"""Concurrency and edge cases around rooms: each test describes the situation it guards against."""
import threading
import time

import pytest
from fastapi.testclient import TestClient

from app import chat, main
from app.main import app


@pytest.fixture
def client():
    with TestClient(app) as client:
        yield client


def bearer(token):
    return {"Authorization": "Bearer " + token}


def test_chat_sent_at_the_same_time_is_never_skipped_by_a_poll(client, monkeypatch):
    host = client.post("/rooms", json={"players": 2, "mode": "online"}).json()
    url = "/rooms/" + host["room"]
    red, yellow = bearer(host["token"]), bearer(client.post(url + "/join").json()["token"])
    original = chat.add

    def slow_first(db, room, kind, seat, body, target=None):
        event = original(db, room, kind, seat, body, target)
        if body == "first":
            time.sleep(0.6)  # Hold the transaction open after taking an id.
        return event
    monkeypatch.setattr(chat, "add", slow_first)
    def send_first():
        with TestClient(app) as other:  # Its own client, so the two requests really overlap.
            other.post(url + "/chat", headers=red, json={"text": "first"})
    first = threading.Thread(target=send_first)
    first.start()
    time.sleep(0.15)
    client.post(url + "/chat", headers=yellow, json={"text": "second"})
    seen = client.get(url, headers=yellow).json()["events"]
    after = max((e["id"] for e in seen), default=0)
    first.join()
    seen += client.get(url + f"?events_after={after}", headers=yellow).json()["events"]
    assert sorted(e["body"] for e in seen) == ["first", "second"]


def test_host_leaving_an_unfilled_room_without_substitutes_ends_it(client):
    host = client.post("/rooms", json={"players": 2, "mode": "online", "substitutes": False}).json()
    url = "/rooms/" + host["room"]
    assert client.post(url + "/leave", headers=bearer(host["token"])).json() == {"ended": True}
    assert client.post(url + "/join").status_code == 404


def test_leaving_before_the_game_starts_frees_the_seat(client):
    host = client.post("/rooms", json={"players": 3, "mode": "online", "substitutes": True}).json()
    url = "/rooms/" + host["room"]
    red = bearer(host["token"])
    green = bearer(client.post(url + "/join", json={"profile": {"name": "Gone", "avatar": "frog"}}).json()["token"])
    client.post(url + "/chat", headers=green, json={"text": "brb"})
    assert client.post(url + "/leave", headers=green).json() == {"ended": False}
    state = client.get(url, headers=red).json()
    assert state["joined"] == 1 and "green" not in state["presence"] and "green" not in state["profiles"]
    assert all(e["seat"] != "green" for e in state["events"])
    newcomer = bearer(client.post(url + "/join", json={"profile": {"name": "New", "avatar": "owl"}}).json()["token"])
    seat = client.get(url, headers=newcomer).json()
    assert seat["seat"] == "green" and seat["profiles"]["green"]["name"] == "New"
    assert seat["presence"]["green"] == "online"


def test_rejected_emotes_do_not_use_up_the_allowance(client):
    host = client.post("/rooms", json={"players": 2, "mode": "online"}).json()
    url = "/rooms/" + host["room"]
    red = bearer(host["token"])
    client.post(url + "/join")
    for _ in range(5):
        assert client.post(url + "/emote", headers=red, json={"emote": "rose", "target": "red"}).status_code == 422
    assert client.post(url + "/emote", headers=red, json={"emote": "rose", "target": "yellow"}).status_code == 201


def test_room_code_collision_retries(client, monkeypatch):
    from app.db import database
    spare = "0f0f0f0f0f"
    with database() as db:
        db.execute("DELETE FROM ludo.rooms WHERE id=%s", (spare,))
    taken = client.post("/rooms", json={"players": 2, "mode": "local"}).json()["room"]
    codes = iter([taken, spare])
    monkeypatch.setattr(main.secrets, "token_hex", lambda _: next(codes))
    created = client.post("/rooms", json={"players": 2, "mode": "local"})
    assert created.status_code == 201 and created.json()["room"] == spare
    with database() as db:
        db.execute("DELETE FROM ludo.rooms WHERE id=%s", (spare,))


def test_chat_while_the_room_is_ending_gets_not_found(client, monkeypatch):
    host = client.post("/rooms", json={"players": 2, "mode": "online"}).json()
    url = "/rooms/" + host["room"]
    red = bearer(host["token"])
    client.post(url + "/join")
    original = main.end_room

    def slow_end(db, room):
        original(db, room)
        time.sleep(0.6)  # The room is deleted but not yet committed.
    monkeypatch.setattr(main, "end_room", slow_end)

    def end():
        with TestClient(app) as other:
            other.post(url + "/end", headers=red)
    ending = threading.Thread(target=end)
    ending.start()
    time.sleep(0.15)
    assert client.post(url + "/chat", headers=red, json={"text": "still here?"}).status_code == 404
    ending.join()


def test_absurd_event_cursor_is_rejected_cleanly(client):
    host = client.post("/rooms", json={"players": 2, "mode": "online"}).json()
    assert client.get("/rooms/" + host["room"] + "?events_after=" + "9" * 30, headers=bearer(host["token"])).status_code == 422


def test_a_middle_seat_freed_before_the_start_is_refilled_without_moving_anyone(client):
    host = client.post("/rooms", json={"players": 4, "mode": "online", "substitutes": True}).json()
    url = "/rooms/" + host["room"]
    red = bearer(host["token"])

    def join(name):
        return bearer(client.post(url + "/join", json={"profile": {"name": name, "avatar": "owl"}}).json()["token"])
    green, yellow = join("Mika"), join("Ravi")
    client.post(url + "/chat", headers=green, json={"text": "back soon"})
    assert client.post(url + "/leave", headers=green).json() == {"ended": False}
    waiting = client.get(url, headers=red).json()
    assert waiting["joined"] == 2 and waiting["seated"] == ["red", "yellow"] and not waiting["ready"]
    assert "green" not in waiting["profiles"] and all(e["seat"] != "green" for e in waiting["events"])
    assert client.get(url, headers=yellow).json()["seat"] == "yellow"  # Nobody else's color changed.
    assert client.post(url + "/emote", headers=red, json={"emote": "rose", "target": "green"}).status_code == 422
    # The next player takes the free green seat, the one after that gets blue, and the game starts.
    newcomer = join("Asha")
    assert client.get(url, headers=newcomer).json()["seat"] == "green"
    last = join("Dev")
    started = client.get(url, headers=last).json()
    assert started["seat"] == "blue" and started["ready"] and started["joined"] == 4
    assert started["seated"] == ["red", "green", "yellow", "blue"]
    assert [started["profiles"][c]["name"] for c in ("green", "yellow", "blue")] == ["Asha", "Ravi", "Dev"]
    assert set(started["presence"].values()) == {"online"}
    assert client.post(url + "/join").status_code == 409


def test_the_creator_leaving_the_waiting_room_keeps_their_seat(client):
    host = client.post("/rooms", json={"players": 3, "mode": "online", "substitutes": True}).json()
    url = "/rooms/" + host["room"]
    green = bearer(client.post(url + "/join").json()["token"])
    assert client.post(url + "/leave", headers=bearer(host["token"])).json() == {"ended": False}
    yellow = bearer(client.post(url + "/join").json()["token"])
    started = client.get(url, headers=yellow).json()
    assert started["seat"] == "yellow" and started["ready"]
    assert started["presence"]["red"] == "computer" and started["presence"]["green"] == "online"

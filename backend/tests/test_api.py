from concurrent.futures import ThreadPoolExecutor

import pytest
from fastapi.testclient import TestClient

from app.main import app


@pytest.fixture
def client():
    with TestClient(app) as client:
        yield client


def test_online(client, monkeypatch):
    result = client.post("/rooms", json={"players": 2, "mode": "online"}).json()
    url = "/rooms/" + result["room"]
    red = {"Authorization": "Bearer " + result["token"]}
    roll = {"action": "roll", "revision": 0}
    assert client.get(url).status_code == 401
    assert client.post(url + "/actions", headers=red, json=roll).status_code == 409
    yellow = {"Authorization": "Bearer " + client.post(url + "/join").json()["token"]}
    assert client.post(url + "/join").status_code == 409
    roll["revision"] = 1
    assert client.post(url + "/actions", headers=yellow, json=roll).status_code == 403
    monkeypatch.setattr("app.main.secrets.randbelow", lambda _: 5)
    def submit(_):
        return client.post(url + "/actions", headers=red, json=roll).status_code
    with ThreadPoolExecutor(2) as pool:
        assert sorted(pool.map(submit, range(2))) == [200, 409]
    response = client.post(url + "/actions", headers=red, json={"revision": 2, "action": "move", "pawn": 0})
    assert response.json()["pawns"][0]["step"] == 0
    assert client.get(url, headers=yellow).json()["revision"] == 3


def test_local_and_restart(client):
    session = client.post("/rooms", json={"players": 4, "mode": "local"}).json()
    path = "/rooms/" + session["room"]
    assert client.post(path + "/join").status_code == 409
    with TestClient(app) as restarted:
        state = restarted.get(path, headers={"Authorization": "Bearer " + session["token"]}).json()
        assert state["ready"] and len(state["pawns"]) == 16


def test_turn_timers_roll_then_move_for_a_slow_seat(client, monkeypatch):
    now = [1000]
    monkeypatch.setattr("app.main.time", type("Clock", (), {"time": lambda: now[0]}))
    monkeypatch.setattr("app.main.secrets.randbelow", lambda _: 5)
    session = client.post("/rooms", json={"players": 2, "mode": "online"}).json()
    path = "/rooms/" + session["room"]
    guest = client.post(path + "/join").json()
    headers = {"Authorization": "Bearer " + guest["token"]}
    now[0] += 4
    waiting = client.get(path, headers=headers).json()
    assert waiting["roll_number"] == 0 and waiting["turn_remaining"] == 1 and waiting["turn_seconds"] == 5
    now[0] += 1
    rolled = client.get(path, headers=headers).json()
    assert rolled["message"] == "Time's up. Red rolled 6." and rolled["phase"] == "move"
    # The move timer starts after clients finish showing the die.
    assert rolled["turn_seconds"] == 15 and rolled["turn_remaining"] == pytest.approx(15.62)
    now[0] += 15
    assert client.get(path, headers=headers).json()["phase"] == "move"
    now[0] += 1
    moved = client.get(path, headers=headers).json()
    assert moved["message"].startswith("Time's up. Red moved pawn") and moved["phase"] == "roll"
    assert moved["turn_seconds"] == 5 and moved["presence"] == {"red": "offline", "yellow": "online"}


def test_player_who_left_rejoins_with_room_code(client):
    host = client.post("/rooms", json={"players": 2, "mode": "online",
                                       "profiles": {"red": {"name": "Nova", "avatar": "owl"}}}).json()
    url = "/rooms/" + host["room"]
    red = {"Authorization": "Bearer " + host["token"]}
    yellow = {"Authorization": "Bearer " + client.post(url + "/join").json()["token"]}
    assert client.post(url + "/join").json()["detail"] == "Room is full."
    client.post(url + "/leave", headers=red)
    seat = client.post(url + "/join", json={"profile": {"name": "nova", "avatar": "fox"}})
    assert seat.status_code == 201
    back = client.get(url, headers={"Authorization": "Bearer " + seat.json()["token"]}).json()
    assert back["seat"] == "red" and back["can_end"] and back["profiles"]["red"]["name"] == "Nova"
    assert client.get(url, headers=red).status_code == 403
    assert client.get(url, headers=yellow).json()["presence"]["red"] == "online"
    assert client.post(url + "/join").status_code == 409


def test_end_room(client):
    session = client.post("/rooms", json={"players": 2, "mode": "local"}).json()
    path = "/rooms/" + session["room"]
    headers = {"Authorization": "Bearer " + session["token"]}
    assert client.post(path + "/leave").status_code == 401
    assert client.post(path + "/leave", headers=headers).status_code == 200
    assert client.get(path, headers=headers).status_code == 200
    assert client.post(path + "/end", headers=headers).status_code == 200
    assert client.get(path, headers=headers).status_code == 404


def test_presence_and_substitute_play_without_waiting(client, monkeypatch):
    now = [1000]
    monkeypatch.setattr("app.main.time", type("Clock", (), {"time": lambda: now[0]}))
    monkeypatch.setattr("app.main.secrets.randbelow", lambda _: 5)
    host = client.post("/rooms", json={"players": 2, "mode": "online", "substitutes": True}).json()
    url = "/rooms/" + host["room"]
    red = {"Authorization": "Bearer " + host["token"]}
    yellow = {"Authorization": "Bearer " + client.post(url + "/join").json()["token"]}
    assert client.get(url, headers=yellow).json()["presence"] == {"red": "online", "yellow": "online"}
    assert client.post(url + "/leave", headers=red).json() == {"ended": False}
    assert client.get(url, headers=yellow).json()["presence"]["red"] == "left"
    assert client.get(url, headers=red).json()["presence"]["red"] == "online"
    client.post(url + "/leave", headers=red)
    now[0] += 299
    timed_out = client.get(url, headers=yellow).json()
    assert timed_out["presence"]["red"] == "left" and timed_out["message"] == "Time's up. Red rolled 6."
    now[0] += 1
    moved = client.get(url, headers=yellow).json()
    assert "computers" not in moved and "substitutes" not in moved
    assert moved["presence"]["red"] == "computer" and moved["turn_remaining"] is None
    assert moved["last_move"]["roll"] == timed_out["roll_number"] and moved["phase"] == "roll"
    assert client.get(url, headers=yellow).json()["revision"] == moved["revision"]
    # The substitute rolls as soon as the pawn has landed instead of waiting five seconds.
    now[0] += 1.5
    assert client.get(url, headers=yellow).json()["roll_number"] == timed_out["roll_number"] + 1
    returned = client.get(url, headers=red).json()
    assert returned["computers"] == [] and returned["presence"]["red"] == "online"
    assert client.post(url + "/end", headers=yellow).status_code == 403
    assert returned["can_end"]
    assert client.post(url + "/end", headers=red).status_code == 200
    assert client.get(url, headers=yellow).status_code == 404

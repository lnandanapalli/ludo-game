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
    host = {"Authorization": "Bearer " + session["token"]}
    now[0] += 10
    client.get(path, headers=host)  # Red is connected but not moving.
    now[0] += 5
    assert client.get(path, headers=headers).json()["phase"] == "move"
    now[0] += 1
    moved = client.get(path, headers=headers).json()
    assert moved["message"].startswith("Time's up. Red moved pawn") and moved["phase"] == "roll"
    assert moved["turn_seconds"] == 5 and moved["presence"] == {"red": "online", "yellow": "online"}
    # Once red is offline its roll still times out as usual, but its move follows a second later.
    now[0] += 15
    rolled = client.get(path, headers=headers).json()
    assert rolled["message"] == "Time's up. Red rolled 6." and rolled["turn_seconds"] == 1
    now[0] += 1.62
    assert client.get(path, headers=headers).json()["message"].startswith("Time's up. Red moved pawn")


def online_room(client, players, substitutes):
    host = client.post("/rooms", json={"players": players, "mode": "online", "substitutes": substitutes}).json()
    url = "/rooms/" + host["room"]
    seats = [{"Authorization": "Bearer " + host["token"]}]
    for _ in range(players - 1):
        seats.append({"Authorization": "Bearer " + client.post(url + "/join").json()["token"]})
    return url, seats


def test_leaving_without_substitutes_removes_the_seat(client):
    url, (red, green, yellow) = online_room(client, 3, substitutes=False)
    assert client.post(url + "/leave", headers=red).json() == {"ended": False}
    state = client.get(url, headers=green).json()
    assert state["out"] == ["red"] and state["presence"]["red"] == "left"
    assert state["current"] == "green" and state["message"] == "Red left the game."
    assert all(p["color"] != "red" for p in state["pawns"])
    # Only the seat's own token could reconnect, and leaving on purpose closes it.
    assert client.get(url, headers=red).json()["detail"] == "You left this game."
    assert client.post(url + "/join").status_code == 409
    client.post(url + "/leave", headers=green)
    won = client.get(url, headers=yellow).json()
    assert won["phase"] == "won" and won["current"] == "yellow"
    assert won["message"] == "Green left the game. Yellow wins!"


def test_leaving_with_substitutes_hands_the_seat_to_a_computer(client, monkeypatch):
    monkeypatch.setattr("app.main.secrets.randbelow", lambda _: 5)
    url, (red, yellow) = online_room(client, 2, substitutes=True)
    client.post(url + "/leave", headers=red)
    played = client.get(url, headers=yellow).json()
    assert played["presence"]["red"] == "computer" and played["roll_number"] == 1
    assert client.get(url, headers=red).status_code == 410


def test_disconnected_seat_is_removed_after_five_minutes_without_substitutes(client, monkeypatch):
    now = [1000]
    monkeypatch.setattr("app.main.time", type("Clock", (), {"time": lambda: now[0]}))
    url, (red, green, yellow) = online_room(client, 3, substitutes=False)
    now[0] += 299
    client.get(url, headers=green)
    # Within five minutes the disconnected seat may reconnect.
    assert client.get(url, headers=yellow).json()["presence"]["red"] == "offline"
    assert client.get(url, headers=red).json()["presence"]["red"] == "online"
    for _ in range(2):
        now[0] += 150
        client.get(url, headers=green)
        removed = client.get(url, headers=yellow).json()
    assert removed["out"] == ["red"] and "removed after 5 minutes offline" in removed["message"]
    assert client.get(url, headers=red).json()["detail"] == "You were removed after 5 minutes offline."


def test_end_room(client):
    session = client.post("/rooms", json={"players": 2, "mode": "local"}).json()
    path = "/rooms/" + session["room"]
    headers = {"Authorization": "Bearer " + session["token"]}
    assert client.post(path + "/leave").status_code == 401
    assert client.post(path + "/leave", headers=headers).status_code == 200
    assert client.get(path, headers=headers).status_code == 200
    assert client.post(path + "/end", headers=headers).status_code == 200
    assert client.get(path, headers=headers).status_code == 404


def test_disconnected_seat_gets_a_computer_and_can_reconnect(client, monkeypatch):
    now = [1000]
    monkeypatch.setattr("app.main.time", type("Clock", (), {"time": lambda: now[0]}))
    monkeypatch.setattr("app.main.secrets.randbelow", lambda _: 5)
    url, (red, yellow) = online_room(client, 2, substitutes=True)
    assert client.get(url, headers=yellow).json()["presence"] == {"red": "online", "yellow": "online"}
    now[0] += 299
    timed_out = client.get(url, headers=yellow).json()
    assert timed_out["presence"]["red"] == "offline" and timed_out["message"] == "Time's up. Red rolled 6."
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

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


def test_turn_timer_plays_for_a_slow_seat(client, monkeypatch):
    now = [1000]
    monkeypatch.setattr("app.main.time", type("Clock", (), {"time": lambda: now[0]}))
    monkeypatch.setattr("app.main.secrets.randbelow", lambda _: 5)
    session = client.post("/rooms", json={"players": 2, "mode": "online"}).json()
    path = "/rooms/" + session["room"]
    guest = client.post(path + "/join").json()
    headers = {"Authorization": "Bearer " + guest["token"]}
    now[0] += 14
    waiting = client.get(path, headers=headers).json()
    assert waiting["roll_number"] == 0 and waiting["turn_remaining"] == 1
    now[0] += 1
    played = client.get(path, headers=headers).json()
    # The six is rolled and, with four equivalent choices, a pawn is moved for red.
    assert played["roll_number"] == 1 and played["message"].startswith("Time's up. Red rolled 6.")
    assert played["last_move"]["pawn"].startswith("red-") and played["current"] == "red"
    assert played["turn_remaining"] == 15 and played["presence"] == {"red": "offline", "yellow": "online"}


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
    assert timed_out["presence"]["red"] == "left" and timed_out["message"].startswith("Time's up.")
    now[0] += 1
    rolled = client.get(url, headers=yellow).json()
    assert "computers" not in rolled and "substitutes" not in rolled
    assert rolled["presence"]["red"] == "computer" and rolled["turn_remaining"] is None
    # The substitute rolls at once instead of waiting out the turn timer.
    assert rolled["phase"] == "move" and rolled["roll_number"] == timed_out["roll_number"] + 1
    assert client.get(url, headers=yellow).json()["revision"] == rolled["revision"]
    now[0] += 1
    moved = client.get(url, headers=yellow).json()
    assert moved["last_move"]["roll"] == rolled["roll_number"]
    returned = client.get(url, headers=red).json()
    assert returned["computers"] == [] and returned["presence"]["red"] == "online"
    assert client.post(url + "/end", headers=yellow).status_code == 403
    assert returned["can_end"]
    assert client.post(url + "/end", headers=red).status_code == 200
    assert client.get(url, headers=yellow).status_code == 404

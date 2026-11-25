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


def test_disconnected_turn_is_skipped_without_substitutes(client, monkeypatch):
    now = [1000]
    monkeypatch.setattr("app.main.time", type("Clock", (), {"time": lambda: now[0]}))
    session = client.post("/rooms", json={"players": 2, "mode": "online"}).json()
    path = "/rooms/" + session["room"]
    guest = client.post(path + "/join").json()
    headers = {"Authorization": "Bearer " + guest["token"]}
    now[0] += 299
    assert client.get(path, headers=headers).status_code == 200
    now[0] += 1
    assert client.get(path, headers=headers).json()["current"] == "yellow"


def test_end_room(client):
    session = client.post("/rooms", json={"players": 2, "mode": "local"}).json()
    path = "/rooms/" + session["room"]
    headers = {"Authorization": "Bearer " + session["token"]}
    assert client.post(path + "/leave").status_code == 401
    assert client.post(path + "/leave", headers=headers).status_code == 200
    assert client.get(path, headers=headers).status_code == 200
    assert client.post(path + "/end", headers=headers).status_code == 200
    assert client.get(path, headers=headers).status_code == 404


def test_substitute_rolls_moves_and_returns_seat(client, monkeypatch):
    now = [1000]
    monkeypatch.setattr("app.main.time", type("Clock", (), {"time": lambda: now[0]}))
    monkeypatch.setattr("app.main.secrets.randbelow", lambda _: 5)
    host = client.post("/rooms", json={"players": 2, "mode": "online", "substitutes": True}).json()
    url = "/rooms/" + host["room"]
    red = {"Authorization": "Bearer " + host["token"]}
    yellow = {"Authorization": "Bearer " + client.post(url + "/join").json()["token"]}
    now[0] += 299
    assert client.get(url, headers=yellow).json()["current"] == "red"
    now[0] += 1
    rolled = client.get(url, headers=yellow).json()
    assert "computers" not in rolled and "substitutes" not in rolled
    assert rolled["phase"] == "move"
    assert client.get(url, headers=yellow).json()["revision"] == rolled["revision"]
    now[0] += 2
    moved = client.get(url, headers=yellow).json()
    assert any(p["step"] == 0 for p in moved["pawns"])
    assert client.get(url, headers=red).json()["computers"] == []
    assert client.post(url + "/leave", headers=red).json() == {"ended": False}
    assert client.post(url + "/end", headers=yellow).status_code == 403
    assert client.get(url, headers=yellow).json()["phase"] == "roll"
    assert client.get(url, headers=red).json()["can_end"]
    assert client.post(url + "/end", headers=red).status_code == 200
    assert client.get(url, headers=yellow).status_code == 404

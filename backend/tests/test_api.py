from concurrent.futures import ThreadPoolExecutor

import pytest
from fastapi.testclient import TestClient

from app.main import app


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("LUDO_DB", str(tmp_path / "game.sqlite3"))
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

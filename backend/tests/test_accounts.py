import secrets

import pytest
from fastapi.testclient import TestClient

from app import security
from app.main import app


@pytest.fixture
def client():
    with TestClient(app) as client:
        yield client


def sign_up(client, name=None, password="correct horse"):
    name = name or "p_" + secrets.token_hex(4)
    response = client.post("/accounts", json={"username": name, "password": password})
    assert response.status_code == 201, response.text
    return name, {"X-Account-Token": response.json()["token"]}


def test_sign_up_sign_in_profile_and_password(client):
    name, account = sign_up(client)
    assert client.post("/accounts", json={"username": name.upper(), "password": "another one"}).status_code == 409
    assert client.post("/accounts", json={"username": "x", "password": "correct horse"}).status_code == 422
    assert client.post("/accounts", json={"username": "good_name", "password": "short"}).status_code == 422
    assert client.post("/sessions", json={"username": name, "password": "wrong password"}).status_code == 401
    assert client.post("/sessions", json={"username": "nobody_" + name, "password": "x" * 8}).status_code == 401
    second = {"X-Account-Token": client.post("/sessions", json={"username": name.upper(),
                                                                "password": "correct horse"}).json()["token"]}
    me = client.get("/me", headers=account).json()
    assert me["username"] == name and me["stats"] == {"games": 0, "wins": 0} and me["games"] == []
    profile = client.put("/me/profile", headers=account, json={"name": "‮No\u0007va ", "avatar": "owl"}).json()
    assert profile["profile"] == {"name": "Nova", "avatar": "owl"}
    assert client.post("/me/password", headers=account, json={"current": "nope", "new": "new password"}).status_code == 403
    assert client.post("/me/password", headers=account,
                       json={"current": "correct horse", "new": "new password"}).status_code == 200
    # Other devices are signed out; this one stays signed in.
    assert client.get("/me", headers=second).status_code == 401
    assert client.get("/me", headers=account).status_code == 200
    assert client.post("/sessions", json={"username": name, "password": "new password"}).status_code == 201
    assert client.delete("/sessions", headers=account).status_code == 200
    assert client.get("/me", headers=account).status_code == 401


def test_delete_account(client):
    name, account = sign_up(client)
    assert client.post("/me/delete", headers=account, json={"password": "wrong"}).status_code == 403
    assert client.post("/me/delete", headers=account, json={"password": "correct horse"}).status_code == 200
    assert client.get("/me", headers=account).status_code == 401
    assert client.post("/sessions", json={"username": name, "password": "correct horse"}).status_code == 401


def test_signed_in_seat_moves_between_devices_and_records_results(client):
    _, host = sign_up(client)
    _, guest = sign_up(client)
    room = client.post("/rooms", headers=host, json={"players": 2, "mode": "online"}).json()
    url = "/rooms/" + room["room"]
    old = {"Authorization": "Bearer " + room["token"]}
    yellow = {"Authorization": "Bearer " + client.post(url + "/join", headers=guest).json()["token"]}
    games = client.get("/me", headers=host).json()["games"]
    assert games[0]["room"] == room["room"] and games[0]["color"] == "red"
    assert client.post(url + "/reclaim", headers=guest | {"X-Account-Token": "bogus"}).status_code == 401
    moved = client.post(url + "/reclaim", headers=host).json()
    assert moved["mode"] == "online"
    red = {"Authorization": "Bearer " + moved["token"]}
    assert client.get(url, headers=old).status_code == 403
    assert client.get(url, headers=red).json()["seat"] == "red"
    _, stranger = sign_up(client)
    assert client.post(url + "/reclaim", headers=stranger).status_code == 404
    client.post(url + "/leave", headers=yellow)  # Substitutes are off, so red wins.
    assert client.get(url, headers=red).json()["phase"] == "won"
    assert client.get("/me", headers=host).json()["stats"] == {"games": 1, "wins": 1}
    me = client.get("/me", headers=guest).json()
    assert me["stats"] == {"games": 1, "wins": 0} and me["games"] == []
    assert client.post(url + "/reclaim", headers=host).status_code == 410


def test_rate_limits_by_address_and_account(client, monkeypatch):
    monkeypatch.setitem(security.LIMITS, "create", (2, 0.0001))
    setup = {"players": 2, "mode": "local"}
    origin = {"Origin": "http://localhost:5173"}
    for _ in range(2):
        assert client.post("/rooms", json=setup).status_code == 201
    limited = client.post("/rooms", json=setup, headers=origin)
    assert limited.status_code == 429 and int(limited.headers["retry-after"]) > 0
    # The browser can read the reply because CORS wraps the limiter.
    assert limited.headers["access-control-allow-origin"] == "http://localhost:5173"
    # A signed-in player has their own allowance.
    _, account = sign_up(client)
    assert client.post("/rooms", json=setup, headers=account).status_code == 201
    monkeypatch.setitem(security.LIMITS, "login-user", (1, 0.0001))
    client.post("/sessions", json={"username": "someone", "password": "x" * 8})
    assert client.post("/sessions", json={"username": "someone", "password": "x" * 8}).status_code == 429


def test_client_address_comes_from_the_trusted_proxy(monkeypatch):
    def scope(forwarded=None):
        headers = [(b"x-forwarded-for", forwarded.encode())] if forwarded else []
        return {"client": ("10.0.0.5", 1234), "headers": headers}
    assert security.client_ip(scope("6.6.6.6")) == "10.0.0.5"  # No proxy configured: ignore the header.
    monkeypatch.setattr(security, "PROXY_HOPS", 1)
    assert security.client_ip(scope("6.6.6.6, 203.0.113.7:51234")) == "203.0.113.7"
    assert security.client_ip(scope("[2001:db8::1]:443")) == "2001:db8::1"
    assert security.client_ip(scope("not-an-address")) == "10.0.0.5"
    assert security.client_ip(scope()) == "10.0.0.5"


def test_request_hardening(client):
    response = client.post("/rooms", content=b"{" + b" " * 20000 + b"}", headers={"Content-Type": "application/json"})
    assert response.status_code == 413
    health = client.get("/health")
    assert health.headers["x-content-type-options"] == "nosniff"
    assert health.headers["content-security-policy"].startswith("default-src 'none'")
    assert client.get("/rooms/../../etc", headers={"Authorization": "Bearer x"}).status_code == 404
    assert client.get("/rooms/ZZZZZZZZZZ", headers={"Authorization": "Bearer x"}).status_code == 404
    assert client.post("/rooms", json={"players": 2, "mode": "local", "profiles": {"purple": {}}}).status_code == 422

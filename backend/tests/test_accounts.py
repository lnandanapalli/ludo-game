import secrets

import pytest
from fastapi.testclient import TestClient

from app import accounts, security
from app.main import app

OUTBOX = []


@pytest.fixture
def client(monkeypatch):
    OUTBOX.clear()
    monkeypatch.setattr(accounts.mail, "configured", lambda: True)
    monkeypatch.setattr(accounts.mail, "send", lambda to, subject, paragraphs, code=None:
                        OUTBOX.append(dict(to=to, subject=subject, text=" ".join(paragraphs), code=code)))
    with TestClient(app) as client:
        yield client


def sign_up(client, name=None, password="correct horse"):
    name = name or "p_" + secrets.token_hex(4)
    email = name + "@example.com"
    response = client.post("/accounts", json={"username": name, "email": email.upper(), "password": password})
    assert response.status_code == 202, response.text
    code = OUTBOX[-1]["code"]
    assert OUTBOX[-1]["to"] == email
    response = client.post("/accounts/verify", json={"email": email, "code": code})
    assert response.status_code == 201, response.text
    return name, {"X-Account-Token": response.json()["token"]}


def test_sign_up_sign_in_profile_and_password(client):
    name, account = sign_up(client)
    taken = {"username": name.upper(), "email": "new_" + name + "@example.com", "password": "another one"}
    assert client.post("/accounts", json=taken).status_code == 409
    assert client.post("/accounts", json={"username": "x", "email": "x@example.com", "password": "correct horse"}).status_code == 422
    assert client.post("/accounts", json={"username": "good_name", "email": "not-an-email", "password": "correct horse"}).status_code == 422
    assert client.post("/accounts", json={"username": "good_name", "email": "g@example.com", "password": "short"}).status_code == 422
    assert client.post("/sessions", json={"login": name, "password": "wrong password"}).status_code == 401
    assert client.post("/sessions", json={"login": "nobody_" + name, "password": "x" * 8}).status_code == 401
    second = {"X-Account-Token": client.post("/sessions", json={"login": name.upper() + "@EXAMPLE.com",
                                                                "password": "correct horse"}).json()["token"]}
    me = client.get("/me", headers=account).json()
    assert me["username"] == name and me["email"] == name + "@example.com"
    assert me["stats"] == {"games": 0, "wins": 0} and me["games"] == []
    profile = client.put("/me/profile", headers=account, json={"name": "‮No\u0007va ", "avatar": "owl"}).json()
    assert profile["profile"] == {"name": "Nova", "avatar": "owl"}
    assert client.post("/me/password", headers=account, json={"current": "nope", "new": "new password"}).status_code == 403
    assert client.post("/me/password", headers=account,
                       json={"current": "correct horse", "new": "new password"}).status_code == 200
    # Other devices are signed out; this one stays signed in.
    assert client.get("/me", headers=second).status_code == 401
    assert client.get("/me", headers=account).status_code == 200
    assert client.post("/sessions", json={"login": name, "password": "new password"}).status_code == 201
    assert client.delete("/sessions", headers=account).status_code == 200
    assert client.get("/me", headers=account).status_code == 401


def test_delete_account(client):
    name, account = sign_up(client)
    assert client.post("/me/delete", headers=account, json={"password": "wrong"}).status_code == 403
    assert client.post("/me/delete", headers=account, json={"password": "correct horse"}).status_code == 200
    assert client.get("/me", headers=account).status_code == 401
    assert client.post("/sessions", json={"login": name, "password": "correct horse"}).status_code == 401


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
    client.post("/sessions", json={"login": "someone", "password": "x" * 8})
    assert client.post("/sessions", json={"login": "someone", "password": "x" * 8}).status_code == 429


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


def test_sign_up_needs_the_emailed_code(client):
    name = "v_" + secrets.token_hex(4)
    email = name + "@example.com"
    form = {"username": name, "email": email, "password": "correct horse"}
    assert client.post("/accounts", json=form).status_code == 202
    code = OUTBOX[-1]["code"]
    wrong = "000000" if code != "000000" else "111111"
    # No account exists until the code is confirmed.
    assert client.post("/sessions", json={"login": name, "password": "correct horse"}).status_code == 401
    replies = [client.post("/accounts/verify", json={"email": email, "code": wrong}).json()["detail"] for _ in range(4)]
    assert replies[0] == "Wrong code. 4 tries left." and replies[-1] == "Wrong code. 1 try left."
    assert client.post("/accounts/resend", json={"email": email}).status_code == 429  # Sent under a minute ago.
    assert client.post("/accounts/verify", json={"email": email, "code": wrong}).json()["detail"].startswith("That code has expired")
    # The code is now used up, even when correct.
    assert client.post("/accounts/verify", json={"email": email, "code": code}).status_code == 400
    assert client.post("/accounts/verify", json={"email": email, "code": "12345"}).status_code == 422


def test_existing_email_is_not_revealed(client):
    name, _ = sign_up(client)
    OUTBOX.clear()
    other = {"username": "o_" + secrets.token_hex(4), "email": name + "@example.com", "password": "correct horse"}
    fresh = {"username": "f_" + secrets.token_hex(4), "email": "f_" + secrets.token_hex(4) + "@example.com",
             "password": "correct horse"}
    taken, new = client.post("/accounts", json=other), client.post("/accounts", json=fresh)
    assert (taken.status_code, taken.json()) == (new.status_code, new.json())
    assert OUTBOX[0]["code"] is None and "already has an account" in OUTBOX[0]["text"]


def test_forgot_password_resets_and_signs_out_everywhere(client):
    name, account = sign_up(client)
    email = name + "@example.com"
    OUTBOX.clear()
    unknown = client.post("/password/forgot", json={"email": "nobody_" + email})
    known = client.post("/password/forgot", json={"email": email.upper()})
    assert (unknown.status_code, unknown.json()) == (known.status_code, known.json()) == (202, known.json())
    assert len(OUTBOX) == 1 and OUTBOX[0]["to"] == email
    code = OUTBOX[0]["code"]
    # A second request within a minute sends nothing new.
    client.post("/password/forgot", json={"email": email})
    assert len(OUTBOX) == 1
    assert client.post("/password/reset", json={"email": email, "code": code, "password": "short"}).status_code == 422
    reset = client.post("/password/reset", json={"email": email, "code": code, "password": "brand new pass"})
    assert reset.status_code == 201 and reset.json()["account"]["username"] == name
    assert client.get("/me", headers=account).status_code == 401
    assert client.post("/password/reset", json={"email": email, "code": code, "password": "again again"}).status_code == 400
    assert client.post("/sessions", json={"login": email, "password": "brand new pass"}).status_code == 201


def test_accounts_need_email_configured(client, monkeypatch):
    monkeypatch.setattr(accounts.mail, "configured", lambda: False)
    form = {"username": "n_" + secrets.token_hex(4), "email": "n@example.com", "password": "correct horse"}
    assert client.post("/accounts", json=form).status_code == 503


def test_code_guesses_are_capped_per_email_across_codes(client, monkeypatch):
    monkeypatch.setitem(security.LIMITS, "code-tries", (3, 0.0001))
    email = "c_" + secrets.token_hex(4) + "@example.com"
    client.post("/accounts", json={"username": "c_" + secrets.token_hex(4), "email": email, "password": "correct horse"})
    wrong = "000000" if OUTBOX[-1]["code"] != "000000" else "111111"
    for _ in range(3):
        assert client.post("/accounts/verify", json={"email": email, "code": wrong}).status_code == 400
    # Requesting a fresh code does not reset the cap.
    assert client.post("/accounts/verify", json={"email": email, "code": OUTBOX[-1]["code"]}).status_code == 429


def test_floods_are_limited_before_any_lookup(client, monkeypatch):
    lookups = []
    monkeypatch.setattr("app.main.resolve", lambda token: lookups.append(token))
    client.get("/health", headers={"X-Account-Token": "not-a-real-token"})
    assert lookups == []  # Malformed tokens never reach the database.
    client.get("/health", headers={"X-Account-Token": "a" * 43})
    assert lookups == ["a" * 43]
    monkeypatch.setitem(security.LIMITS, "address", (2, 0.0001))
    security.limiter.reset()
    assert [client.get("/health").status_code for _ in range(3)] == [200, 200, 429]
    assert client.get("/health").headers["strict-transport-security"]

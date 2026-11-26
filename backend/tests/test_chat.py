import pytest
from fastapi.testclient import TestClient

from app import security
from app.main import app


@pytest.fixture
def client():
    with TestClient(app) as client:
        yield client


def online(client, players=2):
    host = client.post("/rooms", json={"players": players, "mode": "online"}).json()
    url = "/rooms/" + host["room"]
    seats = [{"Authorization": "Bearer " + host["token"]}]
    for _ in range(players - 1):
        seats.append({"Authorization": "Bearer " + client.post(url + "/join").json()["token"]})
    return url, seats


def test_chat_is_delivered_with_polls(client):
    url, (red, yellow) = online(client)
    assert client.get(url, headers=yellow).json()["events"] == []
    sent = client.post(url + "/chat", headers=red, json={"text": "  good\u202e luck\n\n  all\u0007 "})
    assert sent.status_code == 201
    message = sent.json()
    assert (message["kind"], message["seat"], message["body"]) == ("chat", "red", "good luck all")
    events = client.get(url, headers=yellow).json()["events"]
    assert [e["body"] for e in events] == ["good luck all"]
    # Later polls ask only for newer events.
    assert client.get(url + f"?events_after={message['id']}", headers=yellow).json()["events"] == []
    client.post(url + "/chat", headers=yellow, json={"text": "thanks"})
    newer = client.get(url + f"?events_after={message['id']}", headers=red).json()["events"]
    assert [(e["seat"], e["body"]) for e in newer] == [("yellow", "thanks")]
    # Previews (the lobby's saved-game card) carry no chat.
    assert "events" not in client.get(url + "?preview=true", headers=red).json()


def test_chat_validation(client):
    url, (red, _) = online(client)
    assert client.post(url + "/chat", headers=red, json={"text": "\u200b \n"}).status_code == 422
    assert client.post(url + "/chat", headers=red, json={"text": "x" * 201}).status_code == 422
    assert client.post(url + "/chat", headers=red, json={"text": "x" * 200}).status_code == 201
    assert client.post(url + "/chat", json={"text": "hi"}).status_code == 401
    local = client.post("/rooms", json={"players": 2, "mode": "local"}).json()
    assert client.post("/rooms/" + local["room"] + "/chat", json={"text": "hi"},
                       headers={"Authorization": "Bearer " + local["token"]}).status_code == 409


def test_emotes_target_other_players(client):
    url, (red, green, yellow) = online(client, 3)
    snake = client.post(url + "/emote", headers=red, json={"emote": "snake", "target": "green"}).json()
    assert (snake["kind"], snake["seat"], snake["target"], snake["body"]) == ("emote", "red", "green", "snake")
    assert client.post(url + "/emote", headers=red, json={"emote": "ooo"}).status_code == 201
    assert client.post(url + "/emote", headers=red, json={"emote": "snake"}).json()["detail"] == "Choose a player to send that to."
    security.limiter.reset()
    assert client.post(url + "/emote", headers=red, json={"emote": "rose", "target": "red"}).status_code == 422
    assert client.post(url + "/emote", headers=red, json={"emote": "rose", "target": "blue"}).status_code == 422
    assert client.post(url + "/emote", headers=red, json={"emote": "grenade", "target": "green"}).status_code == 422
    client.post(url + "/leave", headers=green)  # Without substitutes, green is removed.
    assert client.post(url + "/emote", headers=red, json={"emote": "rose", "target": "green"}).status_code == 422
    assert client.post(url + "/chat", headers=green, json={"text": "hi"}).status_code == 410


def test_strict_allowances_per_seat(client):
    url, (red, yellow) = online(client)
    for _ in range(3):
        assert client.post(url + "/emote", headers=red, json={"emote": "clap"}).status_code == 201
    limited = client.post(url + "/emote", headers=red, json={"emote": "clap"})
    assert limited.status_code == 429 and 0 < int(limited.headers["retry-after"]) <= 20
    assert limited.json()["detail"].startswith("Too many emotes.")
    # Each seat has its own allowance, and chat is counted separately.
    assert client.post(url + "/emote", headers=yellow, json={"emote": "clap"}).status_code == 201
    for _ in range(6):
        assert client.post(url + "/chat", headers=red, json={"text": "hi"}).status_code == 201
    assert client.post(url + "/chat", headers=red, json={"text": "hi"}).status_code == 429


def test_swearing_is_masked_for_everyone(client):
    from test_profanity import SAMPLES  # Real entries from the library's dictionary, not written here.
    word = SAMPLES[0]
    url, (red, yellow) = online(client)
    sent = client.post(url + "/chat", headers=red, json={"text": f"oh {' '.join(word)} this, nice game!"}).json()
    assert sent["body"] == f"oh {word[0]} {' '.join('*' * (len(word) - 1))} this, nice game!"
    assert client.get(url, headers=yellow).json()["events"][-1]["body"] == sent["body"]

import json

from app import mail


def test_resend_request(monkeypatch):
    monkeypatch.delenv("LUDO_MAIL_DEV", raising=False)
    monkeypatch.setenv("RESEND_API_KEY", "re_test")
    monkeypatch.setenv("LUDO_MAIL_FROM", "Ludo <no-reply@example.com>")
    sent = []

    class Reply:
        def __enter__(self):
            return self

        def __exit__(self, *_):
            return False

        def read(self):
            return b"{}"

    monkeypatch.setattr(mail.urllib.request, "urlopen", lambda request, timeout: sent.append(request) or Reply())
    assert mail.configured()
    mail.send("a@example.com", "Hi", ["Welcome <script>x</script>"], "123456")
    request = sent[0]
    body = json.loads(request.data)
    assert request.full_url == "https://api.resend.com/emails"
    assert request.get_header("Authorization") == "Bearer re_test"
    assert request.get_header("User-agent") == "ludo-api/1.0"
    assert body["to"] == ["a@example.com"] and body["from"] == "Ludo <no-reply@example.com>"
    assert "&lt;script&gt;" in body["html"] and "<script>" not in body["html"]
    assert "123456" in body["text"] and "123456" in body["html"]


def test_not_configured_without_key(monkeypatch):
    for name in ("LUDO_MAIL_DEV", "RESEND_API_KEY", "LUDO_MAIL_FROM"):
        monkeypatch.delenv(name, raising=False)
    assert not mail.configured()

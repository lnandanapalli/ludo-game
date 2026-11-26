"""Transactional email through the Resend HTTP API.

Set RESEND_API_KEY and LUDO_MAIL_FROM (an address on a domain verified in Resend).
For local development, LUDO_MAIL_DEV=1 prints messages instead of sending them and,
when LUDO_MAIL_DIR is set, also writes each one there as JSON (used by the browser tests).
"""
import html
import json
import logging
import os
import time
import urllib.request

log = logging.getLogger("ludo.mail")
API = "https://api.resend.com/emails"


def configured():
    return os.getenv("LUDO_MAIL_DEV") == "1" or bool(os.getenv("RESEND_API_KEY") and os.getenv("LUDO_MAIL_FROM"))


def send(to, subject, paragraphs, code=None):
    """Send a short message. Runs after the response, so failures are logged, not raised."""
    text = "\n\n".join(paragraphs + ([f"Your code: {code}"] if code else []))
    body = "".join(f"<p>{html.escape(p)}</p>" for p in paragraphs)
    if code:
        body += (f'<p style="font-size:28px;font-weight:bold;letter-spacing:6px;font-family:monospace">'
                 f"{html.escape(code)}</p>")
    message = {"to": to, "subject": subject, "text": text,
               "html": f'<div style="font-family:system-ui,sans-serif;line-height:1.5">{body}</div>'}
    if os.getenv("LUDO_MAIL_DEV") == "1":
        print(f"[mail] to={to} subject={subject!r}\n{text}", flush=True)
        folder = os.getenv("LUDO_MAIL_DIR")
        if folder:
            os.makedirs(folder, exist_ok=True)
            with open(os.path.join(folder, f"{time.time_ns()}.json"), "w") as file:
                json.dump(message | {"code": code}, file)
        return
    request = urllib.request.Request(API, method="POST", data=json.dumps({
        "from": os.environ["LUDO_MAIL_FROM"], "to": [to], "subject": subject, "text": text, "html": message["html"],
    }).encode(), headers={
        "Authorization": "Bearer " + os.environ["RESEND_API_KEY"],
        "Content-Type": "application/json",
        "User-Agent": "ludo-api/1.0",  # Resend rejects requests without one.
    })
    try:
        with urllib.request.urlopen(request, timeout=10) as response:
            response.read()
    except Exception as error:  # Never leak mail failures to the client; the user can request a new code.
        log.error("Sending %r failed: %s", subject, error)

"""Client identification, rate limiting and request hardening."""
import ipaddress
import json
import math
import os
import threading
import time

# Number of trusted reverse proxies that append to X-Forwarded-For (Azure App Service: 1).
# Proxies append, so the client address is the entry the outermost trusted proxy added;
# anything to its left came from the client and can be forged.
PROXY_HOPS = int(os.getenv("LUDO_PROXY_HOPS", "0"))
MAX_BODY_BYTES = 16 * 1024

# name: (burst capacity, tokens refilled per second)
LIMITS = {
    "general": (600, 10.0),      # Every request: polling several tabs stays well below this.
    "action": (120, 2.0),        # Rolls and moves.
    "create": (30, 0.1),         # New rooms: a burst of 30, then one every 10 seconds.
    "join": (30, 0.2),
    "signup": (5, 1 / 600),      # Five accounts, then one every 10 minutes.
    "login": (10, 1 / 60),       # Per address.
    "login-user": (10, 1 / 60),  # Per username, against password guessing from many addresses.
    "account": (60, 1.0),        # Profile and password changes.
}


def _strip_port(value):
    value = value.strip()
    if value.startswith("["):  # [IPv6]:port
        value = value[1:value.find("]")]
    elif value.count(":") == 1:  # IPv4:port
        value = value.split(":")[0]
    try:
        return str(ipaddress.ip_address(value))
    except ValueError:
        return None


def client_ip(scope):
    peer = (scope.get("client") or ("unknown", 0))[0]
    if PROXY_HOPS <= 0:
        return peer
    headers = dict(scope.get("headers") or [])
    forwarded = [part for part in headers.get(b"x-forwarded-for", b"").decode("latin-1").split(",") if part.strip()]
    if len(forwarded) < PROXY_HOPS:
        return peer  # Not through the proxy (for example the platform's own health probe).
    return _strip_port(forwarded[-PROXY_HOPS]) or peer


class RateLimiter:
    """In-process token buckets. Each API instance keeps its own counts."""

    def __init__(self):
        self.lock = threading.Lock()
        self.buckets = {}
        self.calls = 0

    def reset(self):
        with self.lock:
            self.buckets.clear()

    def hit(self, name, key):
        """Take one token; return 0 when allowed, else the seconds to wait."""
        capacity, rate = LIMITS[name]
        now = time.monotonic()
        with self.lock:
            self.calls += 1
            if self.calls % 5000 == 0:
                self._prune(now)
            tokens, last = self.buckets.get((name, key), (capacity, now))
            tokens = min(capacity, tokens + (now - last) * rate)
            if tokens < 1:
                self.buckets[(name, key)] = (tokens, now)
                return max(1, math.ceil((1 - tokens) / rate))
            self.buckets[(name, key)] = (tokens - 1, now)
            return 0

    def _prune(self, now):
        for bucket, (tokens, last) in list(self.buckets.items()):
            capacity, rate = LIMITS[bucket[0]]
            if tokens + (now - last) * rate >= capacity:
                del self.buckets[bucket]


limiter = RateLimiter()


async def send_json(send, status, body, headers=()):
    payload = json.dumps(body).encode()
    await send({"type": "http.response.start", "status": status, "headers": [
        (b"content-type", b"application/json"), (b"content-length", str(len(payload)).encode()), *headers]})
    await send({"type": "http.response.body", "body": payload})


class BodyLimit:
    """Reject request bodies over MAX_BODY_BYTES, whether or not Content-Length is sent."""

    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            return await self.app(scope, receive, send)
        length = dict(scope.get("headers") or []).get(b"content-length")
        if length and (not length.isdigit() or int(length) > MAX_BODY_BYTES):
            return await send_json(send, 413, {"detail": "Request too large."})
        received = 0

        async def limited():
            nonlocal received
            message = await receive()
            if message["type"] == "http.request":
                received += len(message.get("body", b""))
                if received > MAX_BODY_BYTES:
                    raise ValueError("Request too large.")
            return message

        try:
            await self.app(scope, limited, send)
        except ValueError as error:
            if str(error) != "Request too large.":
                raise
            await send_json(send, 413, {"detail": "Request too large."})


API_HEADERS = [
    (b"cache-control", b"no-store"),
    (b"x-content-type-options", b"nosniff"),
    (b"referrer-policy", b"no-referrer"),
    (b"x-frame-options", b"DENY"),
    (b"cross-origin-resource-policy", b"same-site"),
]
DOCS = ("/docs", "/redoc", "/openapi.json")


class SecurityHeaders:
    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            return await self.app(scope, receive, send)
        docs = scope["path"].startswith(DOCS)

        async def with_headers(message):
            if message["type"] == "http.response.start":
                names = {name.lower() for name, _ in message.get("headers", [])}
                extra = [h for h in API_HEADERS if h[0] not in names]
                if not docs:
                    extra.append((b"content-security-policy", b"default-src 'none'; frame-ancestors 'none'"))
                message["headers"] = [*message.get("headers", []), *extra]
            await send(message)

        await self.app(scope, receive, with_headers)

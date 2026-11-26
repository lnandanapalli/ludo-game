"""Optional player accounts: sign-up, sessions, profile and match history."""
import hashlib
import hmac
import secrets
import threading
import time
import unicodedata
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, Header, HTTPException
from psycopg.types.json import Jsonb
from pydantic import BaseModel, Field, field_validator

from .db import database
from .security import limiter

router = APIRouter()
SESSION_DAYS = 30
CACHE_SECONDS = 60
SCRYPT = dict(n=2 ** 14, r=8, p=1, dklen=32)
Avatar = Literal["fox", "panda", "tiger", "frog", "owl", "koala"]
Username = Annotated[str, Field(pattern=r"^[A-Za-z0-9_]{3,20}$")]
Password = Annotated[str, Field(min_length=8, max_length=128)]


class Profile(BaseModel):
    name: str = Field(default="", max_length=24)
    avatar: Avatar = "fox"

    @field_validator("name")
    @classmethod
    def printable(cls, name):
        # Drop control and invisible formatting characters (for example right-to-left overrides).
        return "".join(ch for ch in name if unicodedata.category(ch) not in ("Cc", "Cf")).strip()


class SignUp(BaseModel):
    username: Username
    password: Password
    profile: Profile | None = None


class SignIn(BaseModel):
    username: str = Field(max_length=20)
    password: str = Field(max_length=128)


class PasswordChange(BaseModel):
    current: str = Field(max_length=128)
    new: Password


class Confirm(BaseModel):
    password: str = Field(max_length=128)


def digest(token):
    return hashlib.sha256(token.encode()).hexdigest()


def hash_password(password):
    salt = secrets.token_bytes(16)
    key = hashlib.scrypt(password.encode(), salt=salt, **SCRYPT)
    return f"scrypt${salt.hex()}${key.hex()}"


def check_password(password, stored):
    _, salt, key = stored.split("$")
    actual = hashlib.scrypt(password.encode(), salt=bytes.fromhex(salt), **SCRYPT)
    return hmac.compare_digest(actual.hex(), key)


# Spend the same time on unknown usernames as on wrong passwords.
_DUMMY_HASH = hash_password(secrets.token_hex(8))
_cache: dict[str, tuple[int | None, float]] = {}
_cache_lock = threading.Lock()


def resolve(token):
    """Return the account id for a session token, or None. Results are cached briefly."""
    if not token or len(token) > 100:
        return None
    key = digest(token)
    now = time.monotonic()
    with _cache_lock:
        hit = _cache.get(key)
        if hit and now - hit[1] < CACHE_SECONDS:
            return hit[0]
    with database() as db:
        row = db.execute("SELECT account_id FROM ludo.sessions WHERE token_hash=%s AND expires_at > now()",
                         (key,)).fetchone()
    account = row["account_id"] if row else None
    with _cache_lock:
        if len(_cache) > 10000:
            _cache.clear()
        _cache[key] = (account, now)
    return account


def forget_sessions(*keys):
    with _cache_lock:
        for key in keys:
            _cache.pop(key, None)


def optional_account(x_account_token: Annotated[str, Header()] = ""):
    if not x_account_token:
        return None
    account = resolve(x_account_token)
    if account is None:
        raise HTTPException(401, "Your sign-in expired. Please sign in again.")
    return account


def required_account(account: Annotated[int | None, Depends(optional_account)]):
    if account is None:
        raise HTTPException(401, "Sign in first.")
    return account


def start_session(db, account):
    token = secrets.token_urlsafe(32)
    db.execute("INSERT INTO ludo.sessions(token_hash, account_id, expires_at) "
               "VALUES(%s, %s, now() + make_interval(days => %s))", (digest(token), account, SESSION_DAYS))
    db.execute("DELETE FROM ludo.sessions WHERE expires_at < now()")
    return token


def summary(db, account):
    row = db.execute("SELECT username, profile FROM ludo.accounts WHERE id=%s", (account,)).fetchone()
    if row is None:
        raise HTTPException(401, "Your sign-in expired. Please sign in again.")
    stats = db.execute("SELECT count(result) AS games, count(*) FILTER (WHERE result='won') AS wins "
                       "FROM ludo.room_players WHERE account_id=%s", (account,)).fetchone()
    games = []
    for game in db.execute(
            "SELECT r.id, r.state, p.color FROM ludo.room_players p JOIN ludo.rooms r ON r.id = p.room_id "
            "WHERE p.account_id=%s AND p.result IS NULL ORDER BY r.updated_at DESC LIMIT 20", (account,)):
        state, color = game["state"], game["color"]
        if state.get("phase") == "won" or color in state.get("quit", []) or color in state.get("out", []):
            continue
        profiles = state.get("profiles", {})
        games.append(dict(room=game["id"], color=color, started_at=state.get("started_at"),
                          players=[profiles.get(c, {}).get("name") or c.title() for c in state["colors"]]))
    return dict(username=row["username"], profile=row["profile"], games=games,
                stats=dict(games=stats["games"], wins=stats["wins"]))


@router.post("/accounts", status_code=201)
def sign_up(form: SignUp):
    username = form.username.lower()
    profile = (form.profile or Profile(name=form.username)).model_dump()
    with database() as db:
        created = db.execute("INSERT INTO ludo.accounts(username, password_hash, profile) VALUES(%s,%s,%s) "
                             "ON CONFLICT (username) DO NOTHING RETURNING id",
                             (username, hash_password(form.password), Jsonb(profile))).fetchone()
        if created is None:
            raise HTTPException(409, "That username is taken.")
        token = start_session(db, created["id"])
        return dict(token=token, account=summary(db, created["id"]))


@router.post("/sessions", status_code=201)
def sign_in(form: SignIn):
    username = form.username.lower()
    wait = limiter.hit("login-user", username)
    if wait:
        raise HTTPException(429, f"Too many attempts for this username. Try again in {wait} seconds.",
                            headers={"Retry-After": str(wait)})
    with database() as db:
        row = db.execute("SELECT id, password_hash FROM ludo.accounts WHERE username=%s", (username,)).fetchone()
        valid = check_password(form.password, row["password_hash"] if row else _DUMMY_HASH)
        if not row or not valid:
            raise HTTPException(401, "Wrong username or password.")
        token = start_session(db, row["id"])
        return dict(token=token, account=summary(db, row["id"]))


@router.delete("/sessions")
def sign_out(x_account_token: Annotated[str, Header()] = ""):
    key = digest(x_account_token)
    with database() as db:
        db.execute("DELETE FROM ludo.sessions WHERE token_hash=%s", (key,))
    forget_sessions(key)
    return {"signed_out": True}


@router.get("/me")
def me(account: Annotated[int, Depends(required_account)]):
    with database() as db:
        return summary(db, account)


@router.put("/me/profile")
def update_profile(profile: Profile, account: Annotated[int, Depends(required_account)]):
    with database() as db:
        db.execute("UPDATE ludo.accounts SET profile=%s WHERE id=%s", (Jsonb(profile.model_dump()), account))
        return summary(db, account)


@router.post("/me/password")
def change_password(form: PasswordChange, account: Annotated[int, Depends(required_account)],
                    x_account_token: Annotated[str, Header()] = ""):
    with database() as db:
        row = db.execute("SELECT password_hash FROM ludo.accounts WHERE id=%s", (account,)).fetchone()
        if not check_password(form.current, row["password_hash"]):
            raise HTTPException(403, "Current password is wrong.")
        db.execute("UPDATE ludo.accounts SET password_hash=%s WHERE id=%s", (hash_password(form.new), account))
        # Sign out every other device.
        others = db.execute("DELETE FROM ludo.sessions WHERE account_id=%s AND token_hash<>%s RETURNING token_hash",
                            (account, digest(x_account_token))).fetchall()
    forget_sessions(*(row["token_hash"] for row in others))
    return {"changed": True}


@router.post("/me/delete")
def delete_account(form: Confirm, account: Annotated[int, Depends(required_account)]):
    with database() as db:
        row = db.execute("SELECT password_hash FROM ludo.accounts WHERE id=%s", (account,)).fetchone()
        if not check_password(form.password, row["password_hash"]):
            raise HTTPException(403, "Password is wrong.")
        sessions = db.execute("DELETE FROM ludo.sessions WHERE account_id=%s RETURNING token_hash",
                              (account,)).fetchall()
        db.execute("DELETE FROM ludo.accounts WHERE id=%s", (account,))
    forget_sessions(*(row["token_hash"] for row in sessions))
    return {"deleted": True}

"""Optional player accounts: verified sign-up, sessions, password resets, profile and match history."""
import hashlib
import hmac
import secrets
import threading
import time
import unicodedata
from typing import Annotated, Literal

from fastapi import APIRouter, BackgroundTasks, Depends, Header, HTTPException
from psycopg.types.json import Jsonb
from pydantic import BaseModel, Field, field_validator

from . import mail
from .db import database
from .security import limiter

router = APIRouter()
SESSION_DAYS = 30
CACHE_SECONDS = 60
SCRYPT = dict(n=2 ** 14, r=8, p=1, dklen=32)
Avatar = Literal["fox", "panda", "tiger", "frog", "owl", "koala"]
Username = Annotated[str, Field(pattern=r"^[A-Za-z0-9_]{3,20}$")]
Password = Annotated[str, Field(min_length=8, max_length=128)]
Email = Annotated[str, Field(max_length=254, pattern=r"^[^@\s]{1,64}@[^@\s]+\.[^@\s]+$")]
Code = Annotated[str, Field(pattern=r"^[0-9]{6}$")]
CODE_MINUTES = 10
CODE_ATTEMPTS = 5
RESEND_SECONDS = 60


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
    email: Email
    password: Password
    profile: Profile | None = None


class EmailOnly(BaseModel):
    email: Email


class Verify(BaseModel):
    email: Email
    code: Code


class Reset(BaseModel):
    email: Email
    code: Code
    password: Password


class SignIn(BaseModel):
    login: str = Field(max_length=254)  # Username or email address.
    password: str = Field(max_length=128)


class PasswordChange(BaseModel):
    current: str = Field(max_length=128)
    new: Password


class Confirm(BaseModel):
    password: str = Field(max_length=128)


def digest(token):
    return hashlib.sha256(token.encode()).hexdigest()


def code_hash(kind, email, code):
    return digest(f"{kind}:{email}:{code}")


def new_code():
    return f"{secrets.randbelow(10 ** 6):06d}"


def require_mail():
    if not mail.configured():
        raise HTTPException(503, "Email is not set up on this server, so accounts are unavailable.")


def mail_allowed(email):
    """Limit how often any one address is emailed, whoever asks."""
    return limiter.hit("mail-to", email) == 0


def check_code(db, table, key_column, key, kind, email, code):
    """Validate a one-time code row under lock; wrong guesses count toward the attempt limit."""
    wait = limiter.hit("code-tries", f"{kind}:{email}")
    if wait:
        raise HTTPException(429, f"Too many code attempts. Try again in {wait} seconds.",
                            headers={"Retry-After": str(wait)})
    row = db.execute(f"SELECT * FROM ludo.{table} WHERE {key_column}=%s FOR UPDATE", (key,)).fetchone()
    expired = HTTPException(400, "That code has expired. Request a new one.")
    if row is None or row["expires_at"].timestamp() < time.time() or row["attempts"] >= CODE_ATTEMPTS:
        if row is not None:
            db.execute(f"DELETE FROM ludo.{table} WHERE {key_column}=%s", (key,))
        raise expired
    if not hmac.compare_digest(row["code_hash"], code_hash(kind, email, code)):
        left = CODE_ATTEMPTS - row["attempts"] - 1
        db.execute(f"UPDATE ludo.{table} SET attempts = attempts + 1 WHERE {key_column}=%s", (key,))
        if left <= 0:
            raise expired
        raise HTTPException(400, f"Wrong code. {left} {'try' if left == 1 else 'tries'} left.")
    db.execute(f"DELETE FROM ludo.{table} WHERE {key_column}=%s", (key,))
    return row


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
    row = db.execute("SELECT username, email, profile FROM ludo.accounts WHERE id=%s", (account,)).fetchone()
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
    return dict(username=row["username"], email=row["email"], profile=row["profile"], games=games,
                stats=dict(games=stats["games"], wins=stats["wins"]))


SIGNUP_SENT = {"pending": True, "detail": "Check your email for a 6-digit code."}


@router.post("/accounts", status_code=202)
def sign_up(form: SignUp, background: BackgroundTasks):
    """Start a sign-up. The account is created only once the emailed code is confirmed."""
    require_mail()
    username, email = form.username.lower(), form.email.lower()
    profile = (form.profile or Profile(name=form.username)).model_dump()
    with database() as db:
        if db.execute("SELECT 1 FROM ludo.accounts WHERE username=%s", (username,)).fetchone():
            raise HTTPException(409, "That username is taken.")
        password_hash = hash_password(form.password)  # Hashed on both paths so timing reveals nothing.
        if not mail_allowed(email):
            raise HTTPException(429, "Too many codes sent to this address. Try again in a few minutes.")
        if db.execute("SELECT 1 FROM ludo.accounts WHERE email=%s", (email,)).fetchone():
            # Same reply as a new address, so the form never reveals who has an account.
            background.add_task(mail.send, email, "Someone tried to sign up with your email", [
                "Someone tried to create a Ludo account with this email address, which already has an account.",
                "If it was you, sign in, or use \u201cForgot password?\u201d to set a new password. "
                "Otherwise you can ignore this message."])
            return SIGNUP_SENT
        code = new_code()
        db.execute("INSERT INTO ludo.signups(email, username, password_hash, profile, code_hash, expires_at) "
                   "VALUES(%s,%s,%s,%s,%s, now() + make_interval(mins => %s)) ON CONFLICT (email) DO UPDATE SET "
                   "username=EXCLUDED.username, password_hash=EXCLUDED.password_hash, profile=EXCLUDED.profile, "
                   "code_hash=EXCLUDED.code_hash, attempts=0, sent_at=now(), expires_at=EXCLUDED.expires_at",
                   (email, username, password_hash, Jsonb(profile),
                    code_hash("signup", email, code), CODE_MINUTES))
    background.add_task(mail.send, email, f"{code} is your Ludo code", [
        f"Welcome to Ludo, {form.username}! Enter this code to finish creating your account.",
        f"It expires in {CODE_MINUTES} minutes. If you didn't ask for it, ignore this email."], code)
    return SIGNUP_SENT


@router.post("/accounts/resend", status_code=202)
def resend_signup_code(form: EmailOnly, background: BackgroundTasks):
    require_mail()
    email = form.email.lower()
    with database() as db:
        pending = db.execute("SELECT username, sent_at FROM ludo.signups WHERE email=%s FOR UPDATE",
                             (email,)).fetchone()
        if pending and time.time() - pending["sent_at"].timestamp() < RESEND_SECONDS:
            raise HTTPException(429, "Wait a minute before asking for another code.",
                                headers={"Retry-After": str(RESEND_SECONDS)})
        if pending and mail_allowed(email):
            code = new_code()
            db.execute("UPDATE ludo.signups SET code_hash=%s, attempts=0, sent_at=now(), "
                       "expires_at=now() + make_interval(mins => %s) WHERE email=%s",
                       (code_hash("signup", email, code), CODE_MINUTES, email))
            background.add_task(mail.send, email, f"{code} is your Ludo code", [
                f"Enter this code to finish creating your Ludo account. It expires in {CODE_MINUTES} minutes."], code)
    return SIGNUP_SENT


@router.post("/accounts/verify", status_code=201)
def verify_signup(form: Verify):
    email = form.email.lower()
    with database() as db:
        try:
            pending = check_code(db, "signups", "email", email, "signup", email, form.code)
        except HTTPException:
            db.commit()  # Keep the attempt count even though the request fails.
            raise
        created = db.execute(
            "INSERT INTO ludo.accounts(username, email, password_hash, profile) VALUES(%s,%s,%s,%s) "
            "ON CONFLICT DO NOTHING RETURNING id",
            (pending["username"], email, pending["password_hash"], Jsonb(pending["profile"]))).fetchone()
        if created is None:
            db.commit()
            raise HTTPException(409, "That username or email was taken meanwhile. Please sign up again.")
        token = start_session(db, created["id"])
        return dict(token=token, account=summary(db, created["id"]))


RESET_SENT = {"detail": "If an account uses that email, we sent it a 6-digit code."}


@router.post("/password/forgot", status_code=202)
def forgot_password(form: EmailOnly, background: BackgroundTasks):
    require_mail()
    email = form.email.lower()
    with database() as db:
        account = db.execute("SELECT id FROM ludo.accounts WHERE email=%s", (email,)).fetchone()
        if account is None:
            return RESET_SENT
        recent = db.execute("SELECT 1 FROM ludo.password_resets WHERE account_id=%s AND "
                            "sent_at > now() - make_interval(secs => %s)", (account["id"], RESEND_SECONDS)).fetchone()
        if recent or not mail_allowed(email):
            return RESET_SENT
        code = new_code()
        db.execute("INSERT INTO ludo.password_resets(account_id, code_hash, expires_at) "
                   "VALUES(%s,%s, now() + make_interval(mins => %s)) ON CONFLICT (account_id) DO UPDATE SET "
                   "code_hash=EXCLUDED.code_hash, attempts=0, sent_at=now(), expires_at=EXCLUDED.expires_at",
                   (account["id"], code_hash("reset", email, code), CODE_MINUTES))
    background.add_task(mail.send, email, f"{code} is your Ludo password reset code", [
        f"Enter this code to choose a new password. It expires in {CODE_MINUTES} minutes.",
        "If you didn't ask to reset your password, ignore this email; your password stays the same."], code)
    return RESET_SENT


@router.post("/password/reset", status_code=201)
def reset_password(form: Reset):
    email = form.email.lower()
    with database() as db:
        account = db.execute("SELECT id FROM ludo.accounts WHERE email=%s", (email,)).fetchone()
        if account is None:
            raise HTTPException(400, "That code has expired. Request a new one.")
        try:
            check_code(db, "password_resets", "account_id", account["id"], "reset", email, form.code)
        except HTTPException:
            db.commit()
            raise
        db.execute("UPDATE ludo.accounts SET password_hash=%s WHERE id=%s", (hash_password(form.password), account["id"]))
        # A reset signs out every device.
        sessions = db.execute("DELETE FROM ludo.sessions WHERE account_id=%s RETURNING token_hash",
                              (account["id"],)).fetchall()
        token = start_session(db, account["id"])
        result = dict(token=token, account=summary(db, account["id"]))
    forget_sessions(*(row["token_hash"] for row in sessions))
    return result


@router.post("/sessions", status_code=201)
def sign_in(form: SignIn):
    login = form.login.strip().lower()
    wait = limiter.hit("login-user", login)
    if wait:
        raise HTTPException(429, f"Too many attempts for this account. Try again in {wait} seconds.",
                            headers={"Retry-After": str(wait)})
    column = "email" if "@" in login else "username"
    with database() as db:
        row = db.execute(f"SELECT id, password_hash FROM ludo.accounts WHERE {column}=%s", (login,)).fetchone()
        valid = check_password(form.password, row["password_hash"] if row else _DUMMY_HASH)
        if not row or not valid:
            raise HTTPException(401, "Wrong username, email or password.")
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

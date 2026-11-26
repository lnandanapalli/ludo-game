"""HTTP API for local matches and invite-only online rooms."""
import hashlib
import os
import re
import secrets
import threading
import time
from contextlib import asynccontextmanager
from time import monotonic
from dataclasses import fields
from typing import Annotated, Literal

from fastapi import Depends, FastAPI, Header, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from psycopg.types.json import Jsonb
from pydantic import BaseModel, Field
from starlette.concurrency import run_in_threadpool

from .accounts import Profile, optional_account, required_account, resolve, router as accounts_router
from . import chat
from .profanity import censor
from .db import database
from .migrate import migrate
from .game import COLORS, Game
from .security import BodyLimit, SecurityHeaders, client_ip, limiter, send_json

Color = Literal[COLORS]

# Rate-limit groups by route. Sign-up and sign-in always count per address.
LIMITED = [
    ("POST", re.compile(r"^/accounts$"), "signup", True),
    ("POST", re.compile(r"^/sessions$"), "login", True),
    ("POST", re.compile(r"^/(accounts/resend|password/forgot)$"), "send-code", True),
    ("POST", re.compile(r"^/(accounts/verify|password/reset)$"), "check-code", True),
    ("POST", re.compile(r"^/rooms$"), "create", False),
    ("POST", re.compile(r"^/rooms/[^/]+/join$"), "join", False),
    ("POST", re.compile(r"^/rooms/[^/]+/(actions|reclaim)$"), "action", False),
    (None, re.compile(r"^/me(/|$)"), "account", False),
]


class RateLimit:
    """Signed-in players are limited per account, everyone else per client address."""

    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http" or scope["method"] == "OPTIONS":
            return await self.app(scope, receive, send)
        address = "ip:" + client_ip(scope)
        # Checked first, so floods (including ones with made-up sign-in tokens) never reach the database.
        wait = limiter.hit("address", address)
        if wait:
            return await too_many(send, wait)
        token = dict(scope.get("headers") or []).get(b"x-account-token", b"").decode("latin-1")
        account = None
        if TOKEN.fullmatch(token):
            try:
                account = await run_in_threadpool(resolve, token)
            except Exception:  # A database hiccup falls back to the address.
                account = None
        key = f"account:{account}" if account else address
        checks = [("general", key)]
        for method, pattern, name, by_address in LIMITED:
            if (method is None or method == scope["method"]) and pattern.match(scope["path"]):
                checks.append((name, address if by_address else key))
        for name, bucket in checks:
            wait = limiter.hit(name, bucket)
            if wait:
                return await too_many(send, wait)
        await self.app(scope, receive, send)


TOKEN = re.compile(r"[A-Za-z0-9_-]{43}")  # secrets.token_urlsafe(32)


async def too_many(send, wait):
    await send_json(send, 429, {"detail": f"Too many requests. Try again in {wait} seconds."},
                    [(b"retry-after", str(wait).encode())])


@asynccontextmanager
async def lifespan(_):
    # Bring the database schema up to date before serving any request.
    await run_in_threadpool(migrate)
    yield


app = FastAPI(title="Ludo", lifespan=lifespan)
app.include_router(accounts_router)
# The last middleware added runs first: CORS wraps everything so even 429 and 413 replies reach the browser.
app.add_middleware(RateLimit)
app.add_middleware(BodyLimit)
app.add_middleware(SecurityHeaders)
app.add_middleware(CORSMiddleware, allow_origins=[
    origin.strip() for origin in os.getenv("LUDO_ORIGINS", "http://localhost:5173,http://127.0.0.1:5173").split(",")
], allow_methods=["GET", "POST", "PUT", "DELETE"],
    allow_headers=["Authorization", "Content-Type", "X-Account-Token"], expose_headers=["Retry-After"], max_age=600)


class Setup(BaseModel):
    substitutes: bool = False
    profiles: dict[Color, Profile] = Field(default_factory=dict)
    players: int = Field(ge=2, le=4)
    mode: Literal["local", "online"]
    auto_move: dict[Color, bool] = Field(default_factory=dict)


class JoinSetup(BaseModel):
    profile: Profile | None = None
    auto_move: bool = False


class ChatIn(BaseModel):
    text: str = Field(min_length=1, max_length=400)


class EmoteIn(BaseModel):
    emote: Literal[chat.EMOTES]
    target: Color | None = None


class Command(BaseModel):
    action: Literal["roll", "move"]
    revision: int = Field(ge=0)
    pawn: int | None = Field(default=None, ge=0, le=3)


def digest(token):
    return hashlib.sha256(token.encode()).hexdigest()


def credential(authorization: Annotated[str, Header()] = ""):
    if not authorization.startswith("Bearer "):
        raise HTTPException(401, "Seat credential required.")
    return digest(authorization[7:])


def load(db, room, *, lock=False):
    if not re.fullmatch(r"[0-9a-f]{10}", room):
        raise HTTPException(404, "Room not found.")
    query = "SELECT * FROM ludo.rooms WHERE id=%s"
    row = db.execute(query + (" FOR UPDATE" if lock else ""), (room,)).fetchone()
    if row is None:
        raise HTTPException(404, "Room not found.")
    known = {f.name for f in fields(Game)}
    game = Game(**{k: v for k, v in row["state"].items() if k in known})
    return row, game, row["seats"]


ROLL_SECONDS = 5       # Time to roll before the server rolls for the seat.
MOVE_SECONDS = 15      # Time to move before the server moves a random legal pawn.
OFFLINE_MOVE_SECONDS = 1  # An offline seat's move is made almost at once; its roll still waits.
HEARTBEAT_SECONDS = 5  # How often a polling seat refreshes its last_seen time.
OFFLINE_SECONDS = 15   # A seat without a heartbeat for this long shows as offline.
AWAY_SECONDS = 300     # A disconnected seat is substituted, or removed without substitutes, after this.


def seated(game, seats):
    """Colors with a player. Seats are positional (seat i plays colors[i]); a seat given up before the
    game starts is an empty slot (None) until the next player to join takes it."""
    return [color for color, seat in zip(game.colors, seats) if seat]


def presence(row, game, seats, now):
    if row["mode"] != "online":
        return {}
    status = {}
    for color in seated(game, seats):
        if color in game.out:
            status[color] = "left"
        elif color in game.computers:
            status[color] = "computer"
        elif now - game.last_seen.get(color, now) >= OFFLINE_SECONDS:
            status[color] = "offline"
        else:
            status[color] = "online"
    return status


def snapshot(row, game, seats, key):
    if key not in seats:
        raise HTTPException(403, "This seat belongs to another session.")
    color = game.colors[seats.index(key)]
    if color in game.quit:
        raise HTTPException(410, "You left this game.")
    if color in game.out:
        raise HTTPException(410, "You were removed after 5 minutes offline.")
    now = time.time()
    host = seats[0] == key
    players = seated(game, seats)
    ready = row["mode"] == "local" or len(players) == len(game.colors)
    timed = (row["mode"] == "online" and ready and game.phase != "won"
             and game.turn_started is not None and game.current not in game.computers)
    limit = turn_limit(game, now)
    private = {"computers": game.computers, "substitutes": game.substitutes} if host else {}
    return dict(**game.view(), **private, can_end=host, room=row["id"], mode=row["mode"], revision=row["revision"],
                seat=game.colors[seats.index(key)], joined=len(players), seated=players, ready=ready,
                presence=presence(row, game, seats, now), turn_seconds=limit,
                # May exceed turn_seconds while clients still animate the last roll or move.
                turn_remaining=max(0.0, game.turn_started + limit - now) if timed else None)


def turn_limit(game, now):
    if game.phase == "roll":
        return ROLL_SECONDS
    offline = now - game.last_seen.get(game.current, now) >= OFFLINE_SECONDS
    return OFFLINE_MOVE_SECONDS if offline else MOVE_SECONDS


def start_timer(game, now, before):
    """Start the next timer once clients have shown the die and any pawn travel."""
    roll_number, last_roll = before
    settle = 0.0
    rolled = game.roll_number > roll_number
    if rolled:
        settle += 0.62  # Die tumble.
    move = game.last_move
    if move and move["roll"] != last_roll:
        settle += max(0.25, (len(move["path"]) - 1) * 0.165)  # Pawn hops.
        if rolled and move["roll"] == game.roll_number:
            settle += 1.0  # Rolled number held before an automatic move.
    game.turn_started = now + settle


def save(db, room, game, *, seats=None, bump=True):
    """Store the room; when the game has just been won, record each signed-in player's result."""
    row = db.execute("UPDATE ludo.rooms SET state=%s, seats=COALESCE(%s, seats), revision=revision+%s, "
                     "updated_at=now() WHERE id=%s RETURNING *",
                     (Jsonb(game.dump()), None if seats is None else Jsonb(seats), int(bump), room)).fetchone()
    if game.phase == "won":
        db.execute("UPDATE ludo.room_players SET result = CASE WHEN color=%s THEN 'won' ELSE 'lost' END "
                   "WHERE room_id=%s AND result IS NULL", (game.current, room))
    return row


def link(db, room, account, color):
    if account is not None:
        db.execute("INSERT INTO ludo.room_players(room_id, account_id, color) VALUES(%s,%s,%s) "
                   "ON CONFLICT DO NOTHING", (room, account, color))


_last_cleanup = [0.0]
_cleanup_lock = threading.Lock()


def cleanup(db):
    """At most every ten minutes, drop finished rooms after two days and idle rooms after thirty."""
    with _cleanup_lock:
        if monotonic() - _last_cleanup[0] < 600:
            return
        _last_cleanup[0] = monotonic()
    stale = ("updated_at < now() - interval '30 days' "
             "OR (state->>'phase' = 'won' AND updated_at < now() - interval '2 days')")
    db.execute(f"DELETE FROM ludo.room_players p USING ludo.rooms r WHERE p.room_id = r.id "
               f"AND p.result IS NULL AND ({stale})")
    db.execute(f"DELETE FROM ludo.rooms WHERE {stale}")
    db.execute("DELETE FROM ludo.signups WHERE expires_at < now()")
    db.execute("DELETE FROM ludo.password_resets WHERE expires_at < now()")
    db.execute("DELETE FROM ludo.sessions WHERE expires_at < now()")


def progress(game):
    return game.roll_number, (game.last_move or {}).get("roll")


def play_for(game):
    """Take the current seat's next step: roll, or move a random legal pawn."""
    if game.phase == "roll":
        game.roll(secrets.randbelow(6) + 1)
    else:
        game.move(secrets.choice(game.legal()))


@app.get("/health")
def health():
    with database() as db:
        db.execute("SELECT revision FROM ludo.rooms LIMIT 1")
    return {"status": "ok"}


@app.post("/rooms", status_code=201)
def create(setup: Setup, account: Annotated[int | None, Depends(optional_account)]):
    room = secrets.token_hex(5)
    token = secrets.token_urlsafe(32)
    game = Game.new(setup.players)
    if setup.mode == "online":
        game.substitutes = setup.substitutes
        game.last_seen[game.colors[0]] = time.time()
    else:
        game.started_at = time.time()
    eligible = game.colors if setup.mode == "local" else game.colors[:1]
    game.profiles = {c: setup.profiles[c].model_dump() for c in eligible if c in setup.profiles}
    game.auto_move = {c: setup.auto_move.get(c, False) for c in eligible}
    with database() as db:
        for _ in range(5):  # A 40-bit code almost never collides, but never fail if it does.
            if db.execute("INSERT INTO ludo.rooms(id,mode,seats,state) VALUES(%s,%s,%s,%s) "
                          "ON CONFLICT (id) DO NOTHING RETURNING id",
                          (room, setup.mode, Jsonb([digest(token)]), Jsonb(game.dump()))).fetchone():
                break
            room = secrets.token_hex(5)
        else:
            raise HTTPException(503, "Could not create a room. Please try again.")
        if setup.mode == "online":
            link(db, room, account, game.colors[0])
    try:
        with database() as db:  # Separate and best effort, so housekeeping never blocks a new room.
            cleanup(db)
    except Exception:
        pass
    return {"room": room, "token": token}


@app.post("/rooms/{room}/join", status_code=201)
def join(room: str, account: Annotated[int | None, Depends(optional_account)], setup: JoinSetup | None = None):
    token = secrets.token_urlsafe(32)
    with database() as db:
        row, game, seats = load(db, room, lock=True)
        if row["mode"] != "online":
            raise HTTPException(409, "Room is private to one device.")
        if len(seated(game, seats)) >= len(game.colors):
            raise HTTPException(409, "Room is full.")
        # Take the first free seat: one given up before the start, or the next new one.
        slot = next((i for i, seat in enumerate(seats) if not seat), len(seats))
        color = game.colors[slot]
        now = time.time()
        for other in seated(game, seats):
            game.last_seen.setdefault(other, now)
        game.last_seen[color] = now
        if setup and setup.profile:
            game.profiles[color] = setup.profile.model_dump()
        game.auto_move[color] = bool(setup and setup.auto_move)
        link(db, room, account, color)
        if slot < len(seats):
            seats[slot] = digest(token)
        else:
            seats.append(digest(token))
        if len(seated(game, seats)) == len(game.colors):
            game.started_at = game.turn_started = now
        save(db, room, game, seats=seats)
    return {"room": room, "token": token}


@app.post("/rooms/{room}/reclaim", status_code=201)
def reclaim(room: str, account: Annotated[int, Depends(required_account)]):
    """Move a signed-in player's seat to this device; the previous device's credential stops working."""
    with database() as db:
        row, game, seats = load(db, room, lock=True)
        mine = db.execute("SELECT color FROM ludo.room_players WHERE room_id=%s AND account_id=%s",
                          (room, account)).fetchone()
        if mine is None:
            raise HTTPException(404, "You have no seat in this room.")
        color = mine["color"]
        if game.phase == "won":
            raise HTTPException(410, "This game has finished.")
        if color in game.quit or color in game.out:
            raise HTTPException(410, "You left this game.")
        token = secrets.token_urlsafe(32)
        seats[game.colors.index(color)] = digest(token)
        game.last_seen[color] = time.time()
        save(db, room, game, seats=seats)
    return {"room": room, "token": token, "mode": row["mode"]}


@app.get("/rooms/{room}")
def read(room: str, key: Annotated[str, Depends(credential)], preview: bool = False,
         events_after: int = Query(default=0, ge=0, le=2 ** 63 - 1)):
    with database() as db:
        row, game, seats = load(db, room, lock=not preview)
        result = snapshot(row, game, seats, key)
        if not preview and row["mode"] == "online" and game.phase != "won":
            now = time.time()
            seat = result["seat"]
            saved = changed = False
            if now - game.last_seen.get(seat, 0) >= HEARTBEAT_SECONDS:
                for color in seated(game, seats):
                    game.last_seen.setdefault(color, now)
                game.last_seen[seat] = now
                saved = True
            if result["ready"] and game.turn_started is None:
                game.turn_started = now
                saved = True
            playing = [c for c in seated(game, seats) if c not in game.out]
            away = [c for c in playing if c in game.quit or now - game.last_seen[c] >= AWAY_SECONDS]
            if game.substitutes:
                # Seats that left, or stayed disconnected for five minutes, get a computer.
                changed = away != game.computers
                game.computers = away
            else:
                # Without substitutes, a seat disconnected for five minutes is out of the game.
                for color in away:
                    game.remove(color, "was removed after 5 minutes offline")
                    game.turn_started = now
                    changed = True
            if result["ready"] and game.phase != "won":
                before = progress(game)
                if game.current in game.computers:
                    # Substitutes play at once, after clients finish showing the last action.
                    if now >= game.turn_started and now - game.last_bot_action >= 1:
                        play_for(game)
                        game.last_bot_action = now
                        changed = True
                elif now - game.turn_started >= turn_limit(game, now):
                    play_for(game)
                    game.message = "Time's up. " + game.message
                    changed = True
                if changed and progress(game) != before:
                    start_timer(game, now, before)
            if saved or changed:
                row = save(db, room, game, bump=changed)
                result = snapshot(row, game, seats, key)
        if not preview and row["mode"] == "online":
            result["events"] = chat.recent(db, room, events_after)
        return result


def speaker(db, room, key):
    """Authorize a chat or emote from this seat.

    The room row is locked, like every other change to a room: posts are stored in the order polls
    read them, and a room ended at the same moment answers 404 instead of failing the insert.
    """
    row, game, seats = load(db, room, lock=True)
    color = snapshot(row, game, seats, key)["seat"]
    if row["mode"] != "online":
        raise HTTPException(409, "Chat is only available in online rooms.")
    return game, seats, color


def spend(kind, key):
    """Apply the strict per-seat allowance, only once a request is known to be valid."""
    wait = limiter.hit(kind, key)
    if wait:
        what = "messages" if kind == "chat" else "emotes"
        raise HTTPException(429, f"Too many {what}. More in {wait} seconds.", headers={"Retry-After": str(wait)})


@app.post("/rooms/{room}/chat", status_code=201)
def send_chat(room: str, message: ChatIn, key: Annotated[str, Depends(credential)]):
    text = chat.clean(message.text)
    if not text or len(text) > chat.MAX_LENGTH:
        raise HTTPException(422, f"Messages must be 1 to {chat.MAX_LENGTH} characters.")
    text = censor(text)
    with database() as db:
        _, _, color = speaker(db, room, key)
        spend("chat", key)
        return chat.add(db, room, "chat", color, text)


@app.post("/rooms/{room}/emote", status_code=201)
def send_emote(room: str, emote: EmoteIn, key: Annotated[str, Depends(credential)]):
    with database() as db:
        game, seats, color = speaker(db, room, key)
        target = emote.target
        if target is not None and (target == color or target not in seated(game, seats) or target in game.out):
            raise HTTPException(422, "Choose another player in this game.")
        if target is None and emote.emote in chat.THROWS:
            raise HTTPException(422, "Choose a player to send that to.")
        spend("emote", key)
        return chat.add(db, room, "emote", color, emote.emote, target)


@app.post("/rooms/{room}/leave")
def leave(room: str, key: Annotated[str, Depends(credential)]):
    """Online: give up the seat for good. Local: nothing to record; the device can resume."""
    with database() as db:
        row, game, seats = load(db, room, lock=True)
        color = snapshot(row, game, seats, key)["seat"]
        if row["mode"] == "online" and game.phase != "won":
            index = game.colors.index(color)
            if len(seated(game, seats)) < len(game.colors) and index > 0:
                # The game has not started: give the seat back, so the next player to join takes it
                # with the same color. Nobody else's color changes. The creator's seat is never freed,
                # because it carries the power to end the game.
                free_seat(db, room, game, seats, color)
                return {"ended": False}
            game.quit.append(color)
            # Computers only play while some player polls the room. Once nobody is left who could
            # return (every joined seat has left or been removed), end the room instead of
            # leaving it frozen. A merely disconnected player can still return, so they count.
            if not any(c not in game.quit and c not in game.out for c in seated(game, seats)):
                end_room(db, room)
                return {"ended": True}
            if game.substitutes:
                game.computers.append(color)
                game.message = f"{color.title()} left; a computer plays for them."
            else:
                current = game.current
                game.remove(color, "left the game")
                if game.current != current:
                    game.turn_started = time.time()
            save(db, room, game)
    return {"ended": False}


def free_seat(db, room, game, seats, color):
    seats[game.colors.index(color)] = None
    while seats and not seats[-1]:
        seats.pop()  # Keep the list tidy: trailing free seats are the same as never-taken ones.
    for table in (game.profiles, game.auto_move, game.last_seen):
        table.pop(color, None)
    if color in game.computers:
        game.computers.remove(color)
    db.execute("DELETE FROM ludo.room_players WHERE room_id=%s AND color=%s AND result IS NULL", (room, color))
    db.execute("DELETE FROM ludo.room_events WHERE room_id=%s AND (seat=%s OR target=%s)", (room, color, color))
    game.message = f"{color.title()} left before the game started."
    save(db, room, game, seats=seats)


def end_room(db, room):
    db.execute("DELETE FROM ludo.room_players WHERE room_id=%s AND result IS NULL", (room,))
    db.execute("DELETE FROM ludo.rooms WHERE id=%s", (room,))


@app.post("/rooms/{room}/end")
def end(room: str, key: Annotated[str, Depends(credential)]):
    with database() as db:
        row, game, seats = load(db, room, lock=True)
        if not snapshot(row, game, seats, key)["can_end"]:
            raise HTTPException(403, "Only the room creator can end the game.")
        end_room(db, room)
    return {"ended": True}


@app.post("/rooms/{room}/actions")
def act(room: str, command: Command, key: Annotated[str, Depends(credential)]):
    with database() as db:
        row, game, seats = load(db, room, lock=True)
        state = snapshot(row, game, seats, key)
        if command.revision != row["revision"]:
            raise HTTPException(409, "Board changed. Try again.")
        if not state["ready"]:
            raise HTTPException(409, "Waiting for players.")
        if row["mode"] == "online" and state["seat"] != game.current:
            raise HTTPException(403, "Wait for your turn.")
        before = progress(game)
        try:
            if command.action == "roll":
                game.roll(secrets.randbelow(6) + 1)
            else:
                game.move(command.pawn)
        except ValueError as error:
            raise HTTPException(409, str(error)) from error
        now = time.time()
        start_timer(game, now, before)
        if row["mode"] == "online":
            game.last_seen[state["seat"]] = now
        return snapshot(save(db, room, game), game, seats, key)

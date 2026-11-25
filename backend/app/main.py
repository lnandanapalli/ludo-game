"""HTTP API for local matches and invite-only online rooms."""
import hashlib
import os
import secrets
import time
from dataclasses import fields
from typing import Annotated, Literal

from fastapi import Depends, FastAPI, Header, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from psycopg.types.json import Jsonb

from .db import database
from .game import Game


app = FastAPI(title="Ludo")
app.add_middleware(CORSMiddleware, allow_origins=[
    origin.strip() for origin in os.getenv("LUDO_ORIGINS", "http://localhost:5173,http://127.0.0.1:5173").split(",")
], allow_methods=["GET", "POST"], allow_headers=["Authorization", "Content-Type"])


class Profile(BaseModel):
    name: str = Field(default="", max_length=24)
    avatar: Literal["fox", "panda", "tiger", "frog", "owl", "koala"] = "fox"


class Setup(BaseModel):
    substitutes: bool = False
    profiles: dict[str, Profile] = Field(default_factory=dict)
    players: int = Field(ge=2, le=4)
    mode: Literal["local", "online"]
    auto_move: dict[str, bool] = Field(default_factory=dict)


class JoinSetup(BaseModel):
    profile: Profile | None = None
    auto_move: bool = False


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


def presence(row, game, seats, now):
    if row["mode"] != "online":
        return {}
    status = {}
    for color in game.colors[:len(seats)]:
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
    ready = row["mode"] == "local" or len(seats) == len(game.colors)
    timed = (row["mode"] == "online" and ready and game.phase != "won"
             and game.turn_started is not None and game.current not in game.computers)
    limit = turn_limit(game, now)
    private = {"computers": game.computers, "substitutes": game.substitutes} if host else {}
    return dict(**game.view(), **private, can_end=host, room=row["id"], mode=row["mode"], revision=row["revision"],
                seat=game.colors[seats.index(key)], joined=len(seats), ready=ready,
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


def progress(game):
    return game.roll_number, (game.last_move or {}).get("roll")


def play_for(game):
    """Take the current seat's next step: roll, or move a random legal pawn."""
    if game.phase == "roll":
        game.roll(secrets.randbelow(6) + 1)
    else:
        game.move(secrets.choice(game.legal()))


@app.middleware("http")
async def no_cache(request, call_next):
    response = await call_next(request)
    response.headers["Cache-Control"] = "no-store"
    return response


@app.get("/health")
def health():
    with database() as db:
        db.execute("SELECT revision FROM ludo.rooms LIMIT 1")
    return {"status": "ok"}


@app.post("/rooms", status_code=201)
def create(setup: Setup):
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
        db.execute("INSERT INTO ludo.rooms(id,mode,seats,state) VALUES(%s,%s,%s,%s)",
                   (room, setup.mode, Jsonb([digest(token)]), Jsonb(game.dump())))
    return {"room": room, "token": token}


@app.post("/rooms/{room}/join", status_code=201)
def join(room: str, setup: JoinSetup | None = None):
    token = secrets.token_urlsafe(32)
    with database() as db:
        row, game, seats = load(db, room, lock=True)
        if row["mode"] != "online":
            raise HTTPException(409, "Room is private to one device.")
        if len(seats) >= len(game.colors):
            raise HTTPException(409, "Room is full.")
        for color in game.colors[:len(seats)+1]:
            game.last_seen.setdefault(color, time.time())
        if setup and setup.profile:
            game.profiles[game.colors[len(seats)]] = setup.profile.model_dump()
        game.auto_move[game.colors[len(seats)]] = bool(setup and setup.auto_move)
        seats.append(digest(token))
        if len(seats) == len(game.colors):
            game.started_at = game.turn_started = time.time()
        db.execute("UPDATE ludo.rooms SET seats=%s, state=%s, revision=revision+1 WHERE id=%s",
                   (Jsonb(seats), Jsonb(game.dump()), room))
    return {"room": room, "token": token}


@app.get("/rooms/{room}")
def read(room: str, key: Annotated[str, Depends(credential)], preview: bool = False):
    with database() as db:
        row, game, seats = load(db, room, lock=not preview)
        result = snapshot(row, game, seats, key)
        if not preview and row["mode"] == "online" and game.phase != "won":
            now = time.time()
            seat = result["seat"]
            saved = changed = False
            if now - game.last_seen.get(seat, 0) >= HEARTBEAT_SECONDS:
                for color in game.colors[:len(seats)]:
                    game.last_seen.setdefault(color, now)
                game.last_seen[seat] = now
                saved = True
            if result["ready"] and game.turn_started is None:
                game.turn_started = now
                saved = True
            playing = [c for c in game.colors[:len(seats)] if c not in game.out]
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
                row = db.execute("UPDATE ludo.rooms SET state=%s, revision=revision+%s WHERE id=%s RETURNING *",
                                 (Jsonb(game.dump()), int(changed), room)).fetchone()
                result = snapshot(row, game, seats, key)
        return result


@app.post("/rooms/{room}/leave")
def leave(room: str, key: Annotated[str, Depends(credential)]):
    """Online: give up the seat for good. Local: nothing to record; the device can resume."""
    with database() as db:
        row, game, seats = load(db, room, lock=True)
        color = snapshot(row, game, seats, key)["seat"]
        if row["mode"] == "online" and game.phase != "won":
            game.quit.append(color)
            if game.substitutes:
                game.computers.append(color)
                game.message = f"{color.title()} left; a computer plays for them."
            else:
                current = game.current
                game.remove(color, "left the game")
                if game.current != current:
                    game.turn_started = time.time()
            db.execute("UPDATE ludo.rooms SET state=%s, revision=revision+1 WHERE id=%s", (Jsonb(game.dump()), room))
    return {"ended": False}


@app.post("/rooms/{room}/end")
def end(room: str, key: Annotated[str, Depends(credential)]):
    with database() as db:
        row, game, seats = load(db, room, lock=True)
        if not snapshot(row, game, seats, key)["can_end"]:
            raise HTTPException(403, "Only the room creator can end the game.")
        db.execute("DELETE FROM ludo.rooms WHERE id=%s", (room,))
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
        db.execute("UPDATE ludo.rooms SET state=%s, revision=revision+1 WHERE id=%s", (Jsonb(game.dump()), room))
        return snapshot(*load(db, room), key)

"""HTTP API for local matches and invite-only online rooms."""
import hashlib
import os
import secrets
import time
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
    game = Game(**row["state"])
    return row, game, row["seats"]


TURN_SECONDS = 15      # Time to roll or move before the server plays for the seat.
HEARTBEAT_SECONDS = 5  # How often a polling seat refreshes its last_seen time.
OFFLINE_SECONDS = 15   # A seat without a heartbeat for this long shows as offline.
AWAY_SECONDS = 300     # A seat away this long is played by a computer substitute.


def presence(row, game, seats, now):
    if row["mode"] != "online":
        return {}
    status = {}
    for color in game.colors[:len(seats)]:
        if color in game.computers:
            status[color] = "computer"
        elif color in game.left:
            status[color] = "left"
        elif now - game.last_seen.get(color, now) >= OFFLINE_SECONDS:
            status[color] = "offline"
        else:
            status[color] = "online"
    return status


def snapshot(row, game, seats, key):
    if key not in seats:
        raise HTTPException(403, "This seat belongs to another session.")
    now = time.time()
    host = seats[0] == key
    ready = row["mode"] == "local" or len(seats) == len(game.colors)
    timed = (row["mode"] == "online" and ready and game.phase != "won"
             and game.turn_started is not None and game.current not in game.computers)
    private = {"computers": game.computers, "substitutes": game.substitutes} if host else {}
    return dict(**game.view(), **private, can_end=host, room=row["id"], mode=row["mode"], revision=row["revision"],
                seat=game.colors[seats.index(key)], joined=len(seats), ready=ready,
                presence=presence(row, game, seats, now), turn_seconds=TURN_SECONDS,
                turn_remaining=max(0.0, game.turn_started + TURN_SECONDS - now) if timed else None)


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
        if row["mode"] != "online" or len(seats) >= len(game.colors):
            raise HTTPException(409, "Room is full or private to one device.")
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
            if seat in game.left:
                game.left.remove(seat)
                saved = True
            if now - game.last_seen.get(seat, 0) >= HEARTBEAT_SECONDS:
                for color in game.colors[:len(seats)]:
                    game.last_seen.setdefault(color, now)
                game.last_seen[seat] = now
                saved = True
            if result["ready"] and game.turn_started is None:
                game.turn_started = now
                saved = True
            if game.substitutes:
                computers = [c for c in game.colors[:len(seats)] if now - game.last_seen[c] >= AWAY_SECONDS]
                changed = computers != game.computers
                game.computers = computers
            if result["ready"]:
                if game.current in game.computers:
                    if now - game.last_bot_action >= 1:
                        play_for(game)
                        game.last_bot_action = now
                        game.turn_started = now
                        changed = True
                elif now - game.turn_started >= TURN_SECONDS:
                    color = game.current
                    play_for(game)
                    if game.phase == "move" and game.current == color:
                        rolled = game.message
                        play_for(game)
                        game.message = f"{rolled} {game.message}"
                    game.message = "Time's up. " + game.message
                    game.turn_started = now
                    changed = True
            if saved or changed:
                row = db.execute("UPDATE ludo.rooms SET state=%s, revision=revision+%s WHERE id=%s RETURNING *",
                                 (Jsonb(game.dump()), int(changed), room)).fetchone()
                result = snapshot(row, game, seats, key)
        return result


@app.post("/rooms/{room}/leave")
def leave(room: str, key: Annotated[str, Depends(credential)]):
    with database() as db:
        row, game, seats = load(db, room, lock=True)
        state = snapshot(row, game, seats, key)
        if row["mode"] == "online":
            game.last_seen[state["seat"]] = time.time()
            if state["seat"] not in game.left:
                game.left.append(state["seat"])
            db.execute("UPDATE ludo.rooms SET state=%s WHERE id=%s", (Jsonb(game.dump()), room))
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
        try:
            if command.action == "roll":
                game.roll(secrets.randbelow(6) + 1)
            else:
                game.move(command.pawn)
        except ValueError as error:
            raise HTTPException(409, str(error)) from error
        game.turn_started = time.time()
        if row["mode"] == "online":
            game.last_seen[state["seat"]] = game.turn_started
            if state["seat"] in game.left:
                game.left.remove(state["seat"])
        db.execute("UPDATE ludo.rooms SET state=%s, revision=revision+1 WHERE id=%s", (Jsonb(game.dump()), room))
        return snapshot(*load(db, room), key)

"""HTTP API for local matches and invite-only online rooms."""
import hashlib
import json
import os
import secrets
import sqlite3
from contextlib import asynccontextmanager, contextmanager
from typing import Annotated, Literal

from fastapi import Depends, FastAPI, Header, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from .game import Game


@contextmanager
def database(write=False):
    db = sqlite3.connect(os.environ.get("LUDO_DB", "ludo.sqlite3"), timeout=10)
    db.row_factory = sqlite3.Row
    try:
        if write:
            db.execute("BEGIN IMMEDIATE")
        yield db
        db.commit()
    finally:
        db.close()


@asynccontextmanager
async def lifespan(_app):
    with database() as db:
        db.execute("""CREATE TABLE IF NOT EXISTS rooms (
            id TEXT PRIMARY KEY, mode TEXT NOT NULL, seats TEXT NOT NULL,
            state TEXT NOT NULL, revision INTEGER NOT NULL DEFAULT 0)""")
    yield


app = FastAPI(title="Ludo", lifespan=lifespan)
app.add_middleware(CORSMiddleware, allow_origins=[
    origin.strip() for origin in os.getenv("LUDO_ORIGINS", "http://localhost:5173,http://127.0.0.1:5173").split(",")
], allow_methods=["GET", "POST"], allow_headers=["Authorization", "Content-Type"])


class Profile(BaseModel):
    name: str = Field(default="", max_length=24)
    avatar: Literal["fox", "panda", "tiger", "frog", "owl", "koala"] = "fox"


class Setup(BaseModel):
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


def load(db, room):
    row = db.execute("SELECT * FROM rooms WHERE id=?", (room,)).fetchone()
    if row is None:
        raise HTTPException(404, "Room not found.")
    return row, Game(**json.loads(row["state"])), json.loads(row["seats"])


def snapshot(row, game, seats, key):
    if key not in seats:
        raise HTTPException(403, "This seat belongs to another session.")
    return dict(**game.view(), room=row["id"], mode=row["mode"], revision=row["revision"],
                seat=game.colors[seats.index(key)], joined=len(seats),
                ready=row["mode"] == "local" or len(seats) == len(game.colors))


@app.middleware("http")
async def no_cache(request, call_next):
    response = await call_next(request)
    response.headers["Cache-Control"] = "no-store"
    return response


@app.get("/health")
def health():
    with database() as db:
        db.execute("SELECT revision FROM rooms LIMIT 1")
    return {"status": "ok"}


@app.post("/rooms", status_code=201)
def create(setup: Setup):
    room = secrets.token_hex(5)
    token = secrets.token_urlsafe(32)
    game = Game.new(setup.players)
    eligible = game.colors if setup.mode == "local" else game.colors[:1]
    game.profiles = {c: setup.profiles[c].model_dump() for c in eligible if c in setup.profiles}
    game.auto_move = {c: setup.auto_move.get(c, False) for c in eligible}
    with database(True) as db:
        db.execute("INSERT INTO rooms(id,mode,seats,state) VALUES(?,?,?,?)",
                   (room, setup.mode, json.dumps([digest(token)]), json.dumps(game.dump())))
    return {"room": room, "token": token}


@app.post("/rooms/{room}/join", status_code=201)
def join(room: str, setup: JoinSetup | None = None):
    token = secrets.token_urlsafe(32)
    with database(True) as db:
        row, game, seats = load(db, room)
        if row["mode"] != "online" or len(seats) >= len(game.colors):
            raise HTTPException(409, "Room is full or private to one device.")
        if setup and setup.profile:
            game.profiles[game.colors[len(seats)]] = setup.profile.model_dump()
        game.auto_move[game.colors[len(seats)]] = bool(setup and setup.auto_move)
        seats.append(digest(token))
        db.execute("UPDATE rooms SET seats=?, state=?, revision=revision+1 WHERE id=?",
                   (json.dumps(seats), json.dumps(game.dump()), room))
    return {"room": room, "token": token}


@app.get("/rooms/{room}")
def read(room: str, key: Annotated[str, Depends(credential)]):
    with database() as db:
        return snapshot(*load(db, room), key)


@app.post("/rooms/{room}/actions")
def act(room: str, command: Command, key: Annotated[str, Depends(credential)]):
    with database(True) as db:
        row, game, seats = load(db, room)
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
        db.execute("UPDATE rooms SET state=?, revision=revision+1 WHERE id=?", (json.dumps(game.dump()), room))
        return snapshot(*load(db, room), key)

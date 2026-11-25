"""Pure Ludo rules. Progress -1 is the yard, 0 is start, 56 is home."""
from dataclasses import asdict, dataclass, field
from typing import Literal

COLORS = ("red", "green", "yellow", "blue")
QUARTER = [(6, 1), (6, 2), (6, 3), (6, 4), (6, 5), (5, 6), (4, 6),
           (3, 6), (2, 6), (1, 6), (0, 6), (0, 7), (0, 8)]


def rotate(square, turns):
    row, col = square
    for _ in range(turns):
        row, col = col, 14 - row
    return row, col


TRACK = [rotate(square, turn) for turn in range(4) for square in QUARTER]
SAFE = set(TRACK[::13]) | set(TRACK[8::13])


def position(color, pawn, progress):
    turn = COLORS.index(color)
    if progress == -1:
        return rotate((2 + pawn // 2, 2 + pawn % 2), turn)
    if progress <= 50:
        return TRACK[(13 * turn + progress) % 52]
    return rotate((7, progress - 50), turn)


@dataclass
class Game:
    colors: list[str]
    pieces: dict[str, list[int]]
    turn: int = 0
    die: int = 0
    sixes: int = 0
    phase: Literal["roll", "move", "won"] = "roll"
    message: str = "Red starts."

    auto_move: dict[str, bool] = field(default_factory=dict)

    substitutes: bool = False
    computers: list[str] = field(default_factory=list)
    last_bot_action: float = 0
    last_seen: dict[str, float] = field(default_factory=dict)
    profiles: dict = field(default_factory=dict)
    roll_number: int = 0
    roller: str | None = None

    @classmethod
    def new(cls, count):
        colors = ["red", "yellow"] if count == 2 else list(COLORS[:count])
        return cls(colors, {color: [-1] * 4 for color in colors})

    @property
    def current(self):
        return self.colors[self.turn]

    def legal(self):
        if self.phase != "move":
            return []
        return [i for i, step in enumerate(self.pieces[self.current])
                if (step == -1 and self.die == 6) or (0 <= step <= 56 - self.die)]

    def pass_turn(self):
        self.turn = (self.turn + 1) % len(self.colors)
        self.sixes = 0
        self.phase = "roll"

    def roll(self, die):
        if self.phase != "roll":
            raise ValueError("Roll unavailable.")
        self.roll_number += 1
        self.roller = self.current
        self.die = die
        self.sixes = self.sixes + 1 if die == 6 else 0
        self.message = f"{self.current.title()} rolled {die}."
        self.phase = "move"
        if self.sixes == 3:
            self.message += " Third six forfeits the turn."
            self.pass_turn()
        elif not self.legal():
            self.message += " No legal move."
            if die == 6:
                self.phase = "roll"
            else:
                self.pass_turn()
        elif self.auto_move.get(self.current) and len(choices := self.legal()) == 1:
            roll_message = self.message
            self.move(choices[0])
            self.message = f"{roll_message} {self.message}"

    def move(self, pawn):
        if pawn not in self.legal():
            raise ValueError("Choose a highlighted pawn.")
        color = self.current
        pieces = self.pieces[color]
        pieces[pawn] = 0 if pieces[pawn] == -1 else pieces[pawn] + self.die
        destination = position(color, pawn, pieces[pawn])
        captured = 0
        if pieces[pawn] <= 50 and destination not in SAFE:
            for other in self.colors:
                if other == color:
                    continue
                for i, step in enumerate(self.pieces[other]):
                    if 0 <= step <= 50 and position(other, i, step) == destination:
                        self.pieces[other][i] = -1
                        captured += 1
        self.message = f"{color.title()} moved pawn {pawn + 1}."
        if captured:
            self.message += f" Captured {captured}."
        if pieces[pawn] == 56:
            self.message += " Home!"
        if all(step == 56 for step in pieces):
            self.phase = "won"
            self.message = f"{color.title()} wins!"
        elif self.die == 6 or captured or pieces[pawn] == 56:
            self.phase = "roll"
            self.message += " Roll again."
        else:
            self.pass_turn()

    def view(self):
        pawns = []
        for color, pieces in self.pieces.items():
            for i, step in enumerate(pieces):
                row, col = position(color, i, step)
                pawns.append(dict(id=f"{color}-{i+1}", color=color, row=row, col=col, step=step))
        return dict(profiles=self.profiles, roll_number=self.roll_number, roller=self.roller, current=self.current, phase=self.phase, die=self.die, message=self.message,
                    colors=self.colors, pawns=pawns, legal=self.legal())

    def dump(self):
        return asdict(self)

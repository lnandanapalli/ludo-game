import random

import pytest

from app.game import COLORS, SAFE, TRACK, Game, position


def test_routes():
    assert len(set(TRACK)) == 52
    assert len(SAFE) == 8
    for color in COLORS:
        route = [position(color, 0, i) for i in range(57)]
        assert len(set(route)) == 57
        assert all(max(abs(a-c), abs(b-d)) == 1 for (a,b),(c,d) in zip(route,route[1:]))


def test_entry_and_three_sixes():
    g = Game.new(2)
    g.roll(2)
    assert g.current == "yellow"
    for _ in range(2):
        g.roll(6)
        g.move(0)
    assert g.pieces["yellow"][0] == 6
    g.roll(6)
    assert g.current == "red" and g.phase == "roll"


@pytest.mark.parametrize("landing,captured", [(1, True), (8, False)])
def test_capture_and_safe(landing, captured):
    g = Game.new(2)
    g.pieces["red"][0] = landing - 1
    g.pieces["yellow"][:2] = [(landing - 26) % 52] * 2
    g.roll(1)
    g.move(0)
    assert (g.pieces["yellow"][:2] == [-1, -1]) == captured
    assert (g.current == "red") == captured


def test_exact_finish_and_win():
    g = Game.new(2)
    g.pieces["red"] = [55, 56, 56, 56]
    g.roll(2)
    assert g.current == "yellow"
    g.roll(1)
    g.roll(1)
    g.move(0)
    assert g.phase == "won"
    with pytest.raises(ValueError):
        g.roll(6)


@pytest.mark.parametrize("count", [2, 3, 4])
def test_full_match(count):
    rng = random.Random(count)
    g = Game.new(count)
    for _ in range(10000):
        if g.phase == "won":
            break
        g.roll(rng.randint(1, 6))
        if g.legal():
            g.move(rng.choice(g.legal()))
    assert g.phase == "won"


def test_passing_opposing_stack_leaves_it_in_place():
    g = Game.new(2)
    g.pieces["red"][0] = 0
    g.pieces["yellow"][:2] = [28, 28]  # Two squares ahead of red.
    g.roll(3)
    g.move(0)
    assert g.pieces["red"][0] == 3
    assert g.pieces["yellow"][:2] == [28, 28]


@pytest.mark.parametrize("enabled,expected", [(True, 4), (False, 1)])
def test_only_legal_pawn_auto_move(enabled, expected):
    game = Game.new(2)
    game.auto_move["red"] = enabled
    game.pieces["red"][0] = 1
    game.roll(3)
    assert game.pieces["red"][0] == expected
    assert (game.phase == "move") != enabled


def test_auto_move_waits_for_choice_and_respects_other_player():
    game = Game.new(2)
    game.auto_move["red"] = True
    game.roll(6)
    assert game.legal() == [0, 1, 2, 3]
    game.move(0)
    game.roll(2)
    game.pieces["yellow"][2] = 1
    game.roll(1)
    assert game.legal() == [2]

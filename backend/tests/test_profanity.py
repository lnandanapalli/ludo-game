"""Profanity masking tests. Sample words are decoded from the module's list at run time."""
import pytest

from app import profanity
from app.profanity import censor

_LISTS = profanity.decode()
ROOT_SAMPLES = [w for w in sorted(_LISTS["roots"]) if w.isalpha() and len(w) >= 4][::3][:6]
WORD_SAMPLES = [w for w in sorted(_LISTS["words"]) if w.isalpha() and len(w) >= 4][:6]
SAMPLES = ROOT_SAMPLES + WORD_SAMPLES
DIGITS = str.maketrans({"a": "@", "s": "$", "i": "1", "o": "0", "e": "3"})
CYRILLIC = str.maketrans({"a": "а", "e": "е", "o": "о", "c": "с", "p": "р"})

DISGUISES = {
    "plain": lambda w: w,
    "upper": str.upper,
    "repeated": lambda w: w[0] + w[1] * 4 + w[2:],
    "spaced": lambda w: " ".join(w),
    "dotted": lambda w: ".".join(w),
    "digits": lambda w: w[0] + w[1:].translate(DIGITS),
    "look-alike": lambda w: w[0] + w[1:].translate(CYRILLIC),
    "accented": lambda w: w[0] + w[1:].replace("u", "ü").replace("a", "á"),
    "exclaimed": lambda w: w + "!!",
}


def test_list_decodes_and_round_trips():
    assert len(ROOT_SAMPLES) >= 6 and len(WORD_SAMPLES) >= 6
    assert profanity.decode(profanity.encode(_LISTS)) == _LISTS


@pytest.mark.parametrize("disguise", DISGUISES)
@pytest.mark.parametrize("index", range(len(SAMPLES)))
def test_disguised_words_are_masked(disguise, index):
    word = DISGUISES[disguise](SAMPLES[index])
    masked = censor(f"you {word} there")
    assert masked.startswith("you ") and masked.endswith(" there")
    hidden = masked[4:-6]
    assert hidden != word and hidden[0] == word[0] and "*" in hidden
    assert len(hidden) == len(word)
    if disguise == "exclaimed":
        assert hidden.endswith("!!")


@pytest.mark.parametrize("index", range(len(ROOT_SAMPLES)))
def test_roots_match_with_endings_but_not_inside_words(index):
    root = ROOT_SAMPLES[index]
    assert censor(root + "ing") != root + "ing"
    for before in ("zq", "un", "x"):
        assert censor(f"a {before}{root} here") == f"a {before}{root} here"


@pytest.mark.parametrize("before,after", [("zq", "qz"), ("un", "ment"), ("x", ""), ("", "x")])
@pytest.mark.parametrize("index", range(len(WORD_SAMPLES)))
def test_whole_words_are_not_matched_inside_others(before, after, index):
    word = before + WORD_SAMPLES[index] + after
    assert censor(f"a {word} here") == f"a {word} here"


@pytest.mark.parametrize("text", [
    "Good luck!", "Well played!", "Nice move", "So close!", "Oops!", "GG \U0001F91D", "Hurry up! ⏳",
    "I am 100% sure", "a b c", "hello there", "see you next game", "nice roll", "my turn",
    "back in 45s", "brb 5 min", "at 10am", "3rd place", "455 points",
])
def test_ordinary_chat_is_left_alone(text):
    assert censor(text) == text

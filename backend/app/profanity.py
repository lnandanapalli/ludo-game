"""Basic profanity masking for chat messages: each matched word keeps its first letter.

The English word list is kept encoded (compressed and scrambled) and only decoded in memory, so
reading the source never shows it. To review or change the list on purpose:

    python -m app.profanity show            # print the decoded list as JSON
    python -m app.profanity encode FILE     # print the encoded form of a JSON file like that

The list has two parts: "roots" match at the start of a word (so their usual endings are caught
too) and "words" match only as whole words, because they also occur inside ordinary words.
Before matching, words are normalised: look-alike letters from other alphabets and accents become
plain letters, digits and symbols typed in place of letters are decoded, repeated letters are
squeezed, and letters spaced or dotted apart are joined. This is deliberately simple; players can
also mute each other or leave a game.
"""
import base64
import json
import re
import sys
import unicodedata
import zlib

_KEY = b"ludo-board"
_ENCODED = (
    "FK9RPmYMqkF+2Gee+s96GxVq9StMZXgOfbY4lJyhWqxUTF2EfJ7o4rS8GNBheln6XXeAFVzear25vPtlSyUoEu9UJThGBk/K"
    "3HJ4PDzW43XENhf8LDOrg+uphTC5V8pmIhfyqaYp1lZXggBNqCgGCycKxVXfXeelHDoD+YQLsBwpYFRLiFTfJpyqjH4ovM8R"
    "XL6MKe1rJxAxGRUOC9B/Ly2EuGXzZQG9Ys4Pg/rx9f6TSD+vCcH5EO9NzzSSjd03mB+mtooU7v45Ov0njxhatMNpQuPn3F+/"
    "cVkCay9DQBTn0H7PaAAPhkDqeZXoSQjT3Dwvs+XekJ9zsLrXSg=="
)


def encode(lists):
    raw = zlib.compress(json.dumps(lists, separators=(",", ":")).encode(), 9)
    return base64.b64encode(bytes(b ^ _KEY[i % len(_KEY)] for i, b in enumerate(raw))).decode()


def decode(encoded=_ENCODED):
    raw = base64.b64decode(encoded)
    return json.loads(zlib.decompress(bytes(b ^ _KEY[i % len(_KEY)] for i, b in enumerate(raw))))


# Cyrillic and Greek letters that look like Latin ones, mapped to their Latin twins.
LOOKALIKE = str.maketrans(
    "\u0430\u0435\u043e\u0440\u0441\u0443\u0445\u0456\u0458\u0455\u0501\u051b\u051d"
    "\u0410\u0415\u041e\u0420\u0421\u0423\u0425\u0406\u0408\u0405"
    "\u0391\u0392\u0395\u0397\u0399\u039a\u039c\u039d\u039f\u03a1\u03a4\u03a7\u03a5\u0396\u03b1\u03bf",
    "aeopcyxijsdqwaeopcyxijsabehikmnoptxyzao",
)
# Digits and symbols typed in place of letters.
LEET = str.maketrans({"0": "o", "1": "i", "3": "e", "4": "a", "5": "s", "7": "t", "8": "b", "9": "g",
                      "@": "a", "$": "s", "!": "i", "|": "l", "+": "t"})


def squeeze(word):
    """Collapse runs of the same letter to one."""
    return re.sub(r"(.)\1+", r"\1", word)


_LISTS = decode()
ROOTS = tuple(sorted({squeeze(root) for root in _LISTS["roots"]}, key=len, reverse=True))
WORDS = {squeeze(word): len(word) for word in _LISTS["words"]}


def normalise(text):
    text = unicodedata.normalize("NFKD", text.translate(LOOKALIKE))
    return "".join(ch for ch in text if not unicodedata.combining(ch)).lower()


def offensive(token):
    """Whether one word, possibly disguised, is on the list."""
    if token[:1].isdigit():
        return False  # Numbers with units or endings, not disguised words.
    word = re.sub(r"[^a-z]", "", normalise(token).rstrip("!").translate(LEET))
    if not word:
        return False
    plain = squeeze(word)
    if any(plain.startswith(root) for root in ROOTS):
        return True
    # A whole word must be at least as long as the listed one, so a shorter ordinary word that
    # squeezes to the same letters is not mistaken for it.
    return plain in WORDS and len(word) >= WORDS[plain]


def mask(token):
    """Keep the first letter and any trailing exclamation marks; replace the rest with asterisks."""
    core = token.rstrip("!")
    first = next((i for i, ch in enumerate(core) if ch.isalnum() or ch in "@$"), 0)
    hidden = "".join("*" if ch.isalnum() or ch in "@$!|+" else ch for ch in core[first + 1:])
    return core[:first + 1] + hidden + token[len(core):]


# Three or more single characters separated by spaces or punctuation.
SPACED = re.compile(r"(?<![\w@$])[\w@$](?:[\s.\-_*~,]+[\w@$]){2,}(?![\w@$])")
SEPARATORS = re.compile(r"[\s.\-_*~,]")
TOKEN = re.compile(r"[\w@$!|+]+")


def censor(text):
    text = SPACED.sub(lambda m: mask(m.group()) if offensive(SEPARATORS.sub("", m.group())) else m.group(), text)
    return TOKEN.sub(lambda m: mask(m.group()) if offensive(m.group()) else m.group(), text)


if __name__ == "__main__":
    if sys.argv[1:2] == ["show"]:
        print(json.dumps(decode(), indent=2))
    elif sys.argv[1:2] == ["encode"] and len(sys.argv) == 3:
        with open(sys.argv[2]) as file:
            print(encode(json.load(file)))
    else:
        sys.exit("usage: python -m app.profanity show | encode FILE")

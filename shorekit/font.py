"""The kit's 5x7 bitmap font and the driftwood plaque a label is carved on.

Only [A-Z0-9 .'-] exist, so a label cannot carry a homoglyph, a bidi control or a URL. The zero
is slashed so it never reads as O.
"""
import re

from . import MAX_LABEL
from .errors import ShoreError

GLYPH_W, GLYPH_H = 5, 7
SCALE = 2                    # glyphs are drawn at x2
ADVANCE = (GLYPH_W + 1) * SCALE
PAD_X, PAD_Y = 4, 3          # wood around the text, in pixels
PLAQUE_H = GLYPH_H * SCALE + 2 * PAD_Y
GAP = 2                      # pixels of clear ground between the object and its plaque

LABEL_RE = re.compile(r"[A-Z0-9 .'-]{1,%d}" % MAX_LABEL, re.ASCII)

_SRC = {
    "A": ".###. #...# #...# ##### #...# #...# #...#",
    "B": "####. #...# #...# ####. #...# #...# ####.",
    "C": ".###. #...# #.... #.... #.... #...# .###.",
    "D": "####. #...# #...# #...# #...# #...# ####.",
    "E": "##### #.... #.... ####. #.... #.... #####",
    "F": "##### #.... #.... ####. #.... #.... #....",
    "G": ".###. #...# #.... #.### #...# #...# .####",
    "H": "#...# #...# #...# ##### #...# #...# #...#",
    "I": ".###. ..#.. ..#.. ..#.. ..#.. ..#.. .###.",
    "J": "..### ...#. ...#. ...#. ...#. #..#. .##..",
    "K": "#...# #..#. #.#.. ##... #.#.. #..#. #...#",
    "L": "#.... #.... #.... #.... #.... #.... #####",
    "M": "#...# ##.## #.#.# #.#.# #...# #...# #...#",
    "N": "#...# #...# ##..# #.#.# #..## #...# #...#",
    "O": ".###. #...# #...# #...# #...# #...# .###.",
    "P": "####. #...# #...# ####. #.... #.... #....",
    "Q": ".###. #...# #...# #...# #.#.# #..#. .##.#",
    "R": "####. #...# #...# ####. #.#.. #..#. #...#",
    "S": ".#### #.... #.... .###. ....# ....# ####.",
    "T": "##### ..#.. ..#.. ..#.. ..#.. ..#.. ..#..",
    "U": "#...# #...# #...# #...# #...# #...# .###.",
    "V": "#...# #...# #...# #...# #...# .#.#. ..#..",
    "W": "#...# #...# #...# #.#.# #.#.# #.#.# .#.#.",
    "X": "#...# #...# .#.#. ..#.. .#.#. #...# #...#",
    "Y": "#...# #...# .#.#. ..#.. ..#.. ..#.. ..#..",
    "Z": "##### ....# ...#. ..#.. .#... #.... #####",
    "0": ".###. #...# #..## #.#.# ##..# #...# .###.",
    "1": "..#.. .##.. ..#.. ..#.. ..#.. ..#.. .###.",
    "2": ".###. #...# ....# ...#. ..#.. .#... #####",
    "3": "##### ...#. ..#.. ...#. ....# #...# .###.",
    "4": "...#. ..##. .#.#. #..#. ##### ...#. ...#.",
    "5": "##### #.... ####. ....# ....# #...# .###.",
    "6": "..##. .#... #.... ####. #...# #...# .###.",
    "7": "##### ....# ...#. ..#.. .#... .#... .#...",
    "8": ".###. #...# #...# .###. #...# #...# .###.",
    "9": ".###. #...# #...# .#### ....# ...#. .##..",
    " ": "..... ..... ..... ..... ..... ..... .....",
    ".": "..... ..... ..... ..... ..... .##.. .##..",
    "'": "..#.. ..#.. .#... ..... ..... ..... .....",
    "-": "..... ..... ..... ##### ..... ..... .....",
}
GLYPHS = {ch: tuple(src.split(" ")) for ch, src in _SRC.items()}


def check_label(text):
    """Rule 6's text part. Raises ShoreError E_LABEL."""
    if not LABEL_RE.fullmatch(text):
        if len(text) > MAX_LABEL:
            raise ShoreError("E_LABEL", "label is %d characters, max %d" % (len(text), MAX_LABEL))
        for i, ch in enumerate(text):
            if ch not in GLYPHS:
                raise ShoreError("E_LABEL", "label character %d (%s) is not one of A-Z 0-9 space . ' -"
                                 % (i, "0x%02x" % ord(ch) if ord(ch) < 128 else "U+%04X" % ord(ch)))
        raise ShoreError("E_LABEL", "label must be 1-%d characters" % MAX_LABEL)
    if text[0] == " " or text[-1] == " ":
        raise ShoreError("E_LABEL", "label may not start or end with a space")
    if "  " in text:
        raise ShoreError("E_LABEL", "label may not hold two spaces in a row")
    for i in range(len(text) - 1):
        if text[i] == "." and text[i + 1] not in " .":
            raise ShoreError("E_LABEL", "a full stop must be followed by a space or end the label (no URLs)")
    return text


def plaque_width(n):
    return n * ADVANCE - SCALE + 2 * PAD_X


def plaque_cells(text):
    """The plaque as rows of pixels: 'w' wood, 'g' grain, 'i' ink, '.' none.

    Row 0 is the top; the last row is the plaque's foot. The ends are rounded off by one and two
    pixels on the top and bottom two rows, like a worn plank."""
    pw = plaque_width(len(text))
    ph = PLAQUE_H
    rows = []
    for r in range(ph):
        inset = 2 if r in (0, ph - 1) else (1 if r in (1, ph - 2) else 0)
        row = []
        for c in range(pw):
            if c < inset or c >= pw - inset:
                row.append(".")
            elif (r == 2 and c % 7 < 4) or (r == ph - 3 and (c + 3) % 9 < 5):
                row.append("g")
            else:
                row.append("w")
        rows.append(row)
    for i, ch in enumerate(text):
        g = GLYPHS[ch]
        x0 = PAD_X + i * ADVANCE
        for gy in range(GLYPH_H):
            line = g[gy]
            for gx in range(GLYPH_W):
                if line[gx] == "#":
                    for dy in range(SCALE):
                        for dx in range(SCALE):
                            rows[PAD_Y + gy * SCALE + dy][x0 + gx * SCALE + dx] = "i"
    return ["".join(r) for r in rows]

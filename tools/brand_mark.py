"""The pixling mascot mark: a tiny chick holding a paintbrush, placed pixel by pixel (16-ish px, like Clawd).

Vista rules: flat calm value masses, light from the upper left, no black outline (the edge is each colour's own
darker shade), no rim light. Palette from styles/vista.json via pp/brand.py. `mark()` has the brush; `mark_plain()`
is the chick alone, for favicons where every pixel counts.
"""
from __future__ import annotations

from PIL import Image

from pp.brand import LOGO

KEY = {
    "L": "down", "M": "down_mid", "S": "down_shade",     # body: light upper left, shade right and below
    "E": "eye", "B": "bill", "b": "bill_shade", "F": "feet",
    "T": "paint", "t": "paint_light", "C": "ferrule", "W": "wood", "w": "wood_shade",
}

MARK = """
...............t..
.......L.......T..
......LL......tTT.
....MMMMMM....TTT.
...MLLLLLLM...CCC.
..MLLLLLLLMS...W..
..MLELLLLEMS...W..
..MLELLLLEMS...W..
..MLLBBBBMMS...W..
.MMLLbbbbMMSMMMM..
.MMLLLLLMMMSSSSS..
..SMMMMMMMSS...w..
...SSSSSSSS....w..
....F....F........
...FF....FF.......
"""

PLAIN = """
.......L......
......LL......
....MMMMMM....
...MLLLLLLM...
..MLLLLLLLMS..
..MLELLLLEMS..
..MLELLLLEMS..
..MLLBBBBMMS..
.MMLLbbbbMMSS.
.MMLLLLLMMMSS.
..SMMMMMMMSS..
...SSSSSSSS...
....F....F....
...FF....FF...
"""


def _draw(art: str) -> Image.Image:
    rows = art.strip("\n").split("\n")
    im = Image.new("RGBA", (max(len(r) for r in rows), len(rows)), (0, 0, 0, 0))
    for y, row in enumerate(rows):
        for x, ch in enumerate(row):
            if ch in KEY:
                h = LOGO[KEY[ch]].lstrip("#")
                im.putpixel((x, y), tuple(int(h[i:i + 2], 16) for i in (0, 2, 4)) + (255,))
    return im


def mark() -> Image.Image:
    return _draw(MARK)


def mark_plain() -> Image.Image:
    return _draw(PLAIN)


BRUSH, FEET = set("TtCWw"), set("F")
HANDLE_X, HIDDEN_HANDLE = 15, (9, 10)              # where the hand covers the handle in MARK


def _layers(art):
    """The mark as three layers (feet, brush, body incl. arm and hand), so they can move independently."""
    rows = [list(r) for r in art.strip("\n").split("\n")]

    def keep(ok):
        return [[c if ok(c) else "." for c in r] for r in rows]
    brush = keep(BRUSH.__contains__)
    for y in HIDDEN_HANDLE:                          # the handle continues behind the hand (seen when they slide)
        brush[y][HANDLE_X] = "w"
    return keep(FEET.__contains__), brush, keep(lambda c: c not in BRUSH | FEET)


def _down(layer):
    return [["."] * len(layer[0])] + [r[:] for r in layer[:-1]]


def _stack(*layers):
    """Composite bottom to top: the body is last, so the hand sits in front of the handle."""
    out = [r[:] for r in layers[0]]
    for layer in layers[1:]:
        for y, r in enumerate(layer):
            for x, c in enumerate(r):
                if c != ".":
                    out[y][x] = c
    return out


def idle_frames():
    """The mascot's idle, timed by hand (75 ms frames). Actions are offset, never switched on together:
    hold; blink (2 frames); hold; breathe: the body dips 1 px onto its feet and the brush follows a frame late
    (drag); at the bottom the chick hugs the brush in by 1 px (the squash gathers the body); it rises and the brush
    catches up a frame later; hold."""
    feet, brush, body = _layers(MARK)

    def hug(g):                                     # drop column 12 (the arm's outer pixel): arm + brush slide in
        return [r[:12] + r[13:] + ["."] for r in g]

    def blink(g):                                   # eyes close to a 1 px line
        return [[("L" if c == "E" else c) for c in r] if y == 6 else r for y, r in enumerate(g)]

    base = _stack(feet, brush, body)
    lag_down = _stack(feet, brush, _down(body))     # body down, brush still up
    down = _stack(feet, _down(brush), _down(body))
    lag_up = _stack(feet, _down(brush), body)       # body back up, brush still down
    seq = ([base] * 12 + [blink(base)] * 2 + [base] * 8 +
           [lag_down, down] + [hug(down)] * 3 + [down, lag_up] + [base] * 6)
    return [_draw("\n".join("".join(r) for r in g)) for g in seq]

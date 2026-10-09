"""pixling brand: palette, tagline, the mascot's colours and ASCII marks.

The mascot is a tiny chick with a paintbrush, placed pixel by pixel in the vista style (tools/brand_mark.py). A
larger forge-made duckling (specs/sunmeadow/pixling.json) shows off the engine in the GIFs. One source for
tools/brand.py and the CLI's terminal banner.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

from .paths import DATA as ROOT
SPEC = ROOT / "specs" / "sunmeadow" / "pixling.json"
SPRITE = ROOT / "docs" / "brand" / "pixling-sprite.png"   # 1x: the forge duckling, S-facing idle frame
MARK_1X = ROOT / "docs" / "brand" / "pixling-mark-1x.png"  # 1x: the mascot mark, drawn in the terminal

INK = "#2b353a"          # vista slate: text and wordmark on paper
PAPER = "#fbf5e9"        # light background
NIGHT = "#1a2227"        # vista deep slate: dark background
TAGLINE = "the pixel artist for your coding agent"

# The mascot's colours, all from styles/vista.json: leaf_gold down, roof terracotta bill and feet, sea teal paint,
# plaster cream ferrule, wood handle, window slate eyes.
LOGO = {
    "down": "#e2c05a", "down_mid": "#c3962f", "down_shade": "#946a2a",
    "eye": "#2b353a", "bill": "#cc8654", "bill_shade": "#ad6340", "feet": "#ad6340",
    "paint": "#468580", "paint_light": "#86b09c", "ferrule": "#e2ddcc",
    "wood": "#81634b", "wood_shade": "#5e4537",
}

# Plain-text marks for places without colour (logs, plain terminals, docs). Pure ASCII.
ASCII_MARK = r"""
      ,       ^
    .-'-.    /#\
   | o o |   '='
   | <=> |----|
    '---'     |
    "   "
""".strip("\n")


def terminal_banner(stream=sys.stdout) -> str:
    """The mascot in half-block truecolor (two pixels per character) beside the name; empty when piped or NO_COLOR."""
    if os.environ.get("NO_COLOR") or not getattr(stream, "isatty", lambda: False)():
        return ""
    if os.environ.get("COLORTERM", "") not in ("truecolor", "24bit") or not MARK_1X.exists():
        lines = ASCII_MARK.split("\n")
        w = max(len(x) for x in lines) + 3
        lines[2] = lines[2].ljust(w) + "pixling"
        lines[3] = lines[3].ljust(w) + TAGLINE
        return "\n".join(lines) + "\n"
    from PIL import Image
    im = Image.open(MARK_1X).convert("RGBA")
    w, h = im.size
    px = im.load()

    def at(x, y):
        if y >= h:
            return None
        r, g, b, a = px[x, y]
        return "%d;%d;%d" % (r, g, b) if a > 127 else None

    lines = []
    for y in range(0, h, 2):
        out = []
        for x in range(w):
            t, b = at(x, y), at(x, y + 1)
            if t and b:
                out.append("\x1b[38;2;%sm\x1b[48;2;%sm▀\x1b[0m" % (t, b))
            elif t:
                out.append("\x1b[38;2;%sm▀\x1b[0m" % t)
            elif b:
                out.append("\x1b[38;2;%sm▄\x1b[0m" % b)
            else:
                out.append(" ")
        lines.append("".join(out))
    lines[3] += "   \x1b[1mpixling\x1b[0m"
    lines[4] += "   \x1b[2m" + TAGLINE + "\x1b[0m"
    return "\n".join(lines) + "\n"

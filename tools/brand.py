"""pixling brand kit: mascot, wordmark, lockups, favicons, social card, and the animations.

  python3 tools/brand.py            # -> docs/brand/ (builds the mascot spec first, ~15 s)

The mascot mark is a tiny vista-style chick with a paintbrush, placed pixel by pixel (tools/brand_mark.py); a
larger forge-made duckling (specs/sunmeadow/pixling.json) is rendered like any other asset for the engine demo GIFs.
The wordmark is Jersey 15 at its native 27 px (1 px tracking) and the tagline Departure Mono at its native 11 px; the
mark is doubled next to them (one mascot pixel = two font pixels), so everything sits on whole pixels. SVGs are merged pixel
runs (no font needed to view them); PNGs are nearest-neighbour upscales.
"""
from __future__ import annotations

import json
import sys
import tempfile
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from pp.brand import INK, MARK_1X, NIGHT, PAPER, SPEC, SPRITE, TAGLINE  # noqa: E402
from pp.forge import Forge, load_spec  # noqa: E402
from brand_mark import idle_frames, mark as draw_mark, mark_plain  # noqa: E402  (tools/ is on sys.path as a script)

OUT = ROOT / "docs" / "brand"
WORD_FONT = OUT / "fonts" / "Jersey15-Regular.ttf"        # native grid: 27 px
WORD_PX, WORD_TRACK = 27, 1
TAG_FONT = OUT / "fonts" / "DepartureMono-Regular.otf"     # native grid: 11 px
TAG_DIM = {"paper": "#6b7281", "night": "#9599a2"}   # vista stone


def hex_rgba(h, a=255):
    h = h.lstrip("#")
    return tuple(int(h[i:i + 2], 16) for i in (0, 2, 4)) + (a,)


def build_forge_duckling(tmp: Path):
    """Forge build of the engine-demo duckling -> (S idle frame 0 cropped, {(clip, dir): [frames]})."""
    spec = load_spec(str(SPEC))
    spec.pop("shadow", None)                     # no ground shadow on paper; the game build keeps it
    out = tmp / spec["name"]
    Forge(spec).build(out, None)
    meta = json.loads((out / (spec["name"] + ".json")).read_text())
    fw, fh, dirs = meta["frame_w"], meta["frame_h"], meta["directions"]

    def frames(clip, d):
        sh = Image.open(out / f"{spec['name']}_{clip}.png").convert("RGBA")
        r = dirs.index(d)
        cells = [sh.crop((i * fw, r * fh, (i + 1) * fw, (r + 1) * fh)) for i in range(sh.width // fw)]
        return [c for c in cells if c.getbbox()]

    anims = {(c, d): frames(c, d) for c in ("idle", "walk", "attack") for d in ("S", "SE")}
    first = anims[("idle", "S")][0]
    return first.crop(first.getbbox()), anims


def text_image(text, color, font_path, size, track=0) -> Image.Image:
    """A pixel font at its native size, no antialiasing: one font pixel per image pixel, cropped to the ink."""
    font = ImageFont.truetype(str(font_path), size)
    im = Image.new("L", (int(font.getlength(text)) + track * len(text) + 4 * size, 3 * size), 0)
    d = ImageDraw.Draw(im)
    d.fontmode = "1"
    x = size
    for ch in text:                                  # glyph by glyph, so the tracking stays whole pixels
        d.text((x, 2 * size), ch, font=font, fill=255, anchor="ls")
        x += round(font.getlength(ch)) + track
    a = np.array(im) > 127
    ys, xs = np.nonzero(a)
    a = a[ys.min():ys.max() + 1, xs.min():xs.max() + 1]
    out = np.zeros(a.shape + (4,), np.uint8)
    out[a] = hex_rgba(color)
    return Image.fromarray(out)


def word_image(color):
    return text_image("pixling", color, WORD_FONT, WORD_PX, WORD_TRACK)


def lockup(mark, word_color, tag_color=None, bg=None, pad=0, gap=4, k=2) -> Image.Image:
    """Mascot + wordmark (+ tagline), the text block centred on the mascot; gap 4 = three mascot pixels after the brush."""
    mark = up(mark, k)                            # the mascot leads: two font pixels per mascot pixel
    word = word_image(word_color)
    tag = text_image(TAGLINE, tag_color, TAG_FONT, 11) if tag_color else None
    text_h = word.height + (5 + tag.height if tag else 0)
    w = mark.width + gap + max(word.width, tag.width if tag else 0)
    h = max(mark.height, text_h)
    im = Image.new("RGBA", (w + 2 * pad, h + 2 * pad), hex_rgba(bg) if bg else (0, 0, 0, 0))
    im.alpha_composite(mark, (pad, pad + (h - mark.height) // 2))
    x, top = pad + mark.width + gap, pad + (h - text_h) // 2
    im.alpha_composite(word, (x, top))
    if tag:
        im.alpha_composite(tag, (x + 1, top + word.height + 5))
    return im


def svg(im: Image.Image, scale=8) -> str:
    """Pixel image -> SVG of merged horizontal runs (crisp at any size)."""
    a = np.array(im.convert("RGBA"))
    h, w = a.shape[:2]
    parts = []
    for y in range(h):
        x = 0
        while x < w:
            if a[y, x, 3] == 0:
                x += 1
                continue
            c = tuple(a[y, x])
            x0 = x
            while x < w and tuple(a[y, x]) == c:
                x += 1
            fill = "#%02x%02x%02x" % c[:3]
            op = "" if c[3] == 255 else ' fill-opacity="%.2f"' % (c[3] / 255)
            parts.append(f'<rect x="{x0}" y="{y}" width="{x - x0}" height="1" fill="{fill}"{op}/>')
    return (f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {w} {h}" width="{w * scale}" height="{h * scale}" '
            f'shape-rendering="crispEdges">' + "".join(parts) + "</svg>\n")


def up(im, k):
    return im.resize((im.width * k, im.height * k), Image.NEAREST)


def square(im, bg, pad):
    s = max(im.width, im.height) + 2 * pad
    out = Image.new("RGBA", (s, s), hex_rgba(bg) if bg else (0, 0, 0, 0))
    out.alpha_composite(im, ((s - im.width) // 2, (s - im.height) // 2))
    return out


def gif(frames, path, bg, k=6, ms=75):
    """Animated mascot on a paper card; every frame shares one box so the feet stay put."""
    boxes = [f.getbbox() for f in frames]
    box = (min(b[0] for b in boxes), min(b[1] for b in boxes), max(b[2] for b in boxes), max(b[3] for b in boxes))
    cards = []
    for f in frames:
        c = Image.new("RGBA", (box[2] - box[0] + 8, box[3] - box[1] + 8), hex_rgba(bg))
        c.alpha_composite(f.crop(box), (4, 4))
        cards.append(up(c, k).convert("RGB"))
    cards[0].save(path, save_all=True, append_images=cards[1:], duration=ms, loop=0)


def social(mark) -> Image.Image:
    """GitHub social preview, 1280 x 640 (drawn at 320 x 160, x4): the mascot, the name, the tagline."""
    card = Image.new("RGBA", (320, 160), hex_rgba(PAPER))
    big = up(mark, 4)
    word = up(word_image(INK), 2)                 # same ratio as the lockups: one mascot pixel = two font pixels
    tag = text_image(TAGLINE, TAG_DIM["paper"], TAG_FONT, 11)
    block_w = big.width + 8 + word.width
    x0 = (320 - block_w) // 2
    card.alpha_composite(big, (x0, 26))
    card.alpha_composite(word, (x0 + big.width + 8, 26 + (big.height - word.height) // 2))
    card.alpha_composite(tag, ((320 - tag.width) // 2, 112))
    return up(card, 4)


def build():
    OUT.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory() as tmp:
        sprite, anims = build_forge_duckling(Path(tmp))
    sprite.save(SPRITE)
    mark, plain = draw_mark(), mark_plain()
    mark.save(MARK_1X)
    up(mark, 8).save(OUT / "pixling-mark.png")
    (OUT / "pixling-mark.svg").write_text(svg(mark))
    (OUT / "pixling-mark-plain.svg").write_text(svg(plain))
    for px, im, k in ((16, plain, 1), (32, plain, 2), (64, mark, 3)):   # favicons: whole-pixel scales, centred
        sq = Image.new("RGBA", (px, px), (0, 0, 0, 0))
        big = up(im, k)
        sq.alpha_composite(big, ((px - big.width) // 2, (px - big.height) // 2))
        sq.save(OUT / f"favicon-{px}.png")
    up(square(mark, PAPER, 3), 16).save(OUT / "pixling-app-icon.png")
    gif(idle_frames(), OUT / "pixling-mark-idle.gif", PAPER, k=10)
    up(sprite, 8).save(OUT / "pixling-forge-duckling.png")

    for name, word, tag, bg in (("pixling-logo", INK, None, None), ("pixling-logo-dark", PAPER, None, None),
                                ("pixling-banner", INK, TAG_DIM["paper"], PAPER),
                                ("pixling-banner-dark", PAPER, TAG_DIM["night"], NIGHT)):
        im = lockup(mark, word, tag, bg=bg, pad=14 if bg else 0)
        k = 3 if bg else 4
        up(im, k).save(OUT / f"{name}.png")
        (OUT / f"{name}.svg").write_text(svg(im, k))
    social(mark).convert("RGB").save(OUT / "pixling-social.png")

    gif(anims[("walk", "SE")], OUT / "pixling-walk.gif", PAPER)
    gif(anims[("attack", "SE")], OUT / "pixling-paint.gif", PAPER)
    gif(anims[("idle", "S")], OUT / "pixling-idle.gif", PAPER)
    return sorted(p.name for p in OUT.iterdir() if p.is_file())


if __name__ == "__main__":
    for n in build():
        print(OUT / n)

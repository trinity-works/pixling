"""From keyed source frames to placed sprite frames: feet/torso measures, loop cycles, one-scale placement.

A keyed take is a list of Cel (RGBA crop + its offset in the source frame). Everything stays at source
resolution until `place` scales it once. `contact` draws a numbered sheet of source frames: the tool for
picking frames by eye.
"""
from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
from PIL import Image


@dataclass
class Cel:
    rgba: np.ndarray            # HxWx4 uint8 crop
    x0: int                     # crop offset in the source frame
    y0: int
    feet: tuple = (0.0, 0.0)    # source-frame foot point (x = centre of the lowest band, y = bottom)
    box: tuple = (0, 0, 0, 0)   # source-frame bbox of solid alpha
    hold: int = 1               # output repeats (set by the EDL)
    event: str | None = None
    src: tuple = ("", 0)        # (take, frame index) for the review


def measure(cel: Cel, band: float = 0.05) -> Cel:
    a = cel.rgba[..., 3]
    ys, xs = np.nonzero(a >= 128)
    if len(ys) == 0:
        cel.box = (cel.x0, cel.y0, cel.x0 + 1, cel.y0 + 1)
        cel.feet = (cel.x0, cel.y0)
        return cel
    y1 = ys.max()
    h = y1 - ys.min() + 1
    low = ys >= y1 - max(2, int(h * band))
    cel.box = (cel.x0 + int(xs.min()), cel.y0 + int(ys.min()), cel.x0 + int(xs.max()) + 1, cel.y0 + int(y1) + 1)
    cel.feet = (cel.x0 + float(np.median(xs[low])), float(cel.y0 + y1 + 1))
    return cel


def torso_x(cel: Cel, band=(0.3, 0.62)) -> float:
    """Median x of the solid pixels in the upper-body band: holds still while cape, weapon and feet swing."""
    a = cel.rgba[..., 3] >= 128
    y0, y1 = cel.box[1] - cel.y0, cel.box[3] - cel.y0
    lo, hi = int(y0 + (y1 - y0) * band[0]), int(y0 + (y1 - y0) * band[1])
    ys, xs = np.nonzero(a[lo:hi])
    return cel.x0 + float(np.median(xs)) if len(xs) else cel.feet[0]


def body_height(cel: Cel, step=4, open_frac=0.07) -> float:
    """Head-to-feet height without thin weapon shafts: the silhouette opened with a kernel ~7% of its height,
    largest blob kept. Used to put every facing's start frame on one body size."""
    from scipy import ndimage
    m = cel.rgba[::step, ::step, 3] >= 128
    ys = np.nonzero(m.any(1))[0]
    if len(ys) == 0:
        return 1.0
    k = max(3, int((ys.max() - ys.min()) * open_frac))
    o = ndimage.binary_opening(m, structure=np.ones((k, k)))
    lab, n = ndimage.label(o)
    if n == 0:
        return float(height(cel))
    big = int(np.argmax(ndimage.sum(o, lab, range(1, n + 1)))) + 1
    ys = np.nonzero((lab == big).any(1))[0]
    return float((ys.max() - ys.min()) * step)


def height(cel: Cel) -> int:
    return cel.box[3] - cel.box[1]


def thumb(cel: Cel, origin, s, size=48):
    """Small grayscale+alpha signature placed in a fixed window around the origin (for similarity)."""
    ox, oy = origin
    win = size / s                                   # source pixels covered by the thumb window
    im = Image.new("RGBA", (int(win * 1.2), int(win * 1.2)), (0, 0, 0, 0))
    im.paste(Image.fromarray(cel.rgba), (int(cel.x0 - ox + win * 0.6), int(cel.y0 - oy + win * 1.1)))
    im = im.resize((size, size), Image.BOX)
    t = np.asarray(im, np.float32) / 255.0
    return np.concatenate([t[..., :3].mean(-1) * t[..., 3], t[..., 3]]).ravel()


def best_cycle(cels, origin, s, start=0, min_len=8, max_len=30):
    """(i, j): the steady-state cycle cels[i:j] whose ends match best (for takes that start from a still pose)."""
    th = [thumb(c, origin, s) for c in cels]
    best, bi, bj = 1e9, start, len(cels)
    for i in range(start, len(cels) - min_len):
        for j in range(i + min_len, min(len(cels), i + max_len + 1)):
            d = float(np.abs(th[j] - th[i]).mean())
            if d < best:
                best, bi, bj = d, i, j
    return bi, bj, best


def contact(cels, origin, s, path, cols=20, cell=96):
    """Every source frame, numbered, placed at one scale about the reference feet: the sheet to write EDLs from."""
    from PIL import ImageDraw
    pl = place(cels, s, origin)
    h, w = pl.frames[0].shape[:2]
    k = cell / max(h, w)
    cw, ch = int(w * k), int(h * k)
    rows = (len(cels) + cols - 1) // cols
    sheet = Image.new("RGB", (cols * cw, rows * (ch + 12)), (40, 42, 48))
    d = ImageDraw.Draw(sheet)
    for i, f in enumerate(pl.frames):
        r, c = divmod(i, cols)
        im = Image.fromarray(f).resize((cw, ch), Image.LANCZOS)
        sheet.paste(im, (c * cw, r * (ch + 12) + 12), im)
        d.text((c * cw + 2, r * (ch + 12)), str(i), fill=(255, 210, 120))
    sheet.save(path)


@dataclass
class Placed:
    frames: list                 # [RGBA uint8] all the same size
    holds: list
    events: list
    pivot: tuple                 # (x, y) of the feet in the frame
    root: list = field(default_factory=list)   # per-frame root x motion in output px (for "root" anchor)
    src: list = field(default_factory=list)


def place(cels, s, origin, anchor="fixed", pad=6, detrend=False, offsets=None):
    """Scale every cel by s and place it relative to origin (source feet of the reference frame).

    anchor: "fixed"  keep the video's own motion (camera assumed locked)
            "feet"   pin the feet x of every frame to the origin (in-place loops that drift)
            "root"   remove a straight-line travel from the feet x and report it as root motion
    detrend: remove a linear drift of the feet so the last frame lands where the first began (loops).
    """
    fx = np.array([c.feet[0] for c in cels], float)
    fy = np.array([c.feet[1] for c in cels], float)
    t = np.arange(len(cels), dtype=float)
    dx = np.zeros(len(cels))
    dy = np.zeros(len(cels))
    root = []
    if anchor == "feet":
        dx = origin[0] - fx
    elif anchor == "torso":
        # pin the upper body (circularly smoothed so the bob survives, not the jitter) and put the lowest
        # foot on the ground line: a walk in place with zero net drift; the game's glide supplies the travel
        tx = np.array([torso_x(c) for c in cels])
        k = np.array([0.25, 0.5, 0.25])
        tx = np.convolve(np.concatenate([tx[-1:], tx, tx[:1]]), k, "valid") if len(tx) > 2 else tx
        dx = origin[0] - tx
        dy = origin[1] - fy
    elif anchor == "root" and len(cels) > 1:
        k, b = np.polyfit(t, fx, 1)
        dx = -(k * t + b - origin[0])
        root = list((k * t + b - origin[0]) * s)
    if detrend and len(cels) > 2 and anchor != "torso":
        if anchor != "feet" and anchor != "root":
            dx = dx - (fx[-1] - fx[0]) * t / (len(t) - 1)
        dy = dy - (fy[-1] - fy[0]) * t / (len(t) - 1)

    if offsets is not None:          # caller-computed source-pixel offsets (e.g. walk drift removal)
        dx, dy = np.asarray(offsets[0], float), np.asarray(offsets[1], float)
    ims, boxes = [], []
    for c, ddx, ddy in zip(cels, dx, dy):
        w, h = c.rgba.shape[1], c.rgba.shape[0]
        W, H = max(1, int(round(w * s))), max(1, int(round(h * s)))
        im = Image.fromarray(c.rgba).convert("RGBa").resize((W, H), Image.LANCZOS if s < 1 else Image.BICUBIC)
        im = im.convert("RGBA")
        X = (c.x0 + ddx - origin[0]) * s
        Y = (c.y0 + ddy - origin[1]) * s
        ims.append(im)
        boxes.append((int(round(X)), int(round(Y))))
    x0 = min(b[0] for b in boxes) - pad
    y0 = min(b[1] for b in boxes) - pad
    x1 = max(b[0] + im.width for b, im in zip(boxes, ims)) + pad
    y1 = max(max(b[1] + im.height for b, im in zip(boxes, ims)), 0) + pad
    frames = []
    for im, (X, Y) in zip(ims, boxes):
        canvas = Image.new("RGBA", (x1 - x0, y1 - y0), (0, 0, 0, 0))
        canvas.alpha_composite(im, (X - x0, Y - y0))
        frames.append(np.asarray(canvas))
    return Placed(frames, [c.hold for c in cels], [c.event for c in cels], (-x0, -y0), root,
                  [c.src for c in cels])

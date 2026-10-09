"""Quality gate for cut clips: catch what makes a sprite animation read wrong before anyone looks at it.

qc_clip(cels, kind, facing, ref_idle) -> dict with "ok", "flags" (human-readable) and "metrics".
Checks, all in source-frame pixels and normalised by the reference idle height:
  facing   a frame looks more like another facing's idle than its own (the model turned the body)
  arc      an attack's weapon-height trace has more than one peak (a second swing / re-lift in the recovery)
  pop      the silhouette changes too much between neighbouring keys (a morph or a jump)
  dupes    neighbouring keys are near-identical (a frozen hold nobody asked for)
  sway     walk: hip x moves against head x (reads as a pelvis thrust / "humping")
  bob      walk/idle: the feet leave the ground line
  seam     loops: the last->first step is much bigger than a normal step
onion(cels) draws every key over the first with a tip trail, for the review page.
Pass the PLACED keys (after anchoring) so bob/sway/seam measure what the game will show; raw source cels
include the video's own drift.
"""
from __future__ import annotations

import numpy as np
from PIL import Image, ImageDraw

# thresholds, as fractions of the reference idle height H unless noted
SWAY_MAX = 0.02        # walk hip-vs-head x range
BOB_MAX = 0.02         # feet off the ground line
ARC_PROM = 0.12        # a weapon-height peak must stand this far above its neighbours to count
POP_IOU = 0.45         # neighbouring-key silhouette IoU below this is a pop
DUPE_DIFF = 0.004      # mean |thumb diff| below this is a duplicate key
SEAM_RATIO = 2.5       # loop seam step vs median step
FACING_MARGIN = 0.15   # another facing must be closer by this much (relative) to flag a turn
RING = ["s", "se", "e", "ne", "n"]   # neighbouring facings look alike; only a jump of >= 2 steps is a turn


def _alpha(cel):
    return cel.rgba[..., 3] >= 128


def _ref_height(ref):
    return float(max(1, ref.box[3] - ref.box[1]))


def _canvas(cels):
    """Shared source-frame window covering every cel."""
    x0 = min(c.x0 for c in cels); y0 = min(c.y0 for c in cels)
    x1 = max(c.x0 + c.rgba.shape[1] for c in cels); y1 = max(c.y0 + c.rgba.shape[0] for c in cels)
    return x0, y0, x1, y1


def _masks(cels, step=2):
    """Alpha masks of all cels on one shared canvas, downsampled by `step` for speed."""
    x0, y0, x1, y1 = _canvas(cels)
    W, H = (x1 - x0) // step + 1, (y1 - y0) // step + 1
    out = []
    for c in cels:
        m = np.zeros((H, W), bool)
        a = _alpha(c)[::step, ::step]
        oy, ox = (c.y0 - y0) // step, (c.x0 - x0) // step
        m[oy:oy + a.shape[0], ox:ox + a.shape[1]] = a[:H - oy, :W - ox]
        out.append(m)
    return out


def _iou(a, b):
    u = np.logical_or(a, b).sum()
    return float(np.logical_and(a, b).sum() / u) if u else 1.0


def _thumb(cel, size=32):
    """Grey+alpha signature of the cel in its own bbox (position-free)."""
    bx0, by0, bx1, by1 = cel.box
    crop = cel.rgba[by0 - cel.y0:by1 - cel.y0, bx0 - cel.x0:bx1 - cel.x0]
    if crop.size == 0:
        return np.zeros(size * size * 2, np.float32)
    im = Image.fromarray(crop).resize((size, size), Image.BOX)
    t = np.asarray(im, np.float32) / 255.0
    return np.concatenate([(t[..., :3].mean(-1) * t[..., 3]).ravel(), t[..., 3].ravel()])


def _signature(cel):
    """Facing signature: silhouette/grey layout plus an alpha-weighted hue histogram."""
    rgba = cel.rgba.astype(np.float32) / 255.0
    a = rgba[..., 3] >= 0.5
    hsv = np.asarray(Image.fromarray(cel.rgba[..., :3]).convert("HSV"), np.float32) / 255.0
    h, s = hsv[..., 0][a], hsv[..., 1][a]
    hist = np.histogram(h, bins=18, range=(0, 1), weights=s)[0]
    hist = hist / (hist.sum() + 1e-6)
    return np.concatenate([_thumb(cel, 24) * 0.5, hist * 4.0])


def _tip_height(cel):
    """Height of the highest solid pixel above the feet (the raised weapon for a chop/slam)."""
    return float(cel.feet[1] - cel.box[1])


def _reach(cel, pelvis):
    """Distance of the farthest solid pixel from the pelvis point (the extended weapon)."""
    ys, xs = np.nonzero(_alpha(cel))
    if len(xs) == 0:
        return 0.0
    dx = xs + cel.x0 - pelvis[0]; dy = ys + cel.y0 - pelvis[1]
    return float(np.sqrt(dx * dx + dy * dy).max())


def _band_x(cel, lo, hi):
    """Median x of the solid pixels in a vertical band [lo, hi] of the cel's bbox (0 = top)."""
    a = _alpha(cel)
    y0, y1 = cel.box[1] - cel.y0, cel.box[3] - cel.y0
    r0, r1 = int(y0 + (y1 - y0) * lo), max(int(y0 + (y1 - y0) * hi), int(y0 + (y1 - y0) * lo) + 1)
    ys, xs = np.nonzero(a[r0:r1])
    return cel.x0 + float(np.median(xs)) if len(xs) else cel.feet[0]


def _peaks(v, prom):
    """Indices of local maxima in v that rise at least `prom` above the lowest point on both sides."""
    v = np.asarray(v, float)
    out = []
    for i in range(len(v)):
        if (i == 0 or v[i] >= v[i - 1]) and (i == len(v) - 1 or v[i] > v[i + 1]):
            left = v[:i + 1].min(); right = v[i:].min()
            if v[i] - max(left, right) >= prom:
                out.append(i)
    return out


def qc_clip(cels, kind, facing, ref_idle, loop=None):
    """Score one cut clip.

    cels     the chosen keys (reel.cut.Cel), in play order
    kind     "idle" | "walk" | "attack" | other (only the generic checks run)
    facing   this clip's facing key ("s", "se", ...)
    ref_idle a Cel of this facing's idle, or {facing: Cel} for all facings (enables the turn check)
    loop     treat as a loop (seam check); defaults to kind in (idle, walk)
    """
    refs = ref_idle if isinstance(ref_idle, dict) else {facing: ref_idle}
    ref = refs.get(facing) or next(iter(refs.values()))
    H = _ref_height(ref)
    loop = kind in ("idle", "walk") if loop is None else loop
    flags, m = [], {"n": len(cels), "ref_h": H}
    if len(cels) < 2:
        return {"ok": True, "flags": [], "metrics": m}

    # pop: silhouette IoU between neighbours (attacks may legitimately have one fast strike step)
    masks = _masks(cels)
    ious = [_iou(masks[i], masks[i + 1]) for i in range(len(masks) - 1)]
    m["iou_min"] = round(min(ious), 3)
    pops = [i for i, v in enumerate(ious) if v < POP_IOU]
    allowed = 1 if kind == "attack" else 0
    if len(pops) > allowed:
        flags.append(f"pop: silhouette jumps between keys {', '.join(f'{i}->{i + 1}' for i in pops)} (IoU < {POP_IOU})")

    # dupes: near-identical neighbours (one contact hold is fine on an attack)
    th = [_thumb(c) for c in cels]
    diffs = [float(np.abs(th[i] - th[i + 1]).mean()) for i in range(len(th) - 1)]
    dupes = [i for i, d in enumerate(diffs) if d < DUPE_DIFF]
    m["step_median"] = round(float(np.median(diffs)), 4)
    if kind != "idle" and len(dupes) > (1 if kind == "attack" else 0):   # idle breathing is legitimately subtle
        flags.append(f"dupes: keys {', '.join(f'{i}={i + 1}' for i in dupes)} are near-identical (frozen)")

    # facing drift: a key much closer to a facing >= 2 steps away than to its own. Only for idle/walk, whose
    # pose stays near the idle; attack poses change the silhouette too much for this signature (review the onion).
    if len(refs) > 1 and kind in ("idle", "walk") and facing in RING:
        sigs = {f: _signature(c) for f, c in refs.items()}
        turned = []
        for i, c in enumerate(cels):
            s = _signature(c)
            d = {f: float(np.abs(s - v).mean()) for f, v in sigs.items()}
            best = min(d, key=d.get)
            far = best in RING and abs(RING.index(best) - RING.index(facing)) >= 2
            if far and d[best] < d[facing] * (1 - FACING_MARGIN):
                turned.append(f"{i}->{best}")
        if turned:
            flags.append(f"facing: keys look like another facing ({', '.join(turned)})")

    if kind == "attack":
        tip = np.array([_tip_height(c) for c in cels]) / H
        pelvis = (ref.feet[0], ref.feet[1] - 0.45 * H)
        reach = np.array([_reach(c, pelvis) for c in cels]) / H
        m["tip"] = np.round(tip, 3).tolist()
        m["reach"] = np.round(reach, 3).tolist()
        # chops/slams lift the weapon (height), thrusts extend it (reach): judge the arc on whichever moves more
        use_reach = np.ptp(reach) > np.ptp(tip)
        sig = reach if use_reach else tip
        pk = _peaks(sig, ARC_PROM)
        m["tip_peaks"] = pk
        m["arc_signal"] = "reach" if use_reach else "height"
        what = "extends" if use_reach else "rises"
        if len(pk) > 1:
            flags.append(f"arc: the weapon {what} {len(pk)} times (keys {pk}); a second strike or re-lift")
        if len(pk) == 0:
            flags.append("arc: the weapon never clearly peaks; the attack has no readable strike")

    if kind == "walk":
        head = np.array([_band_x(c, 0.0, 0.35) for c in cels])
        hip = np.array([_band_x(c, 0.6, 0.8) for c in cels])
        sway = float(np.ptp(hip - head)) / H
        m["sway"] = round(sway, 4)
        if sway > SWAY_MAX:
            flags.append(f"sway: hips move {sway * 100:.1f}% of height against the head (reads as a pelvis thrust; max {SWAY_MAX * 100:.0f}%)")

    if kind in ("walk", "idle"):
        feet = np.array([c.feet[1] for c in cels])
        bob = float(np.ptp(feet)) / H
        m["feet_range"] = round(bob, 4)
        if bob > BOB_MAX:
            flags.append(f"bob: feet leave the ground line by {bob * 100:.1f}% of height")

    if loop:
        # pose seam (bbox-relative thumbs) and position seam (torso x / feet y): a loop can match in pose but
        # still snap sideways, which the position-free thumbs cannot see
        seam = float(np.abs(th[-1] - th[0]).mean())
        med = float(np.median(diffs)) or 1e-6
        m["seam_ratio"] = round(seam / med, 2)
        if seam > SEAM_RATIO * med:
            flags.append(f"seam: loop jump is {seam / med:.1f}x a normal step")
        pos = np.array([(_band_x(c, 0.3, 0.62), c.feet[1]) for c in cels])
        steps = np.hypot(*np.diff(pos, axis=0).T)
        pseam = float(np.hypot(*(pos[0] - pos[-1])))
        m["seam_px"] = round(pseam, 2)
        if pseam > max(0.01 * H, SEAM_RATIO * float(np.median(steps))):
            flags.append(f"seam: loop snaps {pseam:.1f}px sideways/vertically ({pseam / H * 100:.1f}% of height)")

    return {"ok": not flags, "flags": flags, "metrics": m}


def onion(cels, size=256, trail=True):
    """All keys over the first, tinted from blue (early) to red (late), with the weapon-tip trail."""
    x0, y0, x1, y1 = _canvas(cels)
    W, H = x1 - x0, y1 - y0
    im = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    pts = []
    n = len(cels)
    for i, c in enumerate(cels):
        t = i / max(1, n - 1)
        rgba = c.rgba.copy()
        tint = np.array([255 * t, 80, 255 * (1 - t)], np.float32)
        rgba[..., :3] = (rgba[..., :3] * 0.55 + tint * 0.45).astype(np.uint8)
        rgba[..., 3] = (rgba[..., 3] * (0.35 if i else 0.9)).astype(np.uint8)
        im.alpha_composite(Image.fromarray(rgba), (c.x0 - x0, c.y0 - y0))
        ys, xs = np.nonzero(_alpha(c))
        if len(ys):
            j = int(np.argmin(ys))
            pts.append((int(xs[j] + c.x0 - x0), int(ys[j] + c.y0 - y0)))
    if trail and len(pts) > 1:
        d = ImageDraw.Draw(im)
        d.line(pts, fill=(255, 230, 60, 255), width=max(2, W // 120))
        for k, p in enumerate(pts):
            r = max(3, W // 90)
            d.ellipse((p[0] - r, p[1] - r, p[0] + r, p[1] + r), fill=(255, 230, 60, 255))
            d.text((p[0] + r + 1, p[1] - r), str(k), fill=(255, 255, 255, 255))
    im.thumbnail((size, size))
    return im

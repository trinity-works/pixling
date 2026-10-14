"""Strike anatomy: measure where the weapon, the feet and the body are in every frame of a sprite sheet, so a game
can make a melee hit land where the art paints it, on the tick it resolves.

The measuring half of `pixling strike` (the CLI: strike/__main__.py; the guide: strike/README.md). Works on any
sheet: columns are frames, rows are facings, cells of one size (w x h). Points are in cell px from the pivot (the
feet point), y down, so they hold at every draw size. Only the alpha is read; the artist labels nothing.
- Weapon: the longest THIN part of the silhouette. An opening with radius THIN x body height removes thin parts;
  the longest removed part over BLADE_MIN body heights is the weapon (a blade, a staff, a bow arc; never a limb).
  Its end nearer the body core is the grip, the far end the tip. The hitbox is the segment grip -> tip.
- With a parts map (one flat colour per part: weapon, arm, legs, body; `pixling build --maps parts` writes one from
  the rig), the weapon, the legs and the body come from the map instead: exact, also for small pixel art.
- Feet: the two lowest leg clusters of the weaponless body. With `rtmlib` + `onnxruntime` installed, the RTMPose
  ankles replace them (the silhouette guess is noisy).
- Hurtbox: the weaponless body of a sheet's first frame, 5-85 % of its height (legs count: a thrust in a 3/4 view
  crosses a defender at the hips), 10th-90th percentile in x, median over facings.
- Stride (--walk): the widest feet spread along each facing. Advance the walk frame by distance walked, one cycle per
  two strides, and the feet keep pace at any speed.
"""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw
from scipy import ndimage

THIN = 0.04          # opening radius / body height: blades and shafts are thinner, limbs are not
BLADE_MIN = 0.16     # a weapon is at least this long (body heights)
FOOT_BAND = 0.22     # the legs: the lowest band of the weaponless silhouette (body heights)
DIRS = {"s": (0, 1), "se": (1, 1), "e": (1, 0), "ne": (1, -1), "n": (0, -1), "nw": (-1, -1), "w": (-1, 0), "sw": (-1, 1)}
_MODEL = []          # the pose model, loaded once ([None]: not installed)
# pixling's parts colours (`pixling build --maps parts`; the manifest's "parts" key repeats them)
PARTS = {"weapon": (255, 64, 64), "arm": (64, 200, 64), "legL": (64, 96, 255), "legR": (64, 200, 255), "body": (200, 200, 200)}


def _disk(r):
    y, x = np.mgrid[-r:r + 1, -r:r + 1]
    return x * x + y * y <= r * r


def parts(alpha, body_h, thin=THIN):
    """-> (body mask without the weapon, weapon as (axis, projections, points) or None)."""
    m = alpha > 64
    r = max(2, int(round(thin * body_h)))
    thick = ndimage.binary_dilation(ndimage.binary_opening(m, _disk(r)), _disk(1)) & m
    lab, n = ndimage.label(m & ~thick)
    best, best_len = None, BLADE_MIN * body_h
    sizes = np.bincount(lab.ravel(), minlength=n + 1)
    for i, sl in enumerate(ndimage.find_objects(lab), 1):
        if sizes[i] < 12 or max(sl[0].stop - sl[0].start, sl[1].stop - sl[1].start) < best_len * 0.7:
            continue
        ys, xs = np.nonzero(lab[sl] == i)
        pts = np.stack([xs + sl[1].start, ys + sl[0].start], 1).astype(float)
        c = pts - pts.mean(0)
        axis = np.linalg.svd(c, full_matrices=False)[2][0]
        proj = c @ axis
        length, width = float(np.ptp(proj)), float(np.ptp(c @ np.array([-axis[1], axis[0]])))
        if length > best_len and length > 2.5 * max(1.0, width):
            best, best_len = (axis, proj, pts), length
    return (thick if best is not None else m), best


def _crop(alpha, pivot, pad=8):
    ys, xs = np.nonzero(alpha > 64)
    if len(ys) == 0:
        return alpha, pivot
    y0, x0 = max(0, ys.min() - pad), max(0, xs.min() - pad)
    return alpha[y0:ys.max() + pad + 1, x0:xs.max() + pad + 1], (pivot[0] - x0, pivot[1] - y0)


def _rel(p, pivot):
    return [round(float(p[0] - pivot[0]), 1), round(float(p[1] - pivot[1]), 1)]


def keypoints(alpha, pivot, body_h, thin=THIN):
    """One frame -> {"tip", "grip", "feet"} in cell px from the pivot (None where nothing was found)."""
    alpha, pivot = _crop(alpha, pivot)
    body, w = parts(alpha, body_h, thin)
    out = {"tip": None, "grip": None, "feet": None}
    ys, xs = np.nonzero(body)
    if len(ys) == 0:
        return out
    if w is not None:
        _, proj, pts = w
        core = np.array([np.median(xs), np.median(ys)])
        a, b = pts[np.argmin(proj)], pts[np.argmax(proj)]
        grip, tip = (a, b) if np.hypot(*(a - core)) < np.hypot(*(b - core)) else (b, a)
        out["grip"], out["tip"] = _rel(grip, pivot), _rel(tip, pivot)
    # the legs: the lower band split in two along x (2-means); a foot is a leg's lowest point. In a 3/4 view the far
    # foot sits higher on screen, so a thin bottom band would find only the near one.
    sel = ys >= ys.max() - FOOT_BAND * body_h
    bx, by = xs[sel].astype(float), ys[sel]
    c = np.percentile(bx, [25, 75])
    g = np.ones(len(bx), bool)
    for _ in range(8):
        g = np.abs(bx - c[0]) <= np.abs(bx - c[1])
        if g.all() or not g.any():
            break
        c = np.array([bx[g].mean(), bx[~g].mean()])
    groups = [g, ~g] if g.any() and not g.all() and abs(c[1] - c[0]) > 0.05 * body_h else [np.ones_like(g)] * 2
    out["feet"] = [_rel((np.median(bx[k][by[k] >= by[k].max() - 0.02 * body_h]), by[k].max()), pivot) for k in groups]
    return out


def _match(rgba, rgb, tol=10):
    return (rgba[..., 3] > 0) & (np.abs(rgba[..., :3].astype(int) - rgb).max(-1) <= tol)


def part_masks(sheet_cell, parts_cell, pivot, legend):
    """(weapon, body without the weapon, [leg masks], smear) from a parts map (one flat colour per part, `legend`
    name -> rgb, as `pixling build --maps parts` writes). A frame whose weapon is drawn as an effect (a smear arc) has
    no weapon pixels in the map: then the effect pixels above the feet are the swing, and smear is True."""
    on = parts_cell[..., 3] > 0
    weapon = _match(parts_cell, legend["weapon"]) if "weapon" in legend else np.zeros(on.shape, bool)
    smear = weapon.sum() < 3
    if smear:
        ys = np.arange(on.shape[0])[:, None]
        weapon = (sheet_cell[..., 3] > 64) & ~on & (ys < pivot[1] - 1)
    legs = [_match(parts_cell, legend[k]) for k in sorted(legend) if k.startswith("leg")]
    return weapon, on & ~weapon, [m for m in legs if m.any()], smear


def keypoints_from_parts(sheet_cell, parts_cell, pivot, legend, facing):
    """One frame from its parts map -> {"tip", "grip", "feet"}. A drawn weapon's tip is its pixel farthest from the
    body core; a smear's tip is its pixel that reaches farthest along the facing (an arc has two far ends, and the
    blow lands on the front one). The grip is the weapon pixel nearest the core; a foot is a leg's lowest pixels."""
    weapon, body, legs, smear = part_masks(sheet_cell, parts_cell, pivot, legend)
    out = {"tip": None, "grip": None, "feet": None}
    by, bx = np.nonzero(body)
    if len(by) and weapon.sum() >= 3:
        core = np.array([np.median(bx), np.median(by)])
        wy, wx = np.nonzero(weapon)
        d = np.hypot(wx - core[0], wy - core[1])
        far = (wx - core[0]) * DIRS[facing][0] + (wy - core[1]) * DIRS[facing][1] if smear else d
        out["tip"] = _rel((wx[far.argmax()], wy[far.argmax()]), pivot)
        out["grip"] = _rel((wx[d.argmin()], wy[d.argmin()]), pivot)
    feet = []
    for m in legs:
        ys, xs = np.nonzero(m)
        low = ys >= ys.max()
        feet.append(_rel((float(np.median(xs[low])), ys.max() + 1), pivot))
    if feet:
        out["feet"] = (feet * 2)[:2] if len(feet) == 1 else feet[:2]
    return out


def model_ankles(rgba, pivot, min_score=0.3):
    """The two ankles from RTMPose (cell px from the pivot), or None without rtmlib or a confident person."""
    if not _MODEL:
        try:
            from rtmlib import Body
            _MODEL.append(Body(mode="balanced", backend="onnxruntime", device="cpu"))
        except Exception:
            _MODEL.append(None)
    if _MODEL[0] is None:
        return None
    a = rgba[..., 3:4].astype(np.float32) / 255.0
    rgb = (rgba[..., :3] * a + 128 * (1 - a)).astype(np.uint8)        # on mid grey, as a photo
    kps, sc = _MODEL[0](np.ascontiguousarray(rgb[..., ::-1]))
    if not len(kps):
        return None
    i = int(np.argmax([s.mean() for s in sc]))
    if min(sc[i][15], sc[i][16]) < min_score:
        return None
    return [_rel(kps[i][15], pivot), _rel(kps[i][16], pivot)]


def hurtbox(alpha, pivot, body_h, thin=THIN, body=None):
    """[x, y, w, h] of a standing pose's body without the weapon, below the head (cell px from the pivot). `body`
    is that mask when a parts map gives it; else the thin-part rule removes the weapon."""
    if body is None:
        alpha, pivot = _crop(alpha, pivot)
        body, _ = parts(alpha, body_h, thin)
    ys, xs = np.nonzero(body)
    top, bot = ys.min(), ys.max()
    y0, y1 = bot - 0.85 * (bot - top), bot - 0.05 * (bot - top)
    x0, x1 = np.percentile(xs[(ys > y0) & (ys < y1)], [10, 90])
    return [round(float(v), 1) for v in (x0 - pivot[0], y0 - pivot[1], x1 - x0, y1 - y0)]


def _unit(facing):
    d = np.array(DIRS[facing], float)
    return d / np.linalg.norm(d)


def pose(sheet_path, cell, pivot, rows, frames=None, hit=None, walk=False, body=None, use_model=True, out=None, thin=THIN,
         parts=None, legend=None, log=print):
    """Measure every frame of a sheet; write <out>.pose.json and <out>.pose.png (default: beside the sheet).
    `cell` is (w, h) in px, `pivot` the feet point inside a cell, `rows` the facing of each sheet row. `parts` is an
    optional parts map on the same grid (colours per `legend`, default pixling's): then the weapon, the legs and the
    body come from it instead of from the silhouette. Returns the pose dict; its "json" key is the path written."""
    sheet_path = Path(sheet_path)
    im = np.asarray(Image.open(sheet_path).convert("RGBA"))
    pm = np.asarray(Image.open(parts).convert("RGBA")) if parts else None
    if pm is not None and pm.shape != im.shape:
        raise SystemExit(f"the parts map is {pm.shape[1]}x{pm.shape[0]} px, the sheet {im.shape[1]}x{im.shape[0]}")
    legend = {k: tuple(v) for k, v in (legend or PARTS).items()}
    cw, ch = cell
    rows = [r.lower() for r in rows]
    bad = [r for r in rows if r not in DIRS]
    if bad:
        raise SystemExit(f"unknown facing {', '.join(bad)}; use {', '.join(DIRS)}")
    frames = frames or im.shape[1] // cw
    if frames < 1 or im.shape[1] < frames * cw or im.shape[0] < len(rows) * ch:
        raise SystemExit(f"{sheet_path.name} is {im.shape[1]}x{im.shape[0]} px: too small for {frames} frames x "
                         f"{len(rows)} rows of {cw}x{ch} cells")
    if hit is not None and not 0 <= hit < frames:
        raise SystemExit(f"--hit {hit} is outside the {frames} frames (0-based)")
    grid = lambda a: {f: [a[r * ch:(r + 1) * ch, i * cw:(i + 1) * cw] for i in range(frames)] for r, f in enumerate(rows)}
    cells, pcells = grid(im), (grid(pm) if pm is not None else None)
    firsts = [cells[f][0][..., 3] for f in rows if (cells[f][0][..., 3] > 64).any()]
    if not firsts:
        raise SystemExit(f"{sheet_path.name}: the first frame of every row is empty (check --cell and --rows)")
    if body is None:                                          # the first frame's silhouette height
        ys = np.nonzero(firsts[0] > 64)[0]
        body = float(ys.max() - ys.min() + 1)
    res = {"schema": "pixling.strike-pose/1", "sheet": sheet_path.name, "cell": [cw, ch], "pivot": list(pivot),
           "rows": rows, "frames": frames, "body_px": body, "hit_frame": hit, "parts": bool(parts), "pose": {}}
    model_n = 0
    for f in rows:
        kps = []
        for i, c in enumerate(cells[f]):
            k = keypoints(c[..., 3], pivot, body, thin)
            if pcells is not None:
                kp = keypoints_from_parts(c, pcells[f][i], pivot, legend, f)
                k = {"tip": kp["tip"], "grip": kp["grip"], "feet": kp["feet"] or k["feet"]}
            ankles = model_ankles(c, pivot) if use_model and pcells is None else None
            if ankles:
                k["feet"], model_n = ankles, model_n + 1
            kps.append(k)
        res["pose"][f] = kps
    if pcells is not None:
        boxes = [hurtbox(None, pivot, body, body=part_masks(cells[f][0], pcells[f][0], pivot, legend)[1]) for f in rows
                 if (pcells[f][0][..., 3] > 0).any()]
    else:
        boxes = [hurtbox(a, pivot, body, thin) for a in firsts]
    res["hurtbox"] = dict(zip("xywh", np.median(boxes, 0).round(1).tolist()))
    if walk:
        res["stride_px"] = {f: round(max([abs((np.array(k["feet"][0]) - k["feet"][1]) @ _unit(f)) for k in res["pose"][f]
                                           if k["feet"]] or [0.0]), 1) for f in rows}
    if hit is not None:
        log("  tip at the contact frame: " + ", ".join(f"{f} {res['pose'][f][hit]['tip']}" for f in rows))
    log(f"  pose model ankles on {model_n} of {frames * len(rows)} frames; hurtbox {res['hurtbox']}")
    base = Path(out) if out else sheet_path.with_suffix("")
    js = base.with_name(base.name + ".pose.json")
    js.write_text(json.dumps(res, indent=1))
    _review(im, res, base.with_name(base.name + ".pose.png"))
    res["json"] = str(js)
    return res


def _review(im, p, path):
    """Every frame at a readable size (cells about 256 px tall; pixel art scales by whole steps, nearest neighbour)."""
    (cw, ch), (px, py) = p["cell"], p["pivot"]
    k = 256 / ch if ch > 256 else float(max(1, round(256 / ch)))
    w, h = int(cw * k), int(ch * k)
    img = Image.new("RGBA", (w * p["frames"], h * len(p["rows"])), (92, 104, 84, 255))
    d = ImageDraw.Draw(img)
    for r, f in enumerate(p["rows"]):
        for i in range(p["frames"]):
            t = Image.fromarray(im[r * ch:(r + 1) * ch, i * cw:(i + 1) * cw])
            img.alpha_composite(t.resize((w, h), Image.LANCZOS if k < 1 else Image.NEAREST), (i * w, r * h))
            P = lambda v: (i * w + (px + v[0]) * k, r * h + (py + v[1]) * k)
            kp = p["pose"][f][i]
            for ft in kp["feet"] or []:
                x, y = P(ft)
                d.ellipse((x - 4, y - 4, x + 4, y + 4), outline=(80, 255, 120), width=2)
            if kp["tip"] and kp["grip"]:
                d.line([P(kp["grip"]), P(kp["tip"])], fill=(255, 230, 60), width=2)
                x, y = P(kp["tip"])
                d.ellipse((x - 5, y - 5, x + 5, y + 5), fill=(255, 60, 60))
    img.save(path)


def reach_band(attack, idle, facing, scale, ppm, yscale, step=0.05, far=20.0):
    """(nearest, farthest) ground metres along `facing` at which the contact frame's blade crosses a same-size
    defender's hurtbox, or None. Ground -> screen: (x, y) m -> (x * ppm, y * ppm * yscale) px; `scale` is screen px per
    cell px. This is the game test's own geometry: put the hero's stop distance inside this band."""
    k = attack["pose"][facing][attack["hit_frame"]]
    if not k["tip"]:
        return None
    tip = np.array(k["tip"]) * scale
    grip = np.array(k["grip"] or k["tip"]) * scale
    h = idle["hurtbox"]
    d = _unit(facing)
    hits = []
    for i in range(int(far / step)):
        m = step * (i + 1)
        at = np.array([d[0] * m * ppm, d[1] * m * ppm * yscale])
        x0, y0 = at[0] + h["x"] * scale, at[1] + h["y"] * scale
        x1, y1 = x0 + h["w"] * scale, y0 + h["h"] * scale
        if any(x0 <= q[0] <= x1 and y0 <= q[1] <= y1 for q in (grip + (tip - grip) * j / 20 for j in range(21))):
            hits.append(m)
    return (round(hits[0], 2), round(hits[-1], 2)) if hits else None


def reach(attack, idle, scale, ppm, yscale, stop=None):
    """{facing: {"band": [near, far] m or None, "fits": bool}} plus "ok": every facing has a band holding `stop`
    (or just a band, without `stop`). `attack` and `idle` are pose dicts (or paths to .pose.json files)."""
    attack, idle = (json.loads(Path(x).read_text()) if not isinstance(x, dict) else x for x in (attack, idle))
    if attack.get("hit_frame") is None:
        raise SystemExit("the attack has no hit_frame (measure it with --hit N)")
    res = {"facings": {}, "stop_m": stop}
    for f in attack["rows"]:
        band = reach_band(attack, idle, f, scale, ppm, yscale)
        res["facings"][f] = {"band": list(band) if band else None,
                             "fits": band is not None and (stop is None or band[0] <= stop <= band[1])}
    res["ok"] = all(v["fits"] for v in res["facings"].values())
    return res

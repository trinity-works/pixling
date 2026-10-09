"""Export a reel character as 8-direction sprite sheets plus an actor JSON (with timing
fields; "rows": 4 gives a FR/FL/BR/BL layout).

Every state lands on one game clock, whatever the video's speed: the cut resamples the chosen source range
to a fixed frame count and frameDuration per state, and the attack's contact key is placed on attackHitFrame.

Sheet: cols = frames, rows = S, SE, E, NE, N, NW, W, SW (default, "rows": 8) or FR, FL, BR, BL ("rows": 4);
each anim records its row order in "dirs". The west
side mirrors the east takes and missing facings borrow the nearest one. Die is one row. One scale per
character, one palette, one outline. `<file>-shadow.png` twins share the grid. Writes the actor JSON (timing
contract filled in; shadow/bar/hit offsets are defaults to tune in game), qc.json and attack onion strips.
See reel/README.md for the char.json format.
"""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np
from PIL import Image

from . import cut, finish, keys as K, qc as qc_mod
from .take import OUT, key_cfg, key_take
from .io import save_gif

STATES = {  # frames, frameDuration, loop — the shared game clock (melee heroes)
    "idle": (16, 0.2, True), "walk": (8, 0.1, True), "attack": (8, 0.1, False),
    "damage": (4, 0.1, False), "die": (18, 0.1, False), "celebrate": (12, 0.1, True),
}
HIT_FRAME = 4           # 1-indexed
DIRS = ["s", "se", "e", "ne", "n", "nw", "w", "sw"]               # 8-row sheet order
LAYOUTS = {4: ["se", "sw", "ne", "nw"], 8: DIRS}                # 4-row = FR, FL, BR, BL
ALIAS = {"fr": "se", "fl": "sw", "br": "ne", "bl": "nw"}
MIRROR = {"sw": "se", "w": "e", "nw": "ne", "se": "sw", "e": "w", "ne": "nw"}


def fill_dirs(rows):
    """Mirror the missing left/right facings, then borrow the nearest facing by angle for anything still missing."""
    for d in DIRS:
        if d not in rows and MIRROR.get(d) in rows:
            rows[d] = [t.transpose(Image.FLIP_LEFT_RIGHT) for t in rows[MIRROR[d]]]
    have = [d for d in DIRS if d in rows]
    for i, d in enumerate(DIRS):
        if d not in rows:
            rows[d] = rows[min(have, key=lambda h: min((DIRS.index(h) - i) % 8, (i - DIRS.index(h)) % 8))]
    return rows


def pick(n_src, n, rng=None, contact=None, keys=None, loop=False, hit=HIT_FRAME):
    """Source frame indices for n output frames."""
    if keys:
        assert len(keys) == n, f"keys needs exactly {n} frames"
        return list(keys)
    a, b = rng or (0, n_src - 1)
    b = min(b, n_src - 1)
    if contact is not None:
        pre = np.linspace(a, contact, hit)                 # frames 1..hit, contact on `hit`
        post = np.linspace(contact, b, n - hit + 1)[1:]
        return [int(round(v)) for v in np.concatenate([pre, post])]
    if loop:                                               # b is the frame that equals a: leave it out
        return [int(round(v)) for v in np.linspace(a, b, n + 1)[:-1]]
    return [int(round(v)) for v in np.linspace(a, b, n)]


def find_contact(cels, ref, scale, rng, burst=0.25):
    """Contact = the end of the last motion burst before the recovery burst: wind-up, (hold), strike, hold,
    recover. A fast wind-up does not win just because it is fast."""
    a, b = rng
    th = [cut.thumb(cels[i], ref.feet, scale) for i in range(a, b + 1)]
    sp = np.array([0.0] + [float(np.abs(th[i] - th[i - 1]).mean()) for i in range(1, len(th))])
    sp = np.convolve(sp, np.ones(3) / 3, "same")
    hot = sp > burst * sp.max()
    runs, i = [], 0
    while i < len(hot):                      # [start, end) of each burst
        if hot[i]:
            j = i
            while j < len(hot) and hot[j]:
                j += 1
            runs.append((i, j))
            i = j
        else:
            i += 1
    if len(runs) < 2:
        return a + (runs[0][1] if runs else int(np.argmax(sp)))
    # the strike is the last burst before the recovery; merge bursts separated by a gap of <= 2 frames first
    merged = [runs[0]]
    for r in runs[1:]:
        if r[0] - merged[-1][1] <= 2:
            merged[-1] = (merged[-1][0], r[1])
        else:
            merged.append(r)
    return a + (merged[-2][1] if len(merged) >= 2 else merged[0][1])


def cellify(img: Image.Image, feet, cell, fx, fy):
    """Place a scaled RGBA image so its feet land on (fx*cell, fy*cell) of a cell x cell tile."""
    tile = Image.new("RGBA", (cell, cell), (0, 0, 0, 0))
    tile.alpha_composite(img, (int(round(fx * cell - feet[0])), int(round(fy * cell - feet[1]))))
    return tile


def shadow_of(tile: Image.Image, feet_y, squash=0.28):
    """Baked shadow: the silhouette flattened onto the ground about the feet line, solid black."""
    a = tile.getchannel("A")
    h = tile.height
    flat = a.resize((tile.width, max(1, int(h * squash))), Image.BILINEAR)
    out = Image.new("L", tile.size, 0)
    out.paste(flat, (0, int(feet_y - flat.height * 0.6)))
    sh = Image.new("RGBA", tile.size, (0, 0, 0, 0))
    sh.putalpha(out.point(lambda v: 255 if v > 60 else 0))
    return sh


def export(spec_path, log=print):
    spec_path = Path(spec_path)
    spec = json.loads(spec_path.read_text())
    base = spec_path.parent
    g = spec["gambit"]
    name = spec["name"]
    out = OUT / name / "gambit"
    cell, body, fx, fy = g.get("cell", 256), g.get("body", 0.27), g.get("feet_x", 0.5), g.get("feet_y", 0.59)
    cfg = key_cfg(spec)
    fin = spec.get("finish", {})
    cache = OUT / name / "cache"
    pal = None
    pal_path = base / "palette.json"
    if fin.get("palette") and pal_path.exists():
        pal = np.array([[int(h[i:i + 2], 16) for i in (1, 3, 5)] for h in json.loads(pal_path.read_text())], np.uint8)

    scale = None
    if g.get("scale_from"):             # one scale per character from a named take's first frame
        rc, _ = key_take(base / g["scale_from"], cfg, cache, "g_scale_ref", 0)
        scale = body * cell / max(1, cut.height(rc[0]))
    # one BODY size across facings: generated start sheets drift between facings (the lancer's edited E frame
    # came out ~13% big), and every take reproduces its start frame, so normalise each facing's idle frame 0
    # (weapon shafts opened away) to the character's median. Explicit "facing_scale" wins.
    face_k = dict(g.get("facing_scale", {}))
    if g.get("normalize_facings") and not face_k and "idle" in g["clips"]:
        bh = {}
        for d, rel in g["clips"]["idle"]["takes"].items():
            if (base / rel).exists():
                bh[ALIAS.get(d, d)] = cut.body_height(key_take(base / rel, cfg, cache, f"g_idle_{ALIAS.get(d, d)}", 0)[0][0])
        med = float(np.median(list(bh.values())))
        face_k = {d: float(np.clip(med / v, 0.85, 1.18)) for d, v in bh.items()}
    if face_k:
        log("  facing scale: " + ", ".join(f"{d} {k:.3f}" for d, k in face_k.items()))
    if fin.get("palette") and pal is None:
        # one locked palette per character, fitted across the idle of every facing (not per clip)
        sample = []
        for d, rel in g["clips"]["idle"]["takes"].items():
            if not (base / rel).exists():
                continue
            cels, _ = key_take(base / rel, cfg, cache, f"g_idle_{ALIAS.get(d, d)}", 0)
            s0 = scale or body * cell / max(1, cut.height(cels[0]))
            sample += cut.place(cels[::max(1, len(cels) // 5)], s0, cels[0].feet, pad=0).frames
        pal = finish.fit_palette([finish.grade(f, fin.get("grade")) for f in sample], fin["palette"])
        pal_path.write_text(json.dumps(["#%02x%02x%02x" % tuple(int(v) for v in c) for c in pal]))
    anims, previews = {}, {}
    idle_refs, qc_all = {}, {}
    out.mkdir(parents=True, exist_ok=True)
    order = sorted(g["clips"], key=lambda c: 0 if c == "idle" else 1)
    for state in order:
        clip = g["clips"][state]
        n, dur, loop = clip.get("frames", STATES[state][0]), clip.get("frameDuration", STATES[state][1]), \
            clip.get("loop", STATES[state][2])
        rows = {}
        for d, rel in clip["takes"].items():
            d = ALIAS.get(d, d)
            if not all((base / r).exists() for r in (rel if isinstance(rel, list) else [rel])):
                log(f"    {state}/{d}: missing {rel}, skipped")
                continue
            kc = cfg
            if clip.get("key", {}).get(d):   # per-take key override, e.g. drop a detached VFX splash
                kc = key_cfg({"key": {**spec.get("key", {}), **clip["key"][d]}})
            seam = None
            if isinstance(rel, list):        # keyframe-driven splice: [idle->contact, contact->idle]
                parts = [key_take(base / r, kc, cache, f"g_{state}_{d}_{k}", clip.get("max_side", 0))[0]
                         for k, r in enumerate(rel)]
                cels = parts[0] + [c for p in parts[1:] for c in p[1:]]   # drop each seam's duplicate frame
                seam = len(parts[0]) - 1                                   # last frame of clip 1 = the hit
            else:
                cels, _ = key_take(base / rel, kc, cache, f"g_{state}_{d}", clip.get("max_side", 0))
            ref = cels[0]
            if scale is None:               # one scale per character, from the first idle take's reference pose
                scale = body * cell / max(1, cut.height(ref))
            s_take = scale * face_k.get(d, 1.0)
            if isinstance(clip.get("scale"), dict):
                s_take *= clip["scale"].get(d, 1.0)
            origin = (cut.torso_x(ref), ref.feet[1])   # the cell point: torso over the ground line, every state
            rng = clip.get("range")
            if clip.get("cycle"):         # one steady cycle out of a multi-cycle take (walks)
                cy = clip["cycle"]
                seg = cels[:cy.get("to", len(cels))]
                i0, j0, err = cut.best_cycle(seg, ref.feet, scale, cy.get("from", 0), cy.get("min", 8), cy.get("max", 30))
                rng = [i0, j0]
                log(f"    {state}/{d}: cycle {i0}-{j0} ({j0 - i0} src frames, match {err:.4f})")
            contact = clip.get("contact", "seam" if seam is not None else None)
            if isinstance(contact, dict):     # per-facing contact frames (picked by eye from the contact sheet)
                contact = contact.get(d, "auto")
            rng = clip.get("ranges", {}).get(d, rng)
            if isinstance(contact, str) and contact.startswith("seam"):   # "seam" or "seam+N" (N frames into clip 2)
                contact = seam + int(contact[4:] or 0)
            if contact == "auto":
                contact = find_contact(cels, ref, scale, rng or (0, len(cels) - 1))
                log(f"    {state}/{d}: contact {contact}")
            hit = clip.get("hit", HIT_FRAME)
            manual = clip.get("keys_by_dir", {}).get(d, clip.get("keys"))
            offsets = None
            if manual:
                idx = list(manual)
            elif state == "walk" and clip.get("cycle") and clip.get("walk_keys", "phase") == "phase":
                idx = K.walk_keys(cels, rng[0], rng[1], n)
                L = rng[1] - rng[0]
                close = idx[0] + L if idx[0] + L < len(cels) else idx[0]
                offsets = K.drift_offsets(cels, idx, close, origin)
            elif contact is not None and clip.get("attack_keys", "pose") == "pose":
                a0, b0 = rng if rng else (0, len(cels) - 1)
                idx = K.attack_keys(cels, ref, s_take, contact, n, hit, a0, min(b0, len(cels) - 1),
                                    clip.get("rerise", 0.15), log)
            else:
                idx = pick(len(cels), n, rng, contact, None, loop, hit)
            seq = [cels[i] for i in idx]
            anchor = clip.get("anchor", "torso" if state == "idle" else "fixed")
            pl = cut.place(seq, s_take, origin, anchor, pad=0, detrend=loop and offsets is None, offsets=offsets)
            rows[d] = [cellify(Image.fromarray(finish.finish(f, fin, pal)), pl.pivot, cell, fx, fy) for f in pl.frames]
            # QC on what ships: the placed keys as cels (placed coordinates)
            placed = [cut.measure(cut.Cel(f, 0, 0)) for f in pl.frames]
            if state == "idle":
                idle_refs[d] = placed[0]
            try:
                r = qc_mod.qc_clip(placed, state, d, idle_refs if idle_refs else placed[0])
            except Exception as e:                     # QC must never block an export
                r = {"ok": False, "flags": [f"qc error: {e}"], "metrics": {}}
            r["keys"] = [int(i) for i in idx]
            qc_all.setdefault(state, {})[d] = r
            if not r.get("ok", True):
                log(f"    QC {state}/{d}: " + "; ".join(r.get("flags", [])))
            if state == "attack":
                qc_mod.onion(placed).save(out / f"onion_{state}_{d}.png")
        single = state == "die"
        front = next(d for d in ["se", "s", "e", "ne"] + DIRS if d in rows)
        if not single:
            fill_dirs(rows)
        fname = clip.get("file", state)

        def write(order, suffix):
            sheet = Image.new("RGBA", (cell * n, cell * len(order)), (0, 0, 0, 0))
            shad = Image.new("RGBA", sheet.size, (0, 0, 0, 0))
            for r, dd in enumerate(order):
                for i, t in enumerate(rows[dd]):
                    sheet.alpha_composite(t, (i * cell, r * cell))
                    shad.alpha_composite(shadow_of(t, fy * cell), (i * cell, r * cell))
            sheet.save(out / f"{fname}{suffix}.png")
            shad.save(out / f"{fname}{suffix}-shadow.png")

        # one sheet per state: 8 facing rows S..SW by default (the demo), or 4 (FR, FL, BR, BL) with "rows": 4
        use = [front] if single else LAYOUTS[g.get("rows", 8)]
        write(use, "")
        a = {"file": fname, "frames": n, "frameDuration": dur, "rows": len(use), "dirs": use}
        if loop and state in ("idle", "walk", "celebrate"):
            a["loop"] = True
        if single:
            a["singleRow"] = True
        anims[state] = a
        previews[state] = rows[front]
        save_gif([np.asarray(t) for t in rows[front]], out / "gif" / f"{fname}_{front}.gif", [int(dur * 1000)] * n,
                 bg=(64, 84, 60))
        log(f"  {state}: {n}f @ {dur}s  src {idx}  rows {use}")
    actor = {
        "actorId": g.get("actorId", name), "sheetDir": g.get("sheetDir", f"/assets/combat/{name}/lib"),
        "cell": cell, "scale": round(g.get("world_scale", 3.8) * 32 / cell, 4), "anims": anims,
        "attackHitFrame": g["clips"].get("attack", {}).get("hit", HIT_FRAME),
        "shadow": {"scaleRatio": 0.78, "offsetX": 0, "offsetY": -1.4, "alpha": 0.5},
        "healthBar": {"offsetY": -18, "width": 53, "height": 11},
        "hitOffset": {"x": 0, "y": -7.5},
        "recoil": {"distance": 12, "time": 0.07, "recoverTime": 0.11}, "flash": {"time": 0.08, "amount": 0.72},
        "notes": [f"reel export: cut from AI video takes ({spec_path.relative_to(Path.cwd()) if spec_path.is_absolute() else spec_path}); "
                  f"every state resampled to the shared clock, contact key on frame {g['clips'].get('attack', {}).get('hit', HIT_FRAME)}. Shadow/bar/hit offsets are "
                  "defaults, tune in game."],
    }
    (out / f"{actor['actorId']}.json").write_text(json.dumps(actor, indent=2))
    (out / "qc.json").write_text(json.dumps(qc_all, indent=1, default=float))
    # contact board: FR row of every state, 1 cell = cell px
    W = max(len(v) for v in previews.values()) * cell
    board = Image.new("RGB", (W, cell * len(previews)), (64, 84, 60))
    for r, (st, tiles) in enumerate(previews.items()):
        for i, t in enumerate(tiles):
            board.paste(t, (i * cell, r * cell), t)
    board.save(out / "board.png")
    return out

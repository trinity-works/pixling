"""Lit side-view sprites from AI video: colour + normal sheets that any 2D light can shade per pixel.

One left/right character (left = the node mirrored), any number of clips (walk, idle, attack, ...), each cut from its own
MiniMax H3 take filmed from the SAME start image (same design, framing and light). The video supplies colour and
motion; PATINA (Scenario `model_patina`, ~9 CU a frame) supplies normal maps. What this module adds is temporal
stability, a clean game clock and one sheet format every game reads the same way:

  frames   numbered stills f<NNN>.png, NNN = filmed frame number (`reel light frames`); PATINA maps beside them as
           f<NNN>_p_0.png (basecolor) and f<NNN>_p_1.png (normal, green-up) (`reel light patina`)
  key      the take's flat backdrop keyed out (key.py)
  colour   the video frame itself, with the big baked light divided out by one identical filter on every frame
  normals  every frame mapped: motion-aligned average over k-2..k+2 (optical flow from the steady video frames);
           only key frames mapped: each key carried to every frame by optical flow, blended between the two nearest
           keys. Either way no per-frame AI flicker.
  close    per-frame light lean and brightness follow a low-pass (cyclic for loops: no seam jump), and every clip
           shares the lead clip's lean and brightness
  loop     a walk loops where a later frame matches an earlier pose (`find_loop`, silhouette IoU on the body box);
           the match frame is used only to measure drift, never blended in
  drift    a travelling take slowly walks toward the camera: size growth, ground and travel per frame are measured on
           the matching pair and removed linearly. Each frame keeps its true height (snapping every frame's lowest
           pixel to the ground makes the body hop: the near foot lands lower than the far one)
  pack     one atlas, a key-spill pass on the outer edge band, durations from the filmed spacing, stop/start pose
           matches between the lead (travel) clip and the rest clip, sheet json format "pixling.lit-sprite" v1
  check    every pair in play order: colour, histogram, normal lean, height, planted foot, torso acceleration and
           pixel residual after motion (`check`, exit 1 on an alarm)

Players for that format: reel/light_runtime/ (web: litsprite.js, Godot 4: lit_sprite.gd); `reel light export`.

Spec (light.json, paths relative to it; README "light.json" has every option):
  {"name": "golem", "key": [255, 0, 255], "height": 300,
   "clips": {"walk": {"dir": "walk", "loop": [19, 49], "match": 18},
             "idle": {"dir": "idle", "reverse": true},
             "swing": {"dir": "swing", "loop": false}}}
"""
from __future__ import annotations

import hashlib
import json
import re
import shutil
from pathlib import Path

import numpy as np
from PIL import Image
from scipy import ndimage

from .key import KeyCfg, key_frame

FORMAT = "pixling.lit-sprite"
VERSION = 1
PATINA_CU = 9                      # per frame (Scenario model_patina, basecolor + normal), checked 2026-10

FRAME = re.compile(r"^f(\d+)\.png$")


# ---------------------------------------------------------------- frames and maps

def frame_numbers(d) -> list:
    """filmed frame numbers that have a still f<NNN>.png in d, sorted"""
    return sorted(int(m.group(1)) for p in Path(d).iterdir() if (m := FRAME.match(p.name)))


def frame_path(d, k, suffix="") -> Path:
    """f<NNN><suffix>.png, whatever zero padding the directory uses"""
    for p in Path(d).glob(f"f*{k}{suffix}.png"):
        m = re.match(r"^f(\d+)" + re.escape(suffix) + r"\.png$", p.name)
        if m and int(m.group(1)) == k:
            return p
    return Path(d) / f"f{k:03d}{suffix}.png"


def dump_frames(video, out, every=1, start=0, end=None) -> list:
    """video -> out/f<NNN>.png (NNN = filmed frame number)"""
    from .io import read_frames
    out = Path(out); out.mkdir(parents=True, exist_ok=True)
    done = []
    for i, f in enumerate(read_frames(video)):
        if i < start or (end is not None and i > end) or (i - start) % every:
            continue
        Image.fromarray(f).save(out / f"f{i:03d}.png"); done.append(i)
    return done


def keyed(path, key=(255, 0, 255)):
    """still -> (RGB float 0..1, alpha float 0..1) on the full frame"""
    o = np.asarray(Image.open(path).convert("RGB"))
    rgba, (x0, y0), _ = key_frame(o, KeyCfg(color=tuple(key)))
    a = np.zeros(o.shape[:2]); a[y0:y0 + rgba.shape[0], x0:x0 + rgba.shape[1]] = rgba[:, :, 3] / 255
    return o / 255.0, a


def load_normal(path, shape):
    """PATINA normal map (green-up) -> unit normals, screen y-down, resized to shape"""
    n = np.asarray(Image.open(path).convert("RGB").resize(shape[1::-1])) / 255.0 * 2 - 1
    n[:, :, 1] *= -1
    return unit(n)


def unit(n):
    return n / (np.linalg.norm(n, axis=2, keepdims=True) + 1e-6)


def flow(a, b, s=0.5):
    """optical flow (v, u) that brings b's grid onto a (RGB float frames), computed at scale s, returned full size"""
    from skimage.registration import optical_flow_tvl1
    H, W = a.shape[:2]
    sm = lambda x: np.asarray(Image.fromarray((np.clip(x, 0, 1) * 255).astype(np.uint8))
                              .resize((int(W * s), int(H * s)), Image.BILINEAR)).astype(float).mean(2) / 255
    v, u = optical_flow_tvl1(sm(b), sm(a))
    z = (H / v.shape[0], W / v.shape[1])
    return ndimage.zoom(v, z, order=1) / s, ndimage.zoom(u, z, order=1) / s


def warp(img, fl):
    v, u = fl; H, W = v.shape
    r, c = np.meshgrid(np.arange(H), np.arange(W), indexing="ij")
    return np.dstack([ndimage.map_coordinates(img[:, :, ch], [r + v, c + u], order=1, mode="nearest")
                      for ch in range(img.shape[2])])


# ---------------------------------------------------------------- stable colour and normals

def delight(o, a, ref_lum):
    """divide out the big baked light (alpha-normalised blur, the same filter on every frame), toward ref_lum"""
    low = ndimage.gaussian_filter(o.mean(2) * a, 28) / (ndimage.gaussian_filter(a, 28) + 1e-3)
    return np.clip(o / np.clip((low / ref_lum) ** 0.45, 0.6, 1.6)[:, :, None], 0, 1)


def mean_lean(n, a):
    return n[a > .9].mean(0)


def set_lean(n, a, target):
    """shift a frame's mean normal to target (inside the body), renormalised"""
    return unit(n - (mean_lean(n, a) - target) * (a > .05)[:, :, None])


def stabilise(O, N, A, cyclic=True):
    """every frame mapped: lean levelled, then a motion-aligned weighted average over k-2..k+2"""
    n = len(O); H, W = A[0].shape
    lm = np.mean([mean_lean(N[i], A[i]) for i in range(n)], 0)
    Ns = [set_lean(N[i], A[i], lm) for i in range(n)]
    out = []
    for i in range(n):
        acc = Ns[i] * 3; tot = np.full((H, W), 3.0)
        for d, wgt in ((-2, 1), (-1, 2), (1, 2), (2, 1)):
            j = (i + d) % n if cyclic else min(max(i + d, 0), n - 1)
            if j == i:
                continue
            wn = warp(np.dstack([Ns[j], A[j]]), flow(O[i], O[j]))
            w = wgt * (wn[:, :, 3] > .5); acc += wn[:, :, :3] * w[:, :, None]; tot += w
        out.append(soften(acc / tot[:, :, None]))
    return out


def carry(O, A, keys: dict, cyclic=True):
    """only key frames mapped ({index: normals}): each frame takes its two nearest keys, carried by optical flow and
    weighted by 1/(distance+1)"""
    n = len(O); ks = sorted(keys); out = []
    for i in range(n):
        prev = max([k for k in ks if k <= i], default=ks[-1] if cyclic else ks[0])
        nxt = min([k for k in ks if k > i], default=ks[0] if cyclic else ks[-1])
        acc = np.zeros(O[i].shape); tot = np.zeros(A[i].shape)
        for k in {prev, nxt}:
            d = (i - k) % n if cyclic else abs(i - k)
            d = min(d, n - d) if cyclic else d
            src = np.dstack([keys[k], A[k]])
            wn = src if k == i else warp(src, flow(O[i] * A[i][:, :, None], O[k] * A[k][:, :, None]))
            w = (wn[:, :, 3] > .5) / (d + 1.0); acc += wn[:, :, :3] * w[:, :, None]; tot += w
        nm = np.where(tot[:, :, None] > 0, acc / np.maximum(tot, 1e-6)[:, :, None], [0, 0, 1])
        out.append(soften(nm))
    return out


def soften(n, sigma=2.0):
    return unit(np.dstack([ndimage.gaussian_filter(n[:, :, c], sigma) for c in range(3)]))


def close_loop(C, N, A, sigma=2.0, lean=None, cyclic=True):
    """per-frame lean and brightness follow a low-pass of their own sequence (cyclic for a loop); lean = target for the
    clip's average (shared with the lead clip). Returns new C, N."""
    n = len(N); m = [a > .9 for a in A]; mode = "wrap" if cyclic else "nearest"
    means = np.array([N[i][m[i]].mean(0) for i in range(n)]); lv = np.array([C[i][m[i]].mean() for i in range(n)])
    sm = ndimage.gaussian_filter1d(means, sigma, axis=0, mode=mode)
    sl = ndimage.gaussian_filter1d(lv, sigma, mode=mode)
    if lean is not None:
        sm = sm - sm.mean(0) + lean
    C2 = [np.clip(C[i] * sl[i] / lv[i], 0, 1) for i in range(n)]
    N2 = [unit(N[i] + (sm[i] - means[i]) * (A[i] > .05)[:, :, None]) for i in range(n)]
    return C2, N2


# ---------------------------------------------------------------- loops, drift, despill

def box(a):
    ys, xs = np.nonzero(a > .5)
    return xs.min(), ys.min(), xs.max(), ys.max()


def body_sil(a, size=96):
    """silhouette normalised to its box (bottom-centre, body height = size): pose shape without position/scale"""
    x0, y0, x1, y1 = box(a); h = y1 - y0 + 1; s = size / h
    crop = Image.fromarray(((a[y0:y1 + 1] > .5) * 255).astype(np.uint8))
    w = max(1, int(round(a.shape[1] * s)))
    small = np.asarray(crop.resize((w, size), Image.BILINEAR)) > 127
    cx = int(round((x0 + x1) / 2 * s)); out = np.zeros((size, size * 2), bool)
    lo, hi = max(0, cx - size), min(w, cx + size)
    out[:, lo - (cx - size):hi - (cx - size)] = small[:, lo:hi]
    return out


def iou(p, q):
    return float((p & q).sum() / max(1, (p | q).sum()))


def find_loop(A, nums=None, min_len=16, max_len=None):
    """best loop in a walk: frames (s, e) whose poses and motion match (e repeats s, judged on s-2..s+2). Use s+1..e as the loop: e is frame 0 one
    cycle on, and s is kept only to measure drift. Returns [(iou, s, e)] best first (filmed numbers when given)."""
    S = [body_sil(a) for a in A]; n = len(A); max_len = max_len or n; res = []
    for s in range(n):
        for e in range(s + min_len, min(n, s + max_len + 1)):
            # the neighbours must match too: a pose alone repeats on both sides of a stride's extreme
            ds = [d for d in (-2, -1, 0, 1, 2) if 0 <= s + d and e + d < n]
            res.append((float(np.mean([iou(S[s + d], S[e + d]) for d in ds])), s, e))
    res.sort(reverse=True)
    return [(r, nums[s], nums[e]) for r, s, e in res] if nums else res


def drift(a_start, a_end, n):
    """the matching pair a_start .. a_end, n frames apart: (size growth per frame, ground drift and travel per frame,
    source px)"""
    b0, b1 = box(a_start), box(a_end)
    grow = ((b1[3] - b1[1]) / (b0[3] - b0[1])) ** (1.0 / n)
    return grow, (b1[3] - b0[3]) / n, ((b1[0] + b1[2]) - (b0[0] + b0[2])) / 2 / n


def despill(c, a, band=7, key=(255, 0, 255)):
    """key spill on the outer edge band only (the painting's own shadows keep their hue): pull the key channels down"""
    k = np.asarray(key, float); hi = np.nonzero(k > 127)[0]; lo = np.nonzero(k <= 127)[0]
    if not len(hi) or not len(lo):
        return c
    m = a > .15; edge = m & ~ndimage.binary_erosion(m, iterations=band)
    ex = np.clip(c[:, :, hi].min(2) - c[:, :, lo].max(2), 0, None) * edge
    out = c.copy()
    for ch in hi:
        out[:, :, ch] -= ex
    return out


# ---------------------------------------------------------------- spec

def clip_cfg(name, c):
    """one clip's settings with defaults (README "light.json")"""
    loop = c.get("loop", True)
    return {"name": name, "dir": c["dir"], "loop": loop is not False, "auto": loop == "auto",
            "frames": loop if isinstance(loop, list) else c.get("range"), "min_len": c.get("min_len", 16),
            "match": c.get("match"), "travel": bool(c.get("travel", "match" in c or loop == "auto")),
            "reverse": bool(c.get("reverse", False)), "blend": bool(c.get("blend", False)), "fps": c.get("fps", 12),
            "ground": c.get("ground", "median" if loop is not False else "first"), "scale": c.get("scale", "match"),
            "keys_every": c.get("keys_every", 20), "keys_set": "keys_every" in c,
            "speed": c.get("speed", "travel"), "ground_sigma": c.get("ground_sigma", 2.0)}


def load_spec(path):
    """-> (spec, {name: clip cfg}, lead, rest, build order). lead = first travel clip (sets brightness, light lean and
    scale for all); rest = first looping clip that stays in place (the one the lead stops into; the lead itself
    when nothing travels)."""
    S = json.loads(Path(path).read_text())
    clips = {k: clip_cfg(k, v) for k, v in S["clips"].items()}
    lead = S.get("lead") or next((k for k, c in clips.items() if c["travel"]), next(iter(clips)))
    rest = S.get("rest") or next((k for k, c in clips.items() if c["loop"] and not c["travel"] and k != lead), None)
    if rest is None and clips[lead]["loop"] and not clips[lead]["travel"]:
        rest = lead              # nothing travels (e.g. an idle-only sheet): the lead loop is the rest pose
    return S, clips, lead, rest, [lead] + [k for k in clips if k != lead]


def clip_numbers(d, c, key, log=print):
    """the filmed frames a clip plays, and its match frame (auto loops are found here)"""
    nums = frame_numbers(d)
    if c["frames"]:
        nums = [k for k in nums if c["frames"][0] <= k <= c["frames"][1]]
    match = c["match"]
    if c["auto"]:
        A = [keyed(frame_path(d, k), key)[1] for k in nums]
        v, s, e = find_loop(A, nums, c["min_len"])[0]
        log(f"{c['name']}: loop {s + 1}..{e} (frame {e} matches {s}, IoU {v:.3f}); pin it as \"loop\": [{s + 1}, {e}], "
            f"\"match\": {s} after checking")
        nums, match = [k for k in nums if s < k <= e], s
    return nums, match


# ---------------------------------------------------------------- build

def load_clip(d, nums, key):
    O, A, N = [], [], {}
    for i, k in enumerate(nums):
        o, a = keyed(frame_path(d, k), key); O.append(o); A.append(a)
        p = frame_path(d, k, "_p_1")
        if p.exists():
            N[i] = load_normal(p, o.shape)
    return O, A, N


def process_clip(d, c, nums, match, key, ref, cache):
    """stable colour + normals for one clip, cached on its inputs. ref = (brightness, lean) of the lead, None for the
    lead itself. Returns dict(C, N, A, nums, match, ref_lum, mapped)."""
    sig = hashlib.sha1(json.dumps([c, nums, match, list(map(int, key)), ref and [round(ref[0], 3), [round(float(x), 3) for x in ref[1]]], 2],
                                  default=str).encode())
    for k in nums + ([match] if match is not None else []):
        for f in (frame_path(d, k), frame_path(d, k, "_p_1")):
            if f.exists():
                st = f.stat(); sig.update(f"{f.name}:{st.st_size}:{st.st_mtime_ns}".encode())
    cp = Path(cache) / f"{c['name']}_{sig.hexdigest()[:12]}.npz"
    if cp.exists():
        Z = np.load(cp)
        return dict(C=list(Z["C"].astype(float)), N=list(Z["N"].astype(float)), A=list(Z["A"].astype(float)),
                    nums=Z["nums"].tolist(), match=Z["M"].astype(float) if Z["M"].size else None,
                    ref_lum=float(Z["ref_lum"]), mapped=int(Z["mapped"]), cached=True)
    O, A, keys = load_clip(d, nums, key)
    if not keys:
        raise SystemExit(f"{c['name']}: no PATINA normals (f<NNN>_p_1.png) in {d}; run `reel light patina`")
    ref_lum = ref[0] if ref else float(np.mean([o.mean(2)[a > .9].mean() for o, a in zip(O, A)]))
    C = [delight(o, a, ref_lum) for o, a in zip(O, A)]
    every = len(keys) == len(O)
    if every:
        N = stabilise(O, [keys[i] for i in range(len(O))], A, cyclic=c["loop"])
    else:
        if ref:
            keys = {k: set_lean(v, A[k], ref[1]) for k, v in keys.items()}
        N = carry(O, A, keys, cyclic=c["loop"])
    C, N = close_loop(C, N, A, sigma=2.0 if every else 3.0, lean=ref[1] if ref else None, cyclic=c["loop"])
    M = keyed(frame_path(d, match), key)[1] if match is not None else np.zeros(0)
    cp.parent.mkdir(parents=True, exist_ok=True)
    for old in cp.parent.glob(f"{c['name']}_*.npz"):
        old.unlink()
    np.savez_compressed(cp, C=np.array(C, np.float16), N=np.array(N, np.float16), A=np.array(A, np.float16),
                        nums=np.array(nums), M=M.astype(np.float16), ref_lum=ref_lum, mapped=len(keys))
    return dict(C=C, N=N, A=A, nums=nums, match=M if M.size else None, ref_lum=ref_lum, mapped=len(keys), cached=False)


def build(spec_path, out=None, log=print) -> Path:
    """light.json -> <out>/<name>.json + <name>_color / _normal sheets (webp; png too with "png": true)"""
    spec_path = Path(spec_path); base = spec_path.parent
    S, cfgs, lead, rest, order = load_spec(spec_path)
    key = S.get("key", [255, 0, 255]); out = Path(out or base / S.get("out", "sheet")); out.mkdir(parents=True, exist_ok=True)
    clips, ref = {}, None
    for name in order:
        c = cfgs[name]; d = base / c["dir"]
        nums, match = clip_numbers(d, c, key, log)
        cl = process_clip(d, c, nums, match, key, ref, out / "cache")
        if ref is None:          # the lead sets the shared brightness and light lean
            ref = (cl["ref_lum"], np.mean([mean_lean(n, a) for n, a in zip(cl["N"], cl["A"])], 0))
        if c["reverse"]:         # e.g. a take that rises slowly and slumps: backwards it lifts fast and settles slowly
            for k in ("C", "N", "A", "nums"):
                cl[k] = [cl[k][0]] + cl[k][:0:-1]
        cl["cfg"] = c; clips[name] = cl
        log(f"{name}: {len(cl['nums'])} frames, {cl['mapped']} mapped{' (cached)' if cl['cached'] else ''}"
            f"{', lead' if name == lead else ''}{', rest' if name == rest else ''}")
    meta = pack(clips, order, lead, rest, S, out, key)
    log(f"-> {out / (S['name'] + '.json')}  ({len(meta['frames'])} frames, atlas {meta['atlas']})")
    return out / (S["name"] + ".json")


def cut_frame(C, N, A, s, ax, ground, key):
    x0, y0, x1, y1 = box(A); x0 -= 3; y0 -= 3; x1 += 4; y1 += 2
    w, h = int(round((x1 - x0) * s)), int(round((y1 - y0) * s))
    col = Image.fromarray((np.dstack([despill(C, A, key=key), A])[y0:y1, x0:x1] * 255).astype(np.uint8)).resize((w, h), Image.LANCZOS)
    up = N[y0:y1, x0:x1] * np.array([1.0, -1.0, 1.0])          # sheets store normals green-up (Godot, Unity, OpenGL)
    nor = Image.fromarray(((up * .5 + .5) * 255).astype(np.uint8)).resize((w, h), Image.LANCZOS)
    return {"c": col, "n": nor, "w": w, "h": h, "ox": (x0 - ax) * s, "oy": (y0 - ground) * s}


def placement(cl, s):
    """per frame (scale, anchor x, ground y) in source px for a clip drawn at scale s, and its travel per frame (game
    px). Travelling clips remove the drift measured on match -> last frame (or first -> last); clips in place keep
    one ground line (the median foot for loops, the first frame's for one-shots) and the first frame's centre."""
    A = cl["A"]; n = len(A); c = cl["cfg"]
    if c["travel"]:
        ref = cl["match"] if cl["match"] is not None else A[0]; o = 1 if cl["match"] is not None else 0
        grow, dg, dx = drift(ref, A[-1], max(1, n - 1 + o)); b0 = box(ref)
        G = [b0[3] + dg * (k + o) for k in range(n)]
        if c["ground"] == "lowest":      # a take whose whole body bobs off the floor (H3 walks in place): follow the
            low = np.array([box(a)[3] for a in A], float)      # lowest foot, smoothed so the torso doesn't jolt
            G = list(ndimage.gaussian_filter1d(low, c["ground_sigma"], mode="wrap" if c["loop"] else "nearest")
                     if c["ground_sigma"] else low)
        P = [(s * grow ** (-(k - n / 2)), (b0[0] + b0[2]) / 2 + dx * (k + o), G[k]) for k in range(n)]
        return P, (foot_speed(A, P, c["loop"]) if c["speed"] == "foot" else dx * s)
    bs = [box(a) for a in A]; ax = (bs[0][0] + bs[0][2]) / 2
    g = float(np.median([b[3] for b in bs])) if c["ground"] == "median" else float(bs[0][3])
    return [(s, ax, g)] * n, 0.0


def contact_profile(a, p):
    """lowest body pixel per 1 px column, in game px relative to the frame's anchor and ground: {x: y}"""
    s, ax, g = p; m = a > .5; cols = np.nonzero(m.any(0))[0]
    low = m.shape[0] - 1 - np.argmax(m[::-1], 0); out = {}
    for c in cols:
        x = int(round((c - ax) * s)); out[x] = max(out.get(x, -1e9), (low[c] - g) * s)
    return out


def shift_costs(pa, pb, reach, tol=3.0):
    """per shift (game px, + = forward/right): how badly frame b's planted contact matches frame a's moved by it,
    1 - overlap of the two contact sets + under-edge shape difference. Contact = the columns within tol of each frame's
    own lowest point (the body may bob). None where they barely touch."""
    la, lb = max(pa.values()), max(pb.values())
    ca = {x for x, y in pa.items() if y >= la - tol}; cb = {x for x, y in pb.items() if y >= lb - tol}
    out = {}
    for sh in range(-reach, reach + 1):
        both = [x for x in ca if x + sh in cb]
        out[sh] = None if len(both) < 3 else (1 - len(both) / len(ca | {x - sh for x in cb})) + \
            0.05 * float(np.mean([abs((pb[x + sh] - lb) - (pa[x] - la)) for x in both]))
    return out


def foot_speed(A, P, loop=True):
    """walk speed (game px per frame) at which the planted foot stays put in the world. The foot slides back against
    the anchor at one speed for the whole clip, so the shift with the lowest match cost summed over every frame pair
    wins (pairs with an ambiguous contact add a flat curve), refined to sub-pixel. A walk across the frame gives its
    travel; a walk in place (treadmill) gives the belt speed."""
    n = len(A); H = max(1, int(max(box(a)[3] - box(a)[1] for a in A) * P[0][0])); reach = max(4, H // 8)
    prof = [contact_profile(a, p) for a, p in zip(A, P)]
    tot = np.zeros(2 * reach + 1); cnt = np.zeros(2 * reach + 1)
    for k in range(n if loop else n - 1):
        for sh, c in shift_costs(prof[k], prof[(k + 1) % n], reach).items():
            if c is not None:
                tot[sh + reach] += c; cnt[sh + reach] += 1
    if not cnt.any():
        raise SystemExit("speed: foot found no planted contact; use the travel speed")
    m = np.where(cnt >= cnt.max() * 0.5, tot / np.maximum(cnt, 1), np.inf)   # shifts most pairs can be judged at
    b = int(np.argmin(m)); off = 0.0
    if 0 < b < len(m) - 1 and np.isfinite(m[b - 1]) and np.isfinite(m[b + 1]) and m[b - 1] + m[b + 1] - 2 * m[b] > 1e-9:
        off = 0.5 * (m[b - 1] - m[b + 1]) / (m[b - 1] + m[b + 1] - 2 * m[b])
    return float(-(b - reach + off))


def cut_clip(cl, s, key):
    P, speed = placement(cl, s)
    return [cut_frame(C, N, A, *p, key) for C, N, A, p in zip(cl["C"], cl["N"], cl["A"], P)], speed


def canvas(H):
    """silhouette canvas for a character of body height H (game px): (rows, cols), anchor (x, ground row), reach"""
    return (int(H * 1.45), int(H * 2.6)), (int(H * 1.3), int(H * 1.2)), int(H * 0.3)


def durations(nums, fps, loop, source_fps):
    """hold per frame = the filmed spacing to the next frame, at most one game frame (1/fps)"""
    gap = source_fps / fps; n = len(nums)
    out = [min(abs(nums[(k + 1) % n] - nums[k]), gap) / source_fps for k in range(n)]
    if not loop:
        out[-1] = gap / source_fps
    return [round(x, 4) for x in out]


def pack(clips, order, lead, rest, S, out, key):
    H = S.get("height", 300); src_fps = S.get("source_fps", 24); L = clips[lead]
    s_lead = H / float(np.median([box(a)[3] - box(a)[1] for a in L["A"]]))
    cut, speeds = {lead: None}, {}
    cut[lead], speeds[lead] = cut_clip(L, s_lead, key)
    size, base, reach = canvas(H); step = max(2, H // 75)
    WS = [sil(f, 0, size, base) for f in cut[lead]]
    for name in order[1:]:
        cl = clips[name]; s0 = H / float(np.median([box(a)[3] - box(a)[1] for a in cl["A"]]))
        if isinstance(cl["cfg"]["scale"], (int, float)):
            s = s0 * cl["cfg"]["scale"]
        else:                    # same camera, so the scale that makes its first pose overlap the lead's best poses
            best = None
            for f in np.arange(0.86, 1.15, 0.02):
                P, _ = placement(cl, s0 * f)
                I0 = cut_frame(cl["C"][0], cl["N"][0], cl["A"][0], *P[0], key)
                top = sorted(max(iou(sil(I0, d, size, base), ws) for d in range(-reach, reach + 1, step)) for ws in WS)[-6:]
                if best is None or np.mean(top) > best[0]:
                    best = (np.mean(top), s0 * f)
            s = best[1]
        cut[name], speeds[name] = cut_clip(cl, s, key)
    faces = S.get("faces") or (1 if speeds[lead] >= 0 else -1)
    allf = [f for name in order for f in cut[name]]
    cols = S.get("cols", 10); rows = (len(allf) + cols - 1) // cols
    cw = max(x["w"] for x in allf); chh = max(x["h"] for x in allf)
    col = Image.new("RGBA", (cw * cols, chh * rows)); nor = Image.new("RGB", (cw * cols, chh * rows), (128, 128, 255))
    name = S["name"]; ext = "png" if S.get("png") else "webp"
    meta = {"format": FORMAT, "version": VERSION, "name": name,
            "images": {"color": f"{name}_color.{ext}", "normal": f"{name}_normal.{ext}"}, "normal_y": "up",
            "atlas": [cw * cols, chh * rows], "height": H, "faces": faces, "blend_frames": S.get("blend_frames", 4),
            "lead": lead, "rest": rest, "anims": {}, "frames": []}
    start = 0
    for nm in order:
        c = clips[nm]["cfg"]
        a = {"start": start, "count": len(cut[nm]), "fps": c["fps"], "loop": c["loop"], "blend": c["blend"],
             "durations": durations(clips[nm]["nums"], c["fps"], c["loop"], src_fps)}
        if c["travel"]:
            a["speed"] = float(abs(speeds[nm]))
        meta["anims"][nm] = a; start += len(cut[nm])
    for k, fr in enumerate(allf):
        x, y = (k % cols) * cw, (k // cols) * chh
        col.paste(fr["c"], (x, y)); nor.paste(fr["n"], (x, y))
        meta["frames"].append({"u": x, "v": y, "w": fr["w"], "h": fr["h"], "ox": fr["ox"], "oy": fr["oy"]})
    if rest and rest != lead:
        meta["stops"], meta["starts"] = match_poses(cut[lead], cut[rest], H)
        # at least a few lead frames to stop on, even when no pose overlaps as well as asked (a walk in place and an
        # idle from a different framing)
        ious = sorted((x["iou"] for x in meta["stops"]), reverse=True)
        meta["stop_iou"] = float(np.floor(min(S.get("stop_iou", 0.85), ious[min(3, len(ious) - 1)]) * 1e4) / 1e4)
    col.save(out / f"{name}_color.webp", quality=90, method=6); nor.save(out / f"{name}_normal.webp", quality=92, method=6)
    if S.get("png"):
        col.save(out / f"{name}_color.png"); nor.save(out / f"{name}_normal.png")
    (out / f"{name}.json").write_text(json.dumps(meta))
    return meta


def sil(fr, x, size=(420, 760), base=(380, 360)):
    """a packed frame's silhouette on a game-px canvas: anchor at x, ground at base row"""
    can = np.zeros(size, bool); a = np.asarray(fr["c"])[:, :, 3] > 128
    X, Y = int(round(base[0] + x + fr["ox"])), int(round(base[1] + fr["oy"]))
    X0, Y0 = max(X, 0), max(Y, 0); X1, Y1 = min(X + a.shape[1], size[1]), min(Y + a.shape[0], size[0])
    if X1 > X0 and Y1 > Y0:
        can[Y0:Y1, X0:X1] = a[Y0 - Y:Y1 - Y, X0 - X:X1 - X]
    return can


def match_poses(W, I, H=300):
    """for every lead frame the rest pose to stop into, for every rest pose the lead frame to start from (silhouette
    IoU over placement dx): stops [{walk, idle, dx, iou}], starts [{idle, walk, dx, iou}] (keys named after the
    classic walk/idle pair whatever the clips are called)"""
    size, base, reach = canvas(H); step = max(2, H // 100)
    WS = [sil(f, 0, size, base) for f in W]; best = np.zeros((len(W), len(I))); bdx = np.zeros_like(best)
    for j, f in enumerate(I):
        for d in range(-reach, reach + 1, step):
            s = sil(f, d, size, base)
            for k, ws in enumerate(WS):
                v = iou(s, ws)
                if v > best[k, j]:
                    best[k, j], bdx[k, j] = v, d
    stops = [{"walk": k, "idle": int(best[k].argmax()), "dx": float(bdx[k, best[k].argmax()]), "iou": float(best[k].max())}
             for k in range(len(W))]
    starts = [{"idle": j, "walk": int(best[:, j].argmax()), "dx": float(bdx[best[:, j].argmax(), j]),
               "iou": float(best[:, j].max())} for j in range(len(I))]
    return stops, starts


# ---------------------------------------------------------------- PATINA, export, scaffold

def patina_plan(spec_path):
    """per clip the frames that still need PATINA maps: every frame of a travelling clip (stabilised per frame), key
    frames every `keys_every` filmed frames for the others (carried by flow). -> [(dir, [frame numbers])]"""
    spec_path = Path(spec_path); base = spec_path.parent; S, cfgs, *_ = load_spec(spec_path); plan = []
    for name, c in cfgs.items():
        d = base / c["dir"]; nums = frame_numbers(d)
        if c["frames"]:
            nums = [k for k in nums if c["frames"][0] <= k <= c["frames"][1]]
        if not nums:
            continue
        if c["travel"] and not c["keys_set"]:
            want = nums
        else:
            want = sorted({min(nums, key=lambda k: abs(k - t)) for t in range(nums[0], nums[-1] + 1, c["keys_every"])})
            if not c["loop"] and nums[-1] - want[-1] > c["keys_every"] / 2:   # a one-shot's end (a loop wraps to its start)
                want.append(nums[-1])
        plan.append((d, [k for k in want if not frame_path(d, k, "_p_1").exists()]))
    return plan


def run_patina(d, k, log=print):
    """one frame through Scenario model_patina (via `pixling scenario`): writes f<NNN>_p_0.png and _p_1.png"""
    import subprocess, sys
    f = frame_path(d, k); root = Path(__file__).resolve().parent.parent
    up = subprocess.run([sys.executable, "-m", "pp", "scenario", "upload", str(f)], cwd=root, capture_output=True, text=True)
    asset = (up.stdout.strip().splitlines() or [""])[-1].strip()
    if up.returncode or not asset:
        raise RuntimeError(f"upload {f}: {up.stderr.strip()[-300:]}")
    params = json.dumps({"image": asset, "maps": ["basecolor", "normal"]})
    r = subprocess.run([sys.executable, "-m", "pp", "scenario", "run", "model_patina", params,
                        "--out", str(f.with_name(f.stem + "_p.png"))], cwd=root, capture_output=True, text=True)
    if r.returncode or not frame_path(d, k, "_p_1").exists():
        raise RuntimeError(f"patina {f}: {(r.stderr or r.stdout).strip()[-300:]}")
    log(f"  {f.name}: maps ok")


def patina(spec_path, yes=False, jobs=6, log=print):
    from concurrent.futures import ThreadPoolExecutor
    plan = patina_plan(spec_path); todo = [(d, k) for d, ks in plan for k in ks]
    for d, ks in plan:
        log(f"{d.name}: {len(ks)} frames need maps" + (f" ({ks[0]}..{ks[-1]})" if ks else ""))
    log(f"total {len(todo)} frames x ~{PATINA_CU} CU = ~{len(todo) * PATINA_CU} CU")
    if not todo or not yes:
        if todo:
            log("dry run: add --yes to spend the credits")
        return len(todo)
    errs = []
    with ThreadPoolExecutor(jobs) as ex:
        for fut in [ex.submit(run_patina, d, k, log) for d, k in todo]:
            try:
                fut.result()
            except RuntimeError as e:
                errs.append(str(e)); log(f"  failed: {e}")
    if errs:
        raise SystemExit(f"{len(errs)} frames failed; rerun to retry only those")
    return 0


RUNTIME = Path(__file__).resolve().parent / "light_runtime"


def export(json_path, dest, engine="web") -> Path:
    """copy a lit sheet and its player into a game folder: web -> litsprite.js, godot -> lit_sprite.gd + PNG sheets
    (Godot imports PNG). The json's "images" are rewritten to the copied files."""
    json_path = Path(json_path); M = json.loads(json_path.read_text()); dest = Path(dest); dest.mkdir(parents=True, exist_ok=True)
    name = M["name"]; ext = "png" if engine == "godot" else "webp"
    for kind in ("color", "normal"):
        src = json_path.with_name(M.get("images", {}).get(kind, f"{name}_{kind}.webp"))
        dst = dest / f"{name}_{kind}.{ext}"
        if src.suffix[1:] == ext:
            shutil.copyfile(src, dst)
        else:
            Image.open(src).save(dst, **({"quality": 92, "method": 6} if ext == "webp" else {}))
        M.setdefault("images", {})[kind] = dst.name
    (dest / f"{name}.json").write_text(json.dumps(M))
    shutil.copyfile(RUNTIME / ("lit_sprite.gd" if engine == "godot" else "litsprite.js"), dest / ("lit_sprite.gd" if engine == "godot" else "litsprite.js"))
    return dest / f"{name}.json"


def demo(json_path, out=None) -> Path:
    """a playable page for one lit sheet: walk with A/D, play the other clips with 1-9, a light that follows the
    pointer (click to drop it), and a warm key light"""
    json_path = Path(json_path); M = json.loads(json_path.read_text())
    out = Path(out or json_path.parent / "demo"); export(json_path, out, "web")
    page = (RUNTIME / "demo.html").read_text().replace("__SHEET__", f"{M['name']}.json").replace("__NAME__", M["name"].title())
    (out / "index.html").write_text(page)
    return out / "index.html"


def start_frame(image, out, key=(255, 0, 255), size=(1920, 1080), height=0.44, left=0.05, ground=0.92) -> Path:
    """a design image -> the takes' start frame: the keyed figure on a flat key-colour 16:9 frame, at the left (room
    to walk right across it), feet at `ground`, body `height` of the frame (the golem's framing)"""
    o = np.asarray(Image.open(image).convert("RGB"))
    rgba, _, _ = key_frame(o, KeyCfg(color=tuple(key)))
    fig = Image.fromarray(rgba); fig = fig.crop(fig.getchannel("A").point(lambda v: 255 if v > 127 else 0).getbbox())
    s = size[1] * height / fig.height
    fig = fig.resize((max(1, int(round(fig.width * s))), max(1, int(round(fig.height * s)))), Image.LANCZOS)
    can = Image.new("RGB", size, tuple(key)); x = int(size[0] * left); y = int(size[1] * ground) - fig.height
    can.paste(fig, (x, y), fig)
    Path(out).parent.mkdir(parents=True, exist_ok=True); can.save(out)
    return Path(out)


def new(name, root=None) -> Path:
    """reel/lit/<name>/ from the template: light.json + empty clip dirs, takes/ and ref/ (the start image)"""
    root = Path(root or Path(__file__).resolve().parent / "lit"); d = root / name
    if d.exists():
        raise SystemExit(f"{d} exists")
    shutil.copytree(root / "_template", d)
    spec = json.loads((d / "light.json").read_text()); spec["name"] = name; spec["out"] = spec["out"].replace("NAME", name)
    (d / "light.json").write_text(json.dumps(spec, indent=1) + "\n")
    for c in spec["clips"].values():
        (d / c["dir"]).mkdir(exist_ok=True)
    for sub in ("takes", "ref"):
        (d / sub).mkdir(exist_ok=True)
    return d / "light.json"


# ---------------------------------------------------------------- check

LIMITS = {"dPix": 0.02, "dMotion": 2.5, "dL": 0.02, "dC": 0.012, "dSpread": 0.02, "dHist": 0.02, "dNormal": 0.05,
          "dHeight": 0.04, "dFoot": 6.0, "dTorso": 4.0}


def oklab(rgb):
    c = np.where(rgb <= 0.04045, rgb / 12.92, ((rgb + 0.055) / 1.055) ** 2.4)
    l = np.cbrt(np.clip(c @ np.array([[0.4122214708, 0.2119034982, 0.0883024619], [0.5363325363, 0.6806995451, 0.2817188376],
                                      [0.0514459929, 0.1073969566, 0.6299787005]]), 0, None))
    return l @ np.array([[0.2104542553, 1.9779984951, 0.0259040371], [0.7936177850, -2.4285922050, 0.7827717662],
                         [-0.0040720468, 0.4505937099, -0.8086757660]])


def check(json_path, log=print):
    """alarm table for a packed lit sheet, measured on what the game shows. Every clip's pairs in play order (and the
    seam of a loop), plus every lead -> rest stop. A pair alarms when a change is above its absolute limit AND 3x the
    clip's typical step. dFoot = how far the planted foot moved (a footfall is motion, every contact moving is a pop);
    dTorso = upper-body acceleration along a travelling clip (a lurch); dMotion = mean flow after placement. Returns
    the alarms (empty = pass)."""
    from skimage.registration import optical_flow_tvl1
    json_path = Path(json_path); M = json.loads(json_path.read_text()); name = M.get("name", json_path.stem)
    imgs = M.get("images", {"color": f"{name}_color.webp", "normal": f"{name}_normal.webp"})
    col = np.asarray(Image.open(json_path.with_name(imgs["color"])).convert("RGBA")).astype(float) / 255
    nor = np.asarray(Image.open(json_path.with_name(imgs["normal"])).convert("RGB")).astype(float) / 255 * 2 - 1
    an = M["anims"]; lead, rest = M.get("lead", "walk"), M.get("rest", "idle"); faces = M.get("faces", 1)
    blend = M.get("blend_frames", 1)
    hmax = max(f["h"] for f in M["frames"]); wmax = max(f["w"] for f in M["frames"])
    smax = max([a.get("speed", 0) for a in an.values()] + [0])
    CH, CW = int(hmax * 1.3) + 20, int(wmax * 2 + 4 * smax) + 40; BX, BY = CW // 2, int(hmax * 1.15) + 10

    def crop(img, f):
        return img[f["v"]:f["v"] + f["h"], f["u"]:f["u"] + f["w"]]

    def bottom(m, f):
        cs = np.nonzero(m.any(0))[0]; low = m.shape[0] - 1 - np.argmax(m[::-1], 0); o = {}
        for c in cs:
            b = int((f["ox"] + c) // 6); o[b] = max(o.get(b, -1e9), f["oy"] + low[c])
        return o

    st = []
    with np.errstate(all="ignore"):
        for f in M["frames"]:
            c, nn = crop(col, f), crop(nor, f); m = c[:, :, 3] > .9; lab = oklab(c[:, :, :3][m]); ys, xs = np.nonzero(m)
            hist = np.histogram(lab[:, 0], bins=32, range=(0, 1))[0].astype(float)
            top = ys < ys.min() + 0.45 * (ys.max() - ys.min())
            st.append({"lab": lab.mean(0), "sd": lab.std(0), "nrm": nn[m].mean(0), "cdf": np.cumsum(hist / hist.sum()),
                       "h": float(ys.max() - ys.min()), "bot": bottom(m, f),
                       "torso": np.array([f["ox"] + xs[top].mean(), f["oy"] + ys[top].mean()])})

    def contact_move(a, b, sh):
        def one(p, q, s):
            lo = max(p.values()); best = 1e9
            for k, y in p.items():
                if y >= lo - 4 and (k + s) in q:
                    best = min(best, abs(q[k + s] - y))
            return best if best < 1e9 else abs(max(q.values()) - lo)
        return min(one(a, b, sh), one(b, a, -sh))

    def placed(i, x):
        f = M["frames"][i]; c = crop(col, f); can = np.zeros((CH, CW, 4))
        X, Y = int(round(BX + x + f["ox"])), int(round(BY + f["oy"]))
        X0, Y0 = max(X, 0), max(Y, 0); X1, Y1 = min(X + f["w"], CW), min(Y + f["h"], CH)
        if X1 > X0 and Y1 > Y0:
            can[Y0:Y1, X0:X1] = c[Y0 - Y:Y1 - Y, X0 - X:X1 - X]
        return can

    def pix(i, j, dx):
        a, b = placed(i, 0), placed(j, dx); ga, gb = a[::2, ::2, :3].mean(2), b[::2, ::2, :3].mean(2)
        v, u = optical_flow_tvl1(gb, ga); r, c = np.meshgrid(np.arange(ga.shape[0]), np.arange(ga.shape[1]), indexing="ij")
        wa = np.dstack([ndimage.map_coordinates(a[::2, ::2, ch], [r + v, c + u], order=1) for ch in range(4)])
        m = (wa[:, :, 3] > .9) & (b[::2, ::2, 3] > .9)
        return (0.0, 0.0) if not m.any() else (float(np.abs(wa[:, :, :3] - b[::2, ::2, :3])[m].mean()),
                                                float(np.hypot(v, u)[m].mean() * 2))

    pairs = []
    for nm, a in an.items():
        n0, n = a["start"], a["count"]; dx = a.get("speed", 0.0) * faces
        pairs += [(nm, n0 + k, n0 + (k + 1) % n, dx) for k in range(n if a.get("loop", True) else n - 1)]
    if rest in an and lead in an and rest != lead:
        pairs += [("stop", an[lead]["start"] + s["walk"], an[rest]["start"] + s["idle"], s["dx"])
                  for s in M.get("stops", []) if s["iou"] >= M.get("stop_iou", .85)]
    rows = []
    for clip, i, j, dx in pairs:
        a, b = st[i], st[j]; pr, mo = pix(i, j, dx)
        d = {"dPix": pr, "dMotion": mo, "dL": abs(b["lab"][0] - a["lab"][0]), "dC": float(np.hypot(*(b["lab"][1:] - a["lab"][1:]))),
             "dSpread": float(np.abs(b["sd"] - a["sd"]).sum()), "dHist": float(np.abs(b["cdf"] - a["cdf"]).sum() / 32),
             "dNormal": float(np.linalg.norm(b["nrm"] - a["nrm"])), "dHeight": abs(b["h"] - a["h"]) / a["h"],
             "dFoot": 0.0 if clip == "stop" else contact_move(a["bot"], b["bot"], -int(round(dx / 6))), "dTorso": 0.0}
        A_ = an.get(clip)
        if A_ and A_.get("speed"):           # torso path along the travel: k-th frame drawn k steps on
            n0, n = A_["start"], A_["count"]; k = i - n0
            path = lambda q: st[n0 + q % n]["torso"] + np.array([q * dx, 0.0])
            if A_.get("loop", True) or k + 2 < n:
                d["dTorso"] = float(np.linalg.norm(path(k + 2) - 2 * path(k + 1) + path(k)))
        if clip == "stop":                       # crossfaded over blend_frames
            d = {k_: v / blend for k_, v in d.items()}
        elif A_ and A_.get("blend"):             # a blended pose shows 1/(hold*fps) of the change per game frame
            hold = (A_.get("durations") or [1 / A_["fps"]] * A_["count"])[i - A_["start"]]
            d = {k_: v / max(1.0, hold * A_["fps"]) for k_, v in d.items()}
        rows.append((clip, i, j, d))
    alarms = []
    for clip in list(an) + ["stop"]:
        rs = [r for r in rows if r[0] == clip]; base = [r for r in rows if r[0] == lead] if clip == "stop" else rs
        for k_, lim in LIMITS.items():
            med = float(np.median([r[3][k_] for r in base])) if base else 0.0
            alarms += [(c_, i, j, k_, d[k_], lim, med) for c_, i, j, d in rs if d[k_] > lim and d[k_] > 3 * med]
    log(f"{'pair':16} " + " ".join(f"{k:>8}" for k in LIMITS))
    for clip, i, j, d in rows:
        flag = "  <-- ALARM" if any(a[:3] == (clip, i, j) for a in alarms) else ""
        log(f"{clip[:10]:10} {i:2d}->{j:2d} " + " ".join(f"{d[k]:8.3f}" for k in LIMITS) + flag)
    for a in alarms:
        log(f"ALARM {a[0]} {a[1]}->{a[2]}: {a[3]} = {a[4]:.3f} (limit {a[5]}, typical {a[6]:.3f})")
    return alarms

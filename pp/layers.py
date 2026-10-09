"""Animation layers: combine clips by body part, and add small "life" on top — before the motion passes.

Forge.clips() runs these on raw clips, BEFORE aims/feet are resolved and before drag, follow-through and
stabilize, so every existing guarantee (planted feet, overlap, no boiling pixels) holds for the result and
the springs react to the combined motion. Nothing here runs unless a spec (or its style) asks for it.

Combos (spec "layers"): a base clip drives the body, an "over" clip replaces a set of bones.
  "layers": {"run_attack": {"base": "run", "over": [{"clip": "attack", "bones": "torso/", "spine": 0.5}]}}
  bones: comma list; "name/" = the bone and everything under it. spine: the first bone of each subtree
  blends base->over by this much (slerp), so the waist doesn't shear. Length = the over clip (one-shot) or
  "length": "base". Root motion, squash and footsteps come from the base; hit/smear/hide/flash from the over.
  Combos are baked into their own sheets; runtime layering of split sprites leaves seams in pixel art.

Life (spec or style "life"), additive, in whole pixels:
  "sway":    {"bones": [...], "px": 1, "frames": 8, "wave": 0.9}  props: bones shift sideways by whole pixels in
             a travelling wave (pure translation keeps every pixel of the part: no re-raster, no swimming)
  "flutter": {"bones": ["cape"], "px": 1}   loops: cloth tips flick 1 px in a CLOTH_FLUTTER beat
             [0,1,0,-1,0,-1,0,1], phase per bone, capped so it never competes with the gait
  "look":    {"every": 3, "deg": 25}        idle: every 3rd breath the head turns aside and back
             (minimum-jerk in, hold, out) — the idle becomes 3 loops long so the turn stays rare
"""
from __future__ import annotations

import math
from dataclasses import replace
from typing import Callable, Dict, List, Tuple

from .anim import Clip, Frame, merge
from . import motion as M

FLUTTER = [0, 1, 0, -1, 0, -1, 0, 1]


# ------------------------------------------------------------------ masks

def bone_mask(model, spec: str) -> Tuple[List[str], List[str]]:
    """ "torso/, armR" -> (bone names in model order, the named roots); a trailing / takes the subtree."""
    want = set()
    roots = []
    for tok in [t.strip() for t in spec.split(",") if t.strip()]:
        sub = tok.endswith("/")
        name = tok.rstrip("/")
        if name not in model.bones:
            raise ValueError("layer mask: unknown bone %r" % name)
        want.add(name)
        roots.append(name)
        if sub:
            for n in model.order:                     # order is parent-first, so one pass collects the subtree
                if model.bones[n].parent in want:
                    want.add(n)
    return [n for n in model.order if n in want], roots


# ------------------------------------------------------------------ combos

def combo(model, name: str, cfg: Dict, raw: Callable[[str], Clip]) -> Clip:
    base = raw(cfg["base"])
    masks = []
    for o in cfg.get("over", []):
        bones, roots = bone_mask(model, o.get("bones", "torso/"))
        masks.append((raw(o["clip"]), set(bones), set(roots), float(o.get("spine", 0.5))))
    if not masks:
        return replace(base, name=name)
    lead = masks[0][0]
    by_base = cfg.get("length") == "base"
    n = len(base.frames) if by_base else len(lead.frames)
    loop = base.loop if by_base else lead.loop
    # hitstop: while the lead clip is frozen on its impact, the base holds too (the whole body stops)
    step, frozen = [0], False
    for j in range(1, n):
        cur, prev = lead.frames[min(j, len(lead.frames) - 1)], lead.frames[min(j - 1, len(lead.frames) - 1)]
        frozen = j < len(lead.frames) and cur.pose == prev.pose and (prev.event == "hit" or frozen)
        step.append(step[-1] + (0 if frozen else 1))
    frames: List[Frame] = []
    for i in range(n):
        bf = base.frames[step[i] % len(base.frames)]
        pose = {b: dict(v) for b, v in bf.pose.items()}
        fx = list(bf.fx)
        event, hide, flash = bf.event, list(bf.hide), bf.flash
        for clip, bones, roots, spine in masks:
            j = i % len(clip.frames) if clip.loop else min(i, len(clip.frames) - 1)
            of = clip.frames[j]
            for b in bones:
                if b in roots and spine < 1.0:
                    pose[b] = M.mix({b: bf.pose.get(b, {})}, {b: of.pose.get(b, {})}, spine)[b]
                elif b in of.pose:
                    pose[b] = dict(of.pose[b])
                else:
                    pose.pop(b, None)                 # the over clip holds this bone at rest
            fx += [x for x in of.fx if x.get("kind") != "dust"]
            if of.event:
                event = of.event                      # a hit outranks a footstep
            hide += [h for h in of.hide if h not in hide]
            flash = flash or of.flash
        frames.append(Frame(pose, bf.ms, bf.root, bf.squash, flash, fx, event, hide, bf.away))
    speed = base.speed_px * (step[-1] + 1) / max(1, len(base.frames))
    return Clip(name, frames, loop, speed)


# ------------------------------------------------------------------ life

def sway(clip: Clip, cfg: Dict) -> Clip:
    """Travelling whole-pixel sideways wave over the listed bones (flora crowns, flags, sails)."""
    bones = cfg.get("bones", [])
    n = int(cfg.get("frames", 8))
    px = float(cfg.get("px", 1))
    wave = float(cfg.get("wave", 0.9))
    if not bones or n < 2:
        return clip
    frames = []
    for i in range(n):
        f = clip.frames[i % len(clip.frames)]
        add = {}
        for k, b in enumerate(bones):
            v = math.sin(2 * math.pi * (i / n) - k * wave)
            add[b] = {"at": [float(round(v * px)), 0, 0]}
        frames.append(replace(f, pose=merge(f.pose, add), fx=list(f.fx)))
    return replace(clip, frames=frames, loop=True)


def flutter(model, clip: Clip, cfg: Dict) -> Clip:
    """Cloth tips flick by ~px at the tip in a fixed 8-beat, resampled to the loop so it still closes."""
    bones = [b for b in cfg.get("bones", []) if b in model.bones]
    if not clip.loop or not bones:
        return clip
    from .variants import keyed
    n = len(clip.frames)
    px = float(cfg.get("px", 1))
    for b in bones:
        deg = math.degrees(px / max(1.0, M._reach(model, b)))
        ph = int(keyed(0, "flutter", b) * 8)
        for i, f in enumerate(clip.frames):
            v = FLUTTER[(i * 8 // n + ph) % 8]
            if v:
                f.pose = merge(f.pose, {b: {"rot": (v * deg, 0, 0)}})
    return clip


def _min_jerk(u: float) -> float:
    u = min(1.0, max(0.0, u))
    return u ** 3 * (10 - 15 * u + 6 * u * u)


def look(model, clip: Clip, cfg: Dict) -> Clip:
    """Idle look-aside: the idle repeats `every` times; in the last repeat the head turns deg (yaw) and back."""
    if "head" not in model.bones:
        return clip
    k = max(1, int(cfg.get("every", 3)))
    deg = float(cfg.get("deg", 25))
    frames = [replace(f, pose={b: dict(v) for b, v in f.pose.items()}, fx=list(f.fx))
              for _ in range(k) for f in clip.frames]
    n = len(clip.frames)
    s = (k - 1) * n                                  # the turn lives in the last repeat
    lead, t_in, hold = 2, max(2, n // 5), max(2, n // 4)   # 16-frame idle: 2 still, 3 in, 4 held, 3 out
    for i in range(n):
        u = i - lead + 1
        if u <= 0:
            a = 0.0
        elif u <= t_in:
            a = _min_jerk(u / t_in)
        elif u <= t_in + hold:
            a = 1.0
        else:
            a = 1.0 - _min_jerk((u - t_in - hold) / t_in)
        if a:
            f = frames[s + i]
            f.pose = merge(f.pose, {"head": {"rot": (0, 0, deg * a)}})
    return replace(clip, frames=frames)


def apply_life(model, clips: List[Clip], life: Dict) -> List[Clip]:
    out = []
    for c in clips:
        if "sway" in life and c.name == "idle":
            c = sway(c, life["sway"])
        if "flutter" in life:
            c = flutter(model, c, life["flutter"])
        if "look" in life and c.name == "idle":
            c = look(model, c, life["look"])
        out.append(c)
    return out

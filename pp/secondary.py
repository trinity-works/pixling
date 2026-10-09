"""Secondary motion: spring-driven follow-through for props (tails, ears, capes, hair, plumes).

Each follow bone is a damped angular spring driven by the acceleration of its joint: when the
body drops, a tail lags up, then overshoots and settles. Loops are simulated for a few cycles
first so the result joins seamlessly. Adds rotation on top of whatever the clip already poses.

spec anim: "follow": {"tail": {"gain": 7, "k": 0.35, "damp": 0.45, "axes": "xz"}, ...}
(anim.props bones get a default spring when "follow" is not given.)
"""
from __future__ import annotations

from typing import Dict, List

import numpy as np

from .anim import Clip


def _joint_track(model, clip: Clip, bone: str) -> np.ndarray:
    parent = model.bones[bone].parent
    pts = []
    for fr in clip.frames:
        world = model.world(fr.pose, 0.0, tuple(fr.squash))
        M, o = world[bone]
        pts.append(o + np.asarray(fr.root, float))
    return np.array(pts)


def apply(model, clip: Clip, follow: Dict[str, Dict]) -> Clip:
    n = len(clip.frames)
    if n < 2 or not follow:
        return clip
    for bone, cfg in follow.items():
        if bone not in model.bones:
            continue
        gain = float(cfg.get("gain", 7.0))       # degrees of lag per px/frame^2 of joint acceleration
        k = float(cfg.get("k", 0.35))            # spring stiffness per frame
        damp = float(cfg.get("damp", 0.45))
        axes = cfg.get("axes", "xz")
        limit = float(cfg.get("limit", 35.0))
        P = _joint_track(model, clip, bone)
        if clip.loop:
            vel = (np.roll(P, -1, 0) - np.roll(P, 1, 0)) / 2
            acc = np.roll(P, -1, 0) - 2 * P + np.roll(P, 1, 0)
        else:
            vel = np.gradient(P, axis=0)
            acc = np.gradient(vel, axis=0)
        # whole-pixel snapping makes acceleration spiky; low-pass it so props sway instead of flicker
        kern = np.array([1, 2, 3, 2, 1], float) / 9
        if clip.loop:
            acc = np.stack([np.convolve(np.concatenate([acc[-2:, j], acc[:, j], acc[:2, j]]), kern, "valid")
                            for j in range(3)], 1)
        else:
            acc = np.stack([np.convolve(np.pad(acc[:, j], 2, mode="edge"), kern, "valid") for j in range(3)], 1)
        # target lag angles: vertical accel swings the prop about x (up/down), lateral about z
        tgt = np.zeros((n, 3))
        if "x" in axes:
            tgt[:, 0] = gain * acc[:, 2] - gain * 0.6 * acc[:, 1]
        if "z" in axes:
            tgt[:, 2] = -gain * acc[:, 0]
        ang = np.zeros(3)
        w = np.zeros(3)
        out = np.zeros((n, 3))
        cycles = 4 if clip.loop else 1
        for c in range(cycles):
            for i in range(n):
                a = -k * (ang - tgt[i]) - damp * w
                w = w + a
                ang = np.clip(ang + w, -limit, limit)
                if c == cycles - 1:
                    out[i] = ang
        for i, fr in enumerate(clip.frames):
            d = dict(fr.pose.get(bone, {}))
            r = d.get("rot", (0, 0, 0))
            d["rot"] = tuple(float(x) + float(y) for x, y in zip(r, out[i]))
            fr.pose = dict(fr.pose)
            fr.pose[bone] = d
    return clip

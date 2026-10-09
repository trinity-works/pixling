"""Motion toolkit: key poses -> frames with real arcs and spacing, plus drag (successive breaking of joints).

- Rotations are interpolated as rotations (quaternion slerp), not per-axis Euler lerps, so a weapon swung
  from "raised behind" to "struck forward" travels one clean arc instead of a wobbling Euler path.
- Every segment has its own spacing ("io" slow in/out, "in" slow into the key, "out" slow out of the last
  key, "lin", "snap" = arrive in one frame, "hold" = stay on the previous key until the next key time).
- drag(): a post pass for any clip (built-in or custom). A child bone keeps its WORLD orientation for a
  fraction of a frame while its parent turns, so the chain hips > torso > arm > forearm > weapon breaks
  successively (overlap + follow-through) instead of every bone starting and stopping together.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field, replace
from typing import Dict, List, Optional, Sequence, Tuple

import numpy as np

from .sdf import STAMP_SHAPES, rot_matrix

Pose = Dict[str, Dict]


# ------------------------------------------------------------------ rotations

def quat_from_matrix(R: np.ndarray) -> np.ndarray:
    m = R
    tr = m[0, 0] + m[1, 1] + m[2, 2]
    if tr > 0:
        s = math.sqrt(tr + 1.0) * 2
        q = [0.25 * s, (m[2, 1] - m[1, 2]) / s, (m[0, 2] - m[2, 0]) / s, (m[1, 0] - m[0, 1]) / s]
    elif m[0, 0] > m[1, 1] and m[0, 0] > m[2, 2]:
        s = math.sqrt(1.0 + m[0, 0] - m[1, 1] - m[2, 2]) * 2
        q = [(m[2, 1] - m[1, 2]) / s, 0.25 * s, (m[0, 1] + m[1, 0]) / s, (m[0, 2] + m[2, 0]) / s]
    elif m[1, 1] > m[2, 2]:
        s = math.sqrt(1.0 + m[1, 1] - m[0, 0] - m[2, 2]) * 2
        q = [(m[0, 2] - m[2, 0]) / s, (m[0, 1] + m[1, 0]) / s, 0.25 * s, (m[1, 2] + m[2, 1]) / s]
    else:
        s = math.sqrt(1.0 + m[2, 2] - m[0, 0] - m[1, 1]) * 2
        q = [(m[1, 0] - m[0, 1]) / s, (m[0, 2] + m[2, 0]) / s, (m[1, 2] + m[2, 1]) / s, 0.25 * s]
    q = np.asarray(q, float)
    return q / np.linalg.norm(q)


def matrix_from_quat(q: np.ndarray) -> np.ndarray:
    w, x, y, z = q
    return np.array([
        [1 - 2 * (y * y + z * z), 2 * (x * y - z * w), 2 * (x * z + y * w)],
        [2 * (x * y + z * w), 1 - 2 * (x * x + z * z), 2 * (y * z - x * w)],
        [2 * (x * z - y * w), 2 * (y * z + x * w), 1 - 2 * (x * x + y * y)]])


def euler_from_matrix(R: np.ndarray) -> Tuple[float, float, float]:
    """Inverse of sdf.rot_matrix (R = Rz @ Ry @ Rx), degrees."""
    sy = -R[2, 0]
    sy = max(-1.0, min(1.0, sy))
    b = math.asin(sy)
    if abs(sy) < 0.99999:
        a = math.atan2(R[2, 1], R[2, 2])
        c = math.atan2(R[1, 0], R[0, 0])
    else:                                    # gimbal lock: put everything on x
        a = math.atan2(-R[1, 2], R[1, 1])
        c = 0.0
    return (math.degrees(a), math.degrees(b), math.degrees(c))


def slerp(q0: np.ndarray, q1: np.ndarray, t: float) -> np.ndarray:
    d = float(q0 @ q1)
    if d < 0:
        q1, d = -q1, -d
    if d > 0.9995:
        q = q0 + (q1 - q0) * t
        return q / np.linalg.norm(q)
    th = math.acos(d)
    return (math.sin((1 - t) * th) * q0 + math.sin(t * th) * q1) / math.sin(th)


def _q(rot) -> np.ndarray:
    return quat_from_matrix(rot_matrix(*rot))


def slerp_rot(r0, r1, t: float) -> Tuple[float, float, float]:
    """Euler (deg) -> Euler, along the rotation arc. Keeps plain Euler values when only one axis moves
    (identical result, and it keeps big single-axis swings > 180 deg that a quaternion would shortcut)."""
    r0, r1 = tuple(r0), tuple(r1)
    moving = [i for i in range(3) if abs(r0[i] - r1[i]) > 1e-9]
    if len(moving) <= 1 or t <= 0 or t >= 1:
        v = r0 if t <= 0 else r1 if t >= 1 else tuple(a + (b - a) * t for a, b in zip(r0, r1))
        return tuple(float(x) for x in v)
    return euler_from_matrix(matrix_from_quat(slerp(_q(r0), _q(r1), t)))


# ------------------------------------------------------------------ spacing

def spacing(kind: str, t: float) -> float:
    if kind == "hold":
        return 0.0 if t < 1 else 1.0
    if kind == "snap":
        return 1.0
    if kind == "lin":
        return t
    if kind == "in":           # slow into the key (fast start): ease-out curve
        return 1 - (1 - t) ** 2
    if kind == "out":          # slow out of the previous key (fast finish): ease-in curve
        return t * t
    if kind == "in3":
        return 1 - (1 - t) ** 3
    if kind == "out3":
        return t ** 3
    return 3 * t * t - 2 * t ** 3            # "io"


def mix(a: Pose, b: Pose, t: float) -> Pose:
    """Pose blend: rotations along the arc, offsets and scales linear."""
    out: Pose = {}
    for bone in set(a) | set(b):
        pa, pb = a.get(bone, {}), b.get(bone, {})
        d = {}
        ra, rb = pa.get("rot", (0, 0, 0)), pb.get("rot", (0, 0, 0))
        if any(ra) or any(rb):
            d["rot"] = slerp_rot(ra, rb, t)
        for k, dflt in (("at", (0, 0, 0)), ("scale", (1, 1, 1))):
            va, vb = pa.get(k, dflt), pb.get(k, dflt)
            if tuple(va) != dflt or tuple(vb) != dflt:
                d[k] = tuple(x + (y - x) * t for x, y in zip(va, vb))
        aa, ab = _aim_of(pa), _aim_of(pb)
        if aa is not None or ab is not None:
            if aa is not None and ab is not None and aa[0] is not None and ab[0] is not None:
                d["aim"] = tuple(_slerp_dir(aa[0], ab[0], t))
                d["roll"] = aa[1] + (ab[1] - aa[1]) * t
            else:                                # one side at rest: resolved against the model later
                d["aim_pair"] = (aa, ab, t)
        out[bone] = d
    return out


def _aim_of(pb: Dict):
    if "aim" in pb:
        return (tuple(pb["aim"]), float(pb.get("roll", 0.0)))
    if "aim_pair" in pb:
        return None           # nested pairs are flattened by resolve(); treat as rest here
    return None


def _slerp_dir(a, b, t: float) -> np.ndarray:
    a = np.asarray(a, float); b = np.asarray(b, float)
    a = a / (np.linalg.norm(a) + 1e-12); b = b / (np.linalg.norm(b) + 1e-12)
    d = float(np.clip(a @ b, -1, 1))
    if d > 0.9995:
        v = a + (b - a) * t
    elif d < -0.9995:                         # opposite: swing through "up"
        up = np.array([0.0, 0.0, 1.0]) if abs(a[2]) < 0.9 else np.array([0.0, -1.0, 0.0])
        mid = up - a * (up @ a)
        mid /= np.linalg.norm(mid)
        return _slerp_dir(a, mid, t * 2) if t < 0.5 else _slerp_dir(mid, b, t * 2 - 1)
    else:
        th = math.acos(d)
        v = (math.sin((1 - t) * th) * a + math.sin(t * th) * b) / math.sin(th)
    return v / np.linalg.norm(v)


# ------------------------------------------------------------------ aim (resolved with the model)

def bone_axis(model, name: str) -> np.ndarray:
    """A bone's pointing axis in its own local space: joint -> centre of its parts (arms point down the
    limb, a sword along its blade, an axe toward its head)."""
    cache = model.__dict__.setdefault("_axis_cache", {})
    if name not in cache:
        from .render import _bounds
        b = model.bones[name]
        v = np.array([0.0, 0.0, -1.0])
        if b.parts:
            c, _ = _bounds(b.parts)
            if np.linalg.norm(c) > 0.5:
                v = c / np.linalg.norm(c)
        cache[name] = v
    return cache[name]


def _min_rot(u: np.ndarray, v: np.ndarray) -> np.ndarray:
    """Smallest rotation matrix taking unit u to unit v."""
    u = u / np.linalg.norm(u); v = v / np.linalg.norm(v)
    c = float(u @ v)
    ax = np.cross(u, v)
    s = float(np.linalg.norm(ax))
    if s < 1e-9:
        if c > 0:
            return np.eye(3)
        p = np.array([1.0, 0, 0]) if abs(u[0]) < 0.9 else np.array([0, 1.0, 0])
        ax = np.cross(u, p); ax /= np.linalg.norm(ax)
        return 2 * np.outer(ax, ax) - np.eye(3)
    ax /= s
    K_ = np.array([[0, -ax[2], ax[1]], [ax[2], 0, -ax[0]], [-ax[1], ax[0], 0]])
    ang = math.atan2(s, c)
    return np.eye(3) + math.sin(ang) * K_ + (1 - math.cos(ang)) * K_ @ K_


def _axis_rot(axis: np.ndarray, deg: float) -> np.ndarray:
    a = axis / np.linalg.norm(axis)
    K_ = np.array([[0, -a[2], a[1]], [a[2], 0, -a[0]], [-a[1], a[0], 0]])
    r = math.radians(deg)
    return np.eye(3) + math.sin(r) * K_ + (1 - math.cos(r)) * K_ @ K_


def resolve_aims(model, clip):
    """Turn pose "aim" entries into rotations. pose[bone]["aim"] = direction in the character's body frame
    (x right, y back, z up; the character faces -y), optional "roll" deg about that direction; the bone
    turns the least it can so its axis (bone_axis) points that way, under its parent's pose. Aims ride
    along with the root (a falling body keeps its limbs' aims relative to itself). Blends between an aim
    and a rest pose ("aim_pair") swing along the arc between the two directions."""
    for fr in clip.frames:
        if not any(("aim" in v or "aim_pair" in v) for v in fr.pose.values()):
            continue
        pose = {k: dict(v) for k, v in fr.pose.items()}
        W: Dict[str, np.ndarray] = {}
        rootW = None
        for nme in model.order:
            bone = model.bones[nme]
            d = pose.get(nme, {})
            L = _local_R(model, nme, pose)
            Wp = np.eye(3) if bone.parent is None else W[bone.parent]
            if "aim" in d or "aim_pair" in d:
                axis = bone_axis(model, nme)
                rest_dir = Wp @ L @ axis                       # where it points with its plain rot
                R_root = rootW if rootW is not None else np.eye(3)
                if "aim" in d:
                    want, roll = R_root @ np.asarray(d["aim"], float), float(d.get("roll", 0.0))
                else:
                    a, b, t = d["aim_pair"]
                    va = R_root @ np.asarray(a[0], float) if a else rest_dir
                    vb = R_root @ np.asarray(b[0], float) if b else rest_dir
                    want = _slerp_dir(va, vb, t)
                    roll = (a[1] if a else 0.0) * (1 - t) + (b[1] if b else 0.0) * t
                want = want / np.linalg.norm(want)
                Q = _min_rot(rest_dir, want)
                if roll:
                    Q = _axis_rot(want, roll) @ Q
                if "up" in d:
                    # "up": body-frame direction for the bone's local z (its long axis if the aim axis is not):
                    # twist about the aim so it points there (an upright bow whatever the arm does)
                    cur = Q @ Wp @ L @ np.array([0.0, 0.0, 1.0])
                    tgt = R_root @ np.asarray(d["up"], float)
                    cp = cur - want * float(cur @ want)
                    tp = tgt - want * float(tgt @ want)
                    if np.linalg.norm(cp) > 1e-6 and np.linalg.norm(tp) > 1e-6:
                        cp, tp = cp / np.linalg.norm(cp), tp / np.linalg.norm(tp)
                        ang = math.degrees(math.atan2(float(np.cross(cp, tp) @ want), float(cp @ tp)))
                        Q = _axis_rot(want, ang) @ Q
                L = Wp.T @ Q @ Wp @ L
                d = dict(d)
                d.pop("aim", None); d.pop("aim_pair", None); d.pop("roll", None); d.pop("up", None)
                d["rot"] = euler_from_matrix(rot_matrix(*bone.rot).T @ L)
                pose[nme] = d
            W[nme] = Wp @ L
            if bone.parent is None:
                rootW = W[nme]
        fr.pose = pose
    return clip


# ------------------------------------------------------------------ keyed clips

@dataclass
class Key:
    """A key pose at frame time t. `ease` shapes the segment that ARRIVES at this key."""
    t: float
    pose: Pose
    root: Tuple[float, float, float] = (0.0, 0.0, 0.0)
    squash: float = 1.0                      # vertical stretch (volume preserving)
    ease: str = "io"
    fx: List[Dict] = field(default_factory=list)
    event: Optional[str] = None
    hide: List[str] = field(default_factory=list)
    flash: bool = False


def sample(keys: Sequence[Key], n: int, loop: bool = False):
    """-> list of (pose, root, squash, key-or-None) for frames 0..n-1. A key's fx/event/hide/flash land on
    the frame at round(key.t). Loops wrap from the last key back to the first (first key at t=0)."""
    ks = sorted(keys, key=lambda k: k.t)
    if loop:
        k0 = ks[0]
        ks = ks + [Key(n + k0.t, k0.pose, k0.root, k0.squash, k0.ease)]
    out = []
    for i in range(n):
        t = float(i)
        if t <= ks[0].t:
            a = b = ks[0]
            u = 0.0
        elif t >= ks[-1].t:
            a = b = ks[-1]
            u = 0.0
        else:
            j = next(j for j in range(1, len(ks)) if ks[j].t >= t)
            a, b = ks[j - 1], ks[j]
            u = spacing(b.ease, (t - a.t) / max(1e-9, b.t - a.t))
        pose = mix(a.pose, b.pose, u)
        root = tuple(x + (y - x) * u for x, y in zip(a.root, b.root))
        sq = a.squash + (b.squash - a.squash) * u
        on = next((k for k in keys if int(math.floor(k.t + 0.5)) == i), None)
        out.append((pose, root, sq, on))
    return out


# ------------------------------------------------------------------ drag (post pass on any clip)

def _local_R(model, name: str, pose: Pose) -> np.ndarray:
    b = model.bones[name]
    return rot_matrix(*b.rot) @ rot_matrix(*pose.get(name, {}).get("rot", (0, 0, 0)))


def _world_rots(model, pose: Pose) -> Dict[str, np.ndarray]:
    W: Dict[str, np.ndarray] = {}
    for n in model.order:
        b = model.bones[n]
        L = _local_R(model, n, pose)
        W[n] = L if b.parent is None else W[b.parent] @ L
    return W


def drag(model, clip, lags: Dict[str, float], limit: float = 40.0):
    """Successive breaking of joints. lags = {bone: frames}; a bone's world rotation is its target world
    rotation from `lag` frames ago (fractional = slerp between neighbouring frames), re-expressed under
    its parent's ACTUAL (already dragged) rotation. Loops wrap; one-shot clips clamp at the first frame.
    The correction is capped at `limit` degrees so a fast swing lags without ever flipping."""
    frames = clip.frames
    n = len(frames)
    names = [b for b in model.order if lags.get(b, 0) > 0 and model.bones[b].parent is not None]
    if n < 2 or not names:
        return clip
    target = [_world_rots(model, f.pose) for f in frames]
    Q = {b: [quat_from_matrix(target[i][b]) for i in range(n)] for b in names}

    def delayed(b: str, i: int) -> np.ndarray:
        t = i - lags[b]
        if clip.loop:
            t %= n
        t = max(0.0, t)
        i0 = int(math.floor(t))
        i1 = (i0 + 1) % n if clip.loop else min(n - 1, i0 + 1)
        return slerp(Q[b][i0 % n], Q[b][i1], t - i0)

    for i, fr in enumerate(frames):
        if fr.event == "hit":
            continue                     # the strike lands exactly: the snap frame does the full motion
        pose = {k: dict(v) for k, v in fr.pose.items()}
        actual: Dict[str, np.ndarray] = {}
        for nme in model.order:
            bone = model.bones[nme]
            if nme in lags and nme in names:
                Wt = matrix_from_quat(delayed(nme, i))
                Pw = actual[bone.parent]
                L = Pw.T @ Wt                                    # desired local (rest @ pose)
                Rp = rot_matrix(*bone.rot).T @ L                 # desired pose rotation
                # cap the change vs the undragged pose rotation
                R0 = rot_matrix(*pose.get(nme, {}).get("rot", (0, 0, 0)))
                dq = quat_from_matrix(R0.T @ Rp)
                ang = 2 * math.degrees(math.acos(min(1.0, abs(float(dq[0])))))
                if ang > limit:
                    Rp = R0 @ matrix_from_quat(slerp(np.array([1.0, 0, 0, 0]), dq, limit / ang))
                d = pose.setdefault(nme, {})
                d["rot"] = euler_from_matrix(Rp)
            L = _local_R(model, nme, pose)
            actual[nme] = L if bone.parent is None else actual[bone.parent] @ L
        fr.pose = pose
    return clip


# ------------------------------------------------------------------ swept smear

def blade_span(model, name: str) -> Tuple[np.ndarray, np.ndarray]:
    """(near, far) points of a bone along its axis, in bone space: grip end and tip of a weapon."""
    cache = model.__dict__.setdefault("_span_cache", {})
    if name not in cache:
        ax = bone_axis(model, name)
        ts = [0.0]
        for p in model.bones[name].parts:
            at = np.asarray(p.get("at", (0, 0, 0)), float)
            cand = [at]
            if p["shape"] == "capsule":
                cand += [at + np.asarray(p.get("a", (0, 0, 0)), float), at + np.asarray(p["b"], float)]
            elif p["shape"] == "box":
                h = np.asarray(p["half"], float)
                cand += [at + ax * float(np.abs(h) @ np.abs(ax)), at - ax * float(np.abs(h) @ np.abs(ax))]
            else:
                r = p.get("r", p.get("R", 1.0))
                e = float(np.max(r)) if not isinstance(r, (int, float)) else float(r)
                cand += [at + ax * e, at - ax * e]
            ts += [float(c @ ax) for c in cand]
        cache[name] = (ax * max(0.0, min(ts)), ax * max(ts))
    return cache[name]


def sweep_mask(model, pose0: Pose, root0, pose1: Pose, root1, bone: str, facing_yaw: float, size, anchor,
               depth: Optional[np.ndarray] = None, thick: float = 1.0, squash=(1.0, 1.0), widen: float = 1.0,
               dashed: bool = False) -> np.ndarray:
    """Pixels swept by a bone's grip->tip segment moving from pose0 to pose1 along the rotation arcs
    (the smear follows the real attack path). Crescent-shaped: only the outer part near the ends, the whole
    blade in the middle. `thick` < 1 keeps only the outer fraction (tails)."""
    from PIL import Image, ImageDraw
    from .render import K, RAY
    W_, H_ = size
    ss = 4
    img = Image.new("L", (W_ * ss, H_ * ss), 0)
    dr = ImageDraw.Draw(img)
    near, far = blade_span(model, bone)
    steps = 20
    pts = []
    for k in range(steps + 1):
        u = k / steps
        pose = mix(pose0, pose1, u)
        ro = np.asarray(root0, float) + (np.asarray(root1, float) - np.asarray(root0, float)) * u
        Mw, o = model.world(pose, facing_yaw, squash, widen)[bone]
        Rf = rot_matrix(0, 0, facing_yaw)
        o = o + Rf @ ro
        env = math.sin(math.pi * min(1.0, u * 1.1)) ** 0.7 if u < 0.9 else 0.35 * (1 - u) / 0.1
        s0 = 1.0 - max(0.12, 0.62 * thick * env)            # inner edge: fraction along grip -> tip
        a = o + Mw @ (near + (far - near) * s0)
        b = o + Mw @ far
        pts.append((a, b))
    scr = lambda q: ((anchor[0] + q[0]) * ss, (anchor[1] - (q[2] + K * q[1])) * ss)
    area = 0.0
    for k in range(steps):
        quad = [scr(pts[k][0]), scr(pts[k][1]), scr(pts[k + 1][1]), scr(pts[k + 1][0])]
        area += abs(sum(x0 * y1 - x1 * y0 for (x0, y0), (x1, y1) in zip(quad, quad[1:] + quad[:1]))) / 2
        if dashed and (k * 5 // steps) % 2 == 1:
            continue
        dr.polygon(quad, fill=255)
    if area < 2.0 * ss * ss:
        # a thrust or a loosed arrow moves along its own axis: no arc to fill, so draw the straight streak
        # its tip travels (thicker at the head, thinning back toward the start; `thick` < 1 = a thin tail)
        a0, a1 = scr(pts[0][1]), scr(pts[-1][1])
        n = 8
        for k in range(n):
            if dashed and k % 2 == 1:
                continue
            u0, u1 = k / n, (k + 1) / n
            w = ss * (1.4 + 2.2 * u1) * (0.5 if thick < 1 else 1.0)      # a comet: 3-4 px at the head
            p0 = (a0[0] + (a1[0] - a0[0]) * u0, a0[1] + (a1[1] - a0[1]) * u0)
            p1 = (a0[0] + (a1[0] - a0[0]) * u1, a0[1] + (a1[1] - a0[1]) * u1)
            dr.line([p0, p1], fill=255, width=max(1, int(round(w))))
    m = np.asarray(img, np.float32).reshape(H_, ss, W_, ss).mean(axis=(1, 3)) > 110
    return m


# ------------------------------------------------------------------ pixel stability

def _reach(model, name: str) -> float:
    """How far (px) a bone's parts reach from its joint: converts an angle change into tip travel."""
    cache = model.__dict__.setdefault("_reach_cache", {})
    if name not in cache:
        near, far = blade_span(model, name)
        from .render import _bounds
        b = model.bones[name]
        r = 0.0
        if b.parts:
            c, rad = _bounds(b.parts)
            r = float(np.linalg.norm(c)) + rad - 1.0
        cache[name] = max(float(np.linalg.norm(far)), r, 1.0)
    return cache[name]


def stabilize(model, clip, px: float = 0.6, skip=()):
    """Hold-then-step for every bone: keep a bone's previous rotation until the new one would move its
    farthest point by >= px pixels. Tiny drifts stop re-rasterising parts (no boiling / swimming pixels)
    and 1-frame +-jitters collapse into holds; real motion is untouched. Loops settle over two passes so
    the seam matches."""
    frames = clip.frames
    n = len(frames)
    if n < 2:
        return clip
    names = [b for b in model.order if b not in skip and any("rot" in f.pose.get(b, {}) for f in frames)]
    for b in names:
        reach = _reach(model, b)
        rots = [np.asarray(f.pose.get(b, {}).get("rot", (0, 0, 0)), float) for f in frames]
        Rs = [rot_matrix(*r) for r in rots]
        held = 0
        out = list(range(n))
        passes = 2 if clip.loop else 1
        for ps in range(passes):
            for i in range(n):
                if (ps == 0 and i == 0) or frames[i].event == "hit":
                    held = i
                else:
                    Rd = Rs[held].T @ Rs[i]
                    ang = math.acos(max(-1.0, min(1.0, (np.trace(Rd) - 1) / 2)))
                    if ang * reach >= px:
                        held = i
                out[i] = held
        for i, f in enumerate(frames):
            if out[i] != i:
                d = dict(f.pose.get(b, {}))
                d["rot"] = tuple(float(v) for v in rots[out[i]])
                f.pose = dict(f.pose)
                f.pose[b] = d
    return clip


# ------------------------------------------------------------------ knees

KNEE = 0.46          # the knee sits 46 % of the way from hip to floor


def add_knees(spec: Dict) -> Dict:
    """Split each humanoid leg bone into thigh + shin ("shinL"/"shinR") at the knee, so walks can fold the
    shin instead of lifting a rigid leg. Capsules crossing the knee are cut in two (radius interpolated),
    other parts go to whichever side their centre is on. Specs that already have shins, set
    "knees": false, or have no capsule leg are left alone. Returns a new spec."""
    if spec.get("knees") is False or spec.get("rig", "humanoid") != "humanoid":
        return spec
    names = {b["name"] for b in spec.get("bones", [])}
    out = []
    for b in spec.get("bones", []):
        out.append(b)
        side = {"legL": "shinL", "legR": "shinR"}.get(b["name"])
        if not side or side in names:
            continue
        parts = [p for p in b.get("parts", []) if p.get("shape") not in STAMP_SHAPES]
        caps = [p for p in parts if p["shape"] == "capsule"]
        if not caps:
            continue
        # leg run: joint -> lowest point of the leg's parts
        low = 0.0
        for p in parts:
            at = np.asarray(p.get("at", (0, 0, 0)), float)
            if p["shape"] == "capsule":
                for e in ("a", "b"):
                    v = at + np.asarray(p.get(e, (0, 0, 0)), float)
                    low = min(low, v[2] - p.get("r2" if e == "b" else "r1", p.get("r", 1.0)))
            else:
                r = p.get("r", p.get("half", 1.0))
                rz = float(r[2]) if isinstance(r, (list, tuple)) else float(r)
                low = min(low, at[2] - rz)
        kz = KNEE * low                                    # negative: below the hip joint
        main = max(caps, key=lambda p: abs(p.get("b", (0, 0, 0))[2] - p.get("a", (0, 0, 0))[2]))
        at = np.asarray(main.get("at", (0, 0, 0)), float)
        a = at + np.asarray(main.get("a", (0, 0, 0)), float)
        e = at + np.asarray(main["b"], float)
        if not (min(a[2], e[2]) < kz < max(a[2], e[2])):
            continue
        u = (kz - a[2]) / (e[2] - a[2])
        knee = a + (e - a) * u
        r1, r2 = main.get("r1", main.get("r", 1.0)), main.get("r2", main.get("r", 1.0))
        rk = r1 + (r2 - r1) * u
        thigh, shin = [], []
        for p in b.get("parts", []):
            if p is main:
                q = {k: v for k, v in p.items() if k not in ("at", "a", "b", "r", "r1", "r2")}
                thigh.append({**q, "a": list(a), "b": list(knee), "r1": r1, "r2": rk})
                shin.append({**q, "a": [0, 0, 0], "b": list(e - knee), "r1": rk, "r2": r2})
                continue
            c = np.asarray(p.get("at", (0, 0, 0)), float)
            if p["shape"] == "capsule":
                c = c + (np.asarray(p.get("a", (0, 0, 0)), float) + np.asarray(p["b"], float)) / 2
            if c[2] < kz:
                shin.append({**p, "at": list(np.asarray(p.get("at", (0, 0, 0)), float) - knee)})
            else:
                thigh.append(p)
        b2 = dict(b)
        b2["parts"] = thigh
        out[-1] = b2
        out.append({"name": side, "parent": b["name"], "at": [float(v) for v in knee], "parts": shin})
    spec = dict(spec)
    spec["bones"] = out
    return spec


def leg_ik(fwd: float, up: float, thigh: float, shin: float) -> Tuple[float, float]:
    """Two-bone leg in the sagittal plane. Foot target relative to the hip joint: `fwd` px ahead, `up` px
    above the hip (negative = below). -> (thigh rot x, shin rot x) in degrees, rig convention (rx < 0 swings
    forward); the knee always bends forward. Out-of-reach targets straighten the leg toward them."""
    d = math.hypot(fwd, up)
    d = max(1e-6, min(d, (thigh + shin) * 0.9999, ))
    d = max(d, abs(thigh - shin) + 1e-6)
    aim = math.atan2(fwd, -up)                                   # from straight down, forward positive
    cos_b = (thigh * thigh + d * d - shin * shin) / (2 * thigh * d)
    beta = math.acos(max(-1.0, min(1.0, cos_b)))
    cos_k = (thigh * thigh + shin * shin - d * d) / (2 * thigh * shin)
    flex = math.pi - math.acos(max(-1.0, min(1.0, cos_k)))
    return -math.degrees(aim + beta), math.degrees(flex)


def _sole(model, pose: Pose, leg: str, shin: Optional[str]) -> Tuple[float, float]:
    """(forward, z) of the lowest point of a leg's lowest segment, body frame (yaw 0, no root motion)."""
    w = model.world(pose, 0.0)
    name = shin or leg
    M_, o = w[name]
    best = (0.0, 1e9)
    for p in model.bones[name].parts:
        at = np.asarray(p.get("at", (0, 0, 0)), float)
        cands = []
        if p["shape"] == "capsule":
            for e, rk in (("a", "r1"), ("b", "r2")):
                cands.append((o + M_ @ (at + np.asarray(p.get(e, (0, 0, 0)), float)), p.get(rk, p.get("r", 1.0))))
        else:
            r = p.get("r", p.get("half", 1.0))
            rz = float(r[2]) if isinstance(r, (list, tuple)) else float(r)
            cands.append((o + M_ @ at, rz))
        for q, rz in cands:
            if q[2] - rz < best[1]:
                best = (-float(q[1]), float(q[2] - rz))
    return best


def resolve_feet(model, clip):
    """Turn "foot": (forward, lift) targets on legL/legR (px, body frame; forward from the standing foot,
    lift above the ground) into leg rotations: two-bone IK when the leg has a shin, then a few corrections
    so the lowest point of the real geometry (boot, hoof) sits exactly `lift` above where it stands at
    rest. Planted feet therefore touch the ground on every frame and slide back only as the stride says."""
    cache = model.__dict__.setdefault("_legs_rest", {})
    for fr in clip.frames:
        if not any("foot" in fr.pose.get(l, {}) for l in ("legL", "legR")):
            continue
        pose = {k: dict(v) for k, v in fr.pose.items()}
        for leg, shin in (("legL", "shinL"), ("legR", "shinR")):
            d = pose.get(leg, {})
            if "foot" not in d or leg not in model.bones:
                continue
            fwd, lift = d.pop("foot")
            shin = shin if shin in model.bones else None
            if leg not in cache:
                w0 = model.world({}, 0.0)
                hip0 = w0[leg][1]
                th = float(np.linalg.norm(w0[shin][1] - hip0)) if shin else float(hip0[2])
                sh = float(w0[shin][1][2]) if shin else 0.0
                cache[leg] = (hip0, th, sh, _sole(model, {}, leg, shin))
            hip0, th, sh, (sf0, sz0) = cache[leg]
            ez = 0.0
            for _ in range(4):
                w = model.world(pose, 0.0)
                P, o = w[model.bones[leg].parent]
                hip = w[leg][1]
                # target for the chain end (ankle over the ground point), in the leg parent's frame
                tgt = np.array([hip0[0], hip0[1] - fwd, lift + ez])
                v = P.T @ (tgt - hip)
                if shin:
                    a, k = leg_ik(-v[1], v[2], th, sh)
                    d["rot"] = (a, 0.0, 0.0)
                    pose[shin] = {**pose.get(shin, {}), "rot": (k, 0.0, 0.0)}
                else:
                    L = max(1e-6, math.hypot(v[1], v[2]))
                    d["rot"] = (-math.degrees(math.atan2(-v[1], -v[2])), 0.0, 0.0)
                    d["at"] = (0.0, 0.0, float(math.floor(float(hip0[2]) - L + 0.5)))
                pose[leg] = d
                sole_z = _sole(model, pose, leg, shin)[1]
                err = (sz0 + lift) - sole_z
                if abs(err) < 0.15:
                    break
                ez += err
        fr.pose = pose
    return clip


# ------------------------------------------------------------------ limited animation (stop-motion timing)

def _pose_points(model, fr) -> np.ndarray:
    """Every bone's joint and part centre in px (body frame, squash applied): what the eye tracks."""
    from .render import _bounds
    w = model.world(fr.pose, 0.0, fr.squash)
    root = np.asarray(fr.root, float)
    pts = []
    for name, (Mb, o) in w.items():
        pts.append(o + root)
        parts = model.bones[name].parts
        if parts:
            pts.append(o + Mb @ _bounds(parts)[0] + root)
    return np.asarray(pts)


def _must_key(fr) -> bool:
    return bool(fr.event in ("hit", "cast", "hurt") or fr.flash or fr.hide
                or any(x.get("kind") in ("sweep", "smear", "burst") for x in fr.fx))


def limit(model, clip, on: float = 2, min_px: float = 0.75):
    """Limited animation: show fewer, stronger poses and hold each one (Guilty Gear Xrd / anime "on twos":
    no in-between the eye can't read; fast parts on ones, slow parts on threes and fours).
    Loops step uniformly on `on`s (phase stays symmetric: left and right steps get the same poses).
    One-shots keep their event/smear/flash frames, the first and last frame, then greedily add the frame
    that strays farthest (px) from the straight path between the poses already kept (Douglas-Peucker on
    the pose trajectory = the extremes and breakdowns), up to len/on poses. Every other frame holds the
    last kept pose; its own fx and events stay. Total length never changes."""
    fr = clip.frames
    n = len(fr)
    if on <= 1 or n < 3:
        return clip
    must = {0} | {i for i, f in enumerate(fr) if _must_key(f) or getattr(f, "key", False)}
    if clip.loop:
        step = max(1, int(round(on)))
        keep = sorted(must | set(range(0, n, step)))
    else:
        must.add(n - 1)
        P = [_pose_points(model, f) for f in fr]
        budget = max(len(must), int(math.ceil(n / on)))
        keep = set(must)
        while len(keep) < budget:
            ks = sorted(keep)
            best, err = None, min_px
            for a, b in zip(ks, ks[1:]):
                for i in range(a + 1, b):
                    u = (i - a) / (b - a)
                    e = float(np.max(np.linalg.norm(P[i] - (P[a] + (P[b] - P[a]) * u), axis=1)))
                    if e > err:
                        best, err = i, e
            if best is None:
                break
            keep.add(best)
        keep = sorted(keep)
    src, j = [], 0
    for i in range(n):
        while j + 1 < len(keep) and keep[j + 1] <= i:
            j += 1
        src.append(keep[j])
    out = []
    for i, f in enumerate(fr):
        s = fr[src[i]]
        out.append(f if s is f else replace(f, pose=s.pose, root=s.root, squash=s.squash, hide=list(s.hide),
                                                   show=list(getattr(s, "show", []))))
    return replace(clip, frames=out)

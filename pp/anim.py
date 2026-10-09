"""Animation clips, timed the pixel-art way.

ONE frame duration for everything (~75 ms); holds are made by repeating a frame,
never by longer frames.

A clip is a list of Frame(pose, ...). Poses map bone -> {rot, at, scale, aim, roll}.
Conventions (model faces -Y = south): rx<0 swings a hanging limb forward,
rz>0 turns counter-clockwise seen from above, z is up. "aim" points a bone (arm, weapon) along a
body-frame direction and is resolved against the model by the forge (pp/motion.py).

Motion principles (research/motion/NOTES.md): pose-to-pose with held extremes and 0-1 in-betweens in the
fast part; the strike frame does the whole arc; rotations blend along arcs; walks keep the planted foot
locked to the ground and fold the shin (auto knees) instead of lifting the leg; deaths buckle, then fall
with gravity spacing and land limbs late.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field, replace
from typing import Callable, Dict, List, Optional, Tuple

from . import motion as M

Pose = Dict[str, Dict]
FRAME_MS = 75


@dataclass
class Frame:
    pose: Pose
    ms: int = FRAME_MS
    root: tuple = (0.0, 0.0, 0.0)          # whole-body offset in the character's frame (y<0 = forward)
    squash: Tuple[float, float] = (1.0, 1.0)  # (horizontal, vertical) about the feet
    flash: bool = False                     # flat silhouette in the flash colour
    fx: List[Dict] = field(default_factory=list)
    event: Optional[str] = None             # gameplay marker: "hit", "footstep", "cast"...
    hide: List[str] = field(default_factory=list)
    away: bool = False                      # fall away from the camera: mirror front/back motion in N-ish facings
    key: bool = False                       # a designed key pose: limited animation keeps and holds it
    show: List[str] = field(default_factory=list)   # bones marked "hidden" in the spec that this frame shows


@dataclass
class Clip:
    name: str
    frames: List[Frame]
    loop: bool = True
    speed_px: float = 0.0          # locomotion: ground px travelled per full cycle


# ------------------------------------------------------------------ helpers

def ease_out(t: float) -> float:
    return 1 - (1 - t) ** 3


def ease_in(t: float) -> float:
    return t ** 3


def ease_io(t: float) -> float:
    return 3 * t * t - 2 * t * t * t


def mix_pose(a: Pose, b: Pose, t: float) -> Pose:
    """Blend two poses; rotations travel along their arc (slerp), not per Euler axis."""
    return M.mix(a, b, t)


def merge(*poses: Pose) -> Pose:
    """Additive merge (rot/at add, scale multiplies; aim/roll are directions, so the later one wins)."""
    out: Pose = {}
    for p in poses:
        for bone, d in p.items():
            o = out.setdefault(bone, {})
            for k, v in d.items():
                if k in ("aim", "roll", "aim_pair", "foot"):
                    o[k] = v
                elif k == "scale":
                    o[k] = tuple(x * y for x, y in zip(o.get(k, (1, 1, 1)), v))
                else:
                    o[k] = tuple(x + y for x, y in zip(o.get(k, (0, 0, 0)), v))
    return out


def lerp(a, b, t):
    if isinstance(a, tuple):
        return tuple(x + (y - x) * t for x, y in zip(a, b))
    return a + (b - a) * t


def stretch(v: float) -> Tuple[float, float]:
    """Volume-preserving squash/stretch: vertical v, horizontal 1/sqrt(v)."""
    return (1 / math.sqrt(v), v)


def snap(v: float) -> float:
    return float(math.floor(v + 0.5))


def hitstop(clip: Clip, n: int) -> Clip:
    """Freeze the impact for n frames (Sakurai: both sides freeze and shudder). The smear is solid on ONE
    frame (R21): the first freeze shows its tail, later ones none. The weapon reappears frozen at the end of
    its swing, and the body shudders +-1 px sideways (decaying). vfx/dust play once, on the original."""
    if n <= 0:
        return clip
    out: List[Frame] = []
    for f in clip.frames:
        out.append(f)
        if f.event == "hit":
            for k in range(n):
                fx = [{**x, "arc": "tail"} for x in f.fx if x.get("kind") == "smear" and x.get("arc") == "wide"]
                fx += [{**x, "tail": True} for x in f.fx if x.get("kind") == "sweep" and not x.get("tail")]
                shake = (1 if k % 2 == 0 else -1) if k < 2 else 0
                out.append(replace(f, fx=fx if k == 0 else [], event=None, hide=[],
                                   root=(f.root[0] + shake, f.root[1], f.root[2])))
    return replace(clip, frames=out)


def hold(f: Frame, n: int) -> List[Frame]:
    return [replace(f, fx=list(f.fx), event=f.event if i == 0 else None) for i in range(n)]


# ------------------------------------------------------------------ humanoid
# Rig: root > hips > torso > head ; torso > armL, armR ; hips > legL, legR.
# Optional prop bones (cape/scarf/hair/tail/ears) listed in anim.props swing at 2x.

def _prop_pose(p: Dict, dz: float, sway: float = 0.0) -> Pose:
    """Props trail the body: callers pass the PREVIOUS frame's bob (1-frame lag). When follow-through springs
    are on (the default, pp/secondary.py) they add the overshoot, so the in-phase part is kept small."""
    k = 1.0 if p.get("follow") == {} else 0.6
    out: Pose = {}
    for b in p.get("props", []):
        out[b] = {"rot": (k * (p.get("prop_swing", 10) * dz + sway), 0, 0)}
    return out


def held(clip: Clip, n: int) -> Clip:
    """Slow a clip down the pixel-art way: every frame held n times (one frame duration everywhere)."""
    if n <= 1:
        return clip
    return replace(clip, frames=[g for f in clip.frames for g in hold(f, n)])


def humanoid_idle(p: Dict) -> Clip:
    """Poses, each held idle_hold (2) frames: 16 frames = a 1.2 s breath (8 at 75 ms read frantic).
    Body 2 px bob in 1 px steps, head 2 poses behind, props 2x, feet fixed.
    idle_style "float": the whole body drifts up and down off the ground, legs dangle, arms drift."""
    if p.get("idle_style") == "float":
        return _hovered(held(_float_idle(p), p.get("idle_hold", 2)), p)
    amp = p.get("idle_bob", 2)
    body = [round(v * amp / 2) for v in (0, 1, 1, 2, 2, 1, 1, 0)]   # px down (breathe out)
    frames = []
    for i in range(8):
        b = body[i]
        h = body[(i - 2) % 8]
        arm = p.get("idle_arm", 4) * b / max(1, amp)
        pose = merge({
            "torso": {"at": (0, 0, -b)},
            "head": {"at": (0, 0, -(h - b))},
            "armL": {"rot": (0, -arm, 0)}, "armR": {"rot": (0, arm, 0)},
            "foreL": {"rot": (-8 - 2 * b, 0, 0)}, "foreR": {"rot": (-8 - 2 * b, 0, 0)},
        }, _prop_pose(p, body[(i - 1) % 8]))
        frames.append(Frame(pose))
    return _hovered(held(Clip("idle", frames), p.get("idle_hold", 2)), p)


def _float_idle(p: Dict) -> Clip:
    amp = p.get("float_bob", 2)
    up = [round(v * amp / 2) for v in (0, 1, 1, 2, 2, 1, 1, 0)]
    frames = []
    for i in range(8):
        u, lag = up[i], up[(i - 2) % 8]
        d = 3 * math.sin(2 * math.pi * (i - 2) / 8)            # legs dangle a beat behind the body
        pose = merge({
            "head": {"at": (0, 0, lag - u)},
            "armL": {"rot": (0, -3 - 3 * u, 0)}, "armR": {"rot": (0, 3 + 3 * u, 0)},
            "foreL": {"rot": (-10 - 3 * u, 0, 0)}, "foreR": {"rot": (-10 - 3 * u, 0, 0)},
            "legL": {"rot": (d, 0, 0)}, "legR": {"rot": (-d, 0, 0)},
        }, _prop_pose(p, lag - u))
        frames.append(Frame(pose, root=(0, 0, u)))
    return Clip("idle", frames)


def _hovered(clip: Clip, p: Dict, ground_from: Optional[int] = None) -> Clip:
    """anim.hover: the body floats this many px off the ground (shadow stays down). A death drops to the
    ground from frame `ground_from`."""
    h = p.get("hover", 0)
    if not h:
        return clip
    for i, f in enumerate(clip.frames):
        k = 1.0 if ground_from is None else max(0.0, 1.0 - i / max(1, ground_from))
        f.root = (f.root[0], f.root[1], f.root[2] + snap(h * k))
    return clip


# ------------------------------------------------------------------ gaits
# anim.gait picks the family's way of moving: "stride" (default), "hop" (both feet, off the ground),
# "lurch" (heavy, swaying, bent forward), "bounce" (springy, squash on every step), "glide" (low, level, still arms).

def humanoid_walk(p: Dict) -> Clip:
    g = p.get("gait", "stride")
    if g == "hop":
        return _hovered(_hop(p, run=False), p)
    return _hovered(_stride_walk(p, g), p)


def _hop(p: Dict, run: bool) -> Clip:
    """Two hops per cycle, 4 frames each: land (squash) -> push (stretch) -> apex (legs tucked) -> fall
    (legs reach). Legs move together with a small offset so the pair doesn't read as one block."""
    hh = p.get("run_hop" if run else "walk_hop", 5 if run else 3)
    z = [0, snap(hh * 0.6), hh, snap(hh * 0.6)]
    sq = [0.84, 1.14, 1.04, 1.0] if run else [0.88, 1.1, 1.02, 1.0]
    k = 1.5 if run else 1.0
    leg = [0, 18 * k, 8 * k, -14 * k]                       # +x = trails back, -x = reaches forward
    arm = [-8, 14 * k, 26 * k, 8 * k] if run else [-6, -10, -22, -10]
    lean = -12 if run else -4
    frames = []
    for i in range(8):
        j, side = i % 4, (1 if i < 4 else -1)
        dz_prev = z[j] - z[(j - 1) % 4]
        pose = merge({
            "torso": {"rot": (lean + (5 if j == 0 else -3 if j == 2 else 0), 0, 3 * side)},
            "head": {"at": (0, 0, -max(-1, min(1, dz_prev))), "rot": (4 if j == 0 else -2, 0, 0)},
            "legL": {"rot": (leg[j] + 4 * side, 0, 0)}, "legR": {"rot": (leg[j] - 4 * side, 0, 0)},
            "armL": {"rot": ((arm[j], 0, 0) if run else (0, arm[j], 0))},
            "armR": {"rot": ((arm[j], 0, 0) if run else (0, -arm[j], 0))},
            "foreL": {"rot": (-20, 0, 0)}, "foreR": {"rot": (-20, 0, 0)},
        }, _prop_pose(p, -dz_prev, sway=6 if j else -6))
        land = j == 0
        frames.append(Frame(pose, root=(0, 0, z[j]), squash=stretch(sq[j]),
                            fx=[{"kind": "dust", "n": 2 if run else 1}] if land else [],
                            event="footstep" if land else None))
    if not run:              # a walking hop settles: hold the landing squash and the apex (12 frames, 0.9 s)
        frames = [g for i, f in enumerate(frames) for g in (hold(f, 2) if i % 4 in (0, 2) else [f])]
    return Clip("run" if run else "walk", frames,
                speed_px=p.get("stride_px", 16 if run else 10) * 2)


def _weapon_lag(p: Dict, arm_rot_x: float) -> Pose:
    """A hand-held weapon follows its hand but keeps ~70 % of its own heading (no metronome swing)."""
    return {w: {"rot": (-0.7 * arm_rot_x, 0, 0)} for w in p.get("smear_hides", ["sword", "weapon"])}


# Foot schedules (after Williams). x = fraction of the stride reach, + toward the
# heading; lift = fraction of the leg's height. Stance is 5 of 8 frames and moves back evenly (the planted
# foot is locked to the ground); the swing lifts most at the PASS, under the hip, where the shin folds.
# (lifts of 0.30 / 0.54 / 0.18 are fractions of the leg left under a coat; our legs show whole,
# so the same clearance is a smaller fraction: heel peel, pass, reach.)
WALK_FOOT = ((1, 0), (0.5, 0), (0, 0), (-0.5, 0), (-1, 0), (-0.55, 0.22), (0, 0.48), (0.7, 0.16))
# body drop per step frame (contact, down, pass, up) by bob size: lowest one frame AFTER contact (the knee
# absorbs the landing), highest at the pass. A crown of 1,0,2,1 is the 2 px row; short legs get 1 px.
WALK_DROP = {1: (1, 1, 0, 0), 2: (1, 2, 0, 1), 3: (2, 3, 0, 1)}
# run (saint11 RunCycle, 4 keys per step): contact (foot lands ahead) / down (lowest, stance knee bent) /
# push-off (rear leg long behind, the other knee driven high) / flight (highest, both feet off, legs split).
# Stance 3 of 8; the swing heel kicks up behind the hip, then the knee drives forward and high.
RUN_FOOT = ((1, 0), (0, 0), (-1, 0), (-0.75, 0.62), (-0.05, 0.95), (0.6, 0.8), (0.95, 0.42), (1.05, 0.16))
RUN_RISE = (0, -1, 1, 2)                 # contact, down (lowest), push-off, flight (highest)
RUN_SQUASH = (0.96, 0.9, 1.08, 1.04)


def _legs(p: Dict, foot_l, foot_r, reach: float) -> Pose:
    """Foot targets (x * reach ahead, lift * leg height up); the forge solves them against the real leg
    geometry (motion.resolve_feet: two-bone IK on the auto knees, sole pinned to the ground)."""
    H = p.get("leg_len", 5.0)
    return {leg: {"foot": (x * reach, lift * H)} for leg, (x, lift) in (("legL", foot_l), ("legR", foot_r))}


def _stride_walk(p: Dict, g: str) -> Clip:
    """8 frames on WALK_FOOT / WALK_DROP: contact 0/4, down 1/5, pass 2/6, up 3/7. The planted foot slides
    back one even step per frame, so speed_px matches the feet exactly. Arms swing with the opposite foot,
    the head bobs a frame behind the body. Gaits: lurch (bent, heavy dip, hip sway, dust on each step),
    bounce (bigger bob, squash on the down frame), glide (low, short steps, feet barely lift, arms still)."""
    n = int(p.get("walk_frames", 16))          # 16 x 75 ms = 1.2 s per cycle, ~1.7 steps/s: a walk, not a run
    lurch, bounce, glide = g == "lurch", g == "bounce", g == "glide"
    H = p.get("leg_len", 5.0)
    reach = H * math.sin(math.radians(p.get("walk_leg", 30) * (0.7 if glide else 1.0)))

    def at(table, t):                          # table sampled at key time t (0..8, cyclic), linear between keys
        i0 = int(math.floor(t)) % 8
        u = t - math.floor(t)
        a_, b_ = table[i0], table[(i0 + 1) % 8]
        return tuple(x + (y - x) * u for x, y in zip(a_, b_))
    lift_k = 0.45 if glide else 1.0
    arm_a = p.get("walk_arm", 28) * (0.25 if glide else 0.55 if lurch else 1.3 if bounce else 1.0)
    bob = int(p.get("walk_bob", (1 if H < 6.5 else 2) + (1 if bounce or lurch else 0)))   # the dip bends the knees
    drop = WALK_DROP[max(1, min(3, bob))]
    # rx > 0 tips the torso forward. Pelvis: yaws with the forward leg, rolls down on the swing side, shifts
    # over the planted foot; the shoulders counter-rotate (left shoulder back while the left leg is forward)
    lean = p.get("walk_lean", 6 if lurch else 5 if glide else 2)
    twist = 0 if glide else 7 if lurch else 5
    yaw = 3 if glide else 8 if lurch else 6
    roll = 2 if glide else 5 if lurch else 3
    shift = p.get("walk_sway", 1.6 if lurch else 1.0)
    base = -1 if (lurch or glide) else 0                 # knees kept bent
    def dz(i):
        t = (i % n) * 8 / n
        d = drop[int(t) % 4] + (drop[(int(t) + 1) % 4] - drop[int(t) % 4]) * (t - int(t))
        return base - float(math.floor(d + 0.25))       # half-way values stay on the earlier key (held)
    frames = []
    for i in range(n):
        t = i * 8 / n
        (xl, ll), (xr, lr) = at(WALK_FOOT, t), at(WALK_FOOT, t + 4)
        h, hp = dz(i), dz(i - 1)
        w = max(-1.0, min(1.0, (ll - lr) / 0.48))          # +1: left leg swinging (right planted)
        sway = snap(shift * w)                               # hips over the planted foot
        pose = merge({
            "hips": {"at": (sway, 0, h), "rot": (0, -roll * w, yaw * xl)},
            "torso": {"rot": (lean, 0, -(twist + yaw) * xl)},
            "head": {"at": (0, 0, max(-1, min(1, hp - h))), "rot": (4 if lurch else 0, 0, twist * 0.8 * xl)},
            "armL": {"rot": (arm_a * xl - (10 if lurch else 0), 0, 0)},
            "armR": {"rot": (arm_a * xr - (10 if lurch else 0), 0, 0)},
            "foreL": {"rot": (-14 - 12 * max(0, -xl), 0, 0)}, "foreR": {"rot": (-14 - 12 * max(0, -xr), 0, 0)},
        }, _legs(p, (xl, ll * lift_k), (xr, lr * lift_k), reach),
            _weapon_lag(p, arm_a * xr), _prop_pose(p, hp - h, sway=12 if glide else 6))
        k4 = int(t) % 4                                  # which key of the step: contact, down, pass, up
        step = t % 4 == 0
        sq = (1.0, 1.0)
        if bounce:
            sq = stretch(0.92 if k4 == 1 else 1.05 if k4 == 2 else 1.0)
        elif lurch and k4 == 1 and t == int(t):
            sq = stretch(0.95)                                # the heavy foot lands
        frames.append(Frame(pose, squash=sq, event="footstep" if step else None,
                            fx=[{"kind": "dust", "n": 1}] if lurch and step else []))
    return Clip("walk", frames, speed_px=round(4 * reach, 2))


def humanoid_run(p: Dict) -> Clip:
    """8 frames = 2 strides x 4; body bounce 0/3/4/3 (scaled), height 0.93-1.1.
    Gaits: hop = bounding hops, lurch = low heavy charge, bounce = springy, glide = low dash, arms trailing."""
    g = p.get("gait", "stride")
    if g == "hop":
        return _hovered(_hop(p, run=True), p)
    return _hovered(_stride_run(p, g), p)


def _stride_run(p: Dict, g: str) -> Clip:
    """8 frames on RUN_FOOT / RUN_RISE: contact, mid stance (lowest, squash), push-off, flight (highest,
    both feet up), per step. Body leans and leads with the chest; arms pump with the opposite foot."""
    lurch, springy, glide = g == "lurch", g == "bounce", g == "glide"
    H = p.get("leg_len", 5.0)
    reach = H * math.sin(math.radians(p.get("run_leg", 40) * (0.8 if glide else 1.0)))
    arm_a = p.get("run_arm", 55) * (0.5 if lurch else 1.0)
    # rx > 0 tips the torso FORWARD (its top toward -y): the runner falls into the run and the legs catch it
    lean = p.get("run_lean", 22) + (8 if glide else 0)
    lead = p.get("run_lead", 2)                       # px the chest leads the hips: the body falls forward
    k = p.get("run_bounce", 0.5) * (1.5 if springy else 0.4 if glide else 1.0)
    sq = list(RUN_SQUASH)
    def dz(i):
        return snap(RUN_RISE[i % 4] * k * 1.5) - (1 if (lurch or glide) else 0)
    frames = []
    for i in range(8):
        j = i % 4
        (xl, ll), (xr, lr) = RUN_FOOT[i], RUN_FOOT[(i + 4) % 8]
        h, hp = dz(i), dz(i - 1)
        push = 4 if j == 2 else 0                     # the push-off drives the chest a little further forward
        pose = merge({
            "hips": {"at": (0, 0, h), "rot": (0, 0, 8 * xl)},        # pelvis turns with the forward leg
            "torso": {"rot": (lean + push, 0, -22 * xl), "at": (0, -lead, 0)},   # shoulders counter it
            "head": {"rot": (-(lean + push) * 0.6, 0, 12 * xl), "at": (0, 0, max(-1, min(1, hp - h)))},
            # glide: arms swept back and still (a low dash); others pump with the opposite foot
            "armL": {"rot": ((50, 0, -10) if glide else (arm_a * xl - (15 if lurch else 0), 0, 0))},
            "armR": {"rot": ((50, 0, 10) if glide else (arm_a * xr - (15 if lurch else 0), 0, 0))},
            "foreL": {"rot": (-20 if glide else -80, 0, 0)}, "foreR": {"rot": (-20 if glide else -80, 0, 0)},
        }, _legs(p, (xl, ll), (xr, lr), reach),
            {} if glide else _weapon_lag(p, arm_a * xr), _prop_pose(p, hp - h, sway=30 if glide else 20))
        fx = [{"kind": "dust", "n": 3 if lurch else 2}] if j == 1 else []
        sqj = 1 + (sq[j] - 1) * (1.6 if springy else 0.5 if glide else 1.0)
        frames.append(Frame(pose, squash=stretch(sqj), fx=fx, event="footstep" if j == 0 else None))
    return Clip("run", frames, speed_px=round(8 * reach, 2))


def _cut(p: Dict, kind: str) -> Dict[str, Pose]:
    """Key poses of one weapon cut, as arm/weapon AIM directions in the body frame (x right, y back, z up;
    resolved against the model in the forge, so any weapon design points where it should).
    diag  = shoulder-high back-right -> low front-left (reads in every facing, the default slash)
    chop  = straight overhead -> down in front (heavy)
    thrust = drawn back -> straight ahead (dart)
    draw  = hand at the left hip -> flat cut across to the right (iaido)"""
    W = list(p.get("smear_hides", ["sword", "weapon"]))

    def pose(torso, head, hips, armR, armL, wpn, legs=(-12, 10)):
        d = {"torso": {"rot": torso}, "head": {"rot": head}, "hips": {"at": (0, 0, hips)},
             "armR": {"aim": armR}, "armL": {"aim": armL},
             "legL": {"rot": (legs[0], 0, 0)}, "legR": {"rot": (legs[1], 0, 0)}}
        d.update({w: {"aim": wpn} for w in W})
        return d

    if kind == "chop":
        return {"coil": pose((6, 0, 14), (6, 0, -8), -2, (0.35, 0.6, -0.7), (-0.2, -0.8, -0.5), (0.2, 0.9, -0.3)),
                "up": pose((-10, 0, 8), (-6, 0, -4), 0, (0.15, 0.4, 0.9), (-0.3, -0.6, 0.2), (0.1, 0.85, 0.5),
                           (-16, 12)),
                "strike": pose((20, 0, -6), (10, 0, 4), -2, (0.1, -0.9, -0.4), (0.3, 0.5, -0.7), (0.05, -0.8, -0.55),
                               (-34, 24)),
                "over": pose((24, 0, -8), (12, 0, 4), -2, (0.05, -0.55, -0.8), (0.3, 0.5, -0.75), (0.0, -0.75, -0.6),
                             (-34, 24))}
    if kind == "thrust":
        return {"coil": pose((4, 0, 24), (4, 0, -16), -1, (0.3, 0.8, -0.3), (-0.3, -0.8, -0.3), (0.0, -1.0, 0.1)),
                "up": pose((0, 0, 30), (2, 0, -20), 0, (0.35, 0.9, -0.1), (-0.3, -0.85, 0.0), (0.0, -1.0, 0.15),
                           (-16, 12)),
                "strike": pose((16, 0, -18), (6, 0, 12), -1, (0.1, -1.0, -0.05), (0.3, 0.7, -0.5), (0.0, -1.0, 0.0),
                               (-36, 26)),
                "over": pose((18, 0, -22), (6, 0, 12), -1, (0.05, -1.0, -0.1), (0.3, 0.7, -0.55), (-0.05, -1.0, -0.05),
                             (-36, 26))}
    if kind == "draw":
        return {"coil": pose((8, 0, -26), (4, 0, 20), -2, (-0.55, -0.35, -0.75), (-0.5, -0.4, -0.7),
                             (-0.35, 0.9, -0.2)),
                "up": pose((8, 0, -30), (4, 0, 24), -2, (-0.6, -0.4, -0.7), (-0.5, -0.45, -0.7), (-0.4, 0.9, -0.15),
                           (-18, 14)),
                "strike": pose((10, 0, 30), (4, 0, -16), -2, (0.75, -0.65, 0.0), (-0.4, 0.6, -0.6), (0.9, -0.4, 0.1),
                               (-36, 26)),
                "over": pose((10, 0, 38), (4, 0, -20), -2, (0.9, 0.15, 0.1), (-0.45, 0.6, -0.6), (0.9, 0.35, 0.2),
                             (-36, 26))}
    return {"coil": pose((10, 0, 30), (6, 0, -18), -2, (0.45, 0.55, -0.7), (-0.25, -0.75, -0.6), (0.35, 0.9, -0.25),
                         (-8, 14)),
            "up": pose((-12, 0, 42), (-6, 0, -24), 0, (0.3, 0.35, 0.9), (-0.45, -0.7, -0.1), (0.2, 0.75, 0.6), (-20, 16)),
            "strike": pose((24, 0, -38), (8, 0, 16), -2, (-0.35, -0.85, -0.3), (0.3, 0.6, -0.6), (-0.45, -0.8, -0.35),
                           (-46, 32)),
            "over": pose((28, 0, -50), (8, 0, 18), -3, (-0.75, -0.4, -0.5), (0.35, 0.65, -0.55), (-0.85, -0.3, -0.3),
                         (-48, 34))}


def keyed(name: str, keys: List[M.Key], n: int, loop: bool = False) -> Clip:
    """Sample key poses into n frames (arcs + per-segment spacing, pp/motion.py)."""
    fr: List[Frame] = []
    for pose, root, sq, k in M.sample(keys, n, loop):
        f = Frame(pose, root=root, squash=stretch(sq))
        if k is not None:
            f.fx, f.event, f.hide, f.flash = list(k.fx), k.event, list(k.hide), k.flash
            f.key = True
        fr.append(f)
    return Clip(name, fr, loop=loop)


SWEEP = [{"kind": "sweep"}]                     # smear along the weapon's real path (one solid frame)
SWEEP_TAIL = [{"kind": "sweep", "tail": True}]  # then a thin broken tail


def humanoid_attack(p: Dict) -> Clip:
    """anim.attack_style, all pose-to-pose with the strike done in ONE frame (no in-betweens, the swept
    smear shows the arc) and a held follow-through:
    slash (13): coil back-low, snap up, diagonal cut, follow-through, ease home (the default)
    heavy (16): long coil, slow raise overhead, trembling hold, crushing chop with dust, frozen follow-through
    hop (12): springy crouch, hop up while raising, cut on landing, bouncy recovery
    dart (12): crouch, leap in, thrust mid-air, hang, drift back
    iaido (14): stillness, one-frame flat draw cut, long frozen follow-through, slow sheathe"""
    style = p.get("attack_style", "slash")
    W = list(p.get("smear_hides", ["sword", "weapon"]))
    lunge = p.get("attack_lunge", 3)
    K = M.Key
    if style == "heavy":
        c = _cut(p, "chop")
        keys = [K(0, {}), K(2, c["coil"], squash=0.9, ease="in"), K(4, c["coil"], squash=0.88, ease="lin"),
                K(6, c["up"], squash=1.16, ease="in"), K(7, c["up"], root=(1, 0, 0), squash=1.18, ease="lin"),
                K(8, c["up"], squash=1.18, ease="lin"),
                K(9, c["strike"], root=(0, -lunge, 0), squash=0.76, ease="snap", hide=W, event="hit",
                  fx=SWEEP + [{"kind": "dust", "n": 5}]),
                K(10, c["over"], root=(0, -lunge, 0), squash=0.82, ease="snap", fx=SWEEP_TAIL),
                K(11, c["over"], root=(0, -lunge, 0), squash=0.88, ease="lin"),
                K(13, mix_pose(c["over"], {}, 0.5), root=(0, -lunge * 0.5, 0), ease="in"),
                K(15, {}, ease="io")]
        n = 16
    elif style == "hop":
        c = _cut(p, "diag")
        keys = [K(0, {}), K(2, c["coil"], squash=0.86, ease="in"),
                K(3, c["up"], root=(0, -lunge * 0.3, 3), squash=1.2, ease="snap"),
                K(4, c["up"], root=(0, -lunge * 0.7, 4), squash=1.06, ease="lin"),
                K(5, c["strike"], root=(0, -lunge, 0), squash=0.78, ease="snap", hide=W, event="hit",
                  fx=SWEEP + [{"kind": "dust", "n": 3}]),
                K(6, c["over"], root=(0, -lunge, 0), squash=0.9, ease="snap", fx=SWEEP_TAIL),
                K(7, c["over"], root=(0, -lunge, 1), squash=1.06, ease="lin"),
                K(9, mix_pose(c["over"], {}, 0.6), root=(0, -lunge * 0.4, 0), squash=0.97, ease="in"),
                K(11, {}, ease="io")]
        n = 12
    elif style == "dart":
        c = _cut(p, "thrust")
        far = lunge * 2.5
        keys = [K(0, {}), K(1, c["coil"], squash=0.82, ease="in"),
                K(2, c["up"], root=(0, -far * 0.4, 4), squash=1.22, ease="snap", fx=[{"kind": "dust", "n": 2}]),
                K(3, c["strike"], root=(0, -far, 4), squash=0.86, ease="snap", hide=W, event="hit", fx=SWEEP),
                K(4, c["over"], root=(0, -far, 3), squash=0.92, ease="snap", fx=SWEEP_TAIL),
                K(5, c["over"], root=(0, -far, 3), ease="lin"),
                K(8, mix_pose(c["over"], {}, 0.7), root=(0, -far * 0.35, 2), ease="in"),
                K(10, {}, squash=0.9, ease="io"), K(11, {}, ease="lin")]
        n = 12
    elif style == "iaido":
        c = _cut(p, "draw")
        far = lunge * 2
        keys = [K(0, {}), K(2, c["coil"], squash=0.95, ease="in"), K(4, c["up"], squash=0.94, ease="lin"),
                K(5, c["strike"], root=(0, -far, 0), squash=0.86, ease="snap", hide=W, event="hit", fx=SWEEP),
                K(6, c["over"], root=(0, -far, 0), squash=0.92, ease="snap", fx=SWEEP_TAIL),
                K(10, c["over"], root=(0, -far, 0), ease="lin"),
                K(13, {}, ease="io")]
        n = 14
    else:
        # stepped keys (limited animation holds each one): settle, big wind-up held 3, one-frame cut with a
        # lunge, follow-through held 3, one recovery breakdown held 2, home
        c = _cut(p, "diag")
        far = lunge * 1.6
        keys = [K(0, {}), K(1, c["coil"], root=(0, 1, 0), squash=0.9, ease="snap"),
                K(3, c["up"], root=(0, 1.5, 0), squash=1.12, ease="snap"),
                K(4, merge(c["up"], {"torso": {"rot": (-3, 0, 6)}}), root=(0, 1.5, 0), squash=1.14, ease="lin"),
                K(6, c["strike"], root=(0, -far, 0), squash=0.82, ease="snap", hide=W, event="hit", fx=SWEEP),
                K(7, c["over"], root=(0, -far, 0), squash=0.88, ease="snap", fx=SWEEP_TAIL),
                K(9, c["over"], root=(0, -far, 0), squash=0.9, ease="lin"),
                K(10, merge(mix_pose(c["over"], {}, 0.55), {"hips": {"at": (0, 0, 1)}}), root=(0, -far * 0.5, 0),
                  squash=1.04, ease="snap"),
                K(12, {}, ease="snap")]
        n = 13
    return _hovered(keyed("attack", keys, n), p)


def humanoid_cast(p: Dict) -> Clip:
    """Charge (6) -> release flash -> recover (4)."""
    gather = {"armL": {"rot": (-55, 0, 35)}, "armR": {"rot": (-55, 0, -35)}, "torso": {"rot": (6, 0, 0)},
              "hips": {"at": (0, 0, -1)}, "head": {"rot": (6, 0, 0)}}
    raise_ = {"armL": {"rot": (-160, 0, 20)}, "armR": {"rot": (-160, 0, -20)}, "torso": {"rot": (-10, 0, 0)},
              "head": {"rot": (-12, 0, 0)}}
    release = {"armL": {"rot": (-95, 0, 12)}, "armR": {"rot": (-95, 0, -12)}, "torso": {"rot": (-14, 0, 0)},
               "hips": {"at": (0, 0, -1)}}
    fr: List[Frame] = []
    for i in range(3):
        t = ease_out((i + 1) / 3)
        fr.append(Frame(mix_pose({}, gather, t), squash=stretch(lerp(1, 0.95, t)),
                        fx=[{"kind": "charge", "t": i / 6}]))
    for i in range(3):
        t = ease_io((i + 1) / 3)
        fr.append(Frame(mix_pose(gather, raise_, t), squash=stretch(lerp(0.95, 1.14, t)),
                        fx=[{"kind": "charge", "t": (i + 3) / 6}]))
    fr.append(Frame(release, squash=stretch(0.86), fx=[{"kind": "burst", "t": 0.0}], event="cast"))
    fr.append(Frame(release, squash=stretch(0.92), fx=[{"kind": "burst", "t": 0.25}]))
    for i, t in enumerate((0.2, 0.5, 0.8, 1.0)):
        fr.append(Frame(mix_pose(release, {}, ease_io(t)),
                        fx=[{"kind": "burst", "t": 0.5 + i * 0.2}] if i < 2 else []))
    return _hovered(Clip("cast", fr, loop=False), p)


def humanoid_hit(p: Dict) -> Clip:
    """2 frames — recoil, then flat silhouette flash."""
    recoil = {"torso": {"rot": (16, 0, 0)}, "head": {"rot": (12, 0, 0)}, "armL": {"rot": (-30, 0, 25)},
              "armR": {"rot": (-30, 0, -25)}, "hips": {"at": (0, 0, -1)}}
    return _hovered(Clip("hit", [
        Frame(recoil, root=(0, 1, 0), squash=stretch(0.92), event="hurt"),
        Frame(recoil, root=(0, 1, 0), squash=stretch(0.92), flash=True),
    ], loop=False), p)


def humanoid_death(p: Dict) -> Clip:
    """14 frames of stepped keys (saint11 Death / Rosen; limited animation holds each one): the hit throws
    the body back (flash), it staggers a step, the knees give and it HOLDS on its knees, head down (the
    "give up" beat that reads), then it topples forward with gravity spacing (one breakdown, impact with
    dust, one rebound) and lies face-down, arms out, still. The root slides back so the lying body stays
    centred (death_slide px, default 0.3 x body height). Frames are `away`: the forge rolls the fall
    sideways in S/N and mirrors it in N-ish facings."""
    H = p.get("body_h", 26)
    back = snap(H * 0.12)
    cen = p.get("death_slide", snap(H * 0.3))
    W = list(p.get("smear_hides", ["sword", "weapon"]))
    # torso/head rx < 0 lean back, > 0 slump forward
    thrown = {"torso": {"rot": (-22, 0, 8)}, "head": {"rot": (-14, 0, 10)},
              "armL": {"aim": (-0.85, 0.3, 0.35)}, "armR": {"aim": (0.85, 0.3, 0.35)},
              "legL": {"rot": (-18, 0, 0)}, "legR": {"rot": (14, 0, 0)}}
    stagger = {"torso": {"rot": (10, 0, -4)}, "head": {"rot": (12, 0, -6)}, "hips": {"at": (0, 0, -1)},
               "armL": {"aim": (-0.55, -0.1, -0.8)}, "armR": {"aim": (0.55, 0.2, -0.8)},
               "legL": {"rot": (-26, 0, 0)}, "legR": {"rot": (10, 0, 0)}, "shinL": {"rot": (24, 0, 0)}}
    kneel = {"torso": {"rot": (26, 0, 0)}, "head": {"rot": (22, 0, 0)},
             "hips": {"at": (0, 0, -snap(p.get("thigh_len", p.get("leg_len", 5.0) * 0.54) * 0.85))},
             "armL": {"aim": (-0.3, -0.2, -0.95)}, "armR": {"aim": (0.3, -0.2, -0.95)},
             "legL": {"rot": (-80, 0, 4)}, "legR": {"rot": (-70, 0, -4)},
             "shinL": {"rot": (90, 0, 0)}, "shinR": {"rot": (84, 0, 0)}}
    for w in W:                                    # the weapon drops point-down beside the body
        kneel[w] = {"aim": (0.25, -0.35, -0.9)}

    def prone(a: float, extra: Optional[Pose] = None) -> Pose:
        """Face-down, `a` degrees forward about the feet; legs straighten, arms flung out, head turned."""
        d = merge({"root": {"rot": (a, 0, 0)}, "torso": {"rot": (-4, 0, 0)}, "head": {"rot": (6, 0, 24)},
                   "hips": {"at": (0, 0, -1)},
                   "armL": {"aim": (-0.9, -0.2, 0.3)}, "armR": {"aim": (0.8, -0.2, 0.45)},
                   "legL": {"aim": (-0.16, 0.08, -1)}, "legR": {"aim": (0.1, 0.02, -1)},   # legs together, any stance
                   "shinL": {"rot": (6, 0, 0)}, "shinR": {"rot": (0, 0, 0)}}, extra or {})
        return d

    def fall(a: float, u: float) -> Pose:         # tipping over from the knees; the arms reach out first
        arms = {k: v for k, v in prone(0).items() if k.startswith(("arm", "fore", "head"))}
        pose = merge(kneel, {k: v for k, v in mix_pose(
            {k: kneel.get(k, {}) for k in arms}, arms, u).items()})
        return merge(pose, {"root": {"rot": (a, 0, 0)}})

    K = M.Key
    keys = [K(0, thrown, root=(0, back * 0.6, 0), squash=1.06, flash=True, event="hurt"),
            K(1, thrown, root=(0, back, 1), squash=1.1, ease="snap"),
            K(3, stagger, root=(0, back, 0), squash=0.94, ease="snap"),
            K(5, kneel, root=(0, back, 0), squash=0.92, ease="snap"),
            K(6, kneel, root=(0, back, 0), squash=0.96, ease="snap"),
            K(8, fall(35, 0.5), root=(0, back + (cen - back) * 0.3, 0), ease="snap"),
            K(9, prone(90, {"shinL": {"rot": (24, 0, 0)}, "shinR": {"rot": (16, 0, 0)}}), root=(0, cen, 0),
              squash=0.82, ease="snap", fx=[{"kind": "dust", "n": 6}]),
            K(10, prone(82), root=(0, cen, 1), ease="snap"),
            K(11, prone(90), root=(0, cen, 0), squash=0.94, ease="snap"),
            K(13, prone(90, {"head": {"rot": (4, 0, 0)}}), root=(0, cen, 0), ease="snap")]
    clip = keyed("death", keys, 14)
    for f in clip.frames:
        f.away = True
    return _hovered(clip, p, ground_from=5)   # floaters drop to the ground


# ------------------------------------------------------------------ quadruped
# Rig: root > body > head(>jaw, ears) ; body > legFL, legFR, legHL, legHR, tail.

def quadruped_idle(p: Dict) -> Clip:
    body = [0, 0, 1, 1, 1, 1, 0, 0]
    tail = [0, 8, 14, 18, 14, 8, 0, -6]
    frames = []
    for i in range(8):
        frames.append(Frame({"body": {"at": (0, 0, -body[i])},
                             "head": {"at": (0, 0, body[i] - body[(i - 2) % 8])},
                             "tail": {"rot": (0, 0, tail[i])},
                             "ears": {"rot": (tail[(i - 3) % 8] * 0.4, 0, 0)}}))
    return held(Clip("idle", frames), p.get("idle_hold", 2))


def quadruped_walk(p: Dict, run: bool = False) -> Clip:
    """Walk: lateral sequence (hind leads same-side fore by 1/4). Run: transverse gallop.
    Gaits: hop (rabbit bound: hind legs push together, fore legs reach), lurch (low prowl, head down),
    bounce (springy body bob)."""
    g = p.get("gait", "stride")
    if g == "hop":
        return _hovered(_quad_hop(p, run), p)
    clip = _quad_stride(p, run, g)
    return _hovered(clip, p)


def _quad_hop(p: Dict, run: bool) -> Clip:
    hh = p.get("run_hop" if run else "walk_hop", 5 if run else 3)
    z = [0, snap(hh * 0.7), hh, snap(hh * 0.5)]
    k = 1.4 if run else 1.0
    hind = [-10 * k, 40 * k, 25 * k, 0]           # +x = pushes back
    fore = [5 * k, -10 * k, -35 * k, -20 * k]      # -x = reaches forward to land
    body = [-6, 8, 0, -8]                          # nose up on the push, down to land front-first
    sq = [0.84, 1.14, 1.04, 0.98]
    frames = []
    for i in range(8):
        j, side = i % 4, (1 if i < 4 else -1)
        pose = {"legHL": {"rot": (hind[j] + 3 * side, 0, 0)}, "legHR": {"rot": (hind[j] - 3 * side, 0, 0)},
                "legFL": {"rot": (fore[j] + 3 * side, 0, 0)}, "legFR": {"rot": (fore[j] - 3 * side, 0, 0)},
                "body": {"rot": (body[j], 0, 0)}, "head": {"rot": (-body[j] * 0.6, 0, 0)},
                "tail": {"rot": (-body[j] * 2, 0, 0)}, "ears": {"rot": (10 * (z[j] - z[(j - 1) % 4]) / max(1, hh), 0, 0)}}
        land = j == 0
        frames.append(Frame(pose, root=(0, 0, z[j]), squash=stretch(sq[j]),
                            fx=[{"kind": "dust", "n": 2 if run else 1}] if land else [],
                            event="footstep" if land else None))
    if not run:              # a walking hop settles: hold the landing and the apex
        frames = [g for i, f in enumerate(frames) for g in (hold(f, 2) if i % 4 in (0, 2) else [f])]
    return Clip("run" if run else "walk", frames, speed_px=p.get("stride_px", 12) * 2)


def _quad_foot(ph: float, beta: float, reach: float, lift_h: float) -> Tuple[float, float, bool]:
    """One paw over a cycle phase: stance (0..beta) slides back LINEARLY from +reach to -reach (locked to the
    ground), swing eases forward with an arched lift. -> (forward px, lift px, swinging)."""
    ph %= 1.0
    if ph < beta:
        return reach - 2 * reach * ph / beta, 0.0, False
    u = (ph - beta) / (1 - beta)
    return -reach + 2 * reach * ease_io(u), lift_h * math.sin(math.pi * u) ** 0.8, True


def _quad_leg(fwd: float, lift: float, L: float, body_dz: float) -> Dict:
    """Rigid quadruped leg: angle from the paw's forward offset, shifted along its axis so the paw sits at
    `lift` while the body is body_dz off its rest height."""
    s_ = max(-0.95, min(0.95, fwd / L))
    a = -math.degrees(math.asin(s_))
    return {"rot": (a, 0, 0), "at": (0, 0, snap(L * math.cos(math.asin(s_)) - L - body_dz + lift))}


def _quad_stride(p: Dict, run: bool, g: str) -> Clip:
    """Walk: lateral sequence (hind leads same-side fore by 1/4), duty 0.65. Run: rotary gallop, duty 0.4.
    Paws are ground-locked (speed_px matches them); body bob is held 2 frames; head nods a frame late."""
    n = 8 if run else int(p.get("walk_frames", 16))       # walk 1.2 s per cycle, gallop 0.6 s
    L = p.get("leg_len", 6.0)
    reach = L * math.sin(math.radians(p.get("run_leg" if run else "walk_leg", 38 if run else 24)))
    beta = 0.4 if run else 0.65
    off = {"legHL": 0.0, "legHR": 0.12, "legFL": 0.5, "legFR": 0.62} if run else \
          {"legHL": 0.0, "legFL": 0.25, "legHR": 0.5, "legFR": 0.75}
    lift_h = p.get("run_lift" if run else "walk_lift", 3.0 if run else 2.0)
    bodyz = [0, 1, 2, 1, 0, 1, 2, 1] if run else [0, 0, -1, -1, 0, 0, -1, -1]
    if g == "bounce" and not run:
        bodyz = [0, 1, 1, 0, 0, 1, 1, 0]
    frames = []
    def bz(i):
        return bodyz[int((i % n) * 8 / n)]
    for i in range(n):
        ph = i / n
        h = bz(i)
        pose: Pose = {}
        for leg, o in off.items():
            x, lift, _ = _quad_foot(ph + o, beta, reach, lift_h)
            pose[leg] = _quad_leg(x, lift, L, h)
        pitch = 6 * math.cos(2 * math.pi * ph) if run else 0.0
        pose["body"] = {"at": (0, 0, h), "rot": (pitch, 0, 0)}
        pose["head"] = {"rot": (-pitch * 1.2 + (0 if run else 3 * math.sin(4 * math.pi * ph)), 0, 0),
                        "at": (0, 0, bz(i - 1) - h)}
        pose["tail"] = {"rot": (0, 0, 14 * math.sin(2 * math.pi * ph - 1.2))}
        if g == "lurch":                               # prowl: body low, head down
            pose = merge(pose, {"body": {"at": (0, 0, -1)}, "head": {"rot": (14, 0, 0), "at": (0, 0, -1)},
                                "tail": {"rot": (12, 0, 0)}})
        sq = stretch(1 + 0.06 * (h - 1)) if run else (1.0, 1.0)
        step = (i * 8 / n) % 4 == 0
        frames.append(Frame(pose, squash=sq, fx=[{"kind": "dust", "n": 1}] if run and step else [],
                            event="footstep" if step else None))
    return Clip("run" if run else "walk", frames, speed_px=round(2 * reach / beta, 2))


def quadruped_attack(p: Dict) -> Clip:
    """13 frames (a bite, pose-to-pose): crouch in and HOLD, snap into the leap, bite at full reach,
    land squashed (2 frames), settle with a small overshoot."""
    lunge = p.get("leap_px", 10)
    crouch = {"body": {"at": (0, 0, -2), "rot": (-10, 0, 0)}, "head": {"rot": (12, 0, 0)},
              "legFL": {"rot": (-14, 0, 0), "at": (0, 0, 1)}, "legFR": {"rot": (-14, 0, 0), "at": (0, 0, 1)},
              "legHL": {"rot": (18, 0, 0), "at": (0, 0, 1)}, "legHR": {"rot": (18, 0, 0), "at": (0, 0, 1)},
              "tail": {"rot": (-24, 0, 0)}}
    leap = {"body": {"rot": (12, 0, 0)}, "head": {"rot": (-16, 0, 0)}, "legFL": {"rot": (-60, 0, 0)},
            "legFR": {"rot": (-52, 0, 0)}, "legHL": {"rot": (55, 0, 0)}, "legHR": {"rot": (60, 0, 0)},
            "tail": {"rot": (24, 0, 0)}, "jaw": {"rot": (38, 0, 0)}}
    bite = merge(leap, {"body": {"rot": (-14, 0, 0)}, "head": {"rot": (16, 0, 0)}, "jaw": {"rot": (-38, 0, 0)},
                        "legFL": {"rot": (30, 0, 0)}, "legFR": {"rot": (26, 0, 0)}})
    land = {"body": {"at": (0, 0, -2), "rot": (-6, 0, 0)}, "head": {"rot": (14, 0, 0)},
            "legFL": {"rot": (-10, 0, 0), "at": (0, 0, 1)}, "legFR": {"rot": (-10, 0, 0), "at": (0, 0, 1)},
            "legHL": {"rot": (14, 0, 0), "at": (0, 0, 1)}, "legHR": {"rot": (10, 0, 0), "at": (0, 0, 1)}}
    K = M.Key
    keys = [K(0, {}), K(2, crouch, root=(0, 1.5, 0), squash=0.88, ease="in"),
            K(3, crouch, root=(0, 2, 0), squash=0.86, ease="lin"),
            K(4, leap, root=(0, -lunge * 0.45, 4), squash=1.18, ease="snap", fx=[{"kind": "dust", "n": 3}]),
            K(5, leap, root=(0, -lunge * 0.8, 5), squash=1.06, ease="lin"),
            K(6, bite, root=(0, -lunge, 2), ease="lin", event="hit"),
            K(7, land, root=(0, -lunge, 0), squash=0.64, ease="lin", fx=[{"kind": "dust", "n": 4}]),
            K(8, land, root=(0, -lunge, 0), squash=0.74, ease="lin"),
            K(10, merge(land, {"body": {"at": (0, 0, 1)}}), root=(0, -lunge * 0.6, 0), squash=1.04, ease="in"),
            K(12, {}, ease="io")]
    return _hovered(keyed("attack", keys, 13), p)


def quadruped_death(p: Dict) -> Clip:
    """14 frames: hit (flash) and rear up, the hind legs give, topple onto the side with gravity spacing,
    one rebound, legs settle late, hold."""
    rear = {"body": {"rot": (-16, 0, 0)}, "head": {"rot": (-22, 0, 0)}, "tail": {"rot": (-20, 0, 0)},
            "legFL": {"rot": (-24, 0, 0)}, "legFR": {"rot": (-18, 0, 0)}, "jaw": {"rot": (24, 0, 0)}}
    give = {"body": {"at": (0, 0, -2), "rot": (6, 0, 0)}, "head": {"rot": (18, 0, 0)},
            "legHL": {"rot": (36, 0, 0), "at": (0, 0, 2)}, "legHR": {"rot": (30, 0, 0), "at": (0, 0, 2)},
            "legFL": {"rot": (-10, 0, 0), "at": (0, 0, 1)}, "legFR": {"rot": (-6, 0, 0), "at": (0, 0, 1)}}

    def side(a: float, extra: Optional[Pose] = None) -> Pose:
        return merge({"root": {"rot": (0, a, 0)}, "body": {"at": (0, 0, -2)}, "head": {"rot": (10, 0, 6)},
                      "legFL": {"rot": (-28, 0, 0)}, "legFR": {"rot": (-14, 0, 0)},
                      "legHL": {"rot": (24, 0, 0)}, "legHR": {"rot": (32, 0, 0)}, "tail": {"rot": (0, 0, 18)}},
                     extra or {})
    K = M.Key
    keys = [K(0, rear, root=(0, 1, 0), flash=True, event="hurt"),
            K(1, rear, root=(0, 2, 1), squash=1.12, ease="snap"),
            K(3, merge(rear, {"head": {"rot": (6, 0, 0)}}), root=(0, 2, 1), squash=1.1, ease="in"),
            K(4, give, root=(0, 2, 0), squash=0.88, ease="snap")]
    for j, ang in enumerate((6, 24, 54, 88)):
        u = ang / 88
        pose = merge({k: v for k, v in mix_pose(give, side(0), min(1.0, u * 1.4)).items() if k != "root"},
                     {"root": {"rot": (0, ang, 0)}})
        keys.append(K(5 + j, pose, root=(0, 2, 0), squash=0.8 if j == 3 else 0.96, ease="lin",
                      fx=[{"kind": "dust", "n": 5}] if j == 3 else []))
    keys += [K(9, side(80), root=(0, 2, 1), ease="snap"),
             K(10, side(88), root=(0, 2, 0), squash=0.92, ease="snap"),
             K(11, side(88, {"legFL": {"rot": (8, 0, 0)}, "legHR": {"rot": (-6, 0, 0)}}), root=(0, 2, 0), ease="in"),
             K(13, side(88, {"legFL": {"rot": (12, 0, 0)}, "legHR": {"rot": (-8, 0, 0)}, "head": {"rot": (6, 0, 0)}}),
               root=(0, 2, 0), ease="io")]
    return _hovered(keyed("death", keys, 14), p, ground_from=5)


def quadruped_hit(p: Dict) -> Clip:
    recoil = {"body": {"rot": (6, 0, 0)}, "head": {"rot": (-14, 0, 0)}, "tail": {"rot": (-20, 0, 0)}}
    return Clip("hit", [Frame(recoil, root=(0, 1, 0), squash=stretch(0.9), event="hurt"),
                        Frame(recoil, root=(0, 1, 0), squash=stretch(0.9), flash=True)], loop=False)


RIGS: Dict[str, Dict[str, Callable[[Dict], Clip]]] = {
    "humanoid": {
        "idle": humanoid_idle, "walk": humanoid_walk, "run": humanoid_run, "attack": humanoid_attack,
        "cast": humanoid_cast, "hit": humanoid_hit, "death": humanoid_death,
    },
    "quadruped": {
        "idle": quadruped_idle, "walk": quadruped_walk, "run": lambda p: quadruped_walk(p, run=True),
        "attack": quadruped_attack, "hit": quadruped_hit, "death": quadruped_death,
    },
}

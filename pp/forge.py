"""Spec -> finished asset pack (sheets, GIFs, JSON, contact sheet)."""
from __future__ import annotations

import json
from dataclasses import replace
import math
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import numpy as np

from . import anim as A
from .color import hex_to_rgb
from .io import compose_bg, pack_sheet, save_gif, save_png
from .layers import apply_life, combo
from .render import DIRECTIONS, K, RAY, YAW, Buffers, Model, render_frame
from .sdf import rot_matrix
from .shade import Style, finish

from .paths import DATA as ROOT, OUT  # noqa: F401  (ROOT: styles/specs/docs; OUT: where builds go)


def load_json(path) -> Dict:
    return json.loads(Path(path).read_text())


def load_spec(path) -> Dict:
    """A spec file as the forge takes it (flora "generator" props expanded into bones)."""
    spec = load_json(path)
    if "generator" in spec:
        from .flora import build_spec
        spec = build_spec(spec)
    return spec


def load_style(name_or_path: str) -> Style:
    p = Path(name_or_path)
    if not p.exists():
        p = ROOT / "styles" / (name_or_path + ".json")
    return Style(load_json(p))


# ------------------------------------------------------------------ in-sprite fx

def draw_smear(rgba: np.ndarray, depth: np.ndarray, frame: A.Frame, fx: Dict, facing: str,
               anchor: Tuple[int, int], style: Style, smear: Dict) -> None:
    """Weapon smear: a flat crescent swept in the horizontal plane around the body,
    projected with the same camera, depth-tested against the character."""
    yaw = math.radians(YAW[facing])
    R = rot_matrix(0, 0, YAW[facing])
    radius = smear.get("radius", 14)
    width = smear.get("width", 6)
    if fx.get("arc") == "wide":
        width = max(width, 0.45 * radius)          # R21: the impact smear is a solid, heavy crescent
    height = smear.get("height", 9)
    col = hex_to_rgb(smear.get("color", "#eef2e8"))
    edge = hex_to_rgb(smear["edge"]) if smear.get("edge") else None
    arc = fx.get("arc")
    plane = fx.get("plane", smear.get("plane", "h"))
    if plane == "v":       # overhead chop: behind-above -> front -> down, in the body's forward/up plane
        presets = {"wide": (-30, 150, 1.0), "tail": (90, 165, 0.45)}
        a0, a1, thick = presets.get(arc, (120, 175, 0.3))
    else:                  # horizontal sweep, right -> front -> left
        presets = {"wide": (-110, 80, 1.0), "tail": (20, 95, 0.45)}
        a0, a1, thick = presets.get(arc, (45, 120, 0.3))
    a0, a1, thick = fx.get("a0", a0), fx.get("a1", a1), fx.get("thick", thick)
    tilt = math.radians(fx.get("tilt", smear.get("tilt", 0.0)))     # roll the plane about the forward axis
    side = fx.get("side", smear.get("side", 2.0))                    # lateral offset of a vertical arc
    fwd = fx.get("forward", smear.get("forward", 0.0))               # push the arc centre forward
    ct, st_ = math.cos(tilt), math.sin(tilt)
    H, W = depth.shape
    mask = np.zeros((H, W), bool)
    ro = np.asarray(frame.root, float)
    for a in np.linspace(a0, a1, 180):
        u = (a - a0) / (a1 - a0)
        taper = math.sin(math.pi * min(1.0, u * 1.15)) ** 0.6 if u < 0.87 else max(0.0, (1 - u) / 0.13) * 0.5
        w = width * thick * max(taper, 0.0)
        if w < 0.35 or (arc not in ("wide", "tail") and int(u * 5) % 2 == 1):
            continue
        ang = math.radians(a)
        for r in np.linspace(radius - w, radius, max(2, int(w * 3))):
            if plane == "v":
                lx, ly, lz = side, -r * math.sin(ang), r * math.cos(ang) * 0.9
            else:
                ang2 = ang - math.pi / 2
                lx, ly, lz = r * math.cos(ang2), r * math.sin(ang2) * 0.9, 3 * math.sin(ang) * 0.3
            # tilt about the forward (y) axis, around the smear centre
            lx, lz = lx * ct - lz * st_, lx * st_ + lz * ct
            p = np.array([lx, ly - fwd, height + lz])
            q = R @ p + ro
            x = int(math.floor(anchor[0] + q[0]))
            y = int(math.floor(anchor[1] - (q[2] + K * q[1])))
            d = float(q @ RAY)
            if 0 <= x < W and 0 <= y < H and (rgba[y, x, 3] == 0 or d < depth[y, x] - 0.5):
                mask[y, x] = True
    if not mask.any():
        return
    _smear_fill(rgba, mask, style, smear, trailing=np.arange(H)[:, None] > anchor[1] - height - 2)


def _smear_fill(rgba: np.ndarray, mask: np.ndarray, style: Style, smear: Dict, trailing=True) -> None:
    """Fill a smear mask in the spec's smear colour (palette-locked) and rim it: an ink rim all round when the
    smear is too close to the ground's value to read (|dL| < 0.25), else the edge colour on the trailing rim."""
    from .shade import N4, shift
    from .color import rgb_to_oklab
    col = hex_to_rgb(smear.get("color", "#eef2e8"))
    edge = hex_to_rgb(smear["edge"]) if smear.get("edge") else None
    rgba[mask] = (*col, 255)
    inner = mask.copy()
    for dy, dx in N4:
        inner &= shift(mask, dy, dx, False)
    rim = mask & ~inner
    bgL = float(rgb_to_oklab(np.array(hex_to_rgb(style.spec.get("bg", "#000000"))))[0])
    if abs(float(rgb_to_oklab(np.array(col))[0]) - bgL) < 0.25:
        # a light smear on a light ground would vanish: give it an ink rim all round
        ink = style.ramps.get("ink", [(30, 24, 28)])[0]
        rgba[rim] = (*ink, 255)
    elif edge is not None:
        # the trailing (inner) rim darkens, the leading rim stays bright
        rgba[rim & trailing] = (*edge, 255)


def apply_flash(rgba: np.ndarray, style: Style) -> None:
    col = hex_to_rgb(style.spec.get("flash", "#ffffff"))
    a = rgba[..., 3] > 0
    rgba[a, :3] = col


def _mirror_front_back(fr: A.Frame) -> A.Frame:
    """Reflect a frame's motion through the body's xz plane (y -> -y): x/z rotations and y offsets flip,
    so a backward fall becomes a forward one. The model itself is not mirrored."""
    pose = {}
    for b, v in fr.pose.items():
        w = dict(v)
        if "rot" in w:
            rx, ry, rz = w["rot"]
            w["rot"] = (-rx, ry, -rz)
        if "at" in w:
            x, y, z = w["at"]
            w["at"] = (x, -y, z)
        pose[b] = w
    r = fr.root
    return A.Frame(pose, fr.ms, (r[0], -r[1], r[2]), fr.squash, fr.flash, fr.fx, fr.event, fr.hide, False)


def _fall_sideways(fr: A.Frame) -> A.Frame:
    """Turn a backward fall (pitch about x, drift along y) into a roll about y with the drift along x,
    so S/N deaths lie across the screen in profile."""
    pose = dict(fr.pose)
    if "root" in pose:
        w = dict(pose["root"])
        rx, ry, rz = w.get("rot", (0, 0, 0))
        w["rot"] = (0, ry - rx, rz)
        pose["root"] = w
    r = fr.root
    return A.Frame(pose, fr.ms, (r[0] + r[1], 0, r[2]), fr.squash, fr.flash, fr.fx, fr.event, fr.hide, False)


# ------------------------------------------------------------------ building

class Forge:
    def __init__(self, spec: Dict, style: Optional[Style] = None):
        from .motion import add_knees
        from .size import fit
        self.style = style or load_style(spec["style"])
        spec, self.size_k = fit(spec, self.style)   # spec "size": scale the whole spec to its size class
        spec = add_knees(spec)             # humanoid legs get a thigh + shin, so walks fold the knee
        self.spec = spec
        self.style.add_materials(spec.get("materials"))
        self.mats = self.style.material_list()
        self.model = Model(spec, self.mats)
        self.size = tuple(spec.get("frame", [48, 48]))
        self.anchor = tuple(spec.get("anchor", [self.size[0] // 2, self.size[1] - 6]))

    def clips(self) -> List[A.Clip]:
        rig = self.spec.get("rig", "humanoid")
        # the family's way of moving (style "motion") under the asset's own anim params
        from .size import scale_motion
        own = self.spec.get("anim", {})
        params = {**scale_motion(self.style.spec.get("motion", {}), self.size_k, own), **own}
        params.setdefault("body_h", self._body_height())
        for k, v in self._leg_lengths().items():
            params.setdefault(k, v)
        combos = self.spec.get("layers", {})
        wanted = self.spec.get("clips", list(A.RIGS.get(rig, {}).keys()) + list(combos))

        def raw(name: str) -> A.Clip:
            if name in self.spec.get("custom_clips", {}):
                clip = self._custom(name, self.spec["custom_clips"][name])
            else:
                clip = A.RIGS[rig][name](params)
            carry = params.get("carry")
            if carry and name in ("idle", "walk", "run") and name not in self.spec.get("custom_clips", {}):
                # anim.carry = {bone: {"aim": [x, y, z], "roll": deg}}: a carried bow or spear keeps its angle
                # in the body frame while the arm swings (no flailing)
                for fr in clip.frames:
                    fr.pose = {**fr.pose, **{b: {**fr.pose.get(b, {}), **v} for b, v in carry.items()}}
            return A.hitstop(clip, params.get("hitstop", 0)) if name == "attack" else clip
        out = []
        for name in wanted:
            # body-part layers (pp/layers.py): e.g. run legs + attack arms
            out.append(combo(self.model, name, combos[name], raw) if name in combos else raw(name))
        # additive life (sway, flutter, look) from the style, overridden per spec; off unless asked for
        out = apply_life(self.model, out, {**self.style.spec.get("life", {}), **self.spec.get("life", {})})
        # follow-through springs for props / tails / ears (pp/secondary.py)
        follow = params.get("follow")
        if follow is None:
            follow = {b: {} for b in params.get("props", [])}
            if rig == "quadruped":
                follow.setdefault("tail", {"gain": 8})
                follow.setdefault("ears", {"gain": 5, "axes": "x"})
        from . import motion as M
        # aims -> rotations, then overlap: children trail their parents (successive breaking of joints)
        out = [M.resolve_feet(self.model, M.resolve_aims(self.model, c)) for c in out]
        lags = self._drag_lags(rig, params)
        if lags:
            out = [M.drag(self.model, c, lags) for c in out]
        if follow:
            from .secondary import apply as follow_through
            out = [follow_through(self.model, c, follow) for c in out]
        # hold-then-step: sub-pixel rotation drift is held so parts never boil
        legs = ("legL", "legR", "shinL", "shinR")        # solved feet stay exactly on their targets
        out = [M.stabilize(self.model, c, params.get("stabilize_px", 0.6), skip=legs) for c in out]
        # limited animation: fewer, stronger poses, each held (anim.on = 2 = "on twos"; per clip: {"run": 1})
        out = [M.limit(self.model, c, self._on(c.name, params)) for c in out]
        for c in out:                       # a swept smear draws the path from the last different pose
            for i, fr in enumerate(c.frames):
                for fx in fr.fx:
                    if fx.get("kind") == "sweep" and i > 0:
                        j = i - 1
                        while j > 0 and c.frames[j].pose == fr.pose:
                            j -= 1
                        fx["from"] = (c.frames[j].pose, c.frames[j].root, c.frames[j].squash)
        return out

    ON = {"run": 1, "hit": 1}               # fast cycles stay on ones

    def _on(self, name: str, params: Dict) -> float:
        """Hold factor for a clip: hand-written clips keep their own timing unless they ask ("on": n)."""
        custom = self.spec.get("custom_clips", {})
        if name in custom:
            return float(custom[name].get("on", 1))
        on = params.get("on", 2)
        if isinstance(on, dict):
            return float(on.get(name, self.ON.get(name, 2)))
        return float(self.ON.get(name, on) if "on" not in params else on)

    DRAG = {"head": 0.5, "armL": 0.4, "armR": 0.4, "foreL": 0.65, "foreR": 0.65, "jaw": 0.4}

    def _drag_lags(self, rig: str, params: Dict) -> Dict[str, float]:
        """Frames each bone trails its parent's motion by. anim.drag scales them (0 = off); anim.lags
        overrides per bone. Hand-held weapons trail most (they are the end of the chain)."""
        k = float(params.get("drag", 1.0))
        if k <= 0:
            return {}
        lags = dict(self.DRAG)
        for w in params.get("smear_hides", ["sword", "weapon"]):
            lags[w] = 0.8
        lags.update(params.get("lags", {}))
        return {b: v * k for b, v in lags.items() if b in self.model.bones}

    def _leg_lengths(self) -> Dict[str, float]:
        """leg_len = hip joint height (humanoid legL, quadruped mean of legFL/legHL); thigh_len/shin_len
        when the leg has a knee."""
        w = self.model.world({}, 0.0)
        out: Dict[str, float] = {}
        if "legL" in w:
            out["leg_len"] = float(w["legL"][1][2])
            if "shinL" in w:
                out["shin_len"] = float(w["shinL"][1][2])
                out["thigh_len"] = float(np.linalg.norm(w["legL"][1] - w["shinL"][1]))
        elif "legFL" in w and "legHL" in w:
            out["leg_len"] = float(w["legFL"][1][2] + w["legHL"][1][2]) / 2
        return out

    def _body_height(self) -> float:
        """Rest-pose height in px (top of the highest part's bounding sphere)."""
        from .render import _bounds
        w = self.model.world({}, 0.0)
        top = 0.0
        for n, b in self.model.bones.items():
            if b.parts:
                c, r = _bounds(b.parts)
                M, o = w[n]
                top = max(top, float((o + M @ c)[2] + r))
        return top

    def _custom(self, name: str, c: Dict) -> A.Clip:
        frames = []
        for f in c["frames"]:
            fr = A.Frame(f.get("pose", {}), A.FRAME_MS, tuple(f.get("root", (0, 0, 0))),
                         tuple(f.get("squash", (1, 1))), f.get("flash", False), f.get("fx", []),
                         f.get("event"), f.get("hide", []), bool(f.get("away", False)))
            fr.show = list(f.get("show", []))
            frames += A.hold(fr, int(f.get("hold", 1)))
        return A.Clip(name, frames, c.get("loop", True))

    def frame(self, fr: A.Frame, facing: str) -> np.ndarray:
        # bones with "hidden": true (an arrow, a spell orb) only appear on frames that "show" them
        hidden = [b["name"] for b in self.spec.get("bones", []) if b.get("hidden") and b["name"] not in fr.show]
        if hidden and fr.hide is not None:
            fr = replace(fr, hide=list(fr.hide) + [h for h in hidden if h not in fr.hide])
        if fr.away and facing in ("S", "N"):
            fr = _fall_sideways(fr)            # a fall along the view axis reads as a squash: roll it instead
        elif fr.away and facing in ("NE", "NW"):
            fr = _mirror_front_back(fr)
        root = tuple(float(math.floor(v + 0.5)) for v in fr.root)
        # root motion is authored in the character's own frame (y<0 = forward)
        Rf = rot_matrix(0, 0, YAW[facing])
        root_w = Rf @ np.asarray(root, float)
        view = self.spec.get("view", {})
        yaw_off = float(view.get("yaw", {}).get(facing, 0.0))
        widen = float(view.get("widen", {}).get(facing, 1.0))
        buf = render_frame(self.model, fr.pose, facing, self.size, self.anchor, self.style.light,
                           root_offset=tuple(np.round(root_w)), hide=fr.hide,
                           squash=tuple(fr.squash), yaw_offset=yaw_off, widen=widen)
        self._buf = buf                    # kept for the 2D-HD maps (build: spec "maps")
        self._last = (fr, facing, root_w, yaw_off, widen)   # and for attach points / pp inspect
        seams = [i for i, n in enumerate(self.model.order) if self.model.bones[n].seam]
        rgba = finish(self.style, buf, self.mats, seams=seams,
                      crease=float(self.spec.get("shading", {}).get("crease", 0.0)),
                      bone_names=self.model.order)
        self._stamps(rgba, buf, fr, facing, root_w, yaw_off, widen)
        self._strings(rgba, buf, fr, facing, root_w, yaw_off, widen)
        rgba = self._shadow(rgba, buf, root_w)
        behind_fx = [fx for fx in fr.fx if fx.get("kind") == "vfx" and fx.get("behind")]
        if behind_fx:
            under = np.zeros_like(rgba)
            for fx in behind_fx:
                self._vfx(under, fx, root_w, facing)
            m = rgba[..., 3] == 0
            rgba[m] = under[m]
        for fx in fr.fx:
            kind = fx.get("kind")
            if kind == "vfx" and not fx.get("behind"):
                self._vfx(rgba, fx, root_w, facing)
            if kind == "smear" and self.spec.get("smear"):
                draw_smear(rgba, buf.depth, A.Frame(fr.pose, fr.ms, tuple(root_w)), fx, facing, self.anchor,
                           self.style, self.spec["smear"])
            elif kind == "sweep" and "from" in fx:
                self._sweep(rgba, fr, fx, facing, yaw_off, widen)
            elif kind in ("dust", "charge", "burst"):
                self._sprite_fx(rgba, kind, fx, root_w, facing)
        if fr.flash:
            apply_flash(rgba, self.style)
        return rgba

    def _sweep(self, rgba: np.ndarray, fr: A.Frame, fx: Dict, facing: str, yaw_off: float, widen: float) -> None:
        """Smear along the weapon's (or hand's) real path from the previous pose to this one."""
        from .motion import sweep_mask
        bone = next((b for b in self.spec.get("anim", {}).get("smear_hides", ["sword", "weapon"])
                     if b in self.model.bones), None) or ("foreR" if "foreR" in self.model.bones else "armR")
        pose0, root0, sq0 = fx["from"]
        m = sweep_mask(self.model, pose0, root0, fr.pose, fr.root, bone, YAW[facing] + yaw_off, self.size,
                       self.anchor, thick=0.45 if fx.get("tail") else 1.0, squash=tuple(fr.squash), widen=widen,
                       dashed=bool(fx.get("tail")))
        if m.any():
            _smear_fill(rgba, m, self.style, self.spec.get("smear", {}))

    def _stamp_row(self, rgba: np.ndarray, buf: Buffers, bi: int, nrm: np.ndarray, st: Dict, stamped: np.ndarray) -> None:
        """A row of stamps (windows along a wall, a door) laid out on the face AS DRAWN, not as independent 3D points:
          {"shape": "stamp_row", "normal": [0, -1, 0], "at": [0, 0, z], "count": 6, "rows": ["a"], "key": {"a": "window"},
           "margin": 1, "min_pitch": 3, "keep_clear": 1}
        The face is this bone's visible pixels whose normal points along `normal`. The stamps sit at one whole-pixel
        pitch (so the rhythm is even), centred between margins from the face's side edges; a row drops stamps
        rather than crowding them (pitch >= min_pitch). Each stamp's bottom sits z px above the face's drawn bottom
        edge in its own column, so a row runs parallel to that edge and rows on different floors line up in columns.
        A stamp is skipped where any of its pixels is not on the face (under an eave, off the wall), would touch the
        face's top edge, or comes within keep_clear px of something an earlier row drew (the door)."""
        face = (buf.bone == bi) & (buf.mat >= 0)
        face &= np.einsum("hwc,c->hw", buf.normal, nrm) > st.get("face_dot", 0.8)
        cols = np.nonzero(face.any(0))[0]
        if len(cols) < 2:
            return
        rows = st["rows"]
        h, w = len(rows), max(len(r) for r in rows)
        m = int(st.get("margin", 1))
        lo, hi = int(cols.min()) + m, int(cols.max()) - m - (w - 1)
        if hi < lo:
            return
        n = max(1, int(st.get("count", 1)))
        pmin = max(w + 1, int(st.get("min_pitch", 3)))
        n = min(n, (hi - lo) // pmin + 1)
        pitch = (hi - lo) // (n - 1) if n > 1 else 0
        x_start = lo + ((hi - lo) - pitch * (n - 1)) // 2
        z = float(st.get("at", (0, 0, 0))[2])
        clear = int(st.get("keep_clear", 1))
        H, W = face.shape
        mine = np.zeros_like(stamped)
        for k in range(n):
            x0 = x_start + k * pitch
            col = np.nonzero(face[:, x0 + w // 2])[0]
            if not len(col):
                continue
            bottom, top = int(col.max()), int(col.min())
            y_bot = bottom - int(round(z))
            y0 = y_bot - h + 1
            if y0 <= top:                                    # would touch the eave / the face's top edge
                continue
            cells = [(y0 + j, x0 + i, ch) for j, r in enumerate(rows) for i, ch in enumerate(r) if ch in st["key"]]
            if not all(0 <= y < H and 0 <= x < W and face[y, x] for y, x, _ in cells):
                continue
            ya, yb, xa, xb = max(0, y0 - clear), min(H, y_bot + clear + 1), max(0, x0 - clear), min(W, x0 + w + clear)
            if stamped[ya:yb, xa:xb].any():
                continue
            for y, x, ch in cells:
                mname, _, lv = st["key"][ch].partition(":")
                cs = self.style.mat_colors(mname)
                rgba[y, x] = (*(cs[min(int(lv), len(cs) - 1)] if lv else cs[-1]), 255)
                mine[y, x] = True
        stamped |= mine

    def _stamps(self, rgba: np.ndarray, buf: Buffers, fr: A.Frame, facing: str, root_w,
                yaw_off: float = 0.0, widen: float = 1.0) -> None:
        """Pixel stamps: {"shape": "stamp", "at": [x,y,z], "normal": [0,-1,0], "rows": ["ab"],
        "key": {"a": "pupil", "b": "eye_white:0"}} — drawn when the surface faces the viewer and
        is not hidden behind a nearer part. key values are "material" or "material:shade".
        {"shape": "stamp_row", ...} lays a whole row out on the face as drawn (see _stamp_row)."""
        if fr.hide is None:
            return
        world = None
        H, W = buf.mat.shape
        view = -RAY
        stamped = np.zeros((H, W), bool)                      # what stamp rows have drawn: later rows keep clear of it
        for name in self.model.order:
            bone = self.model.bones[name]
            if not bone.stamps or name in fr.hide:
                continue
            if world is None:
                world = self.model.world(fr.pose, YAW[facing] + yaw_off, tuple(fr.squash), widen)
            M, o = world[name]
            for st in bone.stamps:
                nrm = M @ np.asarray(st.get("normal", (0, -1, 0)), float)
                nrm /= np.linalg.norm(nrm) + 1e-9
                if float(nrm @ view) < st.get("min_facing", 0.2):
                    continue
                if st["shape"] == "stamp_row":
                    self._stamp_row(rgba, buf, self.model.order.index(name), nrm, st, stamped)
                    continue
                p = o + M @ np.asarray(st.get("at", (0, 0, 0)), float) + np.asarray(root_w, float)
                cx = self.anchor[0] + p[0]
                cy = self.anchor[1] - (p[2] + K * p[1])
                d = float(p @ RAY)
                rows = st["rows"]
                h, w = len(rows), max(len(r) for r in rows)
                x0 = int(math.floor(cx - w / 2 + 0.5))
                y0 = int(math.floor(cy - h / 2 + 0.5))
                for j, row in enumerate(rows):
                    for i, ch in enumerate(row):
                        if ch in (".", " ") or ch not in st["key"]:
                            continue
                        x, y = x0 + i, y0 + j
                        if not (0 <= x < W and 0 <= y < H):
                            continue
                        if buf.mat[y, x] < 0 and not st.get("overhang"):
                            if not st.get("clamp"):
                                continue
                            # clamp: slide inward (toward the sprite centre line) onto this bone's pixels
                            step = 1 if x < self.anchor[0] + root_w[0] else -1
                            for _ in range(st.get("clamp", 2) if isinstance(st.get("clamp"), int) else 2):
                                x += step
                                if 0 <= x < W and buf.mat[y, x] >= 0:
                                    break
                            if not (0 <= x < W) or buf.mat[y, x] < 0:
                                continue
                        if buf.depth[y, x] < d - st.get("depth_tol", 2.0):
                            continue
                        mname, _, lv = st["key"][ch].partition(":")
                        cols = self.style.mat_colors(mname)
                        c = cols[min(int(lv), len(cols) - 1)] if lv else cols[-1]
                        rgba[y, x] = (*c, 255)

    def _strings(self, rgba: np.ndarray, buf: Buffers, fr: A.Frame, facing: str, root_w,
                 yaw_off: float = 0.0, widen: float = 1.0) -> None:
        """1 px lines between bone points (bowstrings, ropes, chains): spec "strings": [{"name": "bowstring",
        "points": [["bow", [x, y, z]], ["bow", [x, y, z]]], "pull": ["foreR", [x, y, z]], "mat": "trim:1"}].
        On frames that list the string's name in "show", the line bends through the "pull" point (a drawn
        bow). Hidden where a nearer part covers it, and while any of its bones is hidden."""
        strings = self.spec.get("strings")
        if not strings:
            return
        world = self.model.world(fr.pose, YAW[facing] + yaw_off, tuple(fr.squash), widen)
        H, W = buf.mat.shape

        def proj(ref):
            M, o = world[ref[0]]
            p = o + M @ np.asarray(ref[1], float) + np.asarray(root_w, float)
            return self.anchor[0] + p[0], self.anchor[1] - (p[2] + K * p[1]), float(p @ RAY)
        for st in strings:
            pts = list(st["points"])
            if st.get("pull") and st.get("name") in fr.show:
                pts = [pts[0], st["pull"], pts[-1]]
            if any(r[0] in fr.hide for r in pts):
                continue
            mname, _, lv = st.get("mat", "dark").partition(":")
            cols = self.style.mat_colors(mname)
            c = cols[min(int(lv), len(cols) - 1)] if lv else cols[-1]
            P = [proj(r) for r in pts]
            for (x0, y0, d0), (x1, y1, d1) in zip(P, P[1:]):
                n = int(max(abs(x1 - x0), abs(y1 - y0))) + 1
                for k in range(n + 1):
                    u = k / max(1, n)
                    x = int(math.floor(x0 + (x1 - x0) * u + 0.5))
                    y = int(math.floor(y0 + (y1 - y0) * u + 0.5))
                    d = d0 + (d1 - d0) * u
                    if not (0 <= x < W and 0 <= y < H):
                        continue
                    if buf.mat[y, x] >= 0 and buf.depth[y, x] < d - st.get("depth_tol", 1.0):
                        continue
                    rgba[y, x] = (*c, 255)

    def _anchor_point(self, where: str, root_w, facing: str, offset=(0, 0)) -> Tuple[float, float]:
        fxs = self.spec.get("fx", {})
        ax, ay = self.anchor[0] + root_w[0], self.anchor[1] - K * root_w[1]
        yaw = math.radians(YAW[facing])
        fx_, fy_ = math.sin(yaw), -math.cos(yaw)
        reach = fxs.get("reach", 6)
        if where == "feet":
            x, y = ax, ay
        elif where == "front":
            x, y = ax + fx_ * reach * 1.6, ay - K * fy_ * reach * 1.6
        elif where == "hand":
            x, y = ax + fx_ * reach, ay - fxs.get("hand_h", 14) - K * fy_ * reach
        elif where == "above":
            x, y = ax, ay - fxs.get("head_h", 26)
        else:  # centre of the body
            x, y = ax, ay - fxs.get("hand_h", 14)
        return x + offset[0], y + offset[1]

    _vfx_cache: Dict[str, list] = {}

    def _vfx(self, rgba: np.ndarray, fx: Dict, root_w, facing: str) -> None:
        """{"kind": "vfx", "effect": "burst", "frame": 2, "at": "front|hand|feet|centre|above",
        "offset": [dx, dy], "ramp": "glow_pink", "params": {...}, "behind": false}"""
        from .vfx import render_effect
        import json as _json
        ramp_name = fx.get("ramp") or self.spec.get("fx", {}).get("ramp") or \
            next(iter(self.style.spec.get("vfx_ramps", {}).values()))
        from .color import rgb_to_hex
        ramp = [rgb_to_hex(c) for c in self.style.ramps[ramp_name]]
        params = dict(fx.get("params", {}))
        key = _json.dumps([fx["effect"], params, ramp], sort_keys=True)
        if key not in self._vfx_cache:
            self._vfx_cache[key] = render_effect(fx["effect"], params, ramp)
        frames = self._vfx_cache[key]
        f = frames[min(int(fx.get("frame", 0)), len(frames) - 1)]
        x, y = self._anchor_point(fx.get("at", "front"), root_w, facing, fx.get("offset", (0, 0)))
        h, w = f.shape[:2]
        # effects are authored with their "ground/centre" at 55 % height for bursts; use the frame centre
        x0 = int(round(x - w / 2))
        y0 = int(round(y - h * fx.get("pivot_y", 0.55)))
        H, W = rgba.shape[:2]
        sx0, sy0 = max(0, -x0), max(0, -y0)
        sx1, sy1 = min(w, W - x0), min(h, H - y0)
        if sx1 <= sx0 or sy1 <= sy0:
            return
        src = f[sy0:sy1, sx0:sx1]
        dst = rgba[y0 + sy0:y0 + sy1, x0 + sx0:x0 + sx1]
        m = src[..., 3] > 0
        dst[m] = src[m]

    def _sprite_fx(self, rgba: np.ndarray, kind: str, fx: Dict, root_w, facing: str) -> None:
        """Small in-sprite effects drawn with the vfx canvas, palette-locked to the style."""
        from .vfx import Canvas
        H, W = rgba.shape[:2]
        c = Canvas(W, H)
        ax, ay = self.anchor[0] + root_w[0], self.anchor[1] - K * root_w[1]
        fxs = self.spec.get("fx", {})
        if kind == "dust":
            n = fx.get("n", 2)
            # a few ground-tinted puffs trailing behind the feet, lit top + shaded base
            rng = np.random.default_rng(int(abs(ax * 7 + n)))
            yaw = math.radians(YAW[facing])
            bx, by = -math.sin(yaw), math.cos(yaw) * K        # behind the character, on screen
            for i in range(min(n, 5)):
                side = -1 if i % 2 == 0 else 1
                r = rng.uniform(0.9, 1.5)
                x = ax + bx * rng.uniform(3, 6) + side * rng.uniform(1.5, 4)
                y = ay - rng.uniform(0.5, 2.0) + by * 2
                c.disc(x, y, r, 0.45)
                c.disc(x - 0.4, y - r * 0.4, r * 0.6, 0.95)
            dust = hex_to_rgb(self.style.spec.get("dust", "#74787a"))
            shade_c = hex_to_rgb(self.style.spec.get("shadow_color", "#1f1a2a"))
            ramp = [shade_c, dust]            # both are style colours: the palette lock holds
        else:
            yaw = math.radians(YAW[facing])
            fwd = np.array([math.sin(yaw), -math.cos(yaw)])     # screen x, world y
            hx = ax + fwd[0] * fxs.get("reach", 6)
            hy = ay - fxs.get("hand_h", 14) - K * fwd[1] * fxs.get("reach", 6)
            t = fx.get("t", 0.0)
            if kind == "charge":
                c.disc(hx, hy, 1 + 3 * t, 1.0)
                for k in range(4):
                    a = k * math.pi / 2 + t * 3
                    rr = 9 * (1 - t) + 2
                    c.dot(hx + rr * math.cos(a), hy + rr * math.sin(a) * 0.7, 2 if t < 0.5 else 1, 0.8)
            else:
                r = 4 + 10 * t
                c.ring(hx, hy, r, max(1, 3 - 3 * t), 1.0 - 0.5 * t, squash=0.8)
                if t < 0.1:
                    c.disc(hx, hy, 5, 1.0)
            ramp_name = fxs.get("ramp") or self.style.spec.get("vfx_ramps", {}).get("cyan")
            ramp = self.style.ramps[ramp_name] if ramp_name in self.style.ramps else [(255, 255, 255)]
        layer = c.to_rgba(ramp)
        m = layer[..., 3] > 0
        rgba[m] = layer[m]

    def _shadow(self, rgba: np.ndarray, buf: Buffers, root_w=(0.0, 0.0, 0.0)) -> np.ndarray:
        """Ground ellipse under the body: follows the root across the ground (lunges, falls) and
        shrinks while the body is off the ground (hops, hovering)."""
        sh = self.spec.get("shadow")
        if not sh:
            return rgba
        col = hex_to_rgb(self.style.spec.get("shadow_color", "#1f1a2a"))
        lift = max(0.0, float(root_w[2]))
        k = max(0.55, 1.0 - 0.06 * lift)
        w, h = sh.get("w", 13) * k, max(2.0, sh.get("h", 4) * k)
        cx = self.anchor[0] + math.floor(float(root_w[0]) + 0.5)
        cy = self.anchor[1] + math.floor(-K * float(root_w[1]) + 0.5)
        H, W = buf.mat.shape
        ys, xs = np.mgrid[0:H, 0:W]
        e = ((xs + 0.5 - cx) / (w / 2)) ** 2 + ((ys + 0.5 - cy) / (h / 2)) ** 2 <= 1
        m = e & (rgba[..., 3] == 0)
        rgba[m] = (*col, 255)
        return rgba

    HEIGHT_SCALE = 4   # height maps store px above the feet x 4 (quarter-pixel steps, up to 63.75 px)

    def _maps(self, which: List[str]) -> Dict[str, np.ndarray]:
        """2D-HD maps of the last rendered frame, from the G-buffer: normal (RGB = world normal * 0.5 + 0.5,
        x right, y away from the viewer, z up) and height (grey = px above the feet x HEIGHT_SCALE). Alpha = 255
        on the model's own pixels (not the ground shadow or in-sprite fx)."""
        buf = self._buf
        on = buf.mat >= 0
        out = {}
        if "normal" in which:
            n = np.zeros(buf.mat.shape + (4,), np.uint8)
            n[..., :3] = np.clip(np.round((buf.normal * 0.5 + 0.5) * 255), 0, 255).astype(np.uint8)
            n[..., 3] = np.where(on, 255, 0)
            n[~on, :3] = 0
            out["normal"] = n
        if "height" in which:
            h = np.zeros(buf.mat.shape + (4,), np.uint8)
            v = np.clip(np.round(buf.height * self.HEIGHT_SCALE), 0, 255).astype(np.uint8)
            h[..., 0] = h[..., 1] = h[..., 2] = np.where(on, v, 0)
            h[..., 3] = np.where(on, 255, 0)
            out["height"] = h
        return out

    def attach_spec(self, want=None) -> Dict[str, Tuple[str, object]]:
        """Named points a game (or pp inspect) needs per frame. spec "attach": true = the defaults below;
        a dict adds/overrides {"name": ["bone", "tip" | "joint" | "centre" | [x, y, z]]} (xyz in bone space).
        `want` replaces the spec's value (pp inspect asks for the defaults on any spec)."""
        want = self.spec.get("attach") if want is None else want
        if not want:
            return {}
        bones = self.model.bones
        out: Dict[str, Tuple[str, object]] = {}
        if "head" in bones:
            out["head"] = ("head", "centre")
        for side in "RL":
            b = next((n for n in ("fore" + side, "arm" + side) if n in bones), None)
            if b:
                out["hand_" + side] = (b, "tip")
        w = next((b for b in self.spec.get("anim", {}).get("smear_hides", ["sword", "weapon"]) if b in bones), None)
        if w:
            out["weapon_tip"] = (w, "tip")
        if isinstance(want, dict):
            out.update({k: (v[0], v[1]) for k, v in want.items() if v and v[0] in bones})
        return out

    def attach_points(self, points: Dict[str, Tuple[str, object]]) -> Dict[str, list]:
        """Screen px of each attach point in the LAST rendered frame: [x, y, visible], plus "feet" and
        "box" (bbox of the model's own pixels, x0 y0 x1 y1 inclusive; [] when empty)."""
        from .motion import blade_span
        from .render import _bounds
        fr, facing, root_w, yaw_off, widen = self._last
        buf = self._buf
        world = self.model.world(fr.pose, YAW[facing] + yaw_off, tuple(fr.squash), widen)
        H, W = buf.mat.shape
        out: Dict[str, list] = {}
        for name, (bone, where) in points.items():
            M, o = world[bone]
            if where == "joint":
                loc = np.zeros(3)
            elif where == "tip":
                loc = blade_span(self.model, bone)[1]
            elif where == "centre":
                loc = _bounds(self.model.bones[bone].parts)[0] if self.model.bones[bone].parts else np.zeros(3)
            else:
                loc = np.asarray(where, float)
            p = o + M @ loc + np.asarray(root_w, float)
            x = int(math.floor(self.anchor[0] + p[0] + 0.5))
            y = int(math.floor(self.anchor[1] - (p[2] + K * p[1]) + 0.5))
            bi = self.model.order.index(bone)
            vis = int(0 <= x < W and 0 <= y < H and buf.bone[y, x] == bi)
            out[name] = [x, y, vis]
        out["feet"] = [int(self.anchor[0] + math.floor(float(root_w[0]) + 0.5)),
                       int(self.anchor[1] + math.floor(-K * float(root_w[1]) + 0.5)), 1]
        ys, xs = np.nonzero(buf.mat >= 0)
        out["box"] = [int(xs.min()), int(ys.min()), int(xs.max()), int(ys.max())] if len(xs) else []
        return out

    def build(self, out_dir, directions: Optional[List[str]] = None, preview_scale: int = 4,
              maps: Optional[List[str]] = None) -> Dict:
        maps = list(maps if maps is not None else self.spec.get("maps", []))
        out = Path(out_dir)
        out.mkdir(parents=True, exist_ok=True)
        dirs = directions or self.spec.get("directions", DIRECTIONS)
        meta = {"name": self.spec["name"], "style": self.style.name, "frame_w": self.size[0],
                "frame_h": self.size[1], "anchor": list(self.anchor), "directions": dirs, "clips": {}}
        from .size import measure, size_label
        meta["height_px"], meta["width_px"] = measure(self.spec, self.style)
        meta["size"] = size_label(self.spec)
        if abs(self.size_k - 1) > 1e-6:
            meta["size_scale"] = round(self.size_k, 4)
        contact_rows = []
        if maps:
            meta["height_scale"] = self.HEIGHT_SCALE
        points = self.attach_spec()
        if points:
            meta["attach"] = {k: list(v) for k, v in points.items()}
        for clip in self.clips():
            rows = []
            map_rows = {m: [] for m in maps}
            att = {}
            for d in dirs:
                row = []
                mrow = {m: [] for m in maps}
                for f in clip.frames:
                    row.append(self.frame(f, d))
                    if points:
                        att.setdefault(d, []).append(self.attach_points(points))
                    if maps:
                        for m, img in self._maps(maps).items():
                            mrow[m].append(img)
                rows.append(row)
                for m in maps:
                    map_rows[m].append(mrow[m])
                save_gif(row, [f.ms for f in clip.frames], out / "gif" / f"{clip.name}_{d}.gif",
                         scale=preview_scale, bg=tuple(hex_to_rgb(self.style.spec.get("bg", "#3a3e4a"))))
            sheet = pack_sheet(rows)
            save_png(sheet, out / f"{self.spec['name']}_{clip.name}.png")
            meta["clips"][clip.name] = {"loop": clip.loop, "speed_px_per_cycle": clip.speed_px,
                                        "frames": [{"ms": f.ms, "event": f.event} for f in clip.frames],
                                        "sheet": f"{self.spec['name']}_{clip.name}.png",
                                        "layout": "rows=directions, cols=frames"}
            if points:
                meta["clips"][clip.name]["attach"] = att      # dir -> per frame {name: [x, y, visible]}
            if maps:
                meta["clips"][clip.name]["maps"] = {}
                for m in maps:
                    fn = f"{self.spec['name']}_{clip.name}_{m}.png"
                    save_png(pack_sheet(map_rows[m]), out / fn)
                    meta["clips"][clip.name]["maps"][m] = fn
            contact_rows.append((clip.name, sheet))
        (out / f"{self.spec['name']}.json").write_text(json.dumps(meta, indent=1))
        # contact sheet (all clips stacked) on the style background
        bg = hex_to_rgb(self.style.spec.get("bg", "#3a3e4a"))
        wmax = max(s.shape[1] for _, s in contact_rows)
        stack = np.concatenate([np.pad(s, ((0, 2), (0, wmax - s.shape[1]), (0, 0))) for _, s in contact_rows], 0)
        save_png(compose_bg(stack, bg), out / "contact.png", scale=3)
        return meta

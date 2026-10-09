"""G-buffer -> locked-palette pixels: shade levels, outlines, inner lines, cleanup."""
from __future__ import annotations

from typing import Dict, List

import numpy as np

from .color import hex_to_rgb
from .render import Buffers

N4 = [(-1, 0), (1, 0), (0, -1), (0, 1)]
N8 = N4 + [(-1, -1), (-1, 1), (1, -1), (1, 1)]


def shift(a: np.ndarray, dy: int, dx: int, fill) -> np.ndarray:
    """out[y, x] = a[y + dy, x + dx]"""
    out = np.full_like(a, fill)
    H, W = a.shape[:2]
    ys = slice(max(0, -dy), min(H, H - dy))
    xs = slice(max(0, -dx), min(W, W - dx))
    ys2 = slice(max(0, dy), min(H, H + dy))
    xs2 = slice(max(0, dx), min(W, W + dx))
    out[ys, xs] = a[ys2, xs2]
    return out


class Style:
    def __init__(self, spec: Dict):
        self.spec = spec
        self.name = spec["name"]
        L = np.asarray(spec.get("light", [-0.55, -0.42, 0.72]), float)
        self.light = L / np.linalg.norm(L)
        self.ramps: Dict[str, List[tuple]] = {k: [hex_to_rgb(h) for h in v] for k, v in spec["ramps"].items()}
        self.materials: Dict[str, Dict] = dict(spec["materials"])
        self.thresholds: List[float] = spec.get("thresholds", [0.30, 0.58, 0.86])
        self.outline = spec.get("outline", {"mode": "self"})
        self.inner_lines = spec.get("inner_lines", True)

    def add_materials(self, extra: Dict) -> None:
        self.materials.update(extra or {})

    def material_list(self) -> List[str]:
        return list(self.materials.keys())

    def palette(self) -> List[tuple]:
        seen, out = set(), []
        for r in self.ramps.values():
            for c in r:
                if c not in seen:
                    seen.add(c)
                    out.append(c)
        return out

    def mat_colors(self, m: str) -> List[tuple]:
        spec = self.materials[m]
        ramp = self.ramps[spec["ramp"]]
        return [ramp[i] for i in spec.get("shades", range(len(ramp)))]


def shade_levels(style: Style, buf: Buffers, mats: List[str]) -> np.ndarray:
    """Light value -> discrete level per material (0 = darkest used shade)."""
    lvl = np.zeros(buf.mat.shape, np.int16)
    t = buf.light * 0.5 + 0.5          # half-lambert
    for mi, m in enumerate(mats):
        sel = buf.mat == mi
        if not sel.any():
            continue
        n = len(style.mat_colors(m))
        spec = style.materials[m]
        th = spec.get("thresholds") or _thresholds_for(style.thresholds, n)
        if spec.get("emissive"):
            # glow reads as flat light: brightest shade, one step down where it turns away
            lvl[sel] = np.where(t[sel] > 0.35, n - 1, max(0, n - 2))
            continue
        bias = spec.get("bias", 0.0)
        tl = t[sel] + bias
        # sky light: tops of each part catch more light, undersides fall into shadow
        if spec.get("sky") and buf.hnorm is not None:
            tl = tl + spec["sky"] * (buf.hnorm[sel] - 0.5)
        if spec.get("sky_obj") and buf.height is not None:
            hh = buf.height[sel]
            tl = tl + spec["sky_obj"] * ((hh - hh.min()) / max(float(np.ptp(hh)), 1e-3) - 0.5)
        lv = np.searchsorted(np.asarray(th), tl)
        # cap the highlight plateau per part: on big parts the lightest shade is a small cluster
        # (<= 15 %) and the top two shades <= 60 %, so forms stop reading as shaded balls (review #10)
        if spec.get("rank", True) and n >= 3:
            bones_here = buf.bone[sel]
            for b in np.unique(bones_here):
                part = bones_here == b
                if part.sum() < style.spec.get("rank_min_area", 60):
                    continue
                tp = tl[part]
                lp = lv[part]
                for top_levels, frac in ((1, 0.15), (2, 0.60)):
                    cut = n - top_levels
                    over = lp >= cut
                    if over.mean() > frac:
                        q = np.quantile(tp, 1 - frac)
                        lp = np.where(over & (tp < q), cut - 1, lp)
                lv[part] = lp
        lvl[sel] = lv
    return lvl


def _thresholds_for(base: List[float], n: int) -> List[float]:
    if n - 1 == len(base):
        return base
    return list(np.linspace(0.3, 0.86, n - 1)) if n > 1 else []


def finish(style: Style, buf: Buffers, mats: List[str], cleanup: bool = True, seams=(), crease: float = 0.0,
           bone_names: List[str] = None) -> np.ndarray:
    """-> (H, W, 4) RGBA using only the style's palette."""
    from .detail import edges as detail_edges, surface as detail_surface
    detail_edges(style, buf, mats)              # silhouette tufts / notches (fur, feathers, leaves)
    H, W = buf.mat.shape
    filled = buf.mat >= 0
    lvl = shade_levels(style, buf, mats)

    if cleanup:
        lvl = _despeckle(buf.mat, lvl)
    lvl = detail_surface(style, buf, mats, lvl)  # material patterns, painted in part space

    # crease lines: inside one part, where the surface turns sharply, the darker side gets a line
    if crease:
        ln = buf.light
        cl = np.zeros_like(filled)
        for dy, dx in N4:
            nn = shift(buf.normal, dy, dx, 0.0)
            nb = shift(buf.bone, dy, dx, -1)
            nl = shift(ln, dy, dx, 9.0)
            turn = np.einsum("ijk,ijk->ij", buf.normal, nn) < crease
            cl |= filled & (nb == buf.bone) & turn & (ln < nl - 0.05)
        for mi, m in enumerate(mats):
            if style.materials[m].get("emissive") or style.materials[m].get("no_outline"):
                cl &= buf.mat != mi
        lvl = np.where(cl, 0, lvl)

    # seam bones: always separated from any bone they overlap (pine tiers, armour plates)
    seam_px = np.isin(buf.bone, list(seams)) if len(seams) else np.zeros_like(filled)

    # inner lines: pixels behind a clearly-closer neighbour of another bone
    if style.inner_lines:
        thr = float(style.spec.get("inner_line_depth", 2.5))
        behind = np.zeros_like(filled)
        for dy, dx in N4:
            nd = shift(buf.depth, dy, dx, np.inf)
            nb = shift(buf.bone, dy, dx, -1)
            nm = shift(buf.mat, dy, dx, -1)
            ns = shift(seam_px, dy, dx, False)
            t_here = np.where(seam_px | ns, 0.3, thr)
            behind |= filled & (nb >= 0) & (nb != buf.bone) & (buf.depth - nd > t_here) & \
                ((nm != buf.mat) | seam_px | ns)
        # same-material seams (foliage clumps, rock slabs) break every few px instead of ruling a line (#11)
        same_m = np.zeros_like(filled)
        for dy, dx in N4:
            same_m |= (shift(buf.mat, dy, dx, -1) == buf.mat) & (shift(buf.bone, dy, dx, -1) != buf.bone) & \
                (buf.depth - shift(buf.depth, dy, dx, np.inf) > 0.3)
        behind &= ~same_m | (_hash2(buf.local, 1.5, 81.0) < 0.5)
        lvl = np.where(behind, 0, lvl)

    # contact shadow: a nearer part up-light of this pixel casts one level of shadow on it
    cs = style.spec.get("contact_shadow", 2)
    if cs:
        thr = float(style.spec.get("contact_depth", 1.5))
        shaded = np.zeros_like(filled)
        for k in range(1, cs + 1):
            for dy, dx in ((-k, -k), (-k, 0), (0, -k)):
                nd = shift(buf.depth, dy, dx, np.inf)
                nb = shift(buf.bone, dy, dx, -1)
                ns = shift(seam_px, dy, dx, False)
                shaded |= filled & (nb >= 0) & (nb != buf.bone) & \
                    (buf.depth - nd > np.where(seam_px | ns, 0.3, thr))
        # between clumps of one material the shadow is dashed, not a ruled line (review #11)
        nbm = np.full(buf.mat.shape, -1, np.int16)
        for dy, dx in ((-1, 0), (0, -1), (-1, -1)):
            nbm = np.where(nbm >= 0, nbm, np.where(shift(buf.bone, dy, dx, -1) != buf.bone,
                                                   shift(buf.mat, dy, dx, -1), -1))
        same = (nbm == buf.mat) & ~seam_px
        dash = _hash2(buf.local, 2.0, 71.0) < 0.55
        shaded &= ~same | dash
        lvl = np.where(shaded, np.maximum(lvl - 1, 0), lvl)

    # value separation (review #12a): touching parts of one material at the same shade get a
    # step darker on the farther side, so arms don't melt into torsos (skipped for foliage)
    sep = np.zeros_like(filled)
    for dy, dx in N4:
        nb = shift(buf.bone, dy, dx, -1)
        nm = shift(buf.mat, dy, dx, -1)
        nl = shift(lvl, dy, dx, -9)
        nd = shift(buf.depth, dy, dx, np.inf)
        sep |= filled & (nb >= 0) & (nb != buf.bone) & (nm == buf.mat) & (nl == lvl) & (buf.depth - nd > 0.8)
    for mi, m in enumerate(mats):
        det = style.materials[m].get("detail") or {}
        if det.get("kind") == "leaf" or style.materials[m].get("emissive"):
            sep &= buf.mat != mi
    lvl = np.where(sep, np.maximum(lvl - 1, 0), lvl)

    # far-side limbs (review #14): of a left/right pair, the one farther from the viewer is a step darker
    lvl = _far_limbs(buf, lvl, bone_names or [])

    mode = style.outline.get("mode", "self")
    edge = np.zeros_like(filled)
    for dy, dx in N4:
        edge |= filled & ~shift(filled, dy, dx, False)
    bottom = filled & ~shift(filled, 1, 0, False)
    out = np.zeros((H, W, 4), np.uint8)
    for mi, m in enumerate(mats):
        cols = style.mat_colors(m)
        sel = buf.mat == mi
        if not sel.any():
            continue
        lv = np.clip(lvl, 0, len(cols) - 1)
        for li, c in enumerate(cols):
            s = sel & (lv == li)
            out[s] = (*c, 255)
        if not style.materials[m].get("no_outline"):
            # edges mostly keep their fill; shadow-side and bottom edges drop to the
            # darkest shade, light-side edges get one step of rim light.
            ndl = buf.normal @ style.light
            dark = sel & edge & ((ndl < style.outline.get("dark_below", 0.05)) | bottom)
            out[dark] = (*cols[0], 255)
            rim = sel & edge & ~dark & (ndl > style.outline.get("rim_above", 0.6))
            rl = np.clip(lv + 1, 0, len(cols) - 1)
            for li, c in enumerate(cols):
                out[rim & (rl == li)] = (*c, 255)
    _lift_against_bg(style, out, buf, mats, lvl, edge)
    if cleanup:
        protect = np.zeros_like(filled)
        for mi, m in enumerate(mats):
            if style.materials[m].get("no_outline") or style.materials[m].get("emissive"):
                protect |= buf.mat == mi
        out = despeckle_rgba(out, protect)
    if mode == "outer":
        col = hex_to_rgb(style.outline.get("color", "#1a1420"))
        ring = np.zeros_like(filled)
        nbrs = N8 if style.outline.get("corners") else N4
        for dy, dx in nbrs:
            ring |= ~filled & shift(filled, dy, dx, False)
        out[ring] = (*col, 255)
    return out


def _despeckle(mat: np.ndarray, lvl: np.ndarray) -> np.ndarray:
    """Remove isolated single shade pixels (no 4-neighbour of the same level+material)."""
    key = np.where(mat >= 0, mat.astype(np.int32) * 16 + lvl, -1)
    same = np.zeros(mat.shape, np.int32)
    for dy, dx in N4:
        same += shift(key, dy, dx, -2) == key
    lone = (mat >= 0) & (same == 0)
    if not lone.any():
        return lvl
    out = lvl.copy()
    for y, x in zip(*np.nonzero(lone)):
        cand = {}
        for dy, dx in N4:
            yy, xx = y + dy, x + dx
            if 0 <= yy < mat.shape[0] and 0 <= xx < mat.shape[1] and mat[yy, xx] == mat[y, x]:
                cand[lvl[yy, xx]] = cand.get(lvl[yy, xx], 0) + 1
        if cand:
            out[y, x] = max(cand, key=cand.get)
    return out


def despeckle_rgba(img: np.ndarray, protect: np.ndarray, passes: int = 2) -> np.ndarray:
    """Final pass: a pixel whose colour matches none of its 4 neighbours is noise unless it is a
    protected detail (eyes, glow). Replace it with the most common neighbour colour."""
    out = img.copy()
    H, W = out.shape[:2]
    for _ in range(passes):
        a = out[..., 3] > 0
        k = np.where(a, (out[..., 0].astype(np.int32) << 16) | (out[..., 1].astype(np.int32) << 8) | out[..., 2], -1)
        same = np.zeros(k.shape, np.int32)
        for dy, dx in N8:                       # a diagonal twin keeps a 1-px line alive
            same += shift(k, dy, dx, -2) == k
        lone = a & (same == 0) & ~protect
        if not lone.any():
            break
        for y, x in zip(*np.nonzero(lone)):
            cand = {}
            for dy, dx in N4:
                yy, xx = y + dy, x + dx
                if 0 <= yy < H and 0 <= xx < W and k[yy, xx] >= 0:
                    cand[k[yy, xx]] = cand.get(k[yy, xx], 0) + 1
            n_in = sum(cand.values())
            if n_in >= 3:        # interior noise only; keep 1-px silhouette tips
                best = max(cand, key=cand.get)
                out[y, x, :3] = ((best >> 16) & 255, (best >> 8) & 255, best & 255)
    return out


def _hash2(p: np.ndarray, size: float, seed: float) -> np.ndarray:
    q = np.floor(p / size)
    v = np.sin(q[..., 0] * 127.1 + q[..., 1] * 311.7 + q[..., 2] * 74.7 + seed * 19.19) * 43758.5453
    return v - np.floor(v)


def _pair(name: str):
    """legL <-> legR, legFL <-> legFR, armL <-> armR, foreL <-> foreR ..."""
    for a, b in (("L", "R"), ("R", "L")):
        if name.endswith(a):
            return name[:-1] + b
    return None


def _far_limbs(buf: Buffers, lvl: np.ndarray, names: List[str]) -> np.ndarray:
    if not names:
        return lvl
    idx = {n: i for i, n in enumerate(names)}
    out = lvl
    for n, i in idx.items():
        j = idx.get(_pair(n) or "")
        if j is None or j < i:
            continue
        mi, mj = buf.bone == i, buf.bone == j
        if not mi.any() or not mj.any():
            continue
        di, dj = float(np.median(buf.depth[mi])), float(np.median(buf.depth[mj]))
        if abs(di - dj) < 1.5:
            continue                                   # side by side (front/back views): no cheat
        far = mi if di > dj else mj
        out = np.where(far, np.maximum(out - 1, 0), out)
    return out


def _lift_against_bg(style, out: np.ndarray, buf: Buffers, mats: List[str], lvl: np.ndarray, edge: np.ndarray):
    """Dark styles (review #12c): silhouette pixels that nearly vanish into the background move
    one shade lighter, so a dark body keeps its outline on its own ground."""
    from .color import rgb_to_oklab
    bg = style.spec.get("bg")
    if not bg or style.spec.get("min_bg_contrast", 0.06) <= 0:
        return
    bgL = float(rgb_to_oklab(np.array(hex_to_rgb(bg)))[0])
    thr = float(style.spec.get("min_bg_contrast", 0.06))
    ys, xs = np.nonzero(edge)
    if len(ys) == 0:
        return
    L = rgb_to_oklab(out[ys, xs, :3].astype(np.float64))[:, 0]
    weak = np.abs(L - bgL) < thr
    for y, x in zip(ys[weak], xs[weak]):
        mi = buf.mat[y, x]
        if mi < 0:
            continue
        cols = style.mat_colors(mats[mi])
        cur = tuple(out[y, x, :3])
        k = cols.index(cur) if cur in cols else int(lvl[y, x])
        if k + 1 < len(cols):
            out[y, x, :3] = cols[k + 1]

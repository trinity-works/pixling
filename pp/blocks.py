"""Block tokens: tiny board pieces built from a few chunky voxels, drawn in the scene's exact 2:1 iso.

A tactics piece on an iso board must stand *in* the board's perspective and stay small next to it: a flat
side-view sprite pasted on an iso tile reads as a sticker, and anything near a tile wide swamps the map.
A block token is the abstract answer: 2-5 voxels a side, each voxel `vox` lattice units (2 units = a 4 px wide
cube), with flat faces lit like every other iso prop (top light, +x face mid, +y face dark), one feature
(ears, horn, cap, wings) and two eye pixels. Facings are true rotations of the model (E, S, W, N = screen SE,
SW, NW, NE): the back shows when the piece walks away, as on the board's houses.

Projection (pp.iso's): screen (x - y, (x + y)/2 - z), lattice units, the token's footprint centred on the tile
centre (lattice (0, 0, 0) = the anchor). Each pixel centre shoots the view ray (1, 1, 1) and takes the face of the
first voxel it hits, so edges are exact 2:1 pixel lines with no polygon coverage noise.

Spec (JSON):
    {"name": "pip", "vox": 2,
     "palette": {"a": ["#top", "#right", "#left"], "e": "#c8ff4a"},   # a 1-colour role is flat on every face
     "layers": [                   # bottom to top; each layer is rows y = 0.. (back to front on the left),
       ["aaa", "aaa", "aaa"],      # columns x = 0.. (the piece faces +x: the right end of a row is its front)
       ["aa.", "aae", "aa."]],
     "lift": 0,                    # flyers float `lift` lattice units over their shadow
     "glow": {"e": "E"},           # role swaps in the cast glow frames
     "parts": {"top": 1},          # layers >= this move on idle/attack lean (default 1: the feet stay)
     "cast": true}                 # include the cast clip (familiars)

Clips (frame ops in lattice units): idle (breath: the body above `parts.top` sinks 1), move (hop), attack (lean
back, lunge 3 forward = the `hit` frame), hurt (flash + knock back), cast (rise, glow = the `cast` frame).
`BlockPiece.sheet(clip)` gives rows E, S, W, N; `shadow(facing)` the long flat cast shadow (light [0, -1, 1]:
everything falls toward screen down-left, z units become +y units on the ground).
CLI: pixling blocks SPEC [SPEC ...] [--out DIR] [--bg HEX] [--lineup PNG] [--scale N]
                    [--on SCENE.png --at X,Y --step DX,DY --ink HEX]
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import numpy as np

from .color import hex_to_rgb
from .io import pack_sheet, save_gif, save_png

Frame = np.ndarray
FACINGS = ("E", "S", "W", "N")
# the facing's forward vector in lattice x, y
FORWARD = {"E": (1, 0), "S": (0, 1), "W": (-1, 0), "N": (0, -1)}

DEFAULT_CLIPS: Dict[str, dict] = {
    "idle": {"loop": True, "frames": [{"ms": 520}, {"sink": 1, "ms": 520}]},
    "move": {"loop": True, "frames": [{"z": 2, "ms": 70}, {"z": 4, "ms": 70}, {"z": 2, "ms": 70}, {"sink": 1, "ms": 70}]},
    "attack": {"loop": False, "frames": [{"lean": -1, "sink": 1, "ms": 140}, {"lean": 3, "ms": 80},
                                         {"lean": 3, "ms": 140}, {"lean": 1, "ms": 90}, {"ms": 90}]},
    "hurt": {"loop": False, "frames": [{"flash": "#ffffff", "push": -2, "ms": 70}, {"push": -1, "sink": 1, "ms": 120},
                                       {"ms": 120}]},
    "cast": {"loop": False, "frames": [{"sink": 1, "ms": 140}, {"z": 2, "glow": True, "ms": 140},
                                       {"z": 3, "glow": True, "ms": 160}, {"ms": 120}]},
}


def load(spec_path) -> dict:
    return json.loads(Path(spec_path).read_text())


def _faces(v) -> Tuple[Tuple[int, int, int], ...]:
    """A role's colours: [top, right (+x face), left (+y face)] or one hex for every face."""
    vs = [v] * 3 if isinstance(v, str) else list(v) + [v[-1]] * (3 - len(v))
    return tuple(hex_to_rgb(h) for h in vs[:3])


class BlockPiece:
    def __init__(self, spec: dict):
        self.spec = spec
        self.name = spec["name"]
        self.vox = int(spec.get("vox", 2))
        self.ink = spec.get("ink", "#14101c")
        self.lift = int(spec.get("lift", 0))
        self.pal = {k: _faces(v) for k, v in spec["palette"].items()}
        self.pal.setdefault("k", _faces(self.ink))
        layers = spec["layers"]
        nz, ny = len(layers), max(len(l) for l in layers)
        nx = max(len(r) for l in layers for r in l)
        g = np.full((nx, ny, nz), "", dtype=object)
        for z, layer in enumerate(layers):
            for y, row in enumerate(layer):
                for x, ch in enumerate(row):
                    if ch not in ". ":
                        g[x, y, z] = ch
        self.grid = g
        self.top = int(spec.get("parts", {}).get("top", 1 if nz > 1 else 0))
        self.glow = spec.get("glow", {})
        clips = {k: dict(v) for k, v in DEFAULT_CLIPS.items() if k != "cast" or spec.get("cast")}
        for k, v in spec.get("clips", {}).items():
            clips[k] = v if isinstance(v, dict) else {"loop": clips.get(k, {}).get("loop", True), "frames": v}
        self.clips = clips
        # one frame size for every facing and clip: the footprint's bounding circle plus headroom for hops
        s = self.vox
        half = int(np.ceil(np.hypot(nx, ny) * s / 2)) + 4  # lattice units from centre to any corner, + lunge
        self.w = 4 * half + 2
        self.hz = nz * s + self.lift + 6  # tallest point incl. the hop
        self.h = 2 * half + self.hz + 2
        self.anchor = [self.w // 2, self.hz + half + 1]

    # ── model ──────────────────────────────────────────────────────────────────────────────────────────
    def boxes(self, facing: str, op: dict) -> List[Tuple[np.ndarray, np.ndarray, str]]:
        """Every voxel as (lo, hi, role) in lattice units, rotated to `facing`, transformed by the frame op."""
        g = self.grid
        k = FACINGS.index(facing)  # quarter turns from E (x forward) toward S (y forward)
        nx, ny, nz = g.shape
        s = self.vox
        fx, fy = FORWARD[facing]
        lean, push = int(op.get("lean", 0)), int(op.get("push", 0))
        lo_z = int(op.get("z", 0)) + self.lift
        out = []
        for (x, y, z), role in np.ndenumerate(g):
            if not role:
                continue
            # model coordinates centred on the footprint centre (E facing), voxel corner at (cx, cy)
            cx, cy = x * s - nx * s / 2, y * s - ny * s / 2
            # rotate the box's two corners by k quarter turns (x, y) -> (-y, x)
            corners = [(cx, cy), (cx + s, cy + s)]
            for _ in range(k):
                corners = [(-b, a) for a, b in corners]
            (ax, ay), (bx, by) = corners
            lo = np.array([min(ax, bx), min(ay, by), z * s + lo_z], float)
            hi = np.array([max(ax, bx), max(ay, by), (z + 1) * s + lo_z], float)
            body = z >= self.top
            d = push + (lean if body else 0)
            lo[0] += d * fx; hi[0] += d * fx
            lo[1] += d * fy; hi[1] += d * fy
            if body and op.get("sink"):
                lo[2] -= int(op["sink"]); hi[2] -= int(op["sink"])
                if z == self.top:
                    lo[2] = min(lo[2] + int(op["sink"]), hi[2] - 1)  # the waist folds, it never pokes into the feet
            if op.get("glow") and role in self.glow:
                role = self.glow[role]
            out.append((lo, hi, role))
        return out

    # ── raster ─────────────────────────────────────────────────────────────────────────────────────────
    def frame(self, facing: str = "E", op: Optional[dict] = None, palette: Optional[dict] = None) -> Frame:
        op = op or {}
        pal = dict(self.pal)
        for k, v in (palette or {}).items():
            pal[k] = _faces(v)
        H, W = self.h, self.w
        ax, ay = self.anchor
        py, px = np.mgrid[0:H, 0:W]
        u = px + 0.5 - ax
        v = py + 0.5 - ay
        # the view ray through each pixel centre: (x0 + t, y0 + t, t), t grows toward the viewer
        x0, y0 = v + u / 2, v - u / 2
        best = np.full((H, W), -np.inf)
        col = np.zeros((H, W, 3), np.uint8)
        hit = np.zeros((H, W), bool)
        for lo, hi, role in self.boxes(facing, op):
            t_in = np.maximum(np.maximum(lo[0] - x0, lo[1] - y0), lo[2])
            ex, ey, ez = hi[0] - x0, hi[1] - y0, np.full_like(x0, hi[2])
            t_out = np.minimum(np.minimum(ex, ey), ez)
            m = (t_out > t_in) & (t_out > best)
            if not m.any():
                continue
            # the face the ray enters through (the smallest exit term): 0 top (z), 1 right (+x), 2 left (+y)
            f = np.where(ez <= np.minimum(ex, ey), 0, np.where(ex <= ey, 1, 2))
            tones = np.array(pal.get(role, pal["k"]), np.uint8)
            best[m] = t_out[m]
            col[m] = tones[f[m]]
            hit |= m
        img = np.zeros((H, W, 4), np.uint8)
        img[..., :3] = col
        img[..., 3] = np.where(hit, 255, 0)
        if op.get("flash"):
            fc = hex_to_rgb(op["flash"])
            ink = np.array(self.pal["k"][0], np.uint8)
            keep = (img[..., :3] == ink).all(axis=-1)
            img[hit & ~keep, :3] = fc
        return img

    def clip(self, name: str, facing: str = "E", palette: Optional[dict] = None) -> Tuple[List[Frame], List[int], bool]:
        c = self.clips[name]
        frames = [self.frame(facing, op, palette) for op in c["frames"]]
        return frames, [int(op.get("ms", 100)) for op in c["frames"]], bool(c.get("loop", True))

    def sheet(self, name: str, palette: Optional[dict] = None) -> Frame:
        """Rows E, S, W, N; columns = the clip's frames."""
        return pack_sheet([self.clip(name, f, palette)[0] for f in FACINGS])

    def events(self, clip: str) -> List[dict]:
        c = self.clips[clip]
        if c.get("events") is not None:
            return list(c["events"])
        fr = c["frames"]
        if clip == "attack":
            i = next((k for k, op in enumerate(fr) if int(op.get("lean", 0)) > 1), None)
            return [{"frame": i, "name": "hit"}] if i is not None else []
        if clip == "cast":
            i = next((k for k, op in enumerate(fr) if op.get("glow")), None)
            return [{"frame": i, "name": "cast"}] if i is not None else []
        return []

    def shadow(self, facing: str = "E") -> Frame:
        """The flat cast shadow (white = shadow) on the ground, same frame and anchor as the sprite: each voxel's
        footprint stretched along +y by its top's height (light [0, -1, 1]), the scene's long flat shadow."""
        H, W = self.h, self.w
        ax, ay = self.anchor
        py, px = np.mgrid[0:H, 0:W]
        u, v = px + 0.5 - ax, py + 0.5 - ay
        gx, gy = v + u / 2, v - u / 2  # the ground point (z = 0) under each pixel
        m = np.zeros((H, W), bool)
        for lo, hi, _ in self.boxes(facing, {}):
            m |= (gx >= lo[0]) & (gx < hi[0]) & (gy >= lo[1] + lo[2]) & (gy < hi[1] + hi[2])
        img = np.zeros((H, W, 4), np.uint8)
        img[m] = 255
        return img


# ── review ─────────────────────────────────────────────────────────────────────────────────────────────
def _outline(f: Frame, ink: str) -> Frame:
    a = f[..., 3] > 0
    p = np.pad(a, 1)
    ring = (p[:-2, 1:-1] | p[2:, 1:-1] | p[1:-1, :-2] | p[1:-1, 2:]) & ~a
    out = f.copy()
    out[ring, :3] = hex_to_rgb(ink)
    out[ring, 3] = 255
    return out


def _lum(rgb: np.ndarray) -> np.ndarray:
    c = rgb.astype(np.float32) / 255.0
    return 0.2126 * c[..., 0] + 0.7152 * c[..., 1] + 0.0722 * c[..., 2]


def _tile(bg: Tuple[int, int, int]) -> Frame:
    """A 32 x 16 iso tile diamond (the board's unit) to stand pieces on in the lineup."""
    t = np.zeros((16, 32, 4), np.uint8)
    for y in range(16):
        hw = 2 * (y + 1) if y < 8 else 2 * (16 - y)
        t[y, 16 - hw:16 + hw, :3] = bg
        t[y, 16 - hw:16 + hw, 3] = 255
    return t


def lineup(pieces: List[BlockPiece], bg: str, scale: int = 4, ink: Optional[str] = None) -> Frame:
    """Every piece on an iso tile, idle E then S, at game scale, then the same strip in value only."""
    bgc = hex_to_rgb(bg)
    tc = tuple(min(255, int(c * 1.12) + 8) for c in bgc)
    slot = 40
    hmax = max(p.h for p in pieces) + 4
    strip = np.zeros((hmax, slot * 2 * len(pieces), 4), np.uint8)
    strip[..., :3] = bgc
    strip[..., 3] = 255
    tile = _tile(tc)
    feet = hmax - 10
    for i, p in enumerate(pieces):
        for j, fc in enumerate(("E", "S")):
            cx = (2 * i + j) * slot + slot // 2
            _paste(strip, tile, cx - 16, feet - 8)
            sh = p.shadow(fc)
            ys, xs = np.nonzero(sh[..., 3] > 0)
            yy, xx = ys + feet - p.anchor[1], xs + cx - p.anchor[0]
            ok = (yy >= 0) & (yy < hmax) & (xx >= 0) & (xx < strip.shape[1])
            strip[yy[ok], xx[ok], :3] = (strip[yy[ok], xx[ok], :3] * 0.65).astype(np.uint8)
            f = p.frame(fc)
            if ink:
                f = _outline(f, ink)
            _paste(strip, f, cx - p.anchor[0], feet - p.anchor[1])
    L = (_lum(strip[..., :3]) * 255).astype(np.uint8)
    val = np.dstack([L, L, L, np.full_like(L, 255)])
    both = np.concatenate([strip, val], axis=0)
    return np.repeat(np.repeat(both, scale, 0), scale, 1)


def _paste(dst: Frame, src: Frame, x0: int, y0: int) -> None:
    ys, xs = np.nonzero(src[..., 3] > 0)
    yy, xx = ys + y0, xs + x0
    ok = (yy >= 0) & (yy < dst.shape[0]) & (xx >= 0) & (xx < dst.shape[1])
    dst[yy[ok], xx[ok], :3] = src[ys[ok], xs[ok], :3]
    dst[yy[ok], xx[ok], 3] = 255


def on_scene(pieces: List[BlockPiece], scene: Frame, at: Tuple[int, int], step: Tuple[int, int] = (32, 0),
             ink: Optional[str] = None, shadow_alpha: float = 0.35) -> Frame:
    """Judge pieces where they live: idle keys with shadows standing on a real scene at 1x (a tile centre each)."""
    out = scene.copy()
    if out.shape[2] == 3:
        out = np.dstack([out, np.full(out.shape[:2], 255, np.uint8)])
    for i, p in enumerate(pieces):
        fx, fy = at[0] + i * step[0], at[1] + i * step[1]
        sh = p.shadow("S" if i % 2 else "E")
        ys, xs = np.nonzero(sh[..., 3] > 0)
        yy, xx = ys + fy - p.anchor[1], xs + fx - p.anchor[0]
        ok = (yy >= 0) & (yy < out.shape[0]) & (xx >= 0) & (xx < out.shape[1])
        out[yy[ok], xx[ok], :3] = (out[yy[ok], xx[ok], :3] * (1 - shadow_alpha)).astype(np.uint8)
        f = p.frame("S" if i % 2 else "E")
        if ink:
            f = _outline(f, ink)
        _paste(out, f, fx - p.anchor[0], fy - p.anchor[1])
    return out


def build(spec: dict, out_dir: Path, bg: Optional[str] = None) -> dict:
    """Every clip as a sheet (rows E, S, W, N), the shadows, blocks.json and an idle gif."""
    p = BlockPiece(spec)
    out_dir.mkdir(parents=True, exist_ok=True)
    meta = {"name": p.name, "fw": p.w, "fh": p.h, "anchor": p.anchor, "rows": list(FACINGS), "clips": {}}
    for c in p.clips:
        save_png(p.sheet(c), out_dir / f"{c}.png")
        fr, ms, loop = p.clip(c)
        meta["clips"][c] = {"frames": len(fr), "ms": ms, "loop": loop, "events": p.events(c)}
    save_png(pack_sheet([[p.shadow(f)] for f in FACINGS]), out_dir / "shadow.png")
    (out_dir / "blocks.json").write_text(json.dumps(meta, indent=1))
    if bg:
        fr, ms, _ = p.clip("idle", "S")
        save_gif(fr, ms, out_dir / "idle.gif", 6, hex_to_rgb(bg))
    return meta


def main(argv=None) -> int:
    import argparse
    from .paths import OUT
    ap = argparse.ArgumentParser(prog="pixling blocks", description="iso block tokens for board pieces (pp.blocks)")
    ap.add_argument("specs", nargs="+")
    ap.add_argument("--out", help="output root (default OUT/blocks); each piece writes <out>/<name>/")
    ap.add_argument("--bg", default="#3a5a40", help="ground colour for the lineup and gif")
    ap.add_argument("--lineup", help="also write a roster lineup PNG (pieces on iso tiles + value strip)")
    ap.add_argument("--scale", type=int, default=4)
    ap.add_argument("--ink", help="the 1 px outline your game draws at runtime (hex), for the lineup and --on")
    ap.add_argument("--on", help="judge in place: a scene / screenshot PNG at 1x")
    ap.add_argument("--at", default="", help="X,Y of the first piece's tile centre on --on")
    ap.add_argument("--step", default="32,0", help="DX,DY between pieces on --on (an iso row: 16,8)")
    ap.add_argument("--on-out", help="where the --on card goes (default OUT/blocks/on_x<scale>.png)")
    a = ap.parse_args(argv)
    root = Path(a.out) if a.out else OUT / "blocks"
    pieces = []
    for sp in a.specs:
        spec = load(sp)
        meta = build(spec, root / spec["name"], a.bg)
        pieces.append(BlockPiece(spec))
        print(f"{root / spec['name']}  {meta['fw']}x{meta['fh']}  clips {', '.join(meta['clips'])}")
    if a.lineup:
        save_png(lineup(pieces, a.bg, a.scale, a.ink), a.lineup)
        print(a.lineup)
    if a.on:
        from PIL import Image
        scene = np.array(Image.open(a.on).convert("RGBA"))
        at = tuple(int(v) for v in a.at.split(",")) if a.at else (scene.shape[1] // 3, scene.shape[0] // 2)
        card = on_scene(pieces, scene, at, tuple(int(v) for v in a.step.split(",")), ink=a.ink)
        dest = Path(a.on_out) if a.on_out else root / f"on_x{a.scale}.png"
        save_png(card, dest, a.scale)
        print(dest)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

"""What is under the pixels: one frame's G-buffer as an image + a short text table an LLM can read.

  python3 -m pp inspect specs/<style>/<name>.json --clip attack --dir E --frame 7

Reads the buffers of the real bake (Forge.frame keeps them), never a second render path, so what it
reports is what ships. Image: sprite | bone map | material map, each at --scale, with a numbered legend.
Text: one row per bone (nearest first), touching parts whose values are too close, hidden parts,
attach points, and a glyph grid (one letter per bone).
"""
from __future__ import annotations

import string
from collections import Counter
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import numpy as np
from PIL import Image, ImageDraw

from .color import hex_to_rgb, rgb_to_hex, rgb_to_oklab

GLYPHS = string.ascii_lowercase + string.ascii_uppercase + string.digits
LOW_DL = 0.08          # ARTIST.md: touching parts want value separation >= 0.08 (Oklab L)
_ID = ["#e6194b", "#3cb44b", "#ffe119", "#4363d8", "#f58231", "#911eb4", "#46f0f0", "#f032e6", "#bcf60c",
       "#fabebe", "#008080", "#e6beff", "#9a6324", "#fffac8", "#800000", "#aaffc3", "#808000", "#ffd8b1",
       "#000075", "#a9a9a9"]


def _hues(n: int) -> List[Tuple[int, int, int]]:
    """n well-separated flat colours for id maps."""
    return [hex_to_rgb(_ID[i % len(_ID)]) for i in range(n)]


def _find_frame(forge, clip: str, index: int):
    clips = {c.name: c for c in forge.clips()}
    if clip not in clips:
        raise SystemExit("clip %r not in %s" % (clip, sorted(clips)))
    frames = clips[clip].frames
    if not 0 <= index < len(frames):
        raise SystemExit("frame %d out of range (clip %s has %d)" % (index, clip, len(frames)))
    return frames[index], len(frames)


def gather(forge, clip: str = "idle", facing: str = "S", index: int = 0) -> Dict:
    """Render one frame through the real pipeline and collect everything the report shows."""
    fr, n = _find_frame(forge, clip, index)
    rgba = forge.frame(fr, facing)
    buf = forge._buf
    model = forge.model
    names = model.order
    on = buf.mat >= 0
    L = rgb_to_oklab(rgba[..., :3])[..., 0]
    rows = []
    for bi, name in enumerate(names):
        if not model.bones[name].parts:
            continue
        m = on & (buf.bone == bi)
        if not m.any():
            rows.append({"bone": name, "px": 0})
            continue
        ys, xs = np.nonzero(m)
        cols = Counter(rgb_to_hex(c) for c in rgba[m][:, :3].tolist())
        rows.append({"bone": name, "px": int(m.sum()), "bbox": [int(xs.min()), int(ys.min()), int(xs.max()), int(ys.max())],
                     "depth": float(np.median(buf.depth[m])), "L": float(np.median(L[m])),
                     "mats": sorted({forge.mats[i] for i in np.unique(buf.mat[m]).tolist()}),
                     "colours": cols.most_common()})
    vis = [r for r in rows if r["px"]]
    for i, r in enumerate(sorted(vis, key=lambda r: -r["px"])):
        r["glyph"] = GLYPHS[i % len(GLYPHS)]
    # touching parts: value masses (each part's median Oklab L) compared where parts share an edge
    pairs = []
    for a, b, oa, ob in ((buf.bone[:, :-1], buf.bone[:, 1:], on[:, :-1], on[:, 1:]),
                         (buf.bone[:-1], buf.bone[1:], on[:-1], on[1:])):
        m = oa & ob & (a != b)
        pairs.append(np.sort(np.stack([a[m], b[m]], 1), 1))
    Lof = {names.index(r["bone"]): r["L"] for r in vis}
    touching = [{"a": names[i], "b": names[j], "edge": int(n), "dL": abs(Lof[i] - Lof[j])}
                for (i, j), n in zip(*np.unique(np.concatenate(pairs), axis=0, return_counts=True))
                if n >= 3 and i in Lof and j in Lof]
    touching.sort(key=lambda t: t["dL"])
    attach = forge.attach_points(forge.attach_spec(forge.spec.get("attach") or True))
    extra = (rgba[..., 3] > 0) & ~on          # ground shadow, stamps outside the body, in-sprite fx
    return {"clip": clip, "dir": facing, "frame": index, "frames": n, "event": fr.event, "rgba": rgba,
            "buf": buf, "rows": rows, "touching": touching, "attach": attach, "extra": extra,
            "colours": len({tuple(c) for c in rgba[rgba[..., 3] > 0][:, :3].tolist()}),
            "size": forge.size, "anchor": forge.anchor, "names": names, "mats": forge.mats}


def text(info: Dict, grid: bool = True) -> str:
    W, H = info["size"]
    box = info["attach"].get("box") or [0, 0, 0, 0]
    ev = (" (%s)" % info["event"]) if info["event"] else ""
    out = ["%s %s f%d/%d%s  %dx%d  anchor %d,%d  body x%d..%d y%d..%d  %d colours" % (
        info["clip"], info["dir"], info["frame"], info["frames"], ev, W, H, info["anchor"][0], info["anchor"][1],
        box[0], box[2], box[1], box[3], info["colours"])]
    vis = sorted([r for r in info["rows"] if r["px"]], key=lambda r: r["depth"])
    glyph = {r["bone"]: r["glyph"] for r in vis}
    out.append("g bone          px  bbox(x0,y0,x1,y1)  L     materials / colours (count)   [nearest first]")
    for r in vis:
        cols = " ".join("%s:%d" % c for c in r["colours"][:4]) + (" +%d" % (len(r["colours"]) - 4)
                                                                 if len(r["colours"]) > 4 else "")
        out.append("%s %-12s %4d  %-18s %.2f  %s  %s" % (glyph[r["bone"]], r["bone"], r["px"],
                                                       "%d,%d,%d,%d" % tuple(r["bbox"]), r["L"],
                                                       ",".join(r["mats"]), cols))
    hidden = [r["bone"] for r in info["rows"] if not r["px"]]
    if hidden:
        out.append("hidden in this view: " + ", ".join(hidden))
    low = [t for t in info["touching"] if t["dL"] < LOW_DL]
    if low:
        out.append("touching with low value contrast (dL < %.2f): " % LOW_DL +
                   "; ".join("%s|%s %.2f (%d px edge)" % (t["a"], t["b"], t["dL"], t["edge"]) for t in low[:6]))
    pts = {k: v for k, v in info["attach"].items() if k != "box"}
    out.append("points: " + "  ".join("%s %d,%d%s" % (k, v[0], v[1], "" if v[2] else " (hidden)")
                                      for k, v in pts.items()))
    if grid and box:
        buf = info["buf"]
        idx = {i: glyph.get(n) for i, n in enumerate(info["names"])}
        ex = info["extra"]
        ys, xs = np.nonzero((buf.mat >= 0) | ex)
        x0, x1, y0, y1 = xs.min(), xs.max(), ys.min(), ys.max()
        out.append("grid x%d..%d y%d..%d (letters = bones above, ~ = shadow/fx, . = empty):" % (x0, x1, y0, y1))
        for y in range(y0, y1 + 1):
            line = []
            for x in range(x0, x1 + 1):
                if buf.mat[y, x] >= 0:
                    line.append(idx.get(int(buf.bone[y, x])) or "?")
                elif ex[y, x]:
                    line.append("~")
                else:
                    line.append(".")
            out.append("".join(line))
    return "\n".join(out)


def image(info: Dict, scale: int = 8, bg: str = "#2a2f3a") -> Image.Image:
    """sprite | bone map | material map, cropped to the content, with a legend. Bone letters match the
    text table; attach points are crosses on the sprite (yellow visible, grey hidden)."""
    rgba, buf = info["rgba"], info["buf"]
    names, mats = info["names"], info["mats"]
    on = buf.mat >= 0
    a = rgba[..., 3] > 0
    ys, xs = np.nonzero(a | on)
    pts = [v for k, v in info["attach"].items() if k != "box" and v]
    px = list(xs) + [p[0] for p in pts]
    py = list(ys) + [p[1] for p in pts]
    H0, W0 = rgba.shape[:2]
    x0, x1 = max(0, min(px) - 2), min(W0 - 1, max(px) + 2)
    y0, y1 = max(0, min(py) - 2), min(H0 - 1, max(py) + 2)
    crop = (slice(y0, y1 + 1), slice(x0, x1 + 1))
    H, W = y1 - y0 + 1, x1 - x0 + 1
    bgc = np.array(hex_to_rgb(bg), np.uint8)
    bone_c = _hues(len(names))
    used_m = sorted(set(np.unique(buf.mat[on]).tolist()))
    mat_c = {m: c for m, c in zip(used_m, _hues(len(used_m) + 9)[9:])}
    lum = rgba[..., :3].astype(np.float32).mean(-1) / 255.0

    def panel(colour_of, ids) -> np.ndarray:
        p = np.empty(rgba.shape[:2] + (3,), np.uint8)
        p[:] = bgc
        for i in np.unique(ids[on]).tolist():
            p[on & (ids == i)] = colour_of[i]
        # shade levels stay readable: modulate by the sprite's own value
        p[on] = np.clip(p[on].astype(np.float32) * (0.55 + 0.6 * lum[on, None]), 0, 255).astype(np.uint8)
        return p[crop]

    spr = np.empty(rgba.shape[:2] + (3,), np.uint8)
    spr[:] = bgc
    spr[a] = rgba[a][:, :3]
    panels = [spr[crop], panel(bone_c, buf.bone), panel(mat_c, buf.mat)]
    gap = max(2, W // 6)
    big = [np.kron(p, np.ones((scale, scale, 1), np.uint8)) for p in panels]
    vis = sorted([r for r in info["rows"] if r["px"]], key=lambda r: r["depth"])
    legend_w = 130
    Ht = max(H * scale, 16 + 12 * (len(vis) + len(used_m) + 3))
    Wt = len(big) * W * scale + (len(big) - 1) * gap * scale + legend_w
    img = Image.new("RGB", (Wt, Ht), tuple(int(v) for v in bgc))
    for k, b in enumerate(big):
        img.paste(Image.fromarray(b), (k * (W + gap) * scale, 0))
    dr = ImageDraw.Draw(img)
    ink = (20, 20, 24) if float(bgc.astype(int).mean()) > 120 else (230, 230, 230)
    xb = (W + gap) * scale
    for r in vis:
        bi = names.index(r["bone"])
        yy, xx = np.nonzero(on & (buf.bone == bi))
        # label on the bone's own pixel nearest its centroid (centroids of bent parts fall outside)
        k = int(np.argmin((xx - xx.mean()) ** 2 + (yy - yy.mean()) ** 2))
        cx, cy = xb + (xx[k] - x0) * scale + scale // 2, (yy[k] - y0) * scale + scale // 2
        dr.text((cx - 2, cy - 6), r["glyph"], fill=(0, 0, 0))
        dr.text((cx - 3, cy - 7), r["glyph"], fill=(255, 255, 255))
    for k, v in info["attach"].items():
        if k == "box" or not v:
            continue
        x, y = (v[0] - x0) * scale + scale // 2, (v[1] - y0) * scale + scale // 2
        col = (255, 235, 90) if v[2] else (150, 150, 150)
        dr.line((x - 5, y, x + 5, y), fill=col)
        dr.line((x, y - 5, x, y + 5), fill=col)
    lx = len(big) * (W + gap) * scale - gap * scale + 8
    y = 4
    dr.text((lx, y), "%s %s f%d" % (info["clip"], info["dir"], info["frame"]), fill=ink)
    y += 16
    for r in vis:
        dr.rectangle((lx, y + 2, lx + 8, y + 10), fill=bone_c[names.index(r["bone"])])
        dr.text((lx + 12, y), "%s %s" % (r["glyph"], r["bone"]), fill=ink)
        y += 12
    y += 6
    for mi in used_m:
        dr.rectangle((lx, y + 2, lx + 8, y + 10), fill=mat_c[mi])
        dr.text((lx + 12, y), mats[mi], fill=ink)
        y += 12
    return img


def inspect(spec_path: str, clip: str = "idle", facing: str = "S", index: int = 0, scale: int = 8,
            out: Optional[str] = None, grid: bool = True) -> Tuple[Path, str]:
    from .forge import Forge, OUT, load_spec
    spec = load_spec(spec_path)
    f = Forge(spec)
    if facing not in f.spec.get("directions", [facing]):
        facing = f.spec["directions"][0]
    info = gather(f, clip, facing, index)
    img = image(info, scale, f.style.spec.get("bg", "#2a2f3a"))
    path = Path(out) if out else OUT / spec["name"] / ("inspect_%s_%s_%d.png" % (clip, facing, index))
    path.parent.mkdir(parents=True, exist_ok=True)
    img.save(path)
    return path, text(info, grid)

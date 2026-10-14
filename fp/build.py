"""Pack a layout and the kit it places into a playable folder: index.html (opens the painted view in layers/ when the
layout has one: fp/art/<layout>/, made by `fp paint`; else the first-person walk), walk.html (the first-person walk),
fp.js, world.json, world.bin, vendor/.

world.bin holds every mesh once (instanced by placement) plus the walk heightfield; world.json says where each array
lives, the style, the placements, colliders, lights, steps and the walk route. Nothing is resampled at runtime: the
browser draws exactly these triangles and lines.
"""
from __future__ import annotations

import importlib
import json
import math
import shutil
import time
from pathlib import Path

import numpy as np

from . import kit as kitmod
from .mesh import Lines, Mesh

HERE = Path(__file__).resolve().parent
WEB = HERE / "web"


def load_style(name_or_path: str) -> dict:
    p = Path(name_or_path)
    if not (p.suffix == ".json" and p.exists()):
        p = HERE / "styles" / ("%s.json" % name_or_path)
    if not p.exists():
        raise SystemExit("fp: no style %r (have: %s)" % (name_or_path, ", ".join(
            sorted(f.stem for f in (HERE / "styles").glob("*.json")))))
    return json.loads(p.read_text())


def load_layout(name: str):
    try:
        return importlib.import_module("fp.layouts.%s" % name)
    except ModuleNotFoundError:
        raise SystemExit("fp: no layout %r (have: %s)" % (name, ", ".join(
            sorted(f.stem for f in (HERE / "layouts").glob("*.py") if not f.stem.startswith("_")))))


class Packer:
    def __init__(self):
        self.parts = []
        self.size = 0

    def add(self, arr: np.ndarray) -> list:
        b = np.ascontiguousarray(arr).tobytes()
        off = self.size
        self.parts.append(b)
        self.size += len(b)
        pad = (-self.size) % 4
        if pad:
            self.parts.append(b"\0" * pad)
            self.size += pad
        return [off, int(arr.size)]

    def bytes(self) -> bytes:
        return b"".join(self.parts)


def pack_mesh(pk: Packer, m: Mesh, mats: dict) -> dict:
    unknown = sorted({str(x) for x in m.M} - set(mats))
    if unknown:
        raise SystemExit("fp: materials %s are not ramps in the style" % unknown)
    n = len(m.P)
    attr = np.zeros((n, 4), np.uint8)
    attr[:, 0] = [mats[str(x)] for x in m.M]
    attr[:, 1] = np.clip(np.round(m.S * 255), 0, 255)
    attr[:, 2] = np.clip(np.round(m.A * 255), 0, 255)
    nrm = np.clip(np.round(m.N * 127), -127, 127).astype(np.int8)
    nrm4 = np.zeros((n, 4), np.int8)
    nrm4[:, :3] = nrm
    lo, hi = m.bounds()
    return {"verts": n, "tris": int(len(m.I)),
            "pos": pk.add(m.P.astype(np.float32)), "nrm": pk.add(nrm4), "attr": pk.add(attr),
            "idx": pk.add(m.I.astype(np.uint32)),
            "bounds": [[round(float(v), 3) for v in lo], [round(float(v), 3) for v in hi]]}


def pack_lines(pk: Packer, L: Lines, mats: dict) -> dict:
    seg, mid = [], []
    for mat, p in L.polys:
        if mat not in mats:
            raise SystemExit("fp: line material %r is not a ramp in the style" % mat)
        for a, b in zip(p[:-1], p[1:]):
            seg += [a, b]
            mid += [mats[mat], mats[mat]]
    if not seg:
        return {"verts": 0}
    return {"verts": len(seg), "pos": pk.add(np.array(seg, np.float32)),
            "mat": pk.add(np.array(mid, np.uint8))}


def _xf(x, y, z, yaw, s):
    R = math.radians(yaw)
    c, si = math.cos(R), math.sin(R)
    return lambda p: np.stack([x + s * (p[..., 0] * c + p[..., 2] * si), y + s * p[..., 1],
                               z + s * (-p[..., 0] * si + p[..., 2] * c)], -1)


def build(layout: str = "first_snow", style: str = "hushfall", out: Path = None, quiet=False) -> Path:
    t0 = time.time()
    st = load_style(style)
    L = load_layout(layout).layout(st)
    out = Path(out) if out else _default_out(layout)
    out.mkdir(parents=True, exist_ok=True)
    mats = {name: i for i, name in enumerate(st["ramps"])}
    pk = Packer()

    meshes = {"terrain": pack_mesh(pk, L["terrain"], mats), "slabs": pack_mesh(pk, L["slabs"], mats)}
    world_lines = L["lines"]
    instances, colliders, boxes, lights, emitters = [], [], [], [], []
    for key, places in sorted(L["instances"].items()):
        name, seed = key.split(":")
        a = kitmod.build(name, int(seed))
        if a.mesh.tris:
            meshes[key] = pack_mesh(pk, a.mesh, mats)
            instances.append({"mesh": key, "shadow": a.shadow, "at": places})
        for x, y, z, yaw, s in places:
            f = _xf(x, y, z, yaw, s)
            if a.lines:
                world_lines = world_lines + Lines([(m, f(p).astype(np.float32)) for m, p in a.lines.polys])
            if a.collide:
                colliders.append([x, z, round(a.collide * s, 3)])
            if a.box:
                boxes.append([x, z, yaw, a.box[0] * s, a.box[1] * s])
            for lt in a.lights:
                p = f(np.array(lt["pos"], np.float32))
                d = f(np.array(lt["dir"], np.float32)) - f(np.zeros(3, np.float32))
                d = d / np.linalg.norm(d)
                lights.append({"pos": [round(float(v), 3) for v in p], "dir": [round(float(v), 4) for v in d],
                               "angle": lt["angle"], "range": round(lt["range"] * s, 3), "power": lt.get("power", 1.0),
                               "ramp": lt.get("ramp", "glow")})
            for k, v in a.anchors.items():          # anchors named exhaust* puff smoke (fp.js updateExhaust)
                if k.startswith("exhaust"):
                    p = f(np.array(v[:3], np.float32))
                    d = f(np.array([0.0, 0.0, 1.0], np.float32)) - f(np.zeros(3, np.float32))
                    emitters.append({"pos": [round(float(c), 3) for c in p],
                                     "dir": [round(float(c), 4) for c in d / np.linalg.norm(d)]})
    lines = pack_lines(pk, world_lines, mats)
    H = L["heights"]
    if H["y"].shape != (len(H["zs"]), len(H["xs"])):
        raise SystemExit("fp: heights.y must be shaped (len(zs), len(xs)), got %s" % (H["y"].shape,))
    heights = {"nx": len(H["xs"]), "nz": len(H["zs"]), "xs": pk.add(H["xs"].astype(np.float32)),
               "zs": pk.add(H["zs"].astype(np.float32)), "y": pk.add(H["y"].astype(np.float32))}

    world = {
        "layout": L["name"], "style": st, "materials": list(st["ramps"]), "meshes": meshes, "instances": instances,
        "lines": lines, "heights": heights, "steps": L["steps"], "colliders": colliders, "boxes": boxes,
        "lights": lights, "emitters": emitters, "route": L["route"], "look_end": L["look_end"], "start": L["start"],
        "bounds": L["bounds"], "stats": L["stats"], "built": time.strftime("%Y-%m-%d %H:%M"),
    }
    from . import sky as skymod
    world["sky_image"] = {"src": "sky.png", **skymod.save(st, out / "sky.png")}
    (out / "world.bin").write_bytes(pk.bytes())
    (out / "world.json").write_text(json.dumps(world, separators=(",", ":")))
    for f in ("fp.js", "audio.js", "texel.js"):
        if (WEB / f).exists():
            shutil.copy(WEB / f, out / f)
    # the painted view (layers/) is what opens where the layout has one; the first-person walk stays one click away
    # at walk.html (and opens by itself where there is no painted view)
    shutil.copy(WEB / "index.html", out / "walk.html")
    art = painted_art(layout)
    if art:
        title = json.loads((art / "scene.json").read_text()).get("title", layout)
        (out / "index.html").write_text(REDIRECT.replace("{title}", title))
    else:
        shutil.copy(WEB / "index.html", out / "index.html")
    for sub in ("vendor", "fonts"):
        d = out / sub
        d.mkdir(exist_ok=True)
        for f in (WEB / sub).iterdir():
            if f.is_file():
                shutil.copy(f, d / f.name)
    if art:
        paint_layers(out / "layers", art)
    elif (out / "layers").exists():
        shutil.rmtree(out / "layers")          # a painted view left from an earlier build: not this layout's
    if not quiet:
        tris = sum(m["tris"] * max(1, sum(len(i["at"]) for i in instances if i["mesh"] == k))
                   for k, m in meshes.items())
        print("fp build: %s -> %s  (%.1f MB bin, %d meshes, %d placed tris, %d line segs, %d lights, %.1fs)" % (
            layout, out, pk.size / 1e6, len(meshes), tris, lines.get("verts", 0) // 2, len(lights), time.time() - t0))
    return out


REDIRECT = """<!doctype html>
<html lang="en"><head><meta charset="utf-8"><title>{title}</title>
<meta name="viewport" content="width=device-width, initial-scale=1">
<script>location.replace('layers/' + location.search + location.hash);</script>
<meta http-equiv="refresh" content="0; url=layers/">
<style>body{margin:0;background:#1c2440;color:#90afa3;font:14px ui-monospace,monospace;display:grid;place-items:center;height:100vh}a{color:#c4908c}</style>
</head><body><p>{title}, painted: <a href="layers/">open</a> &middot; <a href="walk.html">first-person walk</a></p></body></html>
"""


def painted_art(layout: str):
    """the layout's painted view (fp/art/<layout>/, made by `fp paint`), or None when it has none"""
    d = HERE / "art" / layout
    return d if (d / "scene.json").exists() else None


def paint_layers(out: Path, art: Path) -> Path:
    """the painted third-person view in out/: the committed layers (art: fp/art/<layout>, made by `fp paint`, so no
    Blender is needed here), the page, its runtime, the audio and the font. A static folder with relative paths."""
    if out.exists():
        shutil.rmtree(out)
    out.mkdir(parents=True)
    for f in Path(art).iterdir():
        if f.is_file():
            shutil.copy(f, out / f.name)
    shutil.copy(WEB / "layers.html", out / "index.html")
    for f in ("layers.js", "audio.js"):
        shutil.copy(WEB / f, out / f)
    (out / "fonts").mkdir(exist_ok=True)
    for f in (WEB / "fonts").iterdir():
        if f.is_file():
            shutil.copy(f, out / "fonts" / f.name)
    return out


def _default_out(layout: str) -> Path:
    try:
        from pp.paths import OUT
    except ImportError:
        OUT = Path.cwd() / "out"
    return OUT / "fp" / layout

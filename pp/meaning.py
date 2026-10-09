"""The meaning layer: what every pixel of a map IS, written by the painters while they paint (never read back
from colours afterwards), so a game can walk the painting.

  python3 -m pp.map specs/vista/highgate.map.json --still --meaning      # -> out/<map>/meaning/
  (--layers writes it too, next to the engine layers)

Files (format version 1, described again in meaning.json):
  meaning.png   R = material index into meaning.json "materials"; G = collision (0 blocked, 1 walk, 2 slow: wading,
                fields marked slow); B = water depth in px (distance to the nearest non-water pixel, 0 on land)
  depth.png     R,G = 16-bit feet-y of whatever stands on this pixel (objects, and terrain regions marked
                "stands"); 0 = flat ground. Draw a mover behind a pixel when its feet are above (smaller y than) it.
  objects.png   R,G = 16-bit object id (index in meaning.json "objects" + 1); 0 = none
  meaning.json  {version, size, materials [{name, walk}], collision, water {shallow_px}, objects [{id, build, at,
                place, box, block}]}

Terrain regions: each kind has a default material and walkability (MATERIALS); a region can say
  "material": "field", "walk": 2           (0 blocked, 1 walk, 2 slow; true/false work too)
  "stands": 412                            the region stands up from the ground at that feet line (a painted
                                           tree crown): its pixels get depth 412 and keep the ground's material and
                                           walkability underneath; add "block": [x, y, w, h] for the trunk
Water is walkable where it is shallow: depth <= spec "meaning": {"shallow_px": 3} px -> 2 (wading), deeper -> 0.
Objects: the pixels of the sprite's body (not its baked ground shadow) get the object's id and its feet-y; what
blocks is ob "block": "base" (default: the bottom third of the body, at least 3 rows), "none" (default for
"over" objects such as bridges), "all", or [dx, dy, w, h] relative to the feet ([-3, -2, 6, 3] is a trunk).
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Dict, List

import numpy as np
from scipy.ndimage import distance_transform_edt

VERSION = 1
# kind -> (material, walk). Painters that change no material (shore, a fx-like pass) are absent.
MATERIALS = {
    "land": ("grass", 1), "grass": ("grass", 1), "fill": ("fill", 1),
    "path": ("path", 1), "dirt": ("path", 1), "sand": ("sand", 1),
    "paving": ("paving", 1), "cobble": ("paving", 1), "bridge": ("bridge", 1), "planks": ("planks", 1),
    "water": ("water", 0), "sea": ("water", 0),
    "canopy": ("foliage", 0), "massif": ("rock", 0), "wall_face": ("wall", 0),
}


def _walk(v) -> int:
    if v is True:
        return 1
    if v is False:
        return 0
    return int(v)


class Meaning:
    def __init__(self, W: int, H: int, spec: Dict):
        self.W, self.H = W, H
        self.mat = np.zeros((H, W), np.uint8)              # 0 = "void"
        self.walk = np.zeros((H, W), np.uint8)
        self.depth = np.zeros((H, W), np.uint16)
        self.obj = np.zeros((H, W), np.uint16)
        self.block = np.zeros((H, W), bool)                # what stands on the ground and blocks (objects, trunks)
        self.materials: List[Dict] = [{"name": "void", "walk": 0}]
        self.objects: List[Dict] = []
        self.shallow = float((spec.get("meaning") or {}).get("shallow_px", 3))

    def _mat_id(self, name: str, walk: int) -> int:
        for i, m in enumerate(self.materials):
            if m["name"] == name:
                return i
        if len(self.materials) >= 255:
            raise ValueError("more than 254 materials in one map")
        self.materials.append({"name": name, "walk": walk})
        return len(self.materials) - 1

    # ---- terrain: called by compose() after each region is painted
    def terrain(self, reg: Dict, m: np.ndarray, before: np.ndarray, after: np.ndarray, pal) -> None:
        kind = reg["kind"]
        if kind not in MATERIALS and "material" not in reg and "stands" not in reg:
            return
        if kind == "canopy":
            # the clumps, not the shadow the painter casts on the ground: changed pixels in the region's own ramps
            ramps = [r for r, _ in reg.get("mix", [[reg.get("ramp", "leaf"), 1.0]])]
            cols = np.array([c for r in ramps if r in pal.ramps for c in pal.ramps[r]], np.int32)
            changed = np.any(before != after, axis=-1)
            key = lambda a: (a[..., 0].astype(np.int32) << 16) | (a[..., 1].astype(np.int32) << 8) | a[..., 2]
            clumps = changed & np.isin(key(after), (cols[:, 0] << 16) | (cols[:, 1] << 8) | cols[:, 2])
            # a mass blocks as a whole (gaps between clumps are not clearings); a standing crown is just its clumps
            painted = clumps if "stands" in reg else (clumps | m)
        else:
            painted = m & (after[..., 3] > 0)
        if "stands" in reg:                                 # stands up from the ground: occludes, keeps the ground
            self.depth[painted] = np.maximum(self.depth[painted], int(reg["stands"]))
            if "block" in reg:
                x, y, w, h = [int(round(v)) for v in reg["block"]]
                self.block[max(0, y):max(0, y + h), max(0, x):max(0, x + w)] = True
            return
        name, walk = MATERIALS.get(kind, (kind, 1))
        name = reg.get("material", name)
        walk = _walk(reg.get("walk", walk))
        i = self._mat_id(name, walk)
        self.mat[painted] = i
        self.walk[painted] = walk

    # ---- objects: called once with every object's first frame
    def object(self, ob: Dict, img: np.ndarray, anchor, shadow_col) -> None:
        a = img[..., 3] > 0
        body = a & ~np.all(img[..., :3] == shadow_col, axis=-1)
        ax, ay = anchor
        if ob.get("flip"):
            body = body[:, ::-1]
            ax = body.shape[1] - 1 - ax
        X0, Y0 = int(ob["at"][0]) - ax, int(ob["at"][1]) - ay
        h, w = body.shape
        x0, y0, x1, y1 = max(0, X0), max(0, Y0), min(self.W, X0 + w), min(self.H, Y0 + h)
        oid = len(self.objects) + 1
        feet = int(ob["at"][1])
        rows = np.nonzero(body.any(1))[0]
        rec = {"id": oid, "build": ob["build"], "at": [int(v) for v in ob["at"][:2]]}
        if ob.get("place"):
            rec["place"] = ob["place"]
        if len(rows) and x1 > x0 and y1 > y0:
            cut = body[y0 - Y0:y1 - Y0, x0 - X0:x1 - X0]
            reg = (slice(y0, y1), slice(x0, x1))
            self.depth[reg] = np.where(cut, np.maximum(self.depth[reg], feet), self.depth[reg])
            self.obj[reg] = np.where(cut, oid, self.obj[reg])
            cols = np.nonzero(body.any(0))[0]
            rec["box"] = [int(X0 + cols.min()), int(Y0 + rows.min()), int(X0 + cols.max() + 1), int(Y0 + rows.max() + 1)]
            blk = ob.get("block", "none" if ob.get("over") else "base")
            rec["block"] = blk
            if blk == "all":
                self.block[reg] |= cut
            elif blk == "base":
                top = rows.max() - max(3, (rows.max() - rows.min() + 1) // 3) + 1
                band = np.zeros_like(body)
                band[top:] = body[top:]
                self.block[reg] |= band[y0 - Y0:y1 - Y0, x0 - X0:x1 - X0]
            elif isinstance(blk, (list, tuple)):
                dx, dy, bw, bh = [int(round(v)) for v in blk]
                X, Y = int(ob["at"][0]) + dx, feet + dy
                self.block[max(0, Y):max(0, Y + bh), max(0, X):max(0, X + bw)] = True
        self.objects.append(rec)

    # ---- finish + export
    def arrays(self):
        water_ids = [i for i, m in enumerate(self.materials) if m["name"] == "water"]
        water = np.isin(self.mat, water_ids) if water_ids else np.zeros_like(self.block)
        wd = distance_transform_edt(water) if water.any() else np.zeros(self.mat.shape)
        wd = np.clip(np.round(wd), 0, 255).astype(np.uint8)      # wading is decided on the depth that is exported
        walk = self.walk.copy()
        walk[water] = np.where(wd[water] <= self.shallow, 2, 0)
        walk[self.block] = 0
        return walk, wd

    def save(self, d: Path) -> Dict:
        from .io import save_png
        d.mkdir(parents=True, exist_ok=True)
        walk, wd = self.arrays()
        a = np.full((self.H, self.W), 255, np.uint8)
        save_png(np.dstack([self.mat, walk, wd, a]), d / "meaning.png")
        save_png(np.dstack([(self.depth >> 8).astype(np.uint8), (self.depth & 255).astype(np.uint8), np.zeros_like(a), a]), d / "depth.png")
        save_png(np.dstack([(self.obj >> 8).astype(np.uint8), (self.obj & 255).astype(np.uint8), np.zeros_like(a), a]), d / "objects.png")
        meta = {"version": VERSION, "size": [self.W, self.H], "materials": self.materials,
                "collision": {"0": "blocked", "1": "walk", "2": "slow"}, "water": {"shallow_px": self.shallow},
                "files": {"meaning": "meaning.png (R material, G collision, B water depth px)",
                          "depth": "depth.png (R,G = 16-bit feet-y)", "objects": "objects.png (R,G = 16-bit object id)"},
                "objects": self.objects}
        (d / "meaning.json").write_text(json.dumps(meta, indent=1))
        return meta

"""Street-scale vista helpers: spec writer, primitives, windows, townhouses."""
import json
import os
ROOT = os.path.normpath(os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', '..'))
D = os.path.join(ROOT, 'specs', 'vista', 'streets') + os.sep
MATS = {
 "roof_t": {"ramp": "roof", "shades": [0, 1, 2, 3], "thresholds": [0.35, 0.6, 0.86], "sky": 0.25, "detail": {"kind": "plate", "scale": 1.0, "amount": 0.5}},
 "plum_t": {"ramp": "roof_plum", "shades": [0, 1, 2, 3], "thresholds": [0.35, 0.6, 0.86], "sky": 0.25, "detail": {"kind": "plate", "scale": 1.0, "amount": 0.5}},
 "wall_s": {"ramp": "stone", "shades": [0, 1, 2, 3], "thresholds": [0.35, 0.62, 0.86], "detail": {"kind": "stone", "scale": 1.4, "amount": 0.5}},
}
def save(name, concept, bones, yaw=-24, frame=None, anchor=None, clips=None):
    s = {"name": name, "style": "vista", "rig": "prop", "directions": ["S"], "concept": concept,
         "frame": frame, "anchor": anchor, "view": {"yaw": {"S": yaw}}, "materials": MATS,
         "clips": ["idle"], "custom_clips": clips or {"idle": {"loop": True, "frames": [{"pose": {}}]}},
         "bones": [{"name": "root"}] + bones}
    json.dump(s, open(D + name + '.json', 'w'), indent=1)
def box(at, half, mat, **k): return dict(shape="box", at=at, half=half, mat=mat, **k)
def roof(at, half, h, mat, **k): return dict(shape="roof", at=at, half=half, h=h, mat=mat, **k)
def st(at, rows, key, normal=(0, -1, 0), **k): return dict(shape="stamp", at=at, normal=list(normal), rows=rows, key=key, min_facing=0.05, **k)
WIN = ["aa", "aa", "bb"]
WK = {"a": "window", "b": "plaster:3"}
def windows(w, d, h, floors, door_x=None, skip_ground=False):
    out = []
    fh = h / floors
    for f in range(floors):
        z = fh * f + fh * 0.55
        n = max(1, int((w - 4) // 6))
        span = (n - 1) * 6
        for i in range(n):
            x = -span / 2 + i * 6
            if f == 0 and (skip_ground or (door_x is not None and abs(x - door_x) < 4)):
                continue
            out.append(st([x, -d / 2 - 0.3, z], WIN, WK))
        ns = max(1, int((d - 4) // 6))
        sp = (ns - 1) * 6
        for i in range(ns):
            out.append(st([w / 2 + 0.3, -sp / 2 + i * 6, z], WIN, WK, normal=(1, 0, 0)))
    return out
def townhouse(name, w, d, h, floors=2, rmat="roof_t", gable=False, door_x=0, shop=None, chimney=None, rh=None, stone_base=True):
    rh = rh or min(w, d) * 0.55
    parts = [box([0, 0, h / 2], [w / 2, d / 2, h / 2], "plaster")] + windows(w, d, h, floors, door_x, skip_ground=bool(shop))
    parts.append(st([door_x, -d / 2 - 0.3, 2.5], [".aaa.", "abbba", "abbba", "abcba", "abbba"], {"a": "wood:0", "b": "wood:1", "c": "gold"}))
    bones = [{"name": "walls", "parent": "root", "parts": parts}]
    if stone_base:
        bones.append({"name": "base", "parent": "root", "parts": [box([0, 0, 1.1], [w / 2 + 0.4, d / 2 + 0.4, 1.1], "wall_s")]})
    bones.append({"name": "roof", "parent": "root", "seam": True, "parts": [roof([0, 0, h], [w / 2 + 1.2, d / 2 + 1.2], rh, rmat, gable=gable)]})
    if chimney:
        cx, cy = chimney
        bones.append({"name": "chimney", "parent": "root", "seam": True, "parts": [box([cx, cy, h + rh * 0.75], [1.6, 1.6, rh * 0.45 + 1.2], "plaster"), box([cx, cy, h + rh * 1.2 + 1.4], [2, 2, 0.5], "stone")]})
    if shop:
        # shop front: wide window + striped awning over the ground floor
        x0 = door_x
        bones.append({"name": "shop", "parent": "root", "parts": [st([x0 + (-8 if x0 > 0 else 8), -d / 2 - 0.3, 3], ["aaaaaa", "abbbba", "abbbba"], {"a": "wood:0", "b": "window"})]})
        bones.append({"name": "awning", "parent": "root", "seam": True, "parts": [
            box([0, -d / 2 - 3.0, h / floors - 1.6], [w / 2 - 1.5, 3.4, 0.8], shop, rot=[-32, 0, 0])]})
    fw, fh = int(w * 1.4 + 24), int(h + rh + d * 0.6 + 22)
    save(name, f"Street-level townhouse {w}x{d}x{h}, {floors} floors" + (f", {shop} shop awning" if shop else ""), bones,
         frame=[fw, fh], anchor=[fw // 2, fh - 8])

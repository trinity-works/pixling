"""Aerial-scale vista helpers: spec writer, primitives, window facades, houses."""
import json
import os
ROOT = os.path.normpath(os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', '..'))
D = os.path.join(ROOT, 'specs', 'vista') + os.sep
def save(name, concept, bones, yaw=-24, frame=None, anchor=None, clips=None, mats=None):
    ext = 0
    s = {"name": name, "style": "vista", "rig": "prop", "directions": ["S"], "concept": concept,
         "frame": frame or [64, 72], "anchor": anchor or [32, 62], "view": {"yaw": {"S": yaw}},
         "clips": ["idle"], "custom_clips": clips or {"idle": {"loop": True, "frames": [{"pose": {}}]}},
         "bones": [{"name": "root"}] + bones}
    if mats: s["materials"] = mats
    json.dump(s, open(D + name + '.json', 'w'), indent=1)
def box(at, half, mat, **k): return dict(shape="box", at=at, half=half, mat=mat, **k)
def roof(at, half, h, mat, **k): return dict(shape="roof", at=at, half=half, h=h, mat=mat, **k)
def st(at, rows, key, normal=(0, -1, 0), **k): return dict(shape="stamp", at=at, normal=list(normal), rows=rows, key=key, min_facing=0.05, **k)
def row(normal, z, count, rows=("a",), key=None, **k):
    """a row of stamps laid out on the face as drawn (pp Forge._stamp_row): even whole-pixel pitch, rows parallel to the
    wall's drawn bottom edge, z px above it"""
    return dict(shape="stamp_row", normal=list(normal), at=[0, 0, z], count=count, rows=list(rows), key=key or {"a": "window"},
                min_facing=0.05, **k)
def facade(w, d, h, floors):
    """window rows on the front (-y) and east (+x) faces, one row per floor per face"""
    out = []
    fh = h / floors
    nf = max(1, int((w - 2) // 3) + 1) if w > 5 else 1
    ns = max(1, int((d - 2) // 3) + 1)
    for f in range(floors):
        z = round(fh * (f + 0.45), 2)
        out.append(row((0, -1, 0), z, nf))
        out.append(row((1, 0, 0), z, ns))
    return out
def house(name, w, d, h, floors=1, rh=None, rmat="roof", gable=False, chimney=None, door=True, yaw=-24, extra=()):
    rh = rh or min(w, d) * 0.62
    # the door first: the ground-floor windows keep clear of it
    parts = [box([0, 0, h / 2], [w / 2, d / 2, h / 2], "plaster")]
    if door:
        parts.append(row((0, -1, 0), 1, 1, rows=("a", "a")))
    parts += facade(w, d, h, floors)
    bones = [{"name": "walls", "parent": "root", "parts": parts},
             {"name": "roof", "parent": "root", "seam": True,
              "parts": [roof([0, 0, h], [w / 2 + 0.7, d / 2 + 0.7], rh, rmat, gable=gable)]}]
    if chimney:
        bones.append({"name": "chimney", "parent": "root", "seam": True,
                      "parts": [box([chimney[0], chimney[1], h + rh * 0.7], [0.8, 0.8, rh * 0.35 + 0.6], "plaster")]})
    bones += list(extra)
    size = max(w, d) * 1.6 + 8
    H = h + rh + d * 0.5 + 10
    save(name, f"Aerial town house {w}x{d}x{h}, {floors} floor(s), {rmat} {'gable' if gable else 'hip'} roof.", bones, yaw,
         frame=[int(size) + 8, int(H) + 10], anchor=[int(size / 2) + 4, int(H) + 2])

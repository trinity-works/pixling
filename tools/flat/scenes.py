"""Flat Minimal scenes: an organic island on the cell grid with a river, a small clustered village, a bridge, a
jetty, a field, trees, a grazing deer and a heron, smoke and water glints. One hand, two biomes: forest, dunes.
scene() returns a pp.iso scene dict; the style file (styles/flat*.json) owns the colours and the night ramp.
"""
import json
import random
from pathlib import Path

import numpy as np

from tools.flat.kit import C, LAND, box, cabin, deer, fir, heron, palm, ruin, solid

ROOT = Path(__file__).resolve().parents[2]


def island_grid(nx, ny, seed, center, radii):
    """An organic island on the cell grid: a few overlapping blobs + coarse noise, then cleaned so no edge has
    one-cell spurs or notches (every coast step is at least one full cell)."""
    rng = np.random.RandomState(seed)
    j, i = np.mgrid[0:ny, 0:nx]
    cx, cy = center
    rx, ry = radii
    field = np.full((ny, nx), 9.0)
    blobs = [(cx, cy, rx, ry)] + [(cx + rng.uniform(-0.5, 0.5) * rx, cy + rng.uniform(-0.5, 0.5) * ry,
                                   rx * rng.uniform(0.45, 0.7), ry * rng.uniform(0.45, 0.7)) for _ in range(3)]
    for (bx, by, ax, ay) in blobs:
        field = np.minimum(field, ((i + 0.5 - bx) / ax) ** 2 + ((j + 0.5 - by) / ay) ** 2)
    noise = rng.rand(ny // 2 + 2, nx // 2 + 2)
    nz = noise[j // 2, i // 2]
    land = field + (nz - 0.5) * 0.7 < 1.0
    for _ in range(4):
        nb = (np.roll(land, 1, 0).astype(int) + np.roll(land, -1, 0) + np.roll(land, 1, 1) + np.roll(land, -1, 1))
        land = np.where(land & (nb <= 1), False, land)
        land = np.where(~land & (nb >= 3), True, land)
    return land


def rings(land, river):
    """Water ring index by chebyshev distance to land: 2 shallow, 1 mid, 0 deep (iso-aligned bands)."""
    ny, nx = land.shape
    dist = np.full(land.shape, 99)
    dist[land] = 0
    cur = land.copy()
    for k in range(1, 12):
        grow = cur.copy()
        for dj in (-1, 0, 1):
            for di in (-1, 0, 1):
                grow |= np.roll(np.roll(cur, dj, 0), di, 1)
        dist[grow & ~cur] = k
        cur = grow
    ring = np.where(dist <= 2, 2, np.where(dist <= 5, 1, 0))
    ring[river] = 1
    return ring


def scene(biome="forest"):
    rng = random.Random(7)
    nx, ny = 32, 28
    land = island_grid(nx, ny, 5 if biome == "forest" else 11, (15.5, 13.5), (11, 10))
    # river: a cell path across the west of the island, out to the sea
    river = np.zeros(land.shape, bool)
    path_cells = [(9, 5), (9, 6), (10, 7), (10, 8), (10, 9), (11, 10), (11, 11), (11, 12), (11, 13), (12, 14),
                  (12, 15), (12, 16), (12, 17), (12, 18), (12, 19), (12, 20), (12, 21)]
    for (i, j) in path_cells:
        if land[j, i] or (j > 3 and j < 23):
            river[j, i] = True
            river[j, i - 1] = True
    river &= land | np.roll(land, 1, 0) | np.roll(land, -1, 0)
    h = np.where(land & ~river, LAND, np.where(river, LAND - 2, 0))
    names = ["w0", "w1", "w2", "land", "path", "field_a", "field_b"]
    ring = rings(land & ~river, river)
    mat = np.where(land & ~river, 3, ring)
    mat[river] = 2
    # village path (cells), field (alternating rows)
    for (i, j) in [(13, 15), (14, 15), (15, 15), (16, 15), (17, 15), (17, 14), (17, 13), (18, 13), (19, 13),
                   (13, 16), (13, 17), (13, 18)]:
        if h[j, i] > 0:
            mat[j, i] = 4
    for j in range(16, 20):
        for i in range(16, 21):
            if h[j, i] > 0:
                mat[j, i] = 5 if j % 2 == 0 else 6
    polys, smoke = [], []
    dunes = biome == "dunes"
    # houses clustered around the path end (one landmark cabin + two small + shed)
    for args in ([14 * C, 10 * C, 12, 8, 8, "x"], [19 * C + 2, 9 * C, 10, 8, 7, "y"], [17 * C + 2, 5 * C + 2, 8, 6, 6, "x"]):
        ps, sm = cabin(*args[:5], ridge=args[5], flat_roof=dunes, chimney=True)
        polys += ps
        if sm:
            smoke.append(sm)
    ps, _ = cabin(10 * C + 2, 13 * C + 2, 6, 6, 5, ridge="y", flat_roof=dunes, chimney=False, windows=1)
    polys += ps
    polys += ruin(16 * C, 21 * C)
    # bridge over the river at the path
    bj = 15
    bi = [i for (i, j) in path_cells if j == bj][0]
    polys.append(box((bi - 1) * C - 1, bj * C + 1, LAND - 1, (bi + 1) * C + 1, bj * C + 3, LAND,
                     {"top": {"m": "wood", "tone": "top"}, "px": {"m": "wood", "tone": "lit"},
                      "py": {"m": "wood", "tone": "shade"}, "*": {"m": "wood"}}, tag="bridge"))
    # jetty out to sea at the south-west shore
    jx, jy = 7 * C, 16 * C
    while jx < nx * C and not land[jy // C, jx // C]:
        jx += C
    polys.append(box(jx - 14, jy, LAND - 3, jx + 1, jy + 3, LAND - 2,
                     {"top": {"m": "wood", "tone": "top"}, "px": {"m": "wood", "tone": "lit"},
                      "py": {"m": "wood", "tone": "shade"}, "*": {"m": "wood"}}, tag="jetty"))
    for px_ in (jx - 14, jx - 8):
        polys.append(box(px_, jy + 3, -2, px_ + 1, jy + 4, LAND - 3, solid("wood"), tag="jetty"))
    # trees: stands behind the village (small i + j is "back" on screen) and along the east rim; never in front of
    # a house (cells with larger i and j than a house, close by, would hide it)
    houses = [p for p in polys if p.get("tag") in ("house", "ruin", "bridge", "jetty")]
    foot = set()
    for p in houses:
        xs = [v[0] for v in p["verts"]]
        ys = [v[1] for v in p["verts"]]
        for a in range(int(min(xs) // C) - 1, int(max(xs) // C) + 2):
            for b in range(int(min(ys) // C) - 1, int(max(ys) // C) + 2):
                foot.add((a, b))
        hi_, hj_ = int(max(xs) // C), int(max(ys) // C)
        for a in range(hi_ - 2, hi_ + 4):
            for b in range(hj_ - 2, hj_ + 4):
                if a >= hi_ - 1 and b >= hj_ - 1:
                    foot.add((a, b))
    for a in range(19, 25):          # keep the deer's meadow clear (it grazes at cell ~21, 16)
        for b in range(13, 20):
            foot.add((a, b))
    spots = []
    for j in range(ny):
        for i in range(nx):
            if h[j, i] == LAND and mat[j, i] == 3 and (i, j) not in foot:
                nb = all(0 <= j + b < ny and 0 <= i + a < nx and h[j + b, i + a] == LAND
                         for a, b in ((-1, 0), (1, 0), (0, -1), (0, 1), (1, 1)))
                if nb:
                    spots.append((i, j))
    rng.shuffle(spots)
    spots.sort(key=lambda c: (c[0] + c[1]) + rng.random() * 6)       # back of the island first
    chosen = []
    for (i, j) in spots:
        gap = 3 if dunes else 2
        if any(max(abs(i - a), abs(j - b)) < gap - (0 if dunes else 1) or abs(i - a) + abs(j - b) < gap
               for a, b in chosen):
            continue
        chosen.append((i, j))
        if len(chosen) >= 24:
            break
    for (i, j) in chosen:
        cx, cy = i * C + 2, j * C + 2
        if dunes:
            polys += palm(cx, cy, 12 + 2 * ((i + j) % 3))
        else:
            polys += fir(cx, cy, size=[0.75, 1.0, 1.25][(i * 7 + j) % 3])
    dx_, dy_ = 21 * C, 17 * C - 2
    hx_, hy_ = 7 * C, 20 * C
    frames_ = []
    for f in range(24):
        dip = 1 if 8 <= f < 16 else 0
        hdip = 1 if 14 <= f < 20 else 0
        frames_.append(deer(dx_, dy_, head_dip=dip) + heron(hx_, hy_, 0, hdip))
    pal = json.loads((ROOT / "styles" / ("flat" + ("_dunes" if dunes else "") + ".json")).read_text())
    ramps = dict(pal["ramps"])
    materials = {
        "w0": {"ramp": "bg", "top": 0, "shadow": 0}, "w1": {"ramp": "bg", "top": 2, "shadow": 0},
        "w2": {"ramp": "stone", "top": 0, "shadow": 2, "shadow_ramp": "bg"},
        "land": {"ramp": "land", "top": 1, "shadow": 2, "shadow_ramp": "bg"},
        "path": {"ramp": "path", "top": 2, "shadow": 2, "shadow_ramp": "bg"},
        "field_a": {"ramp": "land", "top": 2, "shadow": 2, "shadow_ramp": "bg"},
        "field_b": {"ramp": "land", "top": 0, "shadow": 2, "shadow_ramp": "bg"},
        "earth": {"ramp": "cliff" if dunes else "wall", "top": 1, "lit": 1, "shade": 0},
        "wall": {"ramp": "wall", "top": 1, "lit": 1, "shade": 0},
        "roof": {"ramp": "roof", "top": 2, "lit": 1, "shade": 0},
        "chimney": {"ramp": "stone", "top": 1, "lit": 1, "shade": 0},
        "window": {"ramp": "glow_fire", "top": 1}, "door": {"ramp": "ink", "top": 1},
        "tree": {"ramp": "tree", "top": 2, "lit": 2, "shade": 1},
        "bark": {"ramp": "trunk", "top": 1, "lit": 1, "shade": 0},
        "stone": {"ramp": "stone", "top": 1, "lit": 1, "shade": 0, "shadow": 0},
        "wood": {"ramp": "trunk", "top": 1, "lit": 1, "shade": 0},
        "deer": {"ramp": "fur_tan", "top": 1, "lit": 1, "shade": 0},
        "antler": {"ramp": "fur_white", "top": 1}, "tail": {"ramp": "fur_white", "top": 1},
        "heron": {"ramp": "fur_white", "top": 1, "lit": 1, "shade": 0},
        "leg": {"ramp": "ink", "top": 0}, "beak": {"ramp": "glow_fire", "top": 0},
        "smoke": {"ramp": "roof", "top": 2},
    }
    NIGHT = {"w0": {"top": 0}, "w1": {"top": 1, "shadow": 0}, "w2": {"top": 1, "shadow": 0},
             "land": {"top": 2, "shadow": 1}, "path": {"top": 3, "shadow": 1}, "field_a": {"top": 2, "shadow": 1},
             "field_b": {"top": 1, "shadow": 1}, "earth": {"lit": 1, "shade": 0, "top": 1},
             "wall": {"lit": 2, "shade": 1, "top": 2}, "roof": {"top": 4, "lit": 3, "shade": 2},
             "chimney": {"top": 2, "lit": 2, "shade": 1}, "tree": {"top": 1, "lit": 1, "shade": 0},
             "bark": {"top": 1, "lit": 1, "shade": 0}, "stone": {"top": 2, "lit": 2, "shade": 1},
             "wood": {"top": 2, "lit": 1, "shade": 0}, "deer": {"top": 2, "lit": 2, "shade": 1},
             "heron": {"top": 4, "lit": 3, "shade": 2}, "smoke": {"top": 3}}
    if dunes:
        materials["wall"] = {"ramp": "wall", "top": 1, "lit": 1, "shade": 0}
        materials["field_a"] = {"ramp": "path", "top": 2, "shadow": 1, "shadow_ramp": "cliff"}
        materials["field_b"] = {"ramp": "land", "top": 0, "shadow": 1, "shadow_ramp": "cliff"}
        materials["land"] = {"ramp": "land", "top": 1, "shadow": 0, "shadow_ramp": "cliff"}
        materials["path"] = {"ramp": "path", "top": 2, "shadow": 0, "shadow_ramp": "cliff"}
        materials["smoke"] = {"ramp": "path", "top": 2}
        materials["w1"] = {"ramp": "bg", "top": 1, "shadow": 0}
        materials["w2"] = {"ramp": "bg", "top": 2, "shadow": 1}
        materials["deer"] = {"ramp": "fur_brown", "top": 1, "lit": 1, "shade": 0}
    for k, v in NIGHT.items():
        materials[k]["night"] = v
    W, H = 256, 164
    return {"name": "flat_" + biome, "camera": "iso_exact", "size": [W, H], "origin": [116, 30],
            "light": pal["light"], "palette": ramps, "materials": materials,
            "ground": {"cell": C, "h": h.astype(int).tolist(), "mat": mat.astype(int).tolist(), "names": names,
                       "outside": 0, "side": "earth"},
            "polys": polys, "smoke": [{"at": s, "m": "smoke", "puffs": 2, "rise": 10, "size": 2, "drift": -4}
                                      for s in smoke],
            "anim": frames_,
            "glints": {"on": ["w0", "w1"], "ramp": "bg", "tone": 2, "count": 10, "seed": 4, "on_frames": 5},
            "night": dict(pal["night"], glow_mats=["window"], pool_r=12)}

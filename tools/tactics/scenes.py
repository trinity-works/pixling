"""Crisp Tactics scenes: the calibration valley and the harbour, each in two biomes (valley, autumn).

Each scene function returns a pp.iso scene dict: the cell heightfield and ground materials, the props from kit.py,
held-key animal frames, smoke, glints, ground detail, terrain AA and the soft line. Layout coordinates are kit
units on an unpadded 84x84-cell field; finish() pads the field, scales the world by K and centres the screen.
"""
import json
import random
from pathlib import Path

import numpy as np

from pp.iso import scale, shift
from tools.tactics.kit import (C, F, LAND, arch, boat, box, bridge, broken_wall, conifer, crates, cube_tree, fox,
                               heron, house, new_grp, pier, pillar, reset_groups, ruined_house, sheep, slab, stag,
                               stairs, stall, tree_pair, well, windmill)

ROOT = Path(__file__).resolve().parents[2]
K = 2             # world scale: every kit and layout unit becomes K px-units (bigger props, longer clean runs)
PAD = 40          # extra lattice cells on every side so the screen is always over ground


def style(biome):
    return json.loads((ROOT / "styles" / ("tactics" + ("_autumn" if biome == "autumn" else "") + ".json")).read_text())

def materials(biome):
    m = {
        # name: ramp + tone indices (top, lit = right face, shade = left face), line = own-dark index for selout
        "grass": {"ramp": "grass", "top": 2, "shadow": 1, "line": 1},
        "grass_b": {"ramp": "grass", "top": 3, "shadow": 1},
        "plaza": {"ramp": "path", "top": 3, "shadow": 0, "shadow_ramp": "path"},
        "plaza_b": {"ramp": "path", "top": 2, "shadow": 0, "shadow_ramp": "path"},
        "path": {"ramp": "path", "top": 2, "shadow": 0, "shadow_ramp": "path"},
        "field_a": {"ramp": "leaf_b", "top": 2, "shadow": 1},
        "field_b": {"ramp": "leaf_b", "top": 1, "shadow": 0},
        "w_deep": {"ramp": "water", "top": 2, "shadow": 1},
        "w_mid": {"ramp": "water", "top": 3, "shadow": 2},
        "w_shal": {"ramp": "water", "top": 4, "shadow": 3},
        "bank": {"ramp": "wood", "top": 1, "lit": 1, "shade": 0},
        "quay": {"ramp": "stone_b", "top": 1, "lit": 1, "shade": 0},
        "stone": {"ramp": "stone", "top": 2, "lit": 1, "shade": 0, "line": 0},
        "slab": {"ramp": "path", "top": 3, "lit": 2, "shade": 1, "line": 1},
        "mortar_l": {"ramp": "stone", "top": 0}, "mortar_s": {"ramp": "stone_b", "top": 0},
        "moss": {"ramp": "moss", "top": 1},
        "plaster": {"ramp": "plaster", "top": 2, "lit": 2, "shade": 1, "line": 0},
        "roof": {"ramp": "roof", "top": 2, "lit": 1, "shade": 0, "line": 0},
        "window": {"ramp": "pane", "top": 0}, "door": {"ramp": "wood", "top": 0},
        "leaf": {"ramp": "leaf", "top": 2, "lit": 1, "shade": 0, "line": 0},
        "leaf_b": {"ramp": "leaf_b", "top": 2, "lit": 1, "shade": 0, "line": 0},
        "trunk": {"ramp": "trunk", "top": 1, "lit": 1, "shade": 0, "line": 0},
        "wood": {"ramp": "wood", "top": 2, "lit": 1, "shade": 0, "line": 0},
        "wood_l": {"ramp": "wood", "top": 2, "lit": 2, "shade": 1, "line": 0},
        "cloth": {"ramp": "cloth", "top": 2, "lit": 2, "shade": 1, "line": 0},
        "accent": {"ramp": "awn", "top": 2, "lit": 1, "shade": 0, "line": 0},
        "sail_accent": {"ramp": "accent", "top": 2, "lit": 1, "shade": 0, "line": 0},
        "goods_a": {"ramp": "goods", "top": 2, "lit": 1, "shade": 0},
        "goods_b": {"ramp": "goods", "top": 1, "lit": 1, "shade": 0},
        "water_in": {"ramp": "water", "top": 1, "lit": 1, "shade": 0},
        "fur_tan": {"ramp": "fur_tan", "top": 2, "lit": 1, "shade": 0, "line": 0},
        "fur_orange": {"ramp": "fur_orange", "top": 2, "lit": 1, "shade": 0, "line": 0},
        "fur_white": {"ramp": "fur_white", "top": 2, "lit": 2, "shade": 1},
        "fur_dark": {"ramp": "fur_dark", "top": 1, "lit": 1, "shade": 0, "line": 0},
        "antler": {"ramp": "cloth", "top": 2, "lit": 1, "shade": 0, "line": 0},
        "wool": {"ramp": "wool", "top": 2, "lit": 2, "shade": 1, "line": 0},
        "heron": {"ramp": "fur_white", "top": 2, "lit": 2, "shade": 1, "line": 0},
        "beak": {"ramp": "accent", "top": 2},
        "smoke": {"ramp": "cloth", "top": 1},
        "tuft": {"ramp": "grass", "top": 1},
        "flower_a": {"ramp": "cloth", "top": 2}, "flower_b": {"ramp": "stone", "top": 1},
    }
    # every non-terrain material casts onto the ground in the deep shadow tone of the ground under it
    for k in ("grass", "grass_b", "field_a", "field_b"):
        m[k]["shadow_ramp"] = m[k]["ramp"]
    m["grass"]["shadow"] = 0
    m["grass_b"]["shadow"] = 0
    m["grass"]["shadow_ramp"] = "grass"
    m["grass_b"]["shadow_ramp"] = "grass"
    return m


def ground_grid(kind):
    """Cell heightfield + material ids for the valley or harbour (cells of C units). Layout coordinates are the
    unpadded ones (0..84); the arrays are padded by PAD cells and props are shifted by PAD*C in finish()."""
    nx, ny = 84 + 2 * PAD, 84 + 2 * PAD
    h = np.full((ny, nx), LAND, int)
    names = ["grass", "grass_b", "plaza", "plaza_b", "path", "field_a", "field_b", "w_deep", "w_mid", "w_shal"]
    mat = np.zeros((ny, nx), int)
    jj, ii = np.mgrid[0:ny, 0:nx]
    rng = np.random.RandomState(4)
    # soft grass patches (two tones): low-frequency blobs on the cell lattice, smoothed so every patch edge is a
    # run of whole cells (no 1-cell spurs) - variation by density, never noise
    blob = rng.rand(ny // 5 + 2, nx // 5 + 2)
    fy, fx = (jj % 5) / 5.0, (ii % 5) / 5.0
    a, b = blob[jj // 5, ii // 5], blob[jj // 5, ii // 5 + 1]
    c, d = blob[jj // 5 + 1, ii // 5], blob[jj // 5 + 1, ii // 5 + 1]
    field_ = (a * (1 - fx) + b * fx) * (1 - fy) + (c * (1 - fx) + d * fx) * fy
    patch = field_ > 0.66
    for _ in range(3):
        nb = (np.roll(patch, 1, 0).astype(int) + np.roll(patch, -1, 0) + np.roll(patch, 1, 1) + np.roll(patch, -1, 1))
        patch = np.where(patch & (nb <= 1), False, np.where(~patch & (nb >= 3), True, patch))
    mat[patch] = 1
    j, i = jj - PAD, ii - PAD
    if kind == "valley":
        # lake in the west (small i, large j): a lattice-aligned rectangle with a stepped notch
        lake = ((i < 30) & (j > 50)) | ((i < 22) & (j > 44)) | ((i < 36) & (j > 60))
        # river from the north-east down to the lake, 2 cells wide, stepped (whole-cell steps, never 1-cell jogs)
        river = np.zeros_like(lake)
        cells = []
        ci, cj = 70, -30
        while cj < 64:
            cells.append((ci, cj))
            cj += 1
            if cj % 4 == 0 and ci > 30:
                ci -= 2
        for (a, b) in cells:
            river[b + PAD, a + PAD - 2:a + PAD + 3] = True
        water = lake | river
        h[water] = 0
        mat[water] = 8
        mat[lake & ~((i < 26) & (j > 54))] = 9
        mat[lake & ((i < 24) & (j > 58))] = 7
        # plaza (courtyard) east of the river, with a path to the bridge and to the field
        plaza = (i >= 50) & (i < 64) & (j >= 36) & (j < 50)
        mat[plaza] = 2
        mat[plaza & (((i // 2) + (j // 2)) % 5 == 0)] = 3
        path = ((j >= 41) & (j < 43) & (i >= 36) & (i < 50)) | ((i >= 56) & (i < 58) & (j >= 50) & (j < 66))
        mat[path & ~water] = 4
        # field south-east: furrows along x
        field = (i >= 62) & (i < 78) & (j >= 60) & (j < 74)
        mat[field] = np.where((j[field] % 2) == 0, 5, 6)
        return h, mat, names, dict(water=water, plaza=plaza, path=path, field=field, cells=cells)
    # harbour: a corner basin (rows j > 44 and columns i < 40 are sea), quay edges along both iso axes
    sea = (j > 44) | (i < 40)
    sea &= ~((i >= 66) & (j > 44) & (j < 52))          # a short mole on the east side
    h[sea] = 0
    mat[sea] = 7
    def grow(m, r):
        g = m.copy()
        for dj in range(-r, r + 1):
            for di in range(-r, r + 1):
                g |= np.roll(np.roll(m, dj, 0), di, 1)
        return g
    near = grow(~sea, 2)
    mid = grow(~sea, 6)
    mat[sea & mid] = 8
    mat[sea & near] = 9
    market = (i >= 48) & (i < 62) & (j >= 26) & (j < 38)
    mat[market] = 2
    mat[market & (((i // 2) + (j // 2)) % 5 == 0)] = 3
    road = (((j >= 31) & (j < 33) & (i >= 62) & (i < 84)) | ((i >= 54) & (i < 56) & (j >= 6) & (j < 26))
            | ((i >= 46) & (i < 48) & (j >= 38) & (j < 45)))
    mat[road & ~sea] = 4
    return h, mat, names, dict(water=sea, plaza=market, path=road)


def footprint(polys):
    cells = set()
    for p in polys:
        xs = [v[0] for v in p["verts"]]
        ys = [v[1] for v in p["verts"]]
        for a in range(int(min(xs) // C) - 1, int(max(xs) // C) + 2):
            for b in range(int(min(ys) // C) - 1, int(max(ys) // C) + 2):
                cells.add((a, b))
    return cells


def front_of(polys, depth=5):
    """Cells in front of (larger x+y than) the given props, which a tree there would hide."""
    cells = set()
    for p in polys:
        xs = [v[0] for v in p["verts"]]
        ys = [v[1] for v in p["verts"]]
        i0, i1 = int(min(xs) // C), int(max(xs) // C)
        j0, j1 = int(min(ys) // C), int(max(ys) // C)
        for a in range(i0 - 1, i1 + depth):
            for b in range(j0 - 1, j1 + depth):
                if a + b >= i0 + j0:
                    cells.add((a, b))
    return cells


def scatter_trees(h, mat, avoid, rng, region, n, kinds, min_gap=3):
    ny, nx = h.shape
    spots = []
    for (i, j) in region:
        I, J = i + PAD, j + PAD
        if 2 <= I < nx - 2 and 2 <= J < ny - 2 and (i, j) not in avoid and mat[J, I] in (0, 1):
            if all(h[J + b, I + a] == LAND for a in (-2, -1, 0, 1, 2) for b in (-2, -1, 0, 1, 2)):
                spots.append((i, j))
    rng.shuffle(spots)
    chosen = []
    for (i, j) in spots:
        if any(max(abs(i - a), abs(j - b)) < min_gap for a, b in chosen):
            continue
        chosen.append((i, j))
        if len(chosen) >= n:
            break
    out = []
    for k, (i, j) in enumerate(chosen):
        kind = kinds[k % len(kinds)]
        x, y = i * C + 2, j * C + 2
        if kind == "cube":
            out += cube_tree(x, y, 10 if k % 3 == 0 else 8, "leaf" if k % 4 else "leaf_b", 5 + (k % 2))
        elif kind == "pair":
            out += tree_pair(x, y)
        else:
            out += conifer(x, y, m="leaf" if k % 2 else "leaf_b")
    return out


def valley(biome="valley"):
    reset_groups()
    rng = random.Random(9)
    h, mat, names, R = ground_grid("valley")
    polys, smoke = [], []
    # landmark: the ruined courtyard on the plaza (i 50-64, j 36-50 -> x 200-256, y 144-200)
    X0, Y0 = 50 * C, 36 * C
    polys += arch(X0 + 6, Y0 + 2, "x", span=8, h=14)
    polys += arch(X0 + 2, Y0 + 16, "y", span=8, h=12, broken=4)
    polys += pillar(X0 + 36, Y0 + 6, h=16)
    polys += broken_wall(X0 + 30, Y0 + 40, "x", n=21, steps=(9, 9, 7, 5, 4, 3, 2))
    polys += stairs(X0 + 22, Y0 + 32, n=5, w=8)
    polys += well(X0 + 24, Y0 + 20)
    for (sx, sy, w, d) in ((X0 + 12, Y0 + 34, 3, 2), (X0 + 16, Y0 + 30, 2, 2), (X0 + 40, Y0 + 26, 3, 2),
                           (X0 + 34, Y0 + 18, 2, 3), (X0 + 10, Y0 + 44, 3, 2)):
        polys += slab(sx, sy, w, d)
    # houses cluster round the courtyard (north and east of it)
    for (hx, hy, w, d, hh, ridge) in ((X0 + 4, Y0 - 22, 12, 10, 7, "x"), (X0 + 22, Y0 - 18, 10, 8, 6, "y"),
                                      (X0 + 52, Y0 + 2, 12, 10, 7, "y"), (X0 + 50, Y0 + 22, 10, 8, 6, "x"),
                                      (X0 + 38, Y0 - 24, 10, 8, 6, "x")):
        ps, sm = house(hx, hy, w, d, hh, ridge)
        polys += ps
        if sm:
            smoke.append(sm)
    polys += ruined_house(X0 + 54, Y0 + 40)
    # bridge over the river on the path (row j 41-43)
    cells = R["cells"]
    bi = [a for (a, b) in cells if b == 41][0]
    polys += bridge((bi - 3) * C, 41 * C - 2, "x", n=6 * C)
    # field fence + sheep
    for k in range(4):
        g = new_grp()
        polys.append(box(62 * C + k * 8, 60 * C - 1, LAND, 62 * C + k * 8 + 1, 60 * C, LAND + 4, F("wood"), g, tag="fence"))
        polys.append(box(62 * C + k * 8, 60 * C - 1, LAND + 2, 62 * C + k * 8 + 8, 60 * C, LAND + 3, F("wood"), g, tag="fence"))
    # trees: big stands west of the river and south, never in front of the village
    built = [p for p in polys]
    avoid = footprint(built) | front_of(built, 6)
    avoid |= {(a, b) for a in range(60, 80) for b in range(56, 76)}       # field
    avoid |= {(a, b) for a in range(28, 50) for b in range(36, 50)}       # path to the bridge, the stag's meadow
    avoid |= {(a, b) for a in range(44, 52) for b in range(22, 30)}       # the fox
    vis = [(a, b) for a in range(-10, 100) for b in range(-10, 100) if 56 <= a + b <= 140 and -16 <= a - b <= 44]
    north = [c for c in vis if c[0] + c[1] <= 82]
    west = [c for c in vis if c[0] - c[1] <= 2 and c[0] + c[1] > 82]
    east = [c for c in vis if c[0] - c[1] >= 26 and c[0] + c[1] > 82]
    south = [c for c in vis if c[0] + c[1] >= 120 and -2 < c[0] - c[1] < 26]
    polys += scatter_trees(h, mat, avoid, rng, north, 26, ["cube", "pair", "conifer", "cube"], 4)
    polys += scatter_trees(h, mat, avoid, rng, west, 12, ["cube", "pair", "cube"], 4)
    polys += scatter_trees(h, mat, avoid, rng, east, 10, ["conifer", "cube", "pair"], 4)
    polys += scatter_trees(h, mat, avoid, rng, south, 5, ["cube", "pair"], 5)
    # animals (held keys): stag in the meadow by the path, sheep in the field, heron in the lake shallows, fox
    anim = []
    for f in range(24):
        dip = 1 if 8 <= f < 16 else 0
        g_st = 900
        a = stag(43 * C, 46 * C, dip=dip, g=g_st)
        a += sheep(66 * C, 61 * C, dip=1 if f >= 12 else 0) + sheep(70 * C + 2, 63 * C, dip=0 if f >= 12 else 1)
        hc = [a_ for (a_, b_) in cells if b_ == 29][0]
        a += heron(hc * C, 29 * C + 1, 0, 1 if 14 <= f < 20 else 0)
        a += fox(47 * C, 26 * C)
        anim.append(a)
    return finish("tactics_" + biome, biome, h, mat, names, polys, smoke, anim, R, size=(400, 300), origin=(226, 168))


def harbour(biome="valley"):
    reset_groups()
    rng = random.Random(5)
    h, mat, names, R = ground_grid("harbour")
    polys, smoke = [], []
    X0, Y0 = 48 * C, 26 * C
    for (sx, sy) in ((X0 + 4, Y0 + 4), (X0 + 18, Y0 + 4), (X0 + 32, Y0 + 4), (X0 + 4, Y0 + 24),
                     (X0 + 18, Y0 + 24), (X0 + 32, Y0 + 24)):
        polys += stall(sx, sy, m="accent")
    polys += well(X0 + 46, Y0 + 14)
    polys += crates(X0 + 6, Y0 + 44)
    polys += crates(X0 + 30, Y0 + 70)
    polys += windmill(40 * C + 1, 29 * C)
    for (hx, hy, w, d, hh, ridge) in ((X0 + 2, Y0 - 30, 12, 10, 7, "x"), (X0 + 22, Y0 - 26, 10, 8, 6, "y"),
                                      (X0 + 60, Y0 + 2, 12, 10, 7, "y"), (X0 + 62, Y0 + 24, 10, 8, 6, "x"),
                                      (X0 - 14, Y0 - 12, 10, 8, 6, "y")):
        ps, sm = house(hx, hy, w, d, hh, ridge)
        polys += ps
        if sm:
            smoke.append(sm)
    # quayside: a pier into the basin, boats moored along it and off the mole
    polys += pier(46 * C, 45 * C, n=36, along="y")
    polys += boat(48 * C + 2, 48 * C)
    polys += boat(52 * C, 54 * C + 2)
    polys += boat(60 * C, 49 * C)
    polys += boat(36 * C, 36 * C)
    built = list(polys)
    avoid = footprint(built) | front_of(built, 6)
    avoid |= {(a, b) for a in range(44, 66) for b in range(36, 46)}     # quayside walk, the stag
    vis = [(a, b) for a in range(-10, 100) for b in range(-10, 100) if 46 <= a + b <= 126 and -8 <= a - b <= 50]
    north = [c for c in vis if c[0] + c[1] <= 70]
    east = [c for c in vis if c[0] - c[1] >= 30 and c[0] + c[1] > 70]
    polys += scatter_trees(h, mat, avoid, rng, north, 16, ["cube", "pair", "conifer"], 4)
    polys += scatter_trees(h, mat, avoid, rng, east, 12, ["cube", "conifer", "pair"], 4)
    anim = []
    for f in range(24):
        a = sheep(70 * C, 38 * C, dip=1 if f >= 12 else 0)
        a += heron(44 * C, 47 * C, 0, 1 if 14 <= f < 20 else 0)
        a += stag(58 * C, 40 * C, dip=1 if 8 <= f < 16 else 0, g=900)
        anim.append(a)
    return finish("tactics_harbour_" + biome, biome, h, mat, names, polys, smoke, anim, R, size=(400, 300),
                  origin=(212, 150), side="quay")


def finish(name, biome, h, mat, names, polys, smoke, anim, R, size, origin, side="bank"):
    """origin here is the unpadded focus point (x, y) the screen centres on."""
    t = PAD * C
    polys = [scale(shift(p, t), K) for p in polys]
    anim = [[scale(shift(p, t), K) for p in fr] for fr in anim]
    smoke = [[(s_[0] + t) * K, (s_[1] + t) * K, s_[2] * K] for s_ in smoke]
    fx, fy = (origin[0] + t) * K, (origin[1] + t) * K
    origin = (int(round(size[0] / 2 - (fx - fy))), int(round(size[1] / 2 - ((fx + fy) / 2 - LAND * K))))
    h = h * K
    st = style(biome)
    mats = materials(biome)
    for p in polys:
        for f in p["faces"].values():
            if f["m"] == "accent" and biome == "autumn" and p.get("tag") in ("boat", "mill"):
                f["m"] = "sail_accent"
    return {"name": name, "camera": "iso_exact", "size": list(size), "origin": list(origin),
            "light": st["light"], "palette": st["ramps"], "materials": mats,
            "ground": {"cell": C * K, "h": h.astype(int).tolist(), "mat": mat.astype(int).tolist(), "names": names,
                       "outside": 0, "side": side, "merge_rows": True},
            "polys": polys,
            "smoke": [{"at": s, "m": "smoke", "puffs": 3, "rise": 8 * K, "size": K, "drift": 3 * K} for s in smoke],
            "anim": anim,
            "glints": {"on": ["w_deep", "w_mid"], "ramp": "water", "tone": 4, "count": 14, "seed": 4, "on_frames": 5},
            "line": {"ink_ramp": "ink", "ink_tone": 1, "drop_contrast": 0.33, "aa": True},
            "terrain_aa": {"min_run": 2},
            "detail": {"tufts": 160, "flowers": 26, "moss": 0.22, "seed": 3}}

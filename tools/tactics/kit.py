"""Crisp Tactics kit: props and animals on the exact-iso lattice (pp/iso.py).

Everything has integer coordinates, so every edge is a uniform 2:1, 1:1 or vertical stair: cube canopies, slab stone
with masonry courses, gable roofs at pitch 0.5, stepped conifers. Each prop is one object group, so the soft line
(pp/iso_line.py) outlines props and never terrain. Units are kit units; scenes.py scales the world by K.
Animals carry a declared readability enlargement (about 1.6x true scale) and animate on held key poses.
"""
from pp.iso import box

C = 4             # cell size in iso units (one cell = an 8x4 px diamond)
LAND = 4          # land top z

_G = [0]


def reset_groups():
    _G[0] = 0


def new_grp():
    _G[0] += 1
    return _G[0]


def F(m, px=None, py=None):
    """Face table of one material: top, the right face (px) in shade, the left face (py) lit, with optional
    decals on the two side faces."""
    f = {"top": {"m": m, "tone": "top"}, "px": {"m": m, "tone": "shade"}, "py": {"m": m, "tone": "lit"},
         "*": {"m": m, "tone": "shade"}}
    if px:
        f["px"]["decals"] = px
    if py:
        f["py"]["decals"] = py
    return f


def masonry(x0, y0, z0, x1, y1, z1, course=3, brick=6):
    """Mortar courses + staggered joints on both visible faces of a stone box (face-local, whole units):
    (decals for the px face, decals for the py face)."""
    on_px = [{"u": [y0, y1], "v": [z0, z1], "m": "mortar_l", "course": course, "brick": brick, "z0": z0, "u0": y0}]
    on_py = [{"u": [x0, x1], "v": [z0, z1], "m": "mortar_s", "course": course, "brick": brick, "z0": z0, "u0": x0}]
    return on_px, on_py


def stone(x0, y0, z0, x1, y1, z1, grp, m="stone", course=4, brick=7, tag="ruin", plain=False):
    if plain or (z1 - z0) < 4:
        return box(x0, y0, z0, x1, y1, z1, F(m), grp, tag=tag)
    return box(x0, y0, z0, x1, y1, z1, F(m, *masonry(x0, y0, z0, x1, y1, z1, course, brick)), grp, tag=tag)


# ------------------------------------------------------------------ props

def cube_tree(x, y, s=8, m="leaf", trunk=5, z=LAND):
    g = new_grp()
    h = s // 2
    out = [box(x - 1, y - 1, z, x + 1, y + 1, z + trunk, F("trunk"), g, cast=False, tag="tree"),
           box(x - h, y - h, z + trunk, x + h, y + h, z + trunk + s, F(m), g, tag="tree")]
    return out


def tree_pair(x, y, m1="leaf", m2="leaf_b", z=LAND):
    return cube_tree(x, y, 8, m1, 5, z) + cube_tree(x + 6, y + 5, 6, m2, 4, z)


def conifer(x, y, z=LAND, m="leaf"):
    g = new_grp()
    out = [box(x - 1, y - 1, z, x + 1, y + 1, z + 2, F("trunk"), g, cast=False, tag="tree")]
    zz = z + 2
    for r, hh in ((4, 4), (3, 4), (2, 3), (1, 2)):
        out.append(box(x - r, y - r, zz, x + r, y + r, zz + hh, F(m), g, tag="tree"))
        zz += hh
    return out


def house(x, y, w=12, d=10, h=7, ridge="x", z=LAND, chimney=True):
    """Cream plaster walls (windows + door as decals), teal gable roof at pitch 0.5 (rakes land on 1:1 / flat)."""
    g = new_grp()
    x1, y1, ze = x + w, y + d, z + h
    wy = [{"u": [x + 2 + i * 4, x + 4 + i * 4], "v": [z + 3, z + 5], "m": "window"} for i in range(w // 4)
          if x + 4 + i * 4 <= x1 - 2]
    door = [{"u": [x1 - 4, x1 - 2], "v": [z, z + 4], "m": "door"}]
    wx = [{"u": [y + 2 + i * 4, y + 4 + i * 4], "v": [z + 3, z + 5], "m": "window"} for i in range(d // 4)
          if y + 4 + i * 4 <= y1 - 1]
    faces = {"py": {"m": "plaster", "tone": "lit", "decals": wy + door},
             "px": {"m": "plaster", "tone": "shade", "decals": wx}, "*": {"m": "plaster", "tone": "shade"},
             "top": {"m": "plaster", "tone": "top"}}
    out = []
    s = 0.5
    o = 1
    th = 1.5
    if ridge == "x":
        ym = (y + y1) / 2
        zr = ze + s * (d / 2)
        wall = box(x, y, z, x1, y1, zr, faces, g, tag="house")
        wall["planes"] += [[[0, s, 1], zr + s * ym, "rf"], [[0, -s, 1], zr - s * ym, "rb"]]
        out.append(wall)
        for sg in (1, -1):
            n = [0, sg * s, 1]
            c_up = zr + th + sg * s * ym
            ylo, yhi = (ym, y1 + o) if sg > 0 else (y - o, ym)
            planes = [[n, c_up, "top"], [[-n[0], -n[1], -n[2]], -(c_up - th - 0.01), "bot"],
                      [[1, 0, 0], x1 + o, "px"], [[-1, 0, 0], -(x - o), "nx"],
                      [[0, 1, 0], yhi, "py"], [[0, -1, 0], -ylo, "ny"]]
            tone = "lit" if sg > 0 else "top"
            verts = [(xx, yy, zz) for xx in (x - o, x1 + o) for yy in (ylo, yhi) for zz in (ze - 1, zr + th)]
            out.append({"planes": planes, "faces": {"top": {"m": "roof", "tone": tone}, "px": {"m": "roof", "tone": "shade"},
                                                    "py": {"m": "roof", "tone": "lit"}, "*": {"m": "roof", "tone": "shade"}},
                        "verts": [list(v) for v in verts], "cast": True, "tag": "house", "grp": g, "line": True})
    else:
        xm = (x + x1) / 2
        zr = ze + s * (w / 2)
        wall = box(x, y, z, x1, y1, zr, faces, g, tag="house")
        wall["planes"] += [[[s, 0, 1], zr + s * xm, "rf"], [[-s, 0, 1], zr - s * xm, "rb"]]
        out.append(wall)
        for sg in (1, -1):
            n = [sg * s, 0, 1]
            c_up = zr + th + sg * s * xm
            xlo, xhi = (xm, x1 + o) if sg > 0 else (x - o, xm)
            planes = [[n, c_up, "top"], [[-n[0], -n[1], -n[2]], -(c_up - th - 0.01), "bot"],
                      [[1, 0, 0], xhi, "px"], [[-1, 0, 0], -xlo, "nx"],
                      [[0, 1, 0], y1 + o, "py"], [[0, -1, 0], -(y - o), "ny"]]
            tone = "shade" if sg > 0 else "top"
            verts = [(xx, yy, zz) for xx in (xlo, xhi) for yy in (y - o, y1 + o) for zz in (ze - 1, zr + th)]
            out.append({"planes": planes, "faces": {"top": {"m": "roof", "tone": tone}, "px": {"m": "roof", "tone": "shade"},
                                                    "py": {"m": "roof", "tone": "lit"}, "*": {"m": "roof", "tone": "shade"}},
                        "verts": [list(v) for v in verts], "cast": True, "tag": "house", "grp": g, "line": True})
    smoke = None
    if chimney:
        cx, cy = (x1 - 3, y + 2) if ridge == "x" else (x + 2, y1 - 3)
        top = zr + th + 2
        out.append(box(cx, cy, ze, cx + 2, cy + 2, top, F("stone"), g, tag="house"))
        smoke = [cx + 1, cy + 1, top + 1]
    return out, smoke


def arch(x, y, along="x", span=8, h=14, z=LAND, broken=0):
    """Two masonry piers and a lintel; the soffit steps in by one unit twice (a stepped round arch)."""
    g = new_grp()
    t = 3
    out = []
    if along == "x":
        out.append(stone(x, y, z, x + t, y + t, z + h, g))
        out.append(stone(x + t + span, y, z, x + 2 * t + span, y + t, z + h - broken, g))
        out.append(stone(x, y, z + h, x + 2 * t + span - (span // 2 if broken else 0), y + t, z + h + 3, g))
        out.append(box(x + t, y, z + h - 2, x + t + 2, y + t, z + h, F("stone"), g, tag="ruin"))
        if not broken:
            out.append(box(x + t + span - 2, y, z + h - 2, x + t + span, y + t, z + h, F("stone"), g, tag="ruin"))
    else:
        out.append(stone(x, y, z, x + t, y + t, z + h, g))
        out.append(stone(x, y + t + span, z, x + t, y + 2 * t + span, z + h - broken, g))
        out.append(stone(x, y, z + h, x + t, y + 2 * t + span - (span // 2 if broken else 0), z + h + 3, g))
        out.append(box(x, y + t, z + h - 2, x + t, y + t + 2, z + h, F("stone"), g, tag="ruin"))
        if not broken:
            out.append(box(x, y + t + span - 2, z + h - 2, x + t, y + t + span, z + h, F("stone"), g, tag="ruin"))
    return out


def broken_wall(x, y, along="x", n=14, z=LAND, steps=(8, 8, 6, 6, 5, 3, 3)):
    g = new_grp()
    out = []
    seg = max(2, n // len(steps))
    for i, hh in enumerate(steps):
        if along == "x":
            out.append(stone(x + i * seg, y, z, x + (i + 1) * seg, y + 3, z + hh, g))
        else:
            out.append(stone(x, y + i * seg, z, x + 3, y + (i + 1) * seg, z + hh, g))
    return out


def pillar(x, y, h=16, z=LAND):
    g = new_grp()
    return [box(x - 1, y - 1, z, x + 4, y + 4, z + 2, F("stone"), g, tag="ruin"),
            stone(x, y, z + 2, x + 3, y + 3, z + h, g, course=3, brick=99),
            box(x - 1, y - 1, z + h, x + 4, y + 4, z + h + 2, F("stone"), g, tag="ruin")]


def stairs(x, y, n=5, w=8, z=LAND, dirn="y"):
    """Steps rising toward -y (or -x): each step 2 deep, 2 high, cheek walls on both sides."""
    g = new_grp()
    out = []
    for i in range(n):
        if dirn == "y":
            out.append(box(x, y + (n - 1 - i) * 2, z, x + w, y + (n - i) * 2, z + (i + 1) * 2, F("stone"), g, tag="ruin"))
        else:
            out.append(box(x + (n - 1 - i) * 2, y, z, x + (n - i) * 2, y + w, z + (i + 1) * 2, F("stone"), g, tag="ruin"))
    return out


def well(x, y, z=LAND):
    g = new_grp()
    out = [stone(x, y, z, x + 6, y + 1, z + 4, g, plain=True), stone(x, y + 5, z, x + 6, y + 6, z + 4, g, plain=True),
           stone(x, y + 1, z, x + 1, y + 5, z + 4, g, plain=True), stone(x + 5, y + 1, z, x + 6, y + 5, z + 4, g, plain=True),
           box(x + 1, y + 1, z, x + 5, y + 5, z + 2, F("water_in"), g, cast=False, tag="ruin"),
           box(x, y + 2, z + 4, x + 1, y + 4, z + 10, F("wood"), g, tag="ruin"),
           box(x + 5, y + 2, z + 4, x + 6, y + 4, z + 10, F("wood"), g, tag="ruin"),
           box(x, y + 2, z + 10, x + 6, y + 3, z + 11, F("wood"), g, tag="ruin")]
    return out


def slab(x, y, w=3, d=2, z=LAND):
    g = new_grp()
    return [box(x, y, z, x + w, y + d, z + 1, F("slab"), g, cast=False, tag="slab")]


def ruined_house(x, y, z=LAND):
    g = new_grp()
    return [stone(x, y, z, x + 12, y + 3, z + 9, g), stone(x, y + 3, z, x + 3, y + 12, z + 6, g),
            stone(x + 9, y + 3, z, x + 12, y + 7, z + 4, g), stone(x + 3, y + 9, z, x + 7, y + 12, z + 3, g)]


def bridge(x, y, along="x", n=16, z=LAND):
    g = new_grp()
    if along == "x":
        return [stone(x, y, z - 1, x + n, y + 6, z + 1, g, plain=True),
                box(x, y, z + 1, x + n, y + 1, z + 3, F("stone"), g, tag="bridge"),
                box(x, y + 5, z + 1, x + n, y + 6, z + 3, F("stone"), g, tag="bridge")]
    return [stone(x, y, z - 1, x + 6, y + n, z + 1, g, plain=True),
            box(x, y, z + 1, x + 1, y + n, z + 3, F("stone"), g, tag="bridge"),
            box(x + 5, y, z + 1, x + 6, y + n, z + 3, F("stone"), g, tag="bridge")]


def stall(x, y, z=LAND, m="accent"):
    """A market stall that reads as a stall: counter with goods, four posts, a striped awning."""
    g = new_grp()
    out = [box(x, y + 4, z, x + 8, y + 7, z + 3, F("wood"), g, tag="stall"),
           box(x + 1, y + 5, z + 3, x + 3, y + 6, z + 4, F("goods_a"), g, tag="stall"),
           box(x + 4, y + 5, z + 3, x + 6, y + 6, z + 4, F("goods_b"), g, tag="stall")]
    for px_, py_ in ((x, y), (x + 7, y), (x, y + 6), (x + 7, y + 6)):
        out.append(box(px_, py_, z, px_ + 1, py_ + 1, z + 8, F("wood"), g, tag="stall"))
    for i in range(4):
        out.append(box(x - 1 + i * 2.5, y - 1, z + 8, x - 1 + (i + 1) * 2.5, y + 8, z + 9,
                       F(m if i % 2 == 0 else "cloth"), g, tag="stall"))
    return out


def windmill(x, y, z=LAND):
    g = new_grp()
    out = [stone(x, y, z, x + 7, y + 7, z + 20, g, course=4, brick=7),
           box(x - 1, y - 1, z + 20, x + 8, y + 8, z + 23, F("roof"), g, tag="mill"),
           box(x + 1, y + 1, z + 23, x + 6, y + 6, z + 25, F("roof"), g, tag="mill")]
    # sails on the +x face: a vertical and a horizontal (along y) blade, accent trim at the tips
    cx, cy, cz = x + 8, y + 3, z + 17
    out += [box(cx, cy, cz - 9, cx + 1, cy + 1, cz + 10, F("cloth"), g, tag="mill"),
            box(cx, cy - 9, cz, cx + 1, cy + 10, cz + 1, F("cloth"), g, tag="mill"),
            box(cx, cy, cz + 8, cx + 1, cy + 1, cz + 10, F("accent"), g, tag="mill"),
            box(cx, cy + 8, cz, cx + 1, cy + 10, cz + 1, F("accent"), g, tag="mill")]
    return out


def boat(x, y, z=0):
    g = new_grp()
    return [box(x, y, z, x + 12, y + 5, z + 2, F("wood"), g, tag="boat"),
            box(x + 1, y + 1, z + 2, x + 11, y + 4, z + 3, F("wood_l"), g, tag="boat"),
            box(x + 5, y + 2, z + 3, x + 6, y + 3, z + 15, F("wood"), g, tag="boat"),
            box(x + 6, y + 2, z + 5, x + 11, y + 3, z + 14, F("cloth"), g, tag="boat"),
            box(x + 6, y + 2, z + 13, x + 11, y + 3, z + 14, F("accent"), g, tag="boat")]


def pier(x, y, n=24, z=LAND, along="y"):
    g = new_grp()
    out = []
    if along == "y":
        out.append(box(x, y, z - 1, x + 5, y + n, z, F("wood"), g, tag="pier"))
        for i in range(0, n, 6):
            out.append(box(x, y + i, -3, x + 1, y + i + 1, z - 1, F("wood"), g, tag="pier"))
            out.append(box(x + 4, y + i, -3, x + 5, y + i + 1, z - 1, F("wood"), g, tag="pier"))
    else:
        out.append(box(x, y, z - 1, x + n, y + 5, z, F("wood"), g, tag="pier"))
        for i in range(0, n, 6):
            out.append(box(x + i, y, -3, x + i + 1, y + 1, z - 1, F("wood"), g, tag="pier"))
            out.append(box(x + i, y + 4, -3, x + i + 1, y + 5, z - 1, F("wood"), g, tag="pier"))
    return out


def crates(x, y, z=LAND):
    g = new_grp()
    return [box(x, y, z, x + 3, y + 3, z + 3, F("wood_l"), g, tag="crate"),
            box(x + 3, y, z, x + 6, y + 3, z + 3, F("wood_l"), g, tag="crate"),
            box(x + 1, y, z + 3, x + 4, y + 3, z + 6, F("wood_l"), g, tag="crate")]


# ------------------------------------------------------------------ animals

def stag(x, y, z=LAND, dip=0, facing="x", g=None, legs=0):
    g = g or new_grp()
    f = F("fur_tan")
    a = F("antler")
    out = []
    if facing == "x":       # body along x, head at -x
        out.append(box(x + 2, y, z + 5, x + 11, y + 3, z + 10, f, g, tag="animal"))
        leg = [(x + 2, 0), (x + 9, 1)] if legs == 0 else [(x + 3, 1), (x + 8, 0)]
        for lx, k in leg:
            out.append(box(lx, y + 2, z, lx + 2, y + 3, z + 5, f, g, tag="animal"))
            out.append(box(lx + (1 if k else -1) + 1, y, z, lx + (1 if k else -1) + 2, y + 1, z + 5, F("fur_dark"), g, tag="animal"))
        if dip:
            out.append(box(x - 1, y, z + 2, x + 3, y + 3, z + 7, f, g, tag="animal"))
        else:
            out.append(box(x + 1, y, z + 9, x + 4, y + 3, z + 14, f, g, tag="animal"))
            out.append(box(x - 2, y, z + 12, x + 2, y + 3, z + 15, f, g, tag="animal"))
            out.append(box(x, y, z + 15, x + 1, y + 1, z + 19, a, g, tag="animal"))
            out.append(box(x, y + 2, z + 15, x + 1, y + 3, z + 19, a, g, tag="animal"))
            out.append(box(x - 1, y, z + 18, x + 2, y + 1, z + 19, a, g, tag="animal"))
            out.append(box(x - 1, y + 2, z + 18, x + 2, y + 3, z + 19, a, g, tag="animal"))
        out.append(box(x + 11, y + 1, z + 8, x + 12, y + 2, z + 10, F("fur_white"), g, tag="animal"))
    else:                   # body along y, head at -y
        out.append(box(x, y + 2, z + 5, x + 3, y + 11, z + 10, f, g, tag="animal"))
        leg = [(y + 2, 0), (y + 9, 1)] if legs == 0 else [(y + 3, 1), (y + 8, 0)]
        for ly, k in leg:
            out.append(box(x + 2, ly, z, x + 3, ly + 2, z + 5, f, g, tag="animal"))
            out.append(box(x, ly + (1 if k else -1) + 1, z, x + 1, ly + (1 if k else -1) + 2, z + 5, F("fur_dark"), g, tag="animal"))
        if dip:
            out.append(box(x, y - 1, z + 2, x + 3, y + 3, z + 7, f, g, tag="animal"))
        else:
            out.append(box(x, y + 1, z + 9, x + 3, y + 4, z + 14, f, g, tag="animal"))
            out.append(box(x, y - 2, z + 12, x + 3, y + 2, z + 15, f, g, tag="animal"))
            out.append(box(x, y, z + 15, x + 1, y + 1, z + 19, a, g, tag="animal"))
            out.append(box(x + 2, y, z + 15, x + 3, y + 1, z + 19, a, g, tag="animal"))
            out.append(box(x, y - 1, z + 18, x + 1, y + 2, z + 19, a, g, tag="animal"))
            out.append(box(x + 2, y - 1, z + 18, x + 3, y + 2, z + 19, a, g, tag="animal"))
        out.append(box(x + 1, y + 11, z + 8, x + 2, y + 12, z + 10, F("fur_white"), g, tag="animal"))
    return out


def sheep(x, y, z=LAND, dip=0):
    g = new_grp()
    out = [box(x, y, z + 2, x + 7, y + 5, z + 7, F("wool"), g, tag="animal")]
    for lx, ly in ((x + 1, y + 4), (x + 5, y + 4)):
        out.append(box(lx, ly, z, lx + 1, ly + 1, z + 2, F("fur_dark"), g, tag="animal"))
    out.append(box(x - 2, y + 1, z + (2 if dip else 4), x + 1, y + 4, z + (5 if dip else 7), F("fur_dark"), g, tag="animal"))
    return out


def fox(x, y, z=LAND):
    g = new_grp()
    return [box(x + 1, y, z + 2, x + 7, y + 3, z + 5, F("fur_orange"), g, tag="animal"),
            box(x - 1, y, z + 3, x + 2, y + 3, z + 6, F("fur_orange"), g, tag="animal"),
            box(x - 1, y, z + 6, x, y + 1, z + 7, F("fur_orange"), g, tag="animal"),
            box(x - 1, y + 2, z + 6, x, y + 3, z + 7, F("fur_orange"), g, tag="animal"),
            box(x + 7, y + 1, z + 3, x + 10, y + 2, z + 5, F("fur_white"), g, tag="animal"),
            box(x + 1, y + 2, z, x + 2, y + 3, z + 2, F("fur_dark"), g, tag="animal"),
            box(x + 6, y + 2, z, x + 7, y + 3, z + 2, F("fur_dark"), g, tag="animal")]


def heron(x, y, z=0, dip=0):
    g = new_grp()
    out = [box(x + 2, y, z, x + 3, y + 1, z + 6, F("fur_dark"), g, tag="animal"),
           box(x + 1, y, z + 6, x + 7, y + 3, z + 10, F("heron"), g, tag="animal")]
    if dip:
        out += [box(x - 1, y, z + 4, x + 2, y + 2, z + 8, F("heron"), g, tag="animal"),
                box(x - 3, y, z + 3, x - 1, y + 1, z + 4, F("beak"), g, tag="animal")]
    else:
        out += [box(x, y, z + 9, x + 2, y + 2, z + 15, F("heron"), g, tag="animal"),
                box(x - 3, y, z + 14, x, y + 1, z + 15, F("beak"), g, tag="animal")]
    return out

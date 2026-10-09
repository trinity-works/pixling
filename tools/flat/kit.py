"""Flat Minimal kit: cabins, firs, palms, a ruin and animals on the exact-iso lattice (pp/iso.py).

Integer coordinates on the lattice, so every edge is a clean 2:1, 1:1 or vertical stair. Roof pitch is 0.5 (both
roof planes show, gable edges flat and 1:1), fir tiers are pyramids with h = 4r (2:1 silhouettes). Roofs, trees and
palms don't cast; invisible box proxies cast for them, so every shadow edge stays on the lattice (flat, long shadows).
Animals carry a declared readability enlargement (about 1.3x true scale) and animate on held key poses.
"""
from pp.iso import box

C = 4            # cell size (units along an iso axis): one cell is an 8x4 px diamond
LAND = 6         # land top height in px (the chunky earth band)


def poly(planes, faces, verts, cast=True, tag="", hidden=False):
    return {"planes": [[list(n), c, k] for n, c, k in planes], "faces": faces, "verts": [list(v) for v in verts],
            "cast": cast, "tag": tag, "hidden": hidden}


def proxy(x0, y0, z0, x1, y1, z1):
    """An invisible box that only casts: keeps every shadow edge on the 2:1 lattice (flat, ref-like shadows)."""
    return box(x0, y0, z0, x1, y1, z1, {"*": {"m": "ink"}}, cast=True, tag="proxy", hidden=True)


def nocast(polys):
    for p in polys:
        p["cast"] = False
    return polys


def solid(m):
    return {"*": {"m": m}, "top": {"m": m}, "px": {"m": m}, "py": {"m": m}}


def pyramid(cx, cy, z0, r, h, m, tag="tree"):
    planes = [((h, 0, r), h * r + h * cx + r * z0, "px"), ((-h, 0, r), h * r - h * cx + r * z0, "nx"),
              ((0, h, r), h * r + h * cy + r * z0, "py"), ((0, -h, r), h * r - h * cy + r * z0, "ny"),
              ((0, 0, -1), -z0, "bot"), ((0, 0, 1), z0 + h - 2, "tip")]
    verts = [(cx + a, cy + b, z0) for a in (-r, r) for b in (-r, r)] + [(cx, cy, z0 + h)]
    return poly(planes, {"px": {"m": m, "tone": "lit"}, "py": {"m": m, "tone": "shade"},
                      "tip": {"m": m, "tone": "lit"}, "*": {"m": m}}, verts, False, tag)


def cabin(x, y, w, d, h, ridge="x", flat_roof=False, chimney=True, mats=None, z=LAND, windows=2):
    """A cabin on the lattice: walls (with the gable in the wall), two roof slabs, optional chimney, windows/door
    as decals on the two visible faces (+y front-left, +x right)."""
    m = dict(wall="wall", roof="roof", win="window", door="door")
    m.update(mats or {})
    out = []
    x1, y1, ze = x + w, y + d, z + h
    o = 1                                   # eave overhang
    # decals on the two visible faces; u runs along the face, v is height
    wy = [{"u": [x + 2 + i * 4, x + 4 + i * 4], "v": [z + 2, z + 5], "m": m["win"]} for i in range(windows)
          if x + 4 + i * 4 <= x1 - 1]
    door_py = [{"u": [x1 - 4, x1 - 2], "v": [z, z + 4], "m": m["door"]}] if w >= 8 else []
    wx = [{"u": [y + 2, y + 4], "v": [z + 2, z + 5], "m": m["win"]}] if d >= 6 else []
    faces = {"py": {"m": m["wall"], "tone": "shade", "decals": wy + door_py},
             "px": {"m": m["wall"], "tone": "lit", "decals": wx}, "*": {"m": m["wall"]}}
    if flat_roof:
        out.append(box(x, y, z, x1, y1, ze, faces, tag="house"))
        out.append(box(x - o, y - o, ze, x1 + o, y1 + o, ze + 2,
                       {"top": {"m": m["roof"], "tone": "top"}, "px": {"m": m["roof"], "tone": "lit"},
                        "py": {"m": m["roof"], "tone": "shade"}, "*": {"m": m["roof"]}}, tag="house"))
        top = ze + 2
    else:
        s = 0.5
        if ridge == "x":
            ym = (y + y1) / 2
            rise = s * (d / 2)
            zr = ze + rise
            # walls with the gable: box cut by the two roof planes
            wall = box(x, y, z, x1, y1, zr, faces, tag="house")
            wall["planes"] += [[[0, s, 1], zr + s * ym, "rf"], [[0, -s, 1], zr - s * ym, "rb"]]
            out.append(wall)
            th = 1.5
            for side, sg in (("f", 1), ("b", -1)):
                n = [0, sg * s, 1]
                c_up = zr + o * 0 + sg * s * ym + s * 0
                c_up = zr + th + sg * s * ym
                ylo, yhi = (ym, y1 + o) if sg > 0 else (y - o, ym)
                planes = [[n, c_up, "top"], [[-n[0], -n[1], -n[2]], -(c_up - th - 0.01), "bot"],
                          [[1, 0, 0], x1 + o, "px"], [[-1, 0, 0], -(x - o), "nx"],
                          [[0, 1, 0], yhi, "py"], [[0, -1, 0], -ylo, "ny"]]
                tone = "shade" if sg > 0 else "top"
                verts = [(xx, yy, zz) for xx in (x - o, x1 + o) for yy in (ylo, yhi) for zz in (ze - 1, zr + th)]
                out.append({"planes": planes, "faces": {"top": {"m": m["roof"], "tone": tone},
                                                        "px": {"m": m["roof"], "tone": "lit"},
                                                        "py": {"m": m["roof"], "tone": "shade"},
                                                        "*": {"m": m["roof"], "tone": "shade"}},
                            "verts": [list(v) for v in verts], "cast": True, "tag": "house"})
            top = zr + th
        else:
            xm = (x + x1) / 2
            rise = s * (w / 2)
            zr = ze + rise
            wall = box(x, y, z, x1, y1, zr, faces, tag="house")
            wall["planes"] += [[[s, 0, 1], zr + s * xm, "rf"], [[-s, 0, 1], zr - s * xm, "rb"]]
            out.append(wall)
            th = 1.5
            for sg in (1, -1):
                n = [sg * s, 0, 1]
                c_up = zr + th + sg * s * xm
                xlo, xhi = (xm, x1 + o) if sg > 0 else (x - o, xm)
                planes = [[n, c_up, "top"], [[-n[0], -n[1], -n[2]], -(c_up - th - 0.01), "bot"],
                          [[1, 0, 0], xhi, "px"], [[-1, 0, 0], -xlo, "nx"],
                          [[0, 1, 0], y1 + o, "py"], [[0, -1, 0], -(y - o), "ny"]]
                tone = "lit" if sg > 0 else "top"
                verts = [(xx, yy, zz) for xx in (xlo, xhi) for yy in (y - o, y1 + o) for zz in (ze - 1, zr + th)]
                out.append({"planes": planes, "faces": {"top": {"m": m["roof"], "tone": tone},
                                                        "px": {"m": m["roof"], "tone": "lit"},
                                                        "py": {"m": m["roof"], "tone": "shade"},
                                                        "*": {"m": m["roof"], "tone": "shade"}},
                            "verts": [list(v) for v in verts], "cast": True, "tag": "house"})
            top = zr + th
    nocast(out)
    out.append(proxy(x, y, z, x1, y1, int(round(ze + (top - ze) * 0.6))))
    if chimney:
        cx, cy = (x1 - 3, y + 2) if ridge == "x" else (x + 2, y1 - 3)
        out.append(box(cx, cy, ze, cx + 2, cy + 2, top + 2,
                       {"top": {"m": "chimney", "tone": "top"}, "px": {"m": "chimney", "tone": "lit"},
                        "py": {"m": "chimney", "tone": "shade"}, "*": {"m": "chimney"}}, tag="house"))
        smoke = [cx + 1, cy + 1, top + 3]
    else:
        smoke = None
    return out, smoke


def fir(cx, cy, size=1.0, z=LAND):
    r1 = max(2, int(round(3 * size)))
    r2 = max(1, r1 - 1)
    out = [box(cx - 1, cy - 1, z, cx + 1, cy + 1, z + 2, solid("bark"), tag="tree"),
           pyramid(cx, cy, z + 2, r1, 4 * r1, "tree"),
           pyramid(cx, cy, z + 2 + 2 * r1, r2, 4 * r2, "tree")]
    out[0]["cast"] = False
    out.append(proxy(cx - r1 + 1, cy - r1 + 1, z, cx + r1 - 1, cy + r1 - 1, z + 2 + 3 * r1))
    return out


def palm(cx, cy, hgt=14, z=LAND):
    return nocast(_palm(cx, cy, hgt, z)) + [proxy(cx - 1, cy - 1, z, cx + 1, cy + 1, z + hgt),
                                            proxy(cx - 4, cy - 1, z + hgt - 1, cx + 4, cy + 1, z + hgt + 1),
                                            proxy(cx - 1, cy - 4, z + hgt - 1, cx + 1, cy + 4, z + hgt + 1)]


def _palm(cx, cy, hgt=14, z=LAND):
    out = [box(cx - 1, cy - 1, z, cx + 1, cy + 1, z + hgt, solid("bark"), tag="tree")]
    zc = z + hgt
    # crown: a flat cross of fronds, each a thin slab, plus a centre block
    out.append(box(cx - 2, cy - 2, zc, cx + 2, cy + 2, zc + 2, {"top": {"m": "tree", "tone": "top"},
                                                                 "px": {"m": "tree", "tone": "lit"},
                                                                 "py": {"m": "tree", "tone": "shade"},
                                                                 "*": {"m": "tree"}}, tag="tree"))
    # fronds: one flat tone each (no 1-px side faces), the near pair a step darker than the far pair
    for (a0, b0, a1, b1, tone) in ((-6, -1, -2, 1, "top"), (2, -1, 6, 1, "shade"), (-1, -6, 1, -2, "top"),
                                   (-1, 2, 1, 6, "shade")):
        f = {"*": {"m": "tree", "tone": tone}, "top": {"m": "tree", "tone": tone}}
        out.append(box(cx + a0, cy + b0, zc - 1, cx + a1, cy + b1, zc + 1, f, tag="tree"))
    return out


def ruin(x, y, z=LAND):
    f = {"top": {"m": "stone", "tone": "top"}, "px": {"m": "stone", "tone": "lit"},
         "py": {"m": "stone", "tone": "shade"}, "*": {"m": "stone"}}
    return [box(x, y, z, x + 8, y + 2, z + 6, f, tag="ruin"), box(x, y, z, x + 2, y + 8, z + 4, f, tag="ruin"),
            box(x + 6, y + 2, z, x + 8, y + 4, z + 3, f, tag="ruin"),
            box(x + 4, y + 6, z, x + 6, y + 8, z + 2, f, tag="ruin")]


def deer(x, y, z=LAND, head_dip=0, mats=("deer", "antler"), legs=0):
    """A deer from lattice boxes, body along x (head at -x). legs=1 is the passing key of the walk (near legs step
    in by one unit)."""
    b, a = mats
    f = {"top": {"m": b, "tone": "top"}, "px": {"m": b, "tone": "lit"}, "py": {"m": b, "tone": "shade"},
         "*": {"m": b}}
    out = [box(x + 1, y, z + 3, x + 7, y + 2, z + 6, f, tag="animal")]            # body
    for lx in ((x + 1, x + 6), (x + 2, x + 5))[legs]:
        out.append(box(lx, y + 1, z, lx + 1, y + 2, z + 3, f, tag="animal"))      # near legs (far legs hidden)
    if head_dip:
        out.append(box(x - 1, y, z + 1, x + 2, y + 2, z + 4, f, tag="animal"))    # head down, grazing
    else:
        out.append(box(x, y, z + 5, x + 2, y + 2, z + 8, f, tag="animal"))        # neck
        out.append(box(x - 2, y, z + 7, x + 1, y + 2, z + 9, f, tag="animal"))    # head
        fa = {"*": {"m": a, "tone": "top"}, "top": {"m": a, "tone": "top"}}
        out.append(box(x, y, z + 9, x + 1, y + 1, z + 11, fa, tag="animal"))      # antler
    out.append(box(x + 7, y, z + 5, x + 8, y + 1, z + 6, {"*": {"m": "tail", "tone": "top"},
                                                           "top": {"m": "tail", "tone": "top"}}, tag="animal"))
    return out


def heron(x, y, z=0, dip=0):
    f = {"top": {"m": "heron", "tone": "top"}, "px": {"m": "heron", "tone": "lit"},
         "py": {"m": "heron", "tone": "shade"}, "*": {"m": "heron"}}
    leg = {"*": {"m": "leg", "tone": "top"}, "top": {"m": "leg", "tone": "top"}}
    beak = {"*": {"m": "beak", "tone": "top"}, "top": {"m": "beak", "tone": "top"}}
    out = [box(x + 2, y, z, x + 3, y + 1, z + 4, leg, tag="animal"),
           box(x + 1, y, z + 4, x + 5, y + 2, z + 7, f, tag="animal")]
    if dip:
        out.append(box(x - 1, y, z + 3, x + 1, y + 1, z + 6, f, tag="animal"))
        out.append(box(x - 2, y, z + 2, x, y + 1, z + 3, beak, tag="animal"))
    else:
        out.append(box(x, y, z + 6, x + 1, y + 1, z + 10, f, tag="animal"))
        out.append(box(x - 2, y, z + 9, x, y + 1, z + 10, beak, tag="animal"))
    return out

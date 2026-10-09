"""Asset builders for the painted-cards kit. Each builder adds geometry to the current collection at the world origin
(origin = the sprite's ground anchor). Runs inside Blender via kit.py."""
import bpy, bmesh, math
import numpy as np
from mathutils import Vector, noise
import painter as P
from painter import rng, toon, clump, cards, tufts, tube, box, poly, blob

ATLAS = lambda: P.FOL.get('atlas', 'leaves')   # the crown card mask; the style can swap it (painted_cards: brush dabs)
LEAF = lambda ramp='leaf': toon(ramp, ATLAS(), var=.1)
GRASS = lambda: toon('grass', 'grass', var=0)


def bark():
    return toon('bark', grain=.12, var=0)


# ------------------------------------------------------------------ trees and plants

def oak(ramp='leaf', seed=3, mix=None):
    """broad deciduous tree: rooted trunk, limbs into ~13 leaf clumps (ramp / mix pick the clump colours)."""
    rng.seed(seed)
    tube('trunk', [(0, 0, -.2), (.1, 0, 1.4), (-.1, .05, 2.6), (.15, 0, 3.4)], [.42, .3, .26, .2], bark())
    for k in range(5):   # root flare
        a = k / 5 * math.tau + rng.uniform(-.3, .3); L = rng.uniform(.7, 1.0)
        tube(f'root{k}', [(math.cos(a) * .15, math.sin(a) * .15, .5), (math.cos(a) * .45, math.sin(a) * .45, .08),
                          (math.cos(a) * L, math.sin(a) * L, -.05)], [.22, .12, .03], bark(), res=4)
    c0, top, cl = Vector((0, 0, 5.0)), Vector((.15, 0, 3.4)), []
    for i in range(13):
        d = Vector((rng.gauss(0, 1), rng.gauss(0, 1) * .8, rng.gauss(0, 1) * .6)).normalized()
        r = rng.uniform(.5, 1)
        c = c0 + Vector((d.x * 2.7 * r, d.y * 2.0 * r, d.z * 1.7 * r)); cl.append(c)
        clump(f'cl{i}', c, rng.uniform(1.3, 1.8), 70, .55, LEAF(mix[i % len(mix)] if mix else ramp))
    for i, c in enumerate(sorted(cl, key=lambda q: (q - top).length)[:6]):   # limbs show through the crown's holes
        tube(f'br{i}', [top, top.lerp(c, .5) + Vector((0, 0, .4)), c], [.16, .1, .03], bark(), res=4)


def maple():
    """the oak's build in autumn colours, fallen leaves around the roots."""
    oak('leaf_autumn', seed=11)
    rng.seed(12)
    tufts('fallen', [(rng.gauss(.4, 1.3), rng.gauss(-.3, .8), 0) for _ in range(30)], toon('leaf_autumn', 'leaves', var=.1),
          size=(.1, .16))


def blossom(seed=29):
    """a cherry in bloom: short dark trunk splitting into spreading limbs, a broad flat crown of blossom clumps
    with gaps where the limbs show, petals lying flat on the grass. Drifting petals are a runtime effect from this crown."""
    rng.seed(seed)
    wood = toon('bark', grain=.12, var=0, shift=-.08)
    fork = Vector((-.05, .05, 1.9))
    tube('trunk', [(0, 0, -.2), (.15, 0, .9), fork], [.36, .28, .22], wood)
    bloom = toon('blossom', ATLAS(), var=.1)
    for k in range(5):
        a = k / 5 * math.tau + rng.uniform(-.35, .35); L = rng.uniform(2.3, 3.1)
        end = Vector((math.cos(a) * L, math.sin(a) * L * .8, rng.uniform(3.2, 4.0)))
        mid = fork.lerp(end, .5) + Vector((0, 0, .5))
        tube(f'limb{k}', [fork, mid, end], [.18, .11, .04], wood, res=5)
        for j, u in enumerate((.55, 1.0)):   # clumps ride the limbs; the space between limbs stays open
            c = fork.lerp(end, u) + Vector((rng.uniform(-.3, .3), rng.uniform(-.3, .3), .55 + .25 * j))
            clump(f'cl{k}{j}', c, rng.uniform(1.05, 1.4), 58, .46, bloom, squash=.72)
    clump('top', fork + Vector((0, 0, 2.5)), 1.3, 60, .46, bloom, squash=.7)
    pts = []
    for _ in range(70):   # fallen petals lie flat, thickest under the crown and drifting downwind (+x)
        x, y = rng.gauss(.6, 1.5), rng.gauss(-.2, 1.1)
        pts.append((Vector((x, y, .02)), Vector((0, 0, 1)), rng.uniform(.06, .09), Vector((0, 0, 1))))
    cards('petals', (0, 0, 0), pts, toon('blossom', 'puffs', var=.1, shift=.15), sway=False)


def poplar(seed=5):
    """tall narrow tree: seven stacked clumps on a thin trunk."""
    rng.seed(seed)
    tube('trunk', [(0, 0, -.2), (0, 0, 2.0), (.05, 0, 5.5)], [.24, .16, .06], bark())
    for i in range(7):
        r = 1.15 * math.sin(math.pi * (0.15 + .8 * i / 6)) + .25
        clump(f'cl{i}', (rng.uniform(-.15, .15), rng.uniform(-.1, .1), 2.4 + i * .8), r, 48, .45, LEAF('poplar'), squash=1.25)


def pine(seed=7):
    """tiers of drooping card rings: top-lit needles over a dark underside, so every tier reads on its own."""
    rng.seed(seed)
    tube('trunk', [(0, 0, -.2), (0, 0, 2.0), (0, 0, 8.6)], [.24, .18, .05], bark())
    mat, under = toon('pine', 'leaves', var=.1), toon('pine', 'leaves', var=.05, shift=-.35)   # needles: full leaf mask
    T = 6
    for i in range(T):
        f = i / (T - 1); z = 1.5 + i * 1.3; r = 2.1 * (1 - f) ** 1.15 + .3
        pts, low = [], []
        for _ in range(int(24 + 30 * r)):
            a = rng.random() * math.tau; u = rng.random() ** .3; rr = r * u
            p = Vector((math.cos(a) * rr, math.sin(a) * rr, -.6 * u ** 1.6 + rng.uniform(-.1, .1)))
            cn = (Vector((math.cos(a) * .4, math.sin(a) * .4, 1)) * .6 - P.FWD).normalized()
            sn = Vector((math.cos(a) * u * .55, math.sin(a) * u * .55, 1.5 - .8 * u ** 2.5)).normalized()
            pts.append((p, cn, .34 * rng.uniform(.8, 1.2), sn))
        for _ in range(int(8 + 10 * r)):   # the shadowed skirt under the tier
            a = rng.random() * math.tau; rr = r * rng.uniform(.5, .95)
            low.append((Vector((math.cos(a) * rr, math.sin(a) * rr, -.75 * (rr / r) ** 1.4 - .15)),
                        (-P.FWD).normalized(), .3, Vector((math.cos(a), math.sin(a), -.4)).normalized()))
        for o in (cards(f'tier{i}', (0, 0, z), pts, mat), cards(f'skirt{i}', (0, 0, z), low, under)):
            o['shades_self'] = 1   # each tier shades the one below: that's what makes a pine read
    clump('tip', (0, 0, 1.5 + T * 1.3 - .35), .3, 12, .26, mat, squash=1.7, up=.8)


def bush(seed=9):
    """four low leaf clumps."""
    rng.seed(seed)
    for i in range(4):
        a = i / 4 * math.tau
        clump(f'cl{i}', (math.cos(a) * .45, math.sin(a) * .3, .55 + rng.random() * .25), rng.uniform(.55, .75), 34, .35, LEAF())


def rock(seed=13):
    """faceted boulder with a moss cap and grass at its foot."""
    rng.seed(seed)
    me = bpy.data.meshes.new('rock'); bm = bmesh.new()
    bmesh.ops.create_icosphere(bm, subdivisions=3, radius=1.0)
    for v in bm.verts:
        v.co *= 1 + .22 * noise.noise(v.co * 1.3 + Vector((seed, 0, 0)))
        v.co.z = max(v.co.z * .62, -.1)
    for f in bm.faces: f.smooth = False
    bm.to_mesh(me); bm.free()
    o = bpy.data.objects.new('rock', me); o.data.materials.append(toon('stone', grain=-.12, var=0)); o.scale = (1.0, .8, .9)
    P.link(o)
    clump('moss', (-.15, .05, .58), .55, 26, .28, toon('moss', ATLAS(), var=.05), squash=.35, up=1.2, sway=False)
    tufts('grass', [(math.cos(a) * 1.05, math.sin(a) * .85, 0) for a in [rng.random() * math.tau for _ in range(18)]],
          GRASS(), size=(.15, .3))


def flowers(seed=15):
    """a patch of grass tufts and pink flowers."""
    rng.seed(seed)
    tufts('grass', [(rng.gauss(0, .55), rng.gauss(0, .4), 0) for _ in range(40)], GRASS(), size=(.15, .3))
    tufts('pink', [(rng.gauss(0, .45), rng.gauss(0, .32), 0) for _ in range(22)], toon('flower_pink', 'flowers', var=.05),
          size=(.13, .22))


# ------------------------------------------------------------------ built things

def fence(axis='x', seed=17):
    """one 4 m run: 3 posts with caps, 2 rails, grass at the posts."""
    rng.seed(seed)
    wood = toon('fence', grain=.1, var=.06)
    dx = Vector((1, 0, 0)) if axis == 'x' else Vector((0, 1, 0))
    rot = 0 if axis == 'x' else math.pi / 2
    for i in range(3):
        p = dx * (i * 2 - 2)
        box(f'post{i}', p + Vector((0, 0, .55)), (.14, .14, 1.1), wood, rot=rot, tilt=(rng.uniform(-.04, .04), rng.uniform(-.05, .05)))
        box(f'cap{i}', p + Vector((0, 0, 1.12)), (.18, .18, .05), wood, rot=rot)
    for h in (.42, .85):
        lean = rng.uniform(-.015, .015)
        box(f'rail{h}', Vector((0, 0, h)), (4.1, .07, .1), wood, rot=rot, tilt=(0, lean) if axis == 'x' else (lean, 0))
    spots = [(p.x + rng.gauss(0, .2), p.y + rng.gauss(0, .2), 0) for i in range(3) for p in [dx * (i * 2 - 2)] for _ in range(6)]
    tufts('grass', spots, GRASS(), size=(.14, .26))


def fence_y():
    """the fence run along y (north-south)."""
    fence('y', 19)


def house(seed=21, roof_ramp='roof'):
    """cottage: plaster and timber frame on a stone plinth, tiled gable roof, chimney, door, windows with flower boxes, ivy."""
    rng.seed(seed)
    W, D, H = 5.6, 4.0, 3.3
    plaster, timber = toon('plaster', grain=-.1, var=0), toon('timber', grain=.08, var=.04)
    stone, roof = toon('stone', grain=-.14, var=0), toon(roof_ramp, rows=.3, var=0)
    glass, door = toon('glass', var=0), toon('door', grain=.08, var=0)
    box('plinth', (0, 0, .2), (W + .14, D + .14, .4), stone)
    box('walls', (0, 0, .4 + H / 2), (W, D, H), plaster, bevel=.05)
    for sx in (-1, 1):
        for sy in (-1, 1):
            box(f'post{sx}{sy}', (sx * W / 2, sy * D / 2, .4 + H / 2), (.2, .2, H), timber)
    for z in (.42, .4 + H * .55, .4 + H):
        for sy in (-1, 1):
            box(f'beam{sy}{z:.1f}', (0, sy * (D / 2 + .02), z), (W + .1, .16, .16), timber)
    for x in (-W / 6, W / 6):
        box(f'stud{x:.1f}', (x, -D / 2 - .02, .4 + H * .27), (.14, .14, H * .55), timber)
    R, o, zh = 1.45, .35, .4 + H
    ridge = zh + R
    for side in (-1, 1):   # roof slopes with painted-mass normals, then a dark eave lip
        y0 = side * (D / 2 + o)
        poly(f'roof{side}', [(-W / 2 - o, y0, zh - .25), (W / 2 + o, y0, zh - .25), (W / 2 + o, 0, ridge), (-W / 2 - o, 0, ridge)],
             [(0, 1, 2, 3)] if side < 0 else [(3, 2, 1, 0)], roof, bulge=(0, 0, zh - 3.0), k=.55)
        poly(f'eave{side}', [(-W / 2 - o, y0, zh - .25), (W / 2 + o, y0, zh - .25), (W / 2 + o, y0, zh - .42), (-W / 2 - o, y0, zh - .42)],
             [(0, 3, 2, 1)] if side < 0 else [(0, 1, 2, 3)], timber)
    for sx in (-1, 1):
        x = sx * W / 2
        poly(f'gable{sx}', [(x, -D / 2, zh), (x, D / 2, zh), (x, 0, ridge - .1)], [(0, 1, 2)] if sx > 0 else [(2, 1, 0)], plaster)
    box('ridge', (0, 0, ridge + .02), (W + 2 * o + .1, .28, .16), toon(roof_ramp, var=0, shift=-.1), bevel=.06)
    brick = toon('chimney', grain=-.12, var=0)
    box('chimney', (W * .28, .55, ridge - .1), (.6, .6, 2.0), brick, bevel=.04)
    box('chimcap', (W * .28, .55, ridge + .95), (.78, .78, .12), toon('chimney', var=0, shift=-.25))
    box('doorframe', (-.2, -D / 2 - .06, 1.4), (1.05, .1, 2.05), timber)
    box('door', (-.2, -D / 2 - .1, 1.36), (.82, .08, 1.9), door, bevel=.02)
    box('step', (-.2, -D / 2 - .4, .12), (1.3, .6, .24), stone)
    fl = []
    for x in (-W * .34, W * .3):
        z = .4 + H * .55
        box(f'wf{x:.1f}', (x, -D / 2 - .05, z), (1.05, .1, 1.0), timber)
        box(f'wg{x:.1f}', (x, -D / 2 - .09, z), (.8, .06, .78), glass, bevel=0)
        box(f'wm{x:.1f}', (x, -D / 2 - .12, z), (.07, .04, .78), timber, bevel=0)
        box(f'wb{x:.1f}', (x, -D / 2 - .25, z - .58), (1.1, .32, .24), timber)
        fl += [(x + rng.uniform(-.48, .48), -D / 2 - .3 + rng.uniform(-.08, .08), z - .46) for _ in range(9)]
    tufts('wflowers', fl, toon('flower_red', 'flowers', var=.05), size=(.12, .18))
    box('swf', (W / 2 + .05, 0, .4 + H * .55), (.1, .9, .9), timber)
    box('swg', (W / 2 + .09, 0, .4 + H * .55), (.06, .66, .66), glass, bevel=0)
    for i in range(4):   # ivy: the leaf painter flattened against the west corner
        clump(f'ivy{i}', (-W / 2 + .1 + rng.uniform(0, .5), -D / 2 - .05, .6 + i * .65), .5 + .1 * (3 - i), 26, .26,
              toon('leaf', ATLAS(), var=.08), sway=False)
    for i, x in enumerate((W * .48, -W * .12)):
        clump(f'shrub{i}', (x, -D / 2 - .45, .45), .5, 26, .3, LEAF(), up=.8, sway=False)
    tufts('grass', [(rng.uniform(-W / 2 - .3, W / 2 + .3), -D / 2 - .2 - rng.random() * .4, 0) for _ in range(40)], GRASS(),
          size=(.14, .26))


def house_b():
    """the cottage with a blue slate roof."""
    house(seed=41, roof_ramp='roof_blue')


def well(seed=23):
    """stone well: two courses of stones, posts, axle, bucket, a small steep roof."""
    rng.seed(seed)
    stone, wood = toon('stone', grain=-.12, var=.05), toon('fence', grain=.1, var=.04)
    for i in range(14):
        for k in range(2):
            a = (i + k * .5) / 14 * math.tau
            box(f's{i}{k}', (math.cos(a) * .85, math.sin(a) * .85, .22 + k * .38), (.42, .28, .36), stone, rot=a + math.pi / 2, bevel=.06)
    poly('water', [(math.cos(a) * .7, math.sin(a) * .7, .55) for a in [i / 16 * math.tau for i in range(16)]], [tuple(range(16))],
         toon('water', var=0, shift=-.3))
    for sx in (-1, 1):
        box(f'pole{sx}', (sx * .95, 0, 1.25), (.12, .12, 2.0), wood)
    box('axle', (0, 0, 1.75), (2.0, .08, .08), wood)
    box('rope', (.1, 0, 1.5), (.03, .03, .5), toon('timber', var=0), bevel=0)
    box('bucket', (.1, 0, 1.12), (.26, .26, .28), wood)
    roof, ridge = toon('roof', rows=.22, var=0), 2.75
    for side in (-1, 1):   # a small steep roof with gable boards, smaller than the ring
        y0 = side * .55
        poly(f'r{side}', [(-1.1, y0, 2.1), (1.1, y0, 2.1), (1.1, 0, ridge), (-1.1, 0, ridge)],
             [(0, 1, 2, 3)] if side < 0 else [(3, 2, 1, 0)], roof, bulge=(0, 0, 1.2), k=.5, cuts=4)
    for sx in (-1, 1):
        poly(f'g{sx}', [(sx * 1.0, -.5, 2.1), (sx * 1.0, .5, 2.1), (sx * 1.0, 0, ridge - .05)], [(0, 1, 2)] if sx > 0 else [(2, 1, 0)], wood)
    box('ridge', (0, 0, ridge + .02), (2.3, .16, .1), toon('roof', var=0, shift=-.1), bevel=.03)
    tufts('grass', [(math.cos(a) * 1.2, math.sin(a) * 1.1, 0) for a in [rng.random() * math.tau for _ in range(22)]], GRASS(),
          size=(.14, .26))


# ------------------------------------------------------------------ the ground plate: painted lane, footpath, pond

def _polyline_fields(px, py, pts, half):
    """distance to the polyline minus half-width (m, negative inside) and |lateral offset| (for ruts)."""
    pts = np.array(pts, float)
    best = np.full(px.shape, 1e9); lat = np.zeros(px.shape)
    for (ax, ay), (bx, by) in zip(pts[:-1], pts[1:]):
        dx, dy = bx - ax, by - ay; L2 = dx * dx + dy * dy
        t = np.clip(((px - ax) * dx + (py - ay) * dy) / L2, 0, 1)
        qx, qy = ax + t * dx - px, ay + t * dy - py
        d = np.hypot(qx, qy)
        sel = d < best
        best = np.where(sel, d, best); lat = np.where(sel, d, lat)
    return best - half, lat


def ground_fields(px, py):
    lay = P.LAYOUT
    lane_d, lane_lat = _polyline_fields(px, py, lay['lane']['points'], lay['lane']['width'] / 2)
    foot_d = np.full(px.shape, 1e9)
    for fp in lay['footpaths']:
        foot_d = np.minimum(foot_d, _polyline_fields(px, py, fp['points'], fp['width'] / 2)[0])
    path_d = np.minimum(lane_d, foot_d)
    rut_d = np.where(lane_d < foot_d, np.abs(lane_lat - lay['lane']['ruts']), 9.0)
    pc, rx, ry = lay['pond']['centre'], lay['pond']['rx'], lay['pond']['ry']
    a = np.arctan2(py - pc[1], px - pc[0])
    rn = np.hypot((px - pc[0]) / rx, (py - pc[1]) / ry) / (1 + .07 * np.sin(2 * a + .5) + .05 * np.cos(3 * a + 1))
    pond_d = (rn - 1) * (rx + ry) / 2
    bank = ((pond_d > -.7) & (py - pc[1] > .15 * ry)).astype(float)   # the far bank shades the water below it
    return path_d, rut_d, pond_d, bank


def ground_material():
    """one painted surface: turf with broad light patches, a trampled verge, dirt with worn ruts and a darker edge,
    a wet shore over a pale sand rim, water banded by depth with sky streaks and glints (the glint layer is animated)."""
    m, g, out = P.new_material('ground_painted')
    wob, _ = g.noise(1.1, lo=-.3, hi=.3)
    patch, _ = g.noise(.05, lo=-.13, hi=.13, detail=0.5)
    grain, _ = g.noise(3.0, .6, .6, .6, lo=-.05, hi=.05)
    pd = g.math('ADD', g.attr('path_d'), wob)
    od = g.math('ADD', g.attr('pond_d'), g.math('MULTIPLY', wob, .6))
    rd = g.math('ADD', g.attr('rut_d'), g.math('MULTIPLY', wob, .07))
    # the ground takes no cast shadows (sprites carry theirs), so it is painted from designed tones, not from light:
    # one mid tone per material, broad darker/lighter patches, small dabs, and edge bands from the distance fields
    gt = lambda name, v: g.ramp(name, v)
    patch = g.math('ADD', patch, g.math('MULTIPLY', wob, .12))
    turf = g.mix(g.math('GREATER_THAN', patch, .07), gt('turf', .55), gt('turf', .2))
    turf = g.mix(g.math('LESS_THAN', patch, -.08), turf, gt('turf', .85))
    verge = g.mix(g.math('GREATER_THAN', grain, .03), gt('verge', .7), gt('verge', .45))
    dirt = g.mix(g.math('GREATER_THAN', grain, .035), gt('dirt', .75), gt('dirt', .5))
    dirt = g.mix(g.math('GREATER_THAN', pd, -.25), dirt, gt('dirt', .45))
    dirt = g.mix(g.math('LESS_THAN', rd, .1), dirt, gt('rut', .5))
    sand, mud = gt('sand', .75), g.mix(g.math('GREATER_THAN', grain, .03), gt('mud', .5), gt('mud', .2))
    # water: few flat tones, calm. one mid body, a light shallow ring, a darker deep pool, the far bank's shade,
    # a few broad sky reflections, sparse glints only inside them (the glint layer is the animated part), a pale edge line
    depth = g.math('MULTIPLY', od, -1.0)
    refl, _ = g.noise(.55, .14, 1.0, 1.0, lo=0, hi=1, detail=0.3)
    refl = g.math('GREATER_THAN', g.math('ADD', refl, g.math('MULTIPLY', wob, .15)), .6)
    glint, P.GLINT_MAP = g.noise(3.2, .35, 4.0, 1.0, lo=0, hi=1, detail=0.2)
    lvl = g.math('ADD', .55, g.math('MULTIPLY', g.math('LESS_THAN', depth, .4), .23))
    lvl = g.math('ADD', lvl, g.math('MULTIPLY', g.math('GREATER_THAN', depth, 1.35), -.25))
    lvl = g.math('ADD', lvl, g.math('MULTIPLY', g.math('MULTIPLY', refl, g.math('GREATER_THAN', depth, .4)), .23))
    lvl = g.math('ADD', lvl, g.math('MULTIPLY', g.attr('bank'), -.24))
    lvl = g.math('ADD', lvl, g.math('MULTIPLY', g.math('MULTIPLY', refl, g.math('GREATER_THAN', glint, .9)), .4))
    lvl = g.math('MAXIMUM', lvl, g.math('MULTIPLY', g.math('LESS_THAN', depth, .1), .95))
    water = g.ramp('water_depth', lvl)
    col = g.mix(g.math('LESS_THAN', pd, .45), turf, verge)
    col = g.mix(g.math('LESS_THAN', pd, 0), col, dirt)
    col = g.mix(g.math('LESS_THAN', od, .42), col, sand)
    col = g.mix(g.math('LESS_THAN', od, .26), col, mud)
    col = g.mix(g.math('LESS_THAN', od, 0), col, water)
    g.emit(col, out)
    m.surface_render_method = 'DITHERED'
    return m


def ground():
    lay = P.LAYOUT; rng.seed(31)
    pl = lay['plate']
    x0, x1 = pl['x'][0] - 3, pl['x'][1] + 3
    y0, y1 = -7, pl['v'][1] / math.sin(P.E) + 4
    nx, ny = int((x1 - x0) / .2), int((y1 - y0) / .2)
    xs, ys = np.meshgrid(np.linspace(x0, x1, nx + 1), np.linspace(y0, y1, ny + 1))
    px, py = xs.ravel(), ys.ravel()
    path_d, rut_d, pond_d, bank = ground_fields(px, py)
    hz = np.array([.15 * noise.noise(Vector((x * .15, y * .15, 0))) for x, y in zip(px, py)])
    pz = np.where(pond_d < 0, -.06, hz)
    me = bpy.data.meshes.new('turf')
    verts = np.stack([px, py, pz], 1)
    idx = np.arange((nx + 1) * (ny + 1)).reshape(ny + 1, nx + 1)
    quads = np.stack([idx[:-1, :-1], idx[:-1, 1:], idx[1:, 1:], idx[1:, :-1]], -1).reshape(-1, 4)
    me.from_pydata(verts.tolist(), [], quads.tolist()); me.update()
    for name, arr in (('path_d', path_d), ('rut_d', rut_d), ('pond_d', pond_d), ('bank', bank)):
        me.attributes.new(name, 'FLOAT', 'POINT').data.foreach_set('value', arr.astype(np.float32))
    for p in me.polygons: p.use_smooth = True
    o = bpy.data.objects.new('turf', me); o.data.materials.append(ground_material()); P.link(o)

    def field(x, y):
        a, b, c, _ = ground_fields(np.array([x]), np.array([y]))
        return a[0], c[0]

    def z(x, y):
        return .15 * noise.noise(Vector((x * .15, y * .15, 0)))

    turf_t, verge_t, pebbles, reeds, shore, lilies = [], [], [], [], [], []
    for _ in range(int(2.8 * (x1 - x0) * (y1 - y0))):
        x, y = rng.uniform(x0 + 1, x1 - 1), rng.uniform(y0 + 1, y1 - 1)
        pd, od = field(x, y)
        if od < .7 or pd < .12:
            if pd < -.2 and rng.random() < .05: pebbles.append((x, y, z(x, y) + .04))
            continue
        if pd < .8:
            verge_t.append((x, y, z(x, y)))
        elif noise.noise(Vector((x * .2, y * .2, 4))) > -.1 and rng.random() < .3:
            turf_t.append((x, y, z(x, y)))
    pc, rx, ry = lay['pond']['centre'], lay['pond']['rx'], lay['pond']['ry']
    for _ in range(4000):
        a = rng.uniform(0, math.tau); s = rng.uniform(.7, 1.25)
        x, y = pc[0] + math.cos(a) * rx * s, pc[1] + math.sin(a) * ry * s
        pd, od = field(x, y)
        if -.1 < od < .3 and math.sin(a) > .35 and math.cos(a) < .3 and len(reeds) < 70:
            reeds.append((x, y, -.02))
        elif .2 < od < .45 and rng.random() < .03:
            shore.append((x, y))
        elif od < -.6 and rng.random() < .012 and len(lilies) < 16:
            lilies.append((x, y))
    tufts('turf_tufts', turf_t, GRASS(), size=(.14, .3))
    tufts('verge_tufts', verge_t, GRASS(), size=(.16, .34))
    tufts('reeds', reeds, toon('reed', 'grass', var=0), size=(.3, .55))
    stone = toon('stone', var=.1)
    for i, (x, y, zz) in enumerate(pebbles):
        box(f'pebble{i}', (x, y, zz), (rng.uniform(.12, .26), rng.uniform(.1, .18), .06), stone, rot=rng.random() * 3, bevel=.03)
    for i, (x, y) in enumerate(shore):
        box(f'shore{i}', (x, y, .02), (rng.uniform(.25, .5), rng.uniform(.2, .35), .14), stone, rot=rng.random() * 3, bevel=.06)
    pad, bloom = toon('lily', 'puffs', var=.06), toon('flower_pink', 'flowers', var=.05)
    for i, (x, y) in enumerate(lilies):
        clump(f'lily{i}', (x, y, -.03), .3, 4, .2, pad, squash=.04, up=3, sway=False)
        if i % 3 == 0:
            tufts(f'bloom{i}', [(x + .05, y, -.02)], bloom, size=(.1, .12))
    # a small plank jetty on the south-west shore: two stringers, planks across them, posts at the ends
    wood = toon('fence', grain=.1, var=.05)
    th = .55; u = Vector((math.cos(th), math.sin(th), 0)); n = Vector((-u.y, u.x, 0))
    j0 = Vector((pc[0] - rx * .66, pc[1] - ry * .8, 0))
    for s in (-1, 1):
        box(f'stringer{s}', j0 + u * 1.0 + n * s * .38 + Vector((0, 0, .06)), (2.1, .08, .08), wood, rot=th, bevel=.01)
    for k in range(7):
        box(f'plank{k}', j0 + u * (k * .3 + .1) + Vector((0, 0, .12)), (.24, 1.0, .05), wood, rot=th, bevel=.015)
    for k in (0, 1):
        for s in (-1, 1):
            box(f'jpost{k}{s}', j0 + u * (k * 1.9 + .1) + n * s * .45 + Vector((0, 0, .1)), (.1, .1, .4), wood)


# ------------------------------------------------------------------ the animal: a mallard drake and his ducklings

def duck(kind='drake'):
    """built around a 'root' empty so it can be turned to 8 headings and bob; ripple rings are separate objects."""
    root = bpy.data.objects.new('root', None); P.link(root)
    parts = []

    def part(name, c, r, ramp, cut=True, shift=0.0):
        o = blob(name, c, r, toon(ramp, var=0, shift=shift), cut_below=0.0 if cut else None, seg=20)
        o.parent = root; parts.append(o)
        return o

    if kind == 'drake':
        part('body', (0, 0, .06), (.25, .13, .11), 'duck_body')
        part('chest', (.12, 0, .075), (.13, .115, .1), 'duck_chest')
        part('rear', (-.19, 0, .08), (.1, .09, .085), 'duck_dark')
        part('tail', (-.28, 0, .12), (.05, .035, .03), 'duck_dark', cut=False)
        for s in (-1, 1):
            part(f'wing{s}', (-.04, s * .07, .125), (.17, .06, .05), 'duck_wing', cut=False)
        part('neck', (.17, 0, .17), (.05, .05, .075), 'duck_head', cut=False)
        part('collar', (.17, 0, .135), (.056, .056, .014), 'duck_white', cut=False)
        head = part('head', (.205, 0, .24), (.075, .06, .065), 'duck_head', cut=False)
        bill = part('bill', (.29, 0, .222), (.052, .026, .016), 'duck_bill', cut=False)
        ring_r = .34
    else:
        part('body', (0, 0, .045), (.1, .07, .065), 'duckling')
        head = part('head', (.075, 0, .11), (.05, .045, .045), 'duckling', cut=False)
        bill = part('bill', (.125, 0, .1), (.025, .014, .01), 'duck_bill', cut=False, shift=-.2)
        ring_r = .15
    for o in (head, bill):
        o['nod'] = 1
    ripple = toon('ripple', var=0)
    rings = []
    for k in range(2):
        me = bpy.data.meshes.new(f'ring{k}'); bm = bmesh.new()
        n = 28; outer = [bm.verts.new((math.cos(a) * 1.0, math.sin(a) * .8, 0)) for a in [i / n * math.tau for i in range(n)]]
        inner = [bm.verts.new((math.cos(a) * .94, math.sin(a) * .75, 0)) for a in [i / n * math.tau for i in range(n)]]
        for i in range(n):
            bm.faces.new((outer[i], outer[(i + 1) % n], inner[(i + 1) % n], inner[i]))
        bm.to_mesh(me); bm.free()
        r = bpy.data.objects.new(f'ring{k}', me); r.data.materials.append(ripple); r.location = (0, 0, .004)
        r.scale = (ring_r,) * 3; P.link(r); rings.append(r)
    return root, rings, ring_r


def drake():
    """mallard drake on water (green head, chestnut chest), 8 headings x 8 paddle frames, ripple rings."""
    return duck('drake')


def duckling():
    """a duckling that follows the drake."""
    return duck('duckling')

# ------------------------------------------------------------------ the hero: a wanderer in a navy cape

def _empty(name, parent, loc):
    e = bpy.data.objects.new(name, None); e.parent = parent; e.location = loc; P.link(e)
    return e


def _limb(name, parent, length, radius, ramp, end_radius=None):
    """a tube hanging down from its pivot (local -z), parented to the pivot."""
    o = tube(name, [(0, 0, 0), (0, 0, -length / 2), (0, 0, -length)], [radius, radius * .95, end_radius or radius * .85],
             toon(ramp, var=0), res=4)
    o.parent = parent
    return o


def hero():
    """the wanderer: an original painted human in a navy cape and mustard scarf, walk + idle, 8 headings.
    Faces +x. Returns the rig: root (yaw), pelvis (bob/lean), hips/knees, shoulders/elbows, neck, cape mesh + rest coords."""
    root = bpy.data.objects.new('root', None); P.link(root)
    pelvis = _empty('pelvis', root, (0, 0, .8))

    def part(name, parent, c, r, ramp, shift=0.0):
        o = blob(name, c, r, toon(ramp, var=0, shift=shift), seg=20); o.parent = parent
        return o

    part('hips', pelvis, (0, 0, .0), (.11, .15, .1), 'trousers')
    part('torso', pelvis, (0, 0, .25), (.12, .16, .22), 'tunic')
    part('belt', pelvis, (0, 0, .07), (.128, .166, .03), 'leather')
    part('satchel', pelvis, (-.02, .19, .02), (.08, .045, .085), 'leather')
    part('strap', pelvis, (.0, .0, .3), (.13, .17, .02), 'leather', shift=-.1)
    part('scarf', pelvis, (.02, 0, .47), (.1, .12, .055), 'scarf')
    part('scarf_tail', pelvis, (-.1, -.06, .38), (.035, .03, .1), 'scarf')
    neck = _empty('neck', pelvis, (0, 0, .5))
    part('head', neck, (.01, 0, .14), (.108, .102, .118), 'skin')
    part('hair', neck, (-.03, 0, .18), (.12, .114, .105), 'hair')
    part('fringe', neck, (.055, 0, .225), (.068, .095, .045), 'hair')
    for s in (-1, 1):
        part(f'eye{s}', neck, (.105, s * .042, .135), (.014, .014, .02), 'eye')
    rig = dict(root=root, pelvis=pelvis, neck=neck, hips=[], knees=[], boots=[], shoulders=[], elbows=[])
    for s in (-1, 1):   # legs: s = -1 right, +1 left
        hip = _empty(f'hip{s}', pelvis, (0, s * .085, -.02))
        _limb(f'thigh{s}', hip, .38, .078, 'trousers')
        knee = _empty(f'knee{s}', hip, (0, 0, -.38))
        _limb(f'shin{s}', knee, .35, .066, 'trousers', .058)
        boot = part(f'boot{s}', knee, (.04, 0, -.37), (.095, .062, .06), 'boot')
        rig['hips'].append(hip); rig['knees'].append(knee); rig['boots'].append(boot)
    for s in (-1, 1):   # arms
        sh = _empty(f'shoulder{s}', pelvis, (0, s * .175, .41))
        _limb(f'upper{s}', sh, .26, .058, 'tunic')
        el = _empty(f'elbow{s}', sh, (0, 0, -.26))
        _limb(f'fore{s}', el, .22, .052, 'tunic')
        part(f'hand{s}', el, (0, 0, -.25), (.052, .046, .056), 'skin')
        rig['shoulders'].append(sh); rig['elbows'].append(el)
    # cape: the back 220 degrees of a flared cylinder from the shoulders to the knees
    rows, cols = 7, 18
    vs, fs = [], []
    for i in range(rows):
        f = i / (rows - 1); z = .45 - .9 * f; r = .175 + .15 * f ** .8
        for j in range(cols):
            a = math.radians(70 + 220 * j / (cols - 1))
            vs.append((math.cos(a) * r * .9, math.sin(a) * r, z))
    for i in range(rows - 1):
        for j in range(cols - 1):
            fs.append((i * cols + j, i * cols + j + 1, (i + 1) * cols + j + 1, (i + 1) * cols + j))
    me = bpy.data.meshes.new('cape'); me.from_pydata(vs, [], fs); me.update()
    for p in me.polygons: p.use_smooth = True
    cape = bpy.data.objects.new('cape', me); cape.data.materials.append(toon('cape', var=0)); cape.parent = pelvis; P.link(cape)
    sol = cape.modifiers.new('sol', 'SOLIDIFY'); sol.thickness = .02
    rig.update(cape=cape, cape_rest=[Vector(v) for v in vs], cape_rows=rows, cape_cols=cols)
    return rig


CHARACTERS = dict(hero=hero)


TREES = dict(oak=oak, maple=maple, blossom=blossom, poplar=poplar, pine=pine, bush=bush)
STATIC = dict(rock=rock, flowers=flowers, fence_x=fence, fence_y=fence_y, house=house, house_b=house_b, well=well)
ANIMALS = dict(drake=drake, duckling=duckling)

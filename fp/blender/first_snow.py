"""First Snow built in Blender with the painted-cards technique, rendered as DATA layers for fp/paint3d.py.

Run by `python3 -m fp paint` (blender -b -P this.py -- WORK SAMPLES [only], or a python with the bpy module).
Reads WORK/scene3d.json, WORK/terrain.npz and WORK/road.npz (the place in metres: fp/place.py, via paint3d.export) and
WORK/tex/*.png (the card atlases); writes WORK/raw/{sky,trees,hill}.png, 16-bit RGBA: R = lit value, G = material
id / 64, B = depth / 160.

The technique (after the painted engine, painted/bpy/painter.py; nothing imported from it):
- cards: needles, the snow on the boughs and the clouds are alpha-masked planes facing the camera, like dabs
- sphere normals: every card of a clump carries its clump's normal (clouds also lean toward their tower's), so a
  clump shades as one soft mass, not as many planes
- the value step: per tree, cards that other cards bury go darker (the AO pockets between tiers) and a gradient runs
  across the crown along the sun
- diffuse -> Shader to RGB -> value: the stepped ramp is applied after the render, per material, in paint3d.py
- real cast shadows from one low sun behind-left: the spruces on the plateau snow, posts, pillows and the car
Axes: fp's (x right, y up, z into the picture) are Blender's (X, Z, Y). The near-field lens of place.py is a vertex
warp, so a plain pinhole camera draws exactly what place.proj() draws.
"""
import bpy, bmesh, sys, json, math, random
from pathlib import Path
import numpy as np
from mathutils import Vector, Matrix

argv = sys.argv[sys.argv.index('--') + 1:] if '--' in sys.argv else sys.argv[1:]
WORK = Path(argv[0])
SAMPLES = int(argv[1]) if len(argv) > 1 else 1
ONLY = argv[2].split(',') if len(argv) > 2 and argv[2] else ['sky', 'trees', 'hill']
S = json.load(open(WORK / 'scene3d.json'))
MAT = S['MAT']
W, H, F, ZB, CAMH, X0, Y0, SS = S['W'], S['H'], S['F'], S['ZB'], S['CAMH'], S['X0'], S['Y0'], S['SS']
CORE_X = S['CORE_X']                             # the sky below is designed in the composed core's columns
LZS, LZB, LA, LB = S['LENS']
LX, LY_, LZ = S['LIGHT']
SUN = Vector((LX, LZ, LY_)).normalized()        # toward the sun, Blender axes
CAMP = Vector((0, -ZB, CAMH))
rng = random.Random(5)

bpy.ops.wm.read_factory_settings(use_empty=True)
sc = bpy.context.scene
LAYER = {}                                       # object name -> layer


def B(x, y, z):
    return Vector((x, z, y))


def smooth(a, b, x):
    t = min(max((x - a) / (b - a), 0.0), 1.0)
    return t * t * (3 - 2 * t)


def warp(v):
    """the near-field lens of place.py as a vertex warp (Blender coords in, out)"""
    w = smooth(LZS, LZB, v.y)
    s = 1 + LA * w
    return Vector((v.x * s, v.y, v.z * s - (v.y + ZB) * LB * w / F))


# ------------------------------------------------------------------ the data shader
MATS = {}


def dmat(mid, alpha=None, kind='lit', lc=None):
    """emission of (lit value, material id, depth). kind 'lit': diffuse under the sun and the sky fill (shadows and
    all), through Shader to RGB. kind 'cloud': the clump normals against a light of its own (no shadows). kind
    'flat': a constant value (lamps). `val` (a per-card attribute) adds the buried/crown value."""
    key = (mid, alpha, kind)
    if key in MATS:
        return MATS[key]
    m = bpy.data.materials.new(f'm{mid}_{alpha}_{kind}')
    m.use_nodes = True
    N, L = m.node_tree.nodes, m.node_tree.links
    N.clear()
    out = N.new('ShaderNodeOutputMaterial')

    def math_(op, a, b):
        n = N.new('ShaderNodeMath'); n.operation = op
        for i, v in enumerate((a, b)):
            if hasattr(v, 'links'):
                L.new(v, n.inputs[i])
            else:
                n.inputs[i].default_value = v
        return n.outputs[0]

    if kind == 'lit':
        d = N.new('ShaderNodeBsdfDiffuse'); d.inputs['Color'].default_value = (1, 1, 1, 1)
        s2r = N.new('ShaderNodeShaderToRGB'); L.new(d.outputs[0], s2r.inputs[0])
        bw = N.new('ShaderNodeRGBToBW'); L.new(s2r.outputs[0], bw.inputs[0])
        lit = bw.outputs[0]
    elif kind == 'cloud':
        # per pixel: the sphere normal of the card's clump as seen from the camera (attributes cc = clump centre,
        # cs = clump radii (x, -, z)), blended with the whole cloud's (ec, es) by `mass` (cm), and turned down under
        # the cloud's flat base (cb = the base's height, cbw = its blend width): one soft mass per clump, the bands
        # round and crossing the cards
        g = N.new('ShaderNodeNewGeometry')

        def attr(nm):
            a_ = N.new('ShaderNodeAttribute'); a_.attribute_name = nm; a_.attribute_type = 'GEOMETRY'
            return a_

        def vm(op, a, b=None):
            n_ = N.new('ShaderNodeVectorMath'); n_.operation = op
            for i, v in enumerate((a, b)):
                if v is None:
                    continue
                if hasattr(v, 'links'):
                    L.new(v, n_.inputs[i])
                else:
                    n_.inputs[i].default_value = v
            return n_

        def sphere(cn, sn):
            off = vm('SUBTRACT', g.outputs['Position'], attr(cn).outputs['Vector']).outputs[0]
            u = vm('DIVIDE', off, attr(sn).outputs['Vector']).outputs[0]
            sep = N.new('ShaderNodeSeparateXYZ'); L.new(u, sep.inputs[0])
            t2 = math_('ADD', math_('MULTIPLY', sep.outputs['X'], sep.outputs['X']), math_('MULTIPLY', sep.outputs['Z'], sep.outputs['Z']))
            k = math_('DIVIDE', math_('SQRT', math_('MINIMUM', t2, 0.94), 0.0), math_('MAXIMUM', math_('SQRT', t2, 0.0), 1e-4))
            ny = math_('MULTIPLY', math_('SQRT', math_('SUBTRACT', 1.0, math_('MINIMUM', t2, 0.94)), 0.0), -1.0)
            cmb = N.new('ShaderNodeCombineXYZ')
            L.new(math_('MULTIPLY', sep.outputs['X'], k), cmb.inputs[0]); L.new(ny, cmb.inputs[1])
            L.new(math_('MULTIPLY', sep.outputs['Z'], k), cmb.inputs[2])
            return cmb.outputs[0]
        n1, n2 = sphere('cc', 'cs'), sphere('ec', 'es')
        mass = attr('cm').outputs['Fac']
        nb = vm('ADD', vm('SCALE', n1, None).outputs[0], vm('SCALE', n2, None).outputs[0])
        s1, s2 = nb.inputs[0].links[0].from_node, nb.inputs[1].links[0].from_node
        L.new(math_('SUBTRACT', 1.0, mass), s1.inputs['Scale']); L.new(mass, s2.inputs['Scale'])
        sepp = N.new('ShaderNodeSeparateXYZ'); L.new(g.outputs['Position'], sepp.inputs[0])
        bw = math_('MINIMUM', math_('MAXIMUM', math_('DIVIDE', math_('SUBTRACT', attr('cb').outputs['Fac'], sepp.outputs['Z']),
                                                                  attr('cbw').outputs['Fac']), 0.0), 1.0)
        down = vm('SCALE', (0.0, -0.45, -1.0)); L.new(bw, down.inputs['Scale'])
        nn = vm('ADD', vm('SCALE', nb.outputs[0]).outputs[0], down.outputs[0])
        L.new(math_('SUBTRACT', 1.0, bw), nn.inputs[0].links[0].from_node.inputs['Scale'])
        nrm = vm('NORMALIZE', nn.outputs[0])
        dp = vm('DOT_PRODUCT', nrm.outputs[0], lc)
        lit = math_('ADD', math_('MULTIPLY', dp.outputs['Value'], 0.5), 0.5)
    elif kind == 'card':
        # a tree's cards: the clump normals against the sun with the sky fill, but no self-shadow (the sun is behind
        # the band, so real shadows would turn every tree into a silhouette); they still cast onto the snow
        g = N.new('ShaderNodeNewGeometry')
        dp = N.new('ShaderNodeVectorMath'); dp.operation = 'DOT_PRODUCT'
        L.new(g.outputs['Normal'], dp.inputs[0]); dp.inputs[1].default_value = tuple(SUN)
        lit = math_('ADD', math_('MAXIMUM', dp.outputs['Value'], 0.0), 0.28)
    else:
        lit = math_('ADD', 0.0, 1.0)
    at = N.new('ShaderNodeAttribute'); at.attribute_name = 'val'; at.attribute_type = 'GEOMETRY'
    lit = math_('ADD', lit, at.outputs['Fac'])
    r = math_('MINIMUM', math_('MAXIMUM', math_('ADD', math_('MULTIPLY', lit, 0.4), 0.2), 0.0), 1.0)
    g = N.new('ShaderNodeNewGeometry')
    sep = N.new('ShaderNodeSeparateXYZ'); L.new(g.outputs['Position'], sep.inputs[0])
    dep = math_('DIVIDE', sep.outputs['Y'], 160.0)
    comb = N.new('ShaderNodeCombineRGB')
    L.new(r, comb.inputs[0]); comb.inputs[1].default_value = mid / 64.0; L.new(dep, comb.inputs[2])
    em = N.new('ShaderNodeEmission'); L.new(comb.outputs[0], em.inputs[0])
    sh = em.outputs[0]
    if alpha:
        img = bpy.data.images.get(alpha + '.png') or bpy.data.images.load(str(WORK / 'tex' / f'{alpha}.png'))
        img.colorspace_settings.name = 'Non-Color'
        tx = N.new('ShaderNodeTexImage'); tx.image = img; tx.interpolation = 'Closest'
        gt = math_('GREATER_THAN', tx.outputs['Color'], 0.5)
        tr = N.new('ShaderNodeBsdfTransparent'); mx = N.new('ShaderNodeMixShader')
        L.new(gt, mx.inputs[0]); L.new(tr.outputs[0], mx.inputs[1]); L.new(sh, mx.inputs[2]); sh = mx.outputs[0]
    L.new(sh, out.inputs[0])
    m.surface_render_method = 'DITHERED'
    try:
        m.use_transparent_shadow = True
    except Exception:
        pass
    MATS[key] = m
    return m


# ------------------------------------------------------------------ geometry helpers
def obj(name, me, mat, layer, lens=True, mats=None):
    if lens:
        for v in me.vertices:
            v.co = warp(v.co)
    o = bpy.data.objects.new(name, me)
    for mm in (mats or [mat]):
        o.data.materials.append(mm)
    sc.collection.objects.link(o)
    LAYER[o.name] = layer
    return o


def mesh_from(name, verts, faces, smooth_=True):
    me = bpy.data.meshes.new(name)
    me.from_pydata([tuple(v) for v in verts], [], faces)
    me.update()
    for p in me.polygons:
        p.use_smooth = smooth_
    return me


def blob(name, c, rx, ry, rz, mat, layer, seg=16, lift=0.0):
    """a smooth ellipsoid (Blender radii), its bottom buried"""
    bm = bmesh.new()
    bmesh.ops.create_uvsphere(bm, u_segments=seg, v_segments=seg // 2, radius=1.0)
    for v in bm.verts:
        v.co = Vector((c.x + v.co.x * rx, c.y + v.co.y * ry, c.z + v.co.z * rz + lift))
    me = bpy.data.meshes.new(name); bm.to_mesh(me); bm.free()
    for p in me.polygons:
        p.use_smooth = True
    return obj(name, me, mat, layer)


def box(name, corners_fn, mat, layer, bevel=0.0, seg=2):
    """a box from a local->world function over the unit cube [0,1]^3, bevelled"""
    bm = bmesh.new()
    bmesh.ops.create_cube(bm, size=1.0)
    for v in bm.verts:
        v.co = corners_fn(v.co + Vector((.5, .5, .5)))
    if bevel:
        bmesh.ops.bevel(bm, geom=bm.edges[:] + bm.verts[:], offset=bevel, segments=seg, affect='EDGES', clamp_overlap=True)
    me = bpy.data.meshes.new(name); bm.to_mesh(me); bm.free()
    for p in me.polygons:
        p.use_smooth = bool(bevel)
    return obj(name, me, mat, layer)


def cards(name, items, mat, layer, val=None, attrs=None):
    """items = [(centre, half_size, shading_normal)], every card square to the camera (a dab on the canvas). The
    near-field lens moves and grows each card as it warps the meshes around it."""
    me = bpy.data.meshes.new(name); bm = bmesh.new(); uvl = bm.loops.layers.uv.new(); nrm = []
    for p, s, sn in items:
        s *= 1 + LA * smooth(LZS, LZB, p.y)
        p = warp(p)
        f = (CAMP - p).normalized()
        q = f.to_track_quat('Z', 'Y') @ Matrix.Rotation(rng.random() * math.tau, 4, 'Z').to_quaternion()
        corners = [p + q @ Vector((x * s, y * s, 0)) for x, y in ((-1, -1), (1, -1), (1, 1), (-1, 1))]
        face = bm.faces.new([bm.verts.new(c) for c in corners])
        t = rng.randrange(4); u0, v0 = (t % 2) * .5, (t // 2) * .5
        for lp, (u, v) in zip(face.loops, ((0, 0), (1, 0), (1, 1), (0, 1))):
            lp[uvl].uv = (u0 + u * .5, v0 + v * .5)
        # a callable normal is evaluated per corner (a sphere normal across the card, so the bands cross the cards)
        nrm += [tuple(sn(c)) for c in corners] if callable(sn) else [sn] * 4
    bm.to_mesh(me); bm.free()
    me.normals_split_custom_set(nrm)
    if val is not None:
        me.attributes.new('val', 'FLOAT', 'POINT').data.foreach_set('value', np.repeat(np.asarray(val, np.float32), 4))
    for an, av in (attrs or {}).items():           # per-card data the shader reads (a cloud clump's centre and size)
        av = np.repeat(np.asarray(av, np.float32), 4, axis=0)
        if av.ndim == 1:
            me.attributes.new(an, 'FLOAT', 'POINT').data.foreach_set('value', av)
        else:
            me.attributes.new(an, 'FLOAT_VECTOR', 'POINT').data.foreach_set('vector', av.ravel())
    o = bpy.data.objects.new(name, me); o.data.materials.append(mat)
    sc.collection.objects.link(o); LAYER[o.name] = layer
    return o


def card_values(pos, nrm, reach, gradient, value, count):
    """the tutorial's value step over one asset: buried (cards lying outward of a card) darkens, crown (place along the
    sun across the asset) lightens the sun side"""
    pos, nrm = np.asarray(pos), np.asarray(nrm)
    d = pos[None, :, :] - pos[:, None, :]
    r = np.linalg.norm(d, axis=2) + 1e-6
    out = np.einsum('ijk,ik->ij', d, nrm) / r
    buried = ((r < reach) & (out > .35)).sum(1)
    buried = 1 - np.exp(-buried / count)
    along = (pos - pos.mean(0)) @ np.array(tuple(SUN))
    crown = along / max(1e-6, np.abs(along).max())
    return gradient * crown - value * buried


# ------------------------------------------------------------------ terrain
T = np.load(WORK / 'terrain.npz')
TX, TY, TZ = T['x'], T['y'], T['z']


def terrain_obj(name, r0, r1, layer):
    xs, ys, zs = TX[r0:r1], TY[r0:r1], TZ[r0:r1]
    nr, nc = xs.shape
    verts = [B(float(xs[i, j]), float(ys[i, j]), float(zs[i, j])) for i in range(nr) for j in range(nc)]
    faces = [(i * nc + j, i * nc + j + 1, (i + 1) * nc + j + 1, (i + 1) * nc + j) for i in range(nr - 1) for j in range(nc - 1)]
    o = obj(name, mesh_from(name, verts, faces), dmat(MAT['snow']), layer)
    # calm normals: the grid's normals blurred over a few cells, so the snow shades as big soft forms (the drift, the
    # rolling slope) and small bumps don't band
    me = o.data
    P = np.array([v.co[:] for v in me.vertices]).reshape(nr, nc, 3)
    du_ = np.gradient(P, axis=1); dv_ = np.gradient(P, axis=0)
    nn = np.cross(du_, dv_); nn /= np.linalg.norm(nn, axis=2, keepdims=True) + 1e-9
    nn *= np.sign(nn[..., 2:3] + 1e-9)
    for _ in range(4):
        q = np.pad(nn, ((1, 1), (1, 1), (0, 0)), mode='edge')
        nn = (q[:-2, 1:-1] + q[2:, 1:-1] + q[1:-1, :-2] + q[1:-1, 2:] + 2 * q[1:-1, 1:-1]) / 6
        nn /= np.linalg.norm(nn, axis=2, keepdims=True)
    flat = nn.reshape(-1, 3)
    me.normals_split_custom_set_from_vertices([tuple(v) for v in flat])
    return o


cut = int(np.searchsorted(TZ[:, 0], S['HILL_CUT']))
terrain_obj('snow_near', 0, cut + 1, 'hill')
terrain_obj('snow_far', cut, len(TZ), 'trees')

# ------------------------------------------------------------------ the road: a strip of quads laid on the snow
# its parts (place.road_label: lane, ruts, plough ridges, the trodden shoulder) are materials of their own, its normals
# the strip's own, a little blurred, so the ridges shade round like the pillows; split at HILL_CUT like the terrain
R = np.load(WORK / 'road.npz')
ROAD_MATS = {1: 'road', 2: 'rut', 3: 'pillow', 4: 'shoulder'}
ROAD_LIFT = 0.03                                   # over the terrain mesh, which it lies on


def road_obj(name, keep, layer):
    rx, ry, rz, part = R['x'], R['y'] + ROAD_LIFT, R['z'], R['part']
    nr, nc = rx.shape
    P = np.dstack([rx, rz, ry])                    # Blender axes
    du_, dv_ = np.gradient(P, axis=0), np.gradient(P, axis=1)
    nn = np.cross(du_, dv_); nn /= np.linalg.norm(nn, axis=2, keepdims=True) + 1e-9
    nn *= np.sign(nn[..., 2:3] + 1e-9)
    for _ in range(2):
        q = np.pad(nn, ((1, 1), (1, 1), (0, 0)), mode='edge')
        nn = (q[:-2, 1:-1] + q[2:, 1:-1] + q[1:-1, :-2] + q[1:-1, 2:] + 2 * q[1:-1, 1:-1]) / 6
        nn /= np.linalg.norm(nn, axis=2, keepdims=True)
    verts = [B(float(rx[i, j]), float(ry[i, j]), float(rz[i, j])) for i in range(nr) for j in range(nc)]
    faces, fm = [], []
    slot = {k: i for i, k in enumerate(ROAD_MATS)}
    for i in range(nr - 1):
        for j in range(nc - 1):
            if part[i, j] and keep(0.5 * (rz[i, j] + rz[i + 1, j + 1])):
                faces.append((i * nc + j, (i + 1) * nc + j, (i + 1) * nc + j + 1, i * nc + j + 1))   # facing up
                fm.append(slot[int(part[i, j])])
    me = mesh_from(name, verts, faces)
    for p_, f in zip(me.polygons, fm):
        p_.material_index = f
    me.normals_split_custom_set_from_vertices([tuple(v) for v in nn.reshape(-1, 3)])
    return obj(name, me, None, layer, mats=[dmat(MAT[m]) for m in ROAD_MATS.values()])


road_obj('road_near', lambda z: z < S['HILL_CUT'], 'hill')
road_obj('road_far', lambda z: z >= S['HILL_CUT'], 'trees')

# ------------------------------------------------------------------ flagstones: slabs standing proud of the snow
for k, st in enumerate(S['stones']):
    pts, top, bot = st['pts'], st['top'], st['bot']
    n = len(pts)
    cx = sum(p[0] for p in pts) / n; cz = sum(p[1] for p in pts) / n
    ring_b = [B(x, b, z) for (x, z), b in zip(pts, bot)]
    ring_t = [B(x, t, z) for (x, z), t in zip(pts, top)]
    ins = 0.07                                       # a rounded top edge: an inset ring a little higher
    ring_i = [B(cx + (x - cx) * (1 - ins / max(.3, st['w'] / 2)), t + 0.035, cz + (z - cz) * (1 - ins / max(.3, st['w'] / 2)))
              for (x, z), t in zip(pts, top)]
    verts = ring_b + ring_t + ring_i + [B(cx, sum(top) / n + 0.04, cz)]
    faces, fm = [], []
    for i in range(n):
        j = (i + 1) % n
        faces.append((i, j, n + j, n + i)); fm.append(1)
        faces.append((n + i, n + j, 2 * n + j, 2 * n + i)); fm.append(0)
        faces.append((2 * n + i, 2 * n + j, 3 * n)); fm.append(0)
    me = mesh_from(f'stone{k}', verts, faces)
    for p, f in zip(me.polygons, fm):
        p.material_index = f
    # bent normals on the top: toward a centre below the stone, so the flat top shades across in painted bands
    c = B(cx + 0.3 * SUN.x, sum(top) / n - st['w'] * 0.9, cz + 0.3 * SUN.y)
    nl = []
    for p in me.polygons:
        for li in p.loop_indices:
            v = me.vertices[me.loops[li].vertex_index].co
            if p.material_index == 0:
                nl.append(((Vector((0, 0, 1)) * 1.0 + (v - c).normalized() * 0.6)).normalized())
            else:
                nl.append(p.normal.copy())
    me.normals_split_custom_set(nl)
    obj(f'stone{k}', me, None, 'hill', mats=[dmat(MAT['stone']), dmat(MAT['stone_side'])])

# ------------------------------------------------------------------ posts, pillows
for k, (x, z, thick, ht, lean, g) in enumerate(S['posts']):
    r = thick / 2
    ln = math.radians(lean * 2.2)
    top = B(x + math.sin(ln) * ht, g + ht, z)
    base = B(x, g - 0.3, z)
    seg = 8
    verts, faces = [], []
    for c in (base, top):
        for i in range(seg):
            a = i / seg * math.tau
            verts.append(c + Vector((math.cos(a) * r, math.sin(a) * r, 0)))
    for i in range(seg):
        j = (i + 1) % seg
        faces.append((i, j, seg + j, seg + i))
    faces.append(tuple(range(seg, 2 * seg)))
    obj(f'post{k}', mesh_from(f'post{k}', verts, faces), dmat(MAT['wood']), 'hill')
    blob(f'cap{k}', top, r * 1.25, r * 1.25, max(r * 0.7, 0.05), dmat(MAT['pillow']), 'hill', seg=12)
    blob(f'foot{k}', B(x, g - 0.05, z), r * 1.9, r * 1.9, r * 0.9 + 0.05, dmat(MAT['pillow']), 'hill', seg=12)
for k, (x, z, r, g) in enumerate(S['pillows']):
    blob(f'pillow{k}', B(x, g, z), r * 1.35, r * 1.1, r * 0.75, dmat(MAT['pillow']), 'hill', seg=16, lift=-r * 0.15)

# ------------------------------------------------------------------ near snow: drift ridges, wind scallops, the lip
def ground(x, z):
    i = int(np.clip(np.searchsorted(TZ[:, 0], z), 0, len(TZ) - 1))
    return float(TY[i, int(np.argmin(np.abs(TX[i] - x)))])


def drift_chain(name, x0, x1, z0, z1, thick, high, seed, mat='snow'):
    """a wind-cut drift: a chain of overlapping soft lumps from (x0, z0) to (x1, z1), fat in the middle and tapering at
    the ends, so its crest scallops and it shades as one ridge (lit crest, a shaded lee toward us)"""
    dr = random.Random(seed)
    n = max(3, int(abs(x1 - x0) / 0.7))
    for i in range(n):
        t = i / (n - 1)
        taper = math.sin(math.pi * (0.12 + 0.76 * t)) ** 0.7
        x = x0 + (x1 - x0) * t + dr.uniform(-.12, .12)
        z = z0 + (z1 - z0) * t + dr.uniform(-.15, .15)
        rx = (0.95 + dr.uniform(-.1, .15)) * (0.6 + 0.4 * taper)
        blob(f'{name}{i}', B(x, ground(x, z), z), rx, thick * (0.7 + 0.3 * taper), high * taper * dr.uniform(.8, 1.1),
             dmat(MAT[mat]), 'hill', seg=16, lift=-high * 0.25)


# the lip along the bottom edge, either side of the stair, frames the shot (the open field gets its form from the
# rake shadows below: ridges there read as puddles)
for k, ((x0, z0), (x1, z1), thick, high, seed) in enumerate(S['lips']):
    drift_chain(f'lip{k}_', x0, x1, z0, z1, thick, high, seed)
# snow pillows in the open snow (fewer and bigger, round-shouldered: a soft dome sits in the snow, its lit top melting
# into the field and its own shadow at its foot; thin wide lenses read as floating saucers)
for k, (x, z, r) in enumerate(S['near_pillows']):
    blob(f'npillow{k}', B(x, ground(x, z), z), r * 1.25, r * 1.1, r * 0.95, dmat(MAT['pillow']), 'hill', seg=20, lift=-r * 0.35)


# ------------------------------------------------------------------ spruces: tiers of dab cards under snow shelves
def spruce(k, x, z, h, cls, g):
    """spruce k: a trunk, tiers of needle dabs with a skirt of hanging tips and pointed ends, a snow shelf on each
    tier, a leader"""
    layer = 'hill' if cls == 'tn' else 'trees'
    base = B(x, g, z)
    tr = random.Random(1000 + k)
    box(f'trunk{k}', lambda v, base=base, h=h: base + Vector(((v.x - .5) * .22, (v.y - .5) * .22, v.z * h * .4 - .3)),
        dmat(MAT['trunk']), layer)
    n = int(min(max(round(h / 0.85), 5), 10))
    lean = tr.uniform(-.04, .04)
    needles, snows = [], []
    sz = 0.26 + 0.035 * h
    for i in range(n):
        f = i / (n - 1)
        zc = h * (0.16 + 0.78 * i / n)
        r = (0.3 * h) * (1 - f) ** 1.05 + 0.18
        cx = base + Vector((lean * zc, 0, zc))
        for _ in range(int(10 + 22 * r * r ** 0.3)):
            a = tr.random() * math.tau; u = tr.random() ** .35; rr = r * u
            p = cx + Vector((math.cos(a) * rr, math.sin(a) * rr, -0.55 * h / n * u ** 1.5 + tr.uniform(-.06, .06)))
            sn = Vector((math.cos(a) * u * .7, math.sin(a) * u * .7, .9 - .9 * u ** 2)).normalized()
            needles.append((p, sz * tr.uniform(.8, 1.2), sn))
        for _ in range(int(6 + 12 * r)):             # the skirt under the tier: dark hanging tips
            a = tr.random() * math.tau; rr = r * tr.uniform(.45, .95)
            p = cx + Vector((math.cos(a) * rr, math.sin(a) * rr, -0.75 * h / n * (rr / r) ** 1.4 - .1 * h / n))
            needles.append((p, sz * .85, Vector((math.cos(a), math.sin(a), -.6)).normalized()))
        # the tier's ends on the silhouette: a few small cards past the rim, drooping, irregular in reach and drop, so
        # each tier ends in a designed point left and right instead of a round edge
        for side in (0.0, math.pi):
            for j in range(tr.randint(1, 3)):
                a = side + tr.uniform(-.5, .5); rr = r * tr.uniform(1.0, 1.18)
                p = cx + Vector((math.cos(a) * rr, math.sin(a) * rr, -0.9 * h / n - tr.uniform(0, .25) * h / n))
                needles.append((p, sz * tr.uniform(.45, .6), Vector((math.cos(a), math.sin(a), -.3)).normalized()))
        # the snow shelf: a band of soft puff cards along the tier's upper boughs, thickest on the outer half, so each
        # tier reads as a white chevron over its dark body
        for _ in range(int(6 + 16 * r * r ** 0.3)):
            a = tr.random() * math.tau; u = 0.35 + 0.6 * tr.random() ** .7; rr = r * u
            p = cx + Vector((math.cos(a) * rr, math.sin(a) * rr, -0.55 * h / n * u ** 1.5 + 0.1 + 0.06 * h / n))
            sn = Vector((math.cos(a) * u * .6, math.sin(a) * u * .3, 1.0)).normalized()
            snows.append((p, sz * tr.uniform(.85, 1.15), sn))
    tip = base + Vector((lean * h, 0, h * 0.98))     # a pointed leader over the top tier
    for j in range(6):
        p = tip + Vector((tr.uniform(-.06, .06), tr.uniform(-.06, .06), -j * 0.16 * (h / 6)))
        needles.append((p, sz * (0.35 + 0.1 * j), Vector((0, 0, 1))))
    allp = [p for p, _, _ in needles + snows]
    alln = [s for _, _, s in needles + snows]
    v = card_values([tuple(p) for p in allp], [tuple(s) for s in alln], reach=0.9 + 0.08 * h, gradient=0.18, value=0.45, count=10.0)
    cards(f'needles{k}', needles, dmat(MAT['needle_' + cls], 'dabs', 'card'), layer, v[:len(needles)])
    cards(f'snowc{k}', snows, dmat(MAT['snowc_' + cls], 'puffs', 'card'), layer, v[len(needles):] * 0.3)


# the composed core's spruces (the wider world's are built last: every card draws from one stream in build order)
for k, t in enumerate(S['trees'][:S['trees_core']]):
    spruce(k, *t)

# ------------------------------------------------------------------ the car: an old rounded estate, rear three-quarter
C = S['car']
a = math.radians(C['yaw'])
du = Vector((math.cos(a), math.sin(a), 0)); dw = Vector((math.sin(a), -math.cos(a), 0)); dv = Vector((0, 0, 1))
CS = C['L'] / 4.9
O = B(C['x'], C['y'], C['z'])


def cpt(u, w, v):
    return O + (du * u + dw * w + dv * v) * CS


def cbox(name, u0, u1, w0, w1, v0, v1, mat, bevel=0.0, seg=3):
    return box(name, lambda q: cpt(u0 + (u1 - u0) * q.x, w0 + (w1 - w0) * q.y, v0 + (v1 - v0) * q.z), dmat(MAT[mat]),
               'hill', bevel=bevel * CS, seg=seg)


cbox('body', 0.0, 4.9, -1.02, 1.02, 0.32, 1.08, 'car', bevel=0.22)
cbox('glass', 0.28, 3.25, -0.9, 0.9, 1.0, 1.62, 'glass', bevel=0.12)
cbox('roof', 0.2, 3.35, -0.95, 0.95, 1.58, 1.76, 'car', bevel=0.08)
for u0 in (0.22, 1.55, 3.12):                         # pillars
    cbox(f'pillar{u0}', u0, u0 + 0.16, -0.93, 0.93, 1.0, 1.62, 'car', bevel=0.03)
cbox('hood', 3.2, 4.85, -0.98, 0.98, 1.0, 1.16, 'car', bevel=0.12)
cbox('bumper_r', -0.06, 0.12, -1.0, 1.0, 0.36, 0.56, 'rack', bevel=0.05)
for wv in (-1, 1):
    cbox(f'tail{wv}', -0.03, 0.05, wv * 0.62, wv * 0.98, 0.74, 0.9, 'tail')
    cbox(f'lamp{wv}', 4.86, 4.93, wv * 0.55, wv * 0.85, 0.62, 0.78, 'lamp')
for u in (0.95, 3.9):
    for wv in (-1, 1):
        c = cpt(u, wv * 0.86, 0.38)
        bm = bmesh.new()
        bmesh.ops.create_cone(bm, cap_ends=True, segments=16, radius1=0.38 * CS, radius2=0.38 * CS, depth=0.26 * CS)
        me = bpy.data.meshes.new('tyre'); bm.to_mesh(me); bm.free()
        R = Matrix.Rotation(math.pi / 2, 4, 'X')
        Ry = Matrix.Rotation(a, 4, 'Z')
        for vtx in me.vertices:
            vtx.co = c + (Ry @ R @ vtx.co.to_4d()).to_3d()
        obj(f'tyre{u}{wv}', me, dmat(MAT['tyre']), 'hill')
cbox('rack', 0.45, 3.0, -0.85, 0.85, 1.76, 1.82, 'rack')
for k2, (u, w, rr) in enumerate(((0.9, -0.3, 0.55), (1.6, 0.35, 0.6), (2.4, -0.1, 0.55))):   # the roof load, lashed
    blob(f'load{k2}', cpt(u, w, 2.05), rr * CS, 0.5 * CS, 0.32 * CS, dmat(MAT['load']), 'hill', seg=14)
blob('loadsnow', cpt(1.65, 0.0, 2.32), 1.25 * CS, 0.75 * CS, 0.2 * CS, dmat(MAT['loadsnow']), 'hill', seg=16)
blob('hoodsnow', cpt(4.0, 0.0, 1.14), 0.75 * CS, 0.85 * CS, 0.07 * CS, dmat(MAT['loadsnow']), 'hill', seg=12)
TYRE_BANK = 0.5      # a little snow banked at the tyres: lumps within this of a wheel (car units)
for k2 in range(14):                                   # (the draws of a bank all along the foot are kept, so the
    u = -0.3 + 5.6 * k2 / 13                           # clouds built after it keep theirs)
    for wv in (-1, 1):
        c_, r_ = cpt(u, wv * (1.05 + rng.uniform(-.05, .15)), 0.0), [rng.uniform(lo, hi) * CS for lo, hi in
                                                                     ((.45, .7), (.35, .5), (.18, .28))]
        if min(abs(u - 0.95), abs(u - 3.9)) < TYRE_BANK:
            blob(f'bank{k2}{wv}', c_, r_[0] * 0.8, r_[1] * 0.8, r_[2], dmat(MAT['pillow']), 'hill', seg=12)

for o in sc.objects:
    if o.name.startswith(('body', 'glass', 'roof', 'pillar', 'hood', 'bumper', 'tail', 'lamp', 'tyre', 'rack', 'load',
                          'hoodsnow')):
        o['sprite'] = 1       # the car is the hand-drawn sprite in the picture; in 3D it only casts its shadow

# ------------------------------------------------------------------ poles
for k, (x, z, h, g) in enumerate(S['poles']):
    box(f'pole{k}', lambda v, x=x, z=z, h=h, g=g: B(x + (v.x - .5) * .32, g - .3 + v.z * (h + .3), z + (v.y - .5) * .32),
        dmat(MAT['wood']), 'hill')
    box(f'arm{k}', lambda v, x=x, z=z, h=h, g=g: B(x + (v.x - .5) * 2.1, g + h - .55 + v.z * .14, z + (v.y - .5) * .14),
        dmat(MAT['wood']), 'hill')

for o in sc.objects:          # posts, their caps and feet, the poles: pixel sprites in the picture (draw2d.props)
    if o.name.startswith(('post', 'cap', 'foot', 'pole', 'arm')):
        o['sprite'] = 1

# ------------------------------------------------------------------ clouds: puff cards in clumps, lit as one mass
def spx(sx, sy, d=900.0):
    """a point at depth d behind core column sx, row sy"""
    m = (d + ZB) / F
    return Vector(((sx + CORE_X - X0) * m, d, CAMH + (Y0 - sy) * m))


# the clouds' light: the low sun is behind-right of the tower, so its crowns light on the upper right, the faces
# toward us sit in the mid band and the bellies fall to slate-violet (the sun proper stays back-left for the ground)
LC = Vector((0.42, -0.5, 0.76)).normalized()


def view_normal(o, rx, rz):
    """the sphere (ellipsoid) normal seen from the camera at offset o from its centre: x/z across the disc, the rest
    toward us"""
    ux, uz = o.x / rx, o.z / rz
    t = min((ux * ux + uz * uz) ** .5, .97)
    k = t / max(1e-6, (ux * ux + uz * uz) ** .5)
    ux, uz = ux * k, uz * k
    return Vector((ux, -(1 - t * t) ** .5, uz))


def cumulus(name, clumps, mid, d=900.0, mass=0.45, env=None, base=None, card=0.42, ao=0.08, crown=None, crown_mid=None):
    """clumps = [(sx, sy, r_px, squash)]: each clump a disc of puff cards smaller than the clump, so its silhouette is
    a lumpy dab edge while its shading is one sphere (the 'cloud' shader's per-pixel sphere normal from the card's
    clump attributes: the stepped bands cross the cards). The clump normals lean toward the whole cloud's (env = (sx,
    sy, rx_px, ry_px)), and pixels under `base` (a screen row) turn down into one shared flat shadow base. crown(sx, sy) -> True puts a clump's cards on crown_mid
    (the sun's hot pink crown edge)."""
    m = (d + ZB) / F
    if env is None:
        xs = [c[0] for c in clumps]; ys = [c[1] for c in clumps]
        env = ((min(xs) + max(xs)) / 2, (min(ys) + max(ys)) / 2, (max(xs) - min(xs)) / 2 + 30, (max(ys) - min(ys)) / 2 + 30)
    ec = spx(env[0], env[1], d)
    erx, erz = env[2] * m, env[3] * m
    zb = -1e6 if base is None else spx(0, base, d).z
    groups = {}
    for sx, sy, r, sq in clumps:
        c = spx(sx, sy, d); R = r * m
        n = int(6 + 2.4 / (card * card) * (0.6 + 0.4 * sq))
        key = crown_mid if (crown and crown(sx, sy)) else mid
        for _ in range(n):
            a = rng.random() * math.tau; rr = R * 0.62 * rng.random() ** .5
            p = c + Vector((math.cos(a) * rr, rng.gauss(0, 1) * R * .15, math.sin(a) * rr * sq))
            sz = R * card * rng.uniform(.8, 1.2)
            if base is not None and p.z - sz * .55 < zb:
                p.z = zb + sz * .55
            g_ = groups.setdefault(key, dict(items=[], cc=[], cs=[], cb=[], cbw=[]))
            g_['items'].append((p, sz, (0.0, -1.0, 0.0)))
            g_['cc'].append(tuple(c)); g_['cs'].append((R * 1.12, 1.0, R * 1.12 * sq))
            g_['cbw'].append(0.5 * R); g_['cb'].append(zb + 0.35 * R)
    for key, g_ in groups.items():
        items = g_['items']
        v = card_values([tuple(p) for p, _, _ in items], [(0, -1, 0)] * len(items), reach=1.4 * m * 20, gradient=0.0,
                        value=ao, count=14.0)
        k_ = len(items)
        cards(f'{name}_{key}', items, dmat(key, 'puffs', 'cloud', tuple(LC)), 'sky', v,
              attrs=dict(cc=g_['cc'], cs=g_['cs'], ec=[tuple(ec)] * k_, es=[(erx, 1.0, erz)] * k_, cm=[mass] * k_,
                         cb=g_['cb'], cbw=g_['cbw']))


crng = random.Random(9)
# the towering cumulus over the car: a size hierarchy. Big body masses low, mid clumps up the tower, small crisp
# puffs only along the rim; the hot pink is the crown edge of the top and right clumps, attached to the body
BODY = [(415, 262, 58, .9), (520, 255, 64, .9), (612, 270, 46, .85), (340, 282, 44, .8), (465, 205, 52, 1.),
        (560, 200, 50, 1.), (505, 160, 44, 1.)]
MIDC = [(410, 205, 32, .9), (612, 220, 30, .9), (452, 150, 30, 1.), (565, 145, 32, 1.), (520, 112, 30, 1.),
        (470, 112, 24, 1.), (640, 180, 24, 1.), (380, 238, 28, .85), (500, 215, 40, .9), (440, 175, 30, 1.),
        (590, 170, 28, 1.), (545, 232, 40, .85), (485, 128, 26, 1.)]
RIM = []
for (cx, cy, r, sq) in BODY + MIDC:                    # crisp puffs on the outer rim: the top and the sides
    for _ in range(3 if r > 40 else 2):
        a = crng.uniform(math.pi * 0.05, math.pi * 0.95) if cy < 230 else crng.choice((crng.uniform(-.2, .7), crng.uniform(2.4, 3.3)))
        rx, ry = cx + math.cos(a) * r * 0.92, cy - math.sin(a) * r * sq * 0.92
        RIM.append((rx, ry, crng.uniform(9, 14), 1.0))
# the tower is drawn above in a 300 px frame; it is squeezed into the sky the view shows (rows ~160-300)
SQZ = 0.68
BODY, MIDC, RIM = ([(475 + (x - 500) * 1.15, 300 - (300 - y) * SQZ, r * 0.95, sq) for x, y, r, sq in grp]
                   for grp in (BODY, MIDC, RIM))
# then set a little smaller and lower about its base (TS, TDY), so the pink crown has sky above it in the view
TS, TDY = 0.9, 14
BODY, MIDC, RIM = ([(475 + (x - 475) * TS, 300 + (y - 300) * TS + TDY, r * 0.95, sq) for x, y, r, sq in grp]
                   for grp in (BODY, MIDC, RIM))
TOWER_ENV = (475, 300 + TDY - 100 * SQZ * TS, 185 * TS, 100 * SQZ * TS)
cumulus('tower', BODY + MIDC + RIM, MAT['cloud'], mass=0.3, env=TOWER_ENV, base=300 + TDY, card=0.42,
        crown=lambda x, y: (x - 475) / (215 * TS) * 0.75 + (300 + TDY - 100 * SQZ * TS - y) / (125 * SQZ * TS) > 0.62,
        crown_mid=MAT['pink'])
# the low stratocumulus deck along the horizon, under the tower: flat clumps, the same light, paler (further)
deck = []
x = -60
while x < 940:
    r = crng.uniform(22, 34)
    deck.append((x, 262 + crng.uniform(-6, 6), r, 0.42)); x += r * crng.uniform(0.9, 1.3)
    if crng.random() < 0.5:
        deck.append((x - r * .4, 248 + crng.uniform(-5, 4), r * .55, 0.5))
cumulus('deck', deck, MAT['deck'], d=860, mass=0.55, env=(440, 256, 520, 26), base=276, card=0.5, ao=0.05)
# the small far clouds: the same build, smaller, on their own paler ramp
for ci, (cx, cy, wd) in enumerate(((180, 188, 64), (95, 168, 40), (760, 192, 52), (300, 128, 36), (690, 120, 30),
                                   (835, 150, 40), (130, 228, 70), (262, 214, 46), (790, 236, 56), (250, 170, 34), (40, 196, 44),
                                   (330, 196, 26))):
    cl = [(cx + crng.uniform(-wd, wd) * .8, cy + crng.uniform(-3, 3), crng.uniform(11, 17), .7) for _ in range(max(2, int(wd / 14)))]
    cl += [(cx + crng.uniform(-wd, wd) * .5, cy - 8 + crng.uniform(-3, 3), crng.uniform(7, 11), 1.) for _ in range(2)]
    cumulus(f'far{ci}', cl, MAT['cloudfar'], d=1000, mass=0.5, env=(cx, cy, wd + 14, 18), base=cy + 9, card=0.5, ao=0.0)

# ------------------------------------------------------------------ the rake: long shadows from trees off-screen
# a second, low sun from the left (a shadow-only pass) and cones standing in the spruce stand left of the core, invisible
# to the camera: their shadows rake across the near snow as long blue bands, the reference's foreground
RAKE = B(-0.97, 0.2, 0.1).normalized()                 # low (~11 deg), nearly side-on: the bands run across
RAKERS = []
for k, (x, z, h, r) in enumerate(S['rakers']):
    g = ground(x, z)
    for t in range(3):                                  # overlapping cones: one solid spruce shadow, serrated edge
        bm = bmesh.new()
        bmesh.ops.create_cone(bm, cap_ends=True, segments=9, radius1=r * (1.0 - 0.18 * t), radius2=0.02,
                              depth=h * (0.85 - 0.15 * t))
        me = bpy.data.meshes.new(f'raker{k}_{t}'); bm.to_mesh(me); bm.free()
        for vtx in me.vertices:
            vtx.co = B(x, g + h * (0.08 + 0.15 * t) + (h * (0.85 - 0.15 * t)) / 2, z) + Vector(vtx.co)
        o = obj(f'raker{k}_{t}', me, dmat(MAT['trunk']), 'rake')
        RAKERS.append(o)


def catcher():
    """the rake pass's material: diffuse with its normal turned to the rake sun, so the value is the shadow alone"""
    m = bpy.data.materials.new('catch'); m.use_nodes = True
    N, L = m.node_tree.nodes, m.node_tree.links; N.clear()
    out = N.new('ShaderNodeOutputMaterial')
    d = N.new('ShaderNodeBsdfDiffuse'); d.inputs['Color'].default_value = (1, 1, 1, 1)
    nv = N.new('ShaderNodeCombineXYZ')                  # (an unlinked Normal socket is ignored, so link a constant)
    for i in range(3):
        nv.inputs[i].default_value = RAKE[i]
    L.new(nv.outputs[0], d.inputs['Normal'])
    s2r = N.new('ShaderNodeShaderToRGB'); L.new(d.outputs[0], s2r.inputs[0])
    em = N.new('ShaderNodeEmission'); L.new(s2r.outputs[0], em.inputs[0]); L.new(em.outputs[0], out.inputs[0])
    return m


# ------------------------------------------------------------------ the wider world
# built after everything in the composed core, so the core's cards keep the draws they always had: the spruce band and
# the near spruces past the core's edges, the horizon deck and small far clouds on over the wings
for k, t in enumerate(S['trees'][S['trees_core']:], S['trees_core']):
    spruce(k, *t)
wrng = random.Random(23)
for side, (x0, x1) in enumerate(((-CORE_X - 60, -60), (940, W - CORE_X + 60))):
    wdeck, x = [], x0
    while x < x1:
        r = wrng.uniform(22, 34)
        wdeck.append((x, 262 + wrng.uniform(-6, 6), r, 0.42)); x += r * wrng.uniform(0.9, 1.3)
        if wrng.random() < 0.5:
            wdeck.append((x - r * .4, 248 + wrng.uniform(-5, 4), r * .55, 0.5))
    cumulus(f'deck_wing{side}', wdeck, MAT['deck'], d=860, mass=0.55, env=((x0 + x1) / 2, 256, (x1 - x0) / 2 + 80, 26),
            base=276, card=0.5, ao=0.05)
for ci, (cx, cy, wd) in enumerate(((-300, 176, 50), (-210, 214, 64), (-120, 140, 34), (-60, 236, 40), (960, 168, 44),
                                   (1040, 222, 60), (1130, 132, 30), (1190, 196, 52))):
    cl = [(cx + wrng.uniform(-wd, wd) * .8, cy + wrng.uniform(-3, 3), wrng.uniform(11, 17), .7) for _ in range(max(2, int(wd / 14)))]
    cl += [(cx + wrng.uniform(-wd, wd) * .5, cy - 8 + wrng.uniform(-3, 3), wrng.uniform(7, 11), 1.) for _ in range(2)]
    cumulus(f'farw{ci}', cl, MAT['cloudfar'], d=1000, mass=0.5, env=(cx, cy, wd + 14, 18), base=cy + 9, card=0.5, ao=0.0)


# ------------------------------------------------------------------ light, camera, render
sun = bpy.data.lights.new('sun', 'SUN'); sun.energy = math.pi; sun.angle = math.radians(0.6)
so = bpy.data.objects.new('sun', sun); sc.collection.objects.link(so)
so.rotation_euler = (-SUN).to_track_quat('-Z', 'Y').to_euler()
sun2 = bpy.data.lights.new('rake', 'SUN'); sun2.energy = math.pi; sun2.angle = math.radians(1.2)
so2 = bpy.data.objects.new('rake', sun2); sc.collection.objects.link(so2)
so2.rotation_euler = (-RAKE).to_track_quat('-Z', 'Y').to_euler(); so2.hide_render = True
world = bpy.data.worlds.new('w'); sc.world = world; world.use_nodes = True
world.node_tree.nodes['Background'].inputs[0].default_value = (1, 1, 1, 1)
world.node_tree.nodes['Background'].inputs[1].default_value = 0.28
cam = bpy.data.cameras.new('cam'); cam.sensor_fit = 'HORIZONTAL'; cam.sensor_width = 36.0
cam.lens = 36.0 * F / W; cam.shift_y = (Y0 - H / 2) / W; cam.clip_start = 0.5; cam.clip_end = 3000
co = bpy.data.objects.new('cam', cam); sc.collection.objects.link(co); sc.camera = co
co.location = CAMP; co.rotation_euler = (math.pi / 2, 0, 0)

sc.render.engine = 'BLENDER_EEVEE_NEXT'
sc.eevee.taa_render_samples = SAMPLES
sc.eevee.use_shadows = True
try:
    sc.eevee.shadow_ray_count = 1; sc.eevee.shadow_step_count = 4
except Exception:
    pass
sc.render.filter_size = 0.0
sc.render.dither_intensity = 0.0
sc.render.film_transparent = True
sc.view_settings.view_transform = 'Raw'
sc.view_settings.look = 'None'
sc.render.resolution_x, sc.render.resolution_y = W * SS, H * SS
st = sc.render.image_settings
st.file_format = 'PNG'; st.color_mode = 'RGBA'; st.color_depth = '16'
(WORK / 'raw').mkdir(exist_ok=True)
for o in sc.objects:
    if o.type == 'MESH' and LAYER.get(o.name) == 'sky':
        o.visible_shadow = False
    # the per-material shadow switch of the painted engine: thin things (posts, their caps, poles) cast no long
    # stripes over the snow; trees, pillows, stones and the car do
    if o.type == 'MESH' and o.name.startswith(('post', 'cap', 'pole', 'arm')):
        o.visible_shadow = False
    if o.type == 'MESH' and LAYER.get(o.name) == 'rake':
        o.visible_shadow = False


def lampmat(alpha):
    """the lamp pass's material: plain diffuse under the headlamps alone (R) and depth (B); the cards keep their alpha
    and their clump normals, so the spruce boughs the beam reaches light as soft masses"""
    m = bpy.data.materials.new(f'lamp_{alpha}'); m.use_nodes = True
    N, L = m.node_tree.nodes, m.node_tree.links; N.clear()
    out = N.new('ShaderNodeOutputMaterial')
    d = N.new('ShaderNodeBsdfDiffuse'); d.inputs['Color'].default_value = (1, 1, 1, 1)
    s2r = N.new('ShaderNodeShaderToRGB'); L.new(d.outputs[0], s2r.inputs[0])
    bw = N.new('ShaderNodeRGBToBW'); L.new(s2r.outputs[0], bw.inputs[0])
    r = N.new('ShaderNodeMath'); r.operation = 'MULTIPLY_ADD'; r.use_clamp = True
    L.new(bw.outputs[0], r.inputs[0]); r.inputs[1].default_value = 0.4; r.inputs[2].default_value = 0.2
    g = N.new('ShaderNodeNewGeometry'); sep = N.new('ShaderNodeSeparateXYZ'); L.new(g.outputs['Position'], sep.inputs[0])
    dv = N.new('ShaderNodeMath'); dv.operation = 'DIVIDE'; L.new(sep.outputs['Y'], dv.inputs[0]); dv.inputs[1].default_value = 160.0
    comb = N.new('ShaderNodeCombineRGB'); L.new(r.outputs[0], comb.inputs[0]); L.new(dv.outputs[0], comb.inputs[2])
    em = N.new('ShaderNodeEmission'); L.new(comb.outputs[0], em.inputs[0]); sh = em.outputs[0]
    if alpha:
        img = bpy.data.images.get(alpha + '.png') or bpy.data.images.load(str(WORK / 'tex' / f'{alpha}.png'))
        img.colorspace_settings.name = 'Non-Color'
        tx = N.new('ShaderNodeTexImage'); tx.image = img; tx.interpolation = 'Closest'
        gt = N.new('ShaderNodeMath'); gt.operation = 'GREATER_THAN'; L.new(tx.outputs['Color'], gt.inputs[0]); gt.inputs[1].default_value = 0.5
        tr = N.new('ShaderNodeBsdfTransparent'); mx = N.new('ShaderNodeMixShader')
        L.new(gt.outputs[0], mx.inputs[0]); L.new(tr.outputs[0], mx.inputs[1]); L.new(sh, mx.inputs[2]); sh = mx.outputs[0]
    L.new(sh, out.inputs[0])
    m.surface_render_method = 'DITHERED'
    return m


# the headlamps: one spot between the two lamps, aimed along the car's nose and a little down; its own pass
LAMP_U, LAMP_V, LAMP_TILT = S['lamp']                # place.LAMP_*: along the car from its tail, height, tilt (deg)
LAMP_AT = cpt(LAMP_U, 0.0, LAMP_V)
spot = bpy.data.lights.new('headlamps', 'SPOT'); spot.energy = 14000.0
spot.spot_size = math.radians(64); spot.spot_blend = 0.55; spot.shadow_soft_size = 0.05
spo = bpy.data.objects.new('headlamps', spot); sc.collection.objects.link(spo)
spo.location = LAMP_AT
aim = (du * math.cos(math.radians(LAMP_TILT)) - dv * math.sin(math.radians(LAMP_TILT))).normalized()
spo.rotation_euler = aim.to_track_quat('-Z', 'Y').to_euler(); spo.hide_render = True
CATCH = ('snow_near', 'lip', 'ridge', 'pillow', 'npillow', 'foot', 'stone')
if 'hill' in ONLY:
    ONLY = ONLY + ['rake']
if 'hill' in ONLY or 'trees' in ONLY:
    ONLY = ONLY + ['lamp']
for lay in ONLY:
    if lay == 'lamp':                                   # the headlamps alone, over the hill and the trees
        so.hide_render = True; so2.hide_render = True; spo.hide_render = False
        world.node_tree.nodes['Background'].inputs[1].default_value = 0.0
        mats = {}
        for o in sc.objects:
            if o.type != 'MESH':
                continue
            on = LAYER.get(o.name) in ('hill', 'trees')
            o.visible_shadow = on and not o.name.startswith(('lamp', 'post', 'cap', 'pole', 'arm'))
            o.visible_camera = on and not o.get('sprite')
            if on:
                al = 'dabs' if o.name.startswith('needles') else 'puffs' if o.name.startswith('snowc') else None
                if al not in mats:
                    mats[al] = lampmat(al)
                for sl in o.material_slots:
                    sl.link = 'OBJECT'; sl.material = mats[al]
    elif lay == 'rake':                                   # the shadow-only pass: rake sun, no sky, catchers only
        so.hide_render = True; so2.hide_render = False
        world.node_tree.nodes['Background'].inputs[1].default_value = 0.0
        cm = catcher()
        for o in sc.objects:
            if o.type != 'MESH':
                continue
            o.visible_shadow = LAYER.get(o.name) == 'rake'  # only the off-frame trees cast in this pass
            catch = LAYER.get(o.name) == 'hill' and o.name.startswith(CATCH)
            o.visible_camera = catch
            if catch:
                for sl in o.material_slots:
                    sl.link = 'OBJECT'; sl.material = cm
    else:
        for o in sc.objects:
            if o.type == 'MESH':
                o.visible_camera = LAYER.get(o.name) == lay and not o.get('sprite')
    sc.render.filepath = str(WORK / 'raw' / f'{lay}.png')
    bpy.ops.render.render(write_still=True)
    img = bpy.data.images.load(sc.render.filepath); img.colorspace_settings.name = 'Non-Color'
    w, h = img.size
    px = np.empty(w * h * 4, np.float32); img.pixels.foreach_get(px)
    np.save(WORK / 'raw' / f'{lay}.npy', px.reshape(h, w, 4)[::-1].astype(np.float16))   # PIL reads 16-bit PNG as 8
    bpy.data.images.remove(img)
    print('fp paint: rendered', lay, flush=True)

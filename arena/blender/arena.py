"""An arena map built in Blender with the painted-cards technique, rendered as DATA for arena/paint.py.

Run by `python3 -m arena paint --map NAME` (a python with the bpy module, or blender -b -P this.py -- WORK SAMPLES
SCALE ONLY). Reads WORK/scene3d.json + WORK/terrain.npz + WORK/scenery.npz (the map's place.py export) and
WORK/tex/{dabs,puffs}.png; writes WORK/raw/*.npy, float16 (H, W, 4):
    world   R = lit value (diffuse under the low sun + the sky fill, shadows and all), G = material id / 64,
            B = (depth + 200) / 800, A = coverage: the ledge, its cliffs and everything on it
    back    the same for the scenery behind the ledge (backdrop and vista: three forest ridges, the cumulus towers
            and the cloud sea), built in forced scale and at its zone's detail level, no shadows
    ids     R, G = the occluder index (lo, hi bytes): which tree / rock / stake / tent each pixel belongs to, so the
            runtime can draw units behind them; B = the pixel's depth zone code / 8 (0 = the terrain: paint.py
            zones it from where it is)

This file is the shared kit: the data shader, the geometry helpers (blobs, boxes, cylinders, camera-facing dab and puff
cards with sphere normals, the per-card buried/crown values), the terrain mesh, the spruce, the cumulus mass, the far
ridges' strips, the lights, the camera and the passes. The map's own builders (scene3d.json `builder`:
arena/maps/<name>/blender.py) run in this file's namespace and define TERRAIN (the terrain's material classes), BUILD
(kind -> builder for layout() things) and build_back() (the backdrop and vista).

The technique is the fp engine's (fp/blender/first_snow.py, after painted/bpy/painter.py), for an orthographic camera:
camera-facing dab cards with clump (sphere) normals for the spruces and the clouds, per-tree buried/crown values, bent
normals on flat tops, blurred normals on the snow so it shades as big soft forms, one low sun with real cast shadows.
Blender axes = the world grid (x, y, z); the camera looks along +v = (x + y) / sqrt 2, down by EL.
"""
import bpy, bmesh, sys, json, math, random
from pathlib import Path
import numpy as np
from mathutils import Vector, Matrix

argv = sys.argv[sys.argv.index('--') + 1:] if '--' in sys.argv else sys.argv[1:]
WORK = Path(argv[0])
SAMPLES = int(argv[1]) if len(argv) > 1 else 1
SCALE = float(argv[2]) if len(argv) > 2 else 1.0     # render size (0.5 for a quick look)
ONLY = argv[3].split(',') if len(argv) > 3 and argv[3] else ['world', 'back', 'ids']
S = json.load(open(WORK / 'scene3d.json'))
PPM, EL, W, H, X0, Y0 = S['PPM'], S['EL'], S['W'], S['H'], S['X0'], S['Y0']
SE, CE = math.sin(EL), math.cos(EL)
R2 = math.sqrt(2.0)
rng = random.Random(5)

MAT = S['mats']                                     # the map's material ids (its biome.MAT)
ZCODE = {k: v['code'] for k, v in S['zones'].items()}
DETAIL = {k: v['detail'] for k, v in S['zones'].items()}


def U(u, v, z=0.0):
    """world (u, v, z) -> Blender (x, y, z)"""
    return Vector(((u + v) / R2, (v - u) / R2, z))


VD = (U(0, CE, -SE)).normalized()                  # the view direction
TOCAM = -VD
RIGHT = U(1, 0, 0).normalized()
UPS = TOCAM.cross(RIGHT).normalized() * -1         # screen up
if UPS.z < 0:
    UPS = -UPS
su, sv, sz = S['SUN']
SUN = U(su, sv, sz).normalized()
LC = U(-0.55, 0.35, 0.75).normalized()             # the clouds' light: the low sun from the upper left
FILL = U(0.75, -0.55, 0.35).normalized()           # a weak bounce off the cloud sea from the front right: form on
                                                    # the faces the low sun leaves in shade (no shadows)

bpy.ops.wm.read_factory_settings(use_empty=True)
sc = bpy.context.scene
LAYER = {}
OCC = {}                                            # object name -> occluder index (1..)

T = np.load(WORK / 'terrain.npz')
TU, TV, TZ = T['u'], T['v'], T['z']
TL, TP, TQ = T['lane'], T['plat'], T['play']
ST = float(TU[0, 1] - TU[0, 0])


def ground(u, v):
    """terrain height (bilinear on the exported grid)"""
    fi = (v - TV[0, 0]) / ST; fj = (u - TU[0, 0]) / ST
    i = int(np.clip(math.floor(fi), 0, TZ.shape[0] - 2)); j = int(np.clip(math.floor(fj), 0, TZ.shape[1] - 2))
    a, b = fi - i, fj - j
    z = TZ[i, j] * (1 - a) * (1 - b) + TZ[i + 1, j] * a * (1 - b) + TZ[i, j + 1] * (1 - a) * b + TZ[i + 1, j + 1] * a * b
    return float(z)


# ------------------------------------------------------------------ the data shader
MATS = {}


def dmat(mid, alpha=None, kind='lit'):
    """emission of (lit value, material id, depth). 'lit': diffuse under the sun and sky (shadows) through Shader to
    RGB. 'card': the card's (clump) normal against the sun + sky, no shadows received. 'cloud': the clump normal
    against the clouds' light, half-lambert. 'flat': a constant (lamps). The per-card attribute `val` adds the
    buried/crown value."""
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

    g = N.new('ShaderNodeNewGeometry')
    if kind == 'lit':
        d = N.new('ShaderNodeBsdfDiffuse'); d.inputs['Color'].default_value = (1, 1, 1, 1)
        s2r = N.new('ShaderNodeShaderToRGB'); L.new(d.outputs[0], s2r.inputs[0])
        bw = N.new('ShaderNodeRGBToBW'); L.new(s2r.outputs[0], bw.inputs[0])
        lit = bw.outputs[0]
    elif kind in ('card', 'cloud'):
        dp = N.new('ShaderNodeVectorMath'); dp.operation = 'DOT_PRODUCT'
        L.new(g.outputs['Normal'], dp.inputs[0])
        dp.inputs[1].default_value = tuple(SUN if kind == 'card' else LC)
        if kind == 'card':
            dpf = N.new('ShaderNodeVectorMath'); dpf.operation = 'DOT_PRODUCT'
            L.new(g.outputs['Normal'], dpf.inputs[0]); dpf.inputs[1].default_value = tuple(FILL)
            lit = math_('ADD', math_('ADD', math_('MAXIMUM', dp.outputs['Value'], 0.0), 0.28),
                        math_('MULTIPLY', math_('MAXIMUM', dpf.outputs['Value'], 0.0), 0.32))
        else:
            lit = math_('ADD', math_('MULTIPLY', dp.outputs['Value'], 0.5), 0.5)
    else:
        lit = math_('ADD', 0.0, 1.0)
    at = N.new('ShaderNodeAttribute'); at.attribute_name = 'val'; at.attribute_type = 'GEOMETRY'
    lit = math_('ADD', lit, at.outputs['Fac'])
    r = math_('MINIMUM', math_('MAXIMUM', math_('ADD', math_('MULTIPLY', lit, 0.4), 0.2), 0.0), 1.0)
    dp2 = N.new('ShaderNodeVectorMath'); dp2.operation = 'DOT_PRODUCT'
    L.new(g.outputs['Position'], dp2.inputs[0]); dp2.inputs[1].default_value = tuple(VD)
    dep = math_('DIVIDE', math_('ADD', dp2.outputs['Value'], 200.0), 800.0)
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
ZONE_NOW = [0]                                       # the zone code of what is being built (0 = terrain)


def link(name, me, mats, layer='world', occ=None):
    o = bpy.data.objects.new(name, me)
    for mm in mats:
        o.data.materials.append(mm)
    sc.collection.objects.link(o)
    LAYER[o.name] = layer
    o['zone'] = ZONE_NOW[0]
    if occ:
        OCC[o.name] = occ
    return o


def mesh_from(name, verts, faces, smooth_=True):
    me = bpy.data.meshes.new(name)
    me.from_pydata([tuple(v) for v in verts], [], faces)
    me.update()
    for p in me.polygons:
        p.use_smooth = smooth_
    return me


def blob(name, c, rx, ry, rz, mat, occ=None, seg=16, rot=0.0, noise=0.0, seed=0, flat=0.0, mass=0.0, layer='world'):
    """a smooth ellipsoid at Blender point c (radii along the rotated x, y, z); noise lumps it, flat cuts its base"""
    bm = bmesh.new()
    bmesh.ops.create_uvsphere(bm, u_segments=seg, v_segments=max(6, seg // 2), radius=1.0)
    rr = random.Random(seed)
    ph = [rr.uniform(0, 6.28) for _ in range(6)]
    Rz = Matrix.Rotation(rot, 3, 'Z')
    for v in bm.verts:
        p = v.co.copy()
        if noise:
            k = 1 + noise * (math.sin(p.x * 3.1 + ph[0]) * math.sin(p.y * 2.7 + ph[1]) + 0.6 * math.sin(p.z * 3.7 + ph[2])
                             + 0.4 * math.sin((p.x + p.y) * 5.3 + ph[3]))
            p *= k
        if flat and p.z < -flat:
            p.z = -flat
        v.co = c + Rz @ Vector((p.x * rx, p.y * ry, p.z * rz))
    me = bpy.data.meshes.new(name); bm.to_mesh(me); bm.free()
    for p in me.polygons:
        p.use_smooth = True
    if mass:
        nl = []
        for p in me.polygons:
            for li in p.loop_indices:
                vco = me.vertices[me.loops[li].vertex_index].co
                n = ((vco - c).normalized() * mass + me.vertices[me.loops[li].vertex_index].normal * (1 - mass)).normalized()
                nl.append(n)
        me.normals_split_custom_set(nl)
    return link(name, me, [mat], occ=occ, layer=layer)


def box(name, fn, mat, occ=None, bevel=0.0, seg=2, layer='world'):
    """a box from a local->world function over the unit cube [0,1]^3, bevelled"""
    bm = bmesh.new()
    bmesh.ops.create_cube(bm, size=1.0)
    for v in bm.verts:
        v.co = fn(v.co + Vector((.5, .5, .5)))
    if bevel:
        bmesh.ops.bevel(bm, geom=bm.edges[:] + bm.verts[:], offset=bevel, segments=seg, affect='EDGES', clamp_overlap=True)
    me = bpy.data.meshes.new(name); bm.to_mesh(me); bm.free()
    for p in me.polygons:
        p.use_smooth = bool(bevel)
    return link(name, me, [mat], occ=occ, layer=layer)


def frame_box(name, c, ax, ay, sx, sy, z0, z1, mat, occ=None, bevel=0.0, layer='world'):
    """a box centred on Blender point c (xy), axes ax, ay (unit Blender vectors), sizes sx, sy, from z0 to z1"""
    return box(name, lambda q: Vector((c.x, c.y, 0)) + ax * (q.x - .5) * sx + ay * (q.y - .5) * sy + Vector((0, 0, z0 + (z1 - z0) * q.z)),
               mat, occ, bevel, layer=layer)


def cyl(name, a, b, r, mat, occ=None, seg=8, r2=None, cap=True, layer='world'):
    """a cylinder (cone when r2) from Blender point a to b"""
    r2 = r if r2 is None else r2
    ax = (b - a)
    ln = ax.length
    q = ax.normalized().to_track_quat('Z', 'Y')
    verts, faces = [], []
    for k, (c, rr) in enumerate(((a, r), (b, r2))):
        for i in range(seg):
            t = i / seg * math.tau
            verts.append(c + q @ Vector((math.cos(t) * rr, math.sin(t) * rr, 0)))
    for i in range(seg):
        j = (i + 1) % seg
        faces.append((i, j, seg + j, seg + i))
    if cap:
        faces.append(tuple(range(seg, 2 * seg)))
        faces.append(tuple(reversed(range(seg))))
    del ln
    return link(name, mesh_from(name, verts, faces), [mat], occ=occ, layer=layer)


def cards(name, items, mat, val=None, layer='world', occ=None):
    """items = [(centre, half_size, normal or normal(corner))], every card square to the camera (a dab)"""
    me = bpy.data.meshes.new(name); bm = bmesh.new(); uvl = bm.loops.layers.uv.new(); nrm = []
    base_q = TOCAM.to_track_quat('Z', 'Y')
    for p, s, sn in items:
        q = base_q @ Matrix.Rotation(rng.random() * math.tau, 4, 'Z').to_quaternion()
        corners = [p + q @ Vector((x * s, y * s, 0)) for x, y in ((-1, -1), (1, -1), (1, 1), (-1, 1))]
        face = bm.faces.new([bm.verts.new(c) for c in corners])
        t = rng.randrange(4); u0, v0 = (t % 2) * .5, (t // 2) * .5
        for lp, (u, v) in zip(face.loops, ((0, 0), (1, 0), (1, 1), (0, 1))):
            lp[uvl].uv = (u0 + u * .5, v0 + v * .5)
        nrm += [tuple(sn(c)) for c in corners] if callable(sn) else [tuple(sn)] * 4
    bm.to_mesh(me); bm.free()
    me.normals_split_custom_set(nrm)
    if val is not None:
        me.attributes.new('val', 'FLOAT', 'POINT').data.foreach_set('value', np.repeat(np.asarray(val, np.float32), 4))
    return link(name, me, [mat], layer=layer, occ=occ)


def card_values(pos, nrm, reach, gradient, value, count):
    """the value step over one asset: buried cards darken (the AO pockets), a gradient along the sun lightens"""
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
def terrain_obj(slot_names, classify):
    """the terrain as one mesh: calm (blurred) normals on the walkable top, facets past the lip; each face's material
    from the map's classify(i, j, zc, steep) (None leaves the face out)"""
    nr, nc = TU.shape
    verts = [U(float(TU[i, j]), float(TV[i, j]), float(TZ[i, j])) for i in range(nr) for j in range(nc)]
    faces, fm = [], []
    P = np.dstack([(TU + TV) / R2, (TV - TU) / R2, TZ])
    du_ = np.gradient(P, axis=1); dv_ = np.gradient(P, axis=0)
    nn = np.cross(du_, dv_); nn /= np.linalg.norm(nn, axis=2, keepdims=True) + 1e-9
    nn *= np.sign(nn[..., 2:3] + 1e-9)
    steep = nn[..., 2] < 0.62
    # calm normals on the snow (blurred over a few cells), the cliff keeps its facets
    soft = nn.copy()
    for _ in range(4):
        q = np.pad(soft, ((1, 1), (1, 1), (0, 0)), mode='edge')
        soft = (q[:-2, 1:-1] + q[2:, 1:-1] + q[1:-1, :-2] + q[1:-1, 2:] + 2 * q[1:-1, 1:-1]) / 6
        soft /= np.linalg.norm(soft, axis=2, keepdims=True)
    k = np.clip((TP + 0.4) / 0.8, 0, 1)[..., None]                 # past the ledge's lip the rock keeps its facets
    nn = soft * (1 - k) + nn * k
    nn /= np.linalg.norm(nn, axis=2, keepdims=True)
    slot = {m: i for i, m in enumerate(slot_names)}
    for i in range(nr - 1):
        for j in range(nc - 1):
            f = (i * nc + j, i * nc + j + 1, (i + 1) * nc + j + 1, (i + 1) * nc + j)
            zc = TZ[i:i + 2, j:j + 2].mean()
            m = classify(i, j, zc, steep)
            if m is None:
                continue
            faces.append(f); fm.append(slot[m])
    me = mesh_from('terrain', verts, faces)
    for p, f in zip(me.polygons, fm):
        p.material_index = f
    me.normals_split_custom_set_from_vertices([tuple(v) for v in nn.reshape(-1, 3)])
    return link('terrain', me, [dmat(MAT[m]) for m in slot])



# ------------------------------------------------------------------ things
THINGS = S['things']
occ_n = [0]
OCCMETA = []                                        # per occluder: (index, u, v, z) of its foot, for the draw order


def new_occ(u, v, z, deck=0):
    """a new occluder: its foot (for the runtime's draw order); deck=1 marks a walked-on structure (the bridge),
    drawn over fighters beneath it and under fighters on it"""
    occ_n[0] += 1
    OCCMETA.append((occ_n[0], u, v, z, deck))
    return occ_n[0]

def spruce(k, u, v, h, cls, detail=1.0, g=None, layer='world', mats=None):
    """a spruce of dab cards. `detail` (its zone's budget) scales the dab count down and the dab size up, so a far
    tree is the same mass in fewer, bigger strokes; g = its foot height when it is not on the terrain"""
    oc = new_occ(u, v, ground(u, v)) if layer == 'world' else None
    g = ground(u, v) if g is None else g
    base = U(u, v, g)
    tr = random.Random(1000 + k)
    if layer == 'world':
        cyl(f'trunk{k}', base + Vector((0, 0, -0.3)), base + Vector((0, 0, h * 0.4)), 0.14, dmat(MAT[mats[2] if mats and len(mats) > 2 else 'bark']), oc, seg=6)
    n = int(min(max(round(h / 0.85 * min(1, detail ** 0.5 + 0.3)), 3 if detail < 0.5 else 5), 11))
    lean = Vector((tr.uniform(-.04, .04), tr.uniform(-.04, .04), 0))
    needles, snows = [], []
    sz = (0.26 + 0.035 * h) / max(detail, 0.05) ** 0.5
    dn = lambda c: max(2, int(c * detail))
    for i in range(n):
        f = i / (n - 1)
        zc = h * (0.14 + 0.8 * i / n)
        r = (0.3 * h) * (1 - f) ** 1.05 + 0.18
        cx = base + lean * zc + Vector((0, 0, zc))
        for _ in range(dn(10 + 22 * r * r ** 0.3)):
            a = tr.random() * math.tau; uu = tr.random() ** .35; rr = r * uu
            p = cx + Vector((math.cos(a) * rr, math.sin(a) * rr, -0.55 * h / n * uu ** 1.5 + tr.uniform(-.06, .06)))
            sn = Vector((math.cos(a) * uu * .7, math.sin(a) * uu * .7, .9 - .9 * uu ** 2)).normalized()
            needles.append((p, sz * tr.uniform(.8, 1.2), sn))
        for _ in range(dn(6 + 12 * r)):              # the skirt: dark hanging tips
            a = tr.random() * math.tau; rr = r * tr.uniform(.45, .95)
            p = cx + Vector((math.cos(a) * rr, math.sin(a) * rr, -0.75 * h / n * (rr / r) ** 1.4 - .1 * h / n))
            needles.append((p, sz * .85, Vector((math.cos(a), math.sin(a), -.6)).normalized()))
        for j in range(tr.randint(3, 6) if detail > 0.22 else 2):   # pointed tier ends round the silhouette
            a = tr.random() * math.tau; rr = r * tr.uniform(1.0, 1.18)
            p = cx + Vector((math.cos(a) * rr, math.sin(a) * rr, -0.9 * h / n - tr.uniform(0, .25) * h / n))
            needles.append((p, sz * tr.uniform(.45, .6), Vector((math.cos(a), math.sin(a), -.3)).normalized()))
        for _ in range(dn((8 + 18 * r * r ** 0.3) * min(1.0, 0.3 + detail))):   # the snow shelf on the upper boughs
            if detail < 1 and tr.random() > 0.35 + 0.65 * detail and i % 2:
                continue                                 # sparser shelves: fewer light specks in a calmer tree
            a = tr.random() * math.tau; uu = 0.3 + 0.65 * tr.random() ** .7; rr = r * uu
            p = cx + Vector((math.cos(a) * rr, math.sin(a) * rr, -0.55 * h / n * uu ** 1.5 + 0.1 + 0.06 * h / n))
            sn = Vector((math.cos(a) * uu * .6, math.sin(a) * uu * .6, 1.0)).normalized()
            snows.append((p, sz * tr.uniform(.85, 1.15), sn))
    tip = base + lean * h + Vector((0, 0, h * 0.98))
    for j in range(6 if detail > 0.5 else 2):
        p = tip + Vector((tr.uniform(-.06, .06), tr.uniform(-.06, .06), -j * 0.16 * (h / 6)))
        needles.append((p, sz * (0.35 + 0.1 * j) * min(1, detail * 2), Vector((0, 0, 1))))
    allp = [tuple(p) for p, _, _ in needles + snows]
    alln = [tuple(s) for _, _, s in needles + snows]
    val = card_values(allp, alln, reach=0.9 + 0.08 * h, gradient=0.18, value=0.45, count=10.0)
    nm, sm = (mats or ('needle_' + cls, 'snowc_' + cls))[:2]    # needles, and the shelf on the upper boughs
    cards(f'needles{k}', needles, dmat(MAT[nm], 'dabs', 'card'), val[:len(needles)], occ=oc, layer=layer)
    cards(f'snowc{k}', snows, dmat(MAT[sm], 'puffs', 'card'), val[len(needles):] * 0.3, occ=oc, layer=layer)


def axes(rot_deg):
    """the world grid's axes (x, y), turned by rot degrees: things stand square to the grid"""
    a = math.radians(rot_deg)
    ax = Vector((math.cos(a), math.sin(a), 0)); ay = Vector((-math.sin(a), math.cos(a), 0))
    return ax, ay


def boxes_mesh(name, items, mat, occ=None, bevel=0.05, layer='world'):
    """many boxes in one mesh: items = [(centre (Blender), ax, ay, sx, sy, z0, z1, val)], bevelled, a per-box 'val'
    (the value step between blocks or planks) as a point attribute"""
    bm = bmesh.new()
    vl = bm.verts.layers.float.new('val')
    for (c, ax, ay, sx, sy, z0, z1, val) in items:
        res = bmesh.ops.create_cube(bm, size=1.0)
        for v in res['verts']:
            q = v.co + Vector((.5, .5, .5))
            v.co = Vector((c.x, c.y, 0)) + ax * (q.x - .5) * sx + ay * (q.y - .5) * sy + Vector((0, 0, z0 + (z1 - z0) * q.z))
            v[vl] = val
    if bevel:
        bmesh.ops.bevel(bm, geom=bm.edges[:] + bm.verts[:], offset=bevel, segments=1, affect='EDGES', clamp_overlap=True)
    me = bpy.data.meshes.new(name); bm.to_mesh(me); bm.free()
    for p in me.polygons:
        p.use_smooth = False
    return link(name, me, [mat], occ=occ, layer=layer)


# ------------------------------------------------------------------ the cloud sea round the plateau
def cloud_mass(name, cu, cv, cz, wd, ht, seed, crown_side=True, floor=False, detail=1.0, layer='clouds'):
    """a cumulus mass standing on world (cu, cv, cz), wd metres wide and ht high, after the fp tower: big body clumps
    low, mid clumps up the tower, small crisp puffs only along the upper rim; each clump a disc of puff cards whose
    normal is its sphere seen from the camera, leaning toward the whole mass's (one soft form, the stepped bands
    crossing the cards); a flat shared base; the clumps on the sun's crown (upper left) take the hot pink"""
    cr = random.Random(seed)
    base = U(cu, cv, cz)
    sq0 = 0.55 if floor else 1.0
    env_c = base + Vector((0, 0, ht * 0.45))
    env_rx, env_rz = wd * 0.5, ht * 0.55
    clumps = []
    for i in range(max(2, int(wd / 4.5))):                      # the body
        x = (i + 0.5) / max(2, int(wd / 4.5)) * wd * 0.76 - wd * 0.38 + cr.uniform(-1, 1)
        clumps.append((x, ht * cr.uniform(0.18, 0.34), wd * cr.uniform(0.19, 0.26), 0.85 * sq0))
    if not floor:
        for i in range(max(2, int(wd / 5))):                     # up the tower
            x = cr.uniform(-wd * 0.26, wd * 0.26)
            clumps.append((x, ht * cr.uniform(0.45, 0.72) * (1 - 0.8 * (x / wd) ** 2), wd * cr.uniform(0.13, 0.17), 1.0))
        clumps.append((cr.uniform(-wd * 0.1, wd * 0.06), ht * 0.84, wd * 0.11, 1.0))
    rim_ = []
    for (x, y, r, sq) in clumps if detail > 0.5 else []:
        for _ in range(3 if r > wd * 0.15 else 2):
            a = cr.uniform(0.18 * math.pi, 0.85 * math.pi)
            rim_.append((x + math.cos(a) * r * .9, y + math.sin(a) * r * sq * .9, wd * cr.uniform(.045, .07), 1.0))
    top = max(y + r * sq for x, y, r, sq in clumps)
    zb = cz
    groups = {}
    for (x, y, r, sq) in clumps + rim_:
        c = base + RIGHT * x + Vector((0, 0, y))
        pink = crown_side and (-x / (wd / 2)) * 0.5 + (y + r * sq) / top > 0.96 and r < wd * 0.08
        key = 'pink' if pink else ('cloudfloor' if floor else 'cloud')
        n = max(4, int((8 + 18 * (0.6 + 0.4 * sq)) * detail))
        for _ in range(n):
            a = cr.random() * math.tau; rr = r * 0.62 * cr.random() ** .5
            p = c + RIGHT * math.cos(a) * rr + Vector((0, 0, 1)) * math.sin(a) * rr * sq + VD * cr.gauss(0, 1) * r * .15
            sz = r * 0.52 * cr.uniform(.85, 1.15) / max(detail, 0.3) ** 0.5
            if p.z - sz * .55 < zb:
                p.z = zb + sz * .55

            def sn(q, c=c, r=r, sq=sq):
                o = q - c
                ox, oy = o.dot(RIGHT) / (r * 1.12), (q.z - c.z) / (r * 1.12 * sq)
                t2 = min(ox * ox + oy * oy, 0.94)
                k = math.sqrt(t2) / max(math.sqrt(ox * ox + oy * oy), 1e-4)
                n1 = RIGHT * ox * k + UPS * oy * k + TOCAM * math.sqrt(1 - t2)
                eo = q - env_c
                ex, ey = eo.dot(RIGHT) / env_rx, (q.z - env_c.z) / env_rz
                t3 = min(ex * ex + ey * ey, 0.94)
                k3 = math.sqrt(t3) / max(math.sqrt(ex * ex + ey * ey), 1e-4)
                n2 = RIGHT * ex * k3 + UPS * ey * k3 + TOCAM * math.sqrt(1 - t3)
                n_ = n1 * 0.45 + n2 * 0.55          # more of the whole mass: big soft forms, not popcorn
                bw = min(max((zb + 0.35 * r - q.z) / (0.5 * r), 0.0), 1.0)      # the flat base turns down
                n_ = n_.normalized() * (1 - bw) + (Vector((0, 0, -1)) + TOCAM * 0.45) * bw
                return n_.normalized()
            groups.setdefault(key, []).append((p, sz, sn))
    for key, it in groups.items():
        val = card_values([tuple(p) for p, _, _ in it], [tuple(TOCAM)] * len(it), reach=wd * 0.12, gradient=0.0,
                          value=0.06, count=14.0)
        cards(f'{name}_{key}', it, dmat(MAT[key], 'puffs', 'cloud'), val, layer=layer)


# ------------------------------------------------------------------ the back: backdrop and vista, in forced scale
# (the map's place.scenery(): each layer sunk into its screen band). Simpler geometry the further back: coarse height
# fields under forced-scale trees in fewer, bigger dabs per step back, the cumulus in puff cards. The map's
# build_back() places them; BACKID maps back tree cards to their id in the ids pass (10000 + tree index), for the sway.
SCN = np.load(WORK / 'scenery.npz')


def strip(k, info, mat='far_snow'):
    """a forest ridge's ground: a coarse height field in the far snow, hidden mostly under its trees"""
    Uu, Vv, Zz = SCN[f'{k}_U'], SCN[f'{k}_V'], SCN[f'{k}_Z']
    nr, nc = Uu.shape
    verts = [U(float(Uu[i, j]), float(Vv[i, j]), float(Zz[i, j])) for i in range(nr) for j in range(nc)]
    P = np.dstack([(Uu + Vv) / R2, (Vv - Uu) / R2, Zz])
    du_ = np.gradient(P, axis=1); dv_ = np.gradient(P, axis=0)
    nn = np.cross(du_, dv_); nn /= np.linalg.norm(nn, axis=2, keepdims=True) + 1e-9
    nn *= np.sign(nn[..., 2:3] + 1e-9)
    faces = [(i * nc + j, i * nc + j + 1, (i + 1) * nc + j + 1, (i + 1) * nc + j) for i in range(nr - 1) for j in range(nc - 1)]
    me = mesh_from(f'strip_{info["name"]}', verts, faces)
    me.normals_split_custom_set_from_vertices([tuple(v) for v in nn.reshape(-1, 3)])
    return link(f'strip_{info["name"]}', me, [dmat(MAT[mat])], layer='back')


BACKID = {}
# the ids pass: objects whose cards cut their coverage by the dab / puff alpha (by name); objects that cast no shadow
ID_DABS = ('needles', 'tuft')
ID_PUFFS = ('snowc', 'bank')
ID_EXTRA = {}                                       # prefix -> another alpha atlas (a map's own, e.g. big leaves)
NO_SHADOW = ('rope', 'grass', 'tuft', 'lplamp', 'tlamp', 'hcore', 'icicle')

# ------------------------------------------------------------------ the map's builders, then build
BUILDER = S['builder']
exec(compile(open(BUILDER).read(), BUILDER, 'exec'), globals())
terrain_obj(*TERRAIN)
for k, t in enumerate(THINGS):
    ZONE_NOW[0] = ZCODE[t.get('zone', 'playfield')]
    BUILD[t['kind']](k, t)
ZONE_NOW[0] = 0
print('arena: built', len(sc.objects), 'objects,', occ_n[0], 'occluders', flush=True)
build_back()
ZONE_NOW[0] = 0
print('arena: built the back,', len(sc.objects), 'objects', flush=True)

# ------------------------------------------------------------------ light, camera, render
LIGHT = dict(dict(sun=1.0, fill=0.32, world=0.28), **S.get('light', {}))
sun = bpy.data.lights.new('sun', 'SUN'); sun.energy = math.pi * LIGHT['sun']; sun.angle = math.radians(0.8)
so = bpy.data.objects.new('sun', sun); sc.collection.objects.link(so)
so.rotation_euler = (-SUN).to_track_quat('-Z', 'Y').to_euler()
fill = bpy.data.lights.new('fill', 'SUN'); fill.energy = math.pi * LIGHT['fill']; fill.use_shadow = False
fo = bpy.data.objects.new('fill', fill); sc.collection.objects.link(fo)
fo.rotation_euler = (-FILL).to_track_quat('-Z', 'Y').to_euler()
world = bpy.data.worlds.new('w'); sc.world = world; world.use_nodes = True
world.node_tree.nodes['Background'].inputs[0].default_value = (1, 1, 1, 1)
world.node_tree.nodes['Background'].inputs[1].default_value = LIGHT['world']
cam = bpy.data.cameras.new('cam'); cam.type = 'ORTHO'; cam.sensor_fit = 'HORIZONTAL'
cam.ortho_scale = W / PPM; cam.clip_start = 1; cam.clip_end = 1200
vc = (Y0 - H / 2) / PPM / SE                              # the ground point at the picture's centre
co = bpy.data.objects.new('cam', cam); sc.collection.objects.link(co); sc.camera = co
co.location = U(0, vc, 0) - VD * 200
co.rotation_euler = VD.to_track_quat('-Z', 'Y').to_euler()

sc.render.engine = 'BLENDER_EEVEE_NEXT'
sc.eevee.taa_render_samples = SAMPLES
sc.eevee.use_shadows = True
try:
    sc.eevee.shadow_ray_count = 1; sc.eevee.shadow_step_count = 4
    sc.eevee.shadow_resolution_scale = 1.0
except Exception:
    pass
sc.render.filter_size = 0.0
sc.render.dither_intensity = 0.0
sc.render.film_transparent = True
sc.view_settings.view_transform = 'Raw'
sc.view_settings.look = 'None'
sc.render.resolution_x, sc.render.resolution_y = int(W * SCALE), int(H * SCALE)
st = sc.render.image_settings
st.file_format = 'PNG'; st.color_mode = 'RGBA'; st.color_depth = '16'
(WORK / 'raw').mkdir(exist_ok=True)

# sanity: the projection agrees with arena/place.py
from bpy_extras.object_utils import world_to_camera_view
bpy.context.view_layer.update()
for (u, v, z) in ((0, 0, 0), (10, 5, 2), (-20, -10, 0)):
    q = world_to_camera_view(sc, co, U(u, v, z))
    print('proj check', (u, v, z), 'blender', round(q.x * W, 1), round((1 - q.y) * H, 1), 'place',
          X0 + u * PPM, Y0 - (v * SE + z * CE) * PPM, flush=True)


def idmat(alpha):
    m = bpy.data.materials.new(f'id_{alpha}'); m.use_nodes = True
    N, L = m.node_tree.nodes, m.node_tree.links; N.clear()
    out = N.new('ShaderNodeOutputMaterial')
    oi = N.new('ShaderNodeObjectInfo')
    lo = N.new('ShaderNodeMath'); lo.operation = 'MODULO'; L.new(oi.outputs['Object Index'], lo.inputs[0]); lo.inputs[1].default_value = 256
    lo2 = N.new('ShaderNodeMath'); lo2.operation = 'DIVIDE'; L.new(lo.outputs[0], lo2.inputs[0]); lo2.inputs[1].default_value = 255
    hi = N.new('ShaderNodeMath'); hi.operation = 'DIVIDE'; L.new(oi.outputs['Object Index'], hi.inputs[0]); hi.inputs[1].default_value = 256
    hi2 = N.new('ShaderNodeMath'); hi2.operation = 'FLOOR'; L.new(hi.outputs[0], hi2.inputs[0])
    hi3 = N.new('ShaderNodeMath'); hi3.operation = 'DIVIDE'; L.new(hi2.outputs[0], hi3.inputs[0]); hi3.inputs[1].default_value = 255
    comb = N.new('ShaderNodeCombineRGB'); L.new(lo2.outputs[0], comb.inputs[0]); L.new(hi3.outputs[0], comb.inputs[1])
    zat = N.new('ShaderNodeAttribute'); zat.attribute_type = 'OBJECT'; zat.attribute_name = 'zone'
    zq = N.new('ShaderNodeMath'); zq.operation = 'DIVIDE'; L.new(zat.outputs['Fac'], zq.inputs[0]); zq.inputs[1].default_value = 8
    L.new(zq.outputs[0], comb.inputs[2])
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


for o in sc.objects:
    if o.type == 'MESH' and LAYER.get(o.name) in ('clouds', 'back', 'cfar', 'csea', 'ccorner'):
        o.visible_shadow = False
    if o.type == 'MESH' and o.name.startswith(NO_SHADOW):
        o.visible_shadow = False

for lay in ONLY:
    if lay == 'ids':
        so.hide_render = True
        world.node_tree.nodes['Background'].inputs[1].default_value = 0.0
        sc.eevee.taa_render_samples = 1
        mats = {}
        for o in sc.objects:
            if o.type != 'MESH':
                continue
            o.visible_camera = LAYER.get(o.name) in ('world', 'back')
            o.pass_index = OCC.get(o.name, BACKID.get(o.name, 0))
            al = 'dabs' if o.name.startswith(ID_DABS) else 'puffs' if o.name.startswith(ID_PUFFS) else \
                next((v for k, v in ID_EXTRA.items() if o.name.startswith(k)), None)
            if al not in mats:
                mats[al] = idmat(al)
            for sl in o.material_slots:
                sl.link = 'OBJECT'; sl.material = mats[al]
    else:
        so.hide_render = False
        world.node_tree.nodes['Background'].inputs[1].default_value = LIGHT['world']
        sc.eevee.taa_render_samples = SAMPLES
        for o in sc.objects:
            if o.type == 'MESH':
                o.visible_camera = LAYER.get(o.name) == lay
        for sl_o in sc.objects:
            if sl_o.type == 'MESH' and sl_o.material_slots and \
                    sl_o.material_slots[0].link == 'OBJECT':
                raise SystemExit('arena: render the data layers before ids')
    wide = lay in ('cfar', 'csea')
    sc.render.resolution_x = int((S.get('strip_w', W) if wide else W) * SCALE)
    cam.ortho_scale = (S.get('strip_w', W) if wide else W) / PPM
    sc.render.filepath = str(WORK / 'raw' / f'{lay}.png')
    bpy.ops.render.render(write_still=True)
    img = bpy.data.images.load(sc.render.filepath); img.colorspace_settings.name = 'Non-Color'
    w, h = img.size
    px = np.empty(w * h * 4, np.float32); img.pixels.foreach_get(px)
    np.save(WORK / 'raw' / f'{lay}.npy', px.reshape(h, w, 4)[::-1].astype(np.float32 if lay == 'ids' else np.float16))
    bpy.data.images.remove(img)
    print('arena paint: rendered', lay, flush=True)
json.dump(dict(occluders=occ_n[0], occ=OCCMETA), open(WORK / 'raw' / 'meta.json', 'w'))

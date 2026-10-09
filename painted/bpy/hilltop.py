"""The hilltop film shot (perspective, one hero tree over a valley). Normally `python3 -m painted hilltop`.
blender -b -P painted/bpy/hilltop.py -- TEXDIR OUT.png|OUTDIR W H [pixel] [frames]
The technique: alpha cards scattered in a sphere, every card vertex gets the sphere's normal (so the clump
shades as one ball), diffuse -> Shader to RGB -> stepped colour ramp. Tree crown, forest, grass, flowers and
clouds all use that one painter; trunk, ground, houses use the same ramp shader without cards."""
import bpy, bmesh, sys, math, random
from mathutils import Vector, Matrix, noise

argv = sys.argv[sys.argv.index('--') + 1:]
TEX, OUT, W, H = argv[0], argv[1], int(argv[2]), int(argv[3])
PIXEL = len(argv) > 4 and argv[4] == 'pixel'
FRAMES = int(argv[5]) if len(argv) > 5 else 0
rng = random.Random(11)

bpy.ops.wm.read_factory_settings(use_empty=True)
sc = bpy.context.scene


def lin(h):
    c = [int(h[i:i + 2], 16) / 255 for i in (1, 3, 5)]
    return tuple((v / 12.92 if v <= 0.04045 else ((v + 0.055) / 1.055) ** 2.4) for v in c) + (1.0,)


FOG = '#a9d3dc'
SKY_TOP, SKY_LOW = '#3f93bd', '#c3e4e8'

# ------------------------------------------------------------------ the ramp shader


def toon(name, stops, alpha=None, var=0.08, fog=1.0, streak=0.0, emit_floor=None):
    """stops = [(pos, hex), ...]  lit value -> constant colour bands. alpha = atlas image name.
    var: per-object random shift of the ramp (painterly clump-to-clump variation). fog: aerial perspective."""
    m = bpy.data.materials.new(name); m.use_nodes = True
    nt = m.node_tree; N = nt.nodes; L = nt.links; N.clear()
    out = N.new('ShaderNodeOutputMaterial')
    dif = N.new('ShaderNodeBsdfDiffuse')
    s2r = N.new('ShaderNodeShaderToRGB'); L.new(dif.outputs[0], s2r.inputs[0])
    bw = N.new('ShaderNodeRGBToBW'); L.new(s2r.outputs[0], bw.inputs[0])
    fac = bw.outputs[0]
    # world light is a dim fill; map lit value roughly to 0..1
    mr = N.new('ShaderNodeMapRange'); mr.inputs['From Min'].default_value = 0.0; mr.inputs['From Max'].default_value = 1.0
    L.new(fac, mr.inputs['Value']); fac = mr.outputs[0]
    if var:
        oi = N.new('ShaderNodeObjectInfo')
        mv = N.new('ShaderNodeMapRange'); mv.inputs['To Min'].default_value = -var; mv.inputs['To Max'].default_value = var
        L.new(oi.outputs['Random'], mv.inputs['Value'])
        ad = N.new('ShaderNodeMath'); ad.operation = 'ADD'; L.new(fac, ad.inputs[0]); L.new(mv.outputs[0], ad.inputs[1])
        fac = ad.outputs[0]
    if streak:   # bark / ground: noise stretched along one axis nudges the band edges
        tc = N.new('ShaderNodeTexCoord'); mp = N.new('ShaderNodeMapping')
        mp.inputs['Scale'].default_value = (6, 6, 0.6) if streak > 0 else (0.25, 0.25, 0.25)
        L.new(tc.outputs['Object'], mp.inputs[0])
        nz = N.new('ShaderNodeTexNoise'); nz.inputs['Scale'].default_value = 3.0; nz.inputs['Detail'].default_value = 3
        L.new(mp.outputs[0], nz.inputs[0])
        mz = N.new('ShaderNodeMapRange'); mz.inputs['To Min'].default_value = -abs(streak); mz.inputs['To Max'].default_value = abs(streak)
        mz.inputs['From Min'].default_value = 0.3; mz.inputs['From Max'].default_value = 0.7
        L.new(nz.outputs[0], mz.inputs['Value'])
        ad = N.new('ShaderNodeMath'); ad.operation = 'ADD'; L.new(fac, ad.inputs[0]); L.new(mz.outputs[0], ad.inputs[1])
        fac = ad.outputs[0]
    ramp = N.new('ShaderNodeValToRGB'); ramp.color_ramp.interpolation = 'CONSTANT'
    els = ramp.color_ramp.elements
    els[0].position, els[0].color = 0.0, lin(stops[0][1])
    els[1].position, els[1].color = stops[1][0], lin(stops[1][1])
    for p, h in stops[2:]:
        e = els.new(p); e.color = lin(h)
    L.new(fac, ramp.inputs[0]); col = ramp.outputs[0]
    if fog:
        cam = N.new('ShaderNodeCameraData')
        f1 = N.new('ShaderNodeMath'); f1.operation = 'MULTIPLY'; f1.inputs[1].default_value = -0.0027 * fog
        L.new(cam.outputs['View Z Depth'], f1.inputs[0])
        f2 = N.new('ShaderNodeMath'); f2.operation = 'EXPONENT'; L.new(f1.outputs[0], f2.inputs[0])
        f3 = N.new('ShaderNodeMath'); f3.operation = 'SUBTRACT'; f3.inputs[0].default_value = 1.0; L.new(f2.outputs[0], f3.inputs[1])
        mx = N.new('ShaderNodeMix'); mx.data_type = 'RGBA'
        L.new(f3.outputs[0], mx.inputs[0]); L.new(col, mx.inputs[6]); mx.inputs[7].default_value = lin(FOG)
        col = mx.outputs[2]
    em = N.new('ShaderNodeEmission'); L.new(col, em.inputs[0])
    shader = em.outputs[0]
    if alpha:
        img = bpy.data.images.load(f'{TEX}/{alpha}.png'); img.colorspace_settings.name = 'Non-Color'
        tx = N.new('ShaderNodeTexImage'); tx.image = img; tx.interpolation = 'Closest' if PIXEL else 'Linear'
        gt = N.new('ShaderNodeMath'); gt.operation = 'GREATER_THAN'; gt.inputs[1].default_value = 0.2
        L.new(tx.outputs['Color'], gt.inputs[0])
        tr = N.new('ShaderNodeBsdfTransparent'); mix = N.new('ShaderNodeMixShader')
        L.new(gt.outputs[0], mix.inputs[0]); L.new(tr.outputs[0], mix.inputs[1]); L.new(shader, mix.inputs[2])
        shader = mix.outputs[0]
        if alpha == 'flowers':   # grey stem pixels -> stem colour, white -> petals: second ramp lookup by texture value
            pass
    L.new(shader, out.inputs[0])
    m.surface_render_method = 'DITHERED'
    try: m.use_transparent_shadow = True
    except Exception: pass
    return m


LEAF = [(0, '#163f3c'), (0.2, '#1f5a49'), (0.36, '#2f7d45'), (0.55, '#62b23a'), (0.74, '#a8d84e'), (0.9, '#dcef7a')]
LEAF_FAR = [(0, '#2a5f5a'), (0.3, '#3b7d5c'), (0.55, '#5f9e55'), (0.8, '#9cc66a')]
BARK = [(0, '#172a2e'), (0.32, '#26383a'), (0.58, '#3f4a42'), (0.8, '#6d6a55')]
GRASS = [(0, '#24523a'), (0.3, '#3b7a3e'), (0.55, '#5f9f42'), (0.8, '#a6d160')]
GROUND = [(0, '#24523a'), (0.35, '#356f3f'), (0.6, '#528f42'), (0.82, '#7fb154')]
CLOUD = [(0, '#7ea6c2'), (0.3, '#a9c9da'), (0.55, '#e4f0f3'), (0.75, '#ffffff')]
PINK = [(0, '#b4587a'), (0.4, '#e28aa6'), (0.7, '#f7bfd0')]
WALL = [(0, '#8d8f86'), (0.4, '#c9c2a6'), (0.7, '#efe6c8')]
ROOF = [(0, '#5e2f2c'), (0.4, '#9a4a38'), (0.7, '#c86d4b')]
WATER = [(0, '#6fb2c4'), (0.5, '#9fd3db')]
MOUNT = [(0, '#3a6f7c'), (0.45, '#5d93a0'), (0.75, '#8fbcb8')]

M = dict(leaf=toon('leaf', LEAF, 'leaves', var=0.09), leaf_far=toon('leaf_far', LEAF, 'leaves', var=0.12),
         bark=toon('bark', BARK, var=0.0, streak=0.12), grass=toon('grass', GRASS, 'grass', var=0.0, streak=-0.18),
         pink=toon('pink', PINK, 'flowers', var=0.06), ground=toon('ground', GROUND, var=0.0, streak=-0.1),
         cloud=toon('cloud', CLOUD, 'puffs', var=0.05, fog=0.15), wall=toon('wall', WALL, var=0.05),
         roof=toon('roof', ROOF, var=0.08), water=toon('water', WATER, var=0.0), rope=toon('rope', [(0, '#5a5040'), (0.5, '#c9b88d')], var=0.0), plank=toon('plank', [(0, '#3b3530'), (0.45, '#6b5a45'), (0.7, '#a08460')], var=0.0), mount=toon('mount', MOUNT, var=0.0, fog=0.9))

# ------------------------------------------------------------------ the card painter


def clump_cards(bm, uvl, centre, radius, n, size, up=0.0, squash=1.0, face_cam=None):
    """n alpha cards in a sphere; returns per-loop normals (sphere normal, optionally tilted up)."""
    normals = []
    c = Vector(centre)
    for _ in range(n):
        d = Vector((rng.gauss(0, 1), rng.gauss(0, 1), rng.gauss(0, 1))).normalized()
        r = radius * (0.55 + 0.45 * rng.random() ** 0.5)
        p = c + Vector((d.x * r, d.y * r, d.z * r * squash))
        # card faces roughly outward, randomly spun
        nrm = (d + Vector((rng.uniform(-.6, .6), rng.uniform(-.6, .6), rng.uniform(-.6, .6)))).normalized()
        if face_cam is not None:
            nrm = (nrm * 0.4 + (Vector(face_cam) - p).normalized()).normalized()
        q = nrm.to_track_quat('Z', 'Y') @ Matrix.Rotation(rng.random() * math.tau, 4, 'Z').to_quaternion()
        s = size * rng.uniform(0.75, 1.25)
        vs = [bm.verts.new(p + q @ Vector((x * s, y * s, 0))) for x, y in ((-1, -1), (1, -1), (1, 1), (-1, 1))]
        f = bm.faces.new(vs)
        tile = rng.randrange(4); u0, v0 = (tile % 2) * .5, (tile // 2) * .5
        for lp, (u, v) in zip(f.loops, ((0, 0), (1, 0), (1, 1), (0, 1))):
            lp[uvl].uv = (u0 + u * .5, v0 + v * .5)
        sn = (d + Vector((0, 0, up))).normalized()
        normals += [sn] * 4
    return normals


def blade_cards(name, spots, mat, cam, size=(0.5, 0.9)):
    """upright cards facing the camera, bottom edge on the ground; normals tilt up so tufts shade like the turf."""
    me = bpy.data.meshes.new(name); bm = bmesh.new(); uvl = bm.loops.layers.uv.new(); nrm = []
    if PIXEL:
        spots = spots[::3]; size = (size[0] * 1.7, size[1] * 1.7)
    for x, y in spots:
        z = height(x, y) - .05; s = rng.uniform(*size)
        f = Vector((cam.x - x, cam.y - y, 0)).normalized(); side = Vector((-f.y, f.x, 0)) * s
        b = Vector((x, y, z)); up = Vector((0, 0, s * 1.6))
        vs = [bm.verts.new(q) for q in (b - side, b + side, b + side + up, b - side + up)]
        fc = bm.faces.new(vs); tile = rng.randrange(4); u0, v0 = (tile % 2) * .5, (tile // 2) * .5
        for lp, (u, v) in zip(fc.loops, ((0, 0), (1, 0), (1, 1), (0, 1))):
            lp[uvl].uv = (u0 + u * .5, v0 + v * .5)
        n = Vector((0, 0, .8)) + f * .2 + Vector((rng.uniform(-.75, .75), rng.uniform(-.75, .75), 0))
        nrm += [n.normalized()] * 4
    bm.to_mesh(me); bm.free(); me.normals_split_custom_set(nrm)
    o = bpy.data.objects.new(name, me); o.data.materials.append(mat); sc.collection.objects.link(o)
    return o


def cards_object(name, clumps, mat, **kw):
    """clumps = [(centre, radius, n, size), ...]  One object per clump so Object Info Random varies the ramp."""
    objs = []
    if PIXEL:   # pixel mode: fewer, bigger cards so a leaf mass is a few clean pixels, not speckle
        clumps = [(c, r, max(6, int(n / 2.6)), s * 1.7) for c, r, n, s in clumps]
    for i, (c, r, n, s) in enumerate(clumps):
        me = bpy.data.meshes.new(f'{name}{i}'); bm = bmesh.new(); uvl = bm.loops.layers.uv.new()
        nrm = clump_cards(bm, uvl, c, r, n, s, **kw)
        for v in bm.verts: v.co -= Vector(c)
        bm.to_mesh(me); bm.free()
        me.normals_split_custom_set(nrm)
        o = bpy.data.objects.new(f'{name}{i}', me); o.data.materials.append(mat); o.location = c
        sc.collection.objects.link(o); objs.append(o)
    return objs


def tube(name, pts, radii, mat, res=10):
    cu = bpy.data.curves.new(name, 'CURVE'); cu.dimensions = '3D'; cu.bevel_depth = 1.0; cu.bevel_resolution = 3
    cu.use_fill_caps = True
    sp = cu.splines.new('BEZIER'); sp.bezier_points.add(len(pts) - 1)
    for bp, p, r in zip(sp.bezier_points, pts, radii):
        bp.co = p; bp.radius = r; bp.handle_left_type = bp.handle_right_type = 'AUTO'
    cu.resolution_u = res
    o = bpy.data.objects.new(name, cu); o.data.materials.append(mat); sc.collection.objects.link(o)
    return o


# ------------------------------------------------------------------ terrain


def height(x, y):
    """hilltop plateau near the camera, a long fall into the valley, rolling floor, far ridge."""
    t = min(1, max(0, (y - 26) / 36)); fall = t * t * (3 - 2 * t)
    z = -30 * fall + 1.2 * noise.noise(Vector((x * .05, y * .05, 0)))
    z += -0.012 * (x - 4) ** 2 * (1 - fall) * 0.5           # the hilltop crowns a little
    z += fall * 6 * noise.noise(Vector((x * .012, y * .012, 3)))
    return z


def grid(name, x0, x1, y0, y1, nx, ny, fz, mat):
    me = bpy.data.meshes.new(name); bm = bmesh.new()
    vs = [[bm.verts.new((x0 + (x1 - x0) * i / nx, y0 + (y1 - y0) * j / ny, 0)) for i in range(nx + 1)] for j in range(ny + 1)]
    for v in bm.verts:
        v.co.z = fz(v.co.x, v.co.y)
    for j in range(ny):
        for i in range(nx):
            bm.faces.new((vs[j][i], vs[j][i + 1], vs[j + 1][i + 1], vs[j + 1][i]))
    bm.to_mesh(me); bm.free()
    for p in me.polygons: p.use_smooth = True
    o = bpy.data.objects.new(name, me); o.data.materials.append(mat); sc.collection.objects.link(o)
    return o


grid('ground', -700, 800, -40, 640, 300, 260, height, M['ground'])


def river(x, y):   # the river winds across the valley floor
    return 18 + 22 * math.sin(y * 0.018) + 10 * math.sin(y * 0.041 + 1)


def water_z(x, y):
    return -29.6


me = bpy.data.meshes.new('river'); bm = bmesh.new(); prev = None
for j in range(80):
    y = 55 + j * 4.5; cx = river(0, y); w = 3 + j * 0.06
    a, b = bm.verts.new((cx - w, y, -29.2)), bm.verts.new((cx + w, y, -29.2))
    if prev: bm.faces.new((prev[0], prev[1], b, a))
    prev = (a, b)
bm.to_mesh(me); bm.free()
ro = bpy.data.objects.new('river', me); ro.data.materials.append(M['water']); sc.collection.objects.link(ro)

# far mountains: big smooth ridges, heavy fog
grid('mount', -700, 800, 600, 700, 120, 10,
     lambda x, y: -20 + (1 - (y - 430) / 90) * 0 + 55 * max(0, noise.noise(Vector((x * .006, 1.7, 0))) + .6)
     * min(1, (y - 600) / 30), M['mount'])

# ------------------------------------------------------------------ the great tree

TX, TY = -9.0, 22.0
base = height(TX, TY)
tube('trunk', [(TX, TY, base - 1), (TX + .4, TY, base + 3), (TX - .3, TY + .3, base + 7.5), (TX + .6, TY, base + 10.5)],
     [2.3, 1.55, 1.25, 0.9], M['bark'])
for k in range(7):   # flared roots
    a = k / 7 * math.tau + rng.uniform(-.3, .3)
    L = rng.uniform(2.6, 4.2)
    pts = [(TX + math.cos(a) * .6, TY + math.sin(a) * .6, base + 1.8),
           (TX + math.cos(a) * 1.8, TY + math.sin(a) * 1.8, base + .4),
           (TX + math.cos(a) * L, TY + math.sin(a) * L, height(TX + math.cos(a) * L, TY + math.sin(a) * L) - .3)]
    tube(f'root{k}', pts, [1.2, .7, .15], M['bark'])

crown_c = Vector((TX + 2.0, TY + 1.0, base + 15.0))
clumps = []
for i in range(30):
    d = Vector((rng.gauss(0, 1), rng.gauss(0, 1) * .8, rng.gauss(0, 1) * .55)).normalized()
    r = rng.uniform(0.55, 1.0)
    c = crown_c + Vector((d.x * 12 * r, d.y * 8 * r, d.z * 7 * r))
    if c.z < base + 9: c.z = base + 9 + rng.random() * 1.5
    clumps.append((c, rng.uniform(3.4, 5.0), 230, 0.95))
# branches from the trunk top to the inner clumps (they read in the holes of the crown)
top = Vector((TX + .6, TY, base + 10.5))
for i, (c, r, n, s) in enumerate(sorted(clumps, key=lambda q: (q[0] - top).length)[:12]):
    mid = top.lerp(c, .5) + Vector((0, 0, 1.2))
    tube(f'branch{i}', [top, mid, c], [.75, .45, .12], M['bark'], res=6)
# low hanging clumps make the silhouette feel heavy, like an old camphor tree
for i in range(5):
    a = rng.uniform(-1, 1) * 1.4 + (0 if i % 2 else math.pi)
    c = Vector((TX + math.cos(a) * 11, TY + math.sin(a) * 6, base + 8.5 + rng.random() * 2))
    clumps.append((c, rng.uniform(2.6, 3.6), 150, 0.85))
    tube(f'limb{i}', [top - Vector((0, 0, 2)), top.lerp(c, .5) + Vector((0, 0, .6)), c], [.6, .35, .1], M['bark'], res=6)
CROWN = cards_object('crown', clumps, M['leaf'])
SW = Vector((TX + 4.2, TY - 1.0, base + 7.6))
tube('swing_limb', [top - Vector((0, 0, 3.2)), SW + Vector((-.8, 0, .4)), SW + Vector((1.6, 0, -.1))], [.55, .32, .12], M['bark'], res=6)
PIVOT = bpy.data.objects.new('pivot', None); PIVOT.location = SW; sc.collection.objects.link(PIVOT)
SWING = []
for dx in (-.45, .45):
    SWING.append(tube('rope', [SW + Vector((dx, 0, 0)), SW + Vector((dx, 0, -3.3)), SW + Vector((dx, 0, -6.4))], [.04, .04, .04], M['rope'], res=2))
bpy.ops.mesh.primitive_cube_add(size=1, location=SW + Vector((0, 0, -6.45)))
pl = bpy.context.active_object; pl.scale = (1.3, .42, .1); pl.data.materials.append(M['plank']); SWING.append(pl)

# ------------------------------------------------------------------ the valley forest (same painter, smaller)
far = []
for i in range(1100):
    x, y = rng.uniform(-200, 300), rng.uniform(30, 600)
    if noise.noise(Vector((x * .02, y * .02, 5))) < -0.05: continue
    if abs(x - river(0, y)) < 9: continue
    if 165 < y < 245 and abs(x - river(0, 200)) < 42 and rng.random() < .9: continue    # the village clearing
    z = height(x, y)
    s = rng.uniform(1.6, 3.2) * (1 + (y - 30) / 300)
    for k in range(rng.randint(1, 3)):
        far.append(((x + rng.uniform(-s, s), y + rng.uniform(-s, s), z + s * (.9 + k * .5)), s * rng.uniform(.8, 1.1),
                    28, s * .45))
cards_object('forest', far, M['leaf_far'])

# hill-edge bushes on the plateau rim, framing the drop
rim = []
for i in range(26):
    x = rng.uniform(-45, 50); y = rng.uniform(30, 38); z = height(x, y)
    if abs(x - 4) < 9: continue
    s = rng.uniform(1.4, 2.6); rim.append(((x, y, z + s * .6), s, 90, .55))
cards_object('rim', rim, M['leaf'])

# ------------------------------------------------------------------ village


def house(x, y, w, d, h, rot):
    z = height(x, y)
    bpy.ops.mesh.primitive_cube_add(size=1, location=(x, y, z + h / 2))
    b = bpy.context.active_object; b.scale = (w, d, h); b.rotation_euler.z = rot; b.data.materials.append(M['wall'])
    me = bpy.data.meshes.new('roof'); bm = bmesh.new()
    o = .25
    p = [(-w / 2 - o, -d / 2 - o, h), (w / 2 + o, -d / 2 - o, h), (w / 2 + o, d / 2 + o, h), (-w / 2 - o, d / 2 + o, h),
         (-w / 2 - o, 0, h + w * .45), (w / 2 + o, 0, h + w * .45)]
    v = [bm.verts.new(q) for q in p]
    bm.faces.new((v[0], v[1], v[5], v[4])); bm.faces.new((v[3], v[4], v[5], v[2]))
    bm.faces.new((v[0], v[4], v[3])); bm.faces.new((v[1], v[2], v[5]))
    bm.to_mesh(me); bm.free()
    r = bpy.data.objects.new('roof', me); r.location = (x, y, z); r.rotation_euler.z = rot
    r.data.materials.append(M['roof']); sc.collection.objects.link(r)


for i in range(46):
    x, y = rng.uniform(river(0, 200) - 34, river(0, 200) + 30), rng.uniform(175, 235)
    if abs(x - river(0, y)) < 6: continue
    house(x, y, rng.uniform(4, 6.5), rng.uniform(3, 4.4), rng.uniform(2.6, 3.8), rng.choice((0, .2, 1.57, 1.4)))

# ------------------------------------------------------------------ foreground grass + flowers (cards again)
CAM = Vector((7.0, -6.0, 8.5))
LOOK = Vector((2.0, 90.0, -8.5))
spots = [(rng.uniform(-34, 40), rng.uniform(-3, 34)) for _ in range(17000)]
blade_cards('grass', [p for p in spots if (Vector((p[0], p[1], 0)) - CAM.xy.to_3d()).length > 3], M['grass'], CAM, size=(.3, .65))
pinks = []
for k in range(5):   # flower drifts
    cx, cy = rng.uniform(-24, 36), rng.uniform(2, 26)
    pinks += [(cx + rng.gauss(0, 2.5), cy + rng.gauss(0, 1.2)) for _ in range(90)]
blade_cards('flowers', pinks, M['pink'], CAM, size=(.35, .6))

# ------------------------------------------------------------------ clouds (cards again)
CLOUDS = [(120, 780, 55), (470, 760, 95), (-200, 820, 150), (760, 840, 170)]
for k, (cx, cy, cz) in enumerate(CLOUDS):
    cy += 0
    puffs = []
    n = rng.randint(14, 20)
    for j in range(n):   # flat base, towering middle
        u = rng.uniform(-1, 1)
        puffs.append(((cx + u * 110, cy + rng.uniform(-20, 20), cz + (1 - u * u) * rng.uniform(0, 70)),
                      rng.uniform(20, 34) * (1.15 - abs(u) * .4), 80, 16))
    CLOUD_OBJS = globals().setdefault('CLOUD_OBJS', [])
    CLOUD_OBJS += cards_object(f'cloud{k}_', puffs, M['cloud'], squash=.75, face_cam=CAM)

# ------------------------------------------------------------------ light, sky, camera
sun = bpy.data.lights.new('sun', 'SUN'); sun.energy = 5.2; sun.angle = math.radians(2)
so = bpy.data.objects.new('sun', sun); sc.collection.objects.link(so)
so.rotation_euler = Vector((-0.68, 0.36, -0.64)).to_track_quat('-Z', 'Y').to_euler()
world = bpy.data.worlds.new('w'); sc.world = world; world.use_nodes = True
wn = world.node_tree.nodes; wl = world.node_tree.links; wn.clear()
wo = wn.new('ShaderNodeOutputWorld'); lp = wn.new('ShaderNodeLightPath')
tc = wn.new('ShaderNodeTexCoord'); sep = wn.new('ShaderNodeSeparateXYZ'); wl.new(tc.outputs['Generated'], sep.inputs[0])
gr = wn.new('ShaderNodeValToRGB'); gr.color_ramp.elements[0].color = lin(SKY_LOW); gr.color_ramp.elements[0].position = 0.0
gr.color_ramp.elements[1].color = lin(SKY_TOP); gr.color_ramp.elements[1].position = 0.45
wl.new(sep.outputs['Z'], gr.inputs[0])
bgs = wn.new('ShaderNodeBackground'); wl.new(gr.outputs[0], bgs.inputs[0])
amb = wn.new('ShaderNodeBackground'); amb.inputs[0].default_value = (1, 1, 1, 1); amb.inputs[1].default_value = 0.22
mx = wn.new('ShaderNodeMixShader'); wl.new(lp.outputs['Is Camera Ray'], mx.inputs[0])
wl.new(amb.outputs[0], mx.inputs[1]); wl.new(bgs.outputs[0], mx.inputs[2]); wl.new(mx.outputs[0], wo.inputs[0])

cam = bpy.data.cameras.new('cam'); cam.lens = 22
co = bpy.data.objects.new('cam', cam); sc.collection.objects.link(co); sc.camera = co
co.location = CAM
co.rotation_euler = (LOOK - CAM).to_track_quat('-Z', 'Y').to_euler()
cam.clip_end = 2000

sc.render.engine = 'BLENDER_EEVEE_NEXT'
sc.eevee.taa_render_samples = 1 if PIXEL else 32
sc.eevee.shadow_ray_count = 1
sc.eevee.use_shadows = True
sc.render.filter_size = 0.0 if PIXEL else 1.0
sc.render.resolution_x, sc.render.resolution_y, sc.render.resolution_percentage = W, H, 100
sc.view_settings.view_transform = 'Standard'
sc.render.image_settings.file_format = 'PNG'
for o in SWING:
    mw = o.matrix_world.copy(); o.parent = PIVOT; o.matrix_parent_inverse = PIVOT.matrix_world.inverted(); o.matrix_world = mw
if not FRAMES:
    sc.render.filepath = OUT
    bpy.ops.render.render(write_still=True)
else:
    base_loc = {o.name: o.location.copy() for o in CROWN + CLOUD_OBJS}
    ph = {o.name: (rng.random() * math.tau, rng.uniform(.6, 1.3)) for o in CROWN}
    for f in range(FRAMES):
        t = f / FRAMES * math.tau
        for o in CROWN:   # gust: whole crown leans, each clump nods on its own phase; integer cycles keep the loop seamless
            p, a = ph[o.name]; h = (o.location.z - base) / 20
            o.rotation_euler = (math.radians(1.6 * a * math.sin(t * 2 + p)), math.radians(2.2 * a * math.sin(t + p * .5)), 0)
            o.location = base_loc[o.name] + Vector((0.35 * h * math.sin(t) + .12 * math.sin(t * 2 + p), 0, .06 * math.sin(t * 3 + p)))
        PIVOT.rotation_euler.y = math.radians(9 * math.sin(t))
        PIVOT.rotation_euler.x = math.radians(4 * math.sin(t * 2 + 1))
        for o in CLOUD_OBJS:
            o.location = base_loc[o.name] + Vector((6 * math.sin(t), 0, 0))
        sc.render.filepath = f'{OUT}/f{f:03d}.png'
        bpy.ops.render.render(write_still=True)
print('rendered', OUT)

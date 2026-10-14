"""Hushfall Crossing's Blender builders. Executed by arena/blender/arena.py in its own namespace (every kit helper is
in scope: U, ground, dmat, blob, box, frame_box, cyl, cards, card_values, spruce, cloud_mass, strip, MAT, ZCODE,
DETAIL, rng ...). Defines TERRAIN, BUILD and build_back().

The camps (palisade stakes, tents, watchtowers, hearts, fires, banners, crates, woodpiles), the ruin terrace and the
overlook (dressed blocks in courses, kerbs, cornices of snow, parapet stubs, toppled blocks, broken columns), the
timber bridge and its lamps, rocks; the spruce ring; the far forest ridges and the cumulus.
"""


def terrain_classify(i, j, zc, steep):
    if zc < -S['CLIFF'] + 1.5 and TP[i, j] > 3.0:
        return None                                   # the cliff's foot, lost in the fog
    if steep[i:i + 2, j:j + 2].mean() > 0.5 or zc < -1.4:
        return 'cliff'
    if TL[i:i + 2, j:j + 2].mean() < 1.15 and TQ[i, j] < -1.0:
        return 'path'
    return 'snow'


TERRAIN = (('snow', 'path', 'cliff'), terrain_classify)


def rock(k, t):
    oc = new_occ(t['u'], t['v'], ground(t['u'], t['v']))
    u, v, r = t['u'], t['v'], t['r']
    g = ground(u, v)
    rr = random.Random(t['seed'])
    c = U(u, v, g + r * 0.15)
    blob(f'rock{k}', c, r * 1.15, r * 0.95, r * 0.75, dmat(MAT['rock']), oc, seg=18, rot=rr.uniform(0, 3), noise=0.16,
         seed=t['seed'], flat=0.4, mass=0.35)
    for j in range(rr.randint(1, 2)):                # a second stone leaning on it
        a = rr.uniform(0, 6.28)
        c2 = c + Vector((math.cos(a) * r * 0.9, math.sin(a) * r * 0.9, -r * 0.25))
        blob(f'rock{k}b{j}', c2, r * 0.6, r * 0.5, r * 0.45, dmat(MAT['rock']), oc, seg=14, rot=a, noise=0.18,
             seed=t['seed'] + j + 1, flat=0.3, mass=0.35)
    capped(lambda: blob(f'rockcap{k}', c + Vector((0, 0, r * 0.52)), r * 0.85, r * 0.7, r * 0.22, dmat(MAT['cap']), oc,
                        seg=14, rot=rr.uniform(0, 3), noise=0.08, seed=t['seed'] + 7))
    blob(f'rockfoot{k}', U(u, v, g - 0.05), r * 1.5, r * 1.3, 0.3, dmat(MAT['pillow']), None, seg=14)


def stake(k, t):
    oc = new_occ(t['u'], t['v'], ground(t['u'], t['v']))
    u, v, h = t['u'], t['v'], t['h']
    g = ground(u, v)
    a = U(u, v, g - 0.4)
    ln = math.radians(t['lean'])
    b = a + Vector((math.sin(ln) * 0.4, 0, h + 0.4))
    cyl(f'stake{k}', a, b, 0.19, dmat(MAT['wood']), oc, seg=7)
    cyl(f'stakep{k}', b, b + Vector((0, 0, 0.45)), 0.19, dmat(MAT['wood']), oc, seg=7, r2=0.02)
    blob(f'stakesn{k}', U(u, v, g), 0.38, 0.38, 0.22, dmat(MAT['pillow']), None, seg=10)


def tent(k, t):
    oc = new_occ(t['u'], t['v'], ground(t['u'], t['v']))
    u, v = t['u'], t['v']
    g = ground(u, v)
    ax, ay = axes(t['rot'])
    c = U(u, v, g)
    L_, Wd, Ht = 3.4, 2.7, 2.3
    pts = [c + ax * (s * L_ / 2) + ay * (w * Wd / 2) for s in (-1, 1) for w in (-1, 1)]
    ridge = [c + ax * (s * (L_ / 2 + 0.2)) + Vector((0, 0, Ht)) for s in (-1, 1)]
    canvas = dmat(MAT['canvas_' + t['side']])
    verts = [pts[0], pts[1], pts[2], pts[3], ridge[0], ridge[1]]
    faces = [(0, 2, 5, 4), (3, 1, 4, 5), (0, 4, 1), (2, 3, 5)]
    me = mesh_from(f'tent{k}', verts, faces, smooth_=False)
    link(f'tent{k}', me, [canvas], occ=oc)
    # a door flap (darker) on the end facing the field, a team stripe along the ridge, snow along the ridge
    trim = dmat(MAT['trim'])
    e = ridge[1] if True else ridge[0]
    cyl(f'tentridge{k}', ridge[0] + Vector((0, 0, 0.05)), ridge[1] + Vector((0, 0, 0.05)), 0.12, trim, oc, seg=6)
    for s in (-1, 1):
        pole = c + ax * (s * (L_ / 2 + 0.25))
        cyl(f'tentpole{k}{s}', pole + Vector((0, 0, -0.2)), pole + Vector((0, 0, Ht + 0.45)), 0.06, dmat(MAT['wood_dk']), oc, seg=5)
    for j in range(5):
        p = ridge[0].lerp(ridge[1], (j + .5) / 5)
        capped(lambda: blob(f'tentsnow{k}_{j}', p + Vector((0, 0, 0.02)), 0.55, 0.35, 0.16, dmat(MAT['cap']), oc, seg=10,
                            rot=math.radians(t['rot'])))
    blob(f'tentbank{k}', c, L_ * 0.62, Wd * 0.62, 0.28, dmat(MAT['pillow']), None, seg=16, rot=math.radians(t['rot']))
    del e


def tower(k, t):
    oc = new_occ(t['u'], t['v'], ground(t['u'], t['v']))
    u, v = t['u'], t['v']
    g = ground(u, v)
    c = U(u, v, g)
    ax, ay = axes(0)
    hh, s = 4.6, 1.0
    wood, wdk = dmat(MAT['wood']), dmat(MAT['wood_dk'])
    for i in (-1, 1):
        for j in (-1, 1):
            a = c + ax * i * s * 1.1 + ay * j * s * 1.1 + Vector((0, 0, -0.3))
            b = c + ax * i * s * 0.85 + ay * j * s * 0.85 + Vector((0, 0, hh))
            cyl(f'tleg{k}{i}{j}', a, b, 0.13, wood, oc, seg=6)
    for zz in (1.4, 2.9):                                # cross braces
        for i in (-1, 1):
            a = c + ax * i * 1.0 + ay * -1.0 + Vector((0, 0, zz)); b = c + ax * i * 0.95 + ay * 1.0 + Vector((0, 0, zz + 1.1))
            cyl(f'tbr{k}{zz}{i}a', a, b, 0.07, wdk, oc, seg=5)
            a = c + ay * i * 1.0 + ax * -1.0 + Vector((0, 0, zz)); b = c + ay * i * 0.95 + ax * 1.0 + Vector((0, 0, zz + 1.1))
            cyl(f'tbr{k}{zz}{i}b', a, b, 0.07, wdk, oc, seg=5)
    frame_box(f'tplat{k}', c, ax, ay, 2.6, 2.6, hh, hh + 0.22, wood, oc, bevel=0.04)
    for i in (-1, 1):                                    # the parapet
        frame_box(f'tpar{k}{i}a', c + ax * i * 1.22, ax, ay, 0.16, 2.6, hh + 0.2, hh + 1.0, wood, oc)
        frame_box(f'tpar{k}{i}b', c + ay * i * 1.22, ax, ay, 2.6, 0.16, hh + 0.2, hh + 1.0, wood, oc)
    for i in (-1, 1):
        for j in (-1, 1):
            a = c + ax * i * 1.15 + ay * j * 1.15 + Vector((0, 0, hh))
            cyl(f'tpost{k}{i}{j}', a, a + Vector((0, 0, 2.0)), 0.07, wdk, oc, seg=5)
    # the roof: a four-sided cone under snow, and the team's trim along its eaves
    bm = bmesh.new()
    bmesh.ops.create_cone(bm, cap_ends=True, segments=4, radius1=2.25, radius2=0.05, depth=2.3)
    me = bpy.data.meshes.new(f'troof{k}'); bm.to_mesh(me); bm.free()
    Rz = Matrix.Rotation(math.pi / 4, 4, 'Z')
    for vt in me.vertices:
        vt.co = c + Vector((0, 0, hh + 2.0 + 1.15)) + (Rz @ vt.co.to_4d()).to_3d()
    for p in me.polygons:
        p.use_smooth = False
    link(f'troof{k}', me, [dmat(MAT['cap'])], occ=oc)
    frame_box(f'teave{k}', c, ax, ay, 3.05, 3.05, hh + 1.92, hh + 2.06, dmat(MAT['trim']), oc)
    # a lantern hanging under the roof
    blob(f'tlamp{k}', c + Vector((0, 0, hh + 1.55)), 0.22, 0.22, 0.28, dmat(MAT['lamp'], kind='flat'), oc, seg=8)
    blob(f'tbank{k}', c, 1.6, 1.6, 0.25, dmat(MAT['pillow']), None, seg=14)


def heart(k, t):
    oc = new_occ(t['u'], t['v'], ground(t['u'], t['v']))
    u, v = t['u'], t['v']
    g = ground(u, v)
    c = U(u, v, g)
    ax, ay = axes(0)
    frame_box(f'hplinth{k}', c, ax, ay, 1.5, 1.5, -0.3, 0.7, dmat(MAT['rock']), oc, bevel=0.1)
    frame_box(f'hplinth2{k}', c, ax, ay, 1.1, 1.1, 0.7, 1.0, dmat(MAT['rock']), oc, bevel=0.06)
    # the great lantern: a dark iron cage round a glowing core, a cap with a ring
    for i in (-1, 1):
        for j in (-1, 1):
            a = c + ax * i * .42 + ay * j * .42 + Vector((0, 0, 1.0))
            cyl(f'hbar{k}{i}{j}', a, a + Vector((0, 0, 1.25)), 0.06, dmat(MAT['metal']), oc, seg=5)
    blob(f'hcore{k}', c + Vector((0, 0, 1.62)), 0.38, 0.38, 0.55, dmat(MAT['lamp'], kind='flat'), oc, seg=12)
    frame_box(f'hcap{k}', c, ax, ay, 1.15, 1.15, 2.25, 2.42, dmat(MAT['metal']), oc, bevel=0.05)
    bm = bmesh.new()
    bmesh.ops.create_cone(bm, cap_ends=True, segments=4, radius1=0.78, radius2=0.08, depth=0.6)
    me = bpy.data.meshes.new(f'hroof{k}'); bm.to_mesh(me); bm.free()
    Rz = Matrix.Rotation(math.pi / 4, 4, 'Z')
    for vt in me.vertices:
        vt.co = c + Vector((0, 0, 2.72)) + (Rz @ vt.co.to_4d()).to_3d()
    link(f'hroof{k}', me, [dmat(MAT['trim'])], occ=oc)
    blob(f'hbank{k}', c, 1.4, 1.4, 0.3, dmat(MAT['pillow']), None, seg=14)


def fire(k, t):
    u, v = t['u'], t['v']
    g = ground(u, v)
    c = U(u, v, g)
    for i in range(8):
        a = i / 8 * math.tau
        blob(f'fstone{k}{i}', c + Vector((math.cos(a) * .62, math.sin(a) * .62, 0.05)), .2, .17, .15, dmat(MAT['rock']),
             None, seg=8, rot=a)
    for i in range(3):
        a = i / 3 * math.tau + .4
        cyl(f'flog{k}{i}', c + Vector((math.cos(a) * .45, math.sin(a) * .45, 0.05)), c + Vector((0, 0, 0.45)), 0.07,
            dmat(MAT['wood_dk']), None, seg=5)
    blob(f'fash{k}', c + Vector((0, 0, 0.02)), .45, .45, .05, dmat(MAT['hearth']), None, seg=10)


def banner(k, t):
    oc = new_occ(t['u'], t['v'], ground(t['u'], t['v']))
    u, v = t['u'], t['v']
    g = ground(u, v)
    a = U(u, v, g - 0.3)
    cyl(f'bpole{k}', a, a + Vector((0, 0, 5.2)), 0.08, dmat(MAT['wood_dk']), oc, seg=6)
    blob(f'bknob{k}', a + Vector((0, 0, 5.55)), .14, .14, .14, dmat(MAT['trim']), oc, seg=8)
    blob(f'bfoot{k}', U(u, v, g), .5, .5, .25, dmat(MAT['pillow']), None, seg=10)


def crates(k, t):
    oc = new_occ(t['u'], t['v'], ground(t['u'], t['v']))
    u, v = t['u'], t['v']
    g = ground(u, v)
    c = U(u, v, g)
    ax, ay = axes(0)
    for (dx, dy, dz, s) in ((0, 0, 0, .9), (.95, .1, 0, .8), (.35, .1, .9, .7)):
        cc = c + ax * dx + ay * dy
        frame_box(f'crate{k}{dx}{dz}', cc, ax, ay, s, s, dz - 0.05, dz + s, dmat(MAT['wood']), oc, bevel=0.04)
        blob(f'cratesn{k}{dx}{dz}', cc + Vector((0, 0, dz + s)), s * .45, s * .45, .08, dmat(MAT['pillow']), oc, seg=10)


def woodpile(k, t):
    oc = new_occ(t['u'], t['v'], ground(t['u'], t['v']))
    u, v = t['u'], t['v']
    g = ground(u, v)
    c = U(u, v, g)
    ax, ay = axes(t['rot'])
    for row, n in ((0, 4), (1, 3), (2, 2)):
        for i in range(n):
            off = (i - (n - 1) / 2) * 0.34
            p = c + ay * off + Vector((0, 0, 0.17 + row * 0.29))
            cyl(f'wp{k}{row}{i}', p - ax * 0.75, p + ax * 0.75, 0.16, dmat(MAT['bark']), oc, seg=7)
    blob(f'wpsn{k}', c + Vector((0, 0, 0.92)), .8, .42, .12, dmat(MAT['pillow']), oc, seg=10, rot=math.radians(t['rot']))


def altar(k, t):
    oc = new_occ(t['u'], t['v'], ground(t['u'], t['v']))
    c = U(t['u'], t['v'], ground(t['u'], t['v']))
    ax, ay = axes(0)
    frame_box(f'alt{k}', c, ax, ay, 1.6, 1.6, -0.2, 0.32, dmat(MAT['rock']), oc, bevel=0.12)
    frame_box(f'alt2{k}', c, ax, ay, 1.0, 1.0, 0.3, 0.55, dmat(MAT['rock_top']), oc, bevel=0.08)


def menhir(k, t):
    oc = new_occ(t['u'], t['v'], ground(t['u'], t['v']))
    u, v, h = t['u'], t['v'], t['h']
    g = ground(u, v)
    c = U(u, v, g)
    ax, ay = axes(t['rot'])
    lean = random.Random(k).uniform(-.12, .12)
    box(f'men{k}', lambda q: c + ax * (q.x - .5) * (0.95 - 0.35 * q.z) + ay * (q.y - .5) * (0.62 - 0.18 * q.z)
        + Vector((lean * q.z * h, 0, -0.3 + q.z * (h + 0.3))), dmat(MAT['rock']), oc, bevel=0.1, seg=2)
    blob(f'mencap{k}', c + Vector((lean * h, 0, h - 0.05)), .33, .24, .1, dmat(MAT['pillow']), oc, seg=10, rot=math.radians(t['rot']))
    blob(f'menfoot{k}', c, .7, .6, .22, dmat(MAT['pillow']), None, seg=10)


def capped(build):
    """build snow lying on the ruin in the playfield's zone: the light snow of the top it belongs to"""
    was, ZONE_NOW[0] = ZONE_NOW[0], ZCODE['playfield']
    o = build()
    ZONE_NOW[0] = was
    return o


def tangent(nu, nv):
    """(along the edge, out of it) as Blender vectors for an outward normal (nu, nv)"""
    return U(-nv, nu, 0).normalized(), U(nu, nv, 0).normalized()


def ruin(k, t):
    """the terraces' faces: courses of dressed blocks in running bond, each a little proud or sunk and twisted, a value
    step of its own; a gappy kerb of single blocks on the lip; a cornice of drifted snow along the top"""
    br = random.Random(400 + k)

    def lay(items, b, zoff=0.0):
        d, n = tangent(b['nu'], b['nv'])
        a = math.radians(b['tw'])
        d, n = Matrix.Rotation(a, 3, 'Z') @ d, Matrix.Rotation(a, 3, 'Z') @ n
        c = U(b['u'], b['v'], 0) + n * (b['dep'] / 2 - 0.32 + b.get('out', 0.0))
        items.append((c, d, n, b['len'], b['dep'], b['z0'], b['z1'], b['val']))
        return c, d
    items = []
    for b in t['blocks']:
        lay(items, b)
    boxes_mesh(f'ruin{k}', items, dmat(MAT['masonry']), None, bevel=0.06)
    # the kerb: each block its own occluder (units on the terrace pass in front of it, units below behind it)
    for i, b in enumerate(t['kerb']):
        oc = new_occ(b['u'], b['v'], b['z0'])
        it = []
        c, d = lay(it, b)
        boxes_mesh(f'kerb{k}_{i}', it, dmat(MAT['masonry']), oc, bevel=0.05)
        if br.random() < 0.8:
            capped(lambda: blob(f'kerbcap{k}_{i}', c + Vector((0, 0, b['z1'] + 0.01)), b['len'] * 0.45, 0.24,
                                0.08 + 0.04 * br.random(), dmat(MAT['cap']), oc, seg=10, rot=math.atan2(d.y, d.x),
                                noise=0.1, seed=i))
    for i, c_ in enumerate(t['cornice']):
        d, n = tangent(c_['nu'], c_['nv'])
        capped(lambda: blob(f'cornice{k}_{i}', U(c_['u'], c_['v'], c_['z']) + n * 0.12, c_['len'] * 0.5, 0.48, c_['h'],
                            dmat(MAT['cap']), None, seg=12, rot=math.atan2(d.y, d.x), noise=0.14, seed=50 + i, mass=0.3))


def column(k, t):
    """a broken column: two or three drums, the top one tipped, the break under snow"""
    oc = new_occ(t['u'], t['v'], ground(t['u'], t['v']))
    sr = random.Random(t['seed'])
    g = ground(t['u'], t['v'])
    c = U(t['u'], t['v'], g)
    z, r = -0.2, 0.42
    n = max(1, int(round(t['h'] / 0.7)))
    for i in range(n):
        hh = t['h'] / n * sr.uniform(0.92, 1.05)
        off = Vector((sr.uniform(-.05, .05), sr.uniform(-.05, .05), 0)) * i
        cyl(f'col{k}_{i}', c + off + Vector((0, 0, z)), c + off + Vector((0, 0, z + hh - 0.03)), r * (1 - 0.04 * i),
            dmat(MAT['masonry']), oc, seg=10)
        z += hh
    capped(lambda: blob(f'colcap{k}', c + Vector((0, 0, z)), r * 1.05, r * 1.0, 0.14, dmat(MAT['cap']), oc, seg=10,
                        noise=0.12, seed=k))
    blob(f'colbank{k}', c, 0.9, 0.8, 0.3, dmat(MAT['pillow']), None, seg=12, mass=0.3)
    # a fallen drum beside it
    a = sr.uniform(0, 6.28)
    p0 = c + Vector((math.cos(a) * 1.0, math.sin(a) * 1.0, 0.25))
    dd = Vector((math.cos(a + 1.4), math.sin(a + 1.4), 0)) * 0.35
    cyl(f'coldrum{k}', p0 - dd, p0 + dd, r * 0.95, dmat(MAT['masonry']), oc, seg=10)
    capped(lambda: blob(f'coldrumsn{k}', p0 + Vector((0, 0, r * 0.8)), 0.4, 0.3, 0.1, dmat(MAT['cap']), oc, seg=8, rot=a))


def stub(k, t):
    """a broken run of parapet on a terrace's lip: two or three blocks, stepped down at the break, snow on top"""
    sr = random.Random(t['seed'])
    d, n = tangent(t['nu'], t['nv'])
    g = t['z']
    nb = max(1, int(round(t['len'] / 0.8)))
    oc = new_occ(t['u'], t['v'], g)
    items = []
    for i in range(nb):
        f = (i + 0.5) / nb - 0.5
        hh = t['h'] * (1.0 - 0.45 * i / max(1, nb - 1)) * sr.uniform(0.85, 1.05)
        c = U(t['u'], t['v'], 0) + d * f * t['len']
        items.append((c, d, n, t['len'] / nb * 0.96, 0.55, g - 0.2, g + hh, sr.uniform(-0.1, 0.1)))
        capped(lambda: blob(f'stubcap{k}_{i}', c + Vector((0, 0, g + hh + 0.02)), t['len'] / nb * 0.5, 0.32, 0.1,
                            dmat(MAT['cap']), oc, seg=8, rot=math.atan2(d.y, d.x)))
    boxes_mesh(f'stub{k}', items, dmat(MAT['masonry']), oc, bevel=0.05)
    blob(f'stubbank{k}', U(t['u'], t['v'], g) - n * 0.35, t['len'] * 0.55, 0.6, 0.2, dmat(MAT['pillow']), None, seg=12,
         rot=math.atan2(d.y, d.x))


def block(k, t):
    """a toppled block at a terrace's foot: tipped, half sunk in a drift"""
    oc = new_occ(t['u'], t['v'], ground(t['u'], t['v']))
    sr = random.Random(t['seed'])
    u, v = t['u'], t['v']
    g = ground(u, v)
    ax, ay = axes(t['rot'])
    tip = Matrix.Rotation(math.radians(sr.uniform(12, 28)), 3, ax)
    c = U(u, v, g)
    L_, Wd, Hh = sr.uniform(1.1, 1.4), sr.uniform(0.7, 0.85), sr.uniform(0.6, 0.75)
    box(f'blk{k}', lambda q: c + tip @ (ax * (q.x - .5) * L_ + ay * (q.y - .5) * Wd + Vector((0, 0, (q.z - .3) * Hh))),
        dmat(MAT['masonry']), oc, bevel=0.07)
    capped(lambda: blob(f'blkcap{k}', c + tip @ Vector((0, 0, 0.72 * Hh)), L_ * 0.45, Wd * 0.42, 0.11, dmat(MAT['cap']),
                        oc, seg=10, rot=math.radians(t['rot'])))
    blob(f'blkbank{k}', c, L_ * 0.85, Wd * 0.9, 0.3, dmat(MAT['pillow']), None, seg=14, rot=math.radians(t['rot']),
         mass=0.3)


def bridge(k, t):
    """the timber bridge from the terrace to the overlook: planks across in a rhythm (each its own value step, a dark
    gap between), two stringers under the edges, a rail of posts and braces on each side, corbels from the terraces'
    faces; snow banked along both edges and on every post and rail, the walked middle bare. Nothing hangs below the
    stringers: the corridor's headroom stays clear"""
    u0, u1, v0, v1, z0, z1 = t['u0'], t['u1'], t['v0'], t['v1'], t['z0'], t['z1']
    oc = new_occ(0.5 * (u0 + u1), v1, z1, deck=1)
    zf = lambda vv: z0 + (z1 - z0) * (vv - v0) / (v1 - v0)
    wood, wdk = dmat(MAT['wood']), dmat(MAT['wood_dk'])
    ax, ay = U(1, 0, 0).normalized(), U(0, 1, 0).normalized()
    br = random.Random(70 + k)
    pitch = 0.36
    n = int((v1 - v0 + 0.6) / pitch)
    planks = []
    for i in range(n):
        vv = v0 - 0.3 + (i + .5) * pitch
        w_ = (u1 - u0) * br.uniform(0.97, 1.05)
        planks.append((U((u0 + u1) / 2 + br.uniform(-.07, .07), vv, 0), ax, ay, w_, pitch * 0.84, zf(vv) - 0.1,
                       zf(vv) + (0.02 if i % 5 == 0 else 0.0), br.choice((-0.16, -0.06, 0.04, 0.12))))
    boxes_mesh(f'planks{k}', planks, dmat(MAT['plank']), oc, bevel=0.025)
    # a dark sub-deck under the planks: the gaps between them read as lines
    frame_box(f'subdeck{k}', U((u0 + u1) / 2, (v0 + v1) / 2, 0), ax, ay, (u1 - u0) * 0.94, v1 - v0 + 0.4,
              min(z0, z1) - 0.3, min(z0, z1) - 0.12, wdk, oc)
    for sd, uu in ((-1, u0 + 0.12), (1, u1 - 0.12)):
        # the stringer: a heavy beam under each edge
        frame_box(f'str{k}{sd}', U(uu, (v0 + v1) / 2, 0), ax, ay, 0.32, v1 - v0 + 1.0, min(z0, z1) - 0.5, min(z0, z1) - 0.12,
                  wdk, oc, bevel=0.03)
        # corbels: braces from the faces up to the stringer at both ends
        for vv, s_ in ((v0 - 0.2, 1), (v1 + 0.2, -1)):
            cyl(f'corb{k}{sd}{s_}', U(uu, vv, zf(vv) - 1.5), U(uu, vv + s_ * 1.4, zf(vv) - 0.45), 0.09, wdk, oc, seg=5)
        # posts and rails, a brace in every bay
        npost = 6
        posts = []
        for j in range(npost):
            vv = v0 + 0.1 + (v1 - v0 - 0.2) * j / (npost - 1)
            a = U(uu, vv, zf(vv) - 0.2)
            frame_box(f'rpost{k}{sd}{j}', a, ax, ay, 0.24, 0.24, a.z, a.z + 1.3, wdk, oc, bevel=0.03)
            blob(f'rpostsn{k}{sd}{j}', a + Vector((0, 0, 1.33)), 0.17, 0.17, 0.1, dmat(MAT['deck_snow']), oc, seg=8)
            posts.append(a)
        for j, (a, b) in enumerate(zip(posts, posts[1:])):
            cyl(f'rail{k}{sd}{j}', a + Vector((0, 0, 1.12)), b + Vector((0, 0, 1.12)), 0.1, wood, oc, seg=6)
            cyl(f'rail2{k}{sd}{j}', a + Vector((0, 0, 0.6)), b + Vector((0, 0, 0.6)), 0.07, wood, oc, seg=5)
            p_, q_ = (a, b) if j % 2 else (b, a)
            cyl(f'brace{k}{sd}{j}', p_ + Vector((0, 0, 0.2)), q_ + Vector((0, 0, 1.05)), 0.065, wdk, oc, seg=5)
            if br.random() < 0.45:                           # snow lying along the top rail, here and there
                m = a.lerp(b, br.uniform(0.3, 0.7)) + Vector((0, 0, 1.2))
                blob(f'railsn{k}{sd}{j}', m, (b - a).length * 0.22, 0.08, 0.05, dmat(MAT['deck_snow']), oc, seg=10,
                     rot=math.atan2(ay.y, ay.x))
        # snow banked along the deck's edge, broken into drifts
        vv = v0 + br.uniform(0.0, 0.3)
        s = 0
        while vv < v1 - 0.3:                            # a low drift banked along the edge, broken now and then
            ln = br.uniform(1.4, 2.4)
            if br.random() > 0.1:
                c_ = vv + ln / 2
                blob(f'decksn{k}{sd}{s}', U(uu - sd * 0.36, c_, zf(c_) + 0.0), ln * 0.62, 0.2 + 0.05 * br.random(),
                     0.06 + 0.02 * br.random(), dmat(MAT['deck_snow']), oc, seg=14, rot=math.atan2(ay.y, ay.x),
                     noise=0.05, seed=s, mass=0.5)
            vv += ln * 0.9 + br.uniform(0.0, 0.3)
            s += 1
    # a few thin tongues where the snow drifted across the planks
    for s in range(3):
        vv = v0 + 1.2 + br.random() * (v1 - v0 - 2.4)
        blob(f'deckpatch{k}{s}', U(br.uniform(-0.4, 0.4), vv, zf(vv) + 0.01), 0.9, 0.18, 0.03, dmat(MAT['deck_snow']), oc,
             seg=8, rot=math.atan2(ax.y, ax.x) + br.uniform(-.3, .3))


def lamppost(k, t):
    oc = new_occ(t['u'], t['v'], ground(t['u'], t['v']))
    u, v = t['u'], t['v']
    g = ground(u, v)
    a = U(u, v, g - 0.3)
    cyl(f'lp{k}', a, a + Vector((0, 0, 2.6)), 0.07, dmat(MAT['wood_dk']), oc, seg=6)
    arm = a + Vector((0, 0, 2.5))
    tip = arm + RIGHT * (0.45 if u < 0 else -0.45)
    cyl(f'lparm{k}', arm, tip, 0.045, dmat(MAT['wood_dk']), oc, seg=5)
    blob(f'lplamp{k}', tip + Vector((0, 0, -0.32)), 0.13, 0.13, 0.17, dmat(MAT['lamp'], kind='flat'), oc, seg=8)
    blob(f'lpsn{k}', U(u, v, g), .35, .35, .18, dmat(MAT['pillow']), None, seg=8)



BUILD = dict(rock=rock, stake=stake, tent=tent, tower=tower, heart=heart, fire=fire, banner=banner,
             crates=crates, woodpile=woodpile, altar=altar, menhir=menhir, bridge=bridge, lamppost=lamppost,
             ruin=ruin, stub=stub, block=block, column=column,
             spruce=lambda k, t: spruce(k, t['u'], t['v'], t['h'], t['cls'], DETAIL[t.get('zone', 'frame')]))


def build_back():
    """three forest ridges in forced scale under their spruces; the cumulus towers and the cloud sea; the clouds again
    as drifting layers when those passes are asked for"""
    for k, info in enumerate(S['strips']):
        ZONE_NOW[0] = ZCODE[info['zone']]
        strip(k, info)
    BAND_DETAIL = (1.0, 0.8, 0.62)
    for k, t in enumerate(S['trees']):
        ZONE_NOW[0] = ZCODE[t['zone']]
        spruce(5000 + k, t['u'], t['v'], t['h'], 'a' if k % 3 else 'b', DETAIL[t['zone']] * BAND_DETAIL[t['band']], g=t['z'],
               layer='back')
        BACKID[f'needles{5000 + k}'] = BACKID[f'snowc{5000 + k}'] = 10000 + k
    # the cumulus: towers past the forests and out of the sea at the front corners (the sun's pink on their crowns), the
    # cloud sea under the ledge
    ZONE_NOW[0] = ZCODE['vista']
    for i, cl in enumerate(S['clouds']):
        cloud_mass(f'cl{i}', cl['u'], cl['v'], cl['z'], cl['w'], cl['h'], cl['seed'], crown_side=cl['pink'],
                   floor=cl['floor'], detail=DETAIL['vista'], layer='back')
    # the clouds again as drifting layers (place.cloud_layers): complete, the strips periodic; each mass's cards reseeded
    # so a mass and its copy one period over are the same picture
    CL = S.get('cloud_layers', {})
    if any(x in ONLY for x in ('cfar', 'csea', 'ccorner')):
        for lay in ('far', 'sea', 'corner'):
            for i, cl in enumerate(CL.get(lay, [])):
                rng.seed(cl['seed'] * 7 + 1)
                cloud_mass(f'c{lay}{i}', cl['u'], cl['v'], cl['z'], cl['w'], cl['h'], cl['seed'], crown_side=cl['pink'],
                           floor=cl['floor'], detail=DETAIL['vista'], layer='c' + lay)

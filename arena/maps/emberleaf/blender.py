"""Emberleaf Hollow's Blender builders. Executed by arena/blender/arena.py in its own namespace (every kit helper is in
scope: U, ground, dmat, blob, box, frame_box, cyl, cards, card_values, spruce, cloud_mass, strip, boxes_mesh, axes,
new_occ, MAT, ZCODE, DETAIL, rng, TOCAM, RIGHT, UPS, SUN ...). Defines TERRAIN, BUILD and build_back().

The style is the arena's painted cards: every crown is clumps of camera-facing puff cards whose normals are the
clump's sphere blended with the whole crown's (one soft form, stepped into the coral ramp by the painter: plum
undersides, magenta, coral, its light), the pines are the shared spruce of dab cards in teal, the props are smooth
shaded blobs, boxes and cylinders under the sun from the upper left.
"""

ID_PUFFS = ID_PUFFS + ('crown', 'bushc')
ID_EXTRA['fern'] = 'leaves'                          # the leaf atlas (biome.textures)
NO_SHADOW = NO_SHADOW + ('reed', 'river', 'water', 'pebble')
WATER_Z = S['water_z']


def terrain_classify(i, j, zc, steep):
    if zc < -S['CLIFF'] + 1.0:
        return None                                   # the valley floor under the plateau: never seen
    if steep[i:i + 2, j:j + 2].mean() > 0.5 or zc < -1.6:
        return 'cliff'
    return 'grass'


TERRAIN = (('grass', 'cliff'), terrain_classify)


# ------------------------------------------------------------------ crowns
def crown(name, c, R, sq, mat, seed, detail=1.0, occ=None, layer='world', n_clumps=None, card=0.13):
    """a round deciduous crown of puff cards: clumps on the crown's shell (one on top, a ring round it, a few
    lower), each a hemisphere of cards facing out; per-corner normals = the clump's sphere blended with the crown's"""
    tr = random.Random(seed)
    small = n_clumps is None                       # the frame's crowns: a cauliflower of small puffs, each its own cap
    nc = n_clumps or max(3, int(round(16 * min(1.0, detail ** 0.5 + 0.2))))
    clumps = [(Vector((0, 0, R * sq * 0.35)), R * 0.72), (Vector((0, 0, -R * sq * 0.05)), R * 0.8)]
    for i in range(nc - 2):
        a = i / (nc - 2) * math.tau * 2.3 + tr.uniform(-0.4, 0.4)
        el = tr.uniform(-0.3, 0.85) if small else tr.uniform(-0.2, 0.45)
        d = Vector((math.cos(a) * math.cos(el), math.sin(a) * math.cos(el), math.sin(el) * sq)) * R * (0.62 if small else 0.45)
        clumps.append((d, R * (tr.uniform(0.32, 0.44) if small else tr.uniform(0.5, 0.62))))
    items, cent = [], []
    sz0 = R * card / max(detail, 0.12) ** 0.5
    for (off, rc) in clumps:
        cc = c + off
        n = max(5, int((16 + 90 * (rc / R) ** 2) * detail))
        for _ in range(n):
            # a point on the clump's outward hemisphere (cards on the inside are never seen)
            while True:
                q = Vector((tr.gauss(0, 1), tr.gauss(0, 1), tr.gauss(0, 1)))
                if q.length > 1e-3:
                    break
            q.normalize()
            if q.dot(off.normalized() if off.length > 1e-3 else Vector((0, 0, 1))) < -0.35:
                q = -q
            p = cc + Vector((q.x * rc, q.y * rc, q.z * rc * sq)) * tr.uniform(0.85, 1.05)

            def sn(k, cc=cc, rc=rc):
                o1 = k - cc
                n1 = Vector((o1.x / rc, o1.y / rc, o1.z / (rc * sq)))
                o2 = k - c
                n2 = Vector((o2.x / R, o2.y / R, o2.z / (R * sq)))
                # the upper half: mostly the clump's own sphere (a lit cap per puff); the lower: the whole crown's
                # (one calm plum underside)
                wz = min(max((0.1 - o2.z / (R * sq)) / 0.6, 0.0), 1.0) if small else 1.0
                w = 0.38 + 0.37 * wz if small else 0.7
                n_ = n1.normalized() * (1 - w) + n2.normalized() * w
                return n_.normalized()
            items.append((p, sz0 * tr.uniform(0.8, 1.2), sn))
            cent.append((tuple(p), tuple(sn(p))))
    if small:                                       # a finer scallop: small cards on the silhouette ring
        for _ in range(int(70 * detail * R / 2.5)):
            while True:
                q = Vector((tr.gauss(0, 1), tr.gauss(0, 1), tr.gauss(0, 0.8)))
                if q.length > 1e-3 and q.normalized().z > -0.45:
                    break
            q.normalize()
            p = c + Vector((q.x * R, q.y * R, q.z * R * sq)) * tr.uniform(0.86, 1.03)

            def sr(k):
                o2 = k - c
                return Vector((o2.x / R, o2.y / R, o2.z / (R * sq))).normalized()
            items.append((p, sz0 * tr.uniform(0.55, 0.8), sr))
            cent.append((tuple(p), tuple(sr(p))))
    val = card_values([p for p, _ in cent], [n for _, n in cent], reach=R * 0.5, gradient=0.16, value=0.32, count=10.0)
    # a smooth core volume behind the cards (sphere-shaded the same way, receives no shadow): no holes through the crown
    blob('kcore_' + name, c + Vector((0, 0, R * sq * 0.05)), R * 0.7, R * 0.7, R * sq * 0.7, dmat(MAT[mat], None, 'card'),
         occ, seg=16, layer=layer)
    return cards(name, items, dmat(MAT[mat], 'puffs', 'card'), val, layer=layer, occ=occ)


def oak(k, t):
    """a red-crowned tree: a tapered trunk with two limbs into the crown, root flares, a round coral crown"""
    u, v, h, R = t['u'], t['v'], t['h'], t['crown']
    g = ground(u, v)
    oc = new_occ(u, v, g)
    tr = random.Random(t['seed'])
    base = U(u, v, g)
    lean = Vector((tr.uniform(-.25, .25), tr.uniform(-.25, .25), 0))
    top = base + lean + Vector((0, 0, h * 0.62))
    bark = dmat(MAT['bark'])
    cyl(f'trunk{k}', base + Vector((0, 0, -0.3)), top, 0.3, bark, oc, seg=8, r2=0.16)
    for j in range(2):
        a = tr.uniform(0, math.tau)
        p0 = base + lean * 0.5 + Vector((0, 0, h * tr.uniform(0.32, 0.45)))
        p1 = p0 + Vector((math.cos(a) * R * 0.5, math.sin(a) * R * 0.5, R * 0.6))
        cyl(f'limb{k}_{j}', p0, p1, 0.12, bark, oc, seg=6, r2=0.06)
    for j in range(4):
        a = j / 4 * math.tau + tr.uniform(-.3, .3)
        blob(f'root{k}_{j}', base + Vector((math.cos(a) * 0.32, math.sin(a) * 0.32, 0.05)), 0.42, 0.16, 0.16, bark, oc,
             seg=8, rot=a)
    c = base + lean + Vector((0, 0, h - R * 0.85))
    crown(f'crown{k}', c, R, 0.8, 'crown_' + t['cls'], t['seed'], DETAIL[t.get('zone', 'frame')], occ=oc)


def pine(k, t):
    spruce(k, t['u'], t['v'], t['h'], 'a', DETAIL[t.get('zone', 'frame')], mats=('pine', 'pine_hi', 'bark'))


def bush(k, t):
    """a low shrub: two or three clumps of puffs at the ground, green or red"""
    u, v = t['u'], t['v']
    g = ground(u, v)
    oc = new_occ(u, v, g)
    tr = random.Random(t['seed'])
    r = t.get('rad', t.get('r') or 1.0)
    h = t['h']
    mat = 'bush_' + t['cls']
    for j in range(tr.randint(2, 3)):
        a = tr.uniform(0, math.tau)
        c = U(u + math.cos(a) * r * 0.35, v + math.sin(a) * r * 0.35, g + h * 0.42)
        crown(f'bushc{k}_{j}', c, r * tr.uniform(0.62, 0.8), h / (2 * r) * 1.1, mat, t['seed'] + j, 1.0, occ=oc,
              n_clumps=3, card=0.18)


# ------------------------------------------------------------------ stone and wood
def boulder(k, t):
    """a rounded slate boulder: a lumpy smooth blob, a lighter top, small stones at its foot"""
    u, v, r, h = t['u'], t['v'], t['r'], t['h']
    g = ground(u, v)
    oc = new_occ(u, v, g)
    tr = random.Random(t['seed'])
    c = U(u, v, g + h * 0.38 - t.get('sink', 0.0))
    blob(f'boulder{k}', c, r * 1.05, r * 0.9, h * 0.55, dmat(MAT['boulder']), oc, seg=22, rot=tr.uniform(0, 3),
         noise=0.07, seed=t['seed'], flat=0.6, mass=0.5)
    if r >= 0.5:                                      # a moss cap on top, toward the side away from the sun
        mc = c + U(0.18 * r, -0.12 * r, h * 0.5)
        blob(f'bmoss{k}', mc, r * 0.62, r * 0.5, h * 0.12, dmat(MAT['moss']), oc, seg=12, rot=tr.uniform(0, 3),
             noise=0.25, seed=t['seed'] + 3)
    if r > 1.6:                                       # a second stone leaning on the big ones
        a = tr.uniform(0, math.tau)
        blob(f'boulderb{k}', c + Vector((math.cos(a) * r * 0.8, math.sin(a) * r * 0.8, -h * 0.25)), r * 0.55, r * 0.5,
             h * 0.32, dmat(MAT['boulder']), oc, seg=16, rot=a, noise=0.14, seed=t['seed'] + 1, flat=0.5, mass=0.4)
    for j in range(tr.randint(2, 4)):
        a = tr.uniform(0, math.tau); d = r * tr.uniform(1.0, 1.35)
        blob(f'pebble{k}_{j}', U(u + math.cos(a) * d, v + math.sin(a) * d, g + 0.04), 0.16, 0.13, 0.1,
             dmat(MAT['boulder']), None, seg=8, rot=a, noise=0.15, seed=j)


def crag(k, t):
    """a jagged crag: a cluster of rock shards (flat-shaded, faceted, pointed, leaning out from the middle) inside the
    collider's circle, the tallest near the middle; for the big rocks that must stand tall (the spawn screens); small
    faceted rocks broken off at its foot"""
    u, v, r, h = t['u'], t['v'], t['r'], t['h']
    g = ground(u, v)
    oc = new_occ(u, v, g)
    tr = random.Random(t['seed'])
    n = tr.randint(4, 6)
    for j in range(n):
        a = tr.uniform(0, math.tau) if j else 0.0
        d = 0.0 if j == 0 else r * tr.uniform(0.35, 0.62)
        w = r * (0.55 if j == 0 else tr.uniform(0.3, 0.42))
        hh = h * (1.0 if j == 0 else tr.uniform(0.45, 0.8))
        bm = bmesh.new()
        bmesh.ops.create_cone(bm, cap_ends=True, segments=tr.randint(5, 6), radius1=w, radius2=w * 0.1, depth=hh)
        lean = Matrix.Rotation(tr.uniform(0.12, 0.3) if j else tr.uniform(0.0, 0.1), 3,
                               Vector((-math.sin(a), math.cos(a), 0)))
        rz = Matrix.Rotation(tr.uniform(0, math.tau), 3, 'Z')
        base = U(u + math.cos(a) * d, v + math.sin(a) * d, g - 0.12)
        for vt in bm.verts:
            p = vt.co.copy()
            p.z += hh / 2
            if p.z > hh * 0.2:                                   # chipped faces and an off-centre tip
                p.x += tr.uniform(-0.12, 0.12) * w; p.y += tr.uniform(-0.12, 0.12) * w
            p.x *= 1.0; p.y *= 0.8
            vt.co = base + lean @ (rz @ p)
        me = bpy.data.meshes.new(f'crag{k}_{j}'); bm.to_mesh(me); bm.free()
        for poly in me.polygons:
            poly.use_smooth = False
        link(f'crag{k}_{j}', me, [dmat(MAT['boulder'])], occ=oc)
    for j in range(tr.randint(2, 4)):                 # broken pieces at its foot
        a = tr.uniform(0, math.tau); d = r * tr.uniform(0.95, 1.3)
        c = U(u + math.cos(a) * d, v + math.sin(a) * d, g + 0.05)
        bm = bmesh.new()
        bmesh.ops.create_icosphere(bm, subdivisions=1, radius=1.0)
        rr = tr.uniform(0.18, 0.32)
        for vt in bm.verts:
            vt.co = c + Vector((vt.co.x * rr * tr.uniform(0.8, 1.2), vt.co.y * rr * tr.uniform(0.8, 1.2),
                                max(vt.co.z, -0.3) * rr * 0.8))
        me = bpy.data.meshes.new(f'cragbit{k}_{j}'); bm.to_mesh(me); bm.free()
        for poly in me.polygons:
            poly.use_smooth = False
        link(f'cragbit{k}_{j}', me, [dmat(MAT['boulder'])], occ=oc)
    if tr.random() < 0.7:                             # moss in a hollow on its shoulder
        blob(f'cragmoss{k}', U(u + 0.25 * r, v - 0.15 * r, g + h * 0.55), r * 0.4, r * 0.3, 0.1, dmat(MAT['moss']), oc,
             seg=10, noise=0.25, seed=t['seed'] + 2)


def stump(k, t):
    u, v, r, h = t['u'], t['v'], t['r'], t['h']
    g = ground(u, v)
    oc = new_occ(u, v, g)
    tr = random.Random(t['seed'])
    c = U(u, v, g)
    cyl(f'stump{k}', c + Vector((0, 0, -0.25)), c + Vector((0, 0, h)), r, dmat(MAT['bark']), oc, seg=12, r2=r * 0.92)
    cyl(f'stumptop{k}', c + Vector((0, 0, h - 0.03)), c + Vector((0, 0, h + 0.02)), r * 0.86, dmat(MAT['wood_end']), oc,
        seg=12)
    for j in range(3):
        a = j / 3 * math.tau + tr.uniform(-.5, .5)
        blob(f'stumproot{k}_{j}', c + Vector((math.cos(a) * r * 0.9, math.sin(a) * r * 0.9, 0.04)), r * 0.7, r * 0.28,
             0.14, dmat(MAT['bark']), oc, seg=8, rot=a)


def log(k, t):
    """the fallen log across the fighting ground: bark, cut ends with rings, a broken branch, moss on its back"""
    u, v, r, L = t['u'], t['v'], t['r'], t['len']
    g = ground(u, v)
    oc = new_occ(u, v, g)
    tr = random.Random(t['seed'])
    a = math.radians(t['rot'])
    d = U(math.cos(a), math.sin(a), 0).normalized()
    c = U(u, v, g + r * 0.85)
    p0, p1 = c - d * (L / 2), c + d * (L / 2)
    cyl(f'log{k}', p0, p1, r, dmat(MAT['wood']), oc, seg=14, r2=r * 0.9)
    for e, (p, s_) in enumerate(((p0, -1), (p1, 1))):
        rr = r if s_ < 0 else r * 0.9
        cyl(f'logend{k}_{e}', p - d * 0.02 * s_, p + d * 0.03 * s_, rr * 0.9, dmat(MAT['wood_end']), oc, seg=14)
    q = c + d * L * 0.15
    side = U(-math.sin(a), math.cos(a), 0).normalized()
    cyl(f'logbranch{k}', q + side * r * 0.7, q + side * (r + 0.55) + Vector((0, 0, 0.35)), 0.09, dmat(MAT['wood']), oc,
        seg=6, r2=0.05)
    # the root plate standing up at its north end: a disc of roots with the clod of earth they tore up (the big log
    # only; the short logs end in a broken stub)
    rp = p1 + d * 0.1 + Vector((0, 0, 0.3))
    plate = t.get('plate', True)
    if plate:
        blob(f'rootplate{k}', rp, 0.78, 0.2, 0.72, dmat(MAT['bark']), oc, seg=16, rot=math.atan2(side.y, side.x),
             noise=0.2, seed=t['seed'] + 5)
        blob(f'rootclod{k}', rp + d * 0.12 + Vector((0, 0, -0.15)), 0.55, 0.18, 0.4, dmat(MAT['dirt']), oc, seg=12,
             rot=math.atan2(side.y, side.x), noise=0.25, seed=t['seed'] + 6)
    for j in range(7 if plate else 0):
        a2 = j / 7 * math.tau
        tip = rp + side * math.cos(a2) * 1.0 + Vector((0, 0, math.sin(a2) * 0.85)) + d * tr.uniform(-0.1, 0.25)
        cyl(f'root{k}_{j}', rp, tip, 0.06, dmat(MAT['bark']), oc, seg=5, r2=0.015)
    # the split end at its south: jagged splinters
    for j in range(5):
        a2 = j / 5 * math.tau + 0.3
        b0 = p0 + side * math.cos(a2) * r * 0.55 + Vector((0, 0, math.sin(a2) * r * 0.55))
        cyl(f'splint{k}_{j}', b0, b0 - d * tr.uniform(0.15, 0.45), 0.08, dmat(MAT['wood']), oc, seg=4, r2=0.01)
    # bark: long dark strokes along it; moss on the side away from the sun
    for j in range(3):
        a2 = (j - 1) * 0.6
        off = side * math.sin(a2) * r * 1.0 + Vector((0, 0, math.cos(a2) * r * 1.0))
        cyl(f'bark{k}_{j}', p0 + d * 0.3 + off, p1 - d * 0.5 + off * 0.95, 0.035, dmat(MAT['bark']), oc, seg=4)
    blob(f'logmoss{k}', c + side * r * 0.75 + Vector((0, 0, r * 0.35)), 0.12, L * 0.33, 0.1, dmat(MAT['moss']), oc,
         seg=12, rot=math.atan2(side.y, side.x), noise=0.2, seed=t['seed'] + 7)


def ruinwall(k, t):
    """a broken low wall of dressed stone: two or three courses of blocks, its top broken, moss on it, a fallen block"""
    u, v, L, h = t['u'], t['v'], t['len'], t['h']
    g = ground(u, v)
    oc = new_occ(u, v, g)
    tr = random.Random(t['seed'])
    a = math.radians(t['rot'])
    d = U(math.cos(a), math.sin(a), 0).normalized()
    n = U(-math.sin(a), math.cos(a), 0).normalized()
    nc = 3 if h > 1.0 else 2
    ch = h / nc
    items = []
    for i in range(nc):
        s_ = -L / 2 + (0.0 if i % 2 == 0 else -0.3)
        while s_ < L / 2:
            ln = tr.uniform(0.55, 0.8)
            m = s_ + ln / 2
            s_ += ln
            if abs(m) > L / 2:
                continue
            top_broken = i == nc - 1 and (abs(m) > L * 0.3 or tr.random() < 0.3)
            if top_broken and tr.random() < 0.6:
                continue
            cc = U(u, v, 0) + d * m + n * tr.uniform(-0.04, 0.04)
            items.append((cc, d, n, ln * 0.96, 0.7, g - 0.25 + i * ch, g + (i + 1) * ch - 0.02, tr.uniform(-0.12, 0.12)))
    boxes_mesh(f'ruinwall{k}', items, dmat(MAT['ruin']), oc, bevel=0.06)
    for j in range(2):
        m = tr.uniform(-L * 0.3, L * 0.3)
        blob(f'ruinmoss{k}_{j}', U(u, v, g + h * 0.9) + d * m, 0.4, 0.3, 0.1, dmat(MAT['moss']), oc, seg=10,
             rot=a, noise=0.2, seed=j)
    fb = U(u, v, g + 0.2) + d * (L * 0.55) - n * 0.7
    frame_box(f'ruinfall{k}', fb, d, n, 0.65, 0.6, g - 0.1, g + 0.4, dmat(MAT['ruin']), oc, bevel=0.06)


def waystone(k, t):
    """the spawn's mark: a carved wooden totem, a glowing rune on its face toward the camera, a little roof, no stone"""
    u, v, h = t['u'], t['v'], t['h']
    g = ground(u, v)
    oc = new_occ(u, v, g)
    c = U(u, v, g)
    ax, ay = U(1, 0, 0).normalized(), U(0, 1, 0).normalized()
    box(f'waystone{k}', lambda q: c + ax * (q.x - .5) * (0.5 - 0.12 * q.z) + ay * (q.y - .5) * (0.42 - 0.1 * q.z)
        + Vector((0, 0, -0.3 + q.z * (h + 0.3))), dmat(MAT['wood']), oc, bevel=0.05, seg=2)
    for j, zz in enumerate((0.35, 0.95)):                                   # carved bands
        frame_box(f'wayband{k}_{j}', c, ax, ay, 0.54, 0.46, g + zz, g + zz + 0.1, dmat(MAT['bark']), oc)
    frame_box(f'rune{k}', c - ay * 0.22, ax, ay, 0.18, 0.04, g + h * 0.5, g + h * 0.78, dmat(MAT['rune'], kind='flat'), oc)
    bm = bmesh.new()
    bmesh.ops.create_cone(bm, cap_ends=True, segments=4, radius1=0.48, radius2=0.03, depth=0.32)
    me = bpy.data.meshes.new(f'wayroof{k}'); bm.to_mesh(me); bm.free()
    Rz = Matrix.Rotation(math.pi / 4, 4, 'Z')
    for vt in me.vertices:
        vt.co = U(u, v, g + h + 0.12) + (Rz @ vt.co.to_4d()).to_3d()
    link(f'wayroof{k}', me, [dmat(MAT['bark'])], occ=oc)


def lantern(k, t):
    """a wooden lantern post, 1.4 m: a post, a lit lamp box you can read at 1x, a little roof"""
    u, v, h = t['u'], t['v'], t['h']
    g = ground(u, v)
    oc = new_occ(u, v, g)
    c = U(u, v, 0)
    ax, ay = U(1, 0, 0).normalized(), U(0, 1, 0).normalized()
    st = dmat(MAT['wood'])
    frame_box(f'lpost{k}', c, ax, ay, 0.16, 0.16, g - 0.2, g + 0.9, st, oc, bevel=0.02)
    frame_box(f'lhead{k}', c, ax, ay, 0.36, 0.36, g + 0.9, g + 1.2, st, oc, bevel=0.02)
    frame_box(f'llamp{k}', c - (ax + ay).normalized() * 0.16, ax, ay, 0.26, 0.1, g + 0.93, g + 1.17,
              dmat(MAT['lamp'], kind='flat'), oc)
    bm = bmesh.new()
    bmesh.ops.create_cone(bm, cap_ends=True, segments=4, radius1=0.42, radius2=0.03, depth=0.28)
    me = bpy.data.meshes.new(f'lroof{k}'); bm.to_mesh(me); bm.free()
    Rz = Matrix.Rotation(math.pi / 4, 4, 'Z')
    for vt in me.vertices:
        vt.co = U(u, v, g + 1.34) + (Rz @ vt.co.to_4d()).to_3d()
    link(f'lroof{k}', me, [dmat(MAT['bark'])], occ=oc)


def crates(k, t):
    """the camp's supplies: two or three plank crates, one on top, iron straps"""
    u, v = t['u'], t['v']
    g = ground(u, v)
    oc = new_occ(u, v, g)
    tr = random.Random(t['seed'])
    a = math.radians(t.get('rot', 0))
    ax = U(math.cos(a), math.sin(a), 0).normalized(); ay = U(-math.sin(a), math.cos(a), 0).normalized()
    wd, mt = dmat(MAT['clay']), dmat(MAT['metal'])
    spots = [(0.0, 0.0, 0.62, 0.0), (0.68, 0.12, 0.5, 0.0), (0.05, 0.02, 0.5, 0.62)]
    for j, (du, dv, sz, z0) in enumerate(spots[:tr.randint(2, 3)]):
        c = U(u, v, 0) + ax * du + ay * dv
        frame_box(f'crate{k}_{j}', c, ax, ay, sz, sz, g + z0 - 0.05, g + z0 + sz * 0.9, wd, oc, bevel=0.03)
        frame_box(f'cratestrap{k}_{j}', c, ax, ay, sz + 0.02, 0.06, g + z0 - 0.04, g + z0 + sz * 0.9 + 0.01, mt, oc)


def banner(k, t):
    """a banner pole of plain linen (neutral: the units' colours stay theirs), a crossbar, the cloth hanging"""
    u, v, h = t['u'], t['v'], t['h']
    g = ground(u, v)
    oc = new_occ(u, v, g)
    c = U(u, v, g)
    cyl(f'bpole{k}', c + Vector((0, 0, -0.2)), c + Vector((0, 0, h)), 0.05, dmat(MAT['wood']), oc, seg=6)
    ax = U(1, 0, 0).normalized() * (1 if u < 0 else -1)
    cyl(f'bbar{k}', c + Vector((0, 0, h - 0.15)), c + Vector((0, 0, h - 0.15)) + ax * 0.75, 0.03, dmat(MAT['wood']),
        oc, seg=5)
    ay = U(0, 1, 0).normalized()
    frame_box(f'bcloth{k}', c + ax * 0.4 - ay * 0.04, ax, ay, 0.62, 0.04, g + h - 1.25, g + h - 0.17,
              dmat(MAT['cloth']), oc)


def fire(k, t):
    """a campfire: a ring of stones round three crossed logs and the embers (the flames are the viewer's)"""
    u, v = t['u'], t['v']
    g = ground(u, v)
    oc = new_occ(u, v, g)
    tr = random.Random(t['seed'])
    for j in range(9):
        a = j / 9 * math.tau + tr.uniform(-.15, .15)
        blob(f'fstone{k}_{j}', U(u + math.cos(a) * 0.45, v + math.sin(a) * 0.45, g + 0.04), tr.uniform(.11, .15),
             tr.uniform(.09, .12), .09, dmat(MAT['boulder']), oc, seg=8, rot=a, noise=0.15, seed=j)
    for j in range(3):
        a = j / 3 * math.pi + tr.uniform(-.2, .2)
        d = U(math.cos(a), math.sin(a), 0).normalized()
        cc = U(u, v, g + 0.08)
        cyl(f'flog{k}_{j}', cc - d * 0.3, cc + d * 0.3, 0.05, dmat(MAT['wood']), oc, seg=6)
    blob(f'fember{k}', U(u, v, g + 0.04), 0.16, 0.14, 0.04, dmat(MAT['lamp'], kind='flat'), oc, seg=10)


def bedroll(k, t):
    """a bedroll by the fire: a linen blanket laid out, its roll at the head"""
    u, v = t['u'], t['v']
    g = ground(u, v)
    oc = new_occ(u, v, g)
    a = math.radians(t.get('rot', 0))
    ax = U(math.cos(a), math.sin(a), 0).normalized(); ay = U(-math.sin(a), math.cos(a), 0).normalized()
    c = U(u, v, 0)
    frame_box(f'bed{k}', c, ax, ay, 1.3, 0.55, g - 0.02, g + 0.06, dmat(MAT['clay']), oc, bevel=0.03)
    cc = U(u, v, g + 0.12) + ax * 0.58
    cyl(f'bedroll{k}', cc - ay * 0.3, cc + ay * 0.3, 0.12, dmat(MAT['cloth']), oc, seg=10)


def potlight(k, t):
    """a clay pot with a light in it (a candle or glowing fungus), 0.35 m"""
    u, v = t['u'], t['v']
    g = ground(u, v)
    oc = new_occ(u, v, g)
    c = U(u, v, g)
    cyl(f'pot{k}', c + Vector((0, 0, -0.05)), c + Vector((0, 0, 0.26)), 0.12, dmat(MAT['clay']), oc, seg=10, r2=0.15)
    blob(f'potlamp{k}', U(u, v, g + 0.28), 0.08, 0.08, 0.06, dmat(MAT['lamp'], kind='flat'), oc, seg=8)


def reeds(k, t):
    u, v = t['u'], t['v']
    g = ground(u, v)
    tr = random.Random(t['seed'])
    for j in range(tr.randint(5, 9)):
        a = tr.uniform(0, math.tau); d = tr.uniform(0, 0.35)
        b = U(u + math.cos(a) * d, v + math.sin(a) * d, g - 0.1)
        hh = tr.uniform(0.6, 1.1)
        tip = b + Vector((tr.uniform(-.12, .12), tr.uniform(-.12, .12), hh))
        cyl(f'reed{k}_{j}', b, tip, 0.035, dmat(MAT['reed']), None, seg=4, r2=0.006)


def shorestone(k, t):
    """a slate stone on the pond's rim, half in the water"""
    u, v, r = t['u'], t['v'], t['rad']
    tr = random.Random(t['seed'])
    blob(f'shore{k}', U(u, v, WATER_Z + r * 0.1), r * tr.uniform(1.0, 1.3), r * tr.uniform(0.8, 1.0), r * 0.45,
         dmat(MAT['boulder']), None, seg=12, rot=tr.uniform(0, 3), noise=0.12, seed=t['seed'], flat=0.3, mass=0.4)
    if t.get('moss'):
        blob(f'shoremoss{k}', U(u + 0.1 * r, v - 0.05 * r, WATER_Z + r * 0.62), r * 0.7, r * 0.55, r * 0.14,
             dmat(MAT['moss']), None, seg=10, noise=0.25, seed=t['seed'] + 1)


def pebbles(k, t):
    u, v = t['u'], t['v']
    g = ground(u, v)
    tr = random.Random(t['seed'])
    for j in range(tr.randint(2, 4)):
        a = tr.uniform(0, math.tau); d = tr.uniform(0, 0.4)
        blob(f'pebble_{k}_{j}', U(u + math.cos(a) * d, v + math.sin(a) * d, g + 0.03), tr.uniform(.14, .26),
             tr.uniform(.12, .2), tr.uniform(.08, .13), dmat(MAT['boulder']), None, seg=8, rot=a, noise=0.12, seed=j)


def fern(k, t):
    """a fern or leafy plant: big-leaf cards spread from its heart, lit from above"""
    u, v, h = t['u'], t['v'], t['h']
    g = ground(u, v)
    oc = new_occ(u, v, g)
    tr = random.Random(t['seed'])
    c = U(u, v, g + h * 0.35)
    items = []
    for j in range(tr.randint(9, 14)):
        a = tr.uniform(0, math.tau); rr = tr.uniform(0.1, 0.55) * h
        p = c + Vector((math.cos(a) * rr, math.sin(a) * rr, tr.uniform(-0.1, 0.35) * h))
        n_ = Vector((math.cos(a) * 0.45, math.sin(a) * 0.45, 1.0)).normalized()
        items.append((p, h * tr.uniform(0.32, 0.45), n_))
    cards(f'fern{k}', items, dmat(MAT['fern'], 'leaves', 'card'), None, occ=oc)


def nothing(k, t):
    """flowers and mushrooms are painted marks (biome.after_clean), not geometry"""
    return None


def pond():
    """the water: a flat surface at the water's height over each basin, its rim a little past the waterline so the
    bank's own terrain cuts the shore (irregular, with the bays and the stones' feet)"""
    was, ZONE_NOW[0] = ZONE_NOW[0], ZCODE['frame']
    for i, poly in enumerate(S['water_polys']):
        cu = sum(p[0] for p in poly) / len(poly); cv = sum(p[1] for p in poly) / len(poly)
        n = len(poly)
        vs = [U(cu, cv, WATER_Z)] + [U(pu, pv, WATER_Z) for pu, pv in poly]
        fs = [(0, 1 + j, 1 + (j + 1) % n) for j in range(n)]
        nm = 'water' if i == 0 else f'waterpool{i}'
        link(nm, mesh_from(nm, vs, fs, smooth_=False), [dmat(MAT['water'])])
    ZONE_NOW[0] = was


BUILD = dict(crag=crag, oak=oak, pine=pine, bush=bush, boulder=boulder, stump=stump, log=log, ruinwall=ruinwall,
             waystone=waystone, lantern=lantern, reeds=reeds, crates=crates, banner=banner, fire=fire, bedroll=bedroll,
             potlight=potlight, pebbles=pebbles, shorestone=shorestone, fern=fern, flowers=nothing, mushrooms=nothing)
pond()


# ------------------------------------------------------------------ the back
def ribbon(name, us, vs, zs, w, mat, layer='back'):
    verts, faces = [], []
    for i, (u, v, z) in enumerate(zip(us, vs, zs)):
        verts.append(U(u, v - w / 2, z)); verts.append(U(u, v + w / 2, z))
        if i:
            faces.append((2 * i - 2, 2 * i, 2 * i + 1, 2 * i - 1))
    me = mesh_from(name, verts, faces, smooth_=False)
    return link(name, me, [dmat(MAT[mat])], layer=layer)


def build_back():
    """the valley: three bands of canopy over their ground strips (red and green crowns in fewer, bigger puffs every
    step back), the valley floor and the river; the far hills and the cumulus (vista)"""
    for k, info in enumerate(S['strips']):
        ZONE_NOW[0] = ZCODE[info['zone']]
        strip(k, info, mat=info.get('mat', 'far_ground'))
    ZONE_NOW[0] = ZCODE['backdrop']
    rv = S['river']
    ribbon('river', rv['u'], rv['v'], rv['z'], rv['w'], 'river')
    BAND_DETAIL = (0.8, 0.6, 0.45)
    for k, t in enumerate(S['trees']):
        ZONE_NOW[0] = ZCODE[t['zone']]
        R = t['h'] * 0.42
        c = U(t['u'], t['v'], t['z'] + t['h'] * 0.55)
        mat = 'far_coral' if t['cls'] == 'coral' else 'far_green'
        crown(f'crown{5000 + k}', c, R, 0.85, mat, 7000 + k, DETAIL[t['zone']] * BAND_DETAIL[t['band']], layer='back',
              n_clumps=3 if t["band"] < 2 else 2, card=0.24)
        BACKID[f'crown{5000 + k}'] = BACKID[f'kcore_crown{5000 + k}'] = 10000 + k
    ZONE_NOW[0] = ZCODE['vista']
    for i, cl in enumerate(S['clouds']):
        cloud_mass(f'cl{i}', cl['u'], cl['v'], cl['z'], cl['w'], cl['h'], cl['seed'], crown_side=False,
                   floor=False, detail=DETAIL['vista'], layer='back')
    CL = S.get('cloud_layers', {})
    if 'cfar' in ONLY:
        for i, cl in enumerate(CL.get('far', [])):
            rng.seed(cl['seed'] * 7 + 1)
            cloud_mass(f'cfar{i}', cl['u'], cl['v'], cl['z'], cl['w'], cl['h'], cl['seed'], crown_side=False,
                       floor=False, detail=DETAIL['vista'], layer='cfar')

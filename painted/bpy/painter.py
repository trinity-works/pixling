"""The painted-cards painter (runs inside Blender). One look for every asset:
- shading: diffuse -> Shader to RGB -> stepped colour ramp from the style file (painted/styles/*.json) (no gradients, no specular)
- foliage: alpha cards scattered in a sphere, every card vertex carries the sphere normal, so a clump shades as one mass
- flat surfaces can borrow the same trick (normals bent toward a centre) so a plane shades like a painted mass
- the style's `foliage` block adds the rest of the anime-tree method: cards that face the camera, a baked value pass
  (dark pockets where cards bury each other, like the tutorial's AO), a light-to-shadow gradient across the whole crown,
  and per-card flutter for the sway loop
- one fixed orthographic camera; every render is a transparent sprite with its ground-origin anchor
"""
import bpy, bmesh, os, json, math, random
import numpy as np
from mathutils import Vector, Matrix

STY = LAYOUT = None
E = PPM = LT = UPV = FWD = None
FOL = {}      # the style's foliage block; empty = plain cards
CARDS = {}    # card object name -> per-card centres, plane normals, corner normals (for the value pass and flutter)


def configure(style_path, layout_path=None):
    """load the style (camera, light, ramps) and optionally a layout; derive the camera frame. Call before building."""
    global STY, LAYOUT, E, PPM, LT, UPV, FWD, FOL
    STY = json.load(open(style_path))
    FOL = STY.get('foliage', {})
    LAYOUT = json.load(open(layout_path)) if layout_path else None
    E = math.radians(STY['camera']['elevation_deg']); PPM = STY['camera']['ppm']
    LT = Vector(STY['light']['travel']).normalized()
    UPV = Vector((0, math.sin(E), math.cos(E)))     # screen up, in world space
    FWD = Vector((0, math.cos(E), -math.sin(E)))    # view direction
rng = random.Random(1)
TEX = None
COLL = None
MATS = {}


def lin(h):
    c = [int(h[i:i + 2], 16) / 255 for i in (1, 3, 5)]
    return tuple((v / 12.92 if v <= 0.04045 else ((v + 0.055) / 1.055) ** 2.4) for v in c) + (1.0,)


def setup(texdir):
    global TEX, sc, cam, co
    TEX = texdir
    bpy.ops.wm.read_factory_settings(use_empty=True)
    sc = bpy.context.scene
    sc.render.engine = 'BLENDER_EEVEE_NEXT'
    sc.eevee.taa_render_samples = 16
    sc.render.film_transparent = True
    sc.view_settings.view_transform = 'Standard'
    sc.render.image_settings.file_format = 'PNG'; sc.render.image_settings.color_mode = 'RGBA'
    sun = bpy.data.lights.new('sun', 'SUN'); sun.energy = STY['light']['energy']; sun.angle = math.radians(1.5)
    so = bpy.data.objects.new('sun', sun); sc.collection.objects.link(so)
    so.rotation_euler = LT.to_track_quat('-Z', 'Y').to_euler()
    world = bpy.data.worlds.new('w'); sc.world = world; world.use_nodes = True
    world.node_tree.nodes['Background'].inputs[0].default_value = (1, 1, 1, 1)
    world.node_tree.nodes['Background'].inputs[1].default_value = STY['light']['fill']
    cam = bpy.data.cameras.new('cam'); cam.type = 'ORTHO'; cam.clip_end = 500
    co = bpy.data.objects.new('cam', cam); sc.collection.objects.link(co); sc.camera = co
    co.rotation_euler = (math.pi / 2 - E, 0, 0)


# ------------------------------------------------------------------ shader graph helpers

class G:
    """tiny node-graph builder: G(material).math('ADD', a, b) etc. Sockets or floats both accepted."""

    def __init__(self, m):
        self.N, self.L = m.node_tree.nodes, m.node_tree.links

    def node(self, kind, **inputs):
        n = self.N.new(kind)
        for k, v in inputs.items():
            self.put(n.inputs[k], v)
        return n

    def put(self, sock, v):
        if hasattr(v, 'links'):
            self.L.new(v, sock)
        else:
            sock.default_value = v

    def math(self, op, a, b=0.0):
        n = self.N.new('ShaderNodeMath'); n.operation = op
        self.put(n.inputs[0], a); self.put(n.inputs[1], b)
        return n.outputs[0]

    def mix(self, fac, a, b):
        n = self.N.new('ShaderNodeMix'); n.data_type = 'RGBA'
        self.put(n.inputs[0], fac); self.put(n.inputs[6], a); self.put(n.inputs[7], b)
        return n.outputs[2]

    def ramp(self, name, fac):
        n = self.N.new('ShaderNodeValToRGB'); n.color_ramp.interpolation = 'CONSTANT'
        stops = STY['ramps'][name]; els = n.color_ramp.elements
        els[0].position, els[0].color = 0.0, lin(stops[0][1])
        els[1].position, els[1].color = stops[1][0], lin(stops[1][1])
        for p, h in stops[2:]:
            els.new(p).color = lin(h)
        self.put(n.inputs[0], fac)
        return n.outputs[0]

    def lit(self):
        """sun + fill as one value, scaled by the style's gain: the input of every ramp."""
        s2r = self.node('ShaderNodeShaderToRGB', Shader=self.node('ShaderNodeBsdfDiffuse').outputs[0])
        bw = self.node('ShaderNodeRGBToBW', Color=s2r.outputs[0])
        return self.math('MULTIPLY', bw.outputs[0], STY['light'].get('gain', 1.0))

    def noise(self, scale, sx=1.0, sy=1.0, sz=1.0, lo=-1.0, hi=1.0, detail=3.0, offset=None):
        tc = self.node('ShaderNodeTexCoord')
        mp = self.node('ShaderNodeMapping', Vector=tc.outputs['Object'])
        mp.inputs['Scale'].default_value = (sx, sy, sz)
        if offset is not None:
            mp.inputs['Location'].default_value = offset
        nz = self.node('ShaderNodeTexNoise', Vector=mp.outputs[0], Scale=scale, Detail=detail)
        mr = self.node('ShaderNodeMapRange', Value=nz.outputs[0])
        for k, v in (('From Min', .3), ('From Max', .7), ('To Min', lo), ('To Max', hi)):
            mr.inputs[k].default_value = v
        return mr.outputs[0], mp

    def attr(self, name):
        n = self.N.new('ShaderNodeAttribute'); n.attribute_name = name
        return n.outputs['Fac']

    def emit(self, col, out, alpha=None):
        em = self.node('ShaderNodeEmission', Color=col).outputs[0]
        if alpha is not None:
            tr = self.node('ShaderNodeBsdfTransparent').outputs[0]
            mx = self.N.new('ShaderNodeMixShader'); self.put(mx.inputs[0], alpha)
            self.L.new(tr, mx.inputs[1]); self.L.new(em, mx.inputs[2]); em = mx.outputs[0]
        self.L.new(em, out.inputs[0])


def new_material(name):
    m = bpy.data.materials.new(name); m.use_nodes = True; m.node_tree.nodes.clear()
    out = m.node_tree.nodes.new('ShaderNodeOutputMaterial')
    m.surface_render_method = 'DITHERED'
    try: m.use_transparent_shadow = True
    except Exception: pass
    return m, G(m), out


def card_alpha(g, atlas):
    img = bpy.data.images.get(atlas + '.png') or bpy.data.images.load(f'{TEX}/{atlas}.png')
    img.colorspace_settings.name = 'Non-Color'
    tx = g.node('ShaderNodeTexImage'); tx.image = img
    return g.math('GREATER_THAN', tx.outputs['Color'], 0.2), tx


def toon(ramp, alpha=None, var=0.08, grain=0.0, rows=0.0, shift=0.0):
    """the one surface shader. alpha: card atlas. var: per-object ramp shift (clump-to-clump variety).
    grain: noise nudging band edges (+ = stretched vertically like bark, - = blotchy). rows: dark line every n metres
    of object Z (roof tiles). shift: constant offset into the ramp."""
    key = (ramp, alpha, var, grain, rows, shift)
    if key in MATS:
        return MATS[key]
    m, g, out = new_material(f'{ramp}_{alpha or "solid"}')
    fac = g.lit()
    if shift:
        fac = g.math('ADD', fac, shift)
    if var:
        mv = g.node('ShaderNodeMapRange', Value=g.node('ShaderNodeObjectInfo').outputs['Random'])
        mv.inputs['To Min'].default_value, mv.inputs['To Max'].default_value = -var, var
        fac = g.math('ADD', fac, mv.outputs[0])
    if grain:
        n, _ = g.noise(3.0, *((5, 5, .7) if grain > 0 else (.6, .6, .6)), lo=-abs(grain), hi=abs(grain))
        fac = g.math('ADD', fac, n)
    if rows:
        wv = g.node('ShaderNodeTexWave', Vector=g.node('ShaderNodeTexCoord').outputs['Object'], Scale=1.0 / rows,
                    Distortion=0.4, Detail=1.0)
        wv.wave_type, wv.bands_direction, wv.wave_profile = 'BANDS', 'Z', 'SAW'
        fac = g.math('ADD', fac, g.math('MULTIPLY', g.math('GREATER_THAN', wv.outputs['Fac'], .82), -.22))
    if alpha and FOL:   # baked per card by foliage_values(); 0 on anything that wasn't baked
        fac = g.math('ADD', fac, g.math('MULTIPLY', g.attr('crown'), FOL.get('gradient', 0.0)))
        fac = g.math('SUBTRACT', fac, g.math('MULTIPLY', g.math('POWER', g.attr('buried'), FOL.get('value_power', 1.0)),
                                             FOL.get('value', 0.0)))
    a = card_alpha(g, alpha)[0] if alpha else None
    g.emit(g.ramp(ramp, fac), out, a)
    MATS[key] = m
    return m


def shadow_catcher():
    """ground layer: transparent where sunlit, flat shadow colour where not."""
    if 'shadow' in MATS:
        return MATS['shadow']
    m, g, out = new_material('shadow'); m.surface_render_method = 'BLENDED'
    s2r = g.node('ShaderNodeShaderToRGB', Shader=g.node('ShaderNodeBsdfDiffuse').outputs[0])
    bw = g.node('ShaderNodeRGBToBW', Color=s2r.outputs[0]).outputs[0]
    g.emit(lin(STY['shadow']['color']), out, g.math('MULTIPLY', g.math('LESS_THAN', bw, .5), STY['shadow']['alpha']))
    MATS['shadow'] = m
    return m


# ------------------------------------------------------------------ geometry

def link(o):
    COLL.objects.link(o)
    return o


def _card(bm, uvl, p, normal, size, spin=None):
    q = normal.to_track_quat('Z', 'Y') @ Matrix.Rotation(rng.random() * math.tau if spin is None else spin, 4, 'Z').to_quaternion()
    f = bm.faces.new([bm.verts.new(p + q @ Vector((x * size, y * size, 0))) for x, y in ((-1, -1), (1, -1), (1, 1), (-1, 1))])
    t = rng.randrange(4); u0, v0 = (t % 2) * .5, (t // 2) * .5
    for lp, (u, v) in zip(f.loops, ((0, 0), (1, 0), (1, 1), (0, 1))):
        lp[uvl].uv = (u0 + u * .5, v0 + v * .5)


def cards(name, centre, points, mat, sway=True):
    """points = [(offset, card_normal, size, shading_normal)]; one object, origin at centre."""
    me = bpy.data.meshes.new(name); bm = bmesh.new(); uvl = bm.loops.layers.uv.new(); nrm = []
    for p, cn, s, sn in points:
        _card(bm, uvl, p, cn, s); nrm += [sn] * 4
    bm.to_mesh(me); bm.free(); me.normals_split_custom_set(nrm)
    o = bpy.data.objects.new(name, me); o.data.materials.append(mat); o.location = centre
    CARDS[o.name] = dict(c=np.array([tuple(p) for p, *_ in points]), axis=np.array([tuple(cn.normalized()) for _, cn, _, _ in points]),
                         sn=np.array([tuple(sn) for *_, sn in points]), nrm=nrm)
    if sway:
        o['sway'] = 1
    return link(o)


def foliage_values(objs):
    """the tutorial's value step, baked per card over a whole asset: `buried` (0..1) counts the cards lying outward of
    each card within `value_reach` metres (dark pockets between and inside clumps, the AO of the tutorial), `crown`
    (-1..1) is the card's place along the sun direction across all the asset's cards (the light-to-shadow gradient)."""
    if not FOL:
        return
    obs = [o for o in objs if o.name in CARDS]
    if not obs:
        return
    mats = [np.array(o.matrix_basis) for o in obs]   # world = basis: card objects are parentless
    pos = np.concatenate([CARDS[o.name]['c'] @ m[:3, :3].T + m[:3, 3] for o, m in zip(obs, mats)])
    nrm = np.concatenate([CARDS[o.name]['sn'] @ m[:3, :3].T for o, m in zip(obs, mats)])
    nrm /= np.linalg.norm(nrm, axis=1, keepdims=True)
    reach = FOL.get('value_reach', 1.2)
    buried = np.zeros(len(pos))
    for i in range(0, len(pos), 512):   # chunks keep the pair matrix small
        d = pos[None, :, :] - pos[i:i + 512, None, :]
        r = np.linalg.norm(d, axis=2) + 1e-6
        out = np.einsum('ijk,ik->ij', d, nrm[i:i + 512]) / r
        buried[i:i + 512] = ((r < reach) & (out > .35)).sum(1)
    buried = 1 - np.exp(-buried / FOL.get('value_count', 12.0))
    sun = -np.array(tuple(LT))
    along = (pos - pos.mean(0)) @ sun
    crown = along / max(1e-6, np.abs(along).max())
    k = 0
    for o in obs:
        n = len(CARDS[o.name]['c'])
        for name, arr in (('buried', buried[k:k + n]), ('crown', crown[k:k + n])):
            o.data.attributes.new(name, 'FLOAT', 'POINT').data.foreach_set('value', np.repeat(arr, 4).astype(np.float32))
        k += n


def flutter(objs, t):
    """turn every card about its own centre in its own plane, a few degrees on its own phase, swelling as a gust crosses
    the asset (the tutorial's small wind layer). t in [0, 2pi) loops seamlessly; t=None puts the cards back."""
    amp = math.radians(FOL.get('flutter_deg', 0.0))
    if not amp:
        return
    for o in objs:
        d = CARDS.get(o.name)
        if d is None:
            continue
        me = o.data
        if 'base' not in d:
            d['base'] = np.array([v.co[:] for v in me.vertices]).reshape(-1, 4, 3)
            r = random.Random(o.name)
            d['ph'] = np.array([r.random() * math.tau for _ in d['c']]); d['k'] = np.array([r.choice((1, 2, 3)) for _ in d['c']])
        base = d['base']
        if t is None:
            co = base
        else:
            x = d['c'][:, 0] + o.location.x
            a = amp * (.6 + .4 * np.sin(t - x * .6)) * np.sin(d['k'] * t + d['ph'])
            k, v = d['axis'][:, None, :], base - d['c'][:, None, :]
            c, s = np.cos(a)[:, None, None], np.sin(a)[:, None, None]
            co = d['c'][:, None, :] + v * c + np.cross(k, v) * s + k * (v * k).sum(2, keepdims=True) * (1 - c)
        me.vertices.foreach_set('co', co.astype(np.float32).ravel()); me.update()
        me.normals_split_custom_set(d['nrm'])


def clump(name, centre, radius, n, size, mat, squash=1.0, up=0.0, sway=True):
    """n alpha cards in a sphere; each carries the sphere normal (the tutorial's normal transfer)."""
    pts = []
    for _ in range(n):
        d = Vector((rng.gauss(0, 1), rng.gauss(0, 1), rng.gauss(0, 1))).normalized()
        r = radius * (0.55 + 0.45 * rng.random() ** 0.5)
        p = Vector((d.x * r, d.y * r, d.z * r * squash))
        cn = (d + Vector([rng.uniform(-.6, .6) for _ in range(3)])).normalized()
        cn = (cn * .5 - FWD).normalized()           # lean toward the camera so few cards go edge-on
        if FOL.get('face_camera'):                  # the tutorial's billboard: every card square to the camera, like a dab
            cn = -FWD                               # (the lean above still runs, so the rng stream and layout stay put)
        sn = (Vector((d.x, d.y, d.z / max(squash, .3))) + Vector((0, 0, up))).normalized()
        pts.append((p, cn, size * rng.uniform(.75, 1.25), sn))
    return cards(name, centre, pts, mat, sway)


def tufts(name, spots, mat, size=(.22, .4)):
    """upright cards facing the camera, base on the ground, up-tilted normals (grass, flowers, reeds)."""
    me = bpy.data.meshes.new(name); bm = bmesh.new(); uvl = bm.loops.layers.uv.new(); nrm = []
    for x, y, z in spots:
        s = rng.uniform(*size); side = Vector((s, 0, 0))
        b = Vector((x, y, z - .02)); up = UPV * s * 1.5 + Vector((0, 0, s * .4))
        f = bm.faces.new([bm.verts.new(q) for q in (b - side, b + side, b + side + up, b - side + up)])
        t = rng.randrange(4); u0, v0 = (t % 2) * .5, (t // 2) * .5
        for lp, (u, v) in zip(f.loops, ((0, 0), (1, 0), (1, 1), (0, 1))):
            lp[uvl].uv = (u0 + u * .5, v0 + v * .5)
        nrm += [Vector((rng.uniform(-.7, .7), rng.uniform(-.9, .3), 1)).normalized()] * 4
    bm.to_mesh(me); bm.free(); me.normals_split_custom_set(nrm)
    o = bpy.data.objects.new(name, me); o.data.materials.append(mat)
    return link(o)


def tube(name, pts, radii, mat, res=8):
    cu = bpy.data.curves.new(name, 'CURVE'); cu.dimensions = '3D'; cu.bevel_depth = 1.0; cu.bevel_resolution = 3
    cu.use_fill_caps = True; cu.resolution_u = res
    sp = cu.splines.new('BEZIER'); sp.bezier_points.add(len(pts) - 1)
    for bp, p, r in zip(sp.bezier_points, pts, radii):
        bp.co = p; bp.radius = r; bp.handle_left_type = bp.handle_right_type = 'AUTO'
    o = bpy.data.objects.new(name, cu); o.data.materials.append(mat)
    return link(o)


def box(name, centre, size, mat, rot=0.0, bevel=0.03, tilt=(0, 0)):
    me = bpy.data.meshes.new(name); bm = bmesh.new(); bmesh.ops.create_cube(bm, size=1.0); bm.to_mesh(me); bm.free()
    o = bpy.data.objects.new(name, me); o.data.materials.append(mat)
    o.location = centre; o.scale = size; o.rotation_euler = (tilt[0], tilt[1], rot)
    if bevel:
        bv = o.modifiers.new('bv', 'BEVEL'); bv.width = bevel; bv.segments = 2; bv.use_clamp_overlap = True
    return link(o)


def blob(name, centre, radii, mat, cut_below=None, seg=24):
    """smooth ellipsoid (animal bodies, heads); cut_below drops the part under a z (a body floating on water)."""
    me = bpy.data.meshes.new(name); bm = bmesh.new()
    bmesh.ops.create_uvsphere(bm, u_segments=seg, v_segments=seg // 2, radius=1.0)
    for v in bm.verts:
        v.co = Vector((v.co.x * radii[0], v.co.y * radii[1], v.co.z * radii[2]))
    if cut_below is not None:
        bmesh.ops.bisect_plane(bm, geom=bm.verts[:] + bm.edges[:] + bm.faces[:], plane_co=(0, 0, cut_below - centre[2]),
                               plane_no=(0, 0, 1), clear_inner=True)
    for f in bm.faces: f.smooth = True
    bm.to_mesh(me); bm.free()
    o = bpy.data.objects.new(name, me); o.data.materials.append(mat); o.location = centre
    return link(o)


def poly(name, verts, faces, mat, bulge=None, k=.5, cuts=8):
    """flat polygon; bulge=(x,y,z) subdivides it and bends its normals toward that centre (painted-mass shading)."""
    me = bpy.data.meshes.new(name); me.from_pydata(verts, [], faces); me.update()
    if bulge is not None:
        bm = bmesh.new(); bm.from_mesh(me)
        bmesh.ops.subdivide_edges(bm, edges=bm.edges[:], cuts=cuts, use_grid_fill=True)
        bm.to_mesh(me); bm.free()
        fn = me.polygons[0].normal.copy(); c = Vector(bulge)
        me.normals_split_custom_set_from_vertices([(fn + (Vector(v.co) - c).normalized() * k).normalized() for v in me.vertices])
    o = bpy.data.objects.new(name, me); o.data.materials.append(mat)
    return link(o)


# ------------------------------------------------------------------ framing + render

def screen(p):
    return Vector((p.x, p.dot(UPV)))


def frame_bbox(objs, margin, with_shadow=True):
    dg = bpy.context.evaluated_depsgraph_get()
    xs, vs = [], []
    for o in objs:
        if o.type not in ('MESH', 'CURVE'):
            continue
        ev = o.evaluated_get(dg); me = ev.to_mesh()
        for v in me.vertices:
            w = ev.matrix_world @ v.co
            s = screen(w); xs.append(s.x); vs.append(s.y)
            if with_shadow and w.z > 0:
                s = screen(w + LT * (w.z / -LT.z)); xs.append(s.x); vs.append(s.y)
        ev.to_mesh_clear()
    m = margin / PPM
    return min(xs) - m, max(xs) + m, min(vs) - m, max(vs) + m


def set_camera(x0, x1, v0, v1):
    """frame screen rect [x0,x1] x [v0,v1] (metres); returns (w, h, anchor) where anchor = pixel of world origin."""
    rx, ry = int(math.ceil((x1 - x0) * PPM / 2) * 2), int(math.ceil((v1 - v0) * PPM / 2) * 2)
    cx, cv = (x0 + x1) / 2, (v0 + v1) / 2
    cam.ortho_scale = max(rx, ry) / PPM
    co.location = Vector((cx, cv * math.sin(E), cv * math.cos(E))) - FWD * 200
    sc.render.resolution_x, sc.render.resolution_y, sc.render.resolution_percentage = rx, ry, 100
    return rx, ry, (round(-cx * PPM + rx / 2, 1), round(ry / 2 + cv * PPM, 1))


def render(path):
    sc.render.filepath = path
    bpy.ops.render.render(write_still=True)


def shadow_plane():
    sp = bpy.data.objects.new('shadowplane', bpy.data.meshes.new('sp'))
    bm = bmesh.new(); bmesh.ops.create_grid(bm, x_segments=1, y_segments=1, size=30); bm.to_mesh(sp.data); bm.free()
    sp.data.materials.append(shadow_catcher())
    return link(sp)


def self_shadow(objs, on):
    """foliage.self_shadow false (the tutorial's per-material shadow switch): cards don't shade the asset they belong to,
    so a crown reads by its own clumps and values instead of one cast-shadow block. They still cast onto the ground."""
    if FOL.get('self_shadow', True):
        return
    for o in objs:
        if o.name in CARDS and not o.get('shades_self'):
            o.visible_shadow = on


def two_pass(stem, body, sp):
    """body pass (no ground) + shadow pass (ground only; body hidden from camera but still casting)."""
    sp.hide_render = True
    self_shadow(body, False)
    render(stem + '.png')
    self_shadow(body, True)
    sp.hide_render = False
    for o in body: o.visible_camera = False
    render(stem + '_shadow.png')
    for o in body: o.visible_camera = True


def begin(name):
    global COLL
    COLL = bpy.data.collections.new(name); sc.collection.children.link(COLL)
    return COLL


def end():
    CARDS.clear()
    for o in list(COLL.objects):
        bpy.data.objects.remove(o)
    bpy.data.collections.remove(COLL)

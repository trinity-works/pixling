"""The walker of First Snow built in Blender with the painted-cards light, rendered as DATA for fp/paint3d.py.

Run by `python3 -m fp paint` (blender -b -P this.py -- WORK SAMPLES, or a python with the bpy module).
A round hood with her face in its opening, a plum A-line coat, a dark pack, the pink scarf wrapped at the neck, dark
legs and boots, a suitcase in her left hand. Every part is a soft primitive with sphere normals (so it shades as one
mass, like the painted engine's clumps), lit by the scene's own low sun from behind-left and the sky fill, so she has
the same rim and the same dark back as the spruces and the car.

One render holds every heading and pose (ortho camera, the scene's slight downward look): a row per heading (N: walking
away into the picture, then clockwise NE, E, SE, S toward us, SW, W, NW; she turns, the light stays), a column per pose
(four walk poses: contact L, pass, contact R, pass; standing with the case; standing with the case set down). Two passes:
    walker.npy       R = lit value (sun + sky, shadows), G = material id / 64, A = coverage
    walker_lamp.npy  R = the headlamps' light alone (from her left, low), for the mint pickup at the hold
WORK/raw/walker.json records where each figure's feet are in the render (px, heading-major) and the scale (px per
metre), and where her scarf's knot and her mouth are on her (right, forward, up in metres) for the runtime.
"""
import bpy, bmesh, sys, json, math
from bpy_extras.object_utils import world_to_camera_view
from pathlib import Path
import numpy as np
from mathutils import Vector, Matrix

argv = sys.argv[sys.argv.index('--') + 1:] if '--' in sys.argv else sys.argv[1:]
WORK = Path(argv[0])
SAMPLES = int(argv[1]) if len(argv) > 1 else 1
S = json.load(open(WORK / 'scene3d.json'))
LX, LY_, LZ = S['LIGHT']
SUN = Vector((LX, LZ, LY_)).normalized()             # toward the sun, Blender axes (x right, y into the picture, z up)
LAMP = Vector((-0.9, 0.25, 0.2)).normalized()        # toward the headlamps when she stands by the nose: her left, low
MID = dict(coat=1, hood=2, scarf=3, pack=4, leg=5, boot=6, case=7, face=8)
POSES = ['c0', 'p0', 'c1', 'p1', 'idle', 'down']
HEADINGS = 8                                         # turns of 45 degrees, clockwise from walking away (N)
GAP = 1.2                                            # metres between poses in the render
ROW = 1.8                                            # metres between headings (one above the other)
KNOT = (0.1, -0.1, 0.97)                             # the scarf's knot on her (right, forward, up), the tail's root
MOUTH = (0.0, 0.17, 1.1)                             # where her breath leaves her
PXM = 200                                            # render px per metre
TILT = math.radians(7.0)                             # the scene camera looks down on her a little

bpy.ops.wm.read_factory_settings(use_empty=True)
sc = bpy.context.scene
MATS = {}


def dmat(mid):
    if mid in MATS:
        return MATS[mid]
    m = bpy.data.materials.new(f'w{mid}')
    m.use_nodes = True
    N, L = m.node_tree.nodes, m.node_tree.links
    N.clear()
    out = N.new('ShaderNodeOutputMaterial')
    d = N.new('ShaderNodeBsdfDiffuse'); d.inputs['Color'].default_value = (1, 1, 1, 1)
    s2r = N.new('ShaderNodeShaderToRGB'); L.new(d.outputs[0], s2r.inputs[0])
    bw = N.new('ShaderNodeRGBToBW'); L.new(s2r.outputs[0], bw.inputs[0])
    mul = N.new('ShaderNodeMath'); mul.operation = 'MULTIPLY_ADD'
    L.new(bw.outputs[0], mul.inputs[0]); mul.inputs[1].default_value = 0.4; mul.inputs[2].default_value = 0.2
    mul.use_clamp = True
    comb = N.new('ShaderNodeCombineRGB')
    L.new(mul.outputs[0], comb.inputs[0]); comb.inputs[1].default_value = mid / 64.0
    em = N.new('ShaderNodeEmission'); L.new(comb.outputs[0], em.inputs[0])
    L.new(em.outputs[0], out.inputs[0])
    MATS[mid] = m
    return m


def sphere_normals(me, centre, mass=0.7):
    """every vertex's normal leans toward the part's centre-out direction: the part shades as one soft mass"""
    nl = []
    for p in me.polygons:
        for li in p.loop_indices:
            v = me.vertices[me.loops[li].vertex_index]
            n = (v.co - centre).normalized() * mass + v.normal * (1 - mass)
            nl.append(n.normalized())
    me.normals_split_custom_set(nl)


def part(name, bm, mat, centre, mass=0.7):
    me = bpy.data.meshes.new(name); bm.to_mesh(me); bm.free()
    for p in me.polygons:
        p.use_smooth = True
    sphere_normals(me, centre, mass)
    o = bpy.data.objects.new(name, me); o.data.materials.append(dmat(MID[mat]))
    sc.collection.objects.link(o)
    return o


def ellipsoid(name, c, r, mat, seg=20, mass=0.8):
    bm = bmesh.new()
    bmesh.ops.create_uvsphere(bm, u_segments=seg, v_segments=seg // 2, radius=1.0)
    for v in bm.verts:
        v.co = Vector((c.x + v.co.x * r[0], c.y + v.co.y * r[1], c.z + v.co.z * r[2]))
    return part(name, bm, mat, c, mass)


def frustum(name, c0, c1, r0, r1, mat, seg=20, depth=0.8, mass=0.55):
    """a tapered tube from c0 (radius r0) to c1 (radius r1), flattened front-to-back by `depth`"""
    bm = bmesh.new()
    bmesh.ops.create_cone(bm, cap_ends=True, segments=seg, radius1=1.0, radius2=1.0, depth=1.0)
    ax = (c1 - c0)
    L_ = ax.length
    q = ax.normalized().to_track_quat('Z', 'Y')
    for v in bm.verts:
        t = v.co.z + 0.5
        r = r0 + (r1 - r0) * t
        loc = Vector((v.co.x * r, v.co.y * r * depth, (t - 0.5) * L_))
        v.co = (c0 + c1) / 2 + q @ loc
    return part(name, bm, mat, (c0 + c1) / 2, mass)


def rbox(name, c, s, mat, bevel=0.03, mass=0.4):
    bm = bmesh.new()
    bmesh.ops.create_cube(bm, size=1.0)
    for v in bm.verts:
        v.co = Vector((c.x + v.co.x * s[0], c.y + v.co.y * s[1], c.z + v.co.z * s[2]))
    bmesh.ops.bevel(bm, geom=bm.edges[:] + bm.verts[:], offset=bevel, segments=2, affect='EDGES', clamp_overlap=True)
    return part(name, bm, mat, c, mass)


def figure(i, pose, hd):
    """one pose of her at heading hd: built facing +y (into the picture, seen from behind) with her feet at the origin,
    then turned and moved to her cell (column i, row hd). Returns where her feet stand."""
    O = Vector((0, 0, 0))
    k = f'{hd}{pose}_'
    first = len(sc.collection.objects)
    # legs: thigh+shin as one tapered tube from the hip; a contact pose swings one forward (away from us) and lifts
    # the back heel, a pass pose lifts one knee
    swing = {'c0': (0.42, -0.36), 'c1': (-0.36, 0.42), 'p0': (0.05, -0.02), 'p1': (-0.02, 0.05)}.get(pose, (0, 0))
    lift = {'p0': (0.0, 0.07), 'p1': (0.07, 0.0)}.get(pose, (0, 0))
    hipz = 0.40
    for s, (ang, up) in zip((-1, 1), zip(swing, lift)):
        hip = O + Vector((s * 0.075, 0, hipz))
        foot = hip + Vector((0, math.sin(ang) * hipz, -math.cos(ang) * hipz + up))
        frustum(k + f'leg{s}', hip, foot + Vector((0, 0, 0.06)), 0.07, 0.055, 'leg', seg=12, depth=1.0)
        ellipsoid(k + f'boot{s}', foot + Vector((0, 0.03, 0.045)), (0.065, 0.1, 0.05), 'boot', seg=12)
    # the coat: an A-line from the collar to just below the knee, a little wider at the hem, flattened front-to-back
    frustum(k + 'coat', O + Vector((0, 0, 0.33)), O + Vector((0, 0, 0.98)), 0.25, 0.14, 'coat', depth=0.72, mass=0.6)
    ellipsoid(k + 'shoulders', O + Vector((0, 0, 0.9)), (0.19, 0.13, 0.09), 'coat', mass=0.7)
    # the pack on her back (toward us), rounded, smaller than the back so the coat frames it
    rbox(k + 'pack', O + Vector((0.01, -0.13, 0.72)), (0.17, 0.07, 0.18), 'pack', bevel=0.04)
    # the scarf wrapped at the neck: a fat ring, wider than the hood's foot, with the knot on her right
    bm = bmesh.new()
    bmesh.ops.create_cone(bm, cap_ends=True, segments=20, radius1=0.16, radius2=0.14, depth=0.11)
    for v in bm.verts:
        v.co = Vector((v.co.x, v.co.y * 0.85, v.co.z + 0.99))
    part(k + 'scarf', bm, 'scarf', O + Vector((0, 0, 0.99)), mass=0.8)
    ellipsoid(k + 'knot', O + Vector(KNOT), (0.06, 0.05, 0.06), 'scarf', seg=12)
    # the hood: a round mass sitting down into the scarf
    ellipsoid(k + 'hood', O + Vector((0, 0.01, 1.15)), (0.145, 0.14, 0.15), 'hood', mass=0.85)
    # the arms hang inside the coat's line; the left hand holds the case off the snow, swinging with the step
    sw = {'c0': -0.05, 'c1': 0.05}.get(pose, 0.0)
    # (the case turned a little, so its broad side shows)
    if pose == 'down':
        rbox(k + 'case', O + Vector((-0.42, 0.02, 0.12)), (0.24, 0.1, 0.24), 'case', bevel=0.025)
        frustum(k + 'arm', O + Vector((-0.17, 0, 0.88)), O + Vector((-0.21, 0.0, 0.52)), 0.065, 0.055, 'coat', seg=10)
    else:
        hand = O + Vector((-0.25, sw, 0.43))
        frustum(k + 'arm', O + Vector((-0.17, 0, 0.88)), hand + Vector((0, 0, 0.04)), 0.065, 0.055, 'coat', seg=10)
        rbox(k + 'case', hand + Vector((-0.1, 0, -0.15)), (0.22, 0.1, 0.22), 'case', bevel=0.025)
    frustum(k + 'armr', O + Vector((0.17, 0, 0.88)), O + Vector((0.21, 0.02, 0.5)), 0.065, 0.055, 'coat', seg=10)
    # her face in the hood's opening (seen from the front and the sides), a little proud of the hood
    ellipsoid(k + 'face', O + Vector((0, 0.115, 1.13)), (0.085, 0.055, 0.085), 'face', seg=12)
    feet = Vector(((i - (len(POSES) - 1) / 2) * GAP, 0, (hd - (HEADINGS - 1) / 2) * -ROW))
    turn = Matrix.Translation(feet) @ Matrix.Rotation(-hd * math.tau / HEADINGS, 4, 'Z')
    for o in list(sc.collection.objects)[first:]:
        o.matrix_world = turn
    return feet


feet = [figure(i, p, hd) for hd in range(HEADINGS) for i, p in enumerate(POSES)]

# light and camera: the scene's low sun from behind-left and the sky fill; an ortho camera with the scene's look down
sun = bpy.data.lights.new('sun', 'SUN'); sun.energy = math.pi; sun.angle = math.radians(1.0)
so = bpy.data.objects.new('sun', sun); sc.collection.objects.link(so)
so.rotation_euler = (-SUN).to_track_quat('-Z', 'Y').to_euler()
world = bpy.data.worlds.new('w'); sc.world = world; world.use_nodes = True
bg = world.node_tree.nodes['Background']
bg.inputs[0].default_value = (1, 1, 1, 1); bg.inputs[1].default_value = 0.28
d = Vector((0, math.cos(TILT), -math.sin(TILT)))
cam = bpy.data.cameras.new('cam'); cam.type = 'ORTHO'; cam.sensor_fit = 'HORIZONTAL'
WM, HM = GAP * len(POSES), ROW * HEADINGS            # the frame (m): a cell per figure
cam.ortho_scale = WM
co = bpy.data.objects.new('cam', cam); sc.collection.objects.link(co); sc.camera = co
co.location = Vector((0, 0, 0.66)) - 10 * d         # centred on the stack of rows (feet -6.3 .. heads +7.6 m)
co.rotation_euler = (math.pi / 2 - TILT, 0, 0)
sc.render.engine = 'BLENDER_EEVEE_NEXT'
sc.eevee.taa_render_samples = SAMPLES
sc.eevee.use_shadows = False      # sphere normals give the form; tiny self-shadows only blotch
sc.render.filter_size = 0.0
sc.render.dither_intensity = 0.0
sc.render.film_transparent = True
sc.view_settings.view_transform = 'Raw'
sc.view_settings.look = 'None'
sc.render.resolution_x, sc.render.resolution_y = int(WM * PXM), int(HM * PXM)
sc.render.resolution_percentage = 100
st = sc.render.image_settings
st.file_format = 'PNG'; st.color_mode = 'RGBA'; st.color_depth = '16'
(WORK / 'raw').mkdir(exist_ok=True)


def shoot(name):
    sc.render.filepath = str(WORK / 'raw' / f'{name}.png')
    bpy.ops.render.render(write_still=True)
    img = bpy.data.images.load(sc.render.filepath); img.colorspace_settings.name = 'Non-Color'
    w, h = img.size
    px = np.empty(w * h * 4, np.float32); img.pixels.foreach_get(px)
    np.save(WORK / 'raw' / f'{name}.npy', px.reshape(h, w, 4)[::-1].astype(np.float16))
    bpy.data.images.remove(img)
    print('fp paint: rendered', name, flush=True)


shoot('walker')
so.rotation_euler = (-LAMP).to_track_quat('-Z', 'Y').to_euler()     # the lamps' light alone
bg.inputs[1].default_value = 0.0
shoot('walker_lamp')
# where each figure's feet land in the render (px), heading-major
RX, RY = sc.render.resolution_x, sc.render.resolution_y
px = [world_to_camera_view(sc, co, f) for f in feet]
json.dump(dict(poses=POSES, headings=HEADINGS, pxm=PXM, feet=[[p.x * RX, (1 - p.y) * RY] for p in px],
               cell=[GAP * PXM, ROW * math.cos(TILT) * PXM], knot=KNOT, mouth=MOUTH),
          open(WORK / 'raw' / 'walker.json', 'w'))

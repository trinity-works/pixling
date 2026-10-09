"""Render a painted kit as game sprites at the style's one camera. Normally run through `python3 -m painted kit`.
blender -b -P painted/bpy/kit.py -- STYLE.json LAYOUT.json TEXDIR OUTDIR [asset ...]   (no asset names = everything)

Per static asset: <name>.png (body), <name>_shadow.png (ground-shadow layer), <name>.json (anchor = ground-origin pixel).
Trees/bushes add <name>_sway/fNN[_shadow].png (32-frame loop). Animals: <name>/dD_fNN.png, 8 headings x 8 frames.
`ground` renders the layout's ground plate (painted lane, footpath, pond) as ground/fNN.png with moving glints."""
import sys, os, json, math
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import bpy
from mathutils import Vector
import painter as P
import assets as A   # noqa: E402  (painter must be configured before assets build)

argv = sys.argv[sys.argv.index('--') + 1:]
STYLE, LAYOUT, TEX, OUT, ONLY = argv[0], argv[1], argv[2], argv[3], argv[4:]
os.makedirs(OUT, exist_ok=True)
P.configure(STYLE, LAYOUT)
P.setup(TEX)
SWAY_FRAMES, ANIMAL_FRAMES, CHAR_FRAMES = 32, 8, 16


def save_meta(name, **kw):
    json.dump(dict(name=name, ppm=P.PPM, **kw), open(os.path.join(OUT, name + '.json'), 'w'))


def static(name, build, sway):
    P.begin(name); build()
    body = list(P.COLL.objects)
    P.foliage_values(body)
    sp = P.shadow_plane()
    w, h, anchor = P.set_camera(*P.frame_bbox(body, 14 if sway else 6))
    stem = os.path.join(OUT, name)
    P.two_pass(stem, body, sp)
    meta = dict(w=w, h=h, anchor=anchor)
    if sway:   # a slow gust: the crown leans once per loop, clumps nod twice on their own phases (seamless)
        cl = [o for o in body if o.get('sway')]
        rest = {o.name: (o.location.copy(), o.rotation_euler.copy()) for o in cl}
        ph = {o.name: P.rng.random() * math.tau for o in cl}
        sp.hide_render = True
        P.self_shadow(body, False)
        os.makedirs(stem + '_sway', exist_ok=True)
        for f in range(SWAY_FRAMES):
            t = f / SWAY_FRAMES * math.tau
            for o in cl:
                l0, r0 = rest[o.name]; hgt = max(0, l0.z) / 6; p = ph[o.name]
                o.rotation_euler = (r0.x + math.radians(1.2 * math.sin(2 * t + p)), r0.y + math.radians(1.8 * math.sin(t + p * .3)), 0)
                o.location = l0 + Vector((.09 * hgt * (math.sin(t) + .3 * math.sin(2 * t + p)), 0, .012 * math.sin(2 * t + p)))
            P.flutter(cl, t)
            P.render(os.path.join(stem + '_sway', f'f{f:02d}.png'))
        for o in cl:
            o.location, o.rotation_euler = rest[o.name]
        P.flutter(cl, None)
        P.self_shadow(body, True)
        meta['sway_frames'] = SWAY_FRAMES
    save_meta(name, **meta)
    P.end()


def animal(name, build):
    """8 headings (0 = facing +x / screen right, counter-clockwise) x 8 paddle frames: bob, nod, two ripple rings."""
    P.begin(name)
    root, rings, ring_r = build()
    nod = [o for o in root.children if o.get('nod')]
    nod0 = {o.name: o.location.copy() for o in nod}
    parts = list(root.children) + rings
    boxes = []
    for d in range(8):   # one frame size for every heading
        root.rotation_euler.z = d * math.pi / 4
        bpy.context.view_layer.update()
        boxes.append(P.frame_bbox(parts, 4, with_shadow=False))
    x0, x1 = min(b[0] for b in boxes), max(b[1] for b in boxes)
    v0, v1 = min(b[2] for b in boxes), max(b[3] for b in boxes)
    m = ring_r * .7
    w, h, anchor = P.set_camera(x0 - m, x1 + m, v0 - m * .8, v1)
    os.makedirs(os.path.join(OUT, name), exist_ok=True)
    for d in range(8):
        yaw = d * math.pi / 4
        for f in range(ANIMAL_FRAMES):
            t = f / ANIMAL_FRAMES * math.tau
            root.rotation_euler = (0, .05 * math.sin(t), yaw)
            root.location.z = .01 * math.sin(t)
            for o in nod:
                o.location = nod0[o.name] + Vector((.015 * math.sin(t + 1), 0, -.008 * math.sin(t + 1)))
            for k, r in enumerate(rings):   # rings spread out and are replaced, half a cycle apart
                u = ((f + k * ANIMAL_FRAMES / 2) % ANIMAL_FRAMES) / ANIMAL_FRAMES
                r.scale = (ring_r * (1 + .75 * u),) * 3
                r.hide_render = u > .62
            P.render(os.path.join(OUT, name, f'd{d}_f{f:02d}.png'))
    save_meta(name, w=w, h=h, anchor=anchor, directions=8, frames=ANIMAL_FRAMES)
    P.end()


def pose(rig, clip, f):
    """walk: 16 frames, two steps; thighs swing, the swing shin folds, arms counter-swing, cape trails.
    idle: 16 frames of breathing. Afterwards the pelvis drops/rises so the lower boot touches the ground."""
    t = f / CHAR_FRAMES * math.tau
    pel = rig['pelvis']
    pel.location = Vector((0, 0, .8)); pel.rotation_euler = (0, 0, 0)
    wave = 0.0
    if clip == 'walk':
        pel.rotation_euler = (0, math.radians(5), math.radians(4 * math.sin(t)))
        for k, (hip, knee) in enumerate(zip(rig['hips'], rig['knees'])):
            ph = t + k * math.pi
            hip.rotation_euler = (0, -math.radians(27 * math.sin(ph)), 0)
            knee.rotation_euler = (0, math.radians(6 + 52 * max(0.0, math.cos(ph)) ** 1.4), 0)
        for k, (sh, el) in enumerate(zip(rig['shoulders'], rig['elbows'])):
            ph = t + k * math.pi
            sh.rotation_euler = (0, math.radians(22 * math.sin(ph)), 0)
            el.rotation_euler = (0, -math.radians(18 + 10 * max(0.0, -math.sin(ph))), 0)
        rig['neck'].rotation_euler = (0, -math.radians(4), math.radians(-3 * math.sin(t)))
        trail, wave = .09 + .03 * math.sin(2 * t), .025 * math.sin(t)
    else:
        b = math.sin(t)
        pel.rotation_euler = (0, math.radians(1), 0)
        for k, (hip, knee) in enumerate(zip(rig['hips'], rig['knees'])):
            hip.rotation_euler = (math.radians(3 * (1 if k else -1)), 0, 0); knee.rotation_euler = (0, math.radians(3), 0)
        for k, (sh, el) in enumerate(zip(rig['shoulders'], rig['elbows'])):
            sh.rotation_euler = (math.radians(4 * (1 if k else -1)), math.radians(2 * b), 0)
            el.rotation_euler = (0, -math.radians(12), 0)
        rig['neck'].rotation_euler = (0, math.radians(2 * b), math.radians(1.5 * math.sin(t * .5)))
        pel.location.z += .006 * b
        trail = .02 + .01 * b
    me, R, C = rig['cape'].data, rig['cape_rows'], rig['cape_cols']
    for i in range(R):
        f2 = i / (R - 1)
        for j in range(C):
            v = rig['cape_rest'][i * C + j]
            side = v.y / .33
            me.vertices[i * C + j].co = v + Vector((-trail * f2 ** 1.5, wave * f2 * (1 - abs(side)), .02 * trail * f2))
    me.update()
    bpy.context.view_layer.update()
    low = min((b.matrix_world @ Vector((0, 0, -.05))).z for b in rig['boots'])
    pel.location.z -= low - .02
    bpy.context.view_layer.update()


def character(name, build):
    """8 headings x {walk, idle} x 16 frames, body + shadow layer each."""
    P.begin(name)
    rig = build(); root = rig['root']
    body = [o for o in P.COLL.objects if o.type in ('MESH', 'CURVE')]
    sp = P.shadow_plane()
    boxes = []
    for d in range(8):
        root.rotation_euler.z = d * math.pi / 4
        for clip, f in (('walk', 0), ('walk', 4), ('idle', 0)):
            pose(rig, clip, f); boxes.append(P.frame_bbox(body, 6))
    w, h, anchor = P.set_camera(min(b[0] for b in boxes), max(b[1] for b in boxes), min(b[2] for b in boxes), max(b[3] for b in boxes))
    os.makedirs(os.path.join(OUT, name), exist_ok=True)
    for d in range(8):
        root.rotation_euler.z = d * math.pi / 4
        for clip in ('walk', 'idle'):
            for f in range(CHAR_FRAMES):
                pose(rig, clip, f)
                P.two_pass(os.path.join(OUT, name, f'{clip}_d{d}_f{f:02d}'), body, sp)
    save_meta(name, w=w, h=h, anchor=anchor, directions=8, frames=CHAR_FRAMES, clips=['walk', 'idle'])
    P.end()


def ground():
    lay = P.LAYOUT['plate']
    P.begin('ground'); A.ground()
    w, h, anchor = P.set_camera(lay['x'][0], lay['x'][1], lay['v'][0], lay['v'][1])
    P.sc.render.film_transparent = False
    os.makedirs(os.path.join(OUT, 'ground'), exist_ok=True)
    for f in range(lay['frames']):   # only the glint layer moves: its noise slides around a small circle (seamless)
        t = f / lay['frames'] * math.tau
        P.GLINT_MAP.inputs['Location'].default_value = (math.cos(t) * .5, math.sin(t) * .5, 0)
        P.render(os.path.join(OUT, 'ground', f'f{f:02d}.png'))
    P.sc.render.film_transparent = True
    save_meta('ground', w=w, h=h, anchor=anchor, frames=lay['frames'],
              elevation_deg=P.STY['camera']['elevation_deg'], plate=lay)
    P.end()


everything = list(A.TREES) + list(A.STATIC) + list(A.ANIMALS) + list(A.CHARACTERS) + ['ground']
for name in ONLY or everything:
    if name == 'ground':
        ground()
    elif name in A.CHARACTERS:
        character(name, A.CHARACTERS[name])
    elif name in A.ANIMALS:
        animal(name, A.ANIMALS[name])
    else:
        static(name, A.TREES.get(name) or A.STATIC[name], name in A.TREES)
    print('built', name, flush=True)

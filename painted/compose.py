"""Lay out layout.json from kit sprites, the way a game draws it: ground plate (animated water), every shadow layer,
then bodies and animals sorted far to near. Trees sway on their own phase; the ducks swim laps of the pond.
Normally `python3 -m painted compose`; directly: python3 painted/compose.py KITDIR OUTDIR LAYOUT.json [keep]
->  scene.png, scene.mp4 (needs ffmpeg), kit_sheet.png; scene_frames/ stays only with `keep` (or without ffmpeg)"""
import sys, json, math, random, shutil, subprocess
from pathlib import Path
from PIL import Image, ImageDraw

KIT, OUT = Path(sys.argv[1]), Path(sys.argv[2])
(OUT / 'scene_frames').mkdir(parents=True, exist_ok=True)
LAY = json.loads(Path(sys.argv[3]).read_text())
meta = {p.stem: json.loads(p.read_text()) for p in KIT.glob('*.json')}
G = meta['ground']; PPM, E = G['ppm'], math.radians(G['elevation_deg'])
X0, V0 = LAY['plate']['x'][0], LAY['plate']['v'][0]
cache = {}


def img(rel):
    if rel not in cache:
        cache[rel] = Image.open(KIT / rel).convert('RGBA')
    return cache[rel]


def to_px(x, y):
    return (x - X0) * PPM, G['h'] - (y * math.sin(E) - V0) * PPM


def blit(canvas, rel, name, x, y):
    m = meta[name]; px, py = to_px(x, y)
    canvas.alpha_composite(img(rel), (int(round(px - m['anchor'][0])), int(round(py - m['anchor'][1]))))


rnd = random.Random(4)
PLACE = [(n, x, y, rnd.randrange(12)) for n, x, y in LAY['place']]
DK = LAY['ducks']; N = DK['lap_frames']; R = DK['route']
SWAY_LOOPS = 4   # gusts per duck lap: whole loops keep the scene seamless


def duck_states(f):
    """drake leads, ducklings trail on the same oval; heading picks one of 8 sprite directions."""
    out = []
    for k in range(DK['ducklings'] + 1):
        a = f / N * math.tau + (0 if k == 0 else -.32 - .2 * k)
        x, y = R['centre'][0] + R['rx'] * math.cos(a), R['centre'][1] + R['ry'] * math.sin(a)
        hx, hy = -R['rx'] * math.sin(a), R['ry'] * math.cos(a)
        d = int(round(math.atan2(hy, hx) / (math.pi / 4))) % 8
        name = 'drake' if k == 0 else 'duckling'
        out.append((y, name, f'{name}/d{d}_f{(f + 3 * k) % 8:02d}.png', x))
    return out


def frame(f):
    canvas = img(f'ground/f{f % G["frames"]:02d}.png').copy()
    bodies = []
    for name, x, y, ph in PLACE:
        sw = meta[name].get('sway_frames')   # the shadow is the rest pose; the body sways SWAY_LOOPS times per scene loop
        blit(canvas, name + '_shadow.png', name, x, y)
        body = f'{name}_sway/f{(f * sw * SWAY_LOOPS // N + ph) % sw:02d}.png' if sw else name + '.png'
        bodies.append((y, name, body, x))
    bodies += duck_states(f)
    for y, name, rel, x in sorted(bodies, key=lambda b: -b[0]):
        blit(canvas, rel, name, x, y)
    return canvas


for f in range(N):
    fr = frame(f).convert('RGB')
    fr.save(OUT / 'scene_frames' / f'f{f:03d}.png')
    if f == 0:
        fr.save(OUT / 'scene.png')


KEEP = len(sys.argv) > 4 and sys.argv[4] == 'keep'
if shutil.which('ffmpeg'):   # one seamless loop as a video; the 120 full-size frames are ~300 MB of PNG
    subprocess.run(['ffmpeg', '-v', 'error', '-y', '-framerate', '10', '-i', str(OUT / 'scene_frames' / 'f%03d.png'),
                    '-c:v', 'libx264', '-pix_fmt', 'yuv420p', '-crf', '16', str(OUT / 'scene.mp4')], check=True)
    if not KEEP:
        shutil.rmtree(OUT / 'scene_frames')

# ---------------------------------------------------------------- kit contact sheet
TURF = (91, 152, 71, 255)
names = ['oak', 'maple', 'poplar', 'pine', 'bush', 'rock', 'flowers', 'well', 'house', 'fence_x', 'fence_y']
tiles = []
for n in names:
    t = Image.new('RGBA', img(n + '.png').size, TURF)
    t.alpha_composite(img(n + '_shadow.png')); t.alpha_composite(img(n + '.png'))
    tiles.append((n, t))
WATER = (75, 152, 170, 255)
for n in ('drake', 'duckling'):   # the animals: 8 headings, shown 4x
    m = meta[n]; t = Image.new('RGBA', (m['w'] * 8, m['h']), WATER)
    for d in range(8):
        t.alpha_composite(img(f'{n}/d{d}_f00.png'), (d * m['w'], 0))
    tiles.append((n + ' (8 headings, 4x)', t.resize((t.width * 4, t.height * 4), Image.NEAREST)))
rows, cur, w = [], [], 0
for n, t in tiles:
    if w + t.width > 1600 and cur:
        rows.append(cur); cur, w = [], 0
    cur.append((n, t)); w += t.width + 16
rows.append(cur)
sheet = Image.new('RGBA', (1600, sum(max(t.height for _, t in r) + 30 for r in rows)), TURF)
d = ImageDraw.Draw(sheet); y = 0
for r in rows:
    x = 0; rh = max(t.height for _, t in r)
    for n, t in r:
        sheet.alpha_composite(t, (x, y + rh - t.height)); d.text((x + 6, y + rh + 8), n, fill=(240, 244, 226, 255)); x += t.width + 16
    y += rh + 30
sheet.convert('RGB').save(OUT / 'kit_sheet.png')
print('ok', N, 'frames', sheet.size)

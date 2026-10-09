"""Pack kit sprites + layout.json into a walkable web scene (game/): WebP sheets, data.json, index.html.
Normally `python3 -m painted game`; directly: python3 painted/build_game.py KITDIR OUTDIR LAYOUT.json [PP_SPRITE_DIR ...]
(pp pixel characters to drop in, e.g. out/ranger)
- static shadows (trees use their rest shadow) are baked into the ground plate; only the hero's shadow is drawn live
- the water animation is the ground frames cropped to the pond, shadows baked in the same way
- trees: one strip of sway frames; hero: walk/idle sheets (rows = 8 headings, cols = frames) + matching shadow sheets"""
import sys, json, math, shutil
from pathlib import Path
from PIL import Image

HERE = Path(__file__).resolve().parent
KIT, OUT = Path(sys.argv[1]), Path(sys.argv[2])
LAY = json.loads(Path(sys.argv[3]).read_text())
PIXEL = [Path(p) for p in sys.argv[4:]]
A = OUT / 'a'; A.mkdir(parents=True, exist_ok=True)
meta = {p.stem: json.loads(p.read_text()) for p in KIT.glob('*.json')}
G = meta['ground']; PPM = G['ppm']; E = math.radians(G['elevation_deg'])
X0, V0, PH = LAY['plate']['x'][0], LAY['plate']['v'][0], G['h']


def webp(im, name, q=88):
    im.save(A / name, 'WEBP', quality=q, method=6)
    return 'a/' + name


def to_px(x, y):
    return (x - X0) * PPM, PH - (y * math.sin(E) - V0) * PPM


def top_left(name, x, y):
    px, py = to_px(x, y); ax, ay = meta[name]['anchor']
    return int(round(px - ax)), int(round(py - ay))


MAX_W = 2048   # keep every sheet inside small-GPU texture limits (wide strips fall back to slow CPU drawing)


GUT = 2       # every cell gets a 2 px border of its own edge pixels, so scaled drawing never samples a neighbour


def padded(im):
    import numpy as np
    a = np.asarray(im)
    return Image.fromarray(np.pad(a, ((GUT, GUT), (GUT, GUT)) + ((0, 0),) * (a.ndim - 2), mode='edge'))


def pack(ims, mode='RGBA', cols=None):
    """frames into a grid at most MAX_W wide (or `cols` wide); cell stride = frame + 2*GUT. Returns (sheet, cols)."""
    w, h = ims[0].size
    cols = cols or max(1, min(len(ims), MAX_W // (w + 2 * GUT))); rows = -(-len(ims) // cols)
    s = Image.new(mode, ((w + 2 * GUT) * cols, (h + 2 * GUT) * rows))
    for i, im in enumerate(ims):
        s.paste(padded(im.convert(mode)), ((i % cols) * (w + 2 * GUT), (i // cols) * (h + 2 * GUT)))
    return s, cols


def grid(fmt, rows, cols):
    """rows = headings, cols = frames (padded cells, same stride as pack)."""
    return pack([Image.open(fmt(r, c)).convert('RGBA') for r in range(rows) for c in range(cols)], cols=cols)[0]


# ---------------------------------------------------------------- ground + baked shadows + water crop
shadow_layer = Image.new('RGBA', (G['w'], PH))
for name, x, y in LAY['place']:
    shadow_layer.alpha_composite(Image.open(KIT / f'{name}_shadow.png').convert('RGBA'), top_left(name, x, y))
pc, rx, ry = LAY['pond']['centre'], LAY['pond']['rx'], LAY['pond']['ry']
l, t = to_px(pc[0] - rx * 1.25, pc[1] + ry * 1.3); r, b = to_px(pc[0] + rx * 1.25, pc[1] - ry * 1.35)
water_rect = [int(l), int(t), int(r - l), int(b - t)]
frames = []
for f in range(G['frames']):
    g = Image.open(KIT / 'ground' / f'f{f:02d}.png').convert('RGBA'); g.alpha_composite(shadow_layer)
    if f == 0:
        ground = webp(g.convert('RGB'), 'ground.webp', 86)
    frames.append(g.crop((l, t, r, b)))
ws, water_cols = pack([fr.convert('RGB') for fr in frames], 'RGB')
water = webp(ws, 'water.webp', 86)

# ---------------------------------------------------------------- sprites
SOLID = {   # collision in metres around the ground anchor: ('c', r) circle or ('r', half_w, half_d) box
    'oak': ('c', .55), 'maple': ('c', .55), 'blossom': ('c', .5), 'poplar': ('c', .4), 'pine': ('c', .45),
    'bush': ('c', .7), 'rock': ('c', .85), 'well': ('c', 1.15), 'house': ('r', 2.95, 2.15), 'house_b': ('r', 2.95, 2.15),
    'fence_x': ('r', 2.05, .14), 'fence_y': ('r', .14, 2.05)}
sprites = {}
for name in sorted({p[0] for p in LAY['place']}):
    m = meta[name]
    if m.get('sway_frames'):
        sheet, cols = pack([Image.open(KIT / f'{name}_sway' / f'f{i:02d}.png').convert('RGBA') for i in range(m['sway_frames'])])
        sprites[name] = dict(src=webp(sheet, f'{name}.webp'), w=m['w'], h=m['h'], anchor=m['anchor'], frames=m['sway_frames'], cols=cols)
    else:
        sprites[name] = dict(src=webp(pack([Image.open(KIT / f'{name}.png').convert('RGBA')])[0], f'{name}.webp'),
                             w=m['w'], h=m['h'], anchor=m['anchor'], frames=1, cols=1)
for name in ('drake', 'duckling'):
    m = meta[name]
    sprites[name] = dict(src=webp(grid(lambda r, c: KIT / name / f'd{r}_f{c:02d}.png', 8, m['frames']), f'{name}.webp'),
                         w=m['w'], h=m['h'], anchor=m['anchor'], frames=m['frames'])
hm = meta['hero']; hero = dict(w=hm['w'], h=hm['h'], anchor=hm['anchor'], frames=hm['frames'])
for clip in hm['clips']:
    for sfx in ('', '_shadow'):
        hero[clip + sfx] = webp(grid(lambda r, c: KIT / 'hero' / f'{clip}_d{r}_f{c:02d}{sfx}.png', 8, hm['frames']), f'hero_{clip}{sfx}.webp')

jt = .55
data = dict(
    ppm=PPM, elev=G['elevation_deg'], x0=X0, v0=V0, plate=[G['w'], PH], ground=ground,
    water=dict(src=water, rect=water_rect, frames=len(frames), cols=water_cols),
    sprites=sprites, hero=hero,
    place=[dict(name=n, x=x, y=y, solid=SOLID.get(n)) for n, x, y in LAY['place']],
    pond=LAY['pond'], ducks=LAY['ducks'], start=LAY['hero']['start'],
    jetty=dict(x=pc[0] - rx * .66 + math.cos(jt) * 1.0, y=pc[1] - ry * .8 + math.sin(jt) * 1.0, angle=jt, half=[1.25, .52]),
    blossoms=[[x, y] for n, x, y in LAY['place'] if n == 'blossom'],
    bounds=[X0 + .6, LAY['plate']['x'][1] - .6, 0.6, (LAY['plate']['v'][1]) / math.sin(E) - .6])
data['gutter'] = GUT
# pp pixel characters: their own walk/idle sheets (rows = S,SE,E,NE,N,NW,W,SW), kept lossless and drawn unsmoothed
data['pixel'] = []
for d in PIXEL:
    m = json.loads((d / f'{d.name}.json').read_text()); c = dict(name=d.name, w=m['frame_w'], h=m['frame_h'], anchor=m['anchor'],
                                                                 dirs=m['directions'], height_px=m['height_px'])
    for clip in ('walk', 'idle'):
        cm = m['clips'][clip]; shutil.copy(d / cm['sheet'], A / cm['sheet'])
        fr = cm['frames']   # pp lists per-frame timings
        c[clip] = dict(src='a/' + cm['sheet'], frames=len(fr), ms=fr[0]['ms'], speed=cm['speed_px_per_cycle'])
    data['pixel'].append(c)
(OUT / 'data.json').write_text(json.dumps(data))
shutil.copy(HERE / 'game.html', OUT / 'index.html')
total = sum(p.stat().st_size for p in OUT.rglob('*') if p.is_file())
print('ok', len(list(A.iterdir())), 'files', round(total / 1e6, 1), 'MB')

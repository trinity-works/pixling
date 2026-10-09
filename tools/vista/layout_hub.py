"""Highgate town hub, pannable in both directions -> specs/vista/highgate_hub.map.json

  python3 tools/vista/layout_hub.py [builds=out] && python3 -m pp.map specs/vista/highgate_hub.map.json --layers
"""
import os
os.chdir(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".."))
import json, random, sys
import numpy as np
from PIL import Image
sys.path.insert(0, '.')
from pp.sdf import rot_matrix
B = sys.argv[1] if len(sys.argv) > 1 else 'out'; S = 'specs/vista/streets/'
random.seed(11)
W, H = 400, 720
RX = (320, 344)                     # river banks (x)
def meta(n): return json.load(open(f'{B}/{n}/{n}.json'))
def ext(n):
    m = meta(n); a = np.array(Image.open(f'{B}/{n}/{n}_idle.png'))[:m['frame_h'], :m['frame_w'], 3] > 0
    xs = np.nonzero(a.any(0))[0]; ys = np.nonzero(a.any(1))[0]
    return xs.min() - m['anchor'][0], xs.max() - m['anchor'][0], m['anchor'][1] - ys.min()
houses = [f'st_house_{c}' for c in 'abcdefghij']
E = {h: ext(h) for h in houses}
LOW = [h for h in houses if E[h][2] <= 47]
O, smoke, T = [], [], []
def chimney_top(b, x, y):
    s = json.load(open(S + b + '.json')); m = meta(b)
    ch = [bb for bb in s['bones'] if bb['name'] == 'chimney']
    if not ch: return None
    c = np.array(ch[0]['parts'][1]['at'], float); c[2] += 1.0
    p = rot_matrix(0, 0, s.get('view', {}).get('yaw', {}).get('S', 0)) @ (c * m.get('size_scale', 1.0))
    return [round(x + p[0], 1), round(y - (p[2] + 0.5 * p[1]), 1)]
def o(b, x, y, **k):
    O.append(dict(build=b, at=[int(x), int(y)], **k))
    if b.startswith('st_house'):
        c = chimney_top(b, int(x), int(y))
        if c: smoke.append(c)
def pack(x0, x1, y):
    x = x0 - 3
    while True:
        fits = [h for h in LOW if (x - E[h][0] - 1) + E[h][1] <= x1 + 4]
        if not fits or x1 - x0 < 18: break
        h = random.choice(fits); l, r, _ = E[h]; cx = x - l - 1; o(h, cx, y); x = cx + r
def t(**k): T.append(k)
def lane(y, x0, x1, h=10): t(kind="paving", rect=[x0, y, x1 - x0, h], ramp="sand", slab=[12, 6], rough=0.5, alt_rate=90)
def trees(y0, y1, x0, x1, d=0.85, g=0.25): t(kind="canopy", rect=[x0, y0, x1 - x0, y1 - y0], rough=2, density=d, mix=[["leaf", 1 - g], ["leaf_gold", g]])
BR = []
def row(y, spans, bridge=True, tree=True):
    for x0, x1 in spans:
        if tree: trees(y - 40, y - 16, x0 - 2, x1 + 2)
        lane(y, x0 - 2, x1 + 2, 10)
        pack(x0, x1, y)
    if bridge:
        o('st_bridge_ew', 332, y + 5, z=4, over=True); BR.append(y + 5)
MAIN = (188, 212)
t(kind="fill", ramp="grass", tones={"base": 1})                     # land: one flat green
t(kind="canopy", rect=[-6, -6, W + 12, 44], mix=[["leaf", 0.8], ["leaf_gold", 0.2]], rough=0)
# river flows in under the wall, down the east side, into the harbour
t(kind="sea", rect=[RX[0], 40, 24, 520], rough=0, gradient=0.1, levels=[], tones={"deep": 1})
t(kind="shore", rect=[RX[0], 40, 24, 520], width=2, rough=0)
t(kind="fill", rect=[RX[0] - 2, 40, 2, 522], ramp="stone", tones={"base": 3}, rough=0)
t(kind="fill", rect=[RX[1], 40, 2, 522], ramp="stone", tones={"base": 1}, rough=0)
x = 34
while x < W + 34:
    if abs(x - 200) > 50: o('st_wall', x, 60, over=True)
    x += 68
o('st_wall', 128, 60, over=True); o('st_wall', 272, 60, over=True)
o('st_gate', 200, 66, place='gate', over=True)
t(kind="paving", rect=[MAIN[0], 62, 24, 490], ramp="sand", slab=[12, 6], rough=0.4, alt_rate=90)
WEST, MIDE, EAST = (0, MAIN[0] - 2), (MAIN[1] + 2, RX[0] - 3), (RX[1] + 3, W)
row(122, [WEST, MIDE, EAST]); row(180, [WEST, MIDE, EAST])
# market plaza + tavern
t(kind="paving", ellipse=[200, 232, 58, 26], ramp="stone", slab=[7, 4], rough=1.0, alt_rate=150)
trees(206, 262, 0, 132, 0.95, 0.3); trees(206, 262, 268, RX[0] - 2, 0.95, 0.25); trees(206, 262, RX[1] + 2, W + 4, 0.95, 0.3)
o('st_fountain', 200, 232, place='market'); o('st_stall_red', 170, 222); o('st_stall_gold', 228, 220); o('st_stall_teal', 236, 246)
o('st_cart', 160, 248); o('st_lamp', 176, 256); o('st_lamp', 224, 256)
lane(262, 100, 188); o('st_house_c', 150, 262, place='tavern'); o('st_barrels', 128, 266)
# Arena district (west)
trees(282, 420, -4, MAIN[0] - 2, 0.95, 0.3)
t(kind="paving", ellipse=[94, 376, 76, 40], ramp="stone", slab=[7, 4], rough=1.2, alt_rate=150)
t(kind="paving", rect=[0, 402, MAIN[0], 16], ramp="stone", slab=[7, 4], rough=0.5, alt_rate=150)
o('st_arena', 94, 396, place='arena')
for x in (22, 166): o('st_lamp', x, 404)
for x in (30, 158): o('banner_pole_v', x, 372)
row(318, [MIDE, EAST]); row(376, [MIDE, EAST])
# Guild hall square (between the main street and the river)
t(kind="paving", rect=[MIDE[0] - 2, 446, MIDE[1] - MIDE[0] + 4, 30], ramp="stone", slab=[7, 4], rough=0.4, alt_rate=150)
trees(398, 420, MIDE[0], MIDE[1], 0.95, 0.35)
o('st_hall', 266, 448, place='guild'); o('st_lamp', 222, 470); o('st_lamp', 310, 470)
lane(446, EAST[0] - 2, W + 2); o('st_bridge_ew', 332, 451, z=4, over=True); BR.append(451)
pack(EAST[0], EAST[1], 446)
row(504, [WEST, EAST]); pack(MIDE[0], MIDE[1], 504); lane(504, MIDE[0] - 2, MIDE[1] + 2)
trees(424, 468, -4, MAIN[0], 0.95, 0.3)
# harbour
t(kind="paving", rect=[-2, 530, W + 4, 24], ramp="stone", slab=[8, 5], rough=0, alt_rate=150)
t(kind="wall_face", rect=[0, 554, W, 5], ramp="stone", course=3, rough=0)
t(kind="sea", rect=[0, 559, W, 170], rough=0, gradient=0.8, levels=[0.55], streak=26, tones={"deep": 1}, deep_at="bottom")
t(kind="sea", rect=[RX[0], 526, 24, 36], rough=0, gradient=0.1, levels=[], tones={"deep": 1})
t(kind="fill", rect=[RX[0] - 2, 526, 2, 30], ramp="stone", tones={"base": 3}, rough=0)
t(kind="fill", rect=[RX[1], 526, 2, 30], ramp="stone", tones={"base": 1}, rough=0)
t(kind="paving", rect=[MAIN[0], 554, 24, 130], ramp="stone", slab=[8, 5], rough=0, alt_rate=150)
t(kind="wall_face", rect=[MAIN[0], 684, 24, 4], ramp="stone", course=2, rough=0)
t(kind="planks", rect=[70, 559, 8, 80], vertical=True, rough=0); t(kind="planks", rect=[270, 559, 8, 70], vertical=True, rough=0)
t(kind="shore", rect=[0, 548, W, 180], width=3, rough=0)
o('st_bridge_ew', 332, 541, z=4, over=True); BR.append(541)
o('st_lighthouse', 200, 680, place='harbour'); o('st_lamp', 190, 590); o('st_lamp', 210, 590)
for x in (60, 120, 250, 380): o('st_barrels', x, 548)
for x, y in ((100, 596), (100, 640), (40, 610), (300, 600), (246, 652), (370, 626)):
    o('st_ship', x, y, phase=random.randint(0, 5))
# rowboats come in under the city wall, pass under every bridge and row out to sea (both ends hidden)
river = [[332, 40], [332, 556], [326, 600], [306, 740]]
wk = [{"build": "st_rowboat", "path": river, "loop": False, "clip": "idle", "speed_px_s": 5.0, "phase": p} for p in (0.0, 0.5)]
wk += [{"build": "st_ship", "path": [[-30, 706], [430, 700]], "loop": False, "clip": "idle", "speed_px_s": 5.0, "phase": 0.2}]
fx = [{"kind": "flow", "path": [[332, 40], [332, 560]], "width": 12, "lanes": 3, "spacing": 34, "length": 6, "loops": 3, "color": "sea:2", "color2": "sea:2"},
      {"kind": "glints", "rect": [0, 560, W, 160], "count": 18, "rate": 2, "color": "sea:5", "color2": "sea:4"},
      {"kind": "birds", "count": 3, "y": [100, 400, 620], "speed_px_s": 9.0, "shadow_drop": 34},
      {"kind": "clouds", "count": 2, "size": [140, 70], "y": [260, 520], "speed_px_s": 2.5, "alpha": 0.0, "shadow_alpha": 0.14}]
fx += [{"kind": "smoke", "at": c, "life": 60, "puffs": 5, "rise": 18, "grow": 2.2, "drift": 7, "colors": ["plaster:3", "plaster:2", "plaster:1"]} for c in smoke[::3]]
m = {"name": "highgate_hub", "style": "vista", "size": [W, H], "frames": 120, "ms": 100, "seed": 51, "cast_shadow": [3, 1],
     "terrain": T, "objects": O, "walkers": wk, "fx": fx}
json.dump(m, open('specs/vista/highgate_hub.map.json', 'w'), indent=1)
print(len(O), 'objects, bridges', BR)

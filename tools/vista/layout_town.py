"""Tall scrolling street town -> specs/vista/highgate_town.map.json  (python3 tools/vista/layout_town.py [builds=out] [seed])"""
import os
os.chdir(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".."))
import json, random, sys
import numpy as np
from PIL import Image
sys.path.insert(0, '.')
from pp.sdf import rot_matrix
B = sys.argv[1] if len(sys.argv) > 1 else 'out'; S = 'specs/vista/streets/'
random.seed(int(sys.argv[2]) if len(sys.argv) > 2 else 5)
W, H = 195, 1180
def meta(n): return json.load(open(f'{B}/{n}/{n}.json'))
def ext(n):
    m = meta(n); a = np.array(Image.open(f'{B}/{n}/{n}_idle.png'))[:m['frame_h'], :m['frame_w'], 3] > 0
    xs = np.nonzero(a.any(0))[0]; ys = np.nonzero(a.any(1))[0]
    return xs.min() - m['anchor'][0], xs.max() - m['anchor'][0], m['anchor'][1] - ys.min()
houses = [f'st_house_{c}' for c in 'abcdefghij']
E = {h: ext(h) for h in houses}
LOW = [h for h in houses if E[h][2] <= 47]
objs, smoke = [], []
def chimney_top(b, x, y):
    s = json.load(open(S + b + '.json')); m = meta(b)
    ch = [bb for bb in s['bones'] if bb['name'] == 'chimney']
    if not ch: return None
    c = np.array(ch[0]['parts'][1]['at'], float); c[2] += 1.0
    k = m.get('size_scale', 1.0); yaw = s.get('view', {}).get('yaw', {}).get('S', 0)
    p = rot_matrix(0, 0, yaw) @ (c * k)
    return [round(x + p[0], 1), round(y - (p[2] + 0.5 * p[1]), 1)]
def o(b, x, y, **k):
    objs.append(dict(build=b, at=[int(x), int(y)], **k))
    if b.startswith('st_house'):
        c = chimney_top(b, int(x), int(y))
        if c: smoke.append(c)
def pack(x0, x1, y, pool=LOW):
    x = x0 - 3
    while True:
        fits = [h for h in pool if (x - E[h][0] - 1) + E[h][1] <= x1 + 4]
        if not fits: break
        h = random.choice(fits); l, r, _ = E[h]
        cx = x - l - 1; o(h, cx, y); x = cx + r
T = []
def t(**k): T.append(k)
def lane(y, x0=-2, x1=197, h=10): t(kind="paving", rect=[x0, y, x1 - x0, h], ramp="sand", slab=[12, 6], rough=0.5, alt_rate=90)
def trees(y0, y1, x0, x1, dens=0.85, gold=0.25): t(kind="canopy", rect=[x0, y0, x1 - x0, y1 - y0], rough=2, density=dens, mix=[["leaf", 1 - gold], ["leaf_gold", gold]])
RIVER = (140, 164)
t(kind="land", tufts=0.006, patch_cell=14)
t(kind="canopy", rect=[-6, -6, 207, 44], mix=[["leaf", 0.8], ["leaf_gold", 0.2]], rough=0)
for x in (-6, 62): o('st_wall', x + 34, 60)
for x in (126, 194): o('st_wall', x - 34, 60)
o('st_gate', 97, 66)
t(kind="paving", rect=[84, 62, 27, 900], ramp="sand", slab=[12, 6], rough=0.4, alt_rate=90)      # main street
# north quarter
for y in (122, 180):
    trees(y - 40, y - 16, -4, 84); trees(y - 40, y - 16, 111, 199)
    lane(y, h=10 if y == 122 else 14)
    pack(0, 82, y); pack(113, 195, y)
# market plaza
t(kind="paving", ellipse=[97, 232, 50, 24], ramp="stone", slab=[7, 4], rough=1.0, alt_rate=150)
t(kind="canopy", ellipse=[18, 226, 22, 20], rough=1.5, mix=[["leaf", 0.65], ["leaf_gold", 0.35]])
t(kind="canopy", ellipse=[178, 228, 22, 20], rough=1.5, mix=[["leaf", 0.75], ["leaf_gold", 0.25]])
o('st_fountain', 97, 232); o('st_stall_red', 68, 222); o('st_stall_gold', 126, 220); o('st_stall_teal', 134, 246)
o('st_cart', 60, 248); o('st_lamp', 74, 256); o('st_lamp', 120, 256); o('st_well', 164, 244)
# south of the plaza, down to the river road
for y in (318, 376):
    trees(y - 40, y - 16, -4, 84); trees(y - 40, y - 16, 111, 199)
    lane(y, h=10 if y == 318 else 14)
    pack(0, 82, y); pack(113, 195, y)
# river: comes out of a culvert under the river road, runs south to the harbour between stone banks
t(kind="fill", ellipse=[152, 391, 9, 4], ramp="ink", tones={"base": 0}, rough=0)
t(kind="sea", rect=[RIVER[0], 391, 24, 560], rough=0, gradient=0.1, levels=[0.45, 0.62], tones={"deep": 1})
t(kind="shore", rect=[RIVER[0], 391, 24, 560], width=2, rough=0)
t(kind="fill", rect=[RIVER[0] - 2, 390, 2, 562], ramp="stone", tones={"base": 3}, rough=0)
t(kind="fill", rect=[RIVER[1], 390, 2, 562], ramp="stone", tones={"base": 1}, rough=0)
# river quarter: west block, a narrow block between street and river, and the east bank
def rows_river(ys, bridges=()):
    for y in ys:
        trees(y - 40, y - 16, -4, 84); trees(y - 40, y - 16, 111, RIVER[0] - 2, 0.9); trees(y - 40, y - 16, RIVER[1] + 2, 199, 0.9)
        lane(y, -2, RIVER[0] - 2); lane(y, RIVER[1] + 2, 197)
        pack(0, 82, y); pack(113, RIVER[0] - 3, y); pack(RIVER[1] + 3, 195, y)
        if y in bridges:
            o('st_bridge_ew', 152, y + 5, z=4)
rows_river((440, 498), bridges=(440,))
# guild hall square (west of the river), trees and a fountain; east bank keeps its houses
t(kind="paving", rect=[-2, 604, RIVER[0], 42], ramp="stone", slab=[7, 4], rough=0.6, alt_rate=150)
trees(522, 560, 104, RIVER[0] - 2, 0.9, 0.35); trees(522, 556, RIVER[1] + 2, 199, 0.9)
trees(508, 560, -4, 84, 0.95, 0.3)
o('st_hall', 52, 606); o('st_fountain', 116, 630); o('st_lamp', 96, 642); o('st_lamp', 8, 642)
o('st_stall_gold', 124, 614); o('st_barrels', 132, 640)
pack(RIVER[1] + 3, 195, 556)
lane(556, RIVER[1] + 2, 197)
t(kind="paving", rect=[RIVER[1] + 2, 604, 34, 42], ramp="stone", slab=[7, 4], rough=0.6, alt_rate=150)
o('st_bridge_ew', 152, 624, z=4)
rows_river((704, 762, 820, 878))
# harbour: warehouses on the quay, stone mole with the lighthouse, piers, ships
trees(894, 918, -4, 84); trees(894, 918, 111, RIVER[0] - 2, 0.9); trees(894, 918, RIVER[1] + 2, 199, 0.9)
t(kind="paving", rect=[-2, 934, 199, 22], ramp="stone", slab=[8, 5], rough=0, alt_rate=150)
pack(0, 82, 936); pack(113, RIVER[0] - 3, 936); pack(RIVER[1] + 3, 195, 936)
t(kind="wall_face", rect=[0, 956, W, 5], ramp="stone", course=3, rough=0)
t(kind="sea", rect=[RIVER[0], 926, 24, 36], rough=0, gradient=0.1, levels=[0.45, 0.62], tones={"deep": 1})     # river mouth cuts the quay
t(kind="fill", rect=[RIVER[0] - 2, 926, 2, 35], ramp="stone", tones={"base": 3}, rough=0)
t(kind="fill", rect=[RIVER[1], 926, 2, 35], ramp="stone", tones={"base": 1}, rough=0)
t(kind="sea", rect=[0, 961, W, 230], rough=0, gradient=0.55, levels=[0.4, 0.58], tones={"deep": 1}, deep_at="bottom")
t(kind="fill", rect=[RIVER[0], 950, 24, 11], ramp="sea", tones={"base": 2}, rough=0)
t(kind="paving", rect=[84, 956, 27, 150], ramp="stone", slab=[8, 5], rough=0, alt_rate=150)          # the mole
t(kind="wall_face", rect=[84, 1106, 27, 4], ramp="stone", course=2, rough=0)
t(kind="planks", rect=[34, 961, 8, 70], vertical=True, rough=0)
t(kind="planks", rect=[168, 961, 8, 80], vertical=True, rough=0)
t(kind="shore", rect=[0, 950, W, 240], width=3, rough=0)
o('st_bridge_ew', 152, 945, z=4)
o('st_lighthouse', 97, 1100); o('st_barrels', 70, 952); o('st_barrels', 126, 952); o('st_lamp', 86, 1000); o('st_lamp', 108, 1000)
for x, y in ((60, 1000), (60, 1040), (146, 1012), (190, 1060)):
    o('st_ship', x, y, phase=random.randint(0, 5))
m = {"name": "highgate_town", "style": "vista", "size": [W, H], "frames": 120, "ms": 80, "seed": 31, "cast_shadow": [3, 1],
     "terrain": T, "objects": objs,
     "walkers": [
       # each rowboat runs between two bridges and is hidden under a deck at both ends, so the loop is seamless
       {"build": "st_rowboat", "path": [[152, 444], [152, 623]], "loop": False, "clip": "idle", "phase": 0.0},
       {"build": "st_rowboat", "path": [[152, 623], [152, 944]], "loop": False, "clip": "idle", "phase": 0.35},
       {"build": "st_rowboat", "path": [[152, 944], [150, 1010], [136, 1195]], "loop": False, "clip": "idle", "phase": 0.7},
       {"build": "st_ship", "path": [[-30, 1150], [230, 1146]], "loop": False, "clip": "idle", "phase": 0.3}],
     "fx": [{"kind": "waves", "rect": [0, 962, W, 220], "spacing": 6, "speed": 0.3, "on": "sea:1", "color": "sea:2"},
            {"kind": "waves", "rect": [0, 964, W, 220], "spacing": 7, "speed": -0.25, "on": "sea:2", "color": "sea:3"},
            {"kind": "glints", "rect": [0, 964, W, 216], "count": 18, "rate": 3, "color": "sea:5", "color2": "sea:4"},
            {"kind": "glints", "rect": [RIVER[0] + 2, 392, 20, 556], "count": 16, "rate": 3, "color": "sea:5", "color2": "sea:4"},
            {"kind": "birds", "count": 3, "y": [80, 520, 1000], "laps": 1, "color": "plaster:3", "shade": "plaster:1", "shadow_drop": 34},
            {"kind": "clouds", "count": 2, "size": [130, 70], "y": [300, 800], "laps": 1}] +
           [{"kind": "smoke", "at": c, "life": 64, "puffs": 5, "rise": 18, "grow": 2.2, "drift": 7, "colors": ["plaster:3", "plaster:2", "plaster:1"]}
            for c in smoke[::3]]}
json.dump(m, open('specs/vista/highgate_town.map.json', 'w'), indent=1)
print(len(objs), 'objects', len(smoke[::3]), 'smokes', 'low houses', LOW)

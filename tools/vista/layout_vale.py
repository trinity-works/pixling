"""World map layout: The Vale of Highgate -> specs/vista/world/vale.map.json

  python3 tools/vista/layout_vale.py && python3 -m pp.map specs/vista/world/vale.map.json --layers
"""
import os
os.chdir(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".."))
import json, random, math
random.seed(7)
W, H = 520, 800
T, O, FX, WK = [], [], [], []
def t(**k): T.append(k)
def o(b, x, y, **k): O.append(dict(build=b, at=[int(x), int(y)], **k))
# land, sea, coast
sea = [[-5, 470], [40, 500], [60, 556], [52, 606], [60, 656], [86, 694], [128, 702], [158, 684], [186, 708], [250, 745], [300, 765], [360, 790], [360, 810], [-5, 810]]
t(kind="fill", ramp="grass", tones={"base": 1})                     # land: one flat green
t(kind="sea", poly=sea, rough=3, rough_cell=6, gradient=0.8, levels=[0.55], streak=26, tones={"deep": 1}, deep_at="bottom")
# Highgate promontory: land back over the sea
t(kind="shore", width=4)
# river from the mountains to the sea
# water: the river springs inside the peaks (the range is drawn over its source) and runs to the sea;
# a mountain stream feeds the lake, whose outflow joins the river
river = [[346, 110], [340, 160], [336, 196], [330, 260], [352, 330], [362, 390], [328, 462], [300, 540], [312, 620], [296, 700], [300, 780]]
inflow = [[222, 140], [232, 180], [242, 216]]
outflow = [[282, 234], [306, 248], [331, 262]]
STREAMS = [(river, 9), (inflow, 5), (outflow, 5)]
for path, w in STREAMS:
    t(kind="sea", path=path, width=w, rough=1.2, gradient=0.1, levels=[], tones={"deep": 1})
for path, w in STREAMS:
    t(kind="shore", path=path, width=2.5, rough=0)
# lake under the mountains
t(kind="sea", ellipse=[250, 230, 34, 16], rough=2, gradient=0.1, levels=[], tones={"deep": 1})
t(kind="shore", ellipse=[250, 230, 40, 22], width=3, rough=0)
# farm fields east of the river (Millbrook)
for i, (x, y, w, h, r) in enumerate([(372, 470, 34, 22, "leaf_gold"), (410, 474, 30, 20, "grass"), (378, 500, 28, 18, "grass"), (444, 470, 30, 24, "leaf_gold"),
                                     (412, 552, 34, 20, "leaf_gold"), (452, 540, 30, 22, "grass"), (372, 560, 30, 18, "leaf_gold")]):
    t(kind="planks", rect=[x, y, w, h], ramp=r, tones={"base": 2, "alt": 3, "seam": 1}, rough=0.6)
t(kind="fill", ellipse=[400, 150, 40, 22], ramp="rock", tones={"base": 1}, rough=4, rough_cell=6)          # scorched ground round Blackspire
# eastern hills
# roads
roads = [
  [[128, 604], [170, 560], [230, 500]],                    # Highgate gate -> crossroads
  [[230, 500], [196, 440], [158, 378]],                    # -> Hollow Crypt
  [[230, 500], [300, 480], [330, 470], [390, 510]],        # -> bridge -> Millbrook
  [[390, 510], [430, 420], [456, 320]],                    # -> Ember Mines
  [[230, 500], [262, 400], [300, 320], [360, 250], [396, 170]],   # -> Blackspire
  [[196, 440], [120, 320], [90, 200], [84, 128]],          # -> realm portal
  [[170, 560], [70, 470], [48, 420]],                      # -> north coast outpost
]
for r in roads: t(kind="path", path=r, width=4, rough=0.7)
# the mountains: one continuous range, a hollow for Blackspire and a pass along its road
t(kind="massif", poly=[[140, 20], [530, 10], [530, 250], [470, 262], [420, 236], [360, 226], [300, 214], [220, 196], [150, 150]],
  rough=8, rough_cell=24, peak=30, edge=40, spacing=30, snow=0.8,
  valleys=[{"ellipse": [400, 158, 30, 18]}, {"path": [[360, 250], [396, 172]], "width": 10},
           {"path": [[346, 112], [340, 160], [336, 214]], "width": 8, "width_out": 10}])       # the river's gorge
t(kind="massif", ellipse=[478, 300, 46, 34], rough=5, rough_cell=10, peak=14, edge=26, spacing=22, snow=1.0,
  valleys=[{"path": [[430, 420], [456, 322]], "width": 10}, {"ellipse": [458, 322, 12, 9]}])
# forests: the Greenwood (with a clearing for the crypt), groves everywhere else
CLEAR = [{"path": r, "width": 5} for r in roads]
t(kind="canopy", poly=[[20, 250], [120, 230], [250, 270], [280, 340], [240, 420], [200, 470], [110, 470], [40, 420], [10, 330]], mix=[["leaf", 0.8], ["leaf_gold", 0.2]], rough=6, rough_cell=10, clear=CLEAR)
t(kind="fill", ellipse=[160, 372, 22, 14], ramp="grass", tones={"base": 1}, rough=3)                                   # clearing
for (x, y, rx, ry, g) in [(470, 620, 50, 40, 0.3), (230, 620, 40, 26, 0.3), (60, 540, 26, 16, 0.2), (480, 420, 30, 20, 0.35),
                          (40, 180, 40, 40, 0.2), (400, 700, 60, 40, 0.3), (180, 740, 30, 14, 0.2), (130, 150, 30, 30, 0.15)]:
    t(kind="canopy", ellipse=[x, y, rx, ry], mix=[["leaf", 1 - g], ["leaf_gold", g]], rough=5, rough_cell=9, clear=CLEAR)
# points of interest
o('w_spire', 400, 160, place='raid', icon='tower')
o('w_crypt', 160, 374, place='crypt', icon='skull'); o('w_camp', 186, 392)
o('w_mine', 458, 318, place='mines', icon='skull'); o('w_camp', 432, 336)
o('w_portal', 84, 126, place='portal', icon='ring')
# enemy spots: clearing one plants your banner and lifts the fog behind it
for pid, b, (x, y) in (('crossroads', 'w_bandit_camp', (232, 498)), ('riverpass', 'w_wolf_den', (356, 300)),
                       ('northcoast', 'w_smuggler_cove', (46, 418)), ('eastbridge', 'w_goblin_warren', (324, 648))):
    o(b, x, y, place=pid, icon='cave' if b == 'w_wolf_den' else 'camp')
# Millbrook village
for (x, y, b) in [(396, 520, "house_1"), (414, 526, "house_7"), (386, 534, "house_7"), (430, 516, "house_5")]: o(b, x, y)
o('house_4', 402, 540, place='village', icon='house')
o('w_windmill', 450, 512); o('w_windmill', 372, 596, phase=7)
# Highgate on its promontory: keep, chapel, houses, lighthouse
o('lighthouse', 60, 612)
o('keep', 106, 632, place='highgate', icon='castle')
for (x, y, b) in [ (130, 626, "chapel"), (86, 640, "house_3"), (80, 656, "house_1"), (96, 664, "house_4"), (118, 660, "house_2"),
                  (134, 648, "house_7"), (110, 678, "house_5"), (92, 682, "house_7"), (130, 672, "house_1")]:
    o(b, x, y)
# ships at sea, birds, smoke, glints
WK += [{"build": "sailboat", "path": [[-20, 540], [40, 690], [200, 782], [380, 830]], "loop": False, "clip": "idle", "speed_px_s": 4.0, "phase": 0.0},
       {"build": "sailboat", "path": [[34, 520], [22, 600], [36, 690], [110, 752], [44, 716], [34, 520]], "clip": "idle", "speed_px_s": 3.0, "phase": 0.4}]
FX += [{"kind": "flow", "path": p, "width": max(2, w - 4), "lanes": 2 if w > 6 else 1, "spacing": 22, "length": 4, "loops": 3, "color": "sea:2", "color2": "sea:2"} for p, w in STREAMS]
FX += [
       {"kind": "glints", "rect": [0, 480, 360, 320], "count": 24, "rate": 2, "color": "sea:5", "color2": "sea:4"},
       {"kind": "birds", "count": 3, "y": [300, 560, 700], "speed_px_s": 8.0, "shadow_drop": 30},
       {"kind": "clouds", "count": 3, "size": [110, 46], "y": [210, 430, 650], "speed_px_s": 2.5, "alpha": 0.0, "shadow_drop": 0, "shadow_alpha": 0.16}]
for (x, y) in [(84, 628), (120, 650), (400, 526)]:
    FX.append({"kind": "smoke", "at": [x, y], "life": 50, "puffs": 4, "rise": 12, "grow": 1.4, "drift": 5, "colors": ["plaster:3", "plaster:2", "plaster:1"]})
# bridges: every road crossing a stream gets a deck along the road
def _cross(p1, p2, q1, q2):
    d = (p2[0] - p1[0]) * (q2[1] - q1[1]) - (p2[1] - p1[1]) * (q2[0] - q1[0])
    if abs(d) < 1e-9:
        return None
    u = ((q1[0] - p1[0]) * (q2[1] - q1[1]) - (q1[1] - p1[1]) * (q2[0] - q1[0])) / d
    v = ((q1[0] - p1[0]) * (p2[1] - p1[1]) - (q1[1] - p1[1]) * (p2[0] - p1[0])) / d
    return (p1[0] + u * (p2[0] - p1[0]), p1[1] + u * (p2[1] - p1[1])) if 0 <= u <= 1 and 0 <= v <= 1 else None
BRIDGES = []
for road in roads:
    for a1, a2 in zip(road[:-1], road[1:]):
        for path, w in STREAMS:
            for b1, b2 in zip(path[:-1], path[1:]):
                c = _cross(a1, a2, b1, b2)
                if c and all(math.hypot(c[0] - e[0], c[1] - e[1]) > 6 for e in BRIDGES):
                    BRIDGES.append(c)
                    L = math.hypot(a2[0] - a1[0], a2[1] - a1[1]); ux, uy = (a2[0] - a1[0]) / L, (a2[1] - a1[1]) / L
                    half = (w + 8) / 2
                    t(kind="bridge", path=[[c[0] - ux * half, c[1] - uy * half], [c[0] + ux * half, c[1] + uy * half]], width=5, rough=0)
# fog of war: what you have not explored yet; claiming the outpost at a region's edge lifts it
FOG = {"ramp": "mist", "regions": [
  {"id": "greenwood", "poly": [[-10, 20], [164, 20], [172, 226], [300, 226], [300, 476], [-10, 476]]},
  {"id": "peaks", "poly": [[164, 20], [530, 20], [530, 238], [364, 238], [300, 226], [172, 226]]},
  {"id": "east", "poly": [[364, 238], [530, 238], [530, 730], [384, 730], [348, 660], [360, 470]]},
  # the edge of the realm: never lifts (other realms lie beyond)
  {"id": "beyond", "permanent": True, "poly": [[-10, -10], [530, -10], [530, 30], [300, 26], [120, 20], [-10, 32]]},
  {"id": "beyond_e", "permanent": True, "poly": [[508, -10], [530, -10], [530, 810], [506, 810], [498, 500], [508, 200]]}]}
m = {"name": "vale", "style": "vista", "size": [W, H], "frames": 120, "ms": 100, "seed": 41, "cast_shadow": [2, 1],
     "terrain": T, "objects": O, "walkers": WK, "fx": FX, "fog": FOG,
     "sprites": [{"id": "banner", "build": "w_banner", "frame_ms": 140}], "atlas": {"scale": 0.75}}
json.dump(m, open('specs/vista/world/vale.map.json', 'w'), indent=1)
print(len(O), 'objects')

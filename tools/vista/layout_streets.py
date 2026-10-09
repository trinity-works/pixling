"""Short street scene -> specs/vista/highgate_streets.map.json  (python3 tools/vista/layout_streets.py [builds=out] [seed])"""
import os
os.chdir(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".."))
import json, random, sys
import numpy as np
from PIL import Image
B = sys.argv[1] if len(sys.argv) > 1 else 'out'
S = 'specs/vista/streets/'
random.seed(int(sys.argv[2]) if len(sys.argv) > 2 else 3)
def ext(n):
    m = json.load(open(f'{B}/{n}/{n}.json')); a = np.array(Image.open(f'{B}/{n}/{n}_idle.png'))[:m['frame_h'], :m['frame_w'], 3]
    xs = np.nonzero(a.any(0))[0]; return xs.min() - m['anchor'][0], xs.max() - m['anchor'][0]
houses = [f'st_house_{c}' for c in 'abcdefghij']
E = {h: ext(h) for h in houses}
objs, smoke = [], []
def o(b, x, y, **k):
    objs.append(dict(build=b, at=[int(x), int(y)], **k))
    if b.startswith('st_house'):
        s = json.load(open(S + b + '.json')); ch = [bb for bb in s['bones'] if bb['name'] == 'chimney']
        if ch:
            c = ch[0]['parts'][1]['at']; smoke.append([round(x + c[0] * 0.92, 1), round(y - (c[2] + 0.5 * c[1]) - 1, 1)])
def pack(x0, x1, y, avoid=()):
    x = x0 - 3
    while True:
        h = random.choice(houses); l, r = E[h]
        cx = x - l - 1                      # left edge touches (1 px overlap reads as a shared wall)
        if cx + r > x1 + 6: break
        o(h, cx, y + random.randint(-1, 1)); x = cx + r
for x in (-6, 62): o('st_wall', x + 34, 60)
for x in (126, 194): o('st_wall', x - 34, 60)
o('st_gate', 97, 66)
for y in (112, 152):
    pack(0, 82, y); pack(113, 195, y)
for y in (292, 332):
    pack(0, 82, y); pack(113, 195, y)
o('st_fountain', 97, 214)
o('st_house_e', 22, 250); o('st_house_c', 172, 252)
o('st_stall_red', 68, 204); o('st_stall_gold', 126, 202); o('st_stall_teal', 134, 228); o('st_cart', 60, 230)
o('st_lamp', 74, 240); o('st_lamp', 120, 240); o('st_well', 160, 206); o('st_barrels', 46, 254)
o('st_lamp', 82, 350); o('st_lamp', 112, 350); o('st_barrels', 140, 352); o('st_barrels', 44, 354)
m = json.load(open('specs/vista/highgate_streets.map.json'))
m["objects"] = objs; m["cast_shadow"] = [3, 1]
for fx in list(m['fx']):
    if fx['kind'] == 'smoke': m['fx'].remove(fx)
for a, b in smoke[::3][:6]:
    m['fx'].append({"kind": "smoke", "at": [a, b], "life": 64, "puffs": 5, "rise": 18, "grow": 2.2, "drift": 7, "colors": ["plaster:3", "plaster:2", "plaster:1"]})
T = [
  {"kind": "land", "tufts": 0.006, "patch_cell": 14},
  {"kind": "canopy", "rect": [-6, -6, 207, 44], "mix": [["leaf", 0.8], ["leaf_gold", 0.2]], "rough": 0},
  {"kind": "canopy", "rect": [-6, 64, 90, 16], "rough": 2, "mix": [["leaf", 0.75], ["leaf_gold", 0.25]]},
  {"kind": "canopy", "rect": [111, 64, 90, 16], "rough": 2, "mix": [["leaf", 0.75], ["leaf_gold", 0.25]]},
  {"kind": "canopy", "rect": [-6, 244, 90, 14], "rough": 2, "mix": [["leaf", 0.8], ["leaf_gold", 0.2]]},
  {"kind": "canopy", "rect": [111, 244, 90, 14], "rough": 2, "mix": [["leaf", 0.7], ["leaf_gold", 0.3]]},
  {"kind": "paving", "rect": [84, 62, 27, 284], "ramp": "sand", "slab": [12, 6], "rough": 0.4, "alt_rate": 90},
  {"kind": "paving", "rect": [-2, 156, 199, 12], "ramp": "sand", "slab": [12, 6], "rough": 0.6, "alt_rate": 90},
  {"kind": "paving", "ellipse": [97, 214, 50, 26], "ramp": "stone", "slab": [7, 4], "rough": 1.0, "alt_rate": 150},
  {"kind": "canopy", "ellipse": [16, 200, 22, 22], "rough": 1.5, "mix": [["leaf", 0.65], ["leaf_gold", 0.35]]},
  {"kind": "canopy", "ellipse": [180, 202, 22, 22], "rough": 1.5, "mix": [["leaf", 0.75], ["leaf_gold", 0.25]]},
  {"kind": "canopy", "ellipse": [44, 188, 14, 10], "rough": 1.5, "mix": [["leaf", 0.8], ["leaf_gold", 0.2]]},
  {"kind": "canopy", "ellipse": [152, 186, 12, 9], "rough": 1.5, "mix": [["leaf", 0.6], ["leaf_gold", 0.4]]},
  {"kind": "paving", "rect": [-2, 340, 199, 18], "ramp": "stone", "slab": [8, 5], "rough": 0, "alt_rate": 150},
  {"kind": "wall_face", "rect": [0, 358, 195, 6], "rough": 0, "ramp": "stone", "course": 3},
  {"kind": "sea", "rect": [0, 364, 195, 60], "rough": 0, "gradient": 0.2, "levels": [0.45, 0.62], "tones": {"deep": 1}, "deep_at": "bottom"},
  {"kind": "shore", "rect": [0, 362, 195, 62], "width": 3, "rough": 0},
  {"kind": "paving", "rect": [84, 358, 27, 66], "ramp": "stone", "slab": [6, 4], "rough": 0, "rim": False},
  {"kind": "fill", "rect": [84, 358, 2, 66], "ramp": "stone", "tones": {"base": 3}, "rough": 0},
  {"kind": "fill", "rect": [109, 358, 2, 66], "ramp": "stone", "tones": {"base": 1}, "rough": 0}]
m['terrain'] = T
json.dump(m, open('specs/vista/highgate_streets.map.json', 'w'), indent=1)
print(len(objs))

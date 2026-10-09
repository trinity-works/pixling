"""Street vista kit: townhouses, wall, gate, fountain, stalls, well, cart, lamps, boats, bridges, guild hall, ship, arena."""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import math, json, random
from slib import *
# ---- townhouses, city wall and gate, fountain, stalls, well, cart, barrels, lamp, canal boat
T = [("st_house_a", 26, 18, 18, 2, "roof_t", False, -6, None, (6, 3)),
     ("st_house_b", 22, 16, 22, 3, "plum_t", True, 4, "banner", None),
     ("st_house_c", 30, 18, 14, 2, "roof_t", True, 8, "gold", (-8, 2)),
     ("st_house_d", 18, 16, 20, 3, "roof_t", False, 0, None, None),
     ("st_house_e", 34, 20, 18, 2, "plum_t", False, -8, None, (9, 4)),
     ("st_house_f", 24, 18, 16, 2, "roof_t", False, 5, "sea", (-5, 3)),
     ("st_house_g", 20, 14, 12, 1, "roof_t", True, 0, None, (4, 2)),
     ("st_house_h", 28, 20, 24, 3, "roof_t", True, -7, None, (7, 4)),
     ("st_house_i", 22, 18, 14, 2, "plum_t", False, 0, "banner", None),
     ("st_house_j", 16, 14, 16, 2, "roof_t", False, 3, None, (-3, 2))]
K = 1.3
for n, w, d, h, f, rm, g, dx, shop, ch in T:
    townhouse(n, round(w * K), round(d * K), round(h * K), floors=f, rmat=rm, gable=g, door_x=dx * K, shop=shop, chimney=ch and (ch[0] * K, ch[1] * K))

# city wall segment (tileable 40 px) and gatehouse, pale Ascalon stone with crenels
def crenels(x0, x1, y, z, step=4):
    return [box([x, y, z], [1.1, 1.4, 1.3], "wall_s") for x in [x0 + step / 2 + i * step for i in range(int((x1 - x0) / step))]]
save("st_wall", "Tileable 40 px city wall: pale stone, walkway, crenels.", [
  {"name": "body", "parent": "root", "parts": [box([0, 0, 8], [20, 4, 8], "wall_s")]},
  {"name": "top", "parent": "root", "seam": True, "parts": crenels(-20, 20, -2.8, 17.2)}], yaw=0, frame=[52, 40], anchor=[26, 34])
save("st_gate", "Gatehouse: two square towers with terracotta hip roofs, an arched gate, red banners with a gold mark.", [
  {"name": "arch", "parent": "root", "parts": [box([0, 0, 10], [10, 5, 10], "wall_s"), box([0, -5, 5], [5, 2, 5], "wall_s", subtract=True),
     dict(shape="cylinder", at=[0, -5, 10], r=5, h=2, rot=[90, 0, 0], mat="wall_s", subtract=True)]},
  {"name": "dark", "parent": "root", "parts": [box([0, -2.6, 7], [5, 0.6, 7], "dark")]},
  {"name": "arch_top", "parent": "root", "seam": True, "parts": crenels(-10, 10, -3, 21.2)},
  {"name": "tl", "parent": "root", "seam": True, "parts": [box([-15, 0, 14], [5.5, 6, 14], "wall_s"), st([-15, -6.3, 20], ["a", "a"], {"a": "window"}), st([-15, -6.3, 12], ["a", "a"], {"a": "window"})]},
  {"name": "tr", "parent": "root", "seam": True, "parts": [box([15, 0, 14], [5.5, 6, 14], "wall_s"), st([15, -6.3, 20], ["a", "a"], {"a": "window"}), st([15, -6.3, 12], ["a", "a"], {"a": "window"}), st([20.8, 0, 16], ["a", "a"], {"a": "window"}, normal=(1, 0, 0))]},
  {"name": "rl", "parent": "root", "seam": True, "parts": [roof([-15, 0, 28], [6.6, 7], 7, "roof_t")]},
  {"name": "rr", "parent": "root", "seam": True, "parts": [roof([15, 0, 28], [6.6, 7], 7, "roof_t")]},
  {"name": "banners", "parent": "root", "seam": True, "parts": [box([x, -6.5, 16], [2.2, 0.4, 4.5], "banner") for x in (-15, 15)] +
     [st([x, -7.1, 17], [".a.", "aaa", ".a."], {"a": "gold:2"}) for x in (-15, 15)]}], yaw=0, frame=[72, 64], anchor=[36, 56])
# fountain with 3-frame spray
spray = lambda k: {"name": f"spray{k}", "parent": "root", "parts": [st([0, 0, 9], [["..a..", ".b.b.", "b...b"], [".a.a.", "b.b.b", "....."], ["..a..", "a...a", ".b.b."]][k], {"a": "sea:5", "b": "sea:4"}, overhang=True, depth_tol=40)]}
save("st_fountain", "Round plaza fountain: pale stone basin, pillar with a bowl, sparkling spray.", [
  {"name": "basin", "parent": "root", "parts": [dict(shape="cylinder", at=[0, 0, 1.4], r=8, h=1.4, mat="wall_s", round=0.4)]},
  {"name": "pool", "parent": "root", "parts": [dict(shape="cylinder", at=[0, 0, 2.6], r=6.8, h=0.4, mat="sea")]},
  {"name": "pillar", "parent": "root", "seam": True, "parts": [dict(shape="cylinder", at=[0, 0, 4.5], r=1.2, h=2.5, mat="stone"), dict(shape="cylinder", at=[0, 0, 7.2], r=3.2, h=0.6, mat="stone"), dict(shape="cylinder", at=[0, 0, 7.8], r=2.4, h=0.2, mat="sea")]},
  spray(0), spray(1), spray(2)], yaw=0, frame=[28, 28], anchor=[14, 22],
  clips={"idle": {"loop": True, "frames": [{"pose": {}, "hide": [f"spray{j}" for j in range(3) if j != k], "hold": 4} for k in range(3)]}})
# market stall: counter, goods, pitched awning in one colour with pale stripes
def stall(name, col, goods):
    save(name, f"Market stall with a {col} striped awning.", [
      {"name": "counter", "parent": "root", "parts": [box([0, 0, 2], [5.5, 3, 2], "wood")]},
      {"name": "goods", "parent": "root", "seam": True, "parts": [dict(shape="sphere", at=[x, -1, 4.4], r=1.1, mat=goods) for x in (-3.5, -1.2, 1.2, 3.5)]},
      {"name": "posts", "parent": "root", "parts": [box([x, 2.4, 4], [0.5, 0.5, 4], "wood") for x in (-5, 5)]},
      {"name": "awning", "parent": "root", "seam": True, "parts": [roof([0, 0.4, 8], [6.6, 4.2], 2.6, col, gable=True)] +
         [st([x, -4.2, 8.4], ["a"], {"a": "plaster:3"}) for x in (-4, 0, 4)]}], frame=[24, 24], anchor=[12, 19])
stall("st_stall_red", "banner", "roof")
stall("st_stall_gold", "gold", "leaf")
stall("st_stall_teal", "sea", "leaf_gold")
save("st_well", "Stone well with a little tiled roof.", [
  {"name": "ring", "parent": "root", "parts": [dict(shape="cylinder", at=[0, 0, 1.8], r=3.6, h=1.8, mat="wall_s"), dict(shape="cylinder", at=[0, 0, 3.4], r=2.6, h=0.2, mat="dark")]},
  {"name": "posts", "parent": "root", "parts": [box([x, 0, 5], [0.5, 0.5, 3.4], "wood") for x in (-3.2, 3.2)]},
  {"name": "roof", "parent": "root", "seam": True, "parts": [roof([0, 0, 8.2], [4.6, 3.2], 2.6, "roof_t", gable=True)]}], frame=[20, 24], anchor=[10, 19])
save("st_cart", "Hand cart loaded with sacks and a crate.", [
  {"name": "bed", "parent": "root", "parts": [box([0, 0, 3], [4.5, 2.6, 0.8], "wood"), dict(shape="cylinder", at=[-2, -2.9, 2], r=2, h=0.4, rot=[90, 0, 0], mat="wood")]},
  {"name": "load", "parent": "root", "seam": True, "parts": [dict(shape="sphere", at=[-1.8, 0, 5], r=1.9, mat="sand"), dict(shape="sphere", at=[1, 0.5, 5], r=1.7, mat="sand"), box([2.8, -0.4, 5], [1.4, 1.4, 1.4], "wood")]},
  {"name": "handle", "parent": "root", "parts": [box([6.5, 0, 3.4], [2.4, 0.3, 0.3], "wood")]}], frame=[24, 20], anchor=[11, 15])
save("st_barrels", "Two barrels and a crate.", [
  {"name": "b1", "parent": "root", "parts": [dict(shape="cylinder", at=[-2, 0, 2], r=1.7, h=2, mat="wood", round=0.5)]},
  {"name": "b2", "parent": "root", "seam": True, "parts": [dict(shape="cylinder", at=[1.6, -1.4, 1.9], r=1.6, h=1.9, mat="wood", round=0.5)]},
  {"name": "c", "parent": "root", "seam": True, "parts": [box([1.4, 2, 1.5], [1.5, 1.5, 1.5], "sand")]}], frame=[16, 16], anchor=[8, 12])
save("st_lamp", "Street lamp: dark post, warm lantern.", [
  {"name": "post", "parent": "root", "parts": [box([0, 0, 5], [0.45, 0.45, 5], "dark"), box([0, 0, 0.6], [1, 1, 0.6], "stone")]},
  {"name": "lantern", "parent": "root", "seam": True, "parts": [box([0, 0, 11], [1, 1, 1.2], "glass"), roof([0, 0, 12.2], [1.4, 1.4], 1, "dark")]}], yaw=0, frame=[10, 20], anchor=[5, 16])
save("st_boat", "Canal rowing boat with a cream sail furled on the mast.", [
  {"name": "hull", "parent": "root", "parts": [dict(shape="ellipsoid", at=[0, 0, 0.8], r=[8, 3, 1.6], mat="wood"), dict(shape="ellipsoid", at=[0, 0, 1.8], r=[6.8, 2.1, 1.2], mat="dark", subtract=True)]},
  {"name": "mast", "parent": "root", "seam": True, "parts": [box([-1, 0, 6], [0.4, 0.4, 5], "wood"), box([-1, -0.6, 7], [0.5, 0.5, 3], "plaster")]}], yaw=0, frame=[24, 20], anchor=[12, 15],
  clips={"idle": {"loop": True, "frames": [{"pose": {}, "root": [0, 0, z], "hold": 6} for z in (0, 0.6, 0, -0.4)]}})

for n, hh in (("st_gate", 62), ("st_wall", 30), ("st_boat", 18)):
    p = D + n + ".json"; sp = json.load(open(p)); sp["size"] = {"height": hh}
    if n == "st_boat": sp["frame"], sp["anchor"] = [40, 32], [20, 24]
    json.dump(sp, open(p, "w"), indent=1)

# ---- east-west arched bridge, guild hall, harbour ship, river rowboat, lighthouse
# east-west arched bridge over a north-south river: the arch faces the camera, boats pass through it
L, RISE, CROWN = 22.0, 8.0, 6.0
A = math.degrees(math.atan2(RISE, L - CROWN))
RL = (L - CROWN) / math.cos(math.radians(A)) / 2 + 0.6
def span(hy, mat, dz=0.0, th=1.5, y=0.0):
    off = CROWN + (L - CROWN) / 2
    return [box([0, y, RISE + dz], [CROWN, hy, th], mat),
            box([off, y, RISE / 2 + dz], [RL, hy, th], mat, rot=[0, A, 0]),
            box([-off, y, RISE / 2 + dz], [RL, hy, th], mat, rot=[0, -A, 0])]
save("st_bridge_ew", "Arched stone bridge crossing the river east-west: humped deck, parapets, one round arch facing the viewer.", [
  {"name": "body", "parent": "root", "parts": [box([0, 0, RISE / 2], [CROWN + 8, 6, RISE / 2], "wall_s"),
      dict(shape="cylinder", at=[0, 0, -0.5], r=7.2, h=8, rot=[90, 0, 0], mat="wall_s", subtract=True)]},
  {"name": "deck", "parent": "root", "parts": span(6, "sand")},
  {"name": "parapetN", "parent": "root", "seam": True, "parts": span(0.8, "wall_s", dz=1.6, th=1.3, y=6.2)},
  {"name": "parapetS", "parent": "root", "seam": True, "parts": span(0.8, "wall_s", dz=1.6, th=1.3, y=-6.2)}],
  yaw=0, frame=[52, 30], anchor=[26, 22])
# guild hall: long two-storey hall with a portico and a clock tower
bones = [{"name": "hall", "parent": "root", "parts": [box([0, 0, 11], [26, 13, 11], "plaster")] + windows(52, 26, 22, 2, 0) +
          [st([0, -13.3, 3.5], [".aaaaa.", "abbbbba", "abbbbba", "abbcbba", "abbbbba", "abbbbba"], {"a": "wood:0", "b": "wood:1", "c": "gold"})]},
         {"name": "base", "parent": "root", "parts": [box([0, 0, 1.2], [27, 14, 1.2], "wall_s"), box([0, -17, 0.8], [12, 3.5, 0.8], "wall_s")]},
         {"name": "roof", "parent": "root", "seam": True, "parts": [roof([0, 0, 22], [27.4, 14.4], 10, "plum_t")]},
         {"name": "portico", "parent": "root", "seam": True, "parts": [dict(shape="cylinder", at=[x, -16, 8], r=1.1, h=7, mat="plaster") for x in (-9, -3, 3, 9)] +
            [box([0, -16, 15.6], [11, 2.6, 0.9], "wall_s"), roof([0, -16, 16.5], [11.5, 3.2], 4.5, "roof_t", gable=True)]},
         {"name": "tower", "parent": "root", "seam": True, "parts": [box([0, 5, 22], [6, 6, 22], "plaster"),
            st([0, -1.3, 36], [".aa.", "abba", "abba", ".aa."], {"a": "gold:1", "b": "plaster:3"}), st([6.3, 5, 36], ["aa", "aa"], {"a": "window"}, normal=(1, 0, 0))]},
         {"name": "tower_roof", "parent": "root", "seam": True, "parts": [roof([0, 5, 44], [6.8, 6.8], 8, "roof_t")]},
         {"name": "flag", "parent": "root", "at": [0, 5, 52], "parts": [box([0, 0, 2], [0.4, 0.4, 2], "wood"), box([2, 0, 3.4], [1.8, 0.3, 1.0], "banner")]},
         {"name": "banners", "parent": "root", "seam": True, "parts": [box([x, -13.6, 14], [1.8, 0.4, 4], "banner") for x in (-19, 19)]}]
save("st_hall", "Guild hall: long two-storey hall, columned portico with a pediment, clock tower flying a red flag.", bones,
     frame=[100, 110], anchor=[50, 100],
     clips={"idle": {"loop": True, "frames": [{"pose": {"flag": {"rot": [0, 0, a]}}, "hold": 4} for a in (0, 20, 32, 20, 0, -18)]}})
# harbour ship moored east-west, two masts with furled/half sails, bobbing
save("st_ship", "Two-masted harbour ship: dark wooden hull, cream sails, red pennants, gently bobbing.", [
  {"name": "hull", "parent": "root", "parts": [dict(shape="ellipsoid", at=[0, 0, 1.6], r=[18, 6, 3.2], mat="wood"),
      box([0, 0, 5.6], [30, 30, 2.4], "wood", subtract=True), dict(shape="ellipsoid", at=[0, 0, 3.0], r=[16, 4.6, 1.6], mat="sand")]},
  {"name": "masts", "parent": "root", "seam": True, "parts": [box([x, 0, 12], [0.6, 0.6, 10], "wood") for x in (-6, 6)]},
  # triangular fore-and-aft sails: a gable prism (ridge up the mast) sliced thin, so it faces the viewer
  {"name": "sails", "parent": "root", "seam": True, "parts": sum([[roof([x + 3.6, -0.8, 4.6], [4.2, 30], 14, "plaster", gable=True, rot=[0, 0, 0]),
      box([x + 3.6, 30.4, 10], [8, 30, 12], "plaster", subtract=True), box([x + 3.6, -31.2, 10], [8, 30, 12], "plaster", subtract=True)] for x in (-6, 6)], [])},
  {"name": "pennants", "parent": "root", "seam": True, "parts": [box([x + 1.6, 0, 22.4], [1.6, 0.3, 0.6], "banner") for x in (-6, 6)]}],
  yaw=0, frame=[48, 40], anchor=[24, 32],
  clips={"idle": {"loop": True, "frames": [{"pose": {}, "root": [0, 0, z], "hold": 5} for z in (0, 0.6, 1, 0.6, 0, -0.4)]}})
# river rowboat (hull along y: travels north-south), no mast so it fits under the bridges
save("st_rowboat", "Small river rowboat with a cargo crate, no mast, hull along the river.", [
  {"name": "hull", "parent": "root", "parts": [dict(shape="ellipsoid", at=[0, 0, 0.8], r=[3.2, 8, 1.6], mat="wood"), dict(shape="ellipsoid", at=[0, 0, 1.9], r=[2.2, 6.6, 1.2], mat="dark", subtract=True)]},
  {"name": "load", "parent": "root", "seam": True, "parts": [box([0, 1.5, 2.2], [1.4, 1.6, 1.2], "sand")]}],
  yaw=0, frame=[16, 22], anchor=[8, 15],
  clips={"idle": {"loop": True, "frames": [{"pose": {}, "root": [0, 0, z], "hold": 6} for z in (0, 0.5, 0, -0.3)]}})
# lighthouse at street scale
s = json.load(open(os.path.join(ROOT, 'specs', 'vista', 'lighthouse.json')))
s["name"] = "st_lighthouse"; s["size"] = {"height": 58}; s["frame"] = [48, 80]; s["anchor"] = [24, 72]
json.dump(s, open(D + "st_lighthouse.json", "w"), indent=1)

sp = json.load(open(D + "st_hall.json")); sp["size"] = {"height": 84}; sp["frame"], sp["anchor"] = [130, 130], [65, 120]
json.dump(sp, open(D + "st_hall.json", "w"), indent=1)

# ---- the Arena and its banner poles
random.seed(2)
R, HW = 40.0, 15.0
STEPS = [(22.5, 1.5, 4.5), (27.5, 4.5, 8.0), (32.0, 8.0, 11.5), (36.5, 11.5, HW + 1)]
arches = []
for i in range(14):
    a = math.radians(-90 + (i - 6.5) * 13)
    nx, ny = math.cos(a), math.sin(a)
    arches.append(st([nx * (R + 0.3), ny * (R + 0.3), 5], ["aa", "aa", "aa", "bb"], {"a": "dark:1", "b": "plaster:3"}, normal=(nx, ny, 0)))
    arches.append(st([nx * (R + 0.3), ny * (R + 0.3), 11.5], ["aa", "aa"], {"a": "dark:1"}, normal=(nx, ny, 0)))
crowd = []
cols = ["banner:2", "gold:2", "sea:3", "plaster:3", "roof:2"]
for (r, z0, z1) in STEPS[:3]:
    for k in range(34):
        a = math.radians(random.uniform(0, 360))
        if random.random() < 0.45: continue
        crowd.append(st([math.cos(a) * (r + 1.6), math.sin(a) * (r + 1.6), z1 + 0.2], ["a"], {"a": random.choice(cols)}, normal=(0, 0, 1)))
flags = [{"name": f"flag{i}", "parent": "root", "at": [R * math.cos(math.radians(a)), R * math.sin(math.radians(a)), HW + 1],
          "parts": [box([0, 0, 3], [0.4, 0.4, 3], "wood"), box([2.2, 0, 5], [2, 0.3, 1.2], "banner" if i % 2 else "gold")]}
         for i, a in enumerate((200, 250, 290, 340))]
bones = [
  {"name": "wall", "parent": "root", "parts": [dict(shape="cylinder", at=[0, 0, HW / 2], r=R, h=HW / 2, mat="wall_s")] +
      [dict(shape="cylinder", at=[0, 0, (z0 + z1) / 2 + 0.5], r=r, h=(z1 - z0) / 2 + 0.5, mat="wall_s", subtract=True) for r, z0, z1 in STEPS] + arches + crowd},
  {"name": "floor", "parent": "root", "parts": [dict(shape="cylinder", at=[0, 0, 1.2], r=22.6, h=0.4, mat="sand"),
      st([0, 0, 1.7], [".aaa.", "a...a", "a.b.a", "a...a", ".aaa."], {"a": "sand:1", "b": "gold:1"}, normal=(0, 0, 1))]},
  {"name": "rim", "parent": "root", "seam": True, "parts": [dict(shape="torus", at=[0, 0, HW], R=R - 1.4, r=1.3, mat="plaster")]},
  {"name": "gate", "parent": "root", "seam": True, "parts": [box([0, -R + 1, 9], [8, 3.4, 9], "wall_s"), roof([0, -R + 1, 18], [8.8, 4.2], 5, "roof_t", gable=True),
      st([0, -R - 2.7, 5.5], ["..aaa..", ".aaaaa.", "aabbbaa", "aababaa", "aabbbaa", "aababaa"], {"a": "dark:0", "b": "dark:2"}),
      st([0, -R - 2.7, 13.5], [".a.", "aba", ".a."], {"a": "gold:2", "b": "banner:2"})]},
  {"name": "banners", "parent": "root", "seam": True, "parts": [box([x, -R - 0.8 + abs(x) * 0.12, 10], [1.8, 0.4, 3.6], "banner") for x in (-14, 14)] +
      [st([x, -R - 1.4 + abs(x) * 0.12, 11], ["a", "a"], {"a": "gold:2"}) for x in (-14, 14)]}] + flags
fr = [{"pose": {f"flag{i}": {"rot": [0, 0, a + i * 9]} for i in range(4)}, "hold": 4} for a in (0, 22, 34, 22, 0, -18)]
save("st_arena", "The Arena: round pale-stone colosseum, stepped seating with a sparse crowd, sand floor with a crest, arches, main gate, flags.",
     bones, yaw=0, frame=[112, 100], anchor=[56, 80], clips={"idle": {"loop": True, "frames": fr}})

sp_ = json.load(open(D + "st_arena.json")); sp_["size"] = {"height": 50}; sp_["frame"], sp_["anchor"] = [150, 130], [75, 104]
json.dump(sp_, open(D + "st_arena.json", "w"), indent=1)
save("banner_pole_v", "Tall tournament banner pole with a long red pennant.", [
  {"name": "pole", "parent": "root", "parts": [box([0, 0, 10], [0.45, 0.45, 10], "wood"), dict(shape="sphere", at=[0, 0, 20.4], r=0.8, mat="gold")]},
  {"name": "flag", "parent": "root", "at": [0.5, 0, 19], "seam": True, "parts": [box([2.8, 0, -2.4], [2.6, 0.3, 2.4], "banner"), st([2.6, -0.5, -2.2], ["a"], {"a": "gold:2"})]}],
  yaw=0, frame=[20, 32], anchor=[8, 28], clips={"idle": {"loop": True, "frames": [{"pose": {"flag": {"rot": [0, 0, a]}}, "hold": 4} for a in (-10, 14, 26, 14, -10, -22)]}})

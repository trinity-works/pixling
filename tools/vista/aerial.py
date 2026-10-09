"""Aerial vista kit (Highgate overview + world map towns): houses, keep, chapel, lighthouse, fountain, market, sailboat."""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from vlib import *
# town houses: a handful of footprints/heights, two roof colours, hip and gable
H = [("house_1", 10, 8, 6, 1, "roof", False, (2, 1)), ("house_2", 14, 8, 9, 2, "roof", True, None),
     ("house_3", 8, 8, 12, 3, "roof_plum", False, None), ("house_4", 12, 10, 8, 2, "roof", False, (-3, 2)),
     ("house_5", 16, 9, 7, 1, "roof_plum", True, (4, 1)), ("house_6", 9, 12, 10, 2, "roof", True, None),
     ("house_7", 7, 6, 5, 1, "roof", False, None), ("house_8", 11, 7, 13, 3, "roof", False, (3, 1))]
K = 1.3
for n, w, d, h, f, rm, g, ch in H:
    house(n, round(w * K), round(d * K), round(h * K), floors=f, rmat=rm, gable=g, chimney=ch and (ch[0] * K, ch[1] * K))

def tower(x, y, s, h, rh, rmat="roof"):
    return [box([x, y, h / 2], [s / 2, s / 2, h / 2], "plaster")] , roof([x, y, h], [s / 2 + 0.7, s / 2 + 0.7], rh, rmat)
# keep: Ascalon-style great hall, four corner towers, a taller donjon, gate arch, red banners
bones = [{"name": "hall", "parent": "root", "parts": [box([0, 0, 5.5], [13, 8, 5.5], "plaster")] + facade(26, 16, 11, 2) +
          [st([0, -8.3, 2], [".aaa.", "aaaaa", "aaaaa"], {"a": "window"})]},
         {"name": "hall_roof", "parent": "root", "seam": True, "parts": [roof([0, 0, 11], [13.7, 8.7], 7.5, "roof")]},
         {"name": "banners", "parent": "root", "parts": [box([x, -8.4, 7], [1.1, 0.3, 2.4], "banner") for x in (-7, 7)]}]
for i, (x, y) in enumerate([(-14, -8), (14, -8), (-14, 8), (14, 8)]):
    wall, rf = tower(x, y, 6, 13 if y < 0 else 17, 4.5)
    bones.append({"name": f"tw{i}", "parent": "root", "seam": True, "parts": wall +
                  [st([x, y - 3.3, 10], ["a", ".", "a"], {"a": "window"}), st([x + 3.3, y, 10], ["a"], {"a": "window"}, normal=(1, 0, 0))]})
    bones.append({"name": f"tr{i}", "parent": "root", "seam": True, "parts": [rf]})
wall, rf = tower(3, 5, 8, 24, 6.5)
bones.append({"name": "donjon", "parent": "root", "seam": True, "parts": wall + [st([3, 0.7, 20], ["a.a"], {"a": "window"}), st([7.3, 5, 20], ["a.a"], {"a": "window"}, normal=(1, 0, 0))]})
bones.append({"name": "donjon_roof", "parent": "root", "seam": True, "parts": [rf]})
bones.append({"name": "flag", "parent": "root", "at": [3, 5, 30.5], "parts": [box([0, 0, 2], [0.4, 0.4, 2], "wood"), box([1.6, 0, 3.4], [1.4, 0.3, 0.8], "banner")]})
save("keep", "Ascalon-style keep: long hall with a terracotta hip roof, four corner towers, a tall donjon flying a red flag, banners by the gate.",
     bones, frame=[72, 80], anchor=[36, 70],
     clips={"idle": {"loop": True, "frames": [{"pose": {"flag": {"rot": [0, 0, a]}}, "hold": 4} for a in (0, 20, 32, 20, 0, -18)]}})
# chapel with bell tower
save("chapel", "Chapel: long gabled nave, square bell tower with a pyramid roof and an open belfry.", [
  {"name": "nave", "parent": "root", "parts": [box([0, 2, 5], [5, 8, 5], "plaster")] + [st([5.3, 2, 5], ["a.a.a"], {"a": "window"}, normal=(1, 0, 0)), st([0, -6.3, 3], ["a", "a"], {"a": "window"})]},
  {"name": "nave_roof", "parent": "root", "seam": True, "parts": [roof([0, 2, 10], [5.7, 8.7], 5, "roof", gable=True)]},
  {"name": "tower", "parent": "root", "seam": True, "parts": [box([0, -8, 10], [3.2, 3.2, 10], "plaster"), st([0, -11.5, 16], ["a.a", "a.a"], {"a": "window"}), st([3.5, -8, 16], ["a"], {"a": "window"}, normal=(1, 0, 0))]},
  {"name": "tower_roof", "parent": "root", "seam": True, "parts": [roof([0, -8, 20], [3.9, 3.9], 5, "roof_plum")]}],
  frame=[48, 64], anchor=[24, 56])
# lighthouse on a rock: white tower, red cap, lamp that pulses
lamp = lambda k: {"name": f"lamp{k}", "parent": "root", "parts": [box([0, 0, 22], [1.6, 1.6, 1.4], "glass" if k else "gold")]}
save("lighthouse", "Harbour lighthouse on a rock: tapered white tower, red band and cap, a lamp that pulses.", [
  {"name": "rock", "parent": "root", "parts": [dict(shape="ellipsoid", at=[0, 0, 0.5], r=[6, 5, 2.4], mat="rock")]},
  {"name": "tower", "parent": "root", "seam": True, "parts": [dict(shape="cone", at=[0, 0, 1], r=3.6, r_top=2.2, h=20, mat="plaster", flat=True),
     dict(shape="cylinder", at=[0, 0, 12], r=3.3, h=1.4, mat="banner"), st([0, -3.2, 8], ["a"], {"a": "window"})]},
  lamp(0), lamp(1),
  {"name": "cap", "parent": "root", "seam": True, "parts": [dict(shape="cone", at=[0, 0, 23.4], r=2.8, h=3.4, mat="banner")]}],
  frame=[32, 56], anchor=[16, 48], yaw=0,
  clips={"idle": {"loop": True, "frames": [{"pose": {}, "hide": ["lamp1"], "hold": 12}, {"pose": {}, "hide": ["lamp0"], "hold": 8}]}})
# fountain
save("fountain_small", "Small round plaza fountain.", [
  {"name": "basin", "parent": "root", "parts": [dict(shape="cylinder", at=[0, 0, 1], r=4, h=1, mat="stone"), dict(shape="cylinder", at=[0, 0, 1.6], r=3.2, h=0.9, mat="sea", subtract=False)]},
  {"name": "pillar", "parent": "root", "seam": True, "parts": [dict(shape="cylinder", at=[0, 0, 3.5], r=0.9, h=2, mat="stone"), st([0, 0, 6.2], ["a"], {"a": "sea:5"}, overhang=True, depth_tol=20)]}],
  frame=[20, 20], anchor=[10, 15], yaw=0)
# market awnings (a row of three coloured stalls)
save("market", "Row of three market stalls with red, gold and teal awnings.", [
  {"name": f"s{i}", "parent": "root", "seam": True, "parts": [box([x, 0, 1.6], [2.2, 1.6, 1.6], "wood"), roof([x, 0, 3.2], [2.8, 2.4], 2.2, m, gable=True)]}
  for i, (x, m) in enumerate([(-6, "banner"), (0, "gold"), (6, "sea")])], frame=[32, 20], anchor=[16, 14])
# sailboat
save("sailboat", "Small sailboat seen from above: wooden hull, cream sail.", [
  {"name": "hull", "parent": "root", "parts": [dict(shape="ellipsoid", at=[0, 0, 0.8], r=[4.6, 1.8, 1.2], mat="wood")]},
  {"name": "sail", "parent": "root", "seam": True, "parts": [box([0.6, 0, 4], [2.4, 0.3, 3.2], "plaster", rot=[0, 0, 20]), box([-0.8, 0, 4.2], [0.3, 0.3, 3.6], "wood")]}],
  frame=[20, 20], anchor=[10, 15], yaw=0,
  clips={"idle": {"loop": True, "frames": [{"pose": {}, "root": [0, 0, z], "hold": 6} for z in (0, 0.6, 0, -0.4)]}})

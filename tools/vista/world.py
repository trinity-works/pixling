"""World-map vista kit: dungeons (crypt, mines), raid tower, realm portal, adventurers' camp, windmill, enemy spots, your banner.
Mountains, forests, rivers and bridges are painted terrain (pp.map massif / canopy / sea / bridge), not sprites."""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import math, json
import vlib
from vlib import box, roof, st
vlib.D = os.path.join(vlib.ROOT, 'specs', 'vista', 'world') + os.sep
save = vlib.save
M = {"rock_d": {"ramp": "rock", "shades": [0, 1, 2, 3], "thresholds": [0.35, 0.6, 0.85], "detail": {"kind": "stone", "scale": 1.6, "amount": 0.5}},
     "snow": {"ramp": "plaster", "shades": [1, 2, 3], "thresholds": [0.5, 0.8], "sky": 0.3},
     "spire": {"ramp": "ink", "shades": [0, 1, 2], "thresholds": [0.45, 0.8]}}
def cone(at, r, h, mat, **k): return dict(shape="cone", at=at, r=r, h=h, mat=mat, flat=True, **k)
glow = lambda k, parts: {"name": f"g{k}", "parent": "root", "parts": parts}
flick = {"idle": {"loop": True, "frames": [{"pose": {}, "hide": ["g1"], "hold": 6}, {"pose": {}, "hide": ["g0"], "hold": 4}, {"pose": {}, "hide": ["g1"], "hold": 6}, {"pose": {}, "hide": ["g0"], "hold": 4}]}}
# dungeon 1: the Hollow Crypt, a ruined mausoleum in the forest
save("w_crypt", "Dungeon: ruined mausoleum, cracked gable roof, dark doorway, two arcane braziers.", [
  {"name": "body", "parent": "root", "parts": [box([0, 0, 4.5], [7, 5, 4.5], "stone"), st([0, -5.3, 2.4], [".a.", "aaa", "aaa"], {"a": "dark:0"})]},
  {"name": "roof", "parent": "root", "seam": True, "parts": [roof([0, 0, 9], [7.8, 5.8], 4.5, "stone", gable=True), box([5, -2, 12], [3, 3, 3], "stone", subtract=True)]},
  {"name": "pillars", "parent": "root", "seam": True, "parts": [box([x, -8, 2.5], [0.9, 0.9, 2.5], "stone") for x in (-5, 5)] + [box([-5, -8, 5.4], [1.2, 1.2, 0.4], "stone")]},
  glow(0, [box([x, -8, 5.9], [0.8, 0.8, 0.8], "arcane") for x in (-5,)] + [st([5, -8, 5.5], ["a"], {"a": "arcane:1"}, overhang=True, depth_tol=20)]),
  glow(1, [box([x, -8, 6.2], [0.7, 0.7, 1.1], "arcane") for x in (-5,)] + [st([5, -8, 5.5], ["a", "a"], {"a": "arcane:2"}, overhang=True, depth_tol=20)])],
  yaw=-20, frame=[40, 40], anchor=[20, 32], clips=flick, mats=M)
# dungeon 2: the Ember Mines, a cave mouth in a rock mound with torches and rails
save("w_mine", "Dungeon: mine entrance in a rocky mound, timber frame, two torches, rails running out.", [
  {"name": "mound", "parent": "root", "parts": [dict(shape="ellipsoid", at=[0, 2, 1], r=[12, 8, 8], mat="rock_d"), box([0, 0, -10], [20, 20, 10], "rock_d", subtract=True)]},
  {"name": "frame", "parent": "root", "seam": True, "parts": [box([x, -5.6, 3], [0.8, 0.8, 3], "wood") for x in (-3.4, 3.4)] + [box([0, -5.6, 6.4], [4.4, 0.9, 0.7], "wood"),
     st([0, -6.4, 3], ["aaaaa", "aaaaa", "aaaaa", "aaaaa"], {"a": "dark:0"})]},
  {"name": "rails", "parent": "root", "parts": [st([0, -9, 0.2], ["a.a", "bbb", "a.a", "bbb", "a.a"], {"a": "wood:1", "b": "stone:1"}, overhang=True)]},
  glow(0, [box([x, -6.6, 6], [0.6, 0.6, 0.8], "torch") for x in (-5, 5)]),
  glow(1, [box([x, -6.6, 6.3], [0.6, 0.6, 1.2], "torch") for x in (-5, 5)])],
  yaw=0, frame=[40, 36], anchor=[20, 28], clips=flick, mats=M)
# raid: Blackspire, a dark broken tower with arcane windows
save("w_spire", "Raid: Blackspire, a tall black tower with a broken crown and glowing arcane windows.", [
  {"name": "base", "parent": "root", "parts": [cone([0, 0, 0], 7, 6, "rock_d", r_top=5)]},
  {"name": "tower", "parent": "root", "seam": True, "parts": [cone([0, 0, 5], 4.6, 30, "spire", r_top=3.2), box([2, -2, 36], [3, 3, 3], "spire", subtract=True)]},
  {"name": "horns", "parent": "root", "seam": True, "parts": [cone([x, 0, 33], 1.2, 6, "spire", r_top=0.2) for x in (-2.6, 2.6)]},
  glow(0, [st([0, -4.6, z], ["a"], {"a": "arcane:1"}) for z in (12, 20, 28)]),
  glow(1, [st([0, -4.6, z], ["a"], {"a": "arcane:3"}) for z in (12, 20, 28)] + [st([-1.6, -4, 24], ["a"], {"a": "arcane:2"})])],
  yaw=0, frame=[28, 64], anchor=[14, 56], clips=flick, mats=M)
# realm portal: standing ring with a swirling core and four standing stones
swirl = lambda k: {"name": f"sw{k}", "parent": "root", "parts": [st([0, -0.2, 8], [[".aba.", "ab.ba", "b.c.b", "ab.ba", ".aba."], [".bab.", "ba.ab", "a.c.a", "ba.ab", ".bab."]][k],
                    {"a": "arcane:3", "b": "arcane:1", "c": "arcane:2"}, overhang=True, depth_tol=30)]}
save("w_portal", "Realm gate: ring of pale stone standing upright, swirling arcane core, four standing stones.", [
  {"name": "ring", "parent": "root", "parts": [dict(shape="torus", at=[0, 0, 8], R=6.4, r=1.4, rot=[90, 0, 0], mat="stone")]},
  {"name": "core", "parent": "root", "parts": [dict(shape="cylinder", at=[0, 0, 8], r=5, h=0.4, rot=[90, 0, 0], mat="arcane")]},
  swirl(0), swirl(1),
  {"name": "stones", "parent": "root", "seam": True, "parts": [box([x, y, 2.2], [1, 1, 2.2], "stone") for x, y in ((-10, -4), (10, -4), (-8, 6), (8, 6))]},
  {"name": "dais", "parent": "root", "parts": [dict(shape="cylinder", at=[0, 0, 0.4], r=9, h=0.4, mat="stone")]}],
  yaw=0, frame=[32, 36], anchor=[16, 28], mats=M,
  clips={"idle": {"loop": True, "frames": [{"pose": {}, "hide": ["sw1"], "hold": 6}, {"pose": {}, "hide": ["sw0"], "hold": 6}]}})
# adventurers' camp
save("w_camp", "Adventurers' camp: two canvas tents, a red banner tent, a campfire.", [
  {"name": "t1", "parent": "root", "seam": True, "parts": [roof([-5, 0, 0], [3, 4], 5, "plaster", gable=True)]},
  {"name": "t2", "parent": "root", "seam": True, "parts": [roof([4, 3, 0], [3, 4], 5, "banner", gable=True)]},
  {"name": "t3", "parent": "root", "seam": True, "parts": [roof([2, -6, 0], [2.4, 3], 4, "plaster", gable=True)]},
  glow(0, [box([-1, -3, 0.6], [0.8, 0.8, 0.6], "torch")]), glow(1, [box([-1, -3, 0.9], [0.8, 0.8, 1.0], "torch")])],
  yaw=-20, frame=[28, 24], anchor=[14, 18], clips=flick, mats=M)
# small windmill (farm villages)
blade = lambda a: dict(shape="box", at=[3.4 * math.sin(math.radians(a)), 0, 3.4 * math.cos(math.radians(a))], half=[0.8, 0.25, 3.0], rot=[0, a, 0], mat="plaster")
save("w_windmill", "Farm windmill: white tapered tower, red cap, four turning sails.", [
  {"name": "body", "parent": "root", "parts": [cone([0, 0, 0], 3.6, 11, "plaster", r_top=2.4)]},
  {"name": "cap", "parent": "root", "seam": True, "parts": [cone([0, 0, 10.6], 3, 3.4, "roof", r_top=0.4)]},
  {"name": "hub", "parent": "root", "at": [0, -3, 11], "seam": True, "z_bias": -3, "parts": [blade(a) for a in (0, 90, 180, 270)]}],
  yaw=0, frame=[24, 32], anchor=[12, 26], mats=M,
  clips={"idle": {"loop": True, "frames": [{"pose": {"hub": {"rot": [0, a, 0]}}, "hold": 5} for a in range(0, 90, 30)]}})

# map-scale sizes (the helpers author at a nominal scale; the forge refits to these heights)
for n, h, grow in (("w_camp", 14, None),):
    p = vlib.D + n + ".json"; sp = json.load(open(p)); sp["size"] = {"height": h}
    if grow:
        sp["frame"] = [int(sp["frame"][0] * grow), int(sp["frame"][1] * grow)]; sp["anchor"] = [sp["frame"][0] // 2, sp["frame"][1] - 10]
    else:
        sp["frame"], sp["anchor"] = [40, 34], [20, 26]
    json.dump(sp, open(p, "w"), indent=1)

# ---- enemy spots: cleared to push the fog back (they replace plain outposts on the map)
import math as _m
blink = {"idle": {"loop": True, "frames": [{"pose": {}, "hide": ["g1"], "hold": 20}, {"pose": {}, "hide": ["g0"], "hold": 2}, {"pose": {}, "hide": ["g1"], "hold": 14}, {"pose": {}, "hide": ["g0"], "hold": 2},
                                           {"pose": {}, "hide": ["g1"], "hold": 2}]}}
stakes = lambda cx, cy, R, a0, a1, n, h=3.2: [box([cx + R * _m.cos(_m.radians(a0 + (a1 - a0) * i / (n - 1))), cy + R * _m.sin(_m.radians(a0 + (a1 - a0) * i / (n - 1))), h / 2],
                                              [0.7, 0.7, h / 2], "wood") for i in range(n)]
save("w_bandit_camp", "Enemy spot: bandit camp, a stake palisade round two dark tents, a red flag and a campfire.", [
  {"name": "palisade", "parent": "root", "parts": stakes(0, 1, 10, 200, 340, 7, h=3.6)},
  {"name": "t1", "parent": "root", "seam": True, "parts": [roof([-4, 2, 0], [3.6, 4.2], 5.6, "roof_plum", gable=True)]},
  {"name": "t2", "parent": "root", "seam": True, "parts": [roof([4.5, 3, 0], [3.2, 3.8], 5.0, "banner", gable=True)]},
  {"name": "flag", "parent": "root", "at": [7.5, -3, 0], "parts": [box([0, 0, 4], [0.35, 0.35, 4], "wood"), box([1.4, 0, 7], [1.2, 0.3, 0.8], "banner")]},
  glow(0, [box([0, -4, 0.6], [0.8, 0.8, 0.6], "torch")]), glow(1, [box([0, -4, 0.9], [0.8, 0.8, 1.0], "torch")])],
  yaw=-15, frame=[32, 28], anchor=[16, 20], clips=flick, mats=M)
save("w_goblin_warren", "Enemy spot: goblin warren, three hide dome huts behind sharpened stakes and a skull totem with glowing eyes.", [
  {"name": "huts", "parent": "root", "parts": [dict(shape="ellipsoid", at=[x, y, 0.4], r=[r, r * 0.9, r * 0.9], mat="leaf") for x, y, r in ((-4.5, 2, 4.0), (4, 3, 3.6), (0, -1.5, 3.0))] +
     [box([0, 0, -6], [14, 14, 6], "leaf", subtract=True)]},
  {"name": "doors", "parent": "root", "parts": [st([0, -4.6, 1.2], ["a", "a"], {"a": "dark:0"}), st([-4.5, -1.8, 1.4], ["a", "a"], {"a": "dark:0"}), st([4, -0.5, 1.4], ["a"], {"a": "dark:0"})]},
  {"name": "stakes", "parent": "root", "seam": True, "parts": [dict(shape="cone", at=[x, -6.5, 0], r=0.7, h=3.2, mat="wood", flat=True, r_top=0.1) for x in (-7, -4.5, -2, 2, 4.5, 7)]},
  {"name": "totem", "parent": "root", "seam": True, "parts": [box([8, 0, 2.6], [0.5, 0.5, 2.6], "wood"), dict(shape="sphere", at=[8, 0, 5.6], r=1.2, mat="plaster")]},
  glow(0, [st([8, -1.2, 5.8], ["a.a"], {"a": "torch:2"}, overhang=True)]), glow(1, [st([8, -1.2, 5.8], ["a.a"], {"a": "torch:0"}, overhang=True)])],
  yaw=-15, frame=[32, 26], anchor=[16, 19], clips=flick, mats=M)
save("w_wolf_den", "Enemy spot: wolf den, a rocky mound with a dark cave mouth, scattered bones and eyes blinking in the dark.", [
  {"name": "mound", "parent": "root", "parts": [dict(shape="ellipsoid", at=[0, 2, 0.5], r=[10, 7, 6.5], mat="rock_d"), box([0, 0, -8], [16, 16, 8], "rock_d", subtract=True)]},
  {"name": "mouth", "parent": "root", "parts": [st([0, -5.4, 2], [".aaa.", "aaaaa", "aaaaa"], {"a": "dark:0"})]},
  {"name": "bones", "parent": "root", "parts": [st([x, -8, 0.2], ["ab"], {"a": "plaster:3", "b": "plaster:2"}, overhang=True) for x in (-5, 3, 6)]},
  glow(0, [st([0, -5.8, 2.2], ["a.a"], {"a": "torch:2"})]), glow(1, [])],
  yaw=0, frame=[32, 26], anchor=[16, 20], clips=blink, mats=M)
save("w_smuggler_cove", "Enemy spot: smugglers' cove, a tarred shack on stilts, stacked crates and a lantern.", [
  {"name": "stilts", "parent": "root", "parts": [box([x, y, 1.5], [0.5, 0.5, 1.5], "wood") for x in (-4, 4) for y in (-2, 3)]},
  {"name": "shack", "parent": "root", "seam": True, "parts": [box([0, 0.5, 5], [5, 3.6, 2], "wood"), roof([0, 0.5, 7], [5.8, 4.2], 3, "roof_plum", gable=True),
     st([1.5, -3.4, 5], ["a"], {"a": "dark:0"})]},
  {"name": "crates", "parent": "root", "seam": True, "parts": [box([8, -2, 1.3], [1.3, 1.3, 1.3], "sand"), box([8.6, 0.8, 1.3], [1.3, 1.3, 1.3], "sand"), box([8.3, -0.6, 3.6], [1.2, 1.2, 1.0], "sand")]},
  glow(0, [box([-6, -3, 3.8], [0.7, 0.7, 0.8], "torch")]), glow(1, [box([-6, -3, 3.8], [0.7, 0.7, 0.8], "glass")])],
  yaw=-15, frame=[32, 26], anchor=[15, 20], clips=flick, mats=M)
# your banner, planted on a cleared spot (drawn live by the game, so it can appear after a claim)
save("w_banner", "Your banner: pole with a gold-trimmed red pennant, fluttering.", [
  {"name": "pole", "parent": "root", "parts": [box([0, 0, 5], [0.4, 0.4, 5], "wood"), dict(shape="sphere", at=[0, 0, 10.4], r=0.6, mat="gold")]},
  {"name": "flag", "parent": "root", "at": [0.4, 0, 9.4], "seam": True, "parts": [box([2.2, 0, -1.5], [2, 0.3, 1.6], "banner"), box([2.2, -0.4, -2.9], [2, 0.3, 0.3], "gold")]}],
  yaw=0, frame=[16, 18], anchor=[5, 15], mats=M,
  clips={"idle": {"loop": True, "frames": [{"pose": {"flag": {"rot": [0, 0, a]}}, "hold": 1} for a in (0, 18, 30, 18, 0, -16)]}})

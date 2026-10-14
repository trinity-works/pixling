"""arena: the committed map holds its zone budgets, the level data is complete and sound for the user's units
(collision, nav, LOS, zones: reachability, fairness, spawn safety, nothing gets stuck, colliders on the painted props),
the sizes are game-useful, the palette keeps the units' hues free, and the one-file viewer bundles without any units."""
import json
import math
import tempfile
import unittest
from pathlib import Path

import numpy as np

from arena import build, check, game, level as LV, place as P, zones as Z
from arena.palette import PAL, UNIT_HUES, rgb

ART = build.ART


class Budgets(unittest.TestCase):
    def test_lint_holds(self):
        self.assertEqual(Z.lint(ART, quiet=True), 0)

    def test_zone_table(self):
        for name, z in Z.ZONES.items():
            self.assertEqual(len(z["haze"]), Z.NL, name)
            self.assertLessEqual(z["value"][0], z["value"][1], name)
        # the back keeps texture: more than two steps and only a small cleanup
        for name in ("backdrop", "vista"):
            self.assertGreaterEqual(Z.ZONES[name]["steps"], 3)
            self.assertLessEqual(Z.ZONES[name]["clean"][0], 2)
        # the sun's pinks are allowed in the vista and nowhere on the playfield
        self.assertGreater(Z.ZONES["vista"]["sun"], 0.5)
        self.assertEqual(Z.ZONES["playfield"]["sun"], 0.0)


class Palette(unittest.TestCase):
    def test_unit_hues_kept_free(self):
        for k, h in PAL.items():
            if k in Z.SUN_KEYS:
                continue
            c = np.array(rgb(h), float)
            self.assertFalse(Z.unit_mask(c[None, None])[0, 0], f"{k} {h} sits in a unit hue band")

    def test_playfield_two_tones_light(self):
        lit, shade = Z.luma(np.array(rgb(PAL["pf_lit"]))), Z.luma(np.array(rgb(PAL["pf_shade"])))
        self.assertGreater(lit - shade, 0.1)
        self.assertGreater(shade - Z.OUTLINE, 0.3)            # a unit's dark outline stands off the field
        self.assertGreater(lit, Z.luma(np.array(rgb(PAL["ta0"]))) + 0.3)   # the frame's spruce is far darker


class Level(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.L = json.loads((ART / "level.json").read_text())

    def test_grid(self):
        g = self.L["grid"]
        self.assertEqual(len(g["kind"]), g["nv"])
        self.assertEqual(len(g["height_cm"]), g["nv"])
        self.assertTrue(all(len(r) == g["nu"] and set(r) <= set("012") for r in g["kind"]))
        walk = sum(r.count("1") + r.count("2") for r in g["kind"]) * g["cell"] ** 2
        self.assertGreater(walk, 1000)                        # square metres of walkable ground

    def test_spawns_objectives_levels(self):
        L, g = self.L, self.L["grid"]
        for side in ("west", "east"):
            self.assertGreaterEqual(len(L["spawns"][side]), 8)
            for u, v, z in L["spawns"][side]:
                i, j = int((v - g["v0"]) / g["cell"]), int((u - g["u0"]) / g["cell"])
                self.assertNotEqual(g["kind"][i][j], "0")
        kinds = {o["kind"] for o in L["objectives"]}
        self.assertTrue({"stones", "heart", "tower"} <= kinds)
        self.assertEqual([lv["id"] for lv in L["levels"]], [0, 1, 2])
        self.assertEqual(L["version"], 4)
        pr = L["projection"]
        sx, sy = pr["x0"] + 10 * pr["ppm"], pr["y0"] - (5 * pr["sin_el"] + 2 * pr["cos_el"]) * pr["ppm"]
        self.assertEqual((round(sx, 3), round(sy, 3)), tuple(round(x, 3) for x in P.proj(10, 5, 2)))

    def test_routes_reach_both_camps(self):
        for name, pts in self.L["lanes"].items():
            self.assertLess(pts[0][0], -10, name)
            if name != "perch":
                self.assertGreater(pts[-1][0], 10, name)


class Game(unittest.TestCase):
    """the level as a game sees it (arena/check.py does the same, longer, for `python3 -m arena check`)"""
    @classmethod
    def setUpClass(cls):
        cls.lv = check.load()
        cls.fields = {}
        cls.un, cls.fields = check.reach(cls.lv, 0.5, cls.fields)

    def test_data(self):
        L, lv = self.lv.L, self.lv
        for k in ("rules", "levels", "colliders", "nav", "zones", "visibility", "projection", "grid", "spawns"):
            self.assertIn(k, L)
        self.assertEqual(len(lv.clear[0]), lv.nu * lv.nv)
        self.assertEqual(len(lv.z), lv.nu * lv.nv)
        kinds = {s["kind"] for s in lv.shapes}
        self.assertTrue({"wall", "lip", "spruce", "tent", "palisade", "kerb", "bridge rail", "deck"} <= kinds)
        for s in lv.shapes:
            self.assertIn(s["shape"], ("circle", "box", "seg"))
            self.assertLess(s["z0"], s["z1"])
        self.assertEqual(len(L["zones"]["spawns"]["west"]["points"]), len(L["zones"]["spawns"]["east"]["points"]))
        self.assertTrue(any(lk["kind"] == "ramp" for lk in L["nav"]["links"]))
        self.assertEqual(sum(1 for lk in L["nav"]["links"] if lk["kind"] == "deck end" and lk["pairs"]), 2)

    def test_vertical_rule(self):
        lv = self.lv
        rail = next(s for s in lv.shapes if s["kind"] == "bridge rail")
        deck = next(s for s in lv.shapes if s["kind"] == "deck")
        floor = lv.hf_z(0.0, 7.0)                              # the corridor under the bridge
        self.assertFalse(lv.blocks(rail, floor))              # the rails touch the deck only
        self.assertTrue(lv.blocks(rail, lv.deck_z(7.0)))
        self.assertFalse(lv.blocks(deck, floor))              # a person walks under the deck ...
        self.assertGreater(deck["z0"] - floor, 1.5 * P.HUMAN)  # ... with room over a person (levels[2].headroom)
        self.assertAlmostEqual(self.lv.L["levels"][2]["headroom"][0], deck["z0"] - max(
            lv.z[k] for k in range(lv.N) if lv.clear[0][k] > 0 and abs(lv.centre(k)[0]) < 1.8
            and lv.L["levels"][2]["v0"] < lv.centre(k)[1] < lv.L["levels"][2]["v1"] and lv.z[k] < 1.5), delta=0.02)
        self.assertFalse(lv.blocks(deck, lv.deck_z(7.0)))     # and on it

    def test_reachable_and_fair(self):
        self.assertEqual(len(self.un["west"]) + len(self.un["east"]), 0)
        rows = check.fairness(self.lv, 0.5, self.fields)
        self.assertGreaterEqual(len(rows), 5)
        for r in rows:
            self.assertIsNotNone(r["west"], r["target"]); self.assertIsNotNone(r["east"], r["target"])
            self.assertTrue(r["ok"], f"{r['target']}: {r['west']:.2f} vs {r['east']:.2f}")

    def test_spawns_hidden(self):
        self.assertEqual(check.spawn_los(self.lv), [])

    def test_not_stuck(self):
        n, bad = check.sweep(self.lv, 0.5)
        self.assertGreater(n, 10000)
        self.assertEqual(bad, [])
        wedged, lost = check.walkers(self.lv, 30, 120, fields=self.fields)
        self.assertEqual((wedged, lost), ([], []))
        fails, lens = check.followers(self.lv, 5, fields=self.fields)
        self.assertEqual(fails, [])

    def test_los(self):
        lv = self.lv
        # the terrace's wall hides a unit at its foot from one on the far side of the top; the deck hides the corridor
        self.assertFalse(lv.los((0.0, -9.6, 0), (0.0, 1.5, 0)))
        self.assertFalse(lv.los((0.0, 6.9, 0), (0.0, 6.9, 1)))
        self.assertTrue(lv.los((-14.0, -1.6, 0), (-12.0, -1.6, 0)))
        # the batched LOS (coarse visibility) is the same test
        import random
        rng = random.Random(3)
        pts = [lv.centre(k) for k in rng.sample(list(np.nonzero(lv.clear[0] >= 0.3)[0]), 60)]
        A = (pts[0][0], pts[0][1], lv.hf_z(*pts[0]) + lv.eye)
        Bs = [(u, v, lv.hf_z(u, v) + lv.eye) for u, v in pts[1:]]
        self.assertEqual(list(LV.los_from(lv, A, Bs)), [lv.clear_line(A, B) for B in Bs])

    def test_colliders_on_the_art(self):
        res, (wh, wn) = check.art_samples(self.lv)
        poor = [(x["kind"], round(x["u"], 1), round(x["v"], 1)) for x in res if x["share"] < 0.5]
        self.assertEqual(poor, [])
        self.assertGreater(np.mean([x["share"] for x in res]), 0.9)
        self.assertGreater(wh, 0.85 * wn)


class Parity(unittest.TestCase):
    """web/level.js answers exactly as arena/game.py (paths, LOS, moves) on the same level.json"""
    def test_js_matches_python(self):
        import shutil, subprocess
        node = shutil.which("node")
        if not node:
            self.skipTest("no node")
        lv = check.load()
        import random
        rng = random.Random(7)
        cells = [int(k) for k in np.nonzero(lv.clear[0] >= 0.5)[0]]
        pts = [lv.centre(k) for k in rng.sample(cells, 24)]
        q = dict(paths=[[[*pts[i], 0], [*pts[i + 1], 0]] for i in range(0, 8, 2)] + [[[0.6, 13.0, 0], [-14.0, -1.6, 0]]],
                 los=[[[*pts[i], 0], [*pts[i + 1], 0]] for i in range(0, 24, 2)],
                 moves=[[pts[i][0], pts[i][1], 0.5, 0.31 * math.cos(i), 0.31 * math.sin(i)] for i in range(12)])
        js = """
const L = require(process.argv[1]); const fs = require('fs');
const lv = L.load(JSON.parse(fs.readFileSync(process.argv[2])));
const q = JSON.parse(fs.readFileSync(process.argv[3]));
const out = {paths: q.paths.map(([a, b]) => { const p = lv.findPath(a, b, 0.5); return p ? p.length : null; }),
  los: q.los.map(([a, b]) => lv.los(a, b)),
  moves: q.moves.map(([u, v, r, du, dv]) => { const t = {u, v, layer: 0, r}; for (let i = 0; i < 20; i++) lv.move(t, du, dv); return [t.u, t.v, t.layer]; })};
console.log(JSON.stringify(out));"""
        with tempfile.TemporaryDirectory() as d:
            qf = Path(d) / "q.json"
            qf.write_text(json.dumps(q))
            r = subprocess.run([node, "-e", js, str(build.HERE / "web" / "level.js"), str(ART / "level.json"), str(qf)],
                               capture_output=True, text=True, timeout=120)
        self.assertEqual(r.returncode, 0, r.stderr)
        out = json.loads(r.stdout)
        for (a, b), ln in zip(q["paths"], out["paths"]):
            p = lv.find_path(tuple(a), tuple(b), 0.5)
            self.assertAlmostEqual(p["length"], ln, places=6)
        self.assertEqual(out["los"], [lv.los(tuple(a), tuple(b)) for a, b in q["los"]])
        for (u, v, r_, du, dv), m in zip(q["moves"], out["moves"]):
            t = dict(u=u, v=v, layer=0, r=r_)
            for _ in range(20):
                lv.move(t, du, dv)
            self.assertAlmostEqual(t["u"], m[0], places=6); self.assertAlmostEqual(t["v"], m[1], places=6)
            self.assertEqual(t["layer"], m[2])


class Layers(unittest.TestCase):
    """the moving layers: they recompose the map at rest, the strips wrap, the sway is held frames of a few tiles"""
    @classmethod
    def setUpClass(cls):
        from PIL import Image
        cls.L = json.loads((ART / "layers.json").read_text())
        cls.img = {k: np.asarray(Image.open(ART / f"{k}.png").convert("RGBA"))
                   for k in ("sky", "far", "main", "corner", "sea", "cap", "map")}

    def test_composite_at_rest_is_the_map(self):
        H, W = self.img["map"].shape[:2]
        out = np.zeros((H, W, 3))
        for k in ("sky", "far", "main", "corner", "sea", "cap"):
            im, x, y = self.img[k].astype(float), self.L[k]["x"], self.L[k]["y"]
            y0, y1, x0, x1 = max(0, y), min(H, y + im.shape[0]), max(0, x), min(W, x + im.shape[1])
            sub = im[y0 - y:y1 - y, x0 - x:x1 - x]
            a = sub[..., 3:] / 255
            out[y0:y1, x0:x1] = out[y0:y1, x0:x1] * (1 - a) + sub[..., :3] * a
        same = np.all(np.abs(out - self.img["map"][..., :3]) < 1, -1).mean()
        self.assertGreater(same, 0.88)            # the clouds are repainted whole, the rest is the map's own pixels

    def test_strips_wrap(self):
        for k in ("far", "sea"):
            a = self.img[k][..., 3] > 0
            self.assertEqual(a.shape[1], self.L[k]["wrap"])
            self.assertGreater((a[:, 0] == a[:, -1]).mean(), 0.9, k)   # the seam's two sides agree
            self.assertGreater(self.L[k]["drift"], 0)

    def test_sway(self):
        sw = self.L["sway"]
        self.assertEqual(len(sw["frames"]), sw["n"])
        self.assertGreater(sw["trees"], 100)
        self.assertLess(max(len(f) for f in sw["frames"]), 80)         # draw calls per frame
        self.assertLess((ART / "sway.png").stat().st_size, 1_500_000)
        # the field's groves do not sway: no tile of any frame touches the playfield's middle rows
        T = sw["tile"]
        for fr in sw["frames"]:
            for t0, ty, n, ax, ay in fr:
                self.assertFalse(500 < ty * T < 760 and 300 < t0 * T < 1600, (t0, ty))


class Sizes(unittest.TestCase):
    def test_game_useful(self):
        self.assertGreaterEqual(2 * P.RAMP_HW, 5.0)            # a squad of four abreast
        self.assertGreaterEqual(2 * P.DECK["walk"], 2.4)       # two abreast on the bridge
        self.assertGreaterEqual(P.ZD - 0.5 + P.CORR_DIP, 1.5 * P.HUMAN)   # headroom under the deck
        self.assertLessEqual(math.degrees(math.atan(P.ZD / P.RAMP_LEN)), 26)
        spruces = [t["h"] for t in P.layout()["things"] if t["kind"] == "spruce"]
        self.assertGreater(min(spruces), 3 * P.HUMAN)
        self.assertFalse([t for t in P.layout()["things"] if t["kind"] in ("menhir", "altar")])   # the centre stays open


class Bundle(unittest.TestCase):
    def test_bundle_has_no_units(self):
        with tempfile.TemporaryDirectory() as d:
            p = build.bundle(Path(d) / "arena.html")
            html = p.read_text()
        self.assertIn("window.ARENA_DATA", html)
        self.assertNotIn("units_", html)
        self.assertNotIn("unit sprites", html)
        self.assertLess(len(html), 12_000_000)
        self.assertIn("ArenaLevel", html)
        self.assertFalse((ART / "units.json").exists())
        self.assertFalse((Path(build.HERE) / "blender" / "units.py").exists())


if __name__ == "__main__":
    unittest.main()

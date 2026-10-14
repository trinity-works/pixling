"""arena, many maps: the engine binds to one map at a time and every map keeps the shared style rules (arena/STYLE.md);
Emberleaf Hollow, the kill map, holds its zone budgets, keeps its units' hues free, and its level is complete and
sound (reachable, fair, spawns hidden, nothing stuck, colliders on the painted props)."""
import json
import math
import tempfile
import unittest
from pathlib import Path

import numpy as np

from arena import maps


class Binding(unittest.TestCase):
    def tearDown(self):
        maps.activate("hushfall")

    def test_switching_maps(self):
        from arena import build, check, level, paint, place as P, zones as Z
        maps.activate("emberleaf")
        self.assertEqual(P.NAME, "emberleaf_hollow")
        self.assertEqual(build.ART, maps.get("emberleaf").ART)
        self.assertIn("crown_coral", paint.MAT)
        self.assertEqual(Z.ZONES["frame"]["steps"], 4)
        self.assertFalse(level.has_deck())
        maps.activate("hushfall")
        self.assertEqual(P.NAME, "hushfall_crossing")
        self.assertEqual(check.ART, maps.get("hushfall").ART)
        self.assertIn("snowc_a", paint.MAT)
        self.assertEqual(Z.ZONES["frame"]["steps"], 3)
        self.assertTrue(level.has_deck())

    def test_dab_edges_opt_in(self):
        """the step-edge pass is opt-in: Hushfall does not take it (its art stays byte-identical)"""
        self.assertFalse(hasattr(maps.get("hushfall").biome, "DAB_EDGES"))
        self.assertTrue(maps.get("emberleaf").biome.DAB_EDGES)

    def test_shared_style(self):
        """the camera family, the unit scale, the light and the zone order are the same on every map"""
        from arena import place as P, zones as Z
        seen = {}
        for n in maps.names():
            maps.activate(n)
            self.assertIn(P.EL_DEG, (40.0, 68.0))                   # the members of the camera family
            self.assertGreaterEqual(P.PPM * 1.7 * P.CE, 31.0)       # a person stands about 32 px tall or more
            self.assertAlmostEqual(P.W / P.PPM, 60.0, delta=0.5)    # about 60 m of world across the picture
            self.assertAlmostEqual(P.W / P.H, 16 / 9, places=2)
            su, sv, _ = P.sun_vec()
            self.assertGreater(-su, 0); self.assertGreater(sv, 0)   # the sun from the upper left
            from arena import geo
            self.assertAlmostEqual(math.atan2(sv, su), math.atan2(geo.SUN_UV[1], geo.SUN_UV[0]), places=6)
            self.assertEqual([k for k in Z.ZONES], list(Z.BASE))
            B = maps.active().biome
            for name in ("playfield", "focus", "backdrop", "vista", "sky"):
                self.assertEqual(Z.ZONES[name]["soft"], Z.BASE[name]["soft"], (n, name))
                if name == "playfield" and getattr(B, "DAB_EDGES", None):
                    # a map that paints its step boundaries with dabs may absorb more stair-steps (STYLE.md)
                    self.assertEqual(Z.ZONES[name]["clean"][0], Z.BASE[name]["clean"][0])
                    self.assertLessEqual(Z.ZONES[name]["clean"][1], 0.45)
                else:
                    self.assertEqual(Z.ZONES[name]["clean"], Z.BASE[name]["clean"], (n, name))
            self.assertEqual(Z.ZONES["playfield"]["steps"], 2)
            self.assertIn(Z.ZONES["frame"]["steps"], (3, 4))
            from arena import palette as C
            self.assertGreaterEqual(len(C.UNIT_HUES), 2)            # at least two reserved bands: two teams
            for lo, hi in C.UNIT_HUES.values():
                self.assertGreaterEqual(hi - lo, 20)
            seen[n] = P.EL_DEG
        self.assertEqual(set(seen), set(maps.names()))


class Emberleaf(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.M = maps.activate("emberleaf")
        from arena import check
        cls.lv = check.load()
        cls.fields = {}
        cls.un, cls.fields = check.reach(cls.lv, 0.5, cls.fields)

    @classmethod
    def tearDownClass(cls):
        maps.activate("hushfall")

    def test_lint_holds(self):
        from arena import zones as Z
        self.assertEqual(Z.lint(self.M.ART, quiet=True), 0)

    def test_unit_hues_kept_free(self):
        from arena import palette as C, zones as Z
        from arena.palette import rgb
        for k, h in C.PAL.items():
            if k in ("ink", "ink2", "lamp", "lamp_core"):
                continue
            c = np.array(rgb(h), float)
            self.assertFalse(Z.unit_mask(c[None, None])[0, 0], f"{k} {h} sits in a unit hue band")

    def test_kill_map_data(self):
        L, lv = self.lv.L, self.lv
        self.assertEqual(L["version"], 4)
        self.assertEqual(L["zones"]["objectives"], [])
        self.assertEqual(L["zones"]["mode"]["kind"], "annihilation")
        self.assertGreaterEqual(len(L["zones"]["targets"]), 4)
        self.assertEqual(len(L["zones"]["spawns"]["west"]["points"]), len(L["zones"]["spawns"]["east"]["points"]))
        self.assertGreaterEqual(len(L["zones"]["spawns"]["west"]["points"]), 12)
        kinds = {s["kind"] for s in lv.shapes}
        self.assertTrue({"oak", "pine", "bush", "log", "stump", "waystone", "crates", "fire", "lip"} <= kinds)
        # no rocks on this map (the user's round 5): cover is wood and leaves
        self.assertFalse({"boulder", "crag", "ruinwall", "shorestone"} & kinds)
        self.assertGreaterEqual(len(L["zones"]["cover"]), 20)
        self.assertEqual(L["nav"]["deck"]["half_width"], -1.0)        # one layer: no deck
        self.assertEqual(sum(lv.clear[1] > 0), 0)
        walk = float((lv.clear[0] >= 0.3).sum()) * lv.cell ** 2
        self.assertGreater(walk, 700)
        pr = L["projection"]
        self.assertEqual(pr["el_deg"], 68.0)
        self.assertAlmostEqual(pr["human_px"], 1.7 * math.cos(math.radians(68)) * 51.2, places=1)

    def test_reachable_fair_hidden(self):
        from arena import check
        self.assertEqual(len(self.un["west"]) + len(self.un["east"]), 0)
        rows = check.fairness(self.lv, 0.5, self.fields)
        self.assertGreaterEqual(len(rows), 4)
        for r in rows:
            self.assertTrue(r["ok"], f"{r['target']}: {r['west']} vs {r['east']}")
        self.assertEqual(check.spawn_los(self.lv), [])

    def test_not_stuck(self):
        from arena import check
        n, bad = check.sweep(self.lv, 0.5)
        self.assertGreater(n, 10000)
        self.assertEqual(bad, [])
        wedged, lost = check.walkers(self.lv, 30, 120, fields=self.fields)
        self.assertEqual((wedged, lost), ([], []))

    def test_pond_is_soft(self):
        """the pond stops movement, never sight or shots"""
        lv = self.lv
        from arena import place as P
        cu, cv, hu, hv = P.POND
        self.assertEqual(lv.clear_at(cu, cv, 0), 0.0)
        a, b = (cu - hu - 1.5, cv + 0.5, 0), (cu + hu + 1.5, cv + 0.5, 0)
        if lv.clear[0][lv.cell_of(a[0], a[1])] > 0 and lv.clear[0][lv.cell_of(b[0], b[1])] > 0:
            self.assertTrue(lv.los(a, b, "shot"))

    def test_colliders_on_the_art(self):
        from arena import check
        res, _ = check.art_samples(self.lv)
        poor = [(x["kind"], round(x["u"], 1), round(x["v"], 1)) for x in res if x["share"] < 0.5]
        self.assertEqual(poor, [])

    def test_layers_and_bundle(self):
        from arena import build
        L = json.loads((self.M.ART / "layers.json").read_text())
        self.assertNotIn("sea", L)
        self.assertGreater(L["sway"]["trees"], 60)
        self.assertLess(max(len(f) for f in L["sway"]["frames"]), 80)
        self.assertIn("pond", L["ambience"])
        with tempfile.TemporaryDirectory() as d:
            p = build.bundle(Path(d) / "arena.html")
            html = p.read_text()
        self.assertIn("Emberleaf Hollow", html)
        self.assertIn('"particles":"leaves"', html)
        self.assertLess(len(html), 12_000_000)


if __name__ == "__main__":
    unittest.main()

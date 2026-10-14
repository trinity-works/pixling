"""fp: shapes face outward, every asset uses the style's ramps, the build packs a world the walk can stand on."""
import json
import re
import tempfile
import unittest
from pathlib import Path

import numpy as np

from fp import kit, place
from fp import mesh as M
from fp.build import build, load_style
from fp.bundle import bundle

ROOT = Path(__file__).resolve().parent.parent / "fp"


def outward(m):
    c = m.P.mean(0)
    return float((((m.P - c) * m.N).sum(1) > -1e-6).mean())


class Shapes(unittest.TestCase):
    def test_primitives_face_out(self):
        for name, m in [("box", M.box(1, 1, 1, "a")), ("cylinder", M.cylinder(0.5, 1, "a")),
                        ("cone", M.frustum(0.5, 0, 1, "a")), ("sphere", M.sphere(0.5, "a")),
                        ("prism", M.prism([(0, 0), (1, 0), (1, 1), (0, 1)], 0.3, "a")),
                        ("prism_cw", M.prism([(0, 0), (0, 1), (1, 1), (1, 0)], 0.3, "a"))]:
            self.assertGreater(outward(m), 0.9, name)

    def test_spline_is_even(self):
        p = M.spline([(0, 0, 0), (1, 0, -3), (0, 0, -6)], 50)
        d = np.linalg.norm(np.diff(p, axis=0), axis=1)
        self.assertLess(d.std() / d.mean(), 0.05)


class Style(unittest.TestCase):
    def test_ramps(self):
        for f in (ROOT / "styles").glob("*.json"):
            st = json.loads(f.read_text())
            for name, stops in st["ramps"].items():
                pos = [p for p, _ in stops]
                self.assertEqual(pos, sorted(pos), f"{f.stem}.{name}: stops out of order")
                for _, h in stops:
                    self.assertRegex(h, r"^#[0-9a-f]{6}$", f"{f.stem}.{name}")

    def test_assets_use_known_materials(self):
        ramps = set(load_style("hushfall")["ramps"])
        for name in kit.registry():
            for seed in (0, 1):
                a = kit.build(name, seed)
                used = {str(x) for x in a.mesh.M} | {m for m, _ in (a.lines.polys if a.lines else [])}
                self.assertTrue(used <= ramps, f"{name}: {sorted(used - ramps)} not in the style's ramps")
                if a.mesh.tris:
                    self.assertGreaterEqual(float(a.mesh.P[:, 1].min()), -0.6, f"{name}: sinks below its origin")


class World(unittest.TestCase):
    @classmethod
    def setUpClass(cls):                      # one build for the tests of the built folder
        cls.tmp = tempfile.TemporaryDirectory()
        cls.out = build("first_snow", "hushfall", Path(cls.tmp.name), quiet=True)

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def test_build_and_route(self):
        out = self.out
        w = json.loads((out / "world.json").read_text())
        self.assertTrue((out / "index.html").exists() and (out / "fp.js").exists())
        self.assertGreater(len(w["route"]), 20)
        self.assertGreater(len(w["steps"]), 10)
        size = (out / "world.bin").stat().st_size
        for k, m in w["meshes"].items():
            self.assertLessEqual(m["idx"][0] + m["idx"][1] * 4, size, k)
        # the walk starts on the ground and ends near the car
        car = [i for i in w["instances"] if i["mesh"].startswith("car:")][0]["at"][0]
        end = w["route"][-1]
        self.assertLess(np.hypot(end[0] - car[0], end[1] - car[2]), 6.0)
        # the painted view is a static folder holding every file its page loads
        lay = out / "layers"
        sc = json.loads((lay / "scene.json").read_text())
        need = ["index.html", "layers.js", "audio.js", "walker.json", "walker.png", "walk.bin",
                "fonts/GeistPixel-Square.woff2"]
        for l in sc["layers"]:
            need += [l["src"], "hd_" + l["src"], "hd3_" + l["src"]] + ([l["depth"]] if "depth" in l else [])
        for f in need:
            self.assertTrue((lay / f).exists(), f)

    def test_bundle(self):
        # the painted view as one html that opens from disk: every file the page loads is in its table (or inlined:
        # the modules through the import map, the font in the CSS), no relative asset URL is left, and its size is sane
        lay = self.out / "layers"
        html = self.out / "first_snow.html"
        info = bundle(lay, html)
        self.assertTrue(html.exists())
        page = html.read_text()
        self.assertLess(info["bytes"], 16e6)               # an artifact's limit; the art is ~3.5 MB
        self.assertGreater(info["bytes"], 1e6)
        sc = json.loads((lay / "scene.json").read_text())
        ws = json.loads((lay / "walker.json").read_text())
        loads = ["scene.json", "walker.json", ws["src"], sc["walk"]["src"]]
        for l in sc["layers"]:
            loads += [l["src"], "hd_" + l["src"], "hd3_" + l["src"]] + ([l["depth"]] if "depth" in l else [])
        table = json.loads(re.search(r"window.__FP_FILES = (\{.*?\});</script>", page).group(1))
        for f in loads:
            self.assertIn(f, table)
            self.assertTrue(table[f].startswith("data:"), f)
        imap = json.loads(re.search(r'<script type="importmap">(.*?)</script>', page, re.S).group(1))
        self.assertIn("fp-audio", imap["imports"])
        self.assertTrue(all(u.startswith("data:text/javascript;base64,") for u in imap["imports"].values()))
        self.assertNotRegex(page, r'<script[^>]* src=')        # every script inline
        for u in re.findall(r"""url\(\s*["']?([^"')]+)""", page):
            self.assertTrue(u.startswith("data:"), u)       # the font
        self.assertNotRegex(page, r'<(img|link)[^>]*(src|href)="(?!data:|https?:)')
        self.assertNotIn("./audio.js", page)


class Painted(unittest.TestCase):
    def test_place(self):
        a, b = place.layout(), place.layout()
        self.assertEqual(a["posts"], b["posts"])
        self.assertEqual(a["trees"], b["trees"])
        self.assertGreater(len(a["slabs"]), 15)          # the S, short of the road it ends at
        route = place.walk_route(a["curve"])
        self.assertLess(np.hypot(route[-1]["x"] - place.END[0], route[-1]["z"] - place.END[1]), 0.01)
        self.assertTrue(all(q["s"] > p["s"] for p, q in zip(route, route[1:])))

    def test_walkable_area(self):
        # she starts on the stair and can stand at the hold; the area stays inside the frame and short of the trees
        lay = place.layout()
        g = place.walk_grid(lay)
        cell = lambda x, z: (int(round((z - g["z0"]) / g["d"])), int(round((x - g["x0"]) / g["d"])))
        route = place.walk_route(lay["curve"])
        self.assertGreater(g["room"][cell(route[0]["x"], route[0]["z"])], 0.5)
        self.assertGreater(g["room"][cell(*place.END)], 0.5)
        self.assertEqual(g["surface"][cell(route[0]["x"], route[0]["z"])], place.ON_STONE)
        X, Z = np.meshgrid(g["x0"] + np.arange(g["nx"]) * g["d"], g["z0"] + np.arange(g["nz"]) * g["d"])
        inside = g["room"] > 0
        self.assertFalse((Z[inside] > place.TREE_LINE).any())
        sx, sy = place.proj(X[inside], g["height"][inside], Z[inside])
        self.assertTrue((sx >= place.EDGE_PX).all() and (sx <= place.W - place.EDGE_PX).all())
        self.assertTrue((sy <= place.NEAR_ROW).all())
        # and it reaches out into the wider world on both sides
        self.assertLess(X[inside].min(), -30)
        self.assertGreater(X[inside].max(), 30)

    def test_blockers(self):
        # every post, near spruce and pole is walked round; the ropes hold along the stair; the car is a box
        lay = place.layout()
        b = place.walk_blocks(lay)
        n_near = sum(1 for t in lay["trees"] if t[3] == "tn")
        self.assertGreaterEqual(len(b["circles"]), len(lay["posts"]) + n_near + len(place.POLES))
        self.assertGreater(len(b["segs"]), 10)
        cx, cz, yaw, hl, hw = b["boxes"][0]
        self.assertLess(np.hypot(cx - place.CAR_AT[0], cz - place.CAR_AT[1]), hl + hw)

    def test_road(self):
        # the car stands on the lane's near half with its near tyres in the near rut, she holds by its nose on the
        # road, the stair's last stone sits at the shoulder, and the road is walkable at full pace far out both ways
        lay = place.layout()
        w = lambda x, z: float(place.road_w(x, z))
        self.assertLess(abs(w(*place.CAR_AT) - (place.TRACK_W - place.RUT_OFF)), place.RUT_HW)
        c = place.car3d()
        a = np.radians(c["yaw"])
        for u in (0, c["L"]):
            for v in (-c["W"] / 2, c["W"] / 2):
                x, z = c["x"] + u * np.cos(a) + v * np.sin(a), c["z"] + u * np.sin(a) - v * np.cos(a)
                self.assertLess(abs(w(x, z)), place.ROAD_HW)
        self.assertLess(np.hypot(c["L"] / place.CS, c["W"] / place.CS), 6.0)     # an estate, not a bus
        nose = (c["x"] + c["L"] * np.cos(a), c["z"] + c["L"] * np.sin(a))
        self.assertLess(np.hypot(place.END[0] - nose[0], place.END[1] - nose[1]), 2.0)
        self.assertLess(abs(w(*place.END)), place.ROAD_HW)
        last = max(lay["slabs"], key=lambda sb: sb["cz"])
        self.assertTrue(-place.ROAD_EDGE - 1.0 < w(last["cx"], last["cz"]) < -place.ROAD_HW)
        g = place.walk_grid(lay)
        X, Z = np.meshgrid(g["x0"] + np.arange(g["nx"]) * g["d"], g["z0"] + np.arange(g["nz"]) * g["d"])
        road = (g["surface"] == place.ON_ROAD) & (g["room"] >= 1)
        self.assertLess(X[road].min(), -30)
        self.assertGreater(X[road].max(), 20)
        self.assertEqual(place.PACE[place.ON_ROAD], place.PACE[place.ON_STONE])
        self.assertLess(place.PACE[place.ON_SNOW], place.PACE[place.ON_BANK])
        self.assertLess(place.PACE[place.ON_BANK], place.PACE[place.ON_ROAD])

    def test_foot_gaps(self):
        # by the foot of the stair a rope on each side sags into the snow, so she can step off from the start
        lay = place.layout()
        sx, sz = (lambda r: (r["x"], r["z"]))(place.walk_route(lay["curve"])[0])
        gaps = []
        for runs, _ in lay["ropes"]:
            for r0, r1 in zip(runs, runs[1:]):
                gx, gz = (r0[-1][0] + r1[0][0]) / 2, (r0[-1][2] + r1[0][2]) / 2
                if np.hypot(gx - sx, gz - sz) < 3.0 and np.hypot(r1[0][0] - r0[-1][0], r1[0][2] - r0[-1][2]) > 0.8:
                    gaps.append(np.sign(gx - float(place.path_x(gz))))
        self.assertEqual(set(gaps), {-1.0, 1.0})

    def test_art_matches_place(self):
        # the committed layers were painted from this place (after changing place.py, run `fp paint`)
        sc = json.loads((ROOT / "art" / "first_snow" / "scene.json").read_text())
        lay = place.layout()
        self.assertEqual(sc["route"], place.walk_route(lay["curve"]))
        self.assertEqual(sc["camera"]["f"], place.F)
        self.assertEqual(sc["camera"]["lens"], [place.LENS_ZS, place.LENS_ZB, place.LENS_A, place.LENS_B])
        g = place.walk_grid(lay)
        self.assertEqual((sc["walk"]["nx"], sc["walk"]["nz"]), (g["nx"], g["nz"]))
        size = (ROOT / "art" / "first_snow" / "walk.bin").stat().st_size
        self.assertEqual(size, 5 * sc["walk"]["nx"] * sc["walk"]["nz"])


if __name__ == "__main__":
    unittest.main()

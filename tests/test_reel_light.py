"""reel.light on a synthetic side-view walker: loop found by pose, drift measured, edge despill, stable maps, and a
small end-to-end build + check."""
import json
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

import numpy as np
from PIL import Image

from reel import light

try:
    import skimage  # noqa: F401  (pixling[reel]: the build's optical flow)
    HAVE_SKIMAGE = True
except ImportError:
    HAVE_SKIMAGE = False

PERIOD = 10


def walker(t, size=160, travel=1.5, grow=1.004):
    """magenta frame with a body and two legs swinging with PERIOD; moves right and grows (walks toward the camera)"""
    a = np.zeros((size, size, 3), np.uint8); a[:] = (255, 0, 255)
    s = grow ** t; cx = 50 + travel * t; ground = 140
    h = int(70 * s); w = int(24 * s)
    a[ground - h:ground - int(30 * s), int(cx - w / 2):int(cx + w / 2)] = (90, 110, 60)
    sw = np.sin(2 * np.pi * t / PERIOD) * 12 * s
    for sgn, half in ((1, 3), (-1, 7)):        # unequal legs: half a stride is not the same pose
        x = int(cx + sgn * sw)
        a[ground - int(30 * s):ground, x - half:x + half] = (70, 80, 50)
    return a


def normal_map(a):
    """green-up normal map: a dome over the body"""
    m = np.abs(a.astype(int) - (255, 0, 255)).sum(2) > 60
    ys, xs = np.nonzero(m); cx, cy = xs.mean(), ys.mean()
    yy, xx = np.mgrid[0:a.shape[0], 0:a.shape[1]]
    n = np.dstack([(xx - cx) / 80, -(yy - cy) / 80, np.ones(a.shape[:2])])
    n /= np.linalg.norm(n, axis=2, keepdims=True)
    return ((n * .5 + .5) * 255).astype(np.uint8)


def treadmill(t, size=160, amp=12, period=PERIOD, bob=0):
    """a body walking in place: the planted leg slides back at 4*amp/period px per frame, the other swings forward
    lifted; bob lifts the whole figure (feet too), as H3 walks in place do"""
    a = np.zeros((size, size, 3), np.uint8); a[:] = (255, 0, 255)
    cx, ground = 70, 140 - int(round(bob * (1 - np.cos(4 * np.pi * t / period)) / 2))
    a[ground - 70:ground - 30, cx - 12:cx + 12] = (90, 110, 60)
    for k, half in ((0, 3), (1, 6)):
        ph = ((t / period) + k * 0.5) % 1.0
        if ph < 0.5:
            x, lift = cx + amp - 2 * amp * ph / 0.5, 0
        else:
            x, lift = cx - amp + 2 * amp * (ph - 0.5) / 0.5, 8
        x = int(round(x)); a[ground - 30:ground - lift, x - half:x + half] = (70, 80, 50)
    return a


class LightTest(unittest.TestCase):
    def test_foot_speed_treadmill_and_ground(self):
        A = [(np.abs(treadmill(t, bob=6).astype(int) - (255, 0, 255)).sum(2) > 60).astype(float) for t in range(PERIOD + 1)]
        cfg = light.clip_cfg("w", {"dir": "w", "match": 0, "speed": "foot", "ground": "lowest", "ground_sigma": 0})
        cl = dict(A=A[1:], match=A[0], cfg=cfg)
        P, speed = light.placement(cl, 1.0)
        self.assertAlmostEqual(speed, 4 * 12 / PERIOD, delta=0.6)            # belt speed, not the (zero) travel
        feet = [light.box(a)[3] - p[2] for a, p in zip(cl["A"], P)]
        self.assertEqual(max(map(abs, feet)), 0)                              # every frame's lowest foot on the ground


    def test_find_loop_matches_one_period(self):
        A = [(np.abs(walker(t).astype(int) - (255, 0, 255)).sum(2) > 60).astype(float) for t in range(26)]
        best, s, e = light.find_loop(A, min_len=6)[0]
        self.assertEqual((e - s) % PERIOD, 0)
        self.assertGreater(best, .9)

    def test_drift_recovers_travel_and_growth(self):
        A = [(np.abs(walker(t).astype(int) - (255, 0, 255)).sum(2) > 60).astype(float) for t in (0, 20)]
        grow, dg, dx = light.drift(A[0], A[1], 20)
        self.assertAlmostEqual(dx, 1.5, delta=0.15)
        self.assertAlmostEqual(grow, 1.004, delta=0.002)
        self.assertLess(abs(dg), 0.2)

    def test_despill_edge_only(self):
        c = np.full((40, 40, 3), .4); a = np.zeros((40, 40)); a[5:35, 5:35] = 1
        c[5:7, 5:35] = (.8, .3, .8)            # magenta spill on the top edge
        c[20, 20] = (.6, .2, .6)               # a purple pixel deep inside stays
        out = light.despill(c, a, band=3)
        self.assertLess(out[5, 20, 0] - out[5, 20, 1], 0.01)
        self.assertTrue(np.allclose(out[20, 20], c[20, 20]))

    def test_close_loop_levels_lean(self):
        A = [np.ones((20, 20))] * 6; C = [np.full((20, 20, 3), .5)] * 6
        N = [light.unit(np.dstack([np.full((20, 20), .3 * (-1) ** i), np.zeros((20, 20)), np.ones((20, 20))])) for i in range(6)]
        C2, N2 = light.close_loop(C, N, A, sigma=2.0, lean=np.array([0, 0, 1.0]))
        xs = [n[..., 0].mean() for n in N2]
        self.assertLess(np.ptp(xs), 0.1)
        self.assertTrue(all(np.allclose(np.linalg.norm(n, axis=2), 1, atol=1e-3) for n in N2))


@unittest.skipUnless(HAVE_SKIMAGE, "needs scikit-image (pip install pixling[reel])")
class BuildTest(unittest.TestCase):
    """one synthetic character with three clips under made-up names: a travelling loop (lead), a breathing loop (rest)
    and a one-shot hop, built once"""
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory(); d = cls.d = Path(cls.tmp.name)
        for c in ("stride", "breathe", "hop"):
            (d / c).mkdir()
        for t in range(0, 2 * PERIOD + 1):
            f = walker(t); Image.fromarray(f).save(d / "stride" / f"f{t:03d}.png")
            Image.fromarray(normal_map(f)).save(d / "stride" / f"f{t:03d}_p_1.png")
        for t in range(0, 24, 2):              # standing body that breathes; normals on two keys only
            f = walker(0, travel=0); f[60 - (t % 8) // 2:62] = f[62]
            Image.fromarray(f).save(d / "breathe" / f"f{t:03d}.png")
            if t in (0, 12):
                Image.fromarray(normal_map(f)).save(d / "breathe" / f"f{t:03d}_p_1.png")
        for t in range(0, 16, 2):              # a hop: up and down once
            f = np.zeros_like(walker(0)); f[:] = (255, 0, 255); lift = int(20 * np.sin(np.pi * t / 14))
            f[:160 - lift] = walker(0, travel=0)[lift:]
            Image.fromarray(f).save(d / "hop" / f"f{t:03d}.png")
            if t in (0, 14):
                Image.fromarray(normal_map(f)).save(d / "hop" / f"f{t:03d}_p_1.png")
        cls.spec = {"name": "w", "height": 100, "clips": {
            "stride": {"dir": "stride", "loop": [PERIOD + 1, 2 * PERIOD], "match": PERIOD},
            "breathe": {"dir": "breathe", "reverse": True},
            "hop": {"dir": "hop", "loop": False}}}
        (d / "light.json").write_text(json.dumps(cls.spec))
        cls.logs = []
        cls.out = light.build(d / "light.json", log=cls.logs.append)
        cls.M = json.loads(cls.out.read_text())

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def test_format(self):
        M = self.M
        self.assertEqual((M["format"], M["version"], M["normal_y"]), ("pixling.lit-sprite", 1, "up"))
        self.assertEqual((M["lead"], M["rest"], M["faces"]), ("stride", "breathe", 1))
        self.assertEqual([M["anims"][k]["count"] for k in ("stride", "breathe", "hop")], [PERIOD, 12, 8])
        self.assertFalse(M["anims"]["hop"]["loop"]); self.assertNotIn("speed", M["anims"]["hop"])
        self.assertAlmostEqual(M["anims"]["stride"]["speed"], 1.5 * 100 / 70, delta=0.4)
        self.assertEqual(len(M["stops"]), PERIOD); self.assertEqual(len(M["starts"]), 12)
        self.assertEqual(len(M["frames"]), PERIOD + 12 + 8)

    def test_normals_green_up(self):
        f = self.M["frames"][0]
        n = np.asarray(Image.open(self.out.with_name(self.M["images"]["normal"])).convert("RGB")).astype(float)[f["v"]:f["v"] + f["h"], f["u"]:f["u"] + f["w"]]
        a = np.asarray(Image.open(self.out.with_name(self.M["images"]["color"])))[f["v"]:f["v"] + f["h"], f["u"]:f["u"] + f["w"], 3] > 200
        ys = np.nonzero(a)[0]; top = a & (np.arange(a.shape[0])[:, None] < ys.min() + 6)
        self.assertGreater(n[..., 1][top].mean(), 140)        # top of the dome faces up = green above 128

    def test_cache_and_check(self):
        logs = []
        light.build(self.d / "light.json", log=logs.append)
        self.assertTrue(all("(cached)" in l for l in logs if "mapped" in l))
        self.assertIsInstance(light.check(self.out, log=lambda *_: None), list)

    def test_export_demo(self):
        g = light.export(self.out, self.d / "godot", "godot")
        self.assertTrue((g.parent / "lit_sprite.gd").exists() and (g.parent / "w_color.png").exists())
        self.assertEqual(json.loads(g.read_text())["images"]["normal"], "w_normal.png")
        page = light.demo(self.out, self.d / "demo")
        self.assertIn("w.json", page.read_text()); self.assertTrue((page.parent / "litsprite.js").exists())

    def test_patina_plan(self):
        plan = dict((p.name, ks) for p, ks in light.patina_plan(self.d / "light.json"))
        self.assertEqual(plan["stride"], [])                   # every frame mapped
        self.assertEqual(plan["breathe"], [20])                # keys every 20 filmed frames (0 and 12 already mapped)
        self.assertEqual(plan["hop"], [])

    def test_new(self):
        root = self.d / "lit"; shutil.copytree(Path(light.__file__).parent / "lit" / "_template", root / "_template")
        spec = json.loads(light.new("moth", root).read_text())
        self.assertEqual(spec["name"], "moth"); self.assertIn("moth", spec["out"])
        self.assertTrue((root / "moth" / "walk").is_dir())

    def test_idle_only(self):
        """nothing travels: the idle is lead and rest, no stop poses, and the players loop it"""
        spec = {"name": "solo", "height": 100, "out": "solo", "clips": {"breathe": {"dir": "breathe"}}}
        (self.d / "solo.json").write_text(json.dumps(spec))
        M = json.loads(light.build(self.d / "solo.json", log=lambda *_: None).read_text())
        self.assertEqual((M["lead"], M["rest"]), ("breathe", "breathe"))
        self.assertNotIn("stops", M)
        self.assertEqual(light.check(self.d / "solo" / "solo.json", log=lambda *_: None), [])

    def test_start_frame(self):
        im = self.d / "design.png"; Image.fromarray(walker(0, travel=0)).save(im)
        a = np.asarray(Image.open(light.start_frame(im, self.d / "start.png"))).astype(int)
        m = np.abs(a - (255, 0, 255)).sum(2) > 60; ys, xs = np.nonzero(m)
        self.assertEqual(a.shape[:2], (1080, 1920))
        self.assertLess(xs.max(), 1920 * .4); self.assertAlmostEqual(ys.max(), 1080 * .92, delta=4)
        self.assertAlmostEqual(ys.max() - ys.min(), 1080 * .44, delta=8)

    @unittest.skipUnless(shutil.which("node"), "node not installed")
    def test_js_player(self):
        """litsprite.js on this sheet: walk right, release -> settles into the rest clip; a one-shot returns to rest"""
        js = Path(light.__file__).parent / "light_runtime" / "litsprite.js"
        prog = f"""
const L = require({json.dumps(str(js))}); const M = require({json.dumps(str(self.out))});
const a = new L.Actor({{meta: M}}, {{x: 100}}); const dt = 1 / 60, log = [];
for (let i = 0; i < 60; i++) a.update(dt, {{move: 1}});
log.push(a.mode, a.x > 100);
for (let i = 0; i < 90; i++) a.update(dt, {{move: 0}});
log.push(a.mode);
a.play("hop"); a.update(dt, {{}}); log.push(a.mode, a.draws()[0].frame >= M.anims.hop.start);
for (let i = 0; i < 120; i++) a.update(dt, {{}});
log.push(a.mode);
for (let i = 0; i < 30; i++) a.update(dt, {{move: -1}});
log.push(a.draws()[0].mirror);
console.log(JSON.stringify(log));"""
        r = subprocess.run(["node", "-e", prog], capture_output=True, text=True)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(json.loads(r.stdout), ["lead", True, "rest", "shot", True, "rest", True])


if __name__ == "__main__":
    unittest.main()

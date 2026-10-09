"""Map composer (pp.map): terrain, roof primitive, layers export. Run: python3 -m unittest tests.test_map"""
import json
import sys
import tempfile
import unittest
from pathlib import Path

import numpy as np
from PIL import Image

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from pp.forge import Forge  # noqa: E402
from pp.map import compose, export_layers  # noqa: E402
from pp.sdf import sd_roof  # noqa: E402

HUT = {"name": "hut", "style": "vista", "rig": "prop", "directions": ["S"], "frame": [24, 24], "anchor": [12, 20],
       "clips": ["idle"], "custom_clips": {"idle": {"loop": True, "frames": [{"pose": {}, "hold": 2}, {"pose": {}, "root": [0, 0, 1], "hold": 2}]}},
       "bones": [{"name": "root"},
                 {"name": "walls", "parent": "root", "parts": [{"shape": "box", "at": [0, 0, 3], "half": [4, 3, 3], "mat": "plaster"}]},
                 {"name": "roof", "parent": "root", "seam": True, "parts": [{"shape": "roof", "at": [0, 0, 6], "half": [4.6, 3.6], "h": 3, "mat": "roof"}]}]}


def _map(builds):
    return {"name": "t", "style": "vista", "size": [80, 60], "frames": 4, "ms": 100, "seed": 3,
            "terrain": [{"kind": "fill", "ramp": "grass", "tones": {"base": 1}},
                        {"kind": "sea", "rect": [0, 40, 80, 20], "rough": 0, "levels": []},
                        {"kind": "path", "path": [[10, 10], [70, 30]], "width": 4, "rough": 0},
                        {"kind": "bridge", "path": [[40, 36], [40, 44]], "width": 5, "rough": 0}],
            "objects": [{"build": "hut", "at": [30, 30], "place": "hut", "icon": "house"},
                        {"build": "hut", "at": [60, 30], "over": True}],
            "walkers": [{"build": "hut", "path": [[-10, 50], [90, 50]], "loop": False, "speed_px_s": 5}],
            "fx": [{"kind": "flow", "path": [[0, 50], [80, 50]], "width": 6}],
            "fog": {"ramp": "mist", "regions": [{"id": "a", "rect": [0, 0, 40, 60]}, {"id": "b", "rect": [40, 0, 40, 60]}]},
            "atlas": {"scale": 0.75}}


class MapTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        cls.builds = Path(cls.tmp.name) / "builds"
        Forge(json.loads(json.dumps(HUT))).build(cls.builds / "hut")

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def test_roof_is_hip_and_gable(self):
        p = np.array([[0.0, 0.0, 1.0], [0.0, 0.0, 3.5], [3.9, 0.0, 1.0], [0.0, 3.9, 0.1]])
        hip = sd_roof(p, [4, 2], 3)
        self.assertLess(hip[0], 0)             # inside, under the ridge
        self.assertGreater(hip[1], 0)          # above the ridge
        self.assertGreater(hip[2], 0)          # hipped end slopes in along the ridge
        gable = sd_roof(p, [4, 2], 3, gable=True)
        self.assertLess(gable[2], 0)           # a gable end stays vertical

    def test_compose_loops_and_uses_the_palette(self):
        frames = compose(_map(self.builds), self.builds)
        self.assertEqual(len(frames), 4)
        from pp.forge import load_style
        from pp.map import Pal
        pal = Pal(load_style("vista"))
        allowed = {c for r in pal.ramps.values() for c in r} | set(pal.down.values())
        used = {tuple(int(v) for v in c) for c in np.unique(frames[0][..., :3].reshape(-1, 3), axis=0)}
        self.assertTrue(used <= allowed, used - allowed)

    def test_layers_export(self):
        out = Path(self.tmp.name) / "out"
        meta = export_layers(_map(self.builds), self.builds, out)
        L = out / "layers"
        # the delta GIF decodes to exactly the composed frames
        frames = compose(_map(self.builds), self.builds, live=True)
        gif = Image.open(L / meta["base"])
        for k in range(len(frames)):
            gif.seek(k)
            self.assertTrue((np.array(gif.convert("RGB")) == frames[k][..., :3]).all(), k)
        # places carry bounds, an outline ring and an atlas point
        hut = meta["places"]["hut"]
        x0, y0, x1, y1 = hut["box"]
        self.assertTrue(x0 < 30 < x1 and y0 < 30 <= y1)
        self.assertTrue((L / hut["outline"]["image"]).exists() and hut["atlas"])
        # movers keep their path and speed; the occluder layer has the "over" hut only
        self.assertEqual(meta["movers"][0]["speed"], 5)
        over = np.array(Image.open(L / meta["over"]))
        self.assertTrue(over[..., 3][:, 50:].any() and not over[..., 3][:, :45].any())
        # fog: each region has its own shape and they overlap at the shared border
        mask = np.array(Image.open(L / meta["fog"]["ids"]))[..., 0]
        self.assertTrue(((mask & 1) > 0).any() and ((mask & 2) > 0).any() and ((mask & 3) == 3).any())
        self.assertEqual(len(meta["atlas"]["layers"]), 6)


if __name__ == "__main__":
    unittest.main()

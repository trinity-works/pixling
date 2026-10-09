"""Hour lighting: day is the painting itself, night darkens, light sources pool and reflect.
Run: python3 -m unittest tests.test_light"""
import sys
import unittest
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from pp.forge import load_style  # noqa: E402
from pp.light import Lighting, grade  # noqa: E402
from pp.map import compose  # noqa: E402
from pp.meaning import Meaning  # noqa: E402

SPEC = {"name": "t_light", "style": "vista", "size": [80, 60], "seed": 5, "frames": 1, "objects": [], "walkers": [], "fx": [],
        "terrain": [{"kind": "land"}, {"kind": "water", "rect": [0, 40, 80, 20], "rough": 0}],
        "light": {"points": [{"at": [40, 30], "r": [3, 8], "reflect": 20}]}}


class Light(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.mean = Meaning(80, 60, SPEC)
        cls.img = compose(SPEC, ROOT / "out", 1, meaning=cls.mean)[0]
        _, cls.wd = cls.mean.arrays()
        cls.L = Lighting(SPEC, cls.mean, load_style("vista"), lambda n: None)

    def test_day_is_the_painting(self):
        self.assertTrue(np.array_equal(self.L.render(self.img, self.wd, 0.0), self.img))

    def test_night_is_darker(self):
        night = self.L.render(self.img, self.wd, 4.0)[..., :3].astype(int)
        self.assertLess(night[5:20].mean(), self.img[5:20, :, :3].astype(int).mean() * 0.75)

    def test_source_glows_pools_and_reflects(self):
        night = self.L.render(self.img, self.wd, 4.0)[..., :3]
        self.assertEqual(tuple(night[30, 40]), (0xf5, 0xd8, 0x90))
        warm = night[31, 43].astype(int)                 # in the pool: warmer than the same grass far away
        cold = night[31, 75].astype(int)
        self.assertGreater(warm[0] - warm[2], cold[0] - cold[2])
        streak = night[41:60, 38:43]
        self.assertTrue((np.abs(streak.astype(int) - [0xf5, 0xd8, 0x90]).sum(-1) < 40).any() or
                        (np.abs(streak.astype(int) - [0xe0, 0xa0, 0x50]).sum(-1) < 40).any())

    def test_grades_are_flat_colour_tables(self):
        c = np.array([[127.0, 138.0, 90.0]])
        for k in range(8):
            g = grade(c, k)
            self.assertEqual(g.shape, (1, 3))
            self.assertTrue((g >= 0).all() and (g <= 255).all())


if __name__ == "__main__":
    unittest.main()

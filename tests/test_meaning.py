"""The meaning layer: painters write what each pixel is; painting itself is unchanged.
Run: python3 -m unittest tests.test_meaning"""
import sys
import unittest
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from pp.map import compose  # noqa: E402
from pp.meaning import Meaning  # noqa: E402

SPEC = {"name": "t_meaning", "style": "vista", "size": [80, 50], "seed": 3, "frames": 1, "objects": [], "walkers": [], "fx": [],
        "terrain": [
            {"kind": "land"},
            {"kind": "water", "ellipse": [60, 25, 16, 14], "rough": 0},
            {"kind": "path", "path": [[0, 10], [40, 10]], "width": 4, "rough": 0},
            {"kind": "fill", "rect": [4, 30, 20, 12], "material": "field", "walk": 2, "rough": 0},
            {"kind": "canopy", "poly": [[30, 30], [44, 30], [44, 46], [30, 46]], "rough": 0},
            {"kind": "canopy", "ellipse": [12, 18, 6, 4], "stands": 26, "block": [11, 24, 3, 2], "rough": 0}]}


def build():
    mean = Meaning(80, 50, SPEC)
    frames = compose(SPEC, ROOT / "out", 1, meaning=mean)
    return mean, frames[0]


class MeaningLayer(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.mean, cls.img = build()
        cls.walk, cls.wd = cls.mean.arrays()
        cls.names = [m["name"] for m in cls.mean.materials]

    def mat(self, x, y):
        return self.names[self.mean.mat[y, x]]

    def test_painting_is_unchanged_by_recording(self):
        self.assertTrue(np.array_equal(compose(SPEC, ROOT / "out", 1)[0], self.img))

    def test_materials(self):
        self.assertEqual(self.mat(70, 45), "grass")
        self.assertEqual(self.mat(60, 25), "water")
        self.assertEqual(self.mat(20, 10), "path")
        self.assertEqual(self.mat(10, 35), "field")
        self.assertEqual(self.mat(37, 38), "foliage")

    def test_collision(self):
        self.assertEqual(self.walk[45, 70], 1)            # grass
        self.assertEqual(self.walk[35, 10], 2)            # field marked slow
        self.assertEqual(self.walk[25, 60], 0)            # deep water
        self.assertEqual(self.walk[38, 37], 0)            # a forest mass blocks, gaps included
        self.assertEqual(self.walk[25, 12], 0)            # the trunk
        self.assertEqual(self.walk[18, 12], 1)            # under a standing crown: the ground's own walk

    def test_water_depth_and_wading(self):
        self.assertGreater(self.wd[25, 60], 8)
        edge = (self.wd > 0) & (self.wd <= 3)
        self.assertTrue(edge.any() and np.all(self.walk[edge] == 2))

    def test_standing_crown_occludes(self):
        self.assertEqual(int(self.mean.depth[18, 12]), 26)
        self.assertEqual(int(self.mean.depth[45, 70]), 0)


if __name__ == "__main__":
    unittest.main()

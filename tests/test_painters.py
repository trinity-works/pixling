"""Opt-in painters: grass blades by density and the bank-to-middle water gradient.
Run: python3 -m unittest tests.test_painters"""
import sys
import unittest
from pathlib import Path

import numpy as np
from scipy.ndimage import distance_transform_edt

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from pp.map import compose  # noqa: E402


def spec(land=None, water=None):
    return {"name": "t_paint", "style": "vista", "size": [120, 80], "seed": 2, "frames": 1, "objects": [], "walkers": [], "fx": [],
            "terrain": [dict({"kind": "land", "tufts": 0, "flowers": 0, "tones": {"dark": 1, "light": 1}}, **(land or {})),
                        dict({"kind": "water", "rect": [60, 0, 60, 80], "rough": 0}, **(water or {}))]}


def colours(img, box):
    x0, y0, x1, y1 = box
    return {tuple(c) for c in img[y0:y1, x0:x1, :3].reshape(-1, 3)}


class Painters(unittest.TestCase):
    def test_blades_add_small_marks_on_flat_ground_only(self):
        flat = compose(spec(), ROOT / "out", 1)[0]
        blades = compose(spec({"blades": {"density": [0.02, 0.06]}}), ROOT / "out", 1)[0]
        self.assertEqual(len(colours(flat, (0, 0, 55, 80))), 1)
        diff = np.any(flat != blades, axis=-1)
        self.assertGreater(diff[:, :58].mean(), 0.01)
        self.assertFalse(diff[:, 62:].any())                     # nothing lands in the water painted later
        self.assertLess(diff.mean(), 0.15)

    def test_bank_water_lightens_toward_the_bank(self):
        img = compose(spec(water={"bank": {}}), ROOT / "out", 1)[0].astype(int)
        lum = img[..., :3].sum(-1)
        self.assertGreater(lum[40, 61], lum[40, 75])             # the bank is lighter than the middle
        self.assertGreater(lum[40, 66], lum[40, 75] - 1)
        mid = colours(img.astype(np.uint8), (80, 10, 110, 70))
        self.assertEqual(len(mid), 1)                             # the deep middle is one flat tone: no patches


if __name__ == "__main__":
    unittest.main()

"""reel.fx: light on black -> un-premultiplied RGBA that re-adds to the same light; impact peaks."""
import unittest

import numpy as np

from reel.fx import _peaks, light_to_rgba


class FxTest(unittest.TestCase):
    def test_additive_roundtrip(self):
        rgb = np.array([[[0, 0, 0], [8, 4, 2], [200, 120, 40], [255, 255, 255]]], np.uint8)
        out = light_to_rgba(rgb, black=10).astype(float)
        a = out[..., 3:] / 255
        self.assertEqual(out[0, 0, 3], 0)                      # black and noise below the level are clear
        self.assertEqual(out[0, 1, 3], 0)
        self.assertEqual(out[0, 3, 3], 255)                    # full white is opaque
        added = out[..., :3] * a                               # what canvas 'lighter' adds
        self.assertTrue(np.all(np.abs(added[0, 2] - rgb[0, 2]) < 12), added[0, 2])   # same light, minus the black level
        self.assertAlmostEqual(added[0, 2, 0] / added[0, 2, 2], 200 / 40, delta=0.1)     # hue kept

    def test_peaks(self):
        v = np.array([0, 5, 1, 0, 9, 2, 1, 6, 0], float)
        self.assertEqual(_peaks(v, 0.25), [1, 4, 7])
        self.assertEqual(_peaks(np.array([0, 1, 0.95, 1, 0]), 0.25), [1])   # a wobble is not a second hit


if __name__ == "__main__":
    unittest.main()

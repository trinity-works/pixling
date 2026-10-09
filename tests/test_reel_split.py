"""reel.split on a synthetic one-row sheet: figures found left to right, shared scale and baseline, body-centred."""
import tempfile
import unittest
from pathlib import Path

import numpy as np
from PIL import Image

from reel.split import split


class SplitTest(unittest.TestCase):
    def test_split_baseline_and_scale(self):
        a = np.zeros((300, 1000, 3), np.uint8)
        a[:] = (255, 0, 255)
        for i, (h, wpn) in enumerate(((120, 0), (100, 40), (120, 0))):
            x = 100 + i * 300
            a[250 - h:250, x:x + 50] = (40, 60, 120)                 # body, feet on y=250
            if wpn:
                a[250 - h - wpn:250 - h, x + 60:x + 70] = (200, 200, 90)   # detached weapon above-right
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "sheet.png"
            Image.fromarray(a).save(p)
            out = split(p, ("a", "b", "c"), size=400)
            feet, tops, cx = [], [], []
            for n in "abc":
                m = (np.abs(np.asarray(Image.open(out[n])).astype(int) - (255, 0, 255)).sum(-1) > 60)
                ys, xs = np.nonzero(m)
                feet.append(ys.max()); tops.append(ys.min())
                low = ys > ys.max() - 20
                cx.append(np.median(xs[low]))
            self.assertLessEqual(max(feet) - min(feet), 2)            # one baseline
            self.assertLessEqual(abs(tops[0] - tops[2]), 2)           # same scale for equal figures
            self.assertTrue(all(abs(c - 200) <= 3 for c in cx))       # centred on the body, not the weapon
            self.assertLess(tops[1], tops[0])                         # the weapon stayed attached to figure b


if __name__ == "__main__":
    unittest.main()

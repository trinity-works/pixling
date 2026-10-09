"""reel.qc on synthetic block figures: each check fires on its failure and stays quiet on a clean clip."""
import unittest

import numpy as np

from reel.cut import Cel, measure
from reel.qc import qc_clip


def figure(hip_dx=0, weapon_up=0, step=0, x=100, y=100, w=40, h=80):
    """Block figure on a 200x220 frame: upper body, hips shifted by hip_dx, a raised weapon, a stepping foot."""
    a = np.zeros((220, 200, 4), np.uint8)
    a[y:y + int(h * 0.5), x:x + w] = (200, 80, 40, 255)                                  # upper body
    a[y + int(h * 0.5):y + h, x + hip_dx:x + hip_dx + w] = (90, 60, 40, 255)           # hips/legs
    if step:
        a[y + h - 12:y + h, x + w:x + w + step] = (60, 40, 30, 255)                     # forward foot
    if weapon_up:
        a[y - weapon_up:y, x + w - 6:x + w] = (120, 120, 130, 255)                      # raised weapon
    return measure(Cel(a, 0, 0))


class QcTest(unittest.TestCase):
    def test_clean_walk_passes(self):
        cels = [figure(step=s) for s in (2, 5, 8, 5, 2, 5, 8, 5)]
        r = qc_clip(cels, "walk", "e", cels[0])
        self.assertTrue(r["ok"], r["flags"])

    def test_walk_hip_sway_flagged(self):
        cels = [figure(hip_dx=d, step=2 + i) for i, d in enumerate((0, 3, 6, 3, 0, -3, -6, -3))]
        r = qc_clip(cels, "walk", "e", cels[0])
        self.assertTrue(any(f.startswith("sway") for f in r["flags"]), r["flags"])

    def test_walk_position_seam_flagged(self):
        # same pose every key, but the body walks 1px per key and the loop snaps back 7px
        cels = [figure(x=100 + i, step=(2, 5, 8, 5)[i % 4]) for i in range(8)]
        r = qc_clip(cels, "walk", "e", cels[0])
        self.assertTrue(any("snaps" in f for f in r["flags"]), r["flags"])

    def test_attack_second_arc_flagged(self):
        cels = [figure(weapon_up=u) for u in (0, 20, 40, 5, 0, 30, 5, 0)]   # strike, then a re-lift
        r = qc_clip(cels, "attack", "e", cels[0])
        self.assertTrue(any(f.startswith("arc") for f in r["flags"]), r["flags"])

    def test_clean_attack_single_arc(self):
        cels = [figure(weapon_up=u, step=i) for i, u in enumerate((0, 15, 30, 40, 5, 2, 1, 0))]
        r = qc_clip(cels, "attack", "e", cels[0])
        self.assertFalse(any(f.startswith("arc") for f in r["flags"]), r["flags"])
        self.assertEqual(r["metrics"]["tip_peaks"], [3])


if __name__ == "__main__":
    unittest.main()

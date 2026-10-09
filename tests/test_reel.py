import shutil
import tempfile
import unittest
from pathlib import Path

import numpy as np

from reel import io, key, synth

ROOT = Path(__file__).resolve().parent.parent


def _sprites():
    # a simple two-tone figure that bobs, so the test needs no build output
    out = []
    for i in range(8):
        f = np.zeros((52, 40, 4), np.uint8)
        y = 8 + (i % 4 > 1)
        f[y:y + 36, 12:28] = (200, 60, 50, 255)
        f[y:y + 10, 14:26] = (240, 200, 90, 255)
        f[y + 36:48, 14:18] = f[y + 36:48, 22:26] = (40, 40, 60, 255)
        out.append(f)
    return out


@unittest.skipUnless(shutil.which("ffmpeg"), "needs ffmpeg")
class KeyTest(unittest.TestCase):
    def test_synthetic_green_screen(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "t.mp4"
            gt = synth.film(_sprites(), p, repeat=1)
            for i, fr in enumerate(io.read_frames(p)):
                rgba, (x0, y0), _ = key.key_frame(fr)
                full = np.zeros(fr.shape[:2])
                h, w = rgba.shape[:2]
                full[y0:y0 + h, x0:x0 + w] = rgba[..., 3] / 255
                g, pr = gt[i] > 0.5, full > 0.5
                self.assertGreater((g & pr).sum() / (g | pr).sum(), 0.85)
                c = rgba[rgba[..., 3] > 0][:, :3].astype(int)
                self.assertLess(np.mean(c[:, 1] - np.maximum(c[:, 0], c[:, 2]) > 40), 0.01)


class ClockTest(unittest.TestCase):
    def test_contact_lands_on_hit_frame(self):
        from reel.game import pick
        idx = pick(121, 8, (20, 110), contact=64)
        self.assertEqual(len(idx), 8)
        self.assertEqual(idx[3], 64)          # attackHitFrame 4 (1-indexed)
        self.assertEqual((idx[0], idx[-1]), (20, 110))

    def test_loop_leaves_out_the_closing_frame(self):
        from reel.game import pick
        idx = pick(121, 16, (0, 120), loop=True)
        self.assertEqual(len(idx), 16)
        self.assertNotIn(120, idx)


class PoseKeyTest(unittest.TestCase):
    def test_short_windup_does_not_hang(self):
        from reel import cut, keys
        cels = []
        for i in range(24):                       # a bar that grows: 24 frames, contact at 3
            f = np.zeros((60, 40, 4), np.uint8)
            f[10 + (i % 5):58, 10:30] = 200
            cels.append(cut.measure(cut.Cel(f, 0, 0)))
        k = keys.attack_keys(cels, cels[0], 1.0, contact=3, n=10, hit=5)
        self.assertEqual(len(k), 10)
        self.assertEqual(k[4], 3)

    def test_arclength_spacing_skips_holds(self):
        from reel.keys import spaced
        # motion only between frames 10 and 20; a long hold after it
        A = np.concatenate([np.zeros(10), np.linspace(0, 1, 11), np.ones(30)])
        k = spaced(A, 0, 50, 4, include_a=False, include_b=False)
        self.assertTrue(all(10 <= i <= 20 for i in k), k)
        self.assertEqual(len(set(k)), 4)

    def test_pop_detection(self):
        from reel.keys import pops
        th = [np.full(8, 0.1 * i) for i in range(10)]
        th[5] = np.full(8, 3.0)                     # one-frame morph
        bad = pops(th)
        self.assertTrue(bad[5])
        self.assertEqual(int(bad.sum()), 1)


if __name__ == "__main__":
    unittest.main()

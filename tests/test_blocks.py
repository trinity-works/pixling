import unittest

import numpy as np

from pp.blocks import FACINGS, BlockPiece

SPEC = {"name": "t", "vox": 2, "palette": {"a": ["#ffffff", "#888888", "#222222"], "e": ["#ffffff", "#00ff00", "#00ff00"]},
        "layers": [["aaa", "aaa", "aaa"], ["aaa", "aae", "aaa"]], "cast": True}


def colours(f):
    return {tuple(p[:3]) for p in f[f[..., 3] > 0]}


class BlocksTest(unittest.TestCase):
    def test_cube_is_exact_iso(self):
        p = BlockPiece({"name": "c", "vox": 2, "palette": {"a": ["#ffffff", "#888888", "#222222"]},
                        "layers": [["aa", "aa"], ["aa", "aa"]]})
        f = p.frame("E")
        ys, xs = np.nonzero(f[..., 3])
        self.assertEqual(xs.max() - xs.min() + 1, 8)   # 4 units deep each way -> 8 px wide
        self.assertEqual(ys.max() - ys.min() + 1, 8)   # 4 px top diamond + 4 px sides
        self.assertEqual(colours(f), {(255, 255, 255), (136, 136, 136), (34, 34, 34)})

    def test_facings_rotate(self):
        p = BlockPiece(SPEC)
        e, w = p.frame("E"), p.frame("W")
        self.assertIn((0, 255, 0), colours(e))         # eyes on the front face
        self.assertNotIn((0, 255, 0), colours(w))      # walking away shows the back
        self.assertEqual(p.sheet("idle").shape[0], 4 * p.h)

    def test_shadow_falls_down_left(self):
        p = BlockPiece(SPEC)
        m = p.shadow("E")[..., 3] > 0
        f = p.frame("E")[..., 3] > 0
        self.assertLess(np.nonzero(m)[1].mean(), np.nonzero(f)[1].mean())
        self.assertGreater(np.nonzero(m)[0].mean(), np.nonzero(f)[0].mean())

    def test_clips_and_events(self):
        p = BlockPiece(SPEC)
        self.assertEqual(set(p.clips), {"idle", "move", "attack", "hurt", "cast"})
        self.assertEqual(p.events("attack")[0]["name"], "hit")
        self.assertEqual(p.events("cast")[0]["name"], "cast")
        self.assertNotIn("cast", BlockPiece(dict(SPEC, cast=False)).clips)
        for c in p.clips:
            for fc in FACINGS:
                fr, _, _ = p.clip(c, fc)
                for f in fr:  # nothing is clipped by the frame edge
                    a = f[..., 3] > 0
                    self.assertFalse(a[0].any() or a[-1].any() or a[:, 0].any() or a[:, -1].any())


if __name__ == "__main__":
    unittest.main()

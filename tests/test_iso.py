"""Exact-iso camera (pp.iso), soft line (pp.iso_line) and pixel check (pp.pixcheck). Run: python3 -m unittest tests.test_iso"""
import sys
import tempfile
import unittest
from pathlib import Path

import numpy as np
from PIL import Image

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from pp import iso  # noqa: E402
from pp.pixcheck import check  # noqa: E402

PAL = {"grass": ["#2c6a4a", "#4a8a5a", "#6aa874"], "wall": ["#7a5040", "#a87a5a", "#d8b48a"],
       "ink": ["#101818", "#1c2a2a"]}
MATS = {"grass": {"ramp": "grass", "top": 1, "shadow": 0},
        "wall": {"ramp": "wall", "top": 2, "lit": 1, "shade": 0}}


def scene(**extra):
    spec = {"size": [64, 48], "origin": [32, 20], "light": [0, -1, 1], "palette": PAL, "materials": MATS,
            "ground": {"cell": 4, "h": [[2] * 8 for _ in range(8)], "mat": [[0] * 8 for _ in range(8)],
                       "names": ["grass"], "outside": 0, "side": "wall"},
            "polys": [iso.box(10, 10, 2, 18, 16, 10, {"*": {"m": "wall"}, "top": {"m": "wall", "tone": "top"},
                                                       "px": {"m": "wall", "tone": "shade"},
                                                       "py": {"m": "wall", "tone": "lit"}}, grp=1)]}
    spec.update(extra)
    return iso.Scene(spec)


class IsoTest(unittest.TestCase):
    def test_deterministic_and_closed_palette(self):
        a = iso.render_frame(scene())
        b = iso.render_frame(scene())
        self.assertTrue(np.array_equal(a, b))
        allowed = {tuple(c) for ramp in scene().pal.values() for c in ramp}
        self.assertTrue({tuple(c) for c in a.reshape(-1, 3)} <= allowed)

    def test_box_edges_are_clean_stairs(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "box.png"
            Image.fromarray(iso.render_frame(scene())).save(p)
            rep = check(p)
        self.assertEqual(rep["orphans"], 0)
        self.assertEqual(rep["broken_stairs"], 0)
        self.assertTrue(set(rep["stair_shifts"]) <= {0, 1, 2})

    def test_soft_line_stays_inside_the_silhouette(self):
        plain = scene().render()
        lined = iso.render_frame(scene(line={"ink_ramp": "ink", "ink_tone": 1}))
        base = iso.render_frame(scene())
        changed = (lined != base).any(-1)
        self.assertTrue(changed.any())
        self.assertTrue((plain["GRP"][changed] == 1).all())

    def test_mirror_and_swap_keep_volume(self):
        p = iso.box(0, 0, 0, 4, 2, 3, {"*": {"m": "wall"}})
        for q in (iso.mirror(p, 0, 1.0), iso.swap_xy(p)):
            xs = sorted({v[0] for v in q["verts"]})
            ys = sorted({v[1] for v in q["verts"]})
            self.assertEqual((xs[-1] - xs[0]) * (ys[-1] - ys[0]), 8)
            self.assertEqual(sorted(k for _, _, k in q["planes"]), sorted(k for _, _, k in p["planes"]))


if __name__ == "__main__":
    unittest.main()

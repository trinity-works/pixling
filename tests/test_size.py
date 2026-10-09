"""Size classes and 2D-HD maps. Run: python3 -m unittest tests.test_size"""
import copy
import json
import sys
import tempfile
import unittest
from pathlib import Path

import numpy as np
from PIL import Image

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from pp.forge import Forge, load_style  # noqa: E402
from pp.lint import size_family  # noqa: E402
from pp.size import SIZES, fit, measure  # noqa: E402
from tests.test_core import SPEC  # noqa: E402


class SizeTest(unittest.TestCase):
    def test_fit_hits_class_height(self):
        st = load_style("duskborne")
        h0, _ = measure(SPEC, st)
        for cls in ("small", "large"):
            spec = dict(copy.deepcopy(SPEC), size=cls)
            out, k = fit(spec, st)
            h, _ = measure(out, st)
            self.assertLessEqual(abs(h - SIZES[cls]), 1, (cls, h0, h, k))
            fw, fh = out["frame"]
            ax, ay = out["anchor"]
            self.assertGreaterEqual(ay, h)            # the frame holds the whole body above the feet
            self.assertTrue(0 < ax < fw and 0 < ay < fh)

    def test_no_size_is_unchanged(self):
        out, k = fit(SPEC, load_style("duskborne"))
        self.assertIs(out, SPEC)
        self.assertEqual(k, 1.0)

    def test_build_meta_maps_and_family_order(self):
        with tempfile.TemporaryDirectory() as tmp:
            dirs = []
            for name, cls in (("a", "small"), ("b", "large")):
                spec = dict(copy.deepcopy(SPEC), name=name, size=cls, clips=["idle"], maps=["normal", "height"])
                d = Path(tmp) / name
                meta = Forge(spec).build(d, ["S"])
                self.assertEqual(meta["size"], cls)
                self.assertLessEqual(abs(meta["height_px"] - SIZES[cls]), 1)
                c = meta["clips"]["idle"]
                col = np.array(Image.open(d / c["sheet"]).convert("RGBA"))
                nor = np.array(Image.open(d / c["maps"]["normal"]).convert("RGBA"))
                hgt = np.array(Image.open(d / c["maps"]["height"]).convert("RGBA"))
                self.assertEqual(col.shape, nor.shape)
                self.assertEqual(col.shape, hgt.shape)
                on = nor[..., 3] > 0
                self.assertTrue(on.any())
                self.assertTrue((col[..., 3][on] > 0).all())    # maps only where the sprite has pixels
                n = nor[on][:, :3].astype(float) / 127.5 - 1
                self.assertTrue(np.allclose(np.linalg.norm(n, axis=1), 1, atol=0.06))
                self.assertGreater(hgt[on][:, 0].max(), hgt[on][:, 0].min())
                dirs.append(str(d))
            self.assertEqual(size_family(dirs), [])
            # swap the labels: a "large" that measures shorter than a "small" is out of order
            m = json.loads((Path(dirs[0]) / "a.json").read_text())
            m["size"] = "huge"
            (Path(dirs[0]) / "a.json").write_text(json.dumps(m))
            self.assertTrue(size_family(dirs))


if __name__ == "__main__":
    unittest.main()

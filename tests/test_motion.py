"""Motion toolkit guarantees (pp/motion.py). Run: python3 -m unittest discover tests"""
import json
import math
import sys
import unittest
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from pp import anim as A  # noqa: E402
from pp import motion as M  # noqa: E402
from pp.forge import Forge  # noqa: E402
from pp.sdf import rot_matrix  # noqa: E402
from tests.test_core import SPEC  # noqa: E402

ARMED = json.loads(json.dumps(SPEC))
ARMED["bones"].append({"name": "sword", "parent": "armR", "at": [0, 0, -4.5],
                       "parts": [{"shape": "box", "at": [0, 0, 5], "half": [0.6, 0.4, 5], "mat": "bone"}]})


class Motion(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.forge = Forge(json.loads(json.dumps(ARMED)))
        cls.model = cls.forge.model

    def test_euler_roundtrip(self):
        rng = np.random.default_rng(1)
        for _ in range(100):
            r = tuple(rng.uniform(-85, 85, 3))
            self.assertTrue(np.allclose(rot_matrix(*M.euler_from_matrix(rot_matrix(*r))), rot_matrix(*r), atol=1e-6))

    def test_mix_is_an_arc(self):
        """A multi-axis blend turns about ONE axis, so the limb tip draws a single planar circle (an arc),
        where a per-axis Euler lerp wobbles off it."""
        a, b = (-80, 0, 95), (-88, 30, -80)
        v = np.array([0, 0, -1.0])

        def flatness(path):
            P = np.array(path)
            return np.linalg.svd(P - P.mean(0))[1][-1]
        ts = np.linspace(0, 1, 9)
        arc = [rot_matrix(*M.slerp_rot(a, b, t)) @ v for t in ts]
        eul = [rot_matrix(*[x + (y - x) * t for x, y in zip(a, b)]) @ v for t in ts]
        self.assertLess(flatness(arc), 1e-6)
        self.assertGreater(flatness(eul), 1e-3)

    def test_aim_points_the_bone(self):
        clip = A.Clip("t", [A.Frame({"armR": {"aim": (0, -1, 0)}, "sword": {"aim": (0, 0, 1)}})], loop=False)
        M.resolve_aims(self.model, clip)
        w = self.model.world(clip.frames[0].pose, 0.0)
        for bone, want in (("armR", (0, -1, 0)), ("sword", (0, 0, 1))):
            Mw, _ = w[bone]
            got = Mw @ M.bone_axis(self.model, bone)
            self.assertGreater(float(got @ np.asarray(want, float)), 0.999, bone)

    def test_drag_lags_children_and_spares_the_hit(self):
        fr = [A.Frame({"torso": {"rot": (0, 0, 40 * min(1, i / 2))}}) for i in range(5)]
        fr[2].event = "hit"
        clip = A.Clip("t", fr, loop=False)
        before = [f.pose.get("armR", {}).get("rot", (0, 0, 0)) for f in fr]
        M.drag(self.model, clip, {"armR": 0.5})
        self.assertNotEqual(clip.frames[1].pose["armR"]["rot"], before[1])    # lags behind the torso
        self.assertNotIn("armR", clip.frames[2].pose)                           # strike frame is exact
        self.assertAlmostEqual(clip.frames[4].pose["armR"]["rot"][2], 0.0, places=6)   # settles

    def test_stabilize_holds_sub_pixel_drift(self):
        fr = [A.Frame({"armR": {"rot": (0.4 * i, 0, 0)}}) for i in range(6)]
        clip = M.stabilize(self.model, A.Clip("t", fr, loop=False))
        self.assertEqual(len({f.pose["armR"]["rot"] for f in clip.frames}), 1)

    def test_sweep_covers_the_arc(self):
        up = {"armR": {"rot": (-170, 0, 0)}}
        fwd = {"armR": {"rot": (-90, 0, 0)}}
        m = M.sweep_mask(self.model, up, (0, 0, 0), fwd, (0, 0, 0), "sword", 90.0, (40, 40), (20, 34))
        self.assertGreater(int(m.sum()), 20)

    def test_limit_holds_poses_and_keeps_keys(self):
        clips = {c.name: c for c in self.forge.clips()}
        att = clips["attack"]
        poses = [f.pose for f in att.frames]
        uniq = [i for i in range(len(poses)) if i == 0 or poses[i] != poses[i - 1]]
        self.assertLessEqual(len(uniq), len(poses) - 3)          # fewer poses than frames (held)
        hit = next(i for i, f in enumerate(att.frames) if f.event == "hit")
        self.assertIn(hit, uniq)                                  # the strike is its own pose
        walk = clips["walk"]
        for i in range(0, len(walk.frames), 2):                   # loops step on twos
            self.assertEqual(walk.frames[i].pose, walk.frames[i + 1].pose)


if __name__ == "__main__":
    unittest.main()

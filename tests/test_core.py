"""Guarantees the art depends on. Run: python3 -m unittest discover tests"""
import json
import sys
import tempfile
import unittest
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from pp import anim as A  # noqa: E402
from pp.forge import Forge, load_style  # noqa: E402

SPEC = {
    "name": "t", "style": "duskborne", "rig": "humanoid", "frame": [40, 40], "anchor": [20, 34],
    "bones": [
        {"name": "root"},
        {"name": "hips", "parent": "root", "at": [0, 0, 6], "parts": [{"shape": "ellipsoid", "r": [3.5, 2.5, 2], "mat": "leather"}]},
        {"name": "torso", "parent": "hips", "at": [0, 0, 0.5], "parts": [{"shape": "ellipsoid", "at": [0, 0, 3], "r": [4, 3, 3.5], "mat": "cloth_red"}]},
        {"name": "head", "parent": "torso", "at": [0, 0, 6.5], "parts": [{"shape": "sphere", "at": [0, 0, 5], "r": 5.5, "mat": "bone"}]},
        {"name": "armL", "parent": "torso", "at": [-4.5, 0, 5], "parts": [{"shape": "capsule", "b": [0, 0, -4.5], "r": 1.4, "mat": "bone"}]},
        {"name": "armR", "parent": "torso", "at": [4.5, 0, 5], "parts": [{"shape": "capsule", "b": [0, 0, -4.5], "r": 1.4, "mat": "bone"}]},
        {"name": "legL", "parent": "hips", "at": [-1.8, 0, -0.5], "parts": [{"shape": "capsule", "b": [0, 0, -4.5], "r": 1.5, "mat": "dark"}]},
        {"name": "legR", "parent": "hips", "at": [1.8, 0, -0.5], "parts": [{"shape": "capsule", "b": [0, 0, -4.5], "r": 1.5, "mat": "dark"}]},
    ],
}


class Core(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.forge = Forge(json.loads(json.dumps(SPEC)))

    def test_palette_lock(self):
        pal = {tuple(c) for c in self.forge.style.palette()}
        f = self.forge.frame(A.Frame({}), "SE")
        used = {tuple(v) for v in f[f[..., 3] > 0][:, :3].tolist()}
        self.assertTrue(used, "empty sprite")
        self.assertTrue(used <= pal, "off-palette: %s" % (used - pal))
        self.assertTrue(set(np.unique(f[..., 3])) <= {0, 255}, "semi-transparent pixels")

    def test_translation_keeps_pixels(self):
        """Whole-pixel motion must shift pixels exactly (no swimming); a bone moving alone keeps
        its interior pattern (only the seam where it meets other parts may change)."""
        a = self.forge.frame(A.Frame({}), "SE")
        b = self.forge.frame(A.Frame({}, root=(0, 0, 2)), "SE")
        self.assertTrue(np.array_equal(a[2:], b[:-2]))
        c = self.forge.frame(A.Frame({"head": {"at": (0, 0, 1)}}), "SE")
        head_a, head_c = a[4:12], c[3:11]
        self.assertGreater((head_a == head_c).all(-1).mean(), 0.95)

    def test_clip_frame_counts(self):
        want = {"idle": 16, "walk": 16, "run": 8, "attack": 13, "hit": 2, "death": 14}
        for name, n in want.items():
            clip = A.RIGS["humanoid"][name]({})
            self.assertEqual(len(clip.frames), n, name)
            self.assertTrue(all(f.ms == A.FRAME_MS for f in clip.frames))

    def test_feet_swing_forward(self):
        """A lifted foot must be on its forward swing (else walks read as moonwalking), and a planted foot
        slides back evenly (locked to the ground, no skating)."""
        import math
        for name, gait in [(n, g) for n in ("walk", "run") for g in ("stride", "hop", "lurch", "bounce", "glide")]:
            frames = A.RIGS["humanoid"][name]({"gait": gait}).frames
            n = len(frames)
            for leg in ("legL", "legR"):
                if "foot" not in frames[0].pose.get(leg, {}):
                    continue                                   # hop gaits pose legs directly
                fwd = [f.pose[leg]["foot"][0] for f in frames]
                for i, fr in enumerate(frames):
                    if fr.pose[leg]["foot"][1] > 0:
                        self.assertGreater(fwd[(i + 1) % n] - fwd[(i - 1) % n], 0,
                                           "humanoid %s %s %s frame %d lifts while swinging back" % (name, gait, leg, i))
                planted = [fwd[i] - fwd[(i + 1) % n] for i in range(n)
                           if frames[i].pose[leg]["foot"][1] == 0 and frames[(i + 1) % n].pose[leg]["foot"][1] == 0]
                self.assertTrue(planted and max(planted) - min(planted) < 1e-6, "%s %s %s skates" % (name, gait, leg))
        L = 6.0
        for name, gait in [(n, g) for n in ("walk", "run") for g in ("stride", "hop", "lurch", "bounce", "glide")]:
            frames = A.RIGS["quadruped"][name]({"gait": gait}).frames
            n = len(frames)
            for leg in ("legFL", "legFR", "legHL", "legHR"):
                for i, fr in enumerate(frames):
                    d = fr.pose.get(leg, {})
                    a = math.radians(d.get("rot", (0, 0, 0))[0])
                    paw = fr.pose.get("body", {}).get("at", (0, 0, 0))[2] + d.get("at", (0, 0, 0))[2] \
                        + fr.root[2] - L * (1 - math.cos(a))
                    if paw <= 0.5 or fr.root[2] > 0:
                        continue
                    a0 = frames[(i - 1) % n].pose[leg]["rot"][0]
                    a1 = frames[(i + 1) % n].pose[leg]["rot"][0]
                    self.assertLess(a1 - a0, 1e-6, "quadruped %s %s frame %d lifts while swinging back" % (name, leg, i))

    def test_motion_styles(self):
        """Every attack style has exactly one hit, keeps whole-frame timing and ends at rest; hover lifts
        every frame of a floater but its death lands on the ground; hit-stop freezes the impact frame."""
        for st in ("slash", "dart", "heavy", "hop", "iaido"):
            fr = A.RIGS["humanoid"]["attack"]({"attack_style": st}).frames
            self.assertEqual([f.event for f in fr].count("hit"), 1, st)
            self.assertTrue(all(f.ms == A.FRAME_MS for f in fr), st)
            self.assertEqual(tuple(A.snap(v) for v in fr[-1].root), (0, 0, 0), st)
        p = {"hover": 2, "idle_style": "float", "gait": "hop"}
        for name in ("idle", "walk", "run", "attack", "hit"):
            self.assertTrue(all(f.root[2] >= 2 for f in A.RIGS["humanoid"][name](p).frames), name)
        self.assertEqual(A.RIGS["humanoid"]["death"](p).frames[-1].root[2], 0)
        clip = A.RIGS["humanoid"]["attack"]({})
        held = A.hitstop(clip, 2).frames
        self.assertEqual(len(held), len(clip.frames) + 2)
        self.assertEqual([f.event for f in held].count("hit"), 1)
        wide = [i for i, f in enumerate(held) if any(x.get("arc") == "wide" or
                                                     (x.get("kind") == "sweep" and not x.get("tail")) for x in f.fx)]
        self.assertEqual(len(wide), 1, "the solid smear must exist for exactly one frame")

    def test_shadow_stays_on_ground(self):
        """A lifted body keeps its shadow at the feet (smaller), so hops and floating read."""
        spec = json.loads(json.dumps(SPEC))
        spec["shadow"] = {"w": 11, "h": 3}
        f = Forge(spec)
        a = f.frame(A.Frame({}), "S")
        b = f.frame(A.Frame({}, root=(0, 0, 5)), "S")
        ay = f.anchor[1]
        self.assertTrue(a[ay, f.anchor[0], 3] > 0 and b[ay, f.anchor[0], 3] > 0)
        wa = int((a[ay, :, 3] > 0).sum())
        wb = int((b[ay, :, 3] > 0).sum())
        self.assertLess(wb, wa)

    def test_aseprite_roundtrip(self):
        sys.path.insert(0, str(Path(__file__).parent))
        import ase   # tests/ase.py: a pure-Python .aseprite reader
        from pp.aseprite import write_aseprite
        f0 = self.forge.frame(A.Frame({}), "S")
        f1 = self.forge.frame(A.Frame({}), "E")
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "x.aseprite"
            write_aseprite(p, [f0, f1], [75, 75], [("idle_S", 0, 0), ("idle_E", 1, 1)], self.forge.style.palette())
            a = ase.AseFile.load(str(p))
            self.assertEqual([t.name for t in a.tags], ["idle_S", "idle_E"])
            r = np.asarray(a.render_frame(1))
            m = f1[..., 3] > 0
            self.assertTrue(np.array_equal(r[m], f1[m]))


if __name__ == "__main__":
    unittest.main()

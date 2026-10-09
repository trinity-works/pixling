"""Guarantees for inspect, variants, layers and map kits. Run: python3 -m unittest discover tests"""
import copy
import sys
import unittest
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tests"))

from pp import anim as A  # noqa: E402
from pp.forge import Forge  # noqa: E402
from test_core import SPEC  # noqa: E402


def spec(**extra):
    s = copy.deepcopy(SPEC)
    s["bones"].append({"name": "cape", "parent": "torso", "at": [0, 2, 5],
                       "parts": [{"shape": "capsule", "b": [0, 1, -6], "r": 1.2, "mat": "cloth_red"}]})
    s.update(extra)
    return s


class Inspect(unittest.TestCase):
    def test_reads_the_real_bake(self):
        from pp.inspect import gather
        f = Forge(spec(clips=["idle"]))
        info = gather(f, "idle", "SE", 3)
        again = f.frame(f.clips()[0].frames[3], "SE")
        self.assertTrue(np.array_equal(info["rgba"], again), "inspect must show exactly the shipped frame")
        body = int((info["buf"].mat >= 0).sum())
        self.assertEqual(sum(r["px"] for r in info["rows"]), body, "every body pixel belongs to one listed bone")

    def test_attach_points_sit_on_their_bone(self):
        f = Forge(spec(clips=["idle"], attach=True))
        f.frame(A.Frame({}), "S")
        pts = f.attach_points(f.attach_spec())
        x, y, vis = pts["head"]
        self.assertTrue(vis, "head centre is visible from the front")
        self.assertEqual(f.model.order[f._buf.bone[y, x]], "head")


class Variants(unittest.TestCase):
    def test_row0_is_the_spec(self):
        from pp.variants import plan
        rows = plan(["anim.drag=0.5,1.5"])
        self.assertEqual(rows[0], {})
        self.assertEqual([r["anim.drag"] for r in rows[1:]], [0.5, 1.5])

    def test_keyed_draws_ignore_other_keys(self):
        from pp.variants import plan
        a = plan(["anim.drag=0.4..1.6"], sample=4, seed=7)
        b = plan(["anim.drag=0.4..1.6", "anim.idle_bob=1..3"], sample=4, seed=7)
        self.assertEqual([r.get("anim.drag") for r in a], [r.get("anim.drag") for r in b])

    def test_paths_address_bones_by_name(self):
        from pp.variants import set_path
        s = spec()
        set_path(s, "bones.head.parts.0.r", 6.0)
        set_path(s, "anim.drag", 0.5)
        head = next(b for b in s["bones"] if b["name"] == "head")
        self.assertEqual((head["parts"][0]["r"], s["anim"]["drag"]), (6.0, 0.5))


class Layers(unittest.TestCase):
    def test_combo_takes_masked_bones_from_over(self):
        s = spec(clips=["walk_attack"], layers={"walk_attack": {"base": "walk",
                                                                "over": [{"clip": "attack", "bones": "torso/", "spine": 1.0}]}})
        f = Forge(s)
        from pp.layers import bone_mask, combo
        bones, roots = bone_mask(f.model, "torso/")
        self.assertEqual(set(bones), {"torso", "head", "armL", "armR", "cape"})
        params = {"body_h": 20}
        raw = lambda n: A.RIGS["humanoid"][n](params)
        c = combo(f.model, "walk_attack", s["layers"]["walk_attack"], raw)
        att, walk = raw("attack"), raw("walk")
        self.assertEqual(len(c.frames), len(att.frames))
        self.assertTrue(any(fr.event == "hit" for fr in c.frames), "the hit event survives")
        for i in (0, 5):
            self.assertEqual(c.frames[i].pose.get("legL"), walk.frames[i].pose.get("legL"), "legs come from walk")
            self.assertEqual(c.frames[i].pose.get("armR"), att.frames[i].pose.get("armR"), "arms come from attack")

    def test_no_layers_no_change(self):
        a = [(c.name, [f.pose for f in c.frames]) for c in Forge(spec()).clips()]
        b = [(c.name, [f.pose for f in c.frames]) for c in Forge(spec(life={})).clips()]
        self.assertEqual(a, b)

    def test_look_keeps_the_loop_closed(self):
        f = Forge(spec(clips=["idle"], life={"look": {"every": 2}}))
        c = f.clips()[0]
        plain = Forge(spec(clips=["idle"])).clips()[0]
        self.assertEqual(len(c.frames), 2 * len(plain.frames))
        self.assertEqual(c.frames[-1].pose.get("head"), plain.frames[-1].pose.get("head"),
                         "the head is back before the loop wraps")
        self.assertTrue(any(f.pose != g.pose for f, g in zip(c.frames[len(plain.frames):], plain.frames)))

    def test_sway_is_whole_pixels(self):
        from pp.layers import sway
        c = sway(A.Clip("idle", [A.Frame({})]), {"bones": ["a", "b"], "px": 1.8, "frames": 8})
        xs = [f.pose[b]["at"][0] for f in c.frames for b in ("a", "b")]
        self.assertTrue(all(float(x).is_integer() for x in xs))


class Kits(unittest.TestCase):
    def test_plain_maps_untouched_and_neighbours_differ(self):
        from pp.map import resolve_kits
        plain = {"objects": [{"at": [0, 0], "build": "x"}]}
        self.assertIs(resolve_kits(plain), plain)
        m = {"seed": 3, "objects": [{"at": [i * 20, 0], "build": ["a", "b", "c"]} for i in range(20)]}
        picks = [o["build"] for o in resolve_kits(m)["objects"]]
        self.assertTrue(all(p != q for p, q in zip(picks, picks[1:])))
        self.assertEqual(picks, [o["build"] for o in resolve_kits(m)["objects"]], "deterministic")


if __name__ == "__main__":
    unittest.main()

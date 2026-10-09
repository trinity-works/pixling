"""Building states: generic over any building spec, deterministic, and every state builds.
Run: python3 -m unittest tests.test_states"""
import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from pp.forge import Forge, load_spec  # noqa: E402
from pp.states import apply  # noqa: E402

SPECS = ["specs/vista/house_5.json", "specs/vista/house_2.json", "specs/vista/chapel.json"]


def shapes(spec):
    return [p["shape"] for b in spec["bones"] for p in b.get("parts", [])]


class States(unittest.TestCase):
    def test_ruin_has_no_roof_and_keeps_the_frame(self):
        for path in SPECS:
            base = load_spec(ROOT / path)
            _, r = apply(base, "ruin")
            self.assertIn("roof", shapes(base))
            self.assertNotIn("roof", shapes(r))
            self.assertEqual((r["frame"], r["anchor"]), (base["frame"], base["anchor"]))
            self.assertEqual(r["name"], base["name"] + "~ruin")

    def test_ruin_windows_are_dark_holes(self):
        for path in SPECS:
            _, r = apply(load_spec(ROOT / path), "ruin")
            keys = [v for b in r["bones"] for p in b.get("parts", []) if p["shape"] in ("stamp", "stamp_row")
                    for v in p["key"].values()]
            self.assertNotIn("window", keys)

    def test_deterministic(self):
        base = load_spec(ROOT / SPECS[0])
        for st in ("ruin", "build:0.5", "build:0.8"):
            self.assertEqual(json.dumps(apply(base, st)[1], sort_keys=True), json.dumps(apply(base, st)[1], sort_keys=True))

    def test_walls_rise_in_courses_and_the_roof_comes_last(self):
        base = load_spec(ROOT / SPECS[0])
        tops = []
        for k in (0.25, 0.5, 0.7):
            _, s = apply(base, "build:%s" % k)
            walls = [p for b in s["bones"] for p in b.get("parts", [])
                     if p["shape"] == "box" and p.get("mat") == "plaster" and p["at"][2] - p["half"][2] <= 0.6]
            tops.append(max(p["at"][2] + p["half"][2] for p in walls))
            self.assertNotIn("roof", shapes(s))
        self.assertTrue(tops[0] < tops[1] < tops[2])
        self.assertIn("roof", shapes(apply(base, "build:0.95")[1]))
        self.assertEqual(apply(base, "build:1")[1]["bones"], base["bones"])

    def test_every_state_builds(self):
        base = load_spec(ROOT / SPECS[0])
        with tempfile.TemporaryDirectory() as d:
            for st in ("ruin", "build:0.5", "build:0.8"):
                _, s = apply(base, st)
                meta = Forge(s).build(Path(d) / s["name"])
                self.assertEqual(meta["frame_w"], base["frame"][0])


if __name__ == "__main__":
    unittest.main()

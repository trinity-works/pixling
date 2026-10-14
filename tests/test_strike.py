"""strike.measure on a synthetic sheet: a body with two legs and a thin sword. The pose step finds the sword's grip and
tip (the tip at the far end), both feet and the hurtbox; the reach band holds a stop distance and refuses one that
the blade cannot reach."""
import contextlib
import io
import json
import sys
import tempfile
import unittest
from pathlib import Path

import numpy as np
from PIL import Image

from strike import measure as strike
from strike.__main__ import main as cli

SAMPLE = Path(__file__).resolve().parent.parent / "strike" / "sample"

CELL, PIV = 256, (128, 200)                  # feet point inside a cell


def figure(sword_len):
    """One RGBA cell: a 40x100 torso on two 14 px legs, feet on the pivot, a 4 px sword out to the right at hip height."""
    a = np.zeros((CELL, CELL, 4), np.uint8)
    x, y = PIV
    a[y - 140:y - 40, x - 20:x + 20] = (60, 80, 140, 255)             # torso and head
    a[y - 40:y, x - 18:x - 4] = (50, 50, 60, 255)                    # left leg
    a[y - 40:y, x + 4:x + 18] = (50, 50, 60, 255)                    # right leg
    a[y - 72:y - 68, x + 20:x + 20 + sword_len] = (220, 220, 200, 255)
    return a


class StrikeTest(unittest.TestCase):
    def test_pose_and_reach(self):
        with tempfile.TemporaryDirectory() as d:
            sheet = Path(d) / "attack.png"
            Image.fromarray(np.concatenate([figure(10), figure(80)], 1)).save(sheet)   # frame 1: the strike
            p = strike.pose(sheet, (CELL, CELL), PIV, ["e"], hit=1, use_model=False, log=lambda *_: None)
            k = p["pose"]["e"][1]
            self.assertIsNone(p["pose"]["e"][0]["tip"], "a 10 px stub is no weapon")
            self.assertAlmostEqual(k["tip"][0], 99, delta=3)          # the far end: 20 + 80 px right of the pivot
            self.assertAlmostEqual(k["tip"][1], -70, delta=3)
            self.assertAlmostEqual(k["grip"][0], 20, delta=4)        # the end at the body
            feet = sorted(f[0] for f in k["feet"])
            self.assertLess(feet[0], -4); self.assertGreater(feet[1], 4)
            self.assertTrue(all(abs(f[1]) <= 2 for f in k["feet"]))
            h = p["hurtbox"]
            self.assertLess(h["x"], -10); self.assertGreater(h["x"] + h["w"], 10)
            band = strike.reach_band(p, p, "e", scale=1.0, ppm=40, yscale=1.0)
            self.assertIsNotNone(band)
            self.assertLess(band[0], 1.0); self.assertAlmostEqual(band[1], (k["tip"][0] - h["x"]) / 40, delta=0.05)   # tip meets the box edge
            self.assertTrue(Path(p["json"]).exists())
            self.assertTrue(strike.reach(p["json"], p, 1.0, 40, 1.0, stop=2.0)["ok"])
            self.assertFalse(strike.reach(p["json"], p, 1.0, 40, 1.0, stop=4.0)["ok"])

    def test_cli_on_the_sample_and_a_manifest(self):
        """The committed painted sample end to end through the CLI (--json), and a pixling sprite manifest."""
        def run(*argv):
            buf = io.StringIO()
            with contextlib.redirect_stdout(buf):
                code = cli(list(argv))
            return code, json.loads(buf.getvalue())
        with tempfile.TemporaryDirectory() as d:
            sheet = ["--cell", "256", "--pivot", "128,189.5", "--rows", "se", "--no-model", "--json"]
            _, att = run("pose", str(SAMPLE / "warrior_attack.png"), *sheet, "--hit", "3", "--out", f"{d}/attack")
            _, idle = run("pose", str(SAMPLE / "warrior_idle.png"), *sheet, "--out", f"{d}/idle")
            self.assertIsNotNone(att["tip_at_contact"]["se"], "the sample's sword has a tip on the contact frame")
            cam = ["--scale", "1.17", "--ppm", "40", "--yscale", "0.74", "--json"]
            code, r = run("reach", att["json"], idle["json"], *cam, "--stop", "2.3")
            self.assertEqual(code, 0)
            self.assertLess(r["facings"]["se"]["band"][0], 2.3)
            self.assertEqual(run("reach", att["json"], idle["json"], *cam, "--stop", "5.0")[0], 1)
            # a pixling manifest: cell, anchor, facings and the "hit" frame come from it
            Image.fromarray(np.concatenate([figure(10), figure(80)], 1)).save(f"{d}/knight_attack.png")
            Path(f"{d}/knight.json").write_text(json.dumps({
                "frame_w": CELL, "frame_h": CELL, "anchor": list(PIV), "directions": ["E"],
                "clips": {"attack": {"sheet": "knight_attack.png", "frames": [{"event": None}, {"event": "hit"}]}}}))
            _, m = run("pose", f"{d}/knight.json", "--clip", "attack", "--no-model", "--json")
            self.assertEqual(m["hit_frame"], 1)
            self.assertAlmostEqual(m["tip_at_contact"]["e"][0], 99, delta=3)

    def test_bad_input_says_what_is_wrong(self):
        """Wrong facings, a sheet too small for its grid, a hit past the last frame and an empty sheet stop with a
        message, never with a traceback or a silently empty result."""
        with tempfile.TemporaryDirectory() as d:
            sheet = Path(d) / "a.png"
            Image.fromarray(np.concatenate([figure(10), figure(80)], 1)).save(sheet)
            Image.fromarray(np.zeros((CELL, CELL, 4), np.uint8)).save(Path(d) / "empty.png")
            for kw, word in ((dict(rows=["east"]), "unknown facing"), (dict(rows=["e", "w"]), "too small"),
                             (dict(rows=["e"], hit=5), "outside"), (dict(rows=["e"], sheet=Path(d) / "empty.png"), "empty")):
                with self.assertRaises(SystemExit) as e:
                    strike.pose(kw.pop("sheet", sheet), (CELL, CELL), PIV, use_model=False, log=lambda *_: None, **kw)
                self.assertIn(word, str(e.exception))

    def test_parts_map(self):
        """With a parts map the weapon, the legs and the body come from it: the sword is found even where the
        silhouette rule cannot see it (as wide as the arm), a smear frame's tip is its front end along the facing,
        and the hurtbox leaves the weapon out."""
        P = strike.PARTS
        with tempfile.TemporaryDirectory() as d:
            sheet, parts = np.zeros((CELL, 2 * CELL, 4), np.uint8), np.zeros((CELL, 2 * CELL, 4), np.uint8)
            x, y = PIV
            for f in range(2):
                o = f * CELL
                for part, (y0, y1, x0, x1) in (("body", (y - 140, y - 40, x - 20, x + 20)), ("legL", (y - 40, y, x - 18, x - 4)),
                                               ("legR", (y - 40, y, x + 4, x + 18))):
                    sheet[y0:y1, o + x0:o + x1] = (60, 80, 140, 255)
                    parts[y0:y1, o + x0:o + x1] = (*P[part], 255)
            sheet[y - 80:y - 60, x + 20:x + 60] = (220, 220, 200, 255)             # frame 0: a fat sword, 20 px wide
            parts[y - 80:y - 60, x + 20:x + 60] = (*P["weapon"], 255)
            for i in range(30):                                                   # frame 1: a smear arc, no weapon part
                sheet[y - 120 + 3 * i:y - 116 + 3 * i, CELL + x + 30 + int(15 * np.sin(i / 9)):CELL + x + 36 + int(15 * np.sin(i / 9))] = (200, 255, 255, 255)
            Image.fromarray(sheet).save(f"{d}/a.png")
            Image.fromarray(parts).save(f"{d}/a_parts.png")
            plain = strike.pose(f"{d}/a.png", (CELL, CELL), PIV, ["e"], use_model=False, log=lambda *_: None)
            self.assertIsNone(plain["pose"]["e"][0]["tip"], "a sword as wide as a limb is not thin")
            p = strike.pose(f"{d}/a.png", (CELL, CELL), PIV, ["e"], hit=1, parts=f"{d}/a_parts.png", use_model=False,
                            out=f"{d}/b", log=lambda *_: None)
            k0, k1 = p["pose"]["e"]
            self.assertAlmostEqual(k0["tip"][0], 59, delta=2)                    # the sword's far end
            self.assertLessEqual(k0["grip"][0], 21)                              # its end at the body
            self.assertGreater(k1["tip"][0], 40, "the smear's front end along the facing (east)")
            self.assertEqual(sorted(f[0] for f in k0["feet"]), [-11.5, 10.5])     # the middle of each leg's sole
            self.assertLessEqual(p["hurtbox"]["x"] + p["hurtbox"]["w"], 20)      # the box leaves the sword out

    def test_spec_parts_map(self):
        """pixling build --maps parts writes one flat colour per part from the rig, and the legend in the manifest."""
        from pp.forge import Forge
        sys.path.insert(0, str(Path(__file__).resolve().parent))
        from test_core import SPEC
        spec = json.loads(json.dumps(SPEC))
        spec["bones"].append({"name": "sword", "parent": "armR", "at": [0, 0, -4.5],
                              "parts": [{"shape": "box", "at": [0, 0, -6], "half": [0.6, 0.6, 6], "mat": "bone"}]})
        spec["clips"] = ["idle"]
        with tempfile.TemporaryDirectory() as d:
            meta = Forge(spec).build(d, ["SE"], maps=["parts"])
            self.assertEqual(meta["parts"]["weapon"], list(strike.PARTS["weapon"]))
            pm = np.asarray(Image.open(Path(d) / meta["clips"]["idle"]["maps"]["parts"]).convert("RGBA"))
            colours = {tuple(c) for c in pm[pm[..., 3] > 0][:, :3].tolist()}
            self.assertTrue({strike.PARTS[k] for k in ("weapon", "arm", "body")} <= colours, colours)
            self.assertTrue(colours <= set(strike.PARTS.values()), colours)


if __name__ == "__main__":
    unittest.main()

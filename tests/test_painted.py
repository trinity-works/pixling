"""painted format: style and layout files are well formed and agree with the asset list (no Blender needed)."""
import contextlib
import io
import json
import re
import unittest
from pathlib import Path

from painted import __main__ as painted_cli
from pp import cli

ROOT = Path(__file__).resolve().parent.parent / "painted"


def run(fn, *argv):
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        code = fn(list(argv))
    return code, buf.getvalue()


class PaintedFiles(unittest.TestCase):
    def test_style_ramps(self):
        for f in (ROOT / "styles").glob("*.json"):
            st = json.loads(f.read_text())
            self.assertIn("elevation_deg", st["camera"])
            for name, stops in st["ramps"].items():
                pos = [p for p, _ in stops]
                self.assertEqual(pos, sorted(pos), f"{f.stem}.{name}: stops out of order")
                for _, h in stops:
                    self.assertRegex(h, r"^#[0-9a-f]{6}$", f"{f.stem}.{name}")

    def test_layout_places_known_assets(self):
        code, out = run(painted_cli.main, "assets", "--json")
        self.assertEqual(code, 0)
        known = {r["asset"] for r in json.loads(out)}
        for f in (ROOT / "layouts").glob("*.json"):
            lay = json.loads(f.read_text())
            for name, x, y in lay["place"]:
                self.assertIn(name, known, f"{f.stem}: unknown asset {name}")

    def test_ramps_used_by_assets_exist(self):
        src = (ROOT / "bpy" / "assets.py").read_text() + (ROOT / "bpy" / "painter.py").read_text()
        used = set(re.findall(r"toon\('([a-z_]+)'", src)) | set(re.findall(r"g\.ramp\('([a-z_]+)'", src)) \
            | set(re.findall(r"gt\('([a-z_]+)'", src))
        for f in (ROOT / "styles").glob("*.json"):
            ramps = set(json.loads(f.read_text())["ramps"])
            self.assertFalse(used - ramps, f"{f.stem} lacks ramps {sorted(used - ramps)}")


class PaintedCli(unittest.TestCase):
    def test_pixling_lists_the_format(self):
        code, out = run(cli.main, "styles", "--json")
        self.assertEqual(code, 0)
        self.assertIn("painted", {r["format"] for r in json.loads(out)})
        code, out = run(cli.main, "painted", "layouts")
        self.assertEqual(code, 0)
        self.assertIn("hollow_brook", out)
        code, out = run(cli.main, "guide", "painted", "Commands")
        self.assertEqual(code, 0)
        self.assertIn("pixling painted kit", out)


if __name__ == "__main__":
    unittest.main()

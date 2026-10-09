"""Where pixling reads its data and writes its output.

A checkout (styles/ next to pp/) reads and writes in the repo, as it always has. An installed copy reads the styles,
example specs and docs bundled in pp/data/ (pyproject.toml force-includes them in the wheel) and writes into the current
directory, so `pixling build` in a game project leaves out/ in that project. PIXLING_OUT overrides the output root.
"""
from __future__ import annotations

import os
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
CHECKOUT = (REPO / "styles").is_dir() and (REPO / "pp").is_dir()
DATA = REPO if CHECKOUT else Path(__file__).resolve().parent / "data"
OUT_ROOT = Path(os.environ["PIXLING_OUT"]) if os.environ.get("PIXLING_OUT") else (REPO if CHECKOUT else Path.cwd())
OUT = OUT_ROOT / "out"
PACKS = OUT_ROOT / "packs"

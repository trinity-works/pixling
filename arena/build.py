"""Pack the active map into ONE html that opens from disk: the page, the viewer and every picture inlined (data: URIs)."""
from __future__ import annotations

import base64
import html
import json
from pathlib import Path

from . import palette as C

HERE = Path(__file__).resolve().parent
LAYER_PNGS = ("main", "sky", "far", "sea", "corner", "cap", "sway", "occ", "zones")


def _bind():
    global ART, M
    from .maps import active
    M = active()
    ART = M.ART


def data_uri(path: Path) -> str:
    return "data:image/png;base64," + base64.b64encode(Path(path).read_bytes()).decode()


def bundle(out: Path, art: Path = None) -> Path:
    art, out = Path(art or ART), Path(out)
    lj = json.loads((art / "layers.json").read_text())
    names = [k for k in LAYER_PNGS if k in ("main", "sky", "sway", "occ", "zones") or k in lj]
    assets = {k: data_uri(art / f"{k}.png") for k in names}
    view = dict(M.biome.VIEWER, key=M.KEY, name=M.NAME, title=M.TITLE)
    data = dict(level=json.loads((art / "level.json").read_text()), occ=json.loads((art / "occ.json").read_text()),
                layers=lj, pal=C.PAL, map=view)
    page = (HERE / "web" / "index.html").read_text()
    page = page.replace("{{TITLE}}", html.escape(M.TITLE)).replace("{{SUBTITLE}}", html.escape(view["subtitle"]))
    page = page.replace("{{PARTICLES}}", html.escape(view["particles_label"]))
    js = (HERE / "web" / "level.js").read_text() + "\n" + (HERE / "web" / "arena.js").read_text()
    blob = ("<script>window.ARENA_ASSETS=" + json.dumps(assets) + ";\nwindow.ARENA_DATA=" +
            json.dumps(data, separators=(",", ":")) + ";</script>")
    page = page.replace("<!--ARENA_DATA-->", blob).replace("/*ARENA_JS*/", js.replace("</script>", "<\\/script>"))
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(page)
    return out


_bind()

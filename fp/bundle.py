"""The painted view as ONE html file that opens from disk (file://), in a sandboxed frame or served.

`fp build` makes the painted view a static folder (layers/: the page, layers.js, audio.js, the font, scene.json, the
layer PNGs and the walk and depth grids) that needs an http server. bundle() packs that folder into a single page:
    - every file the runtime loads goes into a table of data: URIs (window.__FP_FILES); the runtime's asset() looks
      every fetch and image up in it (web/layers.js), so nothing in the code is rewritten
    - each module script is inlined; the modules it imports are named in the page's import map (layers.html maps
      "fp-audio" to ./audio.js), whose entries become data: modules (a bare name resolves anywhere, even in a srcdoc
      frame, where a relative one can't)
    - CSS url()s that name a file of the folder (the font) become data: URIs
The runtime drops its link to the first-person walk when it runs from the table, and its Look button carries the walk
over a reload in the URL, or in sessionStorage where the URL can't hold a query.
"""
from __future__ import annotations

import base64
import json
import mimetypes
import re
from pathlib import Path

MIME = {".png": "image/png", ".json": "application/json", ".bin": "application/octet-stream", ".woff2": "font/woff2",
        ".js": "text/javascript", ".css": "text/css"}
CODE = {"index.html"}                       # the page itself; its module scripts are inlined, not tabled
MODULE_TAG = re.compile(r'<script type="module" src="([^"]+)"></script>')
IMPORT_MAP = re.compile(r'<script type="importmap">(.*?)</script>', re.S)
CSS_URL = re.compile(r'''url\(\s*["']?([^"')]+)["']?\s*\)''')


def data_uri(path: Path) -> str:
    mime = MIME.get(path.suffix) or mimetypes.guess_type(path.name)[0] or "application/octet-stream"
    return "data:%s;base64,%s" % (mime, base64.b64encode(path.read_bytes()).decode())


def _script(js: str) -> str:
    return js.replace("</script", "<\\/script")


def bundle(folder: Path, out: Path) -> dict:
    """pack the built painted view in `folder` (<root>/layers) into the single page `out`. Returns what went in:
    {"table": [paths], "modules": [paths inlined], "imports": {specifier: path}, "bytes": size}"""
    folder, out = Path(folder), Path(out)
    page = (folder / "index.html").read_text()
    modules = MODULE_TAG.findall(page)
    if not modules:
        raise SystemExit("fp bundle: %s has no module script to inline" % (folder / "index.html"))
    im = IMPORT_MAP.search(page)
    imap = json.loads(im.group(1)) if im else {"imports": {}}
    imports = {spec: u[2:] if u.startswith("./") else u                    # relative to the page
               for spec, u in imap["imports"].items() if not re.match(r"^(data:|https?:|/)", u)}
    inlined = set(modules) | set(imports.values())
    files = sorted(p.relative_to(folder).as_posix() for p in folder.rglob("*") if p.is_file())
    css = {u for u in CSS_URL.findall(page) if not re.match(r"^(data:|https?:|#)", u)}
    table = {f: data_uri(folder / f) for f in files if f not in CODE and f not in inlined and f not in css}

    def css_url(m):
        u = m.group(1)
        return 'url("%s")' % data_uri(folder / u) if u in css else m.group(0)
    page = CSS_URL.sub(css_url, page)
    imap["imports"].update({spec: data_uri(folder / path) for spec, path in imports.items()})
    head = ('<script>window.__FP_FILES = %s;</script>\n' % json.dumps(table, separators=(",", ":"))
            + '<script type="importmap">%s</script>' % json.dumps(imap))
    if im:
        page = IMPORT_MAP.sub(lambda _: head, page, count=1)
    else:
        first = MODULE_TAG.search(page).start()
        page = page[:first] + head + "\n" + page[first:]

    def inline(m):
        return '<script type="module">\n%s\n</script>' % _script((folder / m.group(1)).read_text())
    page = MODULE_TAG.sub(inline, page)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(page)
    return dict(table=sorted(table), modules=modules, imports=imports, css=sorted(css), bytes=out.stat().st_size)

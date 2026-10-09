"""CLI: python3 -m painted <command> ...   (also `pixling painted <command>`)

  kit [assets ...] [--style S] [--layout L] [--out D]   Blender -> every asset as a sprite (+ shadow, sway, 8 headings)
  compose [--layout L] [--kit D] [--out D]              lay the layout out from the sprites: scene.png, scene.mp4, kit sheet
  game [--layout L] [--kit D] [--out D] [--pixel DIR]   walkable web scene (index.html + data.json + a/); pp sprites optional
  serve [--layout L] [--port 8765]                      serve the built game over http and open it (file:// can't load it)
  hilltop [--size WxH] [--pixel] [--frames N] [--out P] the perspective film shot (one hero tree over a valley)
  assets                                                what kit can build, by kind
  styles | layouts                                      what is in painted/styles and painted/layouts
  doctor                                                is Blender here (PIXLING_BLENDER overrides the search)

Outputs default to out/painted/<layout>/{kit,scene,game} (out/painted/hilltop for the film shot).
"""
from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
BPY = HERE / "bpy"


def _out_root() -> Path:
    try:
        from pp.paths import OUT
    except ImportError:   # painted runs without pp too
        OUT = Path.cwd() / "out"
    return OUT / "painted"


def _named(kind: str, name: str) -> Path:
    """a style or layout by name (painted/<kind>/<name>.json) or by path."""
    p = Path(name)
    if p.suffix == ".json" and p.exists():
        return p
    q = HERE / kind / f"{name}.json"
    if not q.exists():
        have = ", ".join(sorted(f.stem for f in (HERE / kind).glob("*.json")))
        sys.exit(f"painted: no {kind[:-1]} '{name}' (have: {have})")
    return q


def blender() -> str | None:
    """PIXLING_BLENDER, then the usual macOS / Linux / Windows install places, then PATH."""
    cands = [os.environ.get("PIXLING_BLENDER"), os.environ.get("BLENDER"),
             str(Path.home() / "Applications/Blender.app/Contents/MacOS/Blender"),
             "/Applications/Blender.app/Contents/MacOS/Blender", shutil.which("blender"),
             *sorted(map(str, Path("C:/Program Files/Blender Foundation").glob("Blender*/blender.exe")), reverse=True)]
    return next((c for c in cands if c and Path(c).exists()), None)


def _run_blender(script: str, args: list[str]) -> int:
    b = blender()
    if not b:
        sys.exit("painted: Blender not found. Install Blender 4.2+ or set PIXLING_BLENDER=/path/to/blender")
    cmd = [b, "-b", "--factory-startup", "-P", str(BPY / script), "--", *args]
    p = subprocess.run(cmd, capture_output=True, text=True)
    log = p.stdout + p.stderr
    for line in log.splitlines():
        if line.startswith("built ") or "Traceback" in line or line.startswith(("Error:", "  File")):
            if "unfreed" not in line:
                print(line)
    if p.returncode or "Traceback" in log:
        print(log[-3000:], file=sys.stderr)
        return 1
    return 0


def _textures(tex: Path):
    subprocess.run([sys.executable, str(HERE / "textures.py"), str(tex)], check=True, capture_output=True)


def cmd_kit(a) -> int:
    style, layout = _named("styles", a.style), _named("layouts", a.layout)
    out = Path(a.out) if a.out else _out_root() / layout.stem / "kit"
    tex = out / "_tex"; _textures(tex)
    code = _run_blender("kit.py", [str(style), str(layout), str(tex), str(out), *a.assets])
    if not code:
        print(f"kit -> {out}")
    return code


def cmd_compose(a) -> int:
    layout = _named("layouts", a.layout)
    kit = Path(a.kit) if a.kit else _out_root() / layout.stem / "kit"
    out = Path(a.out) if a.out else _out_root() / layout.stem / "scene"
    r = subprocess.run([sys.executable, str(HERE / "compose.py"), str(kit), str(out), str(layout), *(["keep"] if a.keep_frames else [])])
    if not r.returncode:
        print(f"scene -> {out}")
    return r.returncode


def cmd_game(a) -> int:
    layout = _named("layouts", a.layout)
    kit = Path(a.kit) if a.kit else _out_root() / layout.stem / "kit"
    out = Path(a.out) if a.out else _out_root() / layout.stem / "game"
    if out.exists():
        shutil.rmtree(out)
    r = subprocess.run([sys.executable, str(HERE / "build_game.py"), str(kit), str(out), str(layout), *a.pixel])
    if not r.returncode:
        print(f"game -> {out}  (serve it over http, e.g. python3 -m http.server -d {out})")
    return r.returncode


def cmd_serve(a) -> int:
    import functools, http.server, threading, webbrowser
    layout = _named("layouts", a.layout)
    root = Path(a.dir) if a.dir else _out_root() / layout.stem / "game"
    if not (root / "index.html").exists():
        sys.exit(f"painted: no game in {root}; run `pixling painted game` first")
    class Quiet(http.server.SimpleHTTPRequestHandler):
        def log_message(self, *args):   # no per-request lines
            pass
    handler = functools.partial(Quiet, directory=str(root))
    srv = http.server.ThreadingHTTPServer(("127.0.0.1", a.port), handler)
    url = f"http://127.0.0.1:{a.port}/"
    print(f"serving {root} at {url}  (Ctrl+C stops)")
    if not a.no_open:
        threading.Timer(.4, lambda: webbrowser.open(url)).start()
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        pass
    return 0


def cmd_hilltop(a) -> int:
    w, h = (int(v) for v in a.size.split("x"))
    root = _out_root() / "hilltop"
    out = Path(a.out) if a.out else root / (("pixel" if a.pixel else "hd") + ("_loop" if a.frames else ".png"))
    out.parent.mkdir(parents=True, exist_ok=True)
    if a.frames:
        out.mkdir(parents=True, exist_ok=True)
    tex = root / "_tex"; _textures(tex)
    code = _run_blender("hilltop.py", [str(tex), str(out), str(w), str(h), "pixel" if a.pixel else "hd", str(a.frames)])
    if not code:
        print(f"hilltop -> {out}")
    return code


def cmd_assets(a) -> int:
    import ast
    src = (BPY / "assets.py").read_text()
    tree = ast.parse(src)
    docs = {n.name: (ast.get_docstring(n) or "").split("\n")[0] for n in tree.body if isinstance(n, ast.FunctionDef)}
    kinds = {}
    for n in tree.body:   # TREES = dict(oak=oak, ...) etc.
        if isinstance(n, ast.Assign) and isinstance(n.value, ast.Call) and getattr(n.value.func, "id", "") == "dict":
            kinds[n.targets[0].id] = {k.arg: getattr(k.value, "id", "") for k in n.value.keywords}
    rows = [{"asset": name, "kind": kind.lower(), "about": docs.get(fn, "")}
            for kind, m in kinds.items() for name, fn in m.items()] + [{"asset": "ground", "kind": "plate",
                                                                        "about": "the layout's painted ground"}]
    if a.json:
        print(json.dumps(rows, indent=1))
    else:
        print("\n".join("  %-10s %-10s %s" % (r["asset"], r["kind"], r["about"]) for r in rows))
    return 0


def _list(kind: str, a) -> int:
    rows = []
    for f in sorted((HERE / kind).glob("*.json")):
        d = json.loads(f.read_text())
        rows.append({"name": f.stem, "about": d.get("about", ""),
                     **({"ramps": len(d.get("ramps", {})), "camera": d.get("camera")} if kind == "styles"
                        else {"places": len(d.get("place", []))})})
    if a.json:
        print(json.dumps(rows, indent=1))
    else:
        print("\n".join("  %-14s %s" % (r["name"], r["about"]) for r in rows))
    return 0


def cmd_doctor(a) -> int:
    b = blender()
    ver = ""
    if b:
        r = subprocess.run([b, "-b", "--factory-startup", "--version"], capture_output=True, text=True)
        ver = (r.stdout.splitlines() or [""])[0]
    rows = {"blender": b or None, "version": ver, "ok": bool(b)}
    if a.json:
        print(json.dumps(rows))
    else:
        print(f"  {'ok ' if b else 'MISSING'} Blender  {ver or 'install Blender 4.2+ or set PIXLING_BLENDER'}  {b or ''}")
    return 0 if b else 1


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="painted", description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    k = sub.add_parser("kit"); k.add_argument("assets", nargs="*")
    for p in (k,):
        p.add_argument("--style", default="painted_cards")
    for p in (k, c := sub.add_parser("compose"), g := sub.add_parser("game")):
        p.add_argument("--layout", default="hollow_brook"); p.add_argument("--out")
    for p in (c, g):
        p.add_argument("--kit")
    c.add_argument("--keep-frames", action="store_true", help="keep the 120 PNG frames next to scene.mp4")
    g.add_argument("--pixel", action="append", default=[], help="a pp sprite dir (out/<name>) to walk the scene too")
    sv = sub.add_parser("serve")
    sv.add_argument("--layout", default="hollow_brook"); sv.add_argument("--dir"); sv.add_argument("--port", type=int, default=8765)
    sv.add_argument("--no-open", action="store_true")
    h = sub.add_parser("hilltop")
    h.add_argument("--size", default="1280x720"); h.add_argument("--pixel", action="store_true")
    h.add_argument("--frames", type=int, default=0); h.add_argument("--out")
    for name in ("assets", "styles", "layouts", "doctor"):
        sub.add_parser(name).add_argument("--json", action="store_true")
    a = ap.parse_args(argv)
    return {"kit": cmd_kit, "compose": cmd_compose, "game": cmd_game, "hilltop": cmd_hilltop, "serve": cmd_serve, "assets": cmd_assets,
            "styles": lambda a: _list("styles", a), "layouts": lambda a: _list("layouts", a), "doctor": cmd_doctor}[a.cmd](a)


if __name__ == "__main__":
    sys.exit(main())

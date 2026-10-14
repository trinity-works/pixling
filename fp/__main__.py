"""CLI: python3 -m fp <command> ...   (also `pixling fp <command>`)

  build [--layout L] [--style S] [--root D]         kit + layout -> a playable folder (default out/fp/<layout>)
  walk  [--layout L] [--t 0,6,12,...] [--out D]     build, then screenshots along the auto-walk + walk_sheet.png
  cards [MESH ...] [--yaws 25,145,265] [--out D]    build, then each asset alone on snow, from a few angles
  shot  QUERY [QUERY ...] [--out D]                 build, then one screenshot per runtime query (e.g. "t=9&look=20,-5")
  film  [--t0 S] [--seconds S] [--fps N]            build, then frames stepped through the runtime -> mp4 (judge motion)
  serve [--layout L] [--port 8770]                  serve the built folder (browsers can't load it from file://)
  bundle [--layout L] [--out FILE]                  build, then the painted view as ONE html that opens from disk
                                                    (every asset inlined; default <root>/<layout>.html)
  layers [--t 0,8,16,24] [look=pixel] [nofx=1]     build, then stills of the painted third-person view (out/.../layers/)
  paint [force] [--out WORK]                        re-render the painted view into fp/art/<layout> (needs
                                                    FP_BLENDER=blender or FP_BPY=python-with-bpy; ~4 min, cached)
  assets | styles | layouts                         what exists

Every command takes --root DIR (the build folder; parallel sessions each use their own) and --no-build.
Screenshots use Playwright's headless Chromium (software WebGL); --size WxH sets the viewport (default 1280x720).
--page layers/index.html points shot and film at the painted view instead of the first-person one.
Runtime queries: t=SECONDS (auto-walk time), pause=1, nofx=1 (no snow or particles); first person: look=YAW,PITCH,
card=MESH&yaw=&pitch=&dist=, h=PIXELS, motion=full|gentle|off, debug=shadow; painted view: look=pixel.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent


def _size(s):
    w, h = s.lower().split("x")
    return int(w), int(h)


def main(argv=None):
    ap = argparse.ArgumentParser(prog="fp", description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("cmd", choices=["build", "walk", "cards", "shot", "film", "serve", "bundle", "layers", "paint", "assets",
                                    "styles", "layouts"])
    ap.add_argument("rest", nargs="*")
    ap.add_argument("--layout", default="first_snow")
    ap.add_argument("--style", default="hushfall")
    ap.add_argument("--out", default=None, help="where screenshots go (default: <root>_review); bundle: the html file")
    ap.add_argument("--root", default=None, help="build folder (default out/fp/<layout>); give each agent its own")
    ap.add_argument("--t", default="0,6,12,18,24,30,36,44")
    ap.add_argument("--yaws", default="25,145,265")
    ap.add_argument("--pitch", type=int, default=8)
    ap.add_argument("--size", default="1280x720")
    ap.add_argument("--t0", type=float, default=0.0)
    ap.add_argument("--seconds", type=float, default=8.0)
    ap.add_argument("--fps", type=int, default=15)
    ap.add_argument("--port", type=int, default=8770)
    ap.add_argument("--no-build", action="store_true", help="reuse the last build")
    ap.add_argument("--page", default="walk.html", help="page under the build folder (walk.html = first person, layers/index.html = the painted view)")
    a = ap.parse_args(argv)

    if a.cmd == "assets":
        from .kit import describe
        for k, v in describe().items():
            print("%-12s %s" % (k, v))
        return 0
    if a.cmd == "styles":
        for f in sorted((HERE / "styles").glob("*.json")):
            print(f.stem)
        return 0
    if a.cmd == "layouts":
        for f in sorted((HERE / "layouts").glob("*.py")):
            if not f.stem.startswith("_"):
                print(f.stem)
        return 0

    from .build import _default_out, build
    root = Path(a.root) if a.root else _default_out(a.layout)
    if a.cmd == "paint":
        from . import paint3d, place
        if a.layout != place.NAME:
            raise SystemExit("fp paint: the painted place (fp/place.py) is %s, not %s" % (place.NAME, a.layout))
        work = Path(a.out) if a.out else root.parent / (root.name + "_paint")
        paint3d.paint(work, force="force" in a.rest)
        print("fp paint: ->", paint3d.ART)
        return 0
    if a.cmd == "serve":
        if not (root / "world.json").exists():
            build(a.layout, a.style, root)
        from .shot import serve
        srv = serve(root, a.port)
        print("fp: http://127.0.0.1:%d/  (Ctrl-C to stop)" % srv.server_address[1])
        try:
            import time
            while True:
                time.sleep(3600)
        except KeyboardInterrupt:
            srv.shutdown()
        return 0
    if a.cmd == "bundle":
        from .build import painted_art
        if not painted_art(a.layout):
            raise SystemExit("fp bundle: %s has no painted view (fp/art/%s/, made by `fp paint`)" % (a.layout, a.layout))
    if not a.no_build or not (root / "world.json").exists():
        build(a.layout, a.style, root)
    if a.cmd == "build":
        return 0
    if a.cmd == "bundle":
        from .bundle import bundle
        out = Path(a.out) if a.out else root / ("%s.html" % a.layout)
        info = bundle(root / "layers", out)
        print("fp bundle: %s  (%.1f MB: %d files inlined, %s as modules)" % (
            out, info["bytes"] / 1e6, len(info["table"]) + len(info["css"]),
            ", ".join(info["modules"] + sorted(info["imports"].values()))))
        return 0
    from . import shot
    out = Path(a.out) if a.out else root.parent / (root.name + "_review")
    size = _size(a.size)
    if a.cmd == "film":
        log, mp4 = shot.film(root, out, a.t0, a.seconds, a.fps, size, "&".join(a.rest), page=a.page)
        print(log.strip())
        print("fp: film ->", mp4)
        return 0
    if a.cmd == "layers":
        out.mkdir(parents=True, exist_ok=True)
        ts = [t for t in a.t.split(",") if t] if a.t != ap.get_default("t") else ["0", "8", "15", "26"]
        shots = [{"query": "t=%s&pause=1" % t + "".join("&" + q for q in a.rest), "out": str(out / ("layers_t%02d.png" % int(float(t))))} for t in ts]
        log = shot.shoot(root, shots, size, page="layers/index.html")
        s = shot.sheet([x["out"] for x in shots], out / "layers_sheet.png", cols=2, labels=["t=%ss" % t for t in ts], width=640)
        print(log.strip())
        print("fp: sheet ->", s)
        return 0
    if a.cmd == "walk":
        log, s = shot.walk_shots(root, out, times=[t for t in a.t.split(",") if t], size=size)
    elif a.cmd == "cards":
        import json
        world = json.loads((root / "world.json").read_text())
        meshes = a.rest or [k for k in world["meshes"] if k not in ("terrain", "slabs")]
        log, s = shot.card_shots(root, out, meshes, yaws=[int(y) for y in a.yaws.split(",")], pitch=a.pitch,
                                 size=(size[1], size[1]))
    else:
        out.mkdir(parents=True, exist_ok=True)
        shots = [{"query": q, "out": str(out / ("shot_%02d.png" % i))} for i, q in enumerate(a.rest)]
        log = shot.shoot(root, shots, size, page=a.page)
        s = shot.sheet([x["out"] for x in shots], out / "shot_sheet.png", cols=2, labels=a.rest, width=800)
    print(log.strip())
    print("fp: sheet ->", s)
    return 0


if __name__ == "__main__":
    sys.exit(main())

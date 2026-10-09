"""Rebuild everything in the vista style, in order.

  python3 tools/vista/build.py            # kits -> builds -> layouts -> maps
  python3 tools/vista/build.py --maps     # only re-lay and re-render the maps (after editing a layout)

Kits write specs (specs/vista/, streets/, world/); pp builds them into out/<name>; the layouts write
the map specs; pp.map renders them (GIF for the showcase maps, --layers for the engine export).
"""
import glob, os, subprocess, sys
ROOT = os.path.normpath(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".."))
HERE = os.path.dirname(os.path.abspath(__file__))


def run(*cmd):
    print("+", " ".join(cmd))
    subprocess.run(cmd, cwd=ROOT, check=True)


def main():
    py = sys.executable
    if "--maps" not in sys.argv:
        for kit in ("aerial", "streets", "world"):
            run(py, os.path.join(HERE, kit + ".py"))
        specs = [f for d in ("specs/vista", "specs/vista/streets", "specs/vista/world")
                 for f in sorted(glob.glob(os.path.join(ROOT, d, "*.json"))) if not f.endswith(".map.json")]
        for f in specs:
            subprocess.run([py, "-m", "pp", "build", f], cwd=ROOT, check=True, stdout=subprocess.DEVNULL)
        print(f"built {len(specs)} specs")
    for lay in ("layout_vale", "layout_hub", "layout_town", "layout_streets"):
        run(py, os.path.join(HERE, lay + ".py"))
    run(py, "-m", "pp.map", "specs/vista/highgate.map.json")
    run(py, "-m", "pp.map", "specs/vista/highgate_streets.map.json")
    run(py, "-m", "pp.map", "specs/vista/highgate_town.map.json")
    run(py, "-m", "pp.map", "specs/vista/world/vale.map.json", "--layers")
    run(py, "-m", "pp.map", "specs/vista/highgate_hub.map.json", "--layers")


if __name__ == "__main__":
    main()

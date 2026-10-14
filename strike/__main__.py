"""CLI: pixling strike <command> ...   (= python3 -m strike)

  pose <manifest.json> --clip attack            a pixling sprite manifest: cell, anchor, facings, the "hit" frame and
                                                its parts map (`pixling build --maps parts`) when it has one
  pose <sheet.png> --cell 512[x512] --pivot X,Y --rows se,sw,ne,nw [--hit N] [--walk]   any sheet
      -> <sheet>.pose.json (per facing, per frame: tip, grip, feet; the hurtbox; stride_px with --walk)
         <sheet>.pose.png  (review: blade grip -> tip in yellow, the tip in red, the feet in green)
  reach <attack.pose.json> <idle.pose.json> --scale K --ppm P [--yscale Y] [--stop M]
      -> per facing, the ground distances (m) where the contact frame's blade crosses a same-size defender's hurtbox;
         with --stop, exit 1 when that distance falls outside the band in any facing
  sample [DIR]                                  copy the example warrior (attack, idle, walk) to DIR and print
                                                the commands that measure it (default DIR: ./strike_sample)
pose and reach take --json (one object on stdout, for agents and CI).
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


def _cell(s):
    w, _, h = s.lower().partition("x")
    return int(w), int(h or w)


def _from_manifest(path, clip):
    """cell, pivot, rows, sheet, hit frame and walk flag of one clip in a pixling sprite manifest (`pixling build`)."""
    m = json.loads(Path(path).read_text())
    clips = m.get("clips") or {}
    if clip not in clips:
        raise SystemExit(f"{path}: no clip {clip!r}; clips: {', '.join(clips) or 'none'}")
    c = clips[clip]
    hits = [i for i, f in enumerate(c.get("frames", [])) if f.get("event") == "hit"]
    parts = c.get("maps", {}).get("parts")
    return dict(sheet=Path(path).parent / c["sheet"], cell=(m["frame_w"], m["frame_h"]), pivot=tuple(m["anchor"]),
                rows=[d.lower() for d in m["directions"]], frames=len(c.get("frames", [])) or None,
                hit=hits[0] if hits else None, walk=c.get("speed_px_per_cycle", 0) > 0,
                parts=Path(path).parent / parts if parts else None, legend=m.get("parts"))


SAMPLE_CMDS = """pixling strike pose {d}/warrior_attack.png --cell 256 --pivot 128,189.5 --rows se --hit 3
pixling strike pose {d}/warrior_idle.png   --cell 256 --pivot 128,189.5 --rows se
pixling strike pose {d}/warrior_walk.png   --cell 256 --pivot 128,189.5 --rows se --walk
pixling strike reach {d}/warrior_attack.pose.json {d}/warrior_idle.pose.json --scale 1.17 --ppm 40 --yscale 0.74 --stop 2.3"""


def _sample(d: Path) -> int:
    """The example warrior from strike/sample (painted, one facing, 256 px cells; the attack lands on frame 3)."""
    import shutil
    d.mkdir(parents=True, exist_ok=True)
    for f in sorted((Path(__file__).resolve().parent / "sample").glob("*.png")):
        shutil.copy(f, d / f.name)
    print(f"-> {d}/ (warrior_attack.png, warrior_idle.png, warrior_walk.png)\nmeasure it:\n" + SAMPLE_CMDS.format(d=d))
    return 0


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="pixling strike", description="melee hits that land where the art paints them")
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("pose", help="measure the weapon, the feet and the hurtbox in every frame")
    p.add_argument("sheet", help="a sprite sheet .png, or a pixling sprite manifest .json (with --clip)")
    p.add_argument("--clip", help="manifest: the clip to measure (attack, idle, walk, ...)")
    p.add_argument("--cell", type=_cell, help="cell size in px: 512 or 56x52")
    p.add_argument("--pivot", help="x,y of the feet point inside a cell (px)")
    p.add_argument("--rows", help="the facing of each sheet row, e.g. se,sw,ne,nw")
    p.add_argument("--frames", type=int, help="frames per row (default: sheet width / cell width)")
    p.add_argument("--hit", type=int, help="0-based contact frame of an attack")
    p.add_argument("--walk", action="store_true", help="also measure the stride per facing")
    p.add_argument("--body", type=float, help="body height in cell px (default: the first frame's)")
    p.add_argument("--parts", help="a parts map on the sheet's grid (weapon, arm, legs, body colours): exact parts")
    p.add_argument("--thin", type=float, default=0.04, help="weapon thickness limit, a fraction of body height (default 0.04)")
    p.add_argument("--no-model", action="store_true", help="feet from the silhouette even with rtmlib installed")
    p.add_argument("--out", help="output path stem (default: beside the sheet)")
    p.add_argument("--json", action="store_true")
    r = sub.add_parser("reach", help="the ground distances where the contact blade crosses a defender's hurtbox")
    r.add_argument("attack", help="the attack's .pose.json (measured with a hit frame)")
    r.add_argument("idle", help="the idle's .pose.json (its hurtbox)")
    r.add_argument("--scale", type=float, required=True, help="screen px per cell px at the game's draw size")
    r.add_argument("--ppm", type=float, required=True, help="screen px per ground metre, across")
    r.add_argument("--yscale", type=float, default=1.0, help="depth foreshortening of the ground (1 = top-down)")
    r.add_argument("--stop", type=float, help="the melee stop distance (m); exit 1 when it falls outside the band")
    r.add_argument("--json", action="store_true")
    s = sub.add_parser("sample", help="copy the example warrior and print the commands that measure it")
    s.add_argument("dir", nargs="?", default="strike_sample")
    a = ap.parse_args(argv)
    if a.cmd == "sample":
        return _sample(Path(a.dir))

    from . import measure
    quiet = (lambda *_: None) if a.json else print
    if a.cmd == "pose":
        if a.sheet.endswith(".json"):
            if not a.clip:
                raise SystemExit("a manifest needs --clip NAME")
            kw = _from_manifest(a.sheet, a.clip)
            kw["hit"] = a.hit if a.hit is not None else kw["hit"]
            kw["walk"] = a.walk or kw["walk"]
            if a.out is None:
                a.out = str(Path(kw["sheet"]).with_suffix(""))
        else:
            if not (a.cell and a.pivot and a.rows):
                raise SystemExit("a sheet needs --cell, --pivot and --rows (or pass a pixling manifest .json with --clip)")
            kw = dict(sheet=a.sheet, cell=a.cell, pivot=tuple(float(v) for v in a.pivot.split(",")),
                      rows=a.rows.split(","), frames=a.frames, hit=a.hit, walk=a.walk, parts=a.parts)
        res = measure.pose(kw.pop("sheet"), body=a.body, use_model=not a.no_model, out=a.out, thin=a.thin, log=quiet, **kw)
        png = res["json"][:-len(".json")] + ".png"
        if a.json:
            print(json.dumps({"json": res["json"], "png": png, "hit_frame": res["hit_frame"], "hurtbox": res["hurtbox"],
                              "stride_px": res.get("stride_px"),
                              "tip_at_contact": {f: k[res["hit_frame"]]["tip"] for f, k in res["pose"].items()}
                              if res["hit_frame"] is not None else None}, indent=1))
        else:
            print(f"-> {res['json']}\n-> {png}  (look at it: blade yellow, tip red, feet green)")
        return 0
    res = measure.reach(a.attack, a.idle, a.scale, a.ppm, a.yscale, a.stop)
    if a.json:
        print(json.dumps(res, indent=1))
    else:
        for f, v in res["facings"].items():
            b = v["band"]
            note = "" if a.stop is None else ("  stop %.2f m inside" % a.stop if v["fits"] else "  stop %.2f m OUTSIDE" % a.stop)
            print(f"  {f}: " + (f"blade crosses the hurtbox at {b[0]}-{b[1]} m" if b else "no blade on the contact frame") + note)
    return 0 if res["ok"] else 1


if __name__ == "__main__":
    sys.exit(main())

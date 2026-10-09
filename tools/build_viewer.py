"""Build viewer/: an HTML showroom that animates every pack asset from its real 1x sheets.

python3 tools/build_viewer.py   -> viewer/index.html + viewer/a/* (open index.html, or publish the folder)
"""
from __future__ import annotations

import json
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from pp.color import rgb_to_hex  # noqa: E402
from pp.forge import load_style  # noqa: E402

PACKS = [
    {"id": "hollow_court", "title": "The Hollow Court", "style": "duskborne", "accent": "#ff76c4", "use_bg": True,
     "blurb": "Dark-fantasy enemy pack. Deep desaturated bodies, near-black ink, one glowing accent per "
              "character, and a crimson rag on every member of the Court."},
    {"id": "meadowfolk", "title": "Meadowfolk", "style": "sunmeadow", "accent": "#b8e06a",
     "blurb": "Cozy top-down village pack. Warm saturated mid-tones, coloured edges instead of black "
              "outlines, animals and a grove of trees at matching scale."},
    {"id": "ember_spirits", "title": "Ember Spirits", "style": "vermilion", "accent": "#dc4a2c", "use_bg": True,
     "blurb": "Folk-print spirits in three inks: warm black, vermilion and bone on cream paper. Black masses "
              "carry the silhouettes, red carries the markings, and hits splatter ink instead of glowing."},
]


def build() -> Path:
    out = ROOT / "viewer"
    if out.exists():
        shutil.rmtree(out)
    (out / "a").mkdir(parents=True)
    data = {"packs": []}
    for pk in PACKS:
        pdir = ROOT / "packs" / pk["id"]
        style = load_style(pk["style"])
        ground = style.ramps.get("ground")
        stage = rgb_to_hex(ground[len(ground) // 2]) if ground and not pk.get("use_bg") else style.spec.get("bg", "#333")
        assets = []
        for jf in sorted((pdir / "sheets").glob("*.json")):
            meta = json.loads(jf.read_text())
            name = meta["name"]
            spec_path = ROOT / "specs" / pk["style"] / (name + ".json")
            spec = json.loads(spec_path.read_text()) if spec_path.exists() else {}
            rig = spec.get("rig") or ("prop" if "generator" in spec else "humanoid")
            if len(meta["directions"]) == 1:
                rig = "prop"
            clips = {}
            for cname, c in meta["clips"].items():
                fn = "%s__%s" % (pk["id"], c["sheet"])
                shutil.copy(pdir / "sheets" / c["sheet"], out / "a" / fn)
                clips[cname] = {"sheet": "a/" + fn, "n": len(c["frames"]), "loop": c["loop"],
                                "ms": [f["ms"] for f in c["frames"]],
                                "events": [f["event"] for f in c["frames"]],
                                "speed": c.get("speed_px_per_cycle", 0)}
            assets.append({"name": name, "label": name.replace("_", " "), "rig": rig,
                           "concept": spec.get("concept", ""), "fw": meta["frame_w"], "fh": meta["frame_h"],
                           "anchor": meta["anchor"], "dirs": meta["directions"], "clips": clips})
        order = {"humanoid": 0, "quadruped": 1, "prop": 2}
        assets.sort(key=lambda a: order.get(a["rig"], 3))
        vfx = []
        for vd in sorted((pdir / "vfx").glob("*")) if (pdir / "vfx").exists() else []:
            m = json.loads((vd / (vd.name + ".json")).read_text())
            fn = "%s__%s.png" % (pk["id"], vd.name)
            shutil.copy(vd / (vd.name + ".png"), out / "a" / fn)
            vfx.append({"name": vd.name, "label": vd.name.split("_", 1)[1].replace("_", " "), "kind": m["kind"],
                        "n": m["frames"], "fw": m["frame_w"], "fh": m["frame_h"], "sheet": "a/" + fn})
        scene = "a/%s__preview.png" % pk["id"]
        shutil.copy(pdir / "preview.png", out / scene)
        pal = [rgb_to_hex(c) for c in style.palette()]
        data["packs"].append({**pk, "stage": stage, "bg": style.spec.get("bg"), "assets": assets, "vfx": vfx,
                              "scene": scene, "palette": pal, "about": style.spec.get("about", "")})
    sys.path.insert(0, str(ROOT / "tools"))
    from export_3d import export_all
    names = {pk["style"]: [a["name"] for a in p["assets"]] for pk, p in zip(PACKS, data["packs"])}
    models = export_all(names)
    html = (ROOT / "tools" / "viewer_template.html").read_text()
    html = html.replace("/*__DATA__*/null", json.dumps(data, separators=(",", ":")))
    html = html.replace("/*__MODELS__*/null", json.dumps(models, separators=(",", ":")))
    (out / "index.html").write_text(html)          # published page (host adds the document skeleton)
    (out / "local.html").write_text('<!doctype html><html lang="en"><head><meta charset="utf-8">'
                                    '<meta name="viewport" content="width=device-width, initial-scale=1">'
                                    '</head><body>' + html + '</body></html>')
    return out


if __name__ == "__main__":
    o = build()
    n = sum(1 for _ in (o / "a").iterdir())
    print("viewer ->", o / "index.html", "(%d asset files)" % n)

"""Build the style explorer: one self-contained HTML page where you walk an animal around every built scene of the
launch styles (Vista, Crisp Tactics, Flat Minimal) and switch style, scene and hour.

  python3 tools/tactics/build.py && python3 tools/flat/build.py     # the scenes and animal sheets it reads
  python3 tools/explorer/build.py                                   # -> out/explorer.html

Everything is read from out/ (Vista falls back to docs/img when its maps aren't built) and embedded at 1x as data
URIs; the page scales by whole numbers only. Scenes that aren't built are skipped with a note.
"""
import base64
import io
import json
import sys
from pathlib import Path

from PIL import Image, ImageSequence

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "out"


def png_uri(im):
    b = io.BytesIO()
    im.save(b, "PNG", optimize=True)
    return "data:image/png;base64," + base64.b64encode(b.getvalue()).decode()


def image(path: Path, div=1):
    """A still or an animated gif at 1x; `div` downsamples an integer-scaled render with nearest neighbour."""
    im = Image.open(path)
    if getattr(im, "n_frames", 1) == 1:
        im = im.convert("RGBA")
        if div > 1:
            im = im.resize((im.width // div, im.height // div), Image.NEAREST)
        return dict(src=png_uri(im), w=im.width, h=im.height)
    if div == 1:
        return dict(src="data:image/gif;base64," + base64.b64encode(path.read_bytes()).decode(), w=im.width,
                    h=im.height)
    frames, durs = [], []
    for f in ImageSequence.Iterator(im):
        frames.append(f.convert("RGBA").resize((im.width // div, im.height // div), Image.NEAREST))
        durs.append(f.info.get("duration", im.info.get("duration", 100)))
    b = io.BytesIO()
    frames[0].save(b, "GIF", save_all=True, append_images=frames[1:], duration=durs, loop=0, disposal=2)
    return dict(src="data:image/gif;base64," + base64.b64encode(b.getvalue()).decode(), w=frames[0].width,
                h=frames[0].height)


def sheet(name, clip="walk"):
    """An 8-direction sheet from out/<name>/ (rows = directions, columns = frames)."""
    d = OUT / name
    meta = json.loads((d / (name + ".json")).read_text())
    clip = clip if clip in meta["clips"] else next(iter(meta["clips"]))
    im = Image.open(d / ("%s_%s.png" % (name, clip))).convert("RGBA")
    fw, fh = meta["frame_w"], meta["frame_h"]
    return dict(src=png_uri(im), fw=fw, fh=fh, ax=meta["anchor"][0], ay=meta["anchor"][1], cols=im.width // fw,
                rows=im.height // fh, ms=meta["clips"][clip]["frames"][0]["ms"])


def first(*paths):
    return next((p for p in paths if p.exists()), None)


def scene(name, img, start, animal=None, hours=(), note=""):
    """img and hour images are (path, div) or None; returns None when the scene isn't built."""
    if img is None or img[0] is None:
        print("skip (not built):", name)
        return None
    hrs = [dict(name=n, img=image(*h) if h else None) for n, h in hours if h is None or h[0] is not None]
    return dict(name=name, img=image(*img), start=start, animal=animal, hours=hrs, note=note)


def safe_sheet(name, clip="walk"):
    try:
        return sheet(name, clip)
    except FileNotFoundError:
        print("no sheet:", name)
        return None


def styles():
    vista = [
        # the README loop is the town at 2x; a fresh out/ build is 1x already
        scene("Highgate", (OUT / "highgate_town" / "highgate_town.gif", 1) if (OUT / "highgate_town").exists()
              else (ROOT / "docs" / "img" / "highgate_town.gif", 2), [98, 260],
              note="The town on its hill. Camera only: no animal at this scale."),
        scene("Vale world map", (ROOT / "docs" / "img" / "vale_world.png", 1), [260, 400],
              note="World map with fog regions."),
    ]
    tactics = [
        scene("Green valley", (first(OUT / "tactics_valley" / "noon_1x.gif"), 1), [200, 160], safe_sheet("tactics_stag")),
        scene("Harbour", (first(OUT / "tactics_harbour_valley" / "noon_1x.gif"), 1), [200, 150],
              safe_sheet("tactics_stag")),
        scene("Autumn valley", (first(OUT / "tactics_autumn" / "noon_1x.png"), 1), [200, 160],
              safe_sheet("tactics_stag_autumn")),
        scene("Autumn harbour", (first(OUT / "tactics_harbour_autumn" / "noon_1x.png"), 1), [200, 150],
              safe_sheet("tactics_stag_autumn")),
    ]
    flat = []
    for nm, label, sheet_name in (("flat_forest", "Forest island", "flat_deer"),
                                  ("flat_dunes", "Dunes island", "flat_deer_dunes")):
        d = OUT / nm
        flat.append(scene(label, (first(d / "noon_1x.gif", d / "noon_1x.png"), 1), [128, 90], safe_sheet(sheet_name),
                          hours=[("Noon", None), ("Night", (first(d / "night_1x.png"), 1)),
                                 ("Night + dither", (first(d / "night_dither_1x.png"), 1))]))
    out = [dict(id="vista", name="Vista", tag="Flagship",
                about="Aerial town map. Muted painterly palette, calm value masses, tiny figures.", scenes=vista),
           dict(id="tactics", name="Crisp Tactics", tag="Exact iso, soft line",
                about="Exact 2:1 iso, three face tones, a soft selout line with corner AA, masonry, cube canopies, "
                      "moss and tufts.", scenes=tactics),
           dict(id="flat", name="Flat Minimal", tag="Exact iso, two hues",
                about="Two hues and a warm window accent, flat faces, chunky pixels, one iso camera for map and "
                      "props.", scenes=flat)]
    for s in out:
        s["scenes"] = [x for x in s["scenes"] if x]
    return [s for s in out if s["scenes"]]


def main():
    data = dict(styles=styles())
    if not data["styles"]:
        sys.exit("nothing built yet: run tools/tactics/build.py and tools/flat/build.py first")
    page = (Path(__file__).parent / "template.html").read_text().replace("/*DATA*/null", json.dumps(data))
    OUT.mkdir(exist_ok=True)
    (OUT / "explorer.html").write_text(page)
    print(OUT / "explorer.html", "%d KB" % (len(page) // 1024))


if __name__ == "__main__":
    main()

"""Build the landing page's art into site/a/ from the engine (the page itself is site/index.html, hand-written).

  python3 tools/site.py            # renders states, light, the house steps and the iso styles; copies maps, fx from out/
  python3 tools/site.py pipelines  # one step only (mascot, sheets, states, house_steps, worlds, iso_styles, pipelines, layers)

Renders go to a temp dir; only the final images land in site/a/. Maps, fx and props are read from out/, so build
those first if they are missing (the error names the command). Everything on the page is a real pixling output.
"""
import copy, glob, hashlib, json, os, shutil, subprocess, sys, tempfile
from PIL import Image, ImageSequence

ROOT = os.path.normpath(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
OUT = os.path.join(ROOT, "out")
A = os.path.join(ROOT, "site", "a")
TMP = tempfile.mkdtemp(prefix="pixling_site_")


def pp(*args):
    r = subprocess.run([sys.executable, "-m", "pp", *args], cwd=ROOT, capture_output=True, text=True)
    if r.returncode:
        sys.exit(f"pp {' '.join(args)} failed:\n{r.stderr[-800:]}")
    return r.stdout


def need(path, how):
    if not os.path.exists(path):
        sys.exit(f"missing {os.path.relpath(path, ROOT)}: run `{how}` first")
    return path


def webp(src, dst, down=1):
    frames, durs = [], []
    for f in ImageSequence.Iterator(Image.open(src)):
        g = f.convert("RGB")
        if down > 1:
            g = g.resize((g.width // down, g.height // down), Image.NEAREST)
        frames.append(g)
        durs.append(f.info.get("duration", 100))
    frames[0].save(dst, save_all=True, append_images=frames[1:], duration=durs, loop=0, lossless=True, method=4)


def worlds():
    for name, out_name in [("highgate_hub", "w_harbour"), ("highgate", "w_hill"), ("highgate_town", "w_town")]:
        gif = need(os.path.join(OUT, name, name + ".gif"), f"pixling map specs/vista/{name}.map.json")
        webp(gif, os.path.join(A, out_name + ".webp"))
    shutil.copy(os.path.join(ROOT, "docs", "img", "vale_world.png"), os.path.join(A, "w_vale.png"))
    pp("light", "specs/vista/highgate_hub.map.json", "--builds", "out", "--out", f"{TMP}/hub", "--gif")
    webp(f"{TMP}/hub/light/highgate_hub_day.gif", os.path.join(A, "w_harbour_day.webp"), down=2)
    for h in ["h0", "h1.2", "h2.2", "h3.1", "h4"]:
        shutil.copy(f"{TMP}/hub/light/highgate_hub_{h}.png", os.path.join(A, f"hub_{h}.png"))
    pp("light", "specs/vista/highgate.map.json", "--builds", "out", "--out", f"{TMP}/hill")
    shutil.copy(f"{TMP}/hill/light/highgate_h4.png", os.path.join(A, "w_hill_night.png"))


def iso_styles():
    """Crisp Tactics and Flat Minimal scenes and animals, built by their style scripts (1x; the page scales them)."""
    for tool in ("tactics", "flat"):
        r = subprocess.run([sys.executable, f"tools/{tool}/build.py", "--out", f"{TMP}/iso"], cwd=ROOT,
                           capture_output=True, text=True)
        if r.returncode:
            sys.exit(f"tools/{tool}/build.py failed:\n{r.stderr[-800:]}")
    I = f"{TMP}/iso"
    webp(f"{I}/tactics_valley/noon_1x.gif", os.path.join(A, "w_tac_valley.webp"))
    webp(f"{I}/tactics_harbour_valley/noon_1x.gif", os.path.join(A, "w_tac_harbour.webp"))
    webp(f"{I}/flat_forest/noon_1x.gif", os.path.join(A, "w_flat_forest.webp"))
    for src, dst in [("tactics_autumn/noon_1x.png", "w_tac_autumn.png"), ("flat_dunes/noon_1x.png", "w_flat_dunes.png"),
                     ("flat_forest/night_1x.png", "w_flat_forest_night.png"),
                     ("tactics_stag/tactics_stag_walk.png", "p_tactics_stag.png"),
                     ("flat_heron/flat_heron_idle.png", "p_flat_heron.png")]:
        shutil.copy(f"{I}/{src}", os.path.join(A, dst))


def states():
    for b in ["chapel", "house_5"]:
        pp("states", f"specs/vista/{b}.json", "--out", f"{TMP}/st_{b}")
        for s in ["ruin", "build25", "build50", "build75", "build90", "built"]:
            src = glob.glob(f"{TMP}/st_{b}/{b}~{s}/*_idle.png")[0]
            shutil.copy(src, os.path.join(A, f"st_{b}_{s}.png"))


def house_steps():
    """The house_5 spec written part by part, plus roof edits: each one a real build."""
    base = json.load(open(os.path.join(ROOT, "specs", "vista", "house_5.json")))
    bones = {b["name"]: b for b in base["bones"]}

    def spec(name, walls_parts, roof=False, chimney=False, mat=None, gable=None):
        s = copy.deepcopy(base)
        s["name"] = name
        walls = copy.deepcopy(bones["walls"])
        walls["parts"] = walls["parts"][:walls_parts]
        bl = [bones["root"], walls]
        if roof:
            r = copy.deepcopy(bones["roof"])
            if mat:
                r["parts"][0]["mat"] = mat
            if gable is not None:
                r["parts"][0]["gable"] = gable
            bl.append(r)
        if chimney:
            bl.append(copy.deepcopy(bones["chimney"]))
        s["bones"] = bl
        return s

    steps = {"s1_box": spec("s1_box", 1), "s2_windows": spec("s2_windows", 4), "s3_roof": spec("s3_roof", 4, True),
             "s4_chimney": spec("s4_chimney", 4, True, True),
             "s5_terracotta": spec("s5_terracotta", 4, True, True, "roof"),
             "s6_hip": spec("s6_hip", 4, True, True, "roof", False),
             "s7_slate": spec("s7_slate", 4, True, True, "stone", False),
             "s8_plum_hip": spec("s8_plum_hip", 4, True, True, "roof_plum", False),
             "s9_slate_gable": spec("s9_slate_gable", 4, True, True, "stone", True)}
    shas = {}
    for name, s in steps.items():
        p = f"{TMP}/{name}.json"
        json.dump(s, open(p, "w"), indent=1)
        pp("build", p, "--out", f"{TMP}/steps")
        dst = os.path.join(A, f"b_{name}.png")
        shutil.copy(f"{TMP}/steps/{name}_idle.png", dst)
        shas[name] = hashlib.sha256(open(dst, "rb").read()).hexdigest()
    json.dump(shas, open(os.path.join(A, "shas.json"), "w"), indent=1)


def sheets():
    for n in ["hc_slash", "hc_burst", "hc_lightning", "hc_hit_spark", "hc_eruption", "hc_shockwave", "hc_aura",
              "meadow_leaf_burst", "meadow_fireball", "m_fx_sparkle_gold"]:
        shutil.copy(need(os.path.join(OUT, "fx", n, n + ".png"), f"pixling fx ... --name {n}"), os.path.join(A, f"fx_{n}.png"))
    for n in ["lighthouse"]:
        shutil.copy(need(os.path.join(OUT, n, n + "_idle.png"), f"pixling build specs/<style>/{n}.json"),
                    os.path.join(A, f"p_{n}.png"))


def pipelines():
    """The pipeline cards' art: a spell cut from a kept H3 take (reel fx, no credits) and the painted Hollow Brook scene."""
    take = need(os.path.join(ROOT, "reel", "fx", "takes", "fireball_rain_a.mp4"), "a local H3 take (reel/fx/takes is not committed)")
    r = subprocess.run([sys.executable, "-m", "pp", "reel", "fx", "reel/fx/fireball_rain.json"], cwd=ROOT,
                       capture_output=True, text=True, env={**os.environ, "PIXLING_OUT": f"{TMP}/reel"})
    if r.returncode:
        sys.exit(f"reel fx failed:\n{r.stderr[-800:]}")
    fx = f"{TMP}/reel/out/reel/_fx/fireball_rain"
    sheet = Image.open(f"{fx}/fireball_rain.png")
    meta = json.load(open(f"{fx}/fireball_rain.json"))
    n, fw, fh = meta["frames"], sheet.width // meta["frames"], sheet.height
    sheet.resize((n * fw // 2, fh // 2), Image.LANCZOS).save(os.path.join(A, "pl_reel_fireball.webp"), quality=90)
    frame = os.path.join(TMP, "take.png")                    # one raw frame of the take, as the model sent it
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-ss", "2.6", "-i", take, "-frames:v", "1", "-vf", "scale=-2:192", frame],
                   check=True)
    Image.open(frame).convert("RGB").save(os.path.join(A, "pl_reel_take.webp"), quality=85)
    kit = need(os.path.join(OUT, "painted", "hollow_brook", "scene", "kit_sheet.png"), "pixling painted compose")
    k = Image.open(kit).convert("RGB")
    k.resize((k.width // 2, k.height // 2), Image.LANCZOS).save(os.path.join(A, "pl_painted_kit.webp"), quality=86)
    scene = need(os.path.join(OUT, "painted", "hollow_brook", "scene", "scene.png"), "pixling painted kit && pixling painted compose")
    im = Image.open(scene).convert("RGB")
    im.resize((im.width // 2, im.height // 2), Image.LANCZOS).save(os.path.join(A, "pl_painted.webp"), quality=88)


def layers():
    """The harbour's engine export, for the pipeline stage and the collision tile: base frame + collision channel."""
    pp("map", "specs/vista/highgate_hub.map.json", "--layers", "--builds", "out", "--out", f"{TMP}/hub_layers")
    lay = f"{TMP}/hub_layers/layers"
    import numpy as np                                  # the collision channel, the way a game reads it
    g = np.array(Image.open(f"{lay}/meaning.png"))[..., 1]
    col = np.zeros(g.shape + (3,), np.uint8)
    for v, rgb in {0: (26, 34, 39), 1: (134, 176, 156), 2: (226, 192, 90)}.items():
        col[g == v] = rgb
    Image.fromarray(col).save(os.path.join(A, "r_collision.png"))
    shutil.copy(f"{lay}/base.png", os.path.join(A, "r_base.png"))


def mascot():
    """The hand-placed mascot's idle GIF, keyed to a transparent 1x sheet."""
    im = Image.open(os.path.join(ROOT, "docs", "brand", "pixling-mark-idle.gif"))
    frames = [f.convert("RGBA") for f in ImageSequence.Iterator(im)]
    bg = frames[0].getpixel((0, 0))[:3]
    scale = 10                                                          # tools/brand.py draws the GIF at 10x
    w, h = frames[0].width // scale, frames[0].height // scale
    sheet = Image.new("RGBA", (w * len(frames), h))
    for i, f in enumerate(frames):
        px = [(0, 0, 0, 0) if p[:3] == bg else p for p in f.getdata()]
        f.putdata(px)
        sheet.alpha_composite(f.resize((w, h), Image.NEAREST), (i * w, 0))
    sheet.save(os.path.join(A, "m_mark.png"))
    for f in ["pixling-mark.svg", "pixling-logo-dark.svg", "favicon-32.png"]:
        shutil.copy(os.path.join(ROOT, "docs", "brand", f), os.path.join(A, f))


if __name__ == "__main__":
    os.makedirs(A, exist_ok=True)
    every = (mascot, sheets, states, house_steps, worlds, iso_styles, pipelines, layers)
    for step in [f for f in every if f.__name__ in sys.argv[1:]] or every:
        print(step.__name__)
        step()
    shutil.rmtree(TMP, ignore_errors=True)
    print("site/a:", len(os.listdir(A)), "files")

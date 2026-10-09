"""pixling: one command for every Pixel Perfect tool, shaped for LLM agents (Claude Code, Codex, Cursor...).

pixling is a catalogue: pipelines (docs/PIPELINES.md), styles with their making-of, the taste and research notes, and
the tools that run them. `pixling` with no arguments prints USAGE (below). The sprite-forge commands live in
pp/__main__.py; this module routes them and owns the rest: guide, pipelines, code, styles, specs, new, world, doctor,
agent install, scenario. Results print as
text; --json on the commands an agent parses.
"""
from __future__ import annotations

import argparse
import ast
import json
import re
import shutil
import sys
import time
from pathlib import Path

from .paths import CHECKOUT, DATA as ROOT, REPO

PKG_DIRS = {"pp": Path(__file__).resolve().parent, "reel": Path(__file__).resolve().parent.parent / "reel",
            "painted": Path(__file__).resolve().parent.parent / "painted",
            # the style kits: worked examples an agent can read and copy (shipped in the wheel under pp/data/tools)
            "tactics": ROOT / "tools" / "tactics", "flat": ROOT / "tools" / "flat", "vista": ROOT / "tools" / "vista"}

ENGINE = ("build", "review", "scene", "lint", "silhouettes", "sizes", "materials", "fx", "pack", "inspect",
          "variants", "states", "light", "aseprite", "pixcheck")

# How each launch style was made: its STYLES.md section, the code that draws it, the lab notes, and how to build it.
# Biomes (tactics_autumn, flat_dunes) are the same style in another palette.
STYLE_HOW = {
    "vista": {"section": "Vista", "build": "python3 tools/vista/build.py  (a checkout; writes specs, then maps)",
              "code": ["tools/vista/aerial.py", "tools/vista/streets.py", "tools/vista/world.py",
                       "tools/vista/layout_hub.py", "pp/map.py", "pp/light.py", "pp/states.py", "pp/meaning.py"],
              "notes": ["environments", "style-dna", "taste-layer"]},
    "tactics": {"section": "Crisp Tactics", "build": "pixling world tactics [--only SCENE]",
                "code": ["tools/tactics/kit.py", "tools/tactics/scenes.py", "tools/tactics/build.py", "pp/iso.py",
                         "pp/iso_line.py"],
                "notes": ["proto-tactics", "style-dna", "taste-layer"]},
    "flat": {"section": "Flat Minimal", "build": "pixling world flat [--only SCENE]",
             "code": ["tools/flat/kit.py", "tools/flat/scenes.py", "tools/flat/build.py", "pp/iso.py"],
             "notes": ["proto-flat", "proto-frost", "style-dna", "taste-layer"]},
}
BIOMES = {"tactics_autumn": "tactics", "flat_dunes": "flat"}
WORLDS = {"tactics": "tools/tactics/build.py", "flat": "tools/flat/build.py"}

# topic -> (file, what it answers). Order is the reading order for a new artist agent.
GUIDES = {
    "pipelines": ("docs/PIPELINES.md", "every pipeline: what it makes, steps, code, what we learned"),
    "workflow": ("docs/WORKFLOW.md", "roles, the render pipeline, the artist loop, definition of done"),
    "artist": ("docs/ARTIST.md", "spec format, design rules, motion, styles, VFX, maps: the main manual"),
    "styles": ("docs/STYLES.md", "the launch styles, how a style is made, the shared taste layer"),
    "environments": ("docs/ENVIRONMENTS.md", "living maps: building states, meaning layer, hour lighting, painters"),
    "requests": ("docs/REQUESTS.md", "open artist -> engineer requests"),
    "motion": ("research/motion/NOTES.md", "fluid attacks, locomotion and deaths at 13 fps"),
    "style-search": ("research/styles/README.md", "how the launch styles were found: rounds, prototypes, votes"),
    "style-dna": ("research/styles/round2_DNA.md", "a DNA sheet per style direction: camera, shapes, shading, marks"),
    "taste-layer": ("research/styles/SHARED_LAYER.md", "the shared taste layer, as first written"),
    "style-palettes": ("research/styles/round1_FINDINGS.md", "six palettes on one kit: why a palette is not a style"),
    "proto-tactics": ("research/styles/proto_tactics_v2.md", "Crisp Tactics: exact iso, the soft line, masonry"),
    "proto-flat": ("research/styles/proto_flat_v2.md", "Flat Minimal: exact iso, clean stairs, flat shadows"),
    "proto-frost": ("research/styles/proto_frost_flat_v1.md", "Frost and Flat v1 on SDF + painted maps (superseded)"),
    "proto-saffron": ("research/styles/proto_saffron.md", "Saffron (parked): a thick ink line"),
    "proto-marsh": ("research/styles/proto_marsh.md", "Marsh (parked): painterly clusters"),
    "reel": ("reel/README.md", "video -> sprites engine: layout, char.json, commands"),
    "reel-workflow": ("reel/WORKFLOW.md", "the reel loop step by step: designs, takes, cut, demo"),
    "reel-notes": ("research/reel/NOTES.md", "video model survey and reel research"),
    "painted": ("painted/README.md", "the painterly format: technique, commands, style/layout files, sprite contract"),
    "brand": ("docs/brand/README.md", "pixling name, mascot, logo files, fonts, colours"),
    "scenario": ("research/reel/SCENARIO_SKILL.md", "Scenario API/MCP conventions (parameter shapes, models)"),
}

USAGE = """\
pixling — art know-how and tools for your coding agent (the Pixel Perfect forge).
Pipelines, styles and taste for making game sprites with code: run them, read how they were made, take what helps.

Know-how (start here)
  pixling pipelines [NAME]              spec, blocks, iso, map, fx, video, painted, style: what each makes, steps, code, lessons
  pixling styles [NAME] [--how]         styles and their ramps; --how: the hand, the kit, the code, the lab notes
  pixling guide [TOPIC] [SECTION]       the docs and research notes; --grep WORD searches them all
  pixling code [MODULE]                 engine and kit modules, with docstrings (`pixling code tactics.kit`)
  pixling specs [STYLE]                 example specs to copy from

Pipeline: spec -> sprites (the loop: new -> build -> review -> fix -> scene -> lint)
  pixling new EXAMPLE NAME                     copy an example spec to ./specs/NAME.json
  pixling build SPEC [--clips idle --dirs S,E]     -> out/<name>/ (sheets, gifs, json)
  pixling review out/<name> [--clips --dirs]       zoomed review grid (look at it)
  pixling scene out/<a> out/<b> --style S          side by side at game scale
  pixling lint out/<name> [...]                    quick numeric hints
  pixling inspect SPEC | variants SPEC --vary k=a,b | silhouettes | sizes
  pixling pixcheck PNG [--mark OUT]                pixel cleanliness of a 1x render (orphans, whiskers, stairs)
  pixling pack NAME DIRS --style S | aseprite out/<name>

Pipeline: block tokens (small units and creatures for an iso board; `pixling pipelines blocks`)
  pixling blocks SPEC [SPEC ...] [--lineup PNG] [--on SCENE.png --at X,Y] [--ink HEX]   voxel layers -> exact 2:1
                                        iso clips in 4 rotated facings, cast shadows, hit/cast events

Pipeline: iso scenes (Crisp Tactics, Flat Minimal)
  pixling world tactics|flat [--only SCENE]    a style's scenes + animal sheets, built by its kit
  python3 -m pp.iso SCENE.json --out DIR [--hour night]   re-render a built scene

Pipeline: living maps and effects
  pixling map MAP.json [--still --meaning --layers]
  pixling states SPEC | light MAP.json [--gif]     building states | every hour + light.json
  pixling fx KIND --style S                        VFX sheets in the style's ramp

Pipeline: image -> video -> frames (Scenario + reel; `pixling pipelines video`)
  pixling scenario login [--device]     OAuth sign-in (once per machine); `status`, `logout`, `use`
  pixling scenario tools [WORD]         the server's tools; `schema TOOL` for one tool's inputs
  pixling scenario call TOOL '{json}'   any tool, e.g. models_list, model_schema_get, recommend
  pixling scenario cost|run MODEL PARAMS [--out F]   estimate / generate + download
  pixling scenario upload FILE | download ASSET --out F
  pixling reel split|contact|key|gambit|page|demo|fx ...   key, cut and export the takes

Pipeline: Blender -> painterly frames (not pixel; `pixling pipelines painted`)
  pixling painted kit [assets] [--style --layout]  shadow layers, sway loops, 8 headings
  pixling painted compose | game [--pixel out/X]   a scene from the sprites | a walkable web scene
  pixling painted assets | styles | layouts | doctor | hilltop

Setup
  pixling doctor                        dependencies, ffmpeg, Blender, Scenario sign-in; `pixling --version`
  pixling agent install DIR             skill + AGENTS.md block for another project

Every command takes -h. `python3 -m pp <cmd>` is the same CLI without installing.
"""


def _emit(obj, as_json, text=None):
    if as_json:
        print(json.dumps(obj, indent=1, default=str))
    else:
        print(text if text is not None else obj)


# ---- guide ----------------------------------------------------------------------------------------------------

def _sections(md: str):
    """[(level, title, body)] for every markdown heading (code fences skipped)."""
    out, cur, fence = [], None, False
    for line in md.splitlines():
        if line.startswith("```"):
            fence = not fence
        m = None if fence else re.match(r"^(#{1,4})\s+(.*)", line)
        if m:
            cur = [len(m.group(1)), m.group(2).strip(), []]
            out.append(cur)
        elif cur:
            cur[2].append(line)
    return [(lv, t, "\n".join(b).strip()) for lv, t, b in out]


def cmd_guide(a):
    if a.grep:
        rx = re.compile(a.grep, re.I)
        hits = []
        for topic, (f, _) in GUIDES.items():
            p = ROOT / f
            if not p.exists():
                continue
            sect = ""
            for i, line in enumerate(p.read_text().splitlines(), 1):
                if line.startswith("#"):
                    sect = line.lstrip("# ").strip()
                if rx.search(line):
                    hits.append({"topic": topic, "section": sect, "line": i, "text": line.strip()[:200]})
        _emit(hits, a.json, "\n".join("%s / %s:%d  %s" % (h["topic"], h["section"], h["line"], h["text"])
                                     for h in hits) or "no matches")
        return 0
    if not a.topic:
        rows = [{"topic": t, "file": f, "about": d, "exists": (ROOT / f).exists()} for t, (f, d) in GUIDES.items()]
        _emit(rows, a.json, "\n".join("  %-14s %s  (%s)" % (r["topic"], r["about"], r["file"])
                                     for r in rows if r["exists"]) +
              "\n\n`pixling guide TOPIC` prints it; `pixling guide TOPIC --toc` lists sections; "
              "`pixling guide TOPIC \"Section\"` prints one.")
        return 0
    if a.topic not in GUIDES:
        raise SystemExit("unknown topic %r; one of: %s" % (a.topic, ", ".join(GUIDES)))
    path = ROOT / GUIDES[a.topic][0]
    if not path.exists():
        raise SystemExit("%s is only in a checkout of the repo (%s)" % (a.topic, GUIDES[a.topic][0]))
    md = path.read_text()
    secs = _sections(md)
    if a.toc:
        _emit([{"level": lv, "title": t} for lv, t, _ in secs], a.json,
              "\n".join("  " * (lv - 1) + t for lv, t, _ in secs))
        return 0
    if a.section:
        want = a.section.lower()
        hit = [s for s in secs if s[1].lower() == want] or [s for s in secs if want in s[1].lower()]
        if not hit:
            raise SystemExit("no section %r in %s; try --toc" % (a.section, a.topic))
        lv, t, _ = hit[0]
        lines = md.splitlines()
        start = next(i for i, l in enumerate(lines) if re.match(r"^#{%d}\s+%s\s*$" % (lv, re.escape(t)), l))
        end = next((i for i in range(start + 1, len(lines))
                    if re.match(r"^#{1,%d}\s" % lv, lines[i]) and not _in_fence(lines, i)), len(lines))
        text = "\n".join(lines[start:end]).rstrip()
        _emit({"topic": a.topic, "section": t, "text": text}, a.json, text)
        return 0
    _emit({"topic": a.topic, "text": md}, a.json, md)
    return 0


def _in_fence(lines, i):
    return sum(1 for l in lines[:i] if l.startswith("```")) % 2 == 1


# ---- pipelines ------------------------------------------------------------------------------------------------

def cmd_pipelines(a):
    """docs/PIPELINES.md, one `## name` section per pipeline; its first line says what it makes."""
    path = ROOT / GUIDES["pipelines"][0]
    secs = [(t, body) for lv, t, body in _sections(path.read_text()) if lv == 2]
    if not a.name:
        rows = [{"pipeline": t, "makes": " ".join(body.split("\n\n")[0].split())} for t, body in secs]
        _emit(rows, a.json, "\n".join("  %-9s %s" % (r["pipeline"], r["makes"] if len(r["makes"]) < 118 else r["makes"][:115] + "...")
                                     for r in rows) +
              "\n\n`pixling pipelines NAME` prints one: when to pick it, the steps, the code, what we learned.")
        return 0
    hit = [s for s in secs if s[0] == a.name.lower()] or [s for s in secs if a.name.lower() in s[0]]
    if not hit:
        raise SystemExit("no pipeline %r; one of: %s" % (a.name, ", ".join(t for t, _ in secs)))
    t, body = hit[0]
    _emit({"pipeline": t, "text": body}, a.json, "## %s\n%s" % (t, body))
    return 0


# ---- code -----------------------------------------------------------------------------------------------------

def _doc_head(doc):
    return (doc or "").strip().split("\n\n")[0].replace("\n", " ")


def cmd_code(a):
    pkgs = [d for d in PKG_DIRS.values() if d.is_dir()]
    if a.module in PKG_DIRS:                            # `pixling code tactics`: one package's modules
        pkgs, a.module = [PKG_DIRS[a.module]], None
    if not a.module:
        rows = []
        for pk in pkgs:
            for f in sorted(pk.glob("*.py")):
                if f.name.startswith("_"):
                    continue
                tree = ast.parse(f.read_text())
                rows.append({"module": "%s.%s" % (pk.name, f.stem), "lines": f.read_text().count("\n"),
                             "about": _doc_head(ast.get_docstring(tree))})
        _emit(rows, a.json, "\n".join("  %-16s %5d  %s" % (r["module"], r["lines"], r["about"][:110]) for r in rows))
        return 0
    mod = a.module if "." in a.module else "pp." + a.module
    pkg, _, name = mod.partition(".")
    f = PKG_DIRS.get(pkg, Path("/nonexistent")).joinpath(*name.split(".")).with_suffix(".py")
    if not f.exists():
        raise SystemExit("no module %s (pixling code lists them)" % mod)
    src = f.read_text()
    tree = ast.parse(src)
    items = []
    for n in tree.body:
        if isinstance(n, (ast.FunctionDef, ast.ClassDef)) and (a.all or not n.name.startswith("_")):
            sig = ast.get_source_segment(src, n).split("\n")[0].rstrip(":")
            items.append({"name": n.name, "line": n.lineno, "kind": "class" if isinstance(n, ast.ClassDef) else "def",
                          "signature": sig.strip(), "doc": (ast.get_docstring(n) or "").strip()})
    out = {"module": mod, "file": str(f.relative_to(f.parent.parent)), "path": str(f),
           "doc": (ast.get_docstring(tree) or "").strip(), "items": items}
    text = "%s  (%s; copy or read it whole: %s)\n%s\n\n" % (mod, out["file"], out["path"], out["doc"]) + "\n".join(
        "%s:%d  %s\n    %s" % (out["file"], i["line"], i["signature"], _doc_head(i["doc"]) or "-") for i in items)
    _emit(out, a.json, text)
    return 0


# ---- styles / specs -------------------------------------------------------------------------------------------

def cmd_styles(a):
    from .forge import load_style
    from .color import rgb_to_hex
    if not a.name:
        rows = []
        for f in sorted((ROOT / "styles").glob("*.json")):
            d = json.loads(f.read_text())
            iso = d.get("camera") == "iso_exact"                 # Tactics, Flat: ramps only, built by their kit
            base = BIOMES.get(f.stem, f.stem)
            rows.append({"style": f.stem, "format": "pixel", "camera": "iso" if iso else "sdf",
                         "launch": base in STYLE_HOW, "biome_of": base if base != f.stem else None,
                         "about": d.get("about", ""), "materials": len(d.get("materials", {})),
                         "ramps": len(d.get("ramps", {})), "specs": len(list((ROOT / "specs" / f.stem).glob("**/*.json")))})
        for f in sorted((PKG_DIRS["painted"] / "styles").glob("*.json")):   # the painted format's styles (Blender)
            d = json.loads(f.read_text())
            rows.append({"style": f.stem, "format": "painted", "camera": "blender", "launch": False, "biome_of": None,
                         "about": d.get("about", ""), "ramps": len(d.get("ramps", {})),
                         "layouts": len(list((PKG_DIRS["painted"] / "layouts").glob("*.json")))})
        rows.sort(key=lambda r: (not r["launch"], r["format"] != "pixel", r["style"]))

        def line(r):
            what = ("%2d ramps, %2d layouts" % (r["ramps"], r["layouts"]) if r["format"] == "painted" else
                    "%2d ramps, kit-built  " % r["ramps"] if r["camera"] == "iso" else
                    "%2d materials, %2d specs" % (r["materials"], r["specs"]))
            tag = "launch " if r["launch"] else "       "
            return "  %s%-14s %-7s %-7s %-22s %s" % (tag, r["style"], r["format"], r["camera"], what, r["about"][:90])
        _emit(rows, a.json, "\n".join(line(r) for r in rows) +
              "\n\n`pixling styles NAME` shows one; `pixling styles NAME --how` shows how a launch style was made.")
        return 0
    if a.how:
        return _style_how(a)
    painted = PKG_DIRS["painted"] / "styles" / f"{a.name}.json"
    if painted.exists():
        d = json.loads(painted.read_text())
        out = {"style": a.name, "format": "painted", "about": d.get("about", ""), "camera": d.get("camera"),
               "light": d.get("light"), "ramps": {k: [h for _, h in v] for k, v in d.get("ramps", {}).items()}}
        _emit(out, a.json, "%s (painted): %s\n" % (a.name, out["about"]) + "\n".join(
            "  %-12s %s" % (k, " ".join(v)) for k, v in out["ramps"].items()))
        return 0
    raw = json.loads((ROOT / "styles" / f"{a.name}.json").read_text()) if (ROOT / "styles" / f"{a.name}.json").exists() else {}
    if raw.get("camera") == "iso_exact":                # exact-iso styles: ramps by role, drawn by the kit in tools/
        base = BIOMES.get(a.name, a.name)
        out = {"style": a.name, "format": "pixel", "camera": "iso", "about": raw.get("about", ""), "biome": raw.get("biome"),
               "light": raw.get("light"), "accent": raw.get("accent"), "ramps": raw.get("ramps", {})}
        _emit(out, a.json, "%s (exact iso, biome %s): %s\n" % (a.name, out["biome"], out["about"]) + "\n".join(
            "  %-12s %s" % (k, " ".join(v)) for k, v in out["ramps"].items()) +
            "\n  accent: %s\n\nhow it was made (hand, kit, code, lab notes): pixling styles %s --how" % (out["accent"], base))
        return 0
    st = load_style(a.name)
    mats = {m: {"ramp": d["ramp"], "colors": [rgb_to_hex(c) for c in st.mat_colors(m)],
                **{k: True for k in ("emissive", "no_outline") if d.get(k)}} for m, d in st.materials.items()}
    out = {"style": a.name, "about": st.spec.get("about", ""), "bg": st.spec.get("bg"),
           "vfx_ramps": st.spec.get("vfx_ramps", {}), "materials": mats}
    base = BIOMES.get(a.name, a.name)
    hint = ("\n\nhow it was made (hand, kit, code, lab notes): pixling styles %s --how" % base) if base in STYLE_HOW else ""
    _emit(out, a.json, "%s: %s\n" % (a.name, out["about"]) + "\n".join(
        "  %-12s ramp=%-12s %s" % (m, d["ramp"], " ".join(d["colors"])) for m, d in mats.items()) + hint)
    return 0


def _style_how(a):
    """The making-of for a launch style: its STYLES.md section, then where the code and notes are."""
    name = BIOMES.get(a.name, a.name)
    if name not in STYLE_HOW:
        raise SystemExit("no making-of for %r; launch styles: %s (legacy and painted styles: pixling styles NAME)"
                         % (a.name, ", ".join(STYLE_HOW)))
    h = STYLE_HOW[name]
    md = (ROOT / GUIDES["styles"][0]).read_text()
    lines = md.splitlines()
    start = next(i for i, l in enumerate(lines) if l.strip() == "## " + h["section"])
    end = next((i for i in range(start + 1, len(lines)) if lines[i].startswith("## ")), len(lines))
    section = "\n".join(lines[start:end]).strip()
    code = [c for c in h["code"] if (ROOT / c).exists() or (PKG_DIRS["pp"] / Path(c).name).exists()]
    notes = [{"topic": t, "about": GUIDES[t][1]} for t in h["notes"] if (ROOT / GUIDES[t][0]).exists()]
    out = {"style": name, "section": section, "palette": "tools/make_styles.py (ramps by role; `pixling styles %s`)" % name,
           "code": code, "build": h["build"], "notes": notes, "contract": "pixling guide styles \"The style contract\"",
           "pipeline": "pixling pipelines style"}
    _emit(out, a.json, section + "\n\n## Take it apart\n" +
          "  palette   %s\n" % out["palette"] +
          "  code      %s\n" % "  ".join(code) +
          "            read one: pixling code %s\n" % (code[0].replace("tools/", "").replace("/", ".")[:-3] if code else "-") +
          "  build     %s\n" % h["build"] +
          "  notes     " + "\n            ".join("pixling guide %-14s %s" % (n["topic"], n["about"]) for n in notes) + "\n" +
          "  contract  %s\n  new style %s" % (out["contract"], out["pipeline"]))
    return 0


def cmd_world(a, rest):
    """Build a style's calibration scenes and animal sheets with its own kit (tools/<style>/build.py)."""
    from .paths import OUT
    name = BIOMES.get(a.style, a.style)
    if name not in WORLDS:
        raise SystemExit("pixling world builds %s; vista is built from a checkout: python3 tools/vista/build.py"
                         % " | ".join(WORLDS))
    script = ROOT / WORLDS[name]
    if not script.exists():
        raise SystemExit("%s is missing from this install" % WORLDS[name])
    import subprocess
    args = list(rest) + ([] if "--out" in rest else ["--out", str(OUT)])
    return subprocess.call([sys.executable, str(script)] + args)


def cmd_specs(a):
    base = ROOT / "specs"
    rows = []
    for f in sorted((base / a.style if a.style else base).glob("**/*.json")):
        try:
            d = json.loads(f.read_text())
        except ValueError:
            continue
        kind = "map" if f.name.endswith(".map.json") else (
            "generator:" + str(d["generator"]) if "generator" in d else d.get("rig", "-"))
        rows.append({"spec": str(f.relative_to(ROOT)) if CHECKOUT else str(f), "name": d.get("name", f.stem), "kind": kind,
                     "about": d.get("about") or d.get("concept") or ""})
    _emit(rows, a.json, "\n".join("  %-46s %-10s %s" % (r["spec"], r["kind"], str(r["about"])[:80]) for r in rows))
    return 0


def cmd_new(a):
    """Copy an example spec into ./specs/<name>.json (renamed), the way every asset should start."""
    hits = [f for f in sorted((ROOT / "specs").glob("**/*.json")) if f.stem == a.example
            or f.name == a.example or str(f).endswith(a.example)]
    if not hits:
        raise SystemExit("no example spec %r; list them with `pixling specs`" % a.example)
    spec = json.loads(hits[0].read_text())
    spec["name"] = a.name
    dest = Path(a.out or "specs") / (a.name + ".json")
    if dest.exists() and not a.force:
        raise SystemExit("%s exists (use --force)" % dest)
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text(json.dumps(spec, indent=1) + "\n")
    if "layers" in spec:  # an iso block token (pp.blocks), not an SDF spec
        print("%s  (from %s, a block token)\nnext: pixling blocks %s --on YOUR_SCENE.png" % (dest, hits[0].stem, dest))
        return 0
    print("%s  (from %s, style %s)\nnext: pixling build %s --clips idle --dirs S,E" % (
        dest, hits[0].stem, spec.get("style"), dest))
    return 0


# ---- doctor ---------------------------------------------------------------------------------------------------

def cmd_doctor(a):
    from .scenario import auth
    checks = [("python>=3.9", sys.version_info >= (3, 9), sys.version.split()[0])]
    for mod in ("numpy", "PIL", "scipy"):
        try:
            m = __import__(mod)
            checks.append((mod, True, getattr(m, "__version__", "")))
        except ImportError:
            checks.append((mod, False, "pip install -r requirements.txt"))
    ff = shutil.which("ffmpeg")
    checks.append(("ffmpeg (reel only)", bool(ff), ff or "brew install ffmpeg"))
    try:
        sys.path.insert(0, str(REPO))
        from painted.__main__ import blender
        bl = blender()
    except ImportError:
        bl = None
    checks.append(("blender (painted only)", bool(bl), bl or "install Blender 4.2+ or set PIXLING_BLENDER"))
    md = auth.mode()
    st = auth.load()
    who = {"api-key": "SCENARIO_API_KEY", "oauth": "team %s, project %s" % (st.get("team_id", "?"), st.get("project_id", "?")),
           "none": "pixling scenario login"}[md]
    checks.append(("scenario sign-in (optional)", md != "none", "%s: %s" % (md, who)))
    rows = [{"check": c, "ok": ok, "detail": d} for c, ok, d in checks]
    _emit(rows, a.json, "\n".join("  %s %-28s %s" % ("ok " if r["ok"] else "-- ", r["check"], r["detail"]) for r in rows))
    return 0 if all(r["ok"] for r in rows[:4]) else 1


# ---- agent install --------------------------------------------------------------------------------------------

AGENTS_BLOCK = """\
<!-- pixling -->
## Game art (pixling)
Game art comes from `pixling` (the Pixel Perfect forge): pipelines, styles and taste for making sprites with code.
Never hand-paint pixels. Start with `pixling pipelines` (spec, iso, map, fx, video, painted, style) and pick one;
`pixling styles NAME --how` shows how a style was made, with its code and notes, to reuse or build on.
Spec loop: copy an example from `pixling specs` -> `pixling build` -> `pixling review` (look at the image) -> fix ->
`pixling scene` -> `pixling lint`. AI image/video: `pixling scenario` (the user signs in once with
`pixling scenario login`). Painterly, non-pixel: `pixling painted` (needs Blender).
<!-- /pixling -->
"""


def cmd_agent(a):
    dest = Path(a.dir).resolve()
    skill = ROOT / ".claude" / "skills" / "pixling" / "SKILL.md"
    done = []
    for d in (".claude/skills/pixling", ".agents/skills/pixling"):
        t = dest / d
        t.mkdir(parents=True, exist_ok=True)
        shutil.copy(skill, t / "SKILL.md")
        done.append(str(t / "SKILL.md"))
    ag = dest / "AGENTS.md"
    text = ag.read_text() if ag.exists() else ""
    if "<!-- pixling -->" in text:                      # re-running replaces the block instead of stacking copies
        text = re.sub(r"<!-- pixling -->.*?<!-- /pixling -->\n?", lambda m: AGENTS_BLOCK, text, flags=re.S)
    else:
        text = (text.rstrip() + "\n\n" if text.strip() else "") + AGENTS_BLOCK
    ag.write_text(text)
    done.append(str(ag))
    if not shutil.which("pixling"):
        done.append("note: pixling is not on PATH; install it with `uv tool install pixling` or `pipx install pixling`")
    print("\n".join(done))
    return 0


# ---- scenario -------------------------------------------------------------------------------------------------

def _json_arg(s):
    if s is None:
        return {}
    if s.startswith("@") or (len(s) < 300 and Path(s).is_file()):
        return json.loads(Path(s.lstrip("@")).read_text())
    return json.loads(s)


def cmd_scenario(a):
    from . import scenario as S
    from .scenario import auth
    sc = a.scmd
    if sc == "login":
        if auth.api_key_header():
            print("note: SCENARIO_API_KEY is set, so commands use the API key, not this OAuth session", file=sys.stderr)
        auth.login(device=a.device, browser=not a.no_browser, scope=a.scope)
        print("signed in to Scenario.")
        return _pick_scope(S, auth)
    if sc == "logout":
        auth.logout()
        print("signed out (client registration kept).")
        return 0
    if sc == "status":
        st = auth.load()
        tok = st.get("tokens") or {}
        out = {"mode": auth.mode(), "server": st.get("server", auth.SERVER), "team_id": st.get("team_id"),
               "project_id": st.get("project_id"), "expires_in_s": int(tok["expires_at"] - time.time()) if tok else None,
               "refreshable": bool(tok.get("refresh_token")), "store": str(auth._store_path())}
        _emit(out, a.json, "\n".join("  %-12s %s" % kv for kv in out.items()))
        return 0 if out["mode"] != "none" else 1
    if sc == "use":
        st = auth.load()
        if a.team:
            st["team_id"] = a.team
        if a.project:
            st["project_id"] = a.project
        auth.save(st)
        if not (a.team or a.project):
            return _pick_scope(S, auth)
        print("team %s, project %s" % (st.get("team_id"), st.get("project_id")))
        return 0
    if sc == "tools":
        ts = S.tools(full=a.full, fresh=a.fresh)
        if a.word:
            w = a.word.lower()
            ts = [t for t in ts if w in (t["name"] + t.get("description", "")).lower()]
        rows = [{"name": t["name"], "about": t.get("description", "").strip().split("\n")[0]} for t in ts]
        _emit(rows, a.json, "\n".join("  %-28s %s" % (r["name"], r["about"][:100]) for r in rows))
        return 0
    if sc == "schema":
        t = next((t for t in S.tools(full=True) if t["name"] == a.tool), None)
        if not t:
            raise SystemExit("no tool %s (pixling scenario tools)" % a.tool)
        _emit(t, True)
        return 0
    if sc == "call":
        r = S.call(a.tool, _json_arg(a.args), full=a.full, raw=a.raw)
        _emit(r, True) if not isinstance(r, str) else print(r)
        return 0
    if sc == "cost":
        _emit(S.cost(a.model, _json_arg(a.params)), True)
        return 0
    if sc == "run":
        paths, cu = S.run(a.model, _json_arg(a.params), a.out, wait=not a.no_wait)
        _emit({"outputs": [str(p) for p in paths] if isinstance(paths, list) else paths, "cu": cu}, True)
        return 0
    if sc == "upload":
        print(S.upload(a.file))
        return 0
    if sc == "download":
        print(S.download(a.asset, a.out, a.format))
        return 0
    raise SystemExit("unknown scenario command")


def _pick_scope(S, auth):
    """OAuth calls need a team and a project; keep the only ones, or list them for `pixling scenario use`."""
    st = auth.load()
    if auth.mode() != "oauth":
        return 0
    try:
        teams = S._find(S.call("teams_list", quiet=True), "teams", "items") or []
    except S.MCPError as e:
        print("could not list teams: %s" % e, file=sys.stderr)
        return 1
    if len(teams) == 1 and not st.get("team_id"):
        st["team_id"] = teams[0].get("id")
        auth.save(st)
    if not st.get("team_id"):
        print("teams:\n" + "\n".join("  %s  %s" % (t.get("id"), t.get("name")) for t in teams) +
              "\nchoose one: pixling scenario use --team ID")
        return 0
    projects = S._find(S.call("projects_list", {"team_id": st["team_id"]}, quiet=True), "projects", "items") or []
    if len(projects) == 1 and not st.get("project_id"):
        st["project_id"] = projects[0].get("id")
        auth.save(st)
    if not st.get("project_id"):
        print("projects:\n" + "\n".join("  %s  %s" % (p.get("id"), p.get("name")) for p in projects) +
              "\nchoose one: pixling scenario use --project ID")
        return 0
    print("using team %s, project %s" % (st["team_id"], st["project_id"]))
    return 0


def version() -> str:
    try:
        from importlib.metadata import version as dist_version
        return dist_version("pixling")
    except Exception:                                    # a checkout run through bin/pixling has no metadata
        return "dev"


# ---- router ---------------------------------------------------------------------------------------------------

def _parser():
    ap = argparse.ArgumentParser(prog="pixling", add_help=False)
    sub = ap.add_subparsers(dest="cmd")
    g = sub.add_parser("guide", help="the docs, by topic and section")
    g.add_argument("topic", nargs="?")
    g.add_argument("section", nargs="?")
    g.add_argument("--toc", action="store_true")
    g.add_argument("--grep")
    g.add_argument("--json", action="store_true")
    c = sub.add_parser("code", help="engine modules and their functions")
    c.add_argument("module", nargs="?")
    c.add_argument("--all", action="store_true", help="include _private functions")
    c.add_argument("--json", action="store_true")
    s = sub.add_parser("styles", help="styles, or one style's materials")
    s.add_argument("name", nargs="?")
    s.add_argument("--how", action="store_true", help="how the style was made: hand, kit, code, lab notes")
    s.add_argument("--json", action="store_true")
    pl = sub.add_parser("pipelines", help="the pipelines: what each makes, steps, code, lessons")
    pl.add_argument("name", nargs="?")
    pl.add_argument("--json", action="store_true")
    sp = sub.add_parser("specs", help="example specs")
    sp.add_argument("style", nargs="?")
    sp.add_argument("--json", action="store_true")
    nw = sub.add_parser("new", help="start a spec from an example: pixling new fox my_fox")
    nw.add_argument("example")
    nw.add_argument("name")
    nw.add_argument("--out", help="folder for the new spec (default ./specs)")
    nw.add_argument("--force", action="store_true")
    d = sub.add_parser("doctor", help="is this machine ready")
    d.add_argument("--json", action="store_true")
    ag = sub.add_parser("agent", help="agent integration for another project")
    ags = ag.add_subparsers(dest="acmd", required=True)
    ai = ags.add_parser("install")
    ai.add_argument("dir", nargs="?", default=".")

    sc = sub.add_parser("scenario", help="Scenario generation over MCP (OAuth)")
    ss = sc.add_subparsers(dest="scmd", required=True)
    li = ss.add_parser("login", help="OAuth sign-in (browser, or --device for a code)")
    li.add_argument("--device", action="store_true", help="device code: open a link on any device, no local browser")
    li.add_argument("--no-browser", action="store_true", help="print the URL instead of opening it")
    li.add_argument("--scope")
    ss.add_parser("logout")
    st = ss.add_parser("status")
    st.add_argument("--json", action="store_true")
    us = ss.add_parser("use", help="set the default team / project (OAuth calls need both)")
    us.add_argument("--team")
    us.add_argument("--project")
    tl = ss.add_parser("tools")
    tl.add_argument("word", nargs="?")
    tl.add_argument("--full", action="store_true", help="the full catalog (projects, collections, training...)")
    tl.add_argument("--fresh", action="store_true", help="ignore the one-day cache")
    tl.add_argument("--json", action="store_true")
    sh = ss.add_parser("schema")
    sh.add_argument("tool")
    ca = ss.add_parser("call")
    ca.add_argument("tool")
    ca.add_argument("args", nargs="?", help="JSON object, or @file.json")
    ca.add_argument("--full", action="store_true")
    ca.add_argument("--raw", action="store_true", help="the MCP result as sent (content blocks)")
    co = ss.add_parser("cost")
    co.add_argument("model")
    co.add_argument("params")
    ru = ss.add_parser("run")
    ru.add_argument("model")
    ru.add_argument("params", help="model inputs: JSON object or @file.json (no 'parameters' wrapper)")
    ru.add_argument("--out", help="file to save; several outputs get _0, _1 ...")
    ru.add_argument("--no-wait", action="store_true")
    up = ss.add_parser("upload")
    up.add_argument("file")
    dl = ss.add_parser("download")
    dl.add_argument("asset")
    dl.add_argument("--out", required=True)
    dl.add_argument("--format")
    return ap


def main(argv=None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    if not argv or argv[0] in ("-h", "--help", "help"):
        from .brand import terminal_banner
        print(terminal_banner() + USAGE)
        return 0
    if argv[0] in ("-V", "--version", "version"):
        print("pixling", version())
        return 0
    head, rest = argv[0], argv[1:]
    if head in ENGINE:
        from .__main__ import engine_main
        return engine_main(argv) or 0
    if head == "world":
        if not rest or rest[0].startswith("-"):
            print("usage: pixling world tactics|flat [--only SCENE] [--frames N] [--out DIR]\n"
                  "builds a style's scenes and animal sheets with its kit (see pixling styles NAME --how)")
            return 0 if rest[:1] in (["-h"], ["--help"]) else 2
        return cmd_world(argparse.Namespace(style=rest[0]), rest[1:]) or 0
    if head == "map":
        from .map import main as map_main
        return map_main(rest) or 0
    if head == "blocks":
        from .blocks import main as blocks_main
        return blocks_main(rest) or 0
    if head == "reel":
        sys.path.insert(0, str(REPO))
        from reel.__main__ import main as reel_main
        return reel_main(rest) or 0
    if head == "painted":
        sys.path.insert(0, str(REPO))
        from painted.__main__ import main as painted_main
        return painted_main(rest) or 0
    a = _parser().parse_args(argv)
    run = {"guide": cmd_guide, "pipelines": cmd_pipelines, "code": cmd_code, "styles": cmd_styles, "specs": cmd_specs, "new": cmd_new, "doctor": cmd_doctor,
           "agent": cmd_agent, "scenario": cmd_scenario}.get(a.cmd)
    if run is None:
        print(USAGE)
        return 2
    try:
        return run(a) or 0
    except BrokenPipeError:
        return 0


if __name__ == "__main__":
    sys.exit(main())

---
name: pixling
description: Make game art with code using pixling (the Pixel Perfect forge), a catalogue of pipelines, styles and taste notes. Pipelines: JSON spec -> 8-direction pixel sprites; exact-iso scenes from Python kits; living maps with states, hour light and a meaning layer; VFX sheets; AI image -> video -> keyed sprite frames (Scenario + reel); Blender -> painterly sprites. Each style ships with how it was made (hand, kit code, lab notes), so you can reuse it or build a new one. Use when asked for sprites, characters, creatures, trees, buildings, spell effects, a town or world map, an iso scene, a new art style, an itch.io pack, or AI image/video generation through Scenario.
---

# Pixel Perfect (`pixling`)

You are the artist. You never paint pixels: you pick a pipeline, drive it with code (a JSON spec, a Python kit, a
Blender layout, video takes), and judge the images by eye. pixling is a catalogue. Run the pipelines as they are, or
read how they and the styles were made and take what helps into the user's own project. Run `pixling` for every command.

## Pick a pipeline
- `pixling pipelines`: spec (sprites), iso (exact-iso scenes), map (living maps), fx, video (image -> video ->
  frames), painted (Blender), style (a new style from scratch). `pixling pipelines NAME` gives the steps, the code
  and what we learned.
- `pixling styles NAME --how`: how a launch style (vista, tactics, flat) was made: hand, kit, code, lab notes.
  `pixling code tactics.kit` prints a kit module and its path, so you can read it whole or copy it.
- `pixling guide styles "The shared taste layer"`: the rules every style keeps. Apply them to your own work too.

## Before the first asset (spec pipeline)
- `pixling doctor`: dependencies. If `pixling` is missing, use `python3 -m pp` from the Pixel Perfect repo.
- `pixling guide artist "The loop"` and `pixling guide artist "Spec format"`: how specs work. `pixling guide` lists every doc;
  `pixling guide --grep WORD` searches them.
- `pixling styles` lists the styles; `pixling styles NAME` shows materials and ramps. Use the style's materials; never invent colours.
- `pixling specs STYLE`: copy the closest example spec and change it. Don't start from a blank file.

## The loop (minutes per asset)
```
pixling build SPEC --clips idle --dirs S,E      # fast: only what you're judging
pixling review out/NAME --clips idle --dirs S,E # look at the PNG it prints
# fix the spec, rebuild, look again; then the full build:
pixling build SPEC
pixling scene out/NAME out/oak --style STYLE    # next to its family and a tree, at game scale
pixling lint out/NAME                           # hints, not gates
```
Use `--out DIR` on build to write into your own project. `pixling inspect SPEC` shows what's under the pixels
(bone/material maps); `pixling variants SPEC --vary key=a,b,c` builds versions side by side, and `--apply N` keeps one.

## Rules
- Judge by looking at the images (your image-reading tool), at 1x in `scene` and animated. No measurement essays.
- Big shapes first, details last. Prototype ONE asset, get the user's sign-off, then make the family.
- Done: it reads at 1x next to its family, all 8 directions are the same character, the attack reads, nothing
  swims in idle, and you can explain every lint WARN in one sentence.
- If the engine can't do something, say what's missing. Don't work around it with dozens of micro-parts.

## Iso scenes (Crisp Tactics, Flat Minimal)
`pixling world tactics|flat [--only SCENE]` builds a style's scenes and animal sheets with its kit. For new scenes,
copy `tools/<style>/scenes.py` (path from `pixling code tactics.scenes`) and render with `pp.iso`; `pixling pipelines iso`.

## Board pieces (units, creatures on an iso board)
`pixling pipelines blocks`. Build them as block tokens (`pixling blocks`): a few chunky voxels (3 x 3 footprint, 2-4
layers, ~12 px: a third of a tile) in the board's exact iso, face light and cast shadow, facings by rotation. Not
side-view sprites, not 3D-rendered animals. Keep them small and pull the camera back rather than growing them. Judge
them standing in the real scene (`--on SCREENSHOT_1x.png`), and never restyle the environment to fix the pieces.

## Maps, states, light, VFX, packs
`pixling guide environments` and `pixling guide artist "Maps (pp.map)"`. Commands: `pixling map MAP.json --still`,
`pixling states SPEC`, `pixling light MAP.json --gif`, `pixling fx KIND --style S`, `pixling pack NAME DIRS --style S`.

## Scenario (AI images, video, 3D, audio)
- Run `pixling scenario status`. If signed out, ask the user to run `! pixling scenario login` (it opens a browser; use
  `--device` for a code to type on another device). Sign-in is once per machine; tokens refresh themselves.
- Discover models with `pixling scenario call recommend '{"query": "..."}'` or `pixling scenario call models_list '{"query": "..."}'`.
  `pixling scenario tools` lists every tool, and `pixling scenario schema TOOL` shows its inputs.
- Before a run: `pixling scenario call model_schema_get '{"model_id": "M"}'`, then `pixling scenario cost M '{...}'`.
  Tell the user the cost in CU and ask before spending beyond their budget.
- `pixling scenario run M '{...model inputs...}' --out file.png` waits for the job and downloads the outputs.
  File inputs are asset ids: `pixling scenario upload FILE`.
- Video for sprites: `pixling guide reel-workflow`. Use MiniMax H3 only.

## Painted format (not pixel art)
When the user wants a painterly look instead of pixels: `pixling guide painted`. Needs Blender (`pixling painted doctor`).
`pixling painted kit` renders a style + layout as sprites (shadow layers, sway loops, 8 headings) into
out/painted/<layout>/kit; `compose` lays the scene out from them; `game` packs a walkable web scene. Look at
`scene/kit_sheet.png` and `scene/scene.png` before showing anything. New assets are builders in painted/bpy/assets.py,
new colours are ramps in painted/styles/*.json, places are painted/layouts/*.json. Never mix pixel and painted sprites in one scene.

## Reading the engine
`pixling code` lists the modules and `pixling code forge` shows one module's functions with their docstrings. Read the
source only when you need it.

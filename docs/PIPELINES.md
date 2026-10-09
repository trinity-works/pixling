# Pipelines: how pixling makes game art with code

pixling is not one renderer. It is a shelf of pipelines, each one a way we found to make a kind of game art
with an agent and code, plus the styles made with them and the taste rules behind them. Take what helps: run a
pipeline as it is, copy its code into your own project, or read how it was made and do better.

`pixling pipelines` lists them; `pixling pipelines NAME` prints one. Each says what it makes, when to pick it, the
steps, the code that does it and what we learned the hard way.

| Pipeline | Makes | Engine | Needs |
|---|---|---|---|
| spec | 8-direction sprites, props, buildings from a JSON spec | `pp` (SDF forge) | Python |
| iso | exact 2:1 isometric scenes and animal sheets, built in Python | `pp.iso` | Python |
| map | living maps: building states, hour light, a meaning layer | `pp.map` | Python |
| fx | VFX sheets in a style's ramp | `pp.vfx` | Python |
| video | sprites cut from AI video: image -> video -> keyed frames | `reel` + Scenario | ffmpeg, Scenario sign-in |
| painted | painterly (non-pixel) sprites and scenes rendered in Blender | `painted` | Blender 4.2+ |
| style | a new art style from scratch | all of them | a person who owns the look |

## spec
JSON spec (simple 3D shapes on bones) -> palette-locked, 8-direction animated sprite sheets.

**Pick it for** characters, creatures, props and buildings that must turn, animate and stay pixel-stable, in one of
the SDF styles (vista props, sunmeadow, duskborne, vermilion).

**Steps**
```
pixling specs vista                             # find the closest example
pixling new house_5 inn                         # copy it to ./specs/inn.json
pixling build specs/inn.json --clips idle --dirs S,E   # fast: only what you judge
pixling review out/inn                          # a zoomed PNG: look at it
# edit the spec, rebuild, look again; then the full build
pixling build specs/inn.json --out assets/art
pixling scene out/inn out/oak --style vista     # next to its family at game scale
pixling lint out/inn                            # hints, not gates
```
**How it works.** Parts are signed-distance shapes on bones, in pixel units. Each of 8 facings is rendered at 4x and
reduced by coverage and majority vote. Each bone is a cached rigid layer placed at whole-pixel offsets, so a part
that only moves keeps identical pixels (no swimming). Pixels are (material, light level) until the very end; the
colours come only from the style's ramps. Banded light, coloured outlines (no black), inner lines where a nearer
part overlaps, contact shadows, despeckle. Motion uses one 75 ms frame and holds by repetition.

**Code:** `pp/forge.py` (render), `pp/sdf.py` (shapes), `pp/motion.py` (clips), `pp/shade.py` (styles, light bands); `pixling code forge`.
**Read:** `pixling guide workflow "The pipeline"`, `pixling guide artist "Spec format"`, `pixling guide artist "Motion"`.

**Learned**
- Big shapes first, details last. Prototype one asset, get sign-off, then the family.
- Don't transcribe a concept sheet detail by detail; small sprites need a few big readable shapes, not chibi.
- If the engine can't do something, ask for the feature. Don't fake it with forty micro-parts.
- 8 frames at 75 ms reads as running; walks want 16 frames and folded knees.

## iso
Python kit + scene layout -> an exact 2:1 isometric scene (still, ambient loop, night) and animal walk sheets.

**Pick it for** tactics boards, iso towns and dioramas where every edge must be a clean 2:1, 1:1 or vertical stair.
Crisp Tactics and Flat Minimal are built with it.

**Steps**
```
pixling world tactics [--only tactics_valley] [--frames 1]   # the style's scenes + sheets -> out/
pixling world flat [--only flat_forest]
python3 -m pp.iso out/tactics_valley/scene.json --out /tmp/tv [--hour night] [--dither night] [--raw]
pixling pixcheck out/tactics_valley/noon_1x.png --mark marks.png   # orphans, whiskers, broken stairs
pixling code tactics.kit                         # the kit: read it, copy it, make your own
```
**How it works.** Every prop is lattice boxes or polytopes with integer coordinates; one ray per pixel centre, no
resampling, so every edge is a uniform stair. World scale x2 (`K = 2`) makes diagonals long and even. Shading is one
flat tone per face (three for Tactics). The soft selout line sits inside each silhouette, is pixel-perfect (no
L-corners), takes the style's ink on the shadow side and one tone darker on the lit side, and gets one in-between
palette tone at each removed corner. Night maps each face to a step of a night ramp, so values keep their order.

**Code:** `pp/iso.py` (camera, scene, render), `pp/iso_line.py` (soft line), `tools/tactics/kit.py` and `scenes.py`,
`tools/flat/kit.py` and `scenes.py`. **Read:** `pixling styles tactics --how`, `pixling styles flat --how`.

**Learned**
- Approximate iso (SDF props at a 45° yaw) jitters: runs wobble 3-2-2-3 and roof rakes land near 1:1.5. Exact
  lattice geometry fixed it, with roof pitch 0.5.
- A 1 px ring outside the silhouette doubles at every stair. Put the line inside and remove L-corners.
- Near-black lines on light ground make every jag visible; ink the shadow side only, in the style's dark hue.
- Small styles need a declared enlargement for animals or they don't read (Flat deer ~1.3x, Tactics stag ~1.6x).

## map
Map JSON -> a living aerial map: building states, every hour of the day, and a meaning layer for your engine.

Terrain, sea and forest are painted procedurally around placed sprites.

**Pick it for** town and world maps in the vista style, and anything a game needs to walk around in.

**Steps**
```
pixling map specs/vista/highgate.map.json --still     # fast layout check
pixling map MAP.json                                  # the ambient loop (GIF)
pixling map MAP.json --layers                         # engine export: base, occluders, movers, fog, places
pixling map MAP.json --meaning                        # material, collision, water depth, feet-y depth, ids
pixling states specs/vista/house_5.json               # ruin, build25..90, built; place "house_5~ruin"
pixling light MAP.json --gif                          # day, golden, sunset, dusk, night + light.json
```
**How it works.** One painter per material: terrain, sea and canopy are painted procedurally; buildings and props
are spec sprites. Windows, water and ground are known from the meaning layer, never by matching colours. Time of
day is a grade over the map, not a repaint; windows light one by one.

**Code:** `pp/map.py` (painters), `pp/meaning.py`, `pp/layers.py`, `pp/light.py`, `pp/states.py`, `tools/vista/` (kits and layouts that write
the specs). **Read:** `pixling guide environments`, `pixling styles vista --how`.

**Learned**
- Zoomed out, tiny people, feel over features. Busy villages read worse than calm masses with one landmark.
- Never mix kit tree sprites with canopy-painted forest in one scene.
- Settlements cluster tightly around one landmark, with open space around the group.

## fx
A kind + a style -> a VFX sheet (PNG, GIF, JSON) posterised to one of the style's ramps.

**Steps**
```
pixling fx KIND --style duskborne [--ramp RAMP] [--param k=v]
# KIND: slash hit_spark burst eruption aura dust projectile lightning sparkle leaves shockwave
```
**How it works.** Effects are energy fields over time, posterised to a ramp last, with the timing rules built in
(fast attack, held peak, slow decay).

**Code:** `pp/vfx.py`. **Read:** `pixling guide artist "VFX sheets"`.

## video
Design image -> image-to-video takes (Scenario, MiniMax H3) -> keyed, cut 8-direction sprite sheets.

The output is palette-locked sheets, an actor JSON and a playable demo.

**Pick it for** painterly or illustrated characters with rich motion that an SDF rig can't give: attacks, casts,
creatures. It costs credits; estimate first and ask.

**Steps**
```
pixling scenario login                      # once; opens a browser, so ask the user to run it
# 1 design: a character at the game camera (~60° top-down), facing SE, on flat #FF00FF
# 2 start sheet: all five facings (S, SE, E, NE, N) in ONE image, then
pixling reel split reel/chars/NAME/ref/sheet.png          # -> start frames on one baseline and scale
# 3 takes: one per facing x state, first = last frame = the start frame, 5 s, 768P
pixling scenario call model_schema_get '{"model_id": "model_minimax-h3"}'
pixling scenario cost model_minimax-h3 @take.json         # tell the user the CU, ask
pixling scenario run model_minimax-h3 @take.json --out reel/chars/NAME/takes/attack_se_a.mp4
# 4 check every take: backdrop drift, turns, re-swings
pixling reel contact reel/chars/NAME/takes/attack_se_a.mp4
# 5 cut (char.json from reel/chars/_template), 6 review
pixling reel gambit reel/chars/NAME/char.json             # -> out/reel/NAME/gambit: sheets, board, qc.json
pixling reel page NAME ; pixling reel demo NAME
# spells: generate on pure black, then
pixling reel fx reel/fx/NAME.json                          # brightness -> alpha, additive sheets
```
**How it works.** The video model supplies the motion; the cut supplies the consistency: one start sheet, one scale,
one palette, one outline and one game clock. Per-frame chroma key, pose-driven key picking, cycle detection,
palette lock and re-outline.

**Code:** `reel/` (`pixling code reel.cut`, `reel.key`, `reel.finish`), `pp/scenario/` (the Scenario client).
**Read:** `pixling guide reel-workflow` (the prompts that worked), `pixling guide reel`.

**Learned**
- Use MiniMax H3 only. It gives attacks a clear timing arc (held wind-up, one strike, a hold, a snap back) with the
  same beats in every facing.
- Four prompt blocks (background, camera, character, motion) and the backdrop rule repeated as the last line.
  Never name other colours in the backdrop block.
- About 1 in 4 takes drifts the magenta backdrop. A drifted take can't be saved: reroll it. Budget ~40% rerolls.
- Keys and holds read better than smooth in-betweens. Never use optical-flow interpolation.
- Never chroma-key effects; turn brightness into alpha and add them back with `lighter`.

## painted
Style + layout -> Blender renders painterly sprites, a composed scene and a walkable web scene.

Soft painted cards, stepped colour bands, no outlines, no pixel grid; sprites come with shadow layers, sway loops and
8 headings.

**Pick it for** a non-pixel, cosy painted look for environments and props.

**Steps**
```
pixling painted doctor                    # Blender found?
pixling painted styles | layouts | assets
pixling painted kit [--style painted_cards --layout hollow_brook]   # -> out/painted/<layout>/kit
pixling painted compose                   # -> scene.png, scene.mp4, kit_sheet.png: look at them
pixling painted game ; pixling painted serve
```
**How it works.** Foliage, grass and clouds are alpha-masked cards (crowns: brush-dab masks square to the camera);
the cards of one clump carry the clump's sphere normals, so it shades as one soft mass. Diffuse -> Shader to RGB -> a
constant colour ramp from the style: no gradients, no specular. A baked value pass darkens buried cards (dark pockets
between clumps) and grades the crown from its sun side to its shadow side; crowns don't shadow themselves; sway loops
add per-card flutter. Roof normals bend toward a point inside the house, so flat planes shade in painted bands.
The ground stores distance fields per vertex and the shader picks designed flat tones from them.

**Code:** `painted/bpy/painter.py` (shader, cards, sprite render), `painted/bpy/assets.py` (builders),
`painted/textures.py`. **Read:** `pixling guide painted`.

**Learned**
- One painter per material holds across formats: never mix pixel and painted sprites in one scene.
- New assets are builders, new colours are ramps, places are layouts; the shader stays shared.
- From the anime-tree tutorial: value (dark pockets) and a crown-wide gradient make a tree read; self-shadowed crowns
  turn into one flat dark block. Pines are the exception: their tiers need to shade each other.

## style
How we make an art style: refs -> DNA -> hand -> kit -> calibration brief -> review card -> walk it -> vote.

**Pick it for** a look none of the styles have. A palette swap is never a new style; it makes a season or a biome.
A style is palette + hand (camera, density, shading, line, shadows, marks) + its own kit.

**Steps**
1. **Refs board.** Mood images (Scenario or the user's). They never ship.
2. **DNA sheet.** Name the hand on each axis: camera, shapes, shading, edges, shadows, marks, palette, vocabulary.
   One line on what makes it distinct.
3. **Hand modes.** Find the engine stages the hand needs (line mode, shading mode, shadow shape, pixel size). Build
   a missing stage once, opt-in, so it serves every later style.
4. **Kit.** Its own buildings, plants, ground, water and animals, from scratch.
5. **Calibration brief.** *A small settlement at a water's edge, three buildings (one a ruin), a path and a bridge,
   trees, a field, a deer and a wading bird, smoke, water and birds moving.* Then a second biome in the same hand.
6. **Review card.** The scene at game zoom, the ref beside it, a greyscale strip, an 8x crop; `pixling pixcheck`.
7. **Walk it.** Does it feel like a place?
8. **Vote.** The person who owns the look says yes, maybe or no.

**Code:** `tools/make_styles.py` (palettes by role), `tools/tactics/`, `tools/flat/`, `tools/vista/` (three worked
examples). **Read:** `pixling guide styles` (the contract and the shared taste layer), `pixling styles NAME --how`,
`pixling guide style-search` (the lab notes of the search that found the launch styles).

**Learned**
- Round 1 put six palettes on one kit: every result looked like the same style. The hand is what differs.
- Prototype in a copy, judge on the same brief, keep the losers' notes. Saffron (ink line) and Marsh (painterly
  clusters) were parked, not deleted.
- A style doesn't ship while any material falls back to another style's painter.

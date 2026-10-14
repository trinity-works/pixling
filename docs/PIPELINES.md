# Pipelines: how pixling makes game art with code

pixling is not one renderer. It is a shelf of pipelines, each one a way we found to make a kind of game art
with an agent and code, plus the styles made with them and the taste rules behind them. Take what helps: run a
pipeline as it is, copy its code into your own project, or read how it was made and do better.

`pixling pipelines` lists them; `pixling pipelines NAME` prints one. Each says what it makes, when to pick it, the
steps, the code that does it and what we learned the hard way.

| Pipeline | Makes | Engine | Needs |
|---|---|---|---|
| spec | 8-direction sprites, props, buildings from a JSON spec | `pp` (SDF forge) | Python |
| blocks | small iso units and creatures from a few voxel layers, in a board's projection, light and shadow | `pp.blocks` | Python |
| iso | exact 2:1 isometric scenes and animal sheets, built in Python | `pp.iso` | Python |
| map | living maps: building states, hour light, a meaning layer | `pp.map` | Python |
| fx | VFX sheets in a style's ramp | `pp.vfx` | Python |
| video | sprites cut from AI video: image -> video -> keyed frames | `reel` + Scenario | ffmpeg, Scenario sign-in |
| painted | painterly (non-pixel) sprites and scenes rendered in Blender | `painted` | Blender 4.2+ |
| fp | a walkable pixel world: a painted scene in layers with a small walker (opens), or first person in WebGL | `fp` | Python; Node + Playwright for shots |
| arena | painted battle maps for your own units, with a complete game level (collision, nav, LOS, zones) | `arena` | Python; Blender 4.2+ to repaint |
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
Opt-in `"hand": true` adds the pixel artist's decisions on top (big-form light, deep shadows, clean clusters,
placed highlights, lost-and-found lines, quiet zones) plus relative-shade motifs (`pixling guide artist "The hand pass"`).

**Code:** `pp/forge.py` (render), `pp/sdf.py` (shapes), `pp/motion.py` (clips), `pp/shade.py` (styles, light bands); `pixling code forge`.
**Read:** `pixling guide workflow "The pipeline"`, `pixling guide artist "Spec format"`, `pixling guide artist "Motion"`.

**Learned**
- Big shapes first, details last. Prototype one asset, get sign-off, then the family.
- Don't transcribe a concept sheet detail by detail; small sprites need a few big readable shapes, not chibi.
- If the engine can't do something, ask for the feature. Don't fake it with forty micro-parts.
- 8 frames at 75 ms reads as running; walks want 16 frames and folded knees.
- Lit-per-primitive shading reads as vector art at pixel size (the Retro Diffusion founder's critique, 2026-10).
  Detail isn't more features: light the big form first, commit to a shadow mass, place marks by meaning.

## blocks
A few voxel layers + the scene's ramps -> small iso board pieces: clips in 4 rotated facings, cast shadows, events.

**Pick it for** tactics and strategy units, creatures and heroes on an iso board seen from far away: anything a
player reads as a token. Below ~20 px, pieces rendered from detailed 3D smear their features and side-view sprites
read as stickers on an iso tile; a handful of chunky voxels in the board's own projection does neither.

**Steps**
```
pixling specs blocks ; pixling new blocks/pip.json my_hero                  # start from an example piece
pixling blocks specs/my_hero.json --lineup out/roster.png --ink "#0b1d22"  # every piece on an iso tile + value strip
pixling blocks specs/*.json --on SCREENSHOT_1x.png --at X,Y --step 16,8 --ink "#0b1d22"   # judge it IN the scene
```
**How it works.** A spec is `layers` (bottom to top) of rows (y) of role letters (x; the piece faces +x, `.` empty),
`"vox": 2` lattice units per voxel (a 4 px cube), and per role its `[top, right, left]` face tones (one hex = flat on
every face). Every pixel centre shoots the iso view ray and takes the face of the first voxel it hits, so edges are
exact 2:1 lines. A role whose top is the body tone and whose sides are ink puts eyes on the front face only. Facings
E, S, W, N (screen SE, SW, NW, NE) are true rotations. Clips: idle breath, hop, lunge (`hit` event), flash and knock
back, rise and glow (`cast` event, with `"cast": true`); `"lift"` floats a flyer; `shadow(facing)` is the long flat
cast shadow in the sprite's own frame.

**Code:** `pp/blocks.py`; examples in `specs/blocks/`.

**Learned**
- Characters rendered from detailed 3D at ~20 px were mush; outlines and saturation passes never fixed it.
- Fixing the characters is not a licence to restyle the environment: an invented flat tileset lost all the board's
  charm and was rolled back. Put the before beside the after and ask which is more charming, not only more readable.
- Side-view pixel tokens on an iso board read as flat stickers, and pieces nearly a tile wide swamp the map. Block
  tokens a third of a tile wide (3 x 3 footprint, 2-4 layers) in the board's iso read as pieces on a board.
- Zoom out with the camera, not by growing the pieces: one camera distance for every map, the world continuing past
  the battlefield in the palette's shadow tones so the lit board reads at once.
- Judge pieces standing in the real scene (`--on`), never only on a swatch.

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

**Lit side view** (`pixling guide reel-lighting`): image -> walk take across a locked 16:9 frame -> keyed frames
-> PATINA colour + normal maps -> standard 2D lights (Godot, Unity). The lighting is standard; the work is making
the maps steady. Raw per-frame AI normals flicker: take the colour from the video and average the normals along
the motion over neighbouring frames. Find the loop by pose matching, never blend frames, and advance the walk by
distance. Compared with image-to-3D (Tripo), the brushwork survives and no rig is needed, but you get one side
view and a new take per animation.
Any character and any clips (a travelling walk leads, an idle is the rest pose it stops into, other clips play
once): `pixling reel light new NAME` -> `start` -> `frames` -> `loop` -> `patina` (prints the CU, `--yes` spends) -> `build`
-> `check` -> `demo`; `export SHEET DIR --engine web|godot` copies the sheet (`pixling.lit-sprite` v1: colour +
normal atlases + json) and a drop-in player (reel/light_runtime: litsprite.js, lit_sprite.gd) into a game.

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

## fp
A place you walk through in the browser, in two views. **The painted view opens:** one composed third-person camera,
the place painted in layers (sky, ridges, trees, hill) about 2.5 screens wide: built in Blender from painted cards,
pixelized back into clean clusters and committed, and a canvas runtime that draws only what moves (a small walker
who goes anywhere on the snow, her footprints, snow, breath) while the view follows her. **The first-person walk** (`walk.html`)
is a Python kit + layout in WebGL, palette-locked pixel art with real shadows. Hushfall (`styles/hushfall.json`) is its
first style, First Snow its first place.

**Pick it for** a scene that should feel like a place you are in: a title screen, a story beat, a walk to a goal. The
painted view when it must look crafted (the camera only pans across one fixed render, so every cluster is placed);
first person when you must turn and look round. Not for sprites (use spec) or 2D maps (use map or iso).

**Steps**
```
pixling fp layers --t 1,12,22,34          # the painted view: stills along the walk -> layers_sheet.png (~10 s)
pixling fp layers --t 6,14 look=pixel     # the same stills on the art grid, to compare (nofx=1: no snow)
FP_BPY=/path/python-with-bpy pixling fp paint   # re-render the painted layers into fp/art/<layout> (~4 min, cached)
pixling fp assets                         # the kit: one builder per asset family (fp/kit/*.py)
pixling fp cards car:0 pine:3             # each asset alone on snow, from a few angles: look at cards_sheet.png
pixling fp walk --t 0,8,16,26,40          # screenshots along the auto-walk: look at walk_sheet.png
pixling fp shot "t=40&pause=1&look=30,-5" # any view; debug=shadow shows the sun and shadow terms
pixling fp build ; pixling fp serve       # play it: http://127.0.0.1:8770
pixling fp bundle                         # the painted view as ONE html that opens from disk: out/fp/first_snow/first_snow.html
```
**How the painted view works.** `fp/place.py` is the place in metres and the one camera that sees it (a long lens
pulled well back, a near-field lens that draws the ground at the bottom bigger): terrain, flagstones, rope fence,
pillows, spruces, poles and wires, the car's spot and the walk route, all from one seeded stream (the wider world past
the composed core draws after it, so the core never moves), and where she can walk (`walk_grid`, `walk_blocks`). `fp/paint3d.py`
exports it to Blender (`fp/blender/first_snow.py`), which builds it with the painted engine's technique: spruces as
tiers of alpha dab cards with sphere normals under snow shelves of puff cards, cumulus as puff cards lit as one mass,
a snow terrain with calm blurred normals and real cast shadows (thin posts and poles cast none), 3D flagstones. It
renders data, not colour (R lit value, G material id, B depth), once per layer; Python steps each material into its
Hushfall ramp (tune in seconds, no re-render). What opens (`fp/hd2d.py`) keeps the render at the screen's own size
(2x for 720p, a 3x render for 1080p, 1:1 on screen), stepped per render pixel with a few cleanups (a gouache stroke
on the snow field, the cumulus's own dabs), and lays the hand-placed things back on top as crisp art pixels: posts,
poles, the hand-drawn car, the ropes and wires refitted as cubics, the lamp's light (`fp/draw2d.py`). The art-grid
version (2x2 block mode, cluster cleanup) is `?look=pixel` and the runtime's colour and depth lookups. The walker is a
Blender-lit sprite sheet the same way (`fp/blender/walker.py`: eight headings, she turns and the light stays). Everything
is committed in `fp/art/first_snow/`, so `fp build` needs no Blender. `web/layers.js` (canvas 2D) opens on the sky,
tilts down once, then follows her sideways with a dead zone, every layer at a whole column of its own (parallax); it
mirrors `place.proj` from `scene.json`, walks her on the `walk.bin` grid (height, surface, room, lamp) round the
posts, ropes, spruces and the car, and draws the walker, her prints, breath, exhaust and snow (three depths of
hand-made flake stamps that always fall) on the art grid. The
built `layers/` folder is static with relative paths (list in `fp/README.md`); `fp bundle` (`fp/bundle.py`) packs it
into one html that opens from file:// or a sandboxed frame (every load goes through the runtime's `asset()` and a
table of data: URIs; audio through the page's import map; the font in the CSS). Lesson: painterly masses plus crisp
art-pixel actors reads as crafted; pixelizing the masses reads as a filter, and every cleanup that merges the render's
dabs costs the painterly read.

**How the first-person walk works.** An asset is a `Mesh` whose vertices name a material (a ramp), a snow catch and baked AO, plus 1 px
`Lines` for ropes, wires and grass. The layout builds the terrain heightfield, the stair, the placements and the walk
route; `build` packs it into `world.json` + `world.bin`. The runtime (three.js, vendored) shades the world into a
cubemap from a probe snapped to a 1 m grid and draws every texel as a square in the world (texel splatting), so art
pixels stay on the surfaces while you move. It draws the sky in direction
space with sky-pinned dither, the world at ~216 px tall with `v = ambient + sky + sun * terminator * shadow` picking a
ramp band, snow on up-facing faces, a pink rim on edges turned to the sun, headlight spill with a dithered fringe and
stepped fog; then 1 px lines, snow and bokeh particles and the breath; then the palette snap. The walker auto-walks the
route until any input takes over; head motion is a breathing rise when idle and a small dip, sway and roll per step.

**Code:** painted view: `fp/place.py`, `fp/paint3d.py`, `fp/hd2d.py`, `fp/draw2d.py`, `fp/blender/`,
`fp/web/layers.js`; first person: `fp/web/fp.js` (runtime), `fp/mesh.py` (shapes), `fp/kit/` (assets),
`fp/layouts/first_snow.py` (its place); both: `fp/build.py`, `fp/shot.py`; one file: `fp/bundle.py`. **Read:** `pixling guide fp`, `pixling styles hushfall --how`.

**Learned**
- Shadows only read when the sun rakes across the ground: a sun behind the hill leaves the whole slope one tone.
- Blender to pixel: render ids and lit values, never colours, then ramp, mode-downsample and clean in Python; dabs must
  land at 3-4+ art px. Thin things (posts, poles) cast no shadow: their long stripes across the snow read as noise.
  What speckled: colour renders snapped to the palette, cards smaller than ~3 px, real self-shadow inside a tree (one
  silhouette), and cleaning every pixel at once (a checker just swaps). What made it clean: per-clump sphere normals
  so a clump shades as one mass, a constant ramp per material, red-black cluster cleanup, 2 px minimum snow bands,
  and the thin things (posts, ropes, poles, the car) drawn as pixel sprites over the render, not rendered.
- Snow banks that rise high on the sun side shade the whole hollow; keep side terrain low or the sun higher.
- Bokeh and breath can't be blended translucency: the palette snap swallows it. Solid cores with a dithered rim read.
- Thin things as 1 px lines, never as thin tubes: tubes break up and shimmer at 216 px.
- A pixel filter on a 3D frame makes the pixels crawl across every surface as the camera moves. Snapping the camera
  only fixes orthographic views. Texel splatting (shade into a grid-snapped cubemap, draw each texel as a square in
  the world) keeps the art pixels on the surfaces through turns, head bob and walking.
- Stable is not enough: a 216 px 3D frame through a pixel filter still reads as a "3D pixel filter dithering mess"
  (blocky texels up close, toon bands, snow noise, shimmering wires). A painted, locked frame with few big value
  masses, detail only where the eye lands, and a small figure in a big world is what feels like a place.
- In the painted view, every dithered or per-pixel effect read as noise: white plus-shaped flakes read as glitter,
  holes inside the sun's pink read as camouflage, fanned grass reads as 'W' glyphs. Solid masses, tufts that lean
  together; snow as lobed clumps with a pale core and a teal rim on the shade side (round discs read as bubbles, a
  fringe of single edge pixels as burrs), falling at least a pixel a frame. Light is a low lobe taken by every layer alike; a glow on one layer shows that layer's edge.

## arena
Painted battle maps for your own units: a painterly map with moving layers and a complete, checked game level beside
it. One shared engine (`arena/*.py`) and one module per map (`arena/maps/NAME/`: place, palette, biome, level hooks,
Blender builders, the committed art). Two maps ship: **Hushfall Crossing** (a winter ledge over a sea of dusk cloud,
two camps, a ruin terrace, a bridge over a corridor; 40 degrees) and **Emberleaf Hollow** (a kill map in a clearing of
red-crowned trees on a forested plateau; 68 degrees, 51.2 px/m).

**Pick it for** a tactics, MOBA or arena game that needs a map to fight on, not just a picture: the level comes with
collision shapes, a nav grid with clearance per unit radius, line of sight and gameplay zones, and a check that the
two sides are fair. Not for open worlds (use map) or scenes you walk through (use fp).

**Steps**
```
pixling arena maps                         # the maps and whether their art is painted
pixling arena bundle --map emberleaf       # the viewer as ONE html: out/arena/emberleaf/arena.html (no Blender needed)
pixling arena export --map emberleaf       # level.json for your units: walk grid, colliders, nav, LOS, spawns, routes
pixling arena check                        # reachability, fairness, spawn safety, stuck tests, colliders on the art
pixling arena lint ; pixling arena zones   # the zone budgets measured on the art; zone map, grey and squint to look at
pixling arena family                       # every map side by side at the same scale: one style family?
ARENA_BPY=/path/python-with-bpy pixling arena paint --map NAME   # re-render in Blender (~2 min at 1 sample)
pixling arena repaint --map NAME           # re-step the last render while tuning ramps (seconds, no Blender)
```
**How it works.** `place.py` is the map in metres: an orthographic camera from a fixed family (40 or 68 degrees, the
same sun, about 60 m across), the walkable as signed distances, the terrain, and `layout()` with every thing's kind and
**depth zone** (focus, playfield, frame, backdrop, vista, sky). Blender (`arena/blender/arena.py` plus the map's
builders) renders data, not colour: lit value, material id, depth and zone id. The painter (`paint.py`) steps each
material through hand-picked ramps under the zone's budget (`zones.py`: value window, saturation, haze, strokes and
cleanups), so the back is quiet by value and haze while it keeps its strokes. `layers.py` bakes the tree sway as held
tile frames (only the changed 32 px runs are stored) and the clouds as wrap-around drifting strips. `level.py` builds
`level.json` v4 from the same place data; `game.py` (Python) and `web/level.js` (browser and node) answer the same
queries (`find_path`, `los`, `move`) with the same code, checked against each other. The viewer (`web/arena.js`,
canvas 2D, no libraries) draws the layers with parallax in whole pixels plus the ambience (snow, fires, leaves,
glints) and overlays for sizing yours: grid, zones, scale people, colliders, nav, LOS, paths, a test agent.

**Code:** `arena/place.py` (the active map), `arena/paint.py`, `arena/zones.py`, `arena/layers.py`, `arena/level.py`,
`arena/game.py`, `arena/check.py`, `arena/web/`, `arena/blender/arena.py`, `arena/maps/`. **Read:** `pixling guide arena`
(the viewer, using the map in your game, making a new map step by step), `pixling guide arena-style` (the shared rules).

**Learned**
- A battle map is an information hierarchy: units and effects loudest, then the objectives, then a calm light
  playfield, a darker frame, a hazed back. Budget each depth zone (`lint`) instead of judging pixels one by one.
- Keep hue bands free for the units (at least two, 20+ degrees wide; gold is free on every map so far) and let the
  sun own the pinks. A playfield in two low-chroma tones lets units of any strong hue pop.
- An orthographic camera does not shrink distance: the back is a stage set placed by screen height, its ridges sunk
  and built smaller the further back, with a window kept open over the play.
- Render ids and lit values in Blender and paint in Python; tuning a ramp then takes seconds, not a re-render.
- Mirror whatever changes how people move, and the noise of the outline and terrain too, so the routes are exactly
  fair; `check` measures it. Every collider must sit on its painted prop.

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

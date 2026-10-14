# Styles: how we make an art style

pp makes environments, buildings and animals. Full-size characters are out of scope for the launch styles; small
iso board pieces (units, creatures) are block tokens in the scene's own hand (`pixling pipelines blocks`).
`pixling styles NAME --how` prints a style's section below with its code and lab notes; `pixling pipelines style`
is the recipe for a new one.

A style is three things, and only the first one is colour:

1. **Palette:** ramps by role (ground, water, foliage, wall, roof, stone, wood, glow, the darkest ink).
2. **Hand:** how pixels are made: camera, pixel density, shading, line, cast shadows, mark-making, detail density.
3. **Vocabulary:** its own kit of buildings, plants, ground and water.

Recolouring one style never makes a new style; it makes a season or a biome of the same style. Every style must
work across several biomes (forest, coast, snow, desert...): **one style, many biomes.**

## The launch styles

| Style | Camera | Hand | Biomes | Build |
|---|---|---|---|---|
| **Vista** (flagship) | painted aerial map (`pp.map`) over SDF props | muted painterly masses, cream walls, terracotta roofs, teal sea, tiny figures | Highgate, Vale world map | `python3 tools/vista/build.py` |
| **Crisp Tactics** | exact 2:1 iso (`pp/iso.py`) | three flat face tones, soft selout line with corner AA, cube canopies, slab stone with masonry, one orange accent | valley, autumn; harbour | `pixling world tactics` |
| **Flat Minimal** | exact 2:1 iso (`pp/iso.py`) | two world hues + a warm window accent, flat faces, no line, flat long shadows, chunky pixels | forest island, dunes | `pixling world flat` |
| **Hushfall** (fp) | a wide third-person painting in layers she walks anywhere in, the view following (`fp/`); first person as a lab | muted teal snow, slate-violet stone, navy spruce, salmon cumulus, the sun's hot pink, a mint headlamp glow; Blender painted cards pixelized to clean clusters, no dither | winter dusk (First Snow) | `pixling fp layers` |

Walk around all of them: `python3 tools/explorer/build.py` writes `out/explorer.html` (run the two style builds first).

**Legacy** (kept, not in the gallery): `sunmeadow`, `duskborne`, `vermilion`. They are character-era styles with no
environment painters; their specs still build and the snapshot gate still covers them.
**Parked:** Saffron (thick ink line) and Marsh (painterly clusters) were prototyped and look promising; Frost becomes
vista's winter season (planned: flat-face shading and swept cast shadows in the vista painters). Notes and contact
sheets: `research/styles/`.

## The workflow

1. **Refs board.** Mood images (generated with Scenario, or your own). They are references only and never ship;
   third-party art is mood only and never goes in a gallery.
2. **DNA sheet.** Name the style's hand on each axis of the contract below, by looking at the refs. One line on what
   makes it distinct from every other style.
3. **Hand modes.** Find which engine stages the hand needs (line mode, shading mode, shadow shape, pixel size,
   brushes). Build a missing stage once, opt-in, so it serves every later style; existing assets stay byte-identical
   (`tools/snapshot.py`).
4. **Kit.** The style's own buildings, plants, ground, water and animals, from scratch. Never borrow another style's
   kit: shapes are where styles really differ.
5. **Calibration brief.** Every style is judged on the same brief, made with its own kit: *a small settlement at a
   water's edge, three buildings (one a ruin), a path and a bridge, a stand of trees, a field or garden, a deer and a
   wading bird, smoke, water and birds moving.* Then a second biome in the same hand.
6. **Review card.** The scene at game zoom, the target ref beside it, a greyscale strip and an 8x crop of houses,
   trees and shore. Run `python3 -m pp pixcheck <scene>_1x.png --mark marks.png` on the 1x render. Judge by eye.
7. **Explorer.** Walk it (`tools/explorer`). It is the honest test: does it feel like a place?
8. **Vote.** The person who owns the look says yes, maybe or no per style, with what to fix first.

## The style contract

Each style declares:
- **camera** (painted aerial map, exact iso, ...) and **pixel density** (unit size, how much world fits on screen);
- **light:** key direction and shadow tint; time of day is a grade over the map, not a repaint;
- **shading mode** (banded, flat per face, clusters, ...), **line mode** (none, self-outline, soft selout, ink),
  **shadow mode** (soft contact, long flat projected shapes, ...) and **texture marks** (tufts, moss, masonry, ...);
- **palette roles** in `tools/make_styles.py` (content names roles, never hex);
- an **accent** with one owner (`"accent": {"ramp", "owner"}`): windows, awnings, sails, roofs of one family;
- a **kit**: one painter or builder per material (terrain, water, canopy, buildings, props) and an ambient set;
- **animal motion:** held keys on twos, slow walks.

A style is incomplete, and does not ship, while any material it uses falls back to another style's painter.

## The shared taste layer

True for every style. E = the engine enforces it by construction, R = checked by eye on the review card,
A = guidance for the agent.

1. **One pixel grid.** One texel size, integer placement and zoom, nothing rotated or scaled live, no partial alpha. E
2. **Closed palette.** Every pixel is a ramp entry; effects posterise last. E
3. **One light per scene.** One key direction for every asset and shadow; asymmetric parts are re-shaded, not
   mirrored. E
4. **One scale.** Everything derives from one unit; trees and landmarks get one declared compression. Animals may get
   a declared enlargement in small styles so they read (Flat deer ~1.3x, Tactics stag ~1.6x). E
5. **One painter per material.** All trees in a scene from one painter at one leaf size; the same for water, roofs,
   stone. E + R
6. **Values first.** Each plane is a calm value mass; the scene reads in greyscale and as silhouettes. R
7. **Quiet zones, one focus.** Detail and contrast where the eye should land; busy textures never touch.
   **Settlements cluster:** buildings group tightly around one landmark, with open space around the group. A + R
8. **Clean clusters.** No orphans, banding or doubled lines; stairs are 1:1, 1:2, 2:1. **Dither only where a style or
   the night grade declares it, never across large flat planes** (snow fields, water). E (`pp pixcheck`)
9. **Texture by density.** Variation drifts at 2-3 frequencies; only detail that reads at game zoom. A + R
10. **The accent has one owner** and covers few pixels. E
11. **Everything grounded.** Every object on the ground gets a contact or cast shadow along the scene light. E
12. **Ambient motion only.** Smoke, water, flags, birds and leaves move in whole pixels, in seamless loops. Nothing
    boils. E
13. **Animals on held keys.** On twos, held extremes, slow walks, far legs a rung darker. E + A
14. **Judge in place, by eye.** One review card at game zoom per build: one look, one fix. The bar is "do I want to
    be there?" R
15. **Meaning, not colour.** Windows, water and ground are known from the meaning layer (or the material image),
    never by matching rendered colours. E

## Crisp Tactics

- **Hand.** Exact 2:1 iso for map and props, so every edge is a uniform 2:1, 1:1 or vertical stair. World scale x2
  (`K = 2`), so diagonals are long even stairs. Three flat face tones (top, lit left face, shade right face). The soft
  line (`pp/iso_line.py`) sits inside each silhouette, is pixel-perfect (no L-corners), takes the style's ink on
  the shadow side and one tone darker than the face on the lit side (dropped where the form already contrasts), and
  gets one in-between palette tone at each removed corner. Ground stair corners get the same AA. Masonry courses
  are face decals in whole units, so courses are 2:1 lines and joints vertical.
- **Kit** (`tools/tactics/kit.py`): cube trees, tree pairs, stepped conifers, gable houses (pitch 0.5), arches,
  broken walls, pillars, stairs, a well, slabs, a ruined house, a bridge, market stalls, a windmill, boats, a pier,
  crates; stag, sheep, fox, heron. Ground detail: moss on stone tops (world-pinned), grass tufts, flowers.
- **Biomes:** valley and autumn; the harbour scene in both. In autumn the orange accent leaves the awnings (they turn
  teal) and stays on sails and mill blades, so the orange canopies don't compete.
- **Build:** `pixling world tactics` (= `python3 tools/tactics/build.py`) -> `out/tactics_valley`, `tactics_autumn`, `tactics_harbour_valley`,
  `tactics_harbour_autumn` (noon_1x.png, the valley and harbour as a 24-frame noon_1x.gif) and the stag walk sheets
  `out/tactics_stag[_autumn]/`. Re-render one scene: `python3 -m pp.iso out/tactics_valley/scene.json --out /tmp/tv`
  (`--raw` drops detail, AA and line for before/after crops).
- **Weak spots:** canopies are plain cubes (a 1-unit top bevel would help), arches are stepped not round, the stag
  walks on two held keys, smoke is a thin column.

## Flat Minimal

- **Hand.** Exact 2:1 iso; terrain is a cell heightfield, island columns 6 px above the sea give the chunky earth
  band, water rings are iso-aligned bands. One flat tone per face, no line. Roofs, trees and palms don't cast;
  invisible box proxies cast for them, so every shadow edge is a lattice stair (flat, long shadows). A small map
  (256x164) shown big.
- **Kit** (`tools/flat/kit.py`): cabins with the gable in the wall (pitch 0.5) or flat roofs, stepped firs
  (pyramids with h = 4r), palms, a ruin, a bridge, a jetty, smoke; deer (~1.3x) and heron on held keys.
- **Biomes:** forest island (teal) and dunes (ochre on deep blue).
- **Night and dither.** `--hour night` maps each material face to a step of the style's night ramp, so silhouettes
  keep their value order; windows glow and throw flat iso light pools. `--dither night` is an option, off by default:
  it dithers only a 2-px rim around the light pools.
- **Build:** `pixling world flat` (= `python3 tools/flat/build.py`) -> `out/flat_forest`, `out/flat_dunes` (noon, night, night_dither; the
  forest also as a 24-frame noon_1x.gif) and the sheets `out/flat_deer[_dunes]/` (walk) and `out/flat_heron[_dunes]/`
  (idle).
- **Weak spots:** the island sits small in a lot of water, the river reads as a trench, windows are slanted iso
  parallelograms, smoke is stacked squares, the heron reads weakly, night is dark overall.

## Vista

The painted aerial map: `pp.map` painters for terrain, sea and forest canopy, SDF props from `tools/vista` kits, the
meaning layer, building states and hour lighting. Its rules and commands are in [ENVIRONMENTS.md](ENVIRONMENTS.md).
Next: seasons (summer, autumn, and winter from the Frost prototype) as biomes of the same hand.

## Hushfall

The first style of the `fp` engine. Made from one reference (a pixel-art winter dusk: a stair through deep snow up
to a parked car, pink sunset, bokeh snow; mood only, it never ships), so palette and mood follow it closely.

- **The painted view (what opens).** One composed camera that opens with a slow tilt and then only pans, following
  her across a world about 2.5 screens wide (the composed stair in the middle, climbing to an old estate parked on a
  plough-cleared road along the crest, the road a calm band with ruts and rounded plough ridges that leaves behind the
  tree band at both ends; spruce stands, a buried fence and a field fence out on the wings, the wires running on); the
  place is
  four layers (sky, far, trees, hill), built in Blender with the painted engine's technique (`fp/paint3d.py`,
  `fp/blender/first_snow.py`). What opens is painterly with pixel accents: the render stepped into its ramps at the
  screen's own size (soft dab masses, flat toon bands, no pixel grid), with the walker, snow, breath, posts, poles,
  the car and the wires as crisp art pixels over it. The Look button switches to the art-grid pixel version.
  Spruces are tiers of alpha dab cards whose clumps
  shade as one sphere, snow shelves of puff cards on top, buried cards darker, a gradient along the sun. The cumulus
  is puff cards in clumps, lit per pixel as soft spheres by the low sun behind it: lit salmon crowns, the face a
  step over the sage, violet bellies over a flat base, the sun's hot pink only on its top-right crown edge. Each
  material's lit value steps into its own ramp (no colour is rendered); 2x2 blocks take their most common colour and
  clusters are cleaned, so no speckle. Big calm value masses: one teal snow field with long raking shadows, one dark
  spruce band, one warm sky with a far hill and mist between. Thin things (posts, ropes, poles, wires) and the hero
  car are pixel sprites over the render; the walker is a Blender-lit sprite sheet in eight headings (her face shows
  when she turns to us), leaving prints a tone darker in the snow. Snow falls in three depths of hand-made stamps:
  specks far off, small clusters, and near broken clumps (a pale core, a ragged teal edge, a crystal or two come
  loose) that tumble. The first-person bullets below are the lab.

- **Hand.** Low-poly, flat-shaded facets in metres; light value `ambient + sky + sun * terminator * shadow` picks a
  band of each material's ramp (4-6 tones), so facets read as painted planes. One sun, low on the left (az -78°,
  12° up), with a real shadow map: long hard shadows rake across the snow and agree with every asset. Snow settles on
  any face that points up enough (world-pinned noise). Faces turned to the sun and seen edge-on take a pink rim that
  fades with distance; wires toward the sun catch it too. No outlines. Thin things are 1 px lines. Every pixel is
  snapped to the palette (OKLab nearest). The art pixels live on the surfaces (texel splatting from a probe on
  a 1 m grid), about 0.22° each, so they stay put while you turn, bob and walk instead of crawling.
- **Palette.** Teal snow (`#64848c` dominant), slate-violet shade, navy spruce, an indigo-plum car, a sage and rose
  sky with salmon undersides. The hot pink `#fc5084` belongs to the setting sun (ridge line, sky clusters, rims) and
  the tail lights; the headlights own a mint glow.
- **Layers in their own hand.** The sky is painted (sky.py): cumulus built from round puffs with scalloped lit tops
  and rose bellies, dithered soft, drawn as its own layer. Snow is fluffy and calm: open fields lit nearly flat (one
  teal mass broken only by shadows) and rounded `drift` pillows with a soft top highlight along the stair, on posts
  and on the car.
- **Dither** only where declared: the clouds' soft bands and specks, the lamp spill fringes, the breath and exhaust rims.
- **Kit** (`fp/kit/`): spruce built from stacked bough rings with snow shelves and drooping teeth (10-15 rings,
  per-instance value jitter), young spruce, dry grass tufts (lines), a lofted 70s estate car with a snowed-under
  roof load, headlights and tail lights that spill their own ramps, an idling exhaust; timber telephone poles square
  to their wires; round-capped rope bollards; a laid stone stair (light tops, dark noses, blue risers, seams).
- **Atmosphere.** Falling snow and a near shell of bokeh flakes, breath that leaves at walking speed so you walk into
  it, a gentle head bob (a dip per footfall, sway per stride, under a degree of roll), wind and snow-crunch audio.
- **Made by** a two-track artist workflow (nature: spruce, grass, snow, sky; made: car, poles, bollards, stair), each
  built by a senior artist, critiqued and improved by a senior reviewer, polished, signed off, then one art
  direction pass over the whole walk.
- **Build:** `pixling fp layers` (painted view stills), `FP_BPY=... pixling fp paint` (re-render the layers in
  Blender; they are committed), `pixling fp walk` (first-person screenshots), `pixling fp cards`
  (assets), `pixling fp serve` (play; opens the painted view).
- **Weak spots (painted view):** the frame is mid grey-teal at thumbnail size (the raw render's dark forest against
  a luminous sky is not back yet); the near spruces read a little as broccoli (no lit shelf fringe); the shadows in
  the bottom-left and the lower-right pillows end in fish and beak shapes; the car's wheel arches and tail-light glow
  are not hand-clean at 1080p; no hand-placed focal accents yet.
- **Weak spots (first person):** near spruce (under ~15 m) show big flat diamonds in the bough fringe; looking back from the crest the
  second sky ridge is a plain band; one place (First Snow) so far.


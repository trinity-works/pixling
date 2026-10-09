# Styles: how we make an art style

pp makes environments, buildings and animals. Characters are out of scope for the launch styles.
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

# Flat Minimal v2 (2026-10-07)

This addresses the user's two round-2 notes: the map wasn't isometric under isometric props, and the pixels were
dirty. All work is in `proto_flat/repo`, a copy of `proto/repo`; the real repo was not touched.

## What changed

- **New camera `iso_exact` (`pp/iso.py`, opt-in).**
  - The whole scene is convex polytopes: terrain columns, the water slab, props and animals. Each pixel casts one
    orthographic ray at its centre, and the nearest face wins with one flat tone.
  - Projection is classic 2:1 pixel iso (`sx = x - y`, `sy = (x + y)/2 - z`). Every edge along an iso axis is
    therefore an exact 2-px stair, and verticals are vertical.
  - Nothing is supersampled or resampled: the image is exact at 1x and only ever scaled by an integer (x4 here).
  - Map and props now use one projection, so the perspective mismatch is gone by construction.
- **Terrain is a cell heightfield** (8x4 px diamonds).
  - Island columns stand 6 px above the water slab, giving the chunky earth band of the reference.
  - The river is shallow columns.
  - Water rings are iso-aligned bands (Chebyshev distance to land), and coast cells are cleaned so there are no
    1-cell spurs.
- **Cast shadows are exact rays toward one light on the -y iso axis.** Only boxes cast, or invisible box proxies
  for roofs, trees and palms, so every shadow edge is also a 2:1 stair: flat, reference-like shadow shapes. The
  island throws its cliff shadow onto the water.
- **Kit built on the lattice** (`tools/proto/iso_flat.py`):
  - **Cabins:** the gable is part of the wall. Roof pitch is 0.5, the only pitch besides 1.5 whose gable edges stay
    clean, and it shows both roof planes.
  - **Windows and doors** are face decals in 2:1.
  - **Trees:** stepped firs built as frustum pyramids with h = 4r, giving 2:1 silhouettes, two-tone facets and a
    2-px tip instead of a 1-px spike.
  - **Other pieces:** palms with single-tone fronds, a ruin, a bridge, a jetty, smoke as whole-pixel cubes.
  - **Animals:**
    - The deer is built from boxes at a declared ~1.3x enlargement, and grazes with a held head-down key.
    - The heron dips the same way.
  - **Biomes:** forest island and dunes (flat roofs, palms, ochre on deep blue) share the same hand and kit.
- **Night grade with optional dither** (`--hour night [--dither off|night]`; default off).
  - Each material face maps to a step of the style's night ramp. This fixed v1's lost silhouettes: walls,
    roofs, land and trees keep their value order.
  - Windows glow and cast flat iso light pools.
  - `--dither night` adds a checker only on a 2-px rim around the pools, never on a flat plane.
- **`tools/proto/pixcheck.py`:** a cleanliness checker that counts orphans, 1-px whiskers and broken stairs, and
  writes a marked image.
  - v1 map (128x112): 24 orphans, 179 whiskers, 52 broken stairs. Its edge shifts were mostly irregular 1-px steps.
  - v2 forest (256x164, 3x the area): 9 orphans, 116 whiskers, 21 broken stairs, with edge shifts dominated by the
    clean 2-px stair.
  - The whiskers that remain are mostly legit ends of 1-px lines: deer legs, antler, beak, window corners.
  - Most of the remaining "broken stairs" are corners where an edge turns.
- **Vista is untouched.** `tools/snapshot.py check base` in the copy reports 144 specs, 0 changed. Only new files
  were added (`pp/iso.py`, `tools/proto/iso_flat.py`, `tools/proto/pixcheck.py`, `specs/proto/flat_iso/`).

## Verdict by eye

- **Fixed:**
  - Perspective is now consistent.
  - Every edge on houses, trees, cliff, shore, rings and shadows is a clean stair at 8x.
  - It reads as a small iso diorama, close to `flat_teal`.
- **Dunes** is the strongest card: palms, flat-roof houses and violet-blue water.
- **Still weaker than the ref:**
  - The island sits small in a lot of water. A tighter frame or a bigger settlement would help.
  - The river reads as a brown trench more than as water.
  - Windows are slanted 2x3 parallelograms, which is correct iso but less cosy than the ref's upright windows.
  - Smoke is stacked squares.
  - The heron reads weakly.
  - Night is very dark overall; the style's night ramp could be lifted a step.
- **Note:** the exact-iso polytope camera would also be the right base for a Crisp Tactics implementation, which
  is iso too.

## Cards (`proto_flat/cards/`)

- `flat2_forest_noon.png`, `flat2_dunes_noon.png`: map at 4x, the target ref, and a 1x crop at 8x.
- `flat2_forest_night.png` (dither off), `flat2_forest_night_dither.png`, `flat2_dunes_night_dither.png`.
- `flat2_forest_ambient.gif`: 24 frames of smoke, water glints and deer/heron held keys.
- `compare_v1_v2.png`: v1 vs v2 maps and crops, with the pixcheck numbers.

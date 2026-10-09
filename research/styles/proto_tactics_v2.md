# Crisp Tactics v2: smoothing the zig-zag (2026-10-07)

Built in a copy (`proto_tactics2/repo`, taken from `proto_tactics/repo`, plus Flat v2's `pp/iso.py`). The real repo
was not touched. Logs are in `proto_tactics2/logs/`; nothing was left in /tmp.

## What caused the zig-zag
1. **Approximate iso.** v1 rendered SDF props at a 45° yaw through the cabinet projection. Edges came close to 2:1,
   but runs wobbled (3-2-2-3) and roof rakes sat at about 1:1.5, so every diagonal jittered.
2. **A doubled-corner line.** The selective line was a 4-connected 1 px ring drawn outside the silhouette. Each
   stair step got an extra L-corner pixel, so the line thickened at every step.
3. **Maximum contrast.** A near-black line on light grass and cream made every jag visible, and small props made
   the edges short, so they were mostly steps.

## What fixed it
- **Exact iso camera (`pp/iso.py`).** Every prop is lattice boxes or polytopes with integer coordinates, one ray per
  pixel centre and no resampling. All edges are uniform 2:1, 1:1 or vertical runs. Roof pitch is 0.5, so rakes
  land on clean angles.
- **World scale ×2 (`K = 2`).** Props carry twice the pixels, so diagonals are long, even stairs rather than a few
  big steps.
- **Soft line (`pp/iso_line.py`, opt-in via the scene's `"line"` key):**
  - The line sits *inside* each object's silhouette, so sprites still composite on any ground.
  - It is pixel-perfect: L-corners are removed, so every step is a single pixel.
  - It uses selout. Bottom and right edges (contact and shadow side) take the style's ink (dark teal, not black).
    Top and left edges take one tone darker than the face they wrap, and are dropped where the form already
    contrasts strongly with what is behind it.
  - Corner AA: each removed corner gets the nearest palette colour to the 50% mix of line and fill, so the palette
    stays closed.
- **Terrain AA (`soft_terrain`).** Stair corners between two ground colours (shore, path, plaza, shadow edges) get
  one in-between palette tone.
- **Masonry as face decals.** Courses run every 8 units with staggered joints, pinned to the face, so courses are
  clean 2:1 lines and joints are vertical. Pillars get courses only.

## Round-3 notes applied
- **Ground detail.** Organic two-tone grass patches on the cell lattice (smoothed, no 1-cell spurs), plus tufts and
  flower clusters at fixed screen spots. Moss on stone tops is world-pinned in 2×2-unit blocks, so it never swims.
- **Stalls read as stalls:** a counter with goods, four posts and a striped awning.
- **Bigger animals:** a declared readability enlargement, about 1.6× the Flat deer at ×2 world scale. The stag is
  now about 40 px tall.
- **Autumn accent owner.** In autumn, the orange accent moves off the awnings (stalls become teal and cream) and
  stays only on sails and mill blades, so the orange canopies don't compete with it.
- **Composition.** Both scenes are framed on the settlement. The harbour is a corner quay with a pier, boats, the
  market and a windmill on the quay corner. The valley is the calibration brief: a ruined courtyard, five houses,
  the river with a bridge, a field with sheep, a stag, a fox, a heron in the river, smoke, glints and long dark-teal
  cast shadows.

## Files (in the copy)
- `pp/iso.py`: the Flat v2 camera, plus object groups (`grp`), masonry decals (`course`/`brick`), merged ground
  rows (only edge rows cast), and HX/HY/T/GRP in the render layers.
- `pp/iso_line.py`: new; `soft_line` and `soft_terrain`.
- `tools/proto/iso_tactics.py`: the kit (cube trees, pairs, stepped conifers, houses, arches, broken walls,
  pillars, stairs, well, slabs, ruined house, bridge, stalls, windmill, boats, pier, crates, stag, sheep, fox,
  heron) and the valley and harbour scenes, each with an autumn biome.
- `tools/proto/render_tactics.py`: the render pipeline (detail, terrain AA, soft line, glints, GIF frames;
  `--raw` for comparisons).
- `tools/proto/tactics_sprites.py`: the stag walk sheet, 8 rows × 4 frames. It uses the 4 true iso facings, with
  the screen cardinals borrowing the nearest diagonal.
- `specs/proto/tactics_iso/*.scene.json`: the generated scenes.

## Outputs
- `cards/before_after_8x.png`:
  - Top row: v1 crop against the matching v2 crop.
  - Bottom row: the same v2 crop, raw (exact iso only) against final.
- `cards/tactics2_{valley_noon,harbour_noon,autumn_valley,autumn_harbour}.png`: each scene at 2×, with the target
  ref and a 6× crop. Overview: `cards/compare.png`.
- `cards/stag_sheet.png`.
- `explorer/`: drop-ins for the explorer:
  - 1× scene PNGs for all four scenes, plus 24-frame 1× GIFs for the valley and harbour.
  - Stag walk sheets with their JSON: `tc_stag2` (valley) and `tc_stag2_a` (autumn).
  - Same JSON layout as the other deer sheets: frame 52×56, anchor (26, 46), 8 directions, walk at 140 ms.

## Check
- The copy's `tools/snapshot.py check base` against the original baseline gives **218 specs, 0 changed**. The new
  entries are prototype specs and the tactics_iso scenes.
- The vista `highgate_town` and merge `meadow` stills are byte-identical to the baselines (`cmp`).
- None of the new code paths runs for vista: `pp/iso.py` and `pp/iso_line.py` are only reached through tactics
  scene specs.

## Still weaker than the refs
- Canopies are plain cubes. The ref's trees have a slightly rounder top edge and visible trunks below dense crowns;
  a 1-unit bevel on the top edge would help.
- Arches are stepped, not round. A round soffit needs a non-convex shape (several small boxes) or a decal.
- The stag walk is two held keys with small leg moves. A third key would make it read more as a walk.
- Smoke is a thin 2 px column, and the GIF only animates smoke, glints and animal holds.

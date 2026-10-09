# Saffron prototype (2026-10-07)

Built in a copy (`proto_saffron/repo`, taken from the Frost/Flat prototype copy). The real repo is untouched, and
build logs went to `proto_saffron/logs`, not /tmp.

Cards are in `cards/`:
- `saffron_<biome>_noon.png` for desert, valley and snow: the scene at x3, the target ref inset, a greyscale strip,
  a 4x crop and the kit sheet.
- `saffron_<biome>_crop4x.png`: the 4x crops on their own.
- `compare.png`: all three cards together.

## What was built (in the copy)

Engine (all opt-in, set by the style or the region):
- **`pp/shade.py`, edge mode `"ink"`** (`"outline": {"mode": "ink", "color", "width": 2, "inner": 1, "crease",
  "inner_depth", "small"}`), in `_ink()`. It draws one ink colour:
  - a ring `width` px wide outside the silhouette. It grows by alternating 4- and 8-neighbour steps, which keeps
    the stepped corners clean and rounded. The ring travels with the sprite, so the sprite composites on any
    ground.
  - 1 px lines at the big plane breaks: material changes, a part in front of another part, and sharp turns of
    one surface (box corners, eaves). Each line sits on the farther or darker pixel, so the nearer shape keeps its
    size.
  - frames around windows. Window and emissive materials take no line themselves.
  - material flag `"ink_inner": false`, which keeps crop rows and soil quiet.
  - `small` keeps tiny sprites to their ring only.
- **`pp/map.py`, region `"ink": px`** (`_ink_edge`): the ink line along the inside of a region's edge, used here on
  river banks. The mask is smoothed first, so the line has no spurs, and the map border is padded, so it is never
  an edge. `"ink_sides": "south"` is also available.
- **`pp/map.py`, style `"shadow_of"`**: maps each ground colour to the style's shadow colour (violet), all in a
  `shade` ramp, so the palette stays closed. Cast shadows and sprite shadows use it.

Style (`tools/make_styles.py`, `saffron(biome)`) writes `saffron`, `saffron_valley` and `saffron_snow`:
- one ink colour (#2a1a1e), flat-face shading, light from the upper right (shadows fall down-left)
- violet shadows per biome
- an awning accent owner (awnings, banners, doors)

Kits (`tools/proto/saffron_kit.py`): one hand, a vocabulary per biome, all at one world scale (S = 1.6) and one
yaw (-30).
- **Desert:** 4 stacked flat-roofed adobe houses with parapets and striped awnings, a domed hall with a minaret,
  a ruin, 3 palms (curved trunk, 8 drooping fronds), rocks, 2 fields, a bridge, a jetty, a well, a heron and a deer.
- **Valley:** 4 timber houses under thatch (porches, chimneys), a long hall with a stone tower, a ruin, 4 broadleaf
  trees (5-7 clumps each, so the ink line separates them into clusters), rocks, 2 fields, a stone bridge, a jetty,
  a heron, a deer and a fox.
- **Snow:** 3 timber or stone houses under snow plus one flat stone block, a stone hall with a tower, a ruin with
  snow caps, 3 tiered conifers with snow caps, snowy rocks, a snowed field, a wooden bridge, a jetty, a heron, a
  deer and a fox.
- Fields, bridges and jetties are sprites at the house yaw, so the ground pieces share the buildings' perspective.
  This is the lesson from Flat Minimal's perspective complaint.

Maps (`tools/proto/saffron_maps.py`): one layout brief built three times:
- a spline river with inked banks and stepped bank tones
- the far-bank cluster packed around the landmark, and a near-bank hamlet with the ruin
- a path crossing the bridge, fields, tree stands, a deer and a heron in the shallows
- glints only on the water, smoke on the valley and snow maps, and birds

## Verdict by eye

- **The thick line works, and it works for games.** Every sprite carries its own clean 2 px stepped ring and 1 px
  plane lines. At the 4x crop there are no orphans, the corners are clean and the walls read crisply. Banks carry
  the same ink, so terrain and sprites read as one drawing.
- **Valley is the closest to its ref:** thatch clusters, clumped broadleaf trees, a stone bridge over an inked
  teal river, fields at the house angle.
- **Desert** reads well: adobe blocks with parapets, the dome and minaret, violet shadows. Palms are good but
  sparse compared with the ref.
- **Snow** reads as the same style in a third biome: white roofs, grey stone, conifers, violet shadows on snow.
- **Trees improved on round 1:** valley canopies are inked clusters, not blobs. Palms read as palms at game zoom.
  Conifers read but are generic.
- **Weaker than the refs:**
  - The refs pack 15-25 buildings; ours have 8-11, so the settlements feel smaller.
  - Awnings are only a few pixels.
  - No camels or goats: we reuse the deer.
  - The snow ref's cracked ice is missing (the ice is flat bands).
  - The ridge line on gable roofs breaks into dashes in places.
  - The desert lacks the ref's mesas (no cliff ink yet).

## Engine stages proven (to port behind the real snapshot gate)

1. Edge mode `ink` in `pp/shade.py` (`_ink`), plus the material flag `ink_inner`.
2. Region `ink` in `pp/map.py` (`_ink_edge`), with mask smoothing and border padding.
3. Style `shadow_of` (coloured cast shadows from a closed shadow ramp) in `Pal`.

They depend on the Frost/Flat stages already in this copy: `flat_face` shading and swept cast shadows.

## Check

- `tools/snapshot.py check base` in the copy, against the pre-prototype baseline: **194 specs, 0 changed**. The
  new specs are NEW, and every pre-existing spec is byte-identical.
- The vista `highgate_town` and merge `meadow` map stills are byte-identical to the baseline.
- The duskborne, sunmeadow, vermilion and vista style JSONs are unchanged.

## Not done

- Cliff and mesa ink (the land `cliff` face is not inked yet).
- Cracked-ice and dune-ridge painters.
- Dusk and night for Saffron.
- An ambient GIF.

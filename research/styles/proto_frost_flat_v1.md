# Frost + Flat Minimal prototypes (2026-10-07)

Built in a copy of the repo (`proto/repo`); the real repo was not touched. Cards are in `proto/cards/` (`compare.png`
is the overview, plus two ambient GIFs).

## What was built (in the copy)

Engine stages (all opt-in, set by the style; existing assets unchanged, see the check below):
- `pp/shade.py`, **shading mode `flat_face`** (`"shading": {"mode": "flat_face"}`): one tone per face straight from
  the light. It turns off highlight capping, the sky gradient and same-material value separation. Far-leg darkening
  stays (shared rule 13).
- `pp/shade.py`, **edge mode `none`** (`"outline": {"mode": "none"}`): no dark or rim edge pass.
- `pp/map.py`, **swept cast shadow** (`"cast_shadow": {"dx", "dy", "sweep": n}`): the silhouette is dragged along
  the light in n steps, so a house throws one long, flat projected shape. The old `[dx, dy]` form behaves exactly as
  before.
- `pp/map.py`, **`rows` terrain kind**: furrows and planted rows, for fields and gardens in any style.
- `pp/map.py`: the cliff painter now accepts short ramps (2-tone styles). It is identical for 4-tone ramps.
- `pp/grade.py`, **night dither grade** (`python3 -m pp.grade map.json`, style key `"night"`): the Lantern Dither
  direction as a night mode for any style. Lightness picks a step on the style's night ramp, with flat steps and an
  ordered dither only in a narrow band at each seam. Windows glow and lift stepped pools around them.
- Pixel size needed no code. It is the style's unit: Flat Minimal is a 128x112 map with small sprites shown at x6,
  one grid for everything.

Styles (`tools/make_styles.py`; one function per family, a `biome` argument, one JSON per biome):
- `frost(biome)` → `frost`, `frost_thaw`.
- `flat(biome)` → `flat`, `flat_dunes`.
- Each declares its camera scale, light, shading, outline, shadow color, accent owner and night ramp, plus its own
  roles: timber/snow/ice/conifer/red/pane for Frost; bg/land/tree/wall/roof/cliff for Flat. Animals share one fur-ramp
  table per family.

Kits (`tools/proto/kits.py`, each style's own vocabulary; nothing from vista):
- **Frost:** 4 timber houses and a red barn. The ridge runs into the picture, so both snow planes show and the
  timber gable faces the viewer. Also a stave church (three tiers under snow skirts, a spire), a stone ruin with
  snow caps, 3 firs (faceted stepped tiers with a snow band on every skirt), a jetty, a fence, a heron with a head
  dip, and a deer (11 px) and fox (6 px) re-targeted from the sunmeadow specs.
- **Flat:** 2 cabins, a shed, a ruin, 3 two-tier conifers, a jetty, a heron and a deer (7 px). The dunes biome swaps
  in flat roofs and date palms.

Calibration maps (`tools/proto/maps.py`) follow the shared brief: water's edge, 3+ buildings (one a ruin) plus a
landmark, a path, a stream with a bridge, a tree stand, a field (`rows`) with a fence, deer, a wading bird, a fox,
smoke, glints and birds.

## Verdict by eye

- **Frost: yes, it survives a build.** Noon reads like `r1_frost`: black timber under bright snow, gable fronts in
  shade, one red barn, long blue projected shadows on the snow, a pale ice lake with a darker shore band, and snowy
  firs that match the church motif.
  - The **thaw** biome (same kit and hand, wet ground, dark meltwater, snow left on the roofs) clearly reads as the
    same style in another season. That is the "one style, many biomes" proof.
  - **Weaker than the ref:**
    - Houses are smaller relative to the scene. The ref is a closer camera.
    - No vertical plank texture on the walls.
    - Firs are regular and symmetric. They need jitter and variety.
    - The ref's pink dawn glow is missing: noon is neutral.
- **Flat Minimal: yes, closest to its ref.** The `user_5` mood works: dark teal water in stepped rings, a lighter
  teal island, flat dark conifers with flat swept shadows, brick cabins with mint roofs and warm windows, a quiet
  path and field.
  - **Dunes** (ochre island on deep blue, cream adobe, date palms) proves it isn't tied to one biome.
  - **Weaker:**
    - The island cliff is a thin dark line, not the ref's chunky earth band.
    - Palms throw long rectangular shadows, because the crown is swept straight.
    - The deer is barely a read at 7 px.
- **Night dither (stretch): promising, not finished.** It gives a pixel-native night with flat steps, dithered seams
  and warm windows.
  - In Frost the big snow fields sit on a seam, so whole areas dither.
  - In Flat the houses lose their silhouettes, because walls and land share one value at night.
  - It needs per-material value anchors, not only image lightness.
- **The dusk from `pp light`** works on both styles: windows light per building, now that Frost uses a unique pane
  colour. It is a generic grade, though, and greyer than either style would pick. A style-owned dusk ramp would
  read better.

## What didn't translate, and why

- **Window detection is by colour** (in `pp light` and `pp.grade`). Frost's first window colour matched the snow on
  the firs, so whole forests "lit up" at night. Every style needs a window colour nothing else uses, or the meaning
  layer has to mark windows.
- **The cone primitive has a rounded base.** It makes eggs, not fir tiers. Use `flat=True` (capped cone) for any
  stepped silhouette.
- **Steep roofs hide the back plane** under the cabinet projection (pitch over about 27°). Both planes only show
  when the ridge runs into the picture.
- **The swept cast shadow sweeps the whole sprite.** Thin trunks with wide crowns (palms) throw a rectangle. Better:
  sweep only the lower part, or project from the footprint.
- **The map painters still carry vista assumptions.** `land` patch, tuft and flower defaults, `path` pebbles and rim,
  and the `shore` foam all expect 4+-tone ramps or vista ramp names. Tuning them was possible through `tones`, but a
  per-style brush table would be cleaner (stage 5).
- **`size` re-targeting of the sunmeadow animals worked**, but their materials had to be stripped: spec-level
  material overrides index into the sunmeadow ramps.

## Proven stages, to port behind the real snapshot gate

1. `flat_face` shading mode and `none` outline mode (`pp/shade.py`). These are the core of Frost and Flat.
2. Swept cast shadow (`pp/map.py` `_cast_offsets`).
3. `rows` terrain kind, plus short-ramp tolerance in the cliff painter.
4. `pp/grade.py` night dither, as an experimental opt-in.

## Check

- `tools/snapshot.py check base` in the copy: **142 specs, 0 changed**. The snapshot dir was pointed at the
  scratchpad, not `/tmp/pp_snapshot`.
- Vista `highgate_town` and merge `meadow` stills are byte-identical before and after.
- The duskborne, sunmeadow, vermilion and vista style JSONs are unchanged.

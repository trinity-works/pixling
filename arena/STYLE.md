# Arena maps: the shared style rules

Every arena map (Hushfall Crossing, Emberleaf Hollow, the next ones) keeps these rules. A biome changes the palette,
the props and the painters; it does not change the camera family, the light, the shading model or the hierarchy.
`tests/test_arena_maps.py` checks the measurable ones on every map; `python3 -m arena family` shows them side by side.

## Light
- One sun from the **upper left** of the picture: toward the sun in (u, v) is (-0.62, 0.52) (`geo.SUN_UV`), its
  elevation 40-55 degrees (Hushfall 50, a dusk; Emberleaf 40, a late afternoon whose long shadows lay the frame's
  shade onto the field's edge, with dappled sun-flecks under the crowns). Warm light against cool shadow: lit steps lean warm, shade steps lean cool. Cast shadows are real (Blender) and are painted
  as each ramp's shade step.
- Plus a sky fill (0.28) and a weak bounce from the front right (0.32, no shadows) that gives form to the sides the sun
  leaves in shade. Same numbers on every map (`blender/arena.py` LIGHT; a biome may override, none does yet).

## Shading model: painted cards, stepped ramps
- Blender renders **data, never colour**: lit value, material id, depth and zone id (`blender/arena.py`).
- Foliage and clouds are camera-facing cards cut by the dab and puff alpha atlases, with **sphere normals** (each
  clump's sphere blended with the whole form's), so a crown or a cloud shades as one soft volume; buried cards darken
  (`card_values`). Props are smooth-shaded blobs, bevelled boxes, cylinders.
- The painter (`paint.py`) steps each material's lit value through a **hand-picked ramp** of palette keys. Colour only
  exists in the map's closed palette; every pixel is a palette key as its zone renders it.
- 2D marks that must keep their size (cobbles, tufts, flowers, petals, the sun's rim) are stamped after the cleanup,
  in palette keys, in world space (they foreshorten with the camera).

## Ramp steps per zone (zones.py `BASE`, biome overrides)
| zone | steps | stroke (soft px) | cleanup (r px, share) |
|---|---|---|---|
| playfield | 2 per material (the variety is in big soft patches of materials, not in steps) | 3 | 3, 0.30 |
| focus | free | 0 | none |
| frame | 3, or 4 where foliage needs under / body / light / top (Emberleaf's crowns) | 0.6 | 1, 0.20 |
| backdrop | 3-4 | 0.8 | 2, 0.30 |
| vista | 5 | 0.5 | 1, 0.20 |
| sky | painted bands | - | - |

Strokes and cleanups are the same on every map; a biome may move a zone's value window, saturation and sun caps and
its haze, never its strokes.

## The value hierarchy is the family's signature
Every map, whatever its palette, reads the same way in grey and at a squint: **a dark, saturated frame wall; the
lightest calm area in the centre of the playfield (a light pool on the fight); the back one haze step lighter and
quieter than the frame, never brighter than the fight.** Lint measures it:
- the frame's 90th percentile luma stays at or under the playfield's median + 0.05 (a median-only rule let bright
  crown tops flood the frame);
- the brightest large region (the top 5% of a squint over the land, sky and vista excluded) lies at least 60% on the
  playfield and is centred in the picture's middle third;
- the playfield is at least 0.15 lighter than the frame in median, calmer (less detail and contrast), and its darks
  stand the biome's gap above a unit's outline.
Also judged by eye on the squint (no lint yet: a per-prop contrast needs a prop-id pass over the painted map): **no
decorative object or obstacle inside the playfield carries its highest contrast** (Emberleaf's pond did; now the fight
does).

## Edges are painted, not contoured
- **Ramp-step boundaries are dabbed, never a bare contour.** The engine's step-edge pass (`paint.dab_edges`) paints
  every boundary between two steps of one material family with leaf-shaped dabs along a slow flow field; the steps
  and the palette stay the same. It is opt-in per biome (`biome.DAB_EDGES`): Emberleaf uses it; Hushfall does not
  yet, so its art stays byte-identical (`r2/hushfall_dab_before_after.png` shows what it would do). A biome that
  dabs may raise the playfield's cleanup share (0.30 -> 0.45): the dabs replace the stair-steps it absorbs.
- **Ground meets ground with a lip**: where a raised surface (grass, snow) meets a trodden one (dirt, lane), a lit
  lip on the raised side facing the sun, a cast-shadow band on the low side where the raised side stands between it
  and the sun, scalloped lobes, tufts in clusters with gaps, a few pebbles.
- **One frame-colour scatter on the floor** ties frame and floor: fallen red leaves here, snow clumps or needles on
  a winter map. Sparse, never a pattern.

## Outlines
- **No ink outlines on the map.** Shapes separate by value steps, cast shadows and haze. The only edge line is the
  sun's rim: a light (peach / salmon) pixel line on the upper-left silhouette of crowns that stand against something
  far behind them (the back, the sky).
- **Units own the outline**: a 1 px ink outline (luma <= 0.12) and a 1 px light rim on their upper-left. So the
  darkest edge on screen is always a unit's.

## Art over walkable ground (the occlusion contract)
Any art drawn over walkable ground (a crown, a bridge, a roof) is a cut-out in `occ.png` with its depth, so a game
draws it over the units behind it, and the game must keep those units readable: draw a unit with art over it again
as a see-through silhouette (the viewer does, 55% alpha), or fade the cut-out within 2 m of a unit. Art that cannot
honour this must not overhang walkable ground. Trees inside the hollow keep their trunks visible and do not sway.

## Unit scale
- A map's px per metre (`place.PPM`) is set so **a 1.7 m person stands at least about 32 px tall** (PPM x 1.7 x
  cos EL): Hushfall 32 px/m at 40 degrees (41.7 px), Emberleaf 51.2 px/m at 68 degrees (32.6 px). The picture covers
  the same ~60 m of world either way (Emberleaf is 3072 x 1728 and the viewer pans at 1x, fits at 0.6x).
- Strokes, cleanups and painted marks are set at 32 px/m and scale with the map's px per metre (`paint` `sp`), so a
  dab, a tuft or a cleanup radius is the same size in metres on every map.
- Never rescale a map's ground to make units taller; units are drawn for the camera member they stand in (below).

## The camera family
- Orthographic, looking along +v with the world's square grid turned 45 degrees (built things sit square to it and
  read isometric); about 60 m of world across the picture.
- **Members: EL 40 (Hushfall) and EL 68 (Emberleaf, a near-top-down view).** EL 55 was
  Emberleaf's first pick (from 40 / 55 / 65) and is superseded. 68 was picked by eye from 62 / 68 / 74 (`angles2.png`):
  62 still showed crowns partly side-on; 74 flattened trunks and props and left the back 12% of the frame; at 68
  crowns are round tops, rocks show mostly their tops, and the valley still shows past the lip.
- **Two members for now**: a series can keep one elevation for every map (re-render the others to it) or two
  members with equal unit heights in px (the px-per-metre rule above). Hushfall stays at 40.
- A unit set ships one sprite set per member (the same 3D or painted source rendered at both elevations). A new map
  picks a member; a new member needs a reason and a sprite set.
- Framing: the walkable's front edge lands a fixed distance above the bottom (`FRONT_PX`), the back is built as a
  stage set in screen bands between the back edge and the picture's top (`place.SCENERY`), so it survives the angle.

## The zone hierarchy and budgets
Loudest to quietest: units and effects > **focus** (objectives, spawn marks, lights) > **playfield** (where units walk)
and **frame** ("the edge is here": trees, cliffs, cover props) > **backdrop** (past the edge) > **vista** (far
ranges, clouds) > **sky**. `python3 -m arena lint --map NAME` fails when:
- a zone leaves its value window or saturation cap (`zones.py` table + the biome's overrides);
- contrast or texture energy (contrast x the share of neighbouring pixels that differ) does not fall frame >
  backdrop > vista;
- the playfield is busier or more contrasted than the frame, or not at least 0.15 lighter in median;
- the playfield's darks come within the biome's gap of a unit's outline (Hushfall 0.30, Emberleaf 0.25);
- the sun's or embers' hues cover more of a zone than the biome allows;
- any pixel shows the map's reserved unit hues above chroma 0.2.

## Hues reserved for the units
Hushfall reserved gold, green and azure. That cannot be a global rule: Emberleaf is green grass round a cyan pond.
The rule is two parts:
1. **Each map reserves at least two hue bands, each >= 20 degrees wide, ideally far apart (two teams)**, and keeps
   every pixel in them under chroma 0.2 (`palette.UNIT_HUES`, checked by lint and by a palette test). The bands are
   documented per map and exported in `level.json` -> the game picks team colours from the map's bands:
   | map | reserved |
   |---|---|
   | Hushfall Crossing | gold 35-70, green 80-165, azure 190-230 |
   | Emberleaf Hollow | gold 40-64, violet 240-290 |
   Gold is reserved on both, so a gold team reads on every map; the second team colour changes with the biome.
2. **Every unit carries the shared outline and rim** (above), so it separates from any ground by value even where
   its hue is close to the map's.
Why not "reserve high chroma only": the reference style is saturated (coral crowns, lime grass, a cyan pond), so a
chroma-only rule would grey the biome out. Hue bands per map keep the biome's colour and still give the units an
exclusive signal.

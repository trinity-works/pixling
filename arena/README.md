# arena: battle maps for your units, one engine, one style

Painted battle maps for your own units, each a map module plus data on one shared engine (`arena/*.py`): an
orthographic camera of a fixed family, Blender rendering DATA passes (lit value, material id, depth, zone id) that a
painter steps through hand-picked colour ramps, depth zones with budgets (`lint`), and a complete game level
(`level.json` v4: collision, nav, LOS, zones) checked by `check`. The shared rules every map keeps are in
[STYLE.md](STYLE.md): the light, the shading model, the steps per zone, outlines, the unit scale, the camera family,
the zone budgets and the hues reserved for units.

| map | what | camera |
|---|---|---|
| **Hushfall Crossing** (`--map hushfall`, the default) | a winter ledge over a sea of dusk cloud: two camps, a ruin terrace with the Stones, a bridge to an overlook, a corridor under it | 40 degrees |
| **Emberleaf Hollow** (`--map emberleaf`) | a kill map (team annihilation) in a clearing of red-crowned trees and dark pines on a forested plateau; past its back edge a valley of canopy, a river, far hills | 68 degrees, 51.2 px/m |

<img src="../docs/img/arena_overview.jpg" alt="Hushfall Crossing: the whole map" width="640">

```
python3 -m arena maps                          # the maps and whether their art is painted
python3 -m arena <command> --map NAME          # every command below takes --map (default hushfall)
python3 -m arena bundle               # ONE html that opens from disk: out/arena/[NAME/]arena.html (everything inlined)
python3 -m arena export [--out FILE]  # the level as JSON for your units (see "Using the map in your game")
python3 -m arena level                # rebuild the map's art/level.json from its place data (collision, nav, LOS, zones)
python3 -m arena check [--quick]      # validate it: reachability, fairness, spawn safety, stuck tests, art agreement
python3 -m arena perf                 # frame time of the viewer in Chromium at 1280x720 and 1920x1080
python3 -m arena shots [--out DIR]    # bundle + stills through the real viewer (Playwright, file://), overlays, crops
python3 -m arena lint                 # the zone budgets measured on the map's art/map.png; fails when the hierarchy breaks
python3 -m arena zones|palette|scale  # looking aids: zone map / grey / squint, the palette strip, the scale sheet
python3 -m arena family               # every map side by side at the same scale: one style family?
ARENA_BPY=/path/to/python-with-bpy python3 -m arena paint [--art DIR]   # re-render in Blender (1-2 min at 1 sample)
python3 -m arena repaint [--art DIR]  # re-step the last render into the map's art/ (tune RAMPS / ZONES, no Blender)
python3 -m arena plan                 # top-down plan of the walk grid
```
Each map's painted art is committed in `arena/maps/NAME/art/` (`map.png`, `zones.png`, `occ.png` + `occ.json`, the
moving layers and `layers.json`, `level.json`), so `bundle`, `export`, `level`, `check`, `shots` and `lint` need no
Blender. `--art DIR` sends a paint or repaint elsewhere (tests, angle trials); `ARENA_EL=55` overrides a map's camera
elevation for such trials.

## How it is split: one engine, a module per map
```
arena/            the engine: geo (camera family, noise, signed distances), zones (budgets, lint), paint (stepping),
                  layers (sway, drifting strips), level / game / check (the game level), sheets, build, render, web/
arena/blender/arena.py   the Blender kit and driver: data shader, cards with sphere normals, blobs, boxes, the spruce,
                  the cumulus, the terrain mesh, lights, camera, passes; it runs the map's builders in its namespace
arena/maps/NAME/  a map:
  place.py        the place in metres: camera elevation and framing, plan (signed distances), terrain, layout() with
                  a zone per thing, the back's bands (scenery), the drifting cloud layers, zone_at, DIMENSIONS
  palette.py      the closed palette, the sun's (or embers') hues, the hue bands reserved for units
  biome.py        materials and ramps, zone-budget overrides, the painter's hooks (sky, ground, after_clean,
                  after_sky), the moving layers (sway amplitudes, cloud strips), the looking aids, the viewer's ambience
  level.py        the level hooks: prop collision shapes, surfaces, spawns, objectives or a kill map's targets,
                  chokepoints, an optional deck (a second nav layer)
  blender.py      the Blender builders: TERRAIN (material classes), BUILD (kind -> builder), build_back()
  art/            the painted map and its level (committed)
```
`arena.maps.activate(NAME)` binds every engine module to one map (`arena.place` / `arena.palette` resolve to it);
the CLI does it from `--map`. Hushfall moved into this split unchanged: repainting its committed render gives
byte-identical art and level.json, and a full Blender re-render differs by 1 pixel of EEVEE shadow noise, exactly as
the old code does against itself.

## Making a new biome map, step by step
1. **Copy a map package** (`arena/maps/emberleaf/` for a one-level map, `hushfall/` for one with high ground and a
   deck) to `arena/maps/NAME/`, and register it in `arena/maps/__init__.py` `MAPS`.
2. **The camera**: pick a member of the family in `place.py` (`EL_DEG` 40 or 68, STYLE.md). Keep the sun's
   direction and about 60 m across; set `PPM` so a person stands at least 32 px tall (32 at 40 degrees; 51.2 and a
   3072 x 1728 picture at 68 degrees). Trial angles with `ARENA_EL=.. python3 -m arena paint --map NAME
   --scale 0.5 --art /tmp/x` and pick by eye.
3. **The plan** (`place.py`): the walkable as signed distances (`sd_play`), the terrain, `layout()` with every thing's
   `kind` and `zone` (fought over = focus, bounds and cover = frame, dressing = playfield; keep dressing rare). Mirror
   whatever changes how people move (`pair()`), and mirror the noise of the outline and the terrain (`fbm(abs(u), v)`)
   so the routes are exactly fair. Spawns behind something that blocks sight.
4. **The back** (`SCENERY`): bands as shares of the room between the back edge and the picture's top, built smaller
   and sunk (`z_for_p`) so each lands in its band; keep the centre of the back open (a window over the play).
5. **The palette** (`palette.py`): closed, hand-picked, each key a ramp step. Reserve at least two hue bands for the
   units (>= 20 degrees, gold if you can: it is free on every map so far) and keep every key out of them.
6. **The biome** (`biome.py`): `MAT` ids (also Blender's) and `RAMPS`; `ZONE_OVERRIDES` for value windows, saturation
   and haze only (strokes and cleanups are shared); the painters (`ground` sets materials per pixel from (u, v),
   `after_clean` stamps the marks that must keep their size); the sway, layers and `VIEWER` settings.
7. **The builders** (`blender.py`) for every `kind`, each prop its own occluder (`new_occ`), and `build_back()`.
8. **The level hooks** (`level.py`): a collision shape per prop matching its geometry, surfaces, spawns, objectives
   or (kill map) `targets` for the fairness check, chokepoints. Run `python3 -m arena level --map NAME` and the check's
   pieces long before any art (reachability, fairness and spawn safety need no render).
9. **Paint** (`paint`, then `repaint` while tuning ramps), **lint**, **check**, **shots**, **perf**, **family**. Judge by
   eye: the overview and 2x crops beside your reference and beside the other maps at the same window; list the three
   worst things, fix them, repeat. Keep a short log of each round.

# Hushfall Crossing (`--map hushfall`)

A battle map in the Hushfall dusk, for your own units. It is the winter forest of fp's *First Snow*, made into a map.
The layout, a classic two-camp arena with a contested centre:
- a ledge above a sea of dusk cloud, ringed by spruce forest, with two palisaded camps (west and east);
- a raised ruin terrace in the middle holding the Stones, with a ramp up to it from each side;
- a timber bridge from the terrace to an overlook at the far edge, a dead end of high ground over the centre;
- a corridor at ground level under the bridge that links the two camp areas, and an apron at the terrace's foot along
  the front lip.

Behind it all: forest ridges receding into the dusk haze, cumulus towers with the low sun's pink on their crowns, and
the cloud sea under the ledge. The trees sway in the wind and the clouds drift past with parallax. The map ships with
no units: the viewer shows the map, its ambience and overlays for sizing and placing yours, and the level is exported
as JSON with everything a game needs: collision shapes, a nav grid with clearance, line of sight, gameplay zones
(see "Using the map in your game"), checked by `python3 -m arena check`.

Its files live in `arena/maps/hushfall/` (place, palette, biome, level hooks, Blender builders, art); the sections
below name them by their old short names (`place.py` is `maps/hushfall/place.py`).

## The map viewer (`web/arena.js` + `web/level.js`, canvas 2D, no libraries)
The picture is six layers: sky < far cumulus < the map < the corner towers < the cloud sea < the ledge's front.
On top run the snowfall, the camp fires and their smoke, the lamps and the hearts' glow, and the banners.

- **Pan**: drag, or WASD / arrows (Shift for faster). **Zoom**: X or the wheel, through 1x, 2x and fit. The map is
  1920 x 1080 at 1x, one 1080p screen.
- **Grid (G)**: the legacy 0.5 m walk grid, with the spawn points, objectives and chokepoints labelled with their
  measured widths.
- **Zones (Z)**: the depth zones tinted over the map.
- **Scale (M)**: a 1 m grid on the walkable ground and neutral people 1.7 m tall on every level. Click to stand
  another one anywhere; C resets them. They are drawn the way your units should be (see "Draw order").
- **Colliders (K)**, **V** cycles the level (all, ground, terrace, deck): every collision shape as its footprint on
  its floor and a prism up to 2.2 m (what touches a unit), coloured by level. A filled shape blocks sight, a dashed
  one only movement. The edges of the walkable are red (wall), blue (lip) and white (bound).
- **Nav (N)**, **R** cycles the agent radius (0.3, 0.5, 0.8 m): every 0.25 m cell by its clearance, dimmed where it
  is too tight for the radius; the ramps' entry, switch and exit edges and the deck's two ends.
- **LOS (L)**: line of sight from the cursor, eye to eye, over every walkable spot (seen green, hidden dark).
- **Paths (P)**: A* for the chosen radius from both spawns to the Stones and to the other side's heart, with
  lengths, and from both spawns to the cursor.
- **Agent (U)**: a test agent at the west spawn. Click to send it: it plans with A* at the chosen radius and walks
  the path through the colliders at 4 m/s (`level.js` `move`).
- **Snow (F)** toggles the snowfall; Space pauses. The readout shows u, v, z, the level, the surface, the
  clearance and the path lengths from both spawns.
- **level.json** downloads the level data from the page.

URL parameters: `zoom=1|2|3|fit`, `at=X,Y` (centre on a map pixel),
`overlay=grid,zones,scale,colliders,nav,los,paths,agent`, `level=0|1|2`, `r=0.3|0.5|0.8`, `los=U,V,LAYER`,
`cursor=U,V,LAYER`, `target=U,V,LAYER&walk=STEPS`, `snow=0`, `sway=0`, `drift=0`, `pause=1`, `t=SECONDS`,
`shot=1&hud=0` (no panels).

### Swaying trees and drifting clouds (`layers.py`)
- **Sway**: the frame's spruces (found by their occluder id) and the far ridges' trees (by their id in the ids pass)
  move sideways by whole pixels: `round(A * w * s)`. `w = (height over the tree's foot / its height)^1.5`, so the foot
  never moves. `s` is a slow sway of the tree's own phase plus a gust crest rolling left to right (960 px apart).
  A is about 2 px for the ring's back trees, 1 px at its sides and 0.8-1.2 px for the far ridges; the groves inside
  the field do not sway. The loop is 12 held frames at 6 fps. What a moved tree uncovers takes the pixel beside it,
  or the sky. Only the 32 px tile runs that differ from `main.png` are stored (`sway.png`, about 0.5 MB).
- **Clouds**: the cumulus and the cloud sea are rendered alone and complete, as 3840 px strips that wrap (every
  mass near the seam is repeated one period over). They drift at 3 and 6 px/s, so a cloud takes 5-10 minutes to
  cross the screen. The pink crowns are part of them. Parallax runs about the centred view: sky 0.15, far 0.35,
  sea 0.7, map 1, all in whole pixels. The corner towers sway ±10 px over four minutes. The ledge's front (`cap.png`)
  is drawn over the sea, so the sea never laps onto the field.
- **Cost**: the scene is one buffer, repainted on the 6 fps tick and only by regions: the sky band, the sea band and
  the changed tile runs in between. A camera move repaints all of it. Every frame then draws that one image plus the
  lights and the snow. In the fit view (a map bigger than the window) the scene is scaled down once into a
  screen-sized picture and only the rects a tick touched are scaled again (bilinear, a few ms per frame until done);
  each frame blits it 1:1 and draws the moving things over it at the zoom. `python3 -m arena perf` measures the
  default view, 1x and panning at 2x, at 1280x720 and 1920x1080.

## Using the map in your game (`art/level.json` v4, `python3 -m arena export`)
Everything is built in Python from the same place data as the render (`level.py`). `game.py` (Python) and
`web/level.js` (browser and node) answer queries on it with the same code; a test checks that they agree.

**Coordinates.** Metres: u runs left to right, v into the picture, z up. `projection` puts a point on the map at
`sx = x0 + u * ppm`, `sy = y0 - (v * sin_el + z * cos_el) * ppm` (ppm 32, 40 degrees). Draw far to near by
`depth = v * cos_el - z * sin_el`. A 1.7 m person is 41.7 px tall.

**Levels.** 0 ground, 1 terrace (the ruin terrace, the ramps' upper halves, the overlook), 2 the bridge deck.
Ground and terrace are one height field (layer 0): they never overlap in plan, and a cell's level is 1 where its
floor is at or over `rules.high_ground_z` (1.5 m). The deck is a second layer (layer 1) over the corridor. A
position is `(u, v, layer)`.

**Rules** (`rules`): max step 0.35 m, max slope 35 degrees (the ramps are 23), agent height 1.8 m, eye 1.6 m, chest
1.1 m, radius classes 0.3 / 0.5 / 0.8 m. An obstacle constrains a unit standing on a floor at z when its z range
overlaps `[z + max_step, z + agent_height]`. So the deck's rails touch only units on the deck, and the deck is a
ceiling over the corridor (2.8 m clear in the middle, 1.9 m at the walls' feet: `levels[2].headroom`). The edges of
the walkable are hard walls; there is no kill plane (`kill_z` if your game knocks units over the lip).

**Collision** (`colliders.shapes`, 720 shapes): each has `kind`, `shape`, `level`, an absolute `z0..z1` and three
flags, `move`, `sight` and `shot`.
- `circle` (u, v, r): spruce trunks, posts, banners, lamps, rocks, columns, tower legs.
- `box` (u, v, hu, hv half sizes, a = the angle of its hu axis from +u toward +v): tents, palisade runs, the
  towers' cage, platform and roof, the hearts, crates, woodpiles, toppled blocks,
  parapets, the deck.
- `seg` (u0, v0 to u1, v1, t = half thickness, a capsule): kerbs, bridge rails, corbels, and the walkable's edges.
  The edges are traced from the height field: `wall` is a face rising (a cliff with no step-up, blocks sight and
  shots), `lip` is a drop (a hard edge), `bound` is the forest shelf (out of bounds).

Low things never block sight (kerbs, the fire's stones, the rails, the towers' open cage: under 1 m or
open). Rocks and toppled blocks (about 0.8 m) stop shots only from low angles.

**Nav** (`nav`): a 0.25 m grid, 256 x 128 cells from (u0, v0), in two layers (`hf`, `deck`). Each layer has these
arrays, base64, row-major `i * nu + j`:
- `clear`: uint8 clearance in 2 cm steps, 0 = not walkable. An agent of radius r may stand where
  `clear * 0.02 >= r`; small pockets cut off at a radius are filled in.
- `surf`: snow (speed 0.85), trodden lane (1.0), drift along the lip (0.7), deck (1.0); `| 8` on the ramps.
- `hf.z_cm`: the ground's height everywhere, walkable or not; LOS uses it as the terrain.

Steps go to the 8 neighbours. A diagonal needs both of its corners free, and a step's height must stay under
max_step. Ground and terrace cells connect only through ramp cells: `links` gives each ramp's rectangle, its entry
(foot), switch (mid) and exit (top) edges. The deck's two ends are explicit cell pairs. Two camp alcoves between the
tents are declared too tight for r 0.8 (`alcoves`).

**Line of sight** (`los`): a 3D segment from eye to eye (shots: chest to chest). It is blocked by the terrain,
sampled every 0.25 m, and by every shape whose prism it crosses and that carries `sight` (`shot`). High ground sees
over whatever is lower than its eye; units right under a wall are in dead ground. `visibility` is a coarse helper: a
bitset of which 2 m squares see each other.

**Zones** (`zones`):
- `spawns`: per side, an origin, an area (r 4.4), a safe radius (7 m) and 13 spawn points, mirrored.
- `objectives`: the Stones (terrace) and each side's heart and tower, with capture circles.
- `heal`: the camp fires' warmth, r 3.2, optional.
- `chokepoints`: measured wall to wall. Ramps 5.1 m, bridge 3.1 m, corridor 6.8-11.9 m, apron 4.3-4.6 m.
- `cover`: 96 spots pressed to things that stop shots, each with its facing and full or half.
- `surfaces`, and `out_of_bounds`: the outer outline.

```js
const lv = ArenaLevel.load(await (await fetch('level.json')).json());   // or require('./level.js') in node
// a unit at the west spawn, radius 0.5, sent to the Stones
const o = lv.L.zones.spawns.west.origin;
const unit = { u: o[0], v: o[1], layer: 0, r: 0.5 };
const path = lv.findPath([unit.u, unit.v, unit.layer], [0, -2.2, 0], unit.r);   // {points: [[u, v, z, layer]], length}
let i = 1;
function step(dt, speed = 4) {                      // each frame: walk toward the next point, slide on the colliders
  if (!path || i >= path.points.length) return;
  const [tu, tv] = path.points[i], du = tu - unit.u, dv = tv - unit.v, d = Math.hypot(du, dv);
  if (d < 0.1) { i++; return; }
  const s = Math.min(speed * dt, d);
  lv.move(unit, du / d * s, dv / d * s);            // changes layer on and off the deck's ends; unit.z = its floor
}
// can the unit see, or shoot, an enemy on the bridge?
lv.los([unit.u, unit.v, unit.layer], [0.3, 6.9, 1]);            // eye to eye
lv.los([unit.u, unit.v, unit.layer], [0.3, 6.9, 1], 'shot');    // chest to chest
// where to draw it, and its depth for the draw order
const P = lv.L.projection;
const sx = P.x0 + unit.u * P.ppm, sy = P.y0 - (unit.v * P.sin_el + unit.z * P.cos_el) * P.ppm;
const depth = unit.v * P.cos_el - unit.z * P.sin_el;
```
In Python, `from arena.game import Level` has the same `find_path`, `field` (Dijkstra), `los`, `move`, `snap` and
`clear_at`.

**Checked** (`python3 -m arena check`, and fast versions in `tests/test_arena.py`):
- every walkable cell is reached from both spawns at every radius (bar the declared alcoves);
- both spawns reach every objective, and the mirrored routes are equal within 0.75 m or 2% (they are within 0.35 m);
- no spawn point sees the other side's;
- every nav step is free in the continuous colliders; 200 random walkers never wedge or end where the nav cannot
  take them home, and 30 units walking A* paths with the mover all arrive;
- the colliders sit on the painted props: their projected samples land on the occluder cut-outs.

**Draw order** (`occ.json` + `occ.png`): every tree, prop and the bridge is cut out of the map with its depth `d`.
Draw a cut-out over a unit whose depth is larger (further) than `d` and that it overlaps. The bridge goes over units
on the height field and under units on the deck.

**The occlusion contract** (every map, STYLE.md): a unit with a cut-out drawn over it must stay readable. Draw it
again over the cut-out as a see-through silhouette (the viewer does: the figure at 55% alpha), or fade the cut-out
to 50% within 2 m of a unit. Emberleaf's two playfield oaks over the spawns' north exits are the case to test.

The v3 keys stay for older code: `grid` (0.5 m kind and height), `spawns`, `objectives`, `chokepoints`, `lanes`,
`props`, `dimensions`.

## Sizes and distances (`place.DIMENSIONS`)
A person is 1.7 m. On screen 1 m is 32 px across, 20.6 px into the picture and 24.5 px up, so a person is 42 px tall.

| what | size |
|---|---|
| camp palisade | 12 x 12 m |
| camp to camp (hearts) | 42 m |
| a camp's heart to the Stones | 21 m |
| ruin terrace | 16 x 9.6 m, 3 m high |
| ramps | 6 m wide (5.1 m kerb to kerb), 7 m run, 23 degrees |
| the Stones | an open 6.8 x 4 m capture ring on the terrace, no props (the game marks it) |
| bridge | 3.6 m wide (3 m walked, two abreast: the one tight chokepoint, on purpose), 8.8 m span |
| headroom under the bridge | 2.8 m in the middle, 1.9 m at the walls' feet |
| corridor | 20 m long, 8.4 m deep |
| overlook | 15.2 x 6.8 m, 3.2 m high |
| front apron | 20 m along the lip, 5.6 m deep |
| frame spruces | 6.5-12 m (4-7 people; real spruces are taller, this is the usual game squeeze) |
| watchtower | 4.6 m platform, 7.5 m roof |
| tents | 3.4 x 2.7 m, 2.3 m ridge |

About 1,170 m² is walkable for a 0.3 m unit. The bridge (3.1 m between the rails) is the tight chokepoint, on
purpose. The space in front of the terrace is the apron, a fourth route along the lip: its joins to the camps are
filleted and its toppled blocks sit against the wall, so it stays 4.3 m wide.

## The camera
Orthographic, looking down 40 degrees across the world's square grid, which is turned 45 degrees. Everything built sits
square to that grid, so it reads as isometric. One camera serves the map, the viewer and the exported projection.
It was picked from a test of 30 (2:1 isometric), 35 (the previous map), 40 and 45 degrees, all at the same framing:
- 30 has the most beautiful back, but the terrace hides the corridor floor and the playfield is 26% of the frame;
- 45 gives the most playfield (38%), but the forest ring swallows the cumulus;
- **40** reads all three levels (the terrace, the bridge, the corridor floor under it), keeps the cumulus crowns over
  the treeline, and puts about 35% of the frame on the playfield and its objectives.

The picture is framed from the layout (`place._frame`): the ledge's front lip lands 120 px above the bottom, and the
back is the band behind and around the play. `ARENA_EL=30 python3 -m arena paint` renders another angle.

## Depth zones: the information hierarchy (`zones.py`)
Loudest to quietest: your units and the effects > **focus** (the Stones, hearts, towers, banners, the bridge) >
**playfield** (where units walk) and **frame** (the forest ring, the ruin's faces, the palisades, the cliff: "the edge is
here") > **backdrop** (the forest ridges past the drop) > **vista** (the cumulus and the cloud sea) > **sky**.

Every element carries its zone (`place.layout()`, `place.scenery()`); ground pixels get theirs from `place.zone_at`.
Blender writes the zone into the id pass, and the painter writes `art/zones.png`. The budgets are one table:

| zone | haze near/mid/far | steps | value (luma) | sat cap | sun cap | stroke px | cleanup (r, share) | Blender detail |
|---|---|---|---|---|---|---|---|---|
| playfield | 0 | 2 | 0.44-0.66 | 0.12 | swapped | 3 | 3, 0.30 | 1.0 |
| focus | 0 | all | free | free | free | 0 | none | 1.0 |
| frame | 0.03 / 0.08 | 3 | 0.16-0.44 | 0.17 | 0.20 | 0.6 | 1, 0.20 | 0.9 |
| backdrop | 0.24 / 0.38 / 0.50 | 3 | 0.36-0.52 (floor +0.03, +0.07 per ridge) | 0.12 | 0.16 | 0.8 | 2, 0.30 | 0.55 |
| vista | 0.10 / 0.20 / 0.30 | 5 | 0.51-0.66 | 0.13 | 0.70 | 0.5 | 1, 0.20 | 0.55 |
| sky | 0 | bands | 0.50-0.68 | 0.20 | 0.22 | 0 | none | none |

The back is quiet by value and haze, not by flattening: the backdrop keeps three steps and a light cleanup, so the far
spruces keep their dabs and their pointed tiers; each ridge sits one haze level further back and a little lighter. The
vista keeps the cumulus's puffs and the pink chains on its crowns.

`lint` checks:
- every zone stays inside its values and saturation;
- contrast falls frame > backdrop > vista, and so does texture energy (contrast x the share of neighbouring pixels
  that differ). Detail alone may stay up in the back: it keeps its strokes, it just says them softly;
- the playfield is calmer than the frame (less detail and contrast), at least 0.15 lighter than it, and its darks stand
  0.3 above a unit's dark outline;
- the accent rule (below).

## Palette and the accent rule (`palette.py`)
- **Playfield**: calm and light, two tones: warm lit snow (a dusk cream-grey) and violet shade, the trodden lanes a
  step between. Low chroma, so units of any strong hue pop on it.
- **Frame**: the darkest: navy spruces with snow shelves and the low sun's salmon rim on the tree line, the ruin's
  masonry, the palisades, the cliff.
- **Backdrop**: the same spruces pushed into the violet-rose dusk haze (`fog`).
- **Sky**: a warm dusk, cool grey-teal at the top, rose and peach down to the glow on the horizon (First Snow's sky).
- **The sun owns the pinks** (hue 300-30 degrees): the cloud crowns, the glow, the rims, the warm lamps. The brightest,
  most saturated colours are kept for the sun, the lights and the objectives. The sun's saturated pinks may cover up to
  5% of the vista and 2% of the sky, and none of the playfield or the frame.
- **Kept free for your units**: gold (35-70 degrees), green (80-165) and azure (190-230). No pixel of the map shows
  them above chroma 0.2. A crimson or rose unit will compete with the sun's crowns, so prefer the free bands for team
  colours.

## A back in an orthographic camera (`place.SCENERY`)
An ortho camera does not shrink distance, and a level strip of land climbs the picture by sin(40°) per metre back.
So the back is a stage set, placed by screen height P (`sy = Y0 - P * PPM`) from `P_BACK`, the ledge's back edge:
- three forest ridges at v 34, 52 and 72, each sunk (`z_for_p`) so it rises from its foot band to its crest band, its
  trees built smaller (6, 4, 2.8 m) and coarser the further back;
- cumulus towers at v 110-120, taller at the sides so their crowns stand over the forest ring, lower in the middle so
  the window over the overlook stays open; two more stand out of the sea at the front corners;
- the cloud sea under the front lip, placed by its tops' screen height so it shows just under the lip.

The ledge's cliffs stay frame until they sink into the cloud sea below `paint.FOG_Z`.

## The ruin (`place.ruin_edges`, `blender/arena.py`)
The terrace and the overlook are snowy ruin terraces, not boxes:
- their outlines wander (`edge_noise`), and their faces are courses of dressed blocks in running bond, each block a
  little proud or sunk and a value step of its own, the top courses broken;
- a gappy kerb runs along every lip (more of it on the edges that face away, so the drop behind still reads), with
  snow on it and a cornice of drift along the top;
- broken parapet stubs, toppled blocks, broken columns and a fallen drum; stone kerbs step down both ramps.

The bridge is timber: planks across in a rhythm with dark gaps, heavy stringers, posts and braced rails, low drifts
banked along both edges. Nothing hangs below the stringers, so the corridor keeps 2.9 m of headroom.

## Making another map with this
See "Making a new biome map, step by step" at the top, and [STYLE.md](STYLE.md).

# Emberleaf Hollow (`--map emberleaf`)

A kill map: team annihilation, no objectives. A clearing of red-crowned trees and dark pines on a forested plateau,
seen from high (68 degrees, nearly top-down) at 51.2 px/m, so the picture is 3072 x 1728 for the same 60 m across
and a 1.7 m person stands 32.6 px tall; midday, the sun from the upper left at 40 degrees.

- **Spawns**: two glades at the ends (u = +-21.5), each tucked behind a thicket of bushes round a red tree (no spawn
  point sees the other side's), left by a north exit (grass) and a south exit (a dirt path into the centre). A carved
  wooden totem with a glowing rune marks each side; wooden lantern posts at the exits.
  At each glade's back rim, 1.5 m clear of every spawn point, a camp: crates, a plain linen banner pole, a ring-stone
  campfire (its flames and glow are the viewer's) with a bedroll, clay pot lights, mushrooms and flower clumps.
- **The fighting ground**: an oval of packed granular soil in the middle, 27 x 9 m (1.4 x round 4's), the light warm
  band of the picture so units pop on it: dusty
  lighter patches, fine grain in 2-4 px clusters a step darker or lighter, and pebbles of 2-12 cm (1-6 px, lit on
  their upper left, a 1 px shadow down-right) placed by blue-noise rejection, dense in the loose soil at the edges and
  round the props, sparse in the middle and on the wear lines; the paths' trodden middles a step darker. Cover is wood:
  a fallen log across the middle (along v: half cover that splits the straight line), two shorter logs and stumps each
  side, mirrored. No rock bigger than a pebble anywhere on the map.
- **The north lane**: through the grass over a low knoll (1.1 m, the one height feature; under `high_ground_z`, so the
  whole map is one level), a fallen trunk on each of its shoulders, a bush clump higher up.
- **The south lane**: through the grass between the fighting ground and the pond.
- **The pond** notches the front edge: a soft obstacle (its bank is a lip: it stops movement, never sight or shots),
  its shore cut by the terrain itself (bays), grass, reeds and painted pebbles at the water; its water in four soft depth
  bands that follow the shore, the sky's band on the far side; two small mirrored pools at the front corners; its
  glints and ripples move in the viewer. Past the hollow's rim the floor darkens in broken bands into the forest's
  shade, and big-leaf plants and mushrooms gather at the rim and round the props (never in a lane).
- **The back**: past the plateau's edge (behind the knoll, where the frame's trees leave a window) a valley: a near
  canopy of red and green crowns just over the lip, the valley floor with a river, a far canopy in haze, far hills,
  fair-weather cumulus drifting over a midday sky.
- **Ambience** in the viewer: the trees sway (baked tile frames, as Hushfall), the cumulus strip drifts, leaves let go
  of the red crowns and settle on the ground, motes of light drift over the hollow, glints come and go on the pond's
  own water pixels; soft light (`ambience.glows`, added at a low alpha, breathing): a warm glow on the fighting
  ground and a peach bloom on the sunlit tops of the big red crowns. About 60 fps at 1280x720 and 1920x1080, fit, 1x
  and 2x, in headless Chromium (`perf`).
- **Level** (`level.json` v4): one height-field layer, no deck; `zones.mode` = annihilation, `zones.objectives` empty,
  `zones.targets` (centre, knoll, south lane, each spawn) are where fights happen, for AI and for the fairness check;
  `zones.unit_hues` names the reserved bands (gold 40-64, violet 240-290). `check`: every walkable cell reached from
  both spawns at r 0.3 / 0.5 / 0.8, the mirrored routes equal to the centimetre, no spawn pair in sight, nothing
  stuck, every collider on its painted prop.

| what | size |
|---|---|
| spawn to spawn | 43 m |
| the hollow | 57 x 21 m, about 730 m2 walkable for a 0.3 m unit |
| the fighting ground | 27 x 9 m of packed granular soil, paths 2 m wide |
| the knoll | 11 m across, 1.1 m high |
| the pond | 10 x 5 m, irregular, with two bays; two small mirrored pools (3.4 x 2.2 m) at the front corners |
| the logs | 3.6 m (0.8 m high) across the middle; 2.0-2.4 m each side; 3.2 m on the knoll's shoulders |
| narrowest lane gaps | south lane by the pond 4.4 m; north lane over the knoll 6.5 m |
| red-crowned trees | four size classes: hero 9.5-10.5 m (crowns 6.4-7.2 m across), standard 6.6-7.8 m (4.4-5.4 m), small 4.6-5.6 m (3-3.8 m), saplings 2.6-3.2 m (about 2 m) at the hollow's edge; the front rows up to 30% lower so the edge shows |
| pines | young 5-7 m at the hollow's edge, tall 8.5-13.5 m behind |
| pebbles | painted, 2-12 cm; no rock bigger than 0.3 m |
| a 1.7 m person | 32.6 px tall (68 degrees, 51.2 px/m) |

## Files (the engine)
| path | what |
|---|---|
| `STYLE.md` | the shared style rules every map keeps |
| `geo.py` | the camera family, noise, signed distances, dart throwing (every map's place.py builds on it) |
| `maps/__init__.py` | the map registry and `activate(NAME)`; `place.py` / `palette.py` here resolve to the active map's |
| `maps/NAME/` | a map: place, palette, biome, level hooks, Blender builders, art (see "How it is split") |
| `level.py`, `game.py`, `check.py` | the level for a game (collision, nav, LOS, zones, `level.json`), queries on it, its validation |
| `layers.py` | the moving layers: sky, cloud strips, main, cap, the sway's tile frames, `layers.json` |
| `zones.py` | the shared zone table, the cleanup, `lint` (with the biome's overrides) |
| `blender/arena.py` | the Blender kit and driver (data renders); it runs the map's `blender.py` builders |
| `render.py`, `paint.py` | run Blender; step renders into the map's `art/` through its biome's ramps and painters |
| `sheets.py` | the palette strip, the zone / grey / squint views, the scale sheet, the family sheet |
| `web/index.html`, `web/arena.js`, `web/level.js` | the page, the map viewer (reads the map's viewer settings), the level queries |
| `build.py`, `shots.mjs`, `perf.mjs`, `__main__.py` | the one-file bundle, stills, frame time, the CLI (`--map`) |

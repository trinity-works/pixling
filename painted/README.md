# painted — the non-pixel format

Pixel Perfect's third engine, beside `pp/` (pixel sprites) and `reel/` (video to sprites). Blender renders
**painted-card** sprites: soft painterly shapes, flat stepped colour bands, no outlines, no pixel grid. A style file
and a layout go in; game sprites, a composed scene and a walkable web scene come out.

| use | engine |
|---|---|
| palette-locked pixel sprites, 8 directions, pixel-stable motion | `pp` (`pixling build`) |
| characters cut from AI video | `reel` (`pixling reel`) |
| painterly environments and props, semi top-down, soft cel look | **`painted`** (`pixling painted`) |

One painter per material holds across formats: don't mix pp pixel sprites into a painted scene, or the reverse,
except as a comparison (`painted game --pixel out/ranger` exists for exactly that).

## The technique
From trungduyng's *Anime Tree Tutorial | Blender*, extended to every asset:
1. **Cards**: foliage, grass, flowers, reeds, ivy, lily pads and clouds are alpha-masked planes (`textures.py` paints
   the masks: brush dabs, leaf clusters, cloud puffs, grass, flowers). Crown cards use the style's `foliage.atlas`
   (`dabs`: fat teardrop stamps fanned from a dense centre, the tutorial's brush mask) and, with
   `foliage.face_camera`, sit square to the camera like strokes on a canvas, so no card goes edge-on.
2. **Sphere normals**: the cards of one clump are scattered in a sphere and every card vertex carries the sphere's normal,
   so the clump shades as one soft mass instead of many planes.
3. **Stepped ramp**: diffuse → Shader to RGB → a constant colour ramp from the style. No gradients, no specular.
   The tutorial's value step is baked per card over the whole asset (`painter.foliage_values`): `buried` darkens cards
   that other cards cover (the dark pockets between and inside clumps, its AO), `crown` adds a light-to-shadow
   gradient across the asset along the sun. Crown cards don't shadow their own asset (`foliage.self_shadow: false`, the
   tutorial's per-material shadow switch), so a crown reads by its clumps, not one cast-shadow block; they still cast
   on the ground. An asset can opt back in per object (`o['shades_self']`, the pine's tiers).
4. **Bent normals on flat surfaces**: a roof's normals are bent toward a point inside the house, so a flat plane
   shades across in painted bands.
5. **Painted ground**: the ground plate stores distance fields per vertex (path, ruts, pond, far bank) and the shader picks
   designed flat tones from them (turf patches, verge, dirt with ruts, sand, mud, depth-banded water) with wobbling edges.

## Commands
```
pixling painted doctor                      # Blender found? (PIXLING_BLENDER=/path overrides the search)
pixling painted assets | styles | layouts   # what exists (--json)
pixling painted kit [assets ...]            # Blender -> out/painted/<layout>/kit   (~4 min all, mostly the hero)
pixling painted compose                     # -> out/painted/<layout>/scene: scene.png, scene.mp4, kit_sheet.png (--keep-frames)
pixling painted game [--pixel out/ranger]   # -> out/painted/<layout>/game: index.html, data.json, a/*.webp
pixling painted serve                       # play the built game: http://127.0.0.1:8765 (file:// can't load it)
pixling painted hilltop [--pixel] [--frames 48] [--size 1280x720]   # the perspective film shot
```
`--style NAME|path.json` (kit) and `--layout NAME|path.json` (kit, compose, game) pick the inputs; defaults
`painted_cards` and `hollow_brook`. `python3 -m painted ...` is the same CLI. Play a game with `pixling painted serve` (browsers block `fetch()` from `file://`).

## Files
| path | what |
|---|---|
| `styles/*.json` | a look: `camera` (elevation, px per metre), `light` (sun travel, energy, fill, gain), `shadow`, `ramps` |
| `layouts/*.json` | a place: `plate` (extent, water frames), `lane`, `footpaths`, `pond`, `ducks`, `hero.start`, `place` |
| `bpy/painter.py` | runs in Blender: the ramp shader, the card painter, primitives, framing and sprite render |
| `bpy/assets.py` | runs in Blender: every asset builder, the ground plate, the ducks, the hero rig |
| `bpy/kit.py` | runs in Blender: renders assets as sprites (sway, headings, walk/idle) |
| `bpy/hilltop.py` | runs in Blender: the standalone perspective scene |
| `textures.py` | the alpha atlases the cards use |
| `compose.py` | lays a layout out from the sprites only, the way a game draws it |
| `build_game.py`, `game.html` | packs a kit + layout into a walkable canvas scene |

## Sprite contract (kit output)
- **static**: `<name>.png` body, `<name>_shadow.png` ground-shadow layer (body hidden from camera, still casting),
  `<name>.json` with `anchor` = the pixel of the asset's ground origin, `w`, `h`, `ppm`.
- **trees, bushes**: `<name>_sway/fNN.png`, a seamless 32-frame gust loop (85 ms per frame; clumps nod on their own
  phases, and every card turns a few degrees in its own plane as the gust crosses, `foliage.flutter_deg`, the
  tutorial's small wind layer); the shadow stays the rest pose.
- **animals**: `<name>/dD_fNN.png`, 8 headings × 8 paddle frames. Heading 0 faces screen right, counter-clockwise
  (2 = away from the camera, 6 = toward it).
- **characters**: `<name>/{walk,idle}_dD_fNN[_shadow].png`, 8 headings × 16 frames at 75 ms, feet locked to the ground.
- **ground**: `ground/fNN.png`, 12 frames of the layout's plate; only the water glints move.
- **draw order**: ground, every shadow layer, then bodies and animals sorted far → near (larger world y first).

## The walkable scene (`game`)
Static shadows are baked into the ground; the water animation is the plate cropped to the pond. Sheets are packed into
grids at most 2048 px wide, each cell padded with its own edge pixels (wide strips fall off the GPU on small devices;
unpadded grids bleed seams when scaled). The runtime is a plain 2D canvas, no libraries: depth sort, culling,
crossfaded sway, petals that ride the sway's gust, ducks on a lap, characters that walk or wander (Tab or the button
switches who you control), collision circles and boxes per asset type, the pond blocked except the jetty.

## Adding things
- **An asset**: write a builder in `bpy/assets.py` from the painter's pieces (`clump`, `cards`, `tufts`, `tube`, `box`,
  `blob`, `poly(bulge=...)`, `toon(ramp, ...)`), register it in `TREES` (sways), `STATIC`, `ANIMALS` or `CHARACTERS`, and give
  it a one-line docstring (that's what `painted assets` lists). New colours go in the style's `ramps`.
- **A style**: copy `styles/painted_cards.json`, change ramps, light, camera and the `foliage` block (atlas,
  face_camera, value / value_power / value_reach / value_count, gradient, flutter_deg, self_shadow; leave it out for
  plain cards). Ramps are `[position, hex]` stops; a
  surface's lit value picks the band. Keep the camera the same across a game's assets.
- **A layout**: copy `layouts/hollow_brook.json`; `place` is `[asset, x, y]` in metres (y grows away from the camera).
  Collision sizes per asset type are in `build_game.py` (`SOLID`).

## Known gaps
- One camera direction per kit. It's 3D, so rotations are only re-renders, but none are wired yet.
- The hero is built from primitives; a real character should be a mesh driven by pp's skeleton and clips.
- The oaks' tops still read very sunlit at 45° (the top two leaf bands cover a lot); a ramp question, not an engine one.
- `hilltop` has its own card code and doesn't use the foliage block yet.
- `hilltop --pixel` is a test of Blender-to-pixel, not a pixel pipeline: leaves speckle. Use `pp` for pixel art.

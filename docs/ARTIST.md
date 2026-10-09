# ARTIST.md — how to make sprites with Pixel Perfect

You are the artist. You never paint pixels by hand. You **design** (concept, silhouette, proportions,
materials, motion feel) by writing a JSON spec, and the forge renders it into palette-locked,
8-direction, pixel-stable sprite sheets. Then you **look** at the result, judge it like an art
director, and iterate. Target quality: sellable itch.io packs next to the best hand-made ones.
The launch styles, how a new style is made and the taste rules every style keeps: [docs/STYLES.md](STYLES.md).

## The loop

```
python3 -m pp build specs/<style>/<name>.json            # -> out/<name>/  (sheets, gifs, json, contact.png)
python3 -m pp review out/<name> --clips idle,attack --dirs S,E,N --scale 5   # zoomed grid on the style's bg (--bg to override)
python3 -m pp scene out/<a> out/<b> out/oak --style <style>                  # side by side on the ground at game scale
python3 -m pp lint out/<a> out/<b> ...                                       # short numeric hints + family silhouette overlap
python3 -m pp silhouettes out/<a> out/<b> ...                                # white-fill silhouette row (design check)
python3 -m pp inspect specs/<style>/<name>.json --clip attack --dir E --frame 7  # what's under the pixels (below)
python3 -m pp variants specs/<style>/<name>.json --vary anim.drag=0.6,1,1.5 --clips attack --dirs E  # pick by eye
```
Fast iteration: `--clips idle --dirs S,E` renders only what you're judging (seconds).
Look at images with your image-reading tool. **Judge by eye first; lints are hints, not gates.**
Don't write measurement reports. One look, one fix, rebuild.

## Design process
1. **Theme + family first.** A family shares palette, materials, eye/nose treatment, proportions.
   Members differ by **one big defining feature** each (huge sword, slingshot, lantern, antlers, shield).
2. **Silhouette first.** Build the big shapes only (1-3 parts per bone), check `pp silhouettes`.
   Silhouettes in a family must read apart (IoU < 0.75). Exaggerate: big weapons, big heads, odd shapes.
3. **Readability = gameplay.** Big = tanky/slow, small = quick, spiky = dangerous, round = friendly.
4. **2-3 shades per part is plenty.** Tiny parts (hands, feet, ears) get 1-2 materials max.
5. **Details last**: eyes, belt, trim, glow accents. One glowing accent per character (eyes, rune, lantern).
6. **Zoom out.** Always check the `scene` view at 3-4x, not only the 5x review.
7. **Attack first.** If the attack looks bad, the design is wrong — fix the design, not the animation.

## Targets
- Humanoid **22-30 px** tall (hero ~26), boss 34-60, critters 8-14, quadrupeds 16-24 tall.
- Head **0.40-0.50** of height (chibi), or deliberately the opposite ("small head, big body" brutes).
- **8-20 colours** per sprite. No #000 / #fff. No semi-transparency (the forge guarantees this).
- No black outline: edges keep their fill, darken on the shadow side, rim-light on the light side (automatic).
- Separate touching parts by value (ΔL ≥ 0.08): don't put two mid-grey materials next to each other.
- Timing is automatic: one 75 ms frame; idle 8, walk 8, run 8, attack 13 (4 anticipation / 3 raise / 1 smear / 5 recovery),
  hit 2 (recoil + flash), death 14, cast 12.

## Spec format

```jsonc
{
 "name": "ashen_knight", "style": "duskborne", "rig": "humanoid",      // or "quadruped", "prop"
 "concept": "one line: who, role, defining feature",
 "frame": [48, 48], "anchor": [24, 40],     // canvas and the feet pixel. Leave room for smears (~2x body)
 "shadow": {"w": 13, "h": 3},               // ground contact ellipse, never wider than the body+2
 "smear": {"color": "#ebede9", "edge": "#6ff0f0", "radius": 13, "width": 6, "height": 8},  // weapon arc
 "fx": {"ramp": "glow_pink", "hand_h": 14, "reach": 6},   // cast charge/burst colour + where hands are
 "anim": {"props": ["scarf_tail"], "prop_swing": 8, "attack_lunge": 3, "idle_bob": 2, "run_bounce": 0.5,
          "raise_weapon_rot": [45, 70, 0]},   // turn a small weapon toward the camera during the wind-up
 "materials": {"my_mat": {"ramp": "cloth_red", "shades": [0, 1, 2, 3]}},  // optional extra materials
 "clips": ["idle", "walk", "run", "attack", "hit", "death"],               // optional subset
 "bones": [ { "name": "root" },
   { "name": "hips", "parent": "root", "at": [0, 0, 6], "parts": [ ...primitives... ] },
   ... ]
}
```
Units are **pixels**. Axes: **x right, y away from the viewer (character faces −y = south), z up**.
Feet are at z = 0. `at` on a bone = its joint position in the parent's space (rotation pivot).

**Primitives** (in the bone's local space): every part has `shape`, `mat`, optional `at`, `rot` [deg x,y,z], `blend` (smooth-merge radius).
- `ellipsoid`/`sphere` `r` (number or [rx, ry, rz]) — heads, bodies, clumps
- `capsule` `a`, `b`, `r1`, `r2` — limbs, tails, horns, branches (tapers)
- `box` `half` [hx, hy, hz], `round` — blades, belts, visors, armour plates
- `cylinder` `r`, `h` (half height), `round`; `cone` `r`, `h` (apex at +z; add `"flat": true` or `"r_top"` for a
  flat-based cone / frustum — robes, hats, skirts, tree tiers) — hats, ears, spikes; `torus` `R`, `r` (flat ring) — collars, scarves
- `roof` `half` [hx, hy], `h` (ridge height), `gable` (bool): a pitched roof on a flat base; hip roof (pyramid on a square), or vertical gable ends.
- `"subtract": true` carves the part out of the bone.
- `stamp` — exact hand-placed pixels pinned to the bone (faces, teeth, glints, runes, buttons). Not 3D:
  `{"shape": "stamp", "at": [x,y,z], "normal": [0,-1,0], "rows": ["a.a", ".b."], "key": {"a": "pupil", "b": "bone:3"}}`
  Drawn centred on the projected point when the normal faces the viewer (`min_facing`, default 0.2) and not behind a
  nearer part. `.` = transparent. Key values are `material` (its brightest shade) or `material:shade`. For 3/4 views give
  each eye its own stamp with a normal tilted outward (e.g. [-0.5,-1,0] / [0.5,-1,0]) so the far eye hides by itself.
  For profile views lower `min_facing` (e.g. 0.05) and add `"clamp": 2` so a stamp that lands just outside the
  silhouette slides inward onto the head instead of vanishing.
- `stamp_row` — a row of stamps along a wall (windows, a door), laid out on the face as drawn instead of as separate
  3D points: `{"shape": "stamp_row", "normal": [0,-1,0], "at": [0,0,z], "count": 6, "rows": ["a"], "key": {"a": "window"}}`
  One whole-pixel pitch between `margin` px (default 1) from the face's edges; windows are dropped rather than packed
  closer than `min_pitch` (3); each sits z px above the face's drawn bottom edge in its own column, so a row runs
  parallel to that edge and floors line up in columns. Skips pixels off the face (under an eave) and keeps
  `keep_clear` px (1) from earlier rows: put the door first. `tools/vista/vlib.facade` writes these.

**Pixel-scale modelling rules**
- Nothing thinner than **1.2 px radius** (it disappears or flickers between frames). Eyes: r ≥ 0.6 and push them 0.3-0.6 px *out of* the face surface.
- Each bone is a rigid layer: **it keeps identical pixels while it only moves** — that's the anti-swim guarantee.
  So put things that should move together on one bone, and parts that should overlap with a visible seam on different bones
  (the forge draws a dark inner line where a nearer bone overlaps a farther one).
- Front details face **−y**. Put the lit side's interest on the upper-left (light comes from the upper left, front).
- Weapons: a `sword`/`weapon` bone parented to `armR` at the hand. It is auto-hidden on the smear frame.
- bone `"hidden": true` — only drawn on frames that list it in `"show": ["arrow"]` (custom clip frames): arrows,
  thrown knives, spell orbs. A `sweep` on a bone that moves along its own axis (a loosed arrow, a thrust: pose the
  bone's `at` far ahead on the release frame) draws a straight comet streak instead of an arc.
- spec `"strings"`: 1 px lines between bone points (bowstrings, ropes, chains), hidden behind nearer parts:
  `[{"name": "bowstring", "points": [["bow", [0,1.5,10]], ["bow", [0,1.5,-10]]], "pull": ["foreR", [0,0,-3.3]],
  "mat": "shirt:3"}]`. Frames that `"show"` the string's name bend it through `pull` (a drawn bow).
- Archer draw (specs/sunmeadow/ranger.json): body side-on (hips rz ~70), bow arm aimed straight at the target,
  bow `aim` [0,1,0] + `roll` -90 (upright), draw shoulder pulled in (`armR.at`), elbow high, hand at the cheek.

**Bone & spec options (engine v2)**
- bone `"seam": true` — always draw a dark seam + contact shadow where this bone overlaps another (tiers, plates, layered cloth).
- bone `"z_bias": -2` — pull a bone toward the viewer in depth sorting (e.g. a small weapon that hides behind a big hat).
- material `"sky": 0.3` / `"sky_obj": 0.2` — tops of each part / of the whole object lighter, undersides darker
  (crowns, bushes, fur backs). `"bias"` shifts all light; `"thresholds"` sets shade bands per material.
- spec `"view": {"yaw": {"S": 14, "N": 14}, "widen": {"S": 1.15, "N": 1.15}}` — cheat front/back views like pixel
  artists do: turn a few degrees to show the body side, and widen on screen so long animals don't become columns.
- flora params: `tree_round` trunk_frac, trunk_r; `tree_pine` tips, droop; `bush` berry_r.

**Detail materials** (the fix for "too round"): add to a material
`"detail": {"kind": "fur|feather|cloth|plate|scale|leaf|bark|stone|hide", "scale": 1.0, "amount": 1.0}` for a surface
pattern (fur strands, feather scallops, cloth folds, plate seams with rivet glints, leaf clusters, bark and stone cracks,
hide wrinkles) and `"edge": {"kind": "fur|feather|leaf", "amount": 0.35}` for a broken silhouette (tufts, notches).
Patterns are painted in the part's own space, so they stick to it and stay pixel-stable while it moves. The duskborne,
sunmeadow style materials already carry sensible defaults; set `"detail": null` in a spec material to turn one off.
Optional carved shading: spec `"shading": {"facets": 14 | 26, "crease": 0.35}` (flat planes + crease lines).

**Rigs & required bone names**
- `humanoid`: `root > hips > torso > head`, `torso > armL, armR`, `hips > legL, legR`. Optional anything else (props list swings 2x).
  Arms hang along −z from the shoulder; legs along −z from the hip.
  Optional elbows: `foreL`/`foreR` bones parented to `armL`/`armR` at the elbow (hand + weapon go on the fore bone);
  the built-in clips bend them automatically.
- `quadruped`: `root > body > head (> jaw, ears)`, `body > legFL, legFR, legHL, legHR, tail`. Body length along y (head at −y).
  Clips: idle, walk, run, attack (leap-bite), hit, death.
- `prop`: use `"generator": "tree_round" | "tree_pine" | "bush" | "rock" | "dead_tree"` with `"params"` (see pp/flora.py),
  or write bones yourself with `"rig": "prop"` and `"directions": ["S"]`.

**Smear options** (spec `smear` or per fx event): `"plane": "h"` (horizontal sweep) or `"v"` (overhead chop),
`"tilt"` degrees (diagonal), `"side"` lateral offset of a vertical arc, `"forward"` push the arc centre forward, per-event `a0`/`a1`/`thick` to shape the arc.

**In-sprite VFX**: any standalone effect can play inside a clip, one effect frame per sprite frame:
`{"kind": "vfx", "effect": "shockwave", "frame": 2, "at": "front|hand|feet|centre|above", "offset": [dx, dy],
"ramp": "stone", "params": {...}, "pivot_y": 0.6, "behind": true}` (behind = drawn under the body).

**Custom clips**: `"custom_clips": {"name": {"loop": false, "frames": [{"pose": {"armR": {"rot": [-90,0,0]}}, "hold": 2,
"squash": [1.1, 0.8], "root": [0,-2,0], "fx": [{"kind": "smear", "arc": "wide"}], "hide": ["sword"], "flash": false}]}}`
— pose values are offsets from the rest pose. `"away": true` on a frame keeps a backward fall readable: it rolls
sideways in S/N and falls face-down away from the camera in NE/NW (the built-in death does this, and slides
the feet forward `death_slide` px, default 0.4 x body height, so the body lies inside the frame). Add the clip name to `clips`.

## Size and 2D-HD maps
- **`"size"`** in a spec: `"tiny"` 14, `"small"` 22, `"medium"` 32, `"large"` 44, `"huge"` 58 (visible rest height in
  px; a ~30 px humanoid hero is about medium) or `{"height": px}`. A style may override the table with `"sizes"`.
  The forge scales the whole spec (lengths and the style's motion lengths, never angles/timing/colours), refits the
  frame, and writes `height_px` / `width_px` / `size` into the build json. Author at any size, declare the size.
  Check a family with `pp sizes <builds...>` (sorted lineup with class rulers); `pp lint` flags classes out of order.
- **`"maps": ["normal", "height"]`** (or `pp build --maps normal,height`) writes `<name>_<clip>_normal.png`
  (RGB = world normal * 0.5 + 0.5; x right, y away, z up) and `_height.png` (grey = px above the feet x
  `height_scale`) beside each sheet, same layout, alpha only on the model's pixels. For real-time lighting in a game
  (2D-HD): light the finished sprite, keep the added light in a few steps so it stays pixel art.

## Motion (family feel)
Each style has a `motion` block, so a family moves as one. A spec's `anim` overrides any key.
- `gait` (walk + run, humanoid and quadruped): `stride` (classic), `hop` (both feet, off the ground; rabbits, spirits;
  `walk_hop`/`run_hop` px), `lurch` (bent forward, hip sway, heavy footfall; quadrupeds prowl low), `bounce` (springy,
  squash on every step), `glide` (low, level, arms still; run = low dash with arms swept back).
- `idle_style: "float"` + `hover` px: the body floats off the ground in every clip (shadow stays down and shrinks);
  deaths drop to the ground. `float_bob` = idle drift px.
- `attack_style` (built-in attack): `slash` (13 f), `dart` (leap in, strike mid-air, drift back), `heavy` (trembling
  wind-up, crushing impact, hit-stop), `hop` (spring up, strike on landing), `iaido` (stillness, one-frame draw, frozen
  follow-through). `hitstop: n` freezes the impact of hand-written `custom_clips.attack` for n frames.
- Families: Hollow Court lurch/heavy, Meadowfolk bounce/hop, Wayfarers stride/slash,
  Ember Spirits float + hop/dart.
- Walks are keyed contact (0, 4: full stride, footstep, 1 px weight shift) / passing (2, 6: body high, 2 px foot lift).
  Runs lean `run_lean` (22) with the chest `run_lead` px (2) ahead of the hips. Props trail 1 frame and get spring
  follow-through; weapon bones (`smear_hides`) lag the hand instead of swinging with it.
- **Limited animation** (stop-motion timing, on by default): built-in clips show fewer, stronger poses and hold
  each one, like Guilty Gear Xrd / anime "on twos". Loops step on twos (walk = 8 poses x 2 frames); one-shots keep
  their designed key poses (wind-up held 3, one-frame cut, follow-through held 3). `anim.on` sets the hold
  (1 = every frame moves, 2 default, 3-4 choppier) or per clip `{"walk": 2, "run": 1}`; run and hit stay on ones.
  Hand-written `custom_clips` keep their frames unless the clip sets `"on": n`. Frame counts never change.
- Runs are keyed contact / down (lowest, squash) / push-off (rear leg long, knee drive, stretch) / flight (both
  feet off, highest), leaning forward `run_lean` with the hips countering the shoulders.
- `anim.carry = {"bow": {"aim": [x,y,z], "up": [0,0,1]}}` keeps a carried item at one body-frame angle in idle,
  walk and run (no flailing bow or spear). `"up"` on any aim also fixes the bone's twist (its local z).
- Check motion with `pp review <dir> --onion`: each clip's frames overlaid (blue = first, red = last) over the ground line.

## Inspect, variants, layers
- **`pp inspect <spec> --clip C --dir D --frame N`**: reads the real bake of one frame. It prints a table with one
  line per part, nearest first: pixels, bbox, value (Oklab L), materials and colours. It also lists parts hidden in
  this view, touching parts whose values are too close (dL < 0.08), attach points, and a glyph grid (one letter per
  part). It writes an image: sprite | part map | material map, with the same letters. Use it when you can't tell
  what a blob is, why a part vanished, or where the hand is. Don't use it to write reports.
- **`pp variants <spec> --vary key=a,b,c`** (dotted path; `bones.head.parts.0.r` addresses bones by name;
  `key=lo..hi --sample 6 --seed 3` draws keyed values) builds each row as a normal build in /tmp and shows a
  labelled still grid plus an animated grid. Row v00 is the spec as it is. A row that renders identically to an
  earlier one is flagged, e.g. `attack_style` under a hand-written attack. Each row lists its lint WARNs.
  `--apply N` writes row N into the spec. Choose by looking at the animated grid, not the still.
- **`"attach": true`** (or `{"muzzle": ["gun", [0, -6, 0]]}`; where = `tip|joint|centre|[x,y,z]`) writes per-frame
  points into the build json: `clips.<c>.attach.<dir>[frame] = {head, hand_R, hand_L, weapon_tip, feet: [x, y,
  visible], box: [x0, y0, x1, y1]}`. Games use them for spawn points (spells, muzzles) and hitboxes.
- **Combo clips** (`"layers"`): `{"run_attack": {"base": "run", "over": [{"clip": "attack", "bones": "torso/",
  "spine": 0.5}]}}`. The legs keep running while the torso subtree plays the attack (`name/` = the bone and its
  children). `spine` blends the waist. The hit, smear and hitstop come from the attack (the legs freeze on impact
  too); footsteps and ground speed come from the base. Combos are listed with the rig's clips and baked into their
  own sheets.
- **Life** (`"life"` in a spec, or as a style default): small additive motion in whole pixels, off unless asked for.
  `sway` {bones, px, frames, wave}: sideways travelling wave for crowns, flags and sails. Flora trees use it by
  default. `flutter` {bones, px}: cloth tips flick 1 px on an 8-beat. `look` {every, deg}: every Nth idle breath
  the head glances aside and back (the idle gets N times longer). Keep it subtle. The idle-change lint and
  `pp review --onion` catch parts that boil.
- Map kits (pp.map): an object's `"build"` can be a list of **same-footprint** variants. Each placement gets a keyed
  pick, never the same as its nearest same-kit neighbour. Don't mix sizes (rows break) and don't flip lit sprites.

## Concept sheet → sprites: what to avoid (failed "wayfarers" party, 2026-09-27)
- Don't force chibi. Copy the concept's proportions (lanky, small head); the chibi default killed the look first.
- Don't transcribe detail. At 26-30 px keep 3-4 colour blocks + skin + one accent; studs, vials, checkers, scales, trim = noise.
- Don't build angular designs from ellipsoids/capsules: they bake into lumpy blobs. Graphic concepts need boxes/wedges/flat cones.
- Don't let 8 artists invent 8 bodies. One shared base body first, then costume + one defining feature each.
- Don't fix "too busy" afterwards by stripping: the result is flat but generic. Decide the simple read before modelling.
- Prototype ONE character against the concept and get sign-off before fanning out to the family.

## Styles (styles/*.json, generated by tools/make_styles.py)
Materials are shared by every asset in a style — that's the consistency. Use style materials; add a spec material only
by pointing at an existing style ramp. List them: `python3 -m pp materials <style>`.
- **duskborne** — dark fantasy action. Deep desaturated bodies, near-black ink, ONE glowing accent (cyan/pink/fire).
- **sunmeadow** — bright cozy adventure. Warm saturated mids, soft values, coloured outlines, green ground.
- **vermilion** — folk-print spirits. Three inks on cream paper: black masses (`ink`, `ink_flat` for sticks),
  red coats/flames (`red`, `canopy` for crowns), painted marks (`red_mark`, `bone_mark`), dry-brush `fur`.
  No outline, 1-2 tones; VFX use `fx_ink` (hot core = darkest ink). Put markings on as stamps (chevrons, bands).

## VFX sheets
`python3 -m pp fx <kind> --style <style> --ramp <ramp> [--param k=v ...]`: kinds `slash, hit_spark, burst, eruption, aura,
dust, projectile, lightning, sparkle, leaves, shockwave`. Eruption takes `spike_h`, `spike_w`, `rune_r`; leaves take `leaf_size` (2 = specks, 3 = two-tone leaves), `count`;
aura takes `radius`, `tongues`, `tongue_w`, `tongue_h`, `motes`, `sustain`; hit_spark `scale`, `ray_w`, `rays`, `sparks`;
dust `puffs`, `radius`, `two_tone`; sparkle `star_size` (3 = 7 px cross), `ring_w`, `ring_r`, `stars`; shockwave `ring_w`, `chips`.
Poses also take per-bone `"at"` offsets (e.g. lift a hand above the head in a gesture clip). VFX dirs can be passed to `pp pack` (they land in vfx/). Posterized to the ramp; timing rules are built in (fast build, slow fragmenting decay).

## Shipping
`python3 -m pp pack <pack_name> out/<a> out/<b> ... --style <style>` → `packs/<pack_name>/` (sheets, gifs, .aseprite
sources, palette.png/.gpl, preview.png, lineup.png, README.txt). `python3 -m pp aseprite out/<a>` exports one source.

## When the engine is the problem
If you can't get something right with the spec (a missing primitive, a rig limit, an ugly automatic rule), write it in
`REQUESTS.md` (one line: what you tried, what you need, which image shows it). The engineer fixes the engine.
Don't hack around it with dozens of micro-parts.

## Maps (pp.map)
`python3 -m pp.map <map.json> [--still] [--layers]` lays built props out on painted terrain and animates them.
- **terrain** (in order): `fill`, `land` (optional `cliff`), `path`, `paving` (quiet slabs), `planks`, `sea` (1-3 calm tones),
  `shore` (shallows + foam), `canopy` (forests of round clumps; `clear` keeps roads open with a row of crowns along them),
  `massif` (one mountain range from blended summits; `valleys` cut hollows and gorges), `bridge` (a deck at any angle), `wall_face`.
  Regions are `rect` / `ellipse` / `poly` / `path`, with a noisy edge (`rough`). Colours are ramp roles (`tones`), never hex.
- **objects** sort by feet y (`z` changes the order only). `place: id` + `icon` export tap bounds, an outline ring and an
  atlas glyph; `over: true` also draws it above movers (bridges, walls). `cast_shadow` darkens the ground by a ramp step.
- **fx**: smoke, glints, waves, `flow` (streaks down a river path), birds, clouds; **walkers** move along paths.
- **fog**: `regions` (bitmask: each region's own rounded, overlapping shape, so lifting one leaves a soft edge), `ramp`
  (the vista `mist`), a faint ghost of the land beneath; `permanent` regions never lift.
- `--layers` is the engine export: a delta-encoded base loop (only changed pixels), occluders, mover strips with
  px/s speeds, sky clouds, fog + bitmask, places with outlines, extra `sprites`, and an `atlas` (the hand-drawn map, read
  back from the rendered colours, in ink layers). Keep clip lengths divisors of the map's `frames` so the loop is seamless.
Vista kits, layouts and maps: `python3 tools/vista/build.py`.


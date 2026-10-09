# Shared taste layer (environments, buildings, animals)

These rules are true for every pp style. Everything else belongs to the style's "hand" (part 2).
Tags: **E** = the engine enforces it by construction, **R** = checked by eye on the review card, **A** = agent guidance in the skill.

## 1. The layer (14 principles)

1. **One pixel grid.** Every texel is the same size. Placement and zoom are integers. Nothing is rotated or scaled live, and final pixels have no partial alpha.
   *Kept by:* **E**: render/pack, map `--layers` sub-pixel camera (docs/ENVIRONMENTS.md); lint for partial alpha.
2. **Closed palette, quantised last.** Every pixel is a style ramp entry. Content names ramp roles, never hex values. Effects compute in float and posterise at the end.
   *Kept by:* **E**: style palette lock + lint for colours off the palette.
3. **One light per scene.** Every asset and every cast shadow shares one key direction. Parts with asymmetric lighting are re-shaded, never mirrored. Time of day is a grade over the whole map, not a repaint.
   *Kept by:* **E**: style `light`, `pp light`.
4. **One scale axiom.** Everything derives from one reference unit. Trees and landmarks get one declared compression factor.
   *Kept by:* **E**: `pp size` / style `sizes`; `pp lint` reports classes out of order.
5. **One painter per material.** All trees in a scene come from one painter at one leaf size, and the same goes for water, roofs and stone.
   *Kept by:* **E**: the style binds each material to one painter or kit, and the map refuses a second one. **R**: check it on the scene image.
6. **Values first.** Each plane is a calm value mass (ground, water, forest, roofs). Touching parts are separated by a value step. The scene reads in greyscale and as flat silhouettes.
   *Kept by:* **R**: a greyscale + silhouette strip on the review card.
7. **Quiet zones and one focus.** Detail and contrast go where the eye should land. Busy textures never sit next to each other.
   *Kept by:* **A** + **R**.
8. **Clean clusters.** No orphan pixels, no banding, no doubled lines. Slopes use only 1:1, 1:2 and 2:1 steps. Curves are monotonic runs.
   *Kept by:* **E**: `shade.finish` despeckle; lint for orphans. Dither in a style is intentional, so mark it exempt.
9. **Texture by density, at 2-3 frequencies.** Variation drifts (blades, clumps, ripples) rather than sitting in hard patches. Only detail that reads at game zoom is drawn.
   *Kept by:* **A**; **R** at game zoom.
10. **The accent has an owner and a budget.** Muted masses carry the scene. One saturated accent hue belongs to one thing (lanterns, a roof family, flowers) and covers few pixels.
    *Kept by:* **E**: the style declares `accent` {ramp, owner, max share}, and the map and variants obey it.
11. **Everything is grounded.** Anything that touches the ground gets a contact shadow no wider than the caster, falling along the scene light.
    *Kept by:* **E**: `cast_shadow` / shadow ellipse. The shape and colour of the shadow are the style's hand.
12. **Ambient motion only, pixel-stable.** Smoke, water, flags, birds and leaves move in whole pixels. Loops are seamless, with clip lengths that divide the map's frame count. Nothing boils.
    *Kept by:* **E**: the map frames divisor, the idle swim lint.
13. **Animals on held keys.** Animals animate on twos with held extremes. Walks stay slow (about 1.7-2 steps/s), distance owns the gait phase, and far legs sit a rung darker.
    *Kept by:* **E**: `motion.limit`, gait; **A** for poses.
14. **Judge in place, by eye.** Art is judged as the scene at game zoom, not as isolated sprites: one look, one fix. The bar is "do I want to be there?", not a checklist.
    *Kept by:* **R**: one review card per build (scene at 1x/3x, greyscale strip, lint hints).

## 2. Deliberately NOT shared (the hand)

- **Camera/projection:** 3/4 tactics, aerial vista, cabinet, side-on, flat elevation.
- **Pixel density:** the unit size and how much world fits on screen (low-res painterly vs crisp tactics).
- **Shading model:** banded SDF, flat 1-2 tones, half-3D clean planes, ordered dither/halftone, soft wash.
- **Edge mode:** none, selective dark outline, thick clean line, selout, coloured line. No-outline is one hand, not a law.
- **Cast-shadow mode:** soft dithered down-right, big flat lavender shapes, contact only, none.
- **Mark-making:** canopy clumps, grass blades, hatching, dry brush, paper grain.
- **Palette structure:** number and length of ramps, how strong the hue shift is (Apollo-style shifts vs constant-hue "moody"), 2-hue minimal, how dark the darkest colour goes.
- **Shape language and vocabulary kit:** architecture (pitched, flat roofs, stilts, pagoda) and flora (broadleaf, conifer, palm, reeds). These are where styles really differ ("the colour is cheap; the shapes are the work").
- **Light direction and hour palette:** each style picks its own (one per scene stays shared).
- **AA policy:** manual AA on curves vs hard stairs.
- **Ambient vocabulary:** what moves (gulls vs cranes vs lanterns) and its cadence.

## 3. Style contract

To plug in, a style declares:
- **camera** (projection, depth axis) and **pixel density** (unit px, tree compression);
- **light** (key direction, shadow tint, hour grades);
- **shading mode**, **edge mode**, **shadow mode** and **texture/mark mode**;
- **palette structure** (ramps by role: ground, water, foliage, wall, roof, stone, wood, glow, plus the darkest ink);
- **accent** {ramp, owner, budget};
- **vocabulary kit**: one painter or kit per material (terrain, water, canopy, building generator, props) and an ambient fx set;
- **animal motion feel** (on-twos cadence, holds).

The engine supplies the shared layer around these choices. A style is incomplete, and does not ship, until every material it uses has its own painter (no fallback to vista's).

**Calibration brief.** Every style is judged on the same brief, made with its own kit, never with vista's assets: *a small settlement at a water's edge: three buildings (one a ruin), a path and a bridge, a stand of trees, a field or garden, one deer and one wading bird, an ambient set (smoke, water, birds), shown at noon and at dusk.* Each style gets one review card (scene at game zoom, greyscale + silhouette strip, lint hints) and one verdict by eye.

## 4. Character-only findings to drop from this layer

- Frame-count templates for attacks (13 frames), hit (2 frames plus flash), death (14 frames) and cast; smear, hit-stop, anticipation and VFX attack timing.
- Head-to-height 0.40-0.50 (chibi), 22-30 px humanoid targets, the folk face/eye-band recipe, legibility proportions.
- "One big defining feature/weapon", gameplay telegraphing, family IoU < 0.75 for units (it could come back later as an optional check that building families read apart).
- Per-character colour budgets (12-24 colours) and 2-3 shades per part. Shade counts become a shading-mode setting.
- Humanoid walk mechanics (knee fold, pelvis/shoulder counter-rotation, IK feet), 8-direction sheets, mirrored directions, the layer schema, the off-white context outline for units, spell-icon rules.
- The "dark style" value dominance (≥ 70% dark) and the fixed Apollo ramp shape. These are one style's palette, not shared law.
- Radiometry, golden-rule registers and byte-hash goldens.

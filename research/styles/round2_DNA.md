# Style DNA, round 2 (2026-10-07)

What the user wants: each style is defined from scratch by its *hand*, not by recolouring vista. Round 1 showed that a
palette swap only gives you a season. This sheet describes each direction by how it draws.

Refs live in `refs/`. `user_1..5` are the user's Pinterest picks. user_3 (marsh), user_4 (kojiro) and user_5
(angrysnail) are by named artists: **mood only, never shipped or shown in the public gallery**. `r1_*` are the round-1
Scenario refs. Everything else is new Scenario output (Gemini 3 Pro, 1K, 15 images, 180 CU).

Engine today (read from pp/render.py, shade.py, detail.py, map.py):
- **Sprites:** SDF parts on bones, 4x supersampled, then majority vote. Cabinet-oblique projection (K=0.5), plus a
  per-spec yaw that fakes isometric (vista houses use yaw -24).
- **Shade:** one model. Normal·light is thresholded into ramp levels (banded), the outline is "self" (the material's
  own dark step below a threshold, rim above one), plus inner crease lines, and detail patterns (fur, leaf, bark,
  stone…) nudge the level by ±1.
- **Maps:** region SDFs, value noise, grass blades, a dithered water bank, one round canopy painter and one massif
  painter. Shadows are "one ramp step down" (contact only, no projected cast shadow).

So every axis below except palette is currently fixed. That is why round 1 read as recolours.

---

## 1. Frost: clean half-3D
Refs: r1_frost, frost_v2.
- **Camera / density:** true isometric (2:1), mid density, large clean silhouettes.
- **Shapes / detail:** simple boxy masses, steep gables, few details (a window, a chimney). Low detail density, big
  flat planes.
- **Shading:** *flat plane*. Each face gets one tone (top, left, right), with no gradient inside a face. 2–3 tones per
  material.
- **Edges:** none, or a 1 px darker plane edge. The silhouette carries the read.
- **Light / shadow:** cool, high-key, with hard blue cast shadows on snow that copy the building footprint.
- **Marks:** snow caps as a separate white plane, triangle-stack pines, ice floes as flat polygons.
- **Palette:** about 12 colours. White/ice-blue ground, black timber, one red owner (barn).
- **Vocabulary:** black-tarred timber house, stave church, red barn, snow pine, frozen water, floes, reindeer,
  arctic fox.
- **Distinct because:** it reads like a low-poly model drawn in pixels. Shape and plane, not texture.
- **Feasibility:** SDF boxes and roofs exist. Needs: **flat-plane shading mode** (snap the normal to the nearest face
  axis, one tone per axis), an **isometric map projection**, a **projected cast-shadow stage**, a **conifer canopy
  painter** and a snow-cap material. Medium effort; the most of it is shading-mode work.

## 2. Saffron: thick ink line, painterly fill
Refs: r1_saffron, saffron_v2.
- **Camera / density:** 3/4 top-down, mid density.
- **Shapes:** soft blocky adobe, domes, awnings with stripes, palms with splayed fronds.
- **Shading:** 3–4 painterly steps with slightly broken band edges. Warm lights, violet shades.
- **Edges:** *thick, clean, dark warm outline* (1–2 px) around every object, plus inner lines at roof and wall breaks.
  This is the signature.
- **Light / shadow:** warm afternoon light with long violet cast shadows (palm shadows on sand).
- **Marks:** stripe patterns on cloth, sand ripples, crop rows.
- **Palette:** about 16 colours. Ochre, terracotta and sand, a turquoise water owner, a violet shadow family, and
  striped accent cloth.
- **Vocabulary:** flat-roof adobe, dome, minaret, awning, palm, canal, terraced garden, camel, goat.
- **Distinct because:** comic-book ink line around a warm, painted world.
- **Feasibility:** needs an **ink line mode** (fixed ink colour, uniform width, outer plus selective inner) and a
  palm canopy painter. Needs an **adobe/dome/awning kit**; this vocabulary was round 1's failure, not the palette.
  Also the projected cast shadows. Medium effort.

## 3. Crisp Tactics: high-detail 3/4 with selective lines
Refs: user_2 (the user said "Oh I do like that"), tactics_ruins, tactics_lake (rejected: it has a grid overlay and is
busy).
- **Camera / density:** 3/4 isometric-ish, *high* pixel density and detail.
- **Shapes:** chunky architecture (arches, stairs, pillars), carved detail, broken stone.
- **Shading:** 4–5 steps, crisp, light from the upper left, with bright top planes.
- **Edges:** *selective dark outline*. A dark line on the shadow side and the base, and lit edges left open or
  highlighted. Hand-AA free.
- **Light / shadow:** soft cast shadows and drop shadows under units.
- **Marks:** *clustered leaf highlights* (bubbly leaf clumps, each with its own lit rim), grass tufts, flower dots,
  moss on stone, brick and slab lines.
- **Palette:** about 24 colours. Saturated green grass, rose-beige stone, small warm accents.
- **Vocabulary:** ruins, arcades, stairs, paving, round and conifer trees, pots, banners, goats, heron.
- **Distinct because:** it's the crisp, juicy look of modern tactics games, packed with detail and very readable.
- **Feasibility:** closest to the engine as it is, since detail.py already does surface patterns. Needs:
  **selective outline mode** (dark on the shadow side only), a **clustered-canopy painter** (leaf clumps with rim
  light), a moss/brick/slab detail kind, and a ruins kit. Medium effort, and the highest payoff.

## 4. Marsh: low-res painterly clusters
Refs: user_3, marsh_stilts, marsh_moor.
- **Camera / density:** 3/4 top-down at *low* density: chunky pixels, so the effective pixel is 2–3x vista's.
- **Shapes:** soft, ragged, organic. Huts are simple blocks with big thatch caps.
- **Shading:** *painterly clusters*. Tones are laid as irregular blobs, band edges broken by noise, and the value
  range is low.
- **Edges:** none. Edges are colour contrast only.
- **Light / shadow:** overcast and diffuse. Almost no cast shadows; mist veils.
- **Marks:** gorse blossom dots, reed strokes with purple tips, birch trunks as white strokes, puddles reflecting the
  sky.
- **Palette:** about 14 colours, desaturated. Ochre, olive, sage, grey-blue, with a yellow blossom accent.
- **Vocabulary:** stilt huts, plank walks, thatch, reeds, gorse, birch, pools, cranes, fox, heather, stone croft.
- **Distinct because:** it reads like a painting made of pixel clusters: quiet, atmospheric, unlike any game kit.
- **Feasibility:** needs a **pixel-density knob** (render at 1/2 or 1/3 scale, then nearest-upscale), a **cluster
  shading mode** (noise-broken bands), a reed/gorse/birch flora painter and a mist veil. The map painters already
  use noise, so medium effort.

## 5. Blossom Light: warm sun and coloured cast shadows
Refs: user_4, blossom_street, blossom_lake.
- **Camera / density:** 3/4 top-down, mid-high density.
- **Shapes:** timber-framed houses with deep roofs, huge round blossom crowns, stone steps.
- **Shading:** 3–4 steps, high key, warm lights.
- **Edges:** coloured (dark plum/brown) lines on buildings, none on foliage.
- **Light / shadow:** the signature is **big lavender cast shadows** thrown across bright cream paving.
- **Marks:** petal scatter, grass fringe, cobble lines.
- **Palette:** about 20 colours. Cream, orange-tile, blossom pink, lavender shadow, fresh green.
- **Vocabulary:** timber-frame, tile roof, cherry tree, wisteria, canal, stone bridge, steps, cats, swans.
- **Distinct because:** it's about light: shadow shapes do the composing.
- **Feasibility:** needs the **projected cast-shadow stage** (sprite height map sheared along the light, coloured
  shadow tone), a blossom canopy painter, petal fx and a coloured line mode. Overlaps vista's grammar more than the
  others do.

## 6. Flat Minimal: few colours, big shapes
Refs: user_5, flat_teal (good), flat_dusk (rejected: incoherent).
- **Camera / density:** iso 3/4, very low density.
- **Shapes:** few big flat shapes with ragged pixel edges, tiny props.
- **Shading:** *flat*, 1–2 tones per material.
- **Edges:** none.
- **Light / shadow:** solid flat cast shadows as darker shapes.
- **Marks:** almost none: a window glow, a tuft.
- **Palette:** 5–8 colours. One hue family plus one warm accent (the window light).
- **Vocabulary:** log cabin, pine, jetty, island, deer.
- **Distinct because:** restraint. Quiet, poster-like, great at small sizes.
- **Feasibility:** cheap. It follows from flat-plane shading, the density knob, flat cast shadows and a palette cap.
  It's a by-product of building Frost.

## 7. Etching: 1-bit plus one accent
Ref: etching.
- **Camera / density:** 3/4, mid-high density.
- **Shapes:** timber houses, a lighthouse, a quay.
- **Shading:** *hatching*. Value comes from line patterns (parallel, cross-hatch, wave lines), not from colour.
- **Edges:** black ink outlines everywhere.
- **Light / shadow:** shown by hatch density.
- **Marks:** waves as rhythmic lines, trees as hatched clumps, rope coils.
- **Palette:** 2 inks (black on paper) plus one red owner.
- **Vocabulary:** harbour, lighthouse, timber houses, boats, gulls, dog.
- **Distinct because:** it's a printmaking look. Nothing else in the market looks like it. Bold and graphic.
- **Feasibility:** needs a **hatch shading mode** (shade level mapped to a pattern tile, locked to the surface the
  way detail.py does), an ink line mode, and pattern painters for water and canopy. Medium effort, and the highest
  novelty.

## 8. Toy Diorama: chunky toy with a thick round line
Ref: toy_diorama.
- **Camera / density:** iso, low-mid density, with a floating soil-block base.
- **Shapes:** rounded, bold, simple: lollipop trees, block houses.
- **Shading:** 2-tone flat.
- **Edges:** thick, uniform, dark navy outline.
- **Palette:** about 10 colours, primary and saturated.
- **Distinct because:** it's a toy box. Kid-friendly, mobile-casual.
- **Feasibility:** cheap once ink line and flat-plane modes exist; also needs a block-base map frame. Risk: it reads
  generic and "AI-kiddy". Keep as an option, not a launch style.

## 9. Lantern Dither: ordered-dither night
Ref: lantern_dither.
- **Shading:** ordered (Bayer) dither between levels, deep indigo, with warm light pools.
- **Distinct because:** of the dither texture, which is genuinely pixel-native.
- **Feasibility:** needs a **dither shading mode** and point-light pools. The other session is adding `pp/light.py`
  (hours). Better used as the **night mode of every style** than as a style of its own.

## Rejected
- **Stained glass:** distinct, but it reads poorly as a game (the lead lines compete with the silhouettes).
- **Felt/clay:** the model returned photoreal felt, not pixel art, so it can't be judged.
- **user_1** (cozy soft-painted farm): smooth painting with no pixel discipline. Its mood sits closest to vista and
  blossom, so it doesn't add a new hand.

---

## Recommendation

**Prototype these 5.** Each one is distinct from the others and from vista:
1. **Crisp Tactics:** the user's favourite, and the closest to the engine.
2. **Frost:** flat-plane, iso, few colours. Flat Minimal comes almost free from it.
3. **Saffron:** ink line plus painterly fill.
4. **Marsh:** low-res painterly clusters.
5. **Etching:** hatching, 1-bit plus one. The wildcard.

That set covers five different hands:

| Style | Line | Shading | Density |
|---|---|---|---|
| Tactics | selective line | 5-step crisp | high |
| Frost | none | flat planes | mid |
| Saffron | thick ink | painterly fill | mid |
| Marsh | none | clusters | low |
| Etching | ink | hatch | high |

Blossom stays a strong option once cast shadows exist; it could be vista's "spring/light" sibling.

**Engine "hand" stages.** Each is shared and opt-in per style. Existing styles stay byte-identical under the snapshot
gate.
1. **Line modes** (`style.line`): `self` (today) / `ink` (fixed colour, width 1–2, outer and/or inner) /
   `selective` (shadow side and base only) / `none`. Unlocks Saffron, Tactics, Etching and Toy.
2. **Shading modes** (`style.shading`): `band` (today) / `plane` (faces snapped to axes, one tone each) / `cluster`
   (noise-broken bands) / `hatch` (level mapped to a surface-locked pattern) / `dither` (ordered between levels).
   Unlocks Frost, Flat, Marsh, Etching, and night for every style.
3. **Pixel density** (`style.density`): render at 1/2 or 1/3, then nearest-upscale, for sprites and maps together.
   Unlocks Marsh and Flat.
4. **Cast-shadow stage** in the map composer: project sprite heights along the light, using the style's shadow
   colour, with hard or soft edges. Unlocks Frost, Blossom, Flat and Saffron.
5. **Brush per style for the map painters:** the same shading and line modes applied to terrain, water and canopy,
   so one painter per material holds inside each style.
6. **Vocabulary kits per style:** flora painters (conifer, palm, birch/reed/gorse, clustered broadleaf, blossom) and
   architecture kits (ruins, adobe/dome/awning, stave/timber, stilt/thatch, harbour). This is the slow part, and
   it's where round 1 actually failed for Saffron.

A style file then becomes palette + line + shading + density + shadow model + brush + vocabulary. Each of those is
"defined from scratch", which is what the user asked for.

**Order:**
1. Line modes and shading modes, which buy the most distinctness per day.
2. Density and cast shadows.
3. Kits per style, starting with Tactics (ruins, clustered canopy) and Frost (conifer, stave), since those are the
   two the user already loves.

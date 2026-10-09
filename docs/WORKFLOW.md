# WORKFLOW — how Pixel Perfect gets built and used

Two roles, one repo.

| | Engineer | Artist (LLM, headless) |
|---|---|---|
| Owns | `pp/` engine, `tools/`, style generators, lints | `specs/`, style *taste* (ramps, thresholds via `tools/make_styles.py`), art direction |
| Reads | `REQUESTS.md`, artist review images | `ARTIST.md`, `STYLES.md` |
| Output | a capability, fixed in the engine for every asset | specs that build into packs |
| Never | tunes one asset by special-casing the engine | paints pixels by hand, or works around the engine with 40 micro-parts |

## The pipeline (why it looks hand-made)
1. **Hidden 3D source.** Specs are SDF primitives on bones, in pixel units.
2. **Bake, don't rotate.** 8 fixed facings are rendered at 4x and reduced by coverage + majority vote. Each bone is a cached
   rigid layer composited at integer offsets — a part that only moves keeps identical pixels (no swimming).
3. **Quantize last.** Pixels are (material, light level); colours come only from the style's locked ramps.
4. **Pixel-art rules as passes:** banded shading (few levels), edges (no black outline; shadow-side darken, light-side
   rim), inner lines where a nearer part overlaps, contact shadows between clumps, despeckle.
5. **Motion from measured timing:** one 75 ms frame, holds by repetition, squash/stretch about the feet,
   2-frame head lag, prop 2x amplitude, 13-frame attacks with a 1-frame smear.
6. **VFX as energy fields** posterized to a ramp, timing rules built in.

## The artist loop (per asset, minutes not hours)
concept line → big shapes → `build --clips idle --dirs S,E` → `review` → fix → add details → full build →
`scene` with its family + a tree for scale → `lint` → done or iterate. Families: `silhouettes` + `lint` on the whole family.

## Definition of done (per asset)
- Reads at 1x in the `scene` view next to its family; defining feature obvious; silhouette distinct.
- All 8 directions look like the same character; attack reads; no swimming in idle.
- `lint` has no WARN you can't explain in one sentence.

## Pack (itch.io)
`out/<name>/`: per-clip sheets (rows = S,SE,E,NE,N,NW,W,SW; cols = frames @ 75 ms), GIF previews, JSON metadata
(anchor, frame size, events like "hit"/"footstep", locomotion speed px/cycle), contact sheet. `python3 -m pp pack <family>`
collects a family into `packs/<family>/`.

## Anti-ceremony rules
- No "golden rule", no canon registers, no derivation essays. Taste is an input; put it in the style file and move on.
- Measure only with the cheap lints. Judge by looking. A test that passes while the art is bad is worth nothing.
- One source of truth per number (style file or spec). Don't restate numbers in prose.

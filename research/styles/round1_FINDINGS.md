# Style search, 2026-10-07

Same scene for every style: the Highgate map plus its 13 props, the sunmeadow deer and fox walk, and an oak.
Only the `style` field changed. Each new style is about 25 anchor colours written by the agent from one Scenario mood
ref and a k-means read of it. Shapes are never copied. Build: about 8 s per style. Scenario: 6 images on Gemini 3 Pro
at 1K, 72 CU.

| style | verdict | notes |
|---|---|---|
| vista (baseline) | keep | identity; calm, painterly |
| **frost** | **launch** | Genuinely new mood: black timber, snow roofs, red accents, ice water (v2 lightened). Painters fit snow well. Limit: the canopy is round broadleaf, so pines need a conifer canopy mode. |
| **gouache** (autumn) | launch, as vista family | Gorgeous rust woods and slate roofs. Same grammar as vista, so it reads as "vista in autumn". Sell it as a season of the vista family, not a new style. |
| **riso** | launch candidate, needs one engine feature | Distinct and fun (pink/teal on paper), playful and toy-like. v1 water was right; lighter water lost the island. To really read as print it needs an ordered-dither/halftone shade mode and paper grain. |
| sumi | not yet | The props look right (cream walls, ink roofs, vermilion). The map fails: the canopy texture is too busy for wash, there's no soft gradient or mist band, and roof_plum shows the accent on 1/3 of houses (accent count should be a spec/variant rule). |
| saffron | not yet | The palette lands, but it's vista with a filter: pitched roofs, a European forest, no palms or flat roofs/domes. Needs a desert building kit and a palm/field painter. The colour is cheap; the shapes are the work. |
| dmg | no | Palette lock holds (exactly 4 colours in the map, a nice proof), but the map turns to olive mush. The look depends on line art and dither patterns the engine doesn't have. Props are fine. |
| sunmeadow / duskborne / vermilion | drop for environments | Character-era styles. Sunmeadow village was rejected before. Duskborne and vermilion have no environment painters/props. |

## What this proves
- **mood image → style works, for palette and mood.** One ref plus about 25 hand-placed anchors gives a new world in
  minutes, every asset retargets with no spec edits, and the palette lock is exact.
- **Palette swaps give seasons and biomes of one style, not new art directions.** frost/gouache/vista are one family.
  Truly different directions (sumi, riso, dmg) are blocked by *painter behaviour*, not colour.

## Engine limits found (not implemented)
1. Shade modes per style: ordered dither / halftone (riso, dmg), soft wash bands (sumi). Today every style gets the same banded SDF shading.
2. Line-art mode: dark 1-px outlines on props *and* map edges (dmg, and an "inked" style). Outline settings only darken self-edges.
3. Canopy variants: conifer/pine, palm, sparse wash trees. One round-broadleaf canopy painter serves every style.
4. Per-style kits: flat roofs/domes (desert), stilt houses/pagoda (sumi). The building generator only knows vista vernacular.
5. Accent budget: a rule for how many props may use the accent ramp (sumi/frost red).
6. Paper/background texture layer (riso, sumi).
7. Painters fall back to vista ramp names; new styles must reuse vista role names (they did, but that's an implicit contract worth publishing).

## Recommendation (2-3 launch styles)
1. **Vista family** with seasons: vista (summer), gouache (autumn), frost (winter). Sold as one style with a season switch. This is the cheapest, strongest launch and plays to the identity.
2. **Riso** as the second, contrasting style, after the halftone/dither shade mode (#1). It proves the engine isn't one look.
3. Optional third later: **sumi**, after the wash/mist painters. It's the most "painterly-distinct" if done right.
Drop sunmeadow, duskborne and vermilion from the environment launch (keep the files; they're character-era).

# Style search round 3 (2026-10-07): same hand, several biomes

Gemini 3 Pro image editing at 1K, anchored with reference images. 13 generations, 162.5 CU in total.
The images are in `refs/`, grouped on `board.png`. Every image is environment, buildings and animals only.

## Saffron (thick ink line): the hand transfers once both refs are used as anchors
- **Desert:** `saffron_desert.png`. It's r1 pushed further: chunkier shapes, dark brown lines and violet shadows. The best one.
- **Green valley:** v1 (`saffron_valley.png`) lost the thick line and turned into a generic cozy RPG. The reroll `saffron_valley2.png` was anchored on r1 plus the new desert and asked for a "uniform 2-px outline on every shape". That held the line, the flat 2-3 tone fills and the violet shadows. Two palms leaked in from the desert ref.
- **Snow:** the reroll `saffron_snow2.png` held the hand well (outlines, flat fills, violet-blue shadows), but it kept the desert's flat-roofed box houses. Chalet roofs were lost.
- **Verdict:** the hand is portable, and it was the *line* that made it portable. The vocabulary (architecture and flora) bleeds over from the anchor image. That confirms the engine split: the hand belongs to the style, and the kit (roofs, trees) belongs to the biome.
- **Engine needs:** ink-line mode with a uniform 2-px outline on everything, a flat 2-3 tone painterly fill, violet cast shadows, and kit sets per biome (adobe/dome, timber/thatch, chalet).

## Marsh (low-res painterly): the hand holds across all three biomes, the strongest result
- **Wetland stilts:** `marsh_wetland.png`. Top-down, the palette carried over, ducks, reeds, gorse. Perspective is consistent; marsh_moor's horizon bug is gone.
- **Birch forest:** `marsh_birch.png`. Same palette logic and clusters, a little crisper. The animals read slightly larger and cleaner than the scene around them, but it's still clearly the same style.
- **Coastal dunes:** `marsh_dunes.png`. Tarred huts, nets, boats and a seal. Same olive, ochre, sand and slate palette. Lovely.
- **Verdict:** one style across three biomes, with the palette doing the unifying work. It's the best proof yet that "style is not biome" can work.
- **Engine needs:** pixel-size setting (chunky), cluster shading, no outline, and reed, gorse, birch and marram painters. Mist is optional.

## Lantern Dither: works as a night mode, not as a style
- **Same scene by day:** `lantern_day.png`. It loses all identity and becomes generic bright AI pixel art. The dither look only exists at night.
- **Dither night v2:** `lantern_night.png`. Readable silhouettes, lamp pools and a moonlit lake. The dither is visible but subtle.
- **Harbour at night:** `lantern_harbour.png`. A different biome in the same night hand, with a lighthouse beam. It holds.
- **Verdict:** use it as the night grade for every style: ordered dither in the shadow ramps, a restricted night palette and warm light pools. Don't ship it as a style of its own.
- **Engine needs:** dither shading mode applied with the `pp light` night grade, plus light-pool sprites around windows and lamps.

## Crisp Tactics, authored variant: it escapes the AI-slop look, but stops being "tactics"
- `tactics_ruins2.png` and `tactics_harbour.png`. A strict palette and geometric shapes produced cube-canopy trees and stepped stone. They are distinct and not slop.
- But they read as a voxel or minimal style, close to Frost and Flat Minimal, and the harbour's giant cubes look odd. The dense, juicy detail that made user_2 appealing is gone.
- **Verdict:** the generic tactics look and the dense detail come together. I'd drop Tactics, or fold the geometric idea into Flat Minimal or Frost.

## Summary
| Direction | Hand holds across biomes? | Best per biome |
|---|---|---|
| Saffron | Yes, with 2-ref anchoring; the kit leaks | desert, valley2, snow2 |
| Marsh | Yes, strongly | wetland, birch, dunes |
| Lantern | Only at night, so a night mode | night, harbour |
| Tactics (authored) | It becomes another style | – |

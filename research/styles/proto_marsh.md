# Marsh prototype (2026-10-07)

Built in a copy (`proto_marsh/repo`, rsynced from `proto/repo`). The real repo was not touched, and build stderr
went to `proto_marsh/log/`, not /tmp.

Cards are in `cards/`:
- `compare.png` is the overview.
- `marsh_wetland_noon.png`, `marsh_wetland_dusk.png`, `marsh_birch_noon.png` and `marsh_dunes_noon.png` each show
  the scene at x6 with the target ref inset, a greyscale strip and a 12x pixel crop (the orange box), plus the
  biome's kit.
- `marsh_wetland_ambient.gif` is the 48-frame loop.

## Engine stages (opt-in; existing assets unchanged)

- `pp/shade.py`: **shading mode `cluster`** (`"shading": {"mode": "cluster", "cell": 1.7, "amount": 0.16}`).
  - Band seams are perturbed by two octaves of part-space value noise (`buf.local`), so they break into irregular
    clusters that stay pinned to the part (no swimming).
  - The existing despeckle keeps them as clusters, not noise.
  - Per-material `cluster` scales it, and 0 turns it off (doors, eyes).
- `pp/detail.py`: two stroke kinds, `dash` (2 px horizontal, for birch marks) and `thatch` (4 px vertical strands).
  A per-material `delta` sets the stroke's level step (birch marks drop 3 steps to the mark colour). The default
  stays -1.
- `pp/map.py`: **terrain kind `clusters`**.
  - It paints a region in a few tones of one ramp by cluster noise (`levels`, `cell`, `drift`, `jag`, `split`),
    instead of smooth bands.
  - Optional `blob` shapes the region itself into pools or patches. Optional `rim` adds 1 px north/south bank
    tones.
  - It ends with an orphan-pixel cleanup (`_orphans`): a pixel with no same-colour 4-neighbour takes the
    neighbours' majority.
- `pp/map.py`: **fx kind `mist`** (late layer).
  - Under a vertical fade plus slow noise patches, every pixel's value is re-read on the style's `mist` ramp.
    Shapes survive as values and colour drains away, so the palette stays closed.
- Pixel size needed no code: a 200x150 map shown at x6.
- Checks:
  - `tools/snapshot.py check base` (against the original pre-prototype baseline): 142 specs, 0 changed.
  - highgate_town and meadow stills are byte-identical.
  - The duskborne, sunmeadow, vermilion, vista, frost and flat style files are unchanged.

## Style + kit (from scratch)

- `tools/make_styles.py` defines `marsh(biome)`, with `marsh` (wetland), `marsh_birch` and `marsh_dunes`.
  - One hand, three ground palettes, the same material roles.
  - Accent owner: gorse bloom.
- `tools/proto/kits_marsh.py` builds 29 specs per biome. One yaw (-35) for every building, boardwalk, garden and
  boat, so their edges share two axes.
  - Wetland: thatched stilt houses with crossed gable horns and the ridge across the picture, a fallen-stilt-house
    ruin and boardwalks.
  - Birch: log cabins (capsule logs, a woodpile) and a log-course ruin.
  - Dunes: black-tarred fisher huts and a collapsed hut.
  - Shared: birch stands, gorse, reeds with cattails, marram, stones, rowboats, a garden bed (furrows laid in
    perspective as a sprite), a crane in profile, a duck, and deer and fox (sunmeadow specs re-targeted).
- `tools/proto/maps_marsh.py`: the calibration brief per biome.
  - A clustered settlement at water, three buildings plus a ruin, a path, a boardwalk or jetty, trees, a garden,
    a deer, a crane, a fox, and ambient mist, glints and birds.

## Verdict by eye

**Yes, the hand survives a build and holds across the three biomes.** All three read as one style: the same
cluster-painted ground and thatch, the same palette logic, the same perspective, and soft mist at the top.

- **Wetland** is closest to `marsh_stilts` / `marsh_wetland`: olive and ochre ground in painterly clusters,
  grey-blue pools, thatched stilt houses with horns, gorse with yellow bloom, birches with dashed bark, cranes in
  the pond, and mist across the top.
- **Birch** is the strongest frame: a warm trodden clearing, white birch trunks with black dashes, cabins under
  thatch, a stream, and the deer in the clearing. It carries the ref's mood.
- **Dunes** has pale sand, a cluster-painted dune-grass slope with gorse, dark tarred huts, rowboats, marram, a
  jetty into the sea, and a wet tide line plus foam band. The style clearly changes biome without changing hand.

**Still weaker than the refs:**
- Water is greyer and more mottled than the refs' clean pale pools. Pool edges need a crisper grass-to-water
  shape.
- The thatch lacks the dark eave line under the overhang that gives the refs their crisp house silhouettes.
- The boardwalks are partly hidden behind houses. In the refs they are a hero element linking the houses.
- The cranes and duck are crude primitives (they read as birds, not yet as cranes).
- Birch crowns are opaque blobs, where the refs' are airy with trunks showing through.
- Log-cabin walls read as flat brown. The individual logs don't separate at this size.
- Ground mottling is a little busy in places. The refs keep calmer masses with clusters at the seams.
- Dusk (`pp light`) works but is the generic grey grade, not a style-owned dusk.
- 1–2 colours per still fall outside the ramps. These come from `Pal.darken` dimming a ramp's darkest tone
  toward ink under cast shadows, which is existing engine behaviour.

## Proven stages to port (behind the real snapshot gate)

1. `cluster` shading mode (shade.py), plus the `dash` and `thatch` strokes and the stroke `delta` (detail.py).
2. `clusters` terrain kind plus `_orphans` cleanup (map.py). This is a general painterly ground brush for any
   style.
3. `mist` fx (map.py).
4. Kit lesson: lay garden furrows, boardwalks and other straight-edged ground features as sprites at the kit yaw,
   not as map-painted rectangles. Then they share the buildings' perspective (the issue the user saw in Flat
   Minimal).

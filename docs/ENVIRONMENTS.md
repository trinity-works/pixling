# Environments: painted maps that live

pp paints a whole map as one picture (`pp.map`), in one locked palette. These tools turn that picture into a place.

| Command | What it gives you |
|---|---|
| `python3 -m pp states specs/vista/house_5.json` | a building's **ruin**, its **construction** stages (walls rising course by course inside a scaffold, rafters, roof) and the finished building, re-rendered by the engine from the building's own spec. Place `house_5~ruin` in a map like any object. |
| `python3 -m pp.map <map> --still --meaning` | the **meaning layer**: what every pixel is (material, collision, water depth, occlusion depth, object ids), written by the painters while they paint. `--layers` always includes it. |
| `python3 -m pp light <map> --gif` | the map at **every hour**: day, golden hour, sunset, dusk, night; windows light building by building, lamps pool warm light, water reflects it. `light.json` lets an engine do it at runtime. |
| `land "blades"`, `water "bank"` | painters for **grass by density** (small pixel blades, no tone patches) and **water from bank to middle** (dithered seams, flat deep middle). |

## Rules that keep a map believable
Learned building the open-world scenes (2026-10). They hold for any environment.

- **The vista look is the identity:** soft, painterly, aerial, muted cream walls, terracotta roofs, teal water, calm
  forest masses. Fix what is flagged inside that language; never swap in a new style.
- **One painter per material, strictly.** Every tree, bush, hedge and forest in a scene comes from the same canopy
  painter at one leaf size. A tree is a bigger crown over a short shaded trunk with a soft down-right ground shadow.
  Mixing kit tree sprites with painted forest breaks the immersion. Check every new asset family against what is
  already on screen for the same material.
- **One scale axiom.** Pick the size of a person and derive everything from it. At walk
  scale a person is 14 px = 1.70 m and the street kit (st_house_*, lamps, fountain, stalls) agrees with it.
- **Paint by density, not patches.** Grass blades whose density drifts; water as a bank-to-middle gradient. Hard tone
  patches read as jagged blotches.
- **Buildings carry the story.** A ruin that rebuilds in beats (scaffold, courses, roof, dust, then smoke and lit
  windows) was the most loved moment of every scene. Light is the other one: a town answering the dusk.
- **Less is more.** One authored, atmospheric place beats many scenes built to a checklist; judge by "do I want to be
  there?", not by measurements.
- **For a game on top:** never round the camera. Draw the world 1 px oversize, scale by a whole number and offset by
  the camera's sub-pixel fraction; non-integer scaling is what makes pixel art look uneven.

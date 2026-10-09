# reel workflow: one character, end to end

The loop that worked on Reaper and Thornbloom. Prototype ONE character, get sign-off, then fan out. Every step
ends with something to look at; judge by eye at game size, animated. The detectors (README "Detectors") give
hints. They don't decide.

```
1 design ──► 2 start sheet ──► 3 takes (H3) ──► 4 check takes ──► 5 cut ──► 6 review
 GPT 2.5       Gemini 3 Pro      pixling scenario      corner colour      reel gambit  reel page / demo
 sign-off      reel split        768P 5 s          reel contact       board, qc    artifact
```

## Setup
- Scenario through the CLI: `pixling scenario login` once (OAuth in the browser; `--device` without one), then
  `pixling scenario call model_schema_get '{"model_id": "model_minimax-h3"}'`, `pixling scenario cost|run MODEL PARAMS`,
  `pixling scenario upload FILE`. Any agent with a shell can do this; no MCP connection in the host is needed.
  An agent host that has the Scenario MCP connected can use its tools instead (same server, same tools; it can
  show assets inline). Conventions: `research/reel/SCENARIO_SKILL.md`. Check the schema with `model_schema_get`
  before running a model, upload file inputs to get asset ids, and get the cost first (`cost`, or `dry_run`).
  CI / headless: `SCENARIO_API_KEY` + `SCENARIO_API_SECRET` in the environment or a gitignored `.env`.
- ffmpeg on the PATH (all video I/O goes through ffmpeg pipes).
- State every spend against the budget the user set, and ask before going over it.

## 1. Design
GPT Image 2.5 Sunburst (13 CU a pair) at the target camera (high top-down, about 60 degrees), facing SE, flat
#FF00FF, no magenta/pink on the character. Use existing characters as style references only when the new one
should match them, because references pull every design toward their style. Show candidates at game size with a
silhouette. Get the user's pick before any video credits are spent. Save candidate sets in `research/reel/designs_<set>/` (local; not kept once a design is picked).

## 2. Start sheet
Generate ALL unique facings (S, SE, E, NE, N) in ONE Gemini 3 Pro image (21:9 4K, 42 CU) so line weight, palette
and scale match. Ask for wide gaps between figures. Save it as `reel/chars/<name>/ref/sheet.png`, then:
```
python3 -m reel split reel/chars/<name>/ref/sheet.png    # -> ref/start_<facing>.png, 2048², one baseline
```
Every facing gets one scale, the feet sit on one baseline, and each figure is centred on its body, not its weapon.
West is a mirror. Gemini sometimes drops the weapon or flips a side view, so check every crop.

## 3. Takes: MiniMax H3 only
`model_minimax-h3`, never Kling (user rule; the older Kling idle/walk takes are legacy). `firstFrameImage` =
`lastFrameImage` = the start frame, 5 s, 768P (80 CU). Sprites end at 256 px, so 2K (130 CU) adds nothing.
One take per facing x state, saved as `reel/chars/<name>/takes/<state>_<facing>_<letter>.mp4` (a, b, c for rerolls).
H3 gives attacks a clear timing arc (held wind-up, one strike, a hold, a fast snap back) with the same beats in
every facing. Budget about 40% rerolls for a multi-hue design.

### Prompt (four blocks, backdrop rule repeated as the last line; both are needed against drift)
> BACKGROUND: a flat chroma-key studio backdrop of solid pure magenta (#FF00FF), exactly as in the first image and
> identical in EVERY frame from the first to the last. The backdrop colour is constant: no colour change, fade,
> gradient, vignette, texture, floor, shadow or lighting change. Nothing is drawn on the backdrop: no slash
> trails, arcs, swooshes, glow, sparks, dust or particles.
> CAMERA: locked-off static high top-down game camera looking down at about 60 degrees, the same angle and same
> on-screen size for the whole clip; no zoom, pan, orbit, rotation or shake. Full body and weapon stay inside the
> frame at all times.
> CHARACTER: <rendering, e.g. 2D game sprite, thick uniform dark outline, flat cel shading>, identical design,
> colours and line weight in every frame. <facing, e.g. "She faces the lower-right in front three-quarter view,
> as in the start image, for the whole clip.">
> MOTION: <one motion paragraph>
> The magenta backdrop stays the exact same flat #FF00FF in every single frame; only the character moves.

Never name other colours in the backdrop block, because the model reads them as suggestions. Motion lines that worked:
- **Idle**: "at natural real-time speed (not slow motion): a calm, subtle combat-ready idle breathing loop ...
  No steps, no turning, no attack and no big gestures. Ends in exactly the starting pose."
- **Walk**: "a steady walk cycle IN PLACE, like on a treadmill, about two steps per second. Body UPRIGHT, hips
  LEVEL and directly under the head: no leaning, no hip thrust ... does not travel across the frame." Stomping or
  marching wording produces a pelvis thrust.
- **Attack**: "in slow motion: ONE <weapon> <strike> toward <direction>. A clear held wind-up ..., then one fast
  ... : one clear moment of contact. Hold at the end, then snap back into exactly the starting stance. Strikes
  only once."
- **Toward the camera (S)**: "drawn flat like a 2D sprite, the same size the whole time, no perspective, never
  comes toward the viewer". Without it the blade balloons out of frame.
- **Away from the camera (N)**: "back stays toward the camera for the WHOLE clip". For a big weapon, ask for a
  horizontal sweep "above her head on screen, the blade stays small", because a cleave seen from behind gets
  swung at the camera.
- **Timing**: keys and holds read better than smooth in-betweens (Guilty Gear Xrd, Dead Cells). Never use
  optical-flow interpolation.

## 4. Check every take before cutting
H3 can let the magenta backdrop drift to other colours mid-clip. This happened in about 1 in 4 takes, and far more
often on back views of a multi-hue character. A drifted take cannot be saved: the per-frame key keeps the
silhouette, but despilling a red, yellow or green backdrop wrecks the character's colours. Reroll it. Don't try
to patch it.
```
python3 -m reel contact reel/chars/<name>/takes/attack_se_a.mp4   # numbered frame sheet: drift, turns, re-swings
python3 -m reel key reel/chars/<name>/takes/attack_se_a.mp4       # matte check over magenta | white | black
```
Look at every frame. Slow a take down before calling it broken: weapon shape changes are often just perspective.

## 5. Cut
Write `reel/chars/<name>/char.json` (copy `reel/chars/_template/char.json`; the format is in the README), then:
```
python3 -m reel gambit reel/chars/<name>/char.json   # -> out/reel/<name>/gambit/
```
Look at `board.png`, the attack onion strips and `qc.json`. Set attack `contact` frames by eye, using the first
frame at the end of the strike (`reel contact`). The automatic pick can land on a glint mid-hold. Reroll bad takes.
Delete `palette.json` after changing `finish` so the palette is refitted.

## 6. Review
```
python3 -m reel page <name>                              # -> out/reel/_review/ (board, every state x facing, raw takes)
python3 -m reel demo <names> --fx fireball_rain,necro_signet   # -> out/reel/_demo/ playable: walk, attack, 1/2 cast
```
Publish the page with its `f/` files as an artifact and send the user the link. Copying sprites into another game is the user's call.

## Spells
Generate the effect on pure black with first = last frame = `reel/fx/black_1024.png`, so it appears from and
vanishes into nothing (H3 768P 5 s). Ask for the high 60° camera, say where the target spot is, and ask for a wide
black margin. Save the take under `reel/fx/takes/`, write a spec beside `fireball_rain.json`, then run
`python3 -m reel fx reel/fx/<name>.json`.

Never chroma-key effects. `reel fx` turns brightness into alpha and un-premultiplies the colour, so the sheet adds
back to the same light with canvas `'lighter'`. The spec sets the key count, fps, the `anchor` (target spot, 0..1
of the generated frame), the on-screen width in `tiles` and `hits` (impact keys for hit flashes). With `auto`,
hits are the peaks of light near the anchor. Set them by eye when a lasting glow masks the impacts. `feather`
fades the light at the frame border and `vignette` fades it to an oval. Use both when a blast fills the frame,
or the effect ends in a straight cut.

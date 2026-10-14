# reel: sprites cut from AI video (experimental)

A second engine beside `pp/`. `pp` builds sprites from SDF specs. `reel` cuts them out of generated video: the
video model (MiniMax H3 via the Scenario MCP) supplies the motion, and the cut supplies the consistency: one
start sheet, one scale, one palette, one outline and one game clock. The output is 8-direction sprite sheets, an
actor JSON and a playable demo.

**Status: experimental.** The pipeline works end to end on four characters, but the art direction is still open
and nothing ships into a game yet. **[WORKFLOW.md](WORKFLOW.md)** walks through making a character, step by step.

| Doc | What |
|---|---|
| [WORKFLOW.md](WORKFLOW.md) | the loop: design, start sheet, H3 takes, checks, cut, review; prompts; spells |
| [LIGHTING.md](LIGHTING.md) | lit side-view sprites: painted frames + steady normal maps that react to 2D lights |
| this README | layout, pipeline, detectors, commands, `char.json` reference |
| [research/reel/NOTES.md](../research/reel/NOTES.md) | research log: what shippers do, model survey, per-character findings |
| [research/reel/SCENARIO_SKILL.md](../research/reel/SCENARIO_SKILL.md) | Scenario MCP/API conventions |
| `.claude/skills/reel-sprites` | the agent skill (short; points here) |

## Layout
```
reel/
  __main__.py   CLI (python3 -m reel <cmd>)
  io.py         video/image I/O through ffmpeg pipes        (Scenario: pp/scenario, `pixling scenario`)
  split.py      facing sheet -> start frames                 take.py      decode + key a take, cached
  key.py        chroma key (detector: matte)                 cut.py       measures, cycles, placement, contact
  keys.py       pose-driven key picking                      finish.py    palette lock, outline, alpha
  game.py       export: sheets, actor JSON                   qc.py        quality gate (detectors: qc flags)
  fx.py         spells on black -> additive sheets           pack.py      matte check views
  page.py       review page                                  demo.py      playable 8-direction demo
  synth.py      synthetic "generator output" for tests      light.py     lit side view: colour + normal sheets (LIGHTING.md)
  light_runtime/ players for lit sheets: litsprite.js (web), lit_sprite.gd (Godot 4), demo.html
  lit/<name>/   lit side-view characters: light.json, clip stills + PATINA maps (local), takes/ (local); _template
  chars/<name>/ char.json, palette.json, ref/ (design, start frames), takes/ (*.mp4, local only)
  fx/           spell specs, black start frame, takes/ (local only)
```
Takes (`*.mp4`), the big facing sheets (`ref/sheet*.png`) and everything under `out/` are not committed. The
committed start frames and `char.json` record how each character was made. Rebuilding the sprites needs the takes.

## Pipeline
```
start sheet   one image with all 5 unique facings (S, SE, E, NE, N) on a shared baseline, flat #FF00FF  (reel split)
  -> takes    image-to-video per facing x state, first = last frame, locked camera (Scenario MCP, MiniMax H3)
  -> key      colour-difference matte, per-frame border key, shadow-invariant, specks dropped,
              soft edges recoloured from the interior (key.py)
  -> cut      one scale per character, feet/torso anchors, walk cycle finder, pose-driven keys (cut.py, keys.py)
  -> finish   one locked palette per character (fitted on every facing's idle), one 2 px outline redrawn at
              sprite size (finish.py)
  -> export   one sheet per state, 8 facing rows S, SE, E, NE, N, NW, W, SW (west = mirrored east), -shadow
              twins, actor JSON, qc.json, attack onion strips (game.py, qc.py)
  -> review   board at game size, every state x facing on the real clock, onions, raw takes (page.py, demo.py)
```

## Detectors
Automatic measurements that find problems in generated video. They give hints for the human review. They don't
replace it.

| Detector | Where | What it finds |
|---|---|---|
| Matte | `key.py` | per-frame key colour from the border median (backdrop exposure drifts), Keylight-style spill, shadow-invariant alpha, connected-component speck removal (stray VFX) |
| Matte check | `reel key` | the keyed take over magenta, white and black, the views that expose halos and holes |
| Contact sheet | `reel contact` | numbered frames: pick contact frames, spot backdrop drift, turns and re-swings by eye |
| Walk cycle | `cut.best_cycle` | the steady-state stretch of a walk take whose ends match best (the loop) |
| Attack poses | `keys.attack_keys` | anticipation, apex (highest silhouette), fastest strike, contact; recovery cut before a second lift; keys spaced by arclength |
| Auto contact | `game.find_contact` | fallback contact = end of the last motion burst before the recovery, when `char.json` gives none (pin it by eye) |
| Walk drift | `keys.drift_offsets` | removes the pelvis's straight-line slide over one loop (the filmed sway stays) and plants the lowest foot |
| QC gate | `qc.py` -> `qc.json` | `facing` (body turned to another facing), `arc` (second swing), `pop` (morph/jump), `dupes` (frozen hold), `sway` (hip thrust), `bob` (feet leave the ground), `seam` (loop jump) |
| Spell hits | `fx.py` | impact keys = peaks of light near the anchor, for hit flashes |

Backdrop drift (H3 recolouring the magenta mid-clip) has no automatic detector yet. Check it with `reel contact`
on every take (WORKFLOW step 4).

## Commands (run from the repo root)
```
python3 -m reel split reel/chars/<name>/ref/sheet.png     # facing sheet -> ref/start_<facing>.png on one baseline
python3 -m reel contact reel/chars/<name>/takes/attack_e_a.mp4   # numbered frame sheet
python3 -m reel key some_take.mp4                         # matte check: source | magenta | white | black
python3 -m reel probe some_take.mp4                       # size / fps / frame count
python3 -m reel gambit reel/chars/<name>/char.json        # -> out/reel/<name>/gambit/
python3 -m reel fx reel/fx/fireball_rain.json             # spell take on black -> out/reel/_fx/<name>/
python3 -m reel page <name> <name2>                       # -> out/reel/_review/index.html (+ f/)
python3 -m reel demo <name> <name2> --fx fireball_rain,necro_signet   # -> out/reel/_demo/
pixling scenario call models_list '{"query": "minimax"}'      # live Scenario catalog (after pixling scenario login)
python3 -m reel light new <name>                          # lit side view: reel/lit/<name>/light.json + clip dirs
python3 -m reel light start ref/design.png ref/start.png  # takes' start frame: figure at the left of a 16:9 key frame
python3 -m reel light frames take.mp4 <dir> --every 2      # stills f<NNN>.png (NNN = filmed frame)
python3 -m reel light loop <dir>                          # walk loop candidates by pose + motion match
python3 -m reel light patina reel/lit/<name>/light.json   # frames still needing maps + CU; --yes runs them
python3 -m reel light build reel/lit/<name>/light.json    # -> out/reel/lit/<name>/: atlases + <name>.json
python3 -m reel light check out/reel/lit/<name>/<name>.json   # pair-by-pair alarms in play order, exit 1 on an alarm
python3 -m reel light demo out/reel/lit/<name>/<name>.json    # playable page (walk, clips, movable lights)
python3 -m reel light export out/reel/lit/<name>/<name>.json <game dir> --engine godot   # sheet + player
python3 -m unittest tests.test_reel tests.test_reel_qc tests.test_reel_split tests.test_reel_fx tests.test_reel_light
```
Keying a 1440² 5 s take takes about 25 s. Results are cached (zlib pickles) in `out/reel/<name>/cache`, keyed on
file + key settings, so re-cuts are instant. The cache is disposable and rebuilds when deleted. `palette.json`
beside a char.json is the character's locked palette. Delete it after changing `finish` (`palette`, `grade`) so
it is refitted.

## char.json
```jsonc
{
 "name": "lancer",
 "concept": "how the refs and takes were made (free text, keep it current)",
 "key": {"color": "auto", "min_part": 0.01},           // auto = per-frame border median; min_part drops VFX specks
 "finish": {"palette": 48, "reoutline": {"width": 2, "strip": 1}, "alpha": "soft", "sharpen": 0.3},
 "gambit": {
  "cell": 256, "rows": 8,                               // default 8 (S..SW rows); 4 = FR/FL/BR/BL
  "scale_from": "takes/idle_se_a.mp4",                  // one scale per character
  "normalize_facings": true,                            // equalise body height across facings (start sheets drift)
  "clips": {
   "idle":   {"takes": {"s": "takes/idle_s_a.mp4", "se": "...", "e": "...", "ne": "...", "n": "..."}, "range": [0, 120]},
   "walk":   {"takes": {...}, "cycle": {"from": 16, "to": 104, "min": 22, "max": 44}},
   "attack": {"takes": {...}, "range": [8, 112],
              "contact": {"s": 67, "se": 58, "e": 65, "ne": 61, "n": 39},   // picked by eye: `reel contact`
              "key": {"s": {"min_part": 0.06}}}                             // per-take key override
  }}
}
```
Clock per state (`game.STATES`): idle 16 @ 0.2 s, walk 8 @ 0.1 s, attack 8 @ 0.1 s, damage 4 @ 0.1 s,
die 18 @ 0.1 s. The attack's contact lands on `attackHitFrame` (4), so the sim contract holds whatever the
video's speed. Per clip you can override `frames`, `frameDuration`, `hit` (e.g. 10 @ 0.08, hit 5: the same 0.4 s
wind-up and 0.8 s total), `ranges` per facing, and `keys_by_dir` for hand-picked source frames.

Other clip options:
- Attack takes can be a list: `["takes/attack_se_a.mp4", "takes/recover_se_a.mp4"]` joins the clips and drops the
  duplicate frame at each join. `"contact": "seam"` puts the last frame of clip 1 on the hit, and `"seam+18"` puts
  the hit 18 frames into clip 2.
- `attack_keys`: `"time"` (Lancer/Duelist) spaces keys evenly in time around the contact. `"pose"` (default) puts
  keys on anticipation, apex, fastest strike and contact, spreads the recovery by amount of motion, and cuts any
  second lift of the weapon.
- Walks: `walk_keys` `"uniform"` with `anchor: "torso"` (Lancer/Duelist) or `"phase"` (default: keys start on a
  foot contact, x keeps the filmed motion minus drift, the lowest foot is planted). Pinning the torso on a stompy
  take reads as a hip thrust, so prompt for an upright walk (WORKFLOW).
- `finish.grade`: {"brightness", "saturation", "contrast"}, applied before the palette fit. Painterly sources read
  dark and muddy at sprite size (Thornbloom). Unset = byte-identical output.
- `gambit.display_scale`: the demo's per-character size (default 1). A heroic 5-head build next to 2-head chibis
  looks undersized at equal body height (Thornbloom 1.2).

The demo ships WebP copies (lossless sprites, lossy q80 effects, about 3x smaller). The PNG masters in
`out/reel` are the export.

## Lit side view (`reel light`, light.py)
Why and how in [LIGHTING.md](LIGHTING.md); steps in [WORKFLOW.md](WORKFLOW.md) "Lit side view". Any left/right
character, any clips. A character lives in `reel/lit/<name>/` (`reel light new <name>`): `light.json`, one directory
of stills per clip (`f<NNN>.png`, NNN = filmed frame, from `reel light frames`), PATINA maps beside them
(`f<NNN>_p_0.png` basecolor, `f<NNN>_p_1.png` normal, green-up, from `reel light patina`), and `takes/` (local only).
Sheets build into `out/reel/lit/<name>/`.

### light.json
```jsonc
{"name": "golem", "concept": "how the image and takes were made",
 "key": [255, 0, 255],                 // backdrop colour of the takes
 "height": 300,                        // body height of the lead clip in sheet px (median)
 "out": "../../../out/reel/lit/golem", // relative to this file; "png": true also writes PNG sheets
 "source_fps": 24,                     // the takes' frame rate (H3: 24)
 "blend_frames": 4, "stop_iou": 0.85,  // crossfade on clip switches (12 fps frames); stop-pose threshold
 "lead": "walk", "rest": "idle",       // optional: default lead = first travelling clip, rest = first looping clip in place
 "clips": {
  "walk":  {"dir": "walk", "loop": [19, 49], "match": 18},   // travelling loop: frames 19..49, 49 repeats 18
  "idle":  {"dir": "idle", "reverse": true},                 // loop in place, played backwards from frame 0
  "swing": {"dir": "swing", "loop": false, "fps": 12}}}      // one-shot in place
```
Clip options:
- `loop`: `true` (default, all stills), `[first, last]` (filmed frames played), `"auto"` (found by pose + motion match;
  the build prints the pick to pin), `false` (one-shot). `range: [a, b]` limits the stills without implying a loop.
- `match`: the frame the loop's last frame repeats. Measures drift (size, ground, travel), never shown. Makes the clip
  travelling (`travel: true`), so it gets `speed` and its frame advances with distance in the players.
- `speed`: `"travel"` (default: the body's travel across the frame) or `"foot"` (the speed at which the planted foot
  stays put: its slide against the body, summed over every frame pair). Use `"foot"` for a walk in place; on the
  golem's walk across, foot and travel agree within 3%.
- `ground` on a travelling clip: default = the drift line (every frame keeps its filmed height). `"lowest"` = follow
  the lowest foot, smoothed over `ground_sigma` frames (default 2): for takes whose whole body bobs off the floor (H3
  walks in place bob ~16 px, feet included). Unsmoothed (`ground_sigma: 0`) jolts the torso.
- `reverse` (play backwards from frame 0), `blend` (crossfade each pose into the next; default off: filmed frames stay
  crisp), `fps` (game clock, default 12: holds follow the filmed spacing, at most 1/fps), `ground` (`"median"` for
  loops, `"first"` for one-shots), `scale` (default: searched so the clip's first pose overlaps the lead's poses; a
  number multiplies the clip's own height fit), `keys_every` (PATINA key spacing for clips in place, default 20).
- Normals: a clip where every frame has a map is stabilised over k-2..k+2 by optical flow; a clip with maps on key
  frames gets them carried to every frame by flow (cheaper, as steady). `reel light patina` maps every frame of a
  travelling clip and keys for the rest.
- Colour: the video frame with the big baked light divided out by one identical filter. The lead sets brightness and
  light lean for all clips; each clip's lean/brightness follows a low-pass (cyclic for loops).
- Travelling clips keep each frame's true height and remove only the linear drift: snapping each frame's lowest pixel
  makes the body hop. Clips in place keep one ground line and their first frame's centre.
- A sheet with nothing travelling (an idle alone) uses its loop as lead and rest: no stop poses, the players loop it
  and the move keys only turn the character.
- Builds cache each clip's stable maps in `<out>/cache/` (keyed on the stills, maps and settings), so re-packing is
  seconds; a fresh 31-frame walk takes about 8 minutes (optical flow).

### Sheet format: `pixling.lit-sprite` v1 (`<name>.json` + `<name>_color.webp` + `<name>_normal.webp`)
```jsonc
{"format": "pixling.lit-sprite", "version": 1, "name": "golem",
 "images": {"color": "golem_color.webp", "normal": "golem_normal.webp"},
 "normal_y": "up",                 // normals green-up (Godot, Unity, OpenGL); world y down in the players
 "atlas": [3340, 3564], "height": 300,
 "faces": 1,                       // the sheet is drawn facing right (1) or left (-1); the other side = mirror
 "blend_frames": 4, "lead": "walk", "rest": "idle",
 "anims": {"walk": {"start": 0, "count": 31, "fps": 12, "loop": true, "blend": false, "durations": [...], "speed": 3.33},
           "idle": {"start": 31, "count": 76, "fps": 12, "loop": true, "blend": false, "durations": [...]}},
 "frames": [{"u": 0, "v": 0, "w": 250, "h": 298, "ox": -126.2, "oy": -297.4}],   // atlas rect + offset from the anchor
 "stops": [{"walk": 0, "idle": 12, "dx": 8.0, "iou": 0.91}],    // per lead frame: the rest pose to stop into
 "starts": [{"idle": 0, "walk": 11, "dx": 8.0, "iou": 0.94}],   // per rest pose: the lead frame to start from
 "stop_iou": 0.85}               // lowered to the 4th-best match when fewer lead frames reach it
```
- Anchor: x on the travel line, y on the ground. Draw frame i at (anchor + (ox, oy) * scale), mirrored about the
  anchor (and the normal's x flipped) when facing the other way. `speed` = sheet px per lead frame: the players
  advance the lead frame by distance, and draw it at the anchor minus the progress inside the frame, so feet never
  slide. `stops`/`starts` keep the classic key names whatever the clips are called.
- Players: `reel/light_runtime/litsprite.js` (web: `LitSprite.load`, `Actor`, optional WebGL `Renderer`) and
  `lit_sprite.gd` (Godot 4 `LitSprite` node: CanvasTexture sprites lit by any Light2D). Same motion rules in both;
  `reel light export <sheet.json> <game dir> --engine web|godot` copies a sheet and its player. Other engines: read
  the json above and follow the rules at the top of litsprite.js.
- Sheets built before 2026-10-13 (the golem prototype) stored normals green-down: flip G to use them.
- `reel light check` alarms (above an absolute limit AND 3x the clip's median step): colour (Oklab L, chroma,
  spread, histogram), normal lean, height, `dFoot` (did the planted foot move), `dTorso` (upper-body acceleration
  along a travelling clip: a lurch or loop hitch), `dMotion`/`dPix` (flow and residual after placement). Fast
  filmed moments can trip `dMotion`; look before rerolling.
- `reel light loop` lists candidates; poses repeat on both sides of a stride's extreme, so confirm the pick with
  `check` (dTorso at the seam) and by eye.

## Characters
None are kept. The workflow stays; the 2026-10 characters (Ember Lancer, Tide Duelist, Grave Reaper, Thornbloom) and
their takes and sheets were deleted on 2026-10-07 (recoverable from git before 2026-10-07). What they taught is kept in
the settings below and in research/reel/NOTES.md: `attack_keys: time`, `walk_keys: uniform` with the torso anchor read
best for chibi cel fighters; MiniMax H3 attacks are the direction (never Kling); a painterly look needs `grade`.
Start a new character from `chars/_template/char.json`.

Spells: `fx/fireball_rain.json`, `fx/necro_signet.json` (H3 768P on `fx/black_1024.png`) are kept as recipes.

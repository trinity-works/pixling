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
  synth.py      synthetic "generator output" for tests
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
python3 -m unittest tests.test_reel tests.test_reel_qc tests.test_reel_split tests.test_reel_fx
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

## Characters
None are kept. The workflow stays; the 2026-10 characters (Ember Lancer, Tide Duelist, Grave Reaper, Thornbloom) and
their takes and sheets were deleted on 2026-10-07 (recoverable from git before 2026-10-07). What they taught is kept in
the settings below and in research/reel/NOTES.md: `attack_keys: time`, `walk_keys: uniform` with the torso anchor read
best for chibi cel fighters; MiniMax H3 attacks are the direction (never Kling); a painterly look needs `grade`.
Start a new character from `chars/_template/char.json`.

Spells: `fx/fireball_rain.json`, `fx/necro_signet.json` (H3 768P on `fx/black_1024.png`) are kept as recipes.

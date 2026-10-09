---
name: reel-sprites
description: Make game sprite animations from AI video. Generate start frames and image-to-video takes with Scenario (pixling scenario), then key, cut and export them with the reel engine (python3 -m reel) into 8-direction sprite sheets (and a playable demo). Use when asked to animate a character from video, add a reel character, reroll takes, or fix reel attack/walk timing.
---

# reel: video -> sprites

Read `reel/WORKFLOW.md` (the step-by-step loop, prompts, spells) and `reel/README.md` (layout, detectors,
commands, char.json format) first.
`research/reel/NOTES.md` has the model list and the research, and `research/reel/SCENARIO_SKILL.md` has the
Scenario API/MCP conventions. Scenario calls go through `pixling scenario` (`pixling scenario status` first; if signed out,
ask the user to run `! pixling scenario login`). If the host has the Scenario MCP connected, its tools work the same way.

Loop for one character (prototype ONE, get sign-off, then fan out):
1. Design (GPT Image 2.5), then all 5 unique facings in one Gemini 3 Pro sheet, cut with
   `python3 -m reel split reel/chars/<name>/ref/sheet.png`. Show the user the design before video credits go.
2. Takes on MiniMax H3 (`model_minimax-h3`) ONLY, never Kling (user rule), 768P 5 s, first = last = start frame.
   `pixling scenario call model_schema_get` first, then `pixling scenario cost` / `run` (pass the model inputs; pixling puts them under `parameters`); state the spend against the
   user's budget and ask before exceeding it. Name takes `takes/<state>_<facing>_<letter>.mp4`. Use the README
   prompt blocks. Check every take's backdrop colour on every frame and reroll drifted ones (they can't be keyed).
3. `python3 -m reel gambit reel/chars/<name>/char.json`, then look at board.png, the onion strips and qc.json.
   Set attack contact frames by eye (`python3 -m reel contact <take>`). Reroll bad takes; don't patch them.
4. `python3 -m reel demo <names> --fx <spells>` (or `reel page <name>`), publish with its `f/` files, send the link.
   Spells: `python3 -m reel fx reel/fx/<spell>.json` (README "Spells").

Rules:
- Judge by looking at every frame, at game size and animated (slow it down before calling a take broken). QC
  flags are hints, not the verdict.
- Keep the settings that worked on the 2026-10 fighters (`attack_keys: time`, `walk_keys: uniform`, torso walk anchor): the user
  accepted them.
- The export is 8-direction by default (rows S, SE, E, NE, N, NW, W, SW; each anim lists them in "dirs").
  `"rows": 4` gives a FR/FL/BR/BL layout.
- Tests: `python3 -m unittest tests.test_reel tests.test_reel_qc tests.test_reel_split tests.test_reel_fx`.

# AGENTS.md

Pixel Perfect: a headless pixel-art forge driven by an agent. Codex, Cursor and other agents read this file;
Claude Code reads CLAUDE.md, which has the same rules plus notes on running several sessions at once.

## Commands
- `pip install -e .` installs the `pixling` command (or `ln -s "$PWD/bin/pixling" ~/.local/bin/pixling`). Without installing,
  run `python3 -m pp <cmd>` from the repo root.
- `pixling` lists every command. `pixling guide` lists the docs; `pixling code` lists the engine modules; `pixling styles` and
  `pixling specs` show the curated styles and the example specs.
- How to make art: `.claude/skills/pixling/SKILL.md` (the same skill is installed into other projects by
  `pixling agent install DIR`).
- Tests: `python3 -m unittest discover -s tests`.
- Formats: pixel art is `pp` (`pixling build`), video sprites are `reel` (`pixling reel`), painterly non-pixel sprites and
  scenes are `painted` (`pixling painted`, Blender 4.2+; `pixling guide painted`). Keep one format per scene.

- Art styles (Vista, Crisp Tactics, Flat Minimal), how a new one is made and the shared taste layer: docs/STYLES.md.
- What pixling offers outside agents, pipeline by pipeline (steps, code, lessons): docs/PIPELINES.md (`pixling pipelines`).
  Keep it, `pixling styles NAME --how` (STYLE_HOW in pp/cli.py), site/ and the pixling skill in step when a pipeline changes.
- Landing page: site/ (static; art rebuilt by `python3 tools/site.py`, see site/README.md).

## Rules
- Python 3.9, numpy, PIL, scipy. Stdlib only for anything new (no SDKs that need 3.10+).
- Judge art by looking at `pixling review` / `pixling scene` images. `pixling lint` is the only measuring. No measurement
  essays and no rule registers.
- Styles are generated: edit tools/make_styles.py, then run `python3 tools/make_styles.py`.
- Engine changes must help every asset; never special-case one spec. Around an engine change, run
  `python3 tools/snapshot.py save <label>` before and `check <label>` after. Assets that don't use the new feature must stay byte-identical.
- Artist -> engineer requests go in docs/REQUESTS.md.
- Scenario (AI generation) goes through `pixling scenario` (OAuth via `pixling scenario login`, or SCENARIO_API_KEY +
  SCENARIO_API_SECRET for CI). Video takes use MiniMax H3 only. Get the cost and ask before spending.
- Stage only the files you changed (`git add <paths>`).

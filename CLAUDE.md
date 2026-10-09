# Pixel Perfect — agent notes
- Python 3.9 + numpy + PIL. Run everything from the repo root: `python3 -m pp <cmd>` (= `pixling <cmd>`; no args lists them).
- Scenario: `pixling scenario ...` (OAuth via `pixling scenario login`); pp/cli.py + pp/scenario/. AGENTS.md is the non-Claude copy of these notes.
- Read docs/WORKFLOW.md (roles, pipeline) and docs/ARTIST.md (spec format, rules). Research lives in research/ (read on demand).
- Maps that live (building states, meaning layer, hour lighting, painters) and the rules for them: docs/ENVIRONMENTS.md.
- Art styles (Vista, Crisp Tactics, Flat Minimal), how a new one is made and the shared taste layer: docs/STYLES.md.
- What pixling offers outside agents, pipeline by pipeline (steps, code, lessons): docs/PIPELINES.md (`pixling pipelines`).
  Keep it, `pixling styles NAME --how` (STYLE_HOW in pp/cli.py), site/ and the pixling skill in step when a pipeline changes.
- Styles are generated: edit tools/make_styles.py, then `python3 tools/make_styles.py`. Brand: logo face = tools/brand_mark.py, mascot = specs/sunmeadow/pixling.json, colours pp/brand.py; files via `python3 tools/brand.py` (docs/brand/README.md).
- Judge art by looking at `pp review` / `pp scene` images. Keep measuring to `pp lint`. No measurement essays,
  no rule registers, no re-deriving colour physics.
- Engine changes must help every asset; never special-case one spec.
- Around an engine change: `python3 tools/snapshot.py save <label>` before, `check <label>` after (builds in /tmp,
  ~25 s). Assets that don't use a new feature must stay byte-identical; any CHANGED line must be intended.
- Artist → engineer requests go in docs/REQUESTS.md.
- Landing page: site/ (static; art rebuilt by `python3 tools/site.py`, see site/README.md).
- `reel/` is a second engine: sprites cut from AI video (Scenario MCP). Read reel/README.md; skill: .claude/skills/reel-sprites.
- `painted/` is the third engine, the non-pixel format: Blender renders painterly sprites from a style + layout
  (`pixling painted kit|compose|game`). Read painted/README.md. It doesn't import pp's renderer; keep pixel and painted apart.

## Several sessions share this repo
- Stage only files you changed (`git add <paths>`, never `git add -A`); never delete or revert another session's files.
- Announce before rebuilding packs/, viewer/ or shared out/ dirs, and say when you're done; test builds go to /tmp.
- Before editing a shared engine file, message the sessions working in it (ListAgents) and agree who owns which function.
- Internal material (notes, pitches, research, refs) goes in `private/`; it never ships. Secrets are never committed.
  Work lands on `dev`, committed from your own worktree or branch (never from a checkout holding another session's
  edits). `main` is what is public: it moves only when the user merges a dev -> main PR, and CI publishes it
  (skill: public-release). Never push to the public repo by hand.

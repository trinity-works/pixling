# site: the pixling landing page

The page is visual-first and dark: a hero wall of real worlds drifting in whole pixels, the pipeline told on a
sticky stage (ask, choose, build, look, ship), a bento of live tiles (hours, 8 directions, states, AI video, painted,
fx, collision, new styles), the styles with their making-of, the gallery and a three-step install. Every image is a
real pixling output from `a/`; no terminal output on the page.

A static page: `index.html` (hand-written, no build step), `a/` (art, all real pixling outputs), `fonts/`, and two
files for coding agents: `llms.txt` (the guide as plain text) and `agents.json` (commands, flags, outputs).

- Rebuild the art: `python3 tools/site.py` (renders building states, hour light and the house-spec steps; copies maps,
  fx and props from `out/`, and tells you which command to run if one is missing).
- Look at it locally: `python3 -m http.server -d site 8000`, then open http://localhost:8000.
- Fonts: Geist, Geist Mono and Geist Pixel Square (headings and labels), all OFL, self-hosted in fonts/ and preloaded with font-display:block so reloads don't flash; the logo is the brand lockup SVG (Jersey 15, OFL, drawn into it).
- Keep `llms.txt` and `agents.json` in step with `pixling` when commands change, and the pipeline cards in step with
  docs/PIPELINES.md. The video and painted cards use `python3 tools/site.py pipelines` (needs the local H3 take in
  reel/fx/takes and a built out/painted/hollow_brook).

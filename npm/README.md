# pixling (npm)

`npx pixling` runs [pixling](https://github.com/trinity-works/pixling), the pixel artist for your coding
agent. The engine is Python, so this package is a launcher: it runs the matching `pixling` release through
[uv](https://docs.astral.sh/uv/) (`uvx`), or through pipx if you have that instead.

```
npx pixling doctor
npx pixling agent install .     # teach your coding agent (Claude Code, Codex, Cursor) to use it
```

Installing it for good is faster: `uv tool install pixling`.

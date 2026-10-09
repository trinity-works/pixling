#!/usr/bin/env node
// `npx pixling ...` -> the Python CLI of the same version, run by uv (uvx) or pipx. No Python packaging on the
// user's side: uv fetches a matching Python and the wheel on first use and caches them.
"use strict";
const { spawnSync } = require("child_process");
const { version } = require("../package.json");

const args = process.argv.slice(2);
const pkg = process.env.PIXLING_FROM || `pixling==${version}`;   // PIXLING_FROM: a local wheel, for testing
const runners = [
  ["uvx", ["--from", pkg, "pixling", ...args]],
  ["pipx", ["run", "--spec", pkg, "pixling", ...args]],
];

for (const [cmd, argv] of runners) {
  const r = spawnSync(cmd, argv, { stdio: "inherit", env: { ...process.env, PIXLING_VIA: "npx" } });
  if (r.error && r.error.code === "ENOENT") continue;      // runner not installed: try the next one
  process.exit(r.status === null ? 1 : r.status);
}

console.error(`pixling needs uv (or pipx) to run its Python engine.
  Install uv:   curl -LsSf https://astral.sh/uv/install.sh | sh      (or: brew install uv)
  then again:   npx pixling ${args.join(" ")}`.trimEnd());
process.exit(1);

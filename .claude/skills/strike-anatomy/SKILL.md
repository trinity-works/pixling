---
name: strike-anatomy
description: Make melee hits land where the sprite art paints them, on the tick they resolve. Measure the weapon (grip -> tip), the feet and the body (hurtbox) in every frame of a sprite sheet with `pixling strike pose`, size the game's melee range from the art with `pixling strike reach`, drive attack frames from the sim's action ticks and the walk cycle from distance walked, then guard all of it with end-to-end tests. Use when asked to fix hits that land early, late, short or past the target, feet that slide, attack timing, melee spacing, hitboxes or hurtboxes for painted or AI-video sprites, in any engine.
---

# Strike anatomy

Read `pixling guide strike` (`strike/README.md`) first: the five steps, the commands, the frame and walk formulas and
the tests to add. `pixling pipelines strike` is the one-screen summary.

Loop:
1. `pixling strike pose` on the attack (`--hit N`, the 0-based contact frame), the idle and the walk (`--walk`).
   A pixling sprite manifest works too: `pixling strike pose out/NAME/NAME.json --clip attack`. Look at every
   `<sheet>.pose.png` before trusting the numbers. A contact frame without a tip needs a fix first (see Limits).
2. `pixling strike reach attack.pose.json idle.pose.json --scale K --ppm P --yscale Y --stop M` with the game's
   own camera numbers. Move the melee stop distance into the band in every facing (exit 0).
3. In the game: the attack frame from the sim's action ticks, the walk frame from distance walked, and every hit
   effect from the sim's contact event.
4. Add the end-to-end tests from the guide, run them and look at the captured frames.

To see it work first: the guide's "Try it on the sample" (the example warrior in `strike/sample/`). Use `--json`
when you parse the output.

Pixel art: the silhouette rule needs larger art (painted or video sprites, body ≥ ~100 px). Small pixel art is hard
to read from its outline (the sword is as wide as the arm). Build it with `pixling build SPEC --maps parts` and
measure the manifest; strike then reads weapon, arms, legs and body from the parts map (or pass `--parts MAP.png`).

Rules: contact is one frame; never blend frames; no screen shake. Size the range from the art; don't slide the
attacker to fake a hit.

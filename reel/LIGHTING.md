# Lit side-view sprites: painted frames that react to light (experimental)

One painted image becomes a walking, idling character that standard 2D lights shade per pixel. It was built on
the moss golem in 2026-10 and shared publicly as "painted game sprites that react to light". The 8-direction
pipeline in [README.md](README.md) cuts chibi fighters for a top-down camera. This one is a side view (left/right,
left = mirror), it keeps the painting's brushwork, and each frame ships with a colour map and a normal map.

```
image        GPT Image 2.5 paints the character on flat #FF00FF                  model_openai-gpt-image-2-5-sunburst
  -> video   MiniMax H3 image-to-video, firstFrameImage only, locked camera,      model_minimax-h3, 80 CU per take
             the character walks across a 16:9 frame (the feet really plant)
  -> frames  key the magenta, find the loop by pose matching, measure the ground speed
  -> maps    PATINA basecolor + normal per frame, then stabilise them over time    model_patina, ~7-9 CU per frame
  -> game    a colour sheet + a normal sheet; standard 2D point lights (Godot CanvasTexture + PointLight2D, Unity 2D)
```

The lighting itself is standard: the same normal-mapped 2D lights Godot and Unity ship. What's new is getting
clean, steady normal maps for painted, AI-animated frames without painting them by hand.

## Steps and what we learned

**1. Image.** Describe the style in the prompt and don't upload a reference. A gouache prompt on GPT Image 2.5 gave
the best brushwork (it beat Gemini, which painted textured backdrops). Use no magenta or pink on the character.

**2. Video.** The walk starts at the left of a 16:9 frame, with `firstFrameImage` only and a locked camera, and
walks across. That gives real travel and planted feet. Make the idle a separate take from the walk's own start
image (same framing). Takes with first = last frame drifted to a forest or a red backdrop (2 of 2), so use the
first frame only. MiniMax H3 only, never Kling. The walk-across is the fragile take: it worked first time on the golem,
but failed 3 of 3 on the fox (an upright biped). Each fox take cut to a new framing around frames 12–20 and the
backdrop drifted to black or cyan, while the idle from the same start frame was clean. Taking the colour word out
of the character block didn't help. A walk IN PLACE from a centred start frame came out clean first time. Its
speed comes from the planted foot (`"speed": "foot"`: how fast the stance foot slides back), and because H3 bobs
the whole body, feet included, by ~16 px, the ground follows the smoothed lowest foot (`"ground": "lowest"`). That
is now the recommended walk take. Check every walk take frame by frame before buying maps.

**3. Frames.**
- Key with `reel.key`, then remove magenta spill at the edges.
- Find the loop by pose-matching late frames against early ones (the golem: frame 49 ≈ 18, a 31-frame stride).
  Don't guess the length: a loop cut one frame short (30) made the body lurch before every restart, and a seam
  blend hid the cause. `reel light loop` ranks candidates, but its top pick can still be off by a frame (on the
  golem it ranked 16→48, period 32, just above the right 18→49, period 31), so confirm the pick with
  `reel light check` and by eye.
- Keep the filmed heights and remove only the linear drift (size + ground line) measured on the matching pair.
  Never snap each frame's lowest pixel to the ground in a side view: the near and far feet touch the ground at
  different screen heights (16 px apart on the golem), so snapping makes the body hop.
- In the game, advance the walk by distance travelled, not by time, so the feet never slide. Finish the step
  when the player stops.
- Play the idle as filmed: no retiming, no pose crossfades, no frame blending. Blends and averages wash the
  colours together and lose the crisp brushwork. Reverse the idle if that makes it follow the character's motion
  curve (quick lift, slow settle).

**4. Lighting maps.** PATINA gives a basecolor and a normal map that relight a painting well. The free depth
normals (Scenario Detection) are worse, and its detection normals came back blank. Raw per-frame PATINA maps
flicker: base brightness swings 0.37–0.54 between frames and the normals' mean lean wobbles, so lit flicker was 4×
the video's own. The fix:
- **Colour** = the video frame itself, with one gentle large-scale delight applied identically to every frame.
- **Normals** = per-frame mean lean removed, then a motion-aligned average over neighbours (k ± 2, optical flow
  from the video frames, cyclic across the loop seam), then a 2 px blur. For an idle, run PATINA on about 6 keys
  and carry their normals along the flow.
- Smooth per-frame lean and brightness cyclically so the loop seam doesn't jump in light.

That brought the lit flicker from 0.052 down to 0.012, the same as the video. Never ship raw per-frame AI maps.

**5. Game.** Pack the colour and normal frames into atlases with a JSON of frames, clips, the ground speed and
the stop poses: the `pixling.lit-sprite` sheet format (README "Sheet format"). Any engine with normal-mapped 2D
lights can draw it. Drop-in players ship in `reel/light_runtime/`: `litsprite.js` for the web (with a small WebGL
renderer) and `lit_sprite.gd` for Godot 4 (a `LitSprite` node using `CanvasTexture`, so `PointLight2D`,
`DirectionalLight2D` and `CanvasModulate` just work). Mirror with `scale.x < 0` rather than `flip_h`. Normals are
green-up. A hand-written shader has to flip the normal's x itself when the sprite faces left. The golem prototype's
sheets stored normals green-down by mistake, which inverted the vertical light (left/right was right); the engine
writes green-up.

**Check every frame in play order** (including the loop seam and walk ↔ idle). Measure colour (Oklab mean/spread),
mean normal, height, torso acceleration (a lurch) and planted-foot motion. Alarm when a value passes an absolute
limit and 3× the clip's median.

## Compared with image-to-3D (Tripo)
Tripo 3.0 from the same painting (75 CU) is honestly good: you get the shape and any angle. But the brushwork
softens, and the model doesn't move until someone rigs and animates it. Here the painting stays the painting and
the motion comes straight from video. The trade-off is one side view, and every new animation (attack, hit,
death) is a new video take that goes through the same steps.

## Cost
The fox, a finished second character: one design (11.5 CU), an idle take and a walk-in-place take (80 CU each),
22 PATINA maps (~200 CU: 16 on every 2nd walk frame, 6 idle keys). About 370 CU, plus 240 CU of failed walk-across
takes.

The golem:
About 2,000 CU over the whole exploration. A finished character costs much less: one image, one walk take and one
idle take (80 CU each), plus PATINA per kept frame (31 walk frames at about 8 CU) or per key for an idle.

## Code
`reel/light.py` (engine) and `reel/light_runtime/` (players). The spec (`light.json`) and the sheet format are in
[README.md](README.md) "Lit side view", and the step-by-step loop is in [WORKFLOW.md](WORKFLOW.md) "Lit side view".
Any left/right character and any clips: a travelling loop (walk) leads, a looping clip in place (idle) is the rest
pose it stops into, and every other clip plays once.
```
python3 -m reel light new <name>                     # reel/lit/<name>/: light.json, clip dirs, takes/, ref/
python3 -m reel light start <design.png> <start.png>  # the takes' start frame (figure left on a 16:9 key frame)
python3 -m reel light frames <take.mp4> <dir> [--every 2 --start S --end E]   # stills f<NNN>.png
python3 -m reel light loop <dir>                     # walk loop candidates (pose + motion match)
python3 -m reel light patina <light.json> [--yes]    # PATINA on the frames that need it; prints the CU first
python3 -m reel light build <light.json>             # colour + normal atlases and the sheet JSON (cached per clip)
python3 -m reel light check <sheet.json>             # every frame in play order; exit 1 on an alarm
python3 -m reel light demo <sheet.json>              # playable page: walk, clips, movable lights
python3 -m reel light export <sheet.json> <dir> --engine web|godot   # sheet + player into a game
python3 -m unittest tests.test_reel_light
```
`pixling reel light ...` is the same command.

| Step | Function |
|---|---|
| frames, key, spill | `dump_frames`, `keyed`, `despill` |
| loop and drift | `find_loop` (pose match), `drift` (linear size + ground drift only) |
| steady maps | `delight`, `stabilise` (every frame has PATINA), `carry` (only key frames have PATINA; flow carries them), `close_loop` (lean/brightness low-pass), `flow`/`warp` |
| maps to buy | `patina_plan`, `patina` |
| game | `build`/`pack` (atlases + JSON), `match_poses` (stop and start poses), `check`, `export`, `demo` |

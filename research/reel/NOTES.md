# Reel research (2026-09-30): video gen -> sprites

A dated log, oldest first. The current workflow is reel/WORKFLOW.md. Kling sections are history: every take is now
MiniMax H3 (user rule, 2026-10-01).

## What shippers do (Steel Maiden, LayrKits, TamerinTECH)
- Character art as the start frame; the same image starts every clip, so identity and scale stay the same.
- Flatten the keyframe background to an exact key colour before generating. Pick a key colour away from the
  character's colours (green for a red-haired hero, magenta for a teal/green one).
- First and last frame: first=last gives a loop; for attacks, generate the pose images, then run pose A to pose B.
- "Slow motion" in the prompt gives more usable in-betweens. Expect 10+ generations per final animation. A 0%
  first-try hit rate is normal. Splice the good sections of several takes.
- Reject a take on camera move, drift, a background change, a limb leaving the frame, extra hands, or a pop. Reroll.
- Never use optical-flow interpolation (it gives ghosting and a video look). Cut keys and hold them instead.
- Repos worth borrowing ideas from: github.com/LayrKits/Sprite-Pipeline (prompting guide, validation),
  github.com/TamerinTECH/claude-skill-klingai-animation.

## Prompt control block (reuse verbatim; motion block goes after it)
Locked-off static camera, same on-screen size for the whole clip. No zoom, pan, tilt, rotation, dolly, shake,
cuts, parallax or scale change. Flat solid pure <KEY> background (#FF00FF / #00FF00), no gradient, texture, floor,
shadow, glow, dust, particles or lighting change. Full body, weapon, hair and cape stay inside the frame at all
times. The character's pelvis stays locked to the same screen point; it does not slide, drift, rise or re-centre
(unless the motion says so). Side view facing right; the character does not turn toward or away from camera.
2D hand-drawn anime game character, thick dark outlines, flat cel shading, same design and colours in every frame.

## Video models on Scenario (live catalog 2026-09-30; now `pixling scenario call models_list`)
Used so far: Kling V3 I2V Pro (start+end frame). It is good at motion, but it turns characters, re-swings
weapons and paints white VFX. Worth testing next, in order:
- Seedance 1.5 Pro (`model_bytedance-seedance-1-5-pro`): first+last frame AND `cameraFixed`; the best fit for a
  locked sprite camera. Seedance 2.0/2.5 (up to 9 reference images, but first/last and references do not combine).
- Motion transfer, for consistent motion across characters and facings: Kling V3 Pro Motion Control
  (`model_kling-v3-pro-motion-control`) and Wan 2.2 Animate Move (`model_wan-2-2-14b-animate-move`) drive a
  character image with a reference video. One good attack or walk performance (filmed, mocap, or one great
  take) can drive every character; this is the most promising fix for "fluid, same timing everywhere".
- Veo 3.1 (`model_veo3-1`): first+last frame and `seed` (reproducible rerolls), but 16:9/9:16 only.
- MiniMax H3 / H3 Max (`model_minimax-h3`, `model_minimax-h3-max-i2v`): first+last frame, seed on Max.
- Luma Ray 3.2 (`model_luma-ray-3-2`): start/end frame plus a `loop` flag, for idles and walks.
- Wan 2.7 I2V (`model_wan-2-7-i2v`): end image and seed; Wan 2.2 I2V also exposes fps (5-24).
- Also listed: FLUX.3 First/Last Frame and Keyframes to Video, Vidu Q3, PixVerse V5 (first+last, seed, 1:1),
  Grok Imagine 1.5, LTX-2.5. Utilities: `model_birefnet-v2-video` (video foreground extractor, a matte
  fallback when chroma fails), `model_meta-sam-3-1-video`, and `model_uthana-video-to-motion-2.1` /
  `model_cartwheel-video-to-motion` (video -> 3D motion; a route to a 3D rig pipeline).

## Scenario models (first survey; IDs from docs.scenario.com)
- Kling v3 i2v pro (`model_kling-v3-i2v-pro`): startImage+endImage, 3-15 s. Turn generateAudio off.
- Seedance 1 Pro / 1.5 Pro: first+last and `cameraFixed`; 2.0/2.5: first+last, no cameraFixed.
- Veo 3.1: first+last and seed, 16:9 or 9:16 only. MiniMax H3, Wan 2.7 (seed), Luma Ray 3.2 (`loop`).
- Pose keyframes with identity: Gemini 3.1 flash image (Nano Banana 2), gpt-image-2 editing, Flux Kontext,
  Seedream 4.5/5 editing.
- Utilities: `model_pixelcut-video-background-removal` (video matte, a fallback when the chroma key fails).
- MCP: `pixling scenario login` (OAuth), then `pixling scenario call <tool>`. Tools: model_schema_get,
  model_run (dry_run gives the cost), upload_asset, jobs_wait, asset_download.

## Animation feel (GDC: Guilty Gear Xrd, Skullgirls, Dead Cells, Cuphead, SF hitstop)
- Keys and holds, not in-betweens: interpolated motion reads as 3D and floaty. Hold each key 2-4 game frames.
- An attack is anticipation (held, 6-15 f), smear (1 f), contact (the most extreme pose, held longer than the video
  holds it), then recovery (10-20 f). Fast in, long out.
- Hitstop, shake and flash belong in the engine (3-5 / 6-8 / 10-15 f by weight), not in the sprite.
- One fixed palette per character; outline in a tinted dark, not black; one saturated class hue owns the costume
  and VFX; the silhouette reads as a black fill at game size.

## Prompt rules learned on the fighters and smith (2026-09-30)
- Start frames: design one keyframe (GPT Image 2.5), then ALL facings (S, SE, E, NE, N) in ONE Gemini 3 Pro 21:9 4K sheet and
  crop them on the shared baseline, so line weight, palette and scale match. W, NW and SW are mirrors.
- Attacks: drive them with keyframes. Make a contact-pose sheet by editing the idle sheet, crop it at the same per-facing x,
  then attack = idle->contact (4 s) and recover = contact->idle (3 s). For a back (N) slam, use idle->wind-up plus wind-up->slam->idle.
  Say "ONE single strike, no bounce", "straight vertical chop, never swing sideways" and "exactly one strike";
  cfg 0.9. Put "second swing, double strike, sideways swing" in the negative prompt.
- Recoveries: "drag the weapon LOW, never above the waist, one smooth movement with no second lift". Without this,
  Kling re-lifts the weapon, which reads as a second attack.
- Walks: "torso UPRIGHT, hips LEVEL and directly under the head, no leaning, no hip thrust; only the legs move, small
  even steps, a gentle bob". Stomping/marching wording produces a pelvis thrust ("humping").
- Kling paints white impact flashes and slash arcs even with negative prompts. The QC (reel/qc.py) and the key picker drop
  small detached blobs, but a burst over the body means a reroll.
- The QC gate (reel/qc.py) flags sway, bob, a second arc, pops, dupes and seams on the placed keys. Attack turns are caught by eye
  on the onion strip; silhouette/colour signatures can't tell neighbouring facings apart.

## MiniMax H3 attacks (2026-10-01, lancer_h3 A/B; that test character is not kept in the repo)
- first = last frame = the start frame, 2K, 5 s, 130 CU. It gives the timing arc the user liked: held wind-up, one
  strike, a long hold at extension, then a fast smear snap back to idle. Every facing gets the same beats, unlike Kling.
- The failure mode is background drift: magenta fades to green, rainbow or navy mid-clip (3 of 6 early takes). Open the
  prompt with a BACKGROUND block ("flat chroma-key studio backdrop of solid pure magenta, identical in every frame,
  constant, nothing drawn on it") and don't name other colours. 4 of 4 takes held after that.
- S thrusts foreshorten toward the camera (the blade balloons out of frame): say "thrust straight DOWN the screen, lance
  drawn flat like a 2D sprite, same size, no perspective". N: "back stays toward the camera for the WHOLE clip".
- Auto contact can land on a mid-hold glint; pick contact by eye = the first frame at full extension.

## Grave Reaper + spells (2026-10-01)
- Big-weapon designs via GPT Image 2.5 with the lancer + duelist start frames as style refs (13 CU/pair); the user
  picked the Grave Reaper (scythe necromancer) over Cinder Blade (slab greatsword) and Thornwild Berserker (axe).
- H3 backdrop drift recurs (2 of 5 Reaper attacks, toward the scythe's lime green); repeating the backdrop rule as
  the prompt's last line fixed both rerolls. S swings still foreshorten the blade larger (kept: reads as stylised).
- Spell takes on black at 768P are plenty (downscaled to 384 px). Fireball Rain and Necromancer Signet both
  worked first try.

## Thornbloom Witch-Knight, GW2/LoL painterly direction (2026-10-01)
- Designs: GPT Image 2.5 with NO style refs (refs pull back to chibi): "Guild Wars 2 concept art / League of
  Legends champion, heroic ~5 heads, painterly brushwork, ONE dominant hue (60/30/10), oversized signature weapon".
  Concepts: Drowned Bellringer (bell flail), Thornbloom (thorn greatsword, picked), Sandglass Juggernaut.
- All takes H3 768P (80 CU). Idle and walk work on H3 (first H3 idle/walk): subtle loop, real steps.
- Backdrop drift was much worse here: 7 of 23 takes, and 4 of 5 N (back view) attacks. Drifted takes CANNOT be
  saved: per-frame keying holds the silhouette, but despilling a red/yellow/orange/green backdrop wrecks her
  crimson, gold and emerald (armour went black-green). Check every take; budget ~40% rerolls for a multi-hue design.
- A cleave seen from behind is ambiguous: H3 swung the blade at the camera. "Horizontal sweep above her head on
  screen, blade stays small" fixed the motion. N currently borrows the NE attack (stopgap).
- Painterly at 70 px reads dark and dissolves into the board: finish "grade" (brightness 1.18, saturation 1.35,
  contrast 1.12) + the cast's 2 px outline fixed it; demo "display_scale" 1.2 lets a heroic build stand taller.

# Motion research: fluid attacks, locomotion and deaths at 13 fps

Sources were read in full (2026-09-27). Items marked [inf] are inferences, not source claims.

## Why our motion looked weird
1. Every key segment eased to a dead stop (`mix_pose` + `ease_io` per segment). Inside an 8-frame cycle,
   every bone stops at every key. Rosen calls this "a sudden velocity jar".
2. Attacks had slow in-betweens in the fast part (3 "raise" frames) and no held extremes.
3. Death was a rigid plank rotating about the feet at constant speed. There was no buckle and no gravity spacing.
4. All bones shared the same timing, so nothing broke successively.
5. Euler lerps on multi-axis keys: the weapon wobbles off its arc.
6. Stance feet followed a sine, so they skated against constant ground speed.

## Rules (with sources)
- **Pose-to-pose, hold then snap.** Hold the extremes and give the fast part 0–1 in-betweens. The Thomas & Johnston
  table (in Lasseter 1987): 0 in-betweens = "hit by a tremendous force", 1 = "hit by a brick", 4 = "crisp", 6–10 = calm.
  Dead Cells (Vasseur): add interpolation frames "before or after the key frames. Never in-between."
- **Overlap / successive breaking of joints.** Lasseter: "the hip leads… the torso follows, then the shoulder, the arm,
  the wrist". Drag and settle time are proportional to weight. "An action should never be brought to a complete stop."
- **Arcs.** Keep path and timing separate. Straight in-betweens kill an action. Slerp rotations.
- **Cycles** need continuous velocity: periodic cubic interpolation, not ease-to-zero at every key (Rosen GDC 2014,
  "An Indie Approach to Procedural Animation": two keys + cubic interpolation looks acceptable even in slow motion).
- **Walk.** Williams keys: contact / down (lowest) / passing / up (highest). Stance is ~60 % of the cycle, swing ~40 %.
  In the body frame the stance foot moves back **linearly** at ground speed. Bob is 1 px at 22–30 px [inf]. saint11: "leg on the ground
  always moves towards the back"; top-down back views use less vertical motion.
- **Run.** saint11: contact / recover (lowest, legs cross) / jump (highest, both feet off) / fall. Stance ~35 %.
  Rosen: the bounce comes from gravity, so faster cadence means a flatter bounce.
- **Attack** (fighting-game frame data, e.g. SF6 st.HP 10/5/18 at 60 fps; saint11 TopDownAttack):
  startup ~30 %, active ~10–15 %, recovery ~55–60 %. Anticipation moves the weapon *opposite* the attack. The strike
  frame "should do the full motion" as a single smear. Recover "in a different arc", and overshoot on the last recovery frame.
  Hit-stop is 1 held frame (light) to 2–3 (heavy) at 75 ms, with a decaying ±1 px shake (Sakurai; Smash/GG hitlag).
- **Smears** (Lendenfeld 2018): smear only the leading part (hand/weapon), bent along its arc. Its edges must move
  monotonically.
- **Death** (saint11 Death.gif; Rosen): the strongest frame comes first (thrown back), then a brief recover/stagger, then "give up": the knees
  bend and the arms and head lag. Fall with gravity spacing (per-frame displacement 1:3:5:7). On impact the body overshoots 1 px into the ground,
  the arms land 1–2 frames later and bounce once. In 3/4 top-down, a fall straight toward or away from the camera foreshortens, so the
  vertical crumple (which reads in every view) carries it, and the topple goes sideways in screen space [inf].
- **Cartoon Animation Filter** (Wang, Drucker, Agrawala, Cohen, SIGGRAPH 2006): x*(t) = x(t) − x''(t) ⊗ A·G_σ,
  i.e. convolve with an inverted LoG. It adds anticipation and follow-through to any curve. The paper uses A = 3 on mocap, with
  σ ≈ the motion period. Re-plant the feet afterwards.
- **Anti-jitter** [inf]: after pixel snapping, no part should go +1 then −1 px inside one motion segment.

- **Limited animation** (Guilty Gear Xrd, Motomura GDC 2015): 3D models with no interpolation. A 35-frame move at
  60 fps shows about 16 poses, 1 frame each in the fast part and up to 4 in slow recoveries. At our 75 ms: loops on
  twos, keys held 2-3, the strike on ones. Every visible pose must be a designed key. Engine: `motion.limit`.

- **Pelvis and shoulders** (2026-09-30 fix): the pelvis shifts over the planted foot, rolls down on the swing
  side and yaws with the forward leg; the shoulders counter-rotate (left shoulder back with the left leg forward,
  like the arms). Torso rx > 0 leans FORWARD; the old walk/run had the lean and the twist signs reversed.
- **Skull Boy run** (the reference's own file): the legs are 1-2 px stubs; the run is sold by the whole body dropping
  3-4 px on contact, a squash, the head and props trailing. Small legs need a body that moves a lot.

## Links
Lasseter 1987 https://web.archive.org/web/2010id_/http://www.evl.uic.edu/aej/527/papers/lasseter.pdf ·
Cartoon Animation Filter http://vis.berkeley.edu/papers/animfilter/TheCartoonAnimationFilter.pdf ·
Rosen GDC 2014 https://www.gdcvault.com/play/1020583/Animation-Bootcamp-An-Indie-Approach ·
saint11 tutorials https://saint11.art/blog/pixel-art-tutorials/ (Walk, RunCycleSimple, TopDownRun, TopDownAttack,
AttackSheet, Impact, Death, 4LegsWalk) ·
Dead Cells pipeline https://www.gamedeveloper.com/production/art-design-deep-dive-using-a-3d-pipeline-for-2d-animation-in-i-dead-cells-i- ·
Lendenfeld smear thesis https://theses.fh-hagenberg.at/system/files/pdf/Lendenfeld18.pdf ·
hitlag https://www.ssbwiki.com/Hitlag, https://sourcegaming.info/2015/11/11/thoughts-on-hitstop-sakurais-famitsu-column-vol-490-1/

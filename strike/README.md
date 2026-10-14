# strike: hits that land on their frame

The idea: **the art sets the rules, and tests hold them.** The sim decides the tick of contact and how far apart
fighters stand. `pixling strike` measures where the blade, the feet and the body are in every frame of a sprite
sheet. The game joins the two, so the blade touches the body on the contact tick. Nobody draws a hitbox by hand.

It works on any sprite sheet (columns = frames, rows = facings, one cell size) and any engine. All points are in
**cell px from the pivot** (the feet point), y down, so one set of numbers holds at every draw size and on every map.

## Try it on the sample
`pixling strike sample` copies an example warrior (painted, one facing, 256 px cells, cut from AI video) into
`./strike_sample/`: an 8-frame attack that lands on frame 3, an idle and an 8-frame walk. It prints these commands:
```
pixling strike pose strike_sample/warrior_attack.png --cell 256 --pivot 128,189.5 --rows se --hit 3
pixling strike pose strike_sample/warrior_idle.png   --cell 256 --pivot 128,189.5 --rows se
pixling strike pose strike_sample/warrior_walk.png   --cell 256 --pivot 128,189.5 --rows se --walk
pixling strike reach strike_sample/warrior_attack.pose.json strike_sample/warrior_idle.pose.json --scale 1.17 --ppm 40 --yscale 0.74 --stop 2.3
#   se: blade crosses the hurtbox at 0.15-2.8 m  stop 2.30 m inside
```
Then open `strike_sample/warrior_attack.pose.png`: the blade in yellow, the tip in red, the feet in green.

## 1. Measure the art
```
pixling strike pose attack.png --cell 512 --pivot 256,379 --rows se,sw,ne,nw --hit 3    # any sheet
pixling strike pose out/knight/knight.json --clip attack                                 # a pixling sprite manifest
```
Each writes `<sheet>.pose.json` and `<sheet>.pose.png` (or `--out STEM`). A pixling manifest (`pixling build`)
gives the cell size, the anchor, the facings and the frame with the `"hit"` event; a clip with walk speed gets
`--walk` on its own. `--json` prints one object (paths, hit frame, hurtbox, stride, tip at contact) for agents and CI.

`.pose.json` (schema `pixling.strike-pose/1`):

| Field | What |
|---|---|
| `pose.<facing>[frame]` | `tip`, `grip` (the weapon's ends) and `feet` (two points), or `null` where nothing was found |
| `hurtbox` | `{x, y, w, h}`: the body without the weapon in the sheet's first frame, 5-85 % of its height, median over facings |
| `stride_px` | with `--walk`: the widest feet spread along each facing |
| `cell`, `pivot`, `rows`, `frames`, `body_px`, `hit_frame` | how the sheet was read |

## Two ways to find the parts
| Art | How | Use |
|---|---|---|
| Painted or AI-video sprites, body about 100 px or taller | **the silhouette** (default): only the alpha is read | `strike pose SHEET ...` |
| Pixel art, or any sprite whose rig you have | **a parts map**: one flat colour per part, painted by the renderer or by hand | `--parts MAP.png`, or a manifest built with `--maps parts` |

**A parts map** says which pixels are the weapon, the arms, each leg and the body. It sits on the sheet's grid and uses
these colours (the manifest's `"parts"` key repeats them):

| Part | RGB |
|---|---|
| weapon | 255, 64, 64 |
| arm | 64, 200, 64 |
| legL | 64, 96, 255 |
| legR | 64, 200, 255 |
| body | 200, 200, 200 |

`pixling build SPEC --maps parts` writes one from the rig (`<name>_<clip>_parts.png`): the weapon is the spec's
`smear_hides` bones (default `sword`, `weapon`), `arm*`/`fore*` are arms, `leg*` are legs by side, the rest is body.
Then `pixling strike pose out/NAME/NAME.json --clip attack` reads it on its own. From a map, the tip is the weapon
pixel farthest from the body core and the grip the nearest; a foot is a leg's lowest pixels; the hurtbox leaves the
weapon out. A frame that draws its blow as a smear arc has no weapon part: the smear pixels above the feet are the
swing, and the tip is the one that reaches farthest along the facing. An exact map also works for any other
pipeline: paint the weapon red in a copy of the sheet.

**The silhouette**, from the alpha alone:
- **Weapon:** the longest thin part of the silhouette. An opening removes everything thinner than `--thin` × body
  height (default 0.04); the longest removed part, over 0.16 body heights, is the weapon: a blade, a staff, a bow
  arc. Its end nearer the body core is the grip, the far end the tip.
- **Feet:** the two lowest leg clusters of the weaponless body. With `pip install 'pixling[strike]'` (rtmlib +
  onnxruntime), RTMPose ankles replace them (the silhouette guess is noisy); `--no-model` turns that off.
- `--hit` is the 0-based frame where the blow lands. Pick it by eye from the take: it is the frame you show on the
  contact tick.

## 2. Let the art set the melee range
```
pixling strike reach attack.pose.json idle.pose.json --scale 0.585 --ppm 40 --yscale 0.74 --stop 2.3
```
It slides a same-size defender's hurtbox out along each facing and prints the ground distances (m) where the
contact frame's blade crosses it. `--scale` is screen px per cell px at your draw size; `--ppm` and `--yscale` are
your camera's ground projection (screen px per metre across; depth foreshortening, 1 for top-down). With `--stop`
it exits 1 when the distance where your AI stops to swing falls outside the band in any facing, so CI can hold it.
- Put the stop distance inside the band in every facing. Then the view never has to slide the attacker to fake a hit.
- A small view-only lean (≤ 16 px, toward the target, never back) may close a leftover gap. Keep it small.
- If a map draws fighters smaller, scale melee range, walk speed and projectile speed by the same size factor
  (hero height ÷ reference height), or the fight reads too fast and the blades miss.

## 3. One tick for contact
The sim owns the timeline: an action has `start`, `release` (contact) and `end` ticks. The view never runs its own
clock for a strike; it maps the current tick to a frame:
```
windup:          frame = floor((tick - start) / (release - start) * hit_frame)      # frames 0 .. hit_frame-1
from release:    frame = hit_frame + floor(since / settle * (frames - hit_frame))  # settle = ~55 % of the aftercast
after settle:    idle
```
So the contact frame is on screen on the release tick by construction. Damage number, hit flash and hit stop fire
from the sim event of that tick, never from the animation. Hit stop: the victim (and a melee striker) hold their
frame 60 ms (100 ms for a heavy hit); the world and the camera keep going.

## 4. Walk by distance
```
cycle_px = 2 * stride_px[facing] * draw_scale       # one cycle = two strides, measured on the feet
frame    = floor(walked_px / (cycle_px / frames)) % frames
```
`walked_px` is the screen distance the fighter moved. The cycle has no clock, so the steps keep pace at any speed
and slow down with the fighter. Don't use a video take's root motion: AI walks often moonwalk.

## 5. Prove it
Add end-to-end tests in the game (not unit tests of the view):
- **Contact frame on the resolve tick**: run a real fight, capture frames around a hit, and check that `hit_frame`
  is on screen on the tick damage resolves, and that the blade (grip -> tip) crosses the defender's hurtbox there.
- **Spacing matches the art**: for every melee skill, facing and map, the stop distance lies inside the reach band
  (`pixling strike reach ... --stop M` in CI, or the same geometry in the engine).
- **Speeds scale with size**, if maps draw fighters at different sizes.

Then look at the captured frames yourself before calling it done.

## Limits
- **The silhouette needs larger art.** It reads painted and video sprites with a body of about 100 px or more.
  Small pixel art is hard to read from its outline: a 28 px knight draws its sword as wide as its arm and its
  contact frame as a smear arc, so the thin-part rule finds no reliable tip. Use a parts map there
  (`pixling build SPEC --maps parts`).
- **Thick weapons** (a mace head, a shield bash) are not thin: the contact frame then has no tip. Raise `--thin`,
  or write that frame's `tip` and `grip` into the json by hand. Don't ship a melee attack without a tip.

## Pitfalls
- Never blend or average frames to smooth a strike; hold the keys. The windup is the readable part: slow, then
  a near-instant contact (~2 frames), then a settle.
- A contact frame "a bit later for juice" is the most common kind of unpolish. Contact is one frame.
- No screen shake, no world-wide hit stop. Fix timing instead.

Code: `strike/measure.py` (`pixling code strike.measure`), the CLI `strike/__main__.py`; tests `tests/test_strike.py`.
Summary: `pixling pipelines strike`.

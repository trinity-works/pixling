// First Snow, painted: a third-person view of the painted layers (built in Blender and stepped into pixel art by
// fp/paint3d.py and fp/hd2d.py; the place itself is fp/place.py). The painting is much wider than a screen; she walks
// anywhere on the snow and the view follows her. The layers stack with every offset in whole pixels (the further ones
// move less: parallax); the only things drawn per frame are what moves: the walker (a sprite sheet in eight headings
// with a pink scarf), her footprints, her breath, the car's exhaust and the falling snow. The actors land on the
// art-pixel grid; the canvas is scaled by a whole number.
import { makeAudio } from 'fp-audio';      // audio.js, through the page's import map (the bundle maps it to a data: module)

// every file the page loads goes through asset(): served, it is the relative path; in the single-file bundle (`fp
// bundle`: one html that opens from file://) the page carries a table of data: URIs (window.__FP_FILES) and the
// path is looked up in it
const FILES = window.__FP_FILES || null;
function asset(path) {
  if (!FILES) return path;
  if (!(path in FILES)) throw new Error('fp: ' + path + ' is not in the bundle');
  return FILES[path];
}
const getJSON = async path => (await fetch(asset(path))).json();
const getBytes = async path => (await fetch(asset(path))).arrayBuffer();
if (FILES) document.querySelectorAll('a.fp').forEach(a => a.remove());   // the first-person walk is not in the bundle

// the query, and what the Look button carried over a reload where the URL can't hold it (nextLook)
const Q = new URLSearchParams(location.search);
{
  let carried = null;
  try { carried = sessionStorage.getItem('fp.look'); sessionStorage.removeItem('fp.look'); } catch (e) { /* no storage */ }
  if (!carried && window.name.startsWith('fp.look:')) { carried = window.name.slice(8); window.name = ''; }
  if (carried && !Q.has('look')) {
    try { for (const [k, v] of Object.entries(JSON.parse(carried))) Q.set(k, v); } catch (e) { /* ignore */ }
  }
}
const audio = makeAudio();
const canvas = document.getElementById('stage');
// Two looks of one place. 'hd2d' (the default): a painted world, pixel actors. The world layers come at the render's
// own size (hd_*.png, 2x the art: one screen pixel each at 720p; hd3_*.png, 3x, when the view is scaled 3x as at
// 1080p) on a canvas of their own underneath; this canvas turns transparent and carries only the art-pixel actors,
// each art pixel SCALE x SCALE screen pixels. 'pixel' (?look=pixel): the same painting stepped onto the art grid.
const HD = Q.get('look') !== 'pixel';
const ctx = canvas.getContext('2d', { alpha: HD });

// a #rrggbb colour as the canvas's little-endian RGBA word, unsigned (>>> 0), as Uint32Array reads it back: map keys
// and lookups (SHADE.get(get(x, y))) must agree on the sign
const hex = h => { const n = parseInt(h.slice(1), 16); return ((255 << 24) | ((n & 255) << 16) | (n & 0xff00) | (n >> 16)) >>> 0; };
const clamp = (v, a, b) => Math.max(a, Math.min(b, v));
const smooth = (a, b, x) => { const t = clamp((x - a) / (b - a), 0, 1); return t * t * (3 - 2 * t); };
const rnd = s => { s = Math.sin(s * 127.1 + 311.7) * 43758.5453; return s - Math.floor(s); };   // a hash: 0..1
const lerp = (r, u) => r[0] + (r[1] - r[0]) * u;
const mod = (a, n) => ((a % n) + n) % n;                  // never negative (T and its cycles can be)

async function loadImage(src, pixels = true) {
  // a picture as a canvas (for drawImage) and, if asked, its pixels
  const im = new Image(); im.src = asset(src); await im.decode();
  const c = document.createElement('canvas'); c.width = im.width; c.height = im.height;
  const g = c.getContext('2d'); g.drawImage(im, 0, 0);
  return { c, w: im.width, h: im.height, px: pixels ? new Uint32Array(g.getImageData(0, 0, im.width, im.height).data.buffer) : null };
}

// ---------------------------------------------------------------- the painting
// scene.json (paint3d.scene_json): the canvas and the composed frame, the camera, the layers (the hill last, with its
// depth), the auto-walk's route, the walk grid and what she walks round, the car's anchors and the shade lookup
const scene = await getJSON('scene.json');
if (scene.title) {
  document.title = scene.title + ', painted';
  const plate = document.querySelector('.plate');
  if (plate && plate.firstChild) plate.firstChild.textContent = scene.title;
}
const WW = scene.w, WH = scene.h, VH = scene.view_h;
const layers = [];
for (const l of scene.layers) {
  const art = await loadImage(l.src);
  const depth = l.depth ? new Uint16Array(await getBytes(l.depth)) : null;
  layers.push({ art, f: l.f, fx: l.fx, depth, hd: null });
}
const hill = layers[layers.length - 1];
let hdc = null, hctx = null, HS = 2;
if (HD) {
  // the 3x world only where the view is scaled 3x (1080p): there it lands 1:1 on the screen; elsewhere the 2x one
  for (const p of viewScale() === 3 ? ['hd3_', 'hd_'] : ['hd_']) {
    for (let i = 0; i < scene.layers.length; i++) {
      try { layers[i].hd = await loadImage(p + scene.layers[i].src, false); } catch (e) { layers[i].hd = null; }
    }
    if (layers.every(l => l.hd)) break;
  }
  if (layers.every(l => l.hd)) {
    hdc = document.createElement('canvas'); hdc.id = 'world';
    hdc.style.cssText = 'display:block;position:fixed;left:50%;top:50%;transform:translate(-50%,-50%);image-rendering:pixelated;pointer-events:none';
    canvas.parentNode.insertBefore(hdc, canvas);
    hctx = hdc.getContext('2d', { alpha: false });
    HS = Math.round(layers[0].hd.w / WW);
  }
}
const HDON = !!hdc;
// the walker painted in Blender (fp/blender/walker.py -> paint3d.walker_sheet): a row of cells per height, across it
// heading by heading each pose plain and lamp-lit
const WS = await getJSON('walker.json');
WS.img = await loadImage(WS.src); WS.px = WS.img.px; WS.w = WS.img.w;
// each ground colour's next darker tone: the palette's steps, and the lamp-lit snow's own (paint3d.lit_shade)
const SHADE = new Map(); for (const k in scene.shade) SHADE.set(hex(k), hex(scene.shade[k]));
const route = scene.route;

// ---------------------------------------------------------------- the camera: place.proj, mirrored from scene.camera
const CAM = scene.camera;
const lens = z => smooth(CAM.lens[0], CAM.lens[1], z);
const ppm = z => CAM.f / (z + CAM.zb) * (1 + CAM.lens[2] * lens(z));                 // art px per metre at depth z
const groundRow = z => CAM.camh * CAM.f / (z + CAM.zb) + CAM.lens[3] * lens(z);
const proj = (x, y, z) => { const k = ppm(z); return [CAM.x0 + k * x, CAM.y0 + groundRow(z) - k * y]; };
const hero = z => 1 + CAM.hero[0] * smooth(CAM.hero[1], CAM.hero[2], z);             // the painter's figure scale

// ---------------------------------------------------------------- the ground she walks (place.walk_grid)
// a grid in metres: the ground's height (the flagstones' tops on the stair), what is underfoot, how far inside the
// walkable area a cell lies (0 outside, 1 a soft edge in) and the headlamps' light there
const WK = scene.walk, NX = WK.nx, NZ = WK.nz, NC = NX * NZ;
const walkBuf = await getBytes(WK.src);
const G = {
  h: new Int16Array(walkBuf, 0, NC), on: new Uint8Array(walkBuf, 2 * NC, NC),
  room: new Uint8Array(walkBuf, 3 * NC, NC), lamp: new Uint8Array(walkBuf, 4 * NC, NC),
};
function sample(a, x, z, k) {
  // bilinear over the grid (edges clamp), scaled by k
  const fx = clamp((x - WK.x0) / WK.d, 0, NX - 1.001), fz = clamp((z - WK.z0) / WK.d, 0, NZ - 1.001);
  const i = Math.floor(fx), j = Math.floor(fz), u = fx - i, v = fz - j, o = j * NX + i;
  return ((a[o] * (1 - u) + a[o + 1] * u) * (1 - v) + (a[o + NX] * (1 - u) + a[o + NX + 1] * u) * v) * k;
}
const heightAt = (x, z) => sample(G.h, x, z, 0.01);
const roomAt = (x, z) => sample(G.room, x, z, 1 / 255);
const lampAt = (x, z) => sample(G.lamp, x, z, 1 / 255);
const cellOf = (x, z) => clamp(Math.round((z - WK.z0) / WK.d), 0, NZ - 1) * NX + clamp(Math.round((x - WK.x0) / WK.d), 0, NX - 1);
const onAt = (x, z) => G.on[cellOf(x, z)];
const cellXZ = c => [WK.x0 + (c % NX) * WK.d, WK.z0 + Math.floor(c / NX) * WK.d];

// what she walks round: posts, near spruces, big pillows and poles (circles), the ropes (segments), the car (a box);
// she is a disc of BODY_R
const BODY_R = 0.22, ROPE_R = 0.03;
function collide(x, z) {
  // push the point out of everything it overlaps, a few rounds so corners settle
  for (let it = 0; it < 3; it++) {
    for (const [cx, cz, r] of WK.circles) {
      const dx = x - cx, dz = z - cz, d = Math.hypot(dx, dz), m = r + BODY_R;
      if (d < m && d > 1e-6) { x = cx + dx / d * m; z = cz + dz / d * m; }
    }
    for (const [ax, az, bx, bz] of WK.segs) {
      const ux = bx - ax, uz = bz - az, L2 = ux * ux + uz * uz || 1e-9;
      const t = clamp(((x - ax) * ux + (z - az) * uz) / L2, 0, 1);
      const px = ax + ux * t, pz = az + uz * t, dx = x - px, dz = z - pz, d = Math.hypot(dx, dz), m = BODY_R + ROPE_R;
      if (d < m && d > 1e-6) { x = px + dx / d * m; z = pz + dz / d * m; }
    }
    for (const [cx, cz, yaw, hl, hw] of WK.boxes) {
      const a = yaw * Math.PI / 180, ca = Math.cos(a), sa = Math.sin(a);
      const u = (x - cx) * ca + (z - cz) * sa, w = (x - cx) * sa - (z - cz) * ca;
      const pu = hl + BODY_R - Math.abs(u), pw = hw + BODY_R - Math.abs(w);
      if (pu > 0 && pw > 0) {
        const nu = pu < pw ? u + Math.sign(u) * pu : u, nw = pu < pw ? w : w + Math.sign(w) * pw;
        x = cx + nu * ca + nw * sa; z = cz + nu * sa - nw * ca;
      }
    }
  }
  return [x, z];
}
const blocked = (x, z) => { const [a, b] = collide(x, z); return Math.hypot(a - x, b - z) > 1e-4; };

// ---------------------------------------------------------------- view size: fill the screen, whole-number scale
// The painting is much wider than any screen and has spare sky above and a little ground below the composed frame.
// Pick the largest whole scale that shows the composed height, then show as many columns and rows as the screen
// holds: no bars on any side. The view opens on the composition's centre (the stair and the car) and then follows her.
const [SKYPAD, GPAD] = scene.pad;
let VW = WW, VHS = VH, SCALE = 2, TOPX = 0, ANCHOR = 0;
let frame, buf, bg, open, bgKey = '';     // open: 1 where only the sky shows (no ridge, tree or hill pixel over it)
const artc = document.createElement('canvas'), actx = artc.getContext('2d', { willReadFrequently: true });
function viewScale() {
  const dpr = window.devicePixelRatio || 1;
  const sw = Math.round(innerWidth * dpr), sh = Math.round(innerHeight * dpr);
  let s = Math.max(1, Math.floor(sh / VH));
  while (s > 1 && sw / s < 300) s--;
  if (s * WW < sw) s = Math.ceil(sw / WW);                             // wider than the painting: a size up
  return s;
}
function resize() {
  const dpr = window.devicePixelRatio || 1;
  const sw = Math.round(innerWidth * dpr), sh = Math.round(innerHeight * dpr);
  SCALE = viewScale();
  VW = Math.min(WW, Math.ceil(sw / SCALE));
  VHS = Math.min(WH, Math.ceil(sh / SCALE));
  const extra = VHS - VH;                                               // rows beyond the composed frame
  const below = extra >= 0 ? Math.min(GPAD, Math.floor(extra / 3)) : Math.ceil(extra * 0.25);
  TOPX = extra - below;                                                 // shown above the frame (more sky)
  ANCHOR = clamp(Math.round(scene.xc - VW / 2), 0, WW - VW);            // the composed view's left column
  view.x = clamp(view.x ?? ANCHOR, 0, WW - VW);
  view.cx = Math.round(view.x);
  canvas.width = VW; canvas.height = VHS;
  canvas.style.width = (VW * SCALE / dpr) + 'px'; canvas.style.height = (VHS * SCALE / dpr) + 'px';
  frame = ctx.createImageData(VW, VHS); buf = new Uint32Array(frame.data.buffer);
  bg = new Uint32Array(VW * VHS); open = new Uint8Array(VW * VHS); bgKey = '';
  artc.width = VW; artc.height = VHS;
  if (HDON) {
    hdc.width = VW * HS; hdc.height = VHS * HS;
    hdc.style.width = canvas.style.width; hdc.style.height = canvas.style.height;
  }
  snowBox();
}

// ---------------------------------------------------------------- the camera's follow
// The view keeps her inside a dead zone round its middle and eases after her when she leaves it; the hill (and the
// actors) sit at a whole art column, every layer behind it at its own whole column (fx of the hill's move, from where
// the composition opens), so the world is rigid between steps and nothing shimmers. It stops at the world's edges.
const view = { x: null, cx: 0 };
const DEAD_ZONE = 0.14;            // half the dead zone, as a share of the view's width
const FOLLOW = 2.4;                // how quickly the view eases after her (1/s)
function follow(dt, sx) {
  const dz = VW * DEAD_ZONE, mid = view.x + VW / 2;
  const target = clamp(sx < mid - dz ? sx + dz - VW / 2 : sx > mid + dz ? sx - dz - VW / 2 : view.x, 0, WW - VW);
  view.x += (target - view.x) * (1 - Math.exp(-dt * FOLLOW));
  if (Math.abs(target - view.x) < 0.05) view.x = target;
  // the whole column comes from hers less the (slowly changing) gap between her and the view, so while the view keeps
  // pace with her the two step on the same frame and she holds still on the screen
  const cx = clamp(Math.round(sx) - Math.round(sx - view.x), 0, WW - VW), moved = cx - view.cx;
  view.cx = cx;
  if (moved) shiftSnow(moved);
}
const layerX = (L, s = 1) => L === hill ? view.cx * s : Math.round((ANCHOR + L.fx * (view.cx - ANCHOR)) * s);

// ---------------------------------------------------------------- the walk
const FIG_H = WK.fig_h;            // her height (m)
const SPEED = 1.15;                // her walking speed on the flagstones, the trodden path and the road (m/s); in deep
                                   // snow and over the plough ridges a share of it (scene.walk.pace per surface)
const AUTO_SPEED = 0.8;            // the auto-walk's composed climb (m/s)
const STEP_LEN = 0.44;             // metres per footfall
const ACCEL = 6.0, AUTO_ACCEL = 3.0;   // how fast she reaches her pace (1/s)
const ROOM_MIN = 0.3;              // she keeps this much room: the walkable area's edge pushes back softly before it
const LOOK_AHEAD = 0.6;            // the auto-walk steers at the route this far ahead (m)
const PATH_AHEAD = 12;             // a walk-to steers at most this many cells down its path
const HEADING_SLACK = 8;           // degrees past an octant's edge before she turns to the next heading
const TILT = [1.8, 4.6];           // a composed still on the sky first, then one slow tilt down (s)
const WALK_FROM = 4.4;             // the auto-walk starts once the tilt has settled (s)
const tiltAt = t => Math.round(scene.crane[0] + (scene.crane[1] - scene.crane[0]) * smooth(TILT[0], TILT[1], t));
const [START_X, START_Z] = WK.start, [END_X, END_Z] = WK.end;
const me = { x: START_X, z: START_Z, vx: 0, vz: 0, heading: 0, auto: true, goal: null, ri: 0, phase: 0, t: 0, step: 0,
             breath: 1.2, hold: 0, beat: 0, h: 0, prints: [] };
let cy = scene.crane[0], T = 0;
const keys = new Set();

function frameAt(x, z) {
  // her screen-relative axes on the ground: up keeps her screen column (into the picture along the view's ray),
  // right is square to it
  const e = 0.05, dx = x * (ppm(z) / ppm(z + e) - 1), n = Math.hypot(dx, e);
  const ux = dx / n, uz = e / n;
  return { ux, uz, rx: uz, rz: -ux };
}

function wanted() {
  // the input as (right, up) in -1..1: keys, then the touch stick
  let r = 0, u = 0;
  if (keys.has('ArrowUp') || keys.has('KeyW')) u += 1;
  if (keys.has('ArrowDown') || keys.has('KeyS')) u -= 1;
  if (keys.has('ArrowRight') || keys.has('KeyD')) r += 1;
  if (keys.has('ArrowLeft') || keys.has('KeyA')) r -= 1;
  r += stick.r; u += stick.u;
  const m = Math.hypot(r, u);
  return m > 1 ? [r / m, u / m] : [r, u];
}

function steer() {
  // the velocity she wants (m/s): the player's input, the auto-walk up the route, or a walk-to along its path
  const pace = WK.pace[onAt(me.x, me.z)];
  const toward = (tx, tz, v) => { const dx = tx - me.x, dz = tz - me.z, d = Math.hypot(dx, dz) || 1; return [dx / d * v, dz / d * v]; };
  if (!me.auto) {
    const [r, u] = wanted(), f = frameAt(me.x, me.z);
    if (r || u) me.goal = null;
    if (!me.goal) return [(r * f.rx + u * f.ux) * SPEED * pace, (r * f.rz + u * f.uz) * SPEED * pace];
  }
  if (me.goal) {
    const d = Math.hypot(me.goal.x - me.x, me.goal.z - me.z);
    if (d < 0.12) { me.goal = null; return [0, 0]; }
    const [tx, tz] = pathAhead(me.goal);
    return toward(tx, tz, (me.auto ? AUTO_SPEED : SPEED) * pace * (smooth(0, 1.2, d) * 0.85 + 0.15));
  }
  if (T < WALK_FROM) return [0, 0];
  // the auto-walk: up the route, slowing into the stop by the car's nose
  while (me.ri < route.length - 1 && Math.hypot(route[me.ri + 1].x - me.x, route[me.ri + 1].z - me.z) <
         Math.hypot(route[me.ri].x - me.x, route[me.ri].z - me.z)) me.ri++;
  const left = route[route.length - 1].s - route[me.ri].s;
  const d = Math.hypot(END_X - me.x, END_Z - me.z);
  if (left < 0.05 && d < 0.05) return [0, 0];
  let k = me.ri; while (k < route.length - 1 && route[k].s < route[me.ri].s + LOOK_AHEAD) k++;
  return toward(route[k].x, route[k].z, AUTO_SPEED * (smooth(0, 1.4, d) * 0.85 + 0.15));
}

function move(dt) {
  const [tx, tz] = steer();
  const a = Math.min(1, dt * (me.auto ? AUTO_ACCEL : ACCEL));
  me.vx += (tx - me.vx) * a; me.vz += (tz - me.vz) * a;
  // the walkable area's soft edge: the part of the move that heads out fades as she nears it (she slides along)
  const r0 = roomAt(me.x, me.z), e = WK.d;
  let gx = roomAt(me.x + e, me.z) - roomAt(me.x - e, me.z), gz = roomAt(me.x, me.z + e) - roomAt(me.x, me.z - e);
  const gn = Math.hypot(gx, gz);
  let vx = me.vx, vz = me.vz;
  if (gn > 1e-6) {
    gx /= gn; gz /= gn;
    const out = -(vx * gx + vz * gz);
    if (out > 0) { const k = 1 - smooth(ROOM_MIN, 1, r0); vx += gx * out * k; vz += gz * out * k; }
  }
  let [nx, nz] = collide(me.x + vx * dt, me.z + vz * dt);
  if (roomAt(nx, nz) < ROOM_MIN && roomAt(nx, nz) < r0) [nx, nz] = [me.x, me.z];
  const moved = Math.hypot(nx - me.x, nz - me.z);
  me.x = nx; me.z = nz;
  return moved / Math.max(dt, 1e-6);
}

function turnTo(vx, vz) {
  // her heading (0 = away into the picture, clockwise in eighths) from her move in the screen-relative frame, with a
  // little slack at each octant's edge so she never flickers between two
  const f = frameAt(me.x, me.z);
  const ang = Math.atan2(vx * f.rx + vz * f.rz, vx * f.ux + vz * f.uz) * 180 / Math.PI;
  let off = ((ang - me.heading * 45) % 360 + 540) % 360 - 180;
  if (Math.abs(off) > 22.5 + HEADING_SLACK) me.heading = ((Math.round(ang / 45) % 8) + 8) % 8;
}

function step(dt) {
  T += dt; me.t += dt;
  const speed = move(dt);
  const moving = speed > 0.08;
  if (moving) {
    turnTo(me.vx, me.vz);
    const before = Math.floor(me.phase * 2);
    me.phase += dt * speed / STEP_LEN / 2;
    if (Math.floor(me.phase * 2) !== before) footfall();
  }
  // the stop beat: standing still by the car's nose, the glow behind her and the rim on her hood ease up with a warm
  // swell
  const still = !moving && Math.hypot(END_X - me.x, END_Z - me.z) < WK.hold_r;
  me.hold = still ? me.hold + dt : 0;
  me.beat = smooth(0.3, 2.8, me.hold);
  if (audio.on && audio.swell) audio.swell(me.beat);
  // breath: a puff every few seconds, quicker while walking
  me.breath -= dt;
  if (me.breath <= 0) { me.breath = (moving ? 2.5 : 3.6) * (0.85 + rnd(me.t) * 0.3); exhale(); audio.breath(moving ? 1 : 0.7); }
  exT -= dt; if (exT <= 0) { exT = 0.55 + rnd(T * 3.1) * 0.3; puffs.push({ x: scene.car.exhaust[0] - 1, y: scene.car.exhaust[1], age: 0, life: 2.6, vx: 2.5, vy: -2.2, kind: 1 }); }
  for (const q of puffs) { q.age += dt; q.x += q.vx * dt; q.y += q.vy * dt; q.vx *= (1 - dt * 0.5); }
  for (let i = puffs.length - 1; i >= 0; i--) if (puffs[i].age > puffs[i].life) puffs.splice(i, 1);
  // the opening: one establishing tilt down from the sky while she stands; the view then follows her sideways only
  cy = tiltAt(T);
  follow(dt, feet()[0]);
  stepSnow(dt);
  if (audio.on) audio.car(Math.hypot(me.x - scene.car.at[0], me.z - scene.car.at[1]));
}

const puffs = []; let exT = 0.3;
const feet = () => proj(me.x, heightAt(me.x, me.z), me.z);       // her feet on the screen (hill-world px)
const PRINT_HOLD = 60, PRINT_FADE = 300, PRINTS = 500;            // prints stay this long, are gone by PRINT_FADE (s)
function footfall() {
  // the foot that just landed: a step sound for what is underfoot, and in the snow a print beside her line
  me.step++;
  const on = onAt(me.x, me.z), f = frameAt(me.x, me.z), a = me.heading * Math.PI / 4;
  audio.step(me.step & 1, 0.8, on === WK.on.stone ? 'stone' : on === WK.on.road ? 'packed' : 'snow');
  if (on === WK.on.stone || on === WK.on.road) return;            // no prints on stone or the packed lane
  const side = (me.step & 1 ? 1 : -1) * 0.08;                     // the foot's offset to her right
  const rx = Math.cos(a) * f.rx - Math.sin(a) * f.ux, rz = Math.cos(a) * f.rz - Math.sin(a) * f.uz;
  me.prints.push({ x: me.x + rx * side, z: me.z + rz * side, t: T });
  if (me.prints.length > PRINTS) me.prints.shift();
}
function exhale() {
  // a soft puff at her mouth (beside her hood, downwind, when her back is to us); the breeze comes from the left
  const h = FIG_H * ppm(me.z) * hero(me.z), s = h / FIG_H, [x, y] = feet();
  const m = onHer(WS.mouth);
  puffs.push({ x: x + m.dx * s + (m.behind ? h * 0.2 : h * 0.05) + 2, y: y - h * 0.86, age: 0, life: 2.0, vx: 4.0,
               vy: -2.6, kind: 0, r: Math.max(2, h * 0.07) });
}
function onHer([r, f]) {
  // a point on her (right, forward in metres) turned to her heading: its screen offset (m) and whether her body is
  // between it and us
  const a = me.heading * Math.PI / 4;
  return { dx: r * Math.cos(a) + f * Math.sin(a), behind: -r * Math.sin(a) + f * Math.cos(a) > 0 };
}

// ---------------------------------------------------------------- walk to a spot (a click or a tap; Walk on)
// a distance field over the walk grid from the spot (diagonals cost more, deep snow costs more than the path) through
// every cell she fits in; she steers at the field's descent a few cells ahead of her
const CELL_X = new Float32Array(NC), CELL_Y = new Float32Array(NC), FREE = new Uint8Array(NC);
for (let c = 0; c < NC; c++) {
  const [x, z] = cellXZ(c), [sx, sy] = proj(x, G.h[c] / 100, z);
  CELL_X[c] = sx; CELL_Y[c] = sy;
  FREE[c] = G.room[c] / 255 >= ROOM_MIN && !blocked(x, z) ? 1 : 0;
}
function field(goal) {
  const dist = new Float64Array(NC).fill(Infinity), heap = [];
  const push = (c, d) => { heap.push([d, c]); let i = heap.length - 1; while (i) { const p = (i - 1) >> 1; if (heap[p][0] <= heap[i][0]) break; [heap[p], heap[i]] = [heap[i], heap[p]]; i = p; } };
  const pop = () => { const top = heap[0], last = heap.pop(); if (heap.length) { heap[0] = last; let i = 0; for (;;) { const l = 2 * i + 1, r = l + 1; let m = i; if (l < heap.length && heap[l][0] < heap[m][0]) m = l; if (r < heap.length && heap[r][0] < heap[m][0]) m = r; if (m === i) break; [heap[m], heap[i]] = [heap[i], heap[m]]; i = m; } } return top; };
  dist[goal] = 0; push(goal, 0);
  while (heap.length) {
    const [d, c] = pop(); if (d > dist[c]) continue;
    const i = c % NX, j = (c - i) / NX;
    for (let dj = -1; dj <= 1; dj++) for (let di = -1; di <= 1; di++) {
      const ii = i + di, jj = j + dj; if ((!di && !dj) || ii < 0 || jj < 0 || ii >= NX || jj >= NZ) continue;
      const n = jj * NX + ii; if (!FREE[n] || (di && dj && !(FREE[j * NX + ii] && FREE[jj * NX + i]))) continue;
      const nd = d + (di && dj ? 1.414 : 1) / WK.pace[G.on[n]];
      if (nd < dist[n]) { dist[n] = nd; push(n, nd); }
    }
  }
  return dist;
}
function walkTo(x, z, auto = false) {
  // send her to the free cell nearest (x, z)
  let best = cellOf(x, z);
  if (!FREE[best]) { let bd = Infinity; for (let c = 0; c < NC; c++) if (FREE[c]) { const [cx, cz] = cellXZ(c), d = Math.hypot(cx - x, cz - z); if (d < bd) { bd = d; best = c; } } }
  const [gx, gz] = cellXZ(best);
  me.goal = { x: gx, z: gz, dist: field(best) };
  me.auto = auto;
}
function pathAhead(goal) {
  // the furthest cell she can see down the field, up to PATH_AHEAD steps (the path pulled taut round corners); from a
  // cell the field never reached (pressed against a rope) the best reached cell beside it
  let c = -1, cd = Infinity;
  const i0 = Math.round((me.x - WK.x0) / WK.d), j0 = Math.round((me.z - WK.z0) / WK.d);
  for (let dj = -2; dj <= 2; dj++) for (let di = -2; di <= 2; di++) {
    const i = i0 + di, j = j0 + dj; if (i < 0 || j < 0 || i >= NX || j >= NZ) continue;
    const n = j * NX + i, d = goal.dist[n] + Math.hypot(di, dj); if (d < cd) { cd = d; c = n; }
  }
  if (c < 0) return [goal.x, goal.z];
  let aim = cellXZ(c);
  for (let k = 0; k < PATH_AHEAD && goal.dist[c] > 0; k++) {
    const i = c % NX, j = (c - i) / NX; let next = c;
    for (let dj = -1; dj <= 1; dj++) for (let di = -1; di <= 1; di++) {
      const ii = i + di, jj = j + dj; if (ii < 0 || jj < 0 || ii >= NX || jj >= NZ) continue;
      const n = jj * NX + ii; if (goal.dist[n] < goal.dist[next]) next = n;
    }
    if (next === c) break;
    c = next;
    const p = goal.dist[c] === 0 ? [goal.x, goal.z] : cellXZ(c);
    if (!clearTo(p[0], p[1])) break;
    aim = p;
  }
  return aim;
}
function clearTo(x, z) {
  // nothing she can't walk through on the straight line from her to (x, z) (her own first steps aside)
  const L = Math.hypot(x - me.x, z - me.z), n = Math.ceil(L / 0.08);
  for (let k = 2; k <= n; k++) { const t = k / n; if (!FREE[cellOf(me.x + (x - me.x) * t, me.z + (z - me.z) * t)]) return false; }
  return true;
}
function groundAt(wx, wy) {
  // the free cell drawn nearest a point of the painting (hill-world px), if one is near enough
  let best = -1, bd = 40 * 40;
  for (let c = 0; c < NC; c++) if (FREE[c]) { const d = (CELL_X[c] - wx) ** 2 + (CELL_Y[c] - wy) ** 2; if (d < bd) { bd = d; best = c; } }
  return best < 0 ? null : cellXZ(best);
}

// ---------------------------------------------------------------- compose
function composeBackground(oy) {
  const top = clamp(Math.round(oy) - TOPX, 0, WH - VHS);              // the window's top row on the canvas
  const offs = layers.map(l => [layerX(l), Math.round(top * l.f)]);
  const key = offs.join(';') + '|' + VW + '|' + VHS;
  if (key === bgKey) return offs;
  bgKey = key;
  // the art-size picture (the pixel look shows it; both looks read colours from it) and where only the sky shows
  actx.clearRect(0, 0, VW, VHS);
  layers.forEach((L, i) => { if (i) actx.drawImage(L.art.c, -offs[i][0], -offs[i][1]); });
  const fore = new Uint32Array(actx.getImageData(0, 0, VW, VHS).data.buffer);
  actx.globalCompositeOperation = 'destination-over';                   // the sky goes in behind
  actx.drawImage(layers[0].art.c, -offs[0][0], -offs[0][1]);
  actx.globalCompositeOperation = 'source-over';
  bg.set(new Uint32Array(actx.getImageData(0, 0, VW, VHS).data.buffer));
  for (let i = 0; i < bg.length; i++) open[i] = (fore[i] >>> 24) === 0 ? 1 : 0;
  if (HDON) {
    // the painted world at its own size: the hill moves with the actors' grid (HS x its art offset), the layers
    // behind it by whole screen pixels
    layers.forEach((L, i) => hctx.drawImage(L.hd.c, -layerX(L, HS), -(L === hill ? offs[i][1] * HS : Math.round(top * HS * L.f))));
  }
  return offs;
}

let OX = 0, OY = 0;      // the hill layer's column and row offsets this frame
function put(x, y, col, z) {
  // x, y in hill-world pixels; depth-tested against the hill when z is given
  const vx = x - OX, vy = y - OY;
  if (vx < 0 || vy < 0 || vx >= VW || vy >= VHS) return;
  if (z !== undefined && y >= 0 && y < WH) { const d = hill.depth[y * WW + x]; if (d !== 65535 && d / 100 < z) return; }
  buf[vy * VW + vx] = col;
}
function get(x, y) {
  const vx = x - OX, vy = y - OY; if (vx < 0 || vy < 0 || vx >= VW || vy >= VHS) return 0;
  const v = buf[vy * VW + vx];
  return HDON && (v >>> 24) === 0 ? bg[vy * VW + vx] : v;    // hd2d: the actors' canvas is clear where the world shows
}
function blend(i, col, a) {
  const b = buf[i];
  if (HDON && (b >>> 24) !== 255) {
    // over a clear (or part-clear) pixel of the actors' canvas: the colour with its alpha, composited by the browser
    const da = (b >>> 24) / 255, oa = a + da * (1 - a);
    const mix = sh => Math.round((((col >> sh) & 255) * a + ((b >> sh) & 255) * da * (1 - a)) / oa);
    buf[i] = ((Math.round(oa * 255) << 24) | (mix(16) << 16) | (mix(8) << 8) | mix(0)) >>> 0;
    return;
  }
  const r = ((b & 255) * (1 - a) + (col & 255) * a) | 0, g = (((b >> 8) & 255) * (1 - a) + ((col >> 8) & 255) * a) | 0,
        bl = (((b >> 16) & 255) * (1 - a) + ((col >> 16) & 255) * a) | 0;
  buf[i] = (255 << 24) | (bl << 16) | (g << 8) | r;
}

// ---------------------------------------------------------------- the walker
// her Blender-lit sprite at her height and heading (poses held 4 per step, the body bobbing 1 px on the passing pose),
// the pink scarf's tail streaming downwind and lagging the walk, a contact shadow, her prints in the snow, and at the
// hold the suitcase set down and the air behind her hood brightening
const FIG = { mint: hex('#a8c8a0'), scarf: hex('#d0607e'), scarfDk: hex('#a04468') };
let lastBob = 0, tailBob = 0;
const SHADOW_A = 0.85;             // her contact shadow's middle: this share of the way to the next darker tone

function shadeAt(x, y, a, z) {
  // the ground at (x, y) (hill-world px) a share a of the way to its next darker tone (scene.shade), unless something
  // nearer than z stands there (nothing where nothing is drawn)
  const vx = x - OX, vy = y - OY;
  if (vx < 0 || vy < 0 || vx >= VW || vy >= VHS || y >= WH) return;
  const d = hill.depth[y * WW + x]; if (d !== 65535 && d / 100 < z) return;
  const sd = SHADE.get(get(x, y)); if (sd === undefined) return;
  if (a >= 1) buf[vy * VW + vx] = sd; else blend(vy * VW + vx, sd, a);
}

function groundSlack(x, z) {
  // how much nearer than (x, z) the ground drawn in its pixel row may lie (m): the depth grid keeps each art pixel's
  // nearest depth, and a row spans more ground the flatter it is seen (toward the crest), so a mark on the ground
  // tests its depth with that much slack. Only ground colours shade (scene.shade), so a post or the car in front
  // never darkens; a nearer drift or stone is ground too
  const e = 0.25, rows = (proj(x, heightAt(x, z), z)[1] - proj(x, heightAt(x, z + e), z + e)[1]) / e;
  return clamp(0.6 + 3 / Math.max(rows, 0.5), 0.6, 3.0);
}

const PRINT_A = 0.7;               // a fresh print: this share of the way to the next darker tone (pressed, not dug)
function drawPrints() {
  // each print a soft step darker than the snow under it, 1-3 px by depth (a 3 px print lighter at its ends), fading
  // very slowly; on the ground, so under her and behind whatever stands nearer
  for (const p of me.prints) {
    const a = PRINT_A * (1 - smooth(PRINT_HOLD, PRINT_FADE, T - p.t)); if (a <= 0) continue;
    const [sx, sy] = proj(p.x, heightAt(p.x, p.z), p.z), w = clamp(Math.round(0.09 * ppm(p.z)), 1, 3);
    const x0 = Math.round(sx - w / 2), y = Math.round(sy);
    const zt = p.z - groundSlack(p.x, p.z);
    for (let i = 0; i < w; i++) shadeAt(x0 + i, y, w === 3 && i !== 1 ? a * 0.6 : a, zt);
  }
}

function drawWalker() {
  // her height follows the perspective (and the painter's hero scale) in single pixels with a little hysteresis, so
  // she never pops or flickers
  const want = FIG_H * ppm(me.z) * hero(me.z);
  if (!me.h || Math.abs(want - me.h) > 0.8) me.h = clamp(Math.round(want), WS.hmin, WS.hmax);
  const h = me.h, [fx, fy0] = feet(), x = Math.round(fx), fy = Math.round(fy0);
  const z = me.z - 0.35;
  const moving = Math.hypot(me.vx, me.vz) > 0.08;
  const pose = moving ? Math.floor(mod(me.phase * 2, 1) * 4) : -1;      // 0 contact L, 1 pass, 2 contact R, 3 pass
  const bob = pose === 1 || pose === 3 ? 1 : 0;
  if (bob !== lastBob) { tailBob = lastBob; lastBob = bob; }             // the scarf's tail follows a pose late
  const headH = Math.max(5, Math.round(h * 0.25)), hw = Math.max(5, Math.round(h * 0.3));
  const botW = Math.max(6, Math.round(h * 0.46));                     // her hem's width
  const hTop = fy - h - bob;
  // the stop beat: the air behind her hood brightens in two flat steps (behind her only, never over the painting's
  // nearer things), so the dark hood stands against light
  if (me.beat > 0.3) {
    const hcx = x + 0.5, hcy = hTop + headH * 0.55;
    for (let k = 0; k < (me.beat > 0.85 ? 2 : 1); k++) {
      const rx = (hw * (k ? 1.05 : 1.6)) + 2, ry = (headH * (k ? 0.95 : 1.4)) + 2;
      for (let yy = Math.floor(hcy - ry); yy <= Math.ceil(hcy + ry); yy++) for (let xx = Math.floor(hcx - rx); xx <= Math.ceil(hcx + rx); xx++) {
        const u = (xx + 0.5 - hcx) / rx, v = (yy + 0.5 - hcy) / ry;
        if (u * u + v * v > 1) continue;
        const vx = xx - OX, vy = yy - OY;
        if (vx < 0 || vy < 0 || vx >= VW || vy >= VHS) continue;
        const d = hill.depth[yy * WW + xx];
        if (d !== 65535 && d / 100 < z + 2) continue;
        blend(vy * VW + vx, FIG.mint, 0.16);
      }
    }
  }
  // contact shadow: the ground under her feet (and under the case once she sets it down) one tone darker
  const down = me.hold > 0.7;
  // a flat oval under her feet: the middle a full step darker, its ends and the row under it half a step (so it reads
  // as her weight in the snow, not a drawn bar); behind anything nearer than her
  const zs = me.z - groundSlack(me.x, me.z);
  const shadow = (xa, xb, yy, a = 1) => { for (let xx = xa; xx <= xb; xx++) shadeAt(xx, yy, xx === xa || xx === xb ? a * 0.5 : a, zs); };
  const sw = Math.max(2, Math.round(botW * 0.4));                    // half its width
  shadow(x - sw, x + sw, fy, SHADOW_A);
  if (h >= 30) shadow(x - sw + 2, x + sw - 2, fy + 1, SHADOW_A * 0.5);
  const s = h / FIG_H, knot = onHer(WS.knot);
  if (down) { const c = onHer([-0.42, 0.02]).dx; shadow(x + Math.round((c - 0.14) * s), x + Math.round((c + 0.14) * s), fy, SHADOW_A); }
  const lit = lampAt(me.x, me.z) > 0.5;                                // in the headlamps' light
  if (knot.behind) drawTail(x, fy, h, bob, knot, z);                    // her body hides the knot: the tail behind her
  drawSprite(x, fy, h, pose, bob, down, lit, z);
  if (!knot.behind) drawTail(x, fy, h, bob, knot, z);
  return { x, y: hTop, h };
}

function drawSprite(x, fy, h, pose, bob, down, lit, z) {
  // her sprite at this height and heading; a pass pose lifts the body (not the feet) one pixel
  const [y0, cw, ch, ax, ay] = WS.rows[h - WS.hmin];
  const col = ((me.heading * WS.poses.length + (pose >= 0 ? pose : (down ? 5 : 4))) * 2 + (lit ? 1 : 0));
  const s = h / FIG_H, cut = ay - Math.round(0.3 * s);              // rows above the knees ride the bob
  const ox = x - ax, oy = fy - 1 - ay;
  for (let j = 0; j < ch; j++) {
    const src = (y0 + j) * WS.w + col * cw;
    for (let i = 0; i < cw; i++) {
      const v = WS.px[src + i]; if ((v >>> 24) === 0) continue;
      if (j < cut) putHer(ox + i, oy + j - bob, v, z);
      else { putHer(ox + i, oy + j, v, z); if (j === cut && bob) putHer(ox + i, oy + j - 1, v, z); }
    }
  }
}

const SEE_THROUGH = [hex('#b4a8c4'), 0.32];   // her see-through silhouette behind something nearer: tone, alpha
function putHer(x, y, col, z) {
  // one pixel of her; where something nearer stands in front of her (a spruce, a post) a faint flat silhouette shows
  // through it instead, so she is never lost behind a tree
  const vx = x - OX, vy = y - OY;
  if (vx < 0 || vy < 0 || vx >= VW || vy >= VHS) return;
  const d = y >= 0 && y < WH ? hill.depth[y * WW + x] : 65535;
  if (d !== 65535 && d / 100 < z) blend(vy * VW + vx, SEE_THROUGH[0], SEE_THROUGH[1]);
  else buf[vy * VW + vx] = col;
}

function drawTail(x, fy, h, bob, knot, z) {
  // the scarf's tail streams downwind from the knot: 3-5 px, it follows the body's bob a pose late and its last two
  // pixels flutter on a held 4-step cycle
  const s = h / FIG_H, tail = clamp(Math.round(h * 0.16), 3, 5), fl = mod(Math.floor(me.t * 5), 4), lag = tailBob - bob;
  const ax = x + Math.round((knot.dx + 0.05) * s), ay = fy - Math.round(WS.knot[2] * s) - bob, sh = Math.max(2, Math.round(h * 0.07));
  for (let i = 0; i < tail; i++) {
    let dy = Math.floor(i * 0.45) + (i >= tail - 2 ? -lag : 0);
    if (i === tail - 1) dy += [0, -1, 0, 1][fl];
    if (i === tail - 2) dy += [0, 0, -1, 0][fl];
    put(ax + i, ay + dy, i === tail - 1 ? FIG.scarfDk : FIG.scarf, z);
    if (sh > 2 && i < tail - 2) put(ax + i, ay + dy + 1, FIG.scarfDk, z);
  }
}

// ---------------------------------------------------------------- snow
// Three depth classes of flakes in the air in front of the painting, in view pixels. Every flake falls at its class's
// terminal speed (faster the nearer and bigger it is), sways sideways on a slow sine of its own and drifts on a light
// steady wind to the right; when the view steps sideways the flakes shift against it, the near ones most. Leaving the
// bottom a flake comes back above the top edge at a new column; leaving a side it comes back off the other side: it
// never pops in or out mid-screen. At 30 frames a second every flake moves down at least one pixel a frame. Each
// flake is a hand-made pixel stamp: far ones 1-2 px specks, mid ones small irregular clusters, near ones broken,
// ragged clumps (a pale core, a mid tone, a snow-teal edge that reads on the sky, a crystal or two come loose) that
// tumble through four orientations in held steps. A few far flakes catch the sun's pink while high over open sky.
const STAMPS = {                              // '@' core, 'o' mid tone, '.' edge; listed small to big
  far: ['@', '@@', '@\n@'],
  mid: ['@o\n.@@', 'o@.\n.@@', ' @o\n@@.\n.o', '@.\no@@\n .o', ' o@\n.@@o\n @@.', '.o@\n@@@.\n .o'],
  near: [
    ' . @.\n.@@@o\n o@@@.\n.  o@.\n    .',
    '   .@\n .o@@. .\n.@@o@@\n .@@@o.\n  o. @\n     .',
    ' .     .\n  o@@.o\n .@@@@@.\no@@o@@\n .@@@o .\n   .o.',
    '  .\n .@@  .\no@@@o\n .@o@@.\n  @@@o\n . .o.\n    .',
    '      .@\n .o@. @o\n.@@@@@@.\n o@@o@@o\n  .@@. .\n   .',
    ' .@.\n @@@o\n  o@@@.  .\n   .@@@@o\n    o@@@.\n  .   .o',
  ],
};
const SNOW_TONE = { '@': hex('#bccec8'), 'o': hex('#9cb4b0'), '.': hex('#6f8c92') };
const FAR_TONE = hex('#8ea8a6'), MID_TONE = { '@': hex('#b0c6be'), 'o': hex('#a2bab4'), '.': hex('#7896a0') };
const GLINT = hex('#fc5084');                 // the sun's pink, on a far flake high over open sky
// per class: flakes per 10 000 view px, fall speed (px/s, the bigger stamps faster), sway (px) and its period (s),
// the wind (px/s), its share of a sideways view step, the tumble's step rate (orientations per second)
const SNOW = [
  { stamps: 'far', per: 6.0, fall: [31, 38], sway: [0.4, 1.2], period: [2.6, 4.6], wind: 4, par: 0.75 },
  { stamps: 'mid', per: 13.0, fall: [40, 54], sway: [0.7, 1.8], period: [2.2, 4.0], wind: 6, par: 0.9 },
  { stamps: 'near', per: 2.1, fall: [58, 80], sway: [1.0, 2.6], period: [1.8, 3.4], wind: 9, par: 1.2, tumble: [1.5, 3.5] },
];
const GLINTS = 12;                           // far flakes that may catch the pink
const SNOW_M = 14;                           // the snow box's margin round the view (px): more than a stamp and a sway
const SNOW_NEAR_FIG = [0.25, 0.7];           // near flakes fade over her: fully see-through within this x her height

function parseStamp(s, tones) {
  const rows = s.split('\n'), w = Math.max(...rows.map(r => r.length)), h = rows.length, px = [];
  rows.forEach((r, j) => [...r].forEach((c, i) => { if (c !== ' ') px.push([i, j, tones[c]]); }));
  // the four orientations it tumbles through, all in its own w x h box: as drawn, flipped, turned over, flipped back
  return [0, 1, 2, 3].map(o => px.map(([i, j, c]) => [o & 1 ? w - 1 - i : i, o & 2 ? h - 1 - j : j, c]))
    .map(v => ({ w, h, px: v }));
}
const STAMP = {
  far: STAMPS.far.map(s => parseStamp(s, { '@': FAR_TONE })),
  mid: STAMPS.mid.map(s => parseStamp(s, MID_TONE)),
  near: STAMPS.near.map(s => parseStamp(s, SNOW_TONE)),
};
let FLAKES = [], BOXW = 0, BOXH = 0, snowSeed = 1;
const srnd = () => rnd(snowSeed++ * 0.6180339);

function makeFlake(k, gl) {
  const C = SNOW[k], set = STAMP[C.stamps];
  const si = Math.floor(srnd() * set.length), size = si / Math.max(set.length - 1, 1);   // stamps are listed small first
  return { k, si, gl, x: srnd() * BOXW - SNOW_M, y: srnd() * BOXH - SNOW_M,
           v: lerp(C.fall, 0.6 * size + 0.4 * srnd()), a: lerp(C.sway, srnd()), w: 2 * Math.PI / lerp(C.period, srnd()),
           p: srnd() * 6.3, tr: C.tumble ? lerp(C.tumble, srnd()) : 0, tp: srnd() * 4 };
}
function snowBox() {
  // the box the flakes live in: the view and a margin; a new view size scatters a fresh fall (count by area)
  const w = VW + 2 * SNOW_M, h = VHS + 2 * SNOW_M;
  if (w === BOXW && h === BOXH) return;
  BOXW = w; BOXH = h; snowSeed = 1; FLAKES = [];
  SNOW.forEach((C, k) => {
    const n = Math.round(C.per * VW * VHS / 10000);
    for (let i = 0; i < n; i++) FLAKES.push(makeFlake(k, k === 0 && i < GLINTS));
  });
}
function wrapX(f) {
  // out at one side: back in off the other
  if (f.x > BOXW - SNOW_M) f.x -= BOXW;
  if (f.x < -SNOW_M) f.x += BOXW;
}
function stepSnow(dt) {
  for (const f of FLAKES) {
    f.y += f.v * dt;
    f.x += SNOW[f.k].wind * dt;
    if (f.y > BOXH - SNOW_M) {                          // out at the bottom: back in above the top, at a new column
      f.y -= BOXH;
      f.x = srnd() * BOXW - SNOW_M;
    }
    wrapX(f);
  }
}
function shiftSnow(dx) {
  // the view stepped dx art px sideways: the air shifts against it, nearer flakes further
  for (const f of FLAKES) { f.x -= dx * SNOW[f.k].par; wrapX(f); }
}
function skyAt(x, y) {
  // the flake and two rows under it over open sky: never on a spruce or a pole, where pink reads as a berry
  for (let j = 0; j < 3; j++) { const yy = y + j; if (x >= 0 && yy >= 0 && x < VW && yy < VHS && !open[yy * VW + x]) return false; }
  return true;
}
const drawn = [];                                         // where each flake was drawn last (for tests: __fp.flakes)
function drawSnow(fig) {
  drawn.length = 0;
  for (const f of FLAKES) {
    const st = STAMP[SNOW[f.k].stamps][f.si][f.tr ? mod(Math.floor(T * f.tr + f.tp), 4) : 0];
    const cx = Math.round(f.x + Math.sin(T * f.w + f.p) * f.a), cy_ = Math.round(f.y);
    const x0 = cx - (st.w >> 1), y0 = cy_ - (st.h >> 1);
    drawn.push([f.k, cx, cy_]);
    let a = 1;
    if (f.k === 2 && fig) {                               // see-through over her, fading smoothly with distance
      const d = Math.hypot(cx + OX - fig.x, cy_ + OY - (fig.y + fig.h * 0.5)) / fig.h;
      a = 0.35 + 0.65 * smooth(SNOW_NEAR_FIG[0], SNOW_NEAR_FIG[1], d);
    }
    const pink = f.gl && cy_ < VHS * 0.38 && skyAt(cx, cy_);
    for (const [i, j, c] of st.px) {
      const xx = x0 + i, yy = y0 + j;
      if (xx < 0 || yy < 0 || xx >= VW || yy >= VHS) continue;
      if (a < 1) blend(yy * VW + xx, c, a); else buf[yy * VW + xx] = pink ? GLINT : c;
    }
  }
}

function drawPuffs() {
  // breath and exhaust: soft two-tone puffs that swell, then thin and shrink away; whole pixels, never a glyph
  const BR = [hex('#b0c4ba'), hex('#90afa3')], EX = [hex('#8e8a98'), hex('#76869a')];
  for (const q of puffs) {
    const t = q.age / q.life;
    const k = Math.min(4, Math.floor(t * 5));
    const r = q.kind ? [2, 2, 3, 3, 2][k] : Math.max(1, Math.round(q.r * [0.8, 1.15, 1.35, 1.2, 0.8][k]));
    const tones = q.kind ? EX : BR;
    const x = Math.round(q.x), y = Math.round(q.y);
    for (let dy = -r; dy <= r; dy++) for (let dx = -r; dx <= r; dx++) {
      const d = dx * dx + dy * dy;
      if (d > r * r + 1.2) continue;
      const vx = x + dx - OX, vy = y + dy - OY;
      if (vx < 0 || vy < 0 || vx >= VW || vy >= VHS) continue;
      const inner = d <= (r - 1) * (r - 1) + 1.2 && dy <= 0 && k < 3;          // the lit core, gone as it thins
      buf[vy * VW + vx] = inner ? tones[0] : tones[1];
    }
  }
}

function render() {
  const offs = composeBackground(cy);
  [OX, OY] = offs[offs.length - 1];
  if (HDON) buf.fill(0); else buf.set(bg);
  drawPrints();
  const fig = drawWalker();
  drawPuffs();
  if (!Q.has('nofx')) drawSnow(fig);
  ctx.putImageData(frame, 0, 0);
}

// ---------------------------------------------------------------- input
// keys (screen-relative: up walks into the picture), the touch stick under the left thumb, a click or a tap walks her
// to the spot; R or Walk on sends her up to the car
const COARSE = matchMedia('(pointer: coarse)').matches;
const stickEl = document.getElementById('stick'), knobEl = document.getElementById('knob');
const STICK_R = 48;                // the knob's travel (css px)
const stick = { id: null, start: null, r: 0, u: 0 };
const tap = { id: null, x: 0, y: 0 };
function showStick() { if (stickEl && !Q.has('shot')) stickEl.hidden = false; }
if (COARSE || Q.has('stick')) showStick();
function setHint(t) { const h = document.getElementById('hint'); h.textContent = t; h.classList.remove('gone'); clearTimeout(setHint.k); setHint.k = setTimeout(() => h.classList.add('gone'), 6000); }
function takeOver() {
  if (!me.auto) return;
  me.auto = false; me.goal = null;
  document.getElementById('auto').hidden = false;
  if (T < TILT[1]) T = TILT[1];                                         // a control during the opening ends the tilt
}
function stickStart(e, float) {
  stick.id = e.pointerId;
  if (float) {                 // a touch on the left side brings the stick under the thumb
    const r = stickEl.getBoundingClientRect();
    stickEl.style.left = (e.clientX - r.width / 2) + 'px'; stickEl.style.top = (e.clientY - r.height / 2) + 'px';
    stickEl.style.bottom = 'auto';
    stick.start = [e.clientX, e.clientY];
  } else {
    const r = stickEl.getBoundingClientRect();
    stick.start = [r.left + r.width / 2, r.top + r.height / 2];
  }
  stickEl.classList.add('active');
  stickMove(e);
  takeOver();
}
function stickMove(e) {
  let dx = e.clientX - stick.start[0], dy = e.clientY - stick.start[1];
  const d = Math.hypot(dx, dy);
  if (d > STICK_R) { dx *= STICK_R / d; dy *= STICK_R / d; }
  knobEl.style.transform = 'translate(' + dx + 'px, ' + dy + 'px)';
  const m = Math.min(d, STICK_R) / STICK_R;
  const k = m < 0.15 ? 0 : (m - 0.15) / 0.85 / m;          // past the dead zone, speed grows with the push
  stick.r = dx / STICK_R * k; stick.u = -dy / STICK_R * k;
}
function stickEnd() {
  stick.id = null; stick.r = stick.u = 0;
  if (!stickEl) return;
  knobEl.style.transform = ''; stickEl.classList.remove('active');
  stickEl.style.left = stickEl.style.top = stickEl.style.bottom = '';
}
stickEl.addEventListener('pointerdown', e => {
  e.preventDefault();
  if (stick.id !== null) return;
  try { stickEl.setPointerCapture(e.pointerId); } catch (_) { /* ignore */ }
  stickStart(e, false);
});
function walkToScreen(cx, cy_) {
  // a point on the screen -> the ground drawn there -> walk to it
  const r = canvas.getBoundingClientRect();
  const g = groundAt(OX + (cx - r.left) / r.width * VW, OY + (cy_ - r.top) / r.height * VHS);
  if (!g) return;
  takeOver(); walkTo(g[0], g[1]);
}
canvas.addEventListener('pointerdown', e => {
  canvas.focus();
  if (e.pointerType === 'touch') {
    showStick();
    if (e.clientX < innerWidth * 0.45 && stick.id === null) { stickStart(e, true); return; }
  }
  tap.id = e.pointerId; tap.x = e.clientX; tap.y = e.clientY;
});
addEventListener('pointermove', e => { if (e.pointerId === stick.id) stickMove(e); });
function pointerEnd(e) {
  if (e.pointerId === stick.id) stickEnd();
  if (e.pointerId === tap.id) {
    tap.id = null;
    if (e.type === 'pointerup' && Math.hypot(e.clientX - tap.x, e.clientY - tap.y) < 12) walkToScreen(e.clientX, e.clientY);
  }
}
addEventListener('pointerup', pointerEnd);
addEventListener('pointercancel', pointerEnd);
const MOVE_KEYS = ['ArrowUp', 'ArrowDown', 'ArrowLeft', 'ArrowRight', 'KeyW', 'KeyA', 'KeyS', 'KeyD'];
addEventListener('keydown', e => {
  if (e.ctrlKey || e.metaKey || e.altKey) return;          // leave browser shortcuts alone
  if (MOVE_KEYS.includes(e.code)) { keys.add(e.code); takeOver(); e.preventDefault(); }
  if (e.repeat) return;
  if (e.code === 'KeyR') resume();
  if (e.code === 'KeyM') toggleSound();
  if (e.code === 'KeyL') nextLook();
});
addEventListener('keyup', e => keys.delete(e.code));
function releaseAll() { keys.clear(); stickEnd(); tap.id = null; }
addEventListener('blur', releaseAll);
function resume() {
  // walk on by herself: up the route from the opening, from anywhere else along the shortest way to the car
  const onRoute = me.ri === 0 && Math.hypot(me.x - START_X, me.z - START_Z) < 0.05;
  if (onRoute) { me.auto = true; me.goal = null; } else walkTo(END_X, END_Z, true);
  if (T < TILT[1]) T = TILT[1];
  document.getElementById('auto').hidden = true;
}
function toggleSound() { const on = audio.toggle(); const b = document.getElementById('sound'); b.textContent = 'Sound: ' + (on ? 'on' : 'off'); b.setAttribute('aria-pressed', String(on)); }
document.getElementById('auto').addEventListener('click', () => { resume(); canvas.focus(); });
document.getElementById('sound').addEventListener('click', () => { toggleSound(); canvas.focus(); });
// the Look button (or L) switches painted <-> pixel; each is its own page load, the walk carried over: in the URL's
// query (?look=, served or from file://), else (a page whose URL holds no query: a sandboxed or srcdoc frame) in
// sessionStorage, or window.name where storage is blocked, read back at the top
const LOOK_NOW = HDON ? 'hd2d' : 'pixel';
function nextLook() {
  const carry = { look: HDON ? 'pixel' : 'hd2d' };
  if (me.auto && !me.goal && T > 0.5) carry.t = T.toFixed(1);
  else if (!me.auto) carry.at = [me.x, me.z, me.heading].map(v => +v.toFixed(2)).join(',');
  if (/^(https?|file):$/.test(location.protocol)) {
    try {
      const u = new URL(location.href);
      for (const k of ['look', 't', 'at']) u.searchParams.delete(k);
      for (const [k, v] of Object.entries(carry)) u.searchParams.set(k, v);
      location.replace(u.href);
      return;
    } catch (e) { /* fall through */ }
  }
  const s = JSON.stringify(carry);
  try { sessionStorage.setItem('fp.look', s); } catch (e) { window.name = 'fp.look:' + s; }
  location.reload();
}
{ const b = document.getElementById('look'); b.textContent = 'Look: ' + (HDON ? 'painted' : 'pixel'); b.hidden = false; b.addEventListener('click', () => { nextLook(); }); }
document.addEventListener('visibilitychange', () => { if (document.hidden) releaseAll(); audio.visible(!document.hidden); });

// ---------------------------------------------------------------- run
addEventListener('resize', resize); resize();
const t0 = parseFloat(Q.get('t') || '0');
if (Q.has('at')) {                 // ?at=X,Z[,HEADING]: start there, the player's (the Look button carries it)
  const [x, z, hd] = Q.get('at').split(',').map(Number);
  me.x = x; me.z = z; me.heading = hd || 0; T = TILT[1]; takeOver();
  view.x = clamp(feet()[0] - VW / 2, 0, WW - VW);
  view.cx = Math.round(view.x);    // the drawn column too, and the settled tilt: a paused still (and the first
  cy = tiltAt(T);                   // frame) shows her, not the opening's view of the sky over the anchor
}
if (t0 > 0) { const n = Math.round(t0 * 30); for (let i = 0; i < n; i++) step(1 / 30); }
document.getElementById('loading').hidden = true;
if (COARSE) setHint('Left thumb: walk · tap a spot to walk there · Walk on climbs to the car');
setTimeout(() => document.getElementById('hint').classList.add('gone'), 6000);
render();
const PAUSE = Q.has('pause');
let last = performance.now();
function loop(now) {
  const dt = Math.min(0.05, (now - last) / 1000); last = now;
  if (!PAUSE) { step(dt); render(); }
  requestAnimationFrame(loop);
}
requestAnimationFrame(loop);
window.__fp = { ready: true, me, step, render, scene, cy: () => cy, look: LOOK_NOW, hs: HS, flakes: () => drawn.slice(),
                view: () => [view.cx, OY], walkTo, proj, feet, offsets: () => layers.map(l => layerX(l)) };

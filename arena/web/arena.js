// The arena's map viewer (every map: Hushfall Crossing, Emberleaf Hollow ...). A painted map (arena/paint.py,
// arena/layers.py) to put your own units on. Canvas 2D, no libraries. The picture is layers (sky < far clouds < the
// map < corner towers < cloud sea < the ledge's front; a map ships the ones it has), composed at the map's own pixel size into a scene buffer only when something in it moves by a
// whole pixel (the clouds drift, the camera pans with parallax, a sway frame comes up), then scaled up whole (1x, 2x)
// or fitted to the screen. Every frame draws that one scene, then the lights, fires, banners and the snowfall.
// The level (level.json) is queried through ArenaLevel (web/level.js, the same code as arena/game.py).
// Overlays for a game dev: the walk grid, the zones, a scale reference, the colliders per level, the nav with its
// clearance and links, line of sight from the cursor, A* paths from both spawns, and a test agent you click to move.
// window.ARENA_ASSETS = {main, sky, sway, occ, zones, and far, sea, corner, cap when the map has them} (data: URIs),
// ARENA_DATA = {level, occ, layers, pal, map}: map = the biome's viewer settings (title, particles, ambience, people).
'use strict';
(() => {
const D = window.ARENA_DATA;
const L = D.level, PAL = D.pal, OCC = D.occ, LY = D.layers, MAPD = D.map || {};
const LV = window.ArenaLevel.load(L);
const Q = new URLSearchParams(location.search);
const SHOT = Q.has('shot');
const PR = L.projection;
const PPM = PR.ppm, SE = PR.sin_el, CE = PR.cos_el, X0 = PR.x0, Y0 = PR.y0;
const MAPW = PR.map_w, MAPH = PR.map_h;
const PI = Math.PI, TAU = PI * 2;

// ---------------------------------------------------------------- seeded randomness (stills repeat)
let seed = +(Q.get('seed') || 7);
function rnd() { seed = (seed * 1664525 + 1013904223) >>> 0; return seed / 4294967296; }
const rr = (a, b) => a + (b - a) * rnd();

// ---------------------------------------------------------------- the place
const proj = (u, v, z = 0) => [X0 + u * PPM, Y0 - (v * SE + z * CE) * PPM];
const depthOf = (u, v, z = 0) => v * CE - z * SE;
const G = L.grid;
const GK = new Uint8Array(G.nu * G.nv);
G.kind.forEach((row, i) => { for (let j = 0; j < G.nu; j++) GK[i * G.nu + j] = row.charCodeAt(j) - 48; });
const DK = L.nav.deck, HAS_DECK = DK.half_width > 0;
const heightAt = (u, v) => LV.hfZ(u, v);
const deckZ = v => LV.deckZ(v);
const SURF = MAPD.surfaces || ['', 'snow', 'trodden lane', 'drift', 'deck'];
const LEVEL = MAPD.levels || ['ground', 'terrace', 'deck'];
function unproj(sx, sy) {        // a map pixel -> [u, v, z, layer]: on the deck when it lands there, else the height field
  const u = (sx - X0) / PPM;
  let z = DK.z1, v = 0;
  for (let i = 0; i < 4; i++) { v = ((Y0 - sy) / PPM - z * CE) / SE; z = deckZ(v); }
  if (LV.inDeck(u, v) && LV.clear[1][LV.cellOf(u, v)] > 0) return [u, v, z, 1];
  z = 0;
  for (let i = 0; i < 8; i++) { v = ((Y0 - sy) / PPM - z * CE) / SE; z = heightAt(u, v); }
  return [u, v, z, 0];
}

// ---------------------------------------------------------------- images
const IMG = {};
function loadImages(cb) {
  const list = Object.entries(window.ARENA_ASSETS);
  let n = list.length;
  for (const [k, src] of list) {
    const im = new Image();
    im.onload = () => { IMG[k] = im; if (--n === 0) cb(); };
    im.onerror = () => { console.error('arena: image failed', k); };
    im.src = src;
  }
}
function mapCanvas(w = MAPW, h = MAPH) { const c = document.createElement('canvas'); c.width = w; c.height = h; return c; }

// ---------------------------------------------------------------- the sway: held frames as tiles over main.png
// layers.json sway: frame f = main.png with atlas tile i at (tx, ty) * tile for every [tx, ty, i] of frames[f]
const SW = LY.sway;

// ---------------------------------------------------------------- overlays, drawn once at map size
const ZCOL = { 1: [90, 200, 120], 2: [250, 70, 140], 3: [240, 170, 60], 4: [90, 140, 230], 5: [170, 110, 230], 6: [200, 200, 210] };
const ZNAME = { 1: 'playfield', 2: 'focus', 3: 'frame', 4: 'backdrop', 5: 'vista', 6: 'sky' };
const OV = {};
function buildZones() {
  const c = mapCanvas(), g = c.getContext('2d');
  g.drawImage(IMG.zones, 0, 0);
  const id = g.getImageData(0, 0, MAPW, MAPH), p = id.data;
  for (let i = 0; i < p.length; i += 4) {
    const col = ZCOL[p[i]];
    if (col) { p[i] = col[0]; p[i + 1] = col[1]; p[i + 2] = col[2]; p[i + 3] = 120; } else p[i + 3] = 0;
  }
  g.putImageData(id, 0, 0);
  OV.zones = c;
}
function poly(g, pts) { g.beginPath(); g.moveTo(pts[0][0], pts[0][1]); for (const q of pts.slice(1)) g.lineTo(q[0], q[1]); g.closePath(); }
function quad(g, u, v, c, z) { poly(g, [[u, v], [u + c, v], [u + c, v + c], [u, v + c]].map(([a, b]) => proj(a, b, z))); }
function buildGrid() {        // the legacy 0.5 m walk grid (level.json grid), with spawns, objectives, chokepoints
  const c = mapCanvas(), g = c.getContext('2d');
  for (let i = 0; i < G.nv; i++) for (let j = 0; j < G.nu; j++) {
    const k = GK[i * G.nu + j], u = G.u0 + j * G.cell, v = G.v0 + i * G.cell, z = G.height_cm[i][j] / 100;
    if (k === 0) {
      let edge = false;
      for (const [di, dj] of [[1, 0], [-1, 0], [0, 1], [0, -1]]) {
        const ii = i + di, jj = j + dj;
        if (ii >= 0 && jj >= 0 && ii < G.nv && jj < G.nu && GK[ii * G.nu + jj] > 0) edge = true;
      }
      if (!edge) continue;
      g.fillStyle = 'rgba(235, 70, 70, 0.42)';
    } else if (z > L.rules.high_ground_z) g.fillStyle = k === 2 ? 'rgba(255, 190, 80, 0.42)' : 'rgba(255, 210, 120, 0.26)';
    else g.fillStyle = k === 2 ? 'rgba(90, 170, 255, 0.3)' : 'rgba(255, 255, 255, 0.12)';
    quad(g, u + 0.02, v + 0.02, G.cell - 0.04, z); g.fill();
  }
  if (HAS_DECK) {
    g.fillStyle = 'rgba(120, 255, 200, 0.32)'; g.strokeStyle = 'rgba(120, 255, 200, 0.95)'; g.lineWidth = 2;
    const w = DK.half_width;
    poly(g, [[-w, DK.v0], [w, DK.v0], [w, DK.v1], [-w, DK.v1]].map(([u, v]) => proj(u, v, deckZ(v)))); g.fill(); g.stroke();
  }
  OV.grid = c;
}
function buildMetres() {
  const c = mapCanvas(), g = c.getContext('2d');
  g.lineWidth = 1;
  for (let i = 0; i < G.nv; i++) for (let j = 0; j < G.nu; j++) {
    if (!GK[i * G.nu + j]) continue;
    const u = G.u0 + j * G.cell, v = G.v0 + i * G.cell, z = G.height_cm[i][j] / 100;
    if (Math.abs(u - Math.round(u)) < 1e-6) {
      g.strokeStyle = Math.round(u) % 5 === 0 ? 'rgba(255,255,255,0.5)' : 'rgba(255,255,255,0.2)';
      const a = proj(u, v, z), b = proj(u, v + G.cell, z); g.beginPath(); g.moveTo(a[0], a[1]); g.lineTo(b[0], b[1]); g.stroke();
    }
    if (Math.abs(v - Math.round(v)) < 1e-6) {
      g.strokeStyle = Math.round(v) % 5 === 0 ? 'rgba(255,255,255,0.5)' : 'rgba(255,255,255,0.2)';
      const a = proj(u, v, z), b = proj(u + G.cell, v, z); g.beginPath(); g.moveTo(a[0], a[1]); g.lineTo(b[0], b[1]); g.stroke();
    }
  }
  OV.metres = c;
}

// the colliders: footprints at their floor, a prism up to 2.2 m (what touches a unit), coloured by level;
// filled = blocks sight, dashed = movement only. Walls red, lips blue, bounds white
const LCOL = ['79, 209, 255', '255, 184, 77', '125, 255, 176'];
function outline(s) {
  if (s.shape === 'circle') { const o = []; for (let k = 0; k < 16; k++) { const a = k / 16 * TAU; o.push([s.u + s.r * Math.cos(a), s.v + s.r * Math.sin(a)]); } return o; }
  if (s.shape === 'box') {
    const c = Math.cos(s.a), sn = Math.sin(s.a);
    return [[-1, -1], [1, -1], [1, 1], [-1, 1]].map(([x, y]) => [s.u + c * x * s.hu - sn * y * s.hv, s.v + sn * x * s.hu + c * y * s.hv]);
  }
  const eu = s.u1 - s.u0, ev = s.v1 - s.v0, n = Math.hypot(eu, ev) || 1, nu = -ev / n * s.t, nv = eu / n * s.t;
  return [[s.u0 + nu, s.v0 + nv], [s.u1 + nu, s.v1 + nv], [s.u1 - nu, s.v1 - nv], [s.u0 - nu, s.v0 - nv]];
}
function centreOf(s) { return s.shape === 'seg' ? [(s.u0 + s.u1) / 2, (s.v0 + s.v1) / 2] : [s.u, s.v]; }
function floorOf(s) {
  const [u, v] = centreOf(s);
  if (s.kind === 'wall') return s.z0 + 0.3;
  if (s.kind === 'lip') return s.z1 - 1.0;
  if (s.kind === 'bound') return s.z0 + 0.5;
  if (s.kind === 'deck' || s.kind === 'corbel') return s.z0;
  if (s.level === 2) return deckZ(v);
  return heightAt(u, v);
}
let collLevel = Q.get('level') === null ? 'all' : (Q.get('level') === 'all' ? 'all' : +Q.get('level'));
function buildColliders() {
  const c = mapCanvas(), g = c.getContext('2d');
  const list = LV.shapes.filter(s => collLevel === 'all' || s.level === collLevel)
    .map(s => ({ s, f: floorOf(s), d: depthOf(...centreOf(s), floorOf(s)) })).sort((a, b) => b.d - a.d);
  for (const { s, f } of list) {
    const top = Math.min(s.z1, f + 2.2);
    if (s.kind === 'wall' || s.kind === 'lip' || s.kind === 'bound') {
      const a0 = proj(s.u0, s.v0, f), a1 = proj(s.u1, s.v1, f);
      g.setLineDash(s.kind === 'wall' ? [] : s.kind === 'lip' ? [5, 3] : [2, 3]);
      g.strokeStyle = s.kind === 'wall' ? 'rgba(255, 70, 70, 0.95)' : s.kind === 'lip' ? 'rgba(90, 190, 255, 0.95)' : 'rgba(255,255,255,0.8)';
      g.lineWidth = 2; g.beginPath(); g.moveTo(a0[0], a0[1]); g.lineTo(a1[0], a1[1]); g.stroke();
      if (s.kind === 'wall') {
        const b0 = proj(s.u0, s.v0, top), b1 = proj(s.u1, s.v1, top);
        g.fillStyle = 'rgba(255, 70, 70, 0.16)'; poly(g, [a0, a1, b1, b0]); g.fill();
      }
      continue;
    }
    const col = LCOL[s.level] || LCOL[0], o = outline(s);
    const bot = o.map(([u, v]) => proj(u, v, Math.max(f, s.z0))), tp = o.map(([u, v]) => proj(u, v, Math.max(top, Math.max(f, s.z0) + 0.05)));
    g.setLineDash(s.sight ? [] : [4, 3]);
    g.fillStyle = `rgba(${col}, ${s.sight ? 0.3 : 0.12})`; g.strokeStyle = `rgba(${col}, 0.95)`; g.lineWidth = 1.5;
    poly(g, bot); g.fill(); g.stroke();
    // the prism: the top ring and the silhouette's sides
    poly(g, tp); g.stroke();
    let li = 0, ri = 0;
    bot.forEach((p, i) => { if (p[0] < bot[li][0]) li = i; if (p[0] > bot[ri][0]) ri = i; });
    for (const i of [li, ri]) { g.beginPath(); g.moveTo(bot[i][0], bot[i][1]); g.lineTo(tp[i][0], tp[i][1]); g.stroke(); }
  }
  g.setLineDash([]);
  OV.colliders = c;
}

// the nav: every walkable 0.25 m cell by its clearance (red < 0.3 < orange < 0.5 < yellow < 0.8 < green), cells too
// tight for the chosen radius dimmed; the links: ramps' entry (foot) and exit (top) edges, the deck's two ends
const RADII = L.rules.radii;
let radius = +(Q.get('r') || 0.5);
function clearCol(c) { return c >= 0.8 ? '110, 220, 120' : c >= 0.5 ? '230, 220, 90' : c >= 0.3 ? '245, 150, 60' : '235, 70, 70'; }
function buildNav() {
  const c = mapCanvas(), g = c.getContext('2d'), cell = LV.cell;
  for (const layer of [0, 1]) {
    const cl = LV.clear[layer];
    for (let k = 0; k < LV.N; k++) {
      if (cl[k] <= 0) continue;
      const [u, v] = LV.centre(k), z = layer ? deckZ(v) : LV.z[k];
      g.fillStyle = `rgba(${clearCol(cl[k])}, ${cl[k] >= radius ? 0.42 : 0.16})`;
      quad(g, u - cell / 2 + 0.015, v - cell / 2 + 0.015, cell - 0.03, z); g.fill();
    }
  }
  g.lineWidth = 3;
  for (const lk of L.nav.links) {
    const seg = (pts, col, z) => { const a = proj(pts[0][0], pts[0][1], z(pts[0])), b = proj(pts[1][0], pts[1][1], z(pts[1])); g.strokeStyle = col; g.beginPath(); g.moveTo(a[0], a[1]); g.lineTo(b[0], b[1]); g.stroke(); };
    if (lk.kind === 'ramp') {
      seg(lk.entry, 'rgba(90, 220, 255, 1)', p => heightAt(p[0], p[1]));
      seg(lk.exit, 'rgba(255, 200, 80, 1)', p => heightAt(p[0], p[1]));
      g.setLineDash([4, 4]); seg(lk.switch, 'rgba(255,255,255,0.8)', p => heightAt(p[0], p[1])); g.setLineDash([]);
    } else seg(lk.edge, 'rgba(120, 255, 210, 1)', p => deckZ(p[1]));
  }
  OV.nav = c;
}

// LOS from a point: every walkable spot (0.5 m apart) shaded seen (green) or hidden (red), eye to eye
let losFrom = null, losKey = '';
function buildLos(from, step = 2) {
  const c = OV.los || mapCanvas(), g = c.getContext('2d'), cell = LV.cell;
  g.clearRect(0, 0, MAPW, MAPH);
  for (const layer of [0, 1]) {
    const cl = LV.clear[layer];
    for (let i = 0; i < LV.nv; i += step) for (let j = 0; j < LV.nu; j += step) {
      const k = i * LV.nu + j;
      if (cl[k] < 0.3) continue;
      const [u, v] = LV.centre(k), z = layer ? deckZ(v) : LV.z[k];
      const vis = LV.los(from, [u, v, layer]);
      g.fillStyle = vis ? 'rgba(120, 255, 150, 0.40)' : 'rgba(40, 10, 40, 0.42)';
      quad(g, u - cell / 2, v - cell / 2, cell * step, z); g.fill();
    }
  }
  const [x, y] = proj(from[0], from[1], LV.floorZ(from[0], from[1], from[2]) + LV.eye);
  g.fillStyle = '#ffffff'; g.beginPath(); g.arc(x, y, 5, 0, TAU); g.fill();
  g.strokeStyle = '#141a30'; g.lineWidth = 2; g.stroke();
  OV.los = c;
}

// paths from both spawns: Dijkstra fields per radius, paths out of them to the cursor and to every objective
const fields = {};
function spawnFields(r) {
  if (!fields[r]) {
    fields[r] = {};
    for (const side of ['west', 'east']) { const o = L.zones.spawns[side].origin; fields[r][side] = LV.field([LV.snap(o[0], o[1], 0, r)], r); }
  }
  return fields[r];
}
const SIDECOL = { west: '#5fd4ff', east: '#ff8ac0' };
function pathTo(side, b) {
  const o = L.zones.spawns[side].origin;
  return LV.pathFrom(spawnFields(radius)[side], b, radius, [o[0], o[1], 0]);
}
// to an objective: into its capture circle (on its level), where the field from that spawn is lowest (as arena/check.py)
function pathToCircle(side, ob) {
  const f = spawnFields(radius)[side], rr_ = ob.capture_r;
  let best = -1, bd = Infinity;
  for (let i = Math.floor((ob.v - rr_ - LV.v0) / LV.cell); i <= Math.floor((ob.v + rr_ - LV.v0) / LV.cell); i++)
    for (let j = Math.floor((ob.u - rr_ - LV.u0) / LV.cell); j <= Math.floor((ob.u + rr_ - LV.u0) / LV.cell); j++) {
      if (i < 0 || j < 0 || i >= LV.nv || j >= LV.nu) continue;
      const k = i * LV.nu + j, [u, v] = LV.centre(k);
      if ((u - ob.u) ** 2 + (v - ob.v) ** 2 > rr_ * rr_ || LV.levelOf(u, v, 0) !== ob.level) continue;
      if (f[k] < bd) { best = k; bd = f[k]; }
    }
  if (best < 0 || !isFinite(bd)) return null;
  const o = L.zones.spawns[side].origin, nodes = LV.descend(f, best, radius);
  if (!nodes) return null;
  const points = LV.smooth(nodes, radius, [o[0], o[1], 0], null);
  return { points, length: LV.constructor.length(points) };
}
let objRoutes = null;
function routesToObjectives() {
  objRoutes = [];
  for (const ob of L.zones.objectives.concat(L.zones.targets || [])) {   // a kill map: its fairness targets
    if (ob.kind === 'tower') continue;
    for (const side of ['west', 'east']) {
      if (ob.side === side) continue;                       // the Stones from both, each side to the other's heart
      const p = pathToCircle(side, ob);
      if (p) objRoutes.push({ side, ob, p });
    }
  }
}
function drawPath(g, pts, col, ox, oy, w = 2) {
  g.strokeStyle = col; g.lineWidth = w; g.beginPath();
  pts.forEach(([u, v, z], i) => { const [x, y] = proj(u, v, z); if (i) g.lineTo(x - ox, y - oy); else g.moveTo(x - ox, y - oy); });
  g.stroke();
}

// ---------------------------------------------------------------- people: the 1.7 m scale reference, the test agent
const HUMAN_PX = PR.human_px;
let people = [];
function defaultPeople() {
  const spots = [[L.spawns.west[0], 0], [L.spawns.east[0], 0]].concat((MAPD.people || []).map(p => [[p[0], p[1]], p[2] || 0]));
  people = spots.map(([p, layer]) => ({ u: p[0], v: p[1], layer }));
}
function personZ(p) { return LV.floorZ(p.u, p.v, p.layer); }
function drawPerson(g, x, y, col = PAL.cloth_lit) {
  const s = HUMAN_PX / 1.7;
  x = Math.round(x); y = Math.round(y);
  g.globalAlpha = 0.35; g.fillStyle = PAL.ink; g.beginPath(); g.ellipse(x, y, 0.35 * s, 0.13 * s, 0, 0, TAU); g.fill(); g.globalAlpha = 1;
  const edge = PAL.ink;
  const R = (a, b, c, d) => { g.fillStyle = edge; g.fillRect(a - 1, b - 1, c + 2, d + 2); g.fillStyle = col; g.fillRect(a, b, c, d); };
  R(x - Math.round(0.2 * s), y - Math.round(0.92 * s), Math.round(0.17 * s), Math.round(0.92 * s));
  R(x + Math.round(0.03 * s), y - Math.round(0.92 * s), Math.round(0.17 * s), Math.round(0.92 * s));
  R(x - Math.round(0.24 * s), y - Math.round(1.48 * s), Math.round(0.48 * s), Math.round(0.6 * s));
  R(x - Math.round(0.11 * s), y - Math.round(1.7 * s), Math.round(0.22 * s), Math.round(0.22 * s));
}
const o0 = L.zones.spawns.west.origin;
const agent = { u: o0[0], v: o0[1], layer: 0, r: radius, path: null, i: 0 };
function agentGo(u, v, layer) {
  agent.r = radius;
  const p = LV.findPath([agent.u, agent.v, agent.layer], [u, v, layer], radius);
  agent.path = p ? p.points : null; agent.i = 1; agent.len = p ? p.length : 0;
  if (!p) flash = 'no path for r ' + radius;
}
function agentStep(dt) {
  if (!agent.path || agent.i >= agent.path.length) return;
  let budget = 4.0 * dt;                       // 4 m/s
  while (budget > 1e-4 && agent.i < agent.path.length) {
    const [tu, tv] = agent.path[agent.i], du = tu - agent.u, dv = tv - agent.v, d = Math.hypot(du, dv);
    if (d < 0.08) { agent.i++; continue; }
    const s = Math.min(budget, d), pu = agent.u, pv = agent.v;
    LV.move(agent, du / d * s, dv / d * s);
    const moved = Math.hypot(agent.u - pu, agent.v - pv);
    budget -= s;
    if (moved < 1e-4) { agent.stuck = (agent.stuck || 0) + 1; if (agent.stuck > 30) { agent.path = null; flash = 'agent stuck'; } break; }
    agent.stuck = 0;
  }
}

// ---------------------------------------------------------------- ambience: lamps, fires, smoke, banners, snow
const props = L.props;
let smoke = [];
const SMOKE = MAPD.smoke || ['sn_hi', 'sn_mid'];
function glow(g, x, y, r, col, a1 = 0.22, a2 = 0.12) {
  g.fillStyle = col;
  g.globalAlpha = a2; g.beginPath(); g.ellipse(x, y, r, r * 0.8, 0, 0, TAU); g.fill();
  g.globalAlpha = a1; g.beginPath(); g.ellipse(x, y, r * 0.6, r * 0.5, 0, 0, TAU); g.fill();
  g.globalAlpha = 1;
}
function drawFire(g, x, y, t) {
  glow(g, x, y - 5, 30, PAL.fire, 0.14, 0.07);
  for (let i = 0; i < 5; i++) {
    const ph = t * 9 + i * 1.7;
    const hgt = 9 + 6 * Math.abs(Math.sin(ph)) + (i === 2 ? 6 : 0);
    const fx = Math.round(x - 6 + i * 3 + Math.sin(ph * 0.7) * 1.5);
    for (let k = 0; k < hgt; k++) {
      const w = Math.max(1, Math.round((1 - k / hgt) * 3));
      g.fillStyle = k < hgt * 0.35 ? PAL.lamp_core : k < hgt * 0.7 ? PAL.lamp : PAL.fire;
      g.fillRect(fx - (w >> 1), Math.round(y - k), w, 1);
    }
  }
}
function drawFlag(g, x, y, t, sv) {
  const Lf = 30, Hf = 26;
  for (let i = 0; i <= Lf; i++) {
    const k = i / Lf;
    const wv = Math.sin(t * 3.6 + sv - k * 4) * 3 * k, slope = Math.cos(t * 3.6 + sv - k * 4);
    const top = Math.round(y + wv + k * 2), h = Math.round(Hf - k * 6 + (i > Lf - 6 ? -((i - (Lf - 6)) % 3) * 3 : 0));
    g.fillStyle = slope > 0.35 ? PAL.cloth_lit : slope < -0.45 ? PAL.cloth_dk : PAL.cloth;
    g.fillRect(Math.round(x + i), top, 1, h);
  }
}
function stepSmoke(dt) {
  for (const p of props) {
    if (p.kind !== 'fire') continue;
    p.acc = (p.acc || 0) + dt;
    while (p.acc > 0.35) {
      p.acc -= 0.35;
      const [x, y] = proj(p.u, p.v, p.z + 0.6);
      smoke.push({ x: x + rr(-3, 3), y, t: 0, life: rr(4, 6), s: rr(0.8, 1.3) });
    }
  }
  for (const s of smoke) { s.t += dt; s.y -= 9 * dt * s.s; s.x += (5 + 4 * Math.sin(s.t * 1.3)) * dt; }
  smoke = smoke.filter(s => s.t < s.life);
}
function drawSmoke(g, ox, oy) {
  for (const s of smoke) {
    const k = s.t / s.life, r = 2 + 9 * k;
    g.globalAlpha = 0.32 * (1 - k); g.fillStyle = k < 0.3 ? PAL[SMOKE[0]] : PAL[SMOKE[1]];
    g.beginPath(); g.ellipse(Math.round(s.x - ox), Math.round(s.y - oy), r, r * 0.8, 0, 0, TAU); g.fill();
  }
  g.globalAlpha = 1;
}
let snow = [];
function newFlake(anywhere) {
  const cls = rnd() < 0.42 ? 0 : rnd() < 0.68 ? 1 : 2;
  return { x: rr(-40, MAPW + 40), y: anywhere ? rr(0, MAPH) : rr(-40, -8), cls, sp: [26, 42, 64][cls] * rr(0.85, 1.2),
           ph: rr(0, TAU), sw: rr(0.6, 1.4), rot: Math.floor(rr(0, 4)) };
}
function snowInit() { if (LEAVES) return leavesInit(); snow = []; for (let i = 0; i < 340; i++) snow.push(newFlake(true)); }
function snowStep(dt, t) {
  if (LEAVES) return leavesStep(dt, t);
  for (const f of snow) {
    f.y += f.sp * dt; f.x += (9 + Math.sin(t * f.sw + f.ph) * 10) * dt * (f.cls + 1) * 0.5;
    if (f.y > MAPH + 20 || f.x > MAPW + 50) Object.assign(f, newFlake(false));
  }
}
const FLAKES = [
  [[0, 0, 'sn_cap']],
  [[0, 0, 'fur'], [1, 0, 'sn_cap'], [0, 1, 'sn_cap'], [-1, 1, 'fur_dk']],
  [[0, 0, 'fur'], [1, 0, 'fur'], [0, 1, 'fur'], [1, 1, 'sn_cap'], [-1, 0, 'sn_cap'], [2, 1, 'fur_dk'], [0, 2, 'fur_dk'], [1, -1, 'sn_cap'], [-1, 2, 'fur_dk']],
];
// ---------------------------------------------------------------- leaves, motes, the pond's glints (maps with
// particles: 'leaves'): leaves let go of the red crowns (ambience.crowns), drift down turning and settle on the ground a
// moment; motes of light drift slowly and twinkle over the hollow; glints come and go on the pond's own water pixels
const AMB = LY.ambience || {};
// soft light over the picture (ambience.glows: [x, y, rx, ry, palette key, alpha]): a tinted radial sprite per colour,
// added at a low alpha and breathing slowly; those off the view are skipped; nothing when a map has none
const GLOWS = AMB.glows || [], glowSpr = {};
function glowSprite(key) {
  if (glowSpr[key]) return glowSpr[key];
  const c = document.createElement('canvas'); c.width = c.height = 128;
  const g = c.getContext('2d'), gr = g.createRadialGradient(64, 64, 0, 64, 64, 64);
  gr.addColorStop(0, 'rgba(0,0,0,1)'); gr.addColorStop(0.45, 'rgba(0,0,0,0.5)'); gr.addColorStop(1, 'rgba(0,0,0,0)');
  g.fillStyle = PAL[key] || '#ffffff'; g.fillRect(0, 0, 128, 128);
  g.globalCompositeOperation = 'destination-in'; g.fillStyle = gr; g.fillRect(0, 0, 128, 128);
  return (glowSpr[key] = c);
}
function drawGlows(g, ox, oy, t) {
  if (!GLOWS.length) return;
  g.save(); g.globalCompositeOperation = 'lighter';     // additive at a low alpha: cheaper than screen on the CPU
  const w = buf.width, h = buf.height;
  for (let i = 0; i < GLOWS.length; i++) {
    const [x, y, rx, ry, key, a] = GLOWS[i];
    if (x + rx < ox || x - rx > ox + w || y + ry < oy || y - ry > oy + h) continue;
    g.globalAlpha = a * (0.88 + 0.12 * Math.sin(t * 0.5 + i * 1.3));
    g.drawImage(glowSprite(key), x - rx - ox, y - ry - oy, 2 * rx, 2 * ry);
  }
  g.restore();
}
const LEAVES = MAPD.particles === 'leaves';
// a leaf: 3 x 4 px, two tones (its lit face and its shade), two frames that flip as it turns
const LEAFSPR = [[[1, 0, 0], [0, 1, 0], [1, 1, 0], [2, 1, 1], [0, 2, 1], [1, 2, 1], [1, 3, 1]],
                 [[1, 0, 1], [1, 1, 0], [2, 1, 0], [1, 2, 0], [0, 2, 1], [1, 3, 1]]];
const LEAFCOL = [['cr_lit', 'cr_mag'], ['ce_lit', 'ce_mag'], ['cr', 'cr_under']];
let leaves = [], motes = [], water = null, glints = [], ripples = [], floaters = [];
function newLeaf(anywhere) {
  const cr = AMB.crowns && AMB.crowns.length ? AMB.crowns[Math.floor(rnd() * AMB.crowns.length)] : [rr(0, MAPW), 0];
  const x = cr[0] + rr(-50, 50), y = cr[1] + rr(-30, 30);
  return { x, y, y0: y, land: y + rr(60, 200), sp: rr(10, 18), ph: rr(0, TAU), sw: rr(0.6, 1.2), amp: rr(15, 25),
           col: LEAFCOL[Math.floor(rnd() * 3)], rest: 0, life: rr(2, 4), x0: x };
}
function leavesInit() {
  leaves = []; for (let i = 0; i < 70; i++) { const l = newLeaf(true); l.y = l.y0 + (l.land - l.y0) * rnd(); leaves.push(l); }
  motes = []; for (let i = 0; i < 30; i++) motes.push({ x: rr(80, MAPW - 80), y: rr(MAPH * 0.3, MAPH * 0.85), ph: rr(0, TAU), sp: rr(0.3, 1), dx: rr(-4, 4) });
}
function leavesStep(dt, t) {
  for (const l of leaves) {
    if (l.y < l.land) { l.y += l.sp * dt; l.x = l.x0 + Math.sin(t * l.sw + l.ph) * l.amp; }
    else { l.rest += dt; if (l.rest > l.life) Object.assign(l, newLeaf(false)); }
  }
  for (const m of motes) { m.x += m.dx * dt * m.sp + Math.sin(t * 0.4 + m.ph) * 3 * dt; m.y -= 2.5 * dt * m.sp; if (m.y < MAPH * 0.25 || m.x < 0 || m.x > MAPW) { m.y = rr(MAPH * 0.6, MAPH * 0.88); m.x = rr(80, MAPW - 80); } }
  if (water) {
    for (const gl of glints) { gl.t += dt; gl.x += gl.vx * dt; }
    glints = glints.filter(gl => gl.t < gl.life);
    while (glints.length < 3) { const [x, y] = water.pick(0.25); glints.push({ x, y, w: 3 + Math.floor(rnd() * 4), t: 0, life: rr(3, 6), vx: rr(2, 5) }); }
    for (const r of ripples) r.t += dt;
    ripples = ripples.filter(r => r.t < 2.4);
    water.next -= dt;
    if (water.next <= 0) { const [x, y] = water.pick(0.3); ripples.push({ x, y, t: 0 }); water.next = rr(6, 10); }
    for (const f of floaters) { f.x += f.vx * dt; if (!water.has(Math.round(f.x), Math.round(f.y)) || !water.has(Math.round(f.x) + 3, Math.round(f.y))) f.vx = -f.vx; f.x += f.vx * dt; }
  }
}
function findGlints() {         // the pond's own water pixels in main.png (its colours: ambience.pond), as a mask
  const P_ = AMB.pond; if (!P_) return;
  const c = mapCanvas(), g = c.getContext('2d'); g.drawImage(IMG.main, 0, 0);
  const x0 = Math.max(0, P_.x0 - 20), y0 = Math.max(0, P_.y0 - 20), w = Math.min(MAPW, P_.x1 + 20) - x0, h = Math.min(MAPH, P_.y1 + 20) - y0;
  if (w <= 0 || h <= 0) return;
  const d = g.getImageData(x0, y0, w, h).data, cols = new Set((P_.colours || []).map(cc => cc.join(',')));
  const mask = new Uint8Array(w * h), pts = [];
  for (let y = 0; y < h; y++) for (let x = 0; x < w; x++) {
    const i = (y * w + x) * 4;
    if (cols.has(d[i] + ',' + d[i + 1] + ',' + d[i + 2])) { mask[y * w + x] = 1; pts.push([x0 + x, y0 + y]); }
  }
  if (!pts.length) return;
  const cx = (P_.x0 + P_.x1) / 2, cy = (P_.y0 + P_.y1) / 2, rx = (P_.x1 - P_.x0) / 2, ry = (P_.y1 - P_.y0) / 2;
  water = { mask, x0, y0, w, h, next: rr(1, 4),
            has: (x, y) => x >= x0 && y >= y0 && x < x0 + w && y < y0 + h && mask[(y - y0) * w + (x - x0)] === 1,
            pick: (inner) => { for (let k = 0; k < 40; k++) { const p = pts[Math.floor(rnd() * pts.length)]; if (Math.hypot((p[0] - cx) / rx, (p[1] - cy) / ry) < 1 - inner) return p; } return pts[Math.floor(rnd() * pts.length)]; } };
  for (let k = 0; k < 2; k++) { const [x, y] = water.pick(0.35); floaters.push({ x, y, vx: rr(1.2, 2.5) * (k ? -1 : 1), col: LEAFCOL[k] }); }
}
function wpx(g, x, y, col) { if (water.has(x, y)) { g.fillStyle = col; g.fillRect(x - camX, y - camY, 1, 1); } }
function drawLeaves(g, t) {
  if (water) {
    for (const gl of glints) {                 // slow sky streaks sliding across the open water
      g.globalAlpha = Math.sin(Math.PI * gl.t / gl.life) * 0.9;
      for (let k = 0; k < gl.w; k++) wpx(g, Math.round(gl.x) + k, gl.y, PAL.wa_hi);
    }
    for (const r of ripples) {                 // an expanding ring, fading
      const rad = 3 + r.t * 9; g.globalAlpha = 0.7 * (1 - r.t / 2.4);
      for (let k = 0; k < 48; k++) { const a = k / 48 * TAU; wpx(g, Math.round(r.x + Math.cos(a) * rad), Math.round(r.y + Math.sin(a) * rad * 0.55), PAL.wa_hi); }
    }
    g.globalAlpha = 1;
    for (const f of floaters) {
      const x = Math.round(f.x - camX), y = Math.round(f.y - camY);
      for (const [dx, dy, k] of LEAFSPR[0]) { g.fillStyle = PAL[f.col[k]]; g.fillRect(x + dy, y + dx, 1, 1); }
    }
  }
  for (const m of motes) {
    const a = 0.35 + 0.35 * Math.sin(t * 1.7 + m.ph);
    if (a < 0.1) continue;
    g.globalAlpha = a; g.fillStyle = PAL.lamp_core; g.fillRect(Math.round(m.x - camX), Math.round(m.y - camY), 1, 1);
  }
  g.globalAlpha = 1;
  for (const l of leaves) {
    const x = Math.round(l.x - camX), y = Math.round(l.y - camY);
    if (x < -6 || y < -6 || x > buf.width + 6 || y > buf.height + 6) continue;
    const landed = l.y >= l.land;
    if (landed) g.globalAlpha = Math.min(1, Math.max(0, 1.5 * (1 - l.rest / l.life)));
    const fr = landed ? 0 : Math.floor(t * 2 * l.sw + l.ph) % 2;
    for (const [dx, dy, k] of LEAFSPR[fr]) { g.fillStyle = PAL[l.col[k]]; g.fillRect(x + dx, y + dy, 1, 1); }
    g.globalAlpha = 1;
  }
}
function drawSnow(g, t) {
  if (LEAVES) return drawLeaves(g, t);
  for (const f of snow) {
    const x = Math.round(f.x - camX), y = Math.round(f.y - camY);
    if (x < -4 || y < -4 || x > buf.width + 4 || y > buf.height + 4) continue;
    const st = FLAKES[f.cls];
    const r = (f.rot + Math.floor(t * 2 + f.ph)) % 4;
    for (const [dx, dy, c] of st) {
      const [rx, ry] = r === 0 ? [dx, dy] : r === 1 ? [-dy, dx] : r === 2 ? [-dx, -dy] : [dy, -dx];
      g.fillStyle = PAL[c]; g.fillRect(x + rx, y + ry, 1, 1);
    }
  }
}

// ---------------------------------------------------------------- the view
const cv = document.getElementById('view');
const ctx = cv.getContext('2d');
const buf = document.createElement('canvas');
const bx = buf.getContext('2d');
const scene = document.createElement('canvas');
const sx = scene.getContext('2d');
// the fit view (zoom < 1): the composed scene is scaled down once into a screen-sized picture, and only the rects the
// compose touched (sway runs, sky bands) are scaled again; each frame then blits it 1:1 and draws the moving things
// (lights, leaves, glints, people, paths, overlays) over it at the zoom
const fitc = document.createElement('canvas');
const fx = fitc.getContext('2d');
let dirty = [], fullDirty = false;
function flushFit(all) {
  // bilinear ('low': no mipmaps of the whole scene per call); the patches of one tick are spread over the next frames
  // within a small budget (a tick comes every 10 frames), all at once after a full repaint or for a still shot
  if (!dirty.length) return;
  fx.imageSmoothingEnabled = true; fx.imageSmoothingQuality = 'low';
  const W = scene.width, H = scene.height, t0 = performance.now();
  while (dirty.length) {
    if (!all && performance.now() - t0 > 4) break;
    const [x0, y0, x1, y1] = dirty.shift();
    const dx0 = Math.floor(x0 * zoom), dy0 = Math.floor(y0 * zoom), dx1 = Math.ceil(x1 * zoom), dy1 = Math.ceil(y1 * zoom);
    // the source rect a few pixels wider than the destination, mapped by the same transform as the whole picture,
    // so a patch samples exactly as a full rescale would (no seams)
    const X0 = Math.max(0, Math.floor(dx0 / zoom) - 3), Y0 = Math.max(0, Math.floor(dy0 / zoom) - 3);
    const X1 = Math.min(W, Math.ceil(dx1 / zoom) + 3), Y1 = Math.min(H, Math.ceil(dy1 / zoom) + 3);
    fx.save(); fx.beginPath(); fx.rect(dx0, dy0, dx1 - dx0, dy1 - dy0); fx.clip();
    fx.clearRect(dx0, dy0, dx1 - dx0, dy1 - dy0);
    fx.drawImage(scene, X0, Y0, X1 - X0, Y1 - Y0, X0 * zoom, Y0 * zoom, (X1 - X0) * zoom, (Y1 - Y0) * zoom);
    fx.restore();
  }
}
let zoom = 1, fit = false, camX = 0, camY = 0, time = +(Q.get('t') || 0), paused = Q.has('pause');
const show = { grid: false, zones: false, scale: false, snow: true, colliders: false, nav: false, los: false, paths: false, agent: false,
               sway: Q.get('sway') !== '0', drift: Q.get('drift') !== '0' };
(Q.get('overlay') || '').split(',').filter(Boolean).forEach(k => { if (k in show) show[k] = true; });
if (Q.get('snow') === '0') show.snow = false;
let cursor = null, flash = '';
const OCC_BUCKET = 64, occGrid = new Map();
OCC.forEach((o, i) => {
  for (let gx = Math.floor(o.x / OCC_BUCKET); gx <= Math.floor((o.x + o.w) / OCC_BUCKET); gx++)
    for (let gy = Math.floor(o.y / OCC_BUCKET); gy <= Math.floor((o.y + o.h) / OCC_BUCKET); gy++) {
      const k = gx + ',' + gy;
      if (!occGrid.has(k)) occGrid.set(k, []);
      occGrid.get(k).push(i);
    }
});
function resize() {
  const dpr = Math.min(2, window.devicePixelRatio || 1);
  cv.width = Math.floor(innerWidth * dpr); cv.height = Math.floor(innerHeight * dpr);
  cv.style.width = innerWidth + 'px'; cv.style.height = innerHeight + 'px';
  if (fit) zoom = Math.min(cv.width / MAPW, cv.height / MAPH);
  else zoom = Math.max(1, Math.round(zoom));
  buf.width = Math.min(Math.ceil(cv.width / zoom), MAPW); buf.height = Math.min(Math.ceil(cv.height / zoom), MAPH);
  scene.width = buf.width; scene.height = buf.height; lastCam = '';
  fitc.width = zoom < 1 ? Math.round(buf.width * zoom) : 1; fitc.height = zoom < 1 ? Math.round(buf.height * zoom) : 1;
  dirty = [];
  clampCam();
}
function clampCam() { camX = Math.max(0, Math.min(MAPW - buf.width, camX)); camY = Math.max(0, Math.min(MAPH - buf.height, camY)); }
function centreOn(x, y) { camX = Math.round(x - buf.width / 2); camY = Math.round(y - buf.height / 2); clampCam(); }
const offset = () => [Math.floor((cv.width - Math.round(buf.width * zoom)) / 2), Math.floor((cv.height - Math.round(buf.height * zoom)) / 2)];
function toScreen(mx, my) { const [ox, oy] = offset(), dpr = cv.width / innerWidth; return [((mx - camX) * zoom + ox) / dpr, ((my - camY) * zoom + oy) / dpr]; }
function screenToMap(ex, ey) { const [ox, oy] = offset(), dpr = cv.width / innerWidth; return [(ex * dpr - ox) / zoom + camX, (ey * dpr - oy) / zoom + camY]; }

// the layers: where each sits for the camera (parallax about the centred view) and the time (drift), whole pixels
function layerAt(name, t) {
  const l = LY[name], refX = (MAPW - buf.width) / 2, refY = (MAPH - buf.height) / 2;
  const ex = refX + (camX - refX) * l.parallax[0], ey = refY + (camY - refY) * l.parallax[1];
  let x = l.x - ex, y = l.y - ey;
  if (l.drift && show.drift) x += l.drift * t;
  if (l.drift_amp && show.drift) x += l.drift_amp * Math.sin(TAU * t / l.drift_period);
  x = Math.round(x); y = Math.round(y);
  if (l.wrap) { x = ((x % l.wrap) + l.wrap) % l.wrap; if (x > 0) x -= l.wrap; }
  return [x, y];
}
// The scene is kept between frames and repainted by regions on the sway's tick: the sky band at the top (sky, far
// cumulus, the map's rows there, the swayed tiles in it), the sea band at the bottom (the map's rows, corner towers,
// sea, the ledge's front), and in between only the tiles the sway frame changes. A camera move repaints it all.
let composes = 0, bands = [];
const prof = { draw: 0 };
let lastCam = '', lastF = -2, lastTop = '', lastBot = '', BOT0 = MAPH;
// per frame: tile 'tx,ty' -> its [ax, ay] in the atlas (runs are strips there, n tiles wide)
const frameTiles = SW.frames.map(fr => { const m = new Map(); for (const [t0, ty, n, ax, ay] of fr) for (let k = 0; k < n; k++) m.set((t0 + k) + ',' + ty, [ax + k * SW.tile, ay]); return m; });
function findBands() {        // the rows where main.png lets the sky through (the top), and where the sea can lap
  const c = mapCanvas(), g = c.getContext('2d');
  g.drawImage(IMG.main, 0, 0);
  const a = g.getImageData(0, 0, MAPW, MAPH).data;
  let open = -1;
  for (let y = 0; y <= MAPH; y++) {
    let see = false;
    if (y < MAPH) for (let x = 0, i = y * MAPW * 4 + 3; x < MAPW; x++, i += 4) if (a[i] < 255) { see = true; break; }
    if (see && open < 0) open = y;
    if (!see && open >= 0) { bands.push([open, y]); open = -1; }
  }
  const T = SW.tile;           // whole tiles, so a region repaint covers every tile it touches
  bands = bands.map(([p, q]) => [Math.floor(p / T) * T, Math.ceil(q / T) * T]);
  BOT0 = (LY.sea || LY.corner) ? Math.floor(Math.min(LY.sea ? LY.sea.y : MAPH, LY.corner ? LY.corner.y : MAPH) / T) * T : MAPH;
}
let curF = -1, curAt = null;
function blit(img, ix, iy, xa, xb, a, b) {   // img placed at scene (ix, iy), clipped to scene rect [xa, xb) x [a, b)
  const y0 = Math.max(a, iy), y1 = Math.min(b, iy + img.height), x0 = Math.max(xa, ix), x1 = Math.min(xb, ix + img.width);
  if (y1 > y0 && x1 > x0) sx.drawImage(img, x0 - ix, y0 - iy, x1 - x0, y1 - y0, x0, y0, x1 - x0, y1 - y0);
}
function behind(xa, xb, a, b) {              // the sky and the far cumulus, where the sky band shows through
  for (const [y0, y1] of bands) {
    const p = Math.max(a, y0 - camY), q = Math.min(b, y1 - camY);
    if (q <= p) continue;
    blit(IMG.sky, curAt.sky[0], curAt.sky[1], xa, xb, p, q);
    if (LY.far) for (let x = curAt.far[0]; x < xb; x += LY.far.wrap) blit(IMG.far, x, curAt.far[1], xa, xb, p, q);
  }
}
const inBands = (y0, y1) => bands.some(([a, b]) => y0 < b && y1 > a);
function run(t0, ty, n, ax, ay, a, b) {      // a sway run (ax < 0: main's own pixels) at its place, scene rows [a, b)
  const T = SW.tile, x = t0 * T - camX, y = ty * T - camY, w = n * T;
  const p = Math.max(a, y), q = Math.min(b, y + T), x0 = Math.max(0, x), x1 = Math.min(scene.width, x + w);
  if (q <= p || x1 <= x0) return;
  dirty.push([x0, p, x1, q]);
  if (inBands(ty * T, ty * T + T)) { sx.clearRect(x0, p, x1 - x0, q - p); behind(x0, x1, p, q); }
  if (ax < 0) sx.drawImage(IMG.main, x0 + camX, p + camY, x1 - x0, q - p, x0, p, x1 - x0, q - p);
  else sx.drawImage(IMG.sway, ax + (x0 - x), ay + (p - y), x1 - x0, q - p, x0, p, x1 - x0, q - p);
}
function paintRows(m0, m1) {            // repaint map rows [m0, m1) of the scene
  const h = scene.height, w = scene.width, a = Math.max(0, m0 - camY), b = Math.min(h, m1 - camY);
  if (b <= a) return;
  if (a === 0 && b === h) { dirty = []; fullDirty = true; }
  dirty.push([0, a, w, b]);
  sx.clearRect(0, a, w, b - a);
  behind(0, w, a, b);
  sx.drawImage(IMG.main, camX, camY + a, w, b - a, 0, a, w, b - a);
  if (curF >= 0) for (const [t0, ty, n, ax, ay] of SW.frames[curF]) run(t0, ty, n, ax, ay, a, b);
  if (LY.corner) blit(IMG.corner, curAt.corner[0], curAt.corner[1], 0, w, a, b);
  if (LY.sea) for (let x = curAt.sea[0]; x < w; x += LY.sea.wrap) blit(IMG.sea, x, curAt.sea[1], 0, w, a, b);
  if (LY.cap) blit(IMG.cap, LY.cap.x - camX, LY.cap.y - camY, 0, w, a, b);
}
function middle(prevF, f) {             // between the bands: put back main where the old frame was, the new frame's runs
  const T = SW.tile, top = bands.length ? bands[bands.length - 1][1] : 0, h = scene.height;
  const mid = ty => ty * T >= top && (ty + 1) * T <= BOT0;
  if (prevF >= 0) {
    const cur = f >= 0 ? frameTiles[f] : new Map();
    for (const [t0, ty, n] of SW.frames[prevF]) {
      if (!mid(ty)) continue;
      let k = 0;
      while (k < n) {                    // sub-runs the new frame does not cover
        if (cur.has((t0 + k) + ',' + ty)) { k++; continue; }
        const s0 = k; while (k < n && !cur.has((t0 + k) + ',' + ty)) k++;
        run(t0 + s0, ty, k - s0, -1, 0, 0, h);
      }
    }
  }
  if (f >= 0) for (const [t0, ty, n, ax, ay] of SW.frames[f]) if (mid(ty)) run(t0, ty, n, ax, ay, 0, h);
}
function compose(t) {
  // everything in the scene moves on the sway's tick (SW.fps), by whole pixels
  const tick = Math.floor(t * SW.fps), tt = tick / SW.fps;
  const f = show.sway ? tick % SW.n : -1;
  const at = {}; for (const n of ['sky', 'far', 'corner', 'sea']) if (LY[n]) at[n] = layerAt(n, tt);
  const cam = [camX, camY, scene.width, scene.height].join(), top = [at.sky, at.far].join(), bot = [at.sea, at.corner].join();
  if (cam === lastCam && f === lastF && top === lastTop && bot === lastBot) return;
  const t0 = performance.now();
  composes++;
  const prevF = curF;
  curF = f; curAt = at;
  sx.imageSmoothingEnabled = false;
  if (cam !== lastCam) paintRows(0, MAPH);
  else {
    if (f !== lastF || top !== lastTop) for (const [y0, y1] of bands) paintRows(y0, y1);
    if (f !== lastF || bot !== lastBot) paintRows(BOT0, MAPH);
    if (f !== lastF) middle(prevF, f);
  }
  lastCam = cam; lastF = f; lastTop = top; lastBot = bot;
  prof.draw += performance.now() - t0;
}

// Draw order for anything standing on the map (your units): far to near by depth (v cos el - z sin el); a cut-out
// from occ.json goes over a figure when it is nearer (its d smaller) and overlaps it; the bridge (deck: 1) goes over
// figures on the height field and under figures on the deck.
function drawStanding(g, ox, oy, figs) {
  for (const pass of [0, 1]) {
    const items = [], used = new Set();
    for (const p of figs) {
      if (p.layer !== pass) continue;
      const z = personZ(p), [x, y] = proj(p.u, p.v, z), d = depthOf(p.u, p.v, z);
      items.push({ d, x, y, p });
      const x0 = x - 20, y0 = y - HUMAN_PX - 4, x1 = x + 20, y1 = y + 4;
      for (let gx = Math.floor(x0 / OCC_BUCKET); gx <= Math.floor(x1 / OCC_BUCKET); gx++)
        for (let gy = Math.floor(y0 / OCC_BUCKET); gy <= Math.floor(y1 / OCC_BUCKET); gy++) {
          for (const i of occGrid.get(gx + ',' + gy) || []) {
            if (used.has(i)) continue;
            const o = OCC[i];
            if (!(o.x < x1 && o.x + o.w > x0 && o.y < y1 && o.y + o.h > y0)) continue;
            if (o.deck) { if (pass === 0) { used.add(i); items.push({ d: -1e9, occ: o }); } continue; }
            if (o.d < d) { used.add(i); items.push({ d: o.d, occ: o }); }
          }
        }
    }
    items.sort((a, b) => b.d - a.d);
    const hidden = [];
    for (const it of items) {
      if (it.occ) { const o = it.occ; g.drawImage(IMG.occ, o.ax, o.ay, o.w, o.h, o.x - ox, o.y - oy, o.w, o.h); }
      else {
        if (it.p.agent) {           // the test agent's footprint: its radius on the floor
          const z = personZ(it.p), [cx, cy] = proj(it.p.u, it.p.v, z);
          g.strokeStyle = '#ffd27a'; g.lineWidth = 2; g.beginPath(); g.ellipse(cx - ox, cy - oy, it.p.r * PPM, it.p.r * PPM * SE, 0, 0, TAU); g.stroke();
        }
        drawPerson(g, it.x - ox, it.y - oy, it.p.agent ? '#ffd27a' : PAL.cloth_lit);
        hidden.push(it);
      }
    }
    // the occlusion contract (README "Draw order"): a unit with art drawn over it shows through as a silhouette
    for (const it of hidden) {
      const covered = items.some(o => o.occ && o.d < it.d && o.occ.x < it.x + 12 && o.occ.x + o.occ.w > it.x - 12 &&
                                          o.occ.y < it.y && o.occ.y + o.occ.h > it.y - HUMAN_PX);
      if (!covered) continue;
      g.globalAlpha = 0.55; drawPerson(g, it.x - ox, it.y - oy, it.p.agent ? '#ffd27a' : PAL.cloth_lit); g.globalAlpha = 1;
    }
  }
}

function render() {
  const t = time;
  compose(t);
  const [px, py] = offset();
  ctx.setTransform(1, 0, 0, 1, 0, 0);
  ctx.fillStyle = PAL.ink; ctx.fillRect(0, 0, cv.width, cv.height);
  if (zoom < 1) {                            // fit: the scaled picture 1:1, the moving things over it at the zoom
    flushFit(fullDirty || paused); fullDirty = false;
    ctx.drawImage(fitc, px, py);
    ctx.save();
    ctx.beginPath(); ctx.rect(px, py, fitc.width, fitc.height); ctx.clip();
    ctx.setTransform(zoom, 0, 0, zoom, px, py);
    ctx.imageSmoothingEnabled = true;
    over(ctx, t);
    ctx.restore();
  } else {
    dirty = [];
    bx.imageSmoothingEnabled = false;
    bx.drawImage(scene, 0, 0);
    over(bx, t);
    ctx.imageSmoothingEnabled = false;
    ctx.drawImage(buf, px, py, Math.round(buf.width * zoom), Math.round(buf.height * zoom));
  }
  labels();
}
function over(g, t) {                        // everything drawn over the composed scene, in scene pixels
  const ox = camX, oy = camY, w = buf.width, h = buf.height;
  const ov = c => g.drawImage(c, ox, oy, w, h, 0, 0, w, h);
  drawGlows(g, ox, oy, t);
  if (show.zones) ov(OV.zones);
  if (show.grid) ov(OV.grid);
  if (show.scale) ov(OV.metres);
  if (show.nav) ov(OV.nav);
  if (show.colliders) ov(OV.colliders);
  if (show.los && OV.los) ov(OV.los);
  for (const p of props) {
    if (p.kind === 'heart') { const [x, y] = proj(p.u, p.v, p.z + 1.62); glow(g, x - ox, y - oy, 34 + 3 * Math.sin(t * 2.2 + p.u), PAL.lamp_core, 0.2, 0.1); }
    else if (p.kind === 'lamppost') { const [x, y] = proj(p.u + (p.u < 0 ? 0.45 : -0.45), p.v, p.z + 1.88); glow(g, x - ox, y - oy, 12 + Math.sin(t * 5 + p.u) * 1.2, PAL.lamp, 0.22, 0.12); }
    else if (p.kind === 'tower') { const [x, y] = proj(p.u, p.v, p.z + 6.15); glow(g, x - ox, y - oy, 16, PAL.lamp, 0.22, 0.1); }
    else if (p.kind === 'fire') { const [x, y] = proj(p.u, p.v, p.z + 0.1); drawFire(g, x - ox, y - oy, t); }
    else if (p.kind === 'banner') { const [x, y] = proj(p.u, p.v, p.z + 4.85); drawFlag(g, x - ox + 2, y - oy, t, p.v); }
    else if (p.kind === 'waystone') { const [x, y] = proj(p.u, p.v - 0.3, p.z + 1.0); glow(g, x - ox, y - oy, 16 + 0.6 * Math.sin(t * 1.6 + p.u), PAL.rune, 0.14, 0.06); }
    else if (p.kind === 'potlight') { const [x, y] = proj(p.u, p.v, p.z + 0.32); glow(g, x - ox, y - oy, 9 + 0.5 * Math.sin(t * 3 + p.v), PAL.lamp, 0.2, 0.08); }
    else if (p.kind === 'lantern') { const [x, y] = proj(p.u, p.v - 0.2, p.z + 1.02); glow(g, x - ox, y - oy, 10 + 0.4 * Math.sin(t * 4 + p.u), PAL.lamp, 0.16, 0.07); }
  }
  drawSmoke(g, ox, oy);
  if (show.paths) {
    if (objRoutes) for (const r of objRoutes) drawPath(g, r.p.points, SIDECOL[r.side], ox, oy, 2);
    if (cursor) for (const side of ['west', 'east']) { const p = pathTo(side, cursor); if (p) { drawPath(g, p.points, '#141a30', ox, oy, 5); drawPath(g, p.points, SIDECOL[side], ox, oy, 3); } }
  }
  if (show.agent && agent.path) drawPath(g, [[agent.u, agent.v, LV.floorZ(agent.u, agent.v, agent.layer)], ...agent.path.slice(agent.i)], '#ffd27a', ox, oy, 2);
  const figs = (show.scale ? people.slice() : []).concat(show.agent ? [Object.assign(agent, { agent: true })] : []);
  if (figs.length) drawStanding(g, ox, oy, figs);
  if (show.snow) drawSnow(g, t);
}

// labels in screen space (crisp at any zoom)
function labels() {
  const dpr = cv.width / innerWidth;
  ctx.save(); ctx.scale(dpr, dpr);
  ctx.font = '11px ui-monospace, Menlo, Consolas, monospace'; ctx.textBaseline = 'middle';
  const tag = (mx, my, text, col) => {
    const [x, y] = toScreen(mx, my);
    if (x < -50 || y < -20 || x > innerWidth + 50 || y > innerHeight + 20) return;
    const w = ctx.measureText(text).width + 8;
    ctx.fillStyle = 'rgba(20,26,48,0.84)'; ctx.fillRect(Math.round(x - w / 2), Math.round(y - 8), Math.round(w), 16);
    ctx.fillStyle = col; ctx.fillText(text, Math.round(x - w / 2 + 4), Math.round(y));
  };
  if (show.grid) {
    for (const side of ['west', 'east']) for (const [u, v, z] of L.spawns[side]) {
      const [x, y] = toScreen(...proj(u, v, z));
      ctx.strokeStyle = '#ffffff'; ctx.lineWidth = 1.5; ctx.beginPath(); ctx.arc(x, y, 3.5 * Math.max(1, zoom * 0.8), 0, TAU); ctx.stroke();
    }
    for (const side of ['west', 'east']) { const [u, v, z] = L.spawns[side][0]; const [x, y] = proj(u, v, z); tag(x, y + 26, 'spawns: ' + side, '#ffffff'); }
    for (const o of L.zones.objectives) { const [x, y] = proj(o.u, o.v, o.z); tag(x, y - 64, o.kind + (o.side ? ' ' + o.side : ''), '#ffd27a'); }
    for (const c of L.zones.chokepoints) { const [x, y] = proj(c.u, c.v, c.layer ? deckZ(c.v) : heightAt(c.u, c.v)); tag(x, y, `${c.name} ${c.width.toFixed(1)} m`, c.layer ? '#78ffc8' : '#9fd0ff'); }
  }
  if (show.nav) for (const lk of L.nav.links) {
    const p = lk.kind === 'ramp' ? lk.entry[1] : lk.edge[1], z = lk.kind === 'ramp' ? heightAt(p[0], p[1]) : deckZ(p[1]);
    const [x, y] = proj(p[0] + 0.6, p[1], z); tag(x, y, lk.kind === 'ramp' ? lk.name + ' (entry, exit)' : lk.name, '#9fffe0');
  }
  if (show.paths && objRoutes) for (const r of objRoutes) {
    const e = r.p.points[r.p.points.length - 1], [x, y] = proj(e[0], e[1], e[2]);
    tag(x + (r.side === 'west' ? -46 : 46), y - 30 - (r.ob.kind === 'stones' ? (r.side === 'west' ? 0 : 18) : 0), `${r.side} ${r.p.length.toFixed(1)} m`, SIDECOL[r.side]);
  }
  if (show.paths && cursor) {
    const ps = ['west', 'east'].map(s => pathTo(s, cursor)), [x, y] = proj(cursor[0], cursor[1], LV.floorZ(...cursor));
    tag(x, y + 18, ps.map((p, i) => `${['W', 'E'][i]} ${p ? p.length.toFixed(1) + ' m' : '-'}`).join('  '), '#ffffff');
  }
  if (show.agent && agent.path) { const e = agent.path[agent.path.length - 1], [x, y] = proj(e[0], e[1], e[2]); tag(x, y + 16, `${agent.len.toFixed(1)} m, r ${agent.r}`, '#ffd27a'); }
  if (show.scale) for (const p of people) { const [x, y] = proj(p.u, p.v, personZ(p)); tag(x, y - HUMAN_PX - 12, p.layer ? '1.7 m (deck)' : '1.7 m', '#f4dcc8'); }
  ctx.restore();
}

// ---------------------------------------------------------------- the panel (DOM)
const $ = id => document.getElementById(id);
const BUTTONS = ['grid', 'zones', 'scale', 'colliders', 'nav', 'los', 'paths', 'agent', 'snow'];
function panel() {
  for (const k of BUTTONS) $('b-' + k).classList.toggle('on', show[k]);
  $('b-zoom').textContent = fit ? 'fit' : zoom + 'x';
  $('b-r').textContent = 'r ' + radius;
  $('b-lv').textContent = 'level ' + (collLevel === 'all' ? 'all' : LEVEL[collLevel]);
  const leg = $('legend');
  let html = '';
  if (show.grid) html += '<div><i style="background:rgba(255,255,255,.5)"></i>walkable <i style="background:rgba(90,170,255,.8)"></i>trodden lane <i style="background:rgba(255,200,100,.8)"></i>high ground <i style="background:rgba(120,255,200,.9)"></i>bridge deck <i style="background:rgba(235,70,70,.9)"></i>blocked edge</div>';
  if (show.zones) html += '<div>' + Object.entries(ZNAME).map(([c, n]) => `<i style="background:rgb(${ZCOL[c].join(',')})"></i>${n}`).join(' ') + '</div>';
  if (show.scale) html += `<div>1 m grid on the walkable ground (every 5 m stronger) &middot; people 1.7 m = ${HUMAN_PX} px &middot; click to stand one</div>`;
  if (show.colliders) html += `<div>colliders (${collLevel === 'all' ? 'all levels' : LEVEL[collLevel]}, V): ${LEVEL.map((n, i) => `<i style="background:rgb(${LCOL[i]})"></i>${n}`).join(' ')} &middot; filled blocks sight, dashed moves only &middot; <i style="background:#ff4646"></i>wall <i style="background:#5abeff"></i>lip <i style="background:#fff"></i>bound</div>`;
  if (show.nav) html += `<div>nav clearance: <i style="background:rgb(235,70,70)"></i>&lt; 0.3 <i style="background:rgb(245,150,60)"></i>0.3 <i style="background:rgb(230,220,90)"></i>0.5 <i style="background:rgb(110,220,120)"></i>0.8+ m &middot; dim = too tight for r ${radius} (R) &middot; links: ramp entry / exit, deck ends</div>`;
  if (show.los) html += '<div>line of sight from the cursor, eye to eye (1.6 m over each floor): <i style="background:rgb(120,255,150)"></i>seen <i style="background:rgb(60,20,60)"></i>hidden</div>';
  if (show.paths) html += `<div>A* (r ${radius}) from both spawns: <i style="background:${SIDECOL.west}"></i>west <i style="background:${SIDECOL.east}"></i>east &middot; to the objectives and to the cursor</div>`;
  if (show.agent) html += `<div>test agent (r ${radius}): click to send it; it walks the A* path through the colliders</div>`;
  leg.innerHTML = html; leg.style.display = html ? 'block' : 'none';
}
function readout(mx, my) {
  const [u, v, z, layer] = unproj(mx, my);
  const k = LV.cellOf(u, v), c = k < 0 ? 0 : LV.clear[layer][k], s = k < 0 ? 0 : LV.surf[layer][k];
  const what = c > 0 ? (SURF[s & 7] || '') + (s & 8 ? ' (ramp)' : '') + `, clearance ${c.toFixed(2)} m` : 'not walkable';
  let txt = `u ${u.toFixed(1)}  v ${v.toFixed(1)}  z ${z.toFixed(1)} m  ${LEVEL[LV.levelOf(u, v, layer)]}  ${what}`;
  if (show.paths && cursor) { const ps = ['west', 'east'].map(sd => pathTo(sd, cursor)); txt += `  |  from the west ${ps[0] ? ps[0].length.toFixed(1) : '-'} m, east ${ps[1] ? ps[1].length.toFixed(1) : '-'} m`; }
  if (flash) { txt += '  |  ' + flash; flash = ''; }
  $('read').textContent = txt;
}

// ---------------------------------------------------------------- input
let drag = null, losTimer = 0;
cv.addEventListener('contextmenu', e => e.preventDefault());
cv.addEventListener('pointerdown', e => { drag = { x: e.clientX, y: e.clientY, cx: camX, cy: camY, moved: false }; });
addEventListener('pointermove', e => {
  const [mx, my] = screenToMap(e.clientX, e.clientY);
  const [u, v, , layer] = unproj(mx, my);
  const k = LV.cellOf(u, v);
  cursor = k >= 0 && LV.clear[layer][k] > 0 ? [u, v, layer] : null;
  readout(mx, my);
  if (show.los && cursor) {
    const key = LV.cellOf(u, v) + ':' + layer;
    if (key !== losKey) { losKey = key; clearTimeout(losTimer); losTimer = setTimeout(() => buildLos(cursor, 2), 60); }
  }
  if (!drag) return;
  const kk = (cv.width / innerWidth) / zoom, dx = (e.clientX - drag.x) * kk, dy = (e.clientY - drag.y) * kk;
  if (Math.hypot(e.clientX - drag.x, e.clientY - drag.y) > 4) drag.moved = true;
  camX = Math.round(drag.cx - dx); camY = Math.round(drag.cy - dy); clampCam();
});
addEventListener('pointerup', e => {
  if (drag && !drag.moved && e.target === cv) {
    const [mx, my] = screenToMap(e.clientX, e.clientY);
    const [u, v, , layer] = unproj(mx, my);
    const k = LV.cellOf(u, v), ok = k >= 0 && LV.clear[layer][k] > 0;
    if (show.agent && ok) agentGo(u, v, layer);
    else if (show.scale && ok) { people.push({ u, v, layer }); if (people.length > 24) people.shift(); }
  }
  drag = null;
});
const keys = {};
addEventListener('keydown', e => {
  const k = e.key.toLowerCase();
  keys[k] = true;
  const map = { g: 'grid', z: 'zones', m: 'scale', f: 'snow', k: 'colliders', n: 'nav', l: 'los', p: 'paths', u: 'agent' };
  if (map[k]) toggle(map[k]);
  if (k === 'x') toggleZoom();
  if (k === 'r') cycleRadius();
  if (k === 'v') cycleLevel();
  if (k === ' ') { paused = !paused; e.preventDefault(); }
  if (k === 'c') defaultPeople();
});
addEventListener('keyup', e => { keys[e.key.toLowerCase()] = false; });
addEventListener('wheel', e => {
  const c = [camX + buf.width / 2, camY + buf.height / 2];
  if (e.deltaY < 0) { if (fit) { fit = false; zoom = 1; } else if (zoom < 3) zoom++; }
  else { if (zoom > 1) zoom--; else fit = true; }
  resize(); centreOn(...c); panel();
}, { passive: true });
function toggle(k) {
  show[k] = !show[k];
  if (k === 'colliders' && show[k] && !OV.colliders) buildColliders();
  if (k === 'nav' && show[k]) buildNav();
  if (k === 'paths' && show[k]) routesToObjectives();
  if (k === 'los' && show[k]) buildLos(cursor || [o0[0], o0[1], 0], 2);
  panel();
}
function cycleRadius() {
  radius = RADII[(RADII.indexOf(radius) + 1) % RADII.length];
  if (show.nav) buildNav();
  if (show.paths) routesToObjectives();
  panel();
}
function cycleLevel() {
  const order = ['all'].concat(LEVEL.map((_, i) => i));
  collLevel = order[(order.indexOf(collLevel) + 1) % order.length];
  buildColliders(); panel();
}
function toggleZoom() {
  const c = [camX + buf.width / 2, camY + buf.height / 2];
  if (fit) { fit = false; zoom = 1; } else if (zoom < 2) zoom = 2; else fit = true;
  resize(); centreOn(...c); panel();
}
for (const k of BUTTONS) $('b-' + k).onclick = () => toggle(k);
$('b-zoom').onclick = toggleZoom; $('b-r').onclick = cycleRadius; $('b-lv').onclick = cycleLevel;
$('b-data').onclick = () => {
  const a = document.createElement('a');
  a.href = URL.createObjectURL(new Blob([JSON.stringify(L)], { type: 'application/json' }));
  a.download = (MAPD.name || L.name) + '.level.json'; document.body.appendChild(a); a.click(); a.remove();
};
addEventListener('resize', () => { resize(); panel(); });

// ---------------------------------------------------------------- run
let last = performance.now();
function frame(now) {
  const dt = Math.min(0.1, (now - last) / 1000); last = now;
  if (!paused) { time += dt; snowStep(dt, time); stepSmoke(dt); if (show.agent) agentStep(dt); }
  const pv = 520 * (keys['shift'] ? 2 : 1) * dt / Math.max(1, zoom);
  if (keys['arrowleft'] || keys['a']) camX -= pv;
  if (keys['arrowright'] || keys['d']) camX += pv;
  if (keys['arrowup'] || keys['w']) camY -= pv;
  if (keys['arrowdown'] || keys['s']) camY += pv;
  camX = Math.round(camX); camY = Math.round(camY); clampCam();
  render();
  requestAnimationFrame(frame);
}
const qpt = s => { const a = (Q.get(s) || '').split(',').map(Number); return a.length >= 2 && !isNaN(a[0]) ? [a[0], a[1], a[2] || 0] : null; };
loadImages(() => {
  findBands(); buildZones(); buildGrid(); buildMetres(); defaultPeople(); snowInit(); findGlints();
  const zq = Q.get('zoom');
  if (zq === 'fit' || (!zq && (innerWidth < MAPW * 0.8 || innerHeight < MAPH * 0.8))) fit = true; else zoom = +(zq || 1);
  resize();
  const at = (Q.get('at') || '').split(',').map(Number);
  if (at.length === 2 && !isNaN(at[0])) centreOn(at[0], at[1]); else centreOn(MAPW / 2, MAPH / 2);
  for (let s = 0; s < Math.min(time, 30); s += 1 / 30) { snowStep(1 / 30, s); stepSmoke(1 / 30); }
  if (show.colliders) buildColliders();
  if (show.nav) buildNav();
  cursor = qpt('cursor');
  if (show.los) buildLos(qpt('los') || cursor || [o0[0], o0[1], 0], +(Q.get('losstep') || 2));
  if (show.paths) routesToObjectives();
  const ag = qpt('agent'), tg = qpt('target');
  if (ag) Object.assign(agent, { u: ag[0], v: ag[1], layer: ag[2] });
  if (tg) { agentGo(...tg); const steps = +(Q.get('walk') || 0); for (let i = 0; i < steps; i++) agentStep(1 / 30); }
  if (SHOT && Q.get('hud') === '0') document.body.classList.add('nohud');
  panel();
  window.__arena = { ready: true, render, show, level: L, LV, people: () => people, unproj, agent, toggle,
                     stats: () => ({ composes, frame: curF, time, compose_ms: +(prof.draw / Math.max(1, composes)).toFixed(2) }), setTime: t => { time = t; } };
  if (SHOT && paused) render(); else requestAnimationFrame(frame);
});
})();

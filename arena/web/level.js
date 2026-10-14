// Hushfall Crossing as a game level: queries on level.json, the same code as arena/game.py.
//   const lv = ArenaLevel.load(levelJson);            // browser: window.ArenaLevel; node: require('./level.js')
//   lv.findPath([u, v, layer], [u, v, layer], r)      // {points: [[u, v, z, layer]], length, grid} or null
//   lv.los([u, v, layer], [u, v, layer], 'sight')     // eye to eye ('shot': chest to chest)
//   lv.move(unit, du, dv)                             // unit = {u, v, layer, r}: slides through the colliders
// A position is (u, v, layer) in metres: layer 0 is the height field (ground, and the terrace where the floor is
// higher than rules.high_ground_z), layer 1 the bridge deck.
(function (root, factory) {
  if (typeof module === 'object' && module.exports) module.exports = factory();
  else root.ArenaLevel = factory();
})(typeof self !== 'undefined' ? self : this, function () {
'use strict';
const R2 = Math.SQRT2, BUCKET = 2.0;
const NB8 = [[0, 1, 1], [0, -1, 1], [1, 0, 1], [-1, 0, 1], [1, 1, R2], [1, -1, R2], [-1, 1, R2], [-1, -1, R2]];

function bytes(s) {
  if (typeof Buffer !== 'undefined' && typeof atob === 'undefined') return new Uint8Array(Buffer.from(s, 'base64'));
  const b = atob(s), out = new Uint8Array(b.length);
  for (let i = 0; i < b.length; i++) out[i] = b.charCodeAt(i);
  return out;
}

// a binary heap of keys (arrays compared element by element, as Python compares the tuples game.py pushes)
function less(a, b) { for (let i = 0; i < a.length; i++) { if (a[i] < b[i]) return true; if (a[i] > b[i]) return false; } return false; }
class Heap {
  constructor() { this.a = []; }
  get size() { return this.a.length; }
  push(key) {
    const a = this.a; a.push(key); let i = a.length - 1;
    while (i > 0) { const j = (i - 1) >> 1; if (!less(a[i], a[j])) break; [a[i], a[j]] = [a[j], a[i]]; i = j; }
  }
  pop() {
    const a = this.a, top = a[0], last = a.pop();
    if (a.length) {
      a[0] = last; let i = 0;
      for (;;) {
        const l = 2 * i + 1, r = l + 1; let m = i;
        if (l < a.length && less(a[l], a[m])) m = l;
        if (r < a.length && less(a[r], a[m])) m = r;
        if (m === i) break; [a[i], a[m]] = [a[m], a[i]]; i = m;
      }
    }
    return top;
  }
}

// ---------------------------------------------------------------- shape geometry (game.py has the same)
function bbox(s) {
  if (s.shape === 'circle') return [s.u - s.r, s.v - s.r, s.u + s.r, s.v + s.r];
  if (s.shape === 'box') {
    const c = Math.abs(Math.cos(s.a)), sn = Math.abs(Math.sin(s.a));
    const eu = s.hu * c + s.hv * sn, ev = s.hu * sn + s.hv * c;
    return [s.u - eu, s.v - ev, s.u + eu, s.v + ev];
  }
  return [Math.min(s.u0, s.u1) - s.t, Math.min(s.v0, s.v1) - s.t, Math.max(s.u0, s.u1) + s.t, Math.max(s.v0, s.v1) + s.t];
}
// [distance, normal u, normal v] from (u, v) to a shape; (pu, pv) picks the side of a zero-thickness wall
function push(s, u, v, pu, pv) {
  if (s.shape === 'circle') {
    let du = u - s.u, dv = v - s.v, L = Math.hypot(du, dv);
    if (L < 1e-9) { du = pu - s.u; dv = pv - s.v; L = Math.max(1e-9, Math.hypot(du, dv)); }
    return [L - s.r, du / L, dv / L];
  }
  if (s.shape === 'box') {
    const c = Math.cos(s.a), sn = Math.sin(s.a), du = u - s.u, dv = v - s.v;
    const x = du * c + dv * sn, y = -du * sn + dv * c, qx = Math.abs(x) - s.hu, qy = Math.abs(y) - s.hv;
    let nx, ny, d;
    if (qx > 0 || qy > 0) {
      const ox = Math.max(qx, 0) * (x < 0 ? -1 : 1), oy = Math.max(qy, 0) * (y < 0 ? -1 : 1), L = Math.hypot(ox, oy);
      nx = ox / L; ny = oy / L; d = L;
    } else if (qx > qy) { nx = x < 0 ? -1 : 1; ny = 0; d = qx; } else { nx = 0; ny = y < 0 ? -1 : 1; d = qy; }
    return [d, nx * c - ny * sn, nx * sn + ny * c];
  }
  const eu = s.u1 - s.u0, ev = s.v1 - s.v0, L2 = eu * eu + ev * ev;
  const t = L2 < 1e-12 ? 0 : Math.min(1, Math.max(0, ((u - s.u0) * eu + (v - s.v0) * ev) / L2));
  const cu = s.u0 + t * eu, cv = s.v0 + t * ev, du = u - cu, dv = v - cv, L = Math.hypot(du, dv);
  if (L < 1e-6) {
    let nu = -ev, nv = eu;
    if ((pu - cu) * nu + (pv - cv) * nv < 0) { nu = -nu; nv = -nv; }
    const n = Math.max(1e-9, Math.hypot(nu, nv));
    return [-s.t, nu / n, nv / n];
  }
  return [L - s.t, du / L, dv / L];
}
const dist = (s, u, v) => push(s, u, v, u, v)[0];
// does the 3D segment A -> B pass through the shape's prism (a seg is taken as its box)
function segHits(s, A, B) {
  const du = B[0] - A[0], dv = B[1] - A[1];
  let t0, t1;
  if (s.shape === 'circle') {
    const fu = A[0] - s.u, fv = A[1] - s.v, a = du * du + dv * dv, b = 2 * (fu * du + fv * dv);
    const c = fu * fu + fv * fv - s.r * s.r;
    if (a < 1e-12) { if (c > 0) return false; t0 = 0; t1 = 1; }
    else {
      const disc = b * b - 4 * a * c;
      if (disc < 0) return false;
      const sq = Math.sqrt(disc); t0 = (-b - sq) / (2 * a); t1 = (-b + sq) / (2 * a);
    }
  } else {
    let cu, cv, hu, hv, ang;
    if (s.shape === 'box') { cu = s.u; cv = s.v; hu = s.hu; hv = s.hv; ang = s.a; }
    else {
      cu = (s.u0 + s.u1) / 2; cv = (s.v0 + s.v1) / 2; ang = Math.atan2(s.v1 - s.v0, s.u1 - s.u0);
      hu = Math.hypot(s.u1 - s.u0, s.v1 - s.v0) / 2 + s.t; hv = Math.max(s.t, 1e-3);
    }
    const c = Math.cos(ang), sn = Math.sin(ang);
    const ox = (A[0] - cu) * c + (A[1] - cv) * sn, oy = -(A[0] - cu) * sn + (A[1] - cv) * c;
    const dx = du * c + dv * sn, dy = -du * sn + dv * c;
    t0 = -1e18; t1 = 1e18;
    for (const [o, d, h] of [[ox, dx, hu], [oy, dy, hv]]) {
      if (Math.abs(d) < 1e-12) { if (Math.abs(o) > h) return false; continue; }
      let ta = (-h - o) / d, tb = (h - o) / d;
      if (ta > tb) [ta, tb] = [tb, ta];
      t0 = Math.max(t0, ta); t1 = Math.min(t1, tb);
      if (t0 > t1) return false;
    }
  }
  t0 = Math.max(t0, 0); t1 = Math.min(t1, 1);
  if (t0 > t1) return false;
  const za = A[2] + (B[2] - A[2]) * t0, zb = A[2] + (B[2] - A[2]) * t1;
  return Math.max(za, zb) >= s.z0 && Math.min(za, zb) <= s.z1;
}

class Level {
  constructor(L) {
    this.L = L;
    const R = L.rules, n = L.nav;
    this.step = R.max_step; this.agentH = R.agent_height; this.eye = R.eye_height; this.chest = R.chest_height;
    this.high = R.high_ground_z;
    this.nu = n.nu; this.nv = n.nv; this.cell = n.cell; this.u0 = n.u0; this.v0 = n.v0; this.N = n.nu * n.nv;
    const q = n.clear_q;
    this.clear = [n.hf.clear, n.deck.clear].map(s => Float64Array.from(bytes(s), x => x * q));
    this.surf = [bytes(n.hf.surf), bytes(n.deck.surf)];
    const zb = bytes(n.hf.z_cm);
    const zi = new Int16Array(zb.buffer, zb.byteOffset, zb.byteLength / 2);
    this.z = Float64Array.from(zi, x => x / 100);
    this.dk = n.deck;
    this.rampBit = n.surfaces.ramp_bit;
    this.links = new Map();
    for (const lk of n.links) for (const [a, b] of (lk.pairs || [])) {
      if (!this.links.has(a)) this.links.set(a, []); this.links.get(a).push(this.N + b);
      if (!this.links.has(this.N + b)) this.links.set(this.N + b, []); this.links.get(this.N + b).push(a);
    }
    this.shapes = L.colliders.shapes;
    this.bu0 = this.u0 - 8; this.bv0 = this.v0 - 8;
    this.bnu = Math.ceil((this.nu * this.cell + 16) / BUCKET); this.bnv = Math.ceil((this.nv * this.cell + 16) / BUCKET);
    this.buckets = Array.from({ length: this.bnu * this.bnv }, () => []);
    this.shapes.forEach((s, k) => {
      const [x0, y0, x1, y1] = bbox(s);
      for (let bi = this.bi(y0, this.bv0, this.bnv); bi <= this.bi(y1, this.bv0, this.bnv); bi++)
        for (let bj = this.bi(x0, this.bu0, this.bnu); bj <= this.bi(x1, this.bu0, this.bnu); bj++) this.buckets[bi * this.bnu + bj].push(k);
    });
    this.stamp = new Int32Array(this.shapes.length); this.stampN = 0;
  }
  bi(x, x0, n) { return Math.min(n - 1, Math.max(0, Math.floor((x - x0) / BUCKET))); }

  // ------------------------------------------------------------ the floor
  deckZ(v) { const d = this.dk, t = Math.min(1, Math.max(0, (v - d.v0) / (d.v1 - d.v0))); return d.z0 + (d.z1 - d.z0) * t; }
  hfZ(u, v) {
    const fi = (v - this.v0) / this.cell - 0.5, fj = (u - this.u0) / this.cell - 0.5;
    const i = Math.min(this.nv - 2, Math.max(0, Math.floor(fi))), j = Math.min(this.nu - 2, Math.max(0, Math.floor(fj)));
    const a = Math.min(1, Math.max(0, fi - i)), b = Math.min(1, Math.max(0, fj - j)), k = i * this.nu + j, z = this.z;
    return z[k] * (1 - a) * (1 - b) + z[k + this.nu] * a * (1 - b) + z[k + 1] * (1 - a) * b + z[k + this.nu + 1] * a * b;
  }
  floorZ(u, v, layer) { return layer === 1 ? this.deckZ(v) : this.hfZ(u, v); }
  levelOf(u, v, layer) { return layer === 1 ? 2 : (this.hfZ(u, v) >= this.high ? 1 : 0); }
  inDeck(u, v) { const d = this.dk; return Math.abs(u) <= d.half_width && v >= d.v0 && v <= d.v1; }
  cellOf(u, v) {
    const i = Math.floor((v - this.v0) / this.cell), j = Math.floor((u - this.u0) / this.cell);
    return (i < 0 || j < 0 || i >= this.nv || j >= this.nu) ? -1 : i * this.nu + j;
  }
  centre(k) { k %= this.N; const i = Math.floor(k / this.nu), j = k - i * this.nu; return [this.u0 + (j + 0.5) * this.cell, this.v0 + (i + 0.5) * this.cell]; }
  nodeZ(node) { return node >= this.N ? this.deckZ(this.centre(node)[1]) : this.z[node]; }
  clearAt(u, v, layer) {
    const c = this.clear[layer], fi = (v - this.v0) / this.cell - 0.5, fj = (u - this.u0) / this.cell - 0.5;
    const i = Math.floor(fi), j = Math.floor(fj);
    if (i < 0 || j < 0 || i >= this.nv - 1 || j >= this.nu - 1) return 0;
    const a = fi - i, b = fj - j, k = i * this.nu + j;
    return c[k] * (1 - a) * (1 - b) + c[k + this.nu] * a * (1 - b) + c[k + 1] * (1 - a) * b + c[k + this.nu + 1] * a * b;
  }
  snap(u, v, layer, r, reach = 1.5) {
    const k0 = this.cellOf(u, v);
    if (k0 < 0) return -1;
    const i0 = Math.floor(k0 / this.nu), j0 = k0 - i0 * this.nu, c = this.clear[layer], n = Math.ceil(reach / this.cell);
    let best = -1, bd = 1e9;
    for (let i = Math.max(0, i0 - n); i < Math.min(this.nv, i0 + n + 1); i++)
      for (let j = Math.max(0, j0 - n); j < Math.min(this.nu, j0 + n + 1); j++) {
        const k = i * this.nu + j;
        if (c[k] < r) continue;
        const cu = this.u0 + (j + 0.5) * this.cell, cv = this.v0 + (i + 0.5) * this.cell, d = (cu - u) ** 2 + (cv - v) ** 2;
        if (d < bd) { best = k; bd = d; }
      }
    return best < 0 ? -1 : best + layer * this.N;
  }

  // ------------------------------------------------------------ the graph
  neighbours(node, r, out = []) {
    out.length = 0;
    const layer = node >= this.N ? 1 : 0, k = node - layer * this.N, i = Math.floor(k / this.nu), j = k - i * this.nu;
    const c = this.clear[layer], z = this.nodeZ(node), hf = layer === 0;
    for (const [di, dj, w] of NB8) {
      const ii = i + di, jj = j + dj;
      if (ii < 0 || jj < 0 || ii >= this.nv || jj >= this.nu) continue;
      const kk = ii * this.nu + jj;
      if (c[kk] < r) continue;
      if (di && dj && (c[i * this.nu + jj] < r || c[ii * this.nu + j] < r)) continue;
      const z2 = hf ? this.z[kk] : this.deckZ(this.v0 + (ii + 0.5) * this.cell);
      if (Math.abs(z2 - z) > this.step) continue;
      if (hf && (z >= this.high) !== (z2 >= this.high) && !((this.surf[0][k] & this.rampBit) && (this.surf[0][kk] & this.rampBit))) continue;
      out.push([kk + layer * this.N, w * this.cell]);
    }
    for (const nb of this.links.get(node) || []) {
      const l2 = nb >= this.N ? 1 : 0;
      if (this.clear[l2][nb - l2 * this.N] >= r) {
        const a = this.centre(node), b = this.centre(nb);
        out.push([nb, Math.hypot(a[0] - b[0], a[1] - b[1])]);
      }
    }
    return out;
  }
  field(starts, r) {           // Dijkstra: grid distance (m) to every node (Infinity where unreachable)
    const dist = new Float64Array(2 * this.N).fill(Infinity), h = new Heap(), nb = [];
    for (const s of starts) if (s >= 0) { dist[s] = 0; h.push([0, s]); }
    while (h.size) {
      const [d, n] = h.pop();
      if (d > dist[n]) continue;
      for (const [m, w] of this.neighbours(n, r, nb)) { const nd = d + w; if (nd < dist[m]) { dist[m] = nd; h.push([nd, m]); } }
    }
    return dist;
  }
  descend(dist, node, r) {
    const out = [node], nb = [];
    while (dist[node] > 0) {
      let best = -1, bd = dist[node];
      for (const [m, w] of this.neighbours(node, r, nb)) if (dist[m] + w <= bd + 1e-9 && dist[m] < dist[node]) { best = m; bd = dist[m] + w; }
      if (best < 0) return null;
      node = best; out.push(node);
    }
    return out.reverse();
  }
  astar(s, g, r) {
    if (s < 0 || g < 0) return null;
    const [gu, gv] = this.centre(g);
    const H = n => { const [u, v] = this.centre(n), a = Math.abs(u - gu), b = Math.abs(v - gv); return Math.max(a, b) + (R2 - 1) * Math.min(a, b); };
    const best = new Map([[s, 0]]), prev = new Map([[s, -1]]), h = new Heap(), nb = [];
    h.push([H(s), 0, s]);
    while (h.size) {
      const [, d, n] = h.pop();
      if (n === g) { const path = [n]; while (prev.get(path[path.length - 1]) >= 0) path.push(prev.get(path[path.length - 1])); return path.reverse(); }
      if (d > (best.has(n) ? best.get(n) : 1e18)) continue;
      for (const [m, w] of this.neighbours(n, r, nb)) {
        const nd = d + w;
        if (nd < (best.has(m) ? best.get(m) : 1e18) - 1e-12) { best.set(m, nd); prev.set(m, n); h.push([nd + H(m), nd, m]); }
      }
    }
    return null;
  }
  walkLine(a, b, layer, r) {
    const L = Math.hypot(b[0] - a[0], b[1] - a[1]), n = Math.max(1, Math.ceil(L / 0.1));
    let zp = null, lp = null, rp = null;
    for (let k = 0; k <= n; k++) {
      const t = k / n, u = a[0] + (b[0] - a[0]) * t, v = a[1] + (b[1] - a[1]) * t;
      if (this.clearAt(u, v, layer) < r) return false;
      const z = this.floorZ(u, v, layer);
      if (layer === 0) {
        const kk = this.cellOf(u, v), lv = z >= this.high, rm = !!(this.surf[0][kk] & this.rampBit);
        if (lp !== null && lv !== lp && !(rm && rp)) return false;
        lp = lv; rp = rm;
      }
      if (zp !== null && Math.abs(z - zp) > this.step) return false;
      zp = z;
    }
    return true;
  }
  smooth(nodes, r, start, end) {
    const pts = nodes.map(n => { const c = this.centre(n); return [c[0], c[1], n >= this.N ? 1 : 0]; });
    if (start && start[2] === pts[0][2] && this.walkLine(start, pts[0], start[2], r)) pts[0] = [start[0], start[1], start[2]];
    const e = pts.length - 1;
    if (end && end[2] === pts[e][2] && this.walkLine(pts[e], end, end[2], r)) pts[e] = [end[0], end[1], end[2]];
    const out = [pts[0]];
    let i = 0;
    while (i < pts.length - 1) {
      let j = i + 1, k = i + 2;
      while (k < pts.length && pts.slice(i, k + 1).every(p => p[2] === pts[i][2]) && this.walkLine(pts[i], pts[k], pts[i][2], r)) { j = k; k++; }
      out.push(pts[j]); i = j;
    }
    return out.map(([u, v, ly]) => [u, v, this.floorZ(u, v, ly), ly]);
  }
  static length(p) { let s = 0; for (let i = 1; i < p.length; i++) s += Math.hypot(p[i][0] - p[i - 1][0], p[i][1] - p[i - 1][1], p[i][2] - p[i - 1][2]); return s; }
  findPath(a, b, r = 0.5) {
    const s = this.snap(a[0], a[1], a[2], r), g = this.snap(b[0], b[1], b[2], r);
    const nodes = this.astar(s, g, r);
    if (!nodes) return null;
    const points = this.smooth(nodes, r, a, b);
    let grid = 0;
    for (let i = 1; i < nodes.length; i++) { const p = this.centre(nodes[i - 1]), q = this.centre(nodes[i]); grid += Math.hypot(p[0] - q[0], p[1] - q[1]); }
    return { points, length: Level.length(points), grid, nodes };
  }
  // a path out of a Dijkstra field (fast for many targets from one start)
  pathFrom(dist, b, r, start) {
    const g = this.snap(b[0], b[1], b[2], r);
    if (g < 0 || !isFinite(dist[g])) return null;
    const nodes = this.descend(dist, g, r);
    if (!nodes) return null;
    const points = this.smooth(nodes, r, start, b);
    return { points, length: Level.length(points), grid: dist[g], nodes };
  }

  // ------------------------------------------------------------ line of sight
  los(a, b, mode = 'sight') {
    const h = mode === 'sight' ? this.eye : this.chest;
    return this.clearLine([a[0], a[1], this.floorZ(a[0], a[1], a[2]) + h], [b[0], b[1], this.floorZ(b[0], b[1], b[2]) + h], mode);
  }
  clearLine(A, B, mode = 'sight') {
    const du = B[0] - A[0], dv = B[1] - A[1], dz = B[2] - A[2], L = Math.hypot(du, dv), n = Math.max(1, Math.ceil(L / 0.25));
    for (let k = 0; k <= n; k++) {
      const t = k / n;
      if (t * L < 0.35 || (1 - t) * L < 0.35) continue;
      if (A[2] + dz * t < this.hfZ(A[0] + du * t, A[1] + dv * t) - 0.05) return false;
    }
    const st = ++this.stampN;
    const x0 = Math.min(A[0], B[0]), x1 = Math.max(A[0], B[0]), y0 = Math.min(A[1], B[1]), y1 = Math.max(A[1], B[1]);
    for (let bi = this.bi(y0, this.bv0, this.bnv); bi <= this.bi(y1, this.bv0, this.bnv); bi++)
      for (let bj = this.bi(x0, this.bu0, this.bnu); bj <= this.bi(x1, this.bu0, this.bnu); bj++)
        for (const k of this.buckets[bi * this.bnu + bj]) {
          if (this.stamp[k] === st) continue;
          this.stamp[k] = st;
          const s = this.shapes[k];
          if (s[mode] && segHits(s, A, B)) return false;
        }
    return true;
  }

  // ------------------------------------------------------------ moving a unit
  near(u, v, rad, out = []) {
    out.length = 0;
    const st = ++this.stampN;
    for (let bi = this.bi(v - rad, this.bv0, this.bnv); bi <= this.bi(v + rad, this.bv0, this.bnv); bi++)
      for (let bj = this.bi(u - rad, this.bu0, this.bnu); bj <= this.bi(u + rad, this.bu0, this.bnu); bj++)
        for (const k of this.buckets[bi * this.bnu + bj]) if (this.stamp[k] !== st) { this.stamp[k] = st; out.push(this.shapes[k]); }
    return out;
  }
  blocks(s, z) { return s.move && s.z1 > z + this.step && s.z0 < z + this.agentH; }
  penetration(u, v, layer, r) {
    const z = this.floorZ(u, v, layer);
    let worst = 0;
    for (const s of this.near(u, v, r + 0.1)) if (this.blocks(s, z)) worst = Math.max(worst, r - dist(s, u, v));
    return worst;
  }
  switchLayer(pu, pv, u, v, ly) {
    if (ly === 0 && this.inDeck(u, v) && this.hfZ(u, v) < this.deckZ(v) - 0.6 && this.hfZ(pu, pv) > this.deckZ(pv) - 0.6) return 1;
    if (ly === 1 && !(v >= this.dk.v0 && v <= this.dk.v1)) return 0;
    return ly;
  }
  move(unit, du, dv) {
    const r = unit.r, L = Math.hypot(du, dv), n = Math.max(1, Math.ceil(L / (0.5 * r))), list = [];
    for (let s_ = 0; s_ < n; s_++) {
      const pu = unit.u, pv = unit.v, ly0 = unit.layer;
      let u = pu + du / n, v = pv + dv / n, ly = this.switchLayer(pu, pv, u, v, ly0);
      for (let it = 0; it < 4; it++) {
        const z = this.floorZ(u, v, ly);
        let pushed = false;
        for (const s of this.near(u, v, r + 0.1, list)) {
          if (!this.blocks(s, z)) continue;
          const [d, nu, nv] = push(s, u, v, pu, pv);
          if (d < r) { u += nu * (r - d + 1e-4); v += nv * (r - d + 1e-4); pushed = true; }
        }
        if (!pushed) break;
      }
      ly = this.switchLayer(pu, pv, u, v, ly0);
      if (this.penetration(u, v, ly, r) > 2e-3) break;
      unit.u = u; unit.v = v; unit.layer = ly;
    }
    unit.z = this.floorZ(unit.u, unit.v, unit.layer);
    return unit;
  }
  // the coarse visibility helper: do coarse points a and b (indices into visibility.points) see each other
  coarseSees(a, b) {
    if (!this.vis) { const V = this.L.visibility; this.vis = { n: V.points.length, bits: bytes(V.bits) }; }
    const k = a * this.vis.n + b;
    return !!(this.vis.bits[k >> 3] & (128 >> (k & 7)));
  }
}
return { load: L => new Level(L), Level, dist, push, segHits, bbox };
});

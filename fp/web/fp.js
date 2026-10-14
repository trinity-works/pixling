// fp runtime: a first-person walk through a world built by `python3 -m fp build`, drawn as palette-locked pixel art.
//
// Every frame: sky (direction-space, sky-pinned dither) -> world at a low internal resolution (banded toon light from
// the style's ramps, one sun with a hard shadow map, snow that settles on up-facing faces, headlight spill, stepped fog)
// -> 1 px lines (ropes, wires, grass) -> particles (falling snow, near bokeh flakes, breath) -> post (every pixel snapped
// to the style palette) -> nearest-neighbour upscale by a whole number.
//
// Default render path: texel splatting (texel.js): the shaded world is captured into a cubemap from a probe snapped
// to a 1 m grid and every texel is drawn as a world-space square, so art pixels stay on the surfaces when the camera
// turns, bobs or walks. ?render=screen draws the old way (low-res target, palette snap), which crawls when moving.
//
// URL: ?t=SECONDS jump the auto-walk; &pause=1 freeze time; &card=MESH (+&yaw=DEG&pitch=DEG&dist=M) one asset on a
// snow disc; &h=PIXELS internal height; &motion=gentle|full|off; &look=YAW,PITCH (degrees) override the view.
import * as THREE from './vendor/three.module.min.js';
import { makeAudio } from './audio.js';
import { makeTexelSplat } from './texel.js';

const Q = new URLSearchParams(location.search);
const canvas = document.getElementById('stage');
const audio = makeAudio();
const hintEl = document.getElementById('hint');

// ---------------------------------------------------------------------------------------------------- small helpers
const hex = h => [parseInt(h.slice(1, 3), 16) / 255, parseInt(h.slice(3, 5), 16) / 255, parseInt(h.slice(5, 7), 16) / 255];
const clamp = (x, a, b) => Math.min(b, Math.max(a, x));
const lerp = (a, b, t) => a + (b - a) * t;
const damp = (a, b, rate, dt) => lerp(a, b, 1 - Math.exp(-rate * dt));
const angDamp = (a, b, rate, dt) => { let d = b - a; while (d > Math.PI) d -= 2 * Math.PI; while (d < -Math.PI) d += 2 * Math.PI; return a + d * (1 - Math.exp(-rate * dt)); };
const smooth = t => t * t * (3 - 2 * t);
const DEG = Math.PI / 180;
function mulberry(seed) { return () => { seed |= 0; seed = seed + 0x6D2B79F5 | 0; let t = Math.imul(seed ^ seed >>> 15, 1 | seed); t = t + Math.imul(t ^ t >>> 7, 61 | t) ^ t; return ((t ^ t >>> 14) >>> 0) / 4294967296; }; }

const GLSL_COMMON = /* glsl */`
float bayer4(vec2 p) {
  ivec2 q = ivec2(mod(p, 4.0));
  int i = q.x + q.y * 4;
  int m[16] = int[16](0, 8, 2, 10, 12, 4, 14, 6, 3, 11, 1, 9, 15, 7, 13, 5);
  return (float(m[i]) + 0.5) / 16.0;
}
float hash12(vec2 p) { vec3 p3 = fract(vec3(p.xyx) * 0.1031); p3 += dot(p3, p3.yzx + 33.33); return fract((p3.x + p3.y) * p3.z); }
float vnoise(vec2 p) {
  vec2 i = floor(p), f = fract(p); vec2 u = f * f * (3.0 - 2.0 * f);
  return mix(mix(hash12(i), hash12(i + vec2(1, 0)), u.x), mix(hash12(i + vec2(0, 1)), hash12(i + vec2(1, 1)), u.x), u.y);
}
// particles in art pixels: uArt device pixels per art pixel, uRes the target size; snap a clip position to that grid
uniform float uArt; uniform vec2 uRes;
vec4 artSnap(vec4 clip) {
  if (uArt < 1.5) return clip;
  vec2 px = (clip.xy / clip.w * 0.5 + 0.5) * uRes;
  px = (floor(px / uArt) + 0.5) * uArt;
  clip.xy = (px / uRes * 2.0 - 1.0) * clip.w;
  return clip;
}
float fbm(vec2 p) { float a = 0.5, s = 0.0; for (int k = 0; k < 5; k++) { s += a * vnoise(p); p = p * 2.03 + vec2(17.1, 9.7); a *= 0.5; } return s; }
`;

// ---------------------------------------------------------------------------------------------------- load
const world = await (await fetch('world.json')).json();
const bin = await (await fetch('world.bin')).arrayBuffer();
const S = world.style;
const view = (T, ref) => new T(bin, ref[0], ref[1]);

// ---------------------------------------------------------------------------------------------------- renderer
const renderer = new THREE.WebGLRenderer({ canvas, antialias: false, alpha: false, stencil: true, powerPreference: 'high-performance',
  preserveDrawingBuffer: Q.has('shot') });
renderer.autoClear = false;
renderer.outputColorSpace = THREE.LinearSRGBColorSpace;   // palette hexes go to the screen untouched
THREE.ColorManagement.enabled = false;
const PIXEL_H = +(Q.get('h') || S.pixel.height);
let W = 0, H = 0, SCALE = 1;
const rt = new THREE.WebGLRenderTarget(4, 4, { minFilter: THREE.NearestFilter, magFilter: THREE.NearestFilter,
  depthBuffer: true, depthTexture: new THREE.DepthTexture(4, 4) });
const camera = new THREE.PerspectiveCamera(S.camera.fov, 1, S.camera.near, S.camera.far);
camera.rotation.order = 'YXZ';

// ---------------------------------------------------------------------------------------------------- palette, ramps
const MATS = world.materials;
const MAT = Object.fromEntries(MATS.map((m, i) => [m, i]));
const RAMP_W = 256;
const rampData = new Uint8Array(RAMP_W * MATS.length * 4);
const palette = new Map();
MATS.forEach((name, row) => {
  const stops = S.ramps[name];
  for (let x = 0; x < RAMP_W; x++) {
    const v = x / (RAMP_W - 1);
    let c = stops[0][1];
    for (const [p, h] of stops) if (v >= p) c = h;
    const rgb = hex(c);
    const o = (row * RAMP_W + x) * 4;
    rampData[o] = rgb[0] * 255; rampData[o + 1] = rgb[1] * 255; rampData[o + 2] = rgb[2] * 255; rampData[o + 3] = 255;
  }
  for (const [, h] of stops) palette.set(h.toLowerCase(), hex(h));
});
const addPal = h => palette.set(h.toLowerCase(), hex(h));
S.sky.stops.forEach(s => addPal(s[1])); S.sky.cumulus.layers.forEach(l => l.tones.forEach(addPal)); S.sky.accent.tones.forEach(addPal);
S.sky.ridges.forEach(r => { addPal(r.color); addPal(r.rim); }); addPal(S.fog.color); addPal(S.fog.color_far);
(S.palette_extra || []).forEach(addPal); addPal(S.particles.snow.color); addPal(S.particles.bokeh.color); addPal(S.particles.breath.color);
const rampTex = new THREE.DataTexture(rampData, RAMP_W, MATS.length, THREE.RGBAFormat);
rampTex.magFilter = rampTex.minFilter = THREE.NearestFilter; rampTex.needsUpdate = true;
const PAL = [...palette.values()];
if (PAL.length > 96) console.warn('fp: palette has', PAL.length, 'colours; post pass reads 96');
const emissive = new Float32Array(32); (S.emissive || []).forEach(n => { if (n in MAT) emissive[MAT[n]] = 1; });

// ---------------------------------------------------------------------------------------------------- sun + shadow map
const sunAz = S.sun.azimuth * DEG, sunEl = S.sun.elevation * DEG;
const SUN = new THREE.Vector3(Math.sin(sunAz) * Math.cos(sunEl), Math.sin(sunEl), -Math.cos(sunAz) * Math.cos(sunEl)).normalize();
const maxTex = renderer.capabilities.maxTextureSize;
const MOBILE = /Mobi|Android/i.test(navigator.userAgent) || navigator.maxTouchPoints > 1;
const SHADOW_N = +(Q.get('shadow') || (maxTex >= 4096 && !MOBILE ? 4096 : 2048));
const shadowRT = new THREE.WebGLRenderTarget(SHADOW_N, SHADOW_N, { depthBuffer: true, format: THREE.RedFormat,
  depthTexture: new THREE.DepthTexture(SHADOW_N, SHADOW_N, THREE.UnsignedIntType) });
shadowRT.depthTexture.minFilter = shadowRT.depthTexture.magFilter = THREE.NearestFilter;
const shadowCam = new THREE.OrthographicCamera(-1, 1, 1, -1, 0.1, 1000);
const shadowMat = new THREE.Matrix4();
function fitShadow(lo, hi) {
  const c = new THREE.Vector3().addVectors(lo, hi).multiplyScalar(0.5);
  shadowCam.position.copy(c).addScaledVector(SUN, 400);
  shadowCam.up.set(0, 1, 0);
  shadowCam.lookAt(c);
  shadowCam.updateMatrixWorld();
  const inv = shadowCam.matrixWorldInverse;
  const b = new THREE.Box3();
  for (let i = 0; i < 8; i++) b.expandByPoint(new THREE.Vector3(i & 1 ? hi.x : lo.x, i & 2 ? hi.y : lo.y, i & 4 ? hi.z : lo.z).applyMatrix4(inv));
  shadowCam.left = b.min.x; shadowCam.right = b.max.x; shadowCam.bottom = b.min.y; shadowCam.top = b.max.y;
  shadowCam.near = -b.max.z - 50; shadowCam.far = -b.min.z + 50;
  shadowCam.updateProjectionMatrix();
  shadowMat.multiplyMatrices(shadowCam.projectionMatrix, shadowCam.matrixWorldInverse);
}

// ---------------------------------------------------------------------------------------------------- world material
const L = S.light, SN = S.snow, FG = S.fog;
const NSPOT = 6;
const spots = (world.lights || []).slice(0, NSPOT);
if ((world.lights || []).length > NSPOT) console.warn('fp: only the first', NSPOT, 'lamps light the scene');
if (MATS.length > 32) console.warn('fp: more than 32 materials; emissive and tone jitter read the first 32');
const spotPos = Array.from({ length: NSPOT }, (_, i) => new THREE.Vector3(...(spots[i] ? spots[i].pos : [0, -999, 0])));
const spotDir = Array.from({ length: NSPOT }, (_, i) => new THREE.Vector3(...(spots[i] ? spots[i].dir : [0, -1, 0])));
const spotPar = Array.from({ length: NSPOT }, (_, i) => new THREE.Vector4(spots[i] ? Math.cos(spots[i].angle * DEG) : 2,
  spots[i] ? spots[i].range : 1, spots[i] ? spots[i].power : 0, spots[i] ? (MAT[spots[i].ramp || 'glow'] ?? MAT.glow ?? 0) : 0));
const fogC = new THREE.Vector3(...hex(FG.color)), fogFar = new THREE.Vector3(...hex(FG.color_far));
const jitter = new Float32Array(32); Object.entries(S.tone_jitter || {}).forEach(([m, k]) => { if (m in MAT) jitter[MAT[m]] = k; });
const worldUniforms = {
  uRamps: { value: rampTex }, uNMats: { value: MATS.length }, uEmissive: { value: emissive },
  uSun: { value: SUN }, uLight: { value: new THREE.Vector4(L.ambient, L.sky, L.sun, L.ao) },
  uTerm: { value: new THREE.Vector2(...L.terminator) },
  uShadowMap: { value: shadowRT.depthTexture }, uShadowMat: { value: shadowMat }, uShadowTexel: { value: 0 },
  uBias: { value: L.shadow_bias },
  uSnow: { value: new THREE.Vector4(MAT[SN.ramp], SN.up, SN.noise, SN.noise_scale) },
  uRim: { value: new THREE.Vector4(L.rim.strength, L.rim.power, L.rim.threshold, MAT[L.rim.ramp]) },
  uFog: { value: new THREE.Vector4(FG.near, FG.far, FG.steps, FG.max) }, uFogC: { value: fogC }, uFogFar: { value: fogFar },
  uSpotPos: { value: spotPos }, uSpotDir: { value: spotDir }, uSpotPar: { value: spotPar }, uGlow: { value: MAT.glow ?? 0 },
  uJitter: { value: jitter }, uProbe: { value: new THREE.Vector4() }, uSnowFlat: { value: SN.flatten ?? 0 },
  uLineValue: { value: S.line_value ?? 0.55 },
};
const WORLD_VERT = /* glsl */`
attribute vec4 attr;
varying vec3 vWorld; varying vec3 vNormal; varying float vMat; varying float vSnow; varying float vAO; varying float vTone;
void main() {
  mat4 M = modelMatrix;
  vTone = 0.0;
#ifdef USE_INSTANCING
  M = modelMatrix * instanceMatrix;
  // each placed copy sits a little lighter or darker (by its position), so a stand of one tree isn't a stamp
  vTone = fract(sin(dot(instanceMatrix[3].xz, vec2(12.9898, 78.233))) * 43758.5453) * 2.0 - 1.0;
#endif
  vec4 wp = M * vec4(position, 1.0);
  vWorld = wp.xyz;
  vNormal = normalize(mat3(M) * normal);
  vMat = attr.x; vSnow = attr.y / 255.0; vAO = attr.z / 255.0;
  gl_Position = projectionMatrix * viewMatrix * wp;
}`;
const SHADE_COMMON = /* glsl */`
uniform sampler2D uRamps; uniform float uNMats; uniform float uEmissive[32];
uniform vec3 uSun; uniform vec4 uLight; uniform vec2 uTerm;
uniform sampler2D uShadowMap; uniform mat4 uShadowMat; uniform float uBias;
uniform vec4 uSnow; uniform vec4 uRim; uniform vec4 uFog; uniform vec3 uFogC; uniform vec3 uFogFar;
uniform vec3 uSpotPos[6]; uniform vec3 uSpotDir[6]; uniform vec4 uSpotPar[6]; uniform float uGlow; uniform float uJitter[32];
uniform float uSnowFlat;
uniform vec4 uProbe;      // capturing a texel probe: xyz origin, w = 1; alpha then carries the Chebyshev distance
float probeA(vec3 wp) { vec3 d = abs(wp - uProbe.xyz); return uProbe.w > 0.5 ? max(d.x, max(d.y, d.z)) : 1.0; }
vec3 ramp(float mat, float v) { return texture2D(uRamps, vec2(clamp(v, 0.0, 0.999), (mat + 0.5) / uNMats)).rgb; }
float shadowAt(vec3 wp, vec3 n, float ndl) {
  vec4 sp = uShadowMat * vec4(wp + n * 0.07, 1.0);
  vec3 c = sp.xyz / sp.w * 0.5 + 0.5;
  if (c.x < 0.0 || c.x > 1.0 || c.y < 0.0 || c.y > 1.0 || c.z > 1.0) return 1.0;
  float b = uBias * (1.0 + 3.0 * (1.0 - clamp(ndl, 0.0, 1.0)));
  return c.z - b > texture2D(uShadowMap, c.xy).r ? 0.0 : 1.0;
}
vec3 fogged(vec3 col, vec3 wp) {
  float d = length(cameraPosition - wp);
  float f = clamp((d - uFog.x) / (uFog.y - uFog.x), 0.0, 1.0);
  f = floor(f * uFog.z + 0.5) / uFog.z;
  return mix(col, mix(uFogC, uFogFar, f), f * uFog.w);
}
// lamp spill: summed per ramp; returns (strength, ramp) of the ramp that gets the most light here
vec2 spotLight(vec3 wp, vec3 n) {
  float g0 = 0.0, g1 = 0.0, r0 = -1.0, r1 = -1.0;
  for (int i = 0; i < 6; i++) {
    if (uSpotPar[i].z <= 0.0) continue;                       // an empty slot
    vec3 d = wp - uSpotPos[i]; float dist = length(d); d /= max(dist, 1e-4);
    float cone = smoothstep(uSpotPar[i].x, mix(uSpotPar[i].x, 1.0, 0.35), dot(d, uSpotDir[i]));
    float fall = clamp(1.0 - dist / uSpotPar[i].y, 0.0, 1.0);
    float g = uSpotPar[i].z * cone * fall * fall * clamp(dot(n, -d) * 1.4 + 0.15, 0.0, 1.0);
    if (r0 < 0.0 || uSpotPar[i].w == r0) { r0 = uSpotPar[i].w; g0 += g; } else { r1 = uSpotPar[i].w; g1 += g; }
  }
  return g1 > g0 ? vec2(g1, r1) : vec2(g0, r0);
}
`;
const WORLD_FRAG = /* glsl */`
${GLSL_COMMON}
${SHADE_COMMON}
varying vec3 vWorld; varying vec3 vNormal; varying float vMat; varying float vSnow; varying float vAO; varying float vTone;
void main() {
  vec3 n = normalize(vNormal);
  if (!gl_FrontFacing) n = -n;
  float mat = floor(vMat + 0.5);
  if (uEmissive[int(mat)] > 0.5) { gl_FragColor = vec4(ramp(mat, 0.5), probeA(vWorld)); return; }
  // snow settles where a face points up enough (world-pinned noise ragged-edges it)
  if (vSnow > 0.0) {
    float nz = vnoise(vWorld.xz / uSnow.w) + 0.5 * vnoise(vWorld.xz / (uSnow.w * 0.37)) - 0.75;
    float need = mix(1.05, uSnow.y, vSnow);
    if (n.y + nz * uSnow.z > need) mat = uSnow.x;
  }
  // a snow field is lit as if nearly flat, so its small drifts don't band: one calm mass, broken only by shadows
  vec3 nl = mat == uSnow.x ? normalize(mix(n, vec3(0.0, 1.0, 0.0), uSnowFlat)) : n;
  float ndl = dot(nl, uSun);
  float lit = smoothstep(uTerm.x, uTerm.y, ndl);
  float sh = lit > 0.0 ? shadowAt(vWorld, n, dot(n, uSun)) : 0.0;
  float v = uLight.x + uLight.y * (0.5 + 0.5 * nl.y) + uLight.z * lit * sh;
  v *= mix(1.0, vAO, uLight.w);
  v += vTone * uJitter[int(mat)];
  vec3 col = ramp(mat, v);
#ifdef DEBUG_SHADOW
  gl_FragColor = vec4(vec3(sh * 0.7 + lit * 0.3), 1.0); return;
#endif
  // rim: faces turned to the low sun, seen edge-on, catch the pink
  vec3 V = normalize(cameraPosition - vWorld);
  vec3 sunH = normalize(vec3(uSun.x, 0.0, uSun.z));
  float rim = pow(1.0 - max(dot(n, V), 0.0), uRim.y) * max(dot(n, sunH), 0.0) * sh * uRim.x;
  rim *= 1.0 - smoothstep(uFog.x, mix(uFog.x, uFog.y, 0.35), length(cameraPosition - vWorld));
  if (rim > uRim.z && mat != uSnow.x) col = ramp(uRim.w, (rim - uRim.z) / (1.0 - uRim.z));
  // lamp spill (headlights mint, tail lights pink): banded, the fringe dithered
  vec2 g = spotLight(vWorld, n);
  if (g.x > 0.04) {
    vec3 wq = floor(vWorld / 0.05);                 // the fringe's dither is pinned to the world, not to a probe or the screen
    float gd = g.x + (bayer4(vec2(wq.x + wq.y, wq.z + wq.y)) - 0.5) * 0.30;
    if (gd > 0.16) col = ramp(g.y, clamp((gd - 0.16) * 0.9, 0.0, 0.999));
  }
  gl_FragColor = vec4(fogged(col, vWorld), probeA(vWorld));
}`;
const worldMat = new THREE.ShaderMaterial({ uniforms: worldUniforms, vertexShader: WORLD_VERT, fragmentShader: WORLD_FRAG,
  defines: Q.get('debug') === 'shadow' ? { DEBUG_SHADOW: 1 } : {} });
const LINE_VERT = /* glsl */`
attribute float lmat; varying vec3 vWorld; varying float vMat;
void main() {
  vec4 wp = modelMatrix * vec4(position, 1.0); vWorld = wp.xyz; vMat = lmat;
  gl_Position = projectionMatrix * viewMatrix * wp;
}`;
const LINE_FRAG = /* glsl */`
${GLSL_COMMON}
${SHADE_COMMON}
uniform float uLineValue;
varying vec3 vWorld; varying float vMat;
uniform vec4 uRimL;
void main() {
  vec3 col = ramp(floor(vMat + 0.5), uLineValue);
  // wires and ropes seen against the low sun catch its pink, fading with distance
  vec3 toP = normalize(vWorld - cameraPosition);
  vec3 sunH = normalize(vec3(uSun.x, 0.0, uSun.z));
  float rl = pow(max(dot(toP, sunH), 0.0), uRimL.y) * (1.0 - smoothstep(uFog.x * 0.5, uFog.x * 1.5, length(cameraPosition - vWorld)));
  if (rl > uRimL.x) col = ramp(uRim.w, uRimL.z);
  vec2 g = spotLight(vWorld, vec3(0.0, 1.0, 0.0));
  if (g.x > 0.25) col = ramp(g.y, 0.4);
  gl_FragColor = vec4(fogged(col, vWorld), -probeA(vWorld));   // negative: a probe's bake keeps line pixels
  if (uProbe.w < 0.5) gl_FragColor.a = 1.0;
}`;
worldUniforms.uRimL = { value: new THREE.Vector4(...(S.light.rim_lines || [0.72, 6.0, 0.45, 0])) };
const lineMat = new THREE.ShaderMaterial({ uniforms: worldUniforms, vertexShader: LINE_VERT, fragmentShader: LINE_FRAG });

// ---------------------------------------------------------------------------------------------------- meshes
const scene = new THREE.Scene();
const lineScene = new THREE.Scene();         // ropes, wires, grass: 1 px lines
const geoms = {};
function geometry(key) {
  if (geoms[key]) return geoms[key];
  const m = world.meshes[key];
  const g = new THREE.BufferGeometry();
  g.setAttribute('position', new THREE.BufferAttribute(view(Float32Array, m.pos), 3));
  g.setAttribute('normal', new THREE.BufferAttribute(view(Int8Array, m.nrm), 4, true));
  g.setAttribute('attr', new THREE.BufferAttribute(view(Uint8Array, m.attr), 4, false));
  g.setIndex(new THREE.BufferAttribute(view(Uint32Array, m.idx), 1));
  g.boundingBox = new THREE.Box3(new THREE.Vector3(...m.bounds[0]), new THREE.Vector3(...m.bounds[1]));
  g.boundingSphere = g.boundingBox.getBoundingSphere(new THREE.Sphere());
  return (geoms[key] = g);
}
const CARD = Q.get('card');
const tmpM = new THREE.Matrix4(), tmpQ = new THREE.Quaternion(), tmpS = new THREE.Vector3(), tmpP = new THREE.Vector3();
const UP = new THREE.Vector3(0, 1, 0);
function instanceMesh(key, places, casts) {
  const im = new THREE.InstancedMesh(geometry(key), worldMat, places.length);
  places.forEach(([x, y, z, yaw, s], i) => {
    tmpQ.setFromAxisAngle(UP, yaw * DEG); tmpS.set(s, s, s); tmpP.set(x, y, z);
    im.setMatrixAt(i, tmpM.compose(tmpP, tmpQ, tmpS));
  });
  im.computeBoundingSphere();
  if (casts) im.layers.enable(1);
  scene.add(im);
  return im;
}
let worldLo, worldHi;
if (!CARD) {
  for (const k of ['terrain', 'slabs']) {
    const mesh = new THREE.Mesh(geometry(k), worldMat);
    mesh.layers.enable(1);
    scene.add(mesh);
  }
  for (const it of world.instances) instanceMesh(it.mesh, it.at, it.shadow);
  if (world.lines.verts) {
    const g = new THREE.BufferGeometry();
    g.setAttribute('position', new THREE.BufferAttribute(view(Float32Array, world.lines.pos), 3));
    g.setAttribute('lmat', new THREE.BufferAttribute(view(Uint8Array, world.lines.mat), 1, false));
    const ls = new THREE.LineSegments(g, lineMat);
    ls.frustumCulled = false;
    lineScene.add(ls);
  }
  // the shadow box: the walkable bounds padded all round, from the lowest ground to the tallest placed asset
  const [x0, z0, x1, z1] = world.bounds, pad = 30;
  let ylo = Infinity, yhi = -Infinity, top = 0;
  const hx = new Float32Array(bin, world.heights.xs[0], world.heights.xs[1]), hz = new Float32Array(bin, world.heights.zs[0], world.heights.zs[1]);
  const hy = new Float32Array(bin, world.heights.y[0], world.heights.y[1]);
  for (let k = 0; k < hz.length; k++) for (let i = 0; i < hx.length; i++) {
    if (hx[i] < x0 - pad || hx[i] > x1 + pad || hz[k] < z0 - pad || hz[k] > z1 + pad) continue;
    const y = hy[k * hx.length + i]; ylo = Math.min(ylo, y); yhi = Math.max(yhi, y);
  }
  for (const it of world.instances) for (const a of it.at) top = Math.max(top, world.meshes[it.mesh].bounds[1][1] * a[4]);
  worldLo = new THREE.Vector3(x0 - pad, ylo - 1, z0 - pad); worldHi = new THREE.Vector3(x1 + pad, yhi + top + 1, z1 + pad);
} else {
  // one asset on a disc of snow, lit by the scene's sun
  const disc = new THREE.CircleGeometry(9, 40).rotateX(-Math.PI / 2);
  const n = disc.attributes.position.count;
  disc.setAttribute('attr', new THREE.BufferAttribute(new Uint8Array(n * 4).map((_, i) => [MAT.snow, 255, 255, 0][i % 4]), 4));
  const dm = new THREE.Mesh(disc, worldMat); dm.layers.enable(1); scene.add(dm);
  const it = world.instances.find(i => i.mesh === CARD);
  if (!it && !world.meshes[CARD]) throw new Error('no mesh ' + CARD);
  instanceMesh(CARD, [[0, 0, 0, +(Q.get('turn') || 0), 1]], true);
  const b = world.meshes[CARD].bounds;
  worldLo = new THREE.Vector3(-9, -1, -9); worldHi = new THREE.Vector3(9, b[1][1] + 1, 9);
}
fitShadow(worldLo, worldHi);
const depthMat = new THREE.MeshDepthMaterial();
function renderShadows() {      // the world never moves: one shadow render, again only if the GPU lost it
  shadowCam.layers.set(1);
  scene.overrideMaterial = depthMat;
  renderer.setRenderTarget(shadowRT); renderer.setClearColor(0xffffff, 1); renderer.clear();
  renderer.render(scene, shadowCam);
  scene.overrideMaterial = null; renderer.setRenderTarget(null);
}
renderShadows();
canvas.addEventListener('webglcontextrestored', () => renderShadows());

// ---------------------------------------------------------------------------------------------------- sky
// The sky is a painted panorama (fp/sky.py: cumulus puffs, pink clusters, ridges), drawn behind everything as its own
// layer: each screen pixel looks up the panorama pixel in its direction, so sky pixels are pinned to the sky and keep
// still while the head turns; the clouds drift whole pixels at a time.
const SKYI = world.sky_image;
const skyTex = await new THREE.TextureLoader().loadAsync(SKYI.src);
skyTex.magFilter = skyTex.minFilter = THREE.NearestFilter; skyTex.generateMipmaps = false;
skyTex.wrapS = THREE.RepeatWrapping; skyTex.wrapT = THREE.ClampToEdgeWrapping; skyTex.colorSpace = THREE.NoColorSpace;
const skyUniforms = {
  uInvVP: { value: new THREE.Matrix4() }, uSky: { value: skyTex },
  uMeta: { value: new THREE.Vector4(SKYI.el_min, SKYI.el_max, SKYI.px_deg, 0) },
};
const skyMat = new THREE.ShaderMaterial({
  uniforms: skyUniforms, depthTest: false, depthWrite: false,
  vertexShader: `varying vec2 vNdc; void main() { vNdc = position.xy; gl_Position = vec4(position.xy, 0.0, 1.0); }`,
  fragmentShader: /* glsl */`
uniform mat4 uInvVP; uniform sampler2D uSky; uniform vec4 uMeta;
varying vec2 vNdc;
void main() {
  vec4 p = uInvVP * vec4(vNdc, 1.0, 1.0);
  vec3 dir = normalize(p.xyz / p.w - cameraPosition);
  float az = degrees(atan(dir.x, -dir.z)) + uMeta.w;            // uMeta.w: the drift, in whole panorama pixels
  float el = degrees(asin(clamp(dir.y, -1.0, 1.0)));
  vec2 uv = vec2((az + 180.0) / 360.0, (clamp(el, uMeta.x, uMeta.y - uMeta.z) - uMeta.x) / (uMeta.y - uMeta.x));
  gl_FragColor = vec4(texture2D(uSky, uv).rgb, 1.0);
}`,
});
const fsTri = new THREE.BufferGeometry();
fsTri.setAttribute('position', new THREE.BufferAttribute(new Float32Array([-1, -1, 0, 3, -1, 0, -1, 3, 0]), 3));
const skyScene = new THREE.Scene();
const skyQuad = new THREE.Mesh(fsTri, skyMat); skyQuad.frustumCulled = false; skyScene.add(skyQuad);

// ---------------------------------------------------------------------------------------------------- particles
const rand = mulberry(+(Q.get('seed') || 7));
const artU = { value: 1 }, resU = { value: new THREE.Vector2(1, 1) };   // art-pixel size and target, set in resize()
const PS = S.particles;
function particleMat(kind) {
  return new THREE.ShaderMaterial({
    transparent: true, depthWrite: false,
    uniforms: { uTime: { value: 0 }, uR: { value: kind === 'snow' ? PS.snow.radius : PS.bokeh.far },
      uFall: { value: PS.snow.fall }, uDrift: { value: PS.snow.drift }, uSize: { value: kind === 'snow' ? PS.snow.size : PS.bokeh.size },
      uK: { value: 100 }, uMax: { value: kind === 'snow' ? 4 : PS.bokeh.max_px },
      uColor: { value: new THREE.Vector3(...hex(kind === 'snow' ? PS.snow.color : PS.bokeh.color)) },
      uColor2: { value: new THREE.Vector3(...hex(kind === 'snow' ? (PS.snow.color2 || PS.snow.color) : (PS.bokeh.color2 || PS.bokeh.color))) },
      uAlpha: { value: kind === 'snow' ? PS.snow.alpha : PS.bokeh.alpha }, uNear: { value: PS.bokeh.near },
      uFog: worldUniforms.uFog, uFogC: worldUniforms.uFogC, uArt: artU, uRes: resU },
    vertexShader: /* glsl */`
${GLSL_COMMON}
uniform float uTime, uR, uFall, uDrift, uSize, uK, uMax, uNear;
attribute vec4 seed;
varying float vA; varying float vPx; varying float vTwo;
void main() {
  vec3 p = position;
  vTwo = step(0.5, seed.y);
  float t = uTime;
  p.y -= t * uFall * (0.7 + 0.6 * seed.x);
  p.x += sin(t * (0.3 + seed.y) + seed.z * 6.28) * uDrift + t * uDrift * 0.35;
  p.z += cos(t * (0.25 + seed.x * 0.5) + seed.w * 6.28) * uDrift * 0.6;
  vec3 rel = mod(p - cameraPosition + uR, 2.0 * uR) - uR;
  vec3 wp = cameraPosition + rel;
  vec4 mv = viewMatrix * vec4(wp, 1.0);
  float d = -mv.z;
  float px = uK * uSize * (0.6 + 0.8 * seed.w) / max(d, 0.01);
  vPx = px;
  vA = (d < uNear) ? 0.0 : 1.0;
  gl_PointSize = clamp(floor(px + 0.5), 1.0, uMax) * max(uArt, 1.0);     // whole art pixels
  gl_Position = artSnap(projectionMatrix * mv);
}`,
    fragmentShader: /* glsl */`
uniform vec3 uColor; uniform vec3 uColor2; uniform float uAlpha;
varying float vA; varying float vPx; varying float vTwo;
void main() {
  if (vA < 0.5) discard;
  vec2 c = gl_PointCoord - 0.5;
  if (dot(c, c) > 0.25) discard;
  gl_FragColor = vec4(mix(uColor, uColor2, vTwo), uAlpha);   // half the flakes pale, half teal: one shows on any ground
}`,
  });
}
function particleCloud(kind, count, R) {
  const pos = new Float32Array(count * 3), seed = new Float32Array(count * 4);
  for (let i = 0; i < count; i++) {
    pos[i * 3] = (rand() * 2 - 1) * R; pos[i * 3 + 1] = (rand() * 2 - 1) * R; pos[i * 3 + 2] = (rand() * 2 - 1) * R;
    for (let k = 0; k < 4; k++) seed[i * 4 + k] = rand();
  }
  const g = new THREE.BufferGeometry();
  g.setAttribute('position', new THREE.BufferAttribute(pos, 3));
  g.setAttribute('seed', new THREE.BufferAttribute(seed, 4));
  const pts = new THREE.Points(g, particleMat(kind));
  pts.frustumCulled = false;
  return pts;
}
const fx = new THREE.Scene();
const snowPts = particleCloud('snow', PS.snow.count, PS.snow.radius);
const bokehPts = particleCloud('bokeh', PS.bokeh.count, PS.bokeh.far);
fx.add(snowPts, bokehPts);

// puffs: short-lived soft clouds drawn as one tone with a dithered rim (the breath, the car's exhaust)
const BR = PS.breath;
function puffSystem(color, alpha, max) {
  const pos = new Float32Array(max * 3), info = new Float32Array(max * 3);
  const geo = new THREE.BufferGeometry();
  geo.setAttribute('position', new THREE.BufferAttribute(pos, 3));
  geo.setAttribute('info', new THREE.BufferAttribute(info, 3));
  const mat = new THREE.ShaderMaterial({
    transparent: false, depthWrite: false,
    uniforms: { uK: { value: 100 }, uColor: { value: new THREE.Vector3(...hex(color)) }, uAlpha: { value: alpha }, uTime: { value: 0 },
      uArt: artU, uRes: resU },
    vertexShader: /* glsl */`
${GLSL_COMMON}
uniform float uK; attribute vec3 info; varying float vA; varying float vSeed; varying float vN;
void main() {
  vec4 mv = viewMatrix * vec4(position, 1.0);
  float d = -mv.z;
  vA = info.y; vSeed = info.z;                     // size, strength, a fixed seed per puff
  vN = d > 0.02 ? clamp(floor(uK * info.x / d + 0.5), 1.0, 220.0) : 0.0;     // the puff's size in art pixels
  gl_PointSize = vN * max(uArt, 1.0);
  gl_Position = artSnap(projectionMatrix * mv);
}`,
    fragmentShader: /* glsl */`
${GLSL_COMMON}
uniform vec3 uColor; uniform float uAlpha; uniform float uTime;
varying float vA; varying float vSeed; varying float vN;
void main() {
  vec2 cell = floor(gl_PointCoord * vN);            // the puff's own art pixels: its dither travels with it
  vec2 c = (cell + 0.5) / max(vN, 1.0) - 0.5;
  float r = length(c) * 2.0;
  float wisp = vnoise(c * 3.5 + vSeed * 31.0);      // fixed per puff: its edge grows and thins, never boils
  float a = vA * (1.0 - smoothstep(0.2, 1.0, r + (wisp - 0.5) * 0.7));
  // a solid core with a dithered rim: one tone, no blending
  if (a / uAlpha < bayer4(cell)) discard;          // thins through 16 dither levels, pinned to the puff
  gl_FragColor = vec4(uColor, 1.0);
}`,
  });
  const pts = new THREE.Points(geo, mat); pts.frustumCulled = false; fx.add(pts);
  const list = [];
  return {
    mat,
    add(q) { q.seed = rand(); list.push(q); while (list.length > max) list.shift(); },
    update(dt, drag, lift, grow) {
      let j = 0;
      for (let i = list.length - 1; i >= 0; i--) {
        const q = list[i];
        q.age += dt;
        if (q.age > q.life) { list.splice(i, 1); continue; }
        if (q.age < 0) { if (q.b) q.p.addScaledVector(q.b, dt); continue; }    // not out yet: still at the moving mouth
        q.v.multiplyScalar(Math.exp(-dt * drag)); q.v.y += dt * lift;
        q.p.addScaledVector(q.v, dt);
        if (q.b) { q.b.multiplyScalar(Math.exp(-dt * 0.28)); q.p.addScaledVector(q.b, dt); }   // carried along with the walker
      }
      for (const q of list) {
        if (q.age < 0 || j >= max) continue;
        const t = q.age / q.life;
        pos[j * 3] = q.p.x; pos[j * 3 + 1] = q.p.y; pos[j * 3 + 2] = q.p.z;
        info[j * 3] = q.size * (1 + grow * Math.sqrt(t));
        info[j * 3 + 1] = q.k * smooth(Math.min(1, t * 6)) * (1 - smooth(t));
        info[j * 3 + 2] = q.seed;
        j++;
      }
      geo.setDrawRange(0, j);
      geo.attributes.position.needsUpdate = true; geo.attributes.info.needsUpdate = true;
    },
  };
}
const breath = puffSystem(BR.color, BR.alpha, 96);
const brMat = breath.mat;
function exhale(strength) {
  // from the mouth, below the eye: the puff leaves forward and a little down, then the warm air lifts it into view
  const fwd = new THREE.Vector3(0, 0, -1).applyQuaternion(camera.quaternion);
  fwd.y = Math.min(fwd.y, 0.1); fwd.normalize();
  const mouth = camera.position.clone().addScaledVector(fwd, 0.16); mouth.y -= 0.11;
  // the breath leaves with the body's own speed, then the still air stops it and you walk into it
  const body = new THREE.Vector3(me.vw.x, 0, me.vw.y);
  const n = 4 + Math.floor(rand() * 3);
  for (let i = 0; i < n; i++) {
    const delay = i * 0.07 + rand() * 0.05;
    const v = fwd.clone().multiplyScalar(0.85 + rand() * 0.35).add(new THREE.Vector3((rand() - 0.5) * 0.08, 0.02 + rand() * 0.08, (rand() - 0.5) * 0.08));
    breath.add({ p: mouth.clone(), v, b: body.clone(), age: -delay, life: BR.life * (0.7 + rand() * 0.4), size: 0.012 + rand() * 0.008, k: strength });
  }
}
function updateBreath(dt) { breath.update(dt, 1.6, 0.12, 2.2); }
// the idling car: a slow plume from each exhaust anchor, drifting downwind
const EX = PS.exhaust || { color: '#8e7e8c', alpha: 0.6, every: 0.35, life: 3.2 };
const exhaust = (world.emitters || []).length ? puffSystem(EX.color, EX.alpha, 160) : null;
let exT = 0;
function updateExhaust(dt) {
  if (!exhaust) return;
  exT += dt;
  while (exT > EX.every) {
    exT -= EX.every;
    for (const e of world.emitters) {
      const v = new THREE.Vector3(...e.dir).multiplyScalar(0.35 + rand() * 0.2).add(new THREE.Vector3(0.12 + rand() * 0.06, 0.02, (rand() - 0.5) * 0.06));
      exhaust.add({ p: new THREE.Vector3(...e.pos), v, age: 0, life: EX.life * (0.7 + rand() * 0.5), size: 0.05 + rand() * 0.04, k: 1 });
    }
  }
  exhaust.update(dt, 0.8, 0.10, 4.0);
}

// ---------------------------------------------------------------------------------------------------- post: snap to palette, upscale
function oklab([r, g, b]) {
  [r, g, b] = [r, g, b].map(v => Math.pow(v, 2.2));
  const l = Math.cbrt(0.4122214708 * r + 0.5363325363 * g + 0.0514459929 * b);
  const m = Math.cbrt(0.2119034982 * r + 0.6806995451 * g + 0.1073969566 * b);
  const s = Math.cbrt(0.0883024619 * r + 0.2817188376 * g + 0.6299787005 * b);
  return [0.2104542553 * l + 0.7936177850 * m - 0.0040720468 * s, 1.9779984951 * l - 2.4285922050 * m + 0.4505937099 * s,
    0.0259040371 * l + 0.7827717662 * m - 0.8086757660 * s];
}
const palArr = PAL.slice(0, 96).map(c => new THREE.Vector3(...c));
const palLab = PAL.slice(0, 96).map(c => new THREE.Vector3(...oklab(c)));
while (palArr.length < 96) { palArr.push(palArr[0].clone()); palLab.push(palLab[0].clone()); }
const postMat = new THREE.ShaderMaterial({
  depthTest: false, depthWrite: false,
  uniforms: { uTex: { value: rt.texture }, uPal: { value: palArr }, uPalLab: { value: palLab }, uNPal: { value: Math.min(PAL.length, 96) },
    uScale: { value: 1 }, uOff: { value: new THREE.Vector2() }, uSize: { value: new THREE.Vector2(1, 1) } },
  vertexShader: `void main() { gl_Position = vec4(position.xy, 0.0, 1.0); }`,
  fragmentShader: /* glsl */`
uniform sampler2D uTex; uniform vec3 uPal[96]; uniform vec3 uPalLab[96]; uniform int uNPal; uniform float uScale; uniform vec2 uOff; uniform vec2 uSize;
vec3 lab(vec3 c) {  // OKLab, so the snap picks the perceptually nearest palette colour
  float l = 0.4122214708 * c.r + 0.5363325363 * c.g + 0.0514459929 * c.b;
  float m = 0.2119034982 * c.r + 0.6806995451 * c.g + 0.1073969566 * c.b;
  float s = 0.0883024619 * c.r + 0.2817188376 * c.g + 0.6299787005 * c.b;
  l = pow(l, 1.0 / 3.0); m = pow(m, 1.0 / 3.0); s = pow(s, 1.0 / 3.0);
  return vec3(0.2104542553 * l + 0.7936177850 * m - 0.0040720468 * s, 1.9779984951 * l - 2.4285922050 * m + 0.4505937099 * s,
              0.0259040371 * l + 0.7827717662 * m - 0.8086757660 * s);
}
vec3 lin(vec3 c) { return pow(c, vec3(2.2)); }
void main() {
  vec2 px = floor((gl_FragCoord.xy - uOff) / uScale);
  vec3 c = texture2D(uTex, (px + 0.5) / uSize).rgb;
  vec3 q = lab(lin(c));
  float best = 1e9; vec3 out_c = c;
  for (int i = 0; i < 96; i++) {
    if (i >= uNPal) break;
    vec3 d = uPalLab[i] - q;
    float e = dot(d, d);
    if (e < best) { best = e; out_c = uPal[i]; }
  }
  gl_FragColor = vec4(out_c, 1.0);
}`,
});
const postScene = new THREE.Scene();
const postQuad = new THREE.Mesh(fsTri, postMat); postQuad.frustumCulled = false; postScene.add(postQuad);
// the snap runs once per art pixel into snapRT; the blit scales it up by a whole number
const snapRT = new THREE.WebGLRenderTarget(4, 4, { minFilter: THREE.NearestFilter, magFilter: THREE.NearestFilter, depthBuffer: false });
const blitMat = new THREE.ShaderMaterial({
  depthTest: false, depthWrite: false,
  uniforms: { uTex: { value: snapRT.texture }, uScale: { value: 1 }, uOff: { value: new THREE.Vector2() }, uSize: { value: new THREE.Vector2(1, 1) } },
  vertexShader: `void main() { gl_Position = vec4(position.xy, 0.0, 1.0); }`,
  fragmentShader: `uniform sampler2D uTex; uniform float uScale; uniform vec2 uOff; uniform vec2 uSize;
void main() { vec2 px = floor((gl_FragCoord.xy - uOff) / uScale); gl_FragColor = vec4(texture2D(uTex, (px + 0.5) / uSize).rgb, 1.0); }`,
});
const blitScene = new THREE.Scene();
const blitQuad = new THREE.Mesh(fsTri, blitMat); blitQuad.frustumCulled = false; blitScene.add(blitQuad);
const orthoDummy = new THREE.OrthographicCamera(-1, 1, 1, -1, 0, 1);

// ---------------------------------------------------------------------------------------------------- texel splatting
const TX = S.texel || {};
const floatOK = renderer.extensions.has('EXT_color_buffer_float') || renderer.extensions.has('EXT_color_buffer_half_float');
const TEXEL = Q.get('render') !== 'screen' && floatOK;
const TX_SIZE = +(Q.get('texels') || (MOBILE ? TX.mobile_size || 320 : TX.size || 400));
const texel = TEXEL ? makeTexelSplat(THREE, {
  renderer, size: TX_SIZE, capture: Math.ceil(TX_SIZE * (TX.capture || 1.28)), cell: TX.cell || 1.0, cellY: TX.cell_y || TX.cell || 1.0, fade: TX.fade || 0.25,
  probeUniform: worldUniforms.uProbe, near: 0.05, far: S.camera.far, halfFloat: true, palette: palArr, paletteLab: palLab,
  draw(cam) {                                       // one probe face: the world and its 1 px lines (the sky is a layer)
    renderer.render(scene, cam);
    renderer.render(lineScene, cam);
  },
}) : null;
let artPx = 1, lastTexelT = -1;
const fogColor = new THREE.Color(fogC.x, fogC.y, fogC.z);   // what a pixel no splat or fill reached shows
function setFill(on) {           // the fill draws the plain world only where no splat landed (stencil 0)
  worldMat.stencilWrite = on;
  worldMat.stencilFunc = THREE.EqualStencilFunc; worldMat.stencilRef = 0; worldMat.stencilWriteMask = 0;
}

function resize() {
  const dpr = Math.min(window.devicePixelRatio || 1, 3);
  let cw = Math.floor(canvas.clientWidth * dpr), ch = Math.floor(canvas.clientHeight * dpr);
  if (TEXEL && ch > 1080) { cw = Math.round(cw * 1080 / ch); ch = 1080; }   // splats are chunky: 1080 lines is plenty
  renderer.setPixelRatio(1);
  renderer.setSize(cw, ch, false);
  SCALE = Math.max(S.pixel.min_scale, Math.round(ch / PIXEL_H));
  W = Math.max(1, Math.ceil(cw / SCALE)); H = Math.max(1, Math.ceil(ch / SCALE));
  rt.setSize(W, H); snapRT.setSize(W, H);
  const aspect = W / H;
  // portrait widens the vertical view smoothly, so a phone still sees the path beside the car
  const vfov = aspect >= 1 ? S.camera.fov : Math.min(80, 2 * Math.atan(Math.tan(S.camera.fov * DEG / 2) / Math.pow(aspect, 0.6)) / DEG);
  camera.fov = vfov; camera.aspect = aspect; camera.updateProjectionMatrix();
  let k = H / (2 * Math.tan(camera.fov * DEG / 2));
  if (TEXEL) {                     // particles in art pixels the size of a splat texel at the centre of the view
    camera.aspect = cw / ch; camera.updateProjectionMatrix();
    const focal = ch / (2 * Math.tan(camera.fov * DEG / 2));
    artPx = focal * texel.texelAngle;
    k = focal / artPx;
    artU.value = artPx; resU.value.set(cw, ch);
  } else {
    artU.value = 1; resU.value.set(W, H);
  }
  for (const m of [snowPts.material, bokehPts.material, brMat, exhaust && exhaust.mat]) if (m) m.uniforms.uK.value = k;
  postMat.uniforms.uScale.value = 1;
  postMat.uniforms.uSize.value.set(W, H);
  postMat.uniforms.uOff.value.set(0, 0);
  blitMat.uniforms.uScale.value = SCALE;
  blitMat.uniforms.uSize.value.set(W, H);
  blitMat.uniforms.uOff.value.set(Math.floor((cw - W * SCALE) / 2), Math.floor((ch - H * SCALE) / 2));
}
window.addEventListener('resize', resize);
if (window.ResizeObserver) new ResizeObserver(resize).observe(canvas);    // also catches a move to a screen with another DPR
resize();

// ---------------------------------------------------------------------------------------------------- walking ground
const HX = view(Float32Array, world.heights.xs), HZ = view(Float32Array, world.heights.zs), HY = view(Float32Array, world.heights.y);
function bsearch(a, x) { let lo = 0, hi = a.length - 1; while (hi - lo > 1) { const m = (lo + hi) >> 1; if (a[m] <= x) lo = m; else hi = m; } return lo; }
function terrainY(x, z) {
  const i = bsearch(HX, x), k = bsearch(HZ, z), nx = world.heights.nx;
  const u = clamp((x - HX[i]) / (HX[i + 1] - HX[i]), 0, 1), v = clamp((z - HZ[k]) / (HZ[k + 1] - HZ[k]), 0, 1);
  const y00 = HY[k * nx + i], y10 = HY[k * nx + i + 1], y01 = HY[(k + 1) * nx + i], y11 = HY[(k + 1) * nx + i + 1];
  return (y00 * (1 - u) + y10 * u) * (1 - v) + (y01 * (1 - u) + y11 * u) * v;
}
function inPoly(x, z, p) {
  let ins = false;
  for (let i = 0, j = p.length - 1; i < p.length; j = i++) {
    const [xi, zi] = p[i], [xj, zj] = p[j];
    if ((zi > z) !== (zj > z) && x < (xj - xi) * (z - zi) / (zj - zi) + xi) ins = !ins;
  }
  return ins;
}
function groundY(x, z) {
  let y = terrainY(x, z);
  for (const s of world.steps) if (s.top > y - 0.6 && inPoly(x, z, s.poly)) y = Math.max(y, s.top);
  return y;
}
function collide(p) {
  const R = 0.32;
  for (const [x, z, r] of world.colliders) {
    const dx = p.x - x, dz = p.z - z, d = Math.hypot(dx, dz), m = r + R;
    if (d < m && d > 1e-5) { p.x = x + dx / d * m; p.z = z + dz / d * m; }
  }
  for (const [x, z, yaw, hw, hd] of world.boxes) {
    // into the asset's frame (local -> world is x + lx cos + lz sin, z - lx sin + lz cos)
    const cy0 = Math.cos(yaw * DEG), sy0 = Math.sin(yaw * DEG);
    let lx = (p.x - x) * cy0 - (p.z - z) * sy0, lz = (p.x - x) * sy0 + (p.z - z) * cy0;
    const ex = hw + R, ez = hd + R;
    if (Math.abs(lx) < ex && Math.abs(lz) < ez) {
      if (ex - Math.abs(lx) < ez - Math.abs(lz)) lx = Math.sign(lx) * ex; else lz = Math.sign(lz) * ez;
      const cy = Math.cos(yaw * DEG), sy = Math.sin(yaw * DEG);
      p.x = x + lx * cy + lz * sy; p.z = z - lx * sy + lz * cy;
    }
  }
  const [x0, z0, x1, z1] = world.bounds;
  p.x = clamp(p.x, x0, x1); p.z = clamp(p.z, z0, z1);
}

// ---------------------------------------------------------------------------------------------------- the walker
const route = world.route.map(([x, z]) => new THREE.Vector2(x, z));
const routeS = [0]; for (let i = 1; i < route.length; i++) routeS.push(routeS[i - 1] + route[i].distanceTo(route[i - 1]));
const routeLen = routeS[routeS.length - 1];
function routeAt(s) {
  s = clamp(s, 0, routeLen);
  let i = bsearch(routeS, s); i = Math.min(i, route.length - 2);
  const t = (s - routeS[i]) / Math.max(routeS[i + 1] - routeS[i], 1e-6);
  return new THREE.Vector2().lerpVectors(route[i], route[i + 1], clamp(t, 0, 1));
}
function routeNearest(x, z, y) {
  let best = 1e9, bs = 0;
  for (let i = 0; i < route.length; i++) {
    const dy = y === undefined ? 0 : groundY(route[i].x, route[i].y) - y;
    const d = (route[i].x - x) ** 2 + (route[i].y - z) ** 2 + 4 * dy * dy;    // height counts: never jump to another leg
    if (d < best) { best = d; bs = routeS[i]; }
  }
  return bs;
}
const B = S.bob, EYE = S.camera.eye;
const lookEnd = new THREE.Vector3(...world.look_end);
const carAt = (world.instances.find(i => i.mesh.startsWith('car:')) || { at: [null] }).at[0];
const me = {
  pos: new THREE.Vector2(route[0].x, route[0].y), yaw: 0, pitch: -6 * DEG, eyeY: 0, speed: 0,
  phase: 0, mode: CARD ? 'card' : 'auto', s: 0, t: 0, arrived: false, breathT: 2.8, gait: 0,
  manualYaw: 0, manualPitch: 0, vw: new THREE.Vector2(),
};
me.eyeY = groundY(me.pos.x, me.pos.y) + EYE;
{ const [y0, p0] = carLook(me.pos); me.yaw = y0; me.pitch = p0; }
const motionPref = Q.get('motion') || (matchMedia('(prefers-reduced-motion: reduce)').matches ? 'gentle' : 'full');
let motionK = { full: 1, gentle: 0.4, off: 0 }[motionPref] ?? 1;
const INTRO = 3.0;
const keys = new Set();

function autoStep(dt) {
  me.t += dt;
  const walking = me.t > INTRO && !me.arrived;
  const left = routeLen - me.s;
  let target = walking ? B.speed : 0;
  if (walking && left < 3.0) target = B.speed * Math.max(0.25, smooth(left / 3.0));
  me.speed = damp(me.speed, target, walking ? 1.6 : 3.0, dt);
  if (walking) me.s = Math.min(routeLen, me.s + me.speed * dt);
  if (left < 0.02 && !me.arrived) me.arrived = true;
  const p = routeAt(me.s);
  if (me.blend) {
    me.blend.t = Math.min(1, me.blend.t + dt);
    me.pos.lerpVectors(me.blend.from, p, smooth(me.blend.t));
    if (me.blend.t >= 1) me.blend = null;
  } else me.pos.copy(p);
  // look: where the stair goes (an average over the next few metres, so curves don't swing the head), pulled
  // toward the car we're walking to; the intro and the last metres look at the car itself
  const [pyaw, ppitch] = pathLook(me.s, p);
  const [cyaw, cpitch] = carLook(p);
  const toCar = clamp(0.30 + 0.70 * smooth(clamp(1 - (left - 1.0) / 7.0, 0, 1)), 0, 1);
  const settle = smooth(clamp((me.t - INTRO) / 4.0, 0, 1));          // the intro look eases onto the path
  const k = lerp(1, toCar, settle);
  let yaw = cyaw + angDiff(pyaw, cyaw) * (1 - k);
  let pitch = lerp(ppitch, cpitch, k);
  if (me.t < INTRO) yaw += 0.05 * Math.sin(me.t * 0.8);
  if (me.arrived) { const w = me.t * 0.22; yaw += 0.10 * Math.sin(w) + 0.04 * Math.sin(w * 2.3); pitch += 0.04 * Math.sin(w * 0.7 + 1); }
  me.yaw = angDamp(me.yaw, yaw, 1.6, dt);
  me.pitch = damp(me.pitch, clamp(pitch, -35 * DEG, 25 * DEG), 1.8, dt);
}
function angDiff(a, b) { let d = a - b; while (d > Math.PI) d -= 2 * Math.PI; while (d < -Math.PI) d += 2 * Math.PI; return d; }
function pathLook(s, p) {
  let x = 0, z = 0, y = 0, n = 0;
  for (let a = 3.0; a <= 7.0; a += 1.0) { const q = routeAt(s + a); x += q.x; z += q.y; y += groundY(q.x, q.y); n++; }
  x /= n; z /= n; y = y / n + 1.15;
  return [Math.atan2(-(x - p.x), -(z - p.y)), Math.atan2(y - me.eyeY, Math.hypot(x - p.x, z - p.y))];
}
function carLook(p) {
  const lift = (world.start && world.start.pitch || 0) * DEG;
  return [Math.atan2(-(lookEnd.x - p.x), -(lookEnd.z - p.y)), Math.atan2(lookEnd.y - me.eyeY, Math.hypot(lookEnd.x - p.x, lookEnd.z - p.y)) + lift];
}
function manualStep(dt) {
  me.t += dt;
  let f = 0, r = 0;
  if (keys.has('KeyW') || keys.has('ArrowUp')) f += 1;
  if (keys.has('KeyS') || keys.has('ArrowDown')) f -= 1;
  if (keys.has('KeyD')) r += 1;
  if (keys.has('KeyA')) r -= 1;
  if (keys.has('ArrowLeft')) me.yaw += dt * 1.6;
  if (keys.has('ArrowRight')) me.yaw -= dt * 1.6;
  f += touch.move.y; r += touch.move.x;
  const len = Math.hypot(f, r);
  if (len > 1) { f /= len; r /= len; }
  const fast = keys.has('ShiftLeft') || keys.has('ShiftRight') ? 1.6 : 1.0;
  me.speed = damp(me.speed, Math.min(1, len) * B.speed * fast, 5.0, dt);
  if (len > 0.01) {
    const dirX = -Math.sin(me.yaw) * f + Math.cos(me.yaw) * r, dirZ = -Math.cos(me.yaw) * f - Math.sin(me.yaw) * r;
    const dl = Math.hypot(dirX, dirZ) || 1;
    me.vel = new THREE.Vector2(dirX / dl, dirZ / dl);
  }
  if (me.vel && me.speed > 0.01) {
    const p = { x: me.pos.x + me.vel.x * me.speed * dt, z: me.pos.y + me.vel.y * me.speed * dt };
    collide(p);
    me.pos.set(p.x, p.z);
  }
  me.pitch = clamp(me.pitch, -70 * DEG, 60 * DEG);
}
function headBob(dt) {
  // gait 0..1 follows real speed; the step phase advances with distance walked, so steps match the ground
  me.gait = damp(me.gait, clamp(me.speed / B.speed, 0, 1.3), 4, dt);
  me.phase += dt * Math.PI * B.walk.step_hz * clamp(me.speed / B.speed, 0, 1.6);
  const g = smooth(clamp(me.gait, 0, 1)) * motionK;
  const ib = B.idle, wb = B.walk;
  const br = Math.sin(me.t * 2 * Math.PI / ib.period);
  const idleK = (1 - smooth(clamp(me.gait, 0, 1))) * motionK;
  const step = Math.cos(2 * me.phase);                  // two dips per stride, one per foot plant
  const foot = Math.floor((me.phase - Math.PI / 2) / Math.PI);   // a foot lands at the bottom of each dip
  if (foot !== me.foot) { me.foot = foot; if (me.gait > 0.3) audio.step(foot & 1, clamp(me.gait, 0.5, 1.2)); }
  const stride = Math.sin(me.phase);
  return {
    y: idleK * ib.height * br + g * wb.height * (step - 1) * 0.5,
    x: g * wb.sway * stride,
    roll: g * wb.roll * DEG * stride * 0.8,
    pitch: idleK * ib.pitch * DEG * Math.sin(me.t * 2 * Math.PI / ib.period - 0.9) + g * wb.pitch * DEG * Math.cos(2 * me.phase + 0.7),
    breath: br,
  };
}
function breathe(dt) {
  const walking = me.gait > 0.4;
  const period = walking ? BR.every_walk : BR.every_idle;
  me.breathT += dt;
  if (me.breathT > period) { me.breathT -= period * (0.85 + rand() * 0.3); exhale(walking ? 1.0 : 0.85); audio.breath(walking ? 1.0 : 0.7); }
  updateBreath(dt);
  updateExhaust(dt);
}

function step(dt) {
  const px = me.pos.x, pz = me.pos.y;
  if (me.mode === 'auto') autoStep(dt); else if (me.mode === 'manual') manualStep(dt);
  if (dt > 0) me.vw.set((me.pos.x - px) / dt, (me.pos.y - pz) / dt);
  const target = groundY(me.pos.x, me.pos.y) + EYE;
  me.eyeY = Math.abs(target - me.eyeY) > 1.5 ? target : damp(me.eyeY, target, 4.5, dt);
  const bob = headBob(dt);
  const right = new THREE.Vector2(Math.cos(me.yaw), -Math.sin(me.yaw));
  camera.position.set(me.pos.x + right.x * bob.x, me.eyeY + bob.y, me.pos.y + right.y * bob.x);
  camera.rotation.set(me.pitch + bob.pitch, me.yaw, bob.roll);
  if (Q.has('look')) { const [y, p] = Q.get('look').split(',').map(Number); camera.rotation.set(p * DEG, y * DEG, 0); }
  camera.updateMatrixWorld();
  breathe(dt);
  if (carAt) audio.car(Math.hypot(me.pos.x - carAt[0], me.pos.y - carAt[2]));
  simTime += dt;
}

// card mode: an orbit camera around the asset
function cardCamera() {
  const b = world.meshes[CARD].bounds;
  const h = b[1][1] - b[0][1], r = Math.max(b[1][0] - b[0][0], b[1][2] - b[0][2], h);
  const yaw = +(Q.get('yaw') || 25) * DEG, pitch = +(Q.get('pitch') || 8) * DEG;
  const dist = +(Q.get('dist') || r * 1.5 + 1.2);
  const c = new THREE.Vector3(0, h * 0.45, 0);
  camera.position.set(c.x + Math.sin(yaw) * Math.cos(pitch) * dist, c.y + Math.sin(pitch) * dist, c.z + Math.cos(yaw) * Math.cos(pitch) * dist);
  camera.lookAt(c);
  camera.updateMatrixWorld();
}

// ---------------------------------------------------------------------------------------------------- input
const touch = { move: new THREE.Vector2(), id: null, look: null, start: null };
const COARSE = matchMedia('(pointer: coarse)').matches;
const autoBtn = document.getElementById('auto');
function takeover() {
  if (me.mode !== 'auto') return;
  me.mode = 'manual';
  if (autoBtn) autoBtn.hidden = false;
  setHint(stickShown() ? 'Left stick to walk, drag the right side to look. Walk on resumes the auto-walk'
    : 'WASD or arrows to walk, drag or click to look. R walks on by itself. M: gentler head motion');
}

// the touch stick: shown on touch screens (or with ?stick); the knob travels STICK_R px, a small dead zone at rest
const stickEl = document.getElementById('stick'), knobEl = document.getElementById('knob');
const STICK_R = 48;
const stickShown = () => !!stickEl && !stickEl.hidden;
function showStick() { if (stickEl && !Q.has('shot')) stickEl.hidden = false; }
if (COARSE || Q.has('stick')) showStick();
function stickStart(e, float) {
  touch.id = e.pointerId;
  if (float) {                 // a touch elsewhere on the left side brings the stick under the thumb
    const r = stickEl.getBoundingClientRect();
    stickEl.style.left = (e.clientX - r.width / 2) + 'px'; stickEl.style.top = (e.clientY - r.height / 2) + 'px';
    stickEl.style.bottom = 'auto';
    touch.start = [e.clientX, e.clientY];
  } else {
    const r = stickEl.getBoundingClientRect();
    touch.start = [r.left + r.width / 2, r.top + r.height / 2];
  }
  stickEl.classList.add('active');
  stickMove(e);
  takeover();
}
function stickMove(e) {
  let dx = e.clientX - touch.start[0], dy = e.clientY - touch.start[1];
  const d = Math.hypot(dx, dy);
  if (d > STICK_R) { dx *= STICK_R / d; dy *= STICK_R / d; }
  knobEl.style.transform = 'translate(' + dx + 'px, ' + dy + 'px)';
  const m = Math.min(d, STICK_R) / STICK_R;
  const k = m < 0.15 ? 0 : (m - 0.15) / 0.85 / m;          // past the dead zone, speed grows with the push
  touch.move.set(dx / STICK_R * k, -dy / STICK_R * k);
}
function stickEnd() {
  touch.id = null; touch.move.set(0, 0);
  if (!stickEl) return;
  knobEl.style.transform = ''; stickEl.classList.remove('active');
  stickEl.style.left = stickEl.style.top = stickEl.style.bottom = '';
}
stickEl?.addEventListener('pointerdown', e => {
  e.preventDefault();
  if (touch.id !== null) return;
  try { stickEl.setPointerCapture(e.pointerId); } catch (_) { /* ignore */ }
  stickStart(e, false);
});
function setHint(t) { if (!hintEl) return; hintEl.textContent = t; hintEl.classList.remove('gone'); clearTimeout(setHint.k); setHint.k = setTimeout(() => hintEl.classList.add('gone'), 6000); }
function setMotion(k, hint) {
  motionK = k;
  const label = 'Head motion: ' + (k === 1 ? 'full' : k > 0 ? 'gentle' : 'off');
  const b = document.getElementById('motion'); if (b) b.textContent = label;
  if (hint) setHint(label);
}
const nextMotion = () => setMotion(motionK === 1 ? 0.4 : motionK > 0 ? 0 : 1, true);
function resume() {
  me.mode = 'auto'; me.arrived = false; me.t = INTRO; me.vw.set(0, 0);
  me.s = routeNearest(me.pos.x, me.pos.y, me.eyeY - EYE);
  me.blend = { from: me.pos.clone(), t: 0 };                // ease back onto the stair instead of jumping
  if (autoBtn) autoBtn.hidden = true;
  setHint(stickShown() ? 'Walking on. The stick or a drag takes over' : 'Walking on. Any key or drag takes over');
}
addEventListener('keydown', e => {
  if (e.ctrlKey || e.metaKey || e.altKey) return;          // leave browser shortcuts alone (and Cmd never sends keyup)
  if (['KeyW', 'KeyA', 'KeyS', 'KeyD', 'ArrowUp', 'ArrowDown', 'ArrowLeft', 'ArrowRight'].includes(e.code)) { takeover(); keys.add(e.code); e.preventDefault(); }
  if (e.code === 'ShiftLeft' || e.code === 'ShiftRight') keys.add(e.code);
  if (e.repeat) return;
  const key = (e.key || '').toLowerCase();
  if (key === 'r') resume();
  if (key === 'm') nextMotion();
});
addEventListener('keyup', e => keys.delete(e.code));
function releaseAll() { keys.clear(); drag = null; touch.look = null; stickEnd(); }
addEventListener('blur', releaseAll);
document.addEventListener('visibilitychange', () => { if (document.hidden) releaseAll(); audio.visible(!document.hidden); });
let drag = null;
canvas.addEventListener('pointerdown', e => {
  canvas.focus();
  if (e.pointerType === 'touch') {
    showStick();
    if (e.clientX < innerWidth * 0.45 && touch.id === null) stickStart(e, true);
    else { touch.look = { id: e.pointerId, x: e.clientX, y: e.clientY }; takeover(); }
    return;
  }
  drag = { x: e.clientX, y: e.clientY };
  try { canvas.setPointerCapture(e.pointerId); } catch (_) { /* ignore */ }
  if (!document.pointerLockElement && canvas.requestPointerLock && e.button === 0) {
    try { const r = canvas.requestPointerLock(); if (r && r.catch) r.catch(() => {}); } catch (_) { /* ignore */ }
  }
});
addEventListener('pointermove', e => {
  if (e.pointerId === touch.id) { stickMove(e); return; }     // the stick, by finger or (for testing) by mouse
  if (e.pointerType === 'touch') {
    if (touch.look && e.pointerId === touch.look.id) { me.yaw -= (e.clientX - touch.look.x) * 0.006; me.pitch -= (e.clientY - touch.look.y) * 0.006; touch.look.x = e.clientX; touch.look.y = e.clientY; }
    return;
  }
  const locked = document.pointerLockElement === canvas;
  if (!locked && !drag) return;
  const dx = locked ? e.movementX : e.clientX - drag.x, dy = locked ? e.movementY : e.clientY - drag.y;
  if (Math.abs(dx) + Math.abs(dy) > 0) takeover();
  me.yaw -= dx * 0.0024; me.pitch -= dy * 0.0024;
  if (drag) { drag.x = e.clientX; drag.y = e.clientY; }
});
function pointerEnd(e) {
  if (e.pointerId === touch.id) stickEnd();
  if (touch.look && e.pointerId === touch.look.id) touch.look = null;
  drag = null;
}
addEventListener('pointerup', pointerEnd);
addEventListener('pointercancel', pointerEnd);
document.getElementById('sound')?.addEventListener('click', e => { const on = audio.toggle(); e.currentTarget.textContent = 'Sound: ' + (on ? 'on' : 'off'); e.currentTarget.setAttribute('aria-pressed', String(on)); canvas.focus(); });
document.getElementById('motion')?.addEventListener('click', () => { nextMotion(); canvas.focus(); });
autoBtn?.addEventListener('click', () => { resume(); canvas.focus(); });
setMotion(motionK, false);

// ---------------------------------------------------------------------------------------------------- frame
let simTime = 0;
const invVP = new THREE.Matrix4();
function render() {
  if (CARD) cardCamera();
  camera.updateMatrixWorld();
  invVP.multiplyMatrices(camera.matrixWorld, camera.projectionMatrixInverse);
  skyUniforms.uInvVP.value.copy(invVP);
  skyUniforms.uMeta.value.w = Math.floor(simTime * (SKYI.drift || 0) / SKYI.px_deg) * SKYI.px_deg;
  snowPts.material.uniforms.uTime.value = simTime;
  bokehPts.material.uniforms.uTime.value = simTime * 0.8;
  brMat.uniforms.uTime.value = simTime;
  if (exhaust) exhaust.mat.uniforms.uTime.value = simTime;
  if (TEXEL) {
    // probes follow the eye on the grid; stills capture a whole probe at once
    const dt = lastTexelT < 0 ? 0 : Math.max(0, simTime - lastTexelT);
    lastTexelT = simTime;
    texel.update(camera.position, paused ? 1 : dt, paused);
    renderer.setRenderTarget(null);
    renderer.setClearColor(fogColor, 1);
    renderer.clear(true, true, true);
    renderer.render(skyScene, camera);
    renderer.render(texel.scene(camera, artPx), camera);
    setFill(true);
    renderer.render(scene, camera);
    setFill(false);
    if (!Q.has('nofx')) renderer.render(fx, camera);
    return;
  }
  renderer.setRenderTarget(rt);
  renderer.setClearColor(0x000000, 1); renderer.clear();
  renderer.render(skyScene, camera);
  renderer.render(scene, camera);
  renderer.render(lineScene, camera);
  if (!Q.has('nofx')) renderer.render(fx, camera);
  renderer.setRenderTarget(snapRT);
  renderer.render(postScene, orthoDummy);
  renderer.setRenderTarget(null);
  renderer.clear();
  renderer.render(blitScene, orthoDummy);
}

const T0 = +(Q.get('t') || 0);
const paused = Q.has('pause');
if (T0 > 0) { const dt = 1 / 30; for (let t = 0; t < T0; t += dt) step(dt); } else step(0);
if (CARD) { motionK = 0; }
let last = performance.now();
function loop(now) {
  const dt = Math.min(0.05, (now - last) / 1000); last = now;
  if (!paused) step(dt);
  render();
  requestAnimationFrame(loop);
}
render();
document.getElementById('loading')?.setAttribute('hidden', '');
if (!CARD && !paused) setHint(stickShown() ? 'Walking up to the car. Use the stick to walk yourself, drag the right side to look'
  : 'Walking up to the car. Any key, drag or tap takes over. M: gentler head motion');
window.__fp = { ready: true, me, step, render, world, W: () => W, H: () => H, SCALE: () => SCALE, texel: TEXEL, artPx: () => artPx,
  texelOrigin: () => texel && texel.origin().toArray() };
requestAnimationFrame(loop);

// Texel splatting (after Dylan Ebert, "Texel Splatting: Perspective-Stable 3D Pixel Art", 2026): the world is shaded
// into a cubemap from a probe point snapped to a grid, and every cubemap texel is drawn as a small square in the
// world. The art pixels then belong to the surfaces, not to the screen: turning the head moves them rigidly, walking
// inside a grid cell leaves them where they are, and crossing into the next cell crossfades to the next probe with
// an ordered dither. Spots the probe can't see (behind a post, under a step) are left to a fill pass the caller draws
// where the stencil says no splat landed.
//
// The splat grid is equi-angular, so pixels keep one size across the view; it samples a denser capture (nearest).
// Shading is camera-independent: materials see the probe as `cameraPosition` while capturing and write their
// Chebyshev distance from it into alpha (0 = nothing there).

const QPI = Math.PI / 4;
// face axis and the two tangents spanning it; any basis works, the cube sampler does the bookkeeping
const FACES = [
  [[1, 0, 0], [0, 0, -1], [0, 1, 0]], [[-1, 0, 0], [0, 0, 1], [0, 1, 0]],
  [[0, 1, 0], [1, 0, 0], [0, 0, -1]], [[0, -1, 0], [1, 0, 0], [0, 0, 1]],
  [[0, 0, 1], [1, 0, 0], [0, 1, 0]], [[0, 0, -1], [-1, 0, 0], [0, 1, 0]],
];

// Once per probe: for every splat texel (an equi-angular grid, all six faces side by side in one 2D texture) read the
// capture at its centre (or at a line pixel inside its footprint, so 1 px wires and grass are never skipped) and at
// its four neighbours, snap the colour to the palette, and pack
//   r = palette index, g = Chebyshev depth (0 = nothing), b = which sides reach under a nearer neighbour (4 bits).
// Lines arrive with negative depth (their flag). Only the farther of two texels grows toward the other: the gap a
// moved eye would see opens behind a silhouette, so the background reaches under it and outlines keep their width.
const BAKE_FRAG = /* glsl */`
uniform samplerCube uCube; uniform float uS; uniform float uFlip;
uniform vec3 uAxes[6]; uniform vec3 uUs[6]; uniform vec3 uVs[6];
uniform vec3 uPalLab[96]; uniform int uNPal;
const float QPI = 0.7853981634;
vec3 lab(vec3 c) {
  c = pow(c, vec3(2.2));
  float l = 0.4122214708 * c.r + 0.5363325363 * c.g + 0.0514459929 * c.b;
  float m = 0.2119034982 * c.r + 0.6806995451 * c.g + 0.1073969566 * c.b;
  float s = 0.0883024619 * c.r + 0.2817188376 * c.g + 0.6299787005 * c.b;
  l = pow(l, 1.0 / 3.0); m = pow(m, 1.0 / 3.0); s = pow(s, 1.0 / 3.0);
  return vec3(0.2104542553 * l + 0.7936177850 * m - 0.0040720468 * s, 1.9779984951 * l - 2.4285922050 * m + 0.4505937099 * s,
              0.0259040371 * l + 0.7827717662 * m - 0.8086757660 * s);
}
vec4 raw(int f, vec2 a) {
  vec3 d = uAxes[f] + tan(a.x * QPI) * uUs[f] + tan(a.y * QPI) * uVs[f];
  return textureLod(uCube, vec3(uFlip * d.x, d.yz), 0.0);
}
vec4 at(int f, vec2 a) { vec4 t = raw(f, a); t.a = t.a == 0.0 ? 1e9 : abs(t.a); return t; }   // empty (sky) = infinitely far
// the texel for a cell: its centre, unless a line pixel lies inside the cell's footprint
vec4 cellAt(int f, vec2 a, float cell) {
  vec4 t = raw(f, a);
  if (t.a < 0.0) { t.a = -t.a; return t; }
  for (int k = 0; k < 4; k++) {
    vec2 o = vec2(k == 0 || k == 2 ? -0.3 : 0.3, k < 2 ? -0.3 : 0.3) * cell;
    vec4 u = raw(f, a + o);
    if (u.a < 0.0) { u.a = -u.a; return u; }
  }
  return t;
}
void main() {
  vec2 px = floor(gl_FragCoord.xy);
  int f = int(floor(px.x / uS));
  vec2 ij = vec2(px.x - float(f) * uS, px.y);
  float cell = 2.0 / uS;
  vec2 a = (ij + 0.5) * cell - 1.0;
  vec4 t = cellAt(f, a, cell);
  float d = t.a;
  if (d <= 0.0) { gl_FragColor = vec4(0.0); return; }
  float tol = 0.035 * d + 0.03;
  float code = 0.0;
  if (at(f, a - vec2(cell, 0.0)).a < d - tol) code += 1.0;
  if (at(f, a + vec2(cell, 0.0)).a < d - tol) code += 2.0;
  if (at(f, a - vec2(0.0, cell)).a < d - tol) code += 4.0;
  if (at(f, a + vec2(0.0, cell)).a < d - tol) code += 8.0;
  vec3 q = lab(t.rgb);
  float best = 1e9; int bi = 0;
  for (int i = 0; i < 96; i++) {
    if (i >= uNPal) break;
    vec3 e = uPalLab[i] - q; float k = dot(e, e);
    if (k < best) { best = k; bi = i; }
  }
  gl_FragColor = vec4(float(bi), d, code, 1.0);
}`;

const SPLAT_VERT = /* glsl */`
uniform sampler2D uAtlas; uniform float uFace; uniform vec3 uO; uniform vec3 uAxis; uniform vec3 uU; uniform vec3 uV;
uniform float uS; uniform vec3 uPal[96]; uniform vec2 uFade;
attribute vec2 corner;
varying vec3 vCol; varying float vHash;
const float QPI = 0.7853981634;
vec3 dirAt(vec2 a) { return uAxis + tan(a.x * QPI) * uU + tan(a.y * QPI) * uV; }
void main() {
  int S = int(uS);
  int i = gl_InstanceID % S, j = gl_InstanceID / S;
  vec4 t = texelFetch(uAtlas, ivec2(int(uFace) * S + i, j), 0);
  float d = t.g;
  if (d <= 0.0) { gl_Position = vec4(2.0, 2.0, 2.0, 1.0); vCol = vec3(0.0); return; }
  // reach under a nearer neighbour (closes the gap a moved eye would see behind its edge); barely toward the same surface
  int code = int(t.b + 0.5);
  vec4 grow = vec4((code & 1) != 0 ? 0.5 : 0.07, (code & 2) != 0 ? 0.5 : 0.07,
                   (code & 4) != 0 ? 0.5 : 0.07, (code & 8) != 0 ? 0.5 : 0.07);
  float cell = 2.0 / uS;
  vec2 a = (vec2(float(i), float(j)) + 0.5) * cell - 1.0;
  vec2 lo = a - cell * (0.5 + grow.xz), hi = a + cell * (0.5 + grow.yw);
  vec3 r = dirAt(mix(lo, hi, corner));
  float m = max(abs(r.x), max(abs(r.y), abs(r.z)));
  vec4 clip = projectionMatrix * viewMatrix * vec4(uO + r * (d / m), 1.0);
  float h = fract(sin(float(gl_InstanceID) * 12.9898 + uFace * 78.233) * 43758.5453);
  clip.z += h * 2e-6 * clip.w;                     // break ties between neighbours
  if (uFade.x > 0.5 && uFade.x < 1.5) clip.z += 4e-4 * clip.w;   // the incoming probe waits just behind the outgoing one
  gl_Position = clip;
  vHash = h;
  vCol = uPal[int(t.r + 0.5)];
}`;
const SPLAT_FRAG = /* glsl */`
uniform vec2 uFade; uniform float uArt;
varying vec3 vCol; varying float vHash;
void main() {
  // a probe swap: the incoming probe is drawn whole just behind; the outgoing one lets go texel by texel, each at its
  // own moment, so nothing screen-fixed sweeps over the picture
  if (uFade.x > 1.5 && vHash < uFade.y) discard;
  gl_FragColor = vec4(vCol, 1.0);
}`;

export function makeTexelSplat(THREE, { renderer, draw, size, capture, cell, cellY, fade, probeUniform, near, far, halfFloat, palette, paletteLab }) {
  const type = halfFloat ? THREE.HalfFloatType : THREE.FloatType;
  const mkRT = () => {
    const rt = new THREE.WebGLCubeRenderTarget(capture, { type, format: THREE.RGBAFormat, generateMipmaps: false,
      minFilter: THREE.NearestFilter, magFilter: THREE.NearestFilter, depthBuffer: true });
    rt.texture.generateMipmaps = false;
    return rt;
  };
  const cubeCam = new THREE.CubeCamera(near, far, mkRT());
  cubeCam.coordinateSystem = renderer.coordinateSystem;
  cubeCam.updateCoordinateSystem();

  // a direction samples the texel the cube camera rendered for it (checked against the screen renderer); FLIP = -1
  // would mirror x, for a renderer whose cube targets are stored mirrored
  const FLIP = 1;

  const pal = palette.slice(0, 96), palLab = paletteLab.slice(0, 96);
  while (pal.length < 96) { pal.push(pal[0]); palLab.push(palLab[0]); }
  const bakeMat = new THREE.ShaderMaterial({
    vertexShader: 'void main() { gl_Position = vec4(position.xy, 0.0, 1.0); }', fragmentShader: BAKE_FRAG,
    depthTest: false, depthWrite: false,
    uniforms: { uCube: { value: null }, uS: { value: size }, uFlip: { value: FLIP },
      uAxes: { value: FACES.map(f => new THREE.Vector3(...f[0])) }, uUs: { value: FACES.map(f => new THREE.Vector3(...f[1])) },
      uVs: { value: FACES.map(f => new THREE.Vector3(...f[2])) }, uPalLab: { value: palLab }, uNPal: { value: Math.min(palette.length, 96) } },
  });
  const tri = new THREE.BufferGeometry();
  tri.setAttribute('position', new THREE.BufferAttribute(new Float32Array([-1, -1, 0, 3, -1, 0, -1, 3, 0]), 3));
  const bakeScene = new THREE.Scene();
  const bakeQuad = new THREE.Mesh(tri, bakeMat); bakeQuad.frustumCulled = false; bakeScene.add(bakeQuad);
  const bakeCam = new THREE.OrthographicCamera(-1, 1, 1, -1, 0, 1);

  const quad = new THREE.InstancedBufferGeometry();
  quad.setAttribute('position', new THREE.BufferAttribute(new Float32Array(12), 3));
  quad.setAttribute('corner', new THREE.BufferAttribute(new Float32Array([0, 0, 1, 0, 1, 1, 0, 1]), 2));
  quad.setIndex([0, 1, 2, 0, 2, 3]);
  quad.instanceCount = size * size;
  quad.boundingSphere = new THREE.Sphere(new THREE.Vector3(), 1e9);

  function probe() {
    const rt = mkRT();
    const atlas = new THREE.WebGLRenderTarget(size * 6, size, { type: halfFloat ? THREE.HalfFloatType : THREE.FloatType,
      format: THREE.RGBAFormat, minFilter: THREE.NearestFilter, magFilter: THREE.NearestFilter, depthBuffer: false,
      generateMipmaps: false });
    const meshes = FACES.map(([ax, u, v], fi) => {
      const mat = new THREE.ShaderMaterial({
        vertexShader: SPLAT_VERT, fragmentShader: SPLAT_FRAG, side: THREE.DoubleSide,
        uniforms: { uAtlas: { value: atlas.texture }, uFace: { value: fi }, uO: { value: new THREE.Vector3() },
          uAxis: { value: new THREE.Vector3(...ax) }, uU: { value: new THREE.Vector3(...u) }, uV: { value: new THREE.Vector3(...v) },
          uS: { value: size }, uPal: { value: pal }, uFade: { value: new THREE.Vector2() }, uArt: { value: 4 } },
        stencilWrite: true, stencilRef: 1, stencilFunc: THREE.AlwaysStencilFunc, stencilZPass: THREE.ReplaceStencilOp,
      });
      const m = new THREE.Mesh(quad, mat);
      m.frustumCulled = false;
      m.userData.axis = new THREE.Vector3(...ax);
      return m;
    });
    return { rt, atlas, meshes, origin: new THREE.Vector3(), ready: false, next: 0, active: false };
  }
  // three probes: the one on screen, the one fading out, and the next one being captured a few faces a frame
  let cur = probe(), prev = probe(), pend = probe();
  let fadeT = 1, hasCur = false;
  const splatScene = new THREE.Scene();

  function captureFaces(p, count) {
    cubeCam.position.copy(p.origin);
    cubeCam.updateMatrixWorld();
    probeUniform.value.set(p.origin.x, p.origin.y, p.origin.z, 1);
    const old = renderer.getRenderTarget();
    for (let n = 0; n < count && p.next < 6; n++, p.next++) {
      renderer.setRenderTarget(p.rt, p.next);
      renderer.setClearColor(0x000000, 0);
      renderer.clear(true, true, true);
      draw(cubeCam.children[p.next], capture);
    }
    renderer.setRenderTarget(old);
    probeUniform.value.w = 0;
    if (p.next >= 6) {
      bakeMat.uniforms.uCube.value = p.rt.texture;          // pack it for the splats: palette index, depth, gap flags
      renderer.setRenderTarget(p.atlas);
      renderer.render(bakeScene, bakeCam);
      renderer.setRenderTarget(old);
      p.ready = true;
      for (const m of p.meshes) m.material.uniforms.uO.value.copy(p.origin);
    }
  }
  const snap = v => Math.round(v / cell) * cell;
  const snapY = v => Math.round(v / cellY) * cellY;

  return {
    // keep the probes on the grid around the eye; `now` captures a whole probe at once (stills, the first frame)
    update(eye, dt, now) {
      if (!hasCur) {                                    // the first probe, whole, before anything is drawn
        cur.origin.set(snap(eye.x), snapY(eye.y), snap(eye.z)); cur.next = 0; captureFaces(cur, 6);
        hasCur = true; fadeT = 1;
        return;
      }
      fadeT = Math.min(1, fadeT + dt / fade);
      if (!pend.active && fadeT >= 1) {
        const away = Math.max(Math.abs(eye.x - cur.origin.x) / cell, Math.abs(eye.y - cur.origin.y) / cellY,
          Math.abs(eye.z - cur.origin.z) / cell);
        if (away > 0.5 + 0.08) {                        // a little hysteresis, so a bob on a cell border can't flicker
          pend.origin.set(snap(eye.x), snapY(eye.y), snap(eye.z)); pend.next = 0; pend.ready = false; pend.active = true;
        }
      }
      if (pend.active) {
        captureFaces(pend, now ? 6 : 2);               // two faces a frame keeps the cost of a crossing small
        if (pend.ready) {                               // swap in; the old probe dithers away under the new one
          [prev, cur, pend] = [cur, pend, prev];
          pend.active = false; pend.ready = false; pend.next = 0;
          fadeT = now ? 1 : 0;
        }
      }
    },
    // draw the splats facing the view; returns the scene so the caller renders it with the main camera
    scene(camera, artPx) {
      splatScene.clear();
      const fwd = new THREE.Vector3(0, 0, -1).applyQuaternion(camera.quaternion);
      const vh = Math.tan(camera.fov * Math.PI / 360), hh = vh * camera.aspect;
      const lim = Math.cos(QPI + Math.atan(Math.hypot(vh, hh)) + 0.12);
      const add = (p, role) => {
        for (const m of p.meshes) {
          if (m.userData.axis.dot(fwd) < lim) continue;
          m.material.uniforms.uFade.value.set(role, fadeT);
          m.material.uniforms.uArt.value = artPx;
          splatScene.add(m);
        }
      };
      add(cur, fadeT < 1 ? 1 : 0);
      if (fadeT < 1 && prev.ready) add(prev, 2);
      return splatScene;
    },
    texelAngle: QPI * 2 / size,
    origin: () => cur.origin,
  };
}

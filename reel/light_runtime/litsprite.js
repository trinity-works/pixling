/* litsprite.js: player for "pixling.lit-sprite" sheets (reel light build), no dependencies.

   const sheet = await LitSprite.load("golem.json");          // json + colour + normal images
   const actor = new LitSprite.Actor(sheet, { x: 400, scale: 1 });
   actor.update(dt, { move: -1 | 0 | 1, hurry: false });      // per frame; actor.play("swing") for a one-shot clip
   for (const d of actor.draws()) ...                         // {frame, mirror, x, alpha}: draw these, back to front
   const r = new LitSprite.Renderer(gl);                      // optional WebGL renderer for the draws
   r.actor(actor, groundY, { ambient, sun, lights }, view);

   Motion rules (the same in lit_sprite.gd):
   - the lead clip (a walk) advances with distance travelled, and the drawn sprite moves in steps synced to its frames
     (anchor minus the progress inside the current frame), so planted feet never slide;
   - on release it finishes the step quickly (within ~0.4 s) to the next lead frame whose silhouette matches a rest
     pose (stops[k].iou >= stop_iou), then crossfades into that rest pose (blend_frames at 12 fps); moving again starts
     from the lead frame that best matches the current rest pose (starts[j]);
   - other clips play once on play(name), crossfaded in and back to the rest clip;
   - frames hold for anims[*].durations (filmed spacing); a clip with blend: true crossfades each pose into the next;
   - facing left mirrors the sprite AND the normal's x (sheets are drawn facing `faces`: 1 = right, -1 = left). */
(function (root) {
  "use strict";

  function loadImage(src) {
    return new Promise((res, rej) => {
      const i = new Image(); i.crossOrigin = "anonymous";
      i.onload = () => res(i); i.onerror = () => rej(new Error("Couldn't load " + src)); i.src = src;
    });
  }

  async function load(url) {
    const meta = await (await fetch(url)).json();
    if (meta.format && meta.format !== "pixling.lit-sprite") throw new Error(url + " is not a lit-sprite sheet");
    const dir = url.slice(0, url.lastIndexOf("/") + 1);
    const img = meta.images || { color: meta.name + "_color.webp", normal: meta.name + "_normal.webp" };
    const [color, normal] = await Promise.all([loadImage(dir + img.color), loadImage(dir + img.normal)]);
    return { meta, color, normal };
  }

  class Actor {
    constructor(sheet, opt = {}) {
      const M = this.M = sheet.meta || sheet;
      this.sheet = sheet; this.scale = opt.scale || 1; this.x = opt.x || 0;
      this.leadName = M.lead || "walk"; this.restName = M.rest === undefined ? "idle" : M.rest;
      this.lead = M.anims[this.leadName]; this.rest = this.restName ? M.anims[this.restName] : null;
      this.faces = M.faces || 1; this.face = 1;
      this.mode = this.rest ? "rest" : "hold"; this.dist = 0; this.t = 0; this.pose = 0; this.rate = 1;
      this.prev = null; this.fade = 0; this.last = null; this.shot = null;
      this.minX = opt.minX === undefined ? -Infinity : opt.minX; this.maxX = opt.maxX === undefined ? Infinity : opt.maxX;
    }
    get step() { return (this.lead.speed || 0) * this.scale; }
    total(a) { return (a.durations || []).reduce((s, d) => s + d, 0) || a.count / a.fps; }
    at(a, t) {        // pose index and progress inside it at time t into clip a
      const D = a.durations || Array(a.count).fill(1 / a.fps); let i = 0;
      while (i < D.length - 1 && t >= D[i]) { t -= D[i]; i++; }
      return [i, Math.min(1, t / D[i])];
    }
    startFade() { if (this.last) { this.prev = Object.assign({}, this.last); this.fade = 1; } }
    restAt(j) { const D = this.rest.durations || Array(this.rest.count).fill(1 / this.rest.fps); return D.slice(0, j).reduce((s, d) => s + d, 0); }
    play(name) {
      if (!this.M.anims[name]) return false;
      this.startFade(); this.shot = name; this.mode = "shot"; this.t = 0; return true;
    }
    move(d) { const nx = Math.max(this.minX, Math.min(this.maxX, this.x + d)); this.dist += Math.abs(nx - this.x); this.x = nx; }
    update(dt, input = {}) {
      dt = Math.min(dt, 0.05);
      const M = this.M, L = this.lead, n = L.count, step = this.step, iou = M.stop_iou || 0.85;
      const dir = Math.sign(input.move || 0), v = step * L.fps * (input.hurry ? 1.6 : 1);
      if (this.mode === "shot") {
        this.t += dt;
        if (this.t >= this.total(M.anims[this.shot])) { this.startFade(); this.shot = null; this.mode = this.rest ? "rest" : "hold"; this.t = 0; }
      } else if (dir !== 0 && step > 0) {
        if (this.mode === "rest") {
          const st = M.starts[this.pose]; this.startFade();
          this.x -= this.face * this.faces * st.dx * this.scale; this.dist = (st.walk + 0.5) * step;
        } else if (dir !== this.face) this.startFade();
        this.face = dir; this.mode = "lead"; this.move(dir * v * dt);
      } else if (dir !== 0) {
        if (dir !== this.face) { this.startFade(); this.face = dir; }
      } else if (this.mode === "lead" || this.mode === "stopping") {
        const k = Math.floor(this.dist / step) % n;
        if (!this.rest) { this.mode = "hold"; }
        else if (this.mode === "stopping" && M.stops[k].iou >= iou) {
          const sp = M.stops[k]; this.startFade();
          this.x += this.face * this.faces * sp.dx * this.scale; this.mode = "rest"; this.t = this.restAt(sp.idle);
        } else {
          if (this.mode !== "stopping") {     // frames left to the next stop pose, finished within ~0.4 s
            let r = 1; while (r < n && M.stops[(k + r) % n].iou < iou) r++;
            this.rate = Math.min(4, Math.max(1, r / (0.4 * L.fps))); this.mode = "stopping";
          }
          this.move(this.face * v * this.rate * dt);
        }
      }
      if (this.mode === "rest") this.t += dt;
      this.fade = Math.max(0, this.fade - dt / ((M.blend_frames || 4) / 12));
      const cur = this.draws(true)[0]; this.last = cur;
    }
    // what to draw now: the current frame, the next pose blended over it (blend: true clips), the fading previous frame
    draws(currentOnly) {
      const M = this.M, mirror = this.face * this.faces < 0, out = [];
      let fi, fb = -1, fw = 0, x = this.x;
      if (this.mode === "shot" || this.mode === "rest") {
        const a = this.mode === "shot" ? M.anims[this.shot] : this.rest;
        const t = this.mode === "shot" ? this.t : this.t % this.total(a);
        const [i, p] = this.at(a, t); if (this.mode === "rest") this.pose = i;
        fi = a.start + i;
        if (a.blend && (a.loop !== false || i + 1 < a.count)) { fb = a.start + (i + 1) % a.count; fw = p; }
      } else {
        const step = this.step || 1;
        fi = this.lead.start + Math.floor(this.dist / step) % this.lead.count;
        x = this.x - this.face * (this.dist % step);       // frame-synced travel: no foot slide
      }
      out.push({ frame: fi, mirror, x, alpha: 1 });
      if (currentOnly) return out;
      if (fb >= 0 && fw > 0.01) out.push({ frame: fb, mirror, x, alpha: fw });
      if (this.fade > 0 && this.prev) out.push(Object.assign({}, this.prev, { alpha: this.fade }));
      return out;
    }
    // screen rect of a draw at ground y: {x, y, w, h, u0, v0, u1, v1} (uv already mirrored)
    rect(d, groundY) {
      const f = this.M.frames[d.frame], A = this.M.atlas, s = this.scale, w = f.w * s, h = f.h * s;
      const left = d.mirror ? d.x - f.ox * s - w : d.x + f.ox * s;
      let u0 = f.u / A[0], u1 = (f.u + f.w) / A[0]; if (d.mirror) [u0, u1] = [u1, u0];
      return { x: left, y: groundY + f.oy * s, w, h, u0, v0: f.v / A[1], u1, v1: (f.v + f.h) / A[1] };
    }
  }

  // ---- WebGL 1 renderer: normal-mapped sprites, soft shapes (shadow blobs, light glows)
  const VS = "attribute vec2 aPos;attribute vec2 aUV;uniform vec4 uView;varying vec2 vUV;varying vec2 vW;" +
    "void main(){vUV=aUV;vW=aPos;vec2 p=(aPos-uView.xy)/uView.zw;gl_Position=vec4(p.x*2.-1.,1.-p.y*2.,0.,1.);}";
  const FS_LIT = "precision mediump float;varying vec2 vUV;varying vec2 vW;uniform sampler2D uC,uN;" +
    "uniform float uFlip,uLit,uA;uniform vec3 uAmb,uSunDir,uSun;uniform vec4 uLP[4];uniform vec4 uLC[4];" +
    "void main(){vec4 b=texture2D(uC,vUV);if(b.a<.02)discard;" +
    "vec3 n=texture2D(uN,vUV).rgb*2.-1.;n.y=-n.y;n.x*=uFlip;n=normalize(n);" +       // sheets are green-up; world y is down
    "vec3 acc=uAmb+uSun*max(dot(n,normalize(uSunDir)),0.);" +
    "for(int i=0;i<4;i++){vec3 d=vec3(uLP[i].xy-vW,uLP[i].z);float r=length(d);d/=r;" +
    "float att=1./(1.+pow(r/uLP[i].w,2.));att*=smoothstep(uLP[i].w*3.2,uLP[i].w*1.2,r);acc+=max(dot(n,d),0.)*att*uLC[i].rgb*uLC[i].a;}" +
    "gl_FragColor=vec4(uLit>.5?b.rgb*acc:b.rgb,b.a*uA);}";
  const FS_SHAPE = "precision mediump float;varying vec2 vUV;uniform vec4 uCol;uniform float uKind;" +
    "void main(){vec2 p=vUV*2.-1.;float r=length(p);" +
    "if(uKind<.5){gl_FragColor=uCol;return;}" +
    "if(uKind<1.5){gl_FragColor=vec4(0.,0.,0.,smoothstep(1.,.15,r)*uCol.a);return;}" +
    "gl_FragColor=vec4(uCol.rgb*(exp(-r*r*5.)*.6+smoothstep(.14,0.,r)),1.);}";

  class Renderer {
    constructor(gl) {
      this.gl = gl; this.buf = gl.createBuffer(); this.v = new Float32Array(24); this.tex = new Map();
      this.lit = this.prog(FS_LIT); this.shape = this.prog(FS_SHAPE); this.view = [0, 0, 1, 1]; this.enabled = true;
    }
    prog(fs) {
      const gl = this.gl, p = gl.createProgram();
      for (const [t, s] of [[gl.VERTEX_SHADER, VS], [gl.FRAGMENT_SHADER, fs]]) {
        const sh = gl.createShader(t); gl.shaderSource(sh, s); gl.compileShader(sh);
        if (!gl.getShaderParameter(sh, gl.COMPILE_STATUS)) throw new Error(gl.getShaderInfoLog(sh));
        gl.attachShader(p, sh);
      }
      gl.linkProgram(p);
      const u = {}, n = gl.getProgramParameter(p, gl.ACTIVE_UNIFORMS);
      for (let i = 0; i < n; i++) { const a = gl.getActiveUniform(p, i); u[a.name.replace("[0]", "")] = gl.getUniformLocation(p, a.name); }
      return { p, u, aPos: gl.getAttribLocation(p, "aPos"), aUV: gl.getAttribLocation(p, "aUV") };
    }
    texture(img) {
      if (this.tex.has(img)) return this.tex.get(img);
      const gl = this.gl, t = gl.createTexture(); gl.bindTexture(gl.TEXTURE_2D, t);
      gl.texImage2D(gl.TEXTURE_2D, 0, gl.RGBA, gl.RGBA, gl.UNSIGNED_BYTE, img);
      for (const [k, v] of [[gl.TEXTURE_MIN_FILTER, gl.LINEAR], [gl.TEXTURE_MAG_FILTER, gl.LINEAR], [gl.TEXTURE_WRAP_S, gl.CLAMP_TO_EDGE], [gl.TEXTURE_WRAP_T, gl.CLAMP_TO_EDGE]]) gl.texParameteri(gl.TEXTURE_2D, k, v);
      this.tex.set(img, t); return t;
    }
    quad(pr, x, y, w, h, u0 = 0, v0 = 0, u1 = 1, v1 = 1) {
      const gl = this.gl, d = this.v;
      d.set([x, y, u0, v0, x + w, y, u1, v0, x, y + h, u0, v1, x + w, y, u1, v0, x + w, y + h, u1, v1, x, y + h, u0, v1]);
      gl.bindBuffer(gl.ARRAY_BUFFER, this.buf); gl.bufferData(gl.ARRAY_BUFFER, d, gl.DYNAMIC_DRAW);
      gl.enableVertexAttribArray(pr.aPos); gl.vertexAttribPointer(pr.aPos, 2, gl.FLOAT, false, 16, 0);
      if (pr.aUV >= 0) { gl.enableVertexAttribArray(pr.aUV); gl.vertexAttribPointer(pr.aUV, 2, gl.FLOAT, false, 16, 8); }
      gl.uniform4fv(pr.u.uView, this.view); gl.drawArrays(gl.TRIANGLES, 0, 6);
    }
    // world rect visible on the canvas: x, y, width, height
    setView(x, y, w, h) { this.view = [x, y, w, h]; }
    fill(x, y, w, h, rgba) { const gl = this.gl, s = this.shape; gl.useProgram(s.p); gl.enable(gl.BLEND); gl.blendFunc(gl.SRC_ALPHA, gl.ONE_MINUS_SRC_ALPHA); gl.uniform1f(s.u.uKind, 0); gl.uniform4fv(s.u.uCol, rgba); this.quad(s, x, y, w, h); }
    blob(cx, cy, w, h, alpha) { const gl = this.gl, s = this.shape; gl.useProgram(s.p); gl.enable(gl.BLEND); gl.blendFunc(gl.SRC_ALPHA, gl.ONE_MINUS_SRC_ALPHA); gl.uniform1f(s.u.uKind, 1); gl.uniform4fv(s.u.uCol, [0, 0, 0, alpha]); this.quad(s, cx - w / 2, cy - h / 2, w, h); }
    glow(cx, cy, r, rgb) { const gl = this.gl, s = this.shape; gl.useProgram(s.p); gl.enable(gl.BLEND); gl.blendFunc(gl.ONE, gl.ONE); gl.uniform1f(s.u.uKind, 2); gl.uniform4fv(s.u.uCol, [rgb[0], rgb[1], rgb[2], 1]); this.quad(s, cx - r, cy - r, 2 * r, 2 * r); }
    // env: {ambient:[r,g,b], sun:{dir:[x,y,z], color:[r,g,b]}, lights:[{x,y,z,r,color:[r,g,b],power}] (up to 4)}
    actor(actor, groundY, env) {
      const gl = this.gl, P = this.lit, u = P.u, sh = actor.sheet;
      gl.useProgram(P.p); gl.enable(gl.BLEND); gl.blendFunc(gl.SRC_ALPHA, gl.ONE_MINUS_SRC_ALPHA);
      gl.activeTexture(gl.TEXTURE0); gl.bindTexture(gl.TEXTURE_2D, this.texture(sh.color)); gl.uniform1i(u.uC, 0);
      gl.activeTexture(gl.TEXTURE1); gl.bindTexture(gl.TEXTURE_2D, this.texture(sh.normal)); gl.uniform1i(u.uN, 1);
      gl.uniform3fv(u.uAmb, env.ambient || [.2, .2, .25]);
      gl.uniform3fv(u.uSunDir, (env.sun && env.sun.dir) || [0, -1, 1]); gl.uniform3fv(u.uSun, (env.sun && env.sun.color) || [0, 0, 0]);
      const lp = new Float32Array(16), lc = new Float32Array(16);
      (env.lights || []).slice(0, 4).forEach((L, i) => { lp.set([L.x, L.y, L.z || 100, L.r || 300], i * 4); lc.set([...(L.color || [1, 1, 1]), L.power === undefined ? 1 : L.power], i * 4); });
      for (let i = (env.lights || []).length; i < 4; i++) lp.set([0, 0, 1, 1], i * 4);
      gl.uniform4fv(u.uLP, lp); gl.uniform4fv(u.uLC, lc); gl.uniform1f(u.uLit, this.enabled ? 1 : 0);
      for (const d of actor.draws()) {
        const r = actor.rect(d, groundY);
        gl.uniform1f(u.uFlip, d.mirror ? -1 : 1); gl.uniform1f(u.uA, d.alpha);
        this.quad(P, r.x, r.y, r.w, r.h, r.u0, r.v0, r.u1, r.v1);
      }
    }
  }

  const api = { load, Actor, Renderer, FORMAT: "pixling.lit-sprite", VERSION: 1 };
  if (typeof module !== "undefined" && module.exports) module.exports = api; else root.LitSprite = api;
})(typeof self !== "undefined" ? self : this);

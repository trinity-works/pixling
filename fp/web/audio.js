// fp audio: everything synthesized, nothing loaded. Wind in the trees, a crunch per footfall in snow or a knock on
// stone (panned to the foot), a soft exhale with each breath cloud, the parked car's idle, louder as you get close,
// and a warm swell when she stops. Off until the player turns it on (browsers only start audio from a gesture).

export function makeAudio() {
  let ctx = null, master = null, noise = null, idle = null;
  const A = { on: false };

  function noiseBuffer(seconds, brown) {
    const n = Math.floor(ctx.sampleRate * seconds), b = ctx.createBuffer(1, n, ctx.sampleRate), d = b.getChannelData(0);
    let last = 0;
    for (let i = 0; i < n; i++) {
      const w = Math.random() * 2 - 1;
      if (brown) { last = (last + 0.02 * w) / 1.02; d[i] = last * 3.5; } else d[i] = w;
    }
    if (brown) {          // crossfade the tail into the head so the loop has no seam
      const f = Math.floor(ctx.sampleRate * 0.5);
      for (let i = 0; i < f; i++) { const t = i / f; d[i] = d[i] * t + d[n - f + i] * (1 - t); }
      return trimmed(b, n - f);
    }
    return b;
  }

  function trimmed(b, n) {
    const o = ctx.createBuffer(1, n, ctx.sampleRate);
    o.getChannelData(0).set(b.getChannelData(0).subarray(0, n));
    return o;
  }

  function start() {
    ctx = new (window.AudioContext || window.webkitAudioContext)();
    master = ctx.createGain(); master.gain.value = 0; master.connect(ctx.destination);
    noise = noiseBuffer(2, false);
    // wind: brown noise through a lowpass whose cutoff and level drift slowly
    const wind = ctx.createBufferSource(); wind.buffer = noiseBuffer(6, true); wind.loop = true;
    const lp = ctx.createBiquadFilter(); lp.type = 'lowpass'; lp.frequency.value = 380; lp.Q.value = 0.6;
    const wg = ctx.createGain(); wg.gain.value = 0.22;
    const lfo = ctx.createOscillator(); lfo.frequency.value = 0.07;
    const lfoAmt = ctx.createGain(); lfoAmt.gain.value = 160;
    const lfo2 = ctx.createOscillator(); lfo2.frequency.value = 0.045;
    const lfo2Amt = ctx.createGain(); lfo2Amt.gain.value = 0.09;
    lfo.connect(lfoAmt).connect(lp.frequency); lfo2.connect(lfo2Amt).connect(wg.gain);
    wind.connect(lp).connect(wg).connect(master);
    wind.start(); lfo.start(); lfo2.start();
    // the car idling: two low detuned saws, muffled, gain set by distance each frame
    const o1 = ctx.createOscillator(), o2 = ctx.createOscillator();
    o1.type = o2.type = 'sawtooth'; o1.frequency.value = 31; o2.frequency.value = 46.7;
    const ilp = ctx.createBiquadFilter(); ilp.type = 'lowpass'; ilp.frequency.value = 140;
    idle = ctx.createGain(); idle.gain.value = 0;
    o1.connect(ilp); o2.connect(ilp); ilp.connect(idle).connect(master);
    o1.start(); o2.start();
  }

  A.toggle = () => {
    if (!ctx) start();
    A.on = !A.on;
    if (A.on && ctx.state === 'suspended') ctx.resume();
    master.gain.setTargetAtTime(A.on ? 0.9 : 0, ctx.currentTime, 0.25);
    clearTimeout(A.k);
    if (!A.on) A.k = setTimeout(() => { if (!A.on) ctx.suspend(); }, 1200);   // after the fade, stop the graph
    return A.on;
  };

  // a hidden tab goes quiet (and stops costing battery); coming back resumes only if sound was on
  A.visible = (shown) => {
    if (!ctx) return;
    if (!shown) ctx.suspend(); else if (A.on) ctx.resume();
  };

  function burst(t, dur, freq, q, gain, pan) {
    const s = ctx.createBufferSource(); s.buffer = noise;
    const f = ctx.createBiquadFilter(); f.type = 'bandpass'; f.frequency.value = freq; f.Q.value = q;
    const g = ctx.createGain();
    g.gain.setValueAtTime(0.0001, t); g.gain.exponentialRampToValueAtTime(gain, t + 0.008);
    g.gain.exponentialRampToValueAtTime(0.0001, t + dur);
    const p = ctx.createStereoPanner ? ctx.createStereoPanner() : null;
    s.connect(f).connect(g);
    if (p) { p.pan.value = pan; g.connect(p).connect(master); } else g.connect(master);
    s.start(t, Math.random() * 1.5, dur + 0.05);
  }

  // a footfall: in snow a soft thud and a handful of tiny crackles as the crust gives; on stone a short dry knock
  // with only a crackle or two of the snow left on it; on the road's packed snow a firm, short squeak
  A.step = (foot, strength = 1, surface = 'snow') => {
    if (!A.on) return;
    const t = ctx.currentTime + 0.01, pan = foot ? 0.18 : -0.18;
    if (surface === 'packed') {
      burst(t, 0.09, 300, 1.2, 0.28 * strength, pan);
      burst(t + 0.01, 0.06, 1300, 4.0, 0.07 * strength, pan);
      for (let i = 0; i < 3; i++) {
        burst(t + 0.02 + Math.random() * 0.06, 0.03, 1800 + Math.random() * 1200, 2.5, 0.05 * strength, pan);
      }
      return;
    }
    if (surface === 'stone') {
      burst(t, 0.07, 520, 1.6, 0.34 * strength, pan);
      burst(t + 0.004, 0.05, 1900, 3.0, 0.08 * strength, pan);
      for (let i = 0; i < 2; i++) burst(t + 0.02 + Math.random() * 0.05, 0.03, 2400 + Math.random() * 1600, 2.5, 0.05 * strength, pan);
      return;
    }
    burst(t, 0.16, 220, 0.8, 0.30 * strength, pan);
    const n = 5 + Math.floor(Math.random() * 5);
    for (let i = 0; i < n; i++) burst(t + 0.015 + Math.random() * 0.12, 0.035, 1500 + Math.random() * 2200, 2.5, 0.10 * strength, pan);
  };

  A.breath = (strength = 1) => {
    if (!A.on) return;
    const t = ctx.currentTime + 0.02;
    const s = ctx.createBufferSource(); s.buffer = noise;
    const f = ctx.createBiquadFilter(); f.type = 'bandpass'; f.frequency.value = 900; f.Q.value = 0.7;
    const g = ctx.createGain();
    g.gain.setValueAtTime(0.0001, t); g.gain.exponentialRampToValueAtTime(0.05 * strength, t + 0.18);
    g.gain.exponentialRampToValueAtTime(0.0001, t + 0.9);
    s.connect(f).connect(g).connect(master);
    s.start(t, Math.random(), 1.0);
  };

  // the stop beat: when she stands still by the car, a soft warm chord swells under the wind (and the glow behind her
  // hood brightens with it); k is 0..1
  let pad = null, lastSwell = -1;
  A.swell = (k) => {
    if (!A.on || !ctx) return;
    if (!pad) {
      pad = ctx.createGain(); pad.gain.value = 0;
      const lp = ctx.createBiquadFilter(); lp.type = 'lowpass'; lp.frequency.value = 760; lp.Q.value = 0.4;
      for (const [f, a] of [[146.83, 0.5], [220.0, 0.38], [293.66, 0.3], [329.63, 0.22], [440.0, 0.12]]) {
        const o = ctx.createOscillator(); o.type = 'triangle'; o.frequency.value = f;
        o.detune.value = (Math.random() - 0.5) * 8;
        const g = ctx.createGain(); g.gain.value = a; o.connect(g).connect(lp); o.start();
      }
      lp.connect(pad).connect(master);
    }
    if (Math.abs(k - lastSwell) < 0.02) return;
    lastSwell = k;
    pad.gain.setTargetAtTime(0.07 * k * k, ctx.currentTime, 0.5);
  };

  let lastCar = -1, lastCarT = 0;
  A.car = (dist) => {
    if (!A.on || !idle) return;
    const g = Math.min(0.10, 0.6 / Math.max(dist * dist, 6)), now = ctx.currentTime;
    if (now - lastCarT < 0.1 && Math.abs(g - lastCar) < lastCar * 0.05) return;     // ~10 updates a second
    lastCar = g; lastCarT = now;
    idle.gain.setTargetAtTime(g, now, 0.4);
  };
  return A;
}

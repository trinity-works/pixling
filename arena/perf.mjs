// Frame time of the viewer in a real Chromium: node arena/perf.mjs PAGE.html [seconds]
// For each viewport (1280x720, 1920x1080) and each case (idle in the page's default view, which fits a map bigger than
// the window; idle at 1x; panning at 2x with the
// camera moving every frame), it hooks requestAnimationFrame and reports the work per frame (the callback's time:
// layers, sway, lights, snow, overlays) and the frame interval (dropped frames show as intervals over 16.7 ms).
// Headless Chromium rasterises on the CPU, so this is a pessimistic "modest laptop".
import { createRequire } from 'module';
const require = createRequire(import.meta.url);
let pw;
try { pw = require('playwright'); } catch (_) { pw = require('/opt/node22/lib/node_modules/playwright'); }
const page_ = process.argv[2], secs = +(process.argv[3] || 5);
const hook = () => {
  const orig = window.requestAnimationFrame.bind(window);
  window.__ft = []; window.__iv = []; let last = 0;
  window.requestAnimationFrame = cb => orig(ts => {
    const t0 = performance.now(); cb(ts); const t1 = performance.now();
    if (window.__rec) { window.__ft.push(t1 - t0); if (last) window.__iv.push(ts - last); }
    last = ts;
  });
};
const stat = a => { const s = [...a].sort((x, y) => x - y), m = s.reduce((p, c) => p + c, 0) / s.length;
  return { n: s.length, mean: +m.toFixed(2), p50: +s[Math.floor(s.length / 2)].toFixed(2), p95: +s[Math.floor(s.length * 0.95)].toFixed(2), max: +s[s.length - 1].toFixed(2) }; };
const browser = await pw.chromium.launch();
const out = [];
for (const [w, h] of [[1280, 720], [1920, 1080]]) {
  for (const cs of ['idle', 'idle1x', 'pan2x']) {          // idle: the page's default view (fit when the map is big)
    const page = await browser.newPage({ viewport: { width: w, height: h }, deviceScaleFactor: 1 });
    const errs = [];
    page.on('pageerror', e => errs.push(String(e)));
    await page.addInitScript(hook);
    await page.goto('file://' + page_ + (cs === 'pan2x' ? '?zoom=2' : cs === 'idle1x' ? '?zoom=1' : ''), { waitUntil: 'load' });
    await page.waitForFunction(() => window.__arena && window.__arena.ready, null, { timeout: 120000 });
    await page.waitForTimeout(1500);
    if (cs === 'pan2x') await page.keyboard.down('d');
    await page.evaluate(() => { window.__rec = true; });
    let t = 0;
    while (t < secs * 1000) {          // pan back and forth so the camera keeps moving
      await page.waitForTimeout(500); t += 500;
      if (cs === 'pan2x' && t % 2000 === 0) { await page.keyboard.up(t % 4000 ? 'd' : 'a'); await page.keyboard.down(t % 4000 ? 'a' : 'd'); }
    }
    const r = await page.evaluate(() => ({ ft: window.__ft, iv: window.__iv, st: window.__arena.stats ? window.__arena.stats() : null }));
    out.push({ viewport: `${w}x${h}`, case: cs, work_ms: stat(r.ft), interval_ms: stat(r.iv),
               fps: +(1000 / stat(r.iv).mean).toFixed(1), over_20ms: r.iv.filter(x => x > 20).length, stats: r.st, errors: errs });
    await page.close();
  }
}
await browser.close();
console.log(JSON.stringify(out, null, 1));

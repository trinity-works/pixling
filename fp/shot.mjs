// Screenshots of a built fp world through the real runtime: node fp/shot.mjs '<json job>'
// job: {base: "http://127.0.0.1:PORT/", size: [w, h], shots: [{query: "t=8&pause=1", out: "path.png"}, ...]}
import { createRequire } from 'module';
import { execSync } from 'child_process';
const require = createRequire(import.meta.url);
let pw;
try { pw = require('playwright'); } catch (_) {
  const root = execSync('npm root -g').toString().trim();
  pw = require(root + '/playwright');
}
const job = JSON.parse(process.argv[2]);
const browser = await pw.chromium.launch({ args: ['--use-gl=angle', '--use-angle=swiftshader', '--enable-unsafe-swiftshader', '--ignore-gpu-blocklist'] });
const page = await browser.newPage({ viewport: { width: job.size[0], height: job.size[1] }, deviceScaleFactor: 1 });
const errors = [];
page.on('pageerror', e => errors.push(String(e)));
page.on('console', m => { if (m.type() === 'error' || m.type() === 'warning') errors.push(m.text()); });
if (job.film) {
  // deterministic frames: freeze the page clock, step the sim by 1/fps, render, capture
  const f = job.film;
  await page.goto(job.base + (job.page || 'walk.html') + '?shot=1&pause=1&t=' + f.t0 + (f.query ? '&' + f.query : ''), { waitUntil: 'load' });
  await page.waitForFunction(() => window.__fp && window.__fp.ready, null, { timeout: 120000 });
  for (let i = 0; i < f.frames; i++) {
    await page.evaluate(dt => { window.__fp.step(dt); window.__fp.render(); }, 1 / f.fps);
    await page.screenshot({ path: `${f.dir}/f_${String(i).padStart(4, '0')}.png` });
  }
  console.log('film', f.frames, 'frames ->', f.dir);
}
for (const s of job.shots || []) {
  await page.goto(job.base + (job.page || 'walk.html') + '?shot=1&' + s.query, { waitUntil: 'load' });
  try { await page.waitForFunction(() => window.__fp && window.__fp.ready, null, { timeout: 120000 }); }
  catch (e) { console.log('ERR', s.out, errors.join(' | ')); continue; }
  await page.waitForTimeout(s.wait ?? 400);
  await page.screenshot({ path: s.out });
  console.log('shot', s.out);
}
if (errors.length) console.log('page messages:', [...new Set(errors)].slice(0, 12).join('\n'));
await browser.close();

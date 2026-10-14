// Stills of the arena through its real runtime: node arena/shots.mjs '<json job>'
// job: {page: "/abs/arena.html", size: [w, h], shots: [{query: "pause=1", out: "a.png", clip?: [x, y, w, h], wait?: ms,
//        clicks?: ["#b-grid", ...], expect?: "js expression that must be true after the clicks"}]}
// Opens the page from file:// (as a reader would) and reports page errors.
import { createRequire } from 'module';
import { execSync } from 'child_process';
const require = createRequire(import.meta.url);
let pw;
try { pw = require('playwright'); } catch (_) {
  try { pw = require('/opt/node22/lib/node_modules/playwright'); }
  catch (__) { pw = require(execSync('npm root -g').toString().trim() + '/playwright'); }
}
const job = JSON.parse(process.argv[2]);
const browser = await pw.chromium.launch();
const page = await browser.newPage({ viewport: { width: job.size[0], height: job.size[1] }, deviceScaleFactor: 1 });
const errors = [];
page.on('pageerror', e => errors.push('pageerror: ' + String(e)));
page.on('console', m => { if (m.type() === 'error') errors.push('console: ' + m.text()); });
for (const s of job.shots) {
  await page.goto('file://' + job.page + '?shot=1&' + s.query, { waitUntil: 'load' });
  await page.waitForFunction(() => window.__arena && window.__arena.ready, null, { timeout: 120000 });
  for (const sel of s.clicks || []) await page.click(sel);
  if (s.expect && !(await page.evaluate(s.expect))) errors.push('expect failed: ' + s.expect);
  if (s.live) await page.waitForTimeout(s.live);
  else await page.evaluate(() => window.__arena.render());
  await page.waitForTimeout(s.wait ?? 100);
  const opt = { path: s.out };
  if (s.clip) opt.clip = { x: s.clip[0], y: s.clip[1], width: s.clip[2], height: s.clip[3] };
  await page.screenshot(opt);
  console.log('shot', s.out);
}
console.log(errors.length ? 'ERRORS\n' + [...new Set(errors)].join('\n') : 'no page errors');
await browser.close();

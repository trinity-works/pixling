"""Review page for Gambit exports: units on a board at game size, every state x facing on the real clock,
the raw takes beside them.

  python3 -m reel page <name> <name2> [--out DIR]   -> out/reel/_review/index.html (+ f/ assets)
"""
from __future__ import annotations

import json
import shutil
import subprocess

import sys
from pathlib import Path

from .take import OUT, ROOT

HTML = r"""<title>__TITLE__</title><style>
/* layout: board stage on top, then one panel per unit with every state x facing on the game clock */
:root{--bg:#121820;--panel:#1b222c;--ink:#e9e6df;--dim:#98a0a8;--acc:#efb94f;--line:#3a4450;color-scheme:dark}
@media (prefers-color-scheme: light){:root:not([data-theme="dark"]){--bg:#e9ecef;--panel:#fbfbfa;--ink:#1c2026;--dim:#56606a;--acc:#9a6a08;--line:#c7ccd2;color-scheme:light}}
:root[data-theme="light"]{--bg:#e9ecef;--panel:#fbfbfa;--ink:#1c2026;--dim:#56606a;--acc:#9a6a08;--line:#c7ccd2;color-scheme:light}
*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--ink);font:15px/1.45 system-ui,sans-serif}
main{max-width:1180px;margin:0 auto;padding:20px 16px 60px}.cell{min-width:0}h1{font-size:22px;margin:0 0 4px}
.sub{color:var(--dim);margin:0 0 16px;max-width:760px}
#board{width:100%;max-width:560px;display:block;margin:0 auto;border-radius:12px;background:#1a2129}
.ctl{display:flex;gap:8px;flex-wrap:wrap;margin:12px 0 20px;align-items:center;justify-content:center;color:var(--dim)}
button{background:var(--panel);color:var(--ink);border:1px solid var(--line);border-radius:6px;padding:5px 10px;cursor:pointer;font:inherit}
button.on{border-color:var(--acc);color:var(--acc)}button:focus-visible{outline:2px solid var(--acc);outline-offset:2px}
section{background:var(--panel);border-radius:10px;padding:14px;margin:0 0 16px;overflow:hidden}
section h2{font-size:17px;margin:0 0 6px}.meta{color:var(--dim);font-size:13px;margin:0 0 10px}
.grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(150px,1fr));gap:10px}
.cell{background:#2b3a2c;border-radius:8px;padding:4px;text-align:center;font-size:12px;color:#dfe8d6}
.cell canvas{width:100%;height:auto;display:block}
.onions{display:flex;gap:10px;flex-wrap:wrap}.onions figure{margin:0;width:150px;max-width:45%;text-align:center;font-size:12px;color:var(--dim)}.onions img{width:100%;background:#2b3a2c;border-radius:8px}.qc{color:var(--dim);font-size:13px;margin:4px 0 10px;padding-left:18px}h3.meta{margin:12px 0 6px}.takes{display:flex;gap:10px;flex-wrap:wrap;margin-top:10px}.takes video{width:220px;max-width:100%;border-radius:6px;background:#000}
</style><main>
<h1>__H1__</h1>
<p class="sub">__SUB__</p>
<canvas id="board" width="560" height="620"></canvas>
<div class="ctl">state <span id="st"></span> <span style="width:12px"></span> zoom <button data-z="0.5">game</button><button data-z="1" class="on">2x</button>
<span style="width:12px"></span><button id="slow">¼ speed</button></div>
<div id="chars"></div></main><script>
const D=__DATA__;const ROWS=D.rows;let Z=1,SLOW=1,STATE='idle';const imgs={};
function img(src){if(!imgs[src]){imgs[src]=new Image();imgs[src].src=src}return imgs[src]}
function frameAt(a,t){const n=a.frames,d=a.frameDuration*1000;let i=Math.floor(t/d);
 if(a.loop)return i%n;const cyc=n+8;i=i%cyc;return Math.min(i,n-1)}   // one-shots hold the last frame briefly
const bc=document.getElementById('board'),bx=bc.getContext('2d');
const units=[];const nc=D.chars.length;D.chars.forEach((c,ci)=>{const x=nc===1?280:170+ci*220;units.push({c,row:'ne',x:nc===1?190:x,y:470});units.push({c,row:'sw',x:nc===1?370:x,y:190});if(nc===1){units.push({c,row:'se',x:190,y:190});units.push({c,row:'nw',x:370,y:470})}});
function drawBoard(t){bx.fillStyle='#1a2129';bx.fillRect(0,0,bc.width,bc.height);const T=92;
 for(let r=0;r<6;r++)for(let q=0;q<6;q++){bx.fillStyle=(r+q)%2?'#4a5654':'#525f5c';if(r>=3){bx.fillStyle=(r+q)%2?'#4c6450':'#546d57'}
 bx.fillRect(4+q*T,34+r*T,T,T)}
 for(const u of units){const a=u.c.anims[STATE]||u.c.anims.idle;const s=u.c.states[STATE]||u.c.states.idle;
  const im=img(s.sheet);const cell=u.c.cell;const k=(T*1.55)/cell*Z;const i=frameAt(a,t);
  let row=a.singleRow?0:ROWS.indexOf(u.row);
  bx.fillStyle='rgba(0,0,0,.28)';bx.beginPath();bx.ellipse(u.x,u.y,26*Z,8*Z,0,0,7);bx.fill();
  if(im.complete)bx.drawImage(im,i*cell,row*cell,cell,cell,u.x-cell*0.5*k,u.y-cell*0.59*k,cell*k,cell*k)}}
const cells=[];const root=document.getElementById('chars');
for(const c of D.chars){const s=document.createElement('section');s.innerHTML=`<h2>${c.name}</h2><p class="meta">${Object.entries(c.anims).map(([k,a])=>`${k} ${a.frames}f @ ${a.frameDuration}s`).join(' · ')} · hit frame ${c.hit} · cell ${c.cell}px</p><div class="grid"></div><h3 class="meta">Attack onion skins (keys tinted blue to red, with a weapon-tip trail)</h3><div class="onions"></div><h3 class="meta">QC flags</h3><ul class="qc"></ul><div class="takes"></div>`;
 root.appendChild(s);const g=s.querySelector('.grid');
 for(const [st,a] of Object.entries(c.anims)){const rows=a.singleRow?[ROWS[1]]:ROWS;for(const r of rows){
  const d=document.createElement('div');d.className='cell';const cv=document.createElement('canvas');cv.width=c.cell;cv.height=c.cell;
  d.appendChild(cv);d.appendChild(document.createTextNode(`${st} · ${r}`));g.appendChild(d);cells.push({cv,c,st,a,row:rows.indexOf(r)})}}
 const on=s.querySelector('.onions');for(const o of c.onions||[]){const f=document.createElement('figure');f.innerHTML=`<img src="${o.src}" alt="onion ${o.label}"><figcaption>${o.label}</figcaption>`;on.appendChild(f)}
 const q=s.querySelector('.qc');const fl=c.qc||[];if(!fl.length)q.innerHTML='<li>none</li>';for(const x of fl){const li=document.createElement('li');li.textContent=x;q.appendChild(li)}
 const tk=s.querySelector('.takes');for(const v of c.takes){const e=document.createElement('video');e.src=v;e.muted=true;e.loop=true;e.autoplay=true;e.playsInline=true;e.controls=true;tk.appendChild(e)}}
const stEl=document.getElementById('st');for(const st of Object.keys(D.chars[0].anims)){const b=document.createElement('button');b.textContent=st;if(st===STATE)b.classList.add('on');
 b.onclick=()=>{STATE=st;stEl.querySelectorAll('button').forEach(x=>x.classList.toggle('on',x===b))};stEl.appendChild(b)}
document.querySelectorAll('[data-z]').forEach(b=>b.onclick=()=>{Z=+b.dataset.z;document.querySelectorAll('[data-z]').forEach(x=>x.classList.toggle('on',x===b))});
document.getElementById('slow').onclick=e=>{SLOW=SLOW===1?0.25:1;e.target.classList.toggle('on',SLOW!==1)};
let t=0,last=performance.now();
function tick(now){t+=(now-last)*SLOW;last=now;drawBoard(t);
 for(const x of cells){const ctx=x.cv.getContext('2d');ctx.clearRect(0,0,x.cv.width,x.cv.height);const im=img(x.c.states[x.st].sheet);
  if(im.complete)ctx.drawImage(im,frameAt(x.a,t)*x.c.cell,x.row*x.c.cell,x.c.cell,x.c.cell,0,0,x.c.cell,x.c.cell)}
 requestAnimationFrame(tick)}requestAnimationFrame(tick);
</script>"""


def make(names, out=None):
    page = Path(out) if out else OUT / "_review"
    (page / "f").mkdir(parents=True, exist_ok=True)
    chars = []
    for n in names:
        g = OUT / n / "gambit"
        actor = json.loads((g / f"{n}.json").read_text())
        states = {}
        for st, a in actor["anims"].items():
            srcf = g / f"{a['file']}.png"
            dst = f"f/{n}_{srcf.name}"
            shutil.copy(srcf, page / dst)
            states[st] = {"sheet": dst}
        spec = json.loads((ROOT / "reel" / "chars" / n / "char.json").read_text())
        takes = []
        for st, clip in spec["gambit"]["clips"].items():
            for rel in [r for v in clip["takes"].values() for r in (v if isinstance(v, list) else [v])]:
                src = ROOT / "reel" / "chars" / n / rel
                if src.exists():
                    dst = page / "f" / f"{n}_{src.name}"
                    if not dst.exists() or dst.stat().st_mtime < src.stat().st_mtime:
                        subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", str(src), "-vf", "scale=480:-2", "-an",
                                        "-c:v", "libx264", "-crf", "28", "-pix_fmt", "yuv420p", str(dst)], check=True)
                    takes.append(f"f/{n}_{src.name}")
        onions = []
        for o in sorted(g.glob("onion_*.png")):
            shutil.copy(o, page / "f" / f"{n}_{o.name}")
            onions.append({"src": f"f/{n}_{o.name}", "label": o.stem.replace("onion_", "").replace("_", " ")})
        qc = json.loads((g / "qc.json").read_text()) if (g / "qc.json").exists() else {}
        flags = [f"{st} {d}: " + "; ".join(r["flags"]) for st, dd in qc.items() for d, r in dd.items() if r.get("flags")]
        chars.append({"name": n.title(), "cell": actor["cell"], "anims": actor["anims"], "states": states,
                      "hit": actor["attackHitFrame"], "takes": takes, "onions": onions, "qc": flags})
    # row order comes from the export ("dirs"); older 4-row exports without it are FR, FL, BR, BL
    rows = chars[0]["anims"]["idle"].get("dirs") or ["se", "sw", "ne", "nw"]
    nrows = len(rows)
    names_t = " and ".join(c["name"] for c in chars)
    html = HTML.replace("__DATA__", json.dumps({"chars": chars, "rows": rows}))
    html = html.replace("__TITLE__", f"{names_t} Reel").replace("__H1__", f"{names_t}, cut from video")
    an = chars[0]["anims"]
    clock = ", ".join(f"{k} {a['frames']}f at {a['frameDuration']} s" for k, a in an.items())
    sub = (f"Video takes keyed and cut to the game clock: {clock}; the strike lands on frame {chars[0]['hit']}. "
           f"{'Eight facings in the order S, SE, E, NE, N, NW, W, SW; the west side mirrors the east. ' if nrows == 8 else ''}"
           "Attack keys follow poses (anticipation, apex, strike, contact, recovery); walks start on a foot contact "
           "with the planted foot on the ground. One palette and one redrawn outline per character.")
    html = html.replace("__SUB__", sub)
    (page / "index.html").write_text(html)
    return page


if __name__ == "__main__":
    a = sys.argv[1:]
    out = a[a.index("--out") + 1] if "--out" in a else None
    names = [x for x in a if not x.startswith("--") and x != out]
    print(make(names, out))

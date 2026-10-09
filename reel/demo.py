"""Playable 8-direction demo of reel characters: walk them around a board, attack and cast, on the export's clock.

  python3 -m reel demo <name> <name2> [--fx fireball_rain,necro_signet] [--out DIR]
      -> out/reel/_demo/index.html + f/ (WebP copies of the sheets)

Click the ground to walk (the facing comes from the move vector over all 8 sectors), click a unit to walk into
range and attack it, Space attacks where you face, arrows / WASD walk, Tab switches unit. 1/2/... (or the cast
buttons) cast the --fx spells (out/reel/_fx/<name>, see reel/fx.py) on the nearest other unit: the caster attacks
toward it, the effect draws additively at its feet and it flashes on each of the effect's impact frames.
Reads out/reel/<name>/gambit/<name>.json and its sheets (row order in anims[state]["dirs"]); body, feet and
display_scale come from reel/chars/<name>/char.json.
"""
from __future__ import annotations

import json
import shutil
from pathlib import Path

from PIL import Image

from .take import OUT, ROOT

HTML = r"""<title>__TITLE__</title>
<style>
/* layout: one board canvas filling the width, a slim control bar under it; deliberately one dark look (a game screen) */
:root{--bg:#10151b;--panel:#18202a;--ink:#e8e4da;--dim:#8f99a3;--acc:#f0b64a;--line:#2e3945;color-scheme:dark}
*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--ink);font:15px/1.45 system-ui,-apple-system,sans-serif}
main{max-width:980px;margin:0 auto;padding:18px 16px 40px}
h1{font-size:20px;margin:0 0 2px;letter-spacing:.01em}.sub{color:var(--dim);margin:0 0 12px;font-size:14px;max-width:70ch}
#stage{position:relative;max-width:100%}
canvas{display:block;width:100%;max-width:100%;height:auto;border-radius:12px;background:#1a222b;touch-action:none;cursor:crosshair}
.bar{display:flex;flex-wrap:wrap;gap:8px;align-items:center;margin-top:10px;color:var(--dim);font-size:13px}
button{background:var(--panel);color:var(--ink);border:1px solid var(--line);border-radius:6px;padding:5px 10px;font:inherit;cursor:pointer}
button.on{border-color:var(--acc);color:var(--acc)}button:focus-visible{outline:2px solid var(--acc);outline-offset:2px}
.sep{width:10px}.keys{margin-top:8px;color:var(--dim);font-size:13px}kbd{background:var(--panel);border:1px solid var(--line);border-radius:4px;padding:0 5px;font:12px ui-monospace,monospace;color:var(--ink)}
</style>
<main>
<h1>__H1__</h1>
<p class="sub">__SUB__</p>
<div id="stage"><canvas id="c" width="960" height="600" aria-label="demo board"></canvas></div>
<div class="bar">control <span id="who"></span><span class="sep"></span>speed <button data-s="1" class="on">1x</button><button data-s="0.25">¼x</button>
<span class="sep"></span>size <button data-z="1" class="on">game</button><button data-z="1.8">close-up</button><span class="sep"></span><span id="spells"></span><span class="sep"></span><span id="readout"></span></div>
<p class="keys">Click the ground to walk · click a unit to attack it · <kbd>Space</kbd> attack · <kbd>←↑→↓</kbd> / <kbd>WASD</kbd> walk · <kbd>Tab</kbd> switch unit<span id="fxkeys"></span></p>
</main>
<script>
const D=__DATA__;
const DIRS=["s","se","e","ne","n","nw","w","sw"];
const cv=document.getElementById('c'),cx=cv.getContext('2d');
const imgs={};function img(s){if(!imgs[s]){imgs[s]=new Image();imgs[s].src=s}return imgs[s]}
let SPEED=1,ZOOM=1,T=0,last=performance.now();
const TILE=64;
// unit scale: the body is ~27% of the cell; draw so the body is ~1.35 tiles tall at "game" size
function unitScale(c){return (TILE*1.35)/(c.cell*c.body)*(c.show||1)}   // show: per-character size (taller heroic builds)
function dirOf(dx,dy){const a=Math.atan2(dy,dx);const k=Math.round(a/(Math.PI/4));return ["e","se","s","sw","w","nw","n","ne"][(k+8)%8]}
const FX=D.fx||[],casts=[];
function nearestFoe(u){let b=null,bd=1e9;for(const o of units)if(o!==u){const d=Math.hypot(o.x-u.x,o.y-u.y);if(d<bd){bd=d;b=o}}return b}
function cast(i){const u=units[me],f=FX[i],foe=nearestFoe(u);if(!f||!foe||u.state==='attack')return;
 u.dir=dirOf(foe.x-u.x,foe.y-u.y);u.foe=null;u.target=null;u.chase=null;setState(u,'attack');
 casts.push({f,foe,x:foe.x,y:foe.y,t0:T+anim(u,'attack').frameDuration*1000*Math.max(0,u.c.hit-1),done:{}})}
function drawCasts(layer){for(let j=casts.length-1;j>=0;j--){const k=casts[j],f=k.f,i=Math.floor((T-k.t0)/(f.frameDuration*1000));
 if(i>=f.frames){casts.splice(j,1);continue}if(i<0||f.layer!==layer)continue;
 if(f.hits.includes(i)&&!k.done[i]){k.done[i]=1;k.foe.flash=0.12;k.foe.kick=4;k.foe.kx=0;k.foe.ky=1}
 const im=img(f.sheet);if(!im.complete)continue;const W=f.tiles*TILE*ZOOM,H=W*f.h/f.w;
 cx.globalCompositeOperation='lighter';cx.drawImage(im,i*f.w,0,f.w,f.h,k.x-f.anchor[0]*W,k.y-f.anchor[1]*H,W,H);cx.globalCompositeOperation='source-over'}}
const units=D.chars.map((c,i)=>({c,x:cv.width*(i+1)/(D.chars.length+1),y:330+(i%2)*60,dir:i?"sw":"se",state:"idle",t0:0,target:null,foe:null,hitDone:false,flash:0,kick:0}));
let me=0;
function anim(u,st){return u.c.anims[st]||u.c.anims.idle}
function setState(u,st){if(u.state!==st){u.state=st;u.t0=T;u.hitDone=false}}
function attack(u,foe){if(u.state==='attack')return;if(foe){u.dir=dirOf(foe.x-u.x,(foe.y-u.y));u.foe=foe}else u.foe=null;u.target=null;setState(u,'attack')}
function frame(u){const a=anim(u,u.state),ms=a.frameDuration*1000,i=Math.floor((T-u.t0)/ms);return a.loop?i%a.frames:Math.min(i,a.frames-1)}
function walkSpeed(u){return TILE*1.6*ZOOM}                         // ground px per second, matched to the 0.8 s stride
function reach(u){return TILE*1.25*ZOOM}
function update(dt){
 for(const u of units){
  if(u.state==='attack'){const a=anim(u,'attack');const f=frame(u);
   if(!u.hitDone&&f>=u.c.hit-1&&u.foe){u.hitDone=true;u.foe.flash=0.12;const d=Math.hypot(u.foe.x-u.x,u.foe.y-u.y)||1;u.foe.kick=6;u.foe.kx=(u.foe.x-u.x)/d;u.foe.ky=(u.foe.y-u.y)/d}
   if(T-u.t0>=a.frames*a.frameDuration*1000){setState(u,'idle');u.foe=null}
   continue}
  let goal=u.target;if(u.chase){const d=Math.hypot(u.chase.x-u.x,u.chase.y-u.y);if(d<=reach(u)){const f=u.chase;u.chase=null;attack(u,f);continue}goal={x:u.chase.x,y:u.chase.y}}
  const key=u===units[me]?keyVec():null;
  if(key&&(key[0]||key[1])){u.target=null;u.chase=null;goal={x:u.x+key[0]*100,y:u.y+key[1]*100}}
  if(goal){const dx=goal.x-u.x,dy=goal.y-u.y,d=Math.hypot(dx,dy);
   if(d<2){u.target=null;setState(u,'idle')}else{u.dir=dirOf(dx,dy);const s=Math.min(d,walkSpeed(u)*dt);u.x+=dx/d*s;u.y+=dy/d*s;setState(u,'walk')}}
  else if(u.state!=='idle')setState(u,'idle');
  u.x=Math.max(40,Math.min(cv.width-40,u.x));u.y=Math.max(90,Math.min(cv.height-20,u.y))}
 for(const u of units){u.flash=Math.max(0,u.flash-dt);u.kick=Math.max(0,u.kick-dt*40)}}
const down=new Set();addEventListener('keydown',e=>{if(['ArrowUp','ArrowDown','ArrowLeft','ArrowRight',' ','Tab'].includes(e.key))e.preventDefault();
 if(e.key===' ')attack(units[me],null);else if(/^[1-9]$/.test(e.key))cast(+e.key-1);else if(e.key==='Tab'){me=(me+1)%units.length;refresh()}else down.add(e.key.toLowerCase())});
addEventListener('keyup',e=>down.delete(e.key.toLowerCase()));
function keyVec(){let x=0,y=0;if(down.has('arrowleft')||down.has('a'))x--;if(down.has('arrowright')||down.has('d'))x++;if(down.has('arrowup')||down.has('w'))y--;if(down.has('arrowdown')||down.has('s'))y++;return [x,y]}
cv.addEventListener('pointerdown',e=>{const r=cv.getBoundingClientRect(),x=(e.clientX-r.left)*cv.width/r.width,y=(e.clientY-r.top)*cv.height/r.height;
 const u=units[me];const hit=units.find(o=>o!==u&&Math.hypot(o.x-x,o.y-(y+20*ZOOM))<34*ZOOM);
 if(hit){u.chase=hit;u.target=null}else{u.target={x,y};u.chase=null}});
function drawBoard(){cx.fillStyle='#1a222b';cx.fillRect(0,0,cv.width,cv.height);
 for(let r=0;r*TILE<cv.height;r++)for(let q=0;q*TILE<cv.width;q++){cx.fillStyle=(r+q)%2?'#46524f':'#4e5c58';cx.fillRect(q*TILE,r*TILE,TILE,TILE)}
 cx.fillStyle='rgba(0,0,0,.18)';cx.fillRect(0,0,cv.width,40)}
function drawUnit(u){const c=u.c,a=anim(u,u.state),im=img(c.sheets[u.state]||c.sheets.idle);const row=a.singleRow?0:(a.dirs||DIRS).indexOf(u.dir);
 const k=unitScale(c)*ZOOM,w=c.cell*k,ox=u.kick*(u.kx||0),oy=u.kick*(u.ky||0);
 cx.fillStyle='rgba(0,0,0,.30)';cx.beginPath();cx.ellipse(u.x,u.y,22*ZOOM,7*ZOOM,0,0,7);cx.fill();
 if(u===units[me]){cx.strokeStyle='#f0b64a';cx.lineWidth=2;cx.beginPath();cx.ellipse(u.x,u.y,26*ZOOM,9*ZOOM,0,0,7);cx.stroke()}
 if(!im.complete)return;
 cx.drawImage(im,frame(u)*c.cell,row*c.cell,c.cell,c.cell,u.x+ox-c.cell*c.fx*k,u.y+oy-c.cell*c.fy*k,w,w);
 if(u.flash>0){cx.globalCompositeOperation='lighter';cx.globalAlpha=Math.min(1,u.flash*8)*0.55;cx.drawImage(im,frame(u)*c.cell,row*c.cell,c.cell,c.cell,u.x+ox-c.cell*c.fx*k,u.y+oy-c.cell*c.fy*k,w,w);cx.globalAlpha=1;cx.globalCompositeOperation='source-over'}}
function drawHud(){const u=units[me];cx.fillStyle='#e8e4da';cx.font='14px system-ui';cx.fillText(`${u.c.name} · ${u.state} · facing ${u.dir.toUpperCase()}`,14,25);
 const X=cv.width-44,Y=20,R=13;cx.strokeStyle='#8f99a3';cx.lineWidth=1.5;cx.beginPath();cx.arc(X,Y+2,R,0,7);cx.stroke();
 const i=["e","se","s","sw","w","nw","n","ne"].indexOf(u.dir),ang=i*Math.PI/4;cx.strokeStyle='#f0b64a';cx.lineWidth=3;cx.beginPath();cx.moveTo(X,Y+2);cx.lineTo(X+Math.cos(ang)*R,Y+2+Math.sin(ang)*R);cx.stroke()}
function tick(now){const dt=Math.min(0.05,(now-last)/1000)*SPEED;last=now;T+=dt*1000;update(dt);drawBoard();
 drawCasts('under');[...units].sort((a,b)=>a.y-b.y).forEach(drawUnit);drawCasts('over');drawHud();requestAnimationFrame(tick)}
const who=document.getElementById('who');
function refresh(){who.innerHTML='';units.forEach((u,i)=>{const b=document.createElement('button');b.textContent=u.c.name;if(i===me)b.classList.add('on');b.onclick=()=>{me=i;refresh()};who.appendChild(b)});
 const c=units[me].c;document.getElementById('readout').textContent=Object.entries(c.anims).map(([k,a])=>`${k} ${a.frames}f@${a.frameDuration}s`).join(' · ')+` · hit on frame ${c.hit}`}
document.querySelectorAll('[data-s]').forEach(b=>b.onclick=()=>{SPEED=+b.dataset.s;document.querySelectorAll('[data-s]').forEach(x=>x.classList.toggle('on',x===b))});
document.querySelectorAll('[data-z]').forEach(b=>b.onclick=()=>{ZOOM=+b.dataset.z;document.querySelectorAll('[data-z]').forEach(x=>x.classList.toggle('on',x===b))});
document.getElementById('fxkeys').innerHTML=FX.map((f,i)=>` · <kbd>${i+1}</kbd> ${f.title}`).join('');
const sp=document.getElementById('spells');if(FX.length){sp.append('cast ');FX.forEach((f,i)=>{const b=document.createElement('button');b.textContent=f.title;b.onclick=()=>cast(i);sp.appendChild(b)})}
refresh();requestAnimationFrame(tick);
</script>"""


def _webp(src, dst, lossless=True):
    """Sheets ship as WebP: lossless for sprites (pixel-exact, ~3.5x smaller than PNG), lossy for additive effects
    (soft glow hides it, ~3x smaller). The PNG masters in out/reel stay untouched for the game contract."""
    im = Image.open(src).convert("RGBA")
    if lossless:
        im.save(dst, "WEBP", lossless=True, quality=100, method=6)
    else:
        im.save(dst, "WEBP", quality=80, alpha_quality=90, method=6)


def make(names, out=None, fx=()):
    page = Path(out) if out else OUT / "_demo"
    if (page / "f").exists():
        shutil.rmtree(page / "f")                    # stale sheets of units no longer in the demo
    (page / "f").mkdir(parents=True, exist_ok=True)
    spells = []
    for n in fx:
        m = json.loads((OUT / "_fx" / n / f"{n}.json").read_text())
        dst = f"f/fx_{n}.webp"
        _webp(OUT / "_fx" / n / f"{m['file']}.png", page / dst, lossless=False)
        spells.append({**m, "sheet": dst, "title": n.replace("_", " ").title()})
    chars = []
    for n in names:
        g = OUT / n / "gambit"
        actor = json.loads((g / f"{n}.json").read_text())
        spec_path = ROOT / "reel" / "chars" / n / "char.json"
        gs = json.loads(spec_path.read_text()).get("gambit", {}) if spec_path.exists() else {}
        sheets = {}
        for st, a in actor["anims"].items():
            if len(a.get("dirs") or []) != 8 and not a.get("singleRow"):
                raise SystemExit(f"{n}/{st}: the demo needs an 8-direction export (\"rows\": 8); got {a.get('rows')}")
            dst = f"f/{n}_{a['file']}.webp"
            _webp(g / f"{a['file']}.png", page / dst, lossless=True)
            sheets[st] = dst
        chars.append({"name": n.replace("_", " ").title(), "cell": actor["cell"], "anims": actor["anims"], "sheets": sheets,
                      "hit": actor["attackHitFrame"], "body": gs.get("body", 0.27),
                      "fx": gs.get("feet_x", 0.5), "fy": gs.get("feet_y", 0.59),
                      "show": gs.get("display_scale", 1.0)})
    names_t = ", ".join(c["name"] for c in chars)
    sub = ("Sprites cut from AI video, in eight facings (S, SE, E, NE, N and their mirrors), each state on its own "
           "clock. The facing follows the direction you move or attack."
           + (" Spells are effects generated on black and drawn additively on the nearest enemy." if spells else ""))
    html = (HTML.replace("__DATA__", json.dumps({"chars": chars, "fx": spells}))
            .replace("__TITLE__", "Reel Fighters Demo").replace("__H1__", f"{names_t}: eight-direction demo")
            .replace("__SUB__", sub))
    (page / "index.html").write_text(html)
    return page


"""CLI: python3 -m reel <command> ...

  split <sheet.png> [--names s,se,e,ne,n]   one-row facing sheet -> ref/start_<facing>.png on one baseline
  gambit <char.json>                  takes -> keyed, cut, finished 8-direction sheets + actor json + qc.json
  fx <spec.json>                      spell effect on black -> additive overlay sheet (out/reel/_fx/<name>)
  demo <name> [<name> ...] [--fx a,b] [--out D]   playable 8-direction demo: walk, attack, cast spells
  page <name> [<name> ...] [--out D]  review page: board at game size, every state x facing, onions, raw takes
  contact <video> [--every 2]         numbered sheet of a take's frames, for picking keys by eye
  key <video> [--color auto]          key one take, write a matte check (source | magenta | white | black)
  probe <video>                       size / fps / frame count
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="reel")
    sub = ap.add_subparsers(dest="cmd", required=True)
    gm = sub.add_parser("gambit")
    gm.add_argument("spec")
    pg = sub.add_parser("page")
    pg.add_argument("names", nargs="+")
    pg.add_argument("--out")
    dm = sub.add_parser("demo")
    dm.add_argument("names", nargs="+")
    dm.add_argument("--out")
    dm.add_argument("--fx", default="")
    fx = sub.add_parser("fx")
    fx.add_argument("spec")
    k = sub.add_parser("key")
    k.add_argument("video")
    k.add_argument("--color", default="auto")
    k.add_argument("--out")
    ct = sub.add_parser("contact")
    ct.add_argument("video")
    ct.add_argument("--color", default="auto")
    ct.add_argument("--every", type=int, default=2)
    ct.add_argument("--out")
    p = sub.add_parser("probe")
    p.add_argument("video")
    sp = sub.add_parser("split")
    sp.add_argument("sheet")
    sp.add_argument("--names", default="s,se,e,ne,n")
    sp.add_argument("--size", type=int, default=2048)
    sp.add_argument("--out")
    a = ap.parse_args(argv)

    if a.cmd == "gambit":
        from .game import export
        print(f"-> {export(a.spec)}")
    elif a.cmd == "page":
        from .page import make
        print(make(a.names, a.out))
    elif a.cmd == "demo":
        from .demo import make as demo
        print(demo(a.names, a.out, [x for x in a.fx.split(",") if x]))
    elif a.cmd == "fx":
        from .fx import export as fx_export
        print(f"-> {fx_export(a.spec)}")
    elif a.cmd == "split":
        from .split import split
        for n, f in split(a.sheet, a.names.split(","), a.size, out=a.out).items():
            print(f"{n}: {f}")
    elif a.cmd == "probe":
        from .io import probe
        print(probe(a.video))
    elif a.cmd in ("key", "contact"):
        from . import cut, pack
        from .take import OUT, key_cfg, key_take
        cfg = key_cfg({"key": {"color": a.color}})
        out = Path(a.out or OUT / "_check" / Path(a.video).stem)
        cels, src = key_take(Path(a.video), cfg, out / "cache", "take", keep_src=a.cmd == "key")
        if a.cmd == "key":
            if not src:                       # cached: re-decode for the source views
                cels, src = key_take(Path(a.video), cfg, out / "cache_src", "take", keep_src=True)
            pack.matte_check(src, cels, out / "matte.png")
            print(f"-> {out / 'matte.png'}")
        else:
            ref = cels[0]
            cut.contact(cels[:: a.every], ref.feet, 160 / max(1, cut.height(ref)), out / "contact.png")
            print(f"-> {out / 'contact.png'}  (cell i = source frame i*{a.every})")
    return 0


if __name__ == "__main__":
    sys.exit(main())

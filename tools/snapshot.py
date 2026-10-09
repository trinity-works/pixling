"""Byte-identity gate: build every spec to /tmp and hash the sheets, so an engine change can prove it left
assets that don't use it untouched.

  python3 tools/snapshot.py save base          # before the change
  python3 tools/snapshot.py check base         # after: lists every spec whose sheets changed
  python3 tools/snapshot.py check base --full  # all clips x all directions (slow); default is a quick subset

Quick = idle, walk, attack in S and E (props: their own clips/dirs). Builds go to /tmp/pp_snapshot/, never out/.
"""
from __future__ import annotations

import argparse
import glob
import hashlib
import json
import os
import sys
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
TMP = Path("/tmp/pp_snapshot")
QUICK_CLIPS = ["idle", "walk", "attack"]
QUICK_DIRS = ["S", "E"]


def specs(pattern=None):
    out = [f for f in sorted(glob.glob(str(ROOT / "specs" / "**" / "*.json"), recursive=True))
           if not f.endswith(".map.json")]
    return [f for f in out if not pattern or pattern in f]


def _one(args):
    path, full = args
    from pp.forge import Forge, load_spec
    spec = load_spec(path)
    rel = os.path.relpath(path, ROOT)
    dirs = None
    if not full:
        from pp import anim as A
        have = spec.get("clips") or list(A.RIGS.get(spec.get("rig", "humanoid"), {})) or ["idle"]
        spec["clips"] = [c for c in have if c in QUICK_CLIPS] or have[:1]
        own = spec.get("directions")
        dirs = [d for d in QUICK_DIRS if not own or d in own] or own[:1]
    out = TMP / "build" / rel.replace("/", "__")[:-5]
    try:
        Forge(spec).build(out, dirs, preview_scale=1)
    except Exception as e:     # a spec that fails to build is a change too
        return rel, "ERROR %s: %s" % (type(e).__name__, e)
    h = hashlib.sha1()
    for p in sorted(out.glob("*.png")) + sorted(out.glob("*.json")):
        h.update(p.name.encode())
        h.update(p.read_bytes())
    return rel, h.hexdigest()


def run(full: bool, pattern=None):
    todo = [(s, full) for s in specs(pattern)]
    with ProcessPoolExecutor(max(1, (os.cpu_count() or 2) - 1)) as ex:
        return dict(ex.map(_one, todo))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("cmd", choices=["save", "check"])
    ap.add_argument("label")
    ap.add_argument("--full", action="store_true")
    ap.add_argument("--only", help="substring filter on spec paths")
    a = ap.parse_args()
    TMP.mkdir(parents=True, exist_ok=True)
    tag = "%s%s.json" % (a.label, "_full" if a.full else "")
    got = run(a.full, a.only)
    if a.cmd == "save":
        (TMP / tag).write_text(json.dumps(got, indent=1))
        bad = [k for k, v in got.items() if v.startswith("ERROR")]
        print("saved %d specs -> %s%s" % (len(got), TMP / tag, (" (%d fail to build)" % len(bad)) if bad else ""))
        return 0
    base = json.loads((TMP / tag).read_text())
    changed = sorted(k for k in got if k in base and base[k] != got[k])
    new = sorted(k for k in got if k not in base)
    for k in changed:
        print("CHANGED", k, "" if not got[k].startswith("ERROR") else got[k])
    for k in new:
        print("NEW", k)
    print("%d specs, %d changed" % (len(got), len(changed)))
    return 1 if changed else 0


if __name__ == "__main__":
    sys.exit(main())

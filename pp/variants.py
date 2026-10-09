"""Variants: build a few deliberate versions of one spec side by side, pick one by eye, apply it.

  python3 -m pp variants specs/<style>/<name>.json --vary anim.attack_style=slash,heavy,dart \\
          --vary anim.drag=0.6,1,1.5 --clips attack --dirs E,S
  python3 -m pp variants specs/<style>/<name>.json --vary anim.drag=0.4..1.6 --sample 6 --seed 3
  python3 -m pp variants specs/<style>/<name>.json --apply 4      # write variant 4's overrides into the spec

Every row is labelled with its exact overrides; row 0 is the spec as it is. Values are explicit lists
(cartesian product) or ranges sampled with keyed draws: a draw depends only on (seed, row, key), so adding
another --vary never reshuffles the others. Each variant is an ordinary build (in /tmp/pp_variants/<name>/);
the grid is read back from those sheets. A row that renders exactly like an earlier one is flagged (the spec
ignores that override), and each row carries its build's lint WARN lines.
Keys are dotted paths; list items with a "name" are addressed by it: bones.head.parts.0.r
"""
from __future__ import annotations

import copy
import hashlib
import itertools
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional

import numpy as np
from PIL import Image, ImageDraw

TMP = Path("/tmp/pp_variants")
MAX_ROWS = 16
# overrides under these keys leave geometry alone, so variants can share the base model's layer cache
SHARES_GEOMETRY = ("anim", "clips", "custom_clips", "layers", "life", "attach", "smear", "fx", "shadow")
LABEL_H, PAD, GUTTER = 12, 4, 40


def keyed(seed, *keys) -> float:
    """Order-independent draw in [0, 1) for (seed, keys...): the same keys always
    give the same value, whatever else is drawn."""
    h = hashlib.sha1("|".join(str(k) for k in (seed,) + keys).encode()).digest()
    return int.from_bytes(h[:8], "big") / 2 ** 64


def set_path(spec: Dict, key: str, value) -> None:
    """spec["a"]["b"][0] = value for key "a.b.0"; list items with a "name" can be addressed by it."""
    *head, last = key.split(".")
    cur = spec
    for part in head:
        if isinstance(cur, list):
            cur = cur[int(part)] if part.isdigit() else next(i for i in cur if i.get("name") == part)
        else:
            cur = cur.setdefault(part, {})
    if isinstance(cur, list):
        cur[int(last)] = value
    else:
        cur[last] = value


# ------------------------------------------------------------------ plan

def _value(v: str):
    try:
        return json.loads(v)
    except ValueError:
        return v


def plan(varies: List[str], sample: int = 0, seed: int = 0) -> List[Dict]:
    """--vary strings ("key=a,b,c" or "key=lo..hi") -> override dicts; row 0 = no overrides."""
    lists, ranges = [], []
    for v in varies:
        key, _, vals = v.partition("=")
        if ".." in vals and "," not in vals:
            lo, hi = vals.split("..")
            ranges.append((key, float(lo), float(hi), "." not in lo + hi))
        else:
            lists.append((key, [_value(x) for x in vals.split(",")]))
    keys = [k for k, _ in lists]
    combos = [dict(zip(keys, c)) for c in itertools.product(*[vals for _, vals in lists])]
    rows: List[Dict] = [{}]
    if ranges:
        for r in range(sample or 6):
            o = dict(combos[r % len(combos)])
            for key, lo, hi, ints in ranges:
                x = lo + (hi - lo) * keyed(seed, r, key)
                o[key] = int(round(x)) if ints else round(x, 2)
            rows.append(o)
    else:
        rows += combos
    if len(rows) > MAX_ROWS + 1:
        raise SystemExit("%d variants is too many to judge by eye; narrow the lists or use a range with --sample"
                         % (len(rows) - 1))
    return rows


def label(o: Dict) -> str:
    return "base" if not o else "  ".join("%s=%s" % (k.replace("anim.", ""), json.dumps(v)) for k, v in o.items())


# ------------------------------------------------------------------ build

@dataclass
class Row:
    overrides: Dict
    warns: List[str]
    cells: List[List[np.ndarray]]      # one frame list per clip x direction, read back from the sheets


def _cells(bdir: Path) -> List[List[np.ndarray]]:
    meta = json.loads((bdir / (bdir.name + ".json")).read_text())
    fw, fh = meta["frame_w"], meta["frame_h"]
    out = []
    for c in meta["clips"].values():
        sheet = np.array(Image.open(bdir / c["sheet"]).convert("RGBA"))
        for r in range(len(meta["directions"])):
            out.append([sheet[r * fh:(r + 1) * fh, k * fw:(k + 1) * fw] for k in range(len(c["frames"]))])
    return out


def run(spec_path: str, varies: List[str], clips: Optional[List[str]] = None, dirs: Optional[List[str]] = None,
        sample: int = 0, seed: int = 0, scale: int = 3):
    """-> (still grid path, animated grid path, one text line per row)."""
    from .color import hex_to_rgb
    from .forge import Forge, load_spec
    from .lint import lint_build
    base = load_spec(spec_path)
    overrides = plan(varies, sample, seed)
    work = TMP / base["name"]
    work.mkdir(parents=True, exist_ok=True)
    (work / "variants.json").write_text(json.dumps({"spec": str(Path(spec_path).resolve()), "rows": overrides},
                                                   indent=1))
    cache, seen, rows, bg = None, {}, [], None
    for i, o in enumerate(overrides):
        spec = copy.deepcopy(base)
        for k, v in o.items():
            set_path(spec, k, v)
        if clips:
            spec["clips"] = clips
        f = Forge(spec)
        bg = bg or hex_to_rgb(f.style.spec.get("bg", "#2a2f3a"))
        if all(k.split(".")[0] in SHARES_GEOMETRY for k in o):
            if cache is None:
                cache = f.model._cache
            f.model._cache = cache
        bdir = work / ("v%02d" % i) / base["name"]      # lint expects <dir>/<name>.json
        f.build(bdir, dirs, preview_scale=1)
        warns = [m.strip()[5:] for m in lint_build(bdir) if m.startswith("WARN")]
        h = hashlib.sha1(b"".join(p.read_bytes() for p in sorted(bdir.glob("*.png")))).hexdigest()
        if h in seen:
            warns.insert(0, "identical to v%02d - these overrides change nothing" % seen[h])
        seen.setdefault(h, i)
        rows.append(Row(o, warns, _cells(bdir)))
    lines = ["v%02d %s%s" % (i, label(r.overrides), "".join("\n     WARN " + w for w in r.warns))
             for i, r in enumerate(rows)]
    _crop(rows)
    name = base["name"]
    return (_still(rows, bg, scale, work / ("variants_%s.png" % name)),
            _animated(rows, bg, scale, work / ("variants_%s.gif" % name)), lines)


# ------------------------------------------------------------------ grids

def _crop(rows: List[Row]) -> None:
    """Crop every frame to the union of all visible pixels (+1 px): the grid shows sprites, not canvas."""
    acc = np.any([f[..., 3] > 0 for r in rows for frames in r.cells for f in frames], axis=0)
    ys, xs = np.nonzero(acc)
    if len(xs):
        y0, y1, x0, x1 = max(0, ys.min() - 1), ys.max() + 2, max(0, xs.min() - 1), xs.max() + 2
        for r in rows:
            r.cells = [[f[y0:y1, x0:x1] for f in frames] for frames in r.cells]


def _ink(bg) -> tuple:
    return (20, 20, 24) if sum(bg) / 3 > 120 else (230, 230, 230)


def _paste(img: Image.Image, frame: np.ndarray, x: int, y: int) -> None:
    im = Image.fromarray(frame)
    img.paste(im, (x, y), im)


def _still(rows: List[Row], bg, scale: int, path: Path) -> Path:
    """One row per variant: every frame of every clip x direction, labelled with overrides + first warning."""
    fh, fw = rows[0].cells[0][0].shape[:2]
    W = max(sum(len(fr) * fw + PAD for fr in r.cells) for r in rows)
    img = Image.new("RGB", (W, (fh + LABEL_H) * len(rows)), bg)
    dr = ImageDraw.Draw(img)
    for i, r in enumerate(rows):
        y = i * (fh + LABEL_H)
        warn = ("   ! " + r.warns[0][:65]) if r.warns else ""
        dr.text((2, y), "v%02d %s%s" % (i, label(r.overrides), warn), fill=_ink(bg))
        x = 0
        for frames in r.cells:
            for f in frames:
                _paste(img, f, x, y + LABEL_H)
                x += fw
            x += PAD
    img.resize((img.width * scale, img.height * scale), Image.NEAREST).save(path)
    return path


def _animated(rows: List[Row], bg, scale: int, path: Path) -> Path:
    """One row per variant, one cell per clip x direction, each cell looping its own frames."""
    fh, fw = rows[0].cells[0][0].shape[:2]
    ncell = max(len(r.cells) for r in rows)
    out = []
    for t in range(max(len(fr) for r in rows for fr in r.cells)):
        im = Image.new("RGB", (GUTTER + ncell * (fw + PAD), (fh + LABEL_H) * len(rows)), bg)
        dr = ImageDraw.Draw(im)
        for i, r in enumerate(rows):
            y = i * (fh + LABEL_H) + LABEL_H
            dr.text((2, y + fh // 2 - 6), "v%02d" % i, fill=_ink(bg))
            for j, frames in enumerate(r.cells):
                _paste(im, frames[t % len(frames)], GUTTER + j * (fw + PAD), y)
        out.append(im.resize((im.width * scale, im.height * scale), Image.NEAREST))
    out[0].save(path, save_all=True, append_images=out[1:], duration=75, loop=0, disposal=1)
    return path


def apply(spec_path: str, index: int) -> Dict:
    """Write variant `index`'s overrides (from the last run on this spec) into the spec file."""
    from .forge import load_json
    spec = load_json(spec_path)
    rec = json.loads((TMP / spec["name"] / "variants.json").read_text())
    if Path(rec["spec"]) != Path(spec_path).resolve():
        raise SystemExit("the last variants run was for %s" % rec["spec"])
    o = rec["rows"][index]
    for k, v in o.items():
        set_path(spec, k, v)
    Path(spec_path).write_text(json.dumps(spec, indent=1, ensure_ascii=False))
    return o

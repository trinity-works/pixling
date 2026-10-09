"""Cheap, short lints. One line per finding; no reports, no ceremony.

Targets are the usual hand-made pixel-art ranges.
A lint is advice for the artist, not a gate: look at the sprite first.
"""
from __future__ import annotations

import json
from collections import Counter
from pathlib import Path
from typing import Dict, List, Tuple

import numpy as np
from PIL import Image
from scipy.ndimage import label

from .forge import load_style
from .shade import shift

N4 = [(-1, 0), (1, 0), (0, -1), (0, 1)]


def _frames(build: Path) -> Tuple[Dict, Dict[str, List[List[np.ndarray]]]]:
    meta = json.loads((build / (build.name + ".json")).read_text())
    fw, fh = meta["frame_w"], meta["frame_h"]
    out = {}
    for name, c in meta["clips"].items():
        sheet = np.array(Image.open(build / c["sheet"]).convert("RGBA"))
        rows = []
        for r in range(sheet.shape[0] // fh):
            rows.append([sheet[r * fh:(r + 1) * fh, i * fw:(i + 1) * fw] for i in range(len(c["frames"]))])
        out[name] = rows
    return meta, out


def _key(img: np.ndarray) -> np.ndarray:
    return (img[..., 0].astype(np.int32) << 16) | (img[..., 1].astype(np.int32) << 8) | img[..., 2]


def orphan_ratio(img: np.ndarray) -> float:
    a = img[..., 3] > 0
    k = np.where(a, _key(img), -1)
    same = np.zeros(k.shape, np.int32)
    # 8-connected: pixel-art lines step diagonally, so a diagonal twin is not an orphan
    for dy, dx in N4 + [(-1, -1), (-1, 1), (1, -1), (1, 1)]:
        same += shift(k, dy, dx, -2) == k
    return float(((same == 0) & a).sum()) / max(1, a.sum())


def silhouette(img: np.ndarray) -> np.ndarray:
    return img[..., 3] > 0


def lint_build(build_dir, style_name: str = None) -> List[str]:
    build = Path(build_dir)
    meta, clips = _frames(build)
    style = load_style(style_name or meta["style"])
    pal = {tuple(c) for c in style.palette()}
    for k in ("flash", "shadow_color", "dust"):
        if k in style.spec:
            from .color import hex_to_rgb
            pal.add(hex_to_rgb(style.spec[k]))
    smear = None
    msgs: List[str] = []
    first = next(iter(clips.values()))
    ref = first[0][0]

    # palette lock + colour count + alpha
    cols = set()
    off = set()
    semi = 0
    for rows in clips.values():
        for row in rows:
            for f in row:
                a = f[..., 3]
                semi += int(((a > 0) & (a < 255)).sum())
                px = {tuple(v) for v in f[a > 0][:, :3].tolist()}
                cols |= px
                off |= {c for c in px if c not in pal}
    idle_cols = {tuple(v) for v in ref[ref[..., 3] > 0][:, :3].tolist()}
    msgs.append("colours: %d in idle frame (target 12-25), %d across all clips" % (len(idle_cols), len(cols)))
    if off:
        msgs.append("WARN off-palette colours: %d (e.g. %s) — smear/fx colours must come from the style" %
                    (len(off), "#%02x%02x%02x" % next(iter(off))))
    if semi:
        msgs.append("WARN %d semi-transparent pixels (sprites must be fully opaque)" % semi)

    # orphans
    orph = max(orphan_ratio(f) for rows in clips.values() for row in rows for f in row[:1])
    msgs.append(("WARN " if orph > 0.06 else "") + "orphan pixels: %.1f%% worst frame (target < 3-6%%)" % (orph * 100))

    # size / direction consistency
    hs = []
    for row in first:
        s = silhouette(row[0])
        ys = np.nonzero(s.any(1))[0]
        hs.append(int(ys.max() - ys.min() + 1) if len(ys) else 0)
    msgs.append("height px by direction: %s" % hs)
    if max(hs) - min(hs) > 3:
        msgs.append("WARN height varies %d px across directions (> 3)" % (max(hs) - min(hs)))

    # edges: share of edge pixels that keep their interior colour
    s = silhouette(ref)
    k = _key(ref)
    H, W = s.shape
    edge = np.zeros_like(s)
    for dy, dx in N4:
        edge |= s & ~shift(s, dy, dx, False)
    ys, xs = np.nonzero(edge)
    keep = 0
    for y, x in zip(ys, xs):
        for dy, dx in N4:
            yy, xx = y + dy, x + dx
            if 0 <= yy < H and 0 <= xx < W and s[yy, xx] and not edge[yy, xx]:
                keep += int(k[yy, xx] == k[y, x])
                break
    msgs.append("edges keeping fill: %d%% (reference 52-90%%)" % (100 * keep // max(1, len(ys))))

    # one body: a piece that detaches in SOME frames of a loop is a joint or thin
    # part dropping out (designed floaters — embers, halos — are detached in every frame and pass)
    from .color import hex_to_rgb
    fxc = [hex_to_rgb(style.spec.get(k, "#1f1a2a")) for k in ("shadow_color", "dust")]
    flick = []
    for name in ("idle", "walk", "run"):
        for d, row in enumerate(clips.get(name, [])):
            loose = []
            for f in row:
                body = f[..., 3] > 0
                for c in fxc:
                    body &= ~np.all(f[..., :3] == c, axis=-1)
                lab, _ = label(body, structure=np.ones((3, 3)))
                loose.append(int((np.bincount(lab.ravel())[1:] >= 3).sum()))
            if max(loose) != min(loose):
                flick.append("%s %s f%d" % (name, meta["directions"][d], int(np.argmax(loose))))
    if flick:
        msgs.append("WARN parts detach in some frames only (%d rows, e.g. %s) — a joint or thin part drops out; "
                    "check with pp inspect" % (len(flick), flick[0]))

    # values per ramp in the idle frame: more than 4 shades of one ramp reads as noise at 1x
    ramp_of = {}
    for rn, cols in style.ramps.items():
        for c in cols:
            ramp_of.setdefault(tuple(c), rn)
    per = Counter(ramp_of[c] for c in idle_cols if c in ramp_of)
    busy = {k: v for k, v in per.items() if v > 4}
    if busy:
        msgs.append("values per ramp > 4 in idle: %s (2-3 per part is plenty)" %
                    ", ".join("%s %d" % kv for kv in sorted(busy.items(), key=lambda kv: -kv[1])))

    # jitter on loops: pixels changed between consecutive frames vs silhouette area
    for name in ("idle", "walk", "run"):
        if name not in clips:
            continue
        row = clips[name][0]
        ch = []
        for a, b in zip(row, row[1:] + row[:1]):
            diff = (np.any(a != b, axis=-1)).sum()
            ch.append(diff / max(1, silhouette(a).sum()))
        msgs.append("%s: %d frames, mean change/frame %.0f%% of area" % (name, len(row), 100 * np.mean(ch)))
        if name == "idle" and np.mean(ch) > 0.35:
            msgs.append("WARN idle changes too much per frame — pixels are swimming (target < 35%)")
    return msgs


def silhouette_family(build_dirs: List[str], direction: str = "S") -> List[str]:
    """Pairwise silhouette overlap (IoU, feet-aligned). Family members should read apart."""
    sil = []
    for d in build_dirs:
        meta, clips = _frames(Path(d))
        c = clips.get("idle") or next(iter(clips.values()))
        r = meta["directions"].index(direction) if direction in meta["directions"] else 0
        s = silhouette(c[r][0])
        ys, xs = np.nonzero(s)
        crop = s[ys.min():ys.max() + 1, xs.min():xs.max() + 1]
        sil.append((Path(d).name, crop))
    msgs = []
    for i in range(len(sil)):
        for j in range(i + 1, len(sil)):
            (na, a), (nb, b) = sil[i], sil[j]
            H = max(a.shape[0], b.shape[0])
            W = max(a.shape[1], b.shape[1])
            A = np.zeros((H, W), bool)
            B = np.zeros((H, W), bool)
            A[H - a.shape[0]:, (W - a.shape[1]) // 2:(W - a.shape[1]) // 2 + a.shape[1]] = a
            B[H - b.shape[0]:, (W - b.shape[1]) // 2:(W - b.shape[1]) // 2 + b.shape[1]] = b
            iou = (A & B).sum() / max(1, (A | B).sum())
            flag = "WARN " if iou > 0.75 else ""
            msgs.append("%ssilhouette IoU %s vs %s: %.2f%s" % (flag, na, nb, iou,
                                                              " (too similar, > 0.75)" if flag else ""))
    return msgs


def size_family(build_dirs: List[str]) -> List[str]:
    """Declared size classes (spec "size") must rank the family the way the eye does: a "small" member measured
    taller than a "large" one is out of order. Builds without a size class are skipped."""
    from .size import ORDER, SIZES
    rows = []
    for d in build_dirs:
        d = Path(d)
        meta = json.loads((d / (d.name + ".json")).read_text())
        s, h = meta.get("size"), meta.get("height_px")
        if h is None or s is None:
            continue
        rank = ORDER.index(s) if s in ORDER else None
        if rank is None and s.endswith("px"):
            rank = sum(1 for v in SIZES.values() if v <= float(s[:-2])) - 0.5
        rows.append((meta["name"], s, h, rank))
    out = []
    for a in rows:
        for b in rows:
            if a[3] is not None and b[3] is not None and a[3] < b[3] and a[2] >= b[2]:
                out.append("size order: %s is %s but %d px, not shorter than %s (%s, %d px)" % (a[0], a[1], a[2], b[0], b[1], b[2]))
    return out

"""Chroma key for generated clips: colour-difference matte, shadow-invariant, defringed edges.

The generator is prompted for a flat key background (green, magenta or blue, chosen against the character's
colours). Per frame:
  1. key colour = median of the frame border (handles exposure drift between frames),
  2. spill = key channel(s) minus the others (Keylight-style; yellow/cyan survive a green key),
     alpha_raw = 1 - spill/spill_key, also computed on luminance-normalised colour so the character's
     drop shadow on the backdrop keys out too,
  3. alpha is hardened between noise-derived thresholds, specks are dropped by connected components,
  4. edge colour is replaced by the nearest solid interior colour (no green/magenta halo ever survives),
     and the remaining interior spill is limited.
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np
from scipy import ndimage

KEYS = {"green": (0, 177, 64), "magenta": (255, 0, 255), "blue": (0, 71, 187)}


@dataclass
class KeyCfg:
    color: tuple | None = None      # fixed key RGB; None = per-frame border median
    ring: float = 0.03              # border ring width (fraction of the short side)
    lo: float | None = None         # alpha_raw below this is background (None = auto from border noise)
    hi: float = 0.75                # alpha_raw above this is solid
    drop_shadow: bool = True        # key out darker backdrop (cast shadows) too
    choke: int = 1                  # erode the matte by N source pixels
    min_part: float = 0.002         # drop components smaller than this fraction of the largest
    despill: float = 1.0            # 0..1 interior spill limit strength
    edge_fill: bool = True          # recolour soft edge pixels from the nearest solid pixel


def _mode(k):
    """('p', ch, others) for a primary key, ('s', (a, b), low) for a secondary key (magenta, cyan, yellow)."""
    k = np.asarray(k, float)
    o = np.argsort(k)[::-1]
    top, mid, low = k[o]
    if top - mid >= mid - low:
        return ("p", int(o[0]), [int(o[1]), int(o[2])])
    return ("s", (int(o[0]), int(o[1])), int(o[2]))


def _spill(img, mode):
    if mode[0] == "p":
        ch, oth = mode[1], mode[2]
        return img[..., ch] - np.maximum(img[..., oth[0]], img[..., oth[1]])
    (a, b), low = mode[1], mode[2]
    return np.minimum(img[..., a], img[..., b]) - img[..., low]


def _despill(img, mode, strength):
    s = np.clip(_spill(img, mode), 0, None)[..., None] * strength
    out = img.copy()
    if mode[0] == "p":
        out[..., mode[1]] -= s[..., 0]
    else:
        a, b = mode[1]
        out[..., a] -= s[..., 0]
        out[..., b] -= s[..., 0]
    return out


def ring_mask(h, w, frac):
    m = max(2, int(min(h, w) * frac))
    r = np.zeros((h, w), bool)
    r[:m], r[-m:], r[:, :m], r[:, -m:] = True, True, True, True
    return r


def border_key(frame, frac=0.03):
    """Robust backdrop colour: median of the border ring, re-estimated without far outliers (character at edge)."""
    f = frame.reshape(-1, 3) if frame.ndim == 2 else frame[ring_mask(*frame.shape[:2], frac)]
    f = f.astype(float)
    med = np.median(f, 0)
    d = np.linalg.norm(f - med, axis=1)
    return np.median(f[d < max(20.0, np.percentile(d, 60) * 2)], 0)


def alpha_raw(img, key, drop_shadow=True):
    """img float 0..1 HxWx3, key float 0..1 (3,). Returns float alpha estimate (not hardened)."""
    mode = _mode(key)
    sk = max(1e-3, float(_spill(key[None, None], mode)[0, 0]))
    a = 1.0 - _spill(img, mode) / sk
    if drop_shadow:
        lum = img.mean(-1)
        lk = max(1e-3, float(key.mean()))
        rel = img / np.maximum(lum, 1e-3)[..., None] * lk          # same chroma, key brightness
        a_n = 1.0 - _spill(rel, mode) / sk
        dark = np.clip((lum / lk - 0.12) / 0.2, 0, 1)                 # near-black is foreground (outlines)
        a_n = dark * a_n + (1 - dark) * 1.0
        # only backdrop-hued pixels (same chromaticity as the key) count as shadow; dark crimson on magenta does not
        cp = img / np.maximum(img.sum(-1), 1e-3)[..., None]
        ck = key / max(key.sum(), 1e-3)
        w = np.exp(-(np.linalg.norm(cp - ck, axis=-1) / 0.08) ** 2)
        a = np.minimum(a, w * a_n + (1 - w) * a)
    return np.clip(a, 0, 1)


def key_frame(frame: np.ndarray, cfg: KeyCfg = KeyCfg()):
    """uint8 HxWx3 -> (RGBA uint8 crop around the character, (x0, y0) of the crop, key colour used)."""
    img = frame.astype(np.float32) / 255.0
    key = np.asarray(cfg.color, float) / 255.0 if cfg.color is not None else border_key(frame, cfg.ring) / 255.0
    a = alpha_raw(img, key, cfg.drop_shadow)
    ring = ring_mask(*a.shape, cfg.ring)
    lo = cfg.lo if cfg.lo is not None else float(np.clip(np.percentile(a[ring], 99.5) + 0.08, 0.12, 0.5))
    hi = max(cfg.hi, lo + 0.1)
    t = np.clip((a - lo) / (hi - lo), 0, 1)
    a = t * t * (3 - 2 * t)
    ys, xs = np.nonzero(a > 0.02)
    if len(ys) == 0:
        return np.zeros((1, 1, 4), np.uint8), (0, 0), key * 255
    pad = 4 + cfg.choke
    y0, y1 = max(0, ys.min() - pad), min(a.shape[0], ys.max() + 1 + pad)
    x0, x1 = max(0, xs.min() - pad), min(a.shape[1], xs.max() + 1 + pad)
    a, img = a[y0:y1, x0:x1], img[y0:y1, x0:x1]

    solid = a > 0.5
    lab, n = ndimage.label(solid)
    if n > 1:
        sizes = ndimage.sum(np.ones_like(a), lab, index=np.arange(1, n + 1))
        keep = np.zeros(n + 1, bool)
        keep[1:] = sizes >= cfg.min_part * sizes.max()
        grown = ndimage.binary_dilation(keep[lab], iterations=3)
        a = a * grown
    if cfg.choke > 0:
        a = np.minimum(a, ndimage.grey_erosion(a, size=(2 * cfg.choke + 1,) * 2))

    rgb = _despill(img, _mode(key), cfg.despill) if cfg.despill > 0 else img
    if cfg.edge_fill and (a > 0.95).any():
        core = a > 0.95
        idx = ndimage.distance_transform_edt(~core, return_distances=False, return_indices=True)
        edge = (a > 0) & ~core
        rgb[edge] = rgb[idx[0][edge], idx[1][edge]]
    out = np.dstack([np.clip(rgb, 0, 1), a])
    return (out * 255 + 0.5).astype(np.uint8), (int(x0), int(y0)), key * 255


def bbox(alpha, thr=128):
    ys, xs = np.nonzero(alpha >= thr)
    if len(ys) == 0:
        return None
    return int(xs.min()), int(ys.min()), int(xs.max()) + 1, int(ys.max()) + 1

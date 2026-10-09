"""Make filmed frames look drawn: one locked palette per character, a tinted outline, crisp alpha.

The palette is fitted once (on the character's reference frames) and every frame of every clip snaps to it,
which also kills the colour swim that video generators add between frames.
"""
from __future__ import annotations

import numpy as np
from PIL import Image, ImageFilter
from scipy import ndimage


def _lab(rgb):
    """sRGB 0..255 -> approx. CIELAB (D65). Enough for nearest-colour snapping."""
    c = rgb.astype(np.float64) / 255.0
    c = np.where(c > 0.04045, ((c + 0.055) / 1.055) ** 2.4, c / 12.92)
    m = np.array([[0.4124, 0.3576, 0.1805], [0.2126, 0.7152, 0.0722], [0.0193, 0.1192, 0.9505]])
    xyz = np.einsum('...j,ij->...i', c, m) / np.array([0.9505, 1.0, 1.089])
    f = np.where(xyz > 0.008856, np.cbrt(xyz), 7.787 * xyz + 16 / 116)
    return np.stack([116 * f[..., 1] - 16, 500 * (f[..., 0] - f[..., 1]), 200 * (f[..., 1] - f[..., 2])], -1)


def fit_palette(frames, k=32, iters=12, seed=0):
    """k-means in Lab over the opaque pixels of the given RGBA frames. Returns (k,3) uint8 sorted by lightness."""
    px = np.concatenate([f[f[..., 3] >= 128][:, :3] for f in frames])
    rng = np.random.default_rng(seed)
    if len(px) > 60000:
        px = px[rng.choice(len(px), 60000, replace=False)]
    lab = _lab(px)
    # k-means++ init
    cent = [lab[rng.integers(len(lab))]]
    for _ in range(1, k):
        d = np.min(((lab[:, None] - np.array(cent)[None]) ** 2).sum(-1), 1)
        cent.append(lab[rng.choice(len(lab), p=d / d.sum())])
    cent = np.array(cent)
    for _ in range(iters):
        lbl = np.argmin(((lab[:, None] - cent[None]) ** 2).sum(-1), 1)
        for j in range(k):
            sel = lbl == j
            if sel.any():
                cent[j] = lab[sel].mean(0)
    lbl = np.argmin(((lab[:, None] - cent[None]) ** 2).sum(-1), 1)
    pal = np.array([px[lbl == j].mean(0) if (lbl == j).any() else px[0] for j in range(k)])
    pal = np.clip(pal + 0.5, 0, 255).astype(np.uint8)
    return pal[np.argsort(_lab(pal)[:, 0])]


def snap(frame, pal):
    out = frame.copy()
    m = frame[..., 3] > 0
    lab = _lab(frame[m][:, :3])
    pl = _lab(pal)
    idx = np.empty(len(lab), int)
    for i in range(0, len(lab), 20000):
        idx[i:i + 20000] = np.argmin(((lab[i:i + 20000, None] - pl[None]) ** 2).sum(-1), 1)
    out[m, :3] = pal[idx]
    return out


def outline(frame, color, width=1, thr=128):
    """Paint `width` px of `color` just outside the silhouette (under the sprite, so AA edges blend onto it)."""
    solid = frame[..., 3] >= thr
    ring = ndimage.binary_dilation(solid, structure=ndimage.generate_binary_structure(2, 1), iterations=width) & ~solid
    out = frame.copy().astype(np.float32)
    a = out[..., 3:4] / 255.0
    col = np.array(color, np.float32)
    # under-composite: existing soft edge over the outline colour
    under = ring | ((frame[..., 3] > 0) & ~solid)
    out[under, :3] = out[under, :3] * a[under] + col * (1 - a[under])
    out[under, 3] = 255
    return out.astype(np.uint8)


def reoutline(frame, color, width=2, strip=1, thr=128):
    """One uniform outline whatever the source drew: eat `strip` px of the source edge, then paint a solid band
    `width` px thick straddling the old edge (strip inside, width-strip outside). Same px on every row and state."""
    solid = frame[..., 3] >= thr
    st = ndimage.generate_binary_structure(2, 1)
    inner = ndimage.binary_erosion(solid, st, iterations=strip) if strip else solid
    outer = ndimage.binary_dilation(solid, st, iterations=max(0, width - strip)) if width > strip else solid
    band = outer & ~inner
    out = frame.copy()
    out[~outer] = 0
    out[band, :3] = color
    out[band, 3] = 255
    out[inner, 3] = 255
    return out


def harden(frame, thr=128):
    out = frame.copy()
    out[..., 3] = np.where(frame[..., 3] >= thr, 255, 0)
    return out


def sharpen(frame, amount=0.6, radius=1.0):
    if amount <= 0:
        return frame
    im = Image.fromarray(frame)
    rgb = im.convert("RGB").filter(ImageFilter.UnsharpMask(radius=radius, percent=int(amount * 100), threshold=2))
    out = np.asarray(rgb).copy()
    return np.dstack([out, frame[..., 3]])


def dark_tint(pal):
    """Outline colour: the darkest palette colour, pushed a bit darker, keeping its hue (never pure black)."""
    c = pal[0].astype(float)
    return tuple(int(v) for v in np.clip(c * 0.7, 8, 255))


def grade(frame, g: dict):
    """Opt-in colour grade (before the palette snap): {"brightness": 1.1, "saturation": 1.3, "contrast": 1.1}.
    Painterly sources read dark and muddy at sprite size; chibi/cel characters don't use it."""
    if not g:
        return frame
    rgb = frame[..., :3].astype(np.float32) / 255.0
    rgb = rgb * g.get("brightness", 1.0)
    lum = rgb @ np.array([0.299, 0.587, 0.114], np.float32)
    rgb = lum[..., None] + (rgb - lum[..., None]) * g.get("saturation", 1.0)
    rgb = (rgb - 0.5) * g.get("contrast", 1.0) + 0.5
    out = (np.clip(rgb, 0, 1) * 255 + 0.5).astype(np.uint8)
    return np.dstack([out, frame[..., 3]])


def finish(frame, cfg: dict, pal=None):
    f = grade(frame, cfg.get("grade"))
    if cfg.get("sharpen", 0):
        f = sharpen(f, cfg["sharpen"])
    if pal is not None:
        f = snap(f, pal)
    if cfg.get("alpha", "soft") == "hard":
        f = harden(f)
    ro = cfg.get("reoutline")
    if ro:
        col = tuple(ro["color"]) if ro.get("color") else (dark_tint(pal) if pal is not None else (22, 18, 30))
        f = reoutline(f, col, ro.get("width", 2), ro.get("strip", 1))
    ol = cfg.get("outline")
    if ol:
        col = tuple(ol.get("color")) if ol.get("color") else (dark_tint(pal) if pal is not None else (20, 16, 28))
        f = outline(f, col, ol.get("width", 1))
    return f

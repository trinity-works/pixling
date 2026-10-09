"""Color science for Pixel Perfect.

Everything perceptual happens in OKLab / OKLCH (Björn Ottosson, 2020). OKLCH hue
angles for orientation: red ~30, orange ~55, yellow ~100, green ~145,
cyan ~195, blue ~260, violet ~300, magenta ~340.
"""
from __future__ import annotations

import math
from typing import Iterable, List, Sequence, Tuple

import numpy as np

RGB = Tuple[int, int, int]


# ---------------------------------------------------------------- conversions

def _srgb_to_linear(c: np.ndarray) -> np.ndarray:
    return np.where(c <= 0.04045, c / 12.92, ((c + 0.055) / 1.055) ** 2.4)


def _linear_to_srgb(c: np.ndarray) -> np.ndarray:
    c = np.clip(c, 0.0, 1.0)
    return np.where(c <= 0.0031308, c * 12.92, 1.055 * np.power(c, 1 / 2.4) - 0.055)


_M1 = np.array([[0.4122214708, 0.5363325363, 0.0514459929],
                [0.2119034982, 0.6806995451, 0.1073969566],
                [0.0883024619, 0.2817188376, 0.6299787005]])
_M2 = np.array([[0.2104542553, 0.7936177850, -0.0040720468],
                [1.9779984951, -2.4285922050, 0.4505937099],
                [0.0259040371, 0.7827717662, -0.8086757660]])
_M2_INV = np.linalg.inv(_M2)
_M1_INV = np.linalg.inv(_M1)


def rgb_to_oklab(rgb: np.ndarray) -> np.ndarray:
    """rgb: (..., 3) uint8 or 0-255 floats -> (..., 3) OKLab."""
    lin = _srgb_to_linear(np.asarray(rgb, dtype=np.float64) / 255.0)
    lms = np.cbrt(lin @ _M1.T)
    return lms @ _M2.T


def oklab_to_rgb_float(lab: np.ndarray) -> np.ndarray:
    lms = np.asarray(lab, dtype=np.float64) @ _M2_INV.T
    lin = (lms ** 3) @ _M1_INV.T
    return lin  # linear, possibly out of gamut


def oklab_to_rgb(lab: np.ndarray) -> np.ndarray:
    return np.round(_linear_to_srgb(oklab_to_rgb_float(lab)) * 255).astype(np.uint8)


def oklch_to_oklab(L: float, C: float, h: float) -> np.ndarray:
    r = math.radians(h)
    return np.array([L, C * math.cos(r), C * math.sin(r)])


def oklab_to_oklch(lab: Sequence[float]) -> Tuple[float, float, float]:
    L, a, b = lab
    return float(L), float(math.hypot(a, b)), float(math.degrees(math.atan2(b, a)) % 360)


def in_gamut(L: float, C: float, h: float, eps: float = 1e-4) -> bool:
    lin = oklab_to_rgb_float(oklch_to_oklab(L, C, h))
    return bool(np.all(lin >= -eps) and np.all(lin <= 1 + eps))


def gamut_clip(L: float, C: float, h: float) -> Tuple[float, float, float]:
    """Reduce chroma (keep L and h) until the color is displayable."""
    if in_gamut(L, C, h):
        return L, C, h
    lo, hi = 0.0, C
    for _ in range(24):
        mid = (lo + hi) / 2
        if in_gamut(L, mid, h):
            lo = mid
        else:
            hi = mid
    return L, lo, h


def oklch_to_rgb(L: float, C: float, h: float) -> RGB:
    L, C, h = gamut_clip(L, C, h)
    return tuple(int(v) for v in oklab_to_rgb(oklch_to_oklab(L, C, h)))  # type: ignore


def rgb_to_oklch(rgb: RGB) -> Tuple[float, float, float]:
    return oklab_to_oklch(rgb_to_oklab(np.array(rgb)))


def hex_to_rgb(h: str) -> RGB:
    h = h.lstrip("#")
    return int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)


def rgb_to_hex(c: Sequence[int]) -> str:
    return "#%02x%02x%02x" % tuple(int(v) for v in c[:3])


def delta_e(a: RGB, b: RGB) -> float:
    """Perceptual distance (OKLab euclidean, ~0.02 = just noticeable)."""
    return float(np.linalg.norm(rgb_to_oklab(np.array(a)) - rgb_to_oklab(np.array(b))))


# ---------------------------------------------------------------- hue helpers

def hue_delta(a: float, b: float) -> float:
    """Signed shortest rotation from hue a to hue b, degrees in (-180, 180]."""
    d = (b - a) % 360
    return d - 360 if d > 180 else d


def hue_toward(h: float, target: float, amount_deg: float) -> float:
    """Rotate hue h toward target by at most amount_deg."""
    d = hue_delta(h, target)
    step = max(-abs(amount_deg), min(abs(amount_deg), d))
    return (h + step) % 360


# ---------------------------------------------------------------- ramps

def make_ramp(
    hue: float,
    chroma: float,
    n: int = 6,
    l_dark: float = 0.22,
    l_light: float = 0.93,
    shadow_hue: float = 285.0,
    light_hue: float = 95.0,
    hue_shift: float = 32.0,
    chroma_dark: float = 0.75,
    chroma_light: float = 0.65,
    l_gamma: float = 1.0,
) -> List[RGB]:
    """A hue-shifted color ramp, darkest first.

    Classic pixel-art ramp physics: going darker the hue rotates toward the
    (cool) shadow hue, going lighter toward the (warm) light hue; chroma peaks
    in the mid tones and falls off at both ends so shadows don't go muddy and
    highlights don't go neon. `hue_shift` is the total rotation at each end.
    """
    out: List[RGB] = []
    for i in range(n):
        t = i / (n - 1) if n > 1 else 0.5          # 0 = darkest, 1 = lightest
        L = l_dark + (l_light - l_dark) * (t ** l_gamma)
        # distance from the mid tone in [-1, 1]
        s = (t - 0.5) * 2
        if s < 0:
            h = hue_toward(hue, shadow_hue, hue_shift * -s)
            c = chroma * (1 - (1 - chroma_dark) * s * s)
        else:
            h = hue_toward(hue, light_hue, hue_shift * s)
            c = chroma * (1 - (1 - chroma_light) * s * s)
        out.append(oklch_to_rgb(L, c, h))
    return out


def ramp_report(ramp: Iterable[RGB]) -> List[Tuple[float, float, float]]:
    return [rgb_to_oklch(c) for c in ramp]

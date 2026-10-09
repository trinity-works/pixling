"""Synthetic 'generator output' for testing the cut path without spending credits.

Films an RGBA sprite sequence the way a video model delivers it: upscaled soft edges, a slightly uneven key
backdrop with vignette, a soft drop shadow, key-colour spill on the rim, sensor noise, slow camera drift, and
h264 compression. Returns ground-truth alphas so tests can score the key.
"""
from __future__ import annotations

import numpy as np
from PIL import Image, ImageFilter

from .io import write_video


def film(sprites, path, key=(20, 190, 70), size=(960, 540), scale=7, fps=24, drift=(0.6, 0.15), seed=0,
         shadow=True, spill=0.25, noise=3.0, crf=23, repeat=2):
    rng = np.random.default_rng(seed)
    W, H = size
    y, x = np.mgrid[0:H, 0:W]
    vign = 1.0 - 0.18 * (((x - W / 2) / W) ** 2 + ((y - H / 2) / H) ** 2) * 4
    base = np.asarray(key, float)[None, None] * vign[..., None]
    frames, alphas = [], []
    seq = [s for s in sprites for _ in range(repeat)]
    for i, spr in enumerate(seq):
        im = Image.fromarray(spr).resize((spr.shape[1] * scale, spr.shape[0] * scale), Image.BICUBIC)
        im = im.filter(ImageFilter.GaussianBlur(1.2))
        a = np.asarray(im, float)[..., 3:4] / 255.0
        rgb = np.asarray(im, float)[..., :3]
        ox = int(W / 2 - im.width / 2 + drift[0] * i)
        oy = int(H - im.height - 12 - drift[1] * i)
        bg = base.copy()
        if shadow:
            sy, sx = oy + int(im.height * 0.82), ox + im.width // 2
            d = ((x - sx) / (im.width * 0.35)) ** 2 + ((y - sy) / (im.height * 0.06)) ** 2
            bg *= (1 - 0.35 * np.exp(-d * 2))[..., None]
        # rim spill: key colour bleeding into the soft edge of the subject
        edge = np.clip(a * (1 - a) * 4, 0, 1)
        rgb = rgb * (1 - spill * edge) + np.asarray(key, float) * spill * edge
        full_a = np.zeros((H, W, 1))
        full_rgb = np.zeros((H, W, 3))
        h, w = a.shape[:2]
        full_a[oy:oy + h, ox:ox + w] = a
        full_rgb[oy:oy + h, ox:ox + w] = rgb
        f = full_rgb * full_a + bg * (1 - full_a) + rng.normal(0, noise, (H, W, 3))
        frames.append(np.clip(f, 0, 255).astype(np.uint8))
        alphas.append(full_a[..., 0])
    write_video(frames, path, fps, crf)
    return alphas


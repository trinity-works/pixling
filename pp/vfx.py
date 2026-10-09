"""Pixel VFX: energy fields posterized to a locked ramp.

Every effect draws shapes into an *energy* buffer (0..1). Energy is posterized
to the style's VFX ramp at the end (brightest colour = highest energy), so
effects are procedural but look hand-pixelled (the "quantize last" rule).

Timing rules:
- build fast (1-5 frames), decay slow (>= 2x build), fragment 1 -> many pieces
- pixel mass x0.3-0.6 per frame after the peak; end on a 1 px particle tail
- colour: lightest at the peak, darker as it dies; fire ends redder
- particles shrink 3 -> 2 -> 1 px instead of fading; dark sinks, bright floats
- one-frame white flash/smear at impact
"""
from __future__ import annotations

import math
from typing import Callable, Dict, List, Sequence, Tuple

import numpy as np

from .color import hex_to_rgb


class Canvas:
    def __init__(self, w: int, h: int):
        self.w, self.h = w, h
        self.e = np.zeros((h, w), np.float32)
        ys, xs = np.mgrid[0:h, 0:w]
        self.X = xs + 0.5
        self.Y = ys + 0.5

    def put(self, mask: np.ndarray, energy) -> None:
        val = energy if np.isscalar(energy) else energy[mask]
        self.e[mask] = np.maximum(self.e[mask], val)

    def cut(self, mask: np.ndarray) -> None:
        self.e[mask] = 0

    # shapes -------------------------------------------------------------
    def disc(self, cx, cy, r, e=1.0, falloff=0.0, squash=1.0):
        d = np.hypot(self.X - cx, (self.Y - cy) / squash)
        m = d <= r
        if falloff:
            self.put(m, np.clip(e * (1 - falloff * d / max(r, 1e-3)), 0, 1))
        else:
            self.put(m, e)

    def ring(self, cx, cy, r, w, e=1.0, squash=1.0):
        d = np.hypot(self.X - cx, (self.Y - cy) / squash)
        self.put((d <= r) & (d > r - w), e)

    def crescent(self, cx, cy, r, w, a0, a1, e=1.0, squash=1.0, taper=True):
        """Arc band between angles a0->a1 (degrees, 0 = +x, counter-clockwise, screen y down).
        Thickest in the middle when taper."""
        dx, dy = self.X - cx, (self.Y - cy) / squash
        d = np.hypot(dx, dy)
        ang = (np.degrees(np.arctan2(-dy, dx)) - a0) % 360
        span = (a1 - a0) % 360
        u = ang / max(span, 1e-3)
        inside = ang <= span
        ww = w * (np.sin(np.pi * np.clip(u, 0, 1)) ** 0.7 if taper else 1)
        m = inside & (d <= r) & (d >= r - ww)
        # leading edge (u -> 1) brightest
        self.put(m, np.clip(e * (0.75 + 0.25 * u), 0, 1))

    def spike(self, bx, by, h, w, angle=90.0, e=1.0, two_tone=True):
        """Triangle from a base centre, pointing at angle (deg, 90 = up)."""
        a = math.radians(angle)
        ux, uy = math.cos(a), -math.sin(a)
        px, py = -uy, ux
        rx, ry = self.X - bx, self.Y - by
        along = rx * ux + ry * uy
        across = rx * px + ry * py
        half = (w / 2) * (1 - along / max(h, 1e-3))
        m = (along >= 0) & (along <= h) & (np.abs(across) <= half)
        if two_tone:
            lit = m & (across < 0)
            self.put(m & ~lit, e * 0.72)
            self.put(lit, e)
        else:
            self.put(m, e)

    def streak(self, x0, y0, x1, y1, w=1.0, e=1.0):
        vx, vy = x1 - x0, y1 - y0
        L2 = vx * vx + vy * vy + 1e-9
        t = np.clip(((self.X - x0) * vx + (self.Y - y0) * vy) / L2, 0, 1)
        d = np.hypot(self.X - (x0 + t * vx), self.Y - (y0 + t * vy))
        self.put(d <= w / 2 + 0.01, np.clip(e * (0.6 + 0.4 * t), 0, 1))

    def dot(self, x, y, size=1, e=1.0):
        """Square particle of 1-3 px (pixel-art particles shrink instead of fading)."""
        s = int(max(1, round(size)))
        x0, y0 = int(math.floor(x - s / 2 + 0.5)), int(math.floor(y - s / 2 + 0.5))
        if s == 3:  # plus shape reads rounder than a 3x3 block
            for dx, dy in ((1, 0), (0, 1), (1, 1), (2, 1), (1, 2)):
                self._px(x0 + dx, y0 + dy, e)
            return
        for dy in range(s):
            for dx in range(s):
                self._px(x0 + dx, y0 + dy, e)

    def _px(self, x, y, e):
        if 0 <= x < self.w and 0 <= y < self.h:
            self.e[y, x] = max(self.e[y, x], e)

    def to_rgba(self, ramp: Sequence[tuple], floor: float = 0.06) -> np.ndarray:
        """Posterize energy to the ramp (darkest first). Energy < floor = empty."""
        out = np.zeros((self.h, self.w, 4), np.uint8)
        m = self.e > floor
        n = len(ramp)
        idx = np.clip((self.e * n).astype(int), 0, n - 1)
        for i, c in enumerate(ramp):
            out[m & (idx == i)] = (*c, 255)
        return out


class Rng:
    def __init__(self, seed: int):
        self.r = np.random.default_rng(seed)

    def u(self, a=0.0, b=1.0):
        return float(self.r.uniform(a, b))


# ------------------------------------------------------------------ effects
# Each effect: fn(params) -> list of Canvas frames. Frame time is the global 75 ms.

def fx_slash(p: Dict) -> List[Canvas]:
    """Impact smear: one solid crescent frame, then fragments that keep travelling
    along the swing and shrink (R21/R22)."""
    W, H = p.get("size", (64, 48))
    cx, cy, r = W / 2, H * 0.55, p.get("radius", 20)
    w = p.get("width", 9)
    a0, a1 = p.get("arc", (200, 20))[0], p.get("arc", (200, 20))[1]
    rng = Rng(p.get("seed", 1))
    frames = []
    # f0: thin lead-in streak (anticipation of the smear)
    c = Canvas(W, H)
    c.crescent(cx, cy, r, 2, a0 + (a1 - a0) % 360 * 0.55, a1, e=0.9, squash=p.get("squash", 0.7))
    frames.append(c)
    # f1: the full crescent (the biggest frame by far)
    c = Canvas(W, H)
    c.crescent(cx, cy, r, w, a0, a1, e=1.0, squash=p.get("squash", 0.7))
    frames.append(c)
    # f2..: fragments along the arc drift forward and shrink
    span = (a1 - a0) % 360
    pieces = [(a0 + span * (0.25 + 0.7 * k / 5) + rng.u(-6, 6), rng.u(0.8, 1.2)) for k in range(6)]
    for f in range(p.get("tail", 5)):
        c = Canvas(W, H)
        life = 1 - f / p.get("tail", 5)
        for k, (a, sz) in enumerate(pieces):
            if k < f - 1:                       # smallest / oldest pieces die first
                continue
            aa = math.radians(a + span * 0.08 * (f + 1))
            rr = r - w * 0.3 + f * 1.2
            x = cx + rr * math.cos(aa)
            y = cy - rr * math.sin(aa) * p.get("squash", 0.7)
            L = (w * 0.9 * life + 1) * sz
            ta = aa + math.pi / 2
            c.streak(x, y, x + L * math.cos(ta), y - L * math.sin(ta) * p.get("squash", 0.7),
                     w=max(1, round(2.5 * life)), e=0.35 + 0.6 * life)
        frames.append(c)
    return frames


def fx_hit_spark(p: Dict) -> List[Canvas]:
    """1-frame flash disc, then rays that shrink + 1 px sparks flying out.
    params: scale (overall size), ray_w (ray width on the flash frames), rays, sparks."""
    k = p.get("scale", 1.0)
    W, H = p.get("size", (int(32 * k), int(32 * k)))
    cx, cy = W / 2, H / 2
    rw = p.get("ray_w", 2)
    rng = Rng(p.get("seed", 2))
    rays = [(rng.u(0, 360), rng.u(0.7, 1.2)) for _ in range(p.get("rays", 6))]
    sparks = [(rng.u(0, 360), rng.u(0.8, 1.6)) for _ in range(p.get("sparks", 7))]
    frames = []
    for f in range(7):
        c = Canvas(W, H)
        if f == 0:
            c.disc(cx, cy, 5 * k, 1.0)
        elif f == 1:
            c.ring(cx, cy, 7 * k, max(2, 2 * k), 0.95)
            for a_, s_ in rays:
                aa = math.radians(a_)
                c.streak(cx + 4 * k * math.cos(aa), cy + 4 * k * math.sin(aa),
                         cx + 11 * k * s_ * math.cos(aa), cy + 11 * k * s_ * math.sin(aa), rw, 1.0)
        else:
            life = 1 - (f - 2) / 5
            for a_, s_ in rays[: max(0, len(rays) - (f - 2) * 2)]:
                aa = math.radians(a_)
                r0, r1 = (6 + f * 1.6) * k, (6 + f * 1.6 + 5 * s_ * life) * k
                c.streak(cx + r0 * math.cos(aa), cy + r0 * math.sin(aa),
                         cx + r1 * math.cos(aa), cy + r1 * math.sin(aa), max(1, rw - 1) if f < 4 else 1,
                         0.4 + 0.5 * life)
            for a_, s_ in sparks:
                aa = math.radians(a_)
                rr = (4 + f * 2.2) * s_ * k
                c.dot(cx + rr * math.cos(aa), cy + rr * math.sin(aa) + 0.25 * f * f * 0.3,
                      1 if f > 3 else 2, 0.3 + 0.6 * life)
        frames.append(c)
    return frames


def fx_burst(p: Dict) -> List[Canvas]:
    """Explosion / magic burst: grow 3, flash, break into puffs that thin out (R22-R23)."""
    W, H = p.get("size", (48, 48))
    cx, cy = W / 2, H * 0.55
    R = p.get("radius", 14)
    rng = Rng(p.get("seed", 3))
    npf = p.get("puffs", 9)
    puffs = [(k * 360 / npf + rng.u(-12, 12), rng.u(0.5, 1.0), rng.u(0.38, 0.55)) for k in range(npf)]
    sparks = [(k * 36 + rng.u(-15, 15), rng.u(1.0, 1.8)) for k in range(10)]
    frames = []
    grow = [0.45, 1.0, 0.92]
    for f, g in enumerate(grow):
        c = Canvas(W, H)
        c.disc(cx, cy, R * g, 1.0 if f == 1 else 0.85, falloff=0.0 if f == 1 else 0.3)
        frames.append(c)
    n_decay = p.get("decay", 8)
    for f in range(n_decay):
        c = Canvas(W, H)
        life = 1 - f / n_decay
        for k, (a, dist, size) in enumerate(puffs):
            if k >= len(puffs) * (life + 0.25):
                continue
            aa = math.radians(a)
            rr = R * (0.3 + dist * 0.8) * (1 + f * 0.12)
            x, y = cx + rr * math.cos(aa), cy + rr * math.sin(aa) * 0.8 - f * 0.9   # smoke rises
            c.disc(x, y, max(0.6, R * size * life ** 0.8), 0.25 + 0.7 * life, falloff=0.35)
        # hollow the core so it breaks up instead of shrinking as a blob
        if f < 3:
            c.cut(np.hypot(c.X - cx, c.Y - cy) < R * 0.35 * (f + 1) / 3)
        for a, s in sparks:
            aa = math.radians(a)
            rr = R * (1.0 + f * 0.25) * s
            if life > 0.2:
                c.dot(cx + rr * math.cos(aa), cy + rr * math.sin(aa) + f * f * 0.12, 2 if f < 3 else 1,
                      0.5 + 0.4 * life)
        frames.append(c)
    return frames


def fx_eruption(p: Dict) -> List[Canvas]:
    """Ice/crystal eruption (tweet 2): staggered spikes grow in 2-3 frames,
    anticipation streak, hold 2, shatter into gravity shards, rune fades."""
    W, H = p.get("size", (64, 56))
    base_y = H - 10
    rng = Rng(p.get("seed", 4))
    n = p.get("spikes", 5)
    xs = np.linspace(W * 0.22, W * 0.78, n)
    sh = p.get("spike_h", 13.0)
    sw = p.get("spike_w", 5.0)
    spikes = [(float(x + rng.u(-2, 2)), sh * rng.u(0.77, 1.23) * (1.5 if k == n // 2 else 1.0),
               sw * rng.u(0.8, 1.2), 90 + (k - n // 2) * rng.u(8, 14), k) for k, x in enumerate(xs)]
    shards = []
    for x, h, w, ang, k in spikes:
        for j in range(3):
            shards.append((x + rng.u(-3, 3), base_y - h * rng.u(0.3, 0.9), rng.u(-1.2, 1.2), rng.u(-2.8, -1.2),
                           rng.u(0, 1)))
    total = n + 14
    frames = []
    for f in range(total):
        c = Canvas(W, H)
        # floor rune: lights with the spikes, fades after
        rune = 1.0 if f < n + 5 else max(0.0, 1 - (f - n - 5) / 5)
        if rune > 0:
            c.ring(W / 2, base_y, p.get("rune_r", W * 0.4), 1.5, 0.55 * rune + 0.2, squash=0.35)
        for x, h, w, ang, k in spikes:
            age = f - k                           # 1-frame stagger
            if age < 0:
                continue
            if age == 0:                          # anticipation streak
                c.streak(x, base_y, x, base_y - 3, 1, 0.5)
                continue
            if age <= 3:                          # grow in 2-3 frames
                c.spike(x, base_y, h * min(1.0, age / 3 + 0.2), w, ang, 0.95 if age == 3 else 0.85)
            elif age <= n + 4 - k:                # hold
                c.spike(x, base_y, h, w, ang, 0.8)
        if f == n + 1:                             # impact flash on the hero spike
            x, h, w, ang, k = spikes[n // 2]
            c.spike(x, base_y, h + 2, w + 1, ang, 1.0, two_tone=False)
        if f > n + 4:                              # shatter: shards under gravity, shrink 3->2->1
            t = f - (n + 4)
            for sx, sy, vx, vy, bright in shards:
                x = sx + vx * t
                y = sy + vy * t + 0.35 * t * t * (1.4 if bright < 0.5 else 0.6)
                size = 3 if t < 3 else 2 if t < 6 else 1
                if t < 10 and y < H:
                    c.dot(x, y, size, 0.5 + 0.45 * bright * (1 - t / 10))
        frames.append(c)
    return frames


def fx_aura(p: Dict) -> List[Canvas]:
    """Buff aura (R24): grow 5, sustain with a 1-frame flash, disperse into rising motes.
    params: radius (ground ring), tongues (flame count), tongue_w, tongue_h, motes, sustain."""
    W, H = p.get("size", (48, 56))
    cx, base = W / 2, H - 8
    R = p.get("radius", 12)
    nt = p.get("tongues", 7)
    tw = p.get("tongue_w", 3)
    th = p.get("tongue_h", 8)
    rng = Rng(p.get("seed", 5))
    nm = p.get("motes", 12)
    # motes spread evenly round the ring (no clumps), each with its own speed and phase
    motes = [(math.cos(2 * math.pi * k / nm) * R * rng.u(0.5, 0.95), rng.u(0, 1), rng.u(0.6, 1.2)) for k in range(nm)]
    grow, sustain, disperse = 5, p.get("sustain", 10), 10
    frames = []
    for f in range(grow + sustain + disperse):
        c = Canvas(W, H)
        if f < grow + sustain:
            g = min(1.0, (f + 1) / grow)
            flick = 1.0 if f == grow + sustain // 2 else 0.75
            c.ring(cx, base, R * g, 2, flick, squash=0.35)
            for k in range(nt):
                x = cx + (k - (nt - 1) / 2) * (2 * R * 0.85 / max(1, nt - 1))
                edge = 1 - abs(k - (nt - 1) / 2) / max(1, (nt - 1) / 2) * 0.5
                h = (th + th * 0.75 * math.sin(f * 1.3 + k * 1.9)) * g * edge
                c.spike(x, base - 1, h, tw, 90 + 6 * math.sin(f + k), flick * 0.8)
        for k, (dx, ph, sp) in enumerate(motes):
            t = f / 4 + ph * 3
            y = base - ((t * 6 * sp) % (H - 12))
            life = 1 if f < grow + sustain else max(0.0, 1 - (f - grow - sustain) / disperse)
            if life <= 0 or (f >= grow + sustain and k % 3 == f % 3):
                continue
            size = 2 if (base - y) < (H - 12) * 0.45 else 1
            c.dot(cx + dx + math.sin(t) * 1.5, y, size, 0.5 + 0.5 * life * (1 - (base - y) / H))
        frames.append(c)
    return frames


def fx_dust(p: Dict) -> List[Canvas]:
    """Footstep / landing dust: puffs roll out sideways, rise a little and shrink.
    params: puffs (per side), radius, frames, two_tone (lit tops, shaded undersides)."""
    W, H = p.get("size", (24, 12))
    n = p.get("frames", 6)
    R = p.get("radius", 2.4)
    k = p.get("puffs", 1)
    two = p.get("two_tone", False)
    frames = []
    for f in range(n):
        c = Canvas(W, H)
        life = 1 - f / n
        for side in (-1, 1):
            for j in range(k):
                x = W / 2 + side * (2 + f * 1.4 + j * R * 1.3)
                y = H - 3 - f * 0.35 - j * 0.6
                r = max(0.6, R * life * (1 - 0.18 * j))
                if two:
                    c.disc(x, y, r, 0.55)
                    c.disc(x - 0.4, y - r * 0.35, r * 0.7, 0.95)
                else:
                    c.disc(x, y, r, 0.9)
        frames.append(c)
    return frames


def fx_projectile(p: Dict) -> List[Canvas]:
    """Loopable fireball / magic bolt travelling right: head + flickering trail."""
    W, H = p.get("size", (32, 16))
    cx, cy = W * 0.7, H / 2
    frames = []
    for f in range(4):
        c = Canvas(W, H)
        c.disc(cx, cy, 4, 0.8, squash=0.9)
        c.disc(cx + 0.6, cy - 0.4, 2.2, 1.0)
        for k in range(5):
            x = cx - 4 - k * 3.2
            y = cy + math.sin(f * 1.6 + k * 1.3) * 1.3
            c.disc(x, y, max(0.6, 3.2 - k * 0.6), 0.7 - k * 0.1)
        c.dot(cx - 8 - (f * 3) % 12, cy + (-2 if f % 2 else 2), 1, 0.6)
        frames.append(c)
    return frames


def fx_lightning(p: Dict) -> List[Canvas]:
    """Vertical strike: blink on/off frames, beam narrows 4 -> 2 -> 1 px, ground flash."""
    W, H = p.get("size", (32, 64))
    rng = Rng(p.get("seed", 6))
    pts = [(W / 2 + rng.u(-5, 5), y) for y in np.linspace(0, H - 8, 9)]
    widths = [4, 0, 4, 2, 0, 2, 1, 1]
    frames = []
    for f, w in enumerate(widths):
        c = Canvas(W, H)
        if w:
            for (x0, y0), (x1, y1) in zip(pts, pts[1:]):
                c.streak(x0, y0, x1, y1, w, 1.0 if w >= 2 else 0.7)
            c.disc(pts[-1][0], H - 7, 6 - f * 0.6, 0.85, squash=0.4)
        frames.append(c)
    return frames


def _twinkle(c: Canvas, x: float, y: float, size: int, e: float) -> None:
    """4-point star: size 0 = dot, 1 = plus, 2 = long plus, 3 = 7 px cross with a 2 px core."""
    xi, yi = int(math.floor(x)), int(math.floor(y))
    c._px(xi, yi, e)
    if size >= 3:
        for dx, dy in ((1, 0), (0, 1), (1, 1)):
            c._px(xi + dx, yi + dy, e)
        for d in (2, 3):
            for dx, dy in ((d, 0), (-d + 1, 0), (0, d), (0, -d + 1)):
                c._px(xi + dx, yi + dy, e * (0.8 if d == 2 else 0.55))
        return
    if size >= 1:
        for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1)):
            c._px(xi + dx, yi + dy, e * 0.8)
    if size >= 2:
        for dx, dy in ((2, 0), (-2, 0), (0, 2), (0, -2)):
            c._px(xi + dx, yi + dy, e * 0.55)


def fx_sparkle(p: Dict) -> List[Canvas]:
    """Heal / pickup sparkle: stars pop in staggered (dot -> plus -> long plus -> plus -> dot)
    while drifting up; soft motes rise; a ground ring glows then fades."""
    W, H = p.get("size", (32, 40))
    rng = Rng(p.get("seed", 7))
    n = p.get("stars", 7)
    peak = p.get("star_size", 2)
    life = [0, 1, peak, 1, 0] if peak <= 2 else [0, 1, 2, peak, 2, 1, 0]
    stars = [(rng.u(5, W - 5), rng.u(8, H - 10), int(k * 1.6)) for k in range(n)]
    total = p.get("frames", 16)
    frames = []
    for f in range(total):
        c = Canvas(W, H)
        if f < total - 4:
            g = min(1.0, (f + 1) / 3) * (1 - max(0, f - (total - 8)) / 5)
            c.ring(W / 2, H - 5, p.get("ring_r", 9) * min(1, (f + 2) / 4), p.get("ring_w", 1.2), 0.5 * g + 0.2,
                   squash=0.35)
        for x, y, t0 in stars:
            age = f - t0
            if 0 <= age < len(life):
                _twinkle(c, x, y - age * 0.6, life[age], 1.0 if life[age] >= 2 else 0.85)
        for k in range(5):
            y = H - 6 - ((f * 1.3 + k * 7) % (H - 10))
            if f < total - 2:
                c.dot(W / 2 + math.sin(f * 0.6 + k * 2.1) * 7, y, 1, 0.45 + 0.1 * (k % 2))
        frames.append(c)
    return frames


def fx_leaves(p: Dict) -> List[Canvas]:
    """Leaf/petal burst: leaves (2x1 / 1x2 flutter shapes) burst out, then fall swaying,
    flipping between 2-px and 1-px widths as they tumble."""
    W, H = p.get("size", (40, 40))
    rng = Rng(p.get("seed", 8))
    leaves = [(rng.u(0, 360), rng.u(2.2, 3.6), rng.u(0, 6.28), rng.u(0.5, 1.0)) for _ in range(p.get("count", 10))]
    frames = []
    total = p.get("frames", 14)
    cx, cy = W / 2, H * 0.45
    for f in range(total):
        c = Canvas(W, H)
        if f == 0:
            c.disc(cx, cy, 4, 1.0)
        for a, sp, ph, b in leaves:
            aa = math.radians(a)
            burst = min(f, 3)
            x = cx + math.cos(aa) * sp * burst + math.sin(f * 0.8 + ph) * 1.6 * max(0, f - 3) / 3
            y = cy + math.sin(aa) * sp * burst * 0.7 + max(0, f - 3) ** 1.25 * 0.8
            if y > H - 2 or f >= total - 1:
                continue
            e = 0.45 + 0.5 * b * (1 - f / total)
            flip = (f + int(ph * 3)) % 3
            xi, yi = int(x), int(y)
            if p.get("leaf_size", 2) <= 2:
                c._px(xi, yi, e)
                if flip == 0:
                    c._px(xi, yi + 1, e * 0.8)
                else:
                    c._px(xi + 1, yi, e * 0.8)
            else:
                # two-tone leaf: lit half + shaded half, tumbling between three silhouettes
                shapes = [((0, 0), (1, 0), (2, 1), (1, 1)), ((0, 0), (0, 1), (1, 1), (1, 2)),
                          ((0, 1), (1, 0), (2, 0), (1, 1))]
                for k, (dx, dy) in enumerate(shapes[flip]):
                    c._px(xi + dx, yi + dy, e if k < 2 else e * 0.7)
        frames.append(c)
    return frames


def fx_shockwave(p: Dict) -> List[Canvas]:
    """Ground slam: flat ring races out and thins; chips fly up and fall; dust rolls at the rim."""
    W, H = p.get("size", (64, 32))
    cx, cy = W / 2, H * 0.62
    R = p.get("radius", 26)
    rng = Rng(p.get("seed", 9))
    chips = [(rng.u(-1, 1), rng.u(1.6, 3.0), rng.u(0.4, 1.0)) for _ in range(p.get("chips", 8))]
    frames = []
    n = p.get("frames", 8)
    for f in range(n):
        c = Canvas(W, H)
        u = ease = 1 - (1 - (f + 1) / n) ** 2
        r = 4 + (R - 4) * ease
        if f == 0:
            c.disc(cx, cy, 6, 1.0, squash=0.4)
        if f < n - 1:
            rw = p.get("ring_w", 3.5)
            width = rw * (1 - u) + 0.5
            if f < n - 3:
                width = max(2.0, width)
            c.ring(cx, cy, r, max(1.0, width), 0.95 - 0.5 * u, squash=0.36)
        for k in range(6):                      # dust puffs riding the rim
            a = math.pi * (k + 0.5) / 6
            for sgn in (-1, 1):
                x = cx + sgn * r * math.cos(a) * 0.98
                y = cy + r * math.sin(a) * 0.36 * (1 if k % 2 else -1)
                if f > 0 and f < n - 1:
                    c.disc(x, y - f * 0.4, max(0.6, 2.2 * (1 - u)), 0.45)
        for vx, vy, b in chips:                 # debris arcs
            t = f + 0.5
            x = cx + vx * 9 * t / n * 3
            y = cy - vy * t + 0.35 * t * t
            if y < cy + 2 and f < n - 1:
                c.dot(x, y, 2 if f < 3 else 1, 0.55 + 0.4 * b)
        frames.append(c)
    return frames


EFFECTS: Dict[str, Callable[[Dict], List[Canvas]]] = {
    "shockwave": fx_shockwave,
    "sparkle": fx_sparkle, "leaves": fx_leaves,
    "slash": fx_slash, "hit_spark": fx_hit_spark, "burst": fx_burst, "eruption": fx_eruption,
    "aura": fx_aura, "dust": fx_dust, "projectile": fx_projectile, "lightning": fx_lightning,
}


def render_effect(kind: str, params: Dict, ramp_hex: Sequence[str]) -> List[np.ndarray]:
    ramp = [hex_to_rgb(h) for h in ramp_hex]
    return [c.to_rgba(ramp) for c in EFFECTS[kind](params)]

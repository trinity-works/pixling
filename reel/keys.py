"""Pose-driven key selection: keys land on poses, not on clock ticks.

Time-spaced keys fail on generated clips: a fast strike gets one key and a long hold gets four identical ones.
Here each segment is resampled by *arclength* (cumulative silhouette change), so keys are spread over the
motion itself; the attack is anchored on measured poses (anticipation start, apex = highest silhouette top,
strike = fastest clean frame, contact), and the recovery is cut before any second lift of the weapon.
The silhouette top is a weapon proxy for overhead swings; on side thrusts it is the head, so pass explicit
contact frames there (they are picked by eye anyway).
"""
from __future__ import annotations

import numpy as np

from . import cut


def thumbs(cels, ref, scale):
    return [cut.thumb(c, ref.feet, scale) for c in cels]


def arclength(th):
    d = np.array([0.0] + [float(np.abs(th[i] - th[i - 1]).mean()) for i in range(1, len(th))])
    return np.cumsum(d), d


def pops(th, k=3.0):
    """Frames that jump away from BOTH neighbours while the neighbours agree with each other: generator morphs,
    one-frame flips. Returns a bool mask."""
    n = len(th)
    bad = np.zeros(n, bool)
    dn = np.array([float(np.abs(th[i] - th[i - 1]).mean()) for i in range(1, n)])
    med = float(np.median(dn)) + 1e-6
    for i in range(1, n - 1):
        a, b = dn[i - 1], dn[i]
        skip = float(np.abs(th[i + 1] - th[i - 1]).mean())
        if a > k * med and b > k * med and skip < 0.6 * min(a, b):
            bad[i] = True
    return bad


def fix_pop(i, bad, lo, hi):
    """Move a key off a popped frame to the nearest clean neighbour."""
    if not bad[i]:
        return i
    for r in range(1, 6):
        for j in (i - r, i + r):
            if lo <= j <= hi and not bad[j]:
                return j
    return i


def spaced(A, a, b, k, include_a=True, include_b=True):
    """k frame indices in [a, b] evenly spaced in arclength A (endpoints optional)."""
    if k <= 0:
        return []
    lo, hi = A[a], A[b]
    m = k + (0 if include_a else 1) + (0 if include_b else 1)
    targets = np.linspace(lo, hi, m)
    if not include_a:
        targets = targets[1:]
    if not include_b:
        targets = targets[:-1]
    seg = np.arange(a, b + 1)
    out = [int(seg[np.argmin(np.abs(A[a:b + 1] - t))]) for t in targets]
    # strictly increasing: nudge collisions forward/backward inside the segment
    for i in range(1, len(out)):
        if out[i] <= out[i - 1]:
            out[i] = min(b, out[i - 1] + 1)
    return out


def attack_keys(cels, ref, scale, contact, n=8, hit=4, start=0, end=None, rerise=0.15, log=None):
    """n keys with `contact` on key `hit` (1-indexed).

    pre  (keys 1..hit): anticipation start, weapon apex, strike, contact; extra pre keys spread by arclength.
    post (hit+1..n):    follow-through .. settle, from the recover part only up to the first re-lift of the
                        weapon (tip rises > rerise x body height above its lowest point after contact); the
                        last key is always the final frame (the idle pose the clip returns to).
    """
    end = len(cels) - 1 if end is None else end
    th = thumbs(cels, ref, scale)
    A, d = arclength(th)
    bad = pops(th)
    body = max(1, cut.height(ref))
    h = np.array([c.feet[1] - c.box[1] for c in cels], float)     # silhouette top above the feet: weapon lift

    # anticipation start: the first frame where motion toward the contact really begins
    tot = A[contact] - A[start]
    ant = start
    for i in range(start, contact):
        if A[i] - A[start] > 0.03 * tot:
            ant = max(start, i - 1)
            break
    pre = [ant]
    if hit >= 3:
        hh = np.where(bad[ant:contact + 1], -1e9, h[ant:contact + 1])
        apex = ant + int(np.argmax(hh))                             # weapon at its highest before the hit
        if apex in (ant, contact):
            apex = None
        strike = None
        s0 = apex if apex is not None else ant
        if contact - s0 >= 2:                                       # fastest frame between apex and contact
            dd = np.where(bad[s0 + 1:contact], -1, d[s0 + 1:contact])
            strike = s0 + 1 + int(np.argmax(dd))
        mids = [x for x in (apex, strike) if x is not None]
        need = hit - 2
        if len(mids) > need:
            mids = mids[-need:] if need > 0 else []
        # fill the rest by arclength between anticipation and the first anchored pose
        fill = need - len(mids)
        anchor = mids[0] if mids else contact
        extra = spaced(A, ant, anchor, fill, include_a=False, include_b=False) if fill > 0 else []
        pre += sorted(set(extra + mids))
        if len(pre) < hit - 1:                                      # collisions: fill by arclength, then time
            pre = sorted(set(pre + spaced(A, ant, contact, hit - len(pre), False, False)))[:hit - 1]
        if len(pre) < hit - 1:                                      # segment too short: repeat frames (a hold)
            pre = [int(round(v)) for v in np.linspace(ant, contact, hit)][:hit - 1]
            if log:
                log(f"      wind-up {ant}-{contact} is shorter than {hit - 1} keys; holding frames")
    pre = pre[:hit - 1] + [contact]

    # recovery: cut at the first re-lift of the weapon after contact, measured against the post-contact pose
    # (NE-style facings hold the weapon above the head at contact, so the idle height is not the baseline);
    # the re-lift is skipped and the tail after it (weapon coming down into idle) is keyed instead
    cut_at, lift_end = end, end
    settle = h[contact:min(end, contact + 12) + 1]
    base = max(float(h[0]), float(np.median(settle)))
    high = h > base + rerise * body
    for i in range(contact + 6, end):
        if high[i]:
            j0 = i                                   # back off to where the rise began (local minimum)
            while j0 > contact + 1 and h[j0 - 1] < h[j0] - 0.002 * body:
                j0 -= 1
            cut_at = max(contact + 1, j0 - 1)
            j = i                                    # forward past the lift until the weapon is back down
            while j < end and (high[j] or h[j] > base + 0.04 * body):
                j += 1
            lift_end = min(end, j)
            break
    npost = n - hit
    if cut_at == end:
        post = spaced(A, contact, end, npost, include_a=False, include_b=True)
    else:
        # skip the lift and everything after it except the final (idle) frame: the tail of a re-lift still
        # swings the weapon, and one held key of it reads as a second attack
        post = spaced(A, contact, cut_at, npost - 1, include_a=False, include_b=True) + [end]
    keys = [fix_pop(k, bad, start, end) for k in pre + post]
    keys = keys[:hit - 1] + [contact] + keys[hit:]                    # fix_pop must never move the contact
    for i in range(1, len(keys)):                                     # keep order; repeats only if forced
        if keys[i] < keys[i - 1]:
            keys[i] = keys[i - 1]
    if log:
        log(f"      keys: anticipation {ant}, contact {contact}, re-lift {f'{cut_at + 1}-{lift_end}' if cut_at != end else '-'}"
            f" -> {keys}")
    return keys


def walk_keys(cels, i0, j0, n=8):
    """n keys over one stride [i0, j0) phase-locked to a foot contact: the frame of widest foot spread (lowest
    band width) starts the loop, then keys step evenly in phase (contact, down, pass, up per step)."""
    L = j0 - i0
    width = []
    for c in cels[i0:j0]:
        a = c.rgba[..., 3] >= 128
        y0, y1 = c.box[1] - c.y0, c.box[3] - c.y0
        band = a[int(y1 - (y1 - y0) * 0.12):y1]
        xs = np.nonzero(band.any(0))[0]
        width.append(xs.max() - xs.min() if len(xs) else 0)
    c0 = int(np.argmax(width))
    return [i0 + (c0 + int(round(k * L / n))) % L for k in range(n)]


def drift_offsets(cels, keys, close, origin, band=(0.45, 0.72)):
    """x: remove only the straight-line drift of the pelvis over one loop (first key -> the closing frame, which
    equals the first pose) and centre its mean on origin; the filmed sway stays and the seam is continuous.
    y: the lowest foot is planted on the ground line every key (the body still bobs above it)."""
    px = np.array([cut.torso_x(cels[k], band) for k in keys] + [cut.torso_x(cels[close], band)])
    gy = np.array([cels[k].feet[1] for k in keys] + [cels[close].feet[1]])
    # phase of each key inside the loop (0..1) from source frame distance
    L = close - keys[0]
    if L <= 0:                        # the stride does not fit after the first key: no drift ramp, centre only
        L, px[-1], gy[-1] = 1, px[0], gy[0]
    ph = np.array([((k - keys[0]) % L) / L if L > 1 else 0.0 for k in keys])
    tx = px[0] + (px[-1] - px[0]) * ph
    ty = gy[0] + (gy[-1] - gy[0]) * ph
    mx = float(np.mean(px[:-1] - tx + px[0]))
    dx = origin[0] - (tx - px[0] + mx)
    dy = origin[1] - gy[:-1]           # the planted (lowest) foot stays on the ground line every key
    return dx, dy

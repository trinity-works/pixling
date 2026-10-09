"""Alpha atlases for the card painter (2x2 tiles each): leaf clusters, cloud puffs, grass tufts, flower dots.
python3 textures.py outdir"""
import sys, math, random
from pathlib import Path
from PIL import Image, ImageDraw, ImageFilter

out = Path(sys.argv[1]); out.mkdir(parents=True, exist_ok=True)
T = 512


def leaf(d, x, y, ang, L, W):
    pts = []
    for i in range(13):
        t = i / 12
        w = math.sin(math.pi * t) ** 0.8 * W
        pts.append((t * L, w))
    pts += [(t, -w) for t, w in reversed(pts[1:-1])]
    ca, sa = math.cos(ang), math.sin(ang)
    d.polygon([(x + px * ca - py * sa, y + px * sa + py * ca) for px, py in pts], fill=255)


def leaves_tile(rng):
    im = Image.new('L', (T, T), 0); d = ImageDraw.Draw(im)
    cx, cy = T / 2, T / 2
    for _ in range(rng.randint(26, 34)):
        a = rng.random() * math.tau
        r = (rng.random() ** 0.7) * T * 0.34
        x, y = cx + math.cos(a) * r, cy + math.sin(a) * r
        leaf(d, x, y, a + rng.uniform(-0.9, 0.9), rng.uniform(70, 120), rng.uniform(22, 36))
    for _ in range(rng.randint(3, 6)):          # holes: the sky shows through the clumps
        x, y, r = rng.uniform(T * .25, T * .75), rng.uniform(T * .25, T * .75), rng.uniform(8, 20)
        d.ellipse([x - r, y - r, x + r, y + r], fill=0)
    return im


def dab(d, x, y, ang, L, W):
    """one brush dab: a teardrop L long and 2W wide, round head at (x, y), pointed tail trailing toward the clump centre."""
    ca, sa = math.cos(ang), math.sin(ang)
    pts = []
    for i in range(32):
        th = i / 32 * math.tau
        px = L / 2 * (math.cos(th) - 1)                         # head end at 0, tail at -L
        py = W * math.sin(th) * ((1 + math.cos(th)) / 2) ** .45
        pts.append((x + px * ca - py * sa, y + px * sa + py * ca))
    d.polygon(pts, fill=255)


def dabs_tile(rng):
    """the tutorial's alpha: separate fat rounded dabs fanned out from a denser centre, like stamps of a leaf brush."""
    S = 2   # drawn at 2x and reduced, so the dab edges are smooth
    im = Image.new('L', (T * S, T * S), 0); d = ImageDraw.Draw(im)
    c = T * S / 2
    for _ in range(rng.randint(28, 34)):
        a = rng.random() * math.tau
        r = (rng.random() ** 0.6) * T * S * 0.33 + T * S * .04
        W = rng.uniform(.036, .048) * T * S
        dab(d, c + math.cos(a) * r, c + math.sin(a) * r, a + rng.uniform(-.7, .7), W * rng.uniform(3.2, 4.0), W)
    return im.resize((T, T), Image.LANCZOS)


def puff_tile(rng):
    im = Image.new('L', (T, T), 0); d = ImageDraw.Draw(im)
    for _ in range(rng.randint(9, 14)):
        a, r = rng.random() * math.tau, rng.random() ** 0.6 * T * 0.26
        x, y, s = T / 2 + math.cos(a) * r, T / 2 + math.sin(a) * r * 0.8, rng.uniform(50, 105)
        d.ellipse([x - s, y - s, x + s, y + s], fill=255)
    return im


def grass_tile(rng):
    im = Image.new('L', (T, T), 0); d = ImageDraw.Draw(im)
    for _ in range(rng.randint(22, 30)):
        x0 = rng.uniform(T * .15, T * .85); h = rng.uniform(T * .35, T * .9); lean = rng.uniform(-90, 90)
        w = rng.uniform(7, 14)
        d.polygon([(x0 - w, T), (x0 + w, T), (x0 + lean, T - h)], fill=255)
    return im


def flower_tile(rng):
    im = grass_tile(rng).point(lambda v: v // 2)    # grey = stem, white = petals
    d = ImageDraw.Draw(im)
    for _ in range(rng.randint(10, 16)):
        x, y, r = rng.uniform(T * .15, T * .85), rng.uniform(T * .1, T * .6), rng.uniform(12, 22)
        d.ellipse([x - r, y - r, x + r, y + r], fill=255)
    return im


def atlas(fn, name, seed, blur=0):
    rng = random.Random(seed)
    a = Image.new('L', (T * 2, T * 2), 0)
    for i in range(4):
        t = fn(rng)
        a.paste(t, ((i % 2) * T, (i // 2) * T))
    if blur:
        a = a.filter(ImageFilter.GaussianBlur(blur))
    a.save(out / f'{name}.png')


atlas(leaves_tile, 'leaves', 3)
atlas(dabs_tile, 'dabs', 4)
atlas(puff_tile, 'puffs', 5, blur=2)
atlas(grass_tile, 'grass', 7)
atlas(flower_tile, 'flowers', 9)
print('ok')

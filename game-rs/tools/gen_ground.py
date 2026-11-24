"""Новое дно зон: бесшовные плитки 512×512 (песчаная рябь, камешки, пятна ила, трещины)
и текстура бликов-каустики для бегущего света. Запуск: python3 tools/gen_ground.py
"""
import os
import numpy as np
from PIL import Image

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, '..', 'assets')
N = 512
yy, xx = np.mgrid[0:N, 0:N].astype(np.float32) / N   # 0..1, период 1


def pnoise(freq, seed):
    """Бесшовный шум: сумма синусов с целыми частотами (период 1)."""
    rng = np.random.default_rng(seed)
    out = np.zeros((N, N), np.float32)
    for _ in range(10):
        fx, fy = rng.integers(-freq, freq + 1, 2)
        if fx == 0 and fy == 0:
            continue
        ph = rng.uniform(0, 2 * np.pi)
        out += np.sin(2 * np.pi * (fx * xx + fy * yy) + ph) / np.hypot(fx, fy) ** .5
    out -= out.min(); out /= out.max() + 1e-6
    return out


def fbm(seed, base=2, octs=5):
    o = np.zeros((N, N), np.float32); a = 1; s = 0
    for k in range(octs):
        o += pnoise(base * 2 ** k, seed + k) * a; s += a; a *= .5
    return o / s


def blur_wrap(img, r):
    from scipy.ndimage import gaussian_filter
    return gaussian_filter(img, r, mode='wrap')


def hexc(h):
    return np.array([(h >> 16) & 255, (h >> 8) & 255, h & 255], np.float32) / 255


# зоны: (вид, основной цвет песка, цвет тени, акцент)
ZONES = [
    ('sand', 0x2c6d80, 0x123a52, 0x7fe8ff),   # 1 сумеречная толща
    ('sand', 0x2a5f84, 0x15304f, 0xff8ad8),   # 2 коралловый сад
    ('sand', 0x2a7a7c, 0x113f4a, 0x6dffe0),   # 3 рифы
    ('rock', 0x2a4878, 0x14234a, 0x7cb4ff),   # 4 скалы
    ('rock', 0x40397a, 0x1d1a48, 0xc79bff),   # 5 колонны
    ('bone', 0x51406e, 0x261d40, 0xffc078),   # 6 костяные поля
    ('moss', 0x285f66, 0x10333e, 0x7bffb0),   # 7 грибной лес
    ('ice', 0x3a7aa6, 0x1a3d66, 0xc8f4ff),    # 8 ледник
    ('lava', 0x4a2648, 0x200f26, 0xff8a40),   # 9 жерла
    ('crys', 0x473e8c, 0x211c50, 0xe9a8ff),   # 10 кристаллы
    ('ice', 0x34558f, 0x18284f, 0xa8c4ff),    # 11
    ('rock', 0x2e3466, 0x15183a, 0x8aa6ff),   # 12
    ('moss', 0x1f6a5e, 0x0c3532, 0x6dffc0),   # 13
    ('lava', 0x57233e, 0x240c1e, 0xff6f9e),   # 14
    ('lava', 0x372460, 0x150c30, 0xd77aff),   # 15 сердце бездны
]


def pebbles(seed, n, rmin, rmax):
    """Камешки: высота-купол с затенением сверху-слева."""
    rng = np.random.default_rng(seed)
    h = np.zeros((N, N), np.float32)
    for _ in range(n):
        cx, cy = rng.random(2); r = rng.uniform(rmin, rmax) / N; e = rng.uniform(.6, 1)
        dx = (xx - cx + .5) % 1 - .5; dy = (yy - cy + .5) % 1 - .5
        d = np.hypot(dx / e, dy) / r
        h = np.maximum(h, np.clip(1 - d * d, 0, 1) ** .5)
    return h


def cracks(seed, n, width):
    rng = np.random.default_rng(seed)
    m = np.zeros((N, N), np.float32)
    for _ in range(n):
        x, y = rng.random(2); a = rng.uniform(0, 2 * np.pi)
        for _ in range(170):
            a += rng.normal(0, .18); x2 = x + np.cos(a) * .0035; y2 = y + np.sin(a) * .0035
            dx = (xx - x + .5) % 1 - .5; dy = (yy - y + .5) % 1 - .5
            m = np.maximum(m, np.clip(1 - np.hypot(dx, dy) * N / width, 0, 1))
            x, y = x2 % 1, y2 % 1
    return m


def shade(h, k=6.0):
    gy, gx = np.gradient(np.pad(h, 1, mode='wrap'))
    gx, gy = gx[1:-1, 1:-1], gy[1:-1, 1:-1]
    return np.clip(.5 + (-gx - gy) * k * N / 512, 0, 1)   # свет сверху-слева


def tile(z):
    kind, base, dark, acc = ZONES[z]
    base, dark, acc = hexc(base), hexc(dark), hexc(acc)
    seed = z * 100
    big = fbm(seed, 2, 4)                         # крупные пятна
    mid = fbm(seed + 10, 6, 3)
    t = np.clip(big * 1.2 - .1, 0, 1)
    col = dark[None, None] * (1 - t[..., None]) + base[None, None] * t[..., None]
    h = np.zeros((N, N), np.float32)
    if kind in ('sand', 'moss', 'bone', 'crys'):
        # песчаная рябь: волны, изогнутые шумом
        warp = fbm(seed + 20, 3, 3) * 2.2
        rip = np.sin(2 * np.pi * (yy * 9 + xx * 2) + warp * 6)
        rip = (rip * .5 + .5) ** 2
        h += rip * .35 * (0.5 + .5 * mid)
    if kind in ('rock', 'lava', 'ice', 'crys'):
        h += fbm(seed + 30, 4, 5) * .9
    p = pebbles(seed + 40, 45 if kind != 'ice' else 20, 3, 10)
    h += p * .6
    sh = shade(h, 2.2 if kind != 'rock' else 3.0)
    col = col * (.62 + .76 * sh[..., None])
    # мелкое зерно
    rng = np.random.default_rng(seed + 50)
    grain = rng.random((N, N)).astype(np.float32)
    col *= (.94 + .12 * grain[..., None])
    if kind == 'moss':
        m = np.clip(fbm(seed + 60, 5, 3) * 1.6 - .7, 0, 1)
        col = col * (1 - m[..., None] * .5) + hexc(0x1d8a6a)[None, None] * m[..., None] * .5
    if kind == 'bone':
        c = cracks(seed + 70, 6, 2.5)
        col = col * (1 - c[..., None] * .35) + hexc(0xd9c9b0)[None, None] * c[..., None] * .35
    if kind in ('lava',):
        c = blur_wrap(cracks(seed + 80, 6, 1.8), .8)
        col = col * (1 - c[..., None] * .45) + acc[None, None] * c[..., None] * .55
    if kind in ('ice',):
        c = cracks(seed + 90, 7, 1.6)
        col = col + acc[None, None] * c[..., None] * .22
    if kind == 'crys':
        c = pebbles(seed + 95, 25, 3, 6)
        col = col + acc[None, None] * c[..., None] * .25
    # светящиеся точки планктона на дне
    g = pebbles(seed + 99, 18, 1, 2.2)
    col = col + acc[None, None] * blur_wrap(g, 1.5)[..., None] * .45
    return np.clip(col * .88, 0, 1)


def caustic():
    """Каустика: светлые сетчатые линии, бесшовно. Альфа = яркость."""
    n = 256
    y, x = np.mgrid[0:n, 0:n].astype(np.float32) / n
    rng = np.random.default_rng(7)
    pts = rng.random((26, 2))
    d1 = np.full((n, n), 9.0); d2 = np.full((n, n), 9.0)
    for px, py in pts:
        dx = (x - px + .5) % 1 - .5; dy = (y - py + .5) % 1 - .5
        d = np.hypot(dx, dy)
        d2 = np.where(d < d1, d1, np.minimum(d2, d)); d1 = np.minimum(d1, d)
    edge = d2 - d1                              # близко к нулю на границах ячеек
    v = np.exp(-(edge / .022) ** 2) * .8 + np.exp(-(edge / .06) ** 2) * .25
    from scipy.ndimage import gaussian_filter
    v = gaussian_filter(v, 1.6, mode='wrap')
    v = v / v.max()
    img = np.zeros((n, n, 4), np.uint8)
    img[..., :3] = 255; img[..., 3] = (v * 255).astype(np.uint8)
    Image.fromarray(img).save(os.path.join(OUT, 'fx', 'caustic.png'))


if __name__ == '__main__':
    import sys
    for z in (range(15) if 'caustic' not in sys.argv else []):
        Image.fromarray((tile(z) * 255).astype(np.uint8)).save(os.path.join(OUT, 'ground', f'g{z}.png'))
        print('ground', z)
    caustic()
    print('caustic')

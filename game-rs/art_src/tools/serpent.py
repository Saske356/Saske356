"""4.5: Левиафан-змея из прямой картинки art_src/new45/leviathan_src.png.
Пишет в assets/spr:
  serp.png      — всё тело (голова справа, хвост слева), центр тела ровно по середине высоты; челюсть вырезана
  serp_jaw.png  — только нижняя челюсть (тот же холст)
  serp_t1*.png, serp_t2*.png — огненный и теневой варианты (сдвиг оттенка)
и meta["serp"] в manifest.json: длина/толщина (aspect), шарнир челюсти (hinge, в долях холста).
Игра режет тело на полосы и гнёт вдоль следа головы (render::serpent).  Запуск из game-rs: python3 art_src/tools/serpent.py
"""
import os, json, colorsys
import numpy as np
from PIL import Image, ImageDraw, ImageFilter
HERE = os.path.dirname(os.path.abspath(__file__)); ROOT = os.path.abspath(os.path.join(HERE, '..', '..'))
SRC = os.path.join(ROOT, 'art_src', 'new45', 'leviathan_src.png'); SPR = os.path.join(ROOT, 'assets', 'spr'); MAN = os.path.join(ROOT, 'assets', 'manifest.json')
X0, X1, CY, HALF = 15, 2160, 362, 223          # обрезка: по ширине и по высоте вокруг оси тела
W = 1536
JAW = [(1905, 352), (1965, 352), (2040, 372), (2118, 356), (2132, 420), (2105, 480), (2075, 545), (2010, 548), (1950, 520), (1893, 462), (1872, 402)]
HINGE = (1912, 360)

def hue_shift(im, deg, sat=1.0):
    a = np.asarray(im).astype(np.float32) / 255.; rgb = a[..., :3]
    mx = rgb.max(-1); mn = rgb.min(-1); d = mx - mn + 1e-6
    r, g, b = rgb[..., 0], rgb[..., 1], rgb[..., 2]
    h = np.where(mx == r, ((g - b) / d) % 6, np.where(mx == g, (b - r) / d + 2, (r - g) / d + 4)) / 6.
    s = np.where(mx > 0, d / (mx + 1e-6), 0); v = mx
    h = (h + deg / 360.) % 1.; s = np.clip(s * sat, 0, 1)
    i = np.floor(h * 6).astype(int) % 6; f = h * 6 - np.floor(h * 6)
    p, q, t = v * (1 - s), v * (1 - s * f), v * (1 - s * (1 - f))
    out = np.zeros_like(rgb)
    for k, (R, G, B) in enumerate([(v, t, p), (q, v, p), (p, v, t), (p, q, v), (t, p, v), (v, p, q)]):
        m = i == k; out[..., 0][m] = R[m]; out[..., 1][m] = G[m]; out[..., 2][m] = B[m]
    a[..., :3] = out; return Image.fromarray((a * 255).astype(np.uint8))

def main():
    im = Image.open(SRC).convert('RGBA').crop((X0, CY - HALF, X1, CY + HALF)); s = W / im.size[0]
    im = im.resize((W, round(im.size[1] * s)), Image.LANCZOS); H = im.size[1]
    tr = lambda p: ((p[0] - X0) * s, (p[1] - CY + HALF) * s)
    m = Image.new('L', im.size, 0); ImageDraw.Draw(m).polygon([tr(p) for p in JAW], fill=255); m = m.filter(ImageFilter.GaussianBlur(1.2))
    mk = np.asarray(m).astype(np.float32) / 255.; a = np.asarray(im).astype(np.float32)
    body = a.copy(); body[..., 3] *= 1 - mk; jaw = a.copy(); jaw[..., 3] *= mk
    # мелкие оторванные кусочки (кончик плавника, клыка) — туда, где их часть больше
    from scipy import ndimage as nd
    for src, dst in ((body, jaw), (jaw, body)):
        lab, n = nd.label(src[..., 3] > 25)
        if n < 2: continue
        sizes = nd.sum(np.ones_like(lab), lab, range(1, n + 1)); big = sizes.max()
        for k, sz in enumerate(sizes, 1):
            if sz < big * 0.02:
                m2 = nd.binary_dilation(lab == k, iterations=2); dst[m2] = np.maximum(dst[m2], a[m2]) if False else dst[m2]
                dst[..., 3][m2] = np.maximum(dst[..., 3][m2], a[..., 3][m2]); dst[..., :3][m2] = a[..., :3][m2]; src[..., 3][m2] = 0
    variants = {'': (0, 1.0), '_t1': (-150, 1.2), '_t2': (100, 0.95)}
    man = json.load(open(MAN))
    for suf, (deg, sat) in variants.items():
        for nm, arr in (('serp', body), ('serp_jaw', jaw)):
            img = Image.fromarray(arr.astype(np.uint8))
            if deg: img = hue_shift(img, deg, sat)
            img.save(os.path.join(SPR, nm.replace('serp', 'serp' + suf, 1) + '.png'))
        hx, hy = tr(HINGE)
        for nm in ('serp' + suf, 'serp' + suf + '_jaw'):
            man['meta'][nm] = {'h': 60, 'r': 30, 'art': True, 'fl': False, 'live': False, 'w': W, 'aspect': round(W / H, 4), 'hinge': [round(hx / W, 4), round(hy / H, 4)]}
    json.dump(man, open(MAN, 'w'), ensure_ascii=False)
    print('serp', W, H, 'hinge', tr(HINGE))

if __name__ == '__main__':
    main()

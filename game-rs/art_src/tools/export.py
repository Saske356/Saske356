"""Готовит новые спрайты для игры: плотная альфа, поворот, размер как у старых, ярусы _t1/_t2, перекраски обликов."""
import numpy as np, json, os, colorsys
from PIL import Image, ImageFilter
SPR = '/home/user/game/game-rs/assets/spr'; OLD = 'old'; CUT = 'cut'

def solid(im, lo=10, hi=70):
    a = np.asarray(im).astype(np.float32); al = a[..., 3]
    t = np.clip((al - lo) / (hi - lo), 0, 1); t = t * t * (3 - 2 * t)
    a[..., 3] = t * 255
    return Image.fromarray(a.astype(np.uint8))

def fill_ratio(path):
    a = np.asarray(Image.open(path).convert('RGBA'))[..., 3]; ys, xs = np.where(a > 20)
    return max(xs.max() - xs.min(), ys.max() - ys.min()) / a.shape[0]

def place(im, size, ratio):
    w, h = im.size; k = size * ratio / max(w, h)
    im = im.resize((max(1, round(w * k)), max(1, round(h * k))), Image.LANCZOS)
    c = Image.new('RGBA', (size, size)); c.alpha_composite(im, ((size - im.width) // 2, (size - im.height) // 2)); return c

def hue_to(im, hue, mix=1.0, sat=1.0, val=1.0):
    a = np.asarray(im).astype(np.float32) / 255; rgb = a[..., :3]
    mx = rgb.max(-1); mn = rgb.min(-1); d = mx - mn + 1e-6
    # HSV вручную (векторно)
    r, g, b = rgb[..., 0], rgb[..., 1], rgb[..., 2]
    h = np.where(mx == r, ((g - b) / d) % 6, np.where(mx == g, (b - r) / d + 2, (r - g) / d + 4)) / 6
    s = np.where(mx > 0, d / (mx + 1e-6), 0); v = mx
    dh = ((hue - h + .5) % 1) - .5; h = (h + dh * mix) % 1
    s = np.clip(s * sat, 0, 1); v = np.clip(v * val, 0, 1)
    i = np.floor(h * 6); f = h * 6 - i; p = v * (1 - s); q = v * (1 - f * s); t = v * (1 - (1 - f) * s); i = i.astype(int) % 6
    out = np.stack([np.choose(i, [v, q, p, p, t, v]), np.choose(i, [t, v, v, q, p, p]), np.choose(i, [p, p, t, v, v, q])], -1)
    a[..., :3] = out
    return Image.fromarray((a * 255).astype(np.uint8))

def rot_hue(im, deg, sat=1.0, val=1.0):
    a = np.asarray(im).astype(np.float32) / 255; rgb = a[..., :3]
    mx = rgb.max(-1); mn = rgb.min(-1); d = mx - mn + 1e-6; r, g, b = rgb[..., 0], rgb[..., 1], rgb[..., 2]
    h = np.where(mx == r, ((g - b) / d) % 6, np.where(mx == g, (b - r) / d + 2, (r - g) / d + 4)) / 6
    return hue_to(im, 0, 0, sat, val) if deg == 0 else _shift(im, deg / 360, sat, val)

def _shift(im, dh, sat, val):
    a = np.asarray(im).astype(np.float32) / 255; rgb = a[..., :3]
    mx = rgb.max(-1); mn = rgb.min(-1); d = mx - mn + 1e-6; r, g, b = rgb[..., 0], rgb[..., 1], rgb[..., 2]
    h = np.where(mx == r, ((g - b) / d) % 6, np.where(mx == g, (b - r) / d + 2, (r - g) / d + 4)) / 6
    s = np.where(mx > 0, d / (mx + 1e-6), 0) * sat; v = np.clip(mx * val, 0, 1); s = np.clip(s, 0, 1); h = (h + dh) % 1
    i = np.floor(h * 6); f = h * 6 - i; p = v * (1 - s); q = v * (1 - f * s); t = v * (1 - (1 - f) * s); i = i.astype(int) % 6
    a[..., :3] = np.stack([np.choose(i, [v, q, p, p, t, v]), np.choose(i, [t, v, v, q, p, p]), np.choose(i, [p, p, t, v, v, q])], -1)
    return Image.fromarray((a * 255).astype(np.uint8))

man = json.load(open('/home/user/game/game-rs/assets/manifest.json'))
done = []
ROT = {'jelly': -90}
FILL = {'pl_amethyst', 'pl_void', 'pl_azure', 'pl_ember', 'pl_emerald', 'queen', 'pl_frost', 'pl_coral', 'pl_ghost', 'pl_inferno', 'pl_aurora', 'pl_royal'}
for f in sorted(os.listdir(CUT)):
    name = f[:-4]
    if not os.path.exists(f'{OLD}/{name}.png'): continue
    TH = {'boss4': (90, 170), 'pl_azure': (3, 20), 'pl_amethyst': (3, 20), 'pl_void': (2, 14), 'queen': (4, 24), 'pl_solar': (3, 20), 'pl_ember': (4, 26), 'pl_emerald': (4, 26)}
    im = solid(Image.open(f'{CUT}/{f}').convert('RGBA'), *TH.get(name, (10, 70)))
    if name in FILL:   # дыры в плавниках (там, где на чёрном фоне был тёмный цвет) — заполнить
        from scipy import ndimage as nd
        a = np.asarray(im).copy(); m = nd.binary_closing(a[..., 3] > 40, iterations=4); m = nd.binary_fill_holes(m)
        mm = np.asarray(Image.fromarray((m * 255).astype(np.uint8)).filter(ImageFilter.GaussianBlur(1.2))).astype(np.float32)
        a[..., 3] = np.maximum(a[..., 3], mm).astype(np.uint8); im = Image.fromarray(a)
    if name in ROT: im = im.rotate(ROT[name], expand=True, resample=Image.BICUBIC)
    size = Image.open(f'{OLD}/{name}.png').size[0]
    ratio = min(0.97, fill_ratio(f'{OLD}/{name}.png'))
    out = place(im, size, ratio); out.save(f'{SPR}/{name}.png'); done.append(name)
    # ярусы глубины: багровый (_t1) и бездна (_t2)
    if os.path.exists(f'{OLD}/{name}_t1.png'):
        hue_to(out, 0.99, 0.85, 1.15, 0.92).save(f'{SPR}/{name}_t1.png')
        hue_to(out, 0.76, 0.85, 1.05, 0.72).save(f'{SPR}/{name}_t2.png')
# облики Люмена без своих картинок — перекраски новых
def sk(src, name, fn):
    out = fn(Image.open(f'{SPR}/{src}.png').convert('RGBA')); out.save(f'{SPR}/{name}.png'); done.append(name)
# лучшая модель (сине-золотая, на прозрачном фоне) — основной облик; бледная голубая — «бездна»
import shutil; shutil.copy(f'{SPR}/pl_azure.png', f'{SPR}/pl_abyss.png'); shutil.copy(f'{SPR}/pl_solar.png', f'{SPR}/pl_azure.png'); done.append('pl_abyss')
sk('pl_abyss', 'pl_abyss', lambda i: _shift(i, 0.03, 1.3, 1.2))
sk('pl_amethyst', 'pl_amethyst', lambda i: _shift(i, 0.0, 1.45, 1.4))
sk('queen', 'queen', lambda i: _shift(i, 0.0, 1.3, 1.25))
sk('pl_ember', 'pl_solar', lambda i: hue_to(i, 0.13, 0.9, 1.0, 1.08))
sk('pl_abyss', 'pl_amber', lambda i: hue_to(i, 0.09, 1.0, 1.25, 1.0))
sk('pl_emerald', 'pl_venom', lambda i: hue_to(i, 0.24, 0.9, 1.3, 1.05))
sk('pl_emerald', 'pl_jade', lambda i: hue_to(i, 0.45, 0.85, 0.9, 1.0))
sk('pl_amethyst', 'pl_nebula', lambda i: _shift(i, -0.12, 1.1, 1.0))
sk('pl_abyss', 'pl_cyber', lambda i: hue_to(i, 0.86, 1.0, 1.35, 1.05))
sk('pl_frost', 'pl_lunar', lambda i: hue_to(i, 0.62, 1.0, 0.25, 1.05))
sk('pl_aurora', 'pl_prism', lambda i: _shift(i, 0.33, 1.15, 1.05))
sk('pl_coral', 'pl_dawn', lambda i: hue_to(i, 0.08, 0.6, 1.1, 1.05))
print(len(done), sorted(done))

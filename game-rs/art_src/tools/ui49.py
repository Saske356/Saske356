"""4.9.4: элементы интерфейса из листов ChatGPT (art_src/ui49/*_src.png) → assets/ui/*.png.
Каждый элемент: вырезка по альфе → очистка ореола → шумоподавление (сглаживание «нейросетевой» зернистости) →
симметрия для симметричных деталей (кнопки, рамки, полосы) → подтяжка цвета к палитре игры → уменьшение до игрового
размера с лёгкой резкостью. Запуск из game-rs: python3 art_src/tools/ui49.py"""
import os, numpy as np, cv2
from PIL import Image, ImageFilter

SRC = 'art_src/ui49'; OUT = 'assets/ui'; os.makedirs(OUT, exist_ok=True)
# палитра игры (оттенок HSV 0..180 в OpenCV)
CYAN, GOLD, PINK, TEAL, CORAL = 94, 23, 145, 88, 176

def load(name): return np.asarray(Image.open(f'{SRC}/{name}_src.png').convert('RGBA')).astype(np.float32)

def crop(img, x, y, w, h, pad=14):
    H, W = img.shape[:2]; x0, y0, x1, y1 = max(0, x - pad), max(0, y - pad), min(W, x + w + pad), min(H, y + h + pad)
    return img[y0:y1, x0:x1].copy()

def clean_alpha(a, lo=26, hi=235):
    """ореол бледнее lo — прочь, плотнее hi — полностью непрозрачно"""
    return np.clip((a - lo) / (hi - lo), 0, 1) * 255

def denoise(rgb):
    u8 = np.clip(rgb, 0, 255).astype(np.uint8)
    u8 = cv2.bilateralFilter(u8, 7, 28, 5)           # гладит зерно, края держит
    return u8.astype(np.float32)

def hue_pull(rgb, a, target, strength=0.65, width=22):
    """оттенки рядом с target стягиваются к нему: ровный цвет, как у отрисованного вручную"""
    u8 = np.clip(rgb, 0, 255).astype(np.uint8); hsv = cv2.cvtColor(u8, cv2.COLOR_RGB2HSV).astype(np.float32)
    h = hsv[:, :, 0]; d = ((h - target + 90) % 180) - 90; m = (np.abs(d) < width) & (hsv[:, :, 1] > 40)
    h[m] = (h[m] - d[m] * strength) % 180; hsv[:, :, 0] = h
    return cv2.cvtColor(hsv.astype(np.uint8), cv2.COLOR_HSV2RGB).astype(np.float32)

def mirror_x(img, keep='left'):
    """симметрия слева-направо с плавным швом посередине"""
    H, W = img.shape[:2]; f = img[:, ::-1]; t = np.clip((np.arange(W) - W * 0.42) / (W * 0.16), 0, 1)[None, :, None]
    if keep == 'right': t = 1 - t[:, ::-1]; return img * t + f * (1 - t)
    return img * (1 - t) + f * t

def trim(img, thr=8):
    a = img[:, :, 3]; ys, xs = np.where(a > thr)
    if len(xs) == 0: return img
    return img[ys.min():ys.max() + 1, xs.min():xs.max() + 1]

def save(img, name, w=None, h=None, sharpen=True):
    img = trim(img); im = Image.fromarray(np.clip(img, 0, 255).astype(np.uint8), 'RGBA')
    if w or h:
        W, H = im.size; k = (w / W) if w else (h / H); im = im.resize((max(1, round(W * k)), max(1, round(H * k))), Image.LANCZOS)
    if sharpen:
        rgb = im.convert('RGB').filter(ImageFilter.UnsharpMask(radius=1.2, percent=55, threshold=2)); r, g, b = rgb.split(); im = Image.merge('RGBA', (r, g, b, im.split()[3]))
    im.save(f'{OUT}/{name}.png', optimize=True); return im.size

def stylize(rgb, a, k=11):
    """4.9.5: «рисованный» вид вместо нейросетевого: фактура и искры — прочь (сглаживание с сохранением краёв),
    цвета — к ограниченной палитре с мягкими переходами, приглушить насыщенность и пересветы"""
    u8 = np.clip(rgb, 0, 255).astype(np.uint8)
    sm = cv2.edgePreservingFilter(u8, flags=1, sigma_s=30, sigma_r=0.22)
    sm = cv2.pyrMeanShiftFiltering(sm, 5, 18)
    m = a > 60; px = sm[m].reshape(-1, 3).astype(np.float32)
    if len(px) > k * 4:
        crit = (cv2.TERM_CRITERIA_EPS + cv2.TERM_CRITERIA_MAX_ITER, 20, 1.0)
        _, lab, cen = cv2.kmeans(px, k, None, crit, 2, cv2.KMEANS_PP_CENTERS); q = sm.copy(); q[m] = cen[lab.flatten()].astype(np.uint8)
        q = cv2.GaussianBlur(q, (0, 0), 1.1); sm = cv2.addWeighted(q, 0.6, sm, 0.4, 0)
    hsv = cv2.cvtColor(sm, cv2.COLOR_RGB2HSV).astype(np.float32); hsv[:, :, 1] *= 0.86; hsv[:, :, 2] = np.minimum(hsv[:, :, 2], 238)
    return cv2.cvtColor(np.clip(hsv, 0, 255).astype(np.uint8), cv2.COLOR_HSV2RGB).astype(np.float32)

def outline(img, w=2, col=(9, 22, 40)):
    """чёткий тёмный контур по силуэту (как у отрисованного интерфейса) вместо размытого ореола"""
    a = img[:, :, 3]; m = (a > 128).astype(np.uint8); pad = w + 2
    img = np.pad(img, ((pad, pad), (pad, pad), (0, 0))); m = np.pad(m, pad)
    d = cv2.dilate(m, cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (2 * w + 1, 2 * w + 1)))
    ring = (d > 0) & (img[:, :, 3] < 200); al = img[:, :, 3:4] / 255.
    base = np.zeros_like(img); base[:, :, :3] = col; base[:, :, 3] = d * 235
    out = img.copy(); out[:, :, :3] = img[:, :, :3] * al + base[:, :, :3] * (1 - al); out[:, :, 3] = np.maximum(img[:, :, 3], base[:, :, 3])
    return out

def proc(img, hue=None, sym=False, strength=0.6, lo=26, style=True):
    a = clean_alpha(img[:, :, 3], max(lo, 70) if style else lo); rgb = denoise(img[:, :, :3])
    if style: rgb = stylize(rgb, a)
    if hue is not None: rgb = hue_pull(rgb, a, hue, strength)
    out = np.dstack([rgb, a])
    if sym: out = mirror_x(out)
    if style: out = outline(out)
    return out

def job(sheet, items):
    img = load(sheet); sizes = {}
    for name, (x, y, w, h), kw in items:
        size = kw.pop('size', {}); c = crop(img, x, y, w, h); sizes[name] = save(proc(c, **kw), name, **size)
    return sizes

hud = [
    ('dash', (35, 56, 324, 311), dict(hue=CYAN, sym=False, size=dict(w=256))),
    ('dash_cd', (418, 57, 323, 310), dict(hue=CYAN, size=dict(w=256))),
    ('super_frame', (782, 31, 357, 353), dict(hue=GOLD, sym=True, size=dict(w=300))),
    ('super_on', (1163, 25, 360, 369), dict(hue=GOLD, sym=True, size=dict(w=300))),
    ('pause', (60, 434, 268, 272), dict(hue=CYAN, sym=True, size=dict(w=160))),
    ('snd_on', (444, 435, 268, 272), dict(hue=CYAN, size=dict(w=160))),
    ('snd_off', (823, 435, 269, 270), dict(hue=CYAN, size=dict(w=160))),
    ('bar_hp', (11, 797, 360, 121), dict(hue=CORAL, sym=True, strength=0.4, size=dict(w=420))),
    ('bar_xp', (395, 804, 361, 96), dict(hue=CYAN, sym=True, size=dict(w=420))),
    ('bar_boss', (786, 796, 445, 133), dict(hue=PINK, sym=True, size=dict(w=520))),
    ('pill', (1287, 799, 238, 112), dict(hue=GOLD, sym=True, size=dict(w=240))),
]
icons = []
pos = [(16, 26), (320, 27), (623, 26), (926, 26), (1230, 26), (15, 354), (320, 355), (623, 354), (926, 354), (1231, 354), (15, 674), (341, 674), (681, 674), (1023, 675)]
for k, (x, y) in enumerate(pos): icons.append((f'ab{k}', (x, y, 300 if k >= 11 else 292, 300), dict(size=dict(w=200))))
menu = [
    ('btn_blue', (16, 54, 362, 147), dict(hue=CYAN, sym=True, size=dict(w=360))),
    ('btn_gold', (396, 54, 362, 147), dict(hue=GOLD, sym=True, size=dict(w=360))),
    ('btn_pink', (778, 54, 363, 147), dict(hue=PINK, sym=True, size=dict(w=360))),
    ('btn_teal', (1160, 53, 363, 148), dict(hue=TEAL, sym=True, size=dict(w=360))),
    ('btn_press', (14, 274, 364, 145), dict(hue=CYAN, sym=True, size=dict(w=360))),
    ('tab_off', (396, 275, 362, 145), dict(sym=True, size=dict(w=300))),
    ('tab_on', (778, 274, 366, 148), dict(hue=CYAN, sym=True, size=dict(w=300))),
    ('back', (1255, 257, 195, 185), dict(hue=CYAN, size=dict(w=140))),
    ('card', (15, 479, 356, 194), dict(hue=CYAN, size=dict(w=420))),
    ('card_gold', (396, 479, 358, 194), dict(hue=GOLD, size=dict(w=420))),
    ('card_evo', (780, 463, 360, 229), dict(hue=PINK, strength=0.4, size=dict(w=420))),
    ('card_lock', (1166, 478, 355, 208), dict(size=dict(w=420))),
    ('modal', (781, 713, 386, 260), dict(hue=CYAN, sym=True, strength=0.4, size=dict(w=480))),
    ('pearl', (1250, 742, 216, 213), dict(size=dict(w=96))),
    ('price', (10, 774, 373, 138), dict(hue=GOLD, size=dict(w=300))),
]
if __name__ == '__main__':
    print(job('hud', hud)); print(job('icons', icons)); print(job('menu', menu))
    # самоцветы для делений уровня: первый (горит) и последний (погас) из полосы
    img = load('menu'); strip = crop(img, 404, 798, 342, 85, pad=6); a = strip[:, :, 3]
    from scipy import ndimage
    lab, n = ndimage.label(a > 120); objs = sorted(ndimage.find_objects(lab), key=lambda s: s[1].start)
    print('pips', len(objs))
    # джойстик: основа — левая половина, отражённая (справа на листе к ней прилипла ручка); ручка — только шар, по кругу
    img = load('hud'); cx, cy = 1290, 566
    base = img[cy - 150:cy + 150, cx - 150:cx + 150].copy(); base = mirror_x(base); save(proc(base, hue=CYAN), 'joy_base', w=256)
    kx, ky, kr = 1456, 628, 58; knob = img[ky - kr - 6:ky + kr + 6, kx - kr - 6:kx + kr + 6].copy(); yy, xx = np.mgrid[:knob.shape[0], :knob.shape[1]]
    d = np.hypot(xx - kr - 6, yy - kr - 6); knob[:, :, 3] *= np.clip((kr + 2 - d) / 4, 0, 1); save(proc(knob, hue=CYAN, lo=10), 'joy_knob', w=96)
    # деления уровня: отдельные самоцветы ромбом-маской
    img = load('menu')
    for nm, gx_ in (('pip_on', 437), ('pip_off', 710)):
        g = img[840 - 48:840 + 48, gx_ - 38:gx_ + 38].copy(); yy, xx = np.mgrid[:g.shape[0], :g.shape[1]]
        m = np.abs(xx - 38) / 35 + np.abs(yy - 48) / 45; g[:, :, 3] *= np.clip((1.02 - m) / 0.05, 0, 1); save(proc(g, hue=CYAN, lo=10), nm, w=40)

# 4.9.4: убрать квадратное гнездо со значком у рамок карточек (значок рисует игра; при растягивании гнездо искажалось):
# заплатка из соседнего гладкого участка той же карточки с мягкими краями
def unslot(name, box, src_dx):
    im = np.asarray(Image.open(f'{OUT}/{name}.png').convert('RGBA')).astype(np.float32); x0, y0, x1, y1 = box; pad = 12
    H, W = im.shape[:2]; X0, Y0, X1, Y1 = max(0, x0 - pad), max(0, y0 - pad), min(W, x1 + pad), min(H, y1 + pad)
    patch = im[Y0:Y1, X0 + src_dx:X1 + src_dx].copy(); h, w = patch.shape[:2]
    yy, xx = np.mgrid[:h, :w]; m = np.minimum(np.minimum(xx, w - 1 - xx), np.minimum(yy, h - 1 - yy)) / pad; m = np.clip(m, 0, 1)[:, :, None]
    im[Y0:Y1, X0:X1, :3] = im[Y0:Y1, X0:X1, :3] * (1 - m) + patch[:, :, :3] * m
    Image.fromarray(np.clip(im, 0, 255).astype(np.uint8), 'RGBA').save(f'{OUT}/{name}.png', optimize=True)
if __name__ == '__main__':
    unslot('card', (78, 55, 196, 173), 130); unslot('card_gold', (75, 55, 196, 176), 130); unslot('card_evo', (65, 75, 186, 186), 130)

"""4.5: новые враги из картинок art_src/new45/*_src.png → assets/spr/NAME.png (+ _t1 огненный, _t2 теневой) и meta в manifest.
Размеры как у остальных: холст квадратный, w = 5·h пикселей (h — полуразмер в мире). После — rig.py NAME… нарезает части.
Запуск из game-rs: python3 art_src/tools/newfoes.py
"""
import os, sys, json
import numpy as np
from PIL import Image
HERE = os.path.dirname(os.path.abspath(__file__)); ROOT = os.path.abspath(os.path.join(HERE, '..', '..'))
sys.path.insert(0, HERE); from serpent import hue_shift
SPR = os.path.join(ROOT, 'assets', 'spr'); MAN = os.path.join(ROOT, 'assets', 'manifest.json'); SRC = os.path.join(ROOT, 'art_src', 'new45')
# имя: (h — полуразмер в мире, r — радиус попадания, анимация)
FOES = {'nautilus': (36, 18, 'fin'), 'hermit': (38, 18, 'fin'), 'seahorse': (38, 15, 'fin'), 'cuttle': (36, 16, 'swim'), 'puffer': (31, 17, 'fin')}
T1, T2 = 12, 278   # целевой оттенок: огненный, теневой (градусы)

def dominant_hue(im):
    a = np.asarray(im.convert('RGBA')).astype(np.float32) / 255.; m = a[..., 3] > 0.5; rgb = a[..., :3][m]
    mx = rgb.max(-1); mn = rgb.min(-1); d = mx - mn + 1e-6; r, g, b = rgb.T
    h = np.where(mx == r, ((g - b) / d) % 6, np.where(mx == g, (b - r) / d + 2, (r - g) / d + 4)) * 60.
    w = d * mx; hist, _ = np.histogram(h, bins=36, range=(0, 360), weights=w); return (np.argmax(hist) + 0.5) * 10.

def hue_pull(im, target, keep=0.22, sat=1.15, val=1.0):
    """Стянуть все оттенки к target (градусы), оставив keep от их разброса: пёстрое существо становится огненным/теневым,
    но рисунок и блики сохраняются"""
    a = np.asarray(im).astype(np.float32) / 255.; rgb = a[..., :3]
    mx = rgb.max(-1); mn = rgb.min(-1); d = mx - mn + 1e-6; r, g, b = rgb[..., 0], rgb[..., 1], rgb[..., 2]
    h = np.where(mx == r, ((g - b) / d) % 6, np.where(mx == g, (b - r) / d + 2, (r - g) / d + 4)) * 60.
    s_ = np.where(mx > 0, d / (mx + 1e-6), 0); v = mx
    dh = (h - dominant_hue(im) + 540) % 360 - 180; h = ((target + dh * keep) % 360) / 360.
    s_ = np.clip(s_ * sat, 0, 1); v = np.clip(v * val, 0, 1)
    i = np.floor(h * 6).astype(int) % 6; f = h * 6 - np.floor(h * 6); p_, q_, t_ = v * (1 - s_), v * (1 - s_ * f), v * (1 - s_ * (1 - f))
    out = np.zeros_like(rgb)
    for k, (R, G, B) in enumerate([(v, t_, p_), (q_, v, p_), (p_, v, t_), (p_, q_, v), (t_, p_, v), (v, p_, q_)]):
        m = i == k; out[..., 0][m] = R[m]; out[..., 1][m] = G[m]; out[..., 2][m] = B[m]
    a[..., :3] = out; return Image.fromarray((a * 255).astype(np.uint8))

def main():
    man = json.load(open(MAN))
    for name, (h, r, anim) in FOES.items():
        im = Image.open(os.path.join(SRC, name + '_src.png')).convert('RGBA'); bb = Image.fromarray((np.asarray(im)[..., 3] > 20).astype(np.uint8) * 255).getbbox(); im = im.crop(bb)
        side = int(max(im.size) * 1.06); can = Image.new('RGBA', (side, side), (0, 0, 0, 0)); can.paste(im, ((side - im.size[0]) // 2, (side - im.size[1]) // 2), im)
        w = 5 * h; can = can.resize((w, w), Image.LANCZOS); dh = dominant_hue(can)
        for suf, tgt in (('', None), ('_t1', T1), ('_t2', T2)):
            img = can if tgt is None else hue_pull(can, (tgt - 18) if name == 'nautilus' and suf == '_t1' else tgt, 0.25, 1.2 if suf == '_t1' else 1.05, 0.92 if suf == '_t1' else 0.9)
            img.save(os.path.join(SPR, name + suf + '.png'))
            man['meta'][name + suf] = {'h': h, 'r': r, 'art': True, 'fl': True, 'anim': anim, 'live': False, 'w': w}
        print(name, 'оттенок', round(dh))
    json.dump(man, open(MAN, 'w'), ensure_ascii=False)

if __name__ == '__main__':
    main()

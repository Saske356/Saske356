"""Уменьшает вес картинок без видимой разницы: в прозрачных местах (дальше 3 пикселей от видимых) цвет обнуляется —
PNG тогда сжимается в разы (раньше части существ хранили цвет всей картинки под прозрачностью). Запуск: python3 tools/shrink.py"""
import os, sys, numpy as np
from PIL import Image
from scipy import ndimage as nd
D = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'assets', 'spr')
before = after = 0
for f in sorted(os.listdir(D)):
    if not f.endswith('.png'): continue
    p = os.path.join(D, f); before += os.path.getsize(p)
    im = Image.open(p)
    if im.mode != 'RGBA': im = im.convert('RGBA')
    a = np.asarray(im).copy(); vis = a[..., 3] > 0
    keep = nd.binary_dilation(vis, iterations=3)
    a[~keep] = 0
    Image.fromarray(a).save(p, optimize=True); after += os.path.getsize(p)
print(f'spr: {before / 1e6:.1f} МБ -> {after / 1e6:.1f} МБ')

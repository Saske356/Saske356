"""4.7.2: все искры и облики одного видимого размера.
Картинки из разных партий (3.5 — 161 px, поля 10%; 4.x — 135 px, поля 17%; у части h=27, у части 32) давали на экране
рыбок шириной 35, 42 и 51 — в магазине и в игре облики выглядели разными. Считаем ширину силуэта (тело + все части)
и ставим h так, чтобы видимая ширина была TARGET. Запуск из game-rs/assets: python3 ../art_src/tools/plsize.py"""
import json, numpy as np
from PIL import Image
TARGET = 51.0
man = json.load(open('manifest.json')); m = man['meta']
for k in sorted(x for x in m if x.startswith('pl_') and '__' not in x):
    keys = [k] + [p['k'] for p in m[k].get('parts', [])]
    A = None
    for kk in keys:
        a = np.asarray(Image.open(f'spr/{kk}.png').convert('RGBA'))[:, :, 3] > 40
        A = a if A is None else (A | a)
    xs = np.nonzero(A.any(0))[0]; bw = (xs[-1] - xs[0] + 1) / A.shape[1]
    h = round(TARGET / (2 * bw), 2)
    for kk in keys: m[kk]['h'] = h
    print(f'{k:14s} bw={bw:.3f} h={h}')
json.dump(man, open('manifest.json', 'w'), ensure_ascii=False)

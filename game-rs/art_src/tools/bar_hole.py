"""4.9.11: прозрачное «окно» в рамках полосок (bar_hp, bar_boss, bar_xp) — заливка видна сквозь рамку.
Заливка от центра по тёмным пикселям → альфа 0, край окна сглажен. Запуск из game-rs после ui49.py/ui_kid.py."""
import numpy as np
from PIL import Image, ImageFilter
from collections import deque
for n in ['bar_hp', 'bar_boss', 'bar_xp']:
    p = f'assets/ui/{n}.png'; im = Image.open(p).convert('RGBA'); a = np.array(im); h, w = a.shape[:2]
    dark = (a[..., :3].max(axis=2) < 135) & (a[..., 3] > 0)
    m = np.zeros((h, w), bool); q = deque([(h // 2, w // 2)]); m[h // 2, w // 2] = True
    if not dark[h // 2, w // 2]: print(n, 'центр не тёмный — пропуск'); continue
    while q:
        y, x = q.popleft()
        for dy, dx in ((1, 0), (-1, 0), (0, 1), (0, -1)):
            yy, xx = y + dy, x + dx
            if 0 <= yy < h and 0 <= xx < w and not m[yy, xx] and dark[yy, xx]: m[yy, xx] = True; q.append((yy, xx))
    soft = np.array(Image.fromarray((m * 255).astype(np.uint8)).filter(ImageFilter.GaussianBlur(1.2))) / 255.
    a[..., 3] = (a[..., 3] * (1 - soft)).astype(np.uint8)
    Image.fromarray(a).save(p); print(n, 'окно', int(m.sum()), 'пикс из', h * w)

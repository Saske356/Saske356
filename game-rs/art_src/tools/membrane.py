"""3.7: мягкое уплотнение «стеклянных» обликов Люмена: прожилки ярче, между ними — полупрозрачная перепонка (альфа 0.42)
цвета соседних пикселей. Без сплошной заливки (её пользователь отклонил). Запуск из assets/spr: python3 membrane.py pl_azure …"""
import sys, numpy as np
from PIL import Image
from scipy import ndimage as nd
def g(x, s): return nd.gaussian_filter(x, s)
for f in sys.argv[1:]:
    im = np.asarray(Image.open(f + '.png').convert('RGBA')).astype(np.float32) / 255
    a = im[..., 3]; rgb = im[..., :3]; n = a.shape[0]
    na = 1 - (1 - a) ** 2.3; gain = np.clip((na / np.maximum(a, 0.08)) ** 0.45, 1, 1.9)[..., None]; top = np.clip(rgb * gain, 0, 1)
    m = nd.binary_fill_holes(nd.binary_closing(a > 0.12, iterations=max(2, n // 60))); mf = g(m.astype(np.float32), 1.0)
    s = n / 40; w = g(a, s) + 1e-4; col = np.stack([g(rgb[..., c] * a, s) / w for c in range(3)], -1)
    col = np.clip(col * 1.25 + 0.04, 0, 1); ma = mf * 0.42
    oa = na + ma * (1 - na); orgb = (top * na[..., None] + col * (ma * (1 - na))[..., None]) / np.maximum(oa, 1e-4)[..., None]
    Image.fromarray((np.dstack([np.clip(orgb, 0, 1), oa]) * 255).astype(np.uint8)).save(f + '.png')

"""Фоны v2: каждая локация из листа 5×3 → квадрат → ×4 нейросетью (Real-ESRGAN) → 1024×1024 → бесшовная плитка."""
import sys, numpy as np
from PIL import Image, ImageEnhance
sys.path.insert(0, '/home/user/game/game-rs/art_src/tools'); import upscale
upscale.load('/tmp/esr/x4.pth')
src = Image.open('in/bg_sheet.png').convert('RGB'); W, H = src.size; cw, ch = W / 5, H / 3; m = 5
zs = [int(a) for a in sys.argv[1:]] or range(15)
for z in zs:
    cx, cy = z % 5, z // 5
    cell = src.crop((round(cx * cw) + m, round(cy * ch) + m, round((cx + 1) * cw) - m, round((cy + 1) * ch) - m))
    s = min(cell.width, cell.height); y0 = (cell.height - s) // 2; cell = cell.crop((0, y0, s, y0 + s))
    big = upscale.up(cell).resize((1024, 1024), Image.LANCZOS)
    t = np.asarray(big).astype(np.float32); n = 1024
    # бесшовность в два шага: сдвинутая копия используется только у «своих» краёв, а её собственный шов
    # (посередине) всегда закрыт оригиналом — внутри плитки швов нет
    ramp = lambda d: (lambda q: q * q * (3 - 2 * q))(np.clip(d / (n * 0.28), 0, 1))
    i = np.arange(n, dtype=np.float32); w1 = ramp(np.minimum(i, n - 1 - i))
    h = t * w1[None, :, None] + np.roll(t, n // 2, 1) * (1 - w1[None, :, None])
    t2 = h * w1[:, None, None] + np.roll(h, n // 2, 0) * (1 - w1[:, None, None])
    out = Image.fromarray(np.clip(t2, 0, 255).astype(np.uint8))
    out = ImageEnhance.Brightness(ImageEnhance.Color(out).enhance(0.9)).enhance(0.82)
    out.save(f'/home/user/game/game-rs/assets/ground/g{z}.png'); print('zone', z, flush=True)

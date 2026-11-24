"""Нарезает лист фонов 5×3 и делает каждую плитку бесшовной (смешивание со сдвигом на полплитки)."""
import numpy as np
from PIL import Image, ImageEnhance
src = Image.open('in/bg_sheet.png').convert('RGB'); W, H = src.size; cw, ch = W / 5, H / 3; m = 5
for z in range(15):
    cx, cy = z % 5, z // 5
    cell = src.crop((round(cx * cw) + m, round(cy * ch) + m, round((cx + 1) * cw) - m, round((cy + 1) * ch) - m))
    # GLES2 повторяет только текстуры со сторонами 2^n: обрезаем до 1:2 и делаем 512×1024
    cw2 = cell.height // 2; x0 = (cell.width - cw2) // 2; cell = cell.crop((x0, 0, x0 + cw2, cell.height))
    tw, th = 512, 1024
    t = np.asarray(cell.resize((tw, th), Image.LANCZOS)).astype(np.float32)
    r = np.roll(np.roll(t, th // 2, 0), tw // 2, 1)
    yy, xx = np.mgrid[0:th, 0:tw].astype(np.float32)
    # вес оригинала: 1 в середине, 0 у краёв (там берём сдвинутую копию — её края непрерывны)
    wx = np.clip(np.minimum(xx, tw - 1 - xx) / (tw * 0.22), 0, 1); wy = np.clip(np.minimum(yy, th - 1 - yy) / (th * 0.22), 0, 1)
    w = (wx * wy)[..., None]; w = w * w * (3 - 2 * w)
    out = Image.fromarray(np.clip(t * w + r * (1 - w), 0, 255).astype(np.uint8))
    out = ImageEnhance.Brightness(ImageEnhance.Color(out).enhance(0.88)).enhance(0.8)
    out.save(f'/home/user/game/game-rs/assets/ground/g{z}.png')
print(tw, th)

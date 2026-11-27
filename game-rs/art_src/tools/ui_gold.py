"""4.9.5: интерфейс «чёрное с золотом» — рисуется программно (поля расстояний, сглаживание ×3), без нейросетей.
Перезаписывает кнопки, вкладки, рамки карточек и окон, кнопки забега в assets/ui. Запуск из game-rs:
python3 art_src/tools/ui_gold.py"""
import numpy as np
from PIL import Image
OUT = 'assets/ui'; SS = 3  # сверхвыборка

def C(h): return np.array([(h >> 16) & 255, (h >> 8) & 255, h & 255], np.float32)
GOLD_D, GOLD_M, GOLD_L, GOLD_W = C(0x5a3c0e), C(0xb8862c), C(0xf3d27a), C(0xfff4cc)
BLACK_T, BLACK_B = C(0x1c1710), C(0x050505)

def grid(W, H): y, x = np.mgrid[0:H * SS, 0:W * SS].astype(np.float32); return (x + 0.5) / SS, (y + 0.5) / SS
def sd_rrect(x, y, x0, y0, x1, y1, r):
    cx, cy, hx, hy = (x0 + x1) / 2, (y0 + y1) / 2, (x1 - x0) / 2 - r, (y1 - y0) / 2 - r
    qx, qy = np.abs(x - cx) - hx, np.abs(y - cy) - hy
    return np.hypot(np.maximum(qx, 0), np.maximum(qy, 0)) + np.minimum(np.maximum(qx, qy), 0) - r
def sd_circle(x, y, cx, cy, r): return np.hypot(x - cx, y - cy) - r
def sd_seg(x, y, ax, ay, bx, by):
    px, py, dx, dy = x - ax, y - ay, bx - ax, by - ay; h = np.clip((px * dx + py * dy) / (dx * dx + dy * dy), 0, 1); return np.hypot(px - dx * h, py - dy * h)
def cov(d, w=0.9): return np.clip(0.5 - d / w, 0, 1)  # покрытие по расстоянию (сглаживание края)
def mix(a, b, t): t = t[..., None]; return a * (1 - t) + b * t

def gold(x, y, H, d=None, k=1.):
    """металлическое золото: вертикальный перелив + отблеск, светлее сверху"""
    t = (y / H); band = 0.5 + 0.5 * np.cos((t * 2.6 + 0.15) * np.pi * 2)
    c = mix(GOLD_D, GOLD_M, np.clip(1.2 - t * 1.1, 0, 1)); c = mix(c, GOLD_L, band * 0.65 * k); c = mix(c, GOLD_W, np.clip(band - 0.82, 0, 1) * 2.5 * k)
    return c

class Canvas:
    def __init__(s, W, H): s.W, s.H = W, H; s.x, s.y = grid(W, H); s.rgb = np.zeros((H * SS, W * SS, 3), np.float32); s.a = np.zeros((H * SS, W * SS), np.float32)
    def put(s, col, alpha):
        alpha = np.clip(alpha, 0, 1); s.rgb = s.rgb * (1 - alpha[..., None]) + col * alpha[..., None]; s.a = s.a + alpha * (1 - s.a)
        # rgb хранится как «поверх чёрного», в конце делим на альфу
    def save(s, name):
        a = np.clip(s.a, 1e-4, 1); rgb = np.clip(s.rgb / a[..., None], 0, 255)
        img = np.dstack([rgb, s.a * 255]).astype(np.float32)
        im = Image.fromarray(img.clip(0, 255).astype(np.uint8), 'RGBA').resize((s.W, s.H), Image.LANCZOS); im.save(f'{OUT}/{name}.png', optimize=True)

def noise(sh, seed=1, sc=1.):
    r = np.random.default_rng(seed); n = r.normal(0, 1, (sh[0] // 6 + 2, sh[1] // 6 + 2)).astype(np.float32)
    im = Image.fromarray(((n - n.min()) / (np.ptp(n) + 1e-6) * 255).astype(np.uint8)).resize((sh[1], sh[0]), Image.BICUBIC)
    return (np.asarray(im).astype(np.float32) / 255 - 0.5) * sc

def panel(cv, x0, y0, x1, y1, r, rim, body='black', glow=0., accent=None, corners=False, stripe=False):
    x, y, H = cv.x, cv.y, cv.H; d = sd_rrect(x, y, x0, y0, x1, y1, r)
    # мягкая тень наружу
    cv.put(np.zeros(3), np.clip(1 - np.maximum(d, 0) / 7, 0, 1) * (d > 0) * 0.45)
    if glow > 0: cv.put(GOLD_L, np.clip(1 - np.maximum(d, 0) / 10, 0, 1) * (d > 0) * glow)
    # золотая рамка
    cv.put(gold(x, y - y0, y1 - y0), cov(d))
    # тело
    di = d + rim; n = noise(x.shape, 3, 10.)
    if body == 'black':
        t = np.clip((y - y0) / (y1 - y0), 0, 1); col = mix(BLACK_T, BLACK_B, t) + n[..., None] * 0.6
        warm = np.clip(1 - np.hypot((x - (x0 + x1) / 2) / ((x1 - x0) * 0.6), (y - y0) / ((y1 - y0) * 0.9)), 0, 1) ** 2
        col = col + C(0x3a2a10) * warm[..., None] * 0.55
        if accent is not None: col = col + accent * (np.clip(1 - (y - y0) / ((y1 - y0) * 0.9), 0, 1) ** 3)[..., None] * 0.10
    else:  # золотое тело (главная награда)
        col = gold(x, y - y0, y1 - y0, k=0.8) * 0.92 + n[..., None] * 0.8
    cv.put(col, cov(di))
    # внутренний тёмный зазор и тонкая золотая нить
    cv.put(C(0x0a0805), cov(np.abs(di) - 0.6) * 0.8)
    if body == 'black': cv.put(gold(x, y - y0, y1 - y0, k=0.6) * 0.95, cov(np.abs(di + 2.6) - 0.45) * 0.7)
    # блик сверху
    hl = np.clip(1 - (y - y0) / ((y1 - y0) * 0.5), 0, 1) ** 2 * cov(di + 1)
    cv.put(np.array([255, 245, 220], np.float32), hl * (0.06 if body == 'black' else 0.22))
    if stripe:  # золотая полоска слева (карточки)
        ds = sd_rrect(x, y, x0 + rim + 7, y0 + (y1 - y0) * 0.18, x0 + rim + 11, y1 - (y1 - y0) * 0.18, 2)
        cv.put(gold(x, y - y0, y1 - y0, k=1.2), cov(ds)); cv.put(GOLD_L, np.clip(1 - np.maximum(ds, 0) / 6, 0, 1) * (ds > 0) * 0.35)
    if corners:  # угловые украшения: ромбик-самоцвет с золотыми усиками
        for (cx, cy, sx, sy) in ((x0 + r * 0.6, y0 + r * 0.6, 1, 1), (x1 - r * 0.6, y0 + r * 0.6, -1, 1), (x0 + r * 0.6, y1 - r * 0.6, 1, -1), (x1 - r * 0.6, y1 - r * 0.6, -1, -1)):
            dd = np.abs(x - cx) + np.abs(y - cy) - 6.5; cv.put(gold(x, y - (cy - 7), 14, k=1.3), cov(dd)); cv.put(C(0x120c04), cov(np.abs(x - cx) + np.abs(y - cy) - 2.8))
            for k in (1, 2):
                ds = sd_seg(x, y, cx + sx * (7 + k * 2), cy, cx + sx * (24 + k * 10), cy); cv.put(gold(x, y - y0, y1 - y0) * (1.05 - 0.15 * k), cov(ds - 0.7) * (k == 1))
                ds = sd_seg(x, y, cx, cy + sy * (7 + k * 2), cx, cy + sy * (24 + k * 10)); cv.put(gold(x, y - y0, y1 - y0) * (1.05 - 0.15 * k), cov(ds - 0.7) * (k == 1))

def gem(cv, cx, cy, s, col):
    x, y = cv.x, cv.y; d = np.abs(x - cx) / s + np.abs(y - cy) / (s * 1.25) - 1
    cv.put(gold(x, y - (cy - s), s * 2.5, k=1.2), cov(d * s - 0.5)); dd = np.abs(x - cx) / (s * 0.66) + np.abs(y - cy) / (s * 0.83) - 1
    t = np.clip((y - (cy - s)) / (2 * s), 0, 1); cv.put(mix(col * 1.25, col * 0.45, t), cov(dd * s * 0.66 - 0.4))
    cv.put(np.array([255, 255, 255], np.float32), cov(np.hypot(x - cx + s * 0.18, y - cy + s * 0.35) - s * 0.16) * 0.8)

# ---------- кнопки меню (9 частей: края 0.12/0.45) ----------
def button(name, body='black', accent=None, glow=0., dark=1.):
    cv = Canvas(360, 120); panel(cv, 8, 8, 352, 112, 26, 5, body=body, accent=accent, glow=glow)
    if dark < 1: cv.rgb *= dark
    cv.save(name)
button('btn_blue', accent=C(0xffd27a), glow=0.18)
button('btn_gold', body='gold', glow=0.3)
button('btn_pink', accent=C(0xc070ff), glow=0.1)
button('btn_teal', dark=0.72)
button('btn_press', accent=C(0xffd27a), dark=0.75)
# вкладки
cv = Canvas(300, 110); panel(cv, 8, 8, 292, 102, 22, 4); cv.rgb *= 0.62; cv.save('tab_off')
cv = Canvas(300, 110); panel(cv, 8, 8, 292, 102, 22, 4, accent=C(0xffd27a), glow=0.35); cv.save('tab_on')
# карточки (рамка с золотой полоской слева и уголками)
cv = Canvas(420, 220); panel(cv, 10, 10, 410, 210, 22, 5, stripe=True, corners=True); cv.save('card')
cv = Canvas(420, 220); panel(cv, 10, 10, 410, 210, 22, 7, stripe=True, corners=True, accent=C(0xffd27a), glow=0.45); cv.save('card_gold')
cv = Canvas(420, 240); panel(cv, 10, 20, 410, 220, 22, 7, stripe=True, corners=True, accent=C(0xc070ff), glow=0.4); gem(cv, 210, 21, 13, C(0xb45cff)); gem(cv, 210, 219, 13, C(0xb45cff)); cv.save('card_evo')
cv = Canvas(420, 220); panel(cv, 10, 10, 410, 210, 22, 5, stripe=True); cv.rgb *= 0.55; cv.save('card_lock')
# окно
cv = Canvas(480, 330); panel(cv, 14, 24, 466, 316, 30, 7, corners=True, accent=C(0xffd27a), glow=0.25); gem(cv, 240, 25, 15, C(0xffc94a)); gem(cv, 240, 315, 12, C(0xffc94a)); cv.save('modal')

# ---------- кнопки забега ----------
def roundbtn(name, glyph, R=118, dim=1.):
    cv = Canvas(256, 256); x, y = cv.x, cv.y; cx = cy = 128; d = sd_circle(x, y, cx, cy, R)
    cv.put(np.zeros(3), np.clip(1 - np.maximum(d, 0) / 8, 0, 1) * (d > 0) * 0.5)
    cv.put(gold(x, y - (cy - R), 2 * R), cov(d)); di = d + 9; n = noise(x.shape, 5, 9.)
    t = np.clip((y - (cy - R)) / (2 * R), 0, 1); body = mix(BLACK_T, BLACK_B, t) + n[..., None] * 0.6
    body = body + C(0x3a2a10) * (np.clip(1 - np.hypot(x - cx, y - (cy - R * 0.35)) / (R * 0.9), 0, 1) ** 2)[..., None] * 0.7
    cv.put(body, cov(di)); cv.put(C(0x0a0805), cov(np.abs(di) - 0.8) * 0.9); cv.put(gold(x, y - (cy - R), 2 * R, k=0.6), cov(np.abs(di + 5) - 0.7) * 0.75)
    cv.put(np.array([255, 245, 220], np.float32), (np.clip(1 - (y - (cy - R)) / R, 0, 1) ** 2) * cov(di + 2) * 0.07)
    glyph(cv, cx, cy); cv.rgb *= dim; cv.save(name)

def g_dash(cv, cx, cy):
    for ox in (-24, 14):
        for (ax, ay, bx, by) in ((cx + ox - 16, cy - 30, cx + ox + 12, cy), (cx + ox + 12, cy, cx + ox - 16, cy + 30)):
            d = sd_seg(cv.x, cv.y, ax, ay, bx, by); cv.put(gold(cv.x, cv.y - (cy - 34), 68, k=1.3), cov(d - 8))
def g_pause(cv, cx, cy):
    for ox in (-20, 20): d = sd_rrect(cv.x, cv.y, cx + ox - 9, cy - 34, cx + ox + 9, cy + 34, 5); cv.put(gold(cv.x, cv.y - (cy - 34), 68, k=1.3), cov(d))
def g_snd(on):
    def f(cv, cx, cy):
        x, y = cv.x, cv.y; G = gold(x, y - (cy - 40), 80, k=1.3)
        cv.put(G, cov(sd_rrect(x, y, cx - 42, cy - 14, cx - 22, cy + 14, 3)))
        tri = np.maximum(np.maximum(x - (cx + 6), (cx - 26) - x), np.abs(y - cy) - (12 + (x - (cx - 26)) * 0.95)); cv.put(G, cov(tri))
        if on:
            for rr in (22, 40):
                a = np.arctan2(y - cy, x - (cx + 6)); d = np.abs(np.hypot(x - (cx + 6), y - cy) - rr) - 4.5; d = np.where(np.abs(a) < 0.85, d, 99); cv.put(G, cov(d))
        else:
            cv.put(C(0xff6f6f), cov(sd_seg(x, y, cx + 18, cy - 18, cx + 46, cy + 18) - 5)); cv.put(C(0xff6f6f), cov(sd_seg(x, y, cx + 46, cy - 18, cx + 18, cy + 18) - 5))
    return f
def g_none(cv, cx, cy): pass
roundbtn('dash', g_dash); roundbtn('dash_cd', g_dash, dim=0.5)

def squarebtn(name, glyph):
    cv = Canvas(160, 160); panel(cv, 8, 8, 152, 152, 30, 5, accent=C(0xffd27a)); glyph(cv, 80, 80); cv.save(name)
def g_pause_s(cv, cx, cy):
    for ox in (-14, 14): d = sd_rrect(cv.x, cv.y, cx + ox - 7, cy - 26, cx + ox + 7, cy + 26, 4); cv.put(gold(cv.x, cv.y - (cy - 26), 52, k=1.3), cov(d))
def g_snd_s(on):
    def f(cv, cx, cy):
        x, y = cv.x, cv.y; G = gold(x, y - (cy - 30), 60, k=1.3); cx = cx - 6
        cv.put(G, cov(sd_rrect(x, y, cx - 26, cy - 10, cx - 12, cy + 10, 2)))
        tri = np.maximum(np.maximum(x - (cx + 4), (cx - 16) - x), np.abs(y - cy) - (9 + (x - (cx - 16)) * 0.95)); cv.put(G, cov(tri))
        if on:
            for rr in (15, 27):
                a = np.arctan2(y - cy, x - (cx + 4)); d = np.abs(np.hypot(x - (cx + 4), y - cy) - rr) - 3.5; d = np.where(np.abs(a) < 0.85, d, 99); cv.put(G, cov(d))
        else:
            cv.put(C(0xff7070), cov(sd_seg(x, y, cx + 12, cy - 12, cx + 32, cy + 12) - 4)); cv.put(C(0xff7070), cov(sd_seg(x, y, cx + 32, cy - 12, cx + 12, cy + 12) - 4))
    return f
squarebtn('pause', g_pause_s); squarebtn('snd_on', g_snd_s(True)); squarebtn('snd_off', g_snd_s(False))

# джойстик: тёмное кольцо с золотой кромкой; ручка — чёрный шар с золотым ободком
cv = Canvas(256, 256); x, y = cv.x, cv.y; d = sd_circle(x, y, 128, 128, 120); cv.put(gold(x, y - 8, 240), cov(np.abs(d) - 3)); cv.put(C(0x0b0906), cov(d + 4) * 0.55)
cv.put(gold(x, y - 8, 240, k=0.5), cov(np.abs(d + 26) - 1.2) * 0.6); cv.save('joy_base')
cv = Canvas(96, 96); x, y = cv.x, cv.y; d = sd_circle(x, y, 48, 48, 40); cv.put(gold(x, y - 8, 80, k=1.2), cov(d)); t = np.clip((y - 8) / 80, 0, 1)
cv.put(mix(C(0x2a2216), C(0x050505), t), cov(d + 6)); cv.put(np.array([255, 240, 200], np.float32), cov(np.hypot(x - 38, y - 34) - 9) * 0.25); cv.save('joy_knob')

# полоски: тонкие золотые рамки с ромбом посередине
def bar(name, W, H, gemcol):
    cv = Canvas(W, H); x, y = cv.x, cv.y; d = sd_rrect(x, y, 10, H * 0.28, W - 10, H * 0.72, H * 0.22)
    cv.put(np.zeros(3), np.clip(1 - np.maximum(d, 0) / 6, 0, 1) * (d > 0) * 0.4); cv.put(gold(x, y - H * 0.28, H * 0.44), cov(np.abs(d) - 2.2))
    for sx in (1, -1):
        cx = W / 2 + sx * 0; pass
    gem(cv, W / 2, H * 0.28, H * 0.16, gemcol); cv.save(name)
bar('bar_hp', 420, 110, C(0xff5f7a)); bar('bar_xp', 420, 90, C(0x5fe9ff)); bar('bar_boss', 520, 120, C(0xd06bff))
cv = Canvas(240, 90); panel(cv, 8, 14, 232, 76, 30, 3, accent=C(0xffd27a)); cv.save('pill')
cv = Canvas(300, 100); panel(cv, 8, 10, 292, 90, 40, 4); cv.save('price')
# деления: золотой ромб (горит) / тёмный
cv = Canvas(40, 48); gem(cv, 20, 24, 16, C(0xffd34a)); cv.save('pip_on')
cv = Canvas(40, 48); gem(cv, 20, 24, 16, C(0x2a2418)); cv.save('pip_off')
print('ok')

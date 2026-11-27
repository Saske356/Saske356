"""4.9.6: детский «мармеладный» интерфейс — рисуется программно (поля расстояний, сглаживание ×3), без нейросетей.
Перезаписывает кнопки, вкладки, рамки карточек и окон, кнопки забега в assets/ui. Запуск из game-rs:
python3 art_src/tools/ui_kid.py"""
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


class Canvas:
    def __init__(s, W, H): s.W, s.H = W, H; s.x, s.y = grid(W, H); s.rgb = np.zeros((H * SS, W * SS, 3), np.float32); s.a = np.zeros((H * SS, W * SS), np.float32)
    def put(s, col, alpha):
        alpha = np.clip(alpha, 0, 1); col = np.broadcast_to(col, s.rgb.shape) if np.ndim(col) == 1 else col
        s.rgb = s.rgb * (1 - alpha[..., None]) + col * alpha[..., None]; s.a = s.a + alpha * (1 - s.a)
    def save(s, name):
        a = np.clip(s.a, 1e-4, 1); rgb = np.clip(s.rgb / a[..., None], 0, 255)
        im = Image.fromarray(np.dstack([rgb, s.a * 255]).clip(0, 255).astype(np.uint8), 'RGBA').resize((s.W, s.H), Image.LANCZOS); im.save(f'{OUT}/{name}.png', optimize=True)

def vgrad(y, y0, y1, top, bot): t = np.clip((y - y0) / max(1e-3, y1 - y0), 0, 1); return mix(top, bot, t)
WHITE = C(0xffffff); INK = C(0x0d2a4a)
# цвета кнопок: (верх, низ, «подошва», кайма)
STY = {'aqua': (C(0x6fe3f2), C(0x2aa3d6), C(0x1673a6), C(0xd9fbff)), 'sun': (C(0xffe27a), C(0xf7b43a), C(0xc9781c), C(0xfff6d2)),
       'coral': (C(0xffa3b8), C(0xf0668a), C(0xb83e63), C(0xffe3ea)), 'slate': (C(0x8fa9c4), C(0x5f7d9c), C(0x3e5873), C(0xe4eef8))}

def candy(cv, x0, y0, x1, y1, r, sty, pressed=False, lip=7):
    """мармеладная кнопка: тень, «подошва» снизу, тело с градиентом, блик сверху, светлая кайма"""
    top, bot, base, rim = STY[sty]; x, y = cv.x, cv.y; L = 0 if pressed else lip
    ds = sd_rrect(x, y, x0, y0 + 4, x1, y1 + 4, r); cv.put(INK, np.clip(1 - np.maximum(ds, 0) / 6, 0, 1) * (ds > -50) * 0.35)
    d_base = sd_rrect(x, y, x0, y0 + (lip if pressed else 0) + 2, x1, y1, r); cv.put(base, cov(d_base))
    yb1 = y1 - L; d_body = sd_rrect(x, y, x0, y0 + (lip if pressed else 0), x1, yb1, r)
    cv.put(vgrad(y, y0, yb1, top, bot), cov(d_body))
    cv.put(rim, cov(np.abs(d_body + 2.2) - 1.3) * 0.75)
    hy0 = y0 + (lip if pressed else 0) + 5; d_hl = sd_rrect(x, y, x0 + r * 0.45, hy0, x1 - r * 0.45, hy0 + (yb1 - hy0) * 0.42, r * 0.55)
    cv.put(WHITE, cov(d_hl) * np.clip(1 - (y - hy0) / ((yb1 - hy0) * 0.42), 0, 1) * 0.38)
    cv.put(INK, cov(np.abs(d_base) - 1.1) * 0.55)

def bubbles(cv, x0, y0, x1, y1, n, seed=7, alpha=0.18):
    r = np.random.default_rng(seed)
    for _ in range(n):
        bx, by, br = r.uniform(x0, x1), r.uniform(y0, y1), r.uniform(3, 8); d = sd_circle(cv.x, cv.y, bx, by, br)
        cv.put(C(0xbff3ff), cov(np.abs(d) - 0.9) * alpha); cv.put(WHITE, cov(sd_circle(cv.x, cv.y, bx - br * 0.35, by - br * 0.35, br * 0.25)) * alpha * 1.3)

def card(cv, x0, y0, x1, y1, r, border, glow=0., stripe=True, deco=True, dim=1.):
    x, y = cv.x, cv.y; d = sd_rrect(x, y, x0, y0, x1, y1, r)
    cv.put(INK, np.clip(1 - np.maximum(d - 2, 0) / 7, 0, 1) * (d > 0) * 0.4)
    if glow: cv.put(border, np.clip(1 - np.maximum(d, 0) / 9, 0, 1) * (d > 0) * glow)
    cv.put(vgrad(y, y0, y1, C(0x24507f) * dim, C(0x142f55) * dim), cov(d))
    cv.put(WHITE, (np.clip(1 - (y - y0) / ((y1 - y0) * 0.45), 0, 1) ** 2) * cov(d + 3) * 0.08)
    cv.put(border, cov(np.abs(d + 2.5) - 2.2)); cv.put(WHITE, cov(np.abs(d + 5.5) - 0.6) * 0.18)
    if stripe: ds = sd_rrect(x, y, x0 + 9, y0 + (y1 - y0) * 0.2, x0 + 14, y1 - (y1 - y0) * 0.2, 2.5); cv.put(border, cov(ds))
    if deco: bubbles(cv, x1 - (x1 - x0) * 0.32, y0 + 14, x1 - 14, y1 - 14, 7)

def save_candy(name, sty, W=360, H=126, r=34, pressed=False):
    cv = Canvas(W, H); candy(cv, 8, 8, W - 8, H - 10, r, sty, pressed); cv.save(name)

if __name__ == '__main__':
    save_candy('btn_blue', 'aqua'); save_candy('btn_gold', 'sun'); save_candy('btn_pink', 'coral'); save_candy('btn_teal', 'slate'); save_candy('btn_press', 'aqua', pressed=True)
    save_candy('tab_on', 'aqua', 300, 110, 28); cv = Canvas(300, 110); candy(cv, 8, 8, 292, 100, 28, 'slate'); cv.rgb *= 0.8; cv.save('tab_off')
    cv = Canvas(420, 220); card(cv, 10, 10, 410, 210, 26, C(0x7fdcff)); cv.save('card')
    cv = Canvas(420, 220); card(cv, 10, 10, 410, 210, 26, C(0xffcf5a), glow=0.35); cv.save('card_gold')
    cv = Canvas(420, 220); card(cv, 10, 10, 410, 210, 26, C(0xd59bff), glow=0.4); cv.save('card_evo')
    cv = Canvas(420, 220); card(cv, 10, 10, 410, 210, 26, C(0x8ca3bb), dim=0.75, deco=False); cv.save('card_lock')
    cv = Canvas(480, 330); card(cv, 14, 14, 466, 316, 34, C(0x8fe6ff), glow=0.25, stripe=False); bubbles(cv, 30, 30, 140, 300, 6, seed=3); cv.save('modal')
    cv = Canvas(240, 90); card(cv, 8, 12, 232, 78, 30, C(0xffcf5a), stripe=False, deco=False); cv.save('pill')
    cv = Canvas(300, 100); card(cv, 8, 10, 292, 90, 38, C(0x7fdcff), stripe=False, deco=False); cv.save('price')
    # круглые кнопки забега
    def round_candy(name, sty, glyph, dim=1.):
        cv = Canvas(256, 256); x, y = cv.x, cv.y; top, bot, base, rim = STY[sty]; R = 112
        ds = sd_circle(x, y, 128, 134, R); cv.put(INK, np.clip(1 - np.maximum(ds, 0) / 8, 0, 1) * (ds > -200) * 0.35)
        cv.put(base, cov(sd_circle(x, y, 128, 134, R))); d = sd_circle(x, y, 128, 124, R); cv.put(vgrad(y, 12, 236, top, bot), cov(d))
        cv.put(rim, cov(np.abs(d + 3) - 2) * 0.8); cv.put(WHITE, cov(sd_circle(x, y, 128, 80, R * 0.62)) * np.clip(1 - (y - 22) / 110, 0, 1) * 0.35)
        glyph(cv, 128, 124); cv.rgb *= dim; cv.save(name)
    def chevrons(cv, cx, cy):
        for ox in (-26, 14):
            for (ax, ay, bx, by) in ((cx + ox - 16, cy - 30, cx + ox + 12, cy), (cx + ox + 12, cy, cx + ox - 16, cy + 30)):
                d = sd_seg(cv.x, cv.y, ax, ay, bx, by); cv.put(C(0x1673a6), cov(d - 13) * 0.35); cv.put(WHITE, cov(d - 10))
    round_candy('dash', 'aqua', chevrons); round_candy('dash_cd', 'slate', chevrons, dim=0.8)
    def sq(name, glyph):
        cv = Canvas(160, 160); candy(cv, 8, 8, 152, 150, 34, 'aqua', lip=6); glyph(cv, 80, 74); cv.save(name)
    def g_pause(cv, cx, cy):
        for ox in (-14, 14): cv.put(WHITE, cov(sd_rrect(cv.x, cv.y, cx + ox - 8, cy - 25, cx + ox + 8, cy + 25, 5)))
    def g_snd(on):
        def f(cv, cx, cy):
            x, y = cv.x, cv.y; cx = cx - 8; cv.put(WHITE, cov(sd_rrect(x, y, cx - 26, cy - 10, cx - 12, cy + 10, 3)))
            tri = np.maximum(np.maximum(x - (cx + 4), (cx - 16) - x), np.abs(y - cy) - (9 + (x - (cx - 16)) * 0.95)); cv.put(WHITE, cov(tri))
            if on:
                for rr in (15, 27):
                    a = np.arctan2(y - cy, x - (cx + 4)); d = np.abs(np.hypot(x - (cx + 4), y - cy) - rr) - 4; d = np.where(np.abs(a) < 0.85, d, 99); cv.put(WHITE, cov(d))
            else:
                for s_ in (1, -1): cv.put(C(0xff5f7f), cov(sd_seg(x, y, cx + 12, cy - 12 * s_, cx + 32, cy + 12 * s_) - 5))
        return f
    sq('pause', g_pause); sq('snd_on', g_snd(True)); sq('snd_off', g_snd(False))
    cv = Canvas(256, 256); x, y = cv.x, cv.y; d = sd_circle(x, y, 128, 128, 118); cv.put(C(0x0d2a4a), cov(d) * 0.25); cv.put(WHITE, cov(np.abs(d + 2) - 3) * 0.7); cv.save('joy_base')
    cv = Canvas(96, 96); x, y = cv.x, cv.y; cv.put(C(0x1673a6), cov(sd_circle(x, y, 48, 52, 40))); cv.put(vgrad(y, 8, 88, C(0xe8fdff), C(0x8fe3f5)), cov(sd_circle(x, y, 48, 46, 40))); cv.put(WHITE, cov(sd_circle(x, y, 38, 32, 12)) * 0.7); cv.save('joy_knob')
    def bar(name, W, H, col):
        cv = Canvas(W, H); x, y = cv.x, cv.y; d = sd_rrect(x, y, 8, H * 0.24, W - 8, H * 0.76, H * 0.26)
        cv.put(INK, np.clip(1 - np.maximum(d, 0) / 5, 0, 1) * (d > 0) * 0.35); cv.put(WHITE, cov(np.abs(d) - 2.6) * 0.95); cv.put(col, cov(np.abs(d + 4) - 1) * 0.6); cv.save(name)
    bar('bar_hp', 420, 100, C(0xff7f9a)); bar('bar_xp', 420, 90, C(0x7fe3ff)); bar('bar_boss', 520, 110, C(0xd59bff))
    for nm, col in (('pip_on', C(0x6fe3f2)), ('pip_off', C(0x3a5677))):
        cv = Canvas(40, 40); x, y = cv.x, cv.y; cv.put(INK, cov(sd_circle(x, y, 20, 22, 15)) * 0.5); cv.put(col, cov(sd_circle(x, y, 20, 20, 14))); cv.put(WHITE, cov(np.abs(sd_circle(x, y, 20, 20, 14)) - 1.4) * 0.8)
        cv.put(WHITE, cov(sd_circle(x, y, 15, 15, 4)) * (0.8 if nm == 'pip_on' else 0.25)); cv.save(nm)
    # оправа суперспособности: мягкое солнечное кольцо (заряжено — со звёздочками)
    def ring(name, stars):
        cv = Canvas(300, 300); x, y = cv.x, cv.y; d = sd_circle(x, y, 150, 150, 122)
        if stars: cv.put(C(0xffe27a), np.clip(1 - np.abs(d) / 26, 0, 1) ** 2 * 0.55)
        cv.put(C(0xc9781c), cov(np.abs(d - 2) - 9)); cv.put(vgrad(y, 20, 280, C(0xfff0a8), C(0xf7b43a)), cov(np.abs(d) - 8)); cv.put(WHITE, cov(np.abs(d + 4) - 1.5) * 0.6)
        if stars:
            for k in range(8):
                a = k * np.pi / 4 + 0.2; sx, sy = 150 + np.cos(a) * 138, 150 + np.sin(a) * 138; rr = np.hypot(x - sx, y - sy); ang = np.arctan2(y - sy, x - sx)
                st = rr - (9 + 6 * np.cos(ang * 4)) * (1 if k % 2 == 0 else 0.7); cv.put(WHITE, cov(st))
        cv.save(name)
    ring('super_frame', False); ring('super_on', True)
    print('ok')

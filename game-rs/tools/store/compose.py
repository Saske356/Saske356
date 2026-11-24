"""Оформление скриншотов (подпись сверху, рамка), обложка 1920×1080 и финальная заставка трейлера.
python3 compose.py ПАПКА_С_КАДРАМИ ПАПКА_STORE"""
import os, sys
from PIL import Image, ImageDraw, ImageFont, ImageFilter
TMP, OUT = sys.argv[1], sys.argv[2]
HERE = os.path.dirname(os.path.abspath(__file__)); ASSETS = os.path.join(HERE, '..', '..', 'assets')
F = os.path.join(ASSETS, 'fonts') + '/'
fb = lambda s: ImageFont.truetype(F + 'Roboto-Black.ttf', s); fm = lambda s: ImageFont.truetype(F + 'Roboto-Medium.ttf', s)

CAPS = [("Ныряй в бездну", "Последняя искра против тьмы", (0x13, 0x6b, 0x8f)),
        ("Сотни светящихся тварей", "Автострельба — ты только уворачиваешься", (0x2a, 0x1d, 0x6e)),
        ("67 улучшений", "46 обычных и 21 золотая синергия", (0x10, 0x4a, 0x7a)),
        ("Реликвии меняют всё", "16 мощных предметов на забег", (0x5a, 0x2a, 0x10)),
        ("Гигантские боссы", "Живые пасти, щупальца и плавники", (0x4d, 0x0f, 0x3a)),
        ("Существа оживают", "Плавники, ноги и щупальца двигаются", (0x0f, 0x3d, 0x55)),
        ("10 искр — 10 атак", "Иглы, шары, молнии, пламя, звёзды…", (0x1a, 0x3f, 0x6a)),
        ("21 облик Люмена", "Огонь, лёд, пустота, аврора и другие", (0x3a, 0x16, 0x5a))]


def ctext(d, W, y, txt, font, fill):
    w = d.textlength(txt, font=font); d.text(((W - w) / 2 + 3, y + 4), txt, font=font, fill=(0, 0, 0)); d.text(((W - w) / 2, y), txt, font=font, fill=fill)


def frame(shot, title, sub, top):
    W, H = 1080, 1920; c = Image.new('RGB', (W, H)); d = ImageDraw.Draw(c)
    for y in range(H):
        q = y / H; d.line([(0, y), (W, y)], fill=tuple(int(top[i] * (1 - q) + [4, 8, 20][i] * q) for i in range(3)))
    sw = 930; sh = int(shot.height * sw / shot.width); shot = shot.resize((sw, sh), Image.LANCZOS)
    m = Image.new('L', (sw, sh), 0); ImageDraw.Draw(m).rounded_rectangle((0, 0, sw - 1, sh - 1), radius=46, fill=255)
    y0 = H - sh + 40
    glow = Image.new('RGBA', (W, H), (0, 0, 0, 0)); ImageDraw.Draw(glow).rounded_rectangle(((W - sw) // 2 - 14, y0 - 14, (W + sw) // 2 + 14, y0 + sh + 14), radius=58, fill=(120, 230, 255, 90))
    c = Image.alpha_composite(c.convert('RGBA'), glow.filter(ImageFilter.GaussianBlur(22))).convert('RGB'); c.paste(shot, ((W - sw) // 2, y0), m)
    d = ImageDraw.Draw(c); ctext(d, W, 70, title, fb(70), (255, 255, 255)); ctext(d, W, 170, sub, fm(36), (190, 240, 255))
    return c


sd = os.path.join(OUT, 'screenshots')
for f in os.listdir(sd): os.remove(os.path.join(sd, f))
for k, (t, s, col) in enumerate(CAPS):
    p = os.path.join(TMP, f's{k + 1}.png')
    if os.path.exists(p): frame(Image.open(p).convert('RGB'), t, s, col).save(os.path.join(sd, f'{k + 1}.jpg'), quality=92)

key = Image.open(os.path.join(ASSETS, 'fx', 'keyart.png')).convert('RGBA')
bg = Image.open(os.path.join(TMP, 's2.png')).convert('RGB')
# обложка 1920×1080: размытый бой с боссом, арт Люмена, название
cov = bg.resize((1920, int(bg.height * 1920 / bg.width))).crop((0, 900, 1920, 1980)).filter(ImageFilter.GaussianBlur(5))
d = ImageDraw.Draw(cov, 'RGBA'); d.rectangle((0, 0, 1920, 1080), fill=(0, 10, 25, 110))
k2 = key.resize((860, 860)); cov.paste(k2, (1000, 110), k2)
d.text((120, 330), "СВЕТ БЕЗДНЫ", font=fb(130), fill=(255, 255, 255)); d.text((126, 490), "Light of the Abyss", font=fm(64), fill=(190, 240, 255))
d.text((126, 620), "Подводный шутер-рогалик · боссы · реликвии", font=fm(44), fill=(255, 224, 140))
cov.save(os.path.join(OUT, 'cover-1920x1080.jpg'), quality=92)
# финальная заставка трейлера 720×1280
im = Image.open(os.path.join(TMP, 's1.png')).convert('RGB').resize((720, 1280), Image.LANCZOS).filter(ImageFilter.GaussianBlur(6))
d = ImageDraw.Draw(im, 'RGBA'); d.rectangle((0, 0, 720, 1280), fill=(0, 10, 25, 120)); k3 = key.resize((560, 560)); im.paste(k3, (80, 170), k3)
ctext(d, 720, 760, "СВЕТ БЕЗДНЫ", fb(66), (255, 255, 255)); ctext(d, 720, 850, "Light of the Abyss", fm(36), (190, 240, 255)); ctext(d, 720, 1000, "Верни свет океану", fm(36), (255, 224, 140))
im.save(os.path.join(TMP, 'endcard.png'))
print('скриншоты, обложка, заставка — готово')

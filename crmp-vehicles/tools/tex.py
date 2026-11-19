"""Procedural textures for the vehicles (numpy + Pillow).

Every function returns an RGBA uint8 array in image order (row 0 = top),
which is what both PNG files and the TXD writer expect.

Body UV layout (see build.py):  u = x / BODY_LEN  (x from the rear, metres)
  top half of the image  = right side, row 0 = s=BODY_S  (s = height-like arc)
  bottom half            = left side, rotated 180 degrees
"""
import math
import numpy as np
from PIL import Image, ImageDraw, ImageFilter, ImageFont

BODY_LEN, BODY_S = 6.0, 3.2
FONT = "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"
FONT_R = "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"
FONT_C = "/usr/share/fonts/truetype/dejavu/DejaVuSansCondensed-Bold.ttf"


def rng(seed):
    return np.random.default_rng(seed)


def font(size, bold=True, cond=False):
    path = FONT_C if cond else (FONT if bold else FONT_R)
    try:
        return ImageFont.truetype(path, size)
    except OSError:
        return ImageFont.truetype(FONT, size)


def noise(h, w, scale, seed=0, octaves=4):
    """Smooth value noise in [0,1]."""
    r = rng(seed)
    out = np.zeros((h, w), np.float32)
    amp, tot = 1.0, 0.0
    for o in range(octaves):
        gh, gw = max(2, int(h / scale) + 2), max(2, int(w / scale) + 2)
        g = r.random((gh, gw)).astype(np.float32)
        im = Image.fromarray((g * 255).astype(np.uint8)).resize((w, h), Image.BICUBIC)
        out += amp * np.asarray(im, np.float32) / 255
        tot += amp
        amp *= 0.5
        scale /= 2
    return out / tot


def rgba(arr_rgb, alpha=None):
    arr = np.clip(arr_rgb, 0, 255).astype(np.uint8)
    a = np.full(arr.shape[:2], 255, np.uint8) if alpha is None else np.clip(alpha, 0, 255).astype(np.uint8)
    return np.dstack([arr, a])


def tint(gray, color):
    return gray[..., None] * np.array(color, np.float32)[None, None, :] / 255.0


def to_img(a):
    return Image.fromarray(a, "RGBA")


def from_img(im):
    return np.asarray(im.convert("RGBA"), np.uint8).copy()


# ---------------------------------------------------------------- materials
def leather(size=512, color=(40, 38, 36), seed=1, perforated=False, stitch=None):
    n = noise(size, size, 6, seed, 3)
    cells = noise(size, size, 2.5, seed + 7, 2)
    g = 200 + 40 * (n - 0.5) - 30 * np.abs(cells - 0.5)
    img = tint(g, color) * 1.25
    if perforated:
        yy, xx = np.mgrid[0:size, 0:size]
        p = 12
        d = ((xx % p - p / 2) ** 2 + (yy % p - p / 2) ** 2) < 4
        img[d] *= 0.35
    im = to_img(rgba(img))
    if stitch:
        d = ImageDraw.Draw(im)
        for x in (size // 4, 3 * size // 4):
            for y in range(0, size, 14):
                d.line([(x, y), (x, y + 8)], fill=stitch, width=3)
    return from_img(im)


def fabric(size=256, color=(70, 70, 72), seed=2):
    yy, xx = np.mgrid[0:size, 0:size]
    weave = 0.5 + 0.25 * np.sin(xx * 1.6) * np.sin(yy * 1.6)
    n = noise(size, size, 8, seed, 3)
    g = 170 + 60 * (weave - 0.5) + 50 * (n - 0.5)
    return rgba(tint(g, color) * 1.4)


def carpet(size=256, color=(34, 34, 36), seed=3):
    n = rng(seed).random((size, size)).astype(np.float32)
    n = np.asarray(Image.fromarray((n * 255).astype(np.uint8)).filter(ImageFilter.GaussianBlur(0.7)), np.float32) / 255
    g = 150 + 110 * (n - 0.5)
    return rgba(tint(g, color) * 1.5)


def plastic(size=256, color=(28, 28, 30), seed=4, grain=6.0):
    n = noise(size, size, grain, seed, 4)
    g = 210 + 50 * (n - 0.5)
    return rgba(tint(g, color) * 1.2)


def carbon(size=256):
    yy, xx = np.mgrid[0:size, 0:size]
    c = 16
    bx, by = (xx // c), (yy // c)
    fx, fy = (xx % c) / c, (yy % c) / c
    tw = ((bx + by) % 2 == 0)
    sheen = np.where(tw, 0.5 + 0.5 * np.sin(fx * math.pi), 0.5 + 0.5 * np.sin(fy * math.pi))
    g = 25 + 55 * sheen
    return rgba(np.dstack([g, g, g * 1.08]))


def brushed(size=256, color=(200, 200, 205), seed=5, radial=False):
    r = rng(seed)
    if radial:
        yy, xx = np.mgrid[0:size, 0:size] - size / 2
        ang = np.arctan2(yy, xx)
        streak = noise(1, 720, 3, seed, 3)[0]
        g = streak[((ang + math.pi) / (2 * math.pi) * 719).astype(int)]
        g = 200 + 55 * (g - 0.5)
    else:
        line = r.random((size, 1)).astype(np.float32)
        line = np.asarray(Image.fromarray((line * 255).astype(np.uint8)).resize((size, size)), np.float32) / 255
        g = 200 + 50 * (line - 0.5) + 15 * (noise(size, size, 30, seed, 2) - 0.5)
    return rgba(tint(g, color) * 1.27)


def rubber(size=128):
    n = noise(size, size, 3, 9, 2)
    g = 34 + 10 * n
    return rgba(np.dstack([g, g, g]))


def grille_honeycomb(size=256, alpha=True):
    im = Image.new("RGBA", (size, size), (8, 8, 9, 0 if alpha else 255))
    d = ImageDraw.Draw(im)
    r = size / 16
    h = r * math.sqrt(3)
    for row in range(-1, 18):
        for col in range(-1, 12):
            cx = col * 1.5 * r * 1.0 * 1.0 + 0
            cx = col * r * 3 + (row % 2) * r * 1.5
            cy = row * h / 2
            pts = [(cx + r * math.cos(a), cy + r * math.sin(a)) for a in np.linspace(0, 2 * math.pi, 7)]
            d.line(pts, fill=(42, 42, 46, 255), width=max(2, size // 64))
    return from_img(im)


def grille_slats(size=256):
    im = Image.new("RGBA", (size, size), (6, 6, 7, 255))
    d = ImageDraw.Draw(im)
    for y in range(0, size, size // 8):
        d.rectangle([0, y, size, y + size // 22], fill=(185, 188, 196, 255))
        d.rectangle([0, y + size // 22, size, y + size // 22 + 2], fill=(90, 90, 96, 255))
    return from_img(im)


# ---------------------------------------------------------------- gauges
def gauges(w=1024, h=512, maxkmh=260, redline=7, accent=(255, 255, 255), style="classic"):
    """Two round dials: speedometer (left) + tachometer (right).
    The needles are separate meshes rotating about each dial centre:
    0 km/h at -135 deg (lower-left), max at +135 deg."""
    im = Image.new("RGBA", (w, h), (6, 6, 8, 255))
    d = ImageDraw.Draw(im)
    R = h * 0.46
    for i, (cx, maxv, label, step, minor) in enumerate([
            (w * 0.25, maxkmh, "km/h", 20, 10), (w * 0.75, redline + 1, "x1000 r/min", 1, 0.5)]):
        cy = h * 0.5
        # bezel and face
        for k in range(14):
            c = int(120 - k * 7)
            d.ellipse([cx - R + k * 0.6, cy - R + k * 0.6, cx + R - k * 0.6, cy + R - k * 0.6], outline=(c, c, c + 4, 255))
        d.ellipse([cx - R * 0.93, cy - R * 0.93, cx + R * 0.93, cy + R * 0.93], fill=(12, 12, 15, 255))
        v = 0.0
        while v <= maxv + 1e-6:
            a = math.radians(-225 + 270 * v / maxv)
            major = abs(v / step - round(v / step)) < 1e-6
            r0 = R * (0.74 if major else 0.81)
            red = (i == 1 and v >= redline)
            col = (230, 40, 30, 255) if red else (accent + (255,))
            d.line([(cx + r0 * math.cos(a), cy + r0 * math.sin(a)),
                    (cx + R * 0.88 * math.cos(a), cy + R * 0.88 * math.sin(a))],
                   fill=col, width=5 if major else 2)
            if major:
                txt = str(int(v))
                f = font(int(R * 0.15))
                tw = d.textlength(txt, font=f)
                rr = R * 0.58
                d.text((cx + rr * math.cos(a) - tw / 2, cy + rr * math.sin(a) - R * 0.09), txt, font=f, fill=col)
            v += minor if minor else step
        if i == 1:
            a0, a1 = -225 + 270 * redline / maxv, 45
            d.arc([cx - R * 0.88, cy - R * 0.88, cx + R * 0.88, cy + R * 0.88], a0, a1, fill=(230, 40, 30, 255), width=8)
        f = font(int(R * 0.1), bold=False)
        tw = d.textlength(label, font=f)
        d.text((cx - tw / 2, cy + R * 0.32), label, font=f, fill=(170, 170, 175, 255))
        # small digital readout window
        d.rounded_rectangle([cx - R * 0.22, cy + R * 0.5, cx + R * 0.22, cy + R * 0.7], 6, fill=(20, 30, 40, 255))
        f2 = font(int(R * 0.12), cond=True)
        t2 = "D 3" if i else "000123"
        tw = d.textlength(t2, font=f2)
        d.text((cx - tw / 2, cy + R * 0.51), t2, font=f2, fill=(120, 200, 255, 255))
        d.ellipse([cx - R * 0.08, cy - R * 0.08, cx + R * 0.08, cy + R * 0.08], fill=(40, 40, 44, 255))
    # centre warning lamps strip
    for j, c in enumerate([(40, 220, 60), (255, 170, 0), (40, 120, 255), (220, 40, 30)]):
        x = w / 2 - 60 + j * 40
        d.ellipse([x - 9, h * 0.86 - 9, x + 9, h * 0.86 + 9], fill=c + (255,))
    return from_img(im)


def needle(size=128, color=(255, 70, 20)):
    """Needle texture: horizontal bar along +u from the hub (u=0.1)."""
    im = Image.new("RGBA", (size, size // 4), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    h = size // 4
    d.polygon([(0, h * 0.3), (size, h * 0.45), (size, h * 0.55), (0, h * 0.7)], fill=color + (255,))
    return from_img(im)


def screen(w=512, h=256, accent=(60, 150, 255)):
    im = Image.new("RGBA", (w, h), (4, 6, 10, 255))
    d = ImageDraw.Draw(im)
    # map-like navigation screen
    r = rng(11)
    for _ in range(26):
        x0, y0 = r.random() * w, r.random() * h
        x1, y1 = x0 + (r.random() - 0.5) * 300, y0 + (r.random() - 0.5) * 200
        d.line([(x0, y0), (x1, y1)], fill=(40, 46, 58, 255), width=int(2 + r.random() * 6))
    d.line([(w * 0.2, h), (w * 0.35, h * 0.55), (w * 0.6, h * 0.45), (w * 0.8, 0)], fill=accent + (255,), width=8)
    d.polygon([(w * 0.35 - 12, h * 0.55 + 18), (w * 0.35, h * 0.55 - 14), (w * 0.35 + 12, h * 0.55 + 18)], fill=(255, 255, 255, 255))
    d.rectangle([0, 0, w, 34], fill=(10, 14, 22, 255))
    d.text((12, 6), "12:45   +4°C   FM 101.7", font=font(20, bold=False), fill=(220, 225, 235, 255))
    d.rounded_rectangle([w - 160, h - 60, w - 12, h - 12], 10, fill=(20, 26, 36, 255))
    d.text((w - 148, h - 52), "1.2 km", font=font(26), fill=(255, 255, 255, 255))
    return from_img(im)


def climate_panel(w=256, h=128):
    im = Image.new("RGBA", (w, h), (18, 18, 20, 255))
    d = ImageDraw.Draw(im)
    for i, x in enumerate([w * 0.2, w * 0.8]):
        d.ellipse([x - 34, h / 2 - 34, x + 34, h / 2 + 34], fill=(50, 50, 54, 255), outline=(150, 150, 156, 255), width=3)
        d.text((x - 20, h / 2 - 12), "21.5" if i == 0 else "22.0", font=font(18), fill=(255, 140, 40, 255))
    for j in range(5):
        x = w * 0.36 + j * 18
        d.rounded_rectangle([x, h * 0.3, x + 14, h * 0.7], 3, fill=(60, 60, 66, 255))
    return from_img(im)


# ---------------------------------------------------------------- wheels
def tire(w=1024, h=256, brand="ROADMASTER", size_txt="225/45 R18 94W"):
    """u: around the tyre (0..1 = 360deg), v: across profile.
    rows 0..h*0.3 outer sidewall, 0.3..0.7 tread, 0.7..1 inner sidewall."""
    base = 30 + 8 * noise(h, w, 4, 12, 2)
    img = np.dstack([base, base, base])
    im = to_img(rgba(img))
    d = ImageDraw.Draw(im)
    t0, t1 = int(h * 0.3), int(h * 0.7)
    # tread blocks
    for x in range(0, w, 16):
        d.polygon([(x, t0), (x + 6, t0), (x + 14, t0 + (t1 - t0) * 0.38), (x + 8, t0 + (t1 - t0) * 0.38)], fill=(14, 14, 14, 255))
        d.polygon([(x + 8, t1), (x + 14, t1), (x + 6, t1 - (t1 - t0) * 0.38), (x, t1 - (t1 - t0) * 0.38)], fill=(14, 14, 14, 255))
    for frac in (0.44, 0.56):
        y = t0 + (t1 - t0) * frac
        d.rectangle([0, y - 3, w, y + 3], fill=(10, 10, 10, 255))
    # sidewall lettering, raised (lighter)
    f = font(int(h * 0.12))
    fs = font(int(h * 0.07), bold=False)
    for k in range(2):
        x = k * w / 2 + 40
        d.text((x, h * 0.06), brand, font=f, fill=(70, 70, 70, 255))
        d.text((x + 380, h * 0.1), size_txt, font=fs, fill=(62, 62, 62, 255))
    return from_img(im)


def rim(size=256, color=(205, 207, 212), finish="silver"):
    if finish == "black":
        color = (38, 38, 42)
    elif finish == "gunmetal":
        color = (90, 92, 98)
    elif finish == "gold":
        color = (190, 160, 90)
    return brushed(size, color, 21, radial=True)


def brake_disc(size=256):
    yy, xx = np.mgrid[0:size, 0:size] - size / 2
    r = np.hypot(xx, yy) / (size / 2)
    ang = np.arctan2(yy, xx)
    g = 120 + 40 * np.sin(r * 120) * 0.2 + 30 * (noise(size, size, 20, 30, 2) - 0.5)
    holes = (np.abs(np.sin(ang * 12 + r * 6)) < 0.08) & (r > 0.6) & (r < 0.92)
    g = np.where(holes, 30, g)
    g = np.where(r < 0.55, 60, g)
    return rgba(np.dstack([g, g * 0.98, g * 0.95]))


# ---------------------------------------------------------------- lights
def headlight(w=512, h=256, kind="led"):
    """Inside of the head lamp seen through a clear lens: chrome reflector,
    projector(s) and the DRL strip (which is a separate emissive mesh)."""
    yy, xx = np.mgrid[0:h, 0:w].astype(np.float32)
    g = 140 + 80 * np.sin(xx / w * 30) * np.cos(yy / h * 9) * 0.5 + 40 * noise(h, w, 30, 40, 2)
    img = np.dstack([g, g, g * 1.03])
    im = to_img(rgba(img))
    d = ImageDraw.Draw(im)
    d.rectangle([0, 0, w, h * 0.16], fill=(18, 18, 20, 255))
    d.rectangle([0, h * 0.84, w, h], fill=(18, 18, 20, 255))
    cys = h * 0.52
    n = 3 if kind == "led" else 2
    for i in range(n):
        cx = w * (0.25 + 0.5 * i / max(1, n - 1)) if n > 1 else w / 2
        R = h * (0.26 if kind == "led" else 0.32)
        for k in range(10):
            c = 60 + k * 18
            d.ellipse([cx - R + k * 2, cys - R + k * 2, cx + R - k * 2, cys + R - k * 2], outline=(c, c, c, 255), width=3)
        d.ellipse([cx - R * 0.55, cys - R * 0.55, cx + R * 0.55, cys + R * 0.55], fill=(235, 240, 255, 255))
        d.ellipse([cx - R * 0.3, cys - R * 0.3, cx + R * 0.3, cys + R * 0.3], fill=(180, 200, 230, 255))
    return from_img(im)


def taillight(w=512, h=256, pattern="bars"):
    base = np.zeros((h, w, 3), np.float32)
    yy, xx = np.mgrid[0:h, 0:w].astype(np.float32)
    g = 0.55 + 0.45 * np.abs(np.sin(xx / w * 50)) * np.abs(np.sin(yy / h * 14))
    base[..., 0] = 120 + 120 * g
    base[..., 1] = 8 + 20 * g
    base[..., 2] = 10 + 20 * g
    im = to_img(rgba(base))
    d = ImageDraw.Draw(im)
    if pattern == "bars":
        for k in range(4):
            y = h * (0.2 + k * 0.18)
            d.rounded_rectangle([w * 0.05, y, w * 0.95, y + h * 0.07], 6, fill=(255, 60, 50, 255))
    elif pattern == "rings":
        for cx in (w * 0.3, w * 0.7):
            for r in (h * 0.38, h * 0.26):
                d.ellipse([cx - r, h / 2 - r, cx + r, h / 2 + r], outline=(255, 70, 60, 255), width=10)
    else:
        d.rectangle([w * 0.05, h * 0.4, w * 0.95, h * 0.6], fill=(255, 60, 50, 255))
    # reverse light section (white) on the inner end
    d.rectangle([w * 0.82, h * 0.1, w * 0.98, h * 0.9], fill=(200, 200, 205, 255))
    return from_img(im)


def lens(size=256):
    """Clear lens: mostly transparent, faint fresnel rings."""
    yy, xx = np.mgrid[0:size, 0:size] - size / 2
    r = np.hypot(xx, yy)
    a = 40 + 25 * (np.sin(r * 0.6) > 0.95)
    g = np.full((size, size), 240, np.float32)
    return rgba(np.dstack([g, g, g]), a)


# ---------------------------------------------------------------- plates
def plate_ru(w=512, h=112, number="А777АА", region="77"):
    im = Image.new("RGBA", (w, h), (250, 250, 250, 255))
    d = ImageDraw.Draw(im)
    d.rounded_rectangle([2, 2, w - 3, h - 3], 10, outline=(10, 10, 10, 255), width=5)
    split = int(w * 0.76)
    d.line([(split, 4), (split, h - 4)], fill=(10, 10, 10, 255), width=4)
    f_big, f_small = font(int(h * 0.74), cond=True), font(int(h * 0.52), cond=True)
    letters = [number[0], number[1:4], number[4:6]]
    x = 22
    for k, part in enumerate(letters):
        f = f_small if k != 1 else f_big
        y = h * 0.2 if k != 1 else h * 0.07
        d.text((x, y), part, font=f, fill=(10, 10, 10, 255))
        x += d.textlength(part, font=f) + 10
    f_r = font(int(h * 0.5), cond=True)
    tw = d.textlength(region, font=f_r)
    d.text((split + (w - split - tw) / 2, h * 0.02), region, font=f_r, fill=(10, 10, 10, 255))
    f_rus = font(int(h * 0.16))
    d.text((split + 10, h * 0.7), "RUS", font=f_rus, fill=(10, 10, 10, 255))
    fx = split + 62
    for i, c in enumerate([(255, 255, 255), (0, 57, 166), (213, 43, 30)]):
        d.rectangle([fx, h * 0.72 + i * 7, fx + 28, h * 0.72 + i * 7 + 7], fill=c + (255,), outline=(0, 0, 0, 255))
    return from_img(im)


# ---------------------------------------------------------------- liveries
class BodyCanvas:
    """Draws the two body sides in metric coordinates (x along the car from
    the rear, s ~ height above ground on the sides) and composes the final
    texture with the UV convention described at the top of the module."""

    def __init__(self, w=2048, h=1024, base=(255, 255, 255)):
        self.w, self.h = w, h
        self.half = h // 2
        self.side = [Image.new("RGBA", (w, self.half), base + (255,)) for _ in range(2)]
        self.base = base

    def px(self, x, s):
        return x / BODY_LEN * self.w, (1 - s / BODY_S) * self.half

    def poly(self, pts, fill, sides=(0, 1)):
        for k in sides:
            ImageDraw.Draw(self.side[k]).polygon([self.px(*p) for p in pts], fill=fill)

    def rect(self, x0, s0, x1, s1, fill, sides=(0, 1)):
        self.poly([(x0, s0), (x1, s0), (x1, s1), (x0, s1)], fill, sides)

    def text(self, x, s, txt, size_m, fill, sides=(0, 1), anchor="mm"):
        """Text centred at (x, s), size in metres; readable on both sides."""
        fpx = int(size_m / BODY_S * self.half)
        f = font(fpx)
        for k in sides:
            layer = Image.new("RGBA", (self.w, self.half), (0, 0, 0, 0))
            d = ImageDraw.Draw(layer)
            X, Y = self.px(x, s)
            if k == 1:  # left side ends up mirrored: pre-mirror the text so it reads correctly
                X = self.w - X
            d.text((X, Y), txt, font=f, fill=fill, anchor=anchor)
            if k == 1:
                layer = layer.transpose(Image.FLIP_LEFT_RIGHT)
            self.side[k].alpha_composite(layer)

    def compose(self):
        out = Image.new("RGBA", (self.w, self.h))
        out.paste(self.side[0], (0, 0))
        # left side: the canvas is drawn with the front on the right, like the
        # right side; mirrored (front on the left, as seen from outside) and
        # rotated 180 it becomes a plain vertical flip.  Text was pre-mirrored.
        out.paste(self.side[1].transpose(Image.FLIP_TOP_BOTTOM), (0, self.half))
        return from_img(out)


def livery(kind, car, w=2048, h=1024):
    """car: dict with keys len, belt, sill, door_x0, door_x1 (metres)."""
    L, belt, sill = car["len"], car["belt"], car["sill"]
    mid = (car["door_x0"] + car["door_x1"]) / 2
    c = BodyCanvas(w, h)
    if kind == "paint":
        pass
    elif kind == "police":
        blue = (16, 52, 150, 255)
        z0 = sill + (belt - sill) * 0.30
        z1 = sill + (belt - sill) * 0.62
        c.rect(0, z0, BODY_LEN, z1, blue)
        c.rect(0, z1 + 0.02, BODY_LEN, z1 + 0.045, (255, 255, 255, 255))
        c.rect(0, z0 - 0.05, BODY_LEN, z0 - 0.02, blue)
        c.text(mid, (z0 + z1) / 2, "ДПС", (z1 - z0) * 0.8, (255, 255, 255, 255))
        c.text(mid, z1 + 0.13, "ПОЛИЦИЯ", 0.13, blue)
        # emblem panels on the hood / boot ends (top of the canvas = hood/roof)
        c.rect(L - 0.9, BODY_S - 1.1, L, BODY_S, blue)
        c.text(L * 0.12, belt + 0.03, "02", 0.12, blue)
    elif kind == "taxi":
        yel = (255, 205, 30, 255)
        c.rect(0, 0, BODY_LEN, BODY_S, yel)
        z = sill + (belt - sill) * 0.45
        sq = (belt - sill) * 0.13
        for row in range(2):
            for i in range(int(L / sq) + 1):
                if (i + row) % 2 == 0:
                    c.rect(i * sq, z + row * sq, (i + 1) * sq, z + (row + 1) * sq, (12, 12, 12, 255))
        c.text(mid, z + sq * 2 + 0.11, "ТАКСИ", 0.16, (12, 12, 12, 255))
        c.text(mid, z - 0.09, "8-800-555-35-35", 0.07, (12, 12, 12, 255))
    elif kind == "vinyl_stripes":
        for off, col in ((0.0, (12, 12, 14, 255)), (0.10, (220, 30, 30, 255))):
            z = sill + (belt - sill) * 0.55 + off
            c.poly([(0, z), (L, z + 0.06), (L, z + 0.13), (0, z + 0.07)], col)
        c.rect(0, BODY_S - 0.55, BODY_LEN, BODY_S - 0.25, (12, 12, 14, 255))  # over-the-top stripe
        c.text(L * 0.62, sill + 0.08, "R-SPORT", 0.11, (12, 12, 14, 255))
    elif kind == "vinyl_tribal":
        r = rng(5)
        for i in range(9):
            x0 = L * (0.05 + i * 0.1)
            z0 = sill + 0.05
            pts = [(x0, z0), (x0 + 0.5, z0 + 0.42 + r.random() * 0.1), (x0 + 0.85, belt - 0.02), (x0 + 0.42, z0 + 0.3)]
            c.poly(pts, (30, 10, 70, 255) if i % 2 else (230, 0, 120, 255))
        c.text(L * 0.5, belt - 0.12, "DRIFT KING", 0.12, (255, 255, 255, 255))
    elif kind == "vinyl_camo":
        n = noise(c.half, w, 60, 8, 3)
        cols = np.array([[90, 100, 70], [60, 70, 45], [140, 130, 100], [35, 38, 30]], np.float32)
        q = np.clip((n * 4).astype(int), 0, 3)
        side = rgba(cols[q])
        c.side = [to_img(side), to_img(side[:, ::-1].copy())]
    else:
        raise ValueError(kind)
    return c.compose()


def body_seams(w=64):
    g = np.full((w, w, 3), 255, np.float32)
    return rgba(g)


def save_png(arr, path):
    Image.fromarray(arr, "RGBA").save(path, optimize=True)


def wood(size=512, color=(120, 70, 35), seed=13):
    yy, xx = np.mgrid[0:size, 0:size].astype(np.float32)
    n = noise(size, size, 40, seed, 3)
    rings = 0.5 + 0.5 * np.sin((yy / size * 18 + n * 6) * math.pi)
    fine = noise(size, size, 2, seed + 1, 2)
    g = 150 + 70 * rings + 25 * (fine - 0.5)
    img = tint(g, color) * 1.4
    return rgba(img)


def badge(size=128, letter="V"):
    im = Image.new("RGBA", (size, size), (190, 192, 198, 255))
    d = ImageDraw.Draw(im)
    d.ellipse([4, 4, size - 4, size - 4], fill=(20, 30, 60, 255), outline=(230, 230, 235, 255), width=8)
    f = font(int(size * 0.55))
    d.text((size / 2, size / 2), letter, font=f, fill=(235, 235, 240, 255), anchor="mm")
    return from_img(im)

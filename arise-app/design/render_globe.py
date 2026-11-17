import sys, numpy as np
from PIL import Image, ImageFilter
src, out = sys.argv[1], sys.argv[2]
LON0 = float(sys.argv[3]) if len(sys.argv) > 3 else 18
LAT0 = float(sys.argv[4]) if len(sys.argv) > 4 else 22
OUT = int(sys.argv[5]) if len(sys.argv) > 5 else 880
tex = np.asarray(Image.open(src).convert("RGB")).astype(np.float32) / 255.0
th, tw, _ = tex.shape
S = 1100; R = 500; cx = cy = S / 2
lon0, lat0 = np.radians(LON0), np.radians(LAT0)   # смотрим на Европу и Африку, как на образце
y, x = np.mgrid[0:S, 0:S].astype(np.float32)
nx = (x - cx) / R; ny = (cy - y) / R
rr = nx * nx + ny * ny
inside = rr <= 1
nz = np.sqrt(np.clip(1 - rr, 0, 1))
# обратная ортографическая проекция
lat = np.arcsin(np.clip(ny * np.cos(lat0) + nz * np.sin(lat0), -1, 1))
lon = lon0 + np.arctan2(nx, nz * np.cos(lat0) - ny * np.sin(lat0))
u = ((lon / (2 * np.pi) + 0.5) % 1.0) * (tw - 1)
v = (0.5 - lat / np.pi) * (th - 1)
c = tex[v.astype(int).clip(0, th - 1), u.astype(int).clip(0, tw - 1)]
lum = c.mean(axis=2)
lights = np.clip((c[..., 0] - 0.05) * 4.5, 0, 1) ** 0.65
landish = np.clip((c[..., 2] - 0.13) / 0.19, 0, 1) * (1 - lights)
# синяя гамма: океан тёмно-синий, суша чуть светлее, огни бело-голубые
base = np.stack([0.015 + 0.05 * landish, 0.035 + 0.15 * landish, 0.12 + 0.38 * landish], -1)
light = np.stack([0.75 * lights, 0.88 * lights, 1.0 * lights], -1)
img = np.clip(base + light, 0, 1)
# освещение: ярче слева сверху, к краю — синее свечение атмосферы
shade = 0.70 + 0.30 * np.clip(nz, 0, 1)
rim = np.clip((np.sqrt(rr) - 0.80) / 0.20, 0, 1) ** 1.6
img = img * shade[..., None] + np.stack([0.14, 0.40, 1.0], -1) * rim[..., None] * 1.05
alpha = inside.astype(np.float32)
rgba = np.dstack([np.clip(img, 0, 1), alpha])
globe = Image.fromarray((rgba * 255).astype(np.uint8), "RGBA")
# внешнее свечение
glow = Image.new("RGBA", (S, S), (0, 0, 0, 0))
mask = Image.fromarray((inside * 255).astype(np.uint8)).filter(ImageFilter.GaussianBlur(28))
g = Image.new("RGBA", (S, S), (40, 110, 255, 0)); g.putalpha(mask.point(lambda a: int(a * 0.85)))
glow = Image.alpha_composite(glow, g)
outimg = Image.alpha_composite(glow, globe).resize((OUT, OUT), Image.LANCZOS)
outimg.save(out, "WEBP", quality=84, method=6) if out.endswith(".webp") else outimg.save(out)

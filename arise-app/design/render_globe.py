import sys, numpy as np
from PIL import Image, ImageFilter
src, out = sys.argv[1], sys.argv[2]
tex = np.asarray(Image.open(src).convert("RGB")).astype(np.float32) / 255.0
th, tw, _ = tex.shape
S = 1100; R = 500; cx = cy = S / 2
lon0, lat0 = np.radians(18), np.radians(22)   # смотрим на Европу и Африку, как на образце
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
lights = np.clip((c[..., 0] - 0.07) * 3.2, 0, 1) ** 0.75
landish = np.clip((c[..., 2] - 0.13) / 0.19, 0, 1) * (1 - lights)
# синяя гамма: океан тёмно-синий, суша чуть светлее, огни бело-голубые
base = np.stack([0.02 + 0.07 * landish, 0.05 + 0.17 * landish, 0.15 + 0.38 * landish], -1)
light = np.stack([0.75 * lights, 0.88 * lights, 1.0 * lights], -1)
img = np.clip(base + light, 0, 1)
# освещение: ярче слева сверху, к краю — синее свечение атмосферы
shade = 0.55 + 0.45 * np.clip(nz, 0, 1)
rim = np.clip((np.sqrt(rr) - 0.72) / 0.28, 0, 1) ** 2.2
img = img * shade[..., None] + np.stack([0.10, 0.32, 1.0], -1) * rim[..., None] * 0.85
alpha = inside.astype(np.float32)
rgba = np.dstack([np.clip(img, 0, 1), alpha])
globe = Image.fromarray((rgba * 255).astype(np.uint8), "RGBA")
# внешнее свечение
glow = Image.new("RGBA", (S, S), (0, 0, 0, 0))
mask = Image.fromarray((inside * 255).astype(np.uint8)).filter(ImageFilter.GaussianBlur(28))
g = Image.new("RGBA", (S, S), (40, 110, 255, 0)); g.putalpha(mask.point(lambda a: int(a * 0.85)))
glow = Image.alpha_composite(glow, g)
outimg = Image.alpha_composite(glow, globe).resize((880, 880), Image.LANCZOS)
outimg.save(out, "WEBP", quality=82, method=6)

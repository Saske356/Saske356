"""4.9.6: облики в высоком разрешении для карточки «Поделиться рекордом»: Real-ESRGAN ×4 по исходникам
art_src/rig_cache/orig/pl_*.png (цвет — с заливкой прозрачных краёв, альфа — отдельно) → assets/card/pl_*.png (400×400).
Запуск из game-rs: python3 art_src/tools/card_hd.py ВЕСА.pth"""
import sys, glob, os, numpy as np, cv2
from PIL import Image
sys.path.insert(0, os.path.dirname(__file__)); import upscale
upscale.load(sys.argv[1])
for f in sorted(glob.glob('art_src/rig_cache/orig/pl_*.png')):
    im = np.asarray(Image.open(f).convert('RGBA')); a = im[:, :, 3]; rgb = im[:, :, :3].copy()
    mask = (a < 20).astype(np.uint8); rgb = cv2.inpaint(rgb, mask, 6, cv2.INPAINT_TELEA)  # цвет краёв наружу — без тёмного ореола
    up_rgb = np.asarray(upscale.up(Image.fromarray(rgb))); up_a = np.asarray(upscale.up(Image.fromarray(np.dstack([a, a, a])))).mean(2)
    out = Image.fromarray(np.dstack([up_rgb, up_a.clip(0, 255).astype(np.uint8)]), 'RGBA').resize((400, 400), Image.LANCZOS)
    out.save(f'assets/card/{os.path.basename(f)}', optimize=True); print(os.path.basename(f))

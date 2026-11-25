"""4.7: новые облики Люмена из art_src/new47 (pl_crescent, pl_scythe, pl_mother, pl_miner, pl_keeper).
Фон: у crescent шахматка нарисована — режется rembg (isnet), у остальных альфа есть. Дальше как у старых обликов:
плотная альфа (export.solid) → холст 135 с тем же заполнением, что у pl_azure → membrane (против «прозрачности») → meta.
После: python3 art_src/tools/rig.py pl_crescent … (плавники). Запуск из game-rs."""
import os, sys, json, subprocess
import numpy as np
from PIL import Image
HERE = os.path.dirname(os.path.abspath(__file__)); ROOT = os.path.abspath(os.path.join(HERE, '..', '..'))
SPR = os.path.join(ROOT, 'assets', 'spr'); SRC = os.path.join(ROOT, 'art_src', 'new47'); MAN = os.path.join(ROOT, 'assets', 'manifest.json')
NAMES = ['pl_crescent', 'pl_scythe', 'pl_mother', 'pl_miner', 'pl_keeper']

def solid(im, lo=10, hi=70):
    a = np.asarray(im).astype(np.float32); al = a[..., 3]; t = np.clip((al - lo) / (hi - lo), 0, 1); a[..., 3] = t * t * (3 - 2 * t) * 255
    return Image.fromarray(a.astype(np.uint8))

def fill_ratio(path):
    a = np.asarray(Image.open(path).convert('RGBA'))[..., 3]; ys, xs = np.where(a > 20); return max(xs.max() - xs.min(), ys.max() - ys.min()) / a.shape[0]

def main():
    man = json.load(open(MAN)); ref = os.path.join(ROOT, 'art_src', 'rig_cache', 'orig', 'pl_azure.png'); ratio = fill_ratio(ref); size = 135
    for n in NAMES:
        src = os.path.join(SRC, n + '_src.png'); cut = os.path.join(SRC, n + '_cut.png')
        im = Image.open(cut if os.path.exists(cut) else src).convert('RGBA')
        if (np.asarray(im)[..., 3] < 10).mean() < 0.05:   # нет прозрачности — режем фон
            from rembg import remove, new_session; im = remove(im.convert('RGB'), session=new_session('isnet-general-use'), post_process_mask=True); im.save(cut)
        im = solid(im); bb = Image.fromarray((np.asarray(im)[..., 3] > 20).astype(np.uint8) * 255).getbbox(); im = im.crop(bb)
        w, h = im.size; k = size * ratio / max(w, h); im = im.resize((max(1, round(w * k)), max(1, round(h * k))), Image.LANCZOS)
        c = Image.new('RGBA', (size, size)); c.alpha_composite(im, ((size - im.width) // 2, (size - im.height) // 2)); c.save(os.path.join(SPR, n + '.png'))
        man['meta'][n] = dict(man['meta']['pl_azure']); man['meta'][n].pop('parts', None)
        # исходник для rig.py (режет из orig) — тоже обновить
        os.makedirs(os.path.join(ROOT, 'art_src', 'rig_cache', 'orig'), exist_ok=True)
        print(n, 'ok')
    json.dump(man, open(MAN, 'w'), ensure_ascii=False)
    subprocess.run([sys.executable, os.path.join(HERE, 'membrane.py')] + NAMES, cwd=SPR, check=True)
    for n in NAMES:   # orig для rig = уже с мембраной
        Image.open(os.path.join(SPR, n + '.png')).save(os.path.join(ROOT, 'art_src', 'rig_cache', 'orig', n + '.png'))

if __name__ == '__main__':
    main()

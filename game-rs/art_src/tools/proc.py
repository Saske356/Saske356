"""Вырезает существ из картинок ChatGPT: фон убирает rembg, оставляет крупнейший объект, обрезает."""
import numpy as np, json, sys
from PIL import Image
from rembg import new_session, remove
from scipy import ndimage as nd
sess = new_session('isnet-general-use')

def cutout(im, keep_largest=True):
    out = np.asarray(remove(im.convert('RGB'), session=sess)).copy()
    a = out[..., 3] > 40
    if keep_largest:
        lab, n = nd.label(nd.binary_dilation(a, iterations=8))
        if n > 1:
            sz = nd.sum(a, lab, range(1, n + 1)); k = 1 + int(np.argmax(sz))
            m = nd.binary_dilation(lab == k, iterations=2)
            out[..., 3] = (out[..., 3] * m).astype(np.uint8)
    return Image.fromarray(out)

def trim(im):
    a = np.asarray(im)[..., 3]; ys, xs = np.where(a > 10)
    return im.crop((xs.min(), ys.min(), xs.max() + 1, ys.max() + 1))

SHEETS = {
 'sheet_l6': {'pl_frost': (30, 0, 730, 345), 'pl_coral': (780, 0, 1510, 345), 'pl_ghost': (30, 330, 730, 690), 'pl_inferno': (780, 330, 1510, 690),
              'pl_aurora': (30, 660, 730, 1024), 'pl_royal': (780, 660, 1510, 1024)},
 'sheet_boss': {'boss1': (0, 0, 585, 480), 'boss2': (575, 0, 1095, 475), 'boss3': (1085, 0, 1536, 455), 'boss4': (0, 455, 610, 1024),
               'queen': (575, 370, 1536, 790), 'kingcrab': (500, 735, 1030, 1024), 'kingcrab_bare': (1010, 735, 1536, 1024)},
 'sheet_mobs': {'drifter': (30, 30, 345, 240), 'dart': (345, 40, 750, 240), 'jelly': (660, 0, 1030, 270), 'urchin': (1040, 0, 1345, 270), 'spikelet': (1355, 45, 1520, 230),
               'eel': (0, 245, 340, 455), 'eelseg': (345, 280, 535, 455), 'squid': (508, 248, 885, 478), 'crab': (885, 238, 1205, 480), 'crab_bare': (1212, 260, 1536, 478),
               'mender': (0, 440, 348, 765), 'bomber': (348, 455, 642, 755), 'chest': (640, 458, 975, 748), 'crystal': (988, 484, 1152, 762), 'ray': (1150, 498, 1536, 792),
               'lantern': (0, 750, 352, 975), 'wisp': (390, 805, 625, 930), 'spawner': (632, 745, 1055, 1024), 'fry': (1098, 790, 1380, 962)},
}
SINGLE = {'l_azure': 'pl_azure', 'l_ember': 'pl_ember', 'l_emerald': 'pl_emerald', 'l_amethyst': 'pl_amethyst', 'l_void': 'pl_void', 'l_solar': 'pl_solar'}

which = sys.argv[1:]
for sh, boxes in SHEETS.items():
    if which and sh not in which: continue
    src = Image.open(f'in/{sh}.png')
    for name, box in boxes.items():
        trim(cutout(src.crop(box))).save(f'cut/{name}.png'); print(name, flush=True)
if not which or 'single' in which:
    for f, name in SINGLE.items():
        trim(cutout(Image.open(f'in/{f}.png'))).save(f'cut/{name}.png'); print(name, flush=True)

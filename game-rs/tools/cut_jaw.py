"""Вырезает нижнюю челюсть у боссов вида сбоку, чтобы пасть по-настоящему открывалась.

Для каждого спрайта создаёт (рядом, в assets/spr):
  NAME_body.png  — спрайт без челюсти
  NAME_jaw.png   — только челюсть (тот же холст)
  NAME_mouth.png — тёмная глотка, видна в щели, когда пасть раскрыта
Координаты — в сетке 512×512 по исходному спрайту. Запуск: python3 tools/cut_jaw.py
"""
import os, json
import numpy as np
from PIL import Image, ImageDraw, ImageFilter

HERE = os.path.dirname(os.path.abspath(__file__))
SPR = os.path.join(HERE, '..', 'assets', 'spr')
MAN = os.path.join(HERE, '..', 'assets', 'manifest.json')

BOSSES = {
    # шарнир, многоугольник челюсти, многоугольник глотки
    'boss1': dict(hinge=(300, 300),
                  jaw=[(298, 300), (452, 308), (452, 425), (380, 425), (320, 380), (288, 330)],
                  mouth=[(306, 272), (418, 262), (436, 298), (424, 334), (322, 330), (300, 302)]),
    'boss4': dict(hinge=(356, 226),
                  jaw=[(352, 222), (472, 230), (472, 305), (420, 312), (380, 292), (342, 252)],
                  mouth=[(362, 196), (438, 194), (454, 214), (444, 244), (382, 250), (354, 226)]),
    # 4.0: новые владыки
    'boss5': dict(hinge=(428, 286), jaw=[(422, 286), (490, 290), (497, 330), (470, 348), (438, 338), (418, 310)],
                  mouth=[(432, 266), (480, 268), (492, 292), (470, 306), (440, 302)]),
    'boss6': dict(hinge=(424, 262), jaw=[(418, 262), (470, 270), (492, 300), (482, 334), (444, 332), (414, 296)],
                  mouth=[(430, 240), (480, 246), (486, 276), (450, 292), (424, 272)]),
    'boss7': dict(hinge=(392, 236), jaw=[(386, 240), (470, 245), (482, 272), (456, 306), (410, 312), (382, 282)],
                  mouth=[(394, 205), (470, 214), (480, 250), (440, 272), (400, 262), (384, 230)]),
    'boss8': dict(hinge=(410, 266), jaw=[(404, 268), (470, 264), (496, 300), (490, 342), (440, 346), (404, 312)],
                  mouth=[(414, 240), (476, 238), (486, 270), (450, 292), (420, 286)]),
    # мобы: челюсти
    'eel': dict(hinge=(290, 285), jaw=[(285, 282), (440, 272), (440, 352), (360, 362), (300, 345), (275, 305)],
                mouth=[(300, 262), (415, 258), (425, 290), (405, 320), (320, 318), (295, 290)]),
    'lantern': dict(hinge=(380, 300), jaw=[(375, 298), (462, 292), (462, 348), (400, 348), (368, 322)],
                    mouth=[(385, 280), (448, 276), (454, 300), (430, 316), (390, 312)]),
    # крабы: клешня на шарнире (рта нет)
    'crab': dict(hinge=(165, 250), jaw=[(36, 116), (178, 116), (190, 250), (152, 366), (36, 366)], mouth=None),
    'crab_bare': dict(hinge=(340, 282), jaw=[(334, 212), (474, 212), (474, 384), (328, 384), (318, 300)], mouth=None),
    'kingcrab': dict(hinge=(192, 262), jaw=[(46, 214), (204, 214), (218, 300), (172, 376), (46, 376)], mouth=None),
    'kingcrab_bare': dict(hinge=(380, 262), jaw=[(368, 212), (484, 212), (484, 390), (358, 390), (352, 290)], mouth=None),
}
MOUTH_COL = {'': (40, 6, 18), '_t1': (48, 4, 8), '_t2': (22, 6, 36)}


def mask(size, poly, blur):
    s = size / 512
    m = Image.new('L', (size, size), 0)
    ImageDraw.Draw(m).polygon([(x * s, y * s) for x, y in poly], fill=255)
    return m.filter(ImageFilter.GaussianBlur(blur * s))


def main():
    man = json.load(open(MAN))
    import sys
    only = sys.argv[1:]
    for base, cfg in BOSSES.items():
        if only and base not in only: continue
        for tier in ('', '_t1', '_t2'):
            name = base + tier
            p = os.path.join(SPR, name + '.png')
            if not os.path.exists(p):
                continue
            im = Image.open(p).convert('RGBA'); n = im.size[0]
            a = np.asarray(im).astype(np.float32)
            jm = np.asarray(mask(n, cfg['jaw'], 1.2)).astype(np.float32) / 255
            body = a.copy(); body[..., 3] *= (1 - jm)
            jaw = a.copy(); jaw[..., 3] *= jm
            Image.fromarray(body.astype(np.uint8)).save(os.path.join(SPR, name + '_body.png'))
            Image.fromarray(jaw.astype(np.uint8)).save(os.path.join(SPR, name + '_jaw.png'))
            meta = man['meta'][name]
            if cfg['mouth'] is None:
                for suf in ('_body', '_jaw'):
                    m = dict(meta); m['hinge'] = [cfg['hinge'][0] / 512, cfg['hinge'][1] / 512]; man['meta'][name + suf] = m
                man['meta'].pop(name + '_mouth', None); print('ok', name); continue
            # глотка: тёмная, к центру ещё темнее, мягкий край
            mm = np.asarray(mask(n, cfg['mouth'], 6)).astype(np.float32) / 255
            r, g, b = MOUTH_COL[tier]
            mo = np.zeros((n, n, 4), np.float32)
            core = np.asarray(mask(n, cfg['mouth'], 22)).astype(np.float32) / 255
            mo[..., 0] = r * (1 - core * .6); mo[..., 1] = g * (1 - core * .6); mo[..., 2] = b * (1 - core * .6)
            mo[..., 3] = mm * 245
            Image.fromarray(mo.astype(np.uint8)).save(os.path.join(SPR, name + '_mouth.png'))
            meta = man['meta'][name]
            for suf in ('_body', '_jaw', '_mouth'):
                m = dict(meta); m['hinge'] = [cfg['hinge'][0] / 512, cfg['hinge'][1] / 512]
                if suf == '_mouth':
                    m['live'] = False
                man['meta'][name + suf] = m
            print('ok', name)
    json.dump(man, open(MAN, 'w'), ensure_ascii=False)


if __name__ == '__main__':
    main()

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
}
MOUTH_COL = {'': (40, 6, 18), '_t1': (48, 4, 8), '_t2': (22, 6, 36)}


def mask(size, poly, blur):
    s = size / 512
    m = Image.new('L', (size, size), 0)
    ImageDraw.Draw(m).polygon([(x * s, y * s) for x, y in poly], fill=255)
    return m.filter(ImageFilter.GaussianBlur(blur * s))


def main():
    man = json.load(open(MAN))
    for base, cfg in BOSSES.items():
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

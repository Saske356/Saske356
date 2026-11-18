#!/usr/bin/env python3
"""Встраивает рисованные спрайты в game/index.html.

Использование:  python3 tools/embed_art.py ПАПКА_С_PNG
Каждый файл <ключ>.png (crab.png, boss1.png, lumen.png...) сжимается в WebP
и попадает в window.ART_DATA между метками <!--ART--> и <!--/ART-->.
Пустая папка = убрать все картинки (вернуть кодовые спрайты).
"""
import base64, io, os, re, sys
from PIL import Image

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
HTML = os.path.join(ROOT, 'index.html')
ALIAS = {'eel_head': 'eel', 'eel_seg': 'eelseg'}  # имя файла -> ключ спрайта
BIG = ('boss1', 'boss2', 'boss3', 'boss4')

def encode(path, key):
    im = Image.open(path).convert('RGBA')
    bbox = im.getchannel('A').point(lambda a: 255 if a > 8 else 0).getbbox()
    if bbox:  # обрезаем пустые поля и центрируем в квадрат с отступом 10%
        im = im.crop(bbox)
        side = int(max(im.size) / 0.8)
        sq = Image.new('RGBA', (side, side), (0, 0, 0, 0))
        sq.paste(im, ((side - im.width) // 2, (side - im.height) // 2)); im = sq
    size = 512 if key in BIG else 256
    im = im.resize((size, size), Image.LANCZOS)
    buf = io.BytesIO(); im.save(buf, 'WEBP', quality=86, method=6)
    return 'data:image/webp;base64,' + base64.b64encode(buf.getvalue()).decode()

def main():
    src = sys.argv[1] if len(sys.argv) > 1 else os.path.join(ROOT, 'art')
    data = {}
    for f in sorted(os.listdir(src)) if os.path.isdir(src) else []:
        name, ext = os.path.splitext(f)
        if ext.lower() not in ('.png', '.webp', '.jpg', '.jpeg'): continue
        key = ALIAS.get(name, name)
        data[key] = encode(os.path.join(src, f), key)
        print(f'{f:22s} -> {key:10s} {len(data[key]) // 1024} КБ')
    js = ''.join(f'"{k}":"{v}",' for k, v in data.items())
    block = f'<!--ART--><script>window.ART_DATA={{{js}}};</script><!--/ART-->' if data else '<!--ART--><!--/ART-->'
    html = open(HTML, encoding='utf-8').read()
    html, n = re.subn(r'<!--ART-->.*?<!--/ART-->', lambda m: block, html, flags=re.S)
    assert n == 1, 'метка <!--ART--> не найдена'
    open(HTML, 'w', encoding='utf-8').write(html)
    print(f'Встроено картинок: {len(data)}')

if __name__ == '__main__':
    main()

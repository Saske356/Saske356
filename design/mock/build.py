"""Собирает один HTML-файл макета (шрифт, глобус и знак внутри файла).

python3 design/mock/build.py  →  design/mock/arise-mock.html
"""
import base64, os
HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
FONT = os.path.join(ROOT, "arise-app/app/src/main/res/font")


def b64(path):
    with open(path, "rb") as f:
        return base64.b64encode(f.read()).decode()


fonts = "".join(
    f"@font-face{{font-family:Inter;font-weight:{w};src:url(data:font/ttf;base64,{b64(os.path.join(FONT, f'inter_{n}.ttf'))}) format('truetype')}}"
    for n, w in (("regular", 400), ("medium", 500), ("semibold", 600), ("bold", 700))
)
html = open(os.path.join(HERE, "mock.template.html"), encoding="utf-8").read()
html = html.replace("/*FONTS*/", fonts).replace("GLOBE_DATA", "data:image/webp;base64," + b64(os.path.join(HERE, "globe.webp")))
with open(os.path.join(HERE, "arise-mock.html"), "w", encoding="utf-8") as f:
    f.write(html)
print("ok", len(html) // 1024, "KB")

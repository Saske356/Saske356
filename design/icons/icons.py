"""Глянцевые значки Arise: силуэт + градиент + блик сверху + свечение. Генерирует SVG и лист-превью.

python3 design/icons/icons.py  → design/icons/svg/*.svg и design/icons/sheet.html
"""
import os
HERE = os.path.dirname(os.path.abspath(__file__))

# Силуэты (viewBox 0 0 24 24). fill — сплошные формы; stroke — линейные (рисуются толстой линией).
FILL = {
    "bolt": "M14.2 1.2 4.2 13.6h6.4l-1.6 9.2 10.6-13.4h-6.6z",
    "gamepad": "M7.2 6.2h9.6a5.4 5.4 0 0 1 5.2 6.9l-1.3 4.6a3 3 0 0 1-5 1.3l-2.2-2.4h-3l-2.2 2.4a3 3 0 0 1-5-1.3L2 13.1a5.4 5.4 0 0 1 5.2-6.9z",
    "rocket": "M12 1.2c3.4 2.8 4.6 7.6 3.4 12.4l2.6 2.8-.6 3.8-3.6-2.4h-3.6l-3.6 2.4-.6-3.8 2.6-2.8C7.4 8.8 8.6 4 12 1.2z",
    "hat": "M7.3 9.6 8.6 3.6c.2-.8 1-1.2 1.8-1l1.6.5 1.6-.5c.8-.2 1.6.2 1.8 1l1.3 6c3.2.4 5.3 1.1 5.3 1.9 0 1.2-4.9 2.1-11 2.1S1 12.7 1 11.5c0-.8 2.1-1.5 5.3-1.9z",
    "battery": "M9 1.8h6v2h1.6A2.4 2.4 0 0 1 19 6.2v13.4a2.4 2.4 0 0 1-2.4 2.4H7.4A2.4 2.4 0 0 1 5 19.6V6.2a2.4 2.4 0 0 1 2.4-2.4H9z",
    "shield": "M12 1.5 21 4.8v6.6c0 5.3-3.8 9.6-9 11.1-5.2-1.5-9-5.8-9-11.1V4.8z",
    "apps": "M3 5a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2zM13 5a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v4a2 2 0 0 1-2 2h-4a2 2 0 0 1-2-2zM3 15a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2zM13 15a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v4a2 2 0 0 1-2 2h-4a2 2 0 0 1-2-2z",
    "bell": "M12 1.8c4.1 0 6.4 3 6.4 7.1v3.6l2 3.6H3.6l2-3.6V8.9c0-4.1 2.3-7.1 6.4-7.1zM9.2 18.4h5.6a2.8 2.8 0 0 1-5.6 0z",
    "crown": "M1.8 7.2l5.4 4.6L12 3.4l4.8 8.4 5.4-4.6-2.3 11H4.1zM4.4 19.6h15.2v2.2H4.4z",
    "lock": "M7 10V7.4a5 5 0 0 1 10 0V10h.6A2.4 2.4 0 0 1 20 12.4v7.2a2.4 2.4 0 0 1-2.4 2.4H6.4A2.4 2.4 0 0 1 4 19.6v-7.2A2.4 2.4 0 0 1 6.4 10zm2.6 0h4.8V7.4a2.4 2.4 0 0 0-4.8 0z",
    "send": "M1.6 10.8 22 2.4 15.4 22.2l-4.2-7.6-7.4-1.4z",
    "globe": "M12 1.5a10.5 10.5 0 1 1 0 21 10.5 10.5 0 0 1 0-21z",
    "info": "M12 1.5a10.5 10.5 0 1 1 0 21 10.5 10.5 0 0 1 0-21z",
    "bubble": "M12 2.4c5.6 0 10 3.8 10 8.6s-4.4 8.6-10 8.6c-1.2 0-2.3-.2-3.4-.5L3.4 21.4l1.4-4.6C3 15.3 2 13.3 2 11c0-4.8 4.4-8.6 10-8.6z",
    "share": "M12 2.2 17 7.2h-3.4v7.4h-3.2V7.2H7zM4.6 12.6h3v6.2h8.8v-6.2h3v8.4c0 .8-.6 1.2-1.2 1.2H5.8c-.6 0-1.2-.4-1.2-1.2z",
    "backspace": "M8.2 4.2h11.6a2.4 2.4 0 0 1 2.4 2.4v10.8a2.4 2.4 0 0 1-2.4 2.4H8.2L1.8 12z",
}
STROKE = {
    "down": "M12 2.6v12.4M6.2 9.6l5.8 5.8 5.8-5.8M4.2 20.8h15.6",
    "up": "M12 21.4V9M6.2 14.4 12 8.6l5.8 5.8M4.2 3.2h15.6",
    "refresh": "M20.2 12a8.2 8.2 0 0 1-14 5.8M3.8 12a8.2 8.2 0 0 1 14-5.8M18.4 2.4v4.4H14M5.6 21.6v-4.4H10",
    "swap": "M3.4 7.6h16M15.6 3.6l4 4-4 4M20.6 16.4h-16M8.4 12.4l-4 4 4 4",
    "power": "M7.2 5.8a8.4 8.4 0 1 0 9.6 0M12 2.4v8.8",
    "clock": "M3.8 12a8.2 8.2 0 1 0 2.4-5.8M3.4 3.4v4.4h4.4M12 7.6v4.6l3.2 2",
    "clip": "M19.4 11.4 12 18.8a5 5 0 0 1-7-7l7.6-7.6a3.4 3.4 0 0 1 4.8 4.8l-7.4 7.4a1.8 1.8 0 0 1-2.6-2.6l6.8-6.8",
    "search": "M10.4 3.4a7 7 0 1 1 0 14 7 7 0 0 1 0-14zM15.6 15.6l5.2 5.2",
    "gear": "M12 8.4a3.6 3.6 0 1 1 0 7.2 3.6 3.6 0 0 1 0-7.2zM12 2v2.6M12 19.4V22M4.9 4.9l1.9 1.9M17.2 17.2l1.9 1.9M2 12h2.6M19.4 12H22M4.9 19.1l1.9-1.9M17.2 6.8l1.9-1.9",
}
# Тёмные «вырезы» поверх силуэта (глаза шпиона, кнопки геймпада, окно ракеты…)
CUT = {
    "gamepad": '<path d="M7.4 9.8v4.4M5.2 12h4.4" stroke="#0a1838" stroke-width="1.9" stroke-linecap="round"/><circle cx="16.2" cy="10.6" r="1.25" fill="#0a1838"/><circle cx="18.2" cy="13" r="1.25" fill="#0a1838"/>',
    "rocket": '<circle cx="12" cy="8.2" r="1.9" fill="#0a1838"/><path d="M10.4 17.6 12 22.4l1.6-4.8z" fill="#bfe0ff"/>',
    "hat": '<path d="M7.1 11.2h9.8" stroke="#0a1838" stroke-width="1.2" opacity=".7"/>',
    "battery": '<path d="M8.6 12.6c0-3 2.4-5.2 6.6-5.4-.2 4-2.4 6.6-5.6 6.4l-1 3" fill="none" stroke="#0a1838" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"/>',
    "shield": '<rect x="9" y="10.4" width="6" height="5.4" rx="1.1" fill="#0a1838"/><path d="M10.2 10.4V9a1.8 1.8 0 0 1 3.6 0v1.4" fill="none" stroke="#0a1838" stroke-width="1.4"/>',
    "lock": '<circle cx="12" cy="15.4" r="1.7" fill="#0a1838"/><path d="M12 16.4v2.2" stroke="#0a1838" stroke-width="1.6" stroke-linecap="round"/>',
    "globe": '<path d="M12 1.8c-3 2.8-4.4 6.2-4.4 10.2s1.4 7.4 4.4 10.2M12 1.8c3 2.8 4.4 6.2 4.4 10.2s-1.4 7.4-4.4 10.2M2.2 12h19.6M3.6 6.8h16.8M3.6 17.2h16.8" fill="none" stroke="#0a1838" stroke-width="1.3" opacity=".75"/>',
    "send": '<path d="M11.2 14.6 22 2.4" stroke="#0a1838" stroke-width="1.2" opacity=".6"/>',
    "info": '<circle cx="12" cy="7.2" r="1.5" fill="#0a1838"/><path d="M12 11v7" stroke="#0a1838" stroke-width="2.4" stroke-linecap="round"/>',
    "bell": "",
    "bubble": '<circle cx="8" cy="11" r="1.3" fill="#0a1838"/><circle cx="12" cy="11" r="1.3" fill="#0a1838"/><circle cx="16" cy="11" r="1.3" fill="#0a1838"/>',
    "backspace": '<path d="M11 9l5 6M16 9l-5 6" stroke="#0a1838" stroke-width="1.8" stroke-linecap="round"/>',
}
GOLD = {"crown"}
EXTRA = {  # детали поверх (не вырез): очки шпиона
    "hat": '<circle cx="8" cy="17.6" r="3.2" fill="url(#G)"/><circle cx="16" cy="17.6" r="3.2" fill="url(#G)"/><path d="M11 17.4h2" stroke="url(#G)" stroke-width="1.6"/>',
}


def svg(name, uid=""):
    gold = name in GOLD
    top, mid, bot = ("#fff6d6", "#ffd36a", "#d48a1c") if gold else ("#f2f8ff", "#8fc0ff", "#2a62f0")
    glow = "#ffb43a" if gold else "#3d7bff"
    u = name + uid
    defs = f'''<defs>
<linearGradient id="G{u}" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="{top}"/><stop offset=".45" stop-color="{mid}"/><stop offset="1" stop-color="{bot}"/></linearGradient>
<linearGradient id="H{u}" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="#fff" stop-opacity=".75"/><stop offset=".45" stop-color="#fff" stop-opacity=".08"/><stop offset=".55" stop-color="#fff" stop-opacity="0"/></linearGradient>
<filter id="F{u}" x="-40%" y="-40%" width="180%" height="180%"><feGaussianBlur in="SourceAlpha" stdDeviation="1.1" result="b"/><feFlood flood-color="{glow}" flood-opacity=".95"/><feComposite in2="b" operator="in" result="g"/><feMerge><feMergeNode in="g"/><feMergeNode in="SourceGraphic"/></feMerge></filter>
</defs>'''
    if name in FILL:
        d = FILL[name]
        body = (f'<path d="{d}" fill="url(#G{u})" stroke="{bot}" stroke-width=".5" stroke-opacity=".6"/>'
                + EXTRA.get(name, "").replace("url(#G)", f"url(#G{u})")
                + CUT.get(name, "")
                + f'<path d="{d}" fill="url(#H{u})"/>')
    else:
        d = STROKE[name]
        body = (f'<path d="{d}" fill="none" stroke="url(#G{u})" stroke-width="2.6" stroke-linecap="round" stroke-linejoin="round"/>'
                f'<path d="{d}" fill="none" stroke="#fff" stroke-opacity=".35" stroke-width=".8" stroke-linecap="round" stroke-linejoin="round" transform="translate(-.3 -.4)"/>')
    return f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="-2 -2 28 28">{defs}<g filter="url(#F{u})">{body}</g></svg>'


NAMES = list(FILL) + list(STROKE)

if __name__ == "__main__":
    os.makedirs(os.path.join(HERE, "svg"), exist_ok=True)
    for n in NAMES:
        open(os.path.join(HERE, "svg", n + ".svg"), "w").write(svg(n))
    cells = "".join(f'<div class="c" id="i-{n}">{svg(n, "_s")}<span>{n}</span></div>' for n in NAMES)
    open(os.path.join(HERE, "sheet.html"), "w").write(f'''<!doctype html><meta charset=utf-8><style>
body{{margin:0;background:#030817;font:12px sans-serif;color:#8fa8d8;display:grid;grid-template-columns:repeat(6,120px);gap:10px;padding:16px}}
.c{{display:flex;flex-direction:column;align-items:center;gap:6px;padding:12px;border-radius:18px;background:linear-gradient(180deg,rgba(22,40,84,.72),rgba(8,16,38,.78));border:1px solid rgba(140,185,255,.45)}}
.c svg{{width:72px;height:72px}}</style>{cells}''')
    print(len(NAMES), "значков")

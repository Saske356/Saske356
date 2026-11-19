"""Конвертер района карты GTA/CRMP (IPL + IMG + texdb) в один .glb для ONIKS RP.

    python3 tools/map2glb.py <папка кэша> <x0> <y0> <x1> <y1> <куда.glb>

<папка кэша> — корень кэша клиента (data/gta.dat, data/maps, texdb/). Координаты — в системе GTA.
Район сдвигается в координаты нашей игры (центр в 328,328), рядом пишется <имя>.json:
точка спавна, границы и смещение, а также <имя>.png — миникарта (1 пиксель = 1 метр).
"""
import io
import json
import math
import os
import re
import struct
import sys
import tempfile

from PIL import Image, ImageDraw

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import rwdff  # noqa: E402
import texdb  # noqa: E402
from dff2glb import Glb, Prim, dedupe  # noqa: E402

CENTER = 328.0  # центр нашей карты (SIZE / 2)
TILE = 100.0


def ci_path(folder, rel):
    """Путь без учёта регистра (в GTA пути в gta.dat записаны как попало)."""
    cur = folder
    for part in re.split(r"[\\/]", rel):
        if not part:
            continue
        low = part.lower()
        hit = next((f for f in os.listdir(cur) if f.lower() == low), None)
        if hit is None:
            return None
        cur = os.path.join(cur, hit)
    return cur


def load_instances(root):
    gta = ci_path(root, "data/gta.dat")
    out = []
    for line in open(gta, encoding="latin1"):
        p = line.strip().split(None, 1)
        if len(p) != 2 or p[0].upper() != "IPL":
            continue
        f = ci_path(root, p[1])
        if not f or not f.lower().endswith(".ipl"):
            continue
        sec, local, lods = None, [], set()
        for l in open(f, encoding="latin1"):
            l = l.strip()
            if l.lower() in ("inst", "end", "cull", "pick", "zone", "occl", "mult", "grge", "enex", "cars", "jump", "tcyc", "auzo"):
                sec = l.lower()
                continue
            if sec == "inst" and l and not l.startswith("#"):
                q = [x.strip() for x in l.split(",")]
                try:
                    local.append((q[1].lower(), *map(float, q[3:10])))
                    if len(q) > 10 and int(q[10]) >= 0:
                        lods.add(int(q[10]))  # ссылка на упрощённую копию для дальнего плана
                except (ValueError, IndexError):
                    local.append(None)
        # упрощённые копии (LOD) не рисуем — рядом стоит детальная модель
        out.extend(e for k, e in enumerate(local) if e is not None and k not in lods)
    return out


def img_index(path):
    f = open(path, "rb")
    hdr = f.read(8)
    n = struct.unpack("<I", hdr[4:])[0]
    d = f.read(32 * n)
    ents = {}
    for i in range(n):
        off, s1, s2, name = struct.unpack_from("<IHH24s", d, i * 32)
        ents[name.split(b"\0")[0].decode("latin1").lower()] = (off * 2048, (s1 or s2) * 2048)
    return f, ents


def quat_matrix(qx, qy, qz, qw):
    # в IPL San Andreas вращение записано сопряжённым кватернионом
    x, y, z, w = -qx, -qy, -qz, qw
    return [[1 - 2 * (y * y + z * z), 2 * (x * y - z * w), 2 * (x * z + y * w)],
            [2 * (x * y + z * w), 1 - 2 * (x * x + z * z), 2 * (y * z - x * w)],
            [2 * (x * z - y * w), 2 * (y * z + x * w), 1 - 2 * (x * x + y * y)]]


def main():
    root, x0, y0, x1, y1, out = sys.argv[1], *map(float, sys.argv[2:6]), sys.argv[6]
    cx, cy = (x0 + x1) / 2, (y0 + y1) / 2
    imgf, ents = img_index(ci_path(root, "texdb/gta3.img"))
    inst = [i for i in load_instances(root) if x0 <= i[1] <= x1 and y0 <= i[2] <= y1 and i[3] < 400]
    # В кэше Black Russia у объекта бывает копия для дальнего плана: то же имя с лишней «a» спереди
    # (или без неё) на том же месте. Из такой пары оставляем более детальную (больший файл модели).
    size = lambda n: ents.get(n + ".dff", (0, 0))[1]
    spot = {}
    for e in inst:
        spot.setdefault((round(e[1] / 4), round(e[2] / 4)), set()).add(e[0])
    def twin_is_better(e):
        bx, by = round(e[1] / 4), round(e[2] / 4)
        twins = {e[0][1:]} if e[0].startswith("a") else set()
        twins.add("a" + e[0])
        for dx in (-1, 0, 1):
            for dy in (-1, 0, 1):
                for t in twins & spot.get((bx + dx, by + dy), set()):
                    if size(t) > size(e[0]):
                        return True
        return False
    inst = [e for e in inst if not twin_is_better(e)]
    texs = texdb.TexSet(ci_path(root, "texdb"), ["gta3", "gta_int", "txd", "samp", "mobile"])
    cache, tiles, colors, texinfo = {}, {}, {}, {}
    zs = []

    def geometry_of(name):
        if name not in cache:
            e = ents.get(name + ".dff")
            cache[name] = None
            if e:
                imgf.seek(e[0])
                tmp = tempfile.NamedTemporaryFile(suffix=".dff", delete=False)
                tmp.write(imgf.read(e[1]))
                tmp.close()
                try:
                    fr, gs, at = rwdff.load(tmp.name)
                    cache[name] = [(rwdff.world_matrix(fr, fi), gs[gi]) for fi, gi in at
                                   if gi < len(gs) and gs[gi].verts and "lod" not in fr[fi].name.lower()]
                except Exception as ex:
                    print("пропущена модель", name, ex)
                finally:
                    os.remove(tmp.name)
        return cache[name]

    alpha_tex = set()

    def texture(name):
        if name not in texinfo:
            img, sharp = texs.get(name) if name else (None, False)
            texinfo[name] = img
            # листва, заборы, провода: у текстуры есть прозрачные пиксели — рисуем «вырезом»
            if img is not None and img.mode == "RGBA" and img.getchannel("A").getextrema()[0] < 128:
                alpha_tex.add(name)
            if img is not None:
                small = img.convert("RGBA").resize((1, 1), Image.BOX).getpixel((0, 0))
                colors[name] = small
        return texinfo[name]

    for name, px, py, pz, qx, qy, qz, qw in inst:
        geo = geometry_of(name)
        if not geo:
            continue
        rot = quat_matrix(qx, qy, qz, qw)
        for mtx, g in geo:
            for (a, b, c, mi) in g.tris:
                if mi >= len(g.materials) or max(a, b, c) >= len(g.verts):
                    continue
                mat = g.materials[mi]
                tex = (mat.texture or "").lower()
                if texture(tex) is None:
                    tex = ""
                world = []
                for v in (a, b, c):
                    lx, ly, lz = (sum(mtx[i][k] * g.verts[v][k] for k in range(3)) + mtx[i][3] for i in range(3))
                    wx = rot[0][0] * lx + rot[0][1] * ly + rot[0][2] * lz + px
                    wy = rot[1][0] * lx + rot[1][1] * ly + rot[1][2] * lz + py
                    wz = rot[2][0] * lx + rot[2][1] * ly + rot[2][2] * lz + pz
                    world.append((wx, wy, wz))
                # GTA → наша игра: x влево, y вверх, z вперёд, центр района в 328,328
                pts = [(cx - w[0] + CENTER, w[2], w[1] - cy + CENTER) for w in world]
                zs.extend(p[1] for p in pts)
                ux, uy, uz = (pts[1][i] - pts[0][i] for i in range(3))
                vx, vy, vz = (pts[2][i] - pts[0][i] for i in range(3))
                n = (uy * vz - uz * vy, uz * vx - ux * vz, ux * vy - uy * vx)
                ln = math.sqrt(sum(t * t for t in n)) or 1
                n = tuple(t / ln for t in n)
                tx = int((pts[0][0] + pts[1][0] + pts[2][0]) / 3 // TILE)
                tz = int((pts[0][2] + pts[1][2] + pts[2][2]) / 3 // TILE)
                key = (tx, tz)
                blend = mat.color[3] < 255
                cut = tex in alpha_tex
                pk = ("t:" + tex if tex else "c") + (":b" if blend else "")
                prims = tiles.setdefault(key, {})
                p = prims.setdefault(pk, (Prim(), {"color": (1, 1, 1, 1), "texture": tex or None, "blend": blend and not cut,
                                                   "mask": cut, "vc": True}))[0]
                for k, v in enumerate((a, b, c)):
                    pre = g.colors[v] if g.colors else (200, 200, 200, 255)
                    # запечённый свет GTA темноват — поднимаем яркость
                    col = tuple(min(1.0, mat.color[i] / 255 * (pre[i] / 255) * 1.6) for i in range(3)) + (mat.color[3] / 255,)
                    p.idx.append(len(p.pos))
                    p.pos.append(pts[k]); p.nrm.append(n)
                    p.uv.append(g.uvs[v] if g.uvs else (0.0, 0.0))
                    p.col.append(col)
    if not tiles:
        print("в районе нет объектов")
        return
    base = sorted(zs)[len(zs) // 50]  # почти самая низкая точка — уровень земли ≈ 0
    for prims in tiles.values():
        for p, _ in prims.values():
            p.pos = [(x, y - base, z) for x, y, z in p.pos]

    # glb: свои текстуры (PNG), участки — отдельные узлы
    g = Glb()
    tmpdir = tempfile.mkdtemp()
    textures = {}
    for name, img in texinfo.items():
        if img is not None and name:
            path = os.path.join(tmpdir, re.sub(r"[^a-z0-9_]", "_", name) + ".png")
            im = img.convert("RGBA")
            if max(im.size) > 256:
                im = im.resize((min(256, im.size[0]), min(256, im.size[1])), Image.LANCZOS)
            im.save(path, optimize=True)
            textures[name] = path
    for (tx, tz), prims in sorted(tiles.items()):
        fixed = {}
        for key, (p, info) in prims.items():
            info = dict(info)
            info["vc"] = (1, 1, 1, 1)
            if not info.get("texture"):
                info.pop("texture", None)
            fixed[key] = (p, info)
        mesh = g.mesh(fixed, textures)
        if mesh is not None:
            g.node(f"tile_{tx}_{tz}", mesh)
    g.save(out)

    # миникарта: треугольники сверху цветом текстур, сначала низкие
    allp = [(p, info) for prims in tiles.values() for p, info in prims.values()]
    W = 656
    mm = Image.new("RGB", (W, W), (40, 62, 36))
    d = ImageDraw.Draw(mm)
    tris = []
    for p, info in allp:
        c = colors.get(info.get("texture") or "", (150, 150, 150, 255))
        for i in range(0, len(p.idx), 3):
            a, b, cc = (p.pos[p.idx[i + k]] for k in range(3))
            if p.nrm[p.idx[i]][1] < 0.3:
                continue
            tris.append(((a[1] + b[1] + cc[1]) / 3, [(a[0], a[2]), (b[0], b[2]), (cc[0], cc[2])], c))
    for _, poly, c in sorted(tris, key=lambda t: t[0]):
        d.polygon(poly, fill=tuple(int(x) for x in c[:3]))
    png = out[:-4] + ".png"
    mm.save(png)
    meta = {"source": [x0, y0, x1, y1], "center_gta": [cx, cy], "base": base, "spawn": [CENTER, CENTER],
            "tiles": len(tiles), "objects": len(inst), "size": os.path.getsize(out)}
    json.dump(meta, open(out[:-4] + ".json", "w"), indent=1)
    print(json.dumps(meta, ensure_ascii=False))


if __name__ == "__main__":
    main()

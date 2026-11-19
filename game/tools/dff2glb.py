"""Конвертер машин RenderWare (.dff + .png) в glTF (.glb) для ONIKS RP.

    python3 tools/dff2glb.py <папка с dff> <папка с текстурами> <куда класть .glb>

Что делает:
- переводит координаты GTA (Z вверх, Y вперёд) в glTF (Y вверх, Z вперёд);
- части «_vlo» (дальний LOD) и «_dam» (повреждённые) пропускает;
- колесо (в GTA оно одно) раскладывает на 4 узла wheel_lf/rf/lb/rb, чтобы игра могла их крутить;
- служебные цвета GTA превращает в материалы: paint1/paint2 — краска (игра перекрашивает),
  light_front/light_rear — фары (светятся ночью), glass — тонированные стёкла;
- пишет cars.json: размеры каждой машины и радиус колеса.
"""
import json
import math
import os
import struct
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import rwdff  # noqa: E402

PAINT1, PAINT2 = (60, 255, 0), (255, 0, 175)
LIGHTS_FRONT = {(255, 175, 0), (0, 255, 200)}
LIGHTS_REAR = {(185, 255, 60), (255, 60, 0), (185, 255, 0)}
WHEELS = {"wheel_lf_dummy": "wheel_lf", "wheel_rf_dummy": "wheel_rf", "wheel_lb_dummy": "wheel_lb",
          "wheel_rb_dummy": "wheel_rb", "wheel_lm_dummy": "wheel_lm", "wheel_rm_dummy": "wheel_rm"}


def conv(v):
    """GTA (x вправо, y вперёд, z вверх) → glTF (x влево, y вверх, z вперёд)."""
    return (-v[0], v[2], v[1])


def apply(m, v, w=1.0):
    return tuple(m[i][0] * v[0] + m[i][1] * v[1] + m[i][2] * v[2] + m[i][3] * w for i in range(3))


def classify(mat, textures):
    rgb, a = tuple(mat.color[:3]), mat.color[3]
    tex = (mat.texture or "").lower()
    if rgb == PAINT1:
        return "paint1", {"color": (1, 1, 1, 1), "metal": 0.35, "rough": 0.35}
    if rgb == PAINT2:
        return "paint2", {"color": (1, 1, 1, 1), "metal": 0.35, "rough": 0.35}
    if rgb in LIGHTS_FRONT:
        return "light_front", {"color": (1.0, 0.97, 0.9, 1), "emissive": (1.0, 0.95, 0.8)}
    if rgb in LIGHTS_REAR:
        return "light_rear", {"color": (0.7, 0.05, 0.05, 1), "emissive": (1.0, 0.1, 0.05)}
    if tex == "remaptoner" or (a < 255 and not (tex and tex in textures)):
        return "glass", {"color": (0.06, 0.08, 0.1, 0.55), "blend": True, "metal": 0.1, "rough": 0.05}
    # Всё остальное красим цветом вершин: одинаковые по виду материалы сливаются в один —
    # меньше отдельных команд видеокарте, выше FPS на телефоне.
    c = tuple(x / 255 for x in mat.color)
    blend = a < 255
    if tex and tex in textures:
        return f"tex:{tex}:{int(blend)}", {"color": (1, 1, 1, 1), "texture": tex, "blend": blend, "vc": c}
    if tex:  # стандартная текстура GTA, которой нет в паке — просто цвет
        c = (0.55, 0.55, 0.57, c[3]) if rgb in ((255, 255, 255), (204, 204, 204)) else c
    return f"vc:{int(blend)}", {"color": (1, 1, 1, 1), "rough": 0.6, "blend": blend, "vc": c}


class Prim:
    def __init__(self):
        self.pos, self.nrm, self.uv, self.col, self.idx = [], [], [], [], []


def bake(geom, matrix, prims, textures, normal_fix=None):
    """Добавляет треугольники геометрии в примитивы по материалам (в координатах glTF)."""
    rot = [row[:3] + [0] for row in matrix[:3]] + [[0, 0, 0, 1]]
    verts = [conv(apply(matrix, v)) for v in geom.verts]
    if geom.normals:
        norms = [conv(apply(rot, n, 0)) for n in geom.normals]
    else:
        norms = None
    for (a, b, c, mi) in geom.tris:
        if mi >= len(geom.materials) or max(a, b, c) >= len(verts):
            continue
        key, info = classify(geom.materials[mi], textures)
        p = prims.setdefault(key, (Prim(), info))[0]
        if norms is None:
            # плоская нормаль треугольника
            va, vb, vc = verts[a], verts[b], verts[c]
            ux, uy, uz = vb[0] - va[0], vb[1] - va[1], vb[2] - va[2]
            wx, wy, wz = vc[0] - va[0], vc[1] - va[1], vc[2] - va[2]
            n = (uy * wz - uz * wy, uz * wx - ux * wz, ux * wy - uy * wx)
            l = math.sqrt(sum(x * x for x in n)) or 1
            fn = tuple(x / l for x in n)
        for v in (a, b, c):
            p.idx.append(len(p.pos))
            p.pos.append(verts[v])
            n = norms[v] if norms else fn
            l = math.sqrt(sum(x * x for x in n)) or 1
            p.nrm.append(tuple(x / l for x in n))
            p.uv.append(geom.uvs[v] if geom.uvs else (0.0, 0.0))
            p.col.append(info.get("vc", (1, 1, 1, 1)))


def dedupe(p):
    """Склеивает одинаковые вершины — файл меньше, рисуется быстрее."""
    seen, pos, nrm, uv, col, idx = {}, [], [], [], [], []
    for i in p.idx:
        k = (tuple(round(x, 5) for x in p.pos[i]), tuple(round(x, 3) for x in p.nrm[i]), tuple(round(x, 5) for x in p.uv[i]), p.col[i])
        j = seen.get(k)
        if j is None:
            j = seen[k] = len(pos)
            pos.append(p.pos[i]); nrm.append(p.nrm[i]); uv.append(p.uv[i]); col.append(p.col[i])
        idx.append(j)
    p.pos, p.nrm, p.uv, p.col, p.idx = pos, nrm, uv, col, idx


class Glb:
    def __init__(self):
        self.bin = bytearray()
        self.j = {"asset": {"version": "2.0", "generator": "oniks dff2glb"}, "scene": 0, "scenes": [{"nodes": []}],
                  "nodes": [], "meshes": [], "materials": [], "accessors": [], "bufferViews": [],
                  "samplers": [{"wrapS": 10497, "wrapT": 10497, "magFilter": 9729, "minFilter": 9987}],
                  "images": [], "textures": [], "buffers": [{"byteLength": 0}]}
        self.tex_index = {}

    def view(self, data, target=None):
        while len(self.bin) % 4:
            self.bin.append(0)
        v = {"buffer": 0, "byteOffset": len(self.bin), "byteLength": len(data)}
        if target:
            v["target"] = target
        self.bin += data
        self.j["bufferViews"].append(v)
        return len(self.j["bufferViews"]) - 1

    def accessor(self, values, kind, comp=5126, target=34962, minmax=False):
        n = {"SCALAR": 1, "VEC2": 2, "VEC3": 3, "VEC4": 4}[kind]
        fmt = {5126: "f", 5125: "I", 5123: "H"}[comp]
        flat = [x for v in values for x in (v if n > 1 else (v,))]
        a = {"bufferView": self.view(struct.pack(f"<{len(flat)}{fmt}", *flat), target), "componentType": comp,
             "count": len(values), "type": kind}
        if minmax:
            a["min"] = [min(v[i] for v in values) for i in range(n)]
            a["max"] = [max(v[i] for v in values) for i in range(n)]
        self.j["accessors"].append(a)
        return len(self.j["accessors"]) - 1

    def texture(self, name, path):
        if name not in self.tex_index:
            with open(path, "rb") as f:
                img = self.view(f.read())
            self.j["images"].append({"bufferView": img, "mimeType": "image/png"})
            self.j["textures"].append({"sampler": 0, "source": len(self.j["images"]) - 1})
            self.tex_index[name] = len(self.j["textures"]) - 1
        return self.tex_index[name]

    def material(self, key, info, textures):
        m = {"name": key[:40],
             "pbrMetallicRoughness": {"baseColorFactor": list(info["color"]), "metallicFactor": info.get("metal", 0.0),
                                      "roughnessFactor": info.get("rough", 0.5)}}
        if "texture" in info:
            m["pbrMetallicRoughness"]["baseColorTexture"] = {"index": self.texture(info["texture"], textures[info["texture"]])}
        if "emissive" in info:
            m["emissiveFactor"] = list(info["emissive"])
        if info.get("blend"):
            m["alphaMode"] = "BLEND"
        m["doubleSided"] = True
        self.j["materials"].append(m)
        return len(self.j["materials"]) - 1

    def mesh(self, prims, textures):
        out = []
        for key, (p, info) in prims.items():
            if not p.idx:
                continue
            dedupe(p)
            big = len(p.pos) > 65535
            out.append({"attributes": {"POSITION": self.accessor(p.pos, "VEC3", minmax=True),
                                       "NORMAL": self.accessor(p.nrm, "VEC3"),
                                       "TEXCOORD_0": self.accessor(p.uv, "VEC2"),
                                       **({"COLOR_0": self.accessor(p.col, "VEC4")} if "vc" in info else {})},
                        "indices": self.accessor(p.idx, "SCALAR", 5125 if big else 5123, 34963),
                        "material": self.material(key, info, textures)})
        if not out:
            return None
        self.j["meshes"].append({"primitives": out})
        return len(self.j["meshes"]) - 1

    def node(self, name, mesh=None, t=None, r=None):
        n = {"name": name}
        if mesh is not None:
            n["mesh"] = mesh
        if t:
            n["translation"] = list(t)
        if r:
            n["rotation"] = list(r)
        self.j["nodes"].append(n)
        self.j["scenes"][0]["nodes"].append(len(self.j["nodes"]) - 1)

    def save(self, path):
        while len(self.bin) % 4:
            self.bin.append(0)
        self.j["buffers"][0]["byteLength"] = len(self.bin)
        for k in ("images", "textures"):
            if not self.j[k]:
                del self.j[k]
        js = json.dumps(self.j, separators=(",", ":")).encode()
        js += b" " * ((4 - len(js) % 4) % 4)
        total = 12 + 8 + len(js) + 8 + len(self.bin)
        with open(path, "wb") as f:
            f.write(struct.pack("<III", 0x46546C67, 2, total))
            f.write(struct.pack("<II", len(js), 0x4E4F534A) + js)
            f.write(struct.pack("<II", len(self.bin), 0x004E4942) + self.bin)


def convert(dff, textures, out):
    frames, geoms, atomics = rwdff.load(dff)
    body = {}
    wheel_geom = wheel_local = None
    for fi, gi in atomics:
        name = frames[fi].name.lower()
        if gi >= len(geoms) or not geoms[gi].verts or name.endswith("_vlo") or name.endswith("_dam"):
            continue
        if name == "wheel" or (frames[fi].parent >= 0 and frames[frames[fi].parent].name.lower() in WHEELS and wheel_geom is None):
            wheel_geom = geoms[gi]
            f = frames[fi]
            r = f.rot
            wheel_local = [[r[0], r[3], r[6], f.pos[0]], [r[1], r[4], r[7], f.pos[1]], [r[2], r[5], r[8], f.pos[2]], [0, 0, 0, 1]]
            continue
        bake(geoms[gi], rwdff.world_matrix(frames, fi), body, textures)
    if not body:
        return None
    g = Glb()
    g.node("body", g.mesh(body, textures))
    allpos = [v for p, _ in body.values() for v in p.pos]
    radius = 0.35
    if wheel_geom is not None:
        wp = {}
        bake(wheel_geom, wheel_local, wp, textures)
        ws = [v for p, _ in wp.values() for v in p.pos]
        if ws:
            radius = (max(v[1] for v in ws) - min(v[1] for v in ws)) / 2
        wm = g.mesh(wp, textures)
        for i, f in enumerate(frames):
            nm = WHEELS.get(f.name.lower())
            if not nm or wm is None:
                continue
            m = rwdff.world_matrix(frames, i)
            t = conv((m[0][3], m[1][3], m[2][3]))
            left = "_l" in nm
            # колесо в GTA смоделировано для правой стороны — левые разворачиваем на 180°
            g.node(nm, wm, t, (0, 1, 0, 0) if left else None)
            allpos.append((t[0] + radius, t[1] - radius, t[2]))
    g.save(out)
    xs, ys, zs = [v[0] for v in allpos], [v[1] for v in allpos], [v[2] for v in allpos]
    return {"len": round(max(zs) - min(zs), 3), "wid": round(max(xs) - min(xs), 3), "hgt": round(max(ys) - min(ys), 3),
            "bottom": round(min(ys), 3), "wheel": round(radius, 3), "size": os.path.getsize(out)}


def main():
    src, texdir, dst = sys.argv[1:4]
    only = set(sys.argv[4].split(",")) if len(sys.argv) > 4 else None
    os.makedirs(dst, exist_ok=True)
    textures = {f[:-4].lower(): os.path.join(texdir, f) for f in os.listdir(texdir) if f.lower().endswith(".png")}
    index, failed = {}, []
    for f in sorted(os.listdir(src)):
        if not f.lower().endswith(".dff"):
            continue
        name = f[:-4].lower()
        if only and name not in only:
            continue
        try:
            info = convert(os.path.join(src, f), textures, os.path.join(dst, name + ".glb"))
            if info:
                index[name] = info
            else:
                failed.append(name)
        except Exception as e:  # битые или нестандартные файлы — пропускаем
            failed.append(f"{name} ({e})")
    with open(os.path.join(dst, "cars.json"), "w") as fh:
        json.dump(index, fh, ensure_ascii=False, indent=0)
    print(f"готово: {len(index)} машин, пропущено {len(failed)}")
    if failed:
        print("пропущены:", ", ".join(failed[:20]))


if __name__ == "__main__":
    main()

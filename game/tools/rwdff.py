"""Разбор моделей RenderWare .dff (формат GTA San Andreas / CRMP): узлы, геометрия, материалы."""
import struct

T_STRUCT, T_STRING, T_EXT, T_TEXTURE, T_MATERIAL, T_MATLIST = 0x01, 0x02, 0x03, 0x06, 0x07, 0x08
T_FRAMELIST, T_GEOMETRY, T_CLUMP, T_ATOMIC, T_GEOMLIST = 0x0E, 0x0F, 0x10, 0x14, 0x1A
T_BINMESH, T_NODENAME = 0x50E, 0x253F2FE


def chunks(b, off, end):
    while off + 12 <= end:
        t, size, ver = struct.unpack_from('<III', b, off)
        yield t, off + 12, off + 12 + size, ver
        off += 12 + size


def find(b, off, end, t):
    for ct, s, e, v in chunks(b, off, end):
        if ct == t:
            return s, e, v
    return None


class Frame:
    def __init__(self, rot, pos, parent):
        self.rot, self.pos, self.parent, self.name = rot, pos, parent, ''


class Material:
    def __init__(self, color, texture):
        self.color, self.texture = color, texture


class Geometry:
    def __init__(self):
        self.verts, self.normals, self.uvs, self.colors, self.tris, self.materials = [], None, None, None, [], []


def parse_frames(b, s, e):
    st = find(b, s, e, T_STRUCT)
    n = struct.unpack_from('<I', b, st[0])[0]
    frames = []
    o = st[0] + 4
    for _ in range(n):
        v = struct.unpack_from('<12fiI', b, o)
        frames.append(Frame(v[0:9], v[9:12], v[12]))
        o += 56
    i = 0
    for ct, cs, ce, _ in chunks(b, st[1], e):
        if ct != T_EXT:
            continue
        nm = find(b, cs, ce, T_NODENAME)
        if nm and i < n:
            frames[i].name = b[nm[0]:nm[1]].decode('latin1').strip('\0')
        i += 1
    return frames


def parse_material(b, s, e):
    st = find(b, s, e, T_STRUCT)
    _flags, r, g, bl, a, _unused, textured = struct.unpack_from('<I4BiI', b, st[0])
    tex = None
    if textured:
        t = find(b, st[1], e, T_TEXTURE)
        if t:
            strs = [b[cs:ce].split(b'\0')[0].decode('latin1') for ct, cs, ce, _ in chunks(b, t[0], t[1]) if ct == T_STRING]
            tex = strs[0] if strs else None
    return Material((r, g, bl, a), tex)


def parse_geometry(b, s, e):
    st = find(b, s, e, T_STRUCT)
    o = st[0]
    flags, nuv, native, ntri, nvert, nmorph = struct.unpack_from('<HBBiii', b, o)
    o += 16
    g = Geometry()
    if native:
        return g
    if not nuv:
        nuv = 2 if flags & 0x80 else 1 if flags & 0x04 else 0
    if flags & 0x08:  # prelit (цвета вершин)
        g.colors = [struct.unpack_from('<4B', b, o + i * 4) for i in range(nvert)]
        o += 4 * nvert
    if nuv:
        g.uvs = [struct.unpack_from('<2f', b, o + i * 8) for i in range(nvert)]
        o += 8 * nvert * nuv
    for i in range(ntri):
        v2, v1, mat, v3 = struct.unpack_from('<4H', b, o + i * 8)
        g.tris.append((v1, v2, v3, mat))
    o += 8 * ntri
    o += 16  # bounding sphere
    has_v, has_n = struct.unpack_from('<II', b, o)
    o += 8
    if has_v:
        g.verts = [struct.unpack_from('<3f', b, o + i * 12) for i in range(nvert)]
        o += 12 * nvert
    if has_n:
        g.normals = [struct.unpack_from('<3f', b, o + i * 12) for i in range(nvert)]
    ml = find(b, st[1], e, T_MATLIST)
    if ml:
        mst = find(b, ml[0], ml[1], T_STRUCT)
        nm = struct.unpack_from('<i', b, mst[0])[0]
        idx = struct.unpack_from(f'<{nm}i', b, mst[0] + 4)
        mats = [parse_material(b, cs, ce) for ct, cs, ce, _ in chunks(b, mst[1], ml[1]) if ct == T_MATERIAL]
        # -1 — следующий материал из списка, иначе ссылка на уже встреченный номер
        res, u = [], 0
        for i in idx:
            if i < 0:
                res.append(mats[u] if u < len(mats) else Material((255, 255, 255, 255), None))
                u += 1
            else:
                res.append(res[i] if i < len(res) else Material((255, 255, 255, 255), None))
        g.materials = res
    return g


def load(path):
    b = open(path, 'rb').read()
    clump = find(b, 0, len(b), T_CLUMP)
    s, e, _ = clump
    fl = find(b, s, e, T_FRAMELIST)
    frames = parse_frames(b, fl[0], fl[1])
    gl = find(b, s, e, T_GEOMLIST)
    geoms = [parse_geometry(b, cs, ce) for ct, cs, ce, _ in chunks(b, gl[0], gl[1]) if ct == T_GEOMETRY]
    atomics = []
    for ct, cs, ce, _ in chunks(b, s, e):
        if ct == T_ATOMIC:
            ast = find(b, cs, ce, T_STRUCT)
            fi, gi = struct.unpack_from('<ii', b, ast[0])
            atomics.append((fi, gi))
    return frames, geoms, atomics


def world_matrix(frames, i):
    """Матрица узла в координатах модели (4x4, строки), с учётом родителей."""
    import math
    def local(f):
        r = f.rot
        return [[r[0], r[3], r[6], f.pos[0]], [r[1], r[4], r[7], f.pos[1]], [r[2], r[5], r[8], f.pos[2]], [0, 0, 0, 1]]
    def mul(a, c):
        return [[sum(a[i][k] * c[k][j] for k in range(4)) for j in range(4)] for i in range(4)]
    m = local(frames[i])
    p = frames[i].parent
    guard = 0
    while p >= 0 and guard < 64:
        m = mul(local(frames[p]), m)
        p = frames[p].parent
        guard += 1
    return m

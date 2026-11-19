"""Minimal RenderWare 3.6 (GTA San Andreas) writer: DFF clumps with embedded
COL3 collision, and D3D9 texture dictionaries (TXD) with DXT1/DXT5 mipmaps.

Pure Python + numpy, no Blender dependency, so it can be unit-tested alone.
"""
import struct
import numpy as np

RW_VERSION = 0x1803FFFF  # 3.6.0.3, what SA PC and mobile ship with

# chunk ids
STRUCT, STRING, EXTENSION = 0x01, 0x02, 0x03
TEXTURE, MATERIAL, MATLIST = 0x06, 0x07, 0x08
FRAMELIST, GEOMETRY, CLUMP, ATOMIC = 0x0E, 0x0F, 0x10, 0x14
TEXNATIVE, TEXDICT, GEOMLIST = 0x15, 0x16, 0x1A
MATFX, BINMESH = 0x120, 0x50E
SPECULAR_MAT, REFLECTION_MAT = 0x253F2F6, 0x253F2FC
COLLISION, FRAME_NAME = 0x253F2FA, 0x253F2FE


def chunk(cid, payload=b""):
    return struct.pack("<III", cid, len(payload), RW_VERSION) + payload


def rw_string(s):
    b = s.encode("ascii") + b"\0"
    b += b"\0" * (-len(b) % 4)
    return chunk(STRING, b)


# --------------------------------------------------------------------------
# DFF
# --------------------------------------------------------------------------
class Frame:
    def __init__(self, name, parent=-1, pos=(0, 0, 0), rot=None):
        self.name, self.parent, self.pos = name, parent, pos
        # rows: right, up(forward in GTA terms), at  -> stored as 3 column vectors
        self.rot = rot if rot is not None else ((1, 0, 0), (0, 1, 0), (0, 0, 1))


class Material:
    def __init__(self, color=(255, 255, 255, 255), texture=None, env=0.0,
                 spec=0.0, reflect=0.0, ambient=1.0, diffuse=1.0):
        self.color, self.texture = tuple(int(c) for c in color), texture
        self.env, self.spec, self.reflect = env, spec, reflect
        self.ambient, self.diffuse = ambient, diffuse

    def key(self):
        return (self.color, self.texture, self.env, self.spec, self.reflect)


class Geometry:
    """Triangle list. verts (N,3) normals (N,3) uvs (N,2) tris (M,3) mat_ids (M,)"""

    def __init__(self, verts, normals, uvs, tris, mat_ids, materials):
        self.verts = np.asarray(verts, np.float32)
        self.normals = np.asarray(normals, np.float32)
        self.uvs = np.asarray(uvs, np.float32)
        self.tris = np.asarray(tris, np.int64)
        self.mat_ids = np.asarray(mat_ids, np.int64)
        self.materials = materials
        if len(self.verts) > 65535:
            raise ValueError("geometry has %d verts (>65535)" % len(self.verts))


def _texture_chunk(name, filt=0x06, wrap=1):
    flags = filt | (wrap << 8) | (wrap << 12) | 0x10000  # 0x10000: has mipmaps
    return chunk(TEXTURE, chunk(STRUCT, struct.pack("<I", flags)) +
                 rw_string(name) + rw_string("") + chunk(EXTENSION))


def _material_chunk(m):
    textured = 1 if m.texture else 0
    st = struct.pack("<I4BII3f", 0, *m.color, 0, textured,
                     m.ambient, 1.0, m.diffuse)
    body = chunk(STRUCT, st)
    if textured:
        body += _texture_chunk(m.texture)
    ext = b""
    if m.env > 0:
        # MatFX env map using SA's stock vehicle environment texture
        fx = struct.pack("<II", 2, 2) + struct.pack("<fII", m.env, 0, 1)
        fx += _texture_chunk("xvehicleenv128", 0x06, 1)
        fx += struct.pack("<I", 0)
        ext += chunk(MATFX, fx)
    if m.reflect > 0:
        ext += chunk(REFLECTION_MAT, struct.pack("<5fI", 1, 1, 0, 0, m.reflect, 0))
    if m.spec > 0:
        ext += chunk(SPECULAR_MAT, struct.pack("<f", m.spec) + b"\0" * 24)
    return chunk(MATERIAL, body + chunk(EXTENSION, ext))


def _geometry_chunk(g):
    flags = 0x02 | 0x04 | 0x10 | 0x20 | 0x40 | (1 << 16)
    nv, nt = len(g.verts), len(g.tris)
    st = struct.pack("<IIII", flags, nt, nv, 1)
    uv = g.uvs.copy()
    uv[:, 1] = 1.0 - uv[:, 1]  # RW uses top-left origin
    st += uv.astype("<f4").tobytes()
    tri = np.empty((nt, 4), "<u2")
    tri[:, 0] = g.tris[:, 1]
    tri[:, 1] = g.tris[:, 0]
    tri[:, 2] = g.tris[:, 2]
    tri[:, 3] = g.mat_ids
    st += tri.tobytes()
    lo, hi = g.verts.min(0), g.verts.max(0)
    c = (lo + hi) / 2
    r = float(np.linalg.norm(g.verts - c, axis=1).max())
    st += struct.pack("<4fII", *c, r, 1, 1)
    st += g.verts.astype("<f4").tobytes() + g.normals.astype("<f4").tobytes()
    body = chunk(STRUCT, st)
    nm = len(g.materials)
    ml = chunk(STRUCT, struct.pack("<I", nm) + struct.pack("<%di" % nm, *([-1] * nm)))
    for m in g.materials:
        ml += _material_chunk(m)
    body += chunk(MATLIST, ml)
    # BinMesh PLG: one split per material
    splits = b""
    used = 0
    total = 0
    for mi in range(nm):
        idx = g.tris[g.mat_ids == mi].reshape(-1)
        if not len(idx):
            continue
        used += 1
        total += len(idx)
        splits += struct.pack("<II", len(idx), mi) + idx.astype("<u4").tobytes()
    binmesh = chunk(BINMESH, struct.pack("<III", 0, used, total) + splits)
    return chunk(GEOMETRY, body + chunk(EXTENSION, binmesh))


def write_dff(path, frames, atomics, col=None):
    """frames: list[Frame]; atomics: list[(frame_index, Geometry)]; col: bytes"""
    fl = struct.pack("<I", len(frames))
    for f in frames:
        r = f.rot
        fl += struct.pack("<9f3fiI", *r[0], *r[1], *r[2], *f.pos, f.parent, 0)
    fl = chunk(STRUCT, fl)
    for f in frames:
        fl += chunk(EXTENSION, chunk(FRAME_NAME, f.name.encode("ascii")))
    out = chunk(STRUCT, struct.pack("<III", len(atomics), 0, 0))
    out += chunk(FRAMELIST, fl)
    gl = chunk(STRUCT, struct.pack("<I", len(atomics)))
    for _, g in atomics:
        gl += _geometry_chunk(g)
    out += chunk(GEOMLIST, gl)
    for gi, (fi, g) in enumerate(atomics):
        a = chunk(STRUCT, struct.pack("<IIII", fi, gi, 5, 0))
        has_fx = any(m.env > 0 for m in g.materials)
        a += chunk(EXTENSION, chunk(MATFX, struct.pack("<I", 1)) if has_fx else b"")
        out += chunk(ATOMIC, a)
    out += chunk(EXTENSION, chunk(COLLISION, col) if col else b"")
    data = chunk(CLUMP, out)
    with open(path, "wb") as fh:
        fh.write(data)
    return len(data)


# --------------------------------------------------------------------------
# COL3 (embedded vehicle collision)
# --------------------------------------------------------------------------
SURF_CAR, SURF_PANEL = 63, 64


def build_col3(name, spheres, boxes, verts=(), faces=(), model_id=0):
    """spheres: [(cx,cy,cz,r,surf)], boxes: [(min3,max3,surf)],
    verts: [(x,y,z)] faces: [(a,b,c,surf)]"""
    pts = [np.array(s[:3]) + d * s[3] for s in spheres for d in (-1, 1)]
    pts += [np.array(b[0]) for b in boxes] + [np.array(b[1]) for b in boxes]
    pts += [np.array(v) for v in verts]
    pts = np.array(pts)
    lo, hi = pts.min(0), pts.max(0)
    c = (lo + hi) / 2
    rad = float(np.linalg.norm(pts - c, axis=1).max())
    head_len = 4 + 4 + 22 + 2 + 40 + 2 + 2 + 4 + 4 + 4 + 6 * 4 + 12
    body = b""
    off = head_len - 4  # offsets are counted from the size field (abs - 4)
    off_sph = off
    sph = b"".join(struct.pack("<4f4B", *s[:4], s[4], 0, 0, 255) for s in spheres)
    off += len(sph)
    off_box = off
    box = b"".join(struct.pack("<6f4B", *b[0], *b[1], b[2], 0, 0, 255) for b in boxes)
    off += len(box)
    off_v = off
    vb = b"".join(struct.pack("<3h", *(int(round(x * 128)) for x in v)) for v in verts)
    vb += b"\0" * (-len(vb) % 4)
    off += len(vb)
    off_f = off
    fb = b"".join(struct.pack("<3H2B", f[0], f[1], f[2], f[3], 0) for f in faces)
    off += len(fb)
    body = sph + box + vb + fb
    flags = 2 if (spheres or boxes or faces) else 0
    nm = name.encode("ascii")[:21]
    hdr = nm + b"\0" * (22 - len(nm))
    hdr += struct.pack("<H", model_id)
    hdr += struct.pack("<3f3f3ff", *lo, *hi, *c, rad)
    hdr += struct.pack("<HHIB3xI", len(spheres), len(boxes), len(faces), 0, flags)
    hdr += struct.pack("<6I", off_sph, off_box, 0,
                       off_v if verts else 0, off_f if faces else 0, 0)
    hdr += struct.pack("<3I", 0, 0, 0)  # shadow mesh: none
    assert 8 + len(hdr) == head_len, (len(hdr), head_len)
    payload = hdr + body
    return b"COL3" + struct.pack("<I", len(payload)) + payload


# --------------------------------------------------------------------------
# DXT compression (simple bounding-box fit, vectorised)
# --------------------------------------------------------------------------
def _to565(c):
    c = np.clip(np.rint(c), 0, 255).astype(np.uint32)
    return ((c[..., 0] >> 3) << 11) | ((c[..., 1] >> 2) << 5) | (c[..., 2] >> 3)


def _from565(v):
    r = ((v >> 11) & 31) * 255 / 31
    g = ((v >> 5) & 63) * 255 / 63
    b = (v & 31) * 255 / 31
    return np.stack([r, g, b], -1).astype(np.float32)


def _blocks(img):
    h, w = img.shape[:2]
    ph, pw = (-h) % 4, (-w) % 4
    if ph or pw:
        img = np.pad(img, ((0, ph), (0, pw), (0, 0)), mode="edge")
    h, w = img.shape[:2]
    return img.reshape(h // 4, 4, w // 4, 4, -1).transpose(0, 2, 1, 3, 4).reshape(-1, 16, img.shape[2])


def _color_block(rgb):
    rgb = rgb.astype(np.float32)
    mean = rgb.mean(1, keepdims=True)
    d = rgb - mean
    # principal axis via a few power iterations
    cov = np.einsum("nki,nkj->nij", d, d)
    v = np.ones((len(rgb), 3), np.float32)
    for _ in range(4):
        v = np.einsum("nij,nj->ni", cov, v)
        v /= np.linalg.norm(v, axis=1, keepdims=True) + 1e-8
    t = np.einsum("nki,ni->nk", d, v)
    c0 = mean[:, 0] + v * t.max(1, keepdims=True)
    c1 = mean[:, 0] + v * t.min(1, keepdims=True)
    e0, e1 = _to565(c0), _to565(c1)
    swap = e0 < e1
    e0, e1 = np.where(swap, e1, e0), np.where(swap, e0, e1)
    eq = e0 == e1
    e0 = np.where(eq & (e0 < 0xFFFF), e0 + 1, e0)
    e1 = np.where(eq & (e0 == 0xFFFF), e1 - 1, e1)
    p0, p1 = _from565(e0), _from565(e1)
    pal = np.stack([p0, p1, (2 * p0 + p1) / 3, (p0 + 2 * p1) / 3], 1)
    dist = ((rgb[:, :, None, :] - pal[:, None, :, :]) ** 2).sum(-1)
    idx = dist.argmin(2).astype(np.uint32)
    bits = (idx << (2 * np.arange(16, dtype=np.uint32))).sum(1).astype(np.uint32)
    out = np.empty((len(rgb), 2), "<u4")
    out[:, 0] = e0 | (e1 << 16)
    out[:, 1] = bits
    return out


def _alpha_block(a):
    a = a.astype(np.float32)
    a0, a1 = a.max(1), a.min(1)
    a1 = np.where(a0 == a1, np.maximum(a0 - 1, 0), a1)
    a0 = np.where(a0 == a1, a1 + 1, a0)
    pal = np.stack([a0, a1] + [((7 - i) * a0 + i * a1) / 7 for i in range(1, 7)], 1)
    idx = np.abs(a[:, :, None] - pal[:, None, :]).argmin(2).astype(np.uint64)
    bits = (idx << (3 * np.arange(16, dtype=np.uint64))).sum(1)
    out = np.zeros((len(a), 8), np.uint8)
    out[:, 0] = a0
    out[:, 1] = a1
    for i in range(6):
        out[:, 2 + i] = (bits >> np.uint64(8 * i)) & np.uint64(255)
    return out


def dxt_compress(img, alpha):
    b = _blocks(img)
    col = _color_block(b[..., :3]).view(np.uint8).reshape(-1, 8)
    if not alpha:
        return col.tobytes()
    al = _alpha_block(b[..., 3])
    return np.concatenate([al, col], 1).tobytes()


def _mips(img):
    out = [img]
    while min(img.shape[:2]) > 4:
        h, w = img.shape[0] // 2, img.shape[1] // 2
        img = img[:h * 2, :w * 2].reshape(h, 2, w, 2, -1).astype(np.float32).mean((1, 3))
        img = np.clip(np.rint(img), 0, 255).astype(np.uint8)
        out.append(img)
    return out


def texture_native(name, rgba, alpha=None, compress=True, wrap=1):
    """rgba: uint8 (H,W,4) array, power-of-two sizes."""
    rgba = np.asarray(rgba, np.uint8)
    if alpha is None:
        alpha = bool((rgba[..., 3] < 250).any())
    h, w = rgba.shape[:2]
    levels = _mips(rgba)
    if compress:
        fourcc = b"DXT5" if alpha else b"DXT1"
        raster = (0x300 if alpha else 0x200) | 0x8000
        depth = 16
        datas = [dxt_compress(l, alpha) for l in levels]
        fmt = struct.unpack("<I", fourcc)[0]
        flags = (1 if alpha else 0) | 8
    else:
        raster = 0x500 | 0x8000
        depth = 32
        fmt = 21  # D3DFMT_A8R8G8B8
        datas = [l[..., [2, 1, 0, 3]].tobytes() for l in levels]
        flags = 1 if alpha else 0
    nm = name.encode("ascii")[:31]
    st = struct.pack("<II", 9, 0x06 | (wrap << 8) | (wrap << 12))
    st += nm + b"\0" * (32 - len(nm)) + b"\0" * 32
    st += struct.pack("<IIHHBBBB", raster, fmt, w, h, depth, len(levels), 4, flags)
    for d in datas:
        st += struct.pack("<I", len(d)) + d
    return chunk(TEXNATIVE, chunk(STRUCT, st) + chunk(EXTENSION))


def write_txd(path, textures):
    """textures: list of (name, rgba ndarray[, alpha])"""
    body = chunk(STRUCT, struct.pack("<HH", len(textures), 2))
    for t in textures:
        body += texture_native(*t)
    data = chunk(TEXDICT, body + chunk(EXTENSION))
    with open(path, "wb") as fh:
        fh.write(data)
    return len(data)


# --------------------------------------------------------------------------
# Reader used by the self-check: walks a chunk tree
# --------------------------------------------------------------------------
def walk(data, off=0, end=None, depth=0, out=None):
    out = [] if out is None else out
    end = len(data) if end is None else end
    containers = {CLUMP, FRAMELIST, GEOMLIST, GEOMETRY, MATLIST, MATERIAL,
                  TEXTURE, ATOMIC, EXTENSION, TEXDICT, TEXNATIVE}
    while off + 12 <= end:
        cid, size, ver = struct.unpack_from("<III", data, off)
        if off + 12 + size > end:
            raise ValueError("chunk 0x%x at %d overruns parent" % (cid, off))
        out.append((depth, cid, size))
        if cid in containers:
            walk(data, off + 12, off + 12 + size, depth + 1, out)
        off += 12 + size
    if off != end:
        raise ValueError("trailing bytes at %d (end %d)" % (off, end))
    return out

"""Small numpy mesh toolkit used by the vehicle generator.

A Mesh holds polygons (tris or quads), per-corner UVs and a material name per
face.  Coordinates follow GTA: x right, y forward, z up, metres.
"""
import math
import numpy as np


class Mesh:
    def __init__(self):
        self.v = np.zeros((0, 3))
        self.f = []          # list of index tuples
        self.uv = []         # list of tuples of (u, v) per corner
        self.mat = []        # material name per face

    # ------------------------------------------------------------ building
    def add(self, verts, faces, uvs, mat):
        """faces: (F,k) array or list of tuples; uvs: same layout of (u,v)."""
        base = len(self.v)
        self.v = np.vstack([self.v, np.asarray(verts, float).reshape(-1, 3)])
        if isinstance(mat, str):
            mat = [mat] * len(faces)
        for fc, uc, m in zip(faces, uvs, mat):
            self.f.append(tuple(int(i) + base for i in fc))
            self.uv.append(tuple((float(a), float(b)) for a, b in uc))
            self.mat.append(m)
        return self

    def extend(self, other):
        base = len(self.v)
        self.v = np.vstack([self.v, other.v])
        self.f += [tuple(i + base for i in fc) for fc in other.f]
        self.uv += list(other.uv)
        self.mat += list(other.mat)
        return self

    def copy(self):
        m = Mesh()
        m.v = self.v.copy()
        m.f, m.uv, m.mat = list(self.f), list(self.uv), list(self.mat)
        return m

    def transformed(self, M=None, t=(0, 0, 0)):
        m = self.copy()
        if M is not None:
            m.v = m.v @ np.asarray(M).T
            if np.linalg.det(M) < 0:
                m.flip()
        m.v = m.v + np.asarray(t)
        return m

    def flip(self):
        self.f = [tuple(reversed(fc)) for fc in self.f]
        self.uv = [tuple(reversed(u)) for u in self.uv]
        return self

    def mirrored_x(self, flip_u=False):
        m = self.transformed(np.diag([-1, 1, 1]))
        if flip_u:
            m.uv = [tuple((1 - a, b) for a, b in u) for u in m.uv]
        return m

    def set_mat(self, name):
        self.mat = [name] * len(self.f)
        return self

    def remap_mat(self, table):
        self.mat = [table.get(m, m) for m in self.mat]
        return self

    def subset(self, keep):
        """New mesh with faces where keep[i] is True (vertices compacted)."""
        idx = [i for i, k in enumerate(keep) if k]
        used = sorted({j for i in idx for j in self.f[i]})
        remap = {o: n for n, o in enumerate(used)}
        m = Mesh()
        m.v = self.v[used] if used else np.zeros((0, 3))
        m.f = [tuple(remap[j] for j in self.f[i]) for i in idx]
        m.uv = [self.uv[i] for i in idx]
        m.mat = [self.mat[i] for i in idx]
        return m

    # ------------------------------------------------------------ queries
    def tris(self):
        """Triangulated arrays: corner positions index, uvs, mat per tri."""
        T, U, M = [], [], []
        for fc, uc, m in zip(self.f, self.uv, self.mat):
            for k in range(1, len(fc) - 1):
                T.append((fc[0], fc[k], fc[k + 1]))
                U.append((uc[0], uc[k], uc[k + 1]))
                M.append(m)
        return np.array(T, int).reshape(-1, 3), np.array(U, float).reshape(-1, 3, 2), M

    def face_normals(self):
        T, _, _ = self.tris()
        return T

    def bounds(self):
        return self.v.min(0), self.v.max(0)

    def tri_count(self):
        return sum(len(f) - 2 for f in self.f)


def corner_normals(verts, tris, angle=40.0):
    """Smooth normals per triangle corner, split where faces bend more than
    `angle` degrees.  Returns (T,3,3)."""
    a, b, c = verts[tris[:, 0]], verts[tris[:, 1]], verts[tris[:, 2]]
    fn = np.cross(b - a, c - a)
    area = np.linalg.norm(fn, axis=1)
    nf = fn / (area[:, None] + 1e-12)
    # weld positions so that seams in UV do not break smoothing
    key = np.round(verts * 1e4).astype(np.int64)
    _, vid = np.unique(key, axis=0, return_inverse=True)
    vid = vid.reshape(-1)
    cv = vid[tris].reshape(-1)            # corner -> welded vertex
    cf = np.repeat(np.arange(len(tris)), 3)
    order = np.argsort(cv, kind="stable")
    cv_s, cf_s = cv[order], cf[order]
    starts = np.searchsorted(cv_s, np.arange(vid.max() + 1))
    ends = np.searchsorted(cv_s, np.arange(vid.max() + 1), side="right")
    deg = ends - starts
    # pairs (corner, neighbour face)
    rep = deg[cv]
    pc = np.repeat(np.arange(len(cv)), rep)
    offs = np.arange(len(pc)) - np.repeat(np.cumsum(rep) - rep, rep)
    pg = cf_s[np.repeat(starts[cv], rep) + offs]
    my = cf[pc]
    ok = (nf[my] * nf[pg]).sum(1) > math.cos(math.radians(angle))
    acc = np.zeros((len(cv), 3))
    np.add.at(acc, pc[ok], fn[pg[ok]])
    n = acc / (np.linalg.norm(acc, axis=1, keepdims=True) + 1e-12)
    bad = np.linalg.norm(acc, axis=1) < 1e-12
    n[bad] = np.repeat(nf, 3, 0)[bad]
    return n.reshape(-1, 3, 3)


def unique_vertices(verts, tris, uvs, normals):
    """Split into a vertex buffer keyed by (pos, normal, uv)."""
    P = verts[tris].reshape(-1, 3)
    N = normals.reshape(-1, 3)
    U = uvs.reshape(-1, 2)
    key = np.hstack([np.round(P * 1e4), np.round(N * 1e3), np.round(U * 1e4)]).astype(np.int64)
    _, first, inv = np.unique(key, axis=0, return_index=True, return_inverse=True)
    return P[first], N[first], U[first], inv.reshape(-1, 3)


# ---------------------------------------------------------------- primitives
def grid_mesh(P, uv, mat, closed_u=False, flip=False):
    """P: (n,m,3) point grid -> quads. uv: (n,m,2). mat: str or (n-1,m-1) names."""
    n, m = P.shape[:2]
    out = Mesh()
    idx = np.arange(n * m).reshape(n, m)
    faces, uvs, mats = [], [], []
    rng_j = range(m) if closed_u else range(m - 1)
    for i in range(n - 1):
        for j in rng_j:
            j2 = (j + 1) % m
            fc = (idx[i, j], idx[i + 1, j], idx[i + 1, j2], idx[i, j2])
            uc = [uv[i, j], uv[i + 1, j], uv[i + 1, j2], uv[i, j2]]
            if closed_u and j2 == 0:
                uc[2] = (uv[i + 1, j2][0] + 1 if uv[i + 1, j2][0] < uv[i + 1, j][0] else uv[i + 1, j2][0], uv[i + 1, j2][1])
                uc[3] = (uv[i, j2][0] + 1 if uv[i, j2][0] < uv[i, j][0] else uv[i, j2][0], uv[i, j2][1])
            if flip:
                fc, uc = fc[::-1], uc[::-1]
            faces.append(fc)
            uvs.append(uc)
            mats.append(mat if isinstance(mat, str) else mat[i][min(j, m - 2)])
    out.add(P.reshape(-1, 3), faces, uvs, mats)
    return out


def lathe(profile, segments, mat, axis="x", u_scale=1.0, v_coords=None, angle0=0.0, arc=2 * math.pi, cap=False):
    """Revolve profile [(r, a)] around `axis` ('x' for wheels).
    u = angle fraction, v = profile parameter."""
    prof = np.asarray(profile, float)
    k = len(prof)
    closed = abs(arc - 2 * math.pi) < 1e-9
    nseg = segments if closed else segments + 1
    th = angle0 + np.arange(nseg) / segments * arc
    if v_coords is None:
        d = np.r_[0, np.cumsum(np.linalg.norm(np.diff(prof, axis=0), axis=1))]
        v_coords = d / max(d[-1], 1e-9)
    P = np.zeros((k, nseg, 3))
    r, a = prof[:, 0][:, None], prof[:, 1][:, None]
    c, s = np.cos(th)[None, :], np.sin(th)[None, :]
    if axis == "x":
        P[..., 0], P[..., 1], P[..., 2] = a, r * c, r * s
    elif axis == "y":
        P[..., 0], P[..., 1], P[..., 2] = r * c, a, r * s
    else:
        P[..., 0], P[..., 1], P[..., 2] = r * c, r * s, a
    UV = np.zeros((k, nseg, 2))
    UV[..., 0] = (np.arange(nseg) / segments)[None, :] * u_scale
    UV[..., 1] = np.asarray(v_coords)[:, None]
    return grid_mesh(P, UV, mat, closed_u=closed)


def box(lo, hi, mat, uv_scale=1.0):
    lo, hi = np.asarray(lo, float), np.asarray(hi, float)
    x0, y0, z0 = lo
    x1, y1, z1 = hi
    V = [(x0, y0, z0), (x1, y0, z0), (x1, y1, z0), (x0, y1, z0),
         (x0, y0, z1), (x1, y0, z1), (x1, y1, z1), (x0, y1, z1)]
    F = [(0, 3, 2, 1), (4, 5, 6, 7), (0, 1, 5, 4), (2, 3, 7, 6), (1, 2, 6, 5), (3, 0, 4, 7)]
    m = Mesh()
    uvs = []
    Va = np.array(V)
    for fc in F:
        p = Va[list(fc)]
        nrm = np.cross(p[1] - p[0], p[2] - p[0])
        ax = np.argmax(np.abs(nrm))
        ij = [i for i in range(3) if i != ax]
        uvs.append([(q[ij[0]] * uv_scale, q[ij[1]] * uv_scale) for q in p])
    m.add(V, F, uvs, mat)
    return m


def superellipsoid(size, center, mat, n=(24, 12), p=4.0, uv_scale=1.0):
    """Rounded box (superellipsoid with exponent p) - used for seats, mirrors, etc."""
    sx, sy, sz = np.asarray(size) / 2
    nu, nv = n
    th = np.linspace(-math.pi / 2, math.pi / 2, nv + 1)
    ph = np.linspace(-math.pi, math.pi, nu + 1)
    def sgnpow(x, e):
        return np.sign(x) * np.abs(x) ** e
    e = 2.0 / p
    T, Ph = np.meshgrid(th, ph, indexing="ij")
    X = sx * sgnpow(np.cos(T), e) * sgnpow(np.cos(Ph), e)
    Y = sy * sgnpow(np.cos(T), e) * sgnpow(np.sin(Ph), e)
    Z = sz * sgnpow(np.sin(T), e)
    P = np.stack([X, Y, Z], -1) + np.asarray(center)
    UV = np.stack([np.broadcast_to((ph / (2 * math.pi) + 0.5)[None, :], T.shape) * uv_scale,
                   (T / math.pi + 0.5) * uv_scale], -1)
    m = grid_mesh(P, UV, mat)
    # drop degenerate pole quads' duplicate verts is not necessary for rendering
    return m


def cylinder(r, h, center, axis, mat, seg=16, cap=True):
    prof = [(0.0, -h / 2), (r, -h / 2), (r, h / 2), (0.0, h / 2)] if cap else [(r, -h / 2), (r, h / 2)]
    m = lathe(prof, seg, mat, axis=axis)
    return m.transformed(t=center)


def torus(R, r, center, axis, mat, seg=(32, 10)):
    prof = [(R + r * math.cos(a), r * math.sin(a)) for a in np.linspace(0, 2 * math.pi, seg[1] + 1)]
    m = lathe(prof, seg[0], mat, axis=axis, u_scale=4)
    return m.transformed(t=center)


def rot_x(a):
    c, s = math.cos(a), math.sin(a)
    return np.array([[1, 0, 0], [0, c, -s], [0, s, c]])


def rot_y(a):
    c, s = math.cos(a), math.sin(a)
    return np.array([[c, 0, s], [0, 1, 0], [-s, 0, c]])


def rot_z(a):
    c, s = math.cos(a), math.sin(a)
    return np.array([[c, -s, 0], [s, c, 0], [0, 0, 1]])


def smooth_curve(ctrl, n, closed=False):
    """Catmull-Rom through ctrl points (k,d) resampled to n points by arc length."""
    P = np.asarray(ctrl, float)
    if closed:
        P = np.vstack([P[-1], P, P[0], P[1]])
    else:
        P = np.vstack([2 * P[0] - P[1], P, 2 * P[-1] - P[-2]])
    pts = []
    for i in range(1, len(P) - 2):
        p0, p1, p2, p3 = P[i - 1], P[i], P[i + 1], P[i + 2]
        for t in np.linspace(0, 1, 24, endpoint=False):
            t2, t3 = t * t, t * t * t
            pts.append(0.5 * ((2 * p1) + (-p0 + p2) * t + (2 * p0 - 5 * p1 + 4 * p2 - p3) * t2 + (-p0 + 3 * p1 - 3 * p2 + p3) * t3))
    pts.append(P[-2])
    pts = np.array(pts)
    d = np.r_[0, np.cumsum(np.linalg.norm(np.diff(pts, axis=0), axis=1))]
    s = np.linspace(0, d[-1], n)
    return np.stack([np.interp(s, d, pts[:, k]) for k in range(pts.shape[1])], 1)


def profile_fn(pts):
    """Smooth 1-D function from (t, value) control points (monotone t)."""
    P = np.asarray(pts, float)
    dense = smooth_curve(P, 400)
    order = np.argsort(dense[:, 0])
    dt, dv = dense[order, 0], dense[order, 1]
    return lambda t: np.interp(t, dt, dv)

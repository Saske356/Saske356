"""Parametric car body: a loft of cross-sections along the car.

The body is generated as a grid  P[station, section_point]  for the right
half and mirrored.  Every grid face is classified into a part (chassis,
doors, bonnet, boot, bumpers, windscreen) and a material slot (paint, glass,
trim...).  Splitting along grid lines keeps panel edges exact; small gaps
and inward flanges are added afterwards so the panels read as separate.
"""
import math
import numpy as np
from mesh import Mesh, profile_fn, smooth_curve
import tex

# section control-point indices (resampled counts per segment)
SEG = [3, 2, 6, 6, 2, 2, 8, 3, 6]   # C0..C9 -> 9 segments


def smoothstep(e0, e1, x):
    t = np.clip((x - e0) / (e1 - e0 + 1e-9), 0, 1)
    return t * t * (3 - 2 * t)


def cr_segments(ctrl, counts):
    """Catmull-Rom through ctrl (k,2), `counts[i]` samples on segment i.
    Returns points and the index where each control point lands."""
    P = np.asarray(ctrl, float)
    E = np.vstack([2 * P[0] - P[1], P, 2 * P[-1] - P[-2]])
    out, marks = [], []
    for i in range(len(P) - 1):
        p0, p1, p2, p3 = E[i], E[i + 1], E[i + 2], E[i + 3]
        marks.append(len(out))
        for t in np.linspace(0, 1, counts[i], endpoint=False):
            t2, t3 = t * t, t * t * t
            out.append(0.5 * ((2 * p1) + (-p0 + p2) * t + (2 * p0 - 5 * p1 + 4 * p2 - p3) * t2 + (-p0 + 3 * p1 - 3 * p2 + p3) * t3))
    marks.append(len(out))
    out.append(P[-1])
    return np.array(out), marks


class Body:
    def __init__(self, p, low=False):
        self.p = p
        self.seg = [max(1, (c + 1) // 2) for c in SEG] if low else SEG
        if low:
            p = dict(p, stations=28)
            self.p = p
        L = p["len"]
        self.z_top = profile_fn(p["z_top"])
        self.z_belt = profile_fn(p["z_belt"])
        self.z_sill = profile_fn(p["z_sill"])
        self.w_sh = profile_fn(p["w_sh"])
        self.w_bot = profile_fn(p["w_bot"])
        self.w_roof = profile_fn(p["w_roof"])
        self.L = L
        self.build_grid()

    # -------------------------------------------------------------- grid
    def stations(self):
        p, L = self.p, self.L
        rcf, rcr = p["corner_f"], p["corner_r"]
        st = []
        for f in (0.0, 0.3, 0.6, 0.85):          # rear cap: (ty, xscale)
            st.append((0.0, f))
        n_r = 6
        for k in range(1, n_r + 1):
            ty = rcr * (1 - math.cos(k / n_r * math.pi / 2))
            st.append((ty, None))
        n_mid = p.get("stations", 90)
        for ty in np.linspace(rcr, L - rcf, n_mid)[1:-1]:
            st.append((float(ty), None))
        for k in range(n_r, 0, -1):
            ty = L - rcf * (1 - math.cos(k / n_r * math.pi / 2))
            st.append((ty, None))
        for f in (0.85, 0.6, 0.3, 0.0):
            st.append((L, f))
        # insert exact split stations so panel edges fall on grid lines
        cuts = [c for c in p["cuts"] if 0 < c < L]
        tys = [s[0] for s in st]
        for c in cuts:
            j = int(np.argmin([abs(t - c) for t in tys]))
            if st[j][1] is None and 4 < j < len(st) - 5:
                st[j] = (c, None)
        st = sorted(st, key=lambda s: (s[0], 0 if s[0] == 0 else 0))
        # keep caps in order (rear caps ascending scale, front descending)
        rear = [s for s in st if s[0] == 0.0]
        front = [s for s in st if s[0] == L]
        mid = sorted([s for s in st if 0 < s[0] < L])
        rear = sorted(rear, key=lambda s: s[1] if s[1] is not None else 1)
        front = sorted(front, key=lambda s: -(s[1] if s[1] is not None else 1))
        return rear + mid + front

    def plan_scale(self, ty):
        p, L = self.p, self.L
        rcf, rcr = p["corner_f"], p["corner_r"]
        W = float(self.w_sh(ty))
        if ty < rcr:
            d = rcr - ty
            return (W - rcr + math.sqrt(max(rcr * rcr - d * d, 0))) / W
        if ty > L - rcf:
            d = ty - (L - rcf)
            return (W - rcf + math.sqrt(max(rcf * rcf - d * d, 0))) / W
        return 1.0

    def arch_z(self, ty):
        p = self.p
        z = -1.0
        for yc in (p["axle_r"], p["axle_f"]):
            R = p["arch_r"]
            d = ty - yc
            if abs(d) < R:
                z = max(z, p["wheel_r"] + math.sqrt(R * R - d * d) * p.get("arch_squash", 1.0))
        return z

    def section(self, ty):
        p = self.p
        zt, zb, zs = float(self.z_top(ty)), float(self.z_belt(ty)), float(self.z_sill(ty))
        w, wb, wr = float(self.w_sh(ty)), float(self.w_bot(ty)), float(self.w_roof(ty))
        cab = p["cabin_h"]
        gh = float(smoothstep(0.02, cab, zt - zb))
        bulge = p.get("bulge", 0.02)
        za = self.arch_z(ty)
        lift = max(0.0, za - zs)
        zs2 = zs + lift
        zmid = zs + (zb - zs) * 0.45
        zmid = max(zmid, zs2 + 0.06)
        flare = p.get("flare", 0.0) * smoothstep(0.0, 0.05, lift) if lift > 0 else 0.0
        crown = p.get("crown", 0.05)
        wg = w - p.get("tumble", 0.10)
        C = [
            (0.0, zs2),
            (wb * 0.80, zs2),
            (wb, zs2 + 0.05),
            (w + bulge + flare, zmid),
            (w + flare * 0.5, zb - 0.04),
            (w - 0.035, zb + 0.01),
            (w - 0.035 - (0.05 + 0.25 * (1 - gh)) * (1 - gh) - (w - 0.035 - wg) * gh, zb + 0.02 + crown * 0.3 * (1 - gh)),
            (wr * gh + (w * 0.55) * (1 - gh), zt - 0.05 * gh - crown * 0.35 * (1 - gh)),
            (wr * 0.62 * gh + (w * 0.28) * (1 - gh), zt - 0.008 - crown * 0.08 * (1 - gh)),
            (0.0, zt),
        ]
        pts, marks = cr_segments(C, self.seg)
        return pts, marks, gh

    def build_grid(self):
        st = self.stations()
        rows, ys, scales = [], [], []
        for ty, cap in st:
            pts, marks, gh = self.section(ty)
            sc = self.plan_scale(ty) if cap is None else cap * self.plan_scale(ty - 1e-6 if ty > 0 else 1e-6)
            P = np.zeros((len(pts), 3))
            P[:, 0] = pts[:, 0] * sc
            P[:, 1] = ty
            P[:, 2] = pts[:, 1]
            rows.append(P)
            ys.append(ty)
            scales.append(cap)
        self.marks = marks
        G = np.array(rows)
        # front/rear rake: lean the end faces a bit for a less boxy look
        L = self.L
        for end, rake in ((0, self.p.get("rake_r", 0.08)), (1, self.p.get("rake_f", 0.12))):
            zt = G[..., 2]
            zl, zh = zt.min(), zt.max()
            ty = G[..., 1]
            w = smoothstep(L * 0.12, 0, ty) if end == 0 else smoothstep(L * 0.88, L, ty)
            hz = np.clip((zt - self.p["bumper_z"]) / (self.p["hood_front_z"] - self.p["bumper_z"] + 1e-6), 0, 1.4)
            sgn = 1 if end == 0 else -1
            G[..., 1] += sgn * rake * w * hz ** 1.6
            # tuck the bumper bottom a bit
            hb = np.clip((self.p["bumper_z"] - zt) / 0.25, 0, 1)
            G[..., 1] += sgn * 0.05 * w * hb ** 2
        self.G = G
        self.ty = np.array(ys)
        self.cap = scales

    # -------------------------------------------------------------- classify
    def classify(self):
        """Returns per-face (station i, section j) part & material arrays."""
        p = self.p
        n, m = self.G.shape[:2]
        mk = self.marks
        i_dbot, i_belt, i_glass, i_roof = mk[2] + 1, mk[5], mk[6], mk[7]
        part = np.full((n - 1, m - 1), "chassis", object)
        mat = np.full((n - 1, m - 1), "paint", object)
        tyc = (self.ty[:-1] + self.ty[1:]) / 2
        capf = np.array([c is not None for c in self.cap])
        is_cap = capf[:-1] | capf[1:]
        ws0, ws1, rw1, rw0 = p["ws0"], p["ws1"], p["rw1"], p["rw0"]
        doors = p["doors"]
        for i in range(n - 1):
            t = tyc[i]
            for j in range(m - 1):
                if j < mk[2] - 1:
                    mat[i, j] = "under"
                    continue
                side_glass = i_glass <= j < i_roof
                top = j >= i_roof
                if is_cap[i]:
                    continue
                if top:
                    if ws1 + 0.01 < t < ws0 - 0.01 and j > i_roof:
                        mat[i, j] = "glass"
                        part[i, j] = "windscreen"
                    elif rw0 + 0.01 < t < rw1 and j > i_roof:
                        mat[i, j] = "glass"
                    continue
                if side_glass:
                    sail = p.get("sail", 0.18)
                    if rw0 + p.get("cpillar", 0.12) < t < ws0 - sail and j < i_roof - 1:
                        mat[i, j] = "glass"
                        for (a, b) in p.get("bpillars", []):
                            if a < t < b:
                                mat[i, j] = "trim_gloss"
                    elif j == i_roof - 1 and rw0 < t < ws0:
                        mat[i, j] = "paint" if p.get("body_pillars", False) else "trim_gloss"
                for name, (a, b) in doors.items():
                    if a < t < b and i_dbot <= j < i_roof:
                        part[i, j] = name
                if p["hood"][0] < t < p["hood"][1] and j >= i_belt + 1:
                    part[i, j] = "bonnet"
                if p["boot"][0] < t < p["boot"][1] and j >= i_belt + 1:
                    part[i, j] = "boot"
            # bumpers: everything in the end zones below the bumper line
        zc = (self.G[:-1, :-1, 2] + self.G[1:, 1:, 2]) / 2
        bz = p["bumper_top"]

        def row_for(z, ty):
            i = int(np.argmin(np.abs(self.ty - ty)))
            col = self.G[i, :, 2]
            js = [j for j in range(mk[2], i_glass) if col[j] <= z]
            return (max(js) if js else mk[2]) + 1
        jf = row_for(bz[1], p["bump_f"] + 0.05)
        jr = row_for(bz[0], p["bump_r"] - 0.05)
        for i in range(n - 1):
            for j in range(m - 1):
                if mat[i, j] == "under":
                    if is_cap[i]:
                        mat[i, j] = "paint"
                    else:
                        continue
                front = tyc[i] > self.L / 2
                if is_cap[i] or tyc[i] >= p["bump_f"] or tyc[i] <= p["bump_r"]:
                    if front and (tyc[i] >= p["bump_f"] or is_cap[i]) and j < jf:
                        part[i, j] = "bump_front"
                    elif not front and (tyc[i] <= p["bump_r"] or is_cap[i]) and j < jr:
                        part[i, j] = "bump_rear"
        self.j_bump = (jr, jf)
        # black frit band around glass
        g = mat == "glass"
        frit = np.zeros_like(g)
        frit[1:, :] |= g[:-1, :]
        frit[:-1, :] |= g[1:, :]
        frit[:, 1:] |= g[:, :-1]
        frit[:, :-1] |= g[:, 1:]
        frit &= (mat == "paint") & (part != "chassis") | ((mat == "paint") & frit)
        # keep frit only where the neighbour glass is on the top band or windscreen
        self.part, self.mat = part, mat
        self.frit = frit & ~g
        return part, mat

    # -------------------------------------------------------------- uv
    def uv_grid(self):
        """Body livery UV: u = x_from_rear / BODY_LEN, v from arc length s."""
        G = self.G
        z = G[..., 2]
        d = np.linalg.norm(np.diff(G[:, :, [0, 2]], axis=1), axis=2)
        arc = np.concatenate([np.zeros((len(G), 1)), np.cumsum(d, 1)], 1)
        k = self.marks[2]
        s = z[:, k:k + 1] + arc - arc[:, k:k + 1]
        s = np.clip(s, 0, tex.BODY_S)
        u = np.clip(G[..., 1], 0, tex.BODY_LEN) / tex.BODY_LEN
        return u, s

    # -------------------------------------------------------------- meshes
    def meshes(self, gap=0.004, flange=0.018):
        part, mat = self.classify()
        G = self.G
        n, m = G.shape[:2]
        u, s = self.uv_grid()
        parts = {}
        for side, sx in (("r", 1), ("l", -1)):
            P = G.copy()
            P[..., 0] *= sx
            vr = 0.5 + 0.5 * s / tex.BODY_S if sx > 0 else 0.5 - 0.5 * s / tex.BODY_S
            idx = np.arange(n * m).reshape(n, m)
            for i in range(n - 1):
                for j in range(m - 1):
                    pt = part[i, j]
                    if pt.startswith("door_"):
                        # doors dict keys: door_f / door_r -> door_lf / door_rf ...
                        pt = "door_%s%s" % (side, pt[-1])
                        pt = {"door_rf": "door_rf", "door_lf": "door_lf", "door_rr": "door_rr", "door_lr": "door_lr"}[pt]
                    fc = [idx[i, j], idx[i + 1, j], idx[i + 1, j + 1], idx[i, j + 1]]
                    if sx < 0:
                        fc = fc[::-1]
                    mt = mat[i, j]
                    if self.frit[i, j]:
                        mt = "trim_gloss"
                    parts.setdefault(pt, []).append((fc, mt, side))
            self._P = getattr(self, "_P", {})
            self._P[side] = (P, u, vr)
        out = {}
        for pt, faces in parts.items():
            msh = Mesh()
            for side in ("r", "l"):
                P, uu, vv = self._P[side]
                fs = [f for f in faces if f[2] == side]
                if not fs:
                    continue
                Pf = P.reshape(-1, 3)
                uf, vf = uu.reshape(-1), vv.reshape(-1)
                used = sorted({k for f in fs for k in f[0]})
                remap = {o: q for q, o in enumerate(used)}
                msh.add(Pf[used], [[remap[k] for k in f[0]] for f in fs],
                        [[(uf[k], vf[k]) for k in f[0]] for f in fs], [f[1] for f in fs])
            out[pt] = weld(msh)
        # panel gaps: pull boundaries of every movable part inwards + flange
        for pt in list(out):
            if pt == "chassis":
                continue
            out[pt] = gap_and_flange(out[pt], gap, flange)
        out["chassis"] = gap_and_flange(out["chassis"], gap, flange, holes_only=True)
        return out


def weld(m, tol=1e-6):
    key = np.round(m.v / tol * 1e-3).astype(np.int64) if False else np.round(m.v * 1e5).astype(np.int64)
    _, first, inv = np.unique(key, axis=0, return_index=True, return_inverse=True)
    inv = inv.reshape(-1)
    out = Mesh()
    out.v = m.v[first]
    out.f, out.uv, out.mat = [], [], []
    for fc, uc, mt in zip(m.f, m.uv, m.mat):
        nf = [int(inv[k]) for k in fc]
        # drop degenerate (collapsed) corners
        keep_f, keep_u = [], []
        for a, b in zip(nf, uc):
            if not keep_f or keep_f[-1] != a:
                keep_f.append(a)
                keep_u.append(b)
        if len(keep_f) > 1 and keep_f[0] == keep_f[-1]:
            keep_f.pop()
            keep_u.pop()
        if len(keep_f) >= 3:
            out.f.append(tuple(keep_f))
            out.uv.append(tuple(keep_u))
            out.mat.append(mt)
    return out


def boundary_edges(m):
    cnt = {}
    for fi, fc in enumerate(m.f):
        for k in range(len(fc)):
            a, b = fc[k], fc[(k + 1) % len(fc)]
            key = (min(a, b), max(a, b))
            cnt.setdefault(key, []).append((fi, a, b))
    return [v[0] for k, v in cnt.items() if len(v) == 1]


def vertex_normals(m):
    n = np.zeros_like(m.v)
    for fc in m.f:
        p = m.v[list(fc)]
        fn = np.zeros(3)
        for k in range(1, len(fc) - 1):
            fn += np.cross(p[k] - p[0], p[k + 1] - p[0])
        for k in fc:
            n[k] += fn
    return n / (np.linalg.norm(n, axis=1, keepdims=True) + 1e-12)


def gap_and_flange(m, gap, flange, holes_only=False):
    """Move boundary vertices `gap` metres into the panel along the surface
    and add an inward lip (dark) so the seams read as real panel gaps."""
    be = boundary_edges(m)
    if not be:
        return m
    vn = vertex_normals(m)
    bverts = {}
    for fi, a, b in be:
        bverts.setdefault(a, []).append((a, b))
        bverts.setdefault(b, []).append((a, b))
    # inward direction: perpendicular to boundary edge within the surface
    move = np.zeros_like(m.v)
    for fi, a, b in be:
        e = m.v[b] - m.v[a]
        nrm = (vn[a] + vn[b])
        inward = np.cross(nrm, e)  # faces are CCW seen from outside -> interior on the left
        ln = np.linalg.norm(inward)
        if ln < 1e-9:
            continue
        inward /= ln
        move[a] += inward
        move[b] += inward
    ln = np.linalg.norm(move, axis=1, keepdims=True)
    mv = np.where(ln > 1e-9, move / (ln + 1e-12), 0)
    # skip vertices on the mirror plane (x=0) that lie on open seams of caps
    newv = m.v.copy()
    bset = np.array(sorted(bverts))
    newv[bset] += mv[bset] * gap
    if holes_only:
        # chassis: only apply where the boundary is an opening for a panel
        pass
    out = Mesh()
    out.v = newv
    out.f, out.uv, out.mat = list(m.f), list(m.uv), list(m.mat)
    # flange quads
    fl_v, fl_f, fl_uv = [], [], []
    base = len(newv)
    for fi, a, b in be:
        pa, pb = newv[a], newv[b]
        qa, qb = pa - vn[a] * flange, pb - vn[b] * flange
        k = base + len(fl_v)
        fl_v += [qa, qb]
        fl_f.append((b, a, k, k + 1))
        fl_uv.append(((0, 0), (1, 0), (1, 1), (0, 1)))
    if fl_v:
        out.v = np.vstack([out.v, np.array(fl_v)])
        out.f += fl_f
        out.uv += fl_uv
        out.mat += ["gap"] * len(fl_f)
    return out

"""Assemble a complete automobile from a preset: body panels, lamps,
details, interior and wheels, organised as GTA SA vehicle parts.

Output of build_car(p):  dict with
   parts   : {part_name: Mesh}  in car coordinates (origin = car centre)
   frames  : [(name, parent_name, position, rotation_matrix)]
   atomics : {part_name: frame_name}
   wheel   : Mesh (local to wheel_rf_dummy)
   steer, spdo, tach : Mesh (local to their frames)
"""
import math
import numpy as np
import bpy  # noqa: F401  (provides mathutils)
from mathutils import Vector
from mathutils.bvhtree import BVHTree

from mesh import (Mesh, grid_mesh, lathe, box, superellipsoid, cylinder, torus,
                  rot_x, rot_y, rot_z, smooth_curve, profile_fn)
from body import Body, weld, vertex_normals
import tex


# ---------------------------------------------------------------- helpers
def bvh_of(meshes):
    V, F = [], []
    for m in meshes:
        b = len(V)
        V += [Vector(v) for v in m.v]
        F += [[i + b for i in f] for f in m.f]
    return BVHTree.FromPolygons(V, F, all_triangles=False, epsilon=0.0)


def raycast(bvh, origin, direction):
    hit = bvh.ray_cast(Vector(origin), Vector(direction))
    if hit[0] is None:
        return None, None
    return np.array(hit[0]), np.array(hit[1])


class Patch:
    """A surface patch projected onto the body along `axis`.
    plane: function (a, b) -> 3D point far outside the body; axis: ray dir.
    shape: a range [a0,a1]; lo(a), hi(a) bottom/top b-curves."""

    def __init__(self, bvh, plane, axis, a0, a1, lo, hi, na=24, nb=10):
        self.ok = True
        A = np.linspace(a0, a1, na)
        P = np.zeros((na, nb, 3))
        N = np.zeros((na, nb, 3))
        UV = np.zeros((na, nb, 2))
        for i, a in enumerate(A):
            B = np.linspace(lo(a), hi(a), nb)
            for j, b in enumerate(B):
                h, n = raycast(bvh, plane(a, b), axis)
                if h is None:
                    self.ok = False
                    h, n = np.array(plane(a, b)), -np.asarray(axis)
                P[i, j], N[i, j] = h, n
                UV[i, j] = ((a - a0) / (a1 - a0 + 1e-9), j / (nb - 1))
        self.P, self.N, self.UV = P, N, UV

    def surface(self, offset, mat, inset=0.0, flip=False, uvmul=(1, 1)):
        P = self.P + self.N * offset
        if inset:
            c = P.mean((0, 1))
            P = c + (P - c) * (1 - inset)
        uv = self.UV * np.array(uvmul)
        return grid_mesh(P, uv, mat, flip=flip)

    def ring(self, off_a, off_b, mat):
        """Wall between the patch boundary at two offsets (a tube)."""
        bd = boundary_loop(self.P)
        bn = boundary_loop(self.N)
        A = bd + bn * off_a
        B = bd + bn * off_b
        G = np.stack([A, B], 1)
        uv = np.zeros(G.shape[:2] + (2,))
        uv[:, 0, 1], uv[:, 1, 1] = 0, 1
        uv[:, :, 0] = np.linspace(0, 4, len(bd))[:, None]
        return grid_mesh(G, uv, mat)


def boundary_loop(P):
    na, nb = P.shape[:2]
    loop = [P[i, 0] for i in range(na)] + [P[na - 1, j] for j in range(1, nb)] + \
           [P[i, nb - 1] for i in range(na - 2, -1, -1)] + [P[0, j] for j in range(nb - 2, -1, -1)]
    return np.array(loop)


def cut_hole(m, inside, normal_axis=None, min_dot=0.2):
    """Remove faces whose centre satisfies inside(c) (and faces the axis)."""
    keep = []
    for fc in m.f:
        p = m.v[list(fc)]
        c = p.mean(0)
        k = True
        if inside(c):
            if normal_axis is None:
                k = False
            else:
                n = np.cross(p[1] - p[0], p[2] - p[0])
                n /= np.linalg.norm(n) + 1e-12
                if np.dot(n, normal_axis) > min_dot:
                    k = False
        keep.append(k)
    return m.subset(keep)


def mirror_x(m):
    return m.mirrored_x()


def flat_quad(center, right, up, w, h, mat, uv=((0, 0), (1, 0), (1, 1), (0, 1))):
    c, r, u = np.asarray(center), np.asarray(right), np.asarray(up)
    V = [c - r * w / 2 - u * h / 2, c + r * w / 2 - u * h / 2, c + r * w / 2 + u * h / 2, c - r * w / 2 + u * h / 2]
    m = Mesh()
    m.add(V, [(0, 1, 2, 3)], [uv], mat)
    return m


# ---------------------------------------------------------------- lamps
def lamp(bvh, body_parts, where, side, x0, x1, lo, hi, mats, depth=0.05, lens=True, n=(22, 8), bulbs=None):
    """Recessed lamp: lens flush with the body, housing behind, walls.
    where: 'front' or 'rear'.  Returns Mesh and modifies body_parts (holes)."""
    sgn = 1 if where == "front" else -1
    axis = (0, -sgn, 0)
    far = 10 * sgn

    def plane(a, b):
        return (a, far, b)
    pa = Patch(bvh, plane, axis, x0, x1, lo, hi, *n)
    out = Mesh()
    if not pa.ok:
        return out, pa
    # hole: faces whose centre is inside the outline (shrunk) and facing out
    def inside(c):
        a, b = c[0], c[2]
        if not (min(x0, x1) + 0.006 < a < max(x0, x1) - 0.006):
            return False
        if not (lo(a) + 0.006 < b < hi(a) - 0.006):
            return False
        return (c[1] * sgn) > 0
    for k in list(body_parts):
        body_parts[k] = cut_hole(body_parts[k], inside, np.array([0, sgn, 0]), 0.45)
    out.extend(pa.surface(-depth, mats["housing"]))
    out.extend(pa.ring(0.002, -depth, "lamp_wall"))
    if lens:
        out.extend(pa.surface(0.002, mats["lens"]))
    if bulbs:
        for (ba0, ba1, blo, bhi, bmat, bd) in bulbs:
            pb = Patch(bvh, plane, axis, ba0, ba1, blo, bhi, 10, 4)
            if pb.ok:
                out.extend(pb.surface(-bd, bmat))
    return out, pa


def side_lamp(bvh, y0, y1, z0, z1, mat, off=0.002):
    def plane(a, b):
        return (10, a, b)
    pa = Patch(bvh, plane, (-1, 0, 0), y0, y1, lambda a: z0, lambda a: z1, 8, 3)
    return pa.surface(off, mat) if pa.ok else Mesh()


# ---------------------------------------------------------------- wheels
def wheel_mesh(p):
    R, rr, w = p["wheel_r"], p["rim_r"], p["tire_w"]
    style = p.get("rim_style", "split")
    out = Mesh()
    # tyre ------------------------------------------------------------
    h = R - rr
    prof = [(rr + 0.005, -w / 2 + 0.012), (rr + h * 0.45, -w / 2 - 0.004), (R - h * 0.12, -w / 2 + 0.006),
            (R - 0.006, -w / 2 + 0.028), (R, -w / 4), (R, w / 4), (R - 0.006, w / 2 - 0.028),
            (R - h * 0.12, w / 2 - 0.006), (rr + h * 0.45, w / 2 + 0.004), (rr + 0.005, w / 2 - 0.012)]
    prof = smooth_curve(prof, 16)
    vco = np.interp(np.arange(16), [0, 4, 11, 15], [0.0, 0.3, 0.7, 1.0])
    out.extend(lathe(prof, 48, "tire", axis="x", v_coords=vco, u_scale=2))
    # rim barrel (seen through the spokes) ------------------------------
    bar = [(rr - 0.004, w / 2 - 0.03), (rr - 0.012, w / 2 - 0.06), (rr - 0.012, -w / 2 + 0.02), (rr + 0.004, -w / 2 + 0.006)]
    out.extend(lathe(bar, 40, "rim_in", axis="x"))
    lip = [(rr + 0.012, w / 2 - 0.006), (rr - 0.004, w / 2 - 0.004), (rr - 0.006, w / 2 - 0.03)]
    out.extend(lathe(lip, 40, "rim", axis="x"))
    # face with spokes --------------------------------------------------
    xf = w / 2 - 0.012
    dish = {"steel": 0.02, "multi": 0.05, "forged": 0.06, "offroad": 0.03, "turbine": 0.035, "split": 0.045}.get(style, 0.04)
    import mesh as _m
    nr, nt = max(6, int(12 * _m.DETAIL)), max(60, int(160 * _m.DETAIL))
    rs = np.linspace(0.045, rr - 0.006, nr)
    th = np.linspace(0, 2 * math.pi, nt + 1)
    ns = max(p.get("spokes", 5), 1)

    def solid(r, t):
        q = r / rr
        if r < 0.075 or r > rr - 0.02:
            return True
        if style == "steel":
            # steel wheel: solid disc with round vent holes
            k = (t * 8 / (2 * math.pi)) % 1
            d = math.hypot((k - 0.5) * 2 * math.pi * r / 8, r - rr * 0.68)
            return d > 0.022
        tw = t + {"forged": 0.5, "turbine": 1.4}.get(style, 0.0) * (q - 0.3)
        k = (tw * ns / (2 * math.pi)) % 1
        width = {"split": 0.05, "multi": 0.024, "forged": 0.06, "offroad": 0.07, "turbine": 0.03}.get(style, 0.04)
        half = (width / 2) / max(r, 1e-3) * ns / (2 * math.pi)
        half *= 1.0 + {"forged": 0.9, "offroad": 0.3}.get(style, 0.2) * (1 - q)
        if style == "split":
            return abs(k - 0.42) < half * 0.6 or abs(k - 0.58) < half * 0.6 or (q < 0.45 and abs(k - 0.5) < half * 1.4)
        return abs(k - 0.5) < half
    keep = np.zeros((nr - 1, nt), bool)
    for i in range(nr - 1):
        for j in range(nt):
            keep[i, j] = solid((rs[i] + rs[i + 1]) / 2, (th[j] + th[j + 1]) / 2)
    P = np.zeros((nr, nt + 1, 3))
    for i, r in enumerate(rs):
        x = xf - dish * (1 - (r - rs[0]) / (rs[-1] - rs[0])) ** 1.3
        P[i, :, 0] = x
        P[i, :, 1] = r * np.cos(th)
        P[i, :, 2] = r * np.sin(th)
    UV = np.zeros((nr, nt + 1, 2))
    UV[..., 0] = 0.5 + P[..., 1] / (2 * rr)
    UV[..., 1] = 0.5 + P[..., 2] / (2 * rr)
    face = Mesh()
    idx = np.arange(nr * (nt + 1)).reshape(nr, nt + 1)
    F, U = [], []
    for i in range(nr - 1):
        for j in range(nt):
            if keep[i, j]:
                fc = (idx[i, j], idx[i, j + 1], idx[i + 1, j + 1], idx[i + 1, j])
                F.append(fc)
                U.append([UV.reshape(-1, 2)[k] for k in fc])
    face.add(P.reshape(-1, 3), F, U, "rim")
    face = weld(face)
    # spoke side walls (depth)
    walls = Mesh()
    depth = 0.035
    for i in range(nr - 1):
        for j in range(nt):
            if not keep[i, j]:
                continue
            for (di, dj, e) in ((0, 1, (idx[i, j + 1], idx[i + 1, j + 1])), (0, -1, (idx[i + 1, j], idx[i, j]))):
                jj = (j + dj) % nt
                if not keep[i, jj]:
                    a, b = P.reshape(-1, 3)[e[0]], P.reshape(-1, 3)[e[1]]
                    walls.add([a, b, b - (depth, 0, 0), a - (depth, 0, 0)], [(0, 1, 2, 3)], [((0, 0), (1, 0), (1, 1), (0, 1))], "rim_dark")
    out.extend(face).extend(walls)
    # centre cap + lug nuts
    cap = lathe([(0.0, xf - dish + 0.012), (0.035, xf - dish + 0.01), (0.045, xf - dish)], 24, "badge", axis="x")
    cap.uv = [tuple((0.5 + v_[0] * 0 + 0.5 * math.cos(2 * math.pi * v_[0]) * v_[1], 0.5 + 0.5 * math.sin(2 * math.pi * v_[0]) * v_[1]) for v_ in uc) for uc in cap.uv]
    out.extend(cap)
    for k in range(5):
        a = k * 2 * math.pi / 5
        c = (xf - dish + 0.004, 0.058 * math.cos(a), 0.058 * math.sin(a))
        out.extend(cylinder(0.009, 0.02, c, "x", "chrome", seg=6))
    # brake disc + hub (rotates with the wheel in GTA, fine for a disc)
    disc = lathe([(0.06, 0.0), (rr - 0.045, 0.0)], 32, "disc", axis="x")
    disc.uv = [tuple((0.5 + 0.5 * (pv[1] if False else 1) * 0 + 0.5 * math.cos(2 * math.pi * pv[0]) * (0.25 + 0.75 * pv[1]),
                      0.5 + 0.5 * math.sin(2 * math.pi * pv[0]) * (0.25 + 0.75 * pv[1])) for pv in uc) for uc in disc.uv]
    out.extend(disc.transformed(t=(w / 2 - 0.08, 0, 0)))
    back = lathe([(rr - 0.045, -0.01), (0.06, -0.01)], 32, "disc", axis="x")
    out.extend(back.transformed(t=(w / 2 - 0.08, 0, 0)))
    return out


def caliper(p):
    rr = p["rim_r"]
    w = p["tire_w"]
    prof = [(rr - 0.05, -0.025), (rr - 0.02, -0.025), (rr - 0.02, 0.03), (rr - 0.05, 0.03)]
    m = lathe(prof, 8, "caliper", axis="x", arc=math.radians(60), angle0=math.radians(150))
    return m.transformed(t=(w / 2 - 0.08, 0, 0))


# ---------------------------------------------------------------- interior
def seat(style, x, y, z, lux=False):
    """Seat at hip point (x,y,z), facing +y."""
    m = Mesh()
    W = {"classic": 0.50, "sport": 0.50, "lux": 0.56, "bucket": 0.50}[style]
    cush_h = 0.13 if style != "bucket" else 0.10
    m.extend(superellipsoid((W * 0.86, 0.50, cush_h), (x, y + 0.13, z - 0.07), "seat", (20, 10), 3.0, 3))
    bol = 0.06 if style == "classic" else 0.10
    for sx in (-1, 1):
        m.extend(superellipsoid((0.09, 0.48, cush_h + bol * 0.6), (x + sx * W * 0.44, y + 0.13, z - 0.06), "seat_side", (12, 8), 3.0, 3))
    back = Mesh()
    bh = 0.62 if style != "bucket" else 0.78
    back.extend(superellipsoid((W * 0.82, 0.13, bh), (0, 0, bh / 2), "seat", (20, 12), 3.0, 3))
    for sx in (-1, 1):
        back.extend(superellipsoid((0.10, 0.16 + bol * 0.3, bh * 0.85), (sx * W * 0.43, 0.02, bh * 0.45), "seat_side", (12, 8), 3.0, 3))
    if style != "bucket":
        back.extend(superellipsoid((0.27, 0.10, 0.18), (0, -0.01, bh + 0.14), "seat", (14, 8), 2.6, 3))
        for sx in (-0.07, 0.07):
            back.extend(cylinder(0.006, 0.08, (sx, -0.01, bh + 0.03), "z", "chrome", 6, False))
    else:
        back.extend(superellipsoid((0.30, 0.12, 0.02), (0, 0.06, bh - 0.12), "trim", (8, 4), 4.0, 3))
    back = back.transformed(rot_x(math.radians(-16)), (x, y - 0.10, z - 0.04))
    m.extend(back)
    # rails
    for sx in (-0.18, 0.18):
        m.extend(box((x + sx - 0.015, y - 0.15, z - 0.22), (x + sx + 0.015, y + 0.40, z - 0.18), "metal_dark"))
    return m


def rear_bench(x_half, y, z):
    m = Mesh()
    m.extend(superellipsoid((x_half * 2 * 0.9, 0.50, 0.14), (0, y + 0.12, z - 0.07), "seat", (30, 10), 3.0, 3))
    back = Mesh()
    for sx in (-1, 0, 1):
        wdt = x_half * 2 * 0.9 / 3
        back.extend(superellipsoid((wdt * 0.96, 0.15, 0.58), (sx * wdt, 0, 0.29), "seat", (16, 10), 3.0, 3))
        back.extend(superellipsoid((0.24, 0.09, 0.15), (sx * wdt, -0.01, 0.70), "seat", (12, 8), 2.6, 3))
    m.extend(back.transformed(rot_x(math.radians(-22)), (0, y - 0.10, z - 0.04)))
    return m


def steering_wheel(style="sport"):
    """Local frame: wheel in the XZ plane, column along +Y (towards dash)."""
    m = Mesh()
    R = 0.185 if style != "classic" else 0.20
    rim = torus(R, 0.017, (0, 0, 0), "y", "steer_leather", (40, 10))
    m.extend(rim)
    m.extend(superellipsoid((0.15, 0.07, 0.12), (0, 0.035, -0.01), "steer_hub", (16, 8), 2.8, 4))
    m.extend(flat_quad((0, -0.0005, -0.01), (1, 0, 0), (0, 0, 1), 0.06, 0.06, "badge").transformed(t=(0, 0, 0)))
    angles = [0, 180, 270] if style != "classic" else [200, 340, 270]
    for a in angles:
        r = math.radians(a)
        d = np.array([math.cos(r), 0, math.sin(r)])
        c = d * (R * 0.55)
        sp = superellipsoid((R * 0.85, 0.022, 0.04), (0, 0, 0), "steer_hub", (10, 6), 3.0, 4)
        M = np.array([[d[0], 0, -d[2]], [0, 1, 0], [d[2], 0, d[0]]])
        m.extend(sp.transformed(M, c + (0, 0.02, 0)))
    if style in ("sport", "bucket"):
        # flat bottom & red top marker
        m.extend(superellipsoid((0.02, 0.036, 0.012), (0, 0, R), "accent", (8, 6), 3.0))
    m.extend(cylinder(0.025, 0.25, (0, 0.18, 0), "y", "plastic_dark", 12))
    return m


def needle_mesh(length):
    """Local frame: dial face = XZ plane, needle along +X at 0 rad,
    rotates about local Y."""
    m = Mesh()
    m.add([(-0.012, -0.002, -0.0025), (length, -0.002, -0.0008), (length, -0.002, 0.0008), (-0.012, -0.002, 0.0025)],
          [(0, 1, 2, 3)], [((0, 0), (1, 0.45), (1, 0.55), (0, 1))], "needle")
    m.extend(cylinder(0.008, 0.006, (0, -0.004, 0), "y", "plastic_dark", 10))
    return m


def loft_profile_across(profile_yz, x0, x1, nx, mat, bump=None):
    """Extrude a (y,z) polyline across x; bump(x) -> dz added to top points."""
    prof = np.asarray(profile_yz, float)
    X = np.linspace(x0, x1, nx)
    P = np.zeros((nx, len(prof), 3))
    for i, x in enumerate(X):
        P[i, :, 0] = x
        P[i, :, 1] = prof[:, 0]
        P[i, :, 2] = prof[:, 1] + (bump(x) * np.linspace(1, 0, len(prof)) ** 0 * (prof[:, 1] >= prof[:, 1].max() - 0.06) if bump else 0)
    UV = np.zeros((nx, len(prof), 2))
    UV[..., 0] = (P[..., 0] - x0) * 3
    UV[..., 1] = np.cumsum(np.r_[0, np.linalg.norm(np.diff(prof, axis=0), axis=1)])[None, :] * 3
    return grid_mesh(P, UV, mat, flip=True)


def interior(p, body):
    """Everything inside the cabin.  Returns (mesh, steer_frame, cluster)."""
    out = Mesh()
    L = p["len"]
    I = p["interior"]
    zs = float(body.z_sill(p["ws1"]))
    zf = zs + 0.08
    w_in = float(body.w_sh(p["ws1"])) - 0.12
    two_seat = len(p["doors"]) == 1 and p.get("engine_rear")
    sport_low = p.get("engine_rear", False)
    yh = p.get("seat_y", p["ws1"] - (0.18 if sport_low else 0.30))
    zh = zf + (0.14 if sport_low else 0.27 if p["name"] != "suv" else 0.34)
    xd = 0.37 if not sport_low else 0.36
    style = I["seats"]
    # floor / carpet
    y_back = (yh - 1.15) if not two_seat else (yh - 0.45)
    y_fw = p["ws0"] - 0.30
    out.extend(box((-w_in, y_back, zf - 0.02), (w_in, y_fw, zf), "carpet", 2))
    out.extend(box((-w_in, y_fw - 0.02, zf), (w_in, y_fw, zh + 0.25), "carpet", 2))  # firewall
    # tunnel
    out.extend(superellipsoid((0.26, y_fw - y_back, 0.16), (0, (y_fw + y_back) / 2, zf + 0.04), "carpet", (16, 8), 3.0, 2))
    # seats
    for sx in (-1, 1):
        out.extend(seat(style, sx * xd, yh, zh))
    if not two_seat:
        out.extend(rear_bench(w_in - 0.05, yh - 0.86, zh + 0.02))
        ys0, ys1 = max(p["rw0"] + 0.02, yh - 1.30), yh - 1.08
        zsh = float(body.z_belt(ys1)) + 0.01
        wsh_ = float(body.w_sh(ys1)) - 0.16
        if ys1 > ys0:
            out.extend(box((-wsh_, ys0, zsh - 0.02), (wsh_, ys1, zsh), "plastic_dark"))  # parcel shelf
    else:
        out.extend(box((-w_in, y_back - 0.02, zf), (w_in, y_back, float(body.z_belt(y_back)) + 0.2), "trim"))  # bulkhead
    # dashboard --------------------------------------------------------
    zb = float(body.z_belt(p["ws0"]))
    yd = yh + 0.80 if not sport_low else yh + 0.86
    ytop0 = p["ws0"] - 0.02
    prof = [(ytop0, zb - 0.01), (ytop0 - 0.10, zb + 0.015), ((ytop0 + yd) / 2, zb + 0.03),
            (yd + 0.04, zb + 0.02), (yd, zb - 0.02), (yd - 0.02, zb - 0.10), (yd + 0.01, zh + 0.20),
            (yd + 0.08, zh + 0.06), (y_fw, zf + 0.10)]
    dash = loft_profile_across(prof, -w_in - 0.02, w_in + 0.02, 36, "dash")
    out.extend(dash)
    # binnacle over the cluster
    bx = -xd
    out.extend(superellipsoid((0.40, 0.20, 0.07), (bx, yd + 0.02, zb + 0.03), "dash", (16, 8), 3.0, 3))
    # cluster face (gauges) - tilted towards the driver
    tilt = math.radians(15)
    cl_c = np.array([bx, yd + 0.05, zb - 0.045])
    cl_w, cl_h = 0.34, 0.17
    up = np.array([0, math.sin(tilt), math.cos(tilt)])
    out.extend(flat_quad(cl_c, (1, 0, 0), up, cl_w, cl_h, "gauges"))
    # needle frames (dial centres), see tex.gauges: dial centres at u=0.25/0.75, v=0.5
    spdo_c = cl_c + np.array([-cl_w * 0.25, -0.004, 0])
    tach_c = cl_c + np.array([cl_w * 0.25, -0.004, 0])
    # centre screen + climate + vents
    sc_c = np.array([0, yd + 0.06, zb - 0.06])
    out.extend(flat_quad(sc_c + (0, -0.003, 0), (1, 0, 0), up, 0.26, 0.13, "screen"))
    out.extend(superellipsoid((0.30, 0.04, 0.17), sc_c + (0, 0.02, 0), "trim", (12, 6), 4, 3))
    out.extend(flat_quad((0, yd + 0.035, zh + 0.26), (1, 0, 0), (0, -0.3, 1), 0.20, 0.10, "climate"))
    for vx in (-w_in + 0.12, -0.14, 0.14, w_in - 0.12):
        out.extend(superellipsoid((0.12, 0.03, 0.05), (vx, yd - 0.005, zb - 0.07), "vent", (10, 6), 4, 3))
    # decorative trim strip across the dash
    out.extend(superellipsoid((w_in * 2 - 0.1, 0.02, 0.03), (0, yd - 0.01, zb - 0.13), "deco", (24, 6), 6, 4))
    # centre console
    out.extend(superellipsoid((0.22, yd - yh + 0.10, 0.20), (0, (yd + yh) / 2 - 0.02, zh - 0.02), "trim", (14, 8), 3.5, 3))
    out.extend(superellipsoid((0.20, 0.30, 0.04), (0, yh - 0.05, zh + 0.10), "seat", (10, 6), 3.5, 3))  # armrest
    out.extend(cylinder(0.010, 0.13, (0, yh + 0.38, zh + 0.12), "z", "chrome", 8))
    out.extend(superellipsoid((0.045, 0.06, 0.05), (0, yh + 0.38, zh + 0.20), "steer_leather", (10, 8), 2.4))
    # pedals
    for k, px in enumerate((-xd - 0.10, -xd + 0.02, -xd + 0.12)):
        out.extend(box((px - 0.035, y_fw - 0.12, zf + 0.06), (px + 0.035, y_fw - 0.10, zf + 0.16), "metal_dark"))
    # interior mirror
    out.extend(superellipsoid((0.24, 0.03, 0.06), (0, p["ws1"] + 0.06, float(body.z_top(p["ws1"])) - 0.11), "plastic_dark", (12, 6), 3.0))
    out.extend(flat_quad((0, p["ws1"] + 0.044, float(body.z_top(p["ws1"])) - 0.11), (1, 0, 0), (0, 0, 1), 0.21, 0.045, "mirror"))
    # steering wheel frame
    col_tilt = math.radians(24 if not sport_low else 18)
    sw_c = np.array([-xd, yh + (0.50 if not sport_low else 0.52), zh + (0.40 if not sport_low else 0.32)])
    return out, dict(steer=(sw_c, col_tilt), spdo=spdo_c, tach=tach_c, dial_up=up, dial_r=cl_h * 0.46,
                     seat=(xd, yh, zh), cluster=(cl_c, cl_w, cl_h))


def inner_shell(m, offset, mat_map, keep_fn=None, flip=True):
    """Offset a panel inwards (door cards, headliner...)."""
    vn = vertex_normals(m)
    keep = [keep_fn(m, i) if keep_fn else True for i in range(len(m.f))]
    sub = Mesh()
    sub.v = m.v - vn * offset
    sub.f, sub.uv, sub.mat = list(m.f), [tuple((a * 6, b * 6) for a, b in u) for u in m.uv], [mat_map(x) for x in m.mat]
    sub = sub.subset(keep)
    if flip:
        sub.flip()
    return sub


# ---------------------------------------------------------------- the car
def build_car(p, low=False):
    L = p["len"]
    body = Body(p)
    parts = body.meshes()
    bodies_for_bvh = [parts[k] for k in parts]
    bvh = bvh_of(bodies_for_bvh)
    extra = {k: Mesh() for k in ["chassis", "bump_front", "bump_rear", "boot", "bonnet"]}
    for k in parts:
        extra.setdefault(k, Mesh())

    # ------------------------------------------------ head lamps
    H = p["head"]
    hx0, hx1 = H["x"]
    hz0, hz1 = H["z"]
    shape = H["shape"]
    if shape == "swept":
        lo = lambda a: hz0 + (a - hx0) / (hx1 - hx0) * 0.045
        hi = lambda a: hz1 + (a - hx0) / (hx1 - hx0) * 0.03 - 0.03 * ((a - hx0) / (hx1 - hx0)) ** 2
    elif shape == "slit":
        lo = lambda a: hz0 + (a - hx0) / (hx1 - hx0) * 0.05
        hi = lambda a: hz0 + 0.035 + (a - hx0) / (hx1 - hx0) * 0.07
    elif shape == "quad":
        lo = lambda a: hz0
        hi = lambda a: hz1
    else:  # twin_round / generic rectangle
        lo = lambda a: hz0
        hi = lambda a: hz1
    head_parts = Mesh()
    for side, sx in (("r", 1), ("l", -1)):
        lmat = "light_head_r" if sx > 0 else "light_head_l"
        tmat = "turn_fr" if sx > 0 else "turn_fl"
        a0, a1 = (hx0, hx1) if sx > 0 else (-hx1, -hx0)
        lo_s = (lambda f: (lambda a: f(abs(a))))(lo)
        hi_s = (lambda f: (lambda a: f(abs(a))))(hi)
        span = hx1 - hx0
        inner = (a0 + 0.08 * span, a0 + 0.62 * span) if sx > 0 else (a1 - 0.62 * span, a1 - 0.08 * span)
        turn = (a0 + 0.78 * span, a1 - 0.03 * span) if sx > 0 else (a0 + 0.03 * span, a1 - 0.78 * span)
        drl = (a0 + 0.05 * span, a1 - 0.05 * span)
        hmid = lambda a: (lo_s(a) + hi_s(a)) / 2
        bulbs = [(inner[0], inner[1], lambda a: lo_s(a) + 0.2 * (hi_s(a) - lo_s(a)), lambda a: hi_s(a) - 0.15 * (hi_s(a) - lo_s(a)), lmat, 0.035),
                 (turn[0], turn[1], lambda a: lo_s(a) + 0.15 * (hi_s(a) - lo_s(a)), lambda a: hi_s(a) - 0.15 * (hi_s(a) - lo_s(a)), tmat, 0.03)]
        if H.get("drl"):
            bulbs.append((drl[0], drl[1], lambda a: lo_s(a) + 0.04 * (hi_s(a) - lo_s(a)), lambda a: lo_s(a) + 0.16 * (hi_s(a) - lo_s(a)), lmat, 0.02))
        if shape == "twin_round":
            # two round lamps per side, plus amber corner
            for c, rr_ in ((a0 + span * 0.25, 0.06), (a0 + span * 0.55, 0.06)) if sx > 0 else ((a1 - span * 0.25, 0.06), (a1 - span * 0.55, 0.06)):
                zc = (hz0 + hz1) / 2
                lo_c = (lambda c, r: (lambda a: zc - math.sqrt(max(r * r - (a - c) ** 2, 0))))(c, rr_)
                hi_c = (lambda c, r: (lambda a: zc + math.sqrt(max(r * r - (a - c) ** 2, 0))))(c, rr_)
                mh, _ = lamp(bvh, parts, "front", side, c - rr_, c + rr_, lo_c, hi_c,
                             {"housing": "head_housing", "lens": "lens"}, 0.05, True, (14, 8),
                             [(c - rr_ * 0.6, c + rr_ * 0.6, (lambda c, r: (lambda a: zc - 0.6 * math.sqrt(max(r * r - (a - c) ** 2, 0))))(c, rr_),
                               (lambda c, r: (lambda a: zc + 0.6 * math.sqrt(max(r * r - (a - c) ** 2, 0))))(c, rr_), lmat, 0.04)])
                head_parts.extend(mh)
            tc0, tc1 = (a0 + span * 0.78, a1) if sx > 0 else (a0, a1 - span * 0.78)
            mt, _ = lamp(bvh, parts, "front", side, tc0, tc1, lambda a: hz0 + 0.01, lambda a: hz1 - 0.01,
                         {"housing": tmat, "lens": "lens_amber"}, 0.02, True, (6, 4))
            head_parts.extend(mt)
        else:
            mh, _ = lamp(bvh, parts, "front", side, a0, a1, lo_s, hi_s, {"housing": "head_housing", "lens": "lens"}, 0.06, True, (26, 8), bulbs)
            head_parts.extend(mh)
    extra["chassis"].extend(head_parts)

    # ------------------------------------------------ tail lamps
    T = p["tail"]
    tx0, tx1 = T["x"]
    tz0, tz1 = T["z"]
    tail_parts = Mesh()
    for side, sx in (("r", 1), ("l", -1)):
        lmat = "light_tail_r" if sx > 0 else "light_tail_l"
        tmat = "turn_rr" if sx > 0 else "turn_rl"
        a0, a1 = (tx0, tx1) if sx > 0 else (-tx1, -tx0)
        span = tx1 - tx0
        if T["pattern"] == "bar_full" and sx < 0:
            continue
        if T["pattern"] == "bar_full":
            a0, a1 = -tx1, tx1
            span = a1 - a0
        lo = lambda a: tz0
        hi = lambda a: tz1
        bulbs = [(a0 + 0.04 * span, a1 - 0.04 * span, lambda a: tz0 + 0.55 * (tz1 - tz0), lambda a: tz1 - 0.1 * (tz1 - tz0), lmat, 0.03),
                 (a0 + 0.04 * span, a1 - 0.04 * span, lambda a: tz0 + 0.1 * (tz1 - tz0), lambda a: tz0 + 0.45 * (tz1 - tz0), tmat, 0.03)]
        if T["pattern"] == "bar_full":
            bulbs = [(a0 + 0.02, -0.03, lambda a: tz0 + 0.2 * (tz1 - tz0), lambda a: tz1 - 0.2 * (tz1 - tz0), "light_tail_l", 0.02),
                     (0.03, a1 - 0.02, lambda a: tz0 + 0.2 * (tz1 - tz0), lambda a: tz1 - 0.2 * (tz1 - tz0), "light_tail_r", 0.02)]
        mt, _ = lamp(bvh, parts, "rear", side, a0, a1, lo, hi, {"housing": "tail_housing", "lens": "lens_red"}, 0.05, True, (24, 6), bulbs)
        tail_parts.extend(mt)
        if T["pattern"] == "bar_full":
            # separate small amber indicators under the bar
            for s2, m2 in ((1, "turn_rr"), (-1, "turn_rl")):
                b0, b1 = sorted((s2 * (tx1 - 0.20), s2 * (tx1 - 0.02)))
                mi, _ = lamp(bvh, parts, "rear", side, b0, b1, lambda a: tz0 - 0.07, lambda a: tz0 - 0.03,
                             {"housing": m2, "lens": "lens_amber"}, 0.01, True, (6, 3))
                tail_parts.extend(mi)
    target_tail = "boot" if p.get("tailgate") else "chassis"
    extra["chassis"].extend(tail_parts)

    # ------------------------------------------------ grille & intakes
    G = p["grille"]
    gw = G["w"]
    gz0, gz1 = G["z"]
    gmat = "grille_hc" if G["style"] in ("honeycomb", "horseshoe", "spindle", "wide_mesh") else "grille_slat"
    openings = []
    def rounded(x0, x1, z0, z1, r):
        cx = (x0 + x1) / 2
        hw = (x1 - x0) / 2
        def lo(a):
            q = max(0.0, abs(a - cx) - (hw - r)) / r
            return z0 + r * (1 - math.sqrt(max(0.0, 1 - min(q, 1) ** 2)))
        def hi(a):
            q = max(0.0, abs(a - cx) - (hw - r)) / r
            return z1 - r * (1 - math.sqrt(max(0.0, 1 - min(q, 1) ** 2)))
        return (x0, x1, lo, hi)
    st = G["style"]
    if st == "kidney":
        # twin rounded openings either side of the centre
        gap = G.get("gap", 0.025)
        r = min(0.05, (gz1 - gz0) * 0.35)
        for sx in (-1, 1):
            x0, x1 = sorted((sx * gap, sx * gw / 2))
            openings.append(rounded(x0, x1, gz0, gz1, r))
    elif st == "spindle":
        zm = gz0 + (gz1 - gz0) * 0.55
        openings.append((-gw * 0.32, gw * 0.32, lambda a: zm, lambda a: gz1 - 0.03 * (abs(a) / (gw * 0.32)) ** 2))
        openings.append((-gw / 2, gw / 2, lambda a: gz0 + 0.03 * (abs(a) / (gw / 2)) ** 2, lambda a: zm - 0.02 + 0.06 * (abs(a) / (gw / 2))))
    elif st == "horseshoe":
        openings.append((-gw / 2, gw / 2, lambda a: gz0 + 0.12 * (abs(a) / (gw / 2)) ** 2, lambda a: gz1 - 0.03 * (abs(a) / (gw / 2)) ** 2))
    else:
        openings.append(rounded(-gw / 2, gw / 2, gz0, gz1, min(0.04, (gz1 - gz0) * 0.3)))
    gpatch = None
    for (x0, x1, lo, hi) in openings:
        mg, gp = lamp(bvh, parts, "front", "c", x0, x1, lo, hi, {"housing": "grille_back", "lens": gmat}, 0.06, True, (20, 8))
        extra["bump_front"].extend(mg)
        if gp.ok:
            extra["bump_front"].extend(gp.ring(0.008, -0.004, "chrome" if G.get("chrome", True) else "trim_gloss"))
            gpatch = gpatch or gp
    if gpatch is None:
        gpatch = gp
    # lower side intakes / fog lamps
    bz = p["bumper_top"][1]
    zfog = float(p["z_sill"][-2][1]) + 0.10
    for sx in (1, -1):
        c = sx * (gw / 2 + 0.16)
        mf, _ = lamp(bvh, parts, "front", "f", c - 0.07, c + 0.07, lambda a: zfog, lambda a: zfog + 0.06,
                     {"housing": "grille_hc", "lens": "lens"}, 0.03, False, (8, 4),
                     [(c - 0.04, c + 0.04, lambda a: zfog + 0.012, lambda a: zfog + 0.048, "fog", 0.02)])
        extra["bump_front"].extend(mf)
    # badge
    if gpatch.ok and st not in ("kidney",) and G.get("badge", True):
        ctr = gpatch.P[gpatch.P.shape[0] // 2, gpatch.P.shape[1] // 2]
        extra["bump_front"].extend(lathe([(0.0, 0.012), (0.04, 0.008), (0.045, 0.0)], 24, "badge", axis="y").transformed(rot_x(math.pi / 2) @ rot_x(-math.pi / 2), ctr + (0, 0.005, 0)))

    # ------------------------------------------------ plates
    def plate(where, z):
        sgn = 1 if where == "front" else -1
        h, n = raycast(bvh, (0, 10 * sgn, z), (0, -sgn, 0))
        if h is None:
            return Mesh()
        c = h + np.array([0, sgn * 0.012, 0])
        right = np.array([-sgn, 0, 0.0])
        m = flat_quad(c, right, (0, 0, 1), 0.52, 0.113, "plate")
        m.extend(box(c - (0.27, 0.008 if sgn > 0 else -0.002, 0.065) - (0, 0.004, 0), c + (0.27, -0.002 if sgn > 0 else 0.008, 0.065), "plastic_dark"))
        return m
    if p.get("plate_f"):
        extra["bump_front"].extend(plate("front", p["plate_f"]))
    if p.get("plate_r"):
        tgt = "boot" if p["plate_r"] > p["bumper_top"][0] else "bump_rear"
        extra[tgt].extend(plate("rear", p["plate_r"]))

    # ------------------------------------------------ exhaust
    for (ex, ez) in p["exhaust"]:
        h, n = raycast(bvh, (ex, -10, ez), (0, 1, 0))
        y = (h[1] if h is not None else 0) + 0.02
        ex_m = lathe([(0.0, 0.10), (0.032, 0.10), (0.038, 0.0), (0.038, -0.12), (0.03, -0.12), (0.03, 0.02), (0.0, 0.02)], 16, "chrome", axis="y")
        extra["bump_rear"].extend(ex_m.transformed(t=(ex, y - 0.06, ez)))
        extra["bump_rear"].extend(lathe([(0.03, 0.0), (0.0, 0.0)], 16, "under", axis="y").transformed(t=(ex, y - 0.02, ez)))

    # ------------------------------------------------ mirrors, handles, wipers, antenna
    ty_m = p["ws0"] - p.get("sail", 0.16) * 0.55
    zb = float(body.z_belt(ty_m))
    wsh = float(body.w_sh(ty_m))
    door_parts = {}
    for side, sx in (("r", 1), ("l", -1)):
        mm = Mesh()
        c = np.array([sx * (wsh + 0.075), ty_m, zb + 0.09])
        mm.extend(superellipsoid((0.17, 0.10, 0.11), c, "paint", (16, 8), 3.0, 1))
        mm.extend(superellipsoid((0.12, 0.07, 0.035), c + (-sx * 0.07, 0.01, -0.065), "paint", (10, 6), 3.0, 1))
        mm.extend(flat_quad(c + (0, -0.051, 0), (-sx, 0, 0), (0, 0, 1), 0.15, 0.09, "mirror"))
        mm.extend(superellipsoid((0.10, 0.012, 0.012), c + (sx * 0.01, 0.045, -0.042), "turn_fr" if sx > 0 else "turn_fl", (8, 4), 3.0))
        door_parts["door_%sf" % side] = mm
        # door handles
        for key, (a, b) in p["doors"].items():
            dname = "door_%s%s" % (side, key[-1])
            hy = b - 0.18 if key[-1] == "f" else b - 0.16
            hz = float(body.z_belt(hy)) - 0.07
            h, n = raycast(bvh, (sx * 10, hy, hz), (-sx, 0, 0))
            if h is None:
                continue
            hm = superellipsoid((0.025, 0.14, 0.03), h + n * 0.008, "chrome" if p["name"] in ("exec_sedan", "classic_sedan") else "paint", (10, 6), 3.0, 1)
            door_parts.setdefault(dname, Mesh()).extend(hm)
    for k, m in door_parts.items():
        if k in parts:
            extra.setdefault(k, Mesh()).extend(m)
    # wipers (on the windscreen base)
    for sx in (-0.38, 0.12):
        y0 = p["ws0"] - 0.06
        z0 = float(body.z_belt(p["ws0"])) + 0.035
        a = math.radians(8)
        wip = box((-0.30, -0.006, -0.004), (0.30, 0.006, 0.004), "plastic_dark").transformed(rot_y(a) @ rot_x(math.radians(-35)), (sx + 0.10, y0, z0 + 0.02))
        extra["chassis"].extend(wip)
    # shark-fin antenna
    yr = p["rw1"] + 0.12
    extra["chassis"].extend(superellipsoid((0.05, 0.16, 0.06), (0, yr, float(body.z_top(yr)) + 0.02), "trim_gloss", (10, 6), 2.2))
    # wheel well liners -------------------------------------------------
    for yc in (p["axle_r"], p["axle_f"]):
        for sx in (1, -1):
            R = p["arch_r"] + 0.01
            w0 = p["track"] - p["tire_w"] / 2 - 0.06
            w1 = float(body.w_sh(yc)) + 0.03
            prof = [(R, 0), (R, 1)]
            th0, th1 = math.radians(-15), math.radians(195)
            n = 20
            th = np.linspace(th0, th1, n)
            P = np.zeros((n, 2, 3))
            for i, t_ in enumerate(th):
                P[i, 0] = (sx * w0, yc + R * math.cos(t_), p["wheel_r"] + R * math.sin(t_))
                P[i, 1] = (sx * w1, yc + R * math.cos(t_), p["wheel_r"] + R * math.sin(t_))
            uv = np.zeros((n, 2, 2))
            uv[:, :, 0] = np.linspace(0, 3, n)[:, None]
            uv[:, 1, 1] = 1
            lin = grid_mesh(P, uv, "liner", flip=sx < 0)
            # inner wall
            Q = np.zeros((n, 2, 3))
            for i, t_ in enumerate(th):
                Q[i, 0] = (sx * w0, yc + R * math.cos(t_), p["wheel_r"] + R * math.sin(t_))
                Q[i, 1] = (sx * w0, yc + 0.2 * math.cos(t_), p["wheel_r"] + 0.2 * math.sin(t_))
            lin.extend(grid_mesh(Q, uv, "liner", flip=sx > 0))
            extra["chassis"].extend(lin)

    # ------------------------------------------------ interior
    inter, info = interior(p, body)
    extra["chassis"].extend(inter)
    # door cards / headliner from the panels themselves
    belt_z = lambda y: float(body.z_belt(y))

    def door_keep(m, i):
        if m.mat[i] != "paint":
            return False
        c = m.v[list(m.f[i])].mean(0)
        return c[2] < belt_z(c[1]) + 0.03 and c[2] > float(body.z_sill(c[1])) + 0.10
    for k in list(parts):
        if k.startswith("door_"):
            extra[k].extend(inner_shell(parts[k], 0.05, lambda x: "door_card", door_keep))
            # armrest + inner handle
            mid = parts[k].v.mean(0)
            sx = 1 if mid[0] > 0 else -1
            zb2 = belt_z(mid[1])
            extra[k].extend(superellipsoid((0.07, 0.40, 0.05), (mid[0] - sx * 0.09, mid[1] - 0.05, zb2 - 0.20), "seat", (10, 6), 3.0, 3))
            extra[k].extend(superellipsoid((0.02, 0.08, 0.025), (mid[0] - sx * 0.08, mid[1] + 0.25, zb2 - 0.08), "chrome", (8, 4), 3.0, 3))
            extra[k].extend(superellipsoid((0.03, 0.25, 0.015), (mid[0] - sx * 0.065, mid[1], zb2 - 0.01), "deco", (8, 4), 4.0, 3))

    def cabin_keep(m, i):
        if m.mat[i] not in ("paint", "trim_gloss"):
            return False
        c = m.v[list(m.f[i])].mean(0)
        return (p["rw0"] - 0.25 < c[1] < p["ws0"] + 0.02) and c[2] > belt_z(c[1]) - 0.05 and abs(c[0]) < float(body.w_sh(c[1])) + 0.05
    extra["chassis"].extend(inner_shell(parts["chassis"], 0.03,
                                        lambda x: "headliner", cabin_keep))
    # merge extras into parts
    for k, m in extra.items():
        if len(m.f):
            parts.setdefault(k, Mesh()).extend(m)
    # centre on the wheelbase so that the car's origin is between the axles
    yc = (p["axle_r"] + p["axle_f"]) / 2
    shift = np.array([0, -yc, 0])
    for k in parts:
        parts[k].v = parts[k].v + shift

    sw_c, tilt = info["steer"]
    frames = dict(
        wheel_rf_dummy=(p["track"], p["axle_f"] - yc, p["wheel_r"]),
        wheel_lf_dummy=(-p["track"], p["axle_f"] - yc, p["wheel_r"]),
        wheel_rb_dummy=(p["track"], p["axle_r"] - yc, p["wheel_r"]),
        wheel_lb_dummy=(-p["track"], p["axle_r"] - yc, p["wheel_r"]),
        f_steer=tuple(sw_c + shift),
        f_spdo=tuple(info["spdo"] + shift),
        f_tach=tuple(info["tach"] + shift),
    )
    xd, yh, zh = info["seat"]
    frames["ped_frontseat"] = (xd, yh - yc + 0.05, zh - 0.25)
    frames["ped_backseat"] = (xd, yh - 0.86 - yc + 0.05, zh - 0.23)
    hx = (p["head"]["x"][0] + p["head"]["x"][1]) / 2
    hz = (p["head"]["z"][0] + p["head"]["z"][1]) / 2
    frames["headlights"] = (hx, L - yc - 0.05, hz)
    frames["taillights"] = ((p["tail"]["x"][0] + p["tail"]["x"][1]) / 2, -yc + 0.05, (p["tail"]["z"][0] + p["tail"]["z"][1]) / 2)
    ex, ez = p["exhaust"][0]
    frames["exhaust"] = (ex, -yc - 0.05, ez)
    frames["engine"] = (0, (L - yc - 0.6) if not p.get("engine_rear") else (-yc + 1.0), p["wheel_r"] + 0.2)
    frames["petrolcap"] = (-float(body.w_sh(p["rw0"])) - 0.02, p["rw0"] - yc + 0.15, float(body.z_belt(p["rw0"])) - 0.12)
    frames["hookup"] = (0, -yc - 0.05, 0.35)
    frames["ped_arm"] = (-xd - 0.25, yh - yc + 0.1, zh + 0.25)
    # hinge positions for moving parts
    d = p["doors"]
    zh_ = float(body.z_belt(d["door_f"][1]))
    frames["door_rf_dummy"] = (float(body.w_sh(d["door_f"][1])), d["door_f"][1] - yc, zh_ - 0.25)
    frames["door_lf_dummy"] = (-float(body.w_sh(d["door_f"][1])), d["door_f"][1] - yc, zh_ - 0.25)
    if "door_r" in d:
        frames["door_rr_dummy"] = (float(body.w_sh(d["door_r"][1])), d["door_r"][1] - yc, zh_ - 0.25)
        frames["door_lr_dummy"] = (-float(body.w_sh(d["door_r"][1])), d["door_r"][1] - yc, zh_ - 0.25)
    frames["bonnet_dummy"] = (0, p["hood"][0] - yc, float(body.z_top(p["hood"][0])))
    by = p["boot"][1] if p["boot"][1] > 0.05 else p["rw1"]
    frames["boot_dummy"] = (0, by - yc, float(body.z_top(by)))
    frames["bump_front_dummy"] = (0, p["bump_f"] - yc, 0.4)
    frames["bump_rear_dummy"] = (0, p["bump_r"] - yc, 0.4)
    frames["windscreen_dummy"] = (0, (p["ws0"] + p["ws1"]) / 2 - yc, float(body.z_top((p["ws0"] + p["ws1"]) / 2)))
    return dict(parts=parts, frames=frames, info=info, body=body, yc=yc,
                wheel=wheel_mesh(p), caliper=caliper(p), steer=steering_wheel(p["interior"]["seats"]),
                needle_spdo=needle_mesh(info["dial_r"] * 0.9), needle_tach=needle_mesh(info["dial_r"] * 0.9),
                tilt=tilt, dial_up=info["dial_up"])

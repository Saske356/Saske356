"""Build one vehicle: textures, DFF + TXD (GTA SA / CRMP), GLB preview and renders.

Run with the Blender Python module:
    python -I build.py <preset_name> <out_dir> [--renders] [--quick]
"""
import math
import os
import sys
import json

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import numpy as np

import tex
import rw
from mesh import Mesh, corner_normals, unique_vertices, rot_x, rot_y, rot_z
import presets

LIVERIES = ["paint", "police", "taxi", "vinyl_stripes", "vinyl_tribal", "vinyl_camo"]

# GTA SA material colour codes
PRIMARY = (60, 255, 0)
LIGHTS = {  # vehicle light materials (SA) + indicator colours used by ImVehFt / VehFuncs
    "light_head_l": (255, 175, 0), "light_head_r": (0, 255, 200),
    "light_tail_l": (185, 255, 0), "light_tail_r": (255, 60, 0),
    "turn_fl": (255, 173, 0), "turn_fr": (0, 255, 198),
    "turn_rl": (184, 255, 0), "turn_rr": (255, 59, 0),
}


def build_textures(p, livery="paint", size="hi"):
    I = p["interior"]
    big = 2048 if size == "hi" else 1024
    car = dict(len=p["len"], belt=float(np.interp(p["len"] * 0.5, *zip(*p["z_belt"]))),
               sill=float(np.interp(p["len"] * 0.5, *zip(*p["z_sill"]))),
               door_x0=p["doors"]["door_f"][0], door_x1=p["doors"]["door_f"][1])
    T = {
        "v_body": tex.livery(livery, car, big, big // 2),
        "v_headlight": tex.headlight(512, 256, "led" if p["head"].get("drl") else "halogen"),
        "v_taillight": tex.taillight(512, 256, p["tail"]["pattern"]),
        "v_grille": tex.grille_honeycomb(256) if p["grille"]["style"] in ("honeycomb", "horseshoe") else tex.grille_slats(256),
        "v_plate": plate_image(p),
        "v_tire": tex.tire(1024, 256),
        "v_rim": tex.rim(256, finish={"forged": "gunmetal", "turbine": "black", "offroad": "black", "steel": "silver"}.get(p["rim_style"], "silver")),
        "v_disc": tex.brake_disc(256),
        "v_badge": tex.badge(128, p["name"][0].upper()),
        "v_leather": tex.leather(512, I["leather"], 1, perforated=I["seats"] in ("lux", "bucket"), stitch=I["stitch"] and I["stitch"] + (255,)),
        "v_leather2": tex.leather(256, tuple(int(c * 0.8) for c in I["leather"]), 2),
        "v_carpet": tex.carpet(256),
        "v_dash": tex.plastic(256, (30, 30, 32), 4),
        "v_trim": tex.carbon(256) if I["trim"] == "carbon" else tex.plastic(256, (22, 22, 24), 5, 3),
        "v_deco": tex.carbon(256) if I["trim"] == "carbon" else (tex.wood(512) if I["trim"] == "wood" else tex.brushed(256, (190, 192, 198), 8)),
        "v_gauges": tex.gauges(1024, 512, p["gauges"]["max"], p["gauges"]["red"]),
        "v_screen": tex.screen(512, 256),
        "v_climate": tex.climate_panel(256, 128),
        "v_fabric": tex.fabric(256, (150, 148, 144)),
        "v_doorcard": tex.leather(256, tuple(int(c * 0.7) for c in I["leather"]), 3),
    }
    return T


def plate_image(p):
    nums = {"compact_sedan": ("В001КР", "77"), "classic_sedan": ("Е777КХ", "50"), "exec_sedan": ("О001ОО", "99"),
            "suv": ("Т123АУ", "177"), "supercar": ("С555ММ", "777"), "hypercar": ("А001АА", "797")}
    n, r = nums.get(p["name"], ("А777АА", "77"))
    return tex.plate_ru(512, 112, n, r)


def material_specs(p, paint_rgb=(200, 200, 205)):
    """name -> (display spec for Blender/GLB, GTA spec for DFF)."""
    I = p["interior"]
    M = {}

    def add(name, disp, gta):
        M[name] = (disp, gta)
    add("paint", dict(color=paint_rgb, tex="v_body", metal=0.55, rough=0.28, coat=1.0, gta_paint=True),
        dict(color=PRIMARY + (255,), texture="v_body", env=0.35, spec=0.6, reflect=0.45))
    add("glass", dict(color=(12, 16, 20), rough=0.03, alpha=0.38),
        dict(color=(10, 10, 10, 120), env=0.5, spec=0.9, reflect=0.6))
    add("trim_gloss", dict(color=(8, 8, 9), rough=0.12), dict(color=(10, 10, 10, 255), env=0.25, spec=0.6))
    add("under", dict(color=(16, 16, 17), rough=0.85), dict(color=(18, 18, 18, 255)))
    add("gap", dict(color=(6, 6, 6), rough=0.9), dict(color=(6, 6, 6, 255)))
    add("liner", dict(color=(14, 14, 15), rough=0.95), dict(color=(14, 14, 14, 255)))
    add("lamp_wall", dict(color=(70, 72, 76), metal=1, rough=0.2), dict(color=(70, 72, 76, 255), env=0.4))
    add("head_housing", dict(color=(255, 255, 255), tex="v_headlight", metal=0.8, rough=0.15), dict(color=(255, 255, 255, 255), texture="v_headlight", env=0.3))
    add("tail_housing", dict(color=(255, 255, 255), tex="v_taillight", rough=0.3), dict(color=(255, 255, 255, 255), texture="v_taillight"))
    add("lens", dict(color=(235, 240, 245), rough=0.02, alpha=0.12), dict(color=(255, 255, 255, 50), env=0.6, spec=1.0))
    add("lens_red", dict(color=(200, 10, 14), rough=0.05, alpha=0.55), dict(color=(190, 10, 10, 150), env=0.4, spec=1.0))
    add("lens_amber", dict(color=(255, 140, 0), rough=0.05, alpha=0.5), dict(color=(255, 140, 0, 150), env=0.4))
    for k, c in LIGHTS.items():
        if k.startswith("light_head"):
            disp = dict(color=(235, 238, 245), emit=(255, 250, 240), emit_strength=0.0, rough=0.2)
        elif k.startswith("light_tail"):
            disp = dict(color=(150, 8, 10), emit=(255, 20, 16), emit_strength=0.0, rough=0.3)
        else:
            disp = dict(color=(230, 120, 0), emit=(255, 140, 0), emit_strength=0.0, rough=0.3)
        add(k, disp, dict(color=c + (255,), texture="vehiclelights128"))
    add("fog", dict(color=(240, 240, 240), emit=(255, 250, 235), emit_strength=0.0), dict(color=(240, 240, 240, 255), env=0.3))
    add("grille_back", dict(color=(5, 5, 6), rough=0.8), dict(color=(5, 5, 5, 255)))
    add("grille_hc", dict(color=(255, 255, 255), tex="v_grille", tex_alpha=True, rough=0.4), dict(color=(255, 255, 255, 255), texture="v_grille"))
    add("grille_slat", dict(color=(255, 255, 255), tex="v_grille", rough=0.3, metal=0.6), dict(color=(255, 255, 255, 255), texture="v_grille", env=0.4))
    add("chrome", dict(color=(230, 232, 236), metal=1.0, rough=0.06), dict(color=(210, 210, 215, 255), env=0.9, spec=1.0, reflect=0.9))
    add("badge", dict(color=(255, 255, 255), tex="v_badge", metal=0.6, rough=0.15), dict(color=(255, 255, 255, 255), texture="v_badge", env=0.6))
    add("plate", dict(color=(255, 255, 255), tex="v_plate", rough=0.4), dict(color=(255, 255, 255, 255), texture="v_plate"))
    add("mirror", dict(color=(240, 240, 245), metal=1.0, rough=0.01), dict(color=(220, 220, 225, 255), env=1.0, reflect=1.0))
    # wheels
    add("tire", dict(color=(255, 255, 255), tex="v_tire", rough=0.85), dict(color=(255, 255, 255, 255), texture="v_tire"))
    add("rim", dict(color=(255, 255, 255), tex="v_rim", metal=1.0, rough=0.22), dict(color=(255, 255, 255, 255), texture="v_rim", env=0.6, spec=0.8))
    add("rim_in", dict(color=(120, 122, 126), metal=1.0, rough=0.4), dict(color=(120, 122, 126, 255), env=0.3))
    add("rim_dark", dict(color=(50, 50, 54), metal=0.8, rough=0.4), dict(color=(50, 50, 54, 255)))
    add("disc", dict(color=(255, 255, 255), tex="v_disc", metal=1.0, rough=0.45), dict(color=(255, 255, 255, 255), texture="v_disc"))
    add("caliper", dict(color=(200, 20, 24), rough=0.3), dict(color=(200, 20, 24, 255), env=0.2))
    # interior
    add("seat", dict(color=(255, 255, 255), tex="v_leather", rough=0.55), dict(color=(255, 255, 255, 255), texture="v_leather"))
    add("seat_side", dict(color=(255, 255, 255), tex="v_leather2", rough=0.55), dict(color=(255, 255, 255, 255), texture="v_leather2"))
    add("carpet", dict(color=(255, 255, 255), tex="v_carpet", rough=1.0), dict(color=(255, 255, 255, 255), texture="v_carpet"))
    add("dash", dict(color=(255, 255, 255), tex="v_dash", rough=0.7), dict(color=(255, 255, 255, 255), texture="v_dash"))
    add("trim", dict(color=(255, 255, 255), tex="v_trim", rough=0.35), dict(color=(255, 255, 255, 255), texture="v_trim", env=0.15))
    add("deco", dict(color=(255, 255, 255), tex="v_deco", rough=0.2, metal=0.3 if I["trim"] == "alu" else 0.0), dict(color=(255, 255, 255, 255), texture="v_deco", env=0.3))
    add("gauges", dict(color=(255, 255, 255), tex="v_gauges", rough=0.2, emit=(255, 255, 255), emit_strength=0.0), dict(color=(255, 255, 255, 255), texture="v_gauges"))
    add("needle", dict(color=(255, 70, 20), emit=(255, 70, 20), emit_strength=1.5), dict(color=(255, 70, 20, 255)))
    add("screen", dict(color=(255, 255, 255), tex="v_screen", rough=0.05, emit=(255, 255, 255), emit_strength=0.0), dict(color=(255, 255, 255, 255), texture="v_screen", env=0.3))
    add("climate", dict(color=(255, 255, 255), tex="v_climate", rough=0.3), dict(color=(255, 255, 255, 255), texture="v_climate"))
    add("vent", dict(color=(12, 12, 13), rough=0.6), dict(color=(12, 12, 12, 255)))
    add("steer_leather", dict(color=(28, 27, 26), rough=0.5), dict(color=(28, 27, 26, 255)))
    add("steer_hub", dict(color=(20, 20, 21), rough=0.45), dict(color=(20, 20, 21, 255)))
    add("accent", dict(color=(220, 30, 30), rough=0.4), dict(color=(220, 30, 30, 255)))
    add("plastic_dark", dict(color=(18, 18, 19), rough=0.55), dict(color=(18, 18, 19, 255)))
    add("metal_dark", dict(color=(60, 60, 62), metal=1, rough=0.4), dict(color=(60, 60, 62, 255)))
    add("door_card", dict(color=(255, 255, 255), tex="v_doorcard", rough=0.6), dict(color=(255, 255, 255, 255), texture="v_doorcard"))
    add("headliner", dict(color=(255, 255, 255), tex="v_fabric", rough=0.95), dict(color=(255, 255, 255, 255), texture="v_fabric"))
    return M


# ---------------------------------------------------------------- DFF
def geometry(mesh, specs, angle=40.0):
    T, U, M = mesh.tris()
    if not len(T):
        return None
    N = corner_normals(mesh.v, T, angle)
    V, Nn, Uu, tris = unique_vertices(mesh.v, T, U, N)
    names = sorted(set(M))
    ids = [names.index(m) for m in M]
    mats = [rw.Material(**specs[n][1]) for n in names]
    return rw.Geometry(V, Nn, Uu, tris, ids, mats)


def dent(m, amount=0.025, seed=1):
    """Damaged panel: smooth random dents (for *_dam atomics)."""
    r = np.random.default_rng(seed)
    c = m.v.mean(0)
    out = m.copy()
    k = r.normal(size=(3, 3)) * 6
    d = np.sin(out.v @ k[0]) * np.sin(out.v @ k[1] + 1.3)
    out.v = out.v - (out.v - c) / (np.linalg.norm(out.v - c, axis=1, keepdims=True) + 1e-9) * (d[:, None] * amount)
    return out


def split_by_material(m, names):
    keep = [x in names for x in m.mat]
    return m.subset(keep), m.subset([not k for k in keep])


INTERIOR_MATS = {"seat", "seat_side", "carpet", "dash", "trim", "deco", "gauges", "screen", "climate", "vent",
                 "steer_leather", "steer_hub", "accent", "metal_dark", "door_card", "headliner", "mirror_int"}


def build_dff(car, p, specs, path):
    F = car["frames"]
    parts = car["parts"]
    frames = [rw.Frame(p["name"]), rw.Frame("chassis_dummy", 0)]
    atomics = []

    def add_frame(name, parent, pos=(0, 0, 0), rot=None):
        R = None
        if rot is not None:
            R = tuple(tuple(float(x) for x in rot[:, k]) for k in range(3))
        frames.append(rw.Frame(name, parent, tuple(float(x) for x in pos), R))
        return len(frames) - 1

    def add_atomic(frame_idx, mesh, angle=40.0):
        g = geometry(mesh, specs, angle)
        if g is not None:
            atomics.append((frame_idx, g))
    chassis = parts["chassis"]
    inter, ext = split_by_material(chassis, INTERIOR_MATS)
    add_atomic(add_frame("chassis", 1), ext)
    add_atomic(add_frame("chassis_vlo", 1), car["vlo"])
    add_atomic(add_frame("interior", 1), inter)
    for nm in ("wheel_rf_dummy", "wheel_lf_dummy", "wheel_rb_dummy", "wheel_lb_dummy"):
        fi = add_frame(nm, 1, F[nm])
        if nm == "wheel_rf_dummy":
            add_atomic(add_frame("wheel", fi), car["wheel"], 50)
    for part in ("door_lf", "door_rf", "door_lr", "door_rr", "bonnet", "boot", "bump_front", "bump_rear", "windscreen"):
        if part not in parts or not len(parts[part].f):
            continue
        dn = part + "_dummy"
        pos = np.array(F.get(dn, (0, 0, 0)))
        fi = add_frame(dn, 1, pos)
        local = parts[part].transformed(t=-pos)
        add_atomic(add_frame(part + "_ok", fi), local)
        if part != "windscreen":
            add_atomic(add_frame(part + "_dam", fi), dent(local, 0.02, hash(part) % 1000))
    # steering wheel and gauge needles (VehFuncs/ImVehFt style nodes)
    sw_c = np.array(F["f_steer"])
    add_atomic(add_frame("f_steer", 1, sw_c, rot_x(car["tilt"])), car["steer"])
    tilt = math.atan2(car["dial_up"][1], car["dial_up"][2])
    Rn = rot_x(-tilt) @ rot_y(math.radians(-225.0))
    add_atomic(add_frame("f_spdo", 1, F["f_spdo"], Rn), car["needle_spdo"])
    add_atomic(add_frame("f_tach", 1, F["f_tach"], Rn), car["needle_tach"])
    for nm in ("ped_frontseat", "ped_backseat", "headlights", "taillights", "exhaust", "engine", "petrolcap", "hookup", "ped_arm"):
        if nm in F:
            add_frame(nm, 1, F[nm])
    col = collision(car, p)
    size = rw.write_dff(path, frames, atomics, col)
    tris = sum(len(g.tris) for _, g in atomics)
    return size, tris, [f.name for f in frames]


def collision(car, p):
    yc = car["yc"]
    body = car["body"]
    L = p["len"]
    w = max(x for _, x in p["w_sh"])
    zs = min(z for _, z in p["z_sill"])
    zb = float(np.mean([z for _, z in p["z_belt"]]))
    zt = max(z for _, z in p["z_top"])
    boxes = [((-w, -yc, zs + 0.05), (w, L - yc, zb), rw.SURF_CAR),
             ((-w + 0.12, p["rw0"] - yc, zb), (w - 0.12, p["ws0"] - yc, zt - 0.02), rw.SURF_CAR)]
    spheres = []
    for y in (0.35, L - 0.35):
        for sx in (-1, 1):
            spheres.append((sx * (w - 0.35), y - yc, zb - 0.15, 0.35, rw.SURF_PANEL))
    return rw.build_col3(p["name"], spheres, boxes)


def build_txd(textures, path, used):
    items = [(k, v) for k, v in textures.items() if k in used]
    return rw.write_txd(path, [(k, v, None, True) for k, v in items])


def used_textures(specs):
    return {g.get("texture") for _, g in specs.values() if g.get("texture")} - {"vehiclelights128"}


# ---------------------------------------------------------------- Blender
def blender_scene(car, p, specs, textures, paint_rgb):
    import blend
    blend.reset()
    imgs = {k: blend.image(k, v) for k, v in textures.items()}
    mats = {}
    for name, (disp, _) in specs.items():
        mats[name] = blend.material(name, disp, imgs)
    F = car["frames"]
    root = blend.empty(p["name"])
    objs = [root]
    parts = car["parts"]
    chassis = parts["chassis"]
    inter, ext = split_by_material(chassis, INTERIOR_MATS)
    objs.append(blend.mesh_object("chassis", ext, mats, root))
    objs.append(blend.mesh_object("interior", inter, mats, root))
    for part in ("door_lf", "door_rf", "door_lr", "door_rr", "bonnet", "boot", "bump_front", "bump_rear", "windscreen"):
        if part not in parts or not len(parts[part].f):
            continue
        pos = np.array(F.get(part + "_dummy", (0, 0, 0)))
        d = blend.empty(part + "_dummy", tuple(pos), root)
        objs.append(d)
        objs.append(blend.mesh_object(part + "_ok", parts[part].transformed(t=-pos), mats, d))
    for nm in ("wheel_rf_dummy", "wheel_lf_dummy", "wheel_rb_dummy", "wheel_lb_dummy"):
        d = blend.empty(nm, F[nm], root)
        objs.append(d)
        left = "_l" in nm
        wm = car["wheel"].transformed(rot_z(math.pi)) if left else car["wheel"]
        cm = car["caliper"].transformed(rot_z(math.pi)) if left else car["caliper"]
        objs.append(blend.mesh_object(nm.replace("_dummy", ""), wm, mats, d, smooth_angle=50))
        objs.append(blend.mesh_object(nm.replace("_dummy", "_caliper"), cm, mats, d))
    import mathutils
    sw = blend.empty("f_steer", F["f_steer"], root)
    sw.rotation_euler = (car["tilt"], 0, 0)
    objs.append(sw)
    objs.append(blend.mesh_object("steering_wheel", car["steer"], mats, sw))
    tilt = math.atan2(car["dial_up"][1], car["dial_up"][2])
    for nm, key in (("f_spdo", "needle_spdo"), ("f_tach", "needle_tach")):
        e = blend.empty(nm, F[nm], root)
        M = mathutils.Matrix((rot_x(-tilt) @ rot_y(math.radians(-225.0))).tolist())
        e.rotation_mode = "QUATERNION"
        e.rotation_quaternion = M.to_quaternion()
        objs.append(e)
        objs.append(blend.mesh_object(nm + "_needle", car[key], mats, e))
    for nm in ("ped_frontseat", "headlights", "taillights", "exhaust"):
        objs.append(blend.empty(nm, F[nm], root))
    return root, objs, mats


def set_lights(mats, head=0.0, tail=0.0, turn_l=0.0, turn_r=0.0, dash=0.0):
    def s(name, v):
        m = mats.get(name)
        if m:
            m.node_tree.nodes["Principled BSDF"].inputs["Emission Strength"].default_value = v
    for k in ("light_head_l", "light_head_r", "fog"):
        s(k, head)
    for k in ("light_tail_l", "light_tail_r"):
        s(k, tail)
    s("turn_fl", turn_l)
    s("turn_rl", turn_l)
    s("turn_fr", turn_r)
    s("turn_rr", turn_r)
    for k in ("gauges", "screen"):
        s(k, dash)


def prepare_glb(mats):
    """glTF: plain texture -> base colour (the viewer tints the paint)."""
    for name, m in mats.items():
        nt = m.node_tree
        mix = [n for n in nt.nodes if n.type == "MIX"]
        texn = [n for n in nt.nodes if n.type == "TEX_IMAGE"]
        if mix and texn:
            bsdf = nt.nodes["Principled BSDF"]
            nt.links.new(texn[0].outputs["Color"], bsdf.inputs["Base Color"])
            for n in mix:
                nt.nodes.remove(n)


def main():
    name = sys.argv[1]
    out = sys.argv[2]
    renders = "--renders" in sys.argv
    quick = "--quick" in sys.argv
    os.makedirs(out, exist_ok=True)
    p = {c["name"]: c for c in presets.CARS}[name]
    from car import build_car
    from body import Body
    car = build_car(p)
    # low LOD body for chassis_vlo
    lo = Body(p, low=True).meshes(0.0, 0.0)
    vlo = Mesh()
    for k, m in lo.items():
        vlo.extend(m)
    vlo.v = vlo.v + np.array([0, -car["yc"], 0])
    vlo.remap_mat({"trim_gloss": "glass", "gap": "under"})
    car["vlo"] = vlo
    paint = tuple(p.get("paint", (200, 200, 205)))
    specs = material_specs(p, paint)
    info = {"name": name, "title": p["title"], "liveries": {}}
    # textures + TXD per livery, one DFF
    base_tex = None
    for liv in (LIVERIES if not quick else ["paint"]):
        T = build_textures(p, liv)
        if base_tex is None:
            base_tex = T
        suffix = "" if liv == "paint" else "_" + liv
        tsize = build_txd(T, os.path.join(out, name + suffix + ".txd"), used_textures(specs))
        tex.save_png(T["v_body"], os.path.join(out, "livery_%s.png" % liv))
        info["liveries"][liv] = tsize
    os.makedirs(os.path.join(out, "textures"), exist_ok=True)
    for k, v in base_tex.items():
        tex.save_png(v, os.path.join(out, "textures", k + ".png"))
    size, tris, fnames = build_dff(car, p, specs, os.path.join(out, name + ".dff"))
    info.update(dff_bytes=size, triangles=tris, frames=fnames)
    # verify file structure
    with open(os.path.join(out, name + ".dff"), "rb") as fh:
        rw.walk(fh.read())
    # Blender: GLB + renders
    import blend
    root, objs, mats = blender_scene(car, p, specs, base_tex, paint)
    if renders:
        render_set(p, out, mats, quick)
    prepare_glb(mats)
    blend.export_glb(os.path.join(out, name + ".glb"), objs)
    info["glb_bytes"] = os.path.getsize(os.path.join(out, name + ".glb"))
    with open(os.path.join(out, "info.json"), "w") as fh:
        json.dump(info, fh, ensure_ascii=False, indent=1)
    print("BUILT", json.dumps({k: v for k, v in info.items() if k != "frames"}, ensure_ascii=False))


def render_set(p, out, mats, quick=False):
    import blend
    import bpy
    L = p["len"]
    s = L / 4.4
    blend.studio()
    res = (1280, 720) if not quick else (800, 450)
    smp = 48 if not quick else 20
    set_lights(mats, head=2.0, tail=0.0, dash=1.0)
    blend.camera((6.2 * s, 6.0 * s, 2.0 * s), (0, 0.2, 0.55), 40)
    blend.render(os.path.join(out, "render_front.png"), res, smp)
    set_lights(mats, head=2.0, tail=3.0, turn_l=0.0, turn_r=0.0, dash=1.0)
    blend.camera((-6.0 * s, -6.2 * s, 2.2 * s), (0, -0.2, 0.55), 40)
    blend.render(os.path.join(out, "render_rear.png"), res, smp)
    if quick:
        return
    blend.camera((0.0, -0.0, 9.0 * s), (0, 0, 0), 45)
    # interior from the driver's eye
    yh = p["ws1"] - (0.18 if p.get("engine_rear") else 0.30) - (p["axle_r"] + p["axle_f"]) / 2
    zeye = float(np.interp(p["ws1"], *zip(*p["z_sill"]))) + 0.08 + 0.95 if p["name"] != "supercar" else 1.0
    zeye = min(zeye, float(np.interp(p["ws1"] - 0.3, *zip(*p["z_top"]))) - 0.12)
    cam = blend.camera((0.05, yh - 0.25, zeye), (-0.35, yh + 1.2, zeye - 0.38), 22)
    cam.data.lens = 18
    for o in bpy.data.objects:
        if o.name in ("door_lf_ok",):
            o.hide_render = True
    set_lights(mats, head=0, tail=0, dash=2.0)
    blend.render(os.path.join(out, "render_interior.png"), res, 64)
    for o in bpy.data.objects:
        o.hide_render = False
    # night with lights + left indicator
    bpy.data.objects.remove(bpy.data.objects["light"], do_unlink=True) if "light" in bpy.data.objects else None
    for o in [o for o in bpy.data.objects if o.type == "LIGHT"]:
        o.data.energy *= 0.04
    bpy.context.scene.world.node_tree.nodes["Background"].inputs["Strength"].default_value = 0.04
    set_lights(mats, head=25.0, tail=8.0, turn_l=20.0, dash=2.0)
    blend.camera((5.0 * s, 7.2 * s, 1.3 * s), (0, 0.6, 0.6), 40)
    blend.render(os.path.join(out, "render_night.png"), res, 64)


if __name__ == "__main__":
    main()

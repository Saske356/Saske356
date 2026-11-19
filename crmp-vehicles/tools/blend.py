"""Blender side: materials, objects, studio and rendering, glTF export."""
import math
import os
import bpy
import numpy as np
from mesh import corner_normals

IMAGES = {}


def reset():
    bpy.ops.wm.read_factory_settings(use_empty=True)
    IMAGES.clear()


def image(name, arr):
    """arr: RGBA uint8 in image order (row 0 = top)."""
    if name in IMAGES:
        return IMAGES[name]
    h, w = arr.shape[:2]
    im = bpy.data.images.new(name, w, h, alpha=True)
    px = (np.flipud(arr).astype(np.float32) / 255.0).reshape(-1)
    im.pixels.foreach_set(px)
    im.pack()
    im.file_format = "PNG"
    IMAGES[name] = im
    return im


def material(name, spec, textures):
    """spec keys: color (rgb 0-255), tex (texture name), metal, rough, coat,
    alpha, emit (rgb), emit_strength, transmission"""
    m = bpy.data.materials.get(name)
    if m:
        return m
    m = bpy.data.materials.new(name)
    m.use_nodes = True
    nt = m.node_tree
    bsdf = nt.nodes.get("Principled BSDF")
    col = [c / 255 for c in spec.get("color", (200, 200, 200))]
    lin = [srgb_to_lin(c) for c in col]
    bsdf.inputs["Base Color"].default_value = (*lin, 1)
    bsdf.inputs["Metallic"].default_value = spec.get("metal", 0.0)
    bsdf.inputs["Roughness"].default_value = spec.get("rough", 0.5)
    if spec.get("coat"):
        bsdf.inputs["Coat Weight"].default_value = spec["coat"]
        bsdf.inputs["Coat Roughness"].default_value = 0.03
    if spec.get("tex"):
        tn = nt.nodes.new("ShaderNodeTexImage")
        tn.image = textures[spec["tex"]]
        tn.label = spec["tex"]
        tn.interpolation = "Linear"
        if col != [1, 1, 1] and spec.get("tint", True):
            mix = nt.nodes.new("ShaderNodeMix")
            mix.data_type = "RGBA"
            mix.blend_type = "MULTIPLY"
            mix.inputs["Factor"].default_value = 1.0
            nt.links.new(tn.outputs["Color"], mix.inputs[6])
            mix.inputs[7].default_value = (*lin, 1)
            nt.links.new(mix.outputs[2], bsdf.inputs["Base Color"])
        else:
            nt.links.new(tn.outputs["Color"], bsdf.inputs["Base Color"])
        if spec.get("tex_alpha"):
            nt.links.new(tn.outputs["Alpha"], bsdf.inputs["Alpha"])
    a = spec.get("alpha", 1.0)
    if a < 1 or spec.get("tex_alpha"):
        bsdf.inputs["Alpha"].default_value = a
        try:
            m.surface_render_method = "BLENDED"
        except Exception:
            pass
    if spec.get("transmission"):
        bsdf.inputs["Transmission Weight"].default_value = spec["transmission"]
        bsdf.inputs["IOR"].default_value = 1.5
    if spec.get("emit"):
        e = [srgb_to_lin(c / 255) for c in spec["emit"]]
        bsdf.inputs["Emission Color"].default_value = (*e, 1)
        bsdf.inputs["Emission Strength"].default_value = spec.get("emit_strength", 0.0)
    m["gta"] = list(spec.get("gta", ()))
    m.diffuse_color = (*lin, a)
    return m


def srgb_to_lin(c):
    return c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4


def mesh_object(name, msh, mats, parent=None, loc=(0, 0, 0), smooth_angle=40):
    T, U, M = msh.tris()
    V = msh.v
    me = bpy.data.meshes.new(name)
    if len(T):
        P = V[T].reshape(-1, 3) - np.asarray(loc)
        n = len(T)
        me.vertices.add(n * 3)
        me.vertices.foreach_set("co", P.reshape(-1).astype(np.float32))
        me.loops.add(n * 3)
        me.loops.foreach_set("vertex_index", np.arange(n * 3, dtype=np.int32))
        me.polygons.add(n)
        me.polygons.foreach_set("loop_start", np.arange(0, n * 3, 3, dtype=np.int32))
        me.polygons.foreach_set("loop_total", np.full(n, 3, np.int32))
        names = sorted(set(M))
        for nm in names:
            me.materials.append(mats[nm])
        mi = np.array([names.index(x) for x in M], np.int32)
        me.polygons.foreach_set("material_index", mi)
        uv = me.uv_layers.new(name="UVMap")
        uv.data.foreach_set("uv", U.reshape(-1).astype(np.float32))
        me.update()
        me.validate()
        # merge coincident verts so smoothing works across triangles
        import bmesh
        bm = bmesh.new()
        bm.from_mesh(me)
        bmesh.ops.remove_doubles(bm, verts=bm.verts, dist=1e-5)
        bm.to_mesh(me)
        bm.free()
        cn = corner_normals(np.array([v.co[:] for v in me.vertices]),
                            np.array([[me.loops[i].vertex_index for i in p.loop_indices] for p in me.polygons]),
                            smooth_angle)
        me.normals_split_custom_set(cn.reshape(-1, 3).tolist())
    ob = bpy.data.objects.new(name, me)
    bpy.context.scene.collection.objects.link(ob)
    ob.location = loc
    if parent:
        ob.parent = parent
    return ob


def empty(name, loc=(0, 0, 0), parent=None, rot=None):
    ob = bpy.data.objects.new(name, None)
    ob.empty_display_size = 0.1
    bpy.context.scene.collection.objects.link(ob)
    ob.location = loc
    if rot is not None:
        ob.rotation_mode = "XYZ"
        ob.rotation_euler = rot
    if parent:
        ob.parent = parent
    return ob


# ------------------------------------------------------------------ studio
def studio(dark=False, floor=True):
    sc = bpy.context.scene
    sc.render.engine = "CYCLES"
    sc.cycles.device = "CPU"
    sc.cycles.samples = 48
    sc.cycles.use_denoising = True
    try:
        sc.cycles.denoiser = "OPENIMAGEDENOISE"
    except Exception:
        pass
    sc.view_settings.view_transform = "AgX"
    sc.view_settings.look = "AgX - Medium High Contrast" if not dark else "AgX - High Contrast"
    w = bpy.data.worlds.new("studio")
    sc.world = w
    w.use_nodes = True
    nt = w.node_tree
    bg = nt.nodes["Background"]
    tc = nt.nodes.new("ShaderNodeTexCoord")
    sep = nt.nodes.new("ShaderNodeSeparateXYZ")
    ramp = nt.nodes.new("ShaderNodeValToRGB")
    nt.links.new(tc.outputs["Generated"], sep.inputs[0])
    nt.links.new(sep.outputs["Z"], ramp.inputs[0])
    cr = ramp.color_ramp
    cr.elements[0].position = 0.0
    cr.elements[0].color = (0.02, 0.02, 0.025, 1) if not dark else (0.003, 0.003, 0.004, 1)
    cr.elements[1].position = 1.0
    cr.elements[1].color = (0.55, 0.62, 0.75, 1) if not dark else (0.02, 0.025, 0.04, 1)
    e = cr.elements.new(0.5)
    e.color = (0.9, 0.92, 0.95, 1) if not dark else (0.05, 0.05, 0.06, 1)
    e2 = cr.elements.new(0.47)
    e2.color = (0.12, 0.12, 0.13, 1) if not dark else (0.01, 0.01, 0.012, 1)
    nt.links.new(ramp.outputs["Color"], bg.inputs["Color"])
    bg.inputs["Strength"].default_value = 1.0
    if floor:
        bpy.ops.mesh.primitive_plane_add(size=60, location=(0, 0, 0))
        fl = bpy.context.object
        fm = bpy.data.materials.new("floor")
        fm.use_nodes = True
        b = fm.node_tree.nodes["Principled BSDF"]
        b.inputs["Base Color"].default_value = (0.05, 0.05, 0.055, 1) if not dark else (0.012, 0.012, 0.014, 1)
        b.inputs["Roughness"].default_value = 0.35
        fl.data.materials.append(fm)
    for loc, size, en, rot in [((0, 0, 7), 7, 900 if not dark else 60, (0, 0, 0)),
                               ((-6, -5, 3), 4, 500 if not dark else 40, (math.radians(70), 0, math.radians(-50))),
                               ((6, 4, 3), 4, 350 if not dark else 30, (math.radians(70), 0, math.radians(130)))]:
        ld = bpy.data.lights.new("key", "AREA")
        ld.size = size
        ld.energy = en
        lo = bpy.data.objects.new("light", ld)
        lo.location = loc
        lo.rotation_euler = rot
        sc.collection.objects.link(lo)


def camera(loc, target, lens=50, name="cam"):
    cd = bpy.data.cameras.new(name)
    cd.lens = lens
    co = bpy.data.objects.new(name, cd)
    bpy.context.scene.collection.objects.link(co)
    co.location = loc
    d = np.asarray(target, float) - np.asarray(loc, float)
    import mathutils
    co.rotation_euler = mathutils.Vector(d).to_track_quat("-Z", "Y").to_euler()
    bpy.context.scene.camera = co
    return co


def render(path, res=(1280, 720), samples=None):
    sc = bpy.context.scene
    sc.render.resolution_x, sc.render.resolution_y = res
    sc.render.resolution_percentage = 100
    if samples:
        sc.cycles.samples = samples
    sc.render.filepath = path
    sc.render.image_settings.file_format = "PNG"
    bpy.ops.render.render(write_still=True)


def export_glb(path, objects):
    bpy.ops.object.select_all(action="DESELECT")
    for o in objects:
        o.select_set(True)
    bpy.ops.export_scene.gltf(filepath=path, export_format="GLB", use_selection=True,
                              export_apply=False, export_yup=True, export_extras=True,
                              export_image_format="WEBP" if False else "JPEG")

import sys, os, math
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import numpy as np
import blend, tex
from body import Body
import presets

name = sys.argv[-2]
out = sys.argv[-1]
p = {c["name"]: c for c in presets.CARS}[name]
blend.reset()
texs = {"liv": blend.image("liv", tex.livery("police", p and dict(len=p["len"], belt=0.93, sill=0.25, door_x0=p["doors"]["door_f"][0], door_x1=p["doors"]["door_f"][1]), 1024, 512))}
mats = {
    "paint": blend.material("paint", dict(color=(255, 255, 255), tex="liv", metal=0.4, rough=0.3, coat=1.0), texs),
    "glass": blend.material("glass", dict(color=(20, 25, 30), rough=0.02, alpha=0.35), texs),
    "trim_gloss": blend.material("trim", dict(color=(10, 10, 10), rough=0.15), texs),
    "under": blend.material("under", dict(color=(15, 15, 15), rough=0.8), texs),
    "gap": blend.material("gap", dict(color=(5, 5, 5), rough=0.9), texs),
}
b = Body(p)
parts = b.meshes()
for k, m in parts.items():
    o = blend.mesh_object(k, m.transformed(t=(0, -p["len"] / 2, 0)), mats)
    print(k, m.tri_count())
blend.studio()
L = p["len"]
blend.camera((6.5, 5.5, 2.6), (0, 0, 0.6), 45)
blend.render(out + "_a.png", (960, 540), 24)
blend.camera((-5.5, -6.0, 2.0), (0, 0, 0.6), 45)
blend.render(out + "_b.png", (960, 540), 24)
blend.camera((9.0, 0, 0.8), (0, 0, 0.7), 50)
blend.render(out + "_c.png", (960, 540), 16)

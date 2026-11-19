"""Vehicle presets (original designs, metres).  ty = distance from the rear.

All the cars share one generator; these numbers are what makes each one a
different car.  To add a car: copy a preset, change the profiles, run
build_all.py.
"""


def cuts(p):
    c = [p["ws0"], p["ws1"], p["rw0"], p["rw1"], p["bump_f"], p["bump_r"],
         p["hood"][0], p["boot"][1], p["ws0"] + p.get("sail", 0.18), p["rw0"] - p.get("cpillar", 0.12)]
    for a, b in p["doors"].values():
        c += [a, b]
    for a, b in p.get("bpillars", []):
        c += [a, b]
    return c


COMPACT = dict(
    name="compact_sedan", title="Компакт-седан «Волжанка С»", kind="car",
    len=4.35, axle_r=0.84, axle_f=3.33, wheel_r=0.295, rim_r=0.19, tire_w=0.19, track=0.715,
    arch_r=0.345, spokes=5, rim_style="split",
    z_top=[(0, 0.74), (0.12, 0.92), (0.45, 0.975), (0.82, 1.0), (1.45, 1.41), (2.0, 1.43), (2.55, 1.40), (3.30, 0.985), (3.7, 0.93), (4.15, 0.83), (4.35, 0.70)],
    z_belt=[(0, 0.72), (0.4, 0.92), (1.0, 0.945), (2.0, 0.935), (3.3, 0.91), (3.9, 0.84), (4.35, 0.68)],
    z_sill=[(0, 0.33), (0.25, 0.26), (0.8, 0.23), (3.5, 0.22), (4.1, 0.24), (4.35, 0.33)],
    w_sh=[(0, 0.75), (0.45, 0.825), (1.2, 0.84), (3.2, 0.84), (3.95, 0.815), (4.35, 0.73)],
    w_bot=[(0, 0.72), (0.45, 0.79), (1.2, 0.80), (3.2, 0.80), (3.95, 0.78), (4.35, 0.70)],
    w_roof=[(0.6, 0.50), (1.45, 0.61), (2.0, 0.635), (2.55, 0.62), (3.35, 0.50)],
    cabin_h=0.32, crown=0.05, tumble=0.11, bulge=0.018, flare=0.01,
    ws0=3.28, ws1=2.56, rw1=1.47, rw0=0.86, sail=0.16, cpillar=0.16,
    doors={"door_f": (2.08, 3.20), "door_r": (1.18, 2.02)}, bpillars=[(2.0, 2.10)],
    hood=(3.31, 4.36), boot=(-0.01, 0.84), bump_f=3.98, bump_r=0.36, bumper_top=(0.56, 0.56),
    bumper_z=0.42, hood_front_z=0.72, rake_f=0.12, rake_r=0.07, corner_f=0.34, corner_r=0.30,
    head=dict(x=(0.42, 0.76), z=(0.60, 0.70), shape="swept", drl=True),
    tail=dict(x=(0.42, 0.78), z=(0.70, 0.86), pattern="bars"),
    grille=dict(w=0.36, z=(0.44, 0.58), style="honeycomb"),
    plate_f=0.36, plate_r=0.70, exhaust=[(-0.45, 0.30)],
    interior=dict(seats="sport", dash="classic", trim="carbon", leather=(36, 34, 33), stitch=(200, 40, 30)),
    gauges=dict(max=220, red=6.5), mass=1150, handling="compact",
)

CLASSIC = dict(COMPACT)
CLASSIC.update(
    name="classic_sedan", title="Классика «Семёрка»",
    len=4.15, axle_r=0.80, axle_f=3.22, wheel_r=0.29, rim_r=0.175, tire_w=0.175, track=0.68, arch_r=0.335,
    spokes=0, rim_style="steel",
    z_top=[(0, 0.80), (0.08, 0.90), (0.6, 0.93), (0.92, 0.95), (1.42, 1.40), (2.0, 1.43), (2.48, 1.42), (3.10, 0.99), (3.5, 0.94), (4.05, 0.90), (4.15, 0.80)],
    z_belt=[(0, 0.80), (0.3, 0.90), (1.0, 0.92), (2.0, 0.92), (3.2, 0.905), (4.0, 0.88), (4.15, 0.80)],
    z_sill=[(0, 0.36), (0.2, 0.30), (0.8, 0.27), (3.4, 0.27), (4.0, 0.30), (4.15, 0.38)],
    w_sh=[(0, 0.77), (0.3, 0.80), (1.2, 0.81), (3.2, 0.81), (3.95, 0.80), (4.15, 0.77)],
    w_bot=[(0, 0.76), (0.3, 0.79), (1.2, 0.80), (3.2, 0.80), (3.95, 0.79), (4.15, 0.76)],
    w_roof=[(0.7, 0.58), (1.42, 0.65), (2.0, 0.66), (2.48, 0.65), (3.1, 0.58)],
    cabin_h=0.30, crown=0.02, tumble=0.08, bulge=0.004, flare=0.0,
    ws0=3.10, ws1=2.48, rw1=1.42, rw0=0.94, sail=0.12, cpillar=0.20,
    doors={"door_f": (2.04, 3.08), "door_r": (1.20, 1.98)}, bpillars=[(1.97, 2.06)],
    hood=(3.13, 4.16), boot=(-0.01, 0.93), bump_f=4.00, bump_r=0.17, bumper_top=(0.50, 0.50),
    bumper_z=0.42, hood_front_z=0.85, rake_f=0.03, rake_r=0.03, corner_f=0.12, corner_r=0.12,
    body_pillars=True,
    head=dict(x=(0.38, 0.74), z=(0.66, 0.80), shape="twin_round", drl=False),
    tail=dict(x=(0.30, 0.76), z=(0.62, 0.80), pattern="classic"),
    grille=dict(w=0.40, z=(0.64, 0.80), style="slats"),
    plate_f=0.43, plate_r=0.58, exhaust=[(-0.40, 0.30)],
    interior=dict(seats="classic", dash="classic", trim="wood", leather=(70, 52, 40), stitch=None),
    gauges=dict(max=180, red=6.0), mass=1060, handling="classic",
)

EXEC = dict(COMPACT)
EXEC.update(
    name="exec_sedan", title="Бизнес-седан «Сенатор 7»",
    len=5.10, axle_r=1.10, axle_f=4.12, wheel_r=0.345, rim_r=0.245, tire_w=0.245, track=0.80, arch_r=0.39,
    spokes=10, rim_style="multi",
    z_top=[(0, 0.76), (0.10, 0.98), (0.5, 1.03), (1.05, 1.06), (1.70, 1.45), (2.4, 1.48), (3.15, 1.45), (3.95, 1.05), (4.4, 0.99), (4.9, 0.88), (5.10, 0.76)],
    z_belt=[(0, 0.74), (0.45, 0.98), (1.2, 1.02), (2.5, 1.01), (3.9, 0.97), (4.6, 0.90), (5.10, 0.74)],
    z_sill=[(0, 0.36), (0.3, 0.26), (1.0, 0.24), (4.2, 0.23), (4.85, 0.26), (5.10, 0.36)],
    w_sh=[(0, 0.80), (0.5, 0.92), (1.3, 0.945), (3.9, 0.945), (4.7, 0.92), (5.10, 0.80)],
    w_bot=[(0, 0.77), (0.5, 0.88), (1.3, 0.905), (3.9, 0.905), (4.7, 0.88), (5.10, 0.77)],
    w_roof=[(0.9, 0.56), (1.7, 0.69), (2.4, 0.72), (3.15, 0.70), (4.0, 0.56)],
    cabin_h=0.34, crown=0.06, tumble=0.13, bulge=0.02, flare=0.012,
    ws0=3.92, ws1=3.12, rw1=1.75, rw0=1.04, sail=0.18, cpillar=0.20,
    doors={"door_f": (2.62, 3.86), "door_r": (1.52, 2.56)}, bpillars=[(2.54, 2.64)],
    hood=(3.95, 5.11), boot=(-0.01, 1.02), bump_f=4.70, bump_r=0.42, bumper_top=(0.60, 0.62),
    bumper_z=0.45, hood_front_z=0.80, rake_f=0.14, rake_r=0.08, corner_f=0.38, corner_r=0.36,
    head=dict(x=(0.50, 0.86), z=(0.66, 0.76), shape="swept", drl=True),
    tail=dict(x=(0.40, 0.90), z=(0.78, 0.92), pattern="bars"),
    grille=dict(w=0.48, z=(0.48, 0.70), style="slats"),
    plate_f=0.40, plate_r=0.78, exhaust=[(-0.52, 0.32), (0.52, 0.32)],
    interior=dict(seats="lux", dash="lux", trim="wood", leather=(120, 90, 62), stitch=(230, 220, 200)),
    gauges=dict(max=280, red=6.5), mass=1900, handling="exec",
)

SUV = dict(COMPACT)
SUV.update(
    name="suv", title="Внедорожник «Тайга 4х4»",
    len=4.85, axle_r=0.98, axle_f=3.88, wheel_r=0.39, rim_r=0.24, tire_w=0.26, track=0.83, arch_r=0.45,
    spokes=6, rim_style="offroad", arch_squash=0.95,
    z_top=[(0, 1.32), (0.05, 1.78), (0.3, 1.86), (1.0, 1.88), (2.2, 1.89), (3.05, 1.84), (3.62, 1.34), (4.0, 1.28), (4.6, 1.20), (4.85, 1.05)],
    z_belt=[(0, 1.25), (0.3, 1.30), (1.5, 1.30), (3.0, 1.28), (3.7, 1.24), (4.4, 1.17), (4.85, 1.02)],
    z_sill=[(0, 0.55), (0.2, 0.46), (0.8, 0.44), (4.0, 0.44), (4.6, 0.48), (4.85, 0.58)],
    w_sh=[(0, 0.88), (0.3, 0.95), (1.3, 0.97), (3.7, 0.97), (4.5, 0.95), (4.85, 0.88)],
    w_bot=[(0, 0.86), (0.3, 0.92), (1.3, 0.94), (3.7, 0.94), (4.5, 0.92), (4.85, 0.86)],
    w_roof=[(0.0, 0.70), (0.3, 0.76), (2.0, 0.78), (3.05, 0.77), (3.65, 0.70)],
    cabin_h=0.40, crown=0.04, tumble=0.12, bulge=0.012, flare=0.05,
    ws0=3.60, ws1=3.02, rw1=0.20, rw0=0.04, sail=0.16, cpillar=0.35,
    doors={"door_f": (2.40, 3.55), "door_r": (1.35, 2.34)}, bpillars=[(2.32, 2.42)],
    hood=(3.63, 4.86), boot=(-0.01, 0.0), bump_f=4.50, bump_r=0.20, bumper_top=(0.80, 0.80),
    bumper_z=0.70, hood_front_z=1.10, rake_f=0.10, rake_r=0.02, corner_f=0.32, corner_r=0.25,
    head=dict(x=(0.52, 0.88), z=(0.98, 1.10), shape="swept", drl=True),
    tail=dict(x=(0.66, 0.92), z=(1.05, 1.50), pattern="rings", vertical=True),
    grille=dict(w=0.56, z=(0.78, 1.06), style="slats"),
    plate_f=0.62, plate_r=0.95, exhaust=[(-0.55, 0.45)],
    interior=dict(seats="lux", dash="modern", trim="alu", leather=(30, 30, 32), stitch=(150, 150, 150)),
    gauges=dict(max=240, red=5.0), mass=2300, handling="suv",
    tailgate=True,
)

SUPER = dict(COMPACT)
SUPER.update(
    name="supercar", title="Суперкар «Торо V12»",
    len=4.70, axle_r=1.07, axle_f=3.75, wheel_r=0.345, rim_r=0.255, tire_w=0.30, track=0.86, arch_r=0.38,
    spokes=5, rim_style="forged",
    z_top=[(0, 0.86), (0.25, 0.98), (1.0, 1.04), (1.55, 1.12), (2.05, 1.16), (2.45, 1.13), (3.25, 0.82), (3.8, 0.72), (4.4, 0.60), (4.70, 0.42)],
    z_belt=[(0, 0.84), (0.6, 0.95), (1.4, 0.98), (2.2, 0.86), (3.3, 0.76), (4.0, 0.66), (4.7, 0.42)],
    z_sill=[(0, 0.30), (0.3, 0.20), (1.1, 0.15), (3.6, 0.14), (4.4, 0.16), (4.70, 0.20)],
    w_sh=[(0, 0.90), (0.6, 0.99), (1.2, 1.01), (2.2, 0.98), (3.6, 0.99), (4.3, 0.95), (4.70, 0.82)],
    w_bot=[(0, 0.88), (0.6, 0.96), (1.2, 0.97), (2.2, 0.92), (3.6, 0.95), (4.3, 0.92), (4.70, 0.80)],
    w_roof=[(1.3, 0.46), (1.6, 0.56), (2.1, 0.60), (2.45, 0.58), (3.3, 0.44)],
    cabin_h=0.22, crown=0.07, tumble=0.30, bulge=0.012, flare=0.04,
    ws0=3.24, ws1=2.42, rw1=1.58, rw0=1.20, sail=0.14, cpillar=0.30,
    doors={"door_f": (1.80, 3.12)}, bpillars=[],
    hood=(3.27, 4.71), boot=(-0.01, 1.18), bump_f=4.35, bump_r=0.30, bumper_top=(0.55, 0.42),
    bumper_z=0.30, hood_front_z=0.45, rake_f=0.18, rake_r=0.04, corner_f=0.40, corner_r=0.25,
    head=dict(x=(0.50, 0.92), z=(0.50, 0.58), shape="slit", drl=True),
    tail=dict(x=(0.30, 0.95), z=(0.76, 0.84), pattern="bars"),
    grille=dict(w=0.70, z=(0.20, 0.36), style="honeycomb"),
    plate_f=None, plate_r=0.48, exhaust=[(-0.12, 0.42), (0.12, 0.42)],
    interior=dict(seats="bucket", dash="sport", trim="carbon", leather=(20, 20, 22), stitch=(255, 190, 0)),
    gauges=dict(max=360, red=8.5), mass=1550, handling="super", engine_rear=True,
)

HYPER = dict(SUPER)
HYPER.update(
    name="hypercar", title="Гиперкар «Аврора W16»",
    len=4.55, axle_r=1.00, axle_f=3.71, wheel_r=0.355, rim_r=0.26, tire_w=0.32, track=0.88, arch_r=0.39,
    spokes=10, rim_style="turbine",
    z_top=[(0, 0.88), (0.3, 1.02), (1.0, 1.06), (1.55, 1.14), (2.05, 1.19), (2.5, 1.16), (3.25, 0.86), (3.7, 0.76), (4.25, 0.64), (4.55, 0.46)],
    z_belt=[(0, 0.86), (0.6, 0.98), (1.4, 1.00), (2.1, 0.90), (3.3, 0.80), (4.0, 0.70), (4.55, 0.46)],
    w_sh=[(0, 0.92), (0.6, 1.00), (1.2, 1.02), (2.1, 0.96), (3.5, 1.00), (4.2, 0.96), (4.55, 0.82)],
    w_bot=[(0, 0.90), (0.6, 0.97), (1.2, 0.98), (2.1, 0.90), (3.5, 0.96), (4.2, 0.93), (4.55, 0.80)],
    w_roof=[(1.3, 0.44), (1.6, 0.55), (2.1, 0.58), (2.5, 0.56), (3.3, 0.42)],
    ws0=3.26, ws1=2.48, rw1=1.58, rw0=1.20,
    doors={"door_f": (1.78, 3.10)},
    hood=(3.29, 4.56), bump_f=4.22, bump_r=0.30, bumper_top=(0.58, 0.46), hood_front_z=0.49,
    head=dict(x=(0.48, 0.90), z=(0.54, 0.62), shape="quad", drl=True),
    tail=dict(x=(0.10, 0.96), z=(0.80, 0.86), pattern="bar_full"),
    grille=dict(w=0.42, z=(0.22, 0.44), style="horseshoe"),
    interior=dict(seats="bucket", dash="sport", trim="carbon", leather=(90, 20, 24), stitch=(240, 240, 240)),
    gauges=dict(max=500, red=6.5), mass=1950, handling="hyper",
)

CARS = [COMPACT, CLASSIC, EXEC, SUV, SUPER, HYPER]
for _p in CARS:
    _p["cuts"] = cuts(_p)

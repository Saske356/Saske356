"""The full car lineup: homages to well-known cars under their own names.

Shapes follow the proportions and signature details of the originals
(grille type, lamp shapes, body style) but carry no real brand names or
logos.  Every car is built from a handful of numbers by `make()`.
"""
from presets import cuts


def make(name, title, cls, L, W, H, wb, oh_r, wheel=(0.31, 0.20, 0.20), body="sedan",
         hood=1.15, ws=0.78, rw=0.62, deck=0.55, belt=None, sill=0.24, nose=None, tail=None,
         box=0.3, doors=4, head=None, tail_l=None, grille=None, interior=None, gauges=(220, 6.5),
         paint=(180, 180, 185), rim="split", spokes=5, mass=1300, **over):
    wr, rr, tw = wheel
    belt = belt if belt is not None else sill + (H - sill) * 0.56
    nose = nose if nose is not None else belt - 0.18
    tail = tail if tail is not None else belt - 0.10
    axle_r, axle_f = oh_r, oh_r + wb
    ws0 = L - hood
    ws1 = ws0 - ws
    if body in ("hatch", "suv", "wagon", "van"):
        deck = 0.04 if body != "hatch" else 0.10
    rw0 = deck
    rw1 = rw0 + rw
    mid = (rw1 + ws1) / 2
    z_hood = belt + 0.05 + 0.03 * (1 - box)
    z_deck = belt + 0.06
    if body == "sedan":
        z_top = [(0, tail), (0.10, tail + 0.12), (rw0 * 0.6, z_deck - 0.01), (rw0, z_deck), (rw1, H - 0.02),
                 (mid, H), (ws1, H - 0.025), (ws0, z_hood), (ws0 + hood * 0.45, (z_hood + nose) / 2 + 0.04), (L - 0.12, nose + 0.03), (L, nose)]
    elif body == "coupe":
        z_top = [(0, tail), (0.12, tail + 0.12), (rw0, z_deck), (rw1, H - 0.03), (mid, H), (ws1, H - 0.03),
                 (ws0, z_hood), (ws0 + hood * 0.5, (z_hood + nose) / 2 + 0.03), (L - 0.12, nose + 0.03), (L, nose)]
    elif body == "super":
        z_top = [(0, tail), (0.25, tail + 0.10), (rw0, z_deck + 0.04), (rw1, H - 0.04), (mid, H), (ws1, H - 0.03),
                 (ws0, z_hood - 0.04), (ws0 + hood * 0.5, (z_hood + nose) / 2 - 0.03), (L - 0.25, nose + 0.08), (L, nose)]
    else:  # hatch / suv / wagon : near-vertical tailgate
        z_top = [(0, tail), (rw0 * 0.5, tail + (H - tail) * 0.6), (rw0, H - 0.08), (rw1, H - 0.02), (mid, H),
                 (ws1, H - 0.03), (ws0, z_hood), (ws0 + hood * 0.5, (z_hood + nose) / 2 + 0.04), (L - 0.12, nose + 0.03), (L, nose)]
    z_belt = [(0, tail - 0.02), (0.4, belt + 0.01), (L * 0.5, belt), (ws0, belt - 0.015), (L - 0.4, max(nose + 0.06, belt - 0.07)), (L, nose - 0.02)]
    z_sill = [(0, sill + 0.12), (0.3, sill + 0.04), (oh_r, sill), (L - 0.75, sill), (L - 0.3, sill + 0.03), (L, sill + 0.11)]
    r_end = 0.08 * (1 - box) + 0.012
    w_sh = [(0, W - r_end * 1.2), (0.4, W - 0.012), (L * 0.5, W), (L - 0.5, W - 0.02), (L, W - r_end * 1.3)]
    w_bot = [(t, w - 0.035) for t, w in w_sh]
    w_roof = [(rw0, W * 0.60), (rw1, W * 0.74), (mid, W * 0.77), (ws1, W * 0.74), (ws0, W * 0.58)]
    if body in ("suv", "hatch", "wagon", "van"):
        w_roof = [(0.0, W * 0.74), (rw1, W * 0.78), (mid, W * 0.79), (ws1, W * 0.76), (ws0, W * 0.60)]
    bp = ws1 - 0.45 * (ws1 - rw1) if body not in ("suv", "hatch", "wagon", "van") else ws1 - 0.42 * (ws1 - rw1 - 0.25)
    arch = wr + 0.05
    if doors == 4:
        dmap = {"door_f": (bp + 0.05, ws0 - 0.08), "door_r": (max(axle_r + arch, rw0 + 0.25), bp - 0.05)}
        bps = [(bp - 0.05, bp + 0.05)]
    else:
        dmap = {"door_f": (max(axle_r + arch + 0.05, ws1 - 1.15), ws0 - 0.08)}
        bps = []
    boot = (-0.01, rw0 - 0.02) if body in ("sedan", "coupe", "super") else (-0.01, rw1 - 0.03)
    tailgate = body not in ("sedan", "coupe", "super")
    head = head or {}
    hd = dict(x=(W * 0.50, W * 0.90), z=(nose - 0.11, nose - 0.025), shape="swept", drl=True)
    hd.update(head)
    tl = dict(x=(W * 0.52, W * 0.93), z=(tail - 0.17, tail - 0.04), pattern="bars")
    if tailgate:
        tl = dict(x=(W * 0.70, W * 0.94), z=(tail - 0.30, tail + 0.12), pattern="rings")
    tl.update(tail_l or {})
    gr = dict(w=W * 0.50, z=(sill + 0.22, nose - 0.10), style="slats")
    gr.update(grille or {})
    it = dict(seats="sport", dash="classic", trim="carbon", leather=(32, 31, 30), stitch=(200, 200, 200))
    it.update(interior or {})
    p = dict(
        name=name, title=title, cls=cls, kind="car", len=L, axle_r=axle_r, axle_f=axle_f, wheel_r=wr, rim_r=rr, tire_w=tw,
        track=W - tw / 2 - 0.035, arch_r=arch, spokes=spokes, rim_style=rim,
        z_top=z_top, z_belt=z_belt, z_sill=z_sill, w_sh=w_sh, w_bot=w_bot, w_roof=w_roof,
        cabin_h=max(0.18, H - belt - 0.10), crown=0.02 + 0.05 * (1 - box), tumble=0.06 + 0.10 * (1 - box) + (0.12 if body == "super" else 0),
        bulge=0.004 + 0.016 * (1 - box), flare=0.0,
        ws0=ws0, ws1=ws1, rw1=rw1, rw0=rw0, sail=0.14, cpillar=0.14 if body == "sedan" else 0.10,
        doors=dmap, bpillars=bps, hood=(ws0 + 0.03, L + 0.01), boot=boot,
        bump_f=L - 0.36, bump_r=0.34 if body != "super" else 0.30,
        bumper_top=(sill + (tail - sill) * 0.42, sill + (nose - sill) * 0.50),
        bumper_z=sill + 0.18, hood_front_z=nose, rake_f=0.03 + 0.14 * (1 - box), rake_r=0.02 + 0.06 * (1 - box),
        corner_f=0.10 + 0.28 * (1 - box), corner_r=0.10 + 0.22 * (1 - box), body_pillars=box > 0.7,
        head=hd, tail=tl, grille=gr, plate_f=sill + 0.16 if body != "super" else None,
        plate_r=(tail - 0.24) if not tailgate else (sill + 0.30), exhaust=[(-W * 0.55, sill + 0.07)],
        interior=it, gauges=dict(max=gauges[0], red=gauges[1]), mass=mass, handling=cls,
        tailgate=tailgate, paint=paint, engine_rear=(body == "super"),
    )
    if body == "super":
        p["exhaust"] = [(-0.10, sill + 0.20), (0.10, sill + 0.20)]
    p.update(over)
    p["cuts"] = cuts(p)
    return p


CARS = [
    # ---------------------------------------------------------- отечественные
    make("kopeyka", "«Копейка»", "классика", 4.07, 0.80, 1.44, 2.42, 0.78, (0.29, 0.17, 0.165), "sedan",
         hood=1.02, ws=0.55, rw=0.48, deck=0.88, sill=0.27, box=0.9, rim="steel", spokes=0,
         head=dict(x=(0.36, 0.70), z=(0.62, 0.76), shape="twin_round", drl=False),
         tail_l=dict(x=(0.50, 0.76), z=(0.60, 0.74), pattern="classic"),
         grille=dict(w=0.38, z=(0.62, 0.76), style="slats", badge=True), gauges=(180, 6.0), paint=(150, 20, 24),
         interior=dict(seats="classic", trim="plastic", leather=(70, 44, 36), stitch=None), nose=0.80, tail=0.78),
    make("semerka", "«Семёрка»", "классика", 4.15, 0.81, 1.44, 2.42, 0.80, (0.29, 0.175, 0.175), "sedan",
         hood=1.06, ws=0.62, rw=0.48, deck=0.94, sill=0.27, box=0.95, rim="steel", spokes=0,
         head=dict(x=(0.38, 0.74), z=(0.66, 0.80), shape="rect", drl=False),
         tail_l=dict(x=(0.30, 0.76), z=(0.60, 0.78), pattern="classic"),
         grille=dict(w=0.40, z=(0.64, 0.80), style="slats"), gauges=(180, 6.0), paint=(230, 228, 220), nose=0.84, tail=0.80,
         interior=dict(seats="classic", trim="wood", leather=(70, 52, 40), stitch=None)),
    make("devyatka", "«Девятка»", "хэтчбек", 4.00, 0.825, 1.40, 2.46, 0.76, (0.29, 0.18, 0.175), "hatch",
         hood=1.10, ws=0.72, rw=0.95, sill=0.25, box=0.55, rim="split", spokes=4, doors=2, nose=0.70, tail=0.82,
         head=dict(x=(0.40, 0.76), z=(0.60, 0.70), shape="rect", drl=False),
         grille=dict(w=0.30, z=(0.60, 0.68), style="slats"), gauges=(200, 6.0), paint=(20, 20, 22)),
    make("chetyrka", "«Четырнадцатая»", "хэтчбек", 4.12, 0.825, 1.42, 2.46, 0.78, (0.29, 0.18, 0.175), "hatch",
         hood=1.12, ws=0.74, rw=0.95, sill=0.25, box=0.5, rim="split", spokes=5, nose=0.72, tail=0.84,
         head=dict(x=(0.38, 0.78), z=(0.60, 0.72), shape="swept", drl=False),
         grille=dict(w=0.44, z=(0.48, 0.60), style="slats"), gauges=(200, 6.0), paint=(190, 192, 196)),
    make("priorik", "«Приорик»", "седан", 4.35, 0.84, 1.42, 2.49, 0.84, (0.295, 0.19, 0.19), "sedan",
         hood=1.07, ws=0.72, rw=0.61, deck=0.86, sill=0.23, box=0.4, rim="split", spokes=5, nose=0.70, tail=0.76,
         head=dict(x=(0.42, 0.78), z=(0.60, 0.70)), grille=dict(w=0.36, z=(0.44, 0.58), style="honeycomb"), paint=(10, 10, 12)),
    make("niva", "«Нива 4×4»", "внедорожник", 3.74, 0.84, 1.64, 2.20, 0.66, (0.36, 0.20, 0.19), "suv",
         hood=1.02, ws=0.58, rw=0.96, sill=0.42, box=0.85, doors=2, rim="steel", spokes=0, nose=1.00, tail=1.06,
         head=dict(x=(0.42, 0.72), z=(0.86, 1.00), shape="twin_round", drl=False),
         grille=dict(w=0.40, z=(0.86, 1.00), style="slats"), gauges=(150, 5.0), paint=(60, 90, 50)),
    make("volga", "«Волга 31»", "седан", 4.92, 0.90, 1.46, 2.80, 1.12, (0.31, 0.19, 0.195), "sedan",
         hood=1.30, ws=0.66, rw=0.56, deck=1.05, sill=0.27, box=0.85, rim="steel", spokes=0, nose=0.86, tail=0.86,
         head=dict(x=(0.42, 0.82), z=(0.70, 0.82), shape="rect", drl=False),
         grille=dict(w=0.70, z=(0.62, 0.82), style="slats"), gauges=(160, 5.5), paint=(25, 25, 30)),
    # ---------------------------------------------------------- немцы
    make("bumer34", "«Бумер 34»", "бизнес-седан", 4.72, 0.875, 1.41, 2.76, 1.02, (0.315, 0.205, 0.225), "sedan",
         hood=1.30, ws=0.66, rw=0.56, deck=1.00, sill=0.25, box=0.75, rim="multi", spokes=12, nose=0.76, tail=0.80,
         head=dict(x=(0.38, 0.80), z=(0.62, 0.74), shape="twin_round", drl=False),
         grille=dict(w=0.30, z=(0.60, 0.76), style="kidney", gap=0.03), gauges=(260, 6.5), paint=(20, 30, 70)),
    make("bumer39", "«Бумер 39»", "бизнес-седан", 4.78, 0.90, 1.43, 2.83, 1.03, (0.32, 0.215, 0.235), "sedan",
         hood=1.25, ws=0.75, rw=0.62, deck=0.98, sill=0.24, box=0.45, rim="multi", spokes=10, nose=0.74, tail=0.80,
         head=dict(x=(0.40, 0.82), z=(0.62, 0.74), shape="twin_round", drl=True),
         grille=dict(w=0.30, z=(0.58, 0.74), style="kidney", gap=0.03), gauges=(280, 6.5), paint=(10, 10, 12),
         interior=dict(seats="lux", trim="wood", leather=(120, 90, 62), stitch=(230, 220, 200))),
    make("bumer_m5", "«Бумер М5»", "спорт-седан", 4.98, 0.95, 1.47, 2.98, 1.05, (0.345, 0.25, 0.275), "sedan",
         hood=1.30, ws=0.82, rw=0.70, deck=0.95, sill=0.22, box=0.25, rim="forged", spokes=5, nose=0.74, tail=0.82,
         head=dict(x=(0.44, 0.88), z=(0.66, 0.74), shape="swept", drl=True),
         grille=dict(w=0.42, z=(0.54, 0.74), style="kidney", gap=0.035, chrome=False), gauges=(330, 7.2), paint=(110, 112, 116),
         interior=dict(seats="bucket", trim="carbon", leather=(150, 40, 30), stitch=(255, 255, 255))),
    make("bumer_m4", "«Бумер М4»", "купе", 4.80, 0.94, 1.39, 2.86, 1.02, (0.345, 0.25, 0.275), "coupe",
         hood=1.35, ws=0.82, rw=0.75, deck=0.82, sill=0.21, box=0.2, doors=2, rim="forged", spokes=10, nose=0.68, tail=0.84,
         head=dict(x=(0.46, 0.88), z=(0.64, 0.72), shape="slit", drl=True),
         grille=dict(w=0.62, z=(0.30, 0.66), style="kidney", gap=0.03, chrome=False), gauges=(330, 7.2), paint=(15, 120, 90),
         interior=dict(seats="bucket", trim="carbon", leather=(200, 100, 40), stitch=(30, 30, 30))),
    make("merin140", "«Мерин 140 Кабан»", "представительский", 5.11, 0.95, 1.49, 3.04, 1.12, (0.33, 0.21, 0.235), "sedan",
         hood=1.30, ws=0.72, rw=0.62, deck=1.08, sill=0.25, box=0.8, rim="multi", spokes=8, nose=0.82, tail=0.86,
         head=dict(x=(0.44, 0.88), z=(0.66, 0.80), shape="rect", drl=False),
         grille=dict(w=0.48, z=(0.62, 0.86), style="slats"), gauges=(260, 6.0), paint=(12, 12, 14),
         interior=dict(seats="lux", trim="wood", leather=(140, 120, 90), stitch=None)),
    make("merin_e63", "«Мерин Е63»", "бизнес-седан", 4.99, 0.93, 1.46, 2.94, 1.06, (0.335, 0.24, 0.255), "sedan",
         hood=1.25, ws=0.84, rw=0.70, deck=0.92, sill=0.23, box=0.25, rim="forged", spokes=5, nose=0.74, tail=0.82,
         head=dict(x=(0.46, 0.88), z=(0.64, 0.73), shape="swept", drl=True),
         grille=dict(w=0.72, z=(0.42, 0.70), style="slats"), gauges=(330, 7.0), paint=(235, 235, 235),
         interior=dict(seats="lux", trim="alu", leather=(20, 20, 22), stitch=(200, 30, 30))),
    make("kubik", "«Кубик G63»", "внедорожник", 4.87, 0.98, 1.97, 2.89, 0.95, (0.40, 0.25, 0.275), "suv",
         hood=1.25, ws=0.42, rw=0.92, sill=0.48, box=1.0, rim="offroad", spokes=6, nose=1.22, tail=1.30,
         head=dict(x=(0.62, 0.90), z=(1.04, 1.17), shape="twin_round", drl=True),
         grille=dict(w=0.72, z=(0.84, 1.18), style="slats"), gauges=(240, 6.0), paint=(20, 20, 22),
         interior=dict(seats="lux", trim="carbon", leather=(150, 40, 30), stitch=(255, 255, 255))),
    make("koltsa_rs6", "«Кольца RS6»", "универсал", 5.00, 0.975, 1.46, 2.93, 1.05, (0.35, 0.255, 0.285), "wagon",
         hood=1.25, ws=0.82, rw=1.85, sill=0.22, box=0.3, rim="turbine", spokes=10, nose=0.76, tail=0.96,
         head=dict(x=(0.44, 0.90), z=(0.66, 0.74), shape="slit", drl=True),
         grille=dict(w=0.80, z=(0.30, 0.72), style="honeycomb"), gauges=(310, 7.0), paint=(100, 104, 108)),
    # ---------------------------------------------------------- японцы
    make("kamryukha", "«Камрюха 70»", "седан", 4.89, 0.92, 1.45, 2.83, 1.04, (0.33, 0.22, 0.235), "sedan",
         hood=1.22, ws=0.80, rw=0.70, deck=0.95, sill=0.24, box=0.3, rim="split", spokes=5, nose=0.74, tail=0.82,
         head=dict(x=(0.44, 0.88), z=(0.64, 0.74), shape="swept", drl=True),
         grille=dict(w=0.86, z=(0.32, 0.60), style="wide_mesh"), gauges=(240, 6.5), paint=(10, 10, 12),
         interior=dict(seats="lux", trim="wood", leather=(190, 170, 140), stitch=None)),
    make("markovnik", "«Марковник»", "седан", 4.76, 0.88, 1.40, 2.78, 1.02, (0.32, 0.21, 0.225), "sedan",
         hood=1.25, ws=0.72, rw=0.60, deck=0.98, sill=0.21, box=0.6, rim="multi", spokes=6, nose=0.72, tail=0.80,
         head=dict(x=(0.40, 0.82), z=(0.62, 0.72), shape="rect", drl=False),
         grille=dict(w=0.56, z=(0.58, 0.70), style="slats"), gauges=(240, 7.0), paint=(235, 235, 235)),
    make("rafik", "«Рафик 4»", "кроссовер", 4.60, 0.93, 1.69, 2.69, 0.98, (0.36, 0.23, 0.235), "suv",
         hood=1.10, ws=0.70, rw=0.40, sill=0.40, box=0.45, rim="split", spokes=5, nose=1.00, tail=1.08,
         head=dict(x=(0.48, 0.88), z=(0.92, 1.02), shape="swept", drl=True),
         grille=dict(w=0.70, z=(0.56, 0.92), style="honeycomb"), gauges=(200, 6.0), paint=(240, 240, 238)),
    make("spindl_lx", "«Спиндл LX»", "внедорожник", 5.08, 0.99, 1.89, 2.85, 1.10, (0.39, 0.26, 0.265), "suv",
         hood=1.30, ws=0.70, rw=0.40, sill=0.44, box=0.6, rim="multi", spokes=10, nose=1.14, tail=1.20,
         head=dict(x=(0.52, 0.92), z=(1.02, 1.12), shape="slit", drl=True),
         grille=dict(w=1.02, z=(0.56, 1.10), style="spindle"), gauges=(220, 6.0), paint=(40, 42, 46),
         interior=dict(seats="lux", trim="wood", leather=(120, 70, 40), stitch=(230, 220, 200))),
    make("godzilla", "«Годзилла R35»", "спорткар", 4.71, 0.945, 1.37, 2.78, 1.02, (0.35, 0.255, 0.285), "coupe",
         hood=1.40, ws=0.82, rw=0.62, deck=0.76, sill=0.20, box=0.35, doors=2, rim="multi", spokes=6, nose=0.66, tail=0.88,
         head=dict(x=(0.48, 0.90), z=(0.60, 0.70), shape="swept", drl=True),
         tail_l=dict(x=(0.50, 0.85), z=(0.72, 0.86), pattern="rings"),
         grille=dict(w=0.80, z=(0.24, 0.56), style="honeycomb"), gauges=(320, 7.0), paint=(30, 32, 36)),
    make("suprim", "«Суприм А90»", "спорткар", 4.38, 0.93, 1.29, 2.47, 0.98, (0.34, 0.245, 0.27), "coupe",
         hood=1.45, ws=0.82, rw=0.52, deck=0.40, sill=0.19, box=0.1, doors=2, rim="forged", spokes=10, nose=0.56, tail=0.86,
         head=dict(x=(0.46, 0.88), z=(0.56, 0.64), shape="slit", drl=True),
         grille=dict(w=0.70, z=(0.20, 0.44), style="honeycomb"), gauges=(300, 7.0), paint=(230, 70, 10)),
    # ---------------------------------------------------------- суперкары
    make("tsuffen911", "«Цуффен 911»", "спорткар", 4.52, 0.925, 1.30, 2.45, 1.10, (0.345, 0.255, 0.295), "hatch",
         hood=1.25, ws=0.85, rw=1.25, sill=0.20, box=0.05, doors=2, rim="turbine", spokes=10, nose=0.60, tail=0.80,
         head=dict(x=(0.52, 0.80), z=(0.56, 0.70), shape="twin_round", drl=True),
         tail_l=dict(x=(0.10, 0.92), z=(0.78, 0.84), pattern="bar_full"),
         grille=dict(w=0.70, z=(0.20, 0.36), style="honeycomb", badge=False), gauges=(330, 7.5), paint=(20, 70, 150),
         tailgate=False),
    make("skakun", "«Скакун F8»", "суперкар", 4.61, 0.98, 1.21, 2.65, 1.06, (0.345, 0.255, 0.30), "super",
         hood=1.30, ws=0.75, rw=0.40, deck=1.15, sill=0.15, box=0.05, doors=2, rim="forged", spokes=5, nose=0.48, tail=0.86,
         head=dict(x=(0.50, 0.90), z=(0.52, 0.60), shape="slit", drl=True),
         tail_l=dict(x=(0.40, 0.80), z=(0.74, 0.84), pattern="rings"),
         grille=dict(w=0.80, z=(0.18, 0.36), style="honeycomb", badge=False), gauges=(340, 8.0), paint=(190, 10, 16),
         interior=dict(seats="bucket", trim="carbon", leather=(20, 20, 22), stitch=(255, 200, 0))),
    make("toro_revuelto", "«Торо Ревуэльто»", "суперкар", 4.95, 1.03, 1.16, 2.78, 1.10, (0.355, 0.265, 0.33), "super",
         hood=1.45, ws=0.82, rw=0.42, deck=1.30, sill=0.13, box=0.0, doors=2, rim="forged", spokes=5, nose=0.42, tail=0.88,
         head=dict(x=(0.50, 0.94), z=(0.46, 0.53), shape="slit", drl=True),
         tail_l=dict(x=(0.30, 0.98), z=(0.76, 0.83), pattern="bars"),
         grille=dict(w=0.90, z=(0.16, 0.34), style="honeycomb", badge=False), gauges=(350, 9.5), paint=(245, 190, 0),
         interior=dict(seats="bucket", trim="carbon", leather=(20, 20, 22), stitch=(255, 190, 0)), scissor=True),
    make("bugai", "«Бугай Широн»", "гиперкар", 4.54, 1.01, 1.21, 2.71, 1.00, (0.36, 0.265, 0.32), "super",
         hood=1.30, ws=0.82, rw=0.45, deck=1.18, sill=0.14, box=0.1, doors=2, rim="turbine", spokes=10, nose=0.48, tail=0.88,
         head=dict(x=(0.50, 0.90), z=(0.52, 0.62), shape="quad", drl=True),
         tail_l=dict(x=(0.10, 0.96), z=(0.80, 0.86), pattern="bar_full"),
         grille=dict(w=0.40, z=(0.20, 0.46), style="horseshoe"), gauges=(500, 6.8), paint=(20, 40, 110),
         interior=dict(seats="bucket", trim="carbon", leather=(90, 20, 24), stitch=(240, 240, 240)), scissor=False),
]

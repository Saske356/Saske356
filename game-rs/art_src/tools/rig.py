"""Риггинг существ нейросетью Segment Anything (Meta, vit_b, на процессоре).

Для каждого спрайта: «отростки» (плавники, щупальца, ноги, усы) находятся по форме силуэта (всё, что торчит из толстого
ядра тела), затем Segment Anything уточняет их край по самому рисунку. Для каждой части находится
шарнир (середина места крепления). Пишутся:
  spr/NAME__pK.png — часть (тот же холст, что у спрайта),
  тело (NAME.png или NAME_body.png у боссов с пастью) — без дальнего конца части (ближний остаётся, чтобы не было дыры),
  manifest: meta[NAME]["parts"] = [{"k": key, "h": [u, v], "a": амплитуда, "w": частота, "p": фаза, "z": 1/-1}].
Маски кэшируются в art_src/rig_cache. Ярусы _t1/_t2 используют маски основы.

Запуск из game-rs:  python3 art_src/tools/rig.py [ИМЕНА…]      (нужны torch, torchvision, segment-anything, opencv, scipy)
Предпросмотр: rig_cache/preview_*.png
"""
import os, sys, json, numpy as np
from PIL import Image, ImageDraw
from scipy import ndimage as nd

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, '..', '..'))
SPR = os.path.join(ROOT, 'assets', 'spr'); MAN = os.path.join(ROOT, 'assets', 'manifest.json')
CACHE = os.path.join(ROOT, 'art_src', 'rig_cache'); os.makedirs(CACHE, exist_ok=True)
CKPT = os.environ.get('SAM_CKPT', '/tmp/sam/vit_b.pth')
N = 512

DEFAULT = [f'pl_{s}' for s in ['azure', 'amber', 'amethyst', 'emerald', 'coral', 'ghost', 'ember', 'frost', 'dawn', 'void', 'aurora', 'solar', 'venom',
                               'royal', 'nebula', 'cyber', 'lunar', 'inferno', 'abyss', 'jade', 'prism']] + \
          ['dart', 'squid', 'lantern', 'ray', 'bomber', 'mender', 'crab', 'crab_bare', 'kingcrab', 'kingcrab_bare', 'boss1', 'boss2']  # boss4 не режем: нарезка рвала голову и хвост (4.4)

_pred = None
def predictor():
    global _pred
    if _pred is None:
        import torch
        from segment_anything import sam_model_registry, SamPredictor
        torch.set_num_threads(4)
        _pred = SamPredictor(sam_model_registry['vit_b'](checkpoint=CKPT))
    return _pred


def disk(r):
    y, x = np.ogrid[-r:r + 1, -r:r + 1]; return x * x + y * y <= r * r


def find_parts(name, im, maxn=None):
    if maxn is None: maxn = {'drifter': 2, 'fry': 2, 'spikelet': 0}.get(name, 7)
    """1) отростки по форме: силуэт минус «толстое ядро» (открытие кругом 0.55 от толщины тела);
       2) Segment Anything уточняет край каждой части по рисунку (подсказка — рамка и точка части, минус-точка в ядре).
       Возвращает (ядро, [(маска, (hx, hy), длина)]) в сетке N×N."""
    cf = os.path.join(CACHE, name + '.npz')
    big = im.resize((N, N), Image.LANCZOS)
    alpha = np.asarray(big)[..., 3] > 40; alpha = nd.binary_fill_holes(nd.binary_closing(alpha, iterations=3)); A = alpha.sum()
    r = max(4, int(nd.distance_transform_edt(alpha).max() * 0.55))
    core = nd.binary_opening(alpha, structure=disk(r)); lab, n = nd.label(core)
    if n > 1: core = lab == (1 + int(np.argmax(nd.sum(core, lab, range(1, n + 1)))))
    app = alpha & ~nd.binary_dilation(core, iterations=2); lab, n = nd.label(app)
    comps = []
    for i in range(1, n + 1):
        m = lab == i
        if m.sum() < A * 0.012: continue
        if (m & nd.binary_dilation(core, iterations=5)).sum() < 4: continue
        comps.append(m)
    # SAM-уточнение (кэшируется)
    if os.path.exists(cf):
        z = np.load(cf); refined = [z[k] for k in sorted(z.files, key=lambda s: int(s[1:]))]
    else:
        refined = []
        if comps:
            pr = predictor(); bg = Image.new('RGB', (N, N), (24, 26, 34)); bg.paste(big, (0, 0), big); pr.set_image(np.asarray(bg))
            cy, cx = [float(v.mean()) for v in np.where(core)]
            for m in comps:
                ys, xs = np.where(m); py, px = ys[len(ys) // 2], xs[len(xs) // 2]
                box = np.array([xs.min() - 8, ys.min() - 8, xs.max() + 8, ys.max() + 8])
                ms, sc, _ = pr.predict(point_coords=np.array([[px, py], [cx, cy]]), point_labels=np.array([1, 0]), box=box, multimask_output=True)
                best = None; bs = -1
                for mm, s in zip(ms, sc):
                    mm = mm & alpha; inter = (mm & m).sum() / max(1, m.sum()); spill = (mm & core).sum() / max(1, mm.sum())
                    q = s * inter * (1 - spill)
                    if q > bs: bs, best = q, mm
                # итог: исходный отросток + то, что SAM добавил рядом с ним (корень плавника), но не глубоко в ядро
                near = nd.binary_dilation(m, iterations=14)
                refined.append(m | (best & near & ~nd.binary_erosion(core, iterations=10)) if best is not None and bs > 0.2 else m)
        np.savez_compressed(cf, **{f'm{i}': m for i, m in enumerate(refined)})
    parts = []
    for m in refined:
        rest = alpha & ~nd.binary_dilation(m, iterations=2)
        contact = m & nd.binary_dilation(core & rest, iterations=6)
        if contact.sum() < 4: continue
        hy, hx = [float(v.mean()) for v in np.where(contact)]; ys, xs = np.where(m)
        L = float(np.percentile(np.hypot(xs - hx, ys - hy), 95))
        if L < N * 0.05: continue
        parts.append((m, (hx, hy), L))
    parts.sort(key=lambda p: -p[0].sum())
    return core, parts[:maxn]


ORIG = os.path.join(CACHE, 'orig'); os.makedirs(ORIG, exist_ok=True)
def orig(key):
    """Исходная картинка (до нарезки) — чтобы повторный запуск не резал уже порезанное"""
    o = os.path.join(ORIG, key + '.png')
    if not os.path.exists(o): Image.open(os.path.join(SPR, key + '.png')).save(o)
    return Image.open(o).convert('RGBA')


def rig(name, man):
    base = os.path.join(SPR, name + '.png')
    if not os.path.exists(base): print('нет', name); return
    im = orig(name); S = im.size[0]
    core, parts = find_parts(name, im)
    # 4.5: что не должно качаться (раковина рака, дуло конька) — по положению шарнира (u, v в долях холста)
    EXCLUDE = {'hermit': lambda u, v: u < 0.5 or v < 0.38, 'seahorse': lambda u, v: u > 0.6}
    if name.startswith('pl_'): EXCLUDE[name] = lambda u, v: u > 0.78   # 4.7: нос облика не качается
    if name in EXCLUDE: parts = [p for p in parts if not EXCLUDE[name](p[1][0] / N, p[1][1] / N)]
    crab = name.startswith('crab') or name.startswith('kingcrab')
    body_key = name + '_body' if os.path.exists(os.path.join(SPR, name + '_body.png')) else name
    jaw = None
    if body_key != name:
        jaw = np.asarray(orig(name + '_jaw').resize((N, N)))[..., 3] > 30
    meta = man['meta'][name]; plist = []; bodies = {}
    for kk in [k for k in man['meta'] if k.startswith(name + '__p') or any(k.startswith(v + '__p') for v in (name + '_t1', name + '_t2'))]: man['meta'].pop(kk)

    variants = [v for v in (name, name + '_t1', name + '_t2') if os.path.exists(os.path.join(SPR, v + '.png'))]
    for k, (m, (hx, hy), L) in enumerate(parts):
        if jaw is not None: m = m & ~nd.binary_dilation(jaw, iterations=6)
        if m.sum() < 50: continue
        yy, xx = np.mgrid[0:N, 0:N]; d = np.hypot(xx - hx, yy - hy)
        far = np.clip((d - 0.22 * L) / (0.25 * L), 0, 1)                       # 0 у шарнира → 1 дальше
        pm = nd.gaussian_filter(nd.binary_dilation(m, iterations=2).astype(np.float32), 1.2)
        cut = (pm * far)                                                          # что убрать из тела
        u, v = hx / N, hy / N
        # фаза волны: части ближе к хвосту (слева) запаздывают; верх/низ — в противофазе
        ph = -u * 3.2 + (0.0 if v < 0.5 else 1.4)
        amp = 0.2 + 0.18 * min(1., L / (N * 0.3))
        w = 1.0
        if crab: ph = k * 2.1; amp = 0.24; w = 1.6                                # ноги краба — шаг вразнобой
        z = 1 if v > 0.55 else -1                                                 # нижние плавники — поверх тела
        for vn in variants:
            src = np.asarray(orig(vn)).astype(np.float32)
            pmS = np.asarray(Image.fromarray((pm * 255).astype(np.uint8)).resize((S, S), Image.BILINEAR)).astype(np.float32) / 255
            part = src.copy(); part[..., 3] *= pmS
            pk = f'{vn}__p{k}'; Image.fromarray(part.astype(np.uint8)).save(os.path.join(SPR, pk + '.png'))
            bk = body_key.replace(name, vn) if body_key != name else vn
            bpath = os.path.join(SPR, bk + '.png'); b = np.asarray(bodies.setdefault(bk, orig(bk))).astype(np.float32)
            cutS = np.asarray(Image.fromarray((cut * 255).astype(np.uint8)).resize((b.shape[1], b.shape[0]), Image.BILINEAR)).astype(np.float32) / 255
            b[..., 3] *= 1 - cutS; bodies[bk] = Image.fromarray(b.astype(np.uint8)); bodies[bk].save(bpath)
            pm_meta = dict(man['meta'][vn]); pm_meta.pop('parts', None); pm_meta.pop('hinge', None); man['meta'][pk] = pm_meta
        plist.append({'k': f'__p{k}', 'h': [round(u, 4), round(v, 4)], 'l': round(L / N, 4), 'a': round(amp, 3), 'w': w, 'p': round(ph, 3), 'z': z})
    for vn in variants:
        bk = body_key.replace(name, vn) if body_key != name else vn
        man['meta'][bk]['parts'] = [dict(p, k=vn + p['k']) for p in plist]
    # предпросмотр
    pv = Image.new('RGB', (N, N), (24, 26, 34)); big = im.resize((N, N)); pv.paste(big, (0, 0), big)
    a = np.asarray(pv).astype(np.float32); rng = np.random.default_rng(3)
    for m, h, L in parts:
        c = rng.integers(80, 255, 3); a[m] = a[m] * 0.45 + c * 0.55
    pv = Image.fromarray(a.astype(np.uint8)); dr = ImageDraw.Draw(pv)
    for m, (hx, hy), L in parts: dr.ellipse((hx - 6, hy - 6, hx + 6, hy + 6), fill=(255, 255, 255), outline=(0, 0, 0))
    pv.save(os.path.join(CACHE, f'preview_{name}.png'))
    print(name, 'частей:', len(plist), flush=True)


if __name__ == '__main__':
    names = sys.argv[1:] or DEFAULT
    man = json.load(open(MAN))
    for n in names:
        rig(n, man)
        json.dump(man, open(MAN, 'w'), ensure_ascii=False)
    os.system(f'python3 "{os.path.join(ROOT, "tools", "shrink.py")}"')  # убрать цвет под прозрачностью — иначе APK раздувается

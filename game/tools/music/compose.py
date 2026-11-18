#!/usr/bin/env python3
"""«Свет Бездны» — оффлайн-генератор саундтрека.

Синтезирует все треки игры из чистой математики (numpy, без сэмплов) и кодирует
их в OGG Vorbis через ffmpeg в game/audio/<имя>.ogg.

Как устроены бесшовные петли: каждый трек рендерится в кольцевой буфер длиной
ровно N тактов. Хвосты нот, вылезающие за конец, «заворачиваются» в начало;
реверберация, задержки, хорус и фильтры — циклические (свёртка через БПФ по длине
петли, LFO с целым числом периодов на петлю). Поэтому последний сэмпл гладко
переходит в первый — щелчка нет по построению.

Запуск:  python3 game/tools/music/compose.py [имя ...]   (без аргументов — все треки)
"""
import os
import subprocess
import sys

import numpy as np

SR = 44100
HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.normpath(os.path.join(HERE, '..', '..', 'audio'))
FFMPEG = '/usr/bin/ffmpeg' if os.path.exists('/usr/bin/ffmpeg') else 'ffmpeg'
TAU = 2 * np.pi


def mtof(m):
    return 440.0 * 2 ** ((np.asarray(m, float) - 69) / 12)


# ---------------------------------------------------------------- DSP-примитивы
def cyc_filter(x, lo=None, hi=None, order=2):
    """Нуль-фазовый фильтр в частотной области (циклический — для петель).
    lo — срез ФВЧ, hi — срез ФНЧ (Гц), спад как у баттерворта порядка order."""
    n = x.shape[-1]
    X = np.fft.rfft(x, axis=-1)
    f = np.fft.rfftfreq(n, 1 / SR)
    H = np.ones_like(f)
    if hi:
        H *= 1 / np.sqrt(1 + (f / hi) ** (2 * order))
    if lo:
        fs = np.maximum(f, 1e-3)
        H *= 1 / np.sqrt(1 + (lo / fs) ** (2 * order))
    return np.fft.irfft(X * H, n=n, axis=-1)


def cyc_conv(x, ir):
    """Циклическая свёртка стерео-сигнала (2, n) со стерео-откликом (2, m)."""
    n = x.shape[-1]
    k = np.zeros((2, n))
    m = min(ir.shape[-1], n)
    k[:, :m] = ir[:, :m]
    return np.fft.irfft(np.fft.rfft(x, axis=-1) * np.fft.rfft(k, axis=-1), n=n, axis=-1)


def reverb_ir(seconds=4.0, decay=3.2, damp=0.55, seed=1, predelay=0.02):
    """Синтетический импульсный отклик «подводного зала»: декоррелированный стерео-шум
    с экспоненциальным затуханием, верха гаснут быстрее низов (несколько полос)."""
    rng = np.random.default_rng(seed)
    n = int(seconds * SR)
    t = np.arange(n) / SR
    ir = np.zeros((2, n))
    bands = [(None, 400, 1.0), (400, 1500, 0.85), (1500, 4500, 0.65), (4500, None, 0.45)]
    for lo, hi, k in bands:
        noise = rng.standard_normal((2, n))
        noise = cyc_filter(noise, lo, hi, 2)
        rt = decay * (k ** (1 + damp))
        env = np.exp(-6.9 * t / rt)
        ir += noise * env
    # мягкое нарастание (диффузия) и предзадержка
    ir *= np.minimum(1, t / 0.06)
    pd = int(predelay * SR)
    ir = np.concatenate([np.zeros((2, pd)), ir[:, :n - pd]], axis=1)
    ir /= np.sqrt((ir ** 2).sum(axis=1, keepdims=True).mean())
    return ir


def delay_ir(beat, n_taps=7, fb=0.5, ping=True, dotted=True):
    """Отклик пинг-понг задержки (пунктирная восьмая)."""
    step = beat * (0.75 if dotted else 0.5)
    m = int(step * SR * (n_taps + 1)) + 1
    ir = np.zeros((2, m))
    for i in range(1, n_taps + 1):
        p = int(i * step * SR)
        ch = (i % 2) if ping else 0
        ir[ch, p] += fb ** (i - 1)
        if not ping:
            ir[1, p] += fb ** (i - 1)
    return ir


def chorus(x, depth_ms=7.0, rate=0.23, loop_len=None, base_ms=14.0):
    """Хорус: модулированная задержка, разные фазы LFO в каналах. Частота LFO
    округляется до целого числа периодов на петлю."""
    n = x.shape[-1]
    L = loop_len or n
    rate = max(1, round(rate * L / SR)) * SR / L
    idx = np.arange(n)
    out = np.empty_like(x)
    for c in range(2):
        ph = c * np.pi / 2
        d = (base_ms + depth_ms * 0.5 * (1 + np.sin(TAU * rate * idx / SR + ph))) * SR / 1000
        pos = idx - d
        i0 = np.floor(pos).astype(np.int64)
        fr = pos - i0
        a = x[c, i0 % n]
        b = x[c, (i0 + 1) % n]
        out[c] = a + (b - a) * fr
    return 0.6 * x + 0.55 * out


def polyblep_saw(freq, n, phase0=0.0):
    """Сглаженная пила (polyBLEP) — без грубого алиасинга. freq — число или массив."""
    dt = np.broadcast_to(np.asarray(freq, float) / SR, (n,))
    ph = (phase0 + np.cumsum(dt)) % 1.0
    y = 2 * ph - 1
    m = ph < dt
    x = ph[m] / dt[m]
    y[m] -= x + x - x * x - 1
    m = ph > 1 - dt
    x = (ph[m] - 1) / dt[m]
    y[m] -= x * x + x + x + 1
    return y


def adsr(n, a, d, s, r, sustain_len=None):
    a, d, r = int(a * SR), int(d * SR), int(r * SR)
    a = max(a, 16)
    if sustain_len is None:
        sustain_len = max(0, n - a - d - r)
    env = np.concatenate([
        np.linspace(0, 1, a, endpoint=False) ** 1.5,
        np.linspace(1, s, max(d, 1), endpoint=False),
        np.full(int(sustain_len), s),
        s * np.linspace(1, 0, max(r, 16)) ** 1.6,
    ])
    return env[:n] if len(env) >= n else np.concatenate([env, np.zeros(n - len(env))])


def pan_st(sig, pan):
    """Равномощностное панорамирование: pan от -1 (лево) до 1 (право)."""
    a = (pan + 1) * np.pi / 4
    return np.stack([sig * np.cos(a), sig * np.sin(a)])


# ---------------------------------------------------------------- инструменты
def inst_pad(f, dur, rng, bright=1.0, voices=5, detune=12):
    n = int((dur + 2.5) * SR)
    sig = np.zeros(n)
    for v in range(voices):
        cents = (v - (voices - 1) / 2) / max(1, (voices - 1) / 2) * detune + rng.normal(0, 1.5)
        fv = f * 2 ** (cents / 1200)
        sig += polyblep_saw(fv, n, rng.random())
    # «дыхание» — ослабленная квинта сверху и октава снизу (тёплая подложка)
    t = np.arange(n) / SR
    sig += 0.35 * np.sin(TAU * f / 2 * t + rng.random() * TAU) * voices * 0.4
    sig /= voices
    env = adsr(n, 1.6, 0.8, 0.8, 2.4, sustain_len=max(0, dur * SR - 2.4 * SR))
    return sig * env


def inst_bell(f, dur, rng, idx=2.2, ratio=3.5, decay=1.4):
    """FM-колокольчик (биолюминесцентные «искры»)."""
    n = int((dur + decay * 2.5) * SR)
    t = np.arange(n) / SR
    env_m = np.exp(-t / (decay * 0.35))
    mod = idx * env_m * np.sin(TAU * f * ratio * t)
    car = np.sin(TAU * f * t + mod + rng.random() * TAU)
    car += 0.25 * np.sin(TAU * f * 2.005 * t) * np.exp(-t / (decay * 0.5))
    env = np.minimum(1, t / 0.004) * np.exp(-t / decay)
    return car * env


def inst_pluck(f, dur, rng, cutoff=2400, decay=0.35):
    n = int((dur + decay * 3) * SR)
    t = np.arange(n) / SR
    sig = polyblep_saw(f, n, rng.random()) * 0.7 + 0.5 * np.sign(np.sin(TAU * f * 1.002 * t)) * 0.4
    # затухающий «фильтр»: смешиваем мягкую синусоиду с пилой по огибающей яркости
    br = np.exp(-t / (decay * 0.5))
    soft = np.sin(TAU * f * t)
    sig = soft * (1 - br) + sig * br
    env = np.minimum(1, t / 0.003) * np.exp(-t / decay)
    return sig * env


def inst_bass(f, dur, rng, drive=1.6, sub=0.8, decay=None):
    n = int((dur + 0.25) * SR)
    t = np.arange(n) / SR
    s = np.sin(TAU * f * t) * sub + 0.45 * polyblep_saw(f, n, 0.0) * np.exp(-t / 0.25)
    s = np.tanh(s * drive) / np.tanh(drive)
    if decay:
        env = np.minimum(1, t / 0.005) * np.exp(-t / decay)
    else:
        env = adsr(n, 0.006, 0.12, 0.75, 0.12, sustain_len=max(0, dur * SR - 0.13 * SR))
    return s * env


def inst_lead(f, dur, rng, vib=0.25, bright=0.5):
    n = int((dur + 1.0) * SR)
    t = np.arange(n) / SR
    vdepth = 0.004 * np.minimum(1, t / 0.6)
    fm = f * (1 + vdepth * np.sin(TAU * 5.2 * t))
    ph = TAU * np.cumsum(fm) / SR
    s = np.sin(ph) + bright * 0.3 * np.sin(2 * ph) + bright * 0.12 * np.sin(3 * ph) + 0.15 * np.sin(ph * 0.5)
    env = adsr(n, 0.08, 0.3, 0.7, 0.8, sustain_len=max(0, dur * SR - 0.38 * SR))
    return s * env


def inst_choir(f, dur, rng):
    """Хор «а-а»: пила через формантные резонансы (через БПФ отдельной ноты)."""
    sig = inst_pad(f, dur, rng, voices=4, detune=9)
    n = len(sig)
    X = np.fft.rfft(sig)
    fr = np.fft.rfftfreq(n, 1 / SR)
    H = np.zeros_like(fr)
    for fc, bw, g in [(730, 90, 1.0), (1090, 110, 0.5), (2440, 160, 0.25), (300, 120, 0.4)]:
        H += g / (1 + ((fr - fc) / bw) ** 2)
    return np.fft.irfft(X * H, n=n) * 3


def drum_kick(rng, f0=150, f1=42, decay=0.32, click=0.3):
    n = int((decay * 3) * SR)
    t = np.arange(n) / SR
    f = f1 + (f0 - f1) * np.exp(-t / 0.035)
    ph = TAU * np.cumsum(f) / SR
    s = np.sin(ph) * np.exp(-t / decay)
    s += click * rng.standard_normal(n) * np.exp(-t / 0.004)
    return np.tanh(s * 1.4)


def drum_noise(rng, dur, lo, hi, decay, tone_f=None):
    n = int(dur * SR)
    t = np.arange(n) / SR
    s = cyc_filter(rng.standard_normal((1, n)), lo, hi, 2)[0]
    s /= np.abs(s).max() + 1e-9
    if tone_f:
        s = s * 0.7 + 0.5 * np.sin(TAU * tone_f * t) * np.exp(-t / 0.05)
    return s * np.minimum(1, t / 0.002) * np.exp(-t / decay)


def drum_tom(rng, f0=110, decay=0.4):
    n = int(decay * 3 * SR)
    t = np.arange(n) / SR
    f = f0 * (1 + 0.6 * np.exp(-t / 0.05))
    ph = TAU * np.cumsum(f) / SR
    return np.sin(ph) * np.exp(-t / decay) + 0.15 * rng.standard_normal(n) * np.exp(-t / 0.01)


# ---------------------------------------------------------------- партитура
SCALES = {
    'aeolian': [0, 2, 3, 5, 7, 8, 10], 'dorian': [0, 2, 3, 5, 7, 9, 10],
    'lydian': [0, 2, 4, 6, 7, 9, 11], 'ionian': [0, 2, 4, 5, 7, 9, 11],
    'phrygian': [0, 1, 3, 5, 7, 8, 10], 'harmonic': [0, 2, 3, 5, 7, 8, 11],
}


class Track:
    def __init__(self, name, bpm, bars, root, scale, seed, loop=True, beats_per_bar=4):
        self.name, self.bpm, self.bars, self.root = name, bpm, bars, root
        self.scale = SCALES[scale]
        self.rng = np.random.default_rng(seed)
        self.beat = 60.0 / bpm
        self.bar = self.beat * beats_per_bar
        self.bpb = beats_per_bar
        self.loop = loop
        self.L = int(round(bars * self.bar * SR))
        self.tail = int(8 * SR)
        self.buses = {}
        self.kicks = []  # моменты ударов бочки (для сайдчейна)

    def deg(self, d, octave=0):
        """Ступень лада -> MIDI (d может быть любым целым, переносится по октавам)."""
        o, i = divmod(int(d), 7)
        return self.root + 12 * (o + octave) + self.scale[i]

    def chord(self, d, n=4, octave=0, spread=2):
        return [self.deg(d + spread * k, octave) for k in range(n)]

    def bus(self, name):
        if name not in self.buses:
            self.buses[name] = np.zeros((2, self.L + self.tail))
        return self.buses[name]

    def add(self, busname, t, sig, gain=1.0, pan=0.0):
        b = self.bus(busname)
        i = int(round(t * SR))
        if i >= self.L + self.tail:
            return
        st = pan_st(sig * gain, pan) if sig.ndim == 1 else sig * gain
        m = min(st.shape[1], b.shape[1] - i)
        b[:, i:i + m] += st[:, :m]

    def folded(self, name):
        b = self.buses.get(name)
        if b is None:
            return np.zeros((2, self.L))
        if not self.loop:
            return b
        x = b[:, :self.L].copy()
        tail = b[:, self.L:]
        k = 0
        while k < tail.shape[1]:  # хвост, длиннее петли, заворачиваем многократно
            m = min(self.L, tail.shape[1] - k)
            x[:, :m] += tail[:, k:k + m]
            k += m
        return x

    def sidechain(self, depth=0.5, rel=0.18):
        n = self.L if self.loop else self.L + self.tail
        g = np.ones(n)
        k = np.arange(int(rel * 4 * SR)) / SR
        shape = 1 - depth * np.exp(-k / rel) * np.minimum(1, k / 0.004 + 0.2)
        for t in self.kicks:
            i = int(round(t * SR))
            idx = (i + np.arange(len(shape)))
            if self.loop:
                idx %= n
            else:
                ok = idx < n
                idx, sh = idx[ok], shape[ok]
                g[idx] = np.minimum(g[idx], sh)
                continue
            g[idx] = np.minimum(g[idx], shape)
        return g


def mix(tr, spec):
    """Сведение: spec — {шина: dict(gain, lp, hp, chorus, rev, dly, duck)}."""
    n = tr.L if tr.loop else tr.L + tr.tail
    dry = np.zeros((2, n))
    rev_send = np.zeros((2, n))
    dly_send = np.zeros((2, n))
    sc = tr.sidechain(depth=spec.get('_sc_depth', 0.5)) if tr.kicks else np.ones(n)
    for name, p in spec.items():
        if name.startswith('_') or name not in tr.buses:
            continue
        x = tr.folded(name)
        if p.get('lp') or p.get('hp'):
            x = cyc_filter(x, p.get('hp'), p.get('lp'), p.get('order', 2))
        if p.get('chorus'):
            x = chorus(x, loop_len=n, rate=p.get('chorus_rate', 0.21))
        if p.get('duck'):
            x = x * (1 - p['duck'] + p['duck'] * sc)
        x *= p.get('gain', 1.0)
        dry += x
        rev_send += x * p.get('rev', 0.0)
        dly_send += x * p.get('dly', 0.0)
    ir = reverb_ir(spec.get('_rev_len', 4.5), spec.get('_rev_decay', 3.6), seed=hash(tr.name) % 1000)
    wet = cyc_conv(rev_send, ir) * 0.11
    wet = cyc_filter(wet, 90, spec.get('_rev_lp', 7000))
    dl = cyc_conv(dly_send, delay_ir(tr.beat, fb=spec.get('_dly_fb', 0.45)))
    dl = cyc_filter(dl, 250, 3800)
    out = dry + wet + dl * 0.5
    # мастер: ФВЧ от гула, мягкая сатурация, нормировка по RMS и пику
    out = cyc_filter(out, 28, None)
    out -= out.mean(axis=1, keepdims=True)
    rms = np.sqrt((out ** 2).mean())
    out *= spec.get('_level', 0.16) / (rms + 1e-9)
    out = np.tanh(out * 1.1) / 1.1
    pk = np.abs(out).max()
    if pk > 0.95:
        out *= 0.95 / pk
    return out


# ---------------------------------------------------------------- общие паттерны
def play_pads(tr, prog, bars_per_chord, octave=-1, gain=0.25, inst=inst_pad, bus='pad', active=None, notes=4):
    bpc = bars_per_chord
    for b in range(0, tr.bars, bpc):
        if active and not active(b):
            continue
        d = prog[(b // bpc) % len(prog)]
        dur = bpc * tr.bar
        for k, m in enumerate(tr.chord(d, notes, octave)):
            tr.add(bus, b * tr.bar, inst(mtof(m), dur, tr.rng), gain / notes ** 0.5, pan=(k - (notes - 1) / 2) * 0.35)


def play_arp(tr, prog, bpc, pattern, div=4, octave=1, gain=0.12, inst=inst_bell, bus='arp', active=None,
             vel_rand=0.25, kw=None):
    kw = kw or {}
    step = tr.beat / div
    steps_per_bar = tr.bpb * div
    for b in range(tr.bars):
        if active and not active(b):
            continue
        d = prog[(b // bpc) % len(prog)]
        ch = tr.chord(d, 4, octave)
        for s in range(steps_per_bar):
            p = pattern[(b * steps_per_bar + s) % len(pattern)]
            if p is None:
                continue
            m = ch[p % 4] + 12 * (p // 4)
            v = gain * (1 - vel_rand * tr.rng.random()) * (1.15 if s % div == 0 else 1)
            tr.add(bus, b * tr.bar + s * step, inst(mtof(m), step, tr.rng, **kw), v, pan=np.sin(s * 1.7) * 0.6)


def play_bass(tr, prog, bpc, rhythm, octave=-2, gain=0.3, bus='bass', active=None, kw=None):
    """rhythm — список (доля_в_такте_в_шагах16, длина_в_шагах16, смещение_ступени)."""
    kw = kw or {}
    s16 = tr.beat / 4
    for b in range(tr.bars):
        if active and not active(b):
            continue
        d = prog[(b // bpc) % len(prog)]
        for pos, ln, off in rhythm:
            m = tr.deg(d + off, octave)
            tr.add(bus, b * tr.bar + pos * s16, inst_bass(mtof(m), ln * s16 * 0.92, tr.rng, **kw), gain)


def play_drums(tr, pat, active=None, kick_kw=None, gains=None, swing=0.0):
    """pat: {'k': 'x...x...', 's': ..., 'h': ..., 'o': ..., 't': ...} шаги 16-х на такт."""
    g = {'k': 0.55, 's': 0.22, 'h': 0.07, 'o': 0.06, 't': 0.25, 'c': 0.18, 'r': 0.05}
    g.update(gains or {})
    s16 = tr.beat / 4
    kick = drum_kick(tr.rng, **(kick_kw or {}))
    for b in range(tr.bars):
        lvl = active(b) if active else 1
        if not lvl:
            continue
        for inst, line in pat.items():
            for s, ch in enumerate(line):
                if ch == '.':
                    continue
                acc = 1.0 if ch in 'xX' else 0.55
                t = b * tr.bar + s * s16 + (swing * s16 if s % 2 else 0)
                if inst == 'k':
                    tr.add('drums', t, kick, g['k'] * acc * lvl)
                    tr.kicks.append(t)
                elif inst == 's':
                    tr.add('drums', t, drum_noise(tr.rng, 0.4, 900, 6000, 0.11, tone_f=190), g['s'] * acc * lvl, 0.05)
                elif inst == 'c':  # хлопок: три близких всплеска
                    for j, dd in enumerate([0, 0.011, 0.023]):
                        tr.add('drums', t + dd, drum_noise(tr.rng, 0.3, 1100, 5000, 0.05 + 0.04 * j), g['c'] * acc * lvl, -0.1)
                elif inst == 'h':
                    tr.add('drums', t, drum_noise(tr.rng, 0.12, 7000, None, 0.025), g['h'] * acc * lvl, 0.35)
                elif inst == 'o':
                    tr.add('drums', t, drum_noise(tr.rng, 0.5, 6000, None, 0.14), g['o'] * acc * lvl, -0.3)
                elif inst == 'r':  # шейкер
                    tr.add('drums', t, drum_noise(tr.rng, 0.15, 4000, 11000, 0.04), g['r'] * acc * lvl, -0.45)
                elif inst == 't':
                    tr.add('drums', t, drum_tom(tr.rng, 95 + 35 * (s % 3)), g['t'] * acc * lvl, (s % 3 - 1) * 0.4)


def play_melody(tr, motif, start_bar, gain=0.12, octave=1, inst=inst_lead, bus='lead', kw=None):
    """motif — список (ступень|None, длина в долях). Повторяется с начала такта start_bar."""
    kw = kw or {}
    t = start_bar * tr.bar
    for d, ln in motif:
        if d is not None:
            tr.add(bus, t, inst(mtof(tr.deg(d, octave)), ln * tr.beat, tr.rng, **kw), gain, pan=tr.rng.uniform(-0.25, 0.25))
        t += ln * tr.beat


def drone(tr, midi, gain=0.08, bus='drone', wobble=0.07):
    """Непрерывный гул с частотами, кратными длине петли (бесшовно)."""
    n = tr.L
    t = np.arange(n) / SR
    out = np.zeros((2, n))
    loopsec = n / SR
    q = lambda f: max(1, round(f * loopsec)) / loopsec  # частота с целым числом периодов
    for k, (mul, a) in enumerate([(1, 1), (2.0, 0.35), (3.0, 0.12), (1.5, 0.18)]):
        f = q(mtof(midi) * mul)
        lfo = 1 + 0.4 * np.sin(TAU * q(wobble * (1 + k * 0.37)) * t + k)
        for c in range(2):
            out[c] += a * lfo * np.sin(TAU * (f + c * q(0.15)) * t + k * 1.3 + c)
    b = tr.bus(bus)
    b[:, :n] += out * gain


def noise_bed(tr, lo, hi, gain=0.02, bus='bed', swell=0.05):
    """Шум течений: циклический окрашенный шум с медленными «волнами»."""
    n = tr.L
    x = cyc_filter(tr.rng.standard_normal((2, n)), lo, hi, 2)
    x /= x.std()
    loopsec = n / SR
    f = max(1, round(swell * loopsec)) / loopsec
    t = np.arange(n) / SR
    env = 0.6 + 0.4 * np.sin(TAU * f * t)
    tr.bus(bus)[:, :n] += x * env * gain


def riser(tr, at_bar, bars, gain=0.08):
    dur = bars * tr.bar
    n = int(dur * SR)
    t = np.arange(n) / SR
    x = tr.rng.standard_normal(n)
    # нарастающий шум: от тёмного к яркому — смешиваем две фильтрованные версии
    a = cyc_filter(x[None], 200, 900)[0]
    b = cyc_filter(x[None], 2000, 9000)[0]
    k = (t / dur) ** 2
    s = (a * (1 - k) + b * k) * k / (np.abs(a).max() + 1e-9)
    tr.add('fx', at_bar * tr.bar, s, gain)


def section(spans):
    """spans — список (с_такта, до_такта); возвращает функцию активности."""
    return lambda b: any(a <= b < z for a, z in spans)


# ---------------------------------------------------------------- треки
def t_menu():
    tr = Track('menu', 68, 40, 57, 'aeolian', 11)  # ля минор, ~141 с
    prog = [0, 5, 2, 6, 0, 3, 5, 4]
    play_pads(tr, prog, 1, octave=-1, gain=0.3)
    play_pads(tr, [p + 2 for p in prog], 1, octave=0, gain=0.09, inst=inst_choir, bus='choir', active=section([(8, 24), (28, 40)]))
    drone(tr, 33, 0.05)
    noise_bed(tr, 300, 1800, 0.012)
    arp = [0, None, 2, None, 1, None, 3, None, 4, None, 2, None, 5, None, 3, None]
    play_arp(tr, prog, 1, arp, div=2, octave=1, gain=0.06, active=section([(4, 36)]), kw=dict(decay=1.8))
    motif = [(4, 2), (3, 1), (2, 1), (0, 3), (None, 1), (2, 2), (4, 1), (5, 1), (4, 4), (None, 4)]
    for sb in (12, 20, 28):
        play_melody(tr, motif, sb, gain=0.07, octave=1, inst=inst_bell, bus='mel', kw=dict(decay=2.2, idx=1.2, ratio=2.0))
    play_drums(tr, {'r': '..x...x...x...xx'}, active=section([(16, 32)]))
    return tr, {'pad': dict(gain=1, lp=1600, chorus=1, rev=0.9), 'choir': dict(gain=1, rev=1.2, chorus=1),
                'drone': dict(gain=1, lp=500, rev=0.3), 'bed': dict(gain=1, rev=0.6),
                'arp': dict(gain=1, rev=0.8, dly=0.5), 'mel': dict(gain=1, rev=1.0, dly=0.4),
                'drums': dict(gain=1, rev=0.3), '_rev_decay': 5.0, '_rev_len': 6.0, '_level': 0.13}


def t_zone1():
    tr = Track('zone1', 92, 56, 53, 'lydian', 21)  # фа лидийский — светлое мелководье, ~146 с
    prog = [0, 4, 5, 3, 0, 1, 4, 2]
    play_pads(tr, prog, 2, octave=0, gain=0.24)
    noise_bed(tr, 800, 5000, 0.008)
    arp = [0, 2, 4, 2, 1, 3, 5, 3, 0, 2, 6, 2, 1, 4, 5, 3]
    play_arp(tr, prog, 2, arp, div=4, octave=1, gain=0.07, kw=dict(decay=0.6, idx=1.6, ratio=4.0), active=section([(0, 52)]))
    play_bass(tr, prog, 2, [(0, 6, 0), (6, 2, 0), (8, 6, 4), (14, 2, 0)], octave=-1, gain=0.22, active=section([(4, 56)]))
    full = section([(8, 24), (28, 52)])
    play_drums(tr, {'k': 'x.......x.......', 'h': '..x...x...x...x.', 'r': 'x.x.x.x.x.x.x.x.', 's': '....x.......x...'},
               active=lambda b: 1 if full(b) else (0.5 if 4 <= b < 56 else 0), gains={'s': 0.12, 'k': 0.4})
    motif = [(4, 1), (5, 0.5), (4, 0.5), (2, 2), (None, 1), (1, 1), (2, 1), (4, 1), (6, 2), (5, 2), (None, 4),
             (4, 1), (2, 1), (1, 1), (0, 1), (1, 3), (None, 5)]
    for sb in (12, 16, 32, 36, 44):
        play_melody(tr, motif, sb, gain=0.085, octave=1, kw=dict(bright=0.6))
    for rb in (6, 26):
        riser(tr, rb, 2, 0.05)
    return tr, {'pad': dict(gain=1, lp=2600, chorus=1, rev=0.7, duck=0.35), 'bed': dict(gain=1, rev=0.5),
                'arp': dict(gain=1, rev=0.6, dly=0.45, lp=6000), 'bass': dict(gain=1, lp=900, duck=0.4),
                'drums': dict(gain=1, rev=0.15), 'lead': dict(gain=1, rev=0.7, dly=0.35, chorus=1),
                'fx': dict(gain=1, rev=0.8), '_level': 0.15, '_sc_depth': 0.45}


def t_zone2():
    tr = Track('zone2', 98, 60, 49, 'aeolian', 31)  # до-диез минор — тьма течений, ~147 с
    prog = [0, 0, 5, 3, 0, 6, 5, 4]
    play_pads(tr, prog, 2, octave=-1, gain=0.26)
    drone(tr, 25, 0.06, wobble=0.11)
    noise_bed(tr, 120, 900, 0.02, swell=0.08)
    play_bass(tr, prog, 2, [(s, 2, 0) for s in range(0, 16, 2)], octave=-2, gain=0.24, kw=dict(decay=0.16),
              active=section([(4, 60)]))
    arp = [0, None, 1, 2, None, 3, 2, None, 1, None, 0, 2, None, 4, 3, None]
    play_arp(tr, prog, 2, arp, div=4, octave=0, gain=0.09, inst=inst_pluck, kw=dict(decay=0.22), active=section([(8, 56)]))
    full = section([(12, 28), (36, 56)])
    play_drums(tr, {'k': 'x.....x...x.....', 'c': '....x.......x...', 'h': 'x.xxx.xxx.xxx.xx'},
               active=lambda b: 1 if full(b) else (0.45 if 4 <= b < 60 else 0), gains={'h': 0.045, 'c': 0.13}, swing=0.12)
    motif = [(0, 1.5), (2, 0.5), (3, 2), (2, 1), (-1, 1), (0, 4), (None, 2), (4, 1.5), (3, 0.5), (2, 2), (0, 2), (-2, 4), (None, 4)]
    for sb in (16, 20, 40, 48):
        play_melody(tr, motif, sb, gain=0.08, octave=1, kw=dict(bright=0.3))
    for rb in (10, 34):
        riser(tr, rb, 2, 0.06)
    return tr, {'pad': dict(gain=1, lp=1200, chorus=1, rev=0.8, duck=0.5), 'drone': dict(gain=1, lp=400),
                'bed': dict(gain=1, rev=0.5), 'bass': dict(gain=1, lp=700, duck=0.6),
                'arp': dict(gain=1, rev=0.5, dly=0.6, lp=3500), 'drums': dict(gain=1, rev=0.2, lp=9000),
                'lead': dict(gain=1, rev=0.9, dly=0.4, chorus=1), 'fx': dict(gain=1, rev=0.8),
                '_level': 0.15, '_sc_depth': 0.6, '_rev_decay': 4.2}


def t_zone3():
    tr = Track('zone3', 84, 52, 52, 'phrygian', 41)  # ми фригийский — лёд и кости, ~149 с
    prog = [0, 1, 0, 6, 0, 1, 5, 4]
    play_pads(tr, prog, 2, octave=0, gain=0.2)
    play_pads(tr, [p + 4 for p in prog], 2, octave=1, gain=0.05, inst=inst_choir, bus='choir', active=section([(16, 48)]))
    drone(tr, 28, 0.07, wobble=0.05)
    drone(tr, 29, 0.02, bus='drone2', wobble=0.13)  # полутон сверху — ледяное биение
    noise_bed(tr, 3000, 12000, 0.006, swell=0.1)
    glass = [0, None, None, 5, None, 2, None, None, 6, None, None, 1, None, None, 4, None]
    play_arp(tr, prog, 2, glass, div=4, octave=2, gain=0.06, kw=dict(decay=1.6, idx=3.0, ratio=5.41), active=section([(0, 52)]))
    play_bass(tr, prog, 2, [(0, 10, 0), (12, 4, 1)], octave=-2, gain=0.22, active=section([(8, 52)]))
    tense = section([(20, 36), (40, 52)])
    play_drums(tr, {'k': 'x.........x.....', 'h': '..x..x..x..x..x.', 't': '.......x.......x', 's': '........x.......'},
               active=lambda b: 1 if tense(b) else (0.5 if b >= 8 else 0), gains={'t': 0.16, 'h': 0.05, 's': 0.14})
    motif = [(0, 2), (1, 2), (0, 1), (-1, 1), (-2, 2), (None, 2), (3, 1), (4, 1), (1, 2), (0, 4), (None, 4)]
    for sb in (24, 28, 44):
        play_melody(tr, motif, sb, gain=0.07, octave=1, inst=inst_lead, kw=dict(bright=0.15))
    return tr, {'pad': dict(gain=1, lp=3200, hp=150, chorus=1, rev=1.0, duck=0.3), 'choir': dict(gain=1, rev=1.3),
                'drone': dict(gain=1, lp=600), 'drone2': dict(gain=1, lp=600), 'bed': dict(gain=1, rev=0.8),
                'arp': dict(gain=1, rev=1.0, dly=0.5), 'bass': dict(gain=1, lp=600, duck=0.4),
                'drums': dict(gain=1, rev=0.35), 'lead': dict(gain=1, rev=1.0, dly=0.3),
                '_level': 0.14, '_rev_decay': 6.0, '_rev_len': 7.0, '_rev_lp': 9000}


def t_zone4():
    tr = Track('zone4', 112, 68, 53, 'harmonic', 51)  # фа гармонический минор — бездна, ~146 с
    prog = [0, 5, 3, 4, 0, 5, 1, 4]
    play_pads(tr, prog, 2, octave=-1, gain=0.25)
    drone(tr, 29, 0.05, wobble=0.2)
    noise_bed(tr, 100, 700, 0.02, swell=0.12)
    play_bass(tr, prog, 2, [(s, 1, 0 if s % 8 else 0) for s in range(16)] , octave=-2, gain=0.22, kw=dict(decay=0.09),
              active=section([(4, 68)]))
    arp = [0, 1, 2, 3, 4, 3, 2, 1, 0, 2, 4, 6, 4, 2, 1, 3]
    play_arp(tr, prog, 2, arp, div=4, octave=0, gain=0.08, inst=inst_pluck, kw=dict(decay=0.15), active=section([(8, 64)]))
    full = section([(12, 30), (36, 64)])
    play_drums(tr, {'k': 'x...x...x...x..x', 's': '....x.......x...', 'h': '..x...x...x...x.', 'r': 'xxxxxxxxxxxxxxxx',
                    't': '.............xxx'},
               active=lambda b: 1 if full(b) else (0.5 if b >= 4 else 0.3), gains={'r': 0.03, 't': 0.14})
    motif = [(0, 1), (2, 1), (3, 1), (4, 1), (5, 2), (4, 1), (6, 1), (7, 3), (None, 1), (6, 1), (5, 1), (4, 2), (3, 2), (4, 4), (None, 4)]
    for sb in (16, 20, 44, 52):
        play_melody(tr, motif, sb, gain=0.08, octave=1, kw=dict(bright=0.8))
    for rb in (10, 34, 62):
        riser(tr, rb, 2, 0.07)
    return tr, {'pad': dict(gain=1, lp=1800, chorus=1, rev=0.6, duck=0.6), 'drone': dict(gain=1, lp=400),
                'bed': dict(gain=1, rev=0.3), 'bass': dict(gain=1, lp=1100, duck=0.6),
                'arp': dict(gain=1, rev=0.4, dly=0.5, lp=5000), 'drums': dict(gain=1, rev=0.12),
                'lead': dict(gain=1, rev=0.6, dly=0.3, chorus=1), 'fx': dict(gain=1, rev=0.6),
                '_level': 0.17, '_sc_depth': 0.6}


def t_boss1():
    tr = Track('boss1', 126, 72, 55, 'aeolian', 61)  # соль минор — хищный пульс удильщика, ~137 с
    prog = [0, 0, 5, 6, 0, 0, 3, 4]
    play_pads(tr, prog, 2, octave=-1, gain=0.22)
    play_bass(tr, prog, 2, [(s, 1, 0) for s in range(16) if s % 4 != 0], octave=-2, gain=0.26, kw=dict(decay=0.07, drive=2.5),
              active=section([(0, 72)]))
    play_bass(tr, prog, 2, [(0, 2, 0)], octave=-3, gain=0.25, kw=dict(decay=0.3), bus='sub')
    arp = [0, None, 0, 4, None, 0, 3, None, 0, None, 0, 5, None, 4, 3, None]
    play_arp(tr, prog, 2, arp, div=4, octave=1, gain=0.08, inst=inst_pluck, kw=dict(decay=0.12), active=section([(8, 72)]))
    full = section([(8, 32), (40, 72)])
    play_drums(tr, {'k': 'x...x...x...x...', 'c': '....x.......x...', 'h': '..x...x...x...x.', 'r': 'x.xxx.xxx.xxx.xx',
                    't': '..........x..x.x'},
               active=lambda b: 1 if full(b) else 0.55, gains={'k': 0.62, 'r': 0.035, 't': 0.18})
    motif = [(0, 0.5), (None, 0.5), (0, 0.5), (1, 0.5), (2, 1), (-1, 1), (0, 3), (None, 1),
             (4, 0.5), (None, 0.5), (4, 0.5), (5, 0.5), (4, 1), (2, 1), (1, 4)]
    for sb in (16, 20, 48, 52, 60):
        play_melody(tr, motif, sb, gain=0.085, octave=1, kw=dict(bright=1.0))
    for rb in (6, 38, 70):
        riser(tr, rb, 2, 0.08)
    return tr, {'pad': dict(gain=1, lp=1500, chorus=1, rev=0.5, duck=0.7), 'bass': dict(gain=1, lp=1600, duck=0.5),
                'sub': dict(gain=1, lp=200, duck=0.3), 'arp': dict(gain=1, rev=0.3, dly=0.4, lp=4500),
                'drums': dict(gain=1, rev=0.12), 'lead': dict(gain=1, rev=0.5, dly=0.25),
                'fx': dict(gain=1, rev=0.6), '_level': 0.18, '_sc_depth': 0.65, '_rev_decay': 2.6}


def t_boss2():
    tr = Track('boss2', 116, 64, 58, 'dorian', 71)  # си-бемоль дорийский — гипнотичная Матерь Глубин, ~132 с
    prog = [0, 6, 5, 6]
    play_pads(tr, prog, 4, octave=-1, gain=0.22)
    play_pads(tr, [p + 2 for p in prog], 4, octave=0, gain=0.07, inst=inst_choir, bus='choir', active=section([(8, 64)]))
    # гипнотическое арпеджио 3 против 4: паттерн из 3 шагов на сетке 16-х
    play_arp(tr, prog, 4, [0, 2, 4], div=4, octave=1, gain=0.075, kw=dict(decay=0.5, idx=2.0, ratio=3.0))
    play_arp(tr, prog, 4, [4, None, 3, None, 2], div=4, octave=2, gain=0.035, bus='arp2', kw=dict(decay=0.8, idx=1.0, ratio=2.0),
             active=section([(16, 64)]))
    play_bass(tr, prog, 4, [(0, 3, 0), (3, 3, 0), (6, 2, 4), (10, 3, 0), (13, 3, 2)], octave=-2, gain=0.24, kw=dict(decay=0.22))
    full = section([(8, 28), (36, 64)])
    play_drums(tr, {'k': 'x..x..x...x..x..', 's': '....x.......x...', 'h': 'x.x.x.x.x.x.x.x.', 't': '..x..x..x.....x.'},
               active=lambda b: 1 if full(b) else 0.5, gains={'t': 0.14, 's': 0.16, 'h': 0.05})
    motif = [(4, 3), (3, 1), (2, 2), (4, 2), (3, 3), (2, 1), (0, 4), (None, 4)]
    for sb in (12, 20, 40, 48, 56):
        play_melody(tr, motif, sb, gain=0.08, octave=1, kw=dict(bright=0.4))
    riser(tr, 34, 2, 0.06)
    return tr, {'pad': dict(gain=1, lp=1400, chorus=1, rev=0.8, duck=0.5), 'choir': dict(gain=1, rev=1.1),
                'arp': dict(gain=1, rev=0.6, dly=0.6), 'arp2': dict(gain=1, rev=1.0, dly=0.6),
                'bass': dict(gain=1, lp=800, duck=0.5), 'drums': dict(gain=1, rev=0.2),
                'lead': dict(gain=1, rev=0.9, dly=0.4, chorus=1), 'fx': dict(gain=1, rev=0.6),
                '_level': 0.17, '_sc_depth': 0.55, '_dly_fb': 0.55, '_rev_decay': 4.5}


def t_boss3():
    tr = Track('boss3', 128, 76, 50, 'harmonic', 81)  # ре гармонический минор — эпичное Сердце Бездны, ~143 с
    prog = [0, 5, 2, 4, 0, 3, 5, 4]
    play_pads(tr, prog, 2, octave=-1, gain=0.24)
    play_pads(tr, [p + 2 for p in prog], 2, octave=0, gain=0.11, inst=inst_choir, bus='choir', active=section([(8, 76)]))
    drone(tr, 26, 0.04, wobble=0.25)
    play_bass(tr, prog, 2, [(0, 1, 0), (2, 1, 0), (3, 1, 0), (6, 1, 0), (8, 1, 0), (10, 1, 0), (11, 1, 0), (14, 1, 4)],
              octave=-2, gain=0.26, kw=dict(decay=0.12, drive=2.2))
    arp = [0, 2, 4, 7, 4, 2, 0, 2, 1, 3, 5, 7, 5, 3, 1, 3]
    play_arp(tr, prog, 2, arp, div=4, octave=1, gain=0.06, inst=inst_pluck, kw=dict(decay=0.13), active=section([(16, 76)]))
    full = section([(8, 32), (40, 76)])
    # сердцебиение: «тук-тук» (бочка на 1 и 2-й шестнадцатой, затем на 3-й доле)
    play_drums(tr, {'k': 'x..x....x..x....', 's': '....x.......x...', 'h': '..x...x...x...x.', 'o': '..............x.',
                    't': '........x.x.xxxx'},
               active=lambda b: 1 if full(b) else 0.55, kick_kw=dict(f0=120, f1=38, decay=0.42, click=0.15),
               gains={'k': 0.7, 't': 0.2})
    motif = [(0, 2), (4, 2), (3, 1), (2, 1), (3, 2), (1, 2), (2, 1), (0, 1), (-1, 2), (0, 4), (None, 4),
             (4, 2), (5, 1), (6, 1), (7, 4), (6, 1), (5, 1), (4, 2), (3, 4), (None, 4)]
    for sb in (16, 24, 48, 56, 64):
        play_melody(tr, motif, sb, gain=0.09, octave=1, kw=dict(bright=0.9))
    for rb in (6, 38, 74):
        riser(tr, rb, 2, 0.08)
    return tr, {'pad': dict(gain=1, lp=2000, chorus=1, rev=0.7, duck=0.55), 'choir': dict(gain=1, rev=1.2, duck=0.3),
                'drone': dict(gain=1, lp=300), 'bass': dict(gain=1, lp=1200, duck=0.5),
                'arp': dict(gain=1, rev=0.4, dly=0.4, lp=5000), 'drums': dict(gain=1, rev=0.25),
                'lead': dict(gain=1, rev=0.8, dly=0.3, chorus=1), 'fx': dict(gain=1, rev=0.7),
                '_level': 0.18, '_sc_depth': 0.6, '_rev_decay': 4.0}


def t_victory():
    tr = Track('victory', 100, 4, 60, 'ionian', 91, loop=False)  # до мажор, ~9.6 с
    for k, d in enumerate([0, 2, 4, 7, 9, 11, 14]):
        tr.add('arp', k * tr.beat / 2, inst_bell(mtof(tr.deg(d, 1)), 0.5, tr.rng, decay=1.6, idx=1.5, ratio=2.0), 0.12, pan=(k - 3) * 0.2)
    for k, m in enumerate(tr.chord(0, 4, 0)):
        tr.add('pad', 1.2, inst_pad(mtof(m), 5.0, tr.rng), 0.16, pan=(k - 1.5) * 0.4)
        tr.add('choir', 1.2, inst_choir(mtof(m + 12), 5.0, tr.rng), 0.06)
    for k, m in enumerate(tr.chord(3, 4, 0)):
        tr.add('pad', 0.0, inst_pad(mtof(m), 1.2, tr.rng), 0.1)
    tr.add('bass', 1.2, inst_bass(mtof(36), 5.0, tr.rng), 0.3)
    tr.add('drums', 1.2, drum_kick(tr.rng, decay=0.6), 0.5)
    tr.add('drums', 1.2, drum_noise(tr.rng, 2.5, 5000, None, 0.9), 0.08)
    play_melody(tr, [(7, 0.5), (9, 0.5), (11, 0.5), (14, 3)], 0.5, gain=0.1, octave=0)
    return tr, {'pad': dict(gain=1, chorus=1, rev=0.8, lp=3000), 'choir': dict(gain=1, rev=1.0), 'arp': dict(gain=1, rev=0.8, dly=0.4),
                'bass': dict(gain=1, lp=500), 'drums': dict(gain=1, rev=0.4), 'lead': dict(gain=1, rev=0.8, dly=0.3), '_level': 0.15}


def t_gameover():
    tr = Track('gameover', 70, 2, 57, 'aeolian', 99, loop=False)  # ля минор, ~6.9 с (+ хвост)
    t = 0.0
    for d, ln in [(4, 0.6), (3, 0.6), (2, 0.6), (1, 0.6), (0, 2.5)]:
        tr.add('mel', t, inst_bell(mtof(tr.deg(d, 1)), ln, tr.rng, decay=1.8, idx=1.0, ratio=2.0), 0.12)
        t += ln * 0.6 * tr.beat / 0.6
    for m in tr.chord(0, 3, -1):
        tr.add('pad', 0.0, inst_pad(mtof(m), 4.5, tr.rng, detune=20), 0.12)
    tr.add('bass', 0.0, inst_bass(mtof(33), 4.5, tr.rng), 0.25)
    tr.add('drums', 0.0, drum_kick(tr.rng, f0=90, f1=30, decay=0.9), 0.4)
    return tr, {'pad': dict(gain=1, chorus=1, rev=1.0, lp=1200), 'mel': dict(gain=1, rev=1.0, dly=0.4),
                'bass': dict(gain=1, lp=300), 'drums': dict(gain=1, rev=0.5), '_level': 0.13, '_rev_decay': 4.0}


TRACKS = {'menu': t_menu, 'zone1': t_zone1, 'zone2': t_zone2, 'zone3': t_zone3, 'zone4': t_zone4,
          'boss1': t_boss1, 'boss2': t_boss2, 'boss3': t_boss3, 'victory': t_victory, 'gameover': t_gameover}


ONESHOT_LEN = {'victory': 9.5, 'gameover': 7.5}  # секунды вместе с затуханием


def render(name):
    tr, spec = TRACKS[name]()
    out = mix(tr, spec)
    if not tr.loop:  # одноразовый трек: обрезаем тишину и плавно гасим конец
        n = min(out.shape[1], int(ONESHOT_LEN.get(name, 9.0) * SR))
        out = out[:, :n]
        fade = int(2.0 * SR)
        out[:, -fade:] *= np.linspace(1, 0, fade) ** 2
        out[:, :64] *= np.linspace(0, 1, 64)
    return out.astype(np.float32)


def encode(name, x):
    os.makedirs(OUT, exist_ok=True)
    path = os.path.join(OUT, name + '.ogg')
    pcm = np.ascontiguousarray(x.T).astype('<f4').tobytes()
    cmd = [FFMPEG, '-y', '-loglevel', 'error', '-f', 'f32le', '-ar', str(SR), '-ac', '2', '-i', 'pipe:0',
           '-c:a', 'libvorbis', '-q:a', '5', '-metadata', 'title=Svet Bezdny - ' + name, path]
    subprocess.run(cmd, input=pcm, check=True)
    return path


def seam_report(x):
    """Скачок на стыке петли относительно типичного шага сигнала."""
    jump = np.abs(x[:, 0] - x[:, -1]).max()
    typ = np.percentile(np.abs(np.diff(x, axis=1)), 99.9)
    return jump, typ


if __name__ == '__main__':
    names = sys.argv[1:] or list(TRACKS)
    for nm in names:
        x = render(nm)
        p = encode(nm, x)
        j, typ = seam_report(x)
        print(f'{nm:9s} {x.shape[1] / SR:6.1f} c  пик {np.abs(x).max():.2f}  стык {j:.4f} (тип. шаг {typ:.4f})  '
              f'{os.path.getsize(p) / 1e6:.2f} МБ', flush=True)

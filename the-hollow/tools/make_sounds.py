"""Синтезирует 7 жутких звуков (.ogg) для The Hollow.
Нужны numpy и ffmpeg с libvorbis.
Запуск: python3 tools/make_sounds.py  (из папки the-hollow)

Это заготовки. Если найдёте звуки лучше (например, на freesound.org
с лицензией CC0), просто замените файлы в RP/sounds/hollow/ на свои
с теми же именами.
"""
import os
import subprocess
import tempfile
import wave

import numpy as np

SR = 44100
OUT = "RP/sounds/hollow"
rng = np.random.default_rng(7)


def t(sec):
    return np.linspace(0, sec, int(SR * sec), endpoint=False)


def env(n, attack=0.05, release=0.3):
    e = np.ones(n)
    a, r = int(n * attack), int(n * release)
    if a:
        e[:a] = np.linspace(0, 1, a)
    if r:
        e[-r:] = np.linspace(1, 0, r)
    return e


def lowpass(x, k=200):
    return np.convolve(x, np.ones(k) / k, mode="same")


def bandnoise(n, k_low, k_high):
    w = rng.standard_normal(n)
    return lowpass(w, k_low) - lowpass(w, k_high)


def norm(x, peak=0.9):
    return x / (np.max(np.abs(x)) + 1e-9) * peak


def save(name, x):
    x = norm(x)
    with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as f:
        tmp = f.name
    with wave.open(tmp, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(SR)
        w.writeframes((x * 32767).astype(np.int16).tobytes())
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-i", tmp, "-c:a", "libvorbis", "-q:a", "4",
                    os.path.join(OUT, name + ".ogg")], check=True)
    os.remove(tmp)


os.makedirs(OUT, exist_ok=True)

# ambient1 — низкий гул с биениями (появление)
x = t(6)
s = (np.sin(2 * np.pi * 42 * x) + 0.7 * np.sin(2 * np.pi * 43.3 * x)
     + 0.4 * np.sin(2 * np.pi * 84.5 * x) + 0.3 * lowpass(rng.standard_normal(len(x)), 400))
save("ambient1", s * env(len(x), 0.3, 0.4))

# ambient2 — далёкий "ветер" с завыванием
x = t(7)
wind = bandnoise(len(x), 30, 6) * (0.6 + 0.4 * np.sin(2 * np.pi * 0.3 * x))
howl = 0.25 * np.sin(2 * np.pi * (220 + 30 * np.sin(2 * np.pi * 0.2 * x)) * x) * env(len(x), 0.4, 0.4)
save("ambient2", (wind + howl) * env(len(x), 0.2, 0.3))

# breath — тяжёлое дыхание (вдох-выдох)
parts = []
for dur, pitch in [(0.9, 1.0), (1.2, 0.8)]:
    x = t(dur)
    n = bandnoise(len(x), 8, 2) * np.sin(np.pi * x / dur) ** 2
    rasp = 0.3 * np.sin(2 * np.pi * 70 * pitch * x) * np.sin(np.pi * x / dur)
    parts += [n + rasp, np.zeros(int(SR * 0.25))]
save("breath", np.concatenate(parts))

# step — тяжёлый глухой шаг
x = t(0.45)
thump = np.sin(2 * np.pi * (70 * np.exp(-x * 6)) * x) * np.exp(-x * 9)
crunch = 0.35 * bandnoise(len(x), 6, 1) * np.exp(-x * 25)
save("step", thump + crunch)

# scream — искажённый визг с вибрато
x = t(2.2)
f = 520 + 260 * np.sin(2 * np.pi * 7 * x) + 300 * x
s = np.sign(np.sin(2 * np.pi * np.cumsum(f) / SR)) * 0.5 + np.sin(2 * np.pi * np.cumsum(f * 1.5) / SR) * 0.4
s += 0.4 * bandnoise(len(x), 3, 1)
save("scream", lowpass(s, 4) * env(len(x), 0.03, 0.5))

# laugh — низкий прерывистый смех "ха-ха-ха"
parts = []
for i in range(6):
    x = t(0.18)
    f0 = 140 - i * 8
    syl = (np.sin(2 * np.pi * f0 * x) + 0.5 * np.sin(2 * np.pi * f0 * 2.02 * x)) * np.sin(np.pi * x / 0.18) ** 2
    parts += [syl + 0.2 * bandnoise(len(x), 4, 1) * np.sin(np.pi * x / 0.18), np.zeros(int(SR * 0.09))]
save("laugh", np.concatenate(parts))

# whisper — шипящий шёпот с "слогами"
x = t(2.6)
syll = np.clip(np.sin(2 * np.pi * 3.1 * x) + 0.3 * np.sin(2 * np.pi * 7.3 * x), 0, None)
save("whisper", bandnoise(len(x), 2, 1) * syll * env(len(x), 0.1, 0.3))

print("sounds ok")

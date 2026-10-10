#!/usr/bin/env python3
"""K3 audio assets, synthesised from scratch with numpy (own work: no third-party samples, nothing to license).
Deep impacts, sub drops, metal hits, risers, whips and a dark minimal A-minor bed (90 s, played once from 0 -> no loop, no seam).
usage: synth_k3.py OUTDIR"""
import sys, wave
from pathlib import Path
import numpy as np
from scipy.signal import butter, sosfilt

SR = 48000
rng = np.random.default_rng(7)
out = Path(sys.argv[1])
(out / 'sfx').mkdir(parents=True, exist_ok=True)
(out / 'music').mkdir(parents=True, exist_ok=True)


def tt(d): return np.arange(int(d * SR)) / SR
def lp(x, f, o=2): return sosfilt(butter(o, f, 'low', fs=SR, output='sos'), x)
def hp(x, f, o=2): return sosfilt(butter(o, f, 'high', fs=SR, output='sos'), x)
def bp(x, a, b, o=2): return sosfilt(butter(o, [a, b], 'band', fs=SR, output='sos'), x)
def sweep(f0, f1, d, k=None):
    t = tt(d); k = k or d / 4
    f = f1 + (f0 - f1) * np.exp(-t / k)
    return np.sin(2 * np.pi * np.cumsum(f) / SR)
def norm(x, pk=0.95): return x / (np.abs(x).max() + 1e-9) * pk
def wav(path, x):
    x = np.clip(x, -1, 1)
    s = (np.stack([x, x], 1) * 32767).astype('<i2')
    with wave.open(str(path), 'wb') as w:
        w.setnchannels(2); w.setsampwidth(2); w.setframerate(SR); w.writeframes(s.tobytes())


# ---------------------------------------------------------------- sfx
def impact_deep():
    d = 1.6; t = tt(d)
    body = sweep(90, 30, d, 0.22) * np.exp(-t / 0.55)
    thud = lp(rng.standard_normal(len(t)), 300) * np.exp(-t / 0.05) * 1.2
    crack = hp(rng.standard_normal(len(t)), 1500) * np.exp(-t / 0.012) * 0.25
    return norm(body + thud + crack)


def boom_low():
    d = 2.0; t = tt(d)
    a = np.minimum(1, t / 0.02)
    return norm((sweep(60, 32, d, 0.5) * np.exp(-t / 0.8) + 0.4 * lp(rng.standard_normal(len(t)), 140) * np.exp(-t / 0.25)) * a)


def sub_drop():
    d = 1.5; t = tt(d)
    return norm(sweep(170, 26, d, 0.35) * np.exp(-t / 0.7) * np.minimum(1, t / 0.01))


def metal_hit():
    d = 1.8; t = tt(d); x = np.zeros(len(t))
    for f, a, dec in ((196, 1.0, 0.9), (318, 0.7, 0.7), (489, 0.5, 0.55), (683, 0.35, 0.4), (1130, 0.2, 0.25), (1640, 0.12, 0.15)):
        x += a * np.sin(2 * np.pi * f * t + rng.uniform(0, 6)) * np.exp(-t / dec)
    x += 0.5 * bp(rng.standard_normal(len(t)), 800, 5000) * np.exp(-t / 0.03)
    x = lp(x, 5000) + 0.9 * sweep(70, 36, d, 0.2) * np.exp(-t / 0.4)
    return norm(x)


def riser():
    d = 1.1; t = tt(d); n = rng.standard_normal(len(t)); y = np.zeros(len(t))
    step = int(0.04 * SR)
    for i in range(0, len(t) - step, step):
        u = i / len(t); c = 180 * (14 ** u)
        y[i:i + step] = bp(n[i:i + step], c * 0.7, min(c * 1.4, 20000), 2)
    y = y * (t / d) ** 2.2 + 0.5 * sweep(40, 120, d, 0.8) * (t / d) ** 2
    y *= np.minimum(1, (d - t) / 0.01)
    return norm(y)


def whip():
    d = 0.4; t = tt(d); n = rng.standard_normal(len(t)); y = np.zeros(len(t)); step = int(0.02 * SR)
    for i in range(0, len(t) - step, step):
        u = i / len(t); c = 500 * (8 ** u)
        y[i:i + step] = bp(n[i:i + step], c * 0.75, min(c * 1.3, 20000), 2)
    env = np.sin(np.pi * np.minimum(1, t / d)) ** 1.5
    return norm(y * env)


def tick_low():
    d = 0.5; t = tt(d)
    return norm(sweep(120, 55, d, 0.05) * np.exp(-t / 0.12) + 0.2 * bp(rng.standard_normal(len(t)), 900, 3500) * np.exp(-t / 0.01))


for name, fn in (('impact_deep', impact_deep), ('boom_low', boom_low), ('sub_drop', sub_drop), ('metal_hit', metal_hit), ('riser', riser), ('whip', whip), ('tick_low', tick_low)):
    wav(out / 'sfx' / f'{name}.wav', fn())

# ---------------------------------------------------------------- music: dark minimal bed, A minor, 72 BPM, 90 s
BPM = 72; beat = 60 / BPM; D = 90.0; n = int(D * SR); t = tt(D)
bed = np.zeros(n)
hz = lambda m: 440 * 2 ** ((m - 69) / 12)


def saw_pad(f, amp, harm=9):
    y = np.zeros(n)
    for det in (-0.35, 0.0, 0.4):
        for k in range(1, harm + 1):
            y += amp * np.sin(2 * np.pi * (f + det) * k * t + rng.uniform(0, 6)) / k ** 1.25
    return y


chords = [(45, 52, 57, 60), (41, 48, 53, 57), (36, 48, 55, 60), (43, 50, 55, 59)]     # Am, F, C, G over a low root
bar = 4 * beat; clen = 4 * bar
for ci in range(int(D / clen) + 1):
    c = chords[ci % 4]; s0 = ci * clen
    env = np.zeros(n); i0, i1 = int(s0 * SR), min(n, int((s0 + clen + 1.5) * SR))
    if i0 >= n: break
    ln = i1 - i0; e = np.minimum(1, np.arange(ln) / (1.8 * SR)) * np.minimum(1, (ln - np.arange(ln)) / (1.5 * SR)); env[i0:i1] = e
    for m in c:
        bed += saw_pad(hz(m), 0.055 if m > 40 else 0.09, 7) * env
slow = 0.75 + 0.25 * np.sin(2 * np.pi * t / 17.0)
bed = lp(bed * slow, 1400, 2)
bed = 0.8 * bed + 0.6 * lp(saw_pad(hz(33), 0.06, 5), 220)

# pulse: sub kick on 1 and 3, faint metal tick on the off-eighths, low pluck pattern for mid-range presence
kick = (sweep(95, 38, 0.5, 0.07) * np.exp(-np.arange(int(0.5 * SR)) / SR / 0.16))
tick = hp(rng.standard_normal(int(0.08 * SR)), 5500) * np.exp(-np.arange(int(0.08 * SR)) / SR / 0.012)
pat = [57, 60, 64, 60, 57, 55, 52, 55]
pl = np.zeros(n); k = 0; tb = 0.0
while tb < D - 1:
    bi = int(round(tb / beat))
    if bi % 4 in (0, 2):
        i = int(tb * SR); m = min(len(kick), n - i); pl[i:i + m] += 1.15 * kick[:m]
    if bi % 2 == 1:
        i = int((tb + beat / 2) * SR); m = min(len(tick), n - i); pl[i:i + m] += 0.10 * tick[:m]
    if bi % 2 == 0:
        f = hz(pat[(bi // 2) % len(pat)]); dur = 1.1; i = int(tb * SR); m = min(int(dur * SR), n - i); tm = np.arange(m) / SR
        note = (np.sin(2 * np.pi * f * tm) + 0.3 * np.sin(4 * np.pi * f * tm)) * np.exp(-tm / 0.38) * np.minimum(1, tm / 0.004)
        pl[i:i + m] += 0.16 * note
    tb += beat
music = bed * 0.9 + pl * 0.8
music = lp(music, 9000, 2)
music = np.tanh(music * 1.3) / 1.3
music = norm(music, 0.9)
wav(out / 'music' / 'music_dark_pulse.wav', music)
print('ok', [p.name for p in sorted((out / 'sfx').iterdir())], 'music', D, 's')

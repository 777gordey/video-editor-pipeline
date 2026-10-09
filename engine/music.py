"""Музыкальная подложка, написанная кодом (никаких чужих треков, никаких стоков): аккорды, бас, пэд, «электропиано»,
мягкая ударная секция, реверб, мастеринг. Пять пресетов (по music_idx стиля). Только numpy + scipy."""
import numpy as np
from scipy import signal

SR = 48000

# (bpm, прогрессия: [(корень_баса_midi, [ноты пэда midi])...], drums: 0 нет / 1 мягко / 2 полно, swing)
PRESETS = [
    dict(bpm=104, drums=2, prog=[(45, [57, 60, 64]), (41, [57, 60, 65]), (48, [55, 60, 64]), (43, [55, 59, 62])], arp=[0, 1, 2, 1, 2, 1, 2, 1], pad=0.9, tone=2400),   # A F C G — «драйв»
    dict(bpm=118, drums=2, prog=[(38, [53, 57, 62]), (34, [53, 58, 62]), (41, [53, 57, 60]), (36, [55, 60, 64])], arp=[0, 2, 1, 2, 0, 2, 1, 2], pad=0.8, tone=3000),   # Dm Bb F C — бодро
    dict(bpm=76, drums=0, prog=[(40, [52, 55, 59]), (36, [52, 55, 60]), (43, [55, 59, 62]), (38, [54, 57, 62])], arp=[0, 1, 2, 1], pad=1.1, tone=1800),               # Em C G D — спокойно
    dict(bpm=110, drums=2, prog=[(45, [57, 60, 64]), (43, [55, 59, 62]), (41, [53, 57, 60]), (40, [52, 56, 59])], arp=[0, 1, 2, 1, 0, 1, 2, 1], pad=0.85, tone=2200),   # Am G F E — тёмная
    dict(bpm=88, drums=1, prog=[(36, [55, 60, 64]), (45, [57, 60, 64]), (41, [53, 57, 60]), (43, [55, 59, 62])], arp=[0, 1, 2, 1, 2, 1], pad=1.0, tone=2000),            # C Am F G — мягко
]


def _f(m):
    return 440.0 * 2 ** ((np.asarray(m, float) - 69) / 12)


def _env(n, a, r, sr=SR):
    e = np.ones(n)
    na, nr = min(int(a * sr), n), min(int(r * sr), n)
    if na:
        e[:na] = np.linspace(0, 1, na) ** 1.5
    if nr:
        e[-nr:] *= np.linspace(1, 0, nr) ** 1.5
    return e


def _lp(x, fc, order=4):
    return signal.sosfilt(signal.butter(order, fc, "low", fs=SR, output="sos"), x)


def _hp(x, fc, order=2):
    return signal.sosfilt(signal.butter(order, fc, "high", fs=SR, output="sos"), x)


def _bp(x, lo, hi, order=2):
    return signal.sosfilt(signal.butter(order, [lo, hi], "band", fs=SR, output="sos"), x)


def _add(buf, start, x, gain=1.0):
    i = int(start * SR)
    if i >= len(buf):
        return
    m = min(len(x), len(buf) - i)
    buf[i:i + m] += x[:m] * gain


def _pad(freqs, dur, tone):
    n = int(dur * SR)
    t = np.arange(n) / SR
    x = np.zeros(n)
    for f in freqs:
        for cents in (-9, 0, 8):
            ff = f * 2 ** (cents / 1200)
            x += signal.sawtooth(2 * np.pi * ff * t + (cents + 9) * 0.37) * 0.5 + np.sin(2 * np.pi * ff * t) * 0.5
    x = _lp(x / (len(freqs) * 3), tone * 0.55)
    return x * _env(n, 0.45, 0.6) * (0.85 + 0.15 * np.sin(2 * np.pi * t * 0.25))


def _bass(f, dur):
    n = int(dur * SR)
    t = np.arange(n) / SR
    x = np.sin(2 * np.pi * f * t) + 0.25 * np.sin(2 * np.pi * f * 2 * t) + 0.12 * signal.sawtooth(2 * np.pi * f * t)
    return _lp(x, 420) * _env(n, 0.008, 0.12) * np.exp(-t * 1.6)


def _keys(f, dur=0.9):
    """электропиано/колокольчик: сумма гармоник с разным затуханием"""
    n = int(dur * SR)
    t = np.arange(n) / SR
    x = np.zeros(n)
    for k, (a, d) in enumerate([(1.0, 3.2), (0.5, 5.0), (0.28, 6.5), (0.14, 9.0), (0.08, 12.0)], start=1):
        x += a * np.sin(2 * np.pi * f * k * t * (1 + 0.0004 * k)) * np.exp(-t * d)
    x += 0.35 * np.sin(2 * np.pi * f * 4.01 * t) * np.exp(-t * 30)           # «молоточек»
    return x * _env(n, 0.003, 0.05)


def _kick():
    n = int(0.42 * SR)
    t = np.arange(n) / SR
    x = np.sin(2 * np.pi * (46 + 95 * np.exp(-t * 26)) * t) * np.exp(-t * 7.5)
    click = _hp(np.random.default_rng(1).standard_normal(n), 2500) * np.exp(-t * 120) * 0.18
    return x + click


def _snare(rng):
    n = int(0.26 * SR)
    t = np.arange(n) / SR
    noise = _bp(rng.standard_normal(n), 1300, 7500) * np.exp(-t * 20)
    tone = np.sin(2 * np.pi * 185 * t) * np.exp(-t * 28) * 0.5
    return noise * 0.6 + tone


def _hat(rng, open_=False):
    n = int((0.16 if open_ else 0.045) * SR)
    t = np.arange(n) / SR
    return _hp(rng.standard_normal(n), 7000) * np.exp(-t * (22 if open_ else 95))


def _reverb(x, seconds=1.3, decay=0.42, seed=5):
    rng = np.random.default_rng(seed)
    n = int(seconds * SR)
    t = np.arange(n) / SR
    ir = _lp(rng.standard_normal(n), 5200) * np.exp(-t / decay)
    ir[: int(0.012 * SR)] *= np.linspace(0, 1, int(0.012 * SR))
    ir /= np.sqrt((ir ** 2).sum()) + 1e-9
    return signal.fftconvolve(x, ir)[: len(x)]


def compose_track(dur, preset=0):
    """-> (float32 моно в [-1,1], список времён ударов)"""
    p = PRESETS[preset % len(PRESETS)]
    rng = np.random.default_rng(100 + preset)
    n = int((dur + 1.0) * SR)
    beat = 60.0 / p["bpm"]
    bar = beat * 4
    nbars = int((dur + 1.0) / bar) + 2
    pad_l, keys_l, bass_l, drum_l = np.zeros(n), np.zeros(n), np.zeros(n), np.zeros(n)
    kicks = []
    for b in range(nbars):
        root, notes = p["prog"][b % len(p["prog"])]
        t0 = b * bar
        _add(pad_l, t0, _pad(_f(notes), bar + 0.7, p["tone"]), 0.9 * p["pad"])
        arp = p["arp"]
        for s in range(8):                                   # восьмые: арпеджио в верхней октаве
            nt = notes[arp[s % len(arp)] % len(notes)] + 12
            vel = 0.8 if s % 2 == 0 else 0.5
            _add(keys_l, t0 + s * beat / 2, _keys(_f(nt)), 0.30 * vel)
        for q, gain in ((0, 1.0), (2, 0.85), (2.5, 0.6)):    # бас: 1, 3, «и» третьей доли
            _add(bass_l, t0 + q * beat, _bass(_f(root), beat * 1.6), 0.55 * gain)
        if p["drums"] and b >= 2:                            # ударные заходят с третьего такта
            for q in range(4):
                if p["drums"] == 2 or q % 2 == 0:
                    _add(drum_l, t0 + q * beat, _kick(), 0.8 if p["drums"] == 2 else 0.5)
                    kicks.append(t0 + q * beat)
            for q in (1, 3):
                _add(drum_l, t0 + q * beat, _snare(rng), 0.30 if p["drums"] == 2 else 0.18)
            for s in range(8):
                _add(drum_l, t0 + s * beat / 2, _hat(rng, open_=(s == 7)), 0.06 if s % 2 else 0.04)
    wet = _reverb(pad_l * 0.7 + keys_l)
    mix = pad_l * 0.95 + keys_l * 0.9 + wet * 0.55 + bass_l * 0.8 + drum_l
    mix = _hp(mix, 35, 2)
    mix = _lp(mix, 12000, 4)
    mix = mix[: int(dur * SR)]
    mix = np.tanh(mix * 1.15) / np.tanh(1.15)               # мягкое сглаживание пиков
    mix /= (np.percentile(np.abs(mix), 99.5) + 1e-9)
    mix *= 0.82
    k = int(0.4 * SR)
    mix[:k] *= np.linspace(0, 1, k)
    f = int(min(1.6, dur / 4) * SR)
    mix[-f:] *= np.linspace(1, 0, f) ** 1.5
    return mix.astype(np.float32), kicks if kicks else [i * beat for i in range(int(dur / beat))]


if __name__ == "__main__":
    import sys, wave
    pre = int(sys.argv[1]) if len(sys.argv) > 1 else 0
    d = float(sys.argv[2]) if len(sys.argv) > 2 else 24
    x, _ = compose_track(d, pre)
    with wave.open(sys.argv[3] if len(sys.argv) > 3 else "music_test.wav", "wb") as w:
        w.setnchannels(1); w.setsampwidth(2); w.setframerate(SR)
        w.writeframes((np.clip(x, -1, 1) * 32767).astype("<i2").tobytes())
    print("ok", len(x) / SR)

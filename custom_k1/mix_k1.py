#!/usr/bin/env python3
"""K1 audio for [A,B] of the ORIGINAL clip. Voice untouched in time (one global gain from loudnorm only).
Music (lo-fi hip-hop, one 128 s file played once from 0: no loop, no seam) ~11 dB under the voice RMS in speech, ~6 dB under in hook / card transitions.
SFX peak = voice peak - 8..12 dB. Final: 2-pass loudnorm -14 LUFS, TP <= -1.5 dBTP.
usage: mix_k1.py SOURCE.mp4 ASSETS_DIR A B OUT.m4a  -> prints an evidence report"""
import json, re, subprocess, sys, tempfile
from pathlib import Path
import numpy as np
sys.path.insert(0, str(Path(__file__).resolve().parent))
import plan_k1 as P

src, assets, A, B, out = sys.argv[1], Path(sys.argv[2]), float(sys.argv[3]), float(sys.argv[4]), sys.argv[5]
DUR = B - A
SR = 48000
MUSIC_UNDER, BOOST, SFX_UNDER, FR = 11.0, 5.0, 10.0, 0.1


def load(path, pre=()):
    raw = subprocess.run(['ffmpeg', '-v', 'error', *pre, '-i', str(path), '-vn', '-ac', '2', '-ar', str(SR), '-f', 'f32le', '-'], capture_output=True, check=True).stdout
    return np.frombuffer(raw, dtype=np.float32).reshape(-1, 2).astype(np.float64)


def fit(x, n):
    return x[:n] if len(x) >= n else np.vstack([x, np.zeros((n - len(x), 2))])


def db(p):
    return 10 * np.log10(np.maximum(p, 1e-12))


def frames_db(x):
    k = int(FR * SR); m = len(x) // k
    return db((x[:m * k] ** 2).reshape(m, k, 2).mean(axis=(1, 2)))


def avg(a, mask):
    return float(db((10 ** (a[mask] / 10)).mean())) if mask.any() else float('nan')


def lufs(path):
    r = subprocess.run(['ffmpeg', '-hide_banner', '-i', str(path), '-af', 'ebur128=peak=true', '-f', 'null', '-'], capture_output=True, text=True)
    I = re.findall(r'I:\s+(-?[\d.]+) LUFS', r.stderr); tp = re.findall(r'Peak:\s+(-?[\d.]+) dBFS', r.stderr)
    return float(I[-1]), float(tp[-1])


n = int(DUR * SR)
voice = fit(load(src, ['-ss', str(A), '-t', str(DUR)]), n)
vpk = 20 * np.log10(np.abs(voice).max())
vf = frames_db(voice); nf = len(vf)
tf = (np.arange(nf) + 0.5) * FR
speech = np.convolve((vf > -40).astype(float), np.ones(3), 'same') > 0
vlev = float(db((10 ** (vf[vf > -40] / 10)).mean()))
gap = vf < (vlev - 20.0)

ev = [(t - A, f, ov) for t, f, ov in P.audio_events() if A - 0.3 <= t <= B]
ev = [(t, f, ov) for t, f, ov in ev if t >= 0]

# ---- music ----
music = fit(load(assets / 'music' / 'music_lofi_hiphop.ogg', ['-ss', str(A)]), n)
fi, fo = int(0.4 * SR), int(2.5 * SR)
env = np.ones(n)
if A <= 0.01: env[:fi] = np.linspace(0, 1, fi)
if B >= P.DUR - 0.05: env[-fo:] = np.linspace(1, 0, fo)
music = music * env[:, None]
boost_win = [(0.0 - A, P.HOOK_T1 - A + 0.2)]
for c in P.INSERTS:
    boost_win += [(c['t'] - A - 0.3, c['t'] - A + 0.45), (c['e'] - A - 0.45, c['e'] - A + 0.3)]
isboost = np.zeros(nf, bool)
for a_, b_ in boost_win: isboost |= (tf >= a_) & (tf <= b_)
calib = speech & ~isboost & (tf < DUR - 3.0)
v_cal = avg(vf, calib)
G = (v_cal - MUSIC_UNDER) - avg(frames_db(music), calib)
hookm = np.zeros(nf, bool)
hookm |= (tf <= P.HOOK_T1 - A + 0.2) & (tf >= 0)
mg = frames_db(music) + G
curve = np.where(isboost, BOOST, 0.0)
if hookm.any() and A <= 0.01:
    curve[hookm] = (avg(vf, hookm) - 6.0) - avg(mg, hookm)       # hook: music lands about 6 dB under the voice
curve = np.convolve(np.pad(curve, 3, mode='edge'), np.ones(5) / 5, 'valid')[:nf]
music = music * (10 ** ((G + np.interp(np.arange(n) / SR, tf, curve)) / 20))[:, None]

# ---- sfx ----
sfx = np.zeros((n, 2)); rows = []
for t, f, ov in ev:
    x = load(assets / 'sfx' / f'{f}.wav')[: int(1.6 * SR)]
    k = min(len(x), int(0.08 * SR)); x[-k:] *= np.linspace(1, 0, k)[:, None]
    tgt = vpk + (ov if ov is not None else -SFX_UNDER)
    x = x * (10 ** (tgt / 20) / np.abs(x).max())
    s0 = int(t * SR); seg = x[:max(0, n - s0)]
    sfx[s0:s0 + len(seg)] += seg
    rows.append((round(float(t + A), 2), f, round(float(tgt - vpk), 1)))

mix = voice + music + sfx
tmp = Path(tempfile.mkdtemp()); pre = tmp / 'pre.f32'; mix.astype(np.float32).tofile(pre)
wav = tmp / 'pre.wav'
subprocess.run(['ffmpeg', '-y', '-loglevel', 'error', '-f', 'f32le', '-ar', str(SR), '-ac', '2', '-i', str(pre), str(wav)], check=True)
r = subprocess.run(['ffmpeg', '-hide_banner', '-i', str(wav), '-af', 'loudnorm=I=-14:TP=-1.5:LRA=11:print_format=json', '-f', 'null', '-'], capture_output=True, text=True)
j = json.loads(r.stderr[r.stderr.rfind('{'):r.stderr.rfind('}') + 1])
ln = (f"loudnorm=I=-14:TP=-1.5:LRA=11:measured_I={j['input_i']}:measured_TP={j['input_tp']}:measured_LRA={j['input_lra']}:measured_thresh={j['input_thresh']}:offset={j['target_offset']}:linear=true")
subprocess.run(['ffmpeg', '-y', '-loglevel', 'error', '-i', str(wav), '-af', ln + ',aresample=48000', '-c:a', 'aac', '-b:a', '192k', out], check=True)
fI, fTP = lufs(out)
norm_db = fI - float(j['input_i'])
mfin, sfin = frames_db(music), frames_db(sfx)
sp = speech & ~isboost
bh = isboost & (tf <= P.HOOK_T1 - A + 0.2)
bt = isboost & ~bh
thr = vpk - 38
onsets = int(((sfin > thr) & ~np.concatenate([[False], sfin[:-1] > thr])).sum())
print('EVIDENCE (relative levels exact; absolute values include final normalisation gain %+.1f dB)' % norm_db)
print(f'voice: peak {vpk + norm_db:.1f} dBFS, RMS in speech {avg(vf, sp) + norm_db:.1f} dB')
print(f'music in SPEECH: {avg(mfin, sp) - avg(vf, sp):+.1f} dB vs voice RMS (target -10..-12) [{int(sp.sum())} frames]')
print(f'music in HOOK: {avg(mfin, bh) - avg(vf, bh):+.1f} dB vs voice RMS [{int(bh.sum())} frames]')
print(f'music in CARD TRANSITIONS: {avg(mfin, bt) - avg(vf, bt):+.1f} dB vs voice RMS (target about -6) [{int(bt.sum())} frames]')
print(f'music in PAUSES: RMS {avg(mfin, gap) + norm_db:.1f} dBFS; voice floor {avg(vf, gap) + norm_db:.1f} dBFS [{gap.sum() * FR:.1f} s]')
print(f'music file is {127.9:.1f} s, played once from {A:.1f} s: covers the whole {DUR:.1f} s with no loop and no seam')
print(f'sfx: {len(rows)} cues, {onsets} audible onsets; peaks {min(r[2] for r in rows):.1f}..{max(r[2] for r in rows):.1f} dB vs voice peak (target -8..-12)')
print('sfx table (t, sample, dB vs voice peak):', rows)
print(f'final mix: integrated {fI} LUFS, true peak {fTP} dBTP')

#!/usr/bin/env python3
"""Round 3 audio for time range [A,B] of the ORIGINAL clip. Voice untouched in time (one global gain only, from loudnorm).
Music bed is CALIBRATED by measurement: ~11 dB under the voice RMS in speech, +5 dB (about 6 dB under) during the hook and transitions.
SFX peak = voice peak - 10 dB (horse neigh - 8 dB). Final: 2-pass loudnorm -14 LUFS, TP <= -1.5.
usage: mix2.py SOURCE.mp4 ASSETS_DIR A B OUT.m4a   -> prints an evidence report"""
import json, re, subprocess, sys, tempfile
from pathlib import Path
import numpy as np
sys.path.insert(0, str(Path(__file__).resolve().parent))
from build2 import INSERTS, CALLOUTS, HOOK, TRANS, HOOK_T0, HOOK_T1

src, assets, A, B, out = sys.argv[1], Path(sys.argv[2]), float(sys.argv[3]), float(sys.argv[4]), sys.argv[5]
DUR = B - A
SR = 48000
MUSIC_UNDER = 11.0   # dB under the voice (RMS, speech frames)
BOOST = 6.0          # dB raise in hook / transitions  -> about 6 dB under
SFX_UNDER = 10.0     # dB under the voice peak
TMAP = {'sweep': 'whoosh_swish_light', 'flare': 'shimmer_up', 'push': 'whoosh_short'}
EXTRA = {'boom_soft': -2, 'boom_low': -2, 'coin': -2, 'ding_chime': -2, 'ding_glass': -2, 'shimmer_up': -2, 'horse_neigh': 2}
FR = 0.1  # analysis frame, s


def load(path, pre=()):
    raw = subprocess.run(['ffmpeg', '-v', 'error', *pre, '-i', str(path), '-vn', '-ac', '2', '-ar', str(SR), '-f', 'f32le', '-'], capture_output=True, check=True).stdout
    return np.frombuffer(raw, dtype=np.float32).reshape(-1, 2).astype(np.float64)


def fit(x, n):
    return x[:n] if len(x) >= n else np.vstack([x, np.zeros((n - len(x), 2))])


def db(p):
    return 10 * np.log10(np.maximum(p, 1e-12))


def frames_db(x):  # per-100ms power (dB), mean of channels
    k = int(FR * SR); m = len(x) // k
    return db((x[:m * k] ** 2).reshape(m, k, 2).mean(axis=(1, 2)))


def avg(a, mask):  # power-average of dB frames
    return float(db((10 ** (a[mask] / 10)).mean())) if mask.any() else float('nan')


def lufs(path):
    r = subprocess.run(['ffmpeg', '-hide_banner', '-i', str(path), '-af', 'ebur128=peak=true', '-f', 'null', '-'], capture_output=True, text=True)
    I = re.findall(r'I:\s+(-?[\d.]+) LUFS', r.stderr); tp = re.findall(r'Peak:\s+(-?[\d.]+) dBFS', r.stderr)
    return float(I[-1]), float(tp[-1])


n = int(DUR * SR)
voice = fit(load(src, ['-ss', str(A), '-t', str(DUR)]), n)
vpk = 20 * np.log10(np.abs(voice).max())
vf = frames_db(voice)
nf = len(vf)
tf = (np.arange(nf) + 0.5) * FR                 # frame centres, s (range-local)
speech = np.convolve((vf > -40).astype(float), np.ones(3), 'same') > 0
gap = vf < (float(db((10 ** (vf[vf > -40] / 10)).mean())) - 20.0)   # pause = 20 dB below the speech level (the clip has no true silence)
g2 = np.zeros(nf, bool); i = 0
while i < nf:           
    if gap[i]:
        j = i
        while j < nf and gap[j]: j += 1
        if j - i >= 2: g2[i:j] = True
        i = j
    else:
        i += 1
gap = g2

# ---- events (range-local seconds): (t, sample, dB-vs-voice-peak override or None) ----
ev = []
for h, nm in zip(HOOK, ('hit_1', 'hit_2', 'hit_3')):
    if A <= HOOK_T0: ev.append((h['t'], nm, -SFX_UNDER + 2))          # rising-pitch impacts, ~8 dB under the voice peak
cut_in_names = ['whoosh_medium2', 'whoosh_long', 'whoosh_medium']   # rotate
ci = 0
card_t = {c['n']: c['t'] for c in INSERTS if c['kind'] == 'card'}
for t in TRANS:
    if t.get('cut'):
        if abs(t['t'] - card_t[t['cut']]) < 1e-6:
            ev.append((t['t'] - 0.2, cut_in_names[ci % 3], None)); ci += 1
        else:
            ev.append((t['t'] - 0.2, 'whoosh_short', None))
    else:
        ev.append((t['t'] - 0.22, TMAP[t['type']], None))
for c in INSERTS:
    for (st, nm, ov) in c['sfx']: ev.append((st, nm, ov))
for c in CALLOUTS:
    for (st, nm, ov) in c['sfx']: ev.append((st, nm, ov))
ev = sorted((t - A, f, ov) for t, f, ov in ev if A - 0.3 <= t <= B)
ev = [(t, f, ov) for t, f, ov in ev if t >= 0]
ALT = {'pop_1': 'click_soft_1', 'pop_bubble': 'click_soft_2', 'click_soft_1': 'pop_1', 'click_soft_2': 'pop_bubble', 'ding_chime': 'ding_glass',
       'whoosh_short': 'whoosh_swish_light', 'whoosh_medium': 'whoosh_medium2', 'whoosh_medium2': 'whoosh_long', 'whoosh_long': 'whoosh_medium'}
for i in range(1, len(ev)):
    if ev[i][1] == ev[i - 1][1] and not ev[i][1].startswith(('hit_', 'boom')): ev[i] = (ev[i][0], ALT.get(ev[i][1], ev[i][1]), ev[i][2])

# ---- music, calibrated ----
mfile = next((assets / 'music').glob('music_*.*'))
mraw = load(mfile)
BAR = int(240 / 140 * SR)             # 1 bar at 140 BPM: crossfading exactly one bar keeps the beat grid aligned
def loop_xfade(x, need):
    out = x.copy(); seams = []
    while len(out) < need + SR:
        ov = BAR
        fo_, fi_ = np.cos(np.linspace(0, np.pi / 2, ov))[:, None], np.sin(np.linspace(0, np.pi / 2, ov))[:, None]
        seams.append(len(out) - ov)
        out = np.vstack([out[:-ov], out[-ov:] * fo_ + x[:ov] * fi_, x[ov:]])
    return out, seams
music, seams = loop_xfade(mraw, n)
music = fit(music, n)
fi, fo = int(0.4 * SR), int(2.5 * SR)
env = np.ones(n); env[:fi] = np.linspace(0, 1, fi); env[-fo:] = np.linspace(1, 0, fo)
music = music * env[:, None]
boost_win = [(0.0, HOOK_T1 - A + 0.2)] if A <= HOOK_T0 else []
for c in INSERTS:
    if c['kind'] == 'stop' and A - 0.5 < c['t'] < B + 0.5: boost_win.append((c['t'] - A - 0.3, c['t'] - A + 0.6))
hook_end = HOOK_T1 - A + 0.2
for t in TRANS:
    if A - 0.5 < t['t'] < B + 0.5: boost_win.append((t['t'] - A - 0.45, t['t'] - A + 0.45))
isboost = np.zeros(nf, bool)
for a_, b_ in boost_win: isboost |= (tf >= a_) & (tf <= b_)
calib = speech & ~isboost & (tf < DUR - 3.0)
v_cal = avg(vf, calib)
mf0 = frames_db(music)
G = (v_cal - MUSIC_UNDER) - avg(mf0, calib)
curve = np.where(isboost, BOOST, 0.0)
curve = np.convolve(np.pad(curve, 3, mode='edge'), np.ones(5) / 5, 'valid')[:nf]   # soften the ramps (~0.5 s)
gain_db = G + np.interp(np.arange(n) / SR, tf, curve)
music = music * (10 ** (gain_db / 20))[:, None]

# ---- sfx ----
sfx = np.zeros((n, 2)); rows = []
for t, f, ov in ev:
    x = load(assets / 'sfx' / f'{f}.wav')
    tgt = vpk + (ov if ov is not None else -SFX_UNDER + EXTRA.get(f, 0))
    x = x * (10 ** (tgt / 20) / np.abs(x).max())
    s0 = int(t * SR)
    seg = x[:max(0, n - s0)]
    sfx[s0:s0 + len(seg)] += seg
    rows.append((round(float(t + A), 2), f, round(float(tgt - vpk), 1)))

mix = voice + music + sfx
tmp = Path(tempfile.mkdtemp())
pre = tmp / 'pre.f32'
mix.astype(np.float32).tofile(pre)
wav = tmp / 'pre.wav'
subprocess.run(['ffmpeg', '-y', '-loglevel', 'error', '-f', 'f32le', '-ar', str(SR), '-ac', '2', '-i', str(pre), str(wav)], check=True)
r = subprocess.run(['ffmpeg', '-hide_banner', '-i', str(wav), '-af', 'loudnorm=I=-14:TP=-1.5:LRA=11:print_format=json', '-f', 'null', '-'], capture_output=True, text=True)
j = json.loads(r.stderr[r.stderr.rfind('{'):r.stderr.rfind('}') + 1])
ln = (f"loudnorm=I=-14:TP=-1.5:LRA=11:measured_I={j['input_i']}:measured_TP={j['input_tp']}:measured_LRA={j['input_lra']}:measured_thresh={j['input_thresh']}:offset={j['target_offset']}:linear=true")
subprocess.run(['ffmpeg', '-y', '-loglevel', 'error', '-i', str(wav), '-af', ln + ',aresample=48000', '-c:a', 'aac', '-b:a', '192k', out], check=True)
fI, fTP = lufs(out)
norm_db = fI - float(j['input_i'])    # gain applied by the final normalisation (same for every stem)

# ---- evidence ----
mfin, sfin = frames_db(music), frames_db(sfx)
sp = speech & ~isboost
bh = isboost & (tf <= hook_end) if A <= HOOK_T0 else np.zeros(nf, bool)
bt = isboost & ~bh
thr = vpk - 38
onsets = int(((sfin > thr) & ~np.concatenate([[False], sfin[:-1] > thr])).sum())
print('EVIDENCE (relative levels are exact; absolute values include the final normalisation gain %+.1f dB)' % norm_db)
print(f'voice: peak {vpk + norm_db:.1f} dBFS, RMS in speech {avg(vf, sp) + norm_db:.1f} dB')
print(f'music in SPEECH: {avg(mfin, sp) - avg(vf, sp):+.1f} dB vs voice RMS (target -10..-12) [{int(sp.sum())} frames]')
print(f'music in HOOK: {avg(mfin, bh) - avg(vf, bh):+.1f} dB vs voice RMS [{int(bh.sum())} frames]')
print(f'music in TRANSITIONS: {avg(mfin, bt) - avg(vf, bt):+.1f} dB vs voice RMS (target about -6) [{int(bt.sum())} frames]')
print(f'music in PAUSES (voice >=20 dB under speech level): RMS {avg(mfin, gap) + norm_db:.1f} dBFS absolute; voice floor there {avg(vf, gap) + norm_db:.1f} dBFS [{int(gap.sum())} frames = {gap.sum() * FR:.1f} s]')
print(f'sfx: {len(rows)} cues scheduled, {onsets} audible onsets detected (frame power above voice-peak-38 dB); peaks {min(r[2] for r in rows):.1f}..{max(r[2] for r in rows):.1f} dB vs voice peak (target -8..-12)')
print('sfx table (t, sample, dB vs voice peak):', rows)
if seams:
    for sm in seams:
        if sm < n - SR:
            w = int(0.5 * SR); pre_, post_ = music[max(0, sm - w):sm], music[sm + BAR:sm + BAR + w]
            if len(pre_) and len(post_):
                print(f'music loop seam at {sm / SR:.1f}s (1-bar crossfade): RMS before {db((pre_ ** 2).mean()):.1f} dB, after {db((post_ ** 2).mean()):.1f} dB, difference {abs(db((pre_ ** 2).mean()) - db((post_ ** 2).mean())):.1f} dB')
print(f'final mix: integrated {fI} LUFS, true peak {fTP} dBTP')

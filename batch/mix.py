#!/usr/bin/env python3
"""Batch audio for the WHOLE clip. Voice untouched in time (one global gain from loudnorm only).
Music ~11 dB under the voice RMS in speech (~6 dB around card transitions / hook), SFX peak = voice peak - 10 dB (or the cue's own offset),
final 2-pass loudnorm -14 LUFS, TP <= -1.5 dBTP. Writes an evidence report + levels.json.
usage: mix.py SOURCE.mp4 PLAN.json ANALYSIS.json OUT.m4a [--assets DIR] [--levels levels.json]"""
import argparse, json, random, re, subprocess, sys, tempfile
from pathlib import Path
import numpy as np

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from presets import PRESETS
from plan import HOOK_POPS
import lib

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
    k = int(FR * SR)
    m = len(x) // k
    return db((x[:m * k] ** 2).reshape(m, k, 2).mean(axis=(1, 2)))


def avg(a, mask):
    return float(db((10 ** (a[mask] / 10)).mean())) if mask.any() else float('nan')


def lufs(path):
    r = subprocess.run(['ffmpeg', '-hide_banner', '-i', str(path), '-af', 'ebur128=peak=true', '-f', 'null', '-'], capture_output=True, text=True)
    I = re.findall(r'I:\s+(-?[\d.]+) LUFS', r.stderr)
    tp = re.findall(r'Peak:\s+(-?[\d.]+) dBFS', r.stderr)
    return float(I[-1]), float(tp[-1])


def loop_music(x, n):
    """one file played once if long enough, else tiled with 1.5 s crossfades (no seam click)"""
    if len(x) >= n:
        return x[:n]
    cf = int(1.5 * SR)
    out = x.copy()
    while len(out) < n:
        fade = np.linspace(0, 1, cf)[:, None]
        out = np.vstack([out[:-cf], out[-cf:] * (1 - fade) + x[:cf] * fade, x[cf:]])
    return out[:n]


def spread(names, t, e):
    """place a kind's cue list over [t,e]: first on t, 'card_out'-like last on e-0.25; tick* expands to a counter run"""
    ev = []
    n = len(names)
    for i, (name, ov) in enumerate(names):
        if name.startswith('tick'):
            for k in range(8):
                ev.append((t + 0.2 + 0.09 * k, name, ov))
            continue
        if name in ('card_out',):
            ev.append((max(t, e - 0.25), name, ov))
        elif i == 0:
            ev.append((t, name, ov))
        else:
            ev.append((t + (e - t - 0.4) * i / max(1, n - 1), name, ov))
    return ev


def events(plan, an, pr):
    W = an['words']
    wc = plan['wildcard']
    shift = 0.45 if wc['type'] == 'blackout_open' else 0.0
    ev = []
    for i, line in enumerate(lib.hook_lines(plan)):
        ev.append((HOOK_POPS[i] + shift, pr['hook_sfx'][i], None))
    for c in plan['inserts']:
        sf = pr['sfx_for'].get(c['kind'], [])
        if c['kind'] == 'stock':
            ev += [(c['t'] - 1.0, sf[0][0], -13), (c['t'], sf[-2][0] if len(sf) > 1 else sf[0][0], None), (c['e'] - 0.05, sf[-1][0], -13)] if len(sf) >= 3 else \
                  [(c['t'] - 0.3, sf[0][0], -12), (c['t'], sf[-1][0], None)]
        else:
            ev += spread(sf, c['t'], c['e'])
    t, e, ty = wc['t'], wc['e'], wc['type']
    if ty == 'blackout_open':
        ev += [(0.0, 'sub_drop', None), (e, 'impact_deep', None)]
    elif ty == 'silence_gag':
        ev += [(t, 'impact_deep', None)]
    elif ty == 'negative_flash':
        ev += [(t, 'metal_hit', None)]
    elif ty == 'letterbox':
        ev += [(t, 'whoosh_long', -12), (e - 0.25, 'whoosh_short', -13)]
    elif ty == 'echo_caption':
        ev += [(t, 'boom_low', None)] + [(t + 0.18 * k, 'tick_a', -11) for k in range(1, 4)]
    elif ty == 'sound_gag':
        ev += [(t, wc.get('sample') or 'impact_deep', -9)]
    elif ty == 'metaphor_stock':
        ev += [(t - 1.0, 'riser', -13), (t, 'impact_deep', None), (e - 0.05, 'whip', -13)]
    elif ty == 'split_black':
        ev += [(t - 0.02, 'sub_drop', None), (t + 0.9, 'impact_deep', None)]
    elif ty == 'timer':
        ev += [(t, 'card_in', None)] + [(t + 0.5 + k, 'tick_a', -11) for k in range(int(max(1, e - t - 0.5)))] + [(e - 0.1, 'ding_chime', -11)]
    elif ty == 'punch_cut':
        ev += [(t, 'whip', -9), (e, 'whip', -13)]
    if plan.get('big') is not None:
        ev.append((W[plan['big']]['s'] + 0.04, pr['final_sfx'], None))
    return sorted(ev)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('src')
    ap.add_argument('plan')
    ap.add_argument('analysis')
    ap.add_argument('out')
    ap.add_argument('--assets', default=str(HERE / 'assets'))
    ap.add_argument('--levels', default='levels.json')
    a = ap.parse_args()
    plan = json.loads(Path(a.plan).read_text(encoding='utf-8'))
    an = json.loads(Path(a.analysis).read_text(encoding='utf-8'))
    pr = PRESETS[plan['preset']]
    assets = Path(a.assets)
    DUR = an['dur']
    n = int(DUR * SR)
    voice = fit(load(a.src, ['-t', str(DUR)]), n)
    vpk = 20 * np.log10(max(1e-6, np.abs(voice).max()))
    vf = frames_db(voice)
    nf = len(vf)
    tf = (np.arange(nf) + 0.5) * FR
    speech = np.convolve((vf > -40).astype(float), np.ones(3), 'same') > 0
    vlev = float(db((10 ** (vf[vf > -40] / 10)).mean())) if (vf > -40).any() else -30.0
    gap = vf < (vlev - 20.0)

    ev = [(t, f, ov) for t, f, ov in events(plan, an, pr) if 0 <= t < DUR - 0.05 and (assets / 'sfx' / f'{f}.wav').exists()]
    wc = plan['wildcard']
    sil = None
    if wc['type'] == 'silence_gag':
        sil = (max(0.0, wc['t'] - 0.7), wc['t'] + 0.05)
        ev = [(t, f, ov) for t, f, ov in ev if not (sil[0] - 0.01 <= t < wc['t'] - 0.01)]    # nothing else in the dead-silence window

    # ---- music ----
    rng = random.Random(plan['seed'])
    mname = (plan.get('style') or {}).get('music') or rng.choice(pr['music'])
    music = loop_music(load(assets / 'music' / mname), n)
    fi, fo = int(0.4 * SR), int(2.5 * SR)
    env = np.ones(n)
    env[:fi] = np.linspace(0, 1, fi)
    env[-fo:] = np.linspace(1, 0, fo)
    music = music * env[:, None]
    hook_end = max(2.7, wc['e'] + 0.2) if wc['type'] == 'blackout_open' else 2.7
    boost_win = [(0.0, hook_end + 0.2)]
    for c in plan['inserts']:
        boost_win += [(c['t'] - 0.3, c['t'] + 0.45), (c['e'] - 0.45, c['e'] + 0.3)]
    if wc['type'] == 'metaphor_stock':
        boost_win += [(wc['t'] - 0.3, wc['t'] + 0.45), (wc['e'] - 0.45, wc['e'] + 0.3)]
    isboost = np.zeros(nf, bool)
    for a_, b_ in boost_win:
        isboost |= (tf >= a_) & (tf <= b_)
    calib = speech & ~isboost & (tf < DUR - 3.0)
    if not calib.any():
        calib = speech
    v_cal = avg(vf, calib)
    G = (v_cal - MUSIC_UNDER) - avg(frames_db(music), calib)
    hookm = (tf <= hook_end + 0.2)
    mg = frames_db(music) + G
    curve = np.where(isboost, BOOST, 0.0)
    if hookm.any():
        curve[hookm] = (avg(vf, hookm) - 6.0) - avg(mg, hookm)
    for a_, b_ in boost_win[1:]:
        mw = (tf >= a_) & (tf <= b_) & ~hookm
        if mw.any():
            curve[mw] = (avg(vf, mw) - 3.8) - avg(mg, mw)
    curve = np.convolve(np.pad(curve, 3, mode='edge'), np.ones(5) / 5, 'valid')[:nf]
    music = music * (10 ** ((G + np.interp(np.arange(n) / SR, tf, curve)) / 20))[:, None]
    if sil:
        g = np.ones(n)
        s0, s1 = int(sil[0] * SR), int(sil[1] * SR)
        rf = int(0.05 * SR)
        g[s0:s1] = 0.0
        g[max(0, s0 - rf):s0] = np.linspace(1, 0, s0 - max(0, s0 - rf))
        music = music * g[:, None]

    # ---- sfx ----
    sfx = np.zeros((n, 2))
    rows = []
    for t, f, ov in ev:
        x = load(assets / 'sfx' / f'{f}.wav')[: int(1.6 * SR)]
        k = min(len(x), int(0.08 * SR))
        x[-k:] *= np.linspace(1, 0, k)[:, None]
        tgt = vpk + (min(-8.0, max(-12.0, ov)) if ov is not None else -SFX_UNDER)
        x = x * (10 ** (tgt / 20) / max(1e-9, np.abs(x).max()))
        s0 = int(t * SR)
        seg = x[:max(0, n - s0)]
        sfx[s0:s0 + len(seg)] += seg
        rows.append((round(float(t), 2), f, round(float(tgt - vpk), 1)))

    mix = voice + music + sfx
    tmp = Path(tempfile.mkdtemp())
    pre = tmp / 'pre.f32'
    mix.astype(np.float32).tofile(pre)
    wav = tmp / 'pre.wav'
    subprocess.run(['ffmpeg', '-y', '-loglevel', 'error', '-f', 'f32le', '-ar', str(SR), '-ac', '2', '-i', str(pre), str(wav)], check=True)
    r = subprocess.run(['ffmpeg', '-hide_banner', '-i', str(wav), '-af', 'loudnorm=I=-14:TP=-1.5:LRA=11:print_format=json', '-f', 'null', '-'], capture_output=True, text=True)
    j = json.loads(r.stderr[r.stderr.rfind('{'):r.stderr.rfind('}') + 1])
    ln = (f"loudnorm=I=-14:TP=-1.5:LRA=11:measured_I={j['input_i']}:measured_TP={j['input_tp']}:measured_LRA={j['input_lra']}:measured_thresh={j['input_thresh']}:offset={j['target_offset']}:linear=true")
    subprocess.run(['ffmpeg', '-y', '-loglevel', 'error', '-i', str(wav), '-af', ln + ',aresample=48000', '-c:a', 'aac', '-b:a', '192k', a.out], check=True)
    fI, fTP = lufs(a.out)
    norm_db = fI - float(j['input_i'])
    mfin, sfin = frames_db(music), frames_db(sfx)
    sp = speech & ~isboost
    bh = isboost & (tf <= hook_end + 0.2)
    bt = isboost & ~bh
    thr = vpk - 38
    onsets = int(((sfin > thr) & ~np.concatenate([[False], sfin[:-1] > thr])).sum())
    m_sp = avg(mfin, sp) - avg(vf, sp)
    peaks = [r_[2] for r_ in rows] or [0]
    lv = {'preset': pr['id'], 'music_file': mname, 'music_in_speech_db': round(m_sp, 1), 'music_in_hook_db': round(avg(mfin, bh) - avg(vf, bh), 1) if bh.any() else None,
          'music_in_transitions_db': round(avg(mfin, bt) - avg(vf, bt), 1) if bt.any() else None, 'sfx_cues': len(rows), 'sfx_audible_onsets': onsets,
          'sfx_peak_min_db': min(peaks), 'sfx_peak_max_db': max(peaks), 'lufs': fI, 'true_peak_db': fTP,
          'levels_ok': bool(-13.5 <= m_sp <= -8.5 and -15.5 <= fI <= -12.5 and fTP <= -1.0),
          'silence_window': sil}
    Path(a.levels).write_text(json.dumps(lv, indent=1), encoding='utf-8')
    print('EVIDENCE (relative levels exact; absolute values include final normalisation gain %+.1f dB)' % norm_db)
    print(f'music file {mname}; voice peak {vpk + norm_db:.1f} dBFS, RMS in speech {avg(vf, sp) + norm_db:.1f} dB')
    print(f'music in SPEECH: {m_sp:+.1f} dB vs voice RMS (target -10..-12) [{int(sp.sum())} frames]')
    print(f'music in HOOK: {lv["music_in_hook_db"]} dB; in CARD TRANSITIONS: {lv["music_in_transitions_db"]} dB (target about -6)')
    print(f'sfx: {len(rows)} cues, {onsets} audible onsets; peaks {min(peaks):.1f}..{max(peaks):.1f} dB vs voice peak (target -8..-12)')
    print('sfx table:', rows)
    print(f'final mix: integrated {fI} LUFS, true peak {fTP} dBTP; levels_ok={lv["levels_ok"]}')


if __name__ == '__main__':
    main()

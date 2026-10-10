#!/usr/bin/env python3
"""Round 2 audio for time range [a,b] of the ORIGINAL clip: voice untouched in time + deeply ducked soft music + very quiet SFX.
Every SFX is peak-normalised to (voice peak - SFX_BELOW dB). Final mix: 2-pass loudnorm to -14 LUFS, TP <= -1.5.
usage: mix2.py SOURCE.mp4 ASSETS_DIR A B OUT.m4a   (prints a level report)"""
import json, re, subprocess, sys, tempfile
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent))
from build2 import STK, TRANS, HOOK_T0

src, assets, A, B, out = sys.argv[1], Path(sys.argv[2]), float(sys.argv[3]), float(sys.argv[4]), sys.argv[5]
DUR = B - A
SFX_BELOW = 22.0     # dB under the voice peak
MUSIC_DB = 4.0     # bed level before ducking (relative to full scale), then sidechain ducks it further
TMAP = {'sweep': 'whoosh_swish_light', 'zoom': 'whoosh_medium', 'push': 'whoosh_short', 'flare': 'shimmer_up'}
SMAP = {'stopwatch': 'click_soft_2', 'magnify': 'pop_bubble', 'one': 'ping_notify', 'question': 'pop_1', 'bell': 'ding_chime',
        'price': 'coin', 'calendar': 'click_soft_1', 'clock': 'pop_bubble', 'check': 'ding_glass'}
EXTRA = {'boom_soft': -4, 'coin': -3, 'ding_chime': -3, 'ding_glass': -3, 'shimmer_up': -2}   # a few are naturally brighter/louder


def run(cmd):
    return subprocess.run(cmd, capture_output=True, text=True)


def peak_db(path, args=()):
    r = run(['ffmpeg', '-hide_banner', '-i', str(path), *args, '-af', 'volumedetect', '-f', 'null', '-'])
    m = re.search(r'max_volume:\s*(-?[\d.]+) dB', r.stderr)
    return float(m.group(1))


def lufs(path_or_filter_in, extra=()):
    r = run(['ffmpeg', '-hide_banner', '-i', str(path_or_filter_in), *extra, '-af', 'ebur128=peak=true', '-f', 'null', '-'])
    I = re.findall(r'I:\s+(-?[\d.]+) LUFS', r.stderr)
    tp = re.findall(r'Peak:\s+(-?[\d.]+) dBFS', r.stderr)
    return (float(I[-1]) if I else None), (float(tp[-1]) if tp else None)


ev = []  # (time in range, sample, extra dB)
if A <= HOOK_T0:
    ev.append((HOOK_T0 + 0.05, 'boom_soft'))
for t in TRANS:
    ev.append((t['t'] - 0.22, TMAP[t['type']]))
for s in STK:
    ev.append((s['t'] + 0.02, SMAP[s['type']]))
ev = sorted((t - A, f) for t, f in ev if A - 0.3 <= t <= B)
ev = [(t, f) for t, f in ev if t >= 0]
# never the same sample twice in a row
for i in range(1, len(ev)):
    if ev[i][1] == ev[i - 1][1]:
        alt = {'pop_1': 'click_soft_1', 'pop_bubble': 'click_soft_2', 'click_soft_1': 'pop_1', 'click_soft_2': 'pop_bubble', 'ding_chime': 'ding_glass'}
        ev[i] = (ev[i][0], alt.get(ev[i][1], ev[i][1]))

tmp = Path(tempfile.mkdtemp())
voice = tmp / 'voice.wav'
subprocess.run(['ffmpeg', '-y', '-loglevel', 'error', '-ss', str(A), '-t', str(DUR), '-i', src, '-vn', '-ac', '2', '-ar', '48000', str(voice)], check=True)
vpk = min(peak_db(voice), -1.0)
vI, vTP = lufs(voice)
music = next((assets / 'music').glob('music_*.*'))
cmd = ['ffmpeg', '-y', '-loglevel', 'error', '-i', str(voice), '-stream_loop', '-1', '-i', str(music)]
fc = ['[0:a]asplit=2[v][vk]',
      f'[1:a]aformat=sample_rates=48000:channel_layouts=stereo,atrim=0:{DUR},afade=t=in:d=1.5,afade=t=out:st={max(0, DUR-2.5)}:d=2.5,volume={MUSIC_DB}dB[m0]',
      '[m0][vk]sidechaincompress=threshold=0.04:ratio=5:attack=20:release=600:makeup=1[m]']
labs, gains = [], []
for i, (t, f) in enumerate(ev):
    p = assets / 'sfx' / f'{f}.wav'
    sp = peak_db(p)
    g = (vpk - SFX_BELOW + EXTRA.get(f, 0)) - sp
    gains.append((round(t, 2), f, round(sp + g, 1)))
    cmd += ['-i', str(p)]
    fc.append(f'[{i+2}:a]aformat=sample_rates=48000:channel_layouts=stereo,volume={g:.2f}dB,adelay={int(t*1000)}|{int(t*1000)}[s{i}]')
    labs.append(f'[s{i}]')
sfxbus = f'{"".join(labs)}amix=inputs={len(labs)}:normalize=0:duration=longest,atrim=0:{DUR}[sfx]' if labs else 'anullsrc=r=48000:cl=stereo[sfx]'
fc.append(sfxbus)
fc.append('[m]asplit=2[ma][mb]'); fc.append('[sfx]asplit=2[sa][sb]')
fc.append('[v][ma][sa]amix=inputs=3:normalize=0:duration=first,alimiter=limit=0.9[pre]')
pre = tmp / 'pre.wav'
stm, sts = tmp / 'm.wav', tmp / 's.wav'
subprocess.run(cmd + ['-filter_complex', ';'.join(fc), '-map', '[pre]', '-t', str(DUR), str(pre), '-map', '[mb]', '-t', str(DUR), str(stm), '-map', '[sb]', '-t', str(DUR), str(sts)], check=True)
# 2-pass loudnorm
r = run(['ffmpeg', '-hide_banner', '-i', str(pre), '-af', 'loudnorm=I=-14:TP=-1.5:LRA=11:print_format=json', '-f', 'null', '-'])
j = json.loads(r.stderr[r.stderr.rfind('{'):r.stderr.rfind('}') + 1])
ln = (f"loudnorm=I=-14:TP=-1.5:LRA=11:measured_I={j['input_i']}:measured_TP={j['input_tp']}:measured_LRA={j['input_lra']}:measured_thresh={j['input_thresh']}:offset={j['target_offset']}:linear=true")
subprocess.run(['ffmpeg', '-y', '-loglevel', 'error', '-i', str(pre), '-af', ln + ',aresample=48000', '-c:a', 'aac', '-b:a', '192k', out], check=True)
fI, fTP = lufs(out)
for name, st in (('music (ducked)', stm), ('sfx bus', sts)):
    mI, mTP = lufs(st)
    print(f'{name}: integrated {mI} LUFS (voice {vI}), peak {mTP} dBFS')
print(f'voice: peak {vpk} dBFS, integrated {vI} LUFS')
print(f'sfx ({len(ev)} cues): peaks {min(g[2] for g in gains)}..{max(g[2] for g in gains)} dBFS = {vpk - max(g[2] for g in gains):.1f} dB below voice peak (target >= 18)')
print('sfx list:', gains)
print(f'final mix: integrated {fI} LUFS, true peak {fTP} dBTP')

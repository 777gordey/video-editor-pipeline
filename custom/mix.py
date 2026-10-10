#!/usr/bin/env python3
"""Audio for the whole clip, mixed ONCE over the full timeline: original voice (untouched in time) + ducked music bed + SFX cues.
usage: mix.py ORIGINAL.mp4 ASSETS_DIR OUT.m4a"""
import subprocess, sys
from pathlib import Path

orig, assets, out = sys.argv[1], Path(sys.argv[2]), sys.argv[3]
DUR = 72.04
SFX = [  # (time s, file, gain dB) — no identical sample twice in a row
    (1.60, 'pop_1', -10), (3.05, 'whoosh_medium', -15), (3.34, 'boom_soft', -9), (4.20, 'whoosh_short', -10),
    (4.45, 'ping_notify', -13), (5.60, 'pop_bubble', -10), (9.30, 'whoosh_swish_light', -10), (11.30, 'whoosh_medium2', -16),
    (13.70, 'pop_1', -11), (13.82, 'shimmer_up', -17), (16.10, 'whoosh_long', -16), (18.00, 'click_soft_1', -12),
    (19.30, 'whoosh_swish_light', -13), (19.82, 'coin', -9), (19.90, 'boom_soft', -13), (23.10, 'whoosh_medium', -14),
    (24.20, 'click_soft_2', -12), (25.40, 'click_soft_1', -14), (27.55, 'whoosh_short', -14), (28.40, 'pop_bubble', -12),
    (28.60, 'pop_1', -13), (29.95, 'ding_glass', -15), (30.40, 'ding_chime', -17), (31.25, 'whoosh_medium2', -14),
    (32.20, 'shimmer_up', -12), (32.22, 'boom_soft', -14), (35.10, 'whoosh_long', -17), (36.60, 'whoosh_swish_light', -14),
    (37.76, 'pop_bubble', -13), (39.36, 'click_soft_1', -12), (39.90, 'ding_chime', -14), (41.55, 'whoosh_short', -12),
    (41.90, 'click_soft_2', -14), (43.18, 'boom_soft', -10), (44.20, 'whoosh_swish_light', -14), (47.90, 'whoosh_medium', -14),
    (48.30, 'boom_soft', -14), (50.20, 'click_soft_1', -10), (50.70, 'ding_glass', -13), (52.30, 'whoosh_swish_light', -12),
    (52.95, 'boom_low', -15), (53.10, 'ding_chime', -13), (55.20, 'whoosh_medium2', -14), (55.60, 'pop_1', -14),
    (57.85, 'whoosh_swish_light', -16), (57.95, 'whoosh_long', -15), (59.55, 'boom_soft', -10), (62.40, 'whoosh_short', -12),
    (63.30, 'whoosh_medium', -16), (63.75, 'boom_soft', -14), (64.75, 'whoosh_medium2', -16), (65.90, 'ding_chime', -10),
    (65.95, 'shimmer_up', -15), (67.80, 'whoosh_swish_light', -12), (68.20, 'riser_light', -17), (69.05, 'boom_low', -11),
    (69.75, 'shimmer_up', -14), (70.70, 'ding_glass', -16),
]
# typing ticks on the phone (S12), alternate two samples
for i in range(1, 14):
    SFX.append((56.95 + i * 0.075, 'click_soft_1' if i % 2 else 'click_soft_2', -22))
SFX.sort()

cmd = ['ffmpeg', '-y', '-loglevel', 'error', '-i', orig, '-stream_loop', '-1', '-i', str(next((assets / 'music').glob('music_lofi_chill_loop.*')))]
files = []
for t, f, g in SFX:
    cmd += ['-i', str(assets / 'sfx' / f'{f}.wav')]
    files.append((t, g))
fc = [f'[0:a]aformat=sample_rates=48000:channel_layouts=stereo,volume=1.0,asplit=2[v][vk]',
      f'[1:a]aformat=sample_rates=48000:channel_layouts=stereo,atrim=0:{DUR},afade=t=in:d=2,afade=t=out:st={DUR-2.5}:d=2.5,volume=-24dB[m0]',
      '[m0][vk]sidechaincompress=threshold=0.03:ratio=8:attack=20:release=400[m]']
labs = []
for i, (t, g) in enumerate(files):
    fc.append(f'[{i+2}:a]volume={g}dB,adelay={int(t*1000)}|{int(t*1000)}[s{i}]')
    labs.append(f'[s{i}]')
fc.append(f'[v][m]{"".join(labs)}amix=inputs={2+len(labs)}:normalize=0:duration=first,alimiter=limit=0.95,loudnorm=I=-14:TP=-1.5:LRA=9[o]')
cmd += ['-filter_complex', ';'.join(fc), '-map', '[o]', '-t', str(DUR), '-c:a', 'aac', '-b:a', '192k', out]
subprocess.run(cmd, check=True)
print('mixed', out, len(SFX), 'sfx cues')

#!/usr/bin/env python3
"""Layers for one time range of the clip (no cuts, no speed change): graded person at 1080x1920, RVM cut-out (with 1 s pre-roll so the
recurrent state is warm), multiply/screen pair (inv.mp4 / pb.mp4), raw range (orig.mp4, for the laptop card) and lap.json (frames with no person).
usage: PYTHONPATH=engine python custom/make_layers.py SOURCE.mp4 A B OUTDIR [--alpha ALPHA_FULL.mkv]"""
import json, subprocess, sys
from pathlib import Path
import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / 'engine'))
import matte as M  # noqa: E402  (engine/matte.py: RVM mobilenetv3 ONNX, CPU)

GRADE = 'eq=contrast=1.06:saturation=1.1:gamma=0.98,unsharp=5:5:0.45'


def ff(*a):
    a = [str(x) for x in a]
    print('+', ' '.join(a)[:300], flush=True)
    subprocess.run(['ffmpeg', '-y', '-loglevel', 'error', *a], check=True)


def main():
    src, A, B, out = sys.argv[1], float(sys.argv[2]), float(sys.argv[3]), Path(sys.argv[4])
    out.mkdir(parents=True, exist_ok=True)
    pre = min(1.0, A)
    d = B - A
    ff('-ss', f'{A:.3f}', '-i', src, '-t', f'{d:.3f}', '-an', '-c:v', 'libx264', '-preset', 'veryfast', '-crf', 14, '-r', 30, '-pix_fmt', 'yuv420p', out / 'orig.mp4')
    full = out / 'person_pre.mp4'
    ff('-ss', f'{A - pre:.3f}', '-i', src, '-t', f'{d + pre:.3f}', '-an', '-vf', f'scale=1080:1920:flags=lanczos,{GRADE}', '-c:v', 'libx264', '-preset', 'veryfast', '-crf', 12, '-r', 30, '-pix_fmt', 'yuv420p', full)
    alpha_pre = out / 'alpha_pre.mkv'
    if '--alpha' in sys.argv:   # reuse a full-clip alpha (local runs)
        ff('-ss', f'{A - pre:.3f}', '-i', sys.argv[sys.argv.index('--alpha') + 1], '-t', f'{d + pre:.3f}', '-c:v', 'ffv1', alpha_pre)
    else:
        M.matte(full, alpha_pre, out / 'rvm.onnx')
    alpha = out / 'alpha.mkv'
    ff('-ss', f'{pre:.3f}', '-i', alpha_pre, '-t', f'{d:.3f}', '-c:v', 'ffv1', alpha)
    person = out / 'person.mp4'
    ff('-ss', f'{pre:.3f}', '-i', full, '-t', f'{d:.3f}', '-c:v', 'libx264', '-preset', 'veryfast', '-crf', 12, '-r', 30, '-pix_fmt', 'yuv420p', person)
    # frames with (almost) no person: the laptop shot
    import cv2
    cap = cv2.VideoCapture(str(alpha)); means = []
    while True:
        ok, fr = cap.read()
        if not ok:
            break
        means.append(float(fr[:, :, 0].mean()) / 255.0)
    cap.release()
    empty = [i for i, m in enumerate(means) if m < 0.035]
    runs, cur = [], []
    for i in empty:
        if cur and i != cur[-1] + 1:
            runs.append(cur); cur = []
        cur.append(i)
    if cur:
        runs.append(cur)
    runs = [(A + r[0] / 30, A + (r[-1] + 1) / 30) for r in runs if len(r) >= 18]
    (out / 'lap.json').write_text(json.dumps({'runs': runs, 'means': [round(m, 3) for m in means[::6]]}))
    print('empty-alpha runs (global s):', runs, flush=True)
    if runs:   # specks of alpha during person-less moments (swing, laptop) would ghost: zero those frames
        en = '+'.join(f"between(t,{a - A:.3f},{b - A:.3f})" for a, b in runs)
        clean = out / 'alpha_clean.mkv'
        ff('-i', alpha, '-vf', f"drawbox=x=0:y=0:w=iw:h=ih:color=black:t=fill:enable='{en}'", '-c:v', 'ffv1', clean)
        clean.replace(alpha)
    M.build_layers(person, alpha, out / 'inv.mp4', out / 'pb.mp4')
    for f in ('person_pre.mp4', 'alpha_pre.mkv', 'person.mp4'):
        (out / f).unlink(missing_ok=True)


if __name__ == '__main__':
    main()

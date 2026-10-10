import json, sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent))
import build2 as b
K = [k for k in b.ZK_TEST]
print('CAMERA MOVES >= 10 % in 0-20 s (start s -> end s, scale from -> to, change):')
n = 0
for (t0, z0), (t1, z1) in zip(K, K[1:]):
    ch = z1 / z0 - 1
    if abs(ch) >= 0.10:
        n += 1
        hidden = any(c['t'] <= t0 + 0.01 and t1 <= c['e'] + 0.4 for c in b.CUTAWAYS)
        print(f"  {n}. {t0:.1f}-{t1:.1f}s  {z0:.2f} -> {z1:.2f}  ({ch*100:+.0f} %)  {'push-in' if ch>0 else 'pull-out'}{'  [under a cutaway card]' if hidden else ''}")
print('total visible-or-not moves:', n, '| max scale', max(z for _, z in K))
face = json.load(open(Path(__file__).resolve().parent / 'face_track.json'))
def zoom(t):
    for (t0, z0), (t1, z1) in zip(K, K[1:]):
        if t0 <= t <= t1:
            u = (t - t0) / (t1 - t0); u = u * u * (3 - 2 * u); return z0 + (z1 - z0) * u
    return K[-1][1]
print('FACE-BOX WIDTH ON SCREEN over time (px of 1080; no face detected = -):')
row = []
for r in face:
    if r['t'] <= 20 and abs(r['t'] * 10 % 20) < 1e-6 or (r['t'] <= 20 and round(r['t'] % 2.0, 2) in (0.0,)):
        z = zoom(r['t']); row.append(f"{r['t']:.0f}s z{z:.2f}:" + (f"{r['f'][2]*1080*z:.0f}px" if r['f'] else '-'))
print('  ' + '  '.join(row))

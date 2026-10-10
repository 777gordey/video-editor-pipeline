#!/usr/bin/env python3
"""Fetch the Pexels stock for the two full-frame inserts (never committed) and cut each to 1080x1920, 30 fps, silent, desaturated mp4.
usage: stock_k3.py OUTDIR [CACHEDIR] — public Pexels download link (Pexels licence: free for commercial use, no attribution); falls back to the API with PEXELS_API_KEY.
Prints only ids and sizes, never keys."""
import json, os, subprocess, sys, urllib.request
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent))
import plan_k3 as P

out = Path(sys.argv[1]); out.mkdir(parents=True, exist_ok=True)
cache = Path(sys.argv[2]) if len(sys.argv) > 2 else out / '_cache'; cache.mkdir(parents=True, exist_ok=True)
UA = {'User-Agent': 'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 Chrome/124 Safari/537.36'}


def get(url, dst, headers=None):
    req = urllib.request.Request(url, headers={**UA, **(headers or {})})
    with urllib.request.urlopen(req, timeout=180) as r, open(dst, 'wb') as f:
        while True:
            b = r.read(1 << 20)
            if not b: break
            f.write(b)


def probe(p):
    r = subprocess.run(['ffprobe', '-v', 'error', '-select_streams', 'v:0', '-show_entries', 'stream=width,height', '-of', 'csv=p=0', str(p)], capture_output=True, text=True)
    return [int(x) for x in r.stdout.strip().split(',')] if r.returncode == 0 and r.stdout.strip() else None


for c in [x for x in P.INSERTS if x['kind'] == 'stock']:
    src = cache / f"{c['src']}.mp4"
    if not (src.exists() and probe(src)):
        try:
            get(f"https://www.pexels.com/download/video/{c['src']}/", src)
        except Exception as e:
            print('public link failed for', c['src'], type(e).__name__)
        if not (src.exists() and probe(src)):
            key = os.environ.get('PEXELS_API_KEY'); assert key, f"cannot fetch {c['src']} and no PEXELS_API_KEY"
            tmp = cache / 'api.json'
            get(f"https://api.pexels.com/videos/videos/{c['src']}", tmp, {'Authorization': key})
            files = [f for f in json.load(open(tmp))['video_files'] if f.get('file_type') == 'video/mp4' and (f.get('width') or 0) <= 1920]
            files.sort(key=lambda f: -(f.get('width') or 0))
            get(files[0]['link'], src)
    w, h = probe(src)
    dur = round(c['e'] - c['t'] + 0.4, 3)
    cw = int(h * 9 / 16) if w > h else w
    x0 = int(min(max(0, c['crop'] * w - cw / 2), w - cw)) if w > h else 0
    vf = (f"crop={cw}:{h}:{x0}:0," if w > h else '') + f"scale=1080:1920:force_original_aspect_ratio=increase:flags=lanczos,crop=1080:1920,fps=30," \
         f"eq=saturation={c['sat']}:contrast=1.22:brightness=-0.05:gamma=0.92,colorbalance=bs=0.05:bm=0.03,format=yuv420p"
    subprocess.run(['ffmpeg', '-y', '-loglevel', 'error', '-ss', str(c['ss']), '-t', str(dur), '-i', str(src), '-vf', vf, '-an', '-c:v', 'libx264', '-crf', '14', '-preset', 'fast', str(out / f"stock{c['n']}.mp4")], check=True)
    print('stock', c['n'], 'pexels', c['src'], 'ok', (out / f"stock{c['n']}.mp4").stat().st_size, 'bytes')

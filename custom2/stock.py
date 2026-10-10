#!/usr/bin/env python3
"""Fetch the Pexels stock segments for the cutaways (never committed) and cut each to a 960x720 cover-cropped, 30 fps, silent mp4.
usage: stock.py OUTDIR [CACHEDIR]   — downloads https://www.pexels.com/download/video/<id>/ (public download link, Pexels licence: free for commercial use);
falls back to the Pexels API with the PEXELS_API_KEY env var if the public link is refused. Prints only ids and sizes, never keys."""
import json, os, subprocess, sys, urllib.request
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent))
from build2 import CUTAWAYS, CARD

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


def ok(p):
    r = subprocess.run(['ffprobe', '-v', 'error', '-select_streams', 'v:0', '-show_entries', 'stream=width', '-of', 'csv=p=0', str(p)], capture_output=True, text=True)
    return r.returncode == 0 and r.stdout.strip().isdigit()


for c in CUTAWAYS:
    src = cache / f"{c['pexels']}.mp4"
    if not (src.exists() and ok(src)):
        try:
            get(f"https://www.pexels.com/download/video/{c['pexels']}/", src)
        except Exception as e:
            print('public link failed for', c['pexels'], type(e).__name__)
        if not (src.exists() and ok(src)):
            key = os.environ.get('PEXELS_API_KEY')
            assert key, f"cannot fetch {c['pexels']} and no PEXELS_API_KEY"
            tmp = cache / 'api.json'
            get(f"https://api.pexels.com/videos/videos/{c['pexels']}", tmp, {'Authorization': key})
            files = [f for f in json.load(open(tmp))['video_files'] if f.get('file_type') == 'video/mp4' and (f.get('width') or 0) <= 1920]
            files.sort(key=lambda f: -(f.get('width') or 0))
            get(files[0]['link'], src)
    assert ok(src), f"bad file for {c['pexels']}"
    dur = round(c['e'] - c['t'] + 0.4, 3)   # a little tail so the video never freezes before the card leaves
    W, H = CARD['w'], CARD['h']
    subprocess.run(['ffmpeg', '-y', '-loglevel', 'error', '-ss', str(c['ss']), '-t', str(dur), '-i', str(src),
                    '-vf', f'scale={W}:{H}:force_original_aspect_ratio=increase:flags=lanczos,crop={W}:{H},fps=30,eq=saturation=1.05', '-an', '-c:v', 'libx264', '-crf', '16', '-preset', 'fast', '-pix_fmt', 'yuv420p',
                    str(out / f"cut{c['n']}.mp4")], check=True)
    print('cutaway', c['n'], 'pexels', c['pexels'], 'ok', (out / f"cut{c['n']}.mp4").stat().st_size, 'bytes')

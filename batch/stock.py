#!/usr/bin/env python3
"""Fetch the Pexels stock cutaways a plan asks for (queries chosen by the planner), cut to 1080x1920 / 30 fps / silent / graded.
A cutaway that cannot be fetched is REMOVED from the plan (a metaphor_stock wildcard degrades to negative_flash) - the clip never fails on stock.
usage: stock.py --plan plan.json --out DIR   (env PEXELS_API_KEY; never printed)"""
import argparse, json, os, random, subprocess, sys, urllib.parse, urllib.request
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from presets import PRESETS
from build import stock_cards

UA = {'User-Agent': 'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 Chrome/124 Safari/537.36'}


def get(url, dst=None, headers=None):
    req = urllib.request.Request(url, headers={**UA, **(headers or {})})
    with urllib.request.urlopen(req, timeout=120) as r:
        if dst is None:
            return json.loads(r.read().decode('utf-8'))
        with open(dst, 'wb') as f:
            while True:
                b = r.read(1 << 20)
                if not b:
                    break
                f.write(b)


def probe(p):
    r = subprocess.run(['ffprobe', '-v', 'error', '-select_streams', 'v:0', '-show_entries', 'stream=width,height', '-of', 'csv=p=0', str(p)], capture_output=True, text=True)
    return [int(x) for x in r.stdout.strip().split(',')] if r.returncode == 0 and r.stdout.strip() else None


def fetch_one(c, key, out, grade, seed):
    q = c['query']
    rng = random.Random(f'{seed}-{c["n"]}')
    need = max(c['e'] - c['t'] + 0.5, 1.5)
    for orient in ('portrait', 'landscape'):
        url = 'https://api.pexels.com/videos/search?' + urllib.parse.urlencode({'query': q, 'per_page': 15, 'orientation': orient, 'size': 'medium'})
        try:
            res = get(url, headers={'Authorization': key})
        except Exception as e:                                        # noqa
            print(f'  stock {c["n"]}: search failed ({type(e).__name__})')
            continue
        vids = [v for v in res.get('videos', []) if (v.get('duration') or 0) >= need + 0.5]
        rng.shuffle(vids)
        for v in vids[:4]:
            files = [f for f in v.get('video_files', []) if f.get('file_type') == 'video/mp4' and 700 <= (f.get('width') or 0) <= 2000]
            if not files:
                continue
            files.sort(key=lambda f: abs((f.get('width') or 0) - (1080 if orient == 'portrait' else 1500)))
            src = out / f'_src{c["n"]}.mp4'
            try:
                get(files[0]['link'], src)
            except Exception as e:                                    # noqa
                continue
            wh = probe(src)
            if not wh:
                continue
            w, h = wh
            cw = int(h * 9 / 16) if w > h else w
            vf = (f'crop={cw}:{h}:{max(0, (w - cw) // 2)}:0,' if w > h else '') + \
                 f'scale=1080:1920:force_original_aspect_ratio=increase:flags=lanczos,crop=1080:1920,fps=30,{grade},format=yuv420p'
            ss = round(rng.uniform(0, max(0.0, (v['duration'] - need - 0.3) * 0.6)), 2)
            dst = out / f'stock{c["n"]}.mp4'
            r = subprocess.run(['ffmpeg', '-y', '-loglevel', 'error', '-ss', str(ss), '-t', str(round(need, 2)), '-i', str(src), '-vf', vf, '-an',
                                '-c:v', 'libx264', '-crf', '16', '-preset', 'fast', str(dst)])
            src.unlink(missing_ok=True)
            if r.returncode == 0 and dst.exists() and dst.stat().st_size > 20000:
                print(f'  stock {c["n"]}: "{q}" -> pexels {v["id"]} ({orient}) ok {dst.stat().st_size} bytes')
                return True
    return False


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--plan', required=True)
    ap.add_argument('--out', required=True)
    a = ap.parse_args()
    plan = json.loads(Path(a.plan).read_text(encoding='utf-8'))
    out = Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    pr = PRESETS[plan['preset']]
    need = stock_cards(plan)
    if not need:
        print('no stock needed')
        return
    key = os.environ.get('PEXELS_API_KEY')
    failed = []
    for c in need:
        ok = bool(key) and fetch_one(c, key, out, pr['stock_grade'], plan['seed'])
        if not ok:
            failed.append(c)
            print(f'  stock {c["n"]}: FAILED -> removed from the plan')
    for c in failed:
        if c.get('wild'):
            wc = plan['wildcard']
            wc.update(type='negative_flash', e=round(wc['t'] + 0.14, 2), query='')
            wc['window'] = [round(wc['t'] - 0.3, 2), round(wc['e'] + 0.3, 2)]
            plan.setdefault('notes', []).append('metaphor_stock failed -> negative_flash')
        else:
            plan['inserts'] = [i for i in plan['inserts'] if not (i['kind'] == 'stock' and i['n'] == c['n'])]
            plan.setdefault('notes', []).append(f'stock insert {c["n"]} dropped')
    plan['stock_failed'] = [c['n'] for c in failed]
    Path(a.plan).write_text(json.dumps(plan, ensure_ascii=False, indent=1), encoding='utf-8')


if __name__ == '__main__':
    main()

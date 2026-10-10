#!/usr/bin/env python3
"""K1 composition builder: ONE HyperFrames project for the range [a,b] of the clip (no cuts, no speed change, no cut-out, no overlay on the room).
usage: build_k1.py --a 0 --b 28.4 --out proj --clip range.mp4 [--fonts DIR --gsap FILE]"""
import argparse, json, re, shutil
from pathlib import Path
import plan_k1 as P

HERE = Path(__file__).resolve().parent
ap = argparse.ArgumentParser()
ap.add_argument('--a', type=float, required=True)
ap.add_argument('--b', type=float, required=True)
ap.add_argument('--out', required=True)
ap.add_argument('--clip', required=True)
ap.add_argument('--fonts', default=str(HERE / 'fonts'))
ap.add_argument('--gsap', required=True)
a = ap.parse_args()
A, B = a.a, a.b
proj = Path(a.out)
(proj / 'media').mkdir(parents=True, exist_ok=True)
(proj / 'fonts').mkdir(exist_ok=True)
for f in Path(a.fonts).glob('*.woff2'):
    shutil.copy2(f, proj / 'fonts' / f.name)
shutil.copy2(a.gsap, proj / 'gsap.min.js')
dst = proj / 'media' / 'clip.mp4'
if Path(a.clip).resolve() != dst.resolve():
    shutil.copy2(a.clip, dst)
(proj / 'meta.json').write_text(json.dumps({'id': 'custom-k1', 'name': 'custom k1'}), encoding='utf-8')
dur = round(B - A, 3)

face = json.loads((HERE / 'data' / 'face_track_k1.json').read_text(encoding='utf-8'))
M = P.Meas(a.fonts)
caps = P.build_caps(a.fonts)
cam = P.cam_path(face)
hook = None
if A <= P.HOOK_T0:
    lines = []
    for l in P.HOOK:
        em = M.em(l['text'], l['font']) + (0.6 if l['cls'] == 'h3' else 0.05)
        lines.append(dict(l, size=int(min(l['size'], 940 / em))))
    hook = {'lines': lines, 't0': P.HOOK_T0, 'exit': P.HOOK_EXIT, 't1': P.HOOK_T1}
cards = [c for c in P.INSERTS if c['e'] > A and c['t'] < B]
plan = {'off': A, 'dur': dur, 'cam': cam, 'caps': [c for c in caps if c['e'] > A and c['s'] < B], 'cards': cards,
        'hits': [h for h in P.hits() if A - 0.01 <= h[0] <= B], 'hook': hook, 'capY': P.CAP_Y}
fonts = []
for sc in ('cyrillic', 'latin'):
    rng = ('U+0301,U+0400-045F,U+0490-0491,U+04B0-04B1,U+2116' if sc == 'cyrillic'
           else 'U+0000-00FF,U+0131,U+0152-0153,U+02BB-02BC,U+02C6,U+02DA,U+02DC,U+2000-206F,U+2074,U+20AC,U+2122,U+2191,U+2193,U+2212,U+2215,U+FEFF,U+FFFD')
    for fam, key, wt, st in (('Manrope', 'manrope-%s-800-normal', 800, 'normal'), ('JetBrains Mono', 'jetbrains-mono-%s-800-normal', 800, 'normal'),
                             ('Lora', 'lora-%s-700-italic', 700, 'italic'), ('Unbounded', 'unbounded-%s-900-normal', 900, 'normal')):
        fonts.append(f"@font-face{{font-family:'{fam}';font-weight:{wt};font-style:{st};src:url('fonts/{key % sc}.woff2') format('woff2');unicode-range:{rng};font-display:block}}")
css = (HERE / 'style_k1.css').read_text(encoding='utf-8')
js = (HERE / 'scene_k1.js').read_text(encoding='utf-8')
html = f"""<!doctype html>
<html lang="ru"><head><meta charset="utf-8"><meta name="viewport" content="width=1080, height=1920">
<script src="gsap.min.js"></script>
<style>
{chr(10).join(fonts)}
{css}
</style></head>
<body>
<div id="root" data-composition-id="main" data-start="0" data-duration="{dur}" data-width="1080" data-height="1920">
  <div id="snap"><div id="cam"><video id="v" src="media/clip.mp4" muted playsinline data-start="0" data-duration="{dur}" data-track-index="1"></video></div></div>
  <div id="over" class="layer"></div>
</div>
<script>window.PLAN = {json.dumps(plan, ensure_ascii=False)};</script>
<script>
{js}
</script>
</body></html>"""
(proj / 'index.html').write_text(html, encoding='utf-8')
print(f'built {proj} {A}-{B} ({dur}s): caps={len(plan["caps"])} cards={[c["n"] for c in cards]} hook={bool(hook)}')

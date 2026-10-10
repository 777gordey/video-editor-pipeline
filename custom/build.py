#!/usr/bin/env python3
"""Assemble one HyperFrames project for a time range of the clip (no cuts, no speed change).
usage: build.py --a 0 --b 26.7 --out proj_p1 [--layers DIR | --plain]
layers DIR holds inv.mp4, pb.mp4 (person cut-out as multiply/screen pair, 1080x1920) and orig.mp4 (raw clip, same range).
--plain: use the raw clip as the person layer (layout stills only, no cut-out)."""
import argparse, json, re, shutil
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent

FIX = {  # normalised ASR word -> display text (None = drop)
    'миланов': 'Милана', 'проден': 'ПроДент', 'чисточку': 'чистку', 'картой': None,
}
KEY = {  # normalised word -> 1 mint / 2 coral
    'красотку': 1, 'проденте': 1, 'чистку': 1, 'тысяч': 1, 'воскресенье': 1, 'утром': 1, 'идеально': 1,
    'телефона': 1, 'проигнорировали': 2, 'записали': 1, 'бесплатна': 1, 'поздно': 2, 'сутки': 1,
}
NUMKEY = {'9', '6', '8'}


def load_words(path):
    segs = json.loads(Path(path).read_text(encoding='utf-8'))
    out = []
    for s in segs:
        for w in s['words']:
            raw = w['w']
            norm = re.sub(r'[^\w]', '', raw.lower())
            out.append({'raw': raw, 'n': norm, 's': w['s'], 'e': w['e']})
    # fixes
    for i, w in enumerate(out):
        if w['n'] == 'может' and abs(w['s'] - 68.30) < 0.05:
            w['fix'] = 'можно'
    res = []
    for w in out:
        t = w.get('fix') or FIX.get(w['n'], re.sub(r'[.,!?]+$', '', w['raw']))
        if t is None:
            continue
        k = KEY.get(w['n'], 0)
        if w['n'] in NUMKEY:
            k = 1
        res.append({'raw': w['raw'] if w.get('fix') is None else t + re.sub(r'^.*?([.,!?]*)$', r'\1', w['raw']),
                    't': t, 's': w['s'], 'e': w['e'], 'k': k})
    # "Проден" is followed by '.', keep display ПроДент
    return res


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--a', type=float, required=True)
    ap.add_argument('--b', type=float, required=True)
    ap.add_argument('--out', required=True)
    ap.add_argument('--layers')
    ap.add_argument('--plain', action='store_true')
    ap.add_argument('--words', default=str(ROOT / 'out' / 'transcript_medium.json'))
    ap.add_argument('--gsap', default=str(HERE / 'gsap.min.js'))
    ap.add_argument('--fonts', default=str(HERE / 'fonts'))
    a = ap.parse_args()

    proj = Path(a.out)
    (proj / 'media').mkdir(parents=True, exist_ok=True)
    (proj / 'fonts').mkdir(exist_ok=True)
    FD = Path(a.fonts)
    FAM = {'montserrat': 'Montserrat', 'unbounded': 'Unbounded', 'russo-one': 'Russo One'}
    for f in FD.glob('*.woff2'):
        if re.match(r'(.+?)-(cyrillic|latin)-', f.name).group(1) in FAM:
            shutil.copy2(f, proj / 'fonts' / f.name)
    shutil.copy2(a.gsap, proj / 'gsap.min.js')
    (proj / 'meta.json').write_text(json.dumps({'id': 'custom-edit', 'name': 'custom edit'}), encoding='utf-8')
    dur = round(a.b - a.a, 3)
    words = [w for w in load_words(a.words) if w['e'] > a.a - 0.01 and w['s'] < a.b]

    fonts = []
    for f in sorted(FD.glob('*.woff2')):
        m = re.match(r'(.+)-(cyrillic|latin)-(\d+)-normal\.woff2', f.name)
        if m.group(1) not in FAM:
            continue
        fam = FAM[m.group(1)]
        rng = ('U+0301,U+0400-045F,U+0490-0491,U+04B0-04B1,U+2116' if m.group(2) == 'cyrillic'
               else 'U+0000-00FF,U+0131,U+0152-0153,U+02BB-02BC,U+02C6,U+02DA,U+02DC,U+2000-206F,U+2074,U+20AC,U+2122,U+2191,U+2193,U+2212,U+2215,U+FEFF,U+FFFD')
        fonts.append(f"@font-face{{font-family:'{fam}';font-weight:{m.group(3)};font-style:normal;src:url('fonts/{f.name}') format('woff2');unicode-range:{rng};font-display:block}}")

    if a.plain or not a.layers:
        person = f'<video id="pb" class="layer" src="media/orig.mp4" muted playsinline data-start="0" data-duration="{dur}" data-track-index="1"></video>'
    else:
        person = (f'<video id="inv" class="layer" src="media/inv.mp4" muted playsinline data-start="0" data-duration="{dur}" data-track-index="1"></video>'
                  f'<video id="pb" class="layer" src="media/pb.mp4" muted playsinline data-start="0" data-duration="{dur}" data-track-index="2"></video>')
    lap = f'<video id="lap" src="media/orig.mp4" muted playsinline data-start="0" data-duration="{dur}" data-track-index="3" style="position:absolute;left:0;top:0;width:720px;height:480px;opacity:0;visibility:hidden"></video>'
    if a.layers:
        for n in ('inv.mp4', 'pb.mp4', 'orig.mp4'):
            if (Path(a.layers) / n).exists():
                shutil.copy2(Path(a.layers) / n, proj / 'media' / n)
    # SVG grain tile
    grain = ("data:image/svg+xml;utf8,<svg xmlns='http://www.w3.org/2000/svg' width='300' height='300'><filter id='n'><feTurbulence type='fractalNoise' baseFrequency='.9' numOctaves='2' stitchTiles='stitch'/></filter><rect width='300' height='300' filter='url(%23n)'/></svg>")
    plan = {'off': a.a, 'dur': dur, 'words': words}
    if a.layers and (Path(a.layers) / 'lap.json').exists():
        runs = json.loads((Path(a.layers) / 'lap.json').read_text())['runs']
        runs = [r for r in runs if 17 < r[0] < 25]
        if runs:
            plan['lap'] = [round(runs[0][0], 2), round(runs[0][1], 2)]
    css = (HERE / 'style.css').read_text(encoding='utf-8')
    js = ''.join((HERE / n).read_text(encoding='utf-8') + '\n' for n in ('lib.js', 'objs.js', 'scenes.js'))
    html = f"""<!doctype html>
<html lang="ru"><head><meta charset="utf-8"><meta name="viewport" content="width=1080, height=1920">
<script src="gsap.min.js"></script>
<style>
{chr(10).join(fonts)}
{css}
#grain{{background-image:url("{grain}")}}
</style></head>
<body>
<div id="root" data-composition-id="main" data-start="0" data-duration="{dur}" data-width="1080" data-height="1920">
  <div id="cam"><div id="snap"><div id="scene">
    <div id="bgLayer"><div id="bgBase"></div><div id="floor"></div></div>
    <div id="behind"></div>
    {person}
    <div id="front">{lap}</div>
    <div id="dust" style="position:absolute;left:0;top:0;width:1080px;height:1920px"></div>
  </div></div></div>
  <div id="caps"></div>
  <div id="fx"></div>
  <div id="vign"></div><div id="grain"></div>
  <div id="flash"></div>
</div>
<script>window.PLAN = {json.dumps(plan, ensure_ascii=False)};</script>
<script>
{js}
window.__timelines = window.__timelines || {{}};
window.__timelines["main"] = tl;
</script>
</body></html>"""
    (proj / 'index.html').write_text(html, encoding='utf-8')
    print(f'built {proj} {a.a}-{a.b} ({dur}s), words={len(words)}')


if __name__ == '__main__':
    main()

#!/usr/bin/env python3
"""Composition builder: ONE HyperFrames project for the range [a,b] of the clip (no cuts, no speed change, no cut-out).
usage: build.py --analysis A.json --plan P.json --a 0 --b 28.4 --out proj --clip range.mp4 --fonts DIR --gsap FILE"""
import argparse, json, shutil, sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from presets import PRESETS, FONT_FILES
from plan import HOOK_POPS, HOOK_T0, HOOK_EXIT, HOOK_T1
import lib


def stock_cards(plan):
    """stock cutaways: planned inserts + the metaphor_stock wildcard, all numbered the same way"""
    cards = [c for c in plan['inserts'] if c['kind'] == 'stock']
    wc = plan['wildcard']
    tr = (plan.get('style') or {}).get('stock_transition', 'zoom')
    ins_ = {'whip': lambda n: 'whip', 'zoom': lambda n: 'cut', 'flash': lambda n: 'cut'}[tr]
    outs_ = {'whip': lambda n: 'cut', 'zoom': lambda n: 'flash' if n % 2 else 'cut', 'flash': lambda n: 'flash'}[tr]
    out = [dict(c, **{'in': ins_(c['n']), 'out': outs_(c['n'])}) for c in cards]
    if wc['type'] == 'metaphor_stock':
        out.append({'kind': 'stock', 'n': 90, 't': wc['t'], 'e': wc['e'], 'query': wc['query'], 'in': 'cut', 'out': 'flash', 'wild': True})
    return out


def scene_cards(plan):
    """everything scene.js draws as a card/slam (stock gets its numbers from stock_cards)"""
    stocks = {(c['t']): c for c in stock_cards(plan)}
    out = []
    for c in plan['inserts']:
        out.append(stocks.get(c['t'], c) if c['kind'] == 'stock' else c)
    for c in stock_cards(plan):
        if c.get('wild'):
            out.append(c)
    return out


def hits_for(plan, pr, shift):
    h = [[round(t + shift, 2), pr['hit_amp'][min(i, 2)], pr['hit_punch'][min(i, 2)]] for i, t in enumerate(HOOK_POPS[:len(lib.hook_lines(plan))])]
    for c in plan['inserts']:
        h.append([round(c['t'] + 0.02, 2), 9 if c['kind'] != 'wave' else 7, 0.02])
    wc = plan['wildcard']
    if wc['type'] in ('silence_gag', 'sound_gag', 'negative_flash', 'punch_cut', 'echo_caption', 'split_black', 'timer'):
        h.append([round(wc['t'] + 0.02, 2), 13 if wc['type'] != 'sound_gag' else 8, 0.04])
    if plan.get('big') is not None:
        h.append([round(plan['_words'][plan['big']]['s'] + 0.04, 2), 10, 0.03])
    return h


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--analysis', required=True)
    ap.add_argument('--plan', required=True)
    ap.add_argument('--a', type=float, required=True)
    ap.add_argument('--b', type=float, required=True)
    ap.add_argument('--out', required=True)
    ap.add_argument('--clip', required=True)
    ap.add_argument('--fonts', default=str(HERE / 'fonts'))
    ap.add_argument('--gsap', required=True)
    a = ap.parse_args()
    an = lib.load_json(a.analysis)
    plan = lib.load_json(a.plan)
    pr = PRESETS[plan['preset']]
    A, B = a.a, a.b
    dur = round(B - A, 3)
    plan['_words'] = an['words']
    proj = Path(a.out)
    (proj / 'media').mkdir(parents=True, exist_ok=True)
    (proj / 'fonts').mkdir(exist_ok=True)
    for f in Path(a.fonts).glob('*.woff2'):
        shutil.copy2(f, proj / 'fonts' / f.name)
    shutil.copy2(a.gsap, proj / 'gsap.min.js')
    dst = proj / 'media' / 'clip.mp4'
    if Path(a.clip).resolve() != dst.resolve():
        shutil.copy2(a.clip, dst)
    (proj / 'meta.json').write_text(json.dumps({'id': 'batch-' + pr['id'], 'name': 'batch ' + pr['id']}), encoding='utf-8')

    wc = plan['wildcard']
    shift = 0.45 if wc['type'] == 'blackout_open' else 0.0
    hook_t0, hook_exit, hook_t1 = HOOK_T0 + shift, HOOK_EXIT + shift, HOOK_T1 + shift

    M = lib.Meas(pr, a.fonts)
    words = lib.clean_words(an['words'], plan.get('fixes'))
    keys, emo, nums = set(plan['keys']), set(plan['emo']), set(plan['nums'])
    caps = lib.build_caps(words, M, pr, keys, emo, nums, hook_t1, plan.get('big'))
    ZK = lib.zoom_keys(an['dur'], an['cuts'], pr, plan['seed'], (plan.get('style') or {}).get('camera', 'normal'))
    jumps = [(wc['t'], wc['e'], 1.22)] if wc['type'] == 'punch_cut' else []
    cam = lib.cam_path(an['face'], ZK, an['cuts'], an['dur'], jumps=jumps)

    hook = None
    if A <= hook_t0 + 0.01:
        lines = []
        single = (plan.get('style') or {}).get('hook_layout') == 'single'
        for i, txt in enumerate(lib.hook_lines(plan)):
            j = 1 if single else i                         # single layout: the one line wears the big face (h2) in the middle slot
            role = pr['hook_font_role'][j]
            em = M.em(txt, role) + 0.05
            lines.append({'text': txt, 'cls': f'h{j + 1}', 't': round(HOOK_POPS[i] + shift, 2), 'y': pr['hook_y'][j] if not single else 1440,
                          'size': int(min(pr['hook_size'][j] * (1.5 if single else 1.0), 940 / em))})
        hook = {'lines': lines, 't0': hook_t0, 'exit': hook_exit, 't1': hook_t1}
    cards = [dict(c) for c in scene_cards(plan) if c['e'] > A and c['t'] < B]
    for c in cards:                                   # giant words must fit the 1080 px frame
        if c['kind'] == 'punch':
            c['size'] = int(min(230, 900 / (M.em(c['text'], 'h2') + 0.5)))
        elif c['kind'] == 'stamp':
            c['size'] = int(min(150, 880 / (M.em(c['text'], 'h2') + 0.85)))
    wcv = dict(wc)
    if wc['type'] == 'echo_caption' and not wcv.get('text'):
        wcv['text'] = words and next((w['t'] for w in words if w['idx'] == wc['at']), '') or ''
    wcv['text'] = (wcv.get('text') or '').upper()
    if wc['type'] == 'split_black' and wcv['text']:
        longest = max(wcv['text'].split(), key=len)
        wcv['size'] = int(min(190, 860 / (M.em(longest, 'h2') + 0.05)))
    pagePlan = {'off': A, 'dur': dur, 'cam': cam, 'caps': [c for c in caps if c['e'] > A and c['s'] < B], 'cards': cards,
                'hits': [h for h in hits_for(plan, pr, shift) if A - 0.01 <= h[0] <= B], 'hook': hook, 'capY': pr['cap_y'],
                'band': pr['card_band'], 'hookAnim': pr['hook_anim'], 'capMode': 'wordwise' if pr['id'] == 'dark' else 'group',
                'wc': wcv if wc['type'] not in ('metaphor_stock',) else {}}
    # fonts
    faces = []
    for key in pr['fonts']:
        fam, wt, st, pat = FONT_FILES[key]
        for sc in ('cyrillic', 'latin'):
            rng = ('U+0301,U+0400-045F,U+0490-0491,U+04B0-04B1,U+2116' if sc == 'cyrillic'
                   else 'U+0000-00FF,U+0131,U+0152-0153,U+02BB-02BC,U+02C6,U+02DA,U+02DC,U+2000-206F,U+2074,U+20AC,U+2122,U+2191,U+2193,U+2212,U+2215,U+FEFF,U+FFFD')
            faces.append(f"@font-face{{font-family:'{fam}';font-weight:{wt};font-style:{st};src:url('fonts/{pat.format(sc=sc)}.woff2') format('woff2');unicode-range:{rng};font-display:block}}")
    css = (HERE / 'style_base.css').read_text(encoding='utf-8') + '\n' + (HERE / pr['css']).read_text(encoding='utf-8')
    js = (HERE / 'scene.js').read_text(encoding='utf-8')
    stockvids = ''.join(
        f'<div id="sb{c["n"]}" class="sbox"><video id="sv{c["n"]}" src="media/stock{c["n"]}.mp4" muted playsinline data-start="{max(0, c["t"] - A):.3f}" '
        f'data-duration="{min(c["e"], B) - max(c["t"], A):.3f}" data-track-index="{5 + (c["n"] % 50)}"></video></div>'
        for c in cards if c['kind'] == 'stock')
    lb = '<div id="lb1" class="lb layer2"></div><div id="lb2" class="lb layer2"></div>' if wc['type'] == 'letterbox' else '<div id="lb1" class="lb" style="display:none"></div><div id="lb2" class="lb" style="display:none"></div>'
    html = f"""<!doctype html>
<html lang="ru"><head><meta charset="utf-8"><meta name="viewport" content="width=1080, height=1920">
<script src="gsap.min.js"></script>
<style>
{chr(10).join(faces)}
{css}
</style></head>
<body class="band-{pr['card_band']}">
<div id="root" data-composition-id="main" data-start="0" data-duration="{dur}" data-width="1080" data-height="1920">
  <div id="snap"><div id="cam"><video id="v" src="media/clip.mp4" muted playsinline data-start="0" data-duration="{dur}" data-track-index="1"></video></div>
    <div id="stocks" class="layer">{stockvids}</div></div>
  <div id="blk2"></div>
  <div id="over" class="layer">{lb}</div>
  <div id="blk"></div>
</div>
<script>window.PLAN = {json.dumps(pagePlan, ensure_ascii=False)};</script>
<script>
{js}
</script>
</body></html>"""
    (proj / 'index.html').write_text(html, encoding='utf-8')
    (proj / 'stock_needs.json').write_text(json.dumps([{'n': c['n'], 'query': c['query'], 'dur': round(c['e'] - c['t'] + 0.4, 2)} for c in stock_cards(plan)]), encoding='utf-8')
    print(f'built {proj} {A}-{B} ({dur}s): preset={pr["id"]} caps={len(pagePlan["caps"])} cards={[(c["kind"], c["n"]) for c in cards]} hook={bool(hook)} wc={wc["type"]}')


if __name__ == '__main__':
    main()

#!/usr/bin/env python3
"""Builds data/words_k3.json from three medium-model passes (0-26.4 s main run, 27.3-57.7 s re-run of the part the main run lost, 59 s+ main run).
usage: gen_words.py tr_medium.json v_mid.txt words_k3.json"""
import json, re, sys

FIX = {'проден': 'ПроДент', 'миланов': 'Милана', 'сформулируем': 'сформулирую', 'еще': 'ещё', 'прием': 'приём', 'наплювать': 'наплевать',
       'отрыв': 'оффер', 'картой': 'каждый'}
main = [w for s in json.load(open(sys.argv[1], encoding='utf-8')) for w in s['words']]
mid = []
for m in re.finditer(r'(\S+?)\[([\d.]+)(\?[\d.]+)?\]', open(sys.argv[2], encoding='utf-8').read()):
    mid.append({'w': m.group(1), 's': float(m.group(2))})
seq = []
for w in main:
    if w['s'] < 26.3:
        seq.append({'w': w['w'], 's': w['s'], 'e': w['e']})
for w in mid:
    if 26.3 < w['s'] < 57.7 and w['w'].lower().strip('.,!?…') not in ('умут', 'углу'):
        seq.append({'w': w['w'], 's': w['s'], 'e': None})
for w in main:
    if w['s'] >= 59.0:
        seq.append({'w': w['w'], 's': w['s'], 'e': w['e']})
out = []
for i, w in enumerate(seq):
    raw = w['w']
    n = re.sub(r'[^\w]', '', raw.lower())
    if raw.startswith('-то') and out:
        out[-1]['w'] += raw
        continue
    nxt = seq[i + 1]['s'] if i + 1 < len(seq) else w['s'] + 0.6
    e = w['e'] if w['e'] else min(nxt - 0.02, w['s'] + 0.6)
    if e - w['s'] < 0.1:
        e = w['s'] + 0.12
    t = FIX.get(n) or re.sub(r'[.,!?…]+$', '', raw)
    p = re.search(r'(\.\.\.|…|[,!?]+|\.)$', raw)
    punct = (p.group(0) if p else '').replace('...', '.')
    out.append({'w': t + punct, 's': round(w['s'], 2), 'e': round(e, 2)})
for w in out:
    if w['w'] == 'скажи.':
        w['w'] = 'скажи,'
    if w['w'] in ('Смотрите.',):
        pass
json.dump([{'words': out}], open(sys.argv[3], 'w', encoding='utf-8'), ensure_ascii=False)
print(len(out), 'words')
print(' '.join('%s@%.1f' % (w['w'], w['s']) for w in out))

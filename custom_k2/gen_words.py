#!/usr/bin/env python3
"""Corrects the medium-model transcript into data/words_k2.json (word timestamps kept). usage: gen_words.py tr_medium.json words_k2.json"""
import json, re, sys
FIX = {'проден': 'ПроДент', 'миланов': 'Милана', 'сформулируем': 'сформулирую', 'еще': 'ещё', 'прием': 'приём', 'угут': None}
words = [w for s in json.load(open(sys.argv[1], encoding='utf-8')) for w in s['words']]
out = []
for i, w in enumerate(words):
    raw = w['w']
    n = re.sub(r'[^\w]', '', raw.lower())
    if n in FIX and FIX[n] is None:
        continue
    if n == 'к' and 5.9 < w['s'] < 6.2:
        continue
    if raw.startswith('-то') and out:
        out[-1]['w'] = out[-1]['w'] + raw; out[-1]['e'] = w['e']; continue
    e = w['e'] if w['e'] - w['s'] >= 0.03 else w['s'] + 0.12
    t = FIX.get(n) or re.sub(r'[.,!?…]+$', '', raw)
    punct = re.search(r'[,!?]+$|\.$', raw)
    out.append({'w': t + (punct.group(0) if punct else ''), 's': w['s'], 'e': e})
json.dump([{'words': out}], open(sys.argv[2], 'w', encoding='utf-8'), ensure_ascii=False)
print(len(out), 'words')

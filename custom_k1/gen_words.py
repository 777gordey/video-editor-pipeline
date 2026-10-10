#!/usr/bin/env python3
"""Corrects the medium-model transcript into data/words_k1.json (word timestamps kept). usage: gen_words.py tr_medium.json words_k1.json"""
import json, re, sys
FIX = {'проден': 'ПроДент', 'миланов': 'Милана', 'самолетик': 'самолётик', 'утопно': 'удобно', 'сформулируем': 'сформулирую', 'еще': 'ещё', 'прием': 'приём', 'умут': None, 'к': None}
out = []
for s in json.load(open(sys.argv[1], encoding='utf-8')):
    for w in s['words']:
        raw = w['w']
        n = re.sub(r'[^\w]', '', raw.lower())
        if n in FIX and FIX[n] is None:
            if n == 'к' and not (w['s'] > 6.6 and w['s'] < 6.8):
                pass
            else:
                continue
        if w['e'] - w['s'] < 0.03:
            w = dict(w, e=w['s'] + 0.12)
        t = FIX.get(n) or re.sub(r'[.,!?…]+$', '', raw).rstrip('.')
        punct = re.search(r'[,!?]+$|\.$', raw)
        out.append({'w': t + (punct.group(0).replace('…', '') if punct else ''), 's': w['s'], 'e': w['e']})
json.dump([{'words': out}], open(sys.argv[2], 'w', encoding='utf-8'), ensure_ascii=False)
print(len(out), 'words')

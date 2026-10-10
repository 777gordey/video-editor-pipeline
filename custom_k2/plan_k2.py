#!/usr/bin/env python3
"""K2 plan (direction A: comedy / reaction): shared data for build_k2.py (video) and mix_k2.py (audio).
Die-cut stickers (drawn in code) sit in the corners above the eyes; captions sit below the chin."""
import json, math, re
from pathlib import Path

HERE = Path(__file__).resolve().parent
DUR = 61.2

# real cuts / whips in the footage; laptop shots and whips keep the camera flat
CUTS = [2.63, 4.2, 6.33, 15.43, 15.63, 18.53, 47.07, 48.93, 57.43]
ZK = [(0.0, 1.00), (2.4, 1.16), (2.63, 1.00), (4.2, 1.00), (6.0, 1.10), (6.33, 1.00), (7.2, 1.00), (7.6, 1.18), (9.5, 1.18), (10.2, 1.04),
      (13.0, 1.04), (15.2, 1.15), (15.43, 1.00), (18.53, 1.00), (19.4, 1.00), (21.3, 1.10), (22.4, 1.10), (23.2, 1.00), (26.0, 1.00), (27.0, 1.12),
      (28.8, 1.12), (29.7, 1.00), (34.9, 1.00), (35.25, 1.16), (36.4, 1.16), (37.0, 1.16), (38.2, 1.10), (40.0, 1.00), (44.7, 1.00), (45.0, 1.14),
      (46.9, 1.14), (47.07, 1.00), (48.93, 1.00), (49.5, 1.14), (51.6, 1.14), (52.4, 1.02), (57.43, 1.00), (59.0, 1.04), (61.2, 1.10)]
ZMAX = 1.22
ANCHOR_Y = 0.30

# ---------------------------------------------------------------- hook (picked A) + alternatives
HOOK_ALTS = [
    ('A (picked)', 'мне лень / ТЕБЕ ГОВОРИТЬ / ПРОСТО ПОСМОТРИ', 'said at 0.0-2.9 s: «мне лень тебе что-то говорить, ты просто возьми и посмотри»'),
    ('B', 'ТЫ ПРОСТО / ВОЗЬМИ И / ПОСМОТРИ', 'said at 1.7-2.9 s'),
    ('C', 'В 6 УТРА? / КЛИНИКА ЕЩЁ / НЕ РАБОТАЕТ', 'said at 37-42 s: the joke up front'),
]
HOOK = [
    {'text': 'мне лень', 'cls': 'h1', 't': 0.20, 'font': 'hand', 'size': 190, 'y': 1360, 'amp': 9, 'punch': 0.03, 'sfx': 'hk_bloop'},
    {'text': 'ТЕБЕ ГОВОРИТЬ', 'cls': 'h2', 't': 0.60, 'font': 'key', 'size': 100, 'y': 1520, 'amp': 15, 'punch': 0.05, 'sfx': 'boom_soft'},
    {'text': 'ПРОСТО ПОСМОТРИ', 'cls': 'h3', 't': 1.02, 'font': 'base', 'size': 108, 'y': 1690, 'amp': 11, 'punch': 0.04, 'sfx': 'hk_pep'},
]
HOOK_T0, HOOK_EXIT, HOOK_T1 = 0.10, 2.40, 2.68

# ---------------------------------------------------------------- stickers (die-cut, drawn in code). sfx = (time, name, dB vs voice peak or None)
INSERTS = [
    {'n': 1, 'kind': 'sloth', 't': 0.55, 'e': 2.45, 'what': 'sloth hanging from the top edge for «мне лень», droops, snores zzz',
     'sfx': [(0.62, 'sloth_down', None)]},
    {'n': 2, 'kind': 'price', 't': 15.75, 'e': 17.35, 'what': 'swinging price tag «4 000 ₽» + coin for «от 4 тысяч рублей»',
     'sfx': [(15.75, 'pop_1', None), (16.40, 'coin', None)]},
    {'n': 3, 'kind': 'alarm', 't': 37.25, 'e': 38.55, 'what': 'alarm clock 6:00 shaking for «мне надо в 6 утра»',
     'sfx': [(37.30, 'alarm_short', -12)]},
    {'n': 4, 'kind': 'closed', 't': 41.00, 'e': 42.75, 'what': 'hanging sign «ЗАКРЫТО» swings in for «клиника ещё не работает»',
     'sfx': [(41.02, 'rec_scratch', None), (41.80, 'fail_down', -11)]},
    {'n': 5, 'kind': 'stars', 't': 44.90, 'e': 46.70, 'what': 'five stars + «ИДЕАЛЬНО» stamp for «идеально»',
     'sfx': [(44.95, 'tick_b', -12), (45.08, 'tick_b', -12), (45.21, 'tick_b', -12), (45.34, 'tick_b', -12), (45.47, 'win_up', None)]},
]
FINAL = {'t': 59.32, 'sfx': [(59.34, 'ding_chime', None)]}                  # «бесплатна»: big orange key word + one ding


# ---------------------------------------------------------------- caption system
CAP_Y, CAP_MAX, CAP_W, GAP = 1545, 84, 940, 0.30
FONTS = {'base': ('rubik-{sc}-800-normal', -0.01), 'key': ('rubik-mono-one-{sc}-400-normal', -0.02), 'emo': ('pt-serif-{sc}-700-italic', 0.0), 'hand': ('caveat-{sc}-700-normal', 0.0)}
KEYS = {'лень', 'посмотри', 'клиника', 'ПроДент', '4', 'тысяч', 'воскресенье', 'утром', '9', '6', '8', 'часов', 'номер', 'качество', 'бесплатна',
        'демоверсия', 'каждый', 'гигиена', 'записали', 'приём', 'телефона', 'проигнорировали', 'ответили', 'лучше', 'говорить'}
EMO_NEG = {'поздно', 'нет', 'проигнорировали', 'лень'}
EMO_POS = {'идеально', 'приятно', 'привет', 'миланочка', 'чисточку', 'хорошо'}
NUMS = {'4', '9', '6', '8'}
IDEAS = [2.9, 3.72, 7.44, 13.24, 17.06, 19.3, 23.18, 29.74, 35.14, 40.56, 44.36, 47.02, 49.16, 52.64, 56.64]
STOP = {'в', 'с', 'к', 'и', 'а', 'о', 'у', 'на', 'по', 'до', 'не', 'от', 'за', 'из', 'бы', 'ли', 'же', 'или', 'но', 'то', 'вот', 'я', 'мне', 'мы', 'ваш', 'для', 'что', 'это', 'как', 'очень', 'ты', 'тебе'}


def load_words():
    segs = json.loads((HERE / 'data' / 'words_k2.json').read_text(encoding='utf-8'))
    out = []
    for s in segs:
        for w in s['words']:
            raw = w['w']
            t = re.sub(r'[.,!?…]+$', '', raw)
            out.append({'raw': raw, 't': t, 'n': t.lower(), 's': w['s'], 'e': w['e']})
    return out


class Meas:
    def __init__(self, fd):
        from fontTools.ttLib import TTFont
        self.f = {}
        for k, (pat, ls) in FONTS.items():
            self.f[k] = [(lambda t: (t.getBestCmap(), t['hmtx'], t['head'].unitsPerEm))(TTFont(Path(fd) / (pat.format(sc=sc) + '.woff2'))) for sc in ('cyrillic', 'latin')]

    def em(self, text, font='base'):
        ls = FONTS[font][1]
        w = 0.0
        for ch in text:
            for cm, hm, upm in self.f[font]:
                if ord(ch) in cm:
                    w += hm[cm[ord(ch)]][0] / upm + ls
                    break
            else:
                w += 0.6 + ls
        return w


def classify(g):
    hi, kind = None, None
    for pri in ('e', 'n', 'k'):
        for i, w in enumerate(g):
            n = w['n']
            if (pri == 'e' and (n in EMO_NEG or n in EMO_POS)) or (pri == 'n' and n in NUMS) or (pri == 'k' and n in {k.lower() for k in KEYS}):
                hi, kind = i, pri
                break
        if hi is not None:
            break
    spec = []
    for i, w in enumerate(g):
        if i == hi and kind == 'e':
            spec.append({'t': w['t'].lower(), 'cls': 'e', 'col': 'red' if w['n'] in EMO_NEG else 'vio', 's': w['s']})
        elif i == hi:
            spec.append({'t': w['t'], 'cls': 'k', 'col': 'amb', 's': w['s']})
        else:
            spec.append({'t': w['t'], 'cls': 'n', 'col': '', 's': w['s']})
    return spec


def cased(spec, starts):
    """sentence case: first word of a sentence capitalised, brand/names keep their case"""
    for i, x in enumerate(spec):
        if x['cls'] == 'k':
            x['t'] = x['t'].lower() if x['t'] != 'ПроДент' else x['t']
        if x['t'].lower() in ('гордей', 'милана', 'миланочка'):
            x['t'] = x['t'][0].upper() + x['t'][1:].lower()
        elif x['t'] == 'ПроДент':
            pass
        elif i == 0 and starts:
            x['t'] = x['t'][0].upper() + x['t'][1:]
        elif x['cls'] != 'k' or x['t'] != 'ПроДент':
            x['t'] = x['t'].lower() if x['t'] != 'ПроДент' else x['t']
    return spec


def spec_em(M, spec):
    tot = 0.0
    for x in spec:
        if x['cls'] == 'n':
            tot += M.em(x['t'], 'base')
        elif x['cls'] == 'k':
            tot += M.em(x['t'], 'key') * 0.88 + 0.62        # pill padding
        else:
            tot += M.em(x['t'], 'emo') * 1.22 + 0.2
    return tot + GAP * (len(spec) - 1) + 0.1


def group_caps(W, M):
    groups, cur = [], []

    def flush():
        nonlocal cur
        if cur:
            groups.append(cur)
            cur = []

    def fits(g):
        return spec_em(M, classify(g)) * 1.1 <= CAP_W / 64        # keep >= ~70 px

    for w in W:
        if cur and w['s'] - cur[-1]['e'] > 0.55:
            flush()
        if cur and (not fits(cur + [w]) or len(cur) >= 5):
            carry = []
            while len(cur) > 1 and cur[-1]['n'] in STOP:     # no dangling prepositions at the end of a caption
                carry.insert(0, cur.pop())
            flush()
            cur = carry
        cur.append(w)
        end = w['raw'][-1] in '.?!' or (w['raw'][-1] == ',' and len(cur) >= 2)
        if end:
            flush()
    flush()
    # 1) trailing stop words move to the next caption (no dangling prepositions)
    for i in range(len(groups) - 1):
        g, nx = groups[i], groups[i + 1]
        while len(g) > 1 and g[-1]['n'] in STOP and g[-1]['raw'][-1] not in '.?!' and nx[0]['s'] - g[-1]['e'] < 1.0 and fits([g[-1]] + nx):
            nx.insert(0, g.pop())
    # 2) orphans: a single word joins the previous caption of the same sentence when it fits
    out = []
    for g in groups:
        if out and len(g) == 1 and out[-1][-1]['raw'][-1] not in '.?!' and g[0]['s'] - out[-1][-1]['e'] < 0.5 and fits(out[-1] + g):
            out[-1] = out[-1] + g
        else:
            out.append(g)
    return out


def build_caps(fonts_dir):
    M = Meas(fonts_dir)
    W = load_words()
    gl = group_caps(W, M)
    caps = []
    prev_end = True
    for i, g in enumerate(gl):
        s, e = g[0]['s'], g[-1]['e'] + 0.2
        if i + 1 < len(gl):
            e = min(e, gl[i + 1][0]['s'] - 0.02)
        if s < HOOK_T1 and e <= HOOK_T1 + 0.1:
            prev_end = g[-1]['raw'][-1] in '.?!'
            continue
        if s < HOOK_T1:
            s = HOOK_T1
        if e - s < 0.28:
            e = s + 0.28
        spec = cased(classify(g), prev_end)
        prev_end = g[-1]['raw'][-1] in '.?!'
        em = spec_em(M, spec)
        size = min(CAP_MAX, CAP_W / em)
        first = any(0 <= g[0]['s'] - t < 0.3 for t in IDEAS)
        if first:
            size = min(CAP_MAX * 1.1, CAP_W / em, size * 1.1)
        big = any(x['t'].lower() == 'бесплатна' for x in spec)
        caps.append({'s': round(s, 2), 'e': round(e, 2), 'w': spec, 'size': int(size), 'first': bool(first), 'big': big})
    return caps


# ---------------------------------------------------------------- camera (about a smoothed face centre; flat on laptop shots / whips)
def zoom_at(t):
    for (t0, z0), (t1, z1) in zip(ZK, ZK[1:]):
        if t0 <= t <= t1:
            u = (t - t0) / (t1 - t0) if t1 > t0 else 1
            u = u * u * (3 - 2 * u)
            return z0 + (z1 - z0) * u
    return ZK[-1][1]


def cam_path(face, step=0.1):
    bounds = [0.0] + CUTS + [999.0]
    ft = [(r['t'], r['f']) for r in face if r['f']]
    out = []
    for si in range(len(bounds) - 1):
        t0, t1 = bounds[si], min(bounds[si + 1], DUR + 0.2)
        if t0 >= DUR + 0.2:
            break
        pts = [(t, f[0]) for t, f in ft if t0 - 0.1 <= t < t1 + 0.1]
        cx = None
        tt = t0
        while tt < t1 - 1e-6:
            near = [c for t, c in pts if abs(t - tt) <= 0.6]
            tgt = sum(near) / len(near) if near else 0.5
            tgt = min(max(tgt, 0.40), 0.60)
            cx = tgt if cx is None else cx + (tgt - cx) * (1 - math.exp(-step / 0.6))
            z = zoom_at(tt)
            z = min(ZMAX, z)
            ay = ANCHOR_Y
            wx = cx * (1 - 1 / z)
            wy = ay * (1 - 1 / z)
            out.append([round(tt, 3), round(z, 4), round(-wx * 1080 * z, 1), round(-wy * 1920 * z, 1)])
            tt += step
        out.append([round(t1 - 0.001, 3), out[-1][1], out[-1][2], out[-1][3]])
    return sorted(out, key=lambda r: r[0])


def hits():
    h = [[x['t'], x['amp'], x['punch']] for x in HOOK]
    for c in INSERTS:
        h.append([round(c['t'] + 0.08, 2), 6, 0.0])
    return h


def audio_events():
    """[(t, sample, dB-vs-voice-peak or None)] — every cue the mix needs"""
    ev = [(x['t'], x['sfx'], None) for x in HOOK]
    for c in INSERTS:
        ev += c['sfx']
    ev += FINAL['sfx']
    return sorted(ev)

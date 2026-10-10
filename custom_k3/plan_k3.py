#!/usr/bin/env python3
"""K3 plan (hard, masculine, editorial): shared data for build_k3.py (video) and mix_k3.py (audio).
Palette: black, bone white, ONE accent (cold steel). Condensed heavy type, hard scale-snaps, 4 inserts only, deep sound."""
import json, math, re
from pathlib import Path

HERE = Path(__file__).resolve().parent
DUR = 84.3

# real cuts in the footage; the close-up part (from 27.67 s) frames the head lower, so its camera anchors higher up
CUTS = [5.53, 13.23, 16.13, 22.1, 27.67]
CLOSE_FROM = 27.6
# reframes every 3-6 s: slow push-ins, then a hard step to a new framing (two keys 0.01 s apart = a jump)
ZK = [(0.0, 1.00), (2.45, 1.13), (2.46, 1.18), (5.52, 1.22), (5.53, 1.00),
      (8.4, 1.12), (8.41, 1.17), (10.15, 1.20), (10.16, 1.05), (13.2, 1.16), (13.23, 1.00),
      (16.12, 1.10), (16.13, 1.00), (19.0, 1.10), (19.01, 1.17), (22.08, 1.22), (22.1, 1.00),
      (24.9, 1.12), (24.91, 1.17), (27.66, 1.21), (27.67, 1.00),
      (31.4, 1.07), (31.41, 1.00), (35.2, 1.09), (35.21, 1.13), (39.3, 1.09), (39.31, 1.00), (43.4, 1.08), (43.41, 1.12),
      (47.0, 1.06), (47.01, 1.00), (50.8, 1.09), (50.81, 1.13), (54.5, 1.08), (54.51, 1.00), (58.4, 1.08), (58.41, 1.12),
      (62.6, 1.14), (62.61, 1.00), (66.4, 1.08), (66.41, 1.12), (70.2, 1.07), (70.21, 1.00), (74.0, 1.09), (74.01, 1.12),
      (77.8, 1.08), (77.81, 1.00), (81.2, 1.08), (81.21, 1.12), (84.3, 1.16)]
ZMAX = 1.22
ANCHOR_Y, ANCHOR_CLOSE = 0.30, 0.12

# ---------------------------------------------------------------- hook (picked A) + alternatives, only the speaker's real words
HOOK_ALTS = [
    ('A (picked)', 'Я ЗВОНЮ БИЗНЕСМЕНАМ / ОНИ НЕ СЛЫШАТ / ЧТО МНЕ 15 ЛЕТ', 'said 0.0-3.2 s: «когда я звоню бизнесменам, они не слышат, что мне 15 лет»'),
    ('B', 'Я ДЕЛАЮ / ВЗРОСЛЫЙ / ГОЛОС', 'said at 3.5-5.3 s'),
    ('C', 'ЕМУ ВАЖНО ОДНО / ЗАРАБОТАТЬ / БОЛЬШЕ ИЛИ НЕТ', 'said at 11.5-15.4 s'),
]
HOOK = [
    {'text': 'Я ЗВОНЮ БИЗНЕСМЕНАМ', 'cls': 'h1', 't': 0.20, 'font': 'h1', 'size': 120, 'y': 1300, 'amp': 11, 'punch': 0.03, 'sfx': 'impact_deep'},
    {'text': 'ОНИ НЕ СЛЫШАТ', 'cls': 'h2', 't': 0.62, 'font': 'h2', 'size': 150, 'y': 1465, 'amp': 15, 'punch': 0.05, 'sfx': 'metal_hit'},
    {'text': 'ЧТО МНЕ 15 ЛЕТ', 'cls': 'h3', 't': 1.04, 'font': 'h3', 'size': 128, 'y': 1640, 'amp': 13, 'punch': 0.04, 'sfx': 'boom_low'},
]
HOOK_T0, HOOK_EXIT, HOOK_T1 = 0.10, 2.45, 2.70

# ---------------------------------------------------------------- inserts (4). sfx = (time, name, dB vs voice peak or None)
INSERTS = [
    {'n': 1, 'kind': 'wave', 't': 4.55, 'e': 6.00, 'in': 'flash', 'out': 'cut', 'what': 'thin steel waveform line for «взрослый голос»',
     'sfx': [(4.50, 'sub_drop', None)]},
    {'n': 2, 'kind': 'stock', 'src': 8426053, 'ss': 2.0, 'crop': 0.62, 'sat': 0.35, 't': 13.78, 'e': 15.50, 'in': 'cut', 'out': 'flash',
     'what': 'stock: close-up handshake (Pexels 8426053), full-frame zoom-through, for «заработать больше»',
     'sfx': [(12.70, 'riser', -13), (13.78, 'impact_deep', None), (15.45, 'whip', -13)]},
    {'n': 3, 'kind': 'punch', 'text': 'ОФФЕР', 't': 23.50, 'e': 24.65, 'in': 'snap', 'out': 'cut', 'what': 'type punch «ОФФЕР» with steel rules for «конкретный оффер»',
     'sfx': [(23.50, 'metal_hit', None)]},
    {'n': 4, 'kind': 'stock', 'src': 30084927, 'ss': 0.5, 'crop': 0.70, 'sat': 0.45, 't': 61.05, 'e': 62.60, 'in': 'whip', 'out': 'cut',
     'what': 'stock: dark alarm clock (Pexels 30084927), full-frame zoom-through, for «надо в 6 утра»',
     'sfx': [(60.30, 'riser', -13), (61.05, 'impact_deep', None), (62.55, 'tick_low', -13)]},
]
FINAL = {'t': 82.40, 'sfx': [(82.44, 'impact_deep', None)]}                    # «бесплатна»: big steel key word + one deep hit

# ---------------------------------------------------------------- caption system (3 Cyrillic styles)
CAP_Y, CAP_MAX, CAP_W, GAP = 1545, 96, 940, 0.20
FONTS = {'base': ('oswald-{sc}-600-normal', 0.0), 'key': ('roboto-condensed-{sc}-800-normal', 0.0), 'emo': ('russo-one-{sc}-400-normal', 0.0),
         'h1': ('oswald-{sc}-700-normal', 0.0), 'h2': ('russo-one-{sc}-400-normal', 0.0), 'h3': ('roboto-condensed-{sc}-800-normal', 0.0)}
KEYS = {'бизнесменам', 'бизнесмену', '15', 'взрослый', 'голос', 'одно', 'заработать', 'больше', 'конкретики', 'оффер', 'продавать', 'предложить',
        'отрыв', '4', 'тысяч', 'воскресенье', 'утром', '9', '6', '8', 'номер', 'качество', 'бесплатна', 'демоверсия', 'клиника', 'ПроДент',
        'слова', 'возраст', 'записали', 'проигнорировали', 'лучше', 'каждого', 'гигиена', 'смотрите'}
EMO_NEG = {'наплевать', 'нет', 'поздно'}
EMO_POS = {'идеально'}
NUMS = {'4', '9', '6', '8', '15'}
IDEAS = []
STOP = {'в', 'с', 'к', 'и', 'а', 'о', 'у', 'на', 'по', 'до', 'не', 'от', 'за', 'из', 'бы', 'ли', 'же', 'или', 'но', 'то', 'вот', 'я', 'мне', 'мы', 'ваш', 'для', 'что', 'это', 'как', 'очень', 'ты', 'тебе', 'он', 'ему', 'они', 'меня', 'а'}


def load_words():
    segs = json.loads((HERE / 'data' / 'words_k3.json').read_text(encoding='utf-8'))
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
        for ch in text.upper():
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
            spec.append({'t': w['t'], 'cls': 'e', 'col': '', 's': w['s']})
        elif i == hi:
            spec.append({'t': w['t'], 'cls': 'k', 'col': '', 's': w['s']})
        else:
            spec.append({'t': w['t'], 'cls': 'n', 'col': '', 's': w['s']})
    return spec


def spec_em(M, spec):
    tot = 0.0
    for x in spec:
        if x['cls'] == 'n':
            tot += M.em(x['t'], 'base')
        elif x['cls'] == 'k':
            tot += M.em(x['t'], 'key') * 1.08
        else:
            tot += M.em(x['t'], 'emo') * 1.05
    return tot + GAP * (len(spec) - 1) + 0.1


def group_caps(W, M):
    groups, cur = [], []

    def flush():
        nonlocal cur
        if cur:
            groups.append(cur)
            cur = []

    def fits(g):
        return spec_em(M, classify(g)) * 1.1 <= CAP_W / 64

    for w in W:
        if cur and w['s'] - cur[-1]['e'] > 0.55:
            flush()
        if cur and (not fits(cur + [w]) or len(cur) >= 5):
            carry = []
            while len(cur) > 1 and cur[-1]['n'] in STOP:
                carry.insert(0, cur.pop())
            flush()
            cur = carry
        cur.append(w)
        end = w['raw'][-1] in '.?!' or (w['raw'][-1] == ',' and len(cur) >= 2)
        if end:
            flush()
    flush()
    for i in range(len(groups) - 1):
        g, nx = groups[i], groups[i + 1]
        while len(g) > 1 and g[-1]['n'] in STOP and g[-1]['raw'][-1] not in '.?!' and nx[0]['s'] - g[-1]['e'] < 1.0 and fits([g[-1]] + nx):
            nx.insert(0, g.pop())
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
    for i, g in enumerate(gl):
        s, e = g[0]['s'], g[-1]['e'] + 0.2
        if i + 1 < len(gl):
            e = min(e, gl[i + 1][0]['s'] - 0.02)
        if s < HOOK_T1 and e <= HOOK_T1 + 0.1:
            continue
        if s < HOOK_T1:
            s = HOOK_T1
        if e - s < 0.28:
            e = s + 0.28
        spec = classify(g)
        em = spec_em(M, spec)
        size = min(CAP_MAX, CAP_W / em)
        big = any(x['t'].lower() == 'бесплатна' for x in spec)
        caps.append({'s': round(s, 2), 'e': round(e, 2), 'w': spec, 'size': int(size), 'first': False, 'big': big})
    return caps


# ---------------------------------------------------------------- camera (about a smoothed face centre)
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
            tgt = min(max(tgt, 0.42), 0.58)
            cx = tgt if cx is None else cx + (tgt - cx) * (1 - math.exp(-step / 0.6))
            z = min(ZMAX, zoom_at(tt))
            ay = ANCHOR_CLOSE if t0 >= CLOSE_FROM else ANCHOR_Y
            wx = cx * (1 - 1 / z)
            wy = ay * (1 - 1 / z)
            out.append([round(tt, 3), round(z, 4), round(-wx * 1080 * z, 1), round(-wy * 1920 * z, 1)])
            tt += step
        out.append([round(t1 - 0.001, 3), out[-1][1], out[-1][2], out[-1][3]])
    return sorted(out, key=lambda r: r[0])


def hits():
    h = [[x['t'], x['amp'], x['punch']] for x in HOOK]
    for c in INSERTS:
        h.append([round(c['t'] + 0.02, 2), 9 if c['kind'] != 'wave' else 7, 0.02])
    h.append([FINAL['t'] + 0.04, 10, 0.03])
    return h


def audio_events():
    """[(t, sample, dB-vs-voice-peak or None)] — every cue the mix needs"""
    ev = [(x['t'], x['sfx'], None) for x in HOOK]
    for c in INSERTS:
        ev += c['sfx']
    ev += FINAL['sfx']
    return sorted(ev)

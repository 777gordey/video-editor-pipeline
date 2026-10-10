#!/usr/bin/env python3
"""K1 plan: shared data for build_k1.py (video) and mix_k1.py (audio). Direction C: proof + numbers + UI cards (top band), captions below the chin."""
import json, math, re
from pathlib import Path

HERE = Path(__file__).resolve().parent
DUR = 59.5

# ---------------------------------------------------------------- footage shot map (real cuts / whip-pans in the clip)
CUTS = [2.5, 3.2, 3.5, 5.0, 5.2, 6.0, 6.4, 6.8, 7.0, 15.6, 16.0, 18.3, 18.5, 45.7, 54.33, 55.1, 55.9, 57.3]
NOFACE = [(3.2, 5.2), (6.0, 7.0), (15.6, 18.5), (45.6, 46.0)]       # whips / laptop shots: camera stays flat there

# camera zoom keys (t, z): real moves 1.00-1.22 on face shots only; anchored near the top so the head is never cropped
ZK = [(0.0, 1.00), (2.5, 1.00), (2.6, 1.02), (3.1, 1.10), (3.2, 1.00), (5.2, 1.00), (5.9, 1.14), (6.0, 1.00), (7.0, 1.00),
      (9.2, 1.00), (9.55, 1.20), (10.9, 1.20), (11.9, 1.04), (13.5, 1.04), (15.4, 1.14), (15.6, 1.00), (18.5, 1.00),
      (19.3, 1.00), (21.6, 1.10), (22.8, 1.10), (23.4, 1.00), (25.9, 1.00), (26.9, 1.10), (28.6, 1.10), (29.4, 1.00),
      (34.5, 1.00), (34.85, 1.12), (36.8, 1.12), (37.9, 1.06), (39.6, 1.00), (43.35, 1.00), (43.65, 1.12),
      (45.4, 1.12), (45.7, 1.00), (47.9, 1.00), (48.6, 1.00), (49.4, 1.16), (50.5, 1.16), (50.95, 1.02), (54.3, 1.02), (54.34, 1.00),
      (57.2, 1.00), (59.5, 1.08)]
ZMAX = 1.22
ANCHOR_Y = 0.30      # zoom is about y = 30 % of the frame (hair stays clear of the top, mouth stays above the captions)

# ---------------------------------------------------------------- hook (picked A) + alternatives
HOOK_ALTS = [
    ('A (picked)', 'смотри, / КАК ОТВЕЧАЮТ / МОИ АГЕНТЫ', 'said at 0.0-2.5 s: «смотри, как отвечают мои агенты»'),
    ('B', 'ДЕМО / БЕСПЛАТНО / ДЛЯ КАЖДОГО', 'said at 57-59 s: «демоверсия бесплатна для каждого», payoff first'),
    ('C', 'В 6 УТРА? / КЛИНИКА ЕЩЁ / НЕ РАБОТАЕТ', 'said at 36-41 s: the joke up front'),
]
HOOK = [
    {'text': 'смотри,', 'cls': 'h1', 't': 0.20, 'font': 'lora', 'size': 112, 'y': 1400, 'amp': 9, 'punch': 0.03, 'sfx': 'click_hi'},
    {'text': 'КАК ОТВЕЧАЮТ', 'cls': 'h2', 't': 0.58, 'font': 'unbounded', 'size': 104, 'y': 1535, 'amp': 15, 'punch': 0.05, 'sfx': 'boom_soft'},
    {'text': 'МОИ АГЕНТЫ', 'cls': 'h3', 't': 0.98, 'font': 'mono', 'size': 112, 'y': 1700, 'amp': 11, 'punch': 0.04, 'sfx': 'ping_confirm'},
]
HOOK_T0, HOOK_EXIT, HOOK_T1 = 0.10, 2.28, 2.56

# ---------------------------------------------------------------- UI inserts (cards in the top band, y 64-304, never over eyes/mouth)
# kind -> built in scene_k1.js; sfx = (time, name, dB vs voice peak or None)
INSERTS = [
    {'n': 1, 'kind': 'call', 't': 3.55, 'e': 7.55, 'what': 'incoming call «ПроДент · клиника», timer, voice bars: agent picks up and greets',
     'sfx': [(3.50, 'card_in', None), (3.52, 'phone_ring', -12), (3.80, 'pickup', None), (7.45, 'card_out', None)]},
    {'n': 2, 'kind': 'price', 't': 15.90, 'e': 18.55, 'what': 'price counter 0 -> от 4 000 ₽ for «от 4 тысяч рублей»',
     'sfx': [(15.88, 'card_in', None)] + [(16.12 + 0.085 * i, 'tick_b', -12) for i in range(10)] + [(16.98, 'coin', None), (18.35, 'card_out', None)]},
    {'n': 3, 'kind': 'pick', 't': 20.85, 'e': 27.60, 'what': 'day strip (ВС selected) then УТРОМ / ВЕЧЕРОМ choice',
     'sfx': [(20.82, 'card_in', None), (21.14, 'select_b', None), (24.72, 'switch_a', None), (26.70, 'select_b', None), (27.40, 'card_out', None)]},
    {'n': 4, 'kind': 'wheel', 't': 32.45, 'e': 44.70, 'what': 'THE JOKE: time wheel 9:00 -> 6:00, red «КЛИНИКА ЕЩЁ НЕ РАБОТАЕТ», -> 8:00, green «ЗАПИСАНО»',
     'sfx': [(32.42, 'card_in', None), (32.78, 'tick_a', None)] + [(37.00 + 0.09 * i, 'tick_b', -12) for i in range(6)] + [(37.62, 'alarm_short', -12), (40.30, 'err_a', None),
             (42.95, 'tick_a', None), (43.15, 'tick_a', None), (43.35, 'tick_a', None), (44.00, 'ok_a', None), (44.48, 'card_out', None)]},
    {'n': 5, 'kind': 'compare', 't': 51.25, 'e': 54.60, 'what': 'proof: «проигнорировали» ✗ vs «ответили и записали» ✓',
     'sfx': [(51.22, 'card_in', None), (52.62, 'err_b', -10), (53.95, 'ok_b', None), (54.40, 'card_out', None)]},
]
FINAL = {'t': 57.64, 'sfx': [(57.70, 'ok_c', None)]}                  # «бесплатна»: big key tag in the captions, one ping
HIT_EXTRA = [(0.2, 0, 0)]  # placeholder, not used


# ---------------------------------------------------------------- caption system
CAP_Y, CAP_MAX, CAP_W, GAP = 1500, 84, 940, 0.30
FONTS = {'manrope': ('manrope-{sc}-800-normal', -0.01), 'mono': ('jetbrains-mono-{sc}-800-normal', -0.02), 'lora': ('lora-{sc}-700-italic', 0.0), 'unbounded': ('unbounded-{sc}-900-normal', 0.0)}
KEYS = {'агенты', 'клиника', 'проДент', 'ПроДент', '4', 'тысяч', 'воскресенье', 'утром', '9', '6', '8', 'часов', 'номер', 'качество', 'бесплатна',
        'демоверсия', 'каждый', 'гигиена', 'записали', 'приём', 'телефона', 'проигнорировали', 'ответили', 'лучше', 'отвечают'}
EMO_NEG = {'поздно', 'нет', 'проигнорировали'}
EMO_POS = {'идеально', 'приятно', 'привет', 'миланочка', 'чисточку', 'самолётик', 'хорошо'}
NUMS = {'4', '9', '6', '8'}
IDEAS = [2.6, 3.76, 7.98, 13.56, 17.22, 19.34, 23.02, 29.38, 34.56, 39.74, 43.4, 46.06, 47.98, 51.32, 55.72]
STOP = {'в', 'с', 'к', 'и', 'а', 'о', 'у', 'на', 'по', 'до', 'не', 'от', 'за', 'из', 'бы', 'ли', 'же', 'или', 'но', 'то', 'вот', 'я', 'мне', 'мы', 'ваш', 'для', 'что', 'это', 'как', 'очень'}


def load_words():
    segs = json.loads((HERE / 'data' / 'words_k1.json').read_text(encoding='utf-8'))
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

    def em(self, text, font='manrope'):
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
            tot += M.em(x['t'], 'manrope')
        elif x['cls'] == 'k':
            tot += M.em(x['t'], 'mono') * 0.88 + 0.62        # pill padding
        else:
            tot += M.em(x['t'], 'lora') * 1.22 + 0.2
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
            ay = 0.0 if tt < 2.5 else ANCHOR_Y          # first shot: hair already touches the top edge, so anchor at the very top
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

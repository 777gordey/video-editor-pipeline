#!/usr/bin/env python3
"""Round 5 composition builder: ONE HyperFrames project for a time range of the clip (no cuts, no speed change, no cut-out, no overlays on the room).
usage: build2.py --a 0 --b 26 --out proj --clip range.mp4 --cutdir DIR [--fonts DIR --gsap FILE --data DIR]
Data (words_2.json, face_track.json) live next to this script unless --data is given."""
import argparse, json, math, re, shutil
from pathlib import Path
from fontTools.ttLib import TTFont

HERE = Path(__file__).resolve().parent
CUTS = [5.73, 7.53, 12.17, 15.3, 17.93, 21.1, 25.0, 25.6, 38.5, 41.1, 68.1]  # jump cuts that already exist in the clip

# ---------------------------------------------------------------- camera: 1.00-1.26, alternating wide / close, eased
ZK = [(0.0, 1.00), (2.2, 1.16), (3.4, 1.16), (4.4, 1.04), (5.4, 1.26), (7.3, 1.05), (8.6, 1.05), (10.9, 1.25), (12.0, 1.25), (12.9, 1.03),
      (13.3, 1.03), (15.2, 1.20), (16.2, 1.03), (17.8, 1.26), (19.7, 1.06), (20.6, 1.24), (21.7, 1.03), (22.7, 1.05), (24.5, 1.20), (25.9, 1.03),
      (31.0, 1.06), (33.2, 1.24), (35.3, 1.24), (36.6, 1.03), (38.6, 1.03), (40.4, 1.18), (41.6, 1.22), (43.0, 1.22), (44.3, 1.03), (47.9, 1.03),
      (49.0, 1.24), (50.5, 1.24), (51.6, 1.05), (54.8, 1.08), (55.9, 1.24), (57.0, 1.24), (58.9, 1.10), (60.6, 1.26), (61.4, 1.26), (62.4, 1.04),
      (64.2, 1.04), (66.0, 1.24), (67.6, 1.24), (68.6, 1.03), (71.6, 1.12)]
ZMAX = 1.26

# ---------------------------------------------------------------- hook: three separate hits, three different fonts
HOOK_ALTS = [
    ('A (picked)', 'ПРОВЕРИТЬ МАСТЕРА? / НЕЛЬЗЯ. / только кто быстрее', 'setup: «не может проверить, где мастер лучше» -> twist: «нельзя» -> payoff: «он проверяет одно: где ответили быстрее»'),
    ('B', 'ОДНО / ПРОВЕРЯЕТ КЛИЕНТ: / кто ответил быстрее', 'setup «одно» -> «проверяет» -> payoff'),
    ('C', 'КЛИЕНТ НЕ ВИДИТ, / КТО ЛУЧШЕ. / Видит — кто быстрее', 'plain setup/twist, longer'),
]
HOOK = [  # t = landing time of the hit (global s), font = style, maxsize = px cap
    {'text': 'ПРОВЕРИТЬ МАСТЕРА?', 'font': 'onest', 'cls': 'h1', 't': 0.20, 'maxsize': 90, 'amp': 14, 'punch': 0.05},
    {'text': 'НЕЛЬЗЯ.', 'font': 'oswald', 'cls': 'h2', 't': 0.62, 'maxsize': 250, 'amp': 18, 'punch': 0.06},
    {'text': 'только кто быстрее', 'font': 'playfair', 'cls': 'h3', 't': 1.04, 'maxsize': 112, 'amp': 22, 'punch': 0.08},
]
HOOK_T0, HOOK_EXIT, HOOK_T1 = 0.12, 1.86, 2.16   # last line lands 1.04, holds ~0.8 s, exits fast

# ---------------------------------------------------------------- inserts (stock-video cards + comic callouts). Pexels: free for commercial use, fetched at render time, never committed.
CARDS = {'land': {'w': 960, 'h': 720, 'x': 60, 'y': 430}, 'port': {'w': 720, 'h': 900, 'x': 180, 'y': 330}}
INSERTS = [
    {'n': 1, 'kind': 'card', 'shape': 'land', 't': 5.50, 'e': 7.30, 'pexels': 8625399, 'ss': 4.6, 'co': {'kind': 'burst', 'text': 'ИГОГО!', 'at': 'tr', 'dt': 0.55, 'rot': -9},
     'sfx': [(5.62, 'horse_neigh', -6)], 'what': 'trotting horse for «копыта» + comic «ИГОГО!»'},
    {'n': 2, 'kind': 'card', 'shape': 'land', 't': 13.40, 'e': 15.20, 'pexels': 38057445, 'ss': 4.0, 'co': {'kind': 'bubble', 'text': 'ЧАСТЬ УСЛУГИ', 'at': 'bl', 'dt': 0.45, 'rot': -3},
     'sfx': [(13.85, 'ding_chime', None)], 'what': 'reception handshake for «первая часть услуги»'},
    {'n': 3, 'kind': 'card', 'shape': 'land', 't': 17.90, 'e': 19.70, 'pexels': 7685810, 'ss': 8.0, 'co': {'kind': 'stamp', 'text': 'ПОКА!', 'at': 'tr', 'dt': 0.95, 'rot': 8, 'slam': True},
     'sfx': [(18.85, 'boom_low', None)], 'what': 'customer walking out of the door for «вернётся или нет?» + slammed «ПОКА!»'},
    {'n': 4, 'kind': 'card', 'shape': 'port', 't': 22.70, 'e': 24.50, 'pexels': 7346566, 'ss': 5.3, 'co': {'kind': 'burst', 'text': 'ДЗЫНЬ!', 'at': 'tl', 'dt': 0.55, 'rot': -8},
     'sfx': [(22.95, 'phone_ring', None)], 'what': 'a hand picks up a phone for «с первого гудка» + «ДЗЫНЬ!»'},
    {'n': 5, 'kind': 'card', 'shape': 'port', 't': 38.60, 'e': 40.40, 'pexels': 3827385, 'ss': 0.3, 'co': {'kind': 'bubble', 'text': 'ОТ 4 000 РУБ.', 'at': 'bl', 'dt': 0.5, 'rot': -3},
     'sfx': [(38.85, 'coin', None)], 'what': 'laughing under falling cash for «от 4 тысяч рублей»'},
    {'n': 6, 'kind': 'card', 'shape': 'port', 't': 58.90, 'e': 60.60, 'pexels': 7593912, 'ss': 1.2, 'co': {'kind': 'burst', 'text': '6:00?!', 'at': 'tr', 'dt': 0.5, 'rot': 8},
     'sfx': [(59.0, 'alarm_short', -12)], 'what': 'waking up to an alarm for «мне надо в 6 утра»'},
    {'n': 7, 'kind': 'stop', 't': 62.60, 'e': 64.20, 'co': {'kind': 'stop', 'text': 'СТОП', 'dt': 0.0, 'rot': -8, 'slam': True},
     'sfx': [(62.62, 'stop_slam', -8), (62.62, 'boom_low', -11)], 'what': 'STOP sign slam for «клиника ещё не работает»'},
]
CALLOUTS = [  # callouts on the plain footage (slot chosen from the face track, never over eyes/mouth)
    {'t': 31.00, 'e': 32.60, 'kind': 'bubble', 'text': 'ПРИВЕТ!', 'rot': -4, 'sfx': [(31.02, 'pop_bubble', None)]},
    {'t': 66.40, 'e': 68.00, 'kind': 'burst', 'text': 'ИДЕАЛЬНО!', 'rot': 7, 'sfx': [(66.45, 'ding_glass', None)]},
]
TRANS = [{'t': 12.15, 'type': 'sweep'}, {'t': 21.05, 'type': 'flare'}, {'t': 25.10, 'type': 'push'}, {'t': 45.85, 'type': 'sweep'},
         {'t': 51.65, 'type': 'flare'}, {'t': 68.55, 'type': 'push'}] + \
        [{'t': c[k], 'type': 'zoom', 'cut': c['n']} for c in INSERTS if c['kind'] == 'card' for k in ('t', 'e')]
TRANS.sort(key=lambda x: x['t'])

# ---------------------------------------------------------------- caption system (3 fonts, 3 accents; rules in classify())
IDEAS = [6.3, 12.3, 15.6, 21.0, 25.2, 36.4, 45.9, 51.7, 56.9, 62.4, 68.7]   # first phrase of a new idea is bigger
EMO = {'плохо', 'поздно', 'нет', 'копыта', 'идеально', 'вернется'}            # italic serif, tilted
NEG = {'плохо', 'поздно', 'нет', 'копыта'}                                    # coral
NUM = {'4', '9', '6', '8', 'тысяч'}                                           # cyan
KEY = {'быстрее', 'скорость', 'тон', 'единственное', 'визита', 'первая', 'услуги', 'гудка', 'секунды', 'клиент', 'системы', 'воскресенье', 'утром',
       'телефона', 'качество', 'ближайший', 'чисточку', 'гигиена', 'ответили'}  # lime, condensed
STOP = {'в', 'с', 'к', 'и', 'а', 'о', 'у', 'на', 'по', 'до', 'не', 'от', 'за', 'из', 'бы', 'ли', 'же', 'или', 'но', 'то', 'вот'}
FIX = {'проден': 'ПроДент', 'миланов': 'Милана', 'гуд': None}
CAP_Y, CAP_MAX, CAP_W, GAP = 1450, 88, 960, 0.5
KSCALE, ESCALE = 1.28, 1.24

FONTS = {'onest': ('onest-{sc}-900-normal', -0.022), 'oswald': ('oswald-{sc}-700-normal', 0.01), 'playfair': ('playfair-display-{sc}-900-italic', -0.01)}


class Meas:
    def __init__(self, fd):
        self.f = {}
        for k, (pat, ls) in FONTS.items():
            self.f[k] = [(lambda t: (t.getBestCmap(), t['hmtx'], t['head'].unitsPerEm))(TTFont(Path(fd) / (pat.format(sc=sc) + '.woff2'))) for sc in ('cyrillic', 'latin')]

    def em(self, text, font='onest'):
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


def load_words(path):
    segs = json.loads(Path(path).read_text(encoding='utf-8'))
    out = []
    for s in segs:
        for w in s['words']:
            raw = w['w']
            n = re.sub(r'[^\w]', '', raw.lower())
            if n in FIX:
                if FIX[n] is None:
                    continue
                t = FIX[n]
            else:
                t = re.sub(r'[.,!?]+$', '', raw)
            out.append({'raw': raw, 't': t, 'n': n, 's': w['s'], 'e': w['e']})
    return out


def classify(g):
    """Rules: one highlighted word per phrase. emotional (italic serif, tilted, coral) > number (condensed, cyan) > key (condensed, lime)."""
    hi, kind = None, None
    for pri in ('e', 'n', 'k'):
        for i, w in enumerate(g):
            n = w['n']
            if (pri == 'e' and n in EMO) or (pri == 'n' and n in NUM) or (pri == 'k' and n in KEY):
                hi, kind = i, pri
                break
        if hi is not None:
            break
    spec = []
    for i, w in enumerate(g):
        if i == hi:
            if kind == 'e':
                spec.append({'t': w['t'].lower(), 'cls': 'e', 'col': 'coral' if w['n'] in NEG else 'lime', 's': w['s']})
            elif kind == 'n':
                spec.append({'t': w['t'], 'cls': 'k', 'col': 'cyan', 's': w['s']})
            else:
                spec.append({'t': w['t'], 'cls': 'k', 'col': 'lime', 's': w['s']})
        else:
            spec.append({'t': w['t'], 'cls': 'n', 'col': '', 's': w['s']})
    return spec


def group_caps(W, M):
    groups, cur = [], []

    def flush():
        nonlocal cur
        if cur:
            groups.append(cur)
            cur = []

    def width(g):
        return sum(M.em(x['t'].upper()) for x in g) + GAP * (len(g) - 1) + 0.1

    for w in W:
        if cur and w['s'] - cur[-1]['e'] > 0.6:
            flush()
        if cur and width(cur + [w]) * 1.12 > CAP_W / 78:      # keep >= ~78 px even for long words
            carry = []
            while len(cur) > 1 and cur[-1]['n'] in STOP:
                carry.insert(0, cur.pop())
            flush()
            cur = carry
        cur.append(w)
        end = w['raw'][-1] in '.?!' or (w['raw'][-1] == ',' and len(cur) >= 2) or len(cur) >= 3 or sum(len(x['t']) + 1 for x in cur) > 20
        if end:
            carry = []
            while len(cur) > 2 and cur[-1]['n'] in STOP and cur[-1]['raw'][-1] not in '.?!':
                carry.insert(0, cur.pop())
            flush()
            cur = carry
    flush()
    return groups


def spec_em(M, spec):
    tot = 0.0
    for x in spec:
        if x['cls'] == 'n':
            tot += M.em(x['t'].upper())
        elif x['cls'] == 'k':
            tot += M.em(x['t'].upper(), 'oswald') * KSCALE + 0.2
        else:
            tot += M.em(x['t'], 'playfair') * ESCALE + 0.2
    return tot + GAP * (len(spec) - 1) + 0.1


# ---------------------------------------------------------------- camera
def cam_path(face, a, b, step=0.1):
    """[(t, z, tx, ty, face_state)] — face-centred, eased, smoothed per cut-free segment; never crops the top of the head."""
    bounds = [0.0] + CUTS + [999.0]
    ft = [(r['t'], r['f']) for r in face]

    def zoom(t):
        for i in range(len(ZK) - 1):
            (t0, z0), (t1, z1) = ZK[i], ZK[i + 1]
            if t0 <= t <= t1:
                u = (t - t0) / (t1 - t0)
                u = u * u * (3 - 2 * u)
                return z0 + (z1 - z0) * u
        return ZK[-1][1]

    def face_at(t0, t1, tt):
        pts = [(t, f) for t, f in ft if f and t0 - 0.15 <= t < t1 + 0.15]
        if not pts:
            return None
        if tt <= pts[0][0]:
            return pts[0][1]
        for i in range(len(pts) - 1):
            if pts[i][0] <= tt <= pts[i + 1][0]:
                u = (tt - pts[i][0]) / (pts[i + 1][0] - pts[i][0])
                return [pts[i][1][j] + (pts[i + 1][1][j] - pts[i][1][j]) * u for j in range(3)]
        return pts[-1][1]

    out = []
    for si in range(len(bounds) - 1):
        t0, t1 = bounds[si], min(bounds[si + 1], 99.0)
        if t1 <= a - 0.2 or t0 >= b + 0.2:
            continue
        tt, st = t0, None
        end = min(t1, b + 0.2)
        while tt < end - 1e-6:
            f = face_at(t0, t1, tt)
            tgt = (0.5, 0.45, 0.4) if f is None else tuple(f)
            st = list(tgt) if st is None else [st[j] + (tgt[j] - st[j]) * (1 - math.exp(-step / 0.5)) for j in range(3)]
            z = min(ZMAX, zoom(tt) * (1 + 0.008 * math.sin(2 * math.pi * tt / 7.0)))
            wx = min(max(st[0] - 0.5 / z, 0), 1 - 1 / z)
            wy = st[1] - 0.40 / z
            head_top = st[1] - 0.8 * st[2] * 0.5625          # top of the hair, normalised
            wy = min(wy, head_top - 0.02)                    # shift the framing down instead of cropping the head
            wy = min(max(wy, 0), 1 - 1 / z)
            out.append((round(tt, 3), round(z, 4), round(-wx * 1080 * z, 1), round(-wy * 1920 * z, 1), st[:]))
            tt += step
        out.append((round(end - 0.001, 3), out[-1][1], out[-1][2], out[-1][3], st[:]))
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--a', type=float, required=True)
    ap.add_argument('--b', type=float, required=True)
    ap.add_argument('--out', required=True)
    ap.add_argument('--clip', required=True)
    ap.add_argument('--fonts', default=str(HERE / 'fonts'))
    ap.add_argument('--gsap', default=str(HERE.parent / 'src' / 'gsap.min.js'))
    ap.add_argument('--data', default=str(HERE))
    ap.add_argument('--cutdir', default=None, help='dir with cut1.mp4.. (stock segments made by stock.py)')
    a = ap.parse_args()
    D, A, B = Path(a.data), a.a, a.b
    proj = Path(a.out)
    (proj / 'media').mkdir(parents=True, exist_ok=True)
    (proj / 'fonts').mkdir(exist_ok=True)
    for f in Path(a.fonts).glob('*.woff2'):
        if re.match(r'(onest|oswald|playfair-display)-(cyrillic|latin)-', f.name):
            shutil.copy2(f, proj / 'fonts' / f.name)
    shutil.copy2(a.gsap, proj / 'gsap.min.js')
    dst = proj / 'media' / 'clip.mp4'
    if Path(a.clip).resolve() != dst.resolve():
        shutil.copy2(a.clip, dst)
    (proj / 'meta.json').write_text(json.dumps({'id': 'custom-edit-2', 'name': 'custom edit 2'}), encoding='utf-8')
    dur = round(B - A, 3)
    M = Meas(a.fonts)
    face = json.loads((D / 'face_track.json').read_text(encoding='utf-8'))

    # ---- captions
    W = load_words(D / 'words_2.json')
    gl = group_caps(W, M)
    caps = []
    for i, g in enumerate(gl):
        s, e = g[0]['s'], g[-1]['e'] + 0.18
        if i + 1 < len(gl):
            e = min(e, gl[i + 1][0]['s'] - 0.02)
        if s < HOOK_T1 + 0.05 and A <= HOOK_T0:
            if e <= HOOK_T1 + 0.3:
                continue
            s = HOOK_T1 + 0.05
        if e - s < 0.25:
            e = s + 0.25
        spec = classify(g)
        em = spec_em(M, spec)
        size = min(CAP_MAX, CAP_W / em)
        first = any(abs(g[0]['s'] - t) < 0.4 or 0 <= g[0]['s'] - t < 0.4 for t in IDEAS)
        if first:
            size = min(CAP_MAX * 1.12, CAP_W / em, size * 1.12)
        caps.append({'s': round(s, 2), 'e': round(e, 2), 'w': spec, 'size': int(size), 'y': CAP_Y, 'first': bool(first)})

    # ---- camera
    cam = cam_path(face, A, B)
    camrows = sorted([[r[0], r[1], r[2], r[3]] for r in cam], key=lambda r: r[0])

    def screen_face(t):
        best = next((r for r in cam if r[0] >= t), cam[-1])
        z, tx, ty, st = best[1], best[2], best[3], best[4]
        return (tx + z * st[0] * 1080, ty + z * st[1] * 1920, z * st[2] * 1080)

    SLOTS = [(165, 215), (915, 215), (165, 420), (915, 420), (165, 700), (915, 700), (165, 1010), (915, 1010), (540, 190)]

    def pick_slot(t, e, half, last):
        samples = [screen_face(t + (e - t) * u / 4) for u in range(5)]
        sc = []
        for sl in SLOTS:
            clear = 1e9
            for fx, fy, fw in samples:
                dx = max(0, abs(sl[0] - fx) - fw * 0.62 - half)
                dy = max(0, abs(sl[1] - (fy + fw * 0.08)) - fw * 0.5 - half)
                clear = min(clear, math.hypot(dx, dy) if (dx > 0 or dy > 0) else -1)
            sc.append((clear - (60 if sl == last else 0) + (15 if sl[1] < 800 else 0), sl))
        sc.sort(reverse=True)
        return sc[0][1], round(sc[0][0])

    # ---- callouts (comic stickers): measure text, place
    def callout(kind, text, rot, slam=False, dt=0.0):
        em = M.em(text.upper(), 'oswald') if kind != 'bubble' else M.em(text.upper(), 'onest')
        if kind == 'burst':
            d = 340
            fs = int(min(120, d * 0.62 / em))
            return {'kind': kind, 'text': text, 'd': d, 'fs': fs, 'rot': rot, 'slam': slam, 'dt': dt, 'w': d, 'h': d}
        if kind == 'stop':
            d = 380
            fs = int(min(120, d * 0.62 / M.em(text.upper(), 'onest') * 0.9))
            return {'kind': kind, 'text': text, 'd': d, 'fs': fs, 'rot': rot, 'slam': slam, 'dt': dt, 'w': d, 'h': d}
        if kind == 'stamp':
            fs = 96
            return {'kind': kind, 'text': text, 'fs': fs, 'rot': rot, 'slam': slam, 'dt': dt, 'w': int(em * fs + 80), 'h': int(fs * 1.25)}
        fs = 66                                                      # bubble
        return {'kind': kind, 'text': text, 'fs': fs, 'rot': rot, 'slam': slam, 'dt': dt, 'w': int(em * fs + 80), 'h': int(fs * 1.55)}

    cuts, calls, hits = [], [], []
    for c in INSERTS:
        if not (c['e'] > A and c['t'] < B):
            continue
        co = callout(c['co']['kind'], c['co']['text'], c['co'].get('rot', 0), c['co'].get('slam', False), c['co'].get('dt', 0.0))
        o = {'n': c['n'], 'kind': c['kind'], 't': c['t'], 'e': c['e'], 'what': c['what']}
        if c['kind'] == 'card':
            if not a.cutdir:
                raise SystemExit('--cutdir required for card inserts')
            shutil.copy2(Path(a.cutdir) / f"cut{c['n']}.mp4", proj / 'media' / f"cut{c['n']}.mp4")
            cd = CARDS[c['shape']]
            o['card'] = cd
            at = c['co']['at']
            cx = cd['x'] + (cd['w'] - co['w'] / 2 + 10 if at.endswith('r') else co['w'] / 2 - 10)
            cy = cd['y'] + (co['h'] / 2 - 10 if at.startswith('t') else cd['h'] - co['h'] / 2 + 10)
            co['x'], co['y'] = int(min(max(cx, co['w'] / 2 + 24), 1056 - co['w'] / 2)), int(cy)
        else:  # stop sign: avoid the face
            sl, clr = pick_slot(c['t'], c['e'], 190, None)
            co['x'], co['y'] = sl
        co['t'], co['e'] = c['t'] + co['dt'] if c['kind'] == 'card' else c['t'], c['e'] - (0.0 if c['kind'] != 'card' else 0.05)
        cuts.append(o)
        calls.append(co)
        hits.append([round(co['t'] + (0.12 if co['slam'] else 0.1), 2), 16 if co['slam'] else 9, 0.05 if co['slam'] else 0.03])
    last = None
    for c in CALLOUTS:
        if not (c['e'] > A and c['t'] < B):
            continue
        co = callout(c['kind'], c['text'], c.get('rot', 0))
        sl, clr = pick_slot(c['t'], c['e'], max(co['w'], co['h']) / 2, last)
        last = sl
        co['x'], co['y'] = sl
        co['t'], co['e'], co['clear'] = c['t'], c['e'], clr
        calls.append(co)
        hits.append([round(c['t'] + 0.1, 2), 8, 0.03])
    for h in HOOK:
        hits.append([h['t'], h['amp'], h['punch']])
    hits = [h for h in hits if A - 0.01 <= h[0] <= B]

    # ---- hook layout
    hook = None
    if A <= HOOK_T0:
        gap, hs, tot = 8, [], 0
        for h in HOOK:
            ls = FONTS[h['font']][1]
            size = int(min(h['maxsize'], 920 / (M.em(h['text'], h['font']) + 0.05)))
            hs.append(dict(h, size=size, w=int(M.em(h['text'], h['font']) * size)))
            tot += size + gap
        gy = 1290
        y = gy - tot / 2
        for h in hs:
            h['y'] = round(y + h['size'] / 2)
            y += h['size'] + gap
        hook = {'lines': hs, 't0': HOOK_T0, 'exit': HOOK_EXIT, 't1': HOOK_T1}

    plan = {'off': A, 'dur': dur, 'cam': camrows, 'caps': caps, 'cuts': cuts, 'calls': calls, 'hits': hits, 'tr': TRANS, 'hook': hook}
    fonts = []
    for sc in ('cyrillic', 'latin'):
        rng = ('U+0301,U+0400-045F,U+0490-0491,U+04B0-04B1,U+2116' if sc == 'cyrillic'
               else 'U+0000-00FF,U+0131,U+0152-0153,U+02BB-02BC,U+02C6,U+02DA,U+02DC,U+2000-206F,U+2074,U+20AC,U+2122,U+2191,U+2193,U+2212,U+2215,U+FEFF,U+FFFD')
        fonts.append(f"@font-face{{font-family:'Onest';font-weight:900;font-style:normal;src:url('fonts/onest-{sc}-900-normal.woff2') format('woff2');unicode-range:{rng};font-display:block}}")
        fonts.append(f"@font-face{{font-family:'Oswald';font-weight:700;font-style:normal;src:url('fonts/oswald-{sc}-700-normal.woff2') format('woff2');unicode-range:{rng};font-display:block}}")
        fonts.append(f"@font-face{{font-family:'Playfair Display';font-weight:900;font-style:italic;src:url('fonts/playfair-display-{sc}-900-italic.woff2') format('woff2');unicode-range:{rng};font-display:block}}")
    css = (HERE / 'style2.css').read_text(encoding='utf-8')
    js = (HERE / 'scene2.js').read_text(encoding='utf-8')
    cutvids = ''.join(
        f'<div id="card{c["n"]}" class="card" style="left:{c["card"]["x"]}px;top:{c["card"]["y"]}px;width:{c["card"]["w"]}px;height:{c["card"]["h"]}px"><video id="cv{c["n"]}" src="media/cut{c["n"]}.mp4" muted playsinline data-start="{max(0, c["t"] - A):.3f}" data-duration="{min(c["e"], B) - max(c["t"], A):.3f}" data-track-index="{5 + c["n"]}"></video></div>'
        for c in cuts if c['kind'] == 'card')
    html = f"""<!doctype html>
<html lang="ru"><head><meta charset="utf-8"><meta name="viewport" content="width=1080, height=1920">
<script src="gsap.min.js"></script>
<style>
{chr(10).join(fonts)}
{css}
</style></head>
<body>
<div id="root" data-composition-id="main" data-start="0" data-duration="{dur}" data-width="1080" data-height="1920">
  <div id="snap"><div id="cam"><video id="v" src="media/clip.mp4" muted playsinline data-start="0" data-duration="{dur}" data-track-index="1"></video></div><div id="cutl" class="layer">{cutvids}</div></div>
  <div id="over" class="layer"></div>
  <div id="fx"></div><div id="flash"></div>
</div>
<script>window.PLAN = {json.dumps(plan, ensure_ascii=False)};</script>
<script>
{js}
</script>
</body></html>"""
    (proj / 'index.html').write_text(html, encoding='utf-8')
    print(f'built {proj} {A}-{B} ({dur}s): caps={len(caps)} cuts={[c["n"] for c in cuts]} callouts={[(c["text"], c["x"], c["y"]) for c in calls]} hook={[(l["text"], l["size"], l["y"]) for l in (hook or {"lines": []})["lines"]]}')


if __name__ == '__main__':
    main()

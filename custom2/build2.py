#!/usr/bin/env python3
"""Round 2 composition builder: ONE HyperFrames project for a time range of the clip (no cuts, no speed change, no cut-out).
usage: build2.py --a 0 --b 20 --out proj --clip range.mp4 [--fonts DIR --gsap FILE --data DIR]
Data (words_2.json, face_track.json) live next to this script unless --data is given."""
import argparse, json, math, re, shutil
from pathlib import Path
from fontTools.ttLib import TTFont

HERE = Path(__file__).resolve().parent
CUTS = [5.73, 7.53, 12.17, 15.3, 17.93, 21.1, 25.0, 25.6, 38.5, 41.1, 68.1]  # jump cuts already in the clip
PUNCH_CUTS = [7.53, 17.93]                                                   # cuts without a transition: tiny punch-in
TRANS = [{'t': 5.95, 'type': 'sweep'}, {'t': 12.15, 'type': 'zoom'}, {'t': 15.4, 'type': 'push'}, {'t': 21.05, 'type': 'flare'}]
# zoom plan (global seconds, scale): push-ins on key phrases, pull-outs on idea changes, slow drift between. <= 1.15
ZK = [(0, 1.0), (2.4, 1.07), (5.6, 1.10), (6.7, 1.01), (8.2, 1.02), (10.9, 1.12), (12.0, 1.12), (12.9, 1.02), (14.2, 1.04), (15.3, 1.13),
      (16.3, 1.02), (18.7, 1.05), (20.6, 1.13), (21.7, 1.02), (23.3, 1.05), (24.9, 1.13), (25.9, 1.03), (31.0, 1.05), (33.2, 1.12), (35.3, 1.12),
      (36.6, 1.02), (40.0, 1.06), (41.6, 1.10), (43.0, 1.10), (44.3, 1.02), (47.9, 1.02), (49.0, 1.12), (50.5, 1.12), (51.6, 1.03), (54.8, 1.05),
      (55.9, 1.12), (58.0, 1.12), (59.2, 1.14), (61.0, 1.14), (62.2, 1.02), (64.0, 1.02), (66.0, 1.12), (67.6, 1.12), (68.6, 1.02), (71.6, 1.08)]
STK = [  # global seconds: appear, leave, icon (at most one per ~4-5 s, none over eyes/mouth: slot chosen from the face track)
    {'t': 4.00, 'e': 5.50, 'type': 'stopwatch'}, {'t': 9.70, 'e': 11.30, 'type': 'magnify'}, {'t': 13.70, 'e': 15.20, 'type': 'one'},
    {'t': 19.15, 'e': 20.80, 'type': 'question'}, {'t': 23.50, 'e': 25.00, 'type': 'bell'},
    {'t': 38.70, 'e': 40.50, 'type': 'price'}, {'t': 43.40, 'e': 45.30, 'type': 'calendar'},
    {'t': 59.20, 'e': 61.80, 'type': 'clock', 'mturn': 0, 'h0': 180, 'h1': 180}, {'t': 66.30, 'e': 67.90, 'type': 'check'}]
KEY = {'быстрее', 'скорость', 'тон', 'единственное', 'визита', 'первая', 'услуги', 'плохо', 'вернется', 'гудка', 'секунды', 'клиент', 'системы',
       '4', 'воскресенье', 'утром', '9', '6', '8', 'поздно', 'идеально', 'телефона', 'качество', 'ближайший', 'чисточку', 'гигиена', 'нет', 'копыта', 'ответили'}
STOP = {'в', 'с', 'к', 'и', 'а', 'о', 'у', 'на', 'по', 'до', 'не', 'от', 'за', 'из', 'бы', 'ли', 'же', 'или', 'но', 'то', 'вот'}
FIX = {'проден': 'ПроДент', 'миланов': 'Милана', 'гуд': None}
HOOK = [('КЛИЕНТ ВЫБИРАЕТ', 96, False), ('КТО ОТВЕТИЛ', 128, False), ('БЫСТРЕЕ', 214, True)]
HOOK_T0, HOOK_T1 = 0.12, 2.35
CAP_Y, CAP_MAX, CAP_W = 1450, 88, 930


class Meas:
    def __init__(self, fd):
        self.f = {}
        for sc in ('cyrillic', 'latin'):
            for wgt in (900,):
                p = Path(fd) / f'onest-{sc}-{wgt}-normal.woff2'
                t = TTFont(p)
                self.f[sc] = (t.getBestCmap(), t['hmtx'], t['head'].unitsPerEm)

    def em(self, text, ls=-0.022):
        w = 0.0
        for ch in text:
            for sc in ('cyrillic', 'latin'):
                cm, hm, upm = self.f[sc]
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
            out.append({'raw': raw, 't': t, 'n': n, 's': w['s'], 'e': w['e'], 'k': 1 if n in KEY else 0})
    return out


def group_caps(W, M):
    groups, cur = [], []

    def flush():
        nonlocal cur
        if cur:
            groups.append(cur)
            cur = []

    def txt(g):
        return ' '.join(x['t'] for x in g)

    for i, w in enumerate(W):
        if cur and w['s'] - cur[-1]['e'] > 0.6:
            flush()
        cur.append(w)
        end = w['raw'][-1] in '.?!' or (w['raw'][-1] == ',' and len(cur) >= 2) or len(cur) >= 3 or len(txt(cur)) > 19
        if end:
            carry = []
            while len(cur) > 2 and cur[-1]['n'] in STOP and cur[-1]['raw'][-1] not in '.?!':
                carry.insert(0, cur.pop())
            flush()
            cur = carry
    flush()
    return groups


def cam_path(face, a, b, step=0.1):
    """[(t, z, tx, ty)] — face-centred, eased, smoothed per cut-free segment."""
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

    def face_at(t0, t1, tt):  # interpolated, from detections inside [t0,t1)
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
        first = True
        while tt < end - 1e-6:
            f = face_at(t0, t1, tt)
            if f is None:
                tgt = (0.5, 0.45, 0.4)
            else:
                tgt = tuple(f)
            st = list(tgt) if st is None else [st[j] + (tgt[j] - st[j]) * (1 - math.exp(-step / 0.5)) for j in range(3)]
            z = min(1.15, zoom(tt) * (1 + 0.008 * math.sin(2 * math.pi * tt / 7.0)))
            wx = min(max(st[0] - 0.5 / z, 0), 1 - 1 / z)
            wy = min(max(st[1] - 0.40 / z, 0), 1 - 1 / z)
            out.append((round(tt, 3) if not first else round(tt, 3), round(z, 4), round(-wx * 1080 * z, 1), round(-wy * 1920 * z, 1), st[:]))
            tt += step
            first = False
        # exact end of segment (hold, so the existing jump cut stays a jump)
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
    a = ap.parse_args()
    D = Path(a.data)
    A, B = a.a, a.b
    proj = Path(a.out)
    (proj / 'media').mkdir(parents=True, exist_ok=True)
    (proj / 'fonts').mkdir(exist_ok=True)
    for f in Path(a.fonts).glob('onest-*.woff2'):
        shutil.copy2(f, proj / 'fonts' / f.name)
    shutil.copy2(a.gsap, proj / 'gsap.min.js')
    dst = proj / 'media' / 'clip.mp4'
    if Path(a.clip).resolve() != dst.resolve():
        shutil.copy2(a.clip, dst)
    (proj / 'meta.json').write_text(json.dumps({'id': 'custom-edit-2', 'name': 'custom edit 2'}), encoding='utf-8')
    dur = round(a.b - a.a, 3)
    M = Meas(a.fonts)
    face = json.loads((D / 'face_track.json').read_text(encoding='utf-8'))

    # captions
    W = load_words(D / 'words_2.json')
    caps = []
    gl = group_caps(W, M)
    for i, g in enumerate(gl):
        s = g[0]['s']
        e = g[-1]['e'] + 0.18
        if i + 1 < len(gl):
            e = min(e, gl[i + 1][0]['s'] - 0.02)
        if s < HOOK_T1 + 0.05 and A <= HOOK_T0:
            if e <= HOOK_T1 + 0.3:
                continue
            s = HOOK_T1 + 0.05
        if e - s < 0.25:
            e = s + 0.25
        text = ' '.join(x['t'] for x in g).upper()
        em = M.em(text) + 0.26 * (len(g) - 1) + 0.04
        size = int(min(CAP_MAX, CAP_W / em))
        ws = []
        kdone = False
        for x in g:
            k = 0
            if x['k'] and not kdone:
                k, kdone = 1, True
            ws.append({'t': x['t'], 'k': k, 's': x['s']})
        caps.append({'s': round(s, 2), 'e': round(e, 2), 'w': ws, 'size': size, 'y': CAP_Y})

    # camera
    cam = cam_path(face, A, B)
    camrows = [[r[0], r[1], r[2], r[3]] for r in cam]
    # nudge: duplicate times at exact cuts are handled by the 1 ms hold; make timeline strictly ordered
    camrows.sort(key=lambda r: r[0])

    def screen_face(t):
        best = None
        for r in cam:
            if r[0] >= t:
                best = r
                break
        if best is None:
            best = cam[-1]
        z, tx, ty, st = best[1], best[2], best[3], best[4]
        return (tx + z * st[0] * 1080, ty + z * st[1] * 1920, z * st[2] * 1080)

    # stickers: pick the slot (beside / above the head) with most clearance over the sticker's life
    SLOTS = [(165, 215), (915, 215), (165, 420), (915, 420), (165, 700), (915, 700), (165, 1010), (915, 1010), (540, 190)]
    stk, last = [], None
    for s in STK:
        if not (s['e'] > A and s['t'] < B):
            continue
        samples = [screen_face(s['t'] + (s['e'] - s['t']) * u / 4) for u in range(5)]
        sc = []
        for sl in SLOTS:
            clear = 1e9
            for fx, fy, fw in samples:
                dx = max(0, abs(sl[0] - fx) - fw * 0.62 - 120)
                dy = max(0, abs(sl[1] - (fy + fw * 0.08)) - fw * 0.5 - 120)
                clear = min(clear, math.hypot(dx, dy) if (dx > 0 or dy > 0) else -1)
            pen = (60 if sl == last else 0)
            sc.append((clear - pen + (15 if sl[1] < 800 else 0), sl))
        sc.sort(reverse=True)
        sl = sc[0][1]
        last = sl
        o = dict(s)
        o['x'], o['y'] = sl
        o['rot'] = (-7 if sl[0] > 540 else 7)
        o['clear'] = round(sc[0][0])
        stk.append(o)

    # hook
    lines, gap, tot = [], 14, 0
    hs = []
    for text, mx, acc in HOOK:
        size = int(min(mx, 900 / (M.em(text) + 0.05)))
        hs.append((text, size, acc))
        tot += size + gap
    gy = 1330
    y = gy - tot / 2
    for text, size, acc in hs:
        lines.append({'text': text, 'size': size, 'y': round(y + size / 2), 'acc': acc})
        y += size + gap
    plan = {'off': A, 'dur': dur, 'cam': camrows, 'caps': caps, 'stk': stk,
            'tr': [t for t in TRANS], 'punch': [[t, 0.045] for t in PUNCH_CUTS],
            'hook': {'t0': HOOK_T0, 't1': HOOK_T1, 'lines': lines, 'gy': gy} if A <= HOOK_T0 else None}
    fonts = []
    for sc in ('cyrillic', 'latin'):
        rng = ('U+0301,U+0400-045F,U+0490-0491,U+04B0-04B1,U+2116' if sc == 'cyrillic'
               else 'U+0000-00FF,U+0131,U+0152-0153,U+02BB-02BC,U+02C6,U+02DA,U+02DC,U+2000-206F,U+2074,U+20AC,U+2122,U+2191,U+2193,U+2212,U+2215,U+FEFF,U+FFFD')
        for wgt in (800, 900):
            fonts.append(f"@font-face{{font-family:'Onest';font-weight:{wgt};font-style:normal;src:url('fonts/onest-{sc}-{wgt}-normal.woff2') format('woff2');unicode-range:{rng};font-display:block}}")
    css = (HERE / 'style2.css').read_text(encoding='utf-8')
    js = (HERE / 'scene2.js').read_text(encoding='utf-8')
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
  <div id="warm" class="layer"></div><div id="vign" class="layer"></div><div id="shade" class="layer"></div>
  <div id="over" class="layer"></div>
  <div id="fx"></div><div id="flash"></div>
</div>
<script>window.PLAN = {json.dumps(plan, ensure_ascii=False)};</script>
<script>
{js}
</script>
</body></html>"""
    (proj / 'index.html').write_text(html, encoding='utf-8')
    print(f'built {proj} {a.a}-{a.b} ({dur}s): caps={len(caps)} stickers={[(s["type"], s["t"], s["x"], s["y"], s["clear"]) for s in stk]} hook={[(l["text"], l["size"], l["y"]) for l in lines]}')


if __name__ == '__main__':
    main()

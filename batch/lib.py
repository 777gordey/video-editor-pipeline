"""Shared helpers: words, caption grouping, camera path, timeline mapping. Pure functions of (analysis, plan, preset)."""
import json, math, random, re
from pathlib import Path

STOP = {'в', 'с', 'к', 'и', 'а', 'о', 'у', 'на', 'по', 'до', 'не', 'от', 'за', 'из', 'бы', 'ли', 'же', 'или', 'но', 'то', 'вот', 'я', 'мне', 'мы',
        'ваш', 'для', 'что', 'это', 'как', 'очень', 'ты', 'тебе', 'он', 'ему', 'они', 'меня', 'во', 'со', 'об', 'ко', 'без', 'при', 'про', 'над', 'под'}
FILLERS = {'э', 'эм', 'э-э', 'эээ', 'м', 'мм', 'м-м', 'ммм', 'ам', 'а-а', 'ээ'}


def load_json(p):
    return json.loads(Path(p).read_text(encoding='utf-8'))


def clean_words(words, fixes=None):
    """analysis words -> caption words. Fillers are dropped, planner fixes (obvious ASR errors) applied. idx = index in the ORIGINAL list."""
    fixes = {int(f['idx']): f['text'] for f in (fixes or [])}
    out = []
    for i, w in enumerate(words):
        raw = fixes.get(i, w['w'])
        t = re.sub(r'[.,!?…:;"«»]+$', '', raw.strip())
        t = re.sub(r'^["«»]+', '', t)
        if not t or t.lower() in FILLERS:
            continue
        out.append({'idx': i, 'raw': raw.strip(), 't': t, 'n': t.lower(), 's': float(w['s']), 'e': float(w['e'])})
    return out


class Meas:
    """text width in em for the preset's font roles (fontTools on the same woff2 files the page loads)"""
    def __init__(self, preset, fonts_dir):
        from fontTools.ttLib import TTFont
        from presets import FONT_FILES
        self.pr = preset
        self.f = {}
        for role, key in preset['roles'].items():
            if key in self.f:
                continue
            pat = FONT_FILES[key][3]
            self.f[key] = [(lambda t: (t.getBestCmap(), t['hmtx'], t['head'].unitsPerEm))(TTFont(Path(fonts_dir) / (pat.format(sc=sc) + '.woff2')))
                           for sc in ('cyrillic', 'latin')]

    def em(self, text, role='base'):
        key = self.pr['roles'][role]
        up = self.pr['upper'] or role in ('h1', 'h2', 'key')
        w = 0.0
        for ch in (text.upper() if up else text):
            for cm, hm, upm in self.f[key]:
                if ord(ch) in cm:
                    w += hm[cm[ord(ch)]][0] / upm
                    break
            else:
                w += 0.6
        return w


def classify(g, keys, emo, nums):
    """one caption group -> span list with classes n/k/e. priority: emotional, number, key (only one highlighted word per group)"""
    hi, kind = None, None
    for pri, S in (('e', emo), ('n', nums), ('k', keys)):
        for i, w in enumerate(g):
            if w['idx'] in S:
                hi, kind = i, pri
                break
        if hi is not None:
            break
    spec = []
    for i, w in enumerate(g):
        cls = 'n' if i != hi else ('e' if kind == 'e' else 'k')
        spec.append({'t': w['t'], 'cls': cls, 'col': '', 's': w['s']})
    return spec


def spec_em(M, pr, spec):
    tot = 0.0
    for x in spec:
        if x['cls'] == 'n':
            tot += M.em(x['t'], 'base')
        elif x['cls'] == 'k':
            tot += M.em(x['t'], 'key') * pr['key_mult']
        else:
            tot += M.em(x['t'], 'emo') * pr['emo_mult']
    return tot + pr['gap'] * (len(spec) - 1) + 0.1


def group_caps(W, M, pr, keys, emo, nums):
    cap_w = pr['cap_w'] / 64
    fits = lambda g: spec_em(M, pr, classify(g, keys, emo, nums)) * 1.1 <= cap_w
    groups, cur = [], []

    def flush():
        nonlocal cur
        if cur:
            groups.append(cur)
            cur = []

    for w in W:
        if cur and w['s'] - cur[-1]['e'] > 0.55:
            flush()
        if cur and (not fits(cur + [w]) or len(cur) >= pr['cap_words']):
            carry = []
            while len(cur) > 1 and cur[-1]['n'] in STOP:       # captions never end on a preposition / conjunction
                carry.insert(0, cur.pop())
            flush()
            cur = carry
        cur.append(w)
        if w['raw'][-1:] in '.?!' or (w['raw'][-1:] == ',' and len(cur) >= 2):
            flush()
    flush()
    for i in range(len(groups) - 1):
        g, nx = groups[i], groups[i + 1]
        while len(g) > 1 and g[-1]['n'] in STOP and g[-1]['raw'][-1:] not in '.?!' and nx[0]['s'] - g[-1]['e'] < 1.0 and fits([g[-1]] + nx):
            nx.insert(0, g.pop())
    out = []
    for g in groups:
        if out and len(g) == 1 and out[-1][-1]['raw'][-1:] not in '.?!' and g[0]['s'] - out[-1][-1]['e'] < 0.5 and fits(out[-1] + g):
            out[-1] = out[-1] + g
        else:
            out.append(g)
    return out


def build_caps(W, M, pr, keys, emo, nums, hook_t1, big_idx=None):
    gl = group_caps(W, M, pr, keys, emo, nums)
    caps = []
    for i, g in enumerate(gl):
        s, e = g[0]['s'], g[-1]['e'] + 0.2
        if i + 1 < len(gl):
            e = min(e, gl[i + 1][0]['s'] - 0.02)
        if s < hook_t1 and e <= hook_t1 + 0.1:
            continue
        if s < hook_t1:
            s = hook_t1
        if e - s < 0.28:
            e = s + 0.28
        spec = classify(g, keys, emo, nums)
        size = min(pr['cap_max'], pr['cap_w'] / spec_em(M, pr, spec))
        big = bool(big_idx) and any(w['idx'] == big_idx for w in g)
        caps.append({'s': round(s, 2), 'e': round(e, 2), 'w': spec, 'size': int(size), 'first': False, 'big': big})
    return caps


# ------------------------------------------------------------------ camera
CAMERA = {'calm': ((1.03, 1.12), (4.5, 7.5)), 'normal': (None, None), 'aggressive': ((1.08, 1.22), (2.0, 3.6)), 'locked': ((1.0, 1.06), (6.0, 9.0))}


def zoom_keys(dur, cuts, pr, seed, camera='normal'):
    """slow push-in, then a hard step to a new framing (two keys 0.01 s apart = a jump). Real cuts of the footage reset to 1.00."""
    rng = random.Random(seed)
    lo, hi = pr['zoom_range']
    zr, ze = CAMERA.get(camera, (None, None))
    every = ze or pr['zoom_every']
    if zr:
        lo, hi = zr
    ev = sorted(set([0.0] + [c for c in cuts if 0 < c < dur] + [dur]))
    keys = [(0.0, 1.0)]
    t = 0.0
    z = 1.0
    cutset = set(round(c, 2) for c in cuts)
    while t < dur - 0.2:
        step = rng.uniform(*every)
        nxt = t + step
        hit_cut = [c for c in cuts if t + 0.3 < c < nxt + 0.6]
        if hit_cut:
            c = hit_cut[0]
            keys.append((round(c - 0.01, 2), round(min(hi, max(z, 1.0 + rng.uniform(0.04, 0.1))), 3)))
            keys.append((round(c, 2), 1.0))
            z = 1.0
            t = c
            continue
        nxt = min(nxt, dur)
        tgt = round(rng.uniform(lo, hi), 3)
        if tgt < z + 0.03 and z > 1.12:
            tgt = round(rng.uniform(1.0, 1.06), 3)         # step back out from a deep zoom
        keys.append((round(nxt - 0.01, 2), tgt))
        keys.append((round(nxt, 2), round(min(hi, tgt + rng.choice([-0.08, -0.05, 0.04, 0.07])), 3)))
        z = keys[-1][1]
        t = nxt
    keys.append((round(dur, 2), keys[-1][1]))
    out, last = [], -1
    for k in sorted(keys):
        if k[0] <= last:
            continue
        out.append(k)
        last = k[0]
    return out


def _zoom_at(ZK, t):
    for (t0, z0), (t1, z1) in zip(ZK, ZK[1:]):
        if t0 <= t <= t1:
            u = (t - t0) / (t1 - t0) if t1 > t0 else 1
            u = u * u * (3 - 2 * u)
            return z0 + (z1 - z0) * u
    return ZK[-1][1]


def shot_anchor(face, t0, t1):
    """zoom anchor y for one shot: keeps the top of the head inside the frame"""
    ys = sorted(r['f'][1] - 0.8 * r['f'][2] * 0.5625 for r in face if r['f'] and t0 <= r['t'] < t1)
    if not ys:
        return 0.30
    head_top = ys[len(ys) // 2]
    return round(min(0.30, max(0.06, head_top)), 3)


def cam_path(face, ZK, cuts, dur, step=0.1, zmax=1.22, jumps=()):
    """[[t, zoom, x, y]] about a smoothed face centre; jumps = [(t0, t1, zoom)] forced punch-cut zooms (wildcard)"""
    bounds = [0.0] + [c for c in cuts if 0 < c < dur] + [999.0]
    ft = [(r['t'], r['f']) for r in face if r['f']]
    out = []
    for si in range(len(bounds) - 1):
        t0, t1 = bounds[si], min(bounds[si + 1], dur + 0.2)
        if t0 >= dur + 0.2:
            break
        pts = [(t, f[0]) for t, f in ft if t0 - 0.1 <= t < t1 + 0.1]
        ay = shot_anchor(face, t0, t1)
        cx, tt = None, t0
        while tt < t1 - 1e-6:
            near = [c for t, c in pts if abs(t - tt) <= 0.6]
            tgt = sum(near) / len(near) if near else 0.5
            tgt = min(max(tgt, 0.42), 0.58)
            cx = tgt if cx is None else cx + (tgt - cx) * (1 - math.exp(-step / 0.6))
            z = min(zmax, _zoom_at(ZK, tt))
            for a, b, jz in jumps:
                if a <= tt <= b:
                    z = jz
            for r in face:                                  # the head is never cropped: cap the zoom by the nearest detected head top
                if r['f'] and abs(r['t'] - tt) <= 0.25:
                    ht = r['f'][1] - 0.8 * r['f'][2] * 0.5625
                    if ht < ay - 0.01:
                        z = min(z, (ay - 0.02) / (ay - ht))
            wx, wy = cx * (1 - 1 / z), ay * (1 - 1 / z)
            out.append([round(tt, 3), round(z, 4), round(-wx * 1080 * z, 1), round(-wy * 1920 * z, 1)])
            tt += step
        out.append([round(t1 - 0.001, 3), out[-1][1], out[-1][2], out[-1][3]])
    return sorted(out, key=lambda r: r[0])


def camera_gate(cam, face):
    """max zoom and the lowest projected head top over the whole clip (y' = ay + z*(y-ay), the same transform the page applies)"""
    zmax = max(r[1] for r in cam)
    worst = 1.0
    for r in face:
        if not r['f']:
            continue
        k = min(range(len(cam)), key=lambda i: abs(cam[i][0] - r['t']))
        z, ty = cam[k][1], cam[k][3]
        ht = r['f'][1] - 0.8 * r['f'][2] * 0.5625
        y_new = z * ht + ty / 1920.0                        # translate is in px of the scaled layer: y' = z*y + ty/1920
        worst = min(worst, y_new)
    return round(zmax, 3), round(worst, 3)


def hook_lines(plan):
    """effective hook lines for the chosen layout (stack: up to 3 | single: one giant line | split: 2)"""
    L = [x for x in plan['hook']['lines'] if x][:3]
    lay = (plan.get('style') or {}).get('hook_layout', 'stack')
    if lay == 'single':
        return [" ".join(L[:2])[:30]] if L else []
    if lay == 'split':
        return L[:2]
    return L

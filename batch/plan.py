#!/usr/bin/env python3
"""ONE headless `claude -p` planning call per clip -> plan.json. Falls back to a rules-based plan if the call fails (a clip never fails because of the planner).
usage: plan.py ANALYSIS.json --preset dark|proof|slab --out plan.json [--payload payload.json]"""
import argparse, json, os, random, re, shutil, subprocess, sys, tempfile, time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from presets import PRESETS, WILDCARDS, SFX_VOCAB
from lib import clean_words, STOP

KIND_HELP = {
    "punch": "text (1-2 words, <=14 chars, from the speech) — giant word slammed mid-frame on first..last",
    "stamp": "text (1-2 words, <=16 chars) — a hard rubber-stamp slam, tilted, for a verdict/label word",
    "stat": "value (number from the speech), prefix?, suffix? (e.g. '₽','%','x','дн'), label (<=24 chars) — animated counter; ONLY if the speaker says a number",
    "stock": "query (2-4 English words, a concrete OBJECT or scene, no people close-ups, no logos) — 1.5 s full-frame cutaway as a visual metaphor",
    "wave": "no params — thin voice waveform line (calm moment, a 'listen' beat)",
    "compare": "left (<=18 chars, the bad option), right (<=24 chars, the good option) — two rows, bad crossed out, good ticked; ONLY for a real contrast in the speech",
    "checklist": "items (2-3 strings <=22 chars, from the speech) — ticks appear one by one; ONLY for a real enumeration",
    "notify": "title (<=20 chars), text (<=40 chars) — a notification card; for a message/call/booking moment",
}
INS_DUR = {"punch": 1.15, "stamp": 1.3, "stat": 2.3, "stock": 1.5, "wave": 1.6, "compare": 3.0, "checklist": 3.4, "notify": 2.6}
HOOK_POPS = (0.20, 0.62, 1.04)
HOOK_T0, HOOK_EXIT, HOOK_T1 = 0.10, 2.45, 2.70


# ------------------------------------------------------------------ helpers
def sentences(words):
    out, cur = [], []
    for i, w in enumerate(words):
        cur.append(i)
        nxt = words[i + 1]['s'] if i + 1 < len(words) else 1e9
        if w['w'][-1:] in '.?!…' or nxt - w['e'] > 0.7:
            out.append(cur)
            cur = []
    if cur:
        out.append(cur)
    return out


def transcript_text(words):
    lines = []
    for si, s in enumerate(sentences(words)):
        lines.append(f"[{si} @{words[s[0]]['s']:.1f}s] " + " ".join(f"{i}:{words[i]['w']}" for i in s))
    return "\n".join(lines)


def build_prompt(an, pr, ctx):
    words = an['words']
    n_ins = 2 if an['dur'] < 30 else 3 if an['dur'] < 60 else 4 if an['dur'] < 90 else 5
    kinds = "\n".join(f"  - {k}: {KIND_HELP[k]}" for k in pr['kinds'])
    wc = "\n".join(f"  - {k}: {v}" for k, v in WILDCARDS.items())
    sfx = ", ".join(f"{k} ({v})" for k, v in SFX_VOCAB.items())
    recent = ctx.get('recent_wildcards') or []
    cuts = ", ".join(f"{c:.1f}" for c in an['cuts']) or "none"
    return f"""Ты — смелый монтажёр вертикальных видео (Reels). Клип: говорящая голова в реальной комнате, {an['dur']:.0f} с. Пресет «{pr['name']}» ({pr['base_look']}).
Ниже транскрипт по предложениям, формат `idx:слово` ([№ @сек]). Реальные склейки в исходнике на секундах: {cuts}.

ЖЁСТКИЕ ПРАВИЛА (нарушение = решение выбрасывается):
 1. Единственный видеослой — реальная комната автора. Никаких вырезов человека, замены фона, плёнок поверх лица. Стоковый кадр допустим только как короткая вставка на весь кадр (не под говорящим).
 2. Взрослый, мужской, жёсткий вкус: никаких мультяшных стикеров, маскотов, эмодзи, пастели, «милоты».
 3. Музыка и эффекты слышны на согласованных уровнях (музыка ≈ −11 дБ от голоса, эффекты ≈ −10 дБ от пика голоса) — не предлагай то, что требует тишины музыки надолго или оглушающих эффектов.
 4. Голос не трогаем по времени (никаких ускорений, вырезов, пауз). Все слова, цифры и факты берутся ТОЛЬКО из речи автора; ничего не выдумывай.
 5. Все idx должны существовать в транскрипте.

ШАГ 1 — ИДЕИ (BOLDNESS BOOST). Прежде чем выбрать план, придумай ровно 5 по-настоящему смелых, неожиданных идей для ЭТОГО клипа:
 необычное открытие, звуковой гэг, яркий переход, визуальная метафора того, что говорит автор. Избегай всего, что делает любой редактор (зум на слове, «whoosh» на каждом слове, стоковый «успех»).
 Каждая идея обязана опираться на один из типов wildcard (меню ниже) с конкретными параметрами. Для каждой отметь проверку по правилам 1-3 (true/false) и смелость 1-5.
 Выбери СИЛЬНЕЙШУЮ идею, прошедшую все проверки, и построй её как wildcard клипа (один на клип).{(' Недавно в этой пачке уже были wildcard: ' + ', '.join(recent) + ' — выбери другой тип, если идея не сильнее.') if recent else ''}

Меню wildcard:
{wc}
Звуки для sound_gag (sample): {sfx}

ШАГ 2 — ПЛАН (в рамках пресета «{pr['name']}» выбирай сильные, необычные решения, но без хаоса):
 - hook: 2-3 коротких строки заголовка (каждая ≤ 18 символов, КАПСОМ не нужно), построенные из реальных слов автора из первых ~12 с речи; first/last — idx слов, на которые он опирается.
   Хук должен быть понятен без контекста, обещать результат/цифру/ошибку/секрет или задавать острый вопрос; строки не заканчиваются предлогом/союзом. Не банальный «Смотри как…».
 - keys: idx 8-14 ключевых слов для выделения в субтитрах (не служебные), emo: до 4 эмоциональных слов, nums: idx слов-цифр.
 - big_word: idx одного самого сильного слова-кульминации в последних 25% клипа (или null).
 - inserts: ровно {n_ins} вставок; допустимые kind для пресета:
{kinds}
   Каждая вставка: kind, first, last (idx слов, к которым она привязана), плюс параметры kind. Вставки разнесены минимум на 5 с, не раньше 4-й секунды, не на хуке, и не на момент wildcard.
 - word_fixes: [{{idx, text}}] только для очевидных ошибок распознавания (имена, термины) — иначе пусто.
 - summary: одна строка — о чём клип.

ТРАНСКРИПТ:
{transcript_text(words)}

Верни ТОЛЬКО JSON по схеме."""


def schema(pr):
    ins = {"type": "object", "required": ["kind", "first", "last"], "properties": {
        "kind": {"enum": pr['kinds']}, "first": {"type": "integer", "minimum": 0}, "last": {"type": "integer", "minimum": 0},
        "text": {"type": "string", "maxLength": 20}, "value": {"type": "number"}, "prefix": {"type": "string", "maxLength": 4},
        "suffix": {"type": "string", "maxLength": 6}, "label": {"type": "string", "maxLength": 30}, "query": {"type": "string", "maxLength": 50},
        "left": {"type": "string", "maxLength": 24}, "right": {"type": "string", "maxLength": 30}, "title": {"type": "string", "maxLength": 24},
        "items": {"type": "array", "items": {"type": "string", "maxLength": 26}, "maxItems": 3}}}
    return {"type": "object", "required": ["ideas", "picked", "wildcard", "hook", "keys", "inserts"], "properties": {
        "ideas": {"type": "array", "minItems": 5, "maxItems": 5, "items": {"type": "object", "required": ["id", "idea", "type", "rules_ok", "boldness"], "properties": {
            "id": {"type": "integer"}, "idea": {"type": "string", "maxLength": 260}, "type": {"enum": list(WILDCARDS)},
            "rules_ok": {"type": "object", "properties": {"real_room_only": {"type": "boolean"}, "adult_masculine": {"type": "boolean"},
                                                          "audible_levels": {"type": "boolean"}}},
            "boldness": {"type": "integer", "minimum": 1, "maximum": 5}}}},
        "picked": {"type": "integer"},
        "wildcard": {"type": "object", "required": ["type", "at_word"], "properties": {
            "type": {"enum": list(WILDCARDS)}, "at_word": {"type": "integer", "minimum": 0}, "last_word": {"type": "integer", "minimum": 0},
            "text": {"type": "string", "maxLength": 20}, "query": {"type": "string", "maxLength": 50}, "sample": {"type": "string"},
            "note": {"type": "string", "maxLength": 200}}},
        "hook": {"type": "object", "required": ["lines", "first", "last"], "properties": {
            "lines": {"type": "array", "minItems": 2, "maxItems": 3, "items": {"type": "string", "maxLength": 22}},
            "first": {"type": "integer", "minimum": 0}, "last": {"type": "integer", "minimum": 0}}},
        "keys": {"type": "array", "items": {"type": "integer", "minimum": 0}, "maxItems": 24},
        "emo": {"type": "array", "items": {"type": "integer", "minimum": 0}, "maxItems": 6},
        "nums": {"type": "array", "items": {"type": "integer", "minimum": 0}, "maxItems": 10},
        "big_word": {"type": ["integer", "null"]},
        "inserts": {"type": "array", "items": ins, "maxItems": 6},
        "word_fixes": {"type": "array", "items": {"type": "object", "required": ["idx", "text"], "properties": {
            "idx": {"type": "integer", "minimum": 0}, "text": {"type": "string", "maxLength": 30}}}},
        "summary": {"type": "string", "maxLength": 200}}}


def scrub(t):
    t = re.sub(r"sk-ant-[A-Za-z0-9_\-]+", "<token>", t or "")
    tok = os.environ.get("CLAUDE_CODE_OAUTH_TOKEN")
    return t.replace(tok, "<token>") if tok else t


def call_claude(prompt, sch, model, timeout, max_turns=4):
    cmd = [shutil.which("claude") or "claude", "-p", "--model", model, "--max-turns", str(max_turns), "--tools", "", "--output-format", "json",
           "--json-schema", json.dumps(sch), "--no-session-persistence"]
    t = time.time()
    p = subprocess.run(cmd, input=prompt, capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=timeout, env=dict(os.environ),
                       cwd=tempfile.mkdtemp(prefix="plan_"))
    out = scrub(p.stdout)
    try:
        meta = json.loads(out)
    except ValueError:
        meta = {}
    if p.returncode != 0 or meta.get("is_error"):
        raise RuntimeError(f"claude exit={p.returncode} subtype={meta.get('subtype')} {scrub(str(meta.get('result') or p.stderr or out))[:300]}")
    data = meta.get("structured_output")
    if not isinstance(data, dict):
        m = re.search(r"\{.*\}", str(meta.get("result", "")), re.S)
        if not m:
            raise RuntimeError("no JSON in the answer")
        data = json.loads(m.group(0))
    u = meta.get("usage") or {}
    info = {"model": model, "cost_usd": meta.get("total_cost_usd"), "turns": meta.get("num_turns"), "duration_ms": meta.get("duration_ms"),
            "input_tokens": u.get("input_tokens"), "output_tokens": u.get("output_tokens"),
            "cache_read_tokens": u.get("cache_read_input_tokens"), "cache_create_tokens": u.get("cache_creation_input_tokens"),
            "wall_s": round(time.time() - t, 1)}
    return data, info


# ------------------------------------------------------------------ validation -> final plan
def _ok(i, n):
    return isinstance(i, int) and 0 <= i < n


def normalise(raw, an, pr, seed):
    W = an['words']
    n = len(W)
    dur = an['dur']
    notes = []
    start = lambda i: W[i]['s']
    end = lambda i: W[i]['e']

    # hook: text must come from the speaker's own words
    hook_lines = [str(x).strip() for x in (raw.get('hook') or {}).get('lines', []) if str(x).strip()][:3]
    hf, hl = (raw.get('hook') or {}).get('first', 0), (raw.get('hook') or {}).get('last', 0)
    support = [re.sub(r'\W', '', W[i]['w'].lower()) for i in range(max(0, (hf if _ok(hf, n) else 0) - 3), min(n, (hl if _ok(hl, n) else 12) + 4))]
    support += [re.sub(r'\W', '', W[i]['w'].lower()) for i in range(min(n, 40)) if W[i]['s'] < 14]

    def grounded(line):
        toks = [re.sub(r'\W', '', t.lower()) for t in line.split()]
        toks = [t for t in toks if len(t) > 2]
        return all(any(s.startswith(t[:4]) or t.startswith(s[:4]) for s in support if s) for t in toks)
    if len(hook_lines) < 2 or not all(grounded(x) for x in hook_lines):
        notes.append('hook not grounded in the speech -> verbatim fallback')
        first = [i for i in range(n) if W[i]['w'].strip(',.!?…').lower() not in ('э', 'эм', 'ну')][:9]
        chunks = [first[0:3], first[3:6], first[6:9]]
        hook_lines = [" ".join(W[i]['w'].strip(',.!?…') for i in c) for c in chunks if c]
    hook_lines = [x.strip(' ,.-—') for x in hook_lines][:3]

    keys = sorted({i for i in raw.get('keys', []) if _ok(i, n) and W[i]['w'].strip(',.!?…').lower() not in STOP})
    emo = sorted({i for i in raw.get('emo', []) if _ok(i, n)})[:4]
    nums = sorted({i for i in raw.get('nums', []) if _ok(i, n)} | {i for i in range(n) if re.search(r'\d', W[i]['w'])})
    big = raw.get('big_word')
    big = big if _ok(big, n) and start(big) > dur * 0.6 else None

    # wildcard
    wcr = raw.get('wildcard') or {}
    wtype = wcr.get('type') if wcr.get('type') in WILDCARDS else 'negative_flash'
    at = wcr.get('at_word', 0)
    at = at if _ok(at, n) else min(n - 1, int(n * 0.45))
    if wtype == 'blackout_open':
        at = 0
    last_w = wcr.get('last_word', at)
    last_w = last_w if _ok(last_w, n) and last_w >= at else at
    wc = {'type': wtype, 'at': at, 'last': last_w, 't': round(0.0 if wtype == 'blackout_open' else start(at), 2),
          'text': (wcr.get('text') or '').strip(), 'query': (wcr.get('query') or '').strip(), 'sample': wcr.get('sample'), 'note': wcr.get('note', '')}
    if wtype == 'sound_gag' and wc['sample'] not in SFX_VOCAB:
        wc['sample'] = 'impact_deep'
    if wtype == 'metaphor_stock' and not wc['query']:
        wtype = wc['type'] = 'negative_flash'
        notes.append('metaphor_stock without query -> negative_flash')
    if wtype == 'letterbox':
        wc['t'], wc['e'] = round(start(at), 2), round(min(dur, max(end(last_w), start(at) + 2.0)) + 0.1, 2)
        wc['e'] = min(wc['e'], wc['t'] + 6.0)
    else:
        wc['e'] = round(wc['t'] + {'blackout_open': 0.5, 'silence_gag': 0.1, 'negative_flash': 0.14, 'echo_caption': 0.9, 'sound_gag': 0.6,
                                   'metaphor_stock': 1.4, 'punch_cut': 0.9, 'redact': 0.6}.get(wtype, 0.5), 2)
    if wtype != 'blackout_open' and wc['t'] < HOOK_T1 + 0.3:
        wc['t'] = round(HOOK_T1 + 0.3, 2)
        wc['e'] = round(wc['t'] + (wc['e'] - start(at)), 2)
    wc['window'] = [round(wc['t'] - (0.75 if wtype == 'silence_gag' else 0.3), 2), round(wc['e'] + 0.3, 2)]

    # inserts: allowed kinds only, spaced, not on the hook / the wildcard
    ins, last_end = [], HOOK_T1 + 0.6
    cand = sorted((x for x in raw.get('inserts', []) if x.get('kind') in pr['kinds'] and _ok(x.get('first'), n)), key=lambda x: start(x['first']))
    for x in cand:
        k = x['kind']
        f = x['first']
        l = x['last'] if _ok(x.get('last'), n) and x['last'] >= f else f
        t = max(start(f) - 0.05, HOOK_T1 + 0.5)
        d = max(INS_DUR[k], min(end(l) - start(f) + 0.4, 3.6)) if k in ('punch', 'stamp', 'wave', 'stock') else INS_DUR[k]
        e = min(t + d, dur - 0.3)
        if t < last_end + 0.8 or e - t < 0.9:
            continue
        if not (e < wc['window'][0] - 0.3 or t > wc['window'][1] + 0.3) and wtype != 'letterbox':
            continue
        p = {'kind': k, 't': round(t, 2), 'e': round(e, 2), 'first': f, 'last': l}
        if k in ('punch', 'stamp'):
            p['text'] = (x.get('text') or ' '.join(W[i]['w'].strip(',.!?…') for i in range(f, min(l, f + 1) + 1))).strip()[:16].upper()
        elif k == 'stat':
            if x.get('value') is None:
                continue
            p.update(value=x['value'], prefix=x.get('prefix', ''), suffix=x.get('suffix', ''), label=(x.get('label') or '')[:26])
        elif k == 'stock':
            if not x.get('query'):
                continue
            p['query'] = x['query']
        elif k == 'compare':
            if not (x.get('left') and x.get('right')):
                continue
            p.update(left=x['left'], right=x['right'])
        elif k == 'checklist':
            if not x.get('items') or len(x['items']) < 2:
                continue
            p['items'] = x['items'][:3]
        elif k == 'notify':
            p.update(title=(x.get('title') or '')[:22], text=(x.get('text') or '')[:40])
        ins.append(p)
        last_end = e
    for i, p in enumerate(ins, 1):
        p['n'] = i
    if wtype == 'metaphor_stock':                      # the wildcard is itself a stock cutaway: give it a slot number
        pass
    ids = {i['id']: i for i in raw.get('ideas', []) if isinstance(i, dict) and 'id' in i}
    return {'preset': pr['id'], 'dur': dur, 'seed': seed, 'hook': {'lines': hook_lines, 'first': hf, 'last': hl},
            'keys': keys, 'emo': emo, 'nums': nums, 'big': big, 'inserts': ins, 'wildcard': wc, 'fixes': raw.get('word_fixes', []),
            'ideas': raw.get('ideas', []), 'picked': raw.get('picked'), 'picked_idea': (ids.get(raw.get('picked')) or {}).get('idea'),
            'summary': raw.get('summary', ''), 'notes': notes}


def fallback_raw(an, pr, seed):
    """rules-based plan: first words as hook, longest words as keys, a numeric stat / punch as inserts, a rotating cheap wildcard"""
    W = an['words']
    n = len(W)
    rng = random.Random(seed)
    good = [i for i in range(n) if len(re.sub(r'\W', '', W[i]['w'])) >= 6 and W[i]['w'].strip(',.!?…').lower() not in STOP]
    keys = sorted(rng.sample(good, min(12, len(good)))) if good else []
    nums = [i for i in range(n) if re.search(r'\d', W[i]['w'])]
    ins = []
    span = an['dur'] - 8
    slots = [5 + span * k / 4 for k in range(1, 4)]
    for s in slots:
        i = min(range(n), key=lambda j: abs(W[j]['s'] - s)) if n else 0
        if nums and not any(x['kind'] == 'stat' for x in ins) and 'stat' in pr['kinds']:
            j = nums[0]
            ins.append({'kind': 'stat', 'first': j, 'last': j, 'value': float(re.sub(r'\D', '', W[j]['w']) or 0) or 1, 'label': ''})
        else:
            kk = 'punch' if 'punch' in pr['kinds'] else pr['kinds'][0]
            if kk == 'punch' and i in keys:
                ins.append({'kind': 'punch', 'first': i, 'last': i, 'text': W[i]['w'].strip(',.!?…')})
    wt = rng.choice(['negative_flash', 'punch_cut', 'letterbox', 'echo_caption'])
    at = keys[len(keys) // 2] if keys else min(n - 1, 10)
    return {'ideas': [], 'picked': None, 'wildcard': {'type': wt, 'at_word': at, 'last_word': min(n - 1, at + 6)},
            'hook': {'lines': [], 'first': 0, 'last': min(n - 1, 8)}, 'keys': keys, 'emo': [], 'nums': nums, 'big_word': None,
            'inserts': ins, 'word_fixes': [], 'summary': ''}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('analysis')
    ap.add_argument('--preset', required=True)
    ap.add_argument('--out', required=True)
    ap.add_argument('--payload', default=None)
    ap.add_argument('--model', default=os.environ.get('PLAN_MODEL') or 'opus')
    ap.add_argument('--timeout', type=int, default=int(os.environ.get('PLAN_TIMEOUT_SEC') or 420))
    ap.add_argument('--seed', default='0')
    ap.add_argument('--no-claude', action='store_true')
    a = ap.parse_args()
    an = json.loads(Path(a.analysis).read_text(encoding='utf-8'))
    pr = PRESETS[a.preset]
    ctx = json.loads(Path(a.payload).read_text(encoding='utf-8')) if a.payload and Path(a.payload).exists() else {}
    seed = a.seed
    raw, info, planner = None, {}, 'claude'
    if not a.no_claude and an['words']:
        prompt = build_prompt(an, pr, ctx)
        sch = schema(pr)
        for attempt in (1, 2):
            try:
                raw, info = call_claude(prompt, sch, a.model, a.timeout)
                info['attempt'] = attempt
                break
            except Exception as e:                       # noqa
                info = {'error': scrub(str(e))[:300], 'attempt': attempt}
                print(f'[plan] attempt {attempt} failed: {info["error"]}', flush=True)
    if raw is None:
        planner = 'fallback'
        raw = fallback_raw(an, pr, seed)
    plan = normalise(raw, an, pr, seed)
    plan['planner'] = planner
    plan['planner_meta'] = info
    Path(a.out).write_text(json.dumps(plan, ensure_ascii=False, indent=1), encoding='utf-8')
    print(f"[plan] planner={planner} preset={pr['id']} wildcard={plan['wildcard']['type']}@{plan['wildcard']['t']}s inserts={[(i['kind'], i['t']) for i in plan['inserts']]} "
          f"cost_usd={info.get('cost_usd')} tokens_in={info.get('input_tokens')} out={info.get('output_tokens')} wall_s={info.get('wall_s')}")


if __name__ == '__main__':
    main()

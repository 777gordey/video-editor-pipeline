#!/usr/bin/env python3
"""ONE headless `claude -p` planning call per clip -> plan.json. Falls back to a rules-based plan if the call fails (a clip never fails because of the planner).
The planner THINKS about the clip first (core idea / emotion / tone), invents 5 unconventional concepts that come from THIS clip's meaning, picks one and
builds the whole edit around it. The preset is only the visual toolbox.
usage: plan.py ANALYSIS.json --preset dark|proof|slab --out plan.json [--payload payload.json] [--clip-no N]"""
import argparse, json, os, random, re, shutil, subprocess, sys, tempfile, time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from presets import PRESETS, WILDCARDS, SFX_VOCAB, MUSIC_ALL, MUSIC_HELP, STYLE_HELP
from lib import STOP

KIND_HELP = {
    "punch": "text (1-2 words, <=14 chars, from the speech) — giant word slammed mid-frame on first..last",
    "stamp": "text (1-2 words, <=16 chars) — a hard rubber-stamp slam, tilted, for a verdict/label word",
    "stat": "value (a number the speaker SAYS), prefix?, suffix? (e.g. '₽','%','x','дн'), label (<=24 chars) — animated counter; ONLY if the speaker says a number",
    "stock": "query (2-4 English words, a concrete OBJECT or scene, no people close-ups, no logos) — 1.5 s full-frame cutaway as a visual metaphor",
    "wave": "no params — thin voice waveform line (calm moment, a 'listen' beat)",
    "compare": "left (<=18 chars, the bad option), right (<=24 chars, the good option) — two rows, bad crossed out, good ticked; ONLY for a real contrast in the speech",
    "checklist": "items (2-3 strings <=22 chars, from the speech) — ticks appear one by one; ONLY for a real enumeration",
    "notify": "title (<=20 chars), text (<=40 chars) — a notification card; for a message/call/booking moment",
}
INS_DUR = {"punch": 1.15, "stamp": 1.3, "stat": 2.3, "stock": 1.5, "wave": 1.6, "compare": 3.0, "checklist": 3.4, "notify": 2.6}
HOOK_POPS = (0.20, 0.62, 1.04)
HOOK_T0, HOOK_EXIT, HOOK_T1 = 0.10, 2.45, 2.70
NUMWORDS = ('один', 'одн', 'два', 'две', 'три', 'тр', 'четыр', 'пят', 'шест', 'сем', 'восем', 'девят', 'десят', 'сто', 'сот', 'тысяч', 'миллион', 'миллиард',
            'двадцат', 'тридцат', 'сорок', 'пятьдесят', 'шестьдесят', 'семьдесят', 'восемьдесят', 'девяносто', 'полтор', 'процент', 'раз')
CONCEPT_KINDS = ["opening", "metaphor", "sound_gag", "transition", "pattern_break"]
TONES = ["deadpan", "urgent", "funny", "serious", "educational", "provocative", "warm", "confident", "reflective", "excited"]


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


def n_inserts(dur):
    return 3 if dur < 25 else 4 if dur < 60 else 5


def build_prompt(an, pr, ctx):
    words = an['words']
    n_ins = n_inserts(an['dur'])
    kinds = "\n".join(f"  - {k}: {KIND_HELP[k]}" for k in pr['kinds'])
    allowed = ctx.get('allowed_wildcards') or list(WILDCARDS)
    wc = "\n".join(f"  - {k}: {WILDCARDS[k]}" for k in allowed)
    sfx = ", ".join(f"{k} ({v})" for k, v in SFX_VOCAB.items())
    music = "\n".join(f"  - {k}: {v}" for k, v in MUSIC_HELP.items())
    style = "\n".join(f"  - {k}: {v}" for k, v in STYLE_HELP.items())
    cuts = ", ".join(f"{c:.1f}" for c in an['cuts']) or "none"
    prior = ctx.get('prior_concepts') or []
    prior_txt = ("\nУЖЕ ЗАНЯТЫЕ КОНЦЕПЦИИ ДРУГИХ КЛИПОВ ПАЧКИ (не копируй и не повторяй их идею, структуру хука, набор вставок, переход; твоя концепция должна быть ЯВНО другой по смыслу, а не по цвету):\n"
                 + "\n".join(f"  · {x}" for x in prior)) if prior else ""
    avoid = ctx.get('avoid_note') or ''
    return f"""Ты — смелый, думающий монтажёр вертикальных видео (Reels). Клип: говорящая голова в реальной комнате, {an['dur']:.0f} с. Тема у каждого клипа своя.
Пресет «{pr['name']}» — это ТОЛЬКО визуальный набор инструментов (шрифты, цвет, звуковая палитра). Что происходит в ролике, решает КОНЦЕПЦИЯ, выросшая из смысла именно этого клипа.
Ниже транскрипт по предложениям, формат `idx:слово` ([№ @сек]). Реальные склейки исходника на секундах: {cuts}.

ЖЁСТКИЕ ПРАВИЛА (нарушение = решение выбрасывается):
 1. Единственный видеослой — реальная комната автора. Никаких вырезов человека, замены фона, плёнок поверх лица. Стоковый кадр — только короткая вставка на весь кадр (не под говорящим).
 2. Взрослый, мужской, жёсткий вкус: никаких мультяшных стикеров, маскотов, эмодзи, пастели, «милоты».
 3. Музыка слышна ≈ −11 дБ от голоса в речи и ≈ −6 дБ в хуке, эффекты ≈ −10 дБ от пика голоса — не предлагай то, что требует тишины надолго или оглушающих эффектов.
 4. Голос не трогаем по времени. Слова, цифры и факты — ТОЛЬКО из речи автора; не приписывай ему того, чего он не говорил (в хуке, в тексте вставок, в подписях).
 5. Все idx должны существовать в транскрипте.
 6. ЗАПРЕЩЕНО банальное: «зум на слове», «whoosh на каждое слово», стоковый «успех/деньги/рукопожатие», рамки «лайк/подписка», любая идея, которую делает любой редактор.{prior_txt}{(chr(10) + avoid) if avoid else ''}

ШАГ 1 — ПОДУМАЙ О КЛИПЕ (поля tone, core_idea, emotion):
  а) какая главная мысль клипа, какая эмоция и какой тон (deadpan / urgent / funny / serious / educational / provocative / warm / confident / reflective / excited)?
ШАГ 2 — 5 НЕОБЫЧНЫХ КОНЦЕПЦИЙ (поле concepts). Каждая вырастает из СМЫСЛА этого клипа (поле from_speech — слова/мысль автора, из которых она выросла) и относится к одному из видов:
  opening (неожиданное открытие), metaphor (визуальная метафора того, что он говорит), sound_gag (звуковой гэг), transition (яркий переход), pattern_break (намеренный слом ритма).
  Для каждой отметь rules_ok (real_room_only, adult_masculine, audible_levels, not_generic) и boldness 1-5. Концепция должна быть исполнима из инструментов ниже.
ШАГ 3 — ВЫБЕРИ ОДНУ (picked = id) — ту, что лучше всего подходит клипу, и ПОСТРОЙ ВЕСЬ МОНТАЖ вокруг неё: wildcard (центральный приём), вставки, хук, камера, музыка, переходы — всё работает на эту концепцию. concept_name — короткое имя (2-5 слов), concept_pitch — одной фразой, почему она подходит клипу.

ИНСТРУМЕНТЫ
 wildcard (центральный приём клипа; для ЭТОГО клипа разрешены ТОЛЬКО типы: {', '.join(allowed)}; все 5 концепций должны быть исполнимы одним из них):
{wc}
 Звуки для sound_gag (sample): {sfx}
 style.camera / style.hook_layout / style.stock_transition:
{style}
 style.music (подбери под тон клипа):
{music}
 hook: 2-3 коротких строки заголовка (каждая ≤ 18 символов) из реальных слов автора из первых ~12 с речи; first/last — idx опорных слов. Хук понятен без контекста, обещает результат/цифру/ошибку/секрет или задаёт острый вопрос; строки не заканчиваются предлогом/союзом. Структура хука тоже часть концепции (вопрос / утверждение / контраст / обрыв).
 keys: idx 8-14 ключевых слов для выделения в субтитрах (не служебные), emo: до 4 эмоциональных слов, nums: idx слов-цифр.
 big_word: idx слова-кульминации в последних 25% клипа (или null).
 inserts: ровно {n_ins} вставок (не считая wildcard), каждая привязана к словам (first/last idx) и работает на концепцию. Допустимые kind для пресета:
{kinds}
   Вставки разнесены минимум на 3.5 с, не раньше 3-й секунды, не на хуке, не на момент wildcard. Разные kind — предпочтительнее одного и того же.
 word_fixes: [{{idx, text}}] только очевидные ошибки распознавания (имена, термины) — иначе пусто.
 summary: одна строка — о чём клип.

ТРАНСКРИПТ:
{transcript_text(words)}

Верни ТОЛЬКО JSON по схеме."""


def schema(pr, allowed=None):
    allowed = allowed or list(WILDCARDS)
    ins = {"type": "object", "required": ["kind", "first", "last"], "properties": {
        "kind": {"enum": pr['kinds']}, "first": {"type": "integer", "minimum": 0}, "last": {"type": "integer", "minimum": 0},
        "text": {"type": "string", "maxLength": 20}, "value": {"type": "number"}, "prefix": {"type": "string", "maxLength": 4},
        "suffix": {"type": "string", "maxLength": 6}, "label": {"type": "string", "maxLength": 30}, "query": {"type": "string", "maxLength": 50},
        "left": {"type": "string", "maxLength": 24}, "right": {"type": "string", "maxLength": 30}, "title": {"type": "string", "maxLength": 24},
        "items": {"type": "array", "items": {"type": "string", "maxLength": 26}, "maxItems": 3}}}
    return {"type": "object", "required": ["tone", "core_idea", "emotion", "concepts", "picked", "concept_name", "wildcard", "hook", "keys", "inserts", "style"], "properties": {
        "tone": {"type": "string", "maxLength": 40}, "core_idea": {"type": "string", "maxLength": 300}, "emotion": {"type": "string", "maxLength": 80},
        "concepts": {"type": "array", "minItems": 5, "maxItems": 5, "items": {"type": "object", "required": ["id", "name", "kind", "description", "from_speech", "rules_ok", "boldness"], "properties": {
            "id": {"type": "integer"}, "name": {"type": "string", "maxLength": 50}, "kind": {"enum": CONCEPT_KINDS},
            "description": {"type": "string", "maxLength": 320}, "from_speech": {"type": "string", "maxLength": 160},
            "rules_ok": {"type": "object", "properties": {"real_room_only": {"type": "boolean"}, "adult_masculine": {"type": "boolean"},
                                                          "audible_levels": {"type": "boolean"}, "not_generic": {"type": "boolean"}}},
            "boldness": {"type": "integer", "minimum": 1, "maximum": 5}}}},
        "picked": {"type": "integer"}, "concept_name": {"type": "string", "maxLength": 60}, "concept_pitch": {"type": "string", "maxLength": 240},
        "style": {"type": "object", "properties": {"camera": {"enum": ["calm", "normal", "aggressive", "locked"]}, "hook_layout": {"enum": ["stack", "single", "split"]},
                                                   "stock_transition": {"enum": ["whip", "zoom", "flash"]}, "music": {"enum": MUSIC_ALL}}},
        "wildcard": {"type": "object", "required": ["type", "at_word"], "properties": {
            "type": {"enum": allowed}, "at_word": {"type": "integer", "minimum": 0}, "last_word": {"type": "integer", "minimum": 0},
            "text": {"type": "string", "maxLength": 24}, "query": {"type": "string", "maxLength": 50}, "sample": {"type": "string"},
            "value_from": {"type": "integer"}, "value_to": {"type": "integer"}, "note": {"type": "string", "maxLength": 200}}},
        "hook": {"type": "object", "required": ["lines", "first", "last"], "properties": {
            "lines": {"type": "array", "minItems": 1, "maxItems": 3, "items": {"type": "string", "maxLength": 26}},
            "first": {"type": "integer", "minimum": 0}, "last": {"type": "integer", "minimum": 0},
            "promise": {"enum": ["result", "number", "mistake", "secret", "question", "claim", "contrast"]}}},
        "keys": {"type": "array", "items": {"type": "integer", "minimum": 0}, "maxItems": 24},
        "emo": {"type": "array", "items": {"type": "integer", "minimum": 0}, "maxItems": 6},
        "nums": {"type": "array", "items": {"type": "integer", "minimum": 0}, "maxItems": 10},
        "big_word": {"type": ["integer", "null"]},
        "inserts": {"type": "array", "items": ins, "maxItems": 7},
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


def _tok(w):
    return re.sub(r'[^\w]', '', w.lower())


def normalise(raw, an, pr, seed):
    W = an['words']
    n = len(W)
    dur = an['dur']
    notes = []
    start = lambda i: W[i]['s']
    end = lambda i: W[i]['e']
    spoken = [_tok(w['w']) for w in W]

    def grounded_text(text, near=None):
        """every meaningful token of an on-screen text must be a word the speaker said (prefix match, any place of the clip)"""
        toks = [_tok(t) for t in str(text).split()]
        toks = [t for t in toks if len(t) > 2 and not t.isdigit()]
        return all(any(s.startswith(t[:4]) or t.startswith(s[:4]) for s in spoken if len(s) > 2) for t in toks)

    def words_at(f, l, cap=3):
        return " ".join(W[i]['w'].strip(',.!?…:;') for i in range(f, min(l, f + cap - 1) + 1))

    # hook: text must come from the speaker's own words
    hk = raw.get('hook') or {}
    hook_lines = [str(x).strip() for x in hk.get('lines', []) if str(x).strip()][:3]
    hf, hl = hk.get('first', 0), hk.get('last', 0)
    support = [_tok(W[i]['w']) for i in range(max(0, (hf if _ok(hf, n) else 0) - 3), min(n, (hl if _ok(hl, n) else 12) + 4))]
    support += [_tok(W[i]['w']) for i in range(min(n, 45)) if W[i]['s'] < 14]

    def hook_grounded(line):
        toks = [t for t in (_tok(x) for x in line.split()) if len(t) > 2 and not t.isdigit()]
        return all(any(s.startswith(t[:4]) or t.startswith(s[:4]) for s in support if s) for t in toks)
    if not hook_lines or not all(hook_grounded(x) for x in hook_lines):
        notes.append('hook not grounded in the speech -> verbatim fallback')
        first = [i for i in range(n) if _tok(W[i]['w']) not in ('э', 'эм', 'ну')][:9]
        chunks = [first[0:3], first[3:6], first[6:9]]
        hook_lines = [" ".join(W[i]['w'].strip(',.!?…') for i in c) for c in chunks if c]
    hook_lines = [x.strip(' ,.-—') for x in hook_lines][:3]

    keys = sorted({i for i in raw.get('keys', []) if _ok(i, n) and _tok(W[i]['w']) not in STOP})
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
    if wtype in ('split_black', 'timer', 'echo_caption') and not grounded_text(wc['text']):
        notes.append(f'{wtype} text not grounded -> taken from the words')
        wc['text'] = words_at(at, last_w, 4 if wtype == 'split_black' else 1)
    if wtype == 'split_black' and not wc['text']:
        wc['text'] = words_at(at, last_w, 4)
    if wtype == 'sound_gag' and wc['sample'] not in SFX_VOCAB:
        wc['sample'] = 'impact_deep'
    if wtype == 'metaphor_stock' and not wc['query']:
        wtype = wc['type'] = 'negative_flash'
        notes.append('metaphor_stock without query -> negative_flash')
    if wtype == 'timer':
        vf, vt = wcr.get('value_from'), wcr.get('value_to')
        wc['value_from'] = vf if isinstance(vf, int) else 0
        wc['value_to'] = vt if isinstance(vt, int) else wc['value_from'] + 10
    if wtype in ('letterbox', 'timer'):
        wc['t'] = round(start(at), 2)
        wc['e'] = round(min(dur - 0.2, max(end(last_w), start(at) + 2.0) + 0.1), 2)
        wc['e'] = min(wc['e'], wc['t'] + (6.0 if wtype == 'letterbox' else 3.6))
    else:
        wc['e'] = round(wc['t'] + {'blackout_open': 0.5, 'silence_gag': 0.1, 'negative_flash': 0.14, 'echo_caption': 0.9, 'sound_gag': 0.6,
                                   'metaphor_stock': 1.4, 'punch_cut': 0.9, 'split_black': 0.9}.get(wtype, 0.5), 2)
    if wtype != 'blackout_open' and wc['t'] < 3.0:
        shift = 3.0 - wc['t']
        wc['t'] = 3.0
        wc['e'] = round(wc['e'] + shift, 2)
    wc['window'] = [round(wc['t'] - (0.75 if wtype == 'silence_gag' else 0.3), 2), round(wc['e'] + 0.3, 2)]

    # inserts: allowed kinds only, spaced, grounded, not on the hook / the wildcard
    ins, last_end = [], 3.0
    cand = sorted((x for x in raw.get('inserts', []) if x.get('kind') in pr['kinds'] and _ok(x.get('first'), n)), key=lambda x: start(x['first']))
    for x in cand:
        k = x['kind']
        f = x['first']
        l = x['last'] if _ok(x.get('last'), n) and x['last'] >= f else f
        t = max(start(f) - 0.05, 3.0)
        d = max(INS_DUR[k], min(end(l) - start(f) + 0.4, 3.6)) if k in ('punch', 'stamp', 'wave', 'stock') else INS_DUR[k]
        e = min(t + d, dur - 0.3)
        if t < last_end + 0.6 or e - t < 0.9:
            continue
        if not (e < wc['window'][0] - 0.3 or t > wc['window'][1] + 0.3) and wtype not in ('letterbox', 'timer'):
            continue
        if wtype in ('letterbox', 'timer') and not (e < wc['window'][0] - 0.2 or t > wc['window'][1] + 0.2) and k in ('stat', 'compare', 'checklist', 'notify', 'wave'):
            continue
        p = {'kind': k, 't': round(t, 2), 'e': round(e, 2), 'first': f, 'last': l}
        if k in ('punch', 'stamp'):
            txt = (x.get('text') or '').strip()
            if not txt or not grounded_text(txt):
                txt = words_at(f, l, 2)
            p['text'] = txt[:16].upper()
        elif k == 'stat':
            near = ' '.join(W[i]['w'] for i in range(max(0, f - 3), min(n, l + 4))).lower()
            if x.get('value') is None or not (re.search(r'\d', near) or any(w in near for w in NUMWORDS)):
                notes.append('stat dropped: no number near the words')
                continue
            lab = (x.get('label') or '')[:26]
            p.update(value=x['value'], prefix=x.get('prefix', ''), suffix=x.get('suffix', ''), label=lab if grounded_text(lab) else '')
        elif k == 'stock':
            if not x.get('query'):
                continue
            p['query'] = x['query']
        elif k == 'compare':
            if not (x.get('left') and x.get('right')) or not (grounded_text(x['left']) and grounded_text(x['right'])):
                notes.append('compare dropped: not grounded')
                continue
            p.update(left=x['left'], right=x['right'])
        elif k == 'checklist':
            its = [i for i in (x.get('items') or []) if grounded_text(i)]
            if len(its) < 2:
                notes.append('checklist dropped: not grounded')
                continue
            p['items'] = its[:3]
        elif k == 'notify':
            if not (grounded_text(x.get('title') or '') and grounded_text(x.get('text') or '')):
                notes.append('notify dropped: not grounded')
                continue
            p.update(title=(x.get('title') or '')[:22], text=(x.get('text') or '')[:40])
        ins.append(p)
        last_end = e
    for i, p in enumerate(ins, 1):
        p['n'] = i
    st = raw.get('style') or {}
    style = {'camera': st.get('camera') if st.get('camera') in ('calm', 'normal', 'aggressive', 'locked') else 'normal',
             'hook_layout': st.get('hook_layout') if st.get('hook_layout') in ('stack', 'single', 'split') else 'stack',
             'stock_transition': st.get('stock_transition') if st.get('stock_transition') in ('whip', 'zoom', 'flash') else 'zoom',
             'music': st.get('music') if st.get('music') in MUSIC_ALL else pr['music'][0]}
    cons = {c['id']: c for c in raw.get('concepts', raw.get('ideas', [])) if isinstance(c, dict) and 'id' in c}
    pc = cons.get(raw.get('picked')) or {}
    return {'preset': pr['id'], 'dur': dur, 'seed': seed, 'hook': {'lines': hook_lines, 'first': hf, 'last': hl, 'promise': hk.get('promise')},
            'keys': keys, 'emo': emo, 'nums': nums, 'big': big, 'inserts': ins, 'wildcard': wc, 'style': style, 'fixes': raw.get('word_fixes', []),
            'tone': raw.get('tone'), 'core_idea': raw.get('core_idea'), 'emotion': raw.get('emotion'),
            'concepts': raw.get('concepts', []), 'picked': raw.get('picked'), 'concept_name': raw.get('concept_name') or pc.get('name'),
            'concept_pitch': raw.get('concept_pitch'), 'concept_kind': pc.get('kind'), 'picked_idea': pc.get('description'),
            'summary': raw.get('summary', ''), 'notes': notes}


def fallback_raw(an, pr, seed, allowed=None):
    """rules-based plan (planner unavailable): first words as hook, longest words as keys, a numeric stat / punch as inserts, a cheap wildcard"""
    W = an['words']
    n = len(W)
    rng = random.Random(seed)
    good = [i for i in range(n) if len(re.sub(r'\W', '', W[i]['w'])) >= 6 and _tok(W[i]['w']) not in STOP]
    keys = sorted(rng.sample(good, min(12, len(good)))) if good else []
    nums = [i for i in range(n) if re.search(r'\d', W[i]['w'])]
    ins = []
    span = an['dur'] - 8
    for k in range(1, n_inserts(an['dur']) + 1):
        s = 3.5 + span * k / (n_inserts(an['dur']) + 1)
        i = min(range(n), key=lambda j: abs(W[j]['s'] - s)) if n else 0
        if nums and not any(x['kind'] == 'stat' for x in ins) and 'stat' in pr['kinds']:
            j = nums[0]
            ins.append({'kind': 'stat', 'first': j, 'last': j, 'value': float(re.sub(r'\D', '', W[j]['w']) or 0) or 1, 'label': ''})
        elif 'punch' in pr['kinds']:
            ins.append({'kind': 'punch', 'first': i, 'last': i, 'text': W[i]['w'].strip(',.!?…')})
    pool = [x for x in ['negative_flash', 'punch_cut', 'letterbox', 'echo_caption'] if not allowed or x in allowed] or ['negative_flash']
    at = keys[len(keys) // 2] if keys else min(n - 1, 10)
    return {'concepts': [], 'picked': None, 'wildcard': {'type': rng.choice(pool), 'at_word': at, 'last_word': min(n - 1, at + 6)},
            'hook': {'lines': [], 'first': 0, 'last': min(n - 1, 8)}, 'keys': keys, 'emo': [], 'nums': nums, 'big_word': None,
            'inserts': ins, 'word_fixes': [], 'summary': '', 'style': {}}


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
    ap.add_argument('--clip-no', type=int, default=0)
    a = ap.parse_args()
    an = json.loads(Path(a.analysis).read_text(encoding='utf-8'))
    pr = PRESETS[a.preset]
    ctx = json.loads(Path(a.payload).read_text(encoding='utf-8')) if a.payload and Path(a.payload).exists() else {}
    seed = a.seed
    if a.clip_no and not ctx.get('allowed_wildcards'):     # rotating window of 5 wildcard types: neighbours in the batch never compete for the same type
        names = list(WILDCARDS)
        k = (a.clip_no * 2) % len(names)
        ctx['allowed_wildcards'] = [names[(k + i) % len(names)] for i in range(5)]
    raw, info, planner = None, {}, 'claude'
    if not a.no_claude and an['words']:
        prompt = build_prompt(an, pr, ctx)
        sch = schema(pr, ctx.get('allowed_wildcards'))
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
        raw = fallback_raw(an, pr, seed, ctx.get('allowed_wildcards'))
    plan = normalise(raw, an, pr, seed)
    plan['planner'] = planner
    plan['planner_meta'] = info
    plan['allowed_wildcards'] = ctx.get('allowed_wildcards')
    Path(a.out).write_text(json.dumps(plan, ensure_ascii=False, indent=1), encoding='utf-8')
    print(f"[plan] planner={planner} preset={pr['id']} concept={plan.get('concept_name')!r} wildcard={plan['wildcard']['type']}@{plan['wildcard']['t']}s "
          f"inserts={[(i['kind'], i['t']) for i in plan['inserts']]} cost_usd={info.get('cost_usd')} tokens_in={info.get('input_tokens')} out={info.get('output_tokens')} wall_s={info.get('wall_s')}")


if __name__ == '__main__':
    main()

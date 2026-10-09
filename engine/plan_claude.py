#!/usr/bin/env python3
"""Один headless-вызов Claude Code на раннере: выборы для всех 5 версий -> plans.json.

Авторизация: переменная CLAUDE_CODE_OAUTH_TOKEN (токен подписки из `claude setup-token`,
GitHub Secret). Токен нигде не печатается: вывод CLI фильтруется.
Модель — настройка: env PLAN_MODEL, иначе engine/config.json["PLAN_MODEL"].
Любая неудача (логин, лимит, таймаут, мусор) -> plans.json = {"_fallback": причина}
и строка "PLAN FALLBACK: <причина>"; render-джобы тогда строят план по правилам.
"""
import argparse
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

from jsonschema import validate, ValidationError

from common import CONFIG, load_json, save_json, log
from plan import ICONS, GKINDS
from styles import STYLES
import hookcheck

MAX_TURNS = int(CONFIG.get("PLAN_MAX_TURNS", 3))
TIMEOUT = int(CONFIG.get("PLAN_TIMEOUT_SEC", 600))

VERSION_SCHEMA = {
    "type": "object",
    "required": ["hook", "emphasis", "graphics", "sfx"],
    "properties": {
        "hook": {"type": "object", "required": ["first", "last", "text"],
                 "properties": {"first": {"type": "integer", "minimum": 0}, "last": {"type": "integer", "minimum": 0},
                                "text": {"type": "string", "minLength": 3, "maxLength": 60},
                                "promise": {"enum": ["result", "number", "mistake", "secret", "question"]},
                                "why": {"type": "string", "maxLength": 200}}},
        "emphasis": {"type": "array", "items": {"type": "integer", "minimum": 0}},
        "graphics": {"type": "array", "items": {
            "type": "object", "required": ["word", "kind"],
            "properties": {"word": {"type": "integer", "minimum": 0}, "kind": {"enum": GKINDS},
                           "icon": {"enum": ICONS}, "num": {"type": "integer", "minimum": 1, "maximum": 9},
                           "text": {"type": "string", "maxLength": 40}}}},
        "sfx": {"type": "array", "items": {
            "type": "object", "required": ["word", "kind"],
            "properties": {"word": {"type": "integer", "minimum": 0},
                           "kind": {"enum": ["hit", "whoosh", "pop", "riser", "click"]}}}},
    },
}
CUT_CATS = ["filler", "false_start", "repeat_take", "off_topic"]
CUTS_SCHEMA = {"type": "array", "maxItems": 40, "items": {
    "type": "object", "required": ["first", "last", "cat"],
    "properties": {"first": {"type": "integer", "minimum": 0}, "last": {"type": "integer", "minimum": 0},
                   "cat": {"enum": CUT_CATS}, "why": {"type": "string", "maxLength": 120}}}}
PLANS_SCHEMA = {"type": "object", "required": list(STYLES),
                "properties": {**{v: VERSION_SCHEMA for v in STYLES}, "cuts": CUTS_SCHEMA}}


def scrub(text: str) -> str:
    text = re.sub(r"sk-ant-[A-Za-z0-9_\-]+", "<token>", text or "")
    tok = os.environ.get("CLAUDE_CODE_OAUTH_TOKEN")
    return text.replace(tok, "<token>") if tok else text


CUTS_PROMPT = """
Дополнительно верни ключ cuts — список вырезов по транскрипту (слова, помеченные ~k:слово~, УЖЕ вырезаны автоматически —
не включай их и не используй в хуках/акцентах). Вырезай ТОЛЬКО то, в чём уверен:
- filler: слова-паразиты (э, эм, ну, типа, как бы, короче), если они не несут смысла;
- false_start: оборванные фразы и повторы-запинки (оставить нужно чистую версию);
- repeat_take: повторные дубли одной мысли (оставить лучший, обычно последний);
- off_topic: куски, не относящиеся к теме ролика (реплики в сторону, посторонние разговоры).
Каждый вырез: {first,last,cat,why} по idx слов. Если сомневаешься — НЕ вырезай. Не вырезай больше ~20% слов.
Хуки, акценты, графику и sfx выбирай только из слов, которые остаются."""


def build_prompt(tr, with_cuts=False) -> str:
    briefs = "\n".join(f"- {v}: «{s['name']}», угол хука: {s['angle']}; плотность графики {s['graphics_density']}; "
                       f"SFX-уровень {s['sfx_level']}" for v, s in STYLES.items())
    dur = tr["duration"]
    return f"""Ты монтажёр коротких вертикальных видео. В файле words.txt — транскрипт речи автора ({'СЫРОЙ, до нарезки' if with_cuts else 'клип уже смонтирован, без нарезки'}), по предложениям, формат `idx:слово`. Длительность клипа {dur:.0f} с.

Нужно составить выборы для ПЯТИ версий ролика и записать их ОДНИМ JSON-файлом plans.json (инструмент Write) в текущей
папке; тот же объект верни и как итоговый structured output. Версии:
{briefs}

Для каждой версии (ключи V1..V5):
- hook: {{first,last,text,promise,why}}. text — заголовок первых 2 секунд, ПРАВИЛА (все обязательны):
  (a) понятен без контекста: нет «он/она/его/это» без существительного, нет обрывка мысли; человек, не слышавший ролик, понимает, о чём речь;
  (b) обещает результат, цифру, ошибку или секрет, ЛИБО задаёт вопрос, ответ на который зрителю нужен (promise = result|number|mistake|secret|question);
  (c) не больше 6 слов И не длиннее 32 символов с пробелами (короткий хук читается крупно);
  (d) законченная мысль, не фрагмент предложения: не начинается с «и/а/но/что/чтобы/потому/который», не заканчивается предлогом, союзом, частицей или местоимением.
  text МОЖЕТ быть подтянутой перефразировкой сказанного (короче, резче), но НЕЛЬЗЯ утверждать то, чего нет в речи автора: цифры, сроки,
  результаты и факты — только из речи. first/last — фрагмент речи (до 12 слов, idx из транскрипта), на котором держится хук; он должен быть из
  первых ~15 секунд речи (время начала предложения указано как @сек). why — одна короткая строка: почему это цепляет.
  ПЯТЬ РАЗНЫХ углов, по версиям (угол каждой версии указан выше): contrarian claim = смелое утверждение против ожиданий;
  result first = сначала результат/выгода; question = острый вопрос зрителю; number+time = цифра/срок из речи (если в речи нет цифр или сроков —
  самое конкретное число/срок, которое есть, но не выдумывай); pain = боль/ошибка, которую зритель узнаёт. Хуки разных версий не должны повторять друг друга.
- emphasis: idx ключевых слов для выделения в субтитрах (примерно каждое 8-е слово; в «спокойных» версиях V3/V5 реже).
- graphics: события графики, привязанные к слову-триггеру (word = idx). kind: globe (мир/страны/интернет/масштаб),
  circle (перечисление, num = номер пункта, text до 3 слов), icon (icon из {', '.join(ICONS)}: деньги/скорость/время/риск/результат).
  Не больше (длительность/8 * плотность) штук на версию, только там, где слово реально про это; можно пусто.
- sfx: дополнительные звуковые акценты {{word, kind}} (hit|whoosh|pop|riser|click), 0-6 штук на версию, на смысловых словах.

{CUTS_PROMPT if with_cuts else ""}
Правила: все idx должны существовать в words.txt. Ничего не выдумывай и не меняй слова автора. Другие файлы не читай."""


def words_txt(tr, drop=None) -> str:
    w = tr["words"]
    drop = drop or {}
    tok = lambda k: (f"~{k}:{w[k]['w']}~" if k in drop else f"{k}:{w[k]['w']}")
    return chr(10).join(f"[{s['id']}{' @%.0fs' % s['t'] if 't' in s else ''}] " + " ".join(tok(k) for k in range(s["first"], s["last"] + 1))
                     for s in tr["sentences"])


def run_claude(tr, model: str, drop=None, with_cuts=False) -> dict:
    tmp = Path(tempfile.mkdtemp(prefix="plan_"))
    (tmp / "words.txt").write_text(words_txt(tr, drop), encoding="utf-8")
    cmd = ["claude", "-p", build_prompt(tr, with_cuts), "--model", model, "--max-turns", str(MAX_TURNS),
           "--allowedTools", "Read,Write", "--output-format", "json",
           "--json-schema", json.dumps(PLANS_SCHEMA)]
    log(f"[plan_claude] claude -p model={model} max-turns={MAX_TURNS} (words={len(tr['words'])})")
    try:
        p = subprocess.run(cmd, cwd=tmp, capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=TIMEOUT, env=dict(os.environ))
    except subprocess.TimeoutExpired:
        raise RuntimeError(f"claude -p timeout after {TIMEOUT}s")
    except FileNotFoundError:
        raise RuntimeError("claude CLI не установлен")
    out, err = scrub(p.stdout), scrub(p.stderr)
    meta = {}
    try:
        meta = json.loads(out)
    except ValueError:
        pass
    if p.returncode != 0 or meta.get("is_error"):
        msg = (meta.get("result") if isinstance(meta, dict) else None) or err or out
        raise RuntimeError(f"claude exit={p.returncode} subtype={meta.get('subtype')} {scrub(str(msg))[:300]}")
    log(f"[plan_claude] ok turns={meta.get('num_turns')} duration_ms={meta.get('duration_ms')} "
        f"cost_usd={meta.get('total_cost_usd')}")
    if (tmp / "plans.json").exists():
        data = json.loads((tmp / "plans.json").read_text(encoding="utf-8"))
    elif isinstance(meta.get("structured_output"), dict):
        data = meta["structured_output"]
    else:
        m = re.search(r"\{.*\}", str(meta.get("result", "")), re.S)
        if not m:
            raise RuntimeError("Claude не вернул plans.json / structured output")
        data = json.loads(m.group(0))
    shutil.rmtree(tmp, ignore_errors=True)
    return data


HOOK_ITEM = {"type": "object", "required": ["text", "first", "last", "promise", "why"],
             "properties": VERSION_SCHEMA["properties"]["hook"]["properties"]}


def call_json(prompt, schema, model, tmp, tools="Read"):
    """Один небольшой вызов claude -p -> dict (structured output). Бросает RuntimeError."""
    cmd = ["claude", "-p", prompt, "--model", model, "--max-turns", "6", "--allowedTools", tools,
           "--output-format", "json", "--json-schema", json.dumps(schema)]
    try:
        p = subprocess.run(cmd, cwd=tmp, capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=TIMEOUT, env=dict(os.environ))
    except subprocess.TimeoutExpired:
        raise RuntimeError(f"claude -p timeout after {TIMEOUT}s")
    out = scrub(p.stdout)
    meta = {}
    try:
        meta = json.loads(out)
    except ValueError:
        pass
    if p.returncode != 0 or meta.get("is_error"):
        raise RuntimeError(f"claude exit={p.returncode} {scrub(str(meta.get('result') or p.stderr or out))[:200]}")
    if isinstance(meta.get("structured_output"), dict):
        return meta["structured_output"]
    m = re.search(r"\{.*\}", str(meta.get("result", "")), re.S)
    if not m:
        raise RuntimeError("no JSON in the review answer")
    return json.loads(m.group(0))


HOOK_RULES = """ПРАВИЛА хука (все обязательны):
(a) понятен без контекста: нет «он/она/его/это» без существительного, нет обрывка мысли;
(b) обещает результат, цифру, ошибку или секрет, ЛИБО задаёт вопрос, ответ на который зрителю нужен;
(c) не больше 6 слов и не длиннее 32 символов с пробелами;
(d) законченная мысль, не фрагмент: не начинается с «и/а/но/что/чтобы/потому/который», не заканчивается предлогом/союзом/частицей/местоимением.
Можно перефразировать сказанное короче и резче, но НЕЛЬЗЯ утверждать то, чего нет в речи автора (цифры, сроки, результаты — только из речи).
Пять разных углов: V1 contrarian claim (смелое утверждение против ожиданий), V2 question (острый вопрос зрителю), V3 result first (сначала результат),
V4 number+time (цифра/срок из речи; если их нет — самое конкретное, что есть, без выдумки), V5 pain (боль/ошибка, которую зритель узнаёт)."""


def _sent_bounds(words):
    """Предложения для words.txt (те же правила, что prep.split_sentences; прямой импорт дал бы цикл)."""
    out, cur = [], []
    for i, w in enumerate(words):
        cur.append(i)
        gap = (words[i + 1]["start"] - w["end"]) if i + 1 < len(words) else 99
        if re.search(r"[.!?…]$", w["w"]) or gap >= 0.7:
            out.append((cur[0], cur[-1]))
            cur = []
    if cur:
        out.append((cur[0], cur[-1]))
    return out


def review_and_fix_hooks(data, words, drop, dur, model, rounds=2):
    """Проверка 5 хуков: (1) один вызов Claude-судьи, (2) программная проверка hookcheck,
    (3) до `rounds` перегенераций только провалившихся. Правит data in place, пишет data[v]['hook']['check']."""
    tr = {"duration": dur, "words": [{"w": w["w"]} for w in words],
          "sentences": [{"id": n, "first": a, "last": b, "t": words[a]["start"]} for n, (a, b) in enumerate(_sent_bounds(words))]}
    tmp = Path(tempfile.mkdtemp(prefix="hooks_"))
    (tmp / "words.txt").write_text(words_txt(tr, drop), encoding="utf-8")
    tw = [w["w"] for w in words]
    schema = lambda vs: {"type": "object", "required": list(vs), "properties": {v: HOOK_ITEM for v in vs}}

    def report():
        rep, seen = {}, []
        for v in STYLES:
            pr = hookcheck.problems(data[v]["hook"]["text"], tw, seen)
            seen.append(data[v]["hook"]["text"])
            if pr:
                rep[v] = pr
        return rep

    def apply(res, vs):
        for v in vs:
            h = res.get(v)
            if isinstance(h, dict) and isinstance(h.get("text"), str) and h["text"].strip():
                f, l = int(h.get("first", 0)), int(h.get("last", 0))
                if not (0 <= f <= l < len(words)):
                    f, l = data[v]["hook"]["first"], data[v]["hook"]["last"]
                keep = {k: h[k] for k in ("text", "promise", "why") if k in h}
                keep["text"] = re.sub(r"\s+[—–-]\s+", ", ", keep["text"]).strip()
                data[v]["hook"] = {**data[v]["hook"], **keep, "first": f, "last": l}

    try:
        prob = report()
        prompt = ("Ты строгий редактор хуков для коротких видео. Файл words.txt — транскрипт речи автора "
                  "(idx:слово по предложениям, @сек = время начала). Ниже текущие хуки пяти версий и проблемы, найденные автоматикой.\n\n"
                  + HOOK_RULES + "\n\n"
                  + "\n".join(f"{v}: «{data[v]['hook']['text']}» (promise={data[v]['hook'].get('promise')}; автоматика: "
                             f"{'; '.join(prob[v]) if v in prob else 'не нашла проблем'})" for v in STYLES)
                  + "\n\nСам проверь каждый хук по (a)-(d) и по фактам речи. Если хук хоть чем-то не проходит — перепиши; "
                    "если проходит — верни без изменений. Верни JSON {V1..V5: {text, first, last, promise, why}} "
                    "(first/last — idx слов речи, на которых держится хук, из первых ~15 с речи, до 12 слов).")
        apply(call_json(prompt, schema(STYLES), model, tmp), list(STYLES))
        log("[plan_claude] hook review done")
    except Exception as e:  # noqa — судья не обязателен: остаётся программная проверка
        print(f"PLAN WARNING: hook review call failed: {type(e).__name__}: {scrub(str(e))[:160]}", flush=True)
    for r in range(rounds + 1):
        prob = report()
        if not prob or r == rounds:
            break
        bad = list(prob)
        prompt = (f"Перепиши хуки только для версий {', '.join(bad)}. Файл words.txt — транскрипт речи автора "
                  f"(idx:слово, @сек = время начала предложения).\n\n{HOOK_RULES}\n\n"
                  + "\n".join(f"{v}: было «{data[v]['hook']['text']}» — отклонено: {'; '.join(prob[v])}" for v in bad)
                  + "\n\nТексты остальных версий (не повторяй их): "
                  + "; ".join(f"{v}: «{data[v]['hook']['text']}»" for v in STYLES if v not in bad)
                  + ". Верни JSON {" + ", ".join(bad) + ": {text, first, last, promise, why}}.")
        try:
            apply(call_json(prompt, schema(bad), model, tmp), bad)
            log(f"[plan_claude] hooks regenerated for {bad} (round {r + 1})")
        except Exception as e:  # noqa
            print(f"PLAN WARNING: hook regenerate failed: {type(e).__name__}: {scrub(str(e))[:160]}", flush=True)
            break
    prob = report()
    for v in STYLES:
        if v in prob:
            data[v]["hook"]["check"] = "FAILED: " + "; ".join(prob[v])
            print(f"HOOK CHECK FAILED {v}: «{data[v]['hook']['text']}» — {'; '.join(prob[v])}", flush=True)
        else:
            data[v]["hook"]["check"] = "ok"
    shutil.rmtree(tmp, ignore_errors=True)
    for v in STYLES:
        h = data[v]["hook"]
        print(f"HOOK {v}: «{h['text']}» [{h.get('promise')}] — {h.get('why', '')} ({h['check']})", flush=True)
    return data


def plan_raw(words, sents, drop, dur, with_cuts=True):
    """Один вызов Claude на СЫРОМ транскрипте (до нарезки): выборы для V1..V5 + вырезы (cuts) в индексах сырых слов.
    Возвращает dict или {"_fallback": причина} (с громкой строкой PLAN FALLBACK)."""
    tr = {"duration": dur, "words": [{"w": w["w"]} for w in words],
          "sentences": [{"id": n, "first": s_[0], "last": s_[-1], "t": words[s_[0]]["start"]} for n, s_ in enumerate(sents)]}
    model = os.environ.get("PLAN_MODEL") or CONFIG.get("PLAN_MODEL", "opus")
    try:
        if not os.environ.get("CLAUDE_CODE_OAUTH_TOKEN"):
            raise RuntimeError("CLAUDE_CODE_OAUTH_TOKEN не задан")
        data = run_claude(tr, model, drop=drop, with_cuts=with_cuts)
        validate(data, PLANS_SCHEMA)
        n = len(words)
        for v in STYLES:
            ch = data[v]
            idxs = [ch["hook"]["first"], ch["hook"]["last"], *ch["emphasis"], *(g["word"] for g in ch["graphics"]),
                    *(s_["word"] for s_ in ch["sfx"])]
            if any(i >= n for i in idxs):
                raise ValueError(f"{v}: индекс слова вне транскрипта")
            if words[ch["hook"]["first"]]["start"] > 25:
                print(f"PLAN WARNING: {v} hook starts at {words[ch['hook']['first']]['start']:.0f}s of raw speech (expected <15s)", flush=True)
        for c_ in data.get("cuts", []):
            if c_["first"] > c_["last"] or c_["last"] >= n:
                raise ValueError("cuts: плохой диапазон")
        if not with_cuts:
            data["cuts"] = []
        review_and_fix_hooks(data, words, drop, dur, model)
        return data
    except Exception as e:  # noqa
        reason = scrub(f"{type(e).__name__}: {str(e)[:300]}")
        print(f"PLAN FALLBACK: {reason}", flush=True)
        return {"_fallback": reason}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--transcript", default="out/transcript.json")
    ap.add_argument("--out", default="out/plans.json")
    a = ap.parse_args()
    tr = load_json(a.transcript)
    model = os.environ.get("PLAN_MODEL") or CONFIG.get("PLAN_MODEL", "opus")
    try:
        if not os.environ.get("CLAUDE_CODE_OAUTH_TOKEN"):
            raise RuntimeError("CLAUDE_CODE_OAUTH_TOKEN не задан")
        data = run_claude(tr, model)
        validate(data, PLANS_SCHEMA)
        n = len(tr["words"])
        for v, ch in data.items():
            idxs = [ch["hook"]["first"], ch["hook"]["last"], *ch["emphasis"], *(g["word"] for g in ch["graphics"]),
                    *(s["word"] for s in ch["sfx"])]
            if any(i >= n for i in idxs):
                raise ValueError(f"{v}: индекс слова вне транскрипта")
    except Exception as e:  # noqa — любая причина, не молча
        reason = scrub(f"{type(e).__name__}: {str(e)[:300]}")
        print(f"PLAN FALLBACK: {reason}", flush=True)
        data = {"_fallback": reason}
    save_json(a.out, data)
    log(f"[plan_claude] wrote {a.out} ({'fallback' if '_fallback' in data else 'claude plans for ' + ','.join(data)})")


if __name__ == "__main__":
    main()

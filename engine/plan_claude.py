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

MAX_TURNS = int(CONFIG.get("PLAN_MAX_TURNS", 3))
TIMEOUT = int(CONFIG.get("PLAN_TIMEOUT_SEC", 600))

VERSION_SCHEMA = {
    "type": "object",
    "required": ["hook", "emphasis", "graphics", "sfx"],
    "properties": {
        "hook": {"type": "object", "required": ["first", "last"],
                 "properties": {"first": {"type": "integer", "minimum": 0}, "last": {"type": "integer", "minimum": 0}}},
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
    return f"""Ты монтажёр коротких вертикальных видео. В файле words.txt — транскрипт речи автора ({'СЫРОЙ, до нарезки' if with_cuts else 'после нарезки и ускорения'}), по предложениям, формат `idx:слово`. Длительность клипа {dur:.0f} с.

Нужно составить выборы для ПЯТИ версий ролика и записать их ОДНИМ JSON-файлом plans.json (инструмент Write) в текущей
папке; тот же объект верни и как итоговый structured output. Версии:
{briefs}

Для каждой версии (ключи V1..V5):
- hook: {{first,last}} — подряд идущие слова ИЗ ТРАНСКРИПТА (last-first<=5, максимум 6 слов), слова не менять. Цепляющий
  заголовок под угол версии. Хуки разных версий должны ОТЛИЧАТЬСЯ.
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
    return chr(10).join(f"[{s['id']}] " + " ".join(tok(k) for k in range(s["first"], s["last"] + 1))
                     for s in tr["sentences"])


def run_claude(tr, model: str, drop=None, with_cuts=False) -> dict:
    tmp = Path(tempfile.mkdtemp(prefix="plan_"))
    (tmp / "words.txt").write_text(words_txt(tr, drop), encoding="utf-8")
    cmd = ["claude", "-p", build_prompt(tr, with_cuts), "--model", model, "--max-turns", str(MAX_TURNS),
           "--allowedTools", "Read,Write", "--output-format", "json",
           "--json-schema", json.dumps(PLANS_SCHEMA)]
    log(f"[plan_claude] claude -p model={model} max-turns={MAX_TURNS} (words={len(tr['words'])})")
    try:
        p = subprocess.run(cmd, cwd=tmp, capture_output=True, text=True, timeout=TIMEOUT, env=dict(os.environ))
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


def plan_raw(words, sents, drop, dur):
    """Один вызов Claude на СЫРОМ транскрипте (до нарезки): выборы для V1..V5 + вырезы (cuts) в индексах сырых слов.
    Возвращает dict или {"_fallback": причина} (с громкой строкой PLAN FALLBACK)."""
    tr = {"duration": dur, "words": [{"w": w["w"]} for w in words],
          "sentences": [{"id": n, "first": s_[0], "last": s_[-1]} for n, s_ in enumerate(sents)]}
    model = os.environ.get("PLAN_MODEL") or CONFIG.get("PLAN_MODEL", "opus")
    try:
        if not os.environ.get("CLAUDE_CODE_OAUTH_TOKEN"):
            raise RuntimeError("CLAUDE_CODE_OAUTH_TOKEN не задан")
        data = run_claude(tr, model, drop=drop, with_cuts=True)
        validate(data, PLANS_SCHEMA)
        n = len(words)
        for v in STYLES:
            ch = data[v]
            idxs = [ch["hook"]["first"], ch["hook"]["last"], *ch["emphasis"], *(g["word"] for g in ch["graphics"]),
                    *(s_["word"] for s_ in ch["sfx"])]
            if any(i >= n for i in idxs):
                raise ValueError(f"{v}: индекс слова вне транскрипта")
        for c_ in data.get("cuts", []):
            if c_["first"] > c_["last"] or c_["last"] >= n:
                raise ValueError("cuts: плохой диапазон")
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

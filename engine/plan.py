#!/usr/bin/env python3
"""plan.json для одной версии из РЕАЛЬНЫХ слов автора.

LLM (через scripts/openai_http.py) выбирает только: хук (<=6 слов подряд из
транскрипта), слова-акценты, триггеры графики. Всё остальное (раскадровка
камер, SFX, чанки субтитров) строит код детерминированно, привязывая события к
началам слов. Если баланс OpenAI пуст / вызов упал / ответ не прошёл схему —
правила и громкая строка "PLAN FALLBACK: <причина>".
"""
import argparse
import json
import os
import re
import sys
from pathlib import Path

from jsonschema import validate, ValidationError

from common import load_json, save_json, log
from styles import STYLES

ICONS = ["check", "warning", "money", "rocket", "bolt", "heart", "clock", "star", "fire", "target"]
GKINDS = ["globe", "circle", "icon"]

PLAN_SCHEMA = {
    "type": "object",
    "required": ["version", "source", "duration", "hook", "emphasis", "chunks", "cams", "snaps", "graphics", "sfx"],
    "properties": {
        "version": {"enum": list(STYLES)},
        "source": {"enum": ["llm", "rules"]},
        "fallback_reason": {"type": "string"},
        "duration": {"type": "number", "exclusiveMinimum": 0},
        "hook": {
            "type": "object", "required": ["text", "first", "last", "t0", "t1"],
            "properties": {
                "text": {"type": "string", "minLength": 1},
                "first": {"type": "integer", "minimum": 0}, "last": {"type": "integer", "minimum": 0},
                "t0": {"type": "number"}, "t1": {"type": "number", "maximum": 2.0},
            },
        },
        "emphasis": {"type": "array", "items": {"type": "integer", "minimum": 0}},
        "chunks": {"type": "array", "items": {
            "type": "object", "required": ["first", "last"],
            "properties": {"first": {"type": "integer"}, "last": {"type": "integer"}}}},
        "cams": {"type": "array", "items": {
            "type": "object", "required": ["t", "framing", "move"],
            "properties": {"t": {"type": "number", "minimum": 0},
                           "framing": {"enum": ["wide", "medium", "close"]},
                           "move": {"enum": ["cut", "whip"]}}}},
        "snaps": {"type": "array", "items": {
            "type": "object", "required": ["t"], "properties": {"t": {"type": "number", "minimum": 0}}}},
        "graphics": {"type": "array", "items": {
            "type": "object", "required": ["t", "kind", "word", "dur"],
            "properties": {"t": {"type": "number", "minimum": 0}, "kind": {"enum": GKINDS},
                           "word": {"type": "integer", "minimum": 0}, "dur": {"type": "number", "exclusiveMinimum": 0},
                           "text": {"type": "string", "maxLength": 40}, "num": {"type": "integer", "minimum": 1, "maximum": 9},
                           "icon": {"enum": ICONS}}}},
        "sfx": {"type": "array", "items": {
            "type": "object", "required": ["t", "kind", "gain"],
            "properties": {"t": {"type": "number", "minimum": 0},
                           "kind": {"enum": ["hit", "whoosh", "pop", "riser", "click"]},
                           "gain": {"type": "number", "minimum": 0, "maximum": 2}}}},
    },
}

STOP = {"это", "который", "которые", "когда", "потому", "поэтому", "просто", "вообще", "только", "очень", "конечно"}


def norm(w):
    return re.sub(r"[^\w]", "", w.lower().replace("ё", "е"))


# --------------------------------------------------------------- deterministic
def make_chunks(words, style, sents):
    maxw = style["cap_words"]
    chunks, cur = [], []
    sent_end = {s["last"] for s in sents}
    for i, w in enumerate(words):
        cur.append(i)
        nxt_gap = (words[i + 1]["start"] - w["end"]) if i + 1 < len(words) else 9
        chars = sum(len(words[k]["w"]) for k in cur)
        brk = (len(cur) >= maxw or i in sent_end or nxt_gap > 0.3 or re.search(r"[,;:.!?…]$", w["w"])
               or chars > 18)
        if brk:
            chunks.append({"first": cur[0], "last": cur[-1]})
            cur = []
    if cur:
        chunks.append({"first": cur[0], "last": cur[-1]})
    return chunks


def rule_emphasis(words, chunks):
    out, last_chunk = [], -9
    for ci, c in enumerate(chunks):
        if ci - last_chunk < 3:
            continue
        cand = [k for k in range(c["first"], c["last"] + 1)
                if (len(norm(words[k]["w"])) >= 7 and norm(words[k]["w"]) not in STOP) or re.search(r"\d", words[k]["w"])]
        if cand:
            out.append(max(cand, key=lambda k: (bool(re.search(r"\d", words[k]["w"])), len(norm(words[k]["w"])))))
            last_chunk = ci
    return out


KEYWORD_GRAPHICS = [
    (r"мир|страны|стран|глобальн|интернет|международ|планет", dict(kind="globe", text="")),
    (r"деньг|рубл|доход|заработ|прибыл|\$|₽|миллион|тысяч", dict(kind="icon", icon="money")),
    (r"быстр|скорост|мгновенн", dict(kind="icon", icon="bolt")),
    (r"ошибк|опасн|риск|внимани|проблем", dict(kind="icon", icon="warning")),
    (r"время|минут|час\b|часа|секунд", dict(kind="icon", icon="clock")),
    (r"цель|результат|точно", dict(kind="icon", icon="target")),
    (r"любов|любим|нравит", dict(kind="icon", icon="heart")),
    (r"запуск|старт|рост|масштаб", dict(kind="icon", icon="rocket")),
    (r"готово|правильн|работает|получилось", dict(kind="icon", icon="check")),
]
ORD = {"первое": 1, "первый": 1, "первая": 1, "второе": 2, "второй": 2, "вторая": 2, "третье": 3, "третий": 3,
       "третья": 3, "четвертое": 4, "четвертый": 4, "пятое": 5, "пятый": 5}


def rule_graphics(words, style, dur):
    max_n = max(1, int(dur / 8 * style["graphics_density"]))
    out = []
    for i, w in enumerate(words):
        n = norm(w["w"])
        if n in ORD:
            out.append(dict(word=i, kind="circle", num=ORD[n], text=""))
            continue
        for rx, g in KEYWORD_GRAPHICS:
            if re.search(rx, n):
                out.append(dict(word=i, **g))
                break
    return out[:max_n * 3]


def place_graphics(cands, words, style, dur):
    """Привязка к началу слова + разрежение по плотности."""
    gap = 2.4 / max(style["graphics_density"], 0.2)
    out, last = [], -99
    for g in sorted(cands, key=lambda g: g["word"]):
        t = words[g["word"]]["start"]
        if t < 1.0 or t > dur - 1.0 or t - last < gap:
            continue
        d = {"globe": 2.0, "circle": 1.7, "icon": 1.4}[g["kind"]]
        item = {"t": round(t, 3), "kind": g["kind"], "word": g["word"], "dur": d}
        if g["kind"] == "circle":
            item["num"] = int(g.get("num") or 1)
            if g.get("text"):
                item["text"] = str(g["text"])[:40]
        if g["kind"] == "icon":
            item["icon"] = g.get("icon") if g.get("icon") in ICONS else "star"
        if g["kind"] == "globe" and g.get("text"):
            item["text"] = str(g["text"])[:40]
        out.append(item)
        last = t
    return out


def snap_beat(t, beats, lo, tol=0.1):
    """Сдвиг реза на ближайший бит (не дальше tol), не раньше lo."""
    if not beats:
        return t
    b = min(beats, key=lambda x: abs(x - t))
    return round(b, 3) if abs(b - t) <= tol and b > lo else t


def make_cams(words, sents, style, dur, beats=None):
    framings = style["framings"]
    cands = [s["start"] for s in sents if s["start"] > 0.8]
    word_starts = [w["start"] for w in words]
    gap = style["cam_gap"]
    cams = [{"t": 0.0, "framing": framings[0], "move": "cut"}]
    last, n = 0.0, 0
    ts = []
    for t in cands:
        if t - last >= gap * 0.8 and t - last >= 1.2:
            ts.append(t)
            last = t
        elif t - last > gap + 0.4:
            ts.append(t)
            last = t
    # дозаполнение: слишком длинные куски без смены -> режем по ближайшему слову
    allts, last = [], 0.0
    for t in sorted(ts + [dur + 99]):
        while t - last > gap * 1.35 + 0.3:
            target = last + gap
            cand = [x for x in word_starts if abs(x - target) < 0.6 and x > last + 1.0]
            nt = min(cand, key=lambda x: abs(x - target)) if cand else target
            if nt >= dur - 0.6:
                break
            allts.append(nt)
            last = nt
        if t < dur - 0.6:
            allts.append(t)
            last = t
    prev = 0.0
    for k, t in enumerate(allts, 1):
        t = snap_beat(t, beats, prev + 0.8)
        prev = t
        whip = (style["id"] in ("V1", "V2", "V4")) and k % 3 == 0
        cams.append({"t": round(t, 3), "framing": framings[k % len(framings)], "move": "whip" if whip else "cut"})
    return cams


def make_snaps(words, emphasis, style, cams):
    if not style["snap_on_emph"]:
        return []
    out, last = [], -9
    cut_ts = [c["t"] for c in cams]
    for i in emphasis:
        t = words[i]["start"]
        if t - last >= 1.2 and all(abs(t - c) > 0.35 for c in cut_ts):
            out.append({"t": round(t, 3)})
            last = t
    return out


def make_sfx(plan, style, words):
    lvl = style["sfx_level"]
    sfx = [{"t": 0.05, "kind": "hit", "gain": round(1.0 * lvl, 2)}]
    for c in plan["cams"][1:]:
        if style["id"] in ("V1", "V2", "V4") or c["move"] == "whip":
            sfx.append({"t": round(max(0, c["t"] - 0.08), 3), "kind": "whoosh", "gain": round(0.8 * lvl, 2)})
    for s in plan["snaps"]:
        sfx.append({"t": s["t"], "kind": "hit", "gain": round(0.6 * lvl, 2)})
    for g in plan["graphics"]:
        sfx.append({"t": g["t"], "kind": "pop" if g["kind"] != "globe" else "riser", "gain": round(0.8 * lvl, 2)})
        if g["kind"] == "globe":
            sfx[-1]["t"] = round(max(0, g["t"] - 0.6), 3)
    return sorted(sfx, key=lambda x: x["t"])


# ------------------------------------------------------------------- hook / LLM
def rule_hook(words, sents, vidx):
    cand = []
    for s in sents[: max(3, int(len(sents) * 0.7))]:
        n = s["last"] - s["first"] + 1
        txt = s["text"]
        sc = (2 if re.search(r"\d", txt) else 0) + (1.5 if "?" in txt else 0) + (1 if 3 <= n <= 8 else 0) - 0.02 * s["id"]
        cand.append((sc, s))
    cand.sort(key=lambda x: -x[0])
    s = cand[vidx % len(cand)][1]
    first = s["first"]
    last = min(s["last"], first + 5)
    return first, last


def clean_hook_text(words, first, last):
    t = " ".join(w["w"] for w in words[first:last + 1])
    return re.sub(r"[,;:.]+$", "", t).strip()


def llm_choices(version, style, words, sents, dur):
    key = os.environ.get("OPENAI_API_KEY")
    if not key:
        raise RuntimeError("no OPENAI_API_KEY")
    from openai_http import openai_post
    listing = "\n".join(
        f"[{s['id']}] " + " ".join(f"{k}:{words[k]['w']}" for k in range(s["first"], s["last"] + 1)) for s in sents)
    max_g = max(1, int(dur / 8 * style["graphics_density"]))
    prompt = f"""Ты монтажёр коротких вертикальных видео. Ниже транскрипт речи автора (формат idx:слово по предложениям).
Стиль версии {version} «{style['name']}». Угол хука: {style['angle']}

Верни СТРОГО JSON без пояснений:
{{"hook":{{"first":int,"last":int}},
 "emphasis":[idx,...],
 "graphics":[{{"word":idx,"kind":"globe|circle|icon","icon":"{'|'.join(ICONS)}","num":1,"text":"до 3 слов"}}]}}

Правила:
- hook: подряд идущие слова ИЗ ТРАНСКРИПТА, не больше 6 слов (last-first<=5), должны звучать как цепляющий заголовок под этот угол. Слова не менять.
- emphasis: ключевые слова для выделения в субтитрах, примерно каждое 8-е слово, idx из транскрипта.
- graphics: не больше {max_g} штук, только где слово реально про это: globe — мир/страны/интернет/масштаб; circle — перечисление (num = номер пункта); icon — деньги/скорость/время/риск/результат/и т.п. word = idx слова-триггера. Если уместных мест нет — пустой список.

Транскрипт:
{listing}"""
    resp = openai_post({"model": "gpt-5.6-luna", "input": prompt}, key, timeout=90)
    body = resp.json()
    txt = "".join(c["text"] for it in body["output"] if it.get("type") == "message"
                  for c in it["content"] if c.get("type") == "output_text")
    m = re.search(r"\{.*\}", txt, re.S)
    if not m:
        raise ValueError("LLM returned no JSON")
    return json.loads(m.group(0))


def semantic_check(plan, n_words):
    h = plan["hook"]
    if not (0 <= h["first"] <= h["last"] < n_words):
        raise ValueError("hook indices out of range")
    if h["last"] - h["first"] + 1 > 6:
        raise ValueError("hook longer than 6 words")
    for i in plan["emphasis"]:
        if i >= n_words:
            raise ValueError("emphasis idx out of range")
    for g in plan["graphics"]:
        if g["word"] >= n_words:
            raise ValueError("graphics word idx out of range")


# ------------------------------------------------------------------------- main
def build_plan(version, tr, force_rules=False, beats=None):
    style = STYLES[version]
    words, sents, dur = tr["words"], tr["sentences"], tr["duration"]
    vidx = list(STYLES).index(version)
    source, reason = "llm", None
    try:
        if force_rules:
            raise RuntimeError("forced rules (--rules)")
        ch = llm_choices(version, style, words, sents, dur)
        hf, hl = int(ch["hook"]["first"]), int(ch["hook"]["last"])
        emph = sorted({int(i) for i in ch.get("emphasis", []) if 0 <= int(i) < len(words)})
        gcand = []
        for g in ch.get("graphics", []):
            k = g.get("kind")
            if k in GKINDS and 0 <= int(g.get("word", -1)) < len(words):
                gcand.append({"word": int(g["word"]), "kind": k, "icon": g.get("icon"), "num": g.get("num"),
                              "text": g.get("text", "")})
    except Exception as e:  # noqa — любая причина: нет ключа, баланс, сеть, мусор в ответе
        source, reason = "rules", f"{type(e).__name__}: {str(e)[:200]}"
        print(f"PLAN FALLBACK: {reason}", flush=True)
        hf, hl = rule_hook(words, sents, vidx)
        emph = None
        gcand = None
    chunks = make_chunks(words, style, sents)
    if emph is None:
        emph = rule_emphasis(words, chunks)
    if gcand is None:
        gcand = rule_graphics(words, style, dur)
    # хук не длиннее 6 слов и не дольше 2 c
    hl = min(hl, hf + 5)
    plan = {
        "version": version, "source": source, "duration": dur,
        "hook": {"text": clean_hook_text(words, hf, hl), "first": hf, "last": hl, "t0": 0.0, "t1": 2.0},
        "emphasis": emph, "chunks": chunks,
    }
    if reason:
        plan["fallback_reason"] = reason
    plan["cams"] = make_cams(words, sents, style, dur, beats)
    plan["snaps"] = make_snaps(words, emph, style, plan["cams"])
    plan["graphics"] = place_graphics(gcand, words, style, dur)
    plan["sfx"] = make_sfx(plan, style, words)
    try:
        validate(plan, PLAN_SCHEMA)
        semantic_check(plan, len(words))
    except (ValidationError, ValueError) as e:
        if source == "llm":      # LLM-ответ испортил план — откат на правила, не молча
            print(f"PLAN FALLBACK: validation: {str(e)[:200]}", flush=True)
            return build_plan(version, tr, force_rules=True, beats=beats)
        raise
    return plan


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("version", choices=list(STYLES))
    ap.add_argument("--transcript", default="out/transcript.json")
    ap.add_argument("--out", default="out")
    ap.add_argument("--rules", action="store_true")
    a = ap.parse_args()
    plan = build_plan(a.version, load_json(a.transcript), a.rules)
    Path(a.out).mkdir(parents=True, exist_ok=True)
    save_json(Path(a.out) / f"plan_{a.version}.json", plan)
    log(f"[plan {a.version}] source={plan['source']} hook=«{plan['hook']['text']}» "
        f"cams={len(plan['cams'])} snaps={len(plan['snaps'])} graphics={len(plan['graphics'])} sfx={len(plan['sfx'])}")


if __name__ == "__main__":
    main()

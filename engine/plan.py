#!/usr/bin/env python3
"""plan.json для одной версии из РЕАЛЬНЫХ слов автора.

Выборы (хук <=6 слов подряд из транскрипта, слова-акценты, триггеры графики,
доп. SFX-точки) приходят из ОДНОГО вызова Claude Code (plan_claude.py ->
plans.json на все 5 версий). Всё остальное (раскадровка камер, SFX, чанки
субтитров) строит код детерминированно, привязывая события к началам слов.
Нет выборов / ответ не прошёл схему — правила и громкая строка
"PLAN FALLBACK: <причина>".
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
        "source": {"enum": ["claude", "rules"]},
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
        idx = range(c["first"], c["last"] + 1)
        strong = [k for k in idx if NUM_RX.search(norm(words[k]["w"])) or MONEY_RX.search(norm(words[k]["w"]))
                  or PAIN_RX.search(norm(words[k]["w"]))]
        if strong:                                  # цифры, деньги, боль — акцент всегда
            out.append(strong[0])
            last_chunk = ci
            continue
        if ci - last_chunk < 3:
            continue
        cand = [k for k in idx if len(norm(words[k]["w"])) >= 7 and norm(words[k]["w"]) not in STOP]
        if cand:
            out.append(max(cand, key=lambda k: len(norm(words[k]["w"]))))
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
        if t < 2.3 or t > dur - 1.0 or t - last < gap:
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
NUM_RX = re.compile(r"\d|тысяч|миллион|миллиард|процент|рубл|доллар|евро|сотн|\$|₽|%")
MONEY_RX = re.compile(r"деньг|доход|заработ|прибыл|рубл|доллар|бюджет|цен[аыуе]|стоим|оплат|инвест")
PAIN_RX = re.compile(r"ошибк|проблем|потер|теряе|провал|никогда|ничего|нельзя|не получ|не смож|боль|страх|слив|неудач|трудн|сложн|мешает|причин|враг|обман")
CLAIM_RX = re.compile(r"секрет|главн|единственн|только|всегда|любой|каждый|важн|навык|правд|на самом деле|запомни|понима|научи")
WEAK_START = {"и", "а", "но", "что", "как", "в", "на", "с", "к", "у", "о", "по", "за", "из", "от", "до", "я", "ну", "вот", "это", "то", "же", "ли"}
WEAK_END = {"и", "а", "но", "что", "как", "в", "на", "с", "к", "у", "о", "по", "за", "из", "от", "до", "не", "же", "ли", "бы", "то", "который", "которым"}
FILLERS = {"э", "эм", "ну", "типа", "короче", "как", "бы"}
# углы подачи: веса признаков (num, money, pain, claim, question, you)
ANGLES = {
    "V1": dict(claim=1.6, pain=1.0, num=1.2, money=0.8, question=0.2, you=0.4),     # самое сильное утверждение
    "V2": dict(question=2.0, pain=1.8, you=1.0, claim=0.6, num=0.6, money=0.4),     # боль / вопрос зрителю
    "V3": dict(num=2.2, money=1.6, claim=1.0, pain=0.4, question=0.2, you=0.2),     # цифра / факт
    "V4": dict(claim=1.8, money=1.0, num=0.8, pain=0.6, question=0.2, you=0.2),     # смелый тезис
    "V5": dict(you=1.8, claim=1.0, pain=0.6, question=0.8, num=0.4, money=0.4),     # личное обращение
}


def _hook_candidates(words, sents, horizon=15.0):
    """Окна по 3-6 слов внутри предложений первых ~15 с (если слов мало — расширяем до всего клипа)."""
    out = []
    pool = [s for s in sents if words[s["first"]]["start"] < horizon] or sents[:3]
    for s in pool:
        for i in range(s["first"], s["last"] + 1):
            if i > s["first"] and not re.search(r"[,;:]$", words[i - 1]["w"]):
                continue                              # окно начинается с начала предложения или клаузы
            for n in range(3, 7):
                j = i + n - 1
                if j > s["last"]:
                    break
                ws = [norm(words[k]["w"]) for k in range(i, j + 1)]
                if ws[0] in WEAK_START or (ws[-1] in WEAK_END and not re.search(r"[,;:.!?…]$", words[j]["w"])) or any(x in FILLERS for x in ws):
                    continue
                if words[j]["end"] - words[i]["start"] > 3.6:
                    continue
                txt = " ".join(ws)
                raw = " ".join(words[k]["w"] for k in range(i, j + 1))
                f = dict(num=1.0 if NUM_RX.search(txt) else 0.0, money=1.0 if MONEY_RX.search(txt) else 0.0,
                         pain=1.0 if PAIN_RX.search(txt) else 0.0, claim=1.0 if CLAIM_RX.search(txt) else 0.0,
                         question=1.0 if "?" in raw or ws[0] in ("почему", "как", "зачем", "что", "сколько", "кто") else 0.0,
                         you=1.0 if re.search(r"ты|тебе|тебя|вы|вам|твой|ваш", txt) else 0.0)
                # слова-«мясо» (длинные) и конец на границе предложения/запятой — лучше
                body = sum(1 for x in ws if len(x) >= 5) / n
                tidy_end = 1.3 if (j == s["last"] or re.search(r"[,;:.!?…]$", words[j]["w"])) else 0.0
                out.append(dict(first=i, last=j, f=f, base=body * 0.8 + tidy_end - 0.015 * (i - s["first"]) - 0.01 * i))
    return out


def _pick(ver, cands, used):
    wts = ANGLES[ver]

    def score(c):
        sc = c["base"] + sum(wts[k] * v for k, v in c["f"].items())
        for (uf, ul) in used:                       # у каждой версии свой угол: не повторять чужие окна
            if not (c["last"] < uf or c["first"] > ul):
                sc -= 2.5
        return sc
    return max(cands, key=score)


def rule_hook(words, sents, vidx, used=None):
    """Хук ≤6 слов из самого сильного утверждения/цифры/боли в первых ~15 с; угол зависит от версии.
    Версии выбирают по порядку V1..V5, пересекающиеся окна штрафуются — получается разный хук."""
    cands = _hook_candidates(words, sents)
    if not cands:
        s = sents[0]
        return s["first"], min(s["last"], s["first"] + 5)
    vers = list(STYLES)
    used = []
    for k in range(vidx + 1):
        best = _pick(vers[k], cands, used)
        used.append((best["first"], best["last"]))
    return best["first"], best["last"]


def clean_hook_text(words, first, last):
    t = " ".join(w["w"] for w in words[first:last + 1])
    t = re.sub(r"\s+-", "-", t)                     # «По -другому» -> «По-другому»
    return re.sub(r"[,;:.]+$", "", t).strip()


def get_choices(version, choices):
    """choices: dict из plans.json (все версии) или None."""
    if not choices:
        raise RuntimeError("plans.json отсутствует")
    if "_fallback" in choices:
        raise RuntimeError(str(choices["_fallback"])[:200])
    if version not in choices:
        raise RuntimeError(f"в plans.json нет {version}")
    return choices[version]


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
def build_plan(version, tr, choices=None, force_rules=False, beats=None, caption=None):
    style = STYLES[version]
    words, sents, dur = tr["words"], tr["sentences"], tr["duration"]
    vidx = list(STYLES).index(version)
    source, reason = "claude", None
    try:
        if force_rules:
            raise RuntimeError("forced rules (validation)")
        ch = get_choices(version, choices)
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
    cap_hook = None
    cap_matches = []
    if caption:
        try:
            import caption as capmod
            cap_matches = capmod.apply_triggers(caption, words)
            for m in cap_matches:                                # триггеры: акцент на слова + графика на начале слова
                if m["level"] in ("ok", "weak"):
                    emph = sorted(set(emph) | set(range(m["first"], m["last"] + 1)))
                    kw = None
                    for rx, g in KEYWORD_GRAPHICS:
                        if re.search(rx, norm(words[m["first"]]["w"])):
                            kw = g
                            break
                    gcand = list(gcand) + [{"word": m["first"], "kind": (kw or {}).get("kind", "icon"),
                                            "icon": (kw or {}).get("icon", "star"), "text": (kw or {}).get("text", ""),
                                            "num": None}]
            vi = list(STYLES).index(version)
            if vi < len(caption.get("hooks", [])) and caption["hooks"][vi]:
                cap_hook = caption["hooks"][vi]
                mm = capmod.match_phrase(cap_hook, words[: max(8, int(len(words) * 0.3))])   # где в речи это сказано
                if mm and mm[2] >= capmod.OK_SCORE:
                    hf, hl = mm[0], min(mm[1], mm[0] + 5)
                else:
                    hf, hl = 0, min(5, len(words) - 1)
        except Exception as e:  # noqa — кривая подпись не должна ломать прогон
            print(f"CAPTION IGNORED: {type(e).__name__}: {str(e)[:120]}", flush=True)
            cap_hook = None
    plan = {
        "version": version, "source": source, "duration": dur,
        "hook": {"text": cap_hook or clean_hook_text(words, hf, hl), "first": hf, "last": hl, "t0": 0.0, "t1": 2.0},
        "emphasis": emph, "chunks": chunks,
    }
    if reason:
        plan["fallback_reason"] = reason
    plan["cams"] = make_cams(words, sents, style, dur, beats)
    plan["snaps"] = make_snaps(words, emph, style, plan["cams"])
    plan["graphics"] = place_graphics(gcand, words, style, dur)
    plan["sfx"] = make_sfx(plan, style, words)
    for e in (ch.get("sfx", []) if source == "claude" else []):    # доп. точки от Claude
        try:
            k = int(e["word"])
            if 0 <= k < len(words) and e["kind"] in ("hit", "whoosh", "pop", "riser", "click"):
                plan["sfx"].append({"t": round(words[k]["start"], 3), "kind": e["kind"], "gain": round(0.7 * style["sfx_level"], 2)})
        except (KeyError, ValueError, TypeError):
            pass
    plan["sfx"].sort(key=lambda x: x["t"])
    if caption:
        try:
            import caption as capmod
            plan["caption_match"] = capmod.summary(caption, cap_matches, list(STYLES).index(version))
        except Exception:  # noqa
            pass
    try:
        validate(plan, PLAN_SCHEMA)
        semantic_check(plan, len(words))
    except (ValidationError, ValueError) as e:
        if source == "claude":   # ответ Claude испортил план — откат на правила, не молча
            print(f"PLAN FALLBACK: validation: {str(e)[:200]}", flush=True)
            return build_plan(version, tr, choices, force_rules=True, beats=beats, caption=caption)
        raise
    return plan


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("version", choices=list(STYLES))
    ap.add_argument("--transcript", default="out/transcript.json")
    ap.add_argument("--plans", default=None, help="plans.json от plan_claude.py")
    ap.add_argument("--out", default="out")
    ap.add_argument("--rules", action="store_true")
    a = ap.parse_args()
    ch = load_json(a.plans) if a.plans and Path(a.plans).exists() else None
    plan = build_plan(a.version, load_json(a.transcript), ch, a.rules)
    Path(a.out).mkdir(parents=True, exist_ok=True)
    save_json(Path(a.out) / f"plan_{a.version}.json", plan)
    log(f"[plan {a.version}] source={plan['source']} hook=«{plan['hook']['text']}» "
        f"cams={len(plan['cams'])} snaps={len(plan['snaps'])} graphics={len(plan['graphics'])} sfx={len(plan['sfx'])}")


if __name__ == "__main__":
    main()

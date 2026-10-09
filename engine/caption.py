#!/usr/bin/env python3
"""Telegram caption -> hooks / triggers / background (Part F). Never raises: bad input = empty result.

ХУКИ: 1) ... 2) ... 3) ... 4) ... 5) ...
ТРИГГЕРЫ: слово, фраза, ...
ФОН: запрос (необязательно)
"""
import difflib
import json
import os
import re
import sys
from pathlib import Path

MAX_CAPTION = 1500
MAX_HOOK_WORDS = 7
MAX_TRIGGERS = 12
OK_SCORE, WEAK_SCORE = 0.78, 0.60


def norm(w):
    return re.sub(r"[^\w]", "", (w or "").lower().replace("ё", "е"), flags=re.U)


def parse(raw):
    out = {"hooks": [], "triggers": [], "bg": None, "warnings": []}
    try:
        if not raw or not isinstance(raw, str):
            return out
        if len(raw) > MAX_CAPTION:
            out["warnings"].append(f"caption truncated from {len(raw)} chars")
            raw = raw[:MAX_CAPTION]
        t = re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f]", " ", raw)
        marks = [(m.start(), m.end(), m.group(1).upper().replace("Ё", "Е"))
                 for m in re.finditer(r"(ХУКИ|ТРИГГЕРЫ|ФОН)\s*:", t, re.I)]
        sec = {}
        for k, (s, e, name) in enumerate(marks):
            sec.setdefault(name, t[e:(marks[k + 1][0] if k + 1 < len(marks) else len(t))].strip())
        if "ХУКИ" in sec:
            parts = re.split(r"(?:^|\s)\d\s*[)\.]\s*", " " + sec["ХУКИ"])
            hooks = [re.sub(r"\s+", " ", p).strip(" \n\t;,") for p in parts if p.strip()]
            for i, h in enumerate(hooks[:5]):
                w = h.split()
                if len(w) > MAX_HOOK_WORDS:
                    out["warnings"].append(f"hook {i + 1} cut from {len(w)} to {MAX_HOOK_WORDS} words")
                    h = " ".join(w[:MAX_HOOK_WORDS])
                out["hooks"].append(h[:70])
            if len(hooks) > 5:
                out["warnings"].append("more than 5 hooks, extra ignored")
        if "ТРИГГЕРЫ" in sec:
            trg = [re.sub(r"\s+", " ", x).strip(" .") for x in re.split(r"[,;\n]", sec["ТРИГГЕРЫ"])]
            out["triggers"] = [x[:40] for x in trg if x][:MAX_TRIGGERS]
        if "ФОН" in sec:
            bg = re.sub(r"[^\w\s\-]", " ", sec["ФОН"].split("\n")[0], flags=re.U)
            bg = re.sub(r"\s+", " ", bg).strip()[:60]
            out["bg"] = bg or None
    except Exception as e:  # noqa
        out = {"hooks": [], "triggers": [], "bg": None, "warnings": [f"caption parse error: {type(e).__name__}"]}
    return out


def _sim(a, b):
    if not a or not b:
        return 0.0
    if a == b:
        return 1.0
    cp = len(os.path.commonprefix([a, b]))
    pre = 1.0 if (cp >= 3 and cp >= min(len(a), len(b)) - 2) else 0.0      # same stem, different Russian ending
    return max(difflib.SequenceMatcher(None, a, b).ratio(), 0.88 * pre)


def match_phrase(phrase, words):
    """-> (first, last, score) of best window in words, or None."""
    pw = [norm(x) for x in phrase.split() if norm(x)]
    if not pw or not words:
        return None
    nw = [norm(w["w"]) for w in words]
    best = None
    for L in {max(1, len(pw) - 1), len(pw), len(pw) + 1}:
        for i in range(0, len(nw) - L + 1):
            win = nw[i:i + L]
            sc = sum(max(_sim(p, x) for x in win) for p in pw) / len(pw)
            sc -= 0.03 * abs(L - len(pw))
            if best is None or sc > best[2]:
                best = (i, i + L - 1, sc)
    return best


def apply_triggers(cap, words):
    """-> list of {phrase, first, last, score, level}"""
    res = []
    for ph in cap.get("triggers", []):
        m = match_phrase(ph, words)
        if not m:
            res.append({"phrase": ph, "level": "none"})
            continue
        f, l, sc = m
        res.append({"phrase": ph, "first": f, "last": min(l, f + 3), "score": round(sc, 2),
                    "level": "ok" if sc >= OK_SCORE else "weak" if sc >= WEAK_SCORE else "none"})
    return res


def summary(cap, matches, version_idx):
    """Line for QA_report: CAPTION MATCH: ok/weak, reason."""
    reasons, level = [], "ok"
    if not (cap.get("hooks") or cap.get("triggers") or cap.get("bg")):
        return "CAPTION MATCH: none, no usable caption" + (f" ({'; '.join(cap.get('warnings', []))})" if cap.get("warnings") else "")
    if cap.get("hooks"):
        if version_idx < len(cap["hooks"]):
            reasons.append(f"hook {version_idx + 1} used")
        else:
            level = "weak"
            reasons.append(f"no hook {version_idx + 1} in caption, planner/rule hook used")
    if cap.get("triggers"):
        ok = [m for m in matches if m["level"] == "ok"]
        weak = [m for m in matches if m["level"] == "weak"]
        none_ = [m for m in matches if m["level"] == "none"]
        reasons.append(f"triggers ok {len(ok)}/{len(matches)}")
        if weak or none_:
            level = "weak"
            reasons.append("weak/no match: " + ", ".join(m["phrase"] for m in weak + none_))
    reasons += cap.get("warnings", [])
    return f"CAPTION MATCH: {level}, " + "; ".join(reasons)


def main():
    out = Path(sys.argv[1] if len(sys.argv) > 1 else "caption.json")
    cap = parse(os.environ.get("CAPTION", ""))
    out.write_text(json.dumps(cap, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"[caption] hooks={len(cap['hooks'])} triggers={len(cap['triggers'])} bg={'yes' if cap['bg'] else 'no'} warnings={len(cap['warnings'])}")


if __name__ == "__main__":
    try:
        main()
    except Exception as e:  # noqa
        print(f"[caption] ignored: {type(e).__name__}")

"""Self-check for hook texts (used by the planner loop and by QA).

A hook is rejected when it is a sentence fragment, ends on a preposition / conjunction / particle,
leans on a missing referent (он/она/его ... with no noun), is too long, or claims things that are
not in the author's speech (numbers or content words that never occur in the transcript).
"""
import re

MAX_WORDS = 6

END_BAD = set("""в во на с со к ко у о об обо от ото до по за из изо для про при без над под через между перед после
и а но или либо да что чтобы как если когда пока потому хотя ведь же ли бы не ни то лишь только даже уж
чем чего кого кому это этот эта эти тот там тут так тоже уже еще ещё очень просто вот ну типа
который которая которое которые которым которой которого
он она оно они его её ее их им ему ним ней
мой моя мои твой твоя твои свой своя свои наш ваш""".split())

START_BAD = set("и а но да чтобы потому который которая которое которые хотя ведь пока либо".split())
COND_START = set("если когда пока".split())            # условное придаточное — нужен хвост: запятая, вопрос или >= 4 слов
REFERENT = set("он она оно они его её ее их им ему ним ней них".split())    # «он»/«его» без существительного = нет контекста

TOK = re.compile(r"[0-9]+(?:[.,][0-9]+)?|[^\W\d_]+(?:-[^\W\d_]+)*", re.U)


def tokens(text):
    return [t.lower().replace("ё", "е") for t in TOK.findall(text or "")]


def _stem(w):
    return w[:5]


def problems(text, transcript_words=None, other_hooks=()):
    """-> list of short reasons (empty = hook is fine)."""
    out = []
    t = (text or "").strip()
    tk = tokens(t)
    if not tk:
        return ["empty"]
    if len(tk) > MAX_WORDS:
        out.append(f"{len(tk)} words (>6)")
    if len(tk) < 2 and not t.endswith("?"):
        out.append("single word")
    if re.search(r"[,:;\-–—…]$", t) or t.endswith(".."):
        out.append("ends on punctuation (cut off)")
    last = tk[-1]
    if last in END_BAD:
        out.append(f"ends on «{last}» (preposition/conjunction/particle/pronoun)")
    if tk[0] in START_BAD:
        out.append(f"starts on «{tk[0]}» (fragment)")
    if tk[0] == "что" and not t.endswith("?") and len(tk) < 4:
        out.append("starts on «что» without a question")
    if tk[0] in COND_START and not (t.endswith("?") or "," in t or len(tk) >= 4):
        out.append(f"«{tk[0]}…» clause is not finished")
    if any(w in REFERENT for w in tk):
        out.append("refers to «он/она/его…» with no noun (no context)")
    if transcript_words:
        tw = [w.lower().replace("ё", "е") for w in transcript_words]
        tset = set(tw)
        stems = {_stem(w) for w in tw if len(w) >= 4}
        for n in (x for x in tk if x[0].isdigit()):
            if n not in tset:
                out.append(f"number «{n}» is not in the speech")
        content = [w for w in tk if len(w) >= 5 and not w[0].isdigit()]
        if content:
            hit = sum(1 for w in content if _stem(w) in stems)
            if hit / len(content) < 0.6:
                out.append(f"claims words not in the speech ({hit}/{len(content)} content words found)")
    for o in other_hooks:
        a, b = set(tk), set(tokens(o))
        if a and b and len(a & b) / len(a | b) > 0.6:
            out.append(f"almost the same as another version's hook «{o}»")
            break
    return out


if __name__ == "__main__":
    for h in ["Его задача с первых секунд", "По-другому никак не бывает", "что он делает?", "Как продать за 10 секунд?",
              "Продажи решает первая секунда", "Только то, о чем смог договориться", "Запомни, ты в жизни получишь"]:
        print(h, "->", problems(h) or "ok")

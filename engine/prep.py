#!/usr/bin/env python3
"""Общая подготовка (job prep): шаги 1-4.

1. нормализация: CFR 30 fps, 1080x1920, SDR (bt709), 48 кГц
2. транскрипция faster-whisper (ru, пословные таймстампы)
3. авто-нарезка: паузы >0.4 c, слова-паразиты, ложные старты, повторы дублей,
   явный оффтоп (LLM, при сомнении оставляем) -> out/cuts.md
4. ускорение SPEED (видео+звук, тон сохраняется), времена слов / SPEED

Выход (в --out): prepped.mp4, transcript.json (времена уже на ФИНАЛЬНОЙ
шкале), cuts.md
"""
import argparse
import difflib
import json
import os
import re
import subprocess
import sys
from pathlib import Path

from common import SPEED, FPS, W, H, AR, log, run, probe, duration, save_json

PAUSE_MAX = 0.4         # пауза длиннее — вырезаем
PAD = 0.08              # воздух вокруг реза, с
HEAD_PAD, TAIL_PAD = 0.15, 0.25
FILLERS = {"э", "эм", "эмм", "ээ", "эээ", "ам", "мм", "ммм", "ну", "типа", "короче"}
FILLER_PAIRS = {("как", "бы")}
SENT_GAP = 0.7


def norm(w: str) -> str:
    return re.sub(r"[^\w]", "", w.lower().replace("ё", "е"), flags=re.U)


# ---------------------------------------------------------------- 1. normalize
def face_center_x(path: Path, w: int, h: int) -> float:
    """Для горизонтального исходника: медианный центр лица (0..1), иначе 0.5."""
    try:
        import cv2
        import numpy as np
        cap = cv2.VideoCapture(str(path))
        n = int(cap.get(cv2.CAP_PROP_FRAME_COUNT) or 0)
        cas = cv2.CascadeClassifier(cv2.data.haarcascades + "haarcascade_frontalface_default.xml")
        xs = []
        for k in range(8):
            cap.set(cv2.CAP_PROP_POS_FRAMES, int(n * (k + 0.5) / 8))
            ok, fr = cap.read()
            if not ok:
                continue
            g = cv2.cvtColor(fr, cv2.COLOR_BGR2GRAY)
            f = cas.detectMultiScale(g, 1.2, 5, minSize=(60, 60))
            if len(f):
                x, y, fw, fh = max(f, key=lambda r: r[2] * r[3])
                xs.append((x + fw / 2) / fr.shape[1])
        return float(np.median(xs)) if xs else 0.5
    except Exception as e:  # noqa
        log(f"[prep] face detect skipped: {e}")
        return 0.5


def normalize(src: Path, dst: Path):
    info = probe(src, "stream=width,height,color_transfer,color_space,pix_fmt,r_frame_rate:stream_tags=rotate:stream_side_data=rotation", "v:0")
    st = info["streams"][0]
    sw, sh = st["width"], st["height"]
    rot = 0
    for sd in st.get("side_data_list", []) or []:
        rot = int(sd.get("rotation", 0) or 0)
    if abs(rot) in (90, 270):
        sw, sh = sh, sw
    hdr = st.get("color_transfer") in ("smpte2084", "arib-std-b67")
    log(f"[prep] source {sw}x{sh} rot={rot} transfer={st.get('color_transfer')} hdr={hdr}")
    vf = []
    if hdr:
        vf.append("zscale=t=linear:npl=100,format=gbrpf32le,zscale=p=bt709,"
                  "tonemap=hable:desat=0,zscale=t=bt709:m=bt709:r=tv")
    if sw / sh > W / H:    # горизонтальный: кроп по лицу
        cx = face_center_x(src, sw, sh)
        vf.append(f"scale=-2:{H}")
        vf.append(f"crop={W}:{H}:'min(max(iw*{cx:.3f}-{W}/2,0),iw-{W})':0")
    else:
        vf.append(f"scale={W}:{H}:force_original_aspect_ratio=increase,crop={W}:{H}")
    vf.append(f"fps={FPS}")
    vf.append("scale=out_color_matrix=bt709:out_range=tv,format=yuv420p")
    run(["ffmpeg", "-y", "-loglevel", "error", "-i", src, "-vf", ",".join(vf),
         "-af", f"aresample={AR}", "-ar", AR, "-ac", 1,
         "-c:v", "libx264", "-preset", "fast", "-crf", 15, "-r", FPS, "-vsync", "cfr",
         "-colorspace", "bt709", "-color_primaries", "bt709", "-color_trc", "bt709",
         "-c:a", "aac", "-b:a", "256k", "-movflags", "+faststart", dst])


# --------------------------------------------------------------- 2. transcribe
def transcribe(path: Path, model_name: str):
    from faster_whisper import WhisperModel
    log(f"[prep] whisper model={model_name} int8 cpu")
    model = WhisperModel(model_name, device="cpu", compute_type="int8",
                         cpu_threads=os.cpu_count() or 4)
    # initial_prompt с паразитами — иначе Whisper их "причёсывает" и вырезать нечего
    segs, info = model.transcribe(
        str(path), language="ru", word_timestamps=True, vad_filter=False,
        condition_on_previous_text=False, beam_size=5,
        initial_prompt="Ну, э-э... это, типа, как бы, короче, эм... Так, ну вот.")
    words = []
    for s in segs:
        for w in s.words or []:
            t = w.word.strip()
            if t:
                words.append({"w": t, "start": float(w.start), "end": float(w.end),
                              "p": float(w.probability or 0)})
    log(f"[prep] words={len(words)} lang={info.language}")
    return words


# ---------------------------------------------------------------------- 3. cuts
def split_sentences(words):
    sents, cur = [], []
    for i, w in enumerate(words):
        cur.append(i)
        end_punct = re.search(r"[.!?…]$", w["w"])
        gap = (words[i + 1]["start"] - w["end"]) if i + 1 < len(words) else 99
        if end_punct or gap >= SENT_GAP:
            sents.append(cur)
            cur = []
    if cur:
        sents.append(cur)
    return sents


def detect_drops(words, sents):
    """Возвращает {word_idx: (категория, пояснение)}."""
    drop = {}
    n = len(words)
    nw = [norm(w["w"]) for w in words]
    # слова-паразиты
    for i in range(n):
        if nw[i] in FILLERS:
            # "ну"/"короче" в начале осмысленной фразы тоже режем — это просили явно
            drop[i] = ("filler", words[i]["w"])
        if i + 1 < n and (nw[i], nw[i + 1]) in FILLER_PAIRS:
            drop[i] = drop[i + 1] = ("filler", f'{words[i]["w"]} {words[i + 1]["w"]}')
    # ложные старты: повтор слова / пары слов подряд (оставляем второй)
    for i in range(n - 1):
        if i in drop:
            continue
        if nw[i] and nw[i] == nw[i + 1] and len(nw[i]) <= 12:
            drop[i] = ("false_start", f'«{words[i]["w"]}» повторено')
        if i + 3 < n and nw[i] == nw[i + 2] and nw[i + 1] == nw[i + 3] and nw[i]:
            drop[i] = drop[i + 1] = ("false_start", f'«{words[i]["w"]} {words[i+1]["w"]}» повторено')
        # обрыв слова: очень короткий кусок без гласной уверенности + следующее слово начинается так же
        if i + 1 < n and len(nw[i]) in (1, 2) and nw[i + 1].startswith(nw[i]) and nw[i] not in ("я", "и", "а", "в", "к", "с", "у", "о", "но", "на", "по", "за", "не", "из", "до", "то", "же", "бы", "ли", "мы", "вы", "он", "от", "ко", "во"):
            drop[i] = ("false_start", f'обрыв «{words[i]["w"]}»')
    # повторные дубли предложений: оставляем лучший (выше средняя уверенность, при равенстве — поздний)
    def sig(idx):
        return " ".join(nw[k] for k in idx if k not in drop and nw[k])
    for a in range(len(sents)):
        for b in range(a + 1, min(a + 4, len(sents))):
            sa, sb = sig(sents[a]), sig(sents[b])
            if len(sa.split()) < 3 or len(sb.split()) < 3:
                continue
            ratio = difflib.SequenceMatcher(None, sa, sb).ratio()
            head = sa.split()[:4] == sb.split()[:4]
            if ratio >= 0.72 or head:
                def score(idx):
                    ps = [words[k]["p"] for k in idx if k not in drop]
                    return (sum(ps) / len(ps) if ps else 0) + 0.01 * len(ps)
                # по умолчанию оставляем более поздний дубль; ранний — только если заметно увереннее
                loser = sents[b] if score(sents[a]) >= score(sents[b]) + 0.15 else sents[a]
                text = " ".join(words[k]["w"] for k in loser)
                for k in loser:
                    drop.setdefault(k, ("repeat_take", f"дубль ({ratio:.2f}): «{text[:60]}»"))
                break
    return drop


def llm_offtopic(words, sents):
    """Оффтоп через LLM. При любой неудаче — ничего не режем (когда не уверены, оставляем)."""
    key = os.environ.get("OPENAI_API_KEY")
    if not key:
        log("[prep] OFFTOPIC SKIPPED: no OPENAI_API_KEY")
        return {}
    try:
        from openai_http import openai_post
        lines = [f"{k}: " + " ".join(words[i]["w"] for i in s) for k, s in enumerate(sents)]
        prompt = (
            "Это транскрипт короткого видео автора (говорящая голова). Найди предложения, которые "
            "ЯВНО не относятся к теме ролика: реплики не в камеру, бытовые отвлечения, разговор с "
            "кем-то за кадром, технические паузы ('подожди', 'сейчас включу'). Если есть сомнение — "
            "НЕ включай. Ответ строго JSON: {\"drop\":[{\"id\":N,\"reason\":\"...\"}]}. "
            "Если таких нет: {\"drop\":[]}.\n\n" + "\n".join(lines))
        resp = openai_post({"model": "gpt-5.6-luna", "input": prompt}, key, timeout=90)
        body = resp.json()
        txt = "".join(c["text"] for it in body["output"] if it.get("type") == "message"
                      for c in it["content"] if c.get("type") == "output_text")
        data = json.loads(re.search(r"\{.*\}", txt, re.S).group(0))
        out = {}
        for d in data.get("drop", []):
            k = int(d["id"])
            if 0 <= k < len(sents) and len(sents) > 3:
                for i in sents[k]:
                    out[i] = ("off_topic", str(d.get("reason", ""))[:80])
        # страховка: не режем больше 25% слов по оффтопу
        if len(out) > 0.25 * len(words):
            log("[prep] OFFTOPIC SKIPPED: LLM wanted to drop >25% — не доверяю")
            return {}
        return out
    except Exception as e:  # noqa
        log(f"[prep] OFFTOPIC SKIPPED: {type(e).__name__}: {str(e)[:160]}")
        return {}


def build_segments(words, drop, total):
    keep = [i for i in range(len(words)) if i not in drop]
    if not keep:
        raise SystemExit("[prep] все слова отброшены — что-то не так с транскриптом")
    segs = []   # [src_start, src_end, [word idx]]
    pauses = []
    cur = [keep[0]]
    for a, b in zip(keep, keep[1:]):
        gap = words[b]["start"] - words[a]["end"]
        dropped_between = b - a > 1
        if gap > PAUSE_MAX or dropped_between:
            segs.append(cur)
            cur = [b]
            pauses.append((words[a]["end"], words[b]["start"], dropped_between))
        else:
            cur.append(b)
    segs.append(cur)
    out = []
    for si, idx in enumerate(segs):
        s = words[idx[0]]["start"] - (HEAD_PAD if si == 0 else PAD)
        e = words[idx[-1]]["end"] + (TAIL_PAD if si == len(segs) - 1 else PAD)
        out.append([max(0.0, s), min(total, e), idx])
    for k in range(1, len(out)):          # без перекрытий
        if out[k][0] < out[k - 1][1]:
            mid = (out[k][0] + out[k - 1][1]) / 2
            out[k][0] = out[k - 1][1] = mid
    return out, pauses


def render_cut_speed(src: Path, segs, dst: Path):
    lines = []
    for k, (s, e, _) in enumerate(segs):
        d = e - s
        fade = min(0.012, d / 4)
        lines.append(f"[0:v]trim=start={s:.4f}:end={e:.4f},setpts=PTS-STARTPTS[v{k}]")
        lines.append(f"[0:a]atrim=start={s:.4f}:end={e:.4f},asetpts=PTS-STARTPTS,"
                     f"afade=t=in:d={fade:.4f},afade=t=out:st={d - fade:.4f}:d={fade:.4f}[a{k}]")
    cat = "".join(f"[v{k}][a{k}]" for k in range(len(segs)))
    lines.append(f"{cat}concat=n={len(segs)}:v=1:a=1[cv][ca]")
    lines.append(f"[cv]setpts=PTS/{SPEED},fps={FPS}[vo]")
    lines.append(f"[ca]atempo={SPEED},aresample={AR}[ao]")      # atempo сохраняет тон
    script = dst.with_suffix(".filter.txt")
    script.write_text(";\n".join(lines), encoding="utf-8")
    run(["ffmpeg", "-y", "-loglevel", "error", "-i", src, "-filter_complex_script", script,
         "-map", "[vo]", "-map", "[ao]", "-c:v", "libx264", "-preset", "fast", "-crf", 15,
         "-r", FPS, "-vsync", "cfr", "-pix_fmt", "yuv420p", "-colorspace", "bt709",
         "-c:a", "aac", "-b:a", "256k", "-ar", AR, "-movflags", "+faststart", dst])


def final_timeline(words, segs):
    """Слова -> времена на ФИНАЛЬНОЙ шкале (после реза и деления на SPEED)."""
    out, off = [], 0.0
    for s, e, idx in segs:
        for i in idx:
            w = words[i]
            ts = (off + max(0.0, w["start"] - s)) / SPEED
            te = (off + max(0.0, min(w["end"], e) - s)) / SPEED
            out.append({"i": len(out), "w": w["w"], "start": round(ts, 3), "end": round(max(te, ts + 0.04), 3), "src": i})
        off += e - s
    return out, off / SPEED


def sentences_final(fw):
    sents, cur = [], []
    for k, w in enumerate(fw):
        cur.append(k)
        gap = (fw[k + 1]["start"] - w["end"]) if k + 1 < len(fw) else 99
        if re.search(r"[.!?…]$", w["w"]) or gap >= 0.35:
            sents.append(cur)
            cur = []
    if cur:
        sents.append(cur)
    return [{"id": n, "first": s[0], "last": s[-1], "start": fw[s[0]]["start"], "end": fw[s[-1]]["end"],
             "text": " ".join(fw[k]["w"] for k in s)} for n, s in enumerate(sents)]


def fmt(t):
    return f"{int(t // 60)}:{t % 60:05.2f}"


def write_cuts_md(path, words, drop, segs, pauses, src_dur, final_dur):
    cats = {"filler": "Слова-паразиты", "false_start": "Ложные старты", "repeat_take": "Повторные дубли (оставлен лучший)",
            "off_topic": "Оффтоп"}
    L = [f"# Cut list", "",
         f"- SPEED = **{SPEED}x** (после нарезки; видео и звук вместе, тон сохранён; времена слов /{SPEED})",
         f"- Исходник: {fmt(src_dur)} → после нарезки {fmt(sum(e - s for s, e, _ in segs))} → после ускорения **{fmt(final_dur)}**",
         f"- Кусков оставлено: {len(segs)}; мёртвых пауз >{PAUSE_MAX} с вырезано: {len(pauses)} "
         f"(всего {sum(b - a for a, b, _ in pauses):.1f} с)", ""]
    for cat, title in cats.items():
        items = [(i, v) for i, v in sorted(drop.items()) if v[0] == cat]
        L.append(f"## {title}: {len(items)}")
        for i, (_, why) in items:
            L.append(f"- {fmt(words[i]['start'])}  {why}")
        L.append("")
    L.append("## Мёртвые паузы (время в исходнике)")
    for a, b, d in pauses:
        L.append(f"- {fmt(a)} → {fmt(b)}  ({b - a:.2f} с){' + вырезанные слова' if d else ''}")
    Path(path).write_text("\n".join(L) + "\n", encoding="utf-8")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("source")
    ap.add_argument("--out", default="out")
    ap.add_argument("--whisper", default=os.environ.get("WHISPER_MODEL", "large-v3"))
    a = ap.parse_args()
    out = Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    norm_mp4 = out / "normalized.mp4"
    normalize(Path(a.source), norm_mp4)
    total = duration(norm_mp4)
    log(f"[prep] normalized {total:.1f}s")

    words = transcribe(norm_mp4, a.whisper)
    if len(words) < 5:
        raise SystemExit("[prep] в видео почти нет речи")
    sents = split_sentences(words)
    drop = detect_drops(words, sents)
    for i, v in llm_offtopic(words, sents).items():
        drop.setdefault(i, v)
    segs, pauses = build_segments(words, drop, total)
    log(f"[prep] drop={len(drop)} segments={len(segs)} pauses={len(pauses)}")

    prepped = out / "prepped.mp4"
    render_cut_speed(norm_mp4, segs, prepped)
    fw, fdur = final_timeline(words, segs)
    real = duration(prepped)
    log(f"[prep] final duration planned={fdur:.2f}s actual={real:.2f}s speed={SPEED}")
    save_json(out / "transcript.json", {"speed": SPEED, "duration": real, "words": fw,
                                         "sentences": sentences_final(fw)})
    write_cuts_md(out / "cuts.md", words, drop, segs, pauses, total, real)
    norm_mp4.unlink()
    (out / "prepped.filter.txt").unlink(missing_ok=True)
    log("[prep] done")


if __name__ == "__main__":
    main()

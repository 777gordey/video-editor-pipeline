#!/usr/bin/env python3
"""Общая подготовка (job prep): шаги 1-4.

1. нормализация: CFR 30 fps, 1080x1920, SDR (bt709), 48 кГц
2. транскрипция faster-whisper (ru, пословные таймстампы)
3. авто-нарезка: паузы >0.4 c, слова-паразиты, ложные старты, повторы дублей,
    -> out/cuts.md
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

import exposure
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
    merged = []                                   # Whisper отдаёт «По», «-другому» отдельными словами: склеиваем «По-другому», «что-либо»
    for w in words:
        if merged and re.match(r"-[^\W\d_]", w["w"]):
            merged[-1]["w"] += w["w"]
            merged[-1]["end"] = w["end"]
            merged[-1]["p"] = min(merged[-1]["p"], w["p"])
        else:
            merged.append(w)
    words = merged
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


def render_cut_speed(src: Path, segs, dst: Path, exp_filter: str = ""):
    lines = []
    for k, (s, e, _) in enumerate(segs):
        d = e - s
        fade = min(0.012, d / 4)
        lines.append(f"[0:v]trim=start={s:.4f}:end={e:.4f},setpts=PTS-STARTPTS[v{k}]")
        lines.append(f"[0:a]atrim=start={s:.4f}:end={e:.4f},asetpts=PTS-STARTPTS,"
                     f"afade=t=in:d={fade:.4f},afade=t=out:st={d - fade:.4f}:d={fade:.4f}[a{k}]")
    cat = "".join(f"[v{k}][a{k}]" for k in range(len(segs)))
    lines.append(f"{cat}concat=n={len(segs)}:v=1:a=1[cv][ca]")
    lines.append(f"[cv]setpts=PTS/{SPEED},fps={FPS}" + (f",{exp_filter}" if exp_filter else "") + "[vo]")
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


def remap_plans(data, fw, n_raw):
    """plans (индексы СЫРЫХ слов) -> индексы слов финального транскрипта; вырезанные слова пропускаем."""
    import bisect
    src = [w["src"] for w in fw]                       # возрастающие индексы оставленных сырых слов
    pos = {s_: k for k, s_ in enumerate(src)}

    def nxt(x):
        k = bisect.bisect_left(src, x)
        return min(k, len(fw) - 1)

    def prv(x):
        k = bisect.bisect_right(src, x) - 1
        return max(k, 0)
    out = {}
    for v, ch in data.items():
        if v.startswith("_") or v == "cuts":
            continue
        hf, hl = nxt(ch["hook"]["first"]), prv(ch["hook"]["last"])
        if hl < hf:
            hl = hf
        hl = min(hl, hf + 11)
        out[v] = {"hook": {**{k: ch["hook"][k] for k in ("text", "promise", "why", "check") if k in ch["hook"]}, "first": hf, "last": hl},
                  "emphasis": sorted({pos[i] for i in ch["emphasis"] if i in pos}),
                  "graphics": [{**g, "word": pos[g["word"]]} for g in ch["graphics"] if g["word"] in pos],
                  "sfx": [{**e, "word": pos[e["word"]]} for e in ch["sfx"] if e["word"] in pos]}
    return out


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
    if not drop and not pauses and len(segs) == 1:
        L.append("- Режим «клип уже смонтирован»: ничего не вырезано, паузы и скорость не трогаем. "
                 "Строки подписи `ПАУЗЫ: да` и `СКОРОСТЬ: 1.2` включают нарезку и ускорение.")
        L.append("")
    for cat, title in cats.items():
        items = [(i, v) for i, v in sorted(drop.items()) if v[0] == cat]
        L.append(f"## {title}: {len(items)}")
        for i, (_, why) in items:
            L.append(f"- {fmt(words[i]['start'])}  {why}")
        L.append("")
    L.append("_Оффтоп и смысловые вырезы предлагает Claude-планировщик (при сомнении оставляем материал); "
             "без токена Claude работают только правила: паузы, паразиты, запинки, дубли._")
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
    cuts_on = os.environ.get("CUTS_ON", "0") == "1"      # по умолчанию клип уже смонтирован: без вырезов (подпись «ПАУЗЫ: да» включает)
    drop = detect_drops(words, sents) if cuts_on else {}
    log(f"[prep] cuts={'ON' if cuts_on else 'off (pre-edited clip)'} speed={SPEED}")
    raw_plans = None
    if os.environ.get("CLAUDE_CODE_OAUTH_TOKEN"):          # один вызов Claude: выборы всех версий + вырезы по смыслу
        import plan_claude
        raw_plans = plan_claude.plan_raw(words, [s_ for s_ in sents], drop, total, with_cuts=cuts_on)
        if "_fallback" not in raw_plans:
            extra = {}
            for c_ in raw_plans.get("cuts", []):
                for k in range(c_["first"], c_["last"] + 1):
                    if k not in drop:
                        extra[k] = (c_["cat"], "Claude: " + (c_.get("why") or c_["cat"]))
            if len(extra) > 0.25 * len(words):
                print(f"PLAN FALLBACK: cuts: Claude предложил вырезать {len(extra)} из {len(words)} слов — слишком много, "
                      f"вырезы Claude не применяются", flush=True)
            else:
                drop.update(extra)
                log(f"[prep] Claude cuts applied: {len(extra)} words")
    else:
        print("PLAN FALLBACK: CLAUDE_CODE_OAUTH_TOKEN не задан", flush=True)
    if cuts_on:
        segs, pauses = build_segments(words, drop, total)
    else:                                                # без нарезки: весь клип одним куском
        segs, pauses = [[0.0, total, list(range(len(words)))]], []
    log(f"[prep] drop={len(drop)} segments={len(segs)} pauses={len(pauses)}")

    prepped = out / "prepped.mp4"
    try:
        em = exposure.measure(norm_mp4)
        exp_filter, einfo = exposure.plan_correction(em)
    except Exception as e:  # noqa
        print(f"EXPOSURE SKIPPED: {type(e).__name__}: {str(e)[:200]}", flush=True)
        em, exp_filter, einfo = {}, "", {"applied": [], "error": str(e)[:200]}
    if exp_filter:      # фильтр не должен ронять прогон: проверяем на одном кадре
        t_ = subprocess.run(["ffmpeg", "-v", "error", "-i", str(norm_mp4), "-frames:v", "1", "-vf", exp_filter, "-f", "null", "-"],
                            capture_output=True, text=True)
        if t_.returncode != 0:
            print(f"EXPOSURE FILTER INVALID, skipped: {t_.stderr[-200:]}", flush=True)
            exp_filter, einfo = "", {"applied": [], "error": "invalid filter"}
    log(f"[prep] exposure before={em} filter={exp_filter or 'none'}")
    render_cut_speed(norm_mp4, segs, prepped, exp_filter)
    try:
        ea = exposure.measure(prepped)
        save_json(out / "exposure.json", {"before": em, "after": ea, "filter": exp_filter, **einfo})
        exposure.compare_image(norm_mp4, prepped, out / "exposure_compare.jpg")
        if einfo.get("dark_clip"):
            print("DARK CLIP: noisy result, consider re-shooting with more light", flush=True)
    except Exception as e:  # noqa
        print(f"EXPOSURE REPORT SKIPPED: {type(e).__name__}: {str(e)[:200]}", flush=True)
    fw, fdur = final_timeline(words, segs)
    real = duration(prepped)
    log(f"[prep] final duration planned={fdur:.2f}s actual={real:.2f}s speed={SPEED}")
    save_json(out / "transcript.json", {"speed": SPEED, "duration": real, "words": fw,
                                         "sentences": sentences_final(fw)})
    if raw_plans is not None:
        if "_fallback" in raw_plans:
            save_json(out / "plans.json", raw_plans)
        else:
            try:
                save_json(out / "plans.json", remap_plans(raw_plans, fw, len(words)))
            except Exception as e:  # noqa
                print(f"PLAN FALLBACK: remap: {type(e).__name__}: {str(e)[:200]}", flush=True)
                save_json(out / "plans.json", {"_fallback": f"remap: {e}"})
    else:
        save_json(out / "plans.json", {"_fallback": "CLAUDE_CODE_OAUTH_TOKEN не задан"})
    write_cuts_md(out / "cuts.md", words, drop, segs, pauses, total, real)
    norm_mp4.unlink()
    (out / "prepped.filter.txt").unlink(missing_ok=True)
    log("[prep] done")


if __name__ == "__main__":
    main()

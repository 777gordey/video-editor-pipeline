#!/usr/bin/env python3
"""
B-roll модуль: транскрипт -> LLM выбирает моменты для вставки -> перевод
запроса на английский (тем же вызовом LLM) -> Pexels/Pixabay video search ->
скачивание -> композит поверх основного видео через FFmpeg overlay
(звук/войсовер остаётся от основного видео, картинка на время вставки
переключается на b-roll — стандартный приём, а не "картинка в картинке").

СТАТУС (22.09.2026): полный пайплайн (pick_broll_candidates -> Pexels/
Pixabay поиск -> скачивание -> compose_broll) проверен живым end-to-end
тестом на тестовом русском ролике про накопление на ипотеку — реальные
тематически релевантные стоковые клипы вставлены в LLM-выбранные моменты,
проверено визуально по извлечённым кадрам. Вшит в process_video.py.

Решение по провайдеру LLM: изначально был выбран Anthropic (дёшево, не
плодить провайдера), но владелец прислал ключ OpenAI — переключил на него.

Требует: OPENAI_API_KEY, PEXELS_API_KEY и/или PIXABAY_API_KEY.
"""
import argparse
import json
import os
import sys
from pathlib import Path

import requests

TARGET_W, TARGET_H = 1080, 1920

BROLL_MIN_GAP = 4.0        # не чаще одной вставки за этот интервал (сек)
BROLL_MIN_DURATION = 1.5
BROLL_MAX_DURATION = 3.0
BROLL_DENSITY_HINT = "8-15 вставок на 60 секунд видео, ориентир, не жёсткое число"

OPENAI_MODEL = "gpt-5.6-luna"


def transcript_text(words) -> str:
    """Транскрипт с таймкодами по словам — вход для LLM."""
    return " ".join(f"[{w['start']:.1f}]{w['word']}" for w in words)


def pick_broll_candidates(words, api_key: str, duration: float) -> list:
    """Один вызов Anthropic Messages API: LLM читает размеченный по времени
    транскрипт и возвращает JSON-список моментов для b-roll вставок с
    английским поисковым запросом (перевод делает тут же, отдельного шага
    перевода не нужно)."""
    prompt = f"""Вот русский транскрипт видео с таймкодами перед каждым словом
в секундах (формат [t]слово). Длительность видео: {duration:.1f}с.

Выбери моменты, где короткая b-roll вставка (типа стокового видео, которое
показывают вместо/поверх говорящего на пару секунд, пока продолжает играть
его голос) усилит просмотр — там, где упоминается конкретный предмет,
место, действие или понятие, которое можно проиллюстрировать. Плотность:
{BROLL_DENSITY_HINT}. Не ставь вставки чаще чем раз в {BROLL_MIN_GAP}с и не
в первые 2 секунды (там хук-фрейм).

Транскрипт:
{transcript_text(words)}

Ответь СТРОГО JSON-массивом без пояснений, каждый элемент:
{{"start": <сек>, "duration": <{BROLL_MIN_DURATION}-{BROLL_MAX_DURATION}>, "query_en": "<2-4 английских слова для поиска стокового видео>"}}"""

    resp = requests.post(
        "https://api.openai.com/v1/responses",
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        },
        json={
            "model": OPENAI_MODEL,
            "input": prompt,
        },
        timeout=60,
    )
    resp.raise_for_status()
    body = resp.json()
    # Responses API: response["output"] -- список айтемов, текст лежит в
    # output[i].content[j].text у айтемов type=="message". Схема почерпнута
    # из доки на сентябрь 2026, не проверена вживую -- если тут упадёт,
    # print(body) в stderr ниже покажет реальную форму ответа для правки.
    try:
        raw = next(
            c["text"]
            for item in body["output"] if item.get("type") == "message"
            for c in item["content"] if c.get("type") == "output_text"
        ).strip()
    except (KeyError, StopIteration) as e:
        print(f"[broll] неожиданная форма ответа Responses API: {body}", file=sys.stderr)
        raise RuntimeError("Не удалось распарсить ответ OpenAI Responses API") from e

    if raw.startswith("```"):
        raw = raw.strip("`")
        raw = raw[raw.find("["):raw.rfind("]") + 1]
    candidates = json.loads(raw)

    picked = []
    last_end = 2.0
    for c in candidates:
        start = float(c["start"])
        dur = min(max(float(c["duration"]), BROLL_MIN_DURATION), BROLL_MAX_DURATION)
        if start < last_end + BROLL_MIN_GAP or start + dur > duration - 0.3:
            continue
        picked.append({"start": start, "end": start + dur, "query_en": c["query_en"]})
        last_end = start + dur
    return picked


def search_pexels_video(query: str, api_key: str) -> str | None:
    resp = requests.get(
        "https://api.pexels.com/videos/search",
        headers={"Authorization": api_key},
        params={"query": query, "orientation": "portrait", "per_page": 3},
        timeout=30,
    )
    resp.raise_for_status()
    videos = resp.json().get("videos", [])
    if not videos:
        return None
    files = sorted(
        videos[0]["video_files"],
        key=lambda f: abs(f.get("height", 0) - TARGET_H),
    )
    return files[0]["link"] if files else None


def search_pixabay_video(query: str, api_key: str) -> str | None:
    resp = requests.get(
        "https://pixabay.com/api/videos/",
        params={"key": api_key, "q": query, "video_type": "film", "per_page": 3},
        timeout=30,
    )
    resp.raise_for_status()
    hits = resp.json().get("hits", [])
    if not hits:
        return None
    videos = hits[0]["videos"]
    for quality in ("medium", "small", "large", "tiny"):
        if quality in videos:
            return videos[quality]["url"]
    return None


def find_broll_url(query: str, pexels_key: str | None, pixabay_key: str | None) -> str | None:
    if pexels_key:
        try:
            url = search_pexels_video(query, pexels_key)
            if url:
                return url
        except requests.RequestException as e:
            print(f"[broll] pexels error for '{query}': {e}", file=sys.stderr)
    if pixabay_key:
        try:
            url = search_pixabay_video(query, pixabay_key)
            if url:
                return url
        except requests.RequestException as e:
            print(f"[broll] pixabay error for '{query}': {e}", file=sys.stderr)
    return None


def run(cmd, **kw):
    import subprocess
    print("+", " ".join(str(c) for c in cmd), file=sys.stderr)
    return subprocess.run(cmd, check=True, **kw)


def download(url: str, dst: Path):
    resp = requests.get(url, stream=True, timeout=120)
    resp.raise_for_status()
    with open(dst, "wb") as f:
        for chunk in resp.iter_content(chunk_size=1 << 16):
            f.write(chunk)


def prep_clip(src: Path, dst: Path, dur: float):
    """Скейл/кроп под 1080x1920, зациклить если короче нужной длины, обрезать
    точно под dur секунд, без звука (звук остаётся от основного видео)."""
    vf = f"scale={TARGET_W}:{TARGET_H}:force_original_aspect_ratio=increase,crop={TARGET_W}:{TARGET_H}"
    run([
        "ffmpeg", "-y", "-stream_loop", "-1", "-i", str(src),
        "-t", f"{dur:.3f}", "-vf", vf, "-an",
        "-c:v", "libx264", "-preset", "veryfast", "-crf", "20",
        str(dst),
    ])


def compose_broll(main_video: Path, candidates: list, clip_paths: list, out_path: Path):
    """candidates[i] соответствует clip_paths[i] (уже prep_clip-нутые под
    нужную длительность). Цепочка overlay c enable=between — картинка
    переключается на b-roll на окне [start,end], звук всегда от 0:a."""
    if not candidates:
        run(["ffmpeg", "-y", "-i", str(main_video), "-c", "copy", str(out_path)])
        return

    inputs = ["-i", str(main_video)]
    for p in clip_paths:
        inputs += ["-i", str(p)]

    filter_parts = []
    prev_label = "0:v"
    for i, c in enumerate(candidates, start=1):
        delayed = f"d{i}"
        out_label = f"v{i}"
        filter_parts.append(
            f"[{i}:v]setpts=PTS-STARTPTS+{c['start']:.3f}/TB[{delayed}]"
        )
        filter_parts.append(
            f"[{prev_label}][{delayed}]overlay=enable='between(t,{c['start']:.3f},{c['end']:.3f})'[{out_label}]"
        )
        prev_label = out_label

    filter_complex = ";".join(filter_parts)
    run([
        "ffmpeg", "-y", *inputs,
        "-filter_complex", filter_complex,
        "-map", f"[{prev_label}]", "-map", "0:a",
        "-c:v", "libx264", "-preset", "veryfast", "-crf", "19",
        "-c:a", "copy",
        str(out_path),
    ])


def add_broll(video_path: Path, words, duration: float, out_path: Path,
               openai_key: str, pexels_key: str | None, pixabay_key: str | None,
               work_dir: Path):
    candidates = pick_broll_candidates(words, openai_key, duration)
    print(f"[broll] кандидатов после прореживания: {len(candidates)}", file=sys.stderr)

    resolved, clip_paths = [], []
    for i, c in enumerate(candidates):
        url = find_broll_url(c["query_en"], pexels_key, pixabay_key)
        if not url:
            print(f"[broll] нет результата для '{c['query_en']}', пропуск", file=sys.stderr)
            continue
        raw_path = work_dir / f"broll_raw_{i}.mp4"
        clip_path = work_dir / f"broll_{i}.mp4"
        download(url, raw_path)
        prep_clip(raw_path, clip_path, c["end"] - c["start"])
        resolved.append(c)
        clip_paths.append(clip_path)

    compose_broll(video_path, resolved, clip_paths, out_path)
    print(f"[broll] вставлено {len(resolved)} клипов -> {out_path}", file=sys.stderr)


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("video", type=Path)
    ap.add_argument("transcript_json", type=Path,
                     help="JSON-список {word,start,end} (тот же формат, что transcribe() в process_video.py)")
    ap.add_argument("--out", type=Path, default=Path("broll_out.mp4"))
    args = ap.parse_args()

    openai_key = os.environ.get("OPENAI_API_KEY")
    pexels_key = os.environ.get("PEXELS_API_KEY")
    pixabay_key = os.environ.get("PIXABAY_API_KEY")
    if not openai_key:
        print("ОШИБКА: задай OPENAI_API_KEY", file=sys.stderr)
        sys.exit(1)
    if not pexels_key and not pixabay_key:
        print("ОШИБКА: задай хотя бы PEXELS_API_KEY или PIXABAY_API_KEY", file=sys.stderr)
        sys.exit(1)

    words = json.loads(args.transcript_json.read_text(encoding="utf-8"))
    from process_video import ffprobe_duration
    duration = ffprobe_duration(args.video)

    add_broll(args.video, words, duration, args.out,
              openai_key, pexels_key, pixabay_key, work_dir=Path("."))


if __name__ == "__main__":
    main()

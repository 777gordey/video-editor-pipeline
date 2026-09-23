#!/usr/bin/env python3
"""
Standalone-клиент для Shotstack Edit/Ingest API — субтитры вместо локальной
ASS-генерации (см. build_caption_chunks() в process_video.py).

СТАТУС (22.09.2026): базовый caption-тип проверен живым end-to-end тестом
(sandbox/stage-рендер) на русском тексте — кириллица рендерится корректно.
СТАТУС (24.09.2026): переведено на rich-text таймлайн (см. ниже) для
эффекта "неожиданности" — акцентные чанки крупнее обычных. Схема rich-text
клипов (position/offset/align/font.size 12-200) собрана по документации
Shotstack (RichCaptionAsset и rich-text asset), НЕ подтверждена живым
рендером — при первом реальном запуске проверить визуальное положение
субтитров (см. Y_OFFSET) и при необходимости поправить.

Почему rich-text, а не RichCaptionAsset: у RichCaptionAsset 'active' стиль
привязан к текущему проговариваемому слову (караоке-подсветка), а не к
выбранным LLM смысловым моментам — под задачу "крупный размер на важных
фразах" не подходит. Вместо этого таймлайн собирается вручную: один
rich-text клип на каждый субтитр-чанк (та же группировка, что раньше шла в
SRT), с font.size побольше на чанках, которые pick_emphasis_chunks() отметил
как акцентные.

Флоу:
  1. ingest_upload_url() -> получить presigned PUT-ссылку (только для видео)
  2. put_file()            -> залить видео по этой ссылке
  3. poll_ingest_ready()   -> дождаться status=="ready", забрать source-url
  4. pick_emphasis_chunks() -> LLM отмечает индексы акцентных чанков
  5. submit_richtext_render() -> запустить рендер (rich-text клипы поверх video)
  6. poll_render()         -> дождаться готовности, забрать итоговый mp4-url
  7. download()

Требует переменные окружения: SHOTSTACK_API_KEY (рендер), OPENAI_API_KEY
(разметка акцентов, передаётся аргументом в pick_emphasis_chunks).
"""
import argparse
import json
import os
import sys
import time
from pathlib import Path

import requests

API_BASE = "https://api.shotstack.io"
INGEST_STAGE = f"{API_BASE}/ingest/stage"
EDIT_STAGE = f"{API_BASE}/edit/stage"   # stage = бесплатный sandbox с водяным знаком
                                          # для прод-рендеров без вотермарка —
                                          # EDIT_BASE = f"{API_BASE}/edit/v1"
                                          # (платный tier, проверить при апгрейде)

FONT_URL_DEFAULT = (
    "https://raw.githubusercontent.com/777gordey/video-editor-pipeline/"
    "master/assets/fonts/Montserrat-Black.ttf"
)

BASE_FONT_SIZE = 34
EMPHASIS_FONT_SIZE = 50    # ~1.47x — заметно крупнее, но не ломает разметку
EMPHASIS_DENSITY_HINT = "15-25% чанков, не больше одного акцента подряд"

OPENAI_MODEL = "gpt-5.6-luna"   # тот же, что в broll.py — не плодить провайдера

# Позиция субтитров: анкер "bottom" + смещение вверх от низа кадра (доля
# высоты, 0..1). Ориентир — старая caption-разметка (margin.top=0.62 от
# 1920 то есть строки начинались на y~1190..1920) переведён в offset; на
# первом живом рендере свериться визуально и поправить.
Y_OFFSET = 0.24
CLIP_WIDTH = 940
CLIP_HEIGHT_BASE = 110
CLIP_HEIGHT_EMPHASIS = 150


def _headers(api_key: str, content_type: str | None = None):
    h = {"x-api-key": api_key, "Accept": "application/json"}
    if content_type:
        h["Content-Type"] = content_type
    return h


def ingest_upload_url(api_key: str, filename: str | None = None) -> dict:
    """Запрашивает presigned URL для загрузки файла."""
    payload = {"filename": filename} if filename else None
    resp = requests.post(
        f"{INGEST_STAGE}/upload",
        headers=_headers(api_key, "application/json"),
        json=payload,
        timeout=30,
    )
    resp.raise_for_status()
    data = resp.json()
    print(f"[ingest] upload url response: {data}", file=sys.stderr)
    return data["data"]["attributes"]


def put_file(signed_url: str, path: Path):
    with open(path, "rb") as f:
        resp = requests.put(signed_url, data=f, timeout=300)
    resp.raise_for_status()


def poll_ingest_ready(api_key: str, source_id: str, timeout_s: int = 120) -> str:
    """Ждёт, пока загруженный файл станет status=='ready', возвращает
    его публичный source-url для использования как src в timeline."""
    deadline = time.time() + timeout_s
    while time.time() < deadline:
        resp = requests.get(
            f"{INGEST_STAGE}/sources/{source_id}",
            headers=_headers(api_key),
            timeout=30,
        )
        resp.raise_for_status()
        attrs = resp.json()["data"]["attributes"]
        status = attrs.get("status")
        print(f"[ingest] {source_id} status={status}", file=sys.stderr)
        if status == "ready":
            return attrs["source"]
        if status == "failed":
            raise RuntimeError(f"Ingest failed for {source_id}: {attrs}")
        time.sleep(3)
    raise TimeoutError(f"Ingest source {source_id} not ready after {timeout_s}s")


def ingest_file(api_key: str, path: Path, filename: str | None = None) -> str:
    """Полный цикл: upload url -> PUT -> poll ready -> вернуть src-url."""
    attrs = ingest_upload_url(api_key, filename=filename or path.name)
    put_file(attrs["url"], path)
    source_id = attrs["id"]
    return poll_ingest_ready(api_key, source_id)


def pick_emphasis_chunks(chunks: list, api_key: str) -> set:
    """Один вызов OpenAI Responses API: LLM читает пронумерованный список
    чанков субтитров (та же группировка, что уходит в рендер) и отмечает,
    какие стоит показать крупнее — там, где происходит что-то неожиданное,
    эмоционально важное, кульминационное, ключевая цифра/факт/вывод.
    Деградирует до пустого множества (без акцентов) при любой ошибке —
    это визуальный "приятный бонус", не должен ронять весь рендер."""
    if not chunks:
        return set()

    numbered = "\n".join(f"{i}: {c['text']}" for i, c in enumerate(chunks))
    prompt = f"""Вот пронумерованный список подряд идущих фраз субтитров русского
видео (текст чанками, как они будут показываться один за другим).

Отметь индексы чанков, которые стоит визуально ВЫДЕЛИТЬ увеличенным размером
текста — там, где происходит что-то неожиданное, эмоционально важное,
кульминационное, называется ключевая цифра/факт/вывод. Не отмечай рядовые
связки и обычные фразы. Ориентир по плотности: {EMPHASIS_DENSITY_HINT}.

Чанки:
{numbered}

Ответь СТРОГО JSON-массивом индексов без пояснений, например [2, 5, 9]."""

    try:
        resp = requests.post(
            "https://api.openai.com/v1/responses",
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
            },
            json={"model": OPENAI_MODEL, "input": prompt},
            timeout=60,
        )
        resp.raise_for_status()
        body = resp.json()
        raw = next(
            c["text"]
            for item in body["output"] if item.get("type") == "message"
            for c in item["content"] if c.get("type") == "output_text"
        ).strip()
        if raw.startswith("```"):
            raw = raw.strip("`")
            raw = raw[raw.find("["):raw.rfind("]") + 1]
        indices = json.loads(raw)
        return {int(i) for i in indices if 0 <= int(i) < len(chunks)}
    except (requests.RequestException, KeyError, StopIteration, ValueError, json.JSONDecodeError) as e:
        print(f"[captions] не удалось разметить акценты, продолжаю без них: {e}", file=sys.stderr)
        return set()


def _richtext_clip(chunk: dict, emphasized: bool) -> dict:
    size = EMPHASIS_FONT_SIZE if emphasized else BASE_FONT_SIZE
    height = CLIP_HEIGHT_EMPHASIS if emphasized else CLIP_HEIGHT_BASE
    return {
        "asset": {
            "type": "rich-text",
            "text": chunk["text"].upper(),
            "font": {
                "family": "Montserrat Black",
                "size": size,
                "color": "#FFFFFF",
            },
            "stroke": {"width": 3, "color": "#000000"},
            "align": {"horizontal": "center", "vertical": "middle"},
        },
        "start": chunk["start"],
        "length": max(chunk["end"] - chunk["start"], 0.1),
        "width": CLIP_WIDTH,
        "height": height,
        "position": "bottom",
        "offset": {"x": 0, "y": Y_OFFSET},
    }


def submit_richtext_render(api_key: str, video_src: str, chunks: list,
                            emphasized_idx: set, font_src: str = FONT_URL_DEFAULT) -> str:
    """Строит таймлайн из отдельных rich-text клипов (один на чанк) вместо
    базового 'caption' типа — это даёт контроль над font.size по чанкам,
    которого у обычного caption/SRT нет."""
    clips = [
        _richtext_clip(chunk, i in emphasized_idx)
        for i, chunk in enumerate(chunks)
    ]
    body = {
        "timeline": {
            "fonts": [{"src": font_src}],
            "tracks": [
                {"clips": clips},
                {
                    "clips": [
                        {
                            "asset": {"type": "video", "src": video_src},
                            "start": 0,
                            "length": "auto",
                        }
                    ]
                },
            ],
        },
        "output": {"format": "mp4", "resolution": "1080", "aspectRatio": "9:16"},
    }
    resp = requests.post(
        f"{EDIT_STAGE}/render",
        headers=_headers(api_key, "application/json"),
        json=body,
        timeout=30,
    )
    resp.raise_for_status()
    render_id = resp.json()["response"]["id"]
    print(f"[render] submitted id={render_id}", file=sys.stderr)
    return render_id


def poll_render(api_key: str, render_id: str, timeout_s: int = 300) -> str:
    deadline = time.time() + timeout_s
    while time.time() < deadline:
        resp = requests.get(
            f"{EDIT_STAGE}/render/{render_id}",
            headers=_headers(api_key),
            timeout=30,
        )
        resp.raise_for_status()
        r = resp.json()["response"]
        status = r.get("status")
        print(f"[render] {render_id} status={status}", file=sys.stderr)
        if status == "done":
            return r["url"]
        if status == "failed":
            raise RuntimeError(f"Render failed: {r}")
        time.sleep(5)
    raise TimeoutError(f"Render {render_id} not done after {timeout_s}s")


def download(url: str, dst: Path):
    resp = requests.get(url, stream=True, timeout=120)
    resp.raise_for_status()
    with open(dst, "wb") as f:
        for chunk in resp.iter_content(chunk_size=1 << 16):
            f.write(chunk)


def burn_captions_via_shotstack(video_path: Path, chunks: list, emphasized_idx: set,
                                  out_path: Path, api_key: str):
    video_src = ingest_file(api_key, video_path)
    render_id = submit_richtext_render(api_key, video_src, chunks, emphasized_idx)
    result_url = poll_render(api_key, render_id)
    download(result_url, out_path)
    print(f"Готово: {out_path}", file=sys.stderr)


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("video", type=Path)
    ap.add_argument("transcript_json", type=Path,
                     help="JSON-список {word,start,end} (формат transcribe() из process_video.py)")
    ap.add_argument("--out", type=Path, default=Path("shotstack_out.mp4"))
    args = ap.parse_args()

    api_key = os.environ.get("SHOTSTACK_API_KEY")
    openai_key = os.environ.get("OPENAI_API_KEY")
    if not api_key:
        print("ОШИБКА: задай SHOTSTACK_API_KEY", file=sys.stderr)
        sys.exit(1)
    if not openai_key:
        print("ОШИБКА: задай OPENAI_API_KEY", file=sys.stderr)
        sys.exit(1)

    words = json.loads(args.transcript_json.read_text(encoding="utf-8"))
    from process_video import build_caption_chunks
    chunks = build_caption_chunks(words)
    emphasized_idx = pick_emphasis_chunks(chunks, openai_key)
    print(f"акцентных чанков: {len(emphasized_idx)}/{len(chunks)}", file=sys.stderr)

    burn_captions_via_shotstack(args.video, chunks, emphasized_idx, args.out, api_key)


if __name__ == "__main__":
    main()

#!/usr/bin/env python3
"""
Standalone-клиент для Shotstack Edit/Ingest API — субтитры вместо локальной
ASS-генерации (см. build_srt() в process_video.py).

СТАТУС (22.09.2026): проверен живым end-to-end тестом (sandbox/stage-рендер)
на русском тексте — кириллица рендерится корректно, не квадратиками и не
латиницей (включая буквы вроде "й"). Response-схемы Ingest API подтверждены
живым ответом. Вшит в process_video.py вместо локальной ASS-генерации body-
субтитров (хук-фраза по-прежнему рендерится в FFmpeg/libass, см. build_hook_ass).

Известное ограничение: используется базовый тип 'caption' (без покадровой
подсветки keyword, как раньше делал ASS) — апгрейд до RichCaptionAsset
рассматривается отдельно, если базовое качество окажется недостаточным.
Стейдж-рендер (EDIT_STAGE) идёт с водяным знаком Shotstack — для прод-вывода
без вотермарка нужно переключить на EDIT_BASE=f"{API_BASE}/edit/v1" (платный
tier) после того, как это будет подтверждено владельцем.

Флоу:
  1. ingest_upload_url()   -> получить presigned PUT-ссылку
  2. put_file()            -> залить файл (видео/srt/шрифт) по этой ссылке
  3. poll_ingest_ready()   -> дождаться status=="ready", забрать source-url
  4. submit_caption_render() -> запустить рендер (caption поверх video)
  5. poll_render()         -> дождаться готовности, забрать итоговый mp4-url
  6. download()

Требует переменную окружения SHOTSTACK_API_KEY.
"""
import argparse
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


def _headers(api_key: str, content_type: str | None = None):
    h = {"x-api-key": api_key, "Accept": "application/json"}
    if content_type:
        h["Content-Type"] = content_type
    return h


def ingest_upload_url(api_key: str, filename: str | None = None) -> dict:
    """Запрашивает presigned URL для загрузки файла. filename нужен для
    текстовых файлов (srt), чтобы Shotstack понял тип по расширению."""
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


def submit_caption_render(api_key: str, video_src: str, srt_src: str,
                           font_src: str = FONT_URL_DEFAULT) -> str:
    """Запускает рендер: видео + caption-трек поверх него. Базовый тип
    'caption' (не RichCaptionAsset) — без покадровой подсветки keyword,
    только стилизованный текст. Апгрейд до RichCaptionAsset — отдельная
    задача после того, как подтвердим, что базовое качество вообще ок."""
    body = {
        "timeline": {
            "fonts": [{"src": font_src}],
            "tracks": [
                {
                    "clips": [
                        {
                            "asset": {
                                "type": "caption",
                                "src": srt_src,
                                "font": {
                                    "family": "Montserrat Black",
                                    "size": 34,
                                    "color": "#FFFFFF",
                                    "stroke": "#000000",
                                    "strokeWidth": 3,
                                    "lineHeight": 0.9,
                                },
                                "background": {"color": "#00000000", "padding": 0},
                                "margin": {"top": 0.62, "left": 0.08, "right": 0.08},
                            },
                            "start": 0,
                            "length": "end",
                        }
                    ]
                },
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


def burn_captions_via_shotstack(video_path: Path, srt_path: Path, out_path: Path,
                                  api_key: str):
    video_src = ingest_file(api_key, video_path)
    srt_src = ingest_file(api_key, srt_path, filename="subtitles.srt")
    render_id = submit_caption_render(api_key, video_src, srt_src)
    result_url = poll_render(api_key, render_id)
    download(result_url, out_path)
    print(f"Готово: {out_path}", file=sys.stderr)


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("video", type=Path)
    ap.add_argument("srt", type=Path)
    ap.add_argument("--out", type=Path, default=Path("shotstack_out.mp4"))
    args = ap.parse_args()

    api_key = os.environ.get("SHOTSTACK_API_KEY")
    if not api_key:
        print("ОШИБКА: задай SHOTSTACK_API_KEY", file=sys.stderr)
        sys.exit(1)

    burn_captions_via_shotstack(args.video, args.srt, args.out, api_key)


if __name__ == "__main__":
    main()

"""Фоновые «плейты» только из свободных источников: brand/plates/ и Pexels API
(ключ PEXELS_API_KEY из GitHub Secrets, не печатается). Никаких AI-сцен.
Нет ни файла, ни ключа — возвращаем None и печатаем "PLATE FALLBACK: ..."; compose рисует CSS-градиент."""
import os
import re
from pathlib import Path

import requests

from common import FPS, W, H, REPO_DIR, log, run

PLATE_EXT = (".mp4", ".mov", ".webm", ".mkv")


def brand_plate(style):
    d = REPO_DIR / "brand" / "plates"
    if not d.exists():
        return None
    key = style["id"].lower()
    files = sorted(p for p in d.glob("*") if p.suffix.lower() in PLATE_EXT)
    named = [p for p in files if key in p.stem.lower()]
    return (named or [])[0] if named else None


def pexels_plate(style, cache: Path):
    key = os.environ.get("PEXELS_API_KEY")
    if not key:
        raise RuntimeError("PEXELS_API_KEY не задан")
    r = requests.get("https://api.pexels.com/videos/search",
                     params={"query": style["plate_query"], "orientation": "portrait", "size": "medium", "per_page": 15},
                     headers={"Authorization": key}, timeout=30)
    r.raise_for_status()
    best = None
    for v in r.json().get("videos", []):
        if v.get("duration", 0) < 6:
            continue
        for f in v.get("video_files", []):
            if f.get("file_type") != "video/mp4" or not f.get("width") or f["width"] > f["height"]:
                continue
            score = abs(f["width"] - 1080) + (0 if f["width"] >= 720 else 5000)
            if best is None or score < best[0]:
                best = (score, f["link"], v["id"])
    if not best:
        raise RuntimeError("Pexels: подходящих вертикальных видео не найдено")
    cache.mkdir(parents=True, exist_ok=True)
    dst = cache / f"pexels_{best[2]}.mp4"
    if not dst.exists():
        with requests.get(best[1], stream=True, timeout=120) as resp:
            resp.raise_for_status()
            with open(dst, "wb") as fh:
                for chunk in resp.iter_content(1 << 20):
                    fh.write(chunk)
    log(f"[plate] Pexels video id={best[2]} ({dst.stat().st_size // 1024} KB)")
    return dst


def prepare_plate(style, dur, out: Path, cache: Path):
    """-> путь к готовому плейту (1080x1920, CFR, без звука) или None."""
    src = None
    try:
        src = brand_plate(style)
        if src:
            log(f"[plate] brand/plates: {src.name}")
        elif style.get("plate_query"):
            src = pexels_plate(style, cache)
    except Exception as e:  # noqa
        print(f"PLATE FALLBACK: {type(e).__name__}: {str(e)[:160]}", flush=True)
        return None
    if not src:
        return None
    # зацикливаем «пинг-понгом» (вперёд-назад), чтобы не было видимого шва
    vf = (f"scale={W}:{H}:force_original_aspect_ratio=increase,crop={W}:{H},fps={FPS},"
          f"split[a][b];[b]reverse[r];[a][r]concat=n=2:v=1:a=0,format=yuv420p")
    one = out.with_suffix(".pp.mp4")
    run(["ffmpeg", "-y", "-loglevel", "error", "-t", "12", "-i", src, "-an", "-filter_complex",
         "[0:v]" + vf + "[o]", "-map", "[o]", "-c:v", "libx264", "-preset", "fast", "-crf", 17, one])
    run(["ffmpeg", "-y", "-loglevel", "error", "-stream_loop", "-1", "-i", one, "-t", f"{dur:.3f}", "-an",
         "-vf", f"{style['plate_grade']}" if style.get("plate_grade") else "null",
         "-c:v", "libx264", "-preset", "fast", "-crf", 17, "-r", FPS, out])
    one.unlink(missing_ok=True)
    return out

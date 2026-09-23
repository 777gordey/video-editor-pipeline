#!/usr/bin/env python3
"""
Автоматическая обложка для готового ролика: несколько кадров-кандидатов из
финального видео -> отсев смазанных (OpenCV Laplacian variance) -> OpenAI
vision выбирает самый выразительный кадр и придумывает короткую подпись ->
подпись накладывается через Pillow (жирный шрифт, обводка+тень, текст не
перекрывает лицо) -> сохраняется в 1080x1920 (TikTok/Reels) и 1280x720
(YouTube).

СТАТУС (24.09.2026): собрано по документации OpenAI Responses API
(multimodal input_image) по аналогии с текстовым вызовом в broll.py —
НЕ подтверждено живым запросом (нет доступа к OPENAI_API_KEY локально, ключ
есть только как секрет GitHub Actions). При первом реальном прогоне сверить
форму ответа; если парсинг упадёт, print(body) в stderr покажет реальную
форму для правки (тот же приём, что уже применён в broll.py). Деградирует
до алгоритмического выбора (самый резкий кадр + хук-фраза как подпись) при
любой ошибке вызова LLM — обложка не должна ронять весь рендер.

Требует: OPENAI_API_KEY. Кадры берутся из уже смонтированного финального
видео (после субтитров), поэтому запускается последним шагом в main().
"""
import base64
import io
import json
import re
import subprocess
import sys
from pathlib import Path

import cv2
import requests
from PIL import Image, ImageDraw, ImageFilter, ImageFont

FONT_PATH = Path(__file__).resolve().parent.parent / "assets" / "fonts" / "Montserrat-Black.ttf"

OPENAI_MODEL = "gpt-5.6-luna"   # тот же, что в broll.py/shotstack_captions.py

CANDIDATE_COUNT = 10       # сколько таймкодов извлечь до отсева по резкости
LLM_CANDIDATE_COUNT = 6    # сколько лучших по резкости уйдёт в LLM (контроль стоимости)
SCENE_THRESHOLD = 0.3
MIN_GAP_S = 0.6            # не брать кандидатов ближе друг к другу, чем это

VERTICAL_SIZE = (1080, 1920)
HORIZONTAL_SIZE = (1280, 720)

TEXT_COLOR = (255, 255, 255, 255)
STROKE_COLOR = (0, 0, 0, 255)
SHADOW_COLOR = (0, 0, 0, 150)


def run(cmd, **kw):
    print("+", " ".join(str(c) for c in cmd), file=sys.stderr)
    return subprocess.run(cmd, check=True, **kw)


def _scene_change_times(video_path: Path) -> list:
    proc = subprocess.run(
        ["ffmpeg", "-i", str(video_path), "-vf", f"select='gt(scene,{SCENE_THRESHOLD})',showinfo",
         "-f", "null", "-"],
        capture_output=True, text=True,
    )
    return [float(m.group(1)) for m in re.finditer(r"pts_time:([0-9.]+)", proc.stderr)]


def _candidate_timestamps(video_path: Path, duration: float) -> list:
    """Смена сцен (обычно самые "содержательные" моменты — в т.ч. b-roll
    вставки) + равномерная подстраховка, если сцен нашлось мало. Середина
    ролика НЕ является приоритетной — часто это смазанный/переходный кадр."""
    times = _scene_change_times(video_path)
    fallback_n = 6
    fallback = [
        duration * (0.08 + i * (0.84 / (fallback_n - 1)))
        for i in range(fallback_n)
    ]
    times = sorted(times + fallback)

    picked = []
    for t in times:
        if 0.2 < t < duration - 0.2 and (not picked or t - picked[-1] >= MIN_GAP_S):
            picked.append(t)
        if len(picked) >= CANDIDATE_COUNT:
            break
    return picked


def extract_candidate_frames(video_path: Path, work_dir: Path, duration: float) -> list:
    timestamps = _candidate_timestamps(video_path, duration)
    paths = []
    for i, t in enumerate(timestamps):
        out = work_dir / f"thumb_candidate_{i}.jpg"
        run([
            "ffmpeg", "-y", "-ss", f"{t:.3f}", "-i", str(video_path),
            "-frames:v", "1", "-update", "1", "-q:v", "2", str(out),
        ])
        paths.append(out)
    return paths


def laplacian_variance(image_path: Path) -> float:
    img = cv2.imread(str(image_path), cv2.IMREAD_GRAYSCALE)
    if img is None:
        return 0.0
    return cv2.Laplacian(img, cv2.CV_64F).var()


def filter_sharp_frames(candidates: list, top_k: int = LLM_CANDIDATE_COUNT) -> list:
    scored = sorted(candidates, key=laplacian_variance, reverse=True)
    return scored[:top_k]


def _encode_for_llm(image_path: Path, max_width: int = 480) -> str:
    img = Image.open(image_path).convert("RGB")
    if img.width > max_width:
        ratio = max_width / img.width
        img = img.resize((max_width, round(img.height * ratio)))
    buf = io.BytesIO()
    img.save(buf, format="JPEG", quality=80)
    b64 = base64.b64encode(buf.getvalue()).decode("ascii")
    return f"data:image/jpeg;base64,{b64}"


def pick_best_frame_and_caption(candidate_paths: list, hook_text: str,
                                  transcript_excerpt: str, api_key: str) -> tuple:
    """Один мультимодальный вызов OpenAI Responses API: LLM смотрит на все
    кандидаты разом, выбирает самый цепляющий кадр и придумывает короткую
    (3-5 слов) подпись на русском. При любой ошибке — деградация до самого
    резкого кадра (candidate_paths уже отсортированы по убыванию резкости
    в filter_sharp_frames) и хук-фразы как подписи."""
    fallback = (candidate_paths[0], (hook_text or "СМОТРИ ДО КОНЦА").upper())
    try:
        content = [{
            "type": "input_text",
            "text": (
                "Вот несколько кадров-кандидатов для обложки видео (пронумерованы "
                "с 0). Выбери самый резкий и выразительный — где хорошо видно лицо "
                "(если оно есть), нет смазанности и это не переходный кадр между "
                "сценами.\n\n"
                f"Хук-фраза видео: \"{hook_text}\"\n"
                f"Начало транскрипта: \"{transcript_excerpt}\"\n\n"
                "Придумай короткую (3-5 слов) цепляющую подпись на русском для "
                "обложки на основе хук-фразы/транскрипта — капслоком не нужно, "
                "просто текст.\n\n"
                'Ответь СТРОГО JSON без пояснений: {"best_index": <int>, "caption": "<текст>"}'
            ),
        }]
        for p in candidate_paths:
            content.append({"type": "input_image", "image_url": _encode_for_llm(p)})

        resp = requests.post(
            "https://api.openai.com/v1/responses",
            headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
            json={"model": OPENAI_MODEL, "input": [{"role": "user", "content": content}]},
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
            raw = raw[raw.find("{"):raw.rfind("}") + 1]
        data = json.loads(raw)
        idx = int(data["best_index"])
        if not (0 <= idx < len(candidate_paths)):
            raise ValueError(f"best_index {idx} вне диапазона")
        caption = str(data["caption"]).strip()
        return candidate_paths[idx], caption
    except (requests.RequestException, KeyError, StopIteration, ValueError, json.JSONDecodeError) as e:
        print(f"[thumbnail] LLM-выбор не удался, беру самый резкий кадр: {e}", file=sys.stderr)
        return fallback


def _detect_face_box(image_path: Path):
    """Возвращает (x,y,w,h) самого крупного лица в пикселях кадра или None."""
    cascade = cv2.CascadeClassifier(
        cv2.data.haarcascades + "haarcascade_frontalface_default.xml"
    )
    img = cv2.imread(str(image_path), cv2.IMREAD_GRAYSCALE)
    if img is None:
        return None
    faces = cascade.detectMultiScale(img, 1.2, 5, minSize=(60, 60))
    if len(faces) == 0:
        return None
    return max(faces, key=lambda f: f[2] * f[3])


def _text_zone(face_box, img_height: int) -> str:
    """top/bottom — куда класть текст, чтобы не перекрывать лицо. Без лица —
    классическое место для подписи, низ кадра."""
    if face_box is None:
        return "bottom"
    _, fy, _, fh = face_box
    face_center_frac = (fy + fh / 2) / img_height
    return "top" if face_center_frac > 0.5 else "bottom"


def _wrap_text(draw: ImageDraw.ImageDraw, text: str, font: ImageFont.FreeTypeFont, max_width: int) -> list:
    words = text.split()
    lines, cur = [], ""
    for w in words:
        trial = f"{cur} {w}".strip()
        if draw.textbbox((0, 0), trial, font=font)[2] <= max_width or not cur:
            cur = trial
        else:
            lines.append(cur)
            cur = w
    if cur:
        lines.append(cur)
    return lines


def _draw_caption(img: Image.Image, caption: str, zone: str, font_size: int, max_width: int):
    """Рисует подпись с обводкой и мягкой тенью на прозрачном слое поверх img
    (RGBA), в верхней или нижней трети кадра."""
    font = ImageFont.truetype(str(FONT_PATH), font_size)
    overlay = Image.new("RGBA", img.size, (0, 0, 0, 0))
    draw = ImageDraw.Draw(overlay)
    lines = _wrap_text(draw, caption, font, max_width)

    line_height = font_size * 1.15
    block_height = line_height * len(lines)
    y0 = img.height * 0.12 if zone == "top" else img.height * 0.78 - block_height

    for i, line in enumerate(lines):
        bbox = draw.textbbox((0, 0), line, font=font)
        line_w = bbox[2] - bbox[0]
        x = (img.width - line_w) / 2
        y = y0 + i * line_height
        shadow_offset = max(3, font_size // 18)
        draw.text((x + shadow_offset, y + shadow_offset), line, font=font, fill=SHADOW_COLOR)
        draw.text((x, y), line, font=font, fill=TEXT_COLOR,
                   stroke_width=max(4, font_size // 12), stroke_fill=STROKE_COLOR)

    return Image.alpha_composite(img.convert("RGBA"), overlay).convert("RGB")


def render_cover(frame_path: Path, caption: str, out_vertical: Path, out_horizontal: Path):
    src = Image.open(frame_path).convert("RGB")
    face_box = _detect_face_box(frame_path)

    # 1080x1920 — исходный кадр уже в этом соотношении (после crop_grade_916)
    vertical = src.resize(VERTICAL_SIZE) if src.size != VERTICAL_SIZE else src.copy()
    zone_v = _text_zone(face_box, src.height)
    vertical = _draw_caption(vertical, caption, zone_v, font_size=96, max_width=int(VERTICAL_SIZE[0] * 0.86))
    vertical.save(out_vertical, quality=92)

    # 1280x720 — вертикальный кадр уже, дополняем размытым фоном по бокам
    hw, hh = HORIZONTAL_SIZE
    bg_ratio = max(hw / src.width, hh / src.height)
    bg = src.resize((round(src.width * bg_ratio), round(src.height * bg_ratio)))
    bg = bg.crop((
        (bg.width - hw) // 2, (bg.height - hh) // 2,
        (bg.width - hw) // 2 + hw, (bg.height - hh) // 2 + hh,
    )).filter(ImageFilter.GaussianBlur(24))

    fg_h = hh
    fg_w = round(src.width * (fg_h / src.height))
    fg = src.resize((fg_w, fg_h))
    canvas = bg.copy()
    canvas.paste(fg, ((hw - fg_w) // 2, 0))

    zone_h = _text_zone(face_box, src.height)
    horizontal = _draw_caption(canvas, caption, zone_h, font_size=64, max_width=int(hw * 0.9))
    horizontal.save(out_horizontal, quality=92)


def make_thumbnail(video_path: Path, hook_text: str, words: list, duration: float,
                     work_dir: Path, openai_key: str) -> tuple:
    candidates = extract_candidate_frames(video_path, work_dir, duration)
    sharp = filter_sharp_frames(candidates)

    transcript_excerpt = " ".join(w["word"] for w in words[:40])
    best_frame, caption = pick_best_frame_and_caption(sharp, hook_text, transcript_excerpt, openai_key)

    out_vertical = work_dir / "thumbnail_1080x1920.jpg"
    out_horizontal = work_dir / "thumbnail_1280x720.jpg"
    render_cover(best_frame, caption, out_vertical, out_horizontal)
    return out_vertical, out_horizontal


def main():
    import argparse
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("video", type=Path)
    ap.add_argument("--hook", default="")
    ap.add_argument("--out-dir", type=Path, default=Path("."))
    args = ap.parse_args()

    import os
    openai_key = os.environ.get("OPENAI_API_KEY")
    if not openai_key:
        print("ОШИБКА: задай OPENAI_API_KEY", file=sys.stderr)
        sys.exit(1)

    from process_video import ffprobe_duration
    duration = ffprobe_duration(args.video)
    out_v, out_h = make_thumbnail(args.video, args.hook, [], duration, args.out_dir, openai_key)
    print(f"Готово: {out_v}, {out_h}", file=sys.stderr)


if __name__ == "__main__":
    main()

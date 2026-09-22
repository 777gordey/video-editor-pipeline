#!/usr/bin/env python3
"""
Обработка уже чисто нарезанного видео: транскрипция -> кроп 9:16 по лицу ->
хук-фрейм в первые ~1.5-2с (FFmpeg/libass) -> punch-in зумы (FFmpeg) ->
b-roll вставки (Pexels/Pixabay, выбор моментов через LLM, scripts/broll.py) ->
субтитры на остальное видео через Shotstack API (scripts/shotstack_captions.py)
-> лёгкая цветокоррекция.

Субтитры и b-roll куплены как API, а не реализованы локально (libass ASS
для body-текста и ручной подбор b-roll были заменены по архитектурному
решению — самые визуально заметные и сложные в поддержке части). Хук-фраза,
punch-in зум и цветокоррекция остаются в FFmpeg.

Запускается на раннере GitHub Actions из edit-video.yml.
Вход: путь к исходному видео (без пауз/слов-паразитов — вырезаны заранее).
Выход: final.mp4 в текущей директории.
Требует переменные окружения: OPENAI_API_KEY, SHOTSTACK_API_KEY,
PEXELS_API_KEY и/или PIXABAY_API_KEY.
"""
import argparse
import json
import os
import subprocess
import sys
from pathlib import Path

TARGET_W, TARGET_H = 1080, 1920
FONT_NAME = "Montserrat Black"
FONTS_DIR = Path(__file__).resolve().parent.parent / "assets" / "fonts"

CHAR_BUDGET = 38          # символов на чанк субтитров (кириллица длиннее английской)
MAX_WORDS_PER_CHUNK = 4
HOOK_MAX_WORDS = 8
HOOK_MAX_SECONDS = 2.0    # хук держится не дольше этого, даже если слова длиннее
HOOK_MIN_SECONDS = 1.5

PUNCH_ZOOM = 1.12         # во сколько раз "впрыгиваем" при punch-in
PUNCH_EASE = 0.12         # длительность самого прыжка (сек), дальше держим уровень
PUNCH_MIN_GAP = 3.5       # не чаще одного пунча за этот интервал (сек)
PUNCH_MAX_COUNT = 40      # защита от чрезмерно длинной ffmpeg-expr на 5-минутном видео


def run(cmd, **kw):
    print("+", " ".join(str(c) for c in cmd), file=sys.stderr)
    return subprocess.run(cmd, check=True, **kw)


def ffprobe_duration(path):
    out = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration",
         "-of", "json", str(path)],
        check=True, capture_output=True, text=True,
    ).stdout
    return float(json.loads(out)["format"]["duration"])


def transcribe(path):
    """Faster-whisper с пословными таймстампами. Возвращает список
    {word, start, end} в порядке звучания."""
    from faster_whisper import WhisperModel

    model = WhisperModel("small", device="cpu", compute_type="int8")
    segments, _ = model.transcribe(
        str(path), word_timestamps=True, vad_filter=True,
    )
    words = []
    for seg in segments:
        for w in seg.words:
            words.append({
                "word": w.word.strip(),
                "start": float(w.start),
                "end": float(w.end),
            })
    return words


def detect_face_center_x(path: Path) -> float:
    """Возвращает относительный (0..1) x-центр лица, усреднённый по кадрам.
    Если лицо не найдено ни на одном сэмпле — 0.5 (центр кадра)."""
    import cv2

    cascade = cv2.CascadeClassifier(
        cv2.data.haarcascades + "haarcascade_frontalface_default.xml"
    )
    cap = cv2.VideoCapture(str(path))
    total = int(cap.get(cv2.CAP_PROP_FRAME_COUNT)) or 1
    fps = cap.get(cv2.CAP_PROP_FPS) or 25
    width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH)) or 1
    sample_every = max(1, int(fps))  # раз в секунду

    centers = []
    idx = 0
    while True:
        ok, frame = cap.read()
        if not ok:
            break
        if idx % sample_every == 0:
            gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
            faces = cascade.detectMultiScale(gray, 1.2, 5, minSize=(60, 60))
            if len(faces):
                fx = max(faces, key=lambda f: f[2] * f[3])
                cx = fx[0] + fx[2] / 2
                centers.append(cx / width)
        idx += 1
    cap.release()

    if not centers:
        return 0.5
    return sum(centers) / len(centers)


def crop_grade_916(src: Path, dst: Path, face_center_x: float):
    probe = json.loads(subprocess.run(
        ["ffprobe", "-v", "error", "-select_streams", "v:0",
         "-show_entries", "stream=width,height", "-of", "json", str(src)],
        check=True, capture_output=True, text=True,
    ).stdout)["streams"][0]
    src_w, src_h = probe["width"], probe["height"]

    crop_w = round(src_h * 9 / 16)
    if crop_w > src_w:
        crop_w = src_w
    crop_h = src_h
    center_px = face_center_x * src_w
    x = int(min(max(0, center_px - crop_w / 2), src_w - crop_w))

    vf = (
        f"crop={crop_w}:{crop_h}:{x}:0,"
        f"scale={TARGET_W}:{TARGET_H},"
        f"eq=contrast=1.08:saturation=1.06,"
        f"colorbalance=rs=0.04:gs=0.0:bs=-0.05:rm=0.03:gm=0.0:bm=-0.04"
    )
    run([
        "ffmpeg", "-y", "-i", str(src),
        "-vf", vf,
        "-c:v", "libx264", "-preset", "veryfast", "-crf", "19",
        "-c:a", "copy",
        str(dst),
    ])


def pick_punch_times(body_words, hook_end: float, duration: float) -> list:
    """Выбирает моменты punch-in зумов: начало каждого субтитр-чанка (та же
    группировка, что и для текста) после хука, прорежённое минимальным
    интервалом. Порядок величины — 1 пунч на ~3.5-5с, не на каждое слово."""
    candidates = [
        chunk[0]["start"] for chunk in chunk_words(body_words)
        if chunk and chunk[0]["start"] > hook_end
    ]
    picked = []
    last = hook_end
    for t in candidates:
        if t - last >= PUNCH_MIN_GAP and t < duration - 0.5:
            picked.append(t)
            last = t
        if len(picked) >= PUNCH_MAX_COUNT:
            break
    return picked


def _ease_expr(t_var: str, p: float, prev_zoom: float, cur_zoom: float) -> str:
    """smoothstep-переход zoom от prev_zoom к cur_zoom, начиная с момента p,
    длится PUNCH_EASE секунд, дальше остаётся равным cur_zoom (т.к. x
    клэмпится в [0,1] и smoothstep(1)=1) — отдельного 'hold'-плеча не нужно."""
    x = f"min(max(({t_var}-{p:.3f})/{PUNCH_EASE:.3f},0),1)"
    s = f"({x}*{x}*(3-2*{x}))"
    return f"({prev_zoom:.4f}+({cur_zoom:.4f}-{prev_zoom:.4f})*{s})"


def build_zoom_expr(punch_times: list) -> str:
    """Строит вложенный if() на переменную 't', возвращающий текущий
    zoom-уровень кадра. Уровни чередуются BASE(1.0)/PUNCH_ZOOM на каждом
    пункт-моменте — то есть каждый следующий пунч "впрыгивает", следующий за
    ним возвращает в исходный масштаб."""
    if not punch_times:
        return "1.0"
    levels = [PUNCH_ZOOM if i % 2 == 0 else 1.0 for i in range(len(punch_times))]
    prev_levels = [1.0] + levels[:-1]

    expr = "1.0"
    for p, prev, cur in zip(punch_times, prev_levels, levels):
        inner = _ease_expr("t", p, prev, cur)
        expr = f"if(lt(t,{p:.3f}),{expr},{inner})"
    return expr


def punch_zoom(src: Path, dst: Path, punch_times: list):
    """Кроп+скейл с time-varying zoom-уровнем (punch-in), работает уже на
    финальном 1080x1920 кадре (после crop_grade_916) — субтитры затем
    накладываются поверх уже "запунченного" видео и не двигаются вместе с
    зумом, как в CapCut."""
    if not punch_times:
        run(["ffmpeg", "-y", "-i", str(src), "-c", "copy", str(dst)])
        return

    zoom = build_zoom_expr(punch_times)
    crop_w = f"({TARGET_W}/({zoom}))"
    crop_h = f"({TARGET_H}/({zoom}))"
    x = f"(({TARGET_W}-{crop_w})/2)"
    y = f"(({TARGET_H}-{crop_h})/2)"

    vf = (
        f"crop=w='{crop_w}':h='{crop_h}':x='{x}':y='{y}',"
        f"scale={TARGET_W}:{TARGET_H}"
    )
    run([
        "ffmpeg", "-y", "-i", str(src),
        "-vf", vf,
        "-c:v", "libx264", "-preset", "veryfast", "-crf", "19",
        "-c:a", "copy",
        str(dst),
    ])


def ass_escape(text: str) -> str:
    return text.replace("\\", r"\\").replace("{", r"\{").replace("}", r"\}")


def fmt_ts(t: float) -> str:
    h = int(t // 3600)
    m = int((t % 3600) // 60)
    s = t % 60
    return f"{h:d}:{m:02d}:{s:05.2f}"


def build_hook_ass(hook_words, out_path: Path):
    """ASS только с хук-фразой (первые ~1.5-2с) — рендерится через FFmpeg/
    libass, отдельно от основных субтитров (те теперь идут через Shotstack,
    см. build_srt/burn_captions_via_shotstack)."""
    header = f"""[Script Info]
ScriptType: v4.00+
PlayResX: {TARGET_W}
PlayResY: {TARGET_H}
ScaledBorderAndShadow: yes

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Hook,{FONT_NAME},92,&H00FFFFFF,&H000000FF,&H00000000,&H64000000,-1,0,0,0,100,100,0,0,3,24,6,8,70,70,460,1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""
    hook_end = hook_display_end(hook_words)
    hook_text = ass_escape(" ".join(w["word"] for w in hook_words)).upper()
    line = (
        f"Dialogue: 1,{fmt_ts(0.0)},{fmt_ts(hook_end)},Hook,,0,0,0,,"
        f"{{\\fad(180,120)}}{hook_text}\n"
    )
    out_path.write_text(header + line, encoding="utf-8")


def fmt_srt_ts(t: float) -> str:
    h = int(t // 3600)
    m = int((t % 3600) // 60)
    s = int(t % 60)
    ms = round((t - int(t)) * 1000)
    if ms == 1000:
        ms = 0
        s += 1
    return f"{h:02d}:{m:02d}:{s:02d},{ms:03d}"


def build_srt(words, out_path: Path):
    """SRT для внешнего caption-API (Shotstack/ZapCap) — та же группировка
    чанков, что и для ASS (chunk_words), без хука (хук остаётся в FFmpeg,
    см. main()) и без цветовой подсветки ключевого слова (обычный SRT её не
    несёт; для этого нужен RichCaptionAsset — проверить на живом ключе,
    пока используем базовый caption-тип)."""
    hook_words, body_words = split_hook(words)
    hook_end = hook_display_end(hook_words) if hook_words else 0.0

    lines = []
    idx = 1
    for chunk in chunk_words(body_words):
        start = max(chunk[0]["start"], hook_end)
        end = max(chunk[-1]["end"], start + 0.35)
        text = " ".join(w["word"] for w in chunk)
        lines.append(f"{idx}\n{fmt_srt_ts(start)} --> {fmt_srt_ts(end)}\n{text}\n")
        idx += 1

    out_path.write_text("\n".join(lines), encoding="utf-8")


def split_hook(words):
    """Отделяет первые слова хук-фразы (до HOOK_MAX_WORDS слов и не позже
    HOOK_MAX_SECONDS) от остального текста, идущего в обычные субтитры."""
    if not words:
        return [], []
    hook = []
    for w in words:
        if len(hook) >= HOOK_MAX_WORDS or w["start"] >= HOOK_MAX_SECONDS:
            break
        hook.append(w)
    if not hook:
        hook = [words[0]]
    return hook, words[len(hook):]


def hook_display_end(hook_words) -> float:
    raw_end = hook_words[-1]["end"] + 0.2
    return min(max(raw_end, HOOK_MIN_SECONDS), HOOK_MAX_SECONDS + 0.4)


def chunk_words(words):
    """Группирует слова в чанки бегущих субтитров по бюджету символов
    (не по числу слов — русские слова длиннее английских)."""
    chunk = []
    chunk_chars = 0
    for w in words:
        w_len = len(w["word"])
        would_exceed = chunk and (
            chunk_chars + 1 + w_len > CHAR_BUDGET or len(chunk) >= MAX_WORDS_PER_CHUNK
        )
        if would_exceed:
            yield chunk
            chunk = []
            chunk_chars = 0
        chunk.append(w)
        chunk_chars += (1 if chunk_chars else 0) + w_len
        if w["word"].strip().endswith((".", "!", "?", "…")):
            yield chunk
            chunk = []
            chunk_chars = 0
    if chunk:
        yield chunk


def burn_ass(src: Path, ass_path: Path, dst: Path):
    ass_escaped = str(ass_path).replace("\\", "/").replace(":", r"\:")
    fonts_escaped = str(FONTS_DIR).replace("\\", "/").replace(":", r"\:")
    run([
        "ffmpeg", "-y", "-i", str(src),
        "-vf", f"ass={ass_escaped}:fontsdir={fonts_escaped}",
        "-c:v", "libx264", "-preset", "veryfast", "-crf", "19",
        "-c:a", "copy",
        str(dst),
    ])


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("input", type=Path)
    ap.add_argument("--max-seconds", type=float, default=300)
    ap.add_argument("--out", type=Path, default=Path("final.mp4"))
    args = ap.parse_args()

    openai_key = os.environ.get("OPENAI_API_KEY")
    pexels_key = os.environ.get("PEXELS_API_KEY")
    pixabay_key = os.environ.get("PIXABAY_API_KEY")
    shotstack_key = os.environ.get("SHOTSTACK_API_KEY")
    missing = [name for name, val in (
        ("OPENAI_API_KEY", openai_key), ("SHOTSTACK_API_KEY", shotstack_key),
    ) if not val]
    if missing:
        print(f"ОШИБКА: не заданы переменные окружения: {', '.join(missing)}", file=sys.stderr)
        sys.exit(4)
    if not pexels_key and not pixabay_key:
        print("ОШИБКА: задай хотя бы PEXELS_API_KEY или PIXABAY_API_KEY", file=sys.stderr)
        sys.exit(4)

    duration = ffprobe_duration(args.input)
    print(f"Исходная длительность: {duration:.1f}s", file=sys.stderr)
    if duration > args.max_seconds:
        print(
            f"ОШИБКА: видео длиннее лимита ({duration:.1f}s > {args.max_seconds}s)",
            file=sys.stderr,
        )
        sys.exit(2)

    print("Транскрипция...", file=sys.stderr)
    words = transcribe(args.input)
    if not words:
        print("ОШИБКА: транскрипция не вернула слов (тишина/нет речи?)", file=sys.stderr)
        sys.exit(3)

    print("Детекция лица...", file=sys.stderr)
    face_x = detect_face_center_x(args.input)
    print(f"face_center_x={face_x:.3f}", file=sys.stderr)

    cropped_path = Path("cropped.mp4")
    crop_grade_916(args.input, cropped_path, face_x)

    hook_words, body_words = split_hook(words)
    hook_end = hook_display_end(hook_words) if hook_words else 0.0
    punch_times = pick_punch_times(body_words, hook_end, duration)
    print(f"punch-in моментов: {len(punch_times)}", file=sys.stderr)

    punched_path = Path("punched.mp4")
    punch_zoom(cropped_path, punched_path, punch_times)

    if hook_words:
        print("Хук-фраза (FFmpeg/libass)...", file=sys.stderr)
        hook_ass_path = Path("hook.ass")
        build_hook_ass(hook_words, hook_ass_path)
        hooked_path = Path("hooked.mp4")
        burn_ass(punched_path, hook_ass_path, hooked_path)
    else:
        hooked_path = punched_path

    print("B-roll (Pexels/Pixabay, моменты выбирает LLM)...", file=sys.stderr)
    from broll import add_broll
    broll_path = Path("with_broll.mp4")
    add_broll(
        hooked_path, words, duration, broll_path,
        openai_key, pexels_key, pixabay_key, work_dir=Path("."),
    )

    print("Субтитры (Shotstack API)...", file=sys.stderr)
    from shotstack_captions import burn_captions_via_shotstack
    srt_path = Path("subs.srt")
    build_srt(words, srt_path)
    burn_captions_via_shotstack(broll_path, srt_path, args.out, shotstack_key)

    print(f"Готово: {args.out}", file=sys.stderr)


if __name__ == "__main__":
    main()

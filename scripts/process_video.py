#!/usr/bin/env python3
"""
Обработка уже чисто нарезанного видео: транскрипция -> кроп 9:16 по лицу ->
хук-фрейм в первые ~1.5-2с -> word-level субтитры (Montserrat Black, ASS/libass,
подсветка ключевого слова) -> лёгкая цветокоррекция.

Запускается на раннере GitHub Actions из edit-video.yml.
Вход: путь к исходному видео (без пауз/слов-паразитов — вырезаны заранее).
Выход: final.mp4 в текущей директории.
"""
import argparse
import json
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

STOPWORDS_FOR_KEYWORD = {
    "э", "эм", "эмм", "ээ", "ну", "как бы", "типа", "короче", "вот",
    "это самое", "в общем", "значит", "так сказать", "собственно",
    "и", "в", "на", "с", "по", "к", "у", "о", "а", "но", "или", "что", "как",
    "это", "то", "не", "я", "мы", "вы", "он", "она", "они", "да", "нет",
    "the", "a", "an", "and", "or", "of", "to", "in", "on", "is", "it", "i",
}


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


def ass_escape(text: str) -> str:
    return text.replace("\\", r"\\").replace("{", r"\{").replace("}", r"\}")


def fmt_ts(t: float) -> str:
    h = int(t // 3600)
    m = int((t % 3600) // 60)
    s = t % 60
    return f"{h:d}:{m:02d}:{s:05.2f}"


def build_ass(words, out_path: Path):
    header = f"""[Script Info]
ScriptType: v4.00+
PlayResX: {TARGET_W}
PlayResY: {TARGET_H}
ScaledBorderAndShadow: yes

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Default,{FONT_NAME},80,&H00FFFFFF,&H000000FF,&H00000000,&H00000000,-1,0,0,0,100,100,0,0,1,6,0,2,60,60,640,1
Style: Hook,{FONT_NAME},92,&H00FFFFFF,&H000000FF,&H00000000,&H64000000,-1,0,0,0,100,100,0,0,3,24,6,8,70,70,460,1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""
    lines = [header]

    hook_words, body_words = split_hook(words)

    if hook_words:
        hook_end = hook_display_end(hook_words)
        hook_text = ass_escape(" ".join(w["word"] for w in hook_words))
        lines.append(
            f"Dialogue: 1,{fmt_ts(0.0)},{fmt_ts(hook_end)},Hook,,0,0,0,,"
            f"{{\\fad(180,120)}}{hook_text.upper()}\n"
        )
    else:
        hook_end = 0.0

    for chunk in chunk_words(body_words):
        start = max(chunk[0]["start"], hook_end)
        end = max(chunk[-1]["end"], start + 0.35)

        keyword = max(
            chunk,
            key=lambda w: len(w["word"]) if w["word"].strip(".,!?…").lower()
            not in STOPWORDS_FOR_KEYWORD else 0,
        )

        parts = []
        for w in chunk:
            text = ass_escape(w["word"])
            if w is keyword and text.strip(".,!?…"):
                text = f"{{\\c&H00D7FF&}}{text.upper()}{{\\c&HFFFFFF&}}"
            parts.append(text)
        line_text = " ".join(parts)

        lines.append(
            f"Dialogue: 0,{fmt_ts(start)},{fmt_ts(end)},Default,,0,0,0,,{line_text}\n"
        )

    out_path.write_text("".join(lines), encoding="utf-8")


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


def burn_subtitles(src: Path, ass_path: Path, dst: Path):
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

    ass_path = Path("subs.ass")
    build_ass(words, ass_path)

    burn_subtitles(cropped_path, ass_path, args.out)
    print(f"Готово: {args.out}", file=sys.stderr)


if __name__ == "__main__":
    main()

#!/usr/bin/env python3
"""
Обработка видео: транскрипция -> вырезание пауз/слов-паразитов -> кроп 9:16 по лицу
-> субтитры (крупный жирный шрифт, CAPSLOCK на ключевых словах, 1-3 слова на кадр)
-> лёгкая цветокоррекция.

Запускается на раннере GitHub Actions из edit-video.yml.
Вход: путь к исходному видео. Выход: final.mp4 в текущей директории.
"""
import argparse
import json
import subprocess
import sys
from pathlib import Path

MAX_PAUSE = 0.4          # сек — паузы длиннее вырезаются
PAD = 0.06                # сек — защитный отступ вокруг сохраняемых слов
MIN_GAP_KEPT = 0.12        # сек — естественная пауза, которую оставляем между сегментами
TARGET_W, TARGET_H = 1080, 1920

FILLER_WORDS = {
    "э", "эм", "эмм", "ээ", "ну", "как бы", "типа", "короче", "вот",
    "это самое", "в общем", "значит", "так сказать", "собственно",
    "um", "uh", "erm", "like", "you know", "so", "actually", "basically",
}
STOPWORDS_FOR_KEYWORD = FILLER_WORDS | {
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


def is_filler(word: str) -> bool:
    return word.strip(".,!?…").lower() in FILLER_WORDS


def build_keep_segments(words):
    """Строит список (start, end) сегментов оригинального таймлайна, которые
    нужно сохранить: без слов-паразитов и без пауз длиннее MAX_PAUSE."""
    keep = []
    cur_start = None
    prev_end = None

    for w in words:
        if is_filler(w["word"]):
            if cur_start is not None:
                keep.append((cur_start, prev_end + PAD))
                cur_start = None
            prev_end = w["end"]
            continue

        if cur_start is None:
            cur_start = max(0.0, w["start"] - PAD)
        elif prev_end is not None and (w["start"] - prev_end) > MAX_PAUSE:
            keep.append((cur_start, prev_end + PAD))
            cur_start = max(prev_end + PAD, w["start"] - PAD)

        prev_end = w["end"]

    if cur_start is not None and prev_end is not None:
        keep.append((cur_start, prev_end + PAD))

    return keep


def remap_words(words, keep_segments):
    """Пересчитывает таймстампы слов в новый таймлайн после вырезания сегментов
    и возвращает только слова, попавшие в сохранённые сегменты."""
    remapped = []
    offset = 0.0
    for seg_start, seg_end in keep_segments:
        for w in words:
            if is_filler(w["word"]):
                continue
            if seg_start <= w["start"] < seg_end:
                remapped.append({
                    "word": w["word"],
                    "start": offset + (w["start"] - seg_start),
                    "end": offset + (min(w["end"], seg_end) - seg_start),
                })
        offset += (seg_end - seg_start) + MIN_GAP_KEPT
    return remapped


def cut_video(src: Path, keep_segments, dst: Path):
    if not keep_segments:
        raise RuntimeError("Нечего сохранять: транскрипция пустая или всё — паузы/паразиты")

    filter_parts = []
    v_labels, a_labels = [], []
    for i, (s, e) in enumerate(keep_segments):
        filter_parts.append(
            f"[0:v]trim=start={s:.3f}:end={e:.3f},setpts=PTS-STARTPTS[v{i}]"
        )
        filter_parts.append(
            f"[0:a]atrim=start={s:.3f}:end={e:.3f},asetpts=PTS-STARTPTS[a{i}]"
        )
        v_labels.append(f"[v{i}]")
        a_labels.append(f"[a{i}]")

    concat_inputs = "".join(f"{v}{a}" for v, a in zip(v_labels, a_labels))
    filter_parts.append(
        f"{concat_inputs}concat=n={len(keep_segments)}:v=1:a=1[vout][aout]"
    )
    filter_complex = ";".join(filter_parts)

    run([
        "ffmpeg", "-y", "-i", str(src),
        "-filter_complex", filter_complex,
        "-map", "[vout]", "-map", "[aout]",
        "-c:v", "libx264", "-preset", "veryfast", "-crf", "20",
        "-c:a", "aac", "-b:a", "160k",
        str(dst),
    ])


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
Style: Default,Arial Black,88,&H00FFFFFF,&H000000FF,&H00000000,&H00000000,-1,0,0,0,100,100,0,0,1,7,0,2,60,60,220,1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""
    lines = [header]

    CHUNK = 2  # слов на экран (в диапазоне 1-3)
    i = 0
    while i < len(words):
        chunk = words[i:i + CHUNK]
        i += CHUNK
        if not chunk:
            continue
        start, end = chunk[0]["start"], chunk[-1]["end"]
        if end <= start:
            continue

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


def burn_subtitles(src: Path, ass_path: Path, dst: Path):
    ass_escaped = str(ass_path).replace("\\", "/").replace(":", r"\:")
    run([
        "ffmpeg", "-y", "-i", str(src),
        "-vf", f"ass={ass_escaped}",
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

    keep_segments = build_keep_segments(words)
    print(f"Сохраняемых сегментов: {len(keep_segments)}", file=sys.stderr)

    cut_path = Path("cut.mp4")
    cut_video(args.input, keep_segments, cut_path)

    remapped_words = remap_words(words, keep_segments)

    print("Детекция лица...", file=sys.stderr)
    face_x = detect_face_center_x(cut_path)
    print(f"face_center_x={face_x:.3f}", file=sys.stderr)

    cropped_path = Path("cropped.mp4")
    crop_grade_916(cut_path, cropped_path, face_x)

    ass_path = Path("subs.ass")
    build_ass(remapped_words, ass_path)

    burn_subtitles(cropped_path, ass_path, args.out)
    print(f"Готово: {args.out}", file=sys.stderr)


if __name__ == "__main__":
    main()

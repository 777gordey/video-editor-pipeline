#!/usr/bin/env python3
"""
Фоновая музыка + звуки на punch-in — целиком локально, без внешнего API.

Музыка: Pixabay НЕ имеет публичного Music/Audio API (только images/videos,
проверено по https://pixabay.com/api/docs/ 24.09.2026) — в отличие от
b-roll (broll.py), где Pixabay Videos API реально существует. Поэтому здесь
применён тот же паттерн, который для звуков предложил владелец как запасной
вариант: небольшой набор CC0/royalty-free файлов, скачанный один раз и
зашитый в репозиторий (assets/music/, assets/sfx/whoosh/), без платной
интеграции. Источник — Mixkit (Mixkit License: бесплатно для коммерческого
использования, без указания авторства, см. assets/music/LICENSE.md).

Дакинг музыки: НЕ через sidechaincompress (на живом локальном тесте с этой
сборкой ffmpeg он давал только ~3dB просадки вместо ожидаемых 15-20dB при
любых threshold/ratio — по всей видимости, особенность конкретной сборки/
детектора уровня, разбираться не стали). Вместо этого используется точный
дакинг по словам транскрипта, которые уже есть от faster-whisper: для каждого
речевого интервала — доп. volume-фильтр с enable='between(t,start,end)'.
Проверено локально (сегментированный рендер + astats по кускам) — даёт ровно
заданную просадку без артефактов. Жёсткий рез (не плавный fade) на границах
речи — сознательное упрощение, компенсируется паддингом вокруг слов.

Синхронизация whoosh: звук на punch-in ставится не на каждый зум, а только
на те punch-моменты, что совпадают с чанками субтитров, отмеченными LLM как
смыслово важные (см. pick_emphasis_chunks в shotstack_captions.py) — тот же
сигнал управляет и крупным размером текста, и whoosh-акцентом, чтобы эффект
был цельным, а не случайным. Максимум WHOOSH_MAX_COUNT за ролик.
"""
import random
import subprocess
import sys
from pathlib import Path

ASSETS_DIR = Path(__file__).resolve().parent.parent / "assets"
MUSIC_DIR = ASSETS_DIR / "music"
WHOOSH_DIR = ASSETS_DIR / "sfx" / "whoosh"

MUSIC_BASE_DB = -17        # уровень музыки в паузах речи
DUCK_EXTRA_DB = -18        # доп. просадка речевых интервалов (итого -35dB) —
                            # с запасом перекрывает требование "минимум 15-20dB"
SPEECH_MERGE_GAP = 0.35    # слова с паузой меньше этой — один речевой интервал
SPEECH_PAD_BEFORE = 0.08   # музыка начинает гаситься чуть раньше первого слова
SPEECH_PAD_AFTER = 0.15    # и отпускает чуть позже последнего

WHOOSH_DB = -5
WHOOSH_MAX_COUNT = 5
WHOOSH_MIN_COUNT = 3       # если акцентных punch-моментов меньше — добираем равномерно

AUDIO_FMT = "aformat=sample_fmts=fltp:sample_rates=44100:channel_layouts=stereo"


def run(cmd, **kw):
    print("+", " ".join(str(c) for c in cmd), file=sys.stderr)
    return subprocess.run(cmd, check=True, **kw)


def _even_subsample(items: list, n: int) -> list:
    if len(items) <= n:
        return list(items)
    step = len(items) / n
    return [items[int(i * step)] for i in range(n)]


def pick_whoosh_times(punches: list, emphasized_idx: set) -> list:
    """punches — список (time, chunk_index) из pick_punch_times().
    Приоритет — punch-моменты на акцентных чанках (тот же сигнал, что двигает
    размер субтитров); если таких меньше WHOOSH_MIN_COUNT, равномерно
    добирает из всех punch-моментов, чтобы эффект не пропал на коротких
    роликах, где LLM отметила мало акцентов."""
    if not punches:
        return []
    primary = [t for t, idx in punches if idx in emphasized_idx]
    if len(primary) < min(WHOOSH_MIN_COUNT, len(punches)):
        all_times = [t for t, _ in punches]
        primary = _even_subsample(all_times, min(WHOOSH_MAX_COUNT, len(all_times)))
    if len(primary) > WHOOSH_MAX_COUNT:
        primary = _even_subsample(primary, WHOOSH_MAX_COUNT)
    return sorted(primary)


def merge_speech_regions(words: list) -> list:
    """Схлопывает пословные таймстампы транскрипта в непрерывные речевые
    интервалы [(start,end), ...], объединяя соседние слова с паузой меньше
    SPEECH_MERGE_GAP — иначе на дакинг ушёл бы отдельный volume-фильтр на
    каждое слово (сотни за ролик, раздутый filter_complex без пользы: паузы
    между словами внутри фразы всё равно короче ощутимой реакции слуха)."""
    if not words:
        return []
    regions = []
    cur_start = max(0.0, words[0]["start"] - SPEECH_PAD_BEFORE)
    cur_end = words[0]["end"] + SPEECH_PAD_AFTER
    for w in words[1:]:
        if w["start"] - cur_end <= SPEECH_MERGE_GAP:
            cur_end = max(cur_end, w["end"] + SPEECH_PAD_AFTER)
        else:
            regions.append((cur_start, cur_end))
            cur_start = max(0.0, w["start"] - SPEECH_PAD_BEFORE)
            cur_end = w["end"] + SPEECH_PAD_AFTER
    regions.append((cur_start, cur_end))
    return regions


def pick_music_track() -> Path:
    tracks = sorted(MUSIC_DIR.glob("*.mp3"))
    if not tracks:
        raise RuntimeError(f"Нет треков в {MUSIC_DIR} — проверь, что assets/music закоммичен")
    return random.choice(tracks)


def pick_whoosh_clip() -> Path:
    clips = sorted(WHOOSH_DIR.glob("*.mp3"))
    if not clips:
        raise RuntimeError(f"Нет звуков в {WHOOSH_DIR} — проверь, что assets/sfx/whoosh закоммичен")
    return random.choice(clips)


def mix_audio(src: Path, dst: Path, duration: float, words: list, whoosh_times: list):
    """Накладывает зациклённую фоновую музыку (с дакингом под речь по точным
    словесным таймстемпам) и whoosh-звуки в заданные моменты. Видео-поток не
    трогается (-map 0:v -c:v copy), меняется только звук."""
    music_path = pick_music_track()
    whoosh_paths = [pick_whoosh_clip() for _ in whoosh_times]
    regions = merge_speech_regions(words)

    music_chain = f"atrim=0:{duration:.3f},asetpts=PTS-STARTPTS,{AUDIO_FMT},volume={MUSIC_BASE_DB}dB"
    for s, e in regions:
        music_chain += f",volume={DUCK_EXTRA_DB}dB:enable='between(t,{s:.3f},{e:.3f})'"

    parts = [
        f"[0:a]{AUDIO_FMT}[voice]",
        f"[1:a]{music_chain}[music]",
    ]
    whoosh_labels = []
    for i, t in enumerate(whoosh_times):
        label = f"w{i}"
        delay_ms = round(t * 1000)
        parts.append(f"[{2 + i}:a]{AUDIO_FMT},adelay={delay_ms}:all=1,volume={WHOOSH_DB}dB[{label}]")
        whoosh_labels.append(f"[{label}]")

    mix_inputs = "[voice][music]" + "".join(whoosh_labels)
    total_inputs = 2 + len(whoosh_times)
    parts.append(
        f"{mix_inputs}amix=inputs={total_inputs}:duration=first:dropout_transition=0:normalize=0[aout]"
    )
    filter_complex = ";".join(parts)

    whoosh_input_args = []
    for p in whoosh_paths:
        whoosh_input_args += ["-i", str(p)]

    run([
        "ffmpeg", "-y",
        "-i", str(src),
        "-stream_loop", "-1", "-i", str(music_path),
        *whoosh_input_args,
        "-filter_complex", filter_complex,
        "-map", "0:v", "-map", "[aout]",
        "-c:v", "copy", "-c:a", "aac", "-b:a", "192k",
        str(dst),
    ])

"""Общие утилиты движка v2: конфиг, запуск команд, ffprobe."""
import json
import subprocess
import sys
from pathlib import Path

ENGINE_DIR = Path(__file__).resolve().parent
REPO_DIR = ENGINE_DIR.parent
sys.path.insert(0, str(REPO_DIR / "scripts"))   # openai_http.py лежит там

CONFIG = json.loads((ENGINE_DIR / "config.json").read_text(encoding="utf-8"))
SPEED = float(CONFIG["SPEED"])          # единственная настройка скорости
FPS = int(CONFIG["FPS"])
W, H = int(CONFIG["WIDTH"]), int(CONFIG["HEIGHT"])
AR = int(CONFIG["AUDIO_RATE"])
LUFS = float(CONFIG["LOUDNESS_LUFS"])


def log(*a):
    print(*a, flush=True)


def run(cmd, **kw):
    cmd = [str(c) for c in cmd]
    log("+", " ".join(cmd)[:400])
    return subprocess.run(cmd, check=True, **kw)


def probe(path, entries, stream=None):
    cmd = ["ffprobe", "-v", "error"]
    if stream:
        cmd += ["-select_streams", stream]
    cmd += ["-show_entries", entries, "-of", "json", str(path)]
    return json.loads(subprocess.run(cmd, check=True, capture_output=True, text=True).stdout)


def duration(path) -> float:
    return float(probe(path, "format=duration")["format"]["duration"])


def load_json(p):
    return json.loads(Path(p).read_text(encoding="utf-8"))


def save_json(p, obj):
    Path(p).write_text(json.dumps(obj, ensure_ascii=False, indent=1), encoding="utf-8")

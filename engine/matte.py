#!/usr/bin/env python3
"""Вырезание фона: Robust Video Matting (ONNX, CPU) на пониженном разрешении.

matte(): prepped.mp4 -> alpha_small.mkv (gray, 540x960, FFV1)
build_layers(): из графированного кадра + альфы делает два видео для слоя
«за мной» без альфа-канала в браузере (надёжно для headless Chrome):
  inv.mp4   = 1-alpha     (CSS mix-blend-mode: multiply  — вырезает дырку в фоне)
  black.mp4 = я на чёрном (CSS mix-blend-mode: screen    — добавляет меня)
bg*(1-a) + person*a  == точная формула композитинга.
"""
import hashlib
import os
import subprocess
import sys
import urllib.request
from pathlib import Path

import numpy as np

from common import FPS, W, H, log, run

MODEL_URL = "https://github.com/PeterL1n/RobustVideoMatting/releases/download/v1.0.0/rvm_mobilenetv3_fp32.onnx"
MODEL_SHA256 = os.environ.get("RVM_SHA256", "88d4531297118f595bf2fd60f6f566aec2e559393802d1f436c380f0cbbd2828")
MW, MH = 540, 960
DOWNSAMPLE = 0.5


def fetch_model(dst: Path) -> Path:
    if not dst.exists():
        log(f"[matte] downloading RVM mobilenetv3 fp32 onnx")
        urllib.request.urlretrieve(MODEL_URL, dst)
    h = hashlib.sha256(dst.read_bytes()).hexdigest()
    log(f"[matte] model sha256={h}")
    if MODEL_SHA256 and h != MODEL_SHA256:
        raise RuntimeError("RVM model sha256 mismatch")
    return dst


def matte(video: Path, out_alpha: Path, model_path: Path):
    import onnxruntime as ort
    so = ort.SessionOptions()
    so.intra_op_num_threads = os.cpu_count() or 4
    sess = ort.InferenceSession(str(fetch_model(model_path)), so, providers=["CPUExecutionProvider"])
    rec = [np.zeros((1, 1, 1, 1), np.float32) for _ in range(4)]
    ratio = np.array([DOWNSAMPLE], np.float32)
    dec = subprocess.Popen(
        ["ffmpeg", "-loglevel", "error", "-i", str(video), "-an", "-vf", f"scale={MW}:{MH}:flags=area",
         "-f", "rawvideo", "-pix_fmt", "rgb24", "-"], stdout=subprocess.PIPE)
    enc = subprocess.Popen(
        ["ffmpeg", "-y", "-loglevel", "error", "-f", "rawvideo", "-pix_fmt", "gray", "-s", f"{MW}x{MH}",
         "-r", str(FPS), "-i", "-", "-c:v", "ffv1", str(out_alpha)], stdin=subprocess.PIPE)
    fsz = MW * MH * 3
    n = 0
    import time
    t0 = time.time()
    while True:
        buf = dec.stdout.read(fsz)
        if len(buf) < fsz:
            break
        src = np.frombuffer(buf, np.uint8).reshape(MH, MW, 3).astype(np.float32).transpose(2, 0, 1)[None] / 255.0
        fgr, pha, *rec = sess.run(None, {"src": src, "r1i": rec[0], "r2i": rec[1], "r3i": rec[2],
                                          "r4i": rec[3], "downsample_ratio": ratio})
        enc.stdin.write((np.clip(pha[0, 0], 0, 1) * 255).astype(np.uint8).tobytes())
        n += 1
        if n % 300 == 0:
            log(f"[matte] {n} frames, {n / (time.time() - t0):.1f} fps")
    enc.stdin.close()
    enc.wait()
    dec.wait()
    if n == 0 or enc.returncode != 0:
        raise RuntimeError("matte produced no frames")
    log(f"[matte] done {n} frames in {time.time() - t0:.0f}s ({n / (time.time() - t0):.1f} fps)")


def build_layers(person: Path, alpha_small: Path, inv_out: Path, black_out: Path):
    a = (f"[1:v]scale={W}:{H}:flags=lanczos,format=gray,gblur=sigma=1.4,"
         f"curves=all='0/0 0.08/0 0.92/1 1/1',format=gray")   # чуть сжимаем края: меньше ореола
    run(["ffmpeg", "-y", "-loglevel", "error", "-i", person, "-i", alpha_small, "-filter_complex",
         f"{a},negate[inv];[inv]format=yuv420p[o]", "-map", "[o]", "-an", "-c:v", "libx264", "-preset", "fast",
         "-crf", 12, "-r", FPS, inv_out])
    run(["ffmpeg", "-y", "-loglevel", "error", "-i", person, "-i", alpha_small, "-filter_complex",
         f"{a}[al];[0:v]format=yuv444p[p];[p][al]alphamerge[pa];"
         f"color=c=black:s={W}x{H}:r={FPS}[bk];[bk][pa]overlay=shortest=1:format=auto,format=yuv420p[o]",
         "-map", "[o]", "-an", "-c:v", "libx264", "-preset", "fast", "-crf", 12, "-r", FPS, black_out])


if __name__ == "__main__":
    matte(Path(sys.argv[1]), Path(sys.argv[2]), Path(sys.argv[3]) if len(sys.argv) > 3 else Path("rvm.onnx"))

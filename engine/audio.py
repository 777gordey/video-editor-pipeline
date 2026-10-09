"""Звук версии: SFX и атмосфера синтезируются кодом, музыка из brand/music
(затем assets/music, затем синтетический бит), биты через librosa,
дакинг под голос, -14 LUFS (двухпроходный loudnorm). Музыка и атмосфера
добавляются ПОСЛЕ ускорения и сами не ускоряются."""
import json
import re
import subprocess
from pathlib import Path

import numpy as np

from common import AR as SR, LUFS, REPO_DIR, log, run

AUDIO_EXT = (".mp3", ".wav", ".m4a", ".ogg", ".flac")


def _write_wav(path, x):
    import wave
    x = np.clip(x, -1, 1)
    with wave.open(str(path), "wb") as f:
        f.setnchannels(1)
        f.setsampwidth(2)
        f.setframerate(SR)
        f.writeframes((x * 32767).astype("<i2").tobytes())


def _bandpass(x, lo, hi):
    X = np.fft.rfft(x)
    f = np.fft.rfftfreq(len(x), 1 / SR)
    X[(f < lo) | (f > hi)] = 0
    return np.fft.irfft(X, len(x))


def _lowpass_sweep(x, f0, f1):
    """однополюсный ФНЧ с плавающей частотой среза"""
    n = len(x)
    fc = np.geomspace(f0, f1, n)
    a = 1 - np.exp(-2 * np.pi * fc / SR)
    y = np.empty(n)
    acc = 0.0
    for i in range(n):
        acc += a[i] * (x[i] - acc)
        y[i] = acc
    return y


def synth_sfx(kind, rng):
    if kind == "hit":
        n = int(0.5 * SR)
        t = np.arange(n) / SR
        body = np.sin(2 * np.pi * (50 + 90 * np.exp(-t * 18)) * t) * np.exp(-t * 7)
        click = _lowpass_sweep(rng.standard_normal(n), 3000, 300) * np.exp(-t * 40) * 0.5
        return 0.9 * (body + click)
    if kind == "whoosh":
        n = int(0.55 * SR)
        t = np.arange(n) / SR
        env = np.sin(np.pi * np.clip(t / 0.55, 0, 1)) ** 2
        return 0.55 * _lowpass_sweep(rng.standard_normal(n), 400, 7000) * env
    if kind == "pop":
        n = int(0.14 * SR)
        t = np.arange(n) / SR
        return 0.6 * np.sin(2 * np.pi * (300 + 900 * np.exp(-t * 28)) * t) * np.exp(-t * 26)
    if kind == "riser":
        n = int(0.9 * SR)
        t = np.arange(n) / SR
        env = (t / 0.9) ** 1.6
        tone = np.sin(2 * np.pi * (200 + 1100 * (t / 0.9) ** 2) * t) * 0.35
        noise = _lowpass_sweep(rng.standard_normal(n), 500, 6000) * 0.5
        return 0.55 * (tone + noise) * env
    if kind == "click":
        n = int(0.03 * SR)
        t = np.arange(n) / SR
        return 0.4 * rng.standard_normal(n) * np.exp(-t * 180)
    raise ValueError(kind)


def build_sfx_track(plan, dur, path):
    rng = np.random.default_rng(7)
    out = np.zeros(int((dur + 1.5) * SR))
    for e in plan["sfx"]:
        s = synth_sfx(e["kind"], rng) * e["gain"]
        i = int(e["t"] * SR)
        out[i:i + len(s)] += s[: len(out) - i]
    _write_wav(path, out[: int(dur * SR)])


def build_ambience(kind, dur, path):
    rng = np.random.default_rng(11)
    n = int(dur * SR)
    if kind == "crowd":
        x = _bandpass(rng.standard_normal(n), 250, 3500)
        am = np.zeros(n)
        for _ in range(14):     # «голоса»: медленные независимые огибающие
            e = _bandpass(rng.standard_normal(n), 0.2, 4)
            e = np.clip(e / (np.std(e) + 1e-9), 0, None)
            band = _bandpass(rng.standard_normal(n), int(rng.integers(300, 1200)), int(rng.integers(1500, 3200)))
            am += e * band
        x = 0.15 * x / (np.std(x) + 1e-9) + 0.25 * am / (np.std(am) + 1e-9)
    elif kind == "birds":
        x = _bandpass(rng.standard_normal(n), 80, 600) * 0.06     # лёгкий ветер
        t = 0.3
        while t < dur - 0.4:
            d = rng.uniform(0.07, 0.22)
            f0 = rng.uniform(2400, 5200)
            sweep = rng.uniform(-1200, 1800)
            k = int(d * SR)
            tt = np.arange(k) / SR
            ch = np.sin(2 * np.pi * (f0 * tt + 0.5 * sweep * tt ** 2 / d) + 6 * np.sin(2 * np.pi * 28 * tt))
            ch *= np.sin(np.pi * tt / d) ** 2 * rng.uniform(0.15, 0.4)
            i = int(t * SR)
            x[i:i + k] += ch[: n - i]
            t += rng.uniform(0.25, 1.1) if rng.random() < 0.8 else rng.uniform(1.5, 3.0)
    else:
        x = np.zeros(n)
    _write_wav(path, x / (np.max(np.abs(x)) + 1e-9) * 0.5)


def synth_music(dur, path, bpm=100):
    """Заглушка, если brand/music и assets/music пусты: кик/хэт + бас."""
    n = int((dur + 1) * SR)
    x = np.zeros(n)
    rng = np.random.default_rng(3)
    beat = 60.0 / bpm
    for k in range(int((dur + 1) / beat) + 1):
        i = int(k * beat * SR)
        if k % 2 == 0:
            s = synth_sfx("hit", rng) * 0.9
            x[i:i + len(s)] += s[: n - i]
        hn = int(0.04 * SR)
        h = rng.standard_normal(hn) * np.exp(-np.arange(hn) / SR * 90) * 0.25
        j = i + int(beat * SR / 2)
        x[j:j + hn] += h[: max(0, n - j)]
    t = np.arange(n) / SR
    x += 0.12 * np.sin(2 * np.pi * 55 * t) * (0.6 + 0.4 * np.sin(2 * np.pi * t / (beat * 4)))
    _write_wav(path, x[: int(dur * SR)])
    return [k * beat for k in range(int(dur / beat))]


def find_music():
    for d in (REPO_DIR / "brand" / "music", REPO_DIR / "assets" / "music"):
        fs = sorted(p for p in d.glob("*") if p.suffix.lower() in AUDIO_EXT) if d.exists() else []
        if fs:
            return d, fs
    return None, []


def beats_of(path):
    try:
        import librosa
        y, sr = librosa.load(str(path), sr=22050, mono=True)
        _, bt = librosa.beat.beat_track(y=y, sr=sr, units="time")
        return [float(b) for b in bt]
    except Exception as e:  # noqa
        log(f"[audio] librosa beats failed: {type(e).__name__}: {e}")
        return []


def prepare_music(style, dur, path):
    """-> (источник, список битов в секундах)"""
    d, files = find_music()
    if not files:
        log("[audio] MUSIC: brand/music пуст — музыка, написанная кодом (аккорды/бас/клавиши/ударные), пресет", style["music_idx"])
        import music as music_mod
        x, kicks = music_mod.compose_track(dur, style["music_idx"])
        _write_wav(path, x)
        return "composed", kicks
    src = files[style["music_idx"] % len(files)]
    fade = max(dur - 1.5, 0)
    run(["ffmpeg", "-y", "-loglevel", "error", "-stream_loop", "-1", "-i", src, "-t", f"{dur:.3f}",
         "-af", f"afade=t=in:d=0.5,afade=t=out:st={fade:.3f}:d=1.5", "-ar", SR, "-ac", 1, path])
    return src.name, beats_of(path)


def mix(voice_media, music, amb, sfx, style, out_wav):
    """voice_media: prepped.mp4. Двухпроходный loudnorm до LUFS."""
    voice_f = ("highpass=f=85,afftdn=nr=12:nf=-38:tn=1,equalizer=f=220:t=q:w=1:g=-1.5,equalizer=f=3200:t=q:w=1.1:g=2.5,"
               "equalizer=f=8500:t=h:w=1:g=1.2,deesser=i=0.4:m=0.5:f=0.5,acompressor=threshold=-22dB:ratio=2.8:attack=6:release=150:makeup=2.5,"
               "alimiter=limit=0.93:attack=2:release=40")
    def _lufs(args, fl):
        r = subprocess.run(["ffmpeg", "-hide_banner", "-nostats", *args, "-af", fl + ",loudnorm=I=-23:print_format=json", "-f", "null", "-"],
                           capture_output=True, text=True)
        mm = re.search(r"\{[^{}]*\"input_i\"[^{}]*\}", r.stderr, re.S)
        return float(json.loads(mm.group(0))["input_i"]) if mm else None
    g = style["music_gain_db"]
    rel = style.get("music_rel_db")
    if rel is not None:                       # музыка = голос + rel LU (до дакинга), а не «на глаз»
        lv, lm = _lufs(["-i", str(voice_media), "-vn"], voice_f), _lufs(["-i", str(music)], "anull")
        if lv is not None and lm is not None:
            g = round(lv + rel - lm, 1)
            style["music_gain_db"] = g
            log(f"[audio] voice {lv:.1f} LUFS, music {lm:.1f} LUFS -> music gain {g} dB (voice {rel:+} LU, then ducked)")
    chain = (f"[0:a]{voice_f},asplit=2[v1][v2];[1:a]volume={g}dB[m0];"
             f"[m0][v2]sidechaincompress=threshold=0.03:ratio=9:attack=12:release=450[md];"
             f"[2:a]volume=-27dB[amb];"
             f"[v1][md][amb][3:a]amix=inputs=4:duration=first:normalize=0")
    ins = ["-i", str(voice_media), "-i", str(music), "-i", str(amb), "-i", str(sfx)]
    p1 = subprocess.run(["ffmpeg", "-hide_banner", "-nostats", *ins, "-filter_complex",
                         chain + f",loudnorm=I={LUFS}:TP=-1.5:LRA=11:print_format=json[o]",
                         "-map", "[o]", "-f", "null", "-"], capture_output=True, text=True)
    m = re.search(r"\{[^{}]*\"input_i\"[^{}]*\}", p1.stderr, re.S)
    if p1.returncode != 0 or not m:
        raise RuntimeError("loudnorm pass1 failed: " + p1.stderr[-400:])
    j = json.loads(m.group(0))
    # линейное усиление до цели + мягкий лимитер на -1.5 dBFS (loudnorm linear упирался в пики голоса и давал -15 LUFS)
    gain = LUFS - float(j["input_i"])
    for attempt in range(3):         # лимитер съедает часть громкости: замеряем результат и доводим до цели
        ln = f"volume={gain:.2f}dB,alimiter=limit=0.86:attack=3:release=60:level=disabled"
        run(["ffmpeg", "-y", "-loglevel", "error", *ins, "-filter_complex", chain + f",{ln},aresample={SR}[o]",
             "-map", "[o]", "-ac", 2, "-ar", SR, out_wav])
        pm = subprocess.run(["ffmpeg", "-hide_banner", "-nostats", "-i", str(out_wav), "-af",
                             f"loudnorm=I={LUFS}:TP=-1.5:LRA=11:print_format=json", "-f", "null", "-"],
                            capture_output=True, text=True)
        mm = re.search(r"\{[^{}]*\"input_i\"[^{}]*\}", pm.stderr, re.S)
        if not mm:
            break
        jm = json.loads(mm.group(0))
        li, tp = float(jm["input_i"]), float(jm["input_tp"])
        log(f"[audio] attempt {attempt}: {li:.2f} LUFS, true peak {tp:.2f} dBTP")
        if abs(li - LUFS) <= 0.35 or tp > -1.1:
            break
        gain += (LUFS - li)
    log(f"[audio] loudnorm pass1 input_i={j['input_i']} -> target {LUFS} LUFS")


def duck_stats(voice_media, music, style, words, out_json):
    """Насколько музыка тише голоса ВО ВРЕМЯ речи (после sidechain). Пишет duck json."""
    import numpy as np
    g = style["music_gain_db"]
    def pcm(args):
        p = subprocess.run(["ffmpeg", "-v", "error", *args, "-ac", "1", "-ar", "16000", "-f", "s16le", "-"], capture_output=True)
        return np.frombuffer(p.stdout, np.int16).astype(np.float32) / 32768.0
    v = pcm(["-i", str(voice_media), "-vn"])
    md = pcm(["-i", str(voice_media), "-i", str(music), "-filter_complex",
              f"[0:a]asplit=2[v1][v2];[1:a]volume={g}dB[m0];[m0][v2]sidechaincompress=threshold=0.03:ratio=9:attack=12:release=450[md]",
              "-map", "[md]"])
    n = min(len(v), len(md))
    vr, mr = [], []
    for w in words:
        a, b = int(w["start"] * 16000), int(w["end"] * 16000)
        if b - a > 800 and b <= n:
            vr.append(float(np.sqrt((v[a:b] ** 2).mean() + 1e-12)))
            mr.append(float(np.sqrt((md[a:b] ** 2).mean() + 1e-12)))
    if not vr:
        return None
    res = {"voice_db": round(20 * np.log10(np.median(vr)), 1), "music_under_speech_db": round(20 * np.log10(np.median(mr)), 1)}
    res["margin_db"] = round(res["voice_db"] - res["music_under_speech_db"], 1)
    Path(out_json).write_text(json.dumps(res), encoding="utf-8")
    return res

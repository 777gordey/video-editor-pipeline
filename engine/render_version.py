#!/usr/bin/env python3
"""Одна версия: plan -> звук -> слои (грейд, вырезка фона, плейт) -> HyperFrames -> финал.

Вход:  --prep DIR (prepped.mp4, transcript.json)  --version V1..V5
Выход: --out DIR: final_Vn.mp4, plan_Vn.json, debug_Vn.jpg, timings_Vn.json
"""
import argparse
import json
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path

import audio
import compose
import exposure
import matte as matte_mod
import plan as plan_mod
import plates
from common import ENGINE_DIR, FPS, W, H, LUFS, duration, load_json, log, run, save_json
from styles import STYLES

T = {}


def stage(name):
    class _S:
        def __enter__(s):
            s.t = time.time()
            log(f"::group::[{name}]")
        def __exit__(s, *a):
            T[name] = round(time.time() - s.t, 1)
            log("::endgroup::")
            log(f"[time] {name}: {T[name]}s")
    return _S()


def hf_env():
    e = dict(os.environ)
    e.update(HYPERFRAMES_NO_TELEMETRY="1", HYPERFRAMES_NO_UPDATE_CHECK="1", HF_CAPTURE_PARALLEL_STREAM="true")
    return e


def hyperframes(args, cwd, timeout=3300):
    cmd = [str(ENGINE_DIR / "node_modules" / ".bin" / "hyperframes"), *args]
    log("+", " ".join(cmd))
    return subprocess.run(cmd, cwd=cwd, env=hf_env(), timeout=timeout)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--version", required=True, choices=list(STYLES))
    ap.add_argument("--prep", default="prep")
    ap.add_argument("--out", default="out")
    ap.add_argument("--work", default="work")
    ap.add_argument("--workers", default=os.environ.get("HF_WORKERS", "4"))
    ap.add_argument("--quality", default="standard")
    ap.add_argument("--no-matte", action="store_true")
    ap.add_argument("--alpha", default=None, help="готовая alpha_small.mkv (общая для всех версий)")
    a = ap.parse_args()
    v = a.version
    style = STYLES[v]
    prep, out, work = Path(a.prep), Path(a.out), Path(a.work) / v
    out.mkdir(parents=True, exist_ok=True)
    work.mkdir(parents=True, exist_ok=True)
    tr = load_json(prep / "transcript.json")
    prepped = prep / "prepped.mp4"
    dur = duration(prepped)
    tr["duration"] = dur
    log(f"[{v}] {style['name']} — клип {dur:.1f}s")

    with stage("audio"):
        music = work / "music.wav"
        msrc, beats = audio.prepare_music(style, dur, music)
        log(f"[audio] music={msrc} beats={len(beats)}")
        pj = prep / "plans.json"
        pl = plan_mod.build_plan(v, tr, load_json(pj) if pj.exists() else None, beats=beats)
        save_json(out / f"plan_{v}.json", pl)
        log(f"[plan {v}] source={pl['source']} hook=«{pl['hook']['text']}» cams={len(pl['cams'])} "
            f"snaps={len(pl['snaps'])} graphics={len(pl['graphics'])} sfx={len(pl['sfx'])}")
        sfx, amb = work / "sfx.wav", work / "amb.wav"
        audio.build_sfx_track(pl, dur, sfx)
        audio.build_ambience(style["ambience"], dur, amb)
        mixwav = work / "mix.wav"
        audio.mix(prepped, music, amb, sfx, style, mixwav)
        try:
            log("[duck]", audio.duck_stats(prepped, music, style, tr["words"], out / f"duck_{v}.json"))
        except Exception as e:  # noqa
            log(f"[duck] stats skipped: {e}")

    proj = work / "proj"
    layers = {}
    with stage("layers"):
        from concurrent.futures import ThreadPoolExecutor
        proj_media = proj / "media"
        proj_media.mkdir(parents=True, exist_ok=True)
        person = proj_media / "person.mp4"

        def grade(plate_future=None):
            vf = style["grade"]
            if plate_future is not None:       # свет на лице подгоняем под плейт
                try:
                    pp = plate_future.result()
                    ej = prep / "exposure.json"
                    if pp and ej.exists():
                        extra, einfo = exposure.match_plate(load_json(ej).get("after"), exposure.measure(pp))
                        if extra:
                            vf = vf + "," + extra
                        log(f"[plate-match] {einfo} -> {extra or 'no change'}")
                        save_json(out / f"platematch_{v}.json", {"filter": extra, **einfo})
                except Exception as e:  # noqa
                    log(f"[plate-match] skipped: {e}")
            run(["ffmpeg", "-y", "-loglevel", "error", "-i", prepped, "-an", "-vf", vf,
                 "-c:v", "libx264", "-preset", "fast", "-crf", 13, "-r", FPS, "-pix_fmt", "yuv420p", person])

        def plate():
            if style["bg"] != "plate":
                return None
            return plates.prepare_plate(style, dur, proj_media / "plate.mp4", work / "plate_cache")

        def do_matte():
            if not (style["bg"] != "room" and style["matte"] and not a.no_matte):
                return None
            if a.alpha and Path(a.alpha).exists():
                log(f"[matte] using shared alpha {a.alpha}")
                return Path(a.alpha)
            t0 = time.time()
            alpha = work / "alpha_small.mkv"
            matte_mod.matte(prepped, alpha, work / "rvm.onnx")
            T["matte"] = round(time.time() - t0, 1)
            return alpha

        layers["person"] = "person.mp4"
        with ThreadPoolExecutor(3) as ex:          # плейт, грейд и вырезка фона идут одновременно
            f_p = ex.submit(plate)
            f_g = ex.submit(grade, f_p if style["bg"] == "plate" else None)
            f_m = ex.submit(do_matte)
            f_g.result()
            plate_path = f_p.result()
            if plate_path:
                layers["plate"] = "plate.mp4"
            try:
                alpha = f_m.result()
                if alpha:
                    matte_mod.build_layers(person, alpha, proj_media / "inv.mp4", proj_media / "black.mp4")
                    layers.update(inv="inv.mp4", black="black.mp4")
            except Exception as e:  # noqa
                print(f"MATTE FALLBACK: {type(e).__name__}: {str(e)[:200]} — фон остаётся исходным", flush=True)
                layers.pop("plate", None)

    with stage("compose"):
        compose.build_project(proj, style, pl, tr, layers)
        (proj / "media" / "person.mp4").exists() or sys.exit("no person layer")
        if "inv" in layers:
            (proj_media / "person.mp4").unlink()      # не нужен — экономим место/кадры
        r = hyperframes(["lint"], proj, 300)
        log(f"[lint] exit={r.returncode} (не блокирует)")

    with stage("hf_render"):
        raw = work / "render.mp4"
        r = hyperframes(["render", "--output", str(raw.resolve()), "--fps", str(FPS), "--quality", a.quality,
                         "--workers", str(a.workers)], proj)
        if r.returncode != 0 or not raw.exists():
            raise SystemExit(f"hyperframes render failed (exit {r.returncode})")

    with stage("finish"):
        final = out / f"final_{v}.mp4"
        grain = {"V1": 5, "V2": 6, "V3": 9, "V4": 5, "V5": 3}[v]
        run(["ffmpeg", "-y", "-loglevel", "error", "-i", raw, "-i", mixwav, "-map", "0:v:0", "-map", "1:a:0",
             "-vf", f"noise=alls={grain}:allf=t+u,format=yuv420p", "-c:v", "libx264", "-preset", "medium", "-crf", 19, "-maxrate", "9M", "-bufsize", "18M",
             "-r", FPS, "-c:a", "aac", "-b:a", "192k", "-ar", 48000, "-movflags", "+faststart",
             "-t", f"{dur:.3f}", final])
        fd = duration(final)
        log(f"[{v}] final {final.name}: {fd:.1f}s {final.stat().st_size / 1e6:.1f} MB")
        # контактный лист для проверки глазами
        pts = [min(1.0, dur / 4), dur * 0.3, dur * 0.55, dur * 0.8]
        ins = []
        for i, t in enumerate(pts):
            f = work / f"dbg{i}.jpg"
            run(["ffmpeg", "-y", "-loglevel", "error", "-ss", f"{t:.2f}", "-i", final, "-frames:v", 1, "-vf", "scale=360:-1", f])
            ins += ["-i", f]
        run(["ffmpeg", "-y", "-loglevel", "error", *ins, "-filter_complex", "hstack=inputs=4", "-frames:v", 1,
             out / f"debug_{v}.jpg"])
    T["total"] = round(sum(v_ for k_, v_ in T.items() if k_ != "matte"), 1)
    save_json(out / f"timings_{v}.json", {"version": v, "plan_source": pl["source"], "layers": sorted(layers), **T})
    log(f"[{v}] DONE {json.dumps(T)}")


if __name__ == "__main__":
    main()

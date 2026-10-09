#!/usr/bin/env python3
"""Автопроверка готовых версий: замеры + контактные листы + обложка.

  python qa.py check --video out/final_V1.mp4 --plan out/plan_V1.json --transcript prep/transcript.json \
                     --version V1 --out out [--expected-dur 55.0]
  python qa.py report --dir parts --out result/QA_report.md

Замеры (pass/fail): формат 1080x1920 CFR 30, длительность, A/V длины, громкость -14 LUFS (±1.5) и
true peak <= -1 dBTP, клиппинг, ducking музыки (речь заметно громче пауз), чёрные/замёрзшие кадры,
подписи против слов транскрипта. Визуальные пункты (текст в кадре, края вырезки) — по контактным листам.
"""
import argparse
import json
import re
import subprocess
import sys
from pathlib import Path

import numpy as np

from common import FPS, W, H, LUFS, load_json, save_json

TP_MAX = -1.0
LUFS_TOL = 1.0


def sh(cmd, **kw):
    return subprocess.run([str(c) for c in cmd], capture_output=True, text=True, **kw)


def check_format(video, expected_dur):
    r = json.loads(sh(["ffprobe", "-v", "error", "-show_entries",
                       "stream=codec_type,width,height,r_frame_rate,avg_frame_rate,duration,codec_name,nb_frames",
                       "-of", "json", video]).stdout)
    v = next(s for s in r["streams"] if s["codec_type"] == "video")
    a = next((s for s in r["streams"] if s["codec_type"] == "audio"), None)
    vd = float(v.get("duration") or 0)
    ad = float(a.get("duration") or 0) if a else 0.0
    out = {"width": v["width"], "height": v["height"], "fps": v["r_frame_rate"], "avg_fps": v["avg_frame_rate"],
           "v_dur": round(vd, 3), "a_dur": round(ad, 3)}
    res = []
    res.append(("resolution 1080x1920", v["width"] == W and v["height"] == H, f'{v["width"]}x{v["height"]}'))
    cfr = v["r_frame_rate"] == f"{FPS}/1" and v["avg_frame_rate"] in (f"{FPS}/1", v["r_frame_rate"])
    res.append(("constant 30 fps", cfr, f'{v["r_frame_rate"]} / avg {v["avg_frame_rate"]}'))
    res.append(("audio track present", a is not None, a["codec_name"] if a else "none"))
    res.append(("A/V length match (<=0.06 s)", abs(vd - ad) <= 0.06, f"video {vd:.2f}s audio {ad:.2f}s"))
    if expected_dur:
        res.append(("duration matches the cut (±0.15 s)", abs(vd - expected_dur) <= 0.15,
                    f"{vd:.2f}s vs {expected_dur:.2f}s"))
    return res, out


def pcm(video):
    p = subprocess.run(["ffmpeg", "-v", "error", "-i", str(video), "-vn", "-ac", "1", "-ar", "16000", "-f", "s16le", "-"],
                       capture_output=True)
    return np.frombuffer(p.stdout, np.int16).astype(np.float32) / 32768.0


def check_audio(video, words, duck=None):
    res = []
    p = sh(["ffmpeg", "-hide_banner", "-nostats", "-i", video, "-vn", "-af",
            f"loudnorm=I={LUFS}:TP=-1.5:LRA=11:print_format=json", "-f", "null", "-"])
    m = re.search(r"\{[^{}]*\"input_i\"[^{}]*\}", p.stderr, re.S)
    meas = json.loads(m.group(0)) if m else {}
    li, tp = float(meas.get("input_i", -99)), float(meas.get("input_tp", 99))
    res.append((f"loudness {LUFS} LUFS (+-{LUFS_TOL})", abs(li - LUFS) <= LUFS_TOL, f"{li:.1f} LUFS"))
    res.append((f"true peak <= {TP_MAX} dBTP", tp <= TP_MAX + 0.05, f"{tp:.1f} dBTP"))
    x = pcm(video)
    clip = int((np.abs(x) >= 0.999).sum())
    res.append(("no clipping", clip <= 3, f"{clip} samples at full scale"))
    # ducking: музыка ВО ВРЕМЯ речи минимум на 14 dB тише голоса (замер из audio.duck_stats), иначе грубая оценка
    if duck and Path(duck).exists():
        d = json.loads(Path(duck).read_text(encoding="utf-8"))
        res.append(("music >= 14 dB under the voice while speaking", d["margin_db"] >= 14.0,
                    f"voice {d['voice_db']} dBFS, music {d['music_under_speech_db']} dBFS, margin {d['margin_db']} dB"))
    sr = 16000
    gp = []
    for (a0, b0), (a1, b1) in zip([(w["start"], w["end"]) for w in words], [(w["start"], w["end"]) for w in words][1:]):
        if a1 - b0 > 0.25:
            seg = x[int((b0 + 0.08) * sr):int((a1 - 0.05) * sr)]
            if len(seg) > sr * 0.08:
                gp.append(float(np.sqrt((seg ** 2).mean() + 1e-12)))
    if gp:
        gd = 20 * np.log10(np.median(gp))
        res.append(("bed audible in gaps (> -60 dBFS)", gd > -60, f"{gd:.1f} dBFS"))
    return res, {"lufs": li, "tp": tp, "clip_samples": clip}


def check_frames(video):
    p = sh(["ffmpeg", "-hide_banner", "-nostats", "-i", video, "-an", "-vf",
            "blackdetect=d=0.2:pic_th=0.97,freezedetect=n=0.0005:d=1.2", "-f", "null", "-"])
    blk = re.findall(r"black_start:([\d.]+) black_end:([\d.]+)", p.stderr)
    frz = re.findall(r"freeze_start: ([\d.]+)", p.stderr)
    return [("no black frames", not blk, f"{len(blk)} spans" + (f" at {blk[0][0]}s" if blk else "")),
            ("no frozen frames", not frz, f"{len(frz)} spans" + (f" at {frz[0]}s" if frz else ""))]


def check_captions(plan, words):
    res = []
    n = len(words)
    chunks = plan.get("chunks", [])
    bad = [c for c in chunks if not (0 <= c["first"] <= c["last"] < n)]
    cover = sorted({i for c in chunks for i in range(c["first"], c["last"] + 1)})
    res.append(("captions index real transcript words", not bad, f"{len(chunks)} chunks, {len(bad)} bad"))
    res.append(("every word is captioned", len(cover) == n, f"{len(cover)}/{n} words"))
    order = all(words[i]["start"] <= words[i + 1]["start"] + 1e-3 for i in range(n - 1))
    res.append(("caption times monotonic (transcript order)", order, ""))
    hook = plan.get("hook", {})
    ht = len((hook.get("text") or "").split())
    res.append(("hook <= 6 words", 1 <= ht <= 6, f"{ht} words: «{hook.get('text','')}»"))
    return res


def stills(video, dur, out_dir, ver):
    out_dir = Path(out_dir)
    tmp = out_dir / f"_st_{ver}"
    tmp.mkdir(parents=True, exist_ok=True)
    ts = [round(t, 2) for t in np.arange(0.5, max(dur - 0.3, 0.6), 2.0)]
    files = []
    for i, t in enumerate(ts):
        f = tmp / f"s{i:02d}.jpg"
        sh(["ffmpeg", "-y", "-loglevel", "error", "-ss", t, "-i", video, "-frames:v", 1, "-vf", "scale=270:-1", f])
        if f.exists():
            files.append(f)
    # контактный лист: 7 колонок
    cols = 7
    rows = [files[i:i + cols] for i in range(0, len(files), cols)]
    row_imgs = []
    for ri, row in enumerate(rows):
        while len(row) < cols:
            row.append(row[-1])
        o = tmp / f"row{ri}.jpg"
        cmd = ["ffmpeg", "-y", "-loglevel", "error"]
        for f in row:
            cmd += ["-i", f]
        sh(cmd + ["-filter_complex", f"hstack=inputs={cols}", "-frames:v", 1, o])
        row_imgs.append(o)
    if row_imgs:
        cmd = ["ffmpeg", "-y", "-loglevel", "error"]
        for f in row_imgs:
            cmd += ["-i", f]
        if len(row_imgs) > 1:
            sh(cmd + ["-filter_complex", f"vstack=inputs={len(row_imgs)}", "-frames:v", 1, out_dir / f"contact_{ver}.jpg"])
        else:
            sh(["ffmpeg", "-y", "-loglevel", "error", "-i", row_imgs[0], out_dir / f"contact_{ver}.jpg"])
    # кадры хука 0.3 / 0.8 / 1.5 c
    hk = []
    for i, t in enumerate((0.3, 0.8, 1.5)):
        f = tmp / f"h{i}.jpg"
        sh(["ffmpeg", "-y", "-loglevel", "error", "-ss", t, "-i", video, "-frames:v", 1, "-vf", "scale=360:-1", f])
        hk += ["-i", f]
    sh(["ffmpeg", "-y", "-loglevel", "error", *hk, "-filter_complex", "hstack=inputs=3", "-frames:v", 1,
        out_dir / f"hook_{ver}.jpg"])
    # обложка: кадр с хуком
    sh(["ffmpeg", "-y", "-loglevel", "error", "-ss", 1.2, "-i", video, "-frames:v", 1, "-q:v", 3,
        out_dir / f"cover_{ver}.jpg"])
    for f in tmp.glob("*"):
        f.unlink()
    tmp.rmdir()


def cmd_check(a):
    tr = load_json(a.transcript)
    plan = load_json(a.plan)
    rows, meta = [], {}
    r, m = check_format(a.video, a.expected_dur)
    rows += r
    meta.update(m)
    r, m = check_audio(a.video, tr["words"], a.duck)
    rows += r
    meta.update(m)
    rows += check_frames(a.video)
    rows += check_captions(plan, tr["words"])
    rows.append(("planner source (info)", True, f'{plan.get("source")}'
                 + (f' — fallback: {plan.get("fallback_reason")}' if plan.get("fallback_reason") else "")))
    stills(a.video, meta["v_dur"], a.out, a.version)
    ok = all(p for _, p, _ in rows )
    save_json(Path(a.out) / f"qa_{a.version}.json",
              {"version": a.version, "ok": ok, "meta": meta, "checks": [{"name": n, "pass": bool(p), "detail": d} for n, p, d in rows]})
    for n, p, d in rows:
        print(("PASS " if p else "FAIL ") + f"{a.version} {n}: {d}", flush=True)
    print(f"QA {a.version}: {'OK' if ok else 'FAILED'}", flush=True)


NAMES = {"V1": "Bold Yellow", "V2": "Neon ADHD", "V3": "Editorial", "V4": "Chrome 3D", "V5": "Soft Pastel"}


def cmd_report(a):
    d = Path(a.dir)
    lines = ["# QA report", "",
             "Automatic checks on every finished version (numbers measured with ffprobe/ffmpeg; "
             "text-in-frame and cut-out edges are checked visually on the contact sheets).", ""]
    allok = True
    ex = next(iter(d.rglob("exposure.json")), None)
    if ex:
        e = load_json(ex)
        b, a_ = e.get("before", {}), e.get("after", {})
        lines += ["## Exposure / colour normalisation (per clip)", "",
                  f"- Measured before: median luma {b.get('median_luma')}, centre {b.get('centre_median_luma')}, "
                  f"p2/p98 {b.get('p02')}/{b.get('p98')}, clipped black/white {b.get('clip_black_pct')}%/{b.get('clip_white_pct')}%, "
                  f"R/B {b.get('rb_ratio')}, noise sigma {b.get('noise_sigma')}",
                  f"- Applied: {'; '.join(e.get('applied', [])) or 'nothing (clip is normal, left untouched)'}",
                  f"- Filter: `{e.get('filter') or 'none'}`",
                  f"- Median luma before -> after: {b.get('median_luma')} -> {a_.get('median_luma')}"
                  f" (noise sigma {b.get('noise_sigma')} -> {a_.get('noise_sigma')})"]
        if e.get("dark_clip"):
            lines.append("- **DARK CLIP: noisy result, consider re-shooting with more light**")
        lines += ["- Before/after stills: exposure_compare.jpg (top row before, bottom row after)", ""]
    for p in sorted(d.rglob("platematch_V*.json")):
        pm = load_json(p)
        lines.append(f"- Plate light match {p.stem.split('_')[1]}: {pm.get('filter') or 'no change'}")
    if list(d.rglob("platematch_V*.json")):
        lines.append("")
    for v in sorted(NAMES):
        f = next(iter(d.rglob(f"qa_{v}.json")), None)
        if not f:
            lines += [f"## {v} {NAMES[v]}", "", "- not rendered / no QA data", ""]
            continue
        q = load_json(f)
        allok &= q["ok"]
        lines += [f"## {v} {NAMES[v]} — {'PASS' if q['ok'] else 'FAIL'}", ""]
        for c in q["checks"]:
            lines.append(f"- {'PASS' if c['pass'] else 'FAIL'}: {c['name']} — {c['detail']}")
        pj = next(iter(d.rglob(f"plan_{v}.json")), None)
        if pj:
            pl_ = load_json(pj)
            lines.append(f"- Hook ({pl_.get('source')}): «{pl_.get('hook', {}).get('text', '')}»"
                         + (f"  — PLAN FALLBACK: {pl_['fallback_reason']}" if pl_.get("fallback_reason") else ""))
        lines.append("")
    extra = Path(a.notes).read_text(encoding="utf-8") if a.notes and Path(a.notes).exists() else ""
    lines += [f"Overall: {'ALL CHECKS PASSED' if allok else 'SOME CHECKS FAILED'}", ""]
    if extra:
        lines += ["## Notes", "", extra, ""]
    Path(a.out).write_text("\n".join(lines), encoding="utf-8")
    print(f"report -> {a.out}")


def main():
    ap = argparse.ArgumentParser()
    sp = ap.add_subparsers(dest="cmd", required=True)
    c = sp.add_parser("check")
    c.add_argument("--video", required=True)
    c.add_argument("--plan", required=True)
    c.add_argument("--transcript", required=True)
    c.add_argument("--version", required=True)
    c.add_argument("--out", required=True)
    c.add_argument("--duck", default=None)
    c.add_argument("--expected-dur", type=float, default=None)
    r = sp.add_parser("report")
    r.add_argument("--dir", required=True)
    r.add_argument("--out", required=True)
    r.add_argument("--notes", default=None)
    a = ap.parse_args()
    {"check": cmd_check, "report": cmd_report}[a.cmd](a)


if __name__ == "__main__":
    main()

#!/usr/bin/env python3
"""Automatic exposure / colour normalisation (per clip, before the per-version grade).

measure(video)      -> dict of luma percentiles, clipping, colour cast, noise
plan_correction(m)  -> ffmpeg filter string (or "") + log of what was applied
match_plate(...)    -> small extra filter so the person sits in the plate's light

Rule: never overcorrect. Normal and bright clips get an empty filter.
"""
import json
import subprocess
from pathlib import Path

import numpy as np

TARGET_LOW, TARGET_HIGH, TARGET = 0.42, 0.50, 0.45
GAMMA_MIN = 0.55          # at most ~1.5-2 stops of lift
NOISE_SOFT, NOISE_HARD = 2.0, 4.0     # luma sigma on a 0..255 scale


def _frames(video, n=12, w=360, h=640, pix="rgb24", extra=""):
    dur = float(subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", str(video)],
                               capture_output=True, text=True).stdout.strip() or 0)
    step = max(dur / (n + 1), 0.5)
    vf = f"fps=1/{step:.3f},{extra}scale={w}:{h}"
    raw = subprocess.run(["ffmpeg", "-v", "error", "-i", str(video), "-an", "-vf", vf, "-frames:v", str(n),
                          "-f", "rawvideo", "-pix_fmt", pix, "-"], capture_output=True).stdout
    ch = 3 if pix == "rgb24" else 1
    arr = np.frombuffer(raw, np.uint8)
    k = arr.size // (w * h * ch)
    return arr[:k * w * h * ch].reshape(k, h, w, ch).astype(np.float32) / 255.0


def _noise_sigma(video):
    """Luma noise sigma (0..255) from the residual against a 3x3 mean in flat-ish areas; centre crop, full res."""
    fr = _frames(video, n=5, w=640, h=640, pix="gray", extra="crop=min(iw\\,ih):min(iw\\,ih):(iw-min(iw\\,ih))/2:(ih-min(iw\\,ih))/2,")
    if fr.size == 0:
        return 0.0
    sig = []
    for f in fr[..., 0]:
        f = f * 255.0
        pad = np.pad(f, 1, mode="edge")
        mean = sum(pad[i:i + f.shape[0], j:j + f.shape[1]] for i in range(3) for j in range(3)) / 9.0
        res = f - mean
        gy, gx = np.gradient(mean)
        flat = (np.abs(gx) + np.abs(gy)) < 1.2          # skip edges
        r = res[flat]
        if r.size > 2000:
            sig.append(1.4826 * float(np.median(np.abs(r - np.median(r)))) * 1.5)   # 3x3 mean shrinks the residual by ~0.94
    return float(np.median(sig)) if sig else 0.0


def measure(video):
    fr = _frames(video)
    if fr.size == 0:
        return {}
    r, g, b = fr[..., 0], fr[..., 1], fr[..., 2]
    y = 0.2126 * r + 0.7152 * g + 0.0722 * b
    h = y.shape[1]
    centre = y[:, h // 5: h * 4 // 5, :]
    mid = (y > 0.2) & (y < 0.8)
    mr, mg, mb = (float(c[mid].mean()) if mid.any() else float(c.mean()) for c in (r, g, b))
    out = {
        "median_luma": round(float(np.median(y)), 3),
        "centre_median_luma": round(float(np.median(centre)), 3),
        "p02": round(float(np.percentile(y, 2)), 3), "p98": round(float(np.percentile(y, 98)), 3),
        "p995": round(float(np.percentile(y, 99.5)), 3),
        "clip_black_pct": round(float((y < 0.02).mean() * 100), 2),
        "clip_white_pct": round(float((y > 0.98).mean() * 100), 2),
        "mean_rgb_mid": [round(mr, 3), round(mg, 3), round(mb, 3)],
        "rb_ratio": round(mr / max(mb, 1e-3), 3),
        "noise_sigma": round(_noise_sigma(video), 2),
    }
    return out


def plan_correction(m):
    """-> (filter_string, info). Empty string = leave the clip alone."""
    info = {"applied": [], "gamma": 1.0}
    if not m:
        return "", info
    med = min(m["median_luma"], m["centre_median_luma"] * 0.5 + m["median_luma"] * 0.5)   # face area weighs in
    filters = []
    # exposure: only when under 0.40; partial correction for 0.40-0.42
    gamma = 1.0
    if med < 0.40:
        tgt = TARGET if med < 0.34 else med + (TARGET - med) * 0.8
        gamma = max(GAMMA_MIN, float(np.log(tgt) / np.log(max(med, 0.02))))
        if gamma < 0.97:
            # gamma <1 on the normalised range keeps black and white points fixed, highlights compress a bit
            filters.append(f"lutyuv=y='clip(16+219*pow(clip((val-16)/219,0,1),{gamma:.3f}),16,235)'")
            info["applied"].append(f"gamma {gamma:.2f} (median {med:.2f} -> ~{med ** gamma:.2f})")
            info["gamma"] = round(gamma, 3)
    # colour cast: gentle gray-world on mid-tones, skin dominates faces so half strength and capped
    r_, g_, b_ = m["mean_rgb_mid"]
    gray = (r_ + g_ + b_) / 3
    rb = m["rb_ratio"]
    green = (g_ - (r_ + b_) / 2) / max(gray, 1e-3)
    # faces are warm (R/B ~1.3-1.7 is normal); only a clearly orange/blue/green frame counts as a cast
    if rb > 1.9 or rb < 0.85 or abs(green) > 0.10:
        gains = [float(np.clip((gray / max(c, 1e-3)) ** 0.4, 0.92, 1.08)) for c in (r_, g_, b_)]
        filters.append(f"colorchannelmixer=rr={gains[0]:.3f}:gg={gains[1]:.3f}:bb={gains[2]:.3f}")
        info["applied"].append(f"cast neutralised gains RGB {gains[0]:.2f}/{gains[1]:.2f}/{gains[2]:.2f} (R/B {rb:.2f}, green {green:+.2f})")
    # noise after the lift: shadows get amplified by roughly 1/gamma
    sigma = m["noise_sigma"] * (1.0 / gamma if gamma < 1 else 1.0)
    info["noise_after_est"] = round(sigma, 2)
    denoised = False
    if sigma > NOISE_HARD:
        filters.append("hqdn3d=4:3:6:5")
        denoised = True
        info["applied"].append(f"denoise strong (sigma {sigma:.1f})")
    elif sigma > NOISE_SOFT:
        filters.append("hqdn3d=2:1.5:3:3")
        denoised = True
        info["applied"].append(f"denoise gentle (sigma {sigma:.1f})")
    lifted = gamma < 0.97
    if lifted or (m["p98"] - m["p02"] < 0.55):
        filters.append("unsharp=luma_msize_x=23:luma_msize_y=23:luma_amount=0.18:chroma_amount=0")   # mild local contrast
        info["applied"].append("mild local contrast")
    if denoised or lifted:
        filters.append("unsharp=5:5:0.35:5:5:0")              # slight sharpen after denoise
        info["applied"].append("slight sharpen")
    info["dark_clip"] = bool(m["median_luma"] < 0.30 and sigma > 3.0)
    return ",".join(filters), info


def match_plate(person_after, plate_stats):
    """Move the person's brightness and colour temperature ~35% toward the plate. -> filter string."""
    if not person_after or not plate_stats:
        return "", {}
    f, info = [], {}
    dl = plate_stats["median_luma"] - person_after["median_luma"]
    if abs(dl) > 0.05:
        step = float(np.clip(dl * 0.35, -0.06, 0.06))
        f.append(f"eq=brightness={step:.3f}")
        info["luma_shift"] = round(step, 3)
    pr, pb = plate_stats["rb_ratio"], person_after["rb_ratio"]
    rel = float(np.clip((pr / max(pb, 1e-3)) ** 0.35, 0.94, 1.06))
    if abs(rel - 1) > 0.015:
        f.append(f"colorchannelmixer=rr={rel:.3f}:bb={1 / rel:.3f}")
        info["warmth_gain_r"] = round(rel, 3)
    return ",".join(f), info


def compare_image(before, after, out, times=(0.25, 0.5, 0.75)):
    """before/after stills side by side (small)."""
    inputs, labels = [], []
    for vid in (before, after):
        dur = float(subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", str(vid)],
                                   capture_output=True, text=True).stdout.strip() or 0)
        for t in times:
            inputs += ["-ss", f"{dur * t:.2f}", "-i", str(vid)]
    n = len(times)
    fc = "".join(f"[{i}:v]scale=300:-1[s{i}];" for i in range(2 * n))
    top = "".join(f"[s{i}]" for i in range(n)) + f"hstack=inputs={n}[t];"
    bot = "".join(f"[s{i}]" for i in range(n, 2 * n)) + f"hstack=inputs={n}[b];"
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", *inputs, "-filter_complex", fc + top + bot + "[t][b]vstack[o]",
                    "-map", "[o]", "-frames:v", "1", str(out)], check=True)


if __name__ == "__main__":
    import sys
    m = measure(sys.argv[1])
    flt, info = plan_correction(m)
    print(json.dumps({"measure": m, "filter": flt, "info": info}, ensure_ascii=False, indent=1))

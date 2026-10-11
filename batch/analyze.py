#!/usr/bin/env python3
"""Clip analysis for the batch machine: probe, speech words (faster-whisper), real cuts of the footage, face track.
usage: analyze.py SOURCE.mp4 OUT_DIR [--model large-v3] [--max-dur 180]  ->  OUT_DIR/analysis.json"""
import argparse, json, re, subprocess, sys, time
from pathlib import Path

ap = argparse.ArgumentParser()
ap.add_argument('src')
ap.add_argument('out')
ap.add_argument('--model', default='large-v3')
ap.add_argument('--max-dur', type=float, default=180.0)
ap.add_argument('--lang', default='ru')
a = ap.parse_args()
out = Path(a.out)
out.mkdir(parents=True, exist_ok=True)
T0 = time.time()
timings = {}


def sh(cmd, **kw):
    return subprocess.run(cmd, capture_output=True, text=True, **kw)


def tick(name, t):
    timings[name] = round(time.time() - t, 1)
    print(f'[analyze] {name}: {timings[name]} s', flush=True)


# ---------------- probe
t = time.time()
pr = sh(['ffprobe', '-v', 'error', '-show_entries', 'stream=codec_type,width,height,r_frame_rate:stream_tags=rotate:stream_side_data=rotation:format=duration', '-of', 'json', a.src])
info = json.loads(pr.stdout or '{}')
vs = next((s for s in info.get('streams', []) if s.get('codec_type') == 'video'), None)
if not vs:
    sys.exit('no video stream')
has_audio = any(s.get('codec_type') == 'audio' for s in info.get('streams', []))
dur = float(info['format']['duration'])
w, h = int(vs['width']), int(vs['height'])
rot = 0
for sd in vs.get('side_data_list', []) or []:
    rot = int(sd.get('rotation', 0))
rot = rot or int((vs.get('tags') or {}).get('rotate', 0) or 0)
if abs(rot) in (90, 270):
    w, h = h, w                                   # ffmpeg autorotates: effective size is swapped
if dur > a.max_dur:
    sys.exit(f'clip too long: {dur:.0f} s > {a.max_dur:.0f} s')
if not has_audio:
    sys.exit('clip has no audio track')
tick('probe', t)

# ---------------- speech
t = time.time()
wav = out / 'speech.wav'
sh(['ffmpeg', '-y', '-loglevel', 'error', '-i', a.src, '-vn', '-ac', '1', '-ar', '16000', str(wav)])
from faster_whisper import WhisperModel
model = WhisperModel(a.model, device='cpu', compute_type='int8', cpu_threads=4)
segs, ginfo = model.transcribe(str(wav), language=a.lang, word_timestamps=True, vad_filter=False, beam_size=5,
                               condition_on_previous_text=False)
words = []
for s in segs:
    for ww in (s.words or []):
        tx = ww.word.strip()
        if tx:
            words.append({'w': tx, 's': round(float(ww.start), 2), 'e': round(max(float(ww.end), float(ww.start) + 0.08), 2)})
for i in range(len(words) - 1):                        # no overlaps
    if words[i]['e'] > words[i + 1]['s']:
        words[i]['e'] = round(max(words[i]['s'] + 0.08, words[i + 1]['s'] - 0.01), 2)
tick('whisper', t)

# ---------------- real cuts of the footage
t = time.time()
r = sh(['ffmpeg', '-hide_banner', '-i', a.src, '-an', '-vf', "scale=320:-2,select='gt(scene,0.22)',showinfo", '-f', 'null', '-'])
cuts = []
for m in re.finditer(r'pts_time:([\d.]+)', r.stderr):
    c = float(m.group(1))
    if 0.4 < c < dur - 0.4 and (not cuts or c - cuts[-1] > 0.5):
        cuts.append(round(c, 2))
tick('cuts', t)

# ---------------- face track (every 0.2 s)
t = time.time()
import cv2, os
CD = (os.environ.get('CASCADE_DIR') or cv2.data.haarcascades).rstrip('/' + chr(92)) + '/'
cap = cv2.VideoCapture(a.src)
fps = cap.get(cv2.CAP_PROP_FPS) or 30
fr = cv2.CascadeClassifier(CD + 'haarcascade_frontalface_default.xml')
pf = cv2.CascadeClassifier(CD + 'haarcascade_profileface.xml')
face, i, step = [], 0, int(round(fps * 0.2)) or 1
USE_FACE = not fr.empty()
if not USE_FACE:
    print('[analyze] WARNING: haar cascade not loadable, no face track (camera stays centred)', flush=True)
while True:
    ok, f = cap.read()
    if not ok:
        break
    if i % step == 0:
        H, W = f.shape[:2]
        sz = (360, 640) if H >= W else (640, 360)
        g = cv2.equalizeHist(cv2.cvtColor(cv2.resize(f, sz), cv2.COLOR_BGR2GRAY))
        best = None
        for c, flip in (((fr, False), (pf, False), (pf, True)) if USE_FACE else ()):
            gg = cv2.flip(g, 1) if flip else g
            for (x, y, ww, hh) in c.detectMultiScale(gg, 1.1, 5, minSize=(60, 60)):
                if flip:
                    x = sz[0] - x - ww
                if best is None or ww * hh > best[2] * best[3]:
                    best = (x, y, ww, hh)
            if best is not None and not flip and c is fr:
                break
        face.append({'t': round(i / fps, 2), 'f': None if best is None else [round((best[0] + best[2] / 2) / sz[0], 3), round((best[1] + best[3] / 2) / sz[1], 3), round(best[2] / sz[0], 3)]})
    i += 1
cap.release()
tick('face', t)

res = {'dur': round(dur, 3), 'w': w, 'h': h, 'fps': round(fps, 2), 'landscape': w > h, 'words': words, 'cuts': cuts, 'face': face,
       'lang_prob': round(float(getattr(ginfo, 'language_probability', 0) or 0), 2), 'timings': timings}
(out / 'analysis.json').write_text(json.dumps(res, ensure_ascii=False), encoding='utf-8')
wav.unlink(missing_ok=True)
print(f"[analyze] done in {time.time() - T0:.0f} s: dur={dur:.1f}s {w}x{h} words={len(words)} cuts={len(cuts)} face={sum(1 for x in face if x['f'])}/{len(face)}")

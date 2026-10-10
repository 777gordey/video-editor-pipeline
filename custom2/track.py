#!/usr/bin/env python3
"""Face track of the clip (every 0.2 s), normalised coords. usage: track.py clip.mp4 out.json"""
import cv2, json, sys, os
CD = os.environ.get('CASCADE_DIR', cv2.data.haarcascades) + '/'
cap = cv2.VideoCapture(sys.argv[1]); fps = cap.get(cv2.CAP_PROP_FPS) or 30
fr = cv2.CascadeClassifier(CD + 'haarcascade_frontalface_default.xml')
pr = cv2.CascadeClassifier(CD + 'haarcascade_profileface.xml')
out = []; i = 0; step = int(round(fps * 0.2))
while True:
    ok, f = cap.read()
    if not ok: break
    if i % step == 0:
        g = cv2.cvtColor(cv2.resize(f, (360, 640)), cv2.COLOR_BGR2GRAY); g = cv2.equalizeHist(g)
        best = None
        for c, flip in ((fr, False), (pr, False), (pr, True)):
            gg = cv2.flip(g, 1) if flip else g
            r = c.detectMultiScale(gg, 1.1, 5, minSize=(60, 60))
            for (x, y, w, h) in r:
                if flip: x = 360 - x - w
                if best is None or w * h > best[2] * best[3]: best = (x, y, w, h)
            if best is not None and not flip and c is fr: break
        out.append({'t': round(i / fps, 2), 'f': None if best is None else [round((best[0] + best[2] / 2) / 360, 3), round((best[1] + best[3] / 2) / 640, 3), round(best[2] / 360, 3)]})
    i += 1
json.dump(out, open(sys.argv[2], 'w'))
print(len(out), sum(1 for o in out if o['f']), 'detected')

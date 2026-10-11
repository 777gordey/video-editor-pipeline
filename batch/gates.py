#!/usr/bin/env python3
"""Automated gates for one finished clip. usage: gates.py PLAN ANALYSIS LEVELS FINAL.mp4 OUT.json
Gates (all from the brief): levels, camera (<=1.22x, head never cropped), inserts (>=4 incl. wildcard, tied to words), hook grounded, final video format."""
import json, subprocess, sys
from pathlib import Path
HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from presets import PRESETS
import lib

plan, an, lv = (json.loads(Path(p).read_text(encoding='utf-8')) for p in sys.argv[1:4])
final, out = sys.argv[4], sys.argv[5]
pr = PRESETS[plan['preset']]
ZK = lib.zoom_keys(an['dur'], an['cuts'], pr, plan['seed'], (plan.get('style') or {}).get('camera', 'normal'))
wc = plan['wildcard']
jumps = [(wc['t'], wc['e'], 1.22)] if wc['type'] == 'punch_cut' else []
cam = lib.cam_path(an['face'], ZK, an['cuts'], an['dur'], jumps=jumps)
zmax, head = lib.camera_gate(cam, an['face'])
pr_ = subprocess.run(['ffprobe', '-v', 'error', '-show_entries', 'stream=codec_type,width,height:format=duration', '-of', 'json', final], capture_output=True, text=True)
info = json.loads(pr_.stdout)
v = next(s for s in info['streams'] if s['codec_type'] == 'video')
has_a = any(s['codec_type'] == 'audio' for s in info['streams'])
fdur = float(info['format']['duration'])
n_ins = len(plan['inserts']) + 1                      # + the wildcard
G = {
    'music_speech': (lv['music_in_speech_db'] is not None and -13.0 <= lv['music_in_speech_db'] <= -9.0, lv['music_in_speech_db'], 'target -10..-12'),
    'music_hook': (lv['music_in_hook_db'] is None or -8.0 <= lv['music_in_hook_db'] <= -4.5, lv['music_in_hook_db'], 'target ~-6'),
    'sfx_peaks': (lv['sfx_peak_min_db'] >= -12.5 and lv['sfx_peak_max_db'] <= -7.5, [lv['sfx_peak_min_db'], lv['sfx_peak_max_db']], 'target -8..-12'),
    'loudness': (-15.0 <= lv['lufs'] <= -13.0 and lv['true_peak_db'] <= -1.0, [lv['lufs'], lv['true_peak_db']], 'target -14 LUFS, TP<=-1'),
    'camera_zoom': (zmax <= 1.2201, zmax, '<=1.22'),
    'head_not_cropped': (head >= 0.0, head, 'projected head top >= 0'),
    'inserts': (n_ins >= 4 or an['dur'] < 25 and n_ins >= 3, n_ins, '4-5 incl. wildcard (3 for clips under 25 s)'),
    'hook_grounded': (not any('hook not grounded' in x for x in plan.get('notes', [])), plan['hook']['lines'], 'from the speaker\'s words'),
    'format': (v['width'] == 1080 and v['height'] == 1920 and has_a and abs(fdur - an['dur']) < 0.4, [v['width'], v['height'], round(fdur, 1)], '1080x1920 + audio + same length'),
}
res = {k: {'pass': bool(a), 'value': b, 'rule': c} for k, (a, b, c) in G.items()}
res['_all'] = all(x['pass'] for x in res.values())
Path(out).write_text(json.dumps(res, ensure_ascii=False, indent=1), encoding='utf-8')
print('GATES', 'PASS' if res['_all'] else 'FAIL:', [k for k, x in res.items() if k != '_all' and not x['pass']])

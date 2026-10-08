"""Сборка проекта HyperFrames (index.html + локальные ассеты) из plan.json и слоёв видео."""
import json
import re
import shutil
from pathlib import Path

from common import ENGINE_DIR, W, H, FPS

STATIC = ENGINE_DIR / "static"
FAMILY = {"montserrat": "Montserrat", "playfair-display": "Playfair Display", "nunito": "Nunito",
          "russo-one": "Russo One", "unbounded": "Unbounded", "pt-serif": "PT Serif"}
RANGE = {
    "cyrillic": "U+0301,U+0400-045F,U+0490-0491,U+04B0-04B1,U+2116",
    "latin": "U+0000-00FF,U+0131,U+0152-0153,U+02BB-02BC,U+02C6,U+02DA,U+02DC,U+2000-206F,U+2074,U+20AC,U+2122,U+2191,U+2193,U+2212,U+2215,U+FEFF,U+FFFD",
}
FALLBACK_BG = {
    "V1": "#111",
    "V2": "radial-gradient(ellipse at 30% 20%,#5b1a8a 0%,#1a0a3a 55%,#07030f 100%)",
    "V3": "linear-gradient(180deg,#27402a 0%,#122216 60%,#0a140c 100%)",
    "V4": "radial-gradient(ellipse at 50% 32%,#22335a 0%,#0b1226 52%,#02040a 100%)",
    "V5": "linear-gradient(160deg,#ffd9e2 0%,#ffe9d6 55%,#e4f1ff 100%)",
}


def font_faces():
    out = []
    for f in sorted((STATIC / "fonts").glob("*.woff2")):
        m = re.match(r"(.+)-(cyrillic|latin)-(\d+)-normal\.woff2", f.name)
        if not m:
            continue
        fam = FAMILY[m.group(1)]
        out.append(f"@font-face{{font-family:'{fam}';font-weight:{m.group(3)};font-style:normal;"
                   f"src:url('fonts/{f.name}') format('woff2');unicode-range:{RANGE[m.group(2)]};font-display:block}}")
    return "\n".join(out)


STYLE_CSS = {
    "V1": """
.chunk{font-weight:900;-webkit-text-stroke:12px #000;paint-order:stroke fill;text-shadow:0 10px 0 rgba(0,0,0,.55)}
.w.emph{font-size:1.28em}
#hook.slam{flex-direction:column;align-items:center;top:210px}
#hook.slam .hw{font-size:1em;line-height:1.02;color:#fff;-webkit-text-stroke:14px #000;paint-order:stroke fill;text-shadow:0 12px 0 rgba(0,0,0,.6)}
""",
    "V2": """
.chunk{font-weight:900;text-shadow:0 0 14px var(--accent),0 0 34px var(--accent),0 6px 0 rgba(0,0,0,.5);-webkit-text-stroke:3px #1a0033;paint-order:stroke fill}
#hook.glitch .hw{font-size:1em;color:#fff;text-shadow:5px 0 #ff2bd6,-5px 0 #00f5ff,0 0 38px #ff2bd6}
""",
    "V3": """
.chunk{font-weight:700;text-shadow:0 3px 18px rgba(0,0,0,.65),0 1px 0 rgba(0,0,0,.4);letter-spacing:.005em}
#hook.editorial .hw{font-size:1em;font-weight:700;color:#F6EEDF;text-shadow:0 4px 30px rgba(0,0,0,.6)}
#hook.editorial{flex-direction:column;align-items:center;top:300px}
#hookrule{position:absolute;left:310px;top:640px;height:5px;width:0;background:var(--accent)}
""",
    "V4": """
.chunk{text-shadow:0 0 22px rgba(77,163,255,.7),0 6px 0 rgba(0,0,0,.6);-webkit-text-stroke:5px #05070D;paint-order:stroke fill;letter-spacing:.02em}
#hook.chrome3d{top:230px}
#hook.chrome3d .hw{position:relative;font-size:1em;color:#56627a;line-height:1.05;margin:0 14px}
#hook.chrome3d .hw::after{content:attr(data-t);position:absolute;left:0;top:0;background:linear-gradient(180deg,#fff 0%,#cfd8e8 38%,#6c7b95 50%,#eef3fb 66%,#8795ae 100%);-webkit-background-clip:text;background-clip:text;-webkit-text-fill-color:transparent}
""",
    "V5": """
.chunk{background:rgba(255,255,255,.9);border-radius:64px;padding:22px 46px;box-shadow:0 14px 44px rgba(255,111,145,.35);font-weight:900;-webkit-text-stroke:0}
#hook.pastel .hw{font-family:'Nunito';font-weight:900;font-size:1em;color:#4B3A5A;background:#fff;border-radius:64px;padding:6px 40px;margin:10px;box-shadow:0 14px 44px rgba(255,111,145,.4)}
""",
}


def build_project(proj: Path, style: dict, plan: dict, tr: dict, layers: dict):
    """layers: person (graded mp4, без звука) | inv+black (матирование), plate (опц.). Пути — файлы в proj/media."""
    proj.mkdir(parents=True, exist_ok=True)
    (proj / "fonts").mkdir(exist_ok=True)
    (proj / "media").mkdir(exist_ok=True)
    for f in (STATIC / "fonts").glob("*.woff2"):
        shutil.copy2(f, proj / "fonts" / f.name)
    shutil.copy2(STATIC / "gsap.min.js", proj / "gsap.min.js")
    shutil.copy2(STATIC / "runtime.js", proj / "runtime.js")
    (proj / "meta.json").write_text(json.dumps({"id": f"reel-{style['id'].lower()}", "name": style["name"]}), encoding="utf-8")

    dur = float(tr["duration"])
    vid = lambda i, f, extra="": (f'<video id="{i}" class="clip layer" src="media/{f}" muted playsinline '
                                  f'data-start="0" data-duration="{dur:.3f}" data-track-index="{0}" {extra}></video>')
    scene = []
    bgcss = FALLBACK_BG[style["id"]]
    if layers.get("plate"):
        scene.append(vid("plate", layers["plate"]))
    elif style["bg"] != "room":
        scene.append(f'<div class="layer" style="background:{bgcss}"></div>')
    if style.get("globe_behind") and layers.get("inv"):
        scene.append('<canvas id="globeBehind" class="layer" style="left:40px;top:330px;width:1000px;height:1000px"></canvas>')
    elif style.get("globe_behind"):
        scene.append('<canvas id="globeBehind" class="layer" style="left:560px;top:1050px;width:520px;height:520px;opacity:.9"></canvas>')
    if layers.get("inv"):
        scene.append(vid("inv", layers["inv"]))
        scene.append(vid("pb", layers["black"]))
    else:
        scene.append(vid("person", layers["person"]))

    data = {"dur": dur, "style": style, "plan": plan, "words": tr["words"]}
    html = f"""<!doctype html>
<html lang="ru"><head><meta charset="utf-8"><meta name="viewport" content="width={W}, height={H}">
<script src="gsap.min.js"></script>
<style>
{font_faces()}
:root{{--accent:{style['colors']['accent']};--emph:{style['colors']['emph']};--text:{style['colors']['text']}}}
*{{margin:0;padding:0;box-sizing:border-box}}
html,body{{width:{W}px;height:{H}px;overflow:hidden;background:#000}}
#root{{position:absolute;left:0;top:0;width:{W}px;height:{H}px;overflow:hidden;background:#000;font-family:'{style['font']}',sans-serif}}
.layer{{position:absolute;left:0;top:0;width:{W}px;height:{H}px}}
video.layer{{object-fit:cover}}
#cam,#snap,#scene{{position:absolute;left:0;top:0;width:{W}px;height:{H}px;transform-origin:50% 38%}}
#scene{{isolation:isolate;overflow:hidden}}
#inv{{mix-blend-mode:multiply}} #pb{{mix-blend-mode:screen}}
#captions{{position:absolute;left:60px;top:1170px;width:960px;height:420px}}
.chunk{{position:absolute;left:0;top:50%;width:100%;transform:translateY(-50%);opacity:0;text-align:center;
  font-family:'{style['font']}',sans-serif;font-weight:{style['font_weight']};font-size:{style['cap_size']}px;line-height:1.08;
  color:var(--text);{'text-transform:uppercase;' if style['caps'] else ''}word-spacing:.05em}}
.chunk .w{{display:inline-block;opacity:0;margin:0 .1em}}
#hook{{position:absolute;left:60px;top:250px;width:960px;display:flex;flex-wrap:wrap;justify-content:center;align-items:center;gap:0 20px;
  text-align:center;font-family:'{style['font']}',sans-serif;font-weight:{style['font_weight']}}}
#hook .hw{{display:inline-block;opacity:0;line-height:1.1}}
#graphics .g{{position:absolute;opacity:0}}
.g.icon{{width:230px;height:230px;border-radius:50%;display:flex;align-items:center;justify-content:center;background:var(--accent);box-shadow:0 12px 40px rgba(0,0,0,.45)}}
.g.icon svg{{fill:none;stroke:#fff;stroke-width:6;stroke-linecap:round;stroke-linejoin:round}}
.g.circ{{width:230px;display:flex;flex-direction:column;align-items:center}}
.g.circ .num{{width:210px;height:210px;border-radius:50%;border:12px solid var(--emph);background:rgba(8,10,20,.78);color:#fff;
  font-size:130px;font-weight:900;display:flex;align-items:center;justify-content:center;box-shadow:0 12px 40px rgba(0,0,0,.5)}}
.g.circ .lbl{{margin-top:14px;font-size:44px;font-weight:900;color:#fff;text-shadow:0 4px 14px rgba(0,0,0,.8);text-align:center;width:420px}}
.g.globe{{width:500px;height:500px}}
#flash{{position:absolute;left:0;top:0;width:{W}px;height:{H}px;background:#fff;opacity:0}}
#vignette{{position:absolute;left:0;top:0;width:{W}px;height:{H}px;background:radial-gradient(ellipse at 50% 45%,rgba(0,0,0,0) 52%,rgba(0,0,0,.5) 100%)}}
{STYLE_CSS[style['id']]}
</style></head>
<body>
<div id="root" data-composition-id="main" data-start="0" data-duration="{dur:.3f}" data-width="{W}" data-height="{H}">
  <div id="cam"><div id="snap"><div id="scene">
    {''.join(scene)}
  </div></div></div>
  <div id="vignette"></div>
  <div id="graphics"></div>
  <div id="captions"></div>
  <div id="hook"></div><div id="hookrule"></div>
  <div id="flash"></div>
</div>
<script>window.PLAN_DATA = {json.dumps(data, ensure_ascii=False)};</script>
<script>RUNTIME_JS</script>
</body></html>"""
    # data-t для объёмного (chrome3d) текста хука
    rt = (STATIC / "runtime.js").read_text(encoding="utf-8")
    tail = 'document.querySelectorAll("#hook .hw").forEach(e=>e.setAttribute("data-t",e.textContent));'
    html = html.replace("RUNTIME_JS", rt + chr(10) + tail)
    (proj / "index.html").write_text(html, encoding="utf-8")

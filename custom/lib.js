/* lib.js — core helpers for the hand-built composition (no frameworks; GSAP timeline only). */
const P = window.PLAN, OFF = P.off, DUR = P.dur, gs = window.gsap;
const tl = gs.timeline({ paused: true });
const T = t => Math.max(0, t - OFF);
const here = (a, b) => b > OFF + 0.001 && a < OFF + DUR - 0.001;
const $ = id => document.getElementById(id);
const rnd = (() => { let s = 20261010; return () => (s = (s * 1664525 + 1013904223) % 4294967296) / 4294967296; })();
const SNAP = $('snap'), CAM = $('cam'), FLASH = $('flash'), FX = $('fx');

function mk(cls, css, parent, html, tag) {
  const e = document.createElement(tag || 'div');
  if (cls) e.className = cls;
  if (css) e.style.cssText = (/(^|;)\s*(left|top|inset|right|bottom)\s*:/.test(css) && !/position\s*:/.test(css) ? 'position:absolute;' : '') + css;
  if (html != null) e.innerHTML = html;
  (parent || $('front')).appendChild(e);
  return e;
}
/* object lives from a to b (global seconds) */
function life(n, a, b) {
  n.classList.add('o');
  gs.set(n, { autoAlpha: 0 });
  tl.set(n, { autoAlpha: 1 }, T(a));
  tl.set(n, { autoAlpha: 0 }, T(b));
  return n;
}
const act = (spans, t) => spans.some(([a, b]) => t >= a && t <= b);
const AI = [[4.4, 9.2], [16.3, 22.4], [27.7, 30.9], [35.3, 40.5], [48.0, 52.4], [55.3, 57.9]];
const USER = [[9.5, 14.3], [23.3, 26.1], [31.4, 33.7], [41.7, 45.8], [52.4, 53.1]];

/* ---------- 3D extruded kinetic text ---------- */
function x3(text, o) {
  const box = mk('x3d ' + (o.cls || ''), `left:${o.x}px;top:${o.y}px;font-size:${o.size}px;letter-spacing:${o.ls || 0}px;transform:translate(-50%,-50%) ${o.tf || ''}`, o.parent);
  const chs = [];
  const dark = o.cls && o.cls.includes('gold') ? [92, 52, 8] : o.cls && o.cls.includes('mint') ? [6, 70, 66] : o.cls && o.cls.includes('coral') ? [90, 14, 32] : [14, 44, 70];
  for (const c of text) {
    const ch = mk('ch', '', box, '', 'span');
    mk('sp', '', ch, c === ' ' ? '&nbsp;&nbsp;' : c, 'span');
    for (let i = o.depth; i >= 1; i--) {
      const k = i / o.depth, m = 0.35 + 0.65 * (1 - k);
      const l = mk('l', `transform:translate(${i * (o.dx || 1.2)}px,${i * (o.dy || 1.6)}px);color:rgb(${dark.map(v => Math.round(v * m)).join(',')})`, ch, c, 'span');
    }
    mk('f', '', ch, c, 'span');
    mk('shine', '', ch, c, 'span');
    chs.push(ch);
  }
  box._chs = chs;
  return box;
}
function x3in(box, t, o = {}) {
  box._chs.forEach((ch, i) => {
    tl.fromTo(ch, { y: o.y0 ?? 140, rotationX: o.rx ?? -80, scale: o.s0 ?? 0.5, opacity: 0, transformPerspective: 900 },
      { y: 0, rotationX: 0, scale: 1, opacity: 1, duration: o.d || 0.55, ease: o.ease || 'back.out(1.9)' }, T(t) + i * (o.st ?? 0.05));
  });
}
function x3out(box, t, o = {}) {
  box._chs.forEach((ch, i) => {
    const n = box._chs.length, dir = o.dir ?? (i - n / 2) / (n / 2);
    tl.to(ch, { y: o.y1 ?? -260, x: dir * 200, rotationX: 60, scale: 0.6, opacity: 0, duration: o.d || 0.34, ease: 'power3.in' }, T(t) + i * 0.02);
  });
}
function x3shine(box, t) {
  box._chs.forEach((ch, i) => {
    tl.fromTo(ch.querySelector('.shine'), { backgroundPosition: '130% 0' }, { backgroundPosition: '-30% 0', duration: 0.7, ease: 'power2.inOut' }, T(t) + i * 0.06);
  });
}
function x3float(box, t0, t1, amp = 12) {
  const n = Math.max(1, Math.round((t1 - t0) / 1.2));
  tl.to(box, { y: `+=${amp}`, duration: (t1 - t0) / n / 2, ease: 'sine.inOut', repeat: n * 2 - 1, yoyo: true }, T(t0));
}

/* ---------- speech-driven equaliser bars ---------- */
function eq(parent, n, o) { // o:{x,y,w,h,gap,color,t0,t1,spans,rad}
  const wrap = mk('', `left:${o.x}px;top:${o.y}px;width:${n * (o.w + o.gap)}px;height:${o.h}px;display:flex;gap:${o.gap}px;align-items:center;justify-content:center;transform:translate(-50%,-50%)`, parent);
  const bars = [];
  for (let i = 0; i < n; i++) {
    const b = mk('', `width:${o.w}px;height:${o.h}px;border-radius:${o.w}px;background:${o.color};transform-origin:50% 50%;transform:scaleY(.12)`, wrap);
    bars.push(b);
  }
  for (let t = o.t0; t < o.t1; t += 0.11) {
    const on = act(o.spans, t) ? 1 : 0;
    bars.forEach((b, i) => {
      const v = on ? 0.18 + 0.82 * Math.abs(Math.sin(t * 9 + i * 1.7) * 0.6 + rnd() * 0.5) : 0.1 + 0.04 * Math.sin(t * 3 + i);
      tl.to(b, { scaleY: Math.min(1, v), duration: 0.11, ease: 'sine.inOut' }, T(t));
    });
  }
  return wrap;
}

/* ---------- transitions ---------- */
function flash(t, d = 0.38, peak = 0.9) {
  tl.set(FLASH, { opacity: peak, visibility: 'visible' }, T(t));
  tl.to(FLASH, { opacity: 0, duration: d, ease: 'power2.out' }, T(t));
  tl.set(FLASH, { visibility: 'hidden' }, T(t) + d + 0.01);
}
function whip(t, dir = 1) {
  tl.fromTo(SNAP, { x: 0, filter: 'blur(0px)' }, { x: -dir * 520, filter: 'blur(26px)', duration: 0.16, ease: 'power3.in', immediateRender: false }, Math.max(0, T(t) - 0.16));
  tl.fromTo(SNAP, { x: dir * 520, filter: 'blur(26px)' }, { x: 0, filter: 'blur(0px)', duration: 0.34, ease: 'power4.out', immediateRender: false }, T(t));
  streaks(t - 0.1, dir);
}
function streaks(t, dir) {
  for (let i = 0; i < 7; i++) {
    const s = mk('', `left:-200px;top:${150 + i * 250 + rnd() * 80}px;width:${600 + rnd() * 500}px;height:${3 + rnd() * 6}px;background:linear-gradient(90deg,transparent,rgba(255,255,255,.9),transparent);opacity:0`, FX);
    tl.fromTo(s, { x: dir > 0 ? 1300 : -300, opacity: 0.9 }, { x: dir > 0 ? -900 : 1500, opacity: 0, duration: 0.3, ease: 'power2.out', immediateRender: false }, T(t) + i * 0.012);
  }
}
function zoomThrough(t) {
  tl.fromTo(SNAP, { scale: 1, filter: 'blur(0px)' }, { scale: 1.7, filter: 'blur(16px)', duration: 0.2, ease: 'power3.in', immediateRender: false }, Math.max(0, T(t) - 0.2));
  tl.fromTo(SNAP, { scale: 0.62, filter: 'blur(16px)' }, { scale: 1, filter: 'blur(0px)', duration: 0.42, ease: 'power3.out', immediateRender: false }, T(t));
  flash(t - 0.04, 0.3, 0.55);
}
function wipe(t, color = '#3CF0C8') {
  const b = mk('', `left:-300px;top:-200px;width:520px;height:2400px;background:linear-gradient(90deg,${color},#fff 70%,${color});transform:skewX(-14deg);opacity:0;box-shadow:0 0 120px ${color}`, FX);
  tl.fromTo(b, { x: -400, opacity: 1 }, { x: 2100, opacity: 1, duration: 0.5, ease: 'power3.inOut', immediateRender: false }, T(t) - 0.2);
  tl.set(b, { opacity: 0 }, T(t) + 0.32);
}
function iris(t, color = '#3CF0C8') {
  const r = mk('', `left:50%;top:48%;width:200px;height:200px;margin:-100px 0 0 -100px;border-radius:50%;border:44px solid ${color};box-shadow:0 0 90px ${color};opacity:0`, FX);
  tl.fromTo(r, { scale: 0.2, opacity: 1 }, { scale: 14, opacity: 0.9, duration: 0.55, ease: 'power3.in', immediateRender: false }, T(t) - 0.28);
  tl.set(r, { opacity: 0 }, T(t) + 0.3);
  flash(t, 0.4, 0.6);
}
function glitch(t) {
  const cols = ['#3CF0C8', '#FF5A6A', '#ffffff', '#3CF0C8', '#7aa6ff', '#ffffff', '#FF5A6A', '#3CF0C8'];
  for (let i = 0; i < 8; i++) {
    const s = mk('', `left:0;top:${i * 240}px;width:1080px;height:${120 + rnd() * 120}px;background:${cols[i]};opacity:0;mix-blend-mode:screen`, FX);
    const a = T(t) - 0.12 + i * 0.015;
    tl.fromTo(s, { x: (rnd() - 0.5) * 900, opacity: 0.9 }, { x: (rnd() - 0.5) * 1400, opacity: 0, duration: 0.26, ease: 'steps(4)', immediateRender: false }, a);
  }
  tl.fromTo(SNAP, { x: -34, filter: 'blur(3px) saturate(1.6)' }, { x: 0, filter: 'blur(0px) saturate(1)', duration: 0.3, ease: 'steps(5)', immediateRender: false }, Math.max(0, T(t) - 0.1));
}

/* ---------- camera plan: [t0,t1,scale0,scale1,x,y] ---------- */
function camera(keys) {
  keys.forEach(([a, b, s0, s1, x = 0, y = 0]) => {
    if (!here(a, b)) return;
    tl.set(CAM, { scale: s0, x, y }, T(a));
    tl.to(CAM, { scale: s1, x: x * 0.7, y: y * 0.7, duration: Math.max(0.05, T(b) - T(a)), ease: 'sine.inOut' }, T(a));
  });
}
function punch(t, s = 1.12) {
  tl.fromTo(SNAP, { scale: s }, { scale: 1, duration: 0.42, ease: 'power3.out', immediateRender: false }, T(t));
}

/* ---------- captions ---------- */
function captions() {
  const W = P.words, box = $('caps'), chunks = [];
  let cur = [];
  const flush = () => { if (cur.length) { chunks.push(cur); cur = []; } };
  W.forEach((w, i) => {
    if (cur.length && w.s - cur[cur.length - 1].e > 0.55) flush();
    cur.push(w);
    const txt = cur.map(x => x.t).join(' ');
    const end = /[.?!]$/.test(w.raw) || (/,$/.test(w.raw) && cur.length >= 2) || cur.length >= 3 || txt.length > 17;
    if (end) flush();
  });
  flush();
  chunks.forEach((c, ci) => {
    const s = c[0].s, nxt = chunks[ci + 1], e = Math.min(c[c.length - 1].e + 0.25, nxt ? nxt[0].s : 1e9);
    if (!here(s, e)) return;
    const el = mk('cap', '', box, c.map(w => `<span class="w${w.k ? ' k' + (w.k === 2 ? ' red' : '') : ''}">${w.t}</span>`).join(' '));
    tl.set(el, { autoAlpha: 1 }, T(s) - 0.001);
    tl.set(el, { autoAlpha: 0 }, T(e));
    el.querySelectorAll('.w').forEach((sp, i) => {
      tl.fromTo(sp, { opacity: 0, y: 26, scale: 0.8 }, { opacity: 1, y: 0, scale: c[i].k ? 1.06 : 1, duration: 0.18, ease: 'back.out(2.6)' }, T(c[i].s));
    });
  });
}

/* ---------- ambient background ---------- */
function ambient(tints) {
  const bg = $('bgLayer');
  const blobs = [mk('blob', 'left:-200px;top:200px;width:800px;height:800px', bg), mk('blob', 'left:560px;top:900px;width:900px;height:900px;opacity:.4', bg), mk('blob', 'left:100px;top:1300px;width:700px;height:700px;opacity:.35', bg)];
  blobs.forEach((b, i) => {
    tl.fromTo(b, { x: 0, y: 0 }, { x: i % 2 ? -140 : 160, y: i === 1 ? -200 : 140, duration: DUR, ease: 'sine.inOut' }, 0);
  });
  tints.forEach(([t, c0, c1, c2]) => {
    if (t > OFF + DUR) return;
    const at = T(t);
    tl.to(blobs[0], { color: c0, duration: 0.7, ease: 'sine.inOut' }, at);
    tl.to(blobs[1], { color: c1, duration: 0.7, ease: 'sine.inOut' }, at);
    tl.to(blobs[2], { color: c2, duration: 0.7, ease: 'sine.inOut' }, at);
  });
  [[ -200, 22, 0.16 ], [ 640, -18, 0.12 ]].forEach(([x, rot, o], i) => {
    const bm = mk('', `left:${x}px;top:-200px;width:300px;height:2400px;transform:rotate(${rot}deg);background:linear-gradient(90deg,transparent,rgba(190,255,245,${o}),transparent);filter:blur(34px);mix-blend-mode:screen`, bg);
    tl.fromTo(bm, { x: 0 }, { x: i ? -260 : 300, duration: DUR, ease: 'sine.inOut' }, 0);
  });
  const floor = $('floor');
  tl.fromTo(floor, { backgroundPosition: '0px 0px' }, { backgroundPosition: '0px 700px', duration: DUR, ease: 'none' }, 0);
  const dust = $('dust');
  for (let i = 0; i < 34; i++) {
    const d = mk('', `left:${rnd() * 1080}px;top:${300 + rnd() * 1600}px;width:${3 + rnd() * 6}px;height:${3 + rnd() * 6}px;border-radius:50%;background:#cff;opacity:${0.2 + rnd() * 0.45}`, dust);
    tl.fromTo(d, { y: 0 }, { y: -(300 + rnd() * 700), duration: DUR, ease: 'none' }, 0);
  }
  const gr = $('grain');
  for (let t = 0; t < DUR; t += 0.083) tl.set(gr, { x: Math.round(rnd() * 60 - 30), y: Math.round(rnd() * 60 - 30) }, t);
}

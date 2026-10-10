/* scene_k3.js — clip K3, hard editorial style: my real room is the ONLY video layer. Hook, captions, 2 full-frame stock inserts, 1 waveform line and 1 type punch are overlays.
   Everything is a pure function of timeline time (GSAP tweens; fromTo with immediateRender:false; waveform via onUpdate on a proxy). */
const P = window.PLAN, OFF = P.off, DUR = P.dur, gs = window.gsap;
const tl = gs.timeline({ paused: true });
const T = t => Math.max(0, t - OFF);
const here = (a, b) => b > OFF + 0.001 && a < OFF + DUR - 0.001;
const $ = id => document.getElementById(id);
const SNAP = $('snap'), CAM = $('cam');

function mk(cls, css, parent, html, tag) {
  const e = document.createElement(tag || 'div');
  if (cls) e.className = cls;
  if (css) e.style.cssText = css;
  if (html != null) e.innerHTML = html;
  (parent || $('over')).appendChild(e);
  return e;
}

/* ---------------- camera ---------------- */
(function camera() {
  const k = P.cam;
  const first = k.find(r => r[0] >= OFF - 0.001) || k[0];
  tl.set(CAM, { scale: first[1], x: first[2], y: first[3] }, 0);
  for (let i = 0; i < k.length - 1; i++) {
    const a = k[i], b = k[i + 1];
    if (b[0] <= OFF || a[0] >= OFF + DUR) continue;
    tl.to(CAM, { scale: b[1], x: b[2], y: b[3], duration: Math.max(0.001, b[0] - a[0]), ease: 'none' }, T(a[0]));
  }
})();

/* ---------------- hits: short hard shake + zoom punch (origin = top edge, so the head is never pushed out of frame) ---------------- */
(P.hits || []).forEach(([t, amp, punch]) => {
  if (!here(t, t + 0.3)) return;
  const s = T(t), f = 1 / 30;
  const pts = [[0, 0], [1, -0.6], [-0.8, 0.7], [0.5, -0.4], [-0.25, 0.2], [0, 0]];
  for (let i = 0; i < pts.length - 1; i++)
    tl.fromTo(SNAP, { x: pts[i][0] * amp, y: pts[i][1] * amp }, { x: pts[i + 1][0] * amp, y: pts[i + 1][1] * amp, duration: f, ease: 'none', immediateRender: false }, s + i * f);
  if (punch > 0) tl.fromTo(SNAP, { scale: 1 + punch }, { scale: 1, duration: 0.3, ease: 'power3.out', immediateRender: false }, s);
});

/* ---------------- light flash ---------------- */
const flashEl = mk(null, '', null, '', 'div'); flashEl.id = 'flash';
const flash = (t, a) => { if (here(t, t + 0.2)) tl.fromTo(flashEl, { opacity: a || 0.5 }, { opacity: 0, duration: 0.14, ease: 'power2.out', immediateRender: false }, T(t)); };

/* ---------------- hook: three hard pops, three faces ---------------- */
(function hook() {
  const H = P.hook;
  if (!H || !here(H.t0, H.t1)) return;
  H.lines.forEach((l, i) => {
    const el = mk('hk ' + l.cls, `left:540px;top:${l.y}px;font-size:${l.size}px`, null, l.text);
    gs.set(el, { xPercent: -50, yPercent: -50, autoAlpha: 0 });
    tl.set(el, { autoAlpha: 1 }, T(l.t));
    if (l.cls === 'h1') tl.fromTo(el, { scale: 1.3 }, { scale: 1, duration: 0.11, ease: 'power4.out', immediateRender: false }, T(l.t));
    if (l.cls === 'h2') tl.fromTo(el, { scale: 1.55, y: -18 }, { scale: 1, y: 0, duration: 0.13, ease: 'power4.out', immediateRender: false }, T(l.t));
    if (l.cls === 'h3') tl.fromTo(el, { x: -90, scale: 1.12 }, { x: 0, scale: 1, duration: 0.12, ease: 'power4.out', immediateRender: false }, T(l.t));
    tl.to(el, { opacity: 0, duration: 0.07, ease: 'none' }, T(H.exit) + i * 0.05);
    tl.set(el, { autoAlpha: 0 }, T(H.t1) + 0.02);
  });
})();

/* ---------------- captions: word by word, hard scale-snap, key word in steel ---------------- */
(function captions() {
  const box = $('over');
  P.caps.forEach(c => {
    if (!here(c.s, c.e)) return;
    const el = mk('cap' + (c.big ? ' big' : ''), `top:${P.capY}px;font-size:${c.size}px`, box,
      c.w.map(w => `<span class="w ${w.cls}">${w.t}</span>`).join(' '));
    gs.set(el, { yPercent: -50 });
    tl.set(el, { autoAlpha: 1 }, T(c.s) - 0.001);
    tl.set(el, { autoAlpha: 0 }, T(c.e));
    P.cards.filter(x => x.kind === 'punch' && x.t < c.e && x.e > c.s).forEach(x => {          /* the type punch carries the word: captions step aside */
      tl.set(el, { autoAlpha: 0 }, Math.max(T(x.t), T(c.s)) + 0.0005);
      if (c.e > x.e) tl.set(el, { autoAlpha: 1 }, T(x.e));
    });
    const sp = el.querySelectorAll('.w');
    c.w.forEach((w, i) => {
      const t0 = i === 0 ? T(c.s) : Math.max(T(c.s), T(w.s));
      tl.set(sp[i], { opacity: 1 }, t0);
      const from = w.cls === 'k' ? 1.26 : w.cls === 'e' ? 1.2 : 1.12;
      tl.fromTo(sp[i], { scale: from }, { scale: 1, duration: 0.1, ease: 'power3.out', immediateRender: false }, t0);
      if (c.big && w.cls === 'k') tl.fromTo(sp[i], { scale: 1.5 }, { scale: 1.12, duration: 0.14, ease: 'power4.out', immediateRender: false }, t0 + 0.001);
    });
  });
})();

/* ---------------- inserts ---------------- */
P.cards.forEach(c => {
  if (!here(c.t, c.e)) return;
  /* full-frame stock: zoom-through in and out, hard cut at the end */
  if (c.kind === 'stock') {
    const box = $('sb' + c.n);
    gs.set(box, { autoAlpha: 0 });
    tl.set(box, { autoAlpha: 1 }, T(c.t));
    tl.set(box, { autoAlpha: 0 }, T(c.e));
    if (c.in === 'whip') tl.fromTo(box, { x: 760, scale: 1.12 }, { x: 0, scale: 1, duration: 0.14, ease: 'power4.out', immediateRender: false }, T(c.t));
    else tl.fromTo(box, { scale: 1.4 }, { scale: 1, duration: 0.24, ease: 'power3.out', immediateRender: false }, T(c.t));
    tl.fromTo(box, { scale: 1 }, { scale: 1.2, duration: 0.2, ease: 'power2.in', immediateRender: false }, T(c.e) - 0.2);
    tl.to(box, { scale: 1.02, duration: Math.max(0.1, c.e - c.t - 0.45), ease: 'none' }, T(c.t) + 0.26);
    if (c.out === 'flash') flash(c.e - 0.02, 0.55);
  }
  /* thin steel waveform: the voice, drawn as 90 hard bars */
  if (c.kind === 'wave') {
    const N = 90, X0 = 90, X1 = 990, CY = 1335, bars = [];
    for (let i = 0; i < N; i++) {
      const b = mk('wbar', `left:${X0 + (X1 - X0) * i / (N - 1) - 2}px;top:${CY}px;height:4px`, null, '');
      gs.set(b, { autoAlpha: 0 }); tl.set(b, { autoAlpha: 1 }, T(c.t)); tl.set(b, { autoAlpha: 0 }, T(c.e)); bars.push(b);
    }
    const base = mk('rule', `left:${X0}px;top:${CY - 2}px;width:${X1 - X0}px;height:3px;transform-origin:50% 50%`, null, '');
    gs.set(base, { autoAlpha: 0, scaleX: 0 });
    tl.set(base, { autoAlpha: 1 }, T(c.t)); tl.set(base, { autoAlpha: 0 }, T(c.e));
    tl.fromTo(base, { scaleX: 0 }, { scaleX: 1, duration: 0.18, ease: 'power4.out', immediateRender: false }, T(c.t));
    const prox = { p: 0 };
    const draw = () => {
      const p = prox.p, dur = c.e - c.t;
      for (let i = 0; i < N; i++) {
        const u = i / (N - 1), env = Math.sin(Math.PI * u) ** 0.8;
        const w = Math.abs(Math.sin(p * 31 + i * 1.9) * Math.cos(p * 17 - i * 0.7)) * 0.75 + 0.25 * Math.abs(Math.sin(p * 53 + i * 3.1));
        const grow = Math.min(1, p * dur / 0.15), fade = Math.min(1, (1 - p) * dur / 0.2);
        const h = Math.max(4, 150 * env * w * grow * fade);
        bars[i].style.height = h + 'px'; bars[i].style.top = (CY - h / 2) + 'px';
      }
    };
    tl.fromTo(prox, { p: 0 }, { p: 1, duration: c.e - c.t, ease: 'none', onUpdate: draw, immediateRender: false }, T(c.t));
    if (c.in === 'flash') flash(c.t, 0.45);
  }
  /* big type punch with two steel rules */
  if (c.kind === 'punch') {
    const Y = 1330;
    const tx = mk('punch', `top:${Y}px;font-size:230px`, null, c.text);
    gs.set(tx, { yPercent: -50, autoAlpha: 0 });
    tl.set(tx, { autoAlpha: 1 }, T(c.t)); tl.set(tx, { autoAlpha: 0 }, T(c.e));
    tl.fromTo(tx, { scale: 1.6 }, { scale: 1, duration: 0.12, ease: 'power4.out', immediateRender: false }, T(c.t));
    tl.to(tx, { scale: 1.04, duration: c.e - c.t - 0.15, ease: 'none' }, T(c.t) + 0.14);
    [Y - 135, Y + 135].forEach((y, k) => {
      const r = mk('rule', `left:210px;top:${y}px;width:660px`, null, '');
      gs.set(r, { autoAlpha: 0, scaleX: 0 });
      tl.set(r, { autoAlpha: 1 }, T(c.t)); tl.set(r, { autoAlpha: 0 }, T(c.e));
      tl.fromTo(r, { scaleX: 0 }, { scaleX: 1, duration: 0.2, ease: 'power4.out', immediateRender: false }, T(c.t) + 0.04 + k * 0.05);
    });
  }
});

window.__timelines = window.__timelines || {};
window.__timelines['main'] = tl;

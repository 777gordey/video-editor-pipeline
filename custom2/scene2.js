/* scene2.js — round 2: real footage untouched; camera, hook, captions, stickers, transitions as overlays.
   Everything is a pure function of timeline time (GSAP tweens, fromTo with immediateRender:false). */
const P = window.PLAN, OFF = P.off, DUR = P.dur, gs = window.gsap;
const tl = gs.timeline({ paused: true });
const T = t => Math.max(0, t - OFF);
const here = (a, b) => b > OFF + 0.001 && a < OFF + DUR - 0.001;
const $ = id => document.getElementById(id);
const SNAP = $('snap'), CAM = $('cam'), FLASH = $('flash'), FX = $('fx');

function mk(cls, css, parent, html, tag) {
  const e = document.createElement(tag || 'div');
  if (cls) e.className = cls;
  if (css) e.style.cssText = (/(^|;)\s*(left|top|inset|right|bottom)\s*:/.test(css) && !/position\s*:/.test(css) ? 'position:absolute;' : '') + css;
  if (html != null) e.innerHTML = html;
  (parent || $('over')).appendChild(e);
  return e;
}
function life(n, a, b) { // visible from a to b (global seconds)
  n.classList.add('o');
  gs.set(n, { autoAlpha: 0 });
  tl.set(n, { autoAlpha: 1 }, T(a));
  tl.set(n, { autoAlpha: 0 }, T(b));
  return n;
}

/* ---------------- camera (face-tracked path computed in build2.py) ---------------- */
(function camera() {
  const k = P.cam; // [t, scale, x, y]
  const first = k.find(r => r[0] >= OFF - 0.001) || k[0];
  tl.set(CAM, { scale: first[1], x: first[2], y: first[3] }, 0);
  for (let i = 0; i < k.length - 1; i++) {
    const a = k[i], b = k[i + 1];
    if (b[0] <= OFF || a[0] >= OFF + DUR) continue;
    tl.to(CAM, { scale: b[1], x: b[2], y: b[3], duration: b[0] - a[0], ease: 'none' }, T(a[0]));
  }
})();

/* ---------------- hook: 3D metal type ---------------- */
function x3(text, o) {
  const box = mk('x3d' + (o.acc ? ' acc' : ''), `left:540px;top:${o.y}px;font-size:${o.size}px;transform:translate(-50%,-50%)`);
  const chs = [];
  const dark = o.acc ? [66, 86, 4] : [46, 54, 64];
  for (const c of text) {
    const ch = mk('ch', '', box, '', 'span');
    mk('sp', '', ch, c === ' ' ? '&nbsp;&nbsp;' : c, 'span');
    const D = o.depth || 7;
    for (let i = D; i >= 1; i--) {
      const m = 0.35 + 0.65 * (1 - i / D);
      mk('l', `transform:translate(${i * 0.9}px,${i * 1.5}px);color:rgb(${dark.map(v => Math.round(v * m)).join(',')})`, ch, c, 'span');
    }
    mk('f', '', ch, c, 'span');
    mk('shine', '', ch, c, 'span');
    chs.push(ch);
  }
  box._chs = chs;
  return box;
}
(function hook() {
  const H = P.hook;
  if (!H || !here(H.t0, H.t1)) return;
  const boxes = H.lines.map(l => x3(l.text, l));
  const glow = mk('hookglow', `left:90px;top:${H.gy - 330}px;width:900px;height:660px`);
  boxes.concat([glow]).forEach(b => { b.classList.add('o'); gs.set(b, { autoAlpha: 0 }); tl.set(b, { autoAlpha: 1 }, T(H.t0)); tl.set(b, { autoAlpha: 0 }, T(H.t1) + 0.02); });
  tl.fromTo(glow, { opacity: 0 }, { opacity: 1, duration: 0.5, ease: 'power2.out', immediateRender: false }, T(H.t0));
  tl.to(glow, { opacity: 0, duration: 0.3 }, T(H.t1) - 0.25);
  let at = H.t0;
  boxes.forEach((b, li) => {
    b._chs.forEach((ch, i) => {
      tl.fromTo(ch, { y: 120, rotationX: -85, scale: 0.55, opacity: 0, transformPerspective: 900 },
        { y: 0, rotationX: 0, scale: 1, opacity: 1, duration: 0.5, ease: 'back.out(1.8)', immediateRender: false }, T(at) + i * 0.035);
    });
    at += 0.16;
    b._chs.forEach((ch, i) => { // soft shine sweep
      tl.fromTo(ch.querySelector('.shine'), { backgroundPosition: '130% 0' }, { backgroundPosition: '-30% 0', duration: 0.6, ease: 'power2.inOut', immediateRender: false }, T(H.t0 + 0.9 + li * 0.12) + i * 0.04);
    });
    b._chs.forEach((ch, i) => { // exit
      const n = b._chs.length, dir = (i - n / 2) / (n / 2);
      tl.to(ch, { y: -170, x: dir * 120, rotationX: 55, scale: 0.7, opacity: 0, duration: 0.3, ease: 'power3.in' }, T(H.t1) - 0.3 + li * 0.04 + i * 0.012);
    });
  });
})();

/* ---------------- captions ---------------- */
(function captions() {
  const box = $('over');
  P.caps.forEach((c, ci) => {
    if (!here(c.s, c.e)) return;
    const el = mk('cap', `top:${c.y}px;font-size:${c.size}px`, box,
      c.w.map(w => `<span class="w${w.k ? ' k' : ''}">${w.t}</span>`).join(' '));
    gs.set(el, { yPercent: -50 });
    tl.set(el, { autoAlpha: 1 }, T(c.s) - 0.001);
    tl.set(el, { autoAlpha: 0 }, T(c.e));
    tl.fromTo(el, { y: 22, scale: 0.92, opacity: 0 }, { y: 0, scale: 1, opacity: 1, duration: 0.16, ease: 'back.out(2.2)', immediateRender: false }, T(c.s));
    const sp = el.querySelectorAll('.w');
    c.w.forEach((w, i) => {
      if (!w.k) return;
      tl.fromTo(sp[i], { scale: 1 }, { scale: 1.16, duration: 0.11, ease: 'power2.out', immediateRender: false }, Math.max(T(c.s) + 0.05, T(w.s)));
      tl.to(sp[i], { scale: 1.05, duration: 0.2, ease: 'power2.inOut' }, Math.max(T(c.s) + 0.05, T(w.s)) + 0.11);
    });
  });
})();

/* ---------------- stickers: small animated icons ---------------- */
const INK = '#101510', ACC = '#D4FF3F', WH = '#ffffff';
const ICONS = {
  stopwatch: `<svg viewBox="0 0 200 200"><rect x="84" y="14" width="32" height="20" rx="6" fill="${ACC}" stroke="${INK}" stroke-width="7"/><rect x="92" y="30" width="16" height="20" fill="${INK}"/>
    <circle cx="100" cy="116" r="72" fill="${WH}" stroke="${INK}" stroke-width="9"/><circle cx="100" cy="116" r="54" fill="none" stroke="${ACC}" stroke-width="14" stroke-dasharray="230 340" transform="rotate(-90 100 116)" stroke-linecap="round"/>
    <g class="hand"><line x1="100" y1="116" x2="100" y2="76" stroke="${INK}" stroke-width="10" stroke-linecap="round"/></g><circle cx="100" cy="116" r="9" fill="${INK}"/></svg>`,
  magnify: `<svg viewBox="0 0 200 200"><line x1="130" y1="130" x2="176" y2="176" stroke="${INK}" stroke-width="30" stroke-linecap="round"/><line x1="130" y1="130" x2="176" y2="176" stroke="${WH}" stroke-width="14" stroke-linecap="round"/>
    <circle cx="88" cy="88" r="60" fill="${WH}" stroke="${INK}" stroke-width="10"/><path class="chk" d="M58 90 L80 112 L120 66" fill="none" stroke="${INK}" stroke-width="22" stroke-linecap="round" stroke-linejoin="round"/><path class="chk" d="M58 90 L80 112 L120 66" fill="none" stroke="${ACC}" stroke-width="12" stroke-linecap="round" stroke-linejoin="round"/></svg>`,
  one: `<svg viewBox="0 0 200 200"><circle class="ring" cx="100" cy="100" r="84" fill="none" stroke="${ACC}" stroke-width="6" opacity=".7"/><circle cx="100" cy="100" r="76" fill="${ACC}" stroke="${INK}" stroke-width="9"/>
    <text x="100" y="100" text-anchor="middle" dominant-baseline="central" class="num" font-size="118" fill="${INK}">1</text></svg>`,
  question: `<svg viewBox="0 0 200 200"><path d="M30 28 H170 a14 14 0 0 1 14 14 V128 a14 14 0 0 1 -14 14 H112 L74 180 V142 H30 a14 14 0 0 1 -14 -14 V42 a14 14 0 0 1 14 -14 Z" fill="${WH}" stroke="${INK}" stroke-width="9" stroke-linejoin="round"/>
    <text x="100" y="86" text-anchor="middle" dominant-baseline="central" class="num" font-size="104" fill="${INK}">?</text><circle class="dot" cx="150" cy="52" r="9" fill="${ACC}" stroke="${INK}" stroke-width="4"/></svg>`,
  bell: `<svg viewBox="0 0 200 200"><g class="waves"><path d="M22 70 a90 90 0 0 0 -4 44" fill="none" stroke="${ACC}" stroke-width="9" stroke-linecap="round"/><path d="M178 70 a90 90 0 0 1 4 44" fill="none" stroke="${ACC}" stroke-width="9" stroke-linecap="round"/></g>
    <g class="swing"><path d="M100 24 C70 24 58 50 58 80 L58 112 L38 140 L162 140 L142 112 L142 80 C142 50 130 24 100 24 Z" fill="${ACC}" stroke="${INK}" stroke-width="9" stroke-linejoin="round"/><circle cx="100" cy="162" r="15" fill="${WH}" stroke="${INK}" stroke-width="8"/></g></svg>`,
  check: `<svg viewBox="0 0 200 200"><circle cx="100" cy="100" r="78" fill="${ACC}" stroke="${INK}" stroke-width="9"/><path class="chk" d="M58 104 L88 134 L144 72" fill="none" stroke="${INK}" stroke-width="20" stroke-linecap="round" stroke-linejoin="round"/></svg>`,
  price: `<svg viewBox="0 0 200 200"><path d="M24 70 L88 22 H168 a10 10 0 0 1 10 10 V110 L110 178 L24 110 Z" fill="${ACC}" stroke="${INK}" stroke-width="9" stroke-linejoin="round" transform="rotate(8 100 100)"/>
    <circle cx="140" cy="54" r="11" fill="${WH}" stroke="${INK}" stroke-width="6"/><text x="104" y="106" text-anchor="middle" dominant-baseline="central" class="num" font-size="46" fill="${INK}" transform="rotate(8 100 100)">4 000</text></svg>`,
  calendar: `<svg viewBox="0 0 200 200"><rect x="26" y="40" width="148" height="136" rx="20" fill="${WH}" stroke="${INK}" stroke-width="9"/><path d="M26 60 a20 20 0 0 1 20 -20 H154 a20 20 0 0 1 20 20 V86 H26 Z" fill="${ACC}" stroke="${INK}" stroke-width="9"/>
    <rect x="56" y="22" width="14" height="36" rx="7" fill="${INK}"/><rect x="130" y="22" width="14" height="36" rx="7" fill="${INK}"/><text x="100" y="134" text-anchor="middle" dominant-baseline="central" class="num" font-size="56" fill="${INK}">ВС</text></svg>`,
  clock: `<svg viewBox="0 0 200 200"><circle cx="100" cy="100" r="78" fill="${WH}" stroke="${INK}" stroke-width="9"/><g class="hh"><line x1="100" y1="100" x2="100" y2="54" stroke="${INK}" stroke-width="10" stroke-linecap="round"/></g><g class="mh"><line x1="100" y1="100" x2="100" y2="40" stroke="${ACC}" stroke-width="8" stroke-linecap="round"/></g><circle cx="100" cy="100" r="9" fill="${INK}"/></svg>`,
};
(function stickers() {
  (P.stk || []).forEach(s => {
    if (!here(s.t, s.e)) return;
    const n = mk('stk', `left:${s.x - 150}px;top:${s.y - 150}px;transform:rotate(${s.rot || 0}deg)`, null, ICONS[s.type]);
    n.classList.add('o');
    const a = s.t, b = s.e;
    tl.set(n, { autoAlpha: 1 }, T(a));
    tl.set(n, { autoAlpha: 0 }, T(b));
    tl.fromTo(n, { scale: 0, rotation: (s.rot || 0) - 22, y: 30 }, { scale: 1, rotation: s.rot || 0, y: 0, duration: 0.5, ease: 'back.out(2.1)', immediateRender: false }, T(a));
    // gentle settle float while on screen
    tl.to(n, { y: -9, duration: Math.max(0.2, (b - a - 0.9) / 2), ease: 'sine.inOut', yoyo: true, repeat: 1 }, T(a) + 0.5);
    tl.to(n, { scale: 0, rotation: (s.rot || 0) + 18, y: 20, duration: 0.24, ease: 'back.in(2)' }, T(b) - 0.26);
    const q = sel => n.querySelectorAll(sel);
    const hand = q('.hand')[0];
    if (hand) tl.fromTo(hand, { rotation: -40, svgOrigin: '100 116' }, { rotation: 320, svgOrigin: '100 116', duration: b - a - 0.3, ease: 'power1.inOut', immediateRender: false }, T(a) + 0.15);
    q('.chk').forEach(c => { tl.fromTo(c, { strokeDasharray: 200, strokeDashoffset: 200 }, { strokeDashoffset: 0, duration: 0.4, ease: 'power2.out', immediateRender: false }, T(a) + 0.35); });
    const ring = q('.ring')[0];
    if (ring) tl.fromTo(ring, { scale: 0.85, transformOrigin: '50% 50%', opacity: 0.9 }, { scale: 1.22, opacity: 0, duration: 0.9, ease: 'power2.out', repeat: 1, immediateRender: false }, T(a) + 0.35);
    const sw = q('.swing')[0];
    if (sw) tl.fromTo(sw, { rotation: -16, svgOrigin: '100 24' }, { rotation: 16, svgOrigin: '100 24', duration: 0.16, ease: 'sine.inOut', yoyo: true, repeat: 7, immediateRender: false }, T(a) + 0.3);
    const wv = q('.waves')[0];
    if (wv) tl.fromTo(wv, { opacity: 0.2 }, { opacity: 1, duration: 0.16, yoyo: true, repeat: 7, immediateRender: false }, T(a) + 0.3);
    const dot = q('.dot')[0];
    if (dot) tl.fromTo(dot, { scale: 0.6, svgOrigin: '150 52' }, { scale: 1.5, svgOrigin: '150 52', duration: 0.3, yoyo: true, repeat: 3, ease: 'sine.inOut', immediateRender: false }, T(a) + 0.4);
    const mh = q('.mh')[0], hh = q('.hh')[0];
    if (mh) tl.fromTo(mh, { rotation: 0, svgOrigin: '100 100' }, { rotation: s.mturn || 360, svgOrigin: '100 100', duration: b - a - 0.4, ease: 'power2.inOut', immediateRender: false }, T(a) + 0.2);
    if (hh) tl.fromTo(hh, { rotation: s.h0 || 0, svgOrigin: '100 100' }, { rotation: s.h1 || 30, svgOrigin: '100 100', duration: b - a - 0.4, ease: 'power2.inOut', immediateRender: false }, T(a) + 0.2);
  });
})();

/* ---------------- transitions + jump-cut punches ---------------- */
function flash(t, d, peak) {
  tl.set(FLASH, { opacity: peak, visibility: 'visible' }, T(t));
  tl.to(FLASH, { opacity: 0, duration: d, ease: 'power2.out' }, T(t));
  tl.set(FLASH, { visibility: 'hidden' }, T(t) + d + 0.01);
}
const TR = {
  sweep(t) { // soft light band sweeping across
    const b = mk('', `left:-420px;top:-200px;width:340px;height:2400px;background:linear-gradient(90deg,rgba(255,255,255,0),rgba(255,255,255,.85) 50%,rgba(255,255,255,0));transform:skewX(-16deg);filter:blur(26px);mix-blend-mode:screen;opacity:0`, FX);
    tl.fromTo(b, { x: 0, opacity: 1 }, { x: 1950, opacity: 1, duration: 0.55, ease: 'power2.inOut', immediateRender: false }, T(t) - 0.28);
    tl.set(b, { opacity: 0 }, T(t) + 0.3);
    tl.fromTo(SNAP, { scale: 1.0 }, { scale: 1.035, duration: 0.2, ease: 'power2.in', immediateRender: false }, Math.max(0, T(t) - 0.2));
    tl.fromTo(SNAP, { scale: 1.035 }, { scale: 1, duration: 0.4, ease: 'power3.out', immediateRender: false }, T(t));
  },
  zoom(t) { // zoom-through with a touch of blur
    tl.fromTo(SNAP, { scale: 1, filter: 'blur(0px)' }, { scale: 1.09, filter: 'blur(7px)', duration: 0.17, ease: 'power3.in', immediateRender: false }, Math.max(0, T(t) - 0.17));
    tl.fromTo(SNAP, { scale: 0.95, filter: 'blur(7px)' }, { scale: 1, filter: 'blur(0px)', duration: 0.38, ease: 'power3.out', immediateRender: false }, T(t));
    flash(t - 0.03, 0.3, 0.32);
  },
  push(t) { // sideways push
    tl.fromTo(SNAP, { x: 0, filter: 'blur(0px)' }, { x: -110, filter: 'blur(8px)', duration: 0.15, ease: 'power3.in', immediateRender: false }, Math.max(0, T(t) - 0.15));
    tl.fromTo(SNAP, { x: 110, filter: 'blur(8px)' }, { x: 0, filter: 'blur(0px)', duration: 0.36, ease: 'power4.out', immediateRender: false }, T(t));
    for (let i = 0; i < 4; i++) {
      const s = mk('', `left:-100px;top:${420 + i * 250}px;width:${520 + i * 90}px;height:4px;border-radius:2px;background:linear-gradient(90deg,transparent,rgba(255,255,255,.8),transparent);opacity:0`, FX);
      tl.fromTo(s, { x: 1250, opacity: 0.75 }, { x: -800, opacity: 0, duration: 0.32, ease: 'power2.out', immediateRender: false }, T(t) - 0.1 + i * 0.015);
    }
  },
  flare(t) { // soft bloom
    const g = mk('', `left:140px;top:560px;width:800px;height:800px;border-radius:50%;background:radial-gradient(closest-side,rgba(255,255,235,.95),rgba(212,255,63,.35) 55%,rgba(212,255,63,0));opacity:0;mix-blend-mode:screen`, FX);
    tl.fromTo(g, { scale: 0.3, opacity: 0.9 }, { scale: 2.4, opacity: 0, duration: 0.6, ease: 'power2.out', immediateRender: false }, T(t) - 0.12);
    tl.fromTo(SNAP, { scale: 1 }, { scale: 1.04, duration: 0.14, ease: 'power2.in', immediateRender: false }, Math.max(0, T(t) - 0.14));
    tl.fromTo(SNAP, { scale: 1.04 }, { scale: 1, duration: 0.4, ease: 'power3.out', immediateRender: false }, T(t));
    flash(t - 0.02, 0.35, 0.28);
  }
};
(P.tr || []).forEach(x => { if (here(x.t - 0.4, x.t + 0.6)) TR[x.type](x.t); });
(P.punch || []).forEach(([t, a]) => {
  if (!here(t, t + 0.5)) return;
  tl.fromTo(SNAP, { scale: 1 + a }, { scale: 1, duration: 0.45, ease: 'power3.out', immediateRender: false }, T(t));
});

window.__timelines = window.__timelines || {};
window.__timelines['main'] = tl;

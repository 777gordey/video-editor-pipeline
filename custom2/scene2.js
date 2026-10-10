/* scene2.js — round 5: my real room is the ONLY video layer; hook, captions, comic callouts, stock cards and transitions are overlays.
   Everything is a pure function of timeline time (GSAP tweens; fromTo with immediateRender:false). */
const P = window.PLAN, OFF = P.off, DUR = P.dur, gs = window.gsap;
const tl = gs.timeline({ paused: true });
const T = t => Math.max(0, t - OFF);
const here = (a, b) => b > OFF + 0.001 && a < OFF + DUR - 0.001;
const $ = id => document.getElementById(id);
const SNAP = $('snap'), CAM = $('cam'), FLASH = $('flash'), FX = $('fx');

function mk(cls, css, parent, html, tag) {
  const e = document.createElement(tag || 'div');
  if (cls) e.className = cls;
  if (css) e.style.cssText = css;
  if (html != null) e.innerHTML = html;
  (parent || $('over')).appendChild(e);
  return e;
}

/* ---------------- camera (face-tracked path from build2.py) ---------------- */
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

/* ---------------- impact: 4-frame screen shake + zoom punch on the footage ---------------- */
(P.hits || []).forEach(([t, amp, punch]) => {
  if (!here(t, t + 0.3)) return;
  const s = T(t), f = 1 / 30;
  const pts = [[0, 0], [1, -0.6], [-0.8, 0.7], [0.5, -0.4], [-0.25, 0.2], [0, 0]];
  for (let i = 0; i < pts.length - 1; i++) {
    tl.fromTo(SNAP, { x: pts[i][0] * amp, y: pts[i][1] * amp }, { x: pts[i + 1][0] * amp, y: pts[i + 1][1] * amp, duration: f, ease: 'none', immediateRender: false }, s + i * f);
  }
  tl.fromTo(SNAP, { scale: 1 + punch }, { scale: 1, duration: 0.3, ease: 'power3.out', immediateRender: false }, s);
});

/* ---------------- hook: three hits, three fonts, hard pop-in with overshoot ---------------- */
(function hook() {
  const H = P.hook;
  if (!H || !here(H.t0, H.t1)) return;
  H.lines.forEach((l, i) => {
    const el = mk('hk ' + l.cls, `left:540px;top:${l.y}px;font-size:${l.size}px`, null, l.text);
    gs.set(el, { xPercent: -50, yPercent: -50, autoAlpha: 0 });
    tl.set(el, { autoAlpha: 1 }, T(l.t));
    tl.fromTo(el, { scale: 1.3 }, { scale: 1, duration: 0.26, ease: 'back.out(3.4)', immediateRender: false }, T(l.t));
    tl.to(el, { scale: 1.18, opacity: 0, y: -80, duration: 0.24, ease: 'power3.in' }, T(H.exit) + i * 0.03);
    tl.set(el, { autoAlpha: 0 }, T(H.t1) + 0.02);
    if (l.cls === 'h3') {   // white underline wipes in under the payoff line
      const w = l.w || 760;
      const u = mk('hku', `left:${540 - w / 2}px;top:${l.y + l.size * 0.66}px;width:${w}px`, null, '');
      gs.set(u, { transformOrigin: '0 50%', scaleX: 0, autoAlpha: 0 });
      tl.set(u, { autoAlpha: 1 }, T(l.t) + 0.12);
      tl.fromTo(u, { scaleX: 0 }, { scaleX: 1, duration: 0.22, ease: 'power3.out', immediateRender: false }, T(l.t) + 0.12);
      tl.to(u, { opacity: 0, duration: 0.2 }, T(H.exit));
      tl.set(u, { autoAlpha: 0 }, T(H.t1) + 0.02);
    }
  });
})();

/* ---------------- captions: designed system (styles chosen in build2.py) ---------------- */
(function captions() {
  const box = $('over');
  P.caps.forEach(c => {
    if (!here(c.s, c.e)) return;
    const el = mk('cap', `top:${c.y}px;font-size:${c.size}px`, box,
      c.w.map(w => `<span class="w ${w.cls}${w.col ? ' c-' + w.col : ''}">${w.t}</span>`).join(' '));
    gs.set(el, { yPercent: -50 });
    tl.set(el, { autoAlpha: 1 }, T(c.s) - 0.001);
    tl.set(el, { autoAlpha: 0 }, T(c.e));
    tl.fromTo(el, { y: 22, scale: c.first ? 0.86 : 0.92, opacity: 0 }, { y: 0, scale: 1, opacity: 1, duration: c.first ? 0.2 : 0.16, ease: 'back.out(2.4)', immediateRender: false }, T(c.s));
    const sp = el.querySelectorAll('.w');
    let tilt = -4;
    c.w.forEach((w, i) => {
      if (w.cls === 'n') return;
      if (w.cls === 'e') { gs.set(sp[i], { rotation: tilt }); tilt = -tilt * 0.75; }
      const at = Math.max(T(c.s) + 0.05, T(w.s));
      tl.fromTo(sp[i], { scale: 0.9 }, { scale: 1.18, duration: 0.11, ease: 'power2.out', immediateRender: false }, at);
      tl.to(sp[i], { scale: 1.05, duration: 0.2, ease: 'power2.inOut' }, at + 0.11);
    });
  });
})();

/* ---------------- comic callouts: burst / bubble / stamp / stop-sign ---------------- */
function burstPts(d) {
  const r = d / 2, pts = [];
  for (let k = 0; k < 32; k++) {
    const a = (k / 32) * Math.PI * 2 - Math.PI / 2, rr = (k % 2 ? 0.74 : 1.0) * (1 + 0.05 * Math.sin(k * 2.3)) * r * 0.97;
    pts.push((r + Math.cos(a) * rr).toFixed(1) + ',' + (r + Math.sin(a) * rr).toFixed(1));
  }
  return pts.join(' ');
}
function octPts(d, k0) {
  const r = d / 2, pts = [];
  for (let k = 0; k < 8; k++) { const a = (k / 8) * Math.PI * 2 + Math.PI / 8; pts.push((r + Math.cos(a) * r * k0).toFixed(1) + ',' + (r + Math.sin(a) * r * k0).toFixed(1)); }
  return pts.join(' ');
}
(P.calls || []).forEach(c => {
  if (!here(c.t, c.e)) return;
  let inner = '';
  if (c.kind === 'burst') inner = `<svg viewBox="0 0 ${c.d} ${c.d}"><polygon points="${burstPts(c.d)}" fill="#FFD21F" stroke="#101510" stroke-width="9" stroke-linejoin="round"/><text x="${c.d / 2}" y="${c.d / 2 + 4}" font-size="${c.fs}" fill="#E0202F" stroke="#fff" stroke-width="10">${c.text}</text></svg>`;
  else if (c.kind === 'stop') inner = `<svg viewBox="0 0 ${c.d} ${c.d}"><polygon points="${octPts(c.d, 0.96)}" fill="#E5202F" stroke="#fff" stroke-width="16" stroke-linejoin="round"/><polygon points="${octPts(c.d, 0.80)}" fill="none" stroke="#fff" stroke-width="5" stroke-linejoin="round"/><text x="${c.d / 2}" y="${c.d / 2 + 4}" font-size="${c.fs}" fill="#fff">${c.text}</text></svg>`;
  else inner = `<div class="tx" style="font-size:${c.fs}px">${c.text}</div>`;
  const n = mk('co ' + c.kind, `left:${c.x - c.w / 2}px;top:${c.y - c.h / 2}px;width:${c.w}px;height:${c.h}px`, null, inner);
  gs.set(n, { autoAlpha: 0, rotation: c.rot });
  tl.set(n, { autoAlpha: 1 }, T(c.t));
  tl.set(n, { autoAlpha: 0 }, T(c.e));
  if (c.slam) {
    tl.fromTo(n, { scale: 2.8, rotation: c.rot - 7 }, { scale: 1, rotation: c.rot, duration: 0.17, ease: 'power4.in', immediateRender: false }, T(c.t));
    tl.fromTo(n, { scale: 1 }, { scale: 1.07, duration: 0.09, ease: 'power2.out', yoyo: true, repeat: 1, immediateRender: false }, T(c.t) + 0.17);
  } else {
    tl.fromTo(n, { scale: 0.2, rotation: c.rot - 18 }, { scale: 1, rotation: c.rot, duration: 0.38, ease: 'back.out(2.6)', immediateRender: false }, T(c.t));
    tl.to(n, { rotation: c.rot + 3, duration: Math.max(0.3, (c.e - c.t - 0.7) / 2), ease: 'sine.inOut', yoyo: true, repeat: 1 }, T(c.t) + 0.4);
  }
  tl.to(n, { scale: 0, rotation: c.rot + 14, duration: 0.2, ease: 'back.in(2)' }, T(c.e) - 0.22);
});

/* ---------------- stock cutaway cards (zoom-through in and out come from P.tr) ---------------- */
(P.cuts || []).forEach(c => {
  if (c.kind !== 'card') return;
  const n = $('card' + c.n);
  if (!n || !here(c.t, c.e)) return;
  n.classList.add('o');
  gs.set(n, { autoAlpha: 0 });
  tl.set(n, { autoAlpha: 1 }, T(c.t));
  tl.set(n, { autoAlpha: 0 }, T(c.e));
  tl.fromTo(n, { scale: 1.07, rotation: c.n % 2 ? -1.5 : 1.5 }, { scale: 1, rotation: 0, duration: 0.5, ease: 'power3.out', immediateRender: false }, T(c.t));
  tl.to(n, { scale: 1.035, duration: Math.max(0.3, c.e - c.t - 0.5), ease: 'none' }, T(c.t) + 0.5);
});

/* ---------------- transitions ---------------- */
function flash(t, d, peak) {
  tl.set(FLASH, { opacity: peak, visibility: 'visible' }, T(t));
  tl.to(FLASH, { opacity: 0, duration: d, ease: 'power2.out' }, T(t));
  tl.set(FLASH, { visibility: 'hidden' }, T(t) + d + 0.01);
}
const TR = {
  sweep(t) {
    const b = mk('', `position:absolute;left:-420px;top:-200px;width:340px;height:2400px;background:linear-gradient(90deg,rgba(255,255,255,0),rgba(255,255,255,.85) 50%,rgba(255,255,255,0));transform:skewX(-16deg);filter:blur(26px);mix-blend-mode:screen;opacity:0`, FX);
    tl.fromTo(b, { x: 0, opacity: 1 }, { x: 1950, opacity: 1, duration: 0.55, ease: 'power2.inOut', immediateRender: false }, T(t) - 0.28);
    tl.set(b, { opacity: 0 }, T(t) + 0.3);
    tl.fromTo(SNAP, { scale: 1.0 }, { scale: 1.035, duration: 0.2, ease: 'power2.in', immediateRender: false }, Math.max(0, T(t) - 0.2));
    tl.fromTo(SNAP, { scale: 1.035 }, { scale: 1, duration: 0.4, ease: 'power3.out', immediateRender: false }, T(t));
  },
  zoom(t) {
    tl.fromTo(SNAP, { scale: 1, filter: 'blur(0px)' }, { scale: 1.09, filter: 'blur(7px)', duration: 0.17, ease: 'power3.in', immediateRender: false }, Math.max(0, T(t) - 0.17));
    tl.fromTo(SNAP, { scale: 0.95, filter: 'blur(7px)' }, { scale: 1, filter: 'blur(0px)', duration: 0.38, ease: 'power3.out', immediateRender: false }, T(t));
    flash(t - 0.03, 0.3, 0.32);
  },
  push(t) {
    tl.fromTo(SNAP, { x: 0, filter: 'blur(0px)' }, { x: -110, filter: 'blur(8px)', duration: 0.15, ease: 'power3.in', immediateRender: false }, Math.max(0, T(t) - 0.15));
    tl.fromTo(SNAP, { x: 110, filter: 'blur(8px)' }, { x: 0, filter: 'blur(0px)', duration: 0.36, ease: 'power4.out', immediateRender: false }, T(t));
    for (let i = 0; i < 4; i++) {
      const s = mk('', `position:absolute;left:-100px;top:${420 + i * 250}px;width:${520 + i * 90}px;height:4px;border-radius:2px;background:linear-gradient(90deg,transparent,rgba(255,255,255,.8),transparent);opacity:0`, FX);
      tl.fromTo(s, { x: 1250, opacity: 0.75 }, { x: -800, opacity: 0, duration: 0.32, ease: 'power2.out', immediateRender: false }, T(t) - 0.1 + i * 0.015);
    }
  },
  flare(t) {
    const g = mk('', `position:absolute;left:140px;top:560px;width:800px;height:800px;border-radius:50%;background:radial-gradient(closest-side,rgba(255,255,235,.95),rgba(212,255,63,.35) 55%,rgba(212,255,63,0));opacity:0;mix-blend-mode:screen`, FX);
    tl.fromTo(g, { scale: 0.3, opacity: 0.9 }, { scale: 2.4, opacity: 0, duration: 0.6, ease: 'power2.out', immediateRender: false }, T(t) - 0.12);
    tl.fromTo(SNAP, { scale: 1 }, { scale: 1.04, duration: 0.14, ease: 'power2.in', immediateRender: false }, Math.max(0, T(t) - 0.14));
    tl.fromTo(SNAP, { scale: 1.04 }, { scale: 1, duration: 0.4, ease: 'power3.out', immediateRender: false }, T(t));
    flash(t - 0.02, 0.35, 0.28);
  }
};
(P.tr || []).forEach(x => { if (here(x.t - 0.4, x.t + 0.6)) TR[x.type](x.t); });

window.__timelines = window.__timelines || {};
window.__timelines['main'] = tl;

/* scene.js — batch machine. My real room is the ONLY video layer. Hook, captions, cards, type slams, 1 wildcard are overlays;
   full-frame stock is a short cutaway. Everything is a pure function of timeline time (GSAP tweens; fromTo with immediateRender:false). */
const P = window.PLAN, OFF = P.off, DUR = P.dur, gs = window.gsap;
const tl = gs.timeline({ paused: true });
const T = t => Math.max(0, t - OFF);
const here = (a, b) => b > OFF + 0.001 && a < OFF + DUR - 0.001;
const $ = id => document.getElementById(id);
const SNAP = $('snap'), CAM = $('cam');
const WC = P.wc || {};

function mk(cls, css, parent, html, tag) {
  const e = document.createElement(tag || 'div');
  if (cls) e.className = cls;
  if (css) e.style.cssText = css;
  if (html != null) e.innerHTML = html;
  (parent || $('over')).appendChild(e);
  return e;
}
const pad = n => String(n).padStart(2, '0');
const thin = n => String(Math.round(n)).replace(/\B(?=(\d{3})+(?!\d))/g, ' ');
const esc = s => String(s == null ? '' : s).replace(/&/g, '&amp;').replace(/</g, '&lt;');

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
  const A = P.hookAnim;
  H.lines.forEach((l, i) => {
    const el = mk('hk ' + l.cls, `left:540px;top:${l.y}px;font-size:${l.size}px`, null, esc(l.text));
    gs.set(el, { xPercent: -50, yPercent: -50, autoAlpha: 0 });
    tl.set(el, { autoAlpha: 1 }, T(l.t));
    const fr = { hard: [[{ scale: 1.3 }, { scale: 1, duration: 0.11, ease: 'power4.out' }], [{ scale: 1.55, y: -18 }, { scale: 1, y: 0, duration: 0.13, ease: 'power4.out' }],
                        [{ x: -90, scale: 1.12 }, { x: 0, scale: 1, duration: 0.12, ease: 'power4.out' }]],
                 soft: [[{ scale: 1.45, rotation: -7 }, { scale: 1, rotation: -3, duration: 0.26, ease: 'back.out(3)' }], [{ scale: 1.7, y: -26 }, { scale: 1, y: 0, duration: 0.24, ease: 'power4.out' }],
                        [{ y: -150, scale: 0.9 }, { y: 0, scale: 1, duration: 0.3, ease: 'bounce.out' }]],
                 slam: [[{ scale: 1.6, rotation: -6 }, { scale: 1, rotation: -2, duration: 0.2, ease: 'back.out(3)' }], [{ scale: 1.9, y: -30 }, { scale: 1, y: 0, duration: 0.18, ease: 'power4.out' }],
                        [{ scale: 1.7, rotation: 7 }, { scale: 1, rotation: 1.5, duration: 0.22, ease: 'back.out(3)' }]] }[A] || [];
    const f = fr[Math.min(i, fr.length - 1)];
    if (f) tl.fromTo(el, f[0], Object.assign({ immediateRender: false }, f[1]), T(l.t));
    tl.to(el, { opacity: 0, duration: A === 'hard' ? 0.07 : 0.22, ease: 'none' }, T(H.exit) + i * 0.05);
    tl.set(el, { autoAlpha: 0 }, T(H.t1) + 0.02);
  });
})();

/* ---------------- captions ---------------- */
(function captions() {
  const box = $('over');
  P.caps.forEach(c => {
    if (!here(c.s, c.e)) return;
    const el = mk('cap' + (c.big ? ' big' : ''), `top:${P.capY}px;font-size:${c.size}px`, box,
      c.w.map(w => `<span class="w ${w.cls}">${esc(w.t)}</span>`).join(' '));
    gs.set(el, { yPercent: -50 });
    tl.set(el, { autoAlpha: 1 }, T(c.s) - 0.001);
    tl.set(el, { autoAlpha: 0 }, T(c.e));
    P.cards.filter(x => (x.kind === 'punch' || x.kind === 'stamp') && x.t < c.e && x.e > c.s).forEach(x => {   /* the slam carries the word: captions step aside */
      tl.set(el, { autoAlpha: 0 }, Math.max(T(x.t), T(c.s)) + 0.0005);
      if (c.e > x.e) tl.set(el, { autoAlpha: 1 }, T(x.e));
    });
    const sp = el.querySelectorAll('.w');
    if (P.capMode === 'wordwise') {
      c.w.forEach((w, i) => {
        const t0 = i === 0 ? T(c.s) : Math.max(T(c.s), T(w.s));
        tl.set(sp[i], { opacity: 1 }, t0);
        const from = w.cls === 'k' ? 1.26 : w.cls === 'e' ? 1.2 : 1.12;
        tl.fromTo(sp[i], { scale: from }, { scale: 1, duration: 0.1, ease: 'power3.out', immediateRender: false }, t0);
        if (c.big && w.cls === 'k') tl.fromTo(sp[i], { scale: 1.5 }, { scale: 1.12, duration: 0.14, ease: 'power4.out', immediateRender: false }, t0 + 0.001);
      });
    } else {
      tl.fromTo(el, { y: 20, scale: c.first ? 0.88 : 0.94, opacity: 0 }, { y: 0, scale: 1, opacity: 1, duration: 0.16, ease: 'back.out(2.2)', immediateRender: false }, T(c.s));
      let tilt = -3.5;
      c.w.forEach((w, i) => {
        if (w.cls === 'n') return;
        if (w.cls === 'e') { gs.set(sp[i], { rotation: tilt }); tilt = -tilt * 0.8; }
        const t0 = Math.max(T(c.s) + 0.05, T(w.s));
        tl.fromTo(sp[i], { scale: 0.7 }, { scale: c.big ? 1.3 : 1.13, duration: 0.12, ease: 'power2.out', immediateRender: false }, t0);
        tl.to(sp[i], { scale: 1.0, duration: 0.22, ease: 'back.out(2)' }, t0 + 0.12);
      });
    }
  });
})();

/* ---------------- cards / slams / stock ---------------- */
function card(c, html, css) {
  const el = mk('uc ' + c.kind, css || '', null, html);
  gs.set(el, { autoAlpha: 0 });
  const from = P.band === 'top' ? { y: -70, scale: 0.94, opacity: 0 } : { y: 70, scale: 0.94, opacity: 0 };
  tl.set(el, { autoAlpha: 1 }, T(c.t));
  tl.fromTo(el, from, { y: 0, scale: 1, opacity: 1, duration: 0.3, ease: 'back.out(2)', immediateRender: false }, T(c.t));
  tl.to(el, { y: P.band === 'top' ? -60 : 60, scale: 0.96, opacity: 0, duration: 0.22, ease: 'power2.in' }, T(c.e) - 0.22);
  tl.set(el, { autoAlpha: 0 }, T(c.e));
  return el;
}
const q = (el, s) => el.querySelector(s);
const CHECK = col => `<svg viewBox="0 0 60 60"><circle cx="30" cy="30" r="27" fill="none" stroke="${col}" stroke-width="5"/><path class="ck" d="M16 31 L26 41 L45 19" fill="none" stroke="${col}" stroke-width="7" stroke-linecap="round" stroke-linejoin="round" pathLength="1" stroke-dasharray="1" stroke-dashoffset="1"/></svg>`;
const CROSS = col => `<svg viewBox="0 0 60 60"><circle cx="30" cy="30" r="27" fill="none" stroke="${col}" stroke-width="5"/><path class="ck" d="M19 19 L41 41 M41 19 L19 41" fill="none" stroke="${col}" stroke-width="7" stroke-linecap="round" pathLength="1" stroke-dasharray="1" stroke-dashoffset="1"/></svg>`;
const draw = (el, t) => tl.fromTo(el.querySelector('.ck'), { strokeDashoffset: 1 }, { strokeDashoffset: 0, duration: 0.28, ease: 'power2.out', immediateRender: false }, T(t));

P.cards.forEach(c => {
  if (!here(c.t, c.e)) return;
  const dur = c.e - c.t;
  /* full-frame stock: zoom-through in and out, hard cut at the end */
  if (c.kind === 'stock') {
    const box = $('sb' + c.n);
    gs.set(box, { autoAlpha: 0 });
    tl.set(box, { autoAlpha: 1 }, T(c.t));
    tl.set(box, { autoAlpha: 0 }, T(c.e));
    if (c.in === 'whip') tl.fromTo(box, { x: 760, scale: 1.12 }, { x: 0, scale: 1, duration: 0.14, ease: 'power4.out', immediateRender: false }, T(c.t));
    else tl.fromTo(box, { scale: 1.4 }, { scale: 1, duration: 0.24, ease: 'power3.out', immediateRender: false }, T(c.t));
    tl.fromTo(box, { scale: 1 }, { scale: 1.2, duration: 0.2, ease: 'power2.in', immediateRender: false }, T(c.e) - 0.2);
    tl.to(box, { scale: 1.02, duration: Math.max(0.1, dur - 0.45), ease: 'none' }, T(c.t) + 0.26);
    if (c.out === 'flash') flash(c.e - 0.02, 0.55);
  }
  /* thin voice waveform: 90 hard bars */
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
    const drawBars = () => {
      const p = prox.p;
      for (let i = 0; i < N; i++) {
        const u = i / (N - 1), env = Math.sin(Math.PI * u) ** 0.8;
        const w = Math.abs(Math.sin(p * 31 + i * 1.9) * Math.cos(p * 17 - i * 0.7)) * 0.75 + 0.25 * Math.abs(Math.sin(p * 53 + i * 3.1));
        const grow = Math.min(1, p * dur / 0.15), fade = Math.min(1, (1 - p) * dur / 0.2);
        const h = Math.max(4, 150 * env * w * grow * fade);
        bars[i].style.height = h + 'px'; bars[i].style.top = (CY - h / 2) + 'px';
      }
    };
    tl.fromTo(prox, { p: 0 }, { p: 1, duration: dur, ease: 'none', onUpdate: drawBars, immediateRender: false }, T(c.t));
    flash(c.t, 0.4);
  }
  /* giant word slammed mid-frame */
  if (c.kind === 'punch') {
    const Y = 1330;
    const tx = mk('punch', `top:${Y}px;font-size:${c.size || 230}px`, null, `<span>${esc(c.text)}</span>`);
    gs.set(tx, { yPercent: -50, autoAlpha: 0 });
    tl.set(tx, { autoAlpha: 1 }, T(c.t)); tl.set(tx, { autoAlpha: 0 }, T(c.e));
    tl.fromTo(tx, { scale: 1.6 }, { scale: 1, duration: 0.12, ease: 'power4.out', immediateRender: false }, T(c.t));
    tl.to(tx, { scale: 1.04, duration: Math.max(0.1, dur - 0.15), ease: 'none' }, T(c.t) + 0.14);
    [Y - 135, Y + 135].forEach((y, k) => {
      const r = mk('rule pr', `left:210px;top:${y}px;width:660px`, null, '');
      gs.set(r, { autoAlpha: 0, scaleX: 0 });
      tl.set(r, { autoAlpha: 1 }, T(c.t)); tl.set(r, { autoAlpha: 0 }, T(c.e));
      tl.fromTo(r, { scaleX: 0 }, { scaleX: 1, duration: 0.2, ease: 'power4.out', immediateRender: false }, T(c.t) + 0.04 + k * 0.05);
    });
  }
  /* rubber-stamp slam, tilted */
  if (c.kind === 'stamp') {
    const st = mk('stamp', `top:1330px;font-size:${c.size || 150}px`, null, `<span>${esc(c.text)}</span>`);
    gs.set(st, { xPercent: -50, yPercent: -50, autoAlpha: 0, rotation: -7 });
    tl.set(st, { autoAlpha: 1 }, T(c.t)); tl.set(st, { autoAlpha: 0 }, T(c.e));
    tl.fromTo(st, { scale: 2.1, opacity: 0 }, { scale: 1, opacity: 1, duration: 0.1, ease: 'power4.in', immediateRender: false }, T(c.t));
    tl.fromTo(st, { scale: 1.07 }, { scale: 1, duration: 0.18, ease: 'power3.out', immediateRender: false }, T(c.t) + 0.1);
  }
  /* counter */
  if (c.kind === 'stat') {
    const el = card(c, `<div class="lab">${esc(c.label || '')}</div><div class="s-row"><span class="pre">${esc(c.prefix || '')}</span><span class="num">0</span><span class="suf">${esc(c.suffix || '')}</span></div><div class="s-bar"></div>`);
    const num = q(el, '.num'), o = { v: 0 }, dec = Math.round(c.value) !== c.value;
    tl.to(o, { v: c.value, duration: Math.min(1.0, dur - 0.7), ease: 'power2.out', onUpdate: () => { num.textContent = dec ? o.v.toFixed(1) : thin(o.v); } }, T(c.t) + 0.2);
    tl.to(q(el, '.s-bar'), { width: 860, duration: Math.min(1.0, dur - 0.7), ease: 'power2.out' }, T(c.t) + 0.2);
    tl.fromTo(q(el, '.s-row'), { scale: 1 }, { scale: 1.05, duration: 0.14, yoyo: true, repeat: 1, transformOrigin: '0% 50%', immediateRender: false }, T(c.t) + 0.2 + Math.min(1.0, dur - 0.7));
  }
  /* bad vs good */
  if (c.kind === 'compare') {
    const el = card(c, `<div class="lab">Что лучше?</div><div class="row r1">${CROSS('var(--bad)')}<span>${esc(c.left)}</span><i class="strike"></i></div><div class="row r2">${CHECK('var(--onacc)')}<span>${esc(c.right)}</span></div>`);
    const r1 = q(el, '.r1'), r2 = q(el, '.r2');
    gs.set([r1, r2], { autoAlpha: 0 });
    tl.fromTo(r1, { autoAlpha: 0, x: -60 }, { autoAlpha: 1, x: 0, duration: 0.28, ease: 'back.out(1.8)', immediateRender: false }, T(c.t) + 0.2);
    draw(r1, c.t + 0.35);
    tl.fromTo(q(el, '.strike'), { width: 0 }, { width: 380, duration: 0.3, ease: 'power2.out', immediateRender: false }, T(c.t) + 0.8);
    tl.fromTo(r2, { autoAlpha: 0, x: 60 }, { autoAlpha: 1, x: 0, duration: 0.28, ease: 'back.out(1.8)', immediateRender: false }, T(c.t) + 1.5);
    draw(r2, c.t + 1.75);
  }
  /* ticking list */
  if (c.kind === 'checklist') {
    const its = c.items || [];
    const el = card(c, `<div class="lab">Чек-лист</div>` + its.map((s, i) => `<div class="li" style="top:${50 + i * 54}px">${CHECK('var(--acc)')}<span>${esc(s)}</span></div>`).join(''));
    el.querySelectorAll('.li').forEach((li, i) => {
      gs.set(li, { autoAlpha: 0 });
      const t0 = c.t + 0.3 + i * (dur - 0.9) / Math.max(1, its.length);
      tl.fromTo(li, { autoAlpha: 0, x: -50 }, { autoAlpha: 1, x: 0, duration: 0.22, ease: 'back.out(1.8)', immediateRender: false }, T(t0));
      draw(li, t0 + 0.12);
    });
  }
  /* notification */
  if (c.kind === 'notify') {
    const el = card(c, `<div class="av">${esc((c.title || ' ').trim().charAt(0).toUpperCase())}</div><div class="n-t1">${esc(c.title)}</div><div class="n-t2">${esc(c.text)}</div>`);
    tl.fromTo(q(el, '.av'), { scale: 1 }, { scale: 1.1, duration: 0.18, yoyo: true, repeat: 1, ease: 'sine.inOut', immediateRender: false }, T(c.t) + 0.3);
  }
});

/* ---------------- wildcard ---------------- */
(function wildcard() {
  if (!WC.type || !here(WC.window[0], WC.window[1])) return;
  const t = WC.t, e = WC.e;
  if (WC.type === 'blackout_open') {
    const b = $('blk');
    tl.set(b, { opacity: 1 }, 0);
    tl.set(b, { opacity: 0 }, T(e));
    flash(e, 0.5);
  }
  if (WC.type === 'negative_flash') {
    tl.set(SNAP, { filter: 'invert(1) contrast(1.25)' }, T(t));
    tl.set(SNAP, { filter: 'none' }, T(t) + 0.1);
  }
  if (WC.type === 'letterbox') {
    const top = $('lb1'), bot = $('lb2');
    gs.set(top, { y: -170 }); gs.set(bot, { y: 170 });
    tl.fromTo(top, { y: -170 }, { y: 0, duration: 0.3, ease: 'power3.out', immediateRender: false }, T(t));
    tl.fromTo(bot, { y: 170 }, { y: 0, duration: 0.3, ease: 'power3.out', immediateRender: false }, T(t));
    tl.to(top, { y: -170, duration: 0.25, ease: 'power2.in' }, T(e) - 0.25);
    tl.to(bot, { y: 170, duration: 0.25, ease: 'power2.in' }, T(e) - 0.25);
  }
  if (WC.type === 'echo_caption') {
    for (let k = 0; k < 3; k++) {
      const ec = mk('echo', `top:${P.capY - 330}px;font-size:${190 + k * 34}px`, null, esc(WC.text));
      gs.set(ec, { xPercent: -50, yPercent: -50, autoAlpha: 0 });
      const t0 = T(t) + k * 0.18;
      tl.set(ec, { autoAlpha: 1 }, t0);
      tl.fromTo(ec, { scale: 0.8, opacity: 0.75 - k * 0.15 }, { scale: 1.12, opacity: 0, duration: 0.5, ease: 'power2.out', immediateRender: false }, t0);
      tl.set(ec, { autoAlpha: 0 }, t0 + 0.52);
    }
  }
  if (WC.type === 'silence_gag') flash(t, 0.35);
  if (WC.type === 'sound_gag') flash(t, 0.18);
})();

window.__timelines = window.__timelines || {};
window.__timelines['main'] = tl;

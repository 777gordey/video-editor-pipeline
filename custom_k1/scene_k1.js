/* scene_k1.js — clip K1, direction C: my real room is the ONLY video layer. Hook, captions and UI cards are overlays (cards sit in the top band, captions below the chin).
   Everything is a pure function of timeline time (GSAP tweens; fromTo with immediateRender:false; counters via onUpdate). */
const P = window.PLAN, OFF = P.off, DUR = P.dur, gs = window.gsap;
const tl = gs.timeline({ paused: true });
const T = t => Math.max(0, t - OFF);
const here = (a, b) => b > OFF + 0.001 && a < OFF + DUR - 0.001;
const $ = id => document.getElementById(id);
const SNAP = $('snap'), CAM = $('cam');
const AMB = '#FFC53D', RED = '#FF5C5C', GRN = '#4FD88B';

function mk(cls, css, parent, html, tag) {
  const e = document.createElement(tag || 'div');
  if (cls) e.className = cls;
  if (css) e.style.cssText = css;
  if (html != null) e.innerHTML = html;
  (parent || $('over')).appendChild(e);
  return e;
}
const at = (t, f) => { if (here(t, t + 0.01)) f(T(t)); };

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

/* ---------------- hits: short shake + zoom punch (origin = top edge, so the head is never pushed out of frame) ---------------- */
(P.hits || []).forEach(([t, amp, punch]) => {
  if (!here(t, t + 0.3)) return;
  const s = T(t), f = 1 / 30;
  const pts = [[0, 0], [1, -0.6], [-0.8, 0.7], [0.5, -0.4], [-0.25, 0.2], [0, 0]];
  for (let i = 0; i < pts.length - 1; i++)
    tl.fromTo(SNAP, { x: pts[i][0] * amp, y: pts[i][1] * amp }, { x: pts[i + 1][0] * amp, y: pts[i + 1][1] * amp, duration: f, ease: 'none', immediateRender: false }, s + i * f);
  if (punch > 0) tl.fromTo(SNAP, { scale: 1 + punch }, { scale: 1, duration: 0.3, ease: 'power3.out', immediateRender: false }, s);
});

/* ---------------- hook: label -> big words -> UI tag ---------------- */
(function hook() {
  const H = P.hook;
  if (!H || !here(H.t0, H.t1)) return;
  H.lines.forEach((l, i) => {
    const html = l.cls === 'h3' ? `<span class="tag">${l.text}</span><span class="caret"></span>` : l.text;
    const el = mk('hk ' + l.cls, `left:540px;top:${l.y}px;font-size:${l.size}px`, null, html);
    gs.set(el, { xPercent: -50, yPercent: -50, autoAlpha: 0 });
    tl.set(el, { autoAlpha: 1 }, T(l.t));
    if (l.cls === 'h1') tl.fromTo(el, { scale: 1.45, rotation: -7 }, { scale: 1, rotation: -3, duration: 0.26, ease: 'back.out(3)', immediateRender: false }, T(l.t));
    if (l.cls === 'h2') tl.fromTo(el, { scale: 1.7, y: -26 }, { scale: 1, y: 0, duration: 0.24, ease: 'power4.out', immediateRender: false }, T(l.t));
    if (l.cls === 'h3') {
      tl.fromTo(el, { y: -150, scale: 0.9 }, { y: 0, scale: 1, duration: 0.3, ease: 'bounce.out', immediateRender: false }, T(l.t));
      const cr = el.querySelector('.caret');
      for (let k = 0; k < 4; k++) tl.set(cr, { opacity: k % 2 ? 1 : 0 }, T(l.t) + 0.35 + k * 0.28);
    }
    tl.to(el, { opacity: 0, y: '+=60', duration: 0.22, ease: 'power2.in' }, T(H.exit) + i * 0.03);
    tl.set(el, { autoAlpha: 0 }, T(H.t1) + 0.02);
  });
})();

/* ---------------- captions ---------------- */
(function captions() {
  const box = $('over');
  P.caps.forEach(c => {
    if (!here(c.s, c.e)) return;
    const el = mk('cap' + (c.big ? ' big' : ''), `top:${P.capY}px;font-size:${c.size}px`, box,
      c.w.map(w => `<span class="w ${w.cls}${w.col ? ' c-' + w.col : ''}">${w.t}</span>`).join(' '));
    gs.set(el, { yPercent: -50 });
    tl.set(el, { autoAlpha: 1 }, T(c.s) - 0.001);
    tl.set(el, { autoAlpha: 0 }, T(c.e));
    tl.fromTo(el, { y: 20, scale: c.first ? 0.88 : 0.94, opacity: 0 }, { y: 0, scale: 1, opacity: 1, duration: 0.16, ease: 'back.out(2.2)', immediateRender: false }, T(c.s));
    const sp = el.querySelectorAll('.w');
    let tilt = -3.5;
    c.w.forEach((w, i) => {
      if (w.cls === 'n') return;
      if (w.cls === 'e') { gs.set(sp[i], { rotation: tilt }); tilt = -tilt * 0.8; }
      const t0 = Math.max(T(c.s) + 0.05, T(w.s));
      tl.fromTo(sp[i], { scale: 0.7 }, { scale: w.cls === 'k' ? 1.14 : 1.12, duration: 0.12, ease: 'power2.out', immediateRender: false }, t0);
      tl.to(sp[i], { scale: 1.0, duration: 0.22, ease: 'back.out(2)' }, t0 + 0.12);
    });
  });
})();

/* ---------------- UI cards ---------------- */
const CARD = {};
function card(n, t, e, html, css) {
  if (!here(t, e)) return null;
  const el = mk('uc', css || '', null, html);
  gs.set(el, { autoAlpha: 0 });
  tl.set(el, { autoAlpha: 1 }, T(t));
  tl.fromTo(el, { y: -70, scale: 0.94, opacity: 0 }, { y: 0, scale: 1, opacity: 1, duration: 0.3, ease: 'back.out(2)', immediateRender: false }, T(t));
  tl.to(el, { y: -60, scale: 0.96, opacity: 0, duration: 0.22, ease: 'power2.in' }, T(e) - 0.22);
  tl.set(el, { autoAlpha: 0 }, T(e));
  CARD[n] = el;
  return el;
}
const q = (el, s) => el.querySelector(s);
function counter(obj, t0, t1, to, fn, ease) {
  tl.to(obj, { v: to, duration: t1 - t0, ease: ease || 'power1.out', onUpdate: () => fn(obj.v) }, T(t0));
}
const pad = n => String(n).padStart(2, '0');
const thin = n => String(Math.round(n)).replace(/\B(?=(\d{3})+(?!\d))/g, ' ');
function tick(el, path, t) { // draws an SVG stroke
  tl.fromTo(el.querySelector(path), { strokeDashoffset: 1 }, { strokeDashoffset: 0, duration: 0.28, ease: 'power2.out', immediateRender: false }, T(t));
}
const CHECK = col => `<svg viewBox="0 0 60 60"><circle cx="30" cy="30" r="27" fill="none" stroke="${col}" stroke-width="5"/><path class="ck" d="M16 31 L26 41 L45 19" fill="none" stroke="${col}" stroke-width="7" stroke-linecap="round" stroke-linejoin="round" pathLength="1" stroke-dasharray="1" stroke-dashoffset="1"/></svg>`;
const CROSS = col => `<svg viewBox="0 0 60 60"><circle cx="30" cy="30" r="27" fill="none" stroke="${col}" stroke-width="5"/><path class="ck" d="M19 19 L41 41 M41 19 L19 41" fill="none" stroke="${col}" stroke-width="7" stroke-linecap="round" pathLength="1" stroke-dasharray="1" stroke-dashoffset="1"/></svg>`;

P.cards.forEach(c => {
  /* 1. incoming call: the agent picks up and greets */
  if (c.kind === 'call') {
    const el = card(1, c.t, c.e, `<div class="av">П</div><div class="c-t1">ПроДент · клиника</div>
      <div class="c-t2"><i class="dot"></i><span class="st">входящий звонок</span> <b class="tm" style="color:#fff">00:00</b></div>
      <div class="bars">${[0, 1, 2, 3, 4].map(i => `<i style="left:${i * 37}px"></i>`).join('')}</div>`);
    if (!el) return;
    const st = q(el, '.st'), tm = q(el, '.tm'), bars = el.querySelectorAll('.bars i');
    const o = { v: 0 }, T0 = 3.78;
    tl.set(q(el, '.dot'), { backgroundColor: AMB }, T(c.t));
    tl.fromTo(q(el, '.av'), { scale: 1 }, { scale: 1.08, duration: 0.2, yoyo: true, repeat: 1, ease: 'sine.inOut', immediateRender: false }, T(c.t) + 0.2);
    tl.set(q(el, '.dot'), { backgroundColor: GRN }, T(T0));
    tl.to(o, { v: 1, duration: c.e - T0 - 0.2, ease: 'none', onUpdate: () => {
      const now = tl.time() + OFF;
      if (now >= T0) { st.textContent = 'идёт звонок'; const s = Math.max(0, Math.floor(now - T0)); tm.textContent = '00:' + pad(s); }
      else { st.textContent = 'входящий звонок'; tm.textContent = '00:00'; }
      bars.forEach((b, i) => { b.style.height = (now >= T0 ? 30 + 110 * Math.abs(Math.sin(now * (5.2 + i * 1.7) + i * 1.3)) * (0.55 + 0.45 * Math.sin(now * 1.3 + i)) : 30) + 'px'; });
    } }, T(T0));
  }
  /* 2. price counter */
  if (c.kind === 'price') {
    const el = card(2, c.t, c.e, `<div class="lab p-lab">Профессиональная гигиена</div><div class="p-row"><small>от</small><span class="num">0</span>&nbsp;₽</div><div class="p-bar"></div>`);
    if (!el) return;
    const num = q(el, '.num'), o = { v: 0 };
    counter(o, 16.12, 16.96, 4000, v => { num.textContent = thin(v); }, 'power2.out');
    tl.to(q(el, '.p-bar'), { width: 860, duration: 0.84, ease: 'power2.out' }, T(16.12));
    tl.fromTo(q(el, '.p-row'), { scale: 1 }, { scale: 1.05, duration: 0.14, yoyo: true, repeat: 1, transformOrigin: '0% 50%', immediateRender: false }, T(16.96));
  }
  /* 3. day -> time pick */
  if (c.kind === 'pick') {
    const days = ['пн', 'вт', 'ср', 'чт', 'пт', 'сб', 'вс'];
    const el = card(3, c.t, c.e, `<div class="pk p1"><div class="lab">Запись · день</div><div class="days">${days.map(d => `<i>${d}</i>`).join('')}</div></div>
      <div class="pk p2"><div class="lab">Запись · время</div><div class="btns"><i class="m">УТРОМ</i><i class="v">ВЕЧЕРОМ</i></div></div>`);
    if (!el) return;
    gs.set(q(el, '.p2'), { autoAlpha: 0, y: 40 });
    const chips = el.querySelectorAll('.days i');
    chips.forEach((ch, i) => tl.fromTo(ch, { y: 24, opacity: 0 }, { y: 0, opacity: 1, duration: 0.2, ease: 'power2.out', immediateRender: false }, T(c.t) + 0.12 + i * 0.04));
    tl.set(chips[6], { backgroundColor: AMB, color: '#15110A' }, T(21.12));
    tl.fromTo(chips[6], { scale: 0.8 }, { scale: 1.12, duration: 0.14, ease: 'power2.out', immediateRender: false }, T(21.12));
    tl.to(chips[6], { scale: 1, duration: 0.2, ease: 'back.out(2)' }, T(21.26));
    tl.to(q(el, '.p1'), { autoAlpha: 0, y: -40, duration: 0.2 }, T(24.6));
    tl.to(q(el, '.p2'), { autoAlpha: 1, y: 0, duration: 0.26, ease: 'back.out(1.6)' }, T(24.72));
    tl.set(q(el, '.m'), { backgroundColor: AMB, color: '#15110A' }, T(26.7));
    tl.set(q(el, '.v'), { opacity: 0.35 }, T(26.72));
    tl.fromTo(q(el, '.m'), { scale: 0.92 }, { scale: 1.05, duration: 0.14, ease: 'power2.out', immediateRender: false }, T(26.7));
    tl.to(q(el, '.m'), { scale: 1, duration: 0.2, ease: 'back.out(2)' }, T(26.84));
  }
  /* 4. THE JOKE: 9:00 -> 6:00 -> "clinic not open yet" -> 8:00 -> booked */
  if (c.kind === 'wheel') {
    const el = card(4, c.t, c.e, `<div class="lab w-lab">Время приёма</div><div class="w-time">09:00</div>
      <div class="w-st"><div class="a w-closed">КЛИНИКА ЕЩЁ<br>НЕ РАБОТАЕТ</div><div class="a w-open">открываемся в 8:00</div><div class="a w-ok">${CHECK(GRN)}<span>ЗАПИСАНО</span></div></div>`);
    if (!el) return;
    const tm = q(el, '.w-time'), o = { m: 9 * 60 };
    const show = m => { tm.textContent = pad(Math.floor(m / 60)) + ':' + pad(m % 60); };
    tl.fromTo(tm, { scale: 0.85, opacity: 0.3 }, { scale: 1, opacity: 1, duration: 0.22, ease: 'back.out(2.4)', transformOrigin: '0% 50%', immediateRender: false }, T(32.7));
    // 36.95-37.55 the wheel rolls back to 6:00 (alarm), card turns red and shakes
    tl.to(o, { m: 6 * 60, duration: 0.55, ease: 'steps(6)', onUpdate: () => show(Math.round(o.m / 30) * 30) }, T(36.95));
    tl.to(el, { borderColor: RED, duration: 0.15 }, T(37.55));
    tl.to(tm, { color: RED, duration: 0.15 }, T(37.55));
    for (let k = 0; k < 6; k++) tl.fromTo(el, { x: k % 2 ? 9 : -9 }, { x: 0, duration: 0.07, ease: 'none', immediateRender: false }, T(37.62) + k * 0.075);
    tl.fromTo(q(el, '.w-closed'), { autoAlpha: 0, scale: 0.7, y: 30 }, { autoAlpha: 1, scale: 1, y: 0, duration: 0.3, ease: 'back.out(2.2)', immediateRender: false }, T(40.24));
    tl.fromTo(q(el, '.w-open'), { autoAlpha: 0, y: 14 }, { autoAlpha: 1, y: 0, duration: 0.25, immediateRender: false }, T(41.5));
    // 42.9-43.4 the wheel rolls forward to 8:00
    tl.to(o, { m: 8 * 60, duration: 0.45, ease: 'steps(4)', onUpdate: () => show(Math.round(o.m / 30) * 30) }, T(42.92));
    // 43.94 "Идеально": green, booked
    tl.to(el, { borderColor: GRN, duration: 0.2 }, T(43.94));
    tl.to(tm, { color: GRN, duration: 0.2 }, T(43.94));
    tl.to([q(el, '.w-closed'), q(el, '.w-open')], { autoAlpha: 0, duration: 0.15 }, T(43.9));
    tl.fromTo(q(el, '.w-ok'), { autoAlpha: 0, scale: 0.6 }, { autoAlpha: 1, scale: 1, duration: 0.3, ease: 'back.out(2.4)', immediateRender: false }, T(44.0));
    tick(q(el, '.w-ok'), '.ck', 44.05);
  }
  /* 5. proof: ignored vs answered and booked */
  if (c.kind === 'compare') {
    const el = card(5, c.t, c.e, `<div class="lab cmp-h">Что лучше?</div>
      <div class="row r1">${CROSS(RED)}<span>проигнорировали</span><i class="strike"></i></div>
      <div class="row r2">${CHECK('#15110A')}<span>ответили и записали</span></div>`);
    if (!el) return;
    const r1 = q(el, '.r1'), r2 = q(el, '.r2');
    gs.set([r1, r2], { autoAlpha: 0 });
    tl.fromTo(r1, { autoAlpha: 0, x: -60 }, { autoAlpha: 1, x: 0, duration: 0.28, ease: 'back.out(1.8)', immediateRender: false }, T(52.45));
    tick(r1, '.ck', 52.6);
    tl.fromTo(q(el, '.strike'), { width: 0 }, { width: 380, duration: 0.3, ease: 'power2.out', immediateRender: false }, T(52.9));
    tl.fromTo(r2, { autoAlpha: 0, x: 60 }, { autoAlpha: 1, x: 0, duration: 0.28, ease: 'back.out(1.8)', immediateRender: false }, T(53.66));
    tick(r2, '.ck', 53.95);
  }
});

window.__timelines = window.__timelines || {};
window.__timelines['main'] = tl;

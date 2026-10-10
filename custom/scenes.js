/* scenes.js — one function per sentence. All times are GLOBAL seconds of the clip. */
const B = $('behind'), F = $('front');
const S = (a, b, fn) => { if (here(a, b)) fn(a, b); };

ambient([
  [0, '#1ec8b0', '#2a63ff', '#12a79a'], [9.5, '#7a5cff', '#1ec8b0', '#3a7bff'], [16.3, '#ffb02e', '#1ec8b0', '#ff7a3a'],
  [23.3, '#ff5a8a', '#7a5cff', '#ffb02e'], [27.7, '#2a63ff', '#ffb02e', '#1ec8b0'], [31.4, '#ffb02e', '#ff7a3a', '#ffd45a'],
  [35.3, '#1ec8b0', '#2a63ff', '#7a5cff'], [41.7, '#ff4a62', '#7a5cff', '#ff7a3a'], [48.0, '#1ec8b0', '#2a63ff', '#12a79a'],
  [52.4, '#3CF0C8', '#1ec8b0', '#2a63ff'], [55.3, '#2a63ff', '#7a5cff', '#1ec8b0'], [58.1, '#ff4a62', '#3CF0C8', '#7a5cff'],
  [67.9, '#3CF0C8', '#ffc94d', '#2a63ff'],
]);

/* ---- giant outlined words in the background (one per idea) ---- */
function bgword(text, a, b, y, tilt = -8, size = 300) {
  if (!here(a, b)) return;
  const w = mk('', `left:540px;top:${y}px;font-family:Unbounded;font-weight:900;font-size:${size}px;line-height:1;white-space:nowrap;color:rgba(60,240,200,.035);-webkit-text-stroke:3px rgba(140,235,255,.30);transform:translate(-50%,-50%) rotate(${tilt}deg)`, $('bgLayer'), text);
  life(w, a, b);
  tl.fromTo(w, { x: 160, opacity: 0 }, { x: -160, opacity: 1, duration: T(b) - T(a), ease: 'none', immediateRender: false }, T(a));
  tl.to(w, { opacity: 0, duration: 0.25 }, T(b) - 0.25);
}
bgword('ПРОДЕНТ', 4.5, 9.4, 560); bgword('ЧИСТКА', 9.6, 16.1, 1000, 6); bgword('ГИГИЕНА', 16.4, 19.1, 700, -6, 270);
bgword('ВОСКРЕСЕНЬЕ', 23.4, 27.4, 1050, 7, 190); bgword('ВРЕМЯ', 27.8, 31.2, 1100, -7, 340); bgword('ПОЗДНО', 41.8, 47.9, 1000, -7, 300);
bgword('РАБОТАЕМ', 48.1, 52.3, 1000, 7, 230); bgword('ТЕЛЕФОН', 55.4, 58.0, 1050, -6, 250); bgword('ВЫБОР', 58.2, 67.8, 1060, -8, 330);

/* ---- camera: slow push-ins that follow each sentence (scale0, scale1, x, y) ---- */
camera([
  [0, 4.4, 1.14, 1.03, 0, 30], [4.4, 9.5, 1.0, 1.07, 0, 0], [9.5, 16.3, 1.06, 1.0, -14, 0], [16.3, 19.2, 1.0, 1.08, 0, 10],
  [19.2, 23.3, 1.0, 1.04, 0, 0], [23.3, 27.7, 1.08, 1.0, 12, 0], [27.7, 31.4, 1.0, 1.07, 0, 0], [31.4, 35.3, 1.1, 1.02, -10, 14],
  [35.3, 41.7, 1.0, 1.06, 0, 0], [41.7, 48.0, 1.08, 1.0, 10, 0], [48.0, 52.4, 1.0, 1.08, -12, 0], [52.4, 55.3, 1.1, 1.04, 0, 0],
  [55.3, 58.1, 1.0, 1.07, 0, 0], [58.1, 62.5, 1.0, 1.14, 0, 20], [62.5, 67.9, 1.1, 1.02, 0, 0], [67.9, 72.1, 1.0, 1.08, 0, 14],
]);

/* ====== S1 · 0.0–4.4  «…красотку, которая отвечает круглые сутки. Смотри!» ====== */
S(0, 4.4, () => {
  const blk = mk('', 'left:0;top:0;width:1080px;height:1920px;background:#000', FX);
  tl.fromTo(blk, { opacity: 1 }, { opacity: 0, duration: 0.4, ease: 'power1.out' }, 0);
  // AI orb pops beside me at «красотку»
  const o = orb(F, 868, 470, 250); life(o, 1.6, 3.2);
  tl.fromTo(o, { scale: 0, rotation: -40 }, { scale: 1, rotation: 0, duration: 0.6, ease: 'elastic.out(1,.55)' }, T(1.6));
  tl.to(o, { y: -18, duration: 0.8, ease: 'sine.inOut', yoyo: true, repeat: 1 }, T(1.9));
  ring(F, 868, 470, 250, 1.65, '#3CF0C8'); ring(F, 868, 470, 250, 2.05, '#3CF0C8', 1.1);
  const e = eq(o, 5, { x: 125, y: 125, w: 20, h: 110, gap: 14, color: '#04101c', t0: 1.9, t1: 3.2, spans: [[1.9, 3.7]] });
  tl.to(o, { scale: 0, rotation: 60, duration: 0.3, ease: 'back.in(2)' }, T(3.0));
  // «круглые сутки» — dial spins a full day behind me
  const c = clock(B, 540, 760, 940, { numSize: 28 }); life(c.n, 3.05, 4.45);
  tl.fromTo(c.n, { scale: 0.5, rotation: -90 }, { scale: 1, rotation: 0, duration: 0.55, ease: 'back.out(1.5)' }, T(3.05));
  tl.fromTo(c.min, { rotation: 0 }, { rotation: 1440, duration: 1.3, ease: 'power2.inOut' }, T(3.05));
  tl.fromTo(c.hour, { rotation: 0 }, { rotation: 120, duration: 1.3, ease: 'power2.inOut' }, T(3.05));
  // huge metallic 24/7 in front
  const k = x3('24/7', { x: 540, y: 1170, size: 300, depth: 22, cls: 'mint', parent: F, ls: -6, tf: 'rotate(-4deg)' }); life(k, 3.32, 4.5);
  x3in(k, 3.32, { st: 0.055 }); x3shine(k, 3.75); x3out(k, 4.18);
  punch(3.34, 1.1); ring(F, 540, 1170, 500, 3.4, '#3CF0C8', 0.8);
});

/* ====== S2 · 4.4–9.5  AI: «Здравствуйте. Клиника ПроДент. Меня зовут Милана.» ====== */
let HUD = null;
function hud() {
  const w = mk('', 'left:70px;top:64px;width:940px;height:196px', F);
  mk('card', 'left:0;top:0;width:940px;height:196px;border-radius:56px', w);
  const av = mk('', 'left:24px;top:24px;width:148px;height:148px;border-radius:50%;background:radial-gradient(circle at 35% 30%,#fff,#bff9ec 25%,#3CF0C8 65%,#0b8f8a);box-shadow:0 0 36px rgba(60,240,200,.6)', w);
  tooth(av, 74, 76, 92);
  mk('', 'left:196px;top:30px;width:520px;font-weight:800;font-size:48px;line-height:1.05;white-space:nowrap', w, 'Милана · <span style="color:#3CF0C8">ПроДент</span>');
  const tm = mk('', 'left:196px;top:104px;width:520px;font-weight:700;font-size:34px;color:rgba(255,255,255,.75);white-space:nowrap', w, 'AI-администратор · <span class="tm">00:00</span>');
  mk('', 'left:745px;top:34px;font-weight:800;font-size:22px;letter-spacing:.12em;color:#3CF0C8', w, 'ИИ');
  mk('', 'left:845px;top:34px;font-weight:800;font-size:22px;letter-spacing:.12em;color:#fff', w, 'ВЫ');
  w._tm = tm.querySelector('.tm');
  return w;
}
S(4.4, 9.5, () => {
  HUD = hud(); life(HUD, 4.45, 58.0);
  tl.fromTo(HUD, { y: 380, rotationX: 55, scale: 0.7, transformPerspective: 900 }, { y: 0, rotationX: 0, scale: 1, duration: 0.7, ease: 'back.out(1.5)' }, T(4.45));
  // call timer follows the clip clock
  const o = { t: 0 };
  tl.fromTo(o, { t: 0 }, { t: 55, duration: Math.min(DUR, 58 - 4.45), ease: 'none', onUpdate: () => {
    const s = Math.floor(o.t + Math.max(0, OFF - 4.45) * 0 + (OFF > 4.45 ? OFF - 4.45 : 0)), m = String(Math.floor(s / 60)).padStart(2, '0'), ss = String(s % 60).padStart(2, '0');
    HUD._tm.textContent = m + ':' + ss; } }, T(4.45));
  eq(HUD, 5, { x: 765, y: 120, w: 14, h: 70, gap: 9, color: '#3CF0C8', t0: Math.max(4.45, OFF), t1: Math.min(58, OFF + DUR), spans: AI });
  eq(HUD, 5, { x: 868, y: 120, w: 14, h: 70, gap: 9, color: '#ffffff', t0: Math.max(4.45, OFF), t1: Math.min(58, OFF + DUR), spans: USER });
});
S(4.4, 9.5, () => {
  // sound rings behind my head while the AI speaks + big tooth badge on «ПроДент»
  [4.7, 5.3, 6.9, 7.8, 8.5].forEach((t, i) => ring(B, 540, 760, 620, t, i % 2 ? '#7fffe6' : '#3CF0C8', 1.2, 5));
  const t1 = tooth(B, 540, 770, 640); life(t1, 5.15, 8.4);
  tl.fromTo(t1, { scale: 0, rotation: -25 }, { scale: 1, rotation: 0, duration: 0.6, ease: 'elastic.out(1,.6)' }, T(5.15));
  tl.to(t1, { scale: 1.06, duration: 0.8, ease: 'sine.inOut', yoyo: true, repeat: 1 }, T(6.0));
  tl.to(t1, { scale: 0, y: -200, rotation: 25, duration: 0.3, ease: 'back.in(2)' }, T(8.1));
});

/* ====== S3 · 9.5–16.3  user: «Привет, Миланочка. Меня зовут Гордей. Я бы хотел на чистку.» ====== */
S(9.5, 16.3, () => {
  // caller tag on «Гордей»
  const tag = mk('card', 'left:50px;top:300px;width:520px;height:150px;border-radius:44px', F,
    `<div style="position:absolute;left:28px;top:22px;width:106px;height:106px;border-radius:50%;background:linear-gradient(160deg,#7a5cff,#3a7bff);display:flex;align-items:center;justify-content:center"><svg viewBox="0 0 100 100" width="62" height="62"><circle cx="50" cy="34" r="19" fill="#fff"/><path d="M14 92 C14 64 86 64 86 92 Z" fill="#fff"/></svg></div>
     <div style="position:absolute;left:156px;top:24px;font-weight:700;font-size:28px;color:rgba(255,255,255,.7);letter-spacing:.06em">КЛИЕНТ</div>
     <div style="position:absolute;left:156px;top:62px;font-weight:800;font-size:50px">Гордей</div>`);
  life(tag, 11.3, 13.4);
  tl.fromTo(tag, { x: -700, rotation: -8 }, { x: 0, rotation: 0, duration: 0.6, ease: 'back.out(1.6)' }, T(11.3));
  tl.to(tag, { x: -700, duration: 0.3, ease: 'power3.in' }, T(13.1));
  // tooth sticker + sparkles on «чистку»
  const th = tooth(F, 850, 470, 280); life(th, 13.7, 15.9);
  tl.fromTo(th, { scale: 0, rotation: 30 }, { scale: 1, rotation: -8, duration: 0.55, ease: 'elastic.out(1,.55)' }, T(13.7));
  tl.to(th, { y: -14, duration: 0.7, ease: 'sine.inOut', yoyo: true, repeat: 1 }, T(14.3));
  tl.to(th, { scale: 0, duration: 0.25, ease: 'back.in(2)' }, T(15.7));
  burst(F, 850, 470, 13.8, 7, 210, '#fff');
});

/* ====== S4 · 16.3–23.3  AI: «Профессиональная гигиена от 4 тысяч рублей. На какой день?» ====== */
S(16.3, 23.3, () => {
  const lab = mk('card', 'left:60px;top:300px;width:560px;height:130px;border-radius:40px', F,
    `<div style="position:absolute;left:30px;top:22px;font-weight:800;font-size:30px;color:#3CF0C8;letter-spacing:.12em">УСЛУГА</div><div style="position:absolute;left:30px;top:60px;font-weight:800;font-size:44px;white-space:nowrap">Проф. гигиена</div>`);
  life(lab, 18.0, 19.5);
  tl.fromTo(lab, { x: -640 }, { x: 0, duration: 0.5, ease: 'power4.out' }, T(18.0));
  tl.to(lab, { x: -640, duration: 0.3, ease: 'power3.in' }, T(19.25));
  burst(F, 330, 365, 18.6, 5, 150, '#3CF0C8');
  // laptop card (the real screen recording) floats in 3D while the price flies
  const lap = $('lap');
  lap.className = 'o'; F.appendChild(lap);
  lap.style.cssText = 'position:absolute;left:90px;top:300px;width:900px;height:700px;object-fit:cover;object-position:50% 14%;border-radius:36px;border:3px solid rgba(255,255,255,.4);box-shadow:0 40px 100px rgba(0,0,0,.6),0 0 80px rgba(60,240,200,.35)';
  life(lap, P.lap ? P.lap[0] : 19.3, P.lap ? P.lap[1] : 22.4);
  tl.fromTo(lap, { y: 400, rotationX: 40, rotationY: -22, scale: 0.7, transformPerspective: 1000 }, { y: 0, rotationX: 6, rotationY: -8, scale: 1, duration: 0.7, ease: 'power4.out' }, T(P.lap ? P.lap[0] : 19.3));
  tl.to(lap, { rotationY: 8, y: -16, duration: 2.6, ease: 'sine.inOut' }, T((P.lap ? P.lap[0] : 19.3) + 0.7));
  // coin → price tag on «4 тысяч»
  const coin = mk('', 'left:445px;top:1010px;width:190px;height:190px', F, `<svg viewBox="0 0 100 100" width="190" height="190" style="filter:drop-shadow(0 20px 26px rgba(0,0,0,.5))"><defs><radialGradient id="cg" cx=".35" cy=".3" r=".9"><stop offset="0" stop-color="#fff3b0"/><stop offset=".55" stop-color="#ffc94d"/><stop offset="1" stop-color="#d98f12"/></radialGradient></defs><circle cx="50" cy="50" r="46" fill="url(#cg)"/><circle cx="50" cy="50" r="36" fill="none" stroke="#b97508" stroke-width="3"/><text x="50" y="66" text-anchor="middle" font-family="Unbounded" font-weight="900" font-size="46" fill="#a86b05">₽</text></svg>`);
  life(coin, 19.3, 19.95);
  tl.fromTo(coin, { y: -900, rotationY: 0, scale: 0.6 }, { y: 0, rotationY: 1080, scale: 1, duration: 0.6, ease: 'power3.in', transformPerspective: 800 }, T(19.3));
  const price = x3('4 000 ₽', { x: 540, y: 1215, size: 190, depth: 18, cls: 'gold', parent: F, ls: -4, tf: 'rotate(-3deg)' }); life(price, 19.85, 22.9);
  x3in(price, 19.85, { st: 0.05, y0: 220, rx: -60 });
  x3shine(price, 20.5); punch(19.88, 1.08); burst(F, 540, 1215, 19.9, 8, 330, '#ffe27a');
  x3out(price, 22.5, { y1: 300, dir: 0 });
});

/* ====== S5 · 23.3–27.7  user: «Да, я на ближайший. Вот, можно в воскресенье.» ====== */
S(23.3, 27.7, () => {
  const w = mk('', 'left:90px;top:300px;width:900px;height:1000px', B);
  life(w, 23.5, 27.4);
  const days = ['ПН', 'ВТ', 'СР', 'ЧТ', 'ПТ', 'СБ', 'ВС'];
  let cells = '';
  for (let r = 0; r < 4; r++) for (let c = 0; c < 7; c++) { const n = r * 7 + c + 6; cells += `<div class="d" style="font-weight:800;font-size:46px;text-align:center;line-height:110px;color:${c === 6 ? '#FF5A6A' : '#fff'}">${n > 31 ? n - 31 : n}</div>`; }
  w.innerHTML = `<div class="card" style="left:0;top:0;width:900px;height:1000px;border-radius:56px;background:linear-gradient(170deg,rgba(255,255,255,.2),rgba(255,255,255,.07))"></div>
   <div style="position:absolute;left:0;top:0;width:900px;height:170px;border-radius:56px 56px 0 0;background:linear-gradient(180deg,#ff6b7d,#e03d52);box-shadow:0 12px 30px rgba(0,0,0,.35)"></div>
   <div style="position:absolute;left:0;top:44px;width:900px;text-align:center;font-weight:900;font-size:64px;letter-spacing:.08em">ОКТЯБРЬ</div>
   <div style="position:absolute;left:60px;top:-30px;width:34px;height:90px;border-radius:17px;background:#fff;box-shadow:0 6px 14px rgba(0,0,0,.4)"></div>
   <div style="position:absolute;left:806px;top:-30px;width:34px;height:90px;border-radius:17px;background:#fff;box-shadow:0 6px 14px rgba(0,0,0,.4)"></div>
   <div style="position:absolute;left:30px;top:200px;width:840px;display:grid;grid-template-columns:repeat(7,1fr)">${days.map((d, i) => `<div style="text-align:center;font-weight:800;font-size:30px;color:${i === 6 ? '#FF5A6A' : 'rgba(255,255,255,.6)'};line-height:70px">${d}</div>`).join('')}</div>
   <div style="position:absolute;left:30px;top:272px;width:840px;display:grid;grid-template-columns:repeat(7,1fr)">${cells}</div>
   <svg style="position:absolute;left:0;top:0;overflow:visible" width="900" height="1000"><ellipse class="pen" cx="${30 + 840 / 7 * 6.5}" cy="${272 + 110 * 2.5}" rx="74" ry="62" fill="none" stroke="#FF5A6A" stroke-width="12" stroke-linecap="round" stroke-dasharray="1200" stroke-dashoffset="1200" style="filter:drop-shadow(0 0 16px #ff5a6a)"/></svg>`;
  tl.fromTo(w, { y: -900, rotationX: -70, rotation: 6, transformPerspective: 1000 }, { y: 0, rotationX: 0, rotation: -2, duration: 0.75, ease: 'bounce.out' }, T(23.5));
  tl.fromTo(w.querySelector('.pen'), { strokeDashoffset: 1200 }, { strokeDashoffset: 0, duration: 0.55, ease: 'power2.inOut' }, T(25.35));
  tl.to(w, { y: 1000, rotation: 8, duration: 0.4, ease: 'power3.in' }, T(27.0));
});

/* ====== S6 · 27.7–31.4  AI: «На какое время удобно? Утром или вечером?» ====== */
S(27.7, 31.4, () => {
  const s = sun(B, 250, 440, 340), m = moon(B, 830, 440, 300);
  life(s, 28.4, 31.4); life(m, 28.6, 31.4);
  tl.fromTo(s, { x: -500, scale: 0.4, rotation: -60 }, { x: 0, scale: 1, rotation: 0, duration: 0.7, ease: 'back.out(1.6)' }, T(28.4));
  tl.fromTo(m, { x: 500, scale: 0.4, rotation: 60 }, { x: 0, scale: 1, rotation: 0, duration: 0.7, ease: 'back.out(1.6)' }, T(28.6));
  tl.to(s._rays, { rotation: 180, duration: 3, ease: 'none' }, T(28.4));
  tl.fromTo(s, { scale: 1 }, { scale: 1.25, duration: 0.3, yoyo: true, repeat: 1, ease: 'power2.out' }, T(29.92));
  tl.fromTo(m, { scale: 1 }, { scale: 1.25, duration: 0.3, yoyo: true, repeat: 1, ease: 'power2.out' }, T(30.38));
  ring(B, 250, 440, 340, 29.95, '#ffd45a'); ring(B, 830, 440, 300, 30.4, '#a9bcff');
  const q = mk('', 'left:0;top:260px;width:1080px;text-align:center;font-weight:900;font-size:110px;color:#fff;text-shadow:0 8px 40px rgba(0,0,0,.6)', F, '?'); life(q, 28.5, 31.3);
  tl.fromTo(q, { scale: 0, rotation: 30 }, { scale: 1, rotation: -6, duration: 0.5, ease: 'elastic.out(1,.5)' }, T(28.5));
});

/* ====== S7 · 31.4–35.3  user: «Давай очень утром.» — sun wins ====== */
S(31.4, 35.3, () => {
  const s = sun(B, 540, 560, 1150); life(s, 32.2, 35.0);
  tl.fromTo(s, { scale: 0.2, y: 500, rotation: -90 }, { scale: 1, y: 0, rotation: 0, duration: 0.9, ease: 'expo.out' }, T(32.2));
  tl.to(s._rays, { rotation: 120, duration: 3, ease: 'none' }, T(32.2));
  tl.to(s, { scale: 1.08, duration: 1.2, ease: 'sine.inOut', yoyo: true, repeat: 1 }, T(33.0));
  tl.to(s, { scale: 0, duration: 0.3, ease: 'power3.in' }, T(34.9));
  flash(32.22, 0.6, 0.65);
  const mn = moon(B, 830, 440, 300); life(mn, 31.4, 32.4);
  tl.to(mn, { y: 900, rotation: 120, duration: 0.55, ease: 'power3.in' }, T(32.0));
  const k = x3('УТРОМ', { x: 540, y: 1290, size: 170, depth: 16, cls: 'gold', parent: F, ls: -2 }); life(k, 32.25, 33.9);
  x3in(k, 32.25, { st: 0.06 }); x3shine(k, 32.9); x3out(k, 33.6);
});

/* ====== S8 · 35.3–41.7  AI: «Давайте сформулируем. Утром, воскресенье. Допустим, в 9 утра.» ====== */
S(35.3, 41.7, () => {
  const tile = mk('card', 'left:120px;top:300px;width:840px;height:270px;border-radius:60px', F);
  life(tile, 36.6, 41.4);
  tl.fromTo(tile, { y: 500, rotationX: 60, scale: 0.6, transformPerspective: 900 }, { y: 0, rotationX: 0, scale: 1, duration: 0.7, ease: 'back.out(1.4)' }, T(36.6));
  const ic = sun(tile, 120, 135, 140); tl.to(ic._rays, { rotation: 360, duration: 5, ease: 'none' }, T(36.6));
  const chip = mk('', 'left:236px;top:22px;padding:6px 26px;border-radius:30px;background:#3CF0C8;color:#04101c;font-weight:900;font-size:40px;letter-spacing:.06em', tile, 'ВС');
  tl.fromTo(chip, { scale: 0, opacity: 0 }, { scale: 1, opacity: 1, duration: 0.35, ease: 'back.out(3)' }, T(37.76));
  const dg = x3('9:00', { x: 560, y: 150, size: 150, depth: 16, cls: 'gold', parent: tile, ls: 2 });
  gs.set(dg._chs, { opacity: 0 });
  x3in(dg, 39.36, { st: 0.07, y0: 90, rx: -90 });
  x3shine(dg, 40.0);
  burst(F, 700, 430, 39.5, 6, 220, '#ffe27a');
  tl.to(tile, { y: -300, scale: 0.8, opacity: 0, duration: 0.35, ease: 'power3.in' }, T(41.35));
});

/* ====== S9 · 41.7–48.0  user: «Нет, в 9 утра это поздно. Мне надо в 6 утра.» ====== */
S(41.7, 48.0, () => {
  const c = clock(B, 540, 760, 940, { numSize: 34, rim: '#FF5A6A', hand: '#FF5A6A', f0: '#5a1c33', f1: '#240d1c' }); life(c.n, 41.9, 47.8);
  tl.fromTo(c.n, { scale: 0.4, rotation: 120 }, { scale: 1, rotation: 0, duration: 0.6, ease: 'back.out(1.6)' }, T(41.9));
  gs.set(c.hour, { rotation: 270 }); gs.set(c.min, { rotation: 0 }); // 9:00
  tl.to(c.hour, { rotation: 180, duration: 0.7, ease: 'back.out(2.2)' }, T(44.2)); // → 6
  const x = crossMark(F, 230, 480, 250); life(x, 43.18, 44.6);
  tl.fromTo(x, { scale: 0, rotation: -40 }, { scale: 1, rotation: 0, duration: 0.45, ease: 'back.out(2.4)' }, T(43.18));
  tl.fromTo(x._c[0], { strokeDashoffset: 110 }, { strokeDashoffset: 0, duration: 0.2, ease: 'power2.out' }, T(43.3));
  tl.fromTo(x._c[1], { strokeDashoffset: 110 }, { strokeDashoffset: 0, duration: 0.2, ease: 'power2.out' }, T(43.45));
  tl.fromTo(x, { x: 0 }, { x: 14, duration: 0.05, yoyo: true, repeat: 5 }, T(43.65));
  const n9 = x3('9', { x: 230, y: 480, size: 330, depth: 14, cls: 'coral', parent: F }); life(n9, 43.1, 44.5);
  x3in(n9, 43.1, { y0: 100 }); x3out(n9, 44.25, { dir: -1 });
  const n6 = x3('6', { x: 230, y: 480, size: 360, depth: 16, cls: 'mint', parent: F }); life(n6, 44.6, 46.9);
  x3in(n6, 44.6, { y0: 160 }); x3shine(n6, 45.2); x3out(n6, 46.5, { dir: 1 });
  tl.to(c.n, { scale: 0, rotation: -90, duration: 0.3, ease: 'back.in(2)' }, T(47.5));
});

/* ====== S10 · 48.0–52.4  AI: «В 6 клиника ещё не работает. Мы открываемся в 8.» ====== */
S(48.0, 52.4, () => {
  const sg = mk('', 'left:640px;top:290px;width:380px;height:520px;transform-origin:50% 0;', F); gs.set(sg, { scale: 0.74, transformOrigin: '50% 0' });
  life(sg, 48.2, 52.4);
  sg.innerHTML = `<div style="position:absolute;left:120px;top:-400px;width:6px;height:460px;background:#cfe9ff"></div><div style="position:absolute;left:254px;top:-400px;width:6px;height:460px;background:#cfe9ff"></div>
    <div class="side a" style="position:absolute;left:0;top:60px;width:380px;height:440px;border-radius:44px;background:linear-gradient(160deg,#ff6b7d,#c92f47);box-shadow:0 40px 80px rgba(0,0,0,.5);backface-visibility:hidden;text-align:center;font-weight:900">
      <div style="margin-top:62px;font-size:56px;letter-spacing:.04em">ЗАКРЫТО</div><div style="margin-top:40px;font-size:30px;font-weight:700;opacity:.85">сейчас</div><div style="margin-top:6px;font-size:96px;font-family:Unbounded">6:00</div></div>
    <div class="side b" style="position:absolute;left:0;top:60px;width:380px;height:440px;border-radius:44px;background:linear-gradient(160deg,#6dffe3,#17b697);color:#04101c;box-shadow:0 40px 80px rgba(0,0,0,.5);backface-visibility:hidden;transform:rotateY(180deg);text-align:center;font-weight:900">
      <div style="margin-top:62px;font-size:56px;letter-spacing:.04em">ОТКРЫТО</div><div style="margin-top:40px;font-size:30px;font-weight:700;opacity:.85">с</div><div style="margin-top:6px;font-size:96px;font-family:Unbounded">8:00</div></div>`;
  const a = sg.querySelector('.a'), b = sg.querySelector('.b');
  tl.fromTo(sg, { y: -700, rotation: 14 }, { y: 0, rotation: -3, duration: 0.7, ease: 'bounce.out' }, T(48.2));
  tl.to(sg, { rotation: 4, duration: 1.0, ease: 'sine.inOut', yoyo: true, repeat: 1 }, T(48.9));
  tl.fromTo(a, { rotationY: 0 }, { rotationY: -180, duration: 0.5, ease: 'back.inOut(1.6)', transformPerspective: 900 }, T(50.2));
  tl.fromTo(b, { rotationY: 180 }, { rotationY: 0, duration: 0.5, ease: 'back.inOut(1.6)', transformPerspective: 900 }, T(50.2));
  tl.to(sg, { y: -900, duration: 0.35, ease: 'power3.in' }, T(52.1));
  ring(F, 830, 520, 360, 50.7, '#3CF0C8');
});

/* ====== S11 · 52.4–55.3  user: «Да, в 8 идеально.» ====== */
S(52.4, 55.3, () => {
  const c = checkMark(F, 540, 520, 440); life(c, 52.95, 54.9);
  tl.fromTo(c, { scale: 2.6, opacity: 0 }, { scale: 1, opacity: 1, duration: 0.3, ease: 'power4.in' }, T(52.95));
  tl.fromTo(c._ck, { strokeDashoffset: 190 }, { strokeDashoffset: 0, duration: 0.35, ease: 'power2.out' }, T(53.1));
  tl.fromTo(c, { rotation: -6 }, { rotation: 0, duration: 0.2 }, T(53.25));
  ring(F, 540, 520, 440, 53.25, '#3CF0C8', 0.9, 8); ring(F, 540, 520, 440, 53.4, '#ffffff', 1.0, 4);
  burst(F, 540, 520, 53.28, 8, 380, '#b6ffee'); punch(53.26, 1.1);
  tl.to(c, { scale: 0, rotation: 40, duration: 0.3, ease: 'back.in(2)' }, T(54.6));
});

/* ====== S12 · 55.3–58.1  AI: «Скажите, пожалуйста, ваш номер телефона?» ====== */
S(55.3, 58.1, () => {
  const ph = mk('', 'left:620px;top:290px;width:380px;height:700px', F); life(ph, 55.5, 58.1); gs.set(ph, { scale: 0.72, transformOrigin: '100% 0' });
  ph.innerHTML = `<div style="position:absolute;left:0;top:0;width:380px;height:700px;border-radius:64px;background:linear-gradient(160deg,#243b52,#0b1624);border:6px solid #8fb3d1;box-shadow:0 50px 100px rgba(0,0,0,.6),0 0 60px rgba(60,240,200,.3)"></div>
   <div style="position:absolute;left:130px;top:22px;width:120px;height:26px;border-radius:14px;background:#04101c"></div>
   <div style="position:absolute;left:30px;top:100px;width:320px;text-align:center;font-weight:800;font-size:32px;color:rgba(255,255,255,.7)">Ваш номер</div>
   <div style="position:absolute;left:28px;top:160px;width:324px;height:96px;border-radius:26px;background:rgba(255,255,255,.12);border:3px solid #3CF0C8;box-shadow:0 0 30px rgba(60,240,200,.5)"></div>
   <div class="num" style="position:absolute;left:40px;top:172px;width:300px;font-weight:800;font-size:38px;line-height:72px;white-space:nowrap">+7 <span class="d"></span><i style="display:inline-block;width:3px;height:44px;background:#3CF0C8;vertical-align:middle;margin-left:3px" class="car"></i></div>
   <div style="position:absolute;left:30px;top:300px;width:320px;display:grid;grid-template-columns:repeat(3,1fr);gap:18px">${[1, 2, 3, 4, 5, 6, 7, 8, 9, '', 0, ''].map(n => `<div style="height:88px;border-radius:44px;background:${n === '' ? 'transparent' : 'rgba(255,255,255,.14)'};text-align:center;line-height:88px;font-weight:800;font-size:40px">${n}</div>`).join('')}</div>
   <div style="position:absolute;left:30px;top:620px;width:320px;height:56px;border-radius:28px;background:#3CF0C8;color:#04101c;text-align:center;line-height:56px;font-weight:900;font-size:28px">ЗАПИСАТЬ</div>`;
  tl.fromTo(ph, { y: 900, rotation: 14, rotationY: -40, transformPerspective: 1000 }, { y: 0, rotation: -5, rotationY: -8, duration: 0.7, ease: 'power4.out' }, T(55.5));
  const d = ph.querySelector('.d'), car = ph.querySelector('.car'), digits = '999 123-45-67';
  for (let i = 1; i <= digits.length; i++) tl.set(d, { textContent: digits.slice(0, i) }, T(56.95 + i * 0.075));
  tl.fromTo(car, { opacity: 1 }, { opacity: 0, duration: 0.25, yoyo: true, repeat: 7, ease: 'steps(1)' }, T(55.8));
  tl.to(ph, { y: 900, duration: 0.35, ease: 'power3.in' }, T(57.85));
});

/* ====== S13 · 58.1–67.9  «Посмотрите на это качество и сравните, что лучше…» ====== */
S(58.1, 67.9, () => {
  const k = x3('СРАВНИ', { x: 540, y: 1040, size: 150, depth: 18, cls: '', parent: F, ls: -3, tf: 'rotate(-3deg)' }); life(k, 59.55, 62.35);
  x3in(k, 59.55, { st: 0.06, y0: 260, rx: -90 }); x3shine(k, 60.4); punch(59.58, 1.1);
  x3out(k, 62.0, { y1: -400 });
  // VS split cards
  const L = mk('', 'left:40px;top:290px;width:480px;height:440px', F), R = mk('', 'left:560px;top:290px;width:480px;height:440px', F);
  gs.set([L, R], { scale: 0.8, transformOrigin: '50% 0' });
  life(L, 63.25, 67.8); life(R, 64.75, 67.8);
  L.innerHTML = `<div style="position:absolute;inset:0;border-radius:52px;background:linear-gradient(160deg,#ff6b7d,#a8243b);box-shadow:0 40px 80px rgba(0,0,0,.5)"></div>
    <div style="position:absolute;left:0;top:34px;width:100%;text-align:center">${phoneIcon('#fff', 130)}</div>
    <div style="position:absolute;left:0;top:200px;width:100%;text-align:center;font-weight:900;font-size:48px;line-height:1.1">Пропущен<br>звонок</div>
    <div style="position:absolute;left:0;top:340px;width:100%;text-align:center;font-weight:800;font-size:38px;opacity:.85">0 записей</div>`;
  R.innerHTML = `<div style="position:absolute;inset:0;border-radius:52px;background:linear-gradient(160deg,#6dffe3,#13a98e);box-shadow:0 40px 80px rgba(0,0,0,.5);color:#04101c"></div>
    <div style="position:absolute;left:0;top:34px;width:100%;text-align:center">${calIcon('#04101c', 130)}</div>
    <div style="position:absolute;left:0;top:200px;width:100%;text-align:center;font-weight:900;font-size:48px;line-height:1.1;color:#04101c">Запись<br>на приём</div>
    <div style="position:absolute;left:0;top:340px;width:100%;text-align:center;font-weight:800;font-size:38px;color:#04101c;opacity:.8">клиент в кресле</div>`;
  tl.fromTo(L, { x: -700, rotation: -12 }, { x: 0, rotation: -3, duration: 0.6, ease: 'back.out(1.5)' }, T(63.25));
  tl.fromTo(R, { x: 700, rotation: 12 }, { x: 0, rotation: 3, duration: 0.6, ease: 'back.out(1.5)' }, T(64.75));
  const x = crossMark(L, 400, 60, 130); const ck = checkMark(R, 90, 60, 130);
  tl.fromTo(x, { scale: 0 }, { scale: 1, duration: 0.35, ease: 'back.out(3)' }, T(63.75));
  tl.fromTo(x._c[0], { strokeDashoffset: 110 }, { strokeDashoffset: 0, duration: 0.2 }, T(63.85)); tl.fromTo(x._c[1], { strokeDashoffset: 110 }, { strokeDashoffset: 0, duration: 0.2 }, T(64.0));
  tl.fromTo(L, { y: 0 }, { y: 10, duration: 0.06, yoyo: true, repeat: 5 }, T(64.2));
  tl.fromTo(ck, { scale: 0 }, { scale: 1, duration: 0.35, ease: 'back.out(3)' }, T(65.9));
  tl.fromTo(ck._ck, { strokeDashoffset: 190 }, { strokeDashoffset: 0, duration: 0.3 }, T(66.05));
  burst(F, 800, 470, 65.95, 7, 260, '#b6ffee'); ring(F, 800, 500, 460, 65.95, '#3CF0C8', 0.9, 6);
  tl.to(L, { y: -500, opacity: 0, rotation: -14, duration: 0.35, ease: 'power3.in' }, T(67.45));
  tl.to(R, { y: -500, opacity: 0, rotation: 14, duration: 0.35, ease: 'power3.in' }, T(67.5));
});

/* ====== S14 · 67.9–72.0  «Попробовать можно. Демоверсия бесплатна для каждого.» ====== */
S(67.9, 72.1, () => {
  const eb = mk('', 'left:0;top:760px;width:1080px;text-align:center;font-weight:800;font-size:46px;letter-spacing:.2em;color:#3CF0C8;text-shadow:0 4px 24px rgba(0,0,0,.6)', F, 'ПОПРОБУЙ САМ'); life(eb, 67.95, 72.1);
  tl.fromTo(eb, { y: 60, opacity: 0, letterSpacing: '0.5em' }, { y: 0, opacity: 1, letterSpacing: '0.2em', duration: 0.6, ease: 'power3.out' }, T(67.95));
  const a = x3('ДЕМО', { x: 540, y: 960, size: 205, depth: 20, cls: 'gold', parent: F, ls: -4 }); life(a, 69.05, 72.1);
  x3in(a, 69.05, { st: 0.07, y0: 300, rx: -90 }); x3shine(a, 69.8); punch(69.08, 1.09);
  const b = x3('БЕСПЛАТНО', { x: 540, y: 1175, size: 104, depth: 12, cls: 'mint', parent: F, ls: -2 }); life(b, 69.75, 72.1);
  x3in(b, 69.75, { st: 0.04, y0: 220, rx: -80 }); x3shine(b, 70.7); punch(69.78, 1.06);
  ring(F, 540, 1080, 900, 69.1, '#ffc94d', 1.1, 8); ring(F, 540, 1080, 900, 69.8, '#3CF0C8', 1.1, 8);
  burst(F, 540, 1080, 69.12, 10, 420, '#ffe27a');
  x3float(a, 70.4, 72.0, 8);
});

/* ---- transitions between sentences (never the same twice in a row) ---- */
if (here(4.2, 4.6)) whip(4.4, 1);
if (here(9.3, 9.7)) wipe(9.5);
if (here(16.1, 16.5)) zoomThrough(16.3);
if (here(23.1, 23.5)) flash(23.3, 0.5, 0.95);
if (here(27.5, 27.9)) glitch(27.7);
if (here(31.2, 31.6)) whip(31.4, -1);
if (here(35.1, 35.5)) iris(35.3, '#7a5cff');
if (here(41.5, 41.9)) whip(41.7, 1);
if (here(47.8, 48.2)) glitch(48.0);
if (here(52.2, 52.6)) flash(52.4, 0.45, 0.8);
if (here(55.1, 55.5)) wipe(55.3, '#7a5cff');
if (here(57.9, 58.3)) zoomThrough(58.1);
if (here(62.3, 62.7)) whip(62.5, -1);
if (here(67.7, 68.1)) flash(67.9, 0.55, 1.0);

captions();

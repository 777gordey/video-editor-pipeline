/* objs.js — hand-built SVG/CSS objects (no external art). Each builder returns a DOM node already placed in `parent`. */
const SVGNS = 'http://www.w3.org/2000/svg';
const TOOTH_D = 'M30 12 C16 12 8 24 10 40 C12 54 18 60 20 76 C21 88 26 94 31 94 C37 94 38 80 41 70 C43 64 57 64 59 70 C62 80 63 94 69 94 C74 94 79 88 80 76 C82 60 88 54 90 40 C92 24 84 12 70 12 C62 12 57 18 50 18 C43 18 38 12 30 12 Z';

function tooth(parent, cx, cy, size, css = '') {
  const n = mk('', `left:${cx - size / 2}px;top:${cy - size / 2}px;width:${size}px;height:${size}px;${css}`, parent,
    `<svg viewBox="0 0 100 100" width="${size}" height="${size}" style="overflow:visible;filter:drop-shadow(0 18px 30px rgba(0,0,0,.45)) drop-shadow(0 0 22px rgba(60,240,200,.55))">
      <defs><linearGradient id="tg${cx|0}${cy|0}" x1="0" y1="0" x2="1" y2="1"><stop offset="0" stop-color="#ffffff"/><stop offset=".6" stop-color="#e3f3ff"/><stop offset="1" stop-color="#a9d3f0"/></linearGradient></defs>
      <path d="${TOOTH_D}" fill="url(#tg${cx|0}${cy|0})" stroke="#3CF0C8" stroke-width="2.4" stroke-linejoin="round"/>
      <path d="M26 24 C20 28 19 38 21 46" fill="none" stroke="#fff" stroke-width="3.5" stroke-linecap="round" opacity=".9"/></svg>`);
  return n;
}
function sparkle(parent, cx, cy, size, color = '#fff') {
  return mk('', `left:${cx - size / 2}px;top:${cy - size / 2}px;width:${size}px;height:${size}px`, parent,
    `<svg viewBox="0 0 100 100" width="${size}" height="${size}" style="filter:drop-shadow(0 0 12px ${color})"><path d="M50 0 C54 30 70 46 100 50 C70 54 54 70 50 100 C46 70 30 54 0 50 C30 46 46 30 50 0 Z" fill="${color}"/></svg>`);
}
function burst(parent, cx, cy, t, n = 6, rad = 200, color = '#fff') {
  for (let i = 0; i < n; i++) {
    const a = i / n * Math.PI * 2 + 0.4, s = sparkle(parent, cx, cy, 44 + rnd() * 40, color);
    s.classList.add('o'); gs.set(s, { autoAlpha: 0 });
    tl.fromTo(s, { x: 0, y: 0, scale: 0, rotation: -30, autoAlpha: 1 }, { x: Math.cos(a) * rad * (0.7 + rnd() * 0.5), y: Math.sin(a) * rad * (0.7 + rnd() * 0.5), scale: 1, rotation: 40, duration: 0.5, ease: 'power3.out', immediateRender: false }, T(t) + i * 0.02);
    tl.to(s, { scale: 0, autoAlpha: 0, duration: 0.35, ease: 'power2.in', immediateRender: false }, T(t) + 0.5 + i * 0.02);
  }
}
function ring(parent, cx, cy, size, t, color = '#3CF0C8', d = 0.9, w = 6) {
  const r = mk('', `left:${cx - size / 2}px;top:${cy - size / 2}px;width:${size}px;height:${size}px;border-radius:50%;border:${w}px solid ${color};box-shadow:0 0 40px ${color};opacity:0`, parent);
  tl.fromTo(r, { scale: 0.3, opacity: 0.95 }, { scale: 1.8, opacity: 0, duration: d, ease: 'power2.out', immediateRender: false }, T(t));
  return r;
}

/* AI orb with live equaliser */
function orb(parent, cx, cy, size) {
  const g = mk('', `left:${cx - size / 2}px;top:${cy - size / 2}px;width:${size}px;height:${size}px`, parent);
  mk('', `left:-18%;top:-18%;width:136%;height:136%;border-radius:50%;background:radial-gradient(closest-side,rgba(60,240,200,.55),transparent);filter:blur(10px)`, g);
  mk('', `left:0;top:0;width:100%;height:100%;border-radius:50%;background:radial-gradient(circle at 34% 28%,#ffffff 0%,#b8fff0 14%,#3CF0C8 42%,#0b8f8a 78%,#06504f 100%);box-shadow:0 30px 70px rgba(0,0,0,.5),inset 0 -14px 30px rgba(0,60,70,.45),inset 0 10px 24px rgba(255,255,255,.55)`, g);
  mk('', `left:12%;top:8%;width:46%;height:26%;border-radius:50%;background:linear-gradient(180deg,rgba(255,255,255,.85),rgba(255,255,255,0));transform:rotate(-24deg)`, g);
  g._bars = size;
  return g;
}

/* clock dial. returns {n, hour, min}; hands rotate around the centre (svgOrigin) */
function clock(parent, cx, cy, size, o = {}) {
  const n = mk('', `left:${cx - size / 2}px;top:${cy - size / 2}px;width:${size}px;height:${size}px`, parent);
  let ticks = '', nums = '';
  for (let i = 0; i < 60; i++) {
    const a = i * 6 * Math.PI / 180, big = i % 5 === 0, r1 = 178, r2 = big ? 160 : 168;
    ticks += `<line x1="${200 + Math.sin(a) * r1}" y1="${200 - Math.cos(a) * r1}" x2="${200 + Math.sin(a) * r2}" y2="${200 - Math.cos(a) * r2}" stroke="${big ? '#fff' : 'rgba(255,255,255,.45)'}" stroke-width="${big ? 5 : 2.5}" stroke-linecap="round"/>`;
  }
  for (let h = 1; h <= 12; h++) {
    const a = h * 30 * Math.PI / 180;
    nums += `<text x="${200 + Math.sin(a) * 134}" y="${200 - Math.cos(a) * 134 + 14}" text-anchor="middle" font-family="Unbounded" font-weight="800" font-size="${o.numSize || 36}" fill="${o.numColor || '#fff'}" id="n${h}">${h}</text>`;
  }
  n.innerHTML = `<svg viewBox="0 0 400 400" width="${size}" height="${size}" style="overflow:visible;filter:drop-shadow(0 30px 50px rgba(0,0,0,.5))">
    <defs><radialGradient id="cf${cx|0}${cy|0}" cx=".4" cy=".3" r=".9"><stop offset="0" stop-color="${o.f0 || '#1d5d7a'}"/><stop offset="1" stop-color="${o.f1 || '#0a2236'}"/></radialGradient></defs>
    <circle cx="200" cy="200" r="196" fill="${o.rim || '#3CF0C8'}"/><circle cx="200" cy="200" r="188" fill="url(#cf${cx|0}${cy|0})"/>
    ${ticks}${nums}
    <g class="hh"><rect x="193" y="104" width="14" height="108" rx="7" fill="#fff"/></g>
    <g class="mh"><rect x="196" y="58" width="8" height="150" rx="4" fill="${o.hand || '#3CF0C8'}"/></g>
    <circle cx="200" cy="200" r="13" fill="#fff"/><circle cx="200" cy="200" r="6" fill="#0a2236"/></svg>`;
  const hour = n.querySelector('.hh'), min = n.querySelector('.mh');
  gs.set([hour, min], { svgOrigin: '200 200' });
  return { n, hour, min };
}

function sun(parent, cx, cy, size) {
  const n = mk('', `left:${cx - size / 2}px;top:${cy - size / 2}px;width:${size}px;height:${size}px`, parent);
  let rays = '';
  for (let i = 0; i < 16; i++) rays += `<rect x="94" y="2" width="12" height="${i % 2 ? 26 : 38}" rx="6" fill="#ffd45a" transform="rotate(${i * 22.5} 100 100)"/>`;
  n.innerHTML = `<svg viewBox="0 0 200 200" width="${size}" height="${size}" style="overflow:visible;filter:drop-shadow(0 0 40px rgba(255,190,60,.8))"><g class="rays">${rays}</g>
    <defs><radialGradient id="sg${cx|0}" cx=".4" cy=".35" r=".8"><stop offset="0" stop-color="#fff6c2"/><stop offset=".55" stop-color="#ffc94d"/><stop offset="1" stop-color="#ff9a1f"/></radialGradient></defs>
    <circle cx="100" cy="100" r="58" fill="url(#sg${cx|0})"/></svg>`;
  n._rays = n.querySelector('.rays'); gs.set(n._rays, { svgOrigin: '100 100' });
  return n;
}
function moon(parent, cx, cy, size) {
  const n = mk('', `left:${cx - size / 2}px;top:${cy - size / 2}px;width:${size}px;height:${size}px`, parent);
  n.innerHTML = `<svg viewBox="0 0 200 200" width="${size}" height="${size}" style="overflow:visible;filter:drop-shadow(0 0 36px rgba(150,180,255,.8))">
    <defs><mask id="mm${cx|0}"><rect width="200" height="200" fill="#fff"/><circle cx="128" cy="84" r="62" fill="#000"/></mask>
    <radialGradient id="mg${cx|0}" cx=".3" cy=".3" r=".9"><stop offset="0" stop-color="#ffffff"/><stop offset="1" stop-color="#a9bcff"/></radialGradient></defs>
    <circle cx="96" cy="108" r="66" fill="url(#mg${cx|0})" mask="url(#mm${cx|0})"/>
    <circle cx="150" cy="150" r="5" fill="#fff"/><circle cx="168" cy="48" r="4" fill="#fff"/><circle cx="40" cy="40" r="3.5" fill="#fff"/></svg>`;
  return n;
}

function pill(parent, x, y, w, h, html, css = '') {
  return mk('card', `left:${x}px;top:${y}px;width:${w}px;height:${h}px;${css}`, parent, html);
}

function checkMark(parent, cx, cy, size, color = '#3CF0C8') {
  const n = mk('', `left:${cx - size / 2}px;top:${cy - size / 2}px;width:${size}px;height:${size}px`, parent,
    `<svg viewBox="0 0 200 200" width="${size}" height="${size}" style="overflow:visible;filter:drop-shadow(0 0 30px ${color}) drop-shadow(0 18px 24px rgba(0,0,0,.5))">
      <circle cx="100" cy="100" r="92" fill="${color}"/><circle cx="100" cy="100" r="92" fill="none" stroke="#fff" stroke-opacity=".5" stroke-width="5"/>
      <path class="ck" d="M52 104 L88 140 L150 66" fill="none" stroke="#04101c" stroke-width="22" stroke-linecap="round" stroke-linejoin="round" stroke-dasharray="190" stroke-dashoffset="190"/></svg>`);
  n._ck = n.querySelector('.ck');
  return n;
}
function crossMark(parent, cx, cy, size, color = '#FF5A6A') {
  const n = mk('', `left:${cx - size / 2}px;top:${cy - size / 2}px;width:${size}px;height:${size}px`, parent,
    `<svg viewBox="0 0 200 200" width="${size}" height="${size}" style="overflow:visible;filter:drop-shadow(0 0 30px ${color}) drop-shadow(0 18px 24px rgba(0,0,0,.5))">
      <circle cx="100" cy="100" r="92" fill="${color}"/>
      <path class="c1" d="M62 62 L138 138" stroke="#fff" stroke-width="22" stroke-linecap="round" stroke-dasharray="110" stroke-dashoffset="110"/>
      <path class="c2" d="M138 62 L62 138" stroke="#fff" stroke-width="22" stroke-linecap="round" stroke-dasharray="110" stroke-dashoffset="110"/></svg>`);
  n._c = [n.querySelector('.c1'), n.querySelector('.c2')];
  return n;
}
function phoneIcon(color = '#fff', size = 120) {
  return `<svg viewBox="0 0 100 100" width="${size}" height="${size}"><path d="M24 12 C18 12 12 18 13 26 C16 52 48 84 74 87 C82 88 88 82 88 76 L88 68 C88 65 86 63 83 62 L70 58 C67 57 64 58 62 60 L58 64 C48 59 41 52 36 42 L40 38 C42 36 43 33 42 30 L38 17 C37 14 35 12 32 12 Z" fill="${color}"/></svg>`;
}
function calIcon(color = '#fff', size = 120) {
  return `<svg viewBox="0 0 100 100" width="${size}" height="${size}"><rect x="12" y="20" width="76" height="68" rx="12" fill="none" stroke="${color}" stroke-width="7"/><path d="M12 42 H88" stroke="${color}" stroke-width="7"/><path d="M32 10 V28 M68 10 V28" stroke="${color}" stroke-width="8" stroke-linecap="round"/></svg>`;
}

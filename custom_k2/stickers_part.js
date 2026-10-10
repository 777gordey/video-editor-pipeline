/* ---------------- stickers (drawn in code; no third-party artwork) ---------------- */
const SW = 'stroke="#141018" stroke-width="7" stroke-linejoin="round" stroke-linecap="round"';
function sticker(c, w, h, x, y, svg, origin, k) {
  if (!here(c.t, c.e)) return null;
  k = k || 1.3;
  const el = mk('stk', `left:${x}px;top:${y}px;width:${w * k}px;height:${h * k}px;transform-origin:${origin || '50% 50%'}`, null, svg);
  el.firstElementChild.style.cssText = `transform:scale(${k});transform-origin:0 0`;
  gs.set(el, { autoAlpha: 0 });
  tl.set(el, { autoAlpha: 1 }, T(c.t));
  tl.set(el, { autoAlpha: 0 }, T(c.e));
  return el;
}
const popIn = (el, c, rot) => tl.fromTo(el, { scale: 0.1, rotation: rot - 20 }, { scale: 1, rotation: rot, duration: 0.4, ease: 'back.out(2.6)', immediateRender: false }, T(c.t));
const popOut = (el, c, rot) => tl.to(el, { scale: 0, rotation: rot + 16, duration: 0.2, ease: 'back.in(2)' }, T(c.e) - 0.22);
const star = (cx, cy, r) => { const p = []; for (let k = 0; k < 10; k++) { const a = -Math.PI / 2 + k * Math.PI / 5, rr = k % 2 ? r * 0.45 : r; p.push((cx + Math.cos(a) * rr).toFixed(1) + ',' + (cy + Math.sin(a) * rr).toFixed(1)); } return p.join(' '); };

P.cards.forEach(c => {
  /* 1. sloth hanging from the top edge: «мне лень» */
  if (c.kind === 'sloth') {
    const el = sticker(c, 300, 420, 650, -50, `<svg width="300" height="420" viewBox="0 0 300 420">
      <rect x="143" y="-30" width="16" height="150" rx="8" fill="#3FA34D" ${SW}/>
      <ellipse cx="150" cy="290" rx="88" ry="112" fill="#8B5E3C" ${SW}/>
      <ellipse cx="82" cy="150" rx="22" ry="38" fill="#8B5E3C" ${SW} transform="rotate(25 82 150)"/><ellipse cx="218" cy="150" rx="22" ry="38" fill="#8B5E3C" ${SW} transform="rotate(-25 218 150)"/>
      <ellipse cx="150" cy="235" rx="82" ry="70" fill="#C9A27A" ${SW}/><ellipse cx="150" cy="240" rx="64" ry="50" fill="#EBD7B7"/>
      <ellipse cx="116" cy="236" rx="22" ry="15" fill="#4A2F1B" transform="rotate(25 116 236)"/><ellipse cx="184" cy="236" rx="22" ry="15" fill="#4A2F1B" transform="rotate(-25 184 236)"/>
      <circle cx="116" cy="236" r="8" fill="#fff"/><circle cx="184" cy="236" r="8" fill="#fff"/><circle cx="118" cy="240" r="4" fill="#141018"/><circle cx="182" cy="240" r="4" fill="#141018"/>
      <rect class="lid" x="104" y="226" width="24" height="12" rx="6" fill="#4A2F1B"/><rect class="lid" x="172" y="226" width="24" height="12" rx="6" fill="#4A2F1B"/>
      <ellipse cx="150" cy="256" rx="11" ry="8" fill="#2B1B10"/><path d="M130 272 Q150 286 170 272" fill="none" ${SW}/></svg>`, '50% 0%');
    if (!el) return;
    tl.fromTo(el, { y: -420 }, { y: 0, duration: 0.45, ease: 'bounce.out', immediateRender: false }, T(c.t));
    tl.fromTo(el, { rotation: 7 }, { rotation: -7, duration: 0.9, ease: 'sine.inOut', yoyo: true, repeat: 1, immediateRender: false }, T(c.t) + 0.45);
    tl.to(el, { y: -420, duration: 0.25, ease: 'back.in(1.5)' }, T(c.e) - 0.27);
    el.querySelectorAll('.lid').forEach(l => tl.fromTo(l, { scaleY: 1, transformOrigin: '50% 0%' }, { scaleY: 2.0, duration: 0.5, ease: 'power1.inOut', immediateRender: false }, T(c.t) + 0.9));
    ['z', 'Z', 'Z'].forEach((ch, i) => {
      const z = mk('zz', `left:${610 + i * 30}px;top:${300 - i * 18}px;font-size:${52 + i * 16}px`, null, ch);
      tl.fromTo(z, { y: 30, opacity: 0, rotation: -10 }, { y: -50, opacity: 1, rotation: 12, duration: 0.55, ease: 'power1.out', immediateRender: false }, T(c.t) + 0.9 + i * 0.22);
      tl.to(z, { opacity: 0, duration: 0.2 }, T(c.e) - 0.25);
    });
  }
  /* 2. swinging price tag + coin */
  if (c.kind === 'price') {
    const el = sticker(c, 400, 380, 520, 20, `<svg width="400" height="380" viewBox="0 0 400 380">
      <path d="M200 -40 L200 70" stroke="#141018" stroke-width="7" fill="none"/>
      <path d="M100 90 L300 90 Q330 90 330 120 L330 290 Q330 320 300 320 L100 320 Q70 320 70 290 L70 120 Q70 90 100 90 Z" fill="${ORG}" ${SW}/>
      <circle cx="200" cy="120" r="14" fill="#141018"/>
      <text x="200" y="215" font-size="74" fill="#fff" stroke="#141018" stroke-width="12" paint-order="stroke">4 000</text>
      <text x="200" y="285" font-size="58" fill="#FFD21F" stroke="#141018" stroke-width="11" paint-order="stroke">₽</text></svg>`, '50% 0%');
    if (!el) return;
    tl.fromTo(el, { y: -300, rotation: 18 }, { y: 0, rotation: 0, duration: 0.5, ease: 'back.out(1.7)', immediateRender: false }, T(c.t));
    tl.fromTo(el, { rotation: 11 }, { rotation: -11, duration: 0.5, ease: 'sine.inOut', yoyo: true, repeat: 1, immediateRender: false }, T(c.t) + 0.5);
    tl.to(el, { y: -420, duration: 0.25, ease: 'back.in(1.4)' }, T(c.e) - 0.27);
    const coin = sticker({ t: 16.4, e: c.e }, 130, 130, 380, 330, `<svg width="130" height="130" viewBox="0 0 130 130"><circle cx="65" cy="65" r="56" fill="${YEL}" ${SW}/><circle cx="65" cy="65" r="40" fill="none" stroke="#C99A00" stroke-width="6"/><text x="65" y="68" font-size="46" fill="#7A5B00">₽</text></svg>`);
    if (coin) { tl.fromTo(coin, { y: -160, rotation: 0, scale: 0.6 }, { y: 0, rotation: 540, scale: 1, duration: 0.45, ease: 'bounce.out', immediateRender: false }, T(16.4)); tl.to(coin, { scale: 0, duration: 0.2 }, T(c.e) - 0.22); }
  }
  /* 3. alarm clock 6:00 */
  if (c.kind === 'alarm') {
    const el = sticker(c, 340, 360, 600, 40, `<svg width="340" height="360" viewBox="0 0 340 360">
      <circle cx="80" cy="64" r="48" fill="#FF3B5C" ${SW}/><circle cx="260" cy="64" r="48" fill="#FF3B5C" ${SW}/>
      <path d="M95 300 L70 345 M245 300 L270 345" ${SW} fill="none"/>
      <circle cx="170" cy="190" r="132" fill="#FF3B5C" ${SW}/><circle cx="170" cy="190" r="104" fill="#fff" ${SW}/>
      <path d="M170 190 L170 112" stroke="#141018" stroke-width="12" stroke-linecap="round"/><path d="M170 190 L170 268" stroke="${PINK}" stroke-width="14" stroke-linecap="round"/><circle cx="170" cy="190" r="11" fill="#141018"/>
      <path d="M60 130 Q40 190 60 250" fill="none" stroke="#141018" stroke-width="7" stroke-linecap="round"/><path d="M280 130 Q300 190 280 250" fill="none" stroke="#141018" stroke-width="7" stroke-linecap="round"/></svg>`, '50% 90%');
    if (!el) return;
    popIn(el, c, 0); popOut(el, c, 0);
    for (let k = 0; k < 14; k++) tl.fromTo(el, { rotation: k % 2 ? 9 : -9 }, { rotation: k % 2 ? -9 : 9, duration: 0.06, ease: 'none', immediateRender: false }, T(c.t) + 0.4 + k * 0.06);
  }
  /* 4. hanging sign «ЗАКРЫТО» */
  if (c.kind === 'closed') {
    const el = sticker(c, 560, 360, 50, -40, `<svg width="560" height="360" viewBox="0 0 560 360">
      <path d="M150 -20 L190 190 M410 -20 L370 190" stroke="#141018" stroke-width="7" fill="none"/>
      <rect x="60" y="170" width="440" height="160" rx="30" fill="${PINK}" ${SW}/><circle cx="190" cy="190" r="10" fill="#141018"/><circle cx="370" cy="190" r="10" fill="#141018"/>
      <text x="280" y="250" font-size="62" fill="#fff" stroke="#141018" stroke-width="12" paint-order="stroke">ЗАКРЫТО</text>
      <text x="280" y="304" font-size="30" fill="#fff" stroke="#141018" stroke-width="7" paint-order="stroke" style="font-family:'Rubik',sans-serif;font-weight:800">ещё не работает</text></svg>`, '50% 0%');
    if (!el) return;
    tl.fromTo(el, { y: -380, rotation: -14 }, { y: 0, rotation: 0, duration: 0.45, ease: 'back.out(1.8)', immediateRender: false }, T(c.t));
    tl.fromTo(el, { rotation: -9 }, { rotation: 9, duration: 0.55, ease: 'sine.inOut', yoyo: true, repeat: 1, immediateRender: false }, T(c.t) + 0.45);
    tl.to(el, { y: -400, duration: 0.25, ease: 'back.in(1.4)' }, T(c.e) - 0.27);
  }
  /* 5. five stars + stamp */
  if (c.kind === 'stars') {
    const el = sticker(c, 760, 330, 90, 30, `<svg width="760" height="330" viewBox="0 0 760 330">
      ${[0, 1, 2, 3, 4].map(i => `<polygon class="st" points="${star(90 + i * 145, 100, 66)}" fill="${YEL}" ${SW}/>`).join('')}
      <g class="stamp"><rect x="150" y="205" width="460" height="100" rx="18" fill="${PINK}" ${SW}/><text x="380" y="258" font-size="52" fill="#fff" stroke="#141018" stroke-width="10" paint-order="stroke">ИДЕАЛЬНО</text></g></svg>`);
    if (!el) return;
    el.querySelectorAll('.st').forEach((s, i) => { gs.set(s, { transformBox: 'fill-box', transformOrigin: '50% 50%', scale: 0 }); tl.to(s, { scale: 1, duration: 0.25, ease: 'back.out(3)' }, T(c.t) + i * 0.13); });
    const st = el.querySelector('.stamp'); gs.set(st, { transformBox: 'fill-box', transformOrigin: '50% 50%', scale: 0, rotation: -8 });
    tl.to(st, { scale: 1, rotation: -6, duration: 0.3, ease: 'back.out(3)' }, T(c.t) + 0.6);
    tl.to(el, { scale: 0, duration: 0.2, ease: 'back.in(2)' }, T(c.e) - 0.22);
  }
});

window.__timelines = window.__timelines || {};
window.__timelines['main'] = tl;

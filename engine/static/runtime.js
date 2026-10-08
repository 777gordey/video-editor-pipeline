/* Композиция версии: всё управляется ТОЛЬКО временем таймлайна (GSAP, paused).
   Никаких Date.now / Math.random / сети. Данные: window.PLAN_DATA (см. compose.py). */
(function () {
  const D = window.PLAN_DATA;
  const S = D.style, C = S.colors, words = D.words, plan = D.plan, DUR = D.dur;
  const tl = gsap.timeline({ paused: true });
  const $ = (id) => document.getElementById(id);
  const mk = (tag, cls, parent, html) => {
    const e = document.createElement(tag);
    if (cls) e.className = cls;
    if (html != null) e.innerHTML = html;
    if (parent) parent.appendChild(e);
    return e;
  };
  const esc = (s) => s.replace(/[&<>]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;" }[c]));
  const tidy = (w) => w.replace(/^[«"(]+|[»",;:.)]+$/g, "");   // знаки в конце слов на экране не нужны
  const ZM = { V1: 1.15, V2: 1.1, V3: 0.7, V4: 1.0, V5: 0.55 }[S.id];
  const F = { wide: 1.0, medium: 1.14, close: 1.34 };
  const emphSet = new Set(plan.emphasis);
  /* ширина символа (в em) по шрифту: подгоняем размер БЕЗ измерения DOM (шрифты могут не успеть загрузиться) */
  const CW = { V1: S.caps ? 0.82 : 0.66, V2: S.caps ? 0.98 : 0.8, V3: 0.6, V4: 0.74, V5: 0.64 }[S.id];
  const fitSize = (base, maxChars, maxW, mult) => Math.max(36, Math.min(base, maxW / (Math.max(maxChars, 1) * CW * (mult || 1))));

  /* ---------- fake multi-camera: cam (кадрирование+наезд) > snap (резкий зум/вип) ---------- */
  const cam = $("cam"), snap = $("snap");
  plan.cams.forEach((c, i) => {
    const t0 = c.t, t1 = i + 1 < plan.cams.length ? plan.cams[i + 1].t : DUR;
    const base = 1 + (F[c.framing] - 1) * ZM;
    const dx = (i % 2 ? -1 : 1) * (base - 1) * 70;
    const dy = -(base - 1) * 60;
    tl.set(cam, { scale: base, x: dx, y: dy }, t0);
    tl.to(cam, { scale: base * (1 + S.push), duration: Math.max(0.05, t1 - t0), ease: "none" }, t0);
    if (c.move === "whip") {
      tl.set(snap, { x: 300, filter: "blur(18px)" }, t0);
      tl.to(snap, { x: 0, filter: "blur(0px)", duration: 0.22, ease: "power3.out" }, t0);
      flash(t0, 0.5);
    } else if (i > 0 && (S.id === "V1" || S.id === "V2")) {
      flash(t0, 0.18);
    }
  });
  plan.snaps.forEach((s) => {
    tl.set(snap, { scale: 1.17 }, s.t);
    tl.to(snap, { scale: 1, duration: 0.34, ease: "power3.out" }, s.t);
  });
  function flash(t, a) {
    const f = $("flash");
    tl.set(f, { opacity: a }, t);
    tl.to(f, { opacity: 0, duration: 0.2, ease: "power1.out" }, t);
  }

  /* ---------- субтитры: слово за словом, акцентные слова крупнее и цветом ---------- */
  const capLayer = $("captions");
  plan.chunks.forEach((c, ci) => {
    const t0 = words[c.first].start;
    const nextStart = ci + 1 < plan.chunks.length ? words[plan.chunks[ci + 1].first].start : DUR;
    const t1 = Math.min(nextStart, words[c.last].end + 0.45);
    const box = mk("div", "chunk", capLayer);
    const toks = words.slice(c.first, c.last + 1).map((w) => tidy(w.w));
    const lng = Math.max(...toks.map((x) => x.length));
    const tot = toks.join(" ").length;
    box.style.fontSize = Math.min(fitSize(S.cap_size, lng, 860, 1.3), fitSize(S.cap_size, tot / 2, 860, 1.15)) + "px";
    const spans = [];
    const capFs = parseFloat(box.style.fontSize);
    for (let i = c.first; i <= c.last; i++) {
      const emph = emphSet.has(i);
      const sp = mk("span", "w" + (emph ? " emph" : ""), box, esc(tidy(words[i].w)));
      if (emph) sp.style.margin = "0 " + Math.round(0.11 * tidy(words[i].w).length * CW * capFs + 0.14 * capFs) + "px";   // scale 1.22 не должен наезжать на соседей
      spans.push([sp, words[i].start, emph]);
    }
    tl.set(box, { opacity: 1 }, t0);
    if (S.id === "V5") spans.forEach(([sp]) => tl.set(sp, { opacity: 1 }, t0));   // пилюля не должна быть пустой
    spans.forEach(([sp, ws, emph]) => {
      tl.set(sp, { opacity: 1, color: emph ? C.emph : C.accent }, ws);
      tl.fromTo(sp, { scale: emph ? 0.6 : 0.8 }, { scale: emph ? 1.22 : 1, duration: 0.14, ease: "back.out(2.4)", immediateRender: false }, ws);
      if (!emph) tl.set(sp, { color: C.text }, ws + 0.22);
    });
    tl.set(box, { opacity: 0 }, t1);
  });

  /* ---------- хук: первые 2 секунды, у каждой версии свой ---------- */
  const hookEl = $("hook");
  const hw = plan.hook.text.split(/\s+/);
  const T1 = plan.hook.t1;
  const hookBase = S.hook_style === "slam" ? 150 : S.hook_style === "chrome3d" ? 140 : 110;
  const hookMax = Math.max(...hw.map((x) => x.length));
  let hookSize = fitSize(hookBase, hookMax, 880, 1);
  if (S.hook_style === "slam") hookSize = Math.min(hookSize, 760 / (hw.length * 1.1));
  else hookSize = Math.min(hookSize, fitSize(hookBase, hw.join(" ").length / 3, 880, 1));
  hookEl.style.fontSize = hookSize + "px";
  const hookSpans = hw.map((w) => mk("span", "hw", hookEl, esc(S.caps ? w.toUpperCase() : w)));
  hookSpans.forEach((sp, i) => tl.set(sp, { opacity: 0 }, 0));
  const st = S.hook_style;
  if (st === "slam") {
    hookEl.classList.add("slam");
    hookSpans.forEach((sp, i) => {
      const t = 0.05 + i * 0.13;
      if (i % 2 === 1) sp.style.color = C.accent;
      tl.set(sp, { opacity: 1, scale: 2.6 }, t);
      tl.to(sp, { scale: 1, duration: 0.14, ease: "power4.in" }, t);
      tl.to(hookEl, { x: 0, duration: 0.01 }, t + 0.14);
      tl.fromTo(hookEl, { y: -14 }, { y: 0, duration: 0.1, ease: "power2.out", immediateRender: false }, t + 0.14);
    });
  } else if (st === "glitch") {
    hookEl.classList.add("glitch");
    hookSpans.forEach((sp, i) => {
      const t = 0.05 + i * 0.1;
      tl.set(sp, { opacity: 1, x: -14 }, t);
      tl.set(sp, { x: 10, opacity: 0.4 }, t + 0.04);
      tl.set(sp, { x: -5, opacity: 1 }, t + 0.08);
      tl.set(sp, { x: 0 }, t + 0.12);
    });
    for (let k = 0; k < 4; k++) {          // редкие мерцания неона
      const t = 0.9 + k * 0.28;
      tl.set(hookEl, { opacity: 0.35 }, t);
      tl.set(hookEl, { opacity: 1 }, t + 0.05);
    }
  } else if (st === "editorial") {
    hookEl.classList.add("editorial");
    const rule = $("hookrule");
    tl.fromTo(rule, { width: 0 }, { width: 460, duration: 0.8, ease: "power2.out", immediateRender: false }, 0.1);
    hookSpans.forEach((sp, i) => {
      const t = 0.15 + i * 0.12;
      tl.set(sp, { opacity: 0, y: 24 }, 0);
      tl.to(sp, { opacity: 1, y: 0, duration: 0.5, ease: "power2.out" }, t);
    });
  } else if (st === "chrome3d") {
    hookEl.classList.add("chrome3d");
    let ext = [];
    for (let k = 1; k <= 14; k++) ext.push(`0 ${k}px 0 rgb(${70 - k * 2},${80 - k * 2},${100 - k * 3})`);
    hookSpans.forEach((sp, i) => {
      sp.style.textShadow = ext.join(",") + ", 0 30px 40px rgba(0,0,0,.6)";
      const t = 0.05 + i * 0.14;
      tl.set(sp, { opacity: 1, rotationY: -80, transformPerspective: 900 }, t);
      tl.to(sp, { rotationY: 0, duration: 0.45, ease: "back.out(1.6)" }, t);
      tl.to(sp, { rotationY: 4, duration: Math.max(0.1, T1 - t - 0.5), ease: "sine.inOut" }, t + 0.45);
    });
  } else if (st === "pastel") {
    hookEl.classList.add("pastel");
    hookSpans.forEach((sp, i) => {
      const t = 0.1 + i * 0.12;
      tl.set(sp, { opacity: 1, y: 70, scale: 0.6 }, t);
      tl.to(sp, { y: 0, scale: 1, duration: 0.5, ease: "elastic.out(1,0.6)" }, t);
    });
  }
  tl.set(hookEl, { opacity: 1 }, 0.001);
  tl.to(hookEl, { opacity: 0, scale: 0.94, duration: 0.2, ease: "power1.in" }, T1 - 0.2);
  tl.set(hookEl, { visibility: "hidden" }, T1);

  /* ---------- глобус (canvas, ортографическая проекция, всё из t) ---------- */
  function makeGlobe(canvas, size) {
    canvas.width = canvas.height = size;
    const ctx = canvas.getContext("2d");
    // детерминированный «рой» точек на сфере
    let seed = 1234567;
    const rnd = () => ((seed = (seed * 1664525 + 1013904223) >>> 0) / 4294967296);
    const pts = [];
    for (let i = 0; i < 520; i++) {
      const lat = Math.asin(2 * rnd() - 1), lon = rnd() * Math.PI * 2;
      pts.push([lat, lon, 0.4 + rnd() * 0.6]);
    }
    const hubs = [];
    for (let i = 0; i < 7; i++) hubs.push([Math.asin(1.6 * rnd() - 0.8), rnd() * Math.PI * 2]);
    const R = size * 0.42, cx = size / 2, cy = size / 2, tilt = 0.38;
    const proj = (lat, lon, rot) => {
      let x = Math.cos(lat) * Math.sin(lon + rot), y = Math.sin(lat), z = Math.cos(lat) * Math.cos(lon + rot);
      const y2 = y * Math.cos(tilt) - z * Math.sin(tilt), z2 = y * Math.sin(tilt) + z * Math.cos(tilt);
      return [cx + x * R, cy - y2 * R, z2];
    };
    return function draw(rot) {
      ctx.clearRect(0, 0, size, size);
      const g = ctx.createRadialGradient(cx - R * 0.3, cy - R * 0.3, R * 0.1, cx, cy, R);
      g.addColorStop(0, C.accent + "55"); g.addColorStop(1, "#00000022");
      ctx.fillStyle = g; ctx.beginPath(); ctx.arc(cx, cy, R, 0, 7); ctx.fill();
      ctx.lineWidth = 1.6; ctx.strokeStyle = C.accent + "99";
      for (let lat = -60; lat <= 60; lat += 30) {
        ctx.beginPath();
        for (let k = 0; k <= 72; k++) {
          const [x, y, z] = proj(lat * Math.PI / 180, k * Math.PI / 36, rot);
          if (z > 0) { (k === 0 || ctx._pen !== 1) ? ctx.moveTo(x, y) : ctx.lineTo(x, y); ctx._pen = 1; } else ctx._pen = 0;
        }
        ctx.stroke(); ctx._pen = 0;
      }
      for (let lon = 0; lon < 360; lon += 30) {
        ctx.beginPath();
        let pen = 0;
        for (let k = -18; k <= 18; k++) {
          const [x, y, z] = proj(k * Math.PI / 36, lon * Math.PI / 180, rot);
          if (z > 0) { pen ? ctx.lineTo(x, y) : ctx.moveTo(x, y); pen = 1; } else pen = 0;
        }
        ctx.stroke();
      }
      ctx.shadowColor = C.accent; ctx.shadowBlur = 10;
      pts.forEach(([la, lo, s]) => {
        const [x, y, z] = proj(la, lo, rot);
        if (z < -0.1) return;
        ctx.fillStyle = z > 0 ? C.text : C.accent + "66";
        ctx.globalAlpha = z > 0 ? 0.35 + 0.65 * z : 0.25;
        ctx.beginPath(); ctx.arc(x, y, 2.2 * s * (0.6 + 0.6 * z), 0, 7); ctx.fill();
      });
      ctx.globalAlpha = 1;
      ctx.lineWidth = 3; ctx.strokeStyle = C.emph;
      for (let i = 0; i + 1 < hubs.length; i += 1) {         // дуги между «городами»
        const a = hubs[i], b = hubs[i + 1];
        ctx.beginPath(); let pen = 0;
        for (let k = 0; k <= 24; k++) {
          const f = k / 24, la = a[0] + (b[0] - a[0]) * f, lo = a[1] + (b[1] - a[1]) * f;
          const lift = 1 + 0.28 * Math.sin(Math.PI * f);
          const [x, y, z] = proj(la, lo, rot);
          const X = cx + (x - cx) * lift, Y = cy + (y - cy) * lift;
          if (z > 0) { pen ? ctx.lineTo(X, Y) : ctx.moveTo(X, Y); pen = 1; } else pen = 0;
        }
        ctx.stroke();
      }
      hubs.forEach((h) => {
        const [x, y, z] = proj(h[0], h[1], rot);
        if (z > 0) { ctx.fillStyle = C.emph; ctx.beginPath(); ctx.arc(x, y, 6, 0, 7); ctx.fill(); }
      });
      ctx.shadowBlur = 0;
    };
  }
  if (S.globe_behind) {                       // V4: вращающийся глобус ЗА мной
    const cv = $("globeBehind");
    const draw = makeGlobe(cv, 1000);
    const o = { r: 0 };
    draw(0);
    tl.to(o, { r: DUR * 0.45, duration: DUR, ease: "none", onUpdate: () => draw(o.r) }, 0);
  }

  /* ---------- графика по триггерным словам ---------- */
  const fx = $("graphics");
  const ICON = {
    check: '<path d="M20 52 L42 74 L82 26" />',
    warning: '<path d="M50 14 L90 84 L10 84 Z"/><path d="M50 40 V62 M50 71 V73"/>',
    money: '<circle cx="50" cy="50" r="34"/><path d="M58 36 C50 28 38 34 40 42 C42 52 60 48 60 58 C60 68 46 70 40 62 M50 24 V76"/>',
    rocket: '<path d="M50 12 C70 28 70 56 60 72 H40 C30 56 30 28 50 12 Z"/><circle cx="50" cy="42" r="7"/><path d="M40 72 L32 88 M60 72 L68 88"/>',
    bolt: '<path d="M56 10 L26 56 H48 L42 90 L74 40 H52 Z"/>',
    heart: '<path d="M50 84 C10 56 18 18 40 24 C46 26 50 32 50 32 C50 32 54 26 60 24 C82 18 90 56 50 84 Z"/>',
    clock: '<circle cx="50" cy="50" r="36"/><path d="M50 26 V52 L68 62"/>',
    star: '<path d="M50 10 L61 38 L90 40 L67 59 L75 88 L50 72 L25 88 L33 59 L10 40 L39 38 Z"/>',
    fire: '<path d="M50 10 C54 30 74 38 70 62 C68 78 58 88 50 88 C40 88 30 78 30 64 C30 52 38 46 42 38 C44 46 48 48 50 48 C52 36 48 24 50 10 Z"/>',
    target: '<circle cx="50" cy="50" r="36"/><circle cx="50" cy="50" r="20"/><circle cx="50" cy="50" r="5"/>',
  };
  plan.graphics.forEach((g, gi) => {
    const t0 = g.t, t1 = g.t + g.dur;
    const right = gi % 2 === 0;
    let box;
    if (g.kind === "icon") {
      box = mk("div", "g icon", fx, `<svg viewBox="0 0 100 100" width="150" height="150">${ICON[g.icon] || ICON.star}</svg>`);
      box.style.left = (right ? 700 : 140) + "px"; box.style.top = "470px";
    } else if (g.kind === "circle") {
      box = mk("div", "g circ", fx, `<div class="num">${g.num}</div>${g.text ? `<div class="lbl">${esc(g.text)}</div>` : ""}`);
      box.style.left = (right ? 640 : 110) + "px"; box.style.top = "430px";
    } else {
      const cv = mk("canvas", "g globe", fx);
      box = cv;
      cv.style.left = "290px"; cv.style.top = "300px";
      const draw = makeGlobe(cv, 500);
      const o = { r: 0 };
      draw(0);
      tl.to(o, { r: Math.PI * 1.2, duration: g.dur, ease: "none", onUpdate: () => draw(o.r) }, t0);
    }
    tl.set(box, { opacity: 1, scale: 0.2, rotation: right ? 14 : -14 }, t0);
    tl.to(box, { scale: 1, rotation: 0, duration: 0.38, ease: "back.out(2.4)" }, t0);
    tl.to(box, { opacity: 0, scale: 0.85, duration: 0.2, ease: "power1.in" }, t1 - 0.2);
    tl.set(box, { opacity: 0 }, t1);
  });

  /* ---------- общий хвост: длительность == длительности клипа ---------- */
  tl.set({}, {}, DUR);
  window.__timelines = window.__timelines || {};
  window.__timelines["main"] = tl;
})();

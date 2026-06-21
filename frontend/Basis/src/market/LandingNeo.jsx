/* Лендинг v3 (порт docs/Lending_new.zip) как экран платформы. Разметка эталона —
   landingHtml.js (CTA → data-route), стили — styles/landing.css (под .lp-scope,
   токены сведены к каноническим cc). Анимации прототипа (canvas-heat, reveal,
   count-up, ticker, матрица корреляций, mesh) воспроизведены в useEffect c очисткой.
   Тема — общий переключатель приложения; CTA — реальный роутинг. */
import React, { useEffect, useRef } from "react";
import "../styles/landing.css";
import LANDING_HTML from "./landingHtml";

const SUN = '<path d="M12 2v2.5M12 19.5V22M2 12h2.5M19.5 12H22M4.9 4.9l1.8 1.8M17.3 17.3l1.8 1.8M19.1 4.9l-1.8 1.8M6.7 17.3l-1.8 1.8" stroke-linecap="round"/><circle cx="12" cy="12" r="4.2"/>';
const MOON = '<path d="M20 14.5A8 8 0 1 1 9.5 4a6.5 6.5 0 0 0 10.5 10.5z" stroke-linejoin="round"/>';

export default function LandingNeo({ onNavigate, onOpenCompany, onShowAuth, theme, toggleTheme }) {
  const ref = useRef(null);

  // CTA-роутинг + переключатель темы (делегирование кликов)
  useEffect(() => {
    const el = ref.current;
    if (!el) return;
    const onClick = (e) => {
      const themeBtn = e.target.closest("#themeBtn");
      if (themeBtn) { e.preventDefault(); toggleTheme && toggleTheme(); return; }
      const a = e.target.closest("[data-route]");
      if (!a) return;
      e.preventDefault();
      const r = a.getAttribute("data-route");
      if (r === "companies") onNavigate && onNavigate("companies");
      else if (r === "screener") onNavigate && onNavigate("screener");
      else if (r === "rosn") onOpenCompany && onOpenCompany("ROSN");
      else if (r === "login") onShowAuth && onShowAuth();
    };
    el.addEventListener("click", onClick);
    return () => el.removeEventListener("click", onClick);
  }, [onNavigate, onOpenCompany, onShowAuth, toggleTheme]);

  // Иконка темы в лендинг-навбаре синхронна с темой приложения
  useEffect(() => {
    const el = ref.current; if (!el) return;
    const icon = el.querySelector("#thIcon");
    if (icon) icon.innerHTML = theme === "dark" ? SUN : MOON;
  }, [theme]);

  // Анимации прототипа (canvas/reveal/ticker/матрица/mesh) + очистка
  useEffect(() => {
    const root = ref.current;
    if (!root) return;
    const cleanups = [];
    const q = (s) => root.querySelector(s);
    const qa = (s) => Array.from(root.querySelectorAll(s));
    const reduce = matchMedia("(prefers-reduced-motion:reduce)").matches;

    // nav shrink (скролл может идти внутри .app-shell, а не в окне)
    const nav = q("#nav");
    const scroller = root.closest(".app-shell") || window;
    const getY = () => (scroller === window ? window.scrollY : scroller.scrollTop);
    const onScroll = () => { if (nav) nav.classList.toggle("stuck", getY() > 16); };
    scroller.addEventListener("scroll", onScroll, { passive: true });
    cleanups.push(() => scroller.removeEventListener("scroll", onScroll));

    // reveal
    const io = new IntersectionObserver((es) => es.forEach((e) => { if (e.isIntersecting) { e.target.classList.add("in"); io.unobserve(e.target); } }), { threshold: 0.14, rootMargin: "0px 0px -7% 0px" });
    qa(".rv").forEach((x) => io.observe(x));
    cleanups.push(() => io.disconnect());

    // count-up
    const cio = new IntersectionObserver((es) => es.forEach((e) => {
      if (!e.isIntersecting) return;
      const ele = e.target, to = +ele.dataset.count, suf = ele.dataset.suffix || "", t0 = performance.now();
      const stp = (now) => { const p = Math.min(1, (now - t0) / 1100); const v = Math.round(to * (1 - Math.pow(1 - p, 3))); ele.textContent = v.toLocaleString("ru-RU") + suf; if (p < 1) requestAnimationFrame(stp); };
      requestAnimationFrame(stp); cio.unobserve(ele);
    }), { threshold: 0.6 });
    qa("[data-count]").forEach((x) => cio.observe(x));
    cleanups.push(() => cio.disconnect());

    // ticker
    const tickerRow = q("#tickerRow");
    if (tickerRow) {
      const TK = [["SBER", "317,82", 1.4], ["GAZP", "128,05", -0.8], ["LKOH", "7 412", 0.3], ["ROSN", "564,20", 0.84], ["GMKN", "138,60", -1.6], ["YDEX", "4 188", 2.1], ["NVTK", "978,40", -2.1], ["PLZL", "14 320", 0.9], ["TATN", "648,00", 0.4], ["MOEX", "198,00", 1.1], ["MGNT", "5 104", -0.4], ["CHMF", "1 284", -0.7]];
      tickerRow.innerHTML = [...TK, ...TK].map(([t, p, c]) => `<span class="tk"><b>${t}</b><span class="px">${p}</span><span class="ch ${c >= 0 ? "up" : "dn"}">${c >= 0 ? "▲" : "▼"} ${Math.abs(c).toLocaleString("ru-RU")}%</span></span>`).join("");
    }

    // матрица корреляций (превью портфеля)
    const corr = q("#pvCorr");
    if (corr) {
      const labels = ["ROSN", "SBER", "GMKN", "YDEX", "PLZL", "MGNT"];
      const M = [[1, .42, .55, .18, .30, .12], [.42, 1, .38, .34, .22, .40], [.55, .38, 1, .20, .48, .10], [.18, .34, .20, 1, .15, .28], [.30, .22, .48, .15, 1, .08], [.12, .40, .10, .28, .08, 1]];
      let h = '<span class="cl"></span>';
      labels.forEach((l) => h += `<span class="cl top">${l.slice(0, 2)}</span>`);
      for (let i = 0; i < 6; i++) { h += `<span class="cl">${labels[i].slice(0, 2)}</span>`; for (let j = 0; j < 6; j++) { const v = M[i][j]; if (i === j) { h += '<span class="cc dg">1,0</span>'; } else { const col = v > 0.5 ? "var(--neg)" : v > 0.3 ? "var(--amber)" : "var(--pos)"; const pct = Math.round(18 + v * 52); h += `<span class="cc" style="background:color-mix(in srgb, ${col} ${pct}%, transparent)">${v.toFixed(1).replace(".", ",")}</span>`; } } }
      corr.innerHTML = h;
    }

    // canvas heat (дышащая карта)
    let raf = 0;
    const cv = q("#heat");
    if (cv && cv.getContext) {
      const cx = cv.getContext("2d");
      let cells = [], cw = 0, ch = 0;
      const DPR = Math.min(2, window.devicePixelRatio || 1);
      const palette = () => { const cs = getComputedStyle(root); return ["--heat-a", "--heat-b", "--heat-c", "--heat-d", "--heat-e", "--heat-f"].map((v) => cs.getPropertyValue(v).trim() || "#888"); };
      let pal = palette();
      const resize = () => {
        const r = cv.getBoundingClientRect(); cw = r.width; ch = r.height;
        cv.width = cw * DPR; cv.height = ch * DPR; cx.setTransform(DPR, 0, 0, DPR, 0, 0);
        const size = 34, gap = 5, cols = Math.ceil(cw / (size + gap)), rows = Math.ceil(ch / (size + gap)); cells = [];
        for (let y = 0; y < rows; y++) for (let x = 0; x < cols; x++) cells.push({ x: x * (size + gap), y: y * (size + gap), s: size, col: Math.floor(Math.random() * 6), ph: Math.random() * Math.PI * 2, sp: 0.6 + Math.random() * 0.9, base: 0.04 + Math.random() * 0.10 });
      };
      resize();
      window.addEventListener("resize", resize);
      cleanups.push(() => window.removeEventListener("resize", resize));
      if (!reduce) {
        const loop = (t) => {
          cx.clearRect(0, 0, cw, ch); const tt = t * 0.001;
          for (const c of cells) { const a = c.base + Math.max(0, Math.sin(tt * c.sp + c.ph)) * 0.16; cx.globalAlpha = a; cx.fillStyle = pal[c.col]; cx.beginPath(); const x = c.x, y = c.y, s = c.s; if (cx.roundRect) cx.roundRect(x, y, s, s, 6); else cx.rect(x, y, s, s); cx.fill(); }
          cx.globalAlpha = 1; raf = requestAnimationFrame(loop);
        };
        raf = requestAnimationFrame(loop);
      } else {
        cells.forEach((c) => { cx.globalAlpha = c.base + 0.08; cx.fillStyle = pal[c.col]; cx.fillRect(c.x, c.y, c.s, c.s); });
      }
    }
    cleanups.push(() => { if (raf) cancelAnimationFrame(raf); });

    // cursor mesh
    const meshes = qa(".mesh");
    if (meshes.length) {
      const onMove = (e) => { const x = (e.clientX / window.innerWidth * 100), y = (e.clientY / window.innerHeight * 60); meshes[0].style.setProperty("--mx", x + "%"); meshes[0].style.setProperty("--my", (y - 6) + "%"); };
      window.addEventListener("pointermove", onMove, { passive: true });
      cleanups.push(() => window.removeEventListener("pointermove", onMove));
    }

    return () => cleanups.forEach((fn) => fn());
  }, []);

  return <div className="cc-root lp-scope" ref={ref} dangerouslySetInnerHTML={{ __html: LANDING_HTML }} />;
}

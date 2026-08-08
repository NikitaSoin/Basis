import React, { useEffect, useRef, useState } from "react";
import "../styles/scroll-rail.css";

// =========================
// SCROLL RAIL — вертикальная линия-навигация справа для ДЛИННЫХ страниц
// (владелец 2026-08-08: «листаешь долго — нужна линия с точками, где что
// написано, видно куда перемещаешься, что ждёт ниже и что осталось выше»).
// Точки = секции контента: элементы [data-rail="Название"] и/или заголовки
// по selector. Позиции точек пропорциональны месту секции в документе
// (мини-карта, не равномерное оглавление); ползунок показывает текущее
// положение вьюпорта. Клик — плавный скролл к секции (reduced-motion → без
// анимации). <minCount секций или ≤1100px — рейл не рендерится вовсе.
// =========================
export function ScrollRail({ selector = "[data-rail], h2, h3", minCount = 4, deps = [], containerRef = null }) {
  const [items, setItems] = useState([]);
  const [active, setActive] = useState(0);
  const [progress, setProgress] = useState(0);
  const rebuildRef = useRef(null);

  useEffect(() => {
    let cancelled = false;
    const rebuild = () => {
      if (cancelled) return;
      const root = (containerRef && containerRef.current) || document;
      const els = Array.from(root.querySelectorAll(selector))
        .filter((el) => el.offsetParent !== null);
      const docH = Math.max(1, document.documentElement.scrollHeight);
      const seen = new Set();
      const its = [];
      for (const el of els) {
        const label = (el.getAttribute("data-rail") || el.textContent || "").trim().replace(/\s+/g, " ").slice(0, 48);
        if (!label || seen.has(label)) continue;
        seen.add(label);
        const top = el.getBoundingClientRect().top + window.scrollY;
        its.push({ label, top, pct: Math.min(97, Math.max(2, (top / docH) * 100)) });
      }
      setItems(its.length >= minCount ? its : []);
    };
    rebuildRef.current = rebuild;
    // контент дорисовывается асинхронно (данные грузятся) — пересобираем с
    // задержками и при изменении размера документа
    const t1 = setTimeout(rebuild, 400);
    const t2 = setTimeout(rebuild, 1600);
    let ro = null;
    try {
      ro = new ResizeObserver(() => { clearTimeout(rebuildRef.current?._t); rebuild(); });
      ro.observe(document.body);
    } catch { /* старые браузеры — хватит таймеров */ }
    return () => { cancelled = true; clearTimeout(t1); clearTimeout(t2); if (ro) ro.disconnect(); };
  }, deps); // eslint-disable-line

  useEffect(() => {
    if (!items.length) return;
    const onScroll = () => {
      const y = window.scrollY + window.innerHeight * 0.28;
      let a = 0;
      items.forEach((it, i) => { if (it.top <= y) a = i; });
      setActive(a);
      const docH = document.documentElement.scrollHeight - window.innerHeight;
      setProgress(docH > 0 ? Math.min(1, window.scrollY / docH) : 0);
    };
    onScroll();
    window.addEventListener("scroll", onScroll, { passive: true });
    window.addEventListener("resize", onScroll);
    return () => { window.removeEventListener("scroll", onScroll); window.removeEventListener("resize", onScroll); };
  }, [items]);

  if (!items.length) return null;
  const reduced = typeof window !== "undefined" && window.matchMedia
    && window.matchMedia("(prefers-reduced-motion: reduce)").matches;
  return (
    <nav className="srail" aria-label="Навигация по разделам страницы">
      <div className="srail-track" aria-hidden="true" />
      <div className="srail-cursor" style={{ top: `${2 + progress * 95}%` }} aria-hidden="true" />
      {items.map((it, i) => (
        <button key={it.label} type="button"
          className={"srail-dot" + (i === active ? " on" : "")}
          style={{ top: `${it.pct}%` }}
          onClick={() => window.scrollTo({ top: it.top - 76, behavior: reduced ? "auto" : "smooth" })}>
          <span className="srail-label">{it.label}</span>
        </button>
      ))}
    </nav>
  );
}

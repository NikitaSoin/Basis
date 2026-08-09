import React, { useEffect, useRef, useState } from "react";
import "../styles/scroll-rail.css";

// =========================
// SCROLL RAIL v2 — постоянно видимое ОГЛАВЛЕНИЕ справа для длинных страниц.
// v1 (точки с подписями по ховеру) забракован владельцем 2026-08-09: «при
// листании не вижу смены блока, надпись загораживает текст, хочу сразу видеть
// структуру/содержание целиком». Теперь: компактная панель со СПИСКОМ всех
// секций, активная подсвечена медью и следует за скроллом; клик — переход.
// Панель живёт в свободном правом поле (не поверх текста), ≤1359px скрыта.
// Секции: элементы [data-rail="Название"] и/или заголовки по selector.
// =========================
export function ScrollRail({ selector = "[data-rail], h2, h3", minCount = 4, deps = [], containerRef = null }) {
  const [items, setItems] = useState([]);
  const [active, setActive] = useState(0);
  const listRef = useRef(null);

  useEffect(() => {
    let cancelled = false;
    const rebuild = () => {
      if (cancelled) return;
      const root = (containerRef && containerRef.current) || document;
      const els = Array.from(root.querySelectorAll(selector))
        .filter((el) => el.offsetParent !== null && !el.closest(".srail"));
      const seen = new Set();
      const its = [];
      for (const el of els) {
        const label = (el.getAttribute("data-rail") || el.textContent || "").trim().replace(/\s+/g, " ").slice(0, 60);
        if (!label || seen.has(label)) continue;
        seen.add(label);
        its.push({ label, top: el.getBoundingClientRect().top + window.scrollY });
      }
      setItems(its.length >= minCount ? its : []);
    };
    // контент дорисовывается асинхронно — пересборка с задержками и по росту документа
    const t1 = setTimeout(rebuild, 400);
    const t2 = setTimeout(rebuild, 1600);
    let ro = null;
    try {
      ro = new ResizeObserver(rebuild);
      ro.observe(document.body);
    } catch { /* старые браузеры — хватит таймеров */ }
    return () => { cancelled = true; clearTimeout(t1); clearTimeout(t2); if (ro) ro.disconnect(); };
  }, deps); // eslint-disable-line

  useEffect(() => {
    if (!items.length) return;
    const onScroll = () => {
      // якорь — верхняя треть вьюпорта: секция «текущая», пока её заголовок выше этой линии
      const y = window.scrollY + window.innerHeight * 0.33;
      let a = 0;
      items.forEach((it, i) => { if (it.top <= y) a = i; });
      setActive(a);
    };
    onScroll();
    window.addEventListener("scroll", onScroll, { passive: true });
    return () => window.removeEventListener("scroll", onScroll);
  }, [items]);

  // активный пункт всегда виден внутри панели (длинные оглавления скроллятся)
  useEffect(() => {
    const el = listRef.current && listRef.current.querySelector(".srail-item.on");
    if (el && el.scrollIntoView) el.scrollIntoView({ block: "nearest" });
  }, [active]);

  if (!items.length) return null;
  const reduced = typeof window !== "undefined" && window.matchMedia
    && window.matchMedia("(prefers-reduced-motion: reduce)").matches;
  return (
    <nav className="srail" aria-label="Содержание страницы" ref={listRef}>
      <div className="srail-title">Содержание</div>
      {items.map((it, i) => (
        <button key={it.label} type="button"
          className={"srail-item" + (i === active ? " on" : "")}
          onClick={() => window.scrollTo({ top: it.top - 76, behavior: reduced ? "auto" : "smooth" })}>
          {it.label}
        </button>
      ))}
    </nav>
  );
}

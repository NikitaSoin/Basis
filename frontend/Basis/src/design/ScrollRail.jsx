import React, { useEffect, useRef, useState } from "react";
import "../styles/scroll-rail.css";

// =========================
// SCROLL RAIL v3 — «Нить содержания» (макет одобрен владельцем 2026-08-10).
// Зарезервированная правая колонка до края экрана: серая направляющая, медная
// нить-прогресс по мере чтения, точки-секции (пройдено/текущее/впереди),
// названия + постоянные описания «что я здесь получу», счётчик снизу,
// кнопка «скрыть» для чтения на всю ширину (состояние в localStorage).
// Место резервируется padding-right на body — контент не перекрывается никогда
// (v2 наезжала на цену карточки). ≤1180px рейл не рендерится вовсе.
// =========================

const W_OPEN = 248, W_MIN = 30;

// описания «что я получу» для известных блоков платформы (fallback — без описания)
const DESC = {
  "Вышел отчёт": "Свежий разбор отчётности: цифры и контекст",
  "Что мы увидели": "Суждение Basis по событию — не пересказ",
  "Справедливая цена по методике Basis": "Модельная оценка и потенциал к рынку",
  "Почему справедливая цена такая": "Разбор по слоям: страна, институты, дивиденды",
  "Аналитическая заметка": "Сводный взгляд аналитика и что с этим делать",
  "Ключевые метрики": "Живые мультипликаторы от текущей цены",
  "Оценка ситуации": "Состояние отраслей и что это значит для рынка",
  "Макрорежим сейчас": "Ставка, инфляция, курс — и эффект для компании",
  "Состав портфеля": "Позиции, веса и агрегированная таблица",
  "Риск и доходность": "VaR/CVaR, волатильность и вклад позиций",
};

function _cleanLabel(el) {
  // склейка «Что мы увиделисуждение» (скрин владельца): заголовок содержит
  // вложенные чипы-теги — берём data-rail, иначе ТОЛЬКО прямые текстовые узлы,
  // иначе первый вложенный элемент
  const attr = el.getAttribute("data-rail");
  if (attr) return attr.trim();
  const direct = Array.from(el.childNodes)
    .filter((n) => n.nodeType === 3)
    .map((n) => n.textContent).join(" ").replace(/\s+/g, " ").trim();
  if (direct) return direct.slice(0, 60);
  const first = el.firstElementChild;
  return ((first && first.textContent) || el.textContent || "")
    .replace(/\s+/g, " ").trim().slice(0, 60);
}

export function ScrollRail({ selector = "[data-rail], h2, h3", minCount = 4, deps = [], containerRef = null }) {
  const [items, setItems] = useState([]);
  const [active, setActive] = useState(0);
  const [progress, setProgress] = useState(0);
  const [hidden, setHidden] = useState(() => {
    try { return localStorage.getItem("srail.hidden") === "1"; } catch { return false; }
  });
  const [narrow, setNarrow] = useState(() => typeof window !== "undefined" && window.innerWidth <= 1180);
  const listRef = useRef(null);

  useEffect(() => {
    const onR = () => setNarrow(window.innerWidth <= 1180);
    window.addEventListener("resize", onR);
    return () => window.removeEventListener("resize", onR);
  }, []);

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
        const label = _cleanLabel(el);
        if (!label || seen.has(label)) continue;
        seen.add(label);
        its.push({
          label,
          desc: el.getAttribute("data-rail-desc") || DESC[label] || null,
          top: el.getBoundingClientRect().top + window.scrollY,
        });
      }
      setItems(its.length >= minCount ? its : []);
    };
    const t1 = setTimeout(rebuild, 400);
    const t2 = setTimeout(rebuild, 1600);
    let ro = null;
    try { ro = new ResizeObserver(rebuild); ro.observe(document.body); } catch { /* таймеров хватит */ }
    return () => { cancelled = true; clearTimeout(t1); clearTimeout(t2); if (ro) ro.disconnect(); };
  }, deps); // eslint-disable-line

  // резервируем место под рейл на body — контент никогда не перекрывается
  const visible = items.length > 0 && !narrow;
  useEffect(() => {
    if (!visible) { document.body.style.paddingRight = ""; return; }
    document.body.style.paddingRight = (hidden ? W_MIN : W_OPEN) + "px";
    return () => { document.body.style.paddingRight = ""; };
  }, [visible, hidden]);

  useEffect(() => {
    if (!items.length) return;
    const onScroll = () => {
      const doc = document.documentElement;
      const denom = doc.scrollHeight - window.innerHeight;
      setProgress(denom > 0 ? Math.min(1, window.scrollY / denom) : 0);
      const anchor = window.scrollY + window.innerHeight * 0.33;
      let a = 0;
      items.forEach((it, i) => { if (it.top <= anchor) a = i; });
      setActive(a);
    };
    onScroll();
    window.addEventListener("scroll", onScroll, { passive: true });
    return () => window.removeEventListener("scroll", onScroll);
  }, [items]);

  useEffect(() => {
    const el = listRef.current && listRef.current.querySelector(".srail-li.on");
    if (el && el.scrollIntoView) el.scrollIntoView({ block: "nearest" });
  }, [active]);

  if (!visible) return null;
  const reduced = typeof window !== "undefined" && window.matchMedia
    && window.matchMedia("(prefers-reduced-motion: reduce)").matches;
  const toggle = () => setHidden((v) => {
    try { localStorage.setItem("srail.hidden", v ? "0" : "1"); } catch { /* noop */ }
    return !v;
  });

  if (hidden) {
    return (
      <button type="button" className="srail-min" onClick={toggle}
        title="Показать содержание" aria-label="Показать содержание страницы">
        <span className="srail-min-bar" style={{ height: `${Math.max(4, progress * 100)}%` }} aria-hidden="true" />
        <span className="srail-min-label">Содержание</span>
      </button>
    );
  }
  return (
    <nav className="srail" aria-label="Содержание страницы">
      <div className="srail-head">
        <span className="srail-eyebrow">Содержание</span>
        <button type="button" className="srail-hide" onClick={toggle}
          title="Скрыть — читать на всю ширину" aria-label="Скрыть содержание">
          <svg width="13" height="13" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round"><path d="M6 3.5L10.5 8 6 12.5" /></svg>
        </button>
      </div>
      <div className="srail-threadwrap" ref={listRef}>
        <span className="srail-thread" style={{ height: `${progress * 100}%` }} aria-hidden="true" />
        <ol className="srail-list">
          {items.map((it, i) => (
            <li key={it.label} className={"srail-li" + (i === active ? " on" : i < active ? " done" : "")}>
              <button type="button" onClick={() => window.scrollTo({ top: it.top - 76, behavior: reduced ? "auto" : "smooth" })}>
                <span className="srail-name">{it.label}</span>
                {it.desc && <span className="srail-gain">{it.desc}</span>}
              </button>
            </li>
          ))}
        </ol>
      </div>
      <div className="srail-foot">
        <span className="srail-num">{active + 1}</span>/<span className="srail-num">{items.length}</span>
        {" · "}<span className="srail-num">{Math.round(progress * 100)}%</span>
      </div>
    </nav>
  );
}

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

// «Вышел отчётфакт2025 · МСФО» (скрин владельца): заголовок = иконка + имя +
// чипы тегов + мета-строка в одном h3. Вырезаем служебное и берём чистое имя.
const _DROP = ".tag,.hmeta,.chip,.badge,.cc-tag,.sc-chip,.obs-tag,svg,sup,time";
function _cleanLabel(el) {
  const attr = el.getAttribute("data-rail");
  if (attr) return attr.trim();
  let txt = "";
  try {
    const c = el.cloneNode(true);
    c.querySelectorAll(_DROP).forEach((n) => n.remove());
    txt = c.textContent || "";
  } catch { txt = el.textContent || ""; }
  return txt.replace(/\s+/g, " ").trim().slice(0, 58);
}

// краткое «что я здесь получу»: словарь → атрибут → первое предложение секции
function _describe(el, label) {
  if (el.getAttribute("data-rail-desc")) return el.getAttribute("data-rail-desc");
  if (DESC[label]) return DESC[label];
  const host = el.closest(".card, section, .obs-panel, .pf-panel, .cc-card") || el.parentElement;
  if (!host) return null;
  const p = host.querySelector("p, li, .cc-lead, .obs-lead");
  if (!p) return null;
  const t = (p.textContent || "").replace(/\s+/g, " ").trim();
  if (t.length < 12) return null;
  const cut = t.slice(0, 78);
  return (t.length > 78 ? cut.replace(/[\s,;:.–-]+\S*$/, "") + "…" : cut);
}

// контейнер прокрутки: у платформы контент местами скроллится не окном
function _scrollHost(el) {
  let n = el && el.parentElement;
  while (n && n !== document.body) {
    const st = getComputedStyle(n);
    if (/(auto|scroll)/.test(st.overflowY) && n.scrollHeight > n.clientHeight + 4) return n;
    n = n.parentElement;
  }
  return null; // окно
}

// customItems — готовый список пунктов [{label, desc, onClick, active}] для
// экранов без секций-заголовков в потоке (Рынок: содержание = сектора рынка,
// в описании крупные тикеры; клик выбирает сектор). Владелец 2026-08-10.
export function ScrollRail({ selector = "[data-rail], h2, h3", minCount = 4, deps = [], containerRef = null, customItems = null, title = "Содержание", minWidth = 1180 }) {
  const [items, setItems] = useState([]);
  const [active, setActive] = useState(0);
  const [progress, setProgress] = useState(0);
  const [hidden, setHidden] = useState(() => {
    try { return localStorage.getItem("srail.hidden") === "1"; } catch { return false; }
  });
  const [narrow, setNarrow] = useState(() => typeof window !== "undefined" && window.innerWidth <= minWidth);
  const listRef = useRef(null);
  const hostRef = useRef(null);

  useEffect(() => {
    const onR = () => setNarrow(window.innerWidth <= minWidth);
    window.addEventListener("resize", onR);
    return () => window.removeEventListener("resize", onR);
  }, []);

  useEffect(() => {
    if (customItems) { setItems(customItems.map((it) => ({ ...it, el: null }))); return undefined; }
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
        if (!label || label.length < 3 || seen.has(label)) continue;
        seen.add(label);
        // храним ЭЛЕМЕНТ: позиции читаются на лету. Кэш top ломался, когда
        // данные дорисовывались после сборки списка — рейл замирал (владелец
        // 2026-08-10: «при пролистывании ничего не происходит, клик не ведёт»)
        its.push({ label, desc: _describe(el, label), el });
      }
      setItems(its.length >= minCount ? its : []);
    };
    const t1 = setTimeout(rebuild, 400);
    const t2 = setTimeout(rebuild, 1600);
    let ro = null;
    try { ro = new ResizeObserver(rebuild); ro.observe(document.body); } catch { /* таймеров хватит */ }
    return () => { cancelled = true; clearTimeout(t1); clearTimeout(t2); if (ro) ro.disconnect(); };
  }, deps); // eslint-disable-line

  // Резерв места — на КОНТЕЙНЕРЕ страницы, не на body: padding на body сжимал
  // и верхнюю навигацию платформы (владелец 2026-08-10: «сайдбар съехал»).
  const visible = items.length > 0 && !narrow;
  useEffect(() => {
    const host = items.length
      ? ((items[0].el && items[0].el.closest(".cc-root, .obs-main, .pf-main, .mkt-main, .mk-screen, .sc-screen, .app-main-top"))
         || document.querySelector(".mkt-main, .obs-main, .pf-main, .cc-root, .sc-screen"))
      : null;
    if (!visible || !host) return undefined;
    const prev = host.style.paddingRight;
    host.style.paddingRight = (hidden ? W_MIN : W_OPEN) + "px";
    return () => { host.style.paddingRight = prev; };
  }, [visible, hidden, items]);

  useEffect(() => {
    if (!items.length || !items[0].el) return undefined;
    const host = _scrollHost(items[0].el);
    hostRef.current = host;
    const onScroll = () => {
      const vh = host ? host.clientHeight : window.innerHeight;
      const sTop = host ? host.scrollTop : window.scrollY;
      const sH = host ? host.scrollHeight : document.documentElement.scrollHeight;
      const denom = sH - vh;
      setProgress(denom > 4 ? Math.min(1, Math.max(0, sTop / denom)) : 0);
      // позиция секции относительно вьюпорта — на лету, без кэша
      const line = vh * 0.33 + (host ? host.getBoundingClientRect().top : 0);
      let a = 0;
      items.forEach((it, i) => {
        const r = it.el.getBoundingClientRect();
        if (r.top <= line) a = i;
      });
      setActive(a);
    };
    onScroll();
    const target = host || window;
    target.addEventListener("scroll", onScroll, { passive: true });
    window.addEventListener("resize", onScroll);
    return () => { target.removeEventListener("scroll", onScroll); window.removeEventListener("resize", onScroll); };
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
        <span className="srail-eyebrow">{title}</span>
        <button type="button" className="srail-hide" onClick={toggle}
          title="Скрыть — читать на всю ширину" aria-label="Скрыть содержание">
          <svg width="13" height="13" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round"><path d="M6 3.5L10.5 8 6 12.5" /></svg>
        </button>
      </div>
      <div className="srail-threadwrap" ref={listRef}>
        <span className="srail-thread" style={{ height: `${progress * 100}%` }} aria-hidden="true" />
        <ol className="srail-list">
          {items.map((it, i) => (
            <li key={it.label} className={"srail-li" + (customItems
              ? (it.active ? " on" : "")
              : (i === active ? " on" : i < active ? " done" : ""))}>
              <button type="button" onClick={() => {
                if (it.onClick) { it.onClick(); return; }
                const host = hostRef.current;
                const behavior = reduced ? "auto" : "smooth";
                if (host) host.scrollTo({ top: host.scrollTop + it.el.getBoundingClientRect().top - host.getBoundingClientRect().top - 20, behavior });
                else window.scrollTo({ top: window.scrollY + it.el.getBoundingClientRect().top - 84, behavior });
              }}>
                <span className="srail-name">{it.label}</span>
                {it.desc && <span className="srail-gain">{it.desc}</span>}
              </button>
            </li>
          ))}
        </ol>
      </div>
      <div className="srail-foot">
        {customItems
          ? <><span className="srail-num">{items.length}</span> разделов</>
          : <><span className="srail-num">{active + 1}</span>/<span className="srail-num">{items.length}</span>
              {" · "}<span className="srail-num">{Math.round(progress * 100)}%</span></>}
      </div>
    </nav>
  );
}

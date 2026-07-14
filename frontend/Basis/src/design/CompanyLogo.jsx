import { useState, useEffect } from "react";
import { catFor } from "./PortfolioViz";

const apiBase = () => process.env.REACT_APP_API_URL || "http://localhost:8000";

// ── Логотипы компаний (бренды Т-Инвестиций) ──
// Карта {ticker: url} тянется ОДИН раз на сессию (module-level кэш + общий promise),
// картинки кэшируются браузером/CDN — внешний источник не дёргается на каждый рендер.
let _logoMap = null;
let _logoPromise = null;
function useCompanyLogos() {
  const [map, setMap] = useState(_logoMap);
  useEffect(() => {
    if (_logoMap) { if (!map) setMap(_logoMap); return; }
    if (!_logoPromise) {
      _logoPromise = fetch(`${apiBase()}/api/companies/logos`).then((r) => (r.ok ? r.json() : {})).catch(() => ({}));
    }
    let alive = true;
    _logoPromise.then((m) => { _logoMap = m || {}; if (alive) setMap(_logoMap); });
    return () => { alive = false; };
  }, []);
  return map || {};
}

// Логотип компании: цветная картинка бренда, при отсутствии/ошибке — аккуратный
// плейсхолдер с инициалами в категориальном цвете (вёрстка не ломается).
export function CompanyLogo({ ticker, name, size = 36, className = "" }) {
  const logos = useCompanyLogos();
  const [err, setErr] = useState(false);
  const url = ticker ? logos[ticker] : null;
  const cat = catFor(ticker || name || "");
  const initials = String(name || ticker || "").replace(/^(ПАО|ОАО|АО|ПJSC)\s+/i, "").trim().slice(0, 2).toUpperCase();
  if (url && !err) {
    return (
      <img
        src={url} alt="" width={size} height={size} loading="lazy" onError={() => setErr(true)}
        className={`tw-rounded-md tw-object-contain tw-bg-white tw-shrink-0 tw-border tw-border-border-subtle ${className}`}
        style={{ width: size, height: size, padding: 2 }}
      />
    );
  }
  return (
    <span
      aria-hidden="true"
      className={`tw-flex tw-items-center tw-justify-center tw-shrink-0 tw-rounded-md tw-font-semibold ${className}`}
      style={{ width: size, height: size, fontSize: Math.round(size * 0.36), background: `var(--cat-${cat}-soft)`, color: `var(--cat-${cat})`, border: `1px solid var(--cat-${cat}-soft)` }}
    >
      {initials}
    </span>
  );
}

// ── Логотипы прочих инструментов (облигации/фонды/фьючерсы/валюта) ──
// Отдельная карта {ISIN-или-secid: url} — облигация не имеет тикера компании
// (ключ ISIN), у фондов/фьючерсов/валюты тикер Т-Инвестиций = наш secid.
// Тот же паттерн кэша, что useCompanyLogos, но отдельный эндпоинт: это
// логотип САМОГО инструмента у брокера, не обязательно компании-эмитента.
let _instrumentLogoMap = null;
let _instrumentLogoPromise = null;
function useInstrumentLogos() {
  const [map, setMap] = useState(_instrumentLogoMap);
  useEffect(() => {
    if (_instrumentLogoMap) { if (!map) setMap(_instrumentLogoMap); return; }
    if (!_instrumentLogoPromise) {
      _instrumentLogoPromise = fetch(`${apiBase()}/api/companies/instrument-logos`).then((r) => (r.ok ? r.json() : {})).catch(() => ({}));
    }
    let alive = true;
    _instrumentLogoPromise.then((m) => { _instrumentLogoMap = m || {}; if (alive) setMap(_instrumentLogoMap); });
    return () => { alive = false; };
  }, []);
  return map || {};
}

// id — ISIN (облигации) или secid (фонды/фьючерсы/валюта). Тот же фолбэк на
// инициалы, что CompanyLogo, если картинки для конкретного инструмента нет.
export function InstrumentLogo({ id, name, size = 36, className = "" }) {
  const logos = useInstrumentLogos();
  const [err, setErr] = useState(false);
  const url = id ? logos[id] : null;
  const cat = catFor(id || name || "");
  const initials = String(name || id || "").replace(/^(ПАО|ОАО|АО|ПJSC)\s+/i, "").trim().slice(0, 2).toUpperCase();
  if (url && !err) {
    return (
      <img
        src={url} alt="" width={size} height={size} loading="lazy" onError={() => setErr(true)}
        className={`tw-rounded-md tw-object-contain tw-bg-white tw-shrink-0 tw-border tw-border-border-subtle ${className}`}
        style={{ width: size, height: size, padding: 2 }}
      />
    );
  }
  return (
    <span
      aria-hidden="true"
      className={`tw-flex tw-items-center tw-justify-center tw-shrink-0 tw-rounded-md tw-font-semibold ${className}`}
      style={{ width: size, height: size, fontSize: Math.round(size * 0.36), background: `var(--cat-${cat}-soft)`, color: `var(--cat-${cat})`, border: `1px solid var(--cat-${cat}-soft)` }}
    >
      {initials}
    </span>
  );
}

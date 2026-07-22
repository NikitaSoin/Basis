import React, { useEffect, useRef, useState } from "react";
import { FlaskConical, Send, RotateCcw } from "lucide-react";
import { Card, Badge, Delta } from "../design/primitives";
import { ImpactBar } from "../design/PortfolioViz";
import "../styles/stress-test.css";

// StressTestView v3 — «Стресс-тестирование» как инструмент, не анкета (владелец,
// 2026-07-23: «хочется, чтобы хотелось пробовать новые сценарии и смотреть что
// будет» — редизайн по интерактивному прототипу). Ставка/курс/нефть теперь
// слайдеры с живым (debounce) пересчётом через уже быстрый /stress-test/numeric
// (без LLM) — карта рынка и лидерборд перекрашиваются на лету. Свободный текст
// («что если...») остаётся отдельным путём через LLM-парсер: КОГДА он извлекает
// явные числовые уровни — слайдеры визуально едут в интерпретированную позицию
// (честно — только когда backend реально это прислал, не выдумываем координаты
// на фронте). Пресеты — качественная факторная модель (санкции/конфликт/спрос),
// у нее нет числовых ставка/курс/нефть эквивалентов в движке — не пытаемся
// натянуть их на слайдеры, остаются отдельным результатом (QualTable), как раньше.

const BUCKETS = [
  { min: 8, label: "▲▲", cls: "bs-wind-up", title: "сильно позитивно" },
  { min: 2, label: "▲", cls: "bs-wind-up", title: "позитивно" },
  { min: -2, label: "─", cls: "bs-wind-neutral", title: "нейтрально / слабо" },
  { min: -8, label: "▼", cls: "bs-wind-down", title: "негативно" },
  { min: -Infinity, label: "▼▼", cls: "bs-wind-down", title: "сильно негативно" },
];
function bucketOf(pct) {
  for (const b of BUCKETS) if (pct >= b.min) return b;
  return BUCKETS[BUCKETS.length - 1];
}

function DeltaCell({ m }) {
  if (!m || m.delta_bn == null) return <span className="tw-text-text-tertiary">—</span>;
  return (
    <span className="tw-inline-flex tw-items-baseline tw-gap-1.5">
      <Delta value={m.delta_bn} suffix="млрд ₽" decimals={1} />
      {m.pct_of_base != null && (
        <span className="tw-text-[11px] tw-text-text-tertiary">
          ({m.pct_of_base > 0 ? "+" : ""}{m.pct_of_base}%)
        </span>
      )}
    </span>
  );
}

// Ранжирование «кто пострадает/выиграет сильнее всего» — сигнальный слой ПЕРЕД
// голой таблицей чисел (конституция: «вердикт поверх данных», голая таблица без
// интерпретации не считается готовым экраном).
function rankByImpact(companies, metric = "net_profit") {
  return companies
    .filter((c) => c.metrics?.[metric]?.delta_bn != null)
    .sort((a, b) => Math.abs(b.metrics[metric].delta_bn) - Math.abs(a.metrics[metric].delta_bn));
}

function ImpactSignal({ numeric }) {
  const ranked = rankByImpact(numeric.companies, "net_profit");
  if (!ranked.length) return null;
  const worst = ranked.filter((c) => c.metrics.net_profit.delta_bn < 0).slice(0, 5);
  const best = ranked.filter((c) => c.metrics.net_profit.delta_bn > 0).slice(0, 5);
  const maxAbs = Math.max(1, ...ranked.slice(0, 8).map((c) => Math.abs(c.metrics.net_profit.delta_bn)));
  const Row = ({ c }) => (
    <div className="tw-flex tw-items-center tw-gap-3 tw-py-1">
      <span className="tw-font-mono tw-text-[12px] tw-text-text-secondary tw-w-16 tw-shrink-0">{c.ticker}</span>
      <div className="tw-flex-1"><ImpactBar value={c.metrics.net_profit.delta_bn} max={maxAbs} /></div>
      <Delta value={c.metrics.net_profit.delta_bn} suffix="млрд ₽" className="tw-w-28 tw-justify-end" />
    </div>
  );
  return (
    <Card header={<span className="tw-flex tw-items-center tw-gap-2">Кто пострадает сильнее всего <span className="bs-tag-estimate">оценка</span></span>}>
      <div className="tw-flex tw-flex-wrap tw-gap-3 tw-mb-4">
        <div className="bs-chip-stat">
          <span className="bs-cs-lbl">Задет фактором</span>
          <span className="bs-cs-val">{ranked.length} из {numeric.companies.length}</span>
        </div>
        {worst[0] && (
          <div className="bs-chip-stat">
            <span className="bs-cs-lbl">Хуже всего</span>
            <span className="bs-cs-val" style={{ color: "var(--bs-down)" }}>
              {worst[0].ticker} · {worst[0].metrics.net_profit.pct_of_base != null ? `${worst[0].metrics.net_profit.pct_of_base}%` : `${worst[0].metrics.net_profit.delta_bn} млрд ₽`}
            </span>
          </div>
        )}
      </div>
      <div className="tw-grid tw-grid-cols-1 sm:tw-grid-cols-2 tw-gap-x-8">
        <div>{worst.map((c) => <Row key={c.ticker} c={c} />)}</div>
        <div>{best.map((c) => <Row key={c.ticker} c={c} />)}</div>
      </div>
    </Card>
  );
}

// Карта рынка — порт интерактивного прототипа (владелец, 2026-07-23: «не
// совсем как в демо — цвета плит не те, расположение»): секторные строки,
// плитки flex-grow по весу внутри строки, цвет — плавный color-mix от
// нейтрального к --success/--danger, а не мозаичный грид общего Treemap.
// Веса — грубая эвристика (голубые фишки крупнее): числового market_cap в
// ответе /numeric нет, это визуальная пропорция, не точный вес индекса.
const MAP_MAX_PCT = 40; // насыщенность цвета: |pct| ≥ этого — уже максимум
function mapColorFor(pct) {
  const m = Math.max(-MAP_MAX_PCT, Math.min(MAP_MAX_PCT, pct)) / MAP_MAX_PCT;
  const tone = m >= 0 ? "var(--success)" : "var(--danger)";
  return `color-mix(in srgb, ${tone} ${Math.round(Math.abs(m) * 85)}%, var(--bg-hover))`;
}
function mapTextColorFor(pct) {
  if (Math.abs(pct) < 3) return "var(--text-secondary)";
  return pct >= 0 ? "var(--success)" : "var(--danger)";
}

function StressMap({ numeric }) {
  const ranked = rankByImpact(numeric.companies, "net_profit").slice(0, 30);
  if (!ranked.length) return null;
  const bySector = new Map();
  for (const c of ranked) {
    const sector = c.sector || "Другое";
    if (!bySector.has(sector)) bySector.set(sector, []);
    bySector.get(sector).push(c);
  }
  return (
    <Card header={<span className="tw-flex tw-items-center tw-gap-2">Карта рынка <span className="bs-tag-estimate">оценка</span></span>}>
      <div className="st-map">
        {[...bySector.entries()].map(([sector, companies]) => (
          <React.Fragment key={sector}>
            <div className="st-sector-lbl">{sector}</div>
            <div className="st-map-row">
              {companies.map((c) => {
                const pct = c.metrics.net_profit.pct_of_base
                  ?? (c.metrics.net_profit.delta_bn > 0 ? 15 : -15);
                const weight = c.is_blue_chip ? 3 : 1;
                return (
                  <div
                    key={c.ticker}
                    className={`st-tile${weight <= 1 ? " st-tile-small" : ""}`}
                    style={{ flexGrow: weight, background: mapColorFor(pct), color: mapTextColorFor(pct) }}
                    title={`${c.name} · ${pct >= 0 ? "+" : ""}${pct.toFixed(1)}%`}
                  >
                    <span className="st-tile-tk">{c.ticker}</span>
                    <span className="st-tile-pc">{pct >= 0 ? "▲" : "▼"} {Math.abs(pct).toFixed(1)}%</span>
                  </div>
                );
              })}
            </div>
          </React.Fragment>
        ))}
      </div>
      <div className="tw-mt-3 tw-text-[11px] tw-text-text-tertiary">
        Размер плитки — грубо, голубые фишки крупнее (веса капитализации в этом контуре нет). Цвет — Δ чистой прибыли, % от базы года.
      </div>
    </Card>
  );
}

// TATN/TATNP, MFGS/MFGSP и т.п. — обычка+префа одного эмитента с идентичными
// коэффициентами чувствительности задваивают список без новой информации;
// схлопываем визуально в одну строку с пометкой доп. тикеров.
function dedupeByIssuer(companies) {
  const seen = new Map();
  for (const c of companies) {
    const key = c.name.replace(/\s*(?:ПАО|АО|"|им\.\s*[\wа-яё.\s]+)\s*$/gi, "").trim();
    if (!seen.has(key)) seen.set(key, { ...c, _also: [] });
    else seen.get(key)._also.push(c.ticker);
  }
  return [...seen.values()];
}

function NumericTable({ numeric }) {
  const [showAll, setShowAll] = useState(false);
  const deduped = dedupeByIssuer(numeric.companies);
  const list = showAll ? deduped : deduped.slice(0, 20);
  return (
    <Card header={<span className="tw-flex tw-items-center tw-gap-2">
      Эффект на финансовые показатели (за год, к базе последнего отчётного года)
      <span className="bs-tag-estimate">оценка</span>
    </span>}>
      <div className="tw-overflow-x-auto">
        <table className="tw-w-full tw-text-[13px]">
          <thead>
            <tr className="tw-text-text-tertiary tw-text-[11px] tw-uppercase tw-tracking-wide">
              <th className="tw-text-left tw-font-semibold tw-pb-2">Компания</th>
              <th className="tw-text-right tw-font-semibold tw-pb-2">Δ Выручка</th>
              <th className="tw-text-right tw-font-semibold tw-pb-2">Δ EBITDA</th>
              <th className="tw-text-right tw-font-semibold tw-pb-2">Δ Чистая прибыль</th>
            </tr>
          </thead>
          <tbody>
            {list.map((c) => (
              <tr key={c.ticker} className="tw-border-t tw-border-border-subtle">
                <td className="tw-py-2">
                  {c.is_blue_chip && <Badge tone="neutral" className="tw-mr-1.5 tw-text-[10px]">ГФ</Badge>}
                  <span className="tw-font-mono tw-text-[12px] tw-text-text-tertiary tw-mr-2">
                    {c.ticker}{c._also?.length > 0 && <span className="tw-text-[10px] tw-ml-1">= {c._also.join(", ")}</span>}
                  </span>
                  <span className="tw-text-text-primary">{c.name}</span>
                  <span className="tw-text-[11px] tw-text-text-tertiary tw-ml-2">{c.sector}</span>
                </td>
                <td className="tw-py-2 tw-text-right"><DeltaCell m={c.metrics.revenue} /></td>
                <td className="tw-py-2 tw-text-right"><DeltaCell m={c.metrics.ebitda} /></td>
                <td className="tw-py-2 tw-text-right"><DeltaCell m={c.metrics.net_profit} /></td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      {deduped.length > 20 && (
        <button type="button" onClick={() => setShowAll(!showAll)}
          className="tw-mt-3 tw-text-[13px] tw-font-semibold tw-text-accent tw-bg-transparent tw-border-0 tw-cursor-pointer">
          {showAll ? "Свернуть ▴" : `Показать все ${deduped.length} компаний ▾`}
        </button>
      )}
      <div className="tw-mt-3 tw-text-[11.5px] tw-text-text-tertiary tw-leading-relaxed">{numeric.semantics}</div>
    </Card>
  );
}

const STRENGTH = { 1: "слабо", 2: "заметно", 3: "сильно" };

const Side = ({ title, sectors, companies, positive }) => {
  const [showAll, setShowAll] = useState(false);
  const total = sectors.length + companies.length;
  const capped = !showAll && total > 6;
  const sList = capped ? sectors.slice(0, Math.max(0, 6 - companies.length)) : sectors;
  const cList = capped ? companies.slice(0, Math.max(0, 6 - sList.length)) : companies;
  return (
    <div>
      <div className={`tw-text-[12px] tw-font-bold tw-uppercase tw-tracking-wide tw-mb-2 ${positive ? "tw-text-success" : "tw-text-danger"}`}>{title}</div>
      {sList.map((s, i) => (
        <div key={`s${i}`}
          className="tw-mb-2 tw-pl-3 tw-border-l-2"
          style={{ borderColor: positive ? "var(--bs-up)" : "var(--bs-down)", opacity: s.strength === 1 ? 0.75 : 1 }}>
          <div className="tw-text-[13.5px] tw-font-semibold tw-text-text-primary">
            {s.sector}
            <span className={`bs-wind-tag ${positive ? "bs-wind-up" : "bs-wind-down"} tw-ml-2`}>{STRENGTH[s.strength] || ""}</span>
          </div>
          <div className="tw-text-[12.5px] tw-text-text-secondary tw-leading-snug">{s.why}</div>
        </div>
      ))}
      {cList.length > 0 && (
        <div className="tw-mt-3 tw-flex tw-flex-col tw-gap-1.5">
          {cList.map((c, i) => (
            <div key={`c${i}`}
              className="tw-text-[12.5px] tw-text-text-secondary tw-leading-snug tw-pl-3 tw-border-l-2"
              style={{ borderColor: positive ? "var(--bs-up)" : "var(--bs-down)" }}>
              <span className="tw-font-mono tw-font-semibold tw-text-text-primary">{c.ticker}</span> — {c.why}
            </div>
          ))}
        </div>
      )}
      {!sectors.length && !companies.length && <div className="tw-text-[12.5px] tw-text-text-tertiary">—</div>}
      {total > 6 && (
        <button type="button" onClick={() => setShowAll(!showAll)}
          className="tw-mt-2 tw-text-[12px] tw-font-semibold tw-text-accent tw-bg-transparent tw-border-0 tw-cursor-pointer">
          {showAll ? "Свернуть ▴" : `Показать все ${total} ▾`}
        </button>
      )}
    </div>
  );
};

function ExpertBlock({ e }) {
  return (
    <Card header={<span className="tw-flex tw-items-center tw-gap-2">
      Разбор эксперта (ИИ на базе знаний платформы)
      <span className="bs-tag-judgment">суждение</span>
    </span>}>
      <div className="tw-text-[14px] tw-text-text-primary tw-leading-relaxed tw-mb-4">{e.summary}</div>
      {e.channels?.length > 0 && (
        <div className="tw-mb-4">
          <div className="tw-text-[11px] tw-font-bold tw-uppercase tw-tracking-wide tw-text-text-tertiary tw-mb-1.5">Каналы влияния</div>
          <ul className="tw-m-0 tw-pl-5 tw-text-[13px] tw-text-text-secondary tw-leading-relaxed">
            {e.channels.map((ch, i) => <li key={i}>{ch}</li>)}
          </ul>
        </div>
      )}
      <div className="tw-grid tw-grid-cols-1 sm:tw-grid-cols-2 tw-gap-6 tw-mb-4">
        <Side title="Потенциальные бенефициары" sectors={e.sector_winners || []} companies={e.company_winners || []} positive />
        <Side title="Потенциально под давлением" sectors={e.sector_losers || []} companies={e.company_losers || []} positive={false} />
      </div>
      {e.caveats?.length > 0 && (
        <div className="tw-p-3 tw-rounded-md tw-bg-bg-surface tw-text-[12.5px] tw-text-text-secondary tw-leading-relaxed">
          <b className="tw-text-text-primary">Оговорки:</b> {e.caveats.join(" · ")}
        </div>
      )}
      <div className="tw-mt-3 tw-text-[11.5px] tw-text-text-tertiary">{e.kb_note}</div>
    </Card>
  );
}

function QualTable({ qual }) {
  const [showAll, setShowAll] = useState(false);
  const rows = [...(qual.winners || []), ...(qual.losers || [])]
    .sort((a, b) => b.reaction_pct - a.reaction_pct);
  const list = showAll ? rows : rows.slice(0, 16);
  return (
    <Card header="Направление эффекта (качественные факторы: санкции / конфликт / налоги / спрос / ставка)">
      <div className="tw-grid tw-grid-cols-1 sm:tw-grid-cols-2 tw-gap-x-8">
        {list.map((r) => {
          const b = bucketOf(r.reaction_pct);
          return (
            <div key={r.ticker} className="tw-flex tw-items-center tw-justify-between tw-gap-3 tw-py-1.5 tw-border-b tw-border-border-subtle">
              <div className="tw-min-w-0 tw-truncate">
                <span className="tw-font-mono tw-text-[12px] tw-text-text-tertiary tw-mr-2">{r.ticker}</span>
                <span className="tw-text-[13px] tw-text-text-primary">{r.name}</span>
              </div>
              <span className={`bs-wind-tag tw-flex-shrink-0 ${b.cls}`} title={b.title}>{b.label}</span>
            </div>
          );
        })}
      </div>
      {rows.length > 16 && (
        <button type="button" onClick={() => setShowAll(!showAll)}
          className="tw-mt-3 tw-text-[13px] tw-font-semibold tw-text-accent tw-bg-transparent tw-border-0 tw-cursor-pointer">
          {showAll ? "Свернуть ▴" : "Показать больше ▾"}
        </button>
      )}
      <div className="tw-mt-3 tw-text-[11.5px] tw-text-text-tertiary tw-leading-relaxed">
        ▲▲ сильно позитивно · ▲ позитивно · ─ нейтрально · ▼ негативно · ▼▼ сильно негативно.
        Только направление по факторной разметке карточек — величину этих эффектов мы числом не оцениваем
        (в отличие от таблицы финансовых показателей выше). Сигнал: {qual.companies_with_signal} из {qual.total_companies} компаний.
      </div>
    </Card>
  );
}

// Дефолты на случай, если /current-levels временно недоступен (честная
// деградация — приблизительные ориентиры, не боевые данные, помечено ниже).
const FALLBACK_LEVELS = { key_rate_pct: 20, fx_usdrub: 80, oil_brent_usd: 70 };
const SLIDER_RANGE = {
  key_rate_pct: { min: 5, max: 30, step: 0.5, label: "Ключевая ставка", unit: "%" },
  fx_usdrub: { min: 50, max: 150, step: 1, label: "Курс ₽/$", unit: "₽" },
  oil_brent_usd: { min: 20, max: 120, step: 1, label: "Нефть Brent", unit: "$" },
};

function Slider({ field, value, onChange, pulsing }) {
  const cfg = SLIDER_RANGE[field];
  return (
    <div className={`st-sl${pulsing ? " st-sl-pulse" : ""}`}>
      <div className="st-sl-label">
        <span className="st-sl-name">{cfg.label}</span>
        <span className="st-sl-val">
          {cfg.unit === "%" ? value.toFixed(1).replace(/\.0$/, "") : Math.round(value)}
          <span className="st-sl-unit">{cfg.unit}</span>
        </span>
      </div>
      <input type="range" min={cfg.min} max={cfg.max} step={cfg.step} value={value}
        onChange={(e) => onChange(field, parseFloat(e.target.value))} />
    </div>
  );
}

export default function StressTestView() {
  const apiUrl = process.env.REACT_APP_API_URL || "http://localhost:8000";

  // Слайдеры — null, пока не подтянули реальные текущие уровни (не рисуем
  // произвольные числа как «сейчас», пока не знаем, что это правда).
  const [levels, setLevels] = useState(null);
  const [levelsIsFallback, setLevelsIsFallback] = useState(false);
  const [pulsingFields, setPulsingFields] = useState(new Set());
  const skipRecomputeRef = useRef(false);

  const [numResult, setNumResult] = useState(null);
  const [numRecomputing, setNumRecomputing] = useState(false);

  const [question, setQuestion] = useState("");
  const [askResult, setAskResult] = useState(null);
  const [askLoading, setAskLoading] = useState(false);

  const [presets, setPresets] = useState([]);
  const [presetResult, setPresetResult] = useState(null);
  const [presetKey, setPresetKey] = useState(null);

  // Реальные текущие ориентиры — стартовая позиция слайдеров.
  useEffect(() => {
    fetch(`${apiUrl}/api/stress-test/current-levels`)
      .then((r) => (r.ok ? r.json() : {}))
      .then((d) => {
        const merged = {
          key_rate_pct: d.key_rate_pct ?? FALLBACK_LEVELS.key_rate_pct,
          fx_usdrub: d.fx_usdrub ?? FALLBACK_LEVELS.fx_usdrub,
          oil_brent_usd: d.oil_brent_usd ?? FALLBACK_LEVELS.oil_brent_usd,
        };
        setLevelsIsFallback(d.key_rate_pct == null || d.fx_usdrub == null || d.oil_brent_usd == null);
        skipRecomputeRef.current = true; // начальная позиция — не пересчитывать лишний раз
        setLevels(merged);
      })
      .catch(() => { setLevels(FALLBACK_LEVELS); setLevelsIsFallback(true); });

    fetch(`${apiUrl}/api/stress-test/scenarios`)
      .then((r) => (r.ok ? r.json() : { scenarios: [] }))
      .then((d) => setPresets(d.scenarios || []))
      .catch(() => {});
  }, [apiUrl]);

  // Живой пересчёт на слайдерах — debounce, БЕЗ полноэкранного лоадера (карта
  // и таблица остаются на месте, пока новые данные не придут — не мигаем пустотой).
  useEffect(() => {
    if (!levels) return;
    if (skipRecomputeRef.current) { skipRecomputeRef.current = false; return; }
    setAskResult(null); setPresetResult(null);
    const t = setTimeout(() => {
      setNumRecomputing(true);
      const params = new URLSearchParams({
        key_rate_pct: levels.key_rate_pct, fx_usdrub: levels.fx_usdrub, oil_brent_usd: levels.oil_brent_usd,
      });
      fetch(`${apiUrl}/api/stress-test/numeric?${params}`)
        .then((r) => (r.ok ? r.json() : Promise.reject()))
        .then((d) => { setNumResult(d); setNumRecomputing(false); })
        .catch(() => setNumRecomputing(false));
    }, 350);
    return () => clearTimeout(t);
  }, [apiUrl, levels?.key_rate_pct, levels?.fx_usdrub, levels?.oil_brent_usd]);

  const setField = (field, value) => setLevels((prev) => ({ ...prev, [field]: value }));

  const resetLevels = () => {
    if (!levels) return;
    setLevels({ ...FALLBACK_LEVELS });
  };

  const ask = () => {
    if (!question.trim() || askLoading || !levels) return;
    setAskLoading(true); setAskResult(null); setPresetResult(null);
    fetch(`${apiUrl}/api/stress-test/ask`, {
      method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ question }),
    })
      .then((r) => (r.ok ? r.json() : Promise.reject()))
      .then((d) => {
        setAskResult(d); setAskLoading(false);
        if (d.numeric) setNumResult(d.numeric);
        const t = d.numeric_targets;
        if (t && (t.key_rate_pct != null || t.fx_usdrub != null || t.oil_brent_usd != null)) {
          skipRecomputeRef.current = true; // уже посчитано в этом же ответе — не дублируем запрос
          setLevels((prev) => ({
            key_rate_pct: t.key_rate_pct ?? prev.key_rate_pct,
            fx_usdrub: t.fx_usdrub ?? prev.fx_usdrub,
            oil_brent_usd: t.oil_brent_usd ?? prev.oil_brent_usd,
          }));
          const pulsed = new Set(Object.entries(t).filter(([, v]) => v != null).map(([k]) => k));
          setPulsingFields(pulsed);
          setTimeout(() => setPulsingFields(new Set()), 900);
        }
      })
      .catch(() => { setAskResult({ error: "network" }); setAskLoading(false); });
  };

  const runPreset = (key) => {
    setPresetKey(key); setPresetResult(null); setAskResult(null);
    fetch(`${apiUrl}/api/stress-test/impact?scenario=${key}`)
      .then((r) => (r.ok ? r.json() : Promise.reject()))
      .then((d) => { setPresetResult(d); setPresetKey(null); })
      .catch(() => setPresetKey(null));
  };

  const EXAMPLES = [
    "Что если война закончится в этом году?",
    "Ставка 20% на весь следующий год",
    "Нефть падает до $45 и держится там",
    "Государство поднимает налоги на бизнес",
  ];

  return (
    <div className="stress-test-view tw-flex tw-flex-col tw-gap-5">
      <div className="tw-flex tw-items-start tw-gap-3 tw-p-4 tw-rounded-md tw-bg-warning-soft">
        <FlaskConical size={18} className="tw-text-warning tw-flex-shrink-0 tw-mt-0.5" />
        <div className="tw-text-[13px] tw-text-text-primary tw-leading-relaxed">
          <b>Демо-версия, супер-тестовая — не воспринимайте её всерьёз как прогноз.</b> Числа считаются по
          линейным коэффициентам чувствительности из макро-разборов карточек (реальность нелинейна: демпферы,
          прогрессивные налоги, хеджи). Интерпретация свободного сценария — ИИ, может понять вас неточно
          (мы показываем «как мы поняли» — проверяйте). Точечные события одной компании (адресный налог,
          смена собственника) модель не считает. Не инвестиционная рекомендация.
        </div>
      </div>

      <div>
        <h2 className="tw-font-display tw-text-[22px] tw-font-semibold tw-text-text-primary tw-m-0">Стресс-тестирование</h2>
        <p className="tw-text-[13px] tw-text-text-secondary tw-mt-1 tw-max-w-[68ch]">
          Подвигайте ползунки — карта рынка и таблица пересчитываются на лету, без ожидания. Или опишите
          сценарий своими словами: если он называет конкретные уровни, ползунки встанут в них сами.
        </p>
      </div>

      <div className="st-console">
        <div className="st-ask">
          <div className="st-ask-row">
            <input
              type="text" value={question}
              onChange={(e) => setQuestion(e.target.value)}
              onKeyDown={(e) => { if (e.key === "Enter") ask(); }}
              placeholder="Опишите сценарий своими словами — «нефть падает до $45 и держится там»"
            />
            <button type="button" onClick={ask} disabled={askLoading}>
              <Send size={14} /> Спросить
            </button>
          </div>
          <div className="st-ask-chips">
            {EXAMPLES.map((ex) => (
              <button key={ex} type="button" onClick={() => setQuestion(ex)} className="st-chip">{ex}</button>
            ))}
          </div>
        </div>

        {askResult?.understood && (
          <div className="st-interp">
            <span className="st-interp-tag">интерпретация ИИ</span>
            <p>{askResult.understood}</p>
            {askResult.horizon && <div className="st-interp-horizon">Горизонт: {askResult.horizon}</div>}
          </div>
        )}
        {askResult?.error === "llm_unavailable" && (
          <div className="st-interp"><p>{askResult.note}</p></div>
        )}
        {askResult?.out_of_scope && (
          <div className="st-interp"><p>{askResult.out_of_scope_note}</p></div>
        )}

        {!levels ? (
          <div className="st-sliders-loading">Загружаем текущие уровни ставки/курса/нефти…</div>
        ) : (
          <>
            <div className="st-sliders-head">
              <span>Или задайте уровни точно {numRecomputing && <span className="st-recompute-dot" aria-label="пересчитываем" />}</span>
              <button type="button" className="st-reset" onClick={resetLevels}>
                <RotateCcw size={12} /> К текущим уровням
              </button>
            </div>
            <div className="st-sliders">
              <Slider field="key_rate_pct" value={levels.key_rate_pct} onChange={setField} pulsing={pulsingFields.has("key_rate_pct")} />
              <Slider field="fx_usdrub" value={levels.fx_usdrub} onChange={setField} pulsing={pulsingFields.has("fx_usdrub")} />
              <Slider field="oil_brent_usd" value={levels.oil_brent_usd} onChange={setField} pulsing={pulsingFields.has("oil_brent_usd")} />
            </div>
            {levelsIsFallback && (
              <div className="st-levels-note">Текущие уровни временно недоступны — старт от приблизительных ориентиров (ставка ~20%, курс ~80 ₽/$, Brent ~$70), не боевые данные.</div>
            )}
          </>
        )}

        {presets.length > 0 && (
          <div className="st-presets">
            <div className="st-presets-head">Готовые сценарии (детерминированный расчёт качественных факторов — санкции/конфликт/спрос, без ИИ-интерпретации)</div>
            <div className="st-presets-grid">
              {presets.map((p) => (
                <button key={p.key} type="button" onClick={() => runPreset(p.key)}
                  disabled={presetKey === p.key} className="bs-ai-plan st-preset">
                  <div className="st-preset-label">{p.label}</div>
                  <div className="st-preset-desc">{p.description}</div>
                </button>
              ))}
            </div>
          </div>
        )}
      </div>

      {askLoading && (
        <div className="tw-py-6 tw-text-text-tertiary tw-text-center tw-animate-pulse">Интерпретируем сценарий…</div>
      )}
      {presetKey && (
        <div className="tw-py-6 tw-text-text-tertiary tw-text-center tw-animate-pulse">Считаем сценарий...</div>
      )}

      {numResult && !numResult.error && <StressMap numeric={numResult} />}
      {numResult && !numResult.error && <ImpactSignal numeric={numResult} />}
      {numResult && !numResult.error && <NumericTable numeric={numResult} />}

      {askResult?.expert && <ExpertBlock e={askResult.expert} />}
      {askResult?.qualitative && <QualTable qual={askResult.qualitative} />}
      {askResult?.no_signal && (
        <Card><div className="tw-text-[13.5px] tw-text-text-secondary">{askResult.note}</div></Card>
      )}
      {askResult?.error === "network" && (
        <Card><div className="tw-text-[13.5px] tw-text-danger">Не удалось получить ответ — попробуйте ещё раз.</div></Card>
      )}

      {presetResult && !presetResult.error && (
        <>
          <Card header={<span className="tw-flex tw-items-center tw-gap-2">
            Как мы поняли сценарий
            <span className="bs-tag-fact">пресет</span>
          </span>}>
            <div className="tw-text-[14px] tw-text-text-primary tw-leading-relaxed">{presetResult.scenario?.description}</div>
          </Card>
          <QualTable qual={presetResult} />
        </>
      )}
      {presetResult?.error && (
        <Card><div className="tw-text-[13.5px] tw-text-danger">Не удалось посчитать сценарий — попробуйте ещё раз.</div></Card>
      )}
    </div>
  );
}

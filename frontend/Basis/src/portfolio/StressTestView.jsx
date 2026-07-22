import React, { useEffect, useState } from "react";
import { FlaskConical, Send } from "lucide-react";
import { Card, Badge, Delta } from "../design/primitives";
import { ImpactBar } from "../design/PortfolioViz";
import "../styles/stress-test.css";

// StressTestView v2 — «Стресс-тестирование» (владелец, 2026-07-17, вторая
// итерация): (1) формат «я спрашиваю ЛЮБОЙ сценарий — получаю ответ» (LLM-парсер
// DeepSeek → детерминированный расчёт); (2) числовые поля (ставка/курс/нефть) →
// Δ выручки/EBITDA/чистой прибыли в млрд ₽ и % от базы года (не «+2% у акции
// непонятно чего»); (3) голубые фишки первыми; (4) качественные факторы — только
// НАПРАВЛЕНИЕ (бакеты ▲▲/▲/▼/▼▼), без псевдоточных процентов. ДЕМО — дисклеймер.

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

export default function StressTestView() {
  const [question, setQuestion] = useState("");
  const [askResult, setAskResult] = useState(null);
  const [askLoading, setAskLoading] = useState(false);
  const [rate, setRate] = useState("");
  const [rub, setRub] = useState("");
  const [oil, setOil] = useState("");
  const [numResult, setNumResult] = useState(null);
  const [numLoading, setNumLoading] = useState(false);
  const apiUrl = process.env.REACT_APP_API_URL || "http://localhost:8000";

  // Готовые сценарии (детерминированный расчёт, без LLM-интерпретации) —
  // заполняют пустое состояние реальной функциональностью вместо декора.
  const [presets, setPresets] = useState([]);
  const [presetResult, setPresetResult] = useState(null);
  const [presetKey, setPresetKey] = useState(null); // какой пресет сейчас грузится

  useEffect(() => {
    fetch(`${apiUrl}/api/stress-test/scenarios`)
      .then((r) => (r.ok ? r.json() : { scenarios: [] }))
      .then((d) => setPresets(d.scenarios || []))
      .catch(() => {});
  }, [apiUrl]);

  const runPreset = (key) => {
    setPresetKey(key); setPresetResult(null); setAskResult(null); setNumResult(null);
    fetch(`${apiUrl}/api/stress-test/impact?scenario=${key}`)
      .then((r) => (r.ok ? r.json() : Promise.reject()))
      .then((d) => { setPresetResult(d); setPresetKey(null); })
      .catch(() => setPresetKey(null));
  };

  const ask = () => {
    if (!question.trim() || askLoading) return;
    setAskLoading(true); setAskResult(null); setNumResult(null); setPresetResult(null);
    fetch(`${apiUrl}/api/stress-test/ask`, {
      method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ question }),
    })
      .then((r) => (r.ok ? r.json() : Promise.reject()))
      .then((d) => { setAskResult(d); setAskLoading(false); })
      .catch(() => { setAskResult({ error: "network" }); setAskLoading(false); });
  };

  const runNumeric = () => {
    const params = new URLSearchParams();
    if (rate !== "") params.set("key_rate_pct", rate);
    if (rub !== "") params.set("fx_usdrub", rub);
    if (oil !== "") params.set("oil_brent_usd", oil);
    if (![...params].length || numLoading) return;
    setNumLoading(true); setNumResult(null); setAskResult(null); setPresetResult(null);
    fetch(`${apiUrl}/api/stress-test/numeric?${params}`)
      .then((r) => (r.ok ? r.json() : Promise.reject()))
      .then((d) => { setNumResult(d); setNumLoading(false); })
      .catch(() => { setNumResult({ error: "network" }); setNumLoading(false); });
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
          Опишите любой сценарий своими словами — или задайте точные уровни ставки/курса/нефти. Покажем,
          как это ориентировочно транслируется в выручку и прибыль компаний (голубые фишки первыми).
        </p>
      </div>

      <Card header="Спросите сценарий">
        <div className="tw-flex tw-gap-2">
          <input
            type="text" value={question}
            onChange={(e) => setQuestion(e.target.value)}
            onKeyDown={(e) => { if (e.key === "Enter") ask(); }}
            placeholder="Что будет, если ...?"
            className="tw-flex-1 tw-px-3 tw-py-2.5 tw-rounded-md tw-border tw-border-border-strong tw-bg-bg-base tw-text-text-primary tw-text-[14px]"
          />
          <button type="button" onClick={ask} disabled={askLoading}
            className="tw-px-4 tw-py-2 tw-rounded-md tw-bg-accent tw-text-white tw-text-[13.5px] tw-font-semibold tw-cursor-pointer tw-border-0 tw-inline-flex tw-items-center tw-gap-1.5 disabled:tw-opacity-60">
            <Send size={14} /> Спросить
          </button>
        </div>
        <div className="tw-flex tw-flex-wrap tw-gap-2 tw-mt-3">
          {EXAMPLES.map((ex) => (
            <button key={ex} type="button" onClick={() => setQuestion(ex)}
              className="tw-px-3 tw-py-1.5 tw-rounded-full tw-border tw-border-border-subtle tw-bg-bg-base tw-text-[12px] tw-text-text-secondary tw-cursor-pointer hover:tw-border-border-hover">
              {ex}
            </button>
          ))}
        </div>
      </Card>

      <Card header="Или задайте уровни точно">
        <div className="tw-flex tw-flex-wrap tw-items-end tw-gap-5">
          <label className="tw-flex tw-flex-col tw-gap-1.5">
            <span className="tw-text-[12px] tw-text-text-tertiary">Ключевая ставка, %</span>
            <input type="number" value={rate} onChange={(e) => setRate(e.target.value)}
              onKeyDown={(e) => { if (e.key === "Enter") runNumeric(); }} placeholder="напр. 20"
              className="tw-w-28 tw-px-2.5 tw-py-1.5 tw-rounded-md tw-border tw-border-border-strong tw-bg-bg-base tw-text-text-primary tw-font-mono" />
          </label>
          <label className="tw-flex tw-flex-col tw-gap-1.5">
            <span className="tw-text-[12px] tw-text-text-tertiary">Курс, ₽/$</span>
            <input type="number" value={rub} onChange={(e) => setRub(e.target.value)}
              onKeyDown={(e) => { if (e.key === "Enter") runNumeric(); }} placeholder="напр. 100"
              className="tw-w-28 tw-px-2.5 tw-py-1.5 tw-rounded-md tw-border tw-border-border-strong tw-bg-bg-base tw-text-text-primary tw-font-mono" />
          </label>
          <label className="tw-flex tw-flex-col tw-gap-1.5">
            <span className="tw-text-[12px] tw-text-text-tertiary">Нефть Brent, $/барр.</span>
            <input type="number" value={oil} onChange={(e) => setOil(e.target.value)}
              onKeyDown={(e) => { if (e.key === "Enter") runNumeric(); }} placeholder="напр. 50"
              className="tw-w-28 tw-px-2.5 tw-py-1.5 tw-rounded-md tw-border tw-border-border-strong tw-bg-bg-base tw-text-text-primary tw-font-mono" />
          </label>
          <button type="button" onClick={runNumeric} disabled={numLoading}
            className="tw-px-4 tw-py-2 tw-rounded-md tw-bg-accent tw-text-white tw-text-[13.5px] tw-font-semibold tw-cursor-pointer tw-border-0 disabled:tw-opacity-60">
            Посчитать
          </button>
          <span className="tw-text-[11.5px] tw-text-text-tertiary tw-max-w-[38ch]">
            Заполните любые из трёх — Δ считается от текущих уровней (у каждой компании свой спот-ориентир из её карточки).
          </span>
        </div>
      </Card>

      {presets.length > 0 && (
        <Card header="Готовые сценарии (детерминированный расчёт, без ИИ-интерпретации — быстрее и без риска неверно понять вопрос)">
          <div className="tw-grid tw-grid-cols-1 sm:tw-grid-cols-2 lg:tw-grid-cols-3 tw-gap-3">
            {presets.map((p) => (
              <button key={p.key} type="button" onClick={() => runPreset(p.key)}
                disabled={presetKey === p.key}
                className="bs-ai-plan tw-text-left tw-bg-transparent tw-w-full tw-cursor-pointer disabled:tw-opacity-60">
                <div className="tw-text-[13.5px] tw-font-semibold tw-text-text-primary tw-mb-1">{p.label}</div>
                <div className="tw-text-[12px] tw-text-text-secondary tw-leading-snug">{p.description}</div>
              </button>
            ))}
          </div>
        </Card>
      )}

      {(askLoading || numLoading || presetKey) && (
        <div className="tw-py-8 tw-text-text-tertiary tw-text-center tw-animate-pulse">
          {askLoading ? "Интерпретируем сценарий и считаем..." : presetKey ? "Считаем сценарий..." : "Считаем по вселенной..."}
        </div>
      )}

      {askResult && !askLoading && (
        <>
          {askResult.error === "llm_unavailable" && (
            <Card><div className="tw-text-[13.5px] tw-text-text-secondary">{askResult.note}</div></Card>
          )}
          {askResult.error === "network" && (
            <Card><div className="tw-text-[13.5px] tw-text-danger">Не удалось получить ответ — попробуйте ещё раз.</div></Card>
          )}
          {askResult.understood && (
            <Card header={<span className="tw-flex tw-items-center tw-gap-2">
              Как мы поняли ваш сценарий
              <span className="bs-tag-judgment">интерпретация ИИ</span>
            </span>}>
              <div className="tw-text-[14px] tw-text-text-primary tw-leading-relaxed">{askResult.understood}</div>
              {askResult.horizon && <div className="tw-text-[12px] tw-text-text-tertiary tw-mt-1.5">Горизонт: {askResult.horizon}</div>}
              {askResult.out_of_scope && (
                <div className="tw-mt-3 tw-p-3 tw-rounded-md tw-bg-warning-soft tw-text-[13px] tw-text-text-primary">{askResult.out_of_scope_note}</div>
              )}
              {askResult.no_signal && (
                <div className="tw-mt-3 tw-p-3 tw-rounded-md tw-bg-warning-soft tw-text-[13px] tw-text-text-primary">{askResult.note}</div>
              )}
            </Card>
          )}
          {askResult.expert && <ExpertBlock e={askResult.expert} />}
          {askResult.numeric && <ImpactSignal numeric={askResult.numeric} />}
          {askResult.numeric && <NumericTable numeric={askResult.numeric} />}
          {askResult.qualitative && <QualTable qual={askResult.qualitative} />}
        </>
      )}

      {numResult && !numLoading && !numResult.error && <ImpactSignal numeric={numResult} />}
      {numResult && !numLoading && !numResult.error && <NumericTable numeric={numResult} />}
      {numResult && numResult.error === "no_inputs" && (
        <Card><div className="tw-text-[13.5px] tw-text-text-secondary">{numResult.note}</div></Card>
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

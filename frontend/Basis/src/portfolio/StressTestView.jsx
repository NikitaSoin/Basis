import React, { useEffect, useState } from "react";
import { FlaskConical, Send } from "lucide-react";
import { Card, Badge } from "../design/primitives";

// StressTestView v2 — «Стресс-тестирование» (владелец, 2026-07-17, вторая
// итерация): (1) формат «я спрашиваю ЛЮБОЙ сценарий — получаю ответ» (LLM-парсер
// DeepSeek → детерминированный расчёт); (2) числовые поля (ставка/курс/нефть) →
// Δ выручки/EBITDA/чистой прибыли в млрд ₽ и % от базы года (не «+2% у акции
// непонятно чего»); (3) голубые фишки первыми; (4) качественные факторы — только
// НАПРАВЛЕНИЕ (бакеты ▲▲/▲/▼/▼▼), без псевдоточных процентов. ДЕМО — дисклеймер.

const BUCKETS = [
  { min: 8, label: "▲▲", cls: "tw-text-success", title: "сильно позитивно" },
  { min: 2, label: "▲", cls: "tw-text-success", title: "позитивно" },
  { min: -2, label: "─", cls: "tw-text-text-tertiary", title: "нейтрально / слабо" },
  { min: -8, label: "▼", cls: "tw-text-danger", title: "негативно" },
  { min: -Infinity, label: "▼▼", cls: "tw-text-danger", title: "сильно негативно" },
];
function bucketOf(pct) {
  for (const b of BUCKETS) if (pct >= b.min) return b;
  return BUCKETS[BUCKETS.length - 1];
}

function fmtBn(v) {
  if (v == null) return "—";
  const s = v > 0 ? "+" : "";
  return `${s}${v.toLocaleString("ru-RU", { maximumFractionDigits: 1 })}`;
}

function DeltaCell({ m }) {
  if (!m || m.delta_bn == null) return <span className="tw-text-text-tertiary">—</span>;
  const positive = m.delta_bn >= 0;
  return (
    <span className={`tw-font-mono tw-tabular-nums ${positive ? "tw-text-success" : "tw-text-danger"}`}>
      {fmtBn(m.delta_bn)} <span className="tw-text-[10.5px]">млрд</span>
      {m.pct_of_base != null && (
        <span className="tw-text-[11px] tw-text-text-tertiary tw-ml-1">({positive ? "+" : ""}{m.pct_of_base}%)</span>
      )}
    </span>
  );
}

function NumericTable({ numeric }) {
  const [showAll, setShowAll] = useState(false);
  const list = showAll ? numeric.companies : numeric.companies.slice(0, 20);
  return (
    <Card header="Эффект на финансовые показатели (за год, к базе последнего отчётного года)">
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
                  {c.is_blue_chip && <Badge tone="accent" className="tw-mr-1.5 tw-text-[10px]">ГФ</Badge>}
                  <span className="tw-font-mono tw-text-[12px] tw-text-text-tertiary tw-mr-2">{c.ticker}</span>
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
      {numeric.companies.length > 20 && (
        <button type="button" onClick={() => setShowAll(!showAll)}
          className="tw-mt-3 tw-text-[13px] tw-font-semibold tw-text-accent tw-bg-transparent tw-border-0 tw-cursor-pointer">
          {showAll ? "Свернуть ▴" : `Показать все ${numeric.companies.length} компаний ▾`}
        </button>
      )}
      <div className="tw-mt-3 tw-text-[11.5px] tw-text-text-tertiary tw-leading-relaxed">{numeric.semantics}</div>
    </Card>
  );
}

const STRENGTH = { 1: "слабо", 2: "заметно", 3: "сильно" };

function ExpertBlock({ e }) {
  const Side = ({ title, sectors, companies, positive }) => (
    <div>
      <div className={`tw-text-[12px] tw-font-bold tw-uppercase tw-tracking-wide tw-mb-2 ${positive ? "tw-text-success" : "tw-text-danger"}`}>{title}</div>
      {sectors.map((s, i) => (
        <div key={`s${i}`} className="tw-mb-2">
          <div className="tw-text-[13.5px] tw-font-semibold tw-text-text-primary">
            {s.sector} <span className="tw-text-[11px] tw-font-normal tw-text-text-tertiary">· {STRENGTH[s.strength] || ""}</span>
          </div>
          <div className="tw-text-[12.5px] tw-text-text-secondary tw-leading-snug">{s.why}</div>
        </div>
      ))}
      {companies.length > 0 && (
        <div className="tw-mt-3 tw-flex tw-flex-col tw-gap-1.5">
          {companies.map((c, i) => (
            <div key={`c${i}`} className="tw-text-[12.5px] tw-text-text-secondary tw-leading-snug">
              <span className="tw-font-mono tw-font-semibold tw-text-text-primary">{c.ticker}</span> — {c.why}
            </div>
          ))}
        </div>
      )}
      {!sectors.length && !companies.length && <div className="tw-text-[12.5px] tw-text-text-tertiary">—</div>}
    </div>
  );
  return (
    <Card header="Разбор эксперта (ИИ на базе знаний платформы)">
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
              <span className={`tw-font-semibold tw-flex-shrink-0 ${b.cls}`} title={b.title}>{b.label}</span>
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

  const ask = () => {
    if (!question.trim() || askLoading) return;
    setAskLoading(true); setAskResult(null); setNumResult(null);
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
    setNumLoading(true); setNumResult(null); setAskResult(null);
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
    <div className="tw-flex tw-flex-col tw-gap-5">
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
            <input type="number" value={rate} onChange={(e) => setRate(e.target.value)} placeholder="напр. 20"
              className="tw-w-28 tw-px-2.5 tw-py-1.5 tw-rounded-md tw-border tw-border-border-strong tw-bg-bg-base tw-text-text-primary tw-font-mono" />
          </label>
          <label className="tw-flex tw-flex-col tw-gap-1.5">
            <span className="tw-text-[12px] tw-text-text-tertiary">Курс, ₽/$</span>
            <input type="number" value={rub} onChange={(e) => setRub(e.target.value)} placeholder="напр. 100"
              className="tw-w-28 tw-px-2.5 tw-py-1.5 tw-rounded-md tw-border tw-border-border-strong tw-bg-bg-base tw-text-text-primary tw-font-mono" />
          </label>
          <label className="tw-flex tw-flex-col tw-gap-1.5">
            <span className="tw-text-[12px] tw-text-text-tertiary">Нефть Brent, $/барр.</span>
            <input type="number" value={oil} onChange={(e) => setOil(e.target.value)} placeholder="напр. 50"
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

      {(askLoading || numLoading) && (
        <div className="tw-py-8 tw-text-text-tertiary tw-text-center tw-animate-pulse">
          {askLoading ? "Интерпретируем сценарий и считаем..." : "Считаем по вселенной..."}
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
            <Card header="Как мы поняли ваш сценарий">
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
          {askResult.numeric && <NumericTable numeric={askResult.numeric} />}
          {askResult.qualitative && <QualTable qual={askResult.qualitative} />}
        </>
      )}

      {numResult && !numLoading && !numResult.error && <NumericTable numeric={numResult} />}
      {numResult && numResult.error === "no_inputs" && (
        <Card><div className="tw-text-[13.5px] tw-text-text-secondary">{numResult.note}</div></Card>
      )}
    </div>
  );
}

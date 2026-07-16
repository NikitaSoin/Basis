import React, { useEffect, useState } from "react";
import { TrendingUp, TrendingDown, FlaskConical } from "lucide-react";
import { Card, Badge } from "../design/primitives";

// StressTestView — «Стресс-тестирование» (широкий блок: сценарии → эффект на
// компании/акции/облигации), НЕ путать с узким портфельным расчётом внутри
// Портфеля (бета×шок индекса). Владелец, 2026-07-17: «возможность +- прикинуть,
// что произойдёт с компаниями/акциями при разных сценариях — качественных
// (война N лет, обвал/скачок нефти, налоговое давление...) и числовых (нефть
// $X, курс ₽Y)». ДЕМО-ВЕРСИЯ — переиспользует реальный факторный движок
// (backend/app/services/stress_scenarios.py), но интенсивности откалиброваны
// на глаз, не исторической регрессией — явный дисклеймер на экране.

function ReactionRow({ r }) {
  const positive = r.reaction_pct >= 0;
  return (
    <div className="tw-flex tw-items-center tw-justify-between tw-gap-3 tw-py-2 tw-border-b tw-border-border-subtle last:tw-border-0">
      <div className="tw-min-w-0">
        <span className="tw-font-mono tw-text-[12px] tw-text-text-tertiary tw-mr-2">{r.ticker}</span>
        <span className="tw-text-[13.5px] tw-text-text-primary">{r.name}</span>
        <span className="tw-text-[11.5px] tw-text-text-tertiary tw-ml-2">{r.sector}</span>
      </div>
      <span className={`tw-inline-flex tw-items-center tw-gap-1 tw-font-mono tw-tabular-nums tw-text-[14px] tw-font-semibold tw-flex-shrink-0 ${positive ? "tw-text-success" : "tw-text-danger"}`}>
        {positive ? <TrendingUp size={13} /> : <TrendingDown size={13} />}
        {positive ? "+" : ""}{r.reaction_pct}%
      </span>
    </div>
  );
}

function SectorBars({ sectors }) {
  if (!sectors.length) return <div className="tw-text-[13px] tw-text-text-tertiary">Недостаточно данных по секторам для этого сценария.</div>;
  const maxAbs = Math.max(...sectors.map((s) => Math.abs(s.avg_reaction_pct)), 1);
  return (
    <div className="tw-flex tw-flex-col tw-gap-2">
      {sectors.map((s) => {
        const positive = s.avg_reaction_pct >= 0;
        const width = Math.min(100, (Math.abs(s.avg_reaction_pct) / maxAbs) * 100);
        return (
          <div key={s.sector} className="tw-grid tw-items-center tw-gap-2.5 tw-text-[13px]" style={{ gridTemplateColumns: "170px 1fr 70px" }}>
            <span className="tw-text-text-secondary tw-truncate">{s.sector} <span className="tw-text-text-tertiary tw-text-[11px]">({s.n})</span></span>
            <span className="tw-h-2 tw-rounded-full tw-bg-bg-surface tw-overflow-hidden">
              <span className={`tw-block tw-h-full tw-rounded-full ${positive ? "tw-bg-success" : "tw-bg-danger"}`} style={{ width: `${width}%` }} />
            </span>
            <span className={`tw-font-mono tw-tabular-nums tw-text-[12px] tw-text-right ${positive ? "tw-text-success" : "tw-text-danger"}`}>
              {positive ? "+" : ""}{s.avg_reaction_pct}%
            </span>
          </div>
        );
      })}
    </div>
  );
}

export default function StressTestView() {
  const [presets, setPresets] = useState([]);
  const [mode, setMode] = useState("preset"); // "preset" | "custom"
  const [scenarioKey, setScenarioKey] = useState(null);
  const [oilUsd, setOilUsd] = useState(60);
  const [rubUsd, setRubUsd] = useState(90);
  const [result, setResult] = useState(null);
  const [loading, setLoading] = useState(false);
  const apiUrl = process.env.REACT_APP_API_URL || "http://localhost:8000";

  useEffect(() => {
    fetch(`${apiUrl}/api/stress-test/scenarios`)
      .then((r) => (r.ok ? r.json() : null))
      .then((d) => {
        if (d?.scenarios?.length) {
          setPresets(d.scenarios);
          setScenarioKey(d.scenarios[0].key);
        }
      })
      .catch(() => {});
  }, [apiUrl]);

  const runPreset = (key) => {
    setMode("preset"); setScenarioKey(key); setLoading(true);
    fetch(`${apiUrl}/api/stress-test/impact?scenario=${encodeURIComponent(key)}`)
      .then((r) => (r.ok ? r.json() : null))
      .then((d) => { setResult(d); setLoading(false); })
      .catch(() => setLoading(false));
  };

  const runCustom = () => {
    setMode("custom"); setLoading(true);
    fetch(`${apiUrl}/api/stress-test/impact?oil_usd=${oilUsd}&rub_usd=${rubUsd}`)
      .then((r) => (r.ok ? r.json() : null))
      .then((d) => { setResult(d); setLoading(false); })
      .catch(() => setLoading(false));
  };

  useEffect(() => {
    if (presets.length && !result) runPreset(presets[0].key);
  }, [presets]);

  return (
    <div className="tw-flex tw-flex-col tw-gap-5">
      <div className="tw-flex tw-items-start tw-gap-3 tw-p-4 tw-rounded-md tw-bg-warning-soft">
        <FlaskConical size={18} className="tw-text-warning tw-flex-shrink-0 tw-mt-0.5" />
        <div className="tw-text-[13px] tw-text-text-primary tw-leading-relaxed">
          <b>Демо-версия, супер-тестовая.</b> Интенсивности сценариев подобраны «на глаз», не откалиброваны
          исторической регрессией. Не все компании имеют разметку по всем факторам (см. охват под таблицей) —
          отсутствие сигнала не значит «влияния нет», значит «мы это не оценивали». Для облигаций показана
          реакция АКЦИИ эмитента как косвенный ориентир направления, не пересчёт спреда/цены бумаги. Точечные
          события одной компании (адресное повышение налога, смена собственника конкретного эмитента) эта
          модель не считает — только общерыночные/секторные сдвиги. Не является инвестиционной рекомендацией
          и не должна восприниматься как точный прогноз.
        </div>
      </div>

      <div>
        <h2 className="tw-font-display tw-text-[22px] tw-font-semibold tw-text-text-primary tw-m-0">Стресс-тестирование</h2>
        <p className="tw-text-[13px] tw-text-text-secondary tw-mt-1 tw-max-w-[68ch]">
          Выберите сценарий или задайте свой (нефть/курс) — увидите, какие компании и сектора выигрывают, какие проигрывают, и насколько.
        </p>
      </div>

      <div className="tw-grid tw-grid-cols-1 sm:tw-grid-cols-2 lg:tw-grid-cols-3 tw-gap-2.5">
        {presets.map((s) => (
          <button
            key={s.key}
            type="button"
            onClick={() => runPreset(s.key)}
            className={`tw-text-left tw-rounded-md tw-border tw-p-3.5 tw-cursor-pointer tw-bg-bg-elevated tw-shadow-sm ${
              mode === "preset" && scenarioKey === s.key ? "tw-border-accent tw-shadow-[0_0_0_1px_var(--accent)_inset]" : "tw-border-border-strong hover:tw-border-border-hover"
            }`}
          >
            <div className="tw-font-display tw-font-semibold tw-text-[14.5px] tw-text-text-primary tw-mb-1">{s.label}</div>
            <div className="tw-text-[12px] tw-text-text-secondary tw-leading-snug">{s.description}</div>
          </button>
        ))}
      </div>

      <Card header="Свой сценарий: нефть и курс рубля">
        <div className="tw-flex tw-flex-wrap tw-items-end tw-gap-5">
          <label className="tw-flex tw-flex-col tw-gap-1.5">
            <span className="tw-text-[12px] tw-text-text-tertiary">Нефть, $/барр.</span>
            <input type="number" value={oilUsd} onChange={(e) => setOilUsd(Number(e.target.value))}
              className="tw-w-28 tw-px-2.5 tw-py-1.5 tw-rounded-md tw-border tw-border-border-strong tw-bg-bg-base tw-text-text-primary tw-font-mono" />
          </label>
          <label className="tw-flex tw-flex-col tw-gap-1.5">
            <span className="tw-text-[12px] tw-text-text-tertiary">Курс, ₽/$</span>
            <input type="number" value={rubUsd} onChange={(e) => setRubUsd(Number(e.target.value))}
              className="tw-w-28 tw-px-2.5 tw-py-1.5 tw-rounded-md tw-border tw-border-border-strong tw-bg-bg-base tw-text-text-primary tw-font-mono" />
          </label>
          <button type="button" onClick={runCustom}
            className="tw-px-4 tw-py-2 tw-rounded-md tw-bg-accent tw-text-white tw-text-[13.5px] tw-font-semibold tw-cursor-pointer tw-border-0">
            Прогнать сценарий
          </button>
          <span className="tw-text-[11.5px] tw-text-text-tertiary">Курс — только валютный канал; нефтяной канал применяется к нефтегазовому сектору.</span>
        </div>
      </Card>

      {loading && <div className="tw-py-8 tw-text-text-tertiary tw-text-center">Считаем реакцию по вселенной...</div>}

      {!loading && result && !result.error && (
        <>
          <Card>
            <div className="tw-flex tw-items-center tw-justify-between tw-flex-wrap tw-gap-2">
              <div>
                <div className="tw-font-display tw-text-[16px] tw-font-semibold tw-text-text-primary">{result.scenario.label}</div>
                <div className="tw-text-[13px] tw-text-text-secondary tw-mt-1 tw-max-w-[60ch]">{result.scenario.description}</div>
              </div>
              <Badge tone="neutral">Сигнал: {result.companies_with_signal} / {result.total_companies} компаний</Badge>
            </div>
          </Card>

          <div className="tw-grid tw-grid-cols-1 lg:tw-grid-cols-2 tw-gap-4">
            <Card header="Потенциальные выигравшие">
              <div className="tw-flex tw-flex-col">
                {result.winners.length ? result.winners.map((r) => <ReactionRow key={r.ticker} r={r} />) : <div className="tw-text-[13px] tw-text-text-tertiary">Нет позиций с положительной реакцией по этому сценарию.</div>}
              </div>
            </Card>
            <Card header="Потенциальные проигравшие">
              <div className="tw-flex tw-flex-col">
                {result.losers.length ? result.losers.map((r) => <ReactionRow key={r.ticker} r={r} />) : <div className="tw-text-[13px] tw-text-text-tertiary">Нет позиций с отрицательной реакцией по этому сценарию.</div>}
              </div>
            </Card>
          </div>

          <Card header="По секторам (средняя реакция)">
            <SectorBars sectors={result.sectors} />
          </Card>

          <div className="tw-text-[11.5px] tw-text-text-tertiary tw-border-t tw-border-border-subtle tw-pt-3">
            {result.methodology}
          </div>
        </>
      )}
    </div>
  );
}

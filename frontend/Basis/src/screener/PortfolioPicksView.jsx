import React, { useEffect, useState } from "react";
import { TrendingUp, TrendingDown } from "lucide-react";
import { Card, Badge } from "../design/primitives";

// PortfolioPicksView — «Подборка портфелей» (владелец, 2026-07-17: не один
// канонический портфель на профиль риска, а несколько тезисных вариантов
// внутри каждого, у каждого явный расчёт + предположение о рынке). Данные —
// GET /api/screener/portfolio-picks, живой расчёт из того же скринер-движка,
// что и «Скринер акций» (backend/app/services/portfolio_picks.py) — не список
// тикеров с потолка. Не индивидуальная инвестиционная рекомендация.

function SectorBars({ sectors }) {
  const palette = ["#0072B2", "#009E73", "#E69F00", "#D55E00", "#CC79A7", "#56B4E9", "#C9A800", "#999999"];
  return (
    <div className="tw-flex tw-flex-col tw-gap-2">
      {sectors.map((s, i) => (
        <div key={s.sector} className="tw-grid tw-items-center tw-gap-2.5 tw-text-[13px]" style={{ gridTemplateColumns: "128px 1fr 44px" }}>
          <span className="tw-text-text-secondary tw-truncate">{s.sector}</span>
          <span className="tw-h-2 tw-rounded-full tw-bg-bg-surface tw-overflow-hidden">
            <span className="tw-block tw-h-full tw-rounded-full" style={{ width: `${s.weight_pct}%`, background: palette[i % palette.length] }} />
          </span>
          <span className="tw-font-mono tw-tabular-nums tw-text-text-secondary tw-text-[12px] tw-text-right">{s.weight_pct}%</span>
        </div>
      ))}
    </div>
  );
}

function MetricTile({ caption, value, unit }) {
  return (
    <div className="tw-flex tw-flex-col tw-gap-1.5 tw-bg-bg-elevated tw-border tw-border-border-strong tw-rounded-md tw-shadow-sm tw-p-4">
      <div className="tw-text-[11.5px] tw-font-medium tw-uppercase tw-tracking-wide tw-text-text-tertiary">{caption}</div>
      <div className="tw-flex tw-items-baseline tw-gap-1">
        <span className="tw-font-display tw-font-light tw-text-[26px] tw-text-text-primary tw-tabular-nums">{value == null ? "—" : value}</span>
        {unit && value != null && <span className="tw-text-[13px] tw-text-text-tertiary">{unit}</span>}
      </div>
    </div>
  );
}

function PortfolioDetail({ p }) {
  const m = p.metrics;
  return (
    <div className="tw-flex tw-flex-col tw-gap-4">
      <div>
        <h3 className="tw-font-display tw-text-[19px] tw-font-semibold tw-text-text-primary tw-mb-1">{p.name}</h3>
        <div className="tw-text-[12px] tw-text-text-tertiary">{p.pool_size} бумаг прошли фильтр · выбрано {p.positions.length}</div>
      </div>

      <div className="tw-grid tw-grid-cols-2 sm:tw-grid-cols-4 tw-gap-3">
        <MetricTile caption="Средний BASIS-балл" value={m.avg_basis} unit="/ 100" />
        <MetricTile caption="Ср. волатильность позиций" value={m.avg_volatility_pct} unit="%" />
        <MetricTile caption="Дивдоходность портфеля" value={m.avg_div_yield_pct} unit="%" />
        <MetricTile caption="Апсайд к справедливой цене" value={m.avg_upside_pct} unit="%" />
      </div>

      <div className="tw-grid tw-grid-cols-1 lg:tw-grid-cols-[1.3fr_1fr] tw-gap-4 tw-items-start">
        <Card header={`Состав (${p.positions.length} позиций)`}>
          <div className="tw-overflow-x-auto">
            <table className="tw-w-full tw-text-[13px]">
              <thead>
                <tr className="tw-text-text-tertiary tw-text-[11px] tw-uppercase tw-tracking-wide">
                  <th className="tw-text-left tw-font-semibold tw-pb-2">Позиция</th>
                  <th className="tw-text-right tw-font-semibold tw-pb-2">Вес</th>
                  <th className="tw-text-right tw-font-semibold tw-pb-2">BASIS</th>
                  <th className="tw-text-right tw-font-semibold tw-pb-2">Апсайд</th>
                </tr>
              </thead>
              <tbody>
                {p.positions.map((r) => (
                  <tr key={r.ticker} className="tw-border-t tw-border-border-subtle">
                    <td className="tw-py-2">
                      {r.name} <span className="tw-font-mono tw-text-text-tertiary tw-text-[11.5px]">{r.ticker}</span>
                    </td>
                    <td className="tw-py-2 tw-text-right tw-font-mono tw-tabular-nums">{r.weight_pct}%</td>
                    <td className="tw-py-2 tw-text-right tw-font-mono tw-tabular-nums">{r.basis ?? "—"}</td>
                    <td className="tw-py-2 tw-text-right tw-font-mono tw-tabular-nums">
                      {r.upside_pct == null ? "—" : (
                        <span className={`tw-inline-flex tw-items-center tw-gap-0.5 ${r.upside_pct >= 0 ? "tw-text-success" : "tw-text-danger"}`}>
                          {r.upside_pct >= 0 ? <TrendingUp size={11} /> : <TrendingDown size={11} />}
                          {r.upside_pct >= 0 ? "+" : ""}{r.upside_pct.toFixed(1)}%
                        </span>
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </Card>
        <Card header="Секторальные веса">
          <SectorBars sectors={p.sectors} />
        </Card>
      </div>

      <Card header="Почему такой набор">
        <div className="tw-flex tw-flex-col tw-gap-3 tw-text-[13.5px] tw-leading-relaxed tw-text-text-secondary">
          <div className="tw-flex tw-gap-2">
            <Badge tone="accent">суждение</Badge>
          </div>
          <div><b className="tw-text-text-primary">Расчёт:</b> {p.thesis}</div>
          <div><b className="tw-text-text-primary">Предположение о рынке:</b> {p.assumption}</div>
        </div>
      </Card>

      <div className="tw-border-l-[3px] tw-border-accent tw-bg-bg-elevated tw-rounded-r-md tw-shadow-sm tw-p-4 tw-text-[14px] tw-leading-relaxed tw-text-text-primary">
        Это результат применения опубликованной методики Basis (тот же скринер-движок, что и «Скринер акций») к текущим данным рынка с явно названным предположением — не прогноз и не индивидуальная инвестиционная рекомендация. Если предположение не сработает, портфель поведёт себя иначе.
      </div>
    </div>
  );
}

export default function PortfolioPicksView() {
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(false);
  const [tierKey, setTierKey] = useState(null);
  const [pickKey, setPickKey] = useState(null);
  const apiUrl = process.env.REACT_APP_API_URL || "http://localhost:8000";

  useEffect(() => {
    setLoading(true); setError(false);
    fetch(`${apiUrl}/api/screener/portfolio-picks`)
      .then((r) => (r.ok ? r.json() : Promise.reject()))
      .then((d) => {
        setData(d);
        setLoading(false);
        const firstTier = d.tiers?.[0];
        const firstPick = firstTier?.portfolios?.[0];
        if (firstTier) setTierKey(firstTier.key);
        if (firstPick) setPickKey(firstPick.key);
      })
      .catch(() => { setError(true); setLoading(false); });
  }, [apiUrl]);

  if (loading) return <div className="tw-flex tw-items-center tw-justify-center tw-py-24 tw-text-text-tertiary tw-text-[16px] tw-animate-pulse">Считаем подборку...</div>;
  if (error || !data) return <div className="tw-py-12 tw-text-text-tertiary">Не удалось загрузить подборку портфелей.</div>;

  const tier = data.tiers.find((t) => t.key === tierKey) || data.tiers[0];
  const pick = tier?.portfolios.find((p) => p.key === pickKey) || tier?.portfolios[0];

  return (
    <div className="tw-flex tw-flex-col tw-gap-5">
      <div>
        <h2 className="tw-font-display tw-text-[22px] tw-font-semibold tw-text-text-primary tw-m-0">Подборка портфелей</h2>
        <p className="tw-text-[13px] tw-text-text-secondary tw-mt-1 tw-max-w-[68ch]">
          Несколько тезисных вариантов на каждый профиль риска — не одна «правильная» корзина, а разные ставки с явно названным расчётом и предположением. Для сравнения с тем, что у вас уже есть, не для копирования вслепую.
        </p>
      </div>

      <div className="tw-grid tw-grid-cols-1 sm:tw-grid-cols-3 tw-gap-2.5" role="tablist" aria-label="Профиль риска">
        {data.tiers.map((t) => (
          <button
            key={t.key}
            type="button"
            role="tab"
            aria-selected={t.key === tier.key}
            onClick={() => { setTierKey(t.key); setPickKey(t.portfolios[0]?.key); }}
            className={`tw-text-left tw-rounded-md tw-border tw-p-3.5 tw-cursor-pointer tw-transition-colors ${
              t.key === tier.key ? "tw-border-accent tw-bg-accent-soft" : "tw-border-border-strong tw-bg-bg-elevated hover:tw-border-border-hover"
            }`}
          >
            <div className="tw-font-display tw-font-semibold tw-text-[15px] tw-text-text-primary">{t.name}</div>
            <div className="tw-text-[12px] tw-text-text-tertiary tw-mt-0.5">{t.sub}</div>
          </button>
        ))}
      </div>

      {tier.portfolios.length === 0 ? (
        <div className="tw-py-8 tw-text-text-tertiary tw-text-[13px]">Для этого профиля пока не набралось достаточно бумаг по фильтру — честная деградация, не пустая заглушка.</div>
      ) : (
        <>
          <div className="tw-grid tw-grid-cols-1 sm:tw-grid-cols-2 tw-gap-2.5">
            {tier.portfolios.map((p) => (
              <button
                key={p.key}
                type="button"
                aria-pressed={p.key === pick?.key}
                onClick={() => setPickKey(p.key)}
                className={`tw-text-left tw-rounded-md tw-border tw-p-4 tw-cursor-pointer tw-bg-bg-elevated tw-shadow-sm ${
                  p.key === pick?.key ? "tw-border-accent tw-shadow-[0_0_0_1px_var(--accent)_inset]" : "tw-border-border-strong hover:tw-border-border-hover"
                }`}
              >
                <div className="tw-font-display tw-font-semibold tw-text-[15px] tw-text-text-primary tw-mb-1.5">{p.name}</div>
                <div className="tw-text-[12.5px] tw-text-text-secondary tw-leading-snug tw-mb-1.5"><b className="tw-text-text-primary">Расчёт:</b> {p.thesis}</div>
                <div className="tw-flex tw-gap-3 tw-text-[11.5px] tw-text-text-tertiary tw-mt-2">
                  <span>BASIS <b className="tw-font-mono tw-text-text-primary">{p.metrics.avg_basis ?? "—"}</b></span>
                  <span>Вол. <b className="tw-font-mono tw-text-text-primary">{p.metrics.avg_volatility_pct ?? "—"}%</b></span>
                  <span>Апсайд <b className="tw-font-mono tw-text-text-primary">{p.metrics.avg_upside_pct ?? "—"}%</b></span>
                </div>
              </button>
            ))}
          </div>

          {pick && <PortfolioDetail p={pick} />}
        </>
      )}

      <div className="tw-text-[11.5px] tw-text-text-tertiary tw-border-t tw-border-border-subtle tw-pt-3">
        Методика: {data.methodology}
      </div>
    </div>
  );
}

// Basis Neo-Institutional Research System — Company Card shell components.
// Presentational only: consume props from the existing CompanyCard data.
// Styling = cc tokens (var(--cc-*)) via .cc-root scope; serif headings, mono numbers.
// No new data fetching, no API. Reuses cc-serif / cc-num / cc-eyebrow CSS classes.
import React from "react";

const cx = (...p) => p.filter(Boolean).join(" ");
const ink = "tw-text-[var(--cc-ink)]";
const ink2 = "tw-text-[var(--cc-ink-2)]";
const ink3 = "tw-text-[var(--cc-ink-3)]";
const panel = "tw-bg-[var(--cc-panel)] tw-border tw-border-[var(--cc-line)] tw-rounded-[14px]";

// ── Fact / Estimate / Judgment / Scenario epistemic tag ──
const FEJ_MAP = {
  fact: { t: "факт", c: "var(--cc-ink-2)" },
  estimate: { t: "оценка", c: "var(--cc-info)" },
  judgment: { t: "суждение", c: "var(--cc-accent)" },
  scenario: { t: "сценарий", c: "var(--cc-violet)" },
};
export function FEJTag({ level = "fact" }) {
  const m = FEJ_MAP[level] || FEJ_MAP.fact;
  return (
    <span className="tw-inline-flex tw-items-center tw-rounded-[6px] tw-px-1.5 tw-py-0.5 tw-text-[10px] tw-font-semibold tw-uppercase tw-tracking-[0.08em]"
      style={{ color: m.c, background: "color-mix(in srgb, " + m.c + " 12%, transparent)" }}>{m.t}</span>
  );
}

// ── Delta (▲/▼ + value), semantic color always paired with a glyph ──
export function NeoDelta({ value, suffix = "%", decimals = 2 }) {
  if (value == null) return <span className={cx("cc-num", ink3)}>—</span>;
  const up = value > 0, flat = value === 0;
  const c = flat ? "var(--cc-ink-3)" : up ? "var(--cc-success)" : "var(--cc-danger)";
  const g = flat ? "▬" : up ? "▲" : "▼";
  const v = Math.abs(value).toLocaleString("ru-RU", { minimumFractionDigits: decimals, maximumFractionDigits: decimals });
  return <span className="cc-num tw-inline-flex tw-items-baseline tw-gap-1 tw-text-[13px] tw-font-medium" style={{ color: c }}><span aria-hidden>{g}</span>{v}{suffix}</span>;
}

// ── Company identity (logo + serif name + mono meta row) ──
export function CompanyIdentityBlock({ logo, name, ticker, exchange = "MOEX", sector, marketOpen }) {
  return (
    <div className="tw-flex tw-items-center tw-gap-4 tw-min-w-0">
      <div className="tw-shrink-0">{logo}</div>
      <div className="tw-min-w-0">
        <h1 className="cc-serif tw-m-0 tw-text-[clamp(30px,4.4vw,50px)] tw-font-semibold tw-leading-[1.02]" style={{ color: "var(--cc-ink)" }}>{name}</h1>
        <div className="cc-num tw-mt-2 tw-flex tw-flex-wrap tw-items-center tw-gap-x-3 tw-gap-y-1 tw-text-[12px]" style={{ color: "var(--cc-ink-3)" }}>
          <span className="tw-inline-flex tw-items-center tw-rounded-[6px] tw-px-1.5 tw-py-0.5 tw-border" style={{ borderColor: "var(--cc-line-2)", color: "var(--cc-ink-2)" }}>{ticker}</span>
          <span>{exchange}</span>
          {sector && <><span aria-hidden>·</span><span style={{ fontFamily: "var(--cc-sans)" }}>{sector}</span></>}
          <span className="tw-inline-flex tw-items-center tw-gap-1.5">
            <span className="tw-w-1.5 tw-h-1.5 tw-rounded-full" style={{ background: marketOpen ? "var(--cc-success)" : "var(--cc-ink-3)" }} />
            <span style={{ fontFamily: "var(--cc-sans)" }}>{marketOpen ? "Торги открыты" : "Торги закрыты"}</span>
          </span>
        </div>
      </div>
    </div>
  );
}

// ── Price panel (mono 52px + delta + cap/updated/tone) ──
export function PricePanel({ price, currency = "₽", changePct, changeAbs, marketCap, asOf, tone }) {
  return (
    <div className="tw-text-right tw-shrink-0">
      <div className="tw-flex tw-items-baseline tw-justify-end tw-gap-1.5">
        <span className="cc-num tw-text-[clamp(34px,4.6vw,52px)] tw-font-medium tw-leading-none" style={{ color: "var(--cc-ink)", letterSpacing: "-0.02em" }}>{price == null ? "—" : price}</span>
        <span className="cc-num tw-text-[20px]" style={{ color: "var(--cc-ink-3)" }}>{currency}</span>
      </div>
      <div className="tw-mt-2 tw-flex tw-items-center tw-justify-end tw-gap-2">
        <NeoDelta value={changePct} suffix="%" />
        {changeAbs != null && <span className="cc-num tw-text-[12px]" style={{ color: "var(--cc-ink-3)" }}>за день</span>}
      </div>
      <div className="tw-mt-3 tw-flex tw-flex-wrap tw-items-center tw-justify-end tw-gap-x-4 tw-gap-y-1 tw-text-[11px]" style={{ color: "var(--cc-ink-3)" }}>
        {marketCap && <span><span className="cc-eyebrow tw-mr-1">Капитализация</span><span className="cc-num" style={{ color: "var(--cc-ink-2)" }}>{marketCap}</span></span>}
        {asOf && <span><span className="cc-eyebrow tw-mr-1">Обновлено</span><span className="cc-num" style={{ color: "var(--cc-ink-2)" }}>{asOf}</span></span>}
        {tone && <span className="tw-inline-flex tw-items-center tw-rounded-full tw-px-2 tw-py-0.5 tw-text-[11px] tw-font-medium" style={{ color: "var(--cc-amber)", background: "var(--cc-amber-soft)" }}>{tone}</span>}
      </div>
    </div>
  );
}

// ── Metric strip (headline KPIs, mono values + FEJ tag) ──
export function MetricStrip({ metrics = [] }) {
  if (!metrics.length) return null;
  return (
    <div className="tw-grid tw-gap-3 tw-mt-7" style={{ gridTemplateColumns: "repeat(auto-fit, minmax(150px, 1fr))" }}>
      {metrics.map((m, i) => (
        <div key={i} className={cx(panel, "tw-p-[15px] tw-relative")}>
          {m.level && <span className="tw-absolute tw-top-2.5 tw-right-2.5"><FEJTag level={m.level} /></span>}
          <div className="cc-eyebrow tw-pr-12">{m.caption}</div>
          <div className="tw-mt-2 tw-flex tw-items-baseline tw-gap-1">
            <span className="cc-num tw-text-[26px] tw-font-medium" style={{ color: "var(--cc-ink)", letterSpacing: "-0.02em" }}>{m.value}</span>
            {m.unit && <span className="cc-num tw-text-[13px]" style={{ color: "var(--cc-ink-3)" }}>{m.unit}</span>}
          </div>
          {m.delta != null && <div className="tw-mt-1"><NeoDelta value={m.delta} suffix={m.deltaSuffix || "%"} decimals={1} /></div>}
        </div>
      ))}
    </div>
  );
}

// ── Research tabs (sticky, accent underline) ──
export function ResearchTabs({ tabs = [], activeId, onSelect, right }) {
  return (
    <div className="tw-sticky tw-top-0 tw-z-20 tw-flex tw-items-stretch tw-gap-1 tw-border-b"
      style={{ borderColor: "var(--cc-line)", background: "color-mix(in srgb, var(--cc-bg) 86%, transparent)", backdropFilter: "blur(12px)" }}>
      <div role="tablist" aria-label="Разделы карточки" className="tw-flex tw-gap-1 tw-overflow-x-auto">
        {tabs.map((t) => {
          const active = activeId === t.id;
          return (
            <button key={t.id} role="tab" aria-selected={active} onClick={() => onSelect(t.id)}
              className="tw-px-4 tw-py-3 tw-text-[14px] tw-font-medium tw-bg-transparent tw-border-0 tw-cursor-pointer tw-whitespace-nowrap tw--mb-px tw-border-b-2 tw-transition-colors focus-visible:tw-outline-none"
              style={{ color: active ? "var(--cc-ink)" : "var(--cc-ink-2)", borderColor: active ? "var(--cc-accent)" : "transparent", fontFamily: "var(--cc-sans)" }}>
              {t.label}
            </button>
          );
        })}
      </div>
      {right && <div className="tw-relative tw-ml-auto tw-shrink-0 tw-flex tw-items-center">{right}</div>}
    </div>
  );
}

// ── Analytical section wrapper (mono number + serif H2 + FEJ tag, flat panel) ──
export function AnalystTile({ number, title, level, id, right, children }) {
  return (
    <section id={id} className="tw-scroll-mt-[120px]">
      {(number || title) && (
        <div className="tw-flex tw-items-baseline tw-gap-3 tw-mb-3">
          {number != null && <span className="cc-num tw-text-[13px]" style={{ color: "var(--cc-ink-3)" }}>{String(number).padStart(2, "0")}</span>}
          <h2 className="cc-serif tw-m-0 tw-text-[22px] tw-font-semibold" style={{ color: "var(--cc-ink)" }}>{title}</h2>
          {level && <FEJTag level={level} />}
          {right && <span className="tw-ml-auto">{right}</span>}
        </div>
      )}
      <div className={cx(panel, "tw-p-6")}>{children}</div>
    </section>
  );
}

// ── Executive intelligence panel ("Что важно сейчас") ──
export function ExecutiveIntelligencePanel({ title = "Что важно сейчас", thesis, insights = [], mainRisk, pricedIn, whatChanges, tone, updated }) {
  if (!thesis && !insights.length && !mainRisk) return null;
  return (
    <div className={cx(panel, "tw-p-6 tw-relative tw-overflow-hidden")} style={{ borderLeft: "2px solid var(--cc-accent)" }}>
      <div className="tw-flex tw-items-center tw-gap-2 tw-mb-3">
        <h2 className="cc-serif tw-m-0 tw-text-[22px] tw-font-semibold" style={{ color: "var(--cc-ink)" }}>{title}</h2>
        {tone && <span className="tw-inline-flex tw-items-center tw-rounded-full tw-px-2.5 tw-py-0.5 tw-text-[12px] tw-font-medium" style={{ color: "var(--cc-amber)", background: "var(--cc-amber-soft)" }}>{tone}</span>}
      </div>
      {thesis && <p className="cc-serif tw-text-[19px] tw-leading-[1.5] tw-m-0 tw-mb-4 tw-max-w-[66ch]" style={{ color: "var(--cc-ink)" }}>{thesis}</p>}
      {insights.length > 0 && (
        <ol className="tw-list-none tw-p-0 tw-m-0 tw-mb-4 tw-flex tw-flex-col tw-gap-2.5">
          {insights.map((it, i) => (
            <li key={i} className="tw-flex tw-gap-3 tw-items-start">
              <span className="cc-num tw-text-[13px] tw-mt-0.5 tw-shrink-0" style={{ color: "var(--cc-accent)" }}>{String(i + 1).padStart(2, "0")}</span>
              <span className="cc-serif tw-text-[16.5px] tw-leading-[1.6]" style={{ color: "var(--cc-ink-2)" }}>{it.text || it} {it.level && <FEJTag level={it.level} />}</span>
            </li>
          ))}
        </ol>
      )}
      {(mainRisk || pricedIn || whatChanges) && (
        <div className="tw-grid tw-gap-3 tw-mt-2" style={{ gridTemplateColumns: "repeat(auto-fit, minmax(180px, 1fr))" }}>
          {mainRisk && <FootCell label="Главный риск" tone="amber">{mainRisk}</FootCell>}
          {pricedIn && <FootCell label="Что уже в цене">{pricedIn}</FootCell>}
          {whatChanges && <FootCell label="Что изменит вывод">{whatChanges}</FootCell>}
        </div>
      )}
      {updated && <div className="tw-mt-4 tw-text-[11px]" style={{ color: "var(--cc-ink-3)" }}>Не является инвестиционной рекомендацией · {updated}</div>}
    </div>
  );
}
function FootCell({ label, children, tone }) {
  return (
    <div className="tw-rounded-[10px] tw-p-3" style={{ background: tone === "amber" ? "var(--cc-amber-soft)" : "var(--cc-panel-2)", border: "1px solid var(--cc-line)" }}>
      <div className="cc-eyebrow tw-mb-1" style={tone === "amber" ? { color: "var(--cc-amber)" } : undefined}>{label}</div>
      <div className="tw-text-[13px] tw-leading-[1.5]" style={{ color: "var(--cc-ink-2)", fontFamily: "var(--cc-sans)" }}>{children}</div>
    </div>
  );
}

// ── Decision support rail (sticky right; decision support, not advice) ──
export function DecisionSupportRail({ tone, fairBase, upside, currency = "₽", confidence, sourcesCount, asOf, onCheckIdea, onScenarios }) {
  return (
    <aside className="tw-sticky tw-top-[80px] tw-self-start tw-w-full">
      <div className={cx(panel, "tw-overflow-hidden")}>
        {tone && <div className="tw-px-5 tw-py-3 tw-text-[13px] tw-font-medium" style={{ background: "var(--cc-amber-soft)", color: "var(--cc-amber)" }}>{tone}</div>}
        {fairBase != null && (
          <div className="tw-px-5 tw-py-4 tw-border-b" style={{ borderColor: "var(--cc-line)" }}>
            <div className="cc-eyebrow tw-mb-1">Справедливая стоимость (база)</div>
            <div className="tw-flex tw-items-baseline tw-gap-2">
              <span className="cc-num tw-text-[24px] tw-font-medium" style={{ color: "var(--cc-ink)" }}>{fairBase}</span>
              <span className="cc-num tw-text-[13px]" style={{ color: "var(--cc-ink-3)" }}>{currency}</span>
              {upside != null && <span className="tw-ml-auto"><NeoDelta value={upside} suffix="%" decimals={0} /></span>}
            </div>
            <div className="tw-text-[11px] tw-mt-1" style={{ color: "var(--cc-ink-3)" }}>потенциал к модельной цене (живьём)</div>
          </div>
        )}
        <div className="tw-px-5 tw-py-3 tw-text-[12px] tw-flex tw-flex-col tw-gap-1.5" style={{ color: "var(--cc-ink-3)" }}>
          {confidence && <div>Уверенность: <span style={{ color: "var(--cc-ink-2)" }}>{confidence}</span></div>}
          {sourcesCount != null && <div className="cc-num">{sourcesCount} источников{asOf ? " · " + asOf : ""}</div>}
        </div>
        <div className="tw-px-5 tw-py-4 tw-flex tw-flex-col tw-gap-2 tw-border-t" style={{ borderColor: "var(--cc-line)" }}>
          <button type="button" onClick={onCheckIdea}
            className="tw-w-full tw-rounded-[8px] tw-py-2.5 tw-text-[14px] tw-font-semibold tw-border-0 tw-cursor-pointer"
            style={{ background: "var(--cc-accent)", color: "#fff", fontFamily: "var(--cc-sans)" }}>Проверить идею</button>
          <button type="button" onClick={onScenarios}
            className="tw-w-full tw-rounded-[8px] tw-py-2.5 tw-text-[14px] tw-font-medium tw-cursor-pointer"
            style={{ background: "transparent", color: "var(--cc-ink)", border: "1px solid var(--cc-line-2)", fontFamily: "var(--cc-sans)" }}>Сценарный анализ</button>
        </div>
        <div className="tw-px-5 tw-pb-4 tw-text-[11px]" style={{ color: "var(--cc-ink-3)" }}>Это аналитическое «второе мнение», а не инвестиционная рекомендация.</div>
      </div>
    </aside>
  );
}

import React, { useState, useEffect, useMemo } from "react";
import { CompanyLogo } from "../design/CompanyLogo";
import { money, num } from "../screener/ScreenerNeo";
import { ObsLineChart } from "../observer/ObsPanels";
import "../styles/indices.css";

// =============================================================
// IndexHubView / IndexDetailView / FearGreedDetailView — «Индексы».
// Точная раскатка 2026-07-14 по одобренному мокапу indices-fear-greed-v1.html
// (референс — конкурент Инвестминт: хаб индексов, drill-down в отдельный
// индекс с графиком по периодам, gauge для индекса страха и жадности).
// Данные: /api/market/indices (IMOEX/MCFTR/RTSI — полная история),
// /api/market/indices/{ticker}/detail?period= (график, добавлен для этой
// задачи), /api/market/pulse (секторные индексы + индекс страха и жадности,
// уже существовали), /api/screener/scored (компании для таблиц).
// =============================================================

const apiBase = () => process.env.REACT_APP_API_URL || "http://localhost:8000";
const MAIN_TICKERS = ["IMOEX", "MCFTR", "RTSI"];

const TIMEFRAMES = [
  { id: "1m", label: "1 мес" },
  { id: "6m", label: "6 мес" },
  { id: "ytd", label: "С начала года" },
  { id: "1y", label: "1 год" },
  { id: "3y", label: "3 года" },
];

// Коды секторных индексов MOEX -> внутренняя классификация Basis (Company.sector).
// ДВЕ РАЗНЫЕ таксономии (официальная MOEX vs внутренняя Basis) — совпадают не
// везде (напр. MOEXMM «Металлы и добыча» vs наша «Металлургия»), отсюда явная
// карта соответствия, а не текстовое сравнение имён.
const SECTOR_TO_INTERNAL = {
  MOEXOG: "Нефть и газ",
  MOEXEU: "Электроэнергетика",
  MOEXTL: "Телеком",
  MOEXCH: "Химия",
  MOEXMM: "Металлургия",
  MOEXFN: "Финансы",
  MOEXCN: "Потребительский сектор",
  MOEXIT: "IT-сектор",
  MOEXTN: "Транспорт и логистика",
  MOEXRE: "Девелопмент",
};

const INDEX_EXPLAIN = {
  IMOEX: {
    title: "Что показывает индекс Мосбиржи простыми словами",
    body: [
      "Индекс объединяет цены 46 крупнейших и самых ликвидных российских акций в одно число — в пунктах. Вес каждой акции — по free-float капитализации, то есть по той части акций, что реально торгуется на бирже, а не лежит у мажоритариев. Чем крупнее компания на рынке, тем сильнее её акция тянет индекс.",
      "Есть валютный двойник — индекс РТС (те же акции, но в долларах), и индекс полной доходности (MCFTR), который добавляет к ценам ещё и дивиденды — поэтому на длинной дистанции обгоняет обычный IMOEX.",
    ],
  },
  MCFTR: {
    title: "Что показывает индекс полной доходности простыми словами",
    body: [
      "Тот же состав акций, что у индекса Мосбиржи, но с одним отличием: сюда реинвестируются дивиденды, а не просто фиксируется цена. На длинной дистанции MCFTR обгоняет обычный IMOEX — так выглядела бы доходность инвестора, который держал широкий рынок и не тратил дивиденды.",
    ],
  },
  RTSI: {
    title: "Что показывает индекс РТС простыми словами",
    body: [
      "Долларовый двойник индекса Мосбиржи — те же акции, тот же вес, но пересчитано в доллары. Разница между динамикой IMOEX и RTSI — это, по сути, движение курса рубля: если рубль слабеет быстрее, чем растут акции, RTSI может падать даже при растущем IMOEX.",
    ],
  },
};

const FG_COMP_META = {
  momentum: { name: "Импульс рынка", desc: "IMOEX относительно своей средней за 125 дней. Ниже средней — рынок слабее обычного, признак осторожности." },
  volatility: { name: "Волатильность", desc: "Индекс волатильности RVI относительно своей средней. Резкий рост волатильности — верный признак страха." },
  breadth: { name: "Ширина рынка", desc: "Доля голубых фишек с положительной доходностью за 20 торговых дней — участвует ли в движении весь рынок или только тяжеловесы." },
  risk_appetite: { name: "Спрос на риск", desc: "Акции против гособлигаций за 20 дней. Когда деньги уходят в ОФЗ, а не в акции — аппетит к риску падает." },
};

function fmtDelta(pct) {
  if (pct == null) return "—";
  const up = pct >= 0;
  return (up ? "▲ " : "▼ ") + Math.abs(pct).toFixed(2).replace(".", ",") + "%";
}

function Sparkline({ points, color, w = 200, h = 36 }) {
  if (!points || points.length < 2) return null;
  const min = Math.min(...points), max = Math.max(...points);
  const range = max - min || 1;
  const step = w / (points.length - 1);
  const d = points.map((v, i) => `${i === 0 ? "M" : "L"}${(i * step).toFixed(1)},${(h - ((v - min) / range) * h).toFixed(1)}`).join(" ");
  return (
    <svg width="100%" height={h} viewBox={`0 0 ${w} ${h}`} preserveAspectRatio="none">
      <path d={d} fill="none" stroke={color} strokeWidth="2" />
    </svg>
  );
}

function fgColorFor(score) {
  if (score == null) return "var(--text-tertiary)";
  if (score < 20) return "var(--danger)";
  if (score < 40) return "var(--warning)";
  if (score < 60) return "var(--text-tertiary)";
  return "var(--success)";
}

// =============================================================
// ХАБ ИНДЕКСОВ
// =============================================================
export function IndexHubView({ onBack, onSelectIndex, onOpenFearGreed }) {
  const [pulse, setPulse] = useState(null);
  const [indices, setIndices] = useState(null);

  useEffect(() => {
    const api = apiBase();
    Promise.all([
      fetch(`${api}/api/market/pulse`).then((r) => (r.ok ? r.json() : null)).catch(() => null),
      fetch(`${api}/api/market/indices`).then((r) => (r.ok ? r.json() : null)).catch(() => null),
    ]).then(([p, idx]) => { setPulse(p); setIndices(idx); });
  }, []);

  const fg = pulse?.fear_greed;

  return (
    <div className="idx-screen">
      {onBack && <div className="idx-crumb"><button onClick={onBack}>← Назад</button></div>}
      <div className="idx-sec-head"><span className="idx-eyebrow">Рынок</span><h1 className="idx-h1">Индексы</h1></div>
      <p className="idx-sub">
        Барометры российского рынка одним числом — от главного индикатора рынка акций до настроения инвесторов.{" "}
        <span className="idx-tag idx-tag--fact">факт — котировки MOEX</span>
      </p>

      {fg && fg.score != null && (
        <>
          <div className="idx-grp-head">Индекс страха и жадности</div>
          <p className="idx-grp-sub">Композитная оценка настроений рынка Basis — куда сейчас смотрят деньги.</p>
          <button className="idx-panel idx-fg-teaser" onClick={onOpenFearGreed}>
            <div>
              <div className="idx-fg-teaser-name">Индекс страха и жадности Basis</div>
              <div className="idx-fg-teaser-desc">
                Композит из импульса рынка, волатильности, ширины рынка и спроса на риск — одно число вместо десятка индикаторов.{" "}
                <span className="idx-tag">оценка/модель Basis</span>
              </div>
            </div>
            <div className="idx-fg-teaser-num">
              <div>
                <div className="idx-fg-mini-num" style={{ color: fgColorFor(fg.score) }}>{Math.round(fg.score)}</div>
                <div className="idx-fg-mini-lbl" style={{ color: fgColorFor(fg.score) }}>{fg.label}</div>
              </div>
            </div>
          </button>
        </>
      )}

      <div className="idx-grp-head">Основные индексы</div>
      <p className="idx-grp-sub">Барометры всего рынка акций и долга — полная история, график по периодам.</p>
      <div className="idx-grid">
        {(indices || []).map((row) => (
          <button key={row.ticker} className="idx-card" onClick={() => onSelectIndex(row.ticker)}>
            <div className="idx-card-top"><span className="idx-card-name">{row.name}</span><span className="idx-card-tk">{row.ticker}</span></div>
            <div className="idx-card-val">
              <b>{num(row.level, 2)}</b>
              <span className={"idx-card-delta " + (row.change_pct >= 0 ? "idx-pos" : "idx-neg")}>{fmtDelta(row.change_pct)}</span>
            </div>
            <Sparkline points={row.spark} color={row.change_pct >= 0 ? "var(--success)" : "var(--danger)"} />
            <div className="idx-card-foot">3 года истории · график по периодам</div>
          </button>
        ))}
        {!indices && <div className="idx-loading">Загрузка…</div>}
      </div>

      <div className="idx-grp-head">Отраслевые индексы MOEX</div>
      <p className="idx-grp-sub">
        Как себя чувствует отдельный сектор рынка.{" "}
        <span className="idx-tag idx-tag--est">пока только текущее значение — история накапливается</span>
      </p>
      <div className="idx-grid">
        {(pulse?.sectors || []).map((s) => (
          <button key={s.ticker} className="idx-card" onClick={() => onSelectIndex(s.ticker)}>
            <div className="idx-card-top"><span className="idx-card-name">{s.name}</span><span className="idx-card-tk">{s.ticker}</span></div>
            <div className="idx-card-val">
              <b>{num(s.level, 0)}</b>
              <span className={"idx-card-delta " + (s.change_pct >= 0 ? "idx-pos" : "idx-neg")}>{fmtDelta(s.change_pct)}</span>
            </div>
            <div className="idx-card-foot"><span className="idx-card-badge">Live</span>&nbsp;история копится</div>
          </button>
        ))}
        {pulse && !(pulse.sectors || []).length && <div className="idx-empty">Нет данных.</div>}
      </div>
    </div>
  );
}

// =============================================================
// ДЕТАЛЬНАЯ СТРАНИЦА ИНДЕКСА
// =============================================================
export function IndexDetailView({ ticker, onOpenHub, onSelectCompany }) {
  const isMain = MAIN_TICKERS.includes(ticker);
  const [period, setPeriod] = useState("3y");
  const [detail, setDetail] = useState(null);
  const [pulse, setPulse] = useState(null);
  const [scored, setScored] = useState(null);

  useEffect(() => { setDetail(null); setPeriod("3y"); }, [ticker]);

  useEffect(() => {
    if (!isMain) return;
    const api = apiBase();
    let alive = true;
    fetch(`${api}/api/market/indices/${ticker}/detail?period=${period}`)
      .then((r) => (r.ok ? r.json() : null)).catch(() => null)
      .then((d) => { if (alive) setDetail(d); });
    return () => { alive = false; };
  }, [ticker, period, isMain]);

  useEffect(() => {
    const api = apiBase();
    fetch(`${api}/api/market/pulse`).then((r) => (r.ok ? r.json() : null)).catch(() => null).then(setPulse);
  }, []);

  useEffect(() => {
    const api = apiBase();
    fetch(`${api}/api/screener/scored?universe=all`).then((r) => (r.ok ? r.json() : null)).catch(() => null)
      .then((d) => setScored(d?.rows || []));
  }, []);

  // RGBI (индекс гособлигаций) приходит не из pulse.sectors, а из pulse.indices —
  // тоже без хранимой истории (index_history пуст для него), деградирует так же,
  // как отраслевые индексы MOEX. Ищем в обоих списках.
  const sectorEntry = !isMain
    ? [...(pulse?.sectors || []), ...(pulse?.indices || [])].find((s) => s.ticker === ticker)
    : null;
  const sectorInternalName = SECTOR_TO_INTERNAL[ticker];

  const drivers = useMemo(() => {
    if (!isMain || !pulse?.sectors) return [];
    return [...pulse.sectors]
      .filter((s) => s.change_pct != null)
      .sort((a, b) => Math.abs(b.change_pct) - Math.abs(a.change_pct))
      .slice(0, 6);
  }, [pulse, isMain]);

  const companies = useMemo(() => {
    if (!scored) return [];
    if (isMain) return [...scored].sort((a, b) => (b.market_cap || 0) - (a.market_cap || 0)).slice(0, 8);
    return scored
      .filter((c) => c.sector === sectorInternalName)
      .sort((a, b) => (b.market_cap || 0) - (a.market_cap || 0))
      .slice(0, 12);
  }, [scored, isMain, sectorInternalName]);

  if (isMain && !detail) return <div className="idx-screen"><div className="idx-loading">Загрузка индекса…</div></div>;
  if (!isMain && !pulse) return <div className="idx-screen"><div className="idx-loading">Загрузка индекса…</div></div>;
  if (!isMain && !sectorEntry) return <div className="idx-screen"><div className="idx-empty">Индекс не найден.</div></div>;

  const name = isMain ? detail.name : sectorEntry.name;
  const level = isMain ? detail.level : sectorEntry.level;
  const changePct = isMain ? detail.change_pct : sectorEntry.change_pct;
  const changeAbs = isMain ? detail.change_abs : sectorEntry.change_abs;
  const explain = INDEX_EXPLAIN[ticker];

  return (
    <div className="idx-screen">
      <div className="idx-crumb"><button onClick={onOpenHub}>Индексы</button> · {name}</div>
      <div className="idx-sec-head"><span className="idx-eyebrow">Рынок</span><h1 className="idx-h1">{name}</h1></div>
      <p className="idx-sub">
        {ticker} — {isMain ? "главный индикатор российского рынка: живое значение, график и что на него влияет." : "отраслевой индекс Мосбиржи: как себя чувствует сектор в одном числе."}{" "}
        <span className="idx-tag idx-tag--fact">факт — расчёт Мосбиржи</span>
      </p>

      <div className="idx-panel idx-hero">
        <div>
          <div className="idx-hero-tk"><span className={"idx-hero-dot" + (changePct < 0 ? " idx-hero-dot--down" : "")} />{ticker} · основная сессия</div>
          <div><span className="idx-hero-val">{num(level, 2)}</span><span className="idx-hero-unit">пунктов</span></div>
          <div className={"idx-hero-delta " + (changePct >= 0 ? "idx-pos" : "idx-neg")}>
            {fmtDelta(changePct)}{changeAbs != null ? ` (${changeAbs >= 0 ? "+" : ""}${num(changeAbs, 2)} п.)` : ""} за день
          </div>
        </div>
      </div>

      {isMain ? (
        <>
          <div className="idx-panel idx-stats-row" style={{ marginTop: -1 }}>
            <div><div className="idx-stat-l">За месяц</div><div className={"idx-stat-v " + (detail.month_change_pct >= 0 ? "idx-pos" : "idx-neg")}>{fmtDelta(detail.month_change_pct)}</div></div>
            <div><div className="idx-stat-l">За год</div><div className={"idx-stat-v " + (detail.year_change_pct >= 0 ? "idx-pos" : "idx-neg")}>{fmtDelta(detail.year_change_pct)}</div></div>
            <div><div className="idx-stat-l">Объём за день</div><div className="idx-stat-v">{detail.volume_today != null ? money(detail.volume_today) : "—"}</div></div>
          </div>

          <div className="idx-tf-row">
            <div className="idx-tf-tabs">
              {TIMEFRAMES.map((t) => (
                <button key={t.id} className={"idx-tf-opt" + (period === t.id ? " idx-tf-opt--on" : "")} onClick={() => setPeriod(t.id)}>{t.label}</button>
              ))}
            </div>
            {detail.period_change_pct != null && (
              <span className={detail.period_change_pct >= 0 ? "idx-pos" : "idx-neg"} style={{ fontFamily: "var(--font-mono)", fontSize: 12, fontWeight: 700 }}>
                {detail.period_change_pct >= 0 ? "+" : ""}{num(detail.period_change_pct, 1)}% за период
              </span>
            )}
          </div>
          <div className="idx-panel idx-chart-wrap">
            <ObsLineChart
              unit=""
              series={[{
                name,
                color: (detail.period_change_pct ?? 0) >= 0 ? "var(--success)" : "var(--danger)",
                points: (detail.points || []).map((p) => ({ as_of: p.date, value: p.close })),
              }]}
            />
          </div>

          {drivers.length > 0 && (
            <div className="idx-panel idx-drivers">
              <span className="idx-eyebrow">Что тянуло индекс сегодня</span>
              <span className="idx-tag" style={{ marginLeft: 8 }}>суждение Basis</span>
              <p style={{ fontSize: "11.5px", color: "var(--text-tertiary)", margin: "10px 0" }}>
                Вклад отраслевых индексов в сегодняшнее движение — какой сектор тянул рынок, а не просто «индекс вырос».
              </p>
              {drivers.map((d) => {
                const mag = Math.min(50, Math.abs(d.change_pct) * 12);
                return (
                  <div className="idx-driver-row" key={d.ticker}>
                    <span>{d.name}</span>
                    <div className="idx-driver-bar-track">
                      <div
                        className="idx-driver-bar-fill"
                        style={{
                          background: d.change_pct >= 0 ? "var(--success)" : "var(--danger)",
                          left: d.change_pct >= 0 ? "50%" : `${50 - mag}%`,
                          right: d.change_pct >= 0 ? `${50 - mag}%` : "50%",
                        }}
                      />
                    </div>
                    <span className={"idx-driver-val " + (d.change_pct >= 0 ? "idx-pos" : "idx-neg")}>{fmtDelta(d.change_pct)}</span>
                  </div>
                );
              })}
            </div>
          )}
        </>
      ) : (
        <div className="idx-degraded-note">
          <span>⚠</span>
          <span>
            <b>График по периодам пока недоступен.</b> Мы собираем ежедневную историю этого индекса — как только накопится
            достаточно точек, здесь появится полноценный график, как у индекса Мосбиржи. Пока — только текущее значение и
            дневная динамика.
          </span>
        </div>
      )}

      {explain && (
        <div className="idx-panel idx-explain">
          <h3>{explain.title}</h3>
          {explain.body.map((p, i) => <p key={i}>{p}</p>)}
        </div>
      )}

      {companies.length > 0 && (
        <div className="idx-panel">
          <div className="idx-tbl-head">
            <span className="idx-eyebrow">{isMain ? "Крупнейшие компании индекса" : `Компании сектора «${sectorInternalName}» в Basis`}</span>
            <span className="idx-tag idx-tag--est" style={{ marginLeft: 8 }}>
              {isMain ? "оценка — приближение Basis, не официальные веса" : "классификация Basis, не официальные веса индекса"}
            </span>
          </div>
          <table className="idx-companies-tbl">
            <thead>
              <tr>
                <th>Компания</th>
                {!isMain ? null : <th>Сектор</th>}
                <th>Капитализация</th>
                <th>BASIS-балл</th>
              </tr>
            </thead>
            <tbody>
              {companies.map((c) => (
                <tr key={c.ticker} onClick={() => onSelectCompany && onSelectCompany(c.ticker)}>
                  <td>
                    <div className="idx-co-asset">
                      <CompanyLogo ticker={c.ticker} name={c.name} size={28} />
                      {c.name}
                    </div>
                  </td>
                  {!isMain ? null : <td style={{ textAlign: "left", color: "var(--text-tertiary)" }}>{c.sector}</td>}
                  <td>{c.market_cap != null ? money(c.market_cap) : "—"}</td>
                  <td>{c.basis ?? "—"}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}

// =============================================================
// ИНДЕКС СТРАХА И ЖАДНОСТИ — гейдж
// =============================================================
export function FearGreedDetailView({ onOpenHub }) {
  const [pulse, setPulse] = useState(null);

  useEffect(() => {
    const api = apiBase();
    fetch(`${api}/api/market/pulse`).then((r) => (r.ok ? r.json() : null)).catch(() => null).then(setPulse);
  }, []);

  const fg = pulse?.fear_greed;

  if (!pulse) return <div className="idx-screen"><div className="idx-loading">Загрузка индекса страха и жадности…</div></div>;
  if (!fg || fg.score == null) return <div className="idx-screen"><div className="idx-empty">{fg?.note || "Недостаточно данных для расчёта."}</div></div>;

  const score = fg.score;
  const angle = -90 + (score / 100) * 180;
  const color = fgColorFor(score);
  const components = Object.entries(fg.components || {});

  return (
    <div className="idx-screen">
      <div className="idx-crumb"><button onClick={onOpenHub}>Индексы</button> · Индекс страха и жадности</div>
      <div className="idx-sec-head"><span className="idx-eyebrow">Рынок</span><h1 className="idx-h1">Индекс страха и жадности Basis</h1></div>
      <p className="idx-sub">
        Куда сейчас смотрят деньги на российском рынке — композитная оценка настроений из {components.length} независимых сигналов.{" "}
        <span className="idx-tag">оценка/модель Basis, не торговый сигнал</span>
      </p>

      <div className="idx-panel idx-fg-wrap">
        <svg className="idx-fg-gauge-svg" viewBox="0 0 460 260">
          <path d="M30,230 A200,200 0 0,1 106,74" fill="none" stroke="var(--danger)" strokeWidth="34" strokeLinecap="round" />
          <path d="M112,68 A200,200 0 0,1 185,32" fill="none" stroke="var(--warning)" strokeWidth="34" strokeLinecap="round" />
          <path d="M192,30 A200,200 0 0,1 268,30" fill="none" stroke="var(--text-tertiary)" strokeWidth="34" strokeLinecap="round" opacity="0.55" />
          <path d="M275,32 A200,200 0 0,1 348,68" fill="none" stroke="color-mix(in srgb, var(--success) 55%, var(--warning))" strokeWidth="34" strokeLinecap="round" />
          <path d="M354,74 A200,200 0 0,1 430,230" fill="none" stroke="var(--success)" strokeWidth="34" strokeLinecap="round" />
          <g className="idx-fg-needle" style={{ transform: `rotate(${angle}deg)` }}>
            <line x1="230" y1="230" x2="230" y2="70" stroke="var(--text-primary)" strokeWidth="4" strokeLinecap="round" />
          </g>
          <circle cx="230" cy="230" r="9" fill="var(--text-primary)" />
          <text x="230" y="150" textAnchor="middle" fontFamily="var(--font-mono)" fontSize="46" fontWeight="700" fill={color}>{Math.round(score)}</text>
          <text x="230" y="178" textAnchor="middle" fontSize="14" fontWeight="700" fill={color}>{(fg.label || "").toUpperCase()}</text>
        </svg>
        <div className="idx-fg-legend">
          <span className="idx-fg-leg-i"><i style={{ background: "var(--danger)" }} />Крайний страх</span>
          <span className="idx-fg-leg-i"><i style={{ background: "var(--warning)" }} />Страх</span>
          <span className="idx-fg-leg-i"><i style={{ background: "var(--text-tertiary)" }} />Нейтрально</span>
          <span className="idx-fg-leg-i"><i style={{ background: "color-mix(in srgb, var(--success) 55%, var(--warning))" }} />Жадность</span>
          <span className="idx-fg-leg-i"><i style={{ background: "var(--success)" }} />Крайняя жадность</span>
        </div>
      </div>

      <span className="idx-eyebrow">Из чего складывается индекс — охват {fg.coverage}</span>
      <div className="idx-fg-comp-grid">
        {components.map(([key, c]) => {
          const meta = FG_COMP_META[key] || { name: key, desc: "" };
          const cScore = c.score;
          const cColor = fgColorFor(cScore);
          return (
            <div className="idx-panel idx-fg-comp-card" key={key}>
              <div className="idx-fg-comp-head">
                <span className="idx-fg-comp-name">{meta.name}</span>
                <span className="idx-fg-comp-score" style={{ color: cColor }}>{cScore != null ? Math.round(cScore) : "—"}</span>
              </div>
              <div className="idx-fg-comp-bar"><i style={{ width: `${cScore ?? 0}%`, background: cColor }} /></div>
              <div className="idx-fg-comp-desc">{meta.desc}</div>
            </div>
          );
        })}
      </div>

      <div className="idx-fg-future">
        <span>🕓</span>
        <span>
          <b>В разработке:</b> сравнение с прошлыми значениями («неделю назад», «месяц назад») и график истории индекса —
          сейчас балл считается только на лету и нигде не сохраняется день за днём. Чтобы построить это честно, нужен
          ежедневный снепшот на бэкенде — не подделываем историю, которой нет.
        </span>
      </div>

      <div className="idx-panel idx-explain">
        <h3>Как читать индекс</h3>
        <p>
          0–20 — крайний страх: рынок в панике, часто перепродан. 80–100 — крайняя жадность: рынок разогрет, часто
          перекуплен. Это не сигнал «купить» или «продать» — индикатор настроений, один из факторов для собственного
          суждения, не автоматическая рекомендация.
        </p>
      </div>
    </div>
  );
}

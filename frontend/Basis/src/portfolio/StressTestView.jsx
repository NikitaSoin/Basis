import React, { useEffect, useRef, useState } from "react";
import { FlaskConical, Send, RotateCcw, PanelLeftClose, PanelLeftOpen } from "lucide-react";
import { CompanyLogo } from "../design/CompanyLogo";
import "../styles/stress-test.css";

// StressTestView v4 — «Стресс-тестирование» как инструмент, не анкета (владелец,
// 2026-07-23: «перекопируй расположение и цвета из Клод-дизайна» — предыдущая
// версия (v3) была лишь ВДОХНОВЛЕНА прототипом, а не его копией: разная
// структура страницы (линейный стек секций вместо рельс+основная область),
// не было агрегированного «индекса рынка», не те цветовые токены (--success/
// --danger вместо канонiчных --bs-up/--bs-down). v4 — консоль как в
// прототипе: рельс слева (пресеты + слайдеры), справа — крупный
// взвешенный индекс + карта рынка, ниже — full-bleed лидерборд «хуже/лучше».
// Свободный текст («что если...») остаётся отдельным путём через LLM-парсер:
// КОГДА он извлекает явные числовые уровни — слайдеры визуально едут в
// интерпретированную позицию (честно — только когда backend реально это
// прислал, не выдумываем координаты на фронте). Пресеты — качественная
// факторная модель (санкции/конфликт/спрос), у неё нет числовых
// ставка/курс/нефть эквивалентов в движке — не пытаемся натянуть их на
// слайдеры, остаются отдельным результатом (DirectionCompass), как раньше.
//
// v4.1 (владелец, 2026-07-24, по живому демо в Клод-дизайне):
// — Слайдеры считают МГНОВЕННО локально в JS (companyImpact/computeAllImpacts
//   ниже — точный порт _company_numeric_impact()/numeric_impact() из
//   backend/app/services/stress_numeric.py), а не через debounce+round-trip на
//   /numeric — «в демо пересчитывается мгновенно, у нас задержка». Сырые
//   коэффициенты грузятся ОДИН раз при заходе на экран (/stress-test/coefficients).
//   Правишь арифметику — правь СИНХРОННО в обоих местах, иначе слайдерный путь
//   (клиент) и путь через «Спросить»/пресеты (сервер) разойдутся в цифрах.
// — Эшелоны: взаимоисключающие срезы 1/2/3/все (echelon===n, backend уже
//   размечает поле) — та же таксономия и ярлыки, что в Скринере. Дефолт —
//   1-й эшелон (голубые фишки, самый узнаваемый вход); длинный хвост мелких
//   бумаг с экстремальным % иначе забивал бы карту, если бы дефолтом было «все».
// — Плитки/строки — имя компании первично, тикер вторично (мельче/mono), клик
//   открывает карточку компании (onOpenCompany, тот же паттерн, что у
//   PortfolioV2/AssistantView в App.js).
//
// v5 (design-critic review 2026-07-25, «Консоль → Досье»): всё, что рендерится
// ПОСЛЕ .st-console, больше не тёмное продолжение приборной панели — это
// сознательный переход на светлую «бумагу» (--bs-surface/--bs-card/--bs-copper),
// собранную как ОДНА глава-досье (заголовок-вердикт → доказательства →
// компас направления → «Спросите ещё»), а не три несвязанные карточки на
// легаси-примитивах (Card/Badge/Delta из design/primitives.jsx, NEO-токены
// --success/--danger). Метафора: тёмная консоль — приборная панель, которую
// «включаешь» и двигаешь рычаги; светлая бумага ниже — распечатанный отчёт по
// итогам прогона, который откладывается и перечитывается. Новые компоненты —
// DossierHead/ShieldSide/ExpertDossier/FinancialTable/DirectionCompass/
// NextQuestionStrip, стили — конец stress-test.css (секция «Досье»).

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

// ---- JS-двойник числового движка backend'а (stress_numeric.py) — см. пояснение
// в шапке файла (v4.1). Держать в точности синхронно с
// _company_numeric_impact()/numeric_impact() — источник истины там, это порт.
const OIL_SECTOR_TOKENS = ["нефт", "газ", "oil", "gas"];
const IMPACT_METRICS = ["revenue", "ebitda", "net_profit"];

function round1(v) {
  return Math.round(v * 10) / 10;
}

function companyImpact(coefs, spot, fin, sector, keyRatePct, fxUsdrub, oilBrentUsd, brentSpot) {
  const sectorL = (sector || "").toLowerCase();
  const factorDeltas = {};

  if (keyRatePct != null && spot.key_rate_pct != null && coefs.rate) {
    const d = keyRatePct - spot.key_rate_pct;
    if (Math.abs(d) > 1e-9) factorDeltas.rate = d;
  }
  if (fxUsdrub != null && spot.fx_usdrub != null && coefs.fx) {
    const d = fxUsdrub - spot.fx_usdrub;
    if (Math.abs(d) > 1e-9) factorDeltas.fx = d;
  }
  if (oilBrentUsd != null && brentSpot && OIL_SECTOR_TOKENS.some((t) => sectorL.includes(t)) &&
      spot.commodity_usd != null && coefs.commodity) {
    const rel = oilBrentUsd / brentSpot - 1;
    const d = spot.commodity_usd * rel;
    if (Math.abs(d) > 1e-9) factorDeltas.commodity = d;
  }

  // Компания с ХОТЯ БЫ одним коэффициентом остаётся во вселенной ВСЕГДА (не
  // return null при пустых factorDeltas) — владелец, 2026-07-24: «компании
  // вылетают/появляются при движении слайдера, это не норма». 0 — честный ноль
  // (ни один текущий фактор её не касается), не «нет данных» — держать
  // синхронно с _company_numeric_impact() в stress_numeric.py.
  const hasAnyFactor = Object.keys(factorDeltas).length > 0;

  const metrics = {};
  for (const m of IMPACT_METRICS) {
    let total = 0, covered = false;
    for (const f in factorDeltas) {
      const c = coefs[f] ? coefs[f][m] : null;
      if (c == null) continue;
      covered = true;
      total += c * factorDeltas[f];
    }
    const base = fin[m] != null ? fin[m] : null;
    if (!covered) {
      metrics[m] = hasAnyFactor
        ? { delta_bn: null, pct_of_base: null, base_bn: base } // фактор сдвинут, но коэффициент на эту метрику не задан — реально не знаем
        : { delta_bn: 0, pct_of_base: 0, base_bn: base }; // ни один текущий фактор её не касается — честный ноль
      continue;
    }
    // % от базы вырожден при крошечной базе — показываем % только когда
    // |Δ| ≤ 2×|базы|, иначе только млрд ₽ (см. stress_numeric.py).
    let pct = null;
    if (base && Math.abs(total) <= 2 * Math.abs(base)) pct = round1((total / Math.abs(base)) * 100);
    metrics[m] = { delta_bn: round1(total), pct_of_base: pct, base_bn: base };
  }
  return { metrics };
}

// Вся вселенная → результат в ТОЙ ЖЕ форме, что /numeric (companies[] с metrics),
// поэтому ConsoleHeadline/MarketMap/Boards/FinancialTable принимают его без
// изменений — независимо от того, посчитан он сервером (ask/preset) или
// локально (слайдеры).
function computeAllImpacts(coefficients, keyRatePct, fxUsdrub, oilBrentUsd, brentSpot) {
  const companies = [];
  for (const c of coefficients) {
    const impact = companyImpact(c.coefficients || {}, c.macro_spot || {}, c.financials || {},
      c.sector, keyRatePct, fxUsdrub, oilBrentUsd, brentSpot);
    if (!impact) continue;
    companies.push({
      ticker: c.ticker, name: c.name, sector: c.sector,
      is_blue_chip: c.is_blue_chip, echelon: c.echelon, metrics: impact.metrics,
    });
  }
  const sortKey = (c) => {
    const np = c.metrics.net_profit;
    if (np.pct_of_base != null) return Math.abs(np.pct_of_base);
    if (np.delta_bn != null) return 999 + Math.abs(np.delta_bn);
    return -1;
  };
  companies.sort((a, b) => {
    if (a.is_blue_chip !== b.is_blue_chip) return a.is_blue_chip ? -1 : 1;
    return sortKey(b) - sortKey(a);
  });
  return { companies };
}

// Эшелоны (backend: BLUE_CHIPS=1, следующие ECHELON2_SIZE по капитализации=2,
// остальное=3) — та же таксономия и те же ярлыки, что в Скринере (UNIVERSES,
// screener/ScreenerNeo.jsx), по рекомендации product-analyst-biz (2026-07-24):
// взаимоисключающие СРЕЗЫ (echelon===n), не накопительный ≤n — «2-й эшелон»
// значит ТОЛЬКО 2-й, без голубых фишек, ровно как уже устроено в Скринере
// (владелец: «фильтр не то ... как в скринере есть»). "all" — без фильтра.
const ECHELON_OPTIONS = [
  { id: 1, label: "Голубые фишки · 1-й эшелон", short: "1-й эшелон" },
  { id: 2, label: "2-й эшелон", short: "2-й эшелон" },
  { id: 3, label: "3-й эшелон", short: "3-й эшелон" },
  { id: "all", label: "Все компании", short: "Все" },
];
function filterByEchelon(companies, echelonFilter) {
  if (echelonFilter === "all") return companies;
  return companies.filter((c) => (c.echelon ?? 3) === echelonFilter);
}

// Ранжирование «кто пострадает/выиграет сильнее всего» — сигнальный слой ПЕРЕД
// голой таблицей чисел (конституция: «вердикт поверх данных», голая таблица без
// интерпретации не считается готовым экраном).
function rankByImpact(companies, metric = "net_profit") {
  return companies
    .filter((c) => c.metrics?.[metric]?.delta_bn != null)
    .sort((a, b) => Math.abs(b.metrics[metric].delta_bn) - Math.abs(a.metrics[metric].delta_bn));
}

// Владелец, 2026-07-24: «у Роснефти доросло до +200%, а дальше +15 и всё» —
// backend честно подавляет pct_of_base при |Δ| > 2×|база| (степень доверия к
// проценту падает при крошечной базе), но ПЛОСКИЕ ±15 вместо реального числа
// выглядели как обрезание/баг ровно в момент пересечения порога. Раз base_bn
// всегда приходит рядом (даже когда pct подавлен) — считаем честный % сами,
// не выдумываем плоскую константу. ±15 — только последний фолбэк, когда даже
// base_bn нет вовсе.
function tilePct(c) {
  const np = c.metrics.net_profit;
  if (np.pct_of_base != null) return np.pct_of_base;
  if (np.delta_bn == null) return 0; // нет сигнала для текущих факторов — нейтрально, не мнимые ±15
  if (np.base_bn) return (np.delta_bn / Math.abs(np.base_bn)) * 100;
  return np.delta_bn > 0 ? 15 : -15;
}

// Взвешенный агрегатный индекс — headline-число консоли (порт прототипа: та
// же грубая эвристика веса, что и у плиток карты — голубые фишки втрое
// тяжелее; настоящих весов по капитализации в контуре /numeric нет).
function computeHeadlineIndex(companies) {
  let sumW = 0, sumWV = 0;
  for (const c of companies) {
    if (c.metrics?.net_profit?.delta_bn == null) continue;
    const w = c.is_blue_chip ? 3 : 1;
    sumW += w; sumWV += w * tilePct(c);
  }
  return sumW > 0 ? sumWV / sumW : 0;
}

function ConsoleHeadline({ numeric }) {
  const ranked = rankByImpact(numeric.companies, "net_profit");
  // «Задето» — компании, которых сценарий РЕАЛЬНО коснулся (Δ≠0), не просто
  // те, у кого вообще есть число (после фикса «честный ноль» ranked включает
  // и незатронутые компании тоже — иначе счётчик вводил бы в заблуждение).
  const affected = ranked.filter((c) => c.metrics.net_profit.delta_bn !== 0).length;
  const worst = ranked.filter((c) => c.metrics.net_profit.delta_bn < 0)[0];
  const best = ranked.filter((c) => c.metrics.net_profit.delta_bn > 0)[0];
  const headline = computeHeadlineIndex(numeric.companies);
  return (
    <div className="st-headline">
      <div className="st-headline-num">
        <span className="st-hl-lbl">Индекс рынка <span className="bs-tag-estimate">модель</span></span>
        <span className="st-hl-val" style={{ color: headline >= 0 ? "var(--bs-up)" : "var(--bs-down)" }}>
          {headline >= 0 ? "+" : ""}{headline.toFixed(1)}%
        </span>
        {/* Владелец, 2026-07-24: «плюс/минус проценты — это что, цена акции?» —
            эти % НИКОГДА не про котировку, только про прогнозную чистую прибыль.
            Владелец, 2026-07-25: явно проговорить, что это МОДЕЛИРУЕТСЯ (не факт,
            не готовый прогноз), и объяснить методологию веса — «по весам индекса
            Мосбиржи, по капитализации, по чему?» — это НИ то, ни другое: грубая
            эвристика Basis (голубые фишки ×3), явно раскрыта здесь, не только
            мелким текстом внизу карты. */}
        <span className="st-hl-clarify">
          Смоделировано: изменение прогнозной чистой прибыли за год, НЕ цена акции.
          Вес в индексе — эвристика Basis (голубые фишки ×3, остальные ×1), НЕ вес
          индекса Мосбиржи и НЕ капитализация.
        </span>
      </div>
      <div className="st-headline-meta">
        <div className="st-hm">
          <span className="st-hm-l">Задето</span>
          <span className="st-hm-v">{affected} из {numeric.companies.length}</span>
        </div>
        <div className="st-hm">
          <span className="st-hm-l">Хуже всего</span>
          <span className="st-hm-v" style={{ color: "var(--bs-down)" }}>
            {worst ? `${worst.name} · ${tilePct(worst).toFixed(1)}%` : "—"}
          </span>
        </div>
        <div className="st-hm">
          <span className="st-hm-l">Лучше всего</span>
          <span className="st-hm-v" style={{ color: "var(--bs-up)" }}>
            {best ? `${best.name} · +${tilePct(best).toFixed(1)}%` : "—"}
          </span>
        </div>
      </div>
    </div>
  );
}

// Карта рынка — секторные строки, плитки flex-grow по весу внутри строки,
// цвет — плавный color-mix от нейтрального к --bs-up/--bs-down (канон
// Basis; НЕ --success/--danger — те дают другой оттенок и не совпадают с
// прототипом, ровно то, на что указал владелец).
// Насыщенность цвета: |pct| ≥ этого — уже максимум (85% в color-mix). Было 40 —
// в 2.2 раза мягче, чем в Клод-дизайне (18), из опасения «зальёт всё максимумом
// на реальных данных». Реальность обратная: у реального /numeric на типичном
// стресс-сценарии (не байдл-случай) медиана |pct| ~24%, т.е. с 40 плитки были
// хронически бледнее, чем в демо-макете (владелец, 2026-07-23: «цвет плиток
// другой») — половина насыщенности на тех же данных. 18 — точное значение
// макета, тоже единственное, что владелец просил «перекопировать» дословно.
const MAP_MAX_PCT = 18;
// Нейтральная база тайла — var(--st-deep-surface), НЕ светлый --bg-hover:
// владелец, 2026-07-24, указал точно на цвет фона секции «03/04 · Погружение
// второе» в docs/design_baza.html (--l3-bg/--l3-surface) как искомый тон —
// карта рынка теперь тёмная «deep»-зона (см. .st-main в stress-test.css),
// тайлы должны сидеть на ЕЁ фоне, не на светлом.
function mapColorFor(pct) {
  const m = Math.max(-MAP_MAX_PCT, Math.min(MAP_MAX_PCT, pct)) / MAP_MAX_PCT;
  const tone = m >= 0 ? "var(--bs-up)" : "var(--bs-down)";
  return `color-mix(in srgb, ${tone} ${Math.round(Math.abs(m) * 85)}%, var(--st-deep-surface))`;
}
function mapTextColorFor(pct) {
  const strength = Math.min(1, Math.abs(pct) / MAP_MAX_PCT);
  if (strength < 0.08) return "var(--st-deep-ink-2)"; // почти нейтральная плитка на тёмном фоне
  if (strength < 0.35) return pct >= 0 ? "var(--bs-up)" : "var(--bs-down)"; // бледная плитка — цветной текст читается
  return "#fff"; // сильно закрашенная плитка — текст того же тона на ней сливается, нужен контраст
}

// Владелец, 2026-07-24: «когда двигаешь ползунки — компании вылетают/появляются,
// это не норма, нужно чтобы были одни и те же». Раньше состав тайлов брался как
// top-30 ПО ТЕКУЩЕМУ impact (rankByImpact().slice(0,30)) — при движении одного
// слайдера компании без релевантного коэффициента теряли сигнал и выпадали.
// Теперь (см. companyImpact() — честный ноль вместо null/исключения) состав
// СТАБИЛЕН: показываем ВСЕХ из текущего эшелон-фильтра, сектора и порядок внутри
// сектора зафиксированы (не по impact) — меняется только цвет/число на тайле.
function MarketMap({ numeric, onOpenCompany }) {
  const companies = numeric.companies;
  if (!companies.length) return null;
  const bySector = new Map();
  for (const c of companies) {
    const sector = c.sector || "Другое";
    if (!bySector.has(sector)) bySector.set(sector, []);
    bySector.get(sector).push(c);
  }
  for (const arr of bySector.values()) {
    arr.sort((a, b) => (a.is_blue_chip !== b.is_blue_chip ? (a.is_blue_chip ? -1 : 1) : a.name.localeCompare(b.name, "ru")));
  }
  const sectorNames = [...bySector.keys()].sort((a, b) => a.localeCompare(b, "ru"));
  return (
    <div className="st-mapwrap">
      <div className="st-map">
        {sectorNames.map((sector) => (
          <React.Fragment key={sector}>
            <div className="st-sector-lbl">{sector}</div>
            <div className="st-map-row">
              {bySector.get(sector).map((c) => {
                const pct = tilePct(c);
                const weight = c.is_blue_chip ? 3 : 1;
                return (
                  <div
                    key={c.ticker}
                    role={onOpenCompany ? "button" : undefined}
                    tabIndex={onOpenCompany ? 0 : undefined}
                    className={`st-tile${weight <= 1 ? " st-tile-small" : ""}`}
                    style={{ flexGrow: weight, background: mapColorFor(pct), color: mapTextColorFor(pct) }}
                    title={`${c.name} (${c.ticker}) · ${pct >= 0 ? "+" : ""}${pct.toFixed(1)}%`}
                    onClick={() => onOpenCompany?.(c.ticker)}
                    onKeyDown={(e) => { if (onOpenCompany && (e.key === "Enter" || e.key === " ")) { e.preventDefault(); onOpenCompany(c.ticker); } }}
                  >
                    <span className="st-tile-nm-row">
                      <CompanyLogo ticker={c.ticker} name={c.name} size={weight <= 1 ? 14 : 16} className="st-tile-logo" />
                      <span className="st-tile-nm">{c.name}</span>
                    </span>
                    <span className="st-tile-pc">{pct >= 0 ? "▲" : "▼"} {Math.abs(pct).toFixed(1)}%</span>
                  </div>
                );
              })}
            </div>
          </React.Fragment>
        ))}
      </div>
      <div className="st-map-note">
        {companies.length} компаний в текущем фильтре · размер плитки — грубый вес (голубые фишки крупнее, реальной капитализации в контуре нет). Клик по плитке открывает карточку компании.
      </div>
    </div>
  );
}

function BoardRow({ c, maxAbs, onOpenCompany }) {
  const pct = tilePct(c);
  const width = Math.max(4, Math.round((Math.abs(pct) / maxAbs) * 100));
  return (
    <div className={`st-brow${onOpenCompany ? " st-brow-clickable" : ""}`}
      role={onOpenCompany ? "button" : undefined} tabIndex={onOpenCompany ? 0 : undefined}
      onClick={() => onOpenCompany?.(c.ticker)}
      onKeyDown={(e) => { if (onOpenCompany && (e.key === "Enter" || e.key === " ")) { e.preventDefault(); onOpenCompany(c.ticker); } }}>
      <span className="st-brow-nm-wrap">
        <CompanyLogo ticker={c.ticker} name={c.name} size={18} className="st-brow-logo" />
        <span className="st-brow-nm">{c.name}</span>
      </span>
      <div className="st-brow-bar"><i style={{ width: `${width}%` }} /></div>
      <span className="st-brow-pc">{pct >= 0 ? "+" : ""}{pct.toFixed(1)}%</span>
    </div>
  );
}

function Boards({ numeric, onOpenCompany }) {
  const ranked = rankByImpact(numeric.companies, "net_profit");
  const worst = ranked.filter((c) => c.metrics.net_profit.delta_bn < 0).slice(0, 6);
  const best = ranked.filter((c) => c.metrics.net_profit.delta_bn > 0).slice(0, 6);
  if (!worst.length && !best.length) return null;
  const maxAbs = Math.max(1, ...[...worst, ...best].map((c) => Math.abs(tilePct(c))));
  return (
    <div className="st-boards">
      <div className="st-board st-board-worse">
        <h3>▾ Под давлением</h3>
        {worst.length ? worst.map((c) => <BoardRow key={c.ticker} c={c} maxAbs={maxAbs} onOpenCompany={onOpenCompany} />) : <div className="st-board-empty">—</div>}
      </div>
      <div className="st-board st-board-better">
        <h3>▴ Выигрывают</h3>
        {best.length ? best.map((c) => <BoardRow key={c.ticker} c={c} maxAbs={maxAbs} onOpenCompany={onOpenCompany} />) : <div className="st-board-empty">—</div>}
      </div>
    </div>
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

const STRENGTH = { 1: "слабо", 2: "заметно", 3: "сильно" };

// Сила эффекта — визуальный код (точки), не только слово мелким шрифтом
// (design-critic, 2026-07-25, пункт 5). aria-label/title держат словесную
// формулировку для читалок экрана и hover.
function Intensity({ n, tone }) {
  return (
    <span className="st-intensity" role="img" aria-label={STRENGTH[n] || ""} title={STRENGTH[n] || ""}>
      {[1, 2, 3].map((i) => (
        <i key={i} className={`st-int-dot${i <= n ? ` st-int-on-${tone}` : ""}`} />
      ))}
    </span>
  );
}

// Заголовок-досье — вердикт ПОВЕРХ доказательств (конституция: «4 слоя
// чтения», голая таблица/список без интерпретации не считается готовым
// экраном). Стоит НАД таблицей/компасом, не после.
function DossierHead({ eyebrow, title, lede, tag }) {
  return (
    <div className="st-dossier-head">
      <span className="st-dossier-eyebrow">{eyebrow}</span>
      <h3 className="st-dossier-title">{title}</h3>
      {tag}
      {lede && <p className="st-dossier-lede">{lede}</p>}
    </div>
  );
}

function ShieldSide({ title, tone, sectors, companies }) {
  const [showAll, setShowAll] = useState(false);
  const total = sectors.length + companies.length;
  const capped = !showAll && total > 5;
  const sList = capped ? sectors.slice(0, Math.max(0, 5 - companies.length)) : sectors;
  const cList = capped ? companies.slice(0, Math.max(0, 5 - sList.length)) : companies;
  return (
    <div className={`st-shield-col st-shield-${tone}`}>
      <h3>{title}</h3>
      {sList.map((s, i) => (
        <div key={`s${i}`} className="st-shield-card">
          <div className="st-shield-row">
            <span className="st-shield-sector">{s.sector}</span>
            <Intensity n={s.strength} tone={tone} />
          </div>
          <p>{s.why}</p>
        </div>
      ))}
      {cList.map((c, i) => (
        <div key={`c${i}`} className="st-shield-card st-shield-card-co">
          <span className="st-shield-ticker">{c.ticker}</span>
          <p>{c.why}</p>
        </div>
      ))}
      {!sectors.length && !companies.length && <p className="st-shield-empty">Явных факторов не выделено.</p>}
      {total > 5 && (
        <button type="button" className="st-more-btn" onClick={() => setShowAll(!showAll)}>
          {showAll ? "Свернуть ▴" : `Показать все ${total} ▾`}
        </button>
      )}
    </div>
  );
}

function ExpertDossier({ e }) {
  return (
    <div className="bs-card st-dossier-card">
      <div className="st-dossier-card-head">
        <h3>Механика сценария</h3>
        <span className="bs-tag-judgment">суждение</span>
      </div>
      <p className="st-dossier-summary">{e.summary}</p>
      {e.channels?.length > 0 && (
        <ol className="st-channels">
          {e.channels.map((ch, i) => (
            <li key={i}><span className="st-channel-n">{i + 1}</span>{ch}</li>
          ))}
        </ol>
      )}
      <div className="st-shield-grid">
        <ShieldSide title="Потенциальные бенефициары" tone="up" sectors={e.sector_winners || []} companies={e.company_winners || []} />
        <ShieldSide title="Потенциально под давлением" tone="down" sectors={e.sector_losers || []} companies={e.company_losers || []} />
      </div>
      {e.caveats?.length > 0 && (
        <div className="bs-callout" style={{ marginTop: 18 }}>
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" aria-hidden="true"><path d="M13 2 3 14h7l-1 8 10-12h-7l1-8Z" /></svg>
          <p><b>Оговорки.</b> {e.caveats.join(" · ")}</p>
        </div>
      )}
      {e.kb_note && <p className="st-dossier-note">{e.kb_note}</p>}
    </div>
  );
}

function FinDelta({ m }) {
  if (!m || m.delta_bn == null) return <span className="st-fd-empty">—</span>;
  const up = m.delta_bn > 0, flat = m.delta_bn === 0;
  const color = flat ? "var(--bs-ink-3)" : up ? "var(--bs-up)" : "var(--bs-down)";
  const glyph = flat ? "•" : up ? "▲" : "▼";
  return (
    <span className="st-fd" style={{ color }}>
      <span aria-hidden="true">{glyph}</span>
      {Math.abs(m.delta_bn).toFixed(1)} млрд ₽
      {m.pct_of_base != null && <span className="st-fd-pct"> ({m.pct_of_base > 0 ? "+" : ""}{m.pct_of_base}%)</span>}
    </span>
  );
}

function FinancialTable({ numeric, onOpenCompany }) {
  const [showAll, setShowAll] = useState(false);
  const deduped = dedupeByIssuer(numeric.companies);
  const list = showAll ? deduped : deduped.slice(0, 8);
  return (
    <div className="bs-card st-dossier-card">
      <div className="st-dossier-card-head">
        <h3>Эффект на финансовые показатели</h3>
        <span className="bs-tag-estimate">оценка</span>
      </div>
      <p className="st-dossier-summary" style={{ marginBottom: 14 }}>За год, к базе последнего отчётного года.</p>
      <div className="st-ftable-wrap">
        <table className="st-ftable">
          <thead>
            <tr>
              <th className="st-fth-l">Компания</th>
              <th>Δ Выручка</th><th>Δ EBITDA</th><th>Δ Чистая прибыль</th>
            </tr>
          </thead>
          <tbody>
            {list.map((c) => (
              <tr key={c.ticker} className={onOpenCompany ? "st-fr-clickable" : ""} onClick={() => onOpenCompany?.(c.ticker)}>
                <td className="st-fth-l">
                  <span className="st-fco">
                    <CompanyLogo ticker={c.ticker} name={c.name} size={22} />
                    <span className="st-fco-txt">
                      <span className="st-fco-name">
                        {c.is_blue_chip && <span className="st-fco-bf">ГФ</span>}
                        {c.name}
                      </span>
                      <span className="st-fco-meta">
                        {c.ticker}{c._also?.length > 0 && ` = ${c._also.join(", ")}`} · {c.sector}
                      </span>
                    </span>
                  </span>
                </td>
                <td><FinDelta m={c.metrics.revenue} /></td>
                <td><FinDelta m={c.metrics.ebitda} /></td>
                <td><FinDelta m={c.metrics.net_profit} /></td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      {deduped.length > 8 && (
        <button type="button" className="st-more-btn" onClick={() => setShowAll(!showAll)}>
          {showAll ? "Свернуть ▴" : `Показать все ${deduped.length} компаний ▾`}
        </button>
      )}
      <p className="st-dossier-note">{numeric.semantics}</p>
    </div>
  );
}

const BUCKET_ORDER = ["▲▲", "▲", "─", "▼", "▼▼"];

function DirectionCompass({ qual, onOpenCompany }) {
  const [showAll, setShowAll] = useState(false);
  const rows = [...(qual.winners || []), ...(qual.losers || [])];
  const groups = new Map(BUCKET_ORDER.map((l) => [l, []]));
  for (const r of rows) groups.get(bucketOf(r.reaction_pct).label).push(r);
  return (
    <div className="bs-card st-dossier-card">
      <div className="st-dossier-card-head">
        <h3>Компас сценария</h3>
        <span className="bs-tag-judgment">суждение</span>
      </div>
      <p className="st-dossier-summary" style={{ marginBottom: 16 }}>
        Только направление — величину этих эффектов мы числом не оцениваем (в отличие от финансовой
        таблицы выше). Сигнал: {qual.companies_with_signal} из {qual.total_companies} компаний.
      </p>
      <div className="st-compass">
        {BUCKET_ORDER.map((label) => {
          const items = groups.get(label);
          if (!items.length) return null;
          const b = BUCKETS.find((x) => x.label === label);
          const list = showAll ? items : items.slice(0, 10);
          return (
            <div key={label} className="st-compass-row">
              <div className="st-compass-lbl">
                <span className={`bs-wind-tag ${b.cls}`}>{label}</span>
                <span className="st-compass-title">{b.title}</span>
                <span className="st-compass-count">{items.length}</span>
              </div>
              <div className="st-compass-chips">
                {list.map((r) => (
                  <button key={r.ticker} type="button" className="st-compass-chip"
                    onClick={() => onOpenCompany?.(r.ticker)} title={r.name}>
                    <span className="st-cc-ticker">{r.ticker}</span>{r.name}
                  </button>
                ))}
                {!showAll && items.length > 10 && <span className="st-compass-more-hint">+{items.length - 10}</span>}
              </div>
            </div>
          );
        })}
      </div>
      {rows.length > 30 && (
        <button type="button" className="st-more-btn" onClick={() => setShowAll(!showAll)}>
          {showAll ? "Свернуть ▴" : "Показать все компании ▾"}
        </button>
      )}
    </div>
  );
}

// Дефолты на случай, если /current-levels временно недоступен (честная
// деградация — приблизительные ориентиры, не боевые данные, помечено ниже).
const FALLBACK_LEVELS = { key_rate_pct: 20, fx_usdrub: 80, oil_brent_usd: 70 };
const SLIDER_RANGE = {
  key_rate_pct: { min: 5, max: 30, step: 0.5, label: "Ключевая ставка", unit: "%", fmtBase: (v) => `сейчас ≈ ${v.toFixed(1).replace(/\.0$/, "")}%` },
  fx_usdrub: { min: 50, max: 150, step: 1, label: "Курс ₽/$", unit: "₽", fmtBase: (v) => `сейчас ≈ ${Math.round(v)} ₽/$` },
  oil_brent_usd: { min: 20, max: 120, step: 1, label: "Нефть Brent", unit: "$", fmtBase: (v) => `сейчас ≈ $${Math.round(v)}/барр.` },
};

// «Спросите ещё» (блок в конце досье) — эскалация ТЕКУЩЕГО значения слайдера
// на шаг дальше в ТУ ЖЕ сторону, куда он уже сдвинут от базы; если ещё не
// сдвинут (|diff| меньше 20% шага) — по умолчанию идём вверх. Клэмп в диапазон
// слайдера, чтобы кнопка никогда не предлагала невалидное значение.
function clamp(v, min, max) { return Math.min(max, Math.max(min, v)); }
function escalate(field, base, current, step) {
  const cfg = SLIDER_RANGE[field];
  let next;
  if (base == null || current == null) next = current + step;
  else {
    const diff = current - base;
    next = Math.abs(diff) < step * 0.2 ? current + step : current + Math.sign(diff) * step;
  }
  next = clamp(next, cfg.min, cfg.max);
  return field === "key_rate_pct" ? round1(next) : Math.round(next);
}

// Пресеты — качественная факторная модель backend'а (stress_scenarios.py),
// без эмодзи в данных; глиф — чисто визуальный, подобран по смыслу сценария
// (порт прототипа, где у каждого пресета был свой значок).
const PRESET_GLYPHS = {
  war_prolonged: "⏳",
  oil_crash: "📉",
  middle_east_spike: "🛢",
  fiscal_pressure: "🏛",
  sticky_inflation: "🌡",
  cbr_optimistic: "☀",
};

function Slider({ field, value, onChange, pulsing, base }) {
  const cfg = SLIDER_RANGE[field];
  const fmt = (v) => (cfg.unit === "%" ? v.toFixed(1).replace(/\.0$/, "") : Math.round(v));
  return (
    <div className={`st-sl${pulsing ? " st-sl-pulse" : ""}`}>
      <div className="st-sl-label">
        <span className="st-sl-name">{cfg.label}</span>
        <span className="st-sl-val">
          {fmt(value)}
          <span className="st-sl-unit">{cfg.unit}</span>
        </span>
      </div>
      <input type="range" min={cfg.min} max={cfg.max} step={cfg.step} value={value}
        onChange={(e) => onChange(field, parseFloat(e.target.value))} />
      {base != null && <div className="st-sl-base">{cfg.fmtBase(base)}</div>}
    </div>
  );
}

// «Спросите ещё» — конец досье, не косметика: три чипа-продолжения, вычисленные
// из РЕАЛЬНЫХ текущих значений слайдеров (не изобретённые текстом сценарии),
// клик двигает соответствующий слайдер и скроллит обратно к консоли — сценарии
// естественно нанизываются один на другой (design-critic, 2026-07-25).
const NEXT_LEDE = {
  idle: "Сценарии складываются один из другого — попробуйте пойти дальше по той же логике.",
  expert: "Хотите увидеть, что будет, если пойти ещё дальше в ту же сторону?",
  qualitative: "Эти факторы работают до определённого предела — сдвиньте рычаги сильнее и посмотрите на цифры.",
  preset: "У этого сценария нет числового аналога — но вот те же рычаги в количественной модели.",
};

function NextQuestionStrip({ levels, baseLevels, onEscalate, context = "idle" }) {
  if (!levels) return null;
  const rateNext = escalate("key_rate_pct", baseLevels?.key_rate_pct, levels.key_rate_pct, 5);
  const oilNext = escalate("oil_brent_usd", baseLevels?.oil_brent_usd, levels.oil_brent_usd, 15);
  const fxNext = escalate("fx_usdrub", baseLevels?.fx_usdrub, levels.fx_usdrub, 15);
  const rateDir = rateNext >= levels.key_rate_pct ? "выше" : "ниже";
  const oilDir = oilNext >= levels.oil_brent_usd ? "выше" : "ниже";
  const fxDir = fxNext >= levels.fx_usdrub ? "слабее" : "крепче";
  return (
    <div className="st-next">
      <div>
        <span className="st-next-eyebrow">Спросите ещё</span>
        <p className="st-next-lede">{NEXT_LEDE[context]}</p>
      </div>
      <div className="st-next-chips">
        <button type="button" className="st-next-chip" onClick={() => onEscalate("key_rate_pct", rateNext)}>
          Ставка ещё {rateDir} → <span>{rateNext}%</span>
        </button>
        <button type="button" className="st-next-chip" onClick={() => onEscalate("oil_brent_usd", oilNext)}>
          Нефть ещё {oilDir} → <span>${oilNext}</span>
        </button>
        <button type="button" className="st-next-chip" onClick={() => onEscalate("fx_usdrub", fxNext)}>
          Рубль {fxDir} → <span>{fxNext} ₽/$</span>
        </button>
        <button type="button" className="st-next-chip st-next-chip-ghost" onClick={() => onEscalate(null)}>
          Или опишите свой сценарий ↑
        </button>
      </div>
    </div>
  );
}

export default function StressTestView({ onOpenCompany }) {
  const apiUrl = process.env.REACT_APP_API_URL || "http://localhost:8000";

  // Слайдеры — null, пока не подтянули реальные текущие уровни (не рисуем
  // произвольные числа как «сейчас», пока не знаем, что это правда).
  // baseLevels — снимок ИСХОДНОГО значения при загрузке (для подписи «сейчас
  // ≈ X» под слайдером и для честного «К текущим уровням»): levels меняется
  // по мере того как пользователь двигает ползунки, baseLevels — нет.
  const [levels, setLevels] = useState(null);
  const [baseLevels, setBaseLevels] = useState(null);
  const [levelsIsFallback, setLevelsIsFallback] = useState(false);
  const [pulsingFields, setPulsingFields] = useState(new Set());
  const skipRecomputeRef = useRef(false);

  // Досье → консоль: рефы для моста «Спросите ещё» (NextQuestionStrip ниже
  // консоли) — клик по чипу-продолжению двигает слайдер И скроллит обратно к
  // консоли, чтобы пользователь увидел новую карту, не просто число в кнопке.
  const consoleRef = useRef(null);
  const askInputRef = useRef(null);

  // Сырые коэффициенты чувствительности по всей вселенной — грузятся ОДИН раз,
  // дальше слайдеры считают локально (см. companyImpact/computeAllImpacts
  // выше) — без debounce и без round-trip на сервер на каждое движение.
  const [coefficients, setCoefficients] = useState(null);
  const [numResult, setNumResult] = useState(null);

  // Эшелоны — дефолт «1-й эшелон» (голубые фишки, самый узнаваемый и чистый
  // вход на карту) по рекомендации product-analyst-biz, 2026-07-24.
  const [echelonFilter, setEchelonFilter] = useState(1);

  // Сворачивание рельса (пресеты+слайдеры) — владелец, 2026-07-25: чтобы карта
  // могла занять всю ширину консоли.
  const [railCollapsed, setRailCollapsed] = useState(false);

  const [question, setQuestion] = useState("");
  const [askResult, setAskResult] = useState(null);
  const [askLoading, setAskLoading] = useState(false);

  const [presets, setPresets] = useState([]);
  const [presetResult, setPresetResult] = useState(null);
  const [presetKey, setPresetKey] = useState(null);

  // Реальные текущие ориентиры — стартовая позиция слайдеров. Сохранение в
  // levels само запускает первый /numeric-пересчёт (эффект ниже) — карта и
  // индекс должны появиться сразу при открытии экрана, как в демо, а не
  // только после того как пользователь тронет ползунок.
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
        setLevels(merged);
        setBaseLevels(merged);
      })
      .catch(() => { setLevels(FALLBACK_LEVELS); setBaseLevels(FALLBACK_LEVELS); setLevelsIsFallback(true); });

    fetch(`${apiUrl}/api/stress-test/scenarios`)
      .then((r) => (r.ok ? r.json() : { scenarios: [] }))
      .then((d) => setPresets(d.scenarios || []))
      .catch(() => {});

    fetch(`${apiUrl}/api/stress-test/coefficients`)
      .then((r) => (r.ok ? r.json() : { companies: [] }))
      .then((d) => setCoefficients(d.companies || []))
      .catch(() => setCoefficients([]));
  }, [apiUrl]);

  // Живой пересчёт на слайдерах — МГНОВЕННО локально в JS (владелец, 2026-07-24:
  // «в демо пересчитывается мгновенно, у нас задержка» — было 350ms debounce +
  // round-trip на /numeric на КАЖДОЕ движение ползунка). baseLevels.oil_brent_usd —
  // тот же застывший «спот»-ориентир, что показывает подпись «сейчас ≈ $X» под
  // слайдером нефти (см. компонент Slider) — не едет при движении ползунка,
  // иначе «Δ от спота» потеряло бы смысл.
  useEffect(() => {
    if (!levels || !coefficients) return;
    if (skipRecomputeRef.current) { skipRecomputeRef.current = false; return; }
    setAskResult(null); setPresetResult(null);
    setNumResult(computeAllImpacts(coefficients, levels.key_rate_pct, levels.fx_usdrub,
      levels.oil_brent_usd, baseLevels?.oil_brent_usd));
  }, [coefficients, levels?.key_rate_pct, levels?.fx_usdrub, levels?.oil_brent_usd, baseLevels?.oil_brent_usd]);

  const setField = (field, value) => setLevels((prev) => ({ ...prev, [field]: value }));

  const resetLevels = () => {
    if (!baseLevels) return;
    setLevels({ ...baseLevels });
  };

  // Клик по чипу «Спросите ещё» (или по ghost-чипу «опишите сами», field=null) —
  // двигает слайдер на эскалированное значение и всегда скроллит назад к
  // консоли, чтобы результат (индекс/карта) был виден сразу, не за скроллом.
  // scrollIntoView({behavior:"smooth"}) безопасен под prefers-reduced-motion —
  // глобальный гард в tokens.css форсит scroll-behavior:auto !important.
  const handleEscalate = (field, value) => {
    if (!field) {
      consoleRef.current?.scrollIntoView({ behavior: "smooth", block: "start" });
      setTimeout(() => askInputRef.current?.focus(), 400);
      return;
    }
    setField(field, value);
    setPulsingFields(new Set([field]));
    setTimeout(() => setPulsingFields(new Set()), 900);
    consoleRef.current?.scrollIntoView({ behavior: "smooth", block: "start" });
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

  // Эшелон-фильтр применяется к тому, что реально рендерят карта/лидерборд/
  // таблица (echelon приходит и от клиентского расчёта, и от серверного —
  // numeric_impact() на бэке размечает его тем же _echelon_map()).
  const displayNumeric = numResult && !numResult.error
    ? { ...numResult, companies: filterByEchelon(numResult.companies, echelonFilter) }
    : numResult;

  // Счётчики по эшелону — для подписи на переключателе (сколько компаний в
  // каждом срезе), как badge-счётчик у UniversePicker в Скринере.
  const echelonCounts = { 1: 0, 2: 0, 3: 0 };
  if (numResult && !numResult.error) {
    for (const c of numResult.companies) echelonCounts[c.echelon ?? 3] += 1;
  }

  // Мета-строка под заголовком — какие уровни считаются «базовыми» для этого
  // прогона (владелец, 2026-07-24: шапка «бедновата» — не хватало опоры на
  // реальные цифры рядом с заголовком). Дата — просто сегодняшняя (день.месяц),
  // НЕ выдаём её за таймстамп котировки: /current-levels такого таймстампа не
  // отдаёт, честно берём то, что реально знаем — момент просмотра.
  const metaParts = [];
  if (baseLevels) {
    if (baseLevels.key_rate_pct != null) metaParts.push(`ставка ${Number(baseLevels.key_rate_pct).toFixed(1).replace(/\.0$/, "")}%`);
    if (baseLevels.fx_usdrub != null) metaParts.push(`$/₽ ${Math.round(baseLevels.fx_usdrub)}`);
    if (baseLevels.oil_brent_usd != null) metaParts.push(`Brent $${Math.round(baseLevels.oil_brent_usd)}`);
  }
  const todayLabel = new Date().toLocaleDateString("ru-RU", { day: "2-digit", month: "2-digit" });

  return (
    <div className="stress-test-view tw-flex tw-flex-col tw-gap-5">
      {/* Баннер-предупреждение — свёрнут в одну строку (был блок на треть экрана,
          владелец: «баннер бедноват… точнее, слишком тяжёлый»). Полный текст
          методики никуда не делся — он за раскрывающимся <details>, доступен в
          один клик/Enter (нативный элемент — работает с клавиатуры и читалками
          экрана без доп. JS, тот же принцип, что у design/textblocks.jsx Disclosure). */}
      <details className="st-disclaimer">
        <summary className="st-disclaimer-summary">
          <FlaskConical size={14} className="st-disclaimer-icon" aria-hidden="true" />
          <span className="st-disclaimer-lead">
            <b>Демо-версия</b> — линейные коэффициенты чувствительности, не прогноз и не инвестрекомендация.
          </span>
          <span className="st-disclaimer-toggle">методика <span className="st-disclaimer-chevron" aria-hidden="true">▾</span></span>
        </summary>
        <div className="st-disclaimer-body">
          Числа считаются по линейным коэффициентам чувствительности из макро-разборов карточек (реальность
          нелинейна: демпферы, прогрессивные налоги, хеджи). Интерпретация свободного сценария — ИИ, может
          понять вас неточно (мы показываем «как мы поняли» — проверяйте). Точечные события одной компании
          (адресный налог, смена собственника) модель не считает.
          {" "}<b>Даже без движения ползунков некоторые компании могут показывать не ноль:</b> у каждой свой
          «спот» (курс/ставка/цена сырья) на МОМЕНТ её макро-разбора — если с тех пор курс или ставка реально
          изменились, «текущие уровни» на слайдере уже отличаются от спота компании, и модель честно показывает
          эту накопившуюся разницу, а не «эффект сценария». Разбор карточки может быть свежее или старше, чем у
          соседней — единой даты обновления по всем компаниям пока нет.
        </div>
      </details>

      {/* Шапка секции — канонический паттерн pf-sec-head/eyebrow/title (portfolio-v2.css),
          тот же, что у соседних разделов Портфеля, а не голые tw-классы «по мотивам»
          (владелец: шапка была другого шрифта/размера). Eyebrow отделяет этот инструмент
          (весь рынок, гипотетическая симуляция) от узкого внутрипортфельного стресс-теста
          в разделе «Портфель» (тот считает конкретно позиции пользователя). Тег «демо» у
          заголовка — тот же честный сигнал, что раньше нёс только громоздкий баннер выше,
          теперь виден на уровне идентичности экрана. */}
      <div>
        <div className="pf-sec-head">
          <span className="pf-sec-eyebrow">Симуляция · весь рынок</span>
          <h2 className="pf-sec-title">Стресс-тестирование</h2>
          <span className="bs-tag-estimate">демо</span>
        </div>
        {metaParts.length > 0 && (
          <div className="st-head-meta">
            Базовые уровни: {metaParts.join(" · ")} · на {todayLabel}{levelsIsFallback ? " (ориентир)" : ""}
          </div>
        )}
        <p className="st-head-lead">
          Что будет с российскими компаниями, если сдвинуть ставку, курс или нефть — и кто пострадает, а кто выиграет.
        </p>
        <p className="st-head-sub">
          Подвигайте ползунки — индекс, карта и таблица пересчитываются на лету, без ожидания. Или опишите
          сценарий своими словами: если он называет конкретные уровни, ползунки встанут в них сами.
        </p>
      </div>

      <div className="st-console" ref={consoleRef}>
        <div className="st-ask">
          <div className="st-ask-row">
            <input
              type="text" value={question}
              onChange={(e) => setQuestion(e.target.value)}
              onKeyDown={(e) => { if (e.key === "Enter") ask(); }}
              placeholder="Опишите сценарий своими словами — «нефть падает до $45 и держится там»"
              ref={askInputRef}
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
        </div>

        <div className={`st-console-top${railCollapsed ? " st-rail-collapsed" : ""}`}>
          <button type="button" className="st-rail-expand-tab" onClick={() => setRailCollapsed(false)} title="Показать пресеты и слайдеры" aria-label="Показать панель">
            <PanelLeftOpen size={13} />
          </button>
          <div className="st-rail">
            <button type="button" className="st-rail-collapse-btn" onClick={() => setRailCollapsed(true)} title="Скрыть панель — карта займёт всю ширину" aria-label="Скрыть панель">
              <PanelLeftClose size={13} />
            </button>
            {presets.length > 0 && (
              <div className="st-presets-compact">
                {presets.map((p) => (
                  <button key={p.key} type="button" onClick={() => runPreset(p.key)}
                    disabled={presetKey === p.key} className="st-preset-compact" title={p.description}>
                    <span className="st-preset-g">{PRESET_GLYPHS[p.key] || "◆"}</span>
                    {p.label}
                  </button>
                ))}
              </div>
            )}

            <div className="st-rail-label">
              <span>Или задайте уровни точно</span>
            </div>

            {!levels ? (
              <div className="st-sliders-loading">Загружаем текущие уровни ставки/курса/нефти…</div>
            ) : (
              <div className="st-slider-group">
                <Slider field="key_rate_pct" value={levels.key_rate_pct} onChange={setField}
                  pulsing={pulsingFields.has("key_rate_pct")} base={baseLevels?.key_rate_pct} />
                <Slider field="fx_usdrub" value={levels.fx_usdrub} onChange={setField}
                  pulsing={pulsingFields.has("fx_usdrub")} base={baseLevels?.fx_usdrub} />
                <Slider field="oil_brent_usd" value={levels.oil_brent_usd} onChange={setField}
                  pulsing={pulsingFields.has("oil_brent_usd")} base={baseLevels?.oil_brent_usd} />
              </div>
            )}

            {levels && (
              <div className="st-reset-row">
                <button type="button" className="st-reset" onClick={resetLevels}>
                  <RotateCcw size={12} /> К текущим уровням
                </button>
                {levelsIsFallback && (
                  <div className="st-levels-note">Текущие уровни временно недоступны — старт от приблизительных ориентиров, не боевые данные.</div>
                )}
              </div>
            )}
          </div>

          <div className="st-main">
            {presetKey ? (
              <div className="st-main-loading">Считаем сценарий…</div>
            ) : presetResult && !presetResult.error ? (
              // Владелец, 2026-07-24: «кнопки сценариев когда нажимаешь ничего не
              // происходит» — пресет реально считался (winners/losers), но
              // headline/карта (числовой контур) вообще не реагируют — у пресетов
              // нет числового эквивалента (см. шапку файла), а результат
              // (DirectionCompass) рендерится далеко внизу страницы. Явно показываем
              // здесь, ГДЕ смотрит пользователь, что клик подействовал — БЕЗ полного
              // описания (оно, плюс заголовок, уже даёт DossierHead в досье ниже,
              // v5 2026-07-25 — было дословное дублирование текста дважды подряд).
              <div className="st-preset-active">
                <div className="st-preset-active-lbl">Показан сценарий «{presetResult.scenario?.label}»</div>
                <div className="st-preset-active-hint">
                  У этого сценария нет точных числовых уровней ставки/курса/нефти — количественная карта
                  здесь недоступна. Направление эффекта по компаниям — в досье ниже ↓
                </div>
              </div>
            ) : numResult && !numResult.error ? (
              <>
                <div className="st-echelon-row">
                  <span className="st-echelon-lbl">Компании</span>
                  <div className="bs-seg-toggle">
                    {ECHELON_OPTIONS.map((opt) => (
                      <span key={opt.id} className={`bs-seg-opt${echelonFilter === opt.id ? " bs-on" : ""}`} role="button" tabIndex={0}
                        onClick={() => setEchelonFilter(opt.id)}
                        onKeyDown={(e) => { if (e.key === "Enter" || e.key === " ") { e.preventDefault(); setEchelonFilter(opt.id); } }}>
                        {opt.short}{opt.id !== "all" && <span className="st-seg-count">{echelonCounts[opt.id]}</span>}
                      </span>
                    ))}
                  </div>
                </div>
                {echelonFilter !== 1 && (
                  <div className="st-echelon-note">
                    {echelonFilter === "all"
                      ? "Показаны все компании, включая 2-й/3-й эшелон — у мелких и средних бумаг реакция обычно резче, а данных по ним меньше."
                      : "Средние и малые компании — реакция обычно резче, чем у голубых фишек, и данных по ним меньше."}
                  </div>
                )}
                <ConsoleHeadline numeric={displayNumeric} />
                <MarketMap numeric={displayNumeric} onOpenCompany={onOpenCompany} />
              </>
            ) : (
              <div className="st-main-loading">
                {askLoading ? "Считаем сценарий…" : "Считаем базовый сценарий…"}
              </div>
            )}
          </div>
        </div>

        {numResult && !numResult.error && !presetResult && <Boards numeric={displayNumeric} onOpenCompany={onOpenCompany} />}
      </div>

      {/* ============================================================
          «Досье» — всё после консоли. Светлая бумага (--bs-surface/--bs-card),
          НЕ продолжение тёмной консоли (см. комментарий v5 в шапке файла).
          Одна глава: вердикт → доказательства → компас → «спросите ещё».
          ============================================================ */}
      <div className="st-dossier">
        {/* Базовое состояние (ни ask, ни пресет не запущены) — просто текущий
            слайдерный расчёт, свежий всегда (numResult синхронен со слайдерами). */}
        {!askResult && !presetResult && numResult && !numResult.error && (
          <>
            <FinancialTable numeric={displayNumeric} onOpenCompany={onOpenCompany} />
            <NextQuestionStrip levels={levels} baseLevels={baseLevels} onEscalate={handleEscalate} context="idle" />
          </>
        )}

        {/* Ответ на свободный вопрос — эксперт/качественный компас/числа могут
            приходить в любой комбинации (backend пробует все три независимо,
            см. stress_ask.py). Показываем финтаблицу ТОЛЬКО когда ЭТОТ ask
            реально принёс свежие числа (askResult.numeric) — иначе рискуем
            выдать устаревшую таблицу от предыдущего расчёта под чужим вердиктом. */}
        {askResult && !askResult.no_signal && !askResult.error &&
          (askResult.expert || askResult.qualitative || (askResult.numeric && !askResult.numeric.error)) && (
          <>
            <DossierHead
              eyebrow="Разбор сценария"
              title={askResult.expert ? "Победители и проигравшие сценария"
                : askResult.qualitative ? "Направление эффекта по компаниям"
                : "Эффект на финансовые показатели"}
              lede={askResult.understood}
              tag={askResult.expert || askResult.qualitative
                ? <span className="bs-tag-judgment">суждение</span>
                : <span className="bs-tag-estimate">оценка</span>}
            />
            {askResult.numeric && !askResult.numeric.error && (
              <FinancialTable numeric={displayNumeric} onOpenCompany={onOpenCompany} />
            )}
            {askResult.expert && <ExpertDossier e={askResult.expert} />}
            {askResult.qualitative && <DirectionCompass qual={askResult.qualitative} onOpenCompany={onOpenCompany} />}
            <NextQuestionStrip levels={levels} baseLevels={baseLevels} onEscalate={handleEscalate}
              context={askResult.expert ? "expert" : askResult.qualitative ? "qualitative" : "idle"} />
          </>
        )}
        {askResult?.no_signal && (
          <div className="bs-card st-dossier-card"><p className="st-dossier-summary">{askResult.note}</p></div>
        )}
        {askResult?.error === "network" && (
          <div className="bs-card st-dossier-card">
            <p className="st-dossier-summary" style={{ color: "var(--bs-down)" }}>Не удалось получить ответ — попробуйте ещё раз.</p>
          </div>
        )}

        {/* Пресет — качественная факторная модель, нет числового контура (см.
            шапку файла) — компас, без финтаблицы. */}
        {presetResult && !presetResult.error && (
          <>
            <DossierHead eyebrow="Пресет" title={presetResult.scenario?.label}
              lede={presetResult.scenario?.description} tag={<span className="bs-tag-fact">пресет</span>} />
            <DirectionCompass qual={presetResult} onOpenCompany={onOpenCompany} />
            <NextQuestionStrip levels={levels} baseLevels={baseLevels} onEscalate={handleEscalate} context="preset" />
          </>
        )}
        {presetResult?.error && (
          <div className="bs-card st-dossier-card">
            <p className="st-dossier-summary" style={{ color: "var(--bs-down)" }}>Не удалось посчитать сценарий — попробуйте ещё раз.</p>
          </div>
        )}
      </div>
    </div>
  );
}

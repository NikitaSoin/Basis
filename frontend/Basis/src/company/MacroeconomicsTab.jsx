/* Вкладка «Макроэкономика» нового образца (пилот 09.2026).
   Источник данных: GET /api/companies/by-ticker/{ticker}/macro-tab — файл
   backend/companies/<T>/macro_tab.json (агент-писатель) + поле calc,
   которое ручка подмешивает из macro_scenarios.json (см. companies.py,
   get_macro_tab). Контракт полей — docs/macro_model_contract_v1.md, раздел 7.
   Состав, порядок и формулировки шести блоков — docs/Описание_вкладки_
   макроэкономика.md, Части 0–7 (владелец, версия 1). Рендерит ТОЛЬКО то,
   что реально пришло — компонент не считает арифметику и не досочиняет
   текст (методика 0.5): каждое число берётся из JSON как есть, каждый блок
   без обязательных полей просто не рисуется.

   Поля с суффиксом needs_rewrite/needs_rewrite_fields — служебная пометка
   для параллельного процесса переписывания прозы, к отображению отношения
   не имеет и здесь нигде не читается.

   Подключение — CompanyCardView.jsx: renderMacro() отдаёт этот компонент
   первым, если пришли данные нового формата (macroTab), иначе — прежний
   разбор (macroMd/macroJson) для компаний вне пилота. */
import React from "react";
import {
  ArrowRight, TrendingUp, TrendingDown, AlertTriangle, Info, Target, Activity, RefreshCw, Zap,
} from "lucide-react";
import "../styles/macroeconomics-tab.css";

// --------------------------------------------------------------------------
// helpers — форматирование и защитные обёртки (устойчивость к «дырам» в JSON)
// --------------------------------------------------------------------------
const isNum = (v) => typeof v === "number" && Number.isFinite(v);
const arr = (v) => (Array.isArray(v) ? v : []);
const txt = (v) => (typeof v === "string" && v.trim() ? v.trim() : null);
const obj = (v) => (v && typeof v === "object" && !Array.isArray(v) ? v : null);

// Денежные величины вкладки — всегда млрд руб. (docs/macro_model_contract_v1.md, п.1);
// в исходных данных числа уже приходят с одним знаком после запятой — сохраняем эту точность,
// без автопереключения млрд↔трлн (единица здесь фиксирована контрактом, не выводится из величины).
function fmtN(v, d = 1) {
  if (!isNum(v)) return "—";
  const s = Math.abs(v).toLocaleString("ru-RU", { minimumFractionDigits: d, maximumFractionDigits: d });
  return v < 0 ? `−${s}` : s;
}
function fmtSigned(v, d = 1) {
  if (!isNum(v)) return "—";
  const s = fmtN(v, d);
  return v < 0 ? s : `+${s}`;
}
function fmtDate(iso) {
  const s = txt(iso);
  if (!s) return null;
  const m = /^(\d{4})-(\d{2})-(\d{2})$/.exec(s);
  return m ? `${m[3]}.${m[2]}.${m[1]}` : s;
}

// Пять эпистемических меток спецификации (Часть 6.3) — переиспользуем ТРИ
// канонических цвета из basis-design-system.css: факт (серый) / оценка
// (синий, --bs-estimate) / суждение (медь) — «разовый» это по сути
// предупреждение «не продлевай в будущее», ближе всего к суждению.
const TAG_CLASS = {
  "из источника": "bs-tag-fact",
  "из структуры": "bs-tag-fact",
  "оценка": "bs-tag-estimate",
  "прогноз": "bs-tag-estimate",
  "разовый": "bs-tag-judgment",
};
function EpistemicTag({ label }) {
  const l = txt(label);
  if (!l) return null;
  return <span className={TAG_CLASS[l] || "bs-tag-fact"}>{l}</span>;
}

// Три точки — сила фактора / уверенность расчёта. Декоративное усиление слова
// (aria-hidden), само слово остаётся основным, видимым сигналом — не полагаемся
// на цвет/точки как на единственный носитель смысла.
function Dots({ level }) {
  return (
    <span className="mt-strength" aria-hidden="true">
      {[1, 2, 3].map((i) => <i key={i} className={i <= level ? "on" : ""} />)}
    </span>
  );
}

// ▲/▼ + подписанное число — глиф обязателен рядом с цветом (конституция: у
// каждой дельты глиф, никогда только цвет).
function DeltaTag({ value, unit = "%" }) {
  if (!isNum(value)) return null;
  const cls = value > 0 ? "bs-d-good" : value < 0 ? "bs-d-bad" : "bs-d-neutral";
  const glyph = value > 0 ? "▲" : value < 0 ? "▼" : "•";
  return (
    <span className={`bs-mono mt-delta ${cls}`}>
      {glyph} {fmtSigned(value, 0)}{unit}
    </span>
  );
}

const COND_ORDER = ["ключевая ставка", "инфляция", "рост ВВП", "курс рубля"];
function orderedConditions(cond) {
  const c = obj(cond);
  if (!c) return [];
  const known = COND_ORDER.filter((k) => k in c).map((k) => [k, c[k]]);
  const rest = Object.keys(c).filter((k) => !COND_ORDER.includes(k)).map((k) => [k, c[k]]);
  return [...known, ...rest];
}

// Домен для полоски диапазона: один общий масштаб на метрику (выручка / чистая
// прибыль) по всем строкам сценариев + 2026 год + базовый год — так все восемь
// полосок в сетке сравнимы визуально между собой, а не каждая в своём масштабе.
function computeDomain(scn) {
  const vals = { revenue: [], net_profit: [] };
  const pushRow = (r) => {
    ["revenue", "net_profit"].forEach((k) => {
      const o = obj(r && r[k]);
      if (!o) return;
      ["low", "base", "high"].forEach((f) => { if (isNum(o[f])) vals[k].push(o[f]); });
    });
  };
  arr(scn && scn.rows).forEach(pushRow);
  if (scn && scn.common_2026) pushRow(scn.common_2026);
  const bf = obj(scn && scn.base_fact);
  if (bf) {
    if (isNum(bf.revenue)) vals.revenue.push(bf.revenue);
    if (isNum(bf.net_profit)) vals.net_profit.push(bf.net_profit);
    if (isNum(bf.net_profit_scenario_base)) vals.net_profit.push(bf.net_profit_scenario_base);
  }
  const mk = (a) => (a.length ? [Math.min(...a), Math.max(...a)] : null);
  return { revenue: mk(vals.revenue), net_profit: mk(vals.net_profit) };
}
function posPct(v, domain) {
  const [dmin, dmax] = domain;
  if (dmax === dmin) return 50;
  return Math.max(0, Math.min(100, ((v - dmin) / (dmax - dmin)) * 100));
}

// Полоска диапазона «min–база–max» относительно базового года (дизайн-решение
// брифа для блока 4): заливка от low до high, сплошная риска — среднее значение
// сценария, пунктирная — где на этой же шкале стоит базовый (фактический) год.
// Числами дублируется рядом в тексте (.mt-scn-metric-range) — полоска не
// единственный носитель информации, только усиление.
function RangeBar({ low, base, high, domain, refValue, positive }) {
  if (!domain || !isNum(low) || !isNum(high)) return null;
  const lowP = posPct(low, domain);
  const highP = posPct(high, domain);
  const baseP = isNum(base) ? posPct(base, domain) : null;
  const refP = isNum(refValue) ? posPct(refValue, domain) : null;
  return (
    <div className="mt-rbar" aria-hidden="true">
      <div className="mt-rbar-track">
        <div className={`mt-rbar-fill ${positive ? "up" : "down"}`} style={{ left: `${lowP}%`, width: `${Math.max(highP - lowP, 1.2)}%` }} />
        {refP != null && <div className="mt-rbar-ref" style={{ left: `${refP}%` }} />}
        {baseP != null && <div className="mt-rbar-base" style={{ left: `${baseP}%` }} />}
      </div>
    </div>
  );
}

// --------------------------------------------------------------------------
// Блок 1 — «Что происходит сейчас» (сигнал вкладки, слой 2 из четырёх слоёв
// чтения). Единственная всегда-тёмная карточка вкладки — .bs-deep-card
// задумана каноном именно для интерпретации/суждения, здесь ей самое место.
// --------------------------------------------------------------------------
const REGIME_CLASS = { "помогает": "up", "смешанно": "mixed", "мешает": "down" };
const REGIME_GLYPH = { "помогает": "▲", "смешанно": "●", "мешает": "▼" };

function NowBlock({ now }) {
  if (!now || (!txt(now.text) && !now.regime)) return null;
  const av = arr(now.anchor_values);
  const asOf = fmtDate(now.as_of);
  return (
    <section className="mt-block">
      <div className="bs-deep-card mt-now">
        <div className="bs-deep-eyebrow">ЧТО ПРОИСХОДИТ СЕЙЧАС{asOf ? ` · на ${asOf}` : ""}</div>
        <div className="mt-now-head">
          {now.regime && (
            <span className={`mt-regime mt-regime-${REGIME_CLASS[now.regime] || "mixed"}`}>
              <span className="glyph" aria-hidden="true">{REGIME_GLYPH[now.regime] || "●"}</span>{now.regime}
            </span>
          )}
          {txt(now.main_pressure) && <span className="mt-pressure">главное давление — <b>{now.main_pressure}</b></span>}
        </div>
        {txt(now.text) && <p>{now.text}</p>}
        {av.length > 0 && (
          <div className="mt-now-anchors">
            {av.map((a, i) => (a && txt(a.value) ? (
              <div className="mt-deep-stat" key={i}>
                <span className="mt-ds-lbl">{a.label || "—"}</span>
                <span className="mt-ds-val">{a.value}</span>
              </div>
            ) : null))}
          </div>
        )}
      </div>
    </section>
  );
}

// --------------------------------------------------------------------------
// Блок 2 — «От чего зависит компания»
// --------------------------------------------------------------------------
const SIGN_CLASS = { "помогает": "bs-wind-up", "мешает": "bs-wind-down", "двояко": "bs-wind-neutral" };
const STRENGTH_LEVEL = { "сильный": 3, "средний": 2, "слабый": 1 };

function FactorCard({ f }) {
  const chain = arr(f.chain);
  const n = obj(f.number);
  return (
    <div className="bs-card mt-factor">
      <div className="mt-factor-head">
        <h4>{f.name || "—"}</h4>
        <div className="mt-factor-head-tags">
          {f.sign && <span className={`bs-wind-tag ${SIGN_CLASS[f.sign] || "bs-wind-neutral"}`}>{f.sign}</span>}
          {f.strength && (
            <span style={{ display: "inline-flex", alignItems: "center", gap: 6 }}>
              <Dots level={STRENGTH_LEVEL[f.strength] || 0} />
              <span className="mt-strength-word">{f.strength}</span>
            </span>
          )}
        </div>
      </div>
      {txt(f.strength_basis) && <p className="mt-factor-basis">{f.strength_basis}</p>}
      {chain.length > 0 && (
        <div className="mt-chain">
          {chain.map((step, i) => (
            <React.Fragment key={i}>
              {i > 0 && <ArrowRight size={12} className="mt-chain-arrow" aria-hidden="true" />}
              <span className="mt-chain-step">{step}</span>
            </React.Fragment>
          ))}
        </div>
      )}
      {n && txt(n.text) && (
        <div className="mt-factor-number">
          <EpistemicTag label={n.label} />
          <p>{n.text}</p>
        </div>
      )}
    </div>
  );
}

function DriversBlock({ drivers }) {
  const factors = arr(drivers && drivers.factors);
  if (!factors.length) return null;
  return (
    <section className="mt-block">
      <h2 className="mt-block-title">От чего зависит компания</h2>
      <div className="mt-factors">
        {factors.map((f, i) => <FactorCard f={f || {}} key={f?.name || i} />)}
      </div>
      {txt(drivers.cycle) && (
        <div className="mt-cycle">
          <Activity size={14} aria-hidden="true" />
          <p>{drivers.cycle}</p>
        </div>
      )}
      {txt(drivers.hidden_link) && (
        <div className="bs-callout">
          <Info aria-hidden="true" />
          <p><b>Неочевидное звено.</b> {drivers.hidden_link}</p>
        </div>
      )}
    </section>
  );
}

// --------------------------------------------------------------------------
// Блок 3 — «Конкурентный разрез»
// --------------------------------------------------------------------------
function PeersBlock({ peers }) {
  if (!peers) return null;
  const winners = arr(peers.winners);
  const losers = arr(peers.losers);
  const hasContent = peers.uniform || txt(peers.fault_line) || winners.length || losers.length || txt(peers.position);
  if (!hasContent) return null;
  return (
    <section className="mt-block">
      <h2 className="mt-block-title">Конкурентный разрез</h2>
      <div className="bs-card mt-peers">
        {peers.uniform ? (
          <p className="mt-peers-uniform">Макроэкономический фон действует на сектор равномерно — относительного преимущества у компании сейчас нет.</p>
        ) : (
          <>
            {txt(peers.fault_line) && (
              <div className="mt-peers-fault">
                <div className="mt-peers-eyebrow">ЧТО СЕЙЧАС ДЕЛИТ СЕКТОР</div>
                <p>{peers.fault_line}</p>
              </div>
            )}
            {(winners.length > 0 || losers.length > 0) && (
              <div className="mt-peers-cols">
                {winners.length > 0 && (
                  <div className="mt-peers-col">
                    <div className="mt-peers-col-lbl up"><TrendingUp size={13} aria-hidden="true" /> Выигрывают сейчас</div>
                    <div className="mt-peers-chips">{winners.map((w, i) => <span className="mt-peer-chip up" key={i}>{w}</span>)}</div>
                  </div>
                )}
                {losers.length > 0 && (
                  <div className="mt-peers-col">
                    <div className="mt-peers-col-lbl down"><TrendingDown size={13} aria-hidden="true" /> Проигрывают сейчас</div>
                    <div className="mt-peers-chips">{losers.map((l, i) => <span className="mt-peer-chip down" key={i}>{l}</span>)}</div>
                  </div>
                )}
              </div>
            )}
            {txt(peers.position) && (
              <div className="mt-peers-position">
                <Target size={14} aria-hidden="true" />
                <p>{peers.position}</p>
              </div>
            )}
            {txt(peers.share_shift) && (
              <p className="mt-peers-shift"><TrendingUp size={13} aria-hidden="true" /> <span><b>Доли рынка.</b> {peers.share_shift}</span></p>
            )}
          </>
        )}
      </div>
    </section>
  );
}

// --------------------------------------------------------------------------
// Блок 4 — «Сценарии Банка России» — дизайн-задача брифа: не «простыня» 4×7,
// а карточки сценариев (2026 год тонкой строкой сверху, четыре сценария 2027
// года — сеткой карточек с полоской диапазона относительно базового года).
// --------------------------------------------------------------------------
function Common2026Row({ c2026 }) {
  const conds = orderedConditions(c2026.conditions);
  const rev = obj(c2026.revenue);
  const np = obj(c2026.net_profit);
  return (
    <div className="mt-c2026">
      <div className="mt-c2026-head">
        <span className="mt-c2026-tag">{c2026.year || "2026"} год</span>
        <span className="mt-c2026-note-lbl">ожидание регулятора на текущий год — одинаково во всех сценариях</span>
      </div>
      {conds.length > 0 && (
        <div className="mt-c2026-conds">
          {conds.map(([k, v]) => <span key={k}><b>{k}:</b> {txt(v) || "—"}</span>)}
        </div>
      )}
      {(rev || np) && (
        <div className="mt-c2026-metrics">
          {rev && <span>Выручка {fmtN(rev.base, 1)} млрд ₽ <DeltaTag value={rev.pct_base} /></span>}
          {np && <span>Чистая прибыль {fmtN(np.base, 1)} млрд ₽ <DeltaTag value={np.pct_base} /></span>}
        </div>
      )}
      {txt(c2026.note) && <p className="mt-c2026-noteline">{c2026.note}</p>}
      {arr(c2026.flags).length > 0 && (
        <div className="mt-scn-flags">
          {c2026.flags.map((fl, i) => <div className="mt-scn-flag" key={i}><AlertTriangle size={12} aria-hidden="true" /> {fl}</div>)}
        </div>
      )}
    </div>
  );
}

function ScenarioMetric({ label, o, domain, refValue }) {
  if (!o) return null;
  const positive = isNum(o.pct_base) ? o.pct_base >= 0 : (isNum(o.base) && isNum(refValue) ? o.base >= refValue : true);
  const hasPctRange = isNum(o.pct_low) || isNum(o.pct_high);
  return (
    <div className="mt-scn-metric">
      <div className="mt-scn-metric-head">
        <span className="mt-scn-metric-lbl">{label}</span>
        <DeltaTag value={o.pct_base} />
      </div>
      <div className="mt-scn-metric-val">{fmtN(o.base, 1)} млрд ₽</div>
      <RangeBar low={o.low} base={o.base} high={o.high} domain={domain} refValue={refValue} positive={positive} />
      <div className="mt-scn-metric-range">
        {fmtN(o.low, 1)} … {fmtN(o.high, 1)} млрд ₽
        {hasPctRange ? ` (${fmtSigned(o.pct_low, 0)}…${fmtSigned(o.pct_high, 0)}%)` : ""}
      </div>
    </div>
  );
}

function ScenarioCard({ row, domain, refRevenue, refProfit }) {
  const conds = orderedConditions(row.conditions);
  const flags = arr(row.flags);
  return (
    <div className="bs-card mt-scn-card">
      <div className="mt-scn-head">
        <h4>{row.scenario || "—"}</h4>
        {isNum(row.year) && <span className="mt-scn-year">{row.year}</span>}
      </div>
      {conds.length > 0 && (
        <div className="mt-scn-conds">
          {conds.map(([k, v]) => (
            <div className="mt-scn-cond-row" key={k}>
              <span className="mt-scn-cond-lbl">{k}</span>
              <span className="mt-scn-cond-val">{txt(v) || "—"}</span>
            </div>
          ))}
        </div>
      )}
      <div className="mt-scn-metrics">
        <ScenarioMetric label="Выручка" o={obj(row.revenue)} domain={domain.revenue} refValue={refRevenue} />
        <ScenarioMetric label="Чистая прибыль" o={obj(row.net_profit)} domain={domain.net_profit} refValue={refProfit} />
      </div>
      {txt(row.explanation) && <p className="mt-scn-expl">{row.explanation}</p>}
      {txt(row.dominant_factor) && (
        <div className="mt-scn-dom"><Zap size={12} aria-hidden="true" /> <span>Определяет исход: {row.dominant_factor}</span></div>
      )}
      {flags.length > 0 && (
        <div className="mt-scn-flags">
          {flags.map((fl, i) => <div className="mt-scn-flag" key={i}><AlertTriangle size={12} aria-hidden="true" /> {fl}</div>)}
        </div>
      )}
    </div>
  );
}

function ScenariosBlock({ scenarios: scn, staleness }) {
  const rows = arr(scn && scn.rows);
  if (!scn || !rows.length) return null;
  const domain = computeDomain(scn);
  const bf = obj(scn.base_fact) || {};
  const profitBase = isNum(bf.net_profit_scenario_base) ? bf.net_profit_scenario_base : bf.net_profit;
  const bridgeNeeded = isNum(bf.net_profit_scenario_base) && isNum(bf.net_profit) && Math.abs(bf.net_profit_scenario_base - bf.net_profit) > 0.5;
  const interim = obj(scn.interim_fact);
  const asOfSrc = fmtDate(scn.as_of);
  // Разные компании (пилот) пробовали разные имена для одной и той же вводной
  // фразы «это не прогноз роста, а сравнение при неизменном масштабе бизнеса» —
  // берём первую, что нашлась, имя поля ещё не устоялось у источника данных.
  const framingNote = txt(scn.framing) || txt(scn.note) || txt(scn.reading_note) || txt(scn.scope_note);
  const conditionsLegend = txt(scn.conditions_legend);
  const detailsItems = !!(framingNote || conditionsLegend || arr(scn.caveats).length > 0 || arr(scn.extra_assumptions).length > 0 || txt(scn.held_at_base_note));

  return (
    <section className="mt-block">
      <h2 className="mt-block-title">Сценарии Банка России</h2>

      {(txt(scn.source) || asOfSrc) && (
        <div className="mt-scn-source">{scn.source}{asOfSrc ? ` · сценарии от ${asOfSrc}` : ""}</div>
      )}

      {staleness && txt(staleness.text) && (
        <div className="bs-callout">
          <RefreshCw aria-hidden="true" />
          <p><b>Что изменилось с даты сценариев.</b> {staleness.text}</p>
        </div>
      )}

      {(isNum(bf.revenue) || isNum(bf.net_profit)) && (
        <div className="mt-scn-basefact">
          <EpistemicTag label="из источника" />
          <span className="mt-scn-basefact-txt">
            {bf.year || "предыдущий"} год — точка отсчёта: выручка {fmtN(bf.revenue, 1)} млрд ₽, чистая прибыль {fmtN(bf.net_profit, 1)} млрд ₽
            {bridgeNeeded ? <>; сравнение сценариев ведётся от устойчивой базы {fmtN(bf.net_profit_scenario_base, 1)} млрд ₽ (мост — в «Как посчитано»)</> : null}
          </span>
          {(txt(bf.note) || txt(scn.base_note)) && <p className="mt-scn-basefact-note">{txt(bf.note) || txt(scn.base_note)}</p>}
        </div>
      )}

      {interim && txt(interim.text) && (
        <div className="mt-fact-note">
          <EpistemicTag label={interim.label || "из источника"} />
          <p>{interim.text}</p>
        </div>
      )}

      {scn.common_2026 && <Common2026Row c2026={scn.common_2026} />}

      <div className="mt-legend">
        Полоска — диапазон сценария на {rows[0]?.year || "следующий год"} (низкий…высокий), тёмная чёрточка — среднее значение сценария, пунктирная — {bf.year || "предыдущий"} год (факт).
      </div>

      <div className="mt-scn-grid">
        {rows.map((row, i) => (
          <ScenarioCard row={row || {}} domain={domain} refRevenue={bf.revenue} refProfit={profitBase} key={row?.scenario_id || row?.scenario || i} />
        ))}
      </div>

      {detailsItems && (
        <details className="mt-details">
          <summary><span>Оговорки и допущения расчёта</span></summary>
          <div className="mt-details-body">
            {framingNote && <p>{framingNote}</p>}
            {conditionsLegend && <p>{conditionsLegend}</p>}
            {arr(scn.caveats).length > 0 && <ul>{scn.caveats.map((c, i) => <li key={i}>{c}</li>)}</ul>}
            {arr(scn.extra_assumptions).length > 0 && (
              <div>
                <div className="mt-details-sub">Что дополнительно принято допущением Basis</div>
                <ul>{scn.extra_assumptions.map((c, i) => <li key={i}>{c}</li>)}</ul>
              </div>
            )}
            {txt(scn.held_at_base_note) && <p>{scn.held_at_base_note}</p>}
          </div>
        </details>
      )}
    </section>
  );
}

// --------------------------------------------------------------------------
// Блок 5 — «Как макроэкономика влияет на цену акции» — дизайн-задача брифа:
// три механизма как последовательность шагов (не одинаковые карточки), а не
// одно число выделено как отдельный «сигнал» с эпистемической меткой.
// --------------------------------------------------------------------------
function PriceLinkBlock({ priceLink }) {
  const mechs = arr(priceLink && priceLink.mechanisms);
  if (!mechs.length) return null;
  const number = obj(priceLink.number);
  return (
    <section className="mt-block">
      <h2 className="mt-block-title">Как макроэкономика влияет на цену акции</h2>
      <ol className="mt-steps">
        {mechs.map((m, i) => (
          <li className="mt-step" key={i}>
            <div className="mt-step-num">{i === 2 && mechs.length === 3 ? "1+2" : i + 1}</div>
            <div className="mt-step-body">
              {txt(m.title) && <h4>{m.title}</h4>}
              {txt(m.text) && <p>{m.text}</p>}
              {txt(m.company) && <p className="mt-step-company">{m.company}</p>}
            </div>
          </li>
        ))}
      </ol>
      {number && txt(number.text) && (
        <div className="mt-estimate-callout">
          <EpistemicTag label={number.label || "оценка"} />
          <p className="mt-estimate-txt">{number.text}</p>
          {txt(number.caveat) && <p className="mt-estimate-caveat">{number.caveat}</p>}
        </div>
      )}
    </section>
  );
}

// --------------------------------------------------------------------------
// Блок 6 — «Как посчитано» — свёрнуто по умолчанию (методика 6.1).
// --------------------------------------------------------------------------
const CONF_LEVEL = { "низкая": 1, "средняя": 2, "высокая": 3 };

function HowComputedBlock({ howComputed: hc, calc }) {
  if (!hc) return null;
  const bv = obj(hc.base_values) || {};
  const conf = obj(hc.confidence) || {};
  const dates = obj(hc.dates) || {};
  const legend = obj(hc.labels_legend) || {};
  const coefs = arr(hc.coefficients);
  const assumptions = arr(hc.assumptions);
  const sources = arr(hc.sources);
  // Мост к устойчивой базе прибыли встречался у пилота в трёх формах: список
  // объектов {step,amount,label} (base_values.base_bridge — основная форма
  // контракта), список готовых строк (у одной компании — на уровень выше,
  // how_computed.base_bridge) или короткий абзац одной строкой (base_values.
  // bridge_note) — показываем то, что реально есть, без гадания за писателя.
  const bridge = arr(bv.base_bridge).length > 0 ? bv.base_bridge : arr(hc.base_bridge);
  const bridgeIsRows = bridge.length > 0 && typeof bridge[0] === "object" && bridge[0] !== null;
  const bridgeNote = txt(bv.bridge_note);
  const oneOff = obj(bv.one_off);
  const legendEntries = Object.entries(legend);
  // У части компаний нет плоского net_profit — только net_profit_adjusted
  // (то же число, что в «Финансах», см. matches_finance_tab) или, на крайний
  // случай, net_profit_reported (до вычета разовых статей).
  const netProfitShown = isNum(bv.net_profit) ? bv.net_profit
    : isNum(bv.net_profit_adjusted) ? bv.net_profit_adjusted
    : bv.net_profit_reported;

  return (
    <section className="mt-block">
      <details className="mt-details">
        <summary>
          <span>Как посчитано</span>
          {conf.level && (
            <span className="mt-conf"><Dots level={CONF_LEVEL[conf.level] || 0} /> уверенность: {conf.level}</span>
          )}
        </summary>
        <div className="mt-details-body">
          {(isNum(bv.revenue) || isNum(netProfitShown)) && (
            <div>
              <div className="mt-details-sub">База расчёта</div>
              {isNum(bv.revenue) && <div className="mt-hc-base-row"><span>Выручка</span><span className="bs-mono">{fmtN(bv.revenue, 1)} млрд ₽</span></div>}
              {isNum(netProfitShown) && <div className="mt-hc-base-row"><span>Чистая прибыль</span><span className="bs-mono">{fmtN(netProfitShown, 1)} млрд ₽</span></div>}
              {(txt(bv.period) || bv.matches_finance_tab != null) && (
                <div className="mt-hc-period">{txt(bv.period)}{bv.matches_finance_tab ? " · совпадает со вкладкой «Финансы»" : ""}</div>
              )}
              {txt(bv.revenue_definition) && <p className="mt-hc-note">{bv.revenue_definition}</p>}
            </div>
          )}

          {txt(hc.interim_note) && <p className="mt-hc-note">{hc.interim_note}</p>}

          {bridge.length > 0 && (
            <div>
              <div className="mt-details-sub">Мост к устойчивой базе прибыли</div>
              {bridgeIsRows ? (
                bridge.map((s, i) => (
                  <div className="mt-bridge-row" key={i}>
                    <span className="mt-bridge-step">{s.step}{s.label ? <EpistemicTag label={s.label} /> : null}</span>
                    {isNum(s.amount) && <span className="bs-mono">{fmtSigned(s.amount, 1)}</span>}
                  </div>
                ))
              ) : (
                <ul>{bridge.map((s, i) => <li key={i}>{String(s)}</li>)}</ul>
              )}
            </div>
          )}
          {!bridge.length && bridgeNote && (
            <div>
              <div className="mt-details-sub">Мост к устойчивой базе прибыли</div>
              <p>{bridgeNote}</p>
            </div>
          )}

          {oneOff && txt(oneOff.text) && (
            <div className="mt-fact-note mt-hc-oneoff">
              <EpistemicTag label={oneOff.label || "разовый"} />
              <p>{oneOff.text}</p>
            </div>
          )}

          {txt(bv.base_year_caveat) && <p className="mt-hc-note">{bv.base_year_caveat}</p>}

          {coefs.length > 0 && (
            <div>
              <div className="mt-details-sub">Коэффициенты чувствительности</div>
              {coefs.map((c, i) => (
                <div className="mt-coef-row" key={i}>
                  <div className="mt-coef-name">{c.name}</div>
                  {txt(c.value_text) && <div className="mt-coef-value">{c.value_text}</div>}
                  {txt(c.origin) && <div className="mt-coef-origin">{c.origin}</div>}
                </div>
              ))}
            </div>
          )}

          {assumptions.length > 0 && (
            <div>
              <div className="mt-details-sub">Допущения</div>
              <ul>{assumptions.map((a, i) => <li key={i}>{a}</li>)}</ul>
            </div>
          )}

          {sources.length > 0 && (
            <div>
              <div className="mt-details-sub">Источники</div>
              <ul>
                {sources.map((s, i) => (
                  <li key={i}>
                    {s.url ? <a href={s.url} target="_blank" rel="noopener noreferrer">{s.title}</a> : <span>{s.title}</span>}
                    {txt(s.date) && <span className="mt-src-date"> · {s.date}</span>}
                  </li>
                ))}
              </ul>
            </div>
          )}

          {(txt(dates.analysis) || txt(dates.macro_update) || txt(dates.reporting_period)) && (
            <div className="mt-hc-dates">
              {txt(dates.analysis) && <span>разбор {fmtDate(dates.analysis)}</span>}
              {txt(dates.macro_update) && <span>обновление макроэкономики {fmtDate(dates.macro_update)}</span>}
              {txt(dates.reporting_period) && <span>отчётность за {dates.reporting_period}</span>}
            </div>
          )}

          {txt(conf.reason) && (
            <div>
              <div className="mt-details-sub">Уровень уверенности{conf.level ? `: ${conf.level}` : ""}</div>
              <p>{conf.reason}</p>
            </div>
          )}

          {legendEntries.length > 0 && (
            <div>
              <div className="mt-details-sub">Обозначения</div>
              {legendEntries.map(([k, v]) => (
                <div className="mt-legend-row" key={k}>
                  <EpistemicTag label={k} />
                  <span>{v}</span>
                </div>
              ))}
            </div>
          )}

          {txt(calc && calc.method_note) && <p className="mt-hc-note">{calc.method_note}</p>}
        </div>
      </details>
    </section>
  );
}

// --------------------------------------------------------------------------
// Компонент вкладки целиком
// --------------------------------------------------------------------------
export default function MacroeconomicsTab({ data, company }) {
  if (!data || typeof data !== "object") return null;
  const meta = obj(data.meta) || {};
  const companyLabel = (company && (company.name || company.ticker)) || meta.name || meta.ticker || "";
  const topDate = fmtDate(meta.as_of);
  const footerBits = [];
  if (txt(meta.macro_as_of)) footerBits.push(`макроэкономика на ${fmtDate(meta.macro_as_of)}`);
  if (txt(meta.cbr_scenarios_as_of)) footerBits.push(`сценарии Банка России на ${fmtDate(meta.cbr_scenarios_as_of)}`);

  return (
    <div className="macro-tab-v2">
      <div className="mt-topmeta">
        <span className="mt-topmeta-eyebrow">Макроэкономика{companyLabel ? ` · ${companyLabel}` : ""}</span>
        {topDate && <span className="mt-topmeta-date">данные на {topDate}</span>}
      </div>

      <NowBlock now={data.now} />
      <DriversBlock drivers={data.drivers} />
      <PeersBlock peers={data.peers} />
      <ScenariosBlock scenarios={data.scenarios} staleness={data.staleness} />
      <PriceLinkBlock priceLink={data.price_link} />
      <HowComputedBlock howComputed={data.how_computed} calc={data.calc} />

      {footerBits.length > 0 && (
        <div className="mt-footer">Basis · {footerBits.join(" · ")}</div>
      )}
    </div>
  );
}

/* Вкладка «Макроэкономика» нового образца (пилот 09.2026, доработка 16.09 —
   продуктовые рекомендации docs/macro_tab_product_recommendations_2026-09-16.md).
   Источник данных: GET /api/companies/by-ticker/{ticker}/macro-tab — файл
   backend/companies/<T>/macro_tab.json (агент-писатель) + поле calc,
   которое ручка подмешивает из macro_scenarios.json (см. companies.py,
   get_macro_tab). Контракт полей — docs/macro_model_contract_v1.md, раздел 7
   и 7.1 (два слоя текста lead/details/takeaway, качественный вариант
   scenarios.variant === "qualitative" без чисел). Состав, порядок и
   формулировки шести блоков — docs/Описание_вкладки_макроэкономика.md, Части
   0–7 (владелец, версия 1). Рендерит ТОЛЬКО то, что реально пришло —
   компонент не считает арифметику и не досочиняет текст (методика 0.5):
   каждое число берётся из JSON как есть, каждый блок без обязательных полей
   просто не рисуется.

   На 16.09.2026 из 35 карточек пилота только 10 — числовой вариант
   (now/drivers/peers/price_link/how_computed заполнены), у остальных 25 эти
   блоки — null (скелет вида GAZP: заполнена только качественная «лестница»
   сценариев). Это НЕ край случая, а большинство — компонент обязан рендерить
   такие файлы без единой пустой плашки и без падений. Новые поля 7.1
   (lead/details/takeaway/headline/verdict/takeaway) ещё не пришли ни в один
   из 10 числовых файлов — везде в ходу фолбэк (первое предложение текста).

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

// Первое предложение — фолбэк для now.lead, пока писатель не прислал
// отдельное поле (раздел 7.1 контракта): режем по первому ./!/?/…
// с пробелом или концом строки после. Грубая эвристика, используется ТОЛЬКО
// как временный фолбэк — когда придёт настоящий now.lead, вызывается не будет.
function firstSentence(text) {
  const t = txt(text);
  if (!t) return null;
  const m = /^(.+?[.!?…])(\s|$)/.exec(t);
  return m ? m[1] : t;
}

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
// Округление главного числа лестницы сценариев без ложной точности (продуктовая
// рекомендация B/E-2): целое число, а при величине больше 1000 — до десятков,
// чтобы последняя цифра не изображала точность, которой нет у оценки с диапазоном.
function stepFor(base) { return isNum(base) && Math.abs(base) > 1000 ? 10 : 1; }
function fmtStep(v, step) {
  if (!isNum(v)) return "—";
  return fmtN(Math.round(v / step) * step, 0);
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
  "суждение": "bs-tag-judgment",
};

// Вердикт качественного сценария (раскатка без финмодели): помогает / мешает / примерно так же
const VERDICT_CLASS = { "помогает": "mt-verdict good", "мешает": "mt-verdict bad", "примерно так же": "mt-verdict neutral" };
function VerdictChip({ verdict }) {
  const v = txt(verdict);
  if (!v) return null;
  const glyph = v === "помогает" ? "▲" : v === "мешает" ? "▼" : "≈";
  return <span className={VERDICT_CLASS[v] || "mt-verdict neutral"}>{glyph} {v}</span>;
}
function EpistemicTag({ label }) {
  const l = txt(label);
  if (!l) return null;
  return <span className={TAG_CLASS[l] || "bs-tag-fact"}>{l}</span>;
}

// Строка-итог «Итог для инвестора» (продуктовая рекомендация D) — следствие
// БЕЗ рекомендации: описывает, что происходит с выручкой/прибылью/долгом,
// не переходит в «стоит/выгодно». Текст пишет агент-писатель, компонент
// только выводит его, если поле пришло — сам ничего не формулирует.
function Takeaway({ text }) {
  const t = txt(text);
  if (!t) return null;
  return (
    <div className="mt-takeaway">
      <span className="mt-takeaway-lbl">Итог для инвестора</span>
      <p>{t}</p>
    </div>
  );
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
  // |Δ| ≤ 3% — «примерно столько же»: нейтральный цвет и глиф ≈, чтобы +3% и +49% не
  // читались одинаково (замечание персоны-ревьюера 16.09).
  const nearZero = Math.abs(value) <= 3;
  const cls = nearZero ? "bs-d-neutral" : value > 0 ? "bs-d-good" : "bs-d-bad";
  const glyph = nearZero ? "≈" : value > 0 ? "▲" : "▼";
  return (
    <span className={`bs-mono mt-delta ${cls}`}>
      {glyph} {fmtSigned(value, 0)}{unit}
    </span>
  );
}

const COND_ORDER = ["ключевая ставка", "инфляция", "рост ВВП", "курс рубля"];
// Короткие подписи ТОЛЬКО для четырёх канонических условий (методика 0 —
// «инвестору как условия сценария показываются ровно четыре показателя»);
// неизвестные дополнительные ключи (напр. госзаказ у ОАК) выводим как есть —
// не подбираем сокращение для того, что не контролируем сами.
const COND_SHORT = { "ключевая ставка": "ставка", "инфляция": "инфляция", "рост ВВП": "ВВП", "курс рубля": "курс" };
function orderedConditions(cond) {
  const c = obj(cond);
  if (!c) return [];
  const known = COND_ORDER.filter((k) => k in c).map((k) => [k, c[k]]);
  const rest = Object.keys(c).filter((k) => !COND_ORDER.includes(k)).map((k) => [k, c[k]]);
  return [...known, ...rest];
}

// Домен для полоски диапазона на шкале (клик по строке лестницы) — один общий
// масштаб чистой прибыли по всем строкам + 2026 год + базовый год, чтобы бар
// каждой развёрнутой строки был сравним с остальными, а не в своём масштабе.
function computeProfitDomain(scn) {
  const vals = [];
  const pushRow = (r) => {
    const o = obj(r && r.net_profit);
    if (!o) return;
    ["low", "base", "high"].forEach((f) => { if (isNum(o[f])) vals.push(o[f]); });
  };
  arr(scn && scn.rows).forEach(pushRow);
  if (scn && scn.common_2026) pushRow(scn.common_2026);
  const bf = obj(scn && scn.base_fact);
  if (bf) {
    if (isNum(bf.net_profit)) vals.push(bf.net_profit);
    if (isNum(bf.net_profit_scenario_base)) vals.push(bf.net_profit_scenario_base);
  }
  return vals.length ? [Math.min(...vals), Math.max(...vals)] : null;
}
function posPct(v, domain) {
  const [dmin, dmax] = domain;
  if (dmax === dmin) return 50;
  return Math.max(0, Math.min(100, ((v - dmin) / (dmax - dmin)) * 100));
}

// Полоска диапазона «min–база–max» относительно базового года — теперь живёт
// ТОЛЬКО под раскрытием строки лестницы (клик «показать на шкале» — вариант 3
// из брифа как опция внутри варианта 2). Заливка от low до high, сплошная
// риска — среднее значение сценария, пунктирная — базовый (фактический) год.
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

// Мост к устойчивой базе прибыли встречался у пилота в трёх формах: список
// объектов {step,amount,label} (base_values.base_bridge — основная форма
// контракта), список готовых строк (у части компаний — на уровень выше,
// how_computed.base_bridge) или короткий абзац одной строкой (base_values.
// bridge_note). Общий разбор формы — здесь, используется и в плашке моста
// над сценариями (блок 4), и в «Как посчитано» (блок 6), без дублирования кода.
function resolveBridge(bv, hc) {
  const rows = arr(bv && bv.base_bridge).length > 0 ? bv.base_bridge : arr(hc && hc.base_bridge);
  const isRows = rows.length > 0 && typeof rows[0] === "object" && rows[0] !== null;
  return { rows, isRows, note: txt(bv && bv.bridge_note) };
}
function BridgeBody({ bridge }) {
  if (!bridge) return null;
  if (bridge.rows.length > 0) {
    return bridge.isRows ? (
      <>
        {bridge.rows.map((s, i) => (
          <div className="mt-bridge-row" key={i}>
            <span className="mt-bridge-step">{s.step}{s.label ? <EpistemicTag label={s.label} /> : null}</span>
            {isNum(s.amount) && <span className="bs-mono">{fmtSigned(s.amount, 1)}</span>}
          </div>
        ))}
      </>
    ) : (
      <ul>{bridge.rows.map((s, i) => <li key={i}>{String(s)}</li>)}</ul>
    );
  }
  if (bridge.note) return <p>{bridge.note}</p>;
  return null;
}

// --------------------------------------------------------------------------
// Блок 1 — «Что происходит сейчас» (сигнал вкладки, слой 2 из четырёх слоёв
// чтения). Единственная всегда-тёмная карточка вкладки — .bs-deep-card
// задумана каноном именно для интерпретации/суждения, здесь ей самое место.
// Продуктовая рекомендация B/C: вывод (lead) — крупно первой строкой, полный
// текст — ниже, всё избыточное — под «Подробнее», «Итог для инвестора» —
// последней строкой.
// --------------------------------------------------------------------------
const REGIME_CLASS = { "помогает": "up", "смешанно": "mixed", "мешает": "down" };
const REGIME_GLYPH = { "помогает": "▲", "смешанно": "●", "мешает": "▼" };

function NowBlock({ now }) {
  if (!now || (!txt(now.text) && !now.regime)) return null;
  const av = arr(now.anchor_values);
  const asOf = fmtDate(now.as_of);
  // now.lead ещё не пришёл ни у одной из 10 карточек пилота (16.09.2026) —
  // фолбэк первым предложением now.text. Когда поле появится, оно станет
  // самостоятельным выводом, а now.text ниже — короче (раздел B методички),
  // временное дублирование первой фразы — ожидаемая цена фолбэка, не баг.
  const lead = txt(now.lead) || firstSentence(now.text);
  const bodyText = txt(now.text);
  const details = txt(now.details);
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
        {lead && <div className="mt-now-lead">{lead}</div>}
        {bodyText && <p className="mt-now-text">{bodyText}</p>}
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
        {details && (
          <details className="mt-details mt-now-details">
            <summary><span>Подробнее</span></summary>
            <div className="mt-details-body"><p>{details}</p></div>
          </details>
        )}
        <Takeaway text={now.takeaway} />
      </div>
    </section>
  );
}

// --------------------------------------------------------------------------
// Блок 2 — «От чего зависит компания» — облегчённая карточка фактора
// (рекомендация C): имя+метки+цепочка-чипы+компактное число видимы сразу,
// основание силы и детали — под «Подробнее», тонкая полоска силы — рядом
// с меткой (усиление, не единственный носитель смысла).
// --------------------------------------------------------------------------
const SIGN_CLASS = { "помогает": "bs-wind-up", "мешает": "bs-wind-down", "двояко": "bs-wind-neutral" };
const STRENGTH_LEVEL = { "сильный": 3, "средний": 2, "слабый": 1 };
const STRENGTH_PCT = { "сильный": 100, "средний": 62, "слабый": 32 };

function FactorStrengthBar({ sign, strength }) {
  const pct = STRENGTH_PCT[strength];
  const cls = sign === "помогает" ? "up" : sign === "мешает" ? "down" : null;
  if (!pct || !cls) return null;
  return (
    <div className="mt-factor-bar" aria-hidden="true">
      <div className="mt-factor-bar-track">
        <span className="mt-factor-bar-center" />
        <span className={`mt-factor-bar-fill ${cls}`} style={{ width: `${pct / 2}%` }} />
      </div>
    </div>
  );
}

function FactorCard({ f }) {
  const chain = arr(f.chain);
  const n = obj(f.number);
  const hasMore = txt(f.strength_basis) || txt(f.details);
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
      <FactorStrengthBar sign={f.sign} strength={f.strength} />
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
      {hasMore && (
        <details className="mt-details mt-factor-details">
          <summary><span>Подробнее</span></summary>
          <div className="mt-details-body">
            {txt(f.strength_basis) && <p>{f.strength_basis}</p>}
            {txt(f.details) && <p>{f.details}</p>}
          </div>
        </details>
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
      <Takeaway text={drivers.takeaway} />
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
// Блок 4 — «Сценарии Банка России» — дизайн-задача доработки 16.09: вместо
// сетки 2×2 тяжёлых карточек — «лестница» (вариант 2 из брифа): строки в
// общей логике «хуже ← база → лучше», сравнимые за секунду сверху вниз,
// работающая одинаково с числами и без (качественный вариант). Клик по
// строке разворачивает объяснение, выручку (вторичную) и диапазон на шкале.
// --------------------------------------------------------------------------

// Порядок строк — по фактическому исходу для КОМПАНИИ, а не по названию
// сценария у регулятора: «Рисковый» называется рисковым по меркам экономики
// в целом, но для конкретной компании может оказаться лучшим исходом (пример
// методички: у экспортёра резкая девальвация в рисковом сценарии перевешивает
// сопутствующие риски). Приоритет сигнала: реальный % изменения прибыли →
// вердикт (если чисел ещё нет) → типовой порядок ЦБ (только когда нет вообще
// никакого сигнала, напр. ещё не заполненный качественный файл).
const CANON_SCN_RANK = { risk: -2, proinflation: -1, base: 0, disinflation: 1 };
const VERDICT_RANK = { "мешает": -1, "примерно так же": 0, "помогает": 1 };
function deriveVerdict(pctBase) {
  if (!isNum(pctBase)) return null;
  if (pctBase > 3) return "помогает";
  if (pctBase < -3) return "мешает";
  return "примерно так же";
}
function rowVerdict(row) {
  const np = obj(row.net_profit);
  return txt(row.verdict) || deriveVerdict(np && np.pct_base);
}
// Контракт задаёт headline целиком как «▲/≈/▼ слово — причина» (раздел 7.1) —
// тот же глиф и слово уже показывает цветной VerdictChip прямо над этой
// строкой, поэтому здесь оставляем только причину: иначе «▼ мешает» читается
// дважды подряд (ровно та «проза-дубль», которую и убирает вся доработка).
const HEADLINE_PREFIX_RE = /^[▲≈▼]\s*(помогает|мешает|примерно так же)\s*[—-]\s*/i;
function headlineReason(headline) {
  const h = txt(headline);
  if (!h) return null;
  return h.replace(HEADLINE_PREFIX_RE, "");
}
function scenarioSortScore(row) {
  const np = obj(row.net_profit);
  if (np && isNum(np.pct_base)) return np.pct_base;
  const v = rowVerdict(row);
  if (v && v in VERDICT_RANK) return VERDICT_RANK[v] * 1000;
  const rank = CANON_SCN_RANK[row.scenario_id];
  return isNum(rank) ? rank : 99;
}

function normalizeC2026(c2026) {
  if (!c2026) return null;
  return {
    key: "c2026",
    name: `${c2026.year || 2026} год`,
    badge: "одинаково во всех сценариях",
    conditions: c2026.conditions,
    verdict: rowVerdict(c2026),
    headline: null,
    revenue: c2026.revenue,
    net_profit: c2026.net_profit,
    explanation: c2026.note,
    dominant_factor: c2026.dominant_factor,
    flags: c2026.flags,
  };
}
function normalizeRow(row) {
  return {
    key: row.scenario_id || row.scenario,
    name: row.scenario || "—",
    badge: isNum(row.year) ? String(row.year) : null,
    conditions: row.conditions,
    verdict: rowVerdict(row),
    headline: txt(row.headline),
    revenue: row.revenue,
    net_profit: row.net_profit,
    explanation: row.explanation,
    dominant_factor: row.dominant_factor,
    flags: row.flags,
  };
}

function LadderRow({ item, hidePct, domain, refValue, refYear, isQualitative }) {
  const conds = orderedConditions(item.conditions);
  const np = obj(item.net_profit);
  const rev = obj(item.revenue);
  const flags = arr(item.flags);
  const hasNumber = !!(np && isNum(np.base));
  const step = hasNumber ? stepFor(np.base) : 1;
  const hasRevenue = !!(rev && isNum(rev.base));
  const hasBody = txt(item.explanation) || txt(item.dominant_factor) || flags.length > 0 || hasRevenue || (hasNumber && domain);
  const positive = hasNumber && isNum(np.pct_base) ? np.pct_base >= 0 : true;
  const hideProfitPct = hidePct || (np && np.pct_hidden === true);
  const hideRevPct = !!(rev && rev.pct_hidden === true);

  const head = (
    <>
      <div className="mt-ladder-name">
        <span className="mt-ladder-scn-name">{item.name}</span>
        {item.badge && <span className="mt-ladder-badge">{item.badge}</span>}
      </div>
      <div className="mt-ladder-conds">
        {conds.map(([k, v]) => (
          <span className="mt-ladder-cond" key={k}><b>{COND_SHORT[k] || k}</b> {txt(v) || "—"}</span>
        ))}
      </div>
      <div className="mt-ladder-verdict">
        <VerdictChip verdict={item.verdict} />
        {headlineReason(item.headline) && <span className="mt-ladder-headline">{headlineReason(item.headline)}</span>}
      </div>
      <div className="mt-ladder-number">
        {hasNumber ? (
          <>
            <span className="mt-ladder-num-val bs-mono">
              ≈{fmtStep(np.base, step)}
              <span className="mt-ladder-num-range"> ({fmtStep(np.low, step)}…{fmtStep(np.high, step)})</span>
            </span>
            <div className="mt-ladder-num-tags">
              {!hideProfitPct && isNum(np.pct_base) && <DeltaTag value={np.pct_base} />}
              <EpistemicTag label="прогноз" />
            </div>
          </>
        ) : item.verdict && isQualitative ? (
          <EpistemicTag label="суждение" />
        ) : null}
      </div>
    </>
  );

  if (!hasBody) {
    return (
      <div className="mt-ladder-row mt-ladder-row-flat">
        <div className="mt-ladder-summary">{head}</div>
      </div>
    );
  }

  return (
    <details className="mt-ladder-row">
      <summary className="mt-ladder-summary">
        {head}
        <span className="mt-ladder-chevron" aria-hidden="true">▾</span>
      </summary>
      <div className="mt-ladder-body">
        {hasRevenue && (
          <div className="mt-ladder-revenue">
            <span className="mt-ladder-revenue-lbl">Выручка (вторично)</span>
            <span className="bs-mono">{fmtN(rev.base, 1)} млрд ₽</span>
            {!hideRevPct && <DeltaTag value={rev.pct_base} />}
            <EpistemicTag label="прогноз" />
          </div>
        )}
        {txt(item.explanation) && <p className="mt-ladder-expl">{item.explanation}</p>}
        {txt(item.dominant_factor) && (
          <div className="mt-scn-dom"><Zap size={12} aria-hidden="true" /> <span>Определяет исход: {item.dominant_factor}</span></div>
        )}
        {flags.length > 0 && (
          <div className="mt-scn-flags">
            {flags.map((fl, i) => <div className="mt-scn-flag" key={i}><AlertTriangle size={12} aria-hidden="true" /> {fl}</div>)}
          </div>
        )}
        {hasNumber && domain && (
          <div className="mt-ladder-scale">
            <div className="mt-ladder-scale-lbl">Чистая прибыль на шкале относительно {refYear || "предыдущего"} года</div>
            <RangeBar low={np.low} base={np.base} high={np.high} domain={domain} refValue={refValue} positive={positive} />
            <div className="mt-scn-metric-range">{fmtN(np.low, 1)} … {fmtN(np.high, 1)} млрд ₽</div>
          </div>
        )}
      </div>
    </details>
  );
}

// Мост базы прибыли — постоянная строка НАД лестницей (рекомендация E-3):
// если устойчивая база сценариев отличается от нормализованной прибыли
// «Финансов», сразу показываем «почему» с разворотом моста, а не заставляем
// искать это в «Как посчитано» внизу. Если база совпадает — короткая строка
// «точка отсчёта», без моста (пример из пилота — SBER, где мост не нужен).
function BaseBridgeCallout({ bf, hc }) {
  // scn.base_fact отсутствует целиком у части качественного варианта (пока нет
  // финансовой модели, напр. GAZP до её построения) — bf в ScenariosBlock уже
  // подстрахован через `|| {}` для других мест блока, но здесь пустой объект
  // ничем не отличается от «данных нет»: без выручки и прибыли строка
  // превращается в прочерки («Точка отсчёта: выручка — млрд ₽») — это ровно
  // тот дефект, который конституция запрещает возвращать («прочерки»), лучше
  // вообще не показывать строку.
  if (!bf || (!isNum(bf.revenue) && !isNum(bf.net_profit))) return null;
  const bv = obj(hc && hc.base_values) || {};
  const scenarioBase = isNum(bf.net_profit_scenario_base) ? bf.net_profit_scenario_base : null;
  const adjusted = isNum(bf.net_profit) ? bf.net_profit : null;
  const reported = isNum(bv.net_profit_reported) ? bv.net_profit_reported : null;
  const needsBridge = scenarioBase != null && adjusted != null && Math.abs(scenarioBase - adjusted) > 0.5;
  const bridge = resolveBridge(bv, hc);
  const hasBridgeBody = bridge.rows.length > 0 || !!bridge.note;

  if (needsBridge) {
    const alt = [];
    if (adjusted != null) alt.push(`не ${fmtN(adjusted, 0)} из «Финансов»`);
    if (reported != null && Math.abs(reported - adjusted) > 0.5) alt.push(`не ${fmtN(reported, 0)} из отчёта`);
    return (
      <details className="mt-details mt-bridge-callout">
        <summary>
          <span>База для сценариев ≈{fmtN(scenarioBase, 0)} млрд ₽{alt.length ? ` — ${alt.join(" и ")}` : ""}</span>
          <span className="mt-bridge-why">почему</span>
        </summary>
        <div className="mt-details-body">
          {hasBridgeBody && <div className="mt-details-sub">Мост к устойчивой базе прибыли</div>}
          <BridgeBody bridge={bridge} />
          {txt(bf.note) && <p>{bf.note}</p>}
        </div>
      </details>
    );
  }

  return (
    <div className="mt-scn-basefact">
      <EpistemicTag label="из источника" />
      <span className="mt-scn-basefact-txt">
        Точка отсчёта — {bf.year || "предыдущий"} год: выручка {fmtN(bf.revenue, 1)} млрд ₽, чистая прибыль {fmtN(adjusted, 1)} млрд ₽
      </span>
      {txt(bf.note) && <p className="mt-scn-basefact-note">{bf.note}</p>}
    </div>
  );
}

function ScenariosBlock({ scenarios: scn, staleness, howComputed }) {
  const rows = arr(scn && scn.rows);
  if (!scn || !rows.length) return null;
  const domain = computeProfitDomain(scn);
  const bf = obj(scn.base_fact) || {};
  const profitBase = isNum(bf.net_profit_scenario_base) ? bf.net_profit_scenario_base : bf.net_profit;
  const isQualitative = scn.variant === "qualitative";
  const interim = obj(scn.interim_fact);
  const asOfSrc = fmtDate(scn.as_of);
  // Разные компании (пилот) пробовали разные имена для одной и той же вводной
  // фразы «это не прогноз роста, а сравнение при неизменном масштабе бизнеса» —
  // берём первую, что нашлась, имя поля ещё не устоялось у источника данных.
  const framingNote = txt(scn.framing) || txt(scn.note) || txt(scn.reading_note) || txt(scn.scope_note);
  const conditionsLegend = txt(scn.conditions_legend);
  const detailsItems = !!(framingNote || conditionsLegend || arr(scn.caveats).length > 0 || arr(scn.extra_assumptions).length > 0);

  // Тонкая или отрицательная база — процент по всей лестнице вводит в
  // заблуждение (контракт 7.1, рекомендация B: |база| < 5% выручки — не
  // показывать проценты; у некоторых компаний это уже приходит явным
  // net_profit.pct_hidden на каждой строке, здесь — общий подстраховочный
  // расчёт на случай, если писатель его не проставил).
  const pctThin = isNum(profitBase) && isNum(bf.revenue) && bf.revenue !== 0
    && Math.abs(profitBase) < 0.05 * Math.abs(bf.revenue);

  const c2026Item = scn.common_2026 ? normalizeC2026(scn.common_2026) : null;
  const orderedRows = [...rows].sort((a, b) => scenarioSortScore(a || {}) - scenarioSortScore(b || {}));

  return (
    <section className="mt-block">
      <h2 className="mt-block-title">Сценарии Банка России</h2>

      {(txt(scn.source) || asOfSrc) && (
        <div className="mt-scn-source">{scn.source}{asOfSrc ? ` · сценарии от ${asOfSrc}` : ""}</div>
      )}

      {txt(scn.held_at_base_note) && (
        <div className="bs-callout mt-held">
          <p><b>Что зафиксировано в расчёте.</b> {scn.held_at_base_note}</p>
        </div>
      )}

      {staleness && txt(staleness.text) && (
        <div className="bs-callout mt-staleness">
          <RefreshCw aria-hidden="true" />
          <div>
            <div className="mt-callout-heading">Поправка на сегодня</div>
            <p>{staleness.text}</p>
          </div>
        </div>
      )}

      <BaseBridgeCallout bf={bf} hc={howComputed} />

      {interim && txt(interim.text) && (
        <div className="mt-fact-note">
          <EpistemicTag label={interim.label || "из источника"} />
          <p>{interim.text}</p>
        </div>
      )}

      <div className="mt-legend">
        {isQualitative
          ? "Вердикт у каждого сценария — направление для компании при условиях сценария против условий 2025 года: суждение, без расчёта выручки и прибыли."
          : "Строки — от худшего исхода к лучшему для компании. Нажмите на сценарий — раскроются объяснение, выручка и диапазон на шкале."}
      </div>

      <div className="mt-ladder">
        {c2026Item && (
          <LadderRow item={c2026Item} hidePct={pctThin} domain={domain} refValue={bf.net_profit} refYear={bf.year} isQualitative={isQualitative} />
        )}
        {orderedRows.map((row, i) => (
          <LadderRow
            item={normalizeRow(row || {})}
            hidePct={pctThin}
            domain={domain}
            refValue={profitBase}
            refYear={bf.year}
            isQualitative={isQualitative}
            key={row?.scenario_id || row?.scenario || i}
          />
        ))}
      </div>

      {txt(scn.numbers_note) && <p className="mt-numbers-note">{scn.numbers_note}</p>}
      <Takeaway text={scn.takeaway} />

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
          </div>
        </details>
      )}
    </section>
  );
}

// --------------------------------------------------------------------------
// Блок 5 — «Как макроэкономика влияет на цену акции» — дизайн-задача
// доработки: строки «у этой компании» видимы сразу (главное), общая теория —
// под один общий разворот «как это работает вообще» (не под каждый механизм),
// единственное число — компактным чипом-сигналом с меткой.
// --------------------------------------------------------------------------
function PriceLinkBlock({ priceLink }) {
  const mechs = arr(priceLink && priceLink.mechanisms);
  if (!mechs.length) return null;
  const number = obj(priceLink.number);
  const hasTheory = mechs.some((m) => txt(m && m.text));
  return (
    <section className="mt-block">
      <h2 className="mt-block-title">Как макроэкономика влияет на цену акции</h2>
      <ol className="mt-steps">
        {mechs.map((m, i) => (
          <li className="mt-step" key={i}>
            <div className="mt-step-num" aria-hidden="true" data-n={i === 2 && mechs.length === 3 ? "1+2" : String(i + 1)} />
            <div className="mt-step-body">
              {txt(m.title) && <h4>{m.title}</h4>}
              {txt(m.company) && <p className="mt-step-company-main">{m.company}</p>}
            </div>
          </li>
        ))}
      </ol>
      {number && txt(number.text) && (
        <div className="mt-signal-chip">
          <EpistemicTag label={number.label || "оценка"} />
          <p className="mt-signal-chip-txt">{number.text}</p>
        </div>
      )}
      {number && txt(number.caveat) && <p className="mt-estimate-caveat">{number.caveat}</p>}
      {hasTheory && (
        <details className="mt-details">
          <summary><span>Как это работает вообще</span></summary>
          <div className="mt-details-body">
            {mechs.map((m, i) => txt(m && m.text) ? <p key={i}><b>{m.title || `Механизм ${i + 1}`}.</b> {m.text}</p> : null)}
          </div>
        </details>
      )}
      <Takeaway text={priceLink.takeaway} />
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
  const bridge = resolveBridge(bv, hc);
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

          {(bridge.rows.length > 0 || bridge.note) && (
            <div>
              <div className="mt-details-sub">Мост к устойчивой базе прибыли</div>
              <BridgeBody bridge={bridge} />
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
      <ScenariosBlock scenarios={data.scenarios} staleness={data.staleness} howComputed={data.how_computed} />
      <PriceLinkBlock priceLink={data.price_link} />
      <HowComputedBlock howComputed={data.how_computed} calc={data.calc} />

      {footerBits.length > 0 && (
        <div className="mt-footer">Basis · {footerBits.join(" · ")}</div>
      )}
    </div>
  );
}

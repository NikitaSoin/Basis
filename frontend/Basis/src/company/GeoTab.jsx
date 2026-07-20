/* Вкладка «Геополитика» (geo-system v0.9) — санкционная/экспортная/владельческая
   экспозиция эмитента к войне и санкциям, переведённая в поправку к оценке
   (премия к WACC / поправка FCF / дисконт мультипликатора — три канала A/B/C,
   ТА ЖЕ визуальная семья, что у InstitutionsTab, потому что оба блока читаются
   как одна поправка и складываются в decision-rail). Данные — geo.json
   (geo-company-analyst) + geo_summary.md (только маркдаун-фолбэк, когда
   geoJson ещё старой схемы — какую схему рендерить решает CompanyCardView по
   наличию gre_profile).

   ВАЖНО про 15 факторов (E1..E15): как и у институтов (S1..S15), ключи НЕ
   означают одну и ту же позицию у разных компаний — кластеризация ниже идёт
   по СМЫСЛУ label (classifyGeo), не по позиции ключа (проверено на LKOH/ROSN/
   NVTK/GAZP — совпадает содержательно на всех четырёх).

   Полярность баллов ОБРАТНАЯ институтам: здесь БОЛЬШЕ = БОЛЬШЕ экспозиции/риска
   (E12 «Госспрос» 5.0 у Газпрома = максимальный риск донора), поэтому scoreColor
   красит высокий балл красным, низкий — зелёным (см. комментарий у scoreColor). */
import React from "react";
import {
  Globe, Cpu, Landmark, Swords, Percent, Eye, ShieldAlert, TrendingUp,
  TrendingDown, Activity, MapPin, Ship, Banknote, Users, Package, Info,
} from "lucide-react";
import { KeyTakeaway } from "../design/textblocks";
import "../styles/geo.css";

/* ── чистка внутренней нотации методики, протекающей в прозу (жалоба владельца
   «c00, экспозиция вчитываешься»): URL-фрагменты источников + debug-коды
   C0x/A0x/§/K-без-словаря/G/имена-файлов. K-коды с известным смыслом заменяем
   человеческим событием (событие несёт достоверность, код — нет). Данные
   geo.json НЕ трогаем — чистим на выводе. См. docs/geo-design-spec §5. ─────── */
const K_EVENTS = {
  K08: "фискальное изъятие вместо дивиденда (прецедент)",
  K09: "принудительная расконвертация расписок (2022)",
  K12: "делистинг / принудительная конвертация",
  K19: "SDN на «Газпром нефть» (01.2025)",
  K22: "политическое обнуление трубопровода (прецедент 2022)",
  K23: "принудительная смена собственника (кейс NIS)",
  K26: "кампания ударов по НПЗ",
  K27: "долговой кризис девелопера при высокой ставке",
  K30: "целевое windfall-изъятие",
};
function stripUrls(s) {
  return s
    .replace(/https?:\/\/\S+/gi, "")
    .replace(/\bwww\.\S+/gi, "")
    .replace(/\b[\w-]+\.(?:ru|com|org|net)\/\S*/gi, "")
    .replace(/\b[a-z0-9]{12,}\.html?\b/gi, "")
    .replace(/\bc0\d\b/gi, "");
}
function stripJargon(s) {
  let out = s;
  out = out.replace(/\bK\d{2}\b/g, (m) => K_EVENTS[m] || "");
  out = out.replace(/\bC\d{2}(?:\s*§\s*\d+[а-яёa-z]?)?/gi, "");
  out = out.replace(/\bA\d{2}(?:\s*§\s*\d+)?/gi, "");
  out = out.replace(/§\s*\d+[а-яёa-z]?/gi, "");
  out = out.replace(/\bsrc_[\w-]+/gi, "");
  out = out.replace(/\b\w+\.json\b/gi, "");
  // E-код в прозе (E14, E14/C03) — внутренний индекс, инвестору не нужен; в
  // 15-факторной сетке E-ключ рендерится напрямую (it.key), не через cleanText.
  out = out.replace(/\bE1[0-5]\b|\bE[1-9]\b/g, "");
  return out;
}

/* ── текст: очистка markdown-эмфазы/ссылок + жаргона + безопасная обрезка (тот
   же приём, что у InstitutionsTab.cleanText/shortText/shortProse) ─────────── */
function cleanText(t) {
  if (!t) return "";
  let s = String(t);
  s = s.replace(/\*\*/g, "").replace(/\*/g, "");
  s = s.replace(/\[[^\]]*\]/g, "");
  s = stripUrls(s);
  s = stripJargon(s);
  s = s.replace(/\s+([,.;:»])/g, "$1").replace(/([«(])\s+/g, "$1");
  s = s.replace(/\(\s*[,;/·]?\s*\)/g, "");
  s = s.replace(/\s{2,}/g, " ").replace(/\s+\/\s+(?=[,.;)])/g, "").replace(/^[\s—–\-,;:./]+/, "").trim();
  return s;
}

/* ── парсинг пары ±% из war_peace_asymmetry для ведущего геочисла рейла/hero
   («Δстоимость S1 ≈ +40…+70%» → «+40…+70%»); фолбэк — одиночное число. ───── */
function extractDelta(text) {
  if (!text) return null;
  const s = String(text);
  const range = s.match(/[+−–-]\s?\d{1,3}\s?[…\-–]{1,3}\s?[+−–-]?\s?\d{1,3}\s?%/);
  if (range) return range[0].replace(/\s/g, "");
  const one = s.match(/[+−–-]?\s?\d{1,3}\s?%/);
  return one ? one[0].replace(/\s/g, "") : null;
}
function maxNum(text) {
  const nums = (String(text || "").match(/\d{1,3}/g) || []).map(Number);
  return nums.length ? Math.max(...nums) : null;
}
function shortText(t, max = 180) {
  const s = cleanText(t);
  if (s.length <= max) return s;
  let cut = s.slice(0, max).replace(/[\s,;:][^\s]*$/, "");
  if ((cut.match(/\(/g) || []).length > (cut.match(/\)/g) || []).length) {
    cut = cut.slice(0, cut.lastIndexOf("(")).replace(/[\s,;:]+$/, "");
  }
  return cut + "…";
}
function shortProse(t, max = 180) {
  const s = cleanText(t);
  const m = s.match(/^(.+?\.)(\s|$)/);
  if (m && m[1].length >= 40 && m[1].length <= max + 45) return m[1];
  return shortText(t, max);
}

const clamp = (x, lo, hi) => Math.max(lo, Math.min(hi, x));
const fmt1 = (x) => (x == null || isNaN(x) ? "—" : Number(x).toLocaleString("ru-RU", { minimumFractionDigits: 1, maximumFractionDigits: 1 }));
const fmtInt = (x) => (x == null || isNaN(x) ? "—" : Math.round(Number(x)).toLocaleString("ru-RU"));

/* Полярность ОБРАТНАЯ институтам: высокий балл = высокая экспозиция/риск → красный. */
const scoreColor = (s) => (s == null ? "var(--ink-3)" : s >= 4 ? "var(--neg)" : s >= 2.5 ? "var(--amber)" : "var(--pos)");

const TAG_KEY = { "факт": "fact", "оценка": "est", "суждение": "judg", fact: "fact", est: "est", judg: "judg", estimate: "est", judgement: "judg" };
const TAG_LABEL = { fact: "факт", est: "оценка", judg: "суждение" };
const Tag = ({ type, className }) => {
  const k = TAG_KEY[type] || "est";
  return <span className={`tag tag-${k}${className ? ` ${className}` : ""}`}>{TAG_LABEL[k]}</span>;
};

const SegBar = ({ score }) => (
  <span className="gsegbar">
    {[1, 2, 3, 4, 5].map((i) => <i key={i} className={score != null && i <= Math.round(score) ? "on" : ""} />)}
  </span>
);

/* ── эпистемический хвост в тексте: экспозиция-поля geo.json часто заканчиваются
   «[ФАКТ: ...]» / «[ОЦЕНКА: M]» / «[ФАКТ/ОЦЕНКА]» — вытаскиваем тег, убираем
   скобку из текста; смешанный факт+оценка честно деградирует в «оценка». ────── */
function splitEpistemic(text) {
  if (!text) return { clean: "", tag: null };
  const s = String(text);
  const m = s.match(/\s*\[([^\]]+)\]\s*$/);
  if (!m) return { clean: s.trim(), tag: null };
  const bracket = m[1];
  const clean = s.slice(0, m.index).trim();
  let tag = null;
  if (/суждение/i.test(bracket)) tag = "judg";
  else if (/оценка/i.test(bracket)) tag = "est";
  else if (/факт/i.test(bracket)) tag = "fact";
  return { clean, tag };
}

/* ── обход объекта в поисках строковых листьев (для фолбэк-парсинга сценарных
   вероятностей из свободного текста verbatim_note/scenario_lean, когда нет
   структурированных scenarios_verbatim — см. ROSN vs LKOH/GAZP/NVTK) ───────── */
function flattenStrings(obj, out = []) {
  if (obj == null) return out;
  if (typeof obj === "string") { out.push(obj); return out; }
  if (Array.isArray(obj)) { obj.forEach((v) => flattenStrings(v, out)); return out; }
  if (typeof obj === "object") { Object.values(obj).forEach((v) => flattenStrings(v, out)); return out; }
  return out;
}
function scenarioProbText(macro, key) {
  const sv = macro?.scenarios_verbatim;
  if (sv && sv[key]) return sv[key];
  const text = flattenStrings(macro).join(" \n ");
  const re = new RegExp(key.replace(/[.*+?^${}()|[\]\\]/g, "\\$&") + "\\s+(\\d+%\\s*6м\\s*/\\s*\\d+%\\s*18м)", "i");
  const m = text.match(re);
  return m ? m[1] : null;
}
function scenarioLeanKey(macro) {
  const text = [macro?.scenario_lean, ...flattenStrings(macro)].join(" ");
  const m = text.match(/S[1-4]_[a-zа-я]+/i);
  return m ? m[0] : null;
}

/* ── смысловая классификация E-фактора → 1 из 5 тематических пакетов (см.
   комментарий в шапке файла). Порядок правил ВАЖЕН: «контрсанкционный»
   содержит подстроку «санкционный» — если проверять общее правило раньше,
   E11 «Контрсанкционный режим» ошибочно попал бы в SANC вместо OWN. ───────── */
const DIM_RULES = [
  ["OWN", /контрсанкцион|перимет|владен|зарубежн[а-яё]*\s*актив|персональн/i],
  ["WAR", /госспрос|военн[а-яё]*\s*эконом|сценарн[а-яё]*\s*асимметр|war.?peace/i],
  ["SANC", /санкционн/i],
  ["TECH", /импортозависим|технологическ/i],
  ["SANC", /географ|логистик|платёжн|ценов[а-яё]*\s*канал/i],
  ["MACRO", /курсов|непрозрачн/i],
];
function classifyGeo(label) {
  const s = String(label || "");
  for (const [bucket, rx] of DIM_RULES) { if (rx.test(s)) return bucket; }
  return "SANC";
}
const CLUSTER_DEFS = [
  { id: "sanc", title: "Санкции и экспортные каналы", icon: Globe, bucket: "SANC" },
  { id: "tech", title: "Импорт и технологии", icon: Cpu, bucket: "TECH" },
  { id: "own", title: "Владение и юрисдикция", icon: Landmark, bucket: "OWN" },
  { id: "war", title: "Война, мир и госспрос", icon: Swords, bucket: "WAR" },
  { id: "macro", title: "Курс и прозрачность", icon: Percent, bucket: "MACRO" },
];

const EXP_LEVEL = {
  high: { t: "высокая гео-экспозиция", c: "var(--neg)", bg: "var(--neg-soft)" },
  moderate: { t: "умеренная гео-экспозиция", c: "var(--amber)", bg: "var(--amber-soft)" },
  low: { t: "низкая гео-экспозиция", c: "var(--pos)", bg: "var(--pos-soft)" },
};

const CONF = {
  L: { t: "низкая", c: "var(--neg)", bg: "var(--neg-soft)" },
  M: { t: "средняя", c: "var(--amber)", bg: "var(--amber-soft)" },
  H: { t: "высокая", c: "var(--pos)", bg: "var(--pos-soft)" },
};

const CHANNEL_DEFS = [
  { key: "A_wacc", eyebrow: "Канал A · Премия к WACC", def: "растёт требуемая доходность инвестора" },
  { key: "B_fcf", eyebrow: "Канал B · Поправка FCF", def: "меньше или жёстче денежный поток акционеру" },
  { key: "C_multiple", eyebrow: "Канал C · Дисконт мультипликатора", def: "рынок платит меньше за рубль прибыли" },
];

const ATTR5_DEFS = [
  { key: "global_cycle", label: "Глобальный цикл" },
  { key: "domestic_macro", label: "Внутренний макро" },
  { key: "competition", label: "Конкуренция" },
  { key: "management", label: "Менеджмент" },
  { key: "direct_geo", label: "Прямая геополитика", acc: true },
];

const SCEN_DEFS = [
  { key: "S1_breakthrough", label: "S1 · Прорыв к миру", c: "var(--pos)" },
  { key: "S2_ceasefire", label: "S2 · Перемирие", c: "var(--accent)" },
  { key: "S3_attrition", label: "S3 · Затяжная война (база)", c: "var(--ink-3)" },
  { key: "S4_escalation", label: "S4 · Эскалация", c: "var(--neg)" },
];
const SCEN_ROW_LABELS = [
  ["volumes", "Объёмы"],
  ["prices_discounts", "Цены/дисконты"],
  ["costs", "Издержки"],
  ["wartime_tax", "Военный налог"],
  ["dividend_capacity", "Дивиденды"],
];
function fcfDirTone(text) {
  const s = String(text || "");
  if (/вниз|отрицат|падени/i.test(s)) return { Icon: TrendingDown, c: "var(--neg)" };
  if (/вверх|восстановлен/i.test(s)) return { Icon: TrendingUp, c: "var(--pos)" };
  return { Icon: Activity, c: "var(--ink-3)" };
}

const EXPOSURE_FIELDS = [
  { key: "assets_production", label: "Активы и производство", icon: MapPin },
  { key: "supply_chains", label: "Цепочки поставок", icon: Package },
  { key: "payment_routes", label: "Платёжные маршруты", icon: Banknote },
  { key: "logistics", label: "Логистика", icon: Ship },
  { key: "ownership_listings", label: "Владение и листинг", icon: Landmark },
  { key: "tech_licenses", label: "Технологии и лицензии", icon: Cpu },
  { key: "people_data", label: "Персональный слой", icon: Users },
];

function severityColor(sev) {
  const s = String(sev || "");
  if (/высок/i.test(s)) return "var(--neg)";
  if (/средн/i.test(s)) return "var(--amber)";
  if (/низк/i.test(s)) return "var(--pos)";
  return "var(--ink-3)";
}

/* ── карта экспозиции: 1 ячейка ───────────────────────────────────────────── */
function ExpCell({ label, Icon, text, sub }) {
  const { clean, tag } = splitEpistemic(text);
  if (!clean) return null;
  return (
    <div className="gexp-cell">
      <div className="gexp-cell-l"><Icon size={12} aria-hidden="true" />{label}{tag && <Tag type={tag} />}</div>
      <div className="gexp-cell-v">{shortText(clean, 260)}</div>
      {sub && sub.map((s, i) => s.v ? (
        <div className="gexp-sub" key={i}>
          <div className="gexp-sub-l">{s.l}</div>
          <div className="gexp-sub-v">{shortText(splitEpistemic(s.v).clean, 220)}</div>
        </div>
      ) : null)}
    </div>
  );
}

/* ── канал трансляции в оценку: несколько пунктов внутри одного канала (в
   отличие от институтов, у гео нет единого числа на канал — несколько
   эффектов с разными величинами) ─────────────────────────────────────────── */
function Channel({ eyebrow, def, items }) {
  return (
    <div className="gchannel">
      <div>
        <div className="gchannel-eyebrow">{eyebrow}</div>
        <div className="gchannel-def">{def}</div>
      </div>
      <div className="gchannel-items">
        {items.length === 0
          ? <div className="gchannel-empty">Не заявлено отдельным эффектом на {new Date().getFullYear()}.</div>
          : items.map((it, i) => (
            <div className="gcitem" key={i}>
              <div className="gcitem-effect">{shortText(it.effect, 110)}</div>
              {it.magnitude && <div className="gcitem-mag">{shortText(it.magnitude, 90)}</div>}
              {it.rationale && <div className="gcitem-rationale">{shortProse(it.rationale, 160)}</div>}
            </div>
          ))}
      </div>
    </div>
  );
}

/* ── кластер из 15-факторной сетки (та же механика, что у InstitutionsTab.Cluster) ── */
function Cluster({ title, Icon, items }) {
  if (!items || !items.length) return null;
  const scored = items.filter((it) => typeof it.score === "number");
  const avg = scored.length ? scored.reduce((s, it) => s + it.score, 0) / scored.length : null;
  const alwaysOpen = items.length <= 1;
  const headInner = (
    <>
      <Icon size={15} className="gcluster-ic" style={{ color: "var(--ink-3)" }} aria-hidden="true" />
      <span className="gcluster-name">{title}</span>
      <SegBar score={avg} />
      <span className="gcluster-val" style={{ "--sc": scoreColor(avg) }}>
        {fmt1(avg)}<s>/5{items.length > 1 ? ` · среднее по ${items.length} факторам` : ""}</s>
      </span>
      {!alwaysOpen && (
        <svg className="chev" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><path d="M6 9l6 6 6-6" /></svg>
      )}
    </>
  );
  const body = (
    <div className="gcluster-body">
      {items.map((it) => (
        <div className="gsub" key={it.key} style={{ "--sc": scoreColor(it.score) }}>
          <div className="gsub-head">
            <span className="gsub-key">{it.key}</span>
            <span className="gsub-name">{it.label}</span>
            <Tag type={it.type} />
            <span className="gsub-score">{it.score ?? "—"}<s>/5</s></span>
          </div>
          {it.rationale && <div className="gsub-why">{cleanText(it.rationale)}</div>}
          {it.trigger && <div className="gsub-trigger"><b>Триггер пересмотра — </b>{shortText(it.trigger, 160)}</div>}
        </div>
      ))}
    </div>
  );
  if (alwaysOpen) {
    return <div className="gcluster"><div className="gcluster-head">{headInner}</div>{body}</div>;
  }
  return <details className="gcluster"><summary className="gcluster-head">{headInner}</summary>{body}</details>;
}

/* ── расхождение inst_overlap: geo_value vs inst_value рядом, явная пометка
   «открытый методологический вопрос» ─────────────────────────────────────── */
function OverlapCard({ d }) {
  return (
    <div className="gdis-overlap">
      <div className="gdis-overlap-h">
        <span className="gdis-factor">{shortText(d.factor, 140)}</span>
        {d.overlap_channel && <span className="gdis-chan">канал {d.overlap_channel}</span>}
      </div>
      <div className="gdis-vs">
        <div className="gdis-vs-cell">
          <div className="gdis-vs-l">Геополитика (этот блок)</div>
          <div className="gdis-vs-v">{shortText(d.geo_value, 150)}</div>
        </div>
        <div className="gdis-vs-sep">vs</div>
        <div className="gdis-vs-cell">
          <div className="gdis-vs-l">Институты{d.inst_field ? ` · ${d.inst_field}` : ""}</div>
          <div className="gdis-vs-v">{shortText(d.inst_value, 150)}</div>
        </div>
      </div>
      {d.resolution && <div className="gdis-resolution">{shortProse(d.resolution, 260)}</div>}
      <span className="gdis-open">открытый методологический вопрос</span>
    </div>
  );
}

/* ── меметр экспозиции: 3 сегмента низк/умер/выс, подсвечен активный ──────── */
function Memeter({ level }) {
  const order = ["low", "moderate", "high"];
  const col = { low: "var(--pos)", moderate: "var(--amber)", high: "var(--neg)" };
  return (
    <span className="gmeme">
      {order.map((k) => (
        <i key={k} style={{ background: level === k ? col[k] : "var(--line-2)" }} />
      ))}
    </span>
  );
}

/* ── 4-сегментный бар вероятностей сценариев S1·S2·S3·S4, лидер заполнен ──── */
function ProbBar({ leaderIdx }) {
  return (
    <span className="gprob">
      {[0, 1, 2, 3].map((i) => (
        <i key={i} style={{ background: i === leaderIdx ? "var(--ink-2)" : "var(--line-2)" }} />
      ))}
    </span>
  );
}

/* ── ведущее геочисло: пара ±% война/мир (зелёный ▲ мир / красный ▼ эскалация) ── */
function WarPeacePair({ peace, esc, compact }) {
  if (!peace && !esc) return null;
  return (
    <div className={`gwp${compact ? " gwp--compact" : ""}`}>
      <div className="gwp-cell">
        <span className="gwp-val up">{peace ? <>▲ {peace}</> : "—"}</span>
        <span className="gwp-lbl">к миру</span>
      </div>
      <div className="gwp-cell">
        <span className="gwp-val down">{esc ? <>▼ {esc}</> : "—"}</span>
        <span className="gwp-lbl">к эскалации</span>
      </div>
    </div>
  );
}

/* ── ГЕО-РЕЙЛ (sticky) — заменяет общую «справедливую цену» на вкладке гео.
   Сквозной якорь смысла при любом скролле (запрос владельца). Ведущее число —
   пара ±% война/мир, НЕ ₽-коридор (решение гендира). См. geo-design-spec §1. ── */
function GeoRail({ verdict, gloss, peace, esc, expInfo, expLevel, leanLabel, leaderIdx,
                   leanProb, directGeo, range, conf, macroDate, sourcesCount, topTrigger,
                   fairBase, onNavigateTab }) {
  return (
    <aside className="geo-rail">
      <div className="geo-rail-card">
        <div className="grl-eyebrow">Гео-оверлей</div>
        {verdict && (
          <div className="grl-verdict">
            {verdict} <Tag type="judg" />
            {gloss && <div className="grl-gloss">{gloss}</div>}
          </div>
        )}

        {(peace || esc) && (
          <div className="grl-sec">
            <div className="grl-label">Куда скосит</div>
            <WarPeacePair peace={peace} esc={esc} />
          </div>
        )}

        {expInfo && (
          <div className="grl-sec">
            <div className="grl-label">Гео-экспозиция</div>
            <div className="grl-exp-val" style={{ color: expInfo.c }}>{expInfo.t.replace(" гео-экспозиция", "")}</div>
            <Memeter level={expLevel} />
          </div>
        )}

        {leanLabel && (
          <div className="grl-sec">
            <div className="grl-label">Крен сценария</div>
            <div className="grl-lean">{leanLabel}</div>
            {leanProb && <div className="grl-lean-p">{leanProb}</div>}
            <ProbBar leaderIdx={leaderIdx} />
          </div>
        )}

        {directGeo != null && (
          <div className="grl-proof">≈{directGeo}% недавних движений — прямой гео-канал</div>
        )}

        {range && (
          <div className="grl-sec grl-range">
            <div className="grl-label">Сценарный разброс (оверлей)</div>
            <div className="grl-range-v">{range}{conf ? ` · уверенность ${conf}` : ""}</div>
            <div className="grl-range-note">разброс-оверлей на оценку, не отдельная цель</div>
          </div>
        )}

        <div className="grl-trust">
          <div className="grl-trust-src">Барометр {macroDate || "—"} · {sourcesCount || "публичные"} {sourcesCount ? "источн." : "источники"}</div>
          {topTrigger && <div className="grl-trust-trig"><span className="grl-dot" aria-hidden="true" />Следим: {topTrigger}</div>}
        </div>

        {fairBase && (
          <button type="button" className="grl-link" onClick={() => onNavigateTab && onNavigateTab("finance")}>
            Модельная цена {fairBase} · гео — поправка к ней →
          </button>
        )}
      </div>
    </aside>
  );
}

export default function GeoTab({ geoJson, geoMd, onNavigateTab, fairBase, upside }) {
  if (!geoJson) return null;

  const macro = geoJson.macro_handoff_cited || {};
  const exposure = geoJson.exposure_map || {};
  const gre = Array.isArray(geoJson.gre_profile) ? geoJson.gre_profile : [];
  const sensitivity = Array.isArray(geoJson.sensitivity_matrix) ? geoJson.sensitivity_matrix : [];
  const attr = geoJson.causal_attribution || {};
  const attrChannels = attr.channels || {};
  const scenarios = Array.isArray(geoJson.scenario_effects) ? geoJson.scenario_effects : [];
  const asym = geoJson.war_peace_asymmetry || {};
  const overhang = geoJson.nonresident_overhang || {};
  const vt = Array.isArray(geoJson.valuation_translation) ? geoJson.valuation_translation : [];
  const dcc = geoJson.double_count_check || {};
  const minRisks = Array.isArray(geoJson.minority_ownership_risk) ? geoJson.minority_ownership_risk : [];
  const conclusion = geoJson.conclusion || {};
  const disagreements = Array.isArray(geoJson.disagreements) ? geoJson.disagreements : [];
  const sources = Array.isArray(geoJson.sources) ? geoJson.sources : [];
  const flags = Array.isArray(geoJson.data_flags) ? geoJson.data_flags : [];
  const asOf = geoJson.as_of;

  const byBucket = { SANC: [], TECH: [], OWN: [], WAR: [], MACRO: [] };
  gre.forEach((e) => { if (e && e.key) (byBucket[classifyGeo(e.label)] || byBucket.SANC).push(e); });

  const scoredAll = gre.filter((e) => typeof e.score === "number");
  const avgExp = scoredAll.length ? scoredAll.reduce((s, e) => s + e.score, 0) / scoredAll.length : null;
  const expLevel = avgExp == null ? null : avgExp >= 3.5 ? "high" : avgExp >= 2.5 ? "moderate" : "low";
  const expInfo = expLevel ? EXP_LEVEL[expLevel] : null;

  const leanKey = scenarioLeanKey(macro);
  const leanLabel = leanKey ? (SCEN_DEFS.find((s) => leanKey.toUpperCase().startsWith(s.key.split("_")[0])) || {}).label : null;

  const channels = CHANNEL_DEFS.map((c) => ({ ...c, items: vt.filter((v) => v.channel === c.key) }));
  const instOwned = vt.filter((v) => v.channel === "inst_owned");

  const confInfo = conclusion.confidence ? CONF[conclusion.confidence] : null;
  const hasRange = conclusion.range_low != null && conclusion.range_high != null;

  const triggers = (Array.isArray(conclusion.key_triggers) && conclusion.key_triggers.length
    ? conclusion.key_triggers
    : minRisks.slice(0, 3).map((r) => `${r.risk}${r.trigger ? ` — ${r.trigger}` : ""}`)
  ).slice(0, 5);

  const hasInstOverlap = disagreements.some((d) => d && typeof d === "object" && d.type === "inst_overlap");

  const attrTotal = ATTR5_DEFS.reduce((s, d) => {
    const raw = attrChannels[d.key];
    if (raw == null) return s;
    const m = String(raw).match(/-?\d+(?:[.,]\d+)?/);
    return s + (m ? parseFloat(m[0].replace(",", ".")) : 0);
  }, 0);

  // ── производные для гео-рейла и hero-вердикта (данные не трогаем, только вывод) ──
  const peaceDelta = extractDelta(asym.peace_gains);
  const escDelta = extractDelta(asym.escalation_losses);
  const pMax = maxNum(asym.peace_gains);
  const eMax = maxNum(asym.escalation_losses);
  const convex = (pMax != null && eMax != null) ? (pMax >= eMax ? "к миру" : "к эскалации") : null;
  const directGeoRaw = attrChannels.direct_geo;
  const directGeo = directGeoRaw != null ? (String(directGeoRaw).match(/\d+/) || [null])[0] : null;
  const leaderIdx = leanKey ? SCEN_DEFS.findIndex((s) => leanKey.toUpperCase().startsWith(s.key.split("_")[0])) : -1;
  const leanKeyFull = leaderIdx >= 0 ? SCEN_DEFS[leaderIdx].key : null;
  const leanProbRaw = leanKeyFull ? scenarioProbText(macro, leanKeyFull) : null;
  // ОТК-персона: «64% / 6 мес» непонятно (вероятность? вес?) → явная подпись
  const leanProbPct = leanProbRaw ? (leanProbRaw.match(/(\d+%)\s*6м/)?.[1] || leanProbRaw.match(/\d+%/)?.[0] || null) : null;
  const leanProb = leanProbPct ? `вероятность ${leanProbPct} · 6 мес` : null;
  const rangeStr = hasRange ? `${fmtInt(conclusion.range_low)}–${fmtInt(conclusion.range_high)} ₽` : null;
  const topTrigger = triggers.length ? shortText(triggers[0], 64) : null;
  const maynik = directGeo != null && +directGeo >= 40
    ? "Геополитика — главный маятник стоимости"
    : "Гео — вторичный фактор для этой бумаги";
  const verdict = `${maynik}${convex ? `. Бумага выпукла ${convex}` : ""}.`;
  // короткая выжимка базового сценария для колонки «БАЗА» в hero
  const baseScen = leanKeyFull ? scenarios.find((x) => x.scenario === leanKeyFull) : null;
  const baseShort = baseScen ? shortText(baseScen.dividend_capacity || baseScen.fcf_direction || "", 64) : null;

  return (
    <div className="geo-layout">
      <div className="geo-body geo-hybrid">
        {/* Слой 1 — HERO-вердикт: сигнал поверх данных (4 слоя чтения) */}
        <div className="ghero">
          <div className="ghero-meta">
            <div className="ghero-meta-l">
              {expInfo && <span className="gexp-badge" style={{ color: expInfo.c, background: expInfo.bg }}>{expInfo.t}</span>}
              {(macro.date || leanLabel) && (
                <span className="ghero-macro">
                  барометр{macro.date ? ` ${macro.date}` : ""}
                  {leanLabel ? <> · крен <b>{leanLabel}</b></> : ""}
                </span>
              )}
            </div>
            {asOf && <span className="ghero-asof">на {asOf}</span>}
          </div>

          <div className="ghero-verdict">{verdict} <Tag type="judg" /></div>

          <div className="ghero-cols">
            <div className="ghero-col">
              <div className="ghero-col-l">К миру</div>
              <div className="ghero-col-v up">{peaceDelta ? <>▲ {peaceDelta}</> : "—"}</div>
            </div>
            <div className="ghero-col">
              <div className="ghero-col-l">К эскалации</div>
              <div className="ghero-col-v down">{escDelta ? <>▼ {escDelta}</> : "—"}</div>
            </div>
            <div className="ghero-col">
              <div className="ghero-col-l">База{leanProbPct ? ` · ${leanProbPct}` : ""}</div>
              <div className="ghero-col-v muted">{leanLabel ? leanLabel.replace(/^S\d\s·\s/, "") : "—"}</div>
              {baseShort && <div className="ghero-col-sub">{baseShort}</div>}
            </div>
            <div className="ghero-col">
              <div className="ghero-col-l">Уверенность</div>
              <div className="ghero-col-v muted" style={confInfo ? { color: confInfo.c } : undefined}>{confInfo ? confInfo.t : "—"}</div>
              <div className="ghero-col-sub">по ₽-коридору</div>
            </div>
          </div>

          {directGeo != null && (
            <div className="ghero-proof">≈{directGeo}% недавних движений — прямой гео-канал (не переоценка рынком).</div>
          )}

          <details className="gdet">
            <summary>
              Как гео переводится в оценку: 3 канала A/B/C{(dcc.within_channels || dcc.vs_macro_rate || dcc.vs_inst || dcc.vs_market_price) ? " + проверка двойного счёта" : ""}
              <svg className="chev" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><path d="M6 9l6 6 6-6" /></svg>
            </summary>
            <div className="gdet-body">
              <div className="gchannels">
                {channels.map((c) => <Channel key={c.key} {...c} />)}
              </div>
              {(dcc.within_channels || dcc.vs_macro_rate || dcc.vs_inst || dcc.vs_market_price || instOwned.length > 0) && (
                <div className="gdcc">
                  {dcc.within_channels && <p><b>Между каналами A/B/C:</b> {shortProse(dcc.within_channels, 260)}</p>}
                  {dcc.vs_macro_rate && <p><b>Против общей ставки/курса:</b> {shortProse(dcc.vs_macro_rate, 260)}</p>}
                  {dcc.vs_inst && <p><b>Против вкладки «Институты»:</b> {shortProse(dcc.vs_inst, 300)}</p>}
                  {dcc.vs_market_price && <p><b>Против рыночной цены:</b> {shortProse(dcc.vs_market_price, 260)}</p>}
                  {instOwned.length > 0 && (
                    <p><b>Не в этих каналах (владение «Институты»):</b> {instOwned.map((v) => shortText(v.effect, 90)).join("; ")}</p>
                  )}
                </div>
              )}
            </div>
          </details>
        </div>

      {/* Слой 2 — анти-сверхатрибуция: что от геополитики, а что от рынка/цикла */}
      {Object.keys(attrChannels).length > 0 && (
        <div className="gcard">
          <h3><Swords size={16} aria-hidden="true" />Что здесь от геополитики, а не от рынка и цикла <Tag type="judg" /></h3>
          <p className="gcard-sub">Причинная атрибуция недавних изменений по 5 каналам{attr.period ? ` · ${attr.period}` : ""} — против соблазна списать всё на войну</p>
          <div className="gattr-bars">
            {ATTR5_DEFS.map((d) => {
              const raw = attrChannels[d.key];
              if (raw == null) return null;
              // числа в этом поле бывают с «~» (ROSN: «~23%») — parseFloat("~23") = NaN,
              // поэтому сперва вырезаем всё, кроме цифр/точки/минуса.
              const numMatch = String(raw).match(/-?\d+(?:[.,]\d+)?/);
              const pct = clamp(numMatch ? parseFloat(numMatch[0].replace(",", ".")) : 0, 0, 100);
              return (
                <div className="gattr-row" key={d.key}>
                  <span className={`gattr-name${d.acc ? " acc" : ""}`}>{d.label}</span>
                  <span className="gattr-track"><span className={`gattr-fill${d.acc ? " acc" : ""}`} style={{ width: `${pct}%` }} /></span>
                  <span className="gattr-pct">{raw}</span>
                </div>
              );
            })}
          </div>
          {attrTotal > 0 && Math.abs(attrTotal - 100) > 8 && (
            <div className="gcard-sub" style={{ marginTop: 8, marginBottom: 0 }}>Сумма каналов ≈ {Math.round(attrTotal)}% (округление методики, не 100% буквально).</div>
          )}
          {attr.conclusion && <div className="gattr-concl">{shortProse(attr.conclusion, 380)}</div>}
        </div>
      )}

      {/* Слой 3.1 — 15 факторов по 5 кластерам */}
      {gre.length > 0 && (
        <div className="gcard">
          <h3>Геополитическая экспозиция по 15 факторам <Tag type="est" />{avgExp != null && <span className="ghmeta">среднее {fmt1(avgExp)}/5</span>}</h3>
          <p className="gcard-sub">Пять тематических групп вместо 15 отдельных строк — раскройте любую</p>
          <div className="gclusters">
            {CLUSTER_DEFS.map((c) => <Cluster key={c.id} title={c.title} Icon={c.icon} items={byBucket[c.bucket]} />)}
          </div>
        </div>
      )}

      {/* Слой 3.2 — чувствительность к осям барометра (G-индексы) */}
      {sensitivity.length > 0 && (
        <div className="gcard">
          <h3><Globe size={16} aria-hidden="true" />Чувствительность к осям барометра <Tag type="est" /></h3>
          <p className="gcard-sub">Какие субиндексы геополитического барометра сильнее всего двигают именно эту бумагу</p>
          <div className="gsens">
            {sensitivity.map((s, i) => (
              <div className="gsens-row" key={i}>
                <div className="gsens-head">
                  <span className="gsens-g">{s.g_index}</span>
                  <span className="gsens-mech">{shortText(s.mechanism, 180)}</span>
                </div>
                {s.elasticity && <div className="gsens-elast">{shortProse(s.elasticity, 200)}</div>}
                {s.source && <div className="gsens-src">{shortText(s.source, 120)}</div>}
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Слой 3.3 — сценарные эффекты (2×2) */}
      {scenarios.length > 0 && (
        <div className="gcard">
          <h3><ShieldAlert size={16} aria-hidden="true" />Что будет с компанией по сценарию <Tag type="judg" /></h3>
          <p className="gcard-sub">Те же 4 сценария барометра, что и в «Обозревателе», в проекции на эту компанию</p>
          <div className="gscen-grid">
            {SCEN_DEFS.map((sd) => {
              const s = scenarios.find((x) => x.scenario === sd.key);
              if (!s) return null;
              const prob = scenarioProbText(macro, sd.key);
              const tone = fcfDirTone(s.fcf_direction);
              return (
                <div className="gscen" key={sd.key} style={{ "--sc": sd.c }}>
                  <div className="gscen-head">
                    <span className="gscen-name">{sd.label}</span>
                    {prob && <span className="gscen-pct" style={{ "--sc": sd.c }}>{prob}</span>}
                  </div>
                  <div className="gscen-rows">
                    {SCEN_ROW_LABELS.map(([k, l]) => s[k] ? (
                      <div className="gscen-row" key={k}><b>{l}</b>{shortText(s[k], 140)}</div>
                    ) : null)}
                  </div>
                  {s.fcf_direction && (
                    <div className="gscen-fcf" style={{ color: tone.c }}>
                      <tone.Icon size={13} aria-hidden="true" />{shortText(s.fcf_direction, 90)}
                    </div>
                  )}
                </div>
              );
            })}
          </div>
        </div>
      )}

      {/* Слой 3.4 — асимметрия война/мир */}
      {(asym.peace_gains || asym.peace_losses || asym.escalation_gains || asym.escalation_losses) && (
        <div className="gcard">
          <h3><Swords size={16} aria-hidden="true" />Асимметрия война/мир <Tag type="judg" /></h3>
          <p className="gcard-sub">Куда бумага выпукла сильнее — к миру или к эскалации</p>
          <div className="gasym">
            <div className="gasym-cell"><div className="gasym-h peace"><TrendingUp size={12} />Мир — выигрыш</div><div className="gasym-txt">{shortProse(asym.peace_gains, 260)}</div></div>
            <div className="gasym-cell"><div className="gasym-h peace"><TrendingDown size={12} />Мир — издержки</div><div className="gasym-txt">{shortProse(asym.peace_losses, 260)}</div></div>
            <div className="gasym-cell"><div className="gasym-h esc"><TrendingUp size={12} />Эскалация — выигрыш</div><div className="gasym-txt">{shortProse(asym.escalation_gains, 260)}</div></div>
            <div className="gasym-cell"><div className="gasym-h esc"><TrendingDown size={12} />Эскалация — издержки</div><div className="gasym-txt">{shortProse(asym.escalation_losses, 260)}</div></div>
          </div>
        </div>
      )}

      {/* Слой 3.5 — карта экспозиции */}
      {Object.keys(exposure).length > 0 && (
        <div className="gcard">
          <h3><MapPin size={16} aria-hidden="true" />Карта экспозиции <Tag type={exposure.revenue?.type || "факт"} /></h3>
          <p className="gcard-sub">Откуда физически приходит выручка и куда физически идут потоки компании</p>
          <div className="gexp-grid">
            {exposure.revenue && (
              <div className="gexp-cell">
                <div className="gexp-cell-l"><Globe size={12} aria-hidden="true" />Выручка: география{exposure.revenue.type && <Tag type={exposure.revenue.type} />}</div>
                <div className="gexp-cell-v">{shortText(splitEpistemic(exposure.revenue.geography).clean, 260)}</div>
                {exposure.revenue.currencies && (
                  <div className="gexp-sub"><div className="gexp-sub-l">Валюты</div><div className="gexp-sub-v">{shortText(splitEpistemic(exposure.revenue.currencies).clean, 220)}</div></div>
                )}
                {exposure.revenue.buyers && (
                  <div className="gexp-sub"><div className="gexp-sub-l">Покупатели и рычаг</div><div className="gexp-sub-v">{shortText(splitEpistemic(exposure.revenue.buyers).clean, 220)}</div></div>
                )}
              </div>
            )}
            {EXPOSURE_FIELDS.map((f) => (
              <ExpCell key={f.key} label={f.label} Icon={f.icon} text={exposure[f.key]} />
            ))}
          </div>
        </div>
      )}

      {/* Слой 3.6 — навес нерезидентов */}
      {(overhang.unlock_scenarios || overhang.price_sensitivity || overhang.frozen_float_pct != null) && (
        <div className="gcard">
          <h3><Users size={16} aria-hidden="true" />Навес нерезидентов <Tag type={overhang.type || "оценка"} /></h3>
          <div className="gover-facts">
            <div className="gexp-cell"><div className="gexp-cell-l">Замороженная доля флоата</div><div className="gexp-cell-v" style={{ fontFamily: "var(--mono)", fontSize: 13 }}>{overhang.frozen_float_pct != null ? `${overhang.frozen_float_pct}%` : "не раскрыто"}</div></div>
          </div>
          {overhang.unlock_scenarios && (
            <div style={{ marginBottom: 10 }}><div className="gexp-sub-l" style={{ marginBottom: 4 }}>Сценарии разблокировки</div><div className="gexp-cell-v">{shortText(overhang.unlock_scenarios, 320)}</div></div>
          )}
          {overhang.price_sensitivity && (
            <div><div className="gexp-sub-l" style={{ marginBottom: 4 }}>Чувствительность цены</div><div className="gexp-cell-v">{shortText(overhang.price_sensitivity, 320)}</div></div>
          )}
        </div>
      )}

      {/* Слой 3.7 — риски владения миноритария */}
      {minRisks.length > 0 && (
        <div className="gcard">
          <h3><ShieldAlert size={16} aria-hidden="true" />Риски владения миноритария</h3>
          <p className="gcard-sub">Что конкретно грозит держателю бумаги — не бизнесу вообще, а миноритарной позиции в нём</p>
          <div className="grisks">
            {minRisks.map((r, i) => (
              <div className="grisk" key={i} style={{ "--sev": severityColor(r.severity) }}>
                <div className="grisk-head">
                  {r.severity && <span className="grisk-sev">{r.severity}</span>}
                  <span className="grisk-name">{shortText(r.risk, 160)}</span>
                  {r.precedent && <span className="grisk-precedent">{r.precedent}</span>}
                </div>
                {r.trigger && <div className="grisk-trigger"><b>Триггер — </b>{shortText(r.trigger, 160)}</div>}
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Слой 3.8 — расхождения (в т.ч. с институтами) */}
      {disagreements.length > 0 && (
        <div className="gcard">
          <h3><Info size={16} aria-hidden="true" />Расхождения с барометром и институтами <Tag type="judg" /></h3>
          <p className="gcard-sub">Открытая методическая прозрачность: где гео и другие блоки спорят о владении фактором риска</p>
          <div className="gdisagree">
            {disagreements.map((d, i) => {
              if (typeof d === "string") return <p className="gdis-prose" key={i}>{shortProse(d, 320)}</p>;
              if (d && d.type === "inst_overlap") return <OverlapCard d={d} key={i} />;
              if (d && d.text) return <p className="gdis-prose" key={i}>{shortProse(d.text, 320)}</p>;
              return null;
            })}
          </div>
          {hasInstOverlap && (
            <div className="gverka-foot">
              {onNavigateTab ? (
                <button type="button" className="gverka-link" onClick={() => onNavigateTab("institutions")}>
                  См. вкладку «Институты» за полным разбором →
                </button>
              ) : (
                <span style={{ fontSize: 12, color: "var(--ink-3)" }}>См. вкладку «Институты» за полным разбором.</span>
              )}
            </div>
          )}
        </div>
      )}

      {/* Слой 4 — за чем следить */}
      {triggers.length > 0 && (
        <div className="gcard">
          <h3><Eye size={16} aria-hidden="true" />За чем следить <Tag type="judg" /></h3>
          <div className="gtrig-list">
            {triggers.map((t, i) => (
              <div className="gtrigger" key={i}>
                <span className="gtrig-n">{String(i + 1).padStart(2, "0")}</span>
                <span className="gtrig-t">{shortText(t, 200)}</span>
              </div>
            ))}
          </div>
        </div>
      )}

      {flags.length > 0 && (
        <KeyTakeaway tone="info" title="Оговорки к данным">
          {shortText(flags[0], 240)}
        </KeyTakeaway>
      )}

      <p className="gend-note">
        Источники — {sources.length || "публичные"} записей: санкционные реестры, биржевые/брокерские данные,
        конфигурация геополитического барометра и сверка с институциональным анализом. Сценарии — суждение,
        не прогноз исхода войны; коридор — сценарно-условный оверлей, не рекомендация.
      </p>
      </div>

      <GeoRail
        verdict={verdict}
        peace={peaceDelta}
        esc={escDelta}
        expInfo={expInfo}
        expLevel={expLevel}
        leanLabel={leanLabel}
        leaderIdx={leaderIdx}
        leanProb={leanProb}
        directGeo={directGeo}
        range={rangeStr}
        conf={confInfo ? confInfo.t : null}
        macroDate={macro.date || asOf}
        sourcesCount={sources.length}
        topTrigger={topTrigger}
        fairBase={fairBase}
        onNavigateTab={onNavigateTab}
      />
    </div>
  );
}

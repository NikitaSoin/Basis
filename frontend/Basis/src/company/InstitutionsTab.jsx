/* Вкладка «Институты» — институциональный/политический риск эмитента (клановый
   патронаж конкретных лиц, риск изъятия государством, санкционный контур),
   переведённый в поправку к оценке (WACC-премия / FCF-haircut / дисконт
   мультипликатора). Данные — institutions.json (institutional-company-analyst,
   схема .claude/agents/institutional-company-analyst.md) + institutions_summary.md
   (используется точечно: финальная фраза-вердикт и фолбэк «Сути» — остальное
   собирается из структурированного JSON, а не из прозы).

   ВАЖНО про 15 субиндексов (S1..S15): ключи НЕ означают одно и то же у разных
   компаний — агент сам присваивает порядок/метки по шкалам методики на каждый
   прогон, фиксирован только S7 = клановая/коалиционная позиция (единственная
   явная привязка в системном промпте агента). Проверено на всех 16 обработанных
   компаниях: группировка по S-КЛЮЧУ (S1,S2,S3,S13→«права собственности» и т.п.)
   даёт правильный результат только для SBER и ломается почти everywhere ещё
   (напр. GAZP: S4/S5 — дивиденды/защита миноритария — попали бы в «внешний
   контур», а S8/S9 — санкции/паттерны изъятия — в «сверку с governance», что
   вводит в заблуждение). Поэтому кластеризация — по СМЫСЛУ label (classifyDim),
   не по позиции ключа; для SBER даёт бит-в-бит тот же состав, что и позиционная
   раскладка (проверено), для остальных — содержательно корректный. */
import React from "react";
import { Scale, Globe, Landmark, Percent, TrendingUp, Eye, ShieldAlert } from "lucide-react";
import { KeyTakeaway } from "../design/textblocks";
import "../styles/institutions.css";

/* ── текст: очистка markdown-эмфазы/ссылок + безопасная обрезка (порт приёма
   GovernanceTab.cleanProse/shortProse — файл самодостаточен, дублирование
   намеренное, как и в соседних *Tab.jsx) ───────────────────────────────────── */
function cleanText(t) {
  if (!t) return "";
  let s = String(t);
  s = s.replace(/\*\*/g, "").replace(/\*/g, "");
  s = s.replace(/\[[^\]]*\]/g, "");
  s = s.replace(/\((?:см\.?|п\.?\s*\d|пункт|раздел\s+[A-EА-Я]|src)[^)]*\)/gi, "");
  s = s.replace(/\b[a-z]+_[a-z_]+\b/g, "");
  s = s.replace(/\(\s*\d+\s*\)/g, "");
  s = s.replace(/\(\s*\)/g, "").replace(/\s+([,.;:»])/g, "$1").replace(/([«(])\s+/g, "$1");
  s = s.replace(/\s{2,}/g, " ").replace(/^[\s—–\-,;:.]+/, "").trim();
  return s;
}
// безопасная обрезка по границе слова (без «сентенс»-эвристики — та ломается на
// числах вида «2,0 п.п.», где точка внутри аббревиатуры читается как конец фразы)
function shortText(t, max = 165) {
  const s = cleanText(t);
  if (s.length <= max) return s;
  let cut = s.slice(0, max).replace(/[\s,;:][^\s]*$/, "");
  if ((cut.match(/\(/g) || []).length > (cut.match(/\)/g) || []).length) {
    cut = cut.slice(0, cut.lastIndexOf("(")).replace(/[\s,;:]+$/, "");
  }
  return cut + "…";
}
// «сентенс»-эвристика (первое цельное предложение, если разумной длины) — только
// там, где текст маловероятно содержит числовые аббревиатуры (см. вызовы ниже)
function shortProse(t, max = 165) {
  const s = cleanText(t);
  const m = s.match(/^(.+?\.)(\s|$)/);
  if (m && m[1].length >= 40 && m[1].length <= max + 45) return m[1];
  return shortText(t, max);
}

const fmt1 = (x) => (x == null || isNaN(x) ? "—" : Number(x).toLocaleString("ru-RU", { minimumFractionDigits: 1, maximumFractionDigits: 1 }));
const fmtPt = (x) => {
  if (x == null || isNaN(x)) return null;
  const r = Math.round(x * 10) / 10;
  return r.toLocaleString("ru-RU", { minimumFractionDigits: Math.abs(r % 1) > 0.001 ? 1 : 0, maximumFractionDigits: 1 });
};
const clamp = (x, lo, hi) => Math.max(lo, Math.min(hi, x));
const scoreColor = (s) => (s == null ? "var(--ink-3)" : s >= 4 ? "var(--pos)" : s >= 3 ? "var(--amber)" : "var(--neg)");

/* ── эпистемический тег: принимает и короткий ключ (fact/est/judg), и русское
   значение поля type ("факт"/"оценка"/"суждение") прямо из JSON — читает РЕАЛЬНОЕ
   значение, не хардкодит. Цвета — схема GovernanceTab (факт = нейтраль, НЕ зелёный:
   у институтов «факт» часто плохая новость, зелёный на плохом факте вводил бы
   в заблуждение). ─────────────────────────────────────────────────────────── */
const TAG_KEY = { "факт": "fact", "оценка": "est", "суждение": "judg", fact: "fact", est: "est", judg: "judg", estimate: "est", judgement: "judg" };
const TAG_LABEL = { fact: "факт", est: "оценка", judg: "суждение" };
const Tag = ({ type, className }) => {
  const k = TAG_KEY[type] || "est";
  return <span className={`tag tag-${k}${className ? ` ${className}` : ""}`}>{TAG_LABEL[k]}</span>;
};

const SegBar = ({ score }) => (
  <span className="isegbar">
    {[1, 2, 3, 4, 5].map((i) => <i key={i} className={score != null && i <= Math.round(score) ? "on" : ""} />)}
  </span>
);

/* ── markdown: разбивка по H2 + извлечение вердикта ───────────────────────── */
function splitH2(md) {
  if (!md) return [];
  const parts = String(md).split(/\n(?=##\s+)/).filter((s) => /^##\s+/.test(s.trim()));
  return parts.map((s) => {
    const m = s.match(/^##\s+(.+)/);
    const heading = (m ? m[1] : "").trim();
    const body = s.replace(/^##\s+.+\n?/, "").trim();
    return { heading, body };
  });
}
// Заголовок финальной секции формулируется РАЗНО у разных компаний (SBER — с тире
// «— одной фразой», GAZP — без тире «одной фразой») — обязателен regex.
function extractVerdict(md) {
  const secs = splitH2(md);
  const final = secs.find((s) => /Итоговая\s+институциональн[а-яё]*\s+поправк/i.test(s.heading));
  if (final && final.body) return shortText(final.body, 220);
  const sut = secs.find((s) => /^суть/i.test(s.heading));
  if (sut && sut.body) return shortProse(sut.body, 180);
  return null;
}

/* ── диапазоны каналов из data_flags[] (честная деградация, если строки нет —
   как у GAZP: показываем одиночную точку с «≈», без выдумывания диапазона) ─── */
function findRangeMatch(text, re) {
  const m = text.match(re);
  if (!m) return null;
  return { loStr: m[1], hiStr: m[2], lo: parseFloat(m[1].replace(",", ".")), hi: parseFloat(m[2].replace(",", ".")) };
}
function parseChannelRanges(flags) {
  const text = (Array.isArray(flags) ? flags : []).join(" \n ");
  return {
    wacc: findRangeMatch(text, /WACC[\s-]*преми[а-яё]*\s+(\d+(?:[.,]\d+)?)\s*[-–]\s*(\d+(?:[.,]\d+)?)\s*п\.?\s*п\.?/i),
    fcf: findRangeMatch(text, /FCF[\s-]*haircut\s+(\d+(?:[.,]\d+)?)\s*[-–]\s*(\d+(?:[.,]\d+)?)\s*%/i),
    mult: findRangeMatch(text, /дисконт[а-яё]*\s+мультипликатора\s+(\d+(?:[.,]\d+)?)\s*[-–]\s*(\d+(?:[.,]\d+)?)\s*%/i),
  };
}

/* ── смысловая классификация субиндекса → 1 из 6 тематических пакетов
   (см. комментарий в шапке файла). Порядок правил ВАЖЕН — первое совпадение
   побеждает (напр. «нерезидент» проверяется раньше общего «ликвидность»,
   иначе «Ликвидность/доступность нерезидентам» осело бы не в тот пакет). ──── */
const DIM_RULES = [
  ["E", /нерезидент/i],
  ["CLAN", /клан[а-яё]*|коалицион|coalition|патрон[а-яё]*/i],
  ["G", /миноритар|акционерн[а-яё]*\s*конфликт|размыти|допэмисс|дивиденд|governance|корпоративн[а-яё]*\s*управлен|раскрыти|связанн[а-яё]*\s*сторон|оферт/i],
  ["F", /фискальн|налог|windfall|ндпи|пошлин|тариф|стратегичност|стратегическ|инструмент|регулятор|электораль|политическ|таргетирован|рент|стоимост[ьи]\s*капитала|финансов[а-яё]*\s*канал/i],
  ["E", /санкц|трансакционн|валютн|swift/i],
  ["P", /собственност|приватизац|верховенств|\bсуд[а-яёa-z]*|деприватизац|hold-up|hold up|специфичност|офшор|иностранн[а-яё]*\s*след|уголовн|вертикал|бенефициар|владен|изъят|преемственност|редомициляц|юрисдикц/i],
  ["T", /дрейф|вектор|траектор/i],
  ["G", /ликвидност|free.?float/i],
];
function classifyDim(label) {
  const s = String(label || "");
  for (const [bucket, rx] of DIM_RULES) { if (rx.test(s)) return bucket; }
  return "P"; // защитный дефолт (не сработал ни разу на 240/240 реальных субиндексов 16 компаний)
}

const CLUSTER_DEFS = [
  { id: "prop", title: "Права собственности и суд", icon: Scale, bucket: "P" },
  { id: "ext", title: "Внешний контур и санкции", icon: Globe, bucket: "E" },
  { id: "clan", title: "Клановая позиция", icon: Landmark, bucket: "CLAN" },
  { id: "fiscal", title: "Фискально-политическая нагрузка", icon: Percent, bucket: "F" },
  { id: "traj", title: "Траектория", icon: TrendingUp, bucket: "T" },
];

/* ── триггеры «за чем следить» — генерируются логикой компонента, не берутся
   текстом из данных (лимит 3 пункта суммарно: патрон max 1 + паттерны max 2,
   дозаполнение из data_flags до общего лимита) ───────────────────────────── */
function buildTriggers(json) {
  const out = [];
  const patron = json?.clan_patronage || {};
  if (["средний", "высокий"].includes(patron.patron_change_risk)) {
    out.push(`Смена патрона — риск ${patron.patron_change_risk}${patron.patron_trend ? `, тренд ${patron.patron_trend}` : ""}.`);
  }
  const patterns = (Array.isArray(json?.expropriation_patterns) ? json.expropriation_patterns : []).filter((p) => p && p.applies).slice(0, 2);
  patterns.forEach((p) => {
    const note = p.note ? shortText(p.note, 80) : "";
    out.push(`${p.pattern}${note ? ` — ${note}` : ""}`);
  });
  const flags = Array.isArray(json?.data_flags) ? json.data_flags : [];
  for (const f of flags) {
    if (out.length >= 3) break;
    if (/сверить|при появлении|не подписан|ожида/i.test(f)) out.push(cleanText(f));
  }
  if (!out.length) {
    out.push(`Существенных триггеров пересмотра на ${json?.as_of || "текущую дату"} не выявлено — вывод опирается на устойчивые структурные факторы.`);
  }
  return out.slice(0, 3);
}

/* ── канал трансляции в оценку (WACC-премия / FCF-haircut / дисконт) ─────── */
function Channel({ eyebrow, def, point, sign, unit, range, note }) {
  const big = range
    ? `${range.loStr}–${range.hiStr} ${unit}`
    : point == null ? "—" : `≈ ${sign}${fmtPt(Math.abs(point))} ${unit}`;
  let dotPos = null;
  if (range && typeof point === "number" && range.hi !== range.lo) {
    dotPos = clamp(((point - range.lo) / (range.hi - range.lo)) * 100, 0, 100);
  }
  return (
    <div className="ichannel">
      <Tag type="est" className="ichannel-tag" />
      <div className="ichannel-eyebrow">{eyebrow}</div>
      {def && <div className="ichannel-def">{def}</div>}
      <div className="ichannel-big">{big}</div>
      {range && (
        <div className="ichannel-track">
          {dotPos != null && <span className="ichannel-dot" style={{ left: `${dotPos}%` }} />}
        </div>
      )}
      {note && <div className="ichannel-note">{shortProse(note, 130)}</div>}
    </div>
  );
}

/* ── кластер из 15-факторной сетки: >1 пункт = аккордеон (закрыт по умолчанию),
   ровно 1 пункт = всегда развёрнут, без chevron/клика ─────────────────────── */
function Cluster({ title, Icon, items }) {
  if (!items || !items.length) return null;
  const scored = items.filter((it) => typeof it.score === "number");
  const avg = scored.length ? scored.reduce((s, it) => s + it.score, 0) / scored.length : null;
  const alwaysOpen = items.length <= 1;
  const headInner = (
    <>
      <Icon size={15} className="icluster-ic" style={{ color: "var(--ink-3)" }} aria-hidden="true" />
      <span className="icluster-name">{title}</span>
      <SegBar score={avg} />
      <span className="icluster-val" style={{ "--sc": scoreColor(avg) }}>
        {fmt1(avg)}<s>/5{items.length > 1 ? ` · среднее по ${items.length} факторам` : ""}</s>
      </span>
      {!alwaysOpen && (
        <svg className="chev" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><path d="M6 9l6 6 6-6" /></svg>
      )}
    </>
  );
  const body = (
    <div className="icluster-body">
      {items.map((it) => (
        <div className="isub" key={it.key} style={{ "--sc": scoreColor(it.score) }}>
          <div className="isub-head">
            <span className="isub-name">{it.label}</span>
            <Tag type={it.type} />
            <span className="isub-score">{it.score ?? "—"}<s>/5</s></span>
          </div>
          {it.rationale && <div className="isub-why">{cleanText(it.rationale)}</div>}
        </div>
      ))}
    </div>
  );
  if (alwaysOpen) {
    return <div className="icluster ialways"><div className="icluster-head">{headInner}</div>{body}</div>;
  }
  return <details className="icluster"><summary className="icluster-head">{headInner}</summary>{body}</details>;
}

export default function InstitutionsTab({ instJson, instMd, onNavigateTab }) {
  if (!instJson && !instMd) return null;

  const patron = instJson?.clan_patronage || {};
  const attr = instJson?.attribution_5_channel || {};
  const patterns = Array.isArray(instJson?.expropriation_patterns) ? instJson.expropriation_patterns : [];
  const activePatterns = patterns.filter((p) => p && p.applies);
  const cases = Array.isArray(instJson?.similar_cases) ? instJson.similar_cases : [];
  const vt = instJson?.valuation_translation || {};
  const subindices = Array.isArray(instJson?.iri_scoring?.subindices) ? instJson.iri_scoring.subindices : [];
  const overall = instJson?.iri_scoring?.overall;
  const asOf = instJson?.as_of;

  const byBucket = { P: [], E: [], CLAN: [], F: [], G: [], T: [] };
  subindices.forEach((s) => { if (s && s.key) (byBucket[classifyDim(s.label)] || byBucket.P).push(s); });

  const ranges = parseChannelRanges(instJson?.data_flags);
  const channels = [
    { key: "wacc", eyebrow: "Канал 1 · Премия к WACC", def: "растёт требуемая доходность инвестора", point: vt.wacc_premium_pp, sign: "+", unit: "п.п.", note: vt.wacc_premium_note, range: ranges.wacc },
    { key: "fcf", eyebrow: "Канал 2 · Вычет из FCF", def: "меньше живых денег достаётся акционеру", point: vt.fcf_haircut_pct, sign: "−", unit: "%", note: vt.fcf_haircut_note, range: ranges.fcf },
    { key: "mult", eyebrow: "Канал 3 · Дисконт мультипликатора", def: "рынок платит меньше за рубль прибыли", point: vt.multiple_discount_pct, sign: "−", unit: "%", note: vt.multiple_discount_note, range: ranges.mult },
  ];
  const hasChannels = channels.some((c) => c.point != null || c.range);
  const hasCalcDetail = vt.wacc_premium_note || vt.fcf_haircut_note || vt.multiple_discount_note || vt.anti_double_count_check;

  const ATTR5 = [
    { key: "macro_cycle", label: "Макро/цикл", acc: false },
    { key: "sector_shock", label: "Отраслевой шок", acc: false },
    { key: "institutional", label: "Институциональный", acc: true },
    { key: "idiosyncratic", label: "Идиосинкразия", acc: false },
    { key: "financial", label: "Финансовый", acc: false },
  ].filter((c) => attr[c.key]);

  const verdict = extractVerdict(instMd);
  const triggers = buildTriggers(instJson);

  return (
    <div className="inst-hybrid">
      {/* Слой 0 — рамка */}
      <p className="ifr-frame">
        Поправка на институциональный риск — перевод политико-собственнических факторов в требуемую
        доходность. Не прогноз изъятия и не рекомендация. Клановые атрибуции — версии по расследованиям,
        не приговор.
      </p>

      {/* Слой 1 — hero: вердикт + 3 канала трансляции в оценку */}
      <div className="ihero">
        <div className="ihero-meta">
          <div className="ihero-meta-l">
            {/* резерв: профиль-чип компании (1 из 6 категорий методики — госкомпания-фаворит/
                частная-лояльная/частная-нейтральная/частная-«токсичная»/иностранная/силовая-кэптивная).
                Поля с готовой категорией в institutions.json пока нет — эвристикой не вычисляем
                (по требованию), просто резервируем место в разметке. */}
            {patron.patron && <span className="ihero-patron"><b>Патрон:</b> {shortText(patron.patron, 80)}</span>}
          </div>
          {asOf && <span className="ihero-asof">на {asOf}</span>}
        </div>

        {verdict && <p className="ihero-verdict">{verdict}</p>}

        {attr.note && (
          <div className="ihero-note">
            <KeyTakeaway tone="info">{cleanText(attr.note)}</KeyTakeaway>
          </div>
        )}

        {hasChannels && (
          <div className="ichannels">
            {channels.map((c) => <Channel key={c.key} {...c} />)}
          </div>
        )}

        {hasCalcDetail && (
          <details className="idet">
            <summary>
              Как считали три канала
              <svg className="chev" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><path d="M6 9l6 6 6-6" /></svg>
            </summary>
            <div className="idet-body">
              {vt.wacc_premium_note && <p><b>Канал 1 — WACC:</b> {cleanText(vt.wacc_premium_note)}</p>}
              {vt.fcf_haircut_note && <p><b>Канал 2 — FCF:</b> {cleanText(vt.fcf_haircut_note)}</p>}
              {vt.multiple_discount_note && <p><b>Канал 3 — мультипликатор:</b> {cleanText(vt.multiple_discount_note)}</p>}
              {vt.anti_double_count_check && <p className="idet-check"><b>Проверка анти-двойного счёта:</b> {cleanText(vt.anti_double_count_check)}</p>}
            </div>
          </details>
        )}
      </div>

      {/* Слой 2 — что здесь от институтов, а не от рынка и цикла (итог-фраза
          attr.note переехала в hero, сразу после вердикта — честный контекст
          должен встречать читателя ДО трёх чисел, не после) */}
      {ATTR5.length > 0 && (
        <div className="icard">
          <h3><Scale size={16} aria-hidden="true" />Что здесь от институтов, а не от рынка и цикла <Tag type="judg" /></h3>
          <p className="icard-sub">Причинная атрибуция по 5 каналам — не всё, что случилось с бумагой, объясняется институтами</p>
          <div className="iattr5">
            {ATTR5.map((c) => (
              <div className={`iof${c.acc ? " acc" : ""}`} key={c.key}>
                <div className="iofl">{c.label}</div>
                <div className="iofv">{shortProse(attr[c.key], 100)}</div>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Слой 3 — доказательства */}
      {subindices.length > 0 && (
        <div className="icard">
          <h3>Институциональный риск по 15 факторам <Tag type="est" /><span className="iri-badge">IRI {fmt1(overall)}<s>/5</s></span></h3>
          <p className="icard-sub">Пять тематических групп вместо 15 отдельных строк — раскройте любую</p>
          <div className="iclusters">
            {CLUSTER_DEFS.map((c) => <Cluster key={c.id} title={c.title} Icon={c.icon} items={byBucket[c.bucket]} />)}
          </div>
        </div>
      )}

      {(patron.patron || patron.patron_position) && (
        <div className="icard">
          <h3><Globe size={16} aria-hidden="true" />Клановый патронаж <Tag type={patron.type || "оценка"} /></h3>
          <div className="ifacts4">
            <div className="iof"><div className="iofl">Патрон</div><div className="iofv b">{patron.patron || "—"}</div></div>
            <div className="iof"><div className="iofl">Позиция</div><div className="iofv">{patron.patron_position || "—"}</div></div>
            <div className="iof"><div className="iofl">Тренд</div><div className="iofv">{patron.patron_trend || "—"}</div></div>
            <div className="iof"><div className="iofl">Риск смены патрона</div><div className="iofv">{patron.patron_change_risk || "—"}</div></div>
          </div>
          {Array.isArray(patron.clan_conflicts) && patron.clan_conflicts.length > 0 && (
            <div className="iconflicts">
              <div className="iconflicts-h">Клановые конфликты</div>
              <ul>{patron.clan_conflicts.map((c, i) => <li key={i}>{cleanText(c)}</li>)}</ul>
              {patron.source && <div className="iprov">— версия по данным {patron.source}, не приговор</div>}
            </div>
          )}
        </div>
      )}

      {patterns.length > 0 && (
        <div className="icard">
          <h3><ShieldAlert size={16} aria-hidden="true" />Паттерны риска изъятия <span className="ihmeta">{activePatterns.length} из {patterns.length} применяется</span></h3>
          <div className="ipatterns">
            {patterns.map((p, i) => (
              <div className="ipattern" key={i} style={{ "--sev": p.applies ? "var(--neg)" : "var(--line-2)" }}>
                <div className="ipattern-head">
                  <span className={`ipattern-pill${p.applies ? " on" : ""}`}>{p.applies ? "применяется" : "не применяется"}</span>
                  <span className="ipattern-name">{p.pattern}</span>
                  <Tag type={p.type} />
                </div>
                {p.note && <div className="ipattern-note">{cleanText(p.note)}</div>}
              </div>
            ))}
          </div>
        </div>
      )}

      {cases.length > 0 && (
        <div className="icard">
          <h3>Похожие кейсы <Tag type="judg" /></h3>
          <div className="icases">
            {cases.map((c, i) => (
              <div className="icase" key={i}>
                <span className="icase-name">{c.case}</span>{c.similarity ? <> — {cleanText(c.similarity)}</> : null}
                {c.source && <span className="iprov-inline"> — {c.source}</span>}
              </div>
            ))}
          </div>
        </div>
      )}

      {byBucket.G.length > 0 && (
        <div className="isverka">
          <div className="isverka-h">Сверка с корп. управлением</div>
          <div className="isverka-rows">
            {byBucket.G.map((it) => (
              <div className="isverka-row" key={it.key}>
                <span className="isverka-name">{it.label}</span>
                <span className="isverka-score" style={{ color: scoreColor(it.score) }}>{it.score ?? "—"}<s>/5</s></span>
                <span className="isverka-why">{it.rationale ? shortProse(it.rationale, 90) : ""}</span>
              </div>
            ))}
          </div>
          <div className="isverka-foot">
            {onNavigateTab ? (
              <button type="button" className="isverka-link" onClick={() => onNavigateTab("governance")}>
                См. вкладку «Корп. управление» за полным разбором →
              </button>
            ) : (
              <span className="isverka-link-static">См. вкладку «Корп. управление» за полным разбором.</span>
            )}
          </div>
        </div>
      )}

      {/* Слой 4 — за чем следить */}
      <div className="icard">
        <h3><Eye size={16} aria-hidden="true" />За чем следить <Tag type="judg" /></h3>
        <div className="itrig-list">
          {triggers.map((t, i) => (
            <div className="itrigger" key={i}>
              <span className="itrig-n">{String(i + 1).padStart(2, "0")}</span>
              <span className="itrig-t">{t}</span>
            </div>
          ))}
        </div>
      </div>

      <p className="iend-note">
        Источники — публичные данные, судебные акты и журналистские расследования; клановые атрибуции
        помечены «суждение».
      </p>
    </div>
  );
}

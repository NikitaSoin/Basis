/* Вкладка «Корп. управление» — полный порт прототипа governance-g1.html
   (docs/Corporate_Management.zip). Двухколоночный макет: основной поток (вердикт-герой,
   «из чего складывается балл», структура владения, дивиденды политика↔практика,
   прецеденты, качество/риски, связанные стороны) + правый рейл «как считается балл» и
   «влияние на оценку». Всё из governance.json; балл и премия к ставке — из scoring +
   governance_discount.premium_to_wacc_pp_computed (считает бэк по конфигу). Служебные
   поля (data_flags, ключи факторов, source_ref) в UI не выводятся. */
import React from "react";
import "../styles/governance.css";

const fmt1 = (x) => (x == null || isNaN(x) ? "—" : Number(x).toLocaleString("ru-RU", { minimumFractionDigits: 1, maximumFractionDigits: 1 }));
const numfmt = (x, d = 0) => (x == null || isNaN(x) ? "—" : Number(x).toLocaleString("ru-RU", { minimumFractionDigits: d, maximumFractionDigits: d }));
const scoreColor = (s) => (s == null ? "var(--ink-3)" : s >= 4 ? "var(--pos)" : s >= 3 ? "var(--amber)" : "var(--neg)");

// Чистка аналитической прозы для UI: убрать код-токены/ссылки/служебные скобки и
// англоязычный жаргон, который читателю-инвестору непонятен (заменить на русский).
const RUS = [
  [/\btunneling\b/gi, "вывод средств"], [/\bsqueeze[\s-]?out\b/gi, "принудительный выкуп"],
  [/\btag[\s-]?along\b/gi, "право присоединения"], [/\bfree[\s-]?float\b/gi, "акции в обращении"],
  [/\bbuy[\s-]?back\b/gi, "обратный выкуп"], [/\bpayout\b/gi, "доля выплат"],
  [/\bEn\+/g, "Эн+"], [/\barms[\s-]?length\b/gi, "рыночные условия"],
];
function cleanProse(t) {
  if (!t) return "";
  let s = String(t);
  s = s.replace(/\[[^\]]*\]/g, "");                                        // [src_1], [ref]
  s = s.replace(/\((?:см\.?|п\.?\s*\d|пункт|раздел\s+[A-EА-Я]|src|по\s+рубрике)[^)]*\)/gi, ""); // внутр. ссылки
  s = s.replace(/\([^)]*\.json[^)]*\)/gi, "");                             // (governance.json …)
  s = s.replace(/\b[a-z]+_[a-z_]+\b/g, "");                                // snake_case код-токены
  s = s.replace(/\(\s*\d+\s*\)/g, "");                                     // (1) (2) перечисления
  RUS.forEach(([re, to]) => { s = s.replace(re, to); });
  s = s.replace(/\(\s*\)/g, "").replace(/\s+([,.;:»])/g, "$1").replace(/([«(])\s+/g, "$1");
  s = s.replace(/\s{2,}/g, " ").replace(/^[\s—–\-,;:.]+/, "").trim();
  return s;
}
// краткая версия (для героя/пояснений): по возможности — первое цельное предложение,
// иначе обрезаем по слову с многоточием (без «висящей» открытой скобки).
function shortProse(t, max = 165) {
  const s = cleanProse(t);
  const m = s.match(/^(.+?\.)(\s|$)/);
  if (m && m[1].length >= 40 && m[1].length <= max + 45) return m[1];
  if (s.length <= max) return s;
  let cut = s.slice(0, max).replace(/[\s,;:][^\s]*$/, "");
  if ((cut.match(/\(/g) || []).length > (cut.match(/\)/g) || []).length) cut = cut.slice(0, cut.lastIndexOf("(")).replace(/[\s,;:]+$/, "");
  return cut + "…";
}

const FLAG = {
  good: { c: "var(--pos)", t: "надёжное управление" },
  mixed: { c: "var(--amber)", t: "смешанное управление" },
  weak: { c: "var(--neg)", t: "слабое управление" },
  insufficient_data: { c: "var(--ink-3)", t: "мало данных" },
};
const TYPE_COLOR = {
  state: "var(--cat-6)", strategic: "var(--cat-5)", founder: "var(--cat-1)",
  institutional: "var(--cat-2)", treasury: "var(--ink-3)", free_float: "var(--cat-3)",
};
const TYPE_LABEL = {
  state: "государство", strategic: "стратегический акционер", founder: "основатель",
  institutional: "институциональный инвестор", treasury: "квазиказначейский пакет", free_float: "free float · розница и институционалы",
};
const SEV = { high: { c: "var(--neg)", t: "высокий" }, medium: { c: "var(--amber)", t: "средний" }, low: { c: "var(--ink-3)", t: "низкий" } };
const IMPACT = { negative: { cls: "neg", t: "негатив" }, neutral: { cls: "neu", t: "нейтраль" }, positive: { cls: "pos", t: "позитив" } };

const Tag = ({ k }) => {
  const m = { fact: "факт", est: "оценка", judg: "суждение" };
  return <span className={`tag tag-${k}`}>{m[k] || k}</span>;
};

const SegBar = ({ score, norm, dx }) => (
  <span className={dx ? "dxbar" : "dbar"}>
    {!dx && norm != null && <span className="normk" style={{ left: `${(norm / 5) * 100}%` }} />}
    {[1, 2, 3, 4, 5].map((i) => <i key={i} className={i <= Math.round(score) ? "on" : ""} />)}
  </span>
);

/* столбиковый график дивидендов (DPS по годам) */
function DivChart({ history }) {
  const rows = (history || []).filter((h) => h && h.year != null);
  if (rows.length < 2) return null;
  const vals = rows.map((h) => (typeof h.dps === "number" ? h.dps : 0));
  const w = 100 * rows.length, h = 120, mx = Math.max(...vals, 1);
  const pB = 20, pT = 18, plotH = h - pT - pB, slot = w / rows.length, bw = slot * 0.52;
  return (
    <svg viewBox={`0 0 ${w} ${h}`} width="100%" style={{ display: "block", overflow: "visible" }}>
      {rows.map((r, i) => {
        const v = typeof r.dps === "number" ? r.dps : 0;
        const paid = r.paid !== false && v > 0;
        const bh = Math.max((v / mx) * plotH, paid ? 3 : 0);
        const x = i * slot + slot / 2, y = h - pB - bh;
        const col = paid ? (r.source_of_payout === "debt" || r.source_of_payout === "mixed" ? "var(--amber)" : "var(--accent)") : "var(--line-2)";
        return (
          <g key={i}>
            {paid ? <rect x={(x - bw / 2).toFixed(1)} y={y.toFixed(1)} width={bw.toFixed(1)} height={bh.toFixed(1)} rx="2" fill={col} />
              : <text className="bc-v" x={x} y={h - pB - 4} textAnchor="middle" style={{ fill: "var(--ink-3)" }}>0</text>}
            {paid && <text className="bc-v" x={x} y={(y - 4).toFixed(1)} textAnchor="middle">{numfmt(v, v >= 100 ? 0 : v >= 10 ? 1 : 2)}</text>}
            <text className="bc-y" x={x} y={h - 5} textAnchor="middle">{r.year}</text>
          </g>
        );
      })}
    </svg>
  );
}

export default function GovernanceTab({ gov, finJson }) {
  if (!gov) return null;
  const meta = gov.meta || {};
  const own = gov.ownership || {};
  const div = gov.dividends || {};
  const gq = gov.governance_quality || {};
  const risks = gov.governance_risks || [];
  const sc = gov.scoring || {};
  const gd = gov.governance_discount || {};
  const sources = Array.isArray(gov.sources) ? gov.sources : [];

  const flag = FLAG[meta.governance_quality_flag] || { c: "var(--ink-3)", t: meta.governance_quality_flag || "—" };
  const scFactors = Array.isArray(sc.factors) ? sc.factors.filter((f) => typeof f.score === "number") : [];
  const overall = typeof sc.overall_score === "number" ? sc.overall_score : null;
  const normOverall = typeof sc.sector_norm_overall === "number" ? sc.sector_norm_overall : null;
  const redFlags = (sc.red_flags || []).filter((f) => f && f.active);
  const premium = typeof gd.premium_to_wacc_pp_computed === "number" ? gd.premium_to_wacc_pp_computed : null;
  const hasScore = overall != null && scFactors.length >= 4;

  const shareholders = (own.shareholders || []).filter((s) => typeof s.stake_pct === "number" && s.stake_pct > 0).sort((a, b) => b.stake_pct - a.stake_pct);
  const shareClasses = own.share_classes || [];
  const mtreat = gq.minority_treatment || [];
  const board = gq.board || {};
  const rps = gq.related_party_signal || meta.related_party_signal || gov.related_party_signal || null; // субагенты кладут сигнал в governance_quality / meta / корень
  const fairBase = finJson && finJson.valuation && finJson.valuation.fair_value_range ? finJson.valuation.fair_value_range.base : null;
  const conf = ({ high: "высокая", medium: "средняя", low: "низкая" })[meta.data_quality] || "средняя";
  const divNote = div.policy_vs_practice || div.regularity_note;
  const divBad = /наруша|пропуск|нерегуляр|из долга|controller_choice|не\s*платил/i.test(String(divNote || ""));

  return (
    <div className="gov-hybrid" style={hasScore ? { "--gv": flag.c, "--gv-soft": `color-mix(in srgb, ${flag.c} 13%, transparent)` } : undefined}>
      <div className="gov-layout">
        <div className="dash">
          {/* 1. ВЕРДИКТ-ГЕРОЙ */}
          {hasScore && (
            <div className="gverdict">
              <div className="gv-top">
                <div className="gv-score"><b>{fmt1(overall)}</b><s>из 5</s></div>
                <div className="gv-txt">
                  <span className="gv-badge">{flag.t}</span>
                  {meta.governance_quality_note && <div className="gv-h">{shortProse(meta.governance_quality_note, 180)}</div>}
                  {gd.rationale && <div className="gv-s">{shortProse(gd.rationale, 150)}</div>}
                </div>
              </div>
              {premium != null && (
                <div className="gv-link">
                  <span className="tag tag-judg">суждение · связь с оценкой</span>
                  <div className="gv-chain">
                    <span className={`n ${overall < 3 ? "bad" : overall >= 4 ? "good" : ""}`}>{flag.t}</span><span className="ar">→</span>
                    <span className="n">{redFlags.length ? "красный флаг → " : ""}премия <b>+{fmt1(premium)} п.п.</b> в ставке</span><span className="ar">→</span>
                    <span className="n bad">справедливый потолок ниже</span>
                  </div>
                </div>
              )}
              <div className="dims">
                {scFactors.map((f, i) => (
                  <div className="dim" key={i} style={{ "--score": scoreColor(f.score) }}>
                    <div className="dn">{f.label}</div>
                    <SegBar score={f.score} norm={f.sector_norm} />
                    <div className="dv">{f.score}<s>норма {f.sector_norm ?? "—"}</s></div>
                  </div>
                ))}
              </div>
              <div className="dims-leg"><span><i className="nm" />норма сектора (медиана сопоставимых эмитентов)</span></div>
              {redFlags.length > 0 && (
                <div className="gflags">
                  <div className="fh">Красные флаги</div>
                  {redFlags.map((f, i) => <div className="fr" key={i}>{cleanProse(f.description || f.label)}</div>)}
                </div>
              )}
            </div>
          )}

          {/* 1b. ИЗ ЧЕГО СКЛАДЫВАЕТСЯ БАЛЛ */}
          {hasScore && (
            <div className="gcard">
              <h3>Из чего складывается балл <Tag k="judg" /><span className="hmeta">обоснование каждой оценки</span></h3>
              <p className="sub">Каждый аспект — с причиной оценки. Веса и вклад в итог — в панели справа.</p>
              <div className="dimx">
                {scFactors.map((f, i) => (
                  <div className="dxrow" key={i} style={{ "--sc": scoreColor(f.score) }}>
                    <div className="dxhead">
                      <span className="dxname">{f.label}</span>
                      <span className="dxw">вклад {Math.round((f.weight || 0) * 100)}%</span>
                      <SegBar score={f.score} dx />
                      <span className="dxval">{f.score}<s>/5</s></span>
                    </div>
                    {f.rationale && <div className="dxwhy"><b>Почему {f.score}:</b> {shortProse(f.rationale, 210)}</div>}
                  </div>
                ))}
              </div>
            </div>
          )}

          {/* 2. СТРУКТУРА ВЛАДЕНИЯ */}
          {shareholders.length > 0 && (
            <div className="gcard">
              <h3>Структура владения <Tag k="fact" /><span className="hmeta">цвет = тип акционера</span></h3>
              {own.controlling_shareholder && <p className="sub">{own.controlling_shareholder}</p>}
              <div className="own-bar">
                {shareholders.map((s, i) => <div className="s" key={i} style={{ flex: s.stake_pct, background: TYPE_COLOR[s.type] || "var(--ink-3)" }}>{s.stake_pct >= 7 ? `${numfmt(s.stake_pct, s.stake_pct % 1 ? 1 : 0)}%` : ""}</div>)}
              </div>
              <div className="own-list">
                {shareholders.map((s, i) => (
                  <div className="own-row" key={i}>
                    <span className="dot" style={{ background: TYPE_COLOR[s.type] || "var(--ink-3)" }} />
                    <div><div className="on">{s.name}</div><div className="od">{TYPE_LABEL[s.type] || s.type || ""}{s.is_controlling ? " · контролирующий" : ""}</div></div>
                    <span className="ov">{numfmt(s.stake_pct, s.stake_pct % 1 ? 1 : 0)} %</span>
                  </div>
                ))}
              </div>
              <div className="kvbox">
                {own.controlling_shareholder && <div className="kvrow"><span className="k">Контролирующий акционер</span><span className="v">{own.controlling_shareholder}</span></div>}
                {own.ultimate_beneficiary && <div className="kvrow"><span className="k">Конечный бенефициар</span><span className="v">{own.ultimate_beneficiary}</span></div>}
                {own.control_type && <div className="kvrow"><span className="k">Тип контроля</span><span className="v">{({ state: "государственный", private: "частный", founder: "контроль основателя", dispersed: "распылённый" })[own.control_type] || own.control_type}</span></div>}
                {typeof own.free_float_pct === "number" && <div className="kvrow"><span className="k">Free float</span><span className="v">{numfmt(own.free_float_pct, own.free_float_pct % 1 ? 1 : 0)} %</span></div>}
              </div>
              {shareClasses.length > 0 && (<>
                <h3 style={{ marginTop: 22 }}>Классы акций и права <Tag k="fact" /></h3>
                <div className="shclass">
                  {shareClasses.map((c, i) => {
                    const pref = /привилег/i.test(c.class || "");
                    return <div className="shc" key={i}><div className="sct">{c.ticker || c.class}<span className="sctag" style={pref ? { background: "var(--pos-soft)", color: "var(--pos)" } : undefined}>{pref ? "привилег." : "обыкновенная"}</span></div>{c.rights_note && <div className="scd">{c.rights_note}</div>}</div>;
                  })}
                </div>
              </>)}
              {own.vote_capital_gap_note && <p className="sub" style={{ margin: "12px 0 0" }}>{own.vote_capital_gap_note}</p>}
            </div>
          )}

          {/* 3. ДИВИДЕНДЫ — политика vs практика */}
          {(div.history || []).length > 0 && (
            <div className="gcard">
              <h3>Дивиденды — политика vs практика <Tag k="fact" /><span className="hmeta">DPS, {div.history[0]?.currency || "₽"}</span></h3>
              {div.policy_text && <p className="sub">{div.policy_text}</p>}
              <DivChart history={div.history} />
              <div className="dch-cap">DPS по годам · {div.history[0]?.year}–{div.history[div.history.length - 1]?.year} · приглушённый/0 — без выплаты</div>
              {divNote && <div className={`kvbox ${divBad ? "bad" : ""}`} style={{ marginTop: 16 }}><div style={{ fontSize: 12.5, lineHeight: 1.55, color: "var(--ink-2)" }}><b style={{ color: "var(--ink)" }}>Вывод:</b> {cleanProse(divNote)}</div></div>}
            </div>
          )}

          {/* 4. ПРЕЦЕДЕНТЫ */}
          {mtreat.length > 0 && (
            <div className="gcard">
              <h3>Прецеденты по миноритариям <Tag k="fact" /></h3>
              <p className="sub">История отношения контролирующего акционера к правам миноритариев</p>
              <div className="prec">
                {mtreat.map((m, i) => {
                  const imp = IMPACT[m.impact] || IMPACT.neutral;
                  return (
                    <div className="pcard" key={i}>
                      <span className="py">{m.period || "—"}</span>
                      <div><div className="pt">{cleanProse(m.event)}</div>{m.description && <div className="pd">{cleanProse(m.description)}{m.implication ? ` — ${cleanProse(m.implication)}` : ""}</div>}</div>
                      <span className={`pimp ${imp.cls}`}>{imp.t}</span>
                    </div>
                  );
                })}
              </div>
            </div>
          )}

          {/* 5. КАЧЕСТВО И РИСКИ */}
          {(risks.length > 0 || board.size != null) && (
            <div className="gcard">
              <h3>Качество управления и риски <Tag k="judg" /></h3>
              <p className="sub">Что именно повышает вес рисков для миноритария</p>
              <div className="minifacts">
                {board.size != null && <div className="mf"><b>{board.size}</b>членов СД</div>}
                {board.independent_count != null && <div className="mf"><b>{board.independent_count}</b>независимых директоров</div>}
                {gq.transparency && <div className="mf"><b>{/закрыл|частич/i.test(gq.transparency) ? "частично" : "есть"}</b>раскрытие</div>}
              </div>
              {board.real_independence_note && <p className="sub" style={{ margin: "0 0 14px" }}>{shortProse(board.real_independence_note, 220)}</p>}
              <div className="grisks">
                {risks.map((r, i) => {
                  const sev = SEV[r.severity] || SEV.medium;
                  return <div className="grisk" key={i} style={{ "--sev": sev.c }}><div className="gh"><span className="gt">{cleanProse(r.risk)}</span><span className="gsev">{sev.t}</span></div>{r.description && <div className="gd">{cleanProse(r.description)}</div>}</div>;
                })}
              </div>
            </div>
          )}

          {/* 6. СВЯЗАННЫЕ СТОРОНЫ */}
          {rps && rps.severity && (
            <div className={`rp ${rps.severity === "low" ? "lowsev" : ""}`}>
              <div className="ri"><svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="#fff" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round"><path d="M12 2v20M2 12h20M5 5l14 14" /></svg></div>
              <div>
                <div className="rt">Связанные стороны — {rps.severity === "low" ? "под контролем" : "ключевой сигнал"}</div>
                <div className="rd">
                  {(rps.flows || []).slice(0, 2).map((fl, i) => <span key={i}>{i > 0 ? " " : ""}{cleanProse(fl.materiality_note)}{fl.direction ? <> <b>{fl.direction === "up_to_owner" ? "— вверх к собственнику" : "— вниз"}</b></> : null}.</span>)}
                  {" "}Сигнал вывода стоимости: <b>{SEV[rps.severity]?.t || rps.severity}</b>. <Tag k="est" />
                </div>
              </div>
            </div>
          )}
        </div>

        {/* ПРАВЫЙ РЕЙЛ — как считается балл + влияние на оценку */}
        {hasScore && (
          <aside className="calc-rail">
            <div className="calc-card">
              <div className="ct">Как считается балл</div>
              <div className="cs">Взвешенная сумма {scFactors.length} аспектов (оценка × вес)</div>
              {scFactors.map((f, i) => (
                <div className="calc-row" key={i} style={i === 0 ? { borderTop: 0 } : undefined}>
                  <span className="cn">{f.label}</span>
                  <span className="cw">×{Math.round((f.weight || 0) * 100)}%</span>
                  <span className="cc">{((f.score || 0) * (f.weight || 0)).toLocaleString("ru-RU", { minimumFractionDigits: 2, maximumFractionDigits: 2 })}</span>
                </div>
              ))}
              <div className="calc-total"><span className="tl">Итоговый балл</span><span className="tv">{fmt1(overall)}<s> / 5</s></span></div>
              <div className="scale-strip"><i style={{ background: "var(--neg)" }} /><i style={{ background: "var(--amber)" }} /><i style={{ background: "var(--pos)" }} /></div>
              <div className="scale-mark">
                {normOverall != null && <span className="nmk" style={{ left: `${((normOverall - 1) / 4) * 100}%` }} />}
                <span className="mk" style={{ left: `${((overall - 1) / 4) * 100}%` }} />
              </div>
              <div className="scale-lbls"><span>1 слабое</span><span>3</span><span>5 сильное</span></div>
              {normOverall != null && (
                <div className="vsnorm"><span className="vl">Против нормы сектора</span><span className="vnums">{fmt1(overall)} <span className="nm">vs {fmt1(normOverall)}</span></span><span className="vgap" style={{ color: overall >= normOverall ? "var(--pos)" : "var(--neg)" }}>{overall >= normOverall ? "+" : "−"}{fmt1(Math.abs(overall - normOverall))}</span></div>
              )}
            </div>

            <div className="calc-card">
              <div className="ct">Влияние на оценку</div>
              {premium != null && (
                <div className="fv-link-box" style={{ marginTop: 4 }}>
                  <div className="lt">суждение · связь с оценкой</div>
                  <div className="lv">Балл <b>{fmt1(overall)}</b>{redFlags.length ? " и красные флаги" : ""} → <b>+{fmt1(premium)} п.п.</b> к ставке дисконтирования → справедливый потолок в DCF ниже. Контур «{gd.contour === "contour_a_linear" ? "академический линейный" : "прагматичный выпуклый"}».</div>
                </div>
              )}
              <div className="rail-kv">
                {typeof fairBase === "number" && <div className="rk"><span className="l">Справедливая (после дисконта)</span><span className="v mono">{numfmt(fairBase, fairBase % 1 ? 1 : 0)} ₽</span></div>}
                <div className="rk"><span className="l">Уверенность</span><span className="v">{conf}</span></div>
                {sources.length > 0 && <div className="rk"><span className="l">Источники</span><span className="v mono">{sources.length}{meta.as_of ? ` · ${meta.as_of}` : ""}</span></div>}
              </div>
              <p className="fnote">Балл — аналитический ориентир Basis по 8 факторам методики, не инвестиционная рекомендация.</p>
            </div>
          </aside>
        )}
      </div>
    </div>
  );
}

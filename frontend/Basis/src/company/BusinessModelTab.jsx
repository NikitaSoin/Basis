/* Вкладка «Бизнес-модель» (гибрид-дизайн). Содержимое вкладки карточки компании —
   шапка/метрики/правый рейл карточки переиспользуются. 8 секций с тегами достоверности.
   Визуализация процентов — из СТРУКТУРИРОВАННЫХ чисел (financials.json), а не из текста:
   мини-P&L и каскад «куда уходит рубль» считаются из income_statement; доли сегментов —
   из profile.revenue_streams / financials.segments, иначе проза. Прочее (суть/цепочка/
   география/риски/оговорки) — проза business_model.md, переоформленная в NEO-плитки. */
import React from "react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import "../styles/business-model.css";

const CAT = ["var(--cat-5)", "var(--cat-2)", "var(--cat-7)", "var(--cat-1)", "var(--cat-6)", "var(--cat-8)", "var(--cat-4)", "var(--cat-3)"];

const Tag = ({ k }) => {
  const m = { fact: "факт", est: "оценка", judg: "суждение" };
  return <span className={`bm-tag ${k}`}>{m[k]}</span>;
};

const num = (v, d = 1) => v == null || isNaN(v) ? "—" : Number(v).toLocaleString("ru-RU", { minimumFractionDigits: d, maximumFractionDigits: d });

// value в млн ₽ → строка в млрд/трлн ₽
function rub(vMln) {
  if (vMln == null || isNaN(vMln)) return "—";
  const mlrd = vMln / 1000;
  if (Math.abs(mlrd) >= 1000) return num(mlrd / 1000, 2) + " трлн";
  return num(mlrd, mlrd >= 100 ? 0 : 1) + " млрд";
}

// Единый бар: items = [{pct, label, color}] → горизонтальный стек.
function StackBar({ items, sm }) {
  const vis = items.filter((x) => x && x.pct > 0.05);
  if (!vis.length) return null;
  return (
    <div className={"bm-stack" + (sm ? " sm" : "")}>
      {vis.map((x, i) => (
        <span key={i} className="seg" style={{ flex: x.pct, background: x.color }} title={`${x.label}: ${num(x.pct, 1)}%`}>
          <span className="sp">{num(x.pct, x.pct >= 10 ? 0 : 1)}%</span>
          {x.label && <span className="sl">{x.label}</span>}
        </span>
      ))}
    </div>
  );
}

const Prose = ({ md }) => md ? <div className="bm-prose"><ReactMarkdown remarkPlugins={[remarkGfm]}>{md}</ReactMarkdown></div> : null;

const Section = ({ title, tag, sub, children }) => (
  <div className="bm-card">
    <div className="bm-h"><h3>{title}</h3>{tag && <Tag k={tag} />}</div>
    {sub && <p className="bm-sub">{sub}</p>}
    {children}
  </div>
);

// ── разбор business_model.md по заголовкам ──
function splitSections(md) {
  const out = [];
  let cur = null;
  for (const line of (md || "").split("\n")) {
    const m = line.match(/^#{2,4}\s+(.*)$/);
    if (m) { if (cur) out.push(cur); cur = { heading: m[1].trim(), lines: [] }; }
    else if (cur) cur.lines.push(line);
    else { (out._pre = out._pre || []).push(line); }
  }
  if (cur) out.push(cur);
  return out;
}
const findBody = (secs, keys) => {
  const s = secs.find((x) => keys.some((k) => x.heading.toLowerCase().includes(k)));
  return s ? s.lines.join("\n").trim() : null;
};

// ── мини-P&L из financials.json ──
function KpiCard({ label, cur, prev }) {
  const max = Math.max(Math.abs(cur || 0), Math.abs(prev || 0)) || 1;
  const delta = (cur != null && prev) ? (cur / prev - 1) * 100 : null;
  const dcls = delta == null ? "" : delta >= 0 ? "tw-text-success" : "tw-text-danger";
  return (
    <div className="bm-kpi">
      <div className="bm-kl">{label}<s>млрд ₽</s></div>
      <div className="bm-kb"><span className="ky">{label === "" ? "" : "тек"}</span><span className="kbar"><i style={{ width: `${Math.abs(cur || 0) / max * 100}%` }} /></span><span className="kv">{rub(cur).replace(" млрд", "").replace(" трлн", "")}</span></div>
      <div className="bm-kb old"><span className="ky">пр.</span><span className="kbar"><i style={{ width: `${Math.abs(prev || 0) / max * 100}%` }} /></span><span className="kv">{rub(prev).replace(" млрд", "").replace(" трлн", "")}</span></div>
      <div className={`bm-kd ${dcls}`}>{delta == null ? "—" : `${delta >= 0 ? "▲ +" : "▼ "}${num(delta, 1)} %`}</div>
    </div>
  );
}

export default function BusinessModelTab({ bmMd, finJson, profile }) {
  const secs = splitSections(bmMd);
  const isx = (finJson && finJson.income_statement) || {};
  const cf = (finJson && finJson.cash_flow) || {};
  const last = (arr) => Array.isArray(arr) && arr.length ? arr[arr.length - 1] : null;
  const prev = (arr) => Array.isArray(arr) && arr.length > 1 ? arr[arr.length - 2] : null;

  const rev = last(isx.revenue), revP = prev(isx.revenue);
  const eb = last(isx.ebitda), ebP = prev(isx.ebitda);
  const np = last(isx.net_profit), npP = prev(isx.net_profit);
  const fcf = last(cf.fcf), fcfP = prev(cf.fcf);
  const hasPnl = rev != null && (eb != null || np != null);

  // каскад «куда уходит рубль» из последнего года (% выручки)
  const da = last(isx.da), fin = last(isx.finance_costs);
  const pct = (x) => (x != null && rev) ? (x / rev * 100) : null;
  const ebPct = pct(eb), npPct = pct(np), daPct = pct(da), finPct = pct(fin);
  const hasCasc = rev != null && ebPct != null && npPct != null;
  const expPct = hasCasc ? Math.max(0, 100 - ebPct) : null;
  const taxPct = hasCasc ? Math.max(0, ebPct - (daPct || 0) - (finPct || 0) - npPct) : null;

  // сегменты: структурированные доли → бары; иначе проза
  let segs = null;
  if (profile && Array.isArray(profile.revenue_streams) && profile.revenue_streams.length)
    segs = profile.revenue_streams.map((s) => ({ name: s.segment || s.name, pct: s.share_pct, note: s.description }));
  else if (finJson && Array.isArray(finJson.segments) && finJson.segments.length)
    segs = finJson.segments.map((s) => ({ name: s.name, pct: s.pct, note: s.note }));
  const segProse = findBody(secs, ["сегмент", "бизнес-юнит", "источник", "выручк"]);

  const sut = findBody(secs, ["суть бизнес", "о компании", "чем занимается"]) || (secs._pre ? secs._pre.join("\n").trim() : null);
  const chain = findBody(secs, ["цепочк", "создания стоимост", "вертикальн интегр", "переработк"]);
  const geo = findBody(secs, ["географ", "клиент", "рынки сбыт"]);
  const risks = findBody(secs, ["фактор", "риск", "уязвим", "угроз", "чувствительн"]);
  const notes = findBody(secs, ["оговорк", "методик", "допущен", "источник"]);

  return (
    <div className="bmx">
      {/* 1. Суть бизнеса */}
      {sut && <Section title="Суть бизнеса" tag="fact"><Prose md={sut} /></Section>}

      {/* 2. Экономика — мини-P&L */}
      {hasPnl && (
        <Section title="Экономика бизнеса" tag="fact" sub="МСФО, млрд ₽ · последний отчётный год против предыдущего (из финансовой отчётности).">
          <div className="bm-kpis">
            <KpiCard label="Выручка" cur={rev} prev={revP} />
            {eb != null && <KpiCard label="EBITDA" cur={eb} prev={ebP} />}
            {np != null && <KpiCard label="Чистая прибыль" cur={np} prev={npP} />}
            {fcf != null && <KpiCard label="FCF" cur={fcf} prev={fcfP} />}
          </div>
        </Section>
      )}

      {/* 3. Куда уходит каждый рубль выручки (+ структура расходов — слиты) */}
      {hasCasc && (
        <Section title="Куда уходит каждый рубль выручки" tag="est" sub="Доли от выручки последнего года, посчитаны из отчёта о прибылях и убытках. Это структура расходов: что остаётся до и после операционной прибыли.">
          <div className="bm-casc-h"><span className="ct">Выручка → EBITDA</span><span className="cv">100% выручки → EBITDA {num(ebPct, 0)}%</span></div>
          <StackBar items={[
            { pct: expPct, label: "Расходы и налоги", color: "var(--cat-8)" },
            { pct: ebPct, label: "EBITDA", color: "var(--cat-5)" },
          ]} />
          <div className="bm-casc-h"><span className="ct">EBITDA → чистая прибыль</span><span className="cv">чистая маржа {num(npPct, 1)}%</span></div>
          <StackBar items={[
            { pct: daPct, label: "Амортизация", color: "var(--cat-8)" },
            { pct: finPct, label: "Финрасходы", color: "var(--cat-1)" },
            { pct: taxPct, label: "Налог и прочее", color: "var(--cat-6)" },
            { pct: npPct, label: "Чистая прибыль", color: "var(--cat-3)" },
          ]} />
          <p className="bm-note"><b>Как читать:</b> переменные статьи (сырьё, производственные налоги) сжимаются вместе с выручкой и смягчают спад; постоянные (амортизация) и разовые курсовые — нет. Поэтому прибыль колеблется сильнее выручки. Доли — оценка из отчётности, не бухгалтерская классификация.</p>
        </Section>
      )}

      {/* 5. Сегменты — бизнес-юниты */}
      {(segs && segs.length >= 2) ? (
        <Section title="Сегменты (бизнес-юниты)" tag="fact" sub="Доли в выручке — из структурированных данных компании.">
          <StackBar sm items={segs.map((s, i) => ({ pct: s.pct, label: "", color: CAT[i % CAT.length] }))} />
          <div className="bm-seglist">
            {segs.map((s, i) => (
              <div key={i} className="bm-segrow">
                <span className="dot" style={{ background: CAT[i % CAT.length] }} />
                <div style={{ flex: 1 }}>
                  <div className="st">{s.name}<span className="sv">~{num(s.pct, s.pct >= 10 ? 0 : 1)} %</span></div>
                  <div className="bm-segscale"><i style={{ width: `${Math.min(100, s.pct)}%`, background: CAT[i % CAT.length] }} /></div>
                  {s.note && <div className="sd">{s.note}</div>}
                </div>
              </div>
            ))}
          </div>
        </Section>
      ) : segProse ? (
        <Section title="Сегменты (бизнес-юниты)" tag="fact"><Prose md={segProse} /></Section>
      ) : null}

      {/* 6. Цепочка создания стоимости */}
      {chain && <Section title="Цепочка создания стоимости" tag="est"><Prose md={chain} /></Section>}

      {/* 7. География и клиенты */}
      {geo && <Section title="География и клиенты" tag="est"><Prose md={geo} /></Section>}

      {/* 8. Ключевые факторы и риски */}
      {risks && <Section title="Ключевые факторы и риски" tag="judg"><Prose md={risks} /></Section>}

      {/* Оговорки / методика */}
      {notes && (
        <div className="bm-card">
          <details className="bm-det">
            <summary>Допущения и оговорки<svg className="chev" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round"><path d="M6 9l6 6 6-6" /></svg></summary>
            <div className="db"><Prose md={notes} /></div>
          </details>
        </div>
      )}
    </div>
  );
}

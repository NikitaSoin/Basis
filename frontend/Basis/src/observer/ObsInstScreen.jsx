// Экран «Оценка ситуации» раздела «Институциональная среда» по спецификации владельца
// (docs/Экран_Институциональная_среда_спецификация_v1.md; решения после прототипа 2026-09-18:
// дизайн как в прототипе, без плиток; лента «Обзор» не меняется; список всех карточек
// периода свёрнут по умолчанию).
//
// Данные: GET /api/market/inst-screen — карточки изменений условий для бизнеса, серии,
// шесть измерений, следствия для экономики, отраслевой разрез, направление и ветви — из
// снимка институционалиста (поле screen). Витрина рисует то, что вернул агент: своей
// аналитической логики здесь нет, только форма по Частям 2–4 спецификации. Вероятности
// словами (p_words), внутренние числа служат для сортировки.
import React, { useMemo, useState } from "react";
import "../styles/inst-screen.css";

const ARROW = {
  "вниз": ["▼", "ins-ar--dn"], "вверх": ["▲", "ins-ar--up"],
  "смешанно": ["◆", "ins-ar--mx"], "без изменений": ["◆", "ins-ar--mx"],
};
const STATUS_CLS = {
  "действует": "on", "принято": "on", "прецедент": "on",
  "обсуждается": "disc", "вступает с даты": "soon", "отменено": "off",
};
const SECTOR_DIR = {
  "помогает": ["▲ помогает", "ins-ar--up"], "мешает": ["▼ мешает", "ins-ar--dn"],
  "по-разному": ["◆ по-разному", "ins-ar--mx"],
};
const MONTH_DAYS = 30;
const QUARTER_DAYS = 92;

function list(x) { return Array.isArray(x) ? x : []; }
function txt(x) { return x == null ? "" : String(x); }
function fmtDate(d) {
  if (!d) return null;
  const m = /^(\d{4})-(\d{2})-(\d{2})/.exec(String(d));
  return m ? `${m[3]}.${m[2]}.${m[1]}` : String(d);
}
function fmtShort(d) {
  const m = /^(\d{4})-(\d{2})-(\d{2})/.exec(String(d || ""));
  return m ? `${m[3]}.${m[2]}` : txt(d);
}

function Tag({ kind, children }) {
  return <span className={`ins-tag ins-tag--${kind}`}>{children}</span>;
}
function StatusTag({ status }) {
  if (!status) return null;
  return <span className={`ins-st ins-st--${STATUS_CLS[status] || "off"}`}>{txt(status)}</span>;
}
function Arrow({ value }) {
  const m = ARROW[value] || ["◆", "ins-ar--mx"];
  return <span className={`ins-ar ${m[1]}`}>{m[0]}</span>;
}
function Cons({ items, brief }) {
  const xs = list(items).filter((x) => x && (typeof x === "string" || x.text));
  const shown = brief ? xs.slice(0, 2) : xs;
  return (
    <div className="ins-cons">
      {shown.map((x, i) => (
        <div key={i}><span className="ins-arr">→</span>{typeof x === "string" ? x : txt(x.text)}</div>
      ))}
    </div>
  );
}

// ───────── карточка изменения целиком (Часть 1.2) ─────────
function FullCard({ c, seriesTitle }) {
  const m = c.means || {};
  const conf = c.confidence || {};
  const ser = c.series || {};
  // Масштаб, горизонт и обратимость — отдельные поля карточки (Часть 1.2); если агент уже
  // вписал их в текст, второй раз не повторяем.
  const mt = txt(m.text).toLowerCase();
  const meansLine = [
    m.text,
    m.scale && !mt.includes("масштаб") && `масштаб — ${m.scale}`,
    m.horizon && !mt.includes("горизонт") && `горизонт — ${m.horizon}`,
    m.reversibility && !mt.includes("обратимость") && `обратимость — ${m.reversibility}`,
  ].filter(Boolean).join("; ");
  return (
    <div className="ins-card">
      <div className="ins-k">Что произошло</div>
      <div className="ins-v">{txt(c.fact)} <StatusTag status={c.status} /> <Tag kind="fact">факт</Tag></div>
      {c.change && <><div className="ins-k">Что меняется</div><div className="ins-v">{txt(c.change)}</div></>}
      {c.who && <><div className="ins-k">Кого касается</div><div className="ins-v">{txt(c.who)}</div></>}
      {meansLine && <><div className="ins-k">Что это значит</div><div className="ins-v">{meansLine}</div></>}
      {list(c.consequences).length > 0 && (
        <><div className="ins-k">Осязаемое следствие</div>
          <div className="ins-v ins-v--cons"><Cons items={c.consequences} /><div style={{ marginTop: 4 }}><Tag kind="est">оценка Basis</Tag></div></div></>
      )}
      {c.driver && <><div className="ins-k">Что за этим стоит</div><div className="ins-v">{txt(c.driver)}</div></>}
      {ser.key && (
        <><div className="ins-k">Серия</div>
          <div className="ins-v"><span className="ins-ser">{seriesTitle ? txt(seriesTitle) : txt(ser.key)}{ser.step ? ` · шаг ${ser.step}` : ""}</span></div></>
      )}
      <div className="ins-k">Подпись</div>
      <div className="ins-v ins-v--sig">
        {fmtDate(c.date)}{conf.level ? ` · уверенность: ${conf.level}` : ""}{conf.why ? ` — ${txt(conf.why)}` : ""}{c.source ? ` · источник: ${txt(c.source)}` : ""}
      </div>
    </div>
  );
}

function ToggleRow({ open, onToggle, className, children }) {
  return (
    <button type="button" className={className} aria-expanded={open} onClick={onToggle}>
      {children}
    </button>
  );
}

// ───────── дайджест: три строки, полная карточка по выбору (Часть 2.2) ─────────
function Digest({ cards, seriesById }) {
  const [open, setOpen] = useState(null);
  if (!cards.length) return null;
  return (
    <ul className="ins-digest">
      {cards.map((c) => {
        const isOpen = open === c.id;
        return (
          <li key={c.id} className={isOpen ? "ins-open" : ""}>
            <ToggleRow open={isOpen} onToggle={() => setOpen(isOpen ? null : c.id)} className="ins-drow">
              <div><b className="ins-kk">Что произошло</b><div className="ins-what">{txt(c.title)}</div></div>
              <div><b className="ins-kk">Кого касается</b>{txt(c.who)}</div>
              <div className="ins-v--cons"><b className="ins-kk">Осязаемое следствие</b><Cons items={c.consequences} brief /></div>
            </ToggleRow>
            {isOpen && <div className="ins-dopen"><FullCard c={c} seriesTitle={seriesById[(c.series || {}).key]} /></div>}
          </li>
        );
      })}
    </ul>
  );
}

// ───────── серии (Часть 1.3) ─────────
function Series({ series }) {
  const xs = list(series).filter((s) => s && s.status !== "закрыта");
  if (!xs.length) return null;
  return (
    <div className="ins-series">
      {xs.map((s) => (
        <div className="ins-ser-card" key={s.key}>
          <div className="ins-n">серия · <Tag kind="est">оценка Basis</Tag>{s.carried_over && <span className="ins-carried">с прошлой сборки</span>}</div>
          <b className="ins-t">{txt(s.title)}</b>
          {s.pattern && <p>{txt(s.pattern)}</p>}
          {list(s.events).length > 0 && <ol>{list(s.events).map((e, i) => <li key={i}>{txt(e)}</li>)}</ol>}
          {s.accumulated && <p className="ins-acc">Накопленное следствие: {txt(s.accumulated)}</p>}
          {s.p_continue_words && <p><span className="ins-pw">продолжение — {txt(s.p_continue_words)}</span></p>}
          {s.stop && <p className="ins-note">Что остановит: {txt(s.stop)}</p>}
        </div>
      ))}
    </div>
  );
}

// ───────── все карточки периода — свёрнуто по умолчанию (владелец, 2026-09-18) ─────────
function AllCards({ cards, types, seriesById, period, setPeriod, counts }) {
  const [filter, setFilter] = useState("all");
  const [open, setOpen] = useState(null);
  const visible = useMemo(() => cards.filter((c) => {
    if (period === "month" && c.period !== "month") return false;
    if (period === "quarter" && c.period === "older") return false;
    return filter === "all" || c.type === filter;
  }), [cards, period, filter]);
  return (
    <details className="ins-all">
      <summary>
        <span>Все карточки периода</span>
        <span className="ins-all-count">{period === "month" ? counts.month : counts.quarter}</span>
        <span className="ins-all-hint">раскрыть список</span>
      </summary>
      <div className="ins-period" role="group" aria-label="Период">
        <span>период:</span>
        {[["month", "месяц"], ["quarter", "квартал"]].map(([k, l]) => (
          <button type="button" key={k} aria-pressed={period === k} onClick={() => setPeriod(k)}>{l}</button>
        ))}
        <span className="ins-period-note">дайджест и вектор — за месяц; карточки старше квартала в список не входят</span>
      </div>
      {types.length > 1 && (
        <div className="ins-filters" role="group" aria-label="Фильтр по типу изменения">
          {[["all", "все"], ...types.map((t) => [t, t])].map(([k, l]) => (
            <button type="button" key={k} aria-pressed={filter === k} onClick={() => setFilter(k)}>{l}</button>
          ))}
        </div>
      )}
      {visible.length === 0 && <div className="ins-empty">За выбранный период карточек этого типа нет.</div>}
      <ul className="ins-allcards">
        {visible.map((c) => {
          const isOpen = open === c.id;
          return (
            <li key={c.id} className={isOpen ? "ins-open" : ""}>
              <ToggleRow open={isOpen} onToggle={() => setOpen(isOpen ? null : c.id)} className="ins-arow">
                <div className="ins-d">{fmtShort(c.date)}</div>
                <div className="ins-tt">{txt(c.title)}<small>{txt(c.who)}</small></div>
                <div className="ins-c">{list(c.consequences)[0] && <><span className="ins-arr">→</span>{txt(list(c.consequences)[0].text || list(c.consequences)[0])}</>}</div>
                <div><StatusTag status={c.status} /></div>
              </ToggleRow>
              {isOpen && <div className="ins-aopen"><FullCard c={c} seriesTitle={seriesById[(c.series || {}).key]} /></div>}
            </li>
          );
        })}
      </ul>
    </details>
  );
}

// ───────── шесть измерений (Часть 3.2) ─────────
function Dimensions({ dims }) {
  if (!dims.length) return null;
  return (
    <div className="ins-dims">
      {dims.map((d) => (
        <div className="ins-dim" key={d.key}>
          <div className="ins-nm">{txt(d.title)}<small>{txt(d.subtitle)}</small></div>
          <div className="ins-lvl">
            <b>{txt(d.level) || "—"}</b>
            <Arrow value={d.arrow} /> {txt(d.arrow_note || d.arrow)} <Tag kind="est">оценка</Tag>
            {d.carried_over && <div className="ins-carried">с прошлой сборки</div>}
          </div>
          <div className="ins-body">
            {d.text && <p>{txt(d.text)}</p>}
            {d.consequence && <p className="ins-cs">Следствие: {txt(d.consequence)}</p>}
            {list(d.cards).length > 0 && (
              <details className="ins-details">
                <summary>Из каких изменений сложилась стрелка ({d.cards.length})</summary>
                <ul>{d.cards.map((c) => <li key={c.id}>{fmtShort(c.date)} — {txt(c.title)}</li>)}</ul>
              </details>
            )}
          </div>
        </div>
      ))}
    </div>
  );
}

function Sectors({ rows }) {
  if (!rows.length) return null;
  return (
    <div className="ins-tblwrap"><table className="ins-table"><thead><tr>
      <th>Кому</th><th>Направление</th><th>Через какую метрику</th><th>Чем измерено</th><th>Устойчивость</th></tr></thead><tbody>
      {rows.map((s, i) => {
        const m = SECTOR_DIR[s.direction] || ["◆ " + txt(s.direction), "ins-ar--mx"];
        return (
          <tr key={i}>
            <td className="ins-s">{txt(s.who)}{list(s.tags).length > 0 && <div style={{ marginTop: 4 }}>{list(s.tags).map((t, j) => <span className="ins-tick" key={j}>{txt(t)}</span>)}</div>}</td>
            <td className={`ins-dir ${m[1]}`}>{m[0]}</td>
            <td>{txt(s.metric)}</td>
            <td>{txt(s.measured)}</td>
            <td>{txt(s.stability)}</td>
          </tr>
        );
      })}
    </tbody></table></div>
  );
}

// ───────── ветви (Часть 4.2) ─────────
function Branches({ branches }) {
  const [open, setOpen] = useState(null);
  if (!branches.length) return null;
  return (
    <ul className="ins-branches">
      {branches.map((b, i) => {
        const key = b.key || String(i);
        const isOpen = open === key;
        return (
          <li key={key} className={isOpen ? "ins-open" : ""}>
            <ToggleRow open={isOpen} onToggle={() => setOpen(isOpen ? null : key)} className="ins-brow">
              <div className="ins-bnm">{txt(b.label)}
                <small className={b.worst ? "ins-dg" : ""}>{b.base ? "наиболее вероятная" : b.worst ? "наиболее неблагоприятная для бизнеса" : "ветвь"}</small>
              </div>
              <div className="ins-pr"><b>{txt(b.p_words) || "—"}</b>{txt(b.geo_note)}</div>
              <div className="ins-how"><b>Как туда попасть</b>{txt(b.how_we_get_there)}</div>
            </ToggleRow>
            {isOpen && (
              <div className="ins-bopen"><div className="ins-four">
                {b.what && <div><h5>Что меняется в условиях</h5><p>{txt(b.what)}</p></div>}
                {b.who && <div><h5>Для кого</h5><p>{txt(b.who)}</p></div>}
                {b.means && <div><h5>Что это значит</h5><p>{txt(b.means)}</p></div>}
                {list(b.consequences).length > 0 && <div><h5>Осязаемые следствия</h5><Cons items={b.consequences} /></div>}
              </div></div>
            )}
          </li>
        );
      })}
    </ul>
  );
}

export default function ObsInstScreen({ data }) {
  if (!data || !data.available) return null;
  const [period, setPeriod] = useState("month");
  const cards = list(data.cards);
  const series = list(data.series);
  const seriesById = useMemo(() => Object.fromEntries(series.map((s) => [s.key, s.title])), [series]);
  const counts = data.counts || { month: 0, quarter: 0, series: 0 };
  const dates = data.dates || {};
  const per = data.period || {};
  return (
    <div className="ins-root">
      <div className="ins-head">
        <div>
          <div className="ins-cfg">Россия · условия для бизнеса · поток изменений с накопленным итогом</div>
          <h1 className="ins-h1">{txt(data.vector) || "Условия для бизнеса: что изменилось за период"}</h1>
          {data.vector && <div className="ins-h1-tag"><Tag kind="est">вектор периода · оценка Basis</Tag></div>}
        </div>
        <div className="ins-dates">
          {(per.from || per.to) && <>период: {fmtShort(per.from)}–{fmtDate(per.to)}<br /></>}
          {dates.inst && <>снимок условий · {fmtDate(dates.inst)}<br /></>}
          {dates.geo && <>ветви по геосценарию · {fmtDate(dates.geo)}</>}
          {data.carried_over && <><br />экран перенесён с прошлой сборки</>}
        </div>
      </div>

      <section className="ins-block">
        <p className="ins-eyebrow">Блок 1<span>что изменилось за период — вход на экран</span></p>
        <h2 className="ins-h2">Изменения условий для бизнеса</h2>
        <h3 className="ins-h3">Дайджест: изменения с самым широким адресатом</h3>
        <Digest cards={list(data.digest)} seriesById={seriesById} />
        {list(data.digest).length === 0 && <div className="ins-empty">За последний месяц карточек, отобранных в дайджест, нет.</div>}
        <p className="ins-note" style={{ marginTop: 10 }}>Отбор в дайджест — по масштабу и широте адресата, не по громкости в новостях. События без экономического адресата на экран не выводятся.</p>
        {series.some((s) => s.status !== "закрыта") && (
          <>
            <h3 className="ins-h3">Активные серии</h3>
            <Series series={series} />
          </>
        )}
        <h3 className="ins-h3">Раскрытие</h3>
        <AllCards cards={cards} types={list(data.card_types)} seriesById={seriesById}
                  period={period} setPeriod={setPeriod} counts={counts} />
      </section>

      <section className="ins-block">
        <p className="ins-eyebrow">Блок 2<span>к чему привели изменения в сумме — обновляется еженедельно</span></p>
        <h2 className="ins-h2">Накопленный эффект: условия и экономика</h2>
        <p className="ins-note">Оценка каждого измерения — не мнение, а сумма карточек: стрелка раскрывается в события, которые её произвели. Сравнение — с началом квартала.</p>
        <Dimensions dims={list(data.dimensions)} />
        {list(data.economy).length > 0 && (
          <div className="ins-econ"><b className="ins-kk">Что это значит для экономики</b>
            {list(data.economy).map((p, i) => <p key={i}>{txt(p)}{i === data.economy.length - 1 && <> <Tag kind="est">оценка Basis</Tag></>}</p>)}
          </div>
        )}
        {list(data.sectors).length > 0 && (
          <>
            <h3 className="ins-h3">Кому помогает, кому мешает</h3>
            <Sectors rows={list(data.sectors)} />
            <p className="ins-small" style={{ marginTop: 8 }}>Компании названы как затронутые условием, а не как рекомендация; это не индивидуальная инвестиционная рекомендация.</p>
          </>
        )}
        {list(data.tax_target).length > 0 && (
          <>
            <h3 className="ins-h3">Признаки налоговой мишени в текущих условиях</h3>
            <div className="ins-target">{list(data.tax_target).map((t, i) => <div key={i}><b>{txt(t.feature)}</b>{txt(t.why)}</div>)}</div>
          </>
        )}
      </section>

      <section className="ins-block">
        <p className="ins-eyebrow">Блок 3<span>куда движутся условия и что может их развернуть — пересмотр ежеквартально и при смене геосценария</span></p>
        <h2 className="ins-h2">Направление и сценарии</h2>
        {list(data.direction).length > 0 && (
          <>
            <h3 className="ins-h3">Направление на год вперёд по шести измерениям</h3>
            <div className="ins-dirgrid">
              {list(data.direction).map((d) => (
                <div key={d.key}><Arrow value={d.arrow} /><span><b>{txt(d.title || d.key)}</b>{txt(d.why)}</span></div>
              ))}
            </div>
          </>
        )}
        {list(data.branches).length > 0 && (
          <>
            <h3 className="ins-h3">Ветви на 12–24 месяца</h3>
            <p className="ins-note">Ветви привязаны к сценариям геополитического экрана: главные развилки условий для бизнеса производны от внешних. Вероятности словами; изменение без события не допускается. Раскрытие — по выбору ветви.</p>
            <Branches branches={list(data.branches)} />
          </>
        )}
        {list(data.thresholds).length > 0 && (
          <div className="ins-thresh"><div className="ins-k">Пороговые события</div><ul>{list(data.thresholds).map((t, i) => <li key={i}>{txt(t)}</li>)}</ul></div>
        )}
      </section>

      <p className="ins-foot">Факты — документы и официальные сообщения; лента — сигнал, факт подтверждается документом. Следствия карточек и ветвей — оценка Basis, уходят в журнал прогнозов и сверяются с фактом еженедельно. Вероятности словесные, внутренние числа служат для сортировки. Не является индивидуальной инвестиционной рекомендацией.</p>
    </div>
  );
}

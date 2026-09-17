// Экран «Оценка ситуации» раздела «Геополитика» по спецификации владельца
// (docs/Оценка_ситуации_Геополитика.md, v1.1; решения после прототипа 2026-09-18).
//
// Данные: GET /api/market/geo-screen → hotspots[<очаг>]. Блоки 1–3 и карта —
// из сводки геополитика (поле screen), блок «Последствия для экономики России»
// — из сводки экономиста (hotspot_effects). У каждого блока своя дата.
// Витрина рисует то, что вернул агент: своей аналитической логики здесь нет,
// только форма по Части 7 спецификации. Вероятности — словами (p6m_words),
// внутренние числа служат для сортировки. Плиток нет, карта — в первом блоке.
import React, { useState } from "react";
import "../styles/geo-screen.css";

const DIR_STYLE = {
  "помогает": ["▲ помогает", "gs-dir--up"],
  "мешает": ["▼ мешает", "gs-dir--dn"],
  "по-разному": ["◆ по-разному", "gs-dir--mx"],
  "не влияет": ["— не влияет", "gs-dir--mx"],
};
const GOAL_ARROW = { "к цели": "→ к цели", "стоит": "◦ стоит", "от цели": "← от цели" };
const STATUS_TAG = {
  "Ф": ["gs-tag--fact", "факт"], "Д": ["gs-tag--fact", "данные"],
  "В": ["gs-tag--est", "оценка Basis"], "Г": ["gs-tag--jud", "суждение Basis"],
};

function Tag({ status }) {
  const m = STATUS_TAG[status];
  if (!m) return null;
  return <span className={`gs-tag ${m[0]}`}>{m[1]}</span>;
}

function list(x) { return Array.isArray(x) ? x : []; }
function txt(x) { return x == null ? "" : String(x); }

function Dir({ value }) {
  const m = DIR_STYLE[value] || ["◆ " + txt(value), "gs-dir--mx"];
  return <span className={`gs-dir ${m[1]}`}>{m[0]}</span>;
}

function fmtDate(d) {
  if (!d) return null;
  const m = /^(\d{4})-(\d{2})-(\d{2})/.exec(String(d));
  return m ? `${m[3]}.${m[2]}.${m[1]}` : String(d);
}

// ───────── блок 1 ─────────
function StateBlock({ state, map, mapNode }) {
  const s = state || {};
  const summary = list(s.summary);
  return (
    <section className="gs-block">
      <p className="gs-eyebrow">1 · Состояние и динамика<span>что происходит и в какую сторону движется</span></p>
      {s.phase && <h2 className="gs-h2">{s.phase}</h2>}
      {summary.length > 0 && (
        <p className="gs-lead">
          {summary.map((x, i) => (i === 0
            ? <span key={i} className="gs-phase">{txt(x)} </span>
            : <span key={i}>{txt(x)} </span>))}
        </p>
      )}
      {list(s.goals).length > 0 && (
        <>
          <h3 className="gs-h3">Достижение целей сторон</h3>
          <div className="gs-tblwrap"><table className="gs-table"><thead><tr>
            <th>Сторона</th><th>Чего добивается на деле</th><th>Направление</th><th>Скорость</th>
            <th>Достижимо ли при сохранении нынешних условий</th></tr></thead><tbody>
            {list(s.goals).map((g, i) => (
              <tr key={i}>
                <td className="gs-ch">{txt(g.side)}</td>
                <td>{txt(g.goal)}</td>
                <td className="gs-num">{GOAL_ARROW[g.direction] || txt(g.direction)}</td>
                <td className="gs-num">{txt(g.speed)}</td>
                <td>{txt(g.achievable)} <Tag status={g.status} /></td>
              </tr>))}
          </tbody></table></div>
        </>
      )}
      {list(s.time).length > 0 && (
        <>
          <h3 className="gs-h3">Фактор времени</h3>
          <div className="gs-tblwrap"><table className="gs-table"><thead><tr>
            <th>Шкала</th><th>На чьей стороне время</th><th>Как меняется</th><th>Почему</th></tr></thead><tbody>
            {list(s.time).map((t, i) => (
              <tr key={i}>
                <td className="gs-ch" style={{ maxWidth: 260 }}>{txt(t.axis)}</td>
                <td className="gs-num">{txt(t.side)}</td>
                <td>{txt(t.shift)}</td>
                <td>{txt(t.why)} <Tag status={t.status} /></td>
              </tr>))}
          </tbody></table></div>
        </>
      )}
      {s.time_verdict && <p className="gs-note" style={{ marginTop: 12 }}><b>{txt(s.time_verdict)}</b> <span className="gs-tag gs-tag--jud">суждение Basis</span></p>}

      {(map || mapNode) && (
        <>
          <h3 className="gs-h3">Карта{map?.kind ? `: ${txt(map.kind)}` : ""}</h3>
          {map && (list(map.dynamics).length > 0 || list(map.points).length > 0) && (
            <div className="gs-map">
              <div>
                <h4>Состояние и динамика за период</h4>
                <ul>{list(map.dynamics).map((x, i) => <li key={i}>{txt(x.k)}: <span className="gs-mnum">{txt(x.v)}</span></li>)}</ul>
              </div>
              <div>
                <h4>Точки, значимые для каналов в экономику</h4>
                <ul>{list(map.points).map((x, i) => <li key={i}>{txt(x.k)}: <span className="gs-mnum">{txt(x.v)}</span></li>)}</ul>
              </div>
            </div>
          )}
          {mapNode && <div className="gs-mapwrap">{mapNode}</div>}
        </>
      )}
    </section>
  );
}

// ───────── блок 2 ─────────
function ForcesBlock({ forces }) {
  const f = forces || {};
  const dur = f.duration || {};
  return (
    <section className="gs-block">
      <p className="gs-eyebrow">2 · Движущие силы и устойчивость ситуации<span>почему оно так и как долго продлится</span></p>
      <h2 className="gs-h2">Кто чего хочет и почему не может иначе</h2>
      <div className="gs-forces">
        {list(f.items).map((it, i) => <div className="gs-force" key={i}><b>{txt(it.who)}</b><p>{txt(it.text)}</p></div>)}
      </div>
      {(list(f.holds).length > 0 || list(f.change).length > 0) && (
        <>
          <h3 className="gs-h3">Что удерживает ситуацию · что способно её изменить</h3>
          <div className="gs-cols">
            <div><h4>Что удерживает ситуацию</h4><ul>{list(f.holds).map((x, i) => <li key={i}>{txt(x)}</li>)}</ul></div>
            <div><h4>Что способно её изменить</h4><ul>{list(f.change).map((x, i) => <li key={i}>{txt(x)}</li>)}</ul></div>
          </div>
        </>
      )}
      {dur.label && (
        <>
          <h3 className="gs-h3">Оценка длительности</h3>
          <div className="gs-duration">
            <span className="gs-pill">{txt(dur.label)}</span>
            <div>
              <p className="gs-note">{txt(dur.why)} <span className="gs-tag gs-tag--jud">суждение Basis</span></p>
              {dur.shortens && (
                <details className="gs-details"><summary>Что должно измениться, чтобы горизонт сократился</summary>
                  <p className="gs-note" style={{ marginTop: 8 }}>{txt(dur.shortens)}</p></details>
              )}
            </div>
          </div>
        </>
      )}
      {f.twist && <div className="gs-twist"><b>Неочевидное звено.</b> {txt(f.twist)}</div>}
    </section>
  );
}

// ───────── блок 3 ─────────
function ScenariosBlock({ scenarios, economy }) {
  const [open, setOpen] = useState(null);
  const sc = scenarios || {};
  const branches = [...list(sc.branches)].sort((a, b) => (Number(b.p6m) || 0) - (Number(a.p6m) || 0));
  // «что с экономикой» по ветви — из сравнения экономиста, если оно есть
  const bb = economy?.by_branch || {};
  const colIdx = {};
  list(bb.columns).forEach((c, i) => { if (c && c.key) colIdx[c.key] = i; });
  const econHint = (key) => {
    const i = colIdx[key];
    if (i == null) return null;
    const parts = list(bb.rows).map((r) => (r && r.cells && r.cells[i] ? `${txt(r.indicator)}: ${txt(r.cells[i])}` : null)).filter(Boolean);
    return parts.length ? parts.join("; ") : null;
  };
  return (
    <section className="gs-block">
      <p className="gs-eyebrow">3 · Сценарии развития<span>во что это может превратиться</span></p>
      <h2 className="gs-h2">Ветви на шесть и восемнадцать месяцев, по убыванию вероятности</h2>
      <p className="gs-note">Вероятности словами по единой шкале: «крайне маловероятно» — до 5 из 100, «маловероятно» — до 20, «возможно» — до 45, «скорее да» — до 70, «вероятно» — до 90. Нажмите на ветвь, чтобы раскрыть: что там происходит, почему, как долго и что это значит для нас.</p>
      <ul className="gs-branches">
        {branches.map((b, i) => {
          const isOpen = open === b.key;
          const hint = econHint(b.key);
          return (
            <li key={b.key || i} className={isOpen ? "gs-open" : ""}>
              <button type="button" className="gs-brow" aria-expanded={isOpen} onClick={() => setOpen(isOpen ? null : b.key)}>
                <div className="gs-rank">{i + 1}</div>
                <div className="gs-bname">{txt(b.label)}
                  {b.base && <small>базовая ветвь</small>}
                  {b.most_dangerous && <small className="gs-dg">наиболее опасная для экономики</small>}
                </div>
                <div className="gs-prob"><b>6 мес: {txt(b.p6m_words)}</b><b>18 мес: {txt(b.p18m_words)}</b></div>
                <div className="gs-how"><b>Как сюда попадём</b><span>{txt(b.how_we_get_there)}</span>
                  {hint && <><b>Что с экономикой</b><span>{hint}</span></>}
                </div>
              </button>
              {isOpen && (
                <div className="gs-bopen">
                  {b.most_dangerous && b.danger_why && <p className="gs-note" style={{ margin: "6px 0 10px" }}><b>Почему опасна:</b> {txt(b.danger_why)}</p>}
                  <div className="gs-four">
                    <div><h5>Что там происходит</h5><p>{txt(b.what)}</p></div>
                    <div><h5>Почему так</h5><p>{txt(b.why)}</p></div>
                    <div><h5>Как долго</h5><p>{txt(b.how_long)}</p></div>
                    <div><h5>Что это значит для нас</h5><p>{txt(b.for_us)}</p></div>
                  </div>
                </div>
              )}
            </li>
          );
        })}
      </ul>
      {sc.nearest?.event && (
        <div className="gs-nearest"><span className="gs-k">Ближайшее событие пересмотра</span>
          <div><b>{txt(sc.nearest.event)}.</b> {txt(sc.nearest.what_it_triggers)}</div></div>
      )}
      {list(sc.other_thresholds).length > 0 && (
        <details className="gs-details"><summary>Остальные пороговые события ({sc.other_thresholds.length})</summary>
          <ul>{list(sc.other_thresholds).map((x, i) => <li key={i}>{txt(x)}</li>)}</ul></details>
      )}
    </section>
  );
}

// ───────── блок 4 (экономист) ─────────
function EconomyBlock({ economy, macroDate }) {
  const e = economy;
  return (
    <section className="gs-block">
      <p className="gs-eyebrow">4 · Последствия для экономики России<span>что это значит в прикладном смысле{macroDate ? ` · сводка экономиста от ${fmtDate(macroDate)}` : ""}</span></p>
      {!e && (
        <div className="gs-empty">Блок экономиста по этому очагу ещё не собран: он появляется после вечерней сборки, в которой экономист получает ветви геополитика.</div>
      )}
      {e && (
        <>
          <h2 className="gs-h2">Экономика сейчас: цифры на дату сборки</h2>
          {e.intro && <p className="gs-note">{txt(e.intro)}</p>}
          {list(e.now).length > 0 && (
            <div className="gs-tblwrap"><table className="gs-table"><thead><tr><th>Показатель</th><th>Значение</th><th>Дата и примечание</th></tr></thead><tbody>
              {list(e.now).map((k, i) => <tr key={i}><td>{txt(k.indicator)}</td><td className="gs-num">{txt(k.value)}</td><td className="gs-small">{txt(k.note)}</td></tr>)}
            </tbody></table></div>
          )}
          {list(e.channels).length > 0 && (
            <>
              <h3 className="gs-h3">Каналы: что происходит, как доходит до экономики, насколько сильно и куда движется</h3>
              {list(e.channels).map((c, i) => (
                <div className="gs-chan" key={i}>
                  <div className="gs-chan-hd">{txt(c.name)}{c.scale && <span>масштаб: {txt(c.scale)}</span>}</div>
                  <div className="gs-chan-body">
                    {c.now && <p><b>Что происходит.</b> {txt(c.now)}</p>}
                    {c.how && <p><b>Как доходит.</b> {txt(c.how)}</p>}
                    {c.where && <p><b>Куда движется.</b> {txt(c.where)}</p>}
                    {c.who && <p className="gs-small"><b>Кого касается:</b> {txt(c.who)}</p>}
                  </div>
                </div>
              ))}
            </>
          )}
          {e.systemic && <div className="gs-sys"><b>Как каналы связаны между собой</b>{txt(e.systemic)}</div>}
          {list(e.institutional).length > 0 && (
            <>
              <h3 className="gs-h3">Институциональный слой</h3>
              <ul className="gs-inst">{list(e.institutional).map((x, i) => <li key={i}><div>{txt(x.what)}</div><div className="gs-to">→ {txt(x.effect)}</div></li>)}</ul>
            </>
          )}
          {list(e.sectors).length > 0 && (
            <>
              <h3 className="gs-h3">Отраслевой слой: кому помогает, кому мешает</h3>
              <div className="gs-tblwrap"><table className="gs-table"><thead><tr><th>Отрасль и компании</th><th>Направление</th><th>Через что</th><th>Цифры</th><th>Почему именно этот очаг</th></tr></thead><tbody>
                {list(e.sectors).map((s, i) => (
                  <tr key={i}>
                    <td><b>{txt(s.sector)}</b>{list(s.tickers).length > 0 && <div style={{ marginTop: 4 }}>{list(s.tickers).map((t, j) => <span className="gs-tick" key={j}>{txt(t)}</span>)}</div>}</td>
                    <td><Dir value={s.direction} /></td>
                    <td>{txt(s.metric)}</td>
                    <td>{txt(s.numbers)}</td>
                    <td>{txt(s.why)}</td>
                  </tr>))}
              </tbody></table></div>
              <p className="gs-small" style={{ marginTop: 8 }}>Компании названы как затронутые каналом, а не как рекомендация; это не индивидуальная инвестиционная рекомендация.</p>
            </>
          )}
          {list(e.by_branch?.columns).length > 0 && list(e.by_branch?.rows).length > 0 && (
            <>
              <h3 className="gs-h3">Сравнение по ветвям</h3>
              <div className="gs-tblwrap"><table className="gs-table"><thead><tr><th></th>{list(e.by_branch.columns).map((c, i) => <th key={i}>{txt(c.label || c.key)}</th>)}</tr></thead><tbody>
                {list(e.by_branch.rows).map((r, i) => <tr key={i}><td className="gs-ch">{txt(r.indicator)}</td>{list(r.cells).map((c, j) => <td key={j}>{txt(c)}</td>)}</tr>)}
              </tbody></table></div>
            </>
          )}
        </>
      )}
    </section>
  );
}

export default function ObsGeoScreen({ data, mapNode }) {
  if (!data) return null;
  const dates = data.dates || {};
  const title = data.state?.phase ? `${data.label}: ${txt(data.state.phase).replace(/\.$/, "")}` : data.label;
  return (
    <div className="gs-root">
      <div className="gs-head">
        <div>
          <div className="gs-cfg">{txt(data.config_label)}</div>
          <h1 className="gs-h1">{title}</h1>
        </div>
        <div className="gs-dates">
          {dates.geo && <>геополитика · {fmtDate(dates.geo)}<br /></>}
          {dates.macro && <>экономика · {fmtDate(dates.macro)}<br /></>}
          {dates.profile && <>портрет очага · {fmtDate(dates.profile)}</>}
          {data.carried_over && <><br />блоки перенесены с прошлой сборки</>}
        </div>
      </div>
      <StateBlock state={data.state} map={data.map} mapNode={mapNode} />
      <ForcesBlock forces={data.forces} />
      <ScenariosBlock scenarios={data.scenarios} economy={data.economy} />
      <EconomyBlock economy={data.economy} macroDate={dates.macro} />
      <p className="gs-foot">Оценка Basis. Вероятности словесные, внутренние числа служат для сортировки и журнала. Не является индивидуальной инвестиционной рекомендацией.</p>
    </div>
  );
}

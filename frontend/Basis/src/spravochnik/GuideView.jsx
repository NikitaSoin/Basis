/**
 * Раздел «Справочник» ВНУТРИ платформы (вкладка в навигации, ?view=guide).
 *
 * ЗАЧЕМ ОТДЕЛЬНЫЙ РАЗДЕЛ, ЕСЛИ ЕСТЬ ПРЕ-РЕНДЕРЕННЫЕ /spravochnik/<слаг>/ (владелец,
 * 11.09.2026): статика — точка входа ИЗ ПОИСКА, одноразовая по своей природе. А тут
 * человек уже внутри платформы: у него шапка, поиск, история переходов, и статья должна
 * вести не «по ссылке наружу», а в тот же интерфейс — открыть карточку компании или
 * график показателя прямо здесь, без перезагрузки.
 *
 * 🔴 ПОЧЕМУ ЭТО НЕ ЛОМАЕТ ПОИСК: раздел живёт на СВОЁМ адресе `?view=guide`, а не
 * подменяет собой статические `/spravochnik/…`, `/pokazateli/…`, `/statistika/…`.
 * Приложение НЕ перехватывает эти адреса и не удаляет их текст — именно перехват в
 * августе стоил нам лучшей точки входа (/bonds/vdo/), когда робот вместо статьи получал
 * пустой каркас. Здесь два адреса с одним содержанием: индексируется статика, внутри
 * платформы работает этот раздел.
 *
 * ТРИ ВКЛАДКИ (владелец, 11.09.2026: «можешь перенести в справочник показатели и
 * термины чтобы были, экономическую статистику»):
 *   • «Как устроен бизнес» — объяснительные статьи с живым разбором компании внутри;
 *   • «Термины рынка» — определения (тот же текст, что на /pokazateli/<слаг>/);
 *   • «Экономическая статистика» — что означает каждый показатель и как он влияет на
 *     оценку бумаг; клик открывает ЖИВОЙ график в Обозревателе, а не копию данных.
 *
 * 🔴 ДАННЫЕ НЕ ДУБЛИРУЕМ. Значения показателей приходят из /api/market/macro — того же
 * источника, что кормит Обозреватель. Своя копия чисел здесь означала бы два места, где
 * они расходятся, а расхождения между экранами — системная боль платформы (CLAUDE.md).
 * Тексты статей и терминов лежат в ./content.js и ./terms.js, их же читают генераторы
 * пре-рендера: один источник на двух потребителей.
 */
import React, { useEffect, useMemo, useState } from "react";
import { ArrowLeft, ArrowRight, BookOpen, LineChart, Layers } from "lucide-react";
import ARTICLES from "./content";
import TERMS from "./terms";
import "../styles/spravochnik.css";

const API = process.env.REACT_APP_API_URL || "https://nikitasoin-basis-a772.twc1.net";

const fmtMoney = (v) => (v == null ? "—"
  : new Intl.NumberFormat("ru-RU", { maximumFractionDigits: v >= 100 ? 0 : 2 }).format(v) + " ₽");
const fmtPct = (v) => (v == null ? "—"
  : new Intl.NumberFormat("ru-RU", { maximumFractionDigits: 1 }).format(Math.abs(v)) + "%");

const TABS = [
  { id: "business", label: "Как устроен бизнес", icon: BookOpen },
  { id: "terms", label: "Термины рынка", icon: Layers },
  { id: "macro", label: "Экономическая статистика", icon: LineChart },
];

/* ------------------------- живой блок компании-эталона ------------------------- */
/** Числа берём из /bfv — того же движка, что считает справедливую цену в карточке.
 *  Своей формулы здесь нет и быть не должно: две цифры с разными методиками на одном
 *  сайте мы уже проходили. */
function BridgeCard({ article, onOpenCompany }) {
  const b = article.bridge;
  const [bfv, setBfv] = useState(null);
  const [failed, setFailed] = useState(false);

  useEffect(() => {
    let alive = true;
    setBfv(null); setFailed(false);
    const ctl = new AbortController();
    const t = setTimeout(() => ctl.abort(), 12000);
    fetch(`${API}/api/companies/by-ticker/${b.ticker}/bfv`, { signal: ctl.signal })
      .then((r) => (r.ok ? r.json() : null))
      .then((d) => { if (alive) { if (d && d.status === "ok" && d.current_price != null) setBfv(d); else setFailed(true); } })
      .catch(() => { if (alive) setFailed(true); })
      .finally(() => clearTimeout(t));
    return () => { alive = false; ctl.abort(); clearTimeout(t); };
  }, [b.ticker]);

  const up = bfv && bfv.upside_pct;
  return (
    <div className="sprv-bridge">
      <span className="sprv-kicker">Проверьте на реальной компании</span>
      <h3>{b.name} <span className="sprv-tick bs-mono">{b.ticker}</span></h3>
      <p className="sprv-why">{b.why}</p>

      {bfv && (
        <div className="sprv-nums">
          <div className="sprv-num">
            <span className="k">Цена сейчас</span>
            <span className="v bs-mono">{fmtMoney(bfv.current_price)}</span>
          </div>
          <div className="sprv-num">
            <span className="k">Справедливая цена Basis</span>
            <span className="v bs-mono">{fmtMoney(bfv.fair_price)}</span>
          </div>
          {up != null && (
            <div className="sprv-num">
              <span className="k">Потенциал</span>
              <span className={`v bs-mono ${up >= 0 ? "up" : "down"}`}>
                {up >= 0 ? "▲ +" : "▼ "}{fmtPct(up)}
              </span>
            </div>
          )}
          {bfv.verdict && (
            <div className="sprv-num">
              <span className="k">Вердикт модели</span>
              <span className="v">{bfv.verdict}</span>
            </div>
          )}
        </div>
      )}

      <p className="sprv-epi">
        {bfv
          ? "Оценка модели (BFV), не прогноз цены и не рекомендация. Считается от текущей котировки."
          : failed
            ? "Живые числа сейчас недоступны — они появятся в карточке компании."
            : "Загружаю текущую оценку…"}
      </p>

      <button type="button" className="sprv-cta" onClick={() => onOpenCompany(b.ticker, b.tab)}>
        Открыть разбор {b.nameGen || b.name} <ArrowRight size={15} />
      </button>
    </div>
  );
}

/* --------------------------------- статья --------------------------------- */
function Article({ article, onOpenCompany, onOpenScreener, onOpenArticle, onBack }) {
  // Мостик стоит после второго раздела: человек уже получил ответ и готов посмотреть
  // на живую бумагу, но ещё не дочитал до конца — до конца доходят не все.
  const at = Math.min(2, article.sections.length);
  useEffect(() => { window.scrollTo({ top: 0, behavior: "auto" }); }, [article.slug]);

  const renderSections = (from, to) => article.sections.slice(from, to).map((s) => (
    <section key={s.h}>
      <h2>{s.h}</h2>
      {s.p.map((t, i) => <p key={i}>{t}</p>)}
    </section>
  ));

  const related = (article.related || [])
    .map((slug) => ARTICLES.find((a) => a.slug === slug)).filter(Boolean);

  return (
    <div className="sprv-article">
      <button type="button" className="sprv-back" onClick={onBack}>
        <ArrowLeft size={15} /> Все ответы
      </button>
      <h1>{article.question}?</h1>
      <div className="sprv-answer">
        <span className="lbl">Короткий ответ</span>
        <p>{article.answer}</p>
      </div>
      <p className="sprv-tagline">
        Объяснение — суждение аналитиков Basis. Числа в блоке ниже живые, из расчётной модели платформы.
      </p>

      {renderSections(0, at)}
      <BridgeCard article={article} onOpenCompany={onOpenCompany} />
      {renderSections(at, article.sections.length)}

      {(article.peers || []).length > 0 && (
        <section>
          <h2>Другие компании этого типа</h2>
          <p>Механика одна, но реализация разная — сравнение полезнее одного примера.</p>
          <div className="sprv-chips">
            {article.peers.map((p) => (
              <button key={p.ticker} type="button" className="sprv-chip"
                      onClick={() => onOpenCompany(p.ticker, "business")}>
                <b>{p.name}</b> <span className="bs-mono">{p.ticker}</span>
                {p.note ? <span className="note"> — {p.note}</span> : null}
              </button>
            ))}
          </div>
        </section>
      )}

      <section>
        <h2>Что с этим делать дальше</h2>
        <p>
          Механику вы теперь знаете — дальше её стоит приложить к конкретной бумаге:
          посмотреть, как эти же метрики выглядят у {article.bridge.nameGen || article.bridge.name},
          и сравнить с другими компаниями того же типа.
        </p>
        <div className="sprv-actions">
          <button type="button" className="sprv-cta"
                  onClick={() => onOpenCompany(article.bridge.ticker, article.bridge.tab)}>
            Разбор {article.bridge.nameGen || article.bridge.name} с оценкой Basis <ArrowRight size={15} />
          </button>
          {article.tool && (
            <button type="button" className="sprv-cta ghost" onClick={onOpenScreener}>
              {article.tool.label}
            </button>
          )}
        </div>
      </section>

      {(article.terms || []).length > 0 && (
        <section>
          <h2>Термины из статьи</h2>
          <div className="sprv-chips">
            {article.terms.map((t) => (
              <a key={t.href} className="sprv-chip" href={t.href}>{t.label}</a>
            ))}
          </div>
        </section>
      )}

      {related.length > 0 && (
        <section>
          <h2>Читать дальше</h2>
          <div className="sprv-cards">
            {related.map((r) => (
              <button key={r.slug} type="button" className="sprv-card"
                      onClick={() => onOpenArticle(r.slug)}>
                <span className="q">{r.question}</span>
                <span className="d">{r.answer.slice(0, 120)}…</span>
              </button>
            ))}
          </div>
        </section>
      )}

      <p className="sprv-note">
        Basis — независимый аналитический слой, а не брокер: мы не проводим сделок и не даём
        сигналов «купить» или «продать». Объяснения в статье — суждение, расчётные числа
        в блоке компании — оценка модели на текущей котировке.
      </p>
    </div>
  );
}

/* --------------------------------- термины --------------------------------- */
function Term({ term, onBack, onOpenTerm }) {
  useEffect(() => { window.scrollTo({ top: 0, behavior: "auto" }); }, [term.slug]);
  const related = (term.related || []).map((s) => TERMS.find((t) => t.slug === s)).filter(Boolean);
  return (
    <div className="sprv-article">
      <button type="button" className="sprv-back" onClick={onBack}>
        <ArrowLeft size={15} /> Все термины
      </button>
      <h1>{term.label}</h1>
      <div className="sprv-answer">
        <span className="lbl">Простыми словами</span>
        <p>{term.simple}</p>
      </div>
      {term.formula && (
        <p className="sprv-tagline">Формула: {term.formula}</p>
      )}
      {term.what && <section><h2>Зачем это инвестору</h2><p>{term.what}</p></section>}
      {term.caveat && (
        <section>
          <h2>Где ошибаются</h2>
          <p>{term.caveat}</p>
        </section>
      )}
      {related.length > 0 && (
        <section>
          <h2>Рядом по смыслу</h2>
          <div className="sprv-chips">
            {related.map((r) => (
              <button key={r.slug} type="button" className="sprv-chip" onClick={() => onOpenTerm(r.slug)}>
                {r.label}
              </button>
            ))}
          </div>
        </section>
      )}
      <p className="sprv-note">
        Определения — как эти величины считает и понимает Basis. Полные страницы терминов с
        примерами на реальных бумагах: <a href="/pokazateli/">показатели и термины</a>.
      </p>
    </div>
  );
}

function TermsIndex({ onOpenTerm }) {
  return (
    <>
      <p className="sprv-lead">
        Что означают величины, которые вы видите в карточках и скринере. Коротко, без
        учебника: определение, зачем смотреть и где обычно ошибаются.
      </p>
      <div className="sprv-cards">
        {TERMS.map((t) => (
          <button key={t.slug} type="button" className="sprv-card" onClick={() => onOpenTerm(t.slug)}>
            <span className="q">{t.label}</span>
            <span className="d">{t.simple.slice(0, 140)}…</span>
          </button>
        ))}
      </div>
    </>
  );
}

/* -------------------------- экономическая статистика -------------------------- */
function MacroIndex({ onOpenIndicator }) {
  const [rows, setRows] = useState(null);
  const [failed, setFailed] = useState(false);

  useEffect(() => {
    let alive = true;
    const ctl = new AbortController();
    const t = setTimeout(() => ctl.abort(), 15000);
    fetch(`${API}/api/market/macro`, { signal: ctl.signal })
      .then((r) => (r.ok ? r.json() : null))
      .then((d) => { if (alive) { Array.isArray(d) ? setRows(d) : setFailed(true); } })
      .catch(() => { if (alive) setFailed(true); })
      .finally(() => clearTimeout(t));
    return () => { alive = false; ctl.abort(); clearTimeout(t); };
  }, []);

  // Показываем российские показатели: справочник объясняет, что двигает НАШ рынок.
  // Мировые (44 из 85) живут в Обозревателе как фон — тащить их сюда значило бы
  // сделать список нечитаемым ради полноты.
  const list = useMemo(() => (rows || [])
    .filter((r) => r.display_group !== "retired" && (r.country === "ru" || r.display_group === "rate"))
    .filter((r) => r.influence_short || r.has_data), [rows]);

  if (failed) return <p className="sprv-lead">Показатели сейчас недоступны — они есть
    в разделе <a href="/?view=overview&obs=economy">Экономическая статистика</a>.</p>;
  if (!rows) return <p className="sprv-lead">Загружаю показатели…</p>;

  return (
    <>
      <p className="sprv-lead">
        Что означает каждый показатель и как он влияет на оценку бумаг. Значения живые —
        те же, что в Обозревателе; клик по показателю открывает его график там же.
      </p>
      <div className="sprv-cards">
        {list.map((r) => {
          const v = (r.values && (r.values.level || Object.values(r.values)[0])) || null;
          return (
            <button key={r.code} type="button" className="sprv-card"
                    onClick={() => onOpenIndicator(r.code)}>
              <span className="q">{r.title}</span>
              {v && v.value != null && (
                <span className="sprv-macro-val bs-mono">
                  {new Intl.NumberFormat("ru-RU", { maximumFractionDigits: 2 }).format(v.value)}
                  {r.unit_suffix || ""}
                  {v.as_of ? <span className="sprv-macro-date"> на {v.as_of}</span> : null}
                </span>
              )}
              <span className="d">{r.influence_short || "Показатель российской экономики."}</span>
              <span className="to">открыть график →</span>
            </button>
          );
        })}
      </div>
      <p className="sprv-note">
        Значения приходят из того же источника, что кормит Обозреватель: своей копии чисел
        здесь нет — иначе два экрана начали бы расходиться. Даты и источник видны на графике.
      </p>
    </>
  );
}

/* ---------------------------------- корень ---------------------------------- */
function Index({ tab, onTab, onOpenArticle, onOpenTerm, onOpenIndicator }) {
  return (
    <div className="sprv-index">
      <div className="sprv-head">
        <BookOpen size={18} />
        <h1>Справочник</h1>
      </div>

      <div className="sprv-tabs" role="tablist">
        {TABS.map((t) => {
          const Icon = t.icon;
          return (
            <button key={t.id} type="button" role="tab" aria-selected={tab === t.id}
                    className={`sprv-tab${tab === t.id ? " is-active" : ""}`}
                    onClick={() => onTab(t.id)}>
              <Icon size={14} /> {t.label}
            </button>
          );
        })}
      </div>

      {tab === "business" && (
        <>
          <p className="sprv-lead">
            Ответы на вопросы, с которыми инвестор приходит раньше, чем с тикером. Каждый
            ответ заканчивается не точкой, а разбором реальной компании — теорию сразу
            можно проверить на живых числах.
          </p>
          <div className="sprv-cards">
            {ARTICLES.map((a) => (
              <button key={a.slug} type="button" className="sprv-card" onClick={() => onOpenArticle(a.slug)}>
                <span className="q">{a.question}</span>
                <span className="d">{a.answer.slice(0, 150)}…</span>
                <span className="to">разбор: {a.bridge.name}</span>
              </button>
            ))}
          </div>
        </>
      )}

      {tab === "terms" && <TermsIndex onOpenTerm={onOpenTerm} />}
      {tab === "macro" && <MacroIndex onOpenIndicator={onOpenIndicator} />}
    </div>
  );
}

export default function GuideView({ initialSlug, onOpenCompany, onOpenScreener,
                                    onOpenIndicator, onSlugChange }) {
  // Адрес несёт и вкладку, и открытую статью: ?article=<слаг> для статьи,
  // ?article=term:<слаг> для термина. Иначе ссылкой на конкретный ответ не поделиться,
  // а «назад» браузера уводил бы из раздела целиком.
  const [slug, setSlug] = useState(initialSlug || null);
  const [tab, setTab] = useState(() => (String(initialSlug || "").startsWith("term:") ? "terms" : "business"));
  useEffect(() => {
    setSlug(initialSlug || null);
    if (String(initialSlug || "").startsWith("term:")) setTab("terms");
  }, [initialSlug]);

  const open = (s) => { setSlug(s); if (onSlugChange) onSlugChange(s); };

  const article = slug && !slug.startsWith("term:")
    ? ARTICLES.find((a) => a.slug === slug) : null;
  const term = slug && slug.startsWith("term:")
    ? TERMS.find((t) => t.slug === slug.slice(5)) : null;

  if (article) {
    return (
      <Article article={article} onOpenCompany={onOpenCompany} onOpenScreener={onOpenScreener}
               onOpenArticle={open} onBack={() => open(null)} />
    );
  }
  if (term) {
    return <Term term={term} onBack={() => open(null)} onOpenTerm={(s) => open(`term:${s}`)} />;
  }
  return (
    <Index tab={tab} onTab={setTab} onOpenArticle={open}
           onOpenTerm={(s) => open(`term:${s}`)}
           onOpenIndicator={onOpenIndicator} />
  );
}

/**
 * Раздел «Справочник» ВНУТРИ платформы (вкладка в навигации, ?view=guide).
 *
 * ЗАЧЕМ ОТДЕЛЬНЫЙ РАЗДЕЛ, ЕСЛИ ЕСТЬ ПРЕ-РЕНДЕРЕННЫЕ /spravochnik/<слаг>/ (владелец,
 * 11.09.2026): статика — это точка входа ИЗ ПОИСКА, одноразовая по своей природе. А тут
 * человек уже внутри платформы: у него шапка, поиск, история переходов, и статья должна
 * вести не «по ссылке наружу», а в тот же интерфейс — открыть карточку компании прямо
 * здесь, без перезагрузки страницы.
 *
 * 🔴 ПОЧЕМУ ЭТО НЕ ЛОМАЕТ ПОИСК (важно, тут легко наступить на грабли августа): раздел
 * живёт на СВОЁМ адресе `?view=guide`, а не подменяет собой статический `/spravochnik/…`.
 * Приложение НЕ перехватывает статические адреса справочника и не удаляет их текст —
 * именно перехват в августе стоил нам лучшей точки входа (/bonds/vdo/), когда робот
 * вместо статьи получал пустой каркас. Здесь два разных адреса с одним контентом:
 * индексируется статика, а внутри платформы работает этот раздел.
 *
 * ИСТОЧНИК ТЕКСТА ОДИН — `./content.js`, тот же файл читает генератор пре-рендера
 * (scripts/generate-spravochnik.js). Копии текста быть не должно: разъедутся молча.
 */
import React, { useEffect, useState } from "react";
import { ArrowLeft, ArrowRight, BookOpen } from "lucide-react";
import ARTICLES from "./content";
import "../styles/spravochnik.css";

const API = process.env.REACT_APP_API_URL || "https://nikitasoin-basis-a772.twc1.net";

const fmtMoney = (v) => (v == null ? "—"
  : new Intl.NumberFormat("ru-RU", { maximumFractionDigits: v >= 100 ? 0 : 2 }).format(v) + " ₽");
const fmtPct = (v) => (v == null ? "—"
  : new Intl.NumberFormat("ru-RU", { maximumFractionDigits: 1 }).format(Math.abs(v)) + "%");

/**
 * Живой блок компании-эталона. Числа берём из /bfv — того же движка, что считает
 * справедливую цену в карточке. Своей формулы здесь нет и быть не должно: две цифры
 * с разными методиками на одном сайте мы уже проходили.
 */
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

function Index({ onOpenArticle }) {
  return (
    <div className="sprv-index">
      <div className="sprv-head">
        <BookOpen size={18} />
        <h1>Справочник</h1>
      </div>
      <p className="sprv-lead">
        Ответы на вопросы, с которыми инвестор приходит раньше, чем с тикером: как устроен
        бизнес, что означает показатель, как оценивать бумагу. Каждый ответ заканчивается
        не точкой, а разбором реальной компании — теорию сразу можно проверить на живых числах.
      </p>

      <h2>Как устроен бизнес</h2>
      <div className="sprv-cards">
        {ARTICLES.map((a) => (
          <button key={a.slug} type="button" className="sprv-card" onClick={() => onOpenArticle(a.slug)}>
            <span className="q">{a.question}</span>
            <span className="d">{a.answer.slice(0, 150)}…</span>
            <span className="to">разбор: {a.bridge.name}</span>
          </button>
        ))}
      </div>

      <h2>Термины и показатели</h2>
      <p>
        Определения метрик и рыночных терминов — в отдельном разделе с примерами на реальных
        бумагах: <a href="/pokazateli/">показатели и термины</a>. Макроэкономические ряды
        с графиками — в <a href="/ekonomicheskaya-statistika-rossii/">экономической статистике</a>.
      </p>
    </div>
  );
}

export default function GuideView({ initialSlug, onOpenCompany, onOpenScreener, onSlugChange }) {
  const [slug, setSlug] = useState(initialSlug || null);
  useEffect(() => { setSlug(initialSlug || null); }, [initialSlug]);

  const open = (s) => { setSlug(s); if (onSlugChange) onSlugChange(s); };
  const article = slug ? ARTICLES.find((a) => a.slug === slug) : null;

  if (!article) return <Index onOpenArticle={open} />;
  return (
    <Article
      article={article}
      onOpenCompany={onOpenCompany}
      onOpenScreener={onOpenScreener}
      onOpenArticle={open}
      onBack={() => open(null)}
    />
  );
}

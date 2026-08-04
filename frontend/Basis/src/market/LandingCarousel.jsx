import React, { useCallback, useEffect, useRef, useState } from "react";
import SLIDES from "./landingCarouselSlides";

// =============================================================
// КАРУСЕЛЬ СКРИНШОТОВ ПЛАТФОРМЫ — единственный интерактивный React-узел
// лендинга (остальное — HTML-строка landingHtml.js).
//
// Владелец (2026-08-04): «лендинг очень перегружен, его нужно сильно короче,
// в двух словах раскрыть ценность и показать картинки с платформы». Пять
// секций-простыней про Обозреватель/Скринер/Портфель/Стресс-тест схлопнуты
// сюда — вместо прозы про экран показан сам экран.
//
// Механика — гибрид, БЕЗ библиотек (в package.json нет ни одной каруселей/
// жестов, и незачем):
//   • физикой жеста владеет CSS scroll-snap — свайп и инерция на телефоне
//     бесплатны и родные;
//   • тонкий JS только ЧИТАЕТ активный индекс (IntersectionObserver,
//     threshold 0.6) для точек и стрелок — два источника позиции не
//     конкурируют, поэтому точки не «дёргаются» на середине жеста;
//   • автоплей — setInterval + тот же scrollTo, ПОЛНАЯ остановка (не
//     замедление) при наведении/касании/уходе со вкладки; при
//     prefers-reduced-motion интервал вообще не создаётся, а прокрутки идут
//     behavior:"auto".
// =============================================================

const AUTOPLAY_MS = 5500;

export default function LandingCarousel({ onRoute }) {
  const trackRef = useRef(null);
  const slideRefs = useRef([]);
  const [active, setActive] = useState(0);
  // Автоплей идёт, пока пользователь не взял управление на себя: наведение,
  // касание, уход со вкладки, а также ЛЮБОЕ ручное переключение (клик по
  // стрелке/точке/клавиатура) — после него навязывать своё движение уже
  // невежливо, поэтому останавливаем насовсем.
  const [autoplay, setAutoplay] = useState(true);
  const reducedRef = useRef(false);

  useEffect(() => {
    try {
      reducedRef.current = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
      if (reducedRef.current) setAutoplay(false);
    } catch {
      /* нет matchMedia — оставляем поведение по умолчанию */
    }
  }, []);

  const scrollToIndex = useCallback((i, smooth = true) => {
    const track = trackRef.current;
    const el = slideRefs.current[i];
    if (!track || !el) return;
    // scrollTo по вычисленному offset, а не scrollIntoView: последний
    // прокручивает ВСЮ страницу к карусели (лендинг скроллится внутри
    // .app-shell), и первый же автоплей утаскивал бы читателя из hero.
    track.scrollTo({ left: el.offsetLeft - track.offsetLeft, behavior: smooth && !reducedRef.current ? "smooth" : "auto" });
  }, []);

  const goTo = useCallback(
    (i) => {
      const next = (i + SLIDES.length) % SLIDES.length;
      setAutoplay(false);
      setActive(next);
      scrollToIndex(next);
    },
    [scrollToIndex]
  );

  // Активный индекс читается из реального положения скролла — источник правды
  // один (сам трек), поэтому свайп, стрелки и автоплей не расходятся.
  useEffect(() => {
    const track = trackRef.current;
    if (!track || typeof IntersectionObserver === "undefined") return undefined;
    const io = new IntersectionObserver(
      (entries) => {
        entries.forEach((e) => {
          if (!e.isIntersecting) return;
          const idx = slideRefs.current.indexOf(e.target);
          if (idx >= 0) setActive(idx);
        });
      },
      { root: track, threshold: 0.6 }
    );
    slideRefs.current.forEach((el) => el && io.observe(el));
    return () => io.disconnect();
  }, []);

  useEffect(() => {
    if (!autoplay) return undefined;
    const id = setInterval(() => {
      setActive((cur) => {
        const next = (cur + 1) % SLIDES.length;
        scrollToIndex(next);
        return next;
      });
    }, AUTOPLAY_MS);
    return () => clearInterval(id);
  }, [autoplay, scrollToIndex]);

  // Вкладку свернули/ушли на другую — автоплей продолжал бы «проматывать»
  // карусель в никуда и вернул бы человека к произвольному слайду.
  useEffect(() => {
    const onVis = () => {
      if (document.hidden) setAutoplay(false);
    };
    document.addEventListener("visibilitychange", onVis);
    return () => document.removeEventListener("visibilitychange", onVis);
  }, []);

  const onKeyDown = (e) => {
    if (e.key === "ArrowRight") {
      e.preventDefault();
      goTo(active + 1);
    } else if (e.key === "ArrowLeft") {
      e.preventDefault();
      goTo(active - 1);
    }
  };

  const openSlide = (slide) => {
    setAutoplay(false);
    if (onRoute) onRoute(slide.route);
  };

  return (
    <section className="band lc-band" id="platform">
      <div className="wrap">
        <div className="sec-head" style={{ marginBottom: 34 }}>
          <div className="eyebrow rv">Платформа</div>
          <h2 className="sh rv d1" style={{ marginLeft: "auto", marginRight: "auto" }}>
            Пять экранов, на которых собирается решение
          </h2>
          <p className="lead rv d2">
            Ниже — сама платформа, а не иллюстрации к ней: карточка компании, фон рынка, скринер, портфель и стресс-тест.
          </p>
        </div>

        <div
          className="lc rv d2"
          role="region"
          aria-roledescription="карусель"
          aria-label="Экраны платформы Basis"
          tabIndex={0}
          onKeyDown={onKeyDown}
          onMouseEnter={() => setAutoplay(false)}
          onTouchStart={() => setAutoplay(false)}
        >
          <div className="lc-track" ref={trackRef}>
            {SLIDES.map((s, i) => (
              <figure
                className="lc-slide"
                key={s.id}
                ref={(el) => {
                  slideRefs.current[i] = el;
                }}
                aria-roledescription="слайд"
                aria-label={`${i + 1} из ${SLIDES.length}: ${s.kicker}`}
              >
                <button type="button" className="lc-shot" onClick={() => openSlide(s)} aria-label={`${s.cta} — ${s.kicker}`}>
                  <img src={s.img} alt={s.alt} loading={i === 0 ? "eager" : "lazy"} decoding="async" draggable="false" />
                </button>
                <figcaption className="lc-cap">
                  <span className="lc-kicker">{s.kicker}</span>
                  <p className="lc-text">{s.caption}</p>
                  <button type="button" className="lc-link" onClick={() => openSlide(s)}>
                    {s.cta}
                    <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" aria-hidden="true">
                      <path d="M5 12h13M13 6l6 6-6 6" />
                    </svg>
                  </button>
                </figcaption>
              </figure>
            ))}
          </div>

          <button type="button" className="lc-arrow lc-arrow-prev" onClick={() => goTo(active - 1)} aria-label="Предыдущий экран">
            <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" aria-hidden="true">
              <path d="M15 6l-6 6 6 6" />
            </svg>
          </button>
          <button type="button" className="lc-arrow lc-arrow-next" onClick={() => goTo(active + 1)} aria-label="Следующий экран">
            <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" aria-hidden="true">
              <path d="M9 6l6 6-6 6" />
            </svg>
          </button>
        </div>

        <div className="lc-dots" role="tablist" aria-label="Выбор экрана">
          {SLIDES.map((s, i) => (
            <button
              key={s.id}
              type="button"
              role="tab"
              aria-selected={i === active}
              aria-label={s.kicker}
              className={`lc-dot${i === active ? " on" : ""}`}
              onClick={() => goTo(i)}
            />
          ))}
        </div>
      </div>
    </section>
  );
}

import React, { useEffect, useState } from "react";
import { X } from "lucide-react";
import { usePrefersReducedMotion } from "../design/primitives";
import "./tour.css";

// =============================================================
// ОВЕРЛЕЙ ЖИВОГО ТУРА — подсветка реального блока + панель-рассказчик.
//
// 🔴 ПЕРЕДЕЛАНО 2026-08-05 по замечаниям владельца после первого прогона:
//   1. «менюшка серая, обычная, просто с текстом — нужно что-то более яркое,
//      запоминающееся» → панель получила медную шапку с прогрессом шагов,
//      серифный заголовок (Fraunces) и моно-счётчик, как в дизайн-системе.
//   2. «менюшка то в одном месте, то в другом — нужно в одном месте» → панель
//      больше НЕ якорится к подсвеченному блоку. Она стоит в ФИКСИРОВАННОМ
//      углу (снизу справа на десктопе, снизу на всю ширину на телефоне) и
//      уезжает в противоположный угол ТОЛЬКО если подсветка попала прямо под
//      неё — то есть двигается лишь чтобы не закрыть то, о чём рассказывает.
//
// Подсветка — 4 div-скрима вокруг цели + кольцо + прозрачный перехватчик
// кликов (не SVG-маска: проще и предсказуемее кросс-браузерно, без новых
// зависимостей). Клик по подсвеченному элементу = «Далее».
//
// z-index 190 у скрима/кольца, 191 у панели — выше TopNav(40) и мобильных
// шторок (100–150), ниже AuthModal(200, styles/account.css).
// =============================================================

const Z = 190;
const PANEL_W = 380;
const EDGE = 20;

function computeSpot(rect) {
  if (!rect) return null;
  const PAD = 8;
  return {
    top: Math.max(0, rect.top - PAD),
    left: Math.max(0, rect.left - PAD),
    width: rect.width + PAD * 2,
    height: rect.height + PAD * 2,
  };
}

function useViewportSize() {
  const [size, setSize] = useState(() => ({
    w: typeof window !== "undefined" ? window.innerWidth : 0,
    h: typeof window !== "undefined" ? window.innerHeight : 0,
  }));
  useEffect(() => {
    const onResize = () => setSize({ w: window.innerWidth, h: window.innerHeight });
    window.addEventListener("resize", onResize);
    return () => window.removeEventListener("resize", onResize);
  }, []);
  return size;
}

// Единственная причина, по которой панель вообще меняет место: она перекрыла
// бы подсвеченный блок. Тогда уходит в противоположный угол по горизонтали —
// это читается как «подвинулся, чтобы показать», а не как прыжки по экрану.
function panelSide(spot, viewport) {
  if (!spot || viewport.w < 900) return "right";
  const panelLeft = viewport.w - PANEL_W - EDGE;
  const overlapsX = spot.left + spot.width > panelLeft;
  const overlapsY = spot.top + spot.height > viewport.h * 0.45;
  return overlapsX && overlapsY ? "left" : "right";
}

function TourPanel({ side, step, stepIndex, totalSteps, children }) {
  const progress = totalSteps > 0 ? ((stepIndex + 1) / totalSteps) * 100 : 0;
  return (
    <div className={`tour-panel tour-panel--${side}`} style={{ zIndex: Z + 1 }} role="dialog" aria-modal="false" aria-label={step ? `Экскурс, шаг ${stepIndex + 1} из ${totalSteps}` : "Экскурс по платформе"}>
      <div className="tour-panel-bar" aria-hidden="true">
        <i style={{ width: `${step ? progress : 0}%` }} />
      </div>
      {children}
    </div>
  );
}

function WelcomeCard({ side, reduced, onStart, onDismiss }) {
  useEffect(() => {
    const onKey = (e) => {
      if (e.key === "Escape") onDismiss();
    };
    document.addEventListener("keydown", onKey);
    return () => document.removeEventListener("keydown", onKey);
  }, [onDismiss]);

  return (
    <TourPanel side={side} step={null} stepIndex={0} totalSteps={0}>
      <div className={`tour-panel-body${!reduced ? " tour-panel--enter" : ""}`}>
        <div className="tour-head">
          <span className="tour-kicker">Экскурс по платформе</span>
          <button type="button" className="tour-x" aria-label="Не сейчас — закрыть приглашение" onClick={onDismiss}>
            <X size={15} />
          </button>
        </div>
        <h3 className="tour-title">Показать Basis за две минуты?</h3>
        <p className="tour-text">
          Пройдём по реальным экранам платформы — рынок, разбор компании, скринер, обозреватель, портфель и стресс-тест.
          Без слайдов и без регистрации; прервать можно в любой момент.
        </p>
        <div className="tour-actions">
          <button type="button" className="tour-btn tour-btn--primary" onClick={onStart}>Начать экскурс</button>
          <button type="button" className="tour-btn tour-btn--ghost" onClick={onDismiss}>Не сейчас</button>
        </div>
      </div>
    </TourPanel>
  );
}

function RunningOverlay({ tour, reduced }) {
  const { step, stepIndex, totalSteps, isLastStep, targetRect, targetStatus, next, prev, finish, pauseTour } = tour;
  const viewport = useViewportSize();
  const spot = targetStatus === "ready" ? computeSpot(targetRect) : null;
  const side = panelSide(spot, viewport);

  const onAdvance = () => (isLastStep ? finish() : next());
  const onClose = () => pauseTour("manual");

  useEffect(() => {
    const onKey = (e) => {
      if (e.key === "Escape") onClose();
    };
    document.addEventListener("keydown", onKey);
    return () => document.removeEventListener("keydown", onKey);
    // onClose оборачивает pauseTour (стабильная ссылка — useCallback в
    // useTourEngine), поэтому [pauseTour] — полный список зависимостей.
  }, [pauseTour]);

  if (!step) return null;

  return (
    <>
      {spot ? (
        <>
          <div className="tour-scrim" style={{ position: "fixed", top: 0, left: 0, width: "100vw", height: spot.top, zIndex: Z }} onClick={onClose} />
          <div
            className="tour-scrim"
            style={{ position: "fixed", top: spot.top + spot.height, left: 0, width: "100vw", height: Math.max(0, viewport.h - (spot.top + spot.height)), zIndex: Z }}
            onClick={onClose}
          />
          <div className="tour-scrim" style={{ position: "fixed", top: spot.top, left: 0, width: spot.left, height: spot.height, zIndex: Z }} onClick={onClose} />
          <div
            className="tour-scrim"
            style={{ position: "fixed", top: spot.top, left: spot.left + spot.width, width: Math.max(0, viewport.w - (spot.left + spot.width)), height: spot.height, zIndex: Z }}
            onClick={onClose}
          />
          <div
            aria-hidden="true"
            className={`tour-ring${!reduced ? " tour-ring--pulse" : ""}`}
            style={{ position: "fixed", top: spot.top, left: spot.left, width: spot.width, height: spot.height, zIndex: Z, borderRadius: 12 }}
          />
          {/* перехватчик кликов — клик/Enter по подсвеченному элементу = «Далее» */}
          <div
            role="button"
            tabIndex={0}
            aria-label="Подсвеченный элемент шага тура — перейти дальше"
            onClick={onAdvance}
            onKeyDown={(e) => {
              if (e.key === "Enter" || e.key === " ") {
                e.preventDefault();
                onAdvance();
              }
            }}
            style={{ position: "fixed", top: spot.top, left: spot.left, width: spot.width, height: spot.height, zIndex: Z, cursor: "pointer", background: "transparent", border: 0, padding: 0 }}
          />
        </>
      ) : (
        // «locating» (ещё ищем) / «missing» (не нашли за таймаут) — фон всё равно
        // приглушаем сплошным скримом: подсвечивать нечего, панель сама честно
        // объясняет статус.
        <div className="tour-scrim" style={{ position: "fixed", inset: 0, zIndex: Z }} onClick={onClose} />
      )}

      <TourPanel side={side} step={step} stepIndex={stepIndex} totalSteps={totalSteps}>
        <div key={step.id} className={`tour-panel-body${!reduced ? " tour-panel--enter" : ""}`}>
          <div className="tour-head">
            <span className="tour-kicker">
              Шаг <b className="tour-count">{stepIndex + 1}</b> из <b className="tour-count">{totalSteps}</b>
            </span>
            <button type="button" className="tour-x" aria-label="Закрыть экскурс" onClick={onClose}>
              <X size={15} />
            </button>
          </div>

          <h3 className="tour-title">{step.title}</h3>
          <p className="tour-text">{step.body}</p>

          {Array.isArray(step.inside) && step.inside.length > 0 && (
            <ul className="tour-inside">
              {step.inside.map((it) => (
                <li key={it.n}>
                  <b>{it.n}</b>
                  <span>{it.d}</span>
                </li>
              ))}
            </ul>
          )}

          {targetStatus === "missing" && (
            <p className="tour-note">Не нашли этот блок на экране прямо сейчас — возможно, он ещё грузится. Можно пойти дальше.</p>
          )}
          {isLastStep && step.outro && <p className="tour-note tour-note--outro">{step.outro}</p>}

          <div className="tour-actions tour-actions--split">
            <div>
              {stepIndex > 0 && (
                <button type="button" className="tour-btn tour-btn--ghost" onClick={prev}>Назад</button>
              )}
            </div>
            <div className="tour-actions">
              <button type="button" className="tour-btn tour-btn--ghost" onClick={onClose}>Пропустить</button>
              <button type="button" className="tour-btn tour-btn--primary" onClick={onAdvance} disabled={targetStatus === "locating"}>
                {isLastStep ? "Готово" : "Далее"}
              </button>
            </div>
          </div>
        </div>
      </TourPanel>
    </>
  );
}

function PauseToast({ toast }) {
  if (!toast) return null;
  const text =
    toast.reason === "auth"
      ? "Экскурс подождёт — форма входа важнее. Продолжить можно в разделе «Профиль»."
      : "Экскурс на паузе. Продолжить можно в разделе «Профиль» — там же кнопка «Продолжить экскурс».";
  return (
    <div key={toast.key} role="status" className="tour-toast tour-toast-pos" style={{ zIndex: Z + 1 }}>
      {text}
    </div>
  );
}

export default function TourOverlay({ tour }) {
  const reduced = usePrefersReducedMotion();
  if (tour.phase === "welcome") {
    return <WelcomeCard side="right" reduced={reduced} onStart={tour.start} onDismiss={tour.dismissWelcome} />;
  }
  if (tour.phase === "running") {
    return <RunningOverlay tour={tour} reduced={reduced} />;
  }
  // paused/idle/completed — тур ничего не блокирует; на экране может остаться
  // только уходящий тост о паузе.
  return <PauseToast toast={tour.toast} />;
}

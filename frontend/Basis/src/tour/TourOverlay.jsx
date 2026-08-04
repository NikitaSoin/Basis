import React, { useEffect, useLayoutEffect, useRef, useState } from "react";
import { X } from "lucide-react";
import { Button, IconButton, usePrefersReducedMotion } from "../design/primitives";
import "./tour.css";

// =============================================================
// ОВЕРЛЕЙ ЖИВОГО ТУРА — 4 div-скрима вокруг цели + декоративное кольцо +
// прозрачный «перехватчик» кликов поверх дыры (НЕ SVG-маска — см. план,
// проще и предсказуемее кросс-браузерно, без новых зависимостей). Клик по
// подсвеченному элементу трактуется как «Далее» — перехватчик не даёт
// реальному клику увести состояние приложения в обход движка тура.
//
// z-index 190 у всей группы (скрим/кольцо/перехватчик), 191 у самой карточки
// тултипа (чтобы читалась поверх кольца при случайном наложении на узких
// экранах) — выше TopNav(40)/мобильных шторок(100-150), ниже AuthModal(200,
// styles/account.css:336).
//
// Один параметр движка — `tour` (результат tour/useTourEngine.js).
// =============================================================

const Z = 190;

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

// Грубый якорь тултипа от прямоугольника спота + placement — в ПРОЦЕНТАХ
// трансформации (ox/oy), поэтому не нужно заранее знать реальный размер
// карточки. useClampedOffset ниже один раз докорректирует его в px, если
// карточка вылезла за safe-margin вьюпорта.
function anchorFor(spot, placement) {
  if (!spot) return null;
  const GAP = 16;
  switch (placement) {
    case "top":
      return { top: spot.top - GAP, left: spot.left + spot.width / 2, ox: -50, oy: -100 };
    case "left":
      return { top: spot.top + spot.height / 2, left: spot.left - GAP, ox: -100, oy: -50 };
    case "right":
      return { top: spot.top + spot.height / 2, left: spot.left + spot.width + GAP, ox: 0, oy: -50 };
    case "bottom":
    default:
      return { top: spot.top + spot.height + GAP, left: spot.left + spot.width / 2, ox: -50, oy: 0 };
  }
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

// Держит карточку тултипа целиком во вьюпорте: измеряет РЕАЛЬНЫЙ
// прямоугольник карточки после того, как анкор её уже расположил (грубо, по
// проценту transform), и один раз докорректирует смещением в px, если
// какой-то край вышел за safe-margin 16px.
function useClampedOffset(cardRef, anchor) {
  const [offset, setOffset] = useState({ dx: 0, dy: 0 });
  useLayoutEffect(() => {
    if (!anchor || !cardRef.current) {
      setOffset({ dx: 0, dy: 0 });
      return;
    }
    const margin = 16;
    const r = cardRef.current.getBoundingClientRect();
    let dx = 0;
    let dy = 0;
    if (r.left < margin) dx = margin - r.left;
    else if (r.right > window.innerWidth - margin) dx = window.innerWidth - margin - r.right;
    if (r.top < margin) dy = margin - r.top;
    else if (r.bottom > window.innerHeight - margin) dy = window.innerHeight - margin - r.bottom;
    setOffset((prev) => (prev.dx === dx && prev.dy === dy ? prev : { dx, dy }));
    // anchor.top/left меняются на каждый ре-скролл цели — специально считаем
    // офсет заново по значениям, а не по ссылке на объект anchor (?. — anchor
    // может быть null на первом рендере до готовности спота). НЕ добавляем
    // eslint-disable-комментарий на react-hooks/* — плагин не зарегистрирован
    // в package.json этого проекта, такой комментарий валит прод-сборку
    // целиком («Definition for rule ... was not found»), см. память
    // eslint-react-hooks-not-registered.
  }, [anchor?.top, anchor?.left, anchor?.ox, anchor?.oy]);
  return offset;
}

// Позиционирующая обёртка (position:fixed + transform) СНАРУЖИ, визуальная
// карточка с своей собственной enter-анимацией ВНУТРИ — иначе CSS-анимация
// transform на самом позиционирующем узле перебивала бы inline-transform
// клэмпа (карточка «прыгала» бы в угол на 200мс каждого шага).
function TooltipCard({ anchor, reduced, children }) {
  const cardRef = useRef(null);
  const offset = useClampedOffset(cardRef, anchor);
  if (!anchor) return null;
  const transform = `translate(calc(${anchor.ox}% + ${offset.dx}px), calc(${anchor.oy}% + ${offset.dy}px))`;
  return (
    <div
      ref={cardRef}
      className="tw-fixed tw-w-[336px] tw-max-w-[calc(100vw-32px)]"
      style={{ top: anchor.top, left: anchor.left, transform, zIndex: Z + 1 }}
    >
      <div
        role="dialog"
        aria-modal="false"
        className={`tw-bg-bg-overlay tw-border tw-border-border-subtle tw-rounded-lg tw-shadow-lg ${!reduced ? "tour-card--enter" : ""}`}
      >
        {children}
      </div>
    </div>
  );
}

function WelcomeCard({ rect, reduced, onStart, onDismiss }) {
  const spot = computeSpot(rect);
  const anchor = spot ? anchorFor(spot, "bottom") : { top: 68, left: 220, ox: 0, oy: 0 };

  useEffect(() => {
    const onKey = (e) => {
      if (e.key === "Escape") onDismiss();
    };
    document.addEventListener("keydown", onKey);
    return () => document.removeEventListener("keydown", onKey);
  }, [onDismiss]);

  return (
    <>
      {/* БЕЗ скрима (владелец: «фон живой, можно проигнорировать») — только
          мягкое декоративное кольцо у кнопки-якоря в шапке. */}
      {spot && (
        <div
          aria-hidden="true"
          className={`tour-ring${!reduced ? " tour-ring--pulse" : ""}`}
          style={{ position: "fixed", top: spot.top, left: spot.left, width: spot.width, height: spot.height, zIndex: Z, borderRadius: 10 }}
        />
      )}
      <TooltipCard anchor={anchor} reduced={reduced}>
        <div className="tw-p-4 tw-flex tw-flex-col tw-gap-3">
          <div className="tw-flex tw-items-start tw-justify-between tw-gap-2">
            <h3 className="tw-text-[15px] tw-font-semibold tw-text-text-primary tw-m-0">Экскурс по Basis</h3>
            <IconButton aria-label="Не сейчас — закрыть приглашение" size="sm" onClick={onDismiss}>
              <X size={14} />
            </IconButton>
          </div>
          <p className="tw-text-[13.5px] tw-text-text-secondary tw-leading-[1.55] tw-m-0">
            Покажем реальные экраны платформы по шагам — рынок, разбор компании, скринер, обозреватель, портфель, стресс-тест. Без слайдов и без регистрации, меньше двух минут.
          </p>
          <div className="tw-flex tw-items-center tw-gap-2 tw-mt-1">
            <Button variant="primary" size="sm" onClick={onStart}>
              Начать тур
            </Button>
            <Button variant="ghost" size="sm" onClick={onDismiss}>
              Не сейчас
            </Button>
          </div>
        </div>
      </TooltipCard>
    </>
  );
}

function RunningOverlay({ tour, reduced }) {
  const { step, stepIndex, totalSteps, isLastStep, targetRect, targetStatus, next, prev, finish, pauseTour } = tour;
  const viewport = useViewportSize();
  const spot = targetStatus === "ready" ? computeSpot(targetRect) : null;
  const placement = (step && step.placement) || "bottom";
  const anchor = spot
    ? anchorFor(spot, placement)
    : { top: Math.max(88, viewport.h * 0.22), left: viewport.w / 2, ox: -50, oy: 0 };

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
            style={{ position: "fixed", top: spot.top, left: spot.left, width: spot.width, height: spot.height, zIndex: Z, borderRadius: 10 }}
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
        // «locating» (ещё ищем) / «target-missing» (не нашли за таймаут) — фон
        // всё равно приглушаем сплошным скримом (без выреза, подсвечивать
        // нечего), карточка сама честно объясняет статус.
        <div className="tour-scrim" style={{ position: "fixed", inset: 0, zIndex: Z }} onClick={onClose} />
      )}

      <TooltipCard key={step.id} anchor={anchor} reduced={reduced}>
        <div className="tw-p-4 tw-flex tw-flex-col tw-gap-3">
          <div className="tw-flex tw-items-start tw-justify-between tw-gap-2">
            <span className="tw-text-[11px] tw-font-semibold tw-uppercase tw-tracking-wide tw-text-text-tertiary">
              Шаг {stepIndex + 1} из {totalSteps}
            </span>
            <IconButton aria-label="Закрыть тур" size="sm" onClick={onClose}>
              <X size={14} />
            </IconButton>
          </div>
          <h3 className="tw-text-[15px] tw-font-semibold tw-text-text-primary tw-m-0">{step.title}</h3>
          <p className="tw-text-[13.5px] tw-text-text-secondary tw-leading-[1.55] tw-m-0">{step.body}</p>
          {targetStatus === "missing" && (
            <p className="tw-text-[12.5px] tw-text-text-tertiary tw-leading-[1.5] tw-m-0">
              Не нашли этот блок на экране прямо сейчас — возможно, он ещё грузится. Можно пойти дальше.
            </p>
          )}
          {isLastStep && step.outro && (
            <p className="tw-text-[12.5px] tw-text-text-tertiary tw-leading-[1.5] tw-m-0 tw-pt-2 tw-border-t tw-border-border-subtle">{step.outro}</p>
          )}
          <div className="tw-flex tw-items-center tw-justify-between tw-mt-1">
            <div>
              {stepIndex > 0 && (
                <Button variant="ghost" size="sm" onClick={prev}>
                  Назад
                </Button>
              )}
            </div>
            <div className="tw-flex tw-items-center tw-gap-2">
              <Button variant="ghost" size="sm" onClick={onClose}>
                Пропустить
              </Button>
              <Button variant="primary" size="sm" onClick={onAdvance} disabled={targetStatus === "locating"}>
                {isLastStep ? "Готово" : "Далее"}
              </Button>
            </div>
          </div>
        </div>
      </TooltipCard>
    </>
  );
}

function PauseToast({ toast }) {
  if (!toast) return null;
  const text =
    toast.reason === "auth"
      ? "Тур подождёт — форма входа важнее. Продолжить можно кнопкой «Продолжить экскурс» в шапке сайта."
      : "Тур на паузе. Продолжить можно кнопкой «Продолжить экскурс» в шапке сайта.";
  return (
    <div
      key={toast.key}
      role="status"
      className="tour-toast--enter tw-fixed tw-left-1/2 -tw-translate-x-1/2 tw-max-w-[92vw] tw-w-[420px] tw-bg-bg-overlay tw-border tw-border-border-subtle tw-rounded-md tw-shadow-lg tw-px-4 tw-py-3 tw-text-[13px] tw-text-text-secondary tour-toast-pos"
      style={{ zIndex: Z + 1 }}
    >
      {text}
    </div>
  );
}

export default function TourOverlay({ tour }) {
  const reduced = usePrefersReducedMotion();
  if (tour.phase === "welcome") {
    return <WelcomeCard rect={tour.targetRect} reduced={reduced} onStart={tour.start} onDismiss={tour.dismissWelcome} />;
  }
  if (tour.phase === "running") {
    return <RunningOverlay tour={tour} reduced={reduced} />;
  }
  // paused/idle/completed — тур сам ушёл в паузу и НЕ блокирует ничего;
  // единственное, что может быть на экране, — уходящий тост о паузе.
  return <PauseToast toast={tour.toast} />;
}

import { logAction } from "../analytics";
import { useCallback, useEffect, useRef, useState } from "react";
import { usePrefersReducedMotion } from "../design/primitives";
import TOUR_STEPS from "./tourSteps";
import { waitForTourTarget } from "./tourLocator";

// =============================================================
// ДВИЖОК ЖИВОГО ТУРА — единственный источник правды (вызывается один раз в
// App(), пропы вниз в TopNav/TourOverlay — в проекте нет React.createContext
// нигде, см. Часть A плана expressive-bubbling-firefly.md).
//
// Стейт-машина: idle → welcome → running → paused/completed
//   - idle      — тур не идёт и приветствие не показывается прямо сейчас.
//   - welcome   — карточка-приглашение у кнопки в шапке, БЕЗ скрима.
//   - running   — активный шаг: скрим + подсветка + тултип.
//   - paused    — тур прерван (X/Escape/скрим/«Пропустить»/открылась форма
//                 входа) — сайт живёт обычной жизнью, кнопка в шапке помнит,
//                 на каком шаге остановились.
//   - completed — «Готово» на последнем шаге.
//
// localStorage-ключи (конвенция basis_ + snake_case, как у RegisterNudge):
//   basis_tour_seen_welcome_at — ставится В МОМЕНТ ПОКАЗА приветствия (не
//                                 на монтировании) — «новый визитор» = ТОЛЬКО
//                                 отсутствие этого ключа.
//   basis_tour_step            — id текущего шага, пишется на каждом
//                                 переходе, чистится при завершении.
//   basis_tour_completed_at    — ставится по «Готово» на последнем шаге.
// =============================================================

const WELCOME_KEY = "basis_tour_seen_welcome_at";
const STEP_KEY = "basis_tour_step";
const COMPLETED_KEY = "basis_tour_completed_at";
const WELCOME_DELAY_MS = 1200;
const TOAST_MS = 4000;

function safeGet(key) {
  try {
    return localStorage.getItem(key);
  } catch {
    return null;
  }
}
function safeSet(key, value) {
  try {
    localStorage.setItem(key, value);
  } catch {
    /* приватный режим / квота — тур продолжает работать, просто без памяти */
  }
}
function safeRemove(key) {
  try {
    localStorage.removeItem(key);
  } catch {}
}

function readInitialPhase() {
  if (safeGet(COMPLETED_KEY)) return "completed";
  if (safeGet(STEP_KEY)) return "paused"; // мид-тур с прошлого визита — НЕ авто-резюме, только кнопкой
  return "idle";
}
function readInitialStepIndex() {
  const id = safeGet(STEP_KEY);
  if (id) {
    const idx = TOUR_STEPS.findIndex((s) => s.id === id);
    if (idx >= 0) return idx;
  }
  return 0;
}

/**
 * @param {{activeTab: string, navigate: (tab: string) => void, onOpenCompany: (v: string) => void, showAuthModal: boolean}} params
 */
export default function useTourEngine({ activeTab, navigate, onOpenCompany, showAuthModal }) {
  const reduced = usePrefersReducedMotion();

  const [phase, setPhase] = useState(readInitialPhase);
  const [stepIndex, setStepIndex] = useState(readInitialStepIndex);
  const [targetRect, setTargetRect] = useState(null);
  const [targetStatus, setTargetStatus] = useState("locating");
  const [toast, setToast] = useState(null);

  // Свежие пропы-функции без пере-подписки эффектов на каждый рендер App().
  const navigateRef = useRef(navigate);
  navigateRef.current = navigate;
  const onOpenCompanyRef = useRef(onOpenCompany);
  onOpenCompanyRef.current = onOpenCompany;

  const phaseRef = useRef(phase);
  useEffect(() => {
    phaseRef.current = phase;
  }, [phase]);

  const welcomeDoneRef = useRef(!!safeGet(WELCOME_KEY)); // уже показывали когда-либо
  const prevActiveTabRef = useRef(activeTab);
  const toastTimerRef = useRef(null);

  const showToast = useCallback((reason) => {
    if (toastTimerRef.current) clearTimeout(toastTimerRef.current);
    setToast({ reason, key: Date.now() });
    toastTimerRef.current = setTimeout(() => setToast(null), TOAST_MS);
  }, []);

  const pauseTour = useCallback(
    (reason = "manual") => {
      if (phaseRef.current !== "running") return;
      setPhase("paused");
      showToast(reason);
    },
    [showToast]
  );

  // ---- Приветствие: первый РЕАЛЬНЫЙ переход activeTab с "landing" на что-то
  // ещё (не монтирование App — лендинг не место для второго попапа поверх
  // собственных CTA). Взводится ОДИН раз за визит (welcomeDoneRef), таймер НЕ
  // отменяется последующими навигациями/ре-рендерами App — иначе пользователь,
  // успевший перейти на 2-й экран за 1200мс, никогда бы не увидел приглашение
  // (см. ловушку с производным render-time булевым флагом в комментарии к PR).
  const welcomeTimerRef = useRef(null);
  useEffect(() => {
    const prev = prevActiveTabRef.current;
    prevActiveTabRef.current = activeTab;
    if (welcomeDoneRef.current) return;
    if (phase !== "idle") return;
    if (prev === "landing" && activeTab !== "landing") {
      welcomeDoneRef.current = true;
      welcomeTimerRef.current = setTimeout(() => {
        safeSet(WELCOME_KEY, String(Date.now())); // «в момент показа», не в момент перехода
        // Верх воронки экскурса. Владелец 2026-08-05: «скольким показался и сколько прошло» —
        // без этих событий вопрос неотвечаем: тур жил в localStorage и наружу не сообщал ничего.
        logAction("tour_shown");
        setPhase((p) => (p === "idle" ? "welcome" : p)); // не перебиваем, если пользователь уже что-то сделал руками
      }, WELCOME_DELAY_MS);
    }
    // eslint: react-hooks не подключён в проекте (см. память
    // eslint-react-hooks-not-registered) — зависимости оставлены по смыслу,
    // а не по автогенератору. Cleanup НЕ отменяет таймер здесь (см. эффект
    // ниже) — иначе КАЖДЫЙ ре-рендер с изменившимся activeTab/phase отменял
    // бы уже взведённое приглашение.
  }, [activeTab, phase]);
  // Таймер приветствия отменяется ТОЛЬКО при полном размонтировании App —
  // отдельный эффект с пустыми deps, чтобы не зависеть от смены activeTab/phase.
  useEffect(
    () => () => {
      if (welcomeTimerRef.current) clearTimeout(welcomeTimerRef.current);
    },
    []
  );

  // ---- Пауза-по-требованию: открылась форма входа (тот же принцип, что уже
  // гасит RegisterNudge, App.js) — тур не должен спорить с модалкой.
  useEffect(() => {
    if (showAuthModal) pauseTour("auth");
  }, [showAuthModal, pauseTour]);

  // Приветствие БОЛЬШЕ НЕ ЯКОРИТСЯ к кнопке: точка входа переехала в «Профиль»
  // (владелец 2026-08-05), а сама панель стоит в фиксированном углу экрана —
  // измерять чужой прямоугольник незачем (tour/TourOverlay.jsx).

  // ---- Шаг активного тура: выполняет действие (navigate/openCompany), затем
  // ждёт цель локатором. Эффект завязан на [phase, stepIndex] — двойной
  // быстрый клик «Далее» меняет stepIndex дважды подряд: cleanup ПЕРВОГО
  // запуска отменяет его локатор (cancel()) и помечает alive=false ДО того,
  // как второй запуск стартует свой — гонки между двумя waitForTourTarget нет.
  useEffect(() => {
    if (phase !== "running") return undefined;
    const step = TOUR_STEPS[stepIndex];
    if (!step) return undefined;

    let alive = true;
    let cleanupTrackers = null;

    setTargetStatus("locating");
    setTargetRect(null);

    safeSet(STEP_KEY, step.id); // пишем НА КАЖДОМ переходе шага (владелец: возврат должен знать, где остановились)

    if (step.action === "navigate" && navigateRef.current) navigateRef.current(step.actionArg);
    else if (step.action === "openCompany" && onOpenCompanyRef.current) onOpenCompanyRef.current(step.actionArg);

    const { promise, cancel } = waitForTourTarget(step.selector, { timeoutMs: 5000, intervalMs: 200 });

    promise.then((el) => {
      if (!alive) return;
      if (!el) {
        // target-missing (см. план): тултип остаётся без спотлайта, «Далее»
        // ждёт явного клика — не виснем и не проваливаемся молча.
        setTargetStatus("missing");
        setTargetRect(null);
        return;
      }
      try {
        // Всегда центрируем. Пробовал уводить широкие цели к верху (чтобы панель
        // тура в нижнем углу их не перекрывала) — стало ХУЖЕ: полоса вкладок
        // карточки sticky, при block:"start" она прилипает под верхнюю навигацию
        // и подсветка встаёт на шапку, а сами вкладки уезжают из кадра
        // (проверено на бою 2026-08-05). От широкой цели панель и так отъезжает
        // вбок — перекрытие остаётся лишь частичным.
        el.scrollIntoView({ block: "center", behavior: reduced ? "auto" : "smooth" });
      } catch {}
      const measure = () => {
        if (!alive) return;
        setTargetRect(el.getBoundingClientRect());
      };
      measure();
      setTargetStatus("ready");

      // Держим прямоугольник в синхроне, пока шаг активен: ResizeObserver на
      // самой цели + throttled (rAF) resize/scroll — без этого подсветка
      // «отклеивается» от контента во время доскролла/смены layout.
      let raf = null;
      const onFrame = () => {
        raf = null;
        measure();
      };
      const onDirty = () => {
        if (raf == null) raf = requestAnimationFrame(onFrame);
      };
      let ro = null;
      if (typeof ResizeObserver !== "undefined") {
        ro = new ResizeObserver(onDirty);
        ro.observe(el);
      }
      window.addEventListener("scroll", onDirty, { passive: true, capture: true });
      window.addEventListener("resize", onDirty);
      cleanupTrackers = () => {
        if (ro) ro.disconnect();
        window.removeEventListener("scroll", onDirty, { capture: true });
        window.removeEventListener("resize", onDirty);
        if (raf != null) cancelAnimationFrame(raf);
      };
    });

    return () => {
      alive = false;
      cancel();
      if (cleanupTrackers) cleanupTrackers();
    };
  }, [phase, stepIndex, reduced]);

  useEffect(
    () => () => {
      if (toastTimerRef.current) clearTimeout(toastTimerRef.current);
    },
    []
  );

  const start = useCallback(() => {
    setStepIndex(0);
    logAction("tour_started");
    setPhase("running");
  }, []);

  const dismissWelcome = useCallback(() => {
    logAction("tour_dismissed");
    setPhase("idle");
  }, []);

  const next = useCallback(() => {
    setStepIndex((i) => {
      const n = Math.min(TOUR_STEPS.length - 1, i + 1);
      // Номер шага в meta: по нему видно, НА КАКОМ шаге бросают. «Показали 100, прошли 12»
      // без этого не объясняет, что чинить.
      if (n !== i) logAction("tour_step", { step: n });
      return n;
    });
  }, []);

  const prev = useCallback(() => {
    setStepIndex((i) => Math.max(0, i - 1));
  }, []);

  const finish = useCallback(() => {
    safeRemove(STEP_KEY);
    safeSet(COMPLETED_KEY, String(Date.now()));
    logAction("tour_completed");
    setPhase("completed");
  }, []);

  const resume = useCallback(() => {
    setPhase("running");
  }, []);

  const onEntryClick = useCallback(() => {
    if (phase === "paused") {
      resume();
      return;
    }
    if (phase === "running") {
      pauseTour("manual");
      return;
    }
    // idle / welcome / completed → (ре)старт тура с шага 0, явный клик
    // владельца кнопки, никогда не автоматически.
    start();
  }, [phase, resume, pauseTour, start]);

  const step = phase === "running" ? TOUR_STEPS[stepIndex] : null;
  const isLastStep = stepIndex === TOUR_STEPS.length - 1;
  // Подпись кнопки в «Профиле» (единственная точка входа после 2026-08-05).
  const buttonLabel =
    phase === "paused" ? "Продолжить экскурс" : phase === "completed" ? "Пройти экскурс заново" : "Пройти экскурс";

  return {
    phase,
    step,
    stepIndex,
    totalSteps: TOUR_STEPS.length,
    isLastStep,
    targetRect,
    targetStatus,
    toast,
    buttonLabel,
    onEntryClick,
    start,
    dismissWelcome,
    next,
    prev,
    finish,
    pauseTour,
  };
}

import React, { useEffect, useRef, useState } from "react";
import { X } from "lucide-react";
import { Button } from "../design/primitives";
import "../styles/register-nudge.css";

// Отложенный ненавязчивый тост-приглашение к регистрации (владелец, 2026-08-02,
// уточнено 2026-08-02): «одну страницу посмотрел — не трогаем, перешёл на
// другую — не трогаем, перешёл на третью — тогда показываем. Или если человек
// пробыл на платформе 10 минут — вкидываем». Монтируется в App.js рядом с
// AuthModal, ТОЛЬКО когда !token — сам компонент не проверяет авторизацию
// повторно. `viewKey` — идентификатор текущего «экрана» (карточка компании/
// бумаги или раздел навигации, см. App.js), меняется при реальной навигации,
// НЕ при переключении вкладок внутри одной карточки.
//
// Механика триггера — ЧТО РАНЬШЕ:
// - PAGE_TRIGGER: 3-й отдельный экран за визит (2 смены viewKey после
//   стартового — пришёл на страницу 1, перешёл на 2, перешёл на 3 → показываем);
// - TIME_TRIGGER_MS: 10 минут на сайте, даже если пользователь ни разу не
//   переключился (читает один длинный разбор).
// - В момент показа сразу пишем localStorage-штамп (не только по клику
//   крестика) — так «уже видел в этой сессии» тоже гасит повтор при следующей
//   перезагрузке, даже если пользователь просто ушёл со страницы, не закрыв
//   тост явно.
// - COOLDOWN_MS — сколько молчим после показа. 5 дней: заметно реже, чем
//   «каждая перезагрузка» (это убивало бы доверие, владелец прямо это
//   отверг), но не «увидел один раз и забыли навсегда» — платформа даёт
//   пользователю ещё несколько напоминаний за первую неделю знакомства.
const DISMISS_KEY = "basis_reg_nudge_dismissed_at";
const PAGE_TRIGGER = 3; // считаем стартовый экран страницей №1
const TIME_TRIGGER_MS = 10 * 60 * 1000; // 10 минут
const COOLDOWN_MS = 5 * 24 * 60 * 60 * 1000; // 5 дней

export default function RegisterNudge({ onOpenAuth, viewKey }) {
  const [visible, setVisible] = useState(false);
  const armedRef = useRef(false); // прошли ли гейт cooldown — таймер/счётчик стоит
  const shownRef = useRef(false); // уже показали в этом монтировании — не триггерить дважды
  const pageCountRef = useRef(1); // стартовый экран — страница №1
  const lastViewKeyRef = useRef(viewKey);

  const trigger = () => {
    if (shownRef.current) return;
    shownRef.current = true;
    setVisible(true);
    try {
      localStorage.setItem(DISMISS_KEY, String(Date.now()));
    } catch {}
  };

  // Гейт cooldown + 10-минутный таймер — один раз на монтирование.
  useEffect(() => {
    let lastShownAt = 0;
    try {
      lastShownAt = Number(localStorage.getItem(DISMISS_KEY)) || 0;
    } catch {}
    // Недавно уже показывали (эта сессия ИЛИ более ранний визит в пределах
    // cooldown) — не планируем повторный показ вовсе.
    if (lastShownAt && Date.now() - lastShownAt < COOLDOWN_MS) return undefined;
    armedRef.current = true;
    const timer = setTimeout(trigger, TIME_TRIGGER_MS);
    return () => clearTimeout(timer);
  }, []);

  // Счётчик «страниц» — реагирует на смену viewKey (реальная навигация, не
  // ре-рендер той же страницы). Не считает, пока гейт cooldown не пройден.
  useEffect(() => {
    if (!armedRef.current) return;
    if (viewKey === lastViewKeyRef.current) return;
    lastViewKeyRef.current = viewKey;
    pageCountRef.current += 1;
    if (pageCountRef.current >= PAGE_TRIGGER) trigger();
  }, [viewKey]);

  const dismiss = () => setVisible(false);

  const handleRegister = () => {
    dismiss();
    onOpenAuth && onOpenAuth();
  };

  if (!visible) return null;

  return (
    <div
      role="status"
      aria-live="polite"
      className="reg-nudge tw-bg-bg-elevated tw-border tw-border-border-strong tw-rounded-lg tw-shadow-lg tw-p-4 tw-pr-9"
    >
      <button
        type="button"
        aria-label="Закрыть"
        onClick={dismiss}
        className="tw-absolute tw-top-2 tw-right-2 tw-inline-flex tw-items-center tw-justify-center tw-w-8 tw-h-8 tw-rounded-sm tw-border-0 tw-bg-transparent tw-text-text-tertiary hover:tw-text-text-primary hover:tw-bg-accent-soft tw-cursor-pointer tw-transition-colors tw-duration-150 focus-visible:tw-outline-none focus-visible:tw-shadow-focus"
      >
        <X size={15} aria-hidden="true" />
      </button>
      <p className="tw-font-sans tw-text-[13px] tw-leading-[1.5] tw-text-text-secondary tw-m-0 tw-mb-3 tw-pr-1">
        Для дальнейшего комфортного использования платформы рекомендуем пройти регистрацию — это быстро и не займёт много времени.
      </p>
      <Button variant="primary" size="sm" onClick={handleRegister}>
        Зарегистрироваться
      </Button>
    </div>
  );
}

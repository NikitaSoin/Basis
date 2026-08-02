import { useEffect, useRef } from "react";

// Отложенный автопоказ регистрации (владелец, 2026-08-02, уточнено 2026-08-02):
// «одну страницу посмотрел — не трогаем, перешёл на другую — не трогаем,
// перешёл на третью — тогда показываем. Или если человек пробыл на платформе
// 10 минут — вкидываем... высвечивается менюшка — пройдите регистрацию (ТАКАЯ
// ЖЕ, как если нажать кнопку войти), её можно закрыть — то есть это не
// обязательно». Т.е. триггер открывает РЕАЛЬНУЮ AuthModal (та же, что и кнопка
// «Войти» в шапке) — не отдельный тост: у AuthModal уже есть крестик/Escape/
// клик мимо для закрытия (см. account/AccountPanels.jsx), второй UI-поверхности
// не нужно. Компонент — чистая логика без собственного рендера (всегда null).
//
// Монтируется в App.js рядом с AuthModal, ТОЛЬКО когда !token И !showAuthModal
// (сам не проверяет авторизацию повторно). `viewKey` — идентификатор текущего
// «экрана» (карточка компании/бумаги или раздел навигации, см. App.js),
// меняется при реальной навигации, НЕ при переключении вкладок внутри одной
// карточки.
//
// Механика триггера — ЧТО РАНЬШЕ:
// - PAGE_TRIGGER: 3-й отдельный экран за визит (2 смены viewKey после
//   стартового — пришёл на страницу 1, перешёл на 2, перешёл на 3 → триггер);
// - TIME_TRIGGER_MS: 10 минут на сайте, даже если пользователь ни разу не
//   переключился (читает один длинный разбор).
// - В момент триггера сразу пишем localStorage-штамп — так «уже показывали
//   недавно» гасит повтор при следующей перезагрузке/после закрытия модалки
//   крестиком, даже если пользователь так и не зарегистрировался.
// - COOLDOWN_MS — сколько молчим после показа. 5 дней: заметно реже, чем
//   «каждая перезагрузка» (это убивало бы доверие, владелец прямо это
//   отверг), но не «увидел один раз и забыли навсегда».
const DISMISS_KEY = "basis_reg_nudge_dismissed_at";
const PAGE_TRIGGER = 3; // считаем стартовый экран страницей №1
const TIME_TRIGGER_MS = 10 * 60 * 1000; // 10 минут
const COOLDOWN_MS = 5 * 24 * 60 * 60 * 1000; // 5 дней

export default function RegisterNudge({ onOpenAuth, viewKey }) {
  const armedRef = useRef(false); // прошли ли гейт cooldown — таймер/счётчик стоит
  const firedRef = useRef(false); // уже сработали в этом монтировании — не триггерить дважды
  const pageCountRef = useRef(1); // стартовый экран — страница №1
  const lastViewKeyRef = useRef(viewKey);

  const trigger = () => {
    if (firedRef.current) return;
    firedRef.current = true;
    try {
      localStorage.setItem(DISMISS_KEY, String(Date.now()));
    } catch {}
    onOpenAuth && onOpenAuth();
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

  return null;
}

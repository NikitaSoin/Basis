import React, { useCallback, useEffect, useRef, useState } from "react";
import { MessageSquare, X } from "lucide-react";
import "../styles/assistant-nudge.css";

// =========================
// ПОДСКАЗКА «СПРОСИТЕ АССИСТЕНТА» ПРИ ЗАЛИПАНИИ (владелец 2026-08-20).
// Замысел: человек читает карточку или разбор и останавливается надолго — обычно
// это значит, что он во что-то упёрся. В этот момент и уместно сказать, что рядом
// есть ассистент с данными платформы, а не показывать баннер сразу при входе.
//
// «Залип» = экран открыт достаточно долго И при этом человек перестал
// взаимодействовать (не листает, не кликает, не печатает). Оба условия нужны:
// только время — поймает того, кто просто оставил вкладку; только простой —
// сработает через полминуты после открытия, когда читать ещё нечего.
//
// Чего здесь намеренно НЕТ: автопоказа при входе, повторов в том же разделе,
// перекрытия контента (панель у нижнего края, не поверх текста), «празднующих»
// анимаций (канон: анимации сдержанные, prefers-reduced-motion уважается).
// =========================

const DWELL_MS = 45_000;      // столько экран должен быть открыт, прежде чем предлагать
const IDLE_MS = 20_000;       // столько человек ничего не делает — вот это и есть «остановился»
const SNOOZE_KEY = "asst.nudge.snoozed";
const SNOOZE_MS = 6 * 3600_000;   // закрыл крестиком — молчим 6 часов
const MAX_PER_SESSION = 2;        // больше двух раз за сеанс не показываемся никому

let shownThisSession = 0;

function snoozed() {
  try {
    const t = Number(localStorage.getItem(SNOOZE_KEY) || 0);
    return t && Date.now() - t < SNOOZE_MS;
  } catch {
    return false;
  }
}

/**
 * @param {object}   context  {key, subject, question} — что человек сейчас читает
 *                            (subject — в винительном падеже: «карточку Сбербанка»).
 *                            key меняется → таймеры сбрасываются, показ снова возможен.
 * @param {function} onAsk    (question) => void — открыть ассистента с заготовленным вопросом.
 * @param {boolean}  disabled выключить (сам ассистент, лендинг, модалки).
 */
export function AssistantNudge({ context, onAsk, disabled = false }) {
  const [visible, setVisible] = useState(false);
  const shownForKey = useRef(null);
  const key = context && context.key;

  const hide = useCallback(() => setVisible(false), []);

  useEffect(() => {
    setVisible(false);
    if (disabled || !key || snoozed() || shownThisSession >= MAX_PER_SESSION) return undefined;

    const openedAt = Date.now();
    let lastAction = Date.now();
    let timer = null;

    const bump = () => { lastAction = Date.now(); };
    // Экскурс по платформе (tour/TourOverlay) живёт в том же нижнем правом углу и
    // сам ведёт человека по разделам — вторая панель рядом читалась бы как спам.
    const busyElsewhere = () => !!document.querySelector(".tour-panel, .fv-rail--open, .mv3-drawer--open, .m5-mrail--open");
    const check = () => {
      const now = Date.now();
      const readingLongEnough = now - openedAt >= DWELL_MS;
      const stoppedInteracting = now - lastAction >= IDLE_MS;
      if (readingLongEnough && stoppedInteracting && shownForKey.current !== key
          && document.visibilityState === "visible" && !busyElsewhere()) {
        shownForKey.current = key;
        shownThisSession += 1;
        setVisible(true);
        clearInterval(timer);
      }
    };

    const events = ["scroll", "pointerdown", "keydown", "wheel", "touchstart"];
    events.forEach((e) => window.addEventListener(e, bump, { passive: true }));
    timer = setInterval(check, 2500);
    return () => {
      clearInterval(timer);
      events.forEach((e) => window.removeEventListener(e, bump));
    };
  }, [key, disabled]);

  if (!visible || !context) return null;

  // Справа может стоять панель «Содержание» (design/ScrollRail) — не накрываем её:
  // это средство навигации по тому же тексту, который человек читает.
  let rightOffset = 20;
  try {
    const rail = document.querySelector(".srail, .srail-min");
    if (rail) rightOffset += Math.round(rail.getBoundingClientRect().width);
  } catch { /* нет DOM — берём отступ по умолчанию */ }

  // При заходе по прямой ссылке (/company/GAZP/ из поиска) приложение знает только
  // тикер, и подсказка говорила «карточку GAZP». Имя компании в этот момент уже
  // напечатано на экране — берём его оттуда, чтобы фраза читалась по-человечески.
  let subject = context.subject;
  if (context.nameFromCard) {
    try {
      const el = document.querySelector(".cc-identity-name");
      const nm = el && el.textContent.trim();
      if (nm && nm.length < 60 && nm !== context.nameFromCard) {
        subject = `карточку ${nm}`;
      }
    } catch { /* оставим исходную подпись */ }
  }

  const dismiss = () => {
    try { localStorage.setItem(SNOOZE_KEY, String(Date.now())); } catch { /* приватный режим */ }
    hide();
  };

  return (
    <aside className="asn" role="complementary" aria-label="Подсказка: спросить ассистента"
           style={rightOffset > 20 ? { right: rightOffset } : undefined}>
      <span className="asn-ic" aria-hidden="true"><MessageSquare size={15} /></span>
      <div className="asn-body">
        <b className="asn-title">Что-то осталось непонятным?</b>
        <span className="asn-text">
          Ассистент знает {subject || "эту страницу"} и всю базу Basis — цифры карточек,
          облигации и фонды, макро, разборы аналитиков. Спросите своими словами.
        </span>
      </div>
      <button type="button" className="asn-cta" onClick={() => { hide(); onAsk(context.question); }}>
        Спросить
      </button>
      <button type="button" className="asn-x" onClick={dismiss} aria-label="Закрыть подсказку">
        <X size={14} />
      </button>
    </aside>
  );
}

export default AssistantNudge;

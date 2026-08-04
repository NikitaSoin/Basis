// =============================================================
// ЛОКАТОР ЦЕЛИ ТУРА — тот же polling-паттерн, что уже есть в проекте
// (scrollToBlockWhenReady, App.js) — НЕ MutationObserver (шквал коллбэков
// на экранах с живыми котировками). Каждый тик: querySelector → проверка
// видимости (offsetParent !== null, элемент реально на экране, а не
// display:none/скрыт в неактивной вкладке) → проверка стабильности rect
// между ДВУМЯ последовательными тиками (защита от подсветки элемента в
// момент, когда скелетон схлопывается в контент и геометрия ещё прыгает).
//
// Возвращает { promise, cancel } — НЕ голый promise: caller должен уметь
// по-настоящему ОСТАНОВИТЬ поллинг (не просто проигнорировать результат),
// иначе быстрый двойной клик «Далее» плодит параллельные таймер-цепочки.
// =============================================================

const EPS = 0.5; // px — допуск «одинаковый» rect между тиками

function sameRect(a, b) {
  if (!a || !b) return false;
  return (
    Math.abs(a.top - b.top) < EPS &&
    Math.abs(a.left - b.left) < EPS &&
    Math.abs(a.width - b.width) < EPS &&
    Math.abs(a.height - b.height) < EPS
  );
}

/**
 * @param {string} selector — CSS-селектор цели (напр. '[data-tour="market"]')
 * @param {{timeoutMs?: number, intervalMs?: number}} opts
 * @returns {{promise: Promise<Element|null>, cancel: () => void}}
 *   promise разрешается найденным элементом ИЛИ null (таймаут/отмена/нет селектора).
 */
export function waitForTourTarget(selector, { timeoutMs = 5000, intervalMs = 200 } = {}) {
  let cancelled = false;
  let timer = null;
  let lastRect = null;
  const startedAt = Date.now();

  const promise = new Promise((resolve) => {
    if (!selector) {
      resolve(null);
      return;
    }
    const tick = () => {
      if (cancelled) {
        resolve(null);
        return;
      }
      let el = null;
      try {
        el = document.querySelector(selector);
      } catch {
        // селектор синтаксически некорректен — не должно случиться (селекторы
        // приходят из tourSteps.js, но лучше выйти честно, чем кинуть исключение
        // в чужой цикл рендера).
        resolve(null);
        return;
      }
      const visible = el && el.offsetParent !== null;
      if (visible) {
        const rect = el.getBoundingClientRect();
        // Таймаут проверяем и ЗДЕСЬ, а не только в ветке «элемента нет»: на
        // экранах с живыми котировками/анимацией высота цели может не
        // устаканиться никогда, и цикл крутился бы вечно по 200мс. Элемент
        // при этом уже виден — честнее подсветить «дышащий» блок, чем
        // молча поллить.
        if (sameRect(rect, lastRect) || Date.now() - startedAt >= timeoutMs) {
          resolve(el);
          return;
        }
        lastRect = rect;
        timer = setTimeout(tick, intervalMs);
        return;
      }
      // элемента нет / скрыт — сбрасываем «стабильность», иначе элемент,
      // который на миг мигнул тем же rect'ом до и после исчезновения, ложно
      // засчитается найденным.
      lastRect = null;
      if (Date.now() - startedAt >= timeoutMs) {
        resolve(null);
        return;
      }
      timer = setTimeout(tick, intervalMs);
    };
    tick();
  });

  const cancel = () => {
    cancelled = true;
    if (timer) {
      clearTimeout(timer);
      timer = null;
    }
  };

  return { promise, cancel };
}

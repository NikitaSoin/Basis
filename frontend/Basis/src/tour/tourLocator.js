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

// 🔴 «Видим» НЕ равно `offsetParent !== null`: у элементов с position:fixed
// offsetParent всегда null по спецификации — а все сайдбары разделов Basis
// именно fixed, и первая версия локатора молча не находила НИ ОДИН из них
// (шаги шли без подсветки, поймано прогоном 2026-08-05). Плюс мобильная
// шторка прячется через translateX(-100%): размеры у неё остаются, и по
// размерам она ложно «видима» — поэтому дополнительно проверяем, попадает ли
// прямоугольник в экран.
function isVisible(el) {
  if (!el) return false;
  const cs = window.getComputedStyle(el);
  if (cs.display === "none" || cs.visibility === "hidden" || parseFloat(cs.opacity || "1") === 0) return false;
  const r = el.getBoundingClientRect();
  if (r.width <= 1 || r.height <= 1) return false;
  const vw = window.innerWidth;
  const vh = window.innerHeight;
  if (r.right <= 0 || r.bottom <= 0 || r.left >= vw || r.top >= vh) return false;
  return true;
}

// Первый ВИДИМЫЙ элемент по списку селекторов — именно по приоритету списка, а не
// по порядку в документе (querySelector с запятой умеет только второе). Нужно для
// телефона: сайдбар раздела там скрыт в шторке, и целью становится кнопка её
// открытия — но только если сайдбара действительно нет на экране.
function firstVisible(selectors) {
  for (const sel of selectors) {
    let el = null;
    try {
      el = document.querySelector(sel);
    } catch {
      continue; // некорректный селектор — пропускаем, не роняя цикл рендера
    }
    if (isVisible(el)) return el;
  }
  return null;
}

/**
 * @param {string|string[]} selector — CSS-селектор цели или список по приоритету
 *   (напр. ['[data-tour="observer"]', '[data-tour="section-menu"]'])
 * @param {{timeoutMs?: number, intervalMs?: number}} opts
 * @returns {{promise: Promise<Element|null>, cancel: () => void}}
 *   promise разрешается найденным элементом ИЛИ null (таймаут/отмена/нет селектора).
 */
export function waitForTourTarget(selector, { timeoutMs = 5000, intervalMs = 200 } = {}) {
  let cancelled = false;
  let timer = null;
  let lastRect = null;
  const startedAt = Date.now();

  const selectors = Array.isArray(selector) ? selector.filter(Boolean) : selector ? [selector] : [];

  const promise = new Promise((resolve) => {
    if (!selectors.length) {
      resolve(null);
      return;
    }
    const tick = () => {
      if (cancelled) {
        resolve(null);
        return;
      }
      const el = firstVisible(selectors);
      const visible = !!el;
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

/**
 * Продуктовая аналитика приложения — досылка просмотров и событий в Яндекс.Метрику.
 *
 * ЗАЧЕМ: до 2026-08-01 платформа НЕ СОБИРАЛА о поведении пользователей ничего. Нельзя
 * было ответить даже на «сколько людей заходило» и «какие карточки открывают».
 *
 * 🔴 СЧЁТЧИК ЗАГРУЖАЕТ НЕ ЭТОТ МОДУЛЬ. Сниппет стоит прямо в <head> каждой страницы
 * (scripts/metrika.js) по двум причинам. Первая: Метрика просит размещать его как можно
 * ближе к началу страницы, чтобы визит засчитался, даже если человек закроет вкладку
 * через секунду — инициализация после монтирования React этого не даёт. Вторая, важнее:
 * 3757 страниц облигаций, фондов и фьючерсов вообще НЕ ГРУЗЯТ приложение, это чистый
 * статический HTML. Инициализируй мы счётчик здесь — весь поисковый трафик по конкретным
 * выпускам был бы не виден.
 *
 * Здесь остаётся только то, чего сниппет сам не умеет.
 *
 * 🔴 SPA-НЮАНС: адрес меняется через pushState, и счётчик этого НЕ ВИДИТ. Без явной
 * отправки за весь сеанс засчитается один просмотр — точка входа, — и отчёт «по
 * страницам» не покажет ни переходов между карточками, ни вкладок, то есть ровно то,
 * ради чего аналитику и ставят. Поэтому trackPageView() зовётся на каждой смене адреса.
 *
 * ПЕРВЫЙ просмотр отсюда НЕ отправляется: его уже отправил сниппет при загрузке. Иначе
 * каждая точка входа считалась бы дважды.
 */

/** Номер счётчика кладёт сниппет — так он не дублируется ещё и в .env. */
function counterId() {
  return (typeof window !== "undefined" && window.__BASIS_METRIKA_ID__) || "";
}

/** Просмотр страницы. Вызывать при КАЖДОЙ смене адреса, кроме первой загрузки. */
export function trackPageView(url, title) {
  const id = counterId();
  if (!id || typeof window === "undefined" || typeof window.ym !== "function") return;
  try {
    window.ym(id, "hit", url || window.location.pathname + window.location.search, {
      title: title || document.title,
    });
  } catch {
    // Аналитика не должна ронять приложение ни при каких обстоятельствах.
  }
}

/**
 * Продуктовое событие: что человек СДЕЛАЛ, а не куда зашёл — применил фильтр скрининга,
 * добавил бумагу в портфель, развернул блок карточки. params попадут в отчёт
 * «Параметры визитов».
 */
export function trackEvent(name, params) {
  const id = counterId();
  if (!id || typeof window === "undefined" || typeof window.ym !== "function") return;
  try {
    window.ym(id, "reachGoal", name, params || undefined);
  } catch { /* молча */ }
}

/** Оставлено для совместимости вызова из App.js: загрузка идёт сниппетом, здесь нечего делать. */
export function initAnalytics() {}

/* ─── Свой лог событий: то, чего Метрика не умеет ────────────────────────────────────
 * Метрика считает ВИЗИТЫ и не знает, кто их совершил. Она не ответит на вопрос
 * «пользователи с портфелем из пяти и более бумаг чаще открывают корреляции?» — а такие
 * вопросы и двигают продукт. Эти события ложатся в НАШУ базу рядом с users и portfolios,
 * поэтому джойнятся обычным SQL (см. /api/debug/sql-console).
 *
 * 🔴 ОТПРАВКА ПАЧКАМИ, А НЕ ПО СОБЫТИЮ. Запрос на каждый клик — это лишняя нагрузка на
 * бэкенд и подтормаживание интерфейса. Копим и шлём раз в несколько секунд, а также при
 * уходе со страницы через sendBeacon: он доставляет данные даже когда вкладку уже
 * закрывают, обычный fetch в этот момент отменяется.
 *
 * 🔴 БЕЗ ПЕРСОНАЛЬНЫХ ДАННЫХ: анонимный идентификатор устройства из localStorage и
 * идентификатор сессии. Ни почт, ни имён — их и не требуется, а хранить лишнее значит
 * брать на себя обязательства по 152-ФЗ без надобности.
 */
const API = process.env.REACT_APP_API_URL || "";
const KEY_ANON = "basisAnonId";

function anonId() {
  try {
    let v = localStorage.getItem(KEY_ANON);
    if (!v) {
      v = "a" + Math.random().toString(36).slice(2) + Date.now().toString(36);
      localStorage.setItem(KEY_ANON, v);
    }
    return v;
  } catch { return null; }
}

// Сессия живёт в памяти вкладки: перезагрузка = новая сессия, это и нужно для «как часто
// заходят».
const SESSION_ID = "s" + Math.random().toString(36).slice(2) + Date.now().toString(36);

let queue = [];
let timer = null;

function flush(useBeacon) {
  if (!queue.length || !API) return;
  const body = JSON.stringify({ events: queue.slice(0, 20) });
  queue = [];
  try {
    if (useBeacon && navigator.sendBeacon) {
      navigator.sendBeacon(`${API}/api/events`, new Blob([body], { type: "application/json" }));
      return;
    }
    const token = localStorage.getItem("token") || localStorage.getItem("basisToken");
    fetch(`${API}/api/events`, {
      method: "POST",
      headers: Object.assign({ "Content-Type": "application/json" },
        token ? { Authorization: `Bearer ${token}` } : {}),
      body,
      keepalive: true,
    }).catch(() => { /* аналитика не повод ломать экран */ });
  } catch { /* молча */ }
}

function push(kind, name, meta) {
  try {
    queue.push({
      kind, name: name || null,
      path: window.location.pathname + window.location.search,
      referrer: document.referrer || null,
      meta: meta || null,
      anon_id: anonId(), session_id: SESSION_ID,
    });
    if (queue.length >= 10) { flush(false); return; }
    if (!timer) timer = setTimeout(() => { timer = null; flush(false); }, 4000);
  } catch { /* молча */ }
}

/** Просмотр страницы в собственный лог (Метрике он уходит отдельно, см. trackPageView). */
export function logPageView() { push("pageview", null, null); }

/** Действие пользователя: открыл вкладку, применил фильтр, добавил бумагу. */
export function logAction(name, meta) { push("action", name, meta); }

/** Клик по заметному элементу. */
export function logClick(name, meta) { push("click", name, meta); }

// Досылаем накопленное, когда человек уходит: иначе теряется последнее и самое
// интересное — на чём именно он закрыл вкладку.
if (typeof window !== "undefined") {
  window.addEventListener("visibilitychange", () => {
    if (document.visibilityState === "hidden") flush(true);
  });
  window.addEventListener("pagehide", () => flush(true));
}

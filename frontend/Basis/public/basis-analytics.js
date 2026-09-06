/**
 * Сборщик собственной аналитики Basis — ОДИН файл на все типы страниц.
 *
 * ЗАЧЕМ ОТДЕЛЬНЫМ ФАЙЛОМ, А НЕ ВНУТРИ ПРИЛОЖЕНИЯ. У платформы три вида HTML, и приложение
 * грузят только два из них: ~3757 страниц облигаций, фондов и фьючерсов — чистая статика
 * без бандла. Пока сбор жил в src/analytics.js, весь поисковый трафик по конкретным
 * выпускам в наш лог НЕ ПОПАДАЛ ВООБЩЕ — а в Метрику попадал, потому что её счётчик стоит
 * во всех каркасах. Это и есть главная причина, по которой наши числа не сходились с её
 * числами: мы сравнивали приложение со всем сайтом.
 *
 * ЧТО ЗДЕСЬ ЕСТЬ ТАКОГО, ЧЕГО НЕ БЫЛО.
 * 1. ВРЕМЯ. Раньше писался только факт просмотра, поэтому «сколько провели на странице»
 *    считалось разностью между соседними событиями: визит из одной страницы давал ноль
 *    секунд, а последняя страница визита не учитывалась никогда. Теперь при уходе
 *    отправляется прожитое время и отдельно — время, когда вкладка была НА ЭКРАНЕ
 *    (фоновая вкладка не должна накручивать часы).
 * 2. ВИЗИТ ПЕРЕЖИВАЕТ ПЕРЕЗАГРУЗКУ. Идентификатор визита лежит в localStorage и
 *    протухает через 30 минут без активности — ровно как визит у Метрики. Раньше он жил
 *    в памяти вкладки: F5 или переход на статическую страницу начинали «новый визит», и
 *    визитов у нас выходило больше, чем есть на самом деле.
 * 3. ПРИЗНАКИ ЖИВОГО ЧЕЛОВЕКА. Скролл, клик, клавиша, тап — любой из них помечает
 *    просмотр как «с действием». Робот, обходящий сайт, их не делает, и по ним же потом
 *    отделяются люди — без грубого правила «визит короче пяти секунд = не человек»,
 *    которое выбрасывало настоящего читателя, открывшего одну страницу.
 *
 * ЧЕГО ЗДЕСЬ НЕТ НАМЕРЕННО: ни IP, ни строки браузера, ни размеров экрана, ни любых
 * других отпечатков устройства. Только идентификатор устройства (случайная строка,
 * которую мы сами и выдали), идентификатор визита, адрес страницы, источник перехода,
 * время и флаг navigator.webdriver — он один и сам себя объявляет автоматизацией.
 */
(function () {
  "use strict";
  if (typeof window === "undefined" || window.__basisAnalytics) return;

  var API = window.__BASIS_API_URL__ || "";
  if (!API) return;                       // некуда слать — молчим

  var K_ANON = "basisAnonId";
  var K_SESS = "basisSession";
  var K_CONSENT = "basis_consent_analytics";
  var SESSION_TIMEOUT_MS = 30 * 60 * 1000;   // как визит у Метрики

  /* 🔴 СОГЛАСИЕ ОБЯЗАТЕЛЬНО (07.09.2026). До нажатия «Принять» не собирается ничего:
     ни событий, ни счётчика Метрики. Идентификаторы, которые ставит аналитика,
     Роскомнадзор относит к персональным данным, а договором аналитика не покрывается —
     нужно согласие, причём ДО начала сбора, а не после. */
  var CONSENT_VERSION = "1.0";

  function consentState() {
    try {
      var raw = localStorage.getItem(K_CONSENT);
      return raw ? JSON.parse(raw) : null;
    } catch (e) { return null; }
  }

  function allowed() {
    var c = consentState();
    return !!(c && c.choice === "accept");
  }

  /** Записать выбор: в браузере всегда, на сервере — если человек вошёл в аккаунт. */
  function saveChoice(choice) {
    var rec = { v: CONSENT_VERSION, at: new Date().toISOString(), choice: choice };
    try { localStorage.setItem(K_CONSENT, JSON.stringify(rec)); } catch (e) { /* приватный режим */ }
    try {
      var token = localStorage.getItem("basis_token");
      var headers = { "Content-Type": "application/json" };
      if (token) headers.Authorization = "Bearer " + token;
      else {
        var g = null;
        try { g = localStorage.getItem("basis_guest_token"); } catch (e2) { /* нет */ }
        if (g) headers["X-Guest-Token"] = g;
      }
      if (token || headers["X-Guest-Token"]) {
        fetch(API + "/api/consents", {
          method: "POST", headers: headers,
          body: JSON.stringify({ kind: "analytics", version: CONSENT_VERSION,
                                 granted: choice === "accept" }),
        }).catch(function () { /* запись в браузере уже есть — этого достаточно */ });
      }
    } catch (e) { /* молча */ }
  }

  function rnd(p) { return p + Math.random().toString(36).slice(2) + Date.now().toString(36); }

  function anonId() {
    try {
      var v = localStorage.getItem(K_ANON);
      if (!v) { v = rnd("a"); localStorage.setItem(K_ANON, v); }
      return v;
    } catch (e) { return null; }
  }

  /** Идентификатор визита: тот же, пока перерыв меньше 30 минут. */
  function sessionId() {
    var now = Date.now();
    try {
      var raw = localStorage.getItem(K_SESS);
      var s = raw ? JSON.parse(raw) : null;
      if (!s || !s.id || !s.ts || now - s.ts > SESSION_TIMEOUT_MS) s = { id: rnd("s"), ts: now };
      else s.ts = now;
      localStorage.setItem(K_SESS, JSON.stringify(s));
      return s.id;
    } catch (e) { return rnd("s"); }
  }

  /* ── состояние текущего просмотра ─────────────────────────────────────────── */
  var view = null;

  function startView(path) {
    var now = Date.now();
    view = {
      path: path || (location.pathname + location.search),
      started: now,
      visibleFrom: document.visibilityState === "visible" ? now : 0,
      visibleMs: 0,
      engaged: false,
      sent: false,
    };
  }

  function visibleMs() {
    if (!view) return 0;
    var extra = view.visibleFrom ? Date.now() - view.visibleFrom : 0;
    return view.visibleMs + extra;
  }

  /* ── очередь отправки ─────────────────────────────────────────────────────── */
  var queue = [];
  var timer = null;

  function enqueue(ev, urgent) {
    if (!allowed()) return;
    ev.anon_id = anonId();
    ev.session_id = sessionId();
    ev.wd = navigator.webdriver === true ? true : undefined;
    queue.push(ev);
    if (urgent) flush(true);
    else if (queue.length >= 10) flush(false);
    else if (!timer) timer = setTimeout(function () { timer = null; flush(false); }, 4000);
  }

  function flush(useBeacon) {
    if (!queue.length) return;
    var body = JSON.stringify({ events: queue.slice(0, 20) });
    queue = [];
    try {
      if (useBeacon && navigator.sendBeacon) {
        // Единственный способ доставить событие, когда вкладку уже закрывают.
        // Заголовков он не умеет, поэтому такие события анонимны — но связаны с
        // человеком через идентификатор устройства и визита.
        navigator.sendBeacon(API + "/api/events", new Blob([body], { type: "application/json" }));
        return;
      }
      var token = null;
      try { token = localStorage.getItem("basis_token"); } catch (e) { /* приватный режим */ }
      var headers = { "Content-Type": "application/json" };
      if (token) headers.Authorization = "Bearer " + token;
      fetch(API + "/api/events", { method: "POST", headers: headers, body: body, keepalive: true })
        .catch(function () { /* аналитика не повод ломать экран */ });
    } catch (e) { /* молча */ }
  }

  /* ── публичные операции ───────────────────────────────────────────────────── */

  /** Просмотр страницы. При переходе внутри приложения сначала закрывает предыдущий. */
  function pageView(path) {
    var p = path || (location.pathname + location.search);
    // 🔴 Первый просмотр отправляет сборщик (он грузится раньше), а через секунду
    // приложение, смонтировавшись, зовёт то же самое для ТОЙ ЖЕ страницы. Без этой
    // проверки один заход дробился на огрызок в двести миллисекунд и настоящий
    // просмотр — в отчёте это выглядело как две страницы вместо одной.
    if (view && !view.sent && view.path === p && Date.now() - view.started < 3000) return;
    endView(false);
    startView(p);
    enqueue({
      kind: "pageview",
      path: view.path,
      referrer: document.referrer || null,
    }, false);
  }

  /** Закрыть текущий просмотр и отправить прожитое время. */
  function endView(urgent) {
    if (!view || view.sent) return;
    var dur = Date.now() - view.started;
    if (dur < 200) { view.sent = true; return; }   // мгновенный редирект — не просмотр
    view.sent = true;
    enqueue({
      // 🔴 Отдельный вид, а НЕ "action": иначе служебное закрытие просмотра попадает в
      // счётчик действий человека, и любой обход выглядит осмысленным визитом — ровно
      // та ошибка, из-за которой отсев роботов теряет смысл.
      kind: "viewend",
      path: view.path,
      duration_ms: dur,
      visible_ms: visibleMs(),
      engaged: view.engaged,
    }, urgent);
  }

  function action(name, meta) {
    // Признак «человек действовал» ставят ТОЛЬКО живые события ввода (см. ниже):
    // показ подсказки или автоматическое действие интерфейса им не является.
    enqueue({ kind: "action", name: name, path: location.pathname + location.search,
              meta: meta || null, engaged: view ? view.engaged : null }, false);
  }

  function click(name, meta) {
    if (view) view.engaged = true;
    enqueue({ kind: "click", name: name, path: location.pathname + location.search,
              meta: meta || null, engaged: true }, false);
  }

  /* ── человеческие сигналы ─────────────────────────────────────────────────── */
  function markEngaged() { if (view) view.engaged = true; }
  ["scroll", "pointerdown", "keydown", "touchstart", "wheel"].forEach(function (t) {
    window.addEventListener(t, markEngaged, { passive: true, once: false });
  });

  document.addEventListener("visibilitychange", function () {
    if (!view) return;
    if (document.visibilityState === "hidden") {
      if (view.visibleFrom) { view.visibleMs += Date.now() - view.visibleFrom; view.visibleFrom = 0; }
      // Вкладку могут закрыть прямо сейчас — досылаем накопленное.
      endView(true);
    } else if (!view.visibleFrom) {
      // Вернулись на вкладку: считаем это новым просмотром той же страницы, иначе
      // время «на экране» и факт возврата потеряются.
      view.visibleFrom = Date.now();
      if (view.sent) startView(view.path);
    }
  });
  window.addEventListener("pagehide", function () { endView(true); });

  /* ── Баннер согласия ───────────────────────────────────────────────────────
   * Живёт здесь, а не в приложении, по той же причине, что и сам сбор: страницы
   * облигаций, фондов и фьючерсов приложение не грузят, а спрашивать надо на всех.
   * Поэтому — чистый DOM и стили в атрибуте: ни React, ни внешнего CSS-файла,
   * которого на статической странице может не быть.
   *
   * Обе кнопки равнозначны по виду: согласие, где «Принять» — заметная кнопка, а
   * «Отклонить» — серая ссылка мелким шрифтом, добровольным не считается.
   */
  var bannerEl = null;

  function closeBanner() {
    if (bannerEl && bannerEl.parentNode) bannerEl.parentNode.removeChild(bannerEl);
    bannerEl = null;
  }

  function decide(choice) {
    saveChoice(choice);
    closeBanner();
    if (choice === "accept") {
      if (typeof window.__basisLoadMetrika === "function") window.__basisLoadMetrika();
      // 🔴 Сбрасываем состояние просмотра перед стартом. Пока согласия не было,
      // приложение всё равно звало pageView() (оно про согласие не знает), просмотр
      // молча открывался, а событие отбрасывалось. Без сброса защита от дубля решала,
      // что эту страницу уже посчитали, и первый разрешённый просмотр терялся —
      // именно он и пропал в проверке 07.09.2026.
      view = null;
      // Считаем страницу с момента согласия, а не задним числом.
      pageView();
    }
  }

  function showBanner() {
    if (bannerEl) return;
    var dark = window.matchMedia && window.matchMedia("(prefers-color-scheme: dark)").matches;
    var bg = dark ? "#1B1713" : "#FFFFFF";
    var ink = dark ? "#F2EDE4" : "#1F1B16";
    var muted = dark ? "#B8AE9F" : "#5A5248";
    var line = dark ? "#332C24" : "#E4DFD5";

    var el = document.createElement("div");
    el.setAttribute("role", "dialog");
    el.setAttribute("aria-label", "Аналитика посещений");
    el.style.cssText = "position:fixed;left:16px;right:16px;bottom:16px;z-index:2147483000;"
      + "max-width:560px;margin:0 auto;background:" + bg + ";color:" + ink + ";"
      + "border:1px solid " + line + ";border-radius:14px;padding:16px 18px;"
      + "box-shadow:0 10px 40px rgba(0,0,0,.18);font:14px/1.5 Inter,-apple-system,"
      + "'Segoe UI',Roboto,sans-serif";

    var text = document.createElement("div");
    text.style.cssText = "color:" + muted + ";margin-bottom:12px";
    text.innerHTML = "<strong style=\"color:" + ink + "\">Аналитика посещений.</strong> "
      + "Мы хотим считать, какими разделами Basis пользуются: собственная статистика на наших "
      + "серверах и Яндекс.Метрика. Метрика поставит cookie и передаст в ООО «Яндекс» данные о "
      + "вашем браузере и просмотрах. Без этого сайт работает полностью. "
      + "<a href=\"/privacy/\" style=\"color:#C97A4A\">Подробнее</a>";

    var row = document.createElement("div");
    row.style.cssText = "display:flex;gap:10px;flex-wrap:wrap";

    function button(label, choice) {
      var b = document.createElement("button");
      b.type = "button";
      b.textContent = label;
      b.style.cssText = "flex:1 1 140px;min-height:40px;border-radius:9px;cursor:pointer;"
        + "font:600 14px/1 Inter,sans-serif;border:1px solid " + line + ";"
        + "background:" + (dark ? "#241F19" : "#F7F5F0") + ";color:" + ink;
      b.onclick = function () { decide(choice); };
      return b;
    }
    row.appendChild(button("Принять", "accept"));
    row.appendChild(button("Отклонить", "reject"));

    el.appendChild(text);
    el.appendChild(row);
    (document.body || document.documentElement).appendChild(el);
    bannerEl = el;
  }

  window.__basisAnalytics = {
    pageView: pageView, action: action, click: click, endView: endView,
    anonId: anonId, sessionId: sessionId, allowed: allowed,
    // «Настройки аналитики» в подвале зовут это, чтобы переспросить и передумать.
    openConsent: function () { closeBanner(); showBanner(); },
    consent: consentState,
  };

  /* Старт. Согласие есть — считаем и грузим счётчик. Решения нет — спрашиваем.
     Отказ — молчим до тех пор, пока человек сам не откроет настройки. */
  if (allowed()) {
    if (typeof window.__basisLoadMetrika === "function") window.__basisLoadMetrika();
    pageView();
  } else if (!consentState()) {
    if (document.readyState === "loading") {
      document.addEventListener("DOMContentLoaded", showBanner);
    } else {
      showBanner();
    }
  }
})();

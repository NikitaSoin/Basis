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

  /* Согласие. Пока баннера нет, режим «спрашиваем» выключен: собираем всех, кроме тех,
     кто уже явно отказался. Когда баннер появится — включается одной строкой в каркасе:
     window.__BASIS_ANALYTICS_REQUIRE_CONSENT__ = true. */
  function allowed() {
    try {
      var raw = localStorage.getItem(K_CONSENT);
      var c = raw ? JSON.parse(raw) : null;
      if (c && c.choice === "reject") return false;
      if (window.__BASIS_ANALYTICS_REQUIRE_CONSENT__) return !!(c && c.choice === "accept");
      return true;
    } catch (e) { return !window.__BASIS_ANALYTICS_REQUIRE_CONSENT__; }
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

  window.__basisAnalytics = {
    pageView: pageView, action: action, click: click, endView: endView,
    anonId: anonId, sessionId: sessionId, allowed: allowed,
  };

  // Первый просмотр — сразу: на статических страницах больше некому его отправить.
  pageView();
})();

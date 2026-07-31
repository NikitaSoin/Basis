#!/usr/bin/env node
/**
 * Освежает ТОЛЬКО снапшот разборов отчётности перед генерацией SEO-страниц.
 *
 * ЗАЧЕМ ОТДЕЛЬНО ОТ fetch-seo-snapshots.js: тот снимает пять тяжёлых списков (одни
 * облигации — 4 МБ) с паузами по 2,5 с, его гонять на каждой сборке незачем — состав
 * облигаций и фондов меняется медленно. А вот отчёты выходят постоянно, и владелец
 * справедливо спросил: «при появлении нового отчёта страница не появится
 * автоматически?». Раньше — не появлялась: снапшот лежал в репозитории и обновлялся
 * руками. Теперь этот шаг встроен в `npm run build`, поэтому КАЖДЫЙ деплой подтягивает
 * свежие разборы, и страницы вида /company/OZON/otchet/ появляются сами.
 *
 * НАДЁЖНОСТЬ ВАЖНЕЕ СВЕЖЕСТИ: если API недоступен или отвечает медленно, скрипт молча
 * выходит с кодом 0, оставляя закоммиченный снапшот. Сборка на Timeweb НЕ должна падать
 * из-за сети — иначе один сетевой сбой роняет весь деплой ради обновления 49 страниц.
 */
"use strict";
const fs = require("fs");
const path = require("path");

const API = process.env.BASIS_API || "https://nikitasoin-basis-a772.twc1.net";
const TIMEOUT_MS = 20000;

async function grab(label, urlPath, pick, outFile) {
  const ctrl = new AbortController();
  const timer = setTimeout(() => ctrl.abort(), TIMEOUT_MS);
  try {
    const res = await fetch(`${API}${urlPath}`, {
      signal: ctrl.signal,
      headers: { "Accept-Encoding": "gzip" },
    });
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    const rows = pick(await res.json());
    if (!rows.length) throw new Error("пустой список");

    const out = path.join(__dirname, "data", outFile);
    fs.mkdirSync(path.dirname(out), { recursive: true });
    fs.writeFileSync(out, JSON.stringify({
      meta: { source: API, fetched_at: new Date().toISOString(), count: rows.length },
      rows,
    }), "utf8");
    console.log(`${label}: ${rows.length} шт. → снапшот обновлён`);
  } catch (e) {
    // Осознанно НЕ роняем сборку: страницы соберутся из последнего закоммиченного
    // снапшота, просто без самых свежих данных.
    console.log(`${label}: снапшот не обновлён (${e.message}) — беру закоммиченный`);
  } finally {
    clearTimeout(timer);
  }
}

async function main() {
  // Три быстрых запроса — всё, что меняется часто и должно попадать в статику само:
  // разборы отчётов, макропоказатели (ставка, инфляция, PMI…) и индексы.
  await grab("Разборы отчётов", "/api/market/earnings?limit=400",
    (d) => (Array.isArray(d) ? d : (d.reports || d.items || [])), "earnings-snapshot.json");
  await grab("Макропоказатели", "/api/market/macro",
    (d) => (Array.isArray(d) ? d : (d.indicators || [])).filter((x) => x && x.has_data),
    "macro-snapshot.json");
  await grab("Индексы", "/api/market/indices",
    (d) => (Array.isArray(d) ? d : (d.indices || [])), "indices-snapshot.json");
  // Секторальные индексы MOEX (10 шт.) живут в «пульсе», а не в /market/indices —
  // владелец перечислил их поимённо и попросил страницы под каждый.
  await grab("Секторальные индексы", "/api/market/pulse",
    (d) => ((d && d.sectors) || []), "sectors-snapshot.json");

  // Справедливая цена по всем бумагам — под страницы /company/<T>/spravedlivaya-tsena/.
  // Спрос на «справедливая цена акций <компании>» подтверждён подсказками Яндекса, а
  // BFV — то, чего нет у агрегаторов. Снимаем вместе с ценой и потенциалом, чтобы на
  // статической странице было видно, к какой цене относится оценка.
  await grab("Справедливая цена", "/api/screener/stocks?limit=400",
    (d) => (Array.isArray(d) ? d : (d.rows || []))
      .filter((r) => r && r.ticker && r.fair_value)
      .map((r) => ({
        ticker: r.ticker, fair_value: r.fair_value, price: r.price,
        upside_pct: r.upside_pct, source: r.fair_value_source,
      })),
    "fair-value-snapshot.json");

  // Ближайшие дивиденды: сумма, дата отсечки и «купить до». Замер спроса показал, что
  // дивиденды спрашивают С УТОЧНЕНИЕМ — «мтс дивиденды 2026 дата выплаты», «дивиденды
  // сбербанка когда выплатят». Без дат страница отвечает на половину вопроса.
  await grab("Ближайшие дивиденды", "/api/market/calendar?limit=800",
    (d) => (Array.isArray(d) ? d : (d.items || d.events || []))
      .filter((e) => e && e.type === "dividend" && e.ticker && e.payload)
      .map((e) => ({
        ticker: e.ticker, date: e.date, status: e.status,
        amount: e.payload.amount, currency: e.payload.currency,
        record_date: e.payload.record_date, buy_by_date: e.payload.buy_by_date,
        yield_pct: e.payload.dividend_yield,
      })),
    "dividend-calendar-snapshot.json");

  // Обозреватель: разделение «новости по теме» и «анализ текущей ситуации».
  // Владелец 2026-07-31: спрос идёт на широких словах («геополитика», «новости
  // геополитики»), а наши заголовки под узкими формулировками («геополитика и
  // российский рынок») находятся заметно хуже. Новости у нас уже размечены по
  // категориям (Геополитика 42, Экономика 39, Политика 17) — этого достаточно,
  // чтобы сделать тематические ленты отдельными страницами.
  await grab("Новости по темам", "/api/market/news?limit=200",
    (d) => (Array.isArray(d) ? d : (d.items || d.news || []))
      .filter((n) => n && n.title)
      .map((n) => ({
        id: n.id, title: n.title, summary: n.summary, category: n.category,
        rubric: n.rubric, importance: n.importance, published_at: n.published_at,
        impact_comment: n.impact_comment, affected_tickers: n.affected_tickers,
      })),
    "news-snapshot.json");

  // Среднесрочный прогноз ЦБ — под запрос «среднесрочный прогноз банка россии»
  // (широкий спрос, с уточнениями «по ключевой ставке», «по инфляции»). Данные уже
  // собираются, но страницы под них не было.
  await grab("Прогноз Банка России", "/api/market/macro/forecast",
    (d) => (d && Array.isArray(d.rows)
      ? [{ as_of: d.as_of, scenario: d.scenario, comment: d.comment,
           source_url: d.source_url, rows: d.rows }] : []),
    "cb-forecast-snapshot.json");

  // График заседаний ЦБ по ставке — «заседание цб по ключевой ставке 2026 график».
  await grab("Заседания ЦБ", "/api/market/calendar?event_type=macro&scope=all&days=400&limit=400",
    (d) => (d.events || []).filter((e) => /ключевой ставке/i.test(String(e.title || "")))
      .map((e) => ({ date: e.date, time: e.time, title: e.title, status: e.status })),
    "cb-meetings-snapshot.json");

  // Институциональная среда: алерты барометра.
  await grab("Институты", "/api/market/institutions",
    (d) => (d && Array.isArray(d.alerts)
      ? d.alerts.map((a) => ({ ...a, _as_of: d.as_of })) : []),
    "institutions-snapshot.json");

  // История значений показателей — ради неё стоит сделать N запросов: без неё страницы
  // статистики остаются справочными «одно число + подпись» (218 слов), а с ней дают
  // реальный контент — динамику за годы, которую и ищут («ключевая ставка по годам»).
  try {
    const macroPath = path.join(__dirname, "data", "macro-snapshot.json");
    const codes = (JSON.parse(fs.readFileSync(macroPath, "utf8")).rows || [])
      .map((r) => r.code).filter(Boolean);
    const series = {};
    for (const code of codes) {
      try {
        const r = await fetch(`${API}/api/market/macro/${encodeURIComponent(code)}/series`,
          { headers: { "Accept-Encoding": "gzip" } });
        if (!r.ok) continue;
        const j = await r.json();
        const pts = (j.points || []).filter((x) => x && x.value != null);
        if (pts.length) series[code] = pts.slice(-60);
      } catch { /* один показатель не должен ронять остальные */ }
      await new Promise((res) => setTimeout(res, 120));
    }
    const out = path.join(__dirname, "data", "macro-series-snapshot.json");
    fs.writeFileSync(out, JSON.stringify({
      meta: { source: API, fetched_at: new Date().toISOString(), count: Object.keys(series).length },
      series,
    }), "utf8");
    console.log(`История показателей: ${Object.keys(series).length} рядов → снапшот обновлён`);
  } catch (e) {
    console.log(`История показателей: не обновлена (${e.message}) — беру закоммиченную`);
  }
}

main();

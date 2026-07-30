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
}

main();

#!/usr/bin/env node
/**
 * Снапшот данных инструментов с ПРОД-API для SEO-статики (задача №2 SEO-программы).
 *
 * ЗАЧЕМ ОТДЕЛЬНЫЙ ШАГ: SEO-страницы генерятся node-скриптом при сборке на Timeweb,
 * где НЕТ доступа к БД и НЕТ Python. Поэтому данные снимаются заранее с боевого API
 * и коммитятся в repo как JSON-снапшоты (scripts/data/*-snapshot.json). Генератор
 * generate-seo-instruments.js читает ТОЛЬКО эти файлы — сборка от сети не зависит.
 *
 * ОБНОВЛЕНИЕ: шаг входит в `npm run build` с флагом --soft, поэтому снапшоты
 * освежаются при каждом деплое сами. Руками — той же командой без флага:
 *   node scripts/fetch-seo-snapshots.js
 *
 * 🔴 ПОЧЕМУ ЭТО ПОПАЛО В СБОРКУ (найдено 2026-09-11): снапшоты bonds/funds/futures/spot
 * последний раз снимали 30.07.2026, и все ~3900 страниц выпусков, фьючерсов и фондов
 * шесть недель писали в сниппете «Данные на 30.07.2026» с устаревшими доходностью и ГО.
 * Ручной шаг забывается — значит он не должен быть ручным.
 *
 * 🔴 ДВА ПРЕДОХРАНИТЕЛЯ, без которых автозапуск опаснее ручного:
 *   1. --soft (режим сборки): сеть недоступна или API ответил ошибкой → печатаем и
 *      выходим с кодом 0, оставляя ПРЕЖНИЕ снапшоты. Деплой не должен падать из-за
 *      того, что бэкенд в этот момент перезапускался. Сюда же — таймаут на каждый
 *      запрос и общий бюджет на весь шаг: «упасть» шаг внутри сборки умеет безопасно,
 *      а вот ВИСЕТЬ — нет, повисший запрос останавливает деплой целиком.
 *   2. Пол по объёму: снапшот перезаписывается, только если строк не меньше 70% от
 *      того, что уже лежит. Пустой или обрезанный ответ API иначе молча снёс бы
 *      тысячи страниц — сборка при этом осталась бы зелёной.
 *
 * ВЕЖЛИВОСТЬ: ровно 5 GET-запросов списков (bonds, screener/bonds, funds, futures,
 * spot) с паузами — НИКАКИХ пер-бумажных запросов (3263 облигации приходят одним
 * списком со всеми расчётными полями: risk_verdict, basis_score, светофор и т.д.).
 */
"use strict";
const fs = require("fs");
const path = require("path");

const API = process.env.BASIS_API || "https://nikitasoin-basis-a772.twc1.net";
const DATA_DIR = path.join(__dirname, "data");
const PAUSE_MS = 2500;
// Режим сборки: не валить деплой из-за недоступного API (см. предохранитель 1 выше).
const SOFT = process.argv.includes("--soft");
// Доля от прежнего размера, ниже которой запись считается подозрительной (предохранитель 2).
const MIN_KEEP_RATIO = 0.7;

const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

// 🔴 ТАЙМАУТ ОБЯЗАТЕЛЕН, РАЗ ШАГ ВНУТРИ СБОРКИ. Без него зависший запрос вешает не
// скрипт, а ВЕСЬ деплой: сборка стоит, старая версия остаётся на бою, и понять причину
// снаружи нельзя — логи билд-окружения Timeweb через прокси отдаются не всегда. Поэтому
// у каждого запроса свой предел, а у шага целиком — общий дедлайн ниже.
const REQ_TIMEOUT_MS = 25000;
const TOTAL_BUDGET_MS = 150000;
const startedAt = Date.now();

async function getJson(urlPath) {
  if (Date.now() - startedAt > TOTAL_BUDGET_MS) {
    throw new Error(`общий бюджет ${Math.round(TOTAL_BUDGET_MS / 1000)} с исчерпан`);
  }
  const url = API + urlPath;
  const ctl = new AbortController();
  const t = setTimeout(() => ctl.abort(), REQ_TIMEOUT_MS);
  try {
    const res = await fetch(url, {
      headers: { "Accept-Encoding": "gzip" }, signal: ctl.signal,
    });
    if (!res.ok) throw new Error(`${urlPath} → HTTP ${res.status}`);
    return await res.json();
  } catch (e) {
    if (e && e.name === "AbortError") {
      throw new Error(`${urlPath} → нет ответа за ${REQ_TIMEOUT_MS / 1000} с`);
    }
    throw e;
  } finally {
    clearTimeout(t);
  }
}

// Поля облигации, которые реально нужны страницам (чуть худеем снапшот: id/board
// и пр. служебное не тащим — при 3263 строках это мегабайты в repo).
const BOND_FIELDS = [
  "secid", "isin", "short_name", "issuer_name", "issuer_ticker", "bond_type",
  "currency", "face_value", "coupon_percent", "coupon_value", "coupon_period",
  "maturity_date", "offer_date", "has_amortization", "lot_size", "listing_level",
  "last_price", "ytm", "ytm_kind", "duration_days", "duration_years", "accrued_int",
  "coupon_type", "coupon_formula", "coupon_label", "is_defaulted",
  "risk_tier", "risk_label", "spread_bp", "floater_spread_bp",
  "agency_rating", "agency_rating_source", "agency_rating_meaning", "agency_tier",
  "rating_divergence", "risk_verdict", "arbitrage_note",
  "basis_score", "basis_group", "sector",
  "yield_anomaly", "near_offer", "spread_artifact",
  // Ликвидность выпуска: без неё страница не может отличить «цена такая» от «цены
  // фактически нет» — см. bondIlliquid() в generate-seo-instruments.js.
  "num_trades", "val_today",
];
// Из скринера доклеиваем светофор «доходность vs риск» (тот же движок, что в карточке)
const SCREENER_FIELDS = { light: "light", vkind: "vkind", premium: "premium_bp", required: "required_bp" };

function writeSnapshot(name, rows, extra) {
  const p0 = path.join(DATA_DIR, `${name}-snapshot.json`);
  // Пол по объёму: сравниваем с тем, что уже лежит. Меньше 70% прежнего — не пишем.
  try {
    const prev = JSON.parse(fs.readFileSync(p0, "utf8"));
    const had = Array.isArray(prev.rows) ? prev.rows.length : (prev.count || 0);
    if (had && rows.length < had * MIN_KEEP_RATIO) {
      console.error(`${name}: ПРОПУСК — пришло ${rows.length} строк против ${had} прежних `
        + `(меньше ${Math.round(MIN_KEEP_RATIO * 100)}%). Старый снапшот сохранён.`);
      return false;
    }
  } catch { /* прежнего файла нет — пишем как есть */ }
  const out = {
    fetched_at: new Date().toISOString(),
    source: API,
    count: rows.length,
    ...(extra || {}),
    rows,
  };
  const p = path.join(DATA_DIR, `${name}-snapshot.json`);
  fs.writeFileSync(p, JSON.stringify(out), "utf8");
  console.log(`${name}: ${rows.length} строк → ${p} (${Math.round(fs.statSync(p).size / 1024)} КБ)`);
  return true;
}

async function main() {
  fs.mkdirSync(DATA_DIR, { recursive: true });

  console.log(`Снимаю данные с ${API} (6 запросов с паузами)…`);
  const bonds = await getJson("/api/bonds");
  await sleep(PAUSE_MS);
  const screener = await getJson("/api/screener/bonds");
  await sleep(PAUSE_MS);
  const funds = await getJson("/api/funds");
  await sleep(PAUSE_MS);
  const futures = await getJson("/api/futures");
  await sleep(PAUSE_MS);
  const spot = await getJson("/api/spot");
  await sleep(PAUSE_MS);
  // Разборы вышедшей отчётности (владелец 2026-07-30: «человек вбивает "отчет ozon" —
  // надо, чтобы находил его у нас»). Одним списком, а не по компании: пер-тикерных
  // запросов было бы 264, а лента отдаёт всё разом со всей сутью разбора.
  const earnings = await getJson("/api/market/earnings?limit=400");

  // облигации: худеем до нужных полей + мёржим светофор скринера по secid
  const byId = new Map();
  for (const r of screener.rows || []) byId.set(r.id, r);
  const bondRows = bonds.map((b) => {
    const slim = {};
    for (const f of BOND_FIELDS) if (b[f] !== undefined) slim[f] = b[f];
    const scr = byId.get(b.secid);
    if (scr) for (const [src, dst] of Object.entries(SCREENER_FIELDS)) {
      if (scr[src] !== undefined && scr[src] !== null) slim[dst] = scr[src];
    }
    return slim;
  });
  // ответ вида {count, reports:[…]} — ключ именно reports
  writeSnapshot("earnings", Array.isArray(earnings) ? earnings : (earnings.reports || earnings.items || []));
  writeSnapshot("bonds", bondRows);
  writeSnapshot("funds", funds);
  writeSnapshot("futures", futures);
  writeSnapshot("spot", spot);
  console.log("Готово. Снапшоты закоммитить вместе с генерацией.");
}

main().catch((e) => {
  console.error("Ошибка снапшота:", e.message);
  if (SOFT) {
    console.error("Режим --soft: сборка продолжается на прежних снапшотах "
      + "(страницы останутся с предыдущей датой данных, но не исчезнут).");
    process.exit(0);
  }
  process.exit(1);
});

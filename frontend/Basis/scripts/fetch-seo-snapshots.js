#!/usr/bin/env node
/**
 * Снапшот данных инструментов с ПРОД-API для SEO-статики (задача №2 SEO-программы).
 *
 * ЗАЧЕМ ОТДЕЛЬНЫЙ ШАГ: SEO-страницы генерятся node-скриптом при сборке на Timeweb,
 * где НЕТ доступа к БД и НЕТ Python. Поэтому данные снимаются заранее с боевого API
 * и коммитятся в repo как JSON-снапшоты (scripts/data/*-snapshot.json). Генератор
 * generate-seo-instruments.js читает ТОЛЬКО эти файлы — сборка от сети не зависит.
 *
 * ОБНОВЛЕНИЕ: запускать вручную/сессией перед пересборкой, когда данные пора
 * освежить (страницы явно показывают «данные на DD.MM.YYYY» из меты снапшота).
 *   node scripts/fetch-seo-snapshots.js
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

const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

async function getJson(urlPath) {
  const url = API + urlPath;
  const res = await fetch(url, { headers: { "Accept-Encoding": "gzip" } });
  if (!res.ok) throw new Error(`${urlPath} → HTTP ${res.status}`);
  return res.json();
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
];
// Из скринера доклеиваем светофор «доходность vs риск» (тот же движок, что в карточке)
const SCREENER_FIELDS = { light: "light", vkind: "vkind", premium: "premium_bp", required: "required_bp" };

function writeSnapshot(name, rows, extra) {
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
}

async function main() {
  fs.mkdirSync(DATA_DIR, { recursive: true });

  console.log(`Снимаю данные с ${API} (5 запросов с паузами)…`);
  const bonds = await getJson("/api/bonds");
  await sleep(PAUSE_MS);
  const screener = await getJson("/api/screener/bonds");
  await sleep(PAUSE_MS);
  const funds = await getJson("/api/funds");
  await sleep(PAUSE_MS);
  const futures = await getJson("/api/futures");
  await sleep(PAUSE_MS);
  const spot = await getJson("/api/spot");

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
  writeSnapshot("bonds", bondRows);
  writeSnapshot("funds", funds);
  writeSnapshot("futures", futures);
  writeSnapshot("spot", spot);
  console.log("Готово. Снапшоты закоммитить вместе с генерацией.");
}

main().catch((e) => { console.error("Ошибка снапшота:", e.message); process.exit(1); });

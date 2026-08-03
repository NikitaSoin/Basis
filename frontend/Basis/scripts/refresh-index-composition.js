#!/usr/bin/env node
/**
 * Состав индексов Мосбиржи (IMOEX / RTSI / MCFTR) — снимок для пре-рендеренных страниц.
 *
 * ЗАЧЕМ: «состав индекса мосбиржи» — 1983 запроса в месяц, а страница /indeks/imoex/ до
 * сих пор состава не содержала вообще. Плюс это внутренняя перелинковка: 46 ссылок с
 * растущей по весу страницы на карточки компаний.
 *
 * НАДЁЖНОСТЬ ВАЖНЕЕ СВЕЖЕСТИ (как в refresh-earnings-snapshot.js): состав меняется раз в
 * квартал при ребалансировке, поэтому при недоступной бирже мы молча оставляем прошлый
 * снимок и НЕ роняем сборку. Уронить сборку = не выкатить сайт целиком (см. CLAUDE.md).
 *
 * 🔴 Сеть на билд-окружении Timeweb может быть закрыта (уже ловили с DeepSeek/FRED) —
 * поэтому снимок ОБЯЗАН быть закоммичен. Этот скрипт его лишь обновляет, когда может.
 */
"use strict";

const fs = require("fs");
const path = require("path");

const OUT = path.join(__dirname, "data", "index-composition-snapshot.json");
const ISS = "https://iss.moex.com/iss/statistics/engines/stock/markets/index/analytics";
const INDICES = ["IMOEX", "RTSI", "MCFTR"];
const TIMEOUT_MS = 20000;

async function fetchComposition(indexId) {
  const ctrl = new AbortController();
  const t = setTimeout(() => ctrl.abort(), TIMEOUT_MS);
  try {
    const r = await fetch(`${ISS}/${indexId}.json?limit=100`, { signal: ctrl.signal });
    if (!r.ok) throw new Error(`HTTP ${r.status}`);
    const j = await r.json();
    const blk = j.analytics || {};
    const cols = blk.columns || [];
    const rows = (blk.data || []).map((r0) => Object.fromEntries(cols.map((c, i) => [c, r0[i]])));
    return rows
      .filter((x) => x.ticker && x.weight != null)
      .map((x) => ({ ticker: String(x.ticker), name: String(x.shortnames || x.ticker), weight: Number(x.weight) }))
      .sort((a, b) => b.weight - a.weight);
  } finally {
    clearTimeout(t);
  }
}

async function main() {
  const prev = fs.existsSync(OUT) ? JSON.parse(fs.readFileSync(OUT, "utf8")) : { indices: {} };
  const out = { meta: { source: ISS, fetched_at: new Date().toISOString() }, indices: { ...(prev.indices || {}) } };
  let ok = 0;
  for (const id of INDICES) {
    try {
      const rows = await fetchComposition(id);
      // Пустой ответ биржи — не повод затирать рабочий состав: ноль бумаг в индексе
      // невозможен, значит это сбой источника, а не факт (см. «деструктивное правило
      // нуждается в пределе» — уже сносили живые ряды, приняв сбой за данные).
      if (rows.length >= 10) {
        out.indices[id] = { rows, tradedate: null, count: rows.length };
        ok++;
      } else {
        console.log(`  Состав ${id}: биржа вернула ${rows.length} бумаг — оставляю прошлый снимок`);
      }
    } catch (e) {
      console.log(`  Состав ${id}: источник недоступен (${e.message}) — оставляю прошлый снимок`);
    }
    await new Promise((r) => setTimeout(r, 600)); // ISS не любит плотный поток
  }
  fs.mkdirSync(path.dirname(OUT), { recursive: true });
  fs.writeFileSync(OUT, JSON.stringify(out, null, 1));
  const total = Object.entries(out.indices).map(([k, v]) => `${k}: ${v.rows.length}`).join(", ");
  console.log(`Состав индексов: обновлено ${ok} из ${INDICES.length} (${total || "нет данных"})`);
}

main().catch((e) => {
  // Никогда не роняем сборку: без состава страница просто будет без таблицы.
  console.log("Состав индексов: не обновлён —", e.message);
});

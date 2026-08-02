#!/usr/bin/env node
/**
 * «Сборка» из уже собранного: проверяет закоммиченный build/ и выходит.
 *
 * ЗАЧЕМ: 2026-08-03 деплой фронта перестал проходить, логи падения ПУСТЫЕ. Пустой лог
 * при падении почти всегда означает, что процесс убит извне (по памяти) — он не успевает
 * ничего записать. Наша сборка тяжёлая: webpack плюс три генератора, создающих ~8800
 * файлов и читающих сотни JSON. На билд-окружении с небольшим лимитом памяти это
 * ложится. Исторически от сборки на сервере уже уходили по этой же причине.
 *
 * Обходной путь: `build/` лежит в репозитории собранным. Сервер может его просто отдать,
 * ничего не собирая. Тогда деплой сводится к клонированию и запуску — падать нечему.
 *
 * 🔴 ЧТО ТЕРЯЕМ, ЧЕСТНО. Обычный `npm run build` на сервере заново выполняет наши
 * генераторы, а они ходят в боевой API за свежими данными: разборы отчётов, справедливая
 * цена, новости, прогноз ЦБ, значения макропоказателей. Именно поэтому новый отчёт
 * компании появлялся на сайте сам. С этим путём снапшоты замирают на том, что
 * закоммичено, и обновляются только когда фронт пересобирают локально и коммитят.
 * Это осознанный размен: рабочий деплой сейчас важнее автосвежести.
 *
 * Использование: в панели Timeweb заменить команду сборки на
 *     npm run build:prebuilt
 * Вернуть автосвежесть — вернуть команду `npm run build`.
 */
"use strict";
const fs = require("fs");
const path = require("path");

const BUILD = path.join(__dirname, "..", "build");

function countFiles(dir) {
  let n = 0;
  const stack = [dir];
  while (stack.length) {
    const d = stack.pop();
    let entries = [];
    try { entries = fs.readdirSync(d, { withFileTypes: true }); } catch { continue; }
    for (const e of entries) {
      if (e.isDirectory()) stack.push(path.join(d, e.name));
      else n++;
    }
  }
  return n;
}

function fail(msg) {
  console.error(`\n❌ ${msg}\n`);
  console.error("Собранный фронт в репозитории неполный — отдавать его нельзя.");
  console.error("Почините локально:  cd frontend/Basis && CI=false npm run build");
  console.error("и закоммитьте build/ целиком.\n");
  process.exit(1);
}

if (!fs.existsSync(BUILD)) fail("Папки build/ нет вовсе.");

const files = countFiles(BUILD);
const indexHtml = fs.existsSync(path.join(BUILD, "index.html"));
let locs = 0;
try {
  locs = (fs.readFileSync(path.join(BUILD, "sitemap.xml"), "utf8").match(/<loc>/g) || []).length;
} catch { /* ниже проверим числом */ }

// 🔴 Те же пороги, что в правиле защиты SEO-страниц (CLAUDE.md): голый craco build
// ужимает build/ до ~31 файла и подменяет карту сайта заготовкой с одним адресом.
// Отдать такое на бой — потерять 8500 страниц молча.
if (!indexHtml) fail("В build/ нет index.html.");
if (files < 5000) fail(`В build/ всего ${files} файлов (ожидаем ~8800). Похоже на голый craco build.`);
if (locs < 1000) fail(`В карте сайта ${locs} адресов (ожидаем ~4700). Карта подменена заготовкой из public/.`);

console.log(`✓ Готовая сборка на месте: ${files} файлов, ${locs} адресов в карте сайта.`);
console.log("  Пересборка на сервере пропущена (см. докстринг scripts/build-prebuilt.js).");

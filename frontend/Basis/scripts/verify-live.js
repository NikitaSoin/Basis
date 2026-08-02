#!/usr/bin/env node
/**
 * Проверка боевого сайта по СОДЕРЖИМОМУ — вместо ручных curl после каждого деплоя.
 *
 * ЗАЧЕМ: за два дня я трижды сделал неверный вывод о состоянии боя, потому что проверял
 * косвенные признаки:
 *   • «HTTP 200» — хостинг отдаёт 200 на ЛЮБОЙ адрес, включая несуществующий;
 *   • «сменился main.<hash>.js» — не меняется, если правка только в статических
 *     страницах, и проверка честно ждёт того, чего не произойдёт;
 *   • «слово есть в бандле» — совпадает со списками вкладок и мёртвым кодом.
 * Плюс из песочницы часть запросов обрывается пустым ответом: один пустой ответ я дважды
 * принял за поломку сайта.
 *
 * Здесь всё это закрыто: проверяем ФАКТ на странице, с повтором при обрыве, и падаем с
 * ненулевым кодом, если ожидание не выполнилось.
 *
 * Запуск:  node scripts/verify-live.js            — все проверки
 *          node scripts/verify-live.js фьючерс    — только совпавшие по названию
 */
"use strict";

const SITE = "https://inbasis.ru";
const TRIES = 4;              // из песочницы ответы обрываются — одного раза мало
const TIMEOUT_MS = 30000;

/** Скачать страницу с повтором: пустой ответ ≠ поломка сайта. */
async function fetchText(path, minBytes = 200) {
  let last = "";
  for (let i = 0; i < TRIES; i++) {
    try {
      const ctrl = new AbortController();
      const t = setTimeout(() => ctrl.abort(), TIMEOUT_MS);
      const r = await fetch(`${SITE}${path}`, { signal: ctrl.signal });
      clearTimeout(t);
      const text = await r.text();
      if (text && text.length >= minBytes) return { ok: true, text, status: r.status };
      last = `пустой ответ (${text.length} байт)`;
    } catch (e) {
      last = e.name === "AbortError" ? "таймаут" : e.message;
    }
    await new Promise((res) => setTimeout(res, 1200));
  }
  return { ok: false, text: "", error: last };
}

// must — обязано быть на странице; mustNot — не должно.
// Каждая проверка описывает КЛАСС дефекта, который мы уже ловили на бою.
const CHECKS = [
  { name: "главная: счётчик Метрики", path: "/", must: ["mc.yandex.ru/metrika/tag.js"] },
  { name: "главная: без слова «независимая»", path: "/", mustNot: ["езависим"] },

  { name: "карточка компании: приложение + статика", path: "/company/SBER/",
    must: ['id="seo-static"', "main.", "Organization"] },
  { name: "карточка компании: заголовок не обрублен", path: "/company/TORS/",
    must: ["Россети Томск (TORS)"], titleMustNot: ["…"] },

  { name: "метрика компании: сравнение с сектором", path: "/company/CHMF/roe/",
    must: ["Медиана по сектору", "у компании"] },
  { name: "справедливая цена: оговорка о методике", path: "/company/SBER/spravedlivaya-tsena/",
    must: ["планка входа", "не является индивидуальной инвестиционной рекомендацией"] },
  { name: "справочник: формула и примеры", path: "/pokazateli/ebitda/",
    must: ["Формула", "DefinedTerm"] },

  // Класс дефекта: страницы инструментов собирает ДРУГОЙ генератор — «глобальные»
  // правки туда не попадают (ловили с Метрикой, с приложением, с шириной).
  { name: "фьючерс: приложение подключено", path: "/futures/SiU6/",
    must: ['id="seo-static"', "main.", "seo-boot"] },
  { name: "фьючерс: месяц словами (различимость близнецов)", path: "/futures/SiU6/",
    must: ["исполнение сентябрь 2026", "сентябре 2026"] },
  { name: "фьючерс: альтернативные написания кода", path: "/futures/SiU6/",
    must: ["Si 9.26", "Si926"] },
  { name: "фьючерс: ширина не зажимает приложение", path: "/futures/SiU6/",
    must: ["#seo-static{max-width"], mustNot: ["\nbody{font-family:-apple-system,'Segoe UI',Roboto,sans-serif;background:var(--paper);color:var(--ink);max-width"] },
  { name: "облигация: приложение подключено", path: "/bonds/RU000A10FEP7/",
    must: ['id="seo-static"', "main."] },
  { name: "фонд: приложение подключено", path: "/funds/TMOS/", must: ['id="seo-static"', "main."] },

  { name: "показатель: график и данные", path: "/statistika/klyuchevaya-stavka/",
    must: ["Ключевая ставка"] },
  { name: "лендинг недооценённых: оговорки", path: "/nedootsenennye-aktsii/",
    must: ["не список «что купить»", "медианная"] },
  { name: "страница 404 существует", path: "/404.html", must: ["Такой страницы нет", "noindex"] },
  { name: "ключ IndexNow отдаётся", path: "/9f82c468ecc5ed2bf352a8ff496af0a2.txt",
    must: ["9f82c468ecc5ed2bf352a8ff496af0a2"], mustNot: ["<!doctype"], minBytes: 30 },
];

async function main() {
  const filter = process.argv[2];
  const list = filter ? CHECKS.filter((c) => c.name.includes(filter)) : CHECKS;
  console.log(`Проверок: ${list.length}\n`);

  // Карты сайта — отдельно: там важны числа, а не подстроки.
  const maps = [["sitemap.xml", 4000], ["sitemap-instruments.xml", 2500], ["sitemap-indicators.xml", 50]];
  let bad = 0;
  if (!filter) {
    for (const [m, min] of maps) {
      const r = await fetchText(`/${m}`);
      const n = r.ok ? (r.text.match(/<loc>/g) || []).length : 0;
      const ok = n >= min;
      if (!ok) bad++;
      console.log(`  ${ok ? "✓" : "✗"} ${m}: ${n} адресов (ожидаем ≥ ${min})`);
    }
    console.log("");
  }

  for (const c of list) {
    const r = await fetchText(c.path, c.minBytes);
    if (!r.ok) { bad++; console.log(`  ✗ ${c.name}\n      страница не скачалась: ${r.error}`); continue; }
    const title = (r.text.match(/<title>([\s\S]*?)<\/title>/) || ["", ""])[1];
    const miss = (c.must || []).filter((s) => !r.text.includes(s));
    const extra = [
      ...(c.mustNot || []).filter((s) => r.text.includes(s)),
      // titleMustNot — про заголовок, а не про всю страницу: обрезка имени в тайтле это
      // дефект, а многоточие в списке соседних компаний — нормальный текст.
      ...(c.titleMustNot || []).filter((s) => title.includes(s)),
    ];
    if (miss.length || extra.length) {
      bad++;
      console.log(`  ✗ ${c.name}  (${c.path})`);
      if (miss.length) console.log(`      нет: ${miss.map((s) => JSON.stringify(s.slice(0, 46))).join(", ")}`);
      if (extra.length) console.log(`      лишнее: ${extra.map((s) => JSON.stringify(s.slice(0, 46))).join(", ")}`);
    } else {
      console.log(`  ✓ ${c.name}`);
    }
  }

  console.log(`\nИтог: ${list.length + (filter ? 0 : maps.length) - bad} прошло, ${bad} не прошло.`);
  process.exit(bad ? 1 : 0);
}

main();

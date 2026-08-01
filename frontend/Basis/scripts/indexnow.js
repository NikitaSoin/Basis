#!/usr/bin/env node
/**
 * IndexNow — прямое уведомление поисковика об адресах, минуя очередь обхода.
 *
 * ЗАЧЕМ: владелец 2026-08-02 — «ждать несколько месяцев я не намерен». Посчитанный по
 * выгрузке Вебмастера темп обхода даёт 2–4 месяца на 8530 страниц: робот приходит сам,
 * когда сочтёт нужным, а ручной переобход ограничен 150 адресами в сутки.
 *
 * IndexNow снимает именно это ограничение: мы САМИ сообщаем поисковику список изменённых
 * адресов, до 10 000 за один запрос. Протокол поддерживают Яндекс и Bing (а значит и
 * поиск Microsoft), Google — нет, для него остаётся карта сайта и Search Console.
 *
 * 🔴 УВЕДОМЛЕНИЕ ≠ ИНДЕКСАЦИЯ. IndexNow ускоряет ОБХОД: робот узнаёт об адресе сразу, а
 * не через недели. Возьмёт ли он страницу в индекс — решает по её качеству, как обычно.
 * Поэтому слать всё подряд бессмысленно: 670 страниц облигаций без рыночной оценки мы уже
 * закрыли от индексации, и в этот список они не попадают — он строится из карт сайта.
 *
 * 🔴 КЛЮЧ ДОЛЖЕН БЫТЬ ДОСТУПЕН НА САЙТЕ. Поисковик проверяет, что файл
 * https://inbasis.ru/<ключ>.txt существует и содержит ровно этот ключ — так он убеждается,
 * что адреса шлёт владелец сайта. Файл лежит в public/ и попадает в сборку.
 *
 * Запуск:
 *   node scripts/indexnow.js              — отправить все адреса из карт сайта
 *   node scripts/indexnow.js --limit 500  — только первые N (для проверки)
 *   node scripts/indexnow.js --file x.txt — свой список адресов, по одному в строке
 */
"use strict";
const fs = require("fs");
const path = require("path");

const KEY = "9f82c468ecc5ed2bf352a8ff496af0a2";
const HOST = "inbasis.ru";
const SITE = `https://${HOST}`;
const BUILD = path.join(__dirname, "..", "build");
// Точка приёма Яндекса. Протокол общий: любой участник передаёт уведомление остальным,
// поэтому одного запроса достаточно и дублировать в Bing не нужно.
const ENDPOINT = "https://yandex.com/indexnow";
const CHUNK = 5000;          // протокол разрешает 10 000; берём с запасом

// 🔴 Адреса берём с ЖИВОГО САЙТА, а не из локальной сборки. Локальная папка build/ —
// ненадёжный источник: параллельные сессии работают в той же рабочей копии, и голый
// craco build ужимает её до 31 файла, подменяя sitemap.xml заготовкой из public/ с
// ОДНИМ адресом. Именно так первая отправка ушла в Яндекс с одним адресом вместо 4692 —
// формально успешно, фактически впустую. Живая карта отражает то, что реально
// опубликовано, и от состояния рабочей папки не зависит.
async function urlsFromSitemaps() {
  const maps = ["sitemap.xml", "sitemap-instruments.xml", "sitemap-indicators.xml"];
  const out = [];
  for (const m of maps) {
    try {
      const r = await fetch(`${SITE}/${m}`);
      if (!r.ok) { console.log(`  ${m}: HTTP ${r.status}, пропускаю`); continue; }
      const xml = await r.text();
      const found = [...xml.matchAll(/<loc>([^<]+)<\/loc>/g)].map((x) => x[1]);
      console.log(`  ${m}: ${found.length} адресов`);
      out.push(...found);
    } catch (e) {
      console.log(`  ${m}: не скачался (${e.message})`);
    }
  }
  return [...new Set(out)];
}

async function submit(batch) {
  const body = JSON.stringify({
    host: HOST, key: KEY, keyLocation: `${SITE}/${KEY}.txt`, urlList: batch,
  });
  const res = await fetch(ENDPOINT, {
    method: "POST",
    headers: { "Content-Type": "application/json; charset=utf-8" },
    body,
  });
  const text = await res.text().catch(() => "");
  return { status: res.status, text: text.slice(0, 200) };
}

async function main() {
  const args = process.argv.slice(2);
  const limIdx = args.indexOf("--limit");
  const fileIdx = args.indexOf("--file");
  const dry = args.includes("--dry");

  let urls = fileIdx >= 0
    ? fs.readFileSync(args[fileIdx + 1], "utf8").split("\n").map((s) => s.trim()).filter((s) => s.startsWith("http"))
    : await urlsFromSitemaps();
  if (limIdx >= 0) urls = urls.slice(0, Number(args[limIdx + 1]) || 100);

  if (!urls.length) { console.log("Адресов нет — карты сайта недоступны?"); return; }
  // Подозрительно короткий список почти всегда означает подменённую карту, а не то, что
  // сайт вдруг усох. Лучше остановиться и разобраться, чем отправить пустышку и считать
  // задачу выполненной.
  if (fileIdx < 0 && limIdx < 0 && urls.length < 100) {
    console.log(`⚠️  В картах всего ${urls.length} адресов — это не похоже на правду.`);
    console.log("    Отправка отменена. Проверьте https://inbasis.ru/sitemap.xml");
    return;
  }
  console.log(`Адресов к отправке: ${urls.length}`);

  // Проверяем ключ ДО отправки: без доступного файла поисковик отвергнет весь запрос,
  // и мы будем думать, что отправили, хотя ничего не произошло.
  try {
    const r = await fetch(`${SITE}/${KEY}.txt`);
    const t = (await r.text()).trim();
    if (!r.ok || t !== KEY) {
      console.log(`⚠️  Ключ на сайте недоступен или не совпадает (${SITE}/${KEY}.txt).`);
      console.log("    Сначала выкатите фронт — файл лежит в public/ и попадает в сборку.");
      return;
    }
    console.log("Ключ на сайте подтверждён.");
  } catch (e) {
    console.log(`⚠️  Не удалось проверить ключ: ${e.message}`);
    return;
  }

  if (dry) { console.log("Пробный прогон: ничего не отправлено."); return; }

  for (let i = 0; i < urls.length; i += CHUNK) {
    const batch = urls.slice(i, i + CHUNK);
    const r = await submit(batch);
    // 200 — принято; 202 — принято, ключ проверяется; 4xx — отказ с причиной в теле.
    console.log(`  партия ${i / CHUNK + 1}: ${batch.length} адресов → HTTP ${r.status} ${r.text}`);
    await new Promise((res) => setTimeout(res, 1500));
  }
  console.log("Готово. Уведомление ускоряет ОБХОД; решение об индексации остаётся за поиском.");
}

main();

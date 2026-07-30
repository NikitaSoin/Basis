#!/usr/bin/env node
/**
 * SEO-страницы под МАКРОПОКАЗАТЕЛИ и ИНДЕКСЫ (владелец, 2026-07-31: «в экономической
 * статистике нужно, чтобы графики/карточки имели доступ вовне — пользователь вбивает
 * "индекс PMI" и мы ему выдаём индекс PMI и страницу нашего сайта»; «в обзоре рынка есть
 * индекс страха, индекс Мосбиржи, секторальные индексы — надо и под них сделать страницы»).
 *
 * До этого у 67 показателей и 3 индексов не было ни одного собственного адреса: всё жило
 * внутри приложения, и на запрос «ключевая ставка ЦБ» или «индекс РТС» предъявить поиску
 * было нечего.
 *
 * Данные — из снапшотов (scripts/data/macro-snapshot.json, indices-snapshot.json),
 * которые обновляет refresh-earnings-snapshot.js ПРИ КАЖДОЙ СБОРКЕ. Поэтому страницы
 * показывают свежие значения без ручного вмешательства, а при недоступности API
 * собираются из последнего закоммиченного снапшота.
 *
 * Страницы гибридные, как карточки компаний: статика для робота + приложение поверх для
 * человека (переход в соответствующий раздел).
 */
"use strict";
const fs = require("fs");
const path = require("path");

const BUILD = path.join(__dirname, "..", "build");
const SITE = "https://inbasis.ru";
const API_BASE = process.env.REACT_APP_API_URL || process.env.BASIS_API
  || "https://nikitasoin-basis-a772.twc1.net";

const esc = (v) => String(v == null ? "" : v)
  .replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;").replace(/"/g, "&quot;");

function readSnap(name) {
  try {
    const raw = JSON.parse(fs.readFileSync(path.join(__dirname, "data", name), "utf8"));
    return { rows: raw.rows || raw || [], meta: raw.meta || {} };
  } catch { return { rows: [], meta: {} }; }
}

// code → человекочитаемый слаг. Для показателей, которые реально ищут словами, слаг
// задан явно: «/statistika/klyuchevaya-stavka/» читается и человеком, и поисковиком
// лучше, чем «/statistika/key_rate/». Остальные — из code с заменой подчёркиваний.
const SLUGS = {
  key_rate: "klyuchevaya-stavka", inflation: "inflyatsiya", inflation_weekly: "nedelnaya-inflyatsiya",
  inflation_expect: "inflyatsionnye-ozhidaniya", usdrub: "kurs-dollara", cnyrub: "kurs-yuanya",
  eurrub: "kurs-evro", gdp: "vvp-rossii", unemployment: "bezrabotitsa",
  pmi_composite: "indeks-pmi", pmi_manufacturing: "pmi-promyshlennosti", pmi_services: "pmi-uslug",
  ppi: "tseny-proizvoditeley", urals: "neft-urals", brent: "neft-brent",
  budget_balance: "byudzhet-rossii", retail_sales: "roznichnye-prodazhi",
  real_wages: "realnye-zarplaty", industrial_production: "promyshlennoe-proizvodstvo",
  money_supply: "denezhnaya-massa", reserves: "zolotovalyutnye-rezervy",
  hh_index: "indeks-hh", gold: "zoloto", rgbi: "indeks-rgbi",
};
const slugOf = (code) => SLUGS[code] || String(code).replace(/_/g, "-").toLowerCase();

function shell({ title, desc, canonical, crumbs, body, jsonLd, assets, note }) {
  const css = assets && assets.css ? `<link rel="stylesheet" href="${assets.css}">` : "";
  const js = assets && assets.js ? `<script defer src="${assets.js}"></script>` : "";
  return `<!doctype html>
<html lang="ru"><head>
<meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>${esc(title)}</title>
<meta name="description" content="${esc(desc)}">
<link rel="canonical" href="${SITE}${canonical}">
<meta property="og:type" content="article"><meta property="og:title" content="${esc(title)}">
<meta property="og:description" content="${esc(desc)}"><meta property="og:url" content="${SITE}${canonical}">
<script type="application/ld+json">${JSON.stringify(jsonLd)}</script>
<style>:root{--paper:#F7F5F0;--ink:#1F1B16;--muted:#5A5248;--faint:#8A8072;--copper:#C97A4A;--line:#E4DFD5}
body{font-family:-apple-system,'Segoe UI',Roboto,sans-serif;background:var(--paper);color:var(--ink);margin:0;padding:0;line-height:1.55}
#seo-static{max-width:760px;margin:0 auto;padding:32px 20px 60px}
h1{font:600 30px/1.2 Georgia,serif;margin:6px 0 10px}h2{font:600 20px/1.3 Georgia,serif;margin:26px 0 8px}
.crumbs,.tag{font-size:12px;color:var(--faint)}.sub{color:var(--muted);font-size:14px}
.val{font:600 40px/1 'IBM Plex Mono',ui-monospace,monospace;color:var(--copper);margin:10px 0 2px}
.meta{font-size:12.5px;color:var(--faint);margin-bottom:18px}
table{border-collapse:collapse;width:100%;font-size:14px;margin:10px 0}
td,th{border-bottom:1px solid var(--line);padding:7px 8px;text-align:left}
.cta{display:inline-block;margin:18px 0;padding:10px 16px;background:var(--copper);color:#fff;border-radius:9px;text-decoration:none;font-weight:600}
a{color:var(--copper)}.note{font-size:12.5px;color:var(--faint);border-top:1px solid var(--line);margin-top:34px;padding-top:14px}
.chip{display:inline-block;border:1px solid var(--line);border-radius:999px;padding:5px 11px;margin:3px 4px 0 0;font-size:13px;text-decoration:none;color:var(--muted)}
#seo-boot{position:fixed;inset:0;z-index:99999;background:var(--paper);display:flex;flex-direction:column;align-items:center;justify-content:center;gap:18px}
#seo-boot .b-mark{font:700 26px/1 Georgia,serif;color:var(--copper)}
#seo-boot .b-bar{width:180px;height:3px;border-radius:2px;background:var(--line);overflow:hidden}
#seo-boot .b-bar i{display:block;width:40%;height:100%;background:var(--copper)}
@media (prefers-reduced-motion:no-preference){#seo-boot .b-bar i{animation:bs 1.1s ease-in-out infinite}}
@keyframes bs{0%{transform:translateX(-100%)}100%{transform:translateX(350%)}}
@media (prefers-color-scheme:dark){#seo-boot{background:#14110E}}
</style>${css}</head><body>
<div id="seo-static">
<p class="crumbs">${crumbs}</p>
${body}
<p class="note">${esc(note)}</p>
</div>
<div id="root"></div>
<script>
(function(){var b=document.createElement("div");b.id="seo-boot";
b.innerHTML='<div class="b-mark">Basis</div><div class="b-bar"><i></i></div>';
document.body.appendChild(b);
setTimeout(function(){var x=document.getElementById("seo-boot");if(x)x.remove();},12000);})();
["basis:company-ready","basis:app-ready"].forEach(function(evt){
window.addEventListener(evt,function(){
  var el=document.getElementById("seo-static");if(el)el.remove();
  var ld=document.getElementById("seo-boot");if(ld)ld.remove();
  document.body.style.background="";document.body.style.color="";document.body.style.font="";
});});
</script>${js}
</body></html>`;
}

function macroPage(ind, assets, all) {
  const v = (ind.values && (ind.values.level || Object.values(ind.values)[0])) || {};
  const unit = v.unit || ind.unit || "";
  const val = v.value != null ? `${v.value}${unit ? " " + unit : ""}` : "—";
  const related = all.filter((x) => x.code !== ind.code).slice(0, 12);
  const title = `${ind.title}${v.value != null ? `: ${val}` : ""} — что это и как влияет на рынок | Basis`;
  const desc = `${ind.title}${v.value != null ? ` — ${val}` : ""}${v.as_of ? ` на ${v.as_of}` : ""}. `
    + `${(ind.influence_short || "Как показатель влияет на российский рынок и оценку компаний.").slice(0, 130)}`;
  const body = `
<p class="tag">Экономическая статистика · Россия</p>
<h1>${esc(ind.title)}</h1>
<div class="val">${esc(val)}</div>
<p class="meta">${v.as_of ? `Значение на ${esc(v.as_of)}` : "Значение обновляется"}${
    v.change != null ? ` · изменение ${v.change > 0 ? "+" : ""}${esc(v.change)}` : ""}${
    v.source ? ` · источник: ${esc(v.source)}` : ""}${
    ind.frequency ? ` · периодичность: ${esc(ind.frequency)}` : ""}</p>
${ind.influence_short ? `<h2>Что это значит для инвестора</h2><p>${esc(ind.influence_short)}</p>` : ""}
${ind.influence_full && ind.influence_full !== ind.influence_short
    ? `<p>${esc(ind.influence_full)}</p>` : ""}
<h2>Где смотреть на платформе</h2>
<p>Показатель живёт в разделе «Экономическая статистика» Обозревателя: там он с графиком,
историей и проверкой данных. Макропоказатели у нас не висят отдельно от бумаг — ключевая
ставка через доходность ОФЗ входит в расчёт
<a href="/spravedlivaya-tsena-aktsiy/">справедливой цены</a> каждой акции, поэтому её
изменение двигает оценку компаний, а не только заголовки.</p>
<a class="cta" href="/?view=overview&obs=economy">Открыть экономическую статистику →</a>
<h2>Другие показатели</h2>
<div>${related.map((x) => `<a class="chip" href="/statistika/${slugOf(x.code)}/">${esc(x.title)}</a>`).join("")}</div>`;
  return shell({
    title, desc, canonical: `/statistika/${slugOf(ind.code)}/`,
    crumbs: `<a href="/">Basis</a> → <a href="/ekonomicheskaya-statistika-rossii/">Экономическая статистика</a> → ${esc(ind.title)}`,
    body, assets,
    jsonLd: {
      "@context": "https://schema.org", "@type": "Dataset", name: ind.title,
      description: desc, url: `${SITE}/statistika/${slugOf(ind.code)}/`,
      creator: { "@type": "Organization", name: "Basis", url: SITE },
      ...(v.source ? { provider: { "@type": "Organization", name: v.source } } : {}),
    },
    note: "Данные приводятся из официальных источников со ссылкой и датой. Basis — аналитический "
      + "слой, не брокер: не проводит сделок и не даёт сигналов «купить/продать».",
  });
}

function indexPage(ix, assets, all) {
  const chg = ix.change_pct;
  const title = `${ix.name} (${ix.ticker})${ix.level != null ? `: ${ix.level}` : ""} — значение и состав | Basis`;
  const desc = `${ix.name} (${ix.ticker})${ix.level != null ? ` — ${ix.level}` : ""}`
    + `${chg != null ? `, изменение ${chg > 0 ? "+" : ""}${chg}%` : ""}. Что показывает индекс, из чего состоит и как читать его движение.`;
  const related = all.filter((x) => x.ticker !== ix.ticker);
  const body = `
<p class="tag">Индексы Московской биржи</p>
<h1>${esc(ix.name)} <span style="color:var(--faint)">(${esc(ix.ticker)})</span></h1>
<div class="val">${esc(ix.level != null ? ix.level : "—")}</div>
<p class="meta">${chg != null ? `Изменение за день: ${chg > 0 ? "+" : ""}${esc(chg)}%` : "Значение обновляется"}${
    ix.change_abs != null ? ` (${ix.change_abs > 0 ? "+" : ""}${esc(ix.change_abs)} п.)` : ""}</p>
<h2>Что показывает индекс</h2>
<p>Индекс — это корзина бумаг, движение которой показывает состояние рынка в целом, а не
отдельной компании. По нему сравнивают результат портфеля: обогнали вы рынок или просто
шли вместе с ним. В разделе «Портфель» такое сравнение считается автоматически.</p>
<h2>Как читать движение</h2>
<p>Рост индекса означает, что бумаги корзины в среднем дорожали, но не говорит, что
дорожало всё: широкий рост и рост за счёт двух-трёх тяжёлых бумаг выглядят одинаково.
Поэтому рядом с индексом полезно смотреть ширину рынка и
<a href="/karta-rynka-aktsiy/">карту рынка</a> — там видно, какая часть бумаг реально
росла.</p>
<a class="cta" href="/?view=overview&obs=pulse">Открыть обзор рынка →</a>
${related.length ? `<h2>Другие индексы</h2><div>${related.map((x) =>
    `<a class="chip" href="/indeks/${String(x.ticker).toLowerCase()}/">${esc(x.name)}</a>`).join("")}</div>` : ""}
<div><a class="chip" href="/indeks-strakha-i-zhadnosti/">Индекс страха и жадности</a></div>`;
  return shell({
    title, desc, canonical: `/indeks/${String(ix.ticker).toLowerCase()}/`,
    crumbs: `<a href="/">Basis</a> → <a href="/obzor-rynka/">Обзор рынка</a> → ${esc(ix.name)}`,
    body, assets,
    jsonLd: {
      "@context": "https://schema.org", "@type": "WebPage", name: title,
      description: desc, url: `${SITE}/indeks/${String(ix.ticker).toLowerCase()}/`,
    },
    note: "Значения индексов приводятся с Московской биржи. Basis — аналитический слой, не брокер: "
      + "не проводит сделок и не даёт сигналов «купить/продать».",
  });
}

function fearGreedPage(assets) {
  const body = `
<p class="tag">Обзор рынка · настроения</p>
<h1>Индекс страха и жадности российского рынка</h1>
<p class="sub">Сводный индикатор настроений: что сейчас движет рынком — осторожность или азарт.</p>
<h2>Что это</h2>
<p>Индикатор сводит несколько рыночных признаков (динамику цен, волатильность, поведение
объёмов) в одну шкалу от страха до жадности. Он не предсказывает движение и не является
сигналом: это описание текущего состояния, полезное как фон для решений, а не как повод
для сделки.</p>
<h2>Как им пользоваться</h2>
<p>Крайние значения полезнее середины. Сильный страх говорит, что рынок уже заложил много
плохого, — но не о том, что падение закончилось. Сильная жадность означает, что хорошие
ожидания уже в ценах. Поэтому индикатор смотрят вместе с фундаментальной оценкой:
<a href="/spravedlivaya-tsena-aktsiy/">справедливой ценой бумаги</a>, а не вместо неё.</p>
<a class="cta" href="/?view=overview&obs=pulse">Посмотреть текущее значение →</a>
<div><a class="chip" href="/indeks/imoex/">Индекс МосБиржи</a><a class="chip" href="/indeks/rtsi/">Индекс РТС</a><a class="chip" href="/karta-rynka-aktsiy/">Карта рынка</a></div>`;
  return shell({
    title: "Индекс страха и жадности российского рынка — Basis",
    desc: "Индикатор настроений российского рынка: шкала от страха до жадности, как его читать и почему он не является сигналом к сделке.",
    canonical: "/indeks-strakha-i-zhadnosti/",
    crumbs: `<a href="/">Basis</a> → <a href="/obzor-rynka/">Обзор рынка</a> → Индекс страха и жадности`,
    body, assets,
    jsonLd: { "@context": "https://schema.org", "@type": "WebPage",
      name: "Индекс страха и жадности российского рынка",
      url: `${SITE}/indeks-strakha-i-zhadnosti/` },
    note: "Индикатор настроений — оценка, а не прогноз. Basis не даёт сигналов «купить/продать».",
  });
}

function main() {
  const manifestPath = path.join(BUILD, "asset-manifest.json");
  let assets = null;
  try {
    const m = JSON.parse(fs.readFileSync(manifestPath, "utf8"));
    assets = { js: m.files["main.js"], css: m.files["main.css"] };
  } catch { assets = null; }

  const macro = readSnap("macro-snapshot.json").rows;
  const indices = readSnap("indices-snapshot.json").rows;
  const urls = [];

  for (const ind of macro) {
    const dir = path.join(BUILD, "statistika", slugOf(ind.code));
    fs.mkdirSync(dir, { recursive: true });
    fs.writeFileSync(path.join(dir, "index.html"), macroPage(ind, assets, macro), "utf8");
    urls.push(`${SITE}/statistika/${slugOf(ind.code)}/`);
  }
  for (const ix of indices) {
    const dir = path.join(BUILD, "indeks", String(ix.ticker).toLowerCase());
    fs.mkdirSync(dir, { recursive: true });
    fs.writeFileSync(path.join(dir, "index.html"), indexPage(ix, assets, indices), "utf8");
    urls.push(`${SITE}/indeks/${String(ix.ticker).toLowerCase()}/`);
  }
  const fgDir = path.join(BUILD, "indeks-strakha-i-zhadnosti");
  fs.mkdirSync(fgDir, { recursive: true });
  fs.writeFileSync(path.join(fgDir, "index.html"), fearGreedPage(assets), "utf8");
  urls.push(`${SITE}/indeks-strakha-i-zhadnosti/`);

  // отдельная карта сайта — основную собирает generate-seo-pages.js, не мешаем ей
  const today = new Date().toISOString().slice(0, 10);
  fs.writeFileSync(path.join(BUILD, "sitemap-indicators.xml"),
    `<?xml version="1.0" encoding="UTF-8"?>\n<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n`
    + urls.map((u) => `<url><loc>${u}</loc><lastmod>${today}</lastmod><changefreq>daily</changefreq><priority>0.7</priority></url>`).join("\n")
    + `\n</urlset>\n`, "utf8");

  console.log(`Показатели и индексы: ${macro.length} статистики + ${indices.length} индексов + индекс страха; sitemap-indicators.xml — ${urls.length} URL`);
}

main();

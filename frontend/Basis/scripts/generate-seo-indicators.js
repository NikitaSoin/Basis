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
const { metrikaSnippet } = require("./metrika");
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
body{font-family:Inter,-apple-system,'Segoe UI',Roboto,sans-serif;background:var(--paper);color:var(--ink);margin:0;padding:0;line-height:1.55}
#seo-static{max-width:760px;margin:0 auto;padding:32px 20px 60px}
h1{font:600 30px/1.2 Fraunces,Georgia,serif;margin:6px 0 10px}h2{font:600 20px/1.3 Fraunces,Georgia,serif;margin:26px 0 8px}
.crumbs,.tag{font-size:12px;color:var(--faint)}.sub{color:var(--muted);font-size:14px}
.val{font:600 40px/1 'IBM Plex Mono',ui-monospace,monospace;color:var(--copper);margin:10px 0 2px}
.meta{font-size:12.5px;color:var(--faint);margin-bottom:18px}
table{border-collapse:collapse;width:100%;font-size:14px;margin:10px 0}
td,th{border-bottom:1px solid var(--line);padding:7px 8px;text-align:left}
.cta{display:inline-block;margin:18px 0;padding:10px 16px;background:var(--copper);color:#fff;border-radius:9px;text-decoration:none;font-weight:600}
a{color:var(--copper)}.note{font-size:12.5px;color:var(--faint);border-top:1px solid var(--line);margin-top:34px;padding-top:14px}
.chip{display:inline-block;border:1px solid var(--line);border-radius:999px;padding:5px 11px;margin:3px 4px 0 0;font-size:13px;text-decoration:none;color:var(--muted)}
#seo-boot{position:fixed;inset:0;z-index:99999;background:var(--paper);display:flex;flex-direction:column;align-items:center;justify-content:center;gap:18px}
#seo-boot .b-mark{font:700 26px/1 Fraunces,Georgia,serif;color:var(--copper)}
#seo-boot .b-bar{width:180px;height:3px;border-radius:2px;background:var(--line);overflow:hidden}
#seo-boot .b-bar i{display:block;width:40%;height:100%;background:var(--copper)}
@media (prefers-reduced-motion:no-preference){#seo-boot .b-bar i{animation:bs 1.1s ease-in-out infinite}}
@keyframes bs{0%{transform:translateX(-100%)}100%{transform:translateX(350%)}}
@media (prefers-color-scheme:dark){#seo-boot{background:#14110E}}
</style>${css}${metrikaSnippet()}
</head><body>
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

// История значений: настоящий контент вместо «одного числа с подписью». Показатели
// вроде ставки или инфляции ищут именно так — «по годам», «динамика», «история».
const SERIES = (() => {
  try {
    const raw = JSON.parse(fs.readFileSync(path.join(__dirname, "data", "macro-series-snapshot.json"), "utf8"));
    return raw.series || {};
  } catch { return {}; }
})();

function seriesHtml(code, unit) {
  const pts = SERIES[code];
  if (!Array.isArray(pts) || pts.length < 3) return "";
  // Показываем не все 60 точек, а срез по годам: для годовой динамики берём последнее
  // значение каждого года — таблица на 10 строк читается, на 60 нет.
  const byYear = new Map();
  for (const p of pts) {
    const y = String(p.as_of || "").slice(0, 4);
    if (y) byYear.set(y, p);
  }
  const rows = [...byYear.entries()].sort((a, b) => b[0].localeCompare(a[0])).slice(0, 11);
  if (rows.length < 3) return "";
  const last = pts[pts.length - 1], first = byYear.get(rows[rows.length - 1][0]);
  const dir = last && first && last.value !== first.value
    ? (last.value > first.value ? "выше" : "ниже") : null;
  return `<h2>Динамика по годам</h2>
${dir ? `<p>За период с ${esc(rows[rows.length - 1][0])} года показатель ${dir}: `
    + `${esc(first.value)}${unit ? " " + esc(unit) : ""} → ${esc(last.value)}${unit ? " " + esc(unit) : ""}.</p>` : ""}
<table><thead><tr><th>Период</th><th>Значение</th></tr></thead><tbody>${
    rows.map(([y, p]) => `<tr><td>${esc(p.as_of || y)}</td><td>${esc(p.value)}${unit ? " " + esc(unit) : ""}</td></tr>`).join("")
  }</tbody></table>
<p class="sub">Значения приводятся на указанные даты. Полный ряд с графиком — в разделе
«Экономическая статистика» платформы.</p>`;
}

function macroPage(ind, assets, all) {
  const v = (ind.values && (ind.values.level || Object.values(ind.values)[0])) || {};
  const unit = v.unit || ind.unit || "";
  const val = v.value != null ? `${v.value}${unit ? " " + unit : ""}` : "—";
  const related = all.filter((x) => x.code !== ind.code).slice(0, 12);
  // «график» и «сегодня» — устойчивые модификаторы в запросах (замер подсказок
  // 2026-07-31: «ключевая ставка цб график», «индекс pmi россии график»). График на
  // странице есть, поэтому слово в заголовке не обещание, а описание.
  const title = `${ind.title}${v.value != null ? `: ${val}` : ""} на сегодня — график, динамика | Basis`;
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
${seriesHtml(ind.code, v.unit || ind.unit)}
<h2>Где смотреть на платформе</h2>
<p>Показатель живёт в разделе «Экономическая статистика» Обозревателя: там он с графиком,
историей и проверкой данных. Макропоказатели у нас не висят отдельно от бумаг — ключевая
ставка через доходность ОФЗ входит в расчёт
<a href="/spravedlivaya-tsena-aktsiy/">справедливой цены</a> каждой акции, поэтому её
изменение двигает оценку компаний, а не только заголовки.</p>
<a class="cta" href="/ekonomicheskaya-statistika-rossii/">Открыть экономическую статистику →</a>
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

// Состав индексов и наши оценки по бумагам — то, чего на странице индекса не было вообще.
// Запрос «состав индекса мосбиржи» — 1983/мес, и это же 46 внутренних ссылок на карточки.
const COMPOSITION = (() => {
  try {
    return JSON.parse(fs.readFileSync(path.join(__dirname, "data", "index-composition-snapshot.json"), "utf8")).indices || {};
  } catch { return {}; }
})();
const FAIR = (() => {
  const m = new Map();
  for (const r of readSnap("fair-value-snapshot.json").rows) if (r && r.ticker) m.set(String(r.ticker), r);
  return m;
})();

/** MCFTR — та же корзина, что у IMOEX, отличается только учётом дивидендов. */
function compositionFor(ticker) {
  const own = COMPOSITION[ticker];
  if (own && own.rows && own.rows.length) return { rows: own.rows, borrowedFrom: null };
  const base = COMPOSITION.IMOEX;
  if (ticker === "MCFTR" && base && base.rows && base.rows.length) return { rows: base.rows, borrowedFrom: "IMOEX" };
  return { rows: [], borrowedFrom: null };
}

const num = (v, d = 2) => (v == null || !isFinite(v) ? "—" : Number(v).toLocaleString("ru-RU",
  { minimumFractionDigits: d, maximumFractionDigits: d }));
const signed = (v, d = 1) => (v == null || !isFinite(v) ? "—" : `${v > 0 ? "+" : ""}${num(v, d)}`);
const median = (a) => {
  const s = a.filter((x) => x != null && isFinite(x)).sort((x, y) => x - y);
  if (!s.length) return null;
  const m = Math.floor(s.length / 2);
  return s.length % 2 ? s[m] : (s[m - 1] + s[m]) / 2;
};

function indexPage(ix, assets, all) {
  const chg = ix.change_pct;
  const key = String(ix.ticker);
  const { rows: comp, borrowedFrom } = compositionFor(key);
  const hasCard = (t) => fs.existsSync(path.join(BUILD, "company", t, "index.html"));

  // Концентрация — главный факт об этом индексе, которого нигде не пишут словами.
  const top5 = comp.slice(0, 5).reduce((s, r) => s + (r.weight || 0), 0);
  const top10 = comp.slice(0, 10).reduce((s, r) => s + (r.weight || 0), 0);
  const upsides = comp.map((r) => FAIR.get(r.ticker)).filter(Boolean)
    .map((f) => f.upside_pct).filter((u) => u != null && isFinite(u));
  const medUp = median(upsides);
  const below = upsides.filter((u) => u < 0).length;

  const title = `${ix.name} (${ix.ticker})${ix.level != null ? `: ${ix.level}` : ""} сегодня — состав, вес бумаг, график | Basis`;
  const desc = `${ix.name} (${ix.ticker})${ix.level != null ? ` — ${ix.level}` : ""}`
    + `${chg != null ? `, ${chg > 0 ? "+" : ""}${chg}% за день` : ""}.`
    + (comp.length ? ` Полный состав: ${comp.length} бумаг с весами, на топ-5 приходится ${num(top5, 1)}%.` : "")
    + " Из чего состоит индекс, что им движет и как читать его динамику.";

  // Динамика по споту: спарклайн — 30 последних значений, это готовый «за месяц».
  const sp = Array.isArray(ix.spark) ? ix.spark.filter((x) => x != null && isFinite(x)) : [];
  const dyn = sp.length >= 5 ? {
    first: sp[0], last: sp[sp.length - 1], max: Math.max(...sp), min: Math.min(...sp),
    pct: ((sp[sp.length - 1] - sp[0]) / sp[0]) * 100,
  } : null;

  const compRows = comp.map((r, i) => {
    const f = FAIR.get(r.ticker);
    const link = hasCard(r.ticker)
      ? `<a href="/company/${esc(r.ticker)}/">${esc(r.name)}</a>` : esc(r.name);
    return `<tr><td>${i + 1}</td><td>${link} <span style="color:var(--faint)">${esc(r.ticker)}</span></td>`
      + `<td>${num(r.weight, 2)}%</td><td>${f && f.price != null ? num(f.price) : "—"}</td>`
      + `<td>${f && f.fair_value != null ? num(f.fair_value) : "—"}</td>`
      + `<td>${f && f.upside_pct != null ? signed(f.upside_pct) + "%" : "—"}</td></tr>`;
  }).join("");

  const related = all.filter((x) => x.ticker !== ix.ticker);
  const body = `
<p class="tag">Индексы Московской биржи · факт (данные биржи)</p>
<h1>${esc(ix.name)} <span style="color:var(--faint)">(${esc(ix.ticker)})</span></h1>
<div class="val">${esc(ix.level != null ? ix.level : "—")}</div>
<p class="meta">${chg != null ? `Изменение за день: ${chg > 0 ? "▲" : chg < 0 ? "▼" : ""} ${signed(chg, 2)}%` : "Значение обновляется"}${
    ix.change_abs != null ? ` (${signed(ix.change_abs, 2)} п.)` : ""}${
    ix.updated ? ` · обновлено ${esc(ix.updated)}` : ""}</p>

${comp.length ? `<p class="sub"><b>Коротко:</b> в корзине ${comp.length} бумаг; на пять крупнейших
приходится ${num(top5, 1)}% веса, на десять — ${num(top10, 1)}%. Это значит, что индекс движут
несколько тяжёлых бумаг, и «рынок вырос» не равно «выросли все».</p>
${medUp != null ? `<p class="sub">По модели Basis ${below} из ${upsides.length} бумаг корзины сейчас
торгуются <b>выше</b> расчётной справедливой цены, медианное расхождение — ${signed(Math.abs(medUp))}%.
Это <b>оценка модели, а не прогноз</b>: модель опирается на текущую прибыль и денежный поток и
поэтому строга к компаниям роста, которые оценивают по будущему. Смотрите не итог, а разбор
конкретной бумаги — в таблице ниже каждая ведёт на свою карточку.</p>` : ""}` : ""}

${dyn ? `<h2>Динамика за последний месяц</h2>
<table><tr><th>Показатель</th><th>Значение</th></tr>
<tr><td>Изменение за период</td><td>${signed(dyn.pct)}%</td></tr>
<tr><td>Максимум</td><td>${num(dyn.max)}</td></tr>
<tr><td>Минимум</td><td>${num(dyn.min)}</td></tr>
<tr><td>Размах</td><td>${num(((dyn.max - dyn.min) / dyn.min) * 100, 1)}%</td></tr></table>
<p class="sub">По последним ${sp.length} торговым дням. Полный график — в разделе «Рынок».</p>` : ""}

${comp.length ? `<h2>Состав индекса ${esc(ix.name)}: ${comp.length} бумаг и их вес</h2>
${borrowedFrom ? `<p class="sub">Корзина совпадает с Индексом МосБиржи — отличается только тем,
что ${esc(ix.name)} учитывает выплаченные дивиденды.</p>` : ""}
<p class="sub">Вес — доля бумаги в индексе по данным Московской биржи (факт). Справедливая цена и
потенциал — <b>оценка Basis</b> по методике карточки, а не прогноз и не рекомендация.</p>
<table><tr><th>№</th><th>Бумага</th><th>Вес</th><th>Цена, ₽</th><th>Справедливая, ₽</th><th>Потенциал</th></tr>
${compRows}</table>
<p class="sub">Каждая бумага — ссылка на разбор: финансы, оценка, риски, дивиденды.</p>` : ""}

<h2>Что движет индексом</h2>
<p>Индекс взвешен по капитализации: чем крупнее компания, тем сильнее её движение отражается
на общем значении.${comp.length ? ` Здесь ${num(top5, 1)}% веса — это ${comp.slice(0, 5).map((r) =>
  esc(r.ticker)).join(", ")}, поэтому день, когда падают только они, выглядит как падение всего
рынка.` : ""} Обратная ситуация тоже бывает: индекс стоит на месте, а большинство бумаг
снижается. Чтобы отличить одно от другого, нужна ширина рынка — сколько бумаг реально росло,
а не среднее по корзине. Это видно на <a href="/karta-rynka-aktsiy/">карте рынка</a>.</p>

<h2>Что такое индекс МосБиржи простыми словами</h2>
<p>Это корзина крупнейших российских акций, собранная биржей по правилам ликвидности и
капитализации. Само число (${esc(ix.level != null ? ix.level : "значение")}) не имеет смысла в
отрыве от истории — важно не оно, а изменение: индекс показывает, куда двигался рынок в целом.
Купить сам индекс нельзя, но можно купить фонд, повторяющий его состав, —
<a href="/funds/">такие фонды есть на бирже</a>.</p>

<h2>Зачем он частному инвестору</h2>
<p>Это точка отсчёта. Ваш портфель вырос на 8% — много это или мало, зависит от того, что за
это время сделал рынок. Если индекс прибавил 15%, портфель отстал, хотя формально в плюсе.
В разделе «Портфель» такое сравнение считается автоматически.</p>

<a class="cta" href="/obzor-rynka/">Что происходит на рынке сегодня →</a>
${related.length ? `<h2>Другие индексы</h2><div>${related.map((x) =>
    `<a class="chip" href="/indeks/${String(x.ticker).toLowerCase()}/">${esc(x.name)}</a>`).join("")}</div>` : ""}
<div><a class="chip" href="/indeks-strakha-i-zhadnosti/">Индекс страха и жадности</a><a class="chip" href="/skrining-aktsiy/">Скринер акций</a><a class="chip" href="/nedootsenennye-aktsii/">Недооценённые акции</a></div>`;

  return shell({
    title, desc, canonical: `/indeks/${key.toLowerCase()}/`,
    crumbs: `<a href="/">Basis</a> → <a href="/obzor-rynka/">Обзор рынка</a> → ${esc(ix.name)}`,
    body, assets,
    jsonLd: {
      "@context": "https://schema.org", "@type": "FAQPage",
      name: title, url: `${SITE}/indeks/${key.toLowerCase()}/`,
      mainEntity: [
        {
          "@type": "Question", name: `Что такое ${ix.name} простыми словами?`,
          acceptedAnswer: {
            "@type": "Answer",
            text: `Это корзина крупнейших российских акций, собранная Московской биржей. Само значение `
              + `не важно в отрыве от истории — важно его изменение: индекс показывает, куда двигался рынок в целом.`,
          },
        },
        comp.length ? {
          "@type": "Question", name: `Из чего состоит ${ix.name}?`,
          acceptedAnswer: {
            "@type": "Answer",
            text: `В индекс входят ${comp.length} бумаг. Крупнейшие по весу: `
              + comp.slice(0, 5).map((r) => `${r.name} — ${r.weight}%`).join(", ")
              + `. На пять крупнейших приходится ${num(top5, 1)}% веса индекса.`,
          },
        } : null,
        {
          "@type": "Question", name: `Почему ${ix.name} растёт или падает?`,
          acceptedAnswer: {
            "@type": "Answer",
            text: `Индекс взвешен по капитализации, поэтому его движение определяют несколько самых `
              + `крупных бумаг. Индекс может падать, когда большинство акций растёт, — если снижаются тяжёлые.`,
          },
        },
      ].filter(Boolean),
    },
    note: "Значения и веса — данные Московской биржи (факт). Справедливая цена и потенциал — оценка Basis "
      + "по собственной методике. Basis — аналитический слой, не брокер: не проводит сделок и не даёт "
      + "сигналов «купить/продать».",
  });
}


// Секторальный индекс MOEX: «Нефть и газ», «Финансы», «Металлы и добыча»… Владелец
// перечислил их поимённо (2026-07-31) — это ходовые запросы («индекс нефть и газ
// мосбиржа»), а собственных адресов у них не было.
const SECTOR_SLUGS = {
  MOEXOG: "neft-i-gaz", MOEXEU: "elektroenergetika", MOEXTL: "telekommunikatsii",
  MOEXCH: "khimiya-i-neftekhimiya", MOEXMM: "metally-i-dobycha", MOEXFN: "finansy",
  MOEXCN: "potrebitelskiy-sektor", MOEXIT: "informatsionnye-tekhnologii",
  MOEXTN: "transport", MOEXRE: "stroitelnye-kompanii",
};
const sectorSlug = (t) => SECTOR_SLUGS[t] || String(t).toLowerCase();

function sectorPage(sx, assets, all) {
  const chg = sx.change_pct;
  const title = `Индекс «${sx.name}» (${sx.ticker}) Мосбиржи${chg != null ? `: ${chg > 0 ? "+" : ""}${chg}%` : ""} — состав и динамика | Basis`;
  const desc = `Секторальный индекс «${sx.name}» (${sx.ticker}) Московской биржи`
    + `${chg != null ? `, изменение ${chg > 0 ? "+" : ""}${chg}% за день` : ""}: что в него входит, `
    + `как читать движение сектора и где смотреть разборы его компаний.`;
  const others = all.filter((x) => x.ticker !== sx.ticker);
  const body = `
<p class="tag">Секторальные индексы MOEX</p>
<h1>Индекс «${esc(sx.name)}» <span style="color:var(--faint)">(${esc(sx.ticker)})</span></h1>
<div class="val">${esc(sx.level != null ? sx.level : (chg != null ? `${chg > 0 ? "+" : ""}${chg}%` : "—"))}</div>
<p class="meta">${chg != null ? `Изменение за день: ${chg > 0 ? "+" : ""}${esc(chg)}%` : "Значение обновляется"}</p>
<h2>Что показывает</h2>
<p>Индекс отслеживает бумаги одного сектора, поэтому его движение отвечает на вопрос
«дело в компании или во всём секторе». Если бумага падает вместе с сектором — причина
скорее общая (цены на сырьё, регулирование, ставка), если против него — искать причину
надо в самой компании.</p>
<h2>Как пользоваться</h2>
<p>Сравнение с широким рынком (<a href="/indeks/imoex/">Индексом МосБиржи</a>) показывает,
какие сектора тянут рынок, а какие отстают. Для портфеля это ещё и проверка
диверсификации: несколько бумаг одного сектора движутся почти как одна позиция — это
видно в <a href="/analiz-portfelya/">матрице корреляций</a>.</p>
<a class="cta" href="/obzor-rynka/">Открыть обзор рынка →</a>
<h2>Другие секторы</h2>
<div>${others.map((x) => `<a class="chip" href="/indeks/sektor/${sectorSlug(x.ticker)}/">${esc(x.name)}</a>`).join("")}</div>
<div style="margin-top:10px"><a class="chip" href="/indeks/imoex/">Индекс МосБиржи</a><a class="chip" href="/karta-rynka-aktsiy/">Карта рынка</a></div>`;
  return shell({
    title, desc, canonical: `/indeks/sektor/${sectorSlug(sx.ticker)}/`,
    crumbs: `<a href="/">Basis</a> → <a href="/obzor-rynka/">Обзор рынка</a> → ${esc(sx.name)}`,
    body, assets,
    jsonLd: { "@context": "https://schema.org", "@type": "WebPage", name: title,
      description: desc, url: `${SITE}/indeks/sektor/${sectorSlug(sx.ticker)}/` },
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
<a class="cta" href="/obzor-rynka/">Посмотреть текущее значение →</a>
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
  const sectors = readSnap("sectors-snapshot.json").rows;
  for (const sx of sectors) {
    const dir = path.join(BUILD, "indeks", "sektor", sectorSlug(sx.ticker));
    fs.mkdirSync(dir, { recursive: true });
    fs.writeFileSync(path.join(dir, "index.html"), sectorPage(sx, assets, sectors), "utf8");
    urls.push(`${SITE}/indeks/sektor/${sectorSlug(sx.ticker)}/`);
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

  // ─── Индекс карт сайта ────────────────────────────────────────────────────────
  // Пишется ЗДЕСЬ, потому что этот скрипт в цепочке сборки идёт последним: к моменту
  // его запуска все три карты уже созданы. Зачем нужен: в Search Console и Вебмастере
  // добавляется ОДИН адрес вместо трёх, а новые карты подхватываются автоматически —
  // не придётся вспоминать, что при добавлении раздела надо идти в панель руками.
  {
    const maps = ["sitemap.xml", "sitemap-instruments.xml", "sitemap-indicators.xml"]
      .filter((f) => fs.existsSync(path.join(BUILD, f)));
    fs.writeFileSync(path.join(BUILD, "sitemap-index.xml"),
      `<?xml version="1.0" encoding="UTF-8"?>\n<sitemapindex xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n`
      + maps.map((f) => `<sitemap><loc>${SITE}/${f}</loc><lastmod>${today}</lastmod></sitemap>`).join("\n")
      + `\n</sitemapindex>\n`, "utf8");
    console.log(`sitemap-index.xml: ${maps.length} карт (${maps.join(", ")})`);
  }

  console.log(`Показатели и индексы: ${macro.length} статистики + ${indices.length} индексов + `
    + `${sectors.length} секторальных + индекс страха; sitemap-indicators.xml — ${urls.length} URL`);
}

main();

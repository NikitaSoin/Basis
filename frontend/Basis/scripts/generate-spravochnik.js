#!/usr/bin/env node
/**
 * Раздел «Справочник» — /spravochnik/ и /spravochnik/<слаг>/.
 *
 * ЗАДАЧА ВЛАДЕЛЬЦА (11.09.2026): «человек попадает на отдельную SEO-страницу, читает и
 * уходит». Нужен справочник с ответами на вопросы инвесторов, из которого какая-то доля
 * читателей идёт дальше в платформу — «читает про бизнес-модель лизинга, а потом может
 * почитать готовый разбор Европлана». Постановка — docs/knowledge-hub-postanovka.md.
 *
 * 🔴 ПОЧЕМУ ЭТИ СТРАНИЦЫ НЕ ЗАБИРАЕТ ПРИЛОЖЕНИЕ (и не должно). Очевидное решение —
 * «пусть адрес открывает раздел внутри SPA» — мы уже пробовали и откатили 31.08.2026:
 * перехват заканчивается удалением #seo-static, Яндекс исполняет скрипты и видит вместо
 * статьи таблицу котировок. Визиты из поиска на /bonds/vdo/ (лучшая точка входа сайта,
 * 19 в месяц) прекратились в день выкатки. Показывать текст роботу и прятать от
 * человека — подмена контента, за неё наказывают.
 * Поэтому здесь принцип ОБРАТНЫЙ: текст статьи остаётся в DOM ВСЕГДА, а «платформенность»
 * добавляется поверх него — живым блоком компании-эталона, который подгружается по API
 * прямо в статью. Робот и человек видят один и тот же текст, разница только в том, что у
 * человека внутри статьи оживает карточка бумаги.
 *
 * 🔴 БАНДЛ ПРИЛОЖЕНИЯ СЮДА НЕ ПОДКЛЮЧАЕТСЯ НАМЕРЕННО. Во-первых, приложение всё равно не
 * знает адрес /spravochnik/ и ушло бы в ветку staticOnly (App.js) — то есть 540 КБ
 * скачались бы, чтобы ничего не нарисовать. Во-вторых, статья должна открываться быстро:
 * это верхушка воронки, человек пришёл с поиска и ещё ничего нам не должен. Переходы
 * внутрь платформы — обычными ссылками.
 *
 * ЖИВОЙ БЛОК: один GET к /api/companies/by-ticker/<TICKER>/bfv (тот же BFV-движок, что
 * считает справедливую цену в карточке — второго числа другой методикой на сайте быть не
 * должно). API недоступен → блок просто не появляется, статья цела: заглушка в разметке
 * несёт статичное объяснение и ссылку, скрипт только дополняет её числами.
 */
"use strict";
const fs = require("fs");
const path = require("path");
const ARTICLES = require("./spravochnik-content");
const { metrikaSnippet } = require("./metrika");
const { analyticsSnippet, API_BASE } = require("./basis-analytics-tag");

const SITE = "https://inbasis.ru";
const BUILD = path.join(__dirname, "..", "build");

const esc = (v) => String(v == null ? "" : v)
  .replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;").replace(/"/g, "&quot;");

/* ------------------------------- оформление ------------------------------- */
// Палитра и шрифты — токены Basis (кремовая бумага, медь, Fraunces/Inter/IBM Plex Mono).
// Стили инлайновые по той же причине, что и на остальных пре-рендеренных страницах:
// внешний CSS — это ещё один запрос до первого экрана на странице, которую читают
// один раз и с телефона.
const CSS = `:root{--paper:#F7F5F0;--surface:#FFFDF9;--ink:#1F1B16;--muted:#5A5248;
  --faint:#8A8072;--copper:#C97A4A;--line:#E4DFD5;--up:#2E7D5B;--down:#B3452F}
*{box-sizing:border-box}
body{font-family:Inter,-apple-system,'Segoe UI',Roboto,sans-serif;background:var(--paper);
  color:var(--ink);margin:0;line-height:1.6;-webkit-font-smoothing:antialiased}
.top{border-bottom:1px solid var(--line);background:var(--surface)}
.top .in{max-width:820px;margin:0 auto;padding:12px 20px;display:flex;align-items:center;
  gap:18px;flex-wrap:wrap}
.top .b{font:700 19px/1 Fraunces,Georgia,serif;color:var(--copper);text-decoration:none}
.top a.nav{font-size:13.5px;color:var(--muted);text-decoration:none}
.top a.nav:hover{color:var(--copper)}
#seo-static{max-width:820px;margin:0 auto;padding:26px 20px 64px}
.crumbs{font-size:12.5px;color:var(--faint);margin:0 0 14px}
.crumbs a{color:var(--faint)}
h1{font:600 33px/1.22 Fraunces,Georgia,serif;margin:0 0 14px;letter-spacing:-.01em}
h2{font:600 21px/1.3 Fraunces,Georgia,serif;margin:32px 0 10px}
p{margin:0 0 13px}
.answer{background:var(--surface);border:1px solid var(--line);border-left:3px solid var(--copper);
  border-radius:12px;padding:16px 18px;margin:0 0 8px;font-size:16.5px}
.answer .lbl{font-size:11.5px;letter-spacing:.06em;text-transform:uppercase;color:var(--faint);
  display:block;margin-bottom:6px}
.tagline{font-size:12.5px;color:var(--faint);margin:0 0 26px}
a{color:var(--copper)}
.bridge{border:1px solid var(--line);border-radius:12px;background:var(--surface);
  padding:16px 18px;margin:26px 0}
.bridge .kicker{font-size:11.5px;letter-spacing:.06em;text-transform:uppercase;color:var(--faint)}
.bridge h3{font:600 19px/1.3 Fraunces,Georgia,serif;margin:6px 0 8px}
.bridge .why{font-size:14.5px;color:var(--muted);margin:0 0 12px}
.nums{display:flex;gap:22px;flex-wrap:wrap;margin:12px 0 4px;padding:12px 0;
  border-top:1px solid var(--line);border-bottom:1px solid var(--line)}
.nums.hidden{display:none}
.num .k{font-size:11.5px;color:var(--faint);display:block}
.num .v{font:600 19px/1.25 'IBM Plex Mono',ui-monospace,monospace;font-variant-numeric:tabular-nums}
.num .v.up{color:var(--up)}.num .v.down{color:var(--down)}
.epi{font-size:11.5px;color:var(--faint);margin:8px 0 0}
.cta{display:inline-block;margin:12px 8px 0 0;padding:10px 16px;background:var(--copper);
  color:#fff;border-radius:9px;text-decoration:none;font-weight:600;font-size:14.5px}
.cta.ghost{background:transparent;color:var(--copper);border:1px solid var(--copper)}
.chips{margin:8px 0 0}
.chip{display:inline-block;border:1px solid var(--line);border-radius:999px;padding:6px 12px;
  margin:4px 5px 0 0;font-size:13.5px;text-decoration:none;color:var(--muted);background:var(--surface)}
.chip:hover{border-color:var(--copper);color:var(--copper)}
.cards{display:grid;grid-template-columns:repeat(auto-fit,minmax(240px,1fr));gap:14px;margin:14px 0}
.card{border:1px solid var(--line);border-radius:12px;background:var(--surface);padding:15px 16px;
  text-decoration:none;color:inherit;display:block}
.card:hover{border-color:var(--copper)}
.card .q{font:600 17px/1.3 Fraunces,Georgia,serif;margin:0 0 6px}
.card .d{font-size:13.5px;color:var(--muted);margin:0}
.note{font-size:12.5px;color:var(--faint);border-top:1px solid var(--line);margin-top:38px;padding-top:14px}
@media (prefers-color-scheme:dark){
  :root{--paper:#14110E;--surface:#1B1713;--ink:#F2EDE5;--muted:#B6ACA0;--faint:#8A8072;--line:#2E2822}
}
@media (max-width:600px){h1{font-size:27px}#seo-static{padding:20px 16px 52px}}`;

/* --------------------------- живой блок-мостик ---------------------------- */
// Один запрос на статью. Ошибка/таймаут/пустой ответ — блок остаётся статичным.
const bridgeScript = (ticker) => `
(function(){
  var host=document.getElementById("bfv-nums");if(!host||!window.fetch)return;
  var ctl=("AbortController" in window)?new AbortController():null;
  if(ctl)setTimeout(function(){try{ctl.abort();}catch(e){}},8000);
  fetch(${JSON.stringify(API_BASE)}+"/api/companies/by-ticker/${ticker}/bfv",
        ctl?{signal:ctl.signal}:{})
    .then(function(r){return r.ok?r.json():null;})
    .then(function(d){
      if(!d||d.status!=="ok"||d.current_price==null)return;
      var f=function(v){return v==null?"—":new Intl.NumberFormat("ru-RU",
        {maximumFractionDigits:v>=100?0:2}).format(v)+" ₽";};
      var up=d.upside_pct;
      var cls=up==null?"":(up>=0?"up":"down");
      var sign=up==null?"":(up>=0?"▲ +":"▼ ");
      var html=""
        +'<div class="num"><span class="k">Цена сейчас</span>'
        +'<span class="v">'+f(d.current_price)+'</span></div>'
        +'<div class="num"><span class="k">Справедливая цена Basis</span>'
        +'<span class="v">'+f(d.fair_price)+'</span></div>'
        +(up==null?"":'<div class="num"><span class="k">Потенциал</span>'
          +'<span class="v '+cls+'">'+sign+new Intl.NumberFormat("ru-RU",
            {maximumFractionDigits:1}).format(Math.abs(up))+'%</span></div>')
        +(d.verdict?'<div class="num"><span class="k">Вердикт модели</span>'
          +'<span class="v">'+String(d.verdict).replace(/[<>]/g,"")+'</span></div>':"");
      host.innerHTML=html;
      host.className="nums";
      var e=document.getElementById("bfv-epi");
      if(e)e.textContent="Оценка модели (BFV), не прогноз цены и не рекомендация. "
        +"Пересчитывается от живой котировки при каждом открытии страницы.";
    })
    .catch(function(){});
})();
// Клик по мостику — активационное событие раздела. Считаем ОБА перехода (середина
// и конец) с пометкой place: ОТК 11.09.2026 показал, что один мостик в середине
// заставляет читателя выбирать между «уйти сейчас» и «дочитать», а дочитавшему в
// конце идти некуда. Две точки — два разных адресата, и по place видно, какая
// работает. Без него «дошёл ли человек из статьи
// в продукт» пришлось бы вычислять по переходам между страницами, а это врёт: переход
// мог быть из шапки, из «похожих» или из хлебных крошек.
(function(){
  var els=document.querySelectorAll("[data-bridge],[data-bridge-end]");
  Array.prototype.forEach.call(els,function(a){
    var mid=a.hasAttribute("data-bridge");
    a.addEventListener("click",function(){
      try{ if(window.__basisAnalytics) window.__basisAnalytics.action("spravochnik_bridge",
        {ticker:a.getAttribute(mid?"data-bridge":"data-bridge-end"),
         place:mid?"middle":"end"}); }catch(e){}
    });
  });
})();`;

function bridgeHtml(a) {
  const b = a.bridge;
  const href = `/company/${b.ticker}/${b.tab || ""}${b.tab ? "/" : ""}`;
  return `<p class="tagline">Дальше — как эта механика выглядит у конкретной торгуемой компании.
Числа живые: считаются от текущей котировки в момент открытия страницы.</p>
<div class="bridge">
<span class="kicker">Проверьте на реальной компании</span>
<h3>${esc(b.name)} (${esc(b.ticker)})</h3>
<p class="why">${esc(b.why)}</p>
<div id="bfv-nums" class="nums hidden"></div>
<p class="epi" id="bfv-epi">Разбор ${esc(b.tabLabel || "компании")} — на карточке ${esc(b.name)}.</p>
<a class="cta" href="${href}" data-bridge="${esc(b.ticker)}">Открыть разбор ${esc(b.nameGen || b.name)} →</a>
${a.tool ? `<a class="cta ghost" href="${esc(a.tool.href)}">${esc(a.tool.label)}</a>` : ""}
</div>`;
}

/* ------------------------------- страница --------------------------------- */
function shell({ title, desc, canonical, body, jsonLd, script }) {
  return `<!doctype html>
<html lang="ru"><head>
<meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>${esc(title)}</title>
<meta name="description" content="${esc(desc)}">
<link rel="canonical" href="${SITE}${canonical}">
<meta property="og:type" content="article"><meta property="og:title" content="${esc(title)}">
<meta property="og:description" content="${esc(desc)}"><meta property="og:url" content="${SITE}${canonical}">
<script type="application/ld+json">${JSON.stringify(jsonLd)}</script>
<style>${CSS}</style>${metrikaSnippet()}${analyticsSnippet()}
</head><body>
<header class="top"><div class="in">
<a class="b" href="/">Basis</a>
<a class="nav" href="/?view=companies">Рынок</a>
<a class="nav" href="/?view=screener">Скрининг</a>
<a class="nav" href="/?view=overview">Обозреватель</a>
<a class="nav" href="/?view=portfolio">Портфель</a>
<a class="nav" href="/spravochnik/">Справочник</a>
</div></header>
<div id="seo-static">
${body}
</div>${script ? `\n<script>${script}</script>` : ""}
</body></html>`;
}

function articlePage(a) {
  // 🔴 Мостик стоит В СЕРЕДИНЕ текста, а не в конце. Проверил на собранной странице:
  // при вставке после всех разделов живой блок оказывается ниже трёх экранов прокрутки —
  // до него доходит меньшинство, а именно он и есть переход в продукт. Ставим после
  // второго раздела: человек уже получил ответ и готов посмотреть на реальную бумагу.
  const rendered = a.sections.map((s) =>
    `<h2>${esc(s.h)}</h2>\n${s.p.map((t) => `<p>${esc(t)}</p>`).join("\n")}`);
  const at = Math.min(2, rendered.length);
  const secs = rendered.slice(0, at).join("\n") + "\n" + bridgeHtml(a) + "\n"
    + rendered.slice(at).join("\n");
  const peers = (a.peers || []).length
    ? `<h2>Другие компании этого типа</h2>
<p>Механика одна, но реализация разная — сравнение полезнее одного примера.</p>
<div class="chips">${a.peers.map((p) =>
      `<a class="chip" href="/company/${esc(p.ticker)}/">${esc(p.name)} (${esc(p.ticker)})${
        p.note ? " — " + esc(p.note) : ""}</a>`).join("")}</div>`
    : "";
  const terms = (a.terms || []).length
    ? `<div class="chips">${a.terms.map((t) =>
      `<a class="chip" href="${esc(t.href)}">${esc(t.label)}</a>`).join("")}</div>` : "";
  const related = (a.related || []).map((slug) => ARTICLES.find((x) => x.slug === slug))
    .filter(Boolean);
  const relatedHtml = related.length
    ? `<h2>Читать дальше</h2>
<div class="cards">${related.map((r) =>
      `<a class="card" href="/spravochnik/${r.slug}/"><p class="q">${esc(r.question)}</p>
<p class="d">${esc(r.answer.slice(0, 110))}…</p></a>`).join("")}</div>` : "";

  const body = `<p class="crumbs"><a href="/">Basis</a> → <a href="/spravochnik/">Справочник</a> → ${esc(a.question)}</p>
<h1>${esc(a.question)}?</h1>
<div class="answer"><span class="lbl">Короткий ответ</span>${esc(a.answer)}</div>
<p class="tagline">Объяснение — суждение аналитиков Basis. Числа в блоке ниже — живые, из расчётной модели платформы.</p>
${secs}
${peers}
<h2>Что с этим делать дальше</h2>
<p>Механику вы теперь знаете — дальше её стоит приложить к конкретной бумаге: посмотреть,
как эти же метрики выглядят у ${esc(a.bridge.nameGen || a.bridge.name)}, и сравнить с другими компаниями
того же типа${a.tool ? ` (${esc(a.tool.note || "")})` : ""}.</p>
<p><a class="cta" href="/company/${esc(a.bridge.ticker)}/${a.bridge.tab ? esc(a.bridge.tab) + "/" : ""}" data-bridge-end="${esc(a.bridge.ticker)}">Разбор ${esc(a.bridge.nameGen || a.bridge.name)} с оценкой Basis →</a>${
    a.tool ? `<a class="cta ghost" href="${esc(a.tool.href)}">${esc(a.tool.label)}</a>` : ""}</p>
${terms ? `<h2>Термины из статьи</h2>${terms}` : ""}
${relatedHtml}
<p class="note">Basis — независимый аналитический слой, а не брокер: мы не проводим сделок и
не даём сигналов «купить» или «продать». Объяснения в статье — суждение, расчётные числа
в блоке компании — оценка модели на текущей котировке.</p>`;

  return shell({
    title: a.title,
    desc: a.desc,
    canonical: `/spravochnik/${a.slug}/`,
    body,
    script: bridgeScript(a.bridge.ticker),
    jsonLd: {
      "@context": "https://schema.org", "@type": "FAQPage",
      mainEntity: [{
        "@type": "Question", name: a.question + "?",
        acceptedAnswer: { "@type": "Answer", text: a.answer },
      }],
      url: `${SITE}/spravochnik/${a.slug}/`,
      publisher: { "@type": "Organization", name: "Basis", url: SITE },
    },
  });
}

function indexPage() {
  const body = `<p class="crumbs"><a href="/">Basis</a> → Справочник</p>
<h1>Справочник Basis</h1>
<div class="answer"><span class="lbl">Что это</span>Ответы на вопросы, с которыми
инвестор приходит раньше, чем с тикером: как устроен бизнес, что означает показатель,
как оценивать бумагу. Каждый ответ заканчивается не точкой, а разбором реальной компании
с Мосбиржи — чтобы теорию сразу можно было проверить на живых числах.</div>
<h2>Как устроен бизнес</h2>
<div class="cards">${ARTICLES.map((a) =>
    `<a class="card" href="/spravochnik/${a.slug}/"><p class="q">${esc(a.question)}</p>
<p class="d">${esc(a.answer.slice(0, 130))}…</p></a>`).join("")}</div>
<h2>Термины и показатели</h2>
<p>Определения метрик и рыночных терминов живут в отдельном разделе — там же примеры на
реальных бумагах: <a href="/pokazateli/">показатели и термины</a>. Макроэкономические ряды
с графиками — в <a href="/ekonomicheskaya-statistika-rossii/">экономической статистике</a>.</p>
<h2>Куда идти дальше</h2>
<p>Разборы компаний — в разделе <a href="/?view=companies">Рынок</a>, отбор бумаг по
метрикам — в <a href="/?view=screener">Скрининге</a>, рыночный фон — в
<a href="/?view=overview">Обозревателе</a>.</p>
<p class="note">Basis — независимый аналитический слой, а не брокер: мы не проводим сделок
и не даём сигналов «купить» или «продать».</p>`;
  return shell({
    title: "Справочник Basis — как устроены бизнесы и что означают показатели",
    desc: "Ответы на вопросы инвестора простыми словами: на чём зарабатывают лизинговые "
      + "компании, банки, застройщики. Каждый ответ — с разбором реальной компании с Мосбиржи.",
    canonical: "/spravochnik/",
    body,
    jsonLd: {
      "@context": "https://schema.org", "@type": "CollectionPage",
      name: "Справочник Basis", url: `${SITE}/spravochnik/`,
      publisher: { "@type": "Organization", name: "Basis", url: SITE },
    },
  });
}

/* --------------------------------- запуск --------------------------------- */
function main() {
  if (!fs.existsSync(BUILD)) {
    console.error("Справочник: папки build/ нет — запускать после craco build.");
    process.exit(1);
  }
  const urls = [];
  const root = path.join(BUILD, "spravochnik");
  fs.mkdirSync(root, { recursive: true });
  fs.writeFileSync(path.join(root, "index.html"), indexPage(), "utf8");
  urls.push(`${SITE}/spravochnik/`);

  for (const a of ARTICLES) {
    const dir = path.join(root, a.slug);
    fs.mkdirSync(dir, { recursive: true });
    fs.writeFileSync(path.join(dir, "index.html"), articlePage(a), "utf8");
    urls.push(`${SITE}/spravochnik/${a.slug}/`);
  }

  const today = new Date().toISOString().slice(0, 10);
  fs.writeFileSync(path.join(BUILD, "sitemap-spravochnik.xml"),
    `<?xml version="1.0" encoding="UTF-8"?>\n<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n`
    + urls.map((u) => `<url><loc>${u}</loc><lastmod>${today}</lastmod><changefreq>monthly</changefreq><priority>0.8</priority></url>`).join("\n")
    + `\n</urlset>\n`, "utf8");

  console.log(`Справочник: ${ARTICLES.length} статей + индекс; sitemap-spravochnik.xml — ${urls.length} URL`);
}

main();

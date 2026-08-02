#!/usr/bin/env node
/**
 * Генератор статических SEO-страниц ИНСТРУМЕНТОВ (не-акции): облигации, фонды,
 * фьючерсы, валюта/металлы. Задача №2 SEO-программы (аудит docs/audit-2026-07/04-seo.md,
 * п.4 топа: 0 страниц на ~3100 облигаций — крупнейший неиспользованный актив).
 *
 * ДАННЫЕ: НЕ из БД (на билд-окружении Timeweb её нет) — из JSON-снапшотов
 * scripts/data/*-snapshot.json, снятых с прод-API скриптом fetch-seo-snapshots.js
 * и закоммиченных в repo. Дата снапшота показывается на каждой странице ЯВНО
 * («данные на DD.MM.YYYY») и идёт в lastmod sitemap — честность про свежесть.
 *
 * ГЕНЕРИТ:
 *   /bonds/{SECID}/            — страница каждого выпуска облигации (~3263)
 *   /bonds/                    — каталог + 6 подборок-магнитов:
 *   /bonds/ofz/                — все ОФЗ + кривая доходности (таблица по срокам)
 *   /bonds/vdo/                — высокодоходные с оценкой «доходность vs риск»
 *   /bonds/kvazivalyutnye/     — замещающие/валютные (USD/CNY/EUR)
 *   /bonds/flotery/            — флоатеры с надбавкой к ключевой ставке
 *   /bonds/korotkie/           — погашение до года
 *   /bonds/ezhemesyachnyy-kupon/ — купон ~раз в месяц
 *   /bonds/vse/{n}/            — полный список ссылок (пагинация, краулинг-хаб)
 *   /funds/{SECID}/ + /funds/  — фонды (тип, TER в % и деньгах, ликвидность)
 *   /futures/{SECID}/ + /futures/ — фьючерсы (БА, ГО, плечо, экспирация); экспирированные НЕ генерятся
 *   /valyuta-metally/          — один лендинг на 6 спот-инструментов (данных на
 *                                отдельные страницы мало — цена/изменение, было бы 6 дорвеев)
 *   sitemap-instruments.xml    — отдельный sitemap (lastmod = дата снапшота).
 *                                ⚠️ добавить ссылку на него в public/robots.txt.
 *
 * КОМПЛАЕНС: без «купить/продать/рекомендуем»; светофор — «оценка соотношения
 * доходности и риска»; эпистемические теги (факт/оценка) на блоках; дисклеймер.
 *
 * ЗАПУСК: node scripts/generate-seo-instruments.js [outDir]   (по умолч. ../build)
 * Только built-in модули Node (Python на билд-окружении Timeweb нет).
 * Снапшоты отсутствуют → мягкий пропуск (сборку не валим).
 */
"use strict";
const fs = require("fs");
const { metrikaSnippet } = require("./metrika");
const path = require("path");

const _DATA_DIR = path.join(__dirname, "data");
const _OUT = process.argv[2] ? path.resolve(process.argv[2]) : path.join(__dirname, "..", "build");
const _SITE = "https://inbasis.ru";
// на эмитента/базовый актив ссылаемся ТОЛЬКО если страница компании реально есть
// (иначе ссылка в soft-404: у части issuer_ticker — ALFA, RSHB — карточек нет)
const _COMPANIES_DIR = path.join(__dirname, "..", "..", "..", "backend", "companies");
function companyExists(tk) {
  if (!tk) return false;
  try { return fs.existsSync(path.join(_COMPANIES_DIR, tk, "financials.json")); } catch { return false; }
}

/* ----------------------------- утилиты ----------------------------- */

function strip(s) { return (s || "").replace(/\s+/g, " ").trim(); }
function escapeHtml(s) {
  return String(s == null ? "" : s)
    .replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;").replace(/'/g, "&#39;");
}
function truncate(s, n) {
  s = strip(s);
  if (s.length <= n) return s;
  const cut = s.slice(0, n);
  return cut.slice(0, Math.max(cut.lastIndexOf(" "), n - 25)).replace(/[,;:.\s]+$/, "") + "…";
}
// число по-русски: 1234.5 → «1 234,5» (NBSP-тысячи, запятая-десятичная)
function fmtN(v, digits) {
  if (v == null || isNaN(v)) return null;
  const d = digits != null ? digits : (Math.abs(v) >= 100 ? 0 : Math.abs(v) >= 10 ? 1 : 2);
  const [int, frac] = Math.abs(v).toFixed(d).split(".");
  const grouped = int.replace(/\B(?=(\d{3})+(?!\d))/g, " ");
  return (v < 0 ? "−" : "") + grouped + (frac ? "," + frac : "");
}
function fmtPct(v, digits) { const s = fmtN(v, digits != null ? digits : 2); return s == null ? null : s.replace(/,?0+$/, "").replace(/,$/, "") + "%"; }
function fmtDate(iso) {
  if (!iso) return null;
  const m = String(iso).match(/^(\d{4})-(\d{2})-(\d{2})/);
  return m ? `${m[3]}.${m[2]}.${m[1]}` : null;
}
const CUR_SYM = { SUR: "₽", RUB: "₽", USD: "$", EUR: "€", CNY: "¥", CHF: "₣" };
function curSym(c) { return CUR_SYM[c] || c || "₽"; }
function readSnapshot(name) {
  const p = path.join(_DATA_DIR, `${name}-snapshot.json`);
  try { return JSON.parse(fs.readFileSync(p, "utf8")); } catch { return null; }
}
function writePage(relDir, html) {
  const dir = path.join(_OUT, relDir);
  fs.mkdirSync(dir, { recursive: true });
  fs.writeFileSync(path.join(dir, "index.html"), html, "utf8");
}
function plural(n, one, few, many) {
  const m10 = n % 10, m100 = n % 100;
  if (m10 === 1 && m100 !== 11) return one;
  if (m10 >= 2 && m10 <= 4 && (m100 < 10 || m100 >= 20)) return few;
  return many;
}
// «5,9 года» (дробные — род. падеж ед.ч.), «6 лет», «1 год», «3 года»
function yearsWord(v) { return Number.isInteger(v) ? plural(v, "год", "года", "лет") : "года"; }
// description с гарантированно НЕобрезанным хвостом «Данные на DD.MM.YYYY.»
function descWithDate(core, dataDate, cap) {
  const tail = ` Данные на ${dataDate}.`;
  return truncate(core, (cap || 230) - tail.length) + tail;
}

/* --------------------------- HTML-шаблон --------------------------- */
// Компактный (страниц ~3,9 тыс. — каждый байт ×3900). Палитра — токены Basis
// (бумага/медь), но сами страницы — лёгкая статика без бандла приложения:
// ОБНОВЛЕНО 2026-08-02: роутер под /bonds/, /futures/, /funds/ в приложении
// ПОЯВИЛСЯ (App.js, разбор mInstr), поэтому приложение здесь монтируется —
// человек получает настоящую карточку бумаги, робот по-прежнему статику.

const CSS = `
#seo-boot{position:fixed;inset:0;z-index:99999;background:var(--paper);
  display:flex;flex-direction:column;align-items:center;justify-content:center;gap:18px}
#seo-boot .b-mark{font:700 26px/1 Fraunces,Georgia,'Times New Roman',serif;color:var(--copper);letter-spacing:.02em}
#seo-boot .b-cap{font:400 13px/1.5 Inter,-apple-system,'Segoe UI',Roboto,sans-serif;color:var(--faint)}
#seo-boot .b-bar{width:180px;height:3px;border-radius:2px;background:var(--line);overflow:hidden}
#seo-boot .b-bar i{display:block;width:40%;height:100%;background:var(--copper)}
@media (prefers-reduced-motion:no-preference){#seo-boot .b-bar i{animation:bootSlide 1.1s ease-in-out infinite}}
@keyframes bootSlide{0%{transform:translateX(-100%)}100%{transform:translateX(350%)}}
@media (prefers-color-scheme:dark){#seo-boot{background:#14110E}#seo-boot .b-cap{color:#8A8072}}

:root{--paper:#F7F5F0;--ink:#1F1B16;--muted:#5A5248;--faint:#8A8072;--copper:#C97A4A;--line:#E4DFD5}
*{box-sizing:border-box}
/* 🔴 Ограничения ширины — на КОНТЕЙНЕР статики, а не на body. Владелец ловит это
   ВТОРОЙ раз («открывается на полэкрана»): первый — 2026-07-30 на страницах компаний,
   теперь здесь. Причина одна: когда поверх статики монтируется приложение, оно
   наследует зажатую ширину body — интерфейс платформы ужимается в узкую колонку, справа
   пустота. Статику мы убираем из DOM, а стиль body остаётся жить.
   Скрипт монтирования сбрасывает background/color/font, но НЕ ширину и отступы —
   поэтому они не должны попадать на body вовсе. */
body{font-family:Inter,-apple-system,'Segoe UI',Roboto,sans-serif;background:var(--paper);color:var(--ink);line-height:1.5}
#seo-static{max-width:860px;margin:0 auto;padding:28px 20px 56px}
h1{font-family:Fraunces,Georgia,'Times New Roman',serif;font-size:26px;line-height:1.25;margin:8px 0 4px}
h2{font-family:Fraunces,Georgia,serif;font-size:20px;margin:26px 0 8px}
h3{font-family:Fraunces,Georgia,serif;font-size:16px;margin:18px 0 6px}
p{margin:9px 0}
a{color:var(--copper)}
.crumbs{font-size:13px;color:var(--faint)} .crumbs a{color:var(--faint)}
.sub{color:var(--muted);font-size:14px;margin:0 0 12px}
table{width:100%;border-collapse:collapse;margin:12px 0;font-size:13.5px}
th,td{text-align:left;padding:6px 6px;border-bottom:1px solid var(--line);vertical-align:top}
th{color:var(--muted);font-weight:600}
td.num,th.num{text-align:right;font-variant-numeric:tabular-nums;white-space:nowrap}
.cta{display:inline-block;margin:16px 0 4px;padding:10px 20px;background:var(--copper);color:#fff;text-decoration:none;border-radius:10px;font-size:14px;font-weight:600}
.grid{display:flex;flex-wrap:wrap;gap:8px;margin:10px 0}
.chip{display:inline-block;padding:6px 13px;border:1px solid var(--line);border-radius:999px;background:#fff;color:var(--ink);text-decoration:none;font-size:13px}
.chip:hover{border-color:var(--copper)}
.note{font-size:12.5px;color:var(--faint);margin-top:24px;border-top:1px solid var(--line);padding-top:12px}
.tag{font-size:11.5px;color:var(--faint);text-transform:uppercase;letter-spacing:.06em}
.pill{display:inline-block;padding:5px 12px;border-radius:999px;font-size:13px;font-weight:600;color:#fff;margin:6px 0}
.lt-green{background:#3E7D4F}.lt-amber{background:#A8761F}.lt-orange{background:#B25B2A}.lt-red{background:#9C3B33}.lt-gray{background:#7A7264}
.box{border:1px solid var(--line);background:#fff;border-radius:12px;padding:12px 16px;margin:12px 0}
.wrap{overflow-x:auto}
ul{padding-left:22px}
`.trim();

// 🔴 Страницы, которым нечего сказать. У 661 выпуска нет ни рыночной доходности, ни
// рейтинга: заголовок обещает «доходность, купон, риск», а на странице — «оценить
// «риск за доходность» по рынку нельзя». Яндекс уже пометил одну такую (СберИОС748,
// RU000A10C667) статусом BAD_QUALITY в выгрузке от 29.07.2026.
//
// Такие страницы не просто бесполезны — они тянут вниз оценку ВСЕГО хоста: поиск
// смотрит на долю качественных страниц сайта. Поэтому они остаются доступными людям
// (прямая ссылка работает, во внутренней навигации есть), но помечаются noindex и не
// попадают в карту сайта. Признак пересчитывается на каждой сборке: как только у бумаги
// появятся котировки и доходность, страница вернётся в индекс сама.
function bondIsThin(b) {
  return b && b.vkind === "nodata" && !b.agency_rating;
}


// 🔴 ПРИЛОЖЕНИЕ НА СТРАНИЦАХ ИНСТРУМЕНТОВ. Владелец 2026-08-02: «вбил si 9 26 — открылась
// SEO-страница, а должна подгружаться настоящая». Так и было: этот генератор собирал
// ЧИСТУЮ статику без бандла — 3757 страниц облигаций, фондов и фьючерсов вели себя иначе,
// чем все остальные 5000. Причина в том, что генераторов два, и общий каркас с
// монтированием приложения жил только в generate-seo-pages.js.
//
// Робот по-прежнему получает полноценный текст (он не исполняет скрипты), человек —
// экран загрузки и через мгновение настоящую карточку бумаги.
function loadAppAssets() {
  try {
    const m = JSON.parse(fs.readFileSync(path.join(_OUT, "asset-manifest.json"), "utf8"));
    const js = m && m.files && m.files["main.js"];
    return js ? { js, css: m.files["main.css"] || null } : null;
  } catch (e) {
    // 🔴 НЕ МОЛЧА. Первая версия писала `path.join(BUILD, …)` — в этом файле каталог
    // сборки называется _OUT, и ReferenceError ушёл в пустой catch. Результат: экран
    // загрузки на страницах появился, а бандл — нет, то есть «Открываем разбор…» висел
    // бы 12 секунд и гас. Тихий catch превратил опечатку в поведение, которое заметил бы
    // только пользователь.
    console.log(`  ⚠️  бандл приложения не подключён: ${e.message}`);
    return null;
  }
}

function appMountHtml(assets) {
  if (!assets || !assets.js) return "";
  const css = assets.css ? `<link rel="stylesheet" href="${assets.css}">` : "";
  return `
<div id="root"></div>
<script>
(function () {
  var b = document.createElement("div");
  b.id = "seo-boot";
  b.innerHTML = '<div class="b-mark">Basis</div>'
    + '<div class="b-bar"><i></i></div>'
    + '<div class="b-cap">Открываем разбор…</div>';
  document.body.appendChild(b);
  // Страховка: если приложение не стартовало за 12 с, убираем экран — статика
  // полноценная, лучше показать её, чем бесконечную загрузку.
  setTimeout(function () { var x = document.getElementById("seo-boot"); if (x) x.remove(); }, 12000);
})();
["basis:company-ready", "basis:app-ready"].forEach(function (evt) {
window.addEventListener(evt, function () {
  var el = document.getElementById("seo-static");
  if (el) el.remove();
  var ld = document.getElementById("seo-boot");
  if (ld) ld.remove();
  document.body.style.background = "";
  document.body.style.color = "";
  document.body.style.font = "";
  document.documentElement.classList.add("basis-app-mounted");
});
});
</script>
${css}
<script defer src="${assets.js}"></script>`;
}

function pageShell({ title, desc, canonicalPath, breadcrumbs, bodyHtml, jsonLd, dataDate, noindex }) {
  const url = _SITE + canonicalPath;
  const crumbsHtml = breadcrumbs
    .map((b, i) => (i < breadcrumbs.length - 1 && b.href ? `<a href="${b.href}">${escapeHtml(b.label)}</a>` : escapeHtml(b.label)))
    .join(" → ");
  const ld = {
    "@context": "https://schema.org",
    "@graph": [
      {
        "@type": "BreadcrumbList",
        itemListElement: breadcrumbs.map((b, i) => ({
          "@type": "ListItem", position: i + 1, name: b.label,
          ...(b.href ? { item: _SITE + b.href } : {}),
        })),
      },
      ...(jsonLd || []),
    ],
  };
  return `<!doctype html>
<html lang="ru">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>${escapeHtml(title)}</title>
<meta name="description" content="${escapeHtml(desc)}">
<link rel="canonical" href="${url}">
<meta name="robots" content="${noindex ? "noindex, follow" : "index, follow"}">
<meta property="og:type" content="article">
<meta property="og:site_name" content="Basis">
<meta property="og:title" content="${escapeHtml(title)}">
<meta property="og:description" content="${escapeHtml(desc)}">
<meta property="og:url" content="${url}">
<meta property="og:image" content="${_SITE}/og-banner.png">
<meta property="og:locale" content="ru_RU">
<meta name="twitter:card" content="summary_large_image">
<link rel="icon" type="image/svg+xml" href="/favicon.svg">
<link rel="apple-touch-icon" sizes="180x180" href="/apple-touch-icon.png">
<script type="application/ld+json">${JSON.stringify(ld)}</script>
<style>${CSS}</style>
${metrikaSnippet()}
</head>
<body>
<div id="seo-static">
<nav class="crumbs">${crumbsHtml}</nav>
${bodyHtml}
<p class="note">Basis — аналитический слой, не брокер: без сигналов
«купить/продать». Числа на странице — данные Московской биржи и расчёты Basis на
${dataDate}; актуальные котировки и полный разбор — в приложении. «Оценка Basis» —
оценка соотношения доходности и риска по открытой методике, а не рейтинг и не совет.
Материал не является индивидуальной инвестиционной рекомендацией.</p>
</div>${appMountHtml(loadAppAssets())}
</body>
</html>`;
}

function finProductLd(name, canonicalPath, category, isin) {
  return [{
    "@type": "FinancialProduct",
    name,
    category,
    ...(isin ? { identifier: isin } : {}),
    url: _SITE + canonicalPath,
    provider: { "@type": "Organization", name: "Московская биржа" },
  }];
}

function kvTable(rows) {
  const body = rows
    .filter(([, v]) => v != null && v !== "")
    .map(([k, v]) => `<tr><th>${escapeHtml(k)}</th><td>${v}</td></tr>`).join("");
  return body ? `<table><tbody>${body}</tbody></table>` : "";
}

/* ============================ ОБЛИГАЦИИ ============================ */

const BOND_TYPE_LABEL = { ofz: "ОФЗ (госдолг РФ)", corporate: "Корпоративная", muni: "Муниципальная", other: "Прочее" };
const RUB_CUR = new Set(["SUR", "RUB"]);

// светофор «доходность vs риск» → короткая подпись (тот же смысл, что пилюля в
// скринере приложения; движок bond_risk.py, поля light/vkind/premium из снапшота)
function lightLabel(b) {
  const k = b.vkind, lt = b.light;
  if (k === "ofz") return "госдолг: кредитный риск минимальный";
  if (k === "defaulted") return "дефолт — доходность нерелевантна";
  if (k === "near_offer") return "доходность искажена близкой офертой/погашением";
  if (k === "floater") {
    return { green: "флоатер: кредитный риск умеренный", amber: "флоатер: кредитный риск средний",
      orange: "флоатер: повышенный кредитный риск", red: "флоатер: высокий кредитный риск" }[lt] || "флоатер";
  }
  if (k === "structured") return "структурная/индексируемая: стандартная оценка неприменима";
  if (k === "nodata") return "без рыночной спред-оценки";
  if (lt === "green") return b.premium_bp != null && b.premium_bp > 200 ? "риск оплачен с запасом" : "риск оплачен";
  if (lt === "amber") return "доходность соответствует риску";
  if (lt === "orange") return "риск недоплачен";
  if (lt === "red") return b.premium_bp != null && b.premium_bp < -200 ? "риск существенно недоплачен" : "дистресс / стоп-фактор";
  return null;
}
function lightClass(b) { return `lt-${b.light || "gray"}`; }

function couponPeriodLabel(days) {
  if (days == null) return null;
  if (days >= 28 && days <= 31) return `${days} дн. (ежемесячный)`;
  if (days >= 84 && days <= 98) return `${days} дн. (квартальный)`;
  if (days >= 175 && days <= 190) return `${days} дн. (полугодовой)`;
  if (days >= 350 && days <= 380) return `${days} дн. (годовой)`;
  return `${days} дн.`;
}

function bondTitle(b) { return `${b.short_name}: доходность, купон, риск — анализ облигации | Basis`; }

function bondDesc(b, dataDate) {
  const bits = [];
  // у флоатера YTM условна (купон плавает со ставкой) — в description её не выносим
  if (b.ytm != null && !b.yield_anomaly && b.coupon_type !== "floater") bits.push(`доходность ${b.ytm_kind || "к погашению"} ${fmtPct(b.ytm)}`);
  if (b.coupon_formula) bits.push(`купон ${b.coupon_formula}`);
  if (b.maturity_date) bits.push(`погашение ${fmtDate(b.maturity_date)}`);
  const lab = lightLabel(b);
  const verdict = lab ? ` Оценка Basis: ${lab}.` : "";
  return descWithDate(`Облигация ${b.short_name} (${b.isin}): ${bits.join(", ") || "параметры выпуска и рыночные данные"}.${verdict}`, dataDate);
}

// Блок «Оценка Basis» — главный SEO-актив страницы: текстовый вердикт из
// расчётных полей (светофор + risk_verdict + премия + Risk Score + рейтинги).
function basisBlock(b) {
  const parts = [];
  const lab = lightLabel(b);
  if (lab) parts.push(`<span class="pill ${lightClass(b)}">${escapeHtml(lab.charAt(0).toUpperCase() + lab.slice(1))}</span>`);
  if (b.risk_verdict) parts.push(`<p>${escapeHtml(strip(b.risk_verdict))}</p>`);
  const detail = [];
  if (b.premium_bp != null && b.required_bp != null && b.spread_bp != null) {
    detail.push(`Спред к ОФЗ ${fmtN(b.spread_bp, 0)} б.п. при требуемых по методике ~${fmtN(b.required_bp, 0)} б.п. — премия ${b.premium_bp >= 0 ? "+" : ""}${fmtN(b.premium_bp, 0)} б.п.`);
  }
  if (b.floater_spread_bp != null) detail.push(`Надбавка купона к ключевой ставке ≈ ${b.floater_spread_bp >= 0 ? "+" : ""}${fmtN(b.floater_spread_bp, 0)} б.п.`);
  if (b.basis_score != null && b.basis_group) detail.push(`Risk Score Basis: ${fmtN(b.basis_score, 1)} из 5 (группа ${escapeHtml(b.basis_group)}).`);
  if (detail.length) parts.push(`<p>${detail.join(" ")}</p>`);
  if (b.agency_rating) {
    const src = b.agency_rating_source ? `, ${escapeHtml(strip(b.agency_rating_source))}` : "";
    const mean = b.agency_rating_meaning ? ` ${escapeHtml(strip(b.agency_rating_meaning))}` : "";
    parts.push(`<p>Агентский рейтинг: <b>${escapeHtml(b.agency_rating)}</b> (нац. шкала${src}).${mean}</p>`);
  } else if (b.bond_type !== "ofz") {
    parts.push(`<p>Рейтинга кредитных агентств в базе Basis нет — методика добавляет за это премию к требуемому спреду.</p>`);
  }
  if (b.arbitrage_note) parts.push(`<p>${escapeHtml(strip(b.arbitrage_note))}</p>`);
  if (!parts.length) return "";
  return `<div class="box"><p class="tag">Оценка Basis: доходность vs риск · оценка, не рекомендация</p>${parts.join("\n")}</div>`;
}

function bondPage(b, ctx, noindex) {
  const { dataDate, collectionsOf, neighborsOf } = ctx;
  const typeLabel = BOND_TYPE_LABEL[b.bond_type] || "Облигация";
  // issuer_name в данных — ПОЛНОЕ ИМЯ ВЫПУСКА (часто с эмитентом внутри), не
  // чистое имя эмитента — подписываем честно
  const issuerCell = b.bond_type === "ofz"
    ? "Минфин России (госдолг РФ)"
    : companyExists(b.issuer_ticker)
      ? `${escapeHtml(strip(b.issuer_name || b.issuer_ticker))} — <a href="/company/${escapeHtml(b.issuer_ticker)}/">разбор эмитента ${escapeHtml(b.issuer_ticker)} на Basis</a>`
      : escapeHtml(strip(b.issuer_name || "") || null);
  const params = kvTable([
    ["ISIN", escapeHtml(b.isin || "—")],
    ["Выпуск / эмитент", issuerCell],
    ["Тип", escapeHtml(typeLabel)],
    ["Валюта номинала", escapeHtml(RUB_CUR.has(b.currency) ? "рубль" : b.currency || "—")],
    ["Номинал", b.face_value != null ? `${fmtN(b.face_value)} ${curSym(b.currency)}` : null],
    ["Купон", b.coupon_formula ? `${escapeHtml(b.coupon_formula)} — ${escapeHtml(b.coupon_label || "")}` : escapeHtml(b.coupon_label || null)],
    ["Периодичность купона", escapeHtml(couponPeriodLabel(b.coupon_period))],
    ["Погашение", escapeHtml(fmtDate(b.maturity_date))],
    ["Ближайшая оферта", escapeHtml(fmtDate(b.offer_date))],
    ["Амортизация номинала", b.has_amortization ? "да (номинал гасится частями)" : "нет"],
    ["Уровень листинга MOEX", b.listing_level != null ? String(b.listing_level) : null],
  ]);
  const floaterNote = b.coupon_type === "floater" ? " — для флоатера ориентир условен: купон меняется вслед за ставкой" :
    b.coupon_type === "linker" ? " — реальная (сверх инфляции): номинал линкера индексируется на ИПЦ" : "";
  const market = kvTable([
    ["Цена", b.last_price != null ? `${fmtN(b.last_price)}% номинала` : null],
    [`Доходность ${b.ytm_kind || "к погашению"}`, b.ytm != null
      ? `${fmtPct(b.ytm)} годовых${b.yield_anomaly ? " — аномально высокая: маркер дистресса/неликвида, не «выгоды»" : ""}${b.near_offer ? " — искажена близкой офертой/погашением" : ""}${floaterNote}`
      : "нет данных (не торгуется / неликвид / не рассчитывается)"],
    ["Дюрация", b.duration_years != null ? `${fmtN(b.duration_years, 1)} ${yearsWord(b.duration_years)}` : null],
    ["НКД", b.accrued_int != null ? `${fmtN(b.accrued_int)} ${curSym(b.currency)}` : null],
    ["Статус", b.is_defaulted ? "дефолт / режим Д" : null],
  ]);
  const chips = (collectionsOf(b) || []).map((c) =>
    `<a class="chip" href="/bonds/${c.slug}/">${escapeHtml(c.chip)}</a>`).join("");
  const nbs = neighborsOf(b).map((n) =>
    `<a class="chip" href="/bonds/${encodeURIComponent(n.secid)}/">${escapeHtml(n.short_name)}</a>`).join("");
  const body = `
<p class="tag">${escapeHtml(b.sector || typeLabel)} · MOEX: ${escapeHtml(b.secid)}</p>
<h1>${escapeHtml(b.short_name)}</h1>
<p class="sub">${escapeHtml(strip(b.issuer_name || ""))}${b.issuer_name ? " · " : ""}ISIN ${escapeHtml(b.isin || "—")}</p>
${basisBlock(b)}
<h2>Параметры выпуска</h2>
<p class="tag">Факт — данные Московской биржи</p>
${params}
<h2>Рыночные данные на ${dataDate}</h2>
${market}
<a class="cta" href="/">Открыть в приложении Basis: скринер и карточка облигации →</a>
${chips ? `<h2>Подборки с этой бумагой</h2><div class="grid">${chips}</div>` : ""}
${nbs ? `<h2>Похожие выпуски</h2><div class="grid">${nbs}</div>` : ""}
<p><a href="/bonds/">← Все облигации: каталог и подборки Basis</a></p>`;
  return pageShell({
    noindex,
    title: bondTitle(b),
    desc: bondDesc(b, dataDate),
    canonicalPath: `/bonds/${b.secid}/`,
    breadcrumbs: [
      { label: "Basis", href: "/" },
      { label: "Облигации", href: "/bonds/" },
      { label: b.short_name },
    ],
    bodyHtml: body,
    jsonLd: finProductLd(b.short_name, `/bonds/${b.secid}/`, "Облигация", b.isin),
    dataDate,
  });
}

/* ------------------------- подборки облигаций ------------------------- */

function yearsTo(iso, fromDate) {
  if (!iso) return null;
  const d = (new Date(iso) - fromDate) / 864e5;
  return d / 365.25;
}
function median(arr) {
  if (!arr.length) return null;
  const s = [...arr].sort((a, b) => a - b);
  const m = Math.floor(s.length / 2);
  return s.length % 2 ? s[m] : (s[m - 1] + s[m]) / 2;
}

// общая таблица подборки: Бумага | Купон | YTM | Погашение | Рейтинг | Оценка Basis
function bondsTable(rows, opts) {
  const o = opts || {};
  const head = `<tr><th>Бумага</th><th>Купон</th><th class="num">${o.ytmHead || "Доходность"}</th><th class="num">Погашение</th><th>Рейтинг</th><th>Оценка Basis</th></tr>`;
  const body = rows.map((b) => {
    const lab = lightLabel(b) || "—";
    const ytm = o.ytmCell ? o.ytmCell(b) : (b.ytm != null ? fmtPct(b.ytm) : "—");
    return `<tr><td><a href="/bonds/${encodeURIComponent(b.secid)}/">${escapeHtml(b.short_name)}</a>${!RUB_CUR.has(b.currency) && !o.noCur ? ` <span class="tag">${escapeHtml(b.currency)}</span>` : ""}</td>` +
      `<td>${escapeHtml(b.coupon_formula || b.coupon_label || "—")}</td>` +
      `<td class="num">${ytm || "—"}</td>` +
      `<td class="num">${fmtDate(b.maturity_date) || "—"}</td>` +
      `<td>${escapeHtml(b.agency_rating || "—")}</td>` +
      `<td>${escapeHtml(lab)}</td></tr>`;
  }).join("");
  return `<div class="wrap"><table><thead>${head}</thead><tbody>${body}</tbody></table></div>`;
}

function collectionPage(col, rows, total, ctx, extraHtml) {
  const { dataDate } = ctx;
  const others = ctx.collections.filter((c) => c.slug !== col.slug)
    .map((c) => `<a class="chip" href="/bonds/${c.slug}/">${escapeHtml(c.chip)}</a>`).join("");
  const shown = Math.min(rows.length, col.top || rows.length);
  const body = `
<p class="tag">Подборка Basis · облигации Московской биржи · данные на ${dataDate}</p>
<h1>${escapeHtml(col.h1)}</h1>
<p class="sub">Всего в базе Basis: ${total} ${plural(total, "бумага", "бумаги", "бумаг")}${shown < total ? `; в таблице — ${shown} (${escapeHtml(col.sortNote)})` : ""}.</p>
${col.intro}
${extraHtml || ""}
<h2>${escapeHtml(col.tableTitle || "Список выпусков")}</h2>
${bondsTable(rows.slice(0, col.top || rows.length), col.tableOpts)}
<a class="cta" href="/">Полный список, фильтры и живые котировки — в скринере облигаций Basis →</a>
<h2>Другие подборки</h2>
<div class="grid">${others}<a class="chip" href="/bonds/">Каталог облигаций</a></div>`;
  return pageShell({
    title: col.title,
    desc: col.desc(total, dataDate),
    canonicalPath: `/bonds/${col.slug}/`,
    breadcrumbs: [
      { label: "Basis", href: "/" },
      { label: "Облигации", href: "/bonds/" },
      { label: col.crumb },
    ],
    bodyHtml: body,
    jsonLd: [],
    dataDate,
  });
}

/* ============================== ФОНДЫ ============================== */

const FUND_TYPE_BLURB = {
  equity: "Фонд акций: корзина акций в одной бумаге. Главные вопросы — какой индекс/набор внутри и сколько съедает комиссия.",
  bonds: "Фонд облигаций: диверсифицированный долговой портфель без выбора отдельных выпусков. Комиссия напрямую уменьшает и без того ограниченную доходность.",
  gold: "Фонд на золото: биржевой доступ к металлу без слитков и обезличенных счетов. Следит за ценой золота; комиссия — постоянное отставание от металла.",
  money_market: "Фонд денежного рынка: «парковка» рублей под ставку, близкую к ключевой (RUSFAR). Низкий риск, но комиссия вычитается из ставки каждый день.",
  currency: "Валютный фонд: экспозиция на валюту через биржевой инструмент.",
  mixed: "Смешанный фонд: акции и облигации в одной упаковке по выбору УК — состав и пропорции задаёт управляющая компания.",
};

function terMoney(ter) {
  if (ter == null) return null;
  const out = [];
  for (const years of [1, 5, 10]) {
    const frac = 1 - Math.pow(1 - ter / 100, years);
    out.push(`за ${years} ${plural(years, "год", "года", "лет")} ≈ ${fmtN(Math.round(100000 * frac))} ₽`);
  }
  return out.join(", ");
}

function fundPage(f, all, ctx) {
  const { dataDate } = ctx;
  // sec_name — человеческое имя («БПИФ Первая Облигации флоатеры»), short_name —
  // биржевое («SBFR ETF»); в title/h1 идёт человеческое: его и ищут
  const name = strip(f.sec_name || f.short_name);
  const terBlock = f.ter != null
    ? `<div class="box"><p class="tag">Комиссия фонда (TER) · факт из документов УК</p>
<p>Совокупные расходы — <b>${fmtPct(f.ter)} годовых</b>. На 100 000 ₽ вложений это ${terMoney(f.ter)}
(оценка без учёта роста котировок — иллюстрация «тихой» стоимости владения).</p></div>`
    : `<div class="box"><p class="tag">Комиссия фонда (TER)</p>
<p>Комиссия этого фонда в данных Basis пока не заполнена — уточняйте в правилах доверительного
управления на сайте УК. Для фондов комиссия — ключевой параметр: она вычитается из результата каждый год.</p></div>`;
  const params = kvTable([
    ["ISIN", escapeHtml(f.isin || "—")],
    ["Тип фонда", escapeHtml(f.type_label || f.fund_type || "—")],
    ["Бенчмарк / базовый актив", escapeHtml(strip(f.benchmark || "") || null)],
    ["Валюта торгов", escapeHtml(RUB_CUR.has(f.currency) ? "рубль" : f.currency || "—")],
    ["Уровень листинга MOEX", f.listing_level != null ? String(f.listing_level) : null],
  ]);
  const market = kvTable([
    ["Цена пая", f.last_price != null ? `${fmtN(f.last_price)} ${curSym(f.currency)}` : null],
    ["Оборот за день", f.val_today != null ? `${fmtN(Math.round(f.val_today / 1e6), f.val_today >= 1e7 ? 0 : 1)} млн ₽` : null],
    ["Сделок за день", f.num_trades != null ? fmtN(f.num_trades, 0) : null],
  ]);
  const peers = all.filter((x) => x.fund_type === f.fund_type && x.secid !== f.secid).slice(0, 8)
    .map((p) => `<a class="chip" href="/funds/${encodeURIComponent(p.secid)}/">${escapeHtml(p.short_name)}</a>`).join("");
  const blurb = FUND_TYPE_BLURB[f.fund_type];
  const body = `
<p class="tag">${escapeHtml(f.type_label || "Фонд")} · БПИФ/ETF · MOEX: ${escapeHtml(f.secid)}</p>
<h1>${escapeHtml(name)} <span style="color:var(--faint)">(${escapeHtml(f.secid)})</span></h1>
${name !== strip(f.short_name) ? `<p class="sub">${escapeHtml(strip(f.short_name))}</p>` : ""}
${blurb ? `<p>${escapeHtml(blurb)}</p>` : ""}
${terBlock}
<h2>Паспорт фонда</h2>
${params}
<h2>Торги на ${dataDate}</h2>
<p class="tag">Факт — данные Московской биржи; ликвидность важна не меньше комиссии</p>
${market}
<a class="cta" href="/">Открыть в приложении Basis: раздел «Рынок» → Фонды →</a>
${peers ? `<h2>Другие фонды этого типа</h2><div class="grid">${peers}</div>` : ""}
<p><a href="/funds/">← Все биржевые фонды: каталог Basis</a></p>`;
  const descBits = [];
  if (f.ter != null) descBits.push(`комиссия TER ${fmtPct(f.ter)} годовых`);
  if (f.benchmark) descBits.push(`бенчмарк: ${strip(f.benchmark)}`);
  if (f.last_price != null) descBits.push(`цена пая ${fmtN(f.last_price)} ${curSym(f.currency)}`);
  return pageShell({
    title: `${truncate(name, 45)} (${f.secid}): комиссия, тип, ликвидность — фонд | Basis`,
    desc: descWithDate(`Биржевой фонд ${name} (${f.secid})${f.type_label ? `, тип «${f.type_label.toLowerCase()}»` : ""}${descBits.length ? ": " + descBits.join(", ") : ""}. Что внутри и сколько стоит владение — разбор Basis.`, dataDate),
    canonicalPath: `/funds/${f.secid}/`,
    breadcrumbs: [
      { label: "Basis", href: "/" },
      { label: "Фонды", href: "/funds/" },
      { label: f.short_name },
    ],
    bodyHtml: body,
    jsonLd: finProductLd(f.short_name, `/funds/${f.secid}/`, "Биржевой фонд (БПИФ/ETF)", f.isin),
    dataDate,
  });
}

function fundsIndex(funds, ctx) {
  const { dataDate } = ctx;
  const byType = {};
  for (const f of funds) (byType[f.type_label || "Прочие"] = byType[f.type_label || "Прочие"] || []).push(f);
  const sections = Object.keys(byType).sort((a, b) => byType[b].length - byType[a].length).map((t) => {
    const rows = byType[t]
      .sort((a, b) => (b.val_today || 0) - (a.val_today || 0))
      .map((f) => `<tr><td><a href="/funds/${encodeURIComponent(f.secid)}/">${escapeHtml(f.secid)}</a></td>` +
        `<td>${escapeHtml(truncate(strip(f.sec_name || f.short_name), 60))}</td>` +
        `<td class="num">${f.ter != null ? fmtPct(f.ter) : "—"}</td>` +
        `<td class="num">${f.val_today != null ? fmtN(Math.round(f.val_today / 1e6), 0) : "—"}</td></tr>`).join("");
    return `<h2>${escapeHtml(t)} <span style="color:var(--faint);font-size:14px">· ${byType[t].length}</span></h2>
<div class="wrap"><table><thead><tr><th>Тикер</th><th>Фонд</th><th class="num">TER</th><th class="num">Оборот, млн ₽</th></tr></thead><tbody>${rows}</tbody></table></div>`;
  }).join("\n");
  const body = `
<h1>Биржевые фонды Мосбиржи: комиссии и ликвидность</h1>
<p class="sub">${funds.length} ${plural(funds.length, "фонд", "фонда", "фондов")} (БПИФ/ETF) по типам. Фонд — упаковка чужих активов:
главные вопросы — что внутри, сколько съедает комиссия (TER) и хватает ли ликвидности. «—» в колонке TER — комиссия в данных Basis не заполнена.</p>
${sections}
<a class="cta" href="/">Открыть приложение Basis: раздел «Рынок» → Фонды →</a>`;
  return pageShell({
    title: `Биржевые фонды (БПИФ/ETF) на Мосбирже: комиссии TER, типы, ликвидность | Basis`,
    desc: `Каталог ${funds.length} биржевых фондов Московской биржи: акции, облигации, золото, денежный рынок. Комиссии TER, бенчмарки, обороты — разбор Basis. Данные на ${dataDate}.`,
    canonicalPath: "/funds/",
    breadcrumbs: [{ label: "Basis", href: "/" }, { label: "Фонды" }],
    bodyHtml: body,
    jsonLd: [],
    dataDate,
  });
}

/* ============================= ФЬЮЧЕРСЫ ============================= */

// 🔴 РАЗЛИЧАЕМ БЛИЗНЕЦОВ. Владелец 2026-08-02: по запросу «si 9 26» находится Si-9.27,
// а не Si-9.26. Причина не в ошибке, а в устройстве: 479 страниц фьючерсов отличаются
// друг от друга кодом, датой и двумя числами — 240 слов почти идентичного шаблона.
// Поисковику приходится выбирать между близнецами, и он ошибается серией.
//
// Лечим тем, что делает страницу узнаваемой ИМЕННО для своего контракта:
//   • месяц исполнения СЛОВАМИ («сентябрь 2026») — «26» и «27» в коде отличаются одним
//     символом, а «сентябрь 2026» и «сентябрь 2027» различаются целым словом;
//   • альтернативные написания кода — люди набирают «si 9.26», «si926», «siu6», и в
//     тексте страницы этих вариантов не было вовсе;
//   • пометка ближайшего контракта серии: чаще всего ищут именно его.
// Две формы месяца: «исполнение — сентябрь 2026» (именительный) и «исполняется в
// сентябре 2026» (предложный). С одним списком выходило «исполнение сентября 2026»
// и «в сентября 2026» — на витрине это выглядит как машинный перевод.
const _MONTHS_NOM = ["январь","февраль","март","апрель","май","июнь",
                     "июль","август","сентябрь","октябрь","ноябрь","декабрь"];
const _MONTHS_PREP = ["январе","феврале","марте","апреле","мае","июне",
                      "июле","августе","сентябре","октябре","ноябре","декабре"];

function expiryWords(iso, form = "nom") {
  if (!iso) return null;
  const d = new Date(iso);
  if (isNaN(d)) return null;
  const m = form === "prep" ? _MONTHS_PREP[d.getMonth()] : _MONTHS_NOM[d.getMonth()];
  return `${m} ${d.getFullYear()}`;
}

/** Варианты написания кода контракта, как их набирают в поиске. */
function codeAliases(f) {
  const short = String(f.short_name || "");      // Si-9.26
  const m = short.match(/^([A-Za-z]+)-(\d{1,2})\.(\d{2})$/);
  if (!m) return [];
  const [, base, mm, yy] = m;
  return [...new Set([
    `${base}-${mm}.${yy}`, `${base} ${mm}.${yy}`, `${base}${mm}${yy}`,
    `${base} ${mm} ${yy}`, String(f.secid || ""),
  ])].filter(Boolean);
}

function futurePage(f, all, ctx) {
  const { dataDate } = ctx;
  const asset = strip(f.asset_name || f.asset_code);
  const params = kvTable([
    ["Базовый актив", `${escapeHtml(asset)}${f.kind_label ? ` (${escapeHtml(f.kind_label.toLowerCase())})` : ""}` +
      (companyExists(f.linked_ticker) ? ` — <a href="/company/${escapeHtml(f.linked_ticker)}/">разбор компании ${escapeHtml(f.linked_ticker)} на Basis</a>` : "")],
    ["Экспирация (последний торговый день)", f.expiration_date ? `${fmtDate(f.expiration_date)}${f.days_to_expiry != null ? ` (через ${fmtN(f.days_to_expiry, 0)} дн. на дату данных)` : ""}` : null],
    ["Единиц базового актива в контракте", f.lot_volume != null ? fmtN(f.lot_volume, 0) : null],
    ["Шаг цены / стоимость шага", f.min_step != null ? `${fmtN(f.min_step)} / ${f.step_price != null ? fmtN(f.step_price) + " ₽" : "—"}` : null],
  ]);
  const market = kvTable([
    ["Расчётная цена (клиринг)", f.settle_price != null ? fmtN(f.settle_price) : null],
    ["Последняя цена", f.last_price != null ? fmtN(f.last_price) : null],
    ["Гарантийное обеспечение (ГО)", f.initial_margin != null ? `${fmtN(Math.round(f.initial_margin), 0)} ₽` : null],
    ["Номинал контракта", f.contract_value != null ? `${fmtN(Math.round(f.contract_value), 0)} ₽` : null],
    ["Эффективное плечо", f.leverage != null ? `≈ ${fmtN(f.leverage, 1)}×` : null],
    ["Открытые позиции", f.open_position != null ? fmtN(f.open_position, 0) : null],
  ]);
  const lev = f.leverage;
  const riskBlock = lev != null ? `<div class="box"><p class="tag">Риск плеча · оценка</p>
<p>Плечо ≈ ${fmtN(lev, 1)}×: движение базового актива против позиции на 1% меняет счёт примерно на
−${fmtN(lev, 1)}% от ГО, на 5% — примерно на −${fmtN(lev * 5, 0)}% от ГО. Фьючерс — инструмент с
встроенным плечом: потери могут превысить внесённое обеспечение.</p></div>` : "";
  const series = all.filter((x) => x.asset_code === f.asset_code && x.secid !== f.secid)
    .sort((a, b) => String(a.expiration_date || "9").localeCompare(String(b.expiration_date || "9")))
    .slice(0, 8)
    .map((s) => `<a class="chip" href="/futures/${encodeURIComponent(s.secid)}/">${escapeHtml(s.short_name)}${s.expiration_date ? ` · ${fmtDate(s.expiration_date)}` : ""}</a>`).join("");
  const body = `
<p class="tag">${escapeHtml(f.kind_label || "Фьючерс")} · срочный рынок FORTS · MOEX: ${escapeHtml(f.secid)}</p>
<h1>${escapeHtml(f.short_name)} — фьючерс на ${escapeHtml(asset)}${
    expiryWords(f.expiration_date) ? `, исполнение ${expiryWords(f.expiration_date)}` : ""}</h1>
${f.sec_name && strip(f.sec_name) !== f.short_name ? `<p class="sub">${escapeHtml(strip(f.sec_name))}</p>` : ""}
${(() => {
    const al = codeAliases(f).filter((x) => x !== f.short_name);
    const nearest = all.filter((x) => x.asset_code === f.asset_code && x.expiration_date)
      .sort((a, b) => String(a.expiration_date).localeCompare(String(b.expiration_date)))[0];
    const isNearest = nearest && nearest.secid === f.secid;
    const bits = [];
    if (expiryWords(f.expiration_date)) {
      bits.push(`Контракт исполняется в ${expiryWords(f.expiration_date, "prep")}`
        + (f.days_to_expiry != null ? ` — через ${fmtN(f.days_to_expiry, 0)} дн. на дату данных` : "")
        + ".");
    }
    if (isNearest) {
      // Ближайший контракт серии — тот, который чаще всего и ищут: у него основной
      // объём торгов, остальные месяцы неликвидны.
      bits.push(`Это ближайший контракт серии ${escapeHtml(f.asset_code)}: у него, как правило, `
        + `основной объём торгов, дальние месяцы заметно менее ликвидны.`);
    }
    if (al.length) {
      bits.push(`Встречается в записи как ${al.map((x) => escapeHtml(x)).join(", ")}.`);
    }
    return bits.length ? `<p>${bits.join(" ")}</p>` : "";
  })()}
<h2>Параметры контракта</h2>
<p class="tag">Факт — данные Московской биржи</p>
${params}
<h2>Рыночные данные на ${dataDate}</h2>
${market}
${riskBlock}
<a class="cta" href="/">Открыть в приложении Basis: срочная структура, базис, связь с активом →</a>
${series ? `<h2>Другие серии на этот актив</h2><div class="grid">${series}</div>` : ""}
<p><a href="/futures/">← Все фьючерсы: каталог Basis</a></p>`;
  const descBits = [];
  // Месяц СЛОВАМИ в описании: в выдаче именно оно отличает Si-9.26 от Si-9.27, где
  // коды различаются одним символом.
  const expWords = expiryWords(f.expiration_date);
  if (f.expiration_date) {
    descBits.push(`экспирация ${fmtDate(f.expiration_date)}${expWords ? ` (${expWords})` : ""}`);
  }
  if (f.initial_margin != null) descBits.push(`ГО ${fmtN(Math.round(f.initial_margin), 0)} ₽`);
  if (f.leverage != null) descBits.push(`плечо ≈ ${fmtN(f.leverage, 1)}×`);
  return pageShell({
    title: `${f.short_name} (${f.secid}): фьючерс на ${truncate(asset, 34)}`
      + `${expiryWords(f.expiration_date) ? ` — исполнение ${expiryWords(f.expiration_date)}` : ""} | Basis`,
    desc: descWithDate(`Фьючерс ${f.short_name} на ${asset}${descBits.length ? ": " + descBits.join(", ") : ""}. Параметры контракта и риск плеча — разбор Basis.`, dataDate),
    canonicalPath: `/futures/${f.secid}/`,
    breadcrumbs: [
      { label: "Basis", href: "/" },
      { label: "Фьючерсы", href: "/futures/" },
      { label: f.short_name },
    ],
    bodyHtml: body,
    jsonLd: finProductLd(f.short_name, `/futures/${f.secid}/`, "Фьючерсный контракт"),
    dataDate,
  });
}

function futuresIndex(futs, ctx) {
  const { dataDate } = ctx;
  const byKind = {};
  for (const f of futs) (byKind[f.kind_label || "Другие"] = byKind[f.kind_label || "Другие"] || []).push(f);
  const order = ["Валюта", "Индекс", "Сырьё", "На акцию", "Ставка", "Другие"];
  const kinds = Object.keys(byKind).sort((a, b) => (order.indexOf(a) + 99) - (order.indexOf(b) + 99) || byKind[b].length - byKind[a].length);
  const sections = kinds.map((k) => {
    const rows = byKind[k].sort((a, b) => (b.open_position || 0) - (a.open_position || 0))
      .map((f) => `<tr><td><a href="/futures/${encodeURIComponent(f.secid)}/">${escapeHtml(f.short_name)}</a></td>` +
        `<td>${escapeHtml(truncate(strip(f.asset_name || f.asset_code), 44))}</td>` +
        `<td class="num">${fmtDate(f.expiration_date) || "—"}</td>` +
        `<td class="num">${f.leverage != null ? fmtN(f.leverage, 1) + "×" : "—"}</td>` +
        `<td class="num">${f.open_position != null ? fmtN(f.open_position, 0) : "—"}</td></tr>`).join("");
    return `<h2>${escapeHtml(k)} <span style="color:var(--faint);font-size:14px">· ${byKind[k].length}</span></h2>
<div class="wrap"><table><thead><tr><th>Контракт</th><th>Базовый актив</th><th class="num">Экспирация</th><th class="num">Плечо</th><th class="num">Откр. позиции</th></tr></thead><tbody>${rows}</tbody></table></div>`;
  }).join("\n");
  const body = `
<h1>Фьючерсы Мосбиржи: контракты срочного рынка</h1>
<p class="sub">${futs.length} ${plural(futs.length, "живой контракт", "живых контракта", "живых контрактов")} FORTS по типам базового актива
(экспирированные не показываются). Фьючерс — инструмент со встроенным плечом: сначала риск (ГО и плечо), потом всё остальное.</p>
${sections}
<a class="cta" href="/">Открыть приложение Basis: раздел «Рынок» → Фьючерсы →</a>`;
  const nWord = plural(futs.length, "контракт", "контракта", "контрактов");
  return pageShell({
    title: `Фьючерсы на Мосбирже: ГО, плечо и экспирации — ${futs.length} ${nWord} | Basis`,
    desc: `Каталог фьючерсов срочного рынка Московской биржи (${futs.length} ${nWord}): валюта, индексы, сырьё, акции. Гарантийное обеспечение, плечо, даты экспирации — разбор Basis. Данные на ${dataDate}.`,
    canonicalPath: "/futures/",
    breadcrumbs: [{ label: "Basis", href: "/" }, { label: "Фьючерсы" }],
    bodyHtml: body,
    jsonLd: [],
    dataDate,
  });
}

/* ========================= ВАЛЮТА И МЕТАЛЛЫ ========================= */

function spotLanding(rows, ctx) {
  const { dataDate } = ctx;
  const cur = rows.filter((r) => r.kind === "currency");
  const met = rows.filter((r) => r.kind === "metal");
  // курсам — 2 знака (77,97 ₽, а не «78 ₽»), тяжёлым ценам металлов — целые
  const px = (v) => v != null ? fmtN(v, Math.abs(v) < 100 ? 2 : 0) : "—";
  const table = (list) => `<div class="wrap"><table><thead><tr><th>Инструмент</th><th class="num">Цена, ₽</th><th class="num">Изменение за день</th><th class="num">Пред. закрытие</th></tr></thead><tbody>${
    list.map((r) => `<tr><td>${escapeHtml(strip(r.name || r.short_name))} <span class="tag">${escapeHtml(r.secid)}</span></td>` +
      `<td class="num">${px(r.last_price)}</td>` +
      `<td class="num">${r.change_pct != null ? (r.change_pct > 0 ? "▲ +" : r.change_pct < 0 ? "▼ " : "") + fmtPct(r.change_pct) : "—"}</td>` +
      `<td class="num">${px(r.prev_close)}</td></tr>`).join("")
  }</tbody></table></div>`;
  const usd = cur.find((r) => r.base_code === "USD"), gld = met.find((r) => r.base_code === "GLD");
  const body = `
<h1>Валюта и драгметаллы на Мосбирже: курсы спот-рынка</h1>
<p class="sub">Биржевые курсы валют и цены металлов (споты MOEX) на ${dataDate}. У валюты и металла нет
«справедливой цены» как у акции — вопрос в их роли в портфеле.</p>
<h2>Валюты</h2>
${table(cur)}
<p>Курс валюты — это макроэкономика: дифференциал ставок, торговый баланс, потоки капитала.
В портфеле валютная позиция — прежде всего управление рублёвым риском, а не «ставка на рост».</p>
<h2>Драгоценные металлы</h2>
${table(met)}
<p>Металлы (цена за грамм) — классический защитный актив: не приносят купона и дивиденда,
но исторически сглаживают просадки портфеля в кризисы и при ослаблении рубля.</p>
<a class="cta" href="/">Открыть в приложении Basis: живые курсы, динамика и роль в портфеле →</a>
<h2>Другие классы активов Basis</h2>
<div class="grid">
<a class="chip" href="/bonds/">Облигации</a>
<a class="chip" href="/funds/">Фонды</a>
<a class="chip" href="/futures/">Фьючерсы</a>
<a class="chip" href="/company/">Компании</a>
</div>`;
  const descBits = [];
  if (usd && usd.last_price != null) descBits.push(`доллар ${fmtN(usd.last_price, 2)} ₽`);
  if (gld && gld.last_price != null) descBits.push(`золото ${fmtN(gld.last_price, 0)} ₽/г`);
  return pageShell({
    title: "Курсы валют и драгметаллов на Мосбирже: доллар, юань, золото, серебро | Basis",
    desc: `Биржевые курсы валют и цены металлов на споте Московской биржи${descBits.length ? ": " + descBits.join(", ") : ""}. Роль валюты и золота в портфеле — разбор Basis. Данные на ${dataDate}.`,
    canonicalPath: "/valyuta-metally/",
    breadcrumbs: [{ label: "Basis", href: "/" }, { label: "Валюта и металлы" }],
    bodyHtml: body,
    jsonLd: [],
    dataDate,
  });
}

/* ============================== MAIN ============================== */

function main() {
  const bondsSnap = readSnapshot("bonds");
  const fundsSnap = readSnapshot("funds");
  const futuresSnap = readSnapshot("futures");
  const spotSnap = readSnapshot("spot");
  if (!bondsSnap && !fundsSnap && !futuresSnap && !spotSnap) {
    console.log("SEO-инструменты: снапшоты scripts/data/*-snapshot.json не найдены — пропуск (сборка не тронута)");
    return;
  }
  fs.mkdirSync(_OUT, { recursive: true });
  const sitemap = []; // {loc, lastmod, pri}
  const RESERVED_BOND_SLUGS = new Set(["ofz", "vdo", "kvazivalyutnye", "flotery", "korotkie", "ezhemesyachnyy-kupon", "vse"]);

  /* ------------------------------ облигации ------------------------------ */
  if (bondsSnap && bondsSnap.rows && bondsSnap.rows.length) {
    const snapDay = bondsSnap.fetched_at.slice(0, 10);
    const dataDate = fmtDate(snapDay);
    const snapDateObj = new Date(snapDay);
    let maturedCount = 0;
    const bonds = bondsSnap.rows.filter((b) => {
      if (!b.secid || !/^[A-Za-z0-9-_]+$/.test(b.secid)) return false;
      if (RESERVED_BOND_SLUGS.has(b.secid.toLowerCase())) { console.log("пропуск (конфликт со слагом подборки):", b.secid); return false; }
      // уже погашенные на дату снапшота — мёртвые инструменты, страниц не делаем
      if (b.maturity_date && b.maturity_date < snapDay) { maturedCount++; return false; }
      return true;
    });
    // MOEX отдаёт ytm=0 у большинства флоатеров и части неликвида — это «нет
    // данных», а не нулевая доходность (та же нормализация, что в скринере)
    for (const b of bonds) if (b.ytm != null && b.ytm <= 0) b.ytm = null;

    // предикаты подборок
    const isClean = (b) => !b.is_defaulted && !b.yield_anomaly && !b.near_offer; // «честный» YTM
    const inOfz = (b) => b.bond_type === "ofz";
    const inVdo = (b) => b.risk_tier === "speculative" && !b.is_defaulted;
    const inQuasi = (b) => b.currency && !RUB_CUR.has(b.currency);
    const inFloater = (b) => b.coupon_type === "floater";
    const inShort = (b) => { const y = yearsTo(b.maturity_date, snapDateObj); return y != null && y > 0 && y <= 1 && !b.is_defaulted; };
    const inMonthly = (b) => b.coupon_period != null && b.coupon_period >= 28 && b.coupon_period <= 31;

    const byYtmDesc = (a, b) => (b.ytm || -1) - (a.ytm || -1);

    const collections = [
      {
        slug: "ofz", chip: "ОФЗ", crumb: "ОФЗ",
        h1: "ОФЗ: все выпуски и кривая доходности",
        title: "Облигации ОФЗ: доходность всех выпусков, кривая доходности | Basis",
        tableTitle: "Все выпуски ОФЗ",
        desc: (n, d) => `Все ${n} выпусков ОФЗ на Мосбирже: доходность к погашению, купоны, дюрация, кривая доходности по срокам. Госдолг РФ без прикрас — разбор Basis. Данные на ${d}.`,
        intro: `<p>ОФЗ — облигации федерального займа, госдолг РФ: кредитный риск минимальный,
поэтому доходность ОФЗ служит безрисковой базой, от которой Basis считает спреды всех
корпоративных бумаг. Основной риск здесь не кредитный, а процентный: чем длиннее выпуск
(дюрация), тем сильнее цена реагирует на движение ключевой ставки. Флоатеры (ОФЗ-ПК) и
линкеры (ОФЗ-ИН) живут по своим правилам — их «доходность к погашению» с фиксированными
выпусками напрямую не сравнивается.</p>`,
        filter: inOfz,
        sort: (a, b) => String(a.maturity_date || "9").localeCompare(String(b.maturity_date || "9")),
        sortNote: "по сроку погашения",
        top: null,
      },
      {
        slug: "vdo", chip: "ВДО", crumb: "ВДО",
        h1: "Высокодоходные облигации (ВДО) с оценкой риска",
        title: "Высокодоходные облигации (ВДО): список с оценкой «доходность vs риск» | Basis",
        tableTitle: "Топ по доходности (без дистресса)",
        desc: (n, d) => `${n} высокодоходных облигаций (ВДО) на Мосбирже: доходность, рейтинги и оценка Basis «доходность vs риск» по каждой — оплачен ли риск дефолта. Данные на ${d}.`,
        intro: `<p>ВДО — высокодоходные облигации спекулятивного кредитного качества (рейтинги BB и ниже
или без рейтинга). Высокая доходность здесь — не «подарок», а плата за реальный риск дефолта:
первый вопрос — «вернут ли тело», и только потом «сколько заработаю». Оценка Basis в последней
колонке — результат сравнения спреда бумаги с требуемым для её кредитной группы (методика
«доходность vs риск»): «риск оплачен» значит премия покрывает типичный риск группы, и ничего
больше. Бумаги в явном дистрессе (аномальная доходность, цена сильно ниже номинала) в топ-таблицу
не включены — там доходность уже нерелевантна.</p>`,
        filter: inVdo,
        preFilter: (b) => inVdo(b) && isClean(b) && b.coupon_type === "fixed",
        sort: byYtmDesc,
        sortNote: "топ-50 по доходности среди бумаг без признаков дистресса, фикс. купон",
        top: 50,
      },
      {
        slug: "kvazivalyutnye", chip: "Квазивалютные", crumb: "Квазивалютные",
        h1: "Квазивалютные и замещающие облигации",
        title: "Квазивалютные облигации: замещающие в USD, CNY, EUR — список | Basis",
        tableTitle: "Топ по доходности",
        desc: (n, d) => `${n} квазивалютных облигаций на Мосбирже: замещающие и юаневые выпуски с номиналом в USD, CNY, EUR. Доходности в валюте номинала, оценка риска Basis. Данные на ${d}.`,
        intro: `<p>Квазивалютные облигации — выпуски с номиналом в иностранной валюте (замещающие,
юаневые и др.), расчёты по которым идут в рублях по курсу. Это способ держать валютную
экспозицию внутри российской инфраструктуры. Доходность такой бумаги — «валютная»: сравнивать
её нужно не с рублёвыми ставками, а с валютными, помня о курсовом риске рублёвой переоценки.</p>`,
        filter: inQuasi,
        preFilter: (b) => inQuasi(b) && isClean(b),
        sort: byYtmDesc,
        sortNote: "топ-50 по доходности без явного дистресса",
        top: 50,
        tableOpts: { ytmHead: "Доходность (в валюте)" },
      },
      {
        slug: "flotery", chip: "Флоатеры", crumb: "Флоатеры",
        h1: "Облигации-флоатеры: купон за ключевой ставкой",
        title: "Флоатеры: облигации с плавающим купоном — список с надбавкой к КС | Basis",
        tableTitle: "Топ по надбавке к ключевой ставке",
        desc: (n, d) => `${n} флоатеров на Мосбирже: облигации с плавающим купоном (КС/RUONIA). Надбавка купона к ставке, кредитная оценка Basis по каждой бумаге. Данные на ${d}.`,
        intro: `<p>Флоатер — облигация с плавающим купоном, привязанным к ключевой ставке или RUONIA:
купон подстраивается под ставку, поэтому процентного риска тела почти нет. Обратная сторона —
«доходность к погашению» и G-спред к обычным ОФЗ для флоатера бессмысленны: реальная плата
за кредитный риск — это надбавка купона к ставке (в базисных пунктах). Именно по ней флоатеры
и отсортированы: больше надбавка — больше кредитного риска эмитента рынок в ней закладывает.</p>`,
        filter: inFloater,
        preFilter: (b) => inFloater(b) && !b.is_defaulted,
        sort: (a, b) => (b.floater_spread_bp != null ? b.floater_spread_bp : -1e9) - (a.floater_spread_bp != null ? a.floater_spread_bp : -1e9),
        sortNote: "топ-50 по надбавке купона к КС",
        top: 50,
        tableOpts: {
          ytmHead: "Надбавка к КС",
          ytmCell: (b) => b.floater_spread_bp != null ? `${b.floater_spread_bp >= 0 ? "+" : ""}${fmtN(b.floater_spread_bp, 0)} б.п.` : "—",
        },
      },
      {
        slug: "korotkie", chip: "Короткие (до года)", crumb: "Короткие",
        h1: "Короткие облигации: погашение до года",
        title: "Короткие облигации до года: доходность к погашению — список | Basis",
        tableTitle: "Ближайшие погашения",
        desc: (n, d) => `${n} облигаций с погашением до года на Мосбирже: доходность, купоны, даты погашения, оценка риска Basis. Короткий горизонт с минимальным процентным риском. Данные на ${d}.`,
        intro: `<p>Короткие облигации (погашение в пределах года) — минимальный процентный риск: цена
почти не реагирует на движение ставки, результат в основном определяется тем, доживёт ли
эмитент до погашения. Нюанс методики: на самом коротком хвосте (до ~4 месяцев) «доходность к
погашению» технически раздувается и перестаёт отражать реальную отдачу — такие бумаги Basis
помечает, а не выдаёт их цифры за «выгоду».</p>`,
        filter: inShort,
        sort: (a, b) => String(a.maturity_date || "9").localeCompare(String(b.maturity_date || "9")),
        sortNote: "топ-50 по близости погашения",
        top: 50,
      },
      {
        slug: "ezhemesyachnyy-kupon", chip: "Ежемесячный купон", crumb: "Ежемесячный купон",
        h1: "Облигации с ежемесячным купоном",
        title: "Облигации с ежемесячным купоном: список с доходностью | Basis",
        tableTitle: "Топ по доходности",
        desc: (n, d) => `${n} облигаций с ежемесячной выплатой купона на Мосбирже: доходность, размер купона, погашение и оценка риска Basis по каждой бумаге. Данные на ${d}.`,
        intro: `<p>Купон раз в месяц — частый запрос под регулярный денежный поток («зарплата с портфеля»).
Важно помнить: частота выплат сама по себе не добавляет доходности и не снижает риска —
ежемесячный купон встречается и у надёжных эмитентов, и у глубокого ВДО. Поэтому рядом с
каждой бумагой — оценка Basis «доходность vs риск», а не только размер купона.</p>`,
        filter: inMonthly,
        preFilter: (b) => inMonthly(b) && isClean(b),
        sort: byYtmDesc,
        sortNote: "топ-50 по доходности без явного дистресса",
        top: 50,
      },
    ];

    // членство в подборках (для чипов на странице бумаги)
    const collectionsOf = (b) => collections.filter((c) => c.filter(b)).map((c) => ({ slug: c.slug, chip: c.chip }));

    // соседи: серии того же эмитента → окно по сектору (не «первые 8 по алфавиту»)
    const issuerKey = (b) => b.issuer_ticker || strip(b.issuer_name || "").split(" ")[0].toLowerCase() || null;
    const byIssuer = new Map();
    const bySector = new Map();
    for (const b of bonds) {
      const ik = issuerKey(b);
      if (ik) { if (!byIssuer.has(ik)) byIssuer.set(ik, []); byIssuer.get(ik).push(b); }
      const sk = b.sector || "—";
      if (!bySector.has(sk)) bySector.set(sk, []);
      bySector.get(sk).push(b);
    }
    for (const list of bySector.values()) list.sort((a, b) => a.short_name.localeCompare(b.short_name, "ru"));
    const neighborsOf = (b) => {
      const out = [];
      const seen = new Set([b.secid]);
      const ik = issuerKey(b);
      if (ik) for (const s of byIssuer.get(ik) || []) {
        if (out.length >= 8) break;
        if (!seen.has(s.secid)) { out.push(s); seen.add(s.secid); }
      }
      if (out.length < 8) {
        const list = bySector.get(b.sector || "—") || [];
        const i = list.findIndex((x) => x.secid === b.secid);
        for (let d = 1; d <= list.length && out.length < 8; d++) {
          const j = i + (d % 2 ? Math.ceil(d / 2) : -Math.ceil(d / 2));
          const s = list[(j + list.length) % list.length];
          if (s && !seen.has(s.secid)) { out.push(s); seen.add(s.secid); }
        }
      }
      return out;
    };

    const ctx = { dataDate, collections, collectionsOf, neighborsOf };

    // страницы выпусков
    let thinCount = 0;
    for (const b of bonds) {
      const thin = bondIsThin(b);
      writePage(path.join("bonds", b.secid), bondPage(b, ctx, thin));
      if (thin) { thinCount++; continue; }   // в карту сайта не добавляем
      sitemap.push({ loc: `${_SITE}/bonds/${b.secid}/`, lastmod: snapDay, pri: "0.6" });
    }
    console.log(`  из них без рыночной оценки (noindex, не в карте сайта): ${thinCount}`);

    // подборки
    for (const col of collections) {
      const totalRows = bonds.filter(col.filter);
      const tableRows = (col.preFilter ? bonds.filter(col.preFilter) : totalRows).slice().sort(col.sort);
      let extra = "";
      if (col.slug === "ofz") {
        // кривая доходности: только фиксированные ОФЗ-ПД, медианный YTM по срокам
        const fixed = totalRows.filter((b) => b.coupon_type === "fixed" && b.ytm != null);
        const buckets = [["до 1 года", 0, 1], ["1–2 года", 1, 2], ["2–3 года", 2, 3], ["3–5 лет", 3, 5], ["5–7 лет", 5, 7], ["7–10 лет", 7, 10], ["10+ лет", 10, 99]];
        const rows = buckets.map(([lab, lo, hi]) => {
          const ys = fixed.filter((b) => { const y = yearsTo(b.maturity_date, snapDateObj); return y != null && y > lo && y <= hi; }).map((b) => b.ytm);
          return ys.length ? `<tr><td>${lab}</td><td class="num">${fmtPct(median(ys))}</td><td class="num">${ys.length}</td></tr>` : "";
        }).filter(Boolean).join("");
        if (rows) extra = `<h2>Кривая доходности ОФЗ на ${dataDate}</h2>
<p class="tag">Медианная доходность фиксированных выпусков (ОФЗ-ПД) по срокам до погашения · факт MOEX</p>
<div class="wrap"><table><thead><tr><th>Срок до погашения</th><th class="num">Доходность (медиана)</th><th class="num">Выпусков</th></tr></thead><tbody>${rows}</tbody></table></div>
<p>Форма кривой — рыночные ожидания по ставке: инверсия (короткие доходнее длинных) обычно
означает, что рынок ждёт снижения ключевой ставки на горизонте.</p>`;
      }
      writePage(path.join("bonds", col.slug), collectionPage(col, tableRows, totalRows.length, ctx, extra));
      sitemap.push({ loc: `${_SITE}/bonds/${col.slug}/`, lastmod: snapDay, pri: "0.8" });
    }

    // каталог /bonds/ + полный список с пагинацией /bonds/vse/{n}/
    const typeOrder = { ofz: 0, muni: 1, corporate: 2, other: 3 };
    const allSorted = bonds.slice().sort((a, b) =>
      (typeOrder[a.bond_type] ?? 9) - (typeOrder[b.bond_type] ?? 9) || a.short_name.localeCompare(b.short_name, "ru"));
    const PER_PAGE = 400;
    const pages = Math.ceil(allSorted.length / PER_PAGE);
    const pagerHtml = (cur) => `<div class="grid">${Array.from({ length: pages }, (_, i) =>
      i + 1 === cur ? `<span class="chip" style="border-color:var(--copper)">${i + 1}</span>`
        : `<a class="chip" href="/bonds/vse/${i + 1}/">${i + 1}</a>`).join("")}</div>`;
    for (let p = 1; p <= pages; p++) {
      const chunk = allSorted.slice((p - 1) * PER_PAGE, p * PER_PAGE);
      const list = chunk.map((b) => {
        const bits = [];
        if (b.ytm != null && !b.yield_anomaly) bits.push(fmtPct(b.ytm));
        if (b.maturity_date) bits.push(`погашение ${fmtDate(b.maturity_date)}`);
        return `<li><a href="/bonds/${encodeURIComponent(b.secid)}/">${escapeHtml(b.short_name)}</a>${bits.length ? ` — ${bits.join(", ")}` : ""}</li>`;
      }).join("");
      const body = `
<h1>Все облигации: страница ${p} из ${pages}</h1>
<p class="sub">Полный список выпусков в базе Basis (${allSorted.length}), в алфавитном порядке по типам:
ОФЗ → муниципальные → корпоративные. У каждой бумаги — своя страница с параметрами и оценкой «доходность vs риск».</p>
${pagerHtml(p)}
<ul>${list}</ul>
${pagerHtml(p)}
<p><a href="/bonds/">← Каталог облигаций и подборки</a></p>`;
      writePage(path.join("bonds", "vse", String(p)), pageShell({
        title: `Все облигации Мосбиржи — список, страница ${p} из ${pages} | Basis`,
        desc: `Полный список облигаций в базе Basis, страница ${p} из ${pages}: доходность и дата погашения каждого выпуска со ссылкой на разбор. Данные на ${dataDate}.`,
        canonicalPath: `/bonds/vse/${p}/`,
        breadcrumbs: [{ label: "Basis", href: "/" }, { label: "Облигации", href: "/bonds/" }, { label: `Все выпуски · стр. ${p}` }],
        bodyHtml: body,
        jsonLd: [],
        dataDate,
      }));
      sitemap.push({ loc: `${_SITE}/bonds/vse/${p}/`, lastmod: snapDay, pri: "0.4" });
    }

    const nOfz = bonds.filter(inOfz).length, nMuni = bonds.filter((b) => b.bond_type === "muni").length,
      nCorp = bonds.filter((b) => b.bond_type === "corporate").length, nDef = bonds.filter((b) => b.is_defaulted).length;
    const colCards = collections.map((c) => {
      const n = bonds.filter(c.filter).length;
      return `<p><a href="/bonds/${c.slug}/"><b>${escapeHtml(c.h1)}</b></a> — ${n} ${plural(n, "бумага", "бумаги", "бумаг")}</p>`;
    }).join("");
    const catalogBody = `
<h1>Облигации на Московской бирже: анализ ${bonds.length} выпусков</h1>
<p class="sub">ОФЗ — ${nOfz}, муниципальные — ${nMuni}, корпоративные — ${nCorp}${nDef ? ` (в т.ч. в дефолте — ${nDef})` : ""}.
По каждому выпуску — страница с параметрами, рыночными данными и оценкой Basis «доходность vs риск». Данные на ${dataDate}.</p>
<div class="box"><p class="tag">Методика Basis — коротко</p>
<p>Каждая бумага получает три взгляда на надёжность: рыночный (спред доходности к ОФЗ),
агентский (рейтинг АКРА/ЭкспертРА и др.) и оценку Basis (Risk Score по совокупности факторов,
включая долговую нагрузку эмитента). Светофор «доходность vs риск» отвечает на главный вопрос
держателя: платит ли бумага достаточно за свой риск — это оценка соотношения, а не совет.</p></div>
<h2>Подборки</h2>
${colCards}
<h2>Полный список выпусков</h2>
<p>Все ${bonds.length} ${plural(bonds.length, "бумага", "бумаги", "бумаг")} на ${pages} страницах: <a href="/bonds/vse/1/">открыть список →</a></p>
<a class="cta" href="/">Скринер облигаций с фильтрами и живыми котировками — в приложении Basis →</a>
<h2>Другие классы активов</h2>
<div class="grid">
<a class="chip" href="/company/">Компании</a>
<a class="chip" href="/funds/">Фонды</a>
<a class="chip" href="/futures/">Фьючерсы</a>
<a class="chip" href="/valyuta-metally/">Валюта и металлы</a>
</div>`;
    if (maturedCount) console.log(`облигации: пропущено погашенных до даты снапшота: ${maturedCount}`);
    writePage("bonds", pageShell({
      title: `Облигации Мосбиржи: доходность и риск ${bonds.length} выпусков — анализ Basis`,
      desc: `Каталог ${bonds.length} облигаций Московской биржи: ОФЗ, корпоративные, ВДО, флоатеры, замещающие. По каждой — доходность, купон и оценка «доходность vs риск». Данные на ${dataDate}.`,
      canonicalPath: "/bonds/",
      breadcrumbs: [{ label: "Basis", href: "/" }, { label: "Облигации" }],
      bodyHtml: catalogBody,
      jsonLd: [],
      dataDate,
    }));
    sitemap.push({ loc: `${_SITE}/bonds/`, lastmod: snapDay, pri: "0.9" });
    console.log(`Облигации: ${bonds.length} страниц выпусков + ${collections.length} подборок + каталог + ${pages} стр. списка`);
  }

  /* ------------------------------ фонды ------------------------------ */
  if (fundsSnap && fundsSnap.rows && fundsSnap.rows.length) {
    const snapDay = fundsSnap.fetched_at.slice(0, 10);
    const ctx = { dataDate: fmtDate(snapDay) };
    const funds = fundsSnap.rows.filter((f) => f.secid && /^[A-Za-z0-9-_@]+$/.test(f.secid));
    for (const f of funds) {
      writePage(path.join("funds", f.secid), fundPage(f, funds, ctx));
      sitemap.push({ loc: `${_SITE}/funds/${f.secid}/`, lastmod: snapDay, pri: "0.6" });
    }
    writePage("funds", fundsIndex(funds, ctx));
    sitemap.push({ loc: `${_SITE}/funds/`, lastmod: snapDay, pri: "0.8" });
    console.log(`Фонды: ${funds.length} страниц + каталог`);
  }

  /* ------------------------------ фьючерсы ------------------------------ */
  if (futuresSnap && futuresSnap.rows && futuresSnap.rows.length) {
    const snapDay = futuresSnap.fetched_at.slice(0, 10);
    const ctx = { dataDate: fmtDate(snapDay) };
    // экспирированные на дату снапшота НЕ генерим (мёртвая цена); прод-API уже
    // фильтрует, но снапшот мог отлежаться — перефильтровываем от даты снапшота
    const futs = futuresSnap.rows.filter((f) =>
      f.secid && /^[A-Za-z0-9-_]+$/.test(f.secid) &&
      (!f.expiration_date || f.expiration_date >= snapDay));
    // last_price=0 у неторговавшихся сегодня контрактов — «нет сделок», не цена
    for (const f of futs) if (f.last_price != null && f.last_price <= 0) f.last_price = null;
    // macOS-ловушка: FS без учёта регистра, FORTS-тикеры регистрозависимы — дубли схлопнутся
    const seen = new Map();
    const dups = [];
    for (const f of futs) {
      const k = f.secid.toLowerCase();
      if (seen.has(k)) { dups.push(f.secid); continue; }
      seen.set(k, f);
    }
    if (dups.length) console.log(`фьючерсы: пропущены case-дубли SECID (${dups.length}):`, dups.slice(0, 5).join(", "));
    const list = [...seen.values()];
    for (const f of list) {
      writePage(path.join("futures", f.secid), futurePage(f, list, ctx));
      sitemap.push({ loc: `${_SITE}/futures/${f.secid}/`, lastmod: snapDay, pri: "0.5" });
    }
    writePage("futures", futuresIndex(list, ctx));
    sitemap.push({ loc: `${_SITE}/futures/`, lastmod: snapDay, pri: "0.8" });
    console.log(`Фьючерсы: ${list.length} страниц + каталог (экспирированных пропущено: ${futuresSnap.rows.length - futs.length})`);
  }

  /* --------------------------- валюта/металлы --------------------------- */
  if (spotSnap && spotSnap.rows && spotSnap.rows.length) {
    const snapDay = spotSnap.fetched_at.slice(0, 10);
    writePage("valyuta-metally", spotLanding(spotSnap.rows, { dataDate: fmtDate(snapDay) }));
    sitemap.push({ loc: `${_SITE}/valyuta-metally/`, lastmod: snapDay, pri: "0.7" });
    console.log("Валюта/металлы: 1 лендинг (6 инструментов; на отдельные страницы данных мало)");
  }

  /* ------------------------------ sitemap ------------------------------ */
  const xml = `<?xml version="1.0" encoding="UTF-8"?>
<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">
${sitemap.map((u) => `  <url><loc>${u.loc}</loc><lastmod>${u.lastmod}</lastmod><priority>${u.pri}</priority></url>`).join("\n")}
</urlset>
`;
  fs.writeFileSync(path.join(_OUT, "sitemap-instruments.xml"), xml, "utf8");
  console.log(`sitemap-instruments.xml: ${sitemap.length} URL (lastmod = дата снапшота). Не забыть строку "Sitemap: ${_SITE}/sitemap-instruments.xml" в robots.txt`);
}

main();

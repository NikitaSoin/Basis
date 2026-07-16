#!/usr/bin/env node
/**
 * Генератор статических SEO-страниц компаний (v2, 2026-07-16).
 *
 * Проблема v1 (жалобы Яндекс.Вебмастера + владельца): (а) description у всех 264
 * страниц был один шаблон под копирку — Яндекс флагует как «отсутствуют или
 * некорректно заполнены»; (б) на страницах компаний не было favicon вообще;
 * (в) заголовки из юридических имён («Публичное акционерное общество ...»);
 * (г) контент тонкий (5 строк фактов) — по запросам «бизнес-модель сбера»,
 * «дивиденды лукойла» ранжироваться нечему; (д) не было точек входа сразу в
 * нужную вкладку карточки.
 *
 * v2 генерирует НА КАЖДУЮ компанию:
 *   /company/T/            — хаб: уникальный title/description из реальных чисел,
 *                            суть бизнеса, финансовая таблица по годам, дивиденды,
 *                            разделы, похожие компании сектора, JSON-LD.
 *   /company/T/business/   — бизнес-модель (выжимка business_model.md).
 *   /company/T/finance/    — финансы по годам + подход к оценке.
 *   /company/T/dividends/  — политика + история выплат (governance.json).
 *   /company/T/macro/      — макро-разбор (выжимка macro_summary.md).
 *   /company/T/geo/        — геополитические риски (выжимка geo_summary.md).
 * Плюс каталог /company/ (все компании по секторам) и sitemap.xml со всеми URL.
 *
 * Каждая страница ведёт кнопкой в живое приложение СРАЗУ на нужную вкладку:
 * /?company=T&tab=business|finance|governance|macro|geo (см. App.js deep-link).
 *
 * Контент — ЧЕСТНАЯ ВЫЖИМКА (первые ~3 тыс. знаков раздела + «продолжение в
 * приложении»), не полная копия анализа: страница отвечает на запрос и ведёт
 * в продукт. Числа в статике — годовые из financials.json (стабильны в пределах
 * года); live-метрики (цена/апсайд/мультипликаторы) в статику НЕ пекутся —
 * прямо написано «считаются в приложении».
 *
 * ПОЧЕМУ Node, а не Python: билд-окружение Timeweb выполняет `npm run build`,
 * там гарантирован только Node (python3 нет — падало на бою). Только built-in
 * модули. Запускается ПОСЛЕ `craco build` (см. package.json), пишет в build/.
 */
"use strict";
const fs = require("fs");
const path = require("path");

const _ROOT = path.resolve(__dirname, "..", "..", "..");
const _COMPANIES_DIR = path.join(_ROOT, "backend", "companies");
const _RATES_CSV = path.join(_ROOT, "rates.csv");
const _BUILD_DIR = path.join(__dirname, "..", "build");
const _SITE = "https://inbasis.ru";
const _TODAY = new Date().toISOString().slice(0, 10);

/* ----------------------------- утилиты ----------------------------- */

function strip(s) { return (s || "").replace(/\s+/g, " ").trim(); }

function escapeHtml(s) {
  return String(s == null ? "" : s)
    .replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;").replace(/'/g, "&#39;");
}

// rates.csv — cp1251; перекодировка вручную (без внешних зависимостей).
const CP1251 = (() => {
  const map = {};
  for (let i = 0; i < 128; i++) map[i] = String.fromCharCode(i);
  const hi = "ЂЃ‚ѓ„…†‡€‰Љ‹ЊЌЋЏђ‘’“”•–—˜™љ›њќћџ ЎўЈ¤Ґ¦§Ё©Є«¬­®Ї°±Ііґµ¶·ё№є»јЅѕїАБВГДЕЖЗИЙКЛМНОПРСТУФХЦЧШЩЪЫЬЭЮЯабвгдежзийклмнопрстуфхцчшщъыьэюя";
  for (let i = 0; i < hi.length; i++) map[128 + i] = hi[i];
  return map;
})();
function decodeCp1251(buf) {
  let out = "";
  for (let i = 0; i < buf.length; i++) out += CP1251[buf[i]] || "?";
  return out;
}
function parseCsvLine(line, delim) {
  const out = [];
  let field = "", inQuotes = false;
  for (let i = 0; i < line.length; i++) {
    const c = line[i];
    if (inQuotes) {
      if (c === '"') { if (line[i + 1] === '"') { field += '"'; i++; } else inQuotes = false; }
      else field += c;
    } else if (c === '"' && field === "") inQuotes = true;
    else if (c === delim) { out.push(field); field = ""; }
    else field += c;
  }
  out.push(field);
  return out;
}
function loadNames() {
  const names = {};
  if (!fs.existsSync(_RATES_CSV)) return names;
  const text = decodeCp1251(fs.readFileSync(_RATES_CSV));
  let header = null;
  for (const line of text.split(/\r?\n/)) {
    if (!line.trim()) continue;
    const row = parseCsvLine(line, ";");
    if (row[0] === "SECID") { header = row; continue; }
    if (!header) continue;
    const d = {};
    header.forEach((k, i) => { d[k] = row[i]; });
    const secid = (d.SECID || "").trim();
    const name = (d.EMITENTNAME || d.NAME || "").trim();
    if (secid && name) names[secid] = name;
  }
  return names;
}

// «ПАО «Сбербанк»» → «Сбербанк»; «Публичное акционерное общество "X"» → «X».
// 🔴 \b в JS-регэкспах НЕ работает с кириллицей (ASCII-only word boundary) —
// юрформы срезаем токенами по пробелам, не по \b.
const LEGAL_TOKENS = new Set(["МКПАО", "МКООО", "ПАО", "ОАО", "ЗАО", "АО", "ООО", "НКО", "ПК"]);
function shortName(raw) {
  if (!raw) return "";
  let s = strip(raw)
    .replace(/Международная компания публичное акционерное общество/gi, "")
    .replace(/Публичное акционерное общество/gi, "")
    .replace(/Открытое акционерное общество/gi, "")
    .replace(/Закрытое акционерное общество/gi, "")
    .replace(/Акционерное общество/gi, "");
  s = s.split(/\s+/).filter((w) => !LEGAL_TOKENS.has(w.replace(/[«»"',.]/g, ""))).join(" ").trim();
  // развернуть кавычки «...» / "..." если имя целиком в них
  const m = s.match(/^[«"']+(.+?)[»"']+$/);
  if (m) s = m[1];
  // хвост в скобках-кавычках после снятия юрформы: `«Сбербанк» (прив.)` → оставить как есть
  s = strip(s.replace(/^[-–—\s]+|[-–—\s]+$/g, ""));
  return s || strip(raw);
}

// meta.sector в данных — зоопарк из английских слагов и русских названий
// (utilities / Нефтегаз / consumer_retail / «Химия (минеральные удобрения»...).
// Для каталога, блока «похожие компании» и видимых меток — нормализация в
// канонические русские корзины. Фолбэк: как есть (кириллица) / капитализация.
const SECTOR_RULES = [
  [/^(utilities|energy_|energosbyt|электросети|электроэнергет|энергетика)/, "Электроэнергетика"],
  [/^(finance|financials|банки|финансы|investment)/, "Финансы"],
  [/^(consumer|потребительск|retail)/, "Потребительский сектор"],
  [/^(metals|mining|металлург|драгоценная добыча|чёрная металлург|черная металлург)/, "Металлургия и добыча"],
  [/^(oil_gas|нефтегаз|нефть и газ|нефтеперераб)/, "Нефть и газ"],
  [/^(telecom|телеком)/, "Телекоммуникации"],
  [/^(chemicals|химия)/, "Химия и удобрения"],
  [/^(it$|it\b|technology|edtech|информационные технолог|media)/, "ИТ и технологии"],
  [/^(machinery|industrials|машиностроен|судостроен|автопром|aerospace|электроника)/, "Машиностроение и промышленность"],
  [/^(real_estate|developer|девелопмент|infrastructure)/, "Девелопмент и инфраструктура"],
  [/^(transport|транспорт)/, "Транспорт"],
  [/^(pharma|здравоохран|медицин)/, "Медицина и фарма"],
  [/^(сельское хозяйство|agro)/, "Агропром"],
  [/^(лесопромышл|производство упаковки)/, "Лес и упаковка"],
  [/^(холдинг)/, "Холдинги"],
];
function normalizeSector(raw) {
  const s = strip(raw).toLowerCase();
  if (!s) return "Прочее";
  for (const [re, label] of SECTOR_RULES) if (re.test(s)) return label;
  // кириллическое название — капитализируем и отрезаем скобочный хвост
  const clean = strip(raw).replace(/\s*[(«].*$/, "");
  return clean ? clean[0].toUpperCase() + clean.slice(1) : "Прочее";
}
// Для видимой метки: русское «Финансы / Банки» оставляем как есть,
// английский слаг заменяем нормализованной корзиной.
function displaySector(rawFull, normalized) {
  const s = strip(rawFull);
  if (!s || /[a-z_]/i.test(s)) return normalized; // латиница/слаг → корзина
  return s;
}

const CUR_SYM = { RUB: "₽", USD: "$", EUR: "€", CNY: "¥" };
// v — в единицах meta.unit (обычно млн). Формат: 1 706 000 млн → «1,71 трлн ₽».
function fmtMoney(v, unit, currency) {
  if (v == null || isNaN(v)) return null;
  const mult = unit === "млрд" ? 1000 : unit === "тыс" ? 0.001 : 1; // → млн
  const mln = v * mult;
  const sym = CUR_SYM[currency] || currency || "₽";
  const abs = Math.abs(mln);
  let num, suffix;
  if (abs >= 1e6) { num = mln / 1e6; suffix = "трлн"; }
  else if (abs >= 1e3) { num = mln / 1e3; suffix = "млрд"; }
  else { num = mln; suffix = "млн"; }
  const digits = Math.abs(num) >= 100 ? 0 : Math.abs(num) >= 10 ? 1 : 2;
  return `${num.toFixed(digits).replace(".", ",")} ${suffix} ${sym}`;
}

function truncate(s, n) {
  s = strip(s);
  if (s.length <= n) return s;
  const cut = s.slice(0, n);
  return cut.slice(0, Math.max(cut.lastIndexOf(" "), n - 25)).replace(/[,;:.\s]+$/, "") + "…";
}

/* --------------------- markdown → простой HTML --------------------- */
// Минимальный конвертер под наши *_summary.md / business_model.md:
// заголовки ##/###, **жирный**, *курсив*, списки «- », таблицы |...|, абзацы.
function mdToHtml(md) {
  const lines = md.split(/\r?\n/);
  const out = [];
  let para = [], list = null, table = null;
  const inline = (s) => escapeHtml(s)
    .replace(/\*\*(.+?)\*\*/g, "<b>$1</b>")
    .replace(/\*([^*]+)\*/g, "<i>$1</i>")
    .replace(/`([^`]+)`/g, "<code>$1</code>");
  const flushPara = () => { if (para.length) { out.push(`<p>${inline(para.join(" "))}</p>`); para = []; } };
  const flushList = () => { if (list) { out.push(`<ul>${list.map((li) => `<li>${inline(li)}</li>`).join("")}</ul>`); list = null; } };
  const flushTable = () => {
    if (!table || !table.length) { table = null; return; }
    const rows = table.filter((r) => !/^\s*\|?[\s:|-]+\|?\s*$/.test(r)); // строки-разделители
    const cells = rows.map((r) => r.replace(/^\s*\|/, "").replace(/\|\s*$/, "").split("|").map((c) => inline(c.trim())));
    if (cells.length) {
      const head = cells[0], body = cells.slice(1);
      out.push("<table><thead><tr>" + head.map((c) => `<th>${c}</th>`).join("") + "</tr></thead><tbody>" +
        body.map((r) => "<tr>" + r.map((c, i) => `<td${i > 0 ? ' class="num"' : ""}>${c}</td>`).join("") + "</tr>").join("") +
        "</tbody></table>");
    }
    table = null;
  };
  for (const raw of lines) {
    const line = raw.replace(/\t/g, " ");
    if (/^\s*\|.*\|\s*$/.test(line)) { flushPara(); flushList(); (table = table || []).push(line); continue; }
    flushTable();
    const h = line.match(/^(#{1,4})\s+(.*)$/);
    if (h) { flushPara(); flushList(); const lvl = Math.min(h[1].length + 1, 4); out.push(`<h${lvl}>${inline(h[2])}</h${lvl}>`); continue; }
    const li = line.match(/^\s*[-*]\s+(.*)$/);
    if (li) { flushPara(); (list = list || []).push(li[1]); continue; }
    if (!line.trim()) { flushPara(); flushList(); continue; }
    // перенос строки внутри пункта списка (md wrap): продолжение клеится к
    // последнему <li>, а не превращается в отдельный <p> с маленькой буквы
    // (аудит 2026-07-16 — «разорванные пункты списков»)
    if (list) { list[list.length - 1] += " " + line.trim(); continue; }
    para.push(line.trim());
  }
  flushPara(); flushList(); flushTable();
  return out.join("\n");
}

// Выжимка: пропустить шапку до первого «## », взять до maxChars исходного md.
// 🔴 Аудит 2026-07-16: резать МОЖНО ТОЛЬКО по границе блока «\n\n» (обрезка по
// «. » посреди абзаца давала видимые огрызки «**4.», «минус**, …» на 49
// страницах), и после обрезки надо вычистить висячий мусор в хвосте: заголовок
// без контента (92 страницы), голый номер пункта, блок с непарными «**»,
// короткий не завершённый обрывок. Плюс служебные заголовки внутренней
// структуры разбора («Первый экран») на публичную страницу не выносим.
const SERVICE_HEADINGS = /^#{1,4}\s*(Первый экран)\s*$/im;
function mdExcerpt(md, maxChars) {
  if (!md) return null;
  let body = md.replace(/^#[^#\n][^\n]*\n/, ""); // сбросить H1
  const firstH2 = body.search(/^##\s/m);
  if (firstH2 > 0) body = body.slice(firstH2);
  if (body.length > maxChars) {
    const cut = body.slice(0, maxChars);
    const lastBreak = cut.lastIndexOf("\n\n");
    body = lastBreak > maxChars * 0.4 ? cut.slice(0, lastBreak) : cut;
  }
  // почистить хвост: убираем мусорные последние блоки, пока они мусорные
  const blocks = body.split(/\n{2,}/).filter((b) => b.trim());
  const isJunk = (b) => {
    const t = b.trim();
    if (/^#{1,4}\s/.test(t)) return true;                      // висячий заголовок
    if (/^\**\s*\d+\.\s*$/.test(t)) return true;               // голый «**4.» / «6.»
    if ((t.match(/\*\*/g) || []).length % 2 === 1) return true; // непарные **
    if (t.length < 40 && !/[.!?:;»)…%]$/.test(t)) return true; // короткий обрывок
    return false;
  };
  while (blocks.length && isJunk(blocks[blocks.length - 1])) blocks.pop();
  // служебные заголовки — вычистить по всему телу
  const cleaned = blocks.filter((b) => !SERVICE_HEADINGS.test(b.trim()));
  if (!cleaned.length) return null;
  const html = mdToHtml(cleaned.join("\n\n"));
  return html || null;
}

// Первое связное предложение прозы из md (для description).
// Конец предложения — точка/!/?, за которой пробел и заглавная буква, и слово
// перед точкой — не сокращение («г. Москва», «руб.», «млн.» — не конец фразы).
const ABBREV = new Set(["г", "гг", "руб", "коп", "тыс", "млн", "млрд", "трлн",
  "т", "п", "пп", "им", "св", "ул", "стр", "др", "проч", "см", "напр", "т.е", "т.д", "т.ч"]);
function mdFirstSentence(md, cap) {
  if (!md) return null;
  const text = md
    .replace(/^#.*$/gm, " ").replace(/\|.*\|/g, " ")
    .replace(/\*\*|\*|`/g, "").replace(/\s+/g, " ").trim();
  if (!text) return null;
  const re = /([.!?])\s+(?=[А-ЯЁA-Z«])/g;
  let m;
  while ((m = re.exec(text)) !== null) {
    const end = m.index + 1;
    if (end < 60) continue;
    const before = text.slice(0, m.index);
    const lastWord = (before.match(/([А-Яа-яЁёA-Za-z.]+)$/) || [])[1] || "";
    if (ABBREV.has(lastWord.replace(/\.+$/, "").toLowerCase())) continue;
    return truncate(text.slice(0, end), cap);
  }
  return truncate(text, cap);
}

/* ----------------------------- данные ----------------------------- */

function readJson(p) { try { return JSON.parse(fs.readFileSync(p, "utf8")); } catch { return null; } }
function readText(p) { try { return fs.readFileSync(p, "utf8"); } catch { return null; } }

function loadCompany(ticker, namesFallback) {
  const dir = path.join(_COMPANIES_DIR, ticker);
  const fin = readJson(path.join(dir, "financials.json"));
  if (!fin || !fin.meta) return null;
  const meta = fin.meta;
  const gov = readJson(path.join(dir, "governance.json"));
  const name = strip(meta.name || namesFallback[ticker] || ticker);
  const rawSector = strip(meta.sector || "");
  const primary = rawSector.split("/")[0].trim();
  const sector = normalizeSector(primary);
  return {
    ticker,
    name,
    short: shortName(name) || ticker,
    sector,
    sectorFull: displaySector(rawSector, sector),
    profile: meta.profile || "standard",
    unit: meta.unit || "млн",
    currency: meta.currency || "RUB",
    standard: meta.reporting_standard || null,
    years: Array.isArray(meta.fiscal_years) ? meta.fiscal_years : [],
    fin,
    dividends: gov && gov.dividends ? gov.dividends : null,
    businessMd: readText(path.join(dir, "business_model.md")),
    macroMd: readText(path.join(dir, "macro_summary.md")),
    geoMd: readText(path.join(dir, "geo_summary.md")),
  };
}

// Ряд «показатель по годам», выровненный к fiscal_years. Возвращает {label, values[]}.
function finRows(c) {
  const pnl = c.profile === "bank" ? (c.fin.bank_pnl || {}) : (c.fin.income_statement || {});
  const spec = c.profile === "bank"
    ? [["net_interest_income", "Чистые процентные доходы"], ["net_fee_income", "Чистые комиссионные доходы"],
       ["provisions", "Резервы под кредитные убытки"], ["net_profit", "Чистая прибыль"]]
    : [["revenue", "Выручка"], ["ebitda", "EBITDA"], ["operating_profit", "Операционная прибыль"], ["net_profit", "Чистая прибыль"]];
  const rows = [];
  for (const [key, label] of spec) {
    const arr = pnl[key];
    if (Array.isArray(arr) && arr.some((v) => v != null)) rows.push({ key, label, values: arr });
  }
  return rows;
}

// Последнее значение ряда с годом (для description).
function lastValue(c, key) {
  const pnl = c.profile === "bank" ? (c.fin.bank_pnl || {}) : (c.fin.income_statement || {});
  const arr = pnl[key];
  if (!Array.isArray(arr)) return null;
  for (let i = arr.length - 1; i >= 0; i--) {
    if (arr[i] != null && c.years[i] != null) return { year: c.years[i], value: arr[i] };
  }
  return null;
}

/* --------------------------- HTML-шаблон --------------------------- */

const CSS = `
:root{--paper:#F7F5F0;--ink:#1F1B16;--muted:#5A5248;--faint:#8A8072;--copper:#C97A4A;--line:#E4DFD5}
*{box-sizing:border-box}
body{font-family:-apple-system,'Segoe UI',Roboto,sans-serif;background:var(--paper);color:var(--ink);
     max-width:760px;margin:0 auto;padding:32px 20px 60px;line-height:1.55}
h1{font-family:Georgia,'Times New Roman',serif;font-size:28px;line-height:1.25;margin:10px 0 4px}
h2{font-family:Georgia,serif;font-size:21px;margin:28px 0 10px}
h3{font-family:Georgia,serif;font-size:17px;margin:20px 0 8px}
h4{font-size:15px;margin:16px 0 6px}
p{margin:10px 0}
a{color:var(--copper)}
.crumbs{font-size:13px;color:var(--faint)} .crumbs a{color:var(--faint)}
.sub{color:var(--muted);font-size:14px;margin:0 0 14px}
table{width:100%;border-collapse:collapse;margin:14px 0;font-size:14px}
th,td{text-align:left;padding:7px 6px;border-bottom:1px solid var(--line);vertical-align:top}
th{color:var(--muted);font-weight:600}
td.num,th.num{text-align:right;font-variant-numeric:tabular-nums}
.cta{display:inline-block;margin:18px 0 6px;padding:11px 22px;background:var(--copper);color:#fff;
     text-decoration:none;border-radius:10px;font-size:14.5px;font-weight:600}
.cta:hover{filter:brightness(.95)}
.grid{display:flex;flex-wrap:wrap;gap:8px;margin:12px 0}
.chip{display:inline-block;padding:7px 14px;border:1px solid var(--line);border-radius:999px;
      background:#fff;color:var(--ink);text-decoration:none;font-size:13.5px}
.chip:hover{border-color:var(--copper)}
.note{font-size:12.5px;color:var(--faint);margin-top:26px;border-top:1px solid var(--line);padding-top:14px}
.tag{font-size:11.5px;color:var(--faint);text-transform:uppercase;letter-spacing:.06em}
ul{padding-left:22px}
`.trim();

function pageShell({ title, desc, canonicalPath, breadcrumbs, bodyHtml, jsonLd }) {
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
<meta name="robots" content="index, follow">
<meta property="og:type" content="article">
<meta property="og:site_name" content="Basis">
<meta property="og:title" content="${escapeHtml(title)}">
<meta property="og:description" content="${escapeHtml(desc)}">
<meta property="og:url" content="${url}">
<meta property="og:image" content="${_SITE}/og-banner.png">
<meta property="og:locale" content="ru_RU">
<meta name="twitter:card" content="summary_large_image">
<meta name="twitter:image" content="${_SITE}/og-banner.png">
<link rel="icon" type="image/svg+xml" href="/favicon.svg">
<link rel="icon" type="image/png" sizes="120x120" href="/favicon-120.png">
<link rel="apple-touch-icon" sizes="180x180" href="/apple-touch-icon.png">
<script type="application/ld+json">${JSON.stringify(ld)}</script>
<style>${CSS}</style>
</head>
<body>
<nav class="crumbs">${crumbsHtml}</nav>
${bodyHtml}
<p class="note">Basis — независимый аналитический слой, не брокер и не даёт сигналов
«купить/продать». Числа на этой странице — из годовой отчётности на дату последнего
обновления разбора; живые показатели (цена, мультипликаторы, апсайд к справедливой цене)
считаются в приложении. Материал не является индивидуальной инвестиционной рекомендацией.</p>
</body>
</html>`;
}

function corpLd(c) {
  return [{
    "@type": "Corporation",
    name: c.name,
    alternateName: c.short !== c.name ? c.short : undefined,
    tickerSymbol: c.ticker,
    url: `${_SITE}/company/${c.ticker}/`,
  }];
}

function finTableHtml(c, maxYears) {
  const rows = finRows(c);
  if (!rows.length || !c.years.length) return null;
  const n = Math.min(maxYears, c.years.length);
  const idx = [];
  for (let i = c.years.length - n; i < c.years.length; i++) idx.push(i);
  const head = `<tr><th>Показатель</th>${idx.map((i) => `<th class="num">${c.years[i]}</th>`).join("")}</tr>`;
  const body = rows.map((r) =>
    `<tr><td>${escapeHtml(r.label)}</td>${idx.map((i) => {
      const f = fmtMoney(r.values[i], c.unit, c.currency);
      return `<td class="num">${f ? escapeHtml(f) : "—"}</td>`;
    }).join("")}</tr>`).join("");
  const std = c.standard ? ` (${escapeHtml(c.standard)})` : "";
  return `<table><thead>${head}</thead><tbody>${body}</tbody></table>
<p class="tag">Годовая отчётность${std}. «—» — данных за период нет.</p>`;
}

function dividendsTableHtml(c, maxRows) {
  const d = c.dividends;
  if (!d || !Array.isArray(d.history) || !d.history.length) return null;
  const hist = [...d.history].sort((a, b) => (b.year || 0) - (a.year || 0)).slice(0, maxRows);
  const rows = hist.map((h) => {
    const dps = h.dps != null ? `${String(h.dps).replace(".", ",")} ${CUR_SYM[h.currency] || h.currency || "₽"}` : "—";
    const y = h.yield_pct != null ? `${String(h.yield_pct).replace(".", ",")}%` : "—";
    const p = h.payout_pct != null ? `${String(h.payout_pct).replace(".", ",")}%` : "—";
    // 🔴 paid=false при заполненной сумме — это РЕКОМЕНДОВАННЫЙ, ещё не выплаченный
    // дивиденд (свежий год), а не «пропуск» (аудит: SBER-2025 с суммой и payout
    // показывался «пропуском» — противоречие на виду).
    const status = h.paid === false
      ? (h.dps != null ? "рекомендован, не выплачен" : "пропуск")
      : h.special ? "выплачен (спец.)" : "выплачен";
    return `<tr><td>${h.year != null ? h.year : "—"}</td><td class="num">${escapeHtml(dps)}</td><td class="num">${escapeHtml(y)}</td><td class="num">${escapeHtml(p)}</td><td>${status}</td></tr>`;
  }).join("");
  return `<table><thead><tr><th>Год</th><th class="num">На акцию</th><th class="num">Доходность*</th><th class="num">Payout</th><th>Статус</th></tr></thead><tbody>${rows}</tbody></table>
<p class="tag">* Доходность приведена к цене на дату обновления разбора — для сопоставимости
истории между годами; текущая доходность считается живьём в приложении.</p>`;
}

/* --------------------------- страницы --------------------------- */

const TAB_PAGES = [
  {
    slug: "business", appTab: "business", label: "Бизнес-модель",
    has: (c) => Boolean(c.businessMd),
    title: (c) => `Бизнес-модель ${titleName(c)} (${c.ticker}): на чём зарабатывает | Basis`,
    // Префикс с тикером — гарантия уникальности description даже когда md-текст
    // общий у пары обычка/преф (SBER/SBERP) или у похожих компаний.
    desc: (c) => truncate(`Бизнес-модель ${c.short} (${c.ticker}): ${mdFirstSentence(c.businessMd, 300) ||
      "источники выручки, экономика, факторы и риски — разбор Basis."}`, 200),
    content: (c) => mdExcerpt(c.businessMd, 3500),
  },
  {
    slug: "finance", appTab: "finance", label: "Финансы и оценка",
    has: (c) => finRows(c).length > 0,
    title: (c) => `Финансы ${titleName(c)} (${c.ticker}): выручка, прибыль, оценка | Basis`,
    desc: (c) => {
      const np = lastValue(c, "net_profit");
      const rv = lastValue(c, c.profile === "bank" ? "net_interest_income" : "revenue");
      const bits = [];
      if (rv) bits.push(`${c.profile === "bank" ? "чистые процентные доходы" : "выручка"} ${rv.year}: ${fmtMoney(rv.value, c.unit, c.currency)}`);
      if (np) bits.push(`${np.value < 0 ? "чистый убыток" : "чистая прибыль"}: ${fmtMoney(Math.abs(np.value), c.unit, c.currency)}`);
      return truncate(`Финансовые показатели ${c.short} (${c.ticker}) по годам${bits.length ? " — " + bits.join(", ") : ""}. Отчётность, динамика, подход к справедливой цене — Basis.`, 200);
    },
    content: (c) => {
      const t = finTableHtml(c, 6);
      if (!t) return null;
      const std = c.standard ? ` по стандарту ${escapeHtml(c.standard)}` : "";
      return `<p>Ключевые статьи отчётности ${escapeHtml(c.short)}${std} за последние годы.
Полная детализация (баланс, денежные потоки, мультипликаторы против сектора, нормализованные
показатели и расчёт справедливой цены несколькими методами) — во вкладке «Финансы и оценка»
карточки компании.</p>${t}
<p>Справедливая цена в Basis считается живьём от текущей котировки маршрутом методов по
сектору (DCF, исторические мультипликаторы, относительная оценка и др.) и показывается
с явными допущениями каждого метода — это оценка, не факт и не рекомендация.</p>`;
    },
  },
  {
    slug: "dividends", appTab: "governance", label: "Дивиденды",
    has: (c) => Boolean(c.dividends && ((c.dividends.history || []).length || c.dividends.policy_text)),
    title: (c) => `Дивиденды ${titleName(c)} (${c.ticker}): история и политика выплат | Basis`,
    desc: (c) => {
      const d = c.dividends || {};
      const yrs = (d.history || []).map((h) => h.year).filter(Boolean);
      const span = yrs.length ? ` История выплат ${Math.min(...yrs)}–${Math.max(...yrs)}.` : "";
      return truncate(`Дивиденды ${c.short} (${c.ticker}): ${d.policy_text ? strip(d.policy_text) : "политика и история выплат"}${span}`, 200);
    },
    content: (c) => {
      const d = c.dividends;
      const parts = [];
      if (d.policy_text) parts.push(`<h2>Дивидендная политика</h2><p>${escapeHtml(strip(d.policy_text))}</p>`);
      if (d.policy_conditions) parts.push(`<p class="sub">${escapeHtml(strip(d.policy_conditions))}</p>`);
      const t = dividendsTableHtml(c, 9);
      if (t) parts.push(`<h2>История выплат</h2>${t}`);
      return parts.length ? parts.join("\n") : null;
    },
  },
  {
    slug: "macro", appTab: "macro", label: "Макроэкономика",
    has: (c) => Boolean(c.macroMd),
    title: (c) => `${titleName(c)} (${c.ticker}) и макро: ставка, инфляция, курс | Basis`,
    desc: (c) => truncate(`Макро и ${c.short} (${c.ticker}): ${mdFirstSentence(c.macroMd, 300) ||
      "как ключевая ставка, инфляция и курс рубля влияют на компанию — разбор Basis."}`, 200),
    content: (c) => mdExcerpt(c.macroMd, 3000),
  },
  {
    slug: "geo", appTab: "geo", label: "Геополитика",
    has: (c) => Boolean(c.geoMd),
    title: (c) => `Геополитические риски ${titleName(c)} (${c.ticker}) | Basis`,
    desc: (c) => truncate(`Геополитика и ${c.short} (${c.ticker}): ${mdFirstSentence(c.geoMd, 300) ||
      "санкционная экспозиция, сценарии, влияние на оценку — разбор Basis."}`, 200),
    content: (c) => mdExcerpt(c.geoMd, 3000),
  },
];


// Имя для <title>: длинные официальные названия режем по слову (~40 симв.),
// иначе title уезжает за 75 символов (аудит tech-seo: максимум был 126).
function titleName(c) { return truncate(c.short, 40); }

function hubDescription(c) {
  const bits = [];
  const rv = lastValue(c, c.profile === "bank" ? "net_interest_income" : "revenue");
  const np = lastValue(c, "net_profit");
  if (rv) bits.push(`${c.profile === "bank" ? "процентные доходы" : "выручка"} ${rv.year}: ${fmtMoney(rv.value, c.unit, c.currency)}`);
  if (np) bits.push(`${np.value < 0 ? "чистый убыток" : "чистая прибыль"}: ${fmtMoney(Math.abs(np.value), c.unit, c.currency)}`);
  const nums = bits.length ? ` ${bits.join(", ").replace(/^./, (ch) => ch.toUpperCase())}.` : "";
  return truncate(
    `${c.short} (${c.ticker}), сектор «${c.sectorFull || c.sector}»: бизнес-модель, финансы, дивиденды, справедливая цена, макро- и геополитические риски.${nums} Независимый разбор Basis.`,
    200
  );
}

function hubPage(c, tabsWritten, sectorPeers) {
  const title = `${titleName(c)} (${c.ticker}) — аналитика: финансы, дивиденды, оценка | Basis`;
  const desc = hubDescription(c);
  const parts = [];
  parts.push(`<p class="tag">${escapeHtml(c.sectorFull || c.sector)} · MOEX: ${c.ticker}</p>`);
  parts.push(`<h1>${escapeHtml(c.short)} <span style="color:var(--faint)">(${c.ticker})</span></h1>`);
  if (c.name !== c.short) parts.push(`<p class="sub">${escapeHtml(c.name)}</p>`);

  // Суть бизнеса — первый абзац прозы из business_model.md
  const lead = mdFirstSentence(c.businessMd, 400);
  if (lead) parts.push(`<h2>Суть бизнеса</h2><p>${escapeHtml(lead)}</p>`);

  // Ключевые факты. 🔴 Значения в части financials.json жёстко обрезаны на 120
  // символах (артефакт экспорта данных, 96 ячеек в 78 файлах по аудиту) — рвём
  // по границе слова и ставим многоточие, чтобы обрубок не выглядел как баг.
  const smoothVal = (v) => {
    const s = strip(v);
    if (s.length < 118 || /[.!?)»%]$/.test(s)) return s;
    const cut = s.slice(0, 112);
    return cut.slice(0, Math.max(cut.lastIndexOf(" "), 80)).replace(/[,;:\s]+$/, "") + "…";
  };
  const kf = (c.fin.key_facts || []).filter((x) => x.label && x.value);
  if (kf.length) {
    parts.push(`<h2>Ключевые факты</h2><table><tbody>${kf.map((x) =>
      `<tr><th>${escapeHtml(strip(x.label))}</th><td>${escapeHtml(smoothVal(x.value))}</td></tr>`).join("")}</tbody></table>`);
  }

  const ft = finTableHtml(c, 5);
  if (ft) parts.push(`<h2>Финансовые показатели</h2>${ft}`);

  const dt = dividendsTableHtml(c, 5);
  if (dt) {
    const pol = c.dividends && c.dividends.policy_text ? `<p>${escapeHtml(strip(c.dividends.policy_text))}</p>` : "";
    parts.push(`<h2>Дивиденды</h2>${pol}${dt}`);
  }

  // Разделы разбора → отдельные страницы + deep-link в приложение
  if (tabsWritten.length) {
    parts.push(`<h2>Разделы разбора</h2><div class="grid">${tabsWritten.map((t) =>
      `<a class="chip" href="/company/${c.ticker}/${t.slug}/">${escapeHtml(t.label)}</a>`).join("")}</div>`);
  }

  parts.push(`<a class="cta" href="/?company=${c.ticker}">Открыть полный разбор ${escapeHtml(c.short)} в Basis →</a>`);

  if (sectorPeers.length) {
    parts.push(`<h2>Похожие компании — ${escapeHtml(c.sector)}</h2><div class="grid">${sectorPeers.map((p) =>
      `<a class="chip" href="/company/${p.ticker}/">${escapeHtml(p.short)} (${p.ticker})</a>`).join("")}</div>`);
  }

  return pageShell({
    title, desc,
    canonicalPath: `/company/${c.ticker}/`,
    breadcrumbs: [
      { label: "Basis", href: "/" },
      { label: "Компании", href: "/company/" },
      { label: `${c.short} (${c.ticker})` },
    ],
    bodyHtml: parts.join("\n"),
    jsonLd: corpLd(c),
  });
}

function tabPage(c, spec, contentHtml, tabsWritten) {
  const others = tabsWritten.filter((t) => t.slug !== spec.slug);
  const othersHtml = others.length
    ? `<h2>Другие разделы разбора</h2><div class="grid">${others.map((t) =>
        `<a class="chip" href="/company/${c.ticker}/${t.slug}/">${escapeHtml(t.label)}</a>`).join("")}</div>`
    : "";
  const body = `
<p class="tag">${escapeHtml(c.sectorFull || c.sector)} · MOEX: ${c.ticker}</p>
<h1>${escapeHtml(spec.label)}: ${escapeHtml(c.short)} <span style="color:var(--faint)">(${c.ticker})</span></h1>
${contentHtml}
<a class="cta" href="/?company=${c.ticker}&amp;tab=${spec.appTab}">Продолжить в приложении: ${escapeHtml(spec.label.toLowerCase())} ${escapeHtml(c.short)} →</a>
${othersHtml}`;
  return pageShell({
    title: spec.title(c),
    desc: spec.desc(c),
    canonicalPath: `/company/${c.ticker}/${spec.slug}/`,
    breadcrumbs: [
      { label: "Basis", href: "/" },
      { label: "Компании", href: "/company/" },
      { label: `${c.short} (${c.ticker})`, href: `/company/${c.ticker}/` },
      { label: spec.label },
    ],
    bodyHtml: body,
    jsonLd: corpLd(c),
  });
}

function indexPage(companies) {
  const bySector = {};
  for (const c of companies) (bySector[c.sector] = bySector[c.sector] || []).push(c);
  const sectors = Object.keys(bySector).sort((a, b) => bySector[b].length - bySector[a].length);
  const body = `
<h1>Аналитика компаний Московской биржи</h1>
<p class="sub">${companies.length} независимых разборов: бизнес-модель, финансы и справедливая
цена, дивиденды, корпоративное управление, макро- и геополитические риски по каждой бумаге.</p>
${sectors.map((s) => `<h2>${escapeHtml(s)} <span style="color:var(--faint);font-size:14px">· ${bySector[s].length}</span></h2>
<div class="grid">${bySector[s]
    .sort((a, b) => a.short.localeCompare(b.short, "ru"))
    .map((c) => `<a class="chip" href="/company/${c.ticker}/">${escapeHtml(c.short)} (${c.ticker})</a>`).join("")}</div>`).join("\n")}
<a class="cta" href="/">Открыть приложение Basis →</a>`;
  return pageShell({
    title: `Аналитика по ${companies.length} компаниям Мосбиржи — разборы Basis`,
    desc: `Каталог независимых разборов Basis: ${companies.length} компаний Московской биржи по секторам — бизнес-модель, финансы, дивиденды, справедливая цена, риски. Без сигналов «купить/продать».`,
    canonicalPath: "/company/",
    breadcrumbs: [{ label: "Basis", href: "/" }, { label: "Компании" }],
    bodyHtml: body,
    jsonLd: [],
  });
}

/* --------------------------- sitemap --------------------------- */

function writeSitemap(urls) {
  const xml = `<?xml version="1.0" encoding="UTF-8"?>
<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">
${urls.map((u) => `  <url><loc>${u.loc}</loc><lastmod>${_TODAY}</lastmod><changefreq>${u.freq}</changefreq><priority>${u.pri}</priority></url>`).join("\n")}
</urlset>
`;
  fs.writeFileSync(path.join(_BUILD_DIR, "sitemap.xml"), xml, "utf8");
}

/* ----------------------------- main ----------------------------- */

function main() {
  if (!fs.existsSync(_COMPANIES_DIR) || !fs.statSync(_COMPANIES_DIR).isDirectory()) {
    console.log("companies dir не найден — пропуск");
    return;
  }
  const names = loadNames();
  const companies = [];
  const skipped = [];
  for (const ticker of fs.readdirSync(_COMPANIES_DIR).sort()) {
    if (ticker.startsWith("_") || ticker === "ocr2025") continue;
    const full = path.join(_COMPANIES_DIR, ticker);
    if (!fs.statSync(full).isDirectory()) continue;
    const c = loadCompany(ticker, names);
    if (c) companies.push(c); else skipped.push(ticker);
  }

  const urls = [
    { loc: `${_SITE}/`, freq: "daily", pri: "1.0" },
    { loc: `${_SITE}/company/`, freq: "weekly", pri: "0.9" },
  ];
  let tabPagesCount = 0;

  for (const c of companies) {
    // какие таб-страницы реально есть у этой компании
    const tabsWritten = [];
    const rendered = [];
    for (const spec of TAB_PAGES) {
      if (!spec.has(c)) continue;
      const content = spec.content(c);
      if (!content) continue;
      tabsWritten.push({ slug: spec.slug, label: spec.label });
      rendered.push([spec, content]);
    }

    // соседи по сектору (до 8, кроме себя)
    const peers = companies
      .filter((p) => p.sector === c.sector && p.ticker !== c.ticker)
      .slice(0, 8);

    const hubDir = path.join(_BUILD_DIR, "company", c.ticker);
    fs.mkdirSync(hubDir, { recursive: true });
    fs.writeFileSync(path.join(hubDir, "index.html"), hubPage(c, tabsWritten, peers), "utf8");
    urls.push({ loc: `${_SITE}/company/${c.ticker}/`, freq: "weekly", pri: "0.8" });

    for (const [spec, content] of rendered) {
      const dir = path.join(hubDir, spec.slug);
      fs.mkdirSync(dir, { recursive: true });
      fs.writeFileSync(path.join(dir, "index.html"), tabPage(c, spec, content, tabsWritten), "utf8");
      urls.push({ loc: `${_SITE}/company/${c.ticker}/${spec.slug}/`, freq: "monthly", pri: "0.6" });
      tabPagesCount++;
    }
  }

  fs.writeFileSync(path.join(_BUILD_DIR, "company", "index.html"), indexPage(companies), "utf8");
  writeSitemap(urls);
  console.log(`SEO-страницы: ${companies.length} хабов + ${tabPagesCount} страниц разделов + каталог; sitemap.xml — ${urls.length} URL; пропущено (нет financials.json): ${skipped.length}`);
  if (skipped.length) console.log("пропущены:", skipped.slice(0, 20).join(", "), skipped.length > 20 ? "..." : "");
}

main();

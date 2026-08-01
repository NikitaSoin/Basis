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
 * v3 (2026-07-27, SEO-задача №1 владельца — «находить по задачам, не по названию»):
 *   + интент-лендинги разделов (/analiz-portfelya/, /skrining-aktsiy/, /kak-vybrat-ofz/
 *     и др.) — тексты в scripts/seo-landings-content.js, рендер — landingPage();
 *   + тайтлы карточек под поисковый интент («анализ акций, справедливая цена X ₽»,
 *     «разбор отчётности», «дивиденды {год}», «риски») — canonical/структура не тронуты;
 *   + честный lastmod в sitemap: дата последнего коммита данных компании (git),
 *     фолбэк — mtime файлов; раньше все 1577 URL получали дату сборки (аудит п.5).
 *
 * ПОЧЕМУ Node, а не Python: билд-окружение Timeweb выполняет `npm run build`,
 * там гарантирован только Node (python3 нет — падало на бою). Только built-in
 * модули. Запускается ПОСЛЕ `craco build` (см. package.json), пишет в build/.
 */
"use strict";
const fs = require("fs");
const path = require("path");
const { execSync } = require("child_process");
// Два файла текстов: базовый (портфель/скрининг/оценка/облигации) и добавленный
// 2026-07-30 по разделам Обозревателя и классам активов — владелец: «чтобы все
// остальные блоки на платформе имели свои SEO-страницы».
const { metrikaSnippet } = require("./metrika");

const LANDINGS = [...require("./seo-landings-content"), ...require("./seo-landings-observer")];

// Разборы вышедшей отчётности (снапшот с прод-API, scripts/fetch-seo-snapshots.js).
// Владелец 2026-07-30: «человек вбивает "отчет ozon" — надо, чтобы находил у нас».
// Отдельная страница на компанию, а не пункт внутри «Финансов»: запрос «отчёт <компания>»
// самостоятельный и очень частый, и по нему должна находиться страница ИМЕННО про отчёт.
// Адрес API для ЖИВОЙ подгрузки свежего разбора на статической странице. Берётся из
// той же переменной, что и у приложения (REACT_APP_API_URL), с боевым значением по
// умолчанию — статика собирается и вне окружения приложения.
const API_BASE = process.env.REACT_APP_API_URL || process.env.BASIS_API
  || "https://nikitasoin-basis-a772.twc1.net";

let EARNINGS_BY_TICKER = {};
try {
  const rows = require("./data/earnings-snapshot.json");
  const list = Array.isArray(rows) ? rows : (rows.rows || rows.reports || []);
  for (const r of list) if (r && r.ticker) EARNINGS_BY_TICKER[String(r.ticker).toUpperCase()] = r;
} catch { EARNINGS_BY_TICKER = {}; }

const _ROOT = path.resolve(__dirname, "..", "..", "..");
const _COMPANIES_DIR = path.join(_ROOT, "backend", "companies");
const _RATES_CSV = path.join(_ROOT, "rates.csv");
const _BUILD_DIR = path.join(__dirname, "..", "build");
const _SITE = "https://inbasis.ru";
const _TODAY = new Date().toISOString().slice(0, 10);
const _YEAR = new Date().getFullYear();

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
  // Развернуть кавычки «...», если имя целиком в них. НО у составных имён вида
  // «НК «Роснефть» внутренняя кавычка своя: слепое разворачивание давало «НК «Роснефть
  // с потерянной закрывающей — это видно в тексте страниц. Разворачиваем, только если
  // внутри кавычки сбалансированы; иначе снимаем лишь внешнюю открывающую.
  const m = s.match(/^[«"']+(.+?)[»"']+$/);
  if (m) {
    const inner = m[1];
    const balanced = (inner.match(/«/g) || []).length === (inner.match(/»/g) || []).length;
    s = balanced ? inner : s.replace(/^[«"']/, "");
  }
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

/* --------- честный lastmod (аудит 2026-07-26 п.5: «sitemap врёт») --------- */
// Дата последнего коммита каждого файла backend/companies — ОДНИМ git-вызовом
// (0,2 с локально). mtime как единственный источник не годится: на билд-окружении
// Timeweb файлы получают mtime момента чекаута, т.е. снова «дата сборки». Если
// git недоступен/история неполная (shallow clone) — честно деградируем к mtime.
function loadGitFileDates() {
  try {
    const out = execSync("git log --format=%x01%cs --name-only -- backend/companies", {
      cwd: _ROOT, encoding: "utf8", maxBuffer: 128 * 1024 * 1024, stdio: ["ignore", "pipe", "ignore"],
    });
    const dates = {};
    let cur = null;
    for (const line of out.split("\n")) {
      if (line.charCodeAt(0) === 1) { cur = line.slice(1).trim(); continue; }
      const f = line.trim();
      // git log идёт от новых коммитов к старым — первая встреча файла = последний коммит
      if (f && cur && !(f in dates)) dates[f] = cur;
    }
    return Object.keys(dates).length ? dates : null;
  } catch { return null; }
}

const COMPANY_SRC_FILES = ["financials.json", "governance.json", "business_model.md", "macro_summary.md", "geo_summary.md"];
// max(дата последнего изменения) по файлам-источникам страниц компании → YYYY-MM-DD | null.
function companyLastmod(ticker, gitDates) {
  let latest = null;
  for (const f of COMPANY_SRC_FILES) {
    let d = gitDates ? gitDates[`backend/companies/${ticker}/${f}`] : null;
    if (!d) {
      try { d = fs.statSync(path.join(_COMPANIES_DIR, ticker, f)).mtime.toISOString().slice(0, 10); }
      catch { d = null; }
    }
    if (d && (!latest || d > latest)) latest = d;
  }
  // будущих дат и дат позже сборки быть не должно (грязный mtime) — зажимаем
  return latest && latest < _TODAY ? latest : _TODAY;
}

function fileLastmod(p) {
  try { return fs.statSync(p).mtime.toISOString().slice(0, 10); } catch { return _TODAY; }
}

// Пути реального бандла приложения (для progressive takeover, см. pageShell) —
// craco build уже отработал (см. package.json: build = craco build && this script),
// asset-manifest.json существует. files["main.js"/"main.css"] уже с ведущим "/"
// (в отличие от entrypoints[] — там пути без слэша, легко словить 404 на вложенных
// /company/T/finance/ путях, если взять оттуда).
function loadAppAssets() {
  const manifest = readJson(path.join(_BUILD_DIR, "asset-manifest.json"));
  const js = manifest && manifest.files && manifest.files["main.js"];
  if (!js) return null;
  const css = manifest.files["main.css"] || null;
  return { js, css };
}

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
/* 🔴 Ограничения ширины — на КОНТЕЙНЕР статики, а не на body (владелец, 2026-07-30:
   «открылось всё на полэкрана»). Раньше body жёстко зажимался в 760px, и когда поверх
   статики монтировалось приложение, оно наследовало эту ширину: интерфейс платформы
   ужимался в узкую колонку по центру, справа оставалась пустота. Статику мы прячем, а
   стиль body оставался жить. */
body{font-family:-apple-system,'Segoe UI',Roboto,sans-serif;background:var(--paper);color:var(--ink);
     margin:0;padding:0;line-height:1.55}
#seo-static{max-width:760px;margin:0 auto;padding:32px 20px 60px}
/* ЭКРАН ЗАГРУЗКИ вместо мелькания контента (владелец, 2026-07-30: «хуже когда
   открывается одно, потом через секунду пропадает и появляется новое — лучше просто
   пустой экран прогрузки»). Бандл ~3 МБ, до старта приложения проходит 2–4 с, и всё это
   время человек читал статическую версию, которая затем подменялась платформой.
   🔴 Сам HTML статики НЕ трогаем — он остаётся в разметке для поисковых роботов и для
   браузеров без JS. Экран ставится СКРИПТОМ поверх: робот, который не исполняет JS,
   видит обычную страницу с контентом; человек видит спокойную загрузку. Это не подмена
   контента — тот же документ, просто визуально перекрыт на время старта. */
#seo-boot{position:fixed;inset:0;z-index:99999;background:var(--paper);
  display:flex;flex-direction:column;align-items:center;justify-content:center;gap:18px}
#seo-boot .b-mark{font:700 26px/1 Georgia,'Times New Roman',serif;color:var(--copper);letter-spacing:.02em}
#seo-boot .b-cap{font:400 13px/1.5 -apple-system,'Segoe UI',Roboto,sans-serif;color:var(--faint)}
#seo-boot .b-bar{width:180px;height:3px;border-radius:2px;background:var(--line);overflow:hidden}
#seo-boot .b-bar i{display:block;width:40%;height:100%;background:var(--copper)}
@media (prefers-reduced-motion:no-preference){#seo-boot .b-bar i{animation:bootSlide 1.1s ease-in-out infinite}}
@keyframes bootSlide{0%{transform:translateX(-100%)}100%{transform:translateX(350%)}}
@media (prefers-color-scheme:dark){#seo-boot{background:#14110E}#seo-boot .b-cap{color:#8A8072}}
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

// Progressive takeover: статика остаётся ПЕРВЫМ и единственным контентом, пока
// живое приложение реально не отрисовало карточку с данными — НЕ прячем её сразу
// синхронным скриптом (в отличие от anti-FOUC темы в public/index.html), потому
// что там cost=0 при отказе, а здесь отказ (бандл не догрузился/не смонтировался)
// без этой страховки означал бы пустой экран — регресс хуже текущей заглушки.
// Слушатель регистрируется СИНХРОННО (без defer) до того, как бандл вообще начнёт
// качаться, поэтому гонка «событие прилетело раньше подписки» невозможна.
// Бот без JS: див #seo-static просто остаётся видимым как обычный HTML — контент
// для такого бота не меняется НИ БАЙТОМ относительно прежней чистой статики.
function appMountHtml(assets) {
  if (!assets || !assets.js) return "";
  const css = assets.css ? `<link rel="stylesheet" href="${assets.css}">` : "";
  return `
<div id="root"></div>
<script>
// Экран загрузки ставим СКРИПТОМ (не в разметке): роботы без исполнения JS получают
// страницу с контентом как раньше, человек — спокойный экран вместо мелькания.
(function () {
  var b = document.createElement("div");
  b.id = "seo-boot";
  b.innerHTML = '<div class="b-mark">Basis</div>'
    + '<div class="b-bar"><i></i></div>'
    + '<div class="b-cap">Открываем разбор…</div>';
  document.body.appendChild(b);
  // Страховка: если приложение не стартовало за 12 с (упал бандл, нет сети), убираем
  // экран и показываем статику — она полноценная, лучше чем бесконечная загрузка.
  setTimeout(function () { var x = document.getElementById("seo-boot"); if (x) x.remove(); }, 12000);
})();
["basis:company-ready", "basis:app-ready"].forEach(function (evt) {
window.addEventListener(evt, function () {
  var el = document.getElementById("seo-static");
  if (el) el.remove();          // не display:none — убираем из потока совсем
  var ld = document.getElementById("seo-boot");
  if (ld) ld.remove();
  // Подчищаем оформление статики: у приложения своя тема (в т.ч. тёмная), а бежевый
  // фон и системный шрифт статической страницы иначе просвечивают сквозь неё.
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

const DEFAULT_NOTE = `Basis — аналитический слой, не брокер и не даёт сигналов
«купить/продать». Числа на этой странице — из годовой отчётности на дату последнего
обновления разбора; живые показатели (цена, мультипликаторы, апсайд к справедливой цене)
считаются в приложении. Материал не является индивидуальной инвестиционной рекомендацией.`;

function pageShell({ title, desc, canonicalPath, breadcrumbs, bodyHtml, jsonLd, assets, note }) {
  const url = _SITE + canonicalPath;
  const crumbsHtml = breadcrumbs
    .map((b, i) => (i < breadcrumbs.length - 1 && b.href ? `<a href="${b.href}">${escapeHtml(b.label)}</a>` : escapeHtml(b.label)))
    .join(" → ");
  // 🔴 Организация и сайт — НА КАЖДОЙ статической странице, а не только в index.html
  // SPA-оболочки. Именно статические страницы поиск и индексирует; до 2026-07-31 в них
  // был только BreadcrumbList, то есть сущности «кто это вообще» у проиндексированных
  // страниц не было вовсе. Рекомендация Вебмастера «настроена ли микроразметка» — про это.
  // SearchAction — то, из чего Яндекс и Google собирают строку поиска по сайту в выдаче
  // и опираются при формировании быстрых ссылок.
  const ld = {
    "@context": "https://schema.org",
    "@graph": [
      {
        "@type": "Organization",
        "@id": `${_SITE}/#org`,
        name: "Basis",
        url: `${_SITE}/`,
        logo: `${_SITE}/icon-512.png`,
        description: "Аналитический слой и «второе мнение» для частного инвестора на "
          + "российском рынке. Не брокер, без сигналов «купить/продать».",
      },
      {
        "@type": "WebSite",
        "@id": `${_SITE}/#site`,
        name: "Basis",
        url: `${_SITE}/`,
        inLanguage: "ru-RU",
        publisher: { "@id": `${_SITE}/#org` },
        potentialAction: {
          "@type": "SearchAction",
          target: { "@type": "EntryPoint", urlTemplate: `${_SITE}/?q={search_term_string}` },
          "query-input": "required name=search_term_string",
        },
      },
      {
        "@type": "WebPage",
        "@id": `${url}#page`,
        url,
        name: title,
        description: desc,
        inLanguage: "ru-RU",
        isPartOf: { "@id": `${_SITE}/#site` },
        breadcrumb: { "@id": `${url}#crumbs` },
      },
      {
        "@type": "BreadcrumbList",
        "@id": `${url}#crumbs`,
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
${metrikaSnippet()}
<style>${CSS}</style>
</head>
<body>
<div id="seo-static">
<nav class="crumbs">${crumbsHtml}</nav>
${bodyHtml}
<p class="note">${note || DEFAULT_NOTE}</p>
</div>${appMountHtml(assets)}
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

// 🔴 maxYears ОБЯЗАН иметь значение по умолчанию: без него Math.min(undefined, 10)
// даёт NaN, диапазон колонок получается пустым, и таблица рендерится с единственным
// столбцом «Показатель» — названия строк без единого числа. Именно так на 262 страницах
// разбора отчётности годовая таблица месяцами стояла пустой: ошибки нет, страница
// собирается, просто данных в ней нет (нашлось 2026-07-31 при проверке «мсфо <компания>
// 2025» — страница весила 209 слов вместо ожидаемых 400+).
function finTableHtml(c, maxYears = 6) {
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

// Заполняется в main() из снимка календаря: тикер → ближайшая объявленная выплата.
let DIVIDEND_CALENDAR = {};

// Дата вида 2026-08-06 → «6 августа 2026». Для читателя, а не для машины.
function ruDate(iso) {
  if (!iso) return null;
  const d = new Date(iso);
  if (isNaN(d)) return null;
  return d.toLocaleDateString("ru-RU", { day: "numeric", month: "long", year: "numeric" })
    .replace(/\s*г\.\s*$/, "");
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

const esc = (v) => escapeHtml(String(v == null ? "" : v));

// Итог года словами: что произошло с выручкой и прибылью, какова долговая нагрузка.
// ЗАЧЕМ: страницы разбора весили 192 слова медианой — это «тонкая» страница, поиск
// такие не любит. Все нужные числа уже лежат в financials.json, их достаточно связать
// в текст. Ничего не досочиняем: только то, что прямо следует из отчётности.
function annualSummaryHtml(c) {
  const yrs = c.years || [];
  if (yrs.length < 2) return "";
  const isBank = c.profile === "bank";
  const pnl = isBank ? (c.fin.bank_pnl || {}) : (c.fin.income_statement || {});
  const at = (arr, i) => (Array.isArray(arr) && typeof arr[i] === "number" ? arr[i] : null);
  const li = yrs.length - 1, pi = yrs.length - 2;
  const money = (v) => fmtMoney(v, c.unit, c.currency);
  const chg = (now, was) => (now != null && was != null && was !== 0
    ? Math.round((now / Math.abs(was) - 1) * 100) : null);
  // Род и число согласуем явно: «доходы вырос» и «выручка вырос» одинаково безграмотны.
  const phrase = (label, arr, form) => {
    const now = at(arr, li), was = at(arr, pi);
    if (now == null) return null;
    const V = { f: ["выросла", "снизилась"], m: ["вырос", "снизился"], p: ["выросли", "снизились"] }[form];
    // 🔴 Смена знака: «прибыль снизилась на 225%» — бессмыслица. Когда прибыль уходит в
    // убыток (или выходит из него), процент не считаем, а говорим словами.
    if (was != null && now < 0 && was > 0) {
      return `${label} за ${yrs[li]} — убыток ${money(Math.abs(now))} против прибыли ${money(was)} годом ранее`;
    }
    if (was != null && now > 0 && was < 0) {
      return `${label} за ${yrs[li]} — ${money(now)} против убытка ${money(Math.abs(was))} годом ранее`;
    }
    // Оба года в минусе: процент к отрицательной базе тоже вводит в заблуждение —
    // у Мечела убыток УГЛУБИЛСЯ, а выходило «прибыль снизилась на 312%».
    if (was != null && now < 0 && was < 0) {
      const deeper = Math.abs(now) > Math.abs(was);
      return `${label} за ${yrs[li]} — убыток ${money(Math.abs(now))}, он ${
        deeper ? "углубился" : "сократился"} по сравнению с ${money(Math.abs(was))} годом ранее`;
    }
    const d = chg(now, was);
    const dir = d == null || d === 0 ? "" : d > 0 ? ` ${V[0]}` : ` ${V[1]}`;
    return `${label} за ${yrs[li]} — ${money(now)}${d ? `${dir} на ${Math.abs(d)}% к ${yrs[pi]} году` : ""}`;
  };
  const bits = [
    phrase(isBank ? "Чистые процентные доходы" : "Выручка",
      pnl[isBank ? "net_interest_income" : "revenue"], isBank ? "p" : "f"),
    phrase("Чистая прибыль", pnl.net_profit, "f"),
  ].filter(Boolean);
  if (!bits.length) return "";

  // Долговая нагрузка — самое частое «а что с долгом» после выручки и прибыли.
  const nd = at((c.fin.balance_sheet || {}).net_debt, li);
  const ndE = at(((c.fin.balance_sheet || {}).ratios || {}).net_debt_ebitda, li);
  const ebitda = at((c.fin.income_statement || {}).ebitda, li);
  let debt = "";
  if (!isBank && nd != null) {
    debt = ` Чистый долг на конец ${yrs[li]} — ${nd < 0
      ? `отрицательный: денег на счетах больше, чем долга, на ${money(Math.abs(nd))}`
      : money(nd)}`;
    // Отношение к EBITDA печатаем только когда оно осмысленно: при отрицательном долге
    // это «минус ноль целых», при отрицательной EBITDA — вовсе бессмыслица.
    if (ndE != null && nd > 0 && !(typeof ebitda === "number" && ebitda < 0)) {
      debt += `, это ${String(ndE).replace(".", ",")} EBITDA`;
    }
    debt += ".";
  }
  // 🔴 Если в данных стоит anomaly_flag — обязательно объясняем, иначе число вводит в
  // заблуждение. У ЛУКОЙЛа убыток 2025 года — разовое неденежное списание зарубежных
  // активов; без этой строки страница читается как «бизнес рухнул». Раньше таблица не
  // рендерилась вовсе, и такие числа наружу не выходили; теперь выходят — значит,
  // объяснение обязано идти рядом с ними, а не в другой вкладке.
  const note = c.fin.anomaly_flag && c.fin.anomaly_note
    ? `<p class="sub"><b>Важно для понимания цифр.</b> ${escapeHtml(strip(String(c.fin.anomaly_note)))}</p>`
    : "";
  return `<h2>Итоги ${yrs[li]} года</h2><p>${escapeHtml(bits.join(". "))}.${escapeHtml(debt)}
Полная динамика по годам — в таблице ниже, разбор каждой строки —
в <a href="/company/${c.ticker}/finance/">финансах компании</a>.</p>${note}`;
}

// Вечнозелёный блок: под запросы «мсфо сбербанк», «отчет по мсфо что это». Люди ищут
// не только цифры, но и что вообще значит стандарт, по которому они посчитаны.
const HOW_TO_READ_REPORT = `<h2>Как читать отчётность компании</h2>
<p>Компании на Мосбирже публикуют отчётность в двух стандартах, и это разные вещи.
<b>МСФО</b> — международный стандарт: он показывает группу целиком, вместе с дочерними
предприятиями, и ближе к экономической реальности. <b>РСБУ</b> — российский
бухгалтерский стандарт, он считается по юридическому лицу и нужен прежде всего налоговой;
по нему прибыль может сильно отличаться от групповой. Когда речь об инвестиционной
оценке, смотрят МСФО, а РСБУ используют как быстрый промежуточный сигнал — он выходит
раньше.</p>
<p>Квартальный отчёт не сравнивают с предыдущим кварталом напрямую: у большинства
бизнесов есть сезонность, и правильное сравнение — с тем же кварталом прошлого года.
Годовой отчёт важнее квартального: в нём отражены итоговые начисления, переоценки и
резервы, которые внутри года могли распределяться неравномерно.</p>
<p>Наконец, прибыль и деньги — не одно и то же. Прибыль можно начислить, не получив
оплату, поэтому рядом с ней всегда смотрят денежный поток: если прибыль растёт, а
поток нет, стоит разобраться, во что превратилась разница — обычно в дебиторскую
задолженность или запасы.</p>`;

// Разбор отчёта: суть → факты → плюсы → риски → вывод. Ровно то, что уже
// разобрано платформой; ничего не досочиняем и не даём сигналов сделок.
function earningsHtml(c) {
  const e = EARNINGS_BY_TICKER[c.ticker];
  // Каркас страницы — годовая отчётность из financials.json. Она есть всегда и не
  // зависит от того, вышел ли свежий отчёт: страница никогда не бывает пустой, а
  // «тонкие» страницы поиск не любит и может вовсе не индексировать.
  const yearly = finTableHtml(c);
  const liveSlot = `
<div id="live-earnings" data-ticker="${esc(c.ticker)}"></div>
<script>
// Свежий разбор подтягивается ЖИВЬЁМ при открытии страницы. Смысл: адрес существует
// заранее и уже проиндексирован, поэтому новый отчёт не требует новой страницы и не
// ждёт пересборки — он приезжает сюда сам. В HTML при сборке кладётся последний
// известный разбор (для поисковых роботов, которые JS не исполняют), а этот скрипт
// заменяет его свежим, если тот появился позже.
(function () {
  var host = document.getElementById("live-earnings");
  if (!host || !window.fetch) return;
  var api = ${JSON.stringify(API_BASE)};
  var esc = function (v) { return String(v == null ? "" : v).replace(/[&<>"]/g, function (m) {
    return { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[m]; }); };
  fetch(api + "/api/companies/by-ticker/" + host.dataset.ticker + "/earnings/latest")
    .then(function (r) { return r.ok ? r.json() : null; })
    .then(function (d) {
      if (!d || !d.digest) return;
      var snapPeriod = ${JSON.stringify((e && e.period) || "")};
      if (d.period && snapPeriod && String(d.period) === snapPeriod) return; // уже в HTML
      var dg = d.digest, parts = [];
      parts.push('<h2>Свежий отчёт: ' + esc([d.period, d.standard].filter(Boolean).join(" · ")) + '</h2>');
      if (dg.one_liner) parts.push('<p class="lead">' + esc(dg.one_liner) + '</p>');
      if (dg.what_report_showed) parts.push('<p>' + esc(dg.what_report_showed) + '</p>');
      if (dg.summary) parts.push('<p>' + esc(dg.summary) + '</p>');
      host.innerHTML = parts.join("");
    })
    .catch(function () { /* нет сети — остаётся то, что в HTML */ });
})();
</script>`;

  if (!e) {
    // Разбора в снапшоте нет — страница живёт на годовой отчётности и живой подгрузке.
    return [
      `<p class="sub">Свежий разбор отчётности появляется здесь автоматически, как только компания публикует отчёт.</p>`,
      annualSummaryHtml(c),
      yearly,
      liveSlot,
    ].filter(Boolean).join("\n");
  }
  const list = (title, arr) => {
    const items = (Array.isArray(arr) ? arr : []).filter(Boolean).slice(0, 6);
    if (!items.length) return "";
    return `<h2>${esc(title)}</h2><ul>${items.map((x) => `<li>${esc(typeof x === "object" ? (x.text || x.title || JSON.stringify(x)) : x)}</li>`).join("")}</ul>`;
  };
  const head = [e.period, e.standard].filter(Boolean).join(" · ");
  const parts = [];
  parts.push(`<p class="tag">${esc(head)}${e.published_at ? " · опубликован " + esc(e.published_at) : ""}</p>`);
  if (e.one_liner) parts.push(`<p class="lead">${esc(e.one_liner)}</p>`);
  parts.push(list("Что показал отчёт", e.facts));
  parts.push(list("Сильные стороны", e.positives));
  parts.push(list("Риски и слабые места", e.risks));
  if (e.conclusion) parts.push(`<h2>Вывод</h2><p>${esc(e.conclusion)}</p>`);
  if (e.market_context) parts.push(`<h2>Контекст рынка</h2><p>${esc(e.market_context)}</p>`);
  if (e.watch_next) parts.push(`<h2>За чем следить дальше</h2><p>${esc(e.watch_next)}</p>`);
  parts.push(`<p class="sub">Ознакомительный разбор события «вышел отчёт». Не является индивидуальной инвестиционной рекомендацией.</p>`);
  parts.push(annualSummaryHtml(c));
  parts.push(yearly);
  parts.push(HOW_TO_READ_REPORT);
  parts.push(liveSlot);
  return parts.filter(Boolean).join("\n");
}

const TAB_PAGES = [
  {
    slug: "otchet", appTab: "finance", label: "Разбор отчёта",
    // 🔴 Страница есть у КАЖДОЙ компании, а не только у тех, чей разбор попал в снапшот
    // (владелец 2026-07-31: «нельзя заранее чтобы у нас были страницы — туда закидываем
    // и выкидываем»). Так новый отчёт не требует НОВОЙ страницы: адрес уже существует и
    // проиндексирован, в него просто приезжает свежий разбор. Пустой страница не бывает —
    // годовая отчётность из financials.json есть у всех 264, она и составляет каркас.
    has: (c) => finRows(c).length > 0 || Boolean(EARNINGS_BY_TICKER[c.ticker]),
    // Тайтл НЕ зависит от свежести КВАРТАЛЬНОГО разбора: период в заголовке означал бы,
    // что при каждом новом отчёте меняется тайтл уже проиндексированной страницы —
    // поиск такое не любит. Но ГОД годовой отчётности ставим: он меняется раз в год, а
    // спрос его требует прямо («отчет сбербанка за 2025 год», «мсфо сбербанк 2025» —
    // замер подсказок 2026-07-31). Стандарт (МСФО/РСБУ) — оттуда же.
    // Имя-первым: «Отчётность Сбербанк» безграмотно, нужен родительный падеж.
    title: (c) => {
      const yr = c.years && c.years.length ? c.years[c.years.length - 1] : null;
      return `${titleName(c)} (${c.ticker}): отчётность${c.standard ? ` ${c.standard}` : ""}`
        + `${yr ? ` за ${yr} год` : ""} — разбор, выручка, прибыль | Basis`;
    },
    desc: (c) => {
      const e = EARNINGS_BY_TICKER[c.ticker] || {};
      return truncate(e.one_liner
        ? `${e.one_liner} Разбор отчётности ${c.short} (${c.ticker}): факты, сильные стороны, риски — Basis.`
        : `Отчётность ${c.short} (${c.ticker}) по годам: выручка, прибыль, долг и денежный поток. Разборы свежих отчётов — Basis.`, 200);
    },
    content: (c) => earningsHtml(c),
  },
  {
    slug: "business", appTab: "business", label: "Бизнес-модель",
    has: (c) => Boolean(c.businessMd),
    title: (c) => `Бизнес-модель ${titleName(c)} (${c.ticker}): на чём зарабатывает | Basis`,
    // Префикс с тикером — гарантия уникальности description даже когда md-текст
    // общий у пары обычка/преф (SBER/SBERP) или у похожих компаний.
    desc: (c) => truncate(`Бизнес-модель ${c.short} (${c.ticker}): ${mdFirstSentence(c.businessMd, 300) ||
      "источники выручки, экономика, факторы и риски — разбор Basis."}`, 200),
    // Лимит поднят 3500 → 12000 (2026-07-31). Замер по всем компаниям: медиана
    // business_model.md — 10 400 символов, то есть при 3500 текст резался у 98 % и в
    // поиск уходила треть разбора. Страницы выглядели «тонкими» (250–530 слов) при том,
    // что содержания у нас больше, чем у конкурентов в топе — просто оно не доезжало
    // до робота. Это и есть главная причина, почему сайт стоял на девятой странице.
    content: (c) => mdExcerpt(c.businessMd, 12000),
  },
  {
    slug: "finance", appTab: "finance", label: "Финансы и оценка",
    has: (c) => finRows(c).length > 0,
    // Имя-первым (как в хабе): «Разбор отчётности {Имя-в-именительном}» не
    // склоняется автоматически — «Разбор отчётности Сбербанк» безграмотно.
    title: (c) => `${titleName(c)} (${c.ticker}): разбор отчётности — выручка, прибыль, оценка | Basis`,
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
    // Год в тайтле — под массовый запрос «дивиденды X 2026» (аудит п.7); при
    // пересборке в новом году подставится актуальный. Имя-первым — см. finance.
    title: (c) => `${titleName(c)} (${c.ticker}): дивиденды ${_YEAR} — история выплат и политика | Basis`,
    desc: (c) => {
      const d = c.dividends || {};
      const yrs = (d.history || []).map((h) => h.year).filter(Boolean);
      const span = yrs.length ? ` История выплат ${Math.min(...yrs)}–${Math.max(...yrs)}.` : "";
      return truncate(`Дивиденды ${c.short} (${c.ticker}): ${d.policy_text ? strip(d.policy_text) : "политика и история выплат"}${span}`, 200);
    },
    content: (c) => {
      const d = c.dividends;
      const parts = [];
      const hist = [...(d.history || [])].sort((a, b) => (b.year || 0) - (a.year || 0));

      // 1) Ответ сверху: сколько платили в последний раз и платят ли вообще регулярно.
      // Раньше страница начиналась с политики — текста на абзац, из которого главное
      // («платят или нет») приходилось выуживать.
      const lastPaid = hist.find((h) => h.paid !== false && h.dps != null);
      if (lastPaid) {
        const paidYears = hist.filter((h) => h.paid !== false && h.dps != null).length;
        const skipped = hist.filter((h) => h.paid === false && h.dps == null).length;
        parts.push(`<p class="sub">Последняя выплата — <b>${escapeHtml(String(lastPaid.dps).replace(".", ","))} ₽`
          + `</b> на акцию за ${lastPaid.year} год${lastPaid.yield_pct != null
            ? ` (доходность ${escapeHtml(String(lastPaid.yield_pct).replace(".", ","))}% к цене того периода)` : ""}.`
          + ` Дивиденды выплачивались ${paidYears} ${
            plural(paidYears, "год", "года", "лет").split(" ")[1]} из ${hist.length}`
          + `${skipped ? `, в остальные годы выплат не было` : ""}.</p>`);
      } else if (hist.length) {
        parts.push(`<p class="sub">За доступную историю (${hist.length} лет) компания дивиденды `
          + `не платила либо выплаты не подтверждены.</p>`);
      }

      // 2) Ближайшая объявленная выплата — прямой ответ на «когда выплатят» и «отсечка».
      const up = DIVIDEND_CALENDAR[c.ticker];
      if (up && up.amount != null) {
        const rec = ruDate(up.record_date), buy = ruDate(up.buy_by_date);
        parts.push(`<h2>Ближайшая выплата</h2>
<p>Объявлен дивиденд <b>${escapeHtml(String(up.amount).replace(".", ","))} ₽</b> на акцию${
          up.yield_pct != null ? ` — доходность ${escapeHtml(String(up.yield_pct).replace(".", ","))}% к текущей цене` : ""}.
${rec ? `Дата закрытия реестра (отсечка) — ${escapeHtml(rec)}.` : ""}
${buy ? `Чтобы попасть в реестр, бумага должна быть куплена не позднее ${escapeHtml(buy)}` : ""}
${buy ? " — из-за режима расчётов Т+1 покупка в день отсечки права на дивиденд уже не даёт." : ""}
${up.status ? ` Статус: ${escapeHtml(up.status)}.` : ""}</p>
<p class="sub">Данные календаря обновляются автоматически. Полный список ближайших выплат
по рынку — в <a href="/dividendnyy-kalendar/">дивидендном календаре</a>.</p>`);
      }

      if (d.policy_text) parts.push(`<h2>Дивидендная политика</h2><p>${escapeHtml(strip(d.policy_text))}</p>`);
      if (d.policy_conditions) parts.push(`<p class="sub">${escapeHtml(strip(d.policy_conditions))}</p>`);
      const t = dividendsTableHtml(c, 9);
      if (t) parts.push(`<h2>История выплат</h2>${t}`);

      // 3) Регулярность и расхождение обещаний с практикой лежали в данных, но на
      // страницу не выводились — а это ровно то, что отличает «политика есть» от
      // «политике можно верить».
      if (d.regularity_note) parts.push(`<h2>Насколько выплаты регулярны</h2><p>${escapeHtml(strip(d.regularity_note))}</p>`);
      if (d.policy_vs_practice) parts.push(`<h2>Политика и практика</h2><p>${escapeHtml(strip(d.policy_vs_practice))}</p>`);

      // 4) Пояснения по конкретным годам: спецдивиденды, выплаты в долг, пропуски.
      const noted = hist.filter((h) => h.note && h.year).slice(0, 4);
      if (noted.length) {
        parts.push(`<h2>Что стоит за отдельными годами</h2><ul>${
          noted.map((h) => `<li><b>${h.year}</b> — ${escapeHtml(strip(h.note))}</li>`).join("")}</ul>`);
      }
      return parts.length ? parts.join("\n") : null;
    },
  },
  {
    slug: "macro", appTab: "macro", label: "Макроэкономика",
    has: (c) => Boolean(c.macroMd),
    title: (c) => `${titleName(c)} (${c.ticker}) и макро: влияние ставки ЦБ, инфляции, курса — Basis`,
    desc: (c) => truncate(`Макро и ${c.short} (${c.ticker}): ${mdFirstSentence(c.macroMd, 300) ||
      "как ключевая ставка, инфляция и курс рубля влияют на компанию — разбор Basis."}`, 200),
    content: (c) => mdExcerpt(c.macroMd, 6000),   // медиана 3 928 симв — резалось у 97 %
  },
  {
    slug: "geo", appTab: "geo", label: "Геополитика",
    has: (c) => Boolean(c.geoMd),
    title: (c) => `${titleName(c)} (${c.ticker}): риски — геополитика и санкции | Basis`,
    desc: (c) => truncate(`Геополитика и ${c.short} (${c.ticker}): ${mdFirstSentence(c.geoMd, 300) ||
      "санкционная экспозиция, сценарии, влияние на оценку — разбор Basis."}`, 200),
    content: (c) => mdExcerpt(c.geoMd, 7000),     // медиана 5 378 симв — резалось у 100 %
  },
];


// Имя для <title>: длинные официальные названия режем по слову (~40 симв.),
// иначе title уезжает за 75 символов (аудит tech-seo: максимум был 126).
function titleName(c) {
  // Убираем латинский дубль в скобках: у 11 компаний short выглядит как
  // «Озон» (Ozon) / «Группа Позитив» (Positive Technologies), и рядом с тикером
  // получалось «„Озон“ (Ozon) (OZON)» — три раза одно имя, да ещё и съедало лимит
  // тайтла в 60–70 символов. Кавычки-ёлочки тоже снимаем: в поисковой выдаче они
  // визуально дробят название.
  let cleaned = String(c.short || "")
    .replace(/\s*\([A-Za-z][^)]*\)\s*$/, "")
    .replace(/[«»"]/g, "")
    .trim();

  // 🔴 Уточнение в скобках выкидываем ЦЕЛИКОМ, а не режем посередине. Обрезка по
  // символам давала в выдаче «Россети Томск (Томская… (TORS)» и «АКБ РОСДОРБАНК
  // (Российский Дорожный… (RDRB)» — незакрытая скобка читается как сломанная страница
  // (21 карточка с многоточием, из них 13 с оборванной скобкой). Само уточнение в
  // заголовке не нужно: рядом уже стоит тикер, а лимит тайтла 60–70 знаков.
  const withoutParen = cleaned.replace(/\s*\([^)]*\)?\s*$/, "").trim();
  if (withoutParen.length >= 8) cleaned = withoutParen;

  // Если и так длинно — режем ПО СЛОВАМ, чтобы не обрывать слово на середине.
  if (cleaned.length > 40) {
    const words = cleaned.slice(0, 40).split(" ");
    if (words.length > 1) words.pop();
    cleaned = words.join(" ").replace(/[\s,–—-]+$/, "");
  }
  // Последняя гарантия: если после всех обрезок скобка осталась незакрытой (так вышло у
  // ДЭК, ЯТЭК, ДИОД — там короткая аббревиатура перед длинным уточнением, и предыдущее
  // правило уточнение сохранило), отрезаем всё от последней открывающей. Проверять
  // результат, а не полагаться на то, что ветки выше всё предусмотрели.
  const open = (cleaned.match(/\(/g) || []).length;
  const close = (cleaned.match(/\)/g) || []).length;
  if (open > close) cleaned = cleaned.slice(0, cleaned.lastIndexOf("(")).replace(/[\s,–—-]+$/, "");

  return cleaned || truncate(String(c.short || ""), 40);
}

// 🔴 БОЛЬШЕ НЕ ИСПОЛЬЗУЕТСЯ В ТАЙТЛАХ (владелец, 2026-07-30). Печатала в заголовок
// `valuation.fair_value_range.base` — оценку аналитика из файла. С переходом платформы на
// методику Basis (движок BFV) это число разошлось с тем, что человек видит, открыв
// страницу: ЛУКОЙЛ 5017 ₽ в выдаче против 2063 ₽ на сайте, Аэрофлот 44 против 17,8,
// Газпром 175 против 98,5. Клик по обещанной цене приводил на другую — по доверию это
// бьёт сильнее, чем отсутствие цифры в тайтле, потому что заголовок читают первым.
// Функция оставлена: живую цену Basis в статику можно вернуть, если сборка будет ходить
// в API (это отдельное решение — статика тогда стареет между деплоями).
function fairPriceRub(c) {
  const v = c.fin && c.fin.valuation && c.fin.valuation.fair_value_range
    ? c.fin.valuation.fair_value_range.base : null;
  if (typeof v !== "number" || !isFinite(v) || v <= 0) return null;
  const abs = Math.abs(v);
  const rounded = abs >= 100 ? Math.round(v)
    : abs >= 10 ? Math.round(v * 10) / 10
    : abs >= 1 ? Math.round(v * 100) / 100
    : Math.round(v * 10000) / 10000;
  const [int, frac] = String(rounded).split(".");
  const grouped = int.replace(/\B(?=(\d{3})+(?!\d))/g, " "); // 15894 → «15 894»
  return frac ? `${grouped},${frac}` : grouped;
}

function hubDescription(c) {
  const bits = [];
  const rv = lastValue(c, c.profile === "bank" ? "net_interest_income" : "revenue");
  const np = lastValue(c, "net_profit");
  if (rv) bits.push(`${c.profile === "bank" ? "процентные доходы" : "выручка"} ${rv.year}: ${fmtMoney(rv.value, c.unit, c.currency)}`);
  if (np) bits.push(`${np.value < 0 ? "чистый убыток" : "чистая прибыль"}: ${fmtMoney(Math.abs(np.value), c.unit, c.currency)}`);
  const nums = bits.length ? ` ${bits.join(", ").replace(/^./, (ch) => ch.toUpperCase())}.` : "";
  return truncate(
    `${c.short} (${c.ticker}), сектор «${c.sectorFull || c.sector}»: бизнес-модель, финансы, дивиденды, справедливая цена, макро- и геополитические риски.${nums} Разбор Basis.`,
    200
  );
}

function hubPage(c, tabsWritten, sectorPeers, assets) {
  // Тайтл под поисковый интент (владелец, 2026-07-27): «анализ акций X»,
  // «справедливая цена X» — реальные запросы; цифра из financials.json датирована.
  // Без числа: интент-слова («анализ акций», «справедливая цена», «дивиденды») в тайтле
  // сохранены — они и ловят запрос, а конкретная цифра теперь живёт только на странице,
  // где считается по актуальной методике.
  // Длина: у 109 карточек из 264 тайтл вылезал за 75 знаков и обрезался в выдаче —
  // терялся хвост, а вместе с ним и «Basis». Убрано слово «дивиденды»: по этому запросу
  // работает отдельная страница /company/<T>/dividends/, дублировать его в заголовке
  // хаба незачем, а место оно съедает у более важного «справедливая цена».
  const title = `${titleName(c)} (${c.ticker}): анализ акций, справедливая цена — Basis`;
  const desc = hubDescription(c);
  const parts = [];
  parts.push(`<p class="tag">${escapeHtml(c.sectorFull || c.sector)} · MOEX: ${c.ticker}</p>`);
  parts.push(`<h1>${escapeHtml(c.short)} <span style="color:var(--faint)">(${c.ticker})</span></h1>`);
  if (c.name !== c.short) parts.push(`<p class="sub">${escapeHtml(c.name)}</p>`);

  // Суть бизнеса — первый абзац прозы из business_model.md
  // Было одно предложение (400 символов) — теперь первые разделы разбора (2600).
  // Полный текст остаётся на /business/ (12 000), так что это не дубль страницы, а
  // содержательное начало: человек, пришедший из поиска, сразу видит суть, а не тизер.
  const lead = mdExcerpt(c.businessMd, 2600) || (() => {
    const one = mdFirstSentence(c.businessMd, 400);
    return one ? `<p>${escapeHtml(one)}</p>` : null;
  })();
  if (lead) parts.push(`<h2>Суть бизнеса</h2>${lead}
<p class="sub"><a href="/company/${c.ticker}/business/">Полный разбор бизнес-модели ${escapeHtml(c.short)} →</a></p>`);

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

  // 🔴 Выжимки макро и геополитики прямо на карточке (2026-07-31). Раньше хаб давал
  // роботу 359 слов: суть бизнеса одним абзацем, факты, две таблицы — и всё. Разборы
  // макро- и геополитических рисков существовали, но только на отдельных страницах, и
  // главная страница компании выглядела «тонкой» при том, что содержания у нас больше,
  // чем у конкурентов в топе. Здесь — сжато и с ссылкой на полный разбор, чтобы
  // страницы не дублировали друг друга целиком (за дубли поиск наказывает).
  const macroLead = mdExcerpt(c.macroMd, 1400);
  if (macroLead) {
    parts.push(`<h2>Макроэкономика: что влияет на компанию</h2>${macroLead}
<p class="sub"><a href="/company/${c.ticker}/macro/">Полный макроразбор ${escapeHtml(c.short)} →</a></p>`);
  }
  const geoLead = mdExcerpt(c.geoMd, 1400);
  if (geoLead) {
    parts.push(`<h2>Геополитика и санкционные риски</h2>${geoLead}
<p class="sub"><a href="/company/${c.ticker}/geo/">Полный геополитический разбор →</a></p>`);
  }

  // Разделы разбора → отдельные страницы + deep-link в приложение
  if (tabsWritten.length) {
    parts.push(`<h2>Разделы разбора</h2><div class="grid">${tabsWritten.map((t) =>
      `<a class="chip" href="/company/${c.ticker}/${t.slug}/">${escapeHtml(t.label)}</a>`).join("")}</div>`);
  }

  parts.push(`<a class="cta" href="/company/${c.ticker}/">Открыть полный разбор ${escapeHtml(c.short)} в Basis →</a>`);

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
    assets,
  });
}

function tabPage(c, spec, contentHtml, tabsWritten, assets) {
  const others = tabsWritten.filter((t) => t.slug !== spec.slug);
  const othersHtml = others.length
    ? `<h2>Другие разделы разбора</h2><div class="grid">${others.map((t) =>
        `<a class="chip" href="/company/${c.ticker}/${t.slug}/">${escapeHtml(t.label)}</a>`).join("")}</div>`
    : "";
  const body = `
<p class="tag">${escapeHtml(c.sectorFull || c.sector)} · MOEX: ${c.ticker}</p>
<h1>${escapeHtml(spec.label)}: ${escapeHtml(c.short)} <span style="color:var(--faint)">(${c.ticker})</span></h1>
${contentHtml}
<a class="cta" href="/company/${c.ticker}/${spec.slug}/">Продолжить в приложении: ${escapeHtml(spec.label.toLowerCase())} ${escapeHtml(c.short)} →</a>
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
    assets,
  });
}

function indexPage(companies) {
  const bySector = {};
  for (const c of companies) (bySector[c.sector] = bySector[c.sector] || []).push(c);
  const sectors = Object.keys(bySector).sort((a, b) => bySector[b].length - bySector[a].length);
  const body = `
<h1>Аналитика компаний Московской биржи</h1>
<p class="sub">${companies.length} разборов: бизнес-модель, финансы и справедливая
цена, дивиденды, корпоративное управление, макро- и геополитические риски по каждой бумаге.</p>
${sectors.map((s) => `<h2>${escapeHtml(s)} <span style="color:var(--faint);font-size:14px">· ${bySector[s].length}</span></h2>
<div class="grid">${bySector[s]
    .sort((a, b) => a.short.localeCompare(b.short, "ru"))
    .map((c) => `<a class="chip" href="/company/${c.ticker}/">${escapeHtml(c.short)} (${c.ticker})</a>`).join("")}</div>`).join("\n")}
<h2>Инструменты и методики Basis</h2>
<div class="grid">${LANDINGS.map((l) => `<a class="chip" href="/${l.slug}/">${escapeHtml(l.crumb)}</a>`).join("")}</div>
<a class="cta" href="/">Открыть приложение Basis →</a>`;
  return pageShell({
    title: `Аналитика по ${companies.length} компаниям Мосбиржи — разборы Basis`,
    desc: `Каталог разборов Basis: ${companies.length} компаний Московской биржи по секторам — бизнес-модель, финансы, дивиденды, справедливая цена, риски. Без сигналов «купить/продать».`,
    canonicalPath: "/company/",
    breadcrumbs: [{ label: "Basis", href: "/" }, { label: "Компании" }],
    bodyHtml: body,
    jsonLd: [],
  });
}


/* ------------ страницы под ТОЧЕЧНЫЕ метрики («ebitda северстали») ------------ */
// Владелец, 2026-07-31: «если человек ищет ebitda северстали — нужно, чтобы он нас
// находил, потому что во вкладке Финансы такая информация есть; надо декомпозировать
// вкладки до конкретных вещей». Запрос «<метрика> <компания>» — самый частый тип
// точечного поиска, а у нас под него не было ни одной страницы: данные лежали внутри
// вкладки «Финансы», куда поиск не заглядывает.
//
// Страницы делаем ТОЛЬКО там, где есть ряд минимум за 3 года: иначе получится пустышка,
// а массовая генерация тонких однотипных страниц понижает весь сайт.
const METRIC_PAGES = [
  {
    slug: "operatsionnaya-pribyl",
    formula: "Выручка − себестоимость − коммерческие и управленческие расходы.",
    simple: "Заработок от основного дела: уже с учётом износа оборудования, но ещё до процентов по кредитам и налогов.", key: "operating_profit", label: "Операционная прибыль",
    bank: false,
    what: "Операционная прибыль — то, что осталось от выручки после всех расходов на ведение "
      + "основной деятельности, но до процентов по долгу и налогов. Она показывает, зарабатывает "
      + "ли бизнес на том, чем занимается, отдельно от того, как он профинансирован.",
    caveat: "В отличие от EBITDA, операционная прибыль уже уменьшена на амортизацию — то есть "
      + "учитывает износ основных средств. Разрыв между этими двумя строками показывает, "
      + "насколько бизнес капиталоёмкий.",
  },
  {
    slug: "svobodnyy-denezhnyy-potok",
    formula: "Операционный денежный поток − капитальные затраты.",
    simple: "Деньги, которые остаются после того, как оплачена текущая работа и вложения в оборудование. Именно из них платят дивиденды и гасят долг.", key: "fcf", label: "Свободный денежный поток",
    from: "cash_flow", bank: false,
    // Готовый ряд есть не у всех, а считать «CFO минус capex» вслепую нельзя: знак
    // капзатрат в данных разный (у одних эмитентов −449 975, у других +97 409), и
    // прямое вычитание половине компаний удвоило бы поток. Берём модуль.
    derive: (fin) => {
      const cf = fin.cash_flow || {};
      if (Array.isArray(cf.fcf) && cf.fcf.filter((x) => typeof x === "number").length >= 3) return cf.fcf;
      const cfo = cf.cfo, capex = cf.capex;
      if (!Array.isArray(cfo) || !Array.isArray(capex)) return null;
      return cfo.map((v, i) => (typeof v === "number" && typeof capex[i] === "number"
        ? v - Math.abs(capex[i]) : null));
    },
    what: "Свободный денежный поток — деньги, которые остались у компании после оплаты текущей "
      + "деятельности и вложений в основные средства. Именно из него платятся дивиденды и "
      + "гасится долг, поэтому он ближе к интересам акционера, чем бумажная прибыль.",
    caveat: "Поток по годам скачет: крупная стройка или разовая закупка легко уводят его в "
      + "минус у здорового бизнеса. Смотреть надо на несколько лет подряд, а не на один год.",
  },
  {
    slug: "operatsionnyy-denezhnyy-potok",
    formula: "Прибыль + амортизация ± изменения оборотного капитала.",
    simple: "Сколько живых денег принесла основная деятельность. Проверка прибыли на честность: прибыль можно начислить на бумаге, деньги на счёте — нет.", key: "cfo", label: "Операционный денежный поток",
    from: "cash_flow", bank: true,
    what: "Операционный денежный поток — сколько живых денег принесла основная деятельность. "
      + "Это проверка прибыли на реальность: прибыль можно начислить, деньги — нет.",
    caveat: "Систематический разрыв, когда прибыль растёт, а денежный поток нет, — повод "
      + "разбираться: обычно за ним стоит рост дебиторской задолженности или запасов.",
  },
  {
    slug: "aktivy",
    formula: "Собственный капитал + все обязательства. Всё, чем компания владеет.",
    simple: "Заводы, склады, запасы, деньги, выданные кредиты — весь имущественный размер компании. У банка активы это в основном выданные кредиты.", key: "total_assets", label: "Активы", from: "balance_sheet", bank: true,
    what: "Активы — всё, чем компания владеет: заводы, запасы, деньги на счетах, выданные "
      + "займы. Мера размера баланса, особенно важная для банков, где активы — это в основном "
      + "кредитный портфель.",
    caveat: "Размер активов ничего не говорит об их качестве. Растущий баланс при падающей "
      + "отдаче на активы означает, что компания вкладывает всё больше, зарабатывая всё меньше.",
  },
  {
    slug: "sobstvennyy-kapital",
    formula: "Активы − обязательства.",
    simple: "Что осталось бы акционерам, если продать всё имущество и раздать все долги. Балансовая стоимость компании.", key: "total_equity", label: "Собственный капитал",
    from: "balance_sheet", bank: true,
    what: "Собственный капитал — то, что осталось бы акционерам после погашения всех "
      + "обязательств. Балансовая стоимость компании, с которой сравнивают рыночную "
      + "капитализацию в мультипликаторе P/B.",
    caveat: "Капитал в отчётности отражает историческую стоимость активов, а не сегодняшнюю. "
      + "У компании со старыми активами он занижен, у компании с переоценёнными — завышен.",
  },
  {
    slug: "roa",
    formula: "Чистая прибыль ÷ активы × 100%.",
    simple: "Сколько прибыли выжимается из каждого рубля активов — независимо от того, чьи это деньги, акционеров или кредиторов.", key: "roa", label: "Рентабельность активов (ROA)", from: "returns",
    percentBasis: [["income_statement", "net_profit"], ["balance_sheet", "total_assets"]],
    unit: "%", bank: true,
    what: "Рентабельность активов — сколько прибыли приносит каждый рубль активов. Показывает "
      + "эффективность бизнеса без поправки на то, чьи это деньги — акционеров или кредиторов.",
    caveat: "ROA несопоставима между отраслями: у ритейла с быстрым оборотом она естественно "
      + "выше, чем у сетевой инфраструктуры с огромной базой активов. Сравнивать имеет смысл "
      + "внутри сектора и с собственной историей компании.",
  },
  {
    slug: "ebitda",
    formula: "Операционная прибыль + амортизация. Или, если идти сверху: выручка − себестоимость − коммерческие и управленческие расходы + амортизация.",
    simple: "Сколько бизнес зарабатывает «до всего»: до процентов банку, налогов государству и списания износа оборудования. Показатель придумали, чтобы сравнивать компании, которые по-разному закредитованы и по-разному считают износ.", key: "ebitda", label: "EBITDA", bank: false,
    what: "EBITDA — прибыль до вычета процентов, налогов и амортизации. Показывает, сколько "
      + "бизнес зарабатывает на основной деятельности, до влияния долговой нагрузки и "
      + "учётной политики по амортизации. Поэтому по ней сравнивают компании с разной "
      + "структурой финансирования.",
    caveat: "EBITDA не равна деньгам: она не учитывает капитальные затраты и оборотный "
      + "капитал. У капиталоёмкого бизнеса высокая EBITDA может сочетаться с нулевым "
      + "свободным потоком — поэтому рядом всегда смотрим денежный поток и долг.",
  },
  {
    slug: "vyruchka",
    formula: "Цена × количество проданного за период. В отчёте — самая верхняя строка.",
    simple: "Сколько денег компания выручила от продаж, ещё ничего не потратив. Это масштаб бизнеса, а не заработок: из выручки предстоит оплатить всё остальное.", key: "revenue", bankKey: "net_interest_income", label: "Выручка",
    bankLabel: "Чистые процентные доходы",
    what: "Выручка — сколько компания продала за период, до вычета любых расходов. Это "
      + "верхняя строка отчёта и мера масштаба бизнеса.",
    caveat: "Рост выручки сам по себе ещё не хорошая новость: если он куплен ростом "
      + "издержек или скидками, прибыль может падать одновременно с ростом продаж.",
  },
  {
    slug: "chistaya-pribyl",
    formula: "Выручка − все расходы − проценты по долгу − налог на прибыль.",
    simple: "То, что реально осталось компании в конце. Из этой суммы платят дивиденды, остальное остаётся внутри и увеличивает капитал.", key: "net_profit", label: "Чистая прибыль", bank: true,
    what: "Чистая прибыль — то, что осталось после всех расходов, процентов и налогов. "
      + "Из неё платятся дивиденды и она формирует капитал компании.",
    caveat: "Чистая прибыль легче других строк искажается разовыми событиями: переоценкой "
      + "активов, курсовыми разницами, продажей бизнеса. Поэтому мы смотрим и "
      + "нормализованную прибыль — без разовых статей.",
  },
  {
    slug: "chistyy-dolg",
    formula: "Все кредиты и облигации − деньги на счетах и депозитах.",
    simple: "Сколько компания должна сверх того, что у неё уже есть в кассе. Если денег больше, чем долгов, показатель отрицательный — это не ошибка, а признак запаса прочности.", lowerIsBetter: true, key: "net_debt", label: "Чистый долг", bank: false,
    from: "balance_sheet",
    what: "Чистый долг — весь долг компании минус денежные средства на счетах. Отрицательное "
      + "значение означает, что денег больше, чем долгов: компания в чистой денежной позиции.",
    caveat: "Сам по себе размер долга ничего не говорит: важно, чем он обслуживается. "
      + "Поэтому долг сопоставляют с прибылью — см. долговую нагрузку. Дешёвый долг у "
      + "растущего бизнеса нормален, дорогой у падающего опасен даже при меньшей сумме.",
  },
  {
    slug: "dolgovaya-nagruzka",
    formula: "Чистый долг ÷ EBITDA.",
    simple: "За сколько лет компания расплатилась бы по долгам, если бы вся операционная прибыль шла только на это. Три года — уже много, полтора — спокойно.", lowerIsBetter: true,
    // минус бывает двух совершенно разных природ — их нельзя показывать одинаково
    pointInvalid: (fin, i) => {
      const e = ((fin.income_statement || {}).ebitda || [])[i];
      return typeof e === "number" && e < 0;
    },
    note: (c, pts, last) => (last < 0
      ? "Отрицательное значение здесь означает отрицательный чистый долг: денежных средств "
        + "на счетах больше, чем всего долга. Формально компания способна погасить долг "
        + "сразу, и долговой риск для неё не основной."
      : ""), key: "net_debt_ebitda", label: "Долговая нагрузка (чистый долг / EBITDA)",
    shortLabel: "Долговая нагрузка", bank: false, from: "ratios", unit: "×", decimals: 2,
    what: "Отношение чистого долга к EBITDA показывает, за сколько лет компания погасила бы "
      + "долг, если бы вся операционная прибыль шла только на это. Универсальная мера того, "
      + "посилен ли долг.",
    caveat: "Ориентир: до 1,5× — низкая нагрузка, 1,5–3× — умеренная, выше 3× — повышенная. "
      + "Но пороги отличаются по отраслям: инфраструктуре и электроэнергетике с "
      + "предсказуемой выручкой можно больше, чем цикличной добыче.",
  },
  {
    slug: "roe",
    formula: "Чистая прибыль ÷ собственный капитал × 100%.",
    simple: "Сколько копеек прибыли приносит каждый рубль, вложенный акционерами. Мера того, насколько эффективно компания распоряжается их деньгами.", key: "roe",
    percentBasis: [["income_statement", "net_profit"], ["balance_sheet", "total_equity"]], label: "ROE (рентабельность капитала)", shortLabel: "ROE",
    bank: true, from: "returns", unit: "%", decimals: 1,
    what: "ROE — отношение прибыли к собственному капиталу: сколько компания зарабатывает "
      + "на деньгах акционеров. Ключевая мера эффективности бизнеса и главный вход в "
      + "оценку по балансовой стоимости.",
    caveat: "Высокий ROE бывает не от эффективности, а от большого долга: чем меньше "
      + "собственного капитала, тем выше отношение при той же прибыли. Поэтому ROE "
      + "смотрят вместе с долговой нагрузкой, а не отдельно.",
  },
];

// Единицы рентабельностей в financials.json СМЕШАНЫ: у одних компаний проценты
// (11.19), у других доли (0.0577) — 31 компания по ROE, 56 по ROA. Порог «меньше
// полутора значит доля» проверен на данных и ошибается на 11 компаниях в опасную
// сторону: у «Красного Октября» ROE действительно 0,88 %, и порог раздул бы его до
// 88 %. Поэтому единицы устанавливаем сверкой с пересчётом из первичных статей, а где
// сверить нечем — НЕ трогаем (занизить безопаснее, чем раздуть в сто раз).
// Та же логика на бэкенде: backend/app/services/units.py.
// Согласование существительного с числом: 21 компании, 22 компании, 25 компаний.
// Тикер привилегированной акции → тикер обычки того же эмитента (SBERP → SBER), если
// обычка есть в наборе. Нужно, чтобы один эмитент не попадал в статистику дважды.
function baseTicker(ticker, tickerSet) {
  if (ticker.length > 1 && ticker.endsWith("P")) {
    const base = ticker.slice(0, -1);
    if (tickerSet.has(base)) return base;
  }
  return ticker;
}

function plural(n, one, few, many) {
  const a = Math.abs(n) % 100, b = a % 10;
  const word = a > 10 && a < 20 ? many : b === 1 ? one : b >= 2 && b <= 4 ? few : many;
  return `${n} ${word}`;
}

function detectScale(series, num, den) {
  if (![series, num, den].every(Array.isArray)) return 1;
  const pairs = [];
  const n = Math.min(series.length, num.length, den.length);
  for (let i = 0; i < n; i++) {
    const s = series[i], a = num[i], b = den[i];
    if (![s, a, b].every((x) => typeof x === "number")) continue;
    if (b <= 0) continue;                       // отрицательный капитал — пересчёт не показателен
    const calc = (a / b) * 100;
    if (Math.abs(calc) > 300) continue;         // выброс, сверять по нему нельзя
    pairs.push([s, calc]);
  }
  if (pairs.length < 2) return 1;
  const errAsIs = pairs.reduce((t, [s, c]) => t + Math.abs(s - c), 0);
  const errX100 = pairs.reduce((t, [s, c]) => t + Math.abs(s * 100 - c), 0);
  return errX100 < errAsIs ? 100 : 1;
}

function metricSeries(c, spec) {
  const isBank = c.profile === "bank";
  if (isBank && spec.bank === false) return null;          // EBITDA у банка не считается
  const key = isBank && spec.bankKey ? spec.bankKey : spec.key;
  // Ряд может лежать не только в P&L: чистый долг — в балансе, ROE — в returns,
  // долговая нагрузка — в ratios (проверено по структуре financials.json).
  const src = spec.from === "balance_sheet" ? (c.fin.balance_sheet || {})
    : spec.from === "ratios" ? ((c.fin.balance_sheet || {}).ratios || {})
    : spec.from === "returns" ? (c.fin.returns || {})
    : spec.from === "cash_flow" ? (c.fin.cash_flow || {})
    : isBank ? (c.fin.bank_pnl || {}) : (c.fin.income_statement || {});
  let arr = spec.derive ? spec.derive(c.fin) : src[key];
  if (spec.percentBasis && Array.isArray(arr)) {
    const [[ng, nk], [dg, dk]] = spec.percentBasis;
    const k = detectScale(arr, (c.fin[ng] || {})[nk], (c.fin[dg] || {})[dk]);
    if (k !== 1) arr = arr.map((x) => (typeof x === "number" ? x * k : x));
  }
  if (!Array.isArray(arr) || !c.years.length) return null;
  const pts = [];
  const dropped = [];
  for (let i = 0; i < Math.min(arr.length, c.years.length); i++) {
    if (typeof arr[i] !== "number") continue;
    // Отношение к отрицательному знаменателю арифметически считается, но смыслом не
    // обладает: «−15,46×» у Мечела читается как «долга нет», хотя означает обратное —
    // EBITDA ушла в минус и обслуживать долг нечем. Такие точки не данные, а артефакт.
    if (spec.pointInvalid && spec.pointInvalid(c.fin, i, arr[i])) { dropped.push(c.years[i]); continue; }
    pts.push({ year: c.years[i], value: arr[i] });
  }
  if (pts.length >= 3 && dropped.length) pts.droppedYears = dropped;
  return pts.length >= 3 ? pts : null;
}

// Сравнение с сектором — то, ради чего страница перестаёт быть «числом из отчёта».
// Голая цифра есть у десятка агрегаторов; ответ на вопрос «это много или мало для такой
// компании» — почти ни у кого. Считаем по нашим же данным: медиана сектора и позиция.
function sectorContext(c, spec, lastValue, peers, fmt) {
  const vals = [];
  for (const p of peers) {
    const pts = metricSeries(p, spec);   // pointInvalid отсеян здесь же — медиана чистая
    if (pts && pts.length) vals.push({ ticker: p.ticker, short: p.short, value: pts[pts.length - 1].value });
  }
  if (vals.length < 3) return "";          // на двух соседях «медиана сектора» — фикция
  const sorted = vals.map((v) => v.value).slice().sort((a, b) => a - b);
  const median = sorted.length % 2
    ? sorted[(sorted.length - 1) / 2]
    : (sorted[sorted.length / 2 - 1] + sorted[sorted.length / 2]) / 2;
  const below = vals.filter((v) => v.value < lastValue).length;
  const rank = vals.length + 1 - below;     // 1 = самое высокое ЗНАЧЕНИЕ, не «лучшее»
  const cmp = lastValue > median ? "выше" : lastValue < median ? "ниже" : "на уровне";
  const top = vals.slice().sort((a, b) => b.value - a.value).slice(0, 6);
  // Нейтральное «N-е по величине», а не «N место»: у долговой нагрузки первое место —
  // это самый закредитованный в секторе, и слово «место» читалось бы как похвала.
  // «у компании», а не «у ${short}»: названия эмитентов не склоняются («у Северсталь
  // выше»), а часть коротких имён ещё и обрезана с незакрытой кавычкой.
  return `<h2>Сравнение с сектором</h2>
<p>Медиана по сектору «${escapeHtml(c.sectorFull || c.sector)}» — ${escapeHtml(fmt(median))};
у компании ${escapeHtml(cmp)} (${escapeHtml(fmt(lastValue))}) —
${rank}-е значение по величине среди ${plural(vals.length + 1, "компании", "компаний", "компаний")} сектора,
по которым есть данные.${
    spec.lowerIsBetter ? " По этому показателю большее значение означает больший риск, а не лучший результат." : ""
  }</p>
<table><thead><tr><th>Компания</th><th>Значение</th></tr></thead><tbody>${
    top.map((v) => `<tr><td><a href="/company/${v.ticker}/${spec.slug}/">${escapeHtml(v.short)}</a></td>`
      + `<td>${escapeHtml(fmt(v.value))}</td></tr>`).join("")
  }</tbody></table>
<p class="sub">Сравнение внутри сектора корректнее сравнения по всему рынку: у отраслей
разная нормальная рентабельность и разная терпимость к долгу.</p>`;
}


// ─── Справедливая цена: страница под запрос «справедливая цена акций <компании>» ────
// Подсказки Яндекса подтверждают спрос по конкретным эмитентам (Сбербанк, ЛУКОЙЛ, Х5,
// Газпром, Татнефть, Интер РАО, Магнит), а у нас это единственная метрика, которой нет
// у агрегаторов — они дают консенсус аналитиков, мы считаем от доходности ОФЗ.
//
// 🔴 ЧЕСТНОСТЬ ВАЖНЕЕ КЛИКА: число живое (пересчитывается от текущей цены), а страница
// статическая, поэтому на ней ОБЯЗАТЕЛЬНО стоит дата снимка и цена, к которой оценка
// относится. Без этого пользователь увидит вчерашний потенциал как сегодняшний.
// Формулировки — те же, что в src/fairValueNote.js, чтобы одно и то же число не
// объяснялось на карточке одним текстом, а здесь другим.
const FV_NOTE = "Это не прогноз цены и не таргет, а планка входа: столько бумага должна "
  + "стоить, чтобы вложение в неё было оправдано при сегодняшней доходности ОФЗ плюс "
  + "премия за риск — макроэкономический и конкретно этой компании. Ставки сейчас "
  + "высокие, поэтому у многих бумаг планка получается заметно ниже рынка: модель "
  + "говорит «дорого относительно безрисковой альтернативы», а не «упадёт». Методика "
  + "прототипная, без калибровки — может преувеличивать в обе стороны. Не является "
  + "индивидуальной инвестиционной рекомендацией.";


// ─── Глоссарий показателей: /pokazateli/<slug>/ ─────────────────────────────────────
// ЗАЧЕМ ОТДЕЛЬНО ОТ СТРАНИЦ КОМПАНИЙ: замер спроса (подсказки Яндекса и Google,
// 2026-07-31) показал, что метрики ищут ОПРЕДЕЛИТЕЛЬНО, а не по эмитенту. «что такое
// ebitda простыми словами», «чистый долг формула», «roa формула» — полные наборы
// подсказок; «ebitda северстали» — две-три. То есть 2541 страница «метрика компании»
// бьёт по тонкому хвосту, а голова спроса у нас не закрыта вообще.
//
// ЧЕМ МЫ ЗДЕСЬ ЛУЧШЕ СПРАВОЧНИКА: определение есть у всех, а вот показать показатель
// на 260 живых российских компаниях сразу — почти ни у кого. Поэтому на каждой странице
// таблица реальных значений со ссылками: определение сразу превращается в инструмент,
// а страница становится узлом, связывающим глоссарий с карточками.

// ─── «Недооценённые акции»: /nedootsenennye-aktsii/ ─────────────────────────────────
// Замер спроса: «недооценённые акции» и «какие акции купить» — широкие запросы, куда
// более массовые, чем «справедливая цена акций <эмитента>». Это тот же интент, только
// без имени компании, и отвечать на него мы можем честно: не списком «покупай», а
// показом того, что говорит наша модель, с оговорками.
//
// 🔴 ПОЧЕМУ ДВА СПИСКА, А НЕ ОДИН ПО УБЫВАНИЮ: верх рейтинга по потенциалу занимают
// малоликвидные бумаги ценой в копейки, где модель наименее устойчива — небольшая
// ошибка в прибыли даёт кратный разброс оценки. Один общий список по убыванию по факту
// рекомендовал бы читателю третий эшелон. Поэтому крупные бумаги отдельно, малые
// отдельно и с предупреждением.
function undervaluedLanding(companies, fairValues, dateIso, assets) {
  const toMln = (v, unit) => {
    if (typeof v !== "number") return null;
    const u = String(unit || "млн");
    if (u.startsWith("млрд")) return v * 1000;
    if (u.startsWith("тыс")) return v / 1000;
    return v;
  };
  const rows = [];
  for (const c of companies) {
    const f = fairValues[c.ticker];
    if (!f || typeof f.upside_pct !== "number") continue;
    const rev = (c.fin.income_statement || {}).revenue;
    const lastRev = Array.isArray(rev)
      ? [...rev].reverse().find((x) => typeof x === "number") : null;
    rows.push({ c, f, revMln: toMln(lastRev, c.unit) });
  }
  const positive = rows.filter((r) => r.f.upside_pct > 0).sort((a, b) => b.f.upside_pct - a.f.upside_pct);
  const BIG = 100000;   // 100 млрд ₽ выручки — грубая, но честная граница «крупной» бумаги
  const big = positive.filter((r) => (r.revMln || 0) >= BIG).slice(0, 15);
  const small = positive.filter((r) => (r.revMln || 0) < BIG).slice(0, 10);
  const asOf = dateIso ? new Date(dateIso).toLocaleDateString("ru-RU",
    { day: "numeric", month: "long", year: "numeric" }).replace(/\s*г\.\s*$/, "") : null;

  const money = (v) => Number(v).toLocaleString("ru-RU",
    { minimumFractionDigits: 2, maximumFractionDigits: 2 }) + " ₽";
  const table = (list) => `<table><thead><tr><th>Компания</th><th class="num">Цена</th>
<th class="num">Оценка Basis</th><th class="num">Разница</th></tr></thead><tbody>${
    list.map((r) => `<tr><td><a href="/company/${r.c.ticker}/spravedlivaya-tsena/">${
      escapeHtml(r.c.short)} (${r.c.ticker})</a></td><td class="num">${escapeHtml(money(r.f.price))}</td>`
      + `<td class="num">${escapeHtml(money(r.f.fair_value))}</td>`
      + `<td class="num">+${Math.round(r.f.upside_pct)}%</td></tr>`).join("")
  }</tbody></table>`;

  const body = `
<p class="tag">Оценка Basis · ${rows.length} бумаг Мосбиржи</p>
<h1>Недооценённые акции российского рынка</h1>
<p class="sub">Бумаги, у которых оценка Basis выше рыночной цены${asOf ? `, на ${escapeHtml(asOf)}` : ""}.
Это не список «что купить», а то, что показывает наша модель — со всеми оговорками ниже.</p>
<h2>Что здесь считается «недооценённой»</h2>
<p>Мы не сравниваем цену с мнением аналитиков. Отправная точка — доходность ОФЗ:
безрисковая альтернатива, доступная инвестору прямо сейчас. К ней добавляется премия за
риск — макроэкономический и конкретно этой компании. Получается планка: столько бумага
должна стоить, чтобы вложение в неё было оправдано. Если рынок торгует её дешевле планки,
она попадает в этот список.</p>
<p>Сразу важное о фоне: из ${rows.length} бумаг оценка выше цены только у
${plural(positive.length, "бумаги", "бумаг", "бумаг")}, а по рынку в целом медианная
разница отрицательная. Это не приговор российским компаниям — это следствие высокой
ключевой ставки: когда безрисковая доходность высокая, планка поднимается у всего рынка
сразу, и «дорого относительно ОФЗ» становится нормой.</p>
<h2>Крупные компании с оценкой выше цены</h2>
<p>Бумаги с выручкой от 100 млрд ₽ — те, что на слуху и достаточно ликвидны.</p>
${big.length ? table(big) : "<p>Сейчас таких бумаг нет.</p>"}
<h2>Небольшие компании</h2>
<p><b>Здесь нужна осторожность.</b> Верх любого рейтинга по потенциалу занимают
малоликвидные бумаги: у них небольшая ошибка в прогнозе прибыли даёт кратный разброс
оценки, а выйти из позиции бывает труднее, чем войти. Большой процент в таблице ниже
чаще говорит о неопределённости, чем о находке.</p>
${small.length ? table(small) : "<p>Сейчас таких бумаг нет.</p>"}
<h2>Чего этот список не значит</h2>
<p>Он не значит «эти акции вырастут». Модель говорит только о соотношении цены и
требуемой доходности сегодня — она не предсказывает котировки и не знает, когда и
почему рынок передумает. Методика прототипная, без калибровки, и может преувеличивать в
обе стороны. Basis не брокер, не проводит сделок и не даёт индивидуальных инвестиционных
рекомендаций.</p>
<p>Разумный следующий шаг — не купить из таблицы, а разобраться: почему рынок оценивает
компанию дешевле, чем модель. Ответ обычно в бизнесе, долге или управлении, и он есть в
разборе — например, <a href="/company/">по любой из ${companies.length} компаний</a>.
Отобрать бумаги по своим условиям можно в <a href="/skrining-aktsiy/">скрининге</a>, а
как устроена сама методика — на странице
<a href="/spravedlivaya-tsena-aktsiy/">справедливой цены</a>.</p>`;

  return pageShell({
    title: "Недооценённые акции России: список по справедливой цене — Basis",
    desc: "Акции Мосбиржи, у которых оценка Basis выше рыночной цены: расчёт от доходности "
      + "ОФЗ и премии за риск. С оговорками о том, что список не значит.",
    canonicalPath: "/nedootsenennye-aktsii/",
    breadcrumbs: [{ label: "Basis", href: "/" }, { label: "Недооценённые акции" }],
    bodyHtml: body, assets, note: DEFAULT_NOTE,
  });
}


// ─── Термины рынка: те же /pokazateli/, но без рядов по годам ───────────────────────
// Спрос по ним широкий («что такое офз», «дюрация облигации что это простыми словами»,
// «оферта по облигации» — полные наборы подсказок), а у нас 3270 страниц выпусков БЕЗ
// справочного узла, который объяснял бы, что означают колонки в их таблицах.
const TERM_PAGES = require("./seo-terms-content");

// Живые примеры: определение, показанное на реальных бумагах, — то, чего нет у
// справочников. Каждый вид примеров знает, что взять и как объяснить выборку.
function termExamples(kind, ctx) {
  const bonds = ctx.bonds || [];
  const num = (v, d = 2) => Number(v).toLocaleString("ru-RU",
    { minimumFractionDigits: d, maximumFractionDigits: d });
  const bondTable = (list, col, cell, note) => list.length
    ? `<table><thead><tr><th>Выпуск</th><th>Эмитент</th><th class="num">${col}</th></tr></thead>
<tbody>${list.map((b) => `<tr><td><a href="/bonds/${b.secid}/">${escapeHtml(b.short_name || b.secid)}</a></td>`
      + `<td>${escapeHtml((b.issuer_name || "—").slice(0, 34))}</td>`
      + `<td class="num">${escapeHtml(cell(b))}</td></tr>`).join("")}</tbody></table>
${note ? `<p class="sub">${note}</p>` : ""}` : "";
  const withYtm = bonds.filter((b) => typeof b.ytm === "number" && b.ytm > 0 && b.ytm < 80);

  switch (kind) {
    case "bonds-ofz": {
      // ТОЛЬКО с реальной доходностью: у ОФЗ-ПК (плавающий купон) ytm приходит нулём,
      // и таблица выходила со столбцом «0,00%» на каждой строке.
      const list = bonds.filter((b) => b.bond_type === "ofz"
        && typeof b.ytm === "number" && b.ytm > 0 && typeof b.duration_years === "number")
        .sort((a, b) => a.duration_years - b.duration_years).slice(0, 8);
      return bondTable(list, "Доходность", (b) => `${num(b.ytm)}%`,
        "Выпуски отсортированы от коротких к длинным: видно, как доходность меняется с "
        + "удлинением срока — это и есть кривая доходности ОФЗ, от которой считается всё остальное.");
    }
    case "bonds-duration": {
      const list = withYtm.filter((b) => typeof b.duration_years === "number")
        .sort((a, b) => b.duration_years - a.duration_years).slice(0, 8);
      return bondTable(list, "Дюрация", (b) => `${num(b.duration_years, 1)} года`,
        "Самые длинные выпуски в базе. Именно они сильнее всего дорожают при снижении "
        + "ключевой ставки — и сильнее всего дешевеют при её росте.");
    }
    case "bonds-coupon": {
      const list = bonds.filter((b) => typeof b.coupon_percent === "number" && b.coupon_percent > 0)
        .sort((a, b) => b.coupon_percent - a.coupon_percent).slice(0, 8);
      return bondTable(list, "Ставка купона", (b) => `${num(b.coupon_percent)}%`,
        "Высокая ставка купона сама по себе не означает высокую доходность вложения: "
        + "такие бумаги обычно торгуются дороже номинала, и часть купона «оплачена» ценой.");
    }
    case "bonds-price": {
      const list = bonds.filter((b) => typeof b.last_price === "number" && b.last_price > 0
        && b.last_price < 100).sort((a, b) => a.last_price - b.last_price).slice(0, 8);
      return bondTable(list, "Цена, % номинала", (b) => `${num(b.last_price)}%`,
        "Выпуски, торгующиеся заметно ниже номинала. Дисконт означает либо купон ниже "
        + "рыночных ставок, либо сомнения рынка в эмитенте — это разные вещи, и различать их "
        + "нужно по разбору эмитента, а не по величине скидки.");
    }
    case "bonds-nkd": {
      const list = bonds.filter((b) => typeof b.accrued_int === "number" && b.accrued_int > 0)
        .sort((a, b) => b.accrued_int - a.accrued_int).slice(0, 8);
      return bondTable(list, "НКД, ₽", (b) => `${num(b.accrued_int)} ₽`,
        "Столько покупатель доплатит сверх цены сверху за каждую бумагу — и получит обратно "
        + "в ближайшую купонную выплату.");
    }
    case "bonds-offer": {
      const today = new Date().toISOString().slice(0, 10);
      const list = bonds.filter((b) => b.offer_date && String(b.offer_date) > today)
        .sort((a, b) => String(a.offer_date).localeCompare(String(b.offer_date))).slice(0, 8);
      return bondTable(list, "Дата оферты", (b) => ruDate(b.offer_date) || String(b.offer_date),
        "Ближайшие оферты в базе. По таким выпускам доходность корректно считать к дате "
        + "оферты, а не к погашению: после неё условия могут стать совсем другими.");
    }
    case "bonds-ytm": {
      const list = withYtm.sort((a, b) => b.ytm - a.ytm).slice(0, 8);
      return bondTable(list, "Доходность", (b) => `${num(b.ytm)}%`,
        "Самые высокие доходности в базе. Это не список выгодных бумаг: доходность выше "
        + "рынка — плата за риск, который рынок уже видит. Разбор эмитента здесь важнее цифры.");
    }
    case "companies-pe": {
      const seen = new Set();
      const tickers = new Set((ctx.companies || []).map((c) => c.ticker));
      const rows = (ctx.companies || []).map((c) => {
        const pe = (((c.fin.multiples || {}).current || {}) || {}).pe;
        return typeof pe === "number" && pe > 0 && pe < 60 ? { c, pe } : null;
      }).filter(Boolean).sort((a, b) => a.pe - b.pe).filter((r) => {
        // обычка и преф одного эмитента — одна компания и один P/E: «Ижсталь» шла дважды
        const base = baseTicker(r.c.ticker, tickers);
        if (seen.has(base)) return false;
        seen.add(base); return true;
      }).slice(0, 10);
      if (!rows.length) return "";
      return `<table><thead><tr><th>Компания</th><th class="num">P/E</th></tr></thead><tbody>${
        rows.map((r) => `<tr><td><a href="/company/${r.c.ticker}/">${escapeHtml(r.c.short)}</a></td>`
          + `<td class="num">${num(r.pe, 1)}</td></tr>`).join("")}</tbody></table>
<p class="sub">Самые низкие P/E на рынке. Низкий множитель — повод разобраться, а не вывод:
у части этих компаний он низкий заслуженно (цикличность, долг, разовая прибыль).</p>`;
    }
    case "companies-dividends": {
      const rows = (ctx.companies || []).map((c) => {
        const h = ((c.dividends || {}).history || []).filter((x) => x && x.paid !== false && x.yield_pct != null);
        const last = h.sort((a, b) => (b.year || 0) - (a.year || 0))[0];
        return last ? { c, y: last.yield_pct, year: last.year } : null;
      }).filter(Boolean).sort((a, b) => b.y - a.y).slice(0, 10);
      if (!rows.length) return "";
      return `<table><thead><tr><th>Компания</th><th class="num">Доходность выплаты</th></tr></thead><tbody>${
        rows.map((r) => `<tr><td><a href="/company/${r.c.ticker}/dividends/">${escapeHtml(r.c.short)}</a></td>`
          + `<td class="num">${num(r.y, 1)}% (${r.year})</td></tr>`).join("")}</tbody></table>
<p class="sub">Доходность последней подтверждённой выплаты к цене того периода — историческая,
не текущая. Ближайшие выплаты по рынку — в <a href="/dividendnyy-kalendar/">календаре</a>.</p>`;
    }
    case "macro-key-rate":
      return `<p>Текущее значение ставки, история решений ЦБ и график —
на странице <a href="/statistika/klyuchevaya-stavka/">ключевой ставки</a>. Там же видно,
как она соотносится с инфляцией: разница между ними показывает, насколько жёсткая сейчас
денежная политика.</p>`;
    default: return "";
  }
}

function termPage(term, ctx, assets) {
  const label = term.label;
  // Не опускаем регистр, если метка начинается с аббревиатуры ИЛИ с одиночной заглавной
  // перед не-буквой: «P/E» → правило про две заглавные не срабатывало и давало «p/E».
  const titleLabel = /^[A-ZА-Я]{2,}|^[A-ZА-Я][^а-яa-zA-ZА-Я]/.test(label)
    ? label : label.charAt(0).toLowerCase() + label.slice(1);
  const title = term.titleOverride
    || `Что такое ${titleLabel} — ${term.formula ? "формула, " : ""}простыми словами | Basis`;
  const ex = termExamples(term.examples, ctx);
  const rel = (term.related || []).map((slug) => {
    const t = TERM_PAGES.find((x) => x.slug === slug);
    const m = METRIC_PAGES.find((x) => x.slug === slug);
    const item = t || m;
    return item ? `<a class="chip" href="/pokazateli/${slug}/">${escapeHtml(item.label)}</a>` : "";
  }).filter(Boolean).join("");

  const body = `
<p class="tag">Термины рынка · справочник Basis</p>
<h1>${escapeHtml(label)}: что это простыми словами</h1>
<p class="sub">${escapeHtml(term.simple)}</p>
${term.formula ? `<h2>Как считается</h2><p class="formula"><b>${escapeHtml(term.formula)}</b></p>` : ""}
<h2>Зачем это инвестору</h2>
<p>${escapeHtml(term.what)}</p>
<h2>Где легко ошибиться</h2>
<p>${escapeHtml(term.caveat)}</p>
${ex ? `<h2>На реальных бумагах</h2>${ex}` : ""}
${rel ? `<h2>Связанные термины</h2><div class="grid">${rel}</div>` : ""}
<p>Весь справочник — на странице <a href="/pokazateli/">показателей и терминов</a>.
Подобрать бумаги по своим условиям можно в <a href="/skrining-obligatsiy/">скрининге
облигаций</a> и <a href="/skrining-aktsiy/">скрининге акций</a>, а готовые подборки —
<a href="/bonds/ofz/">все ОФЗ с кривой доходности</a> и
<a href="/bonds/">каталог выпусков</a>.</p>`;

  return pageShell({
    title,
    desc: truncate(`${label} — что это простыми словами${term.formula ? ", как считается" : ""}, `
      + `зачем инвестору и где ошибаются. С примерами на реальных бумагах Мосбиржи.`, 200),
    jsonLd: [{
      "@type": "DefinedTerm",
      "@id": `${_SITE}/pokazateli/${term.slug}/#term`,
      name: label,
      description: term.simple,
      inDefinedTermSet: { "@id": `${_SITE}/pokazateli/#set` },
    }],
    canonicalPath: `/pokazateli/${term.slug}/`,
    breadcrumbs: [{ label: "Basis", href: "/" }, { label: "Показатели", href: "/pokazateli/" },
      { label }],
    bodyHtml: body, assets, note: DEFAULT_NOTE,
  });
}


// ─── Обозреватель: «новости по теме» отдельно от «анализа ситуации» ─────────────────
// Владелец 2026-07-31: «нужно разделение — новости просто и анализ текущей ситуации.
// Очень много запросов идут просто по названию геополитика, меньше новости геополитики,
// а по нашему „геополитика и российский рынок“ будет находиться хуже».
//
// Замер подтвердил: «новости геополитики» — широкий спрос с уточнением «сегодня»,
// «геополитическая ситуация» — тоже широкий. Это ДВА РАЗНЫХ намерения: одно «что
// случилось», другое «что происходит вообще». Одна страница отвечает на оба плохо.
//
// 🔴 ЧЕСТНО ПРО СВЕЖЕСТЬ: страница статическая, новости живые. Поэтому на ней стоит
// дата снимка, а под ней подгружается актуальная лента — как на страницах отчётности.
function newsTopicPage(cfg, news, assets) {
  const items = news.filter((n) => cfg.categories.includes(String(n.category)))
    .sort((a, b) => String(b.published_at || "").localeCompare(String(a.published_at || "")))
    .slice(0, 25);
  if (items.length < 5) return null;      // тонкую ленту публиковать незачем
  const asOf = ruDate(String(items[0].published_at || "").slice(0, 10));

  const li = items.map((n) => {
    const d = ruDate(String(n.published_at || "").slice(0, 10));
    const tick = (n.affected_tickers || []).slice(0, 3)
      .map((t) => `<a class="chip" href="/company/${escapeHtml(String(t))}/">${escapeHtml(String(t))}</a>`).join(" ");
    return `<li><b>${escapeHtml(strip(n.title))}</b>${d ? ` <span class="tag">${escapeHtml(d)}</span>` : ""}
${n.summary ? `<br>${escapeHtml(truncate(strip(n.summary), 260))}` : ""}
${n.impact_comment ? `<br><i>Что это значит: ${escapeHtml(truncate(strip(n.impact_comment), 220))}</i>` : ""}
${tick ? `<br>${tick}` : ""}</li>`;
  }).join("");

  const body = `
<p class="tag">${escapeHtml(cfg.tag)}${asOf ? ` · обновлено ${escapeHtml(asOf)}` : ""}</p>
<h1>${escapeHtml(cfg.h1)}</h1>
<p class="sub">${escapeHtml(cfg.lead)}</p>
<h2>Последние события</h2>
<ul class="news">${li}</ul>
<div id="live-news" data-cats="${escapeHtml(cfg.categories.join(","))}"></div>
<script>
// Лента подгружается живьём: адрес существует и проиндексирован заранее, свежие
// новости приезжают сюда сами, без пересборки сайта.
(function () {
  var host = document.getElementById("live-news");
  if (!host || !window.fetch) return;
  var cats = (host.dataset.cats || "").split(",");
  var esc = function (v) { return String(v == null ? "" : v).replace(/[&<>"]/g, function (m) {
    return { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[m]; }); };
  fetch(${JSON.stringify(API_BASE)} + "/api/market/news?limit=120")
    .then(function (r) { return r.ok ? r.json() : null; })
    .then(function (d) {
      var rows = (Array.isArray(d) ? d : (d && (d.items || d.news)) || [])
        .filter(function (n) { return n && cats.indexOf(String(n.category)) >= 0; }).slice(0, 25);
      if (!rows.length) return;
      var html = rows.map(function (n) {
        return "<li><b>" + esc(n.title) + "</b>" + (n.summary ? "<br>" + esc(n.summary) : "") + "</li>";
      }).join("");
      var ul = document.querySelector("ul.news");
      if (ul) ul.innerHTML = html;
    })
    .catch(function () { /* нет сети — остаётся снимок из HTML */ });
})();
</script>
${cfg.after}`;

  return pageShell({
    title: cfg.title, desc: cfg.desc, canonicalPath: `/${cfg.slug}/`,
    breadcrumbs: [{ label: "Basis", href: "/" }, { label: cfg.crumb }],
    bodyHtml: body, assets, note: DEFAULT_NOTE,
  });
}

const NEWS_TOPICS = [
  {
    slug: "novosti-geopolitiki",
    crumb: "Новости геополитики",
    tag: "Лента Basis · геополитика",
    title: "Новости геополитики сегодня: события и влияние на рынок — Basis",
    desc: "Свежие новости геополитики с разбором: что произошло и что это значит для "
      + "российского рынка и конкретных компаний. Лента обновляется автоматически.",
    h1: "Новости геополитики сегодня",
    lead: "События, которые двигают российский рынок: санкции, переговоры, ограничения. "
      + "К каждой новости — короткий разбор, что она меняет и для кого.",
    categories: ["Геополитика", "Политика"],
    after: `<h2>Не только новости</h2>
<p>Отдельные события мало что объясняют без общей картины: одна и та же новость значит
разное при разной геополитической обстановке. Разбор текущей ситуации — направления, по
которым идёт напряжение, и что каждое из них означает для секторов рынка — на странице
<a href="/geopolitika-i-rossiyskiy-rynok/">геополитической обстановки</a>. Как это влияет
на конкретную бумагу, видно в разделе «Геополитика» карточки компании — например,
у <a href="/company/GAZP/geo/">Газпрома</a> или <a href="/company/LKOH/geo/">ЛУКОЙЛа</a>.</p>`,
  },
  {
    slug: "novosti-ekonomiki",
    crumb: "Новости экономики",
    tag: "Лента Basis · экономика",
    title: "Новости экономики России сегодня: ставка, инфляция, рубль — Basis",
    desc: "Свежие новости экономики России с разбором: решения ЦБ, инфляция, курс рубля, "
      + "бюджет — и что каждое событие значит для инвестора. Лента обновляется автоматически.",
    h1: "Новости экономики России сегодня",
    lead: "Решения ЦБ, инфляция, курс рубля, бюджет — события, от которых зависит "
      + "доходность вкладов, облигаций и акций. С пояснением, на что каждое влияет.",
    categories: ["Экономика"],
    after: `<h2>Не только новости</h2>
<p>Чтобы понять, куда движется экономика, отдельных новостей мало — нужны показатели в
динамике и то, как они связаны между собой. Текущее состояние по всем ключевым
показателям — на странице <a href="/makroobzor-rossiyskoy-ekonomiki/">макроэкономики
России</a>, официальный ориентир ЦБ на ближайшие годы — в
<a href="/prognoz-banka-rossii/">среднесрочном прогнозе Банка России</a>, а сами
показатели с графиками — в <a href="/ekonomicheskaya-statistika-rossii/">экономической
статистике</a>.</p>`,
  },
];


// ─── Прогноз Банка России и график заседаний ────────────────────────────────────────
// Владелец: «есть например запросы типа среднесрочный прогноз банка россии — а на нас
// это не ведёт». Замер: запрос широкий, с уточнениями «по ключевой ставке», «по
// инфляции», «от <дата>». Данные у нас собираются давно (/api/market/macro/forecast),
// страницы под них не было. Отдельно «заседание цб по ключевой ставке 2026 график» —
// тоже широкий запрос и тоже готовые данные.
function cbForecastPage(fc, meetings, assets) {
  if (!fc || !Array.isArray(fc.rows) || !fc.rows.length) return null;
  const byInd = {};
  for (const r of fc.rows) {
    if (!r || !r.indicator) continue;
    (byInd[r.indicator] = byInd[r.indicator] || []).push(r);
  }
  // Парсер ЦБ иногда вытаскивает вместо числа словесную пометку («не указано», «не
  // изменился» — так в исходнике за 2028 год). В числовой колонке это читается как
  // ошибка данных, а «не изменился» без предыдущего значения вообще ничего не сообщает.
  // Показываем только то, в чём есть цифры.
  const val = (hit) => {
    const v = hit && hit.value != null ? String(hit.value).trim() : "";
    return /\d/.test(v) ? v : null;
  };
  // Годы, по которым нет ни одного числа, из таблицы убираем целиком — колонка из
  // сплошных прочерков только создаёт впечатление, что данные потерялись.
  const years = [...new Set(fc.rows.map((r) => r.year).filter(Boolean))].sort()
    .filter((y) => fc.rows.some((r) => r.year === y && val(r)));
  if (!years.length) return null;
  const head = `<tr><th>Показатель</th>${years.map((y) => `<th class="num">${y}</th>`).join("")}</tr>`;
  const rows = Object.keys(byInd).map((ind) => {
    const cells = years.map((y) => {
      const v = val(byInd[ind].find((r) => r.year === y));
      return `<td class="num">${escapeHtml(v || "—")}</td>`;
    }).join("");
    return `<tr><td>${escapeHtml(ind)}</td>${cells}</tr>`;
  }).join("");
  const asOf = ruDate(fc.as_of);
  const next = (meetings || []).filter((m) => m.date >= new Date().toISOString().slice(0, 10))
    .sort((a, b) => String(a.date).localeCompare(String(b.date)))[0];

  const body = `
<p class="tag">Официальный прогноз ЦБ${asOf ? ` · опубликован ${escapeHtml(asOf)}` : ""}</p>
<h1>Среднесрочный прогноз Банка России</h1>
<p class="sub">${escapeHtml(fc.comment || "Ориентир ЦБ по ключевой ставке, инфляции и росту экономики на ближайшие годы.")}
${fc.scenario ? `Сценарий — ${escapeHtml(fc.scenario)}.` : ""} <span class="tag">факт</span></p>
<table><thead>${head}</thead><tbody>${rows}</tbody></table>
<p class="sub">Значения — диапазоны из среднесрочного прогноза Банка России${
    fc.source_url ? `, <a href="${escapeHtml(fc.source_url)}" rel="nofollow">источник</a>` : ""}.
Прогноз обновляется на опорных заседаниях, четыре раза в год.</p>
<h2>Зачем инвестору этот прогноз</h2>
<p>Это не мнение аналитиков, а официальный ориентир регулятора — и рынок торгует именно
ожидания по нему. Прогноз по ключевой ставке задаёт доходность вкладов и облигаций на
годы вперёд: если ЦБ ждёт снижения, длинные облигации выигрывают заранее, ещё до самого
снижения. Он же меняет и оценку акций — чем ниже безрисковая ставка, тем ниже планка
требуемой доходности, по которой считается
<a href="/spravedlivaya-tsena-aktsiy/">справедливая цена</a>.</p>
<h2>Как читать диапазоны</h2>
<p>ЦБ публикует не точку, а интервал — и это честнее точной цифры: он показывает,
насколько сам регулятор уверен. Широкий диапазон означает высокую неопределённость.
Важно и то, что прогноз по ставке даётся как СРЕДНЕЕ за год: ставка 14,5–14,6% в среднем
за год допускает и 16% в начале, и 12% в конце. Из среднего нельзя прочитать траекторию.</p>
${next ? `<h2>Ближайшее заседание</h2>
<p>Следующее решение по ключевой ставке — ${escapeHtml(ruDate(next.date) || next.date)}${
    next.time ? `, около ${escapeHtml(next.time)}` : ""}.
Полный график и какие заседания опорные — на странице
<a href="/zasedaniya-tsb/">заседаний ЦБ по ключевой ставке</a>.</p>` : ""}
<p>Текущие значения показателей с графиками — в
<a href="/statistika/klyuchevaya-stavka/">ключевой ставке</a> и
<a href="/statistika/inflyatsiya/">инфляции</a>; как это складывается в общую картину —
в <a href="/makroobzor-rossiyskoy-ekonomiki/">макроэкономике России</a>.</p>`;

  return pageShell({
    title: "Среднесрочный прогноз Банка России: ставка, инфляция, ВВП — Basis",
    desc: truncate(`Среднесрочный прогноз Банка России${asOf ? ` от ${asOf}` : ""}: ключевая ставка, `
      + `инфляция и рост ВВП по годам. Что означают диапазоны и как их читать инвестору.`, 200),
    canonicalPath: "/prognoz-banka-rossii/",
    breadcrumbs: [{ label: "Basis", href: "/" }, { label: "Прогноз Банка России" }],
    bodyHtml: body, assets, note: DEFAULT_NOTE,
  });
}

function cbMeetingsPage(meetings, fc, assets) {
  if (!meetings || !meetings.length) return null;
  const today = new Date().toISOString().slice(0, 10);
  const sorted = [...meetings].sort((a, b) => String(a.date).localeCompare(String(b.date)));
  const rows = sorted.map((m) => {
    const key = /опорное/i.test(String(m.title || ""));
    const past = String(m.date) < today;
    return `<tr><td>${escapeHtml(ruDate(m.date) || m.date)}</td>`
      + `<td>${key ? "опорное, с публикацией прогноза" : "обычное"}</td>`
      + `<td>${past ? "прошло" : "предстоит"}</td></tr>`;
  }).join("");
  const next = sorted.find((m) => String(m.date) >= today);

  const body = `
<p class="tag">Календарь Basis · денежная политика</p>
<h1>Заседания ЦБ по ключевой ставке в 2026 году</h1>
<p class="sub">${next
    ? `Ближайшее решение — ${escapeHtml(ruDate(next.date) || next.date)}${next.time ? `, около ${escapeHtml(next.time)}` : ""}.`
    : "График заседаний Совета директоров Банка России по ключевой ставке."}</p>
<table><thead><tr><th>Дата</th><th>Тип заседания</th><th>Статус</th></tr></thead><tbody>${rows}</tbody></table>
<h2>Чем опорное заседание отличается от обычного</h2>
<p>Опорных заседаний четыре в год. На них ЦБ не только меняет или сохраняет ставку, но и
публикует обновлённый <a href="/prognoz-banka-rossii/">среднесрочный прогноз</a> и
проводит пресс-конференцию. Для рынка они важнее: даже при неизменной ставке пересмотр
прогноза меняет ожидания на годы вперёд — а торгуются именно ожидания.</p>
<h2>Что происходит с рынком вокруг решения</h2>
<p>Котировки обычно двигаются заранее: к дате заседания ожидаемое решение уже заложено в
ценах. Поэтому реакция бывает сильной, когда решение расходится с ожиданиями, и почти
нулевой, когда совпадает. Сильнее всего на ставку реагируют длинные облигации и
закредитованные компании: у первых меняется цена через
<a href="/pokazateli/dyuratsiya/">дюрацию</a>, у вторых — процентные расходы.</p>
<p>Текущее значение и история решений — на странице
<a href="/statistika/klyuchevaya-stavka/">ключевой ставки</a>. Остальные события рынка —
в <a href="/kalendar-otchetnostey/">календаре</a>.</p>`;

  return pageShell({
    title: "Заседания ЦБ по ключевой ставке 2026: график и даты — Basis",
    desc: "График заседаний Банка России по ключевой ставке в 2026 году: все даты, какие "
      + "заседания опорные и чем они важнее для рынка.",
    canonicalPath: "/zasedaniya-tsb/",
    breadcrumbs: [{ label: "Basis", href: "/" }, { label: "Заседания ЦБ" }],
    bodyHtml: body, assets, note: DEFAULT_NOTE,
  });
}


// ─── Институциональная среда ────────────────────────────────────────────────────────
// 🔴 ЦЕЛИМСЯ НЕ В СЛОВО «ИНСТИТУТЫ». Замер спроса 2026-07-31: запрос «институты» широкий,
// но это «институты культуры», «институты ФСБ», «институты Санкт-Петербурга список» —
// люди ищут вузы и организации, а не институциональную среду экономики. Гнаться за ним
// значит собирать трафик, которому мы не нужны. Целимся в «институциональная среда»
// (средний спрос, точное намерение) и в «санкции против россии» (широкий) — санкционный
// фон занимает заметную часть содержания самих алертов.
function institutionsPage(alerts, assets) {
  if (!alerts || alerts.length < 3) return null;
  const sorted = [...alerts].sort((a, b) => String(b.date || "").localeCompare(String(a.date || "")));
  const asOf = ruDate(sorted[0]._as_of || sorted[0].date);
  const items = sorted.slice(0, 10).map((a) => `<li><b>${escapeHtml(strip(String(a.title || "")))}</b>
${a.date ? `<span class="tag">${escapeHtml(ruDate(a.date) || a.date)}</span>` : ""}
${a.type ? `<span class="tag">${escapeHtml(String(a.type))}</span>` : ""}
${a.why_it_matters ? `<br>Почему важно: ${escapeHtml(truncate(strip(String(a.why_it_matters)), 320))}` : ""}</li>`).join("");

  const body = `
<p class="tag">Институциональная среда${asOf ? ` · обновлено ${escapeHtml(asOf)}` : ""}</p>
<h1>Институциональная среда России: что меняется для инвестора</h1>
<p class="sub">Санкции, бюджет, регулирование и защита собственности — то, что меняет
правила игры сразу для всего рынка, а не для отдельной компании.</p>
<h2>Что происходит сейчас</h2>
<ul class="news">${items}</ul>
<h2>Почему это отдельная тема, а не часть макроэкономики</h2>
<p>Макропоказатели отвечают на вопрос «в какой фазе экономика», институциональная
среда — на вопрос «по каким правилам она работает и насколько эти правила устойчивы».
Инфляцию можно прогнозировать по данным; вероятность изъятия актива, нового санкционного
пакета или разворота регулирования по данным не считается — но на цену влияет сильнее
любого мультипликатора. Поэтому мы держим этот слой отдельно и помечаем как суждение,
а не как расчёт.</p>
<h2>Как это доходит до конкретной бумаги</h2>
<p>Институциональный фон входит в оценку тремя путями: через требуемую доходность
(выше риск — выше планка, а значит ниже <a href="/spravedlivaya-tsena-aktsiy/">справедливая
цена</a>), через денежный поток (санкции на экспорт или логистику режут выручку) и через
мультипликатор (рынок готов платить меньше за ту же прибыль). У каждой компании этот
расчёт свой — он в разделе «Институты» её карточки, например
у <a href="/company/GAZP/">Газпрома</a> или <a href="/company/SBER/">Сбербанка</a>.</p>
<p>Смежное: <a href="/geopolitika-i-rossiyskiy-rynok/">геополитическая обстановка</a> —
внешний контур тех же рисков, <a href="/novosti-geopolitiki/">новости геополитики</a> —
события по мере поступления, <a href="/makroobzor-rossiyskoy-ekonomiki/">макроэкономика
России</a> — цифры, на которые всё это ложится.</p>`;

  return pageShell({
    title: "Институциональная среда России: санкции, бюджет, регулирование — Basis",
    desc: "Что меняется в правилах игры для инвестора: санкционные пакеты, бюджет, "
      + "регулирование и защита собственности — с пояснением, почему каждое событие важно.",
    canonicalPath: "/institutsionalnaya-sreda/",
    breadcrumbs: [{ label: "Basis", href: "/" }, { label: "Институциональная среда" }],
    bodyHtml: body, assets, note: DEFAULT_NOTE,
  });
}


// ─── Живые блоки для лендингов Обозревателя ─────────────────────────────────────────
// Переименовать заголовок мало: страницы макро и гео весили 232 и 249 слов, а тонкую
// страницу поиск не поднимет, каким бы точным ни был тайтл. Здесь к ним добавляется то,
// ради чего человек и заходит — текущее состояние в цифрах. Данные из снапшотов,
// обновляются на каждой сборке.
function macroLiveBlock(macro) {
  // Коды и МЕТРИКИ берём как они есть в данных: у ставки это values.level, у инфляции
  // и ВВП — values.yoy (уровня там нет вовсе). Слепое обращение к level давало пустую
  // таблицу, и блок молча не выводился.
  // Номинальную зарплату НЕ показываем: в данных у неё значение 101600 при единице «%» —
  // дефект источника, выводить такое на витрину нельзя.
  const want = [
    ["key_rate", "level"], ["inflation", "yoy"], ["inflation_expectations", "level"],
    ["gdp", "yoy"], ["usdrub", "level"], ["cnyrub", "level"],
    ["unemployment", "level"], ["urals", "level"], ["pmi_composite", "level"],
  ];
  const rows = [];
  for (const [code, metric] of want) {
    const ind = (macro || []).find((m) => m.code === code);
    const lvl = ind && ind.values && ind.values[metric];
    if (!lvl || lvl.value == null) continue;
    // Источник отдаёт курс как 79.8573 — на витрине это выглядит как машинный вывод,
    // а не как показатель. Два знака достаточно для любой из этих величин.
    // Единицы приходят как есть из источника («usd», «п», «ед») — на витрине приводим
    // к человеческому виду, иначе таблица выглядит выгрузкой из базы.
    const UNITS = { usd: "$", eur: "€", "руб": "₽", "ед": "ед.", "п": "п.",
      "трлн руб": "трлн ₽", "млрд руб": "млрд ₽" };
    const unit = lvl.unit ? (UNITS[String(lvl.unit)] || String(lvl.unit)) : "";
    const val = `${Number(lvl.value).toLocaleString("ru-RU", { maximumFractionDigits: 2 })}`
      + `${unit ? ` ${unit}` : ""}`;
    const chg = typeof lvl.change === "number" && lvl.change !== 0
      ? `${lvl.change > 0 ? "+" : "−"}${Number(Math.abs(lvl.change)).toLocaleString("ru-RU",
          { maximumFractionDigits: 2 })}` : "—";
    rows.push(`<tr><td>${escapeHtml(ind.title || code)}</td><td class="num">${escapeHtml(val)}</td>`
      + `<td class="num">${escapeHtml(chg)}</td><td>${escapeHtml(ruDate(lvl.as_of) || "—")}</td></tr>`);
  }
  if (rows.length < 3) return "";
  return `<h2>Что происходит в экономике сейчас</h2>
<table><thead><tr><th>Показатель</th><th class="num">Значение</th><th class="num">Изменение</th><th>На дату</th></tr></thead>
<tbody>${rows.join("")}</tbody></table>
<p class="sub">Значения обновляются автоматически из официальных источников; полный набор
показателей с графиками — в <a href="/ekonomicheskaya-statistika-rossii/">экономической
статистике</a>. Официальный ориентир регулятора на годы вперёд —
в <a href="/prognoz-banka-rossii/">среднесрочном прогнозе Банка России</a>, ближайшее
решение по ставке — в <a href="/zasedaniya-tsb/">графике заседаний ЦБ</a>.</p>
<p>Свежие события экономики с разбором, что каждое меняет, — в ленте
<a href="/novosti-ekonomiki/">новостей экономики</a>.</p>`;
}

function geoLiveBlock(geo) {
  if (!geo) return "";
  const SC = {
    S1_breakthrough: "Прорыв: устойчивое урегулирование",
    S2_ceasefire: "Перемирие или заморозка конфликта",
    S3_attrition: "Затяжное противостояние без развязки",
    S4_escalation: "Эскалация",
  };
  const sc = geo.scenarios || {};
  const scRows = Object.keys(SC).filter((k) => sc[k])
    .map((k) => `<tr><td>${escapeHtml(SC[k])}</td><td class="num">${
      escapeHtml(String(sc[k]).replace(/\s*\(Δ[^)]*\)/, ""))}</td></tr>`).join("");

  const reg = geo.regions || {};
  const regRows = Object.keys(reg).slice(0, 4).map((k) => {
    const r = reg[k] || {};
    return `<li><b>${escapeHtml(strip(String(r.label || k)))}</b>${
      r.summary ? `<br>${escapeHtml(truncate(strip(String(r.summary)), 300))}` : ""}</li>`;
  }).join("");

  const parts = [];
  if (geo.summary) {
    parts.push(`<h2>Главное сейчас</h2><p>${escapeHtml(truncate(strip(String(geo.summary)), 700))}
<span class="tag">суждение аналитика</span></p>`);
  }
  if (scRows) {
    parts.push(`<h2>Сценарии и их вероятность</h2>
<table><thead><tr><th>Сценарий</th><th class="num">Вероятность (6 мес / 18 мес)</th></tr></thead>
<tbody>${scRows}</tbody></table>
<p class="sub">Вероятности — оценка модели Basis, а не прогноз событий. Смысл не в самих
процентах, а в том, какой сценарий рынок закладывать не спешит: расхождение между
ожиданиями рынка и этой картиной и есть источник риска.</p>`);
  }
  if (regRows) parts.push(`<h2>По очагам напряжённости</h2><ul class="news">${regRows}</ul>`);
  if (!parts.length) return "";
  parts.push(`<p>События по мере поступления — в ленте
<a href="/novosti-geopolitiki/">новостей геополитики</a>; как геополитика доходит до
конкретной бумаги — в разделе «Геополитика» карточки компании, например
у <a href="/company/GAZP/geo/">Газпрома</a>. Внутренний контур тех же рисков —
<a href="/institutsionalnaya-sreda/">институциональная среда</a>.</p>`);
  return parts.join("\n");
}

function glossaryPage(spec, companies, assets) {
  const label = spec.label;
  const lower = label.toLowerCase();
  const fmtFor = (c, v) => spec.unit
    ? `${Number(v).toLocaleString("ru-RU", { minimumFractionDigits: spec.decimals || 0,
        maximumFractionDigits: spec.decimals || 0 }).replace("-", "−")}${
        spec.unit === "%" ? " %" : spec.unit}`
    : fmtMoney(v, c.unit, c.currency);

  // Примеры берём по убыванию: у денежных показателей это крупнейшие компании рынка —
  // те, которые читатель узнаёт, и по которым проще понять порядок величин.
  const rows = [];
  for (const c of companies) {
    const pts = metricSeries(c, spec);
    if (pts && pts.length) rows.push({ c, v: pts[pts.length - 1].value, year: pts[pts.length - 1].year });
  }
  rows.sort((a, b) => b.v - a.v);
  const top = rows.slice(0, 12);

  // «Что такое Долговая нагрузка» — заглавная посреди фразы. Опускаем регистр, но не у
  // аббревиатур: «что такое ebitda» выглядело бы неряшливо, а ROE вообще потеряло бы смысл.
  const titleLabel = /^[A-ZА-Я]{2,}/.test(label)
    ? label : label.charAt(0).toLowerCase() + label.slice(1);
  const title = `Что такое ${titleLabel} — ${spec.formula ? "формула, " : ""}простыми словами | Basis`;
  const desc = truncate(`${titleLabel} — что это простыми словами${spec.formula ? `, формула расчёта` : ""}, `
    + `как читать и на что смотреть рядом. Плюс значения по ${rows.length} российским компаниям.`, 200);

  const body = `
<p class="tag">Показатели · справочник Basis</p>
<h1>${escapeHtml(label)}: что это простыми словами</h1>
<p class="sub">${escapeHtml(spec.simple || spec.what)}</p>
${spec.formula ? `<h2>Формула</h2>
<p class="formula"><b>${escapeHtml(label)} = ${escapeHtml(spec.formula)}</b></p>` : ""}
<h2>Что показывает</h2>
<p>${escapeHtml(spec.what)}</p>
<h2>Как читать и где легко ошибиться</h2>
<p>${escapeHtml(spec.caveat)}</p>
<h2>${escapeHtml(label)} российских компаний</h2>
<p>Значения из последней отчётности${top.length ? ` (${top[0].year} год у большинства компаний)` : ""}.
По каждой компании — динамика за все годы и сравнение с сектором.</p>
<table><thead><tr><th>Компания</th><th>${escapeHtml(label)}</th></tr></thead><tbody>${
    top.map((r) => `<tr><td><a href="/company/${r.c.ticker}/${spec.slug}/">${
      escapeHtml(r.c.short)} (${r.c.ticker})</a></td><td>${escapeHtml(fmtFor(r.c, r.v))}</td></tr>`).join("")
  }</tbody></table>
<p class="sub">Всего показатель посчитан по ${plural(rows.length, "компании", "компаниям", "компаниям")}
из ${companies.length} на платформе. Там, где данных в отчётности не хватает, мы ставим
прочерк, а не оценку — подставлять сюда догадку было бы хуже, чем признать пробел.</p>
<h2>Другие показатели</h2>
<div class="grid">${METRIC_PAGES.filter((m) => m.slug !== spec.slug && m.formula)
    .map((m) => `<a class="chip" href="/pokazateli/${m.slug}/">${escapeHtml(m.label)}</a>`).join("")}</div>
<a class="cta" href="/skrining-aktsiy/">Отобрать акции по этому показателю →</a>`;

  return pageShell({
    title, desc, canonicalPath: `/pokazateli/${spec.slug}/`,
    jsonLd: [{
      "@type": "DefinedTerm",
      "@id": `${_SITE}/pokazateli/${spec.slug}/#term`,
      name: label,
      description: spec.simple || spec.what,
      inDefinedTermSet: { "@id": `${_SITE}/pokazateli/#set` },
    }],
    breadcrumbs: [{ label: "Basis", href: "/" }, { label: "Показатели", href: "/pokazateli/" },
      { label }],
    bodyHtml: body, assets, note: DEFAULT_NOTE,
  });
}

function fairValuePage(c, fv, dateIso, assets, tabsWritten, sectorAll, fairValues) {
  const money = (v) => Number(v).toLocaleString("ru-RU",
    { minimumFractionDigits: 2, maximumFractionDigits: 2 }).replace("-", "−") + " ₽";
  const up = typeof fv.upside_pct === "number" ? Math.round(fv.upside_pct) : null;
  const verdict = up == null ? "оценка есть, потенциал не рассчитан"
    : up > 0 ? `на ${up}% выше рынка` : `на ${Math.abs(up)}% ниже рынка`;
  // Без хвостового «г.»: оно уже заканчивается точкой, и в конце предложения выходило
  // «Расчёт на 31 июля 2026 г..» с двойной точкой.
  const asOf = dateIso ? new Date(dateIso).toLocaleDateString("ru-RU",
    { day: "numeric", month: "long", year: "numeric" }).replace(/\s*г\.\s*$/, "") : null;
  const byModel = fv.source === "bfv";

  // Контекст сектора: один потенциал без фона читается как приговор компании, хотя при
  // ставке 16-18% отрицательный потенциал — норма почти для всего рынка. Показываем,
  // сколько бумаг сектора в том же положении, чтобы число не выглядело личной бедой.
  const peers = (sectorAll || [])
    .map((p) => ({ p, f: fairValues[p.ticker] }))
    .filter((x) => x.f && typeof x.f.upside_pct === "number");
  let sectorHtml = "";
  if (peers.length >= 3) {
    const below = peers.filter((x) => x.f.upside_pct < 0).length;
    const sorted = peers.map((x) => x.f.upside_pct).slice().sort((a, b) => a - b);
    const med = sorted.length % 2 ? sorted[(sorted.length - 1) / 2]
      : (sorted[sorted.length / 2 - 1] + sorted[sorted.length / 2]) / 2;
    const top = peers.slice().sort((a, b) => b.f.upside_pct - a.f.upside_pct).slice(0, 6);
    sectorHtml = `<h2>Как это выглядит на фоне сектора</h2>
<p>По сектору «${escapeHtml(c.sectorFull || c.sector)}» медианный потенциал —
${String(Math.round(med)).replace("-", "−")}%; оценка ниже текущей цены у
${plural(below, "компании", "компаний", "компаний")} из ${peers.length}. При высокой
ключевой ставке это ожидаемо: планка входа поднимается у всего рынка сразу, а не у
отдельной бумаги.</p>
<table><thead><tr><th>Компания</th><th>Потенциал</th></tr></thead><tbody>${
      top.map((x) => `<tr><td><a href="/company/${x.p.ticker}/spravedlivaya-tsena/">${
        escapeHtml(x.p.short)}</a></td><td>${x.f.upside_pct > 0 ? "+" : "−"}${
        Math.abs(Math.round(x.f.upside_pct))}%</td></tr>`).join("")
    }</tbody></table>`;
  }

  // Имя-первым по той же причине, что на страницах метрик: «справедливая цена акций
  // Сбербанк» безграмотно (нужен родительный падеж, а склонять названия автоматически
  // нельзя), «Сбербанк (SBER): справедливая цена акций» читается верно и ловит тот же
  // запрос — поисковик сопоставляет слова, а не падежи.
  const title = `${titleName(c)} (${c.ticker}): справедливая цена акций — оценка Basis | Basis`;
  const desc = truncate(`Справедливая цена акций — ${c.short} (${c.ticker}) по методике Basis — `
    + `${money(fv.fair_value)}${up != null ? `, ${verdict}` : ""} при цене ${money(fv.price)}`
    + `${asOf ? ` на ${asOf}` : ""}. Как считается и что это число не означает.`, 200);

  const body = `
<p class="tag">${escapeHtml(c.sectorFull || c.sector)} · MOEX: ${c.ticker}</p>
<h1>${escapeHtml(c.short)} <span style="color:var(--faint)">(${escapeHtml(c.ticker)})</span>: справедливая цена акций</h1>
<p class="sub">Оценка Basis — <b>${escapeHtml(money(fv.fair_value))}</b> за акцию при рыночной цене
${escapeHtml(money(fv.price))}${up != null ? `, то есть ${escapeHtml(verdict)}` : ""}.
${asOf ? `Расчёт на ${escapeHtml(asOf)}.` : ""} <span class="tag">оценка модели</span></p>
<table><thead><tr><th>Показатель</th><th>Значение</th></tr></thead><tbody>
<tr><td>Справедливая цена</td><td>${escapeHtml(money(fv.fair_value))}</td></tr>
<tr><td>Цена на момент расчёта</td><td>${escapeHtml(money(fv.price))}</td></tr>
<tr><td>Потенциал</td><td>${up == null ? "—" : (up > 0 ? "+" : "−") + Math.abs(up) + "%"}</td></tr>
<tr><td>Метод</td><td>${byModel ? "модель Basis (BFV)" : "оценка аналитика"}</td></tr>
</tbody></table>
<h2>Как читать это число</h2>
<p>${escapeHtml(FV_NOTE)}</p>
<h2>Как считается</h2>
<p>${byModel
    ? "Методика Basis идёт от требуемой доходности, а не от консенсуса аналитиков. За точку "
      + "отсчёта берётся доходность ОФЗ на сопоставимый срок — безрисковая альтернатива, "
      + "которая доступна инвестору прямо сейчас. К ней добавляется премия за риск: "
      + "макроэкономический, отраслевой и специфический для компании. Полученная планка "
      + "требуемой доходности накладывается на способность бизнеса генерировать поток — "
      + "дивиденды и балансовый капитал либо свободный денежный поток, в зависимости от "
      + "того, что для компании показательнее. Отсюда и получается цена, при которой "
      + "вложение оправдано."
    : "По этой бумаге модель не дала устойчивого результата — обычно так бывает при "
      + "убытке, отрицательном капитале или слишком короткой истории отчётности. "
      + "Показана оценка аналитика, полученная сравнительным методом. Это менее строгий "
      + "путь, и относиться к числу стоит осторожнее."}</p>
<p>Число пересчитывается автоматически: оно зависит от текущей цены и от кривой
доходности ОФЗ, поэтому меняется вместе с рынком. На этой странице — снимок${
    asOf ? ` на ${escapeHtml(asOf)}` : ""}; актуальное значение всегда
<a href="/company/${c.ticker}/">на карточке компании</a>.</p>
${sectorHtml}
<h2>Чем подкреплена оценка</h2>
<p>Оценка опирается на отчётность компании, а не на настроение рынка. Основные величины,
которые в неё входят, разобраны отдельно:
<a href="/company/${c.ticker}/vyruchka/">выручка</a>,
<a href="/company/${c.ticker}/chistaya-pribyl/">чистая прибыль</a>,
<a href="/company/${c.ticker}/dividends/">дивиденды</a> и
<a href="/company/${c.ticker}/finance/">полный разбор отчётности</a>.
Что за бизнес стоит за этими цифрами — в
<a href="/company/${c.ticker}/business/">разборе бизнес-модели</a>.</p>
<a class="cta" href="/company/${c.ticker}/">Открыть разбор ${escapeHtml(c.short)} в Basis →</a>`;

  return pageShell({
    title, desc, canonicalPath: `/company/${c.ticker}/spravedlivaya-tsena/`,
    breadcrumbs: [
      { label: "Basis", href: "/" },
      { label: "Компании", href: "/company/" },
      { label: `${c.short} (${c.ticker})`, href: `/company/${c.ticker}/` },
      { label: "Справедливая цена" },
    ],
    bodyHtml: body, assets, note: DEFAULT_NOTE,
  });
}

function metricPage(c, spec, pts, assets, tabsWritten, sectorAll) {
  const isBank = c.profile === "bank";
  const label = isBank && spec.bankLabel ? spec.bankLabel : spec.label;
  const short = spec.shortLabel || label;
  const last = pts[pts.length - 1], first = pts[0];
  // Деньги, проценты и «разы» форматируются по-разному: ROE 11,19 % нельзя печатать
  // как «11 млрд ₽», а долговую нагрузку 0,16× — как деньги.
  const fmt = (v) => spec.unit
    ? `${Number(v).toLocaleString("ru-RU", { minimumFractionDigits: spec.decimals || 0,
        maximumFractionDigits: spec.decimals || 0 }).replace("-", "−")}${
        spec.unit === "%" ? " %" : spec.unit}`
    : fmtMoney(v, c.unit, c.currency);
  // Род согласуем с названием показателя: «долговая нагрузка выросла», но «чистый долг вырос».
  const fem = /^(выручка|чистая прибыль|долговая нагрузка|рентабельность|ebitda)/i.test(short);
  const dir = last.value > first.value ? (fem ? "выросла" : "вырос")
    : last.value < first.value ? (fem ? "снизилась" : "снизился")
    : (fem ? "не изменилась" : "не изменился");
  // 🔴 У показателей, которые САМИ измеряются в процентах (ROE) или в разах (долговая
  // нагрузка), относительное изменение вводит в заблуждение: ROE 22,6 % → 23,8 % это
  // +1,2 процентных пункта, а не «+5 %». Для них считаем абсолютную разницу.
  const isRelative = !spec.unit;
  const pct = isRelative
    ? (first.value ? Math.round((last.value / first.value - 1) * 100) : null)
    : null;
  const absDelta = isRelative ? null : (last.value - first.value);
  const deltaText = isRelative
    ? (pct != null ? ` на ${Math.abs(pct)}%` : "")
    : (absDelta ? ` на ${Math.abs(absDelta).toLocaleString("ru-RU", {
        minimumFractionDigits: spec.decimals || 0, maximumFractionDigits: spec.decimals || 0 })}`
        + (spec.unit === "%" ? " п.п." : spec.unit) : "");
  // Имя-первым: «EBITDA Северсталь» безграмотно (нужен родительный падеж, а склонять
  // названия автоматически нельзя). «Северсталь (CHMF): EBITDA по годам» читается верно
  // и ловит тот же запрос — поисковик сопоставляет слова, а не падежи.
  const title = `${titleName(c)} (${c.ticker}): ${short} по годам — ${fmt(last.value)} за ${last.year} | Basis`;
  const desc = truncate(`${c.short} (${c.ticker}), ${label.toLowerCase()} за ${last.year} — ${fmt(last.value)}. `
    + `Динамика ${first.year}–${last.year}: ${dir}${deltaText}${/\.$/.test(deltaText) ? " " : ". "}`
    + `Данные из отчётности с разбором, что это значит.`, 200);

  const rowsHtml = pts.slice().reverse().map((p, i, a) => {
    const prev = a[i + 1];
    let cell = "—";
    if (prev) {
      if (isRelative && prev.value) {
        const d = Math.round((p.value / prev.value - 1) * 100);
        cell = (d > 0 ? "+" : "") + d + "%";
      } else if (!isRelative) {
        const d = p.value - prev.value;
        const body = Math.abs(d).toLocaleString("ru-RU", {
          minimumFractionDigits: spec.decimals || 0, maximumFractionDigits: spec.decimals || 0 });
        cell = (d > 0 ? "+" : d < 0 ? "−" : "") + body + (spec.unit === "%" ? " п.п." : spec.unit);
      }
    }
    return `<tr><td>${p.year}</td><td>${escapeHtml(fmt(p.value))}</td><td>${cell}</td></tr>`;
  }).join("");

  // 🔴 Только те показатели, страницы которых у ЭТОЙ компании реально созданы. Раньше
  // блок «Другие показатели» перечислял весь список METRIC_PAGES, и у компаний без
  // части данных (ZVEZ, MFGSP, VRSBP…) ссылки вели в никуда — 36 битых ссылок на
  // сорока проверенных страницах. Условие тут ровно то же, что при генерации.
  const others = METRIC_PAGES.filter((m) => m.slug !== spec.slug && metricSeries(c, m));
  const body = `
<p class="tag">${escapeHtml(c.sectorFull || c.sector)} · MOEX: ${c.ticker}</p>
<h1>${escapeHtml(c.short)} <span style="color:var(--faint)">(${escapeHtml(c.ticker)})</span>: ${escapeHtml(short.toLowerCase())} по годам</h1>
<p class="sub">${escapeHtml(label)} за ${last.year} — <b>${escapeHtml(fmt(last.value))}</b>.
За ${first.year}–${last.year} ${dir}${deltaText}${/\.$/.test(deltaText) ? "" : "."}</p>
<h2>${escapeHtml(label)} по годам</h2>
<table><thead><tr><th>Год</th><th>${escapeHtml(label)}</th><th>Изм. г/г</th></tr></thead>
<tbody>${rowsHtml}</tbody></table>
<p class="sub">Данные из отчётности компании${c.standard ? ` (${escapeHtml(c.standard)})` : ""}.</p>
<h2>Что такое ${escapeHtml(label.toLowerCase())}</h2>
<p>${escapeHtml(spec.what)}</p>
<h2>Как читать этот показатель</h2>
<p>${escapeHtml(spec.caveat)}</p>
${spec.note ? `<p>${escapeHtml(spec.note(c, pts, last.value))}</p>` : ""}
${pts.droppedYears && pts.droppedYears.length ? `<p>За ${pts.droppedYears.join(", ")} `
  + `показатель не рассчитывается: EBITDA отрицательна, то есть компания убыточна уже на `
  + `операционном уровне. Отношение долга к ней в такой ситуации смысла не имеет — `
  + `это не отсутствие долга, а невозможность обслуживать его текущей прибылью.</p>` : ""}
${sectorContext(c, spec, last.value, sectorAll || [], fmt)}
<p>Полная отчётность ${escapeHtml(c.short)} — выручка, расходы, баланс, денежные потоки,
мультипликаторы и расчёт справедливой цены — на странице
<a href="/company/${c.ticker}/finance/">разбора отчётности</a>. Что за бизнес стоит за
этими цифрами — в <a href="/company/${c.ticker}/business/">разборе бизнес-модели</a>.</p>
<h2>Другие показатели ${escapeHtml(c.short)}</h2>
<div class="grid">${others.map((m) =>
    `<a class="chip" href="/company/${c.ticker}/${m.slug}/">${escapeHtml(m.bankLabel && isBank ? m.bankLabel : m.label)}</a>`).join("")}
<a class="chip" href="/company/${c.ticker}/">Полный разбор ${escapeHtml(c.ticker)}</a></div>
<a class="cta" href="/company/${c.ticker}/finance/">Открыть финансы ${escapeHtml(c.short)} в Basis →</a>`;

  return pageShell({
    title, desc, canonicalPath: `/company/${c.ticker}/${spec.slug}/`,
    breadcrumbs: [{ label: "Basis", href: "/" }, { label: "Компании", href: "/company/" },
      { label: `${c.short} (${c.ticker})`, href: `/company/${c.ticker}/` }, { label }],
    bodyHtml: body, assets,
    jsonLd: [{
      "@type": "Dataset", name: `${label} ${c.short} (${c.ticker}) по годам`,
      description: desc, url: `${_SITE}/company/${c.ticker}/${spec.slug}/`,
      creator: { "@type": "Organization", name: "Basis", url: _SITE },
    }],
    note: DEFAULT_NOTE,
  });
}

/* ------------------------- интент-лендинги ------------------------- */
// Статические страницы под информационные запросы («проанализировать портфель»,
// «скринер облигаций», «карта рынка»...) — тексты в scripts/seo-landings-content.js.
//
// 🔴 2026-07-31: лендинги стали ГИБРИДНЫМИ — как карточки компаний (статика + приложение
// поверх). Раньше это была чистая статика без бандла, и из-за этого разделы платформы
// жили на двух разных адресах: человекочитаемом /karta-rynka-aktsiy/ (статика, её видит
// поиск) и служебном /?view=overview&obs=maps (приложение). Владелец поймал следствие:
// «вбиваю „карта рынка basis“ — в выдаче не „Карта рынка“, а общее название платформы»,
// потому что по служебному адресу отдаётся общий index.html с общим тайтлом.
// Теперь адрес один: с него и робот получает нужный заголовок с текстом, и человек
// попадает сразу в нужный раздел приложения (App.js разбирает слаг → LANDING_ROUTES).
function landingPage(l, assets) {
  const faqHtml = l.faq && l.faq.length
    ? `<h2>Частые вопросы</h2>\n` + l.faq.map((f) =>
        `<h3>${escapeHtml(f.q)}</h3>\n<p>${escapeHtml(f.a)}</p>`).join("\n")
    : "";
  const others = LANDINGS.filter((x) => x.slug !== l.slug);
  const relatedHtml = `<h2>Инструменты и методики Basis</h2><div class="grid">${
    others.map((x) => `<a class="chip" href="/${x.slug}/">${escapeHtml(x.crumb)}</a>`).join("")
  }<a class="chip" href="/company/">Разборы 264 компаний</a></div>`;
  const body = `
<p class="tag">Basis · инструменты инвестора</p>
<h1>${escapeHtml(l.h1)}</h1>
<p class="sub">${escapeHtml(l.lead)}</p>
${l.body}
${faqHtml}
<!-- rel="nofollow": CTA ведёт в приложение по адресу с параметрами (/?view=portfolio).
     Чистого адреса-альтернативы у него нет — сам лендинг им и является. Без nofollow
     робот заводит адрес с параметрами отдельной страницей: в выгрузке Вебмастера от
     29.07 такие уже есть (?company=SBER&tab=finance получил статус SEARCHABLE, то есть
     попал в поиск дублем нашей же карточки). -->
<a class="cta" rel="nofollow" href="${escapeHtml(l.appHref)}">${escapeHtml(l.appLabel)} →</a>
${relatedHtml}`;
  // WebPage теперь описывается в pageShell единообразно для ВСЕХ страниц (с @id и
  // связью с WebSite), поэтому свой дубль лендинга убран — две сущности WebPage на одной
  // странице поисковик разбирает хуже, чем одну.
  const ld = [];
  if (l.faq && l.faq.length) {
    ld.push({
      "@type": "FAQPage",
      mainEntity: l.faq.map((f) => ({
        "@type": "Question", name: f.q,
        acceptedAnswer: { "@type": "Answer", text: f.a },
      })),
    });
  }
  return pageShell({
    title: l.title, desc: l.description,
    canonicalPath: `/${l.slug}/`,
    breadcrumbs: [{ label: "Basis", href: "/" }, { label: l.crumb }],
    bodyHtml: body,
    jsonLd: ld,
    assets,   // приложение поверх статики — адрес раздела теперь один для робота и человека
    note: `Basis — аналитический слой для частного инвестора, не брокер:
не проводит сделок и не даёт сигналов «купить/продать». Материалы страницы — рамка
оценки и описание инструментов платформы; они не являются индивидуальной
инвестиционной рекомендацией.`,
  });
}

// Короткий URL /TICKER/ → канонический /company/TICKER/. Мягкий редирект (нет
// доступа к серверу раздачи статики на Timeweb, см. work-journal — прод отдаёт
// Caddy, наш nginx.conf там не участвует, кастомных 301 мы настроить не можем):
// meta-refresh (сработает без JS) + JS location.replace (мгновенно с JS) +
// canonical на целевой URL + noindex (сама эта страница — не результат, не должна
// попасть в выдачу отдельно от /company/T/) чтобы не плодить дубли в индексе.
// НЕ в sitemap — она промежуточная прокладка, п.9 требования: sitemap только
// «реальные» URL.
const RESERVED_ROOT_PATHS = new Set(["COMPANY", "STATIC", "API"]);
function shortRedirectPage(c) {
  const target = `/company/${c.ticker}/`;
  const url = _SITE + target;
  return `<!doctype html>
<html lang="ru">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>${escapeHtml(c.short)} (${c.ticker}) — Basis</title>
<link rel="canonical" href="${url}">
<meta name="robots" content="noindex, follow">
<meta http-equiv="refresh" content="0; url=${target}">
<script>location.replace(${JSON.stringify(target)});</script>
</head>
<body>
<p><a href="${target}">${escapeHtml(c.short)} (${c.ticker}) — открыть на Basis</a></p>
</body>
</html>`;
}

/* --------------------------- sitemap --------------------------- */

// lastmod у каждого URL свой (дата последнего изменения ДАННЫХ, не сборки) —
// аудит 2026-07-26 п.5: одинаковый lastmod=дата сборки у всех URL подрывает
// доверие поисковиков к sitemap и ломает приоритет переобхода.
function writeSitemap(urls) {
  const xml = `<?xml version="1.0" encoding="UTF-8"?>
<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">
${urls.map((u) => `  <url><loc>${u.loc}</loc><lastmod>${u.lastmod || _TODAY}</lastmod><changefreq>${u.freq}</changefreq><priority>${u.pri}</priority></url>`).join("\n")}
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
  const assets = loadAppAssets();
  if (!assets) console.log("⚠️  asset-manifest.json/main.js не найден — страницы без live-приложения (только статика)");
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
  let metricPagesCount = 0;
  let fairValuePagesCount = 0;
  let observerCount = 0;

  // Справедливая цена: снимок с боевого API (обновляется на каждой сборке). Держим
  // отдельно от financials.json, потому что число ЖИВОЕ — оно пересчитывается от
  // текущей цены и кривой ОФЗ, в файлах отчётности его нет и быть не может.
  // Ближайшие объявленные выплаты — под запросы «дивиденды X 2026 дата выплаты».
  let upcomingDivs = {};
  try {
    const raw = JSON.parse(fs.readFileSync(
      path.join(__dirname, "data", "dividend-calendar-snapshot.json"), "utf8"));
    for (const r of raw.rows || []) {
      // на бумагу может быть несколько объявлений — держим ближайшее по дате
      const prev = upcomingDivs[r.ticker];
      if (!prev || String(r.date) < String(prev.date)) upcomingDivs[r.ticker] = r;
    }
  } catch { /* нет снимка — блок ближайшей выплаты просто не выводится */ }
  DIVIDEND_CALENDAR = upcomingDivs;

  let fairValues = {}, fairValueDate = null;
  try {
    const fvRaw = JSON.parse(fs.readFileSync(
      path.join(__dirname, "data", "fair-value-snapshot.json"), "utf8"));
    fairValueDate = (fvRaw.meta || {}).fetched_at || null;
    for (const r of fvRaw.rows || []) fairValues[r.ticker] = r;
    console.log(`Справедливая цена: снимок на ${Object.keys(fairValues).length} бумаг`);
  } catch {
    console.log("Справедливая цена: снимка нет — страницы оценки пропускаются");
  }

  const gitDates = loadGitFileDates();
  if (!gitDates) console.log("⚠️  git-история недоступна — lastmod из mtime файлов");

  // для склейки пар обычка/преф в статистике сектора (см. baseTicker)
  const tickerSet = new Set(companies.map((x) => x.ticker));

  for (const c of companies) {
    const lastmod = companyLastmod(c.ticker, gitDates);
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

    // ВАЖНО: два разных списка. sectorAll — ВЕСЬ сектор, на нём считаются медиана и
    // место компании: если считать по обрезанным восьми, «3-я из 6» будет прямой
    // неправдой при секторе в тридцать бумаг. peers — те же соседи, но обрезанные до
    // восьми для блока перелинковки, где длинный список только мешает.
    // Привилегированные акции — та же компания и те же цифры, что у обычки (SBER/SBERP,
    // TATN/TATNP). Считая их отдельной строкой, мы удваивали эмитента в медиане сектора
    // и показывали Сбербанк соседом самому себе в таблице на его же странице.
    const seenIssuers = new Set([baseTicker(c.ticker, tickerSet)]);
    const sectorAll = companies.filter((p) => {
      if (p.sector !== c.sector || p.ticker === c.ticker) return false;
      const base = baseTicker(p.ticker, tickerSet);
      if (seenIssuers.has(base)) return false;
      seenIssuers.add(base);
      return true;
    });
    const peers = sectorAll.slice(0, 8);

    const hubDir = path.join(_BUILD_DIR, "company", c.ticker);
    fs.mkdirSync(hubDir, { recursive: true });

    // Справедливая цена — отдельной страницей: спрос по конкретным эмитентам
    // подтверждён, а у агрегаторов такой метрики нет (у них консенсус аналитиков).
    const fv = fairValues[c.ticker];
    if (fv && typeof fv.fair_value === "number" && typeof fv.price === "number") {
      const fvDir = path.join(hubDir, "spravedlivaya-tsena");
      fs.mkdirSync(fvDir, { recursive: true });
      fs.writeFileSync(path.join(fvDir, "index.html"),
        fairValuePage(c, fv, fairValueDate, assets, tabsWritten, sectorAll, fairValues), "utf8");
      urls.push({ loc: `${_SITE}/company/${c.ticker}/spravedlivaya-tsena/`,
        freq: "weekly", pri: "0.7", lastmod });
      fairValuePagesCount++;
      tabsWritten.push({ slug: "spravedlivaya-tsena", label: "Справедливая цена" });
    }
    fs.writeFileSync(path.join(hubDir, "index.html"), hubPage(c, tabsWritten, peers, assets), "utf8");
    urls.push({ loc: `${_SITE}/company/${c.ticker}/`, freq: "weekly", pri: "0.8", lastmod });

    for (const [spec, content] of rendered) {
      const dir = path.join(hubDir, spec.slug);
      fs.mkdirSync(dir, { recursive: true });
      fs.writeFileSync(path.join(dir, "index.html"), tabPage(c, spec, content, tabsWritten, assets), "utf8");
      urls.push({ loc: `${_SITE}/company/${c.ticker}/${spec.slug}/`, freq: "monthly", pri: "0.6", lastmod });
      tabPagesCount++;
    }

    // Точечные метрики: /company/CHMF/ebitda/, /vyruchka/, /chistaya-pribyl/ —
    // под запросы вида «ebitda северстали». Только там, где ряд ≥3 лет.
    for (const spec of METRIC_PAGES) {
      const pts = metricSeries(c, spec);
      if (!pts) continue;
      const dir = path.join(hubDir, spec.slug);
      fs.mkdirSync(dir, { recursive: true });
      fs.writeFileSync(path.join(dir, "index.html"), metricPage(c, spec, pts, assets, tabsWritten, sectorAll), "utf8");
      urls.push({ loc: `${_SITE}/company/${c.ticker}/${spec.slug}/`, freq: "monthly", pri: "0.6", lastmod });
      metricPagesCount++;
    }
  }

  fs.writeFileSync(path.join(_BUILD_DIR, "company", "index.html"), indexPage(companies), "utf8");

  // Интент-лендинги разделов (v3, SEO-задача №1): /analiz-portfelya/ и др.
  // lastmod — mtime файла текстов: правка текста = реальное обновление страницы.
  const landingLastmod = fileLastmod(path.join(__dirname, "seo-landings-content.js"));
  // Живые блоки для двух лендингов Обозревателя — см. macroLiveBlock/geoLiveBlock.
  const loadRows = (f) => {
    try { return JSON.parse(fs.readFileSync(path.join(__dirname, "data", f), "utf8")).rows || []; }
    catch { return []; }
  };
  const LIVE_BLOCKS = {
    "makroobzor-rossiyskoy-ekonomiki": macroLiveBlock(loadRows("macro-snapshot.json")),
    "geopolitika-i-rossiyskiy-rynok": geoLiveBlock(loadRows("geo-barometer-snapshot.json")[0]),
  };
  for (const l of LANDINGS) {
    const dir = path.join(_BUILD_DIR, l.slug);
    fs.mkdirSync(dir, { recursive: true });
    const extra = LIVE_BLOCKS[l.slug];
    const withLive = extra ? { ...l, body: `${extra}\n${l.body}` } : l;
    fs.writeFileSync(path.join(dir, "index.html"), landingPage(withLive, assets), "utf8");
    urls.push({ loc: `${_SITE}/${l.slug}/`, freq: "monthly", pri: "0.7", lastmod: landingLastmod });
  }

  // Короткие URL /TICKER/ — редирект на канонический /company/TICKER/ (п.7 задачи).
  let shortUrlCount = 0;
  const shortUrlSkipped = [];
  for (const c of companies) {
    if (RESERVED_ROOT_PATHS.has(c.ticker.toUpperCase())) { shortUrlSkipped.push(c.ticker); continue; }
    const dir = path.join(_BUILD_DIR, c.ticker);
    fs.mkdirSync(dir, { recursive: true });
    fs.writeFileSync(path.join(dir, "index.html"), shortRedirectPage(c), "utf8");
    shortUrlCount++;
  }

  // Лендинг недооценённых — после компаний: нужны и оценки, и выручка для разделения.
  if (Object.keys(fairValues).length) {
    const dir = path.join(_BUILD_DIR, "nedootsenennye-aktsii");
    fs.mkdirSync(dir, { recursive: true });
    fs.writeFileSync(path.join(dir, "index.html"),
      undervaluedLanding(companies, fairValues, fairValueDate, assets), "utf8");
    urls.push({ loc: `${_SITE}/nedootsenennye-aktsii/`, freq: "weekly", pri: "0.8" });
  }

  // Обозреватель: тематические ленты + прогноз ЦБ + график заседаний.
  {
    const load = (f) => {
      try { return JSON.parse(fs.readFileSync(path.join(__dirname, "data", f), "utf8")).rows || []; }
      catch { return []; }
    };
    const news = load("news-snapshot.json");
    const fc = (load("cb-forecast-snapshot.json") || [])[0];
    const meetings = load("cb-meetings-snapshot.json");

    for (const cfg of NEWS_TOPICS) {
      const html = newsTopicPage(cfg, news, assets);
      if (!html) { console.log(`  ${cfg.slug}: новостей мало — страница пропущена`); continue; }
      const dir = path.join(_BUILD_DIR, cfg.slug);
      fs.mkdirSync(dir, { recursive: true });
      fs.writeFileSync(path.join(dir, "index.html"), html, "utf8");
      urls.push({ loc: `${_SITE}/${cfg.slug}/`, freq: "daily", pri: "0.8" });
      observerCount++;
    }
    const fcHtml = cbForecastPage(fc, meetings, assets);
    if (fcHtml) {
      fs.mkdirSync(path.join(_BUILD_DIR, "prognoz-banka-rossii"), { recursive: true });
      fs.writeFileSync(path.join(_BUILD_DIR, "prognoz-banka-rossii", "index.html"), fcHtml, "utf8");
      urls.push({ loc: `${_SITE}/prognoz-banka-rossii/`, freq: "weekly", pri: "0.8" });
      observerCount++;
    }
    const instHtml = institutionsPage(load("institutions-snapshot.json"), assets);
    if (instHtml) {
      fs.mkdirSync(path.join(_BUILD_DIR, "institutsionalnaya-sreda"), { recursive: true });
      fs.writeFileSync(path.join(_BUILD_DIR, "institutsionalnaya-sreda", "index.html"), instHtml, "utf8");
      urls.push({ loc: `${_SITE}/institutsionalnaya-sreda/`, freq: "weekly", pri: "0.7" });
      observerCount++;
    }
    const mHtml = cbMeetingsPage(meetings, fc, assets);
    if (mHtml) {
      fs.mkdirSync(path.join(_BUILD_DIR, "zasedaniya-tsb"), { recursive: true });
      fs.writeFileSync(path.join(_BUILD_DIR, "zasedaniya-tsb", "index.html"), mHtml, "utf8");
      urls.push({ loc: `${_SITE}/zasedaniya-tsb/`, freq: "weekly", pri: "0.7" });
      observerCount++;
    }
  }

  // Глоссарий — после компаний: ему нужны их ряды для таблиц примеров.
  let glossaryCount = 0;
  for (const spec of METRIC_PAGES.filter((m) => m.formula)) {
    const dir = path.join(_BUILD_DIR, "pokazateli", spec.slug);
    fs.mkdirSync(dir, { recursive: true });
    fs.writeFileSync(path.join(dir, "index.html"), glossaryPage(spec, companies, assets), "utf8");
    urls.push({ loc: `${_SITE}/pokazateli/${spec.slug}/`, freq: "monthly", pri: "0.7" });
    glossaryCount++;
  }
  // Термины рынка — те же /pokazateli/, примеры берутся из снимка облигаций и компаний.
  {
    let bonds = [];
    try {
      bonds = (JSON.parse(fs.readFileSync(
        path.join(__dirname, "data", "bonds-snapshot.json"), "utf8")).rows) || [];
    } catch { /* без снимка облигаций примеры просто не выводятся */ }
    const ctx = { bonds, companies };
    for (const term of TERM_PAGES) {
      const dir = path.join(_BUILD_DIR, "pokazateli", term.slug);
      fs.mkdirSync(dir, { recursive: true });
      fs.writeFileSync(path.join(dir, "index.html"), termPage(term, ctx, assets), "utf8");
      urls.push({ loc: `${_SITE}/pokazateli/${term.slug}/`, freq: "monthly", pri: "0.7" });
      glossaryCount++;
    }
  }

  // Оглавление справочника: и людям навигация, и роботу узел, связывающий все страницы.
  {
    const items = METRIC_PAGES.filter((m) => m.formula);
    const body = `<p class="tag">Справочник Basis</p>
<h1>Показатели и термины рынка: что они значат</h1>
<p class="sub">Короткие объяснения без учебника: что показывает величина, как считается,
где её легко прочитать неверно — и сразу примеры на реальных бумагах Мосбиржи.</p>
<h2>Показатели отчётности</h2>
<div class="grid">${items.map((m) => `<a class="chip" href="/pokazateli/${m.slug}/">${
      escapeHtml(m.label)}</a>`).join("")}</div>
<h2>Термины рынка</h2>
<div class="grid">${TERM_PAGES.map((t) => `<a class="chip" href="/pokazateli/${t.slug}/">${
      escapeHtml(t.label)}</a>`).join("")}</div>
<p>Каждый показатель разобран и по отдельным компаниям: динамика по годам, сравнение с
медианой сектора и место среди соседей по отрасли. Начать можно с
<a href="/company/">каталога компаний</a> или с <a href="/skrining-aktsiy/">скрининга</a>,
если нужно отобрать бумаги по значению показателя.</p>`;
    fs.mkdirSync(path.join(_BUILD_DIR, "pokazateli"), { recursive: true });
    fs.writeFileSync(path.join(_BUILD_DIR, "pokazateli", "index.html"), pageShell({
      title: "Показатели и термины рынка: EBITDA, ROE, ОФЗ, дюрация — что значат | Basis",
      desc: "Справочник показателей отчётности: что показывает каждый, формула расчёта, "
        + "как читать и где ошибаются. Со значениями по российским компаниям.",
      canonicalPath: "/pokazateli/",
      jsonLd: [{
        "@type": "DefinedTermSet",
        "@id": `${_SITE}/pokazateli/#set`,
        name: "Показатели и термины рынка — справочник Basis",
        url: `${_SITE}/pokazateli/`,
      }],
      breadcrumbs: [{ label: "Basis", href: "/" }, { label: "Показатели" }],
      bodyHtml: body, assets, note: DEFAULT_NOTE,
    }), "utf8");
    urls.push({ loc: `${_SITE}/pokazateli/`, freq: "monthly", pri: "0.8" });
    glossaryCount++;
  }

  // 🔴 Карта сайта пишется ПОСЛЕДНЕЙ, когда все страницы уже добавлены в urls. Раньше
  // writeSitemap() стоял до генерации справочника и лендинга недооценённых — 25 адресов
  // в файл не попадали, хотя сами страницы существовали и открывались. Коварство в том,
  // что итоговый лог считает длину массива urls, а не строки файла: он рапортовал 4687
  // при реальных 4662 в sitemap.xml. Проверять карту по ФАЙЛУ, а не по логу.
  writeSitemap(urls);
  console.log(`SEO-страницы: ${companies.length} хабов + ${tabPagesCount} разделов + ${metricPagesCount} метрик + ${fairValuePagesCount} оценок + ${glossaryCount} справочника + ${observerCount} обозревателя + ${LANDINGS.length} лендингов + каталог; sitemap.xml — ${urls.length} URL; пропущено (нет financials.json): ${skipped.length}`);
  console.log(`Короткие редиректы /TICKER/: ${shortUrlCount}${shortUrlSkipped.length ? `; пропущены (конфликт с зарезервированным путём): ${shortUrlSkipped.join(", ")}` : ""}`);
  if (skipped.length) console.log("пропущены:", skipped.slice(0, 20).join(", "), skipped.length > 20 ? "..." : "");
}

main();

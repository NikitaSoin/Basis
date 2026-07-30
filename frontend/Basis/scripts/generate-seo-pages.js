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

const esc = (v) => escapeHtml(String(v == null ? "" : v));

// Блок разбора отчёта: суть → факты → плюсы → риски → вывод. Ровно то, что уже
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
  parts.push(yearly);
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
    // Тайтл НЕ зависит от свежести разбора: период в заголовке означал бы, что при каждом
    // новом отчёте меняется тайтл уже проиндексированной страницы — поиск такое не любит.
    title: (c) => `Отчётность ${titleName(c)} (${c.ticker}): разбор — выручка, прибыль | Basis`,
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
    content: (c) => mdExcerpt(c.businessMd, 3500),
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
    title: (c) => `${titleName(c)} (${c.ticker}) и макро: влияние ставки ЦБ, инфляции, курса — Basis`,
    desc: (c) => truncate(`Макро и ${c.short} (${c.ticker}): ${mdFirstSentence(c.macroMd, 300) ||
      "как ключевая ставка, инфляция и курс рубля влияют на компанию — разбор Basis."}`, 200),
    content: (c) => mdExcerpt(c.macroMd, 3000),
  },
  {
    slug: "geo", appTab: "geo", label: "Геополитика",
    has: (c) => Boolean(c.geoMd),
    title: (c) => `${titleName(c)} (${c.ticker}): риски — геополитика и санкции | Basis`,
    desc: (c) => truncate(`Геополитика и ${c.short} (${c.ticker}): ${mdFirstSentence(c.geoMd, 300) ||
      "санкционная экспозиция, сценарии, влияние на оценку — разбор Basis."}`, 200),
    content: (c) => mdExcerpt(c.geoMd, 3000),
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
  const cleaned = String(c.short || "")
    .replace(/\s*\([A-Za-z][^)]*\)\s*$/, "")
    .replace(/[«»"]/g, "")
    .trim();
  return truncate(cleaned || c.short, 40);
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
    `${c.short} (${c.ticker}), сектор «${c.sectorFull || c.sector}»: бизнес-модель, финансы, дивиденды, справедливая цена, макро- и геополитические риски.${nums} Независимый разбор Basis.`,
    200
  );
}

function hubPage(c, tabsWritten, sectorPeers, assets) {
  // Тайтл под поисковый интент (владелец, 2026-07-27): «анализ акций X»,
  // «справедливая цена X» — реальные запросы; цифра из financials.json датирована.
  // Без числа: интент-слова («анализ акций», «справедливая цена», «дивиденды») в тайтле
  // сохранены — они и ловят запрос, а конкретная цифра теперь живёт только на странице,
  // где считается по актуальной методике.
  const title = `${titleName(c)} (${c.ticker}): анализ акций, справедливая цена, дивиденды — Basis`;
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
<a class="cta" href="${escapeHtml(l.appHref)}">${escapeHtml(l.appLabel)} →</a>
${relatedHtml}`;
  const ld = [{
    "@type": "WebPage",
    name: l.title,
    description: l.description,
    url: `${_SITE}/${l.slug}/`,
    inLanguage: "ru",
    isPartOf: { "@type": "WebSite", name: "Basis", url: _SITE },
  }];
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

  const gitDates = loadGitFileDates();
  if (!gitDates) console.log("⚠️  git-история недоступна — lastmod из mtime файлов");

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

    // соседи по сектору (до 8, кроме себя)
    const peers = companies
      .filter((p) => p.sector === c.sector && p.ticker !== c.ticker)
      .slice(0, 8);

    const hubDir = path.join(_BUILD_DIR, "company", c.ticker);
    fs.mkdirSync(hubDir, { recursive: true });
    fs.writeFileSync(path.join(hubDir, "index.html"), hubPage(c, tabsWritten, peers, assets), "utf8");
    urls.push({ loc: `${_SITE}/company/${c.ticker}/`, freq: "weekly", pri: "0.8", lastmod });

    for (const [spec, content] of rendered) {
      const dir = path.join(hubDir, spec.slug);
      fs.mkdirSync(dir, { recursive: true });
      fs.writeFileSync(path.join(dir, "index.html"), tabPage(c, spec, content, tabsWritten, assets), "utf8");
      urls.push({ loc: `${_SITE}/company/${c.ticker}/${spec.slug}/`, freq: "monthly", pri: "0.6", lastmod });
      tabPagesCount++;
    }
  }

  fs.writeFileSync(path.join(_BUILD_DIR, "company", "index.html"), indexPage(companies), "utf8");

  // Интент-лендинги разделов (v3, SEO-задача №1): /analiz-portfelya/ и др.
  // lastmod — mtime файла текстов: правка текста = реальное обновление страницы.
  const landingLastmod = fileLastmod(path.join(__dirname, "seo-landings-content.js"));
  for (const l of LANDINGS) {
    const dir = path.join(_BUILD_DIR, l.slug);
    fs.mkdirSync(dir, { recursive: true });
    fs.writeFileSync(path.join(dir, "index.html"), landingPage(l, assets), "utf8");
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

  writeSitemap(urls);
  console.log(`SEO-страницы: ${companies.length} хабов + ${tabPagesCount} страниц разделов + ${LANDINGS.length} интент-лендингов + каталог; sitemap.xml — ${urls.length} URL; пропущено (нет financials.json): ${skipped.length}`);
  console.log(`Короткие редиректы /TICKER/: ${shortUrlCount}${shortUrlSkipped.length ? `; пропущены (конфликт с зарезервированным путём): ${shortUrlSkipped.join(", ")}` : ""}`);
  if (skipped.length) console.log("пропущены:", skipped.slice(0, 20).join(", "), skipped.length > 20 ? "..." : "");
}

main();

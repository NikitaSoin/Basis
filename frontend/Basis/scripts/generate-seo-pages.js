#!/usr/bin/env node
/**
 * Генератор статических SEO-страниц компаний (build/company/<TICKER>/index.html).
 *
 * Проблема: приложение — client-side SPA без роутинга (все разделы живут на "/" как
 * состояние вкладок), боты видят пустой HTML-шелл. Полноценный SSR недоступен — фронт
 * и бэк на РАЗНЫХ доменах (inbasis.ru vs API). Поэтому вместо server-side rendering —
 * build-time генерация лёгких, но РЕАЛЬНЫХ статических страниц по данным из
 * companies/<TICKER>/financials.json: title/description под конкретный тикер +
 * читаемый факт-лист + переход в живое приложение.
 *
 * ПОЧЕМУ Node, а не Python (была первая версия — scripts/generate_seo_pages.py):
 * билд-окружение Timeweb Cloud Apps реально выполняет `npm run build` на сервере
 * (не только отдаёт закоммиченный build/, как считалось раньше) — там гарантированно
 * есть Node (иначе craco build не запустился бы), но НЕ гарантирован python3
 * (подтверждено на бою: "sh: 1: python3: not found", вся сборка падала). Node —
 * единственная безопасная зависимость в этой среде, без built-in модулей ничего лишнего.
 *
 * Запускается ПОСЛЕ `craco build` (см. package.json), пишет в build/company/.
 */
"use strict";
const fs = require("fs");
const path = require("path");

const _ROOT = path.resolve(__dirname, "..", "..", "..");
const _COMPANIES_DIR = path.join(_ROOT, "backend", "companies");
const _RATES_CSV = path.join(_ROOT, "rates.csv");
const _BUILD_DIR = path.join(__dirname, "..", "build");
const _SITE = "https://inbasis.ru";

function strip(s) {
  return (s || "").replace(/\s+/g, " ").trim();
}

function escapeHtml(s) {
  return String(s == null ? "" : s)
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&#39;");
}

// rates.csv — windows-1251 (cp1251), не UTF-8; читаем как latin1 побайтово и
// перекодируем вручную таблицей cp1251->unicode (без внешних зависимостей).
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

// Простой построчный CSV-парсер (RFC4180-подмножество): поля в кавычках могут
// содержать ";" и экранированные """" -> """. Наивный split(";") ломает поля вроде
// `"Публичное акционерное общество ""Сбербанк России"""` — даёт задвоенные кавычки.
function parseCsvLine(line, delim) {
  const out = [];
  let field = "";
  let inQuotes = false;
  for (let i = 0; i < line.length; i++) {
    const c = line[i];
    if (inQuotes) {
      if (c === '"') {
        if (line[i + 1] === '"') { field += '"'; i++; } else { inQuotes = false; }
      } else {
        field += c;
      }
    } else if (c === '"' && field === "") {
      inQuotes = true;
    } else if (c === delim) {
      out.push(field); field = "";
    } else {
      field += c;
    }
  }
  out.push(field);
  return out;
}

function loadNames() {
  const names = {};
  if (!fs.existsSync(_RATES_CSV)) return names;
  const text = decodeCp1251(fs.readFileSync(_RATES_CSV));
  const lines = text.split(/\r?\n/);
  let header = null;
  for (const line of lines) {
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

function companyFacts(ticker) {
  const p = path.join(_COMPANIES_DIR, ticker, "financials.json");
  if (!fs.existsSync(p)) return null;
  try {
    return JSON.parse(fs.readFileSync(p, "utf8"));
  } catch {
    return null;
  }
}

function renderPage(ticker, name, facts) {
  const keyFacts = facts.key_facts || [];
  const rows = keyFacts
    .filter((kf) => kf.label && kf.value)
    .map((kf) => `<tr><th>${escapeHtml(strip(kf.label))}</th><td>${escapeHtml(strip(kf.value))}</td></tr>`)
    .join("");
  const nameEsc = escapeHtml(name);
  const title = `${nameEsc} (${ticker}): анализ, справедливая цена, финансовые показатели | Basis`;
  const desc = escapeHtml(
    `${name} (${ticker}) на Мосбирже — независимый разбор Basis: ключевые факты, ` +
    `финансовые показатели, оценка. Не брокер, без сигналов «купить/продать».`
  );
  return `<!doctype html>
<html lang="ru">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>${title}</title>
<meta name="description" content="${desc}">
<link rel="canonical" href="${_SITE}/company/${ticker}/">
<meta property="og:title" content="${title}">
<meta property="og:description" content="${desc}">
<meta property="og:url" content="${_SITE}/company/${ticker}/">
<meta property="og:type" content="website">
<meta name="robots" content="index, follow">
<style>
body{font-family:-apple-system,Segoe UI,Roboto,sans-serif;max-width:720px;margin:40px auto;
     padding:0 20px;color:#1a1a1a;line-height:1.5}
h1{font-size:22px} table{width:100%;border-collapse:collapse;margin:20px 0}
th,td{text-align:left;padding:8px 4px;border-bottom:1px solid #eee;font-size:14px}
th{color:#666;font-weight:500;width:40%}
a.cta{display:inline-block;margin-top:16px;padding:10px 20px;background:#4F5BD5;color:#fff;
      text-decoration:none;border-radius:6px;font-size:14px}
p.note{font-size:12px;color:#999;margin-top:24px}
</style>
</head>
<body>
<h1>${nameEsc} (${ticker})</h1>
<p>Независимый разбор Basis по бумаге ${ticker} на Московской бирже. Ниже — ключевые факты
по компании; полная аналитика (финансы, оценка, управление, макро, геополитика) — в приложении.</p>
${rows ? `<table>${rows}</table>` : ""}
<a class="cta" href="${_SITE}/?company=${ticker}">Открыть полный разбор в Basis →</a>
<p class="note">Basis — не брокер, не даёт торговых сигналов. Это независимый аналитический
слой: факты, оценки и логика для собственного решения инвестора.</p>
</body>
</html>`;
}

function writeSitemap(tickers) {
  const urls = [`  <url><loc>${_SITE}/</loc><changefreq>daily</changefreq><priority>1.0</priority></url>`];
  for (const t of tickers) {
    urls.push(`  <url><loc>${_SITE}/company/${t}/</loc><changefreq>weekly</changefreq><priority>0.8</priority></url>`);
  }
  const xml = `<?xml version="1.0" encoding="UTF-8"?>\n<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n${urls.join("\n")}\n</urlset>\n`;
  fs.writeFileSync(path.join(_BUILD_DIR, "sitemap.xml"), xml, "utf8");
}

function main() {
  if (!fs.existsSync(_COMPANIES_DIR) || !fs.statSync(_COMPANIES_DIR).isDirectory()) {
    console.log("companies dir не найден — пропуск");
    return;
  }
  const names = loadNames();
  const written = [];
  const skipped = [];
  const tickers = fs.readdirSync(_COMPANIES_DIR).sort();
  for (const ticker of tickers) {
    if (ticker.startsWith("_") || ticker === "ocr2025") continue;
    const full = path.join(_COMPANIES_DIR, ticker);
    if (!fs.statSync(full).isDirectory()) continue;
    const facts = companyFacts(ticker);
    if (!facts) { skipped.push(ticker); continue; }
    const name = names[ticker] || ticker;
    const html = renderPage(ticker, name, facts);
    const outDir = path.join(_BUILD_DIR, "company", ticker);
    fs.mkdirSync(outDir, { recursive: true });
    fs.writeFileSync(path.join(outDir, "index.html"), html, "utf8");
    written.push(ticker);
  }
  writeSitemap(written);
  console.log(`SEO-страницы компаний: записано ${written.length}, пропущено (нет financials.json) ${skipped.length}; sitemap.xml обновлён (${written.length + 1} URL)`);
  if (skipped.length) console.log("пропущены:", skipped.slice(0, 20).join(", "), skipped.length > 20 ? "..." : "");
}

main();

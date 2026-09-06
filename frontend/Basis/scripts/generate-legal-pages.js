/**
 * Юридические страницы платформы: оферта, политика обработки данных, «Об аналитике».
 *
 * ЗАЧЕМ ГЕНЕРАТОР, А НЕ ЭКРАН ПРИЛОЖЕНИЯ. Эти документы обязаны открываться у любого
 * человека и любого проверяющего — без React, без входа, по прямой ссылке, и остаться
 * читаемыми, даже если приложение сломается. Плюс их положено индексировать: политика
 * должна находиться поиском, а не только из личного кабинета.
 *
 * ИСТОЧНИК ПРАВДЫ — МАРКДАУН В docs/legal. Тексты живут там, здесь только вёрстка.
 * Так правка документа не требует лазить в HTML, а сам документ можно читать и в
 * репозитории, и в браузере — это один и тот же текст.
 *
 * 🔴 ПОКА РЕКВИЗИТЫ ОПЕРАТОРА НЕ ЗАПОЛНЕНЫ (scripts/legal-config.js) на оферте и
 * политике печатается честная пометка «проект»: документ без указания, кто его
 * выпустил, договором не становится и требованию 152-ФЗ не отвечает. Прятать этот
 * факт от читателя нельзя — можно только заполнить реквизиты.
 */
"use strict";

const fs = require("fs");
const path = require("path");
const { metrikaSnippet } = require("./metrika");
const { analyticsSnippet } = require("./basis-analytics-tag");
const L = require("./legal-config");

const ROOT = path.resolve(__dirname, "..", "..", "..");        // корень репозитория
const SRC_DIR = path.join(ROOT, "docs", "legal");
const OUT = path.resolve(__dirname, "..", "build");

const PAGES = [
  { file: "01-публичная-оферта.md", slug: "offer",
    title: "Публичная оферта и пользовательское соглашение — Basis",
    desc: "Условия оказания информационно-аналитических услуг платформы Basis: тарифы, оплата, возврат, ответственность.",
    draft: true },
  { file: "02-политика-обработки-пдн.md", slug: "privacy",
    title: "Политика обработки персональных данных — Basis",
    desc: "Какие данные собирает Basis, зачем, на каком основании, кому передаёт и сколько хранит.",
    draft: true },
  { file: "04-об-аналитике-basis.md", slug: "about-analytics",
    title: "Об аналитике Basis — характер информации на платформе",
    desc: "Почему материалы Basis не являются индивидуальной инвестиционной рекомендацией, как читать уровни достоверности и что умеет ИИ.",
    draft: false },
];

const esc = (s) => String(s).replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;");

/* ── Маркдаун → HTML. Поддерживаем ровно то, что используется в документах:
 * заголовки, абзацы, списки, таблицы, цитаты, жирный, ссылки, код и разделители.
 * Полноценный парсер здесь был бы лишней зависимостью в сборке, которая и так
 * обязана работать без внешних инструментов. ─────────────────────────────────── */
function inline(t) {
  return esc(t)
    .replace(/`([^`]+)`/g, "<code>$1</code>")
    .replace(/\*\*([^*]+)\*\*/g, "<strong>$1</strong>")
    .replace(/\[([^\]]+)\]\((https?:[^)]+|\/[^)]*)\)/g, '<a href="$2">$1</a>');
}

function mdToHtml(md) {
  const lines = md.split("\n");
  const out = [];
  let i = 0, inList = null, para = [];

  const flushPara = () => {
    if (para.length) { out.push(`<p>${inline(para.join(" "))}</p>`); para = []; }
  };
  const closeList = () => { if (inList) { out.push(`</${inList}>`); inList = null; } };

  while (i < lines.length) {
    const line = lines[i];
    const t = line.trim();

    if (!t) { flushPara(); closeList(); i++; continue; }

    // таблица
    if (t.startsWith("|") && (lines[i + 1] || "").trim().match(/^\|[\s:|-]+\|$/)) {
      flushPara(); closeList();
      const head = t.split("|").slice(1, -1).map((c) => c.trim());
      i += 2;
      const rows = [];
      while (i < lines.length && lines[i].trim().startsWith("|")) {
        rows.push(lines[i].trim().split("|").slice(1, -1).map((c) => c.trim()));
        i++;
      }
      out.push('<div class="tw"><table><thead><tr>'
        + head.map((c) => `<th>${inline(c)}</th>`).join("")
        + "</tr></thead><tbody>"
        + rows.map((r) => "<tr>" + r.map((c) => `<td>${inline(c)}</td>`).join("") + "</tr>").join("")
        + "</tbody></table></div>");
      continue;
    }

    // заголовки
    const h = t.match(/^(#{1,4})\s+(.*)$/);
    if (h) {
      flushPara(); closeList();
      const lvl = Math.min(h[1].length, 4);        // # документа → h1 страницы
      out.push(`<h${lvl}>${inline(h[2])}</h${lvl}>`);
      i++; continue;
    }

    if (/^---+$/.test(t)) { flushPara(); closeList(); out.push("<hr>"); i++; continue; }

    if (t.startsWith(">")) {
      flushPara(); closeList();
      const buf = [];
      while (i < lines.length && lines[i].trim().startsWith(">")) {
        buf.push(lines[i].trim().replace(/^>\s?/, "")); i++;
      }
      out.push(`<blockquote>${inline(buf.join(" "))}</blockquote>`);
      continue;
    }

    const li = t.match(/^([-*])\s+(.*)$/);
    const oli = t.match(/^(\d+)\.\s+(.*)$/);
    if (li || oli) {
      flushPara();
      const want = li ? "ul" : "ol";
      if (inList !== want) { closeList(); out.push(`<${want}>`); inList = want; }
      out.push(`<li>${inline((li || oli)[2])}</li>`);
      i++; continue;
    }

    // отступ в четыре пробела — код (в документах это примеры настроек)
    if (/^ {4}\S/.test(line)) {
      flushPara(); closeList();
      const buf = [];
      while (i < lines.length && (/^ {4}/.test(lines[i]) || !lines[i].trim())) {
        buf.push(lines[i].replace(/^ {4}/, "")); i++;
      }
      out.push(`<pre>${esc(buf.join("\n").trim())}</pre>`);
      continue;
    }

    // 🔴 «1.1.», «12.3.» — начало нового пункта документа, а не продолжение абзаца.
    // Без этой проверки весь раздел склеивался в одну простыню: строки идут подряд,
    // пустых строк между пунктами в исходнике нет.
    if (/^\d+(\.\d+)*\.\s/.test(t) && para.length) flushPara();
    para.push(t);
    i++;
  }
  flushPara(); closeList();
  return out.join("\n");
}

const CSS = `:root{--paper:#F7F5F0;--ink:#1F1B16;--muted:#5A5248;--faint:#8A8072;--copper:#C97A4A;--line:#E4DFD5;--warn:#F6E9DD}
*{box-sizing:border-box}body{font-family:Inter,-apple-system,'Segoe UI',Roboto,sans-serif;background:var(--paper);color:var(--ink);margin:0;line-height:1.6;font-size:15px}
.doc{max-width:820px;margin:0 auto;padding:26px 20px 70px}
.top{display:flex;align-items:center;justify-content:space-between;gap:12px;border-bottom:1px solid var(--line);padding-bottom:14px;margin-bottom:26px}
.brand{font:700 20px/1 Fraunces,Georgia,serif;color:var(--ink);text-decoration:none}
.brand span{color:var(--copper)}
.back{font-size:13.5px;color:var(--muted);text-decoration:none}.back:hover{color:var(--copper)}
h1{font:600 30px/1.25 Fraunces,Georgia,serif;margin:0 0 6px}
h2{font:600 22px/1.3 Fraunces,Georgia,serif;margin:34px 0 10px}
h3{font:600 17px/1.35 Fraunces,Georgia,serif;margin:24px 0 8px}
h4{font:600 15px/1.4 Inter,sans-serif;margin:18px 0 6px}
p{margin:10px 0}ul,ol{margin:10px 0 10px 22px;padding:0}li{margin:5px 0}
a{color:var(--copper)}code{font:13px/1.4 'IBM Plex Mono',ui-monospace,monospace;background:#EFEBE3;padding:1px 5px;border-radius:5px}
pre{background:#EFEBE3;padding:12px 14px;border-radius:9px;overflow-x:auto;font:12.5px/1.5 'IBM Plex Mono',ui-monospace,monospace}
blockquote{margin:16px 0;padding:12px 16px;background:#EFEBE3;border-left:3px solid var(--copper);border-radius:0 9px 9px 0;color:var(--muted)}
blockquote p{margin:0}
.tw{overflow-x:auto;margin:14px 0}
table{border-collapse:collapse;width:100%;font-size:13.5px;min-width:520px}
th{text-align:left;font-weight:600;color:var(--muted);border-bottom:2px solid var(--line);padding:8px 10px;vertical-align:top}
td{border-bottom:1px solid var(--line);padding:8px 10px;vertical-align:top}
hr{border:0;border-top:1px solid var(--line);margin:28px 0}
.draft{background:var(--warn);border:1px solid #E0C4A8;border-radius:10px;padding:12px 15px;margin:0 0 22px;font-size:14px;color:#6B4A2C}
.foot{border-top:1px solid var(--line);margin-top:40px;padding-top:16px;font-size:12.5px;color:var(--faint)}
.foot a{color:var(--faint)}
@media (prefers-color-scheme:dark){:root{--paper:#14110E;--ink:#F2EDE4;--muted:#B8AE9F;--faint:#8A8072;--line:#2C2620;--warn:#3A2A1C}
code,pre,blockquote{background:#1E1A15}.draft{border-color:#5A3E28;color:#E8C9A8}}`;

function page(doc, html, ready) {
  const draftNote = (!ready && doc.draft)
    ? `<div class="draft"><strong>Проект документа.</strong> Реквизиты Оператора ещё не опубликованы,
       поэтому документ приведён для ознакомления и не порождает обязательств. Он вступит в силу
       с даты публикации полной редакции с реквизитами.</div>`
    : "";
  return `<!doctype html>
<html lang="ru"><head>
<meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>${esc(doc.title)}</title>
<meta name="description" content="${esc(doc.desc)}">
<link rel="canonical" href="${L.SITE}/${doc.slug}/">
<meta property="og:type" content="article"><meta property="og:title" content="${esc(doc.title)}">
<meta property="og:description" content="${esc(doc.desc)}"><meta property="og:url" content="${L.SITE}/${doc.slug}/">
${(!ready && doc.draft) ? '<meta name="robots" content="noindex, follow">' : ""}
<style>${CSS}</style>${metrikaSnippet()}${analyticsSnippet()}
</head><body>
<div class="doc">
  <div class="top">
    <a class="brand" href="/"><span>B</span>asis</a>
    <a class="back" href="/">← на платформу</a>
  </div>
  ${draftNote}
  ${html}
  <div class="foot">
    <a href="/offer/">Публичная оферта</a> · <a href="/privacy/">Обработка данных</a> ·
    <a href="/about-analytics/">Об аналитике</a> · <a href="/">Платформа Basis</a><br>
    Basis — независимый аналитический сервис. Не брокер, сделок не исполняет,
    индивидуальных инвестиционных рекомендаций не даёт.
  </div>
</div>
</body></html>`;
}

function main() {
  const ready = L.isReady();
  if (!ready) {
    console.log("Юридические страницы: ⚠️ реквизиты Оператора не заполнены "
      + "(scripts/legal-config.js) — оферта и политика публикуются с пометкой «проект» "
      + "и закрыты от индексации.");
  }
  let made = 0;
  for (const doc of PAGES) {
    const src = path.join(SRC_DIR, doc.file);
    if (!fs.existsSync(src)) { console.log(`Юридические страницы: нет файла ${doc.file} — пропуск`); continue; }
    const md = L.fill(fs.readFileSync(src, "utf8"));
    const dir = path.join(OUT, doc.slug);
    fs.mkdirSync(dir, { recursive: true });
    fs.writeFileSync(path.join(dir, "index.html"), page(doc, mdToHtml(md), ready));
    made++;
  }
  console.log(`Юридические страницы: ${made} (${PAGES.map((p) => "/" + p.slug + "/").join(", ")})`
    + (ready ? " — реквизиты заполнены, документы в силе" : ""));
}

main();

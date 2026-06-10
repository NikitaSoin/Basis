// =============================================================
// BondRiskAnalysis — структурный рендер разбора «Доходность и риск»
// по методике v1.2 (канон-схема с ## ВЕРДИКТ {light:X} и {score:N}).
//
// Обратная совместимость: если md НЕ содержит маркер `## ВЕРДИКТ {light:`,
// рендерится legacy-режим через AnalystProse (старые разборы не ломаются).
//
// Все стили — исключительно tw- классы на дизайн-токены из tokens.css.
// Нет захардкоженных hex. Обе темы (светлая / тёмная).
// =============================================================

import React from "react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import { Disclosure } from "./textblocks";

/* ---------- helpers ---------- */
const cx = (...parts) => parts.filter(Boolean).join(" ");

// Удаляет inline-токены вида {факт}, {оценка}, {суждение}, {warn}, {light:X}, {score:N}
// из текста, возвращая чистую строку.
function stripTokens(text) {
  return text.replace(/\{[^}]+\}/g, "").replace(/\s{2,}/g, " ").trim();
}

// Извлекает значение токена из заголовка: {light:orange} → "orange"
function extractToken(heading, name) {
  const m = heading.match(new RegExp(`\\{${name}:([^}]+)\\}`));
  return m ? m[1].trim() : null;
}

// Разбивает markdown по строкам `^## ` на секции { title, rawTitle, body }
function parseSections(md) {
  const lines = md.split("\n");
  const sections = [];
  let current = null;
  for (const line of lines) {
    if (line.startsWith("## ")) {
      if (current) sections.push(current);
      current = { rawTitle: line.slice(3).trim(), body: [] };
    } else if (current) {
      current.body.push(line);
    }
  }
  if (current) sections.push(current);
  return sections;
}

// Парсит строку буллета, вытаскивая inline-метку {факт|оценка|суждение|warn}
function parseBullet(text) {
  const labelMatch = text.match(/\{(факт|оценка|суждение|warn)\}/);
  const label = labelMatch ? labelMatch[1] : null;
  const clean = stripTokens(text);
  return { label, clean };
}

// Нормализует тело секции в массив буллетов (строки, начинающиеся с "- ")
// Остальные строки — абзацы
function parseBody(lines) {
  return lines.join("\n").trim();
}

/* ---------- маппинг light-токена на дизайн-токены ---------- */
const LIGHT_MAP = {
  red:    { bg: "tw-bg-danger-soft",  border: "tw-border-danger",  text: "tw-text-danger",  label: "Высокий риск",    icon: "🔴" },
  orange: { bg: "tw-bg-warning-soft", border: "tw-border-warning", text: "tw-text-warning", label: "Повышенный риск", icon: "🟠" },
  amber:  { bg: "tw-bg-warning-soft", border: "tw-border-warning", text: "tw-text-warning", label: "Умеренный риск",  icon: "🟡" },
  green:  { bg: "tw-bg-success-soft", border: "tw-border-success", text: "tw-text-success", label: "Приемлемый риск", icon: "🟢" },
  gray:   { bg: "tw-bg-bg-base",      border: "tw-border-border-strong", text: "tw-text-text-secondary", label: "Нет вердикта", icon: "⚪" },
};

/* ---------- маппинг score 1–5 на цвета ----------
   score 1–2 = хорошо (зелёный), 3 = нейтрально (жёлтый), 4–5 = плохо (красный)
   Инвертировано: в методике ВЫСОКИЙ score = ПЛОХО (5 = худшая платёжеспособность) */
function scoreStyle(score) {
  const n = parseInt(score, 10);
  if (n <= 2) return { bg: "tw-bg-success-soft", text: "tw-text-success", border: "tw-border-success" };
  if (n === 3) return { bg: "tw-bg-warning-soft", text: "tw-text-warning", border: "tw-border-warning" };
  return { bg: "tw-bg-danger-soft", text: "tw-text-danger", border: "tw-border-danger" };
}

/* ---------- маппинг inline-метки на бейдж-стиль ---------- */
const LABEL_STYLE = {
  факт:     { bg: "tw-bg-bg-base",       text: "tw-text-text-tertiary",  border: "tw-border-border-subtle" },
  оценка:   { bg: "tw-bg-info-soft",     text: "tw-text-info",           border: "tw-border-info" },
  суждение: { bg: "tw-bg-accent-soft",   text: "tw-text-accent",         border: "tw-border-accent" },
};

function LabelBadge({ label }) {
  if (!label || label === "warn") return null;
  const s = LABEL_STYLE[label] || LABEL_STYLE["факт"];
  return (
    <span
      className={cx(
        "tw-inline-block tw-text-[10px] tw-font-semibold tw-px-1.5 tw-py-px tw-rounded-xs",
        "tw-border tw-uppercase tw-tracking-wide tw-shrink-0",
        s.bg, s.text, s.border
      )}
      style={{ letterSpacing: "0.05em" }}
    >
      {label}
    </span>
  );
}

/* ---------- КОМПОНЕНТ ВЕРДИКТ ---------- */
function VerdictBanner({ light, children }) {
  const s = LIGHT_MAP[light] || LIGHT_MAP.gray;
  return (
    <div
      className={cx(
        "tw-flex tw-gap-3 tw-items-start tw-rounded-md tw-border-l-4 tw-p-4",
        s.bg, s.border
      )}
      role="region"
      aria-label="Вердикт"
    >
      <span className="tw-text-[22px] tw-leading-[1.2] tw-shrink-0" aria-hidden="true">{s.icon}</span>
      <div className="tw-min-w-0">
        <div className={cx("tw-text-[11px] tw-font-semibold tw-uppercase tw-mb-1", s.text)} style={{ letterSpacing: "0.07em" }}>
          Вердикт · {s.label}
        </div>
        <div className="tw-text-[15px] tw-leading-[1.55] tw-font-medium tw-text-text-primary">
          {children}
        </div>
      </div>
    </div>
  );
}

/* ---------- КОМПОНЕНТ АРИФМЕТИКА ---------- */
function ArithmeticBlock({ lines }) {
  // Парсим 3 строки: каждая — буллет с жирным числом и пояснением
  const items = lines
    .filter(l => l.trim().startsWith("-"))
    .map(l => l.trim().slice(1).trim());

  return (
    <div className="tw-rounded-md tw-border tw-border-border-strong tw-bg-bg-elevated tw-overflow-hidden" style={{ boxShadow: "var(--shadow-sm)" }}>
      <div className="tw-px-3 tw-py-2 tw-border-b tw-border-border-subtle tw-bg-bg-base">
        <span className="tw-text-[11px] tw-font-semibold tw-uppercase tw-text-text-tertiary" style={{ letterSpacing: "0.07em" }}>Арифметика</span>
      </div>
      <div className="tw-divide-y tw-divide-border-subtle">
        {items.map((item, i) => {
          // Определяем, строка с премией? Ищем «Премия» в тексте
          const isPremium = /Премия/i.test(item);
          // Определяем знак из текста для окраски
          const isPositive = isPremium && /\+[0-9]/.test(item);
          const isNegative = isPremium && /−|-[0-9]/.test(item) && !isPositive;
          return (
            <ArithmeticRow key={i} isPremium={isPremium} isPositive={isPositive} isNegative={isNegative}>
              {item}
            </ArithmeticRow>
          );
        })}
      </div>
    </div>
  );
}

// Рендерит одну строку арифметики с жирными числами через ReactMarkdown
function ArithmeticRow({ children, isPremium, isPositive, isNegative }) {
  const premiumClass = isPositive ? "tw-text-success" : isNegative ? "tw-text-danger" : "";
  return (
    <div className={cx("tw-px-3 tw-py-2.5 tw-text-[13px] tw-text-text-secondary tw-leading-[1.5]", isPremium && premiumClass)}>
      <ReactMarkdown
        remarkPlugins={[remarkGfm]}
        components={{
          p: ({ children }) => <span>{children}</span>,
          strong: ({ children }) => (
            <strong className={cx("tw-font-semibold tw-font-mono", isPremium ? premiumClass || "tw-text-text-primary" : "tw-text-text-primary")}>
              {children}
            </strong>
          ),
        }}
      >
        {stripTokens(children)}
      </ReactMarkdown>
    </div>
  );
}

/* ---------- КОМПОНЕНТ ГЛАВНЫЕ АРГУМЕНТЫ ---------- */
function ArgumentsBlock({ bodyText }) {
  const lines = bodyText.split("\n").filter(l => l.trim().startsWith("-"));
  return (
    <div className="tw-rounded-md tw-border tw-border-border-strong tw-bg-bg-elevated tw-overflow-hidden" style={{ boxShadow: "var(--shadow-sm)" }}>
      <div className="tw-px-3 tw-py-2 tw-border-b tw-border-border-subtle tw-bg-bg-base">
        <span className="tw-text-[11px] tw-font-semibold tw-uppercase tw-text-text-tertiary" style={{ letterSpacing: "0.07em" }}>Главные аргументы</span>
      </div>
      <div className="tw-divide-y tw-divide-border-subtle">
        {lines.map((line, i) => {
          const raw = line.trim().slice(1).trim();
          const { label, clean } = parseBullet(raw);
          return (
            <div key={i} className="tw-px-3 tw-py-2.5 tw-flex tw-gap-2 tw-items-start">
              <span className="tw-text-text-tertiary tw-text-[13px] tw-shrink-0 tw-mt-px">→</span>
              <div className="tw-min-w-0 tw-flex-1">
                <ReactMarkdown
                  remarkPlugins={[remarkGfm]}
                  components={{
                    p: ({ children }) => <span className="tw-text-[13px] tw-text-text-secondary tw-leading-[1.55]">{children}</span>,
                    strong: ({ children }) => <strong className="tw-font-semibold tw-text-text-primary">{children}</strong>,
                  }}
                >
                  {clean}
                </ReactMarkdown>
              </div>
              {label && <LabelBadge label={label} />}
            </div>
          );
        })}
      </div>
    </div>
  );
}

/* ---------- КОМПОНЕНТ ПРОВЕРКА ПОТЕРЯМИ ---------- */
function LossCheckBlock({ bodyText }) {
  const { label, clean } = parseBullet(bodyText.replace(/^-\s*/, ""));
  return (
    <div className="tw-rounded-md tw-border tw-border-border-strong tw-bg-bg-elevated tw-overflow-hidden" style={{ boxShadow: "var(--shadow-sm)" }}>
      <div className="tw-px-3 tw-py-2 tw-border-b tw-border-border-subtle tw-bg-bg-base tw-flex tw-items-center tw-justify-between">
        <span className="tw-text-[11px] tw-font-semibold tw-uppercase tw-text-text-tertiary" style={{ letterSpacing: "0.07em" }}>Проверка потерями</span>
        {label && <LabelBadge label={label} />}
      </div>
      <div className="tw-px-3 tw-py-2.5 tw-text-[13px] tw-text-text-secondary tw-leading-[1.6]">
        <ReactMarkdown
          remarkPlugins={[remarkGfm]}
          components={{
            p: ({ children }) => <span>{children}</span>,
            strong: ({ children }) => <strong className="tw-font-semibold tw-text-text-primary">{children}</strong>,
          }}
        >
          {clean}
        </ReactMarkdown>
      </div>
    </div>
  );
}

/* ---------- КОМПОНЕНТ ТРИГГЕРЫ ---------- */
function TriggersBlock({ bodyText }) {
  const lines = bodyText.split("\n").filter(l => l.trim().startsWith("-"));
  return (
    <div className="tw-rounded-md tw-border tw-border-border-strong tw-bg-bg-elevated tw-overflow-hidden" style={{ boxShadow: "var(--shadow-sm)" }}>
      <div className="tw-px-3 tw-py-2 tw-border-b tw-border-border-subtle tw-bg-bg-base">
        <span className="tw-text-[11px] tw-font-semibold tw-uppercase tw-text-text-tertiary" style={{ letterSpacing: "0.07em" }}>Триггеры переоценки</span>
      </div>
      <div className="tw-divide-y tw-divide-border-subtle">
        {lines.map((line, i) => {
          const raw = line.trim().slice(1).trim();
          return (
            <div key={i} className="tw-px-3 tw-py-2 tw-text-[13px] tw-text-text-secondary tw-leading-[1.5]">
              {stripTokens(raw)}
            </div>
          );
        })}
      </div>
    </div>
  );
}

/* ---------- КОМПОНЕНТ БЛОК A–F ---------- */
function SubBlock({ rawTitle, bodyText }) {
  // rawTitle = "БЛОК A — Платёжеспособность {score:5}"
  const score = extractToken(rawTitle, "score");
  const titleClean = stripTokens(rawTitle);
  // Название без "БЛОК X — "
  const shortTitle = titleClean.replace(/^БЛОК\s+[A-F]\s+[—–-]+\s*/i, "").trim();
  const letter = (rawTitle.match(/БЛОК\s+([A-F])/i) || [])[1] || "";

  const ss = score ? scoreStyle(score) : null;
  const lines = bodyText.split("\n").filter(l => l.trim().startsWith("-"));

  return (
    <div className="tw-rounded-md tw-border tw-border-border-subtle tw-bg-bg-elevated tw-overflow-hidden">
      <div className="tw-px-3 tw-py-2 tw-border-b tw-border-border-subtle tw-bg-bg-base tw-flex tw-items-center tw-justify-between">
        <div className="tw-flex tw-items-center tw-gap-2">
          {letter && (
            <span className="tw-text-[11px] tw-font-semibold tw-uppercase tw-text-text-tertiary tw-font-mono" style={{ letterSpacing: "0.05em" }}>
              {letter}
            </span>
          )}
          <span className="tw-text-[13px] tw-font-semibold tw-text-text-primary">{shortTitle}</span>
        </div>
        {score && ss && (
          <span
            className={cx(
              "tw-text-[12px] tw-font-semibold tw-tabular-nums tw-px-2 tw-py-0.5 tw-rounded-xs tw-border",
              ss.bg, ss.text, ss.border
            )}
            aria-label={`Оценка блока: ${score} из 5`}
          >
            {score}/5
          </span>
        )}
      </div>
      <div className="tw-divide-y tw-divide-border-subtle">
        {lines.map((line, i) => {
          const raw = line.trim().slice(1).trim();
          const { label, clean } = parseBullet(raw);
          return (
            <div key={i} className="tw-px-3 tw-py-2 tw-flex tw-gap-2 tw-items-start">
              <span className="tw-text-text-tertiary tw-text-[12px] tw-shrink-0 tw-mt-0.5">·</span>
              <div className="tw-min-w-0 tw-flex-1 tw-text-[13px] tw-text-text-secondary tw-leading-[1.55]">
                <ReactMarkdown
                  remarkPlugins={[remarkGfm]}
                  components={{
                    p: ({ children }) => <span>{children}</span>,
                    strong: ({ children }) => <strong className="tw-font-semibold tw-text-text-primary">{children}</strong>,
                  }}
                >
                  {clean}
                </ReactMarkdown>
              </div>
              {label && label !== "warn" && <LabelBadge label={label} />}
            </div>
          );
        })}
      </div>
    </div>
  );
}

/* ---------- КОМПОНЕНТ СБОРКА (таблица) ---------- */
function AssemblyBlock({ bodyText }) {
  const lines = bodyText.split("\n");
  // Найти markdown-таблицу (строки начинающиеся с "|")
  const tableLines = lines.filter(l => l.trim().startsWith("|"));
  // Остаток после таблицы — риск-скор и стоп-правило
  const afterTableLines = lines.filter(l => !l.trim().startsWith("|") && l.trim().length > 0);

  // Парсим таблицу вручную (пропускаем разделитель "|---|")
  const tableRows = tableLines.filter(l => !l.match(/\|[-: ]+\|/));
  const [headerRow, ...dataRows] = tableRows;

  const parseRow = row =>
    row.split("|").filter((_, i, a) => i > 0 && i < a.length - 1).map(c => c.trim());

  const headers = headerRow ? parseRow(headerRow) : [];
  const rows = dataRows.map(parseRow);

  return (
    <div className="tw-rounded-md tw-border tw-border-border-strong tw-bg-bg-elevated tw-overflow-hidden" style={{ boxShadow: "var(--shadow-sm)" }}>
      <div className="tw-px-3 tw-py-2 tw-border-b tw-border-border-subtle tw-bg-bg-base">
        <span className="tw-text-[11px] tw-font-semibold tw-uppercase tw-text-text-tertiary" style={{ letterSpacing: "0.07em" }}>Сборка · Risk Score</span>
      </div>
      {/* Таблица */}
      {headers.length > 0 && (
        <div className="tw-overflow-x-auto">
          <table className="tw-w-full tw-border-collapse tw-text-[13px]">
            <thead>
              <tr className="tw-bg-bg-base">
                {headers.map((h, i) => (
                  <th
                    key={i}
                    className={cx(
                      "tw-px-3 tw-py-2 tw-text-[11px] tw-font-semibold tw-uppercase tw-text-text-tertiary tw-border-b tw-border-border-subtle",
                      i > 0 ? "tw-text-right" : "tw-text-left"
                    )}
                    style={{ letterSpacing: "0.05em" }}
                  >
                    {h}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {rows.map((row, ri) => (
                <tr key={ri} className="tw-border-b tw-border-border-subtle last:tw-border-0 hover:tw-bg-bg-base tw-transition-colors tw-duration-150">
                  {row.map((cell, ci) => {
                    // Колонка "Оценка" — окрашиваем по значению
                    const isScoreCol = headers[ci]?.toLowerCase() === "оценка";
                    const scoreNum = isScoreCol ? parseInt(cell, 10) : NaN;
                    const ss = !isNaN(scoreNum) ? scoreStyle(scoreNum) : null;
                    return (
                      <td
                        key={ci}
                        className={cx(
                          "tw-px-3 tw-py-2 tw-align-middle tw-leading-[1.4]",
                          ci > 0 ? "tw-text-right tw-tabular-nums tw-font-mono" : "tw-text-left",
                          ss ? cx(ss.text, "tw-font-semibold") : "tw-text-text-secondary"
                        )}
                      >
                        {cell}
                      </td>
                    );
                  })}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
      {/* Риск-скор и стоп-правило */}
      {afterTableLines.length > 0 && (
        <div className="tw-px-3 tw-py-2.5 tw-border-t tw-border-border-strong tw-space-y-1.5">
          {afterTableLines.map((line, i) => {
            const clean = stripTokens(line);
            const isStop = /стоп-правило/i.test(clean);
            return (
              <div
                key={i}
                className={cx(
                  "tw-text-[13px] tw-leading-[1.55]",
                  isStop
                    ? "tw-text-warning tw-font-medium"
                    : "tw-text-text-primary tw-font-semibold"
                )}
              >
                <ReactMarkdown
                  remarkPlugins={[remarkGfm]}
                  components={{
                    p: ({ children }) => <span>{children}</span>,
                    strong: ({ children }) => <strong>{children}</strong>,
                  }}
                >
                  {clean}
                </ReactMarkdown>
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}

/* ---------- КОМПОНЕНТ СНОСКИ ---------- */
function FootnotesBlock({ bodyText }) {
  const lines = bodyText.split("\n").filter(l => l.trim().startsWith("-"));
  const warns = lines.filter(l => l.includes("{warn}"));
  const regular = lines.filter(l => !l.includes("{warn}"));

  return (
    <div className="tw-space-y-2">
      {warns.map((line, i) => {
        const clean = stripTokens(line.trim().slice(1).trim());
        return (
          <div
            key={i}
            className="tw-flex tw-gap-2 tw-items-start tw-rounded-md tw-border-l-2 tw-border-warning tw-bg-warning-soft tw-p-3"
          >
            <span className="tw-text-warning tw-text-[14px] tw-shrink-0" aria-hidden="true">⚠</span>
            <div className="tw-text-[13px] tw-text-text-primary tw-leading-[1.55]">{clean}</div>
          </div>
        );
      })}
      {regular.length > 0 && (
        <div className="tw-space-y-1 tw-pt-1">
          {regular.map((line, i) => {
            const clean = stripTokens(line.trim().slice(1).trim());
            return (
              <div key={i} className="tw-text-[12px] tw-text-text-tertiary tw-leading-[1.5] tw-pl-1">
                · {clean}
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}

/* ---------- КОМПОНЕНТ ИСТОЧНИКИ ---------- */
function SourcesBlock({ bodyText }) {
  // Находим disclaimer (курсивные строки начинаются с _)
  const lines = bodyText.split("\n");
  const sourceLines = lines.filter(l => l.trim().startsWith("-"));
  const disclaimerLines = lines.filter(l => l.trim().startsWith("_"));

  return (
    <div className="tw-space-y-2">
      <ul className="tw-space-y-1 tw-m-0 tw-p-0 tw-list-none">
        {sourceLines.map((line, i) => {
          const raw = line.trim().slice(1).trim();
          // Ссылка формата [текст](url)
          const linkMatch = raw.match(/\[([^\]]+)\]\(([^)]+)\)/);
          return (
            <li key={i} className="tw-text-[12px] tw-leading-[1.5]">
              {linkMatch ? (
                <a
                  href={linkMatch[2]}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="tw-text-accent hover:tw-text-accent-hover tw-underline tw-decoration-from-font focus-visible:tw-outline-none focus-visible:tw-shadow-focus tw-rounded-xs"
                >
                  {linkMatch[1]}
                </a>
              ) : (
                <span className="tw-text-text-tertiary">{raw}</span>
              )}
            </li>
          );
        })}
      </ul>
      {disclaimerLines.map((line, i) => {
        const clean = line.replace(/^_+|_+$/g, "").trim();
        return (
          <p key={i} className="tw-text-[11px] tw-text-text-tertiary tw-italic tw-leading-[1.5] tw-mt-2 tw-border-t tw-border-border-subtle tw-pt-2">
            {clean}
          </p>
        );
      })}
    </div>
  );
}

/* =============================================================
   LEGACY fallback — AnalystProse (ReactMarkdown «как есть»)
   Используется для разборов НЕ в канон-схеме v1.2.
   ============================================================= */
const ANALYST_MD_COMPONENTS = {
  h1: ({ children }) => <h1 className="tw-text-[18px] tw-font-semibold tw-text-text-primary tw-mt-4 tw-mb-2">{children}</h1>,
  h2: ({ children }) => <h2 className="tw-text-[15px] tw-font-semibold tw-text-text-primary tw-mt-3 tw-mb-1.5 tw-border-b tw-border-border-subtle tw-pb-1">{children}</h2>,
  h3: ({ children }) => <h3 className="tw-text-[13px] tw-font-semibold tw-text-text-primary tw-mt-2.5 tw-mb-1">{children}</h3>,
  p: ({ children }) => <p className="tw-text-[13px] tw-text-text-secondary tw-leading-[1.6] tw-mt-2">{children}</p>,
  ul: ({ children }) => <ul className="tw-text-[13px] tw-text-text-secondary tw-leading-[1.6] tw-mt-2 tw-pl-5 tw-list-disc tw-space-y-1">{children}</ul>,
  ol: ({ children }) => <ol className="tw-text-[13px] tw-text-text-secondary tw-leading-[1.6] tw-mt-2 tw-pl-5 tw-list-decimal tw-space-y-1">{children}</ol>,
  li: ({ children }) => <li className="tw-pl-1">{children}</li>,
  strong: ({ children }) => <strong className="tw-text-text-primary tw-font-semibold">{children}</strong>,
  a: ({ href, children }) => <a href={href} className="tw-text-accent tw-underline hover:tw-text-accent-hover" target="_blank" rel="noopener noreferrer">{children}</a>,
  blockquote: ({ children }) => <blockquote className="tw-border-l-2 tw-border-border-strong tw-pl-3 tw-my-2 tw-italic tw-text-text-tertiary">{children}</blockquote>,
  hr: () => <hr className="tw-my-5 tw-border-border-subtle" />,
  table: ({ children }) => <div className="tw-overflow-x-auto tw-my-3 tw-rounded-md tw-border tw-border-border-subtle"><table className="tw-w-full tw-border-collapse tw-text-[13px]">{children}</table></div>,
  th: ({ children }) => <th className="tw-text-left tw-px-2.5 tw-py-2 tw-bg-bg-base tw-border-b tw-border-border-strong tw-text-text-secondary tw-font-semibold">{children}</th>,
  td: ({ children }) => <td className="tw-px-2.5 tw-py-2 tw-border-b tw-border-border-subtle tw-text-text-secondary tw-align-top tw-leading-[1.5]">{children}</td>,
  code: ({ children }) => <code className="tw-bg-bg-base tw-px-1.5 tw-py-0.5 tw-rounded-xs tw-text-[12.5px] tw-font-mono">{children}</code>,
};

function AnalystProseFallback({ md }) {
  return (
    <div className="tw-max-w-[72ch]">
      <ReactMarkdown remarkPlugins={[remarkGfm]} components={ANALYST_MD_COMPONENTS}>
        {md}
      </ReactMarkdown>
    </div>
  );
}

/* =============================================================
   ГЛАВНЫЙ КОМПОНЕНТ
   ============================================================= */
export function BondRiskAnalysis({ md }) {
  if (!md) return null;

  // Детект формата: канонический v1.2 vs legacy
  const isCanonical = md.includes("## ВЕРДИКТ {light:");
  if (!isCanonical) {
    return <AnalystProseFallback md={md} />;
  }

  const sections = parseSections(md);

  // Находим секции по ключевым словам в rawTitle
  const find = (keyword) => sections.find(s => s.rawTitle.toUpperCase().startsWith(keyword.toUpperCase()));
  const findBlocks = () => sections.filter(s => /^БЛОК\s+[A-F]/i.test(s.rawTitle));

  const verdictSec   = find("ВЕРДИКТ");
  const arithmSec    = find("АРИФМЕТИКА");
  const argsSec      = find("ГЛАВНЫЕ АРГУМЕНТЫ");
  const lossSec      = find("ПРОВЕРКА ПОТЕРЯМИ");
  const triggersSec  = find("ТРИГГЕРЫ");
  const assemblySec  = find("СБОРКА");
  const footnotesSec = find("СНОСКИ");
  const sourcesSec   = find("ИСТОЧНИКИ");
  const subBlocks    = findBlocks();

  const light = verdictSec ? extractToken(verdictSec.rawTitle, "light") : "gray";
  const verdictText = verdictSec ? parseBody(verdictSec.body) : "";

  return (
    <div className="tw-flex tw-flex-col tw-gap-3">

      {/* ── ЭТАЖ 1: ВЕРДИКТ ── */}
      {verdictSec && (
        <VerdictBanner light={light}>
          {verdictText}
        </VerdictBanner>
      )}

      {/* ── ЭТАЖ 1: АРИФМЕТИКА ── */}
      {arithmSec && (
        <ArithmeticBlock lines={arithmSec.body} />
      )}

      {/* ── ЭТАЖ 1: ГЛАВНЫЕ АРГУМЕНТЫ ── */}
      {argsSec && (
        <ArgumentsBlock bodyText={parseBody(argsSec.body)} />
      )}

      {/* ── ЭТАЖ 1: ПРОВЕРКА ПОТЕРЯМИ ── */}
      {lossSec && (
        <LossCheckBlock bodyText={parseBody(lossSec.body)} />
      )}

      {/* ── ЭТАЖ 1: ТРИГГЕРЫ ── */}
      {triggersSec && (
        <TriggersBlock bodyText={parseBody(triggersSec.body)} />
      )}

      {/* ── ЭТАЖ 2: БЛОКИ A–F + СБОРКА в Disclosure ── */}
      {(subBlocks.length > 0 || assemblySec) && (
        <Disclosure summary="Полный разбор по блокам A–F" defaultOpen={false}>
          <div className="tw-flex tw-flex-col tw-gap-2.5 tw-pt-1">
            {subBlocks.map((sec, i) => (
              <SubBlock key={i} rawTitle={sec.rawTitle} bodyText={parseBody(sec.body)} />
            ))}
            {assemblySec && (
              <AssemblyBlock bodyText={parseBody(assemblySec.body)} />
            )}
          </div>
        </Disclosure>
      )}

      {/* ── СНОСКИ ── */}
      {footnotesSec && (
        <FootnotesBlock bodyText={parseBody(footnotesSec.body)} />
      )}

      {/* ── ИСТОЧНИКИ ── */}
      {sourcesSec && (
        <Disclosure summary="Источники" defaultOpen={false}>
          <SourcesBlock bodyText={parseBody(sourcesSec.body)} />
        </Disclosure>
      )}

    </div>
  );
}

// default export для удобного импорта
export default BondRiskAnalysis;

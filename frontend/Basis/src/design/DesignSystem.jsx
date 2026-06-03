// =============================================================
// BASIS DESIGN SYSTEM GALLERY — route /_design (Phase 2)
// Renders every base primitive in all variants/states, shown in
// BOTH themes side by side. Dark sub-tree uses the `.dark` class so
// tokens re-resolve locally without a global theme switch. A top
// toggle also flips the whole page (light/dark) for an overall view.
// Pure JS. Styled only via tw- utilities mapping onto tokens.
// =============================================================
import React, { useState } from "react";
import {
  Button,
  IconButton,
  Card,
  Badge,
  Chip,
  Tooltip,
  Input,
  Select,
  Modal,
  Tabs,
  Table,
  Delta,
  KpiTile,
  usePrefersReducedMotion,
} from "./primitives";
import {
  Prose,
  LeadStatement,
  KeyTakeaway,
  Disclosure,
  StatInline,
} from "./textblocks";
import { formatNumber, formatMoney, formatPercent, formatMultiple } from "./format";
import { LiveDepthBody, LiveDepthPreamble } from "./LiveDepthShowcase";
import { LogomarkBody } from "./logomarks";

// classnames join helper (used by VisibilityTag etc.)
const cx = (...parts) => parts.filter(Boolean).join(" ");

/* ---- small layout helpers (gallery chrome only) ---- */

function Section({ title, children }) {
  return (
    <section className="tw-mb-12">
      <h2
        className="tw-text-[22px] tw-font-semibold tw-text-text-primary tw-mb-4 tw-pb-2 tw-border-b tw-border-border-subtle"
        style={{ letterSpacing: "0.01em" }}
      >
        {title}
      </h2>
      {children}
    </section>
  );
}

function Row({ label, children }) {
  return (
    <div className="tw-mb-5">
      {label && (
        <div
          className="tw-text-[12px] tw-uppercase tw-text-text-tertiary tw-mb-2"
          style={{ letterSpacing: "0.06em" }}
        >
          {label}
        </div>
      )}
      <div className="tw-flex tw-flex-wrap tw-items-center tw-gap-3">{children}</div>
    </div>
  );
}

const Bolt = (
  <svg width="16" height="16" viewBox="0 0 16 16" aria-hidden="true">
    <path d="M9 1L2 9h5l-1 6 7-8H8l1-6z" fill="currentColor" />
  </svg>
);

/* =============================================================
   READABILITY — «Читаемость плотного контента» showcase.
   Shows each text primitive, then a through-sample on a realistic
   long analyst comment («комментарий по Сберу»): «было простынёй /
   стало навигируемым». Rule honoured: Lead + honest caveat are
   ALWAYS visible; only second-order detail goes under Disclosure.
   ============================================================= */

// Small tag used to point out WHAT is always visible vs collapsed.
function VisibilityTag({ tone = "open", children }) {
  const map = {
    open: "tw-bg-success-soft tw-text-success",
    collapsed: "tw-bg-bg-base tw-text-text-tertiary tw-border tw-border-border-subtle",
  };
  return (
    <span className={cx("tw-inline-flex tw-items-center tw-gap-1 tw-rounded-pill tw-px-2 tw-py-0.5 tw-text-[11px] tw-font-medium", map[tone])}>
      {children}
    </span>
  );
}

// Realistic, NON-gutted analyst comment for the «before» wall of text.
const SBER_WALL =
  "Сбербанк остаётся ключевой историей в индексе и фундаментально выглядит недорого: при текущей цене акция торгуется примерно по 0,9 капитала и около 4× прибыли, что заметно ниже исторических средних. В то же время котировки последние месяцы под давлением из-за жёсткой денежно-кредитной политики ЦБ: высокая ставка одновременно поддерживает процентную маржу банка и тормозит кредитование, особенно розничное и ипотечное, поэтому итоговый эффект на прибыль неоднозначен. Качество активов пока остаётся приемлемым, стоимость риска (cost of risk) держится около 1,3 %, но при затяжном периоде высоких ставок возможен рост просрочки в необеспеченной рознице, что съест часть маржи. Менеджмент подтверждает цель по дивидендам в 50 % чистой прибыли по МСФО, что при текущей цене даёт двузначную дивидендную доходность, однако фактическая выплата зависит от достаточности капитала и позиции регулятора. Дополнительный фактор неопределённости — траектория ставки: рынок закладывает снижение во втором полугодии, но если инфляция окажется устойчивее ожиданий, смягчение сдвинется, и переоценка вверх затянется. Отдельно стоит учитывать регуляторные и геополитические риски, которые исторически давили на мультипликатор сектора.";

function ReadabilityBody({ reduced }) {
  return (
    <div className="tw-flex tw-flex-col tw-gap-10">
      {/* --- Each primitive --- */}
      <div className="tw-grid tw-grid-cols-1 lg:tw-grid-cols-2 tw-gap-6">
        {/* LeadStatement */}
        <div className="tw-bg-bg-elevated tw-border tw-border-border-strong tw-rounded-md tw-shadow-sm dark:tw-shadow-none tw-p-4">
          <div className="tw-flex tw-items-center tw-gap-2 tw-mb-3">
            <span className="tw-text-[13px] tw-font-medium tw-text-text-primary">LeadStatement · вывод сверху (BLUF)</span>
            <VisibilityTag tone="open">всегда на виду</VisibilityTag>
          </div>
          <LeadStatement>
            Акция под давлением из-за высокой ставки ЦБ, но фундаментально недооценена: ~0,9 капитала и ~4× прибыли — ниже исторических средних.
          </LeadStatement>
        </div>

        {/* KeyTakeaway tones */}
        <div className="tw-bg-bg-elevated tw-border tw-border-border-strong tw-rounded-md tw-shadow-sm dark:tw-shadow-none tw-p-4">
          <div className="tw-flex tw-items-center tw-gap-2 tw-mb-3">
            <span className="tw-text-[13px] tw-font-medium tw-text-text-primary">KeyTakeaway · честная оговорка (info), сила (positive), риск (caution)</span>
            <VisibilityTag tone="open">всегда раскрыт</VisibilityTag>
          </div>
          <div className="tw-flex tw-flex-col tw-gap-3">
            <KeyTakeaway tone="info">
              Данные по стоимости риска противоречивы: при жёсткой ДКП маржа растёт, но кредитный рост тормозит — итог зависит от траектории ставки, которую точно не предсказать.
            </KeyTakeaway>
            <KeyTakeaway tone="positive">
              Экосистема и доля рынка дают устойчивое преимущество по марже относительно конкурентов.
            </KeyTakeaway>
            <KeyTakeaway tone="caution">
              Регуляторное и геополитическое давление исторически сжимает мультипликатор сектора.
            </KeyTakeaway>
          </div>
        </div>

        {/* StatInline */}
        <div className="tw-bg-bg-elevated tw-border tw-border-border-strong tw-rounded-md tw-shadow-sm dark:tw-shadow-none tw-p-4">
          <div className="tw-flex tw-items-center tw-gap-2 tw-mb-3">
            <span className="tw-text-[13px] tw-font-medium tw-text-text-primary">StatInline · число из прозы → мини-визуал</span>
          </div>
          <div className="tw-flex tw-flex-wrap tw-gap-3">
            <StatInline value={formatMultiple(0.9)} label="P/B" tone="accent" />
            <StatInline value={formatMultiple(4)} label="P/E" tone="accent" />
            <StatInline value={formatPercent(1.3)} label="Cost of risk" tone="neutral" />
            <StatInline value={formatPercent(50, { decimals: 0 })} label="Payout" tone="positive" />
          </div>
          <p className="tw-text-[12px] tw-text-text-tertiary tw-mt-3 tw-mb-0">Табличные цифры, продукт-формат (ru-RU). Дублируют число из текста, не заменяя его.</p>
        </div>

        {/* Disclosure */}
        <div className="tw-bg-bg-elevated tw-border tw-border-border-strong tw-rounded-md tw-shadow-sm dark:tw-shadow-none tw-p-4">
          <div className="tw-flex tw-items-center tw-gap-2 tw-mb-3">
            <span className="tw-text-[13px] tw-font-medium tw-text-text-primary">Disclosure · сворачиваемая деталь второго порядка</span>
            <VisibilityTag tone="collapsed">под сворачиванием</VisibilityTag>
          </div>
          <Disclosure summary="Чувствительность прибыли к ставке ЦБ — детали">
            <Prose>
              <p>
                При ставке выше 18 % процентная маржа банка расширяется на горизонте 1–2 кварталов за счёт быстрой переоценки активов, но кредитный портфель в рознице сжимается с лагом 2–3 квартала. Чистый эффект на прибыль зависит от длительности периода высоких ставок: короткий пик — выигрыш по марже; затяжное плато — рост стоимости риска перевешивает.
              </p>
            </Prose>
          </Disclosure>
          <p className="tw-text-[12px] tw-text-text-tertiary tw-mt-3 tw-mb-0">
            Нативный <code>&lt;details&gt;/&lt;summary&gt;</code> — открывается мышью, клавишей Enter/Space, доступен скринридеру. Сюда — ТОЛЬКО детали, не вывод.
          </p>
        </div>
      </div>

      {/* --- Prose: измеритель строки --- */}
      <div className="tw-bg-bg-elevated tw-border tw-border-border-strong tw-rounded-md tw-shadow-sm dark:tw-shadow-none tw-p-4">
        <span className="tw-text-[13px] tw-font-medium tw-text-text-primary">Prose · воздух, межстрочный 1.6, ширина строки ~68 символов</span>
        <div className="tw-mt-3">
          <Prose>
            <p>
              Сбербанк остаётся ключевой историей в индексе и фундаментально выглядит недорого. Текстовый блок оборачивается в <strong>Prose</strong>: межстрочный интервал 1.6, ограниченная ширина строки (~68 символов) и ритм абзацев по 8pt делают плотный текст комфортным для чтения.
            </p>
            <ul>
              <li>списки получают аккуратный отступ и приглушённый маркер;</li>
              <li>ключевые фразы выделяются <strong>полужирным</strong> и поднимаются к основному цвету текста;</li>
              <li>годится и для обёртки отрендеренного markdown.</li>
            </ul>
          </Prose>
        </div>
      </div>

      {/* --- Through sample: было простынёй / стало навигируемо --- */}
      <div>
        <div className="tw-flex tw-items-center tw-gap-2 tw-mb-3">
          <span className="tw-text-[13px] tw-font-semibold tw-text-text-primary">Сквозной образец · «комментарий аналитика по Сберу»</span>
        </div>
        <div className="tw-grid tw-grid-cols-1 lg:tw-grid-cols-2 tw-gap-6">
          {/* BEFORE — wall of text */}
          <div className="tw-bg-bg-elevated tw-border tw-border-border-strong tw-rounded-md tw-shadow-sm dark:tw-shadow-none tw-p-4">
            <div className="tw-text-[12px] tw-uppercase tw-text-text-tertiary tw-mb-2" style={{ letterSpacing: "0.06em" }}>
              Было · простыня
            </div>
            <p className="tw-text-[13px] tw-leading-[1.45] tw-text-text-secondary tw-m-0">{SBER_WALL}</p>
          </div>

          {/* AFTER — navigable */}
          <div className="tw-bg-bg-elevated tw-border tw-border-border-strong tw-rounded-md tw-shadow-sm dark:tw-shadow-none tw-p-4 tw-flex tw-flex-col tw-gap-4">
            <div className="tw-flex tw-items-center tw-gap-2">
              <span className="tw-text-[12px] tw-uppercase tw-text-text-tertiary" style={{ letterSpacing: "0.06em" }}>
                Стало · навигируемо
              </span>
            </div>

            {/* 1. Lead — always visible */}
            <div>
              <VisibilityTag tone="open">1 · вывод — на виду</VisibilityTag>
              <div className="tw-mt-2">
                <LeadStatement>
                  Фундаментально недооценён (~0,9 капитала, ~4× прибыли), но под давлением высокой ставки ЦБ — переоценка вверх зависит от траектории ставки.
                </LeadStatement>
              </div>
            </div>

            {/* 2. Numbers lifted out */}
            <div>
              <div className="tw-text-[11px] tw-uppercase tw-text-text-tertiary tw-mb-2" style={{ letterSpacing: "0.05em" }}>
                2 · числа из текста — наглядно
              </div>
              <div className="tw-flex tw-flex-wrap tw-gap-2">
                <StatInline value={formatMultiple(0.9)} label="P/B" tone="accent" />
                <StatInline value={formatMultiple(4)} label="P/E" tone="accent" />
                <StatInline value={formatPercent(1.3)} label="Cost of risk" />
                <StatInline value={formatPercent(50, { decimals: 0 })} label="Payout" tone="positive" />
              </div>
            </div>

            {/* 3. Full prose with all nuance preserved */}
            <div>
              <div className="tw-text-[11px] tw-uppercase tw-text-text-tertiary tw-mb-2" style={{ letterSpacing: "0.05em" }}>
                3 · полный комментарий — воздух, все нюансы
              </div>
              <Prose>
                <p>
                  Котировки под давлением из-за жёсткой ДКП ЦБ: высокая ставка <strong>одновременно</strong> поддерживает процентную маржу и тормозит кредитование (розница, ипотека), поэтому итоговый эффект на прибыль неоднозначен. Качество активов пока приемлемо, стоимость риска держится около 1,3 %.
                </p>
                <p>
                  Менеджмент подтверждает дивиденды в 50 % прибыли по МСФО — двузначная доходность при текущей цене, но фактическая выплата зависит от достаточности капитала и позиции регулятора.
                </p>
              </Prose>
            </div>

            {/* 4. Honest caveat — always expanded, framed as trust feature */}
            <div>
              <VisibilityTag tone="open">4 · честная оговорка — на виду</VisibilityTag>
              <div className="tw-mt-2">
                <KeyTakeaway tone="info">
                  Данные противоречивы: при жёсткой ДКП маржа растёт, но кредитный рост тормозит, а при затяжном плато высоких ставок возможен рост просрочки в необеспеченной рознице. Итог зависит от траектории ставки, которую точно не предсказать.
                </KeyTakeaway>
              </div>
            </div>

            {/* 5. Second-order detail — collapsed */}
            <div>
              <VisibilityTag tone="collapsed">5 · детали второго порядка — свёрнуто</VisibilityTag>
              <div className="tw-mt-2">
                <Disclosure summary="Регуляторные и геополитические факторы, траектория ставки">
                  <Prose>
                    <p>
                      Рынок закладывает снижение ставки во втором полугодии, но если инфляция окажется устойчивее ожиданий, смягчение сдвинется и переоценка вверх затянется. Отдельно стоит учитывать регуляторные и геополитические риски, которые исторически давили на мультипликатор сектора.
                    </p>
                  </Prose>
                </Disclosure>
              </div>
            </div>
          </div>
        </div>
        <p className="tw-text-[12px] tw-text-text-tertiary tw-mt-3 tw-mb-0 tw-max-w-[68ch]">
          Текст НЕ сокращён — все нюансы и оговорки на месте, 1:1. Изменилась только подача: вывод и честная оговорка <strong className="tw-text-text-primary">на виду</strong>, числа продублированы визуалом, второстепенное — под раскрытие. {reduced ? "Reduced-motion активен — раскрытие мгновенное." : "Раскрытие плавное (200 мс), reduced-motion отключает анимацию."}
        </p>
      </div>
    </div>
  );
}

/* =============================================================
   MARKETING ACCENTS — landing-only variants for the owner to pick.
   Mocks ONLY (real LandingView / Sidebar untouched). Two groups:
   A) «Базис» hero title — 3 gradient treatments (violet→cobalt).
   B) Sidebar rail — 2 icon-colour options (restraint vs light tint).
   Violet end of the gradient uses --accent-2 (defined per theme so it
   reads on both the warm-cream and near-black backgrounds).
   ============================================================= */

// The violet→cobalt fill, shared by all three title variants.
const HERO_GRADIENT = "linear-gradient(135deg, var(--accent-2) 0%, var(--accent) 100%)";

// Base text style: large display weight, gradient clipped into glyphs.
const heroBase = {
  fontFamily: "var(--font-display)",
  fontWeight: 600,
  fontSize: "52px",
  lineHeight: 1.05,
  letterSpacing: "-0.02em",
  margin: 0,
  backgroundImage: HERO_GRADIENT,
  backgroundSize: "100% 100%",
  WebkitBackgroundClip: "text",
  backgroundClip: "text",
  WebkitTextFillColor: "transparent",
  color: "transparent",
  display: "inline-block",
};

function HeroTitleVariant({ label, note, style, reduced, animated = false }) {
  const animStyle =
    animated && !reduced
      ? {
          backgroundSize: "200% 100%",
          animation: "basis-hero-sweep 600ms var(--ease-out) both",
        }
      : {};
  return (
    <div className="tw-bg-bg-elevated tw-border tw-border-border-strong tw-rounded-lg tw-shadow-sm dark:tw-shadow-none tw-p-6">
      <div className="tw-text-[12px] tw-uppercase tw-text-text-tertiary tw-mb-4" style={{ letterSpacing: "0.06em" }}>
        {label}
      </div>
      <div className="tw-py-3">
        <h1 style={{ ...heroBase, ...style, ...animStyle }}>Базис</h1>
      </div>
      <p className="tw-text-[12px] tw-text-text-tertiary tw-mt-4 tw-mb-0 tw-max-w-[34ch]">{note}</p>
    </div>
  );
}

/* --- Sidebar rail mock (icons + labels), two colour treatments --- */

const HomeIcon = (
  <svg width="20" height="20" viewBox="0 0 20 20" fill="none" aria-hidden="true">
    <path d="M3 9l7-6 7 6M5 8v8h10V8" stroke="currentColor" strokeWidth="1.6" strokeLinejoin="round" strokeLinecap="round" />
  </svg>
);
const ChartIcon = (
  <svg width="20" height="20" viewBox="0 0 20 20" fill="none" aria-hidden="true">
    <path d="M3 17V3M3 17h14M7 13v-4M11 13V6M15 13v-7" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round" />
  </svg>
);
const FolderIcon = (
  <svg width="20" height="20" viewBox="0 0 20 20" fill="none" aria-hidden="true">
    <path d="M3 5h5l2 2h7v8H3V5z" stroke="currentColor" strokeWidth="1.6" strokeLinejoin="round" />
  </svg>
);
const GlobeIcon = (
  <svg width="20" height="20" viewBox="0 0 20 20" fill="none" aria-hidden="true">
    <circle cx="10" cy="10" r="7" stroke="currentColor" strokeWidth="1.6" />
    <path d="M3 10h14M10 3c2 2.3 2 11.7 0 14M10 3c-2 2.3-2 11.7 0 14" stroke="currentColor" strokeWidth="1.6" />
  </svg>
);

const SIDEBAR_ITEMS = [
  { icon: HomeIcon, label: "Главная" },
  { icon: ChartIcon, label: "Компании" },
  { icon: FolderIcon, label: "Портфель" },
  { icon: GlobeIcon, label: "Рынок" },
];

function SidebarRailMock({ variant }) {
  // active index fixed to 1 ("Компании") for the mock
  const activeIdx = 1;
  return (
    <div
      className="tw-inline-flex tw-flex-col tw-gap-1 tw-rounded-lg tw-border tw-border-border-subtle tw-bg-bg-elevated tw-shadow-sm dark:tw-shadow-none tw-p-2"
      style={{ width: "72px" }}
    >
      {SIDEBAR_ITEMS.map((it, i) => {
        const active = i === activeIdx;
        // colour resolution per variant
        let color;
        if (active) color = "var(--accent)";
        else if (variant === "tint") color = "color-mix(in srgb, var(--accent) 38%, var(--text-tertiary))";
        else color = "var(--text-tertiary)"; // restraint: neutral
        return (
          <div
            key={it.label}
            className="tw-relative tw-flex tw-flex-col tw-items-center tw-justify-center tw-gap-1 tw-rounded-md tw-py-2 tw-px-1"
            style={{
              background: active ? "var(--accent-soft)" : "transparent",
            }}
          >
            {active && (
              <span
                aria-hidden="true"
                className="tw-absolute tw-left-0 tw-top-1/2 tw--translate-y-1/2 tw-rounded-pill"
                style={{ width: "3px", height: "20px", background: "var(--accent)" }}
              />
            )}
            <span style={{ color }}>{it.icon}</span>
            <span className="tw-text-[9px] tw-leading-none" style={{ color: active ? "var(--accent)" : "var(--text-tertiary)" }}>
              {it.label}
            </span>
          </div>
        );
      })}
    </div>
  );
}

function MarketingAccentsBody({ reduced }) {
  return (
    <div className="tw-flex tw-flex-col tw-gap-10">
      {/* ---- A. Hero title variants ---- */}
      <div>
        <div className="tw-flex tw-items-center tw-gap-2 tw-mb-3">
          <span className="tw-text-[13px] tw-font-semibold tw-text-text-primary">A · Заголовок «Базис» — 3 варианта эффекта (на выбор)</span>
        </div>
        <p className="tw-text-[13px] tw-text-text-secondary tw-mb-4 tw-max-w-[68ch]">
          Самый выразительный элемент первого экрана лендинга: яркий перелив сиреневый→кобальт, а не строгий чёрный. Градиент залит в буквы (<code>background-clip: text</code>). Выберите вариант — эффектнее.
        </p>
        <div className="tw-grid tw-grid-cols-1 md:tw-grid-cols-3 tw-gap-4">
          <HeroTitleVariant
            reduced={reduced}
            label="Вариант 1 · Градиент"
            note="Статичная заливка сиреневый→кобальт. Спокойно, но уже не строгий чёрный."
          />
          <HeroTitleVariant
            reduced={reduced}
            label="Вариант 2 · Градиент + свечение"
            style={{ filter: "drop-shadow(0 6px 18px var(--decor-glow))" }}
            note="Тот же градиент + мягкое акцентное свечение под словом. Объёмнее, «герой» экрана."
          />
          <HeroTitleVariant
            reduced={reduced}
            animated
            label="Вариант 3 · Градиент + анимация появления"
            note={
              reduced
                ? "Reduced-motion активен → статичный градиент + свечение, без анимации."
                : "Перелив градиента слева направо + нарастание свечения, ОДИН раз (~600 мс). Перезагрузите для повтора."
            }
          />
        </div>
        <p className="tw-text-[12px] tw-text-text-tertiary tw-mt-3 tw-mb-0 tw-max-w-[68ch]">
          В тёмной теме сиреневый конец берётся из <code>--accent-2</code> в осветлённом значении (#A78BFA), чтобы перелив читался на почти-чёрном фоне; в светлой — насыщенный #8B5CF6. Свечение завязано на <code>--decor-glow</code> (тоже по теме).
        </p>
      </div>

      {/* ---- B. Sidebar rail variants ---- */}
      <div>
        <div className="tw-flex tw-items-center tw-gap-2 tw-mb-3">
          <span className="tw-text-[13px] tw-font-semibold tw-text-text-primary">B · Сайдбар — цвет иконок (одобрить перед глобальной раскаткой)</span>
        </div>
        <p className="tw-text-[13px] tw-text-text-secondary tw-mb-4 tw-max-w-[68ch]">
          Сайдбар глобальный — он же на аналитических экранах, где держим сдержанность. Цвет должен оживить, но не сделать рабочие экраны пёстрыми. Активный пункт — «Компании».
        </p>
        <div className="tw-flex tw-flex-wrap tw-gap-8">
          <div className="tw-flex tw-flex-col tw-items-center tw-gap-3">
            <SidebarRailMock variant="restraint" />
            <div className="tw-text-center tw-max-w-[180px]">
              <div className="tw-text-[12px] tw-font-medium tw-text-text-primary">Вариант 1 · Сдержанный</div>
              <p className="tw-text-[12px] tw-text-text-tertiary tw-mt-1 tw-mb-0">Активный — кобальт-акцент; неактивные — нейтраль (как сейчас). Для сравнения.</p>
            </div>
          </div>
          <div className="tw-flex tw-flex-col tw-items-center tw-gap-3">
            <SidebarRailMock variant="tint" />
            <div className="tw-text-center tw-max-w-[180px]">
              <div className="tw-text-[12px] tw-font-medium tw-text-text-primary">Вариант 2 · Лёгкий тинт</div>
              <p className="tw-text-[12px] tw-text-text-tertiary tw-mt-1 tw-mb-0">Активный — кобальт; неактивные — лёгкая акцентная примесь (не мёртвый серый, не радуга).</p>
            </div>
          </div>
        </div>
        <p className="tw-text-[12px] tw-text-text-tertiary tw-mt-4 tw-mb-0 tw-max-w-[68ch]">
          Активный пункт в обоих вариантах одинаков: кобальт-иконка, мягкая <code>--accent-soft</code> подложка и тонкий вертикальный индикатор слева. Различие — только в неактивных иконках. Тинт даёт «примесь» через <code>color-mix</code> кобальта в <code>--text-tertiary</code> (38%).
        </p>
      </div>
    </div>
  );
}

/* ---- the actual gallery body (rendered once per theme) ---- */

function Gallery() {
  const [modalOpen, setModalOpen] = useState(false);
  const [tab, setTab] = useState("overview");
  const [chips, setChips] = useState({ growth: true, value: false, dividend: false });
  const reduced = usePrefersReducedMotion();

  const plRows = [
    { metric: "Выручка", y2023: 1240, y2024: 1388, delta: 11.9 },
    { metric: "EBITDA", y2023: 402, y2024: 421, delta: 4.7 },
    { metric: "Чистая прибыль", y2023: 188, y2024: 166, delta: -11.7 },
    { metric: "Свободный денежный поток", y2023: 95, y2024: 112, delta: 17.9 },
  ];
  const fmtBn = (v) => formatNumber(v, { decimals: 0 });
  const plColumns = [
    { key: "metric", label: "Показатель, млрд ₽" },
    { key: "y2023", label: "2023", render: fmtBn },
    { key: "y2024", label: "2024", render: fmtBn },
    { key: "delta", label: "Δ г/г", render: (v) => <Delta value={v} /> },
  ];

  return (
    <div className="tw-max-w-[1280px] tw-mx-auto tw-px-6 tw-py-8 tw-font-sans">
      <Section title="1 · Button">
        <Row label="Варианты (size md)">
          <Button variant="primary">Primary</Button>
          <Button variant="secondary">Secondary</Button>
          <Button variant="ghost">Ghost</Button>
          <Button variant="danger">Danger</Button>
        </Row>
        <Row label="Размеры">
          <Button size="sm">Small</Button>
          <Button size="md">Medium</Button>
          <Button size="lg">Large</Button>
        </Row>
        <Row label="Иконка / loading / disabled">
          <Button iconLeft={Bolt}>С иконкой слева</Button>
          <Button iconRight={Bolt} variant="secondary">Иконка справа</Button>
          <Button loading>Загрузка</Button>
          <Button disabled>Disabled</Button>
        </Row>
      </Section>

      <Section title="2 · IconButton">
        <Row label="Варианты и размеры (зона ≥ 32×32)">
          <IconButton aria-label="Действие" variant="primary">{Bolt}</IconButton>
          <IconButton aria-label="Действие" variant="secondary">{Bolt}</IconButton>
          <IconButton aria-label="Действие" variant="ghost">{Bolt}</IconButton>
          <IconButton aria-label="Действие" variant="danger">{Bolt}</IconButton>
          <IconButton aria-label="Действие" size="sm">{Bolt}</IconButton>
          <IconButton aria-label="Действие" size="lg">{Bolt}</IconButton>
          <IconButton aria-label="Действие" disabled>{Bolt}</IconButton>
        </Row>
      </Section>

      <Section title="3 · Card">
        <div className="tw-grid tw-grid-cols-1 md:tw-grid-cols-3 tw-gap-4">
          <Card>Простая карточка. В светлой теме — мягкая тень, в тёмной — слой + 1px-граница.</Card>
          <Card header="Заголовок карточки">Тело карточки с контентом.</Card>
          <Card header="С футером" footer="Сноска внизу">Карточка с шапкой и подвалом.</Card>
        </div>
      </Section>

      <Section title="4 · Badge">
        <Row>
          <Badge tone="neutral">Neutral</Badge>
          <Badge tone="accent">Accent</Badge>
          <Badge tone="success">▲ Прибыль</Badge>
          <Badge tone="danger">▼ Убыток</Badge>
          <Badge tone="warning">Риск</Badge>
          <Badge tone="info">Инфо</Badge>
        </Row>
      </Section>

      <Section title="5 · Chip">
        <Row label="Выбираемые (selected / default)">
          <Chip selected={chips.growth} onClick={() => setChips((c) => ({ ...c, growth: !c.growth }))}>
            Рост
          </Chip>
          <Chip selected={chips.value} onClick={() => setChips((c) => ({ ...c, value: !c.value }))}>
            Стоимость
          </Chip>
          <Chip selected={chips.dividend} onClick={() => setChips((c) => ({ ...c, dividend: !c.dividend }))}>
            Дивиденды
          </Chip>
          <Chip disabled>Disabled</Chip>
        </Row>
        <Row label="Удаляемый">
          <Chip onRemove={() => {}}>Технологии ✕</Chip>
          <Chip selected onRemove={() => {}}>Нефтегаз ✕</Chip>
        </Row>
      </Section>

      <Section title="6 · Tooltip">
        <Row label="По наведению / фокусу (учитывает reduced-motion)">
          <Tooltip label="Подсказка сверху">
            <Button variant="secondary">Наведи / Tab</Button>
          </Tooltip>
          <Tooltip label="Справа" side="right">
            <Button variant="ghost">Справа</Button>
          </Tooltip>
        </Row>
      </Section>

      <Section title="7 · Input">
        <div className="tw-grid tw-grid-cols-1 md:tw-grid-cols-3 tw-gap-4 tw-max-w-3xl">
          <Input label="Тикер" placeholder="SBER" />
          <Input label="Цена входа" defaultValue="abc" error="Введите число" />
          <Input label="Заблокировано" placeholder="недоступно" disabled />
        </div>
      </Section>

      <Section title="8 · Select">
        <div className="tw-grid tw-grid-cols-1 md:tw-grid-cols-3 tw-gap-4 tw-max-w-3xl">
          <Select
            label="Сектор"
            options={[
              { value: "oil", label: "Нефтегаз" },
              { value: "metals", label: "Металлургия" },
              { value: "tech", label: "Технологии" },
            ]}
          />
          <Select label="Период" options={[{ value: "y", label: "Год" }, { value: "q", label: "Квартал" }]} />
          <Select label="Недоступно" options={[{ value: "x", label: "—" }]} disabled />
        </div>
      </Section>

      <Section title="9 · Modal">
        <Row label="Esc или крест закрывают; появление 320мс">
          <Button onClick={() => setModalOpen(true)}>Открыть модалку</Button>
        </Row>
        <Modal
          open={modalOpen}
          onClose={() => setModalOpen(false)}
          title="Подтверждение"
          footer={
            <>
              <Button variant="ghost" onClick={() => setModalOpen(false)}>Отмена</Button>
              <Button onClick={() => setModalOpen(false)}>Подтвердить</Button>
            </>
          }
        >
          Это базовая модалка дизайн-системы. Затемнение фона + панель на overlay-поверхности с тенью xl.
        </Modal>
      </Section>

      <Section title="10 · Tabs">
        <Tabs
          value={tab}
          onChange={setTab}
          tabs={[
            { value: "overview", label: "Обзор", content: "Содержимое вкладки «Обзор»." },
            { value: "model", label: "Бизнес-модель", content: "Содержимое вкладки «Бизнес-модель»." },
            { value: "fin", label: "Финансы", content: "Содержимое вкладки «Финансы»." },
          ]}
        />
      </Section>

      <Section title="11 · Table (финансовый стиль)">
        <Table caption="P&L · числа вправо, табличные моноцифры, дельты с ▲/▼" columns={plColumns} rows={plRows} />
      </Section>

      <Section title="12 · KpiTile">
        <div className="tw-grid tw-grid-cols-1 sm:tw-grid-cols-2 lg:tw-grid-cols-4 tw-gap-4">
          <KpiTile caption="Выручка" value={formatNumber(1388, { decimals: 0 })} unit="млрд ₽" delta={11.9} spark={[120, 124, 122, 130, 135, 139]} />
          <KpiTile caption="Чистая прибыль" value={formatNumber(166, { decimals: 0 })} unit="млрд ₽" delta={-11.7} spark={[188, 180, 175, 170, 168, 166]} />
          <KpiTile caption="Цена акции" value={formatMoney(4977.5, { decimals: 1 })} delta={1.4} spark={[4810, 4860, 4905, 4940, 4960, 4977]} />
          <KpiTile caption="P/E" value={formatMultiple(6.4)} delta={0} />
          <KpiTile caption="Див. доходность" value={formatPercent(9.2)} delta={2.1} spark={[7, 7.5, 8, 8.4, 9, 9.2]} />
        </div>
      </Section>

      <Section title="13 · Живость и глубина (язык: сдержанность + точки жизни)">
        <LiveDepthPreamble />
        <LiveDepthBody />
      </Section>

      <Section title="14 · Читаемость плотного контента (текстовые примитивы)">
        <div className="tw-mb-4 tw-max-w-[68ch]">
          <p className="tw-text-[14px] tw-text-text-secondary tw-m-0">
            Плотный аналитический текст становится <strong className="tw-text-text-primary">навигируемым</strong>, не теряя смысла. Вывод и честные оговорки — всегда на виду; под сворачивание уходит только второстепенное. Меньше текста — это провал; задача — иерархия и сканируемость.
          </p>
        </div>
        <ReadabilityBody reduced={reduced} />
      </Section>

      <Section title="15 · Маркетинг-акценты лендинга (варианты на выбор)">
        <div className="tw-mb-4 tw-max-w-[68ch]">
          <p className="tw-text-[14px] tw-text-text-secondary tw-m-0">
            Только моки для выбора владельцем. Заголовок «Базис» — <strong className="tw-text-text-primary">яркий акцент</strong> первого экрана лендинга; сайдбар — глобальный, поэтому цвет дозирован, чтобы не рябило на аналитических экранах. Реальные страницы не тронуты.
          </p>
        </div>
        <MarketingAccentsBody reduced={reduced} />
      </Section>

      <Section title="16 · Логомарк «Basis» — концепты фирменного знака (на выбор)">
        <div className="tw-mb-4 tw-max-w-[68ch]">
          <p className="tw-text-[14px] tw-text-text-secondary tw-m-0">
            Только моки для выбора владельцем — текущий логотип (иконка <code>Activity</code>) это заглушка. Знак должен нести ценности бренда: <strong className="tw-text-text-primary">доверие, логика, основа/базис, снижение неопределённости, второе мнение</strong>. Каждый концепт показан в разных размерах (вкл. фавикон 16/32px) и обеих темах. На токенах: кобальт <code>--accent</code> + нейтрали, акцент-2 дозированно. Реальный сайдбар/фавикон не тронуты.
          </p>
        </div>
        <LogomarkBody />
      </Section>
    </div>
  );
}

/* ---- page shell: top toggle + both themes side-by-side ---- */

export default function DesignSystem() {
  const [page, setPage] = useState("light"); // overall page toggle

  return (
    <div className={page === "dark" ? "dark" : "light"}>
      <div className="tw-min-h-screen tw-bg-bg-base tw-text-text-primary">
        <header className="tw-sticky tw-top-0 tw-z-40 tw-bg-bg-elevated tw-border-b tw-border-border-subtle tw-shadow-sm">
          <div className="tw-max-w-[1280px] tw-mx-auto tw-px-6 tw-py-4 tw-flex tw-items-center tw-justify-between">
            <div>
              <h1 className="tw-text-[28px] tw-font-semibold tw-font-display tw-text-text-primary tw-m-0">
                Basis · Дизайн-система
              </h1>
              <p className="tw-text-[13px] tw-text-text-tertiary tw-m-0">
                Фаза 2 · библиотека базовых примитивов · маршрут /_design
              </p>
            </div>
            <Button
              variant="secondary"
              onClick={() => setPage((p) => (p === "dark" ? "light" : "dark"))}
              className="tw-bg-bg-elevated tw-text-text-primary tw-border-border-strong hover:tw-bg-bg-hover"
            >
              {page === "dark" ? "☀ Светлая тема" : "☾ Тёмная тема"}
            </Button>
          </div>
        </header>

        <main className="tw-px-2 tw-py-2">
          {/* LIGHT section — `.light` forces light tokens regardless of global theme */}
          <div className="light tw-bg-bg-base">
            <div className="tw-max-w-[1280px] tw-mx-auto tw-px-6 tw-pt-6">
              <Badge tone="accent">Светлая тема</Badge>
            </div>
            <Gallery />
          </div>

          {/* DARK section — `.dark` re-resolves tokens locally */}
          <div className="dark tw-bg-bg-base tw-border-t tw-border-border-strong">
            <div className="tw-max-w-[1280px] tw-mx-auto tw-px-6 tw-pt-6">
              <Badge tone="accent">Тёмная тема</Badge>
            </div>
            <Gallery />
          </div>
        </main>
      </div>
    </div>
  );
}

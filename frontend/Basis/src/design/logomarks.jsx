// =============================================================
// BASIS LOGOMARK CONCEPTS — gallery-only (route /_design).
// Four candidate brand marks for «Basis», an independent
// investment-analytics platform. Values: trust, logic, base/
// foundation, reducing uncertainty, second opinion.
//
// Pure inline SVG, coloured ONLY via design tokens (cobalt
// --accent + neutrals, --accent-2 used sparingly). No raster.
// Each mark takes a `size` prop and uses a fixed viewBox so it
// scales crisply from 16px (favicon) up to 64px (hero).
//
// This file defines the marks + a showcase body. It is rendered
// inside DesignSystem.jsx ONLY — real Sidebar / index.html /
// App.js are NOT touched. The owner picks a direction here.
// =============================================================
import React from "react";

const cx = (...parts) => parts.filter(Boolean).join(" ");

/* =============================================================
   CONCEPT 1 — «Монограмма B / слои-фундамент»
   The letter B built from stacked horizontal bands sitting on a
   base line: reads as a B at large size, as a solid layered block
   at favicon size. Idea: a brand built on layers of analysis,
   resting on a firm foundation.
   ============================================================= */
export function MarkMonogram({ size = 32, title = "Basis — монограмма B" }) {
  return (
    <svg
      width={size}
      height={size}
      viewBox="0 0 32 32"
      role="img"
      aria-label={title}
      fill="none"
    >
      {/* rounded square plate (soft accent wash) */}
      <rect x="1" y="1" width="30" height="30" rx="7" fill="var(--accent-soft)" />
      {/* B spine */}
      <rect x="8.5" y="7" width="3.2" height="18" rx="1.2" fill="var(--accent)" />
      {/* upper bowl */}
      <path
        d="M11.7 7h6.4c2.7 0 4.6 1.7 4.6 4.2 0 2.5-1.9 4.1-4.6 4.1h-6.4V7z"
        fill="var(--accent)"
      />
      {/* lower bowl (slightly wider — the "foundation") */}
      <path
        d="M11.7 15.3h7.1c2.9 0 4.9 1.8 4.9 4.4 0 2.6-2 4.3-4.9 4.3h-7.1v-8.7z"
        fill="var(--accent)"
      />
      {/* knockout slits = the layer separation, drawn in plate colour */}
      <rect x="13.4" y="9.4" width="6.2" height="2.4" rx="1.2" fill="var(--bg-elevated)" />
      <rect x="13.4" y="17.7" width="6.8" height="2.6" rx="1.3" fill="var(--bg-elevated)" />
      {/* base line under the mark — the "basis" */}
      <rect x="7" y="26.4" width="18" height="2" rx="1" fill="var(--accent)" opacity="0.55" />
    </svg>
  );
}

/* =============================================================
   CONCEPT 2 — «Опора / базис: рост на прочной основе»
   A thick grounded base bar; from it rises a stepped column
   (a small chart / growth) anchored on the base. Idea: growth
   that stands on a solid foundation — disciplined, not hype.
   ============================================================= */
export function MarkFoundation({ size = 32, title = "Basis — опора и рост" }) {
  return (
    <svg
      width={size}
      height={size}
      viewBox="0 0 32 32"
      role="img"
      aria-label={title}
      fill="none"
    >
      {/* rising steps standing on the base */}
      <rect x="8" y="16" width="4" height="8" rx="1.2" fill="var(--accent)" opacity="0.55" />
      <rect x="14" y="11" width="4" height="13" rx="1.2" fill="var(--accent)" opacity="0.78" />
      <rect x="20" y="6" width="4" height="18" rx="1.2" fill="var(--accent)" />
      {/* the foundation — one strong horizontal that everything rests on */}
      <rect x="4" y="24.5" width="24" height="3.6" rx="1.8" fill="var(--accent)" />
      {/* tiny pier marks under the base = piles into bedrock */}
      <rect x="7" y="28.4" width="2.4" height="2.4" rx="0.8" fill="var(--accent)" opacity="0.45" />
      <rect x="22.6" y="28.4" width="2.4" height="2.4" rx="0.8" fill="var(--accent)" opacity="0.45" />
    </svg>
  );
}

/* =============================================================
   CONCEPT 3 — «Призма / грань: второе мнение»
   A triangular prism with an incoming ray splitting into a small
   fan on exit. Idea: one input seen through analysis becomes a
   spectrum of perspectives — the "second opinion". Accent-2
   (violet) is used sparingly here for ONE refracted ray, the rest
   cobalt — the single dosed marketing touch.
   ============================================================= */
export function MarkPrism({ size = 32, title = "Basis — призма, второе мнение" }) {
  return (
    <svg
      width={size}
      height={size}
      viewBox="0 0 32 32"
      role="img"
      aria-label={title}
      fill="none"
    >
      {/* incoming ray */}
      <rect x="2" y="15" width="7" height="2" rx="1" fill="var(--accent)" opacity="0.6" />
      {/* prism body */}
      <path
        d="M11 24L18 7l7 17H11z"
        fill="var(--accent-soft)"
        stroke="var(--accent)"
        strokeWidth="2"
        strokeLinejoin="round"
      />
      {/* refracted fan on exit — three diverging rays (one violet) */}
      <path d="M22.5 18.5l7.5-3" stroke="var(--accent)" strokeWidth="2" strokeLinecap="round" />
      <path d="M23 21l7 0.5" stroke="var(--accent-2)" strokeWidth="2" strokeLinecap="round" />
      <path d="M22.5 23.5l7 4" stroke="var(--accent)" strokeWidth="2" strokeLinecap="round" opacity="0.55" />
    </svg>
  );
}

/* =============================================================
   CONCEPT 4 — «Оси данных / координата»
   Minimal mark from an L-shaped axis (the base + the upright)
   with a plotted point and a short trend tick. Idea: clear,
   honest data on coordinates — analytics distilled to a glyph.
   Extremely legible at 16px because it is just 3 strokes + a dot.
   ============================================================= */
export function MarkAxes({ size = 32, title = "Basis — оси данных" }) {
  return (
    <svg
      width={size}
      height={size}
      viewBox="0 0 32 32"
      role="img"
      aria-label={title}
      fill="none"
    >
      {/* L axis — vertical + horizontal base */}
      <path
        d="M8 5v19h19"
        stroke="var(--accent)"
        strokeWidth="2.6"
        strokeLinecap="round"
        strokeLinejoin="round"
      />
      {/* trend line rising to the plotted point */}
      <path
        d="M11 20l5-5 4 2 5-8"
        stroke="var(--accent)"
        strokeWidth="2.2"
        strokeLinecap="round"
        strokeLinejoin="round"
        opacity="0.45"
      />
      {/* the plotted point — the conclusion / second opinion */}
      <circle cx="25" cy="9" r="3.2" fill="var(--accent)" />
      <circle cx="25" cy="9" r="3.2" fill="none" stroke="var(--bg-elevated)" strokeWidth="1.4" />
    </svg>
  );
}

/* =============================================================
   MONOGRAM «B» — COLOUR EXPLORATIONS (gallery-only)
   The owner picked Concept 1 («слои-фундамент»). Before locking the
   final, he wants to see COLOUR variants. The letter geometry is the
   SAME approved mark (B from horizontal layers on a base line) — we
   vary ONLY two dimensions: (1) the colour of the B itself, (2) the
   plate/background behind it.

   `MonogramB` below is the approved geometry, fully parameterised by
   tokens. Each variant passes a different palette. A unique gradient
   id per render avoids <defs> collisions when many marks share a page.
   ============================================================= */
let __mbUID = 0;

/**
 * Approved «слои-фундамент» B, colour-parameterised.
 * Props (all token strings, no raw hex):
 *  - letter:   fill of the B strokes/bowls (can be a url(#grad))
 *  - letterBottom: optional darker/denser fill for the LOWER bowl +
 *                  base line ("foundation" — bottom layers heavier);
 *                  defaults to `letter`.
 *  - plate:    fill of the rounded-square container (or "none")
 *  - slit:     knockout colour for the two layer slits (must read as
 *              "cut out of the B" — usually = plate, or bg when plate
 *              is transparent)
 *  - border:   optional stroke colour for the plate (neutral chip look)
 *  - baseOpacity: opacity of the under-mark base line (default 0.55)
 */
export function MonogramB({
  size = 32,
  letter = "var(--accent)",
  letterBottom,
  plate = "none",
  slit = "var(--bg-elevated)",
  border = "none",
  baseOpacity = 0.55,
  title = "Basis — монограмма B",
}) {
  const lower = letterBottom || letter;
  return (
    <svg
      width={size}
      height={size}
      viewBox="0 0 32 32"
      role="img"
      aria-label={title}
      fill="none"
    >
      {/* plate-container behind the letter */}
      {plate !== "none" && (
        <rect x="1" y="1" width="30" height="30" rx="7" fill={plate} />
      )}
      {border !== "none" && (
        <rect
          x="1.5"
          y="1.5"
          width="29"
          height="29"
          rx="6.5"
          fill="none"
          stroke={border}
          strokeWidth="1.4"
        />
      )}
      {/* B spine */}
      <rect x="8.5" y="7" width="3.2" height="18" rx="1.2" fill={letter} />
      {/* upper bowl */}
      <path d="M11.7 7h6.4c2.7 0 4.6 1.7 4.6 4.2 0 2.5-1.9 4.1-4.6 4.1h-6.4V7z" fill={letter} />
      {/* lower bowl (wider — the "foundation"; can be heavier) */}
      <path d="M11.7 15.3h7.1c2.9 0 4.9 1.8 4.9 4.4 0 2.6-2 4.3-4.9 4.3h-7.1v-8.7z" fill={lower} />
      {/* knockout slits = the layer separation */}
      <rect x="13.4" y="9.4" width="6.2" height="2.4" rx="1.2" fill={slit} />
      <rect x="13.4" y="17.7" width="6.8" height="2.6" rx="1.3" fill={slit} />
      {/* base line under the mark — the "basis" */}
      <rect x="7" y="26.4" width="18" height="2" rx="1" fill={lower} opacity={baseOpacity} />
    </svg>
  );
}

/* =============================================================
   PRODUCTION LOGOMARK — the approved «Слои-фундамент (моно-кобальт)».
   Re-usable export wired into the real Sidebar (App.js). Geometry is
   the same approved B-from-layers on a base line; the foundation
   gradient makes upper layers lighter and the lower bowl + base line
   full-strength cobalt. Token-only colour → correct in BOTH themes.
   `slit` knocks the layer separations out to the surface behind the
   mark (sidebar uses the elevated rail surface). Static — no motion,
   safe for prefers-reduced-motion by construction.
   ============================================================= */
export function BasisLogomark({
  size = 28,
  slit = "var(--bg-elevated)",
  crisp = false,
  title = "Basis",
}) {
  return <MonogramBGrad size={size} kind="foundation" plate="none" slit={slit} crisp={crisp} title={title} />;
}

/* Gradient-aware monogram: injects a per-instance linearGradient and
   uses it for the requested target ("letter" cobalt→violet, or
   "foundation" cobalt-light→cobalt for the heavier bottom layers).
   Kept separate so the simple MonogramB stays gradient-free. */
function MonogramBGrad({ size = 32, kind = "letter", plate = "none", slit = "var(--bg-elevated)", border = "none", whiteOnPlate = false, crisp = false, title }) {
  const uid = React.useMemo(() => `mb-${++__mbUID}`, []);
  const top = whiteOnPlate ? "var(--on-accent)" : "var(--accent)";
  /* `crisp` режим (сайдбар): верхние слои фундамента почти полностью кобальтовые
     (0.85 вместо 0.62) → на near-black знак читается чётким кобальтом без серого
     ореола, но всё ещё чуть легче сверху → «слои-фундамент» сохраняются. */
  const fdTopOpacity = crisp ? "0.85" : "0.62";
  const bowlTopOpacity = crisp ? "0.85" : "0.62";
  return (
    <svg width={size} height={size} viewBox="0 0 32 32" role="img" aria-label={title || "Basis — монограмма B"} fill="none">
      <defs>
        {/* cobalt → violet, used across the whole letter */}
        <linearGradient id={`${uid}-cv`} x1="8" y1="7" x2="24" y2="24" gradientUnits="userSpaceOnUse">
          <stop offset="0" stopColor="var(--accent)" />
          <stop offset="1" stopColor="var(--accent-2)" />
        </linearGradient>
        {/* foundation: lighter cobalt up top → full cobalt at the base */}
        <linearGradient id={`${uid}-fd`} x1="16" y1="7" x2="16" y2="28" gradientUnits="userSpaceOnUse">
          <stop offset="0" stopColor="var(--accent)" stopOpacity={fdTopOpacity} />
          <stop offset="1" stopColor="var(--accent)" stopOpacity="1" />
        </linearGradient>
      </defs>
      {plate !== "none" && <rect x="1" y="1" width="30" height="30" rx="7" fill={plate} />}
      {border !== "none" && (
        <rect x="1.5" y="1.5" width="29" height="29" rx="6.5" fill="none" stroke={border} strokeWidth="1.4" />
      )}
      {kind === "letter" ? (
        <>
          <rect x="8.5" y="7" width="3.2" height="18" rx="1.2" fill={`url(#${uid}-cv)`} />
          <path d="M11.7 7h6.4c2.7 0 4.6 1.7 4.6 4.2 0 2.5-1.9 4.1-4.6 4.1h-6.4V7z" fill={`url(#${uid}-cv)`} />
          <path d="M11.7 15.3h7.1c2.9 0 4.9 1.8 4.9 4.4 0 2.6-2 4.3-4.9 4.3h-7.1v-8.7z" fill={`url(#${uid}-cv)`} />
          <rect x="13.4" y="9.4" width="6.2" height="2.4" rx="1.2" fill={slit} />
          <rect x="13.4" y="17.7" width="6.8" height="2.6" rx="1.3" fill={slit} />
          <rect x="7" y="26.4" width="18" height="2" rx="1" fill="var(--accent-2)" opacity="0.55" />
        </>
      ) : (
        <>
          {/* foundation gradient: top layers light, bottom bowl + base full cobalt */}
          <rect x="8.5" y="7" width="3.2" height="18" rx="1.2" fill={`url(#${uid}-fd)`} />
          <path d="M11.7 7h6.4c2.7 0 4.6 1.7 4.6 4.2 0 2.5-1.9 4.1-4.6 4.1h-6.4V7z" fill={top} opacity={bowlTopOpacity} />
          <path d="M11.7 15.3h7.1c2.9 0 4.9 1.8 4.9 4.4 0 2.6-2 4.3-4.9 4.3h-7.1v-8.7z" fill={top} />
          <rect x="13.4" y="9.4" width="6.2" height="2.4" rx="1.2" fill={slit} />
          <rect x="13.4" y="17.7" width="6.8" height="2.6" rx="1.3" fill={slit} />
          <rect x="7" y="26.4" width="18" height="2" rx="1" fill={top} opacity="0.9" />
        </>
      )}
    </svg>
  );
}

/* Plate with a cobalt→violet gradient fill (for the "градиент-плашка"
   variant) + a white B on top. Per-instance gradient id. */
function MonogramBPlateGrad({ size = 32, title }) {
  const uid = React.useMemo(() => `mp-${++__mbUID}`, []);
  return (
    <svg width={size} height={size} viewBox="0 0 32 32" role="img" aria-label={title || "Basis — монограмма B, градиент-плашка"} fill="none">
      <defs>
        <linearGradient id={`${uid}-pg`} x1="2" y1="2" x2="30" y2="30" gradientUnits="userSpaceOnUse">
          <stop offset="0" stopColor="var(--accent)" />
          <stop offset="1" stopColor="var(--accent-2)" />
        </linearGradient>
      </defs>
      <rect x="1" y="1" width="30" height="30" rx="7" fill={`url(#${uid}-pg)`} />
      <rect x="8.5" y="7" width="3.2" height="18" rx="1.2" fill="var(--on-accent)" />
      <path d="M11.7 7h6.4c2.7 0 4.6 1.7 4.6 4.2 0 2.5-1.9 4.1-4.6 4.1h-6.4V7z" fill="var(--on-accent)" />
      <path d="M11.7 15.3h7.1c2.9 0 4.9 1.8 4.9 4.4 0 2.6-2 4.3-4.9 4.3h-7.1v-8.7z" fill="var(--on-accent)" />
      {/* slits knock out to the gradient → fill with a translucent dark so
          they read as cuts regardless of where on the gradient they sit */}
      <rect x="13.4" y="9.4" width="6.2" height="2.4" rx="1.2" fill={`url(#${uid}-pg)`} />
      <rect x="13.4" y="17.7" width="6.8" height="2.6" rx="1.3" fill={`url(#${uid}-pg)`} />
      <rect x="7" y="26.4" width="18" height="2" rx="1" fill="var(--on-accent)" opacity="0.5" />
    </svg>
  );
}

/* ---- registry of COLOUR variants of monogram B (6–8 tasty pairs) ----
   Each `render(size)` returns the mark at that size. Caption = letter × bg. */
export const MONOGRAM_VARIANTS = [
  {
    key: "cobalt-transparent",
    name: "Кобальт на прозрачном",
    note: "Буква: кобальт --accent · Фон: прозрачный",
    render: (size) => (
      <MonogramB size={size} letter="var(--accent)" plate="none" slit="var(--bg-base)" baseOpacity={0.5} />
    ),
  },
  {
    key: "white-on-cobalt",
    name: "Белая B на кобальтовой плашке",
    note: "Буква: белая --on-accent · Фон: плашка --accent (app-icon)",
    render: (size) => (
      <MonogramB size={size} letter="var(--on-accent)" plate="var(--accent)" slit="var(--accent)" baseOpacity={0.5} />
    ),
  },
  {
    key: "cobalt-on-soft",
    name: "Кобальт на мягкой плашке",
    note: "Буква: кобальт --accent · Фон: мягкая плашка --accent-soft",
    render: (size) => (
      <MonogramB size={size} letter="var(--accent)" plate="var(--accent-soft)" slit="var(--bg-elevated)" baseOpacity={0.5} />
    ),
  },
  {
    key: "cobalt-on-neutral",
    name: "Кобальт на нейтральной плашке",
    note: "Буква: кобальт --accent · Фон: нейтраль --bg-elevated + рамка --border-strong",
    render: (size) => (
      <MonogramB size={size} letter="var(--accent)" plate="var(--bg-elevated)" border="var(--border-strong)" slit="var(--bg-elevated)" baseOpacity={0.5} />
    ),
  },
  {
    key: "foundation-mono",
    name: "Слои-фундамент (моно-кобальт)",
    note: "Буква: верхние слои светлее → нижний слой и база насыщенный кобальт · Фон: прозрачный",
    render: (size) => (
      <MonogramBGrad size={size} kind="foundation" plate="none" slit="var(--bg-base)" />
    ),
  },
  {
    key: "letter-gradient",
    name: "Градиент буквы (кобальт→violet)",
    note: "Буква: градиент --accent→--accent-2 · Фон: прозрачный (акцент-2 дозированно)",
    render: (size) => (
      <MonogramBGrad size={size} kind="letter" plate="none" slit="var(--bg-base)" />
    ),
  },
  {
    key: "gradient-plate",
    name: "Градиент-плашка + белая B",
    note: "Буква: белая --on-accent · Фон: градиентная плашка --accent→--accent-2",
    render: (size) => <MonogramBPlateGrad size={size} />,
  },
  {
    key: "deep-plate",
    name: "Тёмная фирменная плашка",
    note: "Буква: светлый кобальт --accent · Фон: глубокая плашка --text-primary",
    render: (size) => (
      <MonogramB size={size} letter="var(--accent)" letterBottom="var(--accent)" plate="var(--text-primary)" slit="var(--text-primary)" baseOpacity={0.6} />
    ),
  },
];

/* ---- registry of concepts ---- */
export const LOGOMARKS = [
  {
    key: "monogram",
    Mark: MarkMonogram,
    name: "Монограмма B · слои-фундамент",
    idea: "Буква B собрана из горизонтальных слоёв на опорной линии. Бренд, выстроенный на слоях анализа, стоящих на прочном основании.",
  },
  {
    key: "foundation",
    Mark: MarkFoundation,
    name: "Опора · рост на прочной базе",
    idea: "Толстая горизонталь-основание, из неё растут ступени-столбики. Дисциплинированный рост, стоящий на твёрдом базисе, а не на хайпе.",
  },
  {
    key: "prism",
    Mark: MarkPrism,
    name: "Призма · второе мнение",
    idea: "Луч входит в грань и расходится веером перспектив. Один вход через анализ → спектр взглядов. Один луч — акцент-2 (дозированно).",
  },
  {
    key: "axes",
    Mark: MarkAxes,
    name: "Оси данных · координата",
    idea: "L-ось (основание + вертикаль) с трендом и нанесённой точкой. Честные данные на координатах — аналитика, сжатая до глифа.",
  },
];

/* =============================================================
   WORDMARK LOCKUP — mark + the word «Basis» beside it.
   Uses the display font + cobalt; gallery preview only.
   ============================================================= */
function Lockup({ Mark }) {
  return (
    <div className="tw-inline-flex tw-items-center tw-gap-2.5">
      <Mark size={28} />
      <span
        className="tw-text-text-primary"
        style={{
          fontFamily: "var(--font-display)",
          fontWeight: 600,
          fontSize: "22px",
          letterSpacing: "-0.01em",
          lineHeight: 1,
        }}
      >
        Basis
      </span>
    </div>
  );
}

/* small labelled swatch for one rendered size */
function SizeSwatch({ Mark, px, note }) {
  return (
    <div className="tw-flex tw-flex-col tw-items-center tw-gap-1.5">
      <div
        className="tw-flex tw-items-center tw-justify-center tw-rounded-md tw-border tw-border-border-subtle tw-bg-bg-base"
        style={{ width: "72px", height: "72px" }}
      >
        <Mark size={px} />
      </div>
      <span className="tw-text-[11px] tw-text-text-tertiary tw-leading-none">{note}</span>
    </div>
  );
}

function ConceptCard({ concept }) {
  const { Mark, name, idea } = concept;
  return (
    <div className="tw-bg-bg-elevated tw-border tw-border-border-strong tw-rounded-lg tw-shadow-sm dark:tw-shadow-none tw-p-5 tw-flex tw-flex-col tw-gap-4">
      {/* header: name + hero-size mark */}
      <div className="tw-flex tw-items-center tw-justify-between tw-gap-3">
        <div>
          <div className="tw-text-[14px] tw-font-semibold tw-text-text-primary">{name}</div>
          <p className="tw-text-[12px] tw-text-text-secondary tw-mt-1 tw-mb-0 tw-max-w-[44ch]">{idea}</p>
        </div>
        {/* hero — ~64px */}
        <div className="tw-shrink-0">
          <Mark size={64} />
        </div>
      </div>

      {/* size ramp incl. favicon sizes */}
      <div className="tw-flex tw-flex-wrap tw-items-end tw-gap-4 tw-pt-1">
        <SizeSwatch Mark={Mark} px={32} note="32 · сайдбар" />
        <SizeSwatch Mark={Mark} px={24} note="24 · сайдбар" />
        <SizeSwatch Mark={Mark} px={32} note="32 · фавикон" />
        <SizeSwatch Mark={Mark} px={16} note="16 · фавикон" />
      </div>

      {/* favicon legibility strip — marks on the actual tiny scale, inline */}
      <div className="tw-flex tw-items-center tw-gap-3 tw-rounded-md tw-bg-bg-base tw-border tw-border-border-subtle tw-px-3 tw-py-2">
        <span className="tw-text-[11px] tw-uppercase tw-text-text-tertiary" style={{ letterSpacing: "0.05em" }}>
          16px в ряд
        </span>
        <Mark size={16} />
        <Mark size={16} />
        <Mark size={16} />
        <span className="tw-text-[11px] tw-text-text-tertiary">— читается в мелком</span>
      </div>

      {/* wordmark lockup */}
      <div className="tw-flex tw-items-center tw-gap-3 tw-pt-1">
        <span className="tw-text-[11px] tw-uppercase tw-text-text-tertiary" style={{ letterSpacing: "0.05em" }}>
          Лого + слово
        </span>
        <Lockup Mark={Mark} />
      </div>
    </div>
  );
}

/* ---- the showcase body (rendered once per theme by the gallery) ---- */
export function LogomarkBody() {
  return (
    <div className="tw-grid tw-grid-cols-1 lg:tw-grid-cols-2 tw-gap-5">
      {LOGOMARKS.map((c) => (
        <ConceptCard key={c.key} concept={c} />
      ))}
    </div>
  );
}

/* =============================================================
   MONOGRAM B — PALETTE showcase. One card per colour variant.
   Shows: presentation size (~60px), favicon 32 + 16, a 16px row to
   judge tiny legibility, and the caption (letter × bg). Rendered once
   per theme by the gallery, so both themes are covered automatically.
   ============================================================= */
function PaletteSizeSwatch({ render, px, note }) {
  return (
    <div className="tw-flex tw-flex-col tw-items-center tw-gap-1.5">
      <div
        className="tw-flex tw-items-center tw-justify-center tw-rounded-md tw-border tw-border-border-subtle tw-bg-bg-base"
        style={{ width: "72px", height: "72px" }}
      >
        {render(px)}
      </div>
      <span className="tw-text-[11px] tw-text-text-tertiary tw-leading-none">{note}</span>
    </div>
  );
}

function PaletteVariantCard({ variant }) {
  const { render, name, note } = variant;
  return (
    <div className="tw-bg-bg-elevated tw-border tw-border-border-strong tw-rounded-lg tw-shadow-sm dark:tw-shadow-none tw-p-5 tw-flex tw-flex-col tw-gap-4">
      {/* header: name + presentation-size mark */}
      <div className="tw-flex tw-items-center tw-justify-between tw-gap-3">
        <div>
          <div className="tw-text-[14px] tw-font-semibold tw-text-text-primary">{name}</div>
          <p className="tw-text-[12px] tw-text-text-secondary tw-mt-1 tw-mb-0 tw-max-w-[40ch]">{note}</p>
        </div>
        {/* presentation — ~60px */}
        <div className="tw-shrink-0">{render(60)}</div>
      </div>

      {/* size ramp incl. favicon sizes */}
      <div className="tw-flex tw-flex-wrap tw-items-end tw-gap-4 tw-pt-1">
        <PaletteSizeSwatch render={render} px={56} note="56 · презентация" />
        <PaletteSizeSwatch render={render} px={32} note="32 · фавикон" />
        <PaletteSizeSwatch render={render} px={16} note="16 · фавикон" />
      </div>

      {/* 16px legibility strip — judge whether the B reads tiny */}
      <div className="tw-flex tw-items-center tw-gap-3 tw-rounded-md tw-bg-bg-base tw-border tw-border-border-subtle tw-px-3 tw-py-2">
        <span className="tw-text-[11px] tw-uppercase tw-text-text-tertiary" style={{ letterSpacing: "0.05em" }}>
          16px в ряд
        </span>
        {render(16)}
        {render(16)}
        {render(16)}
        <span className="tw-text-[11px] tw-text-text-tertiary">— читается ли B мелко</span>
      </div>
    </div>
  );
}

/* The palette showcase body — rendered inside section «16 · Логомарк». */
export function MonogramPaletteBody() {
  return (
    <div className="tw-grid tw-grid-cols-1 lg:tw-grid-cols-2 tw-gap-5">
      {MONOGRAM_VARIANTS.map((v) => (
        <PaletteVariantCard key={v.key} variant={v} />
      ))}
    </div>
  );
}

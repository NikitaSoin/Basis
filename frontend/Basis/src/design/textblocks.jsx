// =============================================================
// BASIS TEXT PRIMITIVES — «Читаемость плотного контента» phase
// Pure JS (no TS). Styled exclusively via `tw-` Tailwind utilities
// that map onto the design tokens in src/styles/tokens.css.
//
// GOAL: make dense analyst text NAVIGABLE without gutting meaning.
// Less text = failure. These primitives add hierarchy and scan-ability:
//   • Lead / takeaway = the bottom line, ALWAYS visible.
//   • Disclosure      = second-order detail only, one click away.
//   • StatInline      = a number lifted out of prose into a mini-visual.
// Accessibility: native <details>/<summary> (keyboard + screen reader),
// focus-rings, prefers-reduced-motion gates every transition. No hex.
// =============================================================
import React, { useId } from "react";
import { usePrefersReducedMotion } from "./primitives";

const cx = (...parts) => parts.filter(Boolean).join(" ");
const FOCUS = "focus-visible:tw-outline-none focus-visible:tw-shadow-focus";

/* =============================================================
   1. Prose — long-form text wrapper.
   Relaxed line-height (~1.6), measure capped to ~68ch so lines
   stay scannable, 8pt paragraph rhythm, list + emphasis styles.
   Body sits at 15px / text-secondary so it reads as comfortable
   reading copy, not cramped UI text. Suitable for wrapping
   rendered markdown too (child <p>/<ul>/<strong> inherit styles).
   ============================================================= */

export function Prose({ children, className = "", as: Tag = "div" }) {
  return (
    <Tag
      className={cx(
        "tw-max-w-[68ch] tw-text-[15px] tw-leading-[1.6] tw-text-text-secondary",
        // paragraph rhythm: 8pt between blocks (skip the first)
        "[&_p]:tw-mt-2 [&_p:first-child]:tw-mt-0",
        "[&_p]:tw-leading-[1.6]",
        // lists — comfortable indent + marker colour + item spacing
        "[&_ul]:tw-mt-2 [&_ul]:tw-pl-5 [&_ul]:tw-list-disc",
        "[&_ol]:tw-mt-2 [&_ol]:tw-pl-5 [&_ol]:tw-list-decimal",
        "[&_li]:tw-mt-1 [&_li]:tw-pl-1 [&_li]:marker:tw-text-text-tertiary",
        // emphasis — bold keyphrases lift to primary text colour
        "[&_strong]:tw-text-text-primary [&_strong]:tw-font-semibold",
        "[&_em]:tw-italic",
        // inline accent links keep the cobalt accent + focus ring
        "[&_a]:tw-text-accent [&_a]:tw-underline [&_a]:tw-decoration-from-font hover:[&_a]:tw-text-accent-hover",
        className
      )}
    >
      {children}
    </Tag>
  );
}

/* =============================================================
   2. LeadStatement — the BLUF (bottom line up front).
   Large (18–22px), medium-weight, primary text, with an accent
   bar on the left. ALWAYS visible — never collapses. This is the
   one-glance conclusion of a block; the full reasoning lives below.
   ============================================================= */

export function LeadStatement({ children, icon = null, className = "" }) {
  return (
    <p
      className={cx(
        "tw-flex tw-gap-3 tw-items-start tw-m-0",
        "tw-border-l-2 tw-border-accent tw-pl-3",
        "tw-text-[19px] tw-leading-[1.45] tw-font-medium tw-text-text-primary",
        className
      )}
    >
      {icon && (
        <span aria-hidden="true" className="tw-shrink-0 tw-text-accent tw-mt-0.5">
          {icon}
        </span>
      )}
      <span>{children}</span>
    </p>
  );
}

/* =============================================================
   3. KeyTakeaway — callout for a key phrase or an HONEST caveat
   about uncertainty. Tone INFO is the neutral default — it frames
   «честно: данные противоречивы» as a TRUST feature, not an alarm.
   warning tone is reserved for genuine risk; positive for upside.
   Soft tone background + coloured left border + a tone icon.
   ALWAYS expanded — caveats are value, never hidden behind a click.
   ============================================================= */

const TAKEAWAY_TONES = {
  info: {
    wrap: "tw-bg-info-soft tw-border-info",
    icon: "tw-text-info",
    label: "tw-text-info",
    glyph: "⚖",
    title: "Честно",
  },
  positive: {
    wrap: "tw-bg-success-soft tw-border-success",
    icon: "tw-text-success",
    label: "tw-text-success",
    glyph: "▲",
    title: "Сильная сторона",
  },
  caution: {
    wrap: "tw-bg-warning-soft tw-border-warning",
    icon: "tw-text-warning",
    label: "tw-text-warning",
    glyph: "⚠",
    title: "Риск",
  },
};

export function KeyTakeaway({ tone = "info", title, icon, children, className = "" }) {
  const t = TAKEAWAY_TONES[tone] || TAKEAWAY_TONES.info;
  const heading = title || t.title;
  return (
    <div
      className={cx(
        "tw-flex tw-gap-3 tw-items-start tw-rounded-md tw-border-l-2 tw-p-3",
        t.wrap,
        className
      )}
    >
      <span aria-hidden="true" className={cx("tw-shrink-0 tw-text-[16px] tw-leading-[1.4]", t.icon)}>
        {icon || t.glyph}
      </span>
      <div className="tw-min-w-0">
        {heading && (
          <div
            className={cx("tw-text-[12px] tw-font-semibold tw-uppercase tw-mb-0.5", t.label)}
            style={{ letterSpacing: "0.06em" }}
          >
            {heading}
          </div>
        )}
        <div className="tw-text-[14px] tw-leading-[1.55] tw-text-text-primary">{children}</div>
      </div>
    </div>
  );
}

/* =============================================================
   4. Disclosure — collapsible section built on native
   <details>/<summary> so it is keyboard-operable and announced by
   screen readers for free. ONLY second-order detail goes here
   (extended reasoning, methodology, long lists) — never the lead
   or the honest caveat. Smooth open via CSS grid-rows transition,
   gated by prefers-reduced-motion. Accessible rotating chevron.
   ============================================================= */

export function Disclosure({ summary, children, defaultOpen = false, className = "" }) {
  const reduced = usePrefersReducedMotion();
  const id = useId();
  return (
    <details
      open={defaultOpen}
      className={cx("tw-group tw-border tw-border-border-subtle tw-rounded-md tw-bg-bg-elevated", className)}
    >
      <summary
        className={cx(
          "tw-flex tw-items-center tw-gap-2 tw-cursor-pointer tw-select-none tw-list-none",
          "tw-px-3 tw-py-2 tw-rounded-md tw-text-[14px] tw-font-medium tw-text-text-primary",
          "hover:tw-bg-bg-hover tw-transition-colors tw-duration-150",
          "[&::-webkit-details-marker]:tw-hidden",
          FOCUS
        )}
        aria-controls={id}
      >
        <svg
          width="12"
          height="12"
          viewBox="0 0 12 12"
          aria-hidden="true"
          className={cx(
            "tw-shrink-0 tw-text-text-tertiary group-open:tw-rotate-90",
            !reduced && "tw-transition-transform tw-duration-200"
          )}
        >
          <path d="M4 2l4 4-4 4" stroke="currentColor" strokeWidth="1.5" fill="none" strokeLinecap="round" strokeLinejoin="round" />
        </svg>
        <span className="tw-flex-1">{summary}</span>
        <span className="tw-text-[12px] tw-text-text-tertiary tw-font-normal group-open:tw-hidden">подробнее</span>
      </summary>
      {/* grid-rows 0fr → 1fr gives a smooth height reveal without JS measuring */}
      <div
        id={id}
        className={cx(
          "tw-grid group-open:tw-grid-rows-[1fr] tw-grid-rows-[0fr]",
          !reduced && "tw-transition-[grid-template-rows] tw-duration-200"
        )}
      >
        <div className="tw-overflow-hidden">
          <div className="tw-px-3 tw-pb-3 tw-pt-1 tw-border-t tw-border-border-subtle">{children}</div>
        </div>
      </div>
    </details>
  );
}

/* =============================================================
   5. StatInline — a number pulled out of prose into a mini-visual:
   large tabular figure + unit + caption, optional semantic tone.
   Use it to DUPLICATE a figure buried in text so the eye catches
   it. Numbers stay product-formatted (tabular-nums; pass already
   formatted strings, or compose with format.js at the call site).
   ============================================================= */

const STAT_TONES = {
  neutral: "tw-text-text-primary",
  accent: "tw-text-accent",
  positive: "tw-text-success",
  negative: "tw-text-danger",
  info: "tw-text-info",
};

export function StatInline({ value, unit, label, tone = "neutral", className = "" }) {
  const toneCls = STAT_TONES[tone] || STAT_TONES.neutral;
  return (
    <div
      className={cx(
        "tw-inline-flex tw-flex-col tw-gap-0.5 tw-rounded-md tw-border tw-border-border-subtle tw-bg-bg-base tw-px-3 tw-py-2",
        className
      )}
    >
      <div className="tw-flex tw-items-baseline tw-gap-1">
        <span className={cx("tw-font-display tw-font-light tw-tabular-nums", toneCls)} style={{ fontSize: "24px", lineHeight: 1 }}>
          {value}
        </span>
        {unit && <span className="tw-text-[13px] tw-text-text-tertiary">{unit}</span>}
      </div>
      {label && (
        <div className="tw-text-[11px] tw-font-medium tw-uppercase tw-text-text-tertiary" style={{ letterSpacing: "0.05em" }}>
          {label}
        </div>
      )}
    </div>
  );
}

/* =============================================================
   (Optional) PullQuote — lift a key conclusion phrase out of the
   prose into a large quote-like emphasis. Always visible; used
   sparingly inside long copy to anchor the eye on the thesis.
   ============================================================= */

export function PullQuote({ children, className = "" }) {
  return (
    <blockquote
      className={cx(
        "tw-m-0 tw-border-l-2 tw-border-border-strong tw-pl-4 tw-py-1",
        "tw-text-[16px] tw-leading-[1.5] tw-italic tw-text-text-primary",
        className
      )}
    >
      {children}
    </blockquote>
  );
}

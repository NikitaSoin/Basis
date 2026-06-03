// =============================================================
// BASIS DESIGN PRIMITIVES — Phase 2 base library
// Pure JS (no TS). Styled exclusively via `tw-` Tailwind utilities
// that map onto the design tokens in src/styles/tokens.css.
// Every interactive element carries a focus-ring; deltas pair a
// semantic colour with a ▲/▼ glyph; motion respects
// prefers-reduced-motion. No hard-coded hex.
// =============================================================
import React, { useEffect, useId, useRef, useState } from "react";
import { formatNumber, formatPercent } from "./format";

/* ---------- shared helpers ---------- */

const cx = (...parts) => parts.filter(Boolean).join(" ");

// Respect the user's OS motion preference once, reactively.
export function usePrefersReducedMotion() {
  // Initialise SYNCHRONOUSLY so `reduced` is correct on the very first render
  // (no 1-frame flash of motion before an effect flips it). Falls back to false
  // when matchMedia is unavailable (SSR/old browsers).
  const [reduced, setReduced] = useState(
    () =>
      typeof window !== "undefined" &&
      !!window.matchMedia &&
      window.matchMedia("(prefers-reduced-motion: reduce)").matches
  );
  useEffect(() => {
    if (typeof window === "undefined" || !window.matchMedia) return;
    const mq = window.matchMedia("(prefers-reduced-motion: reduce)");
    const apply = () => setReduced(mq.matches);
    apply();
    mq.addEventListener ? mq.addEventListener("change", apply) : mq.addListener(apply);
    return () =>
      mq.removeEventListener ? mq.removeEventListener("change", apply) : mq.removeListener(apply);
  }, []);
  return reduced;
}

// Universal focus ring used on every interactive primitive.
const FOCUS = "focus-visible:tw-outline-none focus-visible:tw-shadow-focus";

/* =============================================================
   1. Button
   ============================================================= */

const BTN_SIZES = {
  sm: "tw-text-[13px] tw-px-3 tw-py-1.5 tw-gap-1.5 tw-min-h-[32px]",
  md: "tw-text-[14px] tw-px-4 tw-py-2 tw-gap-2 tw-min-h-[40px]",
  lg: "tw-text-[15px] tw-px-5 tw-py-3 tw-gap-2 tw-min-h-[48px]",
};

const BTN_VARIANTS = {
  primary:
    "tw-bg-accent tw-text-on-accent tw-border tw-border-transparent hover:tw-bg-accent-hover",
  secondary:
    "tw-bg-bg-elevated tw-text-text-primary tw-border tw-border-border-strong hover:tw-bg-accent-soft",
  ghost:
    "tw-bg-transparent tw-text-text-secondary tw-border tw-border-transparent hover:tw-bg-accent-soft hover:tw-text-text-primary",
  danger:
    "tw-bg-danger tw-text-on-danger tw-border tw-border-transparent hover:tw-opacity-90",
};

function Spinner({ className }) {
  return (
    <svg
      className={cx("tw-animate-spin", className)}
      width="16"
      height="16"
      viewBox="0 0 24 24"
      fill="none"
      aria-hidden="true"
    >
      <circle cx="12" cy="12" r="9" stroke="currentColor" strokeWidth="3" opacity="0.25" />
      <path d="M21 12a9 9 0 0 0-9-9" stroke="currentColor" strokeWidth="3" strokeLinecap="round" />
    </svg>
  );
}

export function Button({
  children,
  variant = "primary",
  size = "md",
  iconLeft = null,
  iconRight = null,
  loading = false,
  disabled = false,
  type = "button",
  className = "",
  ...rest
}) {
  const isDisabled = disabled || loading;
  return (
    <button
      type={type}
      disabled={isDisabled}
      aria-busy={loading || undefined}
      className={cx(
        "tw-inline-flex tw-items-center tw-justify-center tw-font-sans tw-font-medium tw-rounded-sm",
        "tw-transition-colors tw-duration-150 tw-select-none",
        BTN_SIZES[size],
        BTN_VARIANTS[variant],
        FOCUS,
        isDisabled && "tw-opacity-50 tw-cursor-not-allowed tw-pointer-events-none",
        !isDisabled && "active:tw-translate-y-px",
        className
      )}
      {...rest}
    >
      {loading && <Spinner />}
      {!loading && iconLeft && <span className="tw-inline-flex tw-shrink-0">{iconLeft}</span>}
      {children && <span>{children}</span>}
      {!loading && iconRight && <span className="tw-inline-flex tw-shrink-0">{iconRight}</span>}
    </button>
  );
}

/* =============================================================
   2. IconButton — square, min 32×32 touch zone
   ============================================================= */

const ICON_SIZES = {
  sm: "tw-w-8 tw-h-8",
  md: "tw-w-10 tw-h-10",
  lg: "tw-w-12 tw-h-12",
};

export function IconButton({
  children,
  variant = "ghost",
  size = "md",
  disabled = false,
  className = "",
  "aria-label": ariaLabel,
  ...rest
}) {
  return (
    <button
      type="button"
      aria-label={ariaLabel}
      disabled={disabled}
      className={cx(
        "tw-inline-flex tw-items-center tw-justify-center tw-rounded-sm",
        "tw-transition-colors tw-duration-150",
        ICON_SIZES[size],
        BTN_VARIANTS[variant],
        FOCUS,
        disabled && "tw-opacity-50 tw-cursor-not-allowed tw-pointer-events-none",
        className
      )}
      {...rest}
    >
      {children}
    </button>
  );
}

/* =============================================================
   3. Card — elevated surface.
   Light: thin border + soft shadow (per constitution).
   Dark:  layered surface + exactly ONE 1px border. The dark
   --shadow-sm token resolves to a 1px border-as-shadow, which would
   double the real border, so we drop the shadow in dark
   (dark:tw-shadow-none) and keep the single tw-border instead.
   ============================================================= */

export function Card({ children, header = null, footer = null, className = "", ...rest }) {
  return (
    <div
      className={cx(
        "tw-bg-bg-elevated tw-border tw-border-border-strong tw-rounded-md tw-shadow-sm dark:tw-shadow-none",
        "tw-overflow-hidden",
        className
      )}
      {...rest}
    >
      {header && (
        <div className="tw-px-4 tw-py-3 tw-border-b tw-border-border-subtle tw-text-text-primary tw-font-medium">
          {header}
        </div>
      )}
      <div className="tw-p-4">{children}</div>
      {footer && (
        <div className="tw-px-4 tw-py-3 tw-border-t tw-border-border-subtle tw-text-text-secondary tw-text-[13px]">
          {footer}
        </div>
      )}
    </div>
  );
}

/* =============================================================
   4. Badge — status pill, soft bg + coloured text
   ============================================================= */

const BADGE_TONES = {
  neutral: "tw-bg-bg-base tw-text-text-secondary tw-border tw-border-border-subtle",
  accent: "tw-bg-accent-soft tw-text-accent",
  success: "tw-bg-success-soft tw-text-success",
  danger: "tw-bg-danger-soft tw-text-danger",
  warning: "tw-bg-warning-soft tw-text-warning",
  info: "tw-bg-info-soft tw-text-info",
};

export function Badge({ children, tone = "neutral", className = "" }) {
  return (
    <span
      className={cx(
        "tw-inline-flex tw-items-center tw-gap-1 tw-rounded-pill tw-px-2 tw-py-0.5",
        "tw-text-[12px] tw-font-medium tw-leading-[18px] tw-whitespace-nowrap",
        BADGE_TONES[tone],
        className
      )}
    >
      {children}
    </span>
  );
}

/* =============================================================
   5. Chip — interactive selectable / removable
   ============================================================= */

export function Chip({
  children,
  selected = false,
  onClick,
  onRemove,
  disabled = false,
  className = "",
}) {
  return (
    <span
      className={cx(
        "tw-inline-flex tw-items-center tw-gap-1.5 tw-rounded-pill tw-px-3 tw-py-1",
        "tw-text-[13px] tw-font-medium tw-transition-colors tw-duration-150 tw-min-h-[32px]",
        selected
          ? "tw-bg-accent tw-text-on-accent tw-border tw-border-transparent"
          : "tw-bg-bg-elevated tw-text-text-secondary tw-border tw-border-border-strong hover:tw-bg-accent-soft hover:tw-text-text-primary",
        disabled && "tw-opacity-50 tw-pointer-events-none"
      )}
    >
      <button
        type="button"
        onClick={onClick}
        disabled={disabled}
        aria-pressed={selected}
        className={cx("tw-bg-transparent tw-border-0 tw-p-0 tw-cursor-pointer tw-text-inherit", FOCUS, className)}
      >
        {children}
      </button>
      {onRemove && (
        <button
          type="button"
          onClick={onRemove}
          aria-label="Удалить"
          disabled={disabled}
          className={cx(
            "tw-inline-flex tw-items-center tw-justify-center tw-w-4 tw-h-4 tw-rounded-pill",
            "tw-text-current tw-opacity-70 hover:tw-opacity-100 tw-cursor-pointer tw-bg-transparent tw-border-0",
            FOCUS
          )}
        >
          <svg width="10" height="10" viewBox="0 0 10 10" aria-hidden="true">
            <path d="M1 1l8 8M9 1l-8 8" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" />
          </svg>
        </button>
      )}
    </span>
  );
}

/* =============================================================
   6. Tooltip — hover/focus, overlay surface + shadow, 120ms
   ============================================================= */

export function Tooltip({ label, children, side = "top" }) {
  const [open, setOpen] = useState(false);
  const reduced = usePrefersReducedMotion();
  const tipId = useId();
  const sidePos = {
    top: "tw-bottom-full tw-left-1/2 -tw-translate-x-1/2 tw-mb-1.5",
    bottom: "tw-top-full tw-left-1/2 -tw-translate-x-1/2 tw-mt-1.5",
    left: "tw-right-full tw-top-1/2 -tw-translate-y-1/2 tw-mr-1.5",
    right: "tw-left-full tw-top-1/2 -tw-translate-y-1/2 tw-ml-1.5",
  };
  return (
    <span
      className="tw-relative tw-inline-flex"
      aria-describedby={tipId}
      onMouseEnter={() => setOpen(true)}
      onMouseLeave={() => setOpen(false)}
      onFocus={() => setOpen(true)}
      onBlur={() => setOpen(false)}
    >
      {children}
      {open && (
        <span
          role="tooltip"
          id={tipId}
          className={cx(
            "tw-absolute tw-z-50 tw-px-2 tw-py-1 tw-rounded-sm tw-whitespace-nowrap tw-pointer-events-none",
            "tw-bg-bg-overlay tw-text-text-primary tw-border tw-border-border-subtle tw-shadow-lg",
            "tw-text-[12px] tw-leading-[18px]",
            !reduced && "tw-transition-opacity tw-duration-150",
            sidePos[side]
          )}
        >
          {label}
        </span>
      )}
    </span>
  );
}

/* =============================================================
   7. Input — visible label, focus-ring, error/disabled
   ============================================================= */

export function Input({
  label,
  error = null,
  disabled = false,
  id,
  className = "",
  ...rest
}) {
  const auto = useId();
  const inputId = id || auto;
  const errId = `${inputId}-err`;
  return (
    <div className={cx("tw-flex tw-flex-col tw-gap-1.5", className)}>
      {label && (
        <label htmlFor={inputId} className="tw-text-[13px] tw-font-medium tw-text-text-secondary">
          {label}
        </label>
      )}
      <input
        id={inputId}
        disabled={disabled}
        aria-invalid={!!error}
        aria-describedby={error ? errId : undefined}
        className={cx(
          "tw-w-full tw-px-3 tw-py-2 tw-rounded-xs tw-text-[14px] tw-bg-bg-elevated tw-text-text-primary",
          "tw-border tw-transition-colors tw-duration-150 placeholder:tw-text-text-tertiary",
          error ? "tw-border-danger" : "tw-border-border-strong",
          FOCUS,
          disabled && "tw-opacity-50 tw-cursor-not-allowed tw-bg-bg-base"
        )}
        {...rest}
      />
      {error && (
        <span id={errId} className="tw-text-[12px] tw-text-danger">
          {error}
        </span>
      )}
    </div>
  );
}

/* =============================================================
   8. Select — native <select> styled to tokens
   ============================================================= */

export function Select({
  label,
  options = [],
  disabled = false,
  id,
  className = "",
  ...rest
}) {
  const auto = useId();
  const selectId = id || auto;
  return (
    <div className={cx("tw-flex tw-flex-col tw-gap-1.5", className)}>
      {label && (
        <label htmlFor={selectId} className="tw-text-[13px] tw-font-medium tw-text-text-secondary">
          {label}
        </label>
      )}
      <div className="tw-relative">
        <select
          id={selectId}
          disabled={disabled}
          className={cx(
            "tw-w-full tw-appearance-none tw-px-3 tw-py-2 tw-pr-9 tw-rounded-xs tw-text-[14px]",
            "tw-bg-bg-elevated tw-text-text-primary tw-border tw-border-border-strong",
            "tw-transition-colors tw-duration-150",
            FOCUS,
            disabled && "tw-opacity-50 tw-cursor-not-allowed tw-bg-bg-base"
          )}
          {...rest}
        >
          {options.map((o) => (
            <option key={o.value} value={o.value}>
              {o.label}
            </option>
          ))}
        </select>
        <svg
          className="tw-absolute tw-right-3 tw-top-1/2 -tw-translate-y-1/2 tw-pointer-events-none tw-text-text-tertiary"
          width="12"
          height="12"
          viewBox="0 0 12 12"
          aria-hidden="true"
        >
          <path d="M2 4l4 4 4-4" stroke="currentColor" strokeWidth="1.5" fill="none" strokeLinecap="round" />
        </svg>
      </div>
    </div>
  );
}

/* =============================================================
   9. Modal — scrim + overlay panel, Esc close, close button
   ============================================================= */

const FOCUSABLE_SELECTOR =
  'a[href], button:not([disabled]), textarea:not([disabled]), input:not([disabled]), select:not([disabled]), [tabindex]:not([tabindex="-1"])';

export function Modal({ open, onClose, title, children, footer = null }) {
  const reduced = usePrefersReducedMotion();
  const panelRef = useRef(null);
  const triggerRef = useRef(null);

  // Esc-close + Tab/Shift+Tab focus-trap inside the dialog.
  useEffect(() => {
    if (!open) return;
    const onKey = (e) => {
      if (e.key === "Escape") {
        onClose && onClose();
        return;
      }
      if (e.key !== "Tab" || !panelRef.current) return;
      const focusable = Array.from(
        panelRef.current.querySelectorAll(FOCUSABLE_SELECTOR)
      ).filter((el) => el.offsetParent !== null || el === panelRef.current);
      const first = focusable[0] || panelRef.current;
      const last = focusable[focusable.length - 1] || panelRef.current;
      const active = document.activeElement;
      if (e.shiftKey) {
        if (active === first || active === panelRef.current) {
          e.preventDefault();
          last.focus();
        }
      } else if (active === last) {
        e.preventDefault();
        first.focus();
      }
    };
    document.addEventListener("keydown", onKey);
    return () => document.removeEventListener("keydown", onKey);
  }, [open, onClose]);

  // On open: remember the trigger, focus the first focusable (or panel).
  // On close: return focus to the element that opened the modal.
  useEffect(() => {
    if (open) {
      triggerRef.current = document.activeElement;
      const node = panelRef.current;
      if (node) {
        const focusable = node.querySelectorAll(FOCUSABLE_SELECTOR);
        (focusable[0] || node).focus();
      }
      return;
    }
    if (triggerRef.current && typeof triggerRef.current.focus === "function") {
      triggerRef.current.focus();
      triggerRef.current = null;
    }
  }, [open]);

  if (!open) return null;

  return (
    <div
      className="tw-fixed tw-inset-0 tw-z-50 tw-flex tw-items-center tw-justify-center tw-p-4"
      style={{ background: "var(--bg-overlay)" }}
      onMouseDown={(e) => {
        if (e.target === e.currentTarget) onClose && onClose();
      }}
    >
      <div
        ref={panelRef}
        role="dialog"
        aria-modal="true"
        aria-label={title}
        tabIndex={-1}
        className={cx(
          "tw-w-full tw-max-w-md tw-bg-bg-overlay tw-rounded-lg tw-shadow-xl tw-border tw-border-border-subtle",
          "tw-outline-none",
          !reduced && "tw-transition tw-duration-300"
        )}
      >
        <div className="tw-flex tw-items-center tw-justify-between tw-px-5 tw-py-4 tw-border-b tw-border-border-subtle">
          <h3 className="tw-text-[18px] tw-font-semibold tw-text-text-primary tw-m-0">{title}</h3>
          <IconButton aria-label="Закрыть" size="sm" onClick={onClose}>
            <svg width="16" height="16" viewBox="0 0 16 16" aria-hidden="true">
              <path d="M3 3l10 10M13 3L3 13" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" />
            </svg>
          </IconButton>
        </div>
        <div className="tw-px-5 tw-py-4 tw-text-text-secondary tw-text-[14px]">{children}</div>
        {footer && (
          <div className="tw-flex tw-justify-end tw-gap-2 tw-px-5 tw-py-4 tw-border-t tw-border-border-subtle">
            {footer}
          </div>
        )}
      </div>
    </div>
  );
}

/* =============================================================
   10. Tabs — ARIA tablist, active underline accent
   ============================================================= */

export function Tabs({ tabs = [], value, onChange }) {
  const baseId = useId();
  return (
    <div>
      <div role="tablist" aria-label="Разделы" className="tw-flex tw-gap-1 tw-border-b tw-border-border-subtle">
        {tabs.map((t) => {
          const active = t.value === value;
          return (
            <button
              key={t.value}
              role="tab"
              id={`${baseId}-tab-${t.value}`}
              aria-selected={active}
              aria-controls={`${baseId}-panel-${t.value}`}
              tabIndex={active ? 0 : -1}
              onClick={() => onChange && onChange(t.value)}
              className={cx(
                "tw-px-4 tw-py-2 tw-text-[14px] tw-font-medium tw-bg-transparent tw-border-0 tw-cursor-pointer",
                "tw--mb-px tw-border-b-2 tw-transition-colors tw-duration-150",
                active
                  ? "tw-text-accent tw-border-accent"
                  : "tw-text-text-secondary tw-border-transparent hover:tw-text-text-primary",
                FOCUS
              )}
            >
              {t.label}
            </button>
          );
        })}
      </div>
      {tabs.map((t) => (
        <div
          key={t.value}
          role="tabpanel"
          id={`${baseId}-panel-${t.value}`}
          aria-labelledby={`${baseId}-tab-${t.value}`}
          hidden={t.value !== value}
          className="tw-pt-4 tw-text-text-secondary tw-text-[14px]"
        >
          {t.content}
        </div>
      ))}
    </div>
  );
}

/* =============================================================
   11. Table — financial style, numbers right, mono tabular,
   signed deltas with ▲/▼ + semantic colour, hover row
   ============================================================= */

// Render a signed delta with glyph + semantic colour.
// `suffix` selects the unit: "%" → formatPercent, otherwise raw formatNumber.
export function Delta({ value, suffix = "%", decimals = 1, className = "" }) {
  if (value === null || value === undefined) return <span className="tw-text-text-tertiary">—</span>;
  const up = value > 0;
  const flat = value === 0;
  const glyph = flat ? "▬" : up ? "▲" : "▼";
  const tone = flat ? "tw-text-text-tertiary" : up ? "tw-text-success" : "tw-text-danger";
  const abs = Math.abs(value);
  const body =
    suffix === "%"
      ? formatPercent(abs, { decimals })
      : `${formatNumber(abs, { decimals })}${suffix ? " " + suffix : ""}`;
  return (
    <span className={cx("tw-inline-flex tw-items-center tw-gap-1 tw-font-mono tw-tabular-nums", tone, className)}>
      <span aria-hidden="true">{glyph}</span>
      {body}
    </span>
  );
}

export function Table({ columns = [], rows = [], caption }) {
  return (
    <div className="tw-overflow-x-auto tw-border tw-border-border-strong tw-rounded-md">
      <table className="tw-w-full tw-border-collapse tw-text-[13px]">
        {caption && <caption className="tw-text-left tw-px-3 tw-py-2 tw-text-text-tertiary tw-text-[12px]">{caption}</caption>}
        <thead>
          <tr className="tw-border-b tw-border-border-strong">
            {columns.map((c, i) => (
              <th
                key={c.key}
                scope="col"
                style={{ letterSpacing: "0.06em" }}
                className={cx(
                  "tw-px-3 tw-py-2 tw-text-[12px] tw-font-medium tw-uppercase tw-text-text-tertiary",
                  i === 0 ? "tw-text-left" : "tw-text-right"
                )}
              >
                {c.label}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {rows.map((r, ri) => (
            <tr
              key={ri}
              className="tw-border-b tw-border-border-subtle last:tw-border-0 hover:tw-bg-bg-hover tw-transition-colors tw-duration-150"
            >
              {columns.map((c, i) => (
                <td
                  key={c.key}
                  className={cx(
                    "tw-px-3 tw-py-2",
                    i === 0
                      ? "tw-text-left tw-text-text-primary tw-font-medium"
                      : "tw-text-right tw-font-mono tw-tabular-nums tw-text-text-secondary"
                  )}
                >
                  {c.render ? c.render(r[c.key], r) : r[c.key]}
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

/* =============================================================
   12. KpiTile — caption / display value / delta / optional sparkline
   ============================================================= */

// Editorial sparkline: line + soft area fill under it + a dot on the
// last point, all in the delta's semantic colour. Padded vertically so
// the stroke and end dot are never clipped at the edges.
// `sign` drives the colour from the SAME source as the Delta glyph, so the
// line colour and the ▲/▼ arrow can never disagree. Falls back to first-vs-last
// only when no sign is supplied.
function Sparkline({ data = [], width = 96, height = 32, sign }) {
  const uid = useId();
  if (!data.length) return null;
  const min = Math.min(...data);
  const max = Math.max(...data);
  const span = max - min || 1;
  const pad = 3; // keep line/dot off the top & bottom edges
  const inner = height - pad * 2;
  const step = width / (data.length - 1 || 1);
  const coords = data.map((v, i) => [
    +(i * step).toFixed(2),
    +(pad + inner - ((v - min) / span) * inner).toFixed(2),
  ]);
  const line = coords.map(([x, y]) => `${x},${y}`).join(" ");
  const area = `0,${height} ${line} ${width},${height}`;
  const [lx, ly] = coords[coords.length - 1];
  const rising =
    sign === undefined || sign === null
      ? data[data.length - 1] >= data[0]
      : sign >= 0;
  const color = rising ? "var(--success)" : "var(--danger)";
  const gradId = `spark-fill-${uid}`;
  return (
    <svg width={width} height={height} viewBox={`0 0 ${width} ${height}`} aria-hidden="true" className="tw-block">
      <defs>
        <linearGradient id={gradId} x1="0" y1="0" x2="0" y2="1">
          <stop offset="0%" stopColor={color} stopOpacity="0.18" />
          <stop offset="100%" stopColor={color} stopOpacity="0" />
        </linearGradient>
      </defs>
      <polygon points={area} fill={`url(#${gradId})`} stroke="none" />
      <polyline
        points={line}
        fill="none"
        stroke={color}
        strokeWidth="1.5"
        strokeLinecap="round"
        strokeLinejoin="round"
      />
      <circle cx={lx} cy={ly} r="2" fill={color} />
    </svg>
  );
}

export function KpiTile({ caption, value, unit, delta, deltaSuffix = "%", spark }) {
  return (
    <div className="tw-flex tw-flex-col tw-gap-1.5 tw-bg-bg-elevated tw-border tw-border-border-strong tw-rounded-md tw-shadow-sm tw-p-4">
      <div
        className="tw-text-[12px] tw-font-medium tw-uppercase tw-text-text-tertiary"
        style={{ letterSpacing: "0.06em" }}
      >
        {caption}
      </div>
      <div className="tw-flex tw-items-baseline tw-gap-1">
        <span
          className="tw-font-display tw-font-light tw-text-text-primary tw-tabular-nums"
          style={{ fontSize: "32px", lineHeight: "1", letterSpacing: "-0.5px" }}
        >
          {value}
        </span>
        {unit && <span className="tw-text-[14px] tw-text-text-tertiary">{unit}</span>}
      </div>
      {delta !== undefined && (
        <div className="tw-text-[14px]">
          <Delta value={delta} suffix={deltaSuffix} />
        </div>
      )}
      {spark && (
        <div className="tw-mt-1">
          <Sparkline data={spark} sign={delta} />
        </div>
      )}
    </div>
  );
}

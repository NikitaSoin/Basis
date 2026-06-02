// =============================================================
// BASIS NUMBER FORMATTING — single source of truth for ru-RU.
// Financial product → numbers must be visually consistent everywhere.
//
// Rules (ru-RU editorial / typographic):
//   • decimal separator  = comma            "4 977,5"
//   • thousands grouping = NARROW NBSP U+202F (not a normal space)
//   • space before % and ₽ = NBSP U+00A0    "9,2 %"  "4 977,5 ₽"
//
// Intl.NumberFormat('ru-RU') groups with U+00A0 (or plain space in
// some engines), so we NORMALISE the grouping char to U+202F to
// guarantee a tight, consistent thousands separator across browsers.
// =============================================================

const NNBSP = " "; // narrow no-break space — thousands grouping
const NBSP = " "; // no-break space — before unit (% ₽ ×)

// Replace whatever grouping space Intl used (regular space or NBSP)
// with the narrow NBSP. We only touch spaces that sit between digits
// so a trailing unit space is never affected.
function normalizeGrouping(str) {
  return str.replace(/(\d)[\s  ](?=\d{3}\b)/g, `$1${NNBSP}`);
}

// Core: format a plain number with ru-RU grouping + comma decimals.
export function formatNumber(value, { decimals } = {}) {
  if (value === null || value === undefined || Number.isNaN(value)) return "—";
  const opts = {};
  if (decimals !== undefined) {
    opts.minimumFractionDigits = decimals;
    opts.maximumFractionDigits = decimals;
  }
  const out = new Intl.NumberFormat("ru-RU", opts).format(value);
  return normalizeGrouping(out);
}

// Money: trailing currency glyph with NBSP. Default ₽.
export function formatMoney(value, { currency = "₽", decimals } = {}) {
  if (value === null || value === undefined || Number.isNaN(value)) return "—";
  return `${formatNumber(value, { decimals })}${NBSP}${currency}`;
}

// Percent: value is already in percent units (9.2 → "9,2 %").
// sign:true adds a leading "+" for positive values (deltas).
export function formatPercent(value, { decimals = 1, sign = false } = {}) {
  if (value === null || value === undefined || Number.isNaN(value)) return "—";
  const body = formatNumber(value, { decimals });
  const lead = sign && value > 0 ? "+" : "";
  return `${lead}${body}${NBSP}%`;
}

// Multiple (P/E, EV/EBITDA…): "6,4×". withGlyph:false → "6,4".
export function formatMultiple(value, { decimals = 1, withGlyph = true } = {}) {
  if (value === null || value === undefined || Number.isNaN(value)) return "—";
  const body = formatNumber(value, { decimals });
  return withGlyph ? `${body}${NBSP}×` : body;
}

export const SPACES = { NNBSP, NBSP };

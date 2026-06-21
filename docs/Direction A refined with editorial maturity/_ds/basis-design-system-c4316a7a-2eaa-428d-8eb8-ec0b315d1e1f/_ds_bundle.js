/* @ds-bundle: {"format":3,"namespace":"BasisDesignSystem_c4316a","components":[{"name":"BondRiskScoreCard","sourcePath":"components/analytical/BondRiskScoreCard.jsx"},{"name":"ConfidenceBadge","sourcePath":"components/analytical/ConfidenceBadge.jsx"},{"name":"ExecutiveSummaryCard","sourcePath":"components/analytical/ExecutiveSummaryCard.jsx"},{"name":"FactEstimateJudgmentTag","sourcePath":"components/analytical/FactEstimateJudgmentTag.jsx"},{"name":"FactorImpactCard","sourcePath":"components/analytical/FactorImpactCard.jsx"},{"name":"KeyTakeaway","sourcePath":"components/analytical/KeyTakeaway.jsx"},{"name":"MacroTransmissionCard","sourcePath":"components/analytical/MacroTransmissionCard.jsx"},{"name":"MetricExplainer","sourcePath":"components/analytical/MetricExplainer.jsx"},{"name":"RISK_TYPES","sourcePath":"components/analytical/RiskBadge.jsx"},{"name":"RiskBadge","sourcePath":"components/analytical/RiskBadge.jsx"},{"name":"ScenarioTabs","sourcePath":"components/analytical/ScenarioTabs.jsx"},{"name":"SourceTag","sourcePath":"components/analytical/SourceTag.jsx"},{"name":"Badge","sourcePath":"components/core/Badge.jsx"},{"name":"Button","sourcePath":"components/core/Button.jsx"},{"name":"Chip","sourcePath":"components/core/Chip.jsx"},{"name":"IconButton","sourcePath":"components/core/IconButton.jsx"},{"name":"Input","sourcePath":"components/core/Input.jsx"},{"name":"Select","sourcePath":"components/core/Select.jsx"},{"name":"Toggle","sourcePath":"components/core/Toggle.jsx"},{"name":"Tooltip","sourcePath":"components/core/Tooltip.jsx"},{"name":"DataTable","sourcePath":"components/data/DataTable.jsx"},{"name":"Delta","sourcePath":"components/data/Delta.jsx"},{"name":"Callout","sourcePath":"components/feedback/Callout.jsx"},{"name":"Drawer","sourcePath":"components/feedback/Drawer.jsx"},{"name":"EmptyState","sourcePath":"components/feedback/EmptyState.jsx"},{"name":"Modal","sourcePath":"components/feedback/Modal.jsx"},{"name":"Skeleton","sourcePath":"components/feedback/Skeleton.jsx"},{"name":"Card","sourcePath":"components/layout/Card.jsx"},{"name":"MetricCard","sourcePath":"components/layout/MetricCard.jsx"}],"sourceHashes":{"components/analytical/BondRiskScoreCard.jsx":"c3bad9506828","components/analytical/ConfidenceBadge.jsx":"145ecabc71ac","components/analytical/ExecutiveSummaryCard.jsx":"17b59f7bedfc","components/analytical/FactEstimateJudgmentTag.jsx":"55d16fd8b2a9","components/analytical/FactorImpactCard.jsx":"3d632dd76300","components/analytical/KeyTakeaway.jsx":"7b35337694dc","components/analytical/MacroTransmissionCard.jsx":"3f4ff6cab90c","components/analytical/MetricExplainer.jsx":"11c0620647b1","components/analytical/RiskBadge.jsx":"e4a9d85d2125","components/analytical/ScenarioTabs.jsx":"58d42cd7eaa6","components/analytical/SourceTag.jsx":"16a34b4b416a","components/core/Badge.jsx":"b276f4ee204c","components/core/Button.jsx":"9207218d9f6f","components/core/Chip.jsx":"b9f2912d06d1","components/core/IconButton.jsx":"ff25a779bd04","components/core/Input.jsx":"4019dd36261b","components/core/Select.jsx":"c37b70068091","components/core/Toggle.jsx":"3cbcdb510589","components/core/Tooltip.jsx":"9d47683b1672","components/data/DataTable.jsx":"cb8d98baa016","components/data/Delta.jsx":"25b5a583ae5e","components/feedback/Callout.jsx":"e85ca2fa1eb2","components/feedback/Drawer.jsx":"278a0bffcb8f","components/feedback/EmptyState.jsx":"1156765f1eb3","components/feedback/Modal.jsx":"012fc3351325","components/feedback/Skeleton.jsx":"617e08f4b53a","components/layout/Card.jsx":"5f82f182a9b8","components/layout/MetricCard.jsx":"96b289f9c8c0","ui_kits/shell.js":"a3652fa29ce2"},"inlinedExternals":[],"unexposedExports":[]} */

(() => {

const __ds_ns = (window.BasisDesignSystem_c4316a = window.BasisDesignSystem_c4316a || {});

const __ds_scope = {};

(__ds_ns.__errors = __ds_ns.__errors || []);

// components/analytical/BondRiskScoreCard.jsx
try { (() => {
// Basis BondRiskScoreCard — answers "Is the yield adequate for the risk?"
// Traffic-light verdict + 1–5 risk score, spread vs OFZ, required spread,
// rating vs market-implied, expected loss PD×LGD. Faithful to the production
// bond-risk methodology (red/orange/amber/green verdict + inverted 1–5 score).
let _injected = false;
function injectCSS() {
  if (_injected || typeof document === "undefined") return;
  _injected = true;
  const css = `
.bss-bond{border:1px solid var(--border-strong);border-radius:var(--radius-md);background:var(--bg-elevated);box-shadow:var(--shadow-sm);overflow:hidden;}
.bss-bond__verdict{display:flex;gap:12px;align-items:flex-start;border-left:4px solid;padding:14px 16px;}
.bss-bond__verdict--red{background:var(--danger-soft);border-color:var(--danger);}
.bss-bond__verdict--orange{background:var(--warning-soft);border-color:var(--warning);}
.bss-bond__verdict--amber{background:var(--warning-soft);border-color:var(--warning);}
.bss-bond__verdict--green{background:var(--success-soft);border-color:var(--success);}
.bss-bond__verdict--gray{background:var(--bg-base);border-color:var(--border-strong);}
.bss-bond__light{font-size:22px;line-height:1.2;flex-shrink:0;}
.bss-bond__vlabel{font-size:11px;font-weight:var(--fw-semibold);text-transform:uppercase;letter-spacing:0.07em;margin-bottom:3px;}
.bss-bond__vlabel--red{color:var(--danger);} .bss-bond__vlabel--orange,.bss-bond__vlabel--amber{color:var(--warning);}
.bss-bond__vlabel--green{color:var(--success);} .bss-bond__vlabel--gray{color:var(--text-secondary);}
.bss-bond__vtext{font-size:15px;line-height:1.5;font-weight:var(--fw-medium);color:var(--text-primary);}
.bss-bond__metrics{display:grid;grid-template-columns:repeat(2,1fr);gap:1px;background:var(--border-subtle);border-top:1px solid var(--border-subtle);}
.bss-bond__m{background:var(--bg-elevated);padding:12px 16px;}
.bss-bond__m-label{font-size:10px;font-weight:var(--fw-semibold);text-transform:uppercase;letter-spacing:var(--ls-eyebrow);color:var(--text-tertiary);margin-bottom:5px;}
.bss-bond__m-val{font-family:var(--font-mono);font-size:16px;font-weight:var(--fw-medium);color:var(--text-primary);font-variant-numeric:tabular-nums;}
.bss-bond__m-sub{font-size:11px;color:var(--text-tertiary);margin-top:2px;}
.bss-bond__score{display:flex;align-items:center;gap:8px;padding:12px 16px;border-top:1px solid var(--border-subtle);}
.bss-bond__score-label{font-size:12px;color:var(--text-secondary);font-weight:var(--fw-medium);}
.bss-bond__dots{display:inline-flex;gap:4px;}
.bss-bond__dot{width:18px;height:6px;border-radius:3px;background:var(--border-strong);}
.bss-bond__dot.on{}
`;
  const el = document.createElement("style");
  el.setAttribute("data-bss", "bond");
  el.textContent = css;
  document.head.appendChild(el);
}
injectCSS();
const LIGHT = {
  red: {
    icon: "🔴",
    label: "Высокий риск"
  },
  orange: {
    icon: "🟠",
    label: "Повышенный риск"
  },
  amber: {
    icon: "🟡",
    label: "Умеренный риск"
  },
  green: {
    icon: "🟢",
    label: "Приемлемый риск"
  },
  gray: {
    icon: "⚪",
    label: "Нет вердикта"
  }
};
// Inverted score: 1–2 good (green), 3 amber, 4–5 bad (red).
function scoreColor(n) {
  return n <= 2 ? "var(--success)" : n === 3 ? "var(--warning)" : "var(--danger)";
}
function BondRiskScoreCard({
  light = "gray",
  verdict,
  score,
  spreadOfz,
  requiredSpread,
  rating,
  marketImplied,
  expectedLoss,
  className = ""
}) {
  injectCSS();
  const l = LIGHT[light] || LIGHT.gray;
  const n = parseInt(score, 10);
  return /*#__PURE__*/React.createElement("div", {
    className: ["bss-bond", className].filter(Boolean).join(" ")
  }, /*#__PURE__*/React.createElement("div", {
    className: `bss-bond__verdict bss-bond__verdict--${light}`
  }, /*#__PURE__*/React.createElement("span", {
    className: "bss-bond__light",
    "aria-hidden": "true"
  }, l.icon), /*#__PURE__*/React.createElement("div", {
    style: {
      minWidth: 0
    }
  }, /*#__PURE__*/React.createElement("div", {
    className: `bss-bond__vlabel bss-bond__vlabel--${light}`
  }, "\u0412\u0435\u0440\u0434\u0438\u043A\u0442 \xB7 ", l.label), /*#__PURE__*/React.createElement("div", {
    className: "bss-bond__vtext"
  }, verdict))), !Number.isNaN(n) && /*#__PURE__*/React.createElement("div", {
    className: "bss-bond__score"
  }, /*#__PURE__*/React.createElement("span", {
    className: "bss-bond__score-label"
  }, "Risk Score"), /*#__PURE__*/React.createElement("span", {
    className: "bss-bond__dots",
    "aria-label": `${n} из 5`
  }, [1, 2, 3, 4, 5].map(i => /*#__PURE__*/React.createElement("span", {
    key: i,
    className: ["bss-bond__dot", i <= n && "on"].filter(Boolean).join(" "),
    style: i <= n ? {
      background: scoreColor(n)
    } : undefined
  }))), /*#__PURE__*/React.createElement("span", {
    style: {
      fontFamily: "var(--font-mono)",
      fontSize: 13,
      fontWeight: 600,
      color: scoreColor(n)
    }
  }, n, "/5")), /*#__PURE__*/React.createElement("div", {
    className: "bss-bond__metrics"
  }, spreadOfz && /*#__PURE__*/React.createElement("div", {
    className: "bss-bond__m"
  }, /*#__PURE__*/React.createElement("div", {
    className: "bss-bond__m-label"
  }, "\u0421\u043F\u0440\u0435\u0434 \u043A \u041E\u0424\u0417"), /*#__PURE__*/React.createElement("div", {
    className: "bss-bond__m-val"
  }, spreadOfz)), requiredSpread && /*#__PURE__*/React.createElement("div", {
    className: "bss-bond__m"
  }, /*#__PURE__*/React.createElement("div", {
    className: "bss-bond__m-label"
  }, "\u0422\u0440\u0435\u0431\u0443\u0435\u043C\u044B\u0439 \u0441\u043F\u0440\u0435\u0434"), /*#__PURE__*/React.createElement("div", {
    className: "bss-bond__m-val"
  }, requiredSpread)), (rating || marketImplied) && /*#__PURE__*/React.createElement("div", {
    className: "bss-bond__m"
  }, /*#__PURE__*/React.createElement("div", {
    className: "bss-bond__m-label"
  }, "\u0420\u0435\u0439\u0442\u0438\u043D\u0433 vs \u0440\u044B\u043D\u043E\u043A"), /*#__PURE__*/React.createElement("div", {
    className: "bss-bond__m-val"
  }, rating || "—"), /*#__PURE__*/React.createElement("div", {
    className: "bss-bond__m-sub"
  }, "\u0440\u044B\u043D\u043E\u043A \u043F\u043E\u0434\u0440\u0430\u0437\u0443\u043C\u0435\u0432\u0430\u0435\u0442 ", marketImplied || "—")), expectedLoss && /*#__PURE__*/React.createElement("div", {
    className: "bss-bond__m"
  }, /*#__PURE__*/React.createElement("div", {
    className: "bss-bond__m-label"
  }, "\u041E\u0436\u0438\u0434. \u043F\u043E\u0442\u0435\u0440\u0438 (PD\xD7LGD)"), /*#__PURE__*/React.createElement("div", {
    className: "bss-bond__m-val"
  }, expectedLoss))));
}
Object.assign(__ds_scope, { BondRiskScoreCard });
})(); } catch (e) { __ds_ns.__errors.push({ path: "components/analytical/BondRiskScoreCard.jsx", error: String((e && e.message) || e) }); }

// components/analytical/ConfidenceBadge.jsx
try { (() => {
// Basis ConfidenceBadge — analyst confidence: low / medium / high.
// Three filled bars + a label. Quiet by default (it qualifies, doesn't shout).
let _injected = false;
function injectCSS() {
  if (_injected || typeof document === "undefined") return;
  _injected = true;
  const css = `
.bss-conf{display:inline-flex;align-items:center;gap:6px;font-family:var(--font-sans);font-size:11px;
  font-weight:var(--fw-medium);color:var(--text-secondary);text-transform:uppercase;letter-spacing:0.04em;}
.bss-conf__bars{display:inline-flex;gap:2px;align-items:flex-end;}
.bss-conf__bar{width:3px;border-radius:1px;background:var(--border-strong);}
.bss-conf__bar.on{background:var(--accent);}
`;
  const el = document.createElement("style");
  el.setAttribute("data-bss", "conf");
  el.textContent = css;
  document.head.appendChild(el);
}
injectCSS();
const LEVELS = {
  low: 1,
  medium: 2,
  high: 3
};
const LABELS = {
  low: "Низкая",
  medium: "Средняя",
  high: "Высокая"
};
function ConfidenceBadge({
  level = "medium",
  showLabel = true,
  label,
  className = ""
}) {
  injectCSS();
  const n = LEVELS[level] || 2;
  const heights = [6, 9, 12];
  return /*#__PURE__*/React.createElement("span", {
    className: ["bss-conf", className].filter(Boolean).join(" ")
  }, /*#__PURE__*/React.createElement("span", {
    className: "bss-conf__bars",
    "aria-hidden": "true"
  }, heights.map((h, i) => /*#__PURE__*/React.createElement("span", {
    key: i,
    className: ["bss-conf__bar", i < n && "on"].filter(Boolean).join(" "),
    style: {
      height: h
    }
  }))), showLabel && /*#__PURE__*/React.createElement("span", null, "\u0423\u0432\u0435\u0440\u0435\u043D\u043D\u043E\u0441\u0442\u044C: ", label || LABELS[level]));
}
Object.assign(__ds_scope, { ConfidenceBadge });
})(); } catch (e) { __ds_ns.__errors.push({ path: "components/analytical/ConfidenceBadge.jsx", error: String((e && e.message) || e) }); }

// components/analytical/FactEstimateJudgmentTag.jsx
try { (() => {
// Basis FactEstimateJudgmentTag — marks the epistemic status of a statement.
// THE backbone of Basis analysis. Fact (sourced) / Estimate (model) /
// Judgment (interpretation) / Scenario (conditional). Color carries meaning.
let _injected = false;
function injectCSS() {
  if (_injected || typeof document === "undefined") return;
  _injected = true;
  const css = `
.bss-fej{display:inline-flex;align-items:center;gap:4px;border-radius:var(--radius-xs);
  padding:1px 6px;font-family:var(--font-sans);font-size:10px;font-weight:var(--fw-semibold);
  text-transform:uppercase;letter-spacing:0.05em;border:1px solid;white-space:nowrap;vertical-align:middle;}
.bss-fej--fact{background:var(--fact-soft);color:var(--fact);border-color:var(--border-subtle);}
.bss-fej--estimate{background:var(--estimate-soft);color:var(--estimate);border-color:var(--estimate);}
.bss-fej--judgment{background:var(--judgment-soft);color:var(--judgment);border-color:var(--accent-border);}
.bss-fej--scenario{background:var(--scenario-soft);color:var(--scenario);border-color:var(--scenario);}
.bss-fej--lg{font-size:11px;padding:2px 8px;}
`;
  const el = document.createElement("style");
  el.setAttribute("data-bss", "fej");
  el.textContent = css;
  document.head.appendChild(el);
}
injectCSS();
const LABELS = {
  fact: "Факт",
  estimate: "Оценка",
  judgment: "Суждение",
  scenario: "Сценарий"
};
const LABELS_EN = {
  fact: "Fact",
  estimate: "Estimate",
  judgment: "Judgment",
  scenario: "Scenario"
};
function FactEstimateJudgmentTag({
  level = "fact",
  lang = "ru",
  size = "sm",
  children,
  className = ""
}) {
  injectCSS();
  const dict = lang === "en" ? LABELS_EN : LABELS;
  const text = children || dict[level] || dict.fact;
  return /*#__PURE__*/React.createElement("span", {
    className: ["bss-fej", `bss-fej--${level}`, size === "lg" && "bss-fej--lg", className].filter(Boolean).join(" ")
  }, text);
}
Object.assign(__ds_scope, { FactEstimateJudgmentTag });
})(); } catch (e) { __ds_ns.__errors.push({ path: "components/analytical/FactEstimateJudgmentTag.jsx", error: String((e && e.message) || e) }); }

// components/analytical/KeyTakeaway.jsx
try { (() => {
// Basis KeyTakeaway — a compact "bottom line" tile placed after a complex block.
// Accent left bar, eyebrow label, one-glance conclusion. Always visible.
let _injected = false;
function injectCSS() {
  if (_injected || typeof document === "undefined") return;
  _injected = true;
  const css = `
.bss-takeaway{border:1px solid var(--border-strong);border-left:3px solid var(--accent);border-radius:var(--radius-md);
  background:var(--bg-elevated);padding:14px 16px;box-shadow:var(--shadow-sm);}
.bss-takeaway__label{display:flex;align-items:center;gap:6px;font-family:var(--font-sans);font-size:11px;
  font-weight:var(--fw-semibold);text-transform:uppercase;letter-spacing:var(--ls-eyebrow);color:var(--accent);margin-bottom:6px;}
.bss-takeaway__body{font-family:var(--font-sans);font-size:16px;line-height:1.5;font-weight:var(--fw-medium);color:var(--text-primary);}
`;
  const el = document.createElement("style");
  el.setAttribute("data-bss", "takeaway");
  el.textContent = css;
  document.head.appendChild(el);
}
injectCSS();
function KeyTakeaway({
  label = "Вывод",
  children,
  className = ""
}) {
  injectCSS();
  return /*#__PURE__*/React.createElement("div", {
    className: ["bss-takeaway", className].filter(Boolean).join(" ")
  }, label && /*#__PURE__*/React.createElement("div", {
    className: "bss-takeaway__label"
  }, /*#__PURE__*/React.createElement("svg", {
    width: "12",
    height: "12",
    viewBox: "0 0 12 12",
    fill: "none",
    "aria-hidden": "true"
  }, /*#__PURE__*/React.createElement("path", {
    d: "M2 6.5l2.5 2.5L10 3",
    stroke: "currentColor",
    strokeWidth: "1.6",
    strokeLinecap: "round",
    strokeLinejoin: "round"
  })), label), /*#__PURE__*/React.createElement("div", {
    className: "bss-takeaway__body"
  }, children));
}
Object.assign(__ds_scope, { KeyTakeaway });
})(); } catch (e) { __ds_ns.__errors.push({ path: "components/analytical/KeyTakeaway.jsx", error: String((e && e.message) || e) }); }

// components/analytical/MacroTransmissionCard.jsx
try { (() => {
// Basis TransmissionCard — the analytical chain that makes Basis distinctive:
// macro/geo factor → channel → company impact → P&L/balance/cash-flow → conclusion.
// kind="macro" (default) or "geo". Each step is a tile; an arrow connects them.
let _injected = false;
function injectCSS() {
  if (_injected || typeof document === "undefined") return;
  _injected = true;
  const css = `
.bss-trans{border:1px solid var(--border-strong);border-radius:var(--radius-md);background:var(--bg-elevated);box-shadow:var(--shadow-sm);overflow:hidden;}
.bss-trans__head{display:flex;align-items:center;gap:8px;padding:12px 16px;border-bottom:1px solid var(--border-subtle);}
.bss-trans__kind{font-size:10px;font-weight:var(--fw-semibold);text-transform:uppercase;letter-spacing:var(--ls-eyebrow);padding:2px 8px;border-radius:var(--radius-xs);}
.bss-trans__kind--macro{background:var(--accent-soft);color:var(--accent);}
.bss-trans__kind--geo{background:var(--scenario-soft);color:var(--scenario);}
.bss-trans__title{font-family:var(--font-display);font-size:15px;font-weight:var(--fw-semibold);color:var(--text-primary);}
.bss-trans__chain{padding:16px;display:flex;flex-direction:column;gap:0;}
.bss-trans__step{display:flex;gap:12px;align-items:flex-start;}
.bss-trans__rail{display:flex;flex-direction:column;align-items:center;flex-shrink:0;width:24px;}
.bss-trans__node{width:24px;height:24px;border-radius:var(--radius-pill);display:flex;align-items:center;justify-content:center;
  font-family:var(--font-mono);font-size:11px;font-weight:600;background:var(--bg-base);border:1px solid var(--border-strong);color:var(--text-secondary);}
.bss-trans__node--last{background:var(--accent);color:var(--on-accent);border-color:transparent;}
.bss-trans__line{flex:1;width:2px;background:var(--border-subtle);min-height:14px;}
.bss-trans__content{flex:1;padding-bottom:14px;}
.bss-trans__step:last-child .bss-trans__content{padding-bottom:0;}
.bss-trans__step-label{font-size:10px;font-weight:var(--fw-semibold);text-transform:uppercase;letter-spacing:var(--ls-eyebrow);color:var(--text-tertiary);margin-bottom:2px;}
.bss-trans__step-text{font-size:14px;line-height:1.5;color:var(--text-primary);}
.bss-trans__step--conclusion .bss-trans__step-text{font-weight:var(--fw-medium);color:var(--accent);}
`;
  const el = document.createElement("style");
  el.setAttribute("data-bss", "trans");
  el.textContent = css;
  document.head.appendChild(el);
}
injectCSS();
const DEFAULT_LABELS = ["Фактор", "Канал передачи", "Влияние на бизнес", "P&L / баланс / FCF", "Инвест-вывод"];
function MacroTransmissionCard({
  kind = "macro",
  title,
  steps = [],
  stepLabels,
  className = ""
}) {
  injectCSS();
  const labels = stepLabels || DEFAULT_LABELS;
  const last = steps.length - 1;
  return /*#__PURE__*/React.createElement("div", {
    className: ["bss-trans", className].filter(Boolean).join(" ")
  }, /*#__PURE__*/React.createElement("div", {
    className: "bss-trans__head"
  }, /*#__PURE__*/React.createElement("span", {
    className: `bss-trans__kind bss-trans__kind--${kind}`
  }, kind === "geo" ? "Гео" : "Макро"), /*#__PURE__*/React.createElement("span", {
    className: "bss-trans__title"
  }, title)), /*#__PURE__*/React.createElement("div", {
    className: "bss-trans__chain"
  }, steps.map((step, i) => /*#__PURE__*/React.createElement("div", {
    key: i,
    className: ["bss-trans__step", i === last && "bss-trans__step--conclusion"].filter(Boolean).join(" ")
  }, /*#__PURE__*/React.createElement("div", {
    className: "bss-trans__rail"
  }, /*#__PURE__*/React.createElement("span", {
    className: ["bss-trans__node", i === last && "bss-trans__node--last"].filter(Boolean).join(" ")
  }, i + 1), i !== last && /*#__PURE__*/React.createElement("span", {
    className: "bss-trans__line"
  })), /*#__PURE__*/React.createElement("div", {
    className: "bss-trans__content"
  }, /*#__PURE__*/React.createElement("div", {
    className: "bss-trans__step-label"
  }, typeof step === "object" && step.label || labels[i] || ""), /*#__PURE__*/React.createElement("div", {
    className: "bss-trans__step-text"
  }, typeof step === "object" ? step.text : step))))));
}
Object.assign(__ds_scope, { MacroTransmissionCard });
})(); } catch (e) { __ds_ns.__errors.push({ path: "components/analytical/MacroTransmissionCard.jsx", error: String((e && e.message) || e) }); }

// components/analytical/MetricExplainer.jsx
try { (() => {
// Basis MetricExplainer — explains a metric to a private investor:
// what it is · your value vs benchmark · what to do with it · formula · takeaway.
// Progressive disclosure: the takeaway is always visible, the formula optional.
let _injected = false;
function injectCSS() {
  if (_injected || typeof document === "undefined") return;
  _injected = true;
  const css = `
.bss-mexp{border:1px solid var(--border-strong);border-radius:var(--radius-md);background:var(--bg-elevated);
  box-shadow:var(--shadow-sm);overflow:hidden;}
.bss-mexp__head{display:flex;align-items:flex-start;justify-content:space-between;gap:12px;padding:14px 16px;border-bottom:1px solid var(--border-subtle);}
.bss-mexp__name{font-family:var(--font-display);font-size:16px;font-weight:var(--fw-semibold);color:var(--text-primary);margin:0;}
.bss-mexp__what{font-size:13px;color:var(--text-secondary);line-height:1.5;margin-top:3px;}
.bss-mexp__value{text-align:right;flex-shrink:0;}
.bss-mexp__num{font-family:var(--font-display);font-weight:var(--fw-light);font-size:28px;line-height:1;color:var(--text-primary);
  font-variant-numeric:lining-nums tabular-nums;letter-spacing:var(--ls-display);}
.bss-mexp__bench{font-family:var(--font-mono);font-size:11px;color:var(--text-tertiary);margin-top:4px;font-variant-numeric:tabular-nums;}
.bss-mexp__body{padding:14px 16px;display:flex;flex-direction:column;gap:12px;}
.bss-mexp__row-label{font-size:11px;font-weight:var(--fw-semibold);text-transform:uppercase;letter-spacing:var(--ls-eyebrow);color:var(--text-tertiary);margin-bottom:3px;}
.bss-mexp__row-text{font-size:14px;color:var(--text-secondary);line-height:1.55;}
.bss-mexp__formula{font-family:var(--font-mono);font-size:13px;color:var(--text-primary);background:var(--bg-base);
  border:1px solid var(--border-subtle);border-radius:var(--radius-xs);padding:8px 10px;display:inline-block;}
.bss-mexp__take{display:flex;gap:8px;align-items:flex-start;border-left:2px solid var(--accent);background:var(--accent-soft);
  border-radius:var(--radius-sm);padding:10px 12px;}
.bss-mexp__take-text{font-size:14px;line-height:1.5;color:var(--text-primary);font-weight:var(--fw-medium);}
`;
  const el = document.createElement("style");
  el.setAttribute("data-bss", "mexp");
  el.textContent = css;
  document.head.appendChild(el);
}
injectCSS();
function MetricExplainer({
  name,
  value,
  unit,
  benchmark,
  what,
  yourValue,
  action,
  formula,
  takeaway,
  className = ""
}) {
  injectCSS();
  return /*#__PURE__*/React.createElement("div", {
    className: ["bss-mexp", className].filter(Boolean).join(" ")
  }, /*#__PURE__*/React.createElement("div", {
    className: "bss-mexp__head"
  }, /*#__PURE__*/React.createElement("div", {
    style: {
      minWidth: 0
    }
  }, /*#__PURE__*/React.createElement("h4", {
    className: "bss-mexp__name"
  }, name), what && /*#__PURE__*/React.createElement("div", {
    className: "bss-mexp__what"
  }, what)), value !== undefined && /*#__PURE__*/React.createElement("div", {
    className: "bss-mexp__value"
  }, /*#__PURE__*/React.createElement("div", {
    className: "bss-mexp__num"
  }, value, unit && /*#__PURE__*/React.createElement("span", {
    style: {
      fontSize: 14,
      color: "var(--text-tertiary)",
      marginLeft: 2
    }
  }, unit)), benchmark && /*#__PURE__*/React.createElement("div", {
    className: "bss-mexp__bench"
  }, "\u0431\u0435\u043D\u0447\u043C\u0430\u0440\u043A ", benchmark))), /*#__PURE__*/React.createElement("div", {
    className: "bss-mexp__body"
  }, yourValue && /*#__PURE__*/React.createElement("div", null, /*#__PURE__*/React.createElement("div", {
    className: "bss-mexp__row-label"
  }, "\u0412\u0430\u0448\u0435 \u0437\u043D\u0430\u0447\u0435\u043D\u0438\u0435 ", /*#__PURE__*/React.createElement(__ds_scope.FactEstimateJudgmentTag, {
    level: "estimate"
  })), /*#__PURE__*/React.createElement("div", {
    className: "bss-mexp__row-text"
  }, yourValue)), action && /*#__PURE__*/React.createElement("div", null, /*#__PURE__*/React.createElement("div", {
    className: "bss-mexp__row-label"
  }, "\u0427\u0442\u043E \u0441 \u044D\u0442\u0438\u043C \u0434\u0435\u043B\u0430\u0442\u044C"), /*#__PURE__*/React.createElement("div", {
    className: "bss-mexp__row-text"
  }, action)), formula && /*#__PURE__*/React.createElement("div", null, /*#__PURE__*/React.createElement("div", {
    className: "bss-mexp__row-label"
  }, "\u0424\u043E\u0440\u043C\u0443\u043B\u0430"), /*#__PURE__*/React.createElement("code", {
    className: "bss-mexp__formula"
  }, formula)), takeaway && /*#__PURE__*/React.createElement("div", {
    className: "bss-mexp__take"
  }, /*#__PURE__*/React.createElement("span", {
    "aria-hidden": "true",
    style: {
      color: "var(--accent)",
      flexShrink: 0
    }
  }, "\u2192"), /*#__PURE__*/React.createElement("div", {
    className: "bss-mexp__take-text"
  }, takeaway))));
}
Object.assign(__ds_scope, { MetricExplainer });
})(); } catch (e) { __ds_ns.__errors.push({ path: "components/analytical/MetricExplainer.jsx", error: String((e && e.message) || e) }); }

// components/analytical/RiskBadge.jsx
try { (() => {
// Basis RiskBadge — a typed risk pill. Risk TYPE drives the label; severity
// (low/medium/high) drives the color (neutral → warning → danger). Always warm,
// never alarmist by default — high severity only where it is genuinely high.
let _injected = false;
function injectCSS() {
  if (_injected || typeof document === "undefined") return;
  _injected = true;
  const css = `
.bss-risk{display:inline-flex;align-items:center;gap:5px;border-radius:var(--radius-pill);padding:2px 9px;
  font-family:var(--font-sans);font-size:12px;font-weight:var(--fw-medium);white-space:nowrap;border:1px solid;}
.bss-risk__dot{width:6px;height:6px;border-radius:var(--radius-pill);flex-shrink:0;background:currentColor;}
.bss-risk--low{background:var(--bg-base);color:var(--text-secondary);border-color:var(--border-subtle);}
.bss-risk--medium{background:var(--warning-soft);color:var(--warning);border-color:transparent;}
.bss-risk--high{background:var(--danger-soft);color:var(--danger);border-color:transparent;}
`;
  const el = document.createElement("style");
  el.setAttribute("data-bss", "risk");
  el.textContent = css;
  document.head.appendChild(el);
}
injectCSS();

// Canonical Basis risk types (ru labels).
const RISK_TYPES = {
  macro: "Макрориск",
  fx: "Валютный риск",
  sanctions: "Санкционный риск",
  leverage: "Долговая нагрузка",
  governance: "Риск управления",
  valuation: "Риск оценки",
  liquidity: "Риск ликвидности",
  dividend: "Дивидендный риск",
  tax: "Налоговый риск",
  commodity: "Сырьевой риск",
  market: "Рыночный риск"
};
function RiskBadge({
  type = "market",
  severity = "medium",
  label,
  className = ""
}) {
  injectCSS();
  const text = label || RISK_TYPES[type] || RISK_TYPES.market;
  return /*#__PURE__*/React.createElement("span", {
    className: ["bss-risk", `bss-risk--${severity}`, className].filter(Boolean).join(" ")
  }, /*#__PURE__*/React.createElement("span", {
    className: "bss-risk__dot",
    "aria-hidden": "true"
  }), text);
}
Object.assign(__ds_scope, { RISK_TYPES, RiskBadge });
})(); } catch (e) { __ds_ns.__errors.push({ path: "components/analytical/RiskBadge.jsx", error: String((e && e.message) || e) }); }

// components/analytical/ExecutiveSummaryCard.jsx
try { (() => {
// Basis ExecutiveSummaryCard — «Что важно сейчас». The top-of-screen briefing:
// current analytical tone, 3–5 key insights, main risk, what would change the
// conclusion, last updated. Decision-support, never advice.
let _injected = false;
function injectCSS() {
  if (_injected || typeof document === "undefined") return;
  _injected = true;
  const css = `
.bss-exec{border:1px solid var(--border-strong);border-radius:var(--radius-lg);background:var(--bg-elevated);box-shadow:var(--shadow-md);overflow:hidden;}
.bss-exec__head{display:flex;align-items:center;justify-content:space-between;gap:12px;padding:16px 20px;border-bottom:1px solid var(--border-subtle);}
.bss-exec__title{display:flex;align-items:center;gap:8px;font-family:var(--font-display);font-size:17px;font-weight:var(--fw-semibold);color:var(--text-primary);margin:0;}
.bss-exec__tone{display:inline-flex;align-items:center;gap:6px;font-size:12px;font-weight:var(--fw-medium);padding:3px 10px;border-radius:var(--radius-pill);}
.bss-exec__tone--neutral{background:var(--bg-base);color:var(--text-secondary);border:1px solid var(--border-subtle);}
.bss-exec__tone--positive{background:var(--success-soft);color:var(--success);}
.bss-exec__tone--cautious{background:var(--warning-soft);color:var(--warning);}
.bss-exec__tone--negative{background:var(--danger-soft);color:var(--danger);}
.bss-exec__body{padding:16px 20px;display:flex;flex-direction:column;gap:14px;}
.bss-exec__insights{list-style:none;margin:0;padding:0;display:flex;flex-direction:column;gap:9px;}
.bss-exec__insights li{display:flex;gap:9px;align-items:flex-start;font-size:14px;line-height:1.5;color:var(--text-primary);}
.bss-exec__bullet{color:var(--accent);flex-shrink:0;margin-top:2px;}
.bss-exec__split{display:grid;grid-template-columns:1fr 1fr;gap:12px;}
@media (max-width:560px){.bss-exec__split{grid-template-columns:1fr;}}
.bss-exec__panel{border:1px solid var(--border-subtle);border-radius:var(--radius-md);background:var(--bg-base);padding:12px;}
.bss-exec__panel-label{font-size:11px;font-weight:var(--fw-semibold);text-transform:uppercase;letter-spacing:var(--ls-eyebrow);color:var(--text-tertiary);margin-bottom:7px;}
.bss-exec__panel-text{font-size:13px;line-height:1.5;color:var(--text-secondary);}
.bss-exec__foot{padding:10px 20px;border-top:1px solid var(--border-subtle);font-size:12px;color:var(--text-tertiary);display:flex;justify-content:space-between;gap:12px;flex-wrap:wrap;}
`;
  const el = document.createElement("style");
  el.setAttribute("data-bss", "exec");
  el.textContent = css;
  document.head.appendChild(el);
}
injectCSS();
const TONE_LABELS = {
  neutral: "Нейтральный",
  positive: "Конструктивный",
  cautious: "Осторожный",
  negative: "Настороженный"
};
function ExecutiveSummaryCard({
  title = "Что важно сейчас",
  tone = "neutral",
  toneLabel,
  insights = [],
  mainRisk,
  mainRiskType = "market",
  mainRiskSeverity = "medium",
  whatWouldChange,
  updated,
  className = ""
}) {
  injectCSS();
  return /*#__PURE__*/React.createElement("div", {
    className: ["bss-exec", className].filter(Boolean).join(" ")
  }, /*#__PURE__*/React.createElement("div", {
    className: "bss-exec__head"
  }, /*#__PURE__*/React.createElement("h3", {
    className: "bss-exec__title"
  }, /*#__PURE__*/React.createElement("svg", {
    width: "16",
    height: "16",
    viewBox: "0 0 16 16",
    fill: "none",
    "aria-hidden": "true",
    style: {
      color: "var(--accent)"
    }
  }, /*#__PURE__*/React.createElement("path", {
    d: "M8 1.5v13M1.5 8h13",
    stroke: "currentColor",
    strokeWidth: "1.4",
    strokeLinecap: "round",
    opacity: "0.35"
  }), /*#__PURE__*/React.createElement("circle", {
    cx: "8",
    cy: "8",
    r: "3",
    fill: "currentColor"
  })), title), /*#__PURE__*/React.createElement("span", {
    className: `bss-exec__tone bss-exec__tone--${tone}`
  }, "\u0422\u043E\u043D: ", toneLabel || TONE_LABELS[tone])), /*#__PURE__*/React.createElement("div", {
    className: "bss-exec__body"
  }, insights.length > 0 && /*#__PURE__*/React.createElement("ul", {
    className: "bss-exec__insights"
  }, insights.map((it, i) => /*#__PURE__*/React.createElement("li", {
    key: i
  }, /*#__PURE__*/React.createElement("span", {
    className: "bss-exec__bullet",
    "aria-hidden": "true"
  }, "\u2192"), /*#__PURE__*/React.createElement("span", null, it)))), /*#__PURE__*/React.createElement("div", {
    className: "bss-exec__split"
  }, mainRisk && /*#__PURE__*/React.createElement("div", {
    className: "bss-exec__panel"
  }, /*#__PURE__*/React.createElement("div", {
    className: "bss-exec__panel-label"
  }, "\u0413\u043B\u0430\u0432\u043D\u044B\u0439 \u0440\u0438\u0441\u043A"), /*#__PURE__*/React.createElement("div", {
    style: {
      marginBottom: 7
    }
  }, /*#__PURE__*/React.createElement(__ds_scope.RiskBadge, {
    type: mainRiskType,
    severity: mainRiskSeverity
  })), /*#__PURE__*/React.createElement("div", {
    className: "bss-exec__panel-text"
  }, mainRisk)), whatWouldChange && /*#__PURE__*/React.createElement("div", {
    className: "bss-exec__panel"
  }, /*#__PURE__*/React.createElement("div", {
    className: "bss-exec__panel-label"
  }, "\u0427\u0442\u043E \u0438\u0437\u043C\u0435\u043D\u0438\u0442 \u0432\u044B\u0432\u043E\u0434"), /*#__PURE__*/React.createElement("div", {
    className: "bss-exec__panel-text"
  }, whatWouldChange)))), updated && /*#__PURE__*/React.createElement("div", {
    className: "bss-exec__foot"
  }, /*#__PURE__*/React.createElement("span", null, "\u041E\u0431\u043D\u043E\u0432\u043B\u0435\u043D\u043E: ", updated), /*#__PURE__*/React.createElement("span", null, "\u041D\u0435 \u044F\u0432\u043B\u044F\u0435\u0442\u0441\u044F \u0438\u043D\u0432\u0435\u0441\u0442\u0438\u0446\u0438\u043E\u043D\u043D\u043E\u0439 \u0440\u0435\u043A\u043E\u043C\u0435\u043D\u0434\u0430\u0446\u0438\u0435\u0439")));
}
Object.assign(__ds_scope, { ExecutiveSummaryCard });
})(); } catch (e) { __ds_ns.__errors.push({ path: "components/analytical/ExecutiveSummaryCard.jsx", error: String((e && e.message) || e) }); }

// components/analytical/SourceTag.jsx
try { (() => {
// Basis SourceTag — an inline citation chip. Source name + optional date, links out.
// Makes evidence visible (evidence-first trust).
let _injected = false;
function injectCSS() {
  if (_injected || typeof document === "undefined") return;
  _injected = true;
  const css = `
.bss-src{display:inline-flex;align-items:center;gap:5px;border-radius:var(--radius-xs);padding:1px 7px;
  font-family:var(--font-sans);font-size:11px;font-weight:var(--fw-medium);color:var(--text-secondary);
  background:var(--bg-base);border:1px solid var(--border-subtle);white-space:nowrap;transition:color var(--motion-fast),border-color var(--motion-fast);}
a.bss-src:hover{color:var(--accent);border-color:var(--accent-border);}
a.bss-src:focus-visible{outline:none;box-shadow:var(--shadow-focus);}
.bss-src__icon{color:var(--text-tertiary);flex-shrink:0;}
a.bss-src:hover .bss-src__icon{color:var(--accent);}
.bss-src__date{color:var(--text-tertiary);}
`;
  const el = document.createElement("style");
  el.setAttribute("data-bss", "src");
  el.textContent = css;
  document.head.appendChild(el);
}
injectCSS();
function SourceTag({
  name,
  date,
  href,
  className = ""
}) {
  injectCSS();
  const inner = /*#__PURE__*/React.createElement(React.Fragment, null, /*#__PURE__*/React.createElement("svg", {
    className: "bss-src__icon",
    width: "11",
    height: "11",
    viewBox: "0 0 12 12",
    fill: "none",
    "aria-hidden": "true"
  }, /*#__PURE__*/React.createElement("path", {
    d: "M3 1.5h4l2.5 2.5v6.5h-6.5z",
    stroke: "currentColor",
    strokeWidth: "1",
    strokeLinejoin: "round"
  }), /*#__PURE__*/React.createElement("path", {
    d: "M7 1.5V4h2.5",
    stroke: "currentColor",
    strokeWidth: "1",
    strokeLinejoin: "round"
  })), /*#__PURE__*/React.createElement("span", null, name), date && /*#__PURE__*/React.createElement("span", {
    className: "bss-src__date"
  }, "\xB7 ", date));
  const cls = ["bss-src", className].filter(Boolean).join(" ");
  return href ? /*#__PURE__*/React.createElement("a", {
    className: cls,
    href: href,
    target: "_blank",
    rel: "noopener noreferrer"
  }, inner) : /*#__PURE__*/React.createElement("span", {
    className: cls
  }, inner);
}
Object.assign(__ds_scope, { SourceTag });
})(); } catch (e) { __ds_ns.__errors.push({ path: "components/analytical/SourceTag.jsx", error: String((e && e.message) || e) }); }

// components/analytical/FactorImpactCard.jsx
try { (() => {
// Basis FactorImpactCard — one factor's effect on a company:
// factor · channel · effect (pos/neg/mixed/neutral) · horizon · confidence · source.
let _injected = false;
function injectCSS() {
  if (_injected || typeof document === "undefined") return;
  _injected = true;
  const css = `
.bss-factor{border:1px solid var(--border-strong);border-radius:var(--radius-md);background:var(--bg-elevated);box-shadow:var(--shadow-sm);padding:14px 16px;display:flex;flex-direction:column;gap:10px;}
.bss-factor__top{display:flex;align-items:flex-start;justify-content:space-between;gap:10px;}
.bss-factor__name{font-family:var(--font-sans);font-size:15px;font-weight:var(--fw-semibold);color:var(--text-primary);}
.bss-factor__effect{display:inline-flex;align-items:center;gap:5px;font-size:12px;font-weight:var(--fw-semibold);padding:2px 9px;border-radius:var(--radius-pill);white-space:nowrap;flex-shrink:0;}
.bss-factor__effect--positive{background:var(--success-soft);color:var(--success);}
.bss-factor__effect--negative{background:var(--danger-soft);color:var(--danger);}
.bss-factor__effect--mixed{background:var(--warning-soft);color:var(--warning);}
.bss-factor__effect--neutral{background:var(--bg-base);color:var(--text-secondary);border:1px solid var(--border-subtle);}
.bss-factor__channel{font-size:13px;line-height:1.55;color:var(--text-secondary);}
.bss-factor__channel b{color:var(--text-primary);font-weight:var(--fw-semibold);}
.bss-factor__meta{display:flex;align-items:center;gap:14px;flex-wrap:wrap;padding-top:8px;border-top:1px solid var(--border-subtle);}
.bss-factor__horizon{font-size:11px;font-weight:var(--fw-medium);text-transform:uppercase;letter-spacing:0.04em;color:var(--text-tertiary);}
.bss-factor__horizon b{color:var(--text-secondary);}
`;
  const el = document.createElement("style");
  el.setAttribute("data-bss", "factor");
  el.textContent = css;
  document.head.appendChild(el);
}
injectCSS();
const EFFECT = {
  positive: {
    glyph: "▲",
    label: "Позитив"
  },
  negative: {
    glyph: "▼",
    label: "Негатив"
  },
  mixed: {
    glyph: "◆",
    label: "Смешанный"
  },
  neutral: {
    glyph: "▬",
    label: "Нейтрально"
  }
};
const HORIZON = {
  short: "Короткий",
  medium: "Средний",
  long: "Длинный"
};
function FactorImpactCard({
  factor,
  channel,
  effect = "neutral",
  effectLabel,
  horizon = "medium",
  confidence = "medium",
  source,
  sourceDate,
  sourceHref,
  className = ""
}) {
  injectCSS();
  const e = EFFECT[effect] || EFFECT.neutral;
  return /*#__PURE__*/React.createElement("div", {
    className: ["bss-factor", className].filter(Boolean).join(" ")
  }, /*#__PURE__*/React.createElement("div", {
    className: "bss-factor__top"
  }, /*#__PURE__*/React.createElement("div", {
    className: "bss-factor__name"
  }, factor), /*#__PURE__*/React.createElement("span", {
    className: `bss-factor__effect bss-factor__effect--${effect}`
  }, /*#__PURE__*/React.createElement("span", {
    "aria-hidden": "true"
  }, e.glyph), effectLabel || e.label)), channel && /*#__PURE__*/React.createElement("div", {
    className: "bss-factor__channel"
  }, channel), /*#__PURE__*/React.createElement("div", {
    className: "bss-factor__meta"
  }, /*#__PURE__*/React.createElement("span", {
    className: "bss-factor__horizon"
  }, "\u0413\u043E\u0440\u0438\u0437\u043E\u043D\u0442: ", /*#__PURE__*/React.createElement("b", null, HORIZON[horizon] || horizon)), /*#__PURE__*/React.createElement(__ds_scope.ConfidenceBadge, {
    level: confidence
  }), source && /*#__PURE__*/React.createElement(__ds_scope.SourceTag, {
    name: source,
    date: sourceDate,
    href: sourceHref
  })));
}
Object.assign(__ds_scope, { FactorImpactCard });
})(); } catch (e) { __ds_ns.__errors.push({ path: "components/analytical/FactorImpactCard.jsx", error: String((e && e.message) || e) }); }

// components/core/Badge.jsx
try { (() => {
// Basis Badge — status pill, soft fill + colored text. Tones are semantic.
let _injected = false;
function injectCSS() {
  if (_injected || typeof document === "undefined") return;
  _injected = true;
  const css = `
.bss-badge{display:inline-flex;align-items:center;gap:4px;border-radius:var(--radius-pill);
  padding:2px 8px;font-family:var(--font-sans);font-size:12px;font-weight:var(--fw-medium);
  line-height:18px;white-space:nowrap;}
.bss-badge--neutral{background:var(--bg-base);color:var(--text-secondary);border:1px solid var(--border-subtle);}
.bss-badge--accent{background:var(--accent-soft);color:var(--accent);}
.bss-badge--success{background:var(--success-soft);color:var(--success);}
.bss-badge--danger{background:var(--danger-soft);color:var(--danger);}
.bss-badge--warning{background:var(--warning-soft);color:var(--warning);}
.bss-badge--info{background:var(--info-soft);color:var(--info);}
`;
  const el = document.createElement("style");
  el.setAttribute("data-bss", "badge");
  el.textContent = css;
  document.head.appendChild(el);
}
injectCSS();
function Badge({
  children,
  tone = "neutral",
  className = ""
}) {
  injectCSS();
  return /*#__PURE__*/React.createElement("span", {
    className: ["bss-badge", `bss-badge--${tone}`, className].filter(Boolean).join(" ")
  }, children);
}
Object.assign(__ds_scope, { Badge });
})(); } catch (e) { __ds_ns.__errors.push({ path: "components/core/Badge.jsx", error: String((e && e.message) || e) }); }

// components/core/Button.jsx
try { (() => {
function _extends() { return _extends = Object.assign ? Object.assign.bind() : function (n) { for (var e = 1; e < arguments.length; e++) { var t = arguments[e]; for (var r in t) ({}).hasOwnProperty.call(t, r) && (n[r] = t[r]); } return n; }, _extends.apply(null, arguments); }
// Basis Button — the signature cobalt action control.
// Variants: primary (cobalt), secondary (white tile), ghost, danger.
// Sizes: sm / md / lg. Self-contained: injects its own token-driven CSS once.

let _injected = false;
function injectCSS() {
  if (_injected || typeof document === "undefined") return;
  _injected = true;
  const css = `
.bss-btn{display:inline-flex;align-items:center;justify-content:center;font-family:var(--font-sans);
  font-weight:var(--fw-medium);border-radius:var(--radius-sm);border:1px solid transparent;cursor:pointer;
  user-select:none;transition:background var(--motion-fast),color var(--motion-fast),border-color var(--motion-fast);
  white-space:nowrap;}
.bss-btn:focus-visible{outline:none;box-shadow:var(--shadow-focus);}
.bss-btn:active:not(:disabled){transform:translateY(1px);}
.bss-btn[disabled]{opacity:.5;cursor:not-allowed;pointer-events:none;}
.bss-btn--sm{font-size:13px;padding:6px 12px;gap:6px;min-height:32px;}
.bss-btn--md{font-size:14px;padding:8px 16px;gap:8px;min-height:40px;}
.bss-btn--lg{font-size:15px;padding:12px 20px;gap:8px;min-height:48px;}
.bss-btn--primary{background:var(--accent);color:var(--on-accent);}
.bss-btn--primary:hover:not(:disabled){background:var(--accent-hover);}
.bss-btn--secondary{background:var(--bg-elevated);color:var(--text-primary);border-color:var(--border-strong);}
.bss-btn--secondary:hover:not(:disabled){background:var(--accent-soft);}
.bss-btn--ghost{background:transparent;color:var(--text-secondary);}
.bss-btn--ghost:hover:not(:disabled){background:var(--accent-soft);color:var(--text-primary);}
.bss-btn--danger{background:var(--danger);color:var(--on-danger);}
.bss-btn--danger:hover:not(:disabled){opacity:.9;}
.bss-btn__spin{animation:bss-spin .7s linear infinite;}
@keyframes bss-spin{to{transform:rotate(360deg);}}
@media (prefers-reduced-motion: reduce){.bss-btn__spin{animation:none;}}
`;
  const el = document.createElement("style");
  el.setAttribute("data-bss", "button");
  el.textContent = css;
  document.head.appendChild(el);
}
injectCSS();
function Spinner() {
  return /*#__PURE__*/React.createElement("svg", {
    className: "bss-btn__spin",
    width: "16",
    height: "16",
    viewBox: "0 0 24 24",
    fill: "none",
    "aria-hidden": "true"
  }, /*#__PURE__*/React.createElement("circle", {
    cx: "12",
    cy: "12",
    r: "9",
    stroke: "currentColor",
    strokeWidth: "3",
    opacity: "0.25"
  }), /*#__PURE__*/React.createElement("path", {
    d: "M21 12a9 9 0 0 0-9-9",
    stroke: "currentColor",
    strokeWidth: "3",
    strokeLinecap: "round"
  }));
}
function Button({
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
  injectCSS();
  const isDisabled = disabled || loading;
  const cls = ["bss-btn", `bss-btn--${size}`, `bss-btn--${variant}`, className].filter(Boolean).join(" ");
  return /*#__PURE__*/React.createElement("button", _extends({
    type: type,
    disabled: isDisabled,
    "aria-busy": loading || undefined,
    className: cls
  }, rest), loading && /*#__PURE__*/React.createElement(Spinner, null), !loading && iconLeft && /*#__PURE__*/React.createElement("span", {
    style: {
      display: "inline-flex",
      flexShrink: 0
    }
  }, iconLeft), children && /*#__PURE__*/React.createElement("span", null, children), !loading && iconRight && /*#__PURE__*/React.createElement("span", {
    style: {
      display: "inline-flex",
      flexShrink: 0
    }
  }, iconRight));
}
Object.assign(__ds_scope, { Button });
})(); } catch (e) { __ds_ns.__errors.push({ path: "components/core/Button.jsx", error: String((e && e.message) || e) }); }

// components/core/Chip.jsx
try { (() => {
// Basis Chip — interactive selectable / removable pill.
let _injected = false;
function injectCSS() {
  if (_injected || typeof document === "undefined") return;
  _injected = true;
  const css = `
.bss-chip{display:inline-flex;align-items:center;gap:6px;border-radius:var(--radius-pill);
  padding:5px 12px;font-family:var(--font-sans);font-size:13px;font-weight:var(--fw-medium);
  min-height:32px;transition:background var(--motion-fast),color var(--motion-fast);
  border:1px solid var(--border-strong);background:var(--bg-elevated);color:var(--text-secondary);cursor:pointer;}
.bss-chip:hover{background:var(--accent-soft);color:var(--text-primary);}
.bss-chip:focus-visible{outline:none;box-shadow:var(--shadow-focus);}
.bss-chip--selected{background:var(--accent);color:var(--on-accent);border-color:transparent;}
.bss-chip--selected:hover{background:var(--accent-hover);color:var(--on-accent);}
.bss-chip[aria-disabled="true"]{opacity:.5;pointer-events:none;}
.bss-chip__x{display:inline-flex;align-items:center;justify-content:center;width:16px;height:16px;
  border:0;background:transparent;color:inherit;opacity:.7;cursor:pointer;padding:0;border-radius:var(--radius-pill);}
.bss-chip__x:hover{opacity:1;}
.bss-chip__x:focus-visible{outline:none;box-shadow:var(--shadow-focus);}
`;
  const el = document.createElement("style");
  el.setAttribute("data-bss", "chip");
  el.textContent = css;
  document.head.appendChild(el);
}
injectCSS();
function Chip({
  children,
  selected = false,
  onClick,
  onRemove,
  disabled = false,
  className = ""
}) {
  injectCSS();
  const cls = ["bss-chip", selected && "bss-chip--selected", className].filter(Boolean).join(" ");
  return /*#__PURE__*/React.createElement("span", {
    className: cls,
    role: "button",
    tabIndex: disabled ? -1 : 0,
    "aria-pressed": selected,
    "aria-disabled": disabled || undefined,
    onClick: disabled ? undefined : onClick,
    onKeyDown: e => {
      if (!disabled && (e.key === "Enter" || e.key === " ")) {
        e.preventDefault();
        onClick && onClick(e);
      }
    }
  }, children, onRemove && /*#__PURE__*/React.createElement("button", {
    type: "button",
    className: "bss-chip__x",
    "aria-label": "\u0423\u0434\u0430\u043B\u0438\u0442\u044C",
    onClick: e => {
      e.stopPropagation();
      onRemove(e);
    }
  }, /*#__PURE__*/React.createElement("svg", {
    width: "10",
    height: "10",
    viewBox: "0 0 10 10",
    "aria-hidden": "true"
  }, /*#__PURE__*/React.createElement("path", {
    d: "M1 1l8 8M9 1l-8 8",
    stroke: "currentColor",
    strokeWidth: "1.5",
    strokeLinecap: "round"
  }))));
}
Object.assign(__ds_scope, { Chip });
})(); } catch (e) { __ds_ns.__errors.push({ path: "components/core/Chip.jsx", error: String((e && e.message) || e) }); }

// components/core/IconButton.jsx
try { (() => {
function _extends() { return _extends = Object.assign ? Object.assign.bind() : function (n) { for (var e = 1; e < arguments.length; e++) { var t = arguments[e]; for (var r in t) ({}).hasOwnProperty.call(t, r) && (n[r] = t[r]); } return n; }, _extends.apply(null, arguments); }
// Basis IconButton — square, min 32×32 touch target. Ghost by default.
let _injected = false;
function injectCSS() {
  if (_injected || typeof document === "undefined") return;
  _injected = true;
  const css = `
.bss-iconbtn{display:inline-flex;align-items:center;justify-content:center;border-radius:var(--radius-sm);
  border:1px solid transparent;cursor:pointer;color:var(--text-secondary);background:transparent;
  transition:background var(--motion-fast),color var(--motion-fast);}
.bss-iconbtn:hover:not(:disabled){background:var(--accent-soft);color:var(--text-primary);}
.bss-iconbtn:focus-visible{outline:none;box-shadow:var(--shadow-focus);}
.bss-iconbtn[disabled]{opacity:.5;cursor:not-allowed;pointer-events:none;}
.bss-iconbtn--sm{width:32px;height:32px;}
.bss-iconbtn--md{width:40px;height:40px;}
.bss-iconbtn--lg{width:48px;height:48px;}
.bss-iconbtn--secondary{background:var(--bg-elevated);border-color:var(--border-strong);color:var(--text-primary);}
.bss-iconbtn--secondary:hover:not(:disabled){background:var(--accent-soft);}
`;
  const el = document.createElement("style");
  el.setAttribute("data-bss", "iconbutton");
  el.textContent = css;
  document.head.appendChild(el);
}
injectCSS();
function IconButton({
  children,
  variant = "ghost",
  size = "md",
  disabled = false,
  className = "",
  "aria-label": ariaLabel,
  ...rest
}) {
  injectCSS();
  const cls = ["bss-iconbtn", `bss-iconbtn--${size}`, variant === "secondary" && "bss-iconbtn--secondary", className].filter(Boolean).join(" ");
  return /*#__PURE__*/React.createElement("button", _extends({
    type: "button",
    "aria-label": ariaLabel,
    disabled: disabled,
    className: cls
  }, rest), children);
}
Object.assign(__ds_scope, { IconButton });
})(); } catch (e) { __ds_ns.__errors.push({ path: "components/core/IconButton.jsx", error: String((e && e.message) || e) }); }

// components/core/Input.jsx
try { (() => {
function _extends() { return _extends = Object.assign ? Object.assign.bind() : function (n) { for (var e = 1; e < arguments.length; e++) { var t = arguments[e]; for (var r in t) ({}).hasOwnProperty.call(t, r) && (n[r] = t[r]); } return n; }, _extends.apply(null, arguments); }
const {
  useId
} = React; // Basis Input — visible label, focus ring, error state. iOS-safe 16px font.
let _injected = false;
function injectCSS() {
  if (_injected || typeof document === "undefined") return;
  _injected = true;
  const css = `
.bss-field{display:flex;flex-direction:column;gap:6px;}
.bss-field__label{font-family:var(--font-sans);font-size:13px;font-weight:var(--fw-medium);color:var(--text-secondary);}
.bss-input{width:100%;padding:8px 12px;border-radius:var(--radius-xs);font-family:var(--font-sans);font-size:14px;
  background:var(--bg-elevated);color:var(--text-primary);border:1px solid var(--border-strong);
  transition:border-color var(--motion-fast),box-shadow var(--motion-fast);}
.bss-input::placeholder{color:var(--text-tertiary);}
.bss-input:focus-visible{outline:none;box-shadow:var(--shadow-focus);border-color:var(--accent);}
.bss-input--error{border-color:var(--danger);}
.bss-input:disabled{opacity:.5;cursor:not-allowed;background:var(--bg-base);}
.bss-field__err{font-size:12px;color:var(--danger);}
.bss-input__search{position:relative;}
.bss-input__search .bss-input{padding-left:34px;}
.bss-input__search svg{position:absolute;left:11px;top:50%;transform:translateY(-50%);color:var(--text-tertiary);pointer-events:none;}
`;
  const el = document.createElement("style");
  el.setAttribute("data-bss", "input");
  el.textContent = css;
  document.head.appendChild(el);
}
injectCSS();
function Input({
  label,
  error = null,
  disabled = false,
  search = false,
  id,
  className = "",
  ...rest
}) {
  injectCSS();
  const auto = useId();
  const inputId = id || auto;
  const errId = `${inputId}-err`;
  const input = /*#__PURE__*/React.createElement("input", _extends({
    id: inputId,
    disabled: disabled,
    "aria-invalid": !!error,
    "aria-describedby": error ? errId : undefined,
    className: ["bss-input", error && "bss-input--error"].filter(Boolean).join(" ")
  }, rest));
  return /*#__PURE__*/React.createElement("div", {
    className: ["bss-field", className].filter(Boolean).join(" ")
  }, label && /*#__PURE__*/React.createElement("label", {
    htmlFor: inputId,
    className: "bss-field__label"
  }, label), search ? /*#__PURE__*/React.createElement("span", {
    className: "bss-input__search"
  }, /*#__PURE__*/React.createElement("svg", {
    width: "16",
    height: "16",
    viewBox: "0 0 16 16",
    fill: "none",
    "aria-hidden": "true"
  }, /*#__PURE__*/React.createElement("circle", {
    cx: "7",
    cy: "7",
    r: "5",
    stroke: "currentColor",
    strokeWidth: "1.5"
  }), /*#__PURE__*/React.createElement("path", {
    d: "M11 11l3 3",
    stroke: "currentColor",
    strokeWidth: "1.5",
    strokeLinecap: "round"
  })), input) : input, error && /*#__PURE__*/React.createElement("span", {
    id: errId,
    className: "bss-field__err"
  }, error));
}
Object.assign(__ds_scope, { Input });
})(); } catch (e) { __ds_ns.__errors.push({ path: "components/core/Input.jsx", error: String((e && e.message) || e) }); }

// components/core/Select.jsx
try { (() => {
function _extends() { return _extends = Object.assign ? Object.assign.bind() : function (n) { for (var e = 1; e < arguments.length; e++) { var t = arguments[e]; for (var r in t) ({}).hasOwnProperty.call(t, r) && (n[r] = t[r]); } return n; }, _extends.apply(null, arguments); }
const {
  useId
} = React; // Basis Select — native <select> styled to tokens, with a chevron.
let _injected = false;
function injectCSS() {
  if (_injected || typeof document === "undefined") return;
  _injected = true;
  const css = `
.bss-select-wrap{position:relative;}
.bss-select{width:100%;appearance:none;-webkit-appearance:none;padding:8px 36px 8px 12px;border-radius:var(--radius-xs);
  font-family:var(--font-sans);font-size:14px;background:var(--bg-elevated);color:var(--text-primary);
  border:1px solid var(--border-strong);transition:border-color var(--motion-fast),box-shadow var(--motion-fast);cursor:pointer;}
.bss-select:focus-visible{outline:none;box-shadow:var(--shadow-focus);border-color:var(--accent);}
.bss-select:disabled{opacity:.5;cursor:not-allowed;background:var(--bg-base);}
.bss-select-wrap svg{position:absolute;right:12px;top:50%;transform:translateY(-50%);color:var(--text-tertiary);pointer-events:none;}
`;
  const el = document.createElement("style");
  el.setAttribute("data-bss", "select");
  el.textContent = css;
  document.head.appendChild(el);
}
injectCSS();
function Select({
  label,
  options = [],
  disabled = false,
  id,
  className = "",
  ...rest
}) {
  injectCSS();
  const auto = useId();
  const selectId = id || auto;
  return /*#__PURE__*/React.createElement("div", {
    className: ["bss-field", className].filter(Boolean).join(" ")
  }, label && /*#__PURE__*/React.createElement("label", {
    htmlFor: selectId,
    className: "bss-field__label"
  }, label), /*#__PURE__*/React.createElement("div", {
    className: "bss-select-wrap"
  }, /*#__PURE__*/React.createElement("select", _extends({
    id: selectId,
    disabled: disabled,
    className: "bss-select"
  }, rest), options.map(o => /*#__PURE__*/React.createElement("option", {
    key: o.value,
    value: o.value
  }, o.label))), /*#__PURE__*/React.createElement("svg", {
    width: "12",
    height: "12",
    viewBox: "0 0 12 12",
    fill: "none",
    "aria-hidden": "true"
  }, /*#__PURE__*/React.createElement("path", {
    d: "M2 4l4 4 4-4",
    stroke: "currentColor",
    strokeWidth: "1.5",
    strokeLinecap: "round"
  }))));
}
Object.assign(__ds_scope, { Select });
})(); } catch (e) { __ds_ns.__errors.push({ path: "components/core/Select.jsx", error: String((e && e.message) || e) }); }

// components/core/Toggle.jsx
try { (() => {
const {
  useId
} = React; // Basis Toggle — accessible switch. Cobalt when on.
let _injected = false;
function injectCSS() {
  if (_injected || typeof document === "undefined") return;
  _injected = true;
  const css = `
.bss-toggle{display:inline-flex;align-items:center;gap:10px;cursor:pointer;font-family:var(--font-sans);font-size:14px;color:var(--text-primary);}
.bss-toggle[aria-disabled="true"]{opacity:.5;pointer-events:none;}
.bss-toggle__track{position:relative;width:38px;height:22px;border-radius:var(--radius-pill);
  background:var(--bg-hover);border:1px solid var(--border-strong);transition:background var(--motion-fast),border-color var(--motion-fast);flex-shrink:0;}
.bss-toggle__track--on{background:var(--accent);border-color:transparent;}
.bss-toggle__knob{position:absolute;top:2px;left:2px;width:16px;height:16px;border-radius:var(--radius-pill);
  background:#fff;box-shadow:var(--shadow-sm);transition:transform var(--motion-fast);}
.bss-toggle__track--on .bss-toggle__knob{transform:translateX(16px);}
.bss-toggle__btn{position:absolute;inset:0;opacity:0;cursor:pointer;}
.bss-toggle__btn:focus-visible + .bss-toggle__track{box-shadow:var(--shadow-focus);}
`;
  const el = document.createElement("style");
  el.setAttribute("data-bss", "toggle");
  el.textContent = css;
  document.head.appendChild(el);
}
injectCSS();
function Toggle({
  checked = false,
  onChange,
  label,
  disabled = false,
  id,
  className = ""
}) {
  injectCSS();
  const auto = useId();
  const tid = id || auto;
  return /*#__PURE__*/React.createElement("label", {
    htmlFor: tid,
    className: ["bss-toggle", className].filter(Boolean).join(" "),
    "aria-disabled": disabled || undefined
  }, /*#__PURE__*/React.createElement("span", {
    style: {
      position: "relative",
      display: "inline-flex"
    }
  }, /*#__PURE__*/React.createElement("input", {
    id: tid,
    type: "checkbox",
    role: "switch",
    className: "bss-toggle__btn",
    checked: checked,
    disabled: disabled,
    onChange: e => onChange && onChange(e.target.checked, e)
  }), /*#__PURE__*/React.createElement("span", {
    className: ["bss-toggle__track", checked && "bss-toggle__track--on"].filter(Boolean).join(" ")
  }, /*#__PURE__*/React.createElement("span", {
    className: "bss-toggle__knob"
  }))), label && /*#__PURE__*/React.createElement("span", null, label));
}
Object.assign(__ds_scope, { Toggle });
})(); } catch (e) { __ds_ns.__errors.push({ path: "components/core/Toggle.jsx", error: String((e && e.message) || e) }); }

// components/core/Tooltip.jsx
try { (() => {
const {
  useId,
  useState
} = React; // Basis Tooltip — hover/focus, overlay surface + shadow.
let _injected = false;
function injectCSS() {
  if (_injected || typeof document === "undefined") return;
  _injected = true;
  const css = `
.bss-tip-wrap{position:relative;display:inline-flex;}
.bss-tip{position:absolute;z-index:50;padding:5px 8px;border-radius:var(--radius-sm);white-space:nowrap;pointer-events:none;
  background:var(--bg-overlay-srf);color:var(--text-primary);border:1px solid var(--border-subtle);box-shadow:var(--shadow-lg);
  font-family:var(--font-sans);font-size:12px;line-height:18px;}
.bss-tip--top{bottom:100%;left:50%;transform:translateX(-50%);margin-bottom:6px;}
.bss-tip--bottom{top:100%;left:50%;transform:translateX(-50%);margin-top:6px;}
.bss-tip--left{right:100%;top:50%;transform:translateY(-50%);margin-right:6px;}
.bss-tip--right{left:100%;top:50%;transform:translateY(-50%);margin-left:6px;}
`;
  const el = document.createElement("style");
  el.setAttribute("data-bss", "tooltip");
  el.textContent = css;
  document.head.appendChild(el);
}
injectCSS();
function Tooltip({
  label,
  children,
  side = "top"
}) {
  injectCSS();
  const [open, setOpen] = useState(false);
  const tipId = useId();
  return /*#__PURE__*/React.createElement("span", {
    className: "bss-tip-wrap",
    "aria-describedby": open ? tipId : undefined,
    onMouseEnter: () => setOpen(true),
    onMouseLeave: () => setOpen(false),
    onFocus: () => setOpen(true),
    onBlur: () => setOpen(false)
  }, children, open && /*#__PURE__*/React.createElement("span", {
    role: "tooltip",
    id: tipId,
    className: `bss-tip bss-tip--${side}`
  }, label));
}
Object.assign(__ds_scope, { Tooltip });
})(); } catch (e) { __ds_ns.__errors.push({ path: "components/core/Tooltip.jsx", error: String((e && e.message) || e) }); }

// components/data/DataTable.jsx
try { (() => {
// Basis DataTable — financial table. First column left + medium ink; the rest
// right-aligned, mono, tabular. Subtle internal hairlines, strong outer border.
let _injected = false;
function injectCSS() {
  if (_injected || typeof document === "undefined") return;
  _injected = true;
  const css = `
.bss-tbl-wrap{overflow-x:auto;border:1px solid var(--border-strong);border-radius:var(--radius-md);background:var(--bg-elevated);}
.bss-tbl{width:100%;border-collapse:collapse;font-family:var(--font-sans);font-size:13px;}
.bss-tbl caption{text-align:left;padding:8px 12px;color:var(--text-tertiary);font-size:12px;}
.bss-tbl thead tr{border-bottom:1px solid var(--border-strong);}
.bss-tbl th{padding:8px 12px;font-size:11px;font-weight:var(--fw-medium);text-transform:uppercase;
  letter-spacing:var(--ls-eyebrow);color:var(--text-tertiary);}
.bss-tbl th.bss-l,.bss-tbl td.bss-l{text-align:left;}
.bss-tbl th.bss-r,.bss-tbl td.bss-r{text-align:right;}
.bss-tbl tbody tr{border-bottom:1px solid var(--border-subtle);transition:background var(--motion-fast);}
.bss-tbl tbody tr:last-child{border-bottom:0;}
.bss-tbl tbody tr.bss-clickable{cursor:pointer;}
.bss-tbl tbody tr:hover{background:var(--bg-hover);}
.bss-tbl td{padding:8px 12px;color:var(--text-secondary);}
.bss-tbl td.bss-l{color:var(--text-primary);font-weight:var(--fw-medium);}
.bss-tbl td.bss-r{font-family:var(--font-mono);font-variant-numeric:tabular-nums;}
`;
  const el = document.createElement("style");
  el.setAttribute("data-bss", "table");
  el.textContent = css;
  document.head.appendChild(el);
}
injectCSS();
function DataTable({
  columns = [],
  rows = [],
  caption,
  onRowClick,
  className = ""
}) {
  injectCSS();
  return /*#__PURE__*/React.createElement("div", {
    className: ["bss-tbl-wrap", className].filter(Boolean).join(" ")
  }, /*#__PURE__*/React.createElement("table", {
    className: "bss-tbl"
  }, caption && /*#__PURE__*/React.createElement("caption", null, caption), /*#__PURE__*/React.createElement("thead", null, /*#__PURE__*/React.createElement("tr", null, columns.map((c, i) => /*#__PURE__*/React.createElement("th", {
    key: c.key,
    scope: "col",
    className: i === 0 ? "bss-l" : "bss-r"
  }, c.label)))), /*#__PURE__*/React.createElement("tbody", null, rows.map((r, ri) => /*#__PURE__*/React.createElement("tr", {
    key: ri,
    onClick: onRowClick ? () => onRowClick(r) : undefined,
    className: onRowClick ? "bss-clickable" : undefined
  }, columns.map((c, i) => /*#__PURE__*/React.createElement("td", {
    key: c.key,
    className: i === 0 ? "bss-l" : "bss-r"
  }, c.render ? c.render(r[c.key], r) : r[c.key])))))));
}
Object.assign(__ds_scope, { DataTable });
})(); } catch (e) { __ds_ns.__errors.push({ path: "components/data/DataTable.jsx", error: String((e && e.message) || e) }); }

// components/data/Delta.jsx
try { (() => {
// Basis Delta — a signed change rendered with a ▲/▼/▬ glyph + semantic color.
// The cardinal rule: gain/loss color NEVER appears without its glyph.
// ru-RU number formatting (comma decimals, narrow-nbsp grouping, nbsp before unit).

const NNBSP = "\u202F"; // narrow no-break space (thousands)
const NBSP = "\u00A0"; // no-break space (before unit)

function fmt(value, decimals) {
  const opts = {};
  if (decimals !== undefined) {
    opts.minimumFractionDigits = decimals;
    opts.maximumFractionDigits = decimals;
  }
  const out = new Intl.NumberFormat("ru-RU", opts).format(value);
  return out.replace(/(\d)[\s\u00A0\u202F](?=\d{3}\b)/g, `$1${NNBSP}`);
}
function Delta({
  value,
  suffix = "%",
  decimals = 1,
  className = "",
  style
}) {
  if (value === null || value === undefined) return /*#__PURE__*/React.createElement("span", {
    style: {
      color: "var(--text-tertiary)"
    }
  }, "\u2014");
  const up = value > 0,
    flat = value === 0;
  const glyph = flat ? "▬" : up ? "▲" : "▼";
  const color = flat ? "var(--text-tertiary)" : up ? "var(--success)" : "var(--danger)";
  const abs = Math.abs(value);
  const body = suffix === "%" ? `${fmt(abs, decimals)}${NBSP}%` : `${fmt(abs, decimals)}${suffix ? NBSP + suffix : ""}`;
  return /*#__PURE__*/React.createElement("span", {
    className: className,
    style: {
      display: "inline-flex",
      alignItems: "center",
      gap: 4,
      color,
      fontFamily: "var(--font-mono)",
      fontVariantNumeric: "tabular-nums",
      ...style
    }
  }, /*#__PURE__*/React.createElement("span", {
    "aria-hidden": "true"
  }, glyph), body);
}
Object.assign(__ds_scope, { Delta });
})(); } catch (e) { __ds_ns.__errors.push({ path: "components/data/Delta.jsx", error: String((e && e.message) || e) }); }

// components/analytical/ScenarioTabs.jsx
try { (() => {
const {
  useState
} = React;
// Basis ScenarioTabs — Base / Bull / Bear / Stress. Each scenario: assumptions,
// revenue/margin/FCF effects, what must happen to materialize, what invalidates it.
let _injected = false;
function injectCSS() {
  if (_injected || typeof document === "undefined") return;
  _injected = true;
  const css = `
.bss-scen{border:1px solid var(--border-strong);border-radius:var(--radius-md);background:var(--bg-elevated);box-shadow:var(--shadow-sm);overflow:hidden;}
.bss-scen__tabs{display:flex;gap:2px;padding:6px 6px 0;border-bottom:1px solid var(--border-subtle);background:var(--bg-base);}
.bss-scen__tab{flex:1;padding:9px 8px;font-family:var(--font-sans);font-size:13px;font-weight:var(--fw-medium);
  background:transparent;border:0;border-bottom:2px solid transparent;color:var(--text-secondary);cursor:pointer;
  transition:color var(--motion-fast),border-color var(--motion-fast);}
.bss-scen__tab:hover{color:var(--text-primary);}
.bss-scen__tab[aria-selected="true"]{color:var(--accent);border-bottom-color:var(--accent);}
.bss-scen__tab:focus-visible{outline:none;box-shadow:var(--shadow-focus);border-radius:var(--radius-xs);}
.bss-scen__body{padding:16px;display:flex;flex-direction:column;gap:14px;}
.bss-scen__effects{display:grid;grid-template-columns:repeat(3,1fr);gap:10px;}
.bss-scen__eff{border:1px solid var(--border-subtle);border-radius:var(--radius-sm);background:var(--bg-base);padding:10px 12px;}
.bss-scen__eff-label{font-size:10px;font-weight:var(--fw-semibold);text-transform:uppercase;letter-spacing:var(--ls-eyebrow);color:var(--text-tertiary);margin-bottom:5px;}
.bss-scen__sec-label{font-size:11px;font-weight:var(--fw-semibold);text-transform:uppercase;letter-spacing:var(--ls-eyebrow);color:var(--text-tertiary);margin-bottom:5px;}
.bss-scen__text{font-size:13px;line-height:1.55;color:var(--text-secondary);}
.bss-scen__split{display:grid;grid-template-columns:1fr 1fr;gap:12px;}
@media (max-width:560px){.bss-scen__split,.bss-scen__effects{grid-template-columns:1fr;}}
.bss-scen__guard{border-left:2px solid var(--warning);background:var(--warning-soft);border-radius:var(--radius-sm);padding:8px 11px;}
.bss-scen__guard .bss-scen__sec-label{color:var(--warning);}
`;
  const el = document.createElement("style");
  el.setAttribute("data-bss", "scenario");
  el.textContent = css;
  document.head.appendChild(el);
}
injectCSS();
const DEFAULT_LABELS = {
  base: "База",
  bull: "Рост",
  bear: "Спад",
  stress: "Стресс"
};
function ScenarioTabs({
  scenarios = {},
  order = ["base", "bull", "bear", "stress"],
  labels = DEFAULT_LABELS,
  defaultKey,
  className = ""
}) {
  injectCSS();
  const keys = order.filter(k => scenarios[k]);
  const [active, setActive] = useState(defaultKey || keys[0]);
  const s = scenarios[active] || {};
  return /*#__PURE__*/React.createElement("div", {
    className: ["bss-scen", className].filter(Boolean).join(" ")
  }, /*#__PURE__*/React.createElement("div", {
    className: "bss-scen__tabs",
    role: "tablist",
    "aria-label": "\u0421\u0446\u0435\u043D\u0430\u0440\u0438\u0438"
  }, keys.map(k => /*#__PURE__*/React.createElement("button", {
    key: k,
    role: "tab",
    "aria-selected": k === active,
    className: "bss-scen__tab",
    onClick: () => setActive(k)
  }, labels[k] || k))), /*#__PURE__*/React.createElement("div", {
    className: "bss-scen__body",
    role: "tabpanel"
  }, s.assumptions && /*#__PURE__*/React.createElement("div", null, /*#__PURE__*/React.createElement("div", {
    className: "bss-scen__sec-label"
  }, "\u0414\u043E\u043F\u0443\u0449\u0435\u043D\u0438\u044F"), /*#__PURE__*/React.createElement("div", {
    className: "bss-scen__text"
  }, s.assumptions)), /*#__PURE__*/React.createElement("div", {
    className: "bss-scen__effects"
  }, /*#__PURE__*/React.createElement("div", {
    className: "bss-scen__eff"
  }, /*#__PURE__*/React.createElement("div", {
    className: "bss-scen__eff-label"
  }, "\u0412\u044B\u0440\u0443\u0447\u043A\u0430"), typeof s.revenue === "number" ? /*#__PURE__*/React.createElement(__ds_scope.Delta, {
    value: s.revenue
  }) : /*#__PURE__*/React.createElement("span", {
    className: "bss-scen__text"
  }, s.revenue || "—")), /*#__PURE__*/React.createElement("div", {
    className: "bss-scen__eff"
  }, /*#__PURE__*/React.createElement("div", {
    className: "bss-scen__eff-label"
  }, "\u041C\u0430\u0440\u0436\u0430"), typeof s.margin === "number" ? /*#__PURE__*/React.createElement(__ds_scope.Delta, {
    value: s.margin,
    suffix: "\u043F.\u043F."
  }) : /*#__PURE__*/React.createElement("span", {
    className: "bss-scen__text"
  }, s.margin || "—")), /*#__PURE__*/React.createElement("div", {
    className: "bss-scen__eff"
  }, /*#__PURE__*/React.createElement("div", {
    className: "bss-scen__eff-label"
  }, "FCF"), typeof s.fcf === "number" ? /*#__PURE__*/React.createElement(__ds_scope.Delta, {
    value: s.fcf
  }) : /*#__PURE__*/React.createElement("span", {
    className: "bss-scen__text"
  }, s.fcf || "—"))), /*#__PURE__*/React.createElement("div", {
    className: "bss-scen__split"
  }, s.materialize && /*#__PURE__*/React.createElement("div", null, /*#__PURE__*/React.createElement("div", {
    className: "bss-scen__sec-label"
  }, "\u0427\u0442\u043E \u0434\u043E\u043B\u0436\u043D\u043E \u043F\u0440\u043E\u0438\u0437\u043E\u0439\u0442\u0438"), /*#__PURE__*/React.createElement("div", {
    className: "bss-scen__text"
  }, s.materialize)), s.invalidate && /*#__PURE__*/React.createElement("div", {
    className: "bss-scen__guard"
  }, /*#__PURE__*/React.createElement("div", {
    className: "bss-scen__sec-label"
  }, "\u0427\u0442\u043E \u043E\u043F\u0440\u043E\u0432\u0435\u0440\u0433\u043D\u0435\u0442 \u0441\u0446\u0435\u043D\u0430\u0440\u0438\u0439"), /*#__PURE__*/React.createElement("div", {
    className: "bss-scen__text"
  }, s.invalidate)))));
}
Object.assign(__ds_scope, { ScenarioTabs });
})(); } catch (e) { __ds_ns.__errors.push({ path: "components/analytical/ScenarioTabs.jsx", error: String((e && e.message) || e) }); }

// components/feedback/Callout.jsx
try { (() => {
// Basis Callout — a framed conclusion / honest caveat. Soft tone fill + left
// border + tone glyph. INFO is the neutral default: it frames «честно: данные
// противоречивы» as a TRUST feature, not an alarm. Caution = real risk only.
let _injected = false;
function injectCSS() {
  if (_injected || typeof document === "undefined") return;
  _injected = true;
  const css = `
.bss-callout{display:flex;gap:12px;align-items:flex-start;border-radius:var(--radius-md);border-left:2px solid;padding:12px;}
.bss-callout__glyph{flex-shrink:0;font-size:16px;line-height:1.4;}
.bss-callout__label{font-family:var(--font-sans);font-size:12px;font-weight:var(--fw-semibold);text-transform:uppercase;
  letter-spacing:var(--ls-eyebrow);margin-bottom:2px;}
.bss-callout__body{font-size:14px;line-height:1.55;color:var(--text-primary);}
.bss-callout--neutral{background:var(--bg-base);border-color:var(--border-strong);}
.bss-callout--neutral .bss-callout__glyph{color:var(--text-tertiary);} .bss-callout--neutral .bss-callout__label{color:var(--text-secondary);}
.bss-callout--info{background:var(--info-soft);border-color:var(--info);}
.bss-callout--info .bss-callout__glyph,.bss-callout--info .bss-callout__label{color:var(--info);}
.bss-callout--positive{background:var(--success-soft);border-color:var(--success);}
.bss-callout--positive .bss-callout__glyph,.bss-callout--positive .bss-callout__label{color:var(--success);}
.bss-callout--caution{background:var(--warning-soft);border-color:var(--warning);}
.bss-callout--caution .bss-callout__glyph,.bss-callout--caution .bss-callout__label{color:var(--warning);}
`;
  const el = document.createElement("style");
  el.setAttribute("data-bss", "callout");
  el.textContent = css;
  document.head.appendChild(el);
}
injectCSS();
const TONES = {
  neutral: {
    glyph: "ℹ",
    title: "Что это"
  },
  info: {
    glyph: "⚖",
    title: "Честно"
  },
  positive: {
    glyph: "▲",
    title: "Сильная сторона"
  },
  caution: {
    glyph: "⚠",
    title: "Риск"
  }
};
function Callout({
  tone = "info",
  title,
  icon,
  children,
  className = ""
}) {
  injectCSS();
  const t = TONES[tone] || TONES.info;
  const heading = title !== undefined ? title : t.title;
  return /*#__PURE__*/React.createElement("div", {
    className: ["bss-callout", `bss-callout--${tone}`, className].filter(Boolean).join(" ")
  }, /*#__PURE__*/React.createElement("span", {
    className: "bss-callout__glyph",
    "aria-hidden": "true"
  }, icon || t.glyph), /*#__PURE__*/React.createElement("div", {
    style: {
      minWidth: 0
    }
  }, heading && /*#__PURE__*/React.createElement("div", {
    className: "bss-callout__label"
  }, heading), /*#__PURE__*/React.createElement("div", {
    className: "bss-callout__body"
  }, children)));
}
Object.assign(__ds_scope, { Callout });
})(); } catch (e) { __ds_ns.__errors.push({ path: "components/feedback/Callout.jsx", error: String((e && e.message) || e) }); }

// components/feedback/Drawer.jsx
try { (() => {
const {
  useEffect
} = React; // Basis Drawer — right-side slide-over panel. Used for EvidenceDrawer, filters,
// detail inspection. Scrim + panel, Esc / click-outside / close button.
let _injected = false;
function injectCSS() {
  if (_injected || typeof document === "undefined") return;
  _injected = true;
  const css = `
.bss-drawer__scrim{position:fixed;inset:0;z-index:500;display:flex;justify-content:flex-end;
  background:var(--bg-overlay);backdrop-filter:blur(4px);}
.bss-drawer{height:100%;width:100%;max-width:420px;background:var(--bg-overlay-srf);border-left:1px solid var(--border-strong);
  box-shadow:var(--shadow-xl);display:flex;flex-direction:column;animation:bss-drawer-in var(--motion-base) var(--ease-out);}
@keyframes bss-drawer-in{from{transform:translateX(24px);opacity:.4;}to{transform:translateX(0);opacity:1;}}
@media (prefers-reduced-motion: reduce){.bss-drawer{animation:none;}}
.bss-drawer__head{display:flex;align-items:center;justify-content:space-between;padding:16px 20px;border-bottom:1px solid var(--border-subtle);}
.bss-drawer__title{font-family:var(--font-display);font-size:17px;font-weight:var(--fw-semibold);color:var(--text-primary);margin:0;}
.bss-drawer__body{padding:16px 20px;overflow-y:auto;flex:1;color:var(--text-secondary);font-size:14px;line-height:1.55;}
.bss-drawer__x{display:inline-flex;align-items:center;justify-content:center;width:32px;height:32px;border:0;background:transparent;
  color:var(--text-secondary);border-radius:var(--radius-sm);cursor:pointer;}
.bss-drawer__x:hover{background:var(--accent-soft);color:var(--text-primary);}
.bss-drawer__x:focus-visible{outline:none;box-shadow:var(--shadow-focus);}
`;
  const el = document.createElement("style");
  el.setAttribute("data-bss", "drawer");
  el.textContent = css;
  document.head.appendChild(el);
}
injectCSS();
function Drawer({
  open,
  onClose,
  title,
  children,
  maxWidth = 420
}) {
  injectCSS();
  useEffect(() => {
    if (!open) return;
    const onKey = e => {
      if (e.key === "Escape") onClose && onClose();
    };
    document.addEventListener("keydown", onKey);
    return () => document.removeEventListener("keydown", onKey);
  }, [open, onClose]);
  if (!open) return null;
  return /*#__PURE__*/React.createElement("div", {
    className: "bss-drawer__scrim",
    onMouseDown: e => {
      if (e.target === e.currentTarget) onClose && onClose();
    }
  }, /*#__PURE__*/React.createElement("div", {
    role: "dialog",
    "aria-modal": "true",
    "aria-label": typeof title === "string" ? title : undefined,
    className: "bss-drawer",
    style: {
      maxWidth
    }
  }, /*#__PURE__*/React.createElement("div", {
    className: "bss-drawer__head"
  }, /*#__PURE__*/React.createElement("h3", {
    className: "bss-drawer__title"
  }, title), /*#__PURE__*/React.createElement("button", {
    type: "button",
    className: "bss-drawer__x",
    "aria-label": "\u0417\u0430\u043A\u0440\u044B\u0442\u044C",
    onClick: onClose
  }, /*#__PURE__*/React.createElement("svg", {
    width: "16",
    height: "16",
    viewBox: "0 0 16 16",
    "aria-hidden": "true"
  }, /*#__PURE__*/React.createElement("path", {
    d: "M3 3l10 10M13 3L3 13",
    stroke: "currentColor",
    strokeWidth: "1.5",
    strokeLinecap: "round"
  })))), /*#__PURE__*/React.createElement("div", {
    className: "bss-drawer__body"
  }, children)));
}
Object.assign(__ds_scope, { Drawer });
})(); } catch (e) { __ds_ns.__errors.push({ path: "components/feedback/Drawer.jsx", error: String((e && e.message) || e) }); }

// components/feedback/EmptyState.jsx
try { (() => {
// Basis EmptyState — calm, instructive empty / zero-data state.
let _injected = false;
function injectCSS() {
  if (_injected || typeof document === "undefined") return;
  _injected = true;
  const css = `
.bss-empty{display:flex;flex-direction:column;align-items:center;text-align:center;gap:8px;padding:40px 24px;}
.bss-empty__icon{color:var(--text-tertiary);margin-bottom:4px;}
.bss-empty__title{font-family:var(--font-sans);font-size:15px;font-weight:var(--fw-semibold);color:var(--text-primary);}
.bss-empty__desc{font-size:13px;color:var(--text-secondary);max-width:42ch;line-height:1.55;}
.bss-empty__action{margin-top:8px;}
`;
  const el = document.createElement("style");
  el.setAttribute("data-bss", "empty");
  el.textContent = css;
  document.head.appendChild(el);
}
injectCSS();
function EmptyState({
  icon,
  title,
  description,
  action,
  className = ""
}) {
  injectCSS();
  return /*#__PURE__*/React.createElement("div", {
    className: ["bss-empty", className].filter(Boolean).join(" ")
  }, icon && /*#__PURE__*/React.createElement("div", {
    className: "bss-empty__icon",
    "aria-hidden": "true"
  }, icon), title && /*#__PURE__*/React.createElement("div", {
    className: "bss-empty__title"
  }, title), description && /*#__PURE__*/React.createElement("div", {
    className: "bss-empty__desc"
  }, description), action && /*#__PURE__*/React.createElement("div", {
    className: "bss-empty__action"
  }, action));
}
Object.assign(__ds_scope, { EmptyState });
})(); } catch (e) { __ds_ns.__errors.push({ path: "components/feedback/EmptyState.jsx", error: String((e && e.message) || e) }); }

// components/feedback/Modal.jsx
try { (() => {
const {
  useEffect,
  useRef
} = React; // Basis Modal — scrim + centered overlay panel. Esc to close, click-outside, close button.
let _injected = false;
function injectCSS() {
  if (_injected || typeof document === "undefined") return;
  _injected = true;
  const css = `
.bss-modal__scrim{position:fixed;inset:0;z-index:500;display:flex;align-items:center;justify-content:center;padding:16px;
  background:var(--bg-overlay);backdrop-filter:blur(4px);}
.bss-modal{width:100%;max-width:440px;background:var(--bg-overlay-srf);border:1px solid var(--border-subtle);
  border-radius:var(--radius-lg);box-shadow:var(--shadow-xl);outline:none;overflow:hidden;}
.bss-modal__head{display:flex;align-items:center;justify-content:space-between;padding:16px 20px;border-bottom:1px solid var(--border-subtle);}
.bss-modal__title{font-family:var(--font-display);font-size:18px;font-weight:var(--fw-semibold);color:var(--text-primary);margin:0;}
.bss-modal__body{padding:16px 20px;color:var(--text-secondary);font-size:14px;line-height:1.55;}
.bss-modal__foot{display:flex;justify-content:flex-end;gap:8px;padding:16px 20px;border-top:1px solid var(--border-subtle);}
.bss-modal__x{display:inline-flex;align-items:center;justify-content:center;width:32px;height:32px;border:0;background:transparent;
  color:var(--text-secondary);border-radius:var(--radius-sm);cursor:pointer;}
.bss-modal__x:hover{background:var(--accent-soft);color:var(--text-primary);}
.bss-modal__x:focus-visible{outline:none;box-shadow:var(--shadow-focus);}
`;
  const el = document.createElement("style");
  el.setAttribute("data-bss", "modal");
  el.textContent = css;
  document.head.appendChild(el);
}
injectCSS();
function Modal({
  open,
  onClose,
  title,
  children,
  footer = null,
  maxWidth = 440
}) {
  injectCSS();
  const panelRef = useRef(null);
  useEffect(() => {
    if (!open) return;
    const onKey = e => {
      if (e.key === "Escape") onClose && onClose();
    };
    document.addEventListener("keydown", onKey);
    return () => document.removeEventListener("keydown", onKey);
  }, [open, onClose]);
  if (!open) return null;
  return /*#__PURE__*/React.createElement("div", {
    className: "bss-modal__scrim",
    onMouseDown: e => {
      if (e.target === e.currentTarget) onClose && onClose();
    }
  }, /*#__PURE__*/React.createElement("div", {
    ref: panelRef,
    role: "dialog",
    "aria-modal": "true",
    "aria-label": typeof title === "string" ? title : undefined,
    tabIndex: -1,
    className: "bss-modal",
    style: {
      maxWidth
    }
  }, /*#__PURE__*/React.createElement("div", {
    className: "bss-modal__head"
  }, /*#__PURE__*/React.createElement("h3", {
    className: "bss-modal__title"
  }, title), /*#__PURE__*/React.createElement("button", {
    type: "button",
    className: "bss-modal__x",
    "aria-label": "\u0417\u0430\u043A\u0440\u044B\u0442\u044C",
    onClick: onClose
  }, /*#__PURE__*/React.createElement("svg", {
    width: "16",
    height: "16",
    viewBox: "0 0 16 16",
    "aria-hidden": "true"
  }, /*#__PURE__*/React.createElement("path", {
    d: "M3 3l10 10M13 3L3 13",
    stroke: "currentColor",
    strokeWidth: "1.5",
    strokeLinecap: "round"
  })))), /*#__PURE__*/React.createElement("div", {
    className: "bss-modal__body"
  }, children), footer && /*#__PURE__*/React.createElement("div", {
    className: "bss-modal__foot"
  }, footer)));
}
Object.assign(__ds_scope, { Modal });
})(); } catch (e) { __ds_ns.__errors.push({ path: "components/feedback/Modal.jsx", error: String((e && e.message) || e) }); }

// components/feedback/Skeleton.jsx
try { (() => {
// Basis Skeleton — quiet loading placeholder with a gentle shimmer.
let _injected = false;
function injectCSS() {
  if (_injected || typeof document === "undefined") return;
  _injected = true;
  const css = `
.bss-skel{display:block;background:linear-gradient(90deg,var(--bg-surface) 25%,var(--bg-hover) 37%,var(--bg-surface) 63%);
  background-size:400% 100%;animation:bss-shimmer 1.4s ease infinite;border-radius:var(--radius-xs);}
@keyframes bss-shimmer{0%{background-position:100% 0;}100%{background-position:0 0;}}
@media (prefers-reduced-motion: reduce){.bss-skel{animation:none;}}
`;
  const el = document.createElement("style");
  el.setAttribute("data-bss", "skeleton");
  el.textContent = css;
  document.head.appendChild(el);
}
injectCSS();
function Skeleton({
  width = "100%",
  height = 16,
  radius,
  circle = false,
  className = "",
  style
}) {
  injectCSS();
  const r = circle ? "9999px" : radius;
  return /*#__PURE__*/React.createElement("span", {
    className: ["bss-skel", className].filter(Boolean).join(" "),
    "aria-hidden": "true",
    style: {
      width: circle ? height : width,
      height,
      borderRadius: r,
      ...style
    }
  });
}
Object.assign(__ds_scope, { Skeleton });
})(); } catch (e) { __ds_ns.__errors.push({ path: "components/feedback/Skeleton.jsx", error: String((e && e.message) || e) }); }

// components/layout/Card.jsx
try { (() => {
function _extends() { return _extends = Object.assign ? Object.assign.bind() : function (n) { for (var e = 1; e < arguments.length; e++) { var t = arguments[e]; for (var r in t) ({}).hasOwnProperty.call(t, r) && (n[r] = t[r]); } return n; }, _extends.apply(null, arguments); }
// Basis Card — the signature white tile floating on the cream background.
// 1px strong border + soft layered shadow; hover deepens both (depth, not movement).
let _injected = false;
function injectCSS() {
  if (_injected || typeof document === "undefined") return;
  _injected = true;
  const css = `
.bss-card{background:var(--bg-elevated);border:1px solid var(--border-strong);border-radius:var(--radius-md);
  box-shadow:var(--shadow-md);overflow:hidden;transition:box-shadow var(--motion-fast),border-color var(--motion-fast);}
.bss-card--hover:hover{box-shadow:var(--shadow-lg);border-color:var(--border-hover);}
.bss-card__header{padding:12px 16px;border-bottom:1px solid var(--border-subtle);color:var(--text-primary);
  font-family:var(--font-sans);font-weight:var(--fw-medium);font-size:14px;}
.bss-card__body{padding:16px;}
.bss-card__footer{padding:12px 16px;border-top:1px solid var(--border-subtle);color:var(--text-secondary);font-size:13px;}
`;
  const el = document.createElement("style");
  el.setAttribute("data-bss", "card");
  el.textContent = css;
  document.head.appendChild(el);
}
injectCSS();
function Card({
  children,
  header = null,
  footer = null,
  hover = false,
  padded = true,
  className = "",
  ...rest
}) {
  injectCSS();
  const cls = ["bss-card", hover && "bss-card--hover", className].filter(Boolean).join(" ");
  return /*#__PURE__*/React.createElement("div", _extends({
    className: cls
  }, rest), header && /*#__PURE__*/React.createElement("div", {
    className: "bss-card__header"
  }, header), padded ? /*#__PURE__*/React.createElement("div", {
    className: "bss-card__body"
  }, children) : children, footer && /*#__PURE__*/React.createElement("div", {
    className: "bss-card__footer"
  }, footer));
}
Object.assign(__ds_scope, { Card });
})(); } catch (e) { __ds_ns.__errors.push({ path: "components/layout/Card.jsx", error: String((e && e.message) || e) }); }

// components/layout/MetricCard.jsx
try { (() => {
const {
  useId
} = React;
// Basis MetricCard — eyebrow caption / large light display value / delta / optional sparkline.
// The Tremor-style compact analytical summary tile.
let _injected = false;
function injectCSS() {
  if (_injected || typeof document === "undefined") return;
  _injected = true;
  const css = `
.bss-metric{display:flex;flex-direction:column;gap:6px;background:var(--bg-elevated);border:1px solid var(--border-strong);
  border-radius:var(--radius-md);box-shadow:var(--shadow-sm);padding:16px;}
.bss-metric__cap{font-family:var(--font-sans);font-size:12px;font-weight:var(--fw-medium);text-transform:uppercase;
  letter-spacing:var(--ls-eyebrow);color:var(--text-tertiary);}
.bss-metric__val{display:flex;align-items:baseline;gap:4px;}
.bss-metric__num{font-family:var(--font-display);font-weight:var(--fw-light);color:var(--text-primary);
  font-size:32px;line-height:1;letter-spacing:var(--ls-display);font-variant-numeric:lining-nums tabular-nums;}
.bss-metric__unit{font-size:14px;color:var(--text-tertiary);}
`;
  const el = document.createElement("style");
  el.setAttribute("data-bss", "metric");
  el.textContent = css;
  document.head.appendChild(el);
}
injectCSS();
function Sparkline({
  data = [],
  width = 96,
  height = 32,
  sign
}) {
  const uid = useId();
  if (!data.length) return null;
  const min = Math.min(...data),
    max = Math.max(...data),
    span = max - min || 1;
  const pad = 3,
    inner = height - pad * 2,
    step = width / (data.length - 1 || 1);
  const coords = data.map((v, i) => [+(i * step).toFixed(2), +(pad + inner - (v - min) / span * inner).toFixed(2)]);
  const line = coords.map(([x, y]) => `${x},${y}`).join(" ");
  const area = `0,${height} ${line} ${width},${height}`;
  const [lx, ly] = coords[coords.length - 1];
  const rising = sign === undefined || sign === null ? data[data.length - 1] >= data[0] : sign >= 0;
  const color = rising ? "var(--success)" : "var(--danger)";
  const gradId = `bss-spark-${uid}`;
  return /*#__PURE__*/React.createElement("svg", {
    width: width,
    height: height,
    viewBox: `0 0 ${width} ${height}`,
    "aria-hidden": "true",
    style: {
      display: "block"
    }
  }, /*#__PURE__*/React.createElement("defs", null, /*#__PURE__*/React.createElement("linearGradient", {
    id: gradId,
    x1: "0",
    y1: "0",
    x2: "0",
    y2: "1"
  }, /*#__PURE__*/React.createElement("stop", {
    offset: "0%",
    stopColor: color,
    stopOpacity: "0.18"
  }), /*#__PURE__*/React.createElement("stop", {
    offset: "100%",
    stopColor: color,
    stopOpacity: "0"
  }))), /*#__PURE__*/React.createElement("polygon", {
    points: area,
    fill: `url(#${gradId})`
  }), /*#__PURE__*/React.createElement("polyline", {
    points: line,
    fill: "none",
    stroke: color,
    strokeWidth: "1.5",
    strokeLinecap: "round",
    strokeLinejoin: "round"
  }), /*#__PURE__*/React.createElement("circle", {
    cx: lx,
    cy: ly,
    r: "2",
    fill: color
  }));
}
function MetricCard({
  caption,
  value,
  unit,
  delta,
  deltaSuffix = "%",
  spark,
  className = ""
}) {
  injectCSS();
  return /*#__PURE__*/React.createElement("div", {
    className: ["bss-metric", className].filter(Boolean).join(" ")
  }, /*#__PURE__*/React.createElement("div", {
    className: "bss-metric__cap"
  }, caption), /*#__PURE__*/React.createElement("div", {
    className: "bss-metric__val"
  }, /*#__PURE__*/React.createElement("span", {
    className: "bss-metric__num"
  }, value), unit && /*#__PURE__*/React.createElement("span", {
    className: "bss-metric__unit"
  }, unit)), delta !== undefined && delta !== null && /*#__PURE__*/React.createElement("div", {
    style: {
      fontSize: 14
    }
  }, /*#__PURE__*/React.createElement(__ds_scope.Delta, {
    value: delta,
    suffix: deltaSuffix
  })), spark && /*#__PURE__*/React.createElement("div", {
    style: {
      marginTop: 4
    }
  }, /*#__PURE__*/React.createElement(Sparkline, {
    data: spark,
    sign: delta
  })));
}
Object.assign(__ds_scope, { MetricCard });
})(); } catch (e) { __ds_ns.__errors.push({ path: "components/layout/MetricCard.jsx", error: String((e && e.message) || e) }); }

// ui_kits/shell.js
try { (() => {
// Basis UI-kit shared shell — 64px icon sidebar + scrolling work area + view header.
// Loaded as text/babel; exposes window.BasisShell = { AppShell, ViewHeader }.
(function () {
  const NAV = [{
    key: "market",
    label: "Рынок",
    icon: "M3 13l4-4 3 3 6-7 2 2",
    box: "grid"
  }, {
    key: "observer",
    label: "Обозреватель",
    icon: "compass"
  }, {
    key: "portfolio",
    label: "Портфель",
    icon: "pie"
  }, {
    key: "bonds",
    label: "Облигации",
    icon: "layers"
  }, {
    key: "screening",
    label: "Скрининг",
    icon: "filter"
  }];
  function Icon({
    kind
  }) {
    const s = {
      width: 22,
      height: 22,
      viewBox: "0 0 24 24",
      fill: "none",
      stroke: "currentColor",
      strokeWidth: 1.7,
      strokeLinecap: "round",
      strokeLinejoin: "round"
    };
    switch (kind) {
      case "grid":
        return /*#__PURE__*/React.createElement("svg", s, /*#__PURE__*/React.createElement("path", {
          d: "M4 13l4-4 3 3 6-7"
        }), /*#__PURE__*/React.createElement("path", {
          d: "M4 20h16",
          opacity: "0.4"
        }), /*#__PURE__*/React.createElement("path", {
          d: "M4 4v16",
          opacity: "0.4"
        }));
      case "compass":
        return /*#__PURE__*/React.createElement("svg", s, /*#__PURE__*/React.createElement("circle", {
          cx: "12",
          cy: "12",
          r: "9"
        }), /*#__PURE__*/React.createElement("path", {
          d: "M15.5 8.5l-2 5-5 2 2-5z"
        }));
      case "pie":
        return /*#__PURE__*/React.createElement("svg", s, /*#__PURE__*/React.createElement("path", {
          d: "M12 3a9 9 0 1 0 9 9h-9z"
        }), /*#__PURE__*/React.createElement("path", {
          d: "M12 3v9h9",
          opacity: "0.5"
        }));
      case "layers":
        return /*#__PURE__*/React.createElement("svg", s, /*#__PURE__*/React.createElement("path", {
          d: "M12 3l9 5-9 5-9-5z"
        }), /*#__PURE__*/React.createElement("path", {
          d: "M3 13l9 5 9-5",
          opacity: "0.5"
        }));
      case "filter":
        return /*#__PURE__*/React.createElement("svg", s, /*#__PURE__*/React.createElement("path", {
          d: "M3 5h18l-7 8v5l-4 2v-7z"
        }));
      default:
        return /*#__PURE__*/React.createElement("svg", s, /*#__PURE__*/React.createElement("circle", {
          cx: "12",
          cy: "12",
          r: "8"
        }));
    }
  }
  function AppShell({
    active = "market",
    children
  }) {
    const railStyle = {
      width: 64,
      flexShrink: 0,
      background: "var(--bg-base)",
      borderRight: "1px solid var(--border-subtle)",
      display: "flex",
      flexDirection: "column",
      alignItems: "center",
      padding: "12px 0",
      gap: 4
    };
    const navBtn = a => ({
      width: 44,
      height: 44,
      display: "flex",
      alignItems: "center",
      justifyContent: "center",
      borderRadius: "var(--radius-sm)",
      border: 0,
      cursor: "pointer",
      background: a ? "var(--accent-soft)" : "transparent",
      color: a ? "var(--accent)" : "var(--sidebar-icon-idle, var(--text-tertiary))"
    });
    return /*#__PURE__*/React.createElement("div", {
      style: {
        display: "flex",
        height: "100vh",
        overflow: "hidden"
      }
    }, /*#__PURE__*/React.createElement("nav", {
      style: railStyle,
      "aria-label": "\u041D\u0430\u0432\u0438\u0433\u0430\u0446\u0438\u044F"
    }, /*#__PURE__*/React.createElement("a", {
      href: "#",
      style: {
        marginBottom: 8
      },
      "aria-label": "Basis"
    }, /*#__PURE__*/React.createElement("img", {
      src: "../../assets/logomark.svg",
      width: "30",
      height: "30",
      alt: "Basis"
    })), NAV.map(n => /*#__PURE__*/React.createElement("button", {
      key: n.key,
      style: navBtn(n.key === active),
      title: n.label,
      "aria-label": n.label,
      "aria-current": n.key === active || undefined
    }, /*#__PURE__*/React.createElement(Icon, {
      kind: n.box || n.icon
    }))), /*#__PURE__*/React.createElement("div", {
      style: {
        flex: 1
      }
    }), /*#__PURE__*/React.createElement("button", {
      style: navBtn(false),
      title: "\u041F\u0440\u043E\u0444\u0438\u043B\u044C",
      "aria-label": "\u041F\u0440\u043E\u0444\u0438\u043B\u044C"
    }, /*#__PURE__*/React.createElement("svg", {
      width: "22",
      height: "22",
      viewBox: "0 0 24 24",
      fill: "none",
      stroke: "currentColor",
      strokeWidth: "1.7",
      strokeLinecap: "round"
    }, /*#__PURE__*/React.createElement("circle", {
      cx: "12",
      cy: "8",
      r: "3.4"
    }), /*#__PURE__*/React.createElement("path", {
      d: "M5 20c1.5-3.5 4-5 7-5s5.5 1.5 7 5"
    })))), /*#__PURE__*/React.createElement("main", {
      style: {
        flex: 1,
        overflowY: "auto",
        padding: "32px 40px",
        minWidth: 0
      }
    }, /*#__PURE__*/React.createElement("div", {
      style: {
        maxWidth: 1180,
        margin: "0 auto"
      }
    }, children)));
  }
  function ViewHeader({
    title,
    subtitle,
    actions
  }) {
    return /*#__PURE__*/React.createElement("div", {
      style: {
        display: "flex",
        alignItems: "flex-start",
        justifyContent: "space-between",
        gap: 16,
        marginBottom: 24
      }
    }, /*#__PURE__*/React.createElement("div", null, /*#__PURE__*/React.createElement("h1", {
      style: {
        fontFamily: "var(--font-display)",
        fontSize: 22,
        fontWeight: 700,
        color: "var(--text-primary)",
        margin: "0 0 4px"
      }
    }, title), subtitle && /*#__PURE__*/React.createElement("p", {
      style: {
        fontSize: 13,
        color: "var(--text-secondary)",
        margin: 0
      }
    }, subtitle)), actions && /*#__PURE__*/React.createElement("div", {
      style: {
        display: "flex",
        gap: 8,
        flexShrink: 0
      }
    }, actions));
  }
  window.BasisShell = {
    AppShell,
    ViewHeader
  };
})();
})(); } catch (e) { __ds_ns.__errors.push({ path: "ui_kits/shell.js", error: String((e && e.message) || e) }); }

__ds_ns.BondRiskScoreCard = __ds_scope.BondRiskScoreCard;

__ds_ns.ConfidenceBadge = __ds_scope.ConfidenceBadge;

__ds_ns.ExecutiveSummaryCard = __ds_scope.ExecutiveSummaryCard;

__ds_ns.FactEstimateJudgmentTag = __ds_scope.FactEstimateJudgmentTag;

__ds_ns.FactorImpactCard = __ds_scope.FactorImpactCard;

__ds_ns.KeyTakeaway = __ds_scope.KeyTakeaway;

__ds_ns.MacroTransmissionCard = __ds_scope.MacroTransmissionCard;

__ds_ns.MetricExplainer = __ds_scope.MetricExplainer;

__ds_ns.RISK_TYPES = __ds_scope.RISK_TYPES;

__ds_ns.RiskBadge = __ds_scope.RiskBadge;

__ds_ns.ScenarioTabs = __ds_scope.ScenarioTabs;

__ds_ns.SourceTag = __ds_scope.SourceTag;

__ds_ns.Badge = __ds_scope.Badge;

__ds_ns.Button = __ds_scope.Button;

__ds_ns.Chip = __ds_scope.Chip;

__ds_ns.IconButton = __ds_scope.IconButton;

__ds_ns.Input = __ds_scope.Input;

__ds_ns.Select = __ds_scope.Select;

__ds_ns.Toggle = __ds_scope.Toggle;

__ds_ns.Tooltip = __ds_scope.Tooltip;

__ds_ns.DataTable = __ds_scope.DataTable;

__ds_ns.Delta = __ds_scope.Delta;

__ds_ns.Callout = __ds_scope.Callout;

__ds_ns.Drawer = __ds_scope.Drawer;

__ds_ns.EmptyState = __ds_scope.EmptyState;

__ds_ns.Modal = __ds_scope.Modal;

__ds_ns.Skeleton = __ds_scope.Skeleton;

__ds_ns.Card = __ds_scope.Card;

__ds_ns.MetricCard = __ds_scope.MetricCard;

})();

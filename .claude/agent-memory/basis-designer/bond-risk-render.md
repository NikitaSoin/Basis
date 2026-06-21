---
name: bond-risk-render
description: BondRiskAnalysis component — structured render of bond yield-vs-risk analysis from canonical markdown v1.2; lives in src/design/bondrisk.jsx; replaces AnalystProse for qualitative_md field
metadata:
  type: project
---

Component `BondRiskAnalysis` at `frontend/Basis/src/design/bondrisk.jsx` replaces `<AnalystProse md={y.qualitative_md}/>` in the bond card (4 places in App.js, tab `yield_risk`).

**Detection:** canonical v1.2 = md contains `## ВЕРДИКТ {light:`. Legacy (116 old analyses) falls through to `AnalystProseFallback` (same ReactMarkdown).

**Parsing strategy:** split md on `^## ` lines → named sections by title keyword. Inline tokens `{факт}`, `{оценка}`, `{суждение}`, `{warn}`, `{light:X}`, `{score:N}` stripped from display text; decoded to badges/colors.

**Score color convention (INVERTED — high score = bad):**
- 1–2 → success (green) = good block
- 3 → warning (yellow) = moderate
- 4–5 → danger (red) = problem block

**Floor 1 (always visible):** VerdictBanner, ArithmeticBlock, ArgumentsBlock, LossCheckBlock, TriggersBlock.
**Floor 2 (Disclosure, collapsed):** SubBlock A–F + AssemblyBlock. Sources also in Disclosure.

**Why:** canonical fixture is `backend/bond_issuers/уральская-сталь/risk.md`. All styles use tw- tokens, no hex. Both themes work.

---
name: bank-financials-fields
description: Маппинг полей bank_pnl/bank_metrics/balance_sheet по банкам SBER/VTBR/BSPB — именования отличаются
metadata:
  type: project
---

## bank_pnl — именования варьируются

| Логическое поле | SBER | VTBR | Фолбэк |
|---|---|---|---|
| Процентные доходы | interest_income_gross | total_interest_income | interest_income |
| Процентные расходы | interest_expense_gross | interest_expense | — |
| Комиссионные доходы | fee_income_gross | — | fee_income |
| Нормализованная ЧП | — (в adjusted) | net_profit_adj | — |

Всегда используй `ga(bp, 'primary') || ga(bp, 'fallback')` цепочку.

## bank_metrics — именования варьируются

| Поле | SBER | VTBR | BSPB |
|---|---|---|---|
| Н1.0 | capital_adequacy | capital_adequacy | capital_adequacy_n10 |
| Н1.2 | — | — | capital_adequacy_n12 |
| ROE норм. | — | roe_adjusted | — |

## balance_sheet — банковские поля

SBER: loans_to_clients_net, cash_and_equivalents, securities, deposits_retail, deposits_corporate
BSPB: loan_portfolio_gross, client_deposits
Всегда: book_value_per_share (в ₽ на акцию, НЕ миллионах — использовать formatNumber, не fmtBig!)

**Why:** fmtBig(369) → "369 млн" — некорректно для per-share значений.
**How to apply:** для BVPS всегда fmt: (v) => formatNumber(v, { decimals: 2 })

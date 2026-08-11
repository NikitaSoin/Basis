#!/usr/bin/env python3
"""Единая конвенция знаков в строках отчётности.

🔴 ЗАЧЕМ. Одна и та же строка на двух карточках выглядела по-разному: «Себестоимость
135 053» у одной компании и «Себестоимость −10 046» у другой, «Налог на прибыль 5 962»
и «−5 962». Читатель не может понять, вычитается величина или прибавляется, и глазами
проверить «прибыль до налога минус налог = чистая» невозможно. Это не косметика: именно
на таких стыках платформа теряет доверие.

Конвенции (выбраны по большинству и по смыслу подписи строки):
  • себестоимость, финансовые расходы, амортизация, капзатраты — ПОЛОЖИТЕЛЬНАЯ величина
    расхода. Знак «минус» на экране рисует фронт, а не база;
  • налог на прибыль — ПОЛОЖИТЕЛЬНЫЙ значит расход, ОТРИЦАТЕЛЬНЫЙ значит льгота
    (движение отложенных налогов в пользу компании). Это единственная строка, где знак
    несёт смысл, поэтому она нормализуется не «по модулю», а по ТОЖДЕСТВУ:
    прибыль до налога − налог = чистая прибыль.

🔴 Осторожность: налог разворачиваем ТОЛЬКО там, где тождество однозначно говорит, что
карточка ведётся в обратной конвенции. Если по годам однозначного ответа нет (например,
налог всюду нулевой или прибыль не заполнена) — не трогаем: угадывать знак вслепую
опаснее, чем оставить как есть.

Запуск: python3 backend/scripts/normalize_signs.py [--apply]
"""
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
COMPANIES = ROOT / "backend" / "companies"

# строка → в каком блоке лежит
POSITIVE_ROWS = [("income_statement", "cogs"), ("income_statement", "finance_costs"),
                 ("income_statement", "da"), ("cash_flow", "capex")]


def tax_convention(card):
    """'A' — положительный налог это расход; 'B' — наоборот; None — не определить."""
    ins = card.get("income_statement") or {}
    years = (card.get("meta") or {}).get("fiscal_years") or []
    pre, tax, net = ins.get("pre_tax_profit"), ins.get("income_tax"), ins.get("net_profit")
    if not all(isinstance(x, list) for x in (pre, tax, net)):
        return None
    a = b = 0
    for i in range(min(len(years), len(pre), len(tax), len(net))):
        P, T, N = pre[i], tax[i], net[i]
        if None in (P, T, N) or not T or abs(P) < 10:
            continue
        tol = max(abs(N) * 0.03, abs(P) * 0.02, 1)
        ok_a, ok_b = abs(P - T - N) <= tol, abs(P + T - N) <= tol
        if ok_a and not ok_b:
            a += 1
        elif ok_b and not ok_a:
            b += 1
    return "A" if a > b else ("B" if b > a else None)


def main():
    apply = "--apply" in sys.argv
    flipped_rows = flipped_tax = 0
    for path in sorted(COMPANIES.glob("*/financials.json")):
        card = json.loads(path.read_text())
        dirty = False
        for block, row in POSITIVE_ROWS:
            vals = (card.get(block) or {}).get(row)
            if not isinstance(vals, list):
                continue
            nums = [v for v in vals if isinstance(v, (int, float)) and v]
            if not nums or not all(v < 0 for v in nums):
                continue
            card[block][row] = [(-v if isinstance(v, (int, float)) else v) for v in vals]
            print(f"{path.parent.name}: {row} — знак развёрнут ({len(nums)} значений)")
            flipped_rows += 1
            dirty = True
        if tax_convention(card) == "B":
            ins = card["income_statement"]
            ins["income_tax"] = [(-v if isinstance(v, (int, float)) else v) for v in ins["income_tax"]]
            print(f"{path.parent.name}: налог на прибыль — конвенция развёрнута к «плюс = расход»")
            flipped_tax += 1
            dirty = True
        if dirty and apply:
            path.write_text(json.dumps(card, ensure_ascii=False, indent=2))
    print(f"\nстрок-расходов развёрнуто: {flipped_rows}; карточек с разворотом налога: {flipped_tax}"
          + ("" if apply else "  (сухой прогон)"))


if __name__ == "__main__":
    main()

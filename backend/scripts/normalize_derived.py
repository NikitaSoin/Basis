#!/usr/bin/env python3
"""Пересчёт производных строк карточки вслед за исходными.

🔴 ЗАЧЕМ. Одна и та же ошибка повторилась за день трижды: исправляешь капитал — а
«материальный капитал» рядом остаётся прежним; исправляешь денежные средства — остаётся
прежним чистый долг. Исправленная ошибка продолжает жить в соседней ячейке, и на экране
получается противоречие там, где его только что убрали. У ОГК-2 в этой строке годами
лежали суммы ОБЯЗАТЕЛЬСТВ, у ЕвроТранса материальный капитал превышал весь капитал на
15,7 млрд — обе беды именно отсюда.

Что пересчитывается и по какому правилу:
  • материальный капитал = капитал − нематериальные активы − гудвил;
  • свободный денежный поток = операционный поток − капзатраты (знак капзатрат в базе
    непоследователен, поэтому берём по модулю — см. память проекта);
  • чистый долг = краткосрочный долг + долгосрочный долг − денежные средства.

🔴 Осторожность, без которой скрипт вреден: пересчитываем ТОЛЬКО там, где известны все
слагаемые. Если у года нет нематериальных активов, прежнее значение материального
капитала может быть верным (взято из отчёта, где вычитали и что-то ещё) — его не трогаем.
Отсутствие данных не повод заменять существующее число расчётом из неполного набора.

Запуск: python3 backend/scripts/normalize_derived.py [--apply] [-v]
Без --apply — сухой прогон.
"""
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
COMPANIES = ROOT / "backend" / "companies"


def series(node, name, sec=""):
    src = node if not sec else (node.get(sec) or {})
    v = src.get(name) if isinstance(src, dict) else None
    return v if isinstance(v, list) else None


def num(x):
    return x if isinstance(x, (int, float)) and not isinstance(x, bool) else None


def normalize(card, n):
    """Возвращает список описаний изменений; карточку правит на месте."""
    bs = card.get("balance_sheet") or {}
    cf = card.get("cash_flow") or {}
    out = []

    def pad(v):
        return (list(v) + [None] * n)[:n] if isinstance(v, list) else [None] * n

    def put(node, name, vals):
        node[name] = vals

    te = pad(series(bs, "total_equity"))
    na = bs.get("non_current_assets") or {}
    intang, good = pad(series(na, "intangibles")), pad(series(na, "goodwill"))
    tg = pad(series(bs, "tangible_equity"))
    if any(x is not None for x in tg):
        changed = False
        for i in range(n):
            if num(te[i]) is None or (num(intang[i]) is None and num(good[i]) is None):
                continue
            calc = round(te[i] - (num(intang[i]) or 0) - (num(good[i]) or 0), 3)
            if tg[i] is None or abs(tg[i] - calc) > max(abs(calc) * 0.005, 0.5):
                out.append(f"материальный капитал[{i}]: {tg[i]} → {calc}")
                tg[i] = calc
                changed = True
        if changed:
            put(bs, "tangible_equity", tg)

    cfo, capex, fcf = pad(series(cf, "cfo")), pad(series(cf, "capex")), pad(series(cf, "fcf"))
    if any(x is not None for x in fcf):
        changed = False
        for i in range(n):
            if num(cfo[i]) is None or num(capex[i]) is None:
                continue
            calc = round(cfo[i] - abs(capex[i]), 3)
            if fcf[i] is None or abs(fcf[i] - calc) > max(abs(calc) * 0.03, 10):
                out.append(f"свободный поток[{i}]: {fcf[i]} → {calc}")
                fcf[i] = calc
                changed = True
        if changed:
            put(cf, "fcf", fcf)

    nd = pad(series(bs, "net_debt"))
    std, ltd = pad(series(bs, "short_term_debt")), pad(series(bs, "long_term_debt"))
    cash = pad(series(bs, "cash"))
    if any(x is not None for x in nd):
        changed = False
        for i in range(n):
            if None in (num(std[i]), num(ltd[i]), num(cash[i])):
                continue
            calc = round(std[i] + ltd[i] - cash[i], 3)
            if nd[i] is None or abs(nd[i] - calc) > max(abs(calc) * 0.03, 10):
                out.append(f"чистый долг[{i}]: {nd[i]} → {calc}")
                nd[i] = calc
                changed = True
        if changed:
            put(bs, "net_debt", nd)
    return out


def main():
    apply = "--apply" in sys.argv
    verbose = "-v" in sys.argv or "--verbose" in sys.argv
    total = cards = 0
    for path in sorted(COMPANIES.glob("*/financials.json")):
        card = json.loads(path.read_text())
        years = (card.get("meta") or {}).get("fiscal_years") or []
        if not years:
            continue
        changes = normalize(card, len(years))
        if not changes:
            continue
        cards += 1
        total += len(changes)
        print(f"{path.parent.name}: {len(changes)}")
        if verbose:
            for c in changes:
                print(f"   {c}")
        if apply:
            path.write_text(json.dumps(card, ensure_ascii=False, indent=2))
    print(f"\nитого: {total} ячеек на {cards} карточках" + ("" if apply else "  (сухой прогон)"))


if __name__ == "__main__":
    main()

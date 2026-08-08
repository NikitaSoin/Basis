#!/usr/bin/env python3
"""Перенос добытых балансовых рядов из sources/ в карточку небанковской компании.

🔴 ЗАЧЕМ. Та же болезнь, что уже дважды вскрылась на банках: report-fetcher по
контракту роли пишет в sources/ и НЕ трогает financials.json — перенос делает
диспетчер, и раньше он делался руками. В итоге у части карточек данные лежали
добытыми, а на экране стояли прочерки.

🔴 ЕДИНИЦЫ. Добытчики пишут в единицах ПЕРВОИСТОЧНИКА (у большинства эмитентов
отчётность в тысячах рублей), карточки ведутся в миллионах. Перенести «как есть» —
это ровно ошибка, которая уже случилась с валовыми кредитами Авангарда: ряд разошёлся
в 1000 раз, счётчик заполненности при этом показывал «всё хорошо». Поэтому масштаб
берётся из meta.unit ОБЕИХ сторон и ПОДТВЕРЖДАЕТСЯ эмпирически — по годам, где число
есть и там, и там. Объявленные единицы врут (у СФИ в одном файле смешаны тыс. и млн),
поэтому при расхождении объявленного с фактическим карточка пропускается целиком:
молча угадывать масштаб нельзя.

Остальные правила:
  1. ЗАПОЛНЯЕМ ТОЛЬКО ДЫРЫ. Существующее число не перетирается — оно могло быть
     выверено по первоисточнику вручную. Расхождение печатается как конфликт.
  2. Совмещение ПО ГОДАМ, а не по позиции: у карточки и добытчика разные
     fiscal_years, «по индексу» тихо сдвинуло бы всю историю.
  3. Капитал пишется в ОБА поля — плоское `total_equity` и вложенное
     `equity.total_equity`. Вкладка «Финансы» читает плоское, но рассинхрон
     оставляет в файле две версии правды (ловилось на Кармани и Совкомбанке).
  4. После переноса проверяется тождество «активы = обязательства + капитал»;
     если оно ломается — карточка не сохраняется.

Запуск: python3 backend/scripts/merge_extracted_balance.py [TICKER ...] [--apply] [-v]
Без тикеров — все небанковские. Без --apply — сухой прогон.
"""
import json
import sys
from pathlib import Path
from statistics import median

ROOT = Path(__file__).resolve().parents[2]
COMPANIES = ROOT / "backend" / "companies"

UNITS = {"млрд": 1e9, "млрд.": 1e9, "billion": 1e9,
         "млн": 1e6, "млн.": 1e6, "million": 1e6,
         "тыс": 1e3, "тыс.": 1e3, "thousand": 1e3,
         "руб": 1.0, "руб.": 1.0}

# слева — имя, которое читает FinanceTab; справа — где это лежит у добытчика
PATHS = {
    "total_assets": [("total_assets",)],
    "total_liabilities": [("total_liabilities",)],
    "total_equity": [("total_equity",), ("equity", "total_equity")],
}


def unit_mult(meta):
    raw = str((meta or {}).get("unit") or "").strip().lower()
    for token, mult in UNITS.items():
        if raw.startswith(token):
            return mult
    return None


def dig(node, path):
    for key in path:
        if not isinstance(node, dict):
            return None
        node = node.get(key)
    return node if isinstance(node, list) else None


def source_series(src_bs, field):
    for path in PATHS[field]:
        vals = dig(src_bs, path)
        if vals and any(isinstance(x, (int, float)) for x in vals):
            return vals
    return None


def as_list(value, n):
    return (list(value) + [None] * n)[:n] if isinstance(value, list) else [None] * n


def num(x):
    return x if isinstance(x, (int, float)) and not isinstance(x, bool) else None


def scale_factor(card, src, years, src_years, bs, src_bs, ticker, verbose):
    """Во сколько раз числа добытчика больше карточных. None — если доверять нельзя."""
    declared = None
    cm, sm = unit_mult(card.get("meta")), unit_mult(src.get("meta"))
    if cm and sm:
        # карточка в млн, добытчик в тыс ⇒ числа добытчика в 1000 раз крупнее ⇒ k = 1e6/1e3
        declared = cm / sm

    pairs = []
    for field in PATHS:
        s_vals = source_series(src_bs, field)
        c_vals = as_list(bs.get(field) if field != "total_equity" or isinstance(bs.get(field), list)
                         else dig(bs, ("equity", "total_equity")), len(years))
        if not s_vals:
            continue
        for j, year in enumerate(src_years):
            if year not in years or j >= len(s_vals):
                continue
            a, b = num(c_vals[years.index(year)]), num(s_vals[j])
            if a and b and abs(a) > 1e-9:
                pairs.append(b / a)

    if not pairs:
        if declared is None:
            print(f"  ✕ {ticker}: не с чем сверить масштаб и единицы не объявлены — пропускаю")
            return None
        if verbose:
            print(f"  · {ticker}: пересечения нет, беру объявленный масштаб ×{declared:g}")
        return declared

    emp = median(pairs)
    # эмпирический масштаб округляем до ближайшей степени тысячи, если он рядом с ней
    for cand in (1e-6, 1e-3, 1, 1e3, 1e6):
        if 0.97 <= emp / cand <= 1.03:
            emp = cand
            break
    else:
        print(f"  ✕ {ticker}: числа расходятся в {emp:,.3g}× — это не разница единиц, разбирать руками")
        return None

    if declared is not None and abs(declared / emp - 1) > 0.03:
        print(f"  ✕ {ticker}: объявлено ×{declared:g}, фактически ×{emp:g} — единицы в файле недостоверны, пропускаю")
        return None
    if verbose:
        print(f"  · {ticker}: масштаб ×{emp:g} (сверено по {len(pairs)} годам)")
    return emp


def merge(ticker, apply, verbose):
    cdir = COMPANIES / ticker
    card_path = cdir / "financials.json"
    src_path = cdir / "sources" / "extracted_financials.json"
    if not src_path.exists():
        return 0, 0
    card = json.loads(card_path.read_text())
    if card.get("bank_pnl") or card.get("bank_balance"):
        return 0, 0
    try:
        src = json.loads(src_path.read_text())
    except Exception as exc:
        print(f"  ✕ {ticker}: битый sources-файл ({str(exc)[:60]})")
        return 0, 0
    src_bs = src.get("balance_sheet") or {}
    src_years = src.get("fiscal_years") or (src.get("meta") or {}).get("fiscal_years") or []
    years = (card.get("meta") or {}).get("fiscal_years") or []
    if not src_years or not years:
        return 0, 0

    n = len(years)
    bs = card.setdefault("balance_sheet", {})
    before = {f: as_list(bs.get(f), n) for f in PATHS}
    # капитал в карточке может лежать только во вложенном виде
    if not any(x is not None for x in before["total_equity"]):
        before["total_equity"] = as_list(dig(bs, ("equity", "total_equity")), n)

    k = scale_factor(card, src, years, src_years, bs, src_bs, ticker, verbose)
    if k is None:
        return 0, 0

    written = conflicts = 0
    for field in PATHS:
        s_vals = source_series(src_bs, field)
        if not s_vals:
            continue
        cur = list(before[field])
        for j, year in enumerate(src_years):
            if year not in years or j >= len(s_vals):
                continue
            new = num(s_vals[j])
            if new is None:
                continue
            new = new / k
            i = years.index(year)
            old = num(cur[i])
            if old is None:
                cur[i] = round(new, 3)
                written += 1
                if verbose:
                    print(f"  {ticker} {field}[{year}] ← {cur[i]:,.0f}")
            elif abs(old - new) > max(abs(new) * 0.01, 1):
                conflicts += 1
                print(f"  ⚠ {ticker} {field}[{year}]: в карточке {old:,.0f}, у добытчика {new:,.0f} — не трогаю")
        bs[field] = cur

    # капитал в файле дублируется — держим оба поля в одном состоянии
    if isinstance(bs.get("equity"), dict) and isinstance(bs.get("total_equity"), list):
        bs["equity"]["total_equity"] = list(bs["total_equity"])

    broke = []
    for i, year in enumerate(years):
        A, L, E = (num(as_list(bs.get(f), n)[i]) for f in PATHS)
        if None in (A, L, E) or not A:
            continue
        if abs(A - L - E) > max(abs(A) * 0.01, 1):
            if not all(before[f][i] is not None for f in PATHS):   # ломается из-за переноса
                broke.append(year)
    if broke:
        print(f"  ✕ {ticker}: перенос ломает баланс за {broke} — карточка не изменена")
        return 0, conflicts

    if apply and written:
        card_path.write_text(json.dumps(card, ensure_ascii=False, indent=2))
    return written, conflicts


def main():
    args = [a for a in sys.argv[1:] if not a.startswith("-")]
    apply = "--apply" in sys.argv
    verbose = "-v" in sys.argv or "--verbose" in sys.argv
    tickers = args or sorted(p.parent.name for p in COMPANIES.glob("*/financials.json"))
    tw = tc = touched = 0
    for t in tickers:
        w, c = merge(t, apply, verbose)
        if w:
            touched += 1
            print(f"{t}: заполнено {w}")
        tw += w
        tc += c
    print(f"\nитого: заполнено {tw} значений в {touched} карточках, конфликтов {tc}"
          + ("" if apply else "  (сухой прогон)"))


if __name__ == "__main__":
    main()

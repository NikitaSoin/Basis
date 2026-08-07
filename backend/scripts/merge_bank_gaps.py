#!/usr/bin/env python3
"""Перенос добытых банковских рядов из sources/extracted_financials_gaps.json
в основной financials.json карточки.

Зачем отдельный скрипт: report-fetcher по контракту роли пишет в sources/ и НЕ
трогает financials.json — перенос делает диспетчер. Раньше это делалось руками и
данные застревали в sources/ (проверка 2026-08-07: у PRMB 31 строка баланса лежала
добытой, а часть до карточки так и не доехала).

Правила переноса (важнее самого переноса):
  1. ЗАПОЛНЯЕМ ТОЛЬКО ДЫРЫ. Существующее число в карточке не перетирается никогда —
     оно могло быть выверено вручную. Расхождение «в файле одно, у добытчика другое»
     печатается как КОНФЛИКТ и решается человеком.
  2. Ряды выравниваются ПО ГОДАМ, а не по позиции: у карточки и у добытчика разные
     fiscal_years (у Приморья 3 года, у Сбера 10) — совмещение «по индексу» тихо
     сдвинуло бы всю историю.
  3. Знак резервов приводится к конвенции карточки: если существующие значения
     положительные, отрицательное значение добытчика берётся по модулю (и наоборот).
  4. Любое записанное поле получает *_note с источником (файл + страница).

Запуск:  python3 backend/scripts/merge_bank_gaps.py TICKER [TICKER ...] [--apply]
Без --apply — сухой прогон: печатает, что бы изменилось, и ничего не пишет.
"""
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
COMPANIES = ROOT / "backend" / "companies"

# Синонимы имён: у добытчика они бывают из отчётности, в карточке — из схемы Basis.
CANON = {
    "loans_gross": ["loans_gross", "gross_loans", "loans_to_customers_gross"],
    "loans_net": ["loans_net", "net_loans"],
    "loan_provisions": ["loan_provisions", "loans_impairment_reserve"],
    "securities": ["securities", "securities_total"],
    "customer_deposits": ["customer_deposits", "deposits"],
    "due_to_banks": ["due_to_banks", "due_to_cbanks_and_credit_orgs"],
    "cash_and_equivalents": ["cash_and_equivalents", "cash_and_cb", "cash"],
    "total_assets": ["total_assets"],
    "total_liabilities": ["total_liabilities"],
    "total_equity": ["total_equity"],
}


def years_of(card, section):
    meta = card.get("meta") or {}
    return meta.get("fiscal_years") or (card.get(section) or {}).get("years") or []


def pick(section, names):
    """Первый непустой ряд среди синонимов + под каким именем он найден."""
    for nm in names:
        v = section.get(nm)
        if isinstance(v, list) and any(x is not None for x in v):
            return nm, v
    return None, None


def sign_like(existing, value):
    """Резерв в карточке может храниться со знаком минус или без — приводим к её конвенции."""
    known = [x for x in (existing or []) if isinstance(x, (int, float)) and x != 0]
    if not known or value is None:
        return value
    return -abs(value) if known[0] < 0 else abs(value)


def merge_one(ticker, apply, only_balance=False):
    cdir = COMPANIES / ticker
    card_path = cdir / "financials.json"
    # 🔴 Читаем ОБА файла добытчиков: свежий *_gaps.json и старый extracted_financials.json.
    # Второй копился месяцами и до карточек не доезжал — у пяти банков (Кармани, Авангард,
    # Приморье, РосДорБанк, МТС-Банк) там лежало по 18-31 строке баланса, пока карточка
    # показывала прочерки. Свежий файл имеет приоритет: он идёт вторым и перекрывает.
    sources = [cdir / "sources" / "extracted_financials.json",
               cdir / "sources" / "extracted_financials_gaps.json"]
    gaps = {}
    for sp in sources:
        if not sp.exists():
            continue
        part = json.loads(sp.read_text())
        for key in ("bank_balance", "bank_pnl", "ecosystem"):
            if isinstance(part.get(key), dict):
                gaps.setdefault(key, {}).update(part[key])
        for key in ("fiscal_years", "unit", "standard"):
            if part.get(key) is not None:
                gaps[key] = part[key]
        meta_years = (part.get("meta") or {}).get("fiscal_years")
        if meta_years and not gaps.get("fiscal_years"):
            gaps["fiscal_years"] = meta_years
    if not gaps:
        print(f"{ticker}: нет добытых файлов в sources/ — пропуск")
        return 0, 0
    card = json.loads(card_path.read_text())

    g_years = gaps.get("fiscal_years") or []
    written = conflicts = 0

    sections = ("bank_balance",) if only_balance else ("bank_balance", "bank_pnl", "ecosystem")
    for section in sections:
        g_sec = gaps.get(section) or {}
        if not g_sec:
            continue
        c_sec = card.setdefault(section, {})
        c_years = years_of(card, section) or g_years
        idx = {y: i for i, y in enumerate(c_years)}

        keys = CANON if section == "bank_balance" else {k: [k] for k in g_sec if not k.endswith("note")}
        for canon, names in keys.items():
            g_name, g_vals = pick(g_sec, names)
            if g_vals is None:
                continue
            c_name, c_vals = pick(c_sec, names)
            target = c_name or canon
            cur = list(c_vals) if c_vals else [None] * len(c_years)
            if len(cur) < len(c_years):
                cur += [None] * (len(c_years) - len(cur))

            for gi, year in enumerate(g_years):
                if year not in idx or gi >= len(g_vals):
                    continue
                new = g_vals[gi]
                if new is None:
                    continue
                ci = idx[year]
                old = cur[ci]
                if old is None:
                    cur[ci] = sign_like(cur, new) if "provision" in canon or "impairment" in canon else new
                    written += 1
                    print(f"  {ticker} {section}.{target}[{year}] ← {cur[ci]}")
                elif abs(float(old) - float(new)) > max(abs(float(old)) * 0.01, 1):
                    conflicts += 1
                    print(f"  ⚠ {ticker} {section}.{target}[{year}]: в карточке {old}, у добытчика {new} — НЕ трогаю")

            c_sec[target] = cur
            note = g_sec.get(f"{g_name}_note") or g_sec.get(f"{canon}_note")
            if note:
                c_sec[f"{target}_note"] = note

    if apply and written:
        card_path.write_text(json.dumps(card, ensure_ascii=False, indent=2))
    return written, conflicts


def main():
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    apply = "--apply" in sys.argv
    total_w = total_c = 0
    for t in args:
        w, c = merge_one(t, apply, only_balance="--balance-only" in sys.argv)
        total_w += w
        total_c += c
    print(f"\nитого: заполнено {total_w}, конфликтов {total_c}" + ("" if apply else "  (сухой прогон, ничего не записано)"))


if __name__ == "__main__":
    main()

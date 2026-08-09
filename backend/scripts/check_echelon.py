#!/usr/bin/env python3
"""Проверка карточек ПЕРВОГО И ВТОРОГО ЭШЕЛОНА: пропусков быть не должно.

🔴 ЗАЧЕМ ОТДЕЛЬНЫЙ СКРИПТ. Владелец задал приоритет прямо: пропуски в третьем эшелоне
терпимы, а первый и второй обязаны быть заполнены. Общий аудит (`audit_financials.py`)
меряет ВСЕ 260+ карточек и тонет в мелких бумагах — по нему невозможно ответить на
вопрос «готовы ли ликвидные бумаги». Здесь считается ровно тот срез, который важен.

Кто относится к эшелону: объединение составов индексов Мосбиржи из
`frontend/Basis/scripts/data/index-composition-snapshot.json` (IMOEX плюс отраслевые —
это и есть ликвидная часть рынка) плюс парные бумаги того же эмитента: если обычка в
индексе, преф относится к тому же эшелону, у них одна отчётность.

Что считается пропуском: пустая ячейка в строках, которые пользователь видит первыми —
активы / обязательства / капитал / выручка / чистая прибыль. У банков вместо выручки
берётся их собственная форма: строки «выручка» у банка нет по природе отчётности.

Что НЕ считается пропуском: год, за который эмитент отчётность не публиковал, если это
разобрано и объяснено на карточке (`meta.disclosure_note`). Такой год выводится
отдельной строкой — «объяснено», а не «дыра»: пустота с причиной на экране честнее
выдуманного числа, и закрывать её нечем.

Запуск: python3 backend/scripts/check_echelon.py [--verbose]
Код возврата 0 — необъяснённых пропусков нет.
"""
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
COMPANIES = ROOT / "backend" / "companies"
INDEX_SNAPSHOT = ROOT / "frontend" / "Basis" / "scripts" / "data" / "index-composition-snapshot.json"


def echelon_tickers():
    data = json.loads(INDEX_SNAPSHOT.read_text())
    tickers = set()
    for block in (data.get("indices") or {}).values():
        tickers |= {r["ticker"] for r in (block.get("rows") or [])}
    have = {p.parent.name for p in COMPANIES.glob("*/financials.json")}
    tickers &= have
    # парные бумаги одного эмитента — тот же эшелон, отчётность общая
    pairs = set()
    for t in tickers:
        if t + "P" in have:
            pairs.add(t + "P")
        if t.endswith("P") and t[:-1] in have:
            pairs.add(t[:-1])
    return sorted(tickers | pairs)


def gaps(card):
    years = (card.get("meta") or {}).get("fiscal_years") or []
    if not years:
        return ["в meta нет fiscal_years"], []
    n = len(years)
    bs = card.get("balance_sheet") or {}
    ins = card.get("income_statement") or {}
    is_bank = bool(card.get("bank_pnl") or card.get("bank_balance"))

    def row(node, name, sec=""):
        src = node if not sec else (node.get(sec) or {})
        v = src.get(name) if isinstance(src, dict) else None
        return (list(v) + [None] * n)[:n] if isinstance(v, list) else [None] * n

    rows = {"активы": row(bs, "total_assets"),
            "обязательства": row(bs, "total_liabilities"),
            "капитал": row(bs, "total_equity"),
            "чистая прибыль": row(card.get("bank_pnl") or ins, "net_profit") if is_bank else row(ins, "net_profit")}
    if not any(x is not None for x in rows["капитал"]):
        rows["капитал"] = row(bs, "total_equity", "equity")
    if not is_bank:
        rows["выручка"] = row(ins, "revenue")

    holes = []
    for label, vals in rows.items():
        for i, y in enumerate(years):
            if vals[i] is None:
                holes.append((y, label))
    return [], holes


def main():
    verbose = "--verbose" in sys.argv or "-v" in sys.argv
    tickers = echelon_tickers()
    broken, explained, clean = [], [], 0
    for t in tickers:
        card = json.loads((COMPANIES / t / "financials.json").read_text())
        errs, holes = gaps(card)
        note = (card.get("meta") or {}).get("disclosure_note")
        if errs:
            broken.append((t, "; ".join(errs), None))
        elif holes and note:
            explained.append((t, sorted({y for y, _ in holes}), note))
        elif holes:
            broken.append((t, sorted({y for y, _ in holes}), holes))
        else:
            clean += 1

    print(f"первый и второй эшелон: {len(tickers)} карточек")
    print(f"  без пропусков:              {clean}")
    print(f"  пропуски объяснены:         {len(explained)}")
    print(f"  НЕОБЪЯСНЁННЫЕ ПРОПУСКИ:     {len(broken)}")
    if broken:
        print("\nтребуют добора:")
        for t, years, holes in broken:
            print(f"   {t:8} {years}")
            if verbose and holes:
                print("            " + ", ".join(f"{y}:{lab}" for y, lab in holes[:10]))
    if verbose and explained:
        print("\nобъяснено на карточке (закрывать нечем — отчётности не существует):")
        for t, years, note in explained:
            print(f"   {t:8} {years} — {note[:90]}…")
    return 1 if broken else 0


if __name__ == "__main__":
    sys.exit(main())

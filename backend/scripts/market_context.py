#!/usr/bin/env python3
"""Рыночный контекст по тикеру из rates.csv — для подкидывания financial-analyst'у,
чтобы он НЕ ходил в веб за ценой/числом акций/капитализацией/дивидендом (всё это
уже есть в нашей БД). Выводит компактную строку.

Запуск: python -m scripts.market_context SBER
        python scripts/market_context.py SBER LKOH GAZP
"""
import csv
import io
import os
import sys

BASE = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
RATES = os.path.join(BASE, "rates.csv")
FIELDS = ["SECID", "SHORTNAME", "PRICE_RUB", "ISSUESIZE", "SECURITYCAPITALIZATION",
          "DIVIDENDVALUE", "DIVIDENDYIELD", "LOTSIZE", "FACEVALUE", "TYPENAME"]


def _num(s):
    if s is None or str(s).strip() == "":
        return None
    try:
        return float(str(s).replace("\xa0", "").replace(" ", "").replace(",", "."))
    except ValueError:
        return s


def _rows():
    with open(RATES, encoding="cp1251") as f:
        lines = f.readlines()
    hi = next(i for i, l in enumerate(lines) if l.startswith("SECID"))
    return list(csv.DictReader(io.StringIO("".join(lines[hi:])), delimiter=";"))


def context_for(ticker, rows=None):
    rows = rows or _rows()
    t = ticker.upper()
    row = next((r for r in rows if (r.get("SECID") or "").upper() == t), None)
    if not row:
        return f"{t}: НЕ НАЙДЕН в rates.csv — цену/акции возьми из веба как исключение."
    price = _num(row.get("PRICE_RUB"))
    shares = _num(row.get("ISSUESIZE"))
    cap = _num(row.get("SECURITYCAPITALIZATION"))
    div = _num(row.get("DIVIDENDVALUE"))
    dy = _num(row.get("DIVIDENDYIELD"))
    parts = [f"тикер {t} ({row.get('SHORTNAME','')})"]
    parts.append(f"цена={price} ₽" if price is not None else "цена=нет")
    parts.append(f"акций={int(shares) if isinstance(shares,(int,float)) else shares}" if shares is not None else "акций=нет")
    parts.append(f"капитализация={cap} ₽" if cap is not None else "капитализация=нет")
    parts.append(f"дивиденд={div} ₽" if div is not None else "дивиденд(rates)=нет")
    parts.append(f"див.доходность={dy}%" if dy is not None else "")
    return "; ".join(p for p in parts if p)


def main():
    if len(sys.argv) < 2:
        print("usage: market_context.py TICKER [TICKER ...]")
        return 1
    rows = _rows()
    for t in sys.argv[1:]:
        print(context_for(t, rows))
    return 0


if __name__ == "__main__":
    sys.exit(main())

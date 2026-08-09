"""Сверка блока «Дивиденды» карточек с фактическими выплатами.

🔴 ЗАЧЕМ (владелец, 2026-08-10): «часть компаний выплатила дивиденды за 2025 год, и
они не все в корпуправлении есть». Проверка подтвердила: из 26 компаний, у которых
есть выплата в 2026 году, у ВОСЬМИ год 2025 помечен как невыплаченный (`paid: false`
при заполненном dps — то есть в карточке записан ОБЪЯВЛЕННЫЙ дивиденд, который с тех
пор уже выплатили), а у трёх строки за 2025 нет вовсе.

🔴 ЧТО ЭТОТ СКРИПТ ДЕЛАЕТ И ЧЕГО НЕ ДЕЛАЕТ.
Делает: ставит `paid: true` там, где в нашей таблице выплат есть ФАКТ платежа после
даты, на которую составлялась карточка, и дописывает в note дату отсечки и сумму из
наших данных.
НЕ делает: не проставляет и не исправляет dps. Наша таблица выплат НЕПОЛНАЯ — ISS
перестал отдавать историю, свежие записи приходят из календаря, и по компании с
тремя выплатами за год у нас может лежать только последняя. Сравнивать годовой dps
карточки с нашей частичной суммой нельзя: у ТАТН в карточке 65,59 за год против
11,61 в базе — это не ошибка карточки, а наша неполнота. Молча «исправить» её
означало бы испортить верные данные хуже, чем они были.
"""
from __future__ import annotations

import argparse
import json
import os
import ssl
import sys
import urllib.parse
import urllib.request
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
COMPANIES = ROOT / "companies"

_ctx = ssl.create_default_context()
_ctx.check_hostname = False
_ctx.verify_mode = ssl.CERT_NONE


def _api() -> tuple[str, str]:
    base = os.environ.get("BASIS_API") or "https://nikitasoin-basis-a772.twc1.net"
    tok = os.environ.get("DEBUG_API_TOKEN") or ""
    if not tok:
        env = ROOT / ".env"
        if env.exists():
            for line in env.read_text(encoding="utf-8").splitlines():
                if line.startswith("DEBUG_API_TOKEN="):
                    tok = line.split("=", 1)[1].strip()
                    break
    return base.rstrip("/"), tok


def fetch_payments(since: str = "2025-06-01") -> dict[str, list[tuple[str, float]]]:
    base, tok = _api()
    q = ("SELECT ticker, record_date, amount FROM dividends "
         f"WHERE record_date >= '{since}' ORDER BY ticker, record_date")
    url = f"{base}/api/debug/sql?q={urllib.parse.quote(q)}"
    req = urllib.request.Request(url, headers={"X-Debug-Token": tok})
    with urllib.request.urlopen(req, timeout=120, context=_ctx) as r:
        data = json.loads(r.read())
    out: dict[str, list[tuple[str, float]]] = defaultdict(list)
    for row in data.get("строки") or []:
        out[row["ticker"]].append((str(row["record_date"]), float(row["amount"])))
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--write", action="store_true")
    args = ap.parse_args()

    pays = fetch_payments()
    fixed, added_note, skipped = [], [], []
    for ticker, plist in sorted(pays.items()):
        p = COMPANIES / ticker.upper() / "governance.json"
        if not p.exists():
            continue
        try:
            g = json.loads(p.read_text(encoding="utf-8"))
        except Exception:  # noqa: BLE001
            continue
        div = g.get("dividends") or {}
        hist = div.get("history") or []
        if not hist:
            skipped.append(f"{ticker}: истории дивидендов нет — не трогаю")
            continue

        last_date, last_amt = plist[-1]
        pay_year = int(last_date[:4])
        # 🔴 Отчётный год выплаты нельзя определить одной датой. Правило «платёж до
        # осени = за прошлый год» верно для большинства, но не для всех: Базис
        # выплатил в июле 2026 дивиденд, который сам же оформил «за 1 кв. 2026», и
        # эвристика уводила проверку на пустой 2025-й — расхождение попадало в
        # список «нужен аналитик», хотя карточка была права.
        # Поэтому сначала СУММА, потом дата: если у одного из двух кандидатных лет
        # записанный дивиденд сходится с фактическим платежом, это он и есть.
        by_date = pay_year - 1 if int(last_date[5:7]) <= 8 else pay_year
        candidates = [by_date, pay_year if by_date != pay_year else pay_year - 1]

        def _close(h) -> bool:
            try:
                v = float(h.get("dps"))
            except (TypeError, ValueError):
                return False
            return v > 0 and abs(v - last_amt) / max(v, last_amt) <= 0.15

        row = next((h for h in hist
                    if h.get("year") in candidates and _close(h)), None)
        fiscal = row.get("year") if row else by_date
        if row is None:
            row = next((h for h in hist if h.get("year") == fiscal), None)
        if row is None:
            skipped.append(f"{ticker}: нет строки за {fiscal} — нужен аналитик "
                           f"(выплата {last_date}, {last_amt:g} ₽)")
            continue
        was = row.get("paid")
        if was is True:
            continue
        # 🔴 Ставим «выплачено» ТОЛЬКО когда сумма в карточке сходится с фактическим
        # платежом. Это признак «рекомендация стала фактом»: в карточке лежал
        # объявленный дивиденд, и он совпал с отсечкой.
        # Иначе — к аналитику. Живой пример: у Совкомфлота в карточке «год убыточный,
        # дивиденда нет» (dps=0), а в базе платёж 4,87 ₽ 16.07.2026 — это либо выплата
        # за ДРУГОЙ год, либо ошибка одной из сторон. Пометить «выплачено» при dps=0
        # значило бы получить в карточке внутреннее противоречие: заплатили ноль.
        dps = row.get("dps")
        try:
            dps_f = float(dps) if dps is not None else 0.0
        except (TypeError, ValueError):
            dps_f = 0.0
        if dps_f <= 0 or abs(dps_f - last_amt) / max(dps_f, last_amt) > 0.15:
            skipped.append(
                f"{ticker}: в карточке за {fiscal} dps={dps}, по базе платёж "
                f"{last_amt:g} ₽ ({last_date}) — расходится, нужен аналитик")
            continue
        row["paid"] = True
        note = (row.get("note") or "").strip()
        add = (f"Выплата подтверждена: отсечка {last_date}, "
               f"{last_amt:g} ₽/акц. по данным платформы.")
        row["note"] = f"{note} {add}".strip() if note else add
        fixed.append(f"{ticker}: {fiscal} → выплачен (было paid={was!r}), "
                     f"отсечка {last_date}, {last_amt:g} ₽")
        if args.write:
            p.write_text(json.dumps(g, ensure_ascii=False, indent=2) + "\n",
                         encoding="utf-8")

    print(f"{'ИСПРАВЛЕНО' if args.write else 'БУДЕТ ИСПРАВЛЕНО (сухой прогон)'}: {len(fixed)}")
    for f in fixed:
        print("   ", f)
    print(f"требуют аналитика: {len(skipped)}")
    for s in skipped:
        print("   ", s)
    return 0


if __name__ == "__main__":
    sys.exit(main())

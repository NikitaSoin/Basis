#!/usr/bin/env python3
"""Аудит карточек: ищет те же поломки, что нашлись у банков, по всем компаниям.

Проверки (каждая уже поймала реальный дефект на банках — это не гипотетика):
  1. БАЛАНС НЕ СХОДИТСЯ: активы ≠ обязательства + капитал.
     У Кузнецкого так вскрылась подмена бухгалтерского капитала регуляторным.
  2. ЧАСТИ НЕ ДАЮТ ЦЕЛОГО: оборотные + внеоборотные ≠ итого активы.
  3. СКОПИРОВАННАЯ ИСТОРИЯ: одно и то же значение в неподряд идущих годах.
     У Кармани так нашлись 2020-2021, оказавшиеся побуквенной копией 2022-2023.
  4. РАЗЪЕХАВШИЕСЯ ЕДИНИЦЫ: значение отличается от соседнего примерно в 1000 раз.
     Так у Авангарда валовые кредиты за 2022 оказались вписаны в млн вместо млрд.
  5. ОДИН РЯД В ДВУХ СТРОКАХ: чистое больше валового (у Сбера чистые кредиты
     превышали валовые — арифметически невозможно).
  6. FCF ≠ операционный поток − капзатраты (знак capex в базе непоследователен,
     поэтому считаем через модуль — см. память проекта).
  7. ДЫРЫ: пустые ячейки в ключевых строках.

Запуск: python3 backend/scripts/audit_financials.py [--banks] [--limit N] [--ticker T]
По умолчанию — небанковские компании.
"""
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
COMPANIES = ROOT / "backend" / "companies"


def series(node, *path):
    """Достаёт ряд по вложенному пути; возвращает [] если нет."""
    cur = node
    for key in path:
        if not isinstance(cur, dict):
            return []
        cur = cur.get(key)
    return cur if isinstance(cur, list) else []


def pad(vals, n):
    return list(vals) + [None] * (n - len(vals))


def close(a, b, tol=0.01, floor=1.0):
    return abs(a - b) <= max(abs(b) * tol, floor)


def audit(card, ticker):
    """Возвращает список находок: (тяжесть, тип, текст)."""
    out = []
    meta = card.get("meta") or {}
    years = meta.get("fiscal_years") or []
    n = len(years)
    if not n:
        return [("!", "нет-лет", "в meta нет fiscal_years")]

    bs = card.get("balance_sheet") or {}
    is_bank = bool(card.get("bank_pnl") or card.get("bank_balance"))

    ta = pad(series(bs, "total_assets"), n)
    tl = pad(series(bs, "total_liabilities"), n)
    te = pad(series(bs, "total_equity"), n) or pad(series(bs, "equity", "total_equity"), n)
    if not any(x is not None for x in te):
        te = pad(series(bs, "equity", "total_equity"), n)

    # 1. активы = обязательства + капитал
    for i, y in enumerate(years):
        A, L, E = ta[i], tl[i], te[i]
        if None in (A, L, E) or A == 0:
            continue
        if not close(A, L + E, 0.01):
            out.append(("!", "баланс", f"{y}: активы {A:,.0f} ≠ обязательства {L:,.0f} + капитал {E:,.0f} (расх. {A-L-E:+,.0f})"))

    # 2. части = целое (только небанки: у банков структура иная)
    if not is_bank:
        cur = pad(series(bs, "current_assets", "total_current"), n)
        noncur = pad(series(bs, "non_current_assets", "total_non_current"), n)
        for i, y in enumerate(years):
            if None in (cur[i], noncur[i], ta[i]) or ta[i] == 0:
                continue
            if not close(cur[i] + noncur[i], ta[i], 0.02):
                out.append(("?", "части", f"{y}: оборотные {cur[i]:,.0f} + внеоборотные {noncur[i]:,.0f} ≠ активы {ta[i]:,.0f}"))

    # ряды, по которым ищем копии и скачки единиц — ВСЕ числовые ряды карточки,
    # включая вложенные (у небанков детализация лежит в current_assets/equity и т.д.).
    # Ограничиваться пятью верхнеуровневыми было мало: копии прятались в деталях.
    named = {}

    def collect(node, prefix=""):
        if not isinstance(node, dict):
            return
        for key, val in node.items():
            if key.endswith("note"):
                continue
            name = f"{prefix}{key}"
            if isinstance(val, list) and any(isinstance(x, (int, float)) for x in val):
                named[name] = pad(val, n)
            elif isinstance(val, dict):
                collect(val, f"{name}.")

    for block in ("balance_sheet", "income_statement", "cash_flow"):
        collect(card.get(block) or {}, f"{block[:2]}.")

    # 3. скопированная история.
    # Фильтры не косметика: без них проверка тонет в шуме. Коэффициенты (ratios,
    # margins) законно повторяются — «долг/капитал = 1» в двух годах это совпадение,
    # а не копия. Мелкие абсолютные величины тоже совпадают случайно, поэтому порог
    # по величине; и требуем «неслучайности» — у настоящей копии обычно есть дробная
    # часть или много значащих цифр.
    RATIO_HINTS = ("ratio", "margin", "per_share", "_pct", "yield", "turnover", "coverage")
    # Уставный капитал, эмиссионный доход и подобные статьи законно НЕ меняются годами —
    # повтор значения там норма, а не копия истории.
    STATIC_HINTS = ("share_capital", "additional_paid_in", "share_premium", "treasury")
    for name, vals in named.items():
        if any(h in name for h in RATIO_HINTS) or any(h in name for h in STATIC_HINTS):
            continue
        seen = {}
        for i, v in enumerate(vals):
            if v is None or abs(v) < 1000:
                continue
            if v in seen and i - seen[v] > 1:
                out.append(("!", "копия", f"{name}: {years[seen[v]]} и {years[i]} = {v:,.2f} — одно и то же значение в разные годы"))
            seen[v] = i

    # 4. разъехавшиеся единицы (скачок ровно на три порядка и обратно)
    for name, vals in named.items():
        for i in range(1, n):
            a, b = vals[i - 1], vals[i]
            if not a or not b:
                continue
            if abs(a) < 100 and abs(b) < 100:
                continue          # мелкие величины скачут законно (округления, разовые статьи)
            r = abs(b / a)
            if 500 <= r <= 2000 or 1 / 2000 <= r <= 1 / 500:
                out.append(("!", "единицы", f"{name}: {years[i-1]} → {years[i]} изменение в {r:,.0f}× ({a:,.0f} → {b:,.0f})"))

    # 5. чистое больше валового
    g = pad(series(bs, "gross_loans"), n)
    net = pad(series(bs, "net_loans"), n)
    for i, y in enumerate(years):
        if None in (g[i], net[i]):
            continue
        if net[i] > g[i] * 1.001:
            out.append(("!", "нетто>гросс", f"{y}: чистые {net[i]:,.0f} больше валовых {g[i]:,.0f}"))

    # 6. FCF = CFO − |capex|
    cf = card.get("cash_flow") or {}
    cfo, capex, fcf = pad(series(cf, "cfo"), n), pad(series(cf, "capex"), n), pad(series(cf, "fcf"), n)
    for i, y in enumerate(years):
        if None in (cfo[i], capex[i], fcf[i]):
            continue
        calc = cfo[i] - abs(capex[i])
        if not close(fcf[i], calc, 0.03, 10):
            out.append(("?", "fcf", f"{y}: FCF {fcf[i]:,.0f}, а поток {cfo[i]:,.0f} − капзатраты {abs(capex[i]):,.0f} = {calc:,.0f}"))

    # 7. КАПИТАЛ И ОБЯЗАТЕЛЬСТВА ПЕРЕПУТАНЫ МЕСТАМИ.
    # Найдено у ОГК-2: в капитале лежала сумма обязательств и наоборот, из-за чего
    # капитал выглядел вдвое меньше реального. Баланс при этом СХОДИТСЯ (сумма та же),
    # поэтому тест на равенство молчит — ловим по устойчивой смене знака разности.
    swaps = []
    for i, y in enumerate(years):
        A, L, E = ta[i], tl[i], te[i]
        if None in (A, L, E) or not A:
            continue
        # у обычной компании капитал обычно СРАВНИМ с обязательствами; резкая инверсия
        # относительно соседних лет — признак перестановки
        swaps.append((y, E / L if L else None))
    ratios = [r for _, r in swaps if r]
    if len(ratios) >= 4:
        flips = sum(1 for a, b in zip(ratios, ratios[1:]) if a and b and ((a > 1) != (b > 1)) and max(a / b, b / a) > 2)
        if flips >= 2:
            out.append(("?", "перестановка", f"соотношение капитала к обязательствам скачет через единицу {flips} раз — возможна перестановка строк местами"))

    # 8. ПОДОЗРИТЕЛЬНО КРУГЛЫЕ среди неокруглённых.
    # Добавлено после Глобалтрака и О'Кея: там весь набор был не из отчётности, но
    # сходился сам с собой, поэтому тест на баланс молчал. Выдаёт подмену именно
    # фактура: рядом с 117 014,3 стоит ровное 83 600 — так отчётность не выглядит.
    for name, vals in named.items():
        nums = [v for v in vals if isinstance(v, (int, float)) and abs(v) >= 1000]
        if len(nums) < 4:
            continue
        flags_round = [isinstance(v, (int, float)) and abs(v) >= 1000 and v % 100 == 0 for v in vals]
        exact = [v for v in nums if v % 100 != 0]
        # ищем непрерывную цепочку ровных значений длиной ≥3 при наличии точных рядом:
        # именно так выглядит «кусок ряда из другого источника»
        best = run = 0
        for fl in flags_round:
            run = run + 1 if fl else 0
            best = max(best, run)
        if best >= 3 and len(exact) >= 2:
            years_round = [years[i] for i, fl in enumerate(flags_round) if fl]
            out.append(("?", "круглые", f"{name}: {', '.join(map(str, years_round))} — подряд идущие ровные сотни при точных значениях в других годах (похоже на кусок ряда из другого источника)"))

    # 8. дыры в ключевых строках
    holes = sum(1 for vals in (ta, tl, te) for v in vals if v is None)
    if holes:
        out.append(("·", "дыры", f"{holes} пустых из {3*n} в строках активы/обязательства/капитал"))
    return out


def main():
    only_banks = "--banks" in sys.argv
    tick = None
    if "--ticker" in sys.argv:
        tick = sys.argv[sys.argv.index("--ticker") + 1]

    stats, all_findings = {}, []
    for path in sorted(COMPANIES.glob("*/financials.json")):
        ticker = path.parent.name
        if tick and ticker != tick:
            continue
        try:
            card = json.loads(path.read_text())
        except Exception as exc:
            all_findings.append((ticker, [("!", "битый", str(exc)[:80])]))
            continue
        is_bank = bool(card.get("bank_pnl") or card.get("bank_balance"))
        if not tick and (is_bank != only_banks):
            continue
        found = audit(card, ticker)
        if found:
            all_findings.append((ticker, found))
            for sev, kind, _ in found:
                stats[kind] = stats.get(kind, 0) + 1

    hard = [(t, f) for t, f in all_findings if any(s == "!" for s, _, _ in f)]
    print(f"проверено карточек: {'банки' if only_banks else 'небанковские'}; с находками: {len(all_findings)}, из них с грубыми: {len(hard)}\n")
    print("сводка по типам:")
    for kind, cnt in sorted(stats.items(), key=lambda x: -x[1]):
        print(f"   {kind:14} {cnt}")
    print("\nГРУБЫЕ НАХОДКИ (арифметика не сходится / данные не могли существовать):")
    for ticker, found in hard:
        heavy = [f for f in found if f[0] == "!"]
        print(f"\n{ticker}:")
        for _, kind, text in heavy[:6]:
            print(f"   [{kind}] {text}")
        if len(heavy) > 6:
            print(f"   … ещё {len(heavy)-6}")


if __name__ == "__main__":
    main()

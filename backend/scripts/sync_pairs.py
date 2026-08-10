#!/usr/bin/env python3
"""Сведение карточек обыкновенной и привилегированной акции ОДНОГО эмитента.

🔴 ЗАЧЕМ. У обычки и префа одна отчётность на двоих: активы, выручка, прибыль, потоки —
это цифры эмитента, а не бумаги. Различаться законно могут только «подушевые» строки
(дивиденд на акцию, прибыль на акцию) — их и только их этот скрипт не трогает. Всё
остальное, если расходится, — дефект: на двух карточках одной компании инвестор видит
разные числа и не понимает, какому верить.

Найдено этим сравнением (2026-08-10): у Саратовэнерго карточка префа показывала чистую
прибыль за 2022 год 640 млн ₽ при фактических 34,0; у Ставропольэнергосбыта — операционную
прибыль 763 вместо 941; у ТГК-2 активы стояли ровными числами (75 400 вместо 75 101,7);
у Волгоградэнергосбыта преф вёлся по МСФО, а обычка по РСБУ — два стандарта в одной паре.

Правило сведения (осознанно простое, чтобы не наплодить новых расхождений):
  • одна сторона пустая, другая заполнена → берём заполненную;
  • обе заполнены и совпадают по существу (в пределах 0,1%) → берём БОЛЕЕ ТОЧНУЮ
    (по числу значащих цифр): 402,754 лучше, чем 402,8;
  • обе заполнены и расходятся по существу → НЕ ТРОГАЕМ и печатаем: это спор, который
    решается по первичному отчёту, а не выбором «кто красивее».

Запуск: python3 backend/scripts/sync_pairs.py [--apply]
Без --apply — сухой прогон.
"""
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
COMPANIES = ROOT / "backend" / "companies"

# строки, которые у обычки и префа ЗАКОННО разные
SKIP = ("per_share", "dps", "eps", "dividend")
BLOCKS = ("income_statement", "balance_sheet", "cash_flow", "bank_pnl", "bank_balance")


def sig(v):
    s = f"{abs(v):.10g}".replace(".", "").rstrip("0")
    return len(s.lstrip("0")) or 1


def merge(va, vb, n, conflicts, name):
    """Поэлементно сводит два ряда; возвращает общий ряд."""
    out = []
    for i in range(n):
        a = va[i] if i < len(va) else None
        b = vb[i] if i < len(vb) else None
        if isinstance(a, (int, float)) and isinstance(b, (int, float)):
            if abs(a - b) <= max(abs(a), abs(b)) * 0.001:
                out.append(b if sig(b) > sig(a) else a)
            else:
                # 🔴 Спор НЕ решаем «по умолчанию в пользу обычки»: у Нижнекамскнефтехима
                # за 2024 год правой оказалась как раз карточка префа (краткосрочный долг
                # 119 461 против 127 700 — с числом обычки детализация превышала итог
                # раздела, чего не бывает). Автоподстановка «победителя» тихо разнесла бы
                # ошибку на вторую карточку. Помечаем и оставляем обе стороны как есть.
                conflicts.append((name, i, a, b))
                out.append(None)       # маркер «не трогать эту ячейку»
        else:
            out.append(a if a is not None else b)
    return out


def walk(sa, sb, n, conflicts, prefix=""):
    """Идёт по одинаковой структуре двух карточек и сводит все числовые ряды."""
    changed = False
    for key in set(sa) | set(sb):
        if key.endswith("note") or any(s in key for s in SKIP):
            continue
        a, b = sa.get(key), sb.get(key)
        if isinstance(a, list) and isinstance(b, list):
            if a and isinstance(a[0], dict):
                continue                # именованные статьи — сводим отдельно, не вслепую
            before = len(conflicts)
            m = merge(a, b, n, conflicts, prefix + key)
            # ячейки, попавшие в спор, возвращаем как были — каждой карточке своё
            for name, i, va, vb in conflicts[before:]:
                m[i] = None
            new_a = [va if m[i] is None else m[i] for i, va in enumerate((a + [None] * n)[:n])]
            new_b = [vb if m[i] is None else m[i] for i, vb in enumerate((b + [None] * n)[:n])]
            if new_a != a or new_b != b:
                sa[key] = new_a
                sb[key] = new_b
                changed = True
        elif isinstance(a, dict) and isinstance(b, dict):
            changed |= walk(a, b, n, conflicts, prefix + key + ".")
    return changed


def main():
    apply = "--apply" in sys.argv
    have = {p.parent.name for p in COMPANIES.glob("*/financials.json")}
    pairs = [(t[:-1], t) for t in sorted(have) if t.endswith("P") and t[:-1] in have]
    touched = 0
    for ord_t, pref_t in pairs:
        pa = COMPANIES / ord_t / "financials.json"
        pb = COMPANIES / pref_t / "financials.json"
        A, B = json.loads(pa.read_text()), json.loads(pb.read_text())
        ya, yb = A["meta"]["fiscal_years"], B["meta"]["fiscal_years"]
        if ya != yb:
            print(f"{ord_t}/{pref_t}: РАЗНЫЕ ГОДА {ya} vs {yb} — свести автоматически нельзя")
            continue
        conflicts, n = [], len(ya)
        changed = False
        for blk in BLOCKS:
            if blk in A and blk in B:
                changed |= walk(A[blk], B[blk], n, conflicts, f"{blk[:2]}.")
        if conflicts:
            print(f"{ord_t}/{pref_t}: СПОРНЫЕ значения (нужен первичный отчёт):")
            for name, i, a, b in conflicts[:8]:
                print(f"    {name} за {ya[i]}: {ord_t}={a}, {pref_t}={b}")
        if changed:
            touched += 1
            print(f"{ord_t}/{pref_t}: ряды сведены")
            if apply:
                pa.write_text(json.dumps(A, ensure_ascii=False, indent=2))
                pb.write_text(json.dumps(B, ensure_ascii=False, indent=2))
    print(f"\nпар всего: {len(pairs)}, сведено: {touched}" + ("" if apply else "  (сухой прогон)"))


if __name__ == "__main__":
    main()

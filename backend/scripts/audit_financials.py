"""Жёсткий аудит полноты и связности financials.json по всем компаниям.

Задача (владелец, 2026-07-27): «у части компаний дыры — выручка и сразу EBITDA,
без себестоимости/опер.расходов/валовой; в любой МСФО-отчётности видно, как из
выручки ПОСЛЕДОВАТЕЛЬНО получается прибыль, как складываются активы/пассивы,
как сходится ОДДС — у нас так должно быть у ВСЕХ; плюс не должно быть чисел,
расходящихся между местами».

Критерий — не конкретный список статей (by_nature-компании легитимно не имеют
себестоимости), а СВЯЗНОСТЬ МОСТОВ на последнем годе:
  P&L: revenue → (статьи расходов: cogs-путь ИЛИ expense_lines) → operating
       → pre_tax → tax → net_profit; ebitda ≈ operating + D&A.
  Баланс: total_assets = current + non_current = total_liabilities + equity;
          net_debt ≈ debt − cash.
  ОДДС: cfo + cfi + cff (+fx) ≈ net_change_in_cash; fcf ≈ cfo − capex.
  Банки: bank_pnl-мост (NII+NFI+прочее → opinc → −резервы −расходы → прибыль),
         bank_balance не пуст.
  Ряды: длины = len(fiscal_years); ключевые строки не оборваны None на свежих
        годах; margins сходятся с пересчётом.

Запуск: python scripts/audit_financials.py [--json отчёт.json]
Выход: свод в stdout + полный JSON-отчёт (по умолчанию в
/tmp/…scratchpad недоступен из скрипта — пишем рядом: scripts/_audit_report.json,
он в .gitignore-паттерны не входит — НЕ коммитить, файл рабочий).
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

COMPANIES = Path(__file__).parent.parent / "companies"

TOL = 0.02          # 2% допуск на мосты (округления/мелкие статьи)
TOL_SOFT = 0.05     # мягкий допуск (ebitda-мост, net_debt)
TOL_FCF = 0.15      # fcf-формулы компаний различаются


def _num(v):
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def _last(series):
    """Последнее значение ряда (list) или None."""
    if isinstance(series, list) and series:
        return _num(series[-1])
    return None


def _rel_err(a, b):
    if a is None or b is None or max(abs(a), abs(b)) < 1e-9:
        return None
    return abs(a - b) / max(abs(a), abs(b))




def _tax_bridge_err(pt, tax, npf):
    """Мин. ошибка моста pre_tax→net при обеих знаковых конвенциях налога
    (в файлах налог бывает и расходом с минусом, и с плюсом; налоговая
    ВЫГОДА — легитимно увеличивает прибыль: abs() давал ложный WARN)."""
    cands = [_rel_err(pt - abs(tax), npf), _rel_err(pt + abs(tax), npf)]
    cands = [c for c in cands if c is not None]
    return min(cands) if cands else None

def audit_company(ticker: str) -> list[dict]:
    """Список дефектов компании: {sev, code, msg}. sev: CRIT | GAP | WARN | INFO."""
    path = COMPANIES / ticker / "financials.json"
    out: list[dict] = []
    add = lambda sev, code, msg: out.append({"sev": sev, "code": code, "msg": msg})
    try:
        d = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as e:
        add("CRIT", "file", f"financials.json не читается: {type(e).__name__}")
        return out

    meta = d.get("meta") or {}
    years = meta.get("fiscal_years") or d.get("fiscal_years") or []
    ny = len(years)
    if not ny:
        add("CRIT", "meta", "нет fiscal_years")
        return out
    is_bank = "bank_pnl" in d

    # ---------- согласованность длин рядов ----------
    # Служебные ключи — НЕ ряды по годам (заметки/флаги/словари) — не проверяем.
    _NOT_SERIES = ("note", "notes", "data_flags", "data_flags_local", "ratios",
                   "cost_format", "margins", "expense_lines", "cfo_lines",
                   "cfi_lines", "cff_lines", "cf_lines_note", "sources")

    def check_lengths(block: dict, block_name: str):
        for k, v in (block or {}).items():
            if k in _NOT_SERIES or k.endswith("_note") or k.endswith("_flags"):
                continue
            if isinstance(v, list) and v and not isinstance(v[0], (dict, str)) and len(v) != ny:
                add("CRIT", "len", f"{block_name}.{k}: длина {len(v)} ≠ лет {ny}")

    # ---------- P&L ----------
    if is_bank:
        bp = d.get("bank_pnl") or {}
        check_lengths(bp, "bank_pnl")
        for k in ("net_interest_income", "net_fee_income", "operating_income",
                  "provisions", "operating_expenses", "pre_tax_profit",
                  "income_tax", "net_profit"):
            if _last(bp.get(k)) is None:
                add("GAP", "bank_pnl", f"bank_pnl.{k}: последний год пуст/отсутствует")
        pt, tax, np_ = _last(bp.get("pre_tax_profit")), _last(bp.get("income_tax")), _last(bp.get("net_profit"))
        if pt is not None and tax is not None and np_ is not None:
            err = _tax_bridge_err(pt, tax, np_)
            if err is not None and err > TOL_SOFT:
                add("WARN", "bank_tax_bridge",
                    f"pre_tax {pt:.0f} − налог {abs(tax):.0f} ≠ прибыль {np_:.0f} (Δ {err*100:.1f}%)")
        bb = d.get("bank_balance") or {}
        if not bb or all(_last(v) is None for v in bb.values() if isinstance(v, list)):
            add("GAP", "bank_balance", "bank_balance пуст — баланс банка не собран")
    else:
        inc = d.get("income_statement") or {}
        check_lengths(inc, "income_statement")
        rev = _last(inc.get("revenue"))
        op = _last(inc.get("operating_profit"))
        npf = _last(inc.get("net_profit"))
        if rev is None:
            add("CRIT", "pnl", "revenue: последний год пуст")
        if op is None:
            add("GAP", "pnl", "operating_profit: последний год пуст")
        if npf is None:
            add("CRIT", "pnl", "net_profit: последний год пуст")

        # Мост выручка → операционная прибыль (два легитимных пути)
        cogs, gross = _last(inc.get("cogs")), _last(inc.get("gross_profit"))
        lines = inc.get("expense_lines") or []
        lines_last = [
            _num((ln.get("values") or [None] * ny)[-1]) if isinstance(ln, dict) else None
            for ln in lines
        ]
        lines_sum = sum(v for v in lines_last if v is not None)
        lines_have = any(v is not None for v in lines_last)
        bridge_ok = False
        if rev is not None and cogs is not None and gross is not None:
            err = _rel_err(rev - abs(cogs), gross)
            if err is not None and err > TOL:
                add("WARN", "gross_bridge",
                    f"выручка − себестоимость ≠ валовая (Δ {err*100:.1f}%)")
            bridge_ok = True
        if not bridge_ok and rev is not None and op is not None and lines_have:
            # by_nature: revenue − Σстатей ≈ operating_profit (знаки статей в
            # файлах бывают и +расход, и −расход — пробуем оба)
            for cand in (rev - abs(lines_sum), rev + lines_sum):
                err = _rel_err(cand, op)
                if err is not None and err < TOL:
                    bridge_ok = True
                    break
            if not bridge_ok:
                none_cnt = sum(1 for v in lines_last if v is None)
                add("GAP" if none_cnt else "WARN", "op_bridge",
                    f"постатейный мост выручка→опер.прибыль не сходится "
                    f"(статей {len(lines)}, из них пустых в последнем году {none_cnt})")
        if not bridge_ok and rev is not None and op is not None and not lines_have and cogs is None:
            add("GAP", "op_bridge",
                "нет НИ себестоимости/валовой, НИ заполненных expense_lines — "
                "не видно, как из выручки получается операционная прибыль")

        # operating → pre_tax → налог → чистая
        pt, tax = _last(inc.get("pre_tax_profit")), _last(inc.get("income_tax"))
        if pt is None:
            add("GAP", "pnl", "pre_tax_profit: последний год пуст")
        if tax is None:
            add("GAP", "pnl", "income_tax: последний год пуст")
        if pt is not None and tax is not None and npf is not None:
            err = _tax_bridge_err(pt, tax, npf)
            if err is not None and err > TOL_SOFT:
                nci = _last(inc.get("net_profit_attributable_to_parent"))
                if nci is None or _tax_bridge_err(pt, tax, nci) is None or _tax_bridge_err(pt, tax, nci) > TOL_SOFT:
                    add("WARN", "tax_bridge",
                        f"до налога {pt:.0f} − налог {abs(tax):.0f} ≠ чистая {npf:.0f} "
                        f"(Δ {err*100:.1f}%; NCI/прочее не объясняет)")
        # EBITDA-мост
        ebitda, da = _last(inc.get("ebitda")), _last(inc.get("da"))
        if ebitda is not None and op is not None and da is not None:
            err = _rel_err(op + abs(da), ebitda)
            if err is not None and err > TOL_SOFT:
                add("WARN", "ebitda_bridge",
                    f"опер.прибыль + D&A ≠ EBITDA (Δ {err*100:.1f}%)")
        # margins сходимость
        margins = inc.get("margins") or {}
        nm = _last(margins.get("net_margin"))
        if nm is not None and rev and npf is not None:
            calc = npf / rev * 100
            if abs(calc - nm) > 1.5:
                add("WARN", "margin",
                    f"net_margin {nm:.1f}% ≠ пересчёт {calc:.1f}%")

        # ---------- Баланс (небанк) ----------
        # 🔴 ДВА легитимных формата в кодовой базе (найдено этим аудитом,
        # 2026-07-27): плоский (bs.cash — ряд; напр. LKOH) и вложенный
        # (bs.current_assets — СЛОВАРЬ статей с total_current; большинство).
        # FinanceTab читает ОБА с фолбэками (cua.cash || bs.cash; total ||
        # сумма статей) — аудитор обязан воспроизводить семантику витрины,
        # иначе ловит сотни ложных дыр (первый прогон: 238 «cash пуст» — из
        # них большинство ложные).
        bs = d.get("balance_sheet") or {}
        check_lengths(bs, "balance_sheet")

        def _grp_last(grp, total_key, part_keys):
            """Эффективное последнее значение группы: total ИЛИ сумма статей
            ИЛИ плоский ряд (если группа — list). Как FinanceTab.orSum."""
            g = bs.get(grp)
            if isinstance(g, list):
                return _last(g)
            if isinstance(g, dict):
                check_lengths({f"{grp}.{k}": v for k, v in g.items()}, "balance_sheet")
                tot = _last(g.get(total_key))
                if tot is not None:
                    return tot
                parts = [_last(g.get(k)) for k in part_keys]
                if any(v is not None for v in parts):
                    return sum(v for v in parts if v is not None)
            return None

        ta = _last(bs.get("total_assets"))
        ca = _grp_last("current_assets", "total_current",
                       ("inventory", "receivables", "cash", "short_term_investments", "other_current"))
        nca = _grp_last("non_current_assets", "total_non_current",
                        ("ppe", "rou_assets", "right_of_use_assets", "intangibles",
                         "goodwill", "long_term_investments", "other_non_current"))
        tl = _last(bs.get("total_liabilities"))
        cl = _grp_last("current_liabilities", "total_current_liab",
                       ("short_term_debt", "short_term_lease", "lease_current",
                        "payables", "other_current_liab"))
        ncl = _grp_last("non_current_liabilities", "total_non_current_liab",
                        ("long_term_debt", "long_term_lease", "lease_non_current",
                         "deferred_tax", "other_non_current_liab"))
        eq = _grp_last("equity", "total_equity",
                       ("share_capital", "retained_earnings", "additional_paid_in",
                        "treasury_shares", "other_equity")) or _last(bs.get("total_equity"))
        cua = bs.get("current_assets")
        cash = (_last(bs.get("cash_and_equivalents")) or _last(bs.get("cash"))
                or (_last(cua.get("cash")) if isinstance(cua, dict) else None))
        cul = bs.get("current_liabilities")
        ncul = bs.get("non_current_liabilities")
        std = (_last(bs.get("short_term_debt"))
               or (_last(cul.get("short_term_debt")) if isinstance(cul, dict) else None))
        ltd = (_last(bs.get("long_term_debt"))
               or (_last(ncul.get("long_term_debt")) if isinstance(ncul, dict) else None))
        nd = _last(bs.get("net_debt"))
        for name, v in (("total_assets", ta), ("equity", eq), ("total_liabilities", tl), ("cash", cash)):
            if v is None:
                add("GAP", "bs", f"{name}: последний год пуст")
        if ta is not None and ca is not None and nca is not None:
            err = _rel_err(ca + nca, ta)
            if err is not None and err > TOL:
                add("WARN", "bs_assets", f"оборотные + внеоборотные ≠ активы (Δ {err*100:.1f}%)")
        elif ta is not None and (ca is None or nca is None):
            add("GAP", "bs", "нет разбивки активов на оборотные/внеоборотные")
        if ta is not None and tl is not None and eq is not None:
            err = _rel_err(tl + eq, ta)
            if err is not None and err > TOL:
                add("CRIT", "bs_eq", f"обязательства + капитал ≠ активы (Δ {err*100:.1f}%)")
        if tl is not None and cl is not None and ncl is not None:
            err = _rel_err(cl + ncl, tl)
            if err is not None and err > TOL:
                add("WARN", "bs_liab", f"кратко + долгосрочные ≠ обязательства (Δ {err*100:.1f}%)")
        elif tl is not None and (cl is None or ncl is None):
            add("GAP", "bs", "нет разбивки обязательств кратко/долгосрочные")
        if nd is not None and cash is not None and (std is not None or ltd is not None):
            debt = (std or 0) + (ltd or 0)
            err = _rel_err(debt - cash, nd)
            if err is not None and err > TOL_SOFT and abs((debt - cash) - nd) > 0.02 * max(abs(ta or 1), 1):
                add("WARN", "net_debt", f"долг − деньги ≠ чистый долг (Δ {err*100:.1f}%; лизинг/депозиты?)")

        # ---------- ОДДС (небанк) ----------
        cf = d.get("cash_flow") or {}
        check_lengths(cf, "cash_flow")
        cfo, cfi, cff = _last(cf.get("cfo")), _last(cf.get("cfi")), _last(cf.get("cff"))
        ncc = _last(cf.get("net_change_in_cash"))
        capex, fcf = _last(cf.get("capex")), _last(cf.get("fcf"))
        for name, v in (("cfo", cfo), ("cfi", cfi), ("cff", cff)):
            if v is None:
                add("GAP", "cf", f"{name}: последний год пуст")
        if capex is None:
            add("GAP", "cf", "capex: последний год пуст")
        if cfo is not None and cfi is not None and cff is not None and ncc is not None:
            fx = _last(cf.get("fx_effect_on_cash")) or 0
            err = _rel_err(cfo + cfi + cff + fx, ncc)
            if err is not None and err > TOL_SOFT:
                add("WARN", "cf_bridge",
                    f"cfo+cfi+cff(+fx) ≠ изменение денег (Δ {err*100:.1f}%)")
        if fcf is not None and cfo is not None and capex is not None:
            err = _rel_err(cfo - abs(capex), fcf)
            if err is not None and err > TOL_FCF:
                add("INFO", "fcf_formula",
                    f"fcf ≠ cfo − capex (Δ {err*100:.1f}%) — формула компании? проверить note")

    # ---------- обрыв свежих лет у ключевых рядов ----------
    key_series = []
    if is_bank:
        bp = d.get("bank_pnl") or {}
        key_series = [("bank_pnl.net_profit", bp.get("net_profit"))]
    else:
        inc = d.get("income_statement") or {}
        cf = d.get("cash_flow") or {}
        key_series = [("revenue", inc.get("revenue")), ("net_profit", inc.get("net_profit")),
                      ("cfo", cf.get("cfo"))]
    for name, s in key_series:
        if isinstance(s, list) and len(s) >= 3:
            vals = [_num(x) for x in s]
            if vals[-1] is None and any(v is not None for v in vals[:-1]):
                add("GAP", "fresh", f"{name}: последний год оборван (None), история есть")

    return out


def main():
    # --ticker T — точечный прогон одной компании (для агентов-починщиков:
    # правишь financials.json → сразу проверяешь свой тикер)
    if "--ticker" in sys.argv:
        t = sys.argv[sys.argv.index("--ticker") + 1].upper()
        defects = audit_company(t)
        if not defects:
            print(f"{t}: ЧИСТО")
            return
        for x in sorted(defects, key=lambda x: x["sev"]):
            print(f"  [{x['sev']}] {x['code']}: {x['msg']}")
        sys.exit(1)

    tickers = sorted(p.name for p in COMPANIES.iterdir()
                     if p.is_dir() and not p.name.startswith((".", "_"))
                     and (p / "financials.json").exists())
    report = {}
    for t in tickers:
        defects = audit_company(t)
        if defects:
            report[t] = defects

    sev_rank = {"CRIT": 0, "GAP": 1, "WARN": 2, "INFO": 3}
    # свод
    from collections import Counter
    by_code = Counter()
    by_sev = Counter()
    for t, ds in report.items():
        for x in ds:
            by_code[f"{x['sev']}:{x['code']}"] += 1
            by_sev[x["sev"]] += 1
    print(f"Компаний с financials.json: {len(tickers)}; с дефектами: {len(report)}")
    print(f"По severity: {dict(by_sev)}")
    print("\nПо типам:")
    for code, n in by_code.most_common():
        print(f"  {code:24} {n}")
    print("\nТоп-30 компаний по тяжести:")
    scored = sorted(report.items(),
                    key=lambda kv: (min(sev_rank[x['sev']] for x in kv[1]),
                                    -len(kv[1])))
    for t, ds in scored[:30]:
        worst = min(ds, key=lambda x: sev_rank[x["sev"]])
        print(f"  {t:6} [{len(ds)} дефектов, худший {worst['sev']}] {worst['msg'][:90]}")

    out_path = Path(sys.argv[sys.argv.index("--json") + 1]) if "--json" in sys.argv else \
        Path(__file__).parent / "_audit_report.json"
    out_path.write_text(json.dumps(report, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"\nПолный отчёт: {out_path}")


if __name__ == "__main__":
    main()

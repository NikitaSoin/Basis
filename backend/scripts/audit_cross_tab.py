#!/usr/bin/env python3
"""Аудит стыков: сверка чисел между financials.json (источник истины)
и прозой/таблицами других блоков карточки (business_model.md, financials_summary.md).

Проверки:
  A (MISMATCH) — мини-P&L таблица business_model.md (| Показатель | 2025 | 2024 |)
      против income_statement по тем же годам.
  B (WARN) — числа «N млрд/трлн» рядом с ключевым словом метрики в прозе,
      которые не совпадают НИ С ОДНИМ годом ряда (число «из ниоткуда»).

Запуск: python3 scripts/audit_cross_tab.py [--ticker T] [--json] [--warn]
"""
import argparse
import json
import re
import sys
from pathlib import Path

BASE = Path(__file__).resolve().parent.parent / "companies"

YEAR_RE = re.compile(r"^(19|20)\d\d$")
NUM_CLEAN_RE = re.compile(r"[\s  ]+")

# --- разбор ячейки таблицы ---------------------------------------------------

REJECT_CELL_RE = re.compile(r"%|п\.п\.|раза|н/д|н/п|—|^-$|x$|×", re.I)


def parse_cell(cell):
    """→ (value_float, approx, scale) | None. scale: 'трлн'|'млрд'|'млн'|None."""
    s = cell.strip()
    if not s or REJECT_CELL_RE.search(s):
        return None
    approx = "~" in s or "≈" in s or "около" in s.lower()
    scale = None
    low = s.lower()
    if "трлн" in low:
        scale = "трлн"
    elif "млрд" in low:
        scale = "млрд"
    elif "млн" in low:
        scale = "млн"
    # убрать скобочные пояснения ($..., руб., от ... до)
    s = re.sub(r"\([^)]*\)", "", s)
    s = re.sub(r"(?i)млрд|трлн|млн|руб\.?|₽|\$|~|≈|\*+", "", s)
    s = s.replace("−", "-").replace("–", "-")
    s = NUM_CLEAN_RE.sub("", s).replace(",", ".")
    # диапазоны "30-55" не сверяем
    if re.search(r"\d-\d", s):
        return None
    m = re.fullmatch(r"-?\d+(\.\d+)?", s)
    if not m:
        return None
    return float(s), approx, scale


# --- сопоставление названия строки таблицы с метрикой ------------------------

def metric_of(name):
    """→ (metric_key, tolerance, negate_if_positive) | None"""
    n = name.strip().lower().replace("ё", "е")
    # другой базис/периметр — не сверяем вовсе
    hard_skip = ("до мсфо", "до ifrs", "pre-ifrs", "без аренды", "на акцию",
                 "lfl", "маржа", "сегмент", "с учетом доли", "динамика",
                 "eps", "dps", "продолж", "прекращ", "пао", "соло",
                 "головн", "ниокр", "полный")
    if any(w in n for w in hard_skip):
        return None
    if any(w in n for w in ("нормализ", "скорр", "adjusted", "adj")):
        # скорректированная EBITDA против отчётной — только WARN, законный базис
        if "ebitda" in n and "/" not in n and "долг" not in n:
            return ("ebitda_adj", 0.15, False)
        return None
    if n.startswith("выручка"):
        return ("revenue", 0.05, False)
    if n.startswith("чистая прибыль"):
        return ("net_profit", 0.05, False)
    if n.startswith("чистый убыток"):
        return ("net_profit", 0.05, True)
    if "ebitda" in n and "/" not in n and "долг" not in n:
        return ("ebitda", 0.10, False)
    if n.startswith("операционная прибыль"):
        return ("operating_profit", 0.07, False)
    if n.startswith("capex") or n.startswith("капзатрат") or n.startswith("капитальные"):
        return ("capex", 0.10, False)
    return None


# --- факты из financials.json ------------------------------------------------

UNIT_TO_BLN = {"млн": 1e-3, "млрд": 1.0, "тыс": 1e-6, "тысячи": 1e-6,
               "тыс. руб.": 1e-6}


def load_facts(fin):
    meta = fin.get("meta") or {}
    years = meta.get("fiscal_years") or fin.get("fiscal_years") or []
    k = UNIT_TO_BLN.get((meta.get("unit") or "млн").strip(), 1e-3)
    is_ = fin.get("income_statement") or {}
    bank = fin.get("bank_pnl") or {}
    cf = fin.get("cash_flow") or {}

    def series(*paths):
        for src, key in paths:
            v = src.get(key)
            if isinstance(v, list) and any(x is not None for x in v):
                return [x * k if isinstance(x, (int, float)) else None for x in v]
        return None

    facts = {
        "revenue": series((is_, "revenue")),
        "net_profit": series((is_, "net_profit"), (bank, "net_profit")),
        "ebitda": series((is_, "ebitda")),
        "operating_profit": series((is_, "operating_profit"),
                                   (bank, "operating_income")),
        "capex": series((cf, "capex")),
    }
    return years, facts


# --- проверка A: таблицы -----------------------------------------------------

CCY_TABLE_RE = re.compile(r"\$|USD|долл|€|EUR", re.I)


def check_tables(md_text, years, facts, fname, file_ccy="RUB", file_std=""):
    # строка таблицы, явно подписанная ДРУГИМ стандартом отчётности, — не стык.
    # Первичный стандарт файла — тот, что упомянут ПЕРВЫМ в meta (в скобках
    # часто поясняют второй).
    s = file_std.lower()
    pi, pr = s.find("мсфо"), s.find("рсбу")
    if pi < 0 and pr < 0:
        other_std = None
    elif pr < 0 or (0 <= pi < pr):
        other_std = "рсбу"   # файл МСФО → пропускаем строки «РСБУ»
    else:
        other_std = "мсфо"
    findings = []
    lines = md_text.splitlines()
    i = 0
    while i < len(lines):
        line = lines[i]
        if line.lstrip().startswith("|"):
            cells = [c.strip() for c in line.strip().strip("|").split("|")]
            year_cols = {j: int(c) for j, c in enumerate(cells)
                         if YEAR_RE.fullmatch(c)}
            # валюта таблицы отличается от валюты financials — не сверить без курса
            ctx = "\n".join(lines[max(0, i - 3):i + 1])
            if year_cols and file_ccy == "RUB" and CCY_TABLE_RE.search(ctx):
                i += 1
                continue
            if year_cols:
                j = i + 1
                if j < len(lines) and set(lines[j].replace("|", "").strip()) <= set("-: "):
                    j += 1
                while j < len(lines) and lines[j].lstrip().startswith("|"):
                    row = [c.strip() for c in lines[j].strip().strip("|").split("|")]
                    mi = metric_of(row[0]) if row else None
                    if mi and other_std and other_std in row[0].lower():
                        mi = None
                    if mi:
                        metric, tol, negate = mi
                        fs = facts.get("ebitda" if metric == "ebitda_adj"
                                       else metric)
                        for col, year in year_cols.items():
                            if col >= len(row) or fs is None or year not in years:
                                continue
                            fact = fs[years.index(year)]
                            if fact is None:
                                continue
                            parsed = parse_cell(row[col])
                            if not parsed:
                                continue
                            val, approx, scale = parsed
                            if negate and val > 0:
                                val = -val
                            if scale == "трлн":
                                val *= 1000
                            elif scale == "млн":
                                val /= 1000
                            if metric == "capex":  # в ОДДС отток со знаком минус
                                val, fact = abs(val), abs(fact)
                            t = max(tol, 0.12 if approx else 0)
                            best = min(
                                (abs(val * m - fact) / max(abs(fact), 1e-9)
                                 for m in (1, 1000, 0.001)),
                            )
                            # оба значения у нуля (<20 млн) — округление, не стык
                            if abs(fact) < 0.02 and min(
                                    abs(val * m - fact)
                                    for m in (1, 1000, 0.001)) < 0.02:
                                best = 0
                            if best > t:
                                findings.append({
                                    "file": fname, "year": year, "metric": metric,
                                    "row": row[0][:45], "in_text": row[col][:25],
                                    "fact_bln": round(fact, 2),
                                    "diff_pct": round(best * 100, 1),
                                    "severity": ("WARN" if metric == "ebitda_adj"
                                                 else "MISMATCH"),
                                })
                    j += 1
                i = j
                continue
        i += 1
    return findings


# --- проверка B: проза -------------------------------------------------------

PROSE_RE = re.compile(
    r"(выручк\w+|чист\w+ прибыл\w+|чист\w+ убыт\w+|чист\w+ результат|ebitda)"
    r"[^.\n;|]{0,70}?"
    r"(?<![\d,.])(-|−)?(\d{1,4}(?:[\s  ]\d{3})*(?:[.,]\d{1,2})?)\s*"
    r"(млрд|трлн)",
    re.I,
)
PROSE_METRIC = {"выручк": "revenue", "прибыл": "net_profit",
                "убыт": "net_profit", "результат": "net_profit",
                "ebitda": "ebitda"}


def check_prose(md_text, years, facts, fname):
    findings = []
    seen = set()
    for m in PROSE_RE.finditer(md_text):
        line_start = md_text.rfind("\n", 0, m.start()) + 1
        head = md_text[line_start:line_start + 4].lstrip()
        if head.startswith("|"):
            continue  # таблицы сверяет check_tables
        if head.startswith(("- [", "* [", "[")):
            continue  # заголовки ссылок-источников (квартальные цифры и т.п.)
        kw = m.group(1).lower()
        # между ключевым словом и числом упомянута ДРУГАЯ метрика — не наш стык
        mid = md_text[m.end(1):m.start(3)]
        if re.search(r"долг|capex|капзатр|актив|капитал|дивиденд|cfo|денежн|"
                     r"маржа|расход|прибыл|убыт|выручк|ebitda", mid, re.I):
            continue
        metric = next((v for k, v in PROSE_METRIC.items() if k in kw), None)
        fs = facts.get(metric)
        if fs is None:
            continue
        ctx = md_text[max(0, m.start() - 60):m.end() + 20]
        if re.search(r"нормализ|скорр|adjust|прогноз|сценар|консенсус|ожида|"
                     r"около|порядка|~|≈|достиг|превыс|более|свыше|до \d|целев|"
                     r"прежн|замен|устар|не подтвер|агрегатор|рсбу|пао|соло",
                     ctx, re.I):
            continue
        val = float(NUM_CLEAN_RE.sub("", m.group(3)).replace(",", "."))
        if m.group(2):
            val = -val
        if "убыт" in kw and val > 0:
            val = -val
        if m.group(4).lower() == "трлн":
            val *= 1000
        key = (metric, round(val, 2))
        if key in seen:
            continue
        # совпадает хоть с одним годом (или полугодовой ~половиной) — ок
        ok = False
        for f in fs:
            if f is None:
                continue
            for mult in (1, 1000, 0.001):
                if abs(val * mult - f) / max(abs(f), 1e-9) < 0.12:
                    ok = True
                if abs(val * mult - f / 2) / max(abs(f) / 2, 1e-9) < 0.12:
                    ok = True  # полугодие
        if not ok:
            seen.add(key)
            findings.append({
                "file": fname, "year": None, "metric": metric,
                "row": "(проза)", "in_text": m.group(0)[-30:].strip(),
                "fact_bln": None, "diff_pct": None, "severity": "WARN",
            })
    return findings


# --- main --------------------------------------------------------------------

def audit_company(tdir, with_warn=True):
    fin_p = tdir / "financials.json"
    if not fin_p.exists():
        return []
    try:
        fin = json.loads(fin_p.read_text())
    except Exception as e:
        return [{"file": "financials.json", "severity": "ERROR",
                 "row": str(e)[:60], "metric": "-", "year": None,
                 "in_text": "-", "fact_bln": None, "diff_pct": None}]
    years, facts = load_facts(fin)
    if not years:
        return []
    meta = fin.get("meta") or {}
    file_ccy = (meta.get("currency") or "RUB").upper()
    file_std = meta.get("reporting_standard") or ""
    out = []
    for fname in ("business_model.md", "financials_summary.md"):
        p = tdir / fname
        if not p.exists():
            continue
        text = p.read_text()
        out += check_tables(text, years, facts, fname, file_ccy, file_std)
        if with_warn:
            out += check_prose(text, years, facts, fname)
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--ticker")
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--warn", action="store_true",
                    help="включить прозу (WARN); по умолчанию только таблицы")
    args = ap.parse_args()

    dirs = ([BASE / args.ticker.upper()] if args.ticker
            else sorted(d for d in BASE.iterdir() if d.is_dir()))
    report = {}
    for d in dirs:
        f = audit_company(d, with_warn=args.warn or bool(args.ticker))
        if f:
            report[d.name] = f

    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=1))
        return
    n_mis = sum(1 for fs in report.values() for x in fs
                if x["severity"] == "MISMATCH")
    n_warn = sum(1 for fs in report.values() for x in fs
                 if x["severity"] == "WARN")
    for t, fs in report.items():
        for x in fs:
            print(f"{t:6} {x['severity']:8} {x['file']:22} "
                  f"{x['year'] or '----'} {x['metric']:16} "
                  f"текст: {x['in_text']:25} факт: {x['fact_bln']} "
                  f"({x['row']})")
    print(f"\nИТОГО: MISMATCH {n_mis}, WARN {n_warn}, "
          f"компаний с расхождениями {len(report)}")


if __name__ == "__main__":
    main()

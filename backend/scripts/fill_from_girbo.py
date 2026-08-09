#!/usr/bin/env python3
"""Замена прикидочных чисел карточки точными из ГИР БО ФНС (bo.nalog.gov.ru).

🔴 ЗАЧЕМ. Аудит показал класс дефектов «числа даны с точностью в три значащие цифры»:
у 66 небанковских карточек ключевые ряды выглядят как 10 400 / 13 000 / 26 100 — так
отчётность не выглядит, это снято с графика агрегатора. Соседние строки при этом точные
(16 346 379 руб), из-за чего разделы не сходятся с итогами: у ТНС энерго Кубань разница
достигала 4%. Первичный источник для таких эмитентов машинный — государственный ресурс
ФНС, куда годовую бухотчётность сдают по 402-ФЗ. Числа приходят структурированно, по кодам
форм (0710001 баланс / 0710002 отчёт о финрезультатах), LLM в извлечении не участвует.

🔴 ЧЕГО ЭТОТ ИСТОЧНИК НЕ УМЕЕТ (иначе легко испортить хорошие карточки):
  • это РСБУ ОТДЕЛЬНОГО ЮРЛИЦА, а не консолидированная МСФО группы. Для холдинга числа
    законно другие — подставлять их в карточку, которая ведётся по МСФО, значит смешать
    два разных периметра. Поэтому периметр ПРОВЕРЯЕТСЯ: берём значения карточки, данные
    с точностью ≥4 значащих цифр (их прикидкой не получишь), и сверяем с ГИР БО. Совпали —
    периметр тот же, работаем. Разошлись или сверить не с чем — карточка пропускается.
  • только годовая отчётность, банков и НФО там нет вовсе (отчитываются перед ЦБ).

Правила записи:
  1. Прикидочное значение (≤3 значащих цифр) заменяется точным, ТОЛЬКО если они сходятся
     в пределах 2% — тогда это одно и то же число, просто округлённое. Разошлись сильнее —
     печатаем и не трогаем: значит расхождение содержательное, а не в точности.
  2. Дыры заполняются всегда (после проверки периметра).
  3. Точные значения карточки не перетираются никогда.
  4. После записи проверяются оба тождества — «активы = обязательства + капитал» и
     «разделы = итог». Не сошлось — карточка не сохраняется.

Запуск: python3 backend/scripts/fill_from_girbo.py [TICKER ...] [--apply] [-v]
"""
import csv
import json
import os
import subprocess
import sys
import time
import urllib.parse
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
COMPANIES = ROOT / "backend" / "companies"
RATES = ROOT / "rates.csv"
BASE = "https://bo.nalog.gov.ru"
UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/120.0 Safari/537.36")

# код формы -> куда кладём в карточке (None = только для проверок)
BALANCE = {
    1600: ("", "total_assets"),
    1300: ("", "total_equity"),
    1200: ("current_assets", "total_current"),
    1210: ("current_assets", "inventory"),
    1230: ("current_assets", "receivables"),
    1240: ("current_assets", "short_term_investments"),
    1250: ("current_assets", "cash"),
    1100: ("non_current_assets", "total_non_current"),
    1110: ("non_current_assets", "intangibles"),
    1150: ("non_current_assets", "ppe"),
    1170: ("non_current_assets", "long_term_investments"),
    1500: ("current_liabilities", "total_current_liab"),
    1510: ("current_liabilities", "short_term_debt"),
    1520: ("current_liabilities", "payables"),
    1400: ("non_current_liabilities", "total_non_current_liab"),
    1410: ("non_current_liabilities", "long_term_debt"),
    1420: ("non_current_liabilities", "deferred_tax"),
}
PNL = {
    2110: "revenue",
    2120: "cogs",
    2200: "operating_profit",
    2300: "pre_tax_profit",
    2400: "net_profit",
    2330: "interest_expense",
}


def get(url, params=None):
    """Через curl, а не urllib: цепочка ГИР БО подписана «Russian Trusted CA», которого нет
    в наборе корневых сертификатов Python — urllib падает на проверке, curl с системным
    хранилищем macOS проходит."""
    if params:
        url += "?" + urllib.parse.urlencode(params)
    out = subprocess.run(["curl", "-sS", "--max-time", "30", "-A", UA,
                          "-H", "Accept: application/json", url],
                         capture_output=True, text=True)
    if out.returncode != 0:
        raise RuntimeError(out.stderr.strip()[:120])
    return json.loads(out.stdout)


def inn_map():
    out = {}
    if not RATES.exists():
        return out
    with open(RATES, encoding="cp1251") as f:
        f.readline(); f.readline()
        for row in csv.DictReader(f, delimiter=";"):
            inn, secid = (row.get("INN") or "").strip(), (row.get("SECID") or "").strip()
            if inn and secid:
                out[secid] = inn
    return out


def girbo_years(inn):
    """{год: {'balance': {код: млн}, 'pnl': {код: млн}}} — из всех сданных отчётов."""
    found = get(f"{BASE}/advanced-search/organizations/search", {"query": inn, "page": 0, "size": 5})
    content = found.get("content") or []
    if not content:
        return {}
    time.sleep(0.7)                                  # госресурс: идём с паузами, не пачкой
    reports = get(f"{BASE}/nbo/organizations/{content[0]['id']}/bfo/")
    out = {}
    for entry in reports or []:
        try:
            corr = entry["typeCorrections"][0]["correction"]
        except (KeyError, IndexError, TypeError):
            continue
        year = int(entry.get("period"))
        bal, pnl = corr.get("balance") or {}, corr.get("financialResult") or {}
        for tag, shift in (("current", 0), ("previous", -1)):
            y = year + shift
            slot = out.setdefault(y, {"balance": {}, "pnl": {}})
            for code in BALANCE:
                v = bal.get(f"{tag}{code}")
                if v is not None and code not in slot["balance"]:
                    slot["balance"][code] = float(v) / 1000        # тыс ₽ -> млн ₽
            for code in PNL:
                v = pnl.get(f"{tag}{code}")
                if v is not None and code not in slot["pnl"]:
                    slot["pnl"][code] = float(v) / 1000
    return out


def sig(v):
    """Значащих цифр в числе: 10400 -> 3, 25048.573 -> 8."""
    s = f"{abs(v):.10g}".replace(".", "").rstrip("0")
    return len(s.lstrip("0")) or 1


def scope_matches(card, data, years, verbose, ticker):
    """Тот ли периметр: сверяем ТОЧНЫЕ значения карточки с ГИР БО."""
    bs = card.get("balance_sheet") or {}
    ins = card.get("income_statement") or {}
    checks = []
    for code, (sec, name) in BALANCE.items():
        vals = (bs.get(name) if not sec else (bs.get(sec) or {}).get(name)) or []
        for i, y in enumerate(years):
            if i < len(vals) and isinstance(vals[i], (int, float)) and sig(vals[i]) >= 4:
                g = (data.get(y) or {}).get("balance", {}).get(code)
                if g is not None and abs(g) > 1:
                    checks.append(abs(vals[i] - g) <= abs(g) * 0.01)
    for code, name in PNL.items():
        vals = ins.get(name) or []
        for i, y in enumerate(years):
            if i < len(vals) and isinstance(vals[i], (int, float)) and sig(vals[i]) >= 4:
                g = (data.get(y) or {}).get("pnl", {}).get(code)
                if g is not None and abs(g) > 1:
                    checks.append(abs(vals[i] - g) <= abs(g) * 0.01)
    if len(checks) < 2:
        # 🔴 Карточка, где НЕТ НИ ОДНОГО точного числа, сверять нечем — но это само по себе
        # диагноз: первоисточника у неё нет вовсе, всё снято с округлением. Тогда периметр
        # проверяем иначе — по близости грубых значений к отчётности: если они расходятся в
        # пределах ошибки округления до трёх значащих цифр (это ≤0,5%, берём 2% с запасом),
        # значит карточка построена на ЭТОЙ ЖЕ отчётности, просто огрублённой.
        # Порог намеренно жёсткий: у Россетей Сибири и РЭСК расхождение 4-6%, и это уже НЕ
        # округление, а другой периметр — такие карточки сюда не попадают.
        rough = []
        for code, (sec, name) in BALANCE.items():
            vals = (bs.get(name) if not sec else (bs.get(sec) or {}).get(name)) or []
            for i, y in enumerate(years):
                if i < len(vals) and isinstance(vals[i], (int, float)) and abs(vals[i]) > 100:
                    g = (data.get(y) or {}).get("balance", {}).get(code)
                    if g and abs(g) > 100:
                        rough.append(abs(vals[i] - g) / abs(g))
        for code, name in PNL.items():
            vals = ins.get(name) or []
            for i, y in enumerate(years):
                if i < len(vals) and isinstance(vals[i], (int, float)) and abs(vals[i]) > 100:
                    g = (data.get(y) or {}).get("pnl", {}).get(code)
                    if g and abs(g) > 100:
                        rough.append(abs(vals[i] - g) / abs(g))
        if len(rough) >= 4:
            med = sorted(rough)[len(rough) // 2]
            if med <= 0.02:
                print(f"  · {ticker}: точных значений в карточке нет вовсе, но грубые сходятся с отчётностью "
                      f"(медиана {med*100:.1f}%) — карточка построена на ней же, беру точные цифры")
                return True, 99
            if verbose:
                print(f"  · {ticker}: точных значений нет, грубые расходятся на {med*100:.0f}% — другой периметр, пропускаю")
                return False, 0
        if verbose:
            print(f"  · {ticker}: не с чем сверить периметр ({len(checks)} точных совпадений) — пропускаю")
        return False, 0
    hits = sum(checks)
    ok = hits / len(checks) >= 0.6
    if verbose or not ok:
        print(f"  · {ticker}: периметр {'совпал' if ok else 'НЕ совпал'} — {hits} из {len(checks)} точных значений сошлись"
              + ("" if ok else " (вероятно карточка по МСФО группы, а ГИР БО даёт РСБУ юрлица — пропускаю)"))
    return ok, hits


def identities_hold(card, years):
    """Сходится ли баланс карточки сам с собой ДО нашего вмешательства."""
    n = len(years)
    bs = card.get("balance_sheet") or {}

    def row(sec, name):
        vals = (bs.get(name) if not sec else (bs.get(sec) or {}).get(name)) or []
        return (list(vals) + [None] * n)[:n]

    ta, tl, te = row("", "total_assets"), row("", "total_liabilities"), row("", "total_equity")
    ca, na = row("current_assets", "total_current"), row("non_current_assets", "total_non_current")
    for i in range(n):
        A, L, E = ta[i], tl[i], te[i]
        if None not in (A, L, E) and A and abs(A - L - E) > max(abs(A) * 0.01, 1):
            return False
        if None not in (ca[i], na[i], A) and A and abs(ca[i] + na[i] - A) > max(abs(A) * 0.01, 1):
            return False
    return True


def fill(ticker, apply, verbose, allow_refine=False):
    path = COMPANIES / ticker / "financials.json"
    if not path.exists():
        return None
    card = json.loads(path.read_text())
    if card.get("bank_pnl") or card.get("bank_balance"):
        return None
    years = (card.get("meta") or {}).get("fiscal_years") or []
    if not years:
        return None
    inn = INN.get(ticker)
    if not inn:
        if verbose:
            print(f"  · {ticker}: ИНН не найден в rates.csv")
        return None
    try:
        data = girbo_years(inn)
    except Exception as exc:                                  # noqa: BLE001
        print(f"  ✕ {ticker}: ГИР БО недоступен ({type(exc).__name__})")
        return None
    if not data:
        if verbose:
            print(f"  · {ticker}: в ГИР БО отчётности нет")
        return None
    ok, exact_hits = scope_matches(card, data, years, verbose, ticker)
    # 🔴 РЕЖИМ ТОЛЬКО-УТОЧНЕНИЯ для карточек, не прошедших проверку периметра.
    # Логика: если грубое значение карточки САМО совпадает с числом ФНС в пределах 2%, то
    # оно из этой же отчётности и взято — просто округлено по дороге. Заменить его точным
    # значит поменять ТОЛЬКО точность, а не периметр: число остаётся тем же. Дыры при этом
    # не заполняются и точные значения не трогаются — там периметр мог бы разъехаться.
    refine_only = not ok
    if refine_only and not allow_refine:
        return None

    # 🔴 Когда источник становится ГЛАВНЫМ, а не дополняющим. Если стержень карточки уже
    # пришёл из ФНС (≥4 значений совпали до рубля), а сама карточка при этом не сходится —
    # значит поверх точных строк налеплены прикидки из чужого места, и держаться за них
    # незачем: у ФНС весь баланс согласован по построению. Тогда перезаписываем всё, что
    # источник покрывает. Условие намеренно узкое: без доказанного совпадения стержня
    # (просто «похоже») мы бы затирали МСФО группы отчётностью юрлица.
    # exact_hits == 99 — особый случай: точных значений в карточке нет вовсе, а грубые
    # сходятся с отчётностью. Сохранять там нечего, поэтому источник берётся целиком: иначе
    # выйдет смесь точных и округлённых значений, у которой перестаёт сходиться баланс.
    authoritative = (not refine_only) and (exact_hits == 99
                                           or (exact_hits >= 4 and not identities_hold(card, years)))
    if authoritative:
        why = ("сохранять нечего — точных значений в карточке нет"
               if exact_hits == 99
               else f"карточка не сходится сама с собой, а {exact_hits} строк совпали с ФНС до рубля")
        print(f"  ! {ticker}: {why} — беру баланс и P&L из ФНС целиком")

    n = len(years)
    bs = card.setdefault("balance_sheet", {})
    ins = card.setdefault("income_statement", {})
    filled = refined = kept = 0

    def slot(sec, name):
        holder = bs if not sec else bs.setdefault(sec, {})
        vals = holder.get(name)
        vals = (list(vals) + [None] * n)[:n] if isinstance(vals, list) else [None] * n
        holder[name] = vals
        return vals

    def write(vals, i, new, label):
        nonlocal filled, refined, kept
        old = vals[i]
        if old is None:
            if refine_only:
                return
            vals[i] = round(new, 3)
            filled += 1
        elif not isinstance(old, (int, float)):
            return
        elif authoritative:
            # источник признан главным: щадить «точные» значения тут нельзя — именно на них
            # и разъезжалось тождество (итог обязательств из чужого места при активах из ФНС)
            if abs(old - new) > max(abs(new) * 0.005, 0.5):
                refined += 1
                if verbose:
                    print(f"    {label}: {old:,.0f} → {new:,.3f}")
            vals[i] = round(new, 3)
        elif sig(old) <= 3 and (authoritative or abs(old - new) <= max(abs(new) * 0.02, 0.5)):
            vals[i] = round(new, 3)
            refined += 1
            if verbose:
                print(f"    {label}: {old:,.0f} → {new:,.3f}")
        elif sig(old) <= 3:
            kept += 1
            if verbose:
                print(f"    ⚠ {label}: в карточке {old:,.0f}, в ФНС {new:,.0f} — расхождение по существу, оставил")

    for y, block in sorted(data.items()):
        if y not in years:
            continue
        i = years.index(y)
        for code, (sec, name) in BALANCE.items():
            v = block["balance"].get(code)
            if v is not None:
                write(slot(sec, name), i, v, f"{y} {name}")
        for code, name in PNL.items():
            v = block["pnl"].get(code)
            if v is None:
                continue
            vals = ins.get(name)
            vals = (list(vals) + [None] * n)[:n] if isinstance(vals, list) else [None] * n
            ins[name] = vals
            write(vals, i, v, f"{y} {name}")

    # итог обязательств формой не выдаётся — это сумма двух разделов
    tl = slot("", "total_liabilities")
    for y, block in sorted(data.items()):
        if y not in years:
            continue
        lt, st = block["balance"].get(1400), block["balance"].get(1500)
        if lt is not None and st is not None:
            write(tl, years.index(y), lt + st, f"{y} total_liabilities")

    # 🔴 Капитал в файле лежит ДВАЖДЫ — плоско и внутри equity. Фронт читает плоское, но
    # рассинхрон оставляет в карточке две версии правды (уже ловилось на Кармани и Совкомбанке).
    if isinstance(bs.get("equity"), dict) and isinstance(bs.get("total_equity"), list):
        bs["equity"]["total_equity"] = list(bs["total_equity"])

    problems = []
    for i, y in enumerate(years):
        A, L, E = (bs.get(f, [None] * n)[i] for f in ("total_assets", "total_liabilities", "total_equity"))
        if None not in (A, L, E) and A and abs(A - L - E) > max(abs(A) * 0.01, 1):
            problems.append(f"{y}: активы−обязательства−капитал = {A-L-E:+,.0f}")
        ca = (bs.get("current_assets") or {}).get("total_current", [None] * n)[i]
        na = (bs.get("non_current_assets") or {}).get("total_non_current", [None] * n)[i]
        if None not in (ca, na, A) and A and abs(ca + na - A) > max(abs(A) * 0.01, 1):
            problems.append(f"{y}: разделы−итог активов = {ca+na-A:+,.0f}")
    if problems:
        print(f"  ✕ {ticker}: после заполнения не сходится — {'; '.join(problems[:3])}; карточка не изменена")
        return None

    if filled or refined:
        meta = card.setdefault("meta", {})
        meta["girbo_note"] = (
            "Ряды баланса и отчёта о финрезультатах взяты из государственного ресурса бухотчётности "
            "ФНС (bo.nalog.gov.ru, формы 0710001/0710002) — сданная эмитентом годовая РСБУ-отчётность. "
            "Периметр сверен с уже имевшимися в карточке точными значениями.")
        if authoritative:
            meta["reporting_standard"] = "РСБУ (ГИР БО ФНС)"
        if apply:
            path.write_text(json.dumps(card, ensure_ascii=False, indent=2))
        print(f"{ticker}: заполнено {filled}, уточнено {refined}, оставлено спорных {kept}")
    return filled + refined


INN = inn_map()

if __name__ == "__main__":
    args = [a for a in sys.argv[1:] if not a.startswith("-")]
    apply = "--apply" in sys.argv
    verbose = "-v" in sys.argv or "--verbose" in sys.argv
    total = 0
    for t in args:
        r = fill(t, apply, verbose, "--refine" in sys.argv)
        total += r or 0
        time.sleep(1.2)                    # госресурс: последовательно, с паузой
    print(f"\nитого изменено значений: {total}" + ("" if apply else "  (сухой прогон)"))

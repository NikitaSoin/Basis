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


def sig_digits(v):
    """Сколько значащих цифр несёт число: 10 400 -> 3, 25 048,573 -> 8.
    Это мера ТОЧНОСТИ, устойчивая к масштабу: у компании, отчитывающейся в миллиардах,
    точное число в наших миллионах законно кратно сотне, и «делимость на 100» его
    оболгала бы (первая версия проверки так и записала всю Роснефть в прикидки)."""
    s = f"{abs(v):.10g}".replace(".", "").rstrip("0")
    return len(s.lstrip("0")) or 1


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

    # 0. ГОДЫ ИДУТ ЗАДОМ НАПЕРЁД.
    # Это не косметика: вкладка «Финансы» считает соседний столбец ПРЕДЫДУЩИМ годом и берёт
    # «последний год» как years[-1]. На обратном порядке стрелки динамики показывают рост
    # падением, а самым свежим годом считается самый старый. Найдено у Эн+ и Черкизово.
    if list(years) != sorted(years):
        out.append(("!", "порядок-лет", f"годы идут не по возрастанию: {years} — на вкладке дельты и «последний год» будут неверными"))
    if len(set(years)) != len(years):
        out.append(("!", "порядок-лет", f"год встречается дважды: {years}"))

    # 0б. ОТРИЦАТЕЛЬНОЕ ТАМ, ГДЕ ЕГО НЕ БЫВАЕТ. Выручка, активы, запасы, деньги — величины,
    # которые не могут быть меньше нуля ни при каком результате бизнеса.
    # Пометка `<строка>_note` на карточке означает, что случай уже разобран и объяснён
    # (у инвесткомпании «выручка» — это результат операций с бумагами, и в 2022 он законно
    # ушёл в минус). Аудит не должен поднимать один и тот же вопрос по кругу.
    NEVER_NEGATIVE = ("revenue", "total_assets", "inventory", "cash", "gross_loans")
    for name in NEVER_NEGATIVE:
        for node in (card.get("income_statement") or {}, bs):
            if not isinstance(node, dict) or node.get(f"{name}_note"):
                continue
            vals = pad(series(node, name), n)
            for i, y in enumerate(years):
                if isinstance(vals[i], (int, float)) and vals[i] < 0:
                    out.append(("!", "знак", f"{name} за {y} = {vals[i]:,.0f} — эта величина не бывает отрицательной"))

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
    explained = set()          # ряды, у которых на карточке есть пояснение `<ряд>_note`

    def collect(node, prefix=""):
        if not isinstance(node, dict):
            return
        for key, val in node.items():
            if key.endswith("note"):
                # `capex_note` объясняет ряд `capex`: значит случай уже разобран человеком,
                # и поднимать его снова — это гонять один и тот же вопрос по кругу
                base = key[:-5].rstrip("_")
                if base:
                    explained.add(f"{prefix}{base}")
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
    # повтор значения там норма, а не копия истории. Гудвил — туда же: между переоценками
    # он стоит на месте по построению (проверено на НМТП и ВСМПО — обе «копии» оказались
    # обычным неизменным гудвилом).
    STATIC_HINTS = ("share_capital", "additional_paid_in", "share_premium", "treasury", "goodwill")
    for name, vals in named.items():
        if any(h in name for h in RATIO_HINTS) or any(h in name for h in STATIC_HINTS) or name in explained:
            continue
        # Значение, стоящее в ТРЁХ и более годах, — это постоянная статья (у Глобалтрака так
        # выглядит «прочий капитал», неизменный пять лет подряд), а не перенесённая история.
        # Настоящие копии, найденные на практике, встречались ровно дважды.
        counts = {}
        for v in vals:
            if v is not None and abs(v) >= 1000:
                counts[v] = counts.get(v, 0) + 1
        seen = {}
        for i, v in enumerate(vals):
            if v is None or abs(v) < 1000 or counts[v] > 2:
                continue
            if v in seen and i - seen[v] > 1:
                out.append(("!", "копия", f"{name}: {years[seen[v]]} и {years[i]} = {v:,.2f} — одно и то же значение в разные годы"))
            seen[v] = i

    # 4. разъехавшиеся единицы (скачок ровно на три порядка и обратно)
    for name, vals in named.items():
        if name in explained:
            continue
        for i in range(1, n):
            a, b = vals[i - 1], vals[i]
            if not a or not b:
                continue
            if abs(a) < 100 and abs(b) < 100:
                continue          # мелкие величины скачут законно (округления, разовые статьи)
            r = abs(b / a)
            if 500 <= r <= 2000 or 1 / 2000 <= r <= 1 / 500:
                out.append(("!", "единицы", f"{name}: {years[i-1]} → {years[i]} изменение в {r:,.0f}× ({a:,.0f} → {b:,.0f})"))

    # 4б. ДЕТАЛЬ БОЛЬШЕ СОДЕРЖАЩЕГО ЕЁ ЦЕЛОГО.
    # Проверка «изменение в 1000 раз» поднимает много законного шума (мелкая статья
    # честно скачет с 1 до 700), поэтому нужен признак, который НЕ МОЖЕТ быть нормой:
    # строка раздела больше итога раздела, или больше всех активов. Именно так выглядит
    # значение, вписанное в чужой единице — оно физически не помещается в своё целое.
    if not is_bank:
        for section, total_name in (("current_assets", "total_current"),
                                    ("non_current_assets", "total_non_current"),
                                    ("current_liabilities", "total_current_liab"),
                                    ("non_current_liabilities", "total_non_current_liab")):
            block = bs.get(section)
            if not isinstance(block, dict):
                continue
            totals = pad(series(bs, section, total_name), n)
            for line, vals in block.items():
                if not isinstance(vals, list) or line == total_name or line.endswith("note"):
                    continue
                vals = pad(vals, n)
                for i, y in enumerate(years):
                    v = vals[i]
                    if not isinstance(v, (int, float)) or abs(v) < 1:
                        continue
                    whole = totals[i] if totals[i] is not None else ta[i]
                    if whole and abs(v) > abs(whole) * 1.02:
                        out.append(("!", "деталь>целого",
                                    f"{section}.{line} за {y}: {v:,.0f} больше своего итога {whole:,.0f}"))

    # 4в. ГРУБОЕ ЗНАЧЕНИЕ — ПОХОЖЕ НА КОПИЮ СОСЕДНЕГО ГОДА.
    # Подпись, которая за один день встретилась на четырёх карточках (Диасофт, Распадская,
    # Россети, Варьеганнефтегаз): в ячейке стоит округлённое число, почти совпадающее с
    # ТОЧНЫМ значением соседнего года. Это признак того, что ряд заполняли со сдвигом или
    # копированием, и проверка на пропуски такое не видит — ячейка ведь заполнена.
    # 🔴 Находка ТРЕБУЕТ ПОДТВЕРЖДЕНИЯ ОТЧЁТОМ: два соседних года законно бывают почти
    # равны (у Донского завода радиодеталей выручка 2023 и 2024 отличается на 0,07% —
    # проверено по годовому отчёту, копией не является). Поэтому тяжесть «?», а не «!».
    for name, vals in named.items():
        if name in explained or any(h in name for h in STATIC_HINTS) or any(h in name for h in RATIO_HINTS):
            continue
        for i in range(n):
            a = vals[i]
            if not isinstance(a, (int, float)) or abs(a) < 100 or sig_digits(a) > 3:
                continue
            for j in (i - 1, i + 1):
                if not (0 <= j < n):
                    continue
                b = vals[j]
                if not isinstance(b, (int, float)) or abs(b) < 100 or sig_digits(b) < 5:
                    continue
                if abs(a - b) <= abs(b) * 0.005:
                    out.append(("?", "копия-соседа",
                                f"{name}: за {years[i]} стоит округлённое {a:,.0f}, почти равное точному "
                                f"значению {years[j]} года ({b:,.1f}) — проверить по отчёту, не сдвинут ли ряд"))
                    break

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

    # 6б. ВАЛОВАЯ ПРИБЫЛЬ ≠ ВЫРУЧКА − СЕБЕСТОИМОСТЬ.
    # Тождество держится на 682 ячейках базы из 711, так что отклонение — сигнал, а не норма.
    # Так нашлись: у Озона себестоимость 2021 БОЛЬШЕ выручки при положительной валовой
    # прибыли, у ГАЗ-Тека выручка 2024 завышена в 72 раза. Законное исключение одно —
    # сельхозкомпании, где валовая прибыль включает переоценку биологических активов;
    # у них на карточке стоит пояснение, и проверка его уважает.
    if not is_bank and not (card.get("income_statement") or {}).get("gross_profit_note"):
        ins_ = card.get("income_statement") or {}
        rev, cogs_, gp = (pad(series(ins_, k), n) for k in ("revenue", "cogs", "gross_profit"))
        for i, y in enumerate(years):
            if None in (rev[i], cogs_[i], gp[i]):
                continue
            calc = rev[i] - abs(cogs_[i])
            if not close(gp[i], calc, 0.02, 1):
                out.append(("!", "валовая", f"{y}: выручка {rev[i]:,.0f} − себестоимость {abs(cogs_[i]):,.0f} "
                                            f"= {calc:,.0f}, а валовая прибыль {gp[i]:,.0f}"))

    # 6в. МАТЕРИАЛЬНЫЙ КАПИТАЛ БОЛЬШЕ ВСЕГО КАПИТАЛА.
    # Строка получается вычитанием из капитала, поэтому превысить его не может ни при каких
    # данных. Нашлось 18 таких ячеек — все от того, что производную строку не пересчитали
    # вслед за исправленной исходной.
    tg = pad(series(bs, "tangible_equity"), n)
    for i, y in enumerate(years):
        if tg[i] is None or te[i] is None:
            continue
        if tg[i] > te[i] + max(abs(te[i]) * 0.001, 0.5):
            out.append(("!", "матер.капитал", f"{y}: материальный капитал {tg[i]:,.0f} больше всего капитала {te[i]:,.0f}"))

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
    # если резкий разворот уже разобран и объяснён на карточке (у Хэдхантера это выплата
    # крупного спецдивиденда, сходящаяся арифметикой), не поднимаем вопрос заново
    if bs.get("total_equity_note"):
        ratios = []
    if len(ratios) >= 4:
        flips = sum(1 for a, b in zip(ratios, ratios[1:]) if a and b and ((a > 1) != (b > 1)) and max(a / b, b / a) > 2)
        if flips >= 2:
            out.append(("?", "перестановка", f"соотношение капитала к обязательствам скачет через единицу {flips} раз — возможна перестановка строк местами"))

    # 8. ПОДОЗРИТЕЛЬНО ГРУБЫЕ среди точных.
    # Добавлено после Глобалтрака и О'Кея: там весь набор был не из отчётности, но
    # сходился сам с собой, поэтому тест на баланс молчал. Выдаёт подмену именно
    # фактура: рядом с 117 014,3 стоит ровное 83 600 — так отчётность не выглядит.
    # 🔴 Мерить надо ЗНАЧАЩИМИ ЦИФРАМИ, а не делимостью на сотню: первая версия теста
    # объявила «прикидкой» всю Роснефть — она отчитывается в миллиардах, и в наших
    # миллионах её точные числа законно кратны сотне (20 000 000 = 8 значащих цифр).
    for name, vals in named.items():
        # Уставный капитал и эмиссионный доход годами стоят на месте и часто выражаются
        # круглым числом по самой своей природе — «грубыми» их считать нельзя.
        if any(h in name for h in STATIC_HINTS):
            continue
        nums = [v for v in vals if isinstance(v, (int, float)) and abs(v) >= 100]
        if len(nums) < 4:
            continue
        rough = [i for i, v in enumerate(vals)
                 if isinstance(v, (int, float)) and abs(v) >= 100 and sig_digits(v) <= 3]
        exact = [v for v in nums if sig_digits(v) >= 5]
        best = run = 0
        for i in range(n):
            run = run + 1 if i in rough else 0
            best = max(best, run)
        if best >= 3 and len(exact) >= 2:
            out.append(("?", "грубые", f"{name}: {', '.join(str(years[i]) for i in rough)} — подряд идущие "
                                       f"значения в три значащие цифры при точных в других годах "
                                       f"(похоже на кусок ряда из другого источника)"))

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

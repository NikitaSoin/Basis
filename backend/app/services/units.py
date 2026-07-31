"""Единицы относительных показателей — приведение к процентам при ЧТЕНИИ.

ЗАЧЕМ: в `financials.json` рентабельности хранятся в РАЗНЫХ единицах у разных компаний —
у одних проценты (11.19), у других доли (0.0577). Наследие того, что блоки собирали
разные прогоны аналитиков без общего контракта на единицы. Замер 2026-07-31 по 264
компаниям: returns.roe — 31 в долях против 185 в процентах; roa — 56 против 166;
ros — 50 против 197; roic — 13 против 64.

Почему не замечали: 0.0577 — валидное число, ошибки не возникает. Оно молча означает
«ROE 0,06 %» вместо 5,77 %, и компания уезжает в самый низ рейтинга качества. Тот же
класс дефекта, что Decimal/isinstance в live_multiples и margins.ebitda_margin в
скринере: не падает, просто врёт.

🔴 ПОЧЕМУ НЕ ПРОСТО «|v| < 1.5 ⇒ доля» (порог, как в bfv/params.py): проверено на
данных — правило ошибается на 11 компаниях из 193, и ошибается в ОПАСНУЮ сторону.
У «Красного Октября» ROE действительно 0,88 %, у «Наука-Связь» — 0,11 %; порог счёл бы
их долями и раздул до 88 % и 11 %. Занизить показатель к нулю плохо, но раздуть его в
сто раз хуже: компания с реальными 0,88 % возглавила бы рейтинг качества.

КАК ОПРЕДЕЛЯЕМ: сверяем записанный ряд с пересчитанным из первичных статей
(прибыль/капитал для ROE) и выбираем ту гипотезу — «как есть» или «×100» — которая ближе
к пересчёту. Это надёжнее любого порога, потому что опирается на сами данные компании.

ЕСЛИ СВЕРИТЬ НЕЧЕМ — НЕ ТРОГАЕМ (fail-safe). Оставить показатель заниженным — это
статус-кво, уже существующее поведение; ошибочно раздуть его в сто раз — новый и худший
дефект. При отсутствии доказательств выбираем безобидную сторону.
"""

# Пересчёт по кривым данным сам может дать бессмыслицу: у компании с отрицательным
# капиталом (Сегежа) «ROE» выходит −34 627 %. Такие пары в сверке не участвуют.
_SANE_MAX_PCT = 300.0
_MIN_PAIRS = 2


def _pairs(series, numerator, denominator):
    """Годы, где есть и записанное значение, и пригодный для сверки пересчёт."""
    if not all(isinstance(x, list) for x in (series, numerator, denominator)):
        return []
    out = []
    for i in range(min(len(series), len(numerator), len(denominator))):
        s, n, d = series[i], numerator[i], denominator[i]
        if not all(isinstance(x, (int, float)) for x in (s, n, d)):
            continue
        if d <= 0:                       # отрицательный капитал/активы — пересчёт не показателен
            continue
        calc = n / d * 100.0
        if abs(calc) > _SANE_MAX_PCT:    # выброс: сверять по нему нельзя
            continue
        out.append((float(s), calc))
    return out


def detect_scale(series, numerator, denominator):
    """Множитель к процентам: 1.0 (уже проценты), 100.0 (доли) или None (не установлено)."""
    pairs = _pairs(series, numerator, denominator)
    if len(pairs) < _MIN_PAIRS:
        return None
    err_as_is = sum(abs(s - c) for s, c in pairs)
    err_x100 = sum(abs(s * 100.0 - c) for s, c in pairs)
    return 100.0 if err_x100 < err_as_is else 1.0


# Из чего пересчитывается каждый показатель: (числитель, знаменатель) в financials.json
_BASIS = {
    "roe": (("income_statement", "net_profit"), ("balance_sheet", "total_equity")),
    "roa": (("income_statement", "net_profit"), ("balance_sheet", "total_assets")),
    "ros": (("income_statement", "net_profit"), ("income_statement", "revenue")),
}


def _scale_for_metric(fin, key, series):
    spec = _BASIS.get(key)
    if not spec or not isinstance(fin, dict):
        return None
    (ng, nk), (dg, dk) = spec
    num = (fin.get(ng) or {}).get(nk)
    den = (fin.get(dg) or {}).get(dk)
    return detect_scale(series, num, den)


def series_to_percent(fin, key, series=None):
    """Ряд показателя `key` в процентах. Единицы определяются сверкой с пересчётом;
    если определить не удалось — ряд возвращается КАК ЕСТЬ (см. fail-safe выше)."""
    if series is None:
        series = (fin.get("returns") or {}).get(key) if isinstance(fin, dict) else None
    if not isinstance(series, list):
        return series
    k = _scale_for_metric(fin, key, series)
    if k in (None, 1.0):
        return series
    return [x * k if isinstance(x, (int, float)) else x for x in series]


def last_to_percent(fin, key, series=None):
    """Последнее непустое значение показателя в процентах."""
    s = series_to_percent(fin, key, series)
    if not isinstance(s, list):
        return None
    for v in reversed(s):
        if isinstance(v, (int, float)):
            return float(v)
    return None

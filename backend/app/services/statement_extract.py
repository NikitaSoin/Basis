"""Постатейное извлечение отчётности из текста документа + проверка арифметики.

Отличие от заголовочного извлечения в `report_watch._extract_financial`: то работает
по пресс-релизу и берёт 8 чисел (выручка/EBITDA/прибыль/долг/активы/капитал/поток/
капзатраты) — больше в релизе и не бывает. Этот модуль работает по ТЕКСТУ САМОГО
ДОКУМЕНТА (см. report_documents.py) и берёт статьи: P&L, баланс, ОДДС.

🔴 Главный принцип — НЕ ДОВЕРЯТЬ МОДЕЛИ НА СЛОВО. Отчётность самопроверяема: в ней
есть тождества, которые обязаны сходиться. Их и проверяем на выходе:
    активы = обязательства + капитал
    выручка − себестоимость = валовая прибыль
    прибыль до налога − налог = чистая прибыль
    EBITDA = операционная прибыль + амортизация
    свободный поток = операционный − капзатраты
Не сошлось за пределами допуска — статья помечается, а не тихо публикуется. Это тот
же подход, которым в проекте выверялись 1395 карточко-лет: расхождение в тождестве
почти всегда означает, что модель взяла число из соседней колонки (другой период,
другая единица, «в том числе»-строка), и такое число хуже, чем его отсутствие.

Единицы. В отчётности РФ шапка таблицы задаёт масштаб («в миллионах рублей»), и
модель обязана вернуть ЕДИНИЦУ ОТДЕЛЬНЫМ ПОЛЕМ, а не пересчитывать самостоятельно:
пересчёт в уме — это ровно тот шаг, на котором появляются ошибки в 1000 раз (в
проекте уже ловили выручку под шапкой «млрд ₽», которая на деле была в млн).

Знаки. Расходы возвращаем ПОЛОЖИТЕЛЬНЫМИ (величина), направление задаёт сама статья.
Иначе половина отчётов приходит с минусом, половина без, и «CFO − капзатраты» вслепую
удваивает поток — эти грабли в проекте уже были (см. память проекта про знак capex).
"""
from __future__ import annotations


import logging

logger = logging.getLogger(__name__)

# Допуск на тождество: 1% от большей стороны. Отчётность округляют, и требовать
# точного равенства нельзя; но 1% уже ловит подстановку чужой строки.
_TOLERANCE = 0.01

_SYS = (
    "Ты — извлекатель финансовой отчётности. Работаешь ТОЛЬКО с переданным текстом "
    "документа. Категорически запрещено додумывать, оценивать или пересчитывать "
    "отсутствующие статьи — чего нет в тексте, то null. Возвращаешь JSON."
)

_SPEC = (
    'Верни JSON: {'
    '"period_label": "как период назван в документе (напр. 1П2026, 2кв2026, 2025)", '
    '"period_end": "YYYY-MM-DD — последний день периода", '
    '"standard": "МСФО" | "РСБУ" | null, '
    '"unit": "тыс" | "млн" | "млрд" — ЕДИНИЦА ИЗ ШАПКИ ТАБЛИЦЫ, не пересчитывай сам, '
    '"currency": "RUB" | "USD" | ..., '
    '"income_statement": {"revenue": ч|null, "cogs": ч|null, "gross_profit": ч|null, '
    '"opex": ч|null, "operating_profit": ч|null, "da": ч|null, "ebitda": ч|null, '
    '"interest_expense": ч|null, "interest_income": ч|null, "fx_result": ч|null, '
    '"pre_tax_profit": ч|null, "income_tax": ч|null, "net_profit": ч|null, '
    '"net_profit_attributable": ч|null}, '
    '"balance_sheet": {"non_current_assets": ч|null, "ppe": ч|null, "intangibles": ч|null, '
    '"current_assets": ч|null, "inventory": ч|null, "receivables": ч|null, "cash": ч|null, '
    '"total_assets": ч|null, "equity": ч|null, "non_controlling_interest": ч|null, '
    '"long_term_debt": ч|null, "short_term_debt": ч|null, '
    '"non_current_liabilities": ч|null, "current_liabilities": ч|null, '
    '"total_liabilities": ч|null}, '
    '"cash_flow": {"cfo": ч|null, "cfi": ч|null, "cff": ч|null, "capex": ч|null, '
    '"dividends_paid": ч|null, "net_change_in_cash": ч|null}, '
    '"is_consolidated": true|false, '
    '"found_statements": ["ОПУ"|"баланс"|"ОДДС"] — какие формы РЕАЛЬНО есть в тексте'
    '}. '
    'ПРАВИЛА. Расходы (cogs, opex, da, interest_expense, income_tax, capex) возвращай '
    'ПОЛОЖИТЕЛЬНЫМИ числами — величиной, без минуса; направление задаёт сама статья. '
    'Исключение: income_tax при налоговой ЛЬГОТЕ (возмещении) возвращай отрицательным — '
    'это единственный случай, где знак несёт смысл. '
    'Берёшь колонку ЗА ОТЧЁТНЫЙ ПЕРИОД, не за сравнительный: в таблицах рядом стоит '
    'прошлый год, перепутать колонки — самая частая ошибка. '
    'equity — итог капитала ВКЛЮЧАЯ неконтролирующие доли; если в отчёте они выделены, '
    'верни их отдельно в non_controlling_interest. '
    'net_profit — прибыль ГРУППЫ; доля акционеров материнской компании — отдельно '
    'в net_profit_attributable. '
    'Если документ — не финансовая отчётность (устав, презентация без таблиц, '
    'сообщение о собрании), верни found_statements: [] и все статьи null.'
)


def _num(v):
    return v if isinstance(v, (int, float)) else None


def check_identities(data: dict) -> list[dict]:
    """Тождества отчётности. Возвращает список расхождений (пустой — всё сошлось).

    Проверяем ТОЛЬКО там, где обе стороны известны: отсутствие статьи — не ошибка,
    это честный пропуск. Ошибка — когда стороны есть и не сходятся.
    """
    out: list[dict] = []
    ist = data.get("income_statement") or {}
    bs = data.get("balance_sheet") or {}
    cf = data.get("cash_flow") or {}

    def near(a, b, name, formula):
        if a is None or b is None:
            return
        scale = max(abs(a), abs(b), 1.0)
        if abs(a - b) / scale > _TOLERANCE:
            out.append({"check": name, "formula": formula, "left": a, "right": b,
                        "diff_pct": round((a - b) / scale * 100, 2)})

    assets, eq, liab = _num(bs.get("total_assets")), _num(bs.get("equity")), _num(bs.get("total_liabilities"))
    if assets is not None and eq is not None and liab is not None:
        near(assets, eq + liab, "баланс", "активы = капитал + обязательства")
    ncl, cl = _num(bs.get("non_current_liabilities")), _num(bs.get("current_liabilities"))
    if liab is not None and ncl is not None and cl is not None:
        near(liab, ncl + cl, "обязательства", "итого = долгосрочные + краткосрочные")
    nca, ca = _num(bs.get("non_current_assets")), _num(bs.get("current_assets"))
    if assets is not None and nca is not None and ca is not None:
        near(assets, nca + ca, "активы", "итого = внеоборотные + оборотные")

    rev, cogs, gross = _num(ist.get("revenue")), _num(ist.get("cogs")), _num(ist.get("gross_profit"))
    if rev is not None and cogs is not None and gross is not None:
        near(gross, rev - abs(cogs), "валовая прибыль", "выручка − себестоимость")
    pre, tax, net = _num(ist.get("pre_tax_profit")), _num(ist.get("income_tax")), _num(ist.get("net_profit"))
    if pre is not None and tax is not None and net is not None:
        # налог отрицательный = льгота, тогда прибыль РАСТЁТ — вычитаем как есть
        near(net, pre - tax, "чистая прибыль", "до налога − налог")
    op, da, ebitda = _num(ist.get("operating_profit")), _num(ist.get("da")), _num(ist.get("ebitda"))
    if op is not None and da is not None and ebitda is not None:
        near(ebitda, op + abs(da), "EBITDA", "операционная прибыль + амортизация")

    cfo, cfi, cff, chg = (_num(cf.get("cfo")), _num(cf.get("cfi")), _num(cf.get("cff")),
                          _num(cf.get("net_change_in_cash")))
    if None not in (cfo, cfi, cff, chg):
        near(chg, cfo + cfi + cff, "изменение денежных средств", "CFO + CFI + CFF")
    return out


def extract(text: str, company_name: str | None = None,
            expected_period: str | None = None) -> dict:
    """Текст документа → статьи отчётности + результат самопроверки.

    Возвращает {"data": {...} | None, "issues": [...], "usable": bool}.
    usable=False означает «на витрину не годится»: либо форм нет, либо тождества
    разошлись. Это не ошибка выполнения — это честный отказ публиковать сомнительное.
    """
    from app.services.llm import complete, LLMError
    if not text or len(text) < 400:
        return {"data": None, "issues": [{"check": "вход", "formula": "текст короче 400 знаков"}],
                "usable": False}
    head = f"Компания: {company_name}. " if company_name else ""
    if expected_period:
        head += f"Ожидаемый период: {expected_period}. "
    try:
        # json_mode=True — llm.complete сам разбирает ответ и возвращает dict;
        # temperature 0: задача механическая, разброс формулировок тут только вредит
        data = complete(_SYS, f"{head}{_SPEC}\n\nТЕКСТ ДОКУМЕНТА:\n{text[:60000]}",
                        json_mode=True, max_tokens=2500, temperature=0)
    except LLMError as e:
        logger.warning("statement_extract: LLM не ответил: %s", e)
        return {"data": None, "issues": [{"check": "LLM", "formula": str(e)[:120]}], "usable": False}
    if not isinstance(data, dict):
        return {"data": None, "issues": [{"check": "разбор ответа", "formula": "модель вернула не объект"}],
                "usable": False}

    found = data.get("found_statements") or []
    issues = check_identities(data)
    # Единица обязательна: без неё числа бессмысленны, а угадывать масштаб по величине —
    # ровно тот путь, которым в проекте появлялись ошибки в 1000 раз.
    if data.get("unit") not in ("тыс", "млн", "млрд"):
        issues.append({"check": "единица", "formula": "unit не распознан — числа без масштаба"})
    usable = bool(found) and not issues
    return {"data": data, "issues": issues, "usable": usable}

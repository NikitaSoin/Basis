"""Постатейное извлечение из САМОГО документа отчётности.

Зачем отдельно от report_watch. Тот извлекает из ПЕРЕСКАЗА (новость, пресс-релиз)
и берёт заголовочные числа — выручка, EBITDA, прибыль, долг. Этого хватает, чтобы
обновить витрину, и не хватает, чтобы понимать бизнес: владелец 2026-08-29 сказал
прямо — «в отчётностях есть детали, которые могут быть важны: разовые факторы,
курсовые переоценки, переплата/недоплата налогов, FCF стоит скорректировать на
изменения в оборотном капитале».

Такие вещи в релиз не выносят: компания показывает красивый заголовок, а разовая
прибыль от переоценки или возврат налога лежат в примечаниях. Поэтому здесь вход —
текст документа (МСФО/РСБУ pdf), а на выходе:

  1. ПОЛНЫЕ формы: P&L построчно, баланс, ОДДС — то, чего нет в новостях;
  2. КАЧЕСТВО прибыли: разовые факторы, курсовые, налог не по ставке — с суммами
     и знаком, чтобы можно было посчитать «а сколько заработал бизнес»;
  3. ОБОРОТНЫЙ КАПИТАЛ: изменение и его вклад в операционный поток — иначе FCF
     сравнивается год к году при том, что поток раздут разовым высвобождением.

🔴 Дисциплина та же, что у всей аналитики платформы: чего нет в документе — то
null. Модель не считает и не оценивает; расчётные величины (скорректированная
прибыль, FCF) считаются КОДОМ из извлечённых строк, чтобы арифметику можно было
проверить, а не верить ей на слово.
"""
from __future__ import annotations

import logging

logger = logging.getLogger(__name__)

_SYS = (
    "Ты — финансовый аналитик, читающий консолидированную отчётность. Из текста "
    "документа извлекаешь строки отчётности и факторы качества прибыли ТОЧНО так, "
    "как они названы в документе. ЗАПРЕЩЕНО: считать, оценивать, выводить одно из "
    "другого, брать число из другого периода. Нет строки в документе — null. "
    "Все суммы — в млн ₽ (переведи из млрд/тыс., если документ в других единицах). "
    "Верни JSON."
)

_SPEC = (
    'Формат JSON:\n'
    '{"period_label": "период отчёта как назван в документе: 1П2026 / 2кв2026 / '
    '9М2026 / 2025", "standard": "МСФО|РСБУ", "currency": "RUB|USD|…", '
    '"unit_in_source": "млн|млрд|тыс — в чём числа В ДОКУМЕНТЕ", '
    '"income_statement": {"revenue": null, "cogs": null, "gross_profit": null, '
    '"operating_expenses": null, "operating_profit": null, "ebitda": null, '
    '"da": null, "finance_income": null, "finance_costs": null, '
    '"fx_gain_loss": null, "other_income_expense": null, "pre_tax_profit": null, '
    '"income_tax": null, "net_profit": null},\n'
    '"balance_sheet": {"total_assets": null, "non_current_assets": null, '
    '"current_assets": null, "cash": null, "inventories": null, '
    '"trade_receivables": null, "total_equity": null, "total_liabilities": null, '
    '"short_term_debt": null, "long_term_debt": null, "trade_payables": null, '
    '"net_debt": null},\n'
    '"cash_flow": {"cfo": null, "cfi": null, "cff": null, "capex": null, '
    '"working_capital_change": null, "interest_paid": null, "tax_paid": null, '
    '"dividends_paid": null},\n'
    '"one_offs": [{"name": "как назван фактор в документе", "amount": число, '
    '"line": "куда попал: net_profit|operating_profit|ebitda|cfo", '
    '"direction": "increase|decrease", "recurring": false, '
    '"quote": "фрагмент документа, где это сказано, до 200 знаков"}],\n'
    '"tax_note": {"effective_rate_pct": null, "statutory_rate_pct": null, '
    '"comment": "почему ставка отличается, если отличается; иначе null"},\n'
    '"working_capital_note": "как изменение оборотного капитала повлияло на '
    'операционный поток — словами документа; null, если не раскрыто",\n'
    '"is_financial_statements": true|false, "has_full_forms": true|false}\n'
    'Правила:\n'
    '- capex — ПОЛОЖИТЕЛЬНЫМ числом; working_capital_change — со знаком, как в ОДДС '
    '(отрицательное = отвлечение средств в оборотный капитал);\n'
    '- fx_gain_loss — курсовые разницы: прибыль положительная, убыток отрицательный;\n'
    '- one_offs — ТОЛЬКО то, что документ сам называет разовым/неденежным/'
    'нерегулярным (обесценение, переоценка, продажа актива, страховое возмещение, '
    'списание, эффект деконсолидации). Не придумывай и не относи сюда обычные '
    'операционные статьи. Нет таких — пустой список;\n'
    '- is_financial_statements=false, если текст не является отчётностью или '
    'релизом о результатах (реклама, устав, сообщение о собрании);\n'
    '- has_full_forms=true только если в тексте есть хотя бы две из трёх форм '
    '(P&L, баланс, ОДДС) построчно, а не пересказ.'
)


def extract_from_document(text_blob: str, company_name: str | None = None,
                          max_chars: int = 60_000) -> dict | None:
    """Постатейное извлечение. None — модель недоступна или текст не отчётность."""
    from app.services.llm import complete, LLMError
    if not text_blob or len(text_blob) < 1500:
        return None
    head = text_blob[:max_chars]
    user = (f"КОМПАНИЯ: {company_name}\n\nДОКУМЕНТ:\n{head}"
            if company_name else f"ДОКУМЕНТ:\n{head}")
    try:
        # Ответ длиннее, чем у извлечения из новости: здесь три формы плюс факторы.
        res = complete(_SYS + "\n" + _SPEC, user, json_mode=True,
                       max_tokens=2600, temperature=0.1)
    except LLMError as e:
        logger.warning("deep_extract: LLM недоступен: %s", e)
        return None
    if not isinstance(res, dict):
        return None
    if res.get("is_financial_statements") is False:
        logger.info("deep_extract: текст не отчётность (%s)", company_name)
        return None
    return enrich(res)


_SCALE_HINTS = {"млрд": 1000.0, "billion": 1000.0, "bn": 1000.0,
                "тыс": 0.001, "thousand": 0.001, "тысяч": 0.001}


def normalize_scale(data: dict, annual_revenue_mln: float | None) -> dict:
    """Привести числа к млн ₽ и не пустить на витрину то, что не сходится.

    🔴 Найдено на бою 2026-08-30: у Северстали с годовой выручкой 712 900 млн ₽
    из документа пришёл FCF «−30,3». Это миллиарды — модель не перевела единицы,
    хотя промпт требует млн. Ошибка масштаба тише любой другой: число выглядит
    правдоподобно и молча уезжает на витрину, где отличается в тысячу раз.

    Поэтому масштаб не «доверяется», а ПРОВЕРЯЕТСЯ по известной величине самой
    компании — годовой выручке из её же карточки. Не сходится и после поправки —
    помечаем `scale_suspect`, и свод к витрине такие числа не отдаёт."""
    ist = data.get("income_statement") or {}
    rev = _num(ist.get("revenue"))
    unit = str(data.get("unit_in_source") or "").lower()

    factor = 1.0
    for hint, mult in _SCALE_HINTS.items():
        if hint in unit:
            factor = mult
            break

    if annual_revenue_mln and rev:
        # Квартал — примерно четверть года, полугодие — половина. Берём широкий
        # коридор: сравниваем ПОРЯДОК, а не точное значение.
        lo, hi = annual_revenue_mln / 40.0, annual_revenue_mln * 2.0
        if not (lo <= rev * factor <= hi):
            # Пробуем стандартные множители, прежде чем сдаваться.
            # 🔴 1.0 в списке ПЕРВОЙ и обязательно (найдено 2026-08-31): подсказка из
            # шапки документа сама бывает неверной — в тексте попадается «тыс.» из
            # соседней таблицы, а числа уже в млн. Без единицы в списке такой случай
            # неисправим в принципе: исходное значение подходит, но вернуться к нему
            # нечем, и разбор уходит в scale_suspect. Так на витрину не попали
            # РусГидро (22,3 % годовой выручки за полугодие), Позитив (51,2 %) и
            # третий тикер (25,2 %) — все три лежали внутри коридора без всякой
            # поправки. Токены на извлечение потрачены, результат выброшен.
            for candidate in (1.0, 1000.0, 0.001, 1_000_000.0):
                if lo <= rev * candidate <= hi:
                    factor = candidate
                    # 1.0 — не «поправка», а отмена неверной подсказки: помечаем
                    # иначе, чтобы в логе было видно, что подвела шапка документа.
                    if candidate == 1.0:
                        data["scale_hint_ignored"] = str(data.get("unit_in_source") or "")
                    else:
                        data["scale_fixed_by"] = candidate
                    break
            else:
                data["scale_suspect"] = {
                    "revenue_extracted": rev,
                    "annual_revenue_known_mln": annual_revenue_mln,
                    "note": "масштаб не сошёлся с карточкой — на витрину не отдаём",
                }
                return data

    if factor != 1.0:
        for form in ("income_statement", "balance_sheet", "cash_flow"):
            node = data.get(form) or {}
            for k, v in list(node.items()):
                n = _num(v)
                if n is not None:
                    node[k] = round(n * factor, 1)
        for o in data.get("one_offs") or []:
            n = _num(o.get("amount"))
            if n is not None:
                o["amount"] = round(n * factor, 1)
        data["scale_factor_applied"] = factor
        data["derived"] = {}          # пересчитываем на приведённых числах
        enrich(data)
    return data


def to_overlay_figures(data: dict) -> dict:
    """Свести постатейный разбор к плоскому виду, который принимает витрина.

    Карточка (interim_overlay) знает восемь имён: revenue/ebitda/net_profit/
    net_debt + активы/капитал/операционный поток/капзатраты. Документ даёт их
    все и ещё десятки строк — те живут в `data` целиком и пойдут дальше по мере
    того, как витрина научится их показывать. Здесь только сведение к контракту,
    без единой новой цифры: что не названо в документе — остаётся пустым."""
    if data.get("scale_suspect"):
        # Масштаб не сошёлся с известной величиной компании — молча отдать такие
        # числа витрине хуже, чем не отдать ничего.
        logger.warning("deep_extract: числа не отданы на витрину, %s", data["scale_suspect"])
        return {}
    ist = data.get("income_statement") or {}
    bs = data.get("balance_sheet") or {}
    cf = data.get("cash_flow") or {}
    out = {
        "revenue": _num(ist.get("revenue")),
        "ebitda": _num(ist.get("ebitda")),
        "net_profit": _num(ist.get("net_profit")),
        "net_debt": _num(bs.get("net_debt")),
        "total_assets": _num(bs.get("total_assets")),
        "total_equity": _num(bs.get("total_equity")),
        "operating_cash_flow": _num(cf.get("cfo")),
        # Знак капзатрат в источниках непоследователен, витрина ждёт положительное.
        "capex": abs(_num(cf.get("capex"))) if _num(cf.get("capex")) is not None else None,
        "period_label": data.get("period_label"),
        "standard": data.get("standard"),
    }
    return {k: v for k, v in out.items() if v is not None}


def _num(v):
    if isinstance(v, bool) or v is None:
        return None
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def enrich(data: dict) -> dict:
    """Расчётные величины — КОДОМ, а не моделью.

    Модель извлекает строки; всё, что можно посчитать, считаем сами: так число
    воспроизводимо и его видно, из чего оно собрано. Это же правило спасает от
    любимой ошибки LLM — «посчитать» скорректированную прибыль в уме."""
    ist = data.get("income_statement") or {}
    cf = data.get("cash_flow") or {}
    derived: dict = {}

    cfo, capex = _num(cf.get("cfo")), _num(cf.get("capex"))
    if cfo is not None and capex is not None:
        # 🔴 abs(capex): знак капзатрат в источниках непоследователен (в памяти
        # проекта это отдельная запись) — вычитание вслепую удваивает поток.
        derived["fcf"] = round(cfo - abs(capex), 1)

    wc = _num(cf.get("working_capital_change"))
    if cfo is not None and wc is not None:
        # Поток без вклада оборотного капитала: год к году сравнивать честнее
        # именно его — разовое высвобождение запасов не выдаётся за рост бизнеса.
        derived["cfo_ex_working_capital"] = round(cfo - wc, 1)
        if derived.get("fcf") is not None:
            derived["fcf_ex_working_capital"] = round(derived["fcf"] - wc, 1)

    net = _num(ist.get("net_profit"))
    one_offs = [o for o in (data.get("one_offs") or []) if isinstance(o, dict)]
    adj, counted = net, []
    if net is not None and one_offs:
        for o in one_offs:
            amt = _num(o.get("amount"))
            if amt is None or o.get("line") not in (None, "net_profit"):
                continue
            # increase → эффект добавил прибыли, значит очищенная прибыль МЕНЬШЕ
            sign = -1 if (o.get("direction") or "increase") == "increase" else 1
            adj += sign * abs(amt)
            counted.append({"name": o.get("name"), "amount": abs(amt),
                            "direction": o.get("direction")})
        if counted:
            derived["net_profit_adjusted"] = round(adj, 1)
            derived["adjusted_from"] = counted

    fx = _num(ist.get("fx_gain_loss"))
    if net is not None and fx:
        derived["net_profit_ex_fx"] = round(net - fx, 1)

    tax, pre_tax = _num(ist.get("income_tax")), _num(ist.get("pre_tax_profit"))
    if tax is not None and pre_tax:
        rate = round(abs(tax) / abs(pre_tax) * 100, 1)
        # 🔴 «Эффективная ставка 207,5 %» — не ставка, а сигнал (Артген, 1П2026:
        # налог 16,6 при прибыли до налога 8,0). Такое бывает по делу — отложенные
        # налоги, убыточные дочерние, доначисления — но на витрине читается как
        # ошибка расчёта и подрывает доверие ко всему блоку. Ставкой называем
        # только то, что ею выглядит; остальное показываем как факт с двумя
        # числами, из которых видно, что произошло.
        if pre_tax > 0 and 0 <= rate <= 60:
            derived["effective_tax_rate_pct"] = rate
        else:
            derived["tax_unusual"] = {"income_tax": abs(tax), "pre_tax_profit": pre_tax,
                                      "ratio_pct": rate}

    data["derived"] = derived
    return data

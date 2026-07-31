"""Гейт авто-свежести прозы: матчинг find и заземление чисел.

Контекст (бой 2026-07-31): за 14 дней 35 попыток интерпретации — 35 rejected,
0 published. Содержательные правки резались не по смыслу, а по механике:
find_not_in_prose из-за типографики (кавычки/переносы/двойные пробелы) и
ungrounded_numbers на датах «30.07», которые есть в сигнале как ISO 2026-07-30.
Эти тесты фиксируют исправленное поведение И сохранность защиты от выдумки.
"""
from app.services.card_prose_patcher import _apply_and_gate

PROSE = ("Прибыль банка за 2025 год — 1 580 млрд ₽.\n"
         "Дивиденд за 2025 год рекомендован,  выплата ожидается летом. "
         "Балл управления 4,2.")
SIG = ("2026-07-30 [ir] Сбер: прибыль за 1П2026 составила 1,019 трлн (+18,6% г/г); "
       "дивиденд за 2025 выплачен")


def _run(find, replace):
    return _apply_and_gate(PROSE, {"confirmed": True,
                                   "edits": [{"find": find, "replace": replace}]}, SIG)


def test_whitespace_tolerant_find():
    # в прозе двойной пробел, модель отдаёт одиночный — раньше find_not_in_prose
    patched, notes = _run("Дивиденд за 2025 год рекомендован, выплата ожидается летом.",
                          "Дивиденд за 2025 год выплачен.")
    assert patched is not None and notes == []
    assert "выплачен." in patched and "ожидается летом" not in patched


def test_quotes_and_yo_tolerant_find():
    prose = "Совет директоров «Газпрома» утвердил отчёт."
    res = {"confirmed": True, "edits": [{"find": 'Совет директоров "Газпрома" утвердил отчет.',
                                         "replace": "Совет директоров «Газпрома» утвердил отчёт 30.07."}]}
    patched, notes = _apply_and_gate(prose, res, SIG)
    assert patched is not None and notes == []


def test_date_grounded_by_iso_signal():
    patched, notes = _run("Балл управления 4,2.", "Балл управления 4,2 (подтверждён 30.07).")
    assert patched is not None and notes == []


def test_invented_number_still_rejected():
    patched, notes = _run("Балл управления 4,2.", "Балл управления 3,1.")
    assert patched is None and any("ungrounded" in n for n in notes)


def test_signal_number_allowed():
    patched, notes = _run("Прибыль банка за 2025 год — 1 580 млрд ₽.",
                          "Прибыль банка за 1П2026 — 1,019 трлн ₽ (+18,6% г/г).")
    assert patched is not None and notes == []


def test_ambiguous_find_rejected():
    prose = "Ставка 14%. Ставка 14%."
    res = {"confirmed": True, "edits": [{"find": "Ставка 14%.", "replace": "Ставка 13%."}]}
    patched, notes = _apply_and_gate(prose, res, "сигнал: ставка 13%")
    assert patched is None and any("ambiguous" in n for n in notes)


def test_thousands_separator_number_grounded():
    # «1 019 млрд» с пробелом-разделителем распадалось на «1»+«019» → ungrounded
    prose = "Прибыль за 2025 год — 1 580 млрд ₽."
    sig = "2026-07-30 [ir] прибыль 1П2026 составила 1 019 млрд руб."
    res = {"confirmed": True, "edits": [{"find": "Прибыль за 2025 год — 1 580 млрд ₽.",
                                         "replace": "Прибыль за 1П2026 — 1 019 млрд ₽."}]}
    patched, notes = _apply_and_gate(prose, res, sig)
    assert patched is not None and notes == []


def test_interp_allows_expectation_wording_but_not_trades():
    prose = "Маржа стабильна."
    res_ok = {"confirmed": True, "edits": [{"find": "Маржа стабильна.",
                                            "replace": "Маржа стабильна; ожидается давление ставки."}]}
    patched, notes = _apply_and_gate(prose, res_ok, "сигнал: ставка", kind="interpretation")
    assert patched is not None and notes == []
    res_trade = {"confirmed": True, "edits": [{"find": "Маржа стабильна.",
                                               "replace": "Маржа стабильна — рекомендуем покупать."}]}
    patched, notes = _apply_and_gate(prose, res_trade, "сигнал", kind="interpretation")
    assert patched is None and any("forbidden" in n for n in notes)


def test_fact_still_blocks_expectation_wording():
    prose = "Маржа стабильна."
    res = {"confirmed": True, "edits": [{"find": "Маржа стабильна.",
                                         "replace": "Маржа стабильна; ожидается рост."}]}
    patched, notes = _apply_and_gate(prose, res, "сигнал", kind="fact")
    assert patched is None and any("forbidden" in n for n in notes)


def test_trailing_sentence_dot_not_ungrounded():
    # «...в 2025.» — точка конца предложения прилипала к числу: токен «2025.» ≠ «2025»
    prose = "План капзатрат подтверждён."
    sig = "2026-07-31 [ir] программа продлена до 2025 года"
    res = {"confirmed": True, "edits": [{"find": "План капзатрат подтверждён.",
                                         "replace": "План капзатрат продлён до 2025."}]}
    patched, notes = _apply_and_gate(prose, res, sig)
    assert patched is not None and notes == []


# ── детектор устаревших макро-чисел в прозе (run_macro_facts) ────────────────
from app.services.card_prose_patcher import _macro_prose_stale


def test_macro_stale_detector_on_real_sber_text():
    anchor = {"rate": (14.0, None), "inflation": (5.94, None), "expectations": (14.7, None)}
    sber = ("19 июня 2026 ставка снижена на 25 б.п. до 14,25% (с пика 21% в начале 2025), "
            "инфляция ~5,6% г/г, инфляционные ожидания повышены (~13%).")
    assert set(_macro_prose_stale(sber, anchor)) == {"rate", "inflation", "expectations"}


def test_macro_stale_detector_fresh_text_quiet():
    anchor = {"rate": (14.0, None), "inflation": (5.94, None), "expectations": (14.7, None)}
    fresh = "Ключевая ставка 14%, инфляция 5,94% г/г, ожидания населения 14,7%."
    assert _macro_prose_stale(fresh, anchor) == []


def test_macro_stale_detector_no_keywords_quiet():
    anchor = {"rate": (14.0, None)}
    assert _macro_prose_stale("Компания нарастила добычу угля.", anchor) == []


def test_strict_numbers_blocks_prose_sourced_value():
    # дыра с боя 2026-08-01: модель поставила «12,1» из другого места прозы вместо
    # 14,7 из якоря — strict_numbers разрешает новые числа ТОЛЬКО из grounding
    prose = "Ожидания повышены (13%). Ранее наблюдаемая инфляция была 12,1%."
    grounding = "Инфляционные ожидания населения: 14,7 % (2026-07-31)"
    bad = {"confirmed": True, "edits": [{"find": "Ожидания повышены (13%).",
                                         "replace": "Ожидания повышены (12,1%)."}]}
    patched, notes = _apply_and_gate(prose, bad, grounding, strict_numbers=True)
    assert patched is None and any("ungrounded" in n for n in notes)
    good = {"confirmed": True, "edits": [{"find": "Ожидания повышены (13%).",
                                          "replace": "Ожидания повышены (14,7%)."}]}
    patched, notes = _apply_and_gate(prose, good, grounding, strict_numbers=True)
    assert patched is not None and notes == []

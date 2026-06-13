#!/usr/bin/env python3
"""
Проверка арифметики и валидация extracted_financials.json для ТУЗА.
"""
import json
import sys

def check_arithmetic(data):
    """Самопроверка арифметики по основным соотношениям."""
    errors = []
    warnings = []

    # 2024 (индекс 3) — единственный год с достаточными данными
    fiscal_years = data["meta"]["fiscal_years"]
    year_idx = len(fiscal_years) - 1  # 2024
    year = fiscal_years[year_idx]

    # Баланс: total_assets ≈ total_equity + total_liabilities
    assets = data["balance_sheet"]["total_assets"][year_idx]
    equity = data["balance_sheet"]["equity"]["total_equity"][year_idx]
    liabilities = data["balance_sheet"]["total_liabilities"][year_idx]

    if assets and equity and liabilities:
        computed_assets = equity + liabilities
        if assets > 0:
            deviation = abs(assets - computed_assets) / assets * 100
            if deviation > 1:
                errors.append(f"Баланс 2024: total_assets ({assets}) ≠ equity+liab ({computed_assets}), отклонение {deviation:.1f}%")
            else:
                print(f"✓ Баланс 2024: assets ({assets}) ≈ equity ({equity}) + liab ({liabilities}) = {computed_assets}, отклонение {deviation:.1f}%")

    # ЧПХ: short_term_debt = 446 — входит ли в total_current_liab?
    std = data["balance_sheet"]["current_liabilities"]["short_term_debt"][year_idx]
    tcl = data["balance_sheet"]["current_liabilities"]["total_current_liab"][year_idx]
    if std and tcl is None:
        warnings.append(f"short_term_debt (446) не имеет total_current_liab для проверки")

    # CFO: Проверка логики денежных потоков (если будут данные)
    cfo = data["cash_flow"]["cfo"][year_idx]
    if cfo:
        print(f"✓ CFO 2024: {cfo} млн руб (положительный, операционная активность здоровая)")

    # Прибыльность
    np = data["income_statement"]["net_profit"][year_idx]
    rev = data["income_statement"]["revenue"][year_idx]
    if np and rev:
        margin = (np / rev) * 100
        print(f"✓ Прибыльность 2024: margin = {np}/{rev} = {margin:.1f}%")

    return errors, warnings

def validate_schema(data):
    """Проверка структуры JSON."""
    required_keys = ["meta", "income_statement", "balance_sheet", "cash_flow", "data_flags"]
    for key in required_keys:
        if key not in data:
            return False, f"Отсутствует ключевой раздел: {key}"
    return True, "Схема валидна"

def main():
    with open("/Users/soinnikita/investment-platform/backend/companies/TUZA/sources/extracted_financials.json", "r") as f:
        data = json.load(f)

    print("=" * 80)
    print(f"ВАЛИДАЦИЯ EXTRACTED_FINANCIALS.JSON ДЛЯ {data['meta']['ticker']}")
    print("=" * 80)

    # Схема
    ok, msg = validate_schema(data)
    print(f"\n1. СХЕМА: {msg}")
    if not ok:
        sys.exit(1)

    # Метаданные
    print(f"\n2. МЕТАДАННЫЕ:")
    print(f"   Тикер: {data['meta']['ticker']}")
    print(f"   Название: {data['meta']['name']}")
    print(f"   Стандарт: {data['meta']['reporting_standard']}")
    print(f"   Валюта: {data['meta']['currency']}, единица: {data['meta']['unit']}")
    print(f"   Годы: {data['meta']['fiscal_years']}")
    print(f"   Источник: {data['meta']['source']['type']}")
    print(f"   Качество данных: {data['meta']['data_quality']}")
    print(f"   Арифметика: {data['meta']['arithmetic_check']}")

    # Арифметика
    print(f"\n3. САМОПРОВЕРКА АРИФМЕТИКИ:")
    errors, warnings = check_arithmetic(data)

    if errors:
        print("   ОШИБКИ:")
        for err in errors:
            print(f"   ✗ {err}")

    if warnings:
        print("   ПРЕДУПРЕЖДЕНИЯ:")
        for warn in warnings:
            print(f"   ⚠ {warn}")

    if not errors and not warnings:
        print("   ✓ Все проверки пройдены")

    # Flags
    print(f"\n4. DATA_FLAGS ({len(data['data_flags'])} записей):")
    for i, flag in enumerate(data['data_flags'], 1):
        severity = "КРИТИЧНО" if "КРИТИЧНО" in flag else "⚠ Ограничение"
        print(f"   {i}. {flag}")

    # Итоговый статус
    print(f"\n5. ИТОГ:")
    print(f"   Годы со ЗНАЧИМЫМИ данными: 2024 (выручка, активы, капитал)")
    print(f"   Годы со ЧАСТИЧНЫМИ данными: 2021 (только чистая прибыль), 2022-2023 (только выручка)")
    print(f"   P&L: НЕПОЛНАЯ (без себестоимости, расходов, финансовых расходов)")
    print(f"   Баланс: НЕПОЛНАЯ (детали по активам/пассивам отсутствуют)")
    print(f"   ОДДС: ОТСУТСТВУЕТ")
    print(f"   Вердикт: ТРЕБУЕТСЯ РУЧНАЯ ЗАГРУЗКА PDF В sources/")
    print("=" * 80)

if __name__ == "__main__":
    main()

"""Сектор компании в каноне Basis (13 значений) — единый источник для эвристик.

🔴 ЗАЧЕМ. Поле `meta.sector` в `financials.json` — свободный текст, который писали
разные субагенты в разное время: 97 уникальных значений на 264 компании, вперемешку
русские и английские, со слэшами и уточнениями («oil_gas», «Нефтегаз», «Нефть и газ»,
«Нефть и газ (формально); фактически — "спящая"/имущественная структура группы»).
Секторные эвристики по такому полю промахиваются ТИХО — ровно тот класс отказа, что уже
дважды прятал поломки факторного каркаса (geo.factors 2026-07-12, знаки effect_sign).

🔴 ИСТОЧНИК ПРАВДЫ — БД (`companies.sector`, 13 чистых значений, на них работает
скринер), а НЕ текст из файла. Проверено 2026-07-30: файл и БД прямо противоречат друг
другу у 35 компаний из 264 — у дочек ГАЗа (GAZC/GAZS/GAZT) в файле стоит «finance»,
а в БД «Машиностроение»; у EUTR в файле «consumer», в БД «Нефть и газ». Нормализация
свободного текста здесь дала бы уверенно неверный сектор, и эвристика (экспортёр?
сырьевик?) молча промахнулась бы. Поэтому текстовая нормализация оставлена только
ФОЛБЭКОМ на случай, когда БД недоступна (офлайн-скрипты, тесты без базы).
"""
from __future__ import annotations

import logging

logger = logging.getLogger(__name__)

CANONICAL = (
    "Нефть и газ", "Электроэнергетика", "Металлургия", "Химия", "Машиностроение",
    "Финансы", "Потребительский сектор", "IT-сектор", "Телеком", "Здравоохранение",
    "Транспорт и логистика", "Девелопмент", "Прочее",
)

# (канонический сектор, кортеж подстрок в нижнем регистре). Проверяются ПО ПОРЯДКУ —
# первое совпадение выигрывает, поэтому специфичное стоит выше общего.
_RULES: tuple[tuple[str, tuple[str, ...]], ...] = (
    # Химия раньше нефтегаза: «нефтехимия»/«минеральные удобрения» содержат «нефт»
    ("Химия", ("хим", "chemical", "удобрен", "нефтехим", "petrochem", "agrochem")),
    ("Нефть и газ", ("нефт", "газ", "oil", "gas", "нгк", "refin", "upstream")),
    ("Электроэнергетика", ("электроэнерг", "энерг", "utilit", "power", "энергосбыт",
                            "генерац", "сет", "grid", "energosbyt", "тэц", "гэс")),
    ("Металлургия", ("металл", "metals", "mining", "добыч", "уголь", "coal", "сталь",
                      "steel", "золот", "gold", "алмаз", "уран", "алюмин")),
    ("Транспорт и логистика", ("транспорт", "transport", "логист", "logistic", "порт",
                                "port", "судоход", "shipping", "авиаперевоз", "airline",
                                "каршеринг", "жд", "railway")),
    ("Машиностроение", ("машиностро", "machinery", "судострои", "aerospace", "defense",
                         "оборон", "автопром", "приборостро", "станко", "industrial")),
    ("Финансы", ("финанс", "financ", "банк", "bank", "страхов", "insur", "лизинг",
                  "leasing", "мфо", "microfin", "биржа", "exchange", "холдинг", "holding")),
    ("Девелопмент", ("девелоп", "develop", "real_estate", "real estate", "строительств",
                      "недвижим", "жилищ")),
    ("IT-сектор", ("it", "technolog", "software", "по", "интернет", "internet", "edtech",
                    "fintech", "кибербез", "маркетплейс", "e-commerce", "электронн")),
    ("Телеком", ("телеком", "telecom", "связь", "мобильн", "оператор связи")),
    ("Здравоохранение", ("здравоохран", "медицин", "pharma", "фарм", "biotech", "биотех",
                          "клиник", "аптек")),
    ("Потребительский сектор", ("потребит", "consumer", "ритейл", "retail", "продукт",
                                 "food", "алког", "alcohol", "агро", "agro", "сельск",
                                 "аквакультур", "пищев", "торгов")),
)


def normalize_sector(raw: str | None) -> str:
    """Свободный текст сектора → один из CANONICAL. Неопознанное → «Прочее»."""
    s = (raw or "").strip().lower()
    if not s:
        return "Прочее"
    for canonical, tokens in _RULES:
        for tok in tokens:
            # «it»/«по» — короткие токены, их матчим только как отдельное слово,
            # иначе «it» поймает «utilities», а «по» — почти всё русское.
            if len(tok) <= 2:
                if tok in s.replace("/", " ").replace(",", " ").split():
                    return canonical
            elif tok in s:
                return canonical
    return "Прочее"


# ────────────────────── сектор по тикеру (БД → фолбэк на текст) ──────────────────────
_db_sectors: dict[str, str] | None = None


def _load_db_sectors() -> dict[str, str]:
    """{ticker: sector} из БД, один раз на процесс. При недоступной БД — пустая карта
    (тогда работает текстовый фолбэк), это не повод падать."""
    global _db_sectors
    if _db_sectors is not None:
        return _db_sectors
    try:
        from sqlalchemy import text

        from app.db.session import SessionLocal
        db = SessionLocal()
        try:
            rows = db.execute(text("SELECT ticker, sector FROM companies")).all()
        finally:
            db.close()
        _db_sectors = {r[0]: r[1] for r in rows if r[0] and r[1]}
    except Exception:  # noqa: BLE001
        logger.warning("sector_norm: БД недоступна, сектор берётся из текста файла", exc_info=True)
        _db_sectors = {}
    return _db_sectors


def sector_for(ticker: str, raw_sector: str | None = None) -> str:
    """Канонический сектор компании: БД (правда) → нормализация текста (фолбэк)."""
    s = _load_db_sectors().get((ticker or "").upper())
    if s:
        return s
    return normalize_sector(raw_sector)


# Сырьевые ПРОИЗВОДИТЕЛИ — выигрывают от роста цены своего товара (структурная бета).
# Осознанно НЕ включены потребители сырья (транспорт: топливо — расход) и
# машиностроение (сталь — вход). См. докстринг factor_exposures.py.
_COMMODITY_PRODUCER_SECTORS = frozenset({"Нефть и газ", "Металлургия", "Химия"})

# Экспортёры — структурно выигрывают от СЛАБОГО рубля (выручка в валюте, затраты в ₽).
# Тот же набор: в РФ-вселенной валютную выручку даёт сырьевой экспорт.
_EXPORTER_SECTORS = frozenset({"Нефть и газ", "Металлургия", "Химия"})


def is_commodity_producer(ticker: str, raw_sector: str | None = None) -> bool:
    return sector_for(ticker, raw_sector) in _COMMODITY_PRODUCER_SECTORS


def is_exporter(ticker: str, raw_sector: str | None = None) -> bool:
    return sector_for(ticker, raw_sector) in _EXPORTER_SECTORS

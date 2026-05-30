"""
Импортирует компании из backend/data/rates.csv в таблицу companies.

CSV — выгрузка с Мосбиржи (MOEX), кодировка cp1251, разделитель ';'.
Заголовок на строке 3 (строки 1-2 — служебные).

Логика:
  - Читает все строки CSV (акции обыкновенные + привилегированные)
  - Upsert: если тикер уже есть в БД — обновляет name/sector/paired_ticker
  - Для привилегированных акций (TYPENAME содержит «привилег») —
    проставляет paired_ticker = тикер без суффикса P
  - Сектор берётся из SECTOR_MAP (заполнен по данным App.js);
    если тикера нет в маппинге — sector остаётся None

Запуск:
  cd backend
  python scripts/import_companies_from_csv.py [--dry-run]
"""

import csv
import os
import re
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from app.db.session import SessionLocal
from app.models.company import Company
from sqlalchemy import select

CSV_PATH = os.path.join(os.path.dirname(__file__), "..", "data", "rates.csv")

# Сектора по тикерам (источник: MOCK_COMPANIES в frontend/Basis/src/App.js)
SECTOR_MAP: dict[str, str] = {
    # Финансовый
    "SBER": "Финансовый", "SBERP": "Финансовый",
    "VTBR": "Финансовый",
    "T": "Финансовый",
    "MOEX": "Финансовый",
    "SPBE": "Финансовый",
    # Нефтегазовый
    "GAZP": "Нефтегазовый",
    "LKOH": "Нефтегазовый",
    "ROSN": "Нефтегазовый",
    "NVTK": "Нефтегазовый",
    "TATN": "Нефтегазовый", "TATNP": "Нефтегазовый",
    "SNGS": "Нефтегазовый", "SNGSP": "Нефтегазовый",
    "BANE": "Нефтегазовый", "BANEP": "Нефтегазовый",
    # Металлургия
    "GMKN": "Металлургия",
    "RUAL": "Металлургия",
    "NLMK": "Металлургия",
    "MAGN": "Металлургия",
    "CHMF": "Металлургия",
    # IT и Телеком
    "VKCO": "IT и Телеком",
    # IT и Кибербезопасность
    "POSI": "IT и Кибербезопасность",
    # Девелопмент
    "PIKK": "Девелопмент",
    "SMLT": "Девелопмент",
    "LSRG": "Девелопмент", "LSRGP": "Девелопмент",
    # Добыча
    "ALRS": "Добыча",
    # Золото
    "PLZL": "Золото",
    # Лесопромышленный сектор
    "SGZH": "Лесопромышленный сектор",
    # Потребительский сектор
    "BELU": "Потребительский сектор",
    "GCHE": "Потребительский сектор",
    # Ритейл
    "MGNT": "Ритейл",
    "LENT": "Ритейл",
    "X5": "Ритейл",
    "MVID": "Ритейл",
    # Телеком
    "MTSS": "Телеком",
    "RTKM": "Телеком", "RTKMP": "Телеком",
    # Транспорт
    "AFLT": "Транспорт",
    # Транспорт и логистика
    "FLOT": "Транспорт и логистика",
    "FESH": "Транспорт и логистика",
    "NMTP": "Транспорт и логистика",
    # Химия и удобрения
    "PHOR": "Химия и удобрения",
    "AKRN": "Химия и удобрения",
    # Энергетика
    "IRAO": "Энергетика",
    "RHYD": "Энергетика",
    "UPRO": "Энергетика",
    "OGKB": "Энергетика",
    # E-commerce
    "OZON": "E-commerce",
}


def clean_name(raw: str) -> str:
    """Убирает кавычки, правовые формы и лишние пробелы."""
    name = raw.strip().strip('"')
    # Убираем «ПАО», «АО», «ООО» и т.п. в начале
    name = re.sub(
        r'^(Публичное акционерное общество|Акционерное общество|'
        r'Общество с ограниченной ответственностью|ПАО|АО|ООО)\s*',
        '', name, flags=re.IGNORECASE
    ).strip().strip('"').strip()
    return name


def is_preferred(typename: str) -> bool:
    return "привилег" in typename.lower()


def infer_paired(ticker: str, typename: str) -> str | None:
    """Для привилегированных возвращает тикер обыкновенной акции."""
    if is_preferred(typename) and ticker.endswith("P"):
        return ticker[:-1]
    return None


def read_csv() -> list[dict]:
    with open(CSV_PATH, encoding="cp1251", errors="replace") as f:
        lines = f.readlines()

    # Строки 1-2 — служебные, строка 3 — заголовок
    header_line = lines[2].strip()
    headers = header_line.split(";")
    rows = []
    reader = csv.DictReader(lines[3:], fieldnames=headers, delimiter=";")
    for row in reader:
        ticker = (row.get("SECID") or "").strip()
        if ticker:
            rows.append(row)
    return rows


def import_companies(dry_run: bool = False) -> None:
    rows = read_csv()
    print(f"Строк в CSV: {len(rows)}")

    db = SessionLocal()
    added = updated = skipped = 0

    try:
        for row in rows:
            ticker = row["SECID"].strip()
            typename = row.get("TYPENAME", "").strip()
            raw_name = row.get("EMITENTNAME", "").strip() or row.get("SHORTNAME", "").strip()
            name = clean_name(raw_name) or ticker
            sector = SECTOR_MAP.get(ticker)
            paired = infer_paired(ticker, typename)

            existing: Company | None = db.execute(
                select(Company).where(Company.ticker == ticker)
            ).scalar_one_or_none()

            if existing:
                changed = False
                if not existing.sector and sector:
                    existing.sector = sector
                    changed = True
                if not existing.paired_ticker and paired:
                    existing.paired_ticker = paired
                    changed = True
                if changed:
                    updated += 1
                    if not dry_run:
                        db.add(existing)
                else:
                    skipped += 1
            else:
                company = Company(
                    ticker=ticker,
                    name=name,
                    sector=sector,
                    paired_ticker=paired,
                )
                added += 1
                if not dry_run:
                    db.add(company)

        if not dry_run:
            db.commit()

        mode = "[DRY RUN] " if dry_run else ""
        print(f"{mode}Добавлено: {added}  |  Обновлено: {updated}  |  Пропущено (без изм.): {skipped}")
        print(f"{mode}Итого обработано: {added + updated + skipped}")

    finally:
        db.close()


if __name__ == "__main__":
    dry_run = "--dry-run" in sys.argv
    if dry_run:
        print("=== DRY RUN — в БД ничего не пишем ===")
    import_companies(dry_run=dry_run)

"""
Загружает все акции MOEX из CSV файла в таблицу companies.
Запуск: cd backend && python -m scripts.load_all_companies [путь_к_csv]
"""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dotenv import load_dotenv
load_dotenv()

import csv
import re
from datetime import date, datetime, timezone
from decimal import Decimal, InvalidOperation
from collections import defaultdict

from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session

DATABASE_URL = os.getenv("DATABASE_URL")
if not DATABASE_URL:
    raise RuntimeError("DATABASE_URL не задан")

# ──────────────────────────────────────────────
# МАППИНГ СЕКТОРОВ по ключевым словам (EMITENTNAME lower)
# Порядок важен: первое совпадение побеждает
# ──────────────────────────────────────────────
SECTOR_RULES: list[tuple[str, list[str]]] = [
    ("Нефть и газ", [
        "газпром", "лукойл", "роснефть", "новатэк", "башнефть", "татнефть",
        "сургутнефтегаз", "газпром нефть", "славнефть", "руссне", "нефтяная",
        "нефтегаз", "нефтеоргсинтез", "нефтеперераб", "нефт", "газораспределен",
        "варьеганнефт", "якутская топливно", "транснефть",
    ]),
    ("Финансы", [
        "сбербанк", "банк", "тинькофф", "т-технологии", "втб", "мкб",
        "бспб", "кредитн", "страхов", "займ", "арсагера", "эсэфай",
        "ренессанс страхование", "росгосстрах", "дом.рф", "в2в", "уралсиб",
        "авангард", "кузнецкий", "приморье", "рдрб", "акционерная финансовая",
    ]),
    ("Металлургия", [
        "северсталь", "нлмк", "ммк", "мечел", "норильский никел", "норникел",
        "русал", "полюс", "полиметалл", "алроса", "магниевый завод",
        "металлург", "металлическ", "трубная", "металлообраб",
        "бурятзолото", "лензолото", "южуралзолото", "горно-металлург",
        "ижсталь", "ашинский", "белон", "угольная компания", "южный кузбасс",
        "уральская кузница", "всмпо", "сегежа", "ункл", "чмк",
    ]),
    ("IT-сектор", [
        "яндекс", "вк\"", " вк ", "group vk", "позитив", "диасофт", "группа астра",
        "хэдхантер", "headhunter", "циан", "аренадата", "ива ", "ива\"",
        "смарттехгрупп", "элемент", "ivi", "selectel",
    ]),
    ("Потребительский сектор", [
        "икс 5", "x5", "магнит", "лента\"", "озон", "ozon", "o'key",
        "фикс прайс", "fix price", "хэндерсон", "henderson", "новабев", "белуга",
        "черкизово", "инарктика", "абрау", "алкогольная", "кристалл", "русагро",
        "аптечная сеть", "ви.ру", "вуш", "светофор", "красный октябрь",
        "кондитерская", "вимм-билль", "продовольств",
    ]),
    ("Телеком", [
        "мтс", "ростелеком", "вымпелком", "мегафон", "таттелеком",
        "центральный телеграф", "башинформсвязь", "московская городская телефонная",
        "мгтс",
    ]),
    ("Электроэнергетика", [
        "интер рао", "русгидро", "федеральная гидрогенерирующая", "россети", "фск",
        "энергосбыт", "энергетики и электрификации", "генерирующая компания",
        "мосэнерго", "юнипро", "эл5-энерго", "двэк", "дальневосточная энергетическ",
        "тгк", "мрск", "оэк", "тнс энерго", "упро",
    ]),
    ("Химия", [
        "акрон", "фосагро", "уралкалий", "химпром", "куйбышевазот",
        "нижнекамскнефтехим", "нижнекамск", "казанское", "органический синтез",
        "химическ", "химический завод",
    ]),
    ("Девелопмент", [
        "группа компаний \"самолет", "самолет", "группа лср", "лср\"",
        "эталон", "апри\"", "глоракс", "девелоп", "инград", "пик\"", "пик ",
    ]),
    ("Транспорт и логистика", [
        "аэрофлот", "современный коммерческий флот", "совкомфлот",
        "дальневосточное морское пароходство", "fesco", "глобалтрак", "евротранс",
        "авиакомпания", "флот", "транспорт", "логистик", "пароходств",
    ]),
    ("Здравоохранение", [
        "артген биотех", "промомед", "юнайтед медикал", "мд медикал",
        "медицин", "фармацевт", "биотех", "генетики и репродукц", "генетико",
        "фармсинтез", "ммцб", "диод",
    ]),
    ("Машиностроение", [
        "яковлев", "иркут", "звезда\"", "выборгский судостроит",
        "ковровский механическ", "завод имени", "объединённые машиностроительные",
        "объединенные машиностроительные", "наука\"", "газ\"", "газ-тек", "газ-серв",
        "газкон", "туймазинский", "кузнечно-прессов", "котлостроит", "радиодеталей",
        "европейская электротехника", "донской завод", "машиностроен", "завод",
    ]),
]


# Точечные оверрайды по тикеру — побеждают ключевые слова.
# Синхронизированы с миграцией a9f31c20d4e1_fix_company_sectors.
TICKER_SECTOR_OVERRIDES: dict[str, str] = {
    "NKNC": "Химия", "NKNCP": "Химия",          # нефтехимия, не добыча
    "CARM": "Финансы",                            # МФО CarMoney
    "OZPH": "Здравоохранение",                    # фарма
    "DZRD": "Машиностроение", "DZRDP": "Машиностроение",
    "BAZA": "IT-сектор",
    "NKSH": "Машиностроение",                     # шины — автокомпоненты
    "EUTR": "Нефть и газ",                        # сеть АЗС
    "TRNFP": "Транспорт и логистика",             # трубопроводная монополия
    "RTGZ": "Транспорт и логистика",              # газораспределение
    "ELMT": "Машиностроение",                     # микроэлектроника
    "URKZ": "Машиностроение",                     # кузнечно-прессовое пр-во
    "RBCM": "Прочее",                             # медиа
    "PRFN": "Металлургия",                        # Теплант Восток — переработка стали
}


def classify_sector(emitent_name: str, ticker: str = "") -> str:
    if ticker and ticker in TICKER_SECTOR_OVERRIDES:
        return TICKER_SECTOR_OVERRIDES[ticker]
    lower = emitent_name.lower()
    for sector, keywords in SECTOR_RULES:
        for kw in keywords:
            if kw in lower:
                return sector
    return "Прочее"


def parse_russian_float(s: str) -> float | None:
    """'56,234' → 56.234"""
    if not s or s.strip() == "":
        return None
    try:
        return float(s.strip().replace(",", "."))
    except ValueError:
        return None


def clean_company_name(name: str, is_preferred: bool = False) -> str:
    s = name.strip()
    leading = [
        r'международная\s+компания\s+публичное\s+акционерное\s+общество',
        r'международная\s+компания',
        r'публичное\s+акционерное\s+общество',
        r'акционерный\s+коммерческий\s+банк',
        r'акционерная\s+компания',
        r'открытое\s+акционерное\s+общество',
        r'закрытое\s+акционерное\s+общество',
        r'акционерное\s+общество',
        r'мкпао', r'пао', r'оао', r'зао', r'ао\b', r'ак\b', r'мк\b',
    ]
    for p in leading:
        s = re.sub(r'(?i)^\s*' + p + r'[\s"«]*', '', s)
    s = re.sub(r'(?i)[\s,]+(?:ао|ап|пао|оао|зао)\.?\s*$', '', s)
    s = re.sub(r'(?i)\s+(?:пао|оао|зао|ао)(?=[\s,»"–-]|$)', '', s)
    s = s.replace('«', '').replace('»', '').replace('"', '').replace('"', '').replace('"', '')
    s = re.sub(r'\s{2,}', ' ', s).strip()
    if is_preferred:
        s += ' (привилегированные)'
    return s


def main():
    csv_path = sys.argv[1] if len(sys.argv) > 1 else None
    candidates = [
        csv_path,
        # основной путь в образе/репозитории: backend/data/rates.csv
        os.path.join(os.path.dirname(__file__), "../data/rates.csv"),
        "/Users/soinnikita/investment-platform/rates.csv",
        "/Users/soinnikita/Downloads/rates.csv",
        os.path.join(os.path.dirname(__file__), "../../rates.csv"),
    ]
    filepath = next((p for p in candidates if p and os.path.exists(p)), None)
    if not filepath:
        print("❌ CSV файл не найден. Укажи путь: python -m scripts.load_all_companies /path/to/rates.csv")
        sys.exit(1)

    print(f"📂 Читаем: {filepath}")

    with open(filepath, encoding="cp1251") as f:
        reader = csv.reader(f, delimiter=";")
        rows = list(reader)

    # Найти строку-заголовок
    header_row_idx = None
    for i, row in enumerate(rows):
        if "SECID" in row:
            header_row_idx = i
            break

    if header_row_idx is None:
        print("❌ Не найден заголовок SECID в CSV")
        sys.exit(1)

    header = rows[header_row_idx]
    data_rows = rows[header_row_idx + 1:]
    idx = {h: i for i, h in enumerate(header)}

    required = ["SECID", "SHORTNAME", "NAME", "EMITENTNAME", "TYPENAME"]  # PRICE больше не нужен
    missing = [c for c in required if c not in idx]
    if missing:
        print(f"❌ В CSV нет колонок: {missing}")
        sys.exit(1)

    engine = create_engine(DATABASE_URL)
    sector_counts: dict[str, int] = defaultdict(int)
    loaded = skipped = errors = 0

    with Session(engine) as session:
        for row in data_rows:
            if len(row) <= max(idx[c] for c in required):
                continue

            ticker = row[idx["SECID"]].strip()
            if not ticker:
                continue

            # Только акции (обыкновенные и привилегированные)
            typename = row[idx["TYPENAME"]].strip().lower()
            if "акци" not in typename:
                continue

            emitent = row[idx["EMITENTNAME"]].strip()
            short = row[idx["SHORTNAME"]].strip()
            raw_name = row[idx["NAME"]].strip() or short or ticker
            # ЦЕНУ из rates.csv НЕ берём — котировки наполняет quotes_updater (Тинёк→БД).

            is_preferred = "привилегированные" in typename
            name = clean_company_name(raw_name, is_preferred=is_preferred)

            cap_raw = row[idx["SECURITYCAPITALIZATION"]].strip() if "SECURITYCAPITALIZATION" in idx else ""
            market_cap = parse_russian_float(cap_raw)

            sector = classify_sector(emitent or raw_name, ticker)

            try:
                # Upsert company (ON CONFLICT DO NOTHING)
                result = session.execute(
                    text("""
                        INSERT INTO companies (ticker, name, sector, market_cap, created_at)
                        VALUES (:ticker, :name, :sector, :market_cap, :now)
                        ON CONFLICT (ticker) DO NOTHING
                        RETURNING id
                    """),
                    {
                        "ticker": ticker,
                        "name": name,
                        "sector": sector,
                        "market_cap": market_cap,
                        "now": datetime.now(timezone.utc),
                    },
                )
                row_id = result.fetchone()

                if row_id is None:
                    # Тикер уже был — обновим только сектор если нужно
                    skipped += 1
                    continue

                company_id = row_id[0]
                loaded += 1
                sector_counts[sector] += 1

                # Котировки НЕ сеем из rates.csv — их наполняет quotes_updater (Тинёк→БД,
                # фолбэк MOEX ISS). rates.csv остаётся справочником (тикеры/имена/сектор/
                # market_cap-сид), цена приходит только живой из quotes.

            except Exception as e:
                errors += 1
                print(f"  ⚠️  {ticker}: {e}")
                session.rollback()
                continue

        session.commit()

    print(f"\n✅ Загружено: {loaded} компаний | Пропущено (дубли): {skipped} | Ошибок: {errors}")
    print("\n📊 По секторам:")
    for sector, count in sorted(sector_counts.items(), key=lambda x: -x[1]):
        print(f"   {sector:<28} {count:>3}")


if __name__ == "__main__":
    main()

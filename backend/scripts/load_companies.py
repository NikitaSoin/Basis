"""
Загружает список российских компаний из App.js в таблицу companies.
Запуск: cd backend && python scripts/load_companies.py
"""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dotenv import load_dotenv
load_dotenv()

from app.db.session import SessionLocal
from app.models.company import Company

COMPANIES = [
    ("SBER",  "Сбербанк ПАО",          "Финансовый"),
    ("GAZP",  "Газпром ПАО",            "Нефтегазовый"),
    ("LKOH",  "Лукойл ПАО",             "Нефтегазовый"),
    ("ROSN",  "Роснефть",               "Нефтегазовый"),
    ("NVTK",  "Новатэк ПАО",            "Нефтегазовый"),
    ("GMKN",  "Норникель",              "Металлургия"),
    ("TATN",  "Татнефть",               "Нефтегазовый"),
    ("SNGS",  "Сургутнефтегаз",         "Нефтегазовый"),
    ("YDEX",  "МКПАО Яндекс",           "IT и Телеком"),
    ("PLZL",  "Полюс",                  "Золото"),
    ("ALRS",  "Алроса",                 "Добыча"),
    ("MTSS",  "МТС",                    "Телеком"),
    ("MGNT",  "Магнит",                 "Ритейл"),
    ("IRAO",  "Интер РАО",              "Энергетика"),
    ("RUAL",  "Русал",                  "Металлургия"),
    ("VTBR",  "Банк ВТБ",              "Финансовый"),
    ("T",     "Т-Технологии",           "Финансовый"),
    ("MOEX",  "Московская биржа",       "Финансовый"),
    ("SPBE",  "СПБ Биржа",              "Финансовый"),
    ("NLMK",  "НЛМК",                  "Металлургия"),
    ("MAGN",  "ММК",                    "Металлургия"),
    ("CHMF",  "Северсталь",             "Металлургия"),
    ("PHOR",  "ФосАгро",                "Химия и удобрения"),
    ("AKRN",  "Акрон",                  "Химия и удобрения"),
    ("OZON",  "Ozon",                   "E-commerce"),
    ("POSI",  "Positive Technologies",  "IT и Кибербезопасность"),
    ("RHYD",  "РусГидро",               "Энергетика"),
    ("UPRO",  "Юнипро",                 "Энергетика"),
    ("OGKB",  "ОГК-2",                  "Энергетика"),
    ("PIKK",  "ПИК",                    "Девелопмент"),
    ("SMLT",  "Самолёт",                "Девелопмент"),
    ("LSRG",  "ЛСР",                    "Девелопмент"),
    ("LENT",  "Лента",                  "Ритейл"),
    ("X5",    "X5 Group",               "Ритейл"),
    ("BELU",  "НоваБев",                "Потребительский сектор"),
    ("GCHE",  "Черкизово",              "Потребительский сектор"),
    ("FLOT",  "Совкомфлот",             "Транспорт и логистика"),
    ("FESH",  "FESCO",                  "Транспорт и логистика"),
    ("NMTP",  "НМТП",                   "Транспорт и логистика"),
    ("RTKM",  "Ростелеком",             "Телеком"),
    ("MVID",  "М.Видео",                "Ритейл"),
    ("SGZH",  "Сегежа",                 "Лесопромышленный сектор"),
    ("VKCO",  "VK",                     "IT и Телеком"),
    ("AFLT",  "Аэрофлот",               "Транспорт"),
    ("BANE",  "Башнефть",               "Нефтегазовый"),
]

def main():
    db = SessionLocal()
    try:
        # Удаляем тестовые записи не из нашего списка
        our_tickers = {t for t, _, _ in COMPANIES}
        removed = db.query(Company).filter(Company.ticker.notin_(our_tickers)).delete(synchronize_session=False)
        if removed:
            print(f"Удалено тестовых записей: {removed}")

        loaded = 0
        skipped = 0
        for ticker, name, sector in COMPANIES:
            existing = db.query(Company).filter(Company.ticker == ticker).first()
            if existing:
                skipped += 1
            else:
                db.add(Company(ticker=ticker, name=name, sector=sector))
                loaded += 1

        db.commit()
        total = db.query(Company).count()
        print(f"Загружено новых: {loaded}  |  Уже были: {skipped}  |  Всего в БД: {total}")
    finally:
        db.close()

if __name__ == "__main__":
    main()

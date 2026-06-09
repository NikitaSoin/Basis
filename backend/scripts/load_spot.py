"""Загрузка спот валюты и драгметаллов с MOEX (класс «Валюта и металлы»).

Запуск (из каталога backend):  python -m scripts.load_spot
"""
import logging, os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from dotenv import load_dotenv
load_dotenv()
from app.db.session import SessionLocal
from app.services.moex_spot import refresh_spot

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")

if __name__ == "__main__":
    db = SessionLocal()
    try:
        refresh_spot(db)
    finally:
        db.close()

"""Загрузка опционов (урезанная витрина) с MOEX. python -m scripts.load_options"""
import logging, os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from dotenv import load_dotenv
load_dotenv()
from app.db.session import SessionLocal
from app.services.moex_options import refresh_options

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
if __name__ == "__main__":
    db = SessionLocal()
    try:
        refresh_options(db)
    finally:
        db.close()

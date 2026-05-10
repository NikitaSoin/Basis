"""
Run from the backend/ directory:
  python -m scripts.generate_analysis

Requires ANTHROPIC_API_KEY in .env (or environment).
"""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dotenv import load_dotenv
load_dotenv()

from app.db.session import SessionLocal
from app.models.company import Company
from app.services.company import get_all_companies, add_analysis, _attach_last_price
from app.services.ai_analysis import generate_company_analysis
from app.schemas.company import AnalysisCreate

TARGET_TICKERS = {"SBER", "GAZP", "LKOH", "YDEX", "T"}


def main():
    db = SessionLocal()
    try:
        companies = db.query(Company).filter(Company.ticker.in_(TARGET_TICKERS)).all()

        if not companies:
            print("Компании не найдены в БД. Сначала загрузи их через load_companies.py.")
            return

        for company in companies:
            _attach_last_price(db, company)
            print(f"[{company.ticker}] Генерирую анализ для {company.name}...")
            try:
                data = generate_company_analysis(company)
                schema = AnalysisCreate(**data)
                analysis = add_analysis(db, company.id, schema)
                print(f"[{company.ticker}] Сохранено (id={analysis.id}). "
                      f"Fair price: {analysis.fair_price}")
            except Exception as e:
                print(f"[{company.ticker}] ОШИБКА: {e}")

    finally:
        db.close()


if __name__ == "__main__":
    main()

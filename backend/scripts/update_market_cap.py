"""
Разовый сидер ЧИСЛА АКЦИЙ (shares_outstanding) из CSV MOEX (ISSUESIZE).
Капитализацию НЕ пишем: market_cap считается живьём quotes_updater'ом
= последний close из quotes × shares_outstanding. rates.csv для цены/капы НЕ источник —
только справочник числа акций (ISSUESIZE).

Запуск: cd backend && python -m scripts.update_market_cap [путь_к_csv]
"""
import sys, os, csv
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from dotenv import load_dotenv
load_dotenv()

from sqlalchemy import create_engine, text

DATABASE_URL = os.getenv("DATABASE_URL")
if not DATABASE_URL:
    raise RuntimeError("DATABASE_URL не задан")


def parse_ru_float(s: str) -> float | None:
    if not s or not s.strip():
        return None
    try:
        return float(s.strip().replace(",", "."))
    except ValueError:
        return None


def main():
    csv_path = sys.argv[1] if len(sys.argv) > 1 else None
    candidates = [
        csv_path,
        "/Users/soinnikita/investment-platform/rates.csv",
        "/Users/soinnikita/Downloads/rates.csv",
        os.path.join(os.path.dirname(__file__), "../../rates.csv"),
    ]
    filepath = next((p for p in candidates if p and os.path.exists(p)), None)
    if not filepath:
        print("❌ CSV не найден")
        sys.exit(1)

    print(f"📂 Читаем: {filepath}")
    with open(filepath, encoding="cp1251") as f:
        reader = csv.reader(f, delimiter=";")
        rows = list(reader)

    header_row_idx = next(i for i, r in enumerate(rows) if "SECID" in r)
    header = rows[header_row_idx]
    data_rows = rows[header_row_idx + 1:]
    idx = {h: i for i, h in enumerate(header)}

    # ticker → shares_outstanding (ISSUESIZE — НЕценовое поле)
    shares_map: dict[str, int] = {}
    sz_idx = idx.get("ISSUESIZE", 999)
    for row in data_rows:
        if len(row) <= sz_idx:
            continue
        ticker = row[idx["SECID"]].strip()
        sh = parse_ru_float(row[sz_idx])
        if ticker and sh and sh > 0:
            shares_map[ticker] = int(sh)

    print(f"  Найдено чисел акций в CSV: {len(shares_map)}")

    engine = create_engine(DATABASE_URL)
    updated = 0
    with engine.begin() as conn:
        tickers_in_db = {r[0] for r in conn.execute(text("SELECT ticker FROM companies")).fetchall()}
        for ticker, sh in shares_map.items():
            if ticker in tickers_in_db:
                conn.execute(
                    text("UPDATE companies SET shares_outstanding=:sh WHERE ticker=:t"),
                    {"sh": sh, "t": ticker}
                )
                updated += 1

    print(f"✅ Обновлено shares_outstanding для {updated} компаний "
          f"(капитализация пересчитается живьём quotes_updater'ом от свежей цены)")


if __name__ == "__main__":
    main()

"""
Очищает названия компаний в БД от юридических аббревиатур.
Запуск: cd backend && python -m scripts.clean_names
"""
import sys, os, re
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from dotenv import load_dotenv
load_dotenv()

from sqlalchemy import create_engine, text

DATABASE_URL = os.getenv("DATABASE_URL")
if not DATABASE_URL:
    raise RuntimeError("DATABASE_URL не задан")

PREF_SUFFIX = " (привилегированные)"


def clean_company_name(name: str) -> str:
    s = name.strip()

    # Сначала снимаем уже добавленный суффикс, чтобы не дублировать
    already_pref = s.endswith(PREF_SUFFIX)
    if already_pref:
        s = s[: -len(PREF_SUFFIX)].strip()

    # Определяем привилегированные по "ап" в конце ДО чистки
    is_pref = already_pref or bool(re.search(r'\sап\.?\s*$', s, flags=re.IGNORECASE))

    # Удаляем trailing ап/ао суффикс
    s = re.sub(r'(?i)[\s,]+(?:ао|ап)\.?\s*$', '', s)

    # Ведущие юридические формы (длинные → короткие)
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

    # ПАО/ОАО в середине
    s = re.sub(r'(?i)\s+(?:пао|оао|зао|ао)(?=[\s,»"–-]|$)', '', s)

    # Кавычки
    s = s.replace('«', '').replace('»', '').replace('"', '').replace('"', '').replace('"', '')

    # Лишние пробелы
    s = re.sub(r'\s{2,}', ' ', s).strip()

    if is_pref:
        s += PREF_SUFFIX

    return s


def main():
    engine = create_engine(DATABASE_URL)
    updated = 0

    with engine.begin() as conn:
        rows = conn.execute(text("SELECT id, ticker, name FROM companies ORDER BY ticker")).fetchall()
        for row in rows:
            company_id, ticker, name = row
            cleaned = clean_company_name(name)
            if cleaned != name:
                conn.execute(
                    text("UPDATE companies SET name=:n WHERE id=:id"),
                    {"n": cleaned, "id": company_id}
                )
                updated += 1
                print(f"  {ticker:<10} {name[:45]!r:<48} → {cleaned!r}")

    print(f"\n✅ Очищено: {updated} из {len(rows)} компаний")


if __name__ == "__main__":
    main()

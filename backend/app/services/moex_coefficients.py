"""Официальные коэффициенты бета/корреляция с MOEX (fortscoefficients).

Источник (стабильный, найден через страницу «Значения коэффициентов»
moex.com/ru/forts/coefficients-values):
  1) метаданные: https://iss.moex.com/iss/archives/files/futures_coefficients_latest.json
     → отдаёт url актуального архива (имя меняется с датой);
  2) сам файл: /iss/downloads/rms/engines/futures/objects/fortscoefficients/
     futures_coefficients_latest_<ДАТА>.csv.zip

Формат CSV: первые 2 строки служебные («fortscoefficients», пустая), затем
шапка tradedate;base_name;issue;kff_korr;kff_beta. Числа в русской локали
(запятая), кодировка UTF-8. Бета акции против индекса МосБиржи — строки
base_name = MIX (фьючерс на индекс; MXI/IMX дублируют значения).

ФОЛБЭК при недоступности URL: положить CSV (или csv.zip) вручную в
backend/data/futures_coefficients_latest.csv — sync_from_file() его подхватит.
"""
import csv
import io
import json
import logging
import ssl
import urllib.request
import zipfile
from datetime import datetime, timezone
from pathlib import Path

from sqlalchemy import text

logger = logging.getLogger(__name__)

_ssl_ctx = ssl.create_default_context()
_ssl_ctx.check_hostname = False
_ssl_ctx.verify_mode = ssl.CERT_NONE

_HEADERS = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}

META_URL = "https://iss.moex.com/iss/archives/files/futures_coefficients_latest.json?iss.json=extended&iss.meta=off"
ISS_HOST = "https://iss.moex.com"
LOCAL_FALLBACK = Path(__file__).parent.parent.parent / "data" / "futures_coefficients_latest.csv"

BASE_INDEX = "MIX"  # фьючерс на индекс МосБиржи (MXI/IMX дают те же значения)

_UPDATE_SQL = text("""
    UPDATE company_metrics
    SET beta_moex = :beta, r_squared_moex = :r2, beta_moex_date = :d, updated_at = :now
    WHERE ticker = :ticker
""")


def _ru_float(s: str) -> float | None:
    try:
        return float(s.strip().replace(",", "."))
    except (ValueError, AttributeError):
        return None


def _download_latest_csv() -> tuple[str, str] | None:
    """Скачивает актуальный CSV. Возвращает (текст CSV, дата файла) или None."""
    try:
        req = urllib.request.Request(META_URL, headers=_HEADERS)
        with urllib.request.urlopen(req, timeout=30, context=_ssl_ctx) as resp:
            meta = json.loads(resp.read())
        files = next((b["files"] for b in meta if isinstance(b, dict) and "files" in b), [])
        entry = next((f for f in files if f.get("extension") == "csv"), None)
        if not entry:
            logger.warning("MOEX coefficients: в метаданных нет csv-файла")
            return None
        url = ISS_HOST + entry["url"]
        req = urllib.request.Request(url, headers=_HEADERS)
        with urllib.request.urlopen(req, timeout=120, context=_ssl_ctx) as resp:
            payload = resp.read()
        with zipfile.ZipFile(io.BytesIO(payload)) as zf:
            name = next(n for n in zf.namelist() if n.endswith(".csv"))
            return zf.read(name).decode("utf-8"), entry.get("date_till") or ""
    except Exception as e:
        logger.warning("MOEX coefficients: не удалось скачать (%s)", e)
        return None


def parse_betas(csv_text: str) -> tuple[dict[str, tuple[float, float]], str]:
    """{issue: (kff_beta, kff_korr)} из строк base_name=MIX + дата файла."""
    out: dict[str, tuple[float, float]] = {}
    tradedate = ""
    reader = csv.reader(io.StringIO(csv_text), delimiter=";")
    for row in reader:
        if len(row) < 5 or row[1] != BASE_INDEX:
            continue
        beta = _ru_float(row[4])
        korr = _ru_float(row[3])
        if beta is None:
            continue
        out[row[2].strip().upper()] = (beta, korr)
        tradedate = row[0]
    return out, tradedate


def sync_official_betas() -> dict:
    """Скачивает (или берёт локальный фолбэк) и кладёт беты MOEX в company_metrics.

    Маппинг тикеров: в строках base=MIX поле issue — это обычный тикер акции
    (SBER, LKOH, YDEX…), нотация совпадает с companies.ticker; несопоставленные
    тикеры файла логируются.
    """
    from app.db.session import SessionLocal

    got = _download_latest_csv()
    source = "url"
    if got is None and LOCAL_FALLBACK.exists():
        got = (LOCAL_FALLBACK.read_text(encoding="utf-8"), "local")
        source = "local file"
    if got is None:
        logger.error("MOEX coefficients: ни URL, ни локальный файл %s недоступны", LOCAL_FALLBACK)
        return {"updated": 0, "unmatched": [], "source": None, "date": None}

    csv_text, file_date = got
    betas, tradedate = parse_betas(csv_text)
    if not betas:
        logger.error("MOEX coefficients: строки base=%s не найдены", BASE_INDEX)
        return {"updated": 0, "unmatched": [], "source": source, "date": file_date}

    try:
        coef_date = datetime.strptime(tradedate, "%d.%m.%Y").date()
    except ValueError:
        coef_date = None

    db = SessionLocal()
    try:
        our = {r[0] for r in db.execute(text("SELECT ticker FROM company_metrics")).all()}
        now = datetime.now(timezone.utc)
        updated = 0
        for ticker, (beta, korr) in betas.items():
            if ticker not in our:
                continue
            r2 = round(korr * korr, 4) if korr is not None else None
            db.execute(_UPDATE_SQL, {"ticker": ticker, "beta": beta, "r2": r2,
                                     "d": coef_date, "now": now})
            updated += 1
        # итоговая показываемая бета: MOEX где есть, иначе наш расчёт
        db.execute(text("""
            UPDATE company_metrics
            SET beta = COALESCE(beta_moex, beta_calc),
                beta_source = CASE WHEN beta_moex IS NOT NULL THEN 'moex'
                                   WHEN beta_calc IS NOT NULL THEN 'calc' END
        """))
        db.commit()
        unmatched = sorted(t for t in betas if t not in our)
        logger.info("MOEX coefficients (%s, %s): обновлено %d тикеров; в файле, но не у нас: %d (%s)",
                    source, tradedate, updated, len(unmatched), ", ".join(unmatched[:10]))
        return {"updated": updated, "unmatched": unmatched, "source": source, "date": tradedate}
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()

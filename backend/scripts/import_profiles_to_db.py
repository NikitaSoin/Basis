"""
Import company profile JSONs into the company_profiles table.

Usage (from backend/):
    python -m scripts.import_profiles_to_db --tickers SBER,LKOH,YDEX,GMKN
    python -m scripts.import_profiles_to_db --all
"""
import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

from dotenv import load_dotenv

load_dotenv(Path(__file__).parent.parent / ".env")

sys.path.insert(0, str(Path(__file__).parent.parent))

from sqlalchemy import select
from app.db.session import SessionLocal
from app.models.company_profile import CompanyProfile

PROFILES_DIR = Path(__file__).parent.parent / "data" / "company_profiles"


def upsert_profile(db, ticker: str, profile: dict, log_entry: dict | None) -> str:
    existing = db.execute(select(CompanyProfile).where(CompanyProfile.ticker == ticker)).scalar_one_or_none()
    now = datetime.now(timezone.utc)

    data_quality = profile.get("meta", {}).get("data_quality") or (log_entry or {}).get("data_quality")
    completeness_pct = profile.get("meta", {}).get("completeness_pct") or (log_entry or {}).get("completeness_pct")

    if existing:
        existing.profile_json = profile
        existing.data_quality = data_quality
        existing.completeness_pct = completeness_pct
        existing.version = (existing.version or 1) + 1
        existing.updated_at = now
        action = "updated"
    else:
        db.add(CompanyProfile(
            ticker=ticker,
            profile_json=profile,
            data_quality=data_quality,
            completeness_pct=completeness_pct,
            version=1,
            created_at=now,
            updated_at=now,
        ))
        action = "inserted"

    return action


def load_log() -> dict:
    log_path = PROFILES_DIR / "_log.json"
    if log_path.exists():
        entries = json.loads(log_path.read_text(encoding="utf-8"))
        return {e["ticker"]: e for e in entries}
    return {}


def run(tickers: list[str]) -> None:
    log = load_log()
    db = SessionLocal()
    results = []

    try:
        for ticker in tickers:
            path = PROFILES_DIR / f"{ticker}.json"
            if not path.exists():
                print(f"  ✗ {ticker}: file not found ({path})")
                results.append((ticker, False, "file not found", None, None))
                continue

            profile = json.loads(path.read_text(encoding="utf-8"))
            log_entry = log.get(ticker)
            action = upsert_profile(db, ticker, profile, log_entry)

            pct = profile.get("meta", {}).get("completeness_pct", "?")
            quality = profile.get("meta", {}).get("data_quality", "?")
            sources = len(profile.get("sources", []))
            results.append((ticker, True, action, pct, quality, sources))

        db.commit()
    except Exception as exc:
        db.rollback()
        print(f"\n  ✗ DB error: {exc}")
        raise
    finally:
        db.close()

    print(f"\n{'═'*55}")
    print(f"  Loaded {sum(1 for r in results if r[1])}/{len(results)} profiles:")
    for r in results:
        if r[1]:
            ticker, _, action, pct, quality, sources = r
            print(f"    {ticker}: {action}  completeness={pct}%  quality={quality}  sources={sources}")
        else:
            ticker, _, reason, *_ = r
            print(f"    {ticker}: ✗ {reason}")
    print(f"{'═'*55}\n")


def main():
    parser = argparse.ArgumentParser(description="Import company profile JSONs into DB")
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--tickers", help="Comma-separated tickers, e.g. SBER,LKOH")
    group.add_argument("--all", action="store_true", help="Import all JSON files in profiles dir")
    args = parser.parse_args()

    if args.all:
        tickers = [p.stem for p in PROFILES_DIR.glob("*.json") if not p.stem.startswith("_")]
    else:
        tickers = [t.strip().upper() for t in args.tickers.split(",") if t.strip()]

    if not tickers:
        sys.exit("No tickers to process")

    print(f"\nImporting profiles: {', '.join(tickers)}")
    run(tickers)


if __name__ == "__main__":
    main()

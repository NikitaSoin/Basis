"""
Build structured company business-model profiles using Claude Opus + web search.

Usage (from backend/):
    python -m scripts.build_company_profile --tickers SBER,LKOH,YDEX,GMKN
"""
import argparse
import json
import os
import re
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

import anthropic
from app.db.session import SessionLocal
from app.models.company import Company

PROFILES_DIR = Path(__file__).parent.parent / "data" / "company_profiles"
LOG_FILE = PROFILES_DIR / "_log.json"
TODAY = datetime.now().strftime("%Y-%m-%d")

# ─── Prompts ───────────────────────────────────────────────────────────────────

SYSTEM_PROMPT = f"""Ты — аналитик финансовых рынков, специализирующийся на российских публичных компаниях.
Твоя задача — составить структурированное фактическое описание бизнес-модели компании на основе поиска в интернете.

Правила:
1. Только факты. Никаких оценочных суждений без цифр ("хорошо позиционирована", "лидер рынка" — только с данными).
2. Все доли, проценты и объёмы — с указанием года источника.
3. Честная оценка data_quality:
   - "high": данные из официальных отчётов (МСФО, годовые отчёты, IR-презентации)
   - "medium": из открытых источников (новости, аналитика, сайт компании)
   - "low": компания закрытая или данных недостаточно
4. Обязательно: минимум 3 macro_sensitivities.
5. Обязательно: минимум 3 конкурента в main_competitors (предпочтительно MOEX-тикеры).
6. sector_specific: заполни поля, реально применимые к сектору компании:
   - Банки: nim_range_pct, npl_ratio_pct, car_pct, roe_pct, key_loan_segments
   - Нефтяники: production_mboepd, refining_capacity_mt, urals_discount_usd, capex_bln_rub
   - IT/Tech: mau или dau, arr_growth_pct, r_and_d_share_pct, key_products (список)
   - Металлурги: key_products (продукт: объём), export_share_pct, key_commodity_prices
   - Другие: наиболее важные операционные метрики
7. Верни ТОЛЬКО валидный JSON. Без markdown-обёртки (без ```), без текста до или после JSON.
8. completeness_pct: оцени сам % заполненности (100% = все поля из реальных отчётов).

Сегодняшняя дата: {TODAY}"""


JSON_SCHEMA_GUIDE = """{
  "meta": {
    "ticker": "TICKER",
    "name_full": "полное официальное наименование",
    "sector": "сектор",
    "industry": "подотрасль",
    "last_updated": "YYYY-MM-DD",
    "data_quality": "high | medium | low",
    "completeness_pct": 0
  },
  "description": {
    "short": "2-3 предложения для превью карточки компании",
    "long": "4-6 абзацев развёрнутого описания бизнеса и инвестиционного профиля",
    "history_brief": "ключевые вехи: год основания, IPO, крупные события"
  },
  "business_essence": {
    "what_company_does": "суть бизнеса в 1-2 предложениях",
    "value_proposition": "ценностное предложение для клиентов",
    "business_model_type": "B2C | B2B | B2G | вертикально-интегрированная | платформа | другое"
  },
  "revenue_streams": [
    {
      "segment": "название сегмента",
      "share_pct": 60,
      "year": 2023,
      "description": "описание сегмента и источников дохода",
      "trend": "growing | stable | declining"
    }
  ],
  "geography": [
    {"region": "Россия", "share_pct": 95, "notes": "основные регионы присутствия"}
  ],
  "clients": {
    "types": ["B2C", "B2B"],
    "concentration": "low | medium | high",
    "top_clients_share_pct": null,
    "notes": "особенности клиентской базы, число активных клиентов если известно"
  },
  "cost_structure": {
    "main_cost_items": ["статья 1", "статья 2"],
    "margin_drivers": ["что улучшает маржу"],
    "margin_threats": ["что давит на маржу"]
  },
  "competitive_position": {
    "market_share_pct": null,
    "market_rank": 1,
    "main_competitors": ["VTBR", "TCSG", "другие"],
    "moats": ["конкурентные преимущества"],
    "vulnerabilities": ["слабые стороны и риски"]
  },
  "regulatory_context": {
    "key_regulators": ["ЦБ РФ"],
    "key_regulations": ["названия законов или нормативов"],
    "regulatory_risk_level": "high | medium | low",
    "notes": "ключевые регуляторные риски"
  },
  "key_metrics_to_watch": [
    {
      "metric": "название метрики (напр. NIM, EBITDA margin)",
      "why_important": "почему этот показатель важен для инвестора",
      "what_to_look_for": "на что смотреть в отчётах и новостях"
    }
  ],
  "macro_sensitivities": [
    {
      "factor": "key_rate | oil_price | ruble | inflation | sanctions | commodity_price | другое",
      "direction": "positive | negative | mixed",
      "strength": "high | medium | low",
      "channel": "объяснение механизма влияния на бизнес"
    }
  ],
  "sector_specific": {
    "note": "заполни поля специфичные для сектора: банки→nim/npl/car/roe, нефтянка→добыча/НПЗ/urals_discount, IT→MAU/ARR/r&d, металлургия→продукция/экспорт"
  },
  "sources": [
    {
      "type": "annual_report | ir_site | edisclosure | broker_research | press_release | news",
      "title": "название или краткое описание источника",
      "year": 2024,
      "url": "URL если найден",
      "retrieved_at": "YYYY-MM-DD"
    }
  ]
}"""


def make_user_prompt(ticker: str, name: str, sector: str) -> str:
    return f"""Компания: {name} (тикер: {ticker})
Сектор: {sector}

Используй web_search чтобы найти:
1. Последний годовой отчёт или отчётность по МСФО (2023–2024)
2. Структуру бизнеса и выручки по сегментам с долями
3. Основных конкурентов и долю рынка
4. Ключевые макрофакторы, влияющие на компанию
5. Регуляторов, ключевые нормативы и регуляторные риски
6. Ключевые операционные и финансовые метрики (специфичные для сектора)

Заполни JSON строго по этой схеме (верни ТОЛЬКО JSON, без markdown):
{JSON_SCHEMA_GUIDE}"""


# ─── Helpers ──────────────────────────────────────────────────────────────────

def extract_json(text: str) -> dict:
    text = text.strip()

    # Strip markdown code fences if present
    md_match = re.search(r"```(?:json)?\s*([\s\S]*?)```", text)
    if md_match:
        text = md_match.group(1).strip()

    def _try_parse(s: str) -> dict:
        s = re.sub(r",(\s*[}\]])", r"\1", s)  # trailing commas
        try:
            return json.loads(s)
        except json.JSONDecodeError:
            # Strip only standalone comment lines (not inside strings — avoids killing URLs)
            cleaned = re.sub(r"^\s*//[^\n]*\n?", "", s, flags=re.MULTILINE)
            return json.loads(re.sub(r",(\s*[}\]])", r"\1", cleaned))

    # Try direct parse first
    try:
        return _try_parse(text)
    except json.JSONDecodeError:
        # Claude sometimes adds commentary before/after the JSON block — extract it
        json_match = re.search(r"\{[\s\S]*\}", text)
        if json_match:
            return _try_parse(json_match.group(0))
        raise


REQUIRED_CHECKS = [
    ("meta.name_full",                  lambda p: bool(p.get("meta", {}).get("name_full"))),
    ("meta.industry",                   lambda p: bool(p.get("meta", {}).get("industry"))),
    ("description.short",               lambda p: len(p.get("description", {}).get("short", "")) > 20),
    ("description.long",                lambda p: len(p.get("description", {}).get("long", "")) > 100),
    ("description.history_brief",       lambda p: bool(p.get("description", {}).get("history_brief"))),
    ("business_essence.what_company_does", lambda p: bool(p.get("business_essence", {}).get("what_company_does"))),
    ("business_essence.value_proposition", lambda p: bool(p.get("business_essence", {}).get("value_proposition"))),
    ("revenue_streams ≥1",              lambda p: len(p.get("revenue_streams", [])) >= 1),
    ("revenue_streams ≥2",              lambda p: len(p.get("revenue_streams", [])) >= 2),
    ("geography ≥1",                    lambda p: len(p.get("geography", [])) >= 1),
    ("clients.types",                   lambda p: bool(p.get("clients", {}).get("types"))),
    ("clients.notes",                   lambda p: bool(p.get("clients", {}).get("notes"))),
    ("cost_structure.main_cost_items",  lambda p: bool(p.get("cost_structure", {}).get("main_cost_items"))),
    ("cost_structure.margin_drivers",   lambda p: bool(p.get("cost_structure", {}).get("margin_drivers"))),
    ("competitive_position.competitors≥3", lambda p: len(p.get("competitive_position", {}).get("main_competitors", [])) >= 3),
    ("competitive_position.moats",      lambda p: bool(p.get("competitive_position", {}).get("moats"))),
    ("competitive_position.vulnerabilities", lambda p: bool(p.get("competitive_position", {}).get("vulnerabilities"))),
    ("regulatory_context.key_regulators", lambda p: bool(p.get("regulatory_context", {}).get("key_regulators"))),
    ("key_metrics_to_watch ≥2",         lambda p: len(p.get("key_metrics_to_watch", [])) >= 2),
    ("macro_sensitivities ≥3",          lambda p: len(p.get("macro_sensitivities", [])) >= 3),
    ("sector_specific non-empty",       lambda p: bool(p.get("sector_specific"))),
    ("sources ≥1",                      lambda p: len(p.get("sources", [])) >= 1),
]


def compute_completeness(profile: dict) -> tuple[int, list[str]]:
    missing = []
    passed = 0
    for name, check in REQUIRED_CHECKS:
        try:
            ok = check(profile)
        except Exception:
            ok = False
        if ok:
            passed += 1
        else:
            missing.append(name)
    pct = round(passed / len(REQUIRED_CHECKS) * 100)
    return pct, missing


def load_log() -> dict:
    if LOG_FILE.exists():
        entries = json.loads(LOG_FILE.read_text(encoding="utf-8"))
        return {e["ticker"]: e for e in entries}
    return {}


def save_log(by_ticker: dict) -> None:
    PROFILES_DIR.mkdir(parents=True, exist_ok=True)
    LOG_FILE.write_text(
        json.dumps(list(by_ticker.values()), ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


# ─── Core ─────────────────────────────────────────────────────────────────────

def build_profile(client: anthropic.Anthropic, ticker: str, name: str, sector: str) -> tuple[dict | None, dict]:
    user_prompt = make_user_prompt(ticker, name, sector)
    last_error: Exception | None = None

    for attempt in range(1, 4):
        print(f"  → Claude API attempt {attempt}/3 (web search, streaming)...")
        try:
            raw_text = ""
            with client.messages.stream(
                model="claude-opus-4-7",
                max_tokens=16000,
                tools=[{"type": "web_search_20250305", "name": "web_search", "max_uses": 8}],
                system=SYSTEM_PROMPT,
                messages=[{"role": "user", "content": user_prompt}],
                extra_headers={"anthropic-beta": "web-search-2025-03-05"},
            ) as stream:
                for chunk in stream.text_stream:
                    raw_text += chunk
                    print(".", end="", flush=True)
                print()

            if not raw_text.strip():
                raise ValueError("Empty response from API")

            profile = extract_json(raw_text)
            completeness_pct, missing = compute_completeness(profile)
            profile.setdefault("meta", {})["completeness_pct"] = completeness_pct
            quality = profile.get("meta", {}).get("data_quality", "medium")

            return profile, {
                "ticker": ticker,
                "status": "ok",
                "completeness_pct": completeness_pct,
                "data_quality": quality,
                "fields_missing": missing,
                "sources_found": len(profile.get("sources", [])),
                "timestamp": datetime.now().isoformat(),
                "error": None,
            }

        except Exception as exc:
            last_error = exc
            print(f"\n  ✗ Attempt {attempt} failed: {exc}")
            if attempt < 3:
                print("    Retrying...")

    return None, {
        "ticker": ticker,
        "status": "error",
        "completeness_pct": 0,
        "data_quality": None,
        "fields_missing": [],
        "sources_found": 0,
        "timestamp": datetime.now().isoformat(),
        "error": str(last_error),
    }


def run(tickers: list[str]) -> None:
    PROFILES_DIR.mkdir(parents=True, exist_ok=True)

    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        sys.exit("Error: ANTHROPIC_API_KEY not set")

    client = anthropic.Anthropic(api_key=api_key)

    # Load company metadata from DB
    db = SessionLocal()
    try:
        db_companies = {
            c.ticker: {"name": c.name, "sector": c.sector or "Прочее"}
            for c in db.query(Company).all()
        }
    finally:
        db.close()

    log_by_ticker = load_log()

    for ticker in tickers:
        print(f"\n{'─'*55}")
        print(f"  {ticker}")
        print(f"{'─'*55}")

        meta = db_companies.get(ticker, {"name": ticker, "sector": "Прочее"})
        if ticker not in db_companies:
            print(f"  [WARN] {ticker} not found in DB — using defaults")

        profile, log_entry = build_profile(client, ticker, meta["name"], meta["sector"])

        if profile is not None:
            out_path = PROFILES_DIR / f"{ticker}.json"
            out_path.write_text(
                json.dumps(profile, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
            q = log_entry["data_quality"]
            pct = log_entry["completeness_pct"]
            src = log_entry["sources_found"]
            miss = len(log_entry["fields_missing"])
            print(f"  ✓ {out_path.name}  |  completeness={pct}%  quality={q}  sources={src}  missing={miss}")
        else:
            print(f"  ✗ Failed — see log for details")

        log_by_ticker[ticker] = log_entry
        save_log(log_by_ticker)  # Save after each ticker so progress isn't lost

    print(f"\n{'═'*55}")
    print(f"  Done. Log: {LOG_FILE}")
    print(f"{'═'*55}\n")


def main():
    parser = argparse.ArgumentParser(description="Build company business-model profiles via Claude API")
    parser.add_argument("--tickers", required=True, help="Comma-separated tickers, e.g. SBER,LKOH,YDEX,GMKN")
    args = parser.parse_args()

    tickers = [t.strip().upper() for t in args.tickers.split(",") if t.strip()]
    if not tickers:
        sys.exit("No tickers provided")

    print(f"\nCompanies to process: {', '.join(tickers)}")
    run(tickers)


if __name__ == "__main__":
    main()

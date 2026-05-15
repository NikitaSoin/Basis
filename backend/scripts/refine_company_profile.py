"""
Refines existing company profiles to schema v2 + FY-2025 data.
Prompt caching on the stable system portion reduces cost for repeated runs.

Usage (from backend/):
    python -m scripts.refine_company_profile --tickers SBER,LKOH,YDEX,GMKN
"""
import argparse
import json
import os
import re
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from dotenv import load_dotenv
load_dotenv(Path(__file__).parent.parent / ".env")

import anthropic

PROFILES_DIR = Path(__file__).parent.parent / "data" / "company_profiles"
LOG_FILE = PROFILES_DIR / "_refine_log.json"
TODAY = datetime.now().strftime("%Y-%m-%d")

ALLOWED_MACRO_FACTORS = frozenset({
    "key_rate", "inflation", "gdp", "ruble",
    "commodity_prices", "sanctions", "global_demand",
})

# ─── System prompt — stable, cached across all 4 company calls ────────────────

SYSTEM_PROMPT = f"""Ты — старший аналитик финансовых рынков. Задача: доработать JSON-профиль компании \
по инструкции, не переписывая с нуля.

═══════════════════════ ПРИНЦИПЫ РАБОТЫ ═══════════════════════

1. Сохраняй весь существующий контент если нет явной инструкции на изменение.
2. Обновляй только поля, указанные в инструкции компании.
3. Для получения финансовых данных (FY 2025) используй web_search.
4. Верни ТОЛЬКО валидный JSON. Никакого markdown, никакого текста до или после.
5. Перед финальным JSON убедись, что все правила валидации выполнены.

═══════ НОВЫЕ И ИЗМЕНЁННЫЕ ПОЛЯ СХЕМЫ (обязательны для всех) ═══════

§1 meta.data_as_of (новое поле, string)
   Период данных в профиле. НЕ путать с meta.last_updated (дата генерации файла).
   Формат: "FY YYYY МСФО", "FY YYYY МСФО + Q1 YYYY+1", "FY YYYY РСБУ" и т.п.
   Примеры: "FY 2025 МСФО", "FY 2025 МСФО + Q1 2026"

§2 revenue_breakdown_basis (top-level field, string)
   Объясняет базис для долей в revenue_streams.
   Значения: "consolidated_revenue (МСФО FY YYYY)" | "net_operating_income (МСФО FY YYYY)" |
             "segment_revenue (МСФО FY YYYY)" | другое с пояснением.
   Все доли в revenue_streams ДОЛЖНЫ быть на ОДНОМ базисе. Сумма share_pct: 98–102%.

§3 competitive_position — новая структура:
   {{
     "market_share_pct": <число или null>,
     "market_share_scope": "<явное описание рынка: напр. 'депозиты физлиц РФ'>",
     "market_rank": <число или null>,
     "main_competitors": ["VTBR (ВТБ)", "TCSG (Т-Технологии)"],
     "non_public_competitors": ["Альфа-Банк", "Газпромбанк"],
     "global_peers": ["JPMorgan Chase", "BNP Paribas"],
     "moats": [...],
     "vulnerabilities": [...]
   }}
   main_competitors = ТОЛЬКО компании, торгующиеся на Московской бирже, с тикером.
   Непубличные российские компании → non_public_competitors.
   Иностранные аналоги → global_peers.

§4 macro_sensitivities — СТРОГО макроэкономические факторы:
   Разрешённые значения поля "factor":
     "key_rate"          — ключевая ставка ЦБ РФ
     "inflation"         — инфляция потребительская в РФ
     "gdp"               — динамика ВВП РФ
     "ruble"             — курс рубля к USD/EUR/CNY
     "commodity_prices"  — цены на commodities (нефть, металлы, газ)
     "sanctions"         — международные санкции
     "global_demand"     — мировой спрос / глобальная рецессия

   Что НЕ должно быть в macro_sensitivities (перенести в regulatory_context):
     - НДПИ, экспортные пошлины, таможенные сборы
     - Квоты ОПЕК+, производственные ограничения
     - Макропруденциальные надбавки и нормативы ЦБ
     - Отраслевые налоги и регуляторные условия
   Перенести в regulatory_context.key_regulations или regulatory_context.notes.

═══════════════ ПРАВИЛА ВАЛИДАЦИИ (проверь перед генерацией) ═══════════════

R1. sum(revenue_streams[*].share_pct) ∈ [98, 102]. Если нет — исправить.
R2. sum(geography[*].share_pct) ∈ [98, 102]. Если нет — исправить.
R3. meta.data_as_of заполнено (не null, не пустая строка).
R4. competitive_position.market_share_scope заполнено.
R5. revenue_breakdown_basis (top-level) заполнено.
R6. Все macro_sensitivities имеют factor из разрешённого списка §4.
R7. Все sources.url содержат конкретный путь (не только домен).
    Некорректно: "https://sberbank.ru/"
    Корректно:   "https://ir.sberbank.ru/ru/reports/annual-report/2025"

Сегодняшняя дата (last_updated): {TODAY}
"""

# ─── Company-specific change instructions ─────────────────────────────────────

COMPANY_CHANGES: dict[str, str] = {
    "SBER": """
ИНСТРУКЦИЯ ПО ДОРАБОТКЕ: СБЕРБАНК (SBER)

1. ФИНАНСОВЫЕ ДАННЫЕ → FY 2025 МСФО
   web_search: "Сбербанк финансовые результаты 2025 годовой отчёт МСФО чистая прибыль NIM ROE"
   Обновить: чистая прибыль, NII, NFI, ROE, NIM, CIR, COR, кредитный портфель, депозиты, CAR.
   meta.data_as_of = "FY 2025 МСФО" (или + Q1 2026 если отчётность доступна).

2. ГАЙДЕНС → обнови на 2026 год (текущий на 2025 устарел).

3. sector_specific → обнови ВСЕ числа до FY 2025:
   nim_pct, roe_pct, cir_pct, cor_pct, net_profit_bln_rub, nii_bln_rub, nfi_bln_rub,
   loan_portfolio_trln_rub, deposits_trln_rub, car_pct, retail_deposit_market_share_pct.

4. competitive_position:
   market_share_scope = "депозиты физлиц РФ"
   main_competitors (только MOEX): ["VTBR (ВТБ)", "TCSG (Т-Технологии)", "SVCB (Совкомбанк)", "BSPB (Банк Санкт-Петербург)"]
   non_public_competitors: ["Альфа-Банк", "Газпромбанк", "Россельхозбанк"]
   global_peers: ["JPMorgan Chase", "BNP Paribas", "Raiffeisen Bank (иностр. аналог)"]

5. vulnerabilities → убрать любые пункты о "диверсифицированной клиентской базе" (не уязвимость).

6. macro_sensitivities → перенести в regulatory_context любые упоминания:
   макропруденциальных надбавок, нормативов ЦБ, банковского регулирования.

7. revenue_breakdown_basis = "net_operating_income (МСФО FY 2025)"
   Проверь сумму revenue_streams = 100% на базисе NII + NFI.
""",

    "LKOH": """
ИНСТРУКЦИЯ ПО ДОРАБОТКЕ: ЛУКОЙЛ (LKOH)

1. ФИНАНСОВЫЕ ДАННЫЕ → FY 2025 МСФО
   web_search: "Лукойл финансовые результаты 2025 МСФО выручка EBITDA деконсолидация LIG убыток"
   Ключевые события FY 2025:
   - Деконсолидация Lukoil International Group (LIG) → разовый убыток ~1.059 трлн руб.
   - Продажа LIG компании Carlyle (январь 2026).
   - Уточни: выручка, EBITDA, FCF после деконсолидации.
   meta.data_as_of = "FY 2025 МСФО (после деконсолидации LIG)"

2. revenue_streams → ПЕРЕСМОТРИ после деконсолидации LIG.
   В description каждого сегмента добавь пометку: "после деконсолидации LIG (FY 2025)".
   Проверь сумму долей = 100%.
   revenue_breakdown_basis = "consolidated_revenue (МСФО FY 2025, после деконсолидации LIG)"

3. geography → обнови после деконсолидации LIG.
   Добавь примечание: "после продажи LIG компании Carlyle (январь 2026)".
   Проверь сумму = 100%.

4. sector_specific → обнови все числа до FY 2025 (выручка, EBITDA, чистый убыток, чистый долг, добыча).

5. Дивиденды: 1014 руб/акция = суммарные дивиденды за ВЕСЬ 2024 год (финальный + промежуточный).
   Это не гайденс на будущее. Перепиши корректно.

6. competitive_position:
   market_share_scope = "добыча нефти в РФ"
   main_competitors (MOEX): ["ROSN (Роснефть)", "SIBN (Газпром нефть)", "TATN (Татнефть)"]
   non_public_competitors: ["Сургутнефтегаз (квазипубличная)", "Газпром (нефтяные активы)"]
   global_peers: ["Shell", "BP", "TotalEnergies", "ExxonMobil"]

7. macro_sensitivities → перенести в regulatory_context:
   НДПИ, экспортные пошлины, квоты ОПЕК+, ценовые потолки.
""",

    "YDEX": """
ИНСТРУКЦИЯ ПО ДОРАБОТКЕ: ЯНДЕКС (YDEX)

1. ФИНАНСОВЫЕ ДАННЫЕ → FY 2025 МСФО
   web_search: "Яндекс финансовые результаты 2025 годовой выручка EBITDA чистая прибыль"
   web_search: "Яндекс Плюс подписчики 2025 количество"
   Обновить: выручка, скорр. EBITDA, чистая прибыль, ARPU, подписчики Яндекс Плюс (конец 2025).
   Текущие данные (FY 2024, подписчики 32.7 млн Q1 2024) устарели на год+.
   meta.data_as_of = "FY 2025 МСФО" (или + Q1 2026 если доступно).

2. ГАЙДЕНС → обнови на 2026 год.

3. revenue_streams → ПЕРЕСОБЕРИ по данным FY 2025 (сумма = 100%).
   Источник: сегментные данные из квартальных и годового IR-релизов.
   revenue_breakdown_basis = "consolidated_revenue (МСФО FY 2025)"

4. competitive_position:
   market_share_scope = "поиск в РФ"
   main_competitors (только MOEX): если есть публичные конкуренты, указать. Если нет — пустой список с пояснением.
   non_public_competitors: ["Wildberries (e-com)", "ВКонтакте/Mail.ru (если непубличные)", "Ozon (публичный OZON)"]
   Примечание: OZON публичный → в main_competitors если конкурент.
   global_peers: ["Google", "Alibaba", "Baidu"]

5. sources → убери Yahoo Finance UK, Statista.
   Замени на: IR-сайт Яндекса, пресс-релизы с результатами за FY 2025.
   web_search: "ir.yandex.ru финансовые результаты 2025 годовой отчёт"

6. macro_sensitivities → перенести в regulatory_context:
   законы о персональных данных, оборотные штрафы, регуляторные требования к маркетплейсам.
""",

    "GMKN": """
ИНСТРУКЦИЯ ПО ДОРАБОТКЕ: НОРИЛЬСКИЙ НИКЕЛЬ (GMKN)

1. ФИНАНСОВЫЕ ДАННЫЕ → FY 2025 (или FY 2024 если 2025 недоступен)
   web_search: "Норильский никель финансовые результаты 2025 выручка EBITDA производство металлы"
   web_search: "Норникель структура выручки по металлам 2024 палладий никель медь платина"
   meta.data_as_of = "FY 2025 МСФО" или "FY 2024 МСФО" (в зависимости от доступности).

2. КРИТИЧНО — revenue_streams: ПОЛНОСТЬЮ ПЕРЕДЕЛАТЬ ПО МЕТАЛЛАМ.
   Текущая структура по дивизионам (GMK Group, Kola) — НЕВЕРНАЯ для этого поля.
   Нужна структура ПО ПРОДУКТАМ (металлам) с долями от выручки:
   [
     {{"segment": "Палладий", "share_pct": 40, "year": 2024, "description": "...", "trend": "..."}},
     {{"segment": "Никель", "share_pct": 27, "year": 2024, ...}},
     {{"segment": "Медь", "share_pct": 17, "year": 2024, ...}},
     {{"segment": "Платина", "share_pct": 9, "year": 2024, ...}},
     {{"segment": "Прочие металлы и попутная продукция", "share_pct": 7, "year": 2024, ...}}
   ]
   Найди реальные доли через web_search. Сумма = 100%.
   Единицы: ТОЛЬКО % от выручки. Не смешивать с тоннами/унциями в share_pct.
   revenue_breakdown_basis = "consolidated_revenue (МСФО FY 2024)" или FY 2025.

3. competitive_position:
   market_share_scope = "мировой рынок палладия"
   main_competitors: В РФ нет публичных прямых конкурентов → main_competitors = []
   Добавить: "market_no_public_competitors_note": "На Московской бирже нет прямых публичных конкурентов по палладию и никелю"
   global_peers: ["Anglo American Platinum (Amplats)", "Sibanye-Stillwater", "Impala Platinum (Implats)", "Vale (никель)", "Glencore"]

4. sector_specific → унифицировать единицы. Все объёмы производства — в тыс. т (не смешивать тыс. т и т).

5. sources → убери Wikipedia и rogtecmagazine.com.
   Замени на официальные: IR-сайт Норникеля, годовые отчёты МСФО, пресс-релизы.
   web_search: "Норникель годовой отчёт 2024 IR инвесторам"

6. macro_sensitivities → перенести в regulatory_context:
   санкции на конкретные биржи (LME), экспортные пошлины на металлы.
""",
}

# ─── Helpers ──────────────────────────────────────────────────────────────────

def extract_json(text: str) -> dict:
    text = text.strip()
    md_match = re.search(r"```(?:json)?\s*([\s\S]*?)```", text)
    if md_match:
        text = md_match.group(1).strip()

    def _try(s: str) -> dict:
        s = re.sub(r",(\s*[}\]])", r"\1", s)
        try:
            return json.loads(s)
        except json.JSONDecodeError:
            cleaned = re.sub(r"^\s*//[^\n]*\n?", "", s, flags=re.MULTILINE)
            return json.loads(re.sub(r",(\s*[}\]])", r"\1", cleaned))

    try:
        return _try(text)
    except json.JSONDecodeError:
        m = re.search(r"\{[\s\S]*\}", text)
        if m:
            return _try(m.group(0))
        raise


def is_specific_url(url: str) -> bool:
    if not url or url.strip() in ("", "#"):
        return False
    path = re.sub(r"^https?://", "", url.strip()).rstrip("/")
    return "/" in path


def validate_profile(profile: dict) -> list[str]:
    errors: list[str] = []

    # R1 revenue_streams sum
    streams = profile.get("revenue_streams", [])
    if streams:
        total = sum(s.get("share_pct", 0) for s in streams
                    if isinstance(s.get("share_pct"), (int, float)))
        if not (98 <= total <= 102):
            errors.append(f"R1: revenue_streams sum={total}% (expected 98–102%)")

    # R2 geography sum
    geo = profile.get("geography", [])
    if geo:
        total = sum(g.get("share_pct", 0) for g in geo
                    if isinstance(g.get("share_pct"), (int, float)))
        if not (98 <= total <= 102):
            errors.append(f"R2: geography sum={total}% (expected 98–102%)")

    # R3 meta.data_as_of
    if not profile.get("meta", {}).get("data_as_of"):
        errors.append("R3: meta.data_as_of is missing or empty")

    # R4 market_share_scope
    if not profile.get("competitive_position", {}).get("market_share_scope"):
        errors.append("R4: competitive_position.market_share_scope is missing")

    # R5 revenue_breakdown_basis
    if not profile.get("revenue_breakdown_basis"):
        errors.append("R5: revenue_breakdown_basis (top-level) is missing")

    # R6 macro_sensitivities factors
    for ms in profile.get("macro_sensitivities", []):
        factor = ms.get("factor", "")
        if factor not in ALLOWED_MACRO_FACTORS:
            errors.append(f"R6: macro_sensitivity factor '{factor}' not allowed")

    # R7 source URLs
    for s in profile.get("sources", []):
        url = s.get("url") or ""
        if not is_specific_url(url):
            title = s.get("title") or s.get("type") or "?"
            errors.append(f"R7: source '{title}' has no specific URL: '{url}'")

    return errors


def load_log() -> dict:
    if LOG_FILE.exists():
        entries = json.loads(LOG_FILE.read_text(encoding="utf-8"))
        return {e["ticker"]: e for e in (entries if isinstance(entries, list) else [])}
    return {}


def save_log(by_ticker: dict) -> None:
    LOG_FILE.write_text(
        json.dumps(list(by_ticker.values()), ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


# ─── Core ─────────────────────────────────────────────────────────────────────

def refine_profile(
    client: anthropic.Anthropic,
    ticker: str,
    existing: dict,
    changes: str,
) -> tuple[dict | None, dict]:
    existing_json_str = json.dumps(existing, ensure_ascii=False, indent=2)

    user_prompt = f"""Существующий профиль {ticker} — СОХРАНЯЙ всё, что не указано в инструкции:

```json
{existing_json_str}
```

---

{changes}

Найди актуальные данные через web_search по указанным запросам, примени все изменения, \
верни ПОЛНЫЙ обновлённый JSON (не только изменённые поля). Без markdown, без текста до или после.
"""

    last_error: Exception | None = None

    for attempt in range(1, 4):
        print(f"  → Attempt {attempt}/3 (cached system + web search)...")
        try:
            raw_text = ""
            with client.messages.stream(
                model="claude-opus-4-7",
                max_tokens=16000,
                system=[
                    {
                        "type": "text",
                        "text": SYSTEM_PROMPT,
                        "cache_control": {"type": "ephemeral"},
                    }
                ],
                tools=[{
                    "type": "web_search_20250305",
                    "name": "web_search",
                    "max_uses": 10,
                }],
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
            profile.setdefault("meta", {})["last_updated"] = TODAY

            validation_errors = validate_profile(profile)
            if validation_errors:
                err_str = "; ".join(validation_errors)
                raise ValueError(f"Validation failed: {err_str}")

            return profile, {
                "ticker": ticker,
                "status": "ok",
                "validation_errors": [],
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
        "validation_errors": [],
        "timestamp": datetime.now().isoformat(),
        "error": str(last_error),
    }


# ─── Entry point ──────────────────────────────────────────────────────────────

def run(tickers: list[str]) -> None:
    PROFILES_DIR.mkdir(parents=True, exist_ok=True)

    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        sys.exit("Error: ANTHROPIC_API_KEY not set")

    client = anthropic.Anthropic(api_key=api_key)
    log_by_ticker = load_log()

    for ticker in tickers:
        print(f"\n{'─'*55}")
        print(f"  {ticker}")
        print(f"{'─'*55}")

        src = PROFILES_DIR / f"{ticker}.json"
        if not src.exists():
            print(f"  ✗ {ticker}.json not found — skipping")
            log_by_ticker[ticker] = {
                "ticker": ticker, "status": "skipped",
                "validation_errors": [],
                "timestamp": datetime.now().isoformat(),
                "error": "source file not found",
            }
            save_log(log_by_ticker)
            continue

        existing = json.loads(src.read_text(encoding="utf-8"))
        changes = COMPANY_CHANGES.get(ticker, "")
        if not changes:
            print(f"  ✗ No change instructions defined for {ticker}")
            continue

        profile, log_entry = refine_profile(client, ticker, existing, changes)

        if profile is not None:
            src.write_text(
                json.dumps(profile, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
            print(f"  ✓ {ticker}.json saved  (validation: OK)")
        else:
            print(f"  ✗ {ticker} failed after 3 attempts — original file UNCHANGED")

        log_by_ticker[ticker] = log_entry
        save_log(log_by_ticker)

    print(f"\n{'═'*55}")
    print(f"  Done. Refine log: {LOG_FILE}")
    print(f"{'═'*55}\n")


def main() -> None:
    parser = argparse.ArgumentParser(description="Refine company profiles to schema v2 + FY-2025 data")
    parser.add_argument("--tickers", required=True, help="Comma-separated: SBER,LKOH,YDEX,GMKN")
    args = parser.parse_args()
    tickers = [t.strip().upper() for t in args.tickers.split(",") if t.strip()]
    if not tickers:
        sys.exit("No tickers provided")
    print(f"\nRefining: {', '.join(tickers)}")
    run(tickers)


if __name__ == "__main__":
    main()

"""ИИ-ассистент — диалоговый слой поверх контура Basis.

Двухшаговый пайплайн (по образцу observer_report.py):
  1. РАСПОЗНАВАНИЕ — LLM извлекает из вопроса пользователя тикеры (из реального
     списка компаний платформы) и намерения (скринер/макро/новости).
  2. СБОР КОНТЕКСТА — детерминированный код читает РЕАЛЬНЫЕ данные (те же файлы
     и таблицы, что отдают company-эндпоинты): *_summary.md, company_metrics,
     котировки, лента новостей.
  3. СИНТЕЗ — LLM формулирует ответ СТРОГО по переданному контексту, с ссылками
     на источники, без «купить/продать» и без чисел из памяти модели.

Если распознавание не нашло ни одного тикера/намерения — синтез идёт с пустым
контекстом и явной инструкцией не выдумывать (честно отвечает «нет данных» /
просит уточнить компанию).
"""
from __future__ import annotations

import json
import logging
import re
import time
from datetime import datetime, timezone
from pathlib import Path

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.models.assistant import Conversation, Message

logger = logging.getLogger(__name__)

COMPANIES_DIR = Path(__file__).parent.parent.parent / "companies"

_MAX_HISTORY_MESSAGES = 8  # сколько последних сообщений диалога подмешиваем в контекст
# Потолки агентского цикла (лимиты — кодом, а не «дисциплиной промпта»):
# 5 шагов хватает на «найти бумагу → открыть её → сверить с разбором», а
# результаты инструментов остаются в диалоге и дорожают каждый следующий шаг.
_TOOL_MAX_STEPS = 5
_TOOL_TOKEN_BUDGET = 60_000
_MAX_TICKERS_PER_TURN = 8  # не даём одному вопросу утянуть контекст на пол-рынка
# Было 4 — владелец попросил сравнить мультипликаторы банков, LLM-экстрактор
# честно нашёл 13 тикеров (SBER/SBERP/VTBR/BSPB/BSPBP/CBOM/...), код обрезал до
# 4 → ВТБ/Т-Технологии выпали из детального контекста и в ответе появилось
# «данных нет», хотя карточка компании их показывает. 8 — компромисс: покрывает
# типичные «сравни топ-N» вопросы, не раздувает контекст на весь сектор целиком.


# ----------------------------- Список компаний (кэш) -----------------------------
_TICKER_LIST_CACHE: dict = {"text": None, "ts": 0.0}
_TICKER_LIST_TTL = 3600.0


def _ticker_list_text(db: Session) -> str:
    """Стабильный (кэшируемый провайдером) список 'TICKER: Имя (Сектор)' — по
    одному на строку, отсортирован. Сектор добавлен (2026-07-25) — без него
    LLM не смогла опознать «Т-Технологии» как банк по одному имени (в вопросе
    «сравни банки» тикер T не попал в список вовсе, хотя это T-Банк) — с
    сектором «Финансы» рядом у модели есть за что зацепиться. Список меняется
    редко (только когда добавляются компании), поэтому системный промпт
    распознавания остаётся стабильным между вызовами (см. заметку про
    DeepSeek prefix-cache в llm.py)."""
    now = time.time()
    if _TICKER_LIST_CACHE["text"] and now - _TICKER_LIST_CACHE["ts"] < _TICKER_LIST_TTL:
        return _TICKER_LIST_CACHE["text"]
    rows = db.execute(text("SELECT ticker, name, sector FROM companies ORDER BY ticker")).all()
    txt = "\n".join(f"{r.ticker}: {r.name}" + (f" ({r.sector})" if r.sector else "") for r in rows)
    _TICKER_LIST_CACHE["text"] = txt
    _TICKER_LIST_CACHE["ts"] = now
    return txt


# ----------------------------- Шаг 1: распознавание -----------------------------
_EXTRACT_SYSTEM_PREFIX = (
    "Ты — диспетчер вопросов инвестора об российском фондовом рынке для платформы "
    "Basis. Твоя ЕДИНСТВЕННАЯ задача — понять, какие данные нужны, чтобы ответить, "
    "а НЕ отвечать самому. Извлеки из вопроса пользователя:\n"
    "- tickers: список тикеров компаний из СПИСКА НИЖЕ, которые упоминаются в вопросе "
    "(по названию, отрасли-намёку или тикеру напрямую). Пусто, если компания не "
    "упомянута. Бери ТОЛЬКО тикеры из списка, не выдумывай.\n"
    "- wants_screener: true, если вопрос просит найти/отфильтровать/отсортировать "
    "список компаний по критерию (P/E, дивдоходность, апсайд и т.п.).\n"
    "- wants_macro: true, если вопрос про макроэкономику РФ в целом (ставка, инфляция, "
    "курс) без привязки к конкретной компании.\n"
    "- wants_news: true, если вопрос про свежие новости/события.\n"
    "- wants_report: true, ТОЛЬКО если пользователь прямо просит СГЕНЕРИРОВАТЬ "
    "документ-обзор («сделай отчёт», «дай сводку по рынку», «ИИ-обзор», «утренний "
    "обзор»). Обычный вопрос — даже про портфель целиком («что у меня в портфеле», "
    "«какие риски у моих бумаг», «что с моими акциями») — это НЕ отчёт: на него "
    "отвечают данными, а не генерацией документа. Сомневаешься — false.\n"
    "- report_topic: если wants_report — тема из списка: \"biz\" (бизнес/отчётности "
    "компаний), \"macro\" (макроэкономика), \"geo\" (геополитика), \"institutions\" "
    "(институциональная среда), \"mixed\" (общий/не уточнил). Иначе null.\n"
    "- report_depth: если wants_report — глубина: \"express\" (короткая сводка, "
    "по умолчанию), \"detailed\" (подробный, неделя), \"deep\" (глубокий, месяц). "
    "Иначе null.\n"
    "- sector_group: если вопрос про ГРУППУ компаний БЕЗ явных имён («сравни банки», "
    "«что с металлургами», «нефтянка сейчас») — код группы: \"banks\" (банки), "
    "\"oil_gas\", \"metals\", \"it\", \"realty\" (девелоперы), \"retail\", "
    "\"telecom\", \"utilities\" (электроэнергетика), \"transport\", \"chem\", "
    "\"machinery\", \"health\", \"finance_other\". Иначе null. Тикеры при этом "
    "всё равно постарайся выбрать из списка.\n"
    "- scope: область вопроса — \"platform\" (про конкретные компании/цифры/данные "
    "платформы), \"general\" (общие знания: что такое индикатор/термин, как работает "
    "инструмент, внешняя политика, мировые рынки, история — БЕЗ запроса конкретных "
    "текущих цифр наших компаний), \"mixed\" (и то и то).\n"
    "Верни строго JSON: {\"tickers\": [...], \"sector_group\": str|null, \"wants_screener\": bool, "
    "\"wants_macro\": bool, \"wants_news\": bool, \"wants_report\": bool, "
    "\"report_topic\": str|null, \"report_depth\": str|null, \"scope\": str}\n\n"
    "СПИСОК КОМПАНИЙ ПЛАТФОРМЫ (тикер: имя):\n"
)


def _extract_entities(db: Session, user_message: str, history_text: str) -> dict:
    from app.services.llm import complete, LLMError
    system = _EXTRACT_SYSTEM_PREFIX + _ticker_list_text(db)
    user_content = (f"Недавний диалог (для контекста, если вопрос ссылается на "
                    f"предыдущий):\n{history_text}\n\nВопрос: {user_message}") if history_text else \
                   f"Вопрос: {user_message}"
    _FALLBACK = {"tickers": [], "wants_screener": False, "wants_macro": False,
                 "wants_news": False, "wants_report": False, "report_topic": None,
                 "report_depth": None, "scope": "platform"}
    try:
        result = complete(system, user_content, json_mode=True, thinking=False,
                          max_tokens=400, temperature=0.0)
    except LLMError:
        logger.exception("Ассистент: распознавание намерения не удалось")
        return dict(_FALLBACK)
    if not isinstance(result, dict):
        return dict(_FALLBACK)
    tickers = result.get("tickers") or []
    if not isinstance(tickers, list):
        tickers = []
    topic = result.get("report_topic")
    depth = result.get("report_depth")
    return {
        "tickers": [str(t).upper() for t in tickers[:_MAX_TICKERS_PER_TURN] if t],
        "wants_screener": bool(result.get("wants_screener")),
        "wants_macro": bool(result.get("wants_macro")),
        "wants_news": bool(result.get("wants_news")),
        "wants_report": bool(result.get("wants_report")),
        "report_topic": topic if topic in ("biz", "macro", "geo", "institutions", "mixed") else "mixed",
        "report_depth": depth if depth in ("express", "detailed", "deep") else "express",
        "scope": result.get("scope") if result.get("scope") in ("platform", "general", "mixed") else "platform",
        "sector_group": result.get("sector_group") if result.get("sector_group") in (
            "banks", "oil_gas", "metals", "it", "realty", "retail", "telecom",
            "utilities", "transport", "chem", "machinery", "health", "finance_other") else None,
    }


# ----------------------------- Шаг 2: сбор контекста -----------------------------
_SECTOR_GROUP_TO_DB = {
    "oil_gas": "Нефть и газ", "metals": "Металлургия", "it": "IT-сектор",
    "realty": "Девелопмент", "retail": "Потребительский сектор", "telecom": "Телеком",
    "utilities": "Электроэнергетика", "transport": "Транспорт и логистика",
    "chem": "Химия", "machinery": "Машиностроение", "health": "Здравоохранение",
    "finance_other": "Финансы",
}
_BANKS_CACHE: dict = {"ts": 0.0, "tickers": None}


def _bank_tickers() -> set[str]:
    """Тикеры с meta.profile == bank в financials.json (кэш 1ч): «банки» — это
    профиль отчётности, а не сектор БД (в «Финансах» также биржа/страховые)."""
    now = time.time()
    if _BANKS_CACHE["tickers"] is not None and now - _BANKS_CACHE["ts"] < 3600:
        return _BANKS_CACHE["tickers"]
    out = set()
    if COMPANIES_DIR.is_dir():
        for d in COMPANIES_DIR.iterdir():
            f = d / "financials.json"
            if not f.is_file():
                continue
            try:
                meta = (json.loads(f.read_text(encoding="utf-8")).get("meta") or {})
                if meta.get("profile") == "bank":
                    out.add(d.name.upper())
            except Exception:  # noqa: BLE001
                continue
    _BANKS_CACHE["tickers"] = out
    _BANKS_CACHE["ts"] = now
    return out


def _resolve_sector_group(db: Session, group: str, limit: int = 6) -> list[str]:
    """Группа («банки», «металлурги»…) → конкретные тикеры, топ по капитализации.
    Детерминированный страховочный ход: «сравни банки» без имён давал ПУСТОЙ
    контекст, и ассистент честно отвечал «нет ни одного банка» (владелец
    2026-08-08, второй заход). Префы того же эмитента (SBERP при SBER)
    отсеиваются — в сравнении групп они дублируют компанию."""
    if group == "banks":
        pool = _bank_tickers()
        if not pool:
            return []
        rows = db.execute(text(
            "SELECT ticker FROM companies WHERE ticker = ANY(:p) "
            "ORDER BY market_cap DESC NULLS LAST"), {"p": list(pool)}).all()
    else:
        sector = _SECTOR_GROUP_TO_DB.get(group)
        if not sector:
            return []
        rows = db.execute(text(
            "SELECT ticker FROM companies WHERE sector = :s "
            "ORDER BY market_cap DESC NULLS LAST"), {"s": sector}).all()
    out: list[str] = []
    for r in rows:
        t = r.ticker.upper()
        if t.endswith("P") and t[:-1] in out:
            continue
        out.append(t)
        if len(out) >= limit:
            break
    return out


def _key_financials(ticker: str) -> dict | None:
    """Компактный ЧИСЛОВОЙ срез financials.json (последние 3 года) для контекста.

    До 2026-08-08 ассистент получал только ТЕКСТЫ (summary.md) + live P/E — сами
    числа отчётности не передавались вовсе. На «сравни банки по банковским
    метрикам» это давало пустой контекст (владелец: «в присланных json ноль
    информации»): у банков вообще нет income_statement, их числа живут в
    bank_metrics/bank_pnl/bank_balance. Теперь:
    - профиль bank → NIM, стоимость риска, CIR, ROE/ROA, достаточность капитала,
      ЧПД/ЧКД/прибыль, кредиты/депозиты;
    - остальные → выручка/прибыль/EBITDA, маржа, ROE/ROA, чистый долг/EBITDA, FCF.
    ROE/ROA стандартных компаний — через units.last_to_percent: в файлах единицы
    СМЕШАНЫ (у части доли, у части проценты — memory: mixed-units-in-returns),
    сырое значение вводило бы модель в заблуждение."""
    p = COMPANIES_DIR / ticker.upper() / "financials.json"
    if not p.exists():
        return None
    try:
        j = json.loads(p.read_text(encoding="utf-8"))
    except Exception:  # noqa: BLE001
        return None
    meta = j.get("meta") or {}

    def tail(seq, n=3):
        if not isinstance(seq, list) or not seq:
            return None
        vals = seq[-n:]
        return vals if any(v is not None for v in vals) else None

    years = j.get("fiscal_years") or meta.get("fiscal_years") or []
    amount_unit = meta.get("unit") or "млн"  # у части файлов суммы в млрд (OZON) — берём из meta
    out = {
        "fiscal_years_tail": tail(years) or [],
        "units_note": f"суммы — {amount_unit} руб; рентабельности/доли — %",
        "profile": meta.get("profile") or "standard",
    }
    if out["profile"] == "bank" or j.get("bank_metrics"):
        bm = j.get("bank_metrics") or {}
        bp = j.get("bank_pnl") or {}
        bb = j.get("bank_balance") or {}
        # имена метрик в файлах разнятся (SBER: nim/cir; T: nim_pct/cir_pct/roe_adj_pct)
        _ALIASES = {"nim": ("nim", "nim_pct"), "cost_of_risk": ("cost_of_risk", "cor_pct"),
                    "cir": ("cir", "cir_pct"), "roe": ("roe", "roe_adj_pct", "roe_rep_pct"),
                    "roa": ("roa", "roa_adj_pct"),
                    "capital_adequacy": ("capital_adequacy", "capital_adequacy_h1_0_pct"),
                    "ltd": ("ltd",)}
        metrics = {}
        for canon, names in _ALIASES.items():
            for nm in names:
                v = tail(bm.get(nm))
                if v:
                    metrics[canon] = v
                    break
        pnl = {k: tail(bp.get(k)) for k in ("net_interest_income", "net_fee_income", "net_profit")}
        bal = {k: tail(bb.get(k)) for k in ("loans_net", "loans_gross", "deposits")}
        out["bank_metrics_pct"] = {k: v for k, v in metrics.items() if v}
        out["bank_pnl_mln"] = {k: v for k, v in pnl.items() if v}
        out["bank_balance_mln"] = {k: v for k, v in bal.items() if v}
    else:
        inc = j.get("income_statement") or {}
        marg = inc.get("margins") or {}
        rat = ((j.get("balance_sheet") or {}).get("ratios") or {})
        cf = j.get("cash_flow") or {}
        ret = j.get("returns") or {}
        pnl = {k: tail(inc.get(k)) for k in ("revenue", "ebitda", "net_profit")}
        out["pnl_mln"] = {k: v for k, v in pnl.items() if v}
        m = tail(marg.get("ebitda_margin"))
        if m:
            out["ebitda_margin_pct"] = m
        try:
            from app.services.units import last_to_percent
            roe = last_to_percent(j, "roe", ret.get("roe"))
            roa = last_to_percent(j, "roa", ret.get("roa"))
            if roe is not None:
                out["roe_pct_last"] = round(roe, 2)
            if roa is not None:
                out["roa_pct_last"] = round(roa, 2)
        except Exception:  # noqa: BLE001
            pass
        nd = tail(rat.get("net_debt_ebitda"), 1)
        if nd:
            out["net_debt_ebitda_last"] = nd[-1]
        fcf = tail(cf.get("fcf"))
        if fcf:
            out["fcf_mln"] = fcf
    return out


def _read_md(ticker: str, filename: str, max_chars: int) -> str | None:
    p = COMPANIES_DIR / ticker.upper() / filename
    if not p.exists():
        return None
    try:
        txt = p.read_text(encoding="utf-8").strip()
    except OSError:
        return None
    return txt[:max_chars] if txt else None


def _company_context(db: Session, ticker: str) -> dict | None:
    ticker = ticker.upper()
    row = db.execute(text("SELECT ticker, name, sector FROM companies WHERE ticker = :t"),
                     {"t": ticker}).first()
    if not row:
        return None
    price_row = db.execute(text(
        "SELECT q.close, q.date FROM quotes q JOIN companies c ON c.id = q.company_id "
        "WHERE c.ticker = :t ORDER BY q.date DESC LIMIT 1"
    ), {"t": ticker}).first()
    price = float(price_row.close) if price_row and price_row.close is not None else None
    price_date = price_row.date.isoformat() if price_row else None

    # Живые мультипликаторы от ТЕКУЩЕЙ цены — тот же приём, что в
    # portfolio.py:515-524 (eps_implied/dps_implied меняются редко, цена —
    # каждый день). Без этого поля ассистент цитировал P/E из
    # financials_summary.md, который пишется аналитиком на дату СНЭПШОТА
    # цены (иногда двухмесячной давности) — владелец поймал расхождение
    # (спросил P/E Сбербанка, получил устаревшие 4,28 вместо живых ~3,49).
    from app.models.company_metrics import CompanyMetrics
    m = db.query(CompanyMetrics).filter(CompanyMetrics.ticker == ticker).first()
    live_multiples = None
    if m:
        eps = float(m.eps_implied) if m.eps_implied is not None else None
        dps = float(m.dps_implied) if m.dps_implied is not None else None
        pe_live = round(price / eps, 2) if price and eps and eps > 0 else (
            round(float(m.pe_current), 2) if m.pe_current is not None else None)
        dy_live = round(dps / price * 100, 2) if price and dps else (
            round(float(m.div_yield), 2) if m.div_yield is not None else None)
        if pe_live is not None or dy_live is not None:
            live_multiples = {
                "pe": pe_live, "div_yield_pct": dy_live, "as_of_price_date": price_date,
                "note": ("посчитано от ТЕКУЩЕЙ цены (см. as_of_price_date) — это "
                         "приоритетный источник по P/E и дивдоходности; числа в "
                         "текстах ниже (financials_summary и др.) могли считаться "
                         "на другую, более старую дату цены"),
            }

    return {
        "ticker": row.ticker, "name": row.name, "sector": row.sector,
        "price": price,
        "price_date": price_date,
        "live_multiples": live_multiples,
        "key_financials": _key_financials(ticker),
        "business_model": _read_md(ticker, "business_model.md", 2500),
        "financials_summary": _read_md(ticker, "financials_summary.md", 2500),
        "macro_summary": _read_md(ticker, "macro_summary.md", 1800),
        "market_summary": _read_md(ticker, "market_summary.md", 1500),
        "governance_summary": _read_md(ticker, "governance_summary.md", 1200),
    }


def _screener_context(db: Session, limit: int = 15) -> list[dict]:
    """Лёгкий срез по готовым метрикам (company_metrics) — не полный BASIS-скоринг
    (он тяжелее и заточен под UI-конструктор), для чата достаточно сырых метрик:
    модель сама отсортирует/отфильтрует по вопросу пользователя из переданных строк."""
    rows = db.execute(text(
        "SELECT c.ticker, c.name, c.sector, m.pe_current, m.div_yield, m.fair_value, "
        "m.beta, m.return_total_3y, l.close AS price "
        "FROM companies c JOIN company_metrics m ON m.ticker = c.ticker "
        "LEFT JOIN LATERAL (SELECT close FROM quotes q WHERE q.company_id = c.id "
        "ORDER BY q.date DESC LIMIT 1) l ON true "
        "WHERE m.pe_current IS NOT NULL ORDER BY c.ticker"
    )).all()
    out = []
    for r in rows:
        upside = None
        if r.fair_value and r.price:
            try:
                upside = round((float(r.fair_value) / float(r.price) - 1) * 100, 1)
            except (TypeError, ZeroDivisionError):
                pass
        out.append({"ticker": r.ticker, "name": r.name, "sector": r.sector,
                    "pe": float(r.pe_current) if r.pe_current is not None else None,
                    "div_yield_pct": float(r.div_yield) if r.div_yield is not None else None,
                    "price": float(r.price) if r.price is not None else None,
                    "fair_value": float(r.fair_value) if r.fair_value is not None else None,
                    "upside_pct": upside,
                    "beta": float(r.beta) if r.beta is not None else None,
                    "return_3y_pct": float(r.return_total_3y) if r.return_total_3y is not None else None})
    return out


def _macro_context(db: Session) -> dict:
    def last(code, metric="level"):
        r = db.execute(text(
            "SELECT value, as_of FROM macro_data_points WHERE indicator_code=:c "
            "AND metric=:m ORDER BY as_of DESC LIMIT 1"
        ), {"c": code, "m": metric}).first()
        return {"value": float(r.value), "as_of": r.as_of.isoformat()} if r else None
    return {
        "key_rate": last("key_rate"),
        "inflation_yoy": last("inflation", "yoy"),
        "usdrub": last("usdrub"),
    }


def _news_context(db: Session, tickers: list[str] | None, limit: int = 8) -> list[dict]:
    from app.models.market import MarketUpdate
    q = db.query(MarketUpdate).filter(MarketUpdate.status == "published")
    rows = q.order_by(MarketUpdate.published_at.desc()).limit(60).all()
    if tickers:
        tset = set(tickers)
        filtered = [u for u in rows if set(u.affected_tickers or []) & tset]
        rows = (filtered or rows)[:limit]
    else:
        rows = rows[:limit]
    return [{"title": u.title, "impact": (u.impact_comment or "")[:200],
            "tickers": u.affected_tickers or [], "published_at": u.published_at.isoformat(),
            "url": u.source_url} for u in rows]


# ----------------------------- Шаг 3: синтез ответа -----------------------------
_ANSWER_FRAMEWORK = (
    "Ты — ИИ-ассистент инвестиционной платформы Basis для частного инвестора на "
    "российском рынке: грамотный, эрудированный аналитик-собеседник.\n\n"
    "ДВА СЛОЯ ЗНАНИЙ — строго различай:\n"
    "1. ДАННЫЕ ПЛАТФОРМЫ (JSON-контекст ниже) — единственный источник ЦИФР по "
    "конкретным компаниям/рынку: цены, P/E, дивиденды, справедливые цены, новости. "
    "Цифры такого рода из своей памяти НЕ бери НИКОГДА, даже если уверен: нет числа "
    "в контексте — скажи «этой цифры нет в переданных данных платформы».\n"
    "2. ОБЩИЕ ЗНАНИЯ (твоя эрудиция) — РАЗРЕШЕНЫ и приветствуются для всего "
    "остального: что такое финансовый индикатор/термин (полосы Боллинджера, дюрация, "
    "P/E), как работают инструменты и рынки, макроэкономические механизмы, "
    "геополитический и внешнеэкономический контекст, история рынков, общемировые "
    "компании и сектора. На такие вопросы давай ТОЛКОВЫЙ, исчерпывающий ответ — "
    "образованный собеседник, а не «этих данных нет на платформе». Числа-константы "
    "общих знаний (формулы, типовые пороги индикаторов) — можно; «текущие» рыночные "
    "цифры из памяти (курс сегодня, цена акции сейчас) — НЕЛЬЗЯ, если их нет в "
    "контексте: скажи, что за живой цифрой — к данным платформы.\n"
    "Если ответ смешанный — сначала данные платформы, затем общий контекст; "
    "помечай, где что: цифры платформы — (факт, дата), общие знания — просто "
    "нормальным текстом, а где уместно — (общие знания, не данные Basis).\n\n"
    "СТРОГО ЗАПРЕЩЕНО: рекомендации «покупать/продавать», целевые цены как совет, "
    "прогнозы будущей цены. Справедливую цену/апсайд из контекста подавай как "
    "оценку/модель Basis, а не факт и не сигнал.\n\n"
    "key_financials у компании — числовой срез отчётности за последние годы "
    "(fiscal_years_tail показывает, каким годам соответствуют списки значений; "
    "units_note — единицы). У банков это банковские метрики (nim, cost_of_risk, "
    "cir, roe, достаточность капитала, ЧПД/ЧКД) — именно по ним сравнивай банки.\n\n"
    "Если у компании в контексте есть поле live_multiples (P/E, дивдоходность) — "
    "именно эти числа приоритетны для ответа про текущий P/E/дивдоходность, а НЕ "
    "числа, упомянутые в текстах business_model/financials_summary/market_summary: "
    "эти тексты пишутся по снэпшоту на дату анализа и могут расходиться с текущей "
    "ценой. live_multiples посчитан от цены на as_of_price_date — сошлись на эту дату.\n\n"
    "Каждое численное утверждение — с явной пометкой (факт с датой / оценка Basis / "
    "суждение), коротко в скобках. Тон — спокойный, по делу, как у грамотного "
    "аналитика, а не рекламный. Отвечай на русском, markdown, без воды."
)


def _build_context(db: Session, entities: dict) -> tuple[dict, list[dict]]:
    ctx: dict = {}
    refs: list[dict] = []
    companies = []
    tickers = list(entities["tickers"])
    group = entities.get("sector_group")
    if group and len(tickers) < 3:
        for t in _resolve_sector_group(db, group):
            if t not in tickers:
                tickers.append(t)
        tickers = tickers[:_MAX_TICKERS_PER_TURN]
        entities["tickers"] = tickers
    for t in entities["tickers"]:
        c = _company_context(db, t)
        if c:
            companies.append(c)
            refs.append({"kind": "company", "ticker": t,
                        "as_of": c.get("price_date"), "title": c.get("name")})
    if companies:
        ctx["companies"] = companies
    if entities["wants_screener"]:
        ctx["screener"] = _screener_context(db)
        refs.append({"kind": "screener", "title": "Скринер акций — метрики company_metrics"})
    if entities["wants_macro"]:
        ctx["macro"] = _macro_context(db)
        refs.append({"kind": "macro", "title": "Макропоказатели РФ"})
    if entities["wants_news"] or companies:
        news = _news_context(db, entities["tickers"] or None)
        if news:
            ctx["news"] = news
            refs.append({"kind": "news", "title": f"Лента новостей ({len(news)})"})
    return ctx, refs


# ---------------------- Шаг 3': добор данных инструментами ----------------------
# 🔴 Почему цикл, а не «положим в контекст ещё таблиц»: слотов слишком много.
# Облигации (3294 выпуска), фонды, фьючерсы, валюта, дивиденды, календарь,
# портфель пользователя, вся проза карточек и досье эмитентов — это не помещается
# в один промпт и не должно: 90% вопросов касаются одной-двух сущностей. Модель
# сама берёт нужное инструментом, а предзагруженный контекст (акции из вопроса)
# остаётся, чтобы типовой вопрос отвечался БЕЗ единого вызова — одним запросом.
_TOOLS_FRAMEWORK = (
    "\n\nИНСТРУМЕНТЫ. У тебя есть доступ к данным платформы через инструменты — "
    "пользуйся ими, а не отвечай «в моём контексте таких данных нет». Что где:\n"
    "- облигации (3000+ выпусков), фонды, фьючерсы, валюта и металлы — search_bonds/"
    "get_bond, search_funds/get_fund, search_futures, get_spot_prices;\n"
    "- акции: подбор по метрикам — screen_stocks, карточка и проза вкладок — "
    "get_company_card, выплаты — get_dividends;\n"
    "- смысл, причины и формулировки разборов Basis (все вкладки карточек, досье "
    "эмитентов облигаций, методички) — search_platform_docs, затем read_platform_doc "
    "по doc_id из выдачи;\n"
    "- макро и траектория ставки — get_macro; события — get_calendar; новости — get_news;\n"
    "- портфель СПРАШИВАЮЩЕГО — get_portfolio (у гостя его нет, это нормально).\n"
    "Если данных для ответа не хватает — СНАЧАЛА позови инструмент, и только если он "
    "вернул found=false, говори, что таких данных на платформе нет. Не выдумывай "
    "SECID и тикеры: сначала найди их поиском. Отвечай пользователю ОБЫЧНЫМ ТЕКСТОМ "
    "(markdown), без JSON.\n"
    "🔴 НЕ ОПИСЫВАЙ СВОЙ ПРОЦЕСС. Пользователь не должен читать «сейчас посмотрю», "
    "«отлично, данных достаточно», «вызываю инструмент» — начинай сразу с ответа по "
    "существу. Откуда взяты данные, видно по списку источников под ответом.\n"
    "Ответ должен доводить до действия: не только «вот число», но и что оно значит "
    "для держателя бумаги и на что смотреть дальше — при этом БЕЗ «покупать/продавать»."
)

# Человеческие названия инструментов — для списка источников под ответом.
_TOOL_REF_TITLES = {
    "search_bonds": "Облигации — база выпусков платформы",
    "get_bond": "Облигация — параметры выпуска и разбор",
    "search_funds": "Фонды (БПИФ/ETF) — база платформы",
    "get_fund": "Фонд — параметры и разбор",
    "search_futures": "Фьючерсы — база контрактов",
    "get_spot_prices": "Валюта и металлы — биржевые цены",
    "screen_stocks": "Скринер акций — метрики платформы",
    "get_company_card": "Карточка компании",
    "get_dividends": "Дивиденды — история выплат",
    "get_macro": "Макропоказатели и решения ЦБ",
    "get_calendar": "Календарь событий",
    "get_portfolio": "Ваш портфель",
    "get_news": "Лента новостей платформы",
    "search_platform_docs": "Поиск по аналитике Basis",
    "read_platform_doc": "Разбор аналитика Basis",
}


# Модель в агентском цикле любит начать с реплики «про себя»: «Отлично, данных
# достаточно, сейчас соберу ответ». Запрет в промпте держит не всегда (проверено
# на бою), поэтому срезаем кодом — но ОСТОРОЖНО: только короткую первую строку,
# только по явным маркерам процесса и только если после неё что-то осталось.
_META_MARKERS = re.compile(
    r"(данных достаточно|соберу ответ|дам (развёрнутый|подробный) ответ|сейчас посмотр|"
    r"сейчас проверю|вызываю инструмент|использую инструмент|давайте (я )?(соберу|посмотрим)|"
    r"начну с|проверю (данные|платформ)|у меня достаточно)", re.IGNORECASE)


def _strip_meta_preamble(text: str) -> str:
    parts = text.split("\n", 1)
    if len(parts) != 2:
        return text
    first, rest = parts[0].strip(), parts[1].strip()
    if first and len(first) <= 160 and not first.startswith("#") and _META_MARKERS.search(first) \
            and len(rest) > 80:
        return rest
    return text


def _answer_with_tools(db: Session, user_id: int | None, guest_token: str | None,
                       user_content: str, prior: list[Message]) -> tuple[str | None, list[dict]]:
    """Прогоняет вопрос через агентский цикл с инструментами платформы.
    Возвращает (текст ответа | None, источники по вызванным инструментам)."""
    try:
        from app.services.agent_runner import run_agent
        from app.services import assistant_tools
    except ImportError:
        # Модуль ещё не доехал на инстанс (Timeweb выкатывает файлы неравномерно) —
        # тихо откатываемся на однопроходный синтез, а не роняем ответ.
        logger.warning("Ассистент: инструменты недоступны, отвечаю без цикла")
        return None, []
    try:
        run = run_agent(
            db,
            system_prompt=_ANSWER_FRAMEWORK + _TOOLS_FRAMEWORK,
            task=user_content,
            tools_schema=assistant_tools.TOOLS_SCHEMA,
            executor=assistant_tools.make_executor(user_id, guest_token),
            history=[{"role": m.role, "content": m.content}
                     for m in prior[-_MAX_HISTORY_MESSAGES:] if m.role in ("user", "assistant")],
            text_final=True,
            max_steps=_TOOL_MAX_STEPS,
            max_tokens_total=_TOOL_TOKEN_BUDGET,
            step_max_tokens=1400,
            final_max_tokens=2200,
        )
    except Exception:  # noqa: BLE001 — ответ пользователю важнее одного механизма
        logger.exception("Ассистент: агентский цикл упал")
        return None, []
    text_out = _strip_meta_preamble(((run.get("result") or {}).get("text") or "").strip())
    used: list[dict] = []
    seen = set()
    for ev in run.get("trace") or []:
        name = ev.get("name")
        if ev.get("event") != "tool" or not name:
            continue
        args = {k: v for k, v in (ev.get("args") or {}).items()
                if isinstance(v, (str, int, float))}
        # В подписи источника — за ЧЕМ ходили: «Облигация — RU000A101H84» полезнее,
        # чем просто «Облигация». Ключи в порядке узнаваемости для человека.
        subject = next((str(args[k]) for k in ("secid", "ticker", "doc_id", "query", "issuer")
                        if args.get(k)), "")
        key = (name, subject)
        if key in seen:
            continue
        seen.add(key)
        title = _TOOL_REF_TITLES.get(name, name)
        used.append({"kind": "tool", "tool": name,
                     "title": f"{title} — {subject[:60]}" if subject else title,
                     "args": args})
    logger.info("Ассистент: цикл — шагов %d, инструментов %d, токенов %d, финал %s",
                len([e for e in run.get("trace") or [] if e.get("event") == "tool"]),
                len(used), run.get("tokens_used") or 0, run.get("stopped_reason"))
    return (text_out or None), used


def _history_text(messages: list[Message]) -> str:
    tail = messages[-_MAX_HISTORY_MESSAGES:]
    lines = []
    for m in tail:
        prefix = "Пользователь" if m.role == "user" else "Ассистент"
        lines.append(f"{prefix}: {m.content[:500]}")
    return "\n".join(lines)


def ask(db: Session, user_id: int | None, user_message: str, conversation_id: int | None,
        guest_token: str | None = None) -> Conversation:
    """Главная точка входа. Создаёт диалог при conversation_id=None, иначе
    дописывает в существующий (с проверкой владельца). Возвращает Conversation
    со свежими messages (включая только что добавленные user+assistant)."""
    from app.services.llm import complete, LLMError

    if conversation_id is not None:
        conv = db.get(Conversation, conversation_id)
        # Гость продолжает СВОЙ диалог по токену; владелец — по user_id. Перепутать
        # нельзя: у диалога заполнено ровно одно из двух полей.
        own = (conv.user_id == user_id) if user_id is not None else (
            conv.user_id is None and guest_token is not None and conv.guest_token == guest_token)
        if not conv or not own:
            conv = None
    else:
        conv = None
    if conv is None:
        conv = Conversation(user_id=user_id, guest_token=guest_token, title=user_message[:120])
        db.add(conv)
        db.flush()

    # Реплики ДО этого хода: текущий вопрос идёт задачей и не должен дублироваться
    # в истории (иначе модель видит его дважды и переспрашивает саму себя).
    prior_messages = list(conv.messages) if conv.messages else []
    history_text = _history_text(prior_messages) if prior_messages else ""

    user_msg = Message(conversation_id=conv.id, role="user", content=user_message)
    db.add(user_msg)

    entities = _extract_entities(db, user_message, history_text)

    # Генерация ИИ-отчёта прямо из чата (владелец 2026-07-26: «все ИИ-функции
    # платформы должны быть доступны из ассистента») — переиспользуем ТОТ ЖЕ
    # генератор, что у Обозревателя (observer_report.generate): отчёт попадает
    # и в чат (полным текстом), и в историю отчётов Обозревателя (generate сам
    # сохраняет ObserverReport). RAG-синтез в этой ветке не гоняем — пользователь
    # просил отчёт, не ответ на вопрос.
    # 🔴 ГОСТЮ отчёт не генерируем: observer_reports.user_id NOT NULL, и попытка
    # сохранить отчёт без пользователя валила запрос IntegrityError → 500 на
    # ровном месте (поймано 2026-08-19 на вопросе «что у меня в портфеле» —
    # экстрактор счёл его запросом отчёта). Гость идёт обычным путём: с
    # инструментами он и так соберёт сводку из новостей, макро и календаря.
    if entities.get("wants_report") and user_id is not None:
        from app.services.observer_report import generate as generate_report
        depth = entities["report_depth"]
        topic = entities["report_topic"]
        try:
            rep = generate_report(db, user_id, depth, topic)
            _topic_ru = {"biz": "бизнес", "macro": "макроэкономика", "geo": "геополитика",
                         "institutions": "институциональная среда", "mixed": "смешанный"}
            _depth_ru = {"express": "экспресс", "detailed": "подробный", "deep": "глубокий"}
            answer_text = (f"**ИИ-отчёт** ({_depth_ru.get(depth, depth)} · "
                           f"{_topic_ru.get(topic, topic)}) — также сохранён в "
                           f"Обозреватель → ИИ-обзор → История отчётов.\n\n---\n\n"
                           f"{rep.content}")
            refs = [{"kind": "observer_report", "id": rep.id,
                     "title": f"ИИ-отчёт {depth}/{topic}"}]
        except LLMError:
            logger.exception("Ассистент: генерация отчёта не удалась")
            answer_text = ("Не получилось сгенерировать отчёт (генератор временно "
                           "недоступен) — попробуйте ещё раз через минуту или через "
                           "Обозреватель → ИИ-обзор.")
            refs = []
        assistant_msg = Message(conversation_id=conv.id, role="assistant",
                                content=answer_text, source_refs=refs)
        db.add(assistant_msg)
        conv.updated_at = datetime.now(timezone.utc)
        db.commit()
        db.refresh(conv)
        return conv

    ctx, refs = _build_context(db, entities)

    # scope от экстрактора — подсказка синтезу, какой слой знаний ведущий
    # (general → образованный ответ из эрудиции; platform → строго контекст).
    _scope_hint = {"general": "Вопрос ОБЩЕГО характера — отвечай из эрудиции (слой 2), "
                              "данные платформы подключай только если реально дополняют.",
                   "mixed": "Вопрос смешанный — сначала данные платформы, затем общий контекст.",
                   "platform": "Вопрос про данные платформы — цифры строго из контекста."}
    # Задача без пересказа диалога — в цикле история идёт отдельными репликами
    # (у модели роли, а не абзац текста); в запасной однопроходный синтез диалог
    # по-прежнему подмешивается строкой, там ролей нет.
    task_text = (f"Область вопроса: {_scope_hint.get(entities.get('scope'), '')}\n"
                 f"Вопрос: {user_message}\n\nПредзагруженный контекст (JSON):\n"
                 f"{json.dumps(ctx, ensure_ascii=False)}")
    user_content = (f"Недавний диалог:\n{history_text}\n\n" if history_text else "") + task_text

    answer_text, tool_refs = _answer_with_tools(db, user_id, guest_token, task_text,
                                                prior_messages)
    refs = (refs or []) + tool_refs
    if answer_text is None:
        # Цикл не дал текста (провайдер, лимит шагов) — отвечаем одним проходом
        # по предзагруженному контексту: хуже, чем с инструментами, но лучше, чем
        # «сервис недоступен» при живом контексте.
        try:
            answer_text = complete(_ANSWER_FRAMEWORK, user_content, json_mode=False,
                                   thinking=False, max_tokens=1800, temperature=0.3)
            if not isinstance(answer_text, str):
                answer_text = str(answer_text)
            answer_text = answer_text.strip() or "Не удалось сформировать ответ — попробуйте переформулировать вопрос."
        except LLMError:
            logger.exception("Ассистент: синтез ответа не удался")
            answer_text = "Сервис временно недоступен, попробуйте ещё раз через минуту."
            refs = []

    assistant_msg = Message(conversation_id=conv.id, role="assistant",
                            content=answer_text, source_refs=refs)
    db.add(assistant_msg)
    conv.updated_at = datetime.now(timezone.utc)
    db.commit()
    db.refresh(conv)
    return conv

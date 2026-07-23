"""ИИ-обозревательский отчёт (Обозреватель, Направление 5) — СИНТЕЗ-слой.

Сам никуда не ходит: пересобирает уже собранные данные направлений 1-4,6,7 + портфель
в сводный дайджест трёх глубин. LLM ТОЛЬКО синтезирует переданный контекст (без
внешних источников и выдумок), каждый тезис ссылается на элемент контекста (id/ref),
без «купить/продать».
"""
from __future__ import annotations

import json
import logging
import re
from datetime import date, datetime, timedelta, timezone

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.models.observer_report import ObserverReport, HORIZON_DAYS
from app.models.company import Company
from app.models.portfolio import Portfolio, PortfolioPosition

logger = logging.getLogger(__name__)


def _portfolio(db: Session, user_id: int) -> tuple[set[str], set[str]]:
    rows = (db.query(Company.ticker, Company.sector)
            .join(PortfolioPosition, PortfolioPosition.company_id == Company.id)
            .join(Portfolio, Portfolio.id == PortfolioPosition.portfolio_id)
            .filter(Portfolio.user_id == user_id).all())
    return {r[0] for r in rows if r[0]}, {r[1] for r in rows if r[1]}


# ----------------------------- СБОР КОНТЕКСТА -----------------------------
# Тема (topic) — ЧТО класть в контекст (фокус источников); глубина (rtype) — СКОЛЬКО
# и как подробно. Раньше topic приходил с фронта и полностью игнорировался — эта
# таблица задаёт реальный множитель объёма каждого источника ПО ТЕМЕ (1.0 = как для
# rtype-глубины по умолчанию, 0 = не собирать вовсе). "mixed" — прежнее поведение.
# "biz" раньше зануляла macro И geo ОДНОВРЕМЕННО (0.0, 0.0) — если главные
# драйверы месяца были ставка ЦБ (macro) и санкции (geo), держатель бумаги с
# темой «Бизнес» получал отчёт, слепой к обеим причинам разом (ломало именно
# ту причинную связку, которую отчёт должен вскрывать). По образцу остальных
# строк (у каждой — небольшой ненулевой вес на «не свою» причинную ось) даны
# 0.2/0.2 — достаточно, чтобы всплыл ГЛАВНЫЙ драйвер каждой оси, не растворяя
# фокус на бизнесе.
_TOPIC_WEIGHT = {
    #           news  earnings  calendar  macro  geo   institutions
    "biz":         (0.6,  1.5,     0.8,     0.2,  0.2,  0.0),
    "macro":       (0.5,  0.0,     0.6,     1.5,  0.3,  0.0),
    "geo":         (0.5,  0.0,     0.4,     0.3,  1.5,  0.0),
    "institutions":(0.3,  0.0,     0.3,     0.2,  0.5,  1.5),
    "mixed":       (1.0,  1.0,     1.0,     1.0,  1.0,  1.0),
}


def _gather(db: Session, rtype: str, topic: str, pf_tickers: set[str], pf_sectors: set[str]) -> tuple[dict, list]:
    """Контекст обозревателя по горизонту/охвату (rtype) И теме-фокусу (topic) +
    список source_refs (ref→элемент)."""
    today = date.today()
    days = HORIZON_DAYS[rtype]
    w_news, w_earn, w_cal, w_macro, w_geo, w_inst = _TOPIC_WEIGHT.get(topic, _TOPIC_WEIGHT["mixed"])
    ctx: dict = {"today": today.isoformat(), "report_type": rtype, "topic": topic, "horizon_days": days,
                 "portfolio_tickers": sorted(pf_tickers), "portfolio_sectors": sorted(pf_sectors)}
    refs: list = []

    n_news = round({"express": 4, "detailed": 12, "deep": 30}[rtype] * w_news)
    ctx["news"] = []
    if n_news > 0:
        from app.models.market import MarketUpdate
        news = (db.query(MarketUpdate).filter(MarketUpdate.status == "published")
                .order_by(MarketUpdate.published_at.desc()).limit(n_news).all())
        for i, u in enumerate(news, 1):
            ref = f"N{i}"
            tickers = u.affected_tickers or []
            ctx["news"].append({"ref": ref, "title": u.title,
                                "impact": (u.impact_comment or "")[:200], "category": u.category,
                                "tickers": tickers, "in_portfolio": bool(set(tickers) & pf_tickers)})
            refs.append({"ref": ref, "kind": "news", "id": u.id, "title": u.title, "url": u.source_url})

    # Отчёты (Напр.3) — портфель + крупные
    n_earn = round({"express": 6, "detailed": 14, "deep": 30}[rtype] * w_earn)
    ctx["earnings"] = []
    if n_earn > 0:
        from app.models.earnings import EarningsReport, EarningsDigest
        er = (db.query(EarningsReport, EarningsDigest)
              .outerjoin(EarningsDigest, EarningsDigest.report_id == EarningsReport.id)
              .order_by(EarningsReport.created_at.desc())
              .limit(n_earn).all())
        for i, (r, dg) in enumerate(er, 1):
            ref = f"E{i}"
            ctx["earnings"].append({"ref": ref, "ticker": r.ticker, "period": r.period,
                                   "standard": r.standard, "one_liner": dg.one_liner if dg else None,
                                   "in_portfolio": r.ticker in pf_tickers})
            refs.append({"ref": ref, "kind": "earnings", "ticker": r.ticker, "title": f"{r.ticker} {r.period}"})

    # Календарь (Напр.4) — будущие события в горизонте
    horizon = today + timedelta(days=days)
    n_cal = round({"express": 8, "detailed": 25, "deep": 60}[rtype] * w_cal)
    ctx["calendar"] = []
    if n_cal > 0:
        from app.models.calendar_event import CalendarEvent
        ce = (db.query(CalendarEvent)
              .filter(CalendarEvent.event_date >= today, CalendarEvent.event_date <= horizon)
              .order_by(CalendarEvent.event_date.asc())
              .limit(n_cal).all())
        for i, e in enumerate(ce, 1):
            ref = f"C{i}"
            ctx["calendar"].append({"ref": ref, "type": e.event_type, "date": e.event_date.isoformat(),
                                   "title": e.title, "ticker": e.ticker,
                                   "in_portfolio": bool(e.ticker and e.ticker in pf_tickers)})
            refs.append({"ref": ref, "kind": "calendar", "id": e.id, "title": e.title})

    # Макро (Напр.2) — по умолчанию для detailed/deep; тема macro включает всегда
    # (даже express); тема institutions с низким весом (0.0) выключает вовсе,
    # тема biz с малым весом (0.2) — включает на detailed/deep, чтобы не быть
    # слепой к главному макро-драйверу месяца, но не на express (терсность)
    if w_macro > 0 and (rtype in ("detailed", "deep") or topic == "macro"):
        ctx["macro"] = _macro_snapshot(db, today, horizon)

    # Геополитика (Напр.7) + Карты (Напр.6) — по умолчанию только deep; тема geo
    # включает на любой глубине
    if w_geo > 0 and (rtype == "deep" or topic == "geo"):
        ctx["geopolitics"] = _geo_snapshot(db)
    if rtype == "deep" or topic in ("biz", "mixed"):
        ctx["valuation_map"] = _maps_snapshot(db, pf_tickers)

    # Институты (Направление «Институциональная среда») — только тема institutions
    # (не входит в mixed по умолчанию: отдельный, специфический срез, не общий фон)
    if w_inst > 0:
        ctx["institutions"] = _institutions_snapshot(pf_tickers)

    return ctx, refs


def _institutions_snapshot(pf_tickers: set[str]) -> dict:
    """Институциональный барометр (макро) + институциональные разборы компаний
    портфеля, если есть (пилот раскатан на 16 голубых фишек, не на все 262)."""
    import json
    from pathlib import Path
    companies_dir = Path(__file__).parent.parent.parent / "companies"
    config_dir = Path(__file__).parent.parent.parent / "config"
    out: dict = {}
    try:
        barometer_path = config_dir / "institutional_barometer.json"
        if barometer_path.exists():
            b = json.loads(barometer_path.read_text(encoding="utf-8"))
            out["barometer"] = {"overall_out_of_5": (b.get("barometer") or {}).get("overall"),
                                "scale_note": "шкала 0-5, где 5 — лучший институциональный профиль (НЕ из 10)",
                                "label": (b.get("barometer") or {}).get("label"),
                                "scenario": (b.get("scenario") or {}).get("current"),
                                "alerts": [a.get("title") for a in (b.get("alerts") or [])[:5]]}
    except Exception:  # noqa: BLE001
        pass
    companies = []
    for t in sorted(pf_tickers):
        p = companies_dir / t.upper() / "institutions.json"
        if not p.exists():
            continue
        try:
            d = json.loads(p.read_text(encoding="utf-8"))
            iri = (d.get("iri_scoring") or {}).get("overall")
            vt = d.get("valuation_translation") or {}
            companies.append({"ticker": t, "iri_overall": iri,
                              "wacc_premium_pp": vt.get("wacc_premium_pp"),
                              "patron_change_risk": (d.get("clan_patronage") or {}).get("patron_change_risk")})
        except Exception:  # noqa: BLE001
            continue
    out["portfolio_companies"] = companies
    out["portfolio_coverage_note"] = (
        f"Институциональный разбор есть по {len(companies)} из {len(pf_tickers)} бумаг портфеля "
        "(пилот на голубых фишках, раскатка на остальные компании продолжается)."
    )
    return out


def _macro_snapshot(db: Session, today: date, horizon: date) -> dict:
    out = {}
    def last(code, metric="level"):
        r = db.execute(text("SELECT value, as_of FROM macro_data_points WHERE indicator_code=:c "
                            "AND metric=:m ORDER BY as_of DESC LIMIT 1"), {"c": code, "m": metric}).first()
        return {"value": float(r.value), "as_of": r.as_of.isoformat()} if r else None
    out["key_rate"] = last("key_rate")
    out["inflation_yoy"] = last("inflation", "yoy")
    out["usdrub"] = last("usdrub")
    try:
        from app.models.macro import RateMeeting
        m = db.query(RateMeeting).order_by(RateMeeting.decision_date.desc()).first()
        if m and m.next_meeting_date and today <= m.next_meeting_date <= horizon:
            out["rate_meeting_in_horizon"] = m.next_meeting_date.isoformat()
    except Exception:  # noqa: BLE001
        pass
    return out


def _geo_snapshot(db: Session) -> list:
    from app.models.geo import GeoBlock
    rows = db.query(GeoBlock).filter_by(tab="overview").all()
    return [{"region": b.title, "status": (b.status_text or "")[:300],
             "market_impact": (b.market_impact or "")[:200]} for b in rows]


def _maps_snapshot(db: Session, pf_tickers: set[str]) -> dict:
    """Топ недо/переоценённых по модельной справедливой цене (Напр.6)."""
    try:
        from app.services import market_maps
        data = market_maps.valuation(db, tickers_filter=None)
    except Exception:  # noqa: BLE001
        return {}
    tiles = [t for s in data.get("sectors", []) for t in s["tiles"]]
    tiles.sort(key=lambda t: t.get("upside_pct", 0))
    over = [{"ticker": t["ticker"], "upside_pct": t["upside_pct"]} for t in tiles[:5]]
    under = [{"ticker": t["ticker"], "upside_pct": t["upside_pct"]} for t in tiles[-5:][::-1]]
    pf = [{"ticker": t["ticker"], "upside_pct": t["upside_pct"]} for t in tiles if t["ticker"] in pf_tickers]
    return {"note": "Апсайд к МОДЕЛЬНОЙ справедливой цене (оценка Basis), не сигнал",
            "most_overvalued": over, "most_undervalued": under, "portfolio": pf[:8]}


# ----------------------------- ПРОМПТ -----------------------------
_FRAMEWORK = (
    "Ты составляешь сводный обзор рынка для частного инвестора на основе ПЕРЕДАННЫХ "
    "данных платформы. Используй ТОЛЬКО переданный контекст — ничего не добавляй от "
    "себя, не выдумывай факты и цифры. НЕ давай рекомендаций покупать/продавать и НЕ "
    "называй целевые цены. Каждый ключевой тезис помечай ссылкой на источник из "
    "контекста в квадратных скобках (например [N1], [E2], [C3]). Тон спокойный, "
    "аналитический. Персонализируй под портфель (portfolio_tickers): что КАСАЕТСЯ "
    "бумаг инвестора — выделяй. Если значимых событий мало — скажи честно. "
    "Выведи markdown."
)
_LEVEL = {
    "express": ("ЭКСПРЕСС (горизонт ±2 дня, кратко ~1 экран). Дай: 2-3 ключевые новости; "
                "1-2 ближайших события (приоритет — портфель и крупнейшие фишки на носу); "
                "краткий итог по свежим отчётам портфеля. Ставку ЦБ упоминай ТОЛЬКО если "
                "заседание в горизонте. Без воды."),
    "detailed": ("ПОДРОБНЫЙ (±7 дней). Разделы: Главные новости недели (со связкой влияния "
                 "«и поэтому»); Макрокартина (инфляция/ставка/курс + что значит); Разбор "
                 "вышедших отчётов (портфель + крупные); Календарь следующей недели; 1-2 "
                 "сквозные темы."),
    "deep": ("ГЛУБОКИЙ (±30 дней). Разделы: Новостной фон месяца; Полная макродинамика; "
             "Значимые отчёты; Геополитика (по каналам, нейтрально); Карты рынка "
             "(перегрето/недооценено — модельная оценка, не сигнал); Темы месяца и связки "
             "между направлениями; Полный календарь вперёд. Персональный месячный обзор."),
}
# Тема — ФОКУС содержания поверх глубины выше (что подчёркивать/группировать),
# без нового обхода источников (тот уже задан _TOPIC_WEIGHT в _gather).
_TOPIC_FOCUS = {
    "biz": ("ФОКУС ТЕМЫ — БИЗНЕС компаний портфеля: вышедшие отчёты, что изменилось в "
            "выручке/марже/долге, что это значит для держателя бумаги. Макро/геополитику "
            "почти не касайся (если только напрямую не бьёт по конкретной компании)."),
    "macro": ("ФОКУС ТЕМЫ — МАКРОЭКОНОМИКА: ставка/инфляция/курс/бюджет и что это значит "
              "для рынка и портфеля через каналы трансмиссии. Отчётности отдельных компаний "
              "почти не касайся, если только не иллюстрируют макро-эффект."),
    "geo": ("ФОКУС ТЕМЫ — ГЕОПОЛИТИКА: санкции/конфликты/внешние ограничения и их канал "
            "влияния на рынок/сектора/портфель. Нейтральный тон, явно суждение там, где "
            "не факт. Финансовые отчёты почти не касайся."),
    "institutions": ("ФОКУС ТЕМЫ — ИНСТИТУЦИОНАЛЬНАЯ СРЕДА: барометр (конфигурация власти, "
                     "защита собственности, госсектор), активные алерты, и — если есть данные "
                     "по компаниям портфеля (institutions.institutions в контексте) — их "
                     "клановый патронаж/риск изъятия/институциональная премия к оценке. "
                     "Если по компании данных нет — честно скажи, что разбор пока не сделан, "
                     "не выдумывай. Это суждение, не факт — подчёркивай явно."),
    "mixed": "ФОКУС ТЕМЫ — СМЕШАННЫЙ (все источники сбалансированно, как раньше).",
}


def generate(db: Session, user_id: int, rtype: str, topic: str = "mixed") -> ObserverReport:
    from app.services.llm import complete, pro_model, LLMError
    if topic not in _TOPIC_FOCUS:
        topic = "mixed"
    pf_t, pf_s = _portfolio(db, user_id)
    ctx, refs = _gather(db, rtype, topic, pf_t, pf_s)
    system = _FRAMEWORK + "\n\nУРОВЕНЬ: " + _LEVEL[rtype] + "\n\n" + _TOPIC_FOCUS[topic]
    thinking = rtype in ("detailed", "deep")
    # detailed/deep включают thinking=True (DeepSeek reasoning) — токены на
    # рассуждение и на финальный текст делят один бюджет max_tokens; при узком
    # бюджете reasoning-модель успевала «подумать», но не успевала дописать
    # content → llm.py раньше подставлял сырой reasoning_content (черновик
    # размышлений поверх входного JSON-контекста — выглядит как «JSON-файл»).
    # Запас увеличен, и (см. llm.py) для json_mode=False такой фолбэк убран —
    # теперь при нехватке бюджета придёт честно пустая строка, а не мусор.
    max_tokens = {"express": 1500, "detailed": 6000, "deep": 12000}[rtype]
    # Интерактивный путь (пользователь смотрит на спиннер) — без override здесь
    # complete() падает на дефолт LLM_TIMEOUT=180с×3 попытки (до ~9 минут висения,
    # см. llm.py:82-86), пока фронт не покажет "failed" и не залипнет кнопка
    # «Сгенерировать» (нет client-side AbortController). Короче таймаут по глубине
    # (те же 30-40с/попытку, что и в stress_ask.py/stress_expert.py, но с запасом
    # под detailed/deep — там thinking=True и бюджет токенов на порядок больше).
    timeout = {"express": 40, "detailed": 75, "deep": 120}[rtype]
    content = complete(system, json.dumps(ctx, ensure_ascii=False), json_mode=False,
                       thinking=thinking, model=pro_model(), max_tokens=max_tokens,
                       temperature=0.3, timeout=timeout, retries=1)
    if not isinstance(content, str):
        content = str(content)
    content = content.strip()
    if len(content) < 40:
        raise LLMError("модель вернула пустой или слишком короткий ответ")
    # _gather() кладёт в refs КАЖДЫЙ собранный элемент безусловно (до ~120 для
    # Глубокого) — модель реально цитирует в тексте обычно меньше половины.
    # Нефильтрованный список внизу читается как сырой кусок контекста, а не как
    # осмысленные источники — оставляем только то, что реально процитировано.
    cited = set(re.findall(r"\[([A-ZА-Я]\d+)\]", content))
    cited_refs = [r for r in refs if r.get("ref") in cited] or refs[:12]
    rep = ObserverReport(user_id=user_id, report_type=rtype, topic=topic, horizon_days=HORIZON_DAYS[rtype],
                         content=content, source_refs=cited_refs,
                         portfolio_snapshot=sorted(pf_t), model_used="deepseek-pro",
                         generated_at=datetime.now(timezone.utc))
    db.add(rep); db.commit(); db.refresh(rep)
    logger.info("Обозревательский отчёт %s/%s сгенерирован для user=%s (refs=%d/%d процитировано)",
               rtype, topic, user_id, len(cited_refs), len(refs))
    return rep

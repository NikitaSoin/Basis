"""ИИ-Диагноз портфеля — синтез-слой (по образцу observer_report.py).

Сам никуда не ходит: пересобирает уже посчитанные метрики портфеля
(compute_portfolio_metrics/compute_factor_profile) + сжатые сигналы каждой
компании-держания (governance-балл/риски, макро bottom_line из карточки) +
рыночный контекст Обозревателя (макро/гео/новости, отфильтрованный под
держания). LLM ТОЛЬКО синтезирует переданный контекст в «щит портфеля /
уязвимости / резюме», каждый тезис — с эпистемическим тегом
(факт/оценка/модель/суждение) и привязкой к конкретному тикеру/сектору/теме
из контекста, не общими фразами. Без «купить/продать».
"""
from __future__ import annotations

import json
import logging
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)

_COMPANIES_DIR = Path(__file__).parent.parent.parent / "companies"


def _load_json(ticker: str, filename: str) -> dict | None:
    path = _COMPANIES_DIR / ticker.upper() / filename
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def _holding_signal(ticker: str) -> dict:
    """Сжатый сигнал по держанию — НЕ полные файлы карточки (сотни КБ на
    компанию не влезут в промпт при 10+ держаниях), только итоговый балл,
    топ-риски и одна макро-фраза."""
    out: dict = {"ticker": ticker}
    gov = _load_json(ticker, "governance.json")
    if gov:
        factors = ((gov.get("scoring") or {}).get("factors")) or []
        scores = [f["score"] for f in factors if isinstance(f.get("score"), (int, float))]
        if scores:
            out["governance_score"] = round(sum(scores) / len(scores), 1)
        risks = gov.get("governance_risks") or []
        titles = [r["risk"] for r in risks if r.get("risk")]
        if titles:
            out["governance_risks"] = titles[:2]
    macro = _load_json(ticker, "macro.json")
    if macro:
        bottom_line = (macro.get("bottom_line") or {}).get("text")
        if bottom_line:
            out["macro_note"] = bottom_line[:350]
        signal = macro.get("signal_macro_regime") or {}
        if signal.get("rate_vector"):
            out["rate_sensitivity_vector"] = signal["rate_vector"]
    return out


def _gather_context(db: Session, portfolio_id: int) -> dict | None:
    from app.services.portfolio import compute_portfolio_metrics, compute_factor_profile

    metrics = compute_portfolio_metrics(db, portfolio_id)
    if not metrics or not metrics.get("positions"):
        return None

    positions = [p for p in metrics["positions"] if p.get("weight_pct")]
    if not positions:
        return None
    tickers = [p["ticker"] for p in positions]

    def _val(v):
        return v.get("value") if isinstance(v, dict) else v

    portfolio_row = metrics.get("portfolio") or {}
    ctx: dict = {
        "positions": [
            {"ticker": p["ticker"], "sector": p["sector"], "weight_pct": p["weight_pct"],
             "beta": p.get("beta"), "volatility": p.get("volatility"),
             "return_total_3y": p.get("return_total_3y"), "sharpe_3y": p.get("sharpe_3y"),
             "history_years": p.get("history_years"), "short_history": p.get("short_history")}
            for p in positions
        ],
        "sector_allocation": metrics.get("sector_allocation"),
        "concentration": metrics.get("concentration"),
        "portfolio_metrics": {
            "beta": _val(portfolio_row.get("beta")),
            "return_total_3y": _val(portfolio_row.get("return_total_3y")),
            "volatility": _val(portfolio_row.get("volatility")),
            "sharpe": portfolio_row.get("sharpe"),
            "sortino": portfolio_row.get("sortino"),
            "alpha": portfolio_row.get("alpha"),
            "max_drawdown": portfolio_row.get("max_drawdown"),
            "downside_vol": portfolio_row.get("downside_vol"),
            "var_95": portfolio_row.get("var_95"),
            "capm": portfolio_row.get("capm"),
        },
        "quality_index": metrics.get("quality"),
        "factor_profile": compute_factor_profile(db, portfolio_id),
        "holdings_signals": [_holding_signal(t) for t in tickers],
    }
    corr = metrics.get("correlation")
    if corr:
        ctx["correlation_summary"] = {
            "avg": corr.get("avg"), "strongest_pair": corr.get("strongest_pair"),
            "weakest_pair": corr.get("weakest_pair"), "low_overlap": corr.get("low_overlap"),
        }

    # Контекст Обозревателя (макро/гео), отфильтрованный по горизонту 30 дней —
    # переиспользуем то, что уже собирает observer_report.py для сводного отчёта.
    try:
        from app.services.observer_report import _macro_snapshot, _geo_snapshot
        today = date.today()
        ctx["market_macro"] = _macro_snapshot(db, today, today + timedelta(days=30))
        ctx["geopolitics"] = _geo_snapshot(db)
    except Exception as e:  # noqa: BLE001
        logger.warning("Диагноз портфеля: контекст Обозревателя недоступен: %s", e)

    # Новости, реально касающиеся держаний портфеля (не весь лентовый поток)
    try:
        from app.models.market import MarketUpdate
        pf_tickers = set(tickers)
        news = (db.query(MarketUpdate).filter(MarketUpdate.status == "published")
                .order_by(MarketUpdate.published_at.desc()).limit(40).all())
        relevant = [u for u in news if set(u.affected_tickers or []) & pf_tickers]
        ctx["portfolio_news"] = [
            {"title": u.title, "impact": (u.impact_comment or "")[:200], "tickers": u.affected_tickers}
            for u in relevant[:8]
        ]
    except Exception as e:  # noqa: BLE001
        logger.warning("Диагноз портфеля: новости недоступны: %s", e)

    return ctx


_SYSTEM = (
    "Ты — аналитик Basis, составляешь ИИ-Диагноз портфеля частного инвестора на основе "
    "ПЕРЕДАННЫХ данных платформы. Используй ТОЛЬКО переданный контекст — ничего не "
    "выдумывай и не добавляй от себя. НЕ давай рекомендаций купить/продать и НЕ называй "
    "целевые цены.\n\n"
    "Диагноз должен быть ТОЧЕЧНЫМ, а не общими фразами: каждый тезис — цепочка "
    "\"конкретный тикер/сектор/макро-тема из контекста → почему это сильная сторона или "
    "уязвимость ИМЕННО этого портфеля\". Плохо: «диверсификация снижает риск». Хорошо: "
    "«SBER и GAZP вместе — 42% портфеля при корреляции 0.81, оба чувствительны к одному "
    "макро-фактору (ставка/экспорт)».\n\n"
    "Синтезируй ТРИ источника вместе, а не по отдельности: (1) метрики портфеля "
    "(portfolio_metrics/quality_index/correlation_summary/concentration/factor_profile), "
    "(2) сигналы по каждому держанию (holdings_signals — governance-балл/риски, "
    "макро-заметка компании), (3) рыночный контекст (market_macro/geopolitics/"
    "portfolio_news). Например: если у крупной позиции низкий governance-балл ИЛИ активные "
    "governance_risks — это уязвимость; если ставка ЦБ (market_macro.key_rate) движется "
    "против factor_profile.rate_pct_per_100bp портфеля — тоже уязвимость.\n\n"
    "У КАЖДОГО тезиса обязательно укажи epistemic-тип: "
    "\"факт\" (посчитанное число портфеля/бумаги), "
    "\"оценка\" (интерпретация числа, напр. \"высокая концентрация\"), "
    "\"модель\" (модельная величина — бета, CAPM, факторная чувствительность), "
    "\"суждение\" (качественный вывод — governance, геополитика, макро-режим).\n\n"
    "Верни СТРОГО валидный JSON без текста вне JSON, формат:\n"
    "{\"shield\": [{\"text\": \"...\", \"type\": \"факт|оценка|модель|суждение\"}, ...2-4 шт], "
    "\"vulnerabilities\": [{...}, ...2-4 шт], "
    "\"summary\": {\"text\": \"1-2 предложения общего вывода\", \"type\": \"...\"}}"
)


def generate_diagnosis(db: Session, portfolio_id: int):
    """Генерирует и кэширует ИИ-Диагноз (один на портфель, перегенерируется по
    кнопке «Обновить диагноз»). Возвращает None, если портфель пуст/без метрик
    (честная деградация — не выдуманный диагноз на пустых данных)."""
    from app.services.llm import complete, pro_model
    from app.models.portfolio_diagnosis import PortfolioDiagnosis

    ctx = _gather_context(db, portfolio_id)
    if not ctx:
        return None

    # max_tokens высокий: "думающая" pro-модель эмитит цепочку рассуждений ДО
    # финального JSON текстом (не в отдельном служебном поле) — при 3000
    # обрезает JSON на середине и парсинг падает; 6000 хватает с запасом.
    result = complete(
        _SYSTEM, json.dumps(ctx, ensure_ascii=False, default=str),
        json_mode=True, thinking=True, model=pro_model(),
        max_tokens=6000, temperature=0.3,
    )
    if not isinstance(result, dict):
        raise ValueError("Диагноз: LLM вернул не JSON-объект")

    diag = db.query(PortfolioDiagnosis).filter_by(portfolio_id=portfolio_id).first()
    if not diag:
        diag = PortfolioDiagnosis(portfolio_id=portfolio_id)
        db.add(diag)
    diag.shield = result.get("shield") or []
    diag.vulnerabilities = result.get("vulnerabilities") or []
    summary = result.get("summary") or {}
    diag.summary = summary.get("text")
    diag.summary_type = summary.get("type")
    diag.portfolio_snapshot = [p["ticker"] for p in ctx["positions"]]
    diag.model_used = pro_model()
    diag.generated_at = datetime.now(timezone.utc)
    db.commit()
    db.refresh(diag)
    logger.info("ИИ-Диагноз портфеля %d сгенерирован (%d держаний)", portfolio_id, len(ctx["positions"]))
    return diag

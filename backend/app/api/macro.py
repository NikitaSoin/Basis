"""API Макрообзора (Обозреватель, Направление 2).

GET /api/market/macro            — сводка показателей (фильтры country, portfolio_only)
GET /api/market/macro/{code}/series — ряд для графика (metric, from, to)
GET /api/market/macro/rate       — спец-блок ключевой ставки
GET /api/market/macro/analytics  — выжимки ЦБ/ЦМАКП
"""
import logging
from datetime import date

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import JSONResponse, StreamingResponse
from sqlalchemy import and_
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.auth import get_current_user_optional
from app.models.company import Company
from app.models.portfolio import Portfolio, PortfolioPosition
from app.models.macro import (MacroIndicator, MacroDataPoint, RateMeeting,
                              MacroAnalyticsDoc, MacroForecast, MacroInterpretation,
                              MacroExpertSurvey)

logger = logging.getLogger(__name__)

router = APIRouter()


def _latest_two(db: Session, code: str, metric: str):
    rows = (db.query(MacroDataPoint)
            .filter_by(indicator_code=code, metric=metric)
            .order_by(MacroDataPoint.as_of.desc()).limit(2).all())
    return rows


def _point_dict(p: MacroDataPoint, prev: MacroDataPoint | None):
    change = None
    if prev is not None and p is not None:
        try:
            change = float(p.value) - float(prev.value)
        except (TypeError, ValueError):
            change = None
    return {
        "metric": p.metric,
        "value": float(p.value),
        "as_of": p.as_of.isoformat(),
        "unit": p.unit,
        "is_preliminary": p.is_preliminary,
        "change": round(change, 4) if change is not None else None,
        "source": p.source,
        "source_url": p.source_url,
    }


def _portfolio_sectors(db: Session, user) -> set[str]:
    if not user:
        return set()
    rows = (db.query(Company.sector)
            .join(PortfolioPosition, PortfolioPosition.company_id == Company.id)
            .join(Portfolio, Portfolio.id == PortfolioPosition.portfolio_id)
            .filter(Portfolio.user_id == user.id).all())
    return {r[0] for r in rows if r[0]}


def _units_parts(unit: str | None) -> tuple[str, str]:
    from app.services.macro_units import parts
    return parts(unit)


@router.get("/market/macro")
def macro_summary(country: str | None = None, portfolio_only: bool = False,
                  db: Session = Depends(get_db), user=Depends(get_current_user_optional)):
    """Сводка показателей с последним значением (по каждой метрике) и изменением."""
    q = db.query(MacroIndicator)
    if country:
        q = q.filter(MacroIndicator.country == country)
    indicators = q.order_by(MacroIndicator.sort_order).all()
    pf_sectors = _portfolio_sectors(db, user) if portfolio_only else set()

    out = []
    for ind in indicators:
        metrics = ind.metric_types or ["level"]
        values = {}
        for m in metrics:
            rows = _latest_two(db, ind.code, m)
            if rows:
                values[m] = _point_dict(rows[0], rows[1] if len(rows) > 1 else None)
        # ЛЁГКАЯ персонализация (по ТЗ): макропоказатели глобальны и влияют на всё,
        # поэтому portfolio_only НЕ фильтрует жёстко, а лишь ПОДСВЕЧИВАЕТ релевантные
        # секторам портфеля (in_portfolio → выделение на фронте).
        in_portfolio = bool(ind.sectors) and bool(pf_sectors & set(ind.sectors or []))
        out.append({
            "code": ind.code, "title": ind.title, "unit": ind.unit,
            # 🔴 Человеческая единица (владелец, 2026-08-09: «4,36 usd/bbl непонятно»).
            # unit оставляем как есть — по нему считает фронт (сравнение с "%") и
            # сходятся сверки; для показа даём префикс/суффикс: «$4,36 / барр.».
            "unit_prefix": _units_parts(ind.unit)[0], "unit_suffix": _units_parts(ind.unit)[1],
            "country": ind.country, "frequency": ind.frequency,
            "display_group": ind.display_group, "metric_types": ind.metric_types,
            "influence_short": ind.influence_short, "influence_full": ind.influence_full,
            "values": values, "has_data": bool(values), "in_portfolio": in_portfolio,
            # 🔴 Свежесть наружу. Ряды ВВП и инфляции КНР — прекращённые серии OECD:
            # витрина показывала «ВВП КНР 3,47%» с датой 2023 года, и число выглядело
            # актуальным. Дата рядом была, но её никто не читает — нужна явная метка.
            **_staleness(ind, values),
        })
    return out


def _staleness(ind, values: dict) -> dict:
    """Насколько просрочен ряд относительно своей частоты."""
    from app.services.macro_ingest import _STALE_DAYS

    dates = [v.get("as_of") for v in values.values() if v.get("as_of")]
    if not dates:
        return {"is_stale": False, "stale_days": None}
    try:
        newest = max(date.fromisoformat(str(d)[:10]) for d in dates)
    except ValueError:
        return {"is_stale": False, "stale_days": None}
    age = (date.today() - newest).days
    limit = _STALE_DAYS.get(ind.frequency or "monthly", 75)
    return {"is_stale": age > limit, "stale_days": age}


@router.get("/market/macro/rate")
def macro_rate(db: Session = Depends(get_db)):
    """Спец-блок ставки: текущая ставка + последнее заседание + инфляция/ожидания."""
    def _last(code, metric="level"):
        p = (db.query(MacroDataPoint).filter_by(indicator_code=code, metric=metric)
             .order_by(MacroDataPoint.as_of.desc()).first())
        return {"value": float(p.value), "as_of": p.as_of.isoformat()} if p else None

    meetings = (db.query(RateMeeting).order_by(RateMeeting.decision_date.desc()).limit(8).all())
    meeting = meetings[0] if meetings else None

    def _mtg(m):
        return {
            "decision_date": m.decision_date.isoformat(),
            "rate_value": float(m.rate_value) if m.rate_value is not None else None,
            "signal": m.signal, "next_meeting_date": m.next_meeting_date.isoformat() if m.next_meeting_date else None,
            "consensus_forecast": m.consensus_forecast, "press_summary": m.press_summary,
        }
    return {
        "key_rate": _last("key_rate"),
        "inflation_yoy": _last("inflation", "yoy"),
        "inflation_expectations": _last("inflation_expectations"),
        "meeting": _mtg(meeting) if meeting else None,
        "meetings": [_mtg(m) for m in meetings],  # история (новые сверху)
    }


@router.get("/market/macro/analytics")
def macro_analytics(limit: int = Query(20, ge=1, le=100), source: str | None = None,
                    db: Session = Depends(get_db)):
    q = db.query(MacroAnalyticsDoc)
    if source:
        q = q.filter(MacroAnalyticsDoc.source == source)
    docs = q.order_by(MacroAnalyticsDoc.published_at.desc().nullslast(),
                      MacroAnalyticsDoc.created_at.desc()).limit(limit).all()
    return [{
        "id": d.id, "source": d.source, "doc_type": d.doc_type, "title": d.title,
        "summary": d.summary, "key_takeaways": d.key_takeaways,
        "interpretation": d.interpretation,
        "published_at": d.published_at.isoformat() if d.published_at else None,
        "source_url": d.source_url, "model_used": d.model_used,
    } for d in docs]


@router.get("/market/macro/forecast")
def macro_forecast(db: Session = Depends(get_db)):
    """Среднесрочный прогноз ЦБ (последняя публикация ПО КАЖДОМУ сценарию отдельно).

    Базовый сценарий уточняется на каждом заседании (~раз в 6 недель, комментарий к
    решению по ставке), альтернативные (дезинфляционный/проинфляционный/рисковый) —
    раз в год в ОНДКП. У них РАЗНЫЕ as_of — если брать один глобальный latest, при
    более свежем базовом альтернативные сценарии пропадали бы из ответа. Берём max
    as_of отдельно для каждого сценария."""
    from sqlalchemy import func
    latest = db.query(MacroForecast).order_by(MacroForecast.as_of.desc()).first()
    if not latest:
        return {"rows": [], "as_of": None, "scenarios": []}
    per_scen_latest = dict(
        db.query(MacroForecast.scenario, func.max(MacroForecast.as_of))
        .group_by(MacroForecast.scenario).all()
    )
    all_rows = []
    for scen, as_of in per_scen_latest.items():
        all_rows.extend(
            db.query(MacroForecast)
            .filter(MacroForecast.scenario == scen, MacroForecast.as_of == as_of)
            .order_by(MacroForecast.year).all()
        )
    # Группируем по сценариям; базовый — первым.
    by_scen: dict[str, list] = {}
    for r in all_rows:
        by_scen.setdefault(r.scenario, []).append(r)
    order = ["базовый", "проинфляционный", "дезинфляционный", "рисковый"]
    scen_names = sorted(by_scen.keys(), key=lambda s: (order.index(s) if s in order else 99, s))
    scenarios = [{
        "scenario": s,
        "comment": next((r.comment for r in by_scen[s] if r.comment), None),
        "rows": [{"indicator": r.indicator, "year": r.year, "value": r.value} for r in by_scen[s]],
    } for s in scen_names]
    base = next((sc for sc in scenarios if sc["scenario"] == "базовый"), scenarios[0] if scenarios else None)
    return {
        "as_of": latest.as_of.isoformat(),
        "source_url": latest.source_url,
        # back-compat: плоский базовый сценарий
        "scenario": base["scenario"] if base else None,
        "comment": base["comment"] if base else None,
        "rows": base["rows"] if base else [],
        # все сценарии
        "scenarios": scenarios,
    }


@router.get("/market/macro/expert-survey")
def macro_expert_survey(db: Session = Depends(get_db)):
    """Макроэкономический опрос ЦБ — медианный консенсус ~30 независимых аналитиков
    (отдельно от прогноза самого ЦБ выше)."""
    latest = db.query(MacroExpertSurvey).order_by(MacroExpertSurvey.as_of.desc()).first()
    if not latest:
        return {"as_of": None, "rows": [], "n_respondents": None}
    rows = (db.query(MacroExpertSurvey)
            .filter(MacroExpertSurvey.as_of == latest.as_of)
            .order_by(MacroExpertSurvey.year).all())
    return {
        "as_of": latest.as_of.isoformat(),
        "n_respondents": latest.n_respondents,
        "source_url": latest.source_url,
        "rows": [{"indicator": r.indicator, "year": r.year, "value": r.value} for r in rows],
    }


@router.get("/market/macro/interpretation")
def macro_interpretation_get(db: Session = Depends(get_db),
                             user=Depends(get_current_user_optional)):
    from app.services.macro_interpreter import get_latest, run_state
    row = get_latest(db)
    # status нужен фронту, чтобы показать «пересобираем…» и опрашивать до готовности:
    # генерация теперь идёт в фоне и НЕ ждёт HTTP-запрос (см. POST ниже).
    status = run_state()
    if not row:
        return {"sections": None, "status": status}
    return {"sections": row.sections, "generated_at": row.generated_at.isoformat(),
            "model_used": row.model_used, "source_snapshot": row.source_snapshot,
            "status": status,
            # Персональная проекция выпуска на бумаги пользователя. Считается ЗДЕСЬ,
            # а не в выпуске: выпуск один для всех и живёт сутки, портфель у каждого
            # свой. Без портфеля возвращается приглашение его завести.
            "portfolio": _portfolio_link(db, user, row.sections),
            # 🔴 Названия компаний к тикерам выпуска. Владелец: «в рынке и сектора
            # названия компаний использовать». Голый тикер читает только тот, кто уже
            # знает рынок; фронт подставляет имя рядом.
            "company_names": _company_names(db, row.sections)}


def _company_names(db: Session, sections: dict) -> dict:
    """{тикер: короткое имя} для бумаг, названных в выпуске."""
    tickers: set[str] = set()
    for sec in (sections or {}).get("sectors") or []:
        if not isinstance(sec, dict):
            continue
        for side in ("winners", "losers"):
            for t in sec.get(side) or []:
                if isinstance(t, str):
                    tickers.add(t.upper())
    if not tickers:
        return {}
    try:
        rows = (db.query(Company.ticker, Company.name)
                .filter(Company.ticker.in_(sorted(tickers))).all())
        return {t: n for t, n in rows if t and n}
    except Exception:  # noqa: BLE001
        logger.warning("Макро: имена компаний не прочитаны", exc_info=True)
        return {}


def _portfolio_link(db: Session, user, sections: dict) -> dict:
    from app.services.macro_portfolio_link import build_link
    if not user:
        return build_link(db, None, sections)
    pf = (db.query(Portfolio).filter(Portfolio.user_id == user.id)
          .order_by(Portfolio.id).first())
    try:
        return build_link(db, pf.id if pf else None, sections or {})
    except Exception:  # noqa: BLE001
        logger.warning("Макро: связка с портфелем не собралась", exc_info=True)
        return {"available": False}


@router.post("/market/macro/interpretation")
def macro_interpretation_post(user=Depends(get_current_user_optional)):
    """Поставить перегенерацию в ФОН и сразу ответить (202).

    🔴 Раньше эндпоинт ждал генерацию целиком и на полном контексте первоисточников
    отдавал 502: прокси Timeweb обрывает долгий запрос (~219 c). Резать контекст ради
    транспортного лимита неправильно — окно модели свободно наполовину. Поэтому HTTP
    больше не ждёт: клиент получает ответ мгновенно и опрашивает GET, пока
    status.running не станет false.
    """
    from app.services.macro_interpreter import start_background_generation
    out = start_background_generation()
    # 202 — «принято, выполняется»; при повторном клике во время работы вернём то же
    # состояние без запуска второго дорогого прогона.
    return JSONResponse(status_code=202, content=out)


@router.get("/market/macro/data-quality")
def macro_data_quality(db: Session = Depends(get_db)):
    """«ОТК данных» для плашки в Обозревателе (Экономическая статистика): результат
    последнего прогона автопроверок (календарь заседаний ЦБ / кросс-сверка с
    независимыми источниками / лимиты скачков). Витринная честность платформы:
    зелёная строка «данные сверены» или жёлтый/красный callout с деталями.
    См. app/services/macro_verification.py."""
    from app.services.macro_verification import latest_results
    return latest_results(db)


@router.get("/market/macro/{code}/series")
def macro_series(code: str, metric: str = "level",
                 from_: str | None = Query(None, alias="from"), to: str | None = None,
                 db: Session = Depends(get_db)):
    ind = db.get(MacroIndicator, code)
    if not ind:
        raise HTTPException(status_code=404, detail="Показатель не найден")
    q = db.query(MacroDataPoint).filter_by(indicator_code=code, metric=metric)
    if from_:
        try:
            q = q.filter(MacroDataPoint.as_of >= date.fromisoformat(from_))
        except ValueError:
            pass
    if to:
        try:
            q = q.filter(MacroDataPoint.as_of <= date.fromisoformat(to))
        except ValueError:
            pass
    pts = q.order_by(MacroDataPoint.as_of).all()
    return {
        "code": code, "title": ind.title, "unit": ind.unit,
        "unit_prefix": _units_parts(ind.unit)[0], "unit_suffix": _units_parts(ind.unit)[1],
        "metric": metric,
        "points": [{"as_of": p.as_of.isoformat(), "value": float(p.value),
                    "is_preliminary": p.is_preliminary} for p in pts],
    }


@router.get("/market/macro/export.csv")
def macro_export_csv(country: str | None = None, since: str | None = None,
                     db: Session = Depends(get_db)):
    """Вся макростатистика платформы одним файлом — для самостоятельной работы.

    🔴 Владелец, 2026-08-14: «выгрузи все цифры в таблицу, которую можно скачать и
    дальше поработать самому». Сделано эндпоинтом, а не разовым файлом: данные
    обновляются ежедневно, и разовая выгрузка устареет к утру.

    Формат — длинный (одна строка = одно наблюдение): так таблица годится и для сводных
    в Excel, и для pandas, и не ломается, когда у показателей разные даты. Разделитель
    «;» и BOM — чтобы русский Excel открыл файл двойным кликом без «Мастера импорта»,
    а не одной колонкой с кракозябрами.
    """
    import csv
    import io

    q = db.query(MacroDataPoint, MacroIndicator).join(
        MacroIndicator, MacroIndicator.code == MacroDataPoint.indicator_code)
    if country:
        q = q.filter(MacroIndicator.country == country)
    if since:
        try:
            q = q.filter(MacroDataPoint.as_of >= date.fromisoformat(since))
        except ValueError:
            raise HTTPException(status_code=400, detail="since — дата в формате ГГГГ-ММ-ДД")
    rows = q.order_by(MacroIndicator.sort_order, MacroDataPoint.indicator_code,
                      MacroDataPoint.metric, MacroDataPoint.as_of).all()

    buf = io.StringIO()
    buf.write("\ufeff")                      # BOM для Excel
    w = csv.writer(buf, delimiter=";", lineterminator="\r\n")
    w.writerow(["Показатель", "Код", "Страна", "Метрика", "Единица", "Дата",
                "Значение", "Предварительное", "Источник", "Ссылка", "Периодичность"])
    for point, ind in rows:
        val = float(point.value) if point.value is not None else None
        w.writerow([
            ind.title, ind.code, ind.country or "", point.metric, ind.unit or "",
            point.as_of.isoformat() if point.as_of else "",
            ("" if val is None else f"{val}".replace(".", ",")),   # запятая — для Excel
            "да" if point.is_preliminary else "",
            point.source or "", point.source_url or "", ind.frequency or "",
        ])
    data = buf.getvalue()
    name = f"basis-macro-{date.today().isoformat()}.csv"
    return StreamingResponse(
        iter([data.encode("utf-8")]), media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="{name}"'})


@router.get("/market/macro/scenario-odds")
def scenario_odds(db: Session = Depends(get_db)):
    """Веса макро-сценариев (рамка среднесрочного прогноза ЦБ) с причинами сдвигов.

    🔴 Считает КОД, а не модель: ЦБ публикует пути, но не вероятности, а процент «на
    глаз» непроверяем. Метод и ограничения — методичка выпуска, раздел 14.6."""
    from app.services.macro_scenario_odds import compute
    return compute(db)


@router.get("/market/macro/scenario-impact")
def scenario_impact(scenario: str | None = None, top: int = 10,
                    db: Session = Depends(get_db)):
    """Кого двигает геополитический сценарий — с числами по конкретным бумагам.

    Без параметра отдаёт сводку по всем сценариям, с параметром — развёрнутую
    картину по одному (вклад каждого макро-канала в эффект).
    """
    from app.services.scenario_transmission import (
        load_scenario_shocks, scenario_board, scenario_impacts,
    )
    if scenario:
        known = (load_scenario_shocks().get("scenarios") or {})
        if scenario not in known:
            raise HTTPException(status_code=404,
                                detail=f"Сценарий не найден. Есть: {', '.join(known)}")
        return scenario_impacts(db, scenario, top_n=max(1, min(top, 40)))
    return scenario_board(db, per_side=max(1, min(top, 20)))

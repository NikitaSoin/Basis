"""Корпоративные события (Обозреватель, вкладка «Корп. события»): лента НОВОСТЕЙ по
компаниям — не календарь. Принцип-разделитель (владелец, 2026-07-15, после аудита
первой версии — та ошибочно тащила ВЕСЬ дивидендный календарь как есть, 82/150 записей
ленты = голый повторяющийся факт «дивиденд X ₽, дата Y»): запись попадает сюда, ТОЛЬКО
если она привязана к конкретному МОМЕНТУ-переходу (объявление/подтверждение/приближение
дедлайна/публикация) и СТАРЕЕТ — узкое окно видимости, не 30 дней подряд один и тот же
факт. Форвардные даты без решения (например, голое «СД соберётся 20.08» без повестки) —
это календарь, сюда не идут (и не идут физически: событий event_type=="corporate" здесь
нет вообще).

Дивиденд — до 3 отдельных короткоживущих момента из ОДНОЙ calendar_events-строки:
  div_recommended  — сумма впервые стала известна (created_at, узкое окно) — по методичке
                     это ещё рекомендация, не финал.
  div_approved     — ГОСА/СД утвердили — ТОЛЬКО из реальной новости Ленты (keyword),
                     календарь сам стадию не хранит — не синтезируем.
  div_cutoff_soon  — вычисляемое напоминание: T-0/T-1 до последнего дня покупки под
                     дивиденд (buy_by_date из payload, уже посчитан при сборке календаря).

report_published / report_missing — без изменений (владелец подтвердил, что это верно).
ipo_spo — CalendarEvent.event_type=="ipo" (уже отдельный пайплайн, build_ipo).
Остальное — keyword-классификация Ленты (MarketUpdate, category=="Бизнес"), БЕЗ LLM,
recall не гарантирован (честно помечено в постановке): ma, management, div_policy_negative,
share_issuance, buyback, ownership_change, delisting, promised_report_date.
"""
from datetime import date, timedelta

from sqlalchemy.orm import Session

from app.models.calendar_event import CalendarEvent
from app.models.company import Company
from app.models.earnings import EarningsDigest, EarningsReport
from app.models.market import MarketUpdate

_MISSING_GRACE_DAYS = 7      # ждём источник столько дней после event_date, прежде чем считать «не вышел»
_MISSING_LOOKBACK_DAYS = 45  # горизонт назад для показа «не вышел»
_MISS_STREAK_LOOKBACK_DAYS = 120  # окно для self-diagnostic по частоте промахов тикера
_MISS_STREAK_THRESHOLD = 2

_DIV_RECOMMEND_WINDOW_DAYS = 10  # момент «сумма стала известна» — узкое окно, не 30 дней
_DIV_CUTOFF_LEAD_DAYS = 1        # напоминание за T-1/T-0 до последнего дня покупки
_IPO_WINDOW_DAYS = 21
_BIZ_NEWS_WINDOW_DAYS = 21        # keyword-новости из Ленты — тоже короче общего окна отчётов

_KW_DIV_APPROVED = ("утвердил дивиденд", "утвердила дивиденд", "утвердило дивиденд",
                    "госа утвердил", "воса утвердил", "собрание акционеров утвердил",
                    "одобрил выплату дивиденд", "одобрила выплату дивиденд")
_KW_DIV_POLICY_NEG = ("дивидендную полит", "дивидендной полит", "приостанов", "отказал",
                      "не будет платить", "отмен", "не рекоменд", "прекращ выплат")
# 🔴 Только СОСТАВНЫЕ фразы (не голые корни типа "приобрет"/"продаж"/"гендиректор") — на
# бою 2026-07-15 голые корни ловили ложные срабатывания: "приобрет" совпало с
# "приобретается отдельно" в статье про страхование (не M&A), "гендиректор" — с ЛЮБОЙ
# цитатой топ-менеджера (не только со сменой), "продаж" — с обычным "продажи выросли".
_KW_MA = ("поглощен", "слияни", "m&a", "консолидац",
          "сделку по покупке", "сделка по покупке",
          "приобрела контрольный пакет", "приобрёл контрольный пакет",
          "приобрела долю в", "приобрёл долю в",
          "приобретет компанию", "приобретёт компанию", "приобретает компанию")
_KW_SHARE_ISSUANCE = ("допэмисси", "доп. эмисси", "дополнительную эмиссию",
                      "дополнительный выпуск акций", "допвыпуск", "вторичное размещение")
_KW_BUYBACK = ("байбэк", "обратный выкуп", "buyback")
_KW_DELISTING = ("делистинг", "исключение из котировального списка", "прекращение листинга")
_KW_OWNERSHIP = ("сменила акционер", "сменил акционер", "сменился акционер",
                 "новый мажоритарный", "новым мажоритарным", "продал долю", "продала долю",
                 "продажа доли в", "смена бенефициара", "смена владельца", "сменился владелец")
_KW_MGMT = ("новый генеральный директор", "новым генеральным директором",
            "нового генерального директора", "избран генеральным директором",
            "избрана генеральным директором", "назначен генеральным директором",
            "назначена генеральным директором", "покинет пост", "покинул пост",
            "покинула пост", "уходит с поста", "ушел с поста", "ушёл с поста",
            "сменил гендиректора", "сменила гендиректора",
            "новый председатель совета директоров",
            "избран председателем совета директоров",
            "избрана председателем совета директоров")
_KW_PROMISED_REPORT = ("планирует опубликовать отчетност", "опубликует отчетность",
                       "объявила дату публикации отчетност", "дату раскрытия отчетност",
                       "сообщила дату публикации")


def _classify_business(title: str, summary: str | None) -> str | None:
    text = f"{title} {summary or ''}".lower()
    if "дивиденд" in text and any(k in text for k in _KW_DIV_APPROVED):
        return "div_approved"
    if "дивиденд" in text and any(k in text for k in _KW_DIV_POLICY_NEG):
        return "div_policy_negative"
    if any(k in text for k in _KW_MA):
        return "ma"
    if any(k in text for k in _KW_SHARE_ISSUANCE):
        return "share_issuance"
    if any(k in text for k in _KW_BUYBACK):
        return "buyback"
    if any(k in text for k in _KW_DELISTING):
        return "delisting"
    if any(k in text for k in _KW_OWNERSHIP):
        return "ownership_change"
    if any(k in text for k in _KW_MGMT):
        return "management"
    if any(k in text for k in _KW_PROMISED_REPORT):
        return "promised_report_date"
    return None


def build_corporate_news(db: Session, portfolio_tickers: list[str] | None = None,
                          days_back: int = 30, limit: int = 150) -> list[dict]:
    """portfolio_tickers: None — без фильтра; [] — пустой портфель (ничего не покажет);
    list — фильтр по тикерам."""
    today = date.today()
    companies = {c.ticker: c for c in db.query(Company).all()}
    out: list[dict] = []

    def _allowed(ticker: str | None) -> bool:
        if portfolio_tickers is None:
            return True
        return bool(ticker) and ticker in portfolio_tickers

    # ---- report_published ----
    reports_q = (db.query(EarningsReport, EarningsDigest)
                 .outerjoin(EarningsDigest, EarningsDigest.report_id == EarningsReport.id)
                 .filter(EarningsReport.status == "processed",
                         EarningsReport.published_at.isnot(None),
                         EarningsReport.published_at >= today - timedelta(days=days_back)))
    for r, dg in reports_q.all():
        c = companies.get(r.ticker)
        if not c or not _allowed(r.ticker):
            continue
        std = f", {r.standard}" if r.standard else ""
        out.append({
            "kind": "report_published",
            "ticker": r.ticker, "company": c.name, "sector": c.sector,
            "date": r.published_at.isoformat(),
            "title": f"{c.name}: вышел отчёт ({r.period}{std})",
            "detail": dg.one_liner if dg else None,
            "epistemic": "факт",
            "link_to": "reports",
            "likely_calendar_error": False,
        })

    # ---- report_missing (grace period прошёл, источник не найден) ----
    lo = today - timedelta(days=_MISSING_LOOKBACK_DAYS)
    hi = today - timedelta(days=_MISSING_GRACE_DAYS)
    matched_event_ids = {
        row[0] for row in db.query(EarningsReport.calendar_event_id)
        .filter(EarningsReport.status == "processed",
                EarningsReport.calendar_event_id.isnot(None)).all()
    }
    # Разные источники детекта (MOEX ir-calendar / smart-lab) могут дать 2+ CalendarEvent
    # на один и тот же (тикер, дата) — группируем ПЕРЕД оценкой "найден/не найден", иначе
    # (а) один и тот же промах считается дважды в self-diagnostic, (б) карточка дублируется,
    # (в) если совпадение нашлось у ОДНОЙ из дублирующихся записей, а не у другой, получим
    # ложный "не вышел" при реально найденном отчёте.
    streak_lo = today - timedelta(days=_MISS_STREAK_LOOKBACK_DAYS)
    streak_rows = (db.query(CalendarEvent.ticker, CalendarEvent.id, CalendarEvent.event_date)
                   .filter(CalendarEvent.event_type == "earnings",
                           CalendarEvent.event_date >= streak_lo,
                           CalendarEvent.event_date <= hi).all())
    streak_groups: dict[tuple, set] = {}
    for ticker, ev_id, ev_date in streak_rows:
        streak_groups.setdefault((ticker, ev_date), set()).add(ev_id)
    miss_counts: dict[str, int] = {}
    for (ticker, _ev_date), ev_ids in streak_groups.items():
        if not (ev_ids & matched_event_ids):
            miss_counts[ticker] = miss_counts.get(ticker, 0) + 1

    missing_rows = (db.query(CalendarEvent)
                    .filter(CalendarEvent.event_type == "earnings",
                            CalendarEvent.event_date >= lo, CalendarEvent.event_date <= hi).all())
    missing_groups: dict[tuple, list] = {}
    for ev in missing_rows:
        missing_groups.setdefault((ev.ticker, ev.event_date), []).append(ev)
    for (ticker, ev_date), evs in missing_groups.items():
        if {e.id for e in evs} & matched_event_ids:
            continue
        c = companies.get(ticker)
        if not c or not _allowed(ticker):
            continue
        ev = evs[0]
        misses = miss_counts.get(ev.ticker, 0)
        likely_calendar_error = misses >= _MISS_STREAK_THRESHOLD
        detail = ("Этот тикер регулярно попадает в «не вышел» — вероятнее, мы неточно "
                  "оцениваем дату отчёта, а не компания срывает публикацию."
                  if likely_calendar_error else
                  "Либо отчёт вышел, но мы не нашли источник, либо расчётная дата в "
                  "календаре была неточной (оценка, не подтверждённая компанией).")
        out.append({
            "kind": "report_missing",
            "ticker": ev.ticker, "company": c.name, "sector": c.sector,
            "date": ev.event_date.isoformat(),
            "title": f"{c.name}: отчёт ожидался {ev.event_date.strftime('%d.%m.%Y')} — публикация не найдена",
            "detail": detail,
            "epistemic": "оценка",
            "link_to": "company",
            "likely_calendar_error": likely_calendar_error,
        })

    # ---- div_recommended: сумма дивиденда впервые стала известна (created_at, узкое окно) ----
    div_new_q = (db.query(CalendarEvent)
                .filter(CalendarEvent.event_type == "dividend",
                        CalendarEvent.created_at >= today - timedelta(days=_DIV_RECOMMEND_WINDOW_DAYS)))
    seen_div_rec = set()
    for ev in div_new_q.all():
        amount = (ev.payload or {}).get("amount")
        if not amount:
            continue
        c = companies.get(ev.ticker)
        if not c or not _allowed(ev.ticker):
            continue
        key = (ev.ticker, ev.event_date)
        if key in seen_div_rec:
            continue
        seen_div_rec.add(key)
        dy = (ev.payload or {}).get("dividend_yield")
        yield_part = f", доходность ≈{dy:g}%" if dy is not None else ""
        out.append({
            "kind": "div_recommended",
            "ticker": ev.ticker, "company": c.name, "sector": c.sector,
            "date": ev.created_at.date().isoformat(),
            "title": (f"{c.name}: объявлен дивиденд {amount:g} ₽/акц.{yield_part} "
                     f"(отсечка {ev.event_date.strftime('%d.%m.%Y')})"),
            "detail": "Сумма объявлена — по методичке Basis это рекомендация, окончательное "
                      "решение утверждает собрание акционеров.",
            "epistemic": "факт",
            "link_to": "company",
            "likely_calendar_error": False,
        })

    # ---- div_cutoff_soon: T-0/T-1 до последнего дня покупки под дивиденд ----
    div_cutoff_q = (db.query(CalendarEvent)
                    .filter(CalendarEvent.event_type == "dividend",
                            CalendarEvent.event_date >= today,
                            CalendarEvent.event_date <= today + timedelta(days=5)))
    seen_cutoff = set()
    for ev in div_cutoff_q.all():
        payload = ev.payload or {}
        amount = payload.get("amount")
        buy_by = payload.get("buy_by_date")
        if not amount or not buy_by:
            continue
        try:
            buy_by_date = date.fromisoformat(buy_by)
        except ValueError:
            continue
        if not (today <= buy_by_date <= today + timedelta(days=_DIV_CUTOFF_LEAD_DAYS)):
            continue
        c = companies.get(ev.ticker)
        if not c or not _allowed(ev.ticker):
            continue
        key = (ev.ticker, ev.event_date)
        if key in seen_cutoff:
            continue
        seen_cutoff.add(key)
        when = "сегодня" if buy_by_date == today else "завтра"
        out.append({
            "kind": "div_cutoff_soon",
            "ticker": ev.ticker, "company": c.name, "sector": c.sector,
            "date": buy_by_date.isoformat(),
            "title": (f"{c.name}: {when} последний день купить под дивиденд {amount:g} ₽/акц. "
                     f"(отсечка {ev.event_date.strftime('%d.%m.%Y')})"),
            "detail": None,
            "epistemic": "факт",
            "link_to": "company",
            "likely_calendar_error": False,
        })

    # ---- ipo_spo (CalendarEvent.event_type=="ipo", источник — build_ipo, keyword по Ленте) ----
    ipo_q = (db.query(CalendarEvent)
            .filter(CalendarEvent.event_type == "ipo",
                    CalendarEvent.created_at >= today - timedelta(days=_IPO_WINDOW_DAYS)))
    seen_ipo = set()
    for ev in ipo_q.all():
        ticker = ev.ticker  # почти всегда None — Лента-детект не резолвит тикер эмитента
        if not _allowed(ticker):
            continue
        key = (ticker, ev.event_date, ev.title)
        if key in seen_ipo:
            continue
        seen_ipo.add(key)
        c = companies.get(ticker) if ticker else None
        out.append({
            "kind": "ipo_spo",
            "ticker": ticker, "company": c.name if c else None, "sector": c.sector if c else None,
            "date": ev.event_date.isoformat(),
            "title": ev.title,
            "detail": (ev.payload or {}).get("summary"),
            "epistemic": "факт",
            "link_to": "company" if ticker else None,
            "likely_calendar_error": False,
        })

    # ---- keyword-классификация Ленты: ma / management / div_approved / div_policy_negative /
    # share_issuance / buyback / ownership_change / delisting / promised_report_date ----
    biz_q = (db.query(MarketUpdate)
             .filter(MarketUpdate.status == "published",
                     MarketUpdate.category == "Бизнес",
                     MarketUpdate.published_at >= today - timedelta(days=_BIZ_NEWS_WINDOW_DAYS),
                     MarketUpdate.affected_tickers.isnot(None)))
    for mu in biz_q.all():
        subtype = _classify_business(mu.title, mu.summary)
        if not subtype:
            continue
        for t in (mu.affected_tickers or []):
            c = companies.get(t)
            if not c or not _allowed(t):
                continue
            out.append({
                "kind": subtype,
                "ticker": t, "company": c.name, "sector": c.sector,
                "date": mu.published_at.date().isoformat(),
                "title": mu.title,
                "detail": mu.summary,
                "epistemic": "факт",
                "link_to": "company",
                "likely_calendar_error": False,
            })

    out.sort(key=lambda x: x["date"], reverse=True)
    return out[:limit]

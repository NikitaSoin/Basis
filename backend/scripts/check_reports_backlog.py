"""Чекер бэклога «свежий отчёт вышел → цифры ещё не перенесены в карточку».

Полуавтомат переноса отчётности в financials.json (владелец, 2026-07-25,
вариант (а)): рантайм-запись в файлы на Timeweb бессмысленна (перетирается
деплоем), поэтому перенос полного P&L/баланса/ОДДС делается DEV-TIME —
report-fetcher добывает сам отчёт, цифры переносятся в
companies/<TICKER>/financials.json (interim-блок) и коммитятся.

Этот скрипт — ДЕТЕКТОР работы: сравнивает свежие финансовые записи ленты
«Отчёты» (боевой API /api/market/earnings — то, что уже нашёл report_watch)
с состоянием interim-блока карточки и печатает, кому нужен добор.

Эвристика соответствия периодов (отчёт «за 1П 2026» пишется в ленту как
«первое полугодие»/«1П 2026»/дата — строгого формата нет): отчёт,
опубликованный в дату D, покрывает период, закончившийся на последнем
квартальном рубеже перед (D − 15 дней). Если последний interim-период
карточки заканчивается РАНЬШЕ этого рубежа — цифры отстают, тикер в бэклог.

Запуск: python scripts/check_reports_backlog.py  (из backend/)
"""
from __future__ import annotations

import json
import sys
from datetime import date, timedelta
from pathlib import Path

import httpx

API = "https://nikitasoin-basis-a772.twc1.net"
COMPANIES = Path(__file__).parent.parent / "companies"

# Операционные релизы не несут P&L/баланс — добирать нечего.
_FINANCIAL_STANDARDS = {"МСФО", "РСБУ", "РСБУ (ГИР БО)", "отчётность"}


def _expected_period_end(published: date, period: str | None = None) -> date:
    """Последний квартальный рубеж перед (published − 15 дней): отчёт за 1П,
    вышедший 20 июля, покрывает период до 30 июня; годовой, вышедший в марте,
    — до 31 декабря. 15 дней — минимальный лаг подготовки отчётности.

    Если period записи — явный ГОД («2025», «2024 год»), квартальная эвристика
    неприменима: годовой отчёт за 2025, вышедший в июне 2026, покрывает период
    только до 2025-12-31 (не до последнего квартального рубежа перед датой
    публикации) — иначе карточки с годовыми данными ложно попадали в бэклог."""
    import re as _re
    if period:
        m = _re.match(r"^((?:19|20)\d{2})(?:\s*год[а]?)?$", period.strip())
        if m:
            return date(int(m.group(1)), 12, 31)
    anchor = published - timedelta(days=15)
    year = anchor.year
    for q_end in (date(year, 12, 31), date(year, 9, 30), date(year, 6, 30),
                  date(year, 3, 31), date(year - 1, 12, 31)):
        if q_end <= anchor:
            return q_end
    return date(year - 1, 9, 30)


def _last_covered_end(fin: dict) -> date | None:
    """Самая поздняя дата, до которой карточка уже покрыта цифрами:
    max(конец последнего interim-периода, конец последнего fiscal year)."""
    ends: list[date] = []
    for p in (fin.get("interim") or {}).get("periods", []):
        try:
            ends.append(date.fromisoformat(p["end_date"]))
        except (KeyError, ValueError):
            continue
    meta = fin.get("meta") or {}
    years = meta.get("fiscal_years") or fin.get("fiscal_years") or []
    if years:
        try:
            ends.append(date(int(years[-1]), 12, 31))
        except (TypeError, ValueError):
            pass
    return max(ends) if ends else None


def main() -> int:
    r = httpx.get(f"{API}/api/market/earnings", params={"limit": 60}, timeout=30)
    r.raise_for_status()
    reports = r.json().get("reports", [])
    backlog = []
    for rep in reports:
        std = (rep.get("standard") or "").strip()
        if std not in _FINANCIAL_STANDARDS or not rep.get("published_at"):
            continue
        ticker = rep["ticker"]
        fin_path = COMPANIES / ticker / "financials.json"
        if not fin_path.exists():
            backlog.append((ticker, rep["period"], std, rep["published_at"][:10],
                            "НЕТ financials.json"))
            continue
        try:
            fin = json.loads(fin_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as e:
            backlog.append((ticker, rep["period"], std, rep["published_at"][:10],
                            f"файл не читается: {type(e).__name__}"))
            continue
        published = date.fromisoformat(rep["published_at"][:10])
        expected = _expected_period_end(published, rep.get("period"))
        covered = _last_covered_end(fin)
        if covered is None or covered < expected:
            backlog.append((ticker, rep["period"], std, rep["published_at"][:10],
                            f"карточка до {covered}, отчёт до {expected}"))
    if not backlog:
        print("Бэклога нет — карточки покрывают все свежие отчёты ленты.")
        return 0
    print(f"БЭКЛОГ ({len(backlog)}): свежий отчёт вышел, цифры в карточку не перенесены\n")
    seen = set()
    for t, period, std, pub, why in backlog:
        mark = "" if t not in seen else "  (повтор тикера — то же событие другим путём)"
        seen.add(t)
        print(f"  {t:6} {std:14} опубл. {pub}  период «{period}» — {why}{mark}")
    print("\nДальше: report-fetcher по каждому тикеру (сам отчёт, не новость) → "
          "перенос в financials.json interim → коммит.")
    return 1


if __name__ == "__main__":
    sys.exit(main())

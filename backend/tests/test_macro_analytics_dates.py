"""Дата документа из имени файла: форматы ЦМАКП, из-за которых на бою было 0 записок."""
from datetime import date
from app.services.macro_analytics import doc_date


def test_iso_with_hyphens():
    assert doc_date("http://x/PR-OTR_2026-08-27.pdf") == date(2026, 8, 27)


def test_full_month_name():
    d = doc_date("http://x/World_trends_august_2026.pdf")
    assert d is not None and (d.year, d.month) == (2026, 8)


def test_bare_year_gives_none():
    assert doc_date("http://x/TT9_2026.pdf") is None
    assert doc_date("http://x/macro69.pdf") is None

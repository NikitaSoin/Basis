"""Живая подмена канонических индикаторов в macro.json.snapshot на отдаче."""
import datetime as dt

from app.services.macro_snapshot_live import enrich_snapshot_live


class _DB:
    VALS = {"key_rate": (14.0, dt.date(2026, 7, 24)),
            "inflation": (5.94, dt.date(2026, 7, 27)),
            "inflation_expectations": (14.7, dt.date(2026, 7, 31)),
            "usdrub": (78.4, dt.date(2026, 7, 31))}

    def execute(self, q, p):
        v = self.VALS.get(p["c"])
        return type("R", (), {"first": staticmethod(lambda v=v: v)})()


def test_canonical_indicators_go_live_company_rows_untouched():
    data = {"snapshot": [
        {"indicator": "Ключевая ставка ЦБ", "value": "14,25%",
         "trend_note": "−25 б.п. 19 июня, следующее — 24 июля"},
        {"indicator": "Внутренняя цена ГК-проката", "value": "~45 тыс ₽/т"},
        {"indicator": "Инфляция РФ (г/г)", "value": "~5,3% (оценка 2026)"},
        {"indicator": "Инфляционные ожидания", "value": "13%"},
    ]}
    enrich_snapshot_live(_DB(), data)
    snap = data["snapshot"]
    assert snap[0]["value"] == "14%" and snap[0]["stale_value"] == "14,25%"
    assert "актуально на" in snap[0]["trend_note"]      # старые даты заседаний убраны
    assert snap[1]["value"] == "~45 тыс ₽/т" and "live_updated" not in snap[1]
    assert snap[2]["value"] == "5,94%"
    assert snap[3]["value"] == "14,7%"


def test_matching_value_left_as_is():
    data = {"snapshot": [{"indicator": "Ключевая ставка ЦБ", "value": "14%"}]}
    enrich_snapshot_live(_DB(), data)
    assert "stale_value" not in data["snapshot"][0]

"""Ручка вкладки «Макроэкономика» нового образца: отдаёт файл компании, 404 без файла."""
import json

from fastapi.testclient import TestClient

from app.api import companies as companies_api
from app.main import app


def test_macro_tab_served_with_calc_passport(tmp_path, monkeypatch):
    folder = tmp_path / "TEST"
    folder.mkdir()
    (folder / "macro_tab.json").write_text(json.dumps({"meta": {"ticker": "TEST"}, "now": {"regime": "смешанно", "text": "т", "main_pressure": "долг"}}, ensure_ascii=False), encoding="utf-8")
    (folder / "macro_scenarios.json").write_text(json.dumps({"computed_at": "2026-09-16", "held_at_base": ["oil_tax_price"], "rate_valuation": {"valuation_channel_pct": {"low": -4, "high": -2}}}), encoding="utf-8")
    monkeypatch.setattr(companies_api, "COMPANIES_DIR", tmp_path)
    client = TestClient(app)
    r = client.get("/api/companies/by-ticker/test/macro-tab")
    assert r.status_code == 200
    body = r.json()
    assert body["now"]["regime"] == "смешанно"
    assert body["calc"]["held_at_base"] == ["oil_tax_price"]
    assert body["calc"]["rate_valuation"]["valuation_channel_pct"]["low"] == -4


def test_macro_tab_404_without_file(tmp_path, monkeypatch):
    monkeypatch.setattr(companies_api, "COMPANIES_DIR", tmp_path)
    client = TestClient(app)
    assert client.get("/api/companies/by-ticker/NOPE/macro-tab").status_code == 404

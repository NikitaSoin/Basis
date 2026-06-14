"""Тесты Ленты новостей Обозревателя (Направление 1)."""
from datetime import datetime, timezone

from app.models.market import MarketUpdate
from app.services import news_pipeline as np
from app.services import llm


def test_config_has_feeds():
    cfg = np.load_config()
    assert cfg["feeds"], "должны быть RSS-ленты в конфиге"
    assert set(f["source"] for f in cfg["feeds"]) <= {"interfax", "rbc", "kommersant"}
    assert cfg["schedule_msk_hours"] == [7, 13, 19, 1]


def test_cluster_near_identical():
    items = [
        {"title": "ЦБ повысил ключевую ставку до 18%", "url": "a"},
        {"title": "ЦБ повысил ключевую ставку до 18 %", "url": "b"},
        {"title": "Газпром отчитался о росте прибыли за год", "url": "c"},
    ]
    np.cluster_items(items, 0.62)
    assert items[0]["cluster_idx"] == items[1]["cluster_idx"]
    assert items[2]["cluster_idx"] != items[0]["cluster_idx"]


def test_llm_results_parsing(monkeypatch):
    monkeypatch.setattr(llm, "complete", lambda *a, **k: {
        "results": [{"id": 0, "keep": True, "importance": "high", "reason": "ставка"},
                    {"id": 1, "keep": False, "importance": "low", "reason": "быт"}]
    })
    out = np._llm_results(np._FILTER_SYS, {"news": []})
    assert out[0]["keep"] is True and out[0]["importance"] == "high"
    assert out[1]["keep"] is False


def test_map_tickers_drops_unknown(monkeypatch, db):
    from app.models.company import Company
    db.add(Company(ticker="SBER", name="Сбербанк", sector="banks"))
    db.commit()
    monkeypatch.setattr(llm, "complete", lambda *a, **k: {
        "results": [{"id": 0, "tickers": ["SBER", "FAKE"], "sectors": ["banks"]}]
    })
    res = np.map_tickers([{"id": 0, "summary": "Сбер"}], db)
    assert res[0]["tickers"] == ["SBER"]  # FAKE отброшен (нет в справочнике)


def _seed(db, **kw):
    base = dict(title="t", published_at=datetime.now(timezone.utc), status="published")
    base.update(kw)
    row = MarketUpdate(**base)
    db.add(row); db.commit(); db.refresh(row)
    return row


def test_news_endpoint_only_published(client, db):
    _seed(db, title="Опубликованная", importance="high", rubric="economy",
          summary="s", impact_comment="i", affected_tickers=["SBER"], affected_sectors=["banks"],
          source="rbc", source_url="u1")
    _seed(db, title="Отфильтрованная", status="filtered_out", source_url="u2")
    r = client.get("/api/market/news")
    assert r.status_code == 200
    titles = [x["title"] for x in r.json()]
    assert "Опубликованная" in titles and "Отфильтрованная" not in titles


def test_news_filters(client, db):
    _seed(db, title="High banks", importance="high", affected_tickers=["SBER"],
          affected_sectors=["banks"], source_url="h1")
    _seed(db, title="Low oil", importance="low", affected_tickers=["LKOH"],
          affected_sectors=["oil_gas"], source_url="l1")
    assert all(x["importance"] == "high" for x in client.get("/api/market/news?importance=high").json())
    tk = client.get("/api/market/news?ticker=LKOH").json()
    assert len(tk) == 1 and tk[0]["title"] == "Low oil"


def test_news_item_404(client):
    assert client.get("/api/market/news/99999").status_code == 404

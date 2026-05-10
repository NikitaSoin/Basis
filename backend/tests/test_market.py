def test_create_market_update(client):
    response = client.post("/api/market/updates", json={
        "title": "Fed raises rates by 25bps",
        "content": "The Federal Reserve increased interest rates...",
        "source": "Reuters",
        "published_at": "2026-05-09T10:00:00Z",
    })
    assert response.status_code == 201
    data = response.json()
    assert data["title"] == "Fed raises rates by 25bps"
    assert data["source"] == "Reuters"


def test_create_market_overview(client):
    response = client.post("/api/market/overviews", json={
        "overview_type": "express",
        "content": "Markets opened higher on strong earnings...",
        "period": "2026-05",
    })
    assert response.status_code == 201
    data = response.json()
    assert data["overview_type"] == "express"
    assert data["period"] == "2026-05"


def test_get_market_updates(client):
    client.post("/api/market/updates", json={
        "title": "Oil prices fall",
        "content": "Brent crude dropped 2%...",
        "published_at": "2026-05-09T08:00:00Z",
    })
    response = client.get("/api/market/updates")
    assert response.status_code == 200
    assert len(response.json()) >= 1


def test_get_market_overviews_filtered_by_type(client):
    client.post("/api/market/overviews", json={
        "overview_type": "deep",
        "content": "In-depth analysis of Q2 2026...",
        "period": "2026-Q2",
    })
    client.post("/api/market/overviews", json={
        "overview_type": "express",
        "content": "Quick summary...",
        "period": "2026-Q2",
    })

    all_resp = client.get("/api/market/overviews")
    assert all_resp.status_code == 200
    assert len(all_resp.json()) >= 2

    deep_resp = client.get("/api/market/overviews?type=deep")
    assert deep_resp.status_code == 200
    deep_list = deep_resp.json()
    assert len(deep_list) >= 1
    assert all(o["overview_type"] == "deep" for o in deep_list)

    express_resp = client.get("/api/market/overviews?type=express")
    assert express_resp.status_code == 200
    assert all(o["overview_type"] == "express" for o in express_resp.json())

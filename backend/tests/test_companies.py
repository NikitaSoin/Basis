def test_create_company(client):
    response = client.post("/api/companies", json={"ticker": "AAPL", "name": "Apple Inc.", "sector": "Technology"})
    assert response.status_code == 201
    data = response.json()
    assert data["ticker"] == "AAPL"
    assert data["name"] == "Apple Inc."
    assert "id" in data


def test_create_company_duplicate_ticker(client):
    client.post("/api/companies", json={"ticker": "MSFT", "name": "Microsoft"})
    response = client.post("/api/companies", json={"ticker": "MSFT", "name": "Microsoft 2"})
    assert response.status_code == 409


def test_get_company(client):
    created = client.post("/api/companies", json={"ticker": "GOOGL", "name": "Google"}).json()
    response = client.get(f"/api/companies/{created['id']}")
    assert response.status_code == 200
    assert response.json()["ticker"] == "GOOGL"


def test_get_company_not_found(client):
    assert client.get("/api/companies/999999").status_code == 404


def test_add_and_get_analysis(client):
    company = client.post("/api/companies", json={"ticker": "AMZN", "name": "Amazon"}).json()
    payload = {
        "bull_case": ["AWS growth", "Prime expansion"],
        "bear_case": ["Thin margins", "Regulation"],
        "risks": ["AWS competition"],
        "fair_price": "185.50",
        "analyst_note": "Long-term hold",
        "business_model": {"text": "E-commerce + AWS cloud"},
        "financials": {"revenue": "574B", "ebitda": "85B"},
        "competitors": {"text": "Google Cloud, Azure"},
        "macro_economy": {"text": "Sensitive to consumer spending"},
        "global_economy": {"text": "Strong in US, growing in EU"},
        "geopolitics": {"text": "US-China tech tensions"},
        "technical_analysis": {"text": "Above 200-day MA, RSI 55"},
    }
    r = client.post(f"/api/companies/{company['id']}/analysis", json=payload)
    assert r.status_code == 201
    data = r.json()
    assert data["bull_case"] == ["AWS growth", "Prime expansion"]
    assert data["business_model"] == {"text": "E-commerce + AWS cloud"}
    assert data["technical_analysis"] == {"text": "Above 200-day MA, RSI 55"}

    analyses = client.get(f"/api/companies/{company['id']}/analysis").json()
    assert len(analyses) == 1
    assert analyses[0]["fair_price"] == "185.50"
    assert analyses[0]["financials"] == {"revenue": "574B", "ebitda": "85B"}


def test_add_and_get_quote(client):
    company = client.post("/api/companies", json={"ticker": "TSLA", "name": "Tesla"}).json()
    r = client.post(f"/api/companies/{company['id']}/quotes", json={
        "date": "2026-05-09", "open": "250.00", "close": "255.00",
        "high": "257.00", "low": "248.00", "volume": 1000000,
    })
    assert r.status_code == 201

    quotes = client.get(f"/api/companies/{company['id']}/quotes").json()
    assert len(quotes) == 1
    assert quotes[0]["close"] == "255.0000"

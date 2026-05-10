def test_create_portfolio(client):
    user = client.post("/api/users", json={"email": "p1@test.com", "password": "pass"}).json()
    response = client.post("/api/portfolios", json={"user_id": user["id"], "name": "My Portfolio"})
    assert response.status_code == 201
    data = response.json()
    assert data["name"] == "My Portfolio"
    assert data["user_id"] == user["id"]
    assert data["positions"] == []


def test_add_position(client):
    user = client.post("/api/users", json={"email": "p2@test.com", "password": "pass"}).json()
    company = client.post("/api/companies", json={"ticker": "NKE", "name": "Nike"}).json()
    portfolio = client.post("/api/portfolios", json={"user_id": user["id"], "name": "Growth"}).json()

    response = client.post(f"/api/portfolios/{portfolio['id']}/positions", json={
        "company_id": company["id"], "quantity": "10.0", "avg_buy_price": "95.00",
    })
    assert response.status_code == 201
    assert response.json()["company_id"] == company["id"]


def test_get_portfolio_with_positions(client):
    user = client.post("/api/users", json={"email": "p3@test.com", "password": "pass"}).json()
    company = client.post("/api/companies", json={"ticker": "META", "name": "Meta"}).json()
    portfolio = client.post("/api/portfolios", json={"user_id": user["id"], "name": "Tech"}).json()
    client.post(f"/api/portfolios/{portfolio['id']}/positions", json={
        "company_id": company["id"], "quantity": "5.0", "avg_buy_price": "500.00",
    })

    response = client.get(f"/api/portfolios/{portfolio['id']}")
    assert response.status_code == 200
    data = response.json()
    assert len(data["positions"]) == 1
    assert data["positions"][0]["quantity"] == "5.0000"


def test_delete_position(client):
    user = client.post("/api/users", json={"email": "p4@test.com", "password": "pass"}).json()
    company = client.post("/api/companies", json={"ticker": "NVDA", "name": "Nvidia"}).json()
    portfolio = client.post("/api/portfolios", json={"user_id": user["id"], "name": "Chips"}).json()
    position = client.post(f"/api/portfolios/{portfolio['id']}/positions", json={
        "company_id": company["id"], "quantity": "3.0", "avg_buy_price": "800.00",
    }).json()

    r = client.delete(f"/api/portfolios/{portfolio['id']}/positions/{position['id']}")
    assert r.status_code == 204

    after = client.get(f"/api/portfolios/{portfolio['id']}").json()
    assert after["positions"] == []

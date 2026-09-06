"""Портфели: создание, позиции, чтение, удаление.

🔴 Тесты писались, когда портфели были открыты анониму. С 2026-08-04 они требуют
входа либо гостевого токена (владелец: «у аналитики портфеля не надо регистрироваться
базово»), а создание компаний — служебного токена (аудит 2026-07-26). Тесты этого не
знали и падали с июля. Здесь они приведены к реальному контракту: пользователь
регистрируется по-настоящему, компании создаются служебным клиентом.
"""


def test_create_portfolio(user_client):
    client, user_id = user_client
    response = client.post("/api/portfolios", json={"name": "My Portfolio"})
    assert response.status_code == 201
    data = response.json()
    assert data["name"] == "My Portfolio"
    assert data["user_id"] == user_id
    assert data["positions"] == []


def test_create_portfolio_requires_auth(client):
    """Без входа и без гостевого токена портфель не создаётся — это не регрессия,
    а защита: иначе в базе копятся ничьи портфели."""
    assert client.post("/api/portfolios", json={"name": "Ничей"}).status_code == 401


def test_add_position(user_client, ops_client):
    client, _ = user_client
    company = ops_client.post("/api/companies", json={"ticker": "NKE", "name": "Nike"}).json()
    portfolio = client.post("/api/portfolios", json={"name": "Growth"}).json()

    response = client.post(f"/api/portfolios/{portfolio['id']}/positions", json={
        "company_id": company["id"], "quantity": "10.0", "avg_buy_price": "95.00",
    })
    assert response.status_code == 201
    assert response.json()["company_id"] == company["id"]


def test_get_portfolio_with_positions(user_client, ops_client):
    client, _ = user_client
    company = ops_client.post("/api/companies", json={"ticker": "META", "name": "Meta"}).json()
    portfolio = client.post("/api/portfolios", json={"name": "Tech"}).json()
    client.post(f"/api/portfolios/{portfolio['id']}/positions", json={
        "company_id": company["id"], "quantity": "5.0", "avg_buy_price": "500.00",
    })

    response = client.get(f"/api/portfolios/{portfolio['id']}")
    assert response.status_code == 200
    data = response.json()
    assert len(data["positions"]) == 1
    assert data["positions"][0]["quantity"] == "5.0000"


def test_delete_position(user_client, ops_client):
    client, _ = user_client
    company = ops_client.post("/api/companies", json={"ticker": "NVDA", "name": "Nvidia"}).json()
    portfolio = client.post("/api/portfolios", json={"name": "Chips"}).json()
    position = client.post(f"/api/portfolios/{portfolio['id']}/positions", json={
        "company_id": company["id"], "quantity": "3.0", "avg_buy_price": "800.00",
    }).json()

    r = client.delete(f"/api/portfolios/{portfolio['id']}/positions/{position['id']}")
    assert r.status_code == 204

    after = client.get(f"/api/portfolios/{portfolio['id']}").json()
    assert after["positions"] == []


def test_guest_portfolio_records_offer_acceptance(client):
    """Гость заключает договор конклюдентно — созданием портфеля. Момент акцепта
    обязан фиксироваться так же, как у зарегистрированных (юр-аудит 2026-09-06)."""
    guest = "guesttokentestcase00000000000001"
    r = client.post("/api/portfolios", json={"name": "Гостевой"},
                    headers={"X-Guest-Token": guest})
    assert r.status_code == 201
    me = client.get("/api/consents/me", headers={"X-Guest-Token": guest}).json()
    assert me["offer_accept"]["granted"] is True
    assert me["offer_accept"]["version"] == "1.0"

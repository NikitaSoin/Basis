"""Тесты эндпоинтов блока «Финансы и оценка» и сравнения по сектору.

Эндпоинты отдают файлы из companies/<TICKER>/ и sectors/<key>/, поэтому
проверяем на реальных данных (ROSN, сектор oil_gas).
"""


def test_financials_json_ok(client):
    r = client.get("/api/companies/by-ticker/ROSN/financials")
    assert r.status_code == 200
    data = r.json()
    assert data["meta"]["ticker"] == "ROSN"
    assert "multiples" in data


def test_financials_json_lowercase_ticker(client):
    # тикер не чувствителен к регистру
    assert client.get("/api/companies/by-ticker/rosn/financials").status_code == 200


def test_financials_summary_ok(client):
    r = client.get("/api/companies/by-ticker/ROSN/financials-summary")
    assert r.status_code == 200
    assert "text/markdown" in r.headers["content-type"]
    assert len(r.text) > 0


def test_financials_not_found(client):
    # компания без financials.json (или несуществующая)
    assert client.get("/api/companies/by-ticker/NOSUCH/financials").status_code == 404


def test_financials_path_traversal_blocked(client):
    # имя с недопустимыми символами не должно выходить за каталог
    assert client.get("/api/companies/by-ticker/..%2F..%2Fetc/financials").status_code == 404


def test_sector_peers_ok(client):
    r = client.get("/api/sectors/oil_gas/peers")
    assert r.status_code == 200
    data = r.json()
    assert data["meta"]["sector_key"] == "oil_gas"
    assert "comparison_table" in data
    assert "maps" in data


def test_sector_peers_not_found(client):
    assert client.get("/api/sectors/nosuch/peers").status_code == 404

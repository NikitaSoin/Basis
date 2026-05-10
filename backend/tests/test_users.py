def test_create_user(client):
    response = client.post("/api/users", json={"email": "test@example.com", "password": "secret123"})
    assert response.status_code == 201
    data = response.json()
    assert data["email"] == "test@example.com"
    assert data["is_active"] is True
    assert "id" in data
    assert "hashed_password" not in data


def test_create_user_duplicate_email(client):
    client.post("/api/users", json={"email": "dup@example.com", "password": "pass1"})
    response = client.post("/api/users", json={"email": "dup@example.com", "password": "pass2"})
    assert response.status_code == 409
    assert "already registered" in response.json()["detail"]


def test_get_user(client):
    created = client.post("/api/users", json={"email": "get@example.com", "password": "pass"})
    user_id = created.json()["id"]

    response = client.get(f"/api/users/{user_id}")
    assert response.status_code == 200
    assert response.json()["email"] == "get@example.com"


def test_get_user_not_found(client):
    response = client.get("/api/users/999999")
    assert response.status_code == 404
    assert response.json()["detail"] == "User not found"

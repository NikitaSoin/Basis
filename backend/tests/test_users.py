"""Профиль пользователя: создание и доступ ТОЛЬКО к своему.

🔴 Юр-аудит 2026-09-06: до этой правки `GET /api/users/{id}` отдавал чужую почту
вообще без токена, и прежняя версия этого файла закрепляла такое поведение как
ожидаемое. Тесты ниже фиксируют обратное: без токена — 401, к чужому профилю —
403, свой профиль доступен и по id, и через /users/me.
"""


def _register(client, email, password="secret123"):
    r = client.post("/api/auth/register", json={"email": email, "password": password})
    assert r.status_code == 201, r.text
    body = r.json()
    return body["user"]["id"], {"Authorization": f"Bearer {body['access_token']}"}


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


def test_get_own_profile(client):
    user_id, headers = _register(client, "own@example.com")
    response = client.get(f"/api/users/{user_id}", headers=headers)
    assert response.status_code == 200
    assert response.json()["email"] == "own@example.com"


def test_get_me(client):
    _, headers = _register(client, "me@example.com")
    response = client.get("/api/users/me", headers=headers)
    assert response.status_code == 200
    assert response.json()["email"] == "me@example.com"
    assert "hashed_password" not in response.json()


def test_get_user_requires_token(client):
    """Без токена почта не отдаётся — та самая закрытая дыра."""
    user_id, _ = _register(client, "victim@example.com")
    response = client.get(f"/api/users/{user_id}")
    assert response.status_code in (401, 403)
    assert "victim@example.com" not in response.text


def test_get_foreign_profile_forbidden(client):
    """Перебор чужих id больше не работает даже с валидным токеном."""
    victim_id, _ = _register(client, "victim2@example.com")
    _, attacker_headers = _register(client, "attacker@example.com")
    response = client.get(f"/api/users/{victim_id}", headers=attacker_headers)
    assert response.status_code == 403
    assert "victim2@example.com" not in response.text


def test_get_user_not_found(client):
    """Несуществующий id — 404 только для владельца токена; чужой id — 403."""
    _, headers = _register(client, "nf@example.com")
    response = client.get("/api/users/999999", headers=headers)
    assert response.status_code == 403

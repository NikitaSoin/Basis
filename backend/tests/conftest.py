import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from dotenv import load_dotenv
import os

load_dotenv()

from app.main import app
from app.db.session import Base, get_db

engine = create_engine(os.getenv("TEST_DATABASE_URL"))
TestingSessionLocal = sessionmaker(bind=engine)


@pytest.fixture(scope="session", autouse=True)
def setup_database():
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)
    yield
    Base.metadata.drop_all(bind=engine)


@pytest.fixture()
def db(setup_database):
    session = TestingSessionLocal()
    try:
        yield session
    finally:
        session.rollback()
        session.close()


@pytest.fixture()
def client(db):
    def override_get_db():
        yield db

    app.dependency_overrides[get_db] = override_get_db
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()

# ── Фикстуры доступа ────────────────────────────────────────────────────────────
# Тесты писались до двух изменений и с июля 2026 падали именно из-за них:
#   * аудит 2026-07-26 закрыл ручки ЗАПИСИ контента ops-токеном (X-Debug-Token);
#   * с 2026-08-04 портфели требуют либо вход, либо гостевой токен.
# Красная сюита хуже отсутствующей: в ней не видно настоящей поломки. Поэтому
# тесты приведены к реальному контракту, а не контракт ослаблен ради тестов.


@pytest.fixture()
def ops_client(client):
    """Клиент со служебным токеном — для ручек записи контента (создание компаний,
    котировок, разборов). Без токена они отвечают 403, и это правильно."""
    token = (os.getenv("DEBUG_API_TOKEN") or "").strip()
    if token:
        client.headers.update({"X-Debug-Token": token})
    return client


@pytest.fixture()
def user_client(client):
    """Клиент от имени зарегистрированного пользователя: возвращает (client, user_id).
    Портфели без входа недоступны, поэтому регистрируем настоящего человека."""
    import uuid
    email = f"t-{uuid.uuid4().hex[:10]}@example.com"
    r = client.post("/api/auth/register", json={"email": email, "password": "secret123"})
    assert r.status_code == 201, r.text
    body = r.json()
    client.headers.update({"Authorization": f"Bearer {body['access_token']}"})
    return client, body["user"]["id"]

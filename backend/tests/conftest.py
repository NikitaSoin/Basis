import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from dotenv import load_dotenv
import os
import pathlib

load_dotenv()

from app.main import app
from app.db.session import Base, get_db

engine = create_engine(os.getenv("TEST_DATABASE_URL"))
TestingSessionLocal = sessionmaker(bind=engine)


@pytest.fixture(scope="session", autouse=True)
def setup_database():
    """Тестовая схема строится МИГРАЦИЯМИ, а не `create_all`.

    🔴 Почему так (07.09.2026). Часть таблиц живёт только в миграциях и ORM-модели не
    имеет: `market_params`, `user_events`, `verification_codes`. На схеме, собранной
    через `create_all`, их просто не было, и тесты падали с `UndefinedTable` — не
    потому что код сломан, а потому что тестовая база не равна боевой. Заодно это
    проверяет сами миграции: если цепочка не применяется, сюита падает сразу и громко,
    а не через месяц на выкатке.

    Схема сносится целиком (`DROP SCHEMA`), потому что `Base.metadata.drop_all` не знает
    про таблицы без моделей и оставлял бы их от прошлого прогона.
    """
    url = os.getenv("TEST_DATABASE_URL") or ""
    # Предохранитель: тут выполняется DROP SCHEMA. Ошибиться переменной окружения —
    # значит снести рабочую базу. Имя обязано содержать «test».
    if "test" not in url.rsplit("/", 1)[-1].lower():
        raise RuntimeError(
            "TEST_DATABASE_URL должна указывать на отдельную тестовую базу "
            f"(в имени ожидается «test»), получено: {url.rsplit('/', 1)[-1] or '—'}")

    with engine.begin() as conn:
        conn.exec_driver_sql("DROP SCHEMA public CASCADE")
        conn.exec_driver_sql("CREATE SCHEMA public")

    # env.py читает адрес из DATABASE_URL, поэтому подменяем его на время миграций.
    prev = os.environ.get("DATABASE_URL")
    os.environ["DATABASE_URL"] = url
    try:
        from alembic import command
        from alembic.config import Config
        cfg = Config(str(pathlib.Path(__file__).resolve().parents[1] / "alembic.ini"))
        command.upgrade(cfg, "head")
    finally:
        if prev is None:
            os.environ.pop("DATABASE_URL", None)
        else:
            os.environ["DATABASE_URL"] = prev
    yield


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

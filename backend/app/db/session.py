from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, DeclarativeBase
from dotenv import load_dotenv
import os

load_dotenv()

DATABASE_URL = os.getenv("DATABASE_URL")

# Timeweb и большинство облачных PostgreSQL требуют SSL.
# Если в URL нет sslmode — добавляем require для не-localhost соединений.
_is_remote = bool(DATABASE_URL) and "localhost" not in DATABASE_URL and "127.0.0.1" not in DATABASE_URL
_connect_args = {}
if _is_remote:
    if "sslmode" not in DATABASE_URL:
        _connect_args["sslmode"] = "require"
    # КЛЮЧЕВОЕ для УДАЛЁННОЙ managed-БД (Timeweb): не висеть бесконечно на коннекте.
    # Без connect_timeout сетевой сбой/медленный коннект к managed-PG подвешивает
    # запрос НАВСЕГДА → на сайте «загружаем…» без ответа. 10с — fail-fast.
    _connect_args["connect_timeout"] = 10
    # TCP keepalive — managed-PG за балансировщиком/NAT молча рвёт простаивающие
    # соединения; keepalive не даёт пулу копить «мёртвые» сокеты.
    _connect_args["keepalives"] = 1
    _connect_args["keepalives_idle"] = 30
    _connect_args["keepalives_interval"] = 10
    _connect_args["keepalives_count"] = 5

# pool_pre_ping — проверять живость соединения (SELECT 1) ПЕРЕД выдачей из пула:
#   именно это лечит «работало, потом зависло» на managed-PG, которая дропает idle.
# pool_recycle=280с — не переиспользовать соединения старше ~4.5 мин (короче типичного
#   idle-timeout managed-PG). pool_timeout=10 — не ждать вечно свободное соединение пула,
#   если фоновые задачи временно его исчерпали → запрос быстро падает, а не висит.
engine = create_engine(
    DATABASE_URL,
    connect_args=_connect_args,
    pool_pre_ping=True,
    pool_recycle=280,
    pool_timeout=10,
    pool_size=5,
    max_overflow=10,
)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


class Base(DeclarativeBase):
    pass


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

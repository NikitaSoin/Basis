from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, DeclarativeBase
from dotenv import load_dotenv
import os

load_dotenv()

DATABASE_URL = os.getenv("DATABASE_URL")

# Timeweb и большинство облачных PostgreSQL требуют SSL.
# Если в URL нет sslmode — добавляем require для не-localhost соединений.
_connect_args = {}
if DATABASE_URL and "localhost" not in DATABASE_URL and "127.0.0.1" not in DATABASE_URL:
    if "sslmode" not in DATABASE_URL:
        _connect_args = {"sslmode": "require"}

engine = create_engine(DATABASE_URL, connect_args=_connect_args)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


class Base(DeclarativeBase):
    pass


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

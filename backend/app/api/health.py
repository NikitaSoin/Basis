from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from sqlalchemy import text
from app.db.session import get_db, engine
import os

router = APIRouter()


@router.get("/health")
def health_check():
    return {"status": "ok"}


@router.get("/health/db")
def health_db():
    try:
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        return {"status": "ok", "database": "connected"}
    except Exception as e:
        db_url = os.getenv("DATABASE_URL", "not set")
        safe_url = db_url.split("@")[-1] if "@" in db_url else db_url
        return {"status": "error", "detail": str(e), "db_host": safe_url}

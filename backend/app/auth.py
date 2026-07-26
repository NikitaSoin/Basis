import os
import bcrypt
from datetime import datetime, timedelta, timezone
from jose import JWTError, jwt
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from sqlalchemy.orm import Session
from app.db.session import get_db
from app.models.user import User

SECRET_KEY = os.environ.get("JWT_SECRET_KEY", "changeme-use-env-in-production")
if SECRET_KEY == "changeme-use-env-in-production":
    # 🔴 Аудит 2026-07-26: с дефолтным секретом ЛЮБОЙ может подделать JWT и
    # войти под любым пользователем. Не роняем прод (вдруг это как раз бой без
    # переменной — падение хуже), но кричим в лог на каждом старте. Действие
    # владельца: задать JWT_SECRET_KEY в панели Timeweb (случайные 64+ символа).
    import logging as _logging
    _logging.getLogger(__name__).critical(
        "🔓 JWT_SECRET_KEY НЕ ЗАДАН — используется публичный дефолт, токены "
        "подделываемы. Задайте JWT_SECRET_KEY в окружении НЕМЕДЛЕННО.")
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_DAYS = 30

_bearer = HTTPBearer(auto_error=False)


def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()


def verify_password(plain: str, hashed: str) -> bool:
    return bcrypt.checkpw(plain.encode(), hashed.encode())


def create_access_token(user_id: int) -> str:
    expire = datetime.now(timezone.utc) + timedelta(days=ACCESS_TOKEN_EXPIRE_DAYS)
    return jwt.encode({"sub": str(user_id), "exp": expire}, SECRET_KEY, algorithm=ALGORITHM)


def _decode_token(token: str) -> int | None:
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        sub = payload.get("sub")
        return int(sub) if sub else None
    except (JWTError, ValueError):
        return None


def get_current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(_bearer),
    db: Session = Depends(get_db),
) -> User:
    if not credentials:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Не авторизован")
    user_id = _decode_token(credentials.credentials)
    if not user_id:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Невалидный токен")
    user = db.get(User, user_id)
    if not user or not user.is_active:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Пользователь не найден")
    return user


def get_current_user_optional(
    credentials: HTTPAuthorizationCredentials | None = Depends(_bearer),
    db: Session = Depends(get_db),
) -> User | None:
    if not credentials:
        return None
    user_id = _decode_token(credentials.credentials)
    if not user_id:
        return None
    return db.get(User, user_id)

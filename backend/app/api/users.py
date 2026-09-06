from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from app.auth import get_current_user
from app.db.session import get_db
from app.models.user import User
from app.schemas.user import UserCreate, UserResponse
from app.services.user import create_user, get_user_by_id, get_user_by_email

router = APIRouter()


@router.post("/users", response_model=UserResponse, status_code=status.HTTP_201_CREATED)
def create_user_endpoint(data: UserCreate, db: Session = Depends(get_db)):
    if get_user_by_email(db, data.email):
        raise HTTPException(status_code=409, detail="Email already registered")
    return create_user(db, data)


# 🔴 /users/me объявлен ДО /users/{user_id}: иначе FastAPI попытается разобрать
# "me" как int и вернёт 422 вместо профиля.
@router.get("/users/me", response_model=UserResponse)
def get_me(current_user: User = Depends(get_current_user)):
    """Свой профиль по токену. Нужен, чтобы фронту не приходилось держать копию
    профиля (с почтой) в локальном хранилище браузера."""
    return current_user


@router.get("/users/{user_id}", response_model=UserResponse)
def get_user_endpoint(user_id: int, current_user: User = Depends(get_current_user),
                      db: Session = Depends(get_db)):
    """🔴 Юр-аудит 2026-09-06: ручка отдавала ЧУЖУЮ почту вообще без авторизации —
    перебором id извлекалась вся база адресов. Теперь нужен токен, и отдаётся
    только собственный профиль. Фронтенд эту ручку не вызывает (проверено
    грепом по src/), поэтому закрытие ничего не ломает."""
    if user_id != current_user.id:
        raise HTTPException(status_code=403, detail="Доступен только собственный профиль")
    user = get_user_by_id(db, user_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    return user

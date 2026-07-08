from datetime import datetime, timedelta, timezone
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from app.db.session import get_db
from app.schemas.user import UserCreate, UserLogin, UserResponse, TokenResponse, SubscriptionChangeRequest
from app.services.user import create_user, get_user_by_email, authenticate_user
from app.auth import create_access_token, get_current_user
from app.models.user import User, SubscriptionType

router = APIRouter(prefix="/auth")


@router.post("/register", response_model=TokenResponse, status_code=status.HTTP_201_CREATED)
def register(data: UserCreate, db: Session = Depends(get_db)):
    if get_user_by_email(db, data.email):
        raise HTTPException(status_code=409, detail="Email уже зарегистрирован")
    user = create_user(db, data)
    token = create_access_token(user.id)
    return TokenResponse(access_token=token, user=user)


@router.post("/login", response_model=TokenResponse)
def login(data: UserLogin, db: Session = Depends(get_db)):
    user = authenticate_user(db, data.email, data.password)
    if not user:
        raise HTTPException(status_code=401, detail="Неверный email или пароль")
    if not user.is_active:
        raise HTTPException(status_code=403, detail="Аккаунт заблокирован")
    token = create_access_token(user.id)
    return TokenResponse(access_token=token, user=user)


@router.get("/me", response_model=UserResponse)
def me(current_user: User = Depends(get_current_user)):
    return current_user


@router.post("/logout")
def logout():
    # JWT stateless — клиент просто удаляет токен
    return {"message": "Вышли из системы"}


@router.post("/me/subscription", response_model=UserResponse)
def change_subscription(
    data: SubscriptionChangeRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Смена тарифа БЕЗ оплаты — платёжного шлюза ещё нет (см. CLAUDE.md/status.md),
    это демо-переключатель, чтобы видеть, как тариф выглядит и что открывает.
    Разово подставляем 30 дней «активности» для платных тарифов — как только
    появится реальный биллинг, дату продления будет проставлять он."""
    current_user.subscription_type = data.tier
    current_user.subscription_expires_at = (
        datetime.now(timezone.utc) + timedelta(days=30)
        if data.tier != SubscriptionType.free
        else None
    )
    db.commit()
    db.refresh(current_user)
    return current_user

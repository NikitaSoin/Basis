from datetime import datetime, timedelta, timezone
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from app.db.session import get_db
from app.schemas.user import UserCreate, UserLogin, UserResponse, TokenResponse, SubscriptionChangeRequest
from app.services.user import create_user, get_user_by_email, authenticate_user
from app.auth import create_access_token, get_current_user
from app.models.user import User, SubscriptionType

router = APIRouter(prefix="/auth")


@router.post("/register/request-code")
def register_request_code(data: dict, db: Session = Depends(get_db)):
    """УСТАРЕЛО (2026-08-06): подтверждение переведено с кода на ССЫЛКУ после
    регистрации (владелец: «чтобы клиент мог в любое удобное время подтвердить»).
    Возвращаем "disabled" всегда — старый фронт при этом ответе регистрирует
    без кода, то есть ведёт себя ровно как новый флоу."""
    return {"status": "disabled"}


@router.post("/register", response_model=TokenResponse, status_code=status.HTTP_201_CREATED)
def register(data: UserCreate, db: Session = Depends(get_db)):
    """Регистрация НЕ блокируется подтверждением: аккаунт создаётся сразу,
    письмо со ссылкой подтверждения уходит следом (если SMTP настроен).
    Сбой отправки не мешает регистрации — повторить можно из профиля."""
    if get_user_by_email(db, data.email):
        raise HTTPException(status_code=409, detail="Email уже зарегистрирован")
    user = create_user(db, data)
    try:
        from app.services.email_verify import send_verification_link
        send_verification_link(db, user, enforce_limit=False)
    except Exception:  # noqa: BLE001 — письмо не должно ронять регистрацию
        import logging
        logging.getLogger(__name__).warning(
            "register: письмо подтверждения на %s не отправилось", user.email, exc_info=True)
    token = create_access_token(user.id)
    return TokenResponse(access_token=token, user=user)


@router.post("/verify-email")
def verify_email(data: dict, db: Session = Depends(get_db)):
    """Подтверждение почты по токену из письма (ссылка ведёт на фронт,
    фронт вызывает этот эндпоинт). Идемпотентно, авторизация не нужна —
    токен подписан и сам удостоверяет владение адресом."""
    from app.services.email_verify import apply_verify_token
    token = (data.get("token") or "").strip()
    if not token:
        raise HTTPException(status_code=422, detail="Нет токена подтверждения")
    try:
        return apply_verify_token(db, token)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/send-verification")
def send_verification(current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """Повторная отправка письма со ссылкой — из профиля. 429 на кулдауне."""
    from app.services.email_verify import send_verification_link
    try:
        return send_verification_link(db, current_user)
    except ValueError as e:
        raise HTTPException(status_code=429, detail=str(e))


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

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy.orm import Session
from app.db.session import get_db
from app.schemas.portfolio import (
    PortfolioCreate, PortfolioDividendsResponse, PortfolioMetricsResponse, PortfolioResponse,
    PositionCreate, PositionResponse, PositionUpdate, TradeCreate, TradeResponse,
)
from app.services.portfolio import (
    get_portfolios_by_user, get_portfolio_by_id,
    create_portfolio, add_position, delete_position, update_position,
    compute_portfolio_metrics, compute_factor_profile, compute_custom_stress,
    compute_portfolio_stress_v2,
    record_trade, compute_position_pnl, compute_portfolio_dividends,
)
from app.services.portfolio_diagnosis import generate_diagnosis
from app.auth import get_current_user, get_current_user_optional
from app.models.user import User, SubscriptionType
from app.models.portfolio import Portfolio

# Подписок/оплаты на платформе пока нет (тарифы — витрина), лимит в 5 позиций
# блокировал реальное использование (баг «6-я позиция не добавляется»).
# Технический потолок оставлен; вернуть продуктовый лимит — при запуске тарифов.
FREE_POSITION_LIMIT = 50

# ── ГОСТЕВОЙ ДОСТУП ────────────────────────────────────────────────────────────────
# Владелец 2026-08-04: «у аналитики портфеля не надо регистрироваться базово — клиент
# может зайти и потыкаться». Гость собирает состав и видит ТУ ЖЕ аналитику, что и
# зарегистрированный: считает её один и тот же код по portfolio_id, второй реализации
# расчётного слоя не заводим (см. миграцию a1f4c7e93b28).
#
# Токен генерирует браузер и хранит у себя. Сервер по нему только находит портфель:
# ни почты, ни имени, ни IP с ним не связывается.
GUEST_TOKEN_HEADER = "X-Guest-Token"
# Гостю — один портфель и меньше позиций: это витрина, а не рабочее место. Заодно
# ограничивает объём мусора, который может нагенерировать обход роботами.
GUEST_PORTFOLIO_LIMIT = 1
GUEST_POSITION_LIMIT = 20

router = APIRouter()


def _guest_token(request: Request) -> str | None:
    """Токен гостя из заголовка. Пустые и мусорные значения не принимаем: короткий или
    чересчур длинный токен — почти наверняка ошибка клиента, а не реальный гость."""
    raw = (request.headers.get(GUEST_TOKEN_HEADER) or "").strip()
    return raw if 16 <= len(raw) <= 64 and raw.isalnum() else None


def resolve_portfolio(db: Session, portfolio_id: int, user: User | None, guest: str | None):
    """Единая проверка доступа: хозяин ИЛИ гость с тем же токеном.

    🔴 Порядок проверок важен. Сначала владелец, и только потом гость — иначе портфель,
    уже привязанный к пользователю, остался бы доступен по старому гостевому токену,
    который мог сохраниться в чужом браузере (например, на общем компьютере).
    """
    portfolio = get_portfolio_by_id(db, portfolio_id)
    if not portfolio:
        raise HTTPException(status_code=404, detail="Портфель не найден")
    if user is not None and portfolio.user_id == user.id:
        return portfolio
    if portfolio.user_id is None and guest and portfolio.guest_token == guest:
        portfolio.guest_seen_at = datetime.now(timezone.utc)
        db.commit()
        return portfolio
    raise HTTPException(status_code=403, detail="Нет доступа")


@router.post("/portfolios", response_model=PortfolioResponse, status_code=status.HTTP_201_CREATED)
def create_portfolio_endpoint(
    data: PortfolioCreate,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User | None = Depends(get_current_user_optional),
):
    if current_user is not None:
        data.user_id = current_user.id
        return create_portfolio(db, data)
    guest = _guest_token(request)
    if not guest:
        raise HTTPException(status_code=401, detail="Нужен вход или гостевой токен")
    existing = db.query(Portfolio).filter(
        Portfolio.guest_token == guest, Portfolio.user_id.is_(None)
    ).all()
    if len(existing) >= GUEST_PORTFOLIO_LIMIT:
        # Гостю хватает одного портфеля: повторный вызов отдаёт тот же, а не плодит
        # новые. Иначе перезагрузка страницы оставляла бы за собой мусор в БД.
        return existing[0]
    data.user_id = None
    portfolio = create_portfolio(db, data)
    portfolio.guest_token = guest
    portfolio.guest_seen_at = datetime.now(timezone.utc)
    db.commit()
    db.refresh(portfolio)
    return portfolio


@router.get("/portfolios", response_model=list[PortfolioResponse])
def list_portfolios_endpoint(
    request: Request,
    db: Session = Depends(get_db),
    current_user: User | None = Depends(get_current_user_optional),
):
    if current_user is not None:
        return get_portfolios_by_user(db, current_user.id)
    guest = _guest_token(request)
    if not guest:
        return []
    return db.query(Portfolio).filter(
        Portfolio.guest_token == guest, Portfolio.user_id.is_(None)
    ).all()


@router.get("/portfolios/{portfolio_id}", response_model=PortfolioResponse)
def get_portfolio_endpoint(
    portfolio_id: int,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User | None = Depends(get_current_user_optional),
):
    portfolio = resolve_portfolio(db, portfolio_id, current_user, _guest_token(request))
    return portfolio


@router.post("/portfolios/{portfolio_id}/positions", response_model=PositionResponse, status_code=status.HTTP_201_CREATED)
def add_position_endpoint(
    portfolio_id: int,
    data: PositionCreate,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User | None = Depends(get_current_user_optional),
):
    portfolio = resolve_portfolio(db, portfolio_id, current_user, _guest_token(request))

    if current_user is None:
        # Гость: портфель — витрина, не рабочее место. Лимит ниже, и текст объясняет,
        # что снимает ограничение, а не просто отказывает.
        if len(portfolio.positions) >= GUEST_POSITION_LIMIT:
            raise HTTPException(
                status_code=403,
                detail=(f"Без регистрации — до {GUEST_POSITION_LIMIT} позиций. "
                        f"Зарегистрируйтесь, чтобы сохранить портфель и добавлять дальше."),
            )
    elif current_user.subscription_type == SubscriptionType.free:
        if len(portfolio.positions) >= FREE_POSITION_LIMIT:
            raise HTTPException(
                status_code=403,
                detail=f"Бесплатный тариф: максимум {FREE_POSITION_LIMIT} позиций. Перейдите на Max.",
            )

    return add_position(db, portfolio_id, data)


@router.patch("/portfolios/{portfolio_id}/positions/{position_id}", response_model=PositionResponse)
def update_position_endpoint(
    portfolio_id: int,
    position_id: int,
    data: PositionUpdate,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User | None = Depends(get_current_user_optional),
):
    """Прямое редактирование позиции: количество и/или средняя цена покупки."""
    portfolio = resolve_portfolio(db, portfolio_id, current_user, _guest_token(request))
    position = update_position(
        db, portfolio_id, position_id,
        quantity=data.quantity, avg_buy_price=data.avg_buy_price,
    )
    if not position:
        raise HTTPException(status_code=404, detail="Позиция не найдена")
    return position


@router.post("/portfolios/{portfolio_id}/positions/{position_id}/trades", response_model=PositionResponse, status_code=status.HTTP_201_CREATED)
def record_trade_endpoint(
    portfolio_id: int,
    position_id: int,
    data: TradeCreate,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User | None = Depends(get_current_user_optional),
):
    """Совершить сделку (не исправление) — заводит запись в истории и
    пересчитывает qty/среднюю по методу средневзвешенной цены."""
    portfolio = resolve_portfolio(db, portfolio_id, current_user, _guest_token(request))
    try:
        position = record_trade(db, portfolio_id, position_id, data)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    if not position:
        raise HTTPException(status_code=404, detail="Позиция не найдена")
    return position


@router.get("/portfolios/{portfolio_id}/positions/{position_id}/pnl")
def position_pnl_endpoint(
    portfolio_id: int,
    position_id: int,
    request: Request,
    current_price: float | None = None,
    db: Session = Depends(get_db),
    current_user: User | None = Depends(get_current_user_optional),
):
    """Реализовано / не реализовано / дивиденды получено / комиссии уплачено —
    из истории сделок позиции (см. compute_position_pnl)."""
    portfolio = resolve_portfolio(db, portfolio_id, current_user, _guest_token(request))
    result = compute_position_pnl(db, portfolio_id, position_id, current_price)
    if result is None:
        raise HTTPException(status_code=404, detail="Позиция не найдена или нет истории сделок")
    return result


_COMPARE_PERIODS = ("1m", "3m", "6m", "1y", "3y", "max")


@router.get("/portfolios/{portfolio_id}/metrics", response_model=PortfolioMetricsResponse)
def portfolio_metrics_endpoint(
    portfolio_id: int,
    request: Request,
    period: str = "3y",
    db: Session = Depends(get_db),
    current_user: User | None = Depends(get_current_user_optional),
):
    """Лёгкие аналитические метрики портфеля (Этап 1): P/E и дивдоходность
    позиций из company_metrics, средневзвешенные по портфелю, распределение
    по секторам/классам активов, концентрация.

    period — окно ТОЛЬКО для графика «Сравнение» (1m/3m/6m/1y/3y/max — max=3y,
    данные глубже 3 лет не хранятся в этом расчёте); волатильность/бета/VaR и
    прочие риск-метрики считаются на фиксированном 3-летнем окне независимо от
    выбора, см. compute_portfolio_metrics."""
    if period not in _COMPARE_PERIODS:
        raise HTTPException(status_code=422, detail=f"period должен быть одним из {_COMPARE_PERIODS}")
    portfolio = resolve_portfolio(db, portfolio_id, current_user, _guest_token(request))
    return compute_portfolio_metrics(db, portfolio_id, compare_period=period)


@router.get("/portfolios/{portfolio_id}/dividends", response_model=PortfolioDividendsResponse)
def portfolio_dividends_endpoint(
    portfolio_id: int,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User | None = Depends(get_current_user_optional),
):
    """Дивиденды по позициям портфеля — три сегмента по датам: upcoming
    (отсечка впереди) / pending (отсечка прошла, оценка окна зачисления) /
    history (окно прошло). См. compute_portfolio_dividends."""
    portfolio = resolve_portfolio(db, portfolio_id, current_user, _guest_token(request))
    return compute_portfolio_dividends(db, portfolio_id)


@router.get("/portfolios/{portfolio_id}/factor-profile")
def portfolio_factor_profile_endpoint(
    portfolio_id: int,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User | None = Depends(get_current_user_optional),
):
    """Взвешенная чувствительность портфеля к ставке ЦБ (вкладка «ИИ-Диагноз»),
    из quant_inputs.coefficients в companies/<TICKER>/macro.json. Возвращает
    null, если ни одна позиция не покрыта макро-данными (честная деградация)."""
    portfolio = resolve_portfolio(db, portfolio_id, current_user, _guest_token(request))
    return compute_factor_profile(db, portfolio_id)


@router.get("/portfolios/{portfolio_id}/stress-test")
def portfolio_custom_stress_endpoint(
    portfolio_id: int,
    request: Request,
    rate_shock_bp: float = 0.0,
    index_shock_pct: float = 0.0,
    fx_shock_pct: float = 0.0,
    db: Session = Depends(get_db),
    current_user: User | None = Depends(get_current_user_optional),
):
    """Свой сценарий стресс-теста («Стресс-тест» → «+ Свой сценарий»): просадка
    по позиции = бета×индексный шок + ставочный канал из macro.json (где
    покрыто). Курс рубля пока НЕ применяется к расчёту (fx_applied=false)."""
    portfolio = resolve_portfolio(db, portfolio_id, current_user, _guest_token(request))
    result = compute_custom_stress(db, portfolio_id, rate_shock_bp, index_shock_pct, fx_shock_pct)
    if result is None:
        raise HTTPException(status_code=404, detail="Недостаточно данных для расчёта")
    return result


@router.get("/portfolios/{portfolio_id}/stress-test-v2")
def portfolio_stress_v2_endpoint(
    portfolio_id: int,
    request: Request,
    key_rate_pct: float | None = None,
    fx_usdrub: float | None = None,
    oil_brent_usd: float | None = None,
    db: Session = Depends(get_db),
    current_user: User | None = Depends(get_current_user_optional),
):
    """Стресс-тест портфеля — единый движок с общерыночным «Стресс-тестированием»
    (см. compute_portfolio_stress_v2): те же коэффициенты чувствительности, что
    в /api/stress-test/*, взвешено по РЕАЛЬНЫМ позициям портфеля. Параметры —
    АБСОЛЮТНЫЕ целевые уровни (не сдвиг/шок), те же имена, что у
    /api/stress-test/numeric и /current-levels — единообразие с общерыночным
    блоком."""
    portfolio = resolve_portfolio(db, portfolio_id, current_user, _guest_token(request))
    result = compute_portfolio_stress_v2(db, portfolio_id, key_rate_pct, fx_usdrub, oil_brent_usd)
    if result is None:
        raise HTTPException(status_code=404, detail="Недостаточно данных для расчёта")
    return result


def _serialize_diagnosis(diag) -> dict:
    return {
        "shield": diag.shield or [],
        "vulnerabilities": diag.vulnerabilities or [],
        "summary": {"text": diag.summary, "type": diag.summary_type} if diag.summary else None,
        "portfolio_snapshot": diag.portfolio_snapshot or [],
        "generated_at": diag.generated_at.isoformat() if diag.generated_at else None,
    }


@router.get("/portfolios/{portfolio_id}/diagnosis")
def portfolio_diagnosis_endpoint(
    portfolio_id: int,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User | None = Depends(get_current_user_optional),
):
    """Кэшированный ИИ-Диагноз портфеля (вкладка «ИИ-Диагноз»). null, если ещё
    ни разу не сгенерирован — фронт предлагает нажать «Обновить диагноз»."""
    portfolio = resolve_portfolio(db, portfolio_id, current_user, _guest_token(request))
    from app.models.portfolio_diagnosis import PortfolioDiagnosis
    diag = db.query(PortfolioDiagnosis).filter_by(portfolio_id=portfolio_id).first()
    return _serialize_diagnosis(diag) if diag else None


@router.post("/portfolios/{portfolio_id}/diagnosis/refresh")
def portfolio_diagnosis_refresh_endpoint(
    portfolio_id: int,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User | None = Depends(get_current_user_optional),
):
    """Перегенерировать ИИ-Диагноз (LLM-вызов — по кнопке, не на каждый рендер)."""
    portfolio = resolve_portfolio(db, portfolio_id, current_user, _guest_token(request))
    try:
        diag = generate_diagnosis(db, portfolio_id)
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"Не удалось сгенерировать диагноз: {e}")
    if diag is None:
        raise HTTPException(status_code=404, detail="Недостаточно данных портфеля для диагноза")
    return _serialize_diagnosis(diag)


@router.delete("/portfolios/{portfolio_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_portfolio_endpoint(
    portfolio_id: int,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User | None = Depends(get_current_user_optional),
):
    portfolio = resolve_portfolio(db, portfolio_id, current_user, _guest_token(request))
    db.delete(portfolio)
    db.commit()


@router.delete("/portfolios/{portfolio_id}/positions/{position_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_position_endpoint(
    portfolio_id: int,
    position_id: int,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User | None = Depends(get_current_user_optional),
):
    resolve_portfolio(db, portfolio_id, current_user, _guest_token(request))
    if not delete_position(db, portfolio_id, position_id):
        raise HTTPException(status_code=404, detail="Позиция не найдена")


@router.post("/portfolios/claim", response_model=list[PortfolioResponse])
def claim_guest_portfolios(
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Перенести гостевой портфель на только что созданный аккаунт.

    Владелец 2026-08-04: «нужно, чтобы портфель, который был бы составлен, сохранился
    после того как клиент пройдёт регистрацию, чтобы не слетело». Фронт вызывает это
    сразу после успешной регистрации или входа, передавая тот же X-Guest-Token.

    🔴 Переносим, а не копируем: у портфеля меняется владелец, id остаётся прежним.
    Иначе пришлось бы копировать позиции и сделки, а ссылки на старый portfolio_id
    (открытая вкладка, кэш диагноза) указывали бы на осиротевшую запись.

    🔴 Токен обнуляем. Без этого портфель остался бы доступен любому, у кого сохранился
    тот же гостевой токен, — например, на общем компьютере.
    """
    guest = _guest_token(request)
    if not guest:
        return []
    orphans = db.query(Portfolio).filter(
        Portfolio.guest_token == guest, Portfolio.user_id.is_(None)
    ).all()
    for p in orphans:
        p.user_id = current_user.id
        p.guest_token = None
        p.guest_seen_at = None
    if orphans:
        db.commit()
        for p in orphans:
            db.refresh(p)
    return orphans

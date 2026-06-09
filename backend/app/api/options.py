"""Эндпоинты класса активов «Опционы» (на фьючерсы).

Витрина урезана. Карточка отвечает на главный вопрос: «что будет с деньгами и
оправдан ли риск» — профиль убытка, разложение премии, тета-распад, IV, греки
человеческим языком. БЕЗ сигналов и «купить/продать».
"""
from datetime import date

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.db.session import get_db

router = APIRouter()


def _safe(s: str) -> str:
    return "".join(c for c in s if c.isalnum() or c in "-_")


def _row(r) -> dict:
    d = dict(r._mapping)
    for k, v in d.items():
        if isinstance(v, date):
            d[k] = v.isoformat()
        elif hasattr(v, "real") and not isinstance(v, (int, float, bool)):
            d[k] = float(v)
    d["type_label"] = "Колл (право купить)" if d.get("option_type") == "C" else "Пут (право продать)"
    if d.get("expiration_date"):
        d["days_to_expiry"] = (date.fromisoformat(d["expiration_date"]) - date.today()).days
    return d


@router.get("/options")
def list_options(db: Session = Depends(get_db)):
    """Список опционов (урезанная витрина), сгруппирован по базовому активу."""
    rows = [_row(r) for r in db.execute(text(
        "SELECT * FROM options ORDER BY asset_code, expiration_date, option_type, strike"))]
    return rows


@router.get("/options/{secid}")
def get_option(secid: str, db: Session = Depends(get_db)):
    """Карточка опциона: профиль выплаты + разложение премии + греки словами."""
    r = db.execute(text("SELECT * FROM options WHERE secid = :s"), {"s": _safe(secid)}).first()
    if not r:
        raise HTTPException(status_code=404, detail="Option not found")
    o = _row(r)
    is_call = o.get("option_type") == "C"
    prem = o.get("premium")
    F = o.get("underlying_price")

    # Профиль выплаты держателя (покупателя): макс. убыток = премия (100%),
    # потенциал прибыли = неограничен (call) / до страйка (put). Это ЛОГИКА.
    payoff = None
    if prem is not None:
        payoff = {
            "max_loss": prem,                 # покупатель теряет максимум премию
            "max_loss_note": "Максимум вы теряете всю премию (100% вложенного) — если опцион истечёт вне денег.",
            "breakeven": o.get("breakeven"),
            "upside": "неограничен (растёт вместе с базовым активом)" if is_call else "до нуля базового актива (ограничен страйком)",
            "seller_warning": "Продавец опциона получает премию, но его убыток теоретически НЕ ограничен (call) — это для профессионалов, требует ГО.",
            "certainty": "логика",
        }

    # Разложение премии + тета (почему дешевеет даже при правоте по направлению)
    decomposition = None
    if prem is not None:
        iv = o.get("iv"); theta = o.get("theta_day")
        decomposition = {
            "premium": prem, "intrinsic_value": o.get("intrinsic_value"), "time_value": o.get("time_value"),
            "theta_day": theta,
            "note": ("Премия = внутренняя стоимость (если опцион уже в деньгах) + временная стоимость («воздух»). "
                     + (f"Временная стоимость тает со скоростью ~{abs(theta):.0f} ₽ в день (тета) — "
                        "вы теряете её, даже если угадали направление, просто от хода времени." if theta else "")),
            "certainty": "логика (стоимости) / оценка (тета)",
        }

    # Греки человеческим языком (оценка по модели Блэк-76)
    greeks_plain = None
    if o.get("delta") is not None:
        delta = o["delta"]
        greeks_plain = {
            "delta": delta,
            "delta_note": f"Дельта {delta:+.2f}: при движении базового актива на 1 пункт цена опциона меняется примерно на {abs(delta):.2f}. Грубо — вероятность исполнения ~{abs(delta)*100:.0f}%.",
            "theta_note": (f"Тета: ~{o['theta_day']:.0f} ₽ в день — столько стоит «время» против покупателя." if o.get("theta_day") else None),
            "vega_note": (f"Вега: при росте волатильности на 1% премия меняется на ~{o['vega']:.0f} ₽ — можно угадать направление, но проиграть на падении волатильности." if o.get("vega") else None),
            "iv": o.get("iv"),
            "iv_note": (f"Подразумеваемая волатильность (IV) ~{o['iv']:.0f}%: чем выше IV, тем «дороже» опцион (выгоднее продавцу). Сравнивайте с историей актива." if o.get("iv") else None),
            "certainty": "оценка (модель Блэк-76)",
        }

    return {"option": o, "payoff": payoff, "decomposition": decomposition, "greeks": greeks_plain}

"""«Стресс-тестирование» — широкий сценарный блок (не путать с узким
портфельным расчётом внутри Портфеля, /api/portfolios/{id}/stress-test).
См. app/services/stress_scenarios.py — ДЕМО-ВЕРСИЯ, честно помечена."""
from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.db.session import get_db

router = APIRouter()


@router.get("/stress-test/scenarios")
def list_stress_scenarios():
    from app.services.stress_scenarios import list_scenarios
    return {"scenarios": list_scenarios()}


@router.get("/stress-test/current-levels")
def stress_test_current_levels(db: Session = Depends(get_db)):
    """Реальные текущие ориентиры (ставка/курс/нефть) — для стартовой позиции
    слайдеров на фронте (не хардкод, живые последние значения тех же источников,
    что уже используются в Обозревателе). Любое поле может быть null, если
    источник временно недоступен — фронт честно деградирует на приблизительный
    дефолт, не выдаёт null за число. Та же функция — источник Δ=0-при-старте в
    numeric_impact() (см. stress_numeric.py, 2026-07-25): держать ОДНУ реализацию,
    не дублировать запрос второй раз с риском разъехаться."""
    from app.services.stress_numeric import get_current_levels
    return get_current_levels(db)


@router.get("/stress-test/impact")
def stress_test_impact(
    scenario: str | None = Query(None, description="Ключ пресета сценария"),
    oil_usd: float | None = Query(None, description="Целевая цена нефти, $/барр. (свой сценарий)"),
    rub_usd: float | None = Query(None, description="Целевой курс USD/RUB (свой сценарий)"),
    db: Session = Depends(get_db),
):
    from app.services.stress_scenarios import build_scenario_result
    return build_scenario_result(db, scenario, oil_usd, rub_usd)


@router.get("/stress-test/coefficients")
def stress_test_coefficients(db: Session = Depends(get_db)):
    """Сырые коэффициенты чувствительности по всем компаниям — фронт грузит ОДИН
    раз при заходе на экран и дальше считает слайдерный путь сам, локально (см.
    docstring coefficients_payload) — устраняет debounce+round-trip задержку на
    каждое движение ползунка."""
    from app.services.stress_numeric import coefficients_payload
    return coefficients_payload(db)


@router.get("/stress-test/numeric")
def stress_test_numeric(
    key_rate_pct: float | None = Query(None, ge=0, le=50, description="Целевая ключевая ставка, %"),
    fx_usdrub: float | None = Query(None, ge=10, le=500, description="Целевой курс USD/RUB"),
    oil_brent_usd: float | None = Query(None, ge=5, le=500, description="Целевая цена Brent, $/барр."),
    db: Session = Depends(get_db),
):
    """Числовой контур v2: Δ выручки/EBITDA/чистой прибыли по каждой компании
    (млрд ₽ и % от базы года) при целевых макро-условиях — детерминированно, по
    коэффициентам чувствительности из макро-разбора карточки (macro_quant)."""
    from app.services.stress_numeric import numeric_impact
    if all(v is None for v in (key_rate_pct, fx_usdrub, oil_brent_usd)):
        return {"error": "no_inputs", "note": "Задайте хотя бы один параметр: ставка, курс или нефть."}
    return numeric_impact(db, key_rate_pct, fx_usdrub, oil_brent_usd)


@router.post("/stress-test/ask")
def stress_test_ask(payload: dict, db: Session = Depends(get_db)):
    """Свободный сценарий текстом («что будет если ...») → LLM-парсер (DeepSeek)
    переводит в вектор шоков → числа считает код (stress_numeric), направления —
    факторный движок. ДЕМО — интерпретация сценария возвращается явно."""
    from app.services.stress_ask import ask_scenario
    return ask_scenario(db, str(payload.get("question", "")))

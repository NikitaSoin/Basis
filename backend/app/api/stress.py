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


@router.get("/stress-test/impact")
def stress_test_impact(
    scenario: str | None = Query(None, description="Ключ пресета сценария"),
    oil_usd: float | None = Query(None, description="Целевая цена нефти, $/барр. (свой сценарий)"),
    rub_usd: float | None = Query(None, description="Целевой курс USD/RUB (свой сценарий)"),
    db: Session = Depends(get_db),
):
    from app.services.stress_scenarios import build_scenario_result
    return build_scenario_result(db, scenario, oil_usd, rub_usd)

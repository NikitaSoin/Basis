"""«Стресс-тестирование» (широкий блок, не путать с узким портфельным
бета×шок-расчётом внутри Портфеля) — владелец, 2026-07-17: «возможность +-
прикинуть, что произойдёт с компаниями/акциями/облигациями» под качественные
сценарии (война N лет, обвал/скачок нефти, налоговое давление, инфляционные
ожидания, оптимистичный сценарий ЦБ, смена собственника...) и числовые шоки
(нефть $X, курс ₽Y) — как это транслируется в компании и их показатели.

🔴 ЯВНО ДЕМО-ВЕРСИЯ (см. флаг is_demo в ответе + дисклеймер на фронте):
переиспользует РЕАЛЬНЫЙ движок «экспозиция → ценовой эффект» (methodology
§3.4, app/services/factor_engine.py) — тот же, что считает MGI (сценарную
устойчивость) индекса качества портфеля, — но:
  1) интенсивности сценариев ниже — продуктовый произвол (как и в
     config/quality_scenarios.json — та же оговорка), калиброваны на глаз,
     НЕ откалиброваны исторической регрессией;
  2) покрытие экспозиций НЕРАВНОМЕРНОЕ: rate/demand ~95-98% компаний,
     commodity/fx/sanctions/conflict — 10-35% (не все карточки тегировали эти
     факторы) — компания без тега по фактору просто не реагирует на НЕГО
     (не «подтверждённый ноль», а «нет данных»), см. coverage в ответе;
  3) НЕ моделирует идиосинкратические события ОДНОЙ компании (точечное
     повышение налога на конкретного эмитента, смена собственника конкретной
     компании) — движок работает на макро/гео-факторах, общих для вселенной,
     не на индивидуальных корпоративных событиях; общее «налоговое давление
     выросло» — да, «Газпрому подняли НДПИ» — нет, это требует отдельного
     разбора аналитика по конкретной бумаге;
  4) для облигаций — НЕ пересчитывает спред/цену бумаги, только показывает
     реакцию АКЦИИ эмитента (если публичный) как прокси-сигнал направления
     кредитного риска — облигация того же эмитента, вероятно, движется в ту
     же сторону, но не на ту же величину (другая природа риска).
"""
from __future__ import annotations

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.services.factor_engine import company_scenario_reaction
from app.services.factor_exposures import get_company_exposures, FACTOR_KEYS


# 🔴 Важное ограничение движка: фактор «commodity» в факторных картах компаний —
# ОБОБЩЁННЫЙ («цена ключевого сырья ЭТОЙ компании» — нефть у нефтяников, золото
# у Полюса, алюминий у Русала, уголь у угольщиков), а не именно нефть. Прямая
# проверка (2026-07-17): «обвал нефти» с global commodity:-1.0 давал Полюсу
# (золото) -17.8% и Русалу (алюминий) -19.9% — ложный сигнал, у этих металлов
# СВОЯ ценовая динамика, не следующая за нефтью. Нефтяные сценарии ограничены
# нефтегазовым сектором (sector_scope) — commodity-интенсивность применяется
# ТОЛЬКО к нему, у остальных сырьевых компаний по ЭТОМУ сценарию реакции по
# commodity-каналу не будет (честная деградация, не «подтверждённый ноль»).
_OIL_SECTOR_TOKENS = ("нефт", "газ", "oil", "gas")

SCENARIOS = [
    {
        "key": "war_prolonged", "label": "Война ещё 4 года",
        "description": "Затяжной конфликт без резкой эскалации, но и без разрешения — санкции продолжают накапливаться, бюджет под давлением военных расходов.",
        "intensities": {"conflict": 0.6, "sanctions": 0.5, "fiscal": 0.4, "fx": 0.3, "rate": 0.3},
    },
    {
        "key": "oil_crash", "label": "Обвал цены нефти",
        "description": "Нефть резко и надолго дешевеет (мировая рецессия/навес предложения) — бюджетные и экспортные доходы падают. Ценовой канал (commodity) применён только к нефтегазовому сектору — см. примечание о движке ниже.",
        "intensities": {"commodity": -1.0, "fx": 0.4, "demand": -0.3},
        "sector_scope": {"commodity": _OIL_SECTOR_TOKENS},
    },
    {
        "key": "middle_east_spike", "label": "Ближний Восток: нефть резко дорожает",
        "description": "Эскалация на Ближнем Востоке выбивает предложение с мирового рынка — нефть дорожает, глобальный риск растёт. Ценовой канал (commodity) применён только к нефтегазовому сектору.",
        "intensities": {"commodity": 0.9, "conflict": 0.2, "fx": -0.2},
        "sector_scope": {"commodity": _OIL_SECTOR_TOKENS},
    },
    {
        "key": "fiscal_pressure", "label": "Рост налогового/регуляторного давления",
        "description": "Государство расширяет изъятие прибыли бизнеса через налоги/пошлины (НДПИ, экспортные пошлины, разовые взносы) — ЭКОНОМИКА В ЦЕЛОМ, не точечно одна компания (точечное решение по одному эмитенту эта модель не считает).",
        "intensities": {"fiscal": 1.0},
    },
    {
        "key": "sticky_inflation", "label": "Инфляционные ожидания остаются повышенными",
        "description": "Инфляция не заякоривается — ЦБ вынужден держать ставку высокой дольше рыночного консенсуса.",
        "intensities": {"demand": -0.6, "rate": 0.6},
    },
    {
        "key": "cbr_optimistic", "label": "Оптимистичный сценарий Банка России",
        "description": "Инфляция быстро замедляется, ЦБ уверенно снижает ставку, геополитический фон не ухудшается.",
        "intensities": {"rate": -0.8, "demand": 0.4, "sanctions": -0.2},
    },
]

_REF_OIL_USD = None
_REF_RUB_USD = None


def _live_refs(db: Session) -> tuple[float | None, float | None]:
    oil = db.execute(text(
        "SELECT last_price FROM futures WHERE (asset_code ILIKE 'BR%' OR secid ILIKE 'BR%') "
        "AND last_price IS NOT NULL AND expiration_date >= now()::date "
        "ORDER BY expiration_date ASC LIMIT 1")).first()
    rub = db.execute(text("SELECT last_price FROM spot_assets WHERE secid='USD000UTSTOM'")).first()
    return (float(oil[0]) if oil and oil[0] else None), (float(rub[0]) if rub and rub[0] else None)


def _clip(v: float, lo: float = -1.3, hi: float = 1.3) -> float:
    return max(lo, min(hi, v))


def custom_intensities(db: Session, oil_usd: float | None, rub_usd: float | None) -> dict:
    """Числовой сценарий: целевые нефть $/барр. и курс ₽/$ → интенсивности
    commodity/fx линейным масштабированием от текущих ориентиров (простое
    приближение — реальная чувствительность нелинейна и секторо-зависима,
    честно не претендуем на точность за пределами направления и порядка
    величины)."""
    ref_oil, ref_rub = _live_refs(db)
    out: dict[str, float] = {}
    if oil_usd is not None and ref_oil:
        out["commodity"] = round(_clip((oil_usd - ref_oil) / ref_oil), 3)
    if rub_usd is not None and ref_rub:
        # выше ₽/$ = слабее рубль = "положительное" событие по конвенции fx
        # (типичный экспортёр Basis-вселенной имеет позитивную fx-экспозицию)
        out["fx"] = round(_clip((rub_usd - ref_rub) / ref_rub), 3)
    return out, ref_oil, ref_rub


def compute_impact(db: Session, intensities: dict, sector_scope: dict | None = None) -> dict:
    """Реакция ВСЕХ компаний с company_metrics (та же вселенная, что скринер)
    на заданный набор интенсивностей факторов. Честная деградация: компания
    без покрытых факторов из intensities получает reaction=0.0, coverage=0 —
    видно во фронте, не маскируется под «нейтральный сценарий».
    sector_scope: {factor_key: (sector_substring, ...)} — фактор применяется
    ТОЛЬКО к компаниям, чей sector содержит один из токенов (регистронезависимо);
    у остальных этот фактор перед расчётом обнуляется для ЭТОЙ компании (не
    глобально) — нужно, когда фактор в движке обобщённый (см. commodity)."""
    sector_scope = sector_scope or {}
    rows = db.execute(text("""
        SELECT c.ticker, c.name, c.sector FROM companies c
        JOIN company_metrics m ON m.ticker = c.ticker
    """)).fetchall()
    out = []
    for r in rows:
        ticker, name, sector = r[0], r[1], r[2]
        exp = dict(get_company_exposures(ticker))
        sector_l = (sector or "").lower()
        eff_intensities = dict(intensities)
        for factor, tokens in sector_scope.items():
            if factor not in eff_intensities:
                continue
            if not any(t in sector_l for t in tokens):
                del eff_intensities[factor]
            elif factor == "commodity":
                # 🔴 Найдено 2026-07-17: тегированный знак commodity-экспозиции
                # НЕНАДЁЖЕН — это "текущий эффект относительно нейтрального
                # уровня аналитика на момент написания карточки", не структурная
                # чувствительность. Проверено: LKOH/ROSN/SIBN — все -2 (карточки
                # писались при нефти НИЖЕ нейтрали), хотя структурно нефтяники
                # ОЧЕВИДНО выигрывают от роста цены нефти. Для нефтесценариев
                # (уже ограничены сектором «Нефть и газ» через sector_scope)
                # берём структурно верный знак напрямую, не из тега. Тот же
                # источник ошибки, вероятно, искажает MGI-субиндекс портфеля —
                # отдельная задача, не в этом фиксе (see docs/status.md).
                exp["commodity"] = 2.0
        covered = [k for k in eff_intensities if exp.get(k) is not None]
        reaction = company_scenario_reaction(exp, eff_intensities) if eff_intensities else 0.0
        out.append({
            "ticker": ticker, "name": name, "sector": sector,
            "reaction_pct": round(reaction * 100, 1),
            "factors_covered": covered, "coverage_n": len(covered), "coverage_total": len(intensities),
        })
    out.sort(key=lambda x: -x["reaction_pct"])
    covered_only = [x for x in out if x["coverage_n"] > 0]

    sector_agg: dict[str, list[float]] = {}
    for x in covered_only:
        if x["sector"]:
            sector_agg.setdefault(x["sector"], []).append(x["reaction_pct"])
    sectors = sorted(
        [{"sector": s, "avg_reaction_pct": round(sum(v) / len(v), 1), "n": len(v)} for s, v in sector_agg.items()],
        key=lambda x: -x["avg_reaction_pct"],
    )

    return {
        "winners": covered_only[:15],
        "losers": list(reversed(covered_only[-15:])) if len(covered_only) > 15 else [],
        "sectors": sectors,
        "total_companies": len(out),
        "companies_with_signal": len(covered_only),
    }


def list_scenarios() -> list[dict]:
    return [{"key": s["key"], "label": s["label"], "description": s["description"]} for s in SCENARIOS]


def build_scenario_result(db: Session, scenario_key: str | None, oil_usd: float | None, rub_usd: float | None) -> dict:
    if scenario_key:
        sc = next((s for s in SCENARIOS if s["key"] == scenario_key), None)
        if not sc:
            return {"error": "unknown_scenario"}
        result = compute_impact(db, sc["intensities"], sc.get("sector_scope"))
        result["scenario"] = {"key": sc["key"], "label": sc["label"], "description": sc["description"], "intensities": sc["intensities"]}
    else:
        intensities, ref_oil, ref_rub = custom_intensities(db, oil_usd, rub_usd)
        # свой сценарий тоже нефтяной шок по своей природе (commodity = нефть,
        # см. custom_intensities) — та же секторная оговорка, что у пресетов
        result = compute_impact(db, intensities, {"commodity": _OIL_SECTOR_TOKENS})
        result["scenario"] = {
            "key": "custom", "label": "Свой сценарий",
            "description": f"Нефть {oil_usd or '—'} $/барр. (сейчас {ref_oil or '—'}), курс {rub_usd or '—'} ₽/$ (сейчас {ref_rub or '—'})",
            "intensities": intensities,
            "reference": {"oil_usd": ref_oil, "rub_usd": ref_rub},
        }
    result["is_demo"] = True
    result["methodology"] = (
        "Тот же факторный движок (8 факторов: ставка/спрос/курс/сырьё/санкции/конфликт/налоги/"
        "рефинансирование), что считает сценарную устойчивость (MGI) в Индексе качества портфеля. "
        "Реакция каждой компании = Σ интенсивность(фактор) × эффект(экспозиция компании к фактору), "
        "кап ±60-70%. Не прогноз — иллюстрация направления и порядка величины при неполном покрытии "
        "факторов по компаниям (см. coverage у каждой позиции)."
    )
    return result

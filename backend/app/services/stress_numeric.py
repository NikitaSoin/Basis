"""Числовой контур «Стресс-тестирования» v2 (владелец, 2026-07-17: «+2% у акций
— это вообще про что?» — справедливо, у качественного контура не было семантики).

ЗДЕСЬ семантика ЖЁСТКАЯ и определённая:
    Пользователь задаёт целевые макро-условия (ставка X%, курс ₽Y/$, нефть $Z).
    Для каждой компании считаем Δ = coefficient × (цель − спот) по КАЖДОЙ метрике
    (выручка / EBITDA / чистая прибыль) — в млрд ₽ и в % от базы последнего
    отчётного года. Читается как: «если в среднем за год ставка будет X вместо
    текущих ~14,25 — чистая прибыль компании ориентировочно изменится на N млрд ₽
    (±M% от базы года)».

    «Спот» для ставки/курса — ЕДИНЫЙ актуальный уровень по рынку (get_current_levels()
    ниже), ОДИН И ТОТ ЖЕ для всех компаний, НЕ дата анализа конкретной карточки.
    Владелец, 2026-07-25 (повторно, после честной оговорки о «споте компании» в UI не
    хватило — «дельта 0, откуда ты взял у Полюса 15 процентов, это бред полнейший»):
    раньше rate/fx мерились от `macro_spot` КАЖДОЙ компании (дата её собственного
    макро-разбора) — если с тех пор ставка/курс реально изменились, «текущие уровни»
    слайдера расходились со спотом компании, и при НУЛЕВОМ движении слайдера дельта
    была не 0, а показывала эту накопившуюся разницу. Раз слайдер стартует от
    get_current_levels() (реального текущего уровня), а не от спота компании — меряем
    и Δ от ТОГО ЖЕ уровня: при движении слайдера на 0 факт-дельта строго 0 для ВСЕХ
    компаний, без исключений. Commodity-канал НЕ затронут: там спот компании
    (spot_commodity_компании) — легитимно СВОЙ ориентир (золото/Urals/алюминий,
    разный по смыслу), это множитель относительного шага, не точка отсчёта времени.

Источник коэффициентов — `macro.json → quant_inputs.coefficients` каждой компании:
их положил аналитик (Opus) с явными допущениями (поле assumption), арифметику
считает код — ровно та же философия, что в macro_quant.py («модель ненадёжна в
арифметике, числа складывает код»). НИЧЕГО не выдумываем: нет коэффициента по
фактору — компания не участвует в этом факторе (честная деградация, видна как
прочерк, а не ноль).

Нефть: ввод — Brent $/барр. У каждой нефтяной компании свой commodity-ориентир
(обычно Urals с санкционным дисконтом, у Полюса — золото, у Русала — алюминий и
т.п.), поэтому нефтяной шок применяем ТОЛЬКО к сектору «Нефть и газ» и
ОТНОСИТЕЛЬНО: Δcommodity_компании = spot_commodity_компании × (Brent_цель/Brent_спот − 1)
— Urals исторически ходит с Brent почти 1:1 по относительным изменениям
(дисконт меняется медленнее уровня). Для остальных секторов нефтяной ввод
не трогает их commodity-фактор (иначе повторим пойманный 2026-07-17 баг,
когда «обвал нефти» бил по золотодобытчикам).

ДЕМО-ОГОВОРКА наследуется: коэффициенты линейные (реальность нелинейна — демпфер,
прогрессивный НДПИ, хеджи), «полный перенос среднегодового уровня» — сильное
упрощение; см. assumption у каждого коэффициента — показываем его в UI.
"""
from __future__ import annotations

import json
from pathlib import Path

from sqlalchemy import text
from sqlalchemy.orm import Session

COMPANIES_DIR = Path(__file__).parent.parent.parent / "companies"

# Голубые фишки/размер 2-го эшелона — тот же список/порог, что в скринере (single
# source, копия осознанно: screener_scoring тянет тяжёлые зависимости, а нам нужен
# только набор тикеров + константа).
from app.services.screener_scoring import BLUE_CHIPS, ECHELON2_SIZE  # noqa: E402

_OIL_SECTOR_TOKENS = ("нефт", "газ", "oil", "gas")
_METRICS = ("revenue", "ebitda", "net_profit")
_METRIC_LABELS = {"revenue": "Выручка", "ebitda": "EBITDA", "net_profit": "Чистая прибыль"}


def _num(v):
    if isinstance(v, bool) or v is None:
        return None
    if isinstance(v, (int, float)):
        return float(v)
    return None


def _echelon_map(rows: list) -> dict[str, int]:
    """Тикер → эшелон (1 голубые фишки / 2 следующие ECHELON2_SIZE по капитализации
    / 3 остальные) — та же таксономия, что в скринере (screener_scoring.py), нужна
    здесь отдельно: карта рынка «Стресс-тестирования» по умолчанию показывает
    только 1-2 эшелон (владелец, 2026-07-24: «второй и третий эшелон большинству
    клиентов не интересен» — длинный хвост мелких бумаг с экстремальным % иначе
    вытесняет узнаваемые голубые фишки из топ-N по силе эффекта)."""
    ranked = sorted(
        (r for r in rows if r[3] is not None and r[0] not in BLUE_CHIPS),
        key=lambda r: -float(r[3]),
    )
    echelon2 = {r[0] for r in ranked[:ECHELON2_SIZE]}
    out: dict[str, int] = {}
    for r in rows:
        ticker = r[0]
        out[ticker] = 1 if ticker in BLUE_CHIPS else (2 if ticker in echelon2 else 3)
    return out


def get_current_levels(db: Session) -> dict:
    """Реальные текущие ориентиры (ставка/курс/нефть) — ЕДИНЫЙ источник для (а)
    стартовой позиции слайдеров на фронте (`/stress-test/current-levels`) и (б)
    точки отсчёта Δ в `_company_numeric_impact()` ниже (rate/fx-каналы). Было
    продублировано инлайн в app/api/stress.py — вынесено сюда, чтобы обе точки
    использования гарантированно смотрели на одно и то же число (см. докстринг
    файла, 2026-07-25). Любое поле может быть None, если источник временно
    недоступен — вызывающий код обязан честно деградировать, не выдавать None
    за число."""
    from datetime import date
    from sqlalchemy import text as _text
    from app.models.macro import MacroDataPoint
    from app.models.future import Future

    rate_row = (db.query(MacroDataPoint)
                .filter_by(indicator_code="key_rate", metric="level")
                .order_by(MacroDataPoint.as_of.desc()).first())
    fx_row = db.execute(_text(
        "SELECT last_price FROM spot_assets WHERE secid = 'USD000UTSTOM'")).first()
    today = date.today()
    oil_f = (db.query(Future)
             .filter(Future.asset_code == "BR",
                     (Future.expiration_date.is_(None)) | (Future.expiration_date >= today))
             .order_by(Future.expiration_date.asc().nullslast()).first())
    return {
        "key_rate_pct": float(rate_row.value) if rate_row else None,
        "fx_usdrub": float(fx_row[0]) if fx_row and fx_row[0] is not None else None,
        "oil_brent_usd": float(oil_f.last_price) if oil_f and oil_f.last_price is not None else None,
    }


def _load_quant(ticker: str) -> dict | None:
    path = COMPANIES_DIR / ticker.upper() / "macro.json"
    if not path.exists():
        return None
    try:
        d = json.loads(path.read_text(encoding="utf-8"))
        return d.get("quant_inputs") or None
    except Exception:  # noqa: BLE001
        return None


def _company_numeric_impact(qi: dict, sector: str | None,
                            key_rate_pct: float | None,
                            fx_usdrub: float | None,
                            oil_brent_usd: float | None,
                            brent_spot: float | None,
                            base_key_rate_pct: float | None = None,
                            base_fx_usdrub: float | None = None) -> dict | None:
    """Δ метрик компании (млрд ₽ и % от базы) при целевых условиях. Внутри метрик:
    0 — честный ноль (ни один текущий фактор компанию не касается, но у нас ЕСТЬ
    её коэффициенты); None — фактор задействован, но коэффициент именно на эту
    метрику не задан (реально не знаем).

    Владелец, 2026-07-24: «когда двигаешь ползунки — какие-то компании вылетают,
    какие-то появляются, это не норма» — раньше при factor_deltas={} (ни один
    слайдер не сдвинут от спота ЭТОЙ компании) функция возвращала None и компания
    целиком исчезала из вселенной/карты до следующего движения слайдера. Компания
    с ХОТЯ БЫ одним коэффициентом теперь остаётся в списке ВСЕГДА — состав карты
    стабилен, меняются только числа."""
    coefs = qi.get("coefficients") or {}
    spot = qi.get("macro_spot") or qi.get("macro_current") or {}
    fin = qi.get("financials") or {}
    sector_l = (sector or "").lower()

    # Δ по каждому задействованному фактору в ЕДИНИЦАХ коэффициента.
    # rate/fx мерятся от ЕДИНОГО текущего уровня (base_key_rate_pct/base_fx_usdrub —
    # get_current_levels(), см. докстринг файла), НЕ от macro_spot ЭТОЙ компании —
    # иначе при нулевом движении слайдера дельта была не 0, а показывала разницу
    # между датой чужого макро-разбора и реальным текущим уровнем (владелец,
    # 2026-07-25: «откуда ты взял у Полюса 15 процентов, это бред»).
    factor_deltas: dict[str, float] = {}
    applied: list[dict] = []

    if key_rate_pct is not None and base_key_rate_pct is not None and "rate" in coefs:
        d = key_rate_pct - base_key_rate_pct
        if abs(d) > 1e-9:
            factor_deltas["rate"] = d
            applied.append({"factor": "rate", "label": "Ключевая ставка",
                            "from": base_key_rate_pct, "to": key_rate_pct,
                            "assumption": (coefs["rate"] or {}).get("assumption")})

    if fx_usdrub is not None and base_fx_usdrub is not None and "fx" in coefs:
        d = fx_usdrub - base_fx_usdrub
        if abs(d) > 1e-9:
            factor_deltas["fx"] = d
            applied.append({"factor": "fx", "label": "Курс USD/RUB",
                            "from": base_fx_usdrub, "to": fx_usdrub,
                            "assumption": (coefs["fx"] or {}).get("assumption")})

    if (oil_brent_usd is not None and brent_spot and
            any(t in sector_l for t in _OIL_SECTOR_TOKENS) and
            _num(spot.get("commodity_usd")) is not None and "commodity" in coefs):
        rel = oil_brent_usd / brent_spot - 1.0
        d = float(spot["commodity_usd"]) * rel
        if abs(d) > 1e-9:
            factor_deltas["commodity"] = d
            applied.append({"factor": "commodity", "label": "Цена нефти (относительно, через сырьё компании)",
                            "from": round(float(spot["commodity_usd"]), 1),
                            "to": round(float(spot["commodity_usd"]) * (1 + rel), 1),
                            "assumption": (coefs["commodity"] or {}).get("assumption")})

    has_any_factor = bool(factor_deltas)

    out_metrics: dict[str, dict] = {}
    for m in _METRICS:
        total = 0.0
        covered = False
        for f, d in factor_deltas.items():
            c = _num((coefs.get(f) or {}).get(m))
            if c is None:
                continue
            covered = True
            total += c * d
        base = _num(fin.get(m))
        if not covered:
            if has_any_factor:
                # фактор сдвинут, но коэффициент именно на эту метрику не задан
                out_metrics[m] = {"delta_bn": None, "pct_of_base": None, "base_bn": base}
            else:
                # ни один текущий фактор компанию не касается — честный ноль
                out_metrics[m] = {"delta_bn": 0.0, "pct_of_base": 0.0, "base_bn": base}
            continue
        # % от базы вырожден при крошечной базе (у OZON прибыль ~1 млрд → «+543%»
        # ничего не говорит) — показываем % только когда |Δ| ≤ 2×|базы|, иначе
        # только млрд ₽ (число всё равно честное, некорректен только процент).
        pct = None
        if base and abs(total) <= 2 * abs(base):
            pct = round(total / abs(base) * 100, 1)
        out_metrics[m] = {"delta_bn": round(total, 1), "pct_of_base": pct, "base_bn": base}

    return {"metrics": out_metrics, "applied_factors": applied,
            "fiscal_year": (fin.get("fiscal_year") if isinstance(fin.get("fiscal_year"), str) else None)}


def numeric_impact(db: Session, key_rate_pct: float | None, fx_usdrub: float | None,
                   oil_brent_usd: float | None) -> dict:
    """По всей вселенной компаний. Сортировка: голубые фишки первыми (владелец),
    внутри группы — по |Δ чистой прибыли в % от базы|."""
    # Единый текущий уровень — тот же источник, что стартовая позиция слайдеров
    # на фронте (get_current_levels() выше) — rate/fx-каналы меряют Δ от НЕГО,
    # не от спота карточки компании (см. докстринг файла и _company_numeric_impact).
    current = get_current_levels(db)
    brent_spot = current.get("oil_brent_usd")

    rows = db.execute(text("""
        SELECT c.ticker, c.name, c.sector, c.market_cap FROM companies c
        JOIN company_metrics m ON m.ticker = c.ticker
    """)).fetchall()
    echelon_by_ticker = _echelon_map(rows)

    companies = []
    for r in rows:
        ticker, name, sector = r[0], r[1], r[2]
        qi = _load_quant(ticker)
        if not qi or not (qi.get("coefficients") or {}):
            continue
        impact = _company_numeric_impact(qi, sector, key_rate_pct, fx_usdrub, oil_brent_usd, brent_spot,
                                          base_key_rate_pct=current.get("key_rate_pct"),
                                          base_fx_usdrub=current.get("fx_usdrub"))
        if not impact:
            continue
        np_metric = impact["metrics"].get("net_profit") or {}
        np_pct, np_bn = np_metric.get("pct_of_base"), np_metric.get("delta_bn")
        if np_pct is not None:
            sort_key = abs(np_pct)
        elif np_bn is not None:
            # % подавлен НЕ потому что эффекта нет, а потому что эффект БОЛЬШЕ базы —
            # экстремальный случай, ранжируем его высоко, а не последним (было -1, из-за
            # чего компания с крупнейшим |Δ млрд ₽| (напр. Роснефть в сценарии «нефть $45»)
            # уходила в конец списка голубых фишек — прямая причина «непонятно кто
            # пострадал больше»).
            sort_key = 999 + abs(np_bn)
        else:
            sort_key = -1
        companies.append({
            "ticker": ticker, "name": name, "sector": sector,
            "is_blue_chip": ticker in BLUE_CHIPS, "echelon": echelon_by_ticker.get(ticker, 3),
            **impact,
            "_sort": sort_key,
        })

    companies.sort(key=lambda c: (not c["is_blue_chip"], -c["_sort"]))
    for c in companies:
        del c["_sort"]

    return {
        "companies": companies,
        "reference": {"brent_spot_usd": brent_spot},
        "inputs": {"key_rate_pct": key_rate_pct, "fx_usdrub": fx_usdrub, "oil_brent_usd": oil_brent_usd},
        "semantics": (
            "Δ — оценка изменения ГОДОВОЙ метрики (к базе последнего отчётного года) при условии, "
            "что заданные уровни станут СРЕДНИМИ за год, при линейном переносе по коэффициентам "
            "чувствительности из макро-разбора компании (свои у каждой компании, с допущениями). "
            "Ставка/курс считаются от ЕДИНОГО текущего уровня рынка (один и тот же для всех "
            "компаний) — при нулевом сдвиге ползунка Δ строго 0. Нефть — относительно (свой "
            "commodity-ориентир компании: золото/Urals/алюминий и т.п.), поэтому один и тот же "
            "сдвиг Brent даёт разный % у разных компаний. Не прогноз цены акции и не таргет — "
            "иллюстрация чувствительности финансовых показателей."
        ),
        "is_demo": True,
    }


def coefficients_payload(db: Session) -> dict:
    """Сырые входные данные (коэффициенты чувствительности + spot + база года +
    эшелон) по всем компаниям с quant_inputs — владелец, 2026-07-24: «в демо
    (Клод-дизайн) слайдеры пересчитывают/перекрашивают карту мгновенно, у нас
    задержка» — было 350ms debounce + round-trip на /numeric при КАЖДОМ движении
    ползунка. Формула у _company_numeric_impact() чисто арифметическая (без
    похода в БД внутри цикла) — портируема 1:1 в JS. Отдаём сырые данные ОДИН
    раз при загрузке экрана, дальше фронт считает сам на каждый кадр слайдера.

    ВАЖНО: если меняешь арифметику в _company_numeric_impact() — синхронно
    поправь JS-двойник (companyImpact() в StressTestView.jsx), иначе слайдерный
    путь и путь через /ask (сервер) начнут расходиться в цифрах."""
    rows = db.execute(text("""
        SELECT c.ticker, c.name, c.sector, c.market_cap FROM companies c
        JOIN company_metrics m ON m.ticker = c.ticker
    """)).fetchall()
    echelon_by_ticker = _echelon_map(rows)

    companies = []
    for r in rows:
        ticker, name, sector = r[0], r[1], r[2]
        qi = _load_quant(ticker)
        if not qi:
            continue
        coefs = qi.get("coefficients") or {}
        if not coefs:
            continue
        companies.append({
            "ticker": ticker, "name": name, "sector": sector,
            "is_blue_chip": ticker in BLUE_CHIPS, "echelon": echelon_by_ticker.get(ticker, 3),
            "coefficients": coefs,
            "macro_spot": qi.get("macro_spot") or qi.get("macro_current") or {},
            "financials": qi.get("financials") or {},
        })
    return {"companies": companies}

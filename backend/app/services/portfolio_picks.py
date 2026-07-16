"""Подборка портфелей (Скринер → «Подборка портфелей»): несколько тезисных
модельных портфелей на профиль риска, собранных ЖИВЬЁМ из существующего
скринер-движка (screener_scoring.score_universe) — не список тикеров с потолка
и не один канонический портфель на профиль (владелец, 2026-07-17: «несколько
консервативных, несколько сбалансированных, несколько агрессивных», у каждого —
явный расчёт + предположение о рынке).

Каждый PICK — предикат-фильтр + сортировка по УЖЕ существующим полям
screener_scoring (raw.*, subindices.*, basis) — никаких новых метрик не
считаем, никакого gadanie: если поле пустое у бумаги, она просто не проходит
фильтр. Вес внутри портфеля — обратно пропорционален волатильности (raw.volatility),
с капом по сектору (после каждого пересчёта секторов, превышающих cap, — сжимаем
до cap и перераспределяем остаток пропорционально остальным).

🔴 Честные приближения (не выдаём за точнее, чем есть):
- «Волатильность портфеля» — средневзвешенная волатильность ПОЗИЦИЙ, не
  дисперсия портфеля с ковариацией (это ВЕРХНЯЯ оценка — реальная волатильность
  диверсифицированного портфеля обычно ниже за счёт неполной корреляции).
- «Средний BASIS-балл» — не полный «Индекс качества портфеля v2.1» (тот
  считается по реальным позициям в БД с суб-индексами диверсификации/
  ликвидности/MGI) — это просто средневзвешенный BASIS-балл (качество+оценка+
  стабильность) выбранных бумаг, честно назван иначе, не путать с v2.1.
- Дивдоходность и апсайд — валидные линейные средневзвешенные (без приближения).
"""
from __future__ import annotations

from sqlalchemy.orm import Session

from app.services.screener_scoring import score_universe

# Секторная нормализация — тот же принцип, что в frontend/Basis/scripts/
# generate-seo-pages.js normalizeSector() (meta.sector — зоопарк англ. слагов и
# русских названий), нужна ТОЛЬКО для секторного фильтра/капа здесь, не трогает
# исходные данные.
_SECTOR_RULES = [
    (("utilities", "energy_", "energosbyt", "электросети", "электроэнергет", "энергетика"), "Электроэнергетика"),
    (("finance", "financials", "банки", "финансы", "investment"), "Финансы"),
    (("consumer", "потребительск", "retail"), "Потребительский сектор"),
    (("metals", "mining", "металлург", "драгоценная добыча"), "Металлургия и добыча"),
    (("oil_gas", "нефтегаз", "нефть и газ", "нефтеперераб"), "Нефть и газ"),
    (("telecom", "телеком"), "Телекоммуникации"),
    (("chemicals", "химия"), "Химия и удобрения"),
    (("it", "technology", "edtech", "информационные технолог", "media"), "ИТ и технологии"),
    (("machinery", "industrials", "машиностроен", "судостроен", "автопром"), "Машиностроение и промышленность"),
    (("real_estate", "developer", "девелопмент", "infrastructure"), "Девелопмент и инфраструктура"),
    (("transport", "транспорт"), "Транспорт"),
    (("pharma", "здравоохран", "медицин"), "Медицина и фарма"),
]


def _norm_sector(raw: str | None) -> str:
    s = (raw or "").strip().lower()
    if not s:
        return "Прочее"
    for keys, label in _SECTOR_RULES:
        if any(k in s for k in keys):
            return label
    clean = (raw or "").strip().split("(")[0].split("«")[0].strip()
    return (clean[0].upper() + clean[1:]) if clean else "Прочее"


def _stability(row: dict) -> float | None:
    return row.get("subindices", {}).get("stability")


def _basis(row: dict) -> float | None:
    return row.get("basis")


def _raw(row: dict, key: str) -> float | None:
    return row.get("raw", {}).get(key)


def _ok_confidence(row: dict) -> bool:
    return not row.get("low_confidence") and not row.get("anomaly")


PICKS = [
    {
        "tier": "cons", "key": "div-anchor", "name": "Дивидендный якорь",
        "thesis": "Отбор среди акций с высокой дивдоходностью (после кэпа 18%) и стабильностью выше медианы — низкая бета/волатильность/долговая нагрузка, BASIS-балл не ниже 45.",
        "assumption": "Предполагаем, что ключевая ставка ЦБ останется повышенной ещё 2–3 квартала — в этой среде высокая дивдоходность конкурентна с депозитом, а низкая волатильность сглаживает просадки индекса.",
        "filter": lambda r: _ok_confidence(r) and (_stability(r) or 0) >= 50 and (_raw(r, "div_yield") or 0) >= 6 and (_basis(r) or 0) >= 45,
        "sort": lambda r: -(_raw(r, "div_yield") or 0),
        "n": 9, "sector_cap": 0.32,
    },
    {
        "tier": "cons", "key": "infl-guard", "name": "Защита от инфляции",
        "thesis": "Компании с высокой операционной (EBITDA) маржой — пропускают рост издержек в цену — и стабильностью выше медианы.",
        "assumption": "Предполагаем, что инфляция останется вблизи текущего уровня дольше, чем закладывает рыночный консенсус — портфель почти не теряет реальную покупательную способность.",
        "filter": lambda r: _ok_confidence(r) and (_stability(r) or 0) >= 50 and (_raw(r, "ebitda_margin") or 0) >= 25 and (_basis(r) or 0) >= 45,
        "sort": lambda r: -(_stability(r) or 0),
        "n": 9, "sector_cap": 0.35,
    },
    {
        "tier": "bal", "key": "broad", "name": "Широкий рынок",
        "thesis": "Отбор по совокупному BASIS-баллу (качество + оценка + стабильность, вес 40/35/25) без выраженного секторного крена.",
        "assumption": "Предполагаем нейтральный сценарий: постепенное смягчение ДКП без резких шоков ставки или геополитики.",
        "filter": lambda r: _ok_confidence(r) and (_basis(r) or 0) >= 55,
        "sort": lambda r: -(_basis(r) or 0),
        "n": 10, "sector_cap": 0.30,
    },
    {
        "tier": "bal", "key": "cycle", "name": "Ставка на цикл сырья",
        "thesis": "Концентрация в металлургии/добыче и нефтегазе — секторах с прямой чувствительностью к ценам сырья — среди бумаг с BASIS-баллом не ниже 45.",
        "assumption": "Предполагаем, что цены на сырьё проходят дно в ближайшие 2–3 квартала на фоне смягчения ставок крупных ЦБ — направленная ставка, не факт.",
        "filter": lambda r: _ok_confidence(r) and _norm_sector(r.get("sector")) in ("Металлургия и добыча", "Нефть и газ") and (_basis(r) or 0) >= 45,
        "sort": lambda r: -(_basis(r) or 0),
        "n": 8, "sector_cap": 0.60,
    },
    {
        # 🔴 Апсайд ограничен сверху 80% — у ~40 бумаг вселенной расчётный апсайд
        # превышает 100% (до 550%+ на живых данных, проверено 2026-07-17) — это
        # хвост, где DCF/относительная модель, вероятнее всего, ловит дистресс-
        # артефакт, а не реальную недооценку. Сортировка по «максимум апсайда»
        # без потолка тянула ВСЕ 9 позиций из этого хвоста (100-250% апсайда) —
        # для «портфеля, который считаем оптимальным» это не выглядело бы
        # достоверно, хотя технически число честное. Кап — не про точность
        # модели, а про то, чтобы не выдавать вероятный артефакт за тезис.
        "tier": "agg", "key": "upside", "name": "Рост и апсайд",
        "thesis": "Отбор по максимальному расчётному апсайду к справедливой цене платформы (в пределах 80%, чтобы не тянуть вероятные модельные искажения) среди бумаг с BASIS-баллом не ниже 55.",
        "assumption": "Предполагаем, что рынок постепенно закроет разрыв с фундаментальной оценкой в течение 12 месяцев — без гарантии сроков и без гарантии, что сама оценка не изменится.",
        "filter": lambda r: _ok_confidence(r) and 0 < (_raw(r, "upside") or -999) <= 80 and (_basis(r) or 0) >= 55,
        "sort": lambda r: -(_raw(r, "upside") or 0),
        "n": 9, "sector_cap": 0.35,
    },
    {
        "tier": "agg", "key": "contrarian", "name": "Контрарианская ставка",
        "thesis": "Бумаги СРЕДНЕГО (не топового) BASIS-балла 45–65 с высоким, но не экстремальным расчётным апсайдом (15–80%) — там, где рынок мог занизить перспективы сильнее, чем оправдано фундаменталом.",
        "assumption": "Предполагаем, что часть негативного фона вокруг этих имён уже отражена в цене с запасом — тезис проверяется по мере выхода отчётности, не гарантирован.",
        "filter": lambda r: _ok_confidence(r) and 45 <= (_basis(r) or 0) < 65 and 15 <= (_raw(r, "upside") or -999) <= 80,
        "sort": lambda r: -(_raw(r, "upside") or 0),
        "n": 8, "sector_cap": 0.35,
    },
]


def _weight_positions(rows: list[dict], sector_cap: float) -> list[dict]:
    """Вес = 1/волатильность, нормировано на 1; бумаги без volatility — средний вес
    пула. Секторный кап: сектора выше cap сжимаются до cap, излишек
    перераспределяется пропорционально остальным (2 прохода — на типичных
    распределениях 6-10 позиций этого достаточно, не гоняемся за точным LP)."""
    if not rows:
        return []
    vols = [_raw(r, "volatility") for r in rows if _raw(r, "volatility")]
    fallback_vol = (sum(vols) / len(vols)) if vols else 25.0
    inv = [1.0 / (_raw(r, "volatility") or fallback_vol) for r in rows]
    total = sum(inv)
    weights = [v / total for v in inv]

    for _pass in range(2):
        sector_sum: dict[str, float] = {}
        for r, w in zip(rows, weights):
            s = _norm_sector(r.get("sector"))
            sector_sum[s] = sector_sum.get(s, 0.0) + w
        over = {s: v for s, v in sector_sum.items() if v > sector_cap + 1e-9}
        if not over:
            break
        excess = 0.0
        for i, r in enumerate(rows):
            s = _norm_sector(r.get("sector"))
            if s in over:
                scale = sector_cap / sector_sum[s]
                new_w = weights[i] * scale
                excess += weights[i] - new_w
                weights[i] = new_w
        under_idx = [i for i, r in enumerate(rows) if _norm_sector(r.get("sector")) not in over]
        under_total = sum(weights[i] for i in under_idx)
        if under_total > 0 and excess > 0:
            for i in under_idx:
                weights[i] += excess * (weights[i] / under_total)

    wsum = sum(weights) or 1.0
    weights = [w / wsum for w in weights]
    return [{**r, "weight": w} for r, w in zip(rows, weights)]


def _build_one(pick: dict, universe_rows: list[dict]) -> dict:
    pool = [r for r in universe_rows if pick["filter"](r)]
    pool.sort(key=pick["sort"])
    picked = pool[: pick["n"]]
    weighted = _weight_positions(picked, pick["sector_cap"])

    def wavg(field_fn):
        vals = [(field_fn(r), r["weight"]) for r in weighted if field_fn(r) is not None]
        wsum = sum(w for _, w in vals)
        return round(sum(v * w for v, w in vals) / wsum, 2) if wsum else None

    sector_weights: dict[str, float] = {}
    for r in weighted:
        s = _norm_sector(r.get("sector"))
        sector_weights[s] = sector_weights.get(s, 0.0) + r["weight"]
    sectors = sorted(
        [{"sector": s, "weight_pct": round(w * 100, 1)} for s, w in sector_weights.items()],
        key=lambda x: -x["weight_pct"],
    )

    positions = [
        {
            "ticker": r["ticker"], "name": r.get("name"), "sector": r.get("sector"),
            "weight_pct": round(r["weight"] * 100, 1),
            "basis": r.get("basis"),
            "upside_pct": _raw(r, "upside"),
            "div_yield_pct": _raw(r, "div_yield"),
        }
        for r in sorted(weighted, key=lambda r: -r["weight"])
    ]

    return {
        "tier": pick["tier"], "key": pick["key"], "name": pick["name"],
        "thesis": pick["thesis"], "assumption": pick["assumption"],
        "pool_size": len(pool), "positions": positions, "sectors": sectors,
        "metrics": {
            "avg_basis": wavg(_basis),
            "avg_volatility_pct": wavg(lambda r: _raw(r, "volatility")),
            "avg_div_yield_pct": wavg(lambda r: _raw(r, "div_yield")),
            "avg_upside_pct": wavg(lambda r: _raw(r, "upside")),
        },
    }


_TIER_META = {
    "cons": {"name": "Консервативный", "sub": "низкая волатильность, дивдоходность"},
    "bal": {"name": "Сбалансированный", "sub": "риск/доходность в середине распределения"},
    "agg": {"name": "Агрессивный", "sub": "выше апсайд к справедливой цене, выше риск"},
}


def build_portfolio_picks(db: Session) -> dict:
    """Отдаёт все 6 (или сколько наберётся — честная деградация, если фильтр
    не набрал минимум позиций, портфель просто получает меньше pool_size,
    не выдумываем позиции)."""
    universe = score_universe(db, universe="all")
    rows = universe["rows"]
    picks = [_build_one(p, rows) for p in PICKS]
    tiers = []
    for tkey, meta in _TIER_META.items():
        tiers.append({
            "key": tkey, "name": meta["name"], "sub": meta["sub"],
            "portfolios": [p for p in picks if p["tier"] == tkey],
        })
    return {
        "as_of": universe["universe"],
        "methodology": "BASIS-скор (screener_scoring v0, качество 40% + оценка 35% + стабильность 25%) — те же данные и формула, что в Скринере акций. Вес позиции — обратно пропорционален волатильности, сектор ограничен капом.",
        "tiers": tiers,
    }

"""Сверка коэффициентов чувствительности из карточек с независимым расчётом.

🔴 ЗАЧЕМ (владелец, 2026-08-02): «чувствительности я бы считал отдельно и где-то это
помечал — в карточках могут быть плохо посчитанные числа с точки зрения методички».

Претензия подтверждается данными: разброс чувствительности к ставке ВНУТРИ сектора
доходит до −57…+17 % (utilities) и −2…+55 % (металлургия). Часть — законная (компания
с кубышкой против закредитованной), часть — явные ошибки карточек.

Как устроено: `sensitivity_structural` считает ту же величину из структуры отчётности
арифметикой, здесь — сравнение. Расхождение не приговор карточке (наша оценка тоже
груба), а ФЛАГ: сюда стоит посмотреть глазами. Методика и границы применимости —
`docs/sensitivity_methodology.md`.

🔴 Раньше (до 2026-08-03) сверялся ОДИН канал — процентный, и только у компаний с
положительным чистым долгом. Это оставляло без проверки самый частый класс ошибок:
знак у компаний с кубышкой и весь курсовой/издержечный контур. Теперь проверяются все
каналы, которые модуль умеет считать честно.
"""
from __future__ import annotations

import json
import logging
from pathlib import Path

from app.services.sensitivity_structural import (
    COMPANIES_DIR,
    structural_sensitivity,
)

logger = logging.getLogger(__name__)

_MISMATCH_FACTOR = 3.0        # расхождение в разы, после которого поднимаем флаг
_UNIT_TO_BLN = {"млрд_руб": 1.0, "млн_руб": 0.001}
_MIN_MEANINGFUL_PCT = 1.0     # ниже этого обе оценки — шум, сравнивать нечего
# 🔴 Потолок правдоподобия — тот же, что в карте чувствительности. Эффект больше двух
# годовых прибылей на один шок означает не чувствительность, а несопоставимость с
# базой: околонулевая прибыль микрокапа, оболочка, ошибка единиц. Такие пары нельзя
# смешивать с содержательными расхождениями — иначе рабочий список «посмотреть
# глазами» возглавляют «3750% против 14%», и до реальных ошибок никто не дочитает.
_MAX_PLAUSIBLE_PCT = 200.0

_CHANNEL_RU = {"rate": "ставка", "fx": "курс", "labor": "зарплаты",
               "cost_inflation": "инфляция издержек"}


def _load(ticker: str, name: str) -> dict | None:
    path = COMPANIES_DIR / ticker / name
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:  # noqa: BLE001
        return None


def _card_pct(macro: dict, channel: str, shock: float) -> float | None:
    """Коэффициент карточки, приведённый к «% годовой базы на шок»."""
    qi = macro.get("quant_inputs") or {}
    scale = _UNIT_TO_BLN.get(str(qi.get("unit") or "").strip().lower())
    spec = (qi.get("coefficients") or {}).get(channel)
    if scale is None or not isinstance(spec, dict):
        return None
    delta = spec.get("net_profit")
    fin_q = qi.get("financials") or {}
    base = fin_q.get("net_profit") if (fin_q.get("net_profit") or 0) > 0 else fin_q.get("revenue")
    if not isinstance(delta, (int, float)) or not base:
        return None
    # scale сокращается (коэффициент и база в одной единице), оставлен для явности.
    return round((delta * scale * shock) / (float(base) * scale) * 100, 1)


def audit_sensitivity(limit: int | None = None, key_rate: float = 14.0,
                      usd_rate: float = 80.0) -> list[dict]:
    """Спорные коэффициенты по всем проверяемым каналам.

    Возвращает только расхождения (разный знак или разница в разы) — это рабочий
    список «посмотреть глазами», а не отчёт по всем 264.
    """
    from app.services.macro_sensitivity_map import _CHANNEL_SHOCK

    if not COMPANIES_DIR.exists():
        return []
    out = []
    for d in sorted(COMPANIES_DIR.iterdir()):
        if not d.is_dir() or d.name.startswith("."):
            continue
        ticker = d.name
        macro = _load(ticker, "macro.json")
        if not macro:
            continue
        structural = structural_sensitivity(ticker, key_rate=key_rate, usd_rate=usd_rate)
        if not structural:
            continue
        for channel, calc in (structural.get("channels") or {}).items():
            shock = _CHANNEL_SHOCK.get(channel)
            if not shock:
                continue
            card = _card_pct(macro, channel, shock[0])
            if card is None:
                continue
            own = calc["pct"]
            issue, kind = None, "величина"
            if abs(card) > _MAX_PLAUSIBLE_PCT or abs(own) > _MAX_PLAUSIBLE_PCT:
                out.append({"ticker": ticker, "channel": channel,
                            "channel_ru": _CHANNEL_RU.get(channel, channel),
                            "card_pct": card, "structural_pct": own,
                            "base": structural["base"], "how": calc["how"], "kind": "база",
                            "issue": "эффект больше двух годовых баз — сравнивать нечего, "
                                     "база околонулевая или единицы в карточке неверны"})
                continue
            # Каналы-«границы» (зарплаты, инфляция издержек) сравниваем ОДНОСТОРОННЕ:
            # структурная величина — предел удара при нулевом переносе в цену, а
            # сколько компания реально переносит, из отчётности не видно. Ошибкой
            # является только удар СИЛЬНЕЕ предела; всё, что мягче, — законный перенос.
            if calc.get("kind") == "граница":
                if card < 0 and abs(card) > abs(own) * 1.2 and abs(own) > _MIN_MEANINGFUL_PCT:
                    out.append({"ticker": ticker, "channel": channel,
                                "channel_ru": _CHANNEL_RU.get(channel, channel),
                                "card_pct": card, "structural_pct": own,
                                "base": structural["base"], "how": calc["how"],
                                "kind": "предел",
                                "issue": f"карточка показывает удар сильнее физического "
                                         f"предела ({own}% при нулевом переносе в цену)"})
                continue
            if card * own < 0 and abs(card) > _MIN_MEANINGFUL_PCT and abs(own) > _MIN_MEANINGFUL_PCT:
                issue, kind = (
                    f"знак: карточка говорит «{'выигрывает' if card > 0 else 'проигрывает'}», "
                    f"структура отчётности — обратное"), "знак"
            elif abs(card) > _MIN_MEANINGFUL_PCT and abs(own) > _MIN_MEANINGFUL_PCT:
                ratio = abs(card) / abs(own)
                if ratio > _MISMATCH_FACTOR or ratio < 1 / _MISMATCH_FACTOR:
                    issue = f"величина: расхождение в {max(ratio, 1 / ratio):.1f} раза"
            elif abs(card) < 0.5 <= abs(own):
                issue, kind = "карточка почти не видит канал, хотя структура его показывает", "пропуск"
            if issue:
                out.append({"ticker": ticker, "channel": channel,
                            "channel_ru": _CHANNEL_RU.get(channel, channel),
                            "card_pct": card, "structural_pct": own,
                            "base": structural["base"], "how": calc["how"],
                            "kind": kind, "issue": issue})
    # Сначала расхождения в ЗНАКЕ (там кто-то точно неправ), потом величина и
    # пропуски, и только в конце — случаи несопоставимой базы.
    order = {"знак": 0, "предел": 1, "величина": 2, "пропуск": 3, "база": 4}
    out.sort(key=lambda r: (order.get(r.get("kind"), 9),
                            -abs(r["card_pct"] - r["structural_pct"])))
    return out[:limit] if limit else out


def audit_rate_sensitivity(limit: int | None = None) -> list[dict]:
    """Совместимость: только процентный канал (так его ждёт карта чувствительности)."""
    return [r for r in audit_sensitivity(limit=None) if r["channel"] == "rate"][:limit or None]

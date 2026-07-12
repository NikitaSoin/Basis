"""Интерпретатор макроситуации (Направление 2, модуль G).

Берёт ВСЕ показатели платформы (РФ+мир) + аналитику ЦБ/ЦМАКП + прогноз ЦБ →
строит связную интерпретацию СТРОГО по методичке docs/macroeconomics_methodology.md
(направление МАКРО→СТАВКА→РЫНОК→СЕКТОРА). Модель — DeepSeek Pro на РАССУЖДЕНИИ
(thinking=True): это думающая задача, не выжимка. Без «купить/продать».
"""
from __future__ import annotations

import json
import logging
import os
from datetime import datetime, timezone

from sqlalchemy.orm import Session

from app.models.macro import (MacroIndicator, MacroDataPoint, RateMeeting,
                              MacroAnalyticsDoc, MacroForecast, MacroInterpretation)
from app.services import llm

logger = logging.getLogger(__name__)

_REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
_METHODOLOGY = os.path.join(_REPO, "docs", "macroeconomics_methodology.md")
_SECTORS = os.path.join(_REPO, "config", "sectors.json")

# Жёсткая инструкция формата вывода (раздел 14 методички) — добавляется к методичке.
# ВАЖНО (2026-07-12, владелец раскритиковал прозу как «простыню», product-analyst-fin
# подтвердил диагноз): раньше current_picture/rate_outlook/cb_forecast_view/market_sectors
# были связным текстом-эссе — числа тонули в повествовании, глазу негде «приземлиться».
# Теперь вывод — атомарные тезисы: каждое поле самостоятельный факт/оценка, без прозы.
_OUTPUT_SPEC = (
    "\n\n================================================================\n"
    "ФОРМАТ ОТВЕТА (СТРОГО JSON, на русском). НИКАКОЙ СВЯЗНОЙ ПРОЗЫ — каждое поле "
    "самостоятельный факт или тезис, читается за 1-2 секунды. Числа живут ВНУТРИ "
    "полей detail/channel, не растворяются в повествовательных предложениях.\n"
    "Верни {\"sections\": {\n"
    "  \"headline\": \"<ГЛАВНЫЙ ВЫВОД одним предложением, максимум 25 слов — вердикт Basis по текущей макрокартине>\",\n"
    "  \"theses\": [ // 4-6 штук, покрывают: экономика/ВВП, потребление, инфляция, ставка, прогноз ЦБ\n"
    "    {\"topic\": \"<2-3 слова>\", \"tag\": \"факт|оценка\",\n"
    "     \"claim\": \"<тезис максимум 15 слов, БЕЗ чисел>\",\n"
    "     \"detail\": \"<числа-доказательство максимум 18 слов>\"}\n"
    "  ],\n"
    "  \"sectors\": [ // по КАЖДОМУ сектору платформы (список ниже в данных)\n"
    "    {\"sector\": \"<имя сектора из списка платформы>\", \"wind\": \"попутный|встречный|смешанный\",\n"
    "     \"channel\": \"<через какой канал, максимум 15 слов>\"}\n"
    "  ],\n"
    "  \"watch\": [\"<что подтвердит/сдвинет картину дальше, максимум 12 слов>\", \"...\", \"...\"], // 2-3 штуки\n"
    "  \"scenarios\": {\n"
    "    \"base\": {\"probability\": \"<строка, напр. '55%'>\", \"key_numbers\": \"<ключевые ориентиры: ставка/инфляция/курс на горизонте>\", \"triggers\": \"<что подтвердит именно этот сценарий>\"},\n"
    "    \"bull\": {\"probability\": \"<строка>\", \"key_numbers\": \"<...>\", \"triggers\": \"<...>\"},\n"
    "    \"bear\": {\"probability\": \"<строка>\", \"key_numbers\": \"<...>\", \"triggers\": \"<...>\"}\n"
    "  }\n"
    "}}. scenarios — СТРОГО объект с тремя ключами base/bull/bear, каждый со всеми тремя "
    "полями (probability/key_numbers/triggers) как короткие строки. Вероятности трёх "
    "сценариев должны в сумме давать ~100%. theses[].tag: 'факт' — если claim прямо следует "
    "из переданных чисел без интерпретации, 'оценка' — если это суждение Basis. Опирайся на "
    "КОНКРЕТНЫЕ значения показателей из переданных данных. Тон спокойный, без "
    "‘купить/продать’. Никакого текста вне JSON."
)


def _methodology() -> str:
    try:
        with open(_METHODOLOGY, encoding="utf-8") as f:
            return f.read()
    except OSError:
        return "Методичка недоступна — действуй как старший макроаналитик: МАКРО→СТАВКА→РЫНОК→СЕКТОРА."


def _sectors_list() -> list[str]:
    try:
        with open(_SECTORS, encoding="utf-8") as f:
            data = json.load(f)
        return [v.get("name", k) for k, v in (data.get("sectors") or {}).items()]
    except OSError:
        return []


def gather_snapshot(db: Session) -> dict:
    """Срез текущих данных платформы для интерпретатора."""
    indicators = []
    for ind in db.query(MacroIndicator).order_by(MacroIndicator.sort_order).all():
        for m in (ind.metric_types or ["level"]):
            p = (db.query(MacroDataPoint).filter_by(indicator_code=ind.code, metric=m)
                 .order_by(MacroDataPoint.as_of.desc()).first())
            if p:
                indicators.append({"code": ind.code, "title": ind.title, "country": ind.country,
                                   "metric": m, "value": float(p.value), "unit": ind.unit,
                                   "as_of": p.as_of.isoformat(), "preliminary": p.is_preliminary})
    meeting = db.query(RateMeeting).order_by(RateMeeting.decision_date.desc()).first()
    rate = None
    if meeting:
        rate = {"decision_date": meeting.decision_date.isoformat(),
                "rate_value": float(meeting.rate_value) if meeting.rate_value else None,
                "signal": meeting.signal, "next_meeting_date": meeting.next_meeting_date.isoformat() if meeting.next_meeting_date else None,
                "consensus_forecast": meeting.consensus_forecast, "press_summary": meeting.press_summary}
    docs = [{"source": d.source, "doc_type": d.doc_type, "title": d.title,
             "summary": d.summary, "key_takeaways": d.key_takeaways}
            for d in db.query(MacroAnalyticsDoc).order_by(MacroAnalyticsDoc.created_at.desc()).limit(12).all()]
    forecast = [{"scenario": f.scenario, "indicator": f.indicator, "year": f.year, "value": f.value}
                for f in db.query(MacroForecast).order_by(MacroForecast.as_of.desc()).limit(40).all()]
    return {"indicators": indicators, "rate": rate, "analytics": docs,
            "cb_forecast": forecast, "sectors": _sectors_list()}


def generate(db: Session) -> MacroInterpretation:
    """Сгенерировать интерпретацию (Pro reasoning) и сохранить срез."""
    snapshot = gather_snapshot(db)
    system = _methodology() + _OUTPUT_SPEC
    user = ("Данные платформы на текущий момент (используй конкретные значения):\n\n"
            + json.dumps(snapshot, ensure_ascii=False, indent=1))
    model = llm.pro_model()
    # max_tokens поднят с 8192: новый структурированный scenarios (3 сценария × 3 поля)
    # добавил объём, и с thinking=True рассуждение тоже расходует общий бюджет —
    # раньше не хватало на последний ключ scenarios, JSON приходил валидным, но без него.
    out = llm.complete(system, user, json_mode=True, thinking=True,
                       model=model, max_tokens=16000, temperature=0.4)
    sections = out.get("sections") if isinstance(out, dict) else None
    if not sections:
        raise llm.LLMError("Интерпретатор: модель не вернула sections")
    row = MacroInterpretation(
        sections=sections, generated_at=datetime.now(timezone.utc),
        model_used=f"{llm.provider_info().get('provider')}:{model}",
        source_snapshot={"indicators_count": len(snapshot["indicators"]),
                         "has_rate": bool(snapshot["rate"]), "docs": len(snapshot["analytics"])})
    db.add(row)
    db.commit()
    db.refresh(row)
    logger.info("Интерпретатор: сгенерирован срез #%d (%s)", row.id, row.model_used)
    return row


def get_latest(db: Session) -> MacroInterpretation | None:
    return db.query(MacroInterpretation).order_by(MacroInterpretation.generated_at.desc()).first()

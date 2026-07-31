"""Живая подмена канонических макро-значений в macro.json НА ОТДАЧЕ.

Владелец 2026-08-01 (кейс Северстали): на вкладке «Макро» живая плашка уже
показывает ставку 14%, а структурный блок snapshot из macro.json рядом — 14,25%
(«снижена 19 июня, следующее заседание 24 июля»् — заседание давно прошло).
snapshot запекается агентом при генерации карточки и НЕ обновляется никем; проза
чинится патчером, а этот слой оставался застывшим.

Паттерн — тот же, что live_scale_multiples: НЕ хранить исправление (файлы на
Timeweb эфемерны, БД-оверлей для JSON — отдельная сущность), а подменять при
отдаче от живых рядов macro_data_points. Идемпотентно, мгновенно для всех ~264
карточек, переживает деплой.

Подменяются ТОЛЬКО канонические общерыночные индикаторы, которые мы ведём живыми
рядами и однозначно узнаём по названию: ключевая ставка, инфляция г/г,
инфляционные ожидания, курс USD/RUB. Компанийно-специфичные строки snapshot
(цена проката, потребление стали) не трогаются — их источник правды в карточке.
"""
from __future__ import annotations

import logging
import re
from datetime import date

logger = logging.getLogger(__name__)

# (regex названия индикатора, ключ живого значения)
_CANON = [
    (re.compile(r"ключев\w+\s+ставк", re.I), "key_rate"),
    (re.compile(r"инфляционн\w+\s+ожидани", re.I), "expectations"),
    (re.compile(r"инфляци", re.I), "inflation"),          # после ожиданий (частный случай раньше общего)
    (re.compile(r"USD\s*/?\s*RUB|курс\s+доллар|доллар.*рубл", re.I), "usdrub"),
]


def _live_values(db) -> dict:
    from sqlalchemy import text as _sql
    out: dict = {}
    for code, metric, key in (("key_rate", "level", "key_rate"),
                              ("inflation", "yoy", "inflation"),
                              ("inflation_expectations", "level", "expectations"),
                              ("usdrub", "level", "usdrub")):
        try:
            row = db.execute(_sql(
                "SELECT value, as_of FROM macro_data_points WHERE indicator_code=:c "
                "AND metric=:m ORDER BY as_of DESC LIMIT 1"), {"c": code, "m": metric}).first()
            if row:
                out[key] = (float(row[0]), row[1])
        except Exception:  # noqa: BLE001
            pass
    return out


def _fmt(v: float, key: str) -> str:
    s = f"{v:.2f}".rstrip("0").rstrip(".").replace(".", ",")
    return f"{s} ₽" if key == "usdrub" else f"{s}%"


def enrich_snapshot_live(db, data: dict) -> dict:
    """Мутирует data.snapshot: канонические индикаторы получают живое value +
    пометку. Ошибки не выпускает наружу — отдача карточки важнее подмены."""
    try:
        snap = data.get("snapshot")
        if not isinstance(snap, list):
            return data
        live = _live_values(db)
        if not live:
            return data
        today = date.today()
        for item in snap:
            if not isinstance(item, dict):
                continue
            name = str(item.get("indicator") or "")
            for rx, key in _CANON:
                if not rx.search(name):
                    continue
                if key not in live:
                    break
                val, as_of = live[key]
                new_val = _fmt(val, key)
                old_val = str(item.get("value") or "")
                if old_val.replace(" ", "") != new_val.replace(" ", ""):
                    item["value"] = new_val
                    item["live_updated"] = as_of.isoformat()
                    item["stale_value"] = old_val
                    # trend_note с датами прошлых заседаний при устаревшем value
                    # вводит в заблуждение сильнее, чем его отсутствие
                    note = str(item.get("trend_note") or "")
                    if note and re.search(r"\d{1,2}\s+[а-я]+|\d{2}\.\d{2}", note):
                        item["trend_note"] = f"актуально на {as_of.strftime('%d.%m.%Y')}"
                break
        data["snapshot_live_at"] = today.isoformat()
    except Exception:  # noqa: BLE001
        logger.warning("macro snapshot live-подмена не удалась", exc_info=True)
    return data

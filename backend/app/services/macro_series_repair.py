"""Разовый ремонт рядов, где метрика была записана неверно.

🔴 Владелец, 2026-08-18: «рост M2 странный — то 10 процентов, то 1, это бред; у
госрасходов старые числа из моей таблицы, надо перепроверить».

Что было. В `csv_mapping` столбцы таблицы владельца M2 / Government_spending_growth /
GDP_m стояли с метрикой `level`, хотя содержат ПРИРОСТЫ (месячный, годовой, месячный).
В итоге в ряду `m2/level` лежали два разных показателя сразу: месячные приросты из файла
(−3,4…6,3%) и годовые из релизов ЦБ (9,7 и 13,2%). Витрина показывала их одним рядом —
отсюда «то 10, то 1». У `gov_spending_growth` та же болезнь плюс вторая: годовое значение
было РАЗМАЗАНО по всем двенадцати месяцам года (десять серий по 12 одинаковых чисел), то
есть выглядело как месячный ряд, не будучи им.

Ремонт идемпотентный: точки переносятся в правильную метрику, размазанные годовые
сворачиваются в одну декабрьскую, дубликаты удаляются. Запускать можно повторно —
второй прогон ничего не найдёт.
"""
from __future__ import annotations

import logging
from collections import defaultdict

from sqlalchemy import text
from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)

# код → (источник, из какой метрики, в какую). Источник различает происхождение точек:
# файл владельца и релизы ЦБ/Минфина несут РАЗНЫЕ показатели под одним кодом.
_MOVES = [
    ("m2", "cb_model file", "level", "mom"),
    ("m2", "ЦБ РФ", "level", "yoy"),
    ("gov_spending_growth", "cb_model file", "level", "yoy"),
    ("gov_spending_growth", "Минфин России", "level", "yoy"),
]


def _move(db: Session, code: str, source: str, frm: str, to: str) -> int:
    """Перенести точки в правильную метрику, не создавая дублей."""
    rows = db.execute(text(
        "SELECT id, as_of FROM macro_data_points WHERE indicator_code=:c "
        "AND metric=:f AND source=:s"), {"c": code, "f": frm, "s": source}).fetchall()
    moved = 0
    for pid, as_of in rows:
        busy = db.execute(text(
            "SELECT 1 FROM macro_data_points WHERE indicator_code=:c AND metric=:m "
            "AND as_of=:d"), {"c": code, "m": to, "d": as_of}).first()
        if busy:
            db.execute(text("DELETE FROM macro_data_points WHERE id=:i"), {"i": pid})
        else:
            db.execute(text("UPDATE macro_data_points SET metric=:m WHERE id=:i"),
                       {"m": to, "i": pid})
        moved += 1
    return moved


def _collapse_smeared_annual(db: Session, code: str, metric: str) -> int:
    """Схлопнуть годовое значение, размазанное по месяцам, в одну точку за год.

    Признак: внутри календарного года ВСЕ значения одинаковы и их больше трёх. Такой
    «месячный ряд» не несёт месячной информации — он вводит в заблуждение и ломает любой
    расчёт динамики. Оставляем декабрьскую точку (конец года), остальные удаляем.
    """
    rows = db.execute(text(
        "SELECT id, as_of, value FROM macro_data_points WHERE indicator_code=:c "
        "AND metric=:m ORDER BY as_of"), {"c": code, "m": metric}).fetchall()
    by_year: dict[int, list] = defaultdict(list)
    for pid, as_of, val in rows:
        by_year[as_of.year].append((pid, as_of, float(val)))
    removed = 0
    for year, pts in by_year.items():
        vals = {round(v, 6) for _, _, v in pts}
        if len(pts) < 4 or len(vals) != 1:
            continue
        keep = max(pts, key=lambda x: x[1])          # последняя дата года
        for pid, _, _ in pts:
            if pid != keep[0]:
                db.execute(text("DELETE FROM macro_data_points WHERE id=:i"), {"i": pid})
                removed += 1
    return removed


def repair(db: Session) -> dict:
    """Полный ремонт. Возвращает отчёт по каждому действию."""
    out: dict = {"moved": {}, "collapsed": {}}
    for code, source, frm, to in _MOVES:
        n = _move(db, code, source, frm, to)
        if n:
            out["moved"][f"{code}:{source}:{frm}→{to}"] = n
    for code, metric in (("gov_spending_growth", "yoy"),):
        n = _collapse_smeared_annual(db, code, metric)
        if n:
            out["collapsed"][f"{code}/{metric}"] = n
    db.commit()
    logger.info("macro_series_repair: %s", out)
    return out

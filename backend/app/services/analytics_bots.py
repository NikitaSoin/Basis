"""Второй слой отсева роботов — по ПОВЕДЕНИЮ, а не по строке браузера.

Зачем второй слой. При записи события мы знаем только User-Agent и флаг
navigator.webdriver. Этого хватает на честных роботов (они себя называют) и не
хватает на всё остальное: обход с подделанным User-Agent выглядит как Chrome.
Именно поэтому наши числа расходились с Метрикой — она классифицирует визит
целиком и постфактум, а мы решали по одному событию в момент записи.

Здесь визит рассматривается ЦЕЛИКОМ, когда он уже закончился, и проверяется то,
что робот не умеет подделать дёшево:
  * ни одного человеческого действия за весь визит (ни скролла, ни клика, ни тапа);
  * страницы пролистываются быстрее, чем их можно прочитать;
  * обход вширь: много разных адресов за один визит без единого возврата назад;
  * визит без источника перехода, начатый не с главной, — типичный заход робота
    прямо в глубокую страницу из индекса.
Каждый признак сам по себе встречается и у людей, поэтому робот объявляется
только при СОВПАДЕНИИ нескольких.

🔴 Мы ПОМЕЧАЕМ, а не удаляем. Ошибочная пометка обратима (переклассифицируем),
удаление — нет. И причина всегда пишется в bot_reason: классификатор, о котором
нельзя спросить «почему», проверить невозможно.
"""
from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone

from sqlalchemy import text
from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)

# Визит считается завершённым через 30 минут после последнего события — так же,
# как его закрывает Метрика. Незакрытые визиты не трогаем: человек может ещё
# вернуться, и «отсутствие действий» пока ничего не доказывает.
VISIT_TIMEOUT_MIN = 30
# Быстрее этого страницу не читают, её пролистывают.
FAST_VIEW_MS = 1500
# Обход вширь: столько разных адресов за визит без единого повтора.
WIDE_SWEEP_PAGES = 8


def reclassify(db: Session, days: int = 3, dry_run: bool = False) -> dict:
    """Пересмотреть завершённые визиты за последние `days` дней.

    Возвращает отчёт: сколько визитов проверили, сколько пометили и по какой причине.
    """
    now = datetime.now(timezone.utc)
    since = now - timedelta(days=days)
    closed_before = now - timedelta(minutes=VISIT_TIMEOUT_MIN)

    # Сводка по каждому завершённому визиту. Считаем в SQL: визитов за сутки тысячи,
    # тянуть события в питон незачем.
    visits = db.execute(text("""
        SELECT session_id,
               MIN(created_at)                                   AS started,
               MAX(created_at)                                   AS ended,
               COUNT(*) FILTER (WHERE kind = 'pageview')         AS views,
               COUNT(DISTINCT path)                              AS uniq_paths,
               COUNT(*) FILTER (WHERE engaged IS TRUE)           AS engaged_events,
               COUNT(*) FILTER (WHERE kind IN ('click','action'))AS actions,
               COUNT(*) FILTER (WHERE referrer IS NOT NULL)      AS with_ref,
               AVG(duration_ms) FILTER (WHERE duration_ms IS NOT NULL) AS avg_dur,
               COUNT(*) FILTER (WHERE duration_ms IS NOT NULL)   AS timed,
               BOOL_OR(is_bot)                                   AS already_bot
        FROM user_events
        WHERE created_at >= :since AND session_id IS NOT NULL
        GROUP BY session_id
        HAVING MAX(created_at) < :closed
    """), {"since": since, "closed": closed_before}).mappings().all()

    verdicts: dict[str, list[str]] = {}
    for v in visits:
        if v["already_bot"]:
            continue                      # уже отсеян первым слоем — не пересматриваем
        signs = []
        no_human = v["engaged_events"] == 0 and v["actions"] == 0
        fast = v["timed"] > 0 and v["avg_dur"] is not None and float(v["avg_dur"]) < FAST_VIEW_MS
        wide = v["views"] >= WIDE_SWEEP_PAGES and v["uniq_paths"] == v["views"]
        no_ref = v["with_ref"] == 0

        if no_human and wide:
            signs.append("обход")         # много разных страниц, ни одного действия
        if no_human and fast and v["views"] >= 3:
            signs.append("быстро")        # листает быстрее, чем читают
        if no_human and no_ref and v["views"] >= 5:
            signs.append("без-источника")

        # Одного признака мало: человек, открывший три вкладки и закрывший их, тоже
        # «не взаимодействовал». Помечаем при совпадении двух и более.
        if len(signs) >= 2:
            verdicts[v["session_id"]] = signs

    if not dry_run and verdicts:
        for sess, signs in verdicts.items():
            db.execute(text(
                "UPDATE user_events SET is_bot = TRUE, bot_reason = :r "
                "WHERE session_id = :s AND (is_bot IS NOT TRUE)"),
                {"r": ("поведение:" + "+".join(signs))[:40], "s": sess})
        db.commit()

    report = {
        "проверено визитов": len(visits),
        "помечено роботами": len(verdicts),
        "dry_run": dry_run,
        "причины": {},
    }
    for signs in verdicts.values():
        key = "+".join(signs)
        report["причины"][key] = report["причины"].get(key, 0) + 1
    logger.info("Ретроспективный отсев роботов: %s", report)
    return report

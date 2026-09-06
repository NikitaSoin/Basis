"""user_events: время на странице, вовлечённость, причина отсева робота

Владелец 2026-09-06: «мне важно, чтобы мы по нашим данным могли посмотреть достоверную
аналитику — на какие страницы приходят, куда идут дальше, сколько времени проводят, и
уметь достоверно выкидывать роботов». Сейчас по логу нельзя посчитать НИ ОДНУ из этих
величин: событие фиксирует только факт просмотра.

Что добавляем и зачем именно так:
* duration_ms  — сколько просмотр прожил от показа до ухода. Без него «время на сайте»
                 считается разностью между соседними событиями, и последний просмотр
                 визита (самый интересный — на нём человек ушёл) всегда даёт ноль.
                 Именно так Метрика и расходится с нами в среднем времени.
* visible_ms   — сколько страница была РЕАЛЬНО видима (вкладка активна). Открытая в
                 фоне вкладка иначе накручивает часы просмотра.
* engaged      — было ли хоть одно человеческое действие (скролл, клик, клавиша, тап).
                 Это и метрика качества визита (отказ), и сильный признак робота:
                 headless-обход не скроллит.
* bot_reason   — причина классификации отдельной колонкой, а не в meta. В meta её
                 нельзя ни проиндексировать, ни быстро сгруппировать, а вопрос «кого и
                 почему мы отсеяли» задаётся при каждом расхождении с Метрикой.

Индекс по (session_id, created_at) — визит собирается именно так: все события сессии по
порядку. Без него агрегаты по визитам будут читать таблицу целиком.

Revision ID: f7a2c93e1b54
Revises: e1c9a7b34d68
"""
from alembic import op
import sqlalchemy as sa


revision = "f7a2c93e1b54"
down_revision = "e1c9a7b34d68"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # NULL везде намеренно: строки, записанные до этой миграции, времени не несут.
    # Ноль вместо NULL означал бы «человек ушёл мгновенно» и занизил бы среднее.
    op.add_column("user_events", sa.Column("duration_ms", sa.Integer, nullable=True))
    op.add_column("user_events", sa.Column("visible_ms", sa.Integer, nullable=True))
    op.add_column("user_events", sa.Column("engaged", sa.Boolean, nullable=True))
    op.add_column("user_events", sa.Column("bot_reason", sa.String(40), nullable=True))
    op.create_index("ix_user_events_session_time", "user_events", ["session_id", "created_at"])


def downgrade() -> None:
    op.drop_index("ix_user_events_session_time", table_name="user_events")
    op.drop_column("user_events", "bot_reason")
    op.drop_column("user_events", "engaged")
    op.drop_column("user_events", "visible_ms")
    op.drop_column("user_events", "duration_ms")

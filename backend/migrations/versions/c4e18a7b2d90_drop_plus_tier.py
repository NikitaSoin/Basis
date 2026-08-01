"""drop_plus_tier — убрать тариф "plus" из enum subscriptiontype

Владелец (2026-08-01): «пусть останется один тариф Max, без Плюс» и затем «клиентов
нет, записей никаких нет, поэтому удалить можно». Тарифов теперь два: free и premium
(в UI — «Бесплатный» и «Max», см. frontend/Basis/src/account/tierCatalog.js).

🔴 Миграция САМОБЕЗОПАСНА и не полагается на предположение «plus-записей нет»:
ПЕРЕД удалением значения переводит все возможные plus-строки в premium. Plus стоил
390 ₽ — ровно столько же теперь стоит Max, и Max включает всё, что было в Plus, так
что такой перевод никого не ущемляет. Если бы миграция просто дропала значение при
живой строке, PostgreSQL уронил бы весь деплой.

PostgreSQL не умеет DROP VALUE у enum — стандартный путь: создать новый тип, перевести
колонку, удалить старый тип, переименовать новый.

Revision ID: c4e18a7b2d90
Revises: b9d3f6a1c284
Create Date: 2026-08-01

"""
from alembic import op

revision = "c4e18a7b2d90"
down_revision = "b9d3f6a1c284"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # 1. Никого не потерять: plus → premium (см. докстринг).
    op.execute("UPDATE users SET subscription_type = 'premium' WHERE subscription_type = 'plus'")
    # 2. Пересобрать enum без "plus".
    # DEFAULT снимаем на время: он типизирован старым enum и ломает USING-каст
    # («default for column cannot be cast automatically» — поймано на прогоне).
    op.execute("ALTER TABLE users ALTER COLUMN subscription_type DROP DEFAULT")
    op.execute("ALTER TYPE subscriptiontype RENAME TO subscriptiontype_old")
    op.execute("CREATE TYPE subscriptiontype AS ENUM ('free', 'premium')")
    op.execute(
        "ALTER TABLE users ALTER COLUMN subscription_type "
        "TYPE subscriptiontype USING subscription_type::text::subscriptiontype"
    )
    op.execute("ALTER TABLE users ALTER COLUMN subscription_type SET DEFAULT 'free'")
    op.execute("DROP TYPE subscriptiontype_old")


def downgrade() -> None:
    # Вернуть значение "plus" в enum. Данные назад не разводим — какие из premium
    # когда-то были plus, после upgrade неизвестно (и это осознанно: их и не было).
    op.execute("ALTER TABLE users ALTER COLUMN subscription_type DROP DEFAULT")
    op.execute("ALTER TYPE subscriptiontype RENAME TO subscriptiontype_old")
    op.execute("CREATE TYPE subscriptiontype AS ENUM ('free', 'plus', 'premium')")
    op.execute(
        "ALTER TABLE users ALTER COLUMN subscription_type "
        "TYPE subscriptiontype USING subscription_type::text::subscriptiontype"
    )
    op.execute("ALTER TABLE users ALTER COLUMN subscription_type SET DEFAULT 'free'")
    op.execute("DROP TYPE subscriptiontype_old")

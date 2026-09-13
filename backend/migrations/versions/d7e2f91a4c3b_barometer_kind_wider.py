"""barometer_versions.kind: String(8) → String(16)

Пункт 2 плана владельца (2026-09-13): в ту же таблицу версий ложатся состояния
макроэкономики (kind="macro") и институциональной среды (kind="inst_state").
Второе не помещается в восемь символов, а сокращать имя до «instst» — значит
заложить в схему загадку для следующей сессии.

Revision ID: d7e2f91a4c3b
Revises: e5c17a934b82
"""
import sqlalchemy as sa
from alembic import op

revision = "d7e2f91a4c3b"
down_revision = "e5c17a934b82"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.alter_column("barometer_versions", "kind", type_=sa.String(16),
                    existing_type=sa.String(8), existing_nullable=True)


def downgrade() -> None:
    op.alter_column("barometer_versions", "kind", type_=sa.String(8),
                    existing_type=sa.String(16), existing_nullable=True)

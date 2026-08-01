"""Попытки закрыть вопрос к данным — чтобы неподдающиеся отступали из очереди.

Без этого очередь встаёт колом: часть дыр не закрывается в принципе (Росстат режет
машинный доступ, китайские ряды за платным терминалом), а лимит раунда маленький —
«вечные» вопросы съедали его целиком, и решаемые до агента не доходили.
"""
import sqlalchemy as sa
from alembic import op

revision = "e7c2b1a45d90"
down_revision = "b2d7f4c19a83"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "macro_question_attempts",
        sa.Column("code", sa.String(), primary_key=True),
        sa.Column("fails", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("last_try", sa.DateTime(timezone=True), nullable=True),
    )


def downgrade():
    op.drop_table("macro_question_attempts")

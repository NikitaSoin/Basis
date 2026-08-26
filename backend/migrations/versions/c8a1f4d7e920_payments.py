"""payments — журнал платежей интернет-эквайринга Т-Бизнеса

Владелец 2026-08-26: «настраиваю интернет-эквайринг, твоя задача всё подключить».
Своя таблица нужна ради идемпотентности: банк повторяет нотификацию, пока не
получит "OK", и без отметки о начислении подписка продлевалась бы на каждую
повторную доставку. См. app/models/payment.py.

Revision ID: c8a1f4d7e920
Revises: b6d41f8a2c07
Create Date: 2026-08-26

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "c8a1f4d7e920"
down_revision = "b6d41f8a2c07"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "payments",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("order_id", sa.String(64), nullable=False),
        sa.Column("payment_id", sa.String(32), nullable=True),
        sa.Column("user_id", sa.Integer(),
                  sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("amount", sa.BigInteger(), nullable=False),
        sa.Column("tier", sa.String(16), nullable=False, server_default="premium"),
        sa.Column("months", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("status", sa.String(32), nullable=False, server_default="NEW"),
        sa.Column("payment_url", sa.String(512), nullable=True),
        sa.Column("error_code", sa.String(16), nullable=True),
        sa.Column("error_message", sa.String(512), nullable=True),
        sa.Column("granted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("raw", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True),
                  server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True),
                  server_default=sa.text("now()"), nullable=False),
    )
    op.create_index("ix_payments_order_id", "payments", ["order_id"], unique=True)
    op.create_index("ix_payments_payment_id", "payments", ["payment_id"])
    op.create_index("ix_payments_user_id", "payments", ["user_id"])
    op.create_index("ix_payments_status", "payments", ["status"])


def downgrade() -> None:
    op.drop_index("ix_payments_status", table_name="payments")
    op.drop_index("ix_payments_user_id", table_name="payments")
    op.drop_index("ix_payments_payment_id", table_name="payments")
    op.drop_index("ix_payments_order_id", table_name="payments")
    op.drop_table("payments")

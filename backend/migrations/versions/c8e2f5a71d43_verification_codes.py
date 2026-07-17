"""verification_codes — коды подтверждения email (и в будущем SMS) при регистрации

Revision ID: c8e2f5a71d43
Revises: b7d1e4f2a950
Create Date: 2026-07-18

"""
from alembic import op
import sqlalchemy as sa

revision = "c8e2f5a71d43"
down_revision = "b7d1e4f2a950"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "verification_codes",
        sa.Column("id", sa.Integer(), primary_key=True),
        # канал доставки: email | sms (sms — задел, отправка появится с провайдером)
        sa.Column("channel", sa.String(length=8), nullable=False, server_default="email"),
        # адрес назначения: email или телефон в нормализованном виде
        sa.Column("destination", sa.String(length=255), nullable=False),
        # назначение кода: register | ... (задел под смену email/пароля)
        sa.Column("purpose", sa.String(length=24), nullable=False, server_default="register"),
        # sha256 кода — сам код нигде не хранится
        sa.Column("code_hash", sa.String(length=64), nullable=False),
        sa.Column("attempts", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.text("now()")),
    )
    op.create_index("ix_verification_codes_destination", "verification_codes",
                    ["destination", "purpose"])


def downgrade() -> None:
    op.drop_index("ix_verification_codes_destination", table_name="verification_codes")
    op.drop_table("verification_codes")

"""companies.shares_outstanding (капитализация = живая цена × число акций)

Revision ID: a1c5e8b740d3
Revises: f4b1d8e3a902
Create Date: 2026-06-17

"""
from alembic import op
import sqlalchemy as sa

revision = "a1c5e8b740d3"
down_revision = "f4b1d8e3a902"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("companies", sa.Column("shares_outstanding", sa.BigInteger(), nullable=True))


def downgrade() -> None:
    op.drop_column("companies", "shares_outstanding")

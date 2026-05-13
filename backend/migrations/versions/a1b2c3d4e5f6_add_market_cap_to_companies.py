"""add_market_cap_to_companies

Revision ID: a1b2c3d4e5f6
Revises: 628d6f53223e
Create Date: 2026-05-13 12:00:00.000000

"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa

revision: str = 'a1b2c3d4e5f6'
down_revision: Union[str, None] = '628d6f53223e'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('companies', sa.Column('market_cap', sa.Numeric(20, 2), nullable=True))


def downgrade() -> None:
    op.drop_column('companies', 'market_cap')

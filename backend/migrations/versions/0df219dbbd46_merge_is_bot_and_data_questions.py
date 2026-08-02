"""слияние веток: is_bot и попытки закрытия вопросов

Revision ID: 0df219dbbd46
Revises: c3a8e5f27b41, e7c2b1a45d90
Create Date: 2026-08-02 11:50:26.688676

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '0df219dbbd46'
down_revision: Union[str, None] = ('c3a8e5f27b41', 'e7c2b1a45d90')
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass

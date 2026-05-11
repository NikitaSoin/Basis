"""add_subscription_fields_to_users

Revision ID: 628d6f53223e
Revises: 33a656bd8176
Create Date: 2026-05-11 22:44:33.232334

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = '628d6f53223e'
down_revision: Union[str, None] = '33a656bd8176'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

subscription_enum = sa.Enum('free', 'premium', name='subscriptiontype')


def upgrade() -> None:
    subscription_enum.create(op.get_bind(), checkfirst=True)
    op.add_column('users', sa.Column(
        'subscription_type',
        sa.Enum('free', 'premium', name='subscriptiontype'),
        nullable=False,
        server_default='free',
    ))
    op.add_column('users', sa.Column('subscription_expires_at', sa.DateTime(timezone=True), nullable=True))


def downgrade() -> None:
    op.drop_column('users', 'subscription_expires_at')
    op.drop_column('users', 'subscription_type')
    subscription_enum.drop(op.get_bind(), checkfirst=True)

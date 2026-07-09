"""macro expert survey (опрос профессиональных аналитиков ЦБ)

Revision ID: b3e7a1f9c204
Revises: a8d4f2c7b391
Create Date: 2026-07-09

MacroExpertSurvey — медианные прогнозы независимых аналитиков (ежемесячный
опрос Банка России, cbr.ru/statistics/ddkp/mo_br/), отдельно от MacroForecast
(сценарии самого ЦБ).
"""
from alembic import op
import sqlalchemy as sa

revision = "b3e7a1f9c204"
down_revision = "a8d4f2c7b391"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "macro_expert_surveys",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("as_of", sa.Date(), nullable=False),
        sa.Column("indicator", sa.String(length=80), nullable=False),
        sa.Column("year", sa.Integer(), nullable=False),
        sa.Column("value", sa.String(length=48)),
        sa.Column("n_respondents", sa.Integer()),
        sa.Column("source_url", sa.String(length=1000)),
        sa.Column("created_at", sa.DateTime(timezone=True)),
        sa.UniqueConstraint("as_of", "indicator", "year", name="uq_macro_expert_survey"),
    )


def downgrade():
    op.drop_table("macro_expert_surveys")

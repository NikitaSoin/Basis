"""geo_strike_events + geo_territorial_claims — автоизвлечение из geo_digest

Владелец (2026-07-24): удары вглубь России/Украины должны помечаться на
карте АВТОМАТИЧЕСКИ из общего потока контента платформы (RSS/телеграм уже
подключены через geo_digest.py), малозначимые — со временем удаляться,
значимые — держаться дольше. Плюс задел на то, чтобы смена контроля
насел. пунктов (Рыбарь/ISW-производные статьи) тоже извлекалась
автоматически, не только выделенным скриптом geo_svo_wikipedia_dates.py.

Revision ID: 9e5c10b0c99c
Revises: 7858a628994c
Create Date: 2026-07-25

"""
from alembic import op
import sqlalchemy as sa

revision = "9e5c10b0c99c"
down_revision = "7858a628994c"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "geo_strike_events",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("theater", sa.String(length=16), nullable=False),
        sa.Column("location_name", sa.String(length=200), nullable=False),
        sa.Column("lat", sa.Float(), nullable=True),
        sa.Column("lon", sa.Float(), nullable=True),
        sa.Column("target_type", sa.String(length=120), nullable=True),
        sa.Column("significance", sa.String(length=16), nullable=False),
        sa.Column("label", sa.String(length=300), nullable=False),
        sa.Column("note", sa.Text(), nullable=True),
        sa.Column("event_date", sa.Date(), nullable=True),
        sa.Column("source_key", sa.String(length=32), nullable=True),
        sa.Column("source_url", sa.String(length=1000), nullable=True),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
    )
    op.create_index("ix_geo_strike_events_theater", "geo_strike_events", ["theater"])
    op.create_index("ix_geo_strike_events_expires_at", "geo_strike_events", ["expires_at"])

    op.create_table(
        "geo_territorial_claims",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("settlement", sa.String(length=200), nullable=False),
        sa.Column("oblast", sa.String(length=120), nullable=True),
        sa.Column("lat", sa.Float(), nullable=True),
        sa.Column("lon", sa.Float(), nullable=True),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("note", sa.Text(), nullable=True),
        sa.Column("claimed_date", sa.Date(), nullable=True),
        sa.Column("source_key", sa.String(length=32), nullable=True),
        sa.Column("source_url", sa.String(length=1000), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.UniqueConstraint("settlement", "oblast", name="uq_geo_territorial_claim_settlement"),
    )


def downgrade() -> None:
    op.drop_table("geo_territorial_claims")
    op.drop_index("ix_geo_strike_events_expires_at", table_name="geo_strike_events")
    op.drop_index("ix_geo_strike_events_theater", table_name="geo_strike_events")
    op.drop_table("geo_strike_events")

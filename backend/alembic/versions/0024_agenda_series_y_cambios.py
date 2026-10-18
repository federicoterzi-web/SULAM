"""Agenda: actividades repetidas (series) e historial de cambios.

Revision ID: 0024
Revises: 0023
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0024"
down_revision = "0023"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("agenda_eventos", sa.Column("serie_id", sa.Uuid()))
    op.add_column("agenda_eventos", sa.Column("repeticion", sa.String(12)))
    op.create_index("ix_agenda_eventos_serie", "agenda_eventos", ["serie_id"])
    op.create_table(
        "agenda_cambios",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("evento_id", sa.Uuid(), sa.ForeignKey("agenda_eventos.id", ondelete="CASCADE"), nullable=False),
        sa.Column("usuario_id", sa.Uuid(), sa.ForeignKey("usuarios.id"), nullable=False),
        sa.Column("en", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("cambios", postgresql.JSONB(), nullable=False),
        sa.Column("motivo", sa.Text()),
    )
    op.create_index("ix_agenda_cambios_evento", "agenda_cambios", ["evento_id"])


def downgrade() -> None:
    op.drop_table("agenda_cambios")
    op.drop_index("ix_agenda_eventos_serie", table_name="agenda_eventos")
    op.drop_column("agenda_eventos", "repeticion")
    op.drop_column("agenda_eventos", "serie_id")

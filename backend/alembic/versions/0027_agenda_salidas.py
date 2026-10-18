"""Salidas de visita: las paradas de una salida guardada quedan unidas, con su orden.

Revision ID: 0027
Revises: 0026
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0027"
down_revision = "0026"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("agenda_eventos", sa.Column("salida_id", sa.Uuid()))
    op.add_column("agenda_eventos", sa.Column("salida_orden", sa.SmallInteger()))
    op.create_index("ix_agenda_eventos_salida", "agenda_eventos", ["salida_id"])


def downgrade() -> None:
    op.drop_index("ix_agenda_eventos_salida", table_name="agenda_eventos")
    op.drop_column("agenda_eventos", "salida_orden")
    op.drop_column("agenda_eventos", "salida_id")

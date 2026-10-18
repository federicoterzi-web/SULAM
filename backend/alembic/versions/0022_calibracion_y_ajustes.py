"""Ajustes del sistema y registro de calibración del reconocimiento automático.

Revision ID: 0022
Revises: 0021
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0022"
down_revision = "0021"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "ajustes",
        sa.Column("clave", sa.String(60), primary_key=True),
        sa.Column("valor", postgresql.JSONB(), nullable=False),
    )
    op.create_table(
        "calibracion_casos",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("creado_en", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("campo", sa.String(30), nullable=False),
        sa.Column("resultado", sa.String(20), nullable=False),
        sa.Column("tipo_documental", sa.String(200)),
        sa.Column("detalle", postgresql.JSONB(), server_default=sa.text("'{}'::jsonb"), nullable=False),
        sa.Column("fragmento", sa.Text()),
    )


def downgrade() -> None:
    op.drop_table("calibracion_casos")
    op.drop_table("ajustes")

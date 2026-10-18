"""Foto de la persona (recortada del DNI) y tipos documentales requeridos en casos abiertos.

Revision ID: 0031
Revises: 0030
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0031"
down_revision = "0030"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("personas", sa.Column("foto", sa.LargeBinary()))
    op.add_column("personas", sa.Column("foto_en", sa.DateTime(timezone=True)))
    op.add_column("personas", sa.Column("foto_por", postgresql.UUID(as_uuid=True), sa.ForeignKey("usuarios.id")))
    op.add_column("personas", sa.Column("foto_documento_id", postgresql.UUID(as_uuid=True)))
    op.add_column("tipos_documentales", sa.Column("requerido_en_caso_abierto", sa.Boolean(), server_default=sa.text("false"), nullable=False))


def downgrade() -> None:
    op.drop_column("tipos_documentales", "requerido_en_caso_abierto")
    for c in ("foto_documento_id", "foto_por", "foto_en", "foto"):
        op.drop_column("personas", c)

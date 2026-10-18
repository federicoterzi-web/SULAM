"""Texto leído de cada documento, para buscarlo y resaltarlo.

Revision ID: 0021
Revises: 0020
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0021"
down_revision = "0020"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("documentos", sa.Column("texto", sa.Text()))
    op.add_column("documentos", sa.Column("texto_busqueda", sa.Text()))
    op.add_column("documentos", sa.Column("texto_estado", sa.String(12), server_default="pendiente", nullable=False))
    op.add_column("documentos", sa.Column("texto_leido_en", sa.DateTime(timezone=True)))
    op.execute("CREATE INDEX ix_documentos_texto_busqueda ON documentos USING gin (to_tsvector('simple', coalesce(texto_busqueda, '')))")


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS ix_documentos_texto_busqueda")
    for c in ("texto_leido_en", "texto_estado", "texto_busqueda", "texto"):
        op.drop_column("documentos", c)

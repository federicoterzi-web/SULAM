"""Captura de documentos con el celular: bandeja de fotos, plantillas de tipos documentales y vencimientos.

Revision ID: 0020
Revises: 0019
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0020"
down_revision = "0019"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Plantilla del tipo documental.
    op.add_column("tipos_documentales", sa.Column("descripcion", sa.Text()))
    op.add_column("tipos_documentales", sa.Column("tiene_vencimiento", sa.Boolean(), server_default=sa.text("false"), nullable=False))
    op.add_column("tipos_documentales", sa.Column("vigencia_dias", sa.Integer()))
    op.add_column("tipos_documentales", sa.Column("usa_numero", sa.Boolean(), server_default=sa.text("false"), nullable=False))
    op.add_column("tipos_documentales", sa.Column("campos", postgresql.JSONB(), server_default=sa.text("'[]'::jsonb"), nullable=False))
    op.add_column("tipos_documentales", sa.Column("creado_por", sa.Uuid(), sa.ForeignKey("usuarios.id")))
    # Datos propios de cada documento según su tipo.
    op.add_column("documentos", sa.Column("fecha_emision", sa.Date()))
    op.add_column("documentos", sa.Column("vence", sa.Date()))
    op.add_column("documentos", sa.Column("numero", sa.String(100)))
    op.add_column("documentos", sa.Column("datos", postgresql.JSONB(), server_default=sa.text("'{}'::jsonb"), nullable=False))
    op.create_index("ix_documentos_vence", "documentos", ["vence"])
    # Fotos sacadas con el celular que esperan ser clasificadas (bandeja de cada persona).
    op.create_table(
        "capturas_paginas",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("usuario_id", sa.Uuid(), sa.ForeignKey("usuarios.id"), nullable=False, index=True),
        sa.Column("mime", sa.String(50), nullable=False),
        sa.Column("tamano", sa.BigInteger(), nullable=False),
        sa.Column("sha256", sa.String(64), nullable=False),
        sa.Column("almacenamiento", sa.String(30), nullable=False),
        sa.Column("clave_almacenamiento", sa.String(300), nullable=False),
        sa.Column("estado", sa.String(20), server_default="pendiente", nullable=False),
        sa.Column("documento_id", sa.Uuid(), sa.ForeignKey("documentos.id")),
        sa.Column("creada_en", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.CheckConstraint("estado IN ('pendiente','clasificada','descartada')", name="ck_captura_pagina_estado"),
    )


def downgrade() -> None:
    op.drop_table("capturas_paginas")
    op.drop_index("ix_documentos_vence", table_name="documentos")
    for c in ("datos", "numero", "vence", "fecha_emision"):
        op.drop_column("documentos", c)
    for c in ("creado_por", "campos", "usa_numero", "vigencia_dias", "tiene_vencimiento", "descripcion"):
        op.drop_column("tipos_documentales", c)

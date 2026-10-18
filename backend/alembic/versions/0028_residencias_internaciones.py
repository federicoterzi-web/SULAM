"""Documentación de residencias e internaciones de personas.

Revision ID: 0028
Revises: 0027
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0028"
down_revision = "0027"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "recursos_documentos",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("recurso_id", sa.Uuid(), sa.ForeignKey("recursos.id", ondelete="CASCADE"), nullable=False),
        sa.Column("tipo", sa.String(40), nullable=False),
        sa.Column("numero", sa.String(100)),
        sa.Column("fecha_emision", sa.Date()),
        sa.Column("vence", sa.Date()),
        sa.Column("observaciones", sa.Text()),
        sa.Column("nombre", sa.String(300)),
        sa.Column("mime", sa.String(100)),
        sa.Column("tamano", sa.BigInteger()),
        sa.Column("sha256", sa.String(64)),
        sa.Column("almacenamiento", sa.String(30)),
        sa.Column("clave_almacenamiento", sa.String(300)),
        sa.Column("creado_por", sa.Uuid(), sa.ForeignKey("usuarios.id")),
        sa.Column("creado_en", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("actualizado_por", sa.Uuid(), sa.ForeignKey("usuarios.id")),
        sa.Column("actualizado_en", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
    )
    op.create_index("ix_recursos_documentos_recurso_id", "recursos_documentos", ["recurso_id"])
    op.create_table(
        "internaciones",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("persona_id", sa.Uuid(), sa.ForeignKey("personas.id"), nullable=False),
        sa.Column("caso_id", sa.Uuid(), sa.ForeignKey("casos.id")),
        sa.Column("recurso_id", sa.Uuid(), sa.ForeignKey("recursos.id")),
        sa.Column("lugar_texto", sa.String(300)),
        sa.Column("modalidad", sa.String(30), server_default="residencia", nullable=False),
        sa.Column("desde", sa.Date(), nullable=False),
        sa.Column("hasta", sa.Date()),
        sa.Column("motivo_egreso", sa.String(30)),
        sa.Column("observaciones", sa.Text()),
        sa.Column("creado_por", sa.Uuid(), sa.ForeignKey("usuarios.id")),
        sa.Column("creado_en", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("actualizado_por", sa.Uuid(), sa.ForeignKey("usuarios.id")),
        sa.Column("actualizado_en", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.CheckConstraint("hasta IS NULL OR hasta >= desde", name="ck_internaciones_fechas"),
        sa.CheckConstraint("recurso_id IS NOT NULL OR lugar_texto IS NOT NULL", name="ck_internaciones_lugar"),
    )
    op.create_index("ix_internaciones_persona_id", "internaciones", ["persona_id"])
    op.create_index("ix_internaciones_recurso_id", "internaciones", ["recurso_id"])
    op.create_index(
        "uq_internaciones_vigente", "internaciones", ["persona_id"], unique=True, postgresql_where=sa.text("hasta IS NULL")
    )


def downgrade() -> None:
    op.drop_table("internaciones")
    op.drop_table("recursos_documentos")

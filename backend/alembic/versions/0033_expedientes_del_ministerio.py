"""Integración con el Sistema de Expedientes del Ministerio de Desarrollo Social.

- tokens_integracion: claves personales para la extensión de Chrome (solo se guarda su SHA-256).
- expedientes_ministerio: copia de lo que la extensión leyó de cada expediente del Ministerio.
- ingresos.pase_ministerio_clave: identifica el pase del Ministerio que originó el ingreso
  (evita cargar dos veces el mismo pase).

Revision ID: 0033
Revises: 0032
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0033"
down_revision = "0032"
branch_labels = None
depends_on = None

UUID = postgresql.UUID(as_uuid=True)
JSONB = postgresql.JSONB


def upgrade() -> None:
    op.create_table(
        "tokens_integracion",
        sa.Column("id", UUID, primary_key=True),
        sa.Column("usuario_id", UUID, sa.ForeignKey("usuarios.id"), nullable=False, index=True),
        sa.Column("nombre", sa.String(100), nullable=False),
        sa.Column("token_hash", sa.String(64), nullable=False, unique=True),
        sa.Column("prefijo", sa.String(16), nullable=False),
        sa.Column("creado_en", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("ultimo_uso_en", sa.DateTime(timezone=True)),
        sa.Column("revocado_en", sa.DateTime(timezone=True)),
    )
    op.create_table(
        "expedientes_ministerio",
        sa.Column("id", UUID, primary_key=True),
        sa.Column("clave", sa.String(40), nullable=False, unique=True),
        sa.Column("numero", sa.Integer(), nullable=False),
        sa.Column("codigo", sa.Integer(), nullable=False),
        sa.Column("letra", sa.String(10), nullable=False),
        sa.Column("anio", sa.Integer(), nullable=False),
        sa.Column("url", sa.String(500)),
        sa.Column("formato", sa.String(30)),
        sa.Column("nomenclador", sa.String(200)),
        sa.Column("asunto", sa.Text()),
        sa.Column("causante", sa.String(300)),
        sa.Column("beneficiario", sa.String(300)),
        sa.Column("documento_beneficiario", sa.String(30), index=True),
        sa.Column("prioridad", sa.String(60)),
        sa.Column("oficina_origen", sa.String(300)),
        sa.Column("fecha_ingreso_ministerio", sa.DateTime(timezone=True)),
        sa.Column("asignado_a", sa.String(100)),
        sa.Column("fecha_asignacion", sa.Date()),
        sa.Column("estado", sa.String(60)),
        sa.Column("oficina_actual", sa.String(300)),
        sa.Column("en_bandeja", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("movimientos", JSONB, nullable=False, server_default=sa.text("'[]'::jsonb")),
        sa.Column("primera_sincronizacion_en", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("ultima_sincronizacion_en", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("sincronizado_por", UUID, sa.ForeignKey("usuarios.id")),
    )
    op.add_column("ingresos", sa.Column("pase_ministerio_clave", sa.String(120)))
    op.create_unique_constraint("uq_ingresos_pase_ministerio", "ingresos", ["pase_ministerio_clave"])
    op.add_column(
        "ingresos",
        sa.Column("expediente_ministerio_id", UUID, sa.ForeignKey("expedientes_ministerio.id")),
    )
    op.create_index("ix_ingresos_expediente_ministerio_id", "ingresos", ["expediente_ministerio_id"])


def downgrade() -> None:
    op.drop_index("ix_ingresos_expediente_ministerio_id", table_name="ingresos")
    op.drop_column("ingresos", "expediente_ministerio_id")
    op.drop_constraint("uq_ingresos_pase_ministerio", "ingresos", type_="unique")
    op.drop_column("ingresos", "pase_ministerio_clave")
    op.drop_table("expedientes_ministerio")
    op.drop_table("tokens_integracion")

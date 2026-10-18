"""Subsidios (residencia, cuidados, alimentarios, materiales), lista de papeles y pagos mensuales.

Revision ID: 0029
Revises: 0028
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0029"
down_revision = "0028"
branch_labels = None
depends_on = None


def _ts(nombre):
    return sa.Column(nombre, sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False)


def upgrade() -> None:
    op.create_table(
        "subsidios",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("persona_id", sa.Uuid(), sa.ForeignKey("personas.id"), nullable=False),
        sa.Column("caso_id", sa.Uuid(), sa.ForeignKey("casos.id")),
        sa.Column("expediente_id", sa.Uuid(), sa.ForeignKey("expedientes.id")),
        sa.Column("internacion_id", sa.Uuid(), sa.ForeignKey("internaciones.id")),
        sa.Column("tipo", sa.String(20), nullable=False),
        sa.Column("estado", sa.String(20), server_default="en_tramite", nullable=False),
        sa.Column("recurso_id", sa.Uuid(), sa.ForeignKey("recursos.id")),
        sa.Column("prestador_texto", sa.String(300)),
        sa.Column("solicitante_nombre", sa.String(200)),
        sa.Column("solicitante_dni", sa.String(20)),
        sa.Column("solicitante_vinculo", sa.String(100)),
        sa.Column("solicitante_telefono", sa.String(100)),
        sa.Column("horas_semanales", sa.Numeric(5, 1)),
        sa.Column("detalle", sa.Text()),
        sa.Column("monto_mensual", sa.Numeric(12, 2)),
        sa.Column("fecha_solicitud", sa.Date()),
        sa.Column("fecha_elevacion", sa.Date()),
        sa.Column("resolucion_numero", sa.String(100)),
        sa.Column("resolucion_fecha", sa.Date()),
        sa.Column("desde", sa.Date()),
        sa.Column("hasta", sa.Date()),
        sa.Column("observaciones", sa.Text()),
        sa.Column("creado_por", sa.Uuid(), sa.ForeignKey("usuarios.id")),
        _ts("creado_en"),
        sa.Column("actualizado_por", sa.Uuid(), sa.ForeignKey("usuarios.id")),
        _ts("actualizado_en"),
        sa.CheckConstraint("hasta IS NULL OR desde IS NULL OR hasta >= desde", name="ck_subsidios_fechas"),
    )
    for c in ("persona_id", "tipo", "estado", "recurso_id"):
        op.create_index(f"ix_subsidios_{c}", "subsidios", [c])
    op.create_table(
        "subsidio_pagos",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("subsidio_id", sa.Uuid(), sa.ForeignKey("subsidios.id", ondelete="CASCADE"), nullable=False),
        sa.Column("periodo", sa.Date(), nullable=False),
        sa.Column("monto", sa.Numeric(12, 2)),
        sa.Column("estado", sa.String(25), server_default="pendiente", nullable=False),
        sa.Column("fecha_pago", sa.Date()),
        sa.Column("comprobante", sa.String(100)),
        sa.Column("observaciones", sa.Text()),
        sa.Column("creado_por", sa.Uuid(), sa.ForeignKey("usuarios.id")),
        _ts("creado_en"),
        sa.Column("actualizado_por", sa.Uuid(), sa.ForeignKey("usuarios.id")),
        _ts("actualizado_en"),
    )
    op.create_index("ix_subsidio_pagos_subsidio_id", "subsidio_pagos", ["subsidio_id"])
    op.create_index("ix_subsidio_pagos_periodo", "subsidio_pagos", ["periodo"])
    op.create_index("uq_subsidio_pago_periodo", "subsidio_pagos", ["subsidio_id", "periodo"], unique=True)
    op.create_table(
        "subsidio_requisitos",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("subsidio_id", sa.Uuid(), sa.ForeignKey("subsidios.id", ondelete="CASCADE"), nullable=False),
        sa.Column("pago_id", sa.Uuid(), sa.ForeignKey("subsidio_pagos.id", ondelete="CASCADE")),
        sa.Column("grupo", sa.String(20), nullable=False),
        sa.Column("codigo", sa.String(40)),
        sa.Column("texto", sa.Text(), nullable=False),
        sa.Column("estado", sa.String(20), server_default="pendiente", nullable=False),
        sa.Column("fecha_presentado", sa.Date()),
        sa.Column("observaciones", sa.Text()),
        sa.Column("orden", sa.SmallInteger(), server_default="0", nullable=False),
        sa.Column("actualizado_por", sa.Uuid(), sa.ForeignKey("usuarios.id")),
        _ts("actualizado_en"),
    )
    op.create_index("ix_subsidio_requisitos_subsidio_id", "subsidio_requisitos", ["subsidio_id"])
    op.create_index("ix_subsidio_requisitos_pago_id", "subsidio_requisitos", ["pago_id"])


def downgrade() -> None:
    op.drop_table("subsidio_requisitos")
    op.drop_table("subsidio_pagos")
    op.drop_table("subsidios")

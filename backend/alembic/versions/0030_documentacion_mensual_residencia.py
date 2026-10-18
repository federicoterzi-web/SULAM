"""La documentación mensual de la institución se carga una vez por residencia y por mes.

Revision ID: 0030
Revises: 0029
"""
from __future__ import annotations

import uuid

import sqlalchemy as sa
from alembic import op

revision = "0030"
down_revision = "0029"
branch_labels = None
depends_on = None

INSTITUCION = [
    ("m_nota_reintegro", "Nota de pedido de reintegro con el monto y los datos completos de los residentes"),
    ("m_habilitacion", "Habilitación del SIPROSA"),
    ("m_categorizacion", "Categorización de la residencia"),
    ("m_fiscal", "Cumplimiento fiscal"),
    ("m_inscripcion", "Constancia de inscripción"),
    ("m_cbu", "Constancia de CBU de la institución"),
    ("m_factura", "Factura correspondiente al período a cobrar"),
    ("m_cae", "CAE (código de autorización electrónico)"),
]


def upgrade() -> None:
    tabla = op.create_table(
        "recurso_periodo_requisitos",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("recurso_id", sa.Uuid(), sa.ForeignKey("recursos.id", ondelete="CASCADE"), nullable=False),
        sa.Column("periodo", sa.Date(), nullable=False),
        sa.Column("codigo", sa.String(40)),
        sa.Column("texto", sa.Text(), nullable=False),
        sa.Column("estado", sa.String(20), server_default="pendiente", nullable=False),
        sa.Column("fecha_presentado", sa.Date()),
        sa.Column("observaciones", sa.Text()),
        sa.Column("orden", sa.SmallInteger(), server_default="0", nullable=False),
        sa.Column("actualizado_por", sa.Uuid(), sa.ForeignKey("usuarios.id")),
        sa.Column("actualizado_en", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
    )
    op.create_index("ix_recurso_periodo_requisitos_recurso_id", "recurso_periodo_requisitos", ["recurso_id"])
    op.create_index("ix_recurso_periodo_requisitos_periodo", "recurso_periodo_requisitos", ["periodo"])

    # Lo ya cargado: se pasan los papeles de la institución de cada mes a la residencia (si estaba marcado en algún
    # residente, queda marcado) y se quitan de los pagos individuales.
    bd = op.get_bind()
    filas = bd.execute(
        sa.text(
            "SELECT s.recurso_id, p.periodo, r.codigo, r.estado, r.fecha_presentado FROM subsidio_requisitos r "
            "JOIN subsidio_pagos p ON p.id = r.pago_id JOIN subsidios s ON s.id = r.subsidio_id "
            "WHERE r.grupo = 'institucion' AND s.recurso_id IS NOT NULL AND s.tipo = 'residencia'"
        )
    ).all()
    mejores: dict = {}
    for recurso_id, periodo, codigo, estado, fecha in filas:
        clave = (recurso_id, periodo, codigo)
        if clave not in mejores or (estado == "presentado" and mejores[clave][0] != "presentado"):
            mejores[clave] = (estado, fecha)
    periodos = {(r, p) for r, p, _c in mejores}
    for recurso_id, periodo in sorted(periodos):
        for orden, (codigo, texto) in enumerate(INSTITUCION):
            estado, fecha = mejores.get((recurso_id, periodo, codigo), ("pendiente", None))
            bd.execute(
                tabla.insert().values(id=uuid.uuid4(), recurso_id=recurso_id, periodo=periodo, codigo=codigo, texto=texto, estado=estado, fecha_presentado=fecha, orden=orden)
            )
    bd.execute(
        sa.text(
            "DELETE FROM subsidio_requisitos WHERE grupo = 'institucion' AND pago_id IS NOT NULL AND subsidio_id IN "
            "(SELECT id FROM subsidios WHERE recurso_id IS NOT NULL AND tipo = 'residencia')"
        )
    )


def downgrade() -> None:
    op.drop_table("recurso_periodo_requisitos")

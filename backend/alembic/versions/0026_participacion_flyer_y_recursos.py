"""Participación: el flyer es una imagen (no un título) y las instituciones se vinculan al mapa de recursos.

Revision ID: 0026
Revises: 0025
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0026"
down_revision = "0025"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Los eventos se registran siempre con el nombre de su tipo: el «nombre del flyer» deja de existir.
    op.execute(
        "UPDATE agenda_eventos SET titulo = t.nombre FROM agenda_participacion p JOIN participacion_tipos t ON t.id = p.tipo_id "
        "WHERE p.evento_id = agenda_eventos.id AND p.nombre_flyer IS NOT NULL"
    )
    op.drop_column("agenda_participacion", "nombre_flyer")
    op.create_table(
        "participacion_recursos",
        sa.Column("evento_id", sa.Uuid(), sa.ForeignKey("agenda_eventos.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("recurso_id", sa.Uuid(), sa.ForeignKey("recursos.id"), primary_key=True),
    )
    op.create_index("ix_participacion_recursos_recurso", "participacion_recursos", ["recurso_id"])
    op.create_table(
        "participacion_flyers",
        sa.Column("evento_id", sa.Uuid(), sa.ForeignKey("agenda_eventos.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("nombre", sa.String(300), nullable=False),
        sa.Column("mime", sa.String(100), nullable=False),
        sa.Column("tamano", sa.BigInteger(), nullable=False),
        sa.Column("sha256", sa.String(64), nullable=False),
        sa.Column("almacenamiento", sa.String(30), nullable=False),
        sa.Column("clave_almacenamiento", sa.String(300), nullable=False),
        sa.Column("subido_por", sa.Uuid(), sa.ForeignKey("usuarios.id")),
        sa.Column("subido_en", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )


def downgrade() -> None:
    op.drop_table("participacion_flyers")
    op.drop_table("participacion_recursos")
    op.add_column("agenda_participacion", sa.Column("nombre_flyer", sa.String(200)))

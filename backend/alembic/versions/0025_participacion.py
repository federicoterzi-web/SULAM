"""División Participación y Sensibilización Ciudadana: eventos (sobre la agenda), campañas, material y fotos.

Revision ID: 0025
Revises: 0024
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0025"
down_revision = "0024"
branch_labels = None
depends_on = None


def _archivo() -> list[sa.Column]:
    return [
        sa.Column("nombre", sa.String(300), nullable=False),
        sa.Column("mime", sa.String(100), nullable=False),
        sa.Column("tamano", sa.BigInteger(), nullable=False),
        sa.Column("sha256", sa.String(64), nullable=False),
        sa.Column("almacenamiento", sa.String(30), nullable=False),
        sa.Column("clave_almacenamiento", sa.String(300), nullable=False),
        sa.Column("subido_por", sa.Uuid(), sa.ForeignKey("usuarios.id")),
        sa.Column("subido_en", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    ]


def upgrade() -> None:
    op.create_table(
        "participacion_tipos",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("nombre", sa.String(120), nullable=False),
        sa.Column("activo", sa.Boolean(), server_default=sa.text("true"), nullable=False),
        sa.Column("creado_por", sa.Uuid(), sa.ForeignKey("usuarios.id")),
        sa.Column("creado_en", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("uq_participacion_tipo_nombre", "participacion_tipos", [sa.text("lower(nombre)")], unique=True)
    op.create_table(
        "campanias",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("nombre", sa.String(200), nullable=False),
        sa.Column("descripcion", sa.Text()),
        sa.Column("desde", sa.Date()),
        sa.Column("hasta", sa.Date()),
        sa.Column("estado", sa.String(10), server_default="activa", nullable=False),
        sa.Column("area_id", sa.Integer(), sa.ForeignKey("areas.id")),
        sa.Column("creado_por", sa.Uuid(), sa.ForeignKey("usuarios.id")),
        sa.Column("creado_en", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.CheckConstraint("estado IN ('activa','cerrada')", name="ck_campania_estado"),
    )
    op.create_table(
        "campanias_materiales",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("campania_id", sa.Uuid(), sa.ForeignKey("campanias.id", ondelete="CASCADE"), nullable=False),
        *_archivo(),
    )
    op.create_index("ix_campanias_materiales_campania", "campanias_materiales", ["campania_id"])
    op.create_table(
        "agenda_participacion",
        sa.Column("evento_id", sa.Uuid(), sa.ForeignKey("agenda_eventos.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("tipo_id", sa.Integer(), sa.ForeignKey("participacion_tipos.id"), nullable=False),
        sa.Column("nombre_flyer", sa.String(200)),
        sa.Column("instituciones", postgresql.JSONB(), server_default=sa.text("'[]'::jsonb"), nullable=False),
        sa.Column("resumen", sa.Text()),
        sa.Column("campania_id", sa.Uuid(), sa.ForeignKey("campanias.id")),
        sa.Column("organiza_otra", sa.String(200)),
        sa.Column("sugerir_directora", sa.Boolean(), server_default=sa.text("false"), nullable=False),
        sa.Column("asistentes", sa.Integer()),
    )
    op.create_index("ix_agenda_participacion_campania", "agenda_participacion", ["campania_id"])
    op.create_table(
        "participacion_fotos",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("evento_id", sa.Uuid(), sa.ForeignKey("agenda_eventos.id", ondelete="CASCADE"), nullable=False),
        sa.Column("orden", sa.SmallInteger(), nullable=False),
        *_archivo(),
        sa.UniqueConstraint("evento_id", "orden", name="uq_participacion_foto_orden"),
    )


def downgrade() -> None:
    op.drop_table("participacion_fotos")
    op.drop_table("agenda_participacion")
    op.drop_table("campanias_materiales")
    op.drop_table("campanias")
    op.drop_table("participacion_tipos")

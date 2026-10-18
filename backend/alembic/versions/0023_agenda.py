"""Agenda: salidas, visitas y actividades con fecha, participantes y resultado.

Revision ID: 0023
Revises: 0022
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0023"
down_revision = "0022"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "agenda_eventos",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("tipo", sa.String(20), nullable=False),
        sa.Column("titulo", sa.String(200), nullable=False),
        sa.Column("descripcion", sa.Text()),
        sa.Column("inicio", sa.DateTime(timezone=True), nullable=False),
        sa.Column("fin", sa.DateTime(timezone=True)),
        sa.Column("todo_el_dia", sa.Boolean(), server_default=sa.text("false"), nullable=False),
        sa.Column("lugar", sa.String(300)),
        sa.Column("area_id", sa.Integer(), sa.ForeignKey("areas.id")),
        sa.Column("persona_id", sa.Uuid(), sa.ForeignKey("personas.id")),
        sa.Column("caso_id", sa.Uuid(), sa.ForeignKey("casos.id")),
        sa.Column("estado", sa.String(15), server_default="programado", nullable=False),
        sa.Column("resultado", sa.Text()),
        sa.Column("resuelto_por", sa.Uuid(), sa.ForeignKey("usuarios.id")),
        sa.Column("resuelto_en", sa.DateTime(timezone=True)),
        sa.Column("creado_por", sa.Uuid(), sa.ForeignKey("usuarios.id"), nullable=False),
        sa.Column("creado_en", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.CheckConstraint("estado IN ('programado','realizado','no_realizado','cancelado')", name="ck_agenda_estado"),
    )
    op.create_index("ix_agenda_eventos_inicio", "agenda_eventos", ["inicio"])
    op.create_index("ix_agenda_eventos_persona", "agenda_eventos", ["persona_id"])
    op.create_index("ix_agenda_eventos_caso", "agenda_eventos", ["caso_id"])
    op.create_table(
        "agenda_participantes",
        sa.Column("evento_id", sa.Uuid(), sa.ForeignKey("agenda_eventos.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("usuario_id", sa.Uuid(), sa.ForeignKey("usuarios.id"), primary_key=True),
    )


def downgrade() -> None:
    op.drop_table("agenda_participantes")
    op.drop_table("agenda_eventos")

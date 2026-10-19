"""Novedades dirigidas por rol y chat interno.

Revision ID: 0032
Revises: 0031
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0032"
down_revision = "0031"
branch_labels = None
depends_on = None

UUID = postgresql.UUID(as_uuid=True)


def upgrade() -> None:
    op.create_table(
        "novedades_roles",
        sa.Column("novedad_id", UUID, sa.ForeignKey("novedades.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("rol_id", sa.Integer(), sa.ForeignKey("roles.id", ondelete="CASCADE"), primary_key=True),
    )
    op.create_table(
        "chat_conversaciones",
        sa.Column("id", UUID, primary_key=True),
        sa.Column("tipo", sa.String(10), nullable=False),
        sa.Column("titulo", sa.String(120)),
        sa.Column("clave_directa", sa.String(80), unique=True),
        sa.Column("creada_por", UUID, sa.ForeignKey("usuarios.id"), nullable=False),
        sa.Column("creada_en", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("ultimo_mensaje_en", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_table(
        "chat_participantes",
        sa.Column("conversacion_id", UUID, sa.ForeignKey("chat_conversaciones.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("usuario_id", UUID, sa.ForeignKey("usuarios.id"), primary_key=True),
        sa.Column("ultimo_leido_en", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("agregado_en", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_chat_participantes_usuario", "chat_participantes", ["usuario_id"])
    op.create_table(
        "chat_mensajes",
        sa.Column("id", UUID, primary_key=True),
        sa.Column("conversacion_id", UUID, sa.ForeignKey("chat_conversaciones.id", ondelete="CASCADE"), nullable=False),
        sa.Column("autor_id", UUID, sa.ForeignKey("usuarios.id"), nullable=False),
        sa.Column("cuerpo", sa.Text(), nullable=False),
        sa.Column("creado_en", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("borrado_en", sa.DateTime(timezone=True)),
    )
    op.create_index("ix_chat_mensajes_conv_fecha", "chat_mensajes", ["conversacion_id", "creado_en"])


def downgrade() -> None:
    op.drop_table("chat_mensajes")
    op.drop_table("chat_participantes")
    op.drop_table("chat_conversaciones")
    op.drop_table("novedades_roles")

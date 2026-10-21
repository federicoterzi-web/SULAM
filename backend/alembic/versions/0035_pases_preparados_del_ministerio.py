"""Pases del Ministerio preparados en SULAM y lista de oficinas del Ministerio.

- pases_ministerio: el pase que SULAM prepara (oficina destino, fojas, nota) y que la extensión de
  Chrome precarga en el formulario del Ministerio; lo confirma una persona en el Ministerio.
- oficinas_ministerio: oficinas destino que la extensión vio en el formulario de pase.

Revision ID: 0035
Revises: 0034
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0035"
down_revision = "0034"
branch_labels = None
depends_on = None

UUID = postgresql.UUID(as_uuid=True)


def upgrade() -> None:
    op.create_table(
        "oficinas_ministerio",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("nombre", sa.String(300), nullable=False, unique=True),
        sa.Column("visto_en", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
    )
    op.create_table(
        "pases_ministerio",
        sa.Column("id", UUID, primary_key=True),
        sa.Column("expediente_ministerio_id", UUID, sa.ForeignKey("expedientes_ministerio.id"), nullable=False, index=True),
        sa.Column("oficina_destino", sa.String(300), nullable=False),
        sa.Column("fojas", sa.Integer),
        sa.Column("nota", sa.Text),
        sa.Column("estado", sa.String(12), nullable=False, server_default="preparado"),
        sa.Column("creado_por", UUID, sa.ForeignKey("usuarios.id")),
        sa.Column("creado_en", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("resuelto_en", sa.DateTime(timezone=True)),
        sa.Column("resuelto_detalle", sa.String(300)),
        sa.CheckConstraint("estado IN ('preparado','hecho','cancelado')", name="ck_pases_ministerio_estado"),
    )


def downgrade() -> None:
    op.drop_table("pases_ministerio")
    op.drop_table("oficinas_ministerio")

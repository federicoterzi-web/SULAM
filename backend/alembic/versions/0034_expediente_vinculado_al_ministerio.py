"""Un expediente de SULAM puede corresponder a un expediente del Ministerio.

Revision ID: 0034
Revises: 0033
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0034"
down_revision = "0033"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "expedientes",
        sa.Column(
            "expediente_ministerio_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("expedientes_ministerio.id"),
            nullable=True,
        ),
    )
    op.create_unique_constraint("uq_expedientes_ministerio", "expedientes", ["expediente_ministerio_id"])


def downgrade() -> None:
    op.drop_constraint("uq_expedientes_ministerio", "expedientes", type_="unique")
    op.drop_column("expedientes", "expediente_ministerio_id")

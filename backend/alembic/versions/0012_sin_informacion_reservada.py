"""se elimina la categoría de información reservada

Revision ID: 0012
Revises: 0011
Create Date: 2026-10-17

Decisión de la Dirección (D-021): no hay casos, documentos, tipos documentales
ni vinculados reservados; quien puede ver un caso ve todo su contenido.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = '0012'
down_revision: Union[str, Sequence[str], None] = '0011'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

TABLAS = ("casos", "documentos", "tipos_documentales", "personas_vinculadas")


def upgrade() -> None:
    for tabla in TABLAS:
        op.drop_column(tabla, 'reservado')
    op.execute("DELETE FROM roles_permisos WHERE modulo = 'reservados'")


def downgrade() -> None:
    for tabla in TABLAS:
        op.add_column(tabla, sa.Column('reservado', sa.Boolean(), server_default=sa.text('false'), nullable=False))

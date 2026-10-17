"""página de inicio por rol

Revision ID: 0009
Revises: 0008
Create Date: 2026-10-17

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = '0009'
down_revision: Union[str, Sequence[str], None] = '0008'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

INICIOS = {
    "Dirección y Administración del Sistema": "direccion",
    "Carga de Datos": "carga",
    "Técnico": "tecnico",
    "Mesa de Entrada": "mesa",
    "Administrativo de Área": "administrativo_area",
}


def upgrade() -> None:
    op.add_column('roles', sa.Column('inicio', sa.String(length=30), nullable=True))
    roles = sa.table('roles', sa.column('nombre', sa.String), sa.column('inicio', sa.String))
    for nombre, inicio in INICIOS.items():
        op.execute(roles.update().where(roles.c.nombre == nombre).values(inicio=inicio))


def downgrade() -> None:
    op.drop_column('roles', 'inicio')

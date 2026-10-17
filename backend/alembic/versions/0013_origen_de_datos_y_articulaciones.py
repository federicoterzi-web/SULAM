"""origen de contactos y recursos; articulaciones en casos

Revision ID: 0013
Revises: 0012
Create Date: 2026-10-17

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = '0013'
down_revision: Union[str, Sequence[str], None] = '0012'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    for tabla in ("recursos", "contactos"):
        op.add_column(tabla, sa.Column('origen', sa.String(length=30), nullable=True))
        op.add_column(tabla, sa.Column('origen_detalle', sa.String(length=300), nullable=True))
    op.create_table(
        'casos_articulaciones',
        sa.Column('id', sa.BigInteger(), nullable=False),
        sa.Column('caso_id', sa.UUID(), nullable=False),
        sa.Column('contacto_id', sa.UUID(), nullable=True),
        sa.Column('recurso_id', sa.UUID(), nullable=True),
        sa.Column('fecha', sa.Date(), nullable=False),
        sa.Column('motivo', sa.Text(), nullable=True),
        sa.Column('resultado', sa.Text(), nullable=True),
        sa.Column('usuario_id', sa.UUID(), nullable=True),
        sa.Column('en', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.ForeignKeyConstraint(['caso_id'], ['casos.id']),
        sa.ForeignKeyConstraint(['contacto_id'], ['contactos.id']),
        sa.ForeignKeyConstraint(['recurso_id'], ['recursos.id']),
        sa.ForeignKeyConstraint(['usuario_id'], ['usuarios.id']),
        sa.PrimaryKeyConstraint('id'),
        sa.CheckConstraint('contacto_id IS NOT NULL OR recurso_id IS NOT NULL', name='ck_articulacion_con_quien'),
    )
    op.create_index('ix_casos_articulaciones_caso_id', 'casos_articulaciones', ['caso_id'])
    op.create_index('ix_casos_articulaciones_contacto_id', 'casos_articulaciones', ['contacto_id'])
    op.create_index('ix_casos_articulaciones_recurso_id', 'casos_articulaciones', ['recurso_id'])


def downgrade() -> None:
    op.drop_table('casos_articulaciones')
    for tabla in ("recursos", "contactos"):
        op.drop_column(tabla, 'origen_detalle')
        op.drop_column(tabla, 'origen')

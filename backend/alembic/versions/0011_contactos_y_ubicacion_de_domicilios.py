"""directorio de contactos y ubicación de domicilios

Revision ID: 0011
Revises: 0010
Create Date: 2026-10-17

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = '0011'
down_revision: Union[str, Sequence[str], None] = '0010'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'contactos',
        sa.Column('id', sa.UUID(), nullable=False),
        sa.Column('nombre', sa.String(length=200), nullable=False),
        sa.Column('nombre_norm', sa.String(length=200), nullable=False),
        sa.Column('cargo', sa.String(length=200), nullable=True),
        sa.Column('institucion', sa.String(length=300), nullable=True),
        sa.Column('institucion_norm', sa.String(length=300), nullable=True),
        sa.Column('categoria', sa.String(length=40), nullable=True),
        sa.Column('recurso_id', sa.UUID(), nullable=True),
        sa.Column('localidad', sa.String(length=200), nullable=True),
        sa.Column('departamento', sa.String(length=100), nullable=True),
        sa.Column('telefono', sa.String(length=100), nullable=True),
        sa.Column('telefono_alternativo', sa.String(length=100), nullable=True),
        sa.Column('whatsapp', sa.String(length=30), nullable=True),
        sa.Column('email', sa.String(length=200), nullable=True),
        sa.Column('temas', sa.Text(), nullable=True),
        sa.Column('observaciones', sa.Text(), nullable=True),
        sa.Column('activo', sa.Boolean(), server_default=sa.text('true'), nullable=False),
        sa.Column('creado_por', sa.UUID(), nullable=True),
        sa.Column('creado_en', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('actualizado_por', sa.UUID(), nullable=True),
        sa.Column('actualizado_en', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.ForeignKeyConstraint(['recurso_id'], ['recursos.id']),
        sa.ForeignKeyConstraint(['creado_por'], ['usuarios.id']),
        sa.ForeignKeyConstraint(['actualizado_por'], ['usuarios.id']),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('ix_contactos_nombre_norm', 'contactos', ['nombre_norm'])
    op.create_index('ix_contactos_institucion_norm', 'contactos', ['institucion_norm'])
    op.create_index('ix_contactos_recurso_id', 'contactos', ['recurso_id'])
    op.create_index('ix_contactos_departamento', 'contactos', ['departamento'])
    op.add_column('personas', sa.Column('lat', sa.Float(), nullable=True))
    op.add_column('personas', sa.Column('lng', sa.Float(), nullable=True))
    op.add_column('personas', sa.Column('ubicacion_actualizada_en', sa.DateTime(timezone=True), nullable=True))


def downgrade() -> None:
    op.drop_column('personas', 'ubicacion_actualizada_en')
    op.drop_column('personas', 'lng')
    op.drop_column('personas', 'lat')
    op.drop_index('ix_contactos_departamento', table_name='contactos')
    op.drop_index('ix_contactos_recurso_id', table_name='contactos')
    op.drop_index('ix_contactos_institucion_norm', table_name='contactos')
    op.drop_index('ix_contactos_nombre_norm', table_name='contactos')
    op.drop_table('contactos')

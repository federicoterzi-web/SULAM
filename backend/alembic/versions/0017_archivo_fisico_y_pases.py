"""archivo físico: ubicación de carpetas en papel y pases

Revision ID: 0017
Revises: 0016
Create Date: 2026-10-17

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = '0017'
down_revision: Union[str, Sequence[str], None] = '0016'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute(
        "INSERT INTO areas (nombre, activo) SELECT 'Oficina de Registro', true "
        "WHERE NOT EXISTS (SELECT 1 FROM areas WHERE nombre = 'Oficina de Registro')"
    )
    op.create_table(
        'ubicaciones_fisicas',
        sa.Column('id', sa.BigInteger(), nullable=False),
        sa.Column('persona_id', sa.UUID(), nullable=True),
        sa.Column('expediente_id', sa.UUID(), nullable=True),
        sa.Column('area_id', sa.Integer(), nullable=False),
        sa.Column('usuario_id', sa.UUID(), nullable=True),
        sa.Column('desde', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('actualizado_por', sa.UUID(), nullable=True),
        sa.ForeignKeyConstraint(['persona_id'], ['personas.id']),
        sa.ForeignKeyConstraint(['expediente_id'], ['expedientes.id']),
        sa.ForeignKeyConstraint(['area_id'], ['areas.id']),
        sa.ForeignKeyConstraint(['usuario_id'], ['usuarios.id']),
        sa.ForeignKeyConstraint(['actualizado_por'], ['usuarios.id']),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('persona_id', name='uq_ubicacion_persona'),
        sa.UniqueConstraint('expediente_id', name='uq_ubicacion_expediente'),
        sa.CheckConstraint('(persona_id IS NULL) <> (expediente_id IS NULL)', name='ck_ubicacion_un_objeto'),
    )
    op.create_table(
        'pases',
        sa.Column('id', sa.BigInteger(), nullable=False),
        sa.Column('tipo', sa.String(length=10), nullable=False),
        sa.Column('persona_id', sa.UUID(), nullable=True),
        sa.Column('expediente_id', sa.UUID(), nullable=True),
        sa.Column('desde_area_id', sa.Integer(), nullable=True),
        sa.Column('desde_usuario_id', sa.UUID(), nullable=True),
        sa.Column('hacia_area_id', sa.Integer(), nullable=False),
        sa.Column('hacia_usuario_id', sa.UUID(), nullable=True),
        sa.Column('motivo', sa.Text(), nullable=True),
        sa.Column('estado', sa.String(length=12), nullable=False),
        sa.Column('iniciado_por', sa.UUID(), nullable=True),
        sa.Column('iniciado_en', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('resuelto_por', sa.UUID(), nullable=True),
        sa.Column('resuelto_en', sa.DateTime(timezone=True), nullable=True),
        sa.Column('respuesta', sa.Text(), nullable=True),
        sa.ForeignKeyConstraint(['persona_id'], ['personas.id']),
        sa.ForeignKeyConstraint(['expediente_id'], ['expedientes.id']),
        sa.ForeignKeyConstraint(['desde_area_id'], ['areas.id']),
        sa.ForeignKeyConstraint(['desde_usuario_id'], ['usuarios.id']),
        sa.ForeignKeyConstraint(['hacia_area_id'], ['areas.id']),
        sa.ForeignKeyConstraint(['hacia_usuario_id'], ['usuarios.id']),
        sa.ForeignKeyConstraint(['iniciado_por'], ['usuarios.id']),
        sa.ForeignKeyConstraint(['resuelto_por'], ['usuarios.id']),
        sa.PrimaryKeyConstraint('id'),
        sa.CheckConstraint('(persona_id IS NULL) <> (expediente_id IS NULL)', name='ck_pase_un_objeto'),
        sa.CheckConstraint("tipo IN ('pedido', 'envio')", name='ck_pase_tipo'),
        sa.CheckConstraint("estado IN ('pendiente', 'hecho', 'rechazado', 'cancelado')", name='ck_pase_estado'),
    )
    op.create_index('ix_pases_persona_id', 'pases', ['persona_id'])
    op.create_index('ix_pases_expediente_id', 'pases', ['expediente_id'])


def downgrade() -> None:
    op.drop_table('pases')
    op.drop_table('ubicaciones_fisicas')

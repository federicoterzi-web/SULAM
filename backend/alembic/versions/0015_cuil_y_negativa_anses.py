"""CUIL de la persona y constancias (certificación negativa de ANSES)

Revision ID: 0015
Revises: 0014
Create Date: 2026-10-17

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = '0015'
down_revision: Union[str, Sequence[str], None] = '0014'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('personas', sa.Column('cuil', sa.String(length=13), nullable=True))
    op.create_table(
        'constancias',
        sa.Column('id', sa.BigInteger(), nullable=False),
        sa.Column('persona_id', sa.UUID(), nullable=False),
        sa.Column('tipo', sa.String(length=40), nullable=False),
        sa.Column('cuil', sa.String(length=13), nullable=True),
        sa.Column('fecha_emision', sa.Date(), nullable=False),
        sa.Column('vence', sa.Date(), nullable=True),
        sa.Column('resultado', sa.String(length=20), nullable=False),
        sa.Column('detalle', sa.Text(), nullable=True),
        sa.Column('codigo_validacion', sa.String(length=100), nullable=True),
        sa.Column('documento_id', sa.UUID(), nullable=True),
        sa.Column('origen', sa.String(length=20), nullable=False),
        sa.Column('observaciones', sa.Text(), nullable=True),
        sa.Column('usuario_id', sa.UUID(), nullable=True),
        sa.Column('en', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.ForeignKeyConstraint(['persona_id'], ['personas.id']),
        sa.ForeignKeyConstraint(['documento_id'], ['documentos.id']),
        sa.ForeignKeyConstraint(['usuario_id'], ['usuarios.id']),
        sa.PrimaryKeyConstraint('id'),
        sa.CheckConstraint(
            "resultado IN ('sin_registros', 'con_registros', 'no_emitida')", name='ck_constancias_resultado'
        ),
    )
    op.create_index('ix_constancias_persona_id', 'constancias', ['persona_id'])
    op.execute(
        "INSERT INTO tipos_documentales (nombre, activo, orden) "
        "SELECT 'Certificación negativa ANSES', true, 20 WHERE NOT EXISTS "
        "(SELECT 1 FROM tipos_documentales WHERE nombre = 'Certificación negativa ANSES')"
    )


def downgrade() -> None:
    op.drop_table('constancias')
    op.drop_column('personas', 'cuil')

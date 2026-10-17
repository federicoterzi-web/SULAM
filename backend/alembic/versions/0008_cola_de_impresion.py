"""cola de impresión de carátulas

Revision ID: 0008
Revises: 0007
Create Date: 2026-10-17

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = '0008'
down_revision: Union[str, Sequence[str], None] = '0007'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('casos', sa.Column('caratula_impresa_en', sa.DateTime(timezone=True), nullable=True))
    op.add_column('casos', sa.Column('caratula_impresa_por', sa.UUID(), nullable=True))
    op.create_foreign_key('fk_casos_caratula_impresa_por', 'casos', 'usuarios', ['caratula_impresa_por'], ['id'])
    op.create_index('ix_casos_caratula_pendiente', 'casos', ['abierto_en'],
                    postgresql_where=sa.text('caratula_impresa_en IS NULL'))


def downgrade() -> None:
    op.drop_index('ix_casos_caratula_pendiente', table_name='casos')
    op.drop_constraint('fk_casos_caratula_impresa_por', 'casos', type_='foreignkey')
    op.drop_column('casos', 'caratula_impresa_por')
    op.drop_column('casos', 'caratula_impresa_en')

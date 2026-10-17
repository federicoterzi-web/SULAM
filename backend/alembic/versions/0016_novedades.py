"""novedades de la Dirección y de las áreas, con confirmación de lectura

Revision ID: 0016
Revises: 0015
Create Date: 2026-10-17

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = '0016'
down_revision: Union[str, Sequence[str], None] = '0015'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

# Publican: Dirección (para todos o cualquier área) y jefaturas (su área).
PERMISOS = {
    "Dirección y Administración del Sistema": "todos",
    "Directora": "todos",
    "Jefe/a de departamento": "area",
    "Jefe/a de división": "area",
}


def upgrade() -> None:
    op.create_table(
        'novedades',
        sa.Column('id', sa.UUID(), nullable=False),
        sa.Column('titulo', sa.String(length=300), nullable=False),
        sa.Column('cuerpo', sa.Text(), nullable=False),
        sa.Column('area_id', sa.Integer(), nullable=True),
        sa.Column('requiere_confirmacion', sa.Boolean(), server_default=sa.text('true'), nullable=False),
        sa.Column('fijada', sa.Boolean(), server_default=sa.text('false'), nullable=False),
        sa.Column('archivo_nombre', sa.String(length=300), nullable=True),
        sa.Column('archivo_mime', sa.String(length=100), nullable=True),
        sa.Column('archivo_tamano', sa.BigInteger(), nullable=True),
        sa.Column('archivo_sha256', sa.String(length=64), nullable=True),
        sa.Column('archivo_almacenamiento', sa.String(length=30), nullable=True),
        sa.Column('archivo_clave', sa.String(length=300), nullable=True),
        sa.Column('autor_id', sa.UUID(), nullable=True),
        sa.Column('publicada_en', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('retirada_en', sa.DateTime(timezone=True), nullable=True),
        sa.Column('retirada_por', sa.UUID(), nullable=True),
        sa.ForeignKeyConstraint(['area_id'], ['areas.id']),
        sa.ForeignKeyConstraint(['autor_id'], ['usuarios.id']),
        sa.ForeignKeyConstraint(['retirada_por'], ['usuarios.id']),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('ix_novedades_area_id', 'novedades', ['area_id'])
    op.create_table(
        'novedades_lecturas',
        sa.Column('novedad_id', sa.UUID(), nullable=False),
        sa.Column('usuario_id', sa.UUID(), nullable=False),
        sa.Column('confirmada_en', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.ForeignKeyConstraint(['novedad_id'], ['novedades.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['usuario_id'], ['usuarios.id']),
        sa.PrimaryKeyConstraint('novedad_id', 'usuario_id'),
    )
    con = op.get_bind()
    for rol, alcance in PERMISOS.items():
        con.execute(
            sa.text(
                "INSERT INTO roles_permisos (rol_id, modulo, accion, alcance) "
                "SELECT id, 'novedades', 'publicar', CAST(:al AS varchar) FROM roles r WHERE r.nombre = :rol "
                "AND NOT EXISTS (SELECT 1 FROM roles_permisos p WHERE p.rol_id = r.id "
                "AND p.modulo = 'novedades' AND p.accion = 'publicar')"
            ),
            {"rol": rol, "al": alcance},
        )


def downgrade() -> None:
    op.execute("DELETE FROM roles_permisos WHERE modulo = 'novedades'")
    op.drop_table('novedades_lecturas')
    op.drop_table('novedades')

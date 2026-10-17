"""red de recursos con geolocalización

Revision ID: 0010
Revises: 0009
Create Date: 2026-10-17

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = '0010'
down_revision: Union[str, Sequence[str], None] = '0009'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

# Permisos propuestos para los roles iniciales (editables en Administración).
PERMISOS = {
    "Dirección y Administración del Sistema": [("consultar", "todos"), ("crear", "todos"), ("modificar", "todos")],
    "Directora": [("consultar", "todos"), ("crear", "todos"), ("modificar", "todos")],
    "Jefe/a de departamento": [("consultar", "todos"), ("crear", "todos"), ("modificar", "todos")],
    "Jefe/a de división": [("consultar", "todos"), ("crear", "todos"), ("modificar", "todos")],
    "Carga de Datos": [("consultar", "todos"), ("crear", "todos"), ("modificar", "todos")],
    "Técnico": [("consultar", "todos"), ("crear", "todos"), ("modificar", "propios")],
    "Mesa de Entrada": [("consultar", "todos")],
    "Administrativo de Área": [("consultar", "todos"), ("crear", "todos"), ("modificar", "propios")],
}


def upgrade() -> None:
    op.create_table(
        'recursos',
        sa.Column('id', sa.UUID(), nullable=False),
        sa.Column('tipo', sa.String(length=30), nullable=False),
        sa.Column('categoria', sa.String(length=40), nullable=True),
        sa.Column('nombre', sa.String(length=300), nullable=False),
        sa.Column('nombre_norm', sa.String(length=300), nullable=False),
        sa.Column('direccion', sa.String(length=500), nullable=True),
        sa.Column('localidad', sa.String(length=200), nullable=True),
        sa.Column('departamento', sa.String(length=100), nullable=True),
        sa.Column('lat', sa.Float(), nullable=True),
        sa.Column('lng', sa.Float(), nullable=True),
        sa.Column('telefono', sa.String(length=100), nullable=True),
        sa.Column('telefono_alternativo', sa.String(length=100), nullable=True),
        sa.Column('email', sa.String(length=200), nullable=True),
        sa.Column('horario', sa.String(length=300), nullable=True),
        sa.Column('referente', sa.String(length=200), nullable=True),
        sa.Column('referente_cargo', sa.String(length=200), nullable=True),
        sa.Column('servicios', sa.Text(), nullable=True),
        sa.Column('observaciones', sa.Text(), nullable=True),
        sa.Column('zonas', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column('formacion', sa.Text(), nullable=True),
        sa.Column('disponibilidad', sa.String(length=300), nullable=True),
        sa.Column('activo', sa.Boolean(), server_default=sa.text('true'), nullable=False),
        sa.Column('creado_por', sa.UUID(), nullable=True),
        sa.Column('creado_en', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('actualizado_por', sa.UUID(), nullable=True),
        sa.Column('actualizado_en', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.ForeignKeyConstraint(['creado_por'], ['usuarios.id']),
        sa.ForeignKeyConstraint(['actualizado_por'], ['usuarios.id']),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('ix_recursos_tipo', 'recursos', ['tipo'])
    op.create_index('ix_recursos_nombre_norm', 'recursos', ['nombre_norm'])
    op.create_index('ix_recursos_departamento', 'recursos', ['departamento'])

    conn = op.get_bind()
    for rol, permisos in PERMISOS.items():
        rol_id = conn.execute(sa.text("SELECT id FROM roles WHERE nombre = :n"), {"n": rol}).scalar()
        if rol_id is None:
            continue
        for accion, alcance in permisos:
            conn.execute(
                sa.text(
                    "INSERT INTO roles_permisos (rol_id, modulo, accion, alcance) "
                    "SELECT :r, 'recursos', CAST(:a AS varchar), CAST(:al AS varchar) WHERE NOT EXISTS ("
                    "SELECT 1 FROM roles_permisos WHERE rol_id = :r AND modulo = 'recursos' "
                    "AND accion = CAST(:a AS varchar))"
                ),
                {"r": rol_id, "a": accion, "al": alcance},
            )


def downgrade() -> None:
    op.execute("DELETE FROM roles_permisos WHERE modulo = 'recursos'")
    op.drop_index('ix_recursos_departamento', table_name='recursos')
    op.drop_index('ix_recursos_nombre_norm', table_name='recursos')
    op.drop_index('ix_recursos_tipo', table_name='recursos')
    op.drop_table('recursos')

"""informes redactados en SULAM y plantillas de informe

Revision ID: 0014
Revises: 0013
Create Date: 2026-10-17

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = '0014'
down_revision: Union[str, Sequence[str], None] = '0013'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

# Quién edita las plantillas: Dirección (todas) y jefaturas (las de su área).
PERMISOS = {
    "Dirección y Administración del Sistema": "todos",
    "Directora": "todos",
    "Jefe/a de departamento": "area",
    "Jefe/a de división": "area",
}


def upgrade() -> None:
    op.create_table(
        'plantillas_informe',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('nombre', sa.String(length=200), nullable=False),
        sa.Column('descripcion', sa.Text(), nullable=True),
        sa.Column('area_id', sa.Integer(), nullable=True),
        sa.Column('tipo_documental_id', sa.Integer(), nullable=True),
        sa.Column('estructura', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column('orden', sa.Integer(), server_default=sa.text('0'), nullable=False),
        sa.Column('activo', sa.Boolean(), server_default=sa.text('true'), nullable=False),
        sa.Column('creado_por', sa.UUID(), nullable=True),
        sa.Column('creado_en', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('actualizado_por', sa.UUID(), nullable=True),
        sa.Column('actualizado_en', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.ForeignKeyConstraint(['area_id'], ['areas.id']),
        sa.ForeignKeyConstraint(['tipo_documental_id'], ['tipos_documentales.id']),
        sa.ForeignKeyConstraint(['creado_por'], ['usuarios.id']),
        sa.ForeignKeyConstraint(['actualizado_por'], ['usuarios.id']),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_table(
        'informes',
        sa.Column('id', sa.UUID(), nullable=False),
        sa.Column('grupo_id', sa.UUID(), nullable=False),
        sa.Column('version', sa.Integer(), nullable=False),
        sa.Column('persona_id', sa.UUID(), nullable=False),
        sa.Column('caso_id', sa.UUID(), nullable=True),
        sa.Column('plantilla_id', sa.Integer(), nullable=True),
        sa.Column('tipo_documental_id', sa.Integer(), nullable=True),
        sa.Column('titulo', sa.String(length=300), nullable=False),
        sa.Column('lugar', sa.String(length=200), nullable=True),
        sa.Column('fecha', sa.Date(), nullable=False),
        sa.Column('destinatario', sa.Text(), nullable=True),
        sa.Column('datos', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column('secciones', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column('firmantes', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column('estado', sa.String(length=20), nullable=False),
        sa.Column('documento_id', sa.UUID(), nullable=True),
        sa.Column('firmado_en', sa.DateTime(timezone=True), nullable=True),
        sa.Column('firmado_por', sa.UUID(), nullable=True),
        sa.Column('creado_por', sa.UUID(), nullable=True),
        sa.Column('creado_en', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('actualizado_por', sa.UUID(), nullable=True),
        sa.Column('actualizado_en', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.ForeignKeyConstraint(['persona_id'], ['personas.id']),
        sa.ForeignKeyConstraint(['caso_id'], ['casos.id']),
        sa.ForeignKeyConstraint(['plantilla_id'], ['plantillas_informe.id']),
        sa.ForeignKeyConstraint(['tipo_documental_id'], ['tipos_documentales.id']),
        sa.ForeignKeyConstraint(['documento_id'], ['documentos.id']),
        sa.ForeignKeyConstraint(['firmado_por'], ['usuarios.id']),
        sa.ForeignKeyConstraint(['creado_por'], ['usuarios.id']),
        sa.ForeignKeyConstraint(['actualizado_por'], ['usuarios.id']),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('grupo_id', 'version', name='uq_informes_grupo_version'),
        sa.CheckConstraint("estado IN ('borrador', 'firmado', 'reemplazado', 'descartado')", name='ck_informes_estado'),
    )
    op.create_index('ix_informes_grupo_id', 'informes', ['grupo_id'])
    op.create_index('ix_informes_persona_id', 'informes', ['persona_id'])
    op.create_index('ix_informes_caso_id', 'informes', ['caso_id'])

    con = op.get_bind()
    for rol, alcance in PERMISOS.items():
        con.execute(
            sa.text(
                "INSERT INTO roles_permisos (rol_id, modulo, accion, alcance) "
                "SELECT id, 'plantillas', 'modificar', CAST(:al AS varchar) FROM roles r WHERE r.nombre = :rol "
                "AND NOT EXISTS (SELECT 1 FROM roles_permisos p WHERE p.rol_id = r.id "
                "AND p.modulo = 'plantillas' AND p.accion = 'modificar')"
            ),
            {"rol": rol, "al": alcance},
        )


def downgrade() -> None:
    op.execute("DELETE FROM roles_permisos WHERE modulo = 'plantillas'")
    op.drop_table('informes')
    op.drop_table('plantillas_informe')

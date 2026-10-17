"""Permiso de estadísticas.

Revision ID: 0019
Revises: 0018
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0019"
down_revision = "0018"
branch_labels = None
depends_on = None

PERMISOS = {
    "Dirección y Administración del Sistema": "todos",
    "Directora": "todos",
    "Jefe/a de departamento": "area",
    "Jefe/a de división": "area",
}


def upgrade() -> None:
    con = op.get_bind()
    for rol, alcance in PERMISOS.items():
        con.execute(
            sa.text(
                "INSERT INTO roles_permisos (rol_id, modulo, accion, alcance) "
                "SELECT r.id, 'estadisticas', 'consultar', CAST(:al AS varchar) FROM roles r WHERE r.nombre = CAST(:rol AS varchar) "
                "AND NOT EXISTS (SELECT 1 FROM roles_permisos p WHERE p.rol_id = r.id AND p.modulo = 'estadisticas' AND p.accion = 'consultar')"
            ),
            {"rol": rol, "al": alcance},
        )


def downgrade() -> None:
    op.execute("DELETE FROM roles_permisos WHERE modulo = 'estadisticas'")

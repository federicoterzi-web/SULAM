"""Las pruebas usan una base PostgreSQL real (por defecto `sulam_test`).

Configurar con SULAM_TEST_DATABASE_URL. ¡La base indicada se vacía!
"""

from __future__ import annotations

import os
import tempfile
from pathlib import Path

import pytest

TEST_URL = os.environ.get(
    "SULAM_TEST_DATABASE_URL", "postgresql+psycopg://sulam:sulam@localhost:5432/sulam_test"
)
_tmp = Path(tempfile.mkdtemp(prefix="sulam-test-"))
os.environ["SULAM_DATABASE_URL"] = TEST_URL
os.environ["SULAM_DATA_DIR"] = str(_tmp)
os.environ["SULAM_STORAGE_DIR"] = str(_tmp / "archivos")
os.environ["SULAM_BACKUP_DIR"] = str(_tmp / "respaldos")
os.environ["SULAM_ENV"] = "pruebas"
os.environ["SULAM_INDEXAR_TEXTO"] = "0"  # las pruebas leen el texto a pedido, no en segundo plano
os.environ["SULAM_FRONTEND_DIST"] = str(_tmp / "sin-frontend")

from fastapi.testclient import TestClient  # noqa: E402
from sqlalchemy import create_engine, text  # noqa: E402

from sulam.config import get_settings  # noqa: E402
from sulam.db import reset_engine, session_factory  # noqa: E402
from sulam.models import Area, Rol, Usuario  # noqa: E402
from sulam.seed import crear_administrador, inicializar_catalogos  # noqa: E402
from sulam.security import hash_password  # noqa: E402

PASSWORD = "clave-prueba-123"


@pytest.fixture(scope="session", autouse=True)
def esquema():
    get_settings.cache_clear()
    motor = create_engine(TEST_URL)
    with motor.begin() as c:
        c.execute(text("DROP SCHEMA public CASCADE"))
        c.execute(text("CREATE SCHEMA public"))
    motor.dispose()
    from sulam.cli import cmd_migrar

    cmd_migrar(None)
    yield


TABLAS = [
    "auditoria", "capturas_paginas", "justificativos", "solicitudes_personal", "revisiones_jornada", "marcaciones", "reloj_importaciones", "agentes_horarios", "agentes", "pases", "ubicaciones_fisicas", "novedades_lecturas", "novedades", "constancias", "informes", "plantillas_informe", "casos_articulaciones", "contactos", "recursos", "registros_demanda", "casos_evoluciones", "documentos", "ingresos", "expedientes", "casos_asignaciones",
    "casos_estados_historial", "casos", "personas_vinculadas", "personas", "sesiones",
    "usuarios_roles", "usuarios", "roles_permisos", "roles", "tipos_vinculo",
    "tipos_documentales", "areas", "contadores",
]


@pytest.fixture(autouse=True)
def base_limpia(esquema):
    reset_engine()
    motor = create_engine(TEST_URL)
    with motor.begin() as c:
        c.execute(text("ALTER TABLE auditoria DISABLE TRIGGER auditoria_sin_truncate"))
        c.execute(text(f"TRUNCATE {', '.join(TABLAS)} RESTART IDENTITY CASCADE"))
        c.execute(text("ALTER TABLE auditoria ENABLE TRIGGER auditoria_sin_truncate"))
    motor.dispose()
    db = session_factory()()
    inicializar_catalogos(db)
    crear_administrador(db, "admin", "Administración", PASSWORD).debe_cambiar_password = False
    db.commit()
    db.close()
    yield


@pytest.fixture
def db():
    s = session_factory()()
    yield s
    s.close()


def crear_usuario(usuario: str, rol: str, area: str | None = None) -> None:
    s = session_factory()()
    try:
        u = Usuario(
            usuario=usuario,
            nombre_completo=usuario.title(),
            password_hash=hash_password(PASSWORD),
            debe_cambiar_password=False,
        )
        u.roles = [s.query(Rol).filter_by(nombre=rol).one()]
        if area:
            u.area_id = s.query(Area).filter_by(nombre=area).one().id
        s.add(u)
        s.commit()
    finally:
        s.close()


class Cliente:
    """Cliente HTTP con sesión iniciada y cabecera CSRF."""

    def __init__(self, usuario: str, password: str = PASSWORD):
        from sulam.main import crear_app

        self.http = TestClient(crear_app())
        r = self.http.post("/api/auth/login", json={"usuario": usuario, "password": password})
        assert r.status_code == 200, r.text
        self.yo = r.json()
        self.http.headers["X-CSRF-Token"] = self.yo["csrf_token"]

    def __getattr__(self, nombre):
        return getattr(self.http, nombre)


@pytest.fixture
def admin() -> Cliente:
    return Cliente("admin")


@pytest.fixture
def cliente():
    return Cliente


AREA_ADMISION = "Departamento Admisión de Casos y Recepción de Denuncias"
AREA_PROMOCION = "Departamento Promoción Integral de Derechos"

PDF = b"%PDF-1.4\n1 0 obj\n<< /Type /Catalog >>\nendobj\ntrailer\n<< /Root 1 0 R >>\n%%EOF\n"


def nueva_persona(c: Cliente, **kw) -> dict:
    datos = {"apellidos": "PRUEBA", "nombres": "Persona", "tipo_documento": "DNI", "numero_documento": "1000000"}
    datos.update(kw)
    r = c.post("/api/personas", json=datos)
    assert r.status_code == 201, r.text
    return r.json()


def nuevo_caso(c: Cliente, persona_id: str, **kw) -> dict:
    r = c.post("/api/casos", json={"persona_id": persona_id, **kw})
    assert r.status_code == 201, r.text
    return r.json()

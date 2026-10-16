"""Sesiones, información reservada, consultas auditadas, unificación y respaldo."""

from __future__ import annotations

import shutil

import pytest
from sqlalchemy import select

from conftest import AREA_ADMISION, PASSWORD, PDF, Cliente, crear_usuario, nueva_persona, nuevo_caso
from sulam.db import session_factory
from sulam.models import Auditoria, Usuario


def test_login_incorrecto_y_bloqueo(admin):
    from sulam.main import crear_app
    from fastapi.testclient import TestClient

    http = TestClient(crear_app())
    for _ in range(4):
        assert http.post("/api/auth/login", json={"usuario": "admin", "password": "mala"}).status_code == 401
    # El quinto intento bloquea, incluso con la contraseña correcta.
    assert http.post("/api/auth/login", json={"usuario": "admin", "password": "mala"}).status_code == 401
    assert http.post("/api/auth/login", json={"usuario": "admin", "password": PASSWORD}).status_code == 423
    # Usuario inexistente: mismo mensaje que contraseña incorrecta.
    r = http.post("/api/auth/login", json={"usuario": "nadie", "password": "x"})
    assert r.status_code == 401 and r.json()["detail"] == "Usuario o contraseña incorrectos."


def test_cambio_de_password_obligatorio(admin):
    r = admin.post("/api/admin/usuarios", json={"usuario": "nuevo", "nombre_completo": "Nuevo Usuario",
                                                "roles": [], "password_inicial": "temporal-123"})
    assert r.status_code == 201, r.text
    nuevo = Cliente("nuevo", "temporal-123")
    assert nuevo.yo["debe_cambiar_password"] is True
    assert nuevo.get("/api/tablero").status_code == 403
    assert nuevo.post("/api/auth/password", json={"password_actual": "temporal-123", "password_nueva": "corta"}).status_code == 400
    r = nuevo.post("/api/auth/password", json={"password_actual": "temporal-123", "password_nueva": "definitiva-456"})
    assert r.status_code == 200
    assert nuevo.get("/api/tablero").status_code == 200


def test_logout_invalida_la_sesion(admin):
    assert admin.post("/api/auth/logout").status_code == 200
    assert admin.get("/api/auth/me").status_code == 401


def test_usuario_desactivado_pierde_acceso(admin):
    crear_usuario("tec", "Técnico")
    tec = Cliente("tec")
    db = session_factory()()
    uid = db.execute(select(Usuario.id).where(Usuario.usuario == "tec")).scalar_one()
    db.close()
    assert admin.patch(f"/api/admin/usuarios/{uid}", json={"activo": False}).status_code == 200
    assert tec.get("/api/tablero").status_code == 401


def test_caso_reservado_y_vinculado_reservado(admin):
    crear_usuario("tec1", "Técnico", AREA_ADMISION)
    crear_usuario("tec2", "Técnico", AREA_ADMISION)
    ids = {u["nombre_completo"]: u["id"] for u in admin.get("/api/catalogos").json()["usuarios_asignables"]}
    p = nueva_persona(admin)
    caso = nuevo_caso(admin, p["id"], reservado=True, motivo="Denuncia de maltrato", responsable_id=ids["Tec1"])
    r = admin.post("/api/documentos", data={"tipo_documental_id": "6", "titulo": "Acta", "persona_id": p["id"], "caso_id": caso["id"]},
                   files={"archivo": ("a.pdf", PDF, "application/pdf")})
    doc = r.json()
    vinculos = {v["nombre"]: v["id"] for v in admin.get("/api/catalogos").json()["tipos_vinculo"]}
    admin.post(f"/api/personas/{p['id']}/vinculados",
               json={"tipo_vinculo_id": vinculos["Denunciante"], "apellidos": "VECINA", "nombres": "Ana", "reservado": True})

    # La técnica asignada ve todo.
    tec1 = Cliente("tec1")
    c = tec1.get(f"/api/casos/{caso['id']}").json()
    assert c["motivo"] == "Denuncia de maltrato" and c["documentos"]
    assert tec1.get(f"/api/documentos/{doc['id']}/archivo").status_code == 200
    v = tec1.get(f"/api/personas/{p['id']}").json()["vinculados"][0]
    assert v["apellidos"] == "VECINA"

    # Otro técnico sabe que el caso existe (evita intervenciones duplicadas) pero no ve su contenido.
    tec2 = Cliente("tec2")
    c = tec2.get(f"/api/casos/{caso['id']}").json()
    assert c["contenido_restringido"] is True and c["motivo"] is None and c["documentos"] == []
    assert tec2.get(f"/api/documentos/{doc['id']}/archivo").status_code == 403
    legajo = tec2.get(f"/api/personas/{p['id']}").json()
    assert legajo["casos"][0]["contenido_restringido"] is True
    assert legajo["documentos"][0]["contenido_restringido"] is True and "titulo" not in legajo["documentos"][0]
    v = legajo["vinculados"][0]
    assert v["contenido_restringido"] is True and "apellidos" not in v

    # La carátula de un expediente del caso reservado tampoco se muestra.
    admin.post("/api/expedientes", json={"persona_id": p["id"], "caso_id": caso["id"], "numero": "J-1/2026",
                                         "tipo": "judicial", "caratula": "s/ protección"})
    assert tec1.get(f"/api/personas/{p['id']}").json()["expedientes"][0]["caratula"] == "s/ protección"
    exp = tec2.get(f"/api/personas/{p['id']}").json()["expedientes"][0]
    assert exp["caratula"] is None and exp["contenido_restringido"] is True


def test_las_consultas_quedan_registradas(admin):
    crear_usuario("tec", "Técnico")
    p = nueva_persona(admin)
    tec = Cliente("tec")
    tec.get(f"/api/personas/{p['id']}")
    tec.get("/api/personas", params={"q": "prueba"})
    db = session_factory()()
    acciones = [
        (a.accion, a.usuario.usuario)
        for a in db.execute(select(Auditoria).where(Auditoria.accion.in_(["consultar_legajo", "busqueda"]))).scalars()
    ]
    db.close()
    assert ("consultar_legajo", "tec") in acciones and ("busqueda", "tec") in acciones

    # El historial del legajo muestra las consultas solo a quien tiene permiso de auditoría.
    assert not any(a["accion"].startswith("consultar") for a in tec.get(f"/api/personas/{p['id']}/actividad").json())
    assert any(a["accion"] == "consultar_legajo" for a in admin.get(f"/api/personas/{p['id']}/actividad").json())


def test_unificacion_de_legajos(admin):
    a = nueva_persona(admin, apellidos="SUAREZ", nombres="Ramón", numero_documento="8000000")
    b = nueva_persona(admin, apellidos="SUÁREZ", nombres="Ramon", numero_documento=None, sin_documento=True,
                      confirmar_posible_duplicado=True)
    nuevo_caso(admin, b["id"])
    crear_usuario("carga", "Carga de Datos")
    assert Cliente("carga").post(f"/api/personas/{a['id']}/unificar",
                                 json={"legajo_a_absorber_id": b["id"], "motivo": "Misma persona"}).status_code == 403

    r = admin.post(f"/api/personas/{a['id']}/unificar", json={"legajo_a_absorber_id": b["id"], "motivo": "Misma persona"})
    assert r.status_code == 200 and r.json()["movidos"]["casos"] == 1
    assert len(admin.get(f"/api/personas/{a['id']}").json()["casos"]) == 1
    r = admin.get(f"/api/personas/{b['id']}")
    assert r.status_code == 409 and r.json()["detail"]["unificada_en_id"] == a["id"]
    assert [p["id"] for p in admin.get("/api/personas", params={"q": "suarez"}).json()] == [a["id"]]


@pytest.mark.skipif(shutil.which("pg_dump") is None, reason="pg_dump no disponible")
def test_respaldo_y_restauracion(admin):
    from sulam.backup import respaldar, restaurar
    from sulam.db import reset_engine

    p = nueva_persona(admin)
    r = admin.post("/api/documentos", data={"tipo_documental_id": "1", "titulo": "Doc", "persona_id": p["id"]},
                   files={"archivo": ("d.pdf", PDF, "application/pdf")})
    doc_id = r.json()["id"]
    archivo = respaldar()

    # Se pierde información después del respaldo...
    nueva_persona(admin, numero_documento="9999999", apellidos="POSTERIOR")
    from sulam.config import get_settings

    shutil.rmtree(get_settings().storage_dir)
    reset_engine()

    # ...y se recupera el estado respaldado, incluidos los archivos.
    restaurar(archivo)
    reset_engine()
    c = Cliente("admin")
    nombres = [x["apellidos"] for x in c.get("/api/personas").json()]
    assert nombres == ["PRUEBA"]
    assert c.get(f"/api/documentos/{doc_id}/archivo").content == PDF

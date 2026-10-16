"""Criterios mínimos de aceptación de SULAM 0.1 (documento de diseño §13.3),
más los agregados de la revisión (reservados, consultas auditadas, respaldo)."""

from __future__ import annotations

import shutil

import pytest
from sqlalchemy import select, text

from conftest import AREA_ADMISION, AREA_PROMOCION, PDF, Cliente, crear_usuario, nueva_persona, nuevo_caso
from sulam.db import reset_engine, session_factory
from sulam.models import Auditoria


# ---------------------------------------------------------------- 1. duplicados


def test_registrar_persona_sin_duplicados_evidentes(admin):
    p = nueva_persona(admin, apellidos="Pérez", nombres="Rosa Elvira", numero_documento="4.123.456",
                      fecha_nacimiento="1941-03-12")
    assert p["numero_documento"] == "4123456"
    assert p["numero_legajo"].startswith("L-")

    # Mismo documento: bloquea siempre.
    r = admin.post("/api/personas", json={"apellidos": "Otra", "nombres": "Persona",
                                          "tipo_documento": "DNI", "numero_documento": "4123456",
                                          "confirmar_posible_duplicado": True})
    assert r.status_code == 409
    assert r.json()["detail"]["bloqueante"] is True

    # Mismo nombre (sin tildes, otro orden de carga) y fecha: pide confirmación.
    r = admin.post("/api/personas", json={"apellidos": "PEREZ", "nombres": "Rosa Elvira", "sin_documento": True,
                                          "fecha_nacimiento": "1941-03-12"})
    assert r.status_code == 409
    d = r.json()["detail"]
    assert d["requiere_confirmacion"] is True
    assert d["coincidencias"][0]["persona"]["id"] == p["id"]

    # Confirmado explícitamente: se crea y queda auditado.
    r = admin.post("/api/personas", json={"apellidos": "PEREZ", "nombres": "Rosa Elvira", "sin_documento": True,
                                          "fecha_nacimiento": "1941-03-12", "confirmar_posible_duplicado": True,
                                          "motivo_confirmacion": "Homónima, verificado en entrevista"})
    assert r.status_code == 201
    db = session_factory()()
    fila = db.execute(select(Auditoria).where(Auditoria.entidad_id == r.json()["id"], Auditoria.accion == "crear")).scalar_one()
    assert fila.detalle["posibles_duplicados_confirmados"][0]["legajo"] == p["numero_legajo"]
    db.close()


def test_persona_sin_documento_y_correccion_de_dni(admin):
    p = nueva_persona(admin, numero_documento=None, sin_documento=True, motivo_sin_documento="Extraviado")
    assert p["numero_documento"] is None and p["sin_documento"] is True

    # No puede declararse sin documento y a la vez cargar un número.
    r = admin.post("/api/personas", json={"apellidos": "X", "nombres": "Y", "sin_documento": True, "numero_documento": "123"})
    assert r.status_code == 400

    # Se le carga el DNI cuando aparece.
    r = admin.patch(f"/api/personas/{p['id']}", json={"sin_documento": False, "tipo_documento": "DNI", "numero_documento": "30111222"})
    assert r.status_code == 200, r.text
    # Corregir un DNI ya cargado exige motivo.
    r = admin.patch(f"/api/personas/{p['id']}", json={"numero_documento": "30111223"})
    assert r.status_code == 400
    r = admin.patch(f"/api/personas/{p['id']}", json={"numero_documento": "30111223", "motivo_cambio": "Error de tipeo"})
    assert r.status_code == 200
    assert r.json()["numero_documento"] == "30111223"


# ---------------------------------------------------------------- 2. ingreso previo


def test_asociar_ingreso_previo_a_legajo(admin):
    r = admin.post("/api/ingresos", json={"asunto": "Nota de hospital", "remitente": "Hospital",
                                          "persona_mencionada": "Gómez Juan", "documento_mencionado": "5.987.321"})
    assert r.status_code == 201
    ingreso = r.json()
    assert ingreso["numero"].startswith("ME-") and ingreso["persona_id"] is None

    # Se adjunta el escaneo al ingreso antes de que exista el legajo.
    r = admin.post("/api/documentos", data={"tipo_documental_id": "7", "titulo": "Nota", "ingreso_id": ingreso["id"]},
                   files={"archivo": ("nota.pdf", PDF, "application/pdf")})
    assert r.status_code == 201, r.text
    doc = r.json()
    assert doc["persona_id"] is None

    p = nueva_persona(admin, apellidos="Gómez", nombres="Juan Carlos", numero_documento="5987321")
    detalle = admin.get(f"/api/ingresos/{ingreso['id']}").json()
    assert [s["id"] for s in detalle["sugerencias"]] == [p["id"]]

    r = admin.post(f"/api/ingresos/{ingreso['id']}/vincular", json={"persona_id": p["id"]})
    assert r.status_code == 200
    vinculado = r.json()
    assert vinculado["persona_id"] == p["id"]
    # El registro de origen se conserva.
    assert vinculado["numero"] == ingreso["numero"] and vinculado["asunto"] == "Nota de hospital"
    assert vinculado["persona_mencionada"] == "Gómez Juan"

    legajo = admin.get(f"/api/personas/{p['id']}").json()
    assert [i["id"] for i in legajo["ingresos"]] == [ingreso["id"]]
    assert [d["id"] for d in legajo["documentos"]] == [doc["id"]]


# ---------------------------------------------------------------- 3. casos


def test_crear_y_cerrar_caso_sin_eliminar_historial(admin):
    p = nueva_persona(admin)
    caso = nuevo_caso(admin, p["id"], motivo="Consulta inicial")
    assert caso["estado"] == "abierto"

    assert admin.post(f"/api/casos/{caso['id']}/estado", json={"estado": "en_seguimiento"}).status_code == 200
    # Cerrar exige motivo.
    assert admin.post(f"/api/casos/{caso['id']}/estado", json={"estado": "cerrado"}).status_code == 400
    r = admin.post(f"/api/casos/{caso['id']}/estado", json={"estado": "cerrado", "motivo": "Intervención finalizada"})
    assert r.status_code == 200 and r.json()["cerrado_en"]
    # Reabrir también exige motivo y conserva todo lo anterior.
    r = admin.post(f"/api/casos/{caso['id']}/estado", json={"estado": "abierto", "motivo": "Nueva demanda"})
    assert r.status_code == 200
    historial = admin.get(f"/api/casos/{caso['id']}").json()["historial_estados"]
    assert [h["estado_nuevo"] for h in historial] == ["abierto", "en_seguimiento", "cerrado", "abierto"]
    assert historial[2]["motivo"] == "Intervención finalizada"

    # Un segundo caso para la misma persona convive con el primero.
    nuevo_caso(admin, p["id"])
    assert len(admin.get(f"/api/personas/{p['id']}").json()["casos"]) == 2


def test_asignacion_y_reasignacion_conservan_historial(admin):
    crear_usuario("tec1", "Técnico", AREA_ADMISION)
    crear_usuario("tec2", "Técnico", AREA_ADMISION)
    usuarios = {u["nombre_completo"]: u["id"] for u in admin.get("/api/catalogos").json()["usuarios_asignables"]}
    p = nueva_persona(admin)
    caso = nuevo_caso(admin, p["id"], responsable_id=usuarios["Tec1"])
    assert [r["usuario"] for r in caso["responsables"]] == ["tec1"]

    r = admin.post(f"/api/casos/{caso['id']}/asignaciones", json={"usuario_id": usuarios["Tec2"], "reemplazar_actuales": True})
    assert r.status_code == 201
    c = r.json()
    assert [r["usuario"] for r in c["responsables"]] == ["tec2"]
    assert len(c["asignaciones"]) == 2 and c["asignaciones"][0]["hasta"] is not None

    # El tablero de cada técnico refleja su asignación actual.
    assert Cliente("tec2").get("/api/tablero").json()["mis_casos"][0]["id"] == caso["id"]
    assert Cliente("tec1").get("/api/tablero").json()["mis_casos"] == []


# ---------------------------------------------------------------- 4. expedientes


def test_varios_expedientes_para_una_persona(admin):
    p = nueva_persona(admin)
    caso = nuevo_caso(admin, p["id"])
    for numero, tipo, caso_id in (("EXP-1/2026", "administrativo", caso["id"]), ("J-99/2026", "judicial", None)):
        r = admin.post("/api/expedientes", json={"persona_id": p["id"], "numero": numero, "tipo": tipo, "caso_id": caso_id})
        assert r.status_code == 201, r.text
    legajo = admin.get(f"/api/personas/{p['id']}").json()
    assert sorted(e["numero"] for e in legajo["expedientes"]) == ["EXP-1/2026", "J-99/2026"]
    assert [e["numero"] for e in admin.get(f"/api/casos/{caso['id']}").json()["expedientes"]] == ["EXP-1/2026"]

    # Un expediente no puede vincularse a un caso de otra persona.
    otra = nueva_persona(admin, numero_documento="2000000", apellidos="OTRA")
    r = admin.post("/api/expedientes", json={"persona_id": otra["id"], "numero": "X", "tipo": "judicial", "caso_id": caso["id"]})
    assert r.status_code == 400


# ---------------------------------------------------------------- 5. documentos


def test_adjuntar_y_recuperar_documento(admin):
    p = nueva_persona(admin)
    r = admin.post("/api/documentos",
                   data={"tipo_documental_id": "3", "titulo": "Informe socioambiental", "persona_id": p["id"]},
                   files={"archivo": ("informe.pdf", PDF, "application/pdf")})
    assert r.status_code == 201, r.text
    doc = r.json()
    assert doc["tamano"] == len(PDF) and doc["advertencias"] == []

    r = admin.get(f"/api/documentos/{doc['id']}/archivo")
    assert r.status_code == 200 and r.content == PDF
    assert r.headers["content-type"] == "application/pdf"

    # Archivo idéntico: se acepta, avisa y no ocupa espacio adicional.
    r = admin.post("/api/documentos", data={"tipo_documental_id": "3", "titulo": "Copia", "persona_id": p["id"]},
                   files={"archivo": ("copia.pdf", PDF, "application/pdf")})
    assert r.status_code == 201 and r.json()["advertencias"]

    # Se valida el contenido real, no la extensión.
    r = admin.post("/api/documentos", data={"tipo_documental_id": "3", "titulo": "Falso", "persona_id": p["id"]},
                   files={"archivo": ("falso.pdf", b"MZ\x90\x00 ejecutable", "application/pdf")})
    assert r.status_code == 415

    # La baja es lógica y exige motivo.
    assert admin.post(f"/api/documentos/{doc['id']}/eliminar", json={"motivo": "Cargado por error"}).status_code == 200
    ids = [d["id"] for d in admin.get(f"/api/personas/{p['id']}").json()["documentos"]]
    assert doc["id"] not in ids


# ---------------------------------------------------------------- 6. permisos


def test_restringir_acciones_segun_permisos(admin):
    crear_usuario("mesa", "Mesa de Entrada", "División Asistencia Administrativa")
    crear_usuario("tec1", "Técnico", AREA_ADMISION)
    crear_usuario("tec2", "Técnico", AREA_PROMOCION)
    crear_usuario("adm_prom", "Administrativo de Área", AREA_PROMOCION)
    usuarios = {u["nombre_completo"]: u["id"] for u in admin.get("/api/catalogos").json()["usuarios_asignables"]}

    p = nueva_persona(admin)
    caso = nuevo_caso(admin, p["id"], area_id=1, responsable_id=usuarios["Tec1"])

    mesa = Cliente("mesa")
    assert mesa.post("/api/casos", json={"persona_id": p["id"]}).status_code == 403
    assert mesa.post("/api/admin/roles", json={"nombre": "x", "permisos": []}).status_code == 403

    # El técnico asignado puede modificar el caso; otro técnico solo consultarlo.
    tec1, tec2 = Cliente("tec1"), Cliente("tec2")
    assert tec1.post(f"/api/casos/{caso['id']}/estado", json={"estado": "en_seguimiento"}).status_code == 200
    assert tec2.get(f"/api/casos/{caso['id']}").status_code == 200
    assert tec2.post(f"/api/casos/{caso['id']}/estado", json={"estado": "pausado", "motivo": "x"}).status_code == 403
    # Tampoco puede reasignarse casos (sin permiso "derivar").
    assert tec2.post(f"/api/casos/{caso['id']}/asignaciones", json={"usuario_id": usuarios["Tec2"]}).status_code == 403

    # Alcance por área: el administrativo de Promoción no ve un legajo cuyo único caso es de otra área.
    adm = Cliente("adm_prom")
    assert adm.get(f"/api/personas/{p['id']}").status_code == 403
    assert adm.get("/api/personas", params={"q": "prueba"}).json() == []
    admin.patch(f"/api/casos/{caso['id']}", json={"area_id": 2})
    nuevo_caso(admin, p["id"], area_id=2)
    assert adm.get(f"/api/personas/{p['id']}").status_code == 200

    # Sin CSRF no se puede modificar nada aunque la sesión sea válida.
    del tec1.http.headers["X-CSRF-Token"]
    assert tec1.post(f"/api/casos/{caso['id']}/estado", json={"estado": "abierto"}).status_code == 403


def test_permisos_configurables_desde_panel(admin):
    crear_usuario("mesa", "Mesa de Entrada")
    roles = {r["nombre"]: r for r in admin.get("/api/admin/roles").json()}
    rol = roles["Mesa de Entrada"]
    p = nueva_persona(admin)
    assert Cliente("mesa").post("/api/casos", json={"persona_id": p["id"]}).status_code == 403

    rol["permisos"].append({"modulo": "casos", "accion": "crear", "alcance": "todos"})
    r = admin.put(f"/api/admin/roles/{rol['id']}", json={k: rol[k] for k in ("nombre", "descripcion", "activo", "permisos")})
    assert r.status_code == 200
    assert Cliente("mesa").post("/api/casos", json={"persona_id": p["id"]}).status_code == 201

    # El cambio de permisos queda auditado con el antes y el después.
    db = session_factory()()
    fila = db.execute(select(Auditoria).where(Auditoria.accion == "modificar_permisos")).scalar_one()
    assert len(fila.detalle["despues"]["permisos"]) == len(fila.detalle["antes"]["permisos"]) + 1
    db.close()

    # No se puede dejar al sistema sin administradores.
    roles = {r["nombre"]: r for r in admin.get("/api/admin/roles").json()}
    direc = roles["Dirección y Administración del Sistema"]
    sin_admin = [x for x in direc["permisos"] if x["modulo"] != "administracion"]
    r = admin.put(f"/api/admin/roles/{direc['id']}", json={**{k: direc[k] for k in ("nombre", "descripcion", "activo")}, "permisos": sin_admin})
    assert r.status_code == 409


# ---------------------------------------------------------------- 7. autoría


def test_registrar_autoria_de_las_operaciones(admin):
    crear_usuario("carga", "Carga de Datos")
    carga = Cliente("carga")
    p = nueva_persona(carga)
    carga.patch(f"/api/personas/{p['id']}", json={"telefono": "381-555"})
    acciones = admin.get("/api/auditoria", params={"persona_id": p["id"]}).json()
    por_accion = {a["accion"]: a for a in acciones}
    assert por_accion["crear"]["usuario"] == "Carga"
    assert por_accion["modificar"]["detalle"]["cambios"]["telefono"] == [None, "381-555"]


def test_auditoria_inmutable(admin):
    nueva_persona(admin)
    db = session_factory()()
    with pytest.raises(Exception, match="no admite modificaciones"):
        db.execute(text("UPDATE auditoria SET accion = 'otra'"))
    db.rollback()
    with pytest.raises(Exception, match="no admite modificaciones"):
        db.execute(text("DELETE FROM auditoria"))
    db.rollback()
    db.close()


# ---------------------------------------------------------------- 8. persistencia


def test_recuperar_informacion_despues_de_reiniciar(admin):
    p = nueva_persona(admin)
    r = admin.post("/api/documentos", data={"tipo_documental_id": "1", "titulo": "Carátula", "persona_id": p["id"]},
                   files={"archivo": ("c.pdf", PDF, "application/pdf")})
    doc_id = r.json()["id"]

    reset_engine()  # simula reinicio: se descartan conexiones y la aplicación se crea de nuevo
    nuevo = Cliente("admin")
    legajo = nuevo.get(f"/api/personas/{p['id']}").json()
    assert legajo["numero_legajo"] == p["numero_legajo"]
    assert nuevo.get(f"/api/documentos/{doc_id}/archivo").content == PDF

"""Avisos para las notificaciones del navegador."""

from __future__ import annotations

from conftest import AREA_ADMISION, crear_usuario, nueva_persona, nuevo_caso


def test_avisos_de_casos_asignados_y_por_asignar(admin, cliente):
    areas = {a["nombre"]: a["id"] for a in admin.get("/api/catalogos").json()["areas"]}
    crear_usuario("tec", "Técnico", AREA_ADMISION)
    tec = {u["nombre_completo"]: u["id"] for u in admin.get("/api/catalogos").json()["usuarios_asignables"]}["Tec"]
    p1 = nueva_persona(admin, apellidos="UNO", numero_documento="3000001")
    p2 = nueva_persona(admin, apellidos="DOS", nombres="Otro", numero_documento="3000002")
    c1 = nuevo_caso(admin, p1["id"], area_id=areas[AREA_ADMISION], responsable_id=tec)
    c2 = nuevo_caso(admin, p2["id"], area_id=areas[AREA_ADMISION])

    mios = cliente("tec").get("/api/avisos")
    assert mios.status_code == 200
    assert mios.json()["avisos"]["casos_asignados"] == [c1["id"]]
    assert "casos_sin_asignar" not in mios.json()["avisos"]  # un técnico no deriva

    todos = admin.get("/api/avisos").json()["avisos"]
    assert c2["id"] in todos["casos_sin_asignar"]
    assert c1["id"] not in todos["casos_sin_asignar"]
    # No viajan nombres ni datos: solo identificadores.
    assert all(isinstance(x, str) for lista in todos.values() for x in lista)


def test_avisos_requieren_sesion():
    from fastapi.testclient import TestClient

    from sulam.main import crear_app

    assert TestClient(crear_app()).get("/api/avisos").status_code in (401, 403)

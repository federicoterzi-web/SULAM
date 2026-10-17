"""Casos en el mapa para organizar visitas."""

from __future__ import annotations

from conftest import AREA_ADMISION, AREA_PROMOCION, crear_usuario, nueva_persona, nuevo_caso


def _areas(admin):
    return {a["nombre"]: a["id"] for a in admin.get("/api/catalogos").json()["areas"]}


def test_ubicacion_y_mapa(admin, cliente):
    areas = _areas(admin)
    crear_usuario("tec", "Técnico", AREA_ADMISION)
    crear_usuario("otro", "Técnico", AREA_PROMOCION)
    tec_id = {u["nombre_completo"]: u["id"] for u in admin.get("/api/catalogos").json()["usuarios_asignables"]}["Tec"]
    p1 = nueva_persona(admin, apellidos="UNO", numero_documento="1111111", domicilio="Calle 1")
    p2 = nueva_persona(admin, apellidos="DOS", nombres="Otra", numero_documento="2222222")
    p3 = nueva_persona(admin, apellidos="TRES", nombres="Otre", numero_documento="3333333")
    c1 = nuevo_caso(admin, p1["id"], area_id=areas[AREA_ADMISION], responsable_id=tec_id, indicadores=["maltrato.fisico"])
    nuevo_caso(admin, p2["id"], area_id=areas[AREA_ADMISION])
    reservado = nuevo_caso(admin, p3["id"], area_id=areas[AREA_ADMISION], reservado=True)

    tec = cliente("tec")
    # El técnico asignado marca el domicilio con el GPS durante la visita.
    r = tec.put(f"/api/personas/{p1['id']}/ubicacion", json={"lat": -26.81, "lng": -65.22, "origen": "gps"})
    assert r.status_code == 200 and r.json()["lat"] == -26.81
    assert tec.put(f"/api/personas/{p1['id']}/ubicacion", json={"lat": -34.6, "lng": -58.4}).status_code == 400
    admin.put(f"/api/personas/{p2['id']}/ubicacion", json={"lat": -26.84, "lng": -65.2})
    admin.put(f"/api/personas/{p3['id']}/ubicacion", json={"lat": -26.85, "lng": -65.21})

    mios = tec.get("/api/mapa/casos").json()
    assert [x["caso_id"] for x in mios["puntos"]] == [c1["id"]] and mios["puntos"][0]["maltrato"] is True
    todos = cliente("otro").get("/api/mapa/casos", params={"de": "todos"}).json()
    ids = {x["caso_id"] for x in todos["puntos"]}
    assert c1["id"] in ids and reservado["id"] not in ids  # el reservado no aparece para quien no lo ve
    assert reservado["id"] in {x["caso_id"] for x in admin.get("/api/mapa/casos", params={"de": "todos"}).json()["puntos"]}
    assert len(todos["partida"]) == 2

    # Quitar la ubicación lo pasa a «sin ubicación».
    admin.put(f"/api/personas/{p2['id']}/ubicacion", json={"lat": None, "lng": None})
    sin = admin.get("/api/mapa/casos", params={"de": "todos"}).json()["sin_ubicacion"]
    assert [x["persona"]["id"] for x in sin] == [p2["id"]]


def test_tecnico_no_ubica_personas_ajenas(admin, cliente):
    crear_usuario("tec", "Técnico", AREA_ADMISION)
    p = nueva_persona(admin)
    nuevo_caso(admin, p["id"])
    assert cliente("tec").put(f"/api/personas/{p['id']}/ubicacion", json={"lat": -26.8, "lng": -65.2}).status_code == 403

from conftest import AREA_ADMISION, crear_usuario, nueva_persona, nuevo_caso


def _ids(admin):
    return {u["nombre_completo"]: u["id"] for u in admin.get("/api/catalogos").json()["usuarios_asignables"]}


def test_baja_con_casos_pide_decidir(admin):
    crear_usuario("tec1", "Técnico", AREA_ADMISION)
    crear_usuario("tec2", "Técnico", AREA_ADMISION)
    ids = _ids(admin)
    p1 = nueva_persona(admin)
    p2 = nueva_persona(admin, apellidos="OTRO", nombres="Nombre", numero_documento="2000002")
    c1 = nuevo_caso(admin, p1["id"], responsable_id=ids["Tec1"])
    c2 = nuevo_caso(admin, p2["id"], responsable_id=ids["Tec1"])
    admin.post(f"/api/casos/{c2['id']}/estado", json={"estado": "cerrado", "motivo": "Intervención finalizada"})
    assert admin.get(f"/api/admin/usuarios/{ids['Tec1']}/casos-a-cargo").json()["cantidad"] == 1  # el cerrado no cuenta
    # Sin decidir, no se da de baja.
    r = admin.patch(f"/api/admin/usuarios/{ids['Tec1']}", json={"activo": False})
    assert r.status_code == 409 and r.json()["detail"]["casos"] == 1
    assert admin.get(f"/api/admin/usuarios").json()  # sigue activo
    # Pasarlos a otra persona.
    r = admin.patch(f"/api/admin/usuarios/{ids['Tec1']}", json={"activo": False, "reasignar_a": ids["Tec2"]})
    assert r.status_code == 200 and r.json()["activo"] is False
    caso = admin.get(f"/api/casos/{c1['id']}").json()
    assert [x["usuario"] for x in caso["responsables"]] == ["tec2"]
    assert any(a["hasta"] for a in caso["asignaciones"])  # el historial se conserva


def test_baja_dejando_casos_sin_asignar(admin):
    crear_usuario("tec1", "Técnico", AREA_ADMISION)
    ids = _ids(admin)
    c = nuevo_caso(admin, nueva_persona(admin)["id"], responsable_id=ids["Tec1"])
    assert admin.patch(f"/api/admin/usuarios/{ids['Tec1']}", json={"activo": False, "dejar_sin_asignar": True}).status_code == 200
    assert admin.get(f"/api/casos/{c['id']}").json()["responsables"] == []
    assert [x["id"] for x in admin.get("/api/casos", params={"sin_responsable": True}).json()] == [c["id"]]


def test_baja_no_puede_pasar_casos_a_alguien_inactivo(admin):
    crear_usuario("tec1", "Técnico", AREA_ADMISION)
    crear_usuario("tec2", "Técnico", AREA_ADMISION)
    ids = _ids(admin)
    nuevo_caso(admin, nueva_persona(admin)["id"], responsable_id=ids["Tec1"])
    admin.patch(f"/api/admin/usuarios/{ids['Tec2']}", json={"activo": False})
    r = admin.patch(f"/api/admin/usuarios/{ids['Tec1']}", json={"activo": False, "reasignar_a": ids["Tec2"]})
    assert r.status_code == 400
    # Un usuario sin casos se da de baja sin preguntar.
    assert admin.patch(f"/api/admin/usuarios/{ids['Tec2']}", json={"activo": True}).status_code == 200

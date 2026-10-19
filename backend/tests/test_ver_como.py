"""Modo debug «Ver como»: quien administra ve SULAM con los permisos de otro rol, solo lectura."""
from conftest import crear_usuario


def _rol(admin, nombre):
    return next(r for r in admin.get("/api/admin/roles").json() if r["nombre"] == nombre)["id"]


def test_ver_como_cambia_permisos_y_es_de_solo_lectura(admin):
    mesa = _rol(admin, "Mesa de Entrada")
    r = admin.get("/api/auth/me", headers={"X-Ver-Como": str(mesa)})
    assert r.status_code == 200
    yo = r.json()
    assert yo["ver_como"] == {"rol": "Mesa de Entrada"}
    assert yo["roles"] == ["Mesa de Entrada"]
    assert "administracion.administrar" not in yo["permisos"]
    assert "mesa_entrada.crear" in yo["permisos"]
    # sin la cabecera sigue siendo el administrador
    assert admin.get("/api/auth/me").json()["ver_como"] is None
    # como Mesa de Entrada no entra a administración
    assert admin.get("/api/admin/usuarios", headers={"X-Ver-Como": str(mesa)}).status_code == 403
    # y no puede guardar nada
    r = admin.post("/api/personas", json={}, headers={"X-Ver-Como": str(mesa)})
    assert r.status_code == 403 and "solo lectura" in r.json()["detail"]
    # el tablero de ese rol se puede ver
    assert admin.get("/api/inicio", headers={"X-Ver-Como": str(mesa)}).status_code == 200


def test_ver_como_solo_para_administradores(cliente, admin):
    mesa = _rol(admin, "Mesa de Entrada")
    crear_usuario("tecnica1", "Técnico")
    c = cliente("tecnica1")
    r = c.get("/api/auth/me", headers={"X-Ver-Como": str(mesa)})
    assert r.status_code == 403
    assert c.get("/api/admin/ver-como").status_code == 403


def test_opciones_ver_como(admin):
    o = admin.get("/api/admin/ver-como").json()
    assert any(r["nombre"] == "Técnico" for r in o["roles"]) and o["areas"]


def test_ver_como_con_alcance_de_area(admin):
    jefe = _rol(admin, "Jefe/a de departamento")
    area = admin.get("/api/admin/ver-como").json()["areas"][0]["id"]
    h = {"X-Ver-Como": str(jefe), "X-Ver-Como-Area": str(area)}
    assert admin.get("/api/casos", headers=h).status_code == 200
    assert admin.get("/api/inicio", headers=h).status_code == 200
    assert admin.get("/api/agenda", headers=h).status_code in (200, 422)

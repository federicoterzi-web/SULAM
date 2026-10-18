"""Diseño de los tableros por perfil: orden, ancho y visibilidad, guardados desde Administración."""

from __future__ import annotations

from conftest import AREA_ADMISION, crear_usuario


def _ids(c):
    return [b["id"] for b in c.get("/api/inicio").json()["diseno"]]


def test_diseno_original_y_personalizado(admin, cliente):
    crear_usuario("tec", "Técnico", AREA_ADMISION)
    t = cliente("tec")
    r = t.get("/api/inicio").json()
    assert r["perfil"] == "tecnico"
    assert _ids(t) == ["novedades", "pases", "pedidos", "indicadores", "para_terminar", "mis_casos"]  # el original
    todos = admin.get("/api/inicio/disenos").json()
    tec = next(x for x in todos if x["codigo"] == "tecnico")
    assert tec["personalizado"] is False and "Técnico" in tec["roles"]
    # El administrador reordena, cambia anchos y oculta bloques.
    nuevo = [
        {"id": "mis_casos", "ancho": 8, "visible": True},
        {"id": "indicadores", "ancho": 4, "visible": True},
        {"id": "novedades", "ancho": 12, "visible": False},
        {"id": "para_terminar", "ancho": 6, "visible": True},
    ]
    assert admin.put("/api/inicio/disenos/tecnico", json={"bloques": nuevo}).status_code == 200
    d = t.get("/api/inicio").json()["diseno"]
    # Los bloques que no se mencionaron (pases, pedidos) quedan al final; los ocultos no se envían.
    assert [b["id"] for b in d] == ["mis_casos", "indicadores", "para_terminar", "pases", "pedidos"]
    assert d[0]["ancho"] == 8 and d[1]["ancho"] == 4
    assert next(x for x in admin.get("/api/inicio/disenos").json() if x["codigo"] == "tecnico")["personalizado"] is True
    # Otro tablero no cambia.
    assert next(x for x in admin.get("/api/inicio/disenos").json() if x["codigo"] == "jefatura")["personalizado"] is False
    # Restablecer vuelve al original.
    assert admin.delete("/api/inicio/disenos/tecnico").status_code == 204
    assert _ids(t) == ["novedades", "pases", "pedidos", "indicadores", "para_terminar", "mis_casos"]


def test_validaciones_y_permiso(admin, cliente):
    crear_usuario("tec", "Técnico", AREA_ADMISION)
    t = cliente("tec")
    ok = [{"id": "mis_casos", "ancho": 12, "visible": True}]
    assert t.put("/api/inicio/disenos/tecnico", json={"bloques": ok}).status_code == 403  # solo quien administra
    assert t.get("/api/inicio/disenos").status_code == 403
    assert admin.put("/api/inicio/disenos/inexistente", json={"bloques": ok}).status_code == 404
    assert admin.put("/api/inicio/disenos/tecnico", json={"bloques": [{"id": "no_existe", "ancho": 6, "visible": True}]}).status_code == 400
    assert admin.put("/api/inicio/disenos/tecnico", json={"bloques": ok + ok}).status_code == 400  # repetido
    assert admin.put("/api/inicio/disenos/tecnico", json={"bloques": [{"id": "mis_casos", "ancho": 1, "visible": True}]}).status_code == 422
    assert admin.put("/api/inicio/disenos/tecnico", json={"bloques": [{"id": "mis_casos", "ancho": 6, "visible": False}]}).status_code == 400  # nada visible
    # Un bloque de otro perfil no sirve.
    assert admin.put("/api/inicio/disenos/tecnico", json={"bloques": [{"id": "equipo", "ancho": 6, "visible": True}]}).status_code == 400

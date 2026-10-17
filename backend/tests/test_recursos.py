"""Red de recursos con ubicación."""

from __future__ import annotations

import io
import json

from conftest import crear_usuario

CENTRO = {
    "tipo": "centro_jubilados",
    "nombre": "Centro de Jubilados Barrio Ejemplo (ficticio)",
    "direccion": "Calle Ficticia 123",
    "localidad": "San Miguel de Tucumán",
    "departamento": "Capital",
    "lat": -26.83,
    "lng": -65.21,
    "telefono": "381 000-0000",
    "referente": "Presidenta (ficticia)",
}


def test_alta_busqueda_y_filtros(admin):
    r = admin.post("/api/recursos", json=CENTRO)
    assert r.status_code == 201, r.text
    cuidadora = admin.post(
        "/api/recursos",
        json={"tipo": "cuidador", "nombre": "Cuidadora Ficticia", "departamento": "Capital", "zonas": ["Yerba Buena", "Tafí Viejo"],
              "formacion": "Curso de cuidados domiciliarios 2025"},
    ).json()
    caps = admin.post(
        "/api/recursos",
        json={"tipo": "institucion", "categoria": "salud", "nombre": "CAPS Ejemplo", "departamento": "Cruz Alta", "lat": -26.82, "lng": -65.1},
    ).json()
    assert caps["categoria"] == "salud"

    todos = admin.get("/api/recursos").json()
    assert len(todos) == 3
    assert [x["nombre"] for x in admin.get("/api/recursos", params={"q": "ejemplo"}).json()] == ["CAPS Ejemplo", CENTRO["nombre"]]
    assert [x["id"] for x in admin.get("/api/recursos", params={"tipo": "cuidador"}).json()] == [cuidadora["id"]]
    # La cuidadora aparece también en los departamentos donde trabaja.
    assert cuidadora["id"] in {x["id"] for x in admin.get("/api/recursos", params={"departamento": "Yerba Buena"}).json()}

    # Baja lógica: deja de aparecer pero se conserva.
    assert admin.patch(f"/api/recursos/{caps['id']}", json={"activo": False}).json()["activo"] is False
    assert len(admin.get("/api/recursos").json()) == 2
    assert len(admin.get("/api/recursos", params={"inactivos": True}).json()) == 3


def test_validaciones(admin):
    assert admin.post("/api/recursos", json={**CENTRO, "tipo": "otro"}).status_code == 400
    assert admin.post("/api/recursos", json={**CENTRO, "lat": -34.6, "lng": -58.4}).status_code == 400  # Buenos Aires
    assert admin.post("/api/recursos", json={**CENTRO, "lng": None}).status_code == 400
    assert admin.post("/api/recursos", json={"tipo": "cuidador", "nombre": "X Y", "zonas": ["Narnia"]}).status_code == 400


def test_permisos(admin, cliente):
    crear_usuario("tec", "Técnico")
    crear_usuario("mesa", "Mesa de Entrada")
    tec, mesa = cliente("tec"), cliente("mesa")
    del_admin = admin.post("/api/recursos", json=CENTRO).json()
    propio = tec.post("/api/recursos", json={**CENTRO, "nombre": "Centro de día cargado por técnico"}).json()
    assert tec.patch(f"/api/recursos/{propio['id']}", json={"telefono": "381 111"}).status_code == 200
    assert tec.patch(f"/api/recursos/{del_admin['id']}", json={"telefono": "381 111"}).status_code == 403
    assert len(mesa.get("/api/recursos").json()) == 2
    assert mesa.post("/api/recursos", json=CENTRO).status_code == 403


def test_geocodificar(admin, monkeypatch):
    from sulam.routers import recursos

    def falso(pedido, timeout):
        assert "bounded=1" in pedido.full_url and pedido.get_header("User-agent").startswith("SULAM")
        return io.BytesIO(json.dumps([{"lat": "-26.8", "lon": "-65.2", "display_name": "Calle Ficticia, Tucumán"}]).encode())

    monkeypatch.setattr(recursos, "urlopen", falso)
    r = admin.get("/api/recursos/geocodificar", params={"q": "Calle Ficticia 123"})
    assert r.json() == [{"lat": -26.8, "lng": -65.2, "descripcion": "Calle Ficticia, Tucumán"}]

    def caido(pedido, timeout):
        raise OSError("sin red")

    monkeypatch.setattr(recursos, "urlopen", caido)
    assert admin.get("/api/recursos/geocodificar", params={"q": "Calle Ficticia 123"}).status_code == 502


def test_mapa_permitido_en_la_politica_de_seguridad(tmp_path, monkeypatch):
    from fastapi.testclient import TestClient

    from sulam.config import get_settings
    from sulam.main import crear_app

    (tmp_path / "index.html").write_text("<html></html>")
    monkeypatch.setenv("SULAM_FRONTEND_DIST", str(tmp_path))
    get_settings.cache_clear()
    try:
        csp = TestClient(crear_app()).get("/").headers["content-security-policy"]
        assert "img-src 'self' data: blob: https://tile.openstreetmap.org;" in csp
    finally:
        monkeypatch.undo()
        get_settings.cache_clear()


def test_migracion_agrega_permisos_a_roles_existentes(db):
    """La migración 0010 corre sobre una base con roles ya creados (instalaciones en uso)."""
    from alembic import command
    from sqlalchemy import text

    from sulam.cli import _alembic_cfg

    command.downgrade(_alembic_cfg(), "0009")
    try:
        assert db.execute(text("SELECT count(*) FROM roles_permisos WHERE modulo = 'recursos'")).scalar_one() == 0
    finally:
        db.rollback()
        command.upgrade(_alembic_cfg(), "head")
    filas = dict(
        db.execute(
            text(
                "SELECT r.nombre, count(*) FROM roles_permisos p JOIN roles r ON r.id = p.rol_id "
                "WHERE p.modulo = 'recursos' GROUP BY r.nombre"
            )
        ).all()
    )
    assert filas["Técnico"] == 3 and filas["Mesa de Entrada"] == 1

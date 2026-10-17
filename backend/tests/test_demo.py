"""Los datos de demostración se cargan en una base nueva y cada rol ve algo."""

from __future__ import annotations

from datetime import date

from conftest import Cliente


def test_datos_demo_completos():
    from sulam.cli import cmd_datos_demo
    from sulam.seed import PASSWORD_DEMO, USUARIOS_DEMO

    cmd_datos_demo(None)
    for usuario, *_ in USUARIOS_DEMO:
        c = Cliente(usuario, PASSWORD_DEMO)
        r = c.get("/api/inicio")
        assert r.status_code == 200, (usuario, r.text)
    d = Cliente("direccion", PASSWORD_DEMO)
    est = d.get("/api/estadisticas/casos", params={"desde": f"{date.today().year - 1}-01-01"}).json()
    assert est["total"] >= 30
    jefa = Cliente("jefa_admision", PASSWORD_DEMO).get("/api/inicio").json()["datos"]
    assert jefa["sin_responsable"], "la jefa tiene casos para asignar"
    p = Cliente("personal", PASSWORD_DEMO)
    assert p.get("/api/personal/pendientes").json()["para_registrar"] >= 1
    assert len(p.get("/api/personal/hoy").json()) >= 2
    assert Cliente("registro", PASSWORD_DEMO).get("/api/archivo/pendientes").json()["cantidad"] >= 2
    assert d.get("/api/estadisticas/interno").status_code == 200

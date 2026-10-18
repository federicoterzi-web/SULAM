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


def test_datos_demo_con_personal_real(tmp_path):
    """El personal importado ocupa los lugares de técnicos y mesa; los casos ficticios quedan a su nombre."""
    import json
    from argparse import Namespace

    from sqlalchemy import select

    from sulam.cli import cmd_datos_demo
    from sulam.db import session_factory
    from sulam.models import Caso, CasoAsignacion, Usuario
    from sulam.personal_importar import importar
    from sulam.seed import PASSWORD_DEMO, inicializar_catalogos

    semana = {str(d): ["08:00", "13:00"] for d in range(5)}
    adm, prom = "Departamento Admisión de Casos y Recepción de Denuncias", "Departamento Promoción Integral de Derechos"
    filas = [{"nombre": f"Ficticio{i} Nombre{i}", "area": adm if i < 3 else prom, "rol": "Técnico", "id_reloj": str(70 + i), "desde": "2026-10-05", "horario": semana} for i in range(5)]
    filas.append({"nombre": "Ficticio Mesa", "area": "División Asistencia Administrativa", "rol": "Mesa de Entrada", "id_reloj": "80", "desde": "2026-10-05", "horario": semana})
    ruta = tmp_path / "p.json"
    ruta.write_text(json.dumps({"agentes": filas}), encoding="utf-8")
    db = session_factory()()
    inicializar_catalogos(db)
    importar(db, ruta, crear_usuarios=True, password_comun="Clave-prueba-2026")
    db.commit()
    db.close()

    cmd_datos_demo(Namespace(con_personal_real=True))

    db = session_factory()()
    reales = {u.id for u in db.execute(select(Usuario).where(Usuario.usuario.like("ficticio%"))).scalars()}
    asignados = [a.usuario_id for a in db.execute(select(CasoAsignacion)).scalars()]
    assert sum(1 for x in asignados if x in reales) >= 10, "los casos ficticios quedaron a nombre del personal real"
    assert db.execute(select(Usuario).where(Usuario.usuario == "tecnica1")).first() is None, "no se crea el demo que ya ocupa el real"
    assert db.execute(select(Usuario).where(Usuario.usuario == "direccion")).first() is not None
    assert db.execute(select(Caso.id)).first() is not None
    db.close()
    c = Cliente("ficticio0.nombre0", "Clave-prueba-2026")
    assert c.http.post("/api/auth/login", json={"usuario": "ficticio0.nombre0", "password": "Clave-prueba-2026"}).status_code == 200

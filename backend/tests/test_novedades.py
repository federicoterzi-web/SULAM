"""Novedades de la Dirección y de las áreas, con confirmación de lectura."""

from __future__ import annotations

from conftest import AREA_ADMISION, AREA_PROMOCION, PDF, crear_usuario


def test_novedades(admin, cliente):
    crear_usuario("directora", "Directora", "Dirección de Adultos Mayores")
    crear_usuario("jefa", "Jefe/a de departamento", AREA_ADMISION)
    crear_usuario("tec1", "Técnico", AREA_ADMISION)
    crear_usuario("tec2", "Técnico", AREA_PROMOCION)
    directora, jefa, tec1, tec2 = (cliente(u) for u in ("directora", "jefa", "tec1", "tec2"))
    areas = {a["nombre"]: a["id"] for a in admin.get("/api/catalogos").json()["areas"]}

    # La Directora publica una circular para todos, con PDF.
    r = directora.post("/api/novedades", data={"titulo": "Circular 1/2026: horario de verano", "cuerpo": "<p>Desde el <b>lunes</b>.</p><script>x</script>"},
                       files={"archivo": ("circular.pdf", PDF, "application/pdf")})
    assert r.status_code == 201, r.text
    general = r.json()
    assert general["cuerpo"] == "<p>Desde el <b>lunes</b>.</p>" and general["archivo"]["nombre"] == "circular.pdf"

    # La jefa publica para su área; no puede para todos ni para otra área.
    area = jefa.post("/api/novedades", data={"titulo": "Reunión de equipo", "cuerpo": "Jueves 10 h", "area_id": str(areas[AREA_ADMISION])}).json()
    assert jefa.post("/api/novedades", data={"titulo": "Para todos", "cuerpo": "x x x"}).status_code == 403
    assert jefa.post("/api/novedades", data={"titulo": "Otra área", "cuerpo": "x x x", "area_id": str(areas[AREA_PROMOCION])}).status_code == 403
    assert tec1.post("/api/novedades", data={"titulo": "No puedo", "cuerpo": "x x x"}).status_code == 403

    # Cada uno ve las generales y las de su área.
    assert {n["titulo"] for n in tec1.get("/api/novedades").json()["novedades"]} == {general["titulo"], area["titulo"]}
    assert {n["titulo"] for n in tec2.get("/api/novedades").json()["novedades"]} == {general["titulo"]}
    assert tec2.get(f"/api/novedades/{area['id']}/lecturas").status_code == 403
    assert tec1.get("/api/novedades/pendientes").json()["cantidad"] == 2
    assert tec2.get(f"/api/novedades/{general['id']}/archivo").content == PDF

    # Confirmación de lectura.
    assert tec1.post(f"/api/novedades/{general['id']}/confirmar").status_code == 200
    assert tec1.post(f"/api/novedades/{general['id']}/confirmar").status_code == 200  # una sola vez
    assert tec1.get("/api/novedades/pendientes").json()["cantidad"] == 1
    l = directora.get(f"/api/novedades/{general['id']}/lecturas").json()
    assert "Tec1" in [x["usuario"]["nombre_completo"] for x in l["confirmaron"]]
    assert "Tec2" in [x["usuario"]["nombre_completo"] for x in l["faltan"]]
    lista = directora.get("/api/novedades").json()["novedades"]
    g = next(n for n in lista if n["id"] == general["id"])
    assert g["lecturas"]["confirmaron"] == 1 and g["lecturas"]["destinatarios"] >= 4
    # La jefa sigue las de su área (no las generales).
    assert jefa.get(f"/api/novedades/{area['id']}/lecturas").json()["faltan"][0]["usuario"]["nombre_completo"] == "Tec1"
    assert jefa.get(f"/api/novedades/{general['id']}/lecturas").status_code == 403

    # Retirar.
    assert directora.post(f"/api/novedades/{general['id']}/retirar").json()["ok"]
    assert general["id"] not in {n["id"] for n in tec2.get("/api/novedades").json()["novedades"]}


def test_novedades_dirigidas_por_rol(admin, cliente, db):
    from sulam.models import Rol

    crear_usuario("directora", "Directora", "Dirección de Adultos Mayores")
    crear_usuario("jefa", "Jefe/a de departamento", AREA_ADMISION)
    crear_usuario("jefe2", "Jefe/a de departamento", AREA_PROMOCION)
    crear_usuario("tec1", "Técnico", AREA_ADMISION)
    crear_usuario("tec2", "Técnico", AREA_PROMOCION)
    directora, jefa, jefe2, tec1, tec2 = (cliente(u) for u in ("directora", "jefa", "jefe2", "tec1", "tec2"))
    areas = {a["nombre"]: a["id"] for a in admin.get("/api/catalogos").json()["areas"]}
    rol = {r.nombre: r.id for r in db.query(Rol).all()}
    nombres = lambda c: {n["titulo"] for n in c.get("/api/novedades").json()["novedades"]}  # noqa: E731

    # Para toda la Dirección, pero solo para quienes son jefes/as de departamento.
    r = directora.post("/api/novedades", data={"titulo": "Reunión de jefaturas", "cuerpo": "Lunes 9 h", "roles_ids": str(rol["Jefe/a de departamento"])})
    assert r.status_code == 201, r.text
    jefaturas = r.json()
    assert [x["nombre"] for x in jefaturas["roles"]] == ["Jefe/a de departamento"]
    assert "Reunión de jefaturas" in nombres(jefa) and "Reunión de jefaturas" in nombres(jefe2)
    assert "Reunión de jefaturas" not in nombres(tec1) and "Reunión de jefaturas" not in nombres(tec2)
    assert tec1.get("/api/novedades/pendientes").json()["cantidad"] == 0
    assert jefa.get("/api/novedades/pendientes").json()["cantidad"] == 1
    assert tec1.post(f"/api/novedades/{jefaturas['id']}/confirmar").status_code == 403  # no es para su rol
    assert [a for a in tec1.get("/api/avisos").json()["avisos"]["novedades"]] == []
    # Los destinatarios son solo las dos jefaturas (la Directora, que publica, no cuenta).
    lectura = directora.get(f"/api/novedades/{jefaturas['id']}/lecturas").json()
    assert sorted(x["usuario"]["nombre_completo"] for x in lectura["faltan"]) == ["Jefa", "Jefe2"]
    assert jefa.post(f"/api/novedades/{jefaturas['id']}/confirmar").status_code == 200
    mia = next(n for n in directora.get("/api/novedades").json()["novedades"] if n["id"] == jefaturas["id"])
    assert mia["lecturas"] == {"destinatarios": 2, "confirmaron": 1}

    # Un área y un rol a la vez: los técnicos de Admisión, no los de Promoción.
    r = directora.post(
        "/api/novedades",
        data={"titulo": "Capacitación de técnicos de Admisión", "cuerpo": "Miércoles", "area_id": str(areas[AREA_ADMISION]), "roles_ids": str(rol["Técnico"])},
    )
    assert r.status_code == 201, r.text
    assert "Capacitación de técnicos de Admisión" in nombres(tec1)
    assert "Capacitación de técnicos de Admisión" not in nombres(tec2)
    assert "Capacitación de técnicos de Admisión" not in nombres(jefa)  # misma área, otro rol

    # Varios roles a la vez.
    directora.post("/api/novedades", data={"titulo": "Jefaturas y técnicos", "cuerpo": "x x x", "roles_ids": f"{rol['Técnico']},{rol['Jefe/a de departamento']}"})
    assert all("Jefaturas y técnicos" in nombres(c) for c in (jefa, jefe2, tec1, tec2))

    # La jefa también puede elegir roles, pero solo dentro de su área.
    assert jefa.get("/api/novedades").json()["roles_publicables"]
    r = jefa.post("/api/novedades", data={"titulo": "Solo técnicos de mi área", "cuerpo": "x x x", "area_id": str(areas[AREA_ADMISION]), "roles_ids": str(rol["Técnico"])})
    assert r.status_code == 201, r.text
    assert "Solo técnicos de mi área" in nombres(tec1) and "Solo técnicos de mi área" not in nombres(tec2)
    assert jefa.post("/api/novedades", data={"titulo": "Para todos los técnicos", "cuerpo": "x x x", "roles_ids": str(rol["Técnico"])}).status_code == 403

    # Un técnico no publica; roles inexistentes o inválidos se rechazan.
    assert tec1.get("/api/novedades").json()["roles_publicables"] == []
    assert directora.post("/api/novedades", data={"titulo": "Rol falso", "cuerpo": "x x x", "roles_ids": "9999"}).status_code == 400
    assert directora.post("/api/novedades", data={"titulo": "Rol roto", "cuerpo": "x x x", "roles_ids": "a,b"}).status_code == 400

    # Las estadísticas de lectura cuentan solo a los destinatarios del rol.
    from datetime import date

    hoy = date.today().isoformat()
    est = admin.get("/api/estadisticas/interno", params={"desde": hoy[:8] + "01", "hasta": hoy})
    assert est.status_code == 200, est.text
    filas = {f["etiqueta"]: f for f in est.json()["comunicacion"]["tablas"][0]["filas"]}
    assert filas["Reunión de jefaturas"]["destinatarios"] == 2
    assert "Jefe/a de departamento" in filas["Reunión de jefaturas"]["para"]

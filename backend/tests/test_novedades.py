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

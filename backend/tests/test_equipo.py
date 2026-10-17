"""Varios técnicos a cargo de un caso, todos responsables por igual."""

from __future__ import annotations

from conftest import AREA_ADMISION, crear_usuario, nueva_persona, nuevo_caso


def test_equipo_a_cargo(admin, cliente):
    for u in ("tec1", "tec2", "tec3"):
        crear_usuario(u, "Técnico", AREA_ADMISION)
    ids = {u["nombre_completo"]: u["id"] for u in admin.get("/api/catalogos").json()["usuarios_asignables"]}
    p = nueva_persona(admin)

    # Se crea con dos técnicos a cargo.
    caso = nuevo_caso(admin, p["id"], responsables_ids=[ids["Tec1"], ids["Tec2"], ids["Tec1"]])
    assert sorted(r["nombre_completo"] for r in caso["responsables"]) == ["Tec1", "Tec2"]
    for u in ("tec1", "tec2"):
        c = cliente(u)
        assert [x["id"] for x in c.get("/api/casos", params={"asignados_a_mi": True}).json()] == [caso["id"]]
        # Los dos pueden trabajar el caso.
        assert c.post(f"/api/casos/{caso['id']}/evolucion", json={"texto": f"Visita de {u} (prueba)"}).status_code == 201
    assert cliente("tec3").post(f"/api/casos/{caso['id']}/evolucion", json={"texto": "Intento sin estar a cargo"}).status_code == 403

    # Se cambia el equipo de una vez: sale Tec2, entra Tec3.
    r = admin.put(f"/api/casos/{caso['id']}/equipo", json={"usuarios_ids": [ids["Tec1"], ids["Tec3"]], "motivo": "Cambio de turno"})
    assert r.status_code == 200, r.text
    assert sorted(x["nombre_completo"] for x in r.json()["responsables"]) == ["Tec1", "Tec3"]
    hist = admin.get(f"/api/casos/{caso['id']}").json()["asignaciones"]
    assert len(hist) == 3 and sum(1 for a in hist if a["hasta"]) == 1
    assert cliente("tec2").get("/api/casos", params={"asignados_a_mi": True}).json() == []

    # Un técnico no cambia el equipo.
    assert cliente("tec1").put(f"/api/casos/{caso['id']}/equipo", json={"usuarios_ids": []}).status_code == 403
    # Se puede dejar sin nadie (para reasignar después).
    assert admin.put(f"/api/casos/{caso['id']}/equipo", json={"usuarios_ids": []}).json()["responsables"] == []

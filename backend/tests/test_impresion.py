"""Cola de impresión: las carátulas nuevas quedan pendientes y se imprimen en tanda."""

from __future__ import annotations

from conftest import AREA_ADMISION, crear_usuario, nueva_persona, nuevo_caso


def test_tanda_de_caratulas(admin, cliente, db):
    from sqlalchemy import text

    crear_usuario("jefa", "Carga de Datos", AREA_ADMISION)
    jefa = cliente("jefa")
    area = {a["nombre"]: a["id"] for a in admin.get("/api/catalogos").json()["areas"]}[AREA_ADMISION]
    mios = [nuevo_caso(jefa, nueva_persona(jefa, apellidos=f"TANDA{chr(65 + i)}", nombres=f"Nombre{chr(75 + i)}", numero_documento=str(20000000 + i * 1111))["id"], area_id=area) for i in range(6)]
    ajeno = nuevo_caso(admin, nueva_persona(admin, apellidos="AJENO", nombres="Otro", numero_documento="30000000")["id"])

    pendientes = jefa.get("/api/caratulas/pendientes").json()
    assert [c["id"] for c in pendientes] == [c["id"] for c in mios]  # en orden de actuación
    assert all(c["caratula_impresa_en"] is None for c in pendientes)
    assert ajeno["id"] in {c["id"] for c in admin.get("/api/caratulas/pendientes", params={"de": "todas"}).json()}
    assert ajeno["id"] not in {c["id"] for c in jefa.get("/api/caratulas/pendientes", params={"de": "area"}).json()}

    r = jefa.post("/api/caratulas/impresas", json={"caso_ids": [c["id"] for c in mios[:4]]})
    assert r.json() == {"marcadas": 4, "reimpresas": 0}
    assert len(jefa.get("/api/caratulas/pendientes").json()) == 2
    impreso = jefa.get(f"/api/casos/{mios[0]['id']}").json()
    assert impreso["caratula_impresa_en"] is not None

    # Reimprimir no cambia la primera impresión, pero queda en la auditoría.
    r = jefa.post("/api/caratulas/impresas", json={"caso_ids": [mios[0]["id"], mios[4]["id"]]})
    assert r.json() == {"marcadas": 1, "reimpresas": 1}
    assert jefa.get(f"/api/casos/{mios[0]['id']}").json()["caratula_impresa_en"] == impreso["caratula_impresa_en"]
    eventos = db.execute(text("SELECT count(*) FROM auditoria WHERE accion = 'imprimir_caratula'")).scalar_one()
    assert eventos == 6


def test_marcar_respeta_permisos(admin, cliente):
    crear_usuario("mesa", "Mesa de Entrada")
    caso = nuevo_caso(admin, nueva_persona(admin)["id"])
    mesa = cliente("mesa")
    assert mesa.get("/api/caratulas/pendientes").status_code == 403
    assert mesa.post("/api/caratulas/impresas", json={"caso_ids": [caso["id"]]}).status_code == 403
    assert admin.get(f"/api/casos/{caso['id']}").json()["caratula_impresa_en"] is None

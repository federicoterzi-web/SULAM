"""Carátula de legajo, registro de demanda y evolución del caso (modelos institucionales)."""

from __future__ import annotations

from conftest import AREA_ADMISION, Cliente, crear_usuario, nueva_persona, nuevo_caso

CARATULA = {
    "numero_actuacion": "123",
    "anio_actuacion": 2026,
    "fecha_ingreso": "2026-10-05",
    "motivo": "Vecina refiere que vive sola y sin recursos",
    "tipo_ingreso": "espontaneo",
    "tipo_ingreso_detalle": "presencial",
    "indicadores": ["maltrato.economico", "vulnerabilidad.habitacional"],
    "intervenciones": ["subsidio.alimentario", "derivacion"],
    "intervencion_derivacion": "CAPS del barrio",
    "persona": {"genero": "F", "departamento": "Capital", "cud": "en_tramite",
                "cobertura_salud": ["pami"], "telefono": "381-111"},
}


def test_caratula_al_crear_el_caso(admin):
    p = nueva_persona(admin, fecha_nacimiento="1945-02-01")
    caso = nuevo_caso(admin, p["id"], **CARATULA)
    car = caso["caratula"]
    assert car["numero_actuacion"] == "123" and car["fecha_ingreso"] == "2026-10-05"
    # Al marcar una subopción se guarda también el grupo.
    assert car["indicadores"] == ["maltrato", "maltrato.economico", "vulnerabilidad", "vulnerabilidad.habitacional"]
    assert car["antecedentes"] is False and car["fecha_ultimo_ingreso"] is None
    assert caso["motivo"] == CARATULA["motivo"]

    # Los datos personales de la carátula actualizan el legajo, con auditoría.
    legajo = admin.get(f"/api/personas/{p['id']}").json()
    assert legajo["genero"] == "F" and legajo["departamento"] == "Capital" and legajo["cud"] == "en_tramite"
    assert legajo["cobertura_salud"] == ["pami"] and legajo["telefono"] == "381-111"

    # Un segundo ingreso detecta los antecedentes en el sistema.
    segundo = nuevo_caso(admin, p["id"], fecha_ingreso="2026-10-20", tipo_ingreso="portal_sae")
    assert segundo["caratula"]["antecedentes"] is True
    assert segundo["caratula"]["fecha_ultimo_ingreso"] == "2026-10-05"


def test_caratula_valida_opciones(admin):
    p = nueva_persona(admin)
    r = admin.post("/api/casos", json={"persona_id": p["id"], "indicadores": ["maltrato.inventado"]})
    assert r.status_code == 400
    r = admin.post("/api/casos", json={"persona_id": p["id"], "tipo_ingreso": "portal_sae", "tipo_ingreso_detalle": "amparo"})
    assert r.status_code == 400
    caso = nuevo_caso(admin, p["id"], tipo_ingreso="mesa_entrada", tipo_ingreso_detalle="amparo")
    # Cambiar el tipo de ingreso descarta el detalle anterior.
    r = admin.patch(f"/api/casos/{caso['id']}/caratula", json={"tipo_ingreso": "derivada", "derivado_por": "mpf"})
    assert r.status_code == 200, r.text
    assert r.json()["caratula"]["tipo_ingreso_detalle"] is None
    assert r.json()["caratula"]["derivado_por"] == "mpf"


def test_registro_de_demanda_sobre_caratula(admin):
    crear_usuario("tec", "Técnico", AREA_ADMISION)
    ids = {u["nombre_completo"]: u["id"] for u in admin.get("/api/catalogos").json()["usuarios_asignables"]}
    p = nueva_persona(admin)
    caso = nuevo_caso(admin, p["id"], responsable_id=ids["Tec"], **CARATULA)

    # El formulario arranca con los datos de la carátula y del legajo.
    sug = admin.get(f"/api/casos/{caso['id']}/demanda-sugerida").json()
    assert sug["indicadores"] == caso["caratula"]["indicadores"]
    assert sug["tipo_ingreso"] == "espontaneo" and sug["departamento"] == "Capital"
    assert sug["agente_id"] == ids["Tec"] and sug["solicitud_expresa"] == CARATULA["motivo"]

    demanda = {k: v for k, v in sug.items() if k not in ("fecha",)}
    demanda.update({
        "solicitante_nombre": "Ana Vecina", "solicitante_vinculo": "Vecina",
        "cobertura_previsional": ["puam"], "discapacidades": ["motora"], "tipo_vivienda": "prestada",
        "estado_civil": "viudo", "tiene_hijos": True, "cantidad_hijos": 2, "vinculo_con_hijos": False,
        "convive_con": "Sola", "estado_funcional": "semidependiente", "tiene_autonomia": False,
        "barrio": "Villa 9 de Julio", "diagnosticos": "Hipertensión (ficticio)",
    })
    r = admin.post(f"/api/casos/{caso['id']}/demandas", json=demanda)
    assert r.status_code == 201, r.text
    d = r.json()
    assert d["receptor"]["usuario"] == "admin" and d["agente"]["usuario"] == "tec"
    assert d["datos_persona"]["numero_legajo"] == p["numero_legajo"]

    # Lo que corresponde al legajo se actualiza en el legajo.
    legajo = admin.get(f"/api/personas/{p['id']}").json()
    assert legajo["cobertura_previsional"] == ["puam"] and legajo["discapacidades"] == ["motora"]
    assert legajo["barrio"] == "Villa 9 de Julio"

    r = admin.post(f"/api/casos/{caso['id']}/demandas", json={"tipo_vivienda": "castillo"})
    assert r.status_code == 400

    detalle = admin.get(f"/api/casos/{caso['id']}").json()
    assert [x["id"] for x in detalle["demandas"]] == [d["id"]]


def test_evolucion_y_reserva(admin):
    crear_usuario("tec1", "Técnico", AREA_ADMISION)
    crear_usuario("tec2", "Técnico", AREA_ADMISION)
    ids = {u["nombre_completo"]: u["id"] for u in admin.get("/api/catalogos").json()["usuarios_asignables"]}
    p = nueva_persona(admin)
    caso = nuevo_caso(admin, p["id"], reservado=True, responsable_id=ids["Tec1"], **CARATULA)
    tec1, tec2 = Cliente("tec1"), Cliente("tec2")
    assert tec1.post(f"/api/casos/{caso['id']}/evolucion", json={"texto": "Visita domiciliaria realizada"}).status_code == 201
    assert tec1.post(f"/api/casos/{caso['id']}/demandas", json={"solicitante_nombre": "X"}).status_code == 201

    visto = tec1.get(f"/api/casos/{caso['id']}").json()
    assert visto["evoluciones"][0]["texto"] == "Visita domiciliaria realizada"

    ajeno = tec2.get(f"/api/casos/{caso['id']}").json()
    assert ajeno["evoluciones"] == [] and ajeno["caratula"]["indicadores"] == []
    assert ajeno["demandas"][0]["contenido_restringido"] is True and "solicitante_nombre" not in ajeno["demandas"][0]
    assert tec2.get(f"/api/demandas/{ajeno['demandas'][0]['id']}").status_code == 403
    assert tec2.post(f"/api/casos/{caso['id']}/evolucion", json={"texto": "x x"}).status_code == 403

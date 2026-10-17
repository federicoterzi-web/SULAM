"""Carátula de legajo, registro de demanda y evolución del caso (modelos institucionales)."""

from __future__ import annotations

from conftest import AREA_ADMISION, Cliente, crear_usuario, nueva_persona, nuevo_caso

CARATULA = {
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
    assert car["numero_actuacion"] == 1 and car["anio_actuacion"] == 2026 and caso["numero"] == "C-2026-00001"
    assert car["fecha_ingreso"] == "2026-10-05"
    # Al marcar una subopción se guarda también el grupo.
    assert car["indicadores"] == ["maltrato", "maltrato.economico", "vulnerabilidad", "vulnerabilidad.habitacional"]
    assert car["antecedentes"] is False and car["fecha_ultimo_ingreso"] is None
    assert caso["motivo"] == CARATULA["motivo"]

    # Los datos personales de la carátula actualizan el legajo, con auditoría.
    legajo = admin.get(f"/api/personas/{p['id']}").json()
    assert legajo["genero"] == "F" and legajo["departamento"] == "Capital" and legajo["cud"] == "en_tramite"
    assert legajo["cobertura_salud"] == ["pami"] and legajo["telefono"] == "381-111"

    # Un segundo ingreso detecta los antecedentes en el sistema.
    segundo = nuevo_caso(admin, p["id"], fecha_ingreso="2027-01-20", tipo_ingreso="portal_sae")
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
        # Formulario completado en papel por la técnica y cargado después por otra persona.
        "fecha": "2026-10-07", "receptor_id": ids["Tec"],
    })
    r = admin.post(f"/api/casos/{caso['id']}/demandas", json=demanda)
    assert r.status_code == 201, r.text
    d = r.json()
    assert d["receptor"]["usuario"] == "tec" and d["cargado_por"]["usuario"] == "admin"
    assert d["cargado_desde_papel"] is True and d["fecha"] == "2026-10-07"
    assert d["agente"]["usuario"] == "tec"

    # Se adjunta el escaneo del original firmado.
    from conftest import PDF
    r = admin.post("/api/documentos", data={"tipo_documental_id": "2", "titulo": "Registro firmado",
                                            "registro_demanda_id": d["id"]},
                   files={"archivo": ("registro.pdf", PDF, "application/pdf")})
    assert r.status_code == 201, r.text
    escaneo = r.json()
    assert escaneo["caso_id"] == caso["id"] and escaneo["registro_demanda_id"] == d["id"]
    assert d["datos_persona"]["numero_legajo"] == p["numero_legajo"]

    # Lo que corresponde al legajo se actualiza en el legajo.
    legajo = admin.get(f"/api/personas/{p['id']}").json()
    assert legajo["cobertura_previsional"] == ["puam"] and legajo["discapacidades"] == ["motora"]
    assert legajo["barrio"] == "Villa 9 de Julio"

    r = admin.post(f"/api/casos/{caso['id']}/demandas", json={"tipo_vivienda": "castillo"})
    assert r.status_code == 400

    detalle = admin.get(f"/api/casos/{caso['id']}").json()
    assert [x["id"] for x in detalle["demandas"]] == [d["id"]]
    assert detalle["demandas"][0]["escaneos"] == [escaneo["id"]]


def test_evolucion_y_reserva(admin):
    crear_usuario("tec1", "Técnico", AREA_ADMISION)
    crear_usuario("tec2", "Técnico", AREA_ADMISION)
    ids = {u["nombre_completo"]: u["id"] for u in admin.get("/api/catalogos").json()["usuarios_asignables"]}
    p = nueva_persona(admin)
    caso = nuevo_caso(admin, p["id"], reservado=True, responsable_id=ids["Tec1"], **CARATULA)
    tec1, tec2 = Cliente("tec1"), Cliente("tec2")
    assert tec1.post(f"/api/casos/{caso['id']}/evolucion", json={"texto": "Visita domiciliaria realizada"}).status_code == 201
    # Evolución escrita en papel por otra persona y cargada después.
    r = tec1.post(f"/api/casos/{caso['id']}/evolucion",
                  json={"texto": "Llamado a la hija", "fecha": "2026-10-01", "autor_nombre": "Lic. Ejemplo"})
    assert r.status_code == 201
    e = r.json()
    assert e["fecha"] == "2026-10-01" and e["autor"]["nombre_completo"] == "Lic. Ejemplo" and e["usuario"]["usuario"] == "tec1"
    assert tec1.post(f"/api/casos/{caso['id']}/demandas", json={"solicitante_nombre": "X"}).status_code == 201

    visto = tec1.get(f"/api/casos/{caso['id']}").json()
    # Ordenadas por fecha de la intervención, no de carga.
    assert [x["texto"] for x in visto["evoluciones"]] == ["Llamado a la hija", "Visita domiciliaria realizada"]
    assert visto["evoluciones"][1]["autor"]["usuario"] == "tec1"

    ajeno = tec2.get(f"/api/casos/{caso['id']}").json()
    assert ajeno["evoluciones"] == [] and ajeno["caratula"]["indicadores"] == []
    assert ajeno["demandas"][0]["contenido_restringido"] is True and "solicitante_nombre" not in ajeno["demandas"][0]
    assert tec2.get(f"/api/demandas/{ajeno['demandas'][0]['id']}").status_code == 403
    assert tec2.post(f"/api/casos/{caso['id']}/evolucion", json={"texto": "x x"}).status_code == 403


def test_numeracion_de_actuaciones(admin):
    p = nueva_persona(admin)
    p2 = nueva_persona(admin, numero_documento="2000001", apellidos="DOS")
    p3 = nueva_persona(admin, numero_documento="2000002", apellidos="TRES")
    # Se continúa la numeración que se llevaba en papel.
    assert admin.put("/api/admin/numeracion", json={"anio": 2026, "proximo": 351}).status_code == 200
    c1 = nuevo_caso(admin, p["id"], fecha_ingreso="2026-10-16")
    assert (c1["caratula"]["numero_actuacion"], c1["numero"]) == (351, "C-2026-00351")

    # Carátula vieja cargada con su número original; no puede repetirse.
    viejo = nuevo_caso(admin, p["id"], fecha_ingreso="2025-03-02", numero_actuacion=87)
    assert viejo["caratula"]["anio_actuacion"] == 2025 and viejo["numero"] == "C-2025-00087"
    r = admin.post("/api/casos", json={"persona_id": p2["id"], "fecha_ingreso": "2025-05-01", "numero_actuacion": 87})
    assert r.status_code == 409

    # El automático saltea un número ya usado manualmente.
    nuevo_caso(admin, p2["id"], numero_actuacion=352, anio_actuacion=2026)
    c3 = nuevo_caso(admin, p3["id"], fecha_ingreso="2026-10-17")
    assert c3["caratula"]["numero_actuacion"] == 353

    # No se puede retroceder la numeración ni cambiar el número de una carátula.
    assert admin.put("/api/admin/numeracion", json={"anio": 2026, "proximo": 300}).status_code == 409
    r = admin.patch(f"/api/casos/{c1['id']}/caratula", json={"numero_actuacion": 999})
    assert r.status_code == 400
    assert admin.get("/api/admin/numeracion/2026").json()["proximo"] == 354


def test_una_actuacion_por_persona_por_anio(admin, cliente):
    from conftest import crear_usuario

    p = nueva_persona(admin)
    caso = nuevo_caso(admin, p["id"], fecha_ingreso="2026-03-01")
    admin.post(f"/api/casos/{caso['id']}/estado", json={"estado": "cerrado", "motivo": "Resuelto"})
    # Aunque esté cerrado, en el mismo año no se abre otra actuación: se reabre el caso.
    r = admin.post("/api/casos", json={"persona_id": p["id"], "fecha_ingreso": "2026-09-01"})
    d = r.json()["detail"]
    assert r.status_code == 409 and d["caso_existente"]["estado"] == "cerrado"
    assert "1/2026" in d["mensaje"]

    # Excepción: solo Administración y con motivo.
    crear_usuario("carga", "Carga de Datos")
    r = cliente("carga").post("/api/casos", json={"persona_id": p["id"], "forzar_otra_actuacion": True,
                                                 "motivo_forzado": "x"})
    assert r.status_code == 403
    r = admin.post("/api/casos", json={"persona_id": p["id"], "forzar_otra_actuacion": True})
    assert r.status_code == 403
    r = admin.post("/api/casos", json={"persona_id": p["id"], "forzar_otra_actuacion": True,
                                       "motivo_forzado": "Dos demandas independientes, autorizado por Dirección"})
    assert r.status_code == 201


def test_reiteraciones(admin):
    p = nueva_persona(admin, numero_documento="5987321", apellidos="GOMEZ", nombres="Juan")
    caso = nuevo_caso(admin, p["id"], fecha_ingreso="2026-02-10")
    admin.post(f"/api/casos/{caso['id']}/estado", json={"estado": "cerrado", "motivo": "Resuelto"})

    # Reiteración registrada desde el caso: lo reabre.
    r = admin.post(f"/api/casos/{caso['id']}/reiteraciones",
                   json={"fecha": "2026-06-01", "motivo": "Vuelve a consultar", "tipo_ingreso": "espontaneo",
                         "tipo_ingreso_detalle": "presencial"})
    assert r.status_code == 201, r.text
    c = admin.get(f"/api/casos/{caso['id']}").json()
    assert c["estado"] == "abierto" and len(c["reiteraciones"]) == 1
    assert c["historial_estados"][-1]["motivo"].startswith("Reiteración")

    # Un ingreso de Mesa de Entrada vinculado a la persona va al caso del año como reiteración.
    ing = admin.post("/api/ingresos", json={"asunto": "Nueva nota del hospital", "documento_mencionado": "5987321"}).json()
    r = admin.post(f"/api/ingresos/{ing['id']}/vincular", json={"persona_id": p["id"]})
    assert r.status_code == 200 and r.json()["reiteracion"] is True and r.json()["caso_id"] == caso["id"]
    c = admin.get(f"/api/casos/{caso['id']}").json()
    assert len(c["reiteraciones"]) == 2 and c["reiteraciones"][1]["ingreso_id"] == ing["id"]


def test_qr_del_caso(admin):
    p = nueva_persona(admin)
    caso = nuevo_caso(admin, p["id"])
    r = admin.get(f"/api/casos/{caso['id']}/qr.svg")
    assert r.status_code == 200 and r.headers["content-type"].startswith("image/svg+xml") and b"<svg" in r.content

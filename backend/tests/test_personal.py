"""Personal: altas y bajas ligadas a usuarios, reloj, jornadas, justificativos y solicitudes (datos inventados)."""

from __future__ import annotations

from datetime import date, timedelta

from conftest import AREA_ADMISION, AREA_PROMOCION, Cliente, crear_usuario

RELOJ = """<table><tr><td>2026-10-05 00:00:00 - 2026-10-09 23:59:59</td></tr>
<tr><th>ID de Persona</th><th>Nombre</th><th>Fecha</th><th>Primera Entrada</th><th>Última Salida</th></tr>
<tr><td>901</td><td>Ficticia Ana María</td><td>2026-10-05</td><td>08:00:00</td><td>13:00:00</td></tr>
<tr><td>901</td><td>Ficticia Ana María</td><td>2026-10-06</td><td>08:20:00</td><td>13:00:00</td></tr>
<tr><td>902</td><td>Inventado Juan</td><td>2026-10-05</td><td>-</td><td>13:00:00</td></tr>
</table>"""
SEMANA = {str(d): ["08:00", "13:00"] for d in range(5)}


def test_circuito_completo(admin, cliente):
    crear_usuario("pers", "Personal", "División Asistencia Administrativa")
    crear_usuario("jefa", "Jefe/a de departamento", AREA_ADMISION)
    crear_usuario("otrojefe", "Jefe/a de departamento", AREA_PROMOCION)
    crear_usuario("tec", "Técnico", AREA_ADMISION)
    pers, jefa, otro, tec = (cliente(u) for u in ("pers", "jefa", "otrojefe", "tec"))
    areas = {a["nombre"]: a["id"] for a in admin.get("/api/catalogos").json()["areas"]}
    usuarios = {u["nombre_completo"]: u["id"] for u in admin.get("/api/catalogos").json()["usuarios_asignables"]}
    assert tec.get("/api/personal/agentes").status_code == 403

    # Altas: una vinculada a un usuario existente y otra creando el usuario.
    ana = pers.post("/api/personal/agentes", json={"nombre": "Ficticia Ana", "fecha_ingreso": "2020-03-01", "area_id": areas[AREA_ADMISION],
                                                    "cargo": "Trabajadora social", "id_reloj": "901", "usuario_id": usuarios["Tec"]}).json()
    juan = pers.post("/api/personal/agentes", json={"nombre": "Inventado Juan", "fecha_ingreso": "2021-01-01", "area_id": areas[AREA_ADMISION],
                                                     "crear_usuario": "jinventado", "password_inicial": "Clave-Segura-2026"}).json()
    assert juan["usuario"]["usuario"] == "jinventado"
    assert pers.post("/api/personal/agentes", json={"nombre": "Repetido X", "fecha_ingreso": "2021-01-01", "id_reloj": "901"}).status_code == 409
    for a in (ana, juan):
        pers.post(f"/api/personal/agentes/{a['id']}/horarios", json={"vigente_desde": "2026-10-01", "semana": SEMANA, "confirmado": True, "fuente": "Planilla de prueba"}).raise_for_status()

    # Reloj: previa, identificación del ID faltante e incorporación.
    prev = pers.post("/api/personal/reloj/previa", files={"archivo": ("semana.xls", RELOJ.encode(), "application/vnd.ms-excel")}).json()
    assert prev["filas"] == 3 and [x["id_reloj"] for x in prev["sin_identificar"]] == ["902"]
    assert prev["sin_identificar"][0]["sugerencias"][0]["id"] == juan["id"]
    assert pers.post(f"/api/personal/reloj/{prev['id']}/incorporar").status_code == 400
    pers.post(f"/api/personal/reloj/{prev['id']}/identificar", json={"id_reloj": "902", "agente_id": juan["id"]}).raise_for_status()
    assert pers.post(f"/api/personal/reloj/{prev['id']}/incorporar").json() == {"incorporadas": 3}
    assert pers.post("/api/personal/reloj/previa", files={"archivo": ("otra.xls", RELOJ.encode(), "application/vnd.ms-excel")}).json()["incorporada"]

    filas = pers.get("/api/personal/informe", params={"desde": "2026-10-05", "hasta": "2026-10-06"}).json()
    estados = {(f["nombre"], f["dia"]): (f["estado"], f["incidencias"]) for f in filas}
    assert estados[("Ficticia Ana", "2026-10-05")][0] == "auto_aprobado"
    assert estados[("Ficticia Ana", "2026-10-06")] == ("pendiente", ["TARDANZA"])
    assert estados[("Inventado Juan", "2026-10-05")] == ("pendiente", ["MARCACION_INCOMPLETA"])
    assert estados[("Inventado Juan", "2026-10-06")] == ("pendiente", ["FILA_AUSENTE_EN_REPORTE"])
    # La técnica ve solo sus jornadas.
    propias = tec.get("/api/personal/informe", params={"desde": "2026-10-05", "hasta": "2026-10-06"}).json()
    assert {f["nombre"] for f in propias} == {"Ficticia Ana"}

    # Revisión humana con huella.
    tarde = next(f for f in filas if f["dia"] == "2026-10-06" and f["nombre"] == "Ficticia Ana")
    r = pers.post("/api/personal/revisiones", json={"agente_id": ana["id"], "dia": "2026-10-06", "decision": "proponer_descuento", "minutos": 20,
                                                   "fundamento": "Llegó 20 minutos tarde", "huella": tarde["huella"]})
    assert r.status_code == 201, r.text
    assert pers.post("/api/personal/revisiones", json={"agente_id": ana["id"], "dia": "2026-10-06", "decision": "sin_descuento",
                                                      "fundamento": "Otra decisión", "huella": tarde["huella"]}).status_code == 409

    # Justificativo de Juan para el día sin marcas.
    j = pers.post("/api/personal/justificativos", json={"agente_id": juan["id"], "codigo": "LICENCIA", "desde": "2026-10-05", "hasta": "2026-10-06"}).json()
    assert j["estado"] == "aprobado"
    filas = pers.get("/api/personal/informe", params={"desde": "2026-10-05", "hasta": "2026-10-06", "agente_id": juan["id"]}).json()
    assert [f["estado"] for f in filas] == ["justificado", "justificado"]

    # Solicitud de licencia por enfermedad de la técnica: aprueba su jefa; el otro jefe no.
    hoy = date.today()
    s = tec.post("/api/personal/solicitudes", data={"tipo": "licencia", "clase": "enfermedad", "desde": hoy.isoformat(),
                                                    "hasta": (hoy + timedelta(days=2)).isoformat(), "motivo": "Indicación médica (prueba)"},
                 files={"archivo": ("certificado.pdf", b"%PDF-1.4\n%prueba\n", "application/pdf")}).json()
    assert s["estado"] == "pendiente" and s["motivo"]
    assert tec.post(f"/api/personal/solicitudes/{s['id']}/decidir", json={"aprobar": True}).status_code == 403
    assert otro.post(f"/api/personal/solicitudes/{s['id']}/decidir", json={"aprobar": True}).status_code == 403
    vista_jefa = jefa.get("/api/personal/solicitudes").json()
    assert [x["id"] for x in vista_jefa] == [s["id"]]
    assert vista_jefa[0]["motivo"] is None and vista_jefa[0]["adjuntos"] == [] and vista_jefa[0]["detalle_reservado"]
    assert jefa.get(f"/api/personal/solicitudes/{s['id']}/adjuntos/{s['adjuntos'][0]['id']}").status_code == 403
    assert jefa.get("/api/personal/pendientes").json()["para_aprobar"] == 1
    jefa.post(f"/api/personal/solicitudes/{s['id']}/decidir", json={"aprobar": True}).raise_for_status()

    # Quién está hoy (sin motivos).
    estado = tec.get("/api/personal/hoy").json()
    assert estado[usuarios["Tec"]]["texto"] == "De licencia"

    # Personal la registra como justificativo, con el certificado.
    assert pers.get("/api/personal/pendientes").json()["para_registrar"] == 1
    reg = pers.post(f"/api/personal/solicitudes/{s['id']}/registrar", json={"codigo": "LICENCIA"}).json()
    assert reg["estado"] == "registrada"
    js = pers.get("/api/personal/justificativos", params={"agente_id": ana["id"]}).json()
    assert js[0]["solicitud_id"] == s["id"] and js[0]["adjuntos"]

    # Cambio de horario: queda como CAMBIO con el nuevo turno.
    c = tec.post("/api/personal/solicitudes", data={"tipo": "cambio_horario", "desde": "2026-10-07", "nueva_entrada": "13:00", "nueva_salida": "18:00",
                                                    "motivo": "Capacitación por la mañana"}).json()
    jefa.post(f"/api/personal/solicitudes/{c['id']}/decidir", json={"aprobar": True})
    pers.post(f"/api/personal/solicitudes/{c['id']}/registrar", json={"codigo": "CT"}).raise_for_status()
    cambio = pers.get("/api/personal/justificativos", params={"agente_id": ana["id"]}).json()[0]
    assert cambio["codigo"] == "CAMBIO" and cambio["excepcion_desde"] == "13:00"

    # Rechazo con motivo y cancelación.
    x = tec.post("/api/personal/solicitudes", data={"tipo": "comision", "desde": "2026-11-02", "lugar": "Comuna Ficticia"}).json()
    assert jefa.post(f"/api/personal/solicitudes/{x['id']}/decidir", json={"aprobar": False}).status_code == 400
    jefa.post(f"/api/personal/solicitudes/{x['id']}/decidir", json={"aprobar": False, "respuesta": "Ese día hay guardia"}).raise_for_status()
    y = tec.post("/api/personal/solicitudes", data={"tipo": "comision", "desde": "2026-11-03", "lugar": "Otro lugar"}).json()
    assert tec.post(f"/api/personal/solicitudes/{y['id']}/cancelar").json()["estado"] == "cancelada"
    assert len(tec.get("/api/personal/mio").json()["solicitudes"]) == 4

    # Baja: se desactiva el usuario y se cierran sus sesiones.
    baja = pers.post(f"/api/personal/agentes/{juan['id']}/alta-baja", json={"activo": False, "fecha": hoy.isoformat(), "revision_vista": 1}).json()
    assert baja["efecto_usuario"] == "usuario_desactivado"
    assert admin.post("/api/auth/login", json={"usuario": "jinventado", "password": "Clave-Segura-2026"}).status_code in (401, 403)
    assert {a["nombre"] for a in pers.get("/api/personal/agentes").json()} == {"Ficticia Ana"}

    # Inicio del perfil Personal.
    d = pers.get("/api/inicio").json()
    assert d["perfil"] == "personal" and d["datos"]["agentes"] == 1


def test_licencia_que_no_es_de_salud_la_ve_la_jefa(admin, cliente):
    crear_usuario("pers", "Personal", "División Asistencia Administrativa")
    crear_usuario("jefa", "Jefe/a de departamento", AREA_ADMISION)
    crear_usuario("tec", "Técnico", AREA_ADMISION)
    usuarios = {u["nombre_completo"]: u["id"] for u in admin.get("/api/catalogos").json()["usuarios_asignables"]}
    cliente("pers").post("/api/personal/agentes", json={"nombre": "Ficticia Ana", "fecha_ingreso": "2020-01-01", "usuario_id": usuarios["Tec"],
                                                        "area_id": {a["nombre"]: a["id"] for a in admin.get("/api/catalogos").json()["areas"]}[AREA_ADMISION]})
    s = cliente("tec").post("/api/personal/solicitudes", data={"tipo": "licencia", "clase": "examen", "desde": "2026-11-10", "motivo": "Final de la facultad"}).json()
    assert cliente("jefa").get("/api/personal/solicitudes").json()[0]["motivo"] == "Final de la facultad"
    # Sin ficha de personal no se puede pedir.
    assert cliente("jefa").post("/api/personal/solicitudes", data={"tipo": "comision", "desde": "2026-11-10", "lugar": "X"}).status_code == 400

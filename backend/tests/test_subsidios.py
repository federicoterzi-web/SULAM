"""Subsidios: trámite con lista de papeles, resolución y pagos mensuales."""

from __future__ import annotations

from datetime import date, timedelta

from conftest import crear_usuario, nueva_persona


def _residencia(c):
    return c.post("/api/recursos", json={"tipo": "residencia", "nombre": "Residencia Sol (ficticia)"}).json()["id"]


def _nuevo(c, persona_id, **kw):
    r = c.post(f"/api/personas/{persona_id}/subsidios", json={"tipo": "residencia", **kw})
    assert r.status_code == 201, r.text
    return r.json()


def _aprobar(c, sid, **kw):
    hoy = date.today()
    r = c.patch(f"/api/subsidios/{sid}", json={"estado": "aprobado", "resolucion_numero": "RM 123/2026", "resolucion_fecha": hoy.isoformat(), "desde": (hoy - timedelta(days=45)).isoformat(), **kw})
    assert r.status_code == 200, r.text
    return r.json()


def test_tramite_papeles_y_aprobacion(admin):
    p = nueva_persona(admin)
    rid = _residencia(admin)
    s = _nuevo(admin, p["id"], recurso_id=rid, solicitante_nombre="Hija Ficticia", solicitante_vinculo="Hija", monto_mensual="450000.50")
    assert s["estado"] == "en_tramite" and s["papeles"]["total"] == 13 and s["papeles"]["presentados"] == 0 and s["prestador"] == "Residencia Sol (ficticia)"
    d = admin.get(f"/api/subsidios/{s['id']}").json()
    assert [r["grupo"] for r in d["requisitos"]][:3] == ["solicitante"] * 3 and d["pagos"] == []
    # Marcar papeles: presentado pone la fecha; no corresponde no cuenta.
    r0, r1 = d["requisitos"][0], d["requisitos"][3]
    m = admin.patch(f"/api/subsidios/requisitos/{r0['id']}", json={"estado": "presentado"}).json()
    assert m["estado"] == "presentado" and m["fecha_presentado"]
    admin.patch(f"/api/subsidios/requisitos/{r1['id']}", json={"estado": "no_corresponde"})
    assert admin.get(f"/api/subsidios/{s['id']}").json()["papeles"] == {"total": 12, "presentados": 1, "faltan": 11}
    # Papeles propios: se agregan y se quitan; los del catálogo, no.
    nuevo = admin.post(f"/api/subsidios/{s['id']}/requisitos", json={"texto": "Informe social de la Dirección", "grupo": "otros"}).json()
    assert nuevo["propio"] and admin.delete(f"/api/subsidios/requisitos/{nuevo['id']}").status_code == 204
    assert admin.delete(f"/api/subsidios/requisitos/{r0['id']}").status_code == 400
    # Aprobar pide resolución y vigencia.
    assert admin.patch(f"/api/subsidios/{s['id']}", json={"estado": "aprobado"}).status_code == 400
    assert admin.patch(f"/api/subsidios/{s['id']}", json={"estado": "elevado"}).json()["fecha_elevacion"]
    a = _aprobar(admin, s["id"])
    assert a["estado"] == "aprobado" and a["resolucion_numero"] == "RM 123/2026"
    assert admin.patch(f"/api/subsidios/{s['id']}", json={"tipo": "cuidados"}).status_code == 400
    assert admin.post(f"/api/personas/{p['id']}/subsidios", json={"tipo": "inventado"}).status_code == 400
    assert admin.get(f"/api/personas/{p['id']}/subsidios").json()[0]["id"] == s["id"]


def test_pagos_mensuales(admin):
    p = nueva_persona(admin)
    s = _nuevo(admin, p["id"], recurso_id=_residencia(admin), monto_mensual="100000")
    hoy = date.today()
    # Sin aprobar no hay pagos.
    assert admin.post(f"/api/subsidios/{s['id']}/pagos", json={"periodo": hoy.isoformat()}).status_code == 400
    _aprobar(admin, s["id"])
    pago = admin.post(f"/api/subsidios/{s['id']}/pagos", json={"periodo": hoy.isoformat()})
    assert pago.status_code == 201, pago.text
    pago = pago.json()
    assert pago["periodo"] == hoy.replace(day=1).isoformat() and pago["monto"] == 100000 and pago["papeles"]["total"] == 16 and pago["estado"] == "pendiente"
    assert admin.post(f"/api/subsidios/{s['id']}/pagos", json={"periodo": hoy.isoformat()}).status_code == 409
    # Antes del inicio de la vigencia no se puede.
    assert admin.post(f"/api/subsidios/{s['id']}/pagos", json={"periodo": (hoy - timedelta(days=400)).isoformat()}).status_code == 400
    # No se liquida con papeles faltantes, salvo que se fuerce (queda auditado).
    r = admin.patch(f"/api/subsidios/pagos/{pago['id']}", json={"estado": "en_liquidacion"})
    assert r.status_code == 409 and r.json()["detail"]["faltan"] == 16
    # Al completar todos los papeles, el mes pasa solo a «documentación completa».
    for x in pago["requisitos"]:
        admin.patch(f"/api/subsidios/requisitos/{x['id']}", json={"estado": "presentado"})
    det = admin.get(f"/api/subsidios/{s['id']}").json()
    assert det["pagos"][0]["estado"] == "documentacion_completa" and det["pagos"][0]["papeles"]["faltan"] == 0
    # Si se desmarca uno, vuelve a pendiente.
    admin.patch(f"/api/subsidios/requisitos/{pago['requisitos'][0]['id']}", json={"estado": "pendiente"})
    assert admin.get(f"/api/subsidios/{s['id']}").json()["pagos"][0]["estado"] == "pendiente"
    forzado = admin.patch(f"/api/subsidios/pagos/{pago['id']}", json={"estado": "en_liquidacion", "forzar": True})
    assert forzado.status_code == 200 and forzado.json()["estado"] == "en_liquidacion"
    ok = admin.patch(f"/api/subsidios/pagos/{pago['id']}", json={"estado": "pagado", "comprobante": "OP 5567"}).json()
    assert ok["estado"] == "pagado" and ok["fecha_pago"] == hoy.isoformat() and ok["comprobante"] == "OP 5567"
    assert admin.delete(f"/api/subsidios/pagos/{pago['id']}").status_code == 409
    assert admin.get(f"/api/subsidios/{s['id']}").json()["total_pagado"] == 100000
    # Liquidación del mes.
    mes = admin.get("/api/subsidios-pagos", params={"periodo": hoy.strftime("%Y-%m")}).json()
    assert len(mes["items"]) == 1 and mes["por_estado"]["pagado"]["cantidad"] == 1 and mes["total"] == 100000
    assert mes["items"][0]["persona"]["nombre"] == "PRUEBA, Persona"


def test_generar_pagos_del_mes(admin):
    hoy = date.today()
    sid = []
    for i, doc in enumerate(("1000001", "1000002", "1000003")):
        p = nueva_persona(admin, apellidos=f"APELLIDO{i}", nombres=f"Nombre{i}", numero_documento=doc)
        sid.append(_nuevo(admin, p["id"], monto_mensual="50000", tipo="cuidados" if i == 2 else "residencia")["id"])
    _aprobar(admin, sid[0])
    _aprobar(admin, sid[2])  # el segundo queda en trámite
    g = admin.post("/api/subsidios/pagos/generar", json={"periodo": hoy.isoformat()}).json()
    assert g["creados"] == 2
    assert admin.post("/api/subsidios/pagos/generar", json={"periodo": hoy.isoformat()}).json()["creados"] == 0
    mes = admin.get("/api/subsidios-pagos", params={"periodo": hoy.strftime("%Y-%m")}).json()
    assert {x["subsidio"]["tipo"] for x in mes["items"]} == {"residencia", "cuidados"}
    # Los cuidados tienen su propia lista mensual (1 papel).
    cuidados = next(x for x in mes["items"] if x["subsidio"]["tipo"] == "cuidados")
    assert cuidados["papeles"]["total"] == 1
    lista = admin.get("/api/subsidios").json()
    assert len(lista["items"]) == 3 and lista["por_estado"]["aprobado"]["cantidad"] == 2 and lista["por_estado"]["aprobado"]["monto_mensual"] == 100000
    assert len(admin.get("/api/subsidios", params={"tipo": "cuidados"}).json()["items"]) == 1


def test_permisos(admin, cliente):
    crear_usuario("tec", "Técnico")
    crear_usuario("per", "Personal")
    p = nueva_persona(admin)
    s = _nuevo(admin, p["id"])
    tec, per = cliente("tec"), cliente("per")
    assert per.get("/api/subsidios").status_code == 403
    assert per.post(f"/api/personas/{p['id']}/subsidios", json={"tipo": "residencia"}).status_code == 403
    # El técnico consulta (los legajos son de consulta general), pero solo modifica lo que cargó él.
    assert tec.get(f"/api/subsidios/{s['id']}").status_code == 200
    assert tec.patch(f"/api/subsidios/{s['id']}", json={"observaciones": "x"}).status_code == 403
    mio = nueva_persona(tec, apellidos="DETEC", nombres="Tomas", numero_documento="1000009")
    ms = _nuevo(tec, mio["id"])
    assert tec.patch(f"/api/subsidios/{ms['id']}", json={"estado": "aprobado", "resolucion_numero": "X", "desde": date.today().isoformat()}).status_code == 403
    assert tec.patch(f"/api/subsidios/{ms['id']}", json={"observaciones": "Hablé con la hija"}).status_code == 200
    assert tec.post("/api/subsidios/pagos/generar", json={"periodo": date.today().isoformat()}).status_code == 403

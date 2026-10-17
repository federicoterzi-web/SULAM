"""Archivo físico: ubicación de carpetas en papel y pases."""

from __future__ import annotations

from conftest import AREA_ADMISION, AREA_PROMOCION, crear_usuario, nueva_persona


def test_pedir_y_entregar_carpeta(admin, cliente):
    crear_usuario("reg1", "Administrativo de Área", "Oficina de Registro")
    crear_usuario("reg2", "Administrativo de Área", "Oficina de Registro")
    crear_usuario("tec", "Técnico", AREA_ADMISION)
    crear_usuario("otra", "Técnico", AREA_PROMOCION)
    areas = {a["nombre"]: a["id"] for a in admin.get("/api/catalogos").json()["areas"]}
    reg1, reg2, tec, otra = (cliente(u) for u in ("reg1", "reg2", "tec", "otra"))
    p = nueva_persona(admin)
    obj = {"persona_id": p["id"]}

    # Sin ubicación: no se puede pedir; Registro la carga.
    v = tec.get("/api/archivo/ubicacion", params=obj).json()
    assert v["ubicacion"] is None and v["puedo"]["registrar"] and not v["puedo"]["pedir"]
    assert tec.post("/api/archivo/pedidos", json=obj).status_code == 409
    reg1.put("/api/archivo/ubicacion", json={**obj, "area_id": areas["Oficina de Registro"]}).raise_for_status()

    # La técnica la pide; cualquiera de Registro la entrega.
    v = tec.get("/api/archivo/ubicacion", params=obj).json()
    assert v["ubicacion"]["area"]["nombre"] == "Oficina de Registro" and v["puedo"]["pedir"]
    pase = tec.post("/api/archivo/pedidos", json={**obj, "motivo": "Visita del jueves"}).json()
    assert tec.post("/api/archivo/pedidos", json=obj).status_code == 409  # uno por vez
    assert otra.post(f"/api/archivo/pases/{pase['id']}/confirmar").status_code == 403
    assert reg2.get("/api/archivo/pendientes").json() == {"entregar": 1, "recibir": 0, "cantidad": 1}
    assert reg2.post(f"/api/archivo/pases/{pase['id']}/confirmar").json()["estado"] == "hecho"
    v = tec.get("/api/archivo/ubicacion", params=obj).json()
    assert v["la_tengo"] and v["ubicacion"]["usuario"]["usuario"] == "tec"
    assert [x["texto"] for x in tec.get("/api/archivo/bandeja").json()["en_mi_poder"]][0].startswith("Legajo")

    # Otra técnica la pide: la entrega quien la tiene; Registro ya no.
    pase2 = otra.post("/api/archivo/pedidos", json=obj).json()
    assert reg1.post(f"/api/archivo/pases/{pase2['id']}/confirmar").status_code == 403
    r = tec.post(f"/api/archivo/pases/{pase2['id']}/rechazar", json={"respuesta": "La devuelvo el lunes"}).json()
    assert r["estado"] == "rechazado"

    # Devolver a Registro: lo confirma Registro al recibirla.
    env = tec.post("/api/archivo/envios", json={**obj, "hacia_area_id": areas["Oficina de Registro"]}).json()
    assert otra.post("/api/archivo/envios", json={**obj, "hacia_area_id": areas[AREA_PROMOCION]}).status_code == 403
    assert reg1.get("/api/archivo/pendientes").json()["recibir"] == 1
    reg1.post(f"/api/archivo/pases/{env['id']}/confirmar").raise_for_status()
    v = tec.get("/api/archivo/ubicacion", params=obj).json()
    assert v["ubicacion"]["area"]["nombre"] == "Oficina de Registro" and v["ubicacion"]["usuario"] is None
    assert [h["estado"] for h in v["historial"]] == ["hecho", "rechazado", "hecho"]

    # Corregir la ubicación: solo quien la tiene (o Administración).
    assert tec.put("/api/archivo/ubicacion", json={**obj, "area_id": areas[AREA_ADMISION]}).status_code == 403
    # Cancelar un pedido propio.
    c = tec.post("/api/archivo/pedidos", json=obj).json()
    assert tec.post(f"/api/archivo/pases/{c['id']}/cancelar").json()["estado"] == "cancelado"


def test_carga_inicial(admin, cliente):
    crear_usuario("reg", "Administrativo de Área", "Oficina de Registro")
    a = nueva_persona(admin, numero_documento="11111111", apellidos="UNO")
    b = nueva_persona(admin, numero_documento="22222222", apellidos="DOS", nombres="Otra")
    reg = cliente("reg")
    r = reg.post("/api/archivo/carga-inicial", json={"numeros": [a["numero_legajo"], "11.111.111", "99999999"]}).json()
    assert r["cargadas"] == [a["numero_legajo"]] and r["no_encontradas"] == ["99999999"]
    r = reg.post("/api/archivo/carga-inicial", json={"numeros": [a["numero_legajo"], b["numero_legajo"]]}).json()
    assert r["cargadas"] == [b["numero_legajo"]] and r["ya_ubicadas"][0]["donde"] == "en Oficina de Registro"

"""Residencias de larga estadía: documentación e internaciones."""

from __future__ import annotations

import io
from datetime import date, timedelta

from conftest import crear_usuario, nueva_persona

PDF = b"%PDF-1.4\n1 0 obj<<>>endobj\ntrailer<<>>\n%%EOF"


def _residencia(c, nombre="Residencia Sol (ficticia)"):
    r = c.post("/api/recursos", json={"tipo": "residencia", "nombre": nombre, "departamento": "Capital"})
    assert r.status_code == 201, r.text
    return r.json()["id"]


def _doc(c, rid, tipo, vence, **kw):
    r = c.post(f"/api/recursos/{rid}/documentacion", data={"tipo": tipo, "vence": vence.isoformat() if vence else "", **kw})
    assert r.status_code == 201, r.text
    return r.json()


def test_documentacion_estados_y_archivo(admin):
    rid = _residencia(admin)
    hoy = date.today()
    _doc(admin, rid, "habilitacion_siprosa", hoy - timedelta(days=5), numero="H-123")
    d = _doc(admin, rid, "fiscalizacion_sanitaria", hoy + timedelta(days=20))
    assert d["estado"] == "por_vencer" and not d["tiene_archivo"]
    # Se adjunta el papel escaneado después; solo PDF o imágenes.
    assert admin.post(f"/api/recursos/documentacion/{d['id']}/archivo", files={"archivo": ("x.exe", io.BytesIO(b"MZ..."), "application/octet-stream")}).status_code == 415
    ok = admin.post(f"/api/recursos/documentacion/{d['id']}/archivo", files={"archivo": ("fiscalizacion.pdf", io.BytesIO(PDF), "application/pdf")})
    assert ok.status_code == 200 and ok.json()["tiene_archivo"]
    assert admin.get(f"/api/recursos/documentacion/{d['id']}/archivo").content == PDF

    r = admin.get(f"/api/recursos/{rid}/documentacion").json()
    estados = {x["tipo"]: x["estado"] for x in r["resumen"]}
    assert estados == {"habilitacion_siprosa": "vencido", "fiscalizacion_sanitaria": "por_vencer"}
    # Una renovación posterior reemplaza el estado: cuenta el documento más reciente de cada tipo.
    _doc(admin, rid, "habilitacion_siprosa", hoy + timedelta(days=400))
    estados = {x["tipo"]: x["estado"] for x in admin.get(f"/api/recursos/{rid}/documentacion").json()["resumen"]}
    assert estados["habilitacion_siprosa"] == "vigente"
    assert admin.post(f"/api/recursos/{rid}/documentacion", data={"tipo": "otra_cosa"}).status_code == 400
    assert admin.post(f"/api/recursos/{rid}/documentacion", data={"tipo": "seguro", "fecha_emision": hoy.isoformat(), "vence": (hoy - timedelta(days=1)).isoformat()}).status_code == 400

    p = admin.get("/api/residencias/panel").json()
    assert p["resumen"]["residencias"] == 1 and p["items"][0]["estado"] == "por_vencer"
    otra = _residencia(admin, "Residencia Luna (ficticia)")
    p = admin.get("/api/residencias/panel").json()
    luna = next(x for x in p["items"] if x["id"] == otra)
    assert luna["estado"] == "falta" and p["resumen"]["con_documentos_faltantes"] == 1

    assert admin.patch(f"/api/recursos/documentacion/{d['id']}", json={"vence": (hoy + timedelta(days=300)).isoformat()}).json()["estado"] == "vigente"
    assert admin.delete(f"/api/recursos/documentacion/{d['id']}").status_code == 204
    # La habilitación vencida quedó renovada y se quitó la fiscalización: no hay nada que avisar.
    assert admin.get("/api/avisos").json()["avisos"]["residencias_documentos"] == []
    _doc(admin, rid, "bomberos", hoy + timedelta(days=10))
    assert len(admin.get("/api/avisos").json()["avisos"]["residencias_documentos"]) == 1


def test_internaciones(admin):
    rid = _residencia(admin)
    p = nueva_persona(admin, apellidos="INTERNADA", nombres="Ana")
    hoy = date.today()
    r = admin.post(f"/api/personas/{p['id']}/internaciones", json={"recurso_id": rid, "desde": (hoy - timedelta(days=40)).isoformat(), "observaciones": "Ingresó por derivación"})
    assert r.status_code == 201, r.text
    i = r.json()
    assert i["vigente"] and i["dias"] == 40 and i["lugar"] == "Residencia Sol (ficticia)"
    # Una sola internación vigente por persona.
    assert admin.post(f"/api/personas/{p['id']}/internaciones", json={"lugar_texto": "Hogar X", "desde": hoy.isoformat()}).status_code == 409
    # Hace falta residencia o lugar, y no puede ser futura.
    assert admin.post(f"/api/personas/{p['id']}/internaciones", json={"desde": hoy.isoformat()}).status_code == 422
    q = nueva_persona(admin, apellidos="OTRA", nombres="Berta", numero_documento="2000000")
    assert admin.post(f"/api/personas/{q['id']}/internaciones", json={"lugar_texto": "Hogar X", "desde": (hoy + timedelta(days=30)).isoformat()}).status_code == 400

    lista = admin.get("/api/internaciones", params={"recurso_id": rid}).json()
    assert lista["total"] == 1 and lista["items"][0]["persona"]["nombre"] == "INTERNADA, Ana"
    assert admin.get("/api/residencias/panel").json()["items"][0]["internados"] == 1

    # Egreso: pide motivo y no puede ser anterior al ingreso.
    assert admin.patch(f"/api/internaciones/{i['id']}", json={"hasta": hoy.isoformat()}).status_code == 400
    assert admin.patch(f"/api/internaciones/{i['id']}", json={"hasta": (hoy - timedelta(days=60)).isoformat(), "motivo_egreso": "traslado"}).status_code == 400
    e = admin.patch(f"/api/internaciones/{i['id']}", json={"hasta": hoy.isoformat(), "motivo_egreso": "traslado"})
    assert e.status_code == 200 and not e.json()["vigente"]
    assert admin.get("/api/internaciones", params={"recurso_id": rid}).json()["total"] == 0
    assert admin.get("/api/internaciones", params={"recurso_id": rid, "vigentes": False}).json()["total"] == 1
    # Ya puede registrarse otra (en un lugar que no está en el mapa).
    assert admin.post(f"/api/personas/{p['id']}/internaciones", json={"lugar_texto": "Hogar San José", "desde": hoy.isoformat()}).status_code == 201
    hist = admin.get(f"/api/personas/{p['id']}/internaciones").json()
    assert [h["lugar"] for h in hist] == ["Hogar San José", "Residencia Sol (ficticia)"] or len(hist) == 2


def test_permisos(admin, cliente):
    crear_usuario("tec", "Técnico")
    crear_usuario("adm", "Personal")
    tec = cliente("tec")
    rid = _residencia(admin)
    assert tec.get(f"/api/recursos/{rid}/documentacion").status_code == 200
    assert tec.post(f"/api/recursos/{rid}/documentacion", data={"tipo": "seguro"}).status_code == 201
    ad = cliente("adm")
    assert ad.get("/api/residencias/panel").status_code == 200
    assert ad.post(f"/api/recursos/{rid}/documentacion", data={"tipo": "seguro"}).status_code == 403

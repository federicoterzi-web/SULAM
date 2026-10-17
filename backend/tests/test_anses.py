"""Certificación negativa de ANSES: CUIL, lectura del PDF, registro y vencimiento.

Los PDF son simulados (texto parecido al de ANSES); la lectura se calibra con
negativas reales cuando la Dirección las provea.
"""

from __future__ import annotations

import io
from datetime import date, timedelta

from conftest import AREA_ADMISION, crear_usuario, nueva_persona, nuevo_caso
from sulam.anses import cuil_sugeridos, cuil_valido, leer_negativa


def pdf_simulado(lineas: list[str]) -> bytes:
    from reportlab.pdfgen.canvas import Canvas

    buf = io.BytesIO()
    c = Canvas(buf)
    y = 800
    for linea in lineas:
        c.drawString(60, y, linea)
        y -= 18
    c.save()
    return buf.getvalue()


def negativa(cuil: str, emision: date, registra: bool = False) -> bytes:
    cuerpo = (
        ["Registra la siguiente prestacion: Pension no contributiva - Beneficio N 123456"]
        if registra
        else ["No registra prestaciones previsionales ni asignaciones.", "No registra aportes. No registra obra social."]
    )
    return pdf_simulado(
        ["ANSES - Administracion Nacional de la Seguridad Social", "CERTIFICACION NEGATIVA",
         f"CUIL: {cuil}", f"Fecha de emision: {emision:%d/%m/%Y}", *cuerpo, "Codigo de validacion: AB12CD34EF"]
    )


def test_cuil():
    assert cuil_sugeridos("12345678", "M") == ["20-12345678-6"]
    assert cuil_valido("20-12345678-6") and not cuil_valido("20-12345678-5")
    assert len(cuil_sugeridos("4123456", None)) == 2
    assert cuil_sugeridos(None, "F") == []


def test_lectura():
    hoy = date(2026, 10, 17)
    from sulam.anses import texto_de_pdf

    l = leer_negativa(texto_de_pdf(negativa("27-04123456-9", date(2026, 10, 10))), hoy)
    assert l["cuiles"] == ["27-04123456-9"] and l["fecha_emision"] == "2026-10-10"
    assert l["resultado"] == "sin_registros" and l["codigo_validacion"] == "AB12CD34EF" and l["es_negativa_anses"]
    l = leer_negativa(texto_de_pdf(negativa("27-04123456-9", date(2026, 10, 10), registra=True)), hoy)
    assert l["resultado"] == "con_registros" and "pension" in l["detalle"]
    l = leer_negativa(texto_de_pdf(pdf_simulado(["Un PDF cualquiera"])), hoy)
    assert l["resultado"] is None and l["avisos"]


def test_registro_en_el_legajo(admin, cliente):
    crear_usuario("tec", "Técnico", AREA_ADMISION)
    ids = {u["nombre_completo"]: u["id"] for u in admin.get("/api/catalogos").json()["usuarios_asignables"]}
    p = nueva_persona(admin, numero_documento="4123456", genero="F")
    caso = nuevo_caso(admin, p["id"], responsables_ids=[ids["Tec"]])
    tec = cliente("tec")

    info = tec.get(f"/api/personas/{p['id']}/negativa-anses").json()
    assert info["cuil"] is None and info["cuil_sugeridos"] == ["27-04123456-9"]
    assert info["ultima"] is None and info["puede_registrar"] and info["url_anses"].startswith("https://")

    hoy = date.today()
    pdf = negativa("27-04123456-9", hoy - timedelta(days=2))
    r = tec.post(f"/api/personas/{p['id']}/negativa-anses/leer", files={"archivo": ("negativa.pdf", pdf, "application/pdf")})
    assert r.status_code == 200, r.text
    lectura = r.json()
    assert lectura["cuil"] == "27-04123456-9" and lectura["cuil_coincide"] is True
    assert lectura["resultado"] == "sin_registros"

    # Negativa de otra persona: se advierte y no se registra.
    ajena = negativa("20-12345678-6", hoy)
    assert tec.post(f"/api/personas/{p['id']}/negativa-anses/leer", files={"archivo": ("x.pdf", ajena, "application/pdf")}).json()["avisos"][0].startswith("El CUIL del PDF")
    r = tec.post(f"/api/personas/{p['id']}/negativa-anses",
                 data={"resultado": "sin_registros", "fecha_emision": hoy.isoformat(), "cuil": "20-12345678-6"},
                 files={"archivo": ("x.pdf", ajena, "application/pdf")})
    assert r.status_code == 400

    r = tec.post(
        f"/api/personas/{p['id']}/negativa-anses",
        data={"resultado": "sin_registros", "fecha_emision": lectura["fecha_emision"], "cuil": lectura["cuil"],
              "codigo_validacion": lectura["codigo_validacion"], "caso_id": caso["id"], "leido_del_pdf": "true"},
        files={"archivo": ("negativa.pdf", pdf, "application/pdf")},
    )
    assert r.status_code == 201, r.text
    c = r.json()
    assert c["estado"] == "vigente" and c["origen"] == "pdf" and c["documento_id"]
    assert c["vence"] == (hoy - timedelta(days=2) + timedelta(days=30)).isoformat()
    # El PDF queda en los documentos del caso y el CUIL en el legajo.
    doc = tec.get(f"/api/documentos/{c['documento_id']}").json()
    assert doc["caso_id"] == caso["id"] and doc["tipo_documental"]["nombre"] == "Certificación negativa ANSES"
    assert admin.get(f"/api/personas/{p['id']}").json()["cuil"] == "27-04123456-9"

    # Una vieja queda vencida; "no emitida" no lleva PDF.
    r = tec.post(f"/api/personas/{p['id']}/negativa-anses",
                 data={"resultado": "no_emitida", "fecha_emision": hoy.isoformat(), "observaciones": "ANSES no la emitió"})
    assert r.status_code == 201 and r.json()["estado"] == "no_emitida"
    assert tec.post(f"/api/personas/{p['id']}/negativa-anses",
                    data={"resultado": "sin_registros", "fecha_emision": hoy.isoformat()}).status_code == 400
    vieja = tec.post(f"/api/personas/{p['id']}/negativa-anses",
                     data={"resultado": "sin_registros", "fecha_emision": (hoy - timedelta(days=60)).isoformat()},
                     files={"archivo": ("v.pdf", negativa("27-04123456-9", hoy - timedelta(days=60)), "application/pdf")}).json()
    assert vieja["estado"] == "vencida"
    info = tec.get(f"/api/personas/{p['id']}/negativa-anses").json()
    assert len(info["historial"]) == 3 and info["ultima"]["resultado"] == "no_emitida"

    # Se puede usar en los informes.
    inf = tec.post("/api/informes", json={"caso_id": caso["id"]}).json()
    disp = {d["clave"]: d["valor"] for d in inf["datos_disponibles"]}
    assert disp["cuil"] == "27-04123456-9" and disp["negativa_anses"].startswith("ANSES no emitió")

    # Sin permiso sobre el legajo no se registra.
    from conftest import AREA_PROMOCION

    crear_usuario("otro", "Técnico", AREA_PROMOCION)
    otro = cliente("otro")
    assert otro.get(f"/api/personas/{p['id']}/negativa-anses").json()["puede_registrar"] is False
    assert otro.post(f"/api/personas/{p['id']}/negativa-anses",
                     data={"resultado": "no_emitida", "fecha_emision": hoy.isoformat()}).status_code == 403


def test_cuil_en_el_legajo(admin):
    p = nueva_persona(admin, numero_documento="12345678")
    assert admin.patch(f"/api/personas/{p['id']}", json={"cuil": "20123456785"}).status_code == 422
    r = admin.patch(f"/api/personas/{p['id']}", json={"cuil": "20123456786"})
    assert r.status_code == 200 and r.json()["cuil"] == "20-12345678-6"

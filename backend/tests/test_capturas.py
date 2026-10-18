"""Captura con el celular: bandeja de fotos, clasificación en documentos y tipos con plantilla."""

from __future__ import annotations

import io
from datetime import date, timedelta

from conftest import AREA_ADMISION, crear_usuario, nueva_persona
from PIL import Image


def _foto(color=(200, 30, 30), lado=300) -> bytes:
    b = io.BytesIO()
    Image.new("RGB", (lado, int(lado * 1.4)), color).save(b, "JPEG")
    return b.getvalue()


def _subir(c, n=1):
    ids = []
    for i in range(n):
        r = c.post("/api/capturas", files={"foto": (f"f{i}.jpg", _foto((20 * i, 50, 90)), "image/jpeg")})
        assert r.status_code == 201, r.text
        ids.append(r.json()["id"])
    return ids


def _tipo(c, **kw):
    datos = {"nombre": "Certificado de prueba", "tiene_vencimiento": True, "vigencia_dias": 180, "usa_numero": True,
             "campos": [{"etiqueta": "Emisor", "tipo": "texto"}, {"etiqueta": "Fecha del estudio", "tipo": "fecha"}]}
    datos.update(kw)
    return c.post("/api/tipos-documentales", json=datos)


def test_bandeja_privada_y_descartar(admin, cliente):
    crear_usuario("tec", "Técnico", AREA_ADMISION)
    ids = _subir(admin, 3)
    b = admin.get("/api/capturas").json()
    assert b["cantidad"] == 3
    assert admin.get(f"/api/capturas/{ids[0]}/imagen").headers["content-type"] == "image/jpeg"
    mini = admin.get(f"/api/capturas/{ids[0]}/imagen", params={"miniatura": True}).content
    assert Image.open(io.BytesIO(mini)).size[0] <= 360
    otro = cliente("tec")
    assert otro.get("/api/capturas").json()["cantidad"] == 0
    assert otro.get(f"/api/capturas/{ids[0]}/imagen").status_code == 404
    assert otro.post(f"/api/capturas/{ids[0]}/descartar").status_code == 404
    admin.post(f"/api/capturas/{ids[0]}/descartar")
    assert admin.get("/api/capturas").json()["cantidad"] == 2
    assert admin.post("/api/capturas", files={"foto": ("x.txt", b"hola", "text/plain")}).status_code == 415


def test_tipo_nuevo_con_plantilla(admin):
    r = _tipo(admin)
    assert r.status_code == 201, r.text
    t = r.json()
    assert t["tiene_vencimiento"] and t["vigencia_dias"] == 180 and t["usa_numero"]
    assert [c["clave"] for c in t["campos"]] == ["emisor", "fecha_del_estudio"]
    assert _tipo(admin, nombre="certificado DE prueba").status_code == 409  # mismo nombre, sin distinguir mayúsculas
    en_catalogo = {x["id"]: x for x in admin.get("/api/catalogos").json()["tipos_documentales"]}
    assert en_catalogo[t["id"]]["campos"][0]["etiqueta"] == "Emisor"
    sin_vence = _tipo(admin, nombre="Constancia simple", tiene_vencimiento=False, vigencia_dias=90, usa_numero=False, campos=[]).json()
    assert sin_vence["vigencia_dias"] is None  # sin vencimiento no guarda vigencia


def test_clasificar_hojas_en_un_documento(admin):
    p = nueva_persona(admin)
    tipo = _tipo(admin).json()
    ids = _subir(admin, 4)
    hoy = date.today()
    r = admin.post("/api/capturas/clasificar", json={
        "paginas": [ids[1], ids[0]], "tipo_documental_id": tipo["id"], "titulo": "Certificado de la clínica",
        "persona_id": p["id"], "fecha_emision": hoy.isoformat(), "numero": "A-123",
        "datos": {"emisor": "Clínica Norte", "fecha_del_estudio": hoy.isoformat(), "inventado": "no se guarda"},
    })
    assert r.status_code == 201, r.text
    d = r.json()
    assert d["mime"] == "application/pdf" and d["numero"] == "A-123"
    assert d["vence"] == (hoy + timedelta(days=180)).isoformat()  # sugerido por la vigencia del tipo
    assert d["datos"] == {"emisor": "Clínica Norte", "fecha_del_estudio": hoy.isoformat()}
    pdf = admin.get(f"/api/documentos/{d['id']}/archivo").content
    assert pdf.startswith(b"%PDF") and pdf.count(b"/Type /Page\n") + pdf.count(b"/Type /Page ") + pdf.count(b"/Type/Page") >= 2
    assert admin.get("/api/capturas").json()["cantidad"] == 2  # las otras dos siguen esperando
    # Una hoja ya usada no se puede reutilizar.
    de_nuevo = admin.post("/api/capturas/clasificar", json={"paginas": [ids[0]], "tipo_documental_id": tipo["id"], "titulo": "x", "persona_id": p["id"]})
    assert de_nuevo.status_code == 409
    # El documento muestra sus datos dentro del legajo.
    lista = admin.get(f"/api/personas/{p['id']}").json()["documentos"]
    assert lista[0]["vence"] == d["vence"] and lista[0]["tipo_documental"]["nombre"] == "Certificado de prueba"


def test_validaciones_de_plantilla(admin):
    p = nueva_persona(admin)
    simple = _tipo(admin, nombre="Nota simple", tiene_vencimiento=False, vigencia_dias=None, usa_numero=False, campos=[]).json()
    ids = _subir(admin, 2)

    def clasificar(pagina, **kw):
        return admin.post("/api/capturas/clasificar", json={"paginas": [pagina], "tipo_documental_id": simple["id"], "titulo": "t", "persona_id": p["id"], **kw})

    assert clasificar(ids[0], vence="2030-01-01").status_code == 400  # el tipo no vence
    assert clasificar(ids[0], numero="1").status_code == 400  # el tipo no lleva número
    ok = clasificar(ids[0])
    assert ok.status_code == 201 and ok.json()["vence"] is None
    # El vencimiento no puede ser anterior a la emisión.
    con = _tipo(admin, nombre="Otro con vencimiento").json()
    mal = admin.post("/api/capturas/clasificar", json={"paginas": [ids[1]], "tipo_documental_id": con["id"], "titulo": "t", "persona_id": p["id"],
                                                      "fecha_emision": "2026-05-01", "vence": "2026-04-01"})
    assert mal.status_code == 400
    # Se pueden corregir los datos después.
    r = admin.patch(f"/api/documentos/{ok.json()['id']}", json={"tipo_documental_id": con["id"], "vence": "2027-01-31"})
    assert r.status_code == 200 and r.json()["vence"] == "2027-01-31"




def test_editar_plantilla_de_un_tipo(admin):
    p = nueva_persona(admin)
    t = _tipo(admin).json()
    ids = _subir(admin, 1)
    doc = admin.post("/api/capturas/clasificar", json={
        "paginas": ids, "tipo_documental_id": t["id"], "titulo": "x", "persona_id": p["id"],
        "fecha_emision": "2026-01-10", "datos": {"emisor": "Clínica Norte"},
    }).json()
    campos = t["campos"]
    # Cambiar el nombre y la vigencia, renombrar un dato y agregar otro.
    r = admin.patch(f"/api/tipos-documentales/{t['id']}", json={
        "nombre": "Certificado médico", "vigencia_dias": 365,
        "campos": [{**campos[0], "etiqueta": "Institución emisora"}, campos[1], {"etiqueta": "Profesional", "tipo": "texto"}],
    })
    assert r.status_code == 200, r.text
    nuevo = r.json()
    assert nuevo["nombre"] == "Certificado médico" and nuevo["vigencia_dias"] == 365
    assert [c["clave"] for c in nuevo["campos"]] == ["emisor", "fecha_del_estudio", "profesional"]
    # Los datos ya cargados siguen ahí, con el nombre nuevo del dato.
    guardado = admin.get(f"/api/personas/{p['id']}").json()["documentos"][0]
    assert guardado["datos"] == {"emisor": "Clínica Norte"} and guardado["tipo_documental"]["campos"][0]["etiqueta"] == "Institución emisora"
    assert guardado["vence"] == doc["vence"]
    # No se pueden quitar datos ni cambiarles la clase; no se repite un nombre.
    assert admin.patch(f"/api/tipos-documentales/{t['id']}", json={"campos": [campos[0]]}).status_code == 400
    assert admin.patch(f"/api/tipos-documentales/{t['id']}", json={"campos": [{**campos[0], "tipo": "fecha"}, campos[1]]}).status_code == 400
    otro = _tipo(admin, nombre="Otro tipo").json()
    assert admin.patch(f"/api/tipos-documentales/{otro['id']}", json={"nombre": "certificado MÉDICO"}).status_code == 409
    # Si ya no vence, no se guarda la vigencia.
    sin = admin.patch(f"/api/tipos-documentales/{t['id']}", json={"tiene_vencimiento": False}).json()
    assert sin["vigencia_dias"] is None
    assert admin.patch("/api/tipos-documentales/99999", json={"nombre": "x1"}).status_code == 404


def test_unidades_del_reconocimiento():
    from sulam import reconocimiento as r

    t = "Certificado de Discapacidad\nPágina 2 de 3\nNro: AB-1234/5 DNI 20.123.456 CUIL 20-20123456-3\nFecha de emisión: 01/02/2024 Válido hasta: 01/02/2029"
    assert "20123456" in r.documentos_en(t) and "20201234563" in r.documentos_en(t)
    assert r.fechas_en(t) == {"vence": "2029-02-01", "fecha_emision": "2024-02-01"}
    assert r.numero_en(t) == "AB-1234/5"
    assert r.pagina_de(t) == (2, 3)
    assert r.agrupar([(1, 3), (2, 3), None, (1, 2), (2, 2), (2, 2)]) == [[0, 1], [2], [3, 4], [5]]
    assert r.tipos_probables(t, [(1, "Certificado de discapacidad", None), (2, "Libreta sanitaria", None)]) == [(1, 1.0)]


def test_leer_fotos_sugiere_legajo_y_tipo(admin):
    import pytest
    from PIL import ImageDraw, ImageFont

    from sulam import reconocimiento

    if not reconocimiento.disponible():
        pytest.skip("Tesseract no está instalado")
    p = nueva_persona(admin, numero_documento="20123456")
    tipo = _tipo(admin, nombre="Disability certificate").json()
    img = Image.new("RGB", (1400, 900), "white")
    d = ImageDraw.Draw(img)
    try:
        f = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", 56)
    except OSError:
        f = ImageFont.load_default(56)
    d.text((60, 60), "Disability certificate", fill="black", font=f)
    d.text((60, 200), "DNI 20.123.456", fill="black", font=f)
    d.text((60, 340), "Valid until 01/02/2029", fill="black", font=f)
    b = io.BytesIO()
    img.save(b, "JPEG")
    pid = admin.post("/api/capturas", files={"foto": ("a.jpg", b.getvalue(), "image/jpeg")}).json()["id"]
    r = admin.post("/api/capturas/leer", json={"paginas": [pid]})
    assert r.status_code == 200, r.text
    j = r.json()
    assert j["tipo_documental_id"] == tipo["id"]
    assert j["persona"] and j["persona"]["id"] == p["id"]
    assert j["grupos"] == [[pid]]
    assert admin.post("/api/capturas/leer", json={"paginas": [pid, pid]}).status_code == 400


def _pdf_con_texto(lineas: list[str]) -> bytes:
    """PDF mínimo con una hoja por cada elemento (texto real, sin OCR)."""
    objs, kids = [], []
    for i, linea in enumerate(lineas):
        n = 4 + i * 2
        kids.append(f"{n} 0 R")
        flujo = f"BT /F1 14 Tf 40 700 Td ({linea}) Tj ET"
        objs.append(f"{n} 0 obj << /Type /Page /Parent 2 0 R /MediaBox [0 0 595 842] /Contents {n + 1} 0 R /Resources << /Font << /F1 3 0 R >> >> >> endobj")
        objs.append(f"{n + 1} 0 obj << /Length {len(flujo)} >> stream\n{flujo}\nendstream endobj")
    cuerpo = ["%PDF-1.4", "1 0 obj << /Type /Catalog /Pages 2 0 R >> endobj",
              f"2 0 obj << /Type /Pages /Kids [{' '.join(kids)}] /Count {len(kids)} >> endobj",
              "3 0 obj << /Type /Font /Subtype /Type1 /BaseFont /Helvetica >> endobj", *objs]
    return ("\n".join(cuerpo) + "\ntrailer << /Root 1 0 R >>\n%%EOF").encode("latin-1")


def test_texto_busqueda_y_resaltado(admin, cliente):
    from sulam import indexacion

    crear_usuario("tec", "Técnico", AREA_ADMISION)
    p = nueva_persona(admin, apellidos="GUTIÉRREZ", nombres="Rosa Elena", numero_documento="12345678")
    otra = nueva_persona(admin, apellidos="OTRA", nombres="Persona", numero_documento="22333444")
    tipo = _tipo(admin).json()
    pdf = _pdf_con_texto([
        "Constancia de residencia de Rosa Elena Gutierrez DNI 12.345.678",
        "Emitida para la Direccion de Adultos Mayores de Tucuman. Resolucion 245/2026",
    ])

    def cargar(persona, pdf_bytes, titulo):
        r = admin.post("/api/documentos", data={"tipo_documental_id": tipo["id"], "titulo": titulo, "persona_id": persona["id"]},
                       files={"archivo": ("c.pdf", pdf_bytes, "application/pdf")})
        assert r.status_code == 201, r.text
        return r.json()

    d = cargar(p, pdf, "Constancia")
    assert d["texto_estado"] == "pendiente"
    assert admin.post(f"/api/documentos/{d['id']}/leer-texto").json()["estado"] == "listo"

    t = admin.get(f"/api/documentos/{d['id']}/texto").json()
    assert len(t["hojas"]) == 2
    marcado = {(x["k"], x["t"]) for h in t["hojas"] for x in h["trozos"] if x["k"]}
    assert ("documento", "12.345.678") in marcado
    assert ("nombre", "Rosa") in marcado and ("nombre", "Gutierrez") in marcado
    assert ("institucion", "Direccion de Adultos Mayores") in marcado
    assert t["alerta"] is None

    # Búsqueda: sin tildes, por prefijo y con todas las palabras.
    r = admin.get("/api/documentos/buscar", params={"q": "resolución 245"}).json()
    assert r["total"] == 1 and r["resultados"][0]["id"] == d["id"]
    assert "245" in r["resultados"][0]["fragmento"] and r["resultados"][0]["persona"]["nombre"].startswith("GUTIÉRREZ")
    assert admin.get("/api/documentos/buscar", params={"q": "inexistente"}).json()["total"] == 0

    # Documento en el legajo equivocado: advierte.
    mal = cargar(otra, pdf, "Mismo papel, otro legajo")
    admin.post(f"/api/documentos/{mal['id']}/leer-texto")
    assert "no aparece" in admin.get(f"/api/documentos/{mal['id']}/texto").json()["alerta"]

    # Quien no puede ver el legajo no lo encuentra; y el documento eliminado tampoco.
    assert cliente("tec").get("/api/documentos/buscar", params={"q": "resolucion"}).status_code in (200, 403)
    assert indexacion.resaltar("Ñandú", [("nombre", r"nandu")]) == [{"t": "Ñandú", "k": "nombre"}]

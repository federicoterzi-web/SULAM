"""Informes redactados en SULAM: plantillas, datos automáticos, firma y versiones."""

from __future__ import annotations

import io

from conftest import AREA_ADMISION, AREA_PROMOCION, crear_usuario, nueva_persona, nuevo_caso


def _plantilla(c, nombre):
    return next(p for p in c.get("/api/informes/catalogo").json()["plantillas"] if p["nombre"] == nombre)


def _guardar(c, inf, **cambios):
    cuerpo = {k: inf[k] for k in ("titulo", "lugar", "fecha", "destinatario", "datos", "secciones", "firmantes")}
    cuerpo["actualizado_en"] = inf["actualizado_en"]
    cuerpo.update(cambios)
    return c.put(f"/api/informes/{inf['id']}", json=cuerpo)


def test_informe_completo(admin, cliente):
    crear_usuario("tec", "Técnico", AREA_ADMISION)
    ids = {u["nombre_completo"]: u["id"] for u in admin.get("/api/catalogos").json()["usuarios_asignables"]}
    p = nueva_persona(
        admin, apellidos="Ficticia", nombres="Rosa", numero_documento="4123456", fecha_nacimiento="1941-03-12",
        domicilio="Calle Inventada 123", localidad="Lules", cud="no", cobertura_salud=["pami"],
    )
    caso = nuevo_caso(admin, p["id"], responsable_id=ids["Tec"], motivo="Vive sola (ficticio).")
    admin.post(f"/api/casos/{caso['id']}/evolucion", json={"texto": "Visita domiciliaria (prueba)."}).raise_for_status()
    tec = cliente("tec")

    cat = tec.get("/api/informes/catalogo").json()
    assert {"Informe socioambiental", "Informe de seguimiento", "Nota / oficio a otra institución"} <= {x["nombre"] for x in cat["plantillas"]}
    socio = _plantilla(tec, "Informe socioambiental")

    r = tec.post("/api/informes", json={"caso_id": caso["id"], "plantilla_id": socio["id"]})
    assert r.status_code == 201, r.text
    inf = r.json()
    assert inf["estado"] == "borrador" and inf["version"] == 1
    datos = {d["clave"]: d["valor"] for d in inf["datos"]}
    assert datos["nombre"] == "Rosa Ficticia"
    assert datos["documento"] == "4.123.456"
    assert datos["fecha_nacimiento"] == "12/03/1941" and datos["edad"].endswith("años")
    assert datos["obra_social"] == "PAMI" and datos["cud"] == "No posee"
    assert datos["domicilio"] == "Calle Inventada 123, Lules"
    assert [s["titulo"] for s in inf["secciones"]][0] == "Reseña"
    assert inf["firmantes"][0]["nombre"] == "Tec"
    assert any(d["clave"] == "telefono" for d in inf["datos_disponibles"])

    # Textos del caso para insertar.
    fuentes = tec.get(f"/api/informes/{inf['id']}/fuentes").json()
    assert {"Motivo de ingreso"} <= {f["titulo"] for f in fuentes}
    assert any(f["grupo"] == "Evolución" for f in fuentes)

    # Se quitan y agregan datos y secciones; el HTML se limpia.
    datos_nuevos = [d for d in inf["datos"] if d["clave"] != "estado_civil"] + [{"clave": None, "etiqueta": "Profesión", "valor": "Docente jubilada"}]
    secciones = [
        {"titulo": "Reseña", "html": "<div>Texto <b>importante</b><script>alert(1)</script></div><img src=x onerror=alert(1)>"},
        {"titulo": "Situación habitacional", "html": "<ul><li>Uno</li><li>Dos</li></ul>"},
        {"titulo": "Sección agregada", "html": "<p>Contenido</p>"},
    ]
    r = _guardar(tec, inf, datos=datos_nuevos, secciones=secciones, firmantes=[{"nombre": "Tec", "cargo": "Lic. en Trabajo Social"}])
    assert r.status_code == 200, r.text
    assert r.json()["secciones"][0]["html"] == "<p>Texto <b>importante</b></p>"
    # Guardar con una versión vieja no pisa lo de otra persona.
    viejo = _guardar(tec, inf, titulo="Pisado")
    assert viejo.status_code == 409
    inf = tec.get(f"/api/informes/{inf['id']}").json()
    assert inf["titulo"] == "Informe socioambiental" and len(inf["secciones"]) == 3
    assert "estado_civil" not in {d["clave"] for d in inf["datos"]}

    previa = tec.get(f"/api/informes/{inf['id']}/vista-previa")
    assert previa.status_code == 200 and previa.content.startswith(b"%PDF")

    # Firmar: genera el PDF como documento del caso y queda inmodificable.
    r = tec.post(f"/api/informes/{inf['id']}/firmar")
    assert r.status_code == 200, r.text
    firmado = r.json()
    assert firmado["estado"] == "firmado" and firmado["documento_id"]
    assert firmado["permisos"]["modificar"] is False and firmado["permisos"]["nueva_version"] is True
    doc = tec.get(f"/api/documentos/{firmado['documento_id']}").json()
    assert doc["caso_id"] == caso["id"] and doc["tipo_documental"]["nombre"] == "Informe socioambiental"
    pdf = tec.get(f"/api/documentos/{firmado['documento_id']}/archivo").content
    texto = _texto_pdf(pdf)
    assert "INFORME SOCIOAMBIENTAL" in texto and "Rosa Ficticia" in texto and "1. Reseña" in texto
    assert "Profesión" in texto and "Lic. en Trabajo Social" in texto and "Córdoba 777" in texto
    assert "alert" not in texto
    assert _guardar(tec, firmado, titulo="Otro").status_code == 409

    # Corregir = nueva versión; al firmarla, la anterior queda reemplazada.
    v2 = tec.post(f"/api/informes/{firmado['id']}/nueva-version").json()
    assert v2["version"] == 2 and v2["estado"] == "borrador" and v2["grupo_id"] == firmado["grupo_id"]
    assert tec.post(f"/api/informes/{firmado['id']}/nueva-version").json()["id"] == v2["id"]
    assert _guardar(tec, v2, titulo="Informe socioambiental corregido").status_code == 200
    tec.post(f"/api/informes/{v2['id']}/firmar")
    assert tec.get(f"/api/informes/{firmado['id']}").json()["estado"] == "reemplazado"
    grupos = tec.get(f"/api/casos/{caso['id']}/informes").json()
    assert len(grupos) == 1 and grupos[0]["cantidad_versiones"] == 2
    assert grupos[0]["vigente"]["version"] == 2
    assert len(admin.get(f"/api/personas/{p['id']}/informes").json()) == 1

    # Borradores descartables.
    otro = tec.post("/api/informes", json={"caso_id": caso["id"], "plantilla_id": _plantilla(tec, "Informe de seguimiento")["id"]}).json()
    assert tec.post(f"/api/informes/{otro['id']}/descartar").json()["ok"]
    assert tec.get(f"/api/informes/{otro['id']}").status_code == 404


def test_permisos_de_informes(admin, cliente):
    crear_usuario("tec", "Técnico", AREA_ADMISION)
    crear_usuario("ajeno", "Técnico", AREA_PROMOCION)
    ids = {u["nombre_completo"]: u["id"] for u in admin.get("/api/catalogos").json()["usuarios_asignables"]}
    p = nueva_persona(admin)
    caso = nuevo_caso(admin, p["id"], responsable_id=ids["Tec"])
    ajeno = cliente("ajeno")
    # Sin asignación no se redactan informes en ese caso, pero se pueden leer los firmados.
    assert ajeno.post("/api/informes", json={"caso_id": caso["id"]}).status_code == 403
    inf = cliente("tec").post("/api/informes", json={"caso_id": caso["id"]}).json()
    assert ajeno.get(f"/api/informes/{inf['id']}").json()["permisos"]["modificar"] is False
    assert _guardar(ajeno, inf, titulo="X").status_code == 403


def test_plantillas(admin, cliente):
    crear_usuario("jefa", "Jefe/a de departamento", AREA_ADMISION)
    crear_usuario("tec", "Técnico", AREA_ADMISION)
    jefa, tec = cliente("jefa"), cliente("tec")
    areas = {a["nombre"]: a["id"] for a in admin.get("/api/catalogos").json()["areas"]}
    assert tec.get("/api/plantillas").status_code == 403

    nueva = {
        "nombre": "Informe para juzgado", "area_id": areas[AREA_ADMISION], "titulo": "Informe al juzgado",
        "destinatario": True, "destinatario_inicial": "Sr. Juez", "datos": ["nombre", "documento", "actuacion"],
        "secciones": [{"titulo": "Situación", "guia": "Qué pasa", "texto": "<p>Inicio <b>sugerido</b></p>"}],
    }
    r = jefa.post("/api/plantillas", json=nueva)
    assert r.status_code == 201, r.text
    pl = r.json()
    # Las generales y las de otras áreas no las edita una jefatura.
    general = next(p for p in jefa.get("/api/plantillas").json() if p["area"] is None)
    assert general["puede_editar"] is False
    assert jefa.put(f"/api/plantillas/{general['id']}", json={**nueva, "area_id": None}).status_code == 403
    assert jefa.post("/api/plantillas", json={**nueva, "area_id": areas[AREA_PROMOCION]}).status_code == 403
    assert admin.post("/api/plantillas", json={**nueva, "datos": ["inventado"]}).status_code == 422

    # Un técnico la usa: aparece primero (es de su área) y arma el informe.
    assert tec.get("/api/informes/catalogo").json()["plantillas"][0]["id"] == pl["id"]
    p = nueva_persona(admin)
    inf = tec.post("/api/informes", json={"persona_id": p["id"], "plantilla_id": pl["id"]})
    assert inf.status_code == 403  # sin caso asignado, el legajo ajeno no se modifica
    ids = {u["nombre_completo"]: u["id"] for u in admin.get("/api/catalogos").json()["usuarios_asignables"]}
    caso = nuevo_caso(admin, p["id"], responsable_id=ids["Tec"])
    inf = tec.post("/api/informes", json={"caso_id": caso["id"], "plantilla_id": pl["id"]}).json()
    assert inf["destinatario"] == "Sr. Juez" and inf["titulo"] == "Informe al juzgado"
    assert [d["clave"] for d in inf["datos"]] == ["nombre", "documento", "actuacion"]
    assert inf["secciones"][0]["html"] == "<p>Inicio <b>sugerido</b></p>"
    assert inf["estructura"]["guias"] == {"Situación": "Qué pasa"}

    # Desactivada, ya no se ofrece.
    jefa.put(f"/api/plantillas/{pl['id']}", json={**nueva, "activo": False})
    assert pl["id"] not in {x["id"] for x in tec.get("/api/informes/catalogo").json()["plantillas"]}


def _texto_pdf(contenido: bytes) -> str:
    import pypdfium2 as pdfium

    pdf = pdfium.PdfDocument(io.BytesIO(contenido))
    return "\n".join(pdf[i].get_textpage().get_text_range() for i in range(len(pdf)))

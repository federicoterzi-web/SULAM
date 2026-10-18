import io

from PIL import Image

from conftest import PDF, nueva_persona, nuevo_caso
from sulam import foto_dni


def _jpeg(ancho=800, alto=500):
    b = io.BytesIO()
    Image.new("RGB", (ancho, alto), (200, 180, 160)).save(b, "JPEG")
    return b.getvalue()


def _tipo(admin, nombre):
    return next(t for t in admin.get("/api/catalogos").json()["tipos_documentales"] if t["nombre"].startswith(nombre))


def _subir(admin, persona_id, tipo_id, datos=None, mime="image/jpeg", nombre="dni.jpg"):
    r = admin.post("/api/documentos", data={"persona_id": persona_id, "tipo_documental_id": tipo_id, "titulo": "DNI"}, files={"archivo": (nombre, datos or _jpeg(), mime)})
    assert r.status_code == 201, r.text
    return r.json()


def test_recorte_geometria():
    caja = foto_dni.ampliar({"x": 0.1, "y": 0.2, "w": 0.2, "h": 0.3})
    assert 0 <= caja["x"] and caja["x"] + caja["w"] <= 1 and 0 <= caja["y"] and caja["y"] + caja["h"] <= 1
    assert caja["w"] > 0.2 and caja["h"] > 0.3
    jpeg = foto_dni.recortar(Image.new("RGB", (1000, 600), "white"), {"x": 0.0, "y": 0.0, "w": 0.5, "h": 0.8})
    assert Image.open(io.BytesIO(jpeg)).size[0] <= foto_dni.LADO_MAXIMO
    try:
        foto_dni.recortar(Image.new("RGB", (1000, 600)), {"x": 0.0, "y": 0.0, "w": 0.001, "h": 0.001})
        assert False
    except ValueError:
        pass


def test_foto_desde_el_dni(admin, cliente, monkeypatch):
    from conftest import crear_usuario

    p = nueva_persona(admin)
    dni = _tipo(admin, "DNI")
    doc = _subir(admin, p["id"], dni["id"])
    assert admin.get(f"/api/personas/{p['id']}/foto").status_code == 404
    # Si el detector encuentra una cara, la sugerencia trae el recorte; si no, viene vacía y se ajusta a mano.
    monkeypatch.setattr(foto_dni, "_caras", lambda img: [(0.1, 0.2, 0.2, 0.3)])
    s = admin.get(f"/api/personas/{p['id']}/foto/sugerencia", params={"documento_id": doc["id"]}).json()
    assert s["hoja"] == 1 and s["caja"] and s["caja"]["w"] > 0.2
    monkeypatch.setattr(foto_dni, "_caras", lambda img: [])
    assert admin.get(f"/api/personas/{p['id']}/foto/sugerencia", params={"documento_id": doc["id"]}).json()["caja"] is None
    # Guardar el recorte (sugerido o ajustado a mano).
    r = admin.put(f"/api/personas/{p['id']}/foto", json={"documento_id": doc["id"], "hoja": 1, "caja": {"x": 0.05, "y": 0.1, "w": 0.3, "h": 0.6}})
    assert r.status_code == 200 and r.json()["tiene_foto"]
    f = admin.get(f"/api/personas/{p['id']}/foto")
    assert f.status_code == 200 and f.headers["content-type"] == "image/jpeg" and Image.open(io.BytesIO(f.content)).size[0] > 20
    assert admin.get(f"/api/personas/{p['id']}").json()["tiene_foto"] is True
    # Un recorte demasiado chico se rechaza; un documento de otra persona no sirve.
    assert admin.put(f"/api/personas/{p['id']}/foto", json={"documento_id": doc["id"], "caja": {"x": 0, "y": 0, "w": 0.01, "h": 0.01}}).status_code == 400
    otra = nueva_persona(admin, apellidos="OTRA", nombres="Persona", numero_documento="3000001")
    assert admin.put(f"/api/personas/{otra['id']}/foto", json={"documento_id": doc["id"], "caja": {"x": 0, "y": 0, "w": 0.5, "h": 0.5}}).status_code == 404
    # Quien no modifica legajos no la cambia.
    crear_usuario("per", "Personal")
    assert cliente("per").put(f"/api/personas/{p['id']}/foto", json={"documento_id": doc["id"], "caja": {"x": 0, "y": 0, "w": 0.5, "h": 0.5}}).status_code == 403
    assert admin.delete(f"/api/personas/{p['id']}/foto").status_code == 204
    assert admin.get(f"/api/personas/{p['id']}/foto").status_code == 404


def test_documentacion_requerida_en_caso_abierto(admin):
    p = nueva_persona(admin)
    d = admin.get(f"/api/personas/{p['id']}/documentacion").json()
    assert d["caso_abierto"] is False
    caso = nuevo_caso(admin, p["id"])
    d = admin.get(f"/api/personas/{p['id']}/documentacion").json()
    assert d["caso_abierto"] and d["faltan"] == 1 and d["requeridos"][0]["estado"] == "falta" and d["requeridos"][0]["nombre"].startswith("DNI")
    dni = _tipo(admin, "DNI")
    _subir(admin, p["id"], dni["id"])
    d = admin.get(f"/api/personas/{p['id']}/documentacion").json()
    assert d["faltan"] == 0 and d["requeridos"][0]["estado"] == "presente" and d["presentes"][0]["cantidad"] == 1
    # La Dirección decide qué otros documentos se exigen.
    anses = _tipo(admin, "Certificación negativa")
    assert admin.patch(f"/api/tipos-documentales/{anses['id']}", json={"requerido_en_caso_abierto": True}).status_code == 200
    d = admin.get(f"/api/personas/{p['id']}/documentacion").json()
    assert d["faltan"] == 1 and {r["nombre"].split()[0]: r["estado"] for r in d["requeridos"]} == {"DNI": "presente", "Certificación": "falta"}
    # Con el caso cerrado ya no se exige nada.
    admin.post(f"/api/casos/{caso['id']}/estado", json={"estado": "cerrado", "motivo": "Intervención finalizada"})
    assert admin.get(f"/api/personas/{p['id']}/documentacion").json()["caso_abierto"] is False

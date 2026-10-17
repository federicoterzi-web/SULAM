"""Versión celular: sesión con inactividad corta, fotos de varias hojas y app instalable."""

from __future__ import annotations

import io
from datetime import timedelta

from fastapi.testclient import TestClient
from PIL import Image
from sqlalchemy import text

from conftest import PASSWORD, nueva_persona, nuevo_caso


def _foto(ancho=800, alto=1100, color=(240, 240, 240), exif_gps=False) -> bytes:
    img = Image.new("RGB", (ancho, alto), color)
    salida = io.BytesIO()
    kw = {}
    if exif_gps:
        exif = Image.Exif()
        exif[0x010F] = "Fabricante"  # Make
        exif[0x8825] = {2: (26.0, 49.0, 0.0)}  # GPSInfo (latitud)
        kw["exif"] = exif
    img.save(salida, "JPEG", **kw)
    return salida.getvalue()


def _login_movil():
    from sulam.main import crear_app

    http = TestClient(crear_app())
    r = http.post("/api/auth/login", json={"usuario": "admin", "password": PASSWORD, "dispositivo": "movil"})
    assert r.status_code == 200, r.text
    http.headers["X-CSRF-Token"] = r.json()["csrf_token"]
    return http, r.json()


def test_sesion_movil_vence_antes_por_inactividad(admin, db):
    assert admin.yo["sesion_movil"] is False and admin.yo["inactividad_minutos"] == 60
    http, yo = _login_movil()
    assert yo["sesion_movil"] is True and yo["inactividad_minutos"] == 15
    assert http.get("/api/auth/me").json()["sesion_movil"] is True

    # 20 minutos sin uso: la sesión del celular vence, la de escritorio sigue.
    db.execute(text("UPDATE sesiones SET ultimo_uso = ultimo_uso - :t"), {"t": timedelta(minutes=20)})
    db.commit()
    assert http.get("/api/auth/me").status_code == 401
    assert admin.get("/api/auth/me").status_code == 200

    evento = db.execute(
        text("SELECT detalle FROM auditoria WHERE accion = 'login' ORDER BY id DESC LIMIT 1")
    ).scalar_one()
    assert evento["dispositivo"] == "movil"


def test_fotos_de_varias_hojas_se_guardan_como_un_pdf(admin):
    p = nueva_persona(admin)
    caso = nuevo_caso(admin, p["id"])
    tipo = admin.get("/api/catalogos").json()["tipos_documentales"][0]["id"]
    r = admin.post(
        "/api/documentos/fotos",
        data={"tipo_documental_id": tipo, "titulo": "Ficha fotografiada", "persona_id": p["id"], "caso_id": caso["id"]},
        files=[
            ("fotos", ("hoja1.jpg", _foto(exif_gps=True), "image/jpeg")),
            ("fotos", ("hoja2.jpg", _foto(4000, 3000), "image/jpeg")),
        ],
    )
    assert r.status_code == 201, r.text
    doc = r.json()
    assert doc["mime"] == "application/pdf" and doc["caso_id"] == caso["id"]

    pdf = admin.get(f"/api/documentos/{doc['id']}/archivo").content
    assert pdf.startswith(b"%PDF")
    import pypdfium2

    documento_pdf = pypdfium2.PdfDocument(pdf)
    assert len(documento_pdf) == 2
    # La foto enorme se reduce (lado máximo 2400 px a 200 ppp = 12 pulgadas).
    ancho, alto = documento_pdf[1].get_size()
    assert max(ancho, alto) <= 2400 / 200 * 72 + 1
    # Los metadatos de la cámara (marca, ubicación) no llegan al archivo guardado.
    assert b"Fabricante" not in pdf and b"Exif" not in pdf


def test_fotos_rechaza_archivos_que_no_son_imagenes(admin):
    p = nueva_persona(admin)
    tipo = admin.get("/api/catalogos").json()["tipos_documentales"][0]["id"]
    r = admin.post(
        "/api/documentos/fotos",
        data={"tipo_documental_id": tipo, "titulo": "x", "persona_id": p["id"]},
        files=[("fotos", ("a.pdf", b"%PDF-1.4 hola", "application/pdf"))],
    )
    assert r.status_code == 415


def test_fotos_requiere_permiso(admin, cliente):
    from conftest import crear_usuario

    crear_usuario("tec", "Técnico")
    p = nueva_persona(admin)
    c = cliente("tec")  # sin el caso asignado
    tipo = admin.get("/api/catalogos").json()["tipos_documentales"][0]["id"]
    r = c.post(
        "/api/documentos/fotos",
        data={"tipo_documental_id": tipo, "titulo": "x", "persona_id": p["id"]},
        files=[("fotos", ("a.jpg", _foto(), "image/jpeg"))],
    )
    assert r.status_code == 403


def test_app_instalable(tmp_path, monkeypatch):
    from sulam.config import get_settings
    from sulam.main import crear_app

    (tmp_path / "assets").mkdir()
    (tmp_path / "iconos").mkdir()
    (tmp_path / "index.html").write_text("<html></html>")
    (tmp_path / "manifest.webmanifest").write_text('{"name":"SULAM"}')
    (tmp_path / "sw.js").write_text("// sw")
    (tmp_path / "iconos" / "sulam-192.png").write_bytes(b"\x89PNG")
    monkeypatch.setenv("SULAM_FRONTEND_DIST", str(tmp_path))
    get_settings.cache_clear()
    try:
        http = TestClient(crear_app())
        r = http.get("/manifest.webmanifest")
        assert r.status_code == 200 and r.headers["content-type"].startswith("application/manifest+json")
        r = http.get("/sw.js")
        assert r.status_code == 200 and r.headers["service-worker-allowed"] == "/"
        assert "camera=(self)" in r.headers["permissions-policy"]
        assert http.get("/iconos/sulam-192.png").status_code == 200
    finally:
        monkeypatch.undo()
        get_settings.cache_clear()


def test_qr_usa_la_direccion_oficial(admin, monkeypatch):
    from sulam.config import get_settings
    from sulam.security import url_publica

    class Pedido:
        def __init__(self, url):
            from starlette.datastructures import URL

            self.url = URL(url)
            self.base_url = URL(url)

    # Sin configurar: una dirección que no es local se usa tal cual.
    assert url_publica(Pedido("http://192.168.0.20:8000/")) == ("http://192.168.0.20:8000", True)
    # Configurada: manda, aunque se imprima desde «localhost».
    monkeypatch.setenv("SULAM_URL_PUBLICA", "http://sulam.oficina:8000/")
    get_settings.cache_clear()
    try:
        assert url_publica(Pedido("http://localhost:8000/")) == ("http://sulam.oficina:8000", True)
        r = admin.get("/api/auth/direccion-publica")
        assert r.json() == {"url": "http://sulam.oficina:8000", "sirve_desde_otros_dispositivos": True}
        monkeypatch.delenv("SULAM_URL_PUBLICA")
        monkeypatch.setenv("SULAM_DOMINIO", "sulam.ejemplo.gob.ar")
        get_settings.cache_clear()
        assert url_publica(Pedido("http://localhost:8000/"))[0] == "https://sulam.ejemplo.gob.ar"
    finally:
        monkeypatch.undo()
        get_settings.cache_clear()

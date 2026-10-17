"""Directorio de contactos."""

from __future__ import annotations

from conftest import crear_usuario


def test_directorio(admin, cliente):
    comuna = admin.post("/api/recursos", json={"tipo": "institucion", "categoria": "municipio", "nombre": "Comuna Ficticia"}).json()
    r = admin.post(
        "/api/contactos",
        json={"nombre": "Laura Técnica", "cargo": "Trabajadora social", "institucion": "Comuna Ficticia",
              "categoria": "municipio", "recurso_id": comuna["id"], "departamento": "Lules",
              "telefono": "381 400-1111", "whatsapp": "0381 15 400-1111", "temas": "Adultos mayores, subsidios"},
    )
    assert r.status_code == 201, r.text
    c = r.json()
    assert c["whatsapp"] == "5493814001111"
    assert c["recurso"]["nombre"] == "Comuna Ficticia"
    admin.post("/api/contactos", json={"nombre": "Pedro Juzgado", "institucion": "Juzgado de Familia (ficticio)", "categoria": "justicia"})

    assert [x["nombre"] for x in admin.get("/api/contactos", params={"q": "comuna"}).json()] == ["Laura Técnica"]
    assert [x["nombre"] for x in admin.get("/api/contactos", params={"q": "subsidios"}).json()] == ["Laura Técnica"]
    assert [x["nombre"] for x in admin.get("/api/contactos", params={"recurso_id": comuna["id"]}).json()] == ["Laura Técnica"]
    assert len(admin.get("/api/contactos", params={"categoria": "justicia"}).json()) == 1

    assert admin.post("/api/contactos", json={"nombre": "X Y", "whatsapp": "123"}).status_code == 422
    for escrito in ("381 400-1111", "+54 9 381 400-1111", "(0381) 154001111"):
        assert admin.post("/api/contactos", json={"nombre": "W W", "whatsapp": escrito}).json()["whatsapp"].endswith("3814001111")
    assert admin.post("/api/contactos", json={"nombre": "X Y", "departamento": "Narnia"}).status_code == 400

    crear_usuario("tec", "Técnico")
    tec = cliente("tec")
    assert len(tec.get("/api/contactos").json()) == 5
    assert tec.patch(f"/api/contactos/{c['id']}", json={"cargo": "Otro"}).status_code == 403
    propio = tec.post("/api/contactos", json={"nombre": "Contacto del técnico"}).json()
    assert tec.patch(f"/api/contactos/{propio['id']}", json={"activo": False}).json()["activo"] is False
    assert len(tec.get("/api/contactos").json()) == 5

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


def test_base_institucional_desde_articulaciones_y_capacitaciones(admin, cliente):
    from conftest import AREA_ADMISION, nueva_persona, nuevo_caso

    catalogo = admin.get("/api/recursos/catalogo").json()
    assert {o["codigo"] for o in catalogo["origenes"]} >= {"capacitacion", "articulacion"}

    # Participación carga lo relevado en una capacitación.
    c1 = admin.post(
        "/api/contactos",
        json={"nombre": "Promotora Ficticia", "institucion": "CIC Barrio Ejemplo", "origen": "capacitacion",
              "origen_detalle": "Taller de buen trato, octubre 2026"},
    ).json()
    assert c1["origen"] == "capacitacion" and c1["articulaciones"] == 0
    assert admin.post("/api/contactos", json={"nombre": "X Y", "origen": "inventado"}).status_code == 400

    # Un técnico articula en su caso con un contacto existente y con uno nuevo.
    crear_usuario("tec", "Técnico", AREA_ADMISION)
    tec_id = {u["nombre_completo"]: u["id"] for u in admin.get("/api/catalogos").json()["usuarios_asignables"]}["Tec"]
    caso = nuevo_caso(admin, nueva_persona(admin)["id"], responsable_id=tec_id)
    tec = cliente("tec")
    r = tec.post(f"/api/casos/{caso['id']}/articulaciones", json={"contacto_id": c1["id"], "motivo": "Acompañamiento en el barrio"})
    assert r.status_code == 201, r.text
    r = tec.post(
        f"/api/casos/{caso['id']}/articulaciones",
        json={"nuevo_contacto": {"nombre": "Juez Ficticio", "institucion": "Juzgado de Familia (ficticio)", "categoria": "justicia"},
              "motivo": "Pedido de informe", "resultado": "Se envió el informe"},
    )
    assert r.status_code == 201, r.text
    nuevo = r.json()["contacto"]
    assert nuevo["origen"] == "articulacion" and nuevo["origen_detalle"] == f"Caso {caso['caratula']['numero_actuacion']}/{caso['caratula']['anio_actuacion']}"

    lista = tec.get(f"/api/casos/{caso['id']}/articulaciones").json()
    assert [x["contacto"]["nombre"] for x in lista] == ["Juez Ficticio", "Promotora Ficticia"]
    usos = {c["nombre"]: c["articulaciones"] for c in admin.get("/api/contactos").json()}
    assert usos["Promotora Ficticia"] == 1 and usos["Juez Ficticio"] == 1
    assert admin.get(f"/api/contactos/{c1['id']}/articulaciones").json()[0]["motivo"] == "Acompañamiento en el barrio"

    # Sin el caso asignado no se puede registrar.
    crear_usuario("otro", "Técnico", AREA_ADMISION)
    assert cliente("otro").post(f"/api/casos/{caso['id']}/articulaciones", json={"contacto_id": c1["id"]}).status_code == 403
    assert tec.post(f"/api/casos/{caso['id']}/articulaciones", json={"motivo": "sin nadie"}).status_code == 400

from conftest import AREA_ADMISION, crear_usuario, nueva_persona, nuevo_caso


def test_antecedentes_para_todos_los_roles_con_datos_minimos(admin, cliente):
    crear_usuario("tec1", "Técnico", AREA_ADMISION)
    crear_usuario("per", "Personal")
    crear_usuario("mesa", "Mesa de Entrada")
    ids = {u["nombre_completo"]: u["id"] for u in admin.get("/api/catalogos").json()["usuarios_asignables"]}
    p = nueva_persona(admin, apellidos="GOMEZ", nombres="Rosa", numero_documento="11222333", telefono="381-0000", observaciones="dato reservado")
    nuevo_caso(admin, p["id"], fecha_ingreso="2026-03-04", responsable_id=ids["Tec1"])
    for usuario in ("per", "mesa", "tec1"):
        c = cliente(usuario)
        r = c.get("/api/antecedentes", params={"q": "gomez rosa"})
        assert r.status_code == 200, (usuario, r.text)
        fila = r.json()[0]
        # Solo nombre, documento, fecha de carátula y responsable: nada más.
        assert set(fila) == {"nombre", "documento", "casos"}
        assert fila["nombre"] == "GOMEZ, Rosa" and fila["documento"] == "DNI 11222333"
        assert fila["casos"] == [{"fecha_caratula": "2026-03-04", "responsables": ["Tec1"]}]
    # También por documento, y sin resultados no devuelve nada.
    assert len(cliente("per").get("/api/antecedentes", params={"q": "11.222.333"}).json()) == 1
    assert cliente("per").get("/api/antecedentes", params={"q": "zzzzzz"}).json() == []
    # Quien no puede ver legajos no los ve por otra vía.
    assert cliente("per").get(f"/api/personas/{p['id']}").status_code == 403
    # Mínimo de 3 letras y queda auditado.
    assert cliente("per").get("/api/antecedentes", params={"q": "go"}).status_code == 422
    aud = admin.get("/api/auditoria", params={"accion": "consultar_antecedentes"}).json()
    aud = aud["items"] if isinstance(aud, dict) else aud
    assert aud and all(a["accion"] == "consultar_antecedentes" for a in aud)

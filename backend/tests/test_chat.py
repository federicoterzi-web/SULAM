"""Chat interno: conversaciones 1 a 1 y en grupo, no leídos, privacidad y avisos."""

from __future__ import annotations

from conftest import AREA_ADMISION, AREA_PROMOCION, crear_usuario


def _ids(admin):
    return {u["nombre_completo"]: u["id"] for u in admin.get("/api/catalogos").json()["usuarios_asignables"]}


def test_chat_directo_no_leidos_y_privacidad(admin, cliente):
    crear_usuario("ana", "Técnico", AREA_ADMISION)
    crear_usuario("beto", "Técnico", AREA_PROMOCION)
    crear_usuario("carla", "Mesa de Entrada")
    ana, beto, carla = cliente("ana"), cliente("beto"), cliente("carla")
    uid = {u["nombre_completo"]: u["id"] for u in ana.get("/api/chat/usuarios").json()}
    assert "Ana" not in uid and {"Beto", "Carla"} <= set(uid)  # uno mismo no aparece
    assert [u["nombre_completo"] for u in ana.get("/api/chat/usuarios", params={"q": "bet"}).json()] == ["Beto"]

    # Ana le escribe a Beto; la conversación 1 a 1 es una sola aunque se abra desde los dos lados.
    c = ana.post("/api/chat/conversaciones", json={"tipo": "directo", "usuario_id": uid["Beto"]})
    assert c.status_code == 201, c.text
    conv = c.json()
    assert conv["titulo"] == "Beto" and conv["no_leidos"] == 0
    otra = beto.post("/api/chat/conversaciones", json={"tipo": "directo", "usuario_id": ana.get("/api/auth/me").json()["id"]}).json()
    assert otra["id"] == conv["id"] and otra["titulo"] == "Ana"
    assert ana.post("/api/chat/conversaciones", json={"tipo": "directo", "usuario_id": uid["Beto"]}).json()["id"] == conv["id"]

    r = ana.post(f"/api/chat/conversaciones/{conv['id']}/mensajes", json={"cuerpo": "  Hola, ¿viste el caso 12?  "})
    assert r.status_code == 201 and r.json()["cuerpo"] == "Hola, ¿viste el caso 12?" and r.json()["mio"]
    ana.post(f"/api/chat/conversaciones/{conv['id']}/mensajes", json={"cuerpo": "Te lo paso hoy"})

    # Beto tiene 2 sin leer; al abrir la conversación quedan leídos.
    assert beto.get("/api/chat/no-leidos").json() == {"mensajes": 2, "conversaciones": 1}
    assert len(beto.get("/api/avisos").json()["avisos"]["chat"]) == 1
    lista = beto.get("/api/chat/conversaciones").json()
    assert lista["no_leidos"] == 2 and lista["conversaciones"][0]["ultimo"]["cuerpo"] == "Te lo paso hoy"
    m = beto.get(f"/api/chat/conversaciones/{conv['id']}/mensajes").json()["mensajes"]
    assert [x["cuerpo"] for x in m] == ["Hola, ¿viste el caso 12?", "Te lo paso hoy"] and not m[0]["mio"]
    assert beto.get("/api/chat/no-leidos").json() == {"mensajes": 0, "conversaciones": 0}
    assert beto.get("/api/avisos").json()["avisos"]["chat"] == []
    # Los propios mensajes de Ana nunca le cuentan como sin leer.
    assert ana.get("/api/chat/no-leidos").json()["mensajes"] == 0

    # Mensajes posteriores a uno dado (para actualizar sin repetir).
    beto.post(f"/api/chat/conversaciones/{conv['id']}/mensajes", json={"cuerpo": "Dale"})
    nuevos = ana.get(f"/api/chat/conversaciones/{conv['id']}/mensajes", params={"despues": m[-1]["id"]}).json()["mensajes"]
    assert [x["cuerpo"] for x in nuevos] == ["Dale"]

    # Carla no ve la conversación ajena ni puede escribir en ella; tampoco la administración.
    assert carla.get(f"/api/chat/conversaciones/{conv['id']}/mensajes").status_code == 404
    assert carla.post(f"/api/chat/conversaciones/{conv['id']}/mensajes", json={"cuerpo": "intruso"}).status_code == 404
    assert carla.get("/api/chat/conversaciones").json()["conversaciones"] == []
    assert admin.get(f"/api/chat/conversaciones/{conv['id']}/mensajes").status_code == 404

    # Borrar: solo los propios; queda el hueco y no el texto.
    mid = nuevos[0]["id"]
    assert ana.delete(f"/api/chat/mensajes/{mid}").status_code == 404
    assert beto.delete(f"/api/chat/mensajes/{mid}").json()["ok"]
    despues = ana.get(f"/api/chat/conversaciones/{conv['id']}/mensajes").json()["mensajes"]
    assert despues[-1]["borrado"] and despues[-1]["cuerpo"] is None

    # Validaciones.
    assert ana.post(f"/api/chat/conversaciones/{conv['id']}/mensajes", json={"cuerpo": "   "}).status_code in (400, 422)
    assert ana.post(f"/api/chat/conversaciones/{conv['id']}/mensajes", json={"cuerpo": "x" * 2001}).status_code == 422
    yo_ana = ana.get("/api/auth/me").json()["id"]
    assert ana.post("/api/chat/conversaciones", json={"tipo": "directo", "usuario_id": yo_ana}).status_code == 400

    # La auditoría registra que hubo conversación, no el texto.
    aud = admin.get("/api/auditoria", params={"entidad": "chat_conversacion"}).json()
    aud = aud["items"] if isinstance(aud, dict) else aud
    assert aud and "Hola" not in str(aud) and "caso 12" not in str(aud)


def test_chat_grupos(admin, cliente):
    for u, rol, area in (("ana", "Técnico", AREA_ADMISION), ("beto", "Técnico", AREA_PROMOCION), ("carla", "Mesa de Entrada", None), ("dora", "Personal", None)):
        crear_usuario(u, rol, area)
    ana, beto, carla, dora = (cliente(u) for u in ("ana", "beto", "carla", "dora"))
    uid = {u["nombre_completo"]: u["id"] for u in ana.get("/api/chat/usuarios").json()}

    assert ana.post("/api/chat/conversaciones", json={"tipo": "grupo", "titulo": "", "usuarios_ids": [uid["Beto"]]}).status_code == 400
    assert ana.post("/api/chat/conversaciones", json={"tipo": "grupo", "titulo": "Equipo", "usuarios_ids": []}).status_code == 400
    g = ana.post("/api/chat/conversaciones", json={"tipo": "grupo", "titulo": "Guardia del fin de semana", "usuarios_ids": [uid["Beto"], uid["Carla"]]})
    assert g.status_code == 201, g.text
    g = g.json()
    assert g["tipo"] == "grupo" and g["titulo"] == "Guardia del fin de semana" and len(g["participantes"]) == 3
    ana.post(f"/api/chat/conversaciones/{g['id']}/mensajes", json={"cuerpo": "¿Quién cubre el sábado?"})
    for c in (beto, carla):
        assert c.get("/api/chat/no-leidos").json()["mensajes"] == 1
    assert dora.get(f"/api/chat/conversaciones/{g['id']}/mensajes").status_code == 404

    # Solo quien creó el grupo suma gente; quien se suma no ve lo anterior.
    assert beto.post(f"/api/chat/conversaciones/{g['id']}/participantes", json={"usuarios_ids": [uid["Dora"]]}).status_code == 403
    assert ana.post(f"/api/chat/conversaciones/{g['id']}/participantes", json={"usuarios_ids": [uid["Dora"]]}).status_code == 200
    ana.post(f"/api/chat/conversaciones/{g['id']}/mensajes", json={"cuerpo": "Yo cubro el sábado"})
    visto = [m["cuerpo"] for m in dora.get(f"/api/chat/conversaciones/{g['id']}/mensajes").json()["mensajes"]]
    assert visto == ["Yo cubro el sábado"]

    # Salir del grupo.
    assert carla.post(f"/api/chat/conversaciones/{g['id']}/salir").json()["ok"]
    assert carla.get(f"/api/chat/conversaciones/{g['id']}/mensajes").status_code == 404
    assert carla.get("/api/chat/no-leidos").json()["mensajes"] == 0

    # Una persona dada de baja no se puede sumar y no recibe conversaciones nuevas.
    ids = {u["usuario"]: u["id"] for u in admin.get("/api/admin/usuarios").json()}
    assert admin.patch(f"/api/admin/usuarios/{ids['dora']}", json={"activo": False}).status_code == 200
    assert ana.post("/api/chat/conversaciones", json={"tipo": "directo", "usuario_id": uid["Dora"]}).status_code == 400
    assert "Dora" not in [u["nombre_completo"] for u in ana.get("/api/chat/usuarios").json()]


def test_chat_sin_permiso(admin, cliente):
    crear_usuario("ana", "Técnico", AREA_ADMISION)
    ana = cliente("ana")
    # Se puede quitar desde Administración: sin el permiso no se usa el chat.
    roles = admin.get("/api/admin/roles").json()
    rol = next(r for r in roles if r["nombre"] == "Técnico")
    permisos = [p for p in rol["permisos"] if not (p["modulo"] == "chat" and p["accion"] == "usar")]
    assert len(permisos) < len(rol["permisos"]), "los roles traen el chat por defecto"
    r = admin.put(f"/api/admin/roles/{rol['id']}", json={"nombre": rol["nombre"], "descripcion": rol.get("descripcion"), "permisos": permisos})
    assert r.status_code == 200, r.text
    assert ana.get("/api/chat/conversaciones").status_code == 403
    assert ana.get("/api/avisos").json()["avisos"]["chat"] == []

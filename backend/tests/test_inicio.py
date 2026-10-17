"""Página de inicio según el rol."""

from __future__ import annotations

from conftest import AREA_ADMISION, AREA_PROMOCION, crear_usuario, nueva_persona, nuevo_caso


def _areas(admin):
    return {a["nombre"]: a["id"] for a in admin.get("/api/catalogos").json()["areas"]}


def _usuarios(admin):
    return {u["nombre_completo"]: u["id"] for u in admin.get("/api/catalogos").json()["usuarios_asignables"]}


def test_perfiles_segun_roles(admin, cliente):
    assert admin.get("/api/inicio").json()["perfil"] == "direccion"
    crear_usuario("tec", "Técnico", AREA_ADMISION)
    r = cliente("tec").get("/api/inicio").json()
    assert r["perfil"] == "tecnico" and [p["codigo"] for p in r["perfiles"]] == ["tecnico"]
    assert cliente("tec").get("/api/inicio", params={"perfil": "direccion"}).status_code == 403
    crear_usuario("mesa", "Mesa de Entrada")
    assert cliente("mesa").get("/api/inicio").json()["perfil"] == "mesa"


def test_inicio_tecnico_prioriza_maltrato(admin, cliente):
    crear_usuario("tec", "Técnico", AREA_ADMISION)
    tec = _usuarios(admin)["Tec"]
    comun = nuevo_caso(admin, nueva_persona(admin, apellidos="UNO", numero_documento="1111111")["id"], responsable_id=tec)
    grave = nuevo_caso(
        admin,
        nueva_persona(admin, apellidos="DOS", nombres="Otra", numero_documento="2222222")["id"],
        responsable_id=tec,
        indicadores=["maltrato.fisico"],
    )
    admin.post(f"/api/casos/{comun['id']}/evolucion", json={"texto": "Llamado de seguimiento"})
    casos = cliente("tec").get("/api/inicio").json()["datos"]["casos"]
    assert [c["id"] for c in casos] == [grave["id"], comun["id"]]
    assert casos[0]["alertas"]["maltrato"] and casos[0]["alertas"]["nuevo"]
    assert casos[1]["ultima_evolucion"]["texto"] == "Llamado de seguimiento"


def test_inicio_jefatura(admin, cliente):
    areas = _areas(admin)
    crear_usuario("jefa", "Jefe/a de departamento", AREA_ADMISION)
    crear_usuario("tec", "Técnico", AREA_ADMISION)
    tec = _usuarios(admin)["Tec"]
    p1 = nueva_persona(admin, apellidos="ADM", numero_documento="3333333")
    p2 = nueva_persona(admin, apellidos="ADMDOS", nombres="Otro", numero_documento="4444444")
    p3 = nueva_persona(admin, apellidos="PROMO", nombres="Otra", numero_documento="5555555")
    sin_resp = nuevo_caso(admin, p1["id"], area_id=areas[AREA_ADMISION], motivo="caso del área")
    nuevo_caso(admin, p2["id"], area_id=areas[AREA_ADMISION], responsable_id=tec)
    nuevo_caso(admin, p3["id"], area_id=areas[AREA_PROMOCION], motivo="caso de otra área")

    jefa = cliente("jefa")
    d = jefa.get("/api/inicio").json()["datos"]
    assert d["area"]["nombre"] == AREA_ADMISION
    assert [c["id"] for c in d["sin_responsable"]] == [sin_resp["id"]]
    assert {e["nombre_completo"]: e["casos_activos"] for e in d["equipo"]}["Tec"] == 1
    assert d["activos"] == 2 and d["mes"]["nuevas"] == 2
    assert d["sin_responsable"][0]["motivo"] == "caso del área"


def test_inicio_direccion_resumen_por_area(admin):
    areas = _areas(admin)
    p1 = nueva_persona(admin, apellidos="A", numero_documento="6666666")
    p2 = nueva_persona(admin, apellidos="B", nombres="Otro", numero_documento="7777777")
    nuevo_caso(admin, p1["id"], area_id=areas[AREA_ADMISION], indicadores=["maltrato.economico"])
    c2 = nuevo_caso(admin, p2["id"], area_id=areas[AREA_PROMOCION])
    admin.post(f"/api/casos/{c2['id']}/reiteraciones", json={"motivo": "vuelve a consultar"})
    d = admin.get("/api/inicio").json()["datos"]
    por = {a["area"]: a for a in d["por_area"]}
    assert por[AREA_ADMISION]["nuevas"] == 1 and por[AREA_PROMOCION]["reiteraciones"] == 1
    assert d["totales"]["nuevas"] == 2 and d["sin_responsable"]["cantidad"] == 2
    assert d["maltrato_mes"]["casos"] == 1 and d["maltrato_mes"]["por_tipo"] == {"maltrato.economico": 1}


def test_inicio_carga(admin, cliente):
    crear_usuario("carga", "Carga de Datos", AREA_ADMISION)
    carga = cliente("carga")
    nuevo_caso(carga, nueva_persona(carga, numero_documento="8888888")["id"])
    d = carga.get("/api/inicio").json()["datos"]
    assert d["sin_registro_cantidad"] == 1 and d["pendientes_impresion"] == 1 and d["hoy"]["casos"] == 1


def test_inicio_del_rol_se_puede_cambiar(admin):
    roles = {r["nombre"]: r for r in admin.get("/api/admin/roles").json()}
    rol = roles["Técnico"]
    assert rol["inicio"] == "tecnico"
    cuerpo = {k: rol[k] for k in ("nombre", "descripcion", "activo", "permisos")}
    assert admin.put(f"/api/admin/roles/{rol['id']}", json=cuerpo).json()["inicio"] == "tecnico"  # sin el campo, se conserva
    assert admin.put(f"/api/admin/roles/{rol['id']}", json={**cuerpo, "inicio": "carga"}).json()["inicio"] == "carga"


def test_jefe_de_division_igual_que_jefe_de_departamento_en_su_area(admin, cliente):
    areas = _areas(admin)
    cuidados = "División Cuidados y Promoción de Autonomía"
    crear_usuario("jefa_div", "Jefe/a de división", cuidados)
    p = nueva_persona(admin, apellidos="CUIDADOS", numero_documento="9999999")
    caso = nuevo_caso(admin, p["id"], area_id=areas[cuidados], motivo="caso de la división")
    jefa = cliente("jefa_div")
    r = jefa.get("/api/inicio").json()
    assert r["perfil"] == "jefatura" and r["datos"]["area"]["nombre"] == cuidados
    assert [c["id"] for c in r["datos"]["sin_responsable"]] == [caso["id"]]
    assert jefa.get(f"/api/casos/{caso['id']}").json()["motivo"] == "caso de la división"
    roles = {x["nombre"]: x for x in admin.get("/api/admin/roles").json()}
    assert roles["Jefe/a de división"]["permisos"] == roles["Jefe/a de departamento"]["permisos"]


def test_pendientes_del_tecnico_y_filtros(admin, cliente):
    areas = _areas(admin)
    crear_usuario("tec", "Técnico", AREA_ADMISION)
    tec_id = _usuarios(admin)["Tec"]
    p = nueva_persona(admin, apellidos="PEND", numero_documento="6666666")
    caso = nuevo_caso(admin, p["id"], area_id=areas[AREA_ADMISION], responsables_ids=[tec_id])
    cerrado = nuevo_caso(admin, nueva_persona(admin, apellidos="CERR", numero_documento="7777777")["id"], responsables_ids=[tec_id])
    admin.post(f"/api/casos/{cerrado['id']}/estado", json={"estado": "cerrado", "motivo": "Prueba"})
    tec = cliente("tec")
    inf = tec.post("/api/informes", json={"caso_id": caso["id"]}).json()

    d = tec.get("/api/inicio").json()["datos"]
    assert [c["id"] for c in d["casos"]] == [caso["id"]]  # el cerrado no aparece
    assert d["casos"][0]["alertas"]["sin_registro"] is True
    assert [b["id"] for b in d["borradores"]] == [inf["id"]]

    # Sin técnico a cargo, por área (enlaces del inicio).
    sin = nuevo_caso(admin, nueva_persona(admin, apellidos="SIN", numero_documento="8888888")["id"], area_id=areas[AREA_ADMISION])
    r = admin.get("/api/casos", params={"sin_responsable": True, "activos": True, "area_id": areas[AREA_ADMISION]}).json()
    assert [c["id"] for c in r] == [sin["id"]]
    dir_ = admin.get("/api/inicio", params={"perfil": "direccion"}).json()["datos"]
    fila = next(a for a in dir_["por_area"] if a["area_id"] == areas[AREA_ADMISION])
    assert fila["sin_responsable"] == 1 and "informes_mes" in dir_

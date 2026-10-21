"""Integración con el Sistema de Expedientes del Ministerio (extensión de Chrome)."""

from __future__ import annotations

from fastapi.testclient import TestClient

from conftest import AREA_ADMISION, Cliente, crear_usuario, nueva_persona


def _expediente(clave="21768/425-AM-2026", dni="14961387", llegada="2026-10-13T12:36:00-03:00", recepcionado=True):
    return {
        "clave": clave,
        "url": "http://www.desarrollosocialtuc.gob.ar/seds/expe/expedienteVer.do?expNum=21768",
        "bandeja": {
            "asignado": "USUARIOX",
            "fecha_asignacion": "2026-10-13",
            "formato": "DIGITAL",
            "fecha_ingreso": "2026-10-09",
            "nomenclador": "SUBSIDIO A PERSONA-Dinero",
            "asunto": "REF. SE SOLICITA SUBSIDIO ECONÓMICO PARA EL SR PRUEBA",
            "causante": "425-DIRECCION DE ADULTOS MAYORES",
            "estado": "PENDIENTE",
        },
        "detalle": {
            "oficina_origen": "MESA DE ENTRADA - MDS",
            "fecha_ingreso": "2026-10-09T13:10:00-03:00",
            "causante": "425-DIRECCION DE ADULTOS MAYORES",
            "beneficiario": f"PRUEBA, PERSONA - D. N. I.: {dni}" if dni else "Sin Beneficiario cargado",
            "asunto": "Solicitud de dinero_REF. SE SOLICITA SUBSIDIO",
            "nomenclador": "SUBSIDIO A PERSONA-Dinero",
            "prioridad": "SIN PRIORIDAD",
        },
        "movimientos": [
            {
                "ingreso": {"fecha": "2026-10-09T13:10:00-03:00", "usuario": "MESA1", "texto": "09/10/2026-1310-MESA1"},
                "fojas_ingreso": 10,
                "oficina_origen": None,
                "nota": "ALTA DE MESA DE ENTRADA",
                "oficina": "MESA DE ENTRADA - MDS",
                "estado": "PASE EFECTIVO",
            },
            {
                "ingreso": {"fecha": "2026-10-13T09:55:00-03:00", "usuario": "MESA2", "texto": "13/10/2026-955-MESA2"},
                "fojas_ingreso": 12,
                "oficina_origen": "MESA DE ENTRADA - MDS",
                "nota": "P/SU INTERVENCION",
                "oficina": "DIRECCION DE ADULTOS MAYORES",
                "recepcion": (
                    {"fecha": llegada, "usuario": "RECEP", "texto": "13/10/2026-1236-RECEP"} if recepcionado else None
                ),
                "estado": "PENDIENTE",
                "dias_pendiente": 5,
            },
        ],
    }


def _extension(token: str) -> TestClient:
    from sulam.main import crear_app

    c = TestClient(crear_app())
    c.headers["Authorization"] = f"Bearer {token}"
    return c


def _token(c: Cliente) -> str:
    r = c.post("/api/integracion/tokens", json={"nombre": "Chrome de prueba"})
    assert r.status_code == 201, r.text
    return r.json()["token"]


def test_sincronizar_crea_un_ingreso_por_pase_y_no_duplica(admin):
    crear_usuario("mesa", "Mesa de Entrada", "División Asistencia Administrativa")
    mesa = Cliente("mesa")
    persona = nueva_persona(admin, numero_documento="14961387")
    ext = _extension(_token(mesa))

    assert ext.get("/api/integracion/yo").json()["puede_cargar"] is True

    r = ext.post("/api/integracion/ministerio/sincronizar", json={"expedientes": [_expediente()]})
    assert r.status_code == 200, r.text
    res = r.json()
    assert res["ingresos_creados"] == 1
    assert res["resultados"][0]["persona_sugerida"]["id"] == persona["id"]

    # Volver a sincronizar no duplica el ingreso.
    r = ext.post("/api/integracion/ministerio/sincronizar", json={"expedientes": [_expediente()]})
    assert r.json()["ingresos_creados"] == 0

    ingresos = mesa.get("/api/ingresos", params={"q": "21768/425-AM-2026"}).json()
    assert len(ingresos) == 1
    i = mesa.get(f"/api/ingresos/{ingresos[0]['id']}").json()
    assert i["documento_mencionado"] == "14961387"
    assert i["persona_mencionada"] == "PRUEBA, PERSONA"
    assert i["folios"] == 12
    assert i["remitente"].endswith("MESA DE ENTRADA - MDS")
    assert i["expediente_ministerio"]["clave"] == "21768/425-AM-2026"
    assert [s["id"] for s in i["sugerencias"]] == [persona["id"]]

    est = ext.get("/api/integracion/ministerio/estado", params={"claves": "21768/425-AM-2026,1/1-X-2026"}).json()
    assert list(est) == ["21768/425-AM-2026"]
    assert est["21768/425-AM-2026"]["ingresos"][0]["numero"] == i["numero"]


def test_pases_anteriores_a_la_fecha_solo_se_guardan(admin):
    ext = _extension(_token(admin))
    r = ext.post(
        "/api/integracion/ministerio/sincronizar",
        json={"crear_ingresos_desde": "2026-10-20", "expedientes": [_expediente(dni=None)]},
    )
    assert r.status_code == 200, r.text
    assert r.json()["ingresos_creados"] == 0
    lista = admin.get("/api/ministerio/expedientes").json()
    assert lista[0]["clave"] == "21768/425-AM-2026"
    assert lista[0]["documento_beneficiario"] is None
    assert lista[0]["beneficiario"] is None


def test_token_revocado_y_sin_permiso(admin):
    crear_usuario("tec", "Técnico", AREA_ADMISION)
    tec = Cliente("tec")
    assert tec.post("/api/integracion/tokens", json={}).status_code == 403

    token = _token(admin)
    ext = _extension(token)
    assert ext.get("/api/integracion/yo").status_code == 200
    tid = admin.get("/api/integracion/tokens").json()[0]["id"]
    assert admin.delete(f"/api/integracion/tokens/{tid}").status_code == 200
    assert ext.get("/api/integracion/yo").status_code == 401
    assert _extension("sulam_inventado").get("/api/integracion/yo").status_code == 401
    # La clave no sirve para la API normal (que usa la sesión).
    assert _extension(token).get("/api/ingresos").status_code == 401


def test_vincular_expediente_del_ministerio_a_un_legajo(admin):
    persona = nueva_persona(admin, numero_documento="14961387")
    ext = _extension(_token(admin))
    ext.post("/api/integracion/ministerio/sincronizar", json={"expedientes": [_expediente()]})
    em = admin.get("/api/ministerio/expedientes").json()[0]
    assert em["expediente_id"] is None

    r = admin.post(f"/api/ministerio/expedientes/{em['id']}/vincular", json={"persona_id": persona["id"]})
    assert r.status_code == 201, r.text
    exp = r.json()
    assert exp["numero"] == "21768/425-AM-2026"
    assert exp["expediente_ministerio_id"] == em["id"]

    # No se puede vincular dos veces.
    r = admin.post(f"/api/ministerio/expedientes/{em['id']}/vincular", json={"persona_id": persona["id"]})
    assert r.status_code == 409

    # La lista del Ministerio ahora apunta al expediente de SULAM.
    assert admin.get("/api/ministerio/expedientes").json()[0]["expediente_id"] == exp["id"]

    # La ficha del expediente trae lo que dice el Ministerio, con los pases.
    ficha = admin.get(f"/api/expedientes/{exp['id']}").json()
    assert ficha["ministerio"]["oficina_actual"] == "DIRECCION DE ADULTOS MAYORES"
    assert len(ficha["ministerio"]["movimientos"]) == 2
    assert ficha["documentos"] == [] and ficha["persona"]["id"] == persona["id"]


def test_vincular_sin_permiso_sobre_el_legajo(admin):
    persona = nueva_persona(admin)
    ext = _extension(_token(admin))
    ext.post("/api/integracion/ministerio/sincronizar", json={"expedientes": [_expediente(dni=None)]})
    em = admin.get("/api/ministerio/expedientes").json()[0]
    crear_usuario("tec2", "Técnico", AREA_ADMISION)
    tec = Cliente("tec2")
    r = tec.post(f"/api/ministerio/expedientes/{em['id']}/vincular", json={"persona_id": persona["id"]})
    assert r.status_code in (403, 404)

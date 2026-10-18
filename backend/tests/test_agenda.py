"""Agenda: actividades propias y del área, resultado y su paso a la evolución del caso."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from conftest import AREA_ADMISION, crear_usuario, nueva_persona, nuevo_caso

OTRA = "Departamento Promoción Integral de Derechos"


def _cuando(horas=24, dias=0):
    return (datetime.now(timezone.utc) + timedelta(hours=horas, days=dias)).replace(microsecond=0).isoformat()


def _ev(c, **kw):
    datos = {"tipo": "visita", "titulo": "Visita domiciliaria", "inicio": _cuando(), "lugar": "Domicilio"}
    datos.update(kw)
    return c.post("/api/agenda", json=datos)


def test_propia_y_del_area(admin, cliente):
    crear_usuario("tec1", "Técnico", AREA_ADMISION)
    crear_usuario("tec2", "Técnico", AREA_ADMISION)
    crear_usuario("otro", "Técnico", OTRA)
    a, b, o = cliente("tec1"), cliente("tec2"), cliente("otro")
    e = _ev(a, titulo="Reunión de equipo", tipo="reunion")
    assert e.status_code == 201, e.text
    desde, hasta = _cuando(-48), _cuando(24 * 10)
    # La ve quien participa; el compañero de área la ve en «el área» pero no en «las mías»; otra área no la ve.
    assert len(a.get("/api/agenda", params={"desde": desde, "hasta": hasta}).json()["eventos"]) == 1
    assert b.get("/api/agenda", params={"desde": desde, "hasta": hasta}).json()["eventos"] == []
    assert len(b.get("/api/agenda", params={"desde": desde, "hasta": hasta, "ambito": "area"}).json()["eventos"]) == 1
    assert o.get("/api/agenda", params={"desde": desde, "hasta": hasta, "ambito": "area"}).json()["eventos"] == []
    assert o.get(f"/api/agenda/{e.json()['id']}").status_code == 403
    # Con alcance «propios» para modificar, el compañero puede verla pero no tocarla.
    assert b.patch(f"/api/agenda/{e.json()['id']}", json={"titulo": "Cambio ajeno"}).status_code == 403
    assert a.patch(f"/api/agenda/{e.json()['id']}", json={"titulo": "Reunión de equipo (aula)"}).json()["titulo"].endswith("(aula)")


def test_no_agenda_para_otra_area_ni_a_personas_dadas_de_baja(admin, cliente):
    crear_usuario("tec1", "Técnico", AREA_ADMISION)
    crear_usuario("otro", "Técnico", OTRA)
    a = cliente("tec1")
    otro_id = next(u["id"] for u in admin.get("/api/admin/usuarios").json() if u["usuario"] == "otro")
    r = _ev(a, participantes=[otro_id])
    assert r.status_code == 403, r.text
    assert _ev(a, tipo="inexistente").status_code == 422
    assert _ev(a, fin=_cuando(-5)).status_code == 422


def test_resultado_de_una_salida_queda_en_el_caso(admin, cliente):
    crear_usuario("tec1", "Técnico", AREA_ADMISION)
    a = cliente("tec1")
    p = nueva_persona(admin)
    caso = nuevo_caso(admin, p["id"])
    e = _ev(admin, tipo="salida", titulo="Salida a domicilio", persona_id=p["id"], caso_id=caso["id"], lugar="Barrio Sur").json()
    assert e["persona"]["nombre"].startswith("PRUEBA") and e["caso"]["id"] == caso["id"]
    # No se puede dar por no realizada sin motivo.
    assert admin.post(f"/api/agenda/{e['id']}/resultado", json={"estado": "no_realizado"}).status_code == 400
    r = admin.post(f"/api/agenda/{e['id']}/resultado", json={"estado": "realizado", "resultado": "Se la encontró bien; se acordó nueva visita."})
    assert r.status_code == 200 and r.json()["estado"] == "realizado"
    ficha = admin.get(f"/api/casos/{caso['id']}").json()
    textos = [x["texto"] for x in ficha.get("evoluciones", [])]
    assert any("Salida realizada" in t and "nueva visita" in t for t in textos), ficha.keys()
    # Ya tiene resultado: no se vuelve a resolver ni se modifica.
    assert admin.post(f"/api/agenda/{e['id']}/resultado", json={"estado": "cancelado"}).status_code == 409
    assert admin.patch(f"/api/agenda/{e['id']}", json={"titulo": "otro"}).status_code == 409


def test_avisos_de_agenda_solo_para_participantes(admin, cliente):
    crear_usuario("tec1", "Técnico", AREA_ADMISION)
    crear_usuario("tec2", "Técnico", AREA_ADMISION)
    a, b = cliente("tec1"), cliente("tec2")
    assert _ev(a, inicio=_cuando(3)).status_code == 201
    assert _ev(a, titulo="Lejana", inicio=_cuando(24 * 5)).status_code == 201
    assert len(a.get("/api/avisos").json()["avisos"]["agenda"]) == 1
    assert b.get("/api/avisos").json()["avisos"]["agenda"] == []


def test_roles_existentes_reciben_los_permisos_de_agenda_una_sola_vez(db):
    from sqlalchemy import delete, select

    from sulam.models import Ajuste, Rol, RolPermiso
    from sulam.seed import inicializar_catalogos

    tec = db.execute(select(Rol).where(Rol.nombre == "Técnico")).scalar_one()
    db.execute(delete(RolPermiso).where(RolPermiso.rol_id == tec.id, RolPermiso.modulo == "agenda"))
    db.execute(delete(Ajuste).where(Ajuste.clave == "permisos_iniciales_agenda"))
    db.commit()
    db.expire_all()
    inicializar_catalogos(db)
    db.commit()
    tec = db.execute(select(Rol).where(Rol.nombre == "Técnico")).scalar_one()
    assert {(p.accion, p.alcance) for p in tec.permisos if p.modulo == "agenda"} == {("consultar", "area"), ("crear", "area"), ("modificar", "propios")}
    # Si el administrador los quita, no se vuelven a poner.
    db.execute(delete(RolPermiso).where(RolPermiso.rol_id == tec.id, RolPermiso.modulo == "agenda"))
    db.commit()
    db.expire_all()
    inicializar_catalogos(db)
    db.commit()
    db.expire_all()
    assert not [p for p in db.execute(select(Rol).where(Rol.nombre == "Técnico")).scalar_one().permisos if p.modulo == "agenda"]

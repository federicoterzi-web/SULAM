"""Filtros por cualquier campo en las listas."""

from __future__ import annotations

import json
from datetime import date

from conftest import AREA_ADMISION, AREA_PROMOCION, crear_usuario, nueva_persona, nuevo_caso

RUTAS = {
    "casos": "/api/casos",
    "legajos": "/api/personas",
    "expedientes": "/api/expedientes",
    "ingresos": "/api/ingresos",
    "recursos": "/api/recursos",
    "contactos": "/api/contactos",
}


def _f(*filtros) -> str:
    return json.dumps([{"c": c, "o": o, "v": v} for c, o, v in filtros])


def _ejemplo(campo: dict, op: str):
    if op in ("vacio", "no_vacio"):
        return None
    t = campo["tipo"]
    if t == "texto":
        return "a"
    if t in ("opcion", "multiple"):
        return [o["valor"] for o in (campo["opciones"] or [{"valor": "x"}])[:2]] or ["x"]
    if t == "fecha":
        return {"desde": "2020-01-01", "hasta": "2030-12-31"}
    if t == "numero":
        return {"desde": 1, "hasta": 100}
    return True


def test_todos_los_campos_y_comparaciones_funcionan(admin):
    """Cada campo de cada lista, con cada comparación, arma una consulta válida."""
    nueva_persona(admin)
    for lista, ruta in RUTAS.items():
        campos = admin.get(f"/api/filtros/{lista}").json()
        assert campos, lista
        for c in campos:
            for op in c["operadores"]:
                f = json.dumps([{"c": c["clave"], "o": op, "v": _ejemplo(c, op)}])
                r = admin.get(ruta, params={"f": f, "con_total": True})
                assert r.status_code == 200, (lista, c["clave"], op, r.text)
                assert isinstance(r.json()["total"], int)
            if c["tipo"] == "si_no":
                r = admin.get(ruta, params={"f": json.dumps([{"c": c["clave"], "o": "es", "v": False}])})
                assert r.status_code == 200, (lista, c["clave"], r.text)


def test_filtros_de_casos(admin):
    areas = {a["nombre"]: a["id"] for a in admin.get("/api/catalogos").json()["areas"]}
    crear_usuario("tec", "Técnico", AREA_ADMISION)
    tec = {u["nombre_completo"]: u["id"] for u in admin.get("/api/catalogos").json()["usuarios_asignables"]}["Tec"]
    p1 = nueva_persona(admin, apellidos="MAYOR", numero_documento="1111111", fecha_nacimiento="1940-05-01", genero="F", departamento="Capital",
                       cobertura_salud=["pami"])
    p2 = nueva_persona(admin, apellidos="MENOR", nombres="Otro", numero_documento="2222222", fecha_nacimiento=f"{date.today().year - 62}-01-01",
                       genero="M", departamento="Lules")
    c1 = nuevo_caso(admin, p1["id"], area_id=areas[AREA_ADMISION], responsable_id=tec, indicadores=["maltrato.fisico"])
    c2 = nuevo_caso(admin, p2["id"], area_id=areas[AREA_PROMOCION], indicadores=["vulnerabilidad.habitacional"])

    def ids(*filtros):
        r = admin.get("/api/casos", params={"f": _f(*filtros), "con_total": True})
        assert r.status_code == 200, r.text
        d = r.json()
        assert d["total"] == len(d["items"])
        return {c["id"] for c in d["items"]}

    assert ids(("caso.indicadores", "alguno", ["maltrato"])) == {c1["id"]}
    assert ids(("caso.indicadores", "alguno", ["maltrato.fisico", "vulnerabilidad"])) == {c1["id"], c2["id"]}
    assert ids(("caso.indicadores", "ninguno", ["maltrato"])) == {c2["id"]}
    assert ids(("persona.edad", "entre", {"desde": 80})) == {c1["id"]}
    assert ids(("persona.edad", "entre", {"hasta": 70})) == {c2["id"]}
    assert ids(("persona.genero", "es", ["F"]), ("persona.departamento", "es", ["Capital"])) == {c1["id"]}
    assert ids(("persona.cobertura_salud", "alguno", ["pami"])) == {c1["id"]}
    assert ids(("caso.responsable", "es", [tec])) == {c1["id"]}
    assert ids(("caso.responsable", "vacio", None)) == {c2["id"]}
    assert ids(("caso.area", "no_es", [str(areas[AREA_ADMISION])])) == {c2["id"]}
    assert ids(("caso.estado", "es", ["abierto"])) == {c1["id"], c2["id"]}
    assert ids(("demanda.tipo_vivienda", "vacio", None)) == {c1["id"], c2["id"]}

    # Legajos: por algo de sus casos.
    r = admin.get("/api/personas", params={"f": _f(("legajo.indicadores", "alguno", ["maltrato"]))}).json()
    assert [p["id"] for p in r] == [p1["id"]]


def test_filtros_invalidos_y_permisos(admin, cliente):
    assert admin.get("/api/casos", params={"f": "no es json"}).status_code == 400
    assert admin.get("/api/casos", params={"f": _f(("no.existe", "es", ["x"]))}).status_code == 400
    assert admin.get("/api/casos", params={"f": _f(("caso.estado", "contiene", "x"))}).status_code == 400
    assert admin.get("/api/casos", params={"f": _f(("persona.edad", "entre", {}))}).status_code == 400
    assert admin.get("/api/filtros/inexistente").status_code == 404
    crear_usuario("mesa", "Mesa de Entrada")
    assert cliente("mesa").get("/api/filtros/ingresos").status_code == 200
    assert cliente("mesa").get("/api/filtros/casos").status_code == 403

"""Importación de personal desde un archivo local (con datos inventados)."""

from __future__ import annotations

import json

import pytest
from conftest import AREA_ADMISION, PASSWORD

from sulam.models import Agente, Usuario
from sulam.personal_importar import ErrorImportacion, importar, usuario_sugerido
from sulam.security import validar_password_nueva

SEMANA = {str(d): ["08:00", "13:00"] for d in range(5)}


def _archivo(tmp_path, agentes):
    ruta = tmp_path / "personal.json"
    ruta.write_text(json.dumps({"agentes": agentes}), encoding="utf-8")
    return ruta


def test_nombres_de_usuario():
    assert usuario_sugerido("Quispe Lucía") == "quispe.lucia"
    assert usuario_sugerido("Ñandú Ibarra María Eugenia") == "nandu.eugenia"
    assert usuario_sugerido("Solo") == "solo"


def test_importa_fichas_y_cuentas_sin_repetir(db, tmp_path):
    filas = [
        {"nombre": "Quispe Lucía", "area": AREA_ADMISION, "rol": "Técnico", "id_reloj": "9001", "boleta": "11", "desde": "2026-10-05", "horario": SEMANA},
        {"nombre": "Quispe Luis", "area": AREA_ADMISION, "id_reloj": "9002", "desde": "2026-10-05", "horario": SEMANA},
        {"nombre": "Sin Reloj Pedro", "area": AREA_ADMISION},
    ]
    r = importar(db, _archivo(tmp_path, filas), crear_usuarios=True)
    db.commit()
    assert (r["fichas"], r["cuentas"]) == (3, 3)
    logins = [c[0] for c in r["credenciales"]]
    assert logins == ["quispe.lucia", "quispe.luis", "sin.pedro"]
    for _, _, _, clave in r["credenciales"]:
        assert validar_password_nueva(clave) is None
    u = db.query(Usuario).filter_by(usuario="quispe.lucia").one()
    assert u.debe_cambiar_password and [x.nombre for x in u.roles] == ["Técnico"]
    a = db.query(Agente).filter_by(id_reloj="9001").one()
    assert a.usuario_id == u.id and a.area_id == u.area_id and a.boleta == "11"

    # Segunda corrida: no duplica nada.
    r2 = importar(db, _archivo(tmp_path, filas[:2]), crear_usuarios=True)
    assert r2["fichas"] == 0 and len(r2["omitidos"]) == 2


def test_sin_cuentas_y_con_errores(db, tmp_path):
    r = importar(db, _archivo(tmp_path, [{"nombre": "Solo Ficha", "id_reloj": "9100", "desde": "2026-10-05", "horario": SEMANA}]), crear_usuarios=False)
    assert (r["fichas"], r["cuentas"]) == (1, 0)
    with pytest.raises(ErrorImportacion):
        importar(db, _archivo(tmp_path, [{"nombre": "X", "area": "Área que no existe"}]), crear_usuarios=False)
    with pytest.raises(ErrorImportacion):
        importar(db, _archivo(tmp_path, [{"nombre": "Y", "rol": "Rol inventado"}]), crear_usuarios=True)
    with pytest.raises(ErrorImportacion):
        importar(db, tmp_path / "no-existe.json", crear_usuarios=False)


def test_cuenta_importada_puede_ingresar(db, tmp_path, cliente):
    r = importar(db, _archivo(tmp_path, [{"nombre": "Vega Ana", "area": AREA_ADMISION}]), crear_usuarios=True, password_comun=PASSWORD)
    db.commit()
    assert r["credenciales"][0][3] == PASSWORD
    yo = cliente("vega.ana").yo
    assert yo["debe_cambiar_password"] is True

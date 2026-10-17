"""Reglas fijas de asistencia: mismos casos que la app «Asistencia DAM» (datos inventados)."""

from __future__ import annotations

import copy

import pytest

from sulam.asistencia import informe, leer_reloj


def base(entrada="08:00:00", salida="13:00:00"):
    return {
        "agentes": [{"id": 1, "nombre": "Prueba Ana", "id_reloj": "900", "boleta": "1", "periodos": [{"desde": "2026-01-01", "hasta": None}],
                     "horarios": [{"vigente_desde": "2026-10-05", "vigente_hasta": None, "confirmado": False,
                                   "semana": {"0": ["08:00", "13:00"], "1": ["08:00", "13:00"], "2": ["08:00", "13:00"]}}]}],
        "marcaciones": [{"agente_id": 1, "dia": "2026-10-05", "entrada": entrada, "salida": salida, "importacion_id": 1}],
        "justificativos": [], "importaciones": [], "revisiones": [],
    }


def fila(d):
    return informe(d, "2026-10-05", "2026-10-05")[0]


def documento(d, **campos):
    j = {"id": len(d["justificativos"]) + 1, "agente_id": 1, "codigo": "CT", "estado": "aprobado", "desde": "2026-10-05",
         "hasta": "2026-10-05", "hora_desde": None, "hora_hasta": None, "excepcion_desde": None, "excepcion_hasta": None,
         "requiere_horario": False}
    j.update(campos)
    d["justificativos"].append(j)
    return j


@pytest.mark.parametrize("entrada,salida,esperado", [
    ("08:00:00", "13:00:00", []),
    ("07:30:00", "13:30:00", []),
    ("07:29:59", "13:00:00", ["ENTRADA_FUERA_VENTANA"]),
    ("08:00:00", "13:30:01", []),
    ("08:00:00", "13:30:59", []),
    ("08:00:00", "13:31:00", ["SALIDA_FUERA_VENTANA"]),
    ("08:01:00", "13:01:00", []),
    ("08:10:00", "13:10:00", []),
    ("08:00:01", "13:00:01", []),
    ("08:00:01", "13:00:00", []),
    ("08:01:00", "13:00:59", ["TARDANZA_SIN_RECUPERAR"]),
    ("08:10:00", "13:09:59", ["TARDANZA_SIN_RECUPERAR"]),
    ("08:10:01", "13:30:00", []),
    ("08:10:59", "13:10:00", []),
    ("08:11:00", "13:11:00", ["TARDANZA"]),
    ("07:50:00", "12:59:59", ["SALIDA_ANTICIPADA"]),
    ("08:05:00", "12:59:00", ["TARDANZA_SIN_RECUPERAR", "SALIDA_ANTICIPADA"]),
    (None, "13:00:00", ["MARCACION_INCOMPLETA"]),
    ("08:00:00", None, ["MARCACION_INCOMPLETA"]),
    (None, None, ["SIN_MARCACIONES_REVISAR"]),
    ("13:30:00", "18:30:00", ["MARCACIONES_FUERA_DEL_TURNO"]),
    ("13:00:00", "08:00:00", ["ORDEN_HORARIO_INVALIDO"]),
])
def test_criterios_fijos(entrada, salida, esperado):
    r = fila(base(entrada, salida))
    assert r["incidencias"] == esperado
    assert r["requiere_revision"] == bool(esperado)
    assert r["estado"] == ("pendiente" if esperado else "auto_aprobado")
    assert "HORARIO_POR_CONFIRMAR" in r["avisos"]


def test_sin_archivos_no_se_presume_falta():
    d = base()
    d["marcaciones"] = []
    assert fila(d)["estado"] == "sin_datos"
    d["importaciones"].append({"id": 1, "incorporada": True, "desde": "2026-10-05", "hasta": "2026-10-09"})
    assert fila(d)["requiere_revision"]
    documento(d)
    assert fila(d)["estado"] == "justificado"


def test_varios_dias_y_rechazo():
    d = base(None, None)
    for dia in ("2026-10-06", "2026-10-07"):
        d["marcaciones"].append({**d["marcaciones"][0], "dia": dia})
    j = documento(d, hasta="2026-10-06")
    assert [r["estado"] for r in informe(d, "2026-10-05", "2026-10-07")] == ["justificado", "justificado", "pendiente"]
    j["estado"] = "rechazado"
    assert fila(d)["requiere_revision"]


def test_tramos_parciales_y_union():
    d = base("08:10:00", "12:55:00")
    documento(d, hora_desde="08:00", hora_hasta="08:10")
    r = fila(d)
    assert r["incidencias"] == ["SALIDA_ANTICIPADA"] and r["incidencias_justificadas"] == ["TARDANZA_SIN_RECUPERAR"]
    documento(d, hora_desde="12:55", hora_hasta="13:00")
    assert fila(d)["estado"] == "justificado"
    falta = base(None, "13:00:00")
    documento(falta, hora_desde="08:00", hora_hasta="10:00")
    assert fila(falta)["requiere_revision"]
    j = documento(falta, hora_desde="10:00", hora_hasta="13:00")
    assert fila(falta)["estado"] == "justificado"
    j["hora_desde"] = "10:01"
    assert fila(falta)["requiere_revision"]


def test_cambio_recalcula_y_no_oculta_conflictos():
    d = base("09:00:00", "14:00:00")
    documento(d, codigo="CAMBIO", excepcion_desde="09:00", excepcion_hasta="14:00")
    assert fila(d)["estado"] == "auto_aprobado"
    d["marcaciones"][0]["entrada"] = None
    assert fila(d)["requiere_revision"]
    d["marcaciones"].append({**d["marcaciones"][0], "entrada": "09:00:00"})
    documento(d)
    assert "MARCACIONES_CONFLICTIVAS" in fila(d)["incidencias"]


def test_documento_pendiente_o_ajeno_no_cubre():
    d = base(None, None)
    j = documento(d)
    assert fila(d)["estado"] == "justificado"
    j["estado"] = "pendiente"
    assert fila(d)["requiere_revision"]
    j["estado"] = "aprobado"
    j["agente_id"] = 999
    assert fila(d)["requiere_revision"]


def test_fuera_del_periodo_de_alta():
    d = base()
    d["agentes"][0]["periodos"] = [{"desde": "2026-01-01", "hasta": "2026-10-04"}]
    assert "FUERA_PERIODO_LABORAL" in fila(d)["incidencias"]
    d["marcaciones"] = []
    assert informe(d, "2026-10-05", "2026-10-05") == []


def test_huella_cambia_con_la_evidencia():
    a, b = base(), base()
    b["marcaciones"][0]["salida"] = "13:05:00"
    assert fila(a)["huella"] != fila(b)["huella"] and fila(a)["huella"] == fila(copy.deepcopy(a))["huella"]


RELOJ = """<html><body><table>
<tr><td>2026-10-05 00:00:00 - 2026-10-09 23:59:59</td></tr>
<tr><th>ID de Persona</th><th>Nombre</th><th>Departamento</th><th>Fecha</th><th>Primera Entrada</th><th>Última Salida</th></tr>
<tr><td>900</td><td>Prueba Ana María</td><td>X</td><td>2026-10-05</td><td>08:02:10</td><td>13:04:00</td></tr>
<tr><td>901</td><td>Ficticio Juan</td><td>X</td><td>2026-10-05</td><td>-</td><td>13:00</td></tr>
<tr><td>902</td><td>Mal Fecha</td><td>X</td><td>2026-13-40</td><td>08:00</td><td>13:00</td></tr>
</table></body></html>"""


def test_lectura_del_reloj():
    r = leer_reloj(RELOJ)
    assert (r["desde"], r["hasta"]) == ("2026-10-05", "2026-10-09")
    assert [(x["id_reloj"], x["entrada"], x["salida"]) for x in r["registros"]] == [("900", "08:02:10", "13:04:00"), ("901", None, "13:00:00")]
    assert len(r["errores"]) == 1

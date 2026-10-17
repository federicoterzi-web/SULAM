"""Motor de asistencias: lectura del reloj y cálculo de incidencias.

Portado de la app «Asistencia DAM» (Google Apps Script, `DamCore`) sin cambiar las
reglas fijas confirmadas por la Dirección:

- Se ignoran los segundos (sin redondear): 08:10:59 se evalúa como 08:10.
- Entrada hasta 30 min antes y salida hasta 30 min después: no son incidencia.
- Atraso de hasta 10 min: se aprueba si se recupera a la salida el mismo día.
- Atraso de más de 10 min: revisión aunque se recupere.
- Marcas faltantes, salida anticipada, marcas fuera de la ventana: revisión.
- Los días sin archivos importados no se convierten en ausencias.
- Los justificativos aprobados cubren días (o tramos) y cierran sólo las
  incidencias contenidas íntegramente en su cobertura. CAMBIO reemplaza el turno.

Las funciones trabajan con estructuras simples (dicts) para poder probarse sin base.
"""

from __future__ import annotations

import hashlib
import html as htmlmod
import json
import re
import unicodedata
from datetime import date, timedelta

CODIGOS = ["CT", "CE", "CS", "VAO", "DF", "C3", "SESOP", "LICENCIA", "CAMBIO"]
BLOQUEANTES = {
    "IDENTIDAD_PENDIENTE", "SIN_VIGENCIA_HORARIA", "HORARIO_POR_CONFIRMAR", "CAMBIOS_SUPERPUESTOS",
    "JUSTIFICATIVO_PENDIENTE", "MARCACIONES_CONFLICTIVAS", "SIN_MARCACIONES_REVISAR", "MARCACION_INCOMPLETA",
    "ORDEN_HORARIO_INVALIDO", "MARCACION_SIN_TURNO", "MARCACIONES_FUERA_DEL_TURNO", "FILA_AUSENTE_EN_REPORTE",
    "SIN_DATOS_IMPORTADOS",
}
CRITERIOS = {
    "tolerancia_minutos": 10, "recuperacion": "mismo_dia", "ventana_entrada_minutos": 30,
    "ventana_salida_minutos": 30, "ignora_segundos": True, "version": 2,
}

# Textos para la pantalla.
INCIDENCIAS = {
    "TARDANZA": "Llegada tarde (más de 10 min)",
    "TARDANZA_SIN_RECUPERAR": "Llegada tarde sin recuperar",
    "SALIDA_ANTICIPADA": "Salida anticipada",
    "ENTRADA_FUERA_VENTANA": "Entrada más de 30 min antes",
    "SALIDA_FUERA_VENTANA": "Salida más de 30 min después",
    "MARCACION_INCOMPLETA": "Falta la entrada o la salida",
    "SIN_MARCACIONES_REVISAR": "Sin marcas en el reloj",
    "FILA_AUSENTE_EN_REPORTE": "No figura en el reloj ese día",
    "SIN_DATOS_IMPORTADOS": "Semana sin importar",
    "MARCACIONES_FUERA_DEL_TURNO": "Marcas fuera de su turno",
    "MARCACION_SIN_TURNO": "Marcó un día sin turno",
    "ORDEN_HORARIO_INVALIDO": "Salida anterior a la entrada",
    "MARCACIONES_CONFLICTIVAS": "Marcas repetidas distintas",
    "IDENTIDAD_PENDIENTE": "Falta el ID del reloj",
    "SIN_VIGENCIA_HORARIA": "Sin horario cargado",
    "CAMBIOS_SUPERPUESTOS": "Cambios de horario superpuestos",
    "CAMBIO_SIN_HORARIO": "Cambio de horario sin completar",
    "FUERA_PERIODO_LABORAL": "Fuera de su período de alta",
    "HORARIO_POR_CONFIRMAR": "Horario por confirmar",
    "REVISION_DESACTUALIZADA": "La revisión anterior quedó desactualizada",
}


class ErrorAsistencia(ValueError):
    pass


def _seg(valor: str) -> int:
    partes = [int(x) for x in valor.split(":")]
    return partes[0] * 3600 + partes[1] * 60


def _redondeo(x: float) -> float:
    return round(x + 1e-12, 2)


def hora(valor: str | None) -> str:
    if not isinstance(valor, str) or not re.fullmatch(r"(?:[01]\d|2[0-3]):[0-5]\d", valor):
        raise ErrorAsistencia("Hora inválida: usá HH:MM.")
    return valor


def tramo(desde: str | None, hasta: str | None, requerido: bool) -> tuple[str | None, str | None]:
    if not requerido and not desde and not hasta:
        return None, None
    hora(desde)
    hora(hasta)
    if desde >= hasta:
        raise ErrorAsistencia("El tramo debe terminar después de comenzar, en el mismo día.")
    return desde, hasta


def validar_semana(semana: dict) -> dict:
    if not isinstance(semana, dict):
        raise ErrorAsistencia("Horario inválido.")
    salida = {}
    for k, v in semana.items():
        if not re.fullmatch(r"[0-6]", str(k)) or not isinstance(v, (list, tuple)) or len(v) != 2:
            raise ErrorAsistencia("Revisá los días y tramos del horario.")
        tramo(v[0], v[1], True)
        salida[str(k)] = [v[0], v[1]]
    return salida


def _normalizado(valor: str) -> str:
    t = unicodedata.normalize("NFD", str(valor).lower())
    return "".join(c for c in t if not unicodedata.combining(c))


# ---------------------------------------------------------------- reloj


def leer_reloj(contenido: str) -> dict:
    """Lee el «.xls» del reloj (en realidad, una tabla HTML)."""
    if len(contenido) > 8 * 1024 * 1024:
        raise ErrorAsistencia("El archivo supera los 8 MB.")
    cabecera = None
    registros, errores = [], []
    for indice, fragmento in enumerate(re.split(r"</tr\s*>", contenido, flags=re.I)):
        if len(fragmento) > 200000:
            raise ErrorAsistencia("La estructura del HTML no es la del reloj.")
        celdas = [
            re.sub(r"\s+", " ", htmlmod.unescape(re.sub(r"<[^>]*>", "", m))).strip()
            for m in re.findall(r"<t[dh]\b[^>]*>([\s\S]*?)</t[dh]\s*>", fragmento, flags=re.I)
        ]
        bajas = [_normalizado(c) for c in celdas]
        if "id de persona" in bajas and "primera entrada" in bajas:
            if not all(k in bajas for k in ("id de persona", "nombre", "fecha", "primera entrada", "ultima salida")):
                raise ErrorAsistencia("Cabecera incompleta del reloj.")
            cabecera = bajas
            continue
        if not cabecera or len(celdas) != len(cabecera):
            if cabecera and celdas and celdas[0].isdigit():
                errores.append(f"Fila HTML {indice + 1}: cantidad de columnas inesperada.")
            continue
        fila = dict(zip(cabecera, celdas))
        if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", fila.get("fecha", "")):
            if (fila.get("id de persona") or "").isdigit():
                errores.append(f"Fila HTML {indice + 1}: fecha inválida.")
            continue
        try:
            date.fromisoformat(fila["fecha"])
            if not fila["id de persona"] or not fila["nombre"]:
                raise ErrorAsistencia("ID o nombre vacíos.")
            marcas = []
            for k in ("primera entrada", "ultima salida"):
                v = fila[k].strip()
                if v in ("", "-", "--", "---"):
                    marcas.append(None)
                    continue
                if not re.fullmatch(r"(?:[01]\d|2[0-3]):[0-5]\d(?::[0-5]\d)?", v):
                    raise ErrorAsistencia(f"{k}: hora no reconocida.")
                marcas.append(v if len(v) == 8 else v + ":00")
            registros.append(
                {"fila": indice + 1, "id_reloj": fila["id de persona"], "nombre": fila["nombre"], "dia": fila["fecha"],
                 "entrada": marcas[0], "salida": marcas[1], "crudo": fila}
            )
        except (ValueError, ErrorAsistencia) as e:
            errores.append(f"Fila HTML {indice + 1}: {e}")
    if not cabecera or not registros:
        raise ErrorAsistencia("No se reconoció la tabla HTML del reloj.")
    declarado = re.search(r"(\d{4}-\d{2}-\d{2}) 00:00:00\s*-\s*(\d{4}-\d{2}-\d{2}) 23:59:59", contenido)
    dias = sorted(r["dia"] for r in registros)
    inicio, fin = (declarado.group(1), declarado.group(2)) if declarado else (dias[0], dias[-1])
    if inicio > fin:
        raise ErrorAsistencia("Período inválido en el archivo.")
    if any(r["dia"] < inicio or r["dia"] > fin for r in registros):
        errores.append("Hay fechas fuera del período declarado.")
    avisos = ["El reloj exporta solamente primera entrada y última salida: no acredita permanencia continua ni pausas."]
    if len({(r["id_reloj"], r["dia"]) for r in registros}) != len(registros):
        avisos.append("Hay filas repetidas por persona y fecha; se revisarán los conflictos.")
    return {"desde": inicio, "hasta": fin, "registros": registros, "errores": errores, "avisos": avisos}


def coincide_nombre(nombre_base: str, nombre_reloj: str) -> bool:
    original = _normalizado(nombre_reloj).split()
    return all(p in original for p in _normalizado(nombre_base).split())


# ---------------------------------------------------------------- cálculo


def _cubre(intervalos: list[tuple[int, int]], inicio: int, fin: int) -> bool:
    cursor = inicio
    for a, b in sorted(intervalos):
        if a > cursor:
            break
        cursor = max(cursor, b)
        if cursor >= fin:
            return True
    return False


def _canonico(v):
    if isinstance(v, list):
        return [_canonico(x) for x in v]
    if isinstance(v, dict):
        return {k: _canonico(v[k]) for k in sorted(v)}
    return v


def huella(valor) -> str:
    return hashlib.sha256(json.dumps(_canonico(valor), ensure_ascii=False, separators=(",", ":")).encode()).hexdigest()


def en_periodo(periodos: list[dict], dia: str) -> bool:
    periodos = periodos or [{"desde": None, "hasta": None}]
    return any((not p.get("desde") or p["desde"] <= dia) and (not p.get("hasta") or p["hasta"] >= dia) for p in periodos)


def informe(datos: dict, desde: str, hasta: str, agente_id: int | None = None) -> list[dict]:
    """Jornadas con sus incidencias.

    datos = {
      "agentes": [{"id", "nombre", "id_reloj", "boleta", "periodos", "horarios": [{"vigente_desde", "vigente_hasta", "semana", "confirmado"}]}],
      "marcaciones": [{"agente_id", "dia", "entrada", "salida", "importacion_id"}],
      "justificativos": [{"id", "agente_id", "codigo", "estado", "desde", "hasta", "hora_desde", "hora_hasta", "excepcion_desde", "excepcion_hasta", "requiere_horario"}],
      "importaciones": [{"id", "desde", "hasta", "incorporada"}],
      "revisiones": [{"id", "agente_id", "dia", "huella", "decision", ...}],
    }  (fechas como «AAAA-MM-DD»)
    """
    d0, d1 = date.fromisoformat(desde), date.fromisoformat(hasta)
    if d0 > d1 or (d1 - d0).days > 366:
        raise ErrorAsistencia("Revisá el período; máximo 367 días.")
    por_dia: dict = {}
    for m in datos["marcaciones"]:
        por_dia.setdefault((m["agente_id"], m["dia"]), []).append(m)
    just_por: dict = {}
    for j in datos["justificativos"]:
        just_por.setdefault(j["agente_id"], []).append(j)
    importadas = [i for i in datos["importaciones"] if i["incorporada"]]
    revisiones_por: dict = {}
    for r in sorted(datos["revisiones"], key=lambda x: x["id"]):
        revisiones_por[(r["agente_id"], r["dia"])] = r
    salida = []
    agentes = [a for a in datos["agentes"] if agente_id is None or a["id"] == agente_id]
    for persona in sorted(agentes, key=lambda a: _normalizado(a["nombre"])):
        horarios = sorted(persona.get("horarios", []), key=lambda h: h["vigente_desde"], reverse=True)
        dia = d0
        while dia <= d1:
            texto = dia.isoformat()
            dia_semana = dia.weekday()  # 0 = lunes
            dia += timedelta(days=1)
            horario = next(
                (h for h in horarios if h["vigente_desde"] <= texto and (not h.get("vigente_hasta") or h["vigente_hasta"] >= texto)),
                None,
            )
            turno = horario["semana"].get(str(dia_semana)) if horario else None
            marcas = por_dia.get((persona["id"], texto), [])
            justs = [j for j in just_por.get(persona["id"], []) if j["desde"] <= texto <= j["hasta"]]
            empleado = en_periodo(persona.get("periodos"), texto)
            if not empleado and not marcas and not justs:
                continue
            cambios = [j for j in justs if j["codigo"] == "CAMBIO" and j["estado"] == "aprobado" and j.get("excepcion_desde") and j.get("excepcion_hasta")]
            if len(cambios) == 1:
                turno = [cambios[0]["excepcion_desde"], cambios[0]["excepcion_hasta"]]
            if not turno and not marcas and not justs and dia_semana >= 5:
                continue
            flags, avisos = [], []
            if not empleado:
                flags.append("FUERA_PERIODO_LABORAL")
            if any(j["codigo"] == "CAMBIO" and j.get("requiere_horario") and j["estado"] == "pendiente" for j in justs):
                flags.append("CAMBIO_SIN_HORARIO")
            if not persona.get("id_reloj"):
                flags.append("IDENTIDAD_PENDIENTE")
            if not horario:
                flags.append("SIN_VIGENCIA_HORARIA")
            elif not horario.get("confirmado"):
                avisos.append("HORARIO_POR_CONFIRMAR")
            if len(cambios) > 1:
                flags.append("CAMBIOS_SUPERPUESTOS")
            distintas = {(m["entrada"], m["salida"]) for m in marcas}
            if len(distintas) > 1:
                flags.append("MARCACIONES_CONFLICTIVAS")
            marca = marcas[0] if len(distintas) == 1 else None
            entrada = marca["entrada"] if marca else None
            salida_m = marca["salida"] if marca else None
            tarde = temprano = recuperado = deficit = 0.0
            hay_semana = any(i["desde"] <= texto <= i["hasta"] for i in importadas)
            if not marcas:
                flags.append("FILA_AUSENTE_EN_REPORTE" if hay_semana else "SIN_DATOS_IMPORTADOS")
            elif not entrada and not salida_m and len(distintas) == 1:
                flags.append("SIN_MARCACIONES_REVISAR")
            elif not entrada or not salida_m:
                flags.append("MARCACION_INCOMPLETA")
            elif _seg(salida_m) <= _seg(entrada):
                flags.append("ORDEN_HORARIO_INVALIDO")
            elif not turno:
                flags.append("MARCACION_SIN_TURNO")
            elif _seg(entrada) >= _seg(turno[1]) or _seg(salida_m) <= _seg(turno[0]):
                flags.append("MARCACIONES_FUERA_DEL_TURNO")
            else:
                tarde_s = max(0, _seg(entrada) - _seg(turno[0]))
                extra_s = max(0, _seg(salida_m) - _seg(turno[1]))
                tarde = _redondeo(tarde_s / 60)
                temprano = _redondeo(max(0, _seg(turno[1]) - _seg(salida_m)) / 60)
                if tarde_s > 600:
                    flags.append("TARDANZA")
                elif tarde_s > extra_s:
                    flags.append("TARDANZA_SIN_RECUPERAR")
                if temprano:
                    flags.append("SALIDA_ANTICIPADA")
                if _seg(entrada) < _seg(turno[0]) - 1800:
                    flags.append("ENTRADA_FUERA_VENTANA")
                if extra_s > 1800:
                    flags.append("SALIDA_FUERA_VENTANA")
                recuperado = _redondeo(min(tarde_s, extra_s) / 60)
                deficit = _redondeo(max(0, tarde + temprano - recuperado))
            originales = list(flags)
            documentos = [j for j in justs if j["estado"] == "aprobado" and j["codigo"] != "CAMBIO"]
            intervalos = [(_seg(j["hora_desde"]), _seg(j["hora_hasta"])) if j.get("hora_desde") else (0, 86400) for j in documentos]
            t0 = _seg(turno[0]) if turno else None
            t1 = _seg(turno[1]) if turno else None
            e = _seg(entrada) if entrada else None
            s_ = _seg(salida_m) if salida_m else None
            cobertura = {
                "TARDANZA": (t0, e) if e is not None and turno else None,
                "TARDANZA_SIN_RECUPERAR": (t0, e) if e is not None and turno else None,
                "SALIDA_ANTICIPADA": (s_, t1) if s_ is not None and turno else None,
                "ENTRADA_FUERA_VENTANA": (e, t0 - 1800) if e is not None and turno else None,
                "SALIDA_FUERA_VENTANA": (t1 + 1800, s_) if s_ is not None and turno else None,
                "MARCACION_INCOMPLETA": (t0, t1) if turno else None,
                "SIN_MARCACIONES_REVISAR": (t0, t1) if turno else None,
                "FILA_AUSENTE_EN_REPORTE": (t0, t1) if turno else None,
                "MARCACIONES_FUERA_DEL_TURNO": (min(t0, e), max(t1, s_)) if turno and e is not None and s_ is not None else None,
            }
            justificadas = [f for f in flags if cobertura.get(f) and _cubre(intervalos, *cobertura[f])]
            restantes = [f for f in flags if f not in justificadas]
            evaluada = bool(entrada and salida_m and turno and _seg(salida_m) > _seg(entrada) and _seg(entrada) < _seg(turno[1]) and _seg(salida_m) > _seg(turno[0]) and len(distintas) == 1)
            fila = {
                "agente_id": persona["id"], "nombre": persona["nombre"], "dia": texto,
                "turno_desde": turno[0] if turno else None, "turno_hasta": turno[1] if turno else None,
                "entrada": entrada, "salida": salida_m, "minutos_tarde": tarde, "minutos_salida_anticipada": temprano,
                "minutos_recuperados": recuperado, "minutos_diferencia": deficit,
                "incidencias": restantes, "avisos": avisos, "incidencias_originales": originales,
                "incidencias_justificadas": justificadas,
                "justificativos": [{"id": j["id"], "codigo": j["codigo"], "estado": j["estado"]} for j in justs],
                "evaluada": evaluada,
            }
            evidencia = {
                "resultado": {k: v for k, v in fila.items()}, "criterios": CRITERIOS,
                "horario": {k: horario[k] for k in ("vigente_desde", "semana", "confirmado")} if horario else None,
                "marcas": [{"dia": m["dia"], "entrada": m["entrada"], "salida": m["salida"]} for m in marcas],
                "identidad": [persona.get("id_reloj"), persona.get("boleta")],
            }
            fila["huella"] = huella(evidencia)
            previa = revisiones_por.get((persona["id"], texto))
            fila["revision"] = previa if previa and previa["huella"] == fila["huella"] else None
            fila["revision_id"] = previa["id"] if previa else None
            hay_datos = bool(marcas) or hay_semana
            estado = (
                "sin_datos" if not hay_datos and not justificadas
                else "pendiente" if restantes
                else "justificado" if justificadas
                else "auto_aprobado"
            )
            if estado == "pendiente" and fila["revision"] and fila["revision"]["decision"] != "pendiente":
                estado = "revisado"
            fila["estado"] = estado
            fila["requiere_revision"] = estado == "pendiente"
            if previa and not fila["revision"] and fila["requiere_revision"]:
                fila["avisos"].append("REVISION_DESACTUALIZADA")
            if estado in ("auto_aprobado", "justificado"):
                fila["revision"] = {
                    "decision": "sin_descuento", "minutos": 0, "usuario": "Evaluación automática", "automatica": True,
                    "fundamento": "Incidencias cubiertas por los justificativos registrados." if estado == "justificado" else "Cumple los criterios fijos de asistencia.",
                }
            salida.append(fila)
    return salida


def validar_revision(fila: dict | None, decision: str, minutos: int, fundamento: str, huella_vista: str, revision_vista: int | None) -> None:
    if decision not in ("sin_descuento", "pendiente", "proponer_descuento"):
        raise ErrorAsistencia("Decisión no reconocida.")
    if not fundamento or len(fundamento.strip()) < 5:
        raise ErrorAsistencia("Escribí el fundamento (al menos 5 caracteres).")
    if not isinstance(minutos, int) or minutos < 0 or minutos > 1440:
        raise ErrorAsistencia("Minutos fuera de rango.")
    if fila is None or fila["huella"] != huella_vista:
        raise ErrorAsistencia("Las evidencias cambiaron. Actualizá el informe y revisá nuevamente.")
    if revision_vista != fila["revision_id"]:
        raise ErrorAsistencia("Otra persona revisó la jornada. Actualizá antes de registrar una nueva decisión.")
    if decision == "proponer_descuento":
        if any(f in BLOQUEANTES or f in ("FUERA_PERIODO_LABORAL", "CAMBIO_SIN_HORARIO") for f in fila["incidencias"]) or "HORARIO_POR_CONFIRMAR" in fila["avisos"]:
            raise ErrorAsistencia("Faltan evidencias o confirmaciones antes de proponer minutos.")
        if not fila["requiere_revision"] and fila["estado"] != "revisado":
            raise ErrorAsistencia("La jornada no tiene incidencias pendientes para proponer minutos.")
        import math

        if minutos <= 0 or minutos > math.ceil(fila["minutos_diferencia"]):
            raise ErrorAsistencia("Los minutos propuestos superan la diferencia técnica.")
    elif minutos != 0:
        raise ErrorAsistencia("Sólo una propuesta puede contener minutos.")

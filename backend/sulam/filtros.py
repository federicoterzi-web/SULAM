"""Filtros por cualquier campo, comunes a las listas y a las estadísticas.

Cada lista (casos, legajos, expedientes, Mesa de Entrada, recursos, contactos)
declara sus campos: etiqueta, grupo, tipo y cómo se traduce cada operador a una
condición SQL. La pantalla pide el catálogo (GET /filtros/{lista}) y manda los
filtros como JSON en el parámetro ``f``: ``[{"c": campo, "o": operador, "v": valor}]``.

Tipos y operadores:
- texto:    contiene · no_contiene · vacio · no_vacio
- opcion:   es · no_es · vacio · no_vacio          (valor: lista de códigos)
- multiple: alguno · todos · ninguno · vacio · no_vacio  (listas JSONB)
- fecha:    entre · vacio · no_vacio               (valor: {desde, hasta})
- numero:   entre · vacio · no_vacio               (valor: {desde, hasta})
- si_no:    es                                      (valor: true / false)
"""
from __future__ import annotations

import json
import uuid
from dataclasses import dataclass, field
from datetime import date, datetime, time, timedelta
from typing import Any, Callable

from fastapi import HTTPException, status
from sqlalchemy import and_, exists, false, func, not_, or_, select, true
from sqlalchemy.orm import Session, aliased

from . import formularios as F
from .models import (
    Area,
    Articulacion,
    Caso,
    CasoAsignacion,
    CasoEvolucion,
    Constancia,
    Contacto,
    Expediente,
    Ingreso,
    Persona,
    Recurso,
    RegistroDemanda,
    Reiteracion,
    TipoDocumental,
    UbicacionFisica,
    Usuario,
)
from .textutil import escapar_like

OPERADORES = {
    "texto": ["contiene", "no_contiene", "vacio", "no_vacio"],
    "opcion": ["es", "no_es", "vacio", "no_vacio"],
    "multiple": ["alguno", "todos", "ninguno", "vacio", "no_vacio"],
    "fecha": ["entre", "vacio", "no_vacio"],
    "numero": ["entre", "vacio", "no_vacio"],
    "si_no": ["es"],
}
MAX_FILTROS = 30

Condicion = Callable[[str, Any], Any]
Opciones = list[dict] | Callable[[Session], list[dict]] | None


@dataclass
class Campo:
    clave: str
    etiqueta: str
    grupo: str
    tipo: str
    condicion: Condicion
    opciones: Opciones = None
    operadores: list[str] = field(default_factory=list)

    def ops(self) -> list[str]:
        return self.operadores or OPERADORES[self.tipo]


class FiltroInvalido(HTTPException):
    def __init__(self, texto: str):
        super().__init__(status.HTTP_400_BAD_REQUEST, f"Filtro inválido: {texto}")


# ---------------------------------------------------------------- valores


def _lista(v: Any) -> list[str]:
    if isinstance(v, (str, int)):
        v = [v]
    if not isinstance(v, list) or not v or len(v) > 200:
        raise FiltroInvalido("elegí al menos una opción.")
    return [str(x) for x in v]


def _texto(v: Any) -> str:
    if not isinstance(v, str) or not v.strip() or len(v) > 200:
        raise FiltroInvalido("escribí el texto a buscar.")
    return "%" + escapar_like(v.strip()) + "%"


def _rango_fechas(v: Any) -> tuple[date | None, date | None]:
    if not isinstance(v, dict):
        raise FiltroInvalido("indicá las fechas.")
    try:
        d = date.fromisoformat(v["desde"]) if v.get("desde") else None
        h = date.fromisoformat(v["hasta"]) if v.get("hasta") else None
    except (TypeError, ValueError):
        raise FiltroInvalido("fecha mal escrita.") from None
    if d is None and h is None:
        raise FiltroInvalido("indicá al menos una de las dos fechas.")
    if d and h and h < d:
        raise FiltroInvalido("la fecha «hasta» es anterior a «desde».")
    return d, h


def _rango_numeros(v: Any) -> tuple[float | None, float | None]:
    if not isinstance(v, dict):
        raise FiltroInvalido("indicá los valores.")
    try:
        d = float(v["desde"]) if v.get("desde") not in (None, "") else None
        h = float(v["hasta"]) if v.get("hasta") not in (None, "") else None
    except (TypeError, ValueError):
        raise FiltroInvalido("número mal escrito.") from None
    if d is None and h is None:
        raise FiltroInvalido("indicá al menos uno de los dos valores.")
    return d, h


def _si_no(v: Any) -> bool:
    if v in (True, "true", "si", "1", 1):
        return True
    if v in (False, "false", "no", "0", 0):
        return False
    raise FiltroInvalido("elegí sí o no.")


def _inicio(d: date) -> datetime:
    return datetime.combine(d, time.min).astimezone()


# ---------------------------------------------------------------- constructores de condiciones


def c_texto(col) -> Condicion:
    def f(op, v):
        if op == "vacio":
            return or_(col.is_(None), func.trim(col) == "")
        if op == "no_vacio":
            return and_(col.is_not(None), func.trim(col) != "")
        patron = _texto(v)
        return col.ilike(patron) if op == "contiene" else or_(col.is_(None), not_(col.ilike(patron)))

    return f


def c_opcion(col, convertir: Callable[[str], Any] = lambda x: x) -> Condicion:
    def f(op, v):
        if op == "vacio":
            return col.is_(None)
        if op == "no_vacio":
            return col.is_not(None)
        try:
            valores = [convertir(x) for x in _lista(v)]
        except (TypeError, ValueError):
            raise FiltroInvalido("opción inexistente.") from None
        return col.in_(valores) if op == "es" else or_(col.is_(None), col.not_in(valores))

    return f


def c_multiple(col) -> Condicion:
    def f(op, v):
        vacio = or_(col.is_(None), func.jsonb_array_length(col) == 0)
        if op == "vacio":
            return vacio
        if op == "no_vacio":
            return not_(vacio)
        partes = [col.contains([x]) for x in _lista(v)]
        if op == "alguno":
            return or_(*partes)
        if op == "todos":
            return and_(*partes)
        return or_(vacio, not_(or_(*partes)))

    return f


def c_fecha(col, es_fecha_hora: bool = False) -> Condicion:
    def f(op, v):
        if op == "vacio":
            return col.is_(None)
        if op == "no_vacio":
            return col.is_not(None)
        d, h = _rango_fechas(v)
        partes = []
        if es_fecha_hora:
            if d:
                partes.append(col >= _inicio(d))
            if h:
                partes.append(col < _inicio(h + timedelta(days=1)))
        else:
            if d:
                partes.append(col >= d)
            if h:
                partes.append(col <= h)
        return and_(*partes)

    return f


def c_numero(col) -> Condicion:
    def f(op, v):
        if op == "vacio":
            return col.is_(None)
        if op == "no_vacio":
            return col.is_not(None)
        d, h = _rango_numeros(v)
        partes = []
        if d is not None:
            partes.append(col >= d)
        if h is not None:
            partes.append(col <= h)
        return and_(*partes)

    return f


def c_si_no(cond_si) -> Condicion:
    """``cond_si`` es la condición (o una función sin argumentos que la arma) para «sí»."""

    def f(op, v):
        c = cond_si() if callable(cond_si) else cond_si
        return c if _si_no(v) else not_(c)

    return f


def c_bool(col) -> Condicion:
    def f(op, v):
        return col.is_(True) if _si_no(v) else or_(col.is_(False), col.is_(None))

    return f


def c_existe(modelo, union, armar: Condicion) -> Condicion:
    """La condición vale si existe una fila de ``modelo`` (unida por ``union``) que la cumple."""

    def f(op, v):
        if op in ("no_es", "no_contiene", "ninguno"):
            positivo = {"no_es": "es", "no_contiene": "contiene", "ninguno": "alguno"}[op]
            return not_(exists().where(union, armar(positivo, v)))
        if op == "vacio":
            return not_(exists().where(union))
        if op == "no_vacio":
            return exists().where(union)
        return exists().where(union, armar(op, v))

    return f


def c_edad(col_nacimiento) -> Condicion:
    def f(op, v):
        if op == "vacio":
            return col_nacimiento.is_(None)
        if op == "no_vacio":
            return col_nacimiento.is_not(None)
        d, h = _rango_numeros(v)
        hoy = date.today()
        partes = []
        if d is not None:  # al menos d años: nació antes de hoy - d años
            partes.append(col_nacimiento <= _restar_anios(hoy, int(d)))
        if h is not None:  # como mucho h años: nació después de hoy - (h + 1) años
            partes.append(col_nacimiento > _restar_anios(hoy, int(h) + 1))
        return and_(*partes)

    return f


def _restar_anios(d: date, n: int) -> date:
    try:
        return d.replace(year=d.year - n)
    except ValueError:  # 29 de febrero
        return d.replace(year=d.year - n, day=28)


# ---------------------------------------------------------------- opciones


def _de_dict(catalogo: dict) -> list[dict]:
    return [{"valor": k, "texto": v} for k, v in catalogo.items()]


def _jerarquicas(catalogo: dict) -> list[dict]:
    salida = []
    for g, (texto, subs) in catalogo.items():
        salida.append({"valor": g, "texto": texto})
        salida += [{"valor": f"{g}.{s}", "texto": f"{texto}: {t}", "nivel": 1} for s, t in subs.items()]
    return salida


def _simple(catalogo: dict) -> list[dict]:
    salida = []
    for g, (texto, subs) in catalogo.items():
        salida.append({"valor": g, "texto": texto})
    return salida


def _detalles(catalogo: dict) -> list[dict]:
    return [{"valor": s, "texto": f"{texto}: {t}"} for _, (texto, subs) in catalogo.items() for s, t in subs.items()]


def op_areas(db: Session) -> list[dict]:
    return [{"valor": str(a.id), "texto": a.nombre} for a in db.execute(select(Area).where(Area.activo).order_by(Area.nombre)).scalars()]


def op_usuarios(db: Session) -> list[dict]:
    return [
        {"valor": str(u.id), "texto": u.nombre_completo + ("" if u.activo else " (inactivo)")}
        for u in db.execute(select(Usuario).order_by(Usuario.activo.desc(), Usuario.nombre_completo)).scalars()
    ]


def op_tipos_documentales(db: Session) -> list[dict]:
    return [{"valor": str(t.id), "texto": t.nombre} for t in db.execute(select(TipoDocumental).order_by(TipoDocumental.nombre)).scalars()]


def op_distintos(col) -> Callable[[Session], list[dict]]:
    def f(db: Session) -> list[dict]:
        return [{"valor": v, "texto": v} for v in db.execute(select(col).where(col.is_not(None)).distinct().order_by(col)).scalars() if v]

    return f


DEPARTAMENTOS = [{"valor": d, "texto": d} for d in F.DEPARTAMENTOS]
ESTADOS = [
    {"valor": "abierto", "texto": "Abierto"},
    {"valor": "en_seguimiento", "texto": "En seguimiento"},
    {"valor": "pausado", "texto": "Pausado"},
    {"valor": "cerrado", "texto": "Cerrado"},
]
NEGATIVA = [
    {"valor": "vigente", "texto": "Negativa vigente"},
    {"valor": "vencida", "texto": "Negativa vencida"},
    {"valor": "con_registros", "texto": "Con beneficios registrados"},
    {"valor": "no_emitida", "texto": "No emitida"},
]


# ---------------------------------------------------------------- campos de la persona

def _campos_persona(grupo: str = "Persona") -> list[Campo]:
    P = Persona
    return [
        Campo("persona.numero_legajo", "N° de legajo", grupo, "texto", c_texto(P.numero_legajo)),
        Campo("persona.apellidos", "Apellido", grupo, "texto", c_texto(P.apellidos)),
        Campo("persona.nombres", "Nombre", grupo, "texto", c_texto(P.nombres)),
        Campo("persona.tipo_documento", "Tipo de documento", grupo, "opcion", c_opcion(P.tipo_documento), op_distintos(P.tipo_documento)),
        Campo("persona.numero_documento", "N° de documento", grupo, "texto", c_texto(P.numero_documento)),
        Campo("persona.sin_documento", "Sin documento", grupo, "si_no", c_bool(P.sin_documento)),
        Campo("persona.legajo_provisorio", "Legajo provisorio", grupo, "si_no", c_si_no(lambda: P.legajo_provisorio.is_not(None))),
        Campo("persona.cuil", "CUIL", grupo, "texto", c_texto(P.cuil)),
        Campo("persona.edad", "Edad (años)", grupo, "numero", c_edad(P.fecha_nacimiento)),
        Campo("persona.fecha_nacimiento", "Fecha de nacimiento", grupo, "fecha", c_fecha(P.fecha_nacimiento)),
        Campo("persona.genero", "Género", grupo, "opcion", c_opcion(P.genero), _de_dict(F.GENEROS)),
        Campo("persona.domicilio", "Domicilio", grupo, "texto", c_texto(P.domicilio)),
        Campo("persona.barrio", "Barrio", grupo, "texto", c_texto(P.barrio)),
        Campo("persona.localidad", "Localidad", grupo, "texto", c_texto(P.localidad)),
        Campo("persona.departamento", "Departamento", grupo, "opcion", c_opcion(P.departamento), DEPARTAMENTOS),
        Campo("persona.ubicada", "Ubicada en el mapa", grupo, "si_no", c_si_no(lambda: P.lat.is_not(None))),
        Campo("persona.telefono", "Teléfono", grupo, "texto", c_texto(P.telefono)),
        Campo("persona.cud", "CUD", grupo, "opcion", c_opcion(P.cud), _de_dict(F.CUD)),
        Campo("persona.discapacidades", "Discapacidad", grupo, "multiple", c_multiple(P.discapacidades), _de_dict(F.DISCAPACIDAD)),
        Campo("persona.cobertura_salud", "Cobertura de salud", grupo, "multiple", c_multiple(P.cobertura_salud), _de_dict(F.COBERTURA_SALUD)),
        Campo("persona.obra_social", "Obra social", grupo, "texto", c_texto(P.obra_social)),
        Campo("persona.cobertura_previsional", "Cobertura previsional", grupo, "multiple", c_multiple(P.cobertura_previsional), _de_dict(F.COBERTURA_PREVISIONAL)),
        Campo("persona.trabajo_informal", "Trabajo informal", grupo, "si_no", c_bool(P.trabajo_informal)),
        Campo("persona.observaciones", "Observaciones del legajo", grupo, "texto", c_texto(P.observaciones)),
        Campo("persona.creado_en", "Alta del legajo", grupo, "fecha", c_fecha(P.creado_en, True)),
        Campo("persona.negativa", "Negativa de ANSES", grupo, "opcion", _negativa, NEGATIVA),
        Campo(
            "persona.carpeta_area", "Carpeta en papel en el área", grupo, "opcion",
            c_existe(UbicacionFisica, UbicacionFisica.persona_id == P.id, c_opcion(UbicacionFisica.area_id, int)), op_areas,
        ),
    ]


def _negativa(op, v):
    """Estado de la última constancia de ANSES de la persona."""
    K = aliased(Constancia)
    ultima = (
        select(K.id)
        .where(K.persona_id == Persona.id, K.tipo == "negativa_anses")
        .order_by(K.fecha_emision.desc(), K.id.desc())
        .limit(1)
        .correlate(Persona)
        .scalar_subquery()
    )
    hoy = date.today()

    def estado(x: str):
        base = Constancia.id == ultima
        if x == "vigente":
            return and_(base, Constancia.resultado == "sin_registros", or_(Constancia.vence.is_(None), Constancia.vence >= hoy))
        if x == "vencida":
            return and_(base, Constancia.resultado == "sin_registros", Constancia.vence < hoy)
        if x not in ("con_registros", "no_emitida"):
            raise FiltroInvalido("opción inexistente.")
        return and_(base, Constancia.resultado == x)

    if op == "vacio":
        return not_(exists().where(Constancia.persona_id == Persona.id, Constancia.tipo == "negativa_anses"))
    if op == "no_vacio":
        return exists().where(Constancia.persona_id == Persona.id, Constancia.tipo == "negativa_anses")
    cond = or_(*[exists().where(estado(x)) for x in _lista(v)])
    return cond if op == "es" else not_(cond)


# ---------------------------------------------------------------- casos

def _asignado(op, v):
    return c_existe(
        CasoAsignacion, and_(CasoAsignacion.caso_id == Caso.id, CasoAsignacion.hasta.is_(None)),
        c_opcion(CasoAsignacion.usuario_id, uuid.UUID),
    )(op, v)


def _demanda(armar: Condicion) -> Condicion:
    return c_existe(RegistroDemanda, RegistroDemanda.caso_id == Caso.id, armar)


def _campos_casos() -> list[Campo]:
    C, R = Caso, RegistroDemanda
    g, gd = "Caso", "Registro de demanda"
    return [
        Campo("caso.numero", "N° de caso", g, "texto", c_texto(C.numero)),
        Campo("caso.estado", "Estado", g, "opcion", c_opcion(C.estado), ESTADOS),
        Campo("caso.area", "Área", g, "opcion", c_opcion(C.area_id, int), op_areas),
        Campo("caso.responsable", "Técnico/a a cargo", g, "opcion", _asignado, op_usuarios),
        Campo("caso.fecha_ingreso", "Fecha de ingreso", g, "fecha", c_fecha(C.fecha_ingreso)),
        Campo("caso.anio_actuacion", "Año de la actuación", g, "numero", c_numero(C.anio_actuacion)),
        Campo("caso.abierto_en", "Alta en el sistema", g, "fecha", c_fecha(C.abierto_en, True)),
        Campo("caso.ultima_actividad", "Última actividad", g, "fecha", c_fecha(C.ultima_actividad, True)),
        Campo("caso.cerrado_en", "Fecha de cierre", g, "fecha", c_fecha(C.cerrado_en, True)),
        Campo("caso.motivo", "Motivo de ingreso", g, "texto", c_texto(C.motivo)),
        Campo("caso.antecedentes", "Con antecedentes", g, "si_no", c_bool(C.antecedentes)),
        Campo("caso.tipo_ingreso", "Tipo de ingreso", g, "opcion", c_opcion(C.tipo_ingreso), _simple(F.TIPOS_INGRESO)),
        Campo("caso.tipo_ingreso_detalle", "Detalle del ingreso", g, "opcion", c_opcion(C.tipo_ingreso_detalle), _detalles(F.TIPOS_INGRESO)),
        Campo("caso.derivado_por", "Derivado por", g, "opcion", c_opcion(C.derivado_por), _de_dict(F.DERIVADO_POR)),
        Campo("caso.derivado_por_detalle", "Detalle de la derivación", g, "texto", c_texto(C.derivado_por_detalle)),
        Campo("caso.indicadores", "Indicadores", g, "multiple", c_multiple(C.indicadores), _jerarquicas(F.INDICADORES)),
        Campo("caso.intervenciones", "Intervenciones", g, "multiple", c_multiple(C.intervenciones), _jerarquicas(F.INTERVENCIONES)),
        Campo("caso.intervencion_otro", "Otra intervención", g, "texto", c_texto(C.intervencion_otro)),
        Campo("caso.caratula_impresa", "Carátula impresa", g, "si_no", c_si_no(lambda: C.caratula_impresa_en.is_not(None))),
        Campo(
            "caso.evolucion", "Con evolución en", g, "fecha",
            c_existe(CasoEvolucion, CasoEvolucion.caso_id == C.id, c_fecha(CasoEvolucion.fecha)), operadores=["entre", "vacio", "no_vacio"],
        ),
        Campo(
            "caso.reiteracion", "Con reiteración en", g, "fecha",
            c_existe(Reiteracion, Reiteracion.caso_id == C.id, c_fecha(Reiteracion.fecha)), operadores=["entre", "vacio", "no_vacio"],
        ),
        Campo(
            "caso.articulacion", "Con articulación en", g, "fecha",
            c_existe(Articulacion, Articulacion.caso_id == C.id, c_fecha(Articulacion.fecha)), operadores=["entre", "vacio", "no_vacio"],
        ),
        Campo(
            "caso.expediente", "Con expediente", g, "opcion",
            c_existe(Expediente, Expediente.caso_id == C.id, c_opcion(Expediente.tipo)),
            [{"valor": "administrativo", "texto": "Administrativo"}, {"valor": "judicial", "texto": "Judicial"}],
        ),
        Campo("demanda.fecha", "Fecha del registro", gd, "fecha", _demanda(c_fecha(R.fecha)), operadores=["entre", "vacio", "no_vacio"]),
        Campo("demanda.solicitante_vinculo", "Vínculo de quien solicita", gd, "texto", _demanda(c_texto(R.solicitante_vinculo))),
        Campo("demanda.solicitud_expresa", "Solicitud expresa", gd, "texto", _demanda(c_texto(R.solicitud_expresa))),
        Campo("demanda.tipo_vivienda", "Tipo de vivienda", gd, "opcion", _demanda(c_opcion(R.tipo_vivienda)), _de_dict(F.TIPO_VIVIENDA)),
        Campo("demanda.estado_civil", "Estado civil", gd, "opcion", _demanda(c_opcion(R.estado_civil)), _de_dict(F.ESTADO_CIVIL)),
        Campo("demanda.tiene_hijos", "Tiene hijos", gd, "si_no", _demanda_bool(R.tiene_hijos)),
        Campo("demanda.vinculo_con_hijos", "Vínculo con los hijos", gd, "si_no", _demanda_bool(R.vinculo_con_hijos)),
        Campo("demanda.convive_con", "Convive con", gd, "texto", _demanda(c_texto(R.convive_con))),
        Campo("demanda.referente", "Referente", gd, "texto", _demanda(c_texto(R.referente_nombre))),
        Campo("demanda.diagnosticos", "Diagnósticos", gd, "texto", _demanda(c_texto(R.diagnosticos))),
        Campo("demanda.tiene_autonomia", "Tiene autonomía", gd, "si_no", _demanda_bool(R.tiene_autonomia)),
        Campo("demanda.estado_funcional", "Estado funcional", gd, "opcion", _demanda(c_opcion(R.estado_funcional)), _de_dict(F.ESTADO_FUNCIONAL)),
        Campo("demanda.observaciones", "Observaciones del registro", gd, "texto", _demanda(c_texto(R.observaciones))),
        Campo("demanda.cargado_desde_papel", "Cargado desde papel", gd, "si_no", _demanda_bool(R.cargado_desde_papel)),
        *_campos_persona(),
    ]


def _demanda_bool(col) -> Condicion:
    def f(op, v):
        return exists().where(RegistroDemanda.caso_id == Caso.id, col.is_(True) if _si_no(v) else col.is_(False))

    return f


# ---------------------------------------------------------------- legajos

def _campos_legajos() -> list[Campo]:
    P = Persona
    g = "Casos de la persona"
    casos = Caso.persona_id == P.id
    return [
        *_campos_persona("Persona"),
        Campo("legajo.caso_activo", "Tiene casos activos", g, "si_no", c_si_no(lambda: exists().where(casos, Caso.estado != "cerrado"))),
        Campo("legajo.caso_area", "Área de alguno de sus casos", g, "opcion", c_existe(Caso, casos, c_opcion(Caso.area_id, int)), op_areas),
        Campo(
            "legajo.responsable", "Técnico/a a cargo de algún caso", g, "opcion",
            c_existe(
                CasoAsignacion,
                and_(CasoAsignacion.hasta.is_(None), CasoAsignacion.caso_id.in_(select(Caso.id).where(casos))),
                c_opcion(CasoAsignacion.usuario_id, uuid.UUID),
            ),
            op_usuarios,
        ),
        Campo("legajo.indicadores", "Indicadores en algún caso", g, "multiple", c_existe(Caso, casos, c_multiple(Caso.indicadores)), _jerarquicas(F.INDICADORES)),
        Campo("legajo.expediente", "Tiene expediente", g, "si_no", c_si_no(lambda: exists().where(Expediente.persona_id == P.id))),
    ]


# ---------------------------------------------------------------- expedientes y Mesa de Entrada

def _campos_expedientes() -> list[Campo]:
    E = Expediente
    g = "Expediente"
    return [
        Campo("expediente.numero", "Número", g, "texto", c_texto(E.numero)),
        Campo("expediente.tipo", "Tipo", g, "opcion", c_opcion(E.tipo), [{"valor": "administrativo", "texto": "Administrativo"}, {"valor": "judicial", "texto": "Judicial"}]),
        Campo("expediente.organismo", "Organismo", g, "texto", c_texto(E.organismo)),
        Campo("expediente.caratula", "Carátula", g, "texto", c_texto(E.caratula)),
        Campo("expediente.observaciones", "Observaciones", g, "texto", c_texto(E.observaciones)),
        Campo("expediente.con_caso", "Vinculado a un caso", g, "si_no", c_si_no(lambda: E.caso_id.is_not(None))),
        Campo("expediente.creado_en", "Fecha de carga", g, "fecha", c_fecha(E.creado_en, True)),
        Campo("expediente.cargado_por", "Cargado por", g, "opcion", c_opcion(E.creado_por, uuid.UUID), op_usuarios),
        Campo(
            "expediente.carpeta_area", "Carpeta en papel en el área", g, "opcion",
            c_existe(UbicacionFisica, UbicacionFisica.expediente_id == E.id, c_opcion(UbicacionFisica.area_id, int)), op_areas,
        ),
        *[c for c in _campos_persona("Persona") if c.clave in {
            "persona.apellidos", "persona.numero_documento", "persona.numero_legajo", "persona.edad", "persona.genero",
            "persona.localidad", "persona.departamento",
        }],
    ]


def _campos_ingresos() -> list[Campo]:
    I = Ingreso
    g = "Ingreso"
    return [
        Campo("ingreso.numero", "N° de ingreso", g, "texto", c_texto(I.numero)),
        Campo("ingreso.fecha_ingreso", "Fecha de ingreso", g, "fecha", c_fecha(I.fecha_ingreso, True)),
        Campo("ingreso.remitente", "Remitente", g, "texto", c_texto(I.remitente)),
        Campo("ingreso.tipo_documental", "Tipo de documento", g, "opcion", c_opcion(I.tipo_documental_id, int), op_tipos_documentales),
        Campo("ingreso.asunto", "Asunto", g, "texto", c_texto(I.asunto)),
        Campo("ingreso.folios", "Folios", g, "numero", c_numero(I.folios)),
        Campo("ingreso.persona_mencionada", "Persona mencionada", g, "texto", c_texto(I.persona_mencionada)),
        Campo("ingreso.documento_mencionado", "Documento mencionado", g, "texto", c_texto(I.documento_mencionado)),
        Campo("ingreso.expediente_externo", "Expediente externo", g, "texto", c_texto(I.numero_expediente_externo)),
        Campo("ingreso.observaciones", "Observaciones", g, "texto", c_texto(I.observaciones)),
        Campo("ingreso.vinculado", "Vinculado a un legajo", g, "si_no", c_si_no(lambda: I.persona_id.is_not(None))),
        Campo("ingreso.vinculado_en", "Fecha de vinculación", g, "fecha", c_fecha(I.vinculado_en, True)),
        Campo("ingreso.con_caso", "Vinculado a un caso", g, "si_no", c_si_no(lambda: I.caso_id.is_not(None))),
        Campo("ingreso.registrado_por", "Registrado por", g, "opcion", c_opcion(I.creado_por, uuid.UUID), op_usuarios),
    ]


# ---------------------------------------------------------------- recursos y contactos

def _tipos_recurso() -> list[dict]:
    from .routers.recursos import TIPOS

    return [{"valor": t["codigo"], "texto": t["texto"]} for t in TIPOS]


def _categorias_recurso() -> list[dict]:
    from .routers.recursos import TIPOS

    return [{"valor": c["codigo"], "texto": c["texto"]} for t in TIPOS for c in t.get("categorias", [])]


def _origenes() -> list[dict]:
    from .routers.recursos import ORIGENES

    return [{"valor": o["codigo"], "texto": o["texto"]} for o in ORIGENES]


def _campos_recursos() -> list[Campo]:
    R = Recurso
    g = "Recurso"
    return [
        Campo("recurso.tipo", "Tipo", g, "opcion", c_opcion(R.tipo), lambda db: _tipos_recurso()),
        Campo("recurso.categoria", "Categoría de institución", g, "opcion", c_opcion(R.categoria), lambda db: _categorias_recurso()),
        Campo("recurso.nombre", "Nombre", g, "texto", c_texto(R.nombre)),
        Campo("recurso.direccion", "Dirección", g, "texto", c_texto(R.direccion)),
        Campo("recurso.localidad", "Localidad", g, "texto", c_texto(R.localidad)),
        Campo("recurso.departamento", "Departamento", g, "opcion", c_opcion(R.departamento), DEPARTAMENTOS),
        Campo("recurso.zonas", "Zonas donde trabaja", g, "multiple", c_multiple(R.zonas), DEPARTAMENTOS),
        Campo("recurso.ubicado", "Ubicado en el mapa", g, "si_no", c_si_no(lambda: R.lat.is_not(None))),
        Campo("recurso.telefono", "Teléfono", g, "texto", c_texto(R.telefono)),
        Campo("recurso.email", "Correo", g, "texto", c_texto(R.email)),
        Campo("recurso.horario", "Horario", g, "texto", c_texto(R.horario)),
        Campo("recurso.referente", "Referente", g, "texto", c_texto(R.referente)),
        Campo("recurso.servicios", "Servicios", g, "texto", c_texto(R.servicios)),
        Campo("recurso.formacion", "Formación", g, "texto", c_texto(R.formacion)),
        Campo("recurso.disponibilidad", "Disponibilidad", g, "texto", c_texto(R.disponibilidad)),
        Campo("recurso.observaciones", "Observaciones", g, "texto", c_texto(R.observaciones)),
        Campo("recurso.origen", "De dónde sale el dato", g, "opcion", c_opcion(R.origen), lambda db: _origenes()),
        Campo("recurso.articulaciones", "Usado en articulaciones", g, "si_no", c_si_no(lambda: exists().where(Articulacion.recurso_id == R.id))),
        Campo("recurso.actualizado_en", "Última actualización", g, "fecha", c_fecha(R.actualizado_en, True)),
    ]


def _campos_contactos() -> list[Campo]:
    C = Contacto
    g = "Contacto"
    return [
        Campo("contacto.nombre", "Nombre", g, "texto", c_texto(C.nombre)),
        Campo("contacto.cargo", "Cargo", g, "texto", c_texto(C.cargo)),
        Campo("contacto.institucion", "Institución", g, "texto", c_texto(C.institucion)),
        Campo("contacto.categoria", "Categoría", g, "opcion", c_opcion(C.categoria), lambda db: _categorias_recurso()),
        Campo("contacto.localidad", "Localidad", g, "texto", c_texto(C.localidad)),
        Campo("contacto.departamento", "Departamento", g, "opcion", c_opcion(C.departamento), DEPARTAMENTOS),
        Campo("contacto.telefono", "Teléfono", g, "texto", c_texto(C.telefono)),
        Campo("contacto.whatsapp", "WhatsApp", g, "texto", c_texto(C.whatsapp)),
        Campo("contacto.email", "Correo", g, "texto", c_texto(C.email)),
        Campo("contacto.temas", "Temas", g, "texto", c_texto(C.temas)),
        Campo("contacto.observaciones", "Observaciones", g, "texto", c_texto(C.observaciones)),
        Campo("contacto.origen", "De dónde sale el dato", g, "opcion", c_opcion(C.origen), lambda db: _origenes()),
        Campo("contacto.con_recurso", "Vinculado a un recurso del mapa", g, "si_no", c_si_no(lambda: C.recurso_id.is_not(None))),
        Campo("contacto.articulaciones", "Usado en articulaciones", g, "si_no", c_si_no(lambda: exists().where(Articulacion.contacto_id == C.id))),
    ]


# ---------------------------------------------------------------- catálogo y aplicación

# Permiso que hace falta para pedir el catálogo de cada lista.
LISTAS: dict[str, tuple[Callable[[], list[Campo]], tuple[str, str]]] = {
    "casos": (_campos_casos, ("casos", "consultar")),
    "legajos": (_campos_legajos, ("personas", "consultar")),
    "expedientes": (_campos_expedientes, ("expedientes", "consultar")),
    "ingresos": (_campos_ingresos, ("mesa_entrada", "consultar")),
    "recursos": (_campos_recursos, ("recursos", "consultar")),
    "contactos": (_campos_contactos, ("recursos", "consultar")),
}
_CACHE: dict[str, dict[str, Campo]] = {}


def campos(lista: str) -> dict[str, Campo]:
    if lista not in LISTAS:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Lista sin filtros.")
    if lista not in _CACHE:
        _CACHE[lista] = {c.clave: c for c in LISTAS[lista][0]()}
    return _CACHE[lista]


def catalogo(db: Session, lista: str) -> list[dict]:
    salida = []
    for c in campos(lista).values():
        opciones = c.opciones(db) if callable(c.opciones) else c.opciones
        salida.append({"clave": c.clave, "etiqueta": c.etiqueta, "grupo": c.grupo, "tipo": c.tipo, "operadores": c.ops(), "opciones": opciones})
    return salida


def leer(texto: str | None) -> list[dict]:
    """Interpreta el parámetro ``f``. Vacío = sin filtros."""
    if not texto:
        return []
    try:
        datos = json.loads(texto)
    except ValueError:
        raise FiltroInvalido("formato incorrecto.") from None
    if not isinstance(datos, list) or len(datos) > MAX_FILTROS or not all(isinstance(x, dict) for x in datos):
        raise FiltroInvalido(f"se admiten hasta {MAX_FILTROS} filtros.")
    return datos


def condicion(lista: str, filtros: list[dict]):
    """Une todos los filtros con «y». Devuelve ``true()`` si no hay filtros."""
    if not filtros:
        return true()
    disponibles = campos(lista)
    partes = []
    for f in filtros:
        campo = disponibles.get(str(f.get("c")))
        if campo is None:
            raise FiltroInvalido(f"campo desconocido ({f.get('c')}).")
        op = str(f.get("o") or campo.ops()[0])
        if op not in campo.ops():
            raise FiltroInvalido(f"«{campo.etiqueta}» no admite esa comparación.")
        partes.append(campo.condicion(op, f.get("v")))
    return and_(*partes)


def aplicar(lista: str, consulta, texto: str | None):
    return consulta.where(condicion(lista, leer(texto)))


__all__ = ["aplicar", "catalogo", "condicion", "leer", "LISTAS", "false"]


def total(db: Session, consulta) -> int:
    """Cantidad de filas de una consulta (sin orden ni límite)."""
    return db.execute(select(func.count()).select_from(consulta.order_by(None).limit(None).subquery())).scalar_one()


def resumen(texto: str | None) -> list[str]:
    """Claves de los campos usados, para la auditoría (sin valores)."""
    return [str(f.get("c")) for f in leer(texto)]


def describir(db: Session, lista: str, filtros: list[dict]) -> list[str]:
    """Texto legible de cada filtro (para el PDF y el Excel)."""
    OPS = {"contiene": "contiene", "no_contiene": "no contiene", "vacio": "sin dato", "no_vacio": "con algún dato", "es": "es",
           "no_es": "no es", "alguno": "incluye", "todos": "incluye todos", "ninguno": "no incluye", "entre": ""}
    disponibles = campos(lista)
    salida = []
    for f in filtros:
        c = disponibles.get(str(f.get("c")))
        if c is None:
            continue
        op, v = f.get("o"), f.get("v")
        if op in ("vacio", "no_vacio"):
            valor = ""
        elif c.tipo == "si_no":
            salida.append(f"{c.etiqueta}: {'sí' if v in (True, 'true', 1) else 'no'}")
            continue
        elif c.tipo in ("fecha", "numero") and isinstance(v, dict):
            d, h = v.get("desde"), v.get("hasta")
            if c.tipo == "fecha":
                d = date.fromisoformat(d).strftime("%d/%m/%Y") if d else None
                h = date.fromisoformat(h).strftime("%d/%m/%Y") if h else None
            valor = f"de {d} a {h}" if d is not None and h is not None else f"desde {d}" if d is not None else f"hasta {h}"
        elif c.tipo in ("opcion", "multiple"):
            ops = c.opciones(db) if callable(c.opciones) else (c.opciones or [])
            textos = {o["valor"]: o["texto"] for o in ops}
            valor = (" y " if op == "todos" else " o ").join(textos.get(str(x), str(x)) for x in (v if isinstance(v, list) else [v]))
        else:
            valor = f"«{v}»"
        salida.append(" ".join(x for x in (c.etiqueta, OPS.get(op, op), valor) if x))
    return salida

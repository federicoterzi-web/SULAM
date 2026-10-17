"""Página de inicio de cada rol.

Cada rol tiene un «perfil de inicio» (roles.inicio) que decide qué ve la persona
al entrar. Todo lo que se muestra respeta los permisos de siempre: alcance de
consulta y contenido reservado.
"""

from __future__ import annotations

from collections import Counter, defaultdict
from datetime import date, timedelta

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import and_, exists, func, select
from sqlalchemy.orm import Session

from ..db import get_db
from ..deps import contexto
from ..models import (
    Area,
    Caso,
    CasoAsignacion,
    CasoEvolucion,
    Documento,
    Expediente,
    Ingreso,
    Persona,
    RegistroDemanda,
    Reiteracion,
    Usuario,
)
from ..permissions import Contexto, filtro_casos, ve_caso_reservado
from ..security import ahora
from ..serializers import caso_out, documento_out, expediente_out, ingreso_out, persona_resumen

router = APIRouter(tags=["inicio"])

# Orden de prioridad cuando una persona tiene varios roles.
PERFILES = {
    "direccion": "Dirección",
    "jefatura": "Jefatura",
    "tecnico": "Técnico/a",
    "carga": "Carga de datos",
    "mesa": "Mesa de Entrada",
    "administrativo_area": "Administrativo de área",
}
DIAS_SIN_ACTIVIDAD = 30


def perfiles_de(usuario: Usuario) -> list[str]:
    propios = {r.inicio for r in usuario.roles if r.activo and r.inicio in PERFILES}
    return [p for p in PERFILES if p in propios]


# ---------------------------------------------------------------- auxiliares


def _hoy() -> date:
    return ahora().astimezone().date()


def _activos():
    return Caso.estado != "cerrado"


def _con_responsable():
    return exists().where(CasoAsignacion.caso_id == Caso.id, CasoAsignacion.hasta.is_(None))


def _visibles(ctx: Contexto):
    alcance = ctx.alcance("casos", "consultar")
    return filtro_casos(ctx, alcance) if alcance else None


def _casos(db: Session, ctx: Contexto, consulta) -> list[dict]:
    return [caso_out(c, ve_caso_reservado(db, ctx, c), p) for c, p in db.execute(consulta).all()]


def _base(ctx: Contexto):
    filtro = _visibles(ctx)
    q = select(Caso, Persona).join(Persona, Persona.id == Caso.persona_id)
    return q.where(filtro) if filtro is not None else q.where(Caso.id.is_(None))


def _contar(db: Session, *condiciones) -> int:
    return db.execute(select(func.count(Caso.id)).where(*condiciones)).scalar_one()


def _maltrato(indicadores) -> bool:
    return any(str(i).startswith("maltrato") for i in indicadores or [])


def _limite_actividad():
    return ahora() - timedelta(days=DIAS_SIN_ACTIVIDAD)


# ---------------------------------------------------------------- perfiles


def _tecnico(db: Session, ctx: Contexto) -> dict:
    asignaciones = {
        a.caso_id: a.desde
        for a in db.execute(
            select(CasoAsignacion).where(CasoAsignacion.usuario_id == ctx.id, CasoAsignacion.hasta.is_(None))
        ).scalars()
    }
    filas = db.execute(
        select(Caso, Persona)
        .join(Persona, Persona.id == Caso.persona_id)
        .where(Caso.id.in_(asignaciones.keys()), _activos())
    ).all()
    ids = [c.id for c, _ in filas]
    ultimas: dict = {}
    for e in db.execute(
        select(CasoEvolucion)
        .where(CasoEvolucion.caso_id.in_(ids))
        .order_by(CasoEvolucion.caso_id, CasoEvolucion.fecha.desc(), CasoEvolucion.en.desc())
    ).scalars():
        ultimas.setdefault(e.caso_id, e)
    hace30 = _hoy() - timedelta(days=30)
    reiterados = set(
        db.execute(
            select(Reiteracion.caso_id).where(Reiteracion.caso_id.in_(ids), Reiteracion.fecha >= hace30)
        ).scalars()
    )
    limite = _limite_actividad()
    nuevo_desde = ahora() - timedelta(days=7)
    casos = []
    for c, p in filas:
        d = caso_out(c, True, p)
        e = ultimas.get(c.id)
        d["ultima_evolucion"] = (
            {"fecha": e.fecha.isoformat(), "texto": e.texto[:240], "autor": e.autor.nombre_completo if e.autor else e.autor_nombre}
            if e
            else None
        )
        d["alertas"] = {
            "maltrato": _maltrato(c.indicadores),
            "sin_actividad": c.ultima_actividad < limite,
            "reiteracion_reciente": c.id in reiterados,
            "nuevo": asignaciones[c.id] >= nuevo_desde,
        }
        casos.append(d)
    casos.sort(
        key=lambda d: (
            not d["alertas"]["maltrato"],
            not d["alertas"]["reiteracion_reciente"],
            not d["alertas"]["sin_actividad"],
            not d["alertas"]["nuevo"],
            d["ultima_actividad"] or "",
        )
    )
    return {"casos": casos, "dias_sin_actividad": DIAS_SIN_ACTIVIDAD}


def _jefatura(db: Session, ctx: Contexto) -> dict:
    area_id = ctx.usuario.area_id
    if area_id is None:
        return {"sin_area": True}
    area = db.get(Area, area_id)
    del_area = and_(Caso.area_id == area_id, _visibles(ctx))
    hoy = _hoy()
    mes = hoy.replace(day=1)
    limite = _limite_actividad()

    sin_responsable = _casos(
        db, ctx, _base(ctx).where(Caso.area_id == area_id, _activos(), ~_con_responsable()).order_by(Caso.abierto_en).limit(50)
    )
    sin_actividad = _casos(
        db,
        ctx,
        _base(ctx)
        .where(Caso.area_id == area_id, _activos(), _con_responsable(), Caso.ultima_actividad < limite)
        .order_by(Caso.ultima_actividad)
        .limit(20),
    )

    # Carga de trabajo del equipo: personas del área con casos asignados.
    activos_por = dict(
        db.execute(
            select(CasoAsignacion.usuario_id, func.count(Caso.id))
            .join(Caso, Caso.id == CasoAsignacion.caso_id)
            .where(CasoAsignacion.hasta.is_(None), _activos())
            .group_by(CasoAsignacion.usuario_id)
        ).all()
    )
    quietos_por = dict(
        db.execute(
            select(CasoAsignacion.usuario_id, func.count(Caso.id))
            .join(Caso, Caso.id == CasoAsignacion.caso_id)
            .where(CasoAsignacion.hasta.is_(None), _activos(), Caso.ultima_actividad < limite)
            .group_by(CasoAsignacion.usuario_id)
        ).all()
    )
    equipo = [
        {
            "id": str(u.id),
            "nombre_completo": u.nombre_completo,
            "casos_activos": activos_por.get(u.id, 0),
            "sin_actividad": quietos_por.get(u.id, 0),
        }
        for u in db.execute(
            select(Usuario).where(Usuario.area_id == area_id, Usuario.activo, Usuario.id != ctx.id).order_by(Usuario.nombre_completo)
        ).scalars()
    ]

    return {
        "area": {"id": area.id, "nombre": area.nombre},
        "sin_responsable": sin_responsable,
        "sin_actividad": sin_actividad,
        "equipo": equipo,
        "mes": {
            "desde": mes.isoformat(),
            "nuevas": _contar(db, del_area, Caso.fecha_ingreso >= mes),
            "reiteraciones": db.execute(
                select(func.count(Reiteracion.id)).join(Caso, Caso.id == Reiteracion.caso_id).where(del_area, Reiteracion.fecha >= mes)
            ).scalar_one(),
            "cerrados": _contar(db, del_area, Caso.estado == "cerrado", Caso.cerrado_en >= mes),
        },
        "activos": _contar(db, del_area, _activos()),
        "pendientes_impresion": _contar(db, del_area, Caso.caratula_impresa_en.is_(None)),
        "dias_sin_actividad": DIAS_SIN_ACTIVIDAD,
    }


def _direccion(db: Session, ctx: Contexto) -> dict:
    visibles = _visibles(ctx)
    hoy = _hoy()
    anio = hoy.year
    mes = hoy.replace(day=1)
    inicio_anio = date(anio, 1, 1)
    limite = _limite_actividad()

    nombres = {a.id: a.nombre for a in db.execute(select(Area)).scalars()}
    por_area: dict = defaultdict(lambda: {"nuevas": 0, "reiteraciones": 0, "activos": 0, "cerrados": 0})

    def sumar(clave, consulta):
        for area_id, n in db.execute(consulta).all():
            por_area[area_id][clave] = n

    sumar("nuevas", select(Caso.area_id, func.count(Caso.id)).where(visibles, Caso.anio_actuacion == anio).group_by(Caso.area_id))
    sumar("activos", select(Caso.area_id, func.count(Caso.id)).where(visibles, _activos()).group_by(Caso.area_id))
    sumar(
        "cerrados",
        select(Caso.area_id, func.count(Caso.id))
        .where(visibles, Caso.estado == "cerrado", Caso.cerrado_en >= inicio_anio)
        .group_by(Caso.area_id),
    )
    sumar(
        "reiteraciones",
        select(Caso.area_id, func.count(Reiteracion.id))
        .join(Caso, Caso.id == Reiteracion.caso_id)
        .where(visibles, Reiteracion.fecha >= inicio_anio)
        .group_by(Caso.area_id),
    )
    areas = sorted(
        ({"area": nombres.get(k, "Sin área"), **v} for k, v in por_area.items()),
        key=lambda x: -(x["nuevas"] + x["activos"]),
    )

    # Maltrato: casos ingresados en el mes con ese indicador, por tipo.
    con_maltrato = db.execute(
        select(Caso.indicadores).where(visibles, Caso.fecha_ingreso >= mes, Caso.indicadores.contains(["maltrato"]))
    ).scalars().all()
    tipos = Counter(i for ind in con_maltrato for i in ind or [] if str(i).startswith("maltrato."))

    sin_responsable_q = _base(ctx).where(_activos(), ~_con_responsable())
    return {
        "anio": anio,
        "mes": mes.isoformat(),
        "por_area": areas,
        "totales": {
            "nuevas": sum(a["nuevas"] for a in areas),
            "reiteraciones": sum(a["reiteraciones"] for a in areas),
            "activos": sum(a["activos"] for a in areas),
            "cerrados": sum(a["cerrados"] for a in areas),
        },
        "maltrato_mes": {"casos": len(con_maltrato), "por_tipo": dict(tipos)},
        "reservados_activos": _contar(db, visibles, _activos(), Caso.reservado),
        "sin_responsable": {
            "cantidad": _contar(db, visibles, _activos(), ~_con_responsable()),
            "casos": _casos(db, ctx, sin_responsable_q.order_by(Caso.abierto_en).limit(8)),
        },
        "sin_actividad": _contar(db, visibles, _activos(), Caso.ultima_actividad < limite),
        "recientes": _casos(db, ctx, _base(ctx).order_by(Caso.ultima_actividad.desc()).limit(10)),
        "dias_sin_actividad": DIAS_SIN_ACTIVIDAD,
    }


def _mesa(db: Session, ctx: Contexto) -> dict:
    hoy = _hoy()
    alcance = ctx.alcance("mesa_entrada", "consultar")
    base = select(Ingreso)
    if alcance == "propios":
        base = base.where(Ingreso.creado_por == ctx.id)
    sin_vincular = base.where(Ingreso.persona_id.is_(None))
    return {
        "hoy": db.execute(select(func.count()).select_from(base.where(Ingreso.fecha_ingreso == hoy).subquery())).scalar_one(),
        "sin_vincular_cantidad": db.execute(select(func.count()).select_from(sin_vincular.subquery())).scalar_one(),
        "sin_vincular": [ingreso_out(i) for i in db.execute(sin_vincular.order_by(Ingreso.fecha_ingreso.desc()).limit(15)).scalars()],
        "mios": [
            ingreso_out(i, db.get(Persona, i.persona_id) if i.persona_id else None)
            for i in db.execute(
                select(Ingreso).where(Ingreso.creado_por == ctx.id).order_by(Ingreso.creado_en.desc()).limit(10)
            ).scalars()
        ],
    }


def _carga(db: Session, ctx: Contexto) -> dict:
    visibles = _visibles(ctx)
    hoy = _hoy()
    sin_registro = ~exists().where(RegistroDemanda.caso_id == Caso.id)
    escaneada = exists().where(Documento.registro_demanda_id == RegistroDemanda.id, Documento.eliminado_en.is_(None))
    demandas = db.execute(
        select(RegistroDemanda, Caso, Persona)
        .join(Caso, Caso.id == RegistroDemanda.caso_id)
        .join(Persona, Persona.id == RegistroDemanda.persona_id)
        .where(visibles, RegistroDemanda.cargado_desde_papel, ~escaneada)
        .order_by(RegistroDemanda.fecha)
        .limit(20)
    ).all()
    return {
        "sin_registro_cantidad": _contar(db, visibles, _activos(), sin_registro),
        "sin_registro": _casos(db, ctx, _base(ctx).where(_activos(), sin_registro).order_by(Caso.abierto_en).limit(20)),
        "sin_escaneo_cantidad": db.execute(
            select(func.count(RegistroDemanda.id))
            .join(Caso, Caso.id == RegistroDemanda.caso_id)
            .where(visibles, RegistroDemanda.cargado_desde_papel, ~escaneada)
        ).scalar_one(),
        "sin_escaneo": [
            {
                "id": str(r.id),
                "fecha": r.fecha.isoformat(),
                "caso": {"id": str(c.id), "numero": c.numero, "actuacion": f"{c.numero_actuacion}/{c.anio_actuacion}"},
                "persona": persona_resumen(p),
            }
            for r, c, p in demandas
        ],
        "pendientes_impresion": _contar(db, visibles, Caso.caratula_impresa_en.is_(None)),
        "hoy": {
            "casos": _contar(db, Caso.creado_por == ctx.id, func.date(Caso.abierto_en) == hoy),
            "evoluciones": db.execute(
                select(func.count(CasoEvolucion.id)).where(CasoEvolucion.usuario_id == ctx.id, func.date(CasoEvolucion.en) == hoy)
            ).scalar_one(),
            "registros": db.execute(
                select(func.count(RegistroDemanda.id)).where(RegistroDemanda.creado_por == ctx.id, func.date(RegistroDemanda.creado_en) == hoy)
            ).scalar_one(),
        },
    }


def _administrativo_area(db: Session, ctx: Contexto) -> dict:
    area_id = ctx.usuario.area_id
    visibles = _visibles(ctx)
    del_area = and_(Caso.area_id == area_id, visibles) if area_id else visibles
    expedientes = []
    if ctx.tiene("expedientes", "consultar"):
        expedientes = [
            {**expediente_out(e, ve_caso_reservado(db, ctx, c)), "persona": persona_resumen(p)}
            for e, c, p in db.execute(
                select(Expediente, Caso, Persona)
                .join(Caso, Caso.id == Expediente.caso_id)
                .join(Persona, Persona.id == Expediente.persona_id)
                .where(del_area)
                .order_by(Expediente.creado_en.desc())
                .limit(10)
            ).all()
        ]
    documentos = [
        documento_out(d, True, ctx.usuario)
        for d in db.execute(
            select(Documento)
            .where(Documento.cargado_por == ctx.id, Documento.eliminado_en.is_(None))
            .order_by(Documento.cargado_en.desc())
            .limit(10)
        ).scalars()
    ]
    return {
        "area": db.get(Area, area_id).nombre if area_id else None,
        "casos": _casos(db, ctx, _base(ctx).where(del_area, _activos()).order_by(Caso.ultima_actividad.desc()).limit(15)),
        "expedientes": expedientes,
        "documentos": documentos,
        "pendientes_impresion": _contar(db, del_area, Caso.caratula_impresa_en.is_(None)),
    }


ARMADORES = {
    "direccion": _direccion,
    "jefatura": _jefatura,
    "tecnico": _tecnico,
    "carga": _carga,
    "mesa": _mesa,
    "administrativo_area": _administrativo_area,
}


@router.get("/inicio")
def inicio(
    perfil: str | None = Query(None),
    ctx: Contexto = Depends(contexto),
    db: Session = Depends(get_db),
):
    propios = perfiles_de(ctx.usuario)
    if not propios:
        return {"perfil": None, "perfiles": []}
    if perfil is None:
        perfil = propios[0]
    if perfil not in propios:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Ese inicio no corresponde a sus roles.")
    # Un rol sin permiso para consultar casos no ve bloques de casos.
    if perfil != "mesa" and not ctx.tiene("casos", "consultar"):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Su rol no permite consultar casos.")
    if perfil == "mesa":
        ctx.requerir("mesa_entrada", "consultar")
    datos = ARMADORES[perfil](db, ctx)
    return {
        "perfil": perfil,
        "perfiles": [{"codigo": p, "nombre": PERFILES[p]} for p in propios],
        "datos": datos,
    }

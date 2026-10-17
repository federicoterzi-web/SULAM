"""Buscador general, catálogos para formularios y consulta de auditoría."""

from __future__ import annotations

import uuid
from datetime import datetime

from fastapi import APIRouter, Depends, Query
from sqlalchemy import and_, or_, select
from sqlalchemy.orm import Session

from .. import audit
from ..db import get_db
from ..deps import contexto
from ..models import (
    Area,
    Auditoria,
    Caso,
    Expediente,
    Ingreso,
    Persona,
    TipoDocumental,
    TipoVinculo,
    Usuario,
)
from ..permissions import Contexto, filtro_casos, filtro_personas
from ..serializers import caso_out, expediente_out, ingreso_out, persona_resumen
from ..textutil import escapar_like, normalizar, normalizar_documento

router = APIRouter(tags=["general"])


@router.get("/buscar")
def buscar(
    q: str = Query(..., min_length=2, max_length=200),
    ctx: Contexto = Depends(contexto),
    db: Session = Depends(get_db),
):
    """Busca a la vez en legajos, casos, expedientes e ingresos, según permisos."""
    texto = normalizar(q)
    exacto = q.strip().upper()
    doc = normalizar_documento(q)
    resultado: dict[str, list] = {"personas": [], "casos": [], "expedientes": [], "ingresos": []}

    if ctx.tiene("personas", "consultar"):
        alcance = ctx.alcance("personas", "consultar")
        condiciones = [Persona.numero_legajo == exacto, Persona.legajo_provisorio == exacto]
        if doc:
            condiciones.append(Persona.numero_documento == doc)
        palabras = texto.split()
        if palabras:
            condiciones.append(
                and_(
                    *[
                        or_(
                            Persona.apellidos_norm.like("%" + escapar_like(p) + "%"),
                            Persona.nombres_norm.like("%" + escapar_like(p) + "%"),
                        )
                        for p in palabras
                    ]
                )
            )
        q_personas = (
            select(Persona)
            .where(Persona.unificada_en_id.is_(None), filtro_personas(ctx, alcance), or_(*condiciones))
            .order_by(Persona.apellidos_norm)
            .limit(25)
        )
        resultado["personas"] = [persona_resumen(p) for p in db.execute(q_personas).scalars()]

    if ctx.tiene("casos", "consultar"):
        alcance = ctx.alcance("casos", "consultar")
        q_casos = (
            select(Caso, Persona)
            .join(Persona, Persona.id == Caso.persona_id)
            .where(filtro_casos(ctx, alcance), Caso.numero.ilike("%" + escapar_like(exacto) + "%"))
            .limit(10)
        )
        resultado["casos"] = [
            caso_out(c, p) for c, p in db.execute(q_casos).all()
        ]

    if ctx.tiene("expedientes", "consultar"):
        alcance = ctx.alcance("expedientes", "consultar")
        q_exp = (
            select(Expediente, Persona)
            .join(Persona, Persona.id == Expediente.persona_id)
            .where(filtro_personas(ctx, alcance), Expediente.numero.ilike("%" + escapar_like(q.strip()) + "%"))
            .limit(10)
        )
        resultado["expedientes"] = [
            {**expediente_out(e), "persona": persona_resumen(p)}
            for e, p in db.execute(q_exp).all()
        ]

    if ctx.tiene("mesa_entrada", "consultar"):
        alcance = ctx.alcance("mesa_entrada", "consultar")
        q_ing = select(Ingreso).where(
            or_(
                Ingreso.numero.ilike("%" + escapar_like(exacto) + "%"),
                Ingreso.numero_expediente_externo.ilike("%" + escapar_like(q.strip()) + "%"),
            )
        )
        if alcance == "propios":
            q_ing = q_ing.where(Ingreso.creado_por == ctx.id)
        resultado["ingresos"] = [ingreso_out(i) for i in db.execute(q_ing.limit(10)).scalars()]

    audit.registrar(db, ctx, "busqueda", "general", detalle={"q": q[:200]})
    db.commit()
    return resultado


@router.get("/catalogos")
def catalogos(ctx: Contexto = Depends(contexto), db: Session = Depends(get_db)):
    r = {
        "areas": [
            {"id": a.id, "nombre": a.nombre}
            for a in db.execute(select(Area).where(Area.activo).order_by(Area.nombre)).scalars()
        ],
        "tipos_documentales": [
            {"id": t.id, "nombre": t.nombre}
            for t in db.execute(
                select(TipoDocumental).where(TipoDocumental.activo).order_by(TipoDocumental.orden, TipoDocumental.nombre)
            ).scalars()
        ],
        "tipos_vinculo": [
            {"id": t.id, "nombre": t.nombre}
            for t in db.execute(select(TipoVinculo).where(TipoVinculo.activo).order_by(TipoVinculo.nombre)).scalars()
        ],
        "usuarios_asignables": [],
    }
    if ctx.tiene("casos", "derivar") or ctx.tiene("casos", "crear"):
        r["usuarios_asignables"] = [
            {
                "id": str(u.id),
                "nombre_completo": u.nombre_completo,
                "area": u.area.nombre if u.area else None,
            }
            for u in db.execute(
                select(Usuario).where(Usuario.activo).order_by(Usuario.nombre_completo)
            ).scalars()
        ]
    return r


@router.get("/auditoria")
def consultar_auditoria(
    usuario_id: uuid.UUID | None = None,
    persona_id: uuid.UUID | None = None,
    entidad: str | None = None,
    accion: str | None = None,
    desde: datetime | None = None,
    hasta: datetime | None = None,
    limite: int = Query(200, ge=1, le=1000),
    ctx: Contexto = Depends(contexto),
    db: Session = Depends(get_db),
):
    ctx.requerir("auditoria", "consultar")
    q = select(Auditoria)
    if usuario_id:
        q = q.where(Auditoria.usuario_id == usuario_id)
    if persona_id:
        q = q.where(Auditoria.persona_id == persona_id)
    if entidad:
        q = q.where(Auditoria.entidad == entidad)
    if accion:
        q = q.where(Auditoria.accion == accion)
    if desde:
        q = q.where(Auditoria.en >= desde)
    if hasta:
        q = q.where(Auditoria.en <= hasta)
    filas = db.execute(q.order_by(Auditoria.en.desc(), Auditoria.id.desc()).limit(limite)).scalars().all()
    audit.registrar(
        db, ctx, "consultar_auditoria", "auditoria",
        detalle={k: v for k, v in {"usuario_id": usuario_id, "persona_id": persona_id, "entidad": entidad, "accion": accion}.items() if v},
    )
    db.commit()
    return [
        {
            "id": a.id,
            "en": a.en.isoformat(),
            "usuario": a.usuario.nombre_completo if a.usuario else "Sistema",
            "usuario_id": str(a.usuario_id) if a.usuario_id else None,
            "accion": a.accion,
            "entidad": a.entidad,
            "entidad_id": a.entidad_id,
            "persona_id": str(a.persona_id) if a.persona_id else None,
            "detalle": a.detalle,
            "ip": a.ip,
        }
        for a in filas
    ]

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from .. import audit
from ..db import get_db
from ..deps import contexto
from ..models import Expediente, Persona
from ..permissions import Contexto, filtro_personas, requerir_persona
from ..schemas import ExpedienteIn, ExpedientePatch
from ..serializers import expediente_out, persona_resumen
from ..textutil import escapar_like
from ._comun import (
    obtener_expediente,
    obtener_persona,
    registrar_actividad_caso,
    validar_pertenencia,
)

router = APIRouter(tags=["expedientes"])


@router.get("/expedientes")
def listar_expedientes(
    q: str = Query("", max_length=100),
    limite: int = Query(50, ge=1, le=200),
    ctx: Contexto = Depends(contexto),
    db: Session = Depends(get_db),
):
    alcance = ctx.requerir("expedientes", "consultar")
    consulta = (
        select(Expediente, Persona)
        .join(Persona, Persona.id == Expediente.persona_id)
        .where(filtro_personas(ctx, alcance))
    )
    if q.strip():
        consulta = consulta.where(Expediente.numero.ilike("%" + escapar_like(q.strip()) + "%"))
    consulta = consulta.order_by(Expediente.creado_en.desc()).limit(limite)
    return [
        {**expediente_out(e), "persona": persona_resumen(p)}
        for e, p in db.execute(consulta).all()
    ]


@router.post("/expedientes", status_code=201)
def crear_expediente(datos: ExpedienteIn, ctx: Contexto = Depends(contexto), db: Session = Depends(get_db)):
    persona = obtener_persona(db, datos.persona_id)
    requerir_persona(db, ctx, persona, "expedientes", "crear")
    caso, _ = validar_pertenencia(db, persona.id, datos.caso_id, None)
    exp = Expediente(**datos.model_dump(), creado_por=ctx.id)
    db.add(exp)
    db.flush()
    if caso:
        registrar_actividad_caso(caso)
    audit.registrar(
        db, ctx, "crear", "expediente", exp.id, persona.id,
        {"numero": exp.numero, "tipo": exp.tipo, "caso_id": exp.caso_id},
    )
    db.commit()
    return expediente_out(exp)


@router.get("/expedientes/{expediente_id}")
def ver_expediente(expediente_id: uuid.UUID, ctx: Contexto = Depends(contexto), db: Session = Depends(get_db)):
    exp = obtener_expediente(db, expediente_id)
    persona = db.get(Persona, exp.persona_id)
    requerir_persona(db, ctx, persona, "expedientes", "consultar")
    return {**expediente_out(exp), "persona": persona_resumen(persona)}


@router.patch("/expedientes/{expediente_id}")
def modificar_expediente(
    expediente_id: uuid.UUID,
    datos: ExpedientePatch,
    ctx: Contexto = Depends(contexto),
    db: Session = Depends(get_db),
):
    exp = obtener_expediente(db, expediente_id)
    persona = db.get(Persona, exp.persona_id)
    requerir_persona(db, ctx, persona, "expedientes", "modificar")
    cambios_pedidos = datos.model_dump(exclude_unset=True)
    if "caso_id" in cambios_pedidos:
        validar_pertenencia(db, persona.id, cambios_pedidos["caso_id"], None)
    diff = audit.cambios(exp, cambios_pedidos)
    if diff:
        audit.registrar(db, ctx, "modificar", "expediente", exp.id, persona.id, {"cambios": diff})
        db.commit()
    return expediente_out(exp)

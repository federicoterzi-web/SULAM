"""Mesa de Entrada: registro de ingresos, aun sin legajo, y su vinculación posterior."""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import or_, select, true
from sqlalchemy.orm import Session

from .. import audit
from ..db import get_db
from ..deps import contexto
from ..models import Documento, Ingreso, Persona, TipoDocumental, Usuario
from ..numbering import numero_ingreso
from ..permissions import Contexto, filtro_personas, requerir_persona
from ..schemas import IngresoIn, VincularIngresoIn
from ..security import ahora
from ..serializers import documento_out, ingreso_out, persona_resumen
from ..textutil import escapar_like, normalizar, normalizar_documento
from ._comun import (
    no_encontrado,
    obtener_persona,
    registrar_actividad_caso,
    validar_pertenencia,
    ve_documento,
)

router = APIRouter(tags=["mesa de entrada"])


def _filtro_alcance(ctx: Contexto, alcance: str):
    # En Mesa de Entrada: "propios" limita a lo registrado por el usuario;
    # cualquier alcance mayor permite ver todos los ingresos.
    return Ingreso.creado_por == ctx.id if alcance == "propios" else true()


def _obtener(db: Session, ctx: Contexto, ingreso_id: uuid.UUID, accion: str) -> Ingreso:
    alcance = ctx.requerir("mesa_entrada", accion)
    ingreso = db.get(Ingreso, ingreso_id)
    if ingreso is None:
        raise no_encontrado("Ingreso")
    if alcance == "propios" and ingreso.creado_por != ctx.id:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "El ingreso está fuera de su alcance.")
    return ingreso


@router.get("/ingresos")
def listar_ingresos(
    pendientes: bool = False,
    q: str = Query("", max_length=200),
    limite: int = Query(50, ge=1, le=200),
    ctx: Contexto = Depends(contexto),
    db: Session = Depends(get_db),
):
    alcance = ctx.requerir("mesa_entrada", "consultar")
    consulta = select(Ingreso).where(_filtro_alcance(ctx, alcance))
    if pendientes:
        consulta = consulta.where(Ingreso.persona_id.is_(None))
    if q.strip():
        patron = "%" + escapar_like(q.strip()) + "%"
        consulta = consulta.where(
            or_(
                Ingreso.numero.ilike(patron),
                Ingreso.asunto.ilike(patron),
                Ingreso.remitente.ilike(patron),
                Ingreso.persona_mencionada.ilike(patron),
                Ingreso.numero_expediente_externo.ilike(patron),
            )
        )
    consulta = consulta.order_by(Ingreso.fecha_ingreso.desc()).limit(limite)
    ingresos = list(db.execute(consulta).scalars())
    personas = {
        p.id: p
        for p in db.execute(
            select(Persona).where(Persona.id.in_([i.persona_id for i in ingresos if i.persona_id]))
        ).scalars()
    }
    return [ingreso_out(i, personas.get(i.persona_id)) for i in ingresos]


@router.post("/ingresos", status_code=201)
def crear_ingreso(datos: IngresoIn, ctx: Contexto = Depends(contexto), db: Session = Depends(get_db)):
    ctx.requerir("mesa_entrada", "crear")
    if datos.tipo_documental_id is not None and db.get(TipoDocumental, datos.tipo_documental_id) is None:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Tipo documental inválido.")
    valores = datos.model_dump(exclude_none=True)
    valores["documento_mencionado"] = normalizar_documento(datos.documento_mencionado)
    ingreso = Ingreso(**valores, numero=numero_ingreso(db), creado_por=ctx.id)
    persona = None
    if datos.persona_id is not None:
        persona = obtener_persona(db, datos.persona_id)
        ingreso.vinculado_por = ctx.id
        ingreso.vinculado_en = ahora()
    db.add(ingreso)
    db.flush()
    db.refresh(ingreso)
    audit.registrar(
        db, ctx, "crear", "ingreso", ingreso.id, ingreso.persona_id,
        {"numero": ingreso.numero, "asunto": ingreso.asunto[:200]},
    )
    db.commit()
    return ingreso_out(ingreso, persona)


@router.get("/ingresos/{ingreso_id}")
def ver_ingreso(ingreso_id: uuid.UUID, ctx: Contexto = Depends(contexto), db: Session = Depends(get_db)):
    ingreso = _obtener(db, ctx, ingreso_id, "consultar")
    persona = db.get(Persona, ingreso.persona_id) if ingreso.persona_id else None
    r = ingreso_out(ingreso, persona)

    q = (
        select(Documento, Usuario)
        .outerjoin(Usuario, Usuario.id == Documento.cargado_por)
        .where(Documento.ingreso_id == ingreso.id, Documento.eliminado_en.is_(None))
    )
    r["documentos"] = [documento_out(d, ve_documento(db, ctx, d), u) for d, u in db.execute(q).all()]

    # Legajos sugeridos para vincular, según los datos mencionados en el ingreso.
    r["sugerencias"] = []
    if ingreso.persona_id is None and ctx.tiene("personas", "consultar"):
        alcance = ctx.alcance("personas", "consultar")
        condiciones = []
        if ingreso.documento_mencionado:
            condiciones.append(Persona.numero_documento == ingreso.documento_mencionado)
        palabras = [p for p in normalizar(ingreso.persona_mencionada).split() if len(p) >= 3]
        if palabras:
            condiciones.append(
                or_(*[Persona.apellidos_norm.like("%" + escapar_like(p) + "%") for p in palabras])
            )
        if condiciones:
            sugeridas = db.execute(
                select(Persona)
                .where(Persona.unificada_en_id.is_(None), filtro_personas(ctx, alcance), or_(*condiciones))
                .limit(10)
            ).scalars()
            r["sugerencias"] = [persona_resumen(p) for p in sugeridas]

    audit.registrar(db, ctx, "consultar_ingreso", "ingreso", ingreso.id, ingreso.persona_id)
    db.commit()
    return r


@router.post("/ingresos/{ingreso_id}/vincular")
def vincular_ingreso(
    ingreso_id: uuid.UUID,
    datos: VincularIngresoIn,
    ctx: Contexto = Depends(contexto),
    db: Session = Depends(get_db),
):
    """Asocia un ingreso (y sus documentos) a un legajo. Los datos originales
    del ingreso no se modifican: se conserva el registro de origen."""
    ingreso = _obtener(db, ctx, ingreso_id, "modificar")
    persona = obtener_persona(db, datos.persona_id)
    requerir_persona(db, ctx, persona, "personas", "consultar")
    caso, exp = validar_pertenencia(db, persona.id, datos.caso_id, datos.expediente_id)

    anterior = {
        "persona_id": ingreso.persona_id,
        "caso_id": ingreso.caso_id,
        "expediente_id": ingreso.expediente_id,
    }
    ingreso.persona_id = persona.id
    ingreso.caso_id = caso.id if caso else None
    ingreso.expediente_id = exp.id if exp else None
    ingreso.vinculado_por = ctx.id
    ingreso.vinculado_en = ahora()
    if caso:
        registrar_actividad_caso(caso)

    docs = db.execute(select(Documento).where(Documento.ingreso_id == ingreso.id)).scalars().all()
    for d in docs:
        d.persona_id = persona.id
        d.caso_id = caso.id if caso else d.caso_id
        d.expediente_id = exp.id if exp else d.expediente_id

    audit.registrar(
        db, ctx, "vincular", "ingreso", ingreso.id, persona.id,
        {
            "legajo": persona.numero_legajo,
            "caso_id": ingreso.caso_id,
            "expediente_id": ingreso.expediente_id,
            "anterior": anterior,
            "documentos": len(docs),
        },
    )
    db.commit()
    db.refresh(ingreso)
    return ingreso_out(ingreso, persona)

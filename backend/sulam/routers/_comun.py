from __future__ import annotations

import uuid

from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from ..models import Caso, Expediente, Persona
from ..security import ahora


def no_encontrado(que: str) -> HTTPException:
    return HTTPException(status.HTTP_404_NOT_FOUND, f"{que} inexistente.")


def obtener_persona(db: Session, persona_id: uuid.UUID, permitir_unificada: bool = False) -> Persona:
    persona = db.get(Persona, persona_id)
    if persona is None:
        raise no_encontrado("Legajo")
    if persona.unificada_en_id and not permitir_unificada:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            {
                "mensaje": "Este legajo fue unificado con otro.",
                "unificada_en_id": str(persona.unificada_en_id),
            },
        )
    return persona


def obtener_caso(db: Session, caso_id: uuid.UUID) -> Caso:
    caso = db.get(Caso, caso_id)
    if caso is None:
        raise no_encontrado("Caso")
    return caso


def obtener_expediente(db: Session, expediente_id: uuid.UUID) -> Expediente:
    exp = db.get(Expediente, expediente_id)
    if exp is None:
        raise no_encontrado("Expediente")
    return exp


def registrar_actividad_caso(caso: Caso) -> None:
    caso.ultima_actividad = ahora()


def validar_pertenencia(
    db: Session, persona_id: uuid.UUID, caso_id: uuid.UUID | None, expediente_id: uuid.UUID | None
) -> tuple[Caso | None, Expediente | None]:
    caso = exp = None
    if caso_id is not None:
        caso = obtener_caso(db, caso_id)
        if caso.persona_id != persona_id:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, "El caso no pertenece a este legajo.")
    if expediente_id is not None:
        exp = obtener_expediente(db, expediente_id)
        if exp.persona_id != persona_id:
            raise HTTPException(
                status.HTTP_400_BAD_REQUEST, "El expediente no pertenece a este legajo."
            )
    return caso, exp


def ve_documento(db: Session, ctx, d) -> bool:
    """Un documento es visible si su caso (si tiene) es visible y, cuando es
    reservado por sí o por su tipo, si el usuario puede ver lo reservado."""
    from ..permissions import ve_caso_reservado, ve_reservado_de_persona

    if d.caso_id is not None:
        caso = db.get(Caso, d.caso_id)
        if caso is not None and not ve_caso_reservado(db, ctx, caso):
            return False
    if d.reservado or d.tipo_documental.reservado:
        if d.persona_id is None:
            return ctx.tiene("reservados", "consultar")
        return ve_reservado_de_persona(db, ctx, d.persona_id, d.caso_id)
    return True


def ve_expediente(db: Session, ctx, e) -> bool:
    """La carátula de un expediente vinculado a un caso reservado es reservada."""
    from ..permissions import ve_caso_reservado

    if e.caso_id is None:
        return True
    caso = db.get(Caso, e.caso_id)
    return caso is None or ve_caso_reservado(db, ctx, caso)

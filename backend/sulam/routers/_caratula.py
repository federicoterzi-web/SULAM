"""Reglas compartidas de la carátula de legajo."""

from __future__ import annotations

import uuid
from datetime import date

from sqlalchemy import select
from sqlalchemy.orm import Session

from .. import audit
from ..formularios import validar_datos_persona, validar_ingreso, validar_motivo_consulta
from ..models import Caso, Persona
from ..permissions import Contexto, requerir_persona


def antecedentes_sistema(
    db: Session, persona_id: uuid.UUID, excluir_caso_id: uuid.UUID | None = None, antes_de: date | None = None
) -> tuple[bool, date | None]:
    """Si la persona tuvo otros casos en SULAM y la fecha de ingreso del más reciente."""
    q = select(Caso).where(Caso.persona_id == persona_id)
    if excluir_caso_id is not None:
        q = q.where(Caso.id != excluir_caso_id)
    fechas = []
    for c in db.execute(q).scalars():
        f = c.fecha_ingreso or c.abierto_en.date()
        if antes_de is None or f <= antes_de:
            fechas.append(f)
    return (bool(fechas), max(fechas) if fechas else None)


def aplicar_caratula(db: Session, ctx: Contexto, caso: Caso, persona: Persona, datos: dict) -> dict:
    """Aplica los campos de carátula al caso (y los datos personales al legajo).

    Devuelve el diff del caso; el cambio en el legajo se audita aparte.
    """
    datos = dict(datos)
    datos_persona = datos.pop("persona", None)
    if "tipo_ingreso" in datos and "tipo_ingreso_detalle" not in datos and datos["tipo_ingreso"] != caso.tipo_ingreso:
        datos["tipo_ingreso_detalle"] = None
    validar_ingreso({**{"tipo_ingreso": caso.tipo_ingreso, "tipo_ingreso_detalle": caso.tipo_ingreso_detalle}, **datos})
    validar_motivo_consulta(datos)
    diff = audit.cambios(caso, datos)

    if datos_persona:
        validar_datos_persona(datos_persona)
        cambios_persona = {k: v for k, v in datos_persona.items() if getattr(persona, k) != v}
        if cambios_persona:
            requerir_persona(db, ctx, persona, "personas", "modificar")
            diff_p = audit.cambios(persona, cambios_persona)
            audit.registrar(
                db, ctx, "modificar", "persona", persona.id, persona.id,
                {"cambios": diff_p, "origen": f"carátula del caso {caso.numero}"},
            )
    return diff

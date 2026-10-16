"""Registro de demanda: se carga sobre un caso que ya tiene carátula."""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from .. import audit
from ..db import get_db
from ..deps import contexto
from ..formularios import catalogo_formularios, validar_demanda
from ..models import Caso, Persona, RegistroDemanda, Usuario
from ..permissions import Contexto, requerir_caso, ve_caso_reservado
from ..schemas import DemandaIn
from ..security import ahora
from ..serializers import demanda_out
from ._comun import no_encontrado, obtener_caso, registrar_actividad_caso

router = APIRouter(tags=["registro de demanda"])

# Campos del registro que también existen en el legajo y se mantienen al día.
CAMPOS_LEGAJO = (
    "genero", "telefono", "domicilio", "barrio", "localidad", "departamento", "cud",
    "cobertura_salud", "obra_social", "cobertura_previsional", "trabajo_informal", "discapacidades",
)
# Campos que vienen de la carátula del caso.
CAMPOS_CARATULA = (
    "indicadores", "intervenciones", "intervencion_otro", "tipo_ingreso", "tipo_ingreso_detalle",
    "derivado_por", "derivado_por_detalle",
)


def _datos_persona(p: Persona) -> dict:
    """Copia de los datos de identificación al momento del registro (sección 2)."""
    return {
        "numero_legajo": p.numero_legajo,
        "apellidos": p.apellidos,
        "nombres": p.nombres,
        "tipo_documento": p.tipo_documento,
        "numero_documento": p.numero_documento,
        "fecha_nacimiento": p.fecha_nacimiento.isoformat() if p.fecha_nacimiento else None,
        "genero": p.genero,
        "telefono": p.telefono,
    }


@router.get("/formularios")
def formularios(ctx: Contexto = Depends(contexto)):
    """Opciones de los formularios institucionales (carátula y registro de demanda)."""
    return catalogo_formularios()


@router.get("/casos/{caso_id}/demanda-sugerida")
def demanda_sugerida(caso_id: uuid.UUID, ctx: Contexto = Depends(contexto), db: Session = Depends(get_db)):
    """Valores iniciales del registro, tomados del legajo y de la carátula."""
    caso = obtener_caso(db, caso_id)
    requerir_caso(db, ctx, caso, "casos", "modificar")
    if not ve_caso_reservado(db, ctx, caso):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Caso reservado.")
    persona = db.get(Persona, caso.persona_id)
    sugerido: dict = {k: getattr(persona, k) for k in CAMPOS_LEGAJO}
    sugerido.update({k: getattr(caso, k) for k in CAMPOS_CARATULA})
    sugerido["solicitud_expresa"] = caso.motivo
    responsables = [a.usuario_id for a in caso.asignaciones if a.hasta is None]
    sugerido["agente_id"] = str(responsables[0]) if responsables else None
    sugerido["lugar"] = "San Miguel de Tucumán"
    sugerido["fecha"] = ahora().astimezone().date().isoformat()
    for k in ("cobertura_salud", "cobertura_previsional", "discapacidades", "indicadores", "intervenciones"):
        sugerido[k] = sugerido.get(k) or []
    return sugerido


def _aplicar(db: Session, ctx: Contexto, reg: RegistroDemanda, persona: Persona, datos: dict) -> dict:
    actualizar_legajo = datos.pop("actualizar_legajo", True)
    validar_demanda(datos)
    if datos.get("agente_id") is not None:
        agente = db.get(Usuario, datos["agente_id"])
        if agente is None:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, "Agente a cargo inexistente.")
    genero = datos.pop("genero", None) if "genero" in datos else None
    telefono = datos.pop("telefono", None) if "telefono" in datos else None
    diff = audit.cambios(reg, datos)

    if actualizar_legajo:
        para_legajo = {k: datos[k] for k in CAMPOS_LEGAJO if k in datos and datos[k] not in (None, [], "")}
        if genero:
            para_legajo["genero"] = genero
        if telefono:
            para_legajo["telefono"] = telefono
        cambios_legajo = {k: v for k, v in para_legajo.items() if getattr(persona, k) != v}
        if cambios_legajo:
            diff_p = audit.cambios(persona, cambios_legajo)
            audit.registrar(
                db, ctx, "modificar", "persona", persona.id, persona.id,
                {"cambios": diff_p, "origen": "registro de demanda"},
            )
    reg.datos_persona = _datos_persona(persona)
    return diff


@router.post("/casos/{caso_id}/demandas", status_code=201)
def crear_demanda(
    caso_id: uuid.UUID, datos: DemandaIn, ctx: Contexto = Depends(contexto), db: Session = Depends(get_db)
):
    caso = obtener_caso(db, caso_id)
    requerir_caso(db, ctx, caso, "casos", "modificar")
    if not ve_caso_reservado(db, ctx, caso):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Caso reservado.")
    persona = db.get(Persona, caso.persona_id)
    valores = datos.model_dump()
    reg = RegistroDemanda(
        caso_id=caso.id,
        persona_id=persona.id,
        fecha=valores.pop("fecha") or ahora().astimezone().date(),
        creado_por=ctx.id,
    )
    db.add(reg)
    _aplicar(db, ctx, reg, persona, valores)
    registrar_actividad_caso(caso)
    db.flush()
    audit.registrar(db, ctx, "crear", "registro_demanda", reg.id, persona.id, {"caso": caso.numero})
    db.commit()
    db.refresh(reg)
    return demanda_out(reg)


def _obtener(db: Session, ctx: Contexto, demanda_id: uuid.UUID, accion: str) -> tuple[RegistroDemanda, Caso]:
    reg = db.get(RegistroDemanda, demanda_id)
    if reg is None:
        raise no_encontrado("Registro de demanda")
    caso = db.get(Caso, reg.caso_id)
    requerir_caso(db, ctx, caso, "casos", accion)
    if not ve_caso_reservado(db, ctx, caso):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Registro de un caso reservado.")
    return reg, caso


@router.get("/demandas/{demanda_id}")
def ver_demanda(demanda_id: uuid.UUID, ctx: Contexto = Depends(contexto), db: Session = Depends(get_db)):
    reg, caso = _obtener(db, ctx, demanda_id, "consultar")
    audit.registrar(db, ctx, "consultar_demanda", "registro_demanda", reg.id, reg.persona_id)
    db.commit()
    return {**demanda_out(reg), "caso_numero": caso.numero}


@router.patch("/demandas/{demanda_id}")
def modificar_demanda(
    demanda_id: uuid.UUID, datos: DemandaIn, ctx: Contexto = Depends(contexto), db: Session = Depends(get_db)
):
    reg, caso = _obtener(db, ctx, demanda_id, "modificar")
    persona = db.get(Persona, reg.persona_id)
    valores = datos.model_dump(exclude_unset=True)
    if "fecha" in valores and valores["fecha"] is None:
        valores.pop("fecha")
    diff = _aplicar(db, ctx, reg, persona, valores)
    if diff:
        registrar_actividad_caso(caso)
        audit.registrar(db, ctx, "modificar", "registro_demanda", reg.id, reg.persona_id, {"campos": sorted(diff)})
    db.commit()
    db.refresh(reg)
    return demanda_out(reg)

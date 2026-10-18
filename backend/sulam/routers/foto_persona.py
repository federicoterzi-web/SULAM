"""Foto de la persona (recortada del DNI) y documentación del legajo (lo que hay y lo que falta en un caso abierto)."""

from __future__ import annotations

import io
import uuid
from datetime import date

from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.responses import Response
from pydantic import BaseModel, Field
from PIL import Image
from sqlalchemy import select
from sqlalchemy.orm import Session

from .. import audit, foto_dni, indexacion
from ..db import get_db
from ..deps import contexto
from ..models import Caso, Documento, Subsidio, SubsidioRequisito, TipoDocumental
from ..permissions import Contexto, requerir_persona
from ..schemas import Entrada
from ..security import ahora
from ._comun import no_encontrado, obtener_persona
from .documentos import _bytes_del_archivo, _verificar_acceso

router = APIRouter(tags=["documentos"])

HOJAS_A_REVISAR = 4


class Caja(BaseModel):
    x: float = Field(ge=0, le=1)
    y: float = Field(ge=0, le=1)
    w: float = Field(gt=0, le=1)
    h: float = Field(gt=0, le=1)


class FotoIn(Entrada):
    documento_id: uuid.UUID
    hoja: int = Field(default=1, ge=1, le=50)
    caja: Caja


def _documento_de(db: Session, ctx: Contexto, persona_id: uuid.UUID, documento_id: uuid.UUID) -> Documento:
    d = db.get(Documento, documento_id)
    if d is None or d.persona_id != persona_id:
        raise no_encontrado("Documento")
    _verificar_acceso(db, ctx, d, "descargar")
    return d


def _imagen(d: Documento, hoja: int) -> Image.Image:
    r = indexacion.imagen_de_hoja(_bytes_del_archivo(d), d.mime, hoja)
    if r is None:
        raise no_encontrado("Hoja")
    return Image.open(io.BytesIO(r[0])).convert("RGB")


@router.get("/personas/{persona_id}/foto")
def ver_foto(persona_id: uuid.UUID, ctx: Contexto = Depends(contexto), db: Session = Depends(get_db)):
    persona = obtener_persona(db, persona_id, permitir_unificada=True)
    requerir_persona(db, ctx, persona, "personas", "consultar")
    if persona.foto is None:
        raise no_encontrado("Foto")
    return Response(persona.foto, media_type="image/jpeg", headers={"Cache-Control": "private, no-store"})


@router.get("/personas/{persona_id}/foto/sugerencia")
def sugerir_foto(
    persona_id: uuid.UUID,
    documento_id: uuid.UUID,
    hoja: int | None = Query(None, ge=1, le=50),
    ctx: Contexto = Depends(contexto),
    db: Session = Depends(get_db),
):
    """Busca la cara en el documento y devuelve el recorte sugerido (en fracción de la hoja), o ninguno."""
    persona = obtener_persona(db, persona_id)
    requerir_persona(db, ctx, persona, "personas", "modificar")
    d = _documento_de(db, ctx, persona.id, documento_id)
    total = indexacion.cantidad_de_hojas(_bytes_del_archivo(d), d.mime)
    if total == 0:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Este archivo no se puede mostrar como imagen.")
    candidatas = [hoja] if hoja else list(range(1, min(total, HOJAS_A_REVISAR) + 1))
    mejor = None
    for n in candidatas:
        caja = foto_dni.sugerir_recorte(_imagen(d, n))
        if caja and (mejor is None or caja["w"] * caja["h"] > mejor[1]["w"] * mejor[1]["h"]):
            mejor = (n, caja)
    return {
        "hojas": total,
        "hoja": mejor[0] if mejor else (hoja or 1),
        "caja": mejor[1] if mejor else None,
        "deteccion_disponible": foto_dni.disponible(),
    }


@router.put("/personas/{persona_id}/foto")
def guardar_foto(persona_id: uuid.UUID, datos: FotoIn, ctx: Contexto = Depends(contexto), db: Session = Depends(get_db)):
    persona = obtener_persona(db, persona_id)
    requerir_persona(db, ctx, persona, "personas", "modificar")
    d = _documento_de(db, ctx, persona.id, datos.documento_id)
    try:
        jpeg = foto_dni.recortar(_imagen(d, datos.hoja), datos.caja.model_dump())
    except ValueError as e:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(e))
    persona.foto = jpeg
    persona.foto_en = ahora()
    persona.foto_por = ctx.id
    persona.foto_documento_id = d.id
    audit.registrar(db, ctx, "foto_persona", "persona", persona.id, persona.id, {"documento_id": str(d.id), "hoja": datos.hoja})
    db.commit()
    return {"tiene_foto": True, "foto_en": persona.foto_en.isoformat()}


@router.delete("/personas/{persona_id}/foto", status_code=204)
def quitar_foto(persona_id: uuid.UUID, ctx: Contexto = Depends(contexto), db: Session = Depends(get_db)):
    persona = obtener_persona(db, persona_id)
    requerir_persona(db, ctx, persona, "personas", "modificar")
    if persona.foto is not None:
        persona.foto = persona.foto_en = persona.foto_por = persona.foto_documento_id = None
        audit.registrar(db, ctx, "quitar_foto_persona", "persona", persona.id, persona.id)
        db.commit()
    return Response(status_code=204)


@router.get("/personas/{persona_id}/documentacion")
def documentacion(persona_id: uuid.UUID, ctx: Contexto = Depends(contexto), db: Session = Depends(get_db)):
    """Qué documentos hay en el legajo y, si tiene un caso abierto, cuáles de los requeridos faltan."""
    persona = obtener_persona(db, persona_id)
    requerir_persona(db, ctx, persona, "documentos", "consultar")
    hoy = date.today()
    abiertos = db.execute(select(Caso.id).where(Caso.persona_id == persona.id, Caso.estado != "cerrado")).scalars().all()
    documentos = db.execute(
        select(Documento).where(Documento.persona_id == persona.id, Documento.eliminado_en.is_(None)).order_by(Documento.cargado_en.desc())
    ).scalars().all()
    por_tipo: dict[int, list[Documento]] = {}
    for d in documentos:
        por_tipo.setdefault(d.tipo_documental_id, []).append(d)

    def vigente(d: Documento) -> bool:
        return d.vence is None or d.vence >= hoy

    requeridos = []
    for t in db.execute(select(TipoDocumental).where(TipoDocumental.activo, TipoDocumental.requerido_en_caso_abierto).order_by(TipoDocumental.orden, TipoDocumental.nombre)).scalars():
        docs = por_tipo.get(t.id, [])
        elegido = next((d for d in docs if vigente(d)), docs[0] if docs else None)
        estado = "falta" if elegido is None else ("presente" if vigente(elegido) else "vencido")
        requeridos.append({
            "tipo_id": t.id, "nombre": t.nombre, "estado": estado,
            "documento_id": str(elegido.id) if elegido else None,
            "fecha": elegido.cargado_en.date().isoformat() if elegido else None,
            "vence": elegido.vence.isoformat() if elegido and elegido.vence else None,
        })
    presentes = []
    for t in db.execute(select(TipoDocumental).where(TipoDocumental.id.in_(list(por_tipo) or [0])).order_by(TipoDocumental.orden, TipoDocumental.nombre)).scalars():
        docs = por_tipo[t.id]
        presentes.append({"tipo_id": t.id, "nombre": t.nombre, "cantidad": len(docs), "ultimo": docs[0].cargado_en.date().isoformat()})

    pendientes_subsidio = None
    if ctx.tiene("subsidios", "consultar"):
        pendientes_subsidio = len(
            db.execute(
                select(SubsidioRequisito.id)
                .join(Subsidio, Subsidio.id == SubsidioRequisito.subsidio_id)
                .where(Subsidio.persona_id == persona.id, Subsidio.estado.in_(("en_tramite", "elevado")), SubsidioRequisito.pago_id.is_(None), SubsidioRequisito.estado == "pendiente")
            ).all()
        )
    return {
        "caso_abierto": bool(abiertos),
        "casos_abiertos": len(abiertos),
        "requeridos": requeridos,
        "faltan": sum(1 for r in requeridos if r["estado"] != "presente"),
        "presentes": presentes,
        "subsidios_pendientes": pendientes_subsidio,
    }

"""Certificación negativa de ANSES en el legajo (ver sulam/anses.py).

- Consultar: quien puede consultar el legajo.
- Registrar una negativa: quien puede cargar documentos en el legajo.
"""

from __future__ import annotations

import io
import re
import uuid
from datetime import date, timedelta

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from .. import audit
from ..anses import RESULTADOS, cuil_sugeridos, cuil_valido, estado, formatear, hoy_local, leer_negativa, texto_de_pdf
from ..config import get_settings
from ..db import get_db
from ..deps import contexto
from ..models import Constancia, Persona, TipoDocumental
from ..permissions import Contexto, persona_en_alcance, requerir_persona
from ..serializers import usuario_breve
from ._comun import obtener_persona, validar_pertenencia
from .documentos import cargar_documento

router = APIRouter(tags=["anses"])

MAX_PDF = 5 * 1024 * 1024
TIPO = "negativa_anses"


def constancia_out(c: Constancia, hoy: date | None = None) -> dict:
    return {
        "id": c.id,
        "cuil": c.cuil,
        "fecha_emision": c.fecha_emision.isoformat(),
        "vence": c.vence.isoformat() if c.vence else None,
        "estado": estado(c.vence, hoy) if c.resultado != "no_emitida" else "no_emitida",
        "resultado": c.resultado,
        "resultado_texto": RESULTADOS[c.resultado],
        "detalle": c.detalle,
        "codigo_validacion": c.codigo_validacion,
        "documento_id": str(c.documento_id) if c.documento_id else None,
        "origen": c.origen,
        "observaciones": c.observaciones,
        "usuario": usuario_breve(c.usuario),
        "en": c.en.isoformat(),
    }


def ultima_negativa(db: Session, persona_id: uuid.UUID) -> Constancia | None:
    return db.execute(
        select(Constancia)
        .where(Constancia.persona_id == persona_id, Constancia.tipo == TIPO)
        .order_by(Constancia.fecha_emision.desc(), Constancia.en.desc())
    ).scalars().first()


def resumen_negativa(db: Session, persona_id: uuid.UUID) -> dict | None:
    c = ultima_negativa(db, persona_id)
    return constancia_out(c) if c else None


def _dni(p: Persona) -> str | None:
    if p.sin_documento or not p.numero_documento:
        return None
    d = re.sub(r"\D", "", p.numero_documento)
    return d if 6 <= len(d) <= 8 else None


def _cuil_coincide(cuil: str, p: Persona) -> bool | None:
    """¿El CUIL corresponde al DNI del legajo? None si el legajo no tiene DNI."""
    dni = _dni(p)
    if dni is None:
        return None
    return re.sub(r"\D", "", cuil)[2:10] == dni.zfill(8)


@router.get("/personas/{persona_id}/negativa-anses")
def ver_negativa(persona_id: uuid.UUID, ctx: Contexto = Depends(contexto), db: Session = Depends(get_db)):
    p = obtener_persona(db, persona_id)
    requerir_persona(db, ctx, p, "personas", "consultar")
    cfg = get_settings()
    historial = db.execute(
        select(Constancia)
        .where(Constancia.persona_id == p.id, Constancia.tipo == TIPO)
        .order_by(Constancia.fecha_emision.desc(), Constancia.en.desc())
    ).scalars().all()
    alc = ctx.alcance("documentos", "crear")
    return {
        "cuil": p.cuil,
        "cuil_sugeridos": [] if p.cuil else cuil_sugeridos(_dni(p), p.genero),
        "genero_conocido": p.genero in ("F", "M"),
        "url_anses": cfg.url_negativa_anses,
        "dias_vigencia": cfg.dias_vigencia_negativa,
        "ultima": constancia_out(historial[0]) if historial else None,
        "historial": [constancia_out(c) for c in historial],
        "puede_registrar": alc is not None and persona_en_alcance(db, ctx, p, alc),
    }


@router.post("/personas/{persona_id}/negativa-anses/leer")
def leer_pdf(
    persona_id: uuid.UUID,
    archivo: UploadFile = File(...),
    ctx: Contexto = Depends(contexto),
    db: Session = Depends(get_db),
):
    """Lee el PDF descargado de ANSES y propone los datos. No guarda nada."""
    p = obtener_persona(db, persona_id)
    requerir_persona(db, ctx, p, "documentos", "crear")
    contenido = archivo.file.read(MAX_PDF + 1)
    if len(contenido) > MAX_PDF:
        raise HTTPException(status.HTTP_413_REQUEST_ENTITY_TOO_LARGE, "El PDF es demasiado grande para una negativa.")
    if not contenido.startswith(b"%PDF"):
        raise HTTPException(status.HTTP_415_UNSUPPORTED_MEDIA_TYPE, "Elija el PDF que descargó de ANSES.")
    try:
        texto = texto_de_pdf(contenido)
    except Exception:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "No se pudo leer el PDF. ¿Está completo?")
    hoy = hoy_local()
    lectura = leer_negativa(texto, hoy)
    # El CUIL del PDF que corresponde a este legajo (si hay varios, el que coincide con el DNI).
    cuil = next((c for c in lectura["cuiles"] if _cuil_coincide(c, p)), None) or (lectura["cuiles"][0] if lectura["cuiles"] else None)
    coincide = _cuil_coincide(cuil, p) if cuil else None
    if cuil and p.cuil and formatear(p.cuil) != cuil:
        lectura["avisos"].insert(0, f"El CUIL del PDF ({cuil}) no es el del legajo ({p.cuil}). ¿Es la negativa de otra persona?")
    elif cuil and coincide is False:
        lectura["avisos"].insert(0, f"El CUIL del PDF ({cuil}) no corresponde al DNI del legajo. ¿Es la negativa de otra persona?")
    elif not cuil:
        lectura["avisos"].append("No se encontró el CUIL en el PDF.")
    if lectura["fecha_emision"]:
        emitida = date.fromisoformat(lectura["fecha_emision"])
        if (hoy - emitida).days > get_settings().dias_vigencia_negativa:
            lectura["avisos"].append("La negativa ya está vencida por la fecha de emisión.")
    lectura["cuil"] = cuil
    lectura["cuil_coincide"] = coincide if not (cuil and p.cuil) else formatear(p.cuil) == cuil
    return lectura


@router.post("/personas/{persona_id}/negativa-anses", status_code=201)
def registrar_negativa(
    persona_id: uuid.UUID,
    resultado: str = Form(...),
    fecha_emision: date = Form(...),
    cuil: str | None = Form(None),
    codigo_validacion: str | None = Form(None, max_length=100),
    detalle: str | None = Form(None, max_length=3000),
    observaciones: str | None = Form(None, max_length=3000),
    caso_id: str | None = Form(None),
    leido_del_pdf: bool = Form(False),
    archivo: UploadFile | None = File(None),
    ctx: Contexto = Depends(contexto),
    db: Session = Depends(get_db),
):
    p = obtener_persona(db, persona_id)
    requerir_persona(db, ctx, p, "documentos", "crear")
    if resultado not in RESULTADOS:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Resultado inválido.")
    hoy = hoy_local()
    if fecha_emision > hoy:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "La fecha de emisión no puede ser futura.")
    cuil_f = None
    if cuil and cuil.strip():
        if not cuil_valido(cuil):
            raise HTTPException(status.HTTP_400_BAD_REQUEST, "CUIL inválido.")
        cuil_f = formatear(cuil)
        if p.cuil and formatear(p.cuil) != cuil_f:
            raise HTTPException(
                status.HTTP_400_BAD_REQUEST,
                f"El CUIL ({cuil_f}) no es el del legajo ({p.cuil}). Si el del legajo está mal, corríjalo primero.",
            )
        if _cuil_coincide(cuil_f, p) is False:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, "El CUIL no corresponde al DNI del legajo.")
    if resultado != "no_emitida" and archivo is None:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Adjunte el PDF descargado de ANSES.")
    cid = uuid.UUID(caso_id) if caso_id and caso_id.strip() else None
    if cid is not None:
        validar_pertenencia(db, p.id, cid, None)

    doc_id = None
    if archivo is not None:
        contenido = archivo.file.read(MAX_PDF + 1)
        if len(contenido) > MAX_PDF or not contenido.startswith(b"%PDF"):
            raise HTTPException(status.HTTP_415_UNSUPPORTED_MEDIA_TYPE, "Adjunte el PDF descargado de ANSES (hasta 5 MB).")
        tipo = db.execute(select(TipoDocumental).where(TipoDocumental.nombre == "Certificación negativa ANSES")).scalar_one_or_none()
        if tipo is None:
            tipo = db.execute(select(TipoDocumental).where(TipoDocumental.nombre == "Otros documentos")).scalar_one()
        r = cargar_documento(
            archivo=UploadFile(file=io.BytesIO(contenido), filename=(archivo.filename or "negativa-anses.pdf")[:200]),
            tipo_documental_id=tipo.id,
            titulo=f"Certificación negativa ANSES del {fecha_emision:%d/%m/%Y}",
            descripcion=RESULTADOS[resultado],
            persona_id=str(p.id),
            caso_id=str(cid) if cid else None,
            expediente_id=None,
            ingreso_id=None,
            registro_demanda_id=None,
            ctx=ctx,
            db=db,
        )
        doc_id = uuid.UUID(r["id"])

    vence = None if resultado == "no_emitida" else fecha_emision + timedelta(days=get_settings().dias_vigencia_negativa)
    c = Constancia(
        persona_id=p.id,
        tipo=TIPO,
        cuil=cuil_f,
        fecha_emision=fecha_emision,
        vence=vence,
        resultado=resultado,
        detalle=(detalle or "").strip() or None,
        codigo_validacion=(codigo_validacion or "").strip() or None,
        documento_id=doc_id,
        origen="pdf" if (archivo is not None and leido_del_pdf) else "manual",
        observaciones=(observaciones or "").strip() or None,
        usuario_id=ctx.id,
    )
    db.add(c)
    detalle_audit = {"resultado": resultado, "fecha_emision": fecha_emision, "documento": doc_id}
    if cuil_f and not p.cuil:
        # El CUIL confirmado por ANSES queda en el legajo.
        p.cuil = cuil_f
        detalle_audit["cuil_agregado_al_legajo"] = cuil_f
    db.flush()
    audit.registrar(db, ctx, "registrar_negativa_anses", "constancia", c.id, p.id, detalle_audit)
    db.commit()
    db.refresh(c)
    return constancia_out(c, hoy)

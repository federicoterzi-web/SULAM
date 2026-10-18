"""Residencias de larga estadía e internaciones.

- Documentación de cada residencia (habilitación, fiscalización sanitaria…), con vencimiento y archivo opcional.
- Internaciones de las personas: dónde están, desde cuándo, y cómo terminó.

Permisos: módulo «residencias» (consultar / crear / modificar). Para ver o cargar datos de una persona
hace falta además tener la persona dentro del alcance de «personas».
"""

from __future__ import annotations

import hashlib
import io
import uuid
from datetime import date, timedelta
from urllib.parse import quote

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile, status
from fastapi.responses import Response, StreamingResponse
from pydantic import Field, model_validator
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from .. import audit
from ..db import get_db
from ..deps import contexto
from ..models import Caso, Internacion, Persona, Recurso, RecursoDocumento
from ..permissions import Contexto, filtro_personas, persona_en_alcance
from ..schemas import Entrada
from ..security import ahora
from ..storage import almacenamiento_actual, almacenamiento_por_nombre
from ._comun import no_encontrado, obtener_persona

router = APIRouter(tags=["residencias"])

# Documentación que se pide a una residencia (se puede sumar «otro» con un detalle).
TIPOS_DOCUMENTO = [
    {"codigo": "habilitacion_siprosa", "texto": "Habilitación (SIPROSA)", "obligatorio": True},
    {"codigo": "fiscalizacion_sanitaria", "texto": "Fiscalización sanitaria", "obligatorio": True},
    {"codigo": "habilitacion_municipal", "texto": "Habilitación municipal", "obligatorio": False},
    {"codigo": "bomberos", "texto": "Certificado de bomberos", "obligatorio": False},
    {"codigo": "director_tecnico", "texto": "Director/a técnico/a (matrícula)", "obligatorio": False},
    {"codigo": "seguro", "texto": "Seguro", "obligatorio": False},
    {"codigo": "otro", "texto": "Otro documento", "obligatorio": False},
]
CODIGOS_DOCUMENTO = {t["codigo"] for t in TIPOS_DOCUMENTO}
OBLIGATORIOS = [t["codigo"] for t in TIPOS_DOCUMENTO if t["obligatorio"]]

MODALIDADES = [
    {"codigo": "residencia", "texto": "Residencia de larga estadía"},
    {"codigo": "hogar", "texto": "Hogar"},
    {"codigo": "otra", "texto": "Otra modalidad"},
]
CODIGOS_MODALIDAD = {m["codigo"] for m in MODALIDADES}

MOTIVOS_EGRESO = [
    {"codigo": "retorno_domicilio", "texto": "Vuelve a su domicilio"},
    {"codigo": "traslado", "texto": "Traslado a otra residencia"},
    {"codigo": "internacion_salud", "texto": "Internación de salud"},
    {"codigo": "fallecimiento", "texto": "Fallecimiento"},
    {"codigo": "otro", "texto": "Otro"},
]
CODIGOS_EGRESO = {m["codigo"] for m in MOTIVOS_EGRESO}

DIAS_POR_VENCER = 60
MAX_ARCHIVO = 15 * 1024 * 1024
MIMES = {"application/pdf": "PDF", "image/jpeg": "JPG", "image/png": "PNG"}


def estado_documento(vence: date | None, hoy: date | None = None) -> str:
    if vence is None:
        return "sin_fecha"
    hoy = hoy or date.today()
    if vence < hoy:
        return "vencido"
    if (vence - hoy).days <= DIAS_POR_VENCER:
        return "por_vencer"
    return "vigente"


def _doc_out(d: RecursoDocumento, hoy: date | None = None) -> dict:
    return {
        "id": str(d.id),
        "recurso_id": str(d.recurso_id),
        "tipo": d.tipo,
        "numero": d.numero,
        "fecha_emision": d.fecha_emision.isoformat() if d.fecha_emision else None,
        "vence": d.vence.isoformat() if d.vence else None,
        "estado": estado_documento(d.vence, hoy),
        "observaciones": d.observaciones,
        "tiene_archivo": d.clave_almacenamiento is not None,
        "nombre_archivo": d.nombre,
        "actualizado_en": d.actualizado_en.isoformat() if d.actualizado_en else None,
    }


def _recurso(db: Session, recurso_id: uuid.UUID) -> Recurso:
    r = db.get(Recurso, recurso_id)
    if r is None:
        raise no_encontrado("Recurso")
    return r


def _documento(db: Session, doc_id: uuid.UUID) -> RecursoDocumento:
    d = db.get(RecursoDocumento, doc_id)
    if d is None:
        raise no_encontrado("Documento")
    return d


def _puede_tocar(ctx: Contexto, alcance: str, creado_por: uuid.UUID | None) -> None:
    if alcance == "propios" and creado_por != ctx.id:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Solo puede modificar lo que cargó usted.")


def _validar_documento(tipo: str | None, vence: date | None, emision: date | None) -> None:
    if tipo is not None and tipo not in CODIGOS_DOCUMENTO:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Tipo de documento inválido.")
    if vence and emision and vence < emision:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "El vencimiento no puede ser anterior a la emisión.")


def _leer_archivo(archivo: UploadFile) -> tuple[bytes, str]:
    cabecera = archivo.file.read(8)
    archivo.file.seek(0)
    mime = None
    if cabecera.startswith(b"%PDF"):
        mime = "application/pdf"
    elif cabecera.startswith(b"\xff\xd8\xff"):
        mime = "image/jpeg"
    elif cabecera.startswith(b"\x89PNG"):
        mime = "image/png"
    if mime is None:
        raise HTTPException(status.HTTP_415_UNSUPPORTED_MEDIA_TYPE, "Suba un PDF, JPG o PNG.")
    datos = archivo.file.read(MAX_ARCHIVO + 1)
    if len(datos) > MAX_ARCHIVO:
        raise HTTPException(status.HTTP_413_REQUEST_ENTITY_TOO_LARGE, f"El archivo supera los {MAX_ARCHIVO // (1024 * 1024)} MB.")
    return datos, mime


def _adjuntar(d: RecursoDocumento, archivo: UploadFile) -> str:
    datos, mime = _leer_archivo(archivo)
    almacen = almacenamiento_actual()
    g = almacen.guardar(io.BytesIO(datos))
    d.nombre = (archivo.filename or "documento")[:300]
    d.mime = mime
    d.tamano = len(datos)
    d.sha256 = g.sha256
    d.almacenamiento = almacen.nombre
    d.clave_almacenamiento = g.clave
    return g.sha256


# ---------------------------------------------------------------- catálogo

@router.get("/residencias/catalogo")
def catalogo(ctx: Contexto = Depends(contexto)):
    ctx.requerir("residencias", "consultar")
    return {
        "tipos_documento": TIPOS_DOCUMENTO,
        "modalidades": MODALIDADES,
        "motivos_egreso": MOTIVOS_EGRESO,
        "dias_por_vencer": DIAS_POR_VENCER,
        "puede": {"crear": ctx.tiene("residencias", "crear"), "modificar": ctx.alcance("residencias", "modificar")},
    }


# ---------------------------------------------------------------- documentación de la institución

class DocumentoIn(Entrada):
    tipo: str
    numero: str | None = Field(default=None, max_length=100)
    fecha_emision: date | None = None
    vence: date | None = None
    observaciones: str | None = Field(default=None, max_length=2000)


class DocumentoPatch(Entrada):
    tipo: str | None = None
    numero: str | None = Field(default=None, max_length=100)
    fecha_emision: date | None = None
    vence: date | None = None
    observaciones: str | None = Field(default=None, max_length=2000)


@router.get("/recursos/{recurso_id}/documentacion")
def documentacion(recurso_id: uuid.UUID, ctx: Contexto = Depends(contexto), db: Session = Depends(get_db)):
    ctx.requerir("residencias", "consultar")
    _recurso(db, recurso_id)
    docs = db.execute(
        select(RecursoDocumento)
        .where(RecursoDocumento.recurso_id == recurso_id)
        .order_by(RecursoDocumento.vence.desc().nulls_last(), RecursoDocumento.creado_en.desc())
    ).scalars().all()
    salida = [_doc_out(d) for d in docs]
    # De cada tipo obligatorio cuenta el más reciente: así se ve qué falta o está vencido.
    vigentes = {}
    for d in salida:
        vigentes.setdefault(d["tipo"], d)
    resumen = []
    for t in TIPOS_DOCUMENTO:
        if not t["obligatorio"] and t["codigo"] not in vigentes:
            continue
        d = vigentes.get(t["codigo"])
        resumen.append({"tipo": t["codigo"], "texto": t["texto"], "estado": d["estado"] if d else "falta", "vence": d["vence"] if d else None})
    return {"documentos": salida, "resumen": resumen}


@router.post("/recursos/{recurso_id}/documentacion", status_code=201)
def agregar_documento(
    recurso_id: uuid.UUID,
    tipo: str = Form(...),
    numero: str | None = Form(None),
    fecha_emision: date | None = Form(None),
    vence: date | None = Form(None),
    observaciones: str | None = Form(None),
    archivo: UploadFile | None = File(None),
    ctx: Contexto = Depends(contexto),
    db: Session = Depends(get_db),
):
    ctx.requerir("residencias", "crear")
    _recurso(db, recurso_id)
    _validar_documento(tipo, vence, fecha_emision)
    d = RecursoDocumento(
        recurso_id=recurso_id, tipo=tipo, numero=(numero or "").strip() or None, fecha_emision=fecha_emision, vence=vence,
        observaciones=(observaciones or "").strip() or None, creado_por=ctx.id, actualizado_por=ctx.id,
    )
    sha = None
    if archivo is not None and archivo.filename:
        sha = _adjuntar(d, archivo)
    db.add(d)
    db.flush()
    audit.registrar(db, ctx, "documento_cargado", "recurso_documento", d.id, None, {"recurso": str(recurso_id), "tipo": tipo, "vence": str(vence) if vence else None, "sha256": sha})
    db.commit()
    db.refresh(d)
    return _doc_out(d)


@router.patch("/recursos/documentacion/{doc_id}")
def modificar_documento(doc_id: uuid.UUID, datos: DocumentoPatch, ctx: Contexto = Depends(contexto), db: Session = Depends(get_db)):
    alcance = ctx.requerir("residencias", "modificar")
    d = _documento(db, doc_id)
    _puede_tocar(ctx, alcance, d.creado_por)
    cambios = datos.model_dump(exclude_unset=True)
    if cambios.get("tipo") is None:
        cambios.pop("tipo", None)
    _validar_documento(cambios.get("tipo"), cambios.get("vence", d.vence), cambios.get("fecha_emision", d.fecha_emision))
    diff = {}
    for k, v in cambios.items():
        if isinstance(v, str):
            v = v.strip() or None
        if getattr(d, k) != v:
            diff[k] = [str(getattr(d, k)) if getattr(d, k) is not None else None, str(v) if v is not None else None]
            setattr(d, k, v)
    if diff:
        d.actualizado_por = ctx.id
        d.actualizado_en = ahora()
        audit.registrar(db, ctx, "documento_modificado", "recurso_documento", d.id, None, {"recurso": str(d.recurso_id), "cambios": diff})
        db.commit()
        db.refresh(d)
    return _doc_out(d)


@router.post("/recursos/documentacion/{doc_id}/archivo")
def adjuntar_archivo(doc_id: uuid.UUID, archivo: UploadFile = File(...), ctx: Contexto = Depends(contexto), db: Session = Depends(get_db)):
    alcance = ctx.requerir("residencias", "modificar")
    d = _documento(db, doc_id)
    _puede_tocar(ctx, alcance, d.creado_por)
    sha = _adjuntar(d, archivo)
    d.actualizado_por = ctx.id
    d.actualizado_en = ahora()
    audit.registrar(db, ctx, "documento_archivo", "recurso_documento", d.id, None, {"recurso": str(d.recurso_id), "sha256": sha})
    db.commit()
    db.refresh(d)
    return _doc_out(d)


@router.get("/recursos/documentacion/{doc_id}/archivo")
def ver_archivo(doc_id: uuid.UUID, ctx: Contexto = Depends(contexto), db: Session = Depends(get_db)):
    ctx.requerir("residencias", "consultar")
    d = _documento(db, doc_id)
    if d.clave_almacenamiento is None:
        raise no_encontrado("Archivo")
    almacen = almacenamiento_por_nombre(d.almacenamiento)
    with almacen.abrir(d.clave_almacenamiento) as fh:
        datos = fh.read()
    if hashlib.sha256(datos).hexdigest() != d.sha256:
        raise HTTPException(status.HTTP_409_CONFLICT, "El archivo no coincide con su huella de integridad.")
    audit.registrar(db, ctx, "documento_visto", "recurso_documento", d.id, None, {"recurso": str(d.recurso_id)})
    db.commit()
    return StreamingResponse(
        io.BytesIO(datos), media_type=d.mime or "application/octet-stream",
        headers={"Content-Disposition": f"inline; filename*=UTF-8''{quote(d.nombre or 'documento')}", "Cache-Control": "no-store", "X-Content-Type-Options": "nosniff"},
    )


@router.delete("/recursos/documentacion/{doc_id}", status_code=204)
def quitar_documento(doc_id: uuid.UUID, ctx: Contexto = Depends(contexto), db: Session = Depends(get_db)):
    alcance = ctx.requerir("residencias", "modificar")
    d = _documento(db, doc_id)
    _puede_tocar(ctx, alcance, d.creado_por)
    audit.registrar(db, ctx, "documento_quitado", "recurso_documento", d.id, None, {"recurso": str(d.recurso_id), "tipo": d.tipo, "sha256": d.sha256})
    db.delete(d)
    db.commit()
    return Response(status_code=204)


# ---------------------------------------------------------------- internaciones

class InternacionIn(Entrada):
    recurso_id: uuid.UUID | None = None
    lugar_texto: str | None = Field(default=None, max_length=300)
    modalidad: str = "residencia"
    desde: date
    caso_id: uuid.UUID | None = None
    observaciones: str | None = Field(default=None, max_length=3000)

    @model_validator(mode="after")
    def _lugar(self):
        self.lugar_texto = (self.lugar_texto or "").strip() or None
        if self.recurso_id is None and self.lugar_texto is None:
            raise ValueError("Indique la residencia (del mapa de recursos) o escriba el lugar.")
        return self


class InternacionPatch(Entrada):
    recurso_id: uuid.UUID | None = None
    lugar_texto: str | None = Field(default=None, max_length=300)
    modalidad: str | None = None
    desde: date | None = None
    hasta: date | None = None
    motivo_egreso: str | None = None
    observaciones: str | None = Field(default=None, max_length=3000)


def _int_out(i: Internacion, hoy: date | None = None, persona: Persona | None = None) -> dict:
    hoy = hoy or date.today()
    fin = i.hasta or hoy
    d = {
        "id": str(i.id),
        "persona_id": str(i.persona_id),
        "caso_id": str(i.caso_id) if i.caso_id else None,
        "recurso_id": str(i.recurso_id) if i.recurso_id else None,
        "lugar": i.recurso.nombre if i.recurso else i.lugar_texto,
        "lugar_texto": i.lugar_texto,
        "modalidad": i.modalidad,
        "desde": i.desde.isoformat(),
        "hasta": i.hasta.isoformat() if i.hasta else None,
        "vigente": i.hasta is None,
        "dias": (fin - i.desde).days,
        "motivo_egreso": i.motivo_egreso,
        "observaciones": i.observaciones,
    }
    if persona is not None:
        d["persona"] = {"id": str(persona.id), "numero_legajo": persona.numero_legajo, "nombre": f"{persona.apellidos}, {persona.nombres}"}
    return d


def _validar_internacion(db: Session, persona_id: uuid.UUID, v: dict) -> None:
    if v.get("modalidad") is not None and v["modalidad"] not in CODIGOS_MODALIDAD:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Modalidad inválida.")
    if v.get("motivo_egreso") is not None and v["motivo_egreso"] not in CODIGOS_EGRESO:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Motivo de egreso inválido.")
    if v.get("recurso_id") is not None:
        r = db.get(Recurso, v["recurso_id"])
        if r is None:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, "La residencia elegida no existe en el mapa de recursos.")
    if v.get("caso_id") is not None:
        c = db.get(Caso, v["caso_id"])
        if c is None or c.persona_id != persona_id:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, "El caso no pertenece a este legajo.")
    if v.get("hasta") and v.get("desde") and v["hasta"] < v["desde"]:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "El egreso no puede ser anterior al ingreso.")
    if v.get("desde") and v["desde"] > date.today() + timedelta(days=1):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "La fecha de ingreso no puede ser futura.")


def _persona_visible(db: Session, ctx: Contexto, persona_id: uuid.UUID) -> Persona:
    p = obtener_persona(db, persona_id, permitir_unificada=True)
    if not persona_en_alcance(db, ctx, p, ctx.requerir("personas", "consultar")):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "El legajo está fuera de su alcance.")
    return p


@router.get("/personas/{persona_id}/internaciones")
def internaciones_de_persona(persona_id: uuid.UUID, ctx: Contexto = Depends(contexto), db: Session = Depends(get_db)):
    ctx.requerir("residencias", "consultar")
    _persona_visible(db, ctx, persona_id)
    filas = db.execute(
        select(Internacion).where(Internacion.persona_id == persona_id).order_by(Internacion.desde.desc(), Internacion.creado_en.desc())
    ).scalars().all()
    return [_int_out(i) for i in filas]


@router.post("/personas/{persona_id}/internaciones", status_code=201)
def registrar_internacion(persona_id: uuid.UUID, datos: InternacionIn, ctx: Contexto = Depends(contexto), db: Session = Depends(get_db)):
    ctx.requerir("residencias", "crear")
    p = _persona_visible(db, ctx, persona_id)
    v = datos.model_dump()
    _validar_internacion(db, persona_id, v)
    if db.execute(select(Internacion.id).where(Internacion.persona_id == persona_id, Internacion.hasta.is_(None))).first():
        raise HTTPException(status.HTTP_409_CONFLICT, "La persona ya tiene una internación vigente. Registre primero el egreso.")
    i = Internacion(persona_id=persona_id, creado_por=ctx.id, actualizado_por=ctx.id, **v)
    db.add(i)
    db.flush()
    audit.registrar(db, ctx, "internacion_registrada", "internacion", i.id, persona_id, {"recurso": str(i.recurso_id) if i.recurso_id else None, "lugar": i.lugar_texto, "desde": str(i.desde)})
    db.commit()
    db.refresh(i)
    return _int_out(i, persona=p)


@router.patch("/internaciones/{internacion_id}")
def modificar_internacion(internacion_id: uuid.UUID, datos: InternacionPatch, ctx: Contexto = Depends(contexto), db: Session = Depends(get_db)):
    alcance = ctx.requerir("residencias", "modificar")
    i = db.get(Internacion, internacion_id)
    if i is None:
        raise no_encontrado("Internación")
    p = _persona_visible(db, ctx, i.persona_id)
    _puede_tocar(ctx, alcance, i.creado_por)
    cambios = datos.model_dump(exclude_unset=True)
    if cambios.get("modalidad") is None:
        cambios.pop("modalidad", None)
    if cambios.get("desde") is None:
        cambios.pop("desde", None)
    if isinstance(cambios.get("lugar_texto"), str):
        cambios["lugar_texto"] = cambios["lugar_texto"].strip() or None
    final = {c: cambios.get(c, getattr(i, c)) for c in ("recurso_id", "lugar_texto", "desde", "hasta")}
    if final["recurso_id"] is None and final["lugar_texto"] is None:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Indique la residencia o escriba el lugar.")
    if final["hasta"] is not None and not (cambios.get("motivo_egreso") or i.motivo_egreso):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Indique el motivo del egreso.")
    _validar_internacion(db, i.persona_id, {**cambios, "desde": final["desde"], "hasta": final["hasta"]})
    diff = {}
    for k, v in cambios.items():
        if getattr(i, k) != v:
            diff[k] = [str(getattr(i, k)) if getattr(i, k) is not None else None, str(v) if v is not None else None]
            setattr(i, k, v)
    if i.hasta is None:
        i.motivo_egreso = None
    if diff:
        i.actualizado_por = ctx.id
        i.actualizado_en = ahora()
        audit.registrar(db, ctx, "internacion_modificada", "internacion", i.id, i.persona_id, {"cambios": diff})
        db.commit()
        db.refresh(i)
    return _int_out(i, persona=p)


@router.get("/internaciones")
def listar_internaciones(
    recurso_id: uuid.UUID | None = None,
    vigentes: bool = True,
    q: str = Query("", max_length=200),
    ctx: Contexto = Depends(contexto),
    db: Session = Depends(get_db),
):
    """Personas internadas (solo las que están dentro del alcance de quien consulta; el resto se cuenta aparte)."""
    ctx.requerir("residencias", "consultar")
    alcance = ctx.requerir("personas", "consultar")
    base = select(Internacion, Persona).join(Persona, Persona.id == Internacion.persona_id)
    if recurso_id:
        base = base.where(Internacion.recurso_id == recurso_id)
    if vigentes:
        base = base.where(Internacion.hasta.is_(None))
    visibles = base.where(filtro_personas(ctx, alcance))
    if q.strip():
        t = "%" + q.strip().replace("%", "").replace("_", "") + "%"
        visibles = visibles.where(or_(Persona.apellidos.ilike(t), Persona.nombres.ilike(t), Persona.numero_legajo.ilike(t)))
    filas = db.execute(visibles.order_by(Internacion.desde.desc()).limit(500)).all()
    total = db.execute(select(func.count()).select_from(base.subquery())).scalar_one()
    return {"items": [_int_out(i, persona=p) for i, p in filas], "total": total, "fuera_de_alcance": max(0, total - len(filas)) if not q.strip() else 0}


# ---------------------------------------------------------------- panel

@router.get("/residencias/panel")
def panel(ctx: Contexto = Depends(contexto), db: Session = Depends(get_db)):
    """Una fila por residencia: personas internadas y estado de su documentación."""
    ctx.requerir("residencias", "consultar")
    hoy = date.today()
    residencias = db.execute(
        select(Recurso).where(Recurso.tipo == "residencia", Recurso.activo).order_by(Recurso.nombre_norm)
    ).scalars().all()
    ids = [r.id for r in residencias]
    docs: dict[uuid.UUID, list[RecursoDocumento]] = {}
    for d in db.execute(select(RecursoDocumento).where(RecursoDocumento.recurso_id.in_(ids))).scalars() if ids else []:
        docs.setdefault(d.recurso_id, []).append(d)
    internados = dict(
        db.execute(
            select(Internacion.recurso_id, func.count()).where(Internacion.hasta.is_(None), Internacion.recurso_id.in_(ids)).group_by(Internacion.recurso_id)
        ).all()
    ) if ids else {}
    filas = []
    resumen = {"residencias": len(residencias), "internados": sum(internados.values()), "con_documentos_vencidos": 0, "con_documentos_por_vencer": 0, "con_documentos_faltantes": 0}
    for r in residencias:
        ultimos: dict[str, RecursoDocumento] = {}
        for d in sorted(docs.get(r.id, []), key=lambda x: (x.vence or date.min, x.creado_en)):
            ultimos[d.tipo] = d
        estados = {}
        for t in OBLIGATORIOS:
            d = ultimos.get(t)
            estados[t] = estado_documento(d.vence, hoy) if d else "falta"
        for t, d in ultimos.items():
            if t not in OBLIGATORIOS:
                estados[t] = estado_documento(d.vence, hoy)
        peor = "vigente"
        for s in ("vencido", "falta", "por_vencer", "sin_fecha"):
            if s in estados.values():
                peor = s
                break
        if "vencido" in estados.values():
            resumen["con_documentos_vencidos"] += 1
        if "por_vencer" in estados.values():
            resumen["con_documentos_por_vencer"] += 1
        if "falta" in estados.values():
            resumen["con_documentos_faltantes"] += 1
        proximo = min((d.vence for d in ultimos.values() if d.vence and d.vence >= hoy), default=None)
        filas.append({
            "id": str(r.id), "nombre": r.nombre, "localidad": r.localidad, "departamento": r.departamento, "telefono": r.telefono,
            "internados": internados.get(r.id, 0), "estados": estados, "estado": peor, "proximo_vencimiento": proximo.isoformat() if proximo else None,
        })
    return {"resumen": resumen, "tipos": [t for t in TIPOS_DOCUMENTO if t["obligatorio"]], "items": filas}

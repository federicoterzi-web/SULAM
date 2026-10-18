"""Captura de documentos con el celular: bandeja de fotos y clasificación.

1. Con el celular (o subiendo imágenes desde la computadora) se sacan todas las fotos seguidas:
   cada una queda en la bandeja de quien la sacó.
2. Después, en el celular o en la computadora, se eligen las hojas que forman un documento,
   se indica el legajo y el tipo (con los datos que pide su plantilla) y se guarda como un solo PDF.
Las fotos de la bandeja son privadas de cada persona hasta que se las clasifica.
"""

from __future__ import annotations

import io
import uuid

from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile, status
from fastapi.responses import Response
from pydantic import Field
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from .. import audit, calibracion, reconocimiento
from ..config import get_settings
from ..db import get_db
from ..deps import contexto
from ..models import Documento, Persona, PaginaCaptura, TipoDocumental
from ..permissions import Contexto
from ..schemas import Entrada
from ..storage import almacenamiento_actual, almacenamiento_por_nombre, detectar_mime
from ._comun import no_encontrado
from .documentos import LADO_MAXIMO_FOTO, cargar_documento

router = APIRouter(tags=["capturas"])

MAX_PENDIENTES = 300
MAX_HOJAS = 60


def _pagina_propia(db: Session, ctx: Contexto, pid: uuid.UUID) -> PaginaCaptura:
    p = db.get(PaginaCaptura, pid)
    if p is None or p.usuario_id != ctx.id:
        raise no_encontrado("Foto")
    return p


def _salida(p: PaginaCaptura) -> dict:
    return {"id": str(p.id), "creada_en": p.creada_en.isoformat(), "tamano": p.tamano, "estado": p.estado}


@router.get("/capturas")
def bandeja(ctx: Contexto = Depends(contexto), db: Session = Depends(get_db)):
    ctx.requerir("documentos", "crear")
    filas = db.execute(
        select(PaginaCaptura)
        .where(PaginaCaptura.usuario_id == ctx.id, PaginaCaptura.estado == "pendiente")
        .order_by(PaginaCaptura.creada_en, PaginaCaptura.id)
    ).scalars().all()
    return {"cantidad": len(filas), "paginas": [_salida(p) for p in filas]}


@router.post("/capturas", status_code=201)
def subir_foto(foto: UploadFile = File(...), ctx: Contexto = Depends(contexto), db: Session = Depends(get_db)):
    """Una foto a la bandeja. Se vuelve a codificar: se respeta la orientación y se quitan los metadatos (GPS)."""
    from PIL import Image, ImageOps

    ctx.requerir("documentos", "crear")
    pendientes = db.execute(
        select(func.count(PaginaCaptura.id)).where(PaginaCaptura.usuario_id == ctx.id, PaginaCaptura.estado == "pendiente")
    ).scalar_one()
    if pendientes >= MAX_PENDIENTES:
        raise HTTPException(status.HTTP_409_CONFLICT, f"Hay {MAX_PENDIENTES} fotos sin clasificar. Clasifique o descarte algunas antes de seguir.")
    tope = get_settings().max_upload_bytes
    crudo = foto.file.read(tope + 1)
    if len(crudo) > tope:
        raise HTTPException(status.HTTP_413_REQUEST_ENTITY_TOO_LARGE, "La foto es demasiado grande.")
    if detectar_mime(crudo[:16]) not in ("image/jpeg", "image/png"):
        raise HTTPException(status.HTTP_415_UNSUPPORTED_MEDIA_TYPE, "Solo se aceptan fotos JPG o PNG.")
    try:
        img = ImageOps.exif_transpose(Image.open(io.BytesIO(crudo))).convert("RGB")
    except Exception:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "No se pudo leer la foto.")
    img.thumbnail((LADO_MAXIMO_FOTO, LADO_MAXIMO_FOTO))
    salida = io.BytesIO()
    img.save(salida, "JPEG", quality=82)
    salida.seek(0)
    almacen = almacenamiento_actual()
    guardado = almacen.guardar(salida)
    p = PaginaCaptura(
        usuario_id=ctx.id, mime="image/jpeg", tamano=guardado.tamano, sha256=guardado.sha256,
        almacenamiento=almacen.nombre, clave_almacenamiento=guardado.clave,
    )
    db.add(p)
    db.commit()
    db.refresh(p)
    return _salida(p)


@router.get("/capturas/{pagina_id}/imagen")
def imagen(pagina_id: uuid.UUID, miniatura: bool = Query(False), ctx: Contexto = Depends(contexto), db: Session = Depends(get_db)):
    from PIL import Image

    p = _pagina_propia(db, ctx, pagina_id)
    with almacenamiento_por_nombre(p.almacenamiento).abrir(p.clave_almacenamiento) as f:
        datos = f.read()
    if miniatura:
        img = Image.open(io.BytesIO(datos))
        img.thumbnail((360, 360))
        s = io.BytesIO()
        img.save(s, "JPEG", quality=70)
        datos = s.getvalue()
    return Response(datos, media_type="image/jpeg", headers={"Cache-Control": "private, no-store"})


@router.post("/capturas/{pagina_id}/descartar")
def descartar(pagina_id: uuid.UUID, ctx: Contexto = Depends(contexto), db: Session = Depends(get_db)):
    p = _pagina_propia(db, ctx, pagina_id)
    if p.estado == "pendiente":
        p.estado = "descartada"
        db.commit()
    return _salida(p)


class ClasificarIn(Entrada):
    paginas: list[uuid.UUID] = Field(min_length=1, max_length=MAX_HOJAS)  # en el orden de las hojas
    tipo_documental_id: int
    titulo: str = Field(min_length=1, max_length=300)
    descripcion: str | None = Field(default=None, max_length=5000)
    persona_id: uuid.UUID
    caso_id: uuid.UUID | None = None
    expediente_id: uuid.UUID | None = None
    fecha_emision: str | None = None
    vence: str | None = None
    numero: str | None = Field(default=None, max_length=100)
    datos: dict[str, str] = Field(default_factory=dict)


@router.post("/capturas/clasificar", status_code=201)
def clasificar(datos: ClasificarIn, ctx: Contexto = Depends(contexto), db: Session = Depends(get_db)):
    """Une las hojas elegidas en un solo PDF y lo guarda como documento del legajo."""
    import json

    from PIL import Image

    if len(set(datos.paginas)) != len(datos.paginas):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Una hoja está repetida.")
    paginas = [_pagina_propia(db, ctx, i) for i in datos.paginas]
    if any(p.estado != "pendiente" for p in paginas):
        raise HTTPException(status.HTTP_409_CONFLICT, "Alguna de las hojas ya fue clasificada o descartada.")
    imagenes = []
    for p in paginas:
        with almacenamiento_por_nombre(p.almacenamiento).abrir(p.clave_almacenamiento) as f:
            imagenes.append(Image.open(io.BytesIO(f.read())).convert("RGB"))
    pdf = io.BytesIO()
    imagenes[0].save(pdf, "PDF", save_all=True, append_images=imagenes[1:], resolution=200.0, quality=82)
    pdf.seek(0)
    doc = cargar_documento(
        archivo=UploadFile(file=pdf, filename=f"captura-{len(imagenes)}-hojas.pdf"),
        tipo_documental_id=datos.tipo_documental_id,
        titulo=datos.titulo,
        descripcion=datos.descripcion,
        persona_id=str(datos.persona_id),
        caso_id=str(datos.caso_id) if datos.caso_id else None,
        expediente_id=str(datos.expediente_id) if datos.expediente_id else None,
        ingreso_id=None,
        registro_demanda_id=None,
        fecha_emision=datos.fecha_emision,
        vence=datos.vence,
        numero=datos.numero,
        datos=json.dumps(datos.datos),
        ctx=ctx,
        db=db,
    )
    for p in paginas:
        p.estado = "clasificada"
        p.documento_id = uuid.UUID(doc["id"])
    persona = db.get(Persona, datos.persona_id)
    calibracion.registrar(
        db,
        paginas=[p.id for p in paginas],
        final={"persona": str(datos.persona_id), "tipo": datos.tipo_documental_id, "fecha_emision": datos.fecha_emision or None,
               "vence": datos.vence or None, "numero": datos.numero or None},
        tipo_nombre=doc["tipo_documental"]["nombre"],
        nombres_persona=set(f"{persona.apellidos_norm} {persona.nombres_norm}".split()) if persona else set(),
    )
    audit.registrar(db, ctx, "clasificar_captura", "documento", uuid.UUID(doc["id"]), datos.persona_id, {"hojas": len(paginas)})
    db.commit()
    return doc


MAX_LEER = 20


class LeerIn(Entrada):
    paginas: list[uuid.UUID] = Field(min_length=1, max_length=MAX_LEER)  # en el orden de las hojas


@router.post("/capturas/leer")
def leer(datos: LeerIn, ctx: Contexto = Depends(contexto), db: Session = Depends(get_db)):
    """Lee las hojas con OCR local y SUGIERE legajo, tipo, fechas, número y agrupación. No guarda nada."""
    ctx.requerir("documentos", "crear")
    if len(set(datos.paginas)) != len(datos.paginas):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Una hoja está repetida.")
    paginas = [_pagina_propia(db, ctx, i) for i in datos.paginas]
    if not reconocimiento.disponible():
        return {"disponible": False, "grupos": [[str(p.id)] for p in paginas]}
    textos = []
    for p in paginas:
        with almacenamiento_por_nombre(p.almacenamiento).abrir(p.clave_almacenamiento) as f:
            textos.append(reconocimiento.leer_texto(f.read()))
    todo = "\n".join(textos)

    numeros = reconocimiento.documentos_en(todo)
    persona = None
    if numeros:
        candidatas = db.execute(
            select(Persona).where(
                Persona.unificada_en_id.is_(None),
                (Persona.numero_documento.in_(numeros)) | (Persona.cuil.in_(numeros)),
            ).limit(5)
        ).scalars().all()
        if len(candidatas) == 1:
            c = candidatas[0]
            persona = {"id": str(c.id), "nombre": f"{c.apellidos}, {c.nombres}", "documento": c.numero_documento}
    tipos = db.execute(select(TipoDocumental).where(TipoDocumental.activo.is_(True))).scalars().all()
    filas = db.execute(
        select(Documento.tipo_documental_id, Documento.texto_busqueda)
        .where(Documento.eliminado_en.is_(None), Documento.texto_estado == "listo")
        .order_by(Documento.cargado_en.desc())
        .limit(400)
    ).all()
    por_tipo: dict[int, list[str]] = {}
    for tid, t in filas:
        if t and len(por_tipo.setdefault(tid, [])) < 40:
            por_tipo[tid].append(t[:20000])
    probables = reconocimiento.tipos_probables(
        todo, [(t.id, t.nombre, t.descripcion) for t in tipos], reconocimiento.palabras_aprendidas(por_tipo)
    )
    fechas = reconocimiento.fechas_en(todo)
    marcas = [reconocimiento.pagina_de(t) for t in textos]
    salida = {
        "disponible": True,
        "persona": persona,
        "tipo_documental_id": probables[0][0] if probables else None,
        "tipos_probables": [t for t, _ in probables[:3]],
        "fecha_emision": fechas["fecha_emision"],
        "vence": fechas["vence"],
        "numero": reconocimiento.numero_en(todo),
        "grupos": [[str(paginas[i].id) for i in g] for g in reconocimiento.agrupar(marcas)],
    }
    if calibracion.config(db)["activo"]:
        calibracion.recordar_lectura(
            [p.id for p in paginas],
            {"persona": persona["id"] if persona else None, "tipo": salida["tipo_documental_id"], "fecha_emision": salida["fecha_emision"],
             "vence": salida["vence"], "numero": salida["numero"], "grupos": salida["grupos"]},
            todo,
        )
    return salida

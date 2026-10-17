from __future__ import annotations

import uuid
from urllib.parse import quote

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile, status
from fastapi.responses import StreamingResponse
from sqlalchemy import select
from sqlalchemy.orm import Session

from .. import audit
from ..config import get_settings
from ..db import get_db
from ..deps import contexto
from ..models import Documento, Ingreso, Persona, RegistroDemanda, TipoDocumental, Usuario
from ..permissions import Contexto, requerir_persona
from ..schemas import DocumentoPatch, EliminarDocumentoIn
from ..security import ahora
from ..serializers import documento_out
from ..storage import almacenamiento_actual, almacenamiento_por_nombre, copiar_a_temporal, detectar_mime
from ._comun import no_encontrado, obtener_persona, registrar_actividad_caso, validar_pertenencia, ve_documento

router = APIRouter(tags=["documentos"])


def _uuid_opcional(valor: str | None, campo: str) -> uuid.UUID | None:
    if valor is None or valor.strip() == "":
        return None
    try:
        return uuid.UUID(valor)
    except ValueError:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, f"Identificador inválido en {campo}.")


def _verificar_acceso(db: Session, ctx: Contexto, d: Documento, accion: str) -> None:
    if d.eliminado_en is not None and accion != "consultar":
        raise HTTPException(status.HTTP_410_GONE, "El documento fue eliminado.")
    if d.persona_id is not None:
        persona = db.get(Persona, d.persona_id)
        requerir_persona(db, ctx, persona, "documentos", accion)
    else:
        # Documento de un ingreso todavía no vinculado a un legajo.
        if not (ctx.tiene("documentos", accion) or ctx.tiene("mesa_entrada", "consultar")):
            ctx.requerir("documentos", accion)
        if ctx.alcance("documentos", accion) == "propios" and d.cargado_por != ctx.id:
            raise HTTPException(status.HTTP_403_FORBIDDEN, "Documento fuera de su alcance.")
    if not ve_documento(db, ctx, d):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Documento reservado.")


@router.post("/documentos", status_code=201)
def cargar_documento(
    archivo: UploadFile = File(...),
    tipo_documental_id: int = Form(...),
    titulo: str = Form(..., min_length=1, max_length=300),
    descripcion: str | None = Form(None, max_length=5000),
    persona_id: str | None = Form(None),
    caso_id: str | None = Form(None),
    expediente_id: str | None = Form(None),
    ingreso_id: str | None = Form(None),
    registro_demanda_id: str | None = Form(None),
    reservado: bool = Form(False),
    ctx: Contexto = Depends(contexto),
    db: Session = Depends(get_db),
):
    cfg = get_settings()
    pid = _uuid_opcional(persona_id, "persona_id")
    cid = _uuid_opcional(caso_id, "caso_id")
    eid = _uuid_opcional(expediente_id, "expediente_id")
    iid = _uuid_opcional(ingreso_id, "ingreso_id")
    rid = _uuid_opcional(registro_demanda_id, "registro_demanda_id")
    if rid is not None:
        reg = db.get(RegistroDemanda, rid)
        if reg is None:
            raise no_encontrado("Registro de demanda")
        if pid is not None and str(reg.persona_id) != str(pid):
            raise HTTPException(status.HTTP_400_BAD_REQUEST, "El registro no pertenece a este legajo.")
        pid = reg.persona_id
        cid = cid or reg.caso_id

    ingreso = None
    if iid is not None:
        ingreso = db.get(Ingreso, iid)
        if ingreso is None:
            raise no_encontrado("Ingreso")
        if pid is None:
            pid = ingreso.persona_id

    caso = None
    if pid is not None:
        persona = obtener_persona(db, pid)
        requerir_persona(db, ctx, persona, "documentos", "crear")
        caso, _ = validar_pertenencia(db, persona.id, cid, eid)
    elif ingreso is not None:
        if not (ctx.tiene("mesa_entrada", "crear") or ctx.tiene("documentos", "crear")):
            ctx.requerir("documentos", "crear")
        if cid or eid:
            raise HTTPException(
                status.HTTP_400_BAD_REQUEST,
                "Vincule primero el ingreso a un legajo para asociar casos o expedientes.",
            )
    else:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST, "El documento debe pertenecer a un legajo o a un ingreso."
        )

    tipo = db.get(TipoDocumental, tipo_documental_id)
    if tipo is None or not tipo.activo:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Tipo documental inválido.")

    cabecera = archivo.file.read(16)
    archivo.file.seek(0)
    mime = detectar_mime(cabecera)
    if mime is None or mime not in cfg.allowed_mime:
        raise HTTPException(
            status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
            "Formato no admitido. Por ahora se aceptan PDF, JPG y PNG.",
        )
    try:
        tmp, _ = copiar_a_temporal(archivo.file, cfg.max_upload_bytes)
    except ValueError:
        raise HTTPException(
            status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            f"El archivo supera el máximo de {cfg.max_upload_mb} MB.",
        )
    almacen = almacenamiento_actual()
    with tmp:
        guardado = almacen.guardar(tmp)
    if guardado.tamano == 0:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "El archivo está vacío.")

    identicos = db.execute(
        select(Documento).where(Documento.sha256 == guardado.sha256, Documento.eliminado_en.is_(None))
    ).scalars().all()

    doc = Documento(
        persona_id=pid,
        caso_id=cid,
        expediente_id=eid,
        ingreso_id=iid,
        registro_demanda_id=rid,
        tipo_documental_id=tipo.id,
        titulo=titulo.strip(),
        descripcion=(descripcion or "").strip() or None,
        nombre_original=(archivo.filename or "archivo")[:300],
        mime=mime,
        tamano=guardado.tamano,
        sha256=guardado.sha256,
        almacenamiento=almacen.nombre,
        clave_almacenamiento=guardado.clave,
        reservado=reservado,
        cargado_por=ctx.id,
    )
    db.add(doc)
    db.flush()
    db.refresh(doc)
    if caso:
        registrar_actividad_caso(caso)
    audit.registrar(
        db, ctx, "cargar", "documento", doc.id, pid,
        {
            "titulo": doc.titulo,
            "tipo": tipo.nombre,
            "sha256": doc.sha256,
            "tamano": doc.tamano,
            "identico_a": [str(d.id) for d in identicos],
        },
    )
    db.commit()

    r = documento_out(doc, True, ctx.usuario)
    r["advertencias"] = []
    if identicos:
        mismos_legajo = [d for d in identicos if d.persona_id == pid and pid is not None]
        r["advertencias"].append(
            "Este archivo es idéntico a otro ya cargado"
            + (" en este mismo legajo." if mismos_legajo else " en el sistema.")
            + " No ocupa espacio adicional."
        )
    return r


@router.get("/documentos/{documento_id}")
def ver_documento(documento_id: uuid.UUID, ctx: Contexto = Depends(contexto), db: Session = Depends(get_db)):
    d = db.get(Documento, documento_id)
    if d is None:
        raise no_encontrado("Documento")
    _verificar_acceso(db, ctx, d, "consultar")
    return documento_out(d, True, db.get(Usuario, d.cargado_por) if d.cargado_por else None)


@router.get("/documentos/{documento_id}/archivo")
def descargar(
    documento_id: uuid.UUID,
    en_linea: bool = Query(False),
    ctx: Contexto = Depends(contexto),
    db: Session = Depends(get_db),
):
    d = db.get(Documento, documento_id)
    if d is None:
        raise no_encontrado("Documento")
    _verificar_acceso(db, ctx, d, "descargar")
    almacen = almacenamiento_por_nombre(d.almacenamiento)
    if not almacen.existe(d.clave_almacenamiento):
        raise HTTPException(status.HTTP_500_INTERNAL_SERVER_ERROR, "El archivo no se encuentra en el almacenamiento.")
    audit.registrar(db, ctx, "descargar", "documento", d.id, d.persona_id, {"titulo": d.titulo})
    db.commit()

    f = almacen.abrir(d.clave_almacenamiento)

    def iterar():
        with f:
            while bloque := f.read(256 * 1024):
                yield bloque

    disposicion = "inline" if en_linea else "attachment"
    return StreamingResponse(
        iterar(),
        media_type=d.mime,
        headers={
            "Content-Disposition": f"{disposicion}; filename*=UTF-8''{quote(d.nombre_original)}",
            "Content-Length": str(d.tamano),
            "Cache-Control": "no-store",
            "X-Content-Type-Options": "nosniff",
        },
    )


@router.patch("/documentos/{documento_id}")
def modificar_documento(
    documento_id: uuid.UUID,
    datos: DocumentoPatch,
    ctx: Contexto = Depends(contexto),
    db: Session = Depends(get_db),
):
    d = db.get(Documento, documento_id)
    if d is None:
        raise no_encontrado("Documento")
    _verificar_acceso(db, ctx, d, "modificar")
    cambios_pedidos = datos.model_dump(exclude_unset=True)
    if "tipo_documental_id" in cambios_pedidos:
        tipo = db.get(TipoDocumental, cambios_pedidos["tipo_documental_id"])
        if tipo is None or not tipo.activo:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, "Tipo documental inválido.")
    if {"caso_id", "expediente_id"} & cambios_pedidos.keys():
        if d.persona_id is None:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, "El documento no está asociado a un legajo.")
        validar_pertenencia(db, d.persona_id, cambios_pedidos.get("caso_id"), cambios_pedidos.get("expediente_id"))
    diff = audit.cambios(d, cambios_pedidos)
    if diff:
        audit.registrar(db, ctx, "modificar", "documento", d.id, d.persona_id, {"cambios": diff})
        db.commit()
        db.refresh(d)
    return documento_out(d, True, db.get(Usuario, d.cargado_por) if d.cargado_por else None)


@router.post("/documentos/{documento_id}/eliminar")
def eliminar_documento(
    documento_id: uuid.UUID,
    datos: EliminarDocumentoIn,
    ctx: Contexto = Depends(contexto),
    db: Session = Depends(get_db),
):
    """Baja lógica: el documento deja de mostrarse pero el archivo y su registro se conservan."""
    d = db.get(Documento, documento_id)
    if d is None:
        raise no_encontrado("Documento")
    _verificar_acceso(db, ctx, d, "administrar")
    d.eliminado_en = ahora()
    d.eliminado_por = ctx.id
    d.motivo_eliminacion = datos.motivo
    audit.registrar(
        db, ctx, "eliminar", "documento", d.id, d.persona_id, {"titulo": d.titulo, "motivo": datos.motivo}
    )
    db.commit()
    return {"ok": True}


# ---------------------------------------------------------------- fotos tomadas con el celular

MAX_PAGINAS_FOTO = 30
LADO_MAXIMO_FOTO = 2400  # px: suficiente para leer una hoja A4 a ~200 ppp


def fotos_a_pdf(archivos: list[UploadFile], max_bytes: int) -> bytes:
    """Une fotos JPG/PNG en un único PDF, una página por foto.

    Cada imagen se vuelve a codificar: se respeta la orientación de la cámara,
    se reduce si es enorme y se descartan los metadatos (EXIF, ubicación GPS).
    """
    import io

    from PIL import Image, ImageOps

    paginas = []
    total = 0
    for a in archivos:
        crudo = a.file.read(max_bytes + 1)
        total += len(crudo)
        if len(crudo) > max_bytes or total > max_bytes * 3:
            raise HTTPException(status.HTTP_413_REQUEST_ENTITY_TOO_LARGE, "Las fotos son demasiado grandes.")
        if detectar_mime(crudo[:16]) not in ("image/jpeg", "image/png"):
            raise HTTPException(status.HTTP_415_UNSUPPORTED_MEDIA_TYPE, "Solo se pueden unir fotos JPG o PNG.")
        try:
            img = Image.open(io.BytesIO(crudo))
            img = ImageOps.exif_transpose(img).convert("RGB")
        except Exception:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, f"No se pudo leer la foto «{a.filename}».")
        img.thumbnail((LADO_MAXIMO_FOTO, LADO_MAXIMO_FOTO))
        paginas.append(img)
    salida = io.BytesIO()
    paginas[0].save(salida, "PDF", save_all=True, append_images=paginas[1:], resolution=200.0, quality=82)
    return salida.getvalue()


@router.post("/documentos/fotos", status_code=201)
def cargar_fotos(
    fotos: list[UploadFile] = File(...),
    tipo_documental_id: int = Form(...),
    titulo: str = Form(..., min_length=1, max_length=300),
    descripcion: str | None = Form(None, max_length=5000),
    persona_id: str | None = Form(None),
    caso_id: str | None = Form(None),
    registro_demanda_id: str | None = Form(None),
    reservado: bool = Form(False),
    ctx: Contexto = Depends(contexto),
    db: Session = Depends(get_db),
):
    """Fotos de un documento de una o varias hojas sacadas con el celular: se guardan como un solo PDF."""
    import io

    if not fotos:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "No llegó ninguna foto.")
    if len(fotos) > MAX_PAGINAS_FOTO:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, f"Máximo {MAX_PAGINAS_FOTO} hojas por documento.")
    # Se controla el permiso antes de procesar las imágenes.
    pid = _uuid_opcional(persona_id, "persona_id")
    if pid is not None:
        requerir_persona(db, ctx, obtener_persona(db, pid), "documentos", "crear")
    else:
        ctx.requerir("documentos", "crear")
    pdf = fotos_a_pdf(fotos, get_settings().max_upload_bytes)
    nombre = f"fotos-{ahora():%Y%m%d-%H%M}.pdf"
    return cargar_documento(
        archivo=UploadFile(file=io.BytesIO(pdf), filename=nombre),
        tipo_documental_id=tipo_documental_id,
        titulo=titulo,
        descripcion=descripcion,
        persona_id=persona_id,
        caso_id=caso_id,
        expediente_id=None,
        ingreso_id=None,
        registro_demanda_id=registro_demanda_id,
        reservado=reservado,
        ctx=ctx,
        db=db,
    )

from __future__ import annotations

import json
import uuid
from datetime import date, timedelta
from urllib.parse import quote

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile, status
from fastapi.responses import StreamingResponse
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from .. import audit, indexacion
from ..config import get_settings
from ..db import get_db
from ..deps import contexto
from ..models import Documento, Ingreso, Persona, RegistroDemanda, TipoDocumental, Usuario
from ..permissions import Contexto, requerir_persona
from ..schemas import DocumentoPatch, EliminarDocumentoIn, TipoDocumentalIn, TipoDocumentalPatch
from ..security import ahora
from ..serializers import documento_out, tipo_documental_out
from ..storage import almacenamiento_actual, almacenamiento_por_nombre, copiar_a_temporal, detectar_mime
from ._comun import no_encontrado, obtener_persona, registrar_actividad_caso, validar_pertenencia

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


def _fecha(valor: str | None, campo: str) -> date | None:
    if valor is None or valor.strip() == "":
        return None
    try:
        return date.fromisoformat(valor.strip())
    except ValueError:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, f"Fecha inválida en {campo}.")


def datos_segun_tipo(
    tipo: TipoDocumental, fecha_emision: str | None, vence: str | None, numero: str | None, datos: str | None
) -> dict:
    """Valida y normaliza lo que se pide según la plantilla del tipo documental."""
    emision = _fecha(fecha_emision, "la fecha de emisión")
    caduca = _fecha(vence, "el vencimiento")
    if caduca is None and emision is not None and tipo.tiene_vencimiento and tipo.vigencia_dias:
        caduca = emision + timedelta(days=tipo.vigencia_dias)
    if caduca is not None and not tipo.tiene_vencimiento:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, f"Los documentos «{tipo.nombre}» no tienen vencimiento.")
    if emision is not None and caduca is not None and caduca < emision:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "El vencimiento no puede ser anterior a la emisión.")
    num = (numero or "").strip() or None
    if num is not None and not tipo.usa_numero:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, f"Los documentos «{tipo.nombre}» no llevan número.")
    try:
        crudos = json.loads(datos) if datos and datos.strip() else {}
    except ValueError:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Los datos del documento no son válidos.")
    if not isinstance(crudos, dict):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Los datos del documento no son válidos.")
    propios = {}
    for c in tipo.campos or []:
        v = crudos.get(c["clave"])
        if v is None or str(v).strip() == "":
            continue
        v = str(v).strip()[:300]
        if c["tipo"] == "fecha":
            v = (_fecha(v, c["etiqueta"]) or date.today()).isoformat()
        elif c["tipo"] == "numero":
            try:
                float(v.replace(",", "."))
            except ValueError:
                raise HTTPException(status.HTTP_400_BAD_REQUEST, f"«{c['etiqueta']}» debe ser un número.")
        propios[c["clave"]] = v
    return {"fecha_emision": emision, "vence": caduca, "numero": num, "datos": propios}


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
    fecha_emision: str | None = Form(None),
    vence: str | None = Form(None),
    numero: str | None = Form(None),
    datos: str | None = Form(None),
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

    # Otras rutas llaman a esta función directamente: los parámetros de formulario omitidos llegan como objetos Form.
    texto = lambda v: v if isinstance(v, str) else None  # noqa: E731
    propios = datos_segun_tipo(tipo, texto(fecha_emision), texto(vence), texto(numero), texto(datos))

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
        cargado_por=ctx.id,
        **propios,
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
            "vence": propios["vence"].isoformat() if propios["vence"] else None,
        },
    )
    db.commit()
    indexacion.lanzar(doc.id)

    r = documento_out(doc, ctx.usuario)
    r["advertencias"] = []
    if identicos:
        mismos_legajo = [d for d in identicos if d.persona_id == pid and pid is not None]
        r["advertencias"].append(
            "Este archivo es idéntico a otro ya cargado"
            + (" en este mismo legajo." if mismos_legajo else " en el sistema.")
            + " No ocupa espacio adicional."
        )
    return r


def _clave_de(etiqueta: str, usadas: set[str]) -> str:
    import re
    import unicodedata

    base = re.sub(r"[^a-z0-9]+", "_", unicodedata.normalize("NFD", etiqueta.lower()).encode("ascii", "ignore").decode()).strip("_") or "campo"
    clave, n = base[:40], 1
    while clave in usadas:
        n += 1
        clave = f"{base[:36]}_{n}"
    usadas.add(clave)
    return clave


@router.post("/tipos-documentales", status_code=201)
def crear_tipo_documental(datos: TipoDocumentalIn, ctx: Contexto = Depends(contexto), db: Session = Depends(get_db)):
    """Tipo de documento nuevo, con su plantilla (vencimiento, número y campos propios) para los próximos documentos."""
    ctx.requerir("documentos", "crear")
    nombre = " ".join(datos.nombre.split())
    ya = db.execute(select(TipoDocumental).where(func.lower(TipoDocumental.nombre) == nombre.lower())).scalar_one_or_none()
    if ya is not None:
        raise HTTPException(status.HTTP_409_CONFLICT, f"Ya existe el tipo «{ya.nombre}»." + ("" if ya.activo else " Está desactivado: pida a la Dirección que lo reactive."))
    usadas: set[str] = set()
    t = TipoDocumental(
        nombre=nombre,
        descripcion=(datos.descripcion or "").strip() or None,
        tiene_vencimiento=datos.tiene_vencimiento,
        vigencia_dias=datos.vigencia_dias if datos.tiene_vencimiento else None,
        usa_numero=datos.usa_numero,
        campos=[{"clave": _clave_de(c.etiqueta, usadas), "etiqueta": c.etiqueta.strip(), "tipo": c.tipo} for c in datos.campos],
        creado_por=ctx.id,
        orden=1000,
    )
    db.add(t)
    db.flush()
    audit.registrar(db, ctx, "crear", "tipo_documental", t.id, None, {"nombre": t.nombre, "plantilla": tipo_documental_out(t)})
    db.commit()
    return tipo_documental_out(t)


@router.patch("/tipos-documentales/{tipo_id}")
def modificar_tipo_documental(
    tipo_id: int, datos: TipoDocumentalPatch, ctx: Contexto = Depends(contexto), db: Session = Depends(get_db)
):
    """Edita la plantilla de un tipo. Los datos ya cargados no se pierden: los campos no se pueden quitar ni cambiar de clase."""
    ctx.requerir("documentos", "crear")
    t = db.get(TipoDocumental, tipo_id)
    if t is None:
        raise no_encontrado("Tipo documental")
    antes = tipo_documental_out(t)
    pedido = datos.model_dump(exclude_unset=True)
    if "nombre" in pedido and pedido["nombre"] is not None:
        nombre = " ".join(pedido["nombre"].split())
        otro = db.execute(
            select(TipoDocumental).where(func.lower(TipoDocumental.nombre) == nombre.lower(), TipoDocumental.id != t.id)
        ).scalar_one_or_none()
        if otro is not None:
            raise HTTPException(status.HTTP_409_CONFLICT, f"Ya existe el tipo «{otro.nombre}».")
        t.nombre = nombre
    if "descripcion" in pedido:
        t.descripcion = (pedido["descripcion"] or "").strip() or None
    if pedido.get("tiene_vencimiento") is not None:
        t.tiene_vencimiento = pedido["tiene_vencimiento"]
    if "vigencia_dias" in pedido or pedido.get("tiene_vencimiento") is False:
        t.vigencia_dias = pedido.get("vigencia_dias") if t.tiene_vencimiento else None
    if pedido.get("usa_numero") is not None:
        t.usa_numero = pedido["usa_numero"]
    if pedido.get("campos") is not None:
        actuales = {c["clave"]: c for c in t.campos or []}
        nuevos, usadas = [], set(actuales)
        recibidos = set()
        for c in datos.campos or []:
            if c.clave:
                if c.clave not in actuales:
                    raise HTTPException(status.HTTP_400_BAD_REQUEST, "Un dato no corresponde a este tipo.")
                if c.tipo != actuales[c.clave]["tipo"]:
                    raise HTTPException(status.HTTP_400_BAD_REQUEST, f"No se puede cambiar la clase del dato «{actuales[c.clave]['etiqueta']}».")
                recibidos.add(c.clave)
                nuevos.append({"clave": c.clave, "etiqueta": c.etiqueta.strip(), "tipo": c.tipo})
            else:
                nuevos.append({"clave": _clave_de(c.etiqueta, usadas), "etiqueta": c.etiqueta.strip(), "tipo": c.tipo})
        if set(actuales) - recibidos:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, "Los datos existentes no se pueden quitar: ya hay documentos que los usan.")
        t.campos = nuevos
    despues = tipo_documental_out(t)
    if despues != antes:
        audit.registrar(db, ctx, "modificar", "tipo_documental", t.id, None, {"antes": antes, "despues": despues})
        db.commit()
        db.refresh(t)
    return tipo_documental_out(t)


@router.get("/documentos/buscar")
def buscar_en_textos(
    q: str = Query(min_length=2, max_length=200),
    limite: int = Query(30, ge=1, le=100),
    ctx: Contexto = Depends(contexto),
    db: Session = Depends(get_db),
):
    """Busca en el texto leído de los documentos. Solo aparecen los que quien busca puede abrir."""
    ctx.requerir("documentos", "consultar")
    consulta = indexacion.consulta_tsquery(q)
    if consulta is None:
        return {"total": 0, "resultados": []}
    vector = func.to_tsvector("simple", func.coalesce(Documento.texto_busqueda, ""))
    tsq = func.to_tsquery("simple", consulta)
    filas = db.execute(
        select(Documento)
        .where(Documento.eliminado_en.is_(None), vector.op("@@")(tsq))
        .order_by(func.ts_rank(vector, tsq).desc(), Documento.cargado_en.desc())
        .limit(300)
    ).scalars().all()
    resultados = []
    for d in filas:
        try:
            _verificar_acceso(db, ctx, d, "consultar")
        except HTTPException:
            continue
        p = db.get(Persona, d.persona_id) if d.persona_id else None
        resultados.append({
            **documento_out(d),
            "persona": {"id": str(p.id), "nombre": f"{p.apellidos}, {p.nombres}"} if p else None,
            "fragmento": indexacion.fragmento(d.texto, q),
        })
        if len(resultados) >= limite:
            break
    audit.registrar(db, ctx, "buscar_texto", "documento", None, None, {"q": q[:200], "resultados": len(resultados)})
    db.commit()
    return {"total": len(resultados), "resultados": resultados}


def _bytes_del_archivo(d: Documento) -> bytes:
    with almacenamiento_por_nombre(d.almacenamiento).abrir(d.clave_almacenamiento) as f:
        return f.read()


@router.get("/documentos/{documento_id}/hojas/{hoja}/imagen")
def imagen_de_hoja(documento_id: uuid.UUID, hoja: int, ctx: Contexto = Depends(contexto), db: Session = Depends(get_db)):
    """La hoja como imagen, para verla con las marcas encima. Equivale a ver el archivo: pide permiso de descarga."""
    from fastapi.responses import Response

    d = db.get(Documento, documento_id)
    if d is None:
        raise no_encontrado("Documento")
    _verificar_acceso(db, ctx, d, "descargar")
    r = indexacion.imagen_de_hoja(_bytes_del_archivo(d), d.mime, hoja)
    if r is None:
        raise no_encontrado("Hoja")
    audit.registrar(db, ctx, "ver_hoja", "documento", d.id, d.persona_id, {"hoja": hoja})
    db.commit()
    return Response(r[0], media_type="image/jpeg", headers={"Cache-Control": "private, no-store"})


@router.get("/documentos/{documento_id}/hojas/{hoja}/marcas")
def marcas_de_hoja(documento_id: uuid.UUID, hoja: int, ctx: Contexto = Depends(contexto), db: Session = Depends(get_db)):
    """Dónde están, sobre la imagen de la hoja, el nombre y los datos de la persona y las menciones a la Dirección (en fracciones 0–1)."""
    from .. import reconocimiento

    d = db.get(Documento, documento_id)
    if d is None:
        raise no_encontrado("Documento")
    _verificar_acceso(db, ctx, d, "consultar")
    datos = _bytes_del_archivo(d)
    r = indexacion.imagen_de_hoja(datos, d.mime, hoja)
    if r is None:
        raise no_encontrado("Hoja")
    ancho, alto, palabras = reconocimiento.leer_palabras(r[0])
    persona = db.get(Persona, d.persona_id) if d.persona_id else None
    marcadas = indexacion.marcar_palabras(palabras, persona, indexacion.menciones_institucion())
    return {
        "hojas": r[1],
        "disponible": reconocimiento.disponible(),
        "marcas": [
            {"k": k, "t": p["t"], "x": p["x"] / ancho, "y": p["y"] / alto, "w": p["w"] / ancho, "h": p["h"] / alto}
            for p, k in marcadas
        ],
    }


@router.get("/documentos/{documento_id}/texto")
def ver_texto(documento_id: uuid.UUID, ctx: Contexto = Depends(contexto), db: Session = Depends(get_db)):
    """Texto leído del documento, por hoja, con marcas sobre el nombre y los datos de la persona y las menciones a la Dirección."""
    d = db.get(Documento, documento_id)
    if d is None:
        raise no_encontrado("Documento")
    _verificar_acceso(db, ctx, d, "consultar")
    persona = db.get(Persona, d.persona_id) if d.persona_id else None
    pats_persona = indexacion.patrones_persona(persona) if persona else []
    pats = pats_persona + indexacion.patrones_institucion()
    hojas = (d.texto or "").split(indexacion.SALTO) if d.texto else []
    salida = [{"hoja": i + 1, "trozos": indexacion.resaltar(h, pats)} for i, h in enumerate(hojas)]
    cuenta = {"nombre": 0, "documento": 0, "institucion": 0}
    for h in salida:
        for t in h["trozos"]:
            if t["k"]:
                cuenta[t["k"]] += 1
    alerta = None
    if persona and d.texto_estado == "listo" and len(d.texto or "") > 60 and not cuenta["nombre"] and not cuenta["documento"]:
        alerta = "En el texto no aparece el nombre ni el documento de la persona de este legajo. Verifique que esté en el legajo correcto."
    return {"estado": d.texto_estado, "hojas": salida, "cuenta": cuenta, "alerta": alerta, "paginas": indexacion.cantidad_de_hojas(_bytes_del_archivo(d), d.mime)}


@router.post("/documentos/{documento_id}/leer-texto")
def releer_texto(documento_id: uuid.UUID, ctx: Contexto = Depends(contexto), db: Session = Depends(get_db)):
    """Vuelve a leer el texto del archivo (por ejemplo, para documentos cargados antes de que existiera la lectura)."""
    d = db.get(Documento, documento_id)
    if d is None:
        raise no_encontrado("Documento")
    _verificar_acceso(db, ctx, d, "crear")
    estado = indexacion.indexar_documento(d.id)
    return {"estado": estado}


@router.get("/documentos/{documento_id}")
def ver_documento(documento_id: uuid.UUID, ctx: Contexto = Depends(contexto), db: Session = Depends(get_db)):
    d = db.get(Documento, documento_id)
    if d is None:
        raise no_encontrado("Documento")
    _verificar_acceso(db, ctx, d, "consultar")
    return documento_out(d, db.get(Usuario, d.cargado_por) if d.cargado_por else None)


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
    tipo_final = db.get(TipoDocumental, cambios_pedidos.get("tipo_documental_id", d.tipo_documental_id))
    if cambios_pedidos.get("vence") and not tipo_final.tiene_vencimiento:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, f"Los documentos «{tipo_final.nombre}» no tienen vencimiento.")
    if cambios_pedidos.get("numero") and not tipo_final.usa_numero:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, f"Los documentos «{tipo_final.nombre}» no llevan número.")
    if cambios_pedidos.get("datos"):
        claves = {c["clave"] for c in tipo_final.campos or []}
        cambios_pedidos["datos"] = {k: v for k, v in cambios_pedidos["datos"].items() if k in claves and str(v).strip()}
    if {"caso_id", "expediente_id"} & cambios_pedidos.keys():
        if d.persona_id is None:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, "El documento no está asociado a un legajo.")
        validar_pertenencia(db, d.persona_id, cambios_pedidos.get("caso_id"), cambios_pedidos.get("expediente_id"))
    diff = audit.cambios(d, cambios_pedidos)
    if diff:
        audit.registrar(db, ctx, "modificar", "documento", d.id, d.persona_id, {"cambios": diff})
        db.commit()
        db.refresh(d)
    return documento_out(d, db.get(Usuario, d.cargado_por) if d.cargado_por else None)


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
    fecha_emision: str | None = Form(None),
    vence: str | None = Form(None),
    numero: str | None = Form(None),
    datos: str | None = Form(None),
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
        fecha_emision=fecha_emision,
        vence=vence,
        numero=numero,
        datos=datos,
        ctx=ctx,
        db=db,
    )

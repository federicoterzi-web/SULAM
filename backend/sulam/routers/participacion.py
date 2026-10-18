"""División Participación y Sensibilización Ciudadana: eventos, campañas, material, asistentes, fotos y brief.

- Los eventos son actividades de la agenda (tipo «evento»): comparten día, hora, lugar, participantes, estado, repetición e
  historial con el resto de la agenda. Acá se guarda lo propio: nombre del flyer, tipo (lo define el área), instituciones,
  resumen, campaña, quién organiza, si se sugiere la presencia de la Dirección y los asistentes.
- Los tipos de evento los constituye el área.
- Una campaña reúne material y eventos; cada evento puede estar a cargo de otra organización.
- Una vez realizado, el evento admite cantidad de asistentes y hasta dos fotos, y se exporta un brief en Word.
- Es interna; los eventos no llevan datos de personas.
"""

from __future__ import annotations

import hashlib
import io
import uuid
from datetime import date, datetime, time, timedelta
from urllib.parse import quote

from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile, status
from fastapi.responses import Response, StreamingResponse
from pydantic import Field, model_validator
from sqlalchemy import func, or_, select, true
from sqlalchemy.orm import Session

from .. import audit
from ..db import get_db
from ..deps import contexto
from ..models import (
    Campania,
    CampaniaMaterial,
    EventoAgenda,
    EventoParticipacion,
    FotoParticipacion,
    TipoParticipacion,
)
from ..permissions import Contexto
from ..schemas import Entrada
from ..security import ahora
from ..storage import almacenamiento_actual, almacenamiento_por_nombre
from ._comun import no_encontrado
from .agenda import (
    TIPO_EVENTO,
    EventoIn,
    EventoPatch,
    Repeticion,
    _condicion_alcance,
    _destinos,
    _en_alcance,
    _evento,
    _puede_modificar,
    _salida,
    crear_actividades,
    modificar_actividad,
)

router = APIRouter(tags=["participacion"])

MAX_FOTO = 12 * 1024 * 1024
MAX_MATERIAL = 25 * 1024 * 1024
MAX_FOTOS_POR_EVENTO = 2
DOCX = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
MESES = ["enero", "febrero", "marzo", "abril", "mayo", "junio", "julio", "agosto", "septiembre", "octubre", "noviembre", "diciembre"]
DIAS = ["lunes", "martes", "miércoles", "jueves", "viernes", "sábado", "domingo"]


# ---------------------------------------------------------------- utilidades

def _local(d: datetime) -> datetime:
    return d.astimezone()


def fecha_larga(d: date) -> str:
    return f"{DIAS[d.weekday()]} {d.day} de {MESES[d.month - 1]}"


def _alcance_campanias(ctx: Contexto, accion: str):
    """Condición sobre campañas: todas, las del área o las propias, según el alcance."""
    alc = ctx.requerir("participacion", accion)
    if alc == "todos":
        return true()
    if alc in ("area", "asignados") and ctx.usuario.area_id is not None:
        return or_(Campania.area_id == ctx.usuario.area_id, Campania.creado_por == ctx.id)
    return Campania.creado_por == ctx.id


def _campania(db: Session, ctx: Contexto, campania_id: uuid.UUID, accion: str = "consultar") -> Campania:
    c = db.execute(select(Campania).where(Campania.id == campania_id, _alcance_campanias(ctx, accion))).scalar_one_or_none()
    if c is None:
        if db.get(Campania, campania_id) is None:
            raise no_encontrado("Campaña")
        raise HTTPException(status.HTTP_403_FORBIDDEN, "La campaña está fuera de su alcance.")
    return c


def _ext(db: Session, evento_id: uuid.UUID) -> EventoParticipacion:
    x = db.get(EventoParticipacion, evento_id)
    if x is None:
        raise no_encontrado("Evento")
    return x


def _evento_part(db: Session, ctx: Contexto, evento_id: uuid.UUID, accion: str = "consultar") -> tuple[EventoAgenda, EventoParticipacion]:
    """El evento, verificando que el usuario tenga el permiso de Participación y que la actividad esté a su alcance."""
    alc = ctx.requerir("participacion", accion)
    e = db.get(EventoAgenda, evento_id)
    if e is None or e.tipo != TIPO_EVENTO:
        raise no_encontrado("Evento")
    if not _en_alcance(db, ctx, e, alc):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "El evento está fuera de su alcance.")
    return e, _ext(db, evento_id)


def _tipo_activo(db: Session, tipo_id: int) -> TipoParticipacion:
    t = db.get(TipoParticipacion, tipo_id)
    if t is None or not t.activo:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Elija un tipo de evento válido.")
    return t


def _limpiar_instituciones(xs: list[str] | None) -> list[str]:
    salida: list[str] = []
    for x in xs or []:
        x = " ".join((x or "").split())[:200]
        if x and x.lower() not in {s.lower() for s in salida}:
            salida.append(x)
    return salida[:30]


def _titulo(flyer: str | None, tipo: TipoParticipacion) -> str:
    return (flyer or "").strip() or tipo.nombre


def _foto_out(f: FotoParticipacion) -> dict:
    return {"id": str(f.id), "orden": f.orden, "nombre": f.nombre}


def _evento_out(db: Session, ctx: Contexto, e: EventoAgenda, x: EventoParticipacion, detalle: bool = False) -> dict:
    base = _salida(db, ctx, e, detalle=detalle)
    fotos = db.execute(select(FotoParticipacion).where(FotoParticipacion.evento_id == e.id).order_by(FotoParticipacion.orden)).scalars().all()
    base["participacion"] = {
        "tipo": {"id": x.tipo.id, "nombre": x.tipo.nombre},
        "nombre_flyer": x.nombre_flyer,
        "instituciones": x.instituciones or [],
        "resumen": x.resumen,
        "campania": {"id": str(x.campania.id), "nombre": x.campania.nombre} if x.campania else None,
        "organiza_otra": x.organiza_otra,
        "sugerir_directora": x.sugerir_directora,
        "asistentes": x.asistentes,
        "fotos": [_foto_out(f) for f in fotos],
        "puedo_cargar_cierre": e.estado == "realizado" and _puede_modificar(db, ctx, e),
        "puedo_descargar_brief": e.estado == "realizado" and ctx.tiene("participacion", "descargar"),
    }
    return base


# ---------------------------------------------------------------- tipos de evento

class TipoIn(Entrada):
    nombre: str = Field(min_length=2, max_length=120)


class TipoPatch(Entrada):
    nombre: str | None = Field(default=None, min_length=2, max_length=120)
    activo: bool | None = None


@router.get("/participacion/tipos")
def listar_tipos(ctx: Contexto = Depends(contexto), db: Session = Depends(get_db)):
    ctx.requerir("participacion", "consultar")
    usos = dict(db.execute(select(EventoParticipacion.tipo_id, func.count()).group_by(EventoParticipacion.tipo_id)).all())
    filas = db.execute(select(TipoParticipacion).order_by(func.lower(TipoParticipacion.nombre))).scalars()
    return [{"id": t.id, "nombre": t.nombre, "activo": t.activo, "eventos": usos.get(t.id, 0)} for t in filas]


def _nombre_libre(db: Session, nombre: str, excepto: int | None = None) -> str:
    nombre = " ".join(nombre.split())
    q = select(TipoParticipacion.id).where(func.lower(TipoParticipacion.nombre) == nombre.lower())
    if excepto is not None:
        q = q.where(TipoParticipacion.id != excepto)
    if db.execute(q).first() is not None:
        raise HTTPException(status.HTTP_409_CONFLICT, "Ya existe un tipo de evento con ese nombre.")
    return nombre


@router.post("/participacion/tipos", status_code=201)
def crear_tipo(datos: TipoIn, ctx: Contexto = Depends(contexto), db: Session = Depends(get_db)):
    ctx.requerir("participacion", "administrar")
    t = TipoParticipacion(nombre=_nombre_libre(db, datos.nombre), creado_por=ctx.id)
    db.add(t)
    db.flush()
    audit.registrar(db, ctx, "crear", "participacion_tipo", None, None, {"id": t.id, "nombre": t.nombre})
    db.commit()
    return {"id": t.id, "nombre": t.nombre, "activo": True, "eventos": 0}


@router.patch("/participacion/tipos/{tipo_id}")
def modificar_tipo(tipo_id: int, datos: TipoPatch, ctx: Contexto = Depends(contexto), db: Session = Depends(get_db)):
    ctx.requerir("participacion", "administrar")
    t = db.get(TipoParticipacion, tipo_id)
    if t is None:
        raise no_encontrado("Tipo de evento")
    antes = {"nombre": t.nombre, "activo": t.activo}
    if datos.nombre is not None:
        t.nombre = _nombre_libre(db, datos.nombre, excepto=t.id)
    if datos.activo is not None:
        t.activo = datos.activo
    audit.registrar(db, ctx, "modificar", "participacion_tipo", None, None, {"id": t.id, "antes": antes, "despues": {"nombre": t.nombre, "activo": t.activo}})
    db.commit()
    return {"id": t.id, "nombre": t.nombre, "activo": t.activo}


# ---------------------------------------------------------------- eventos

class EventoPartIn(Entrada):
    tipo_id: int
    nombre_flyer: str | None = Field(default=None, max_length=200)
    inicio: datetime
    fin: datetime | None = None
    todo_el_dia: bool = False
    lugar: str | None = Field(default=None, max_length=300)
    instituciones: list[str] = Field(default_factory=list)
    resumen: str | None = Field(default=None, max_length=3000)
    campania_id: uuid.UUID | None = None
    organiza_otra: str | None = Field(default=None, max_length=200)
    sugerir_directora: bool = False
    participantes: list[uuid.UUID] | None = None
    repetir: Repeticion | None = None

    @model_validator(mode="after")
    def _coherencia(self):
        if self.fin is not None and self.fin < self.inicio:
            raise ValueError("El fin es anterior al inicio.")
        return self


class EventoPartPatch(Entrada):
    tipo_id: int | None = None
    nombre_flyer: str | None = Field(default=None, max_length=200)
    inicio: datetime | None = None
    fin: datetime | None = None
    todo_el_dia: bool | None = None
    lugar: str | None = Field(default=None, max_length=300)
    instituciones: list[str] | None = None
    resumen: str | None = Field(default=None, max_length=3000)
    campania_id: uuid.UUID | None = None
    organiza_otra: str | None = Field(default=None, max_length=200)
    sugerir_directora: bool | None = None
    participantes: list[uuid.UUID] | None = None
    aplicar_a: str = Field(default="esta", pattern="^(esta|siguientes)$")
    motivo: str | None = Field(default=None, max_length=1000)


@router.post("/participacion/eventos", status_code=201)
def crear_evento(datos: EventoPartIn, ctx: Contexto = Depends(contexto), db: Session = Depends(get_db)):
    ctx.requerir("participacion", "crear")
    tipo = _tipo_activo(db, datos.tipo_id)
    if datos.campania_id is not None:
        _campania(db, ctx, datos.campania_id, "consultar")
    resumen = (datos.resumen or "").strip() or None
    base = EventoIn(
        tipo=TIPO_EVENTO, titulo=_titulo(datos.nombre_flyer, tipo), descripcion=resumen, inicio=datos.inicio, fin=datos.fin,
        todo_el_dia=datos.todo_el_dia, lugar=(datos.lugar or "").strip() or None, participantes=datos.participantes, repetir=datos.repetir,
    )
    creados = crear_actividades(db, ctx, base)
    for e in creados:
        db.add(
            EventoParticipacion(
                evento_id=e.id, tipo_id=tipo.id, nombre_flyer=(datos.nombre_flyer or "").strip() or None,
                instituciones=_limpiar_instituciones(datos.instituciones), resumen=resumen, campania_id=datos.campania_id,
                organiza_otra=(datos.organiza_otra or "").strip() or None, sugerir_directora=datos.sugerir_directora,
            )
        )
    db.flush()
    audit.registrar(db, ctx, "crear", "participacion_evento", creados[0].id, None, {"tipo": tipo.nombre, "campania": str(datos.campania_id) if datos.campania_id else None, "repeticiones": len(creados)})
    db.commit()
    db.refresh(creados[0])
    salida = _evento_out(db, ctx, creados[0], _ext(db, creados[0].id), detalle=True)
    salida["creadas"] = len(creados)
    return salida


@router.get("/participacion/eventos/{evento_id}")
def ver_evento(evento_id: uuid.UUID, ctx: Contexto = Depends(contexto), db: Session = Depends(get_db)):
    e, x = _evento_part(db, ctx, evento_id)
    return _evento_out(db, ctx, e, x, detalle=True)


@router.patch("/participacion/eventos/{evento_id}")
def modificar_evento(evento_id: uuid.UUID, datos: EventoPartPatch, ctx: Contexto = Depends(contexto), db: Session = Depends(get_db)):
    e, x = _evento_part(db, ctx, evento_id, "modificar")
    cambios = datos.model_dump(exclude_unset=True)
    if "tipo_id" in cambios and cambios["tipo_id"] is None:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Elija un tipo de evento.")
    tipo = _tipo_activo(db, cambios["tipo_id"]) if cambios.get("tipo_id") else x.tipo
    if cambios.get("campania_id") is not None:
        _campania(db, ctx, cambios["campania_id"], "consultar")
    flyer = ((cambios["nombre_flyer"] or "").strip() or None) if "nombre_flyer" in cambios else x.nombre_flyer
    resumen = ((cambios["resumen"] or "").strip() or None) if "resumen" in cambios else x.resumen
    patch = EventoPatch(
        titulo=_titulo(flyer, tipo), descripcion=resumen, aplicar_a=datos.aplicar_a, motivo=datos.motivo,
        **{k: cambios[k] for k in ("inicio", "fin", "todo_el_dia", "lugar", "participantes") if k in cambios},
    )

    def aplicar(d: EventoAgenda) -> None:
        ex = _ext(db, d.id)
        ex.tipo_id = tipo.id
        if "nombre_flyer" in cambios:
            ex.nombre_flyer = flyer
        if "resumen" in cambios:
            ex.resumen = resumen
        if "instituciones" in cambios:
            ex.instituciones = _limpiar_instituciones(cambios["instituciones"])
        if "campania_id" in cambios:
            ex.campania_id = cambios["campania_id"]
        if "organiza_otra" in cambios:
            ex.organiza_otra = (cambios["organiza_otra"] or "").strip() or None
        if cambios.get("sugerir_directora") is not None:
            ex.sugerir_directora = cambios["sugerir_directora"]

    modificar_actividad(db, ctx, e, patch, al_aplicar=aplicar)
    audit.registrar(db, ctx, "modificar", "participacion_evento", e.id, None, {"campos": sorted(k for k in cambios if k not in ("aplicar_a", "motivo"))})
    db.commit()
    db.refresh(e)
    db.refresh(x)
    return _evento_out(db, ctx, e, x, detalle=True)


class CierreIn(Entrada):
    asistentes: int = Field(ge=0, le=1_000_000)


@router.patch("/participacion/eventos/{evento_id}/asistentes")
def cargar_asistentes(evento_id: uuid.UUID, datos: CierreIn, ctx: Contexto = Depends(contexto), db: Session = Depends(get_db)):
    e, x = _evento_part(db, ctx, evento_id, "modificar")
    if e.estado != "realizado":
        raise HTTPException(status.HTTP_409_CONFLICT, "Los asistentes se cargan una vez realizado el evento.")
    if not _puede_modificar(db, ctx, e):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "El evento está fuera de su alcance para modificar.")
    antes = x.asistentes
    x.asistentes = datos.asistentes
    audit.registrar(db, ctx, "asistentes", "participacion_evento", e.id, None, {"antes": antes, "despues": datos.asistentes})
    db.commit()
    return _evento_out(db, ctx, e, x, detalle=True)


# ---------------------------------------------------------------- fotos

def _leer_imagen(archivo: UploadFile, limite: int, permitidos: dict[str, str]) -> tuple[bytes, str]:
    cabecera = archivo.file.read(16)
    archivo.file.seek(0)
    mime = None
    if cabecera.startswith(b"\xff\xd8\xff"):
        mime = "image/jpeg"
    elif cabecera.startswith(b"\x89PNG\r\n\x1a\n"):
        mime = "image/png"
    elif cabecera[:4] == b"RIFF" and cabecera[8:12] == b"WEBP":
        mime = "image/webp"
    if mime not in permitidos:
        raise HTTPException(status.HTTP_415_UNSUPPORTED_MEDIA_TYPE, f"Suba {', '.join(permitidos.values())}.")
    datos = archivo.file.read(limite + 1)
    if len(datos) > limite:
        raise HTTPException(status.HTTP_413_REQUEST_ENTITY_TOO_LARGE, f"El archivo supera los {limite // (1024 * 1024)} MB.")
    return datos, mime


def _guardar(datos: bytes):
    almacen = almacenamiento_actual()
    g = almacen.guardar(io.BytesIO(datos))
    return almacen.nombre, g


def _servir(f, disposicion: str = "inline") -> StreamingResponse:
    almacen = almacenamiento_por_nombre(f.almacenamiento)
    with almacen.abrir(f.clave_almacenamiento) as fh:
        datos = fh.read()
    if hashlib.sha256(datos).hexdigest() != f.sha256:
        raise HTTPException(status.HTTP_409_CONFLICT, "El archivo no coincide con su huella de integridad.")
    return StreamingResponse(
        io.BytesIO(datos), media_type=f.mime,
        headers={"Content-Disposition": f"{disposicion}; filename*=UTF-8''{quote(f.nombre)}", "Cache-Control": "no-store", "X-Content-Type-Options": "nosniff"},
    )


def _bytes(f) -> bytes:
    almacen = almacenamiento_por_nombre(f.almacenamiento)
    with almacen.abrir(f.clave_almacenamiento) as fh:
        datos = fh.read()
    if hashlib.sha256(datos).hexdigest() != f.sha256:
        raise HTTPException(status.HTTP_409_CONFLICT, "Un archivo no coincide con su huella de integridad.")
    return datos


@router.post("/participacion/eventos/{evento_id}/fotos", status_code=201)
def subir_foto(evento_id: uuid.UUID, archivo: UploadFile = File(...), ctx: Contexto = Depends(contexto), db: Session = Depends(get_db)):
    e, _x = _evento_part(db, ctx, evento_id, "modificar")
    if e.estado != "realizado":
        raise HTTPException(status.HTTP_409_CONFLICT, "Las fotos se suben una vez realizado el evento.")
    if not _puede_modificar(db, ctx, e):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "El evento está fuera de su alcance para modificar.")
    ocupados = set(db.execute(select(FotoParticipacion.orden).where(FotoParticipacion.evento_id == e.id)).scalars())
    libres = [o for o in range(1, MAX_FOTOS_POR_EVENTO + 1) if o not in ocupados]
    if not libres:
        raise HTTPException(status.HTTP_409_CONFLICT, f"Cada evento admite hasta {MAX_FOTOS_POR_EVENTO} fotos. Elimine una para subir otra.")
    datos, mime = _leer_imagen(archivo, MAX_FOTO, {"image/jpeg": "JPG", "image/png": "PNG", "image/webp": "WEBP"})
    nombre_almacen, g = _guardar(datos)
    f = FotoParticipacion(
        evento_id=e.id, orden=libres[0], nombre=(archivo.filename or "foto")[:300], mime=mime, tamano=len(datos), sha256=g.sha256,
        almacenamiento=nombre_almacen, clave_almacenamiento=g.clave, subido_por=ctx.id,
    )
    db.add(f)
    db.flush()
    audit.registrar(db, ctx, "foto_cargada", "participacion_evento", e.id, None, {"orden": f.orden, "sha256": g.sha256})
    db.commit()
    return _foto_out(f)


def _foto(db: Session, evento_id: uuid.UUID, foto_id: uuid.UUID) -> FotoParticipacion:
    f = db.get(FotoParticipacion, foto_id)
    if f is None or f.evento_id != evento_id:
        raise no_encontrado("Foto")
    return f


@router.get("/participacion/eventos/{evento_id}/fotos/{foto_id}")
def ver_foto(evento_id: uuid.UUID, foto_id: uuid.UUID, ctx: Contexto = Depends(contexto), db: Session = Depends(get_db)):
    _evento_part(db, ctx, evento_id)
    return _servir(_foto(db, evento_id, foto_id))


@router.delete("/participacion/eventos/{evento_id}/fotos/{foto_id}", status_code=204)
def quitar_foto(evento_id: uuid.UUID, foto_id: uuid.UUID, ctx: Contexto = Depends(contexto), db: Session = Depends(get_db)):
    e, _x = _evento_part(db, ctx, evento_id, "modificar")
    if not _puede_modificar(db, ctx, e):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "El evento está fuera de su alcance para modificar.")
    f = _foto(db, evento_id, foto_id)
    db.delete(f)
    audit.registrar(db, ctx, "foto_quitada", "participacion_evento", e.id, None, {"orden": f.orden, "sha256": f.sha256})
    db.commit()
    return Response(status_code=204)


# ---------------------------------------------------------------- semana (planificación y resumen para la Dirección)

def _lunes(d: date) -> date:
    return d - timedelta(days=d.weekday())


def _filas_del_rango(db: Session, ctx: Contexto, desde: datetime, hasta: datetime, campania_id: uuid.UUID | None = None):
    alc = ctx.requerir("participacion", "consultar")
    q = (
        select(EventoAgenda, EventoParticipacion)
        .join(EventoParticipacion, EventoParticipacion.evento_id == EventoAgenda.id)
        .where(EventoAgenda.inicio >= desde, EventoAgenda.inicio < hasta, _condicion_alcance(ctx, alc))
        .order_by(EventoAgenda.inicio)
    )
    if campania_id is not None:
        q = q.where(EventoParticipacion.campania_id == campania_id)
    return db.execute(q).all()


def _resumen_corto(e: EventoAgenda, x: EventoParticipacion) -> dict:
    inicio = _local(e.inicio)
    return {
        "id": str(e.id),
        "titulo": e.titulo,
        "tipo": x.tipo.nombre,
        "fecha": inicio.date().isoformat(),
        "hora": None if e.todo_el_dia else inicio.strftime("%H:%M"),
        "fin": None if (e.todo_el_dia or not e.fin) else _local(e.fin).strftime("%H:%M"),
        "lugar": e.lugar,
        "instituciones": x.instituciones or [],
        "resumen": x.resumen,
        "campania": x.campania.nombre if x.campania else None,
        "organiza_otra": x.organiza_otra,
        "sugerir_directora": x.sugerir_directora,
        "estado": e.estado,
        "asistentes": x.asistentes,
    }


def _texto_de_la_semana(lunes: date, eventos: list[dict]) -> str:
    domingo = lunes + timedelta(days=6)
    rango = f"del {lunes.day} al {domingo.day} de {MESES[domingo.month - 1]}" if lunes.month == domingo.month else f"del {lunes.day} de {MESES[lunes.month - 1]} al {domingo.day} de {MESES[domingo.month - 1]}"
    vigentes = [e for e in eventos if e["estado"] != "cancelado"]
    if not vigentes:
        return f"Semana {rango}: no hay eventos de Participación y Sensibilización planificados."
    partes = [f"Semana {rango}: {len(vigentes)} {'evento' if len(vigentes) == 1 else 'eventos'} de Participación y Sensibilización."]
    por_campania: dict[str, int] = {}
    for e in vigentes:
        if e["campania"]:
            por_campania[e["campania"]] = por_campania.get(e["campania"], 0) + 1
    if por_campania:
        partes.append("En campañas: " + "; ".join(f"«{k}» ({n})" for k, n in por_campania.items()) + ".")
    otras = [e for e in vigentes if e["organiza_otra"]]
    if otras:
        partes.append(f"A cargo de otras organizaciones: {len(otras)}.")
    for e in vigentes:
        d = date.fromisoformat(e["fecha"])
        donde = f", {e['lugar']}" if e["lugar"] else ""
        hora = f" {e['hora']} hs" if e["hora"] else ""
        con = f" (con {', '.join(e['instituciones'])})" if e["instituciones"] else ""
        marca = " Se sugiere la presencia de la Dirección." if e["sugerir_directora"] else ""
        partes.append(f"• {fecha_larga(d).capitalize()}{hora}: {e['titulo']}{donde}{con}.{marca}")
    return "\n".join(partes)


def datos_de_la_semana(db: Session, ctx: Contexto, lunes: date | None = None) -> dict:
    lunes = _lunes(lunes or ahora().astimezone().date())
    desde = datetime.combine(lunes, time.min).astimezone()
    hasta = desde + timedelta(days=7)
    eventos = [_resumen_corto(e, x) for e, x in _filas_del_rango(db, ctx, desde, hasta)]
    dias = []
    for i in range(7):
        d = lunes + timedelta(days=i)
        dias.append({"fecha": d.isoformat(), "texto": fecha_larga(d), "eventos": [e for e in eventos if e["fecha"] == d.isoformat()]})
    return {
        "lunes": lunes.isoformat(),
        "domingo": (lunes + timedelta(days=6)).isoformat(),
        "dias": dias,
        "total": len([e for e in eventos if e["estado"] != "cancelado"]),
        "con_presencia_sugerida": len([e for e in eventos if e["sugerir_directora"] and e["estado"] != "cancelado"]),
        "texto": _texto_de_la_semana(lunes, eventos),
    }


@router.get("/participacion/semana")
def semana(lunes: date | None = None, ctx: Contexto = Depends(contexto), db: Session = Depends(get_db)):
    ctx.requerir("participacion", "consultar")
    return datos_de_la_semana(db, ctx, lunes)


@router.get("/participacion/pendientes")
def pendientes(ctx: Contexto = Depends(contexto), db: Session = Depends(get_db)):
    """Eventos ya realizados a los que falta cargar los asistentes."""
    ctx.requerir("participacion", "consultar")
    desde = ahora() - timedelta(days=120)
    filas = _filas_del_rango(db, ctx, desde, ahora())
    return {
        "sin_asistentes": [_resumen_corto(e, x) for e, x in filas if e.estado == "realizado" and x.asistentes is None],
        "sin_fotos": len([1 for e, x in filas if e.estado == "realizado" and not db.scalar(select(func.count()).select_from(FotoParticipacion).where(FotoParticipacion.evento_id == e.id))]),
    }


# ---------------------------------------------------------------- campañas

class CampaniaIn(Entrada):
    nombre: str = Field(min_length=2, max_length=200)
    descripcion: str | None = Field(default=None, max_length=5000)
    desde: date | None = None
    hasta: date | None = None

    @model_validator(mode="after")
    def _fechas(self):
        if self.desde and self.hasta and self.hasta < self.desde:
            raise ValueError("La fecha de fin es anterior a la de inicio.")
        return self


class CampaniaPatch(Entrada):
    nombre: str | None = Field(default=None, min_length=2, max_length=200)
    descripcion: str | None = Field(default=None, max_length=5000)
    desde: date | None = None
    hasta: date | None = None
    estado: str | None = Field(default=None, pattern="^(activa|cerrada)$")


def _eventos_de(db: Session, campania_id: uuid.UUID):
    return db.execute(
        select(EventoAgenda, EventoParticipacion)
        .join(EventoParticipacion, EventoParticipacion.evento_id == EventoAgenda.id)
        .where(EventoParticipacion.campania_id == campania_id)
        .order_by(EventoAgenda.inicio)
    ).all()


def _material_out(m: CampaniaMaterial) -> dict:
    return {"id": str(m.id), "nombre": m.nombre, "mime": m.mime, "tamano": m.tamano, "subido_en": m.subido_en.isoformat()}


def _campania_out(db: Session, c: Campania, detalle: bool = False) -> dict:
    filas = _eventos_de(db, c.id)
    vigentes = [(e, x) for e, x in filas if e.estado != "cancelado"]
    salida = {
        "id": str(c.id),
        "nombre": c.nombre,
        "descripcion": c.descripcion,
        "desde": c.desde.isoformat() if c.desde else None,
        "hasta": c.hasta.isoformat() if c.hasta else None,
        "estado": c.estado,
        "eventos": len(vigentes),
        "realizados": len([1 for e, _ in vigentes if e.estado == "realizado"]),
        "asistentes": sum(x.asistentes or 0 for e, x in vigentes if e.estado == "realizado"),
        "materiales": len(c.materiales),
    }
    if detalle:
        salida["lista_materiales"] = [_material_out(m) for m in c.materiales]
        salida["lista_eventos"] = [_resumen_corto(e, x) for e, x in filas]
    return salida


@router.get("/participacion/campanias")
def listar_campanias(estado: str | None = Query(None, pattern="^(activa|cerrada)$"), ctx: Contexto = Depends(contexto), db: Session = Depends(get_db)):
    q = select(Campania).where(_alcance_campanias(ctx, "consultar")).order_by(Campania.creado_en.desc())
    if estado:
        q = q.where(Campania.estado == estado)
    return [_campania_out(db, c) for c in db.execute(q).scalars()]


@router.post("/participacion/campanias", status_code=201)
def crear_campania(datos: CampaniaIn, ctx: Contexto = Depends(contexto), db: Session = Depends(get_db)):
    ctx.requerir("participacion", "crear")
    c = Campania(nombre=" ".join(datos.nombre.split()), descripcion=(datos.descripcion or "").strip() or None, desde=datos.desde, hasta=datos.hasta, area_id=ctx.usuario.area_id, creado_por=ctx.id)
    db.add(c)
    db.flush()
    audit.registrar(db, ctx, "crear", "campania", c.id, None, {"nombre": c.nombre})
    db.commit()
    db.refresh(c)
    return _campania_out(db, c, detalle=True)


@router.get("/participacion/campanias/{campania_id}")
def ver_campania(campania_id: uuid.UUID, ctx: Contexto = Depends(contexto), db: Session = Depends(get_db)):
    return _campania_out(db, _campania(db, ctx, campania_id), detalle=True)


@router.patch("/participacion/campanias/{campania_id}")
def modificar_campania(campania_id: uuid.UUID, datos: CampaniaPatch, ctx: Contexto = Depends(contexto), db: Session = Depends(get_db)):
    c = _campania(db, ctx, campania_id, "modificar")
    cambios = datos.model_dump(exclude_unset=True)
    if cambios.get("nombre") is not None:
        c.nombre = " ".join(cambios["nombre"].split())
    for campo in ("descripcion", "desde", "hasta"):
        if campo in cambios:
            setattr(c, campo, (cambios[campo].strip() or None) if campo == "descripcion" and cambios[campo] else cambios[campo])
    if cambios.get("estado") is not None:
        c.estado = cambios["estado"]
    if c.desde and c.hasta and c.hasta < c.desde:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "La fecha de fin es anterior a la de inicio.")
    audit.registrar(db, ctx, "modificar", "campania", c.id, None, {"campos": sorted(cambios)})
    db.commit()
    db.refresh(c)
    return _campania_out(db, c, detalle=True)


_EXTENSIONES_MATERIAL = {
    ".pdf": "application/pdf", ".png": "image/png", ".jpg": "image/jpeg", ".jpeg": "image/jpeg", ".webp": "image/webp",
    ".docx": DOCX, ".pptx": "application/vnd.openxmlformats-officedocument.presentationml.presentation",
    ".xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", ".mp4": "video/mp4",
}


def _mime_material(cabecera: bytes, nombre: str) -> str | None:
    ext = "." + nombre.lower().rsplit(".", 1)[-1] if "." in nombre else ""
    esperado = _EXTENSIONES_MATERIAL.get(ext)
    if esperado is None:
        return None
    ok = {
        "application/pdf": cabecera.startswith(b"%PDF-"),
        "image/png": cabecera.startswith(b"\x89PNG\r\n\x1a\n"),
        "image/jpeg": cabecera.startswith(b"\xff\xd8\xff"),
        "image/webp": cabecera[:4] == b"RIFF" and cabecera[8:12] == b"WEBP",
        "video/mp4": cabecera[4:8] == b"ftyp",
    }.get(esperado, cabecera.startswith(b"PK\x03\x04"))  # Office: zip
    return esperado if ok else None


@router.post("/participacion/campanias/{campania_id}/materiales", status_code=201)
def subir_material(campania_id: uuid.UUID, archivo: UploadFile = File(...), ctx: Contexto = Depends(contexto), db: Session = Depends(get_db)):
    c = _campania(db, ctx, campania_id, "modificar")
    nombre = (archivo.filename or "material")[:300]
    cabecera = archivo.file.read(16)
    archivo.file.seek(0)
    mime = _mime_material(cabecera, nombre)
    if mime is None:
        raise HTTPException(status.HTTP_415_UNSUPPORTED_MEDIA_TYPE, "Suba un PDF, imagen (JPG, PNG, WEBP), Word, PowerPoint, Excel o video MP4.")
    datos = archivo.file.read(MAX_MATERIAL + 1)
    if len(datos) > MAX_MATERIAL:
        raise HTTPException(status.HTTP_413_REQUEST_ENTITY_TOO_LARGE, f"El archivo supera los {MAX_MATERIAL // (1024 * 1024)} MB.")
    nombre_almacen, g = _guardar(datos)
    m = CampaniaMaterial(campania_id=c.id, nombre=nombre, mime=mime, tamano=len(datos), sha256=g.sha256, almacenamiento=nombre_almacen, clave_almacenamiento=g.clave, subido_por=ctx.id)
    db.add(m)
    db.flush()
    audit.registrar(db, ctx, "material_cargado", "campania", c.id, None, {"nombre": nombre, "sha256": g.sha256})
    db.commit()
    return _material_out(m)


def _material(db: Session, campania_id: uuid.UUID, material_id: uuid.UUID) -> CampaniaMaterial:
    m = db.get(CampaniaMaterial, material_id)
    if m is None or m.campania_id != campania_id:
        raise no_encontrado("Material")
    return m


@router.get("/participacion/campanias/{campania_id}/materiales/{material_id}")
def ver_material(campania_id: uuid.UUID, material_id: uuid.UUID, ctx: Contexto = Depends(contexto), db: Session = Depends(get_db)):
    _campania(db, ctx, campania_id)
    m = _material(db, campania_id, material_id)
    return _servir(m, "inline" if m.mime.startswith("image/") or m.mime == "application/pdf" else "attachment")


@router.delete("/participacion/campanias/{campania_id}/materiales/{material_id}", status_code=204)
def quitar_material(campania_id: uuid.UUID, material_id: uuid.UUID, ctx: Contexto = Depends(contexto), db: Session = Depends(get_db)):
    c = _campania(db, ctx, campania_id, "modificar")
    m = _material(db, campania_id, material_id)
    db.delete(m)
    audit.registrar(db, ctx, "material_quitado", "campania", c.id, None, {"nombre": m.nombre, "sha256": m.sha256})
    db.commit()
    return Response(status_code=204)


# ---------------------------------------------------------------- brief para Comunicación (Word)

def _nombre_archivo(prefijo: str, texto: str) -> str:
    limpio = "".join(ch if ch.isalnum() else "-" for ch in texto.lower()).strip("-")
    while "--" in limpio:
        limpio = limpio.replace("--", "-")
    return f"{prefijo}-{limpio[:60] or 'sin-titulo'}.docx"


def _descarga(contenido: bytes, nombre: str) -> Response:
    return Response(
        contenido, media_type=DOCX,
        headers={"Content-Disposition": f"attachment; filename*=UTF-8''{quote(nombre)}", "Cache-Control": "no-store"},
    )


@router.get("/participacion/eventos/{evento_id}/brief.docx")
def brief_evento(evento_id: uuid.UUID, ctx: Contexto = Depends(contexto), db: Session = Depends(get_db)):
    from ..participacion_brief import brief_de_evento

    e, x = _evento_part(db, ctx, evento_id, "descargar")
    if e.estado != "realizado":
        raise HTTPException(status.HTTP_409_CONFLICT, "El brief se arma una vez realizado el evento.")
    fotos = db.execute(select(FotoParticipacion).where(FotoParticipacion.evento_id == e.id).order_by(FotoParticipacion.orden)).scalars().all()
    contenido = brief_de_evento(e, x, [(f.nombre, _bytes(f)) for f in fotos], ctx.usuario.nombre_completo)
    audit.registrar(db, ctx, "brief_exportado", "participacion_evento", e.id, None, {"fotos": len(fotos)})
    db.commit()
    return _descarga(contenido, _nombre_archivo("brief", f"{_local(e.inicio).date().isoformat()} {e.titulo}"))


@router.get("/participacion/campanias/{campania_id}/brief.docx")
def brief_campania(campania_id: uuid.UUID, ctx: Contexto = Depends(contexto), db: Session = Depends(get_db)):
    from ..participacion_brief import brief_de_campania

    c = _campania(db, ctx, campania_id)
    ctx.requerir("participacion", "descargar")
    filas = [(e, x, [(f.nombre, _bytes(f)) for f in db.execute(select(FotoParticipacion).where(FotoParticipacion.evento_id == e.id).order_by(FotoParticipacion.orden)).scalars()]) for e, x in _eventos_de(db, c.id)]
    contenido = brief_de_campania(c, filas, ctx.usuario.nombre_completo)
    audit.registrar(db, ctx, "brief_exportado", "campania", c.id, None, {"eventos": len(filas)})
    db.commit()
    return _descarga(contenido, _nombre_archivo("brief-campania", c.nombre))

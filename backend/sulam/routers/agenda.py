"""Agenda: salidas, visitas y actividades con fecha, participantes y resultado.

- Cada persona ve la suya (en las que participa o que cargó) y, con alcance «área», la de su área.
- Una actividad puede estar ligada a un legajo y a un caso; al registrar el resultado de una salida o visita,
  queda anotado también en la evolución del caso.
- Es interna: no se comparte con otras instituciones.
"""

from __future__ import annotations

import uuid
from datetime import date, datetime

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import Field, model_validator
from sqlalchemy import or_, select, true
from sqlalchemy.orm import Session

from .. import audit
from ..db import get_db
from ..deps import contexto
from ..models import Area, Caso, CasoEvolucion, EventoAgenda, ParticipanteAgenda, Persona, Usuario
from ..permissions import Contexto, requerir_caso, requerir_persona
from ..schemas import Entrada
from ..security import ahora
from ._comun import no_encontrado, obtener_caso, obtener_persona, registrar_actividad_caso

router = APIRouter(tags=["agenda"])

TIPOS = {
    "salida": "Salida",
    "visita": "Visita domiciliaria",
    "entrevista": "Entrevista",
    "reunion": "Reunión",
    "audiencia": "Audiencia",
    "tramite": "Trámite",
    "recordatorio": "Recordatorio",
    "otro": "Otro",
}
ESTADOS_FINALES = {"realizado": "realizada", "no_realizado": "no realizada", "cancelado": "cancelada"}
MAX_RANGO = 500


# ---------------------------------------------------------------- permisos

def _condicion_mio(ctx: Contexto):
    return or_(
        EventoAgenda.creado_por == ctx.id,
        EventoAgenda.id.in_(select(ParticipanteAgenda.evento_id).where(ParticipanteAgenda.usuario_id == ctx.id)),
    )


def _condicion_alcance(ctx: Contexto, alcance: str):
    if alcance == "todos":
        return true()
    if alcance in ("area", "asignados") and ctx.usuario.area_id is not None:
        return or_(_condicion_mio(ctx), EventoAgenda.area_id == ctx.usuario.area_id)
    return _condicion_mio(ctx)


def _en_alcance(db: Session, ctx: Contexto, e: EventoAgenda, alcance: str) -> bool:
    if alcance == "todos":
        return True
    if e.creado_por == ctx.id or any(p.usuario_id == ctx.id for p in e.participantes):
        return True
    return alcance in ("area", "asignados") and ctx.usuario.area_id is not None and e.area_id == ctx.usuario.area_id


def _puede_modificar(db: Session, ctx: Contexto, e: EventoAgenda) -> bool:
    alc = ctx.alcance("agenda", "modificar")
    return alc is not None and _en_alcance(db, ctx, e, alc)


def _evento(db: Session, ctx: Contexto, evento_id: uuid.UUID, accion: str = "consultar") -> EventoAgenda:
    e = db.get(EventoAgenda, evento_id)
    if e is None:
        raise no_encontrado("Actividad")
    alc = ctx.requerir("agenda", accion)
    if not _en_alcance(db, ctx, e, alc):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "La actividad está fuera de su alcance.")
    return e


# ---------------------------------------------------------------- salida

def _salida(db: Session, ctx: Contexto, e: EventoAgenda) -> dict:
    persona = None
    if e.persona_id:
        p = db.get(Persona, e.persona_id)
        try:
            requerir_persona(db, ctx, p, "personas", "consultar")
            persona = {"id": str(p.id), "nombre": f"{p.apellidos}, {p.nombres}", "legajo": p.numero_legajo}
        except HTTPException:
            persona = {"id": None, "nombre": "Legajo reservado", "legajo": None}
    caso = None
    if e.caso_id and persona and persona["id"]:
        c = db.get(Caso, e.caso_id)
        caso = {"id": str(c.id), "numero": c.numero}
    resolvio = db.get(Usuario, e.resuelto_por) if e.resuelto_por else None
    creador = db.get(Usuario, e.creado_por)
    return {
        "id": str(e.id),
        "tipo": e.tipo,
        "tipo_texto": TIPOS.get(e.tipo, e.tipo),
        "titulo": e.titulo,
        "descripcion": e.descripcion,
        "inicio": e.inicio.isoformat(),
        "fin": e.fin.isoformat() if e.fin else None,
        "todo_el_dia": e.todo_el_dia,
        "lugar": e.lugar,
        "area": {"id": e.area.id, "nombre": e.area.nombre} if e.area else None,
        "persona": persona,
        "caso": caso,
        "estado": e.estado,
        "resultado": e.resultado,
        "resuelto_por": resolvio.nombre_completo if resolvio else None,
        "resuelto_en": e.resuelto_en.isoformat() if e.resuelto_en else None,
        "participantes": [{"id": str(p.usuario_id), "nombre": p.usuario.nombre_completo} for p in e.participantes],
        "creado_por": creador.nombre_completo if creador else None,
        "soy_participante": any(p.usuario_id == ctx.id for p in e.participantes),
        "puedo_modificar": _puede_modificar(db, ctx, e),
    }


# ---------------------------------------------------------------- entrada

class EventoIn(Entrada):
    tipo: str
    titulo: str = Field(min_length=2, max_length=200)
    descripcion: str | None = Field(default=None, max_length=5000)
    inicio: datetime
    fin: datetime | None = None
    todo_el_dia: bool = False
    lugar: str | None = Field(default=None, max_length=300)
    area_id: int | None = None
    persona_id: uuid.UUID | None = None
    caso_id: uuid.UUID | None = None
    participantes: list[uuid.UUID] | None = None

    @model_validator(mode="after")
    def _coherencia(self):
        if self.tipo not in TIPOS:
            raise ValueError("Tipo de actividad inválido.")
        if self.fin is not None and self.fin < self.inicio:
            raise ValueError("El fin es anterior al inicio.")
        return self


class EventoPatch(Entrada):
    tipo: str | None = None
    titulo: str | None = Field(default=None, min_length=2, max_length=200)
    descripcion: str | None = Field(default=None, max_length=5000)
    inicio: datetime | None = None
    fin: datetime | None = None
    todo_el_dia: bool | None = None
    lugar: str | None = Field(default=None, max_length=300)
    persona_id: uuid.UUID | None = None
    caso_id: uuid.UUID | None = None
    participantes: list[uuid.UUID] | None = None


class ResultadoIn(Entrada):
    estado: str
    resultado: str | None = Field(default=None, max_length=5000)

    @model_validator(mode="after")
    def _estado(self):
        if self.estado not in ESTADOS_FINALES:
            raise ValueError("Estado inválido.")
        return self


def _validar_vinculo(db: Session, ctx: Contexto, persona_id, caso_id):
    persona = caso = None
    if caso_id is not None:
        caso = obtener_caso(db, caso_id)
        if persona_id is not None and caso.persona_id != persona_id:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, "El caso no pertenece a ese legajo.")
        persona_id = caso.persona_id
        requerir_caso(db, ctx, caso, "casos", "consultar")
    if persona_id is not None:
        persona = obtener_persona(db, persona_id)
        requerir_persona(db, ctx, persona, "personas", "consultar")
    return persona, caso


def _validar_participantes(db: Session, ctx: Contexto, ids: list[uuid.UUID] | None) -> list[Usuario]:
    ids = list(dict.fromkeys(ids)) if ids else [ctx.id]
    usuarios = db.execute(select(Usuario).where(Usuario.id.in_(ids), Usuario.activo.is_(True))).scalars().all()
    if len(usuarios) != len(ids):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Algún participante no existe o está dado de baja.")
    if ctx.alcance("agenda", "crear") != "todos":
        for u in usuarios:
            if u.id != ctx.id and u.area_id != ctx.usuario.area_id:
                raise HTTPException(status.HTTP_403_FORBIDDEN, "Solo puede agendar actividades para personas de su área.")
    return usuarios


# ---------------------------------------------------------------- rutas

@router.get("/agenda")
def listar(
    desde: datetime,
    hasta: datetime,
    ambito: str = Query("mio", pattern="^(mio|area|todos)$"),
    estado: str | None = None,
    ctx: Contexto = Depends(contexto),
    db: Session = Depends(get_db),
):
    """Actividades entre dos fechas. ``ambito``: las mías, las de mi área o todas (según el alcance de cada uno)."""
    alcance = ctx.requerir("agenda", "consultar")
    q = select(EventoAgenda).where(EventoAgenda.inicio >= desde, EventoAgenda.inicio < hasta)
    if ambito == "mio":
        q = q.where(_condicion_mio(ctx))
    elif ambito == "area":
        if alcance == "propios" or ctx.usuario.area_id is None:
            raise HTTPException(status.HTTP_403_FORBIDDEN, "No tiene acceso a la agenda del área.")
        q = q.where(EventoAgenda.area_id == ctx.usuario.area_id)
    else:
        if alcance != "todos":
            raise HTTPException(status.HTTP_403_FORBIDDEN, "No tiene acceso a toda la agenda.")
    if estado:
        q = q.where(EventoAgenda.estado == estado)
    filas = db.execute(q.order_by(EventoAgenda.inicio).limit(MAX_RANGO)).scalars().all()
    return {"alcance": alcance, "eventos": [_salida(db, ctx, e) for e in filas]}


@router.get("/agenda/tipos")
def tipos(ctx: Contexto = Depends(contexto)):
    ctx.requerir("agenda", "consultar")
    return [{"clave": k, "texto": v} for k, v in TIPOS.items()]


@router.get("/agenda/participantes")
def posibles_participantes(ctx: Contexto = Depends(contexto), db: Session = Depends(get_db)):
    """Personas con quienes se puede agendar: las de su área (o todas, con alcance «todos»)."""
    ctx.requerir("agenda", "crear")
    q = select(Usuario).where(Usuario.activo.is_(True)).order_by(Usuario.nombre_completo)
    if ctx.alcance("agenda", "crear") != "todos":
        q = q.where(Usuario.area_id == ctx.usuario.area_id) if ctx.usuario.area_id else q.where(Usuario.id == ctx.id)
    return [{"id": str(u.id), "nombre": u.nombre_completo, "area": u.area.nombre if u.area else None} for u in db.execute(q).scalars()]


@router.post("/agenda", status_code=201)
def crear(datos: EventoIn, ctx: Contexto = Depends(contexto), db: Session = Depends(get_db)):
    ctx.requerir("agenda", "crear")
    persona, caso = _validar_vinculo(db, ctx, datos.persona_id, datos.caso_id)
    participantes = _validar_participantes(db, ctx, datos.participantes)
    area_id = ctx.usuario.area_id
    if datos.area_id is not None and ctx.alcance("agenda", "crear") == "todos":
        if db.get(Area, datos.area_id) is None:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, "Área inexistente.")
        area_id = datos.area_id
    e = EventoAgenda(
        tipo=datos.tipo, titulo=datos.titulo, descripcion=datos.descripcion, inicio=datos.inicio, fin=datos.fin,
        todo_el_dia=datos.todo_el_dia, lugar=datos.lugar, area_id=area_id,
        persona_id=persona.id if persona else None, caso_id=caso.id if caso else None, creado_por=ctx.id,
    )
    e.participantes = [ParticipanteAgenda(usuario_id=u.id) for u in participantes]
    db.add(e)
    db.flush()
    audit.registrar(db, ctx, "crear", "agenda", e.id, e.persona_id, {"tipo": e.tipo, "inicio": e.inicio.isoformat(), "participantes": len(participantes)})
    db.commit()
    db.refresh(e)
    return _salida(db, ctx, e)


@router.get("/agenda/{evento_id}")
def ver(evento_id: uuid.UUID, ctx: Contexto = Depends(contexto), db: Session = Depends(get_db)):
    return _salida(db, ctx, _evento(db, ctx, evento_id))


@router.patch("/agenda/{evento_id}")
def modificar(evento_id: uuid.UUID, datos: EventoPatch, ctx: Contexto = Depends(contexto), db: Session = Depends(get_db)):
    e = _evento(db, ctx, evento_id, "modificar")
    if e.estado != "programado":
        raise HTTPException(status.HTTP_409_CONFLICT, "La actividad ya tiene resultado: no se puede modificar.")
    cambios = datos.model_dump(exclude_unset=True)
    antes = {"inicio": e.inicio.isoformat(), "titulo": e.titulo}
    if cambios.get("tipo") is not None and cambios["tipo"] not in TIPOS:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Tipo de actividad inválido.")
    if "persona_id" in cambios or "caso_id" in cambios:
        persona_id = cambios["persona_id"] if "persona_id" in cambios else e.persona_id
        if "caso_id" in cambios:
            caso_id = cambios["caso_id"]
        else:
            caso_id = None if persona_id != e.persona_id else e.caso_id  # al cambiar de legajo se suelta el caso anterior
        persona, caso = _validar_vinculo(db, ctx, persona_id, caso_id)
        e.persona_id, e.caso_id = (persona.id if persona else None), (caso.id if caso else None)
    if cambios.get("participantes") is not None:
        e.participantes = [ParticipanteAgenda(usuario_id=u.id) for u in _validar_participantes(db, ctx, cambios["participantes"])]
    for campo in ("tipo", "titulo", "inicio", "todo_el_dia"):
        if cambios.get(campo) is not None:
            setattr(e, campo, cambios[campo])
    for campo in ("descripcion", "fin", "lugar"):
        if campo in cambios:
            setattr(e, campo, cambios[campo])
    if e.fin is not None and e.fin < e.inicio:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "El fin es anterior al inicio.")
    audit.registrar(db, ctx, "modificar", "agenda", e.id, e.persona_id, {"antes": antes, "despues": {"inicio": e.inicio.isoformat(), "titulo": e.titulo}})
    db.commit()
    db.refresh(e)
    return _salida(db, ctx, e)


@router.post("/agenda/{evento_id}/resultado")
def registrar_resultado(evento_id: uuid.UUID, datos: ResultadoIn, ctx: Contexto = Depends(contexto), db: Session = Depends(get_db)):
    """Marca la actividad como realizada, no realizada o cancelada. Si está ligada a un caso, queda en su evolución."""
    e = _evento(db, ctx, evento_id, "modificar")
    if e.estado != "programado":
        raise HTTPException(status.HTTP_409_CONFLICT, "La actividad ya tiene resultado.")
    if datos.estado == "no_realizado" and not (datos.resultado or "").strip():
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Indique el motivo por el que no se realizó.")
    e.estado = datos.estado
    e.resultado = (datos.resultado or "").strip() or None
    e.resuelto_por = ctx.id
    e.resuelto_en = ahora()
    if e.caso_id and datos.estado != "cancelado":
        caso = db.get(Caso, e.caso_id)
        texto = f"{TIPOS[e.tipo]} {ESTADOS_FINALES[datos.estado]}" + (f" ({e.lugar})" if e.lugar else "") + (f": {e.resultado}" if e.resultado else ".")
        db.add(CasoEvolucion(caso_id=caso.id, texto=texto, fecha=e.inicio.date(), autor_id=ctx.id, usuario_id=ctx.id))
        registrar_actividad_caso(caso)
    audit.registrar(db, ctx, "resultado", "agenda", e.id, e.persona_id, {"estado": e.estado})
    db.commit()
    db.refresh(e)
    return _salida(db, ctx, e)

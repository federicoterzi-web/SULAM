"""Chat interno: conversaciones entre personas que usan SULAM (1 a 1 o en grupo).

- Cualquier persona con el permiso «chat · usar» puede escribirle a cualquier otra persona activa.
- Solo ven una conversación quienes participan en ella. Nadie más, tampoco la administración.
- La auditoría registra que se creó una conversación o se borró un mensaje, nunca el texto.
- Quien se suma a un grupo ve solo los mensajes posteriores a su ingreso.
- No hay tiempo real: la pantalla consulta cada pocos segundos. Los mensajes sin leer también
  salen en los avisos del navegador (sin el texto del mensaje).
"""

from __future__ import annotations

import uuid
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field
from sqlalchemy import and_, func, select
from sqlalchemy.orm import Session

from .. import audit
from ..db import get_db
from ..deps import contexto
from ..models import ChatConversacion, ChatMensaje, ChatParticipante, Usuario
from ..permissions import Contexto
from ..security import ahora
from ._comun import no_encontrado

router = APIRouter(prefix="/chat", tags=["chat"])

MAX_MENSAJE = 2000
MAX_GRUPO = 50
LIMITE_MENSAJES = 200


class NuevaConversacion(BaseModel):
    tipo: str = Field(pattern="^(directo|grupo)$")
    usuario_id: uuid.UUID | None = None
    titulo: str | None = Field(None, max_length=120)
    usuarios_ids: list[uuid.UUID] = Field(default_factory=list, max_length=MAX_GRUPO)


class NuevoMensaje(BaseModel):
    cuerpo: str = Field(min_length=1, max_length=MAX_MENSAJE)


class SumarGente(BaseModel):
    usuarios_ids: list[uuid.UUID] = Field(min_length=1, max_length=MAX_GRUPO)


def _persona(u: Usuario) -> dict:
    return {
        "id": str(u.id),
        "nombre_completo": u.nombre_completo,
        "area": u.area.nombre if u.area else None,
        "roles": sorted(r.nombre for r in u.roles),
    }


def _mia(db: Session, ctx: Contexto, conversacion_id: uuid.UUID) -> tuple[ChatConversacion, ChatParticipante]:
    c = db.get(ChatConversacion, conversacion_id)
    if c is None:
        raise no_encontrado("Conversación")
    mi = next((p for p in c.participantes if p.usuario_id == ctx.id), None)
    if mi is None:
        # No se revela que existe una conversación ajena.
        raise no_encontrado("Conversación")
    return c, mi


def _activos(db: Session, ids: list[uuid.UUID], excluir: uuid.UUID) -> list[Usuario]:
    unicos = {i for i in ids if i != excluir}
    if not unicos:
        return []
    usuarios = list(db.execute(select(Usuario).where(Usuario.id.in_(unicos), Usuario.activo.is_(True))).scalars())
    if len(usuarios) != len(unicos):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Hay personas inexistentes o dadas de baja.")
    return usuarios


def _mensaje_out(m: ChatMensaje, ctx: Contexto) -> dict:
    borrado = m.borrado_en is not None
    return {
        "id": str(m.id),
        "autor": {"id": str(m.autor.id), "nombre_completo": m.autor.nombre_completo},
        "cuerpo": None if borrado else m.cuerpo,
        "borrado": borrado,
        "creado_en": m.creado_en.isoformat(),
        "mio": m.autor_id == ctx.id,
    }


def _no_leidos(db: Session, usuario_id: uuid.UUID) -> dict[uuid.UUID, tuple[int, datetime]]:
    """Por conversación: cuántos mensajes ajenos sin leer y la fecha del último."""
    filas = db.execute(
        select(ChatMensaje.conversacion_id, func.count(), func.max(ChatMensaje.creado_en))
        .join(
            ChatParticipante,
            and_(ChatParticipante.conversacion_id == ChatMensaje.conversacion_id, ChatParticipante.usuario_id == usuario_id),
        )
        .where(
            ChatMensaje.autor_id != usuario_id,
            ChatMensaje.borrado_en.is_(None),
            ChatMensaje.creado_en > ChatParticipante.ultimo_leido_en,
            ChatMensaje.creado_en >= ChatParticipante.agregado_en,
        )
        .group_by(ChatMensaje.conversacion_id)
    ).all()
    return {c: (n, f) for c, n, f in filas}


def avisos_chat(db: Session, ctx: Contexto) -> list[str]:
    """Identificadores para los avisos del navegador: uno por conversación con mensajes sin leer."""
    if not ctx.tiene("chat", "usar"):
        return []
    return [f"{c}:{f.isoformat()}" for c, (_, f) in _no_leidos(db, ctx.id).items()][:200]


def _conversacion_out(db: Session, ctx: Contexto, c: ChatConversacion, sin_leer: dict) -> dict:
    otros = [p.usuario for p in c.participantes if p.usuario_id != ctx.id]
    ultimo = db.execute(
        select(ChatMensaje)
        .where(ChatMensaje.conversacion_id == c.id, ChatMensaje.borrado_en.is_(None))
        .order_by(ChatMensaje.creado_en.desc())
        .limit(1)
    ).scalar_one_or_none()
    return {
        "id": str(c.id),
        "tipo": c.tipo,
        "titulo": c.titulo if c.tipo == "grupo" else (otros[0].nombre_completo if otros else "—"),
        "participantes": [_persona(p.usuario) for p in c.participantes],
        "creada_por": str(c.creada_por),
        "ultimo": (
            {
                "cuerpo": ultimo.cuerpo[:140],
                "autor": ultimo.autor.nombre_completo,
                "mio": ultimo.autor_id == ctx.id,
                "creado_en": ultimo.creado_en.isoformat(),
            }
            if ultimo
            else None
        ),
        "no_leidos": sin_leer.get(c.id, (0, None))[0],
        "ultimo_mensaje_en": c.ultimo_mensaje_en.isoformat(),
    }


@router.get("/conversaciones")
def conversaciones(ctx: Contexto = Depends(contexto), db: Session = Depends(get_db)):
    ctx.requerir("chat", "usar")
    lista = list(
        db.execute(
            select(ChatConversacion)
            .join(ChatParticipante, ChatParticipante.conversacion_id == ChatConversacion.id)
            .where(ChatParticipante.usuario_id == ctx.id)
            .order_by(ChatConversacion.ultimo_mensaje_en.desc())
            .limit(150)
        ).scalars()
    )
    sin_leer = _no_leidos(db, ctx.id)
    return {
        "conversaciones": [_conversacion_out(db, ctx, c, sin_leer) for c in lista],
        "no_leidos": sum(n for n, _ in sin_leer.values()),
    }


@router.get("/no-leidos")
def no_leidos(ctx: Contexto = Depends(contexto), db: Session = Depends(get_db)):
    ctx.requerir("chat", "usar")
    sin_leer = _no_leidos(db, ctx.id)
    return {"mensajes": sum(n for n, _ in sin_leer.values()), "conversaciones": len(sin_leer)}


@router.get("/usuarios")
def usuarios(q: str = Query("", max_length=100), ctx: Contexto = Depends(contexto), db: Session = Depends(get_db)):
    """Personas a quienes se les puede escribir (activas, menos uno mismo)."""
    ctx.requerir("chat", "usar")
    consulta = select(Usuario).where(Usuario.activo.is_(True), Usuario.id != ctx.id)
    if q.strip():
        consulta = consulta.where(Usuario.nombre_completo.ilike(f"%{q.strip()}%"))
    return [_persona(u) for u in db.execute(consulta.order_by(Usuario.nombre_completo).limit(60)).scalars()]


@router.post("/conversaciones", status_code=201)
def crear(datos: NuevaConversacion, ctx: Contexto = Depends(contexto), db: Session = Depends(get_db)):
    ctx.requerir("chat", "usar")
    if datos.tipo == "directo":
        if datos.usuario_id is None or datos.usuario_id == ctx.id:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, "Elija a la persona a quien escribirle.")
        otro = _activos(db, [datos.usuario_id], ctx.id)[0]
        clave = ":".join(sorted((str(ctx.id), str(otro.id))))
        existente = db.execute(select(ChatConversacion).where(ChatConversacion.clave_directa == clave)).scalar_one_or_none()
        if existente is not None:
            return _conversacion_out(db, ctx, existente, _no_leidos(db, ctx.id))
        c = ChatConversacion(tipo="directo", clave_directa=clave, creada_por=ctx.id)
        c.participantes = [ChatParticipante(usuario_id=ctx.id), ChatParticipante(usuario_id=otro.id)]
    else:
        titulo = (datos.titulo or "").strip()
        if len(titulo) < 2:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, "Escriba el nombre del grupo.")
        miembros = _activos(db, datos.usuarios_ids, ctx.id)
        if not miembros:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, "Sume al menos a una persona al grupo.")
        c = ChatConversacion(tipo="grupo", titulo=titulo, creada_por=ctx.id)
        c.participantes = [ChatParticipante(usuario_id=ctx.id)] + [ChatParticipante(usuario_id=u.id) for u in miembros]
    db.add(c)
    db.flush()
    audit.registrar(
        db, ctx, "crear", "chat_conversacion", c.id, None,
        {"tipo": c.tipo, "titulo": c.titulo, "participantes": len(c.participantes)},
    )
    db.commit()
    db.refresh(c)
    return _conversacion_out(db, ctx, c, {})


@router.get("/conversaciones/{conversacion_id}/mensajes")
def mensajes(
    conversacion_id: uuid.UUID,
    despues: uuid.UUID | None = None,
    ctx: Contexto = Depends(contexto),
    db: Session = Depends(get_db),
):
    """Los últimos mensajes (o los posteriores a `despues`). Abrir la conversación la marca como leída."""
    ctx.requerir("chat", "usar")
    c, mi = _mia(db, ctx, conversacion_id)
    q = select(ChatMensaje).where(ChatMensaje.conversacion_id == c.id, ChatMensaje.creado_en >= mi.agregado_en)
    if despues is not None:
        previo = db.get(ChatMensaje, despues)
        if previo is not None and previo.conversacion_id == c.id:
            q = q.where(ChatMensaje.creado_en > previo.creado_en)
    lista = list(db.execute(q.order_by(ChatMensaje.creado_en.desc()).limit(LIMITE_MENSAJES)).scalars())[::-1]
    mi.ultimo_leido_en = ahora()
    db.commit()
    return {"mensajes": [_mensaje_out(m, ctx) for m in lista], "participantes": [_persona(p.usuario) for p in c.participantes]}


@router.post("/conversaciones/{conversacion_id}/mensajes", status_code=201)
def enviar(conversacion_id: uuid.UUID, datos: NuevoMensaje, ctx: Contexto = Depends(contexto), db: Session = Depends(get_db)):
    ctx.requerir("chat", "usar")
    c, mi = _mia(db, ctx, conversacion_id)
    cuerpo = datos.cuerpo.strip()
    if not cuerpo:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Escriba el mensaje.")
    if c.tipo == "directo":
        otro = next(p.usuario for p in c.participantes if p.usuario_id != ctx.id)
        if not otro.activo:
            raise HTTPException(status.HTTP_409_CONFLICT, "Esa persona ya no usa el sistema.")
    m = ChatMensaje(conversacion_id=c.id, autor_id=ctx.id, cuerpo=cuerpo)
    db.add(m)
    db.flush()
    db.refresh(m)
    c.ultimo_mensaje_en = m.creado_en
    mi.ultimo_leido_en = m.creado_en
    db.commit()
    db.refresh(m)
    return _mensaje_out(m, ctx)


@router.delete("/mensajes/{mensaje_id}")
def borrar(mensaje_id: uuid.UUID, ctx: Contexto = Depends(contexto), db: Session = Depends(get_db)):
    """Cada persona puede borrar sus propios mensajes (queda «mensaje borrado»)."""
    ctx.requerir("chat", "usar")
    m = db.get(ChatMensaje, mensaje_id)
    if m is None or m.autor_id != ctx.id:
        raise no_encontrado("Mensaje")
    if m.borrado_en is None:
        m.borrado_en = ahora()
        m.cuerpo = ""
        audit.registrar(db, ctx, "borrar", "chat_mensaje", m.id, None, {"conversacion": str(m.conversacion_id)})
        db.commit()
    return {"ok": True}


@router.post("/conversaciones/{conversacion_id}/participantes")
def sumar(conversacion_id: uuid.UUID, datos: SumarGente, ctx: Contexto = Depends(contexto), db: Session = Depends(get_db)):
    """Quien creó el grupo puede sumar más personas."""
    ctx.requerir("chat", "usar")
    c, _ = _mia(db, ctx, conversacion_id)
    if c.tipo != "grupo" or c.creada_por != ctx.id:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Solo quien creó el grupo puede sumar personas.")
    ya = {p.usuario_id for p in c.participantes}
    nuevos = [u for u in _activos(db, datos.usuarios_ids, ctx.id) if u.id not in ya]
    if len(c.participantes) + len(nuevos) > MAX_GRUPO:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, f"Un grupo admite hasta {MAX_GRUPO} personas.")
    for u in nuevos:
        c.participantes.append(ChatParticipante(usuario_id=u.id))
    audit.registrar(db, ctx, "sumar", "chat_conversacion", c.id, None, {"sumadas": [u.nombre_completo for u in nuevos]})
    db.commit()
    db.refresh(c)
    return _conversacion_out(db, ctx, c, {})


@router.post("/conversaciones/{conversacion_id}/salir")
def salir(conversacion_id: uuid.UUID, ctx: Contexto = Depends(contexto), db: Session = Depends(get_db)):
    ctx.requerir("chat", "usar")
    c, mi = _mia(db, ctx, conversacion_id)
    if c.tipo != "grupo":
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Solo se puede salir de un grupo.")
    c.participantes.remove(mi)
    audit.registrar(db, ctx, "salir", "chat_conversacion", c.id, None, {})
    db.commit()
    return {"ok": True}

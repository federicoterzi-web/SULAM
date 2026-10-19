"""Avisos para las notificaciones del navegador.

Devuelve, por cada tipo de aviso, los identificadores de lo que la persona tiene
pendiente. El navegador compara con lo que ya vio y avisa solo lo nuevo. No se
devuelven nombres ni datos de personas: solo identificadores y cantidades.
"""

from __future__ import annotations

from datetime import timedelta

from fastapi import APIRouter, Depends
from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from ..db import get_db
from ..deps import contexto
from ..models import RecursoDocumento, Caso, CasoAsignacion, CambioAgenda, EventoAgenda, EventoParticipacion, Novedad, ParticipanteAgenda, SolicitudPersonal
from ..permissions import Contexto, filtro_casos
from ..security import ahora
from .archivo import _para_mi
from .chat import avisos_chat
from .novedades import _es_destinatario, _mis_confirmaciones, _visibles
from .personal import _puede_aprobar

router = APIRouter(tags=["avisos"])

LIMITE = 200


def _ids(xs) -> list[str]:
    return [str(x) for x in list(xs)[:LIMITE]]


@router.get("/avisos")
def avisos(ctx: Contexto = Depends(contexto), db: Session = Depends(get_db)):
    salida: dict[str, list[str]] = {}

    # Novedades que piden confirmar la lectura.
    mias = _mis_confirmaciones(db, ctx)
    salida["novedades"] = _ids(
        n.id
        for n in db.execute(_visibles(ctx).where(Novedad.requiere_confirmacion)).scalars()
        if _es_destinatario(ctx, n) and n.id not in mias
    )

    # Chat interno: una entrada por conversación con mensajes sin leer (sin el texto).
    salida["chat"] = avisos_chat(db, ctx)

    # Carpetas físicas: para entregar y para recibir.
    entregar, recibir = _para_mi(db, ctx)
    salida["pases_entregar"] = _ids(p.id for p in entregar)
    salida["pases_recibir"] = _ids(p.id for p in recibir)

    # Personal: pedidos para aprobar y para registrar.
    if ctx.tiene("personal", "aprobar"):
        salida["personal_aprobar"] = _ids(
            s.id for s in db.execute(select(SolicitudPersonal).where(SolicitudPersonal.estado == "pendiente")).scalars() if _puede_aprobar(ctx, s)
        )
    if ctx.tiene("personal", "administrar"):
        salida["personal_registrar"] = _ids(
            db.execute(select(SolicitudPersonal.id).where(SolicitudPersonal.estado == "aprobada")).scalars()
        )

    # Respuestas a mis propios pedidos (última semana). El estado va en el id: si cambia, se vuelve a avisar.
    desde = ahora() - timedelta(days=7)
    salida["mis_pedidos"] = _ids(
        f"{s.id}:{s.estado}"
        for s in db.execute(
            select(SolicitudPersonal).where(
                SolicitudPersonal.pedido_por == ctx.id,
                SolicitudPersonal.estado.in_(("aprobada", "rechazada", "registrada")),
                SolicitudPersonal.decidido_en >= desde,
            )
        ).scalars()
    )

    # Casos: los que me asignaron y, para quien deriva, los que esperan asignación.
    if ctx.tiene("casos", "consultar"):
        salida["casos_asignados"] = _ids(
            db.execute(
                select(CasoAsignacion.caso_id)
                .join(Caso, Caso.id == CasoAsignacion.caso_id)
                .where(CasoAsignacion.usuario_id == ctx.id, CasoAsignacion.hasta.is_(None), Caso.estado != "cerrado")
            ).scalars()
        )
    alcance = ctx.alcance("casos", "derivar")
    if alcance and ctx.tiene("casos", "consultar"):
        salida["casos_sin_asignar"] = _ids(
            db.execute(
                select(Caso.id).where(
                    filtro_casos(ctx, alcance),
                    Caso.estado != "cerrado",
                    ~Caso.id.in_(select(CasoAsignacion.caso_id).where(CasoAsignacion.hasta.is_(None))),
                )
            ).scalars()
        )

    # Agenda: lo que tengo agendado para las próximas horas (solo actividades en las que participo). El inicio va en el id:
    # si se reprograma, se vuelve a avisar.
    if ctx.tiene("agenda", "consultar"):
        ahora_ = ahora()
        salida["agenda"] = _ids(
            f"{e.id}:{e.inicio.isoformat()}"
            for e in db.execute(
                select(EventoAgenda)
                .join(ParticipanteAgenda, ParticipanteAgenda.evento_id == EventoAgenda.id)
                .where(
                    ParticipanteAgenda.usuario_id == ctx.id,
                    EventoAgenda.estado == "programado",
                    EventoAgenda.inicio >= ahora_ - timedelta(hours=1),
                    EventoAgenda.inicio < ahora_ + timedelta(hours=36),
                )
                .order_by(EventoAgenda.inicio)
            ).scalars()
        )

    # Participación: eventos próximos que se reprogramaron o cambiaron de lugar en la última semana. Los recibe quien los creó,
    # quien participa y, si se sugiere la presencia de la Dirección, quien tiene alcance total. No avisa de los cambios propios.
    if ctx.tiene("participacion", "consultar"):
        ahora_ = ahora()
        condicion = or_(
            EventoAgenda.creado_por == ctx.id,
            EventoAgenda.id.in_(select(ParticipanteAgenda.evento_id).where(ParticipanteAgenda.usuario_id == ctx.id)),
        )
        if ctx.alcance("participacion", "consultar") == "todos":
            condicion = or_(condicion, EventoParticipacion.sugerir_directora.is_(True))
        cambios: dict = {}
        for c, e in db.execute(
            select(CambioAgenda, EventoAgenda)
            .join(EventoAgenda, EventoAgenda.id == CambioAgenda.evento_id)
            .join(EventoParticipacion, EventoParticipacion.evento_id == EventoAgenda.id)
            .where(
                condicion,
                EventoAgenda.estado == "programado",
                EventoAgenda.inicio >= ahora_,
                CambioAgenda.en >= ahora_ - timedelta(days=7),
                CambioAgenda.usuario_id != ctx.id,
            )
            .order_by(CambioAgenda.en)
        ):
            if set(c.cambios) & {"inicio", "fin", "lugar", "todo_el_dia"}:
                cambios[e.id] = f"{e.id}:{c.id}"  # queda el último cambio: si vuelve a cambiar, se avisa de nuevo
        salida["participacion_cambios"] = _ids(cambios.values())

    # Residencias: documentación vencida o que vence en los próximos 30 días (el documento más reciente de cada tipo).
    if ctx.tiene("residencias", "consultar"):
        hoy = ahora().date()
        ultimos: dict = {}
        for d in db.execute(select(RecursoDocumento).where(RecursoDocumento.vence.is_not(None)).order_by(RecursoDocumento.vence)).scalars():
            ultimos[(d.recurso_id, d.tipo)] = d
        salida["residencias_documentos"] = _ids(
            f"{d.id}:{'vencido' if d.vence < hoy else 'por_vencer'}" for d in ultimos.values() if d.vence <= hoy + timedelta(days=30)
        )

    return {"avisos": salida}

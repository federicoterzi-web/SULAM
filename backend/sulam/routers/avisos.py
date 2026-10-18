"""Avisos para las notificaciones del navegador.

Devuelve, por cada tipo de aviso, los identificadores de lo que la persona tiene
pendiente. El navegador compara con lo que ya vio y avisa solo lo nuevo. No se
devuelven nombres ni datos de personas: solo identificadores y cantidades.
"""

from __future__ import annotations

from datetime import timedelta

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..db import get_db
from ..deps import contexto
from ..models import Caso, CasoAsignacion, Novedad, SolicitudPersonal
from ..permissions import Contexto, filtro_casos
from ..security import ahora
from .archivo import _para_mi
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

    return {"avisos": salida}

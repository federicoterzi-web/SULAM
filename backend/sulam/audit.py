"""Registro de auditoría.

Se registran tanto las modificaciones como las consultas de información
sensible (apertura de legajos y casos, descargas, búsquedas). La tabla es de
solo agregado: un trigger en la base impide modificar o borrar filas.
"""

from __future__ import annotations

import uuid
from datetime import date, datetime
from typing import Any

from sqlalchemy.orm import Session

from .models import Auditoria


def _serializable(valor: Any) -> Any:
    if isinstance(valor, (uuid.UUID,)):
        return str(valor)
    if isinstance(valor, (datetime, date)):
        return valor.isoformat()
    if isinstance(valor, dict):
        return {k: _serializable(v) for k, v in valor.items()}
    if isinstance(valor, (list, tuple, set)):
        return [_serializable(v) for v in valor]
    return valor


def registrar(
    db: Session,
    ctx,
    accion: str,
    entidad: str,
    entidad_id: Any = None,
    persona_id: uuid.UUID | None = None,
    detalle: dict | None = None,
    *,
    usuario_id: uuid.UUID | None = None,
    ip: str | None = None,
) -> None:
    """Agrega una fila de auditoría a la transacción en curso.

    `ctx` puede ser un `Contexto` (usuario autenticado) o None (sistema).
    """
    db.add(
        Auditoria(
            usuario_id=usuario_id or getattr(ctx, "id", None),
            accion=accion,
            entidad=entidad,
            entidad_id=str(entidad_id) if entidad_id is not None else None,
            persona_id=persona_id,
            detalle=_serializable(detalle) if detalle else None,
            ip=ip or getattr(ctx, "ip", None),
        )
    )


def cambios(obj: Any, datos: dict) -> dict:
    """Aplica `datos` sobre `obj` y devuelve {campo: [anterior, nuevo]} de lo que cambió."""
    diff: dict[str, list] = {}
    for campo, nuevo in datos.items():
        anterior = getattr(obj, campo)
        if anterior != nuevo:
            diff[campo] = [_serializable(anterior), _serializable(nuevo)]
            setattr(obj, campo, nuevo)
    return diff

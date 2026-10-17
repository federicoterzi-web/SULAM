"""Catálogo de filtros de cada lista (campos, comparaciones y opciones)."""
from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from .. import filtros
from ..db import get_db
from ..deps import contexto
from ..permissions import Contexto

router = APIRouter(tags=["filtros"])


@router.get("/filtros/{lista}")
def catalogo(lista: str, ctx: Contexto = Depends(contexto), db: Session = Depends(get_db)):
    filtros.campos(lista)  # 404 si la lista no existe
    modulo, accion = filtros.LISTAS[lista][1]
    ctx.requerir(modulo, accion)
    return filtros.catalogo(db, lista)

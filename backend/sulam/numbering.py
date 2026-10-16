"""Numeración correlativa con bloqueo de fila (segura ante cargas simultáneas)."""

from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from .models import Contador


def siguiente(db: Session, clave: str) -> int:
    db.execute(insert(Contador).values(clave=clave, valor=0).on_conflict_do_nothing())
    fila = db.execute(select(Contador).where(Contador.clave == clave).with_for_update()).scalar_one()
    fila.valor += 1
    db.flush()
    return fila.valor


def _anio() -> int:
    return datetime.now(timezone.utc).astimezone().year


def numero_legajo(db: Session) -> str:
    return f"L-{siguiente(db, 'legajo'):06d}"


def numero_caso(db: Session) -> str:
    anio = _anio()
    return f"C-{anio}-{siguiente(db, f'caso-{anio}'):05d}"


def numero_ingreso(db: Session) -> str:
    anio = _anio()
    return f"ME-{anio}-{siguiente(db, f'ingreso-{anio}'):05d}"

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


def formato_caso(anio: int, numero: int) -> str:
    return f"C-{anio}-{numero:05d}"


def nueva_actuacion(db: Session, anio: int | None = None) -> tuple[int, int, str]:
    """Próxima Actuación N° del año (= número de caso). Saltea números ya usados
    por carátulas cargadas con su número original."""
    from .models import Caso

    anio = anio or _anio()
    while True:
        n = siguiente(db, f"caso-{anio}")
        numero = formato_caso(anio, n)
        if db.execute(select(Caso.id).where(Caso.numero == numero)).first() is None:
            return anio, n, numero


def numero_caso(db: Session) -> str:
    return nueva_actuacion(db)[2]


def proximo(db: Session, clave: str) -> int:
    fila = db.get(Contador, clave)
    return (fila.valor if fila else 0) + 1


def fijar_proximo(db: Session, clave: str, proximo_valor: int) -> None:
    db.execute(insert(Contador).values(clave=clave, valor=0).on_conflict_do_nothing())
    fila = db.execute(select(Contador).where(Contador.clave == clave).with_for_update()).scalar_one()
    fila.valor = proximo_valor - 1
    db.flush()


def numero_ingreso(db: Session) -> str:
    anio = _anio()
    return f"ME-{anio}-{siguiente(db, f'ingreso-{anio}'):05d}"

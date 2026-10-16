"""Detección de posibles legajos duplicados.

Criterios (ver FUNCTIONAL_SPEC.md §3.3):

1. Mismo número de documento en un legajo activo:
   - con el mismo tipo de documento  -> BLOQUEA el alta (no puede haber dos).
   - con otro tipo de documento       -> coincidencia "alta" (avisa).
2. Apellidos y nombres casi idénticos (similitud >= 0,90)   -> "alta".
3. Nombre parecido (>= 0,75) y misma fecha de nacimiento
   (o mismo año, si alguna de las fechas es aproximada)       -> "alta".
4. Mismo primer apellido y misma fecha de nacimiento         -> "media".

Las coincidencias que no bloquean obligan a confirmar el alta de manera
explícita; la confirmación queda en la auditoría.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from difflib import SequenceMatcher

from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from .models import Persona
from .textutil import escapar_like, normalizar


@dataclass
class Coincidencia:
    persona: Persona
    nivel: str  # "bloqueante" | "alta" | "media"
    motivos: list[str]
    similitud: float


def _clave_nombre(apellidos_norm: str, nombres_norm: str) -> str:
    return " ".join(sorted(f"{apellidos_norm} {nombres_norm}".split()))


def similitud(a: str, b: str) -> float:
    if not a or not b:
        return 0.0
    return SequenceMatcher(None, a, b).ratio()


def buscar_posibles_duplicados(
    db: Session,
    *,
    apellidos: str,
    nombres: str,
    tipo_documento: str | None,
    numero_documento: str | None,
    fecha_nacimiento: date | None,
    fecha_aproximada: bool = False,
    excluir_id=None,
) -> list[Coincidencia]:
    ap_n, no_n = normalizar(apellidos), normalizar(nombres)
    clave = _clave_nombre(ap_n, no_n)
    primer_apellido = ap_n.split(" ")[0] if ap_n else ""

    condiciones = []
    if numero_documento:
        condiciones.append(Persona.numero_documento == numero_documento)
    if primer_apellido:
        condiciones.append(Persona.apellidos_norm.like(escapar_like(primer_apellido[:4]) + "%"))
        # Por si apellidos y nombres fueron cargados invertidos.
        condiciones.append(Persona.nombres_norm.like(escapar_like(primer_apellido[:4]) + "%"))
    if fecha_nacimiento:
        condiciones.append(Persona.fecha_nacimiento == fecha_nacimiento)
    if not condiciones:
        return []

    q = select(Persona).where(Persona.unificada_en_id.is_(None), or_(*condiciones)).limit(500)
    if excluir_id is not None:
        q = q.where(Persona.id != excluir_id)

    resultado: list[Coincidencia] = []
    for p in db.execute(q).scalars():
        motivos: list[str] = []
        nivel: str | None = None
        sim = similitud(clave, _clave_nombre(p.apellidos_norm, p.nombres_norm))

        if numero_documento and p.numero_documento == numero_documento:
            if (p.tipo_documento or "") == (tipo_documento or ""):
                nivel = "bloqueante"
                motivos.append("Mismo tipo y número de documento")
            else:
                nivel = "alta"
                motivos.append("Mismo número de documento con otro tipo")

        if sim >= 0.90:
            nivel = nivel or "alta"
            motivos.append(f"Apellidos y nombres casi idénticos ({sim:.0%})")

        misma_fecha = False
        if fecha_nacimiento and p.fecha_nacimiento:
            if fecha_aproximada or p.fecha_nacimiento_aproximada:
                misma_fecha = fecha_nacimiento.year == p.fecha_nacimiento.year
            else:
                misma_fecha = fecha_nacimiento == p.fecha_nacimiento
        if misma_fecha and 0.75 <= sim < 0.90:
            nivel = nivel or "alta"
            motivos.append(f"Nombre parecido ({sim:.0%}) y misma fecha de nacimiento")
        elif misma_fecha and primer_apellido and p.apellidos_norm.split(" ")[0] == primer_apellido:
            nivel = nivel or "media"
            motivos.append("Mismo primer apellido y misma fecha de nacimiento")

        if nivel:
            resultado.append(Coincidencia(persona=p, nivel=nivel, motivos=motivos, similitud=sim))

    orden = {"bloqueante": 0, "alta": 1, "media": 2}
    resultado.sort(key=lambda c: (orden[c.nivel], -c.similitud))
    return resultado[:20]

"""Permisos de SULAM.

Cada permiso combina:
- módulo (área funcional),
- acción (consultar, crear, modificar, descargar, derivar, autorizar, administrar),
- alcance (propios < asignados < area < todos).

Un usuario puede tener varios roles; para cada (módulo, acción) vale el alcance
más amplio entre sus roles. Toda verificación se hace en el servidor.

Además del alcance, la información marcada como reservada (casos reservados,
tipos documentales reservados, personas vinculadas reservadas) solo es visible
con el permiso "reservados.consultar" o para quien tenga asignado el caso.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field

from fastapi import HTTPException, status
from sqlalchemy import false, or_, select, true
from sqlalchemy.orm import Session

from .models import Caso, CasoAsignacion, Persona, Sesion, Usuario

ALCANCES = ("propios", "asignados", "area", "todos")
_ORDEN = {a: i for i, a in enumerate(ALCANCES)}

CATALOGO: dict[str, dict] = {
    "personas": {
        "nombre": "Legajos (personas mayores y vinculados)",
        "acciones": ["consultar", "crear", "modificar", "administrar"],
    },
    "casos": {
        "nombre": "Gestión de casos",
        "acciones": ["consultar", "crear", "modificar", "derivar"],
    },
    "expedientes": {
        "nombre": "Expedientes",
        "acciones": ["consultar", "crear", "modificar"],
    },
    "mesa_entrada": {
        "nombre": "Mesa de Entrada",
        "acciones": ["consultar", "crear", "modificar"],
    },
    "documentos": {
        "nombre": "Gestión documental",
        "acciones": ["consultar", "crear", "descargar", "modificar", "administrar"],
    },
    "reservados": {
        "nombre": "Información reservada",
        "acciones": ["consultar"],
    },
    "auditoria": {
        "nombre": "Auditoría",
        "acciones": ["consultar"],
    },
    "administracion": {
        "nombre": "Administración del sistema",
        "acciones": ["administrar"],
    },
}

DESCRIPCION_ACCIONES = {
    "consultar": "Consultar",
    "crear": "Crear",
    "modificar": "Modificar",
    "descargar": "Descargar",
    "derivar": "Asignar / derivar",
    "autorizar": "Autorizar",
    "administrar": "Administrar",
}


def permiso_valido(modulo: str, accion: str, alcance: str) -> bool:
    return modulo in CATALOGO and accion in CATALOGO[modulo]["acciones"] and alcance in ALCANCES


@dataclass
class Contexto:
    """Usuario autenticado y sus permisos efectivos para la petición en curso."""

    usuario: Usuario
    sesion: Sesion | None = None
    ip: str | None = None
    permisos: dict[tuple[str, str], str] = field(default_factory=dict)

    @property
    def id(self) -> uuid.UUID:
        return self.usuario.id

    def alcance(self, modulo: str, accion: str) -> str | None:
        return self.permisos.get((modulo, accion))

    def tiene(self, modulo: str, accion: str) -> bool:
        return (modulo, accion) in self.permisos

    def requerir(self, modulo: str, accion: str) -> str:
        alc = self.alcance(modulo, accion)
        if alc is None:
            raise HTTPException(
                status.HTTP_403_FORBIDDEN,
                f"No tiene permiso para {DESCRIPCION_ACCIONES.get(accion, accion).lower()} "
                f"en {CATALOGO.get(modulo, {}).get('nombre', modulo)}.",
            )
        return alc


def permisos_efectivos(usuario: Usuario) -> dict[tuple[str, str], str]:
    efectivos: dict[tuple[str, str], str] = {}
    for rol in usuario.roles:
        if not rol.activo:
            continue
        for p in rol.permisos:
            clave = (p.modulo, p.accion)
            actual = efectivos.get(clave)
            if actual is None or _ORDEN[p.alcance] > _ORDEN[actual]:
                efectivos[clave] = p.alcance
    return efectivos


# ---------------------------------------------------------------------------
# Filtros SQL por alcance
# ---------------------------------------------------------------------------


def _casos_asignados(usuario_id: uuid.UUID):
    return select(CasoAsignacion.caso_id).where(
        CasoAsignacion.usuario_id == usuario_id, CasoAsignacion.hasta.is_(None)
    )


def filtro_casos(ctx: Contexto, alcance: str):
    if alcance == "todos":
        return true()
    if alcance == "area":
        if ctx.usuario.area_id is None:
            return or_(Caso.id.in_(_casos_asignados(ctx.id)), Caso.creado_por == ctx.id)
        return or_(
            Caso.area_id == ctx.usuario.area_id,
            Caso.id.in_(_casos_asignados(ctx.id)),
            Caso.creado_por == ctx.id,
        )
    if alcance == "asignados":
        return or_(Caso.id.in_(_casos_asignados(ctx.id)), Caso.creado_por == ctx.id)
    if alcance == "propios":
        return Caso.creado_por == ctx.id
    return false()


def filtro_personas(ctx: Contexto, alcance: str):
    if alcance == "todos":
        return true()
    personas_de_casos = select(Caso.persona_id).where(filtro_casos(ctx, alcance))
    return or_(Persona.id.in_(personas_de_casos), Persona.creado_por == ctx.id)


def persona_en_alcance(db: Session, ctx: Contexto, persona: Persona, alcance: str) -> bool:
    if alcance == "todos":
        return True
    q = select(Persona.id).where(Persona.id == persona.id, filtro_personas(ctx, alcance))
    return db.execute(q).first() is not None


def caso_en_alcance(db: Session, ctx: Contexto, caso: Caso, alcance: str) -> bool:
    if alcance == "todos":
        return True
    q = select(Caso.id).where(Caso.id == caso.id, filtro_casos(ctx, alcance))
    return db.execute(q).first() is not None


def requerir_persona(db: Session, ctx: Contexto, persona: Persona, modulo: str, accion: str) -> None:
    alcance = ctx.requerir(modulo, accion)
    if not persona_en_alcance(db, ctx, persona, alcance):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "El legajo está fuera de su alcance.")


def requerir_caso(db: Session, ctx: Contexto, caso: Caso, modulo: str, accion: str) -> None:
    alcance = ctx.requerir(modulo, accion)
    if not caso_en_alcance(db, ctx, caso, alcance):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "El caso está fuera de su alcance.")


# ---------------------------------------------------------------------------
# Información reservada
# ---------------------------------------------------------------------------


def esta_asignado(db: Session, ctx: Contexto, caso_id: uuid.UUID) -> bool:
    q = select(CasoAsignacion.id).where(
        CasoAsignacion.caso_id == caso_id,
        CasoAsignacion.usuario_id == ctx.id,
        CasoAsignacion.hasta.is_(None),
    )
    return db.execute(q).first() is not None


def asignado_a_persona(db: Session, ctx: Contexto, persona_id: uuid.UUID) -> bool:
    q = select(CasoAsignacion.id).join(Caso, Caso.id == CasoAsignacion.caso_id).where(
        Caso.persona_id == persona_id,
        CasoAsignacion.usuario_id == ctx.id,
        CasoAsignacion.hasta.is_(None),
    )
    return db.execute(q).first() is not None


def _reservados_de_toda_la_direccion(ctx: Contexto) -> bool:
    """«reservados.consultar» con alcance amplio: ve toda la información reservada.

    Con alcance «area» (jefes de departamento) solo ve la de los casos de su área.
    """
    alc = ctx.alcance("reservados", "consultar")
    return alc is not None and alc != "area"


def _reservados_del_area(ctx: Contexto) -> int | None:
    if ctx.alcance("reservados", "consultar") == "area":
        return ctx.usuario.area_id
    return None


def ve_caso_reservado(db: Session, ctx: Contexto, caso: Caso) -> bool:
    if not caso.reservado:
        return True
    if _reservados_de_toda_la_direccion(ctx) or caso.creado_por == ctx.id:
        return True
    area = _reservados_del_area(ctx)
    if area is not None and caso.area_id == area:
        return True
    return esta_asignado(db, ctx, caso.id)


def ve_reservado_de_persona(
    db: Session, ctx: Contexto, persona_id: uuid.UUID, caso_id: uuid.UUID | None = None
) -> bool:
    """Para documentos o vinculados reservados de una persona."""
    if _reservados_de_toda_la_direccion(ctx):
        return True
    area = _reservados_del_area(ctx)
    if area is not None:
        q = select(Caso.id).where(Caso.area_id == area)
        q = q.where(Caso.id == caso_id) if caso_id is not None else q.where(Caso.persona_id == persona_id)
        if db.execute(q).first() is not None:
            return True
    if caso_id is not None:
        return esta_asignado(db, ctx, caso_id)
    return asignado_a_persona(db, ctx, persona_id)


def filtro_casos_visibles_reservados(ctx: Contexto):
    """Condición SQL: el caso no es reservado o el usuario puede verlo."""
    if _reservados_de_toda_la_direccion(ctx):
        return true()
    condiciones = [
        Caso.reservado.is_(False),
        Caso.creado_por == ctx.id,
        Caso.id.in_(_casos_asignados(ctx.id)),
    ]
    area = _reservados_del_area(ctx)
    if area is not None:
        condiciones.append(Caso.area_id == area)
    return or_(*condiciones)


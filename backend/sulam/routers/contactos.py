"""Directorio de contactos: técnicos de gobiernos locales y referentes de otras
instituciones con las que se articula. Usa los permisos del módulo «recursos»."""

from __future__ import annotations

import json
import re
import uuid

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import Field, field_validator
from datetime import date

from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from .. import audit, filtros
from ._comun import obtener_caso, registrar_actividad_caso
from ..db import get_db
from ..deps import contexto
from ..formularios import DEPARTAMENTOS
from ..models import Articulacion, Caso, Contacto, Persona, Recurso
from ..permissions import Contexto, filtro_casos, requerir_caso
from ..schemas import Entrada, _vacio_a_none
from ..security import ahora
from ..textutil import escapar_like, normalizar
from .recursos import CATEGORIAS, CODIGOS_ORIGEN

router = APIRouter(tags=["recursos"])

CAMPOS = (
    "nombre", "cargo", "institucion", "categoria", "recurso_id", "localidad", "departamento",
    "telefono", "telefono_alternativo", "whatsapp", "email", "temas", "observaciones", "origen", "origen_detalle",
    "activo",
)


class ContactoIn(Entrada):
    nombre: str = Field(min_length=2, max_length=200)
    cargo: str | None = Field(default=None, max_length=200)
    institucion: str | None = Field(default=None, max_length=300)
    categoria: str | None = None
    recurso_id: uuid.UUID | None = None
    localidad: str | None = Field(default=None, max_length=200)
    departamento: str | None = Field(default=None, max_length=100)
    telefono: str | None = Field(default=None, max_length=100)
    telefono_alternativo: str | None = Field(default=None, max_length=100)
    whatsapp: str | None = Field(default=None, max_length=30)
    email: str | None = Field(default=None, max_length=200)
    temas: str | None = Field(default=None, max_length=3000)
    observaciones: str | None = Field(default=None, max_length=5000)
    origen: str | None = None
    origen_detalle: str | None = Field(default=None, max_length=300)
    activo: bool = True

    _limpiar = field_validator(
        "origen", "origen_detalle", "cargo", "institucion", "categoria", "localidad", "departamento", "telefono",
        "telefono_alternativo", "whatsapp", "email", "temas", "observaciones", mode="before",
    )(_vacio_a_none)

    @field_validator("whatsapp")
    @classmethod
    def _whatsapp(cls, v):
        # Se guarda solo con dígitos, en formato internacional (549 + característica + número).
        if v is None:
            return v
        digitos = re.sub(r"\D", "", v)
        if len(digitos) < 10:
            raise ValueError("WhatsApp: escriba el número completo con característica.")
        if digitos.startswith("54"):
            return digitos
        nacional = digitos.lstrip("0")
        # 0381 15 4001111 -> 381 4001111: el «15» de los celulares no va en WhatsApp.
        if len(nacional) == 12:
            for largo_caracteristica in (2, 3, 4):
                if nacional[largo_caracteristica : largo_caracteristica + 2] == "15":
                    nacional = nacional[:largo_caracteristica] + nacional[largo_caracteristica + 2 :]
                    break
        if len(nacional) != 10:
            raise ValueError("WhatsApp: escriba característica y número (ej.: 381 15 400-1111).")
        return "549" + nacional


class ContactoPatch(ContactoIn):
    nombre: str | None = Field(default=None, min_length=2, max_length=200)  # type: ignore[assignment]
    activo: bool | None = None  # type: ignore[assignment]


def _validar(db: Session, v: dict) -> None:
    if v.get("categoria") is not None and v["categoria"] not in CATEGORIAS:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Categoría inválida.")
    if v.get("origen") is not None and v["origen"] not in CODIGOS_ORIGEN:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Origen inválido.")
    if v.get("departamento") is not None and v["departamento"] not in DEPARTAMENTOS:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Departamento inválido.")
    if v.get("recurso_id") is not None and db.get(Recurso, v["recurso_id"]) is None:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "El recurso vinculado no existe.")


def contacto_out(c: Contacto, articulaciones: int = 0) -> dict:
    d = {k: getattr(c, k) for k in CAMPOS}
    d["articulaciones"] = articulaciones
    d["id"] = str(c.id)
    d["recurso_id"] = str(c.recurso_id) if c.recurso_id else None
    d["recurso"] = {"id": str(c.recurso.id), "nombre": c.recurso.nombre, "tipo": c.recurso.tipo} if c.recurso else None
    d["creado_por"] = str(c.creado_por) if c.creado_por else None
    d["actualizado_en"] = c.actualizado_en.isoformat() if c.actualizado_en else None
    return d


@router.get("/contactos")
def listar(
    q: str = Query("", max_length=200),
    departamento: str | None = None,
    categoria: str | None = None,
    recurso_id: uuid.UUID | None = None,
    inactivos: bool = False,
    f: str | None = Query(None, max_length=20000),
    con_total: bool = False,
    ctx: Contexto = Depends(contexto),
    db: Session = Depends(get_db),
):
    ctx.requerir("recursos", "consultar")
    consulta = filtros.aplicar("contactos", select(Contacto), f)
    if not inactivos:
        consulta = consulta.where(Contacto.activo)
    if departamento:
        consulta = consulta.where(Contacto.departamento == departamento)
    if categoria:
        consulta = consulta.where(Contacto.categoria == categoria)
    if recurso_id:
        consulta = consulta.where(Contacto.recurso_id == recurso_id)
    if q.strip():
        t = "%" + escapar_like(normalizar(q)) + "%"
        crudo = "%" + escapar_like(q.strip()) + "%"
        consulta = consulta.where(
            or_(
                Contacto.nombre_norm.like(t),
                Contacto.institucion_norm.like(t),
                Contacto.cargo.ilike(crudo),
                Contacto.localidad.ilike(crudo),
                Contacto.temas.ilike(crudo),
            )
        )
    consulta = consulta.order_by(Contacto.departamento.nulls_last(), Contacto.institucion_norm, Contacto.nombre_norm).limit(1000)
    cantidad = filtros.total(db, consulta) if con_total else None
    contactos = list(db.execute(consulta).unique().scalars())
    usos = dict(
        db.execute(
            select(Articulacion.contacto_id, func.count(Articulacion.id))
            .where(Articulacion.contacto_id.in_([c.id for c in contactos]))
            .group_by(Articulacion.contacto_id)
        ).all()
    )
    items = [contacto_out(c, usos.get(c.id, 0)) for c in contactos]
    return {"total": cantidad, "items": items} if con_total else items


@router.post("/contactos", status_code=201)
def crear(datos: ContactoIn, ctx: Contexto = Depends(contexto), db: Session = Depends(get_db)):
    ctx.requerir("recursos", "crear")
    v = datos.model_dump()
    _validar(db, v)
    c = Contacto(
        **v,
        nombre_norm=normalizar(v["nombre"]),
        institucion_norm=normalizar(v["institucion"]) if v["institucion"] else None,
        creado_por=ctx.id,
        actualizado_por=ctx.id,
    )
    db.add(c)
    db.flush()
    audit.registrar(db, ctx, "crear", "contacto", c.id, detalle={"nombre": c.nombre, "institucion": c.institucion})
    db.commit()
    db.refresh(c)
    return contacto_out(c)


@router.get("/contactos/{contacto_id}")
def ver(contacto_id: uuid.UUID, ctx: Contexto = Depends(contexto), db: Session = Depends(get_db)):
    ctx.requerir("recursos", "consultar")
    c = db.get(Contacto, contacto_id)
    if c is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Contacto inexistente.")
    return contacto_out(c)


@router.patch("/contactos/{contacto_id}")
def modificar(
    contacto_id: uuid.UUID, datos: ContactoPatch, ctx: Contexto = Depends(contexto), db: Session = Depends(get_db)
):
    alcance = ctx.requerir("recursos", "modificar")
    c = db.get(Contacto, contacto_id)
    if c is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Contacto inexistente.")
    if alcance == "propios" and c.creado_por != ctx.id:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Solo puede modificar los contactos que cargó usted.")
    cambios = datos.model_dump(exclude_unset=True)
    _validar(db, {**{k: getattr(c, k) for k in CAMPOS}, **cambios})
    diff = {}
    for campo, valor in cambios.items():
        if campo in ("nombre", "activo") and valor is None:
            continue
        if getattr(c, campo) != valor:
            diff[campo] = [getattr(c, campo), valor]
            setattr(c, campo, valor)
    if diff:
        c.nombre_norm = normalizar(c.nombre)
        c.institucion_norm = normalizar(c.institucion) if c.institucion else None
        c.actualizado_por = ctx.id
        c.actualizado_en = ahora()
        audit.registrar(db, ctx, "modificar", "contacto", c.id, detalle=json.loads(json.dumps(diff, default=str)))
        db.commit()
        db.refresh(c)
    return contacto_out(c)



# ---------------------------------------------------------------- articulaciones en casos


class ArticulacionIn(Entrada):
    contacto_id: uuid.UUID | None = None
    recurso_id: uuid.UUID | None = None
    # Si la persona todavía no está en el directorio, se la agrega al registrar la articulación.
    nuevo_contacto: ContactoIn | None = None
    fecha: date | None = None
    motivo: str | None = Field(default=None, max_length=3000)
    resultado: str | None = Field(default=None, max_length=3000)

    _limpiar = field_validator("motivo", "resultado", mode="before")(_vacio_a_none)


def articulacion_out(a: Articulacion) -> dict:
    return {
        "id": a.id,
        "caso_id": str(a.caso_id),
        "fecha": a.fecha.isoformat(),
        "motivo": a.motivo,
        "resultado": a.resultado,
        "contacto": contacto_out(a.contacto) if a.contacto else None,
        "recurso": {"id": str(a.recurso.id), "nombre": a.recurso.nombre, "tipo": a.recurso.tipo} if a.recurso else None,
        "usuario": {"id": str(a.usuario.id), "nombre_completo": a.usuario.nombre_completo} if a.usuario else None,
        "en": a.en.isoformat(),
    }


@router.get("/casos/{caso_id}/articulaciones")
def articulaciones_del_caso(caso_id: uuid.UUID, ctx: Contexto = Depends(contexto), db: Session = Depends(get_db)):
    caso = obtener_caso(db, caso_id)
    requerir_caso(db, ctx, caso, "casos", "consultar")
    filas = db.execute(
        select(Articulacion).where(Articulacion.caso_id == caso.id).order_by(Articulacion.fecha.desc(), Articulacion.id.desc())
    ).unique().scalars()
    return [articulacion_out(a) for a in filas]


@router.post("/casos/{caso_id}/articulaciones", status_code=201)
def registrar_articulacion(
    caso_id: uuid.UUID, datos: ArticulacionIn, ctx: Contexto = Depends(contexto), db: Session = Depends(get_db)
):
    caso = obtener_caso(db, caso_id)
    requerir_caso(db, ctx, caso, "casos", "modificar")
    contacto_id = datos.contacto_id
    if datos.nuevo_contacto is not None:
        ctx.requerir("recursos", "crear")
        v = datos.nuevo_contacto.model_dump()
        v["origen"] = v.get("origen") or "articulacion"
        v["origen_detalle"] = v.get("origen_detalle") or f"Caso {caso.numero_actuacion}/{caso.anio_actuacion}"
        _validar(db, v)
        nuevo = Contacto(
            **v,
            nombre_norm=normalizar(v["nombre"]),
            institucion_norm=normalizar(v["institucion"]) if v["institucion"] else None,
            creado_por=ctx.id,
            actualizado_por=ctx.id,
        )
        db.add(nuevo)
        db.flush()
        audit.registrar(db, ctx, "crear", "contacto", nuevo.id, detalle={"nombre": nuevo.nombre, "desde_caso": caso.numero})
        contacto_id = nuevo.id
    if contacto_id is None and datos.recurso_id is None:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Indique con quién se articuló.")
    if contacto_id is not None and db.get(Contacto, contacto_id) is None:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "El contacto no existe.")
    if datos.recurso_id is not None and db.get(Recurso, datos.recurso_id) is None:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "El recurso no existe.")
    a = Articulacion(
        caso_id=caso.id,
        contacto_id=contacto_id,
        recurso_id=datos.recurso_id,
        fecha=datos.fecha or ahora().astimezone().date(),
        motivo=datos.motivo,
        resultado=datos.resultado,
        usuario_id=ctx.id,
    )
    db.add(a)
    registrar_actividad_caso(caso)
    db.flush()
    audit.registrar(
        db, ctx, "articular", "caso", caso.id, caso.persona_id,
        {"contacto_id": str(contacto_id) if contacto_id else None, "recurso_id": str(datos.recurso_id) if datos.recurso_id else None},
    )
    db.commit()
    db.refresh(a)
    return articulacion_out(a)


@router.get("/contactos/{contacto_id}/articulaciones")
def casos_del_contacto(contacto_id: uuid.UUID, ctx: Contexto = Depends(contexto), db: Session = Depends(get_db)):
    """En qué casos se articuló con este contacto (dentro del alcance de consulta del usuario)."""
    ctx.requerir("recursos", "consultar")
    alcance = ctx.alcance("casos", "consultar")
    if alcance is None:
        return []
    filas = db.execute(
        select(Articulacion, Caso, Persona)
        .join(Caso, Caso.id == Articulacion.caso_id)
        .join(Persona, Persona.id == Caso.persona_id)
        .where(Articulacion.contacto_id == contacto_id, filtro_casos(ctx, alcance))
        .order_by(Articulacion.fecha.desc())
    ).unique().all()
    return [
        {
            "fecha": a.fecha.isoformat(),
            "motivo": a.motivo,
            "resultado": a.resultado,
            "caso": {"id": str(c.id), "actuacion": f"{c.numero_actuacion}/{c.anio_actuacion}"},
            "persona": f"{p.apellidos.upper()}, {p.nombres}",
        }
        for a, c, p in filas
    ]

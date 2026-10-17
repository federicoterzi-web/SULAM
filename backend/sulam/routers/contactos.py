"""Directorio de contactos: técnicos de gobiernos locales y referentes de otras
instituciones con las que se articula. Usa los permisos del módulo «recursos»."""

from __future__ import annotations

import json
import re
import uuid

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import Field, field_validator
from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from .. import audit
from ..db import get_db
from ..deps import contexto
from ..formularios import DEPARTAMENTOS
from ..models import Contacto, Recurso
from ..permissions import Contexto
from ..schemas import Entrada, _vacio_a_none
from ..security import ahora
from ..textutil import escapar_like, normalizar
from .recursos import CATEGORIAS

router = APIRouter(tags=["recursos"])

CAMPOS = (
    "nombre", "cargo", "institucion", "categoria", "recurso_id", "localidad", "departamento",
    "telefono", "telefono_alternativo", "whatsapp", "email", "temas", "observaciones", "activo",
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
    activo: bool = True

    _limpiar = field_validator(
        "cargo", "institucion", "categoria", "localidad", "departamento", "telefono",
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
    if v.get("departamento") is not None and v["departamento"] not in DEPARTAMENTOS:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Departamento inválido.")
    if v.get("recurso_id") is not None and db.get(Recurso, v["recurso_id"]) is None:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "El recurso vinculado no existe.")


def contacto_out(c: Contacto) -> dict:
    d = {k: getattr(c, k) for k in CAMPOS}
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
    ctx: Contexto = Depends(contexto),
    db: Session = Depends(get_db),
):
    ctx.requerir("recursos", "consultar")
    consulta = select(Contacto)
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
    return [contacto_out(c) for c in db.execute(consulta).unique().scalars()]


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

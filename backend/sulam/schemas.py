"""Esquemas de entrada de la API (validación con Pydantic)."""

from __future__ import annotations

import uuid
from datetime import date, datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

TIPOS_DOCUMENTO = ("DNI", "LC", "LE", "CI", "Pasaporte", "Otro")


class Entrada(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


def _vacio_a_none(v):
    if isinstance(v, str) and v.strip() == "":
        return None
    return v


# ---------------------------------------------------------------- auth


class LoginIn(Entrada):
    usuario: str = Field(min_length=1, max_length=80)
    password: str = Field(min_length=1, max_length=200)


class CambioPasswordIn(Entrada):
    password_actual: str
    password_nueva: str = Field(max_length=200)


# ---------------------------------------------------------------- personas


class PersonaBase(Entrada):
    apellidos: str = Field(min_length=1, max_length=200)
    nombres: str = Field(min_length=1, max_length=200)
    tipo_documento: Literal["DNI", "LC", "LE", "CI", "Pasaporte", "Otro"] | None = None
    numero_documento: str | None = Field(default=None, max_length=30)
    sin_documento: bool = False
    motivo_sin_documento: str | None = Field(default=None, max_length=2000)
    fecha_nacimiento: date | None = None
    fecha_nacimiento_aproximada: bool = False
    domicilio: str | None = Field(default=None, max_length=2000)
    localidad: str | None = Field(default=None, max_length=200)
    telefono: str | None = Field(default=None, max_length=100)
    observaciones: str | None = Field(default=None, max_length=5000)

    _limpiar = field_validator(
        "numero_documento", "motivo_sin_documento", "domicilio", "localidad", "telefono",
        "observaciones", mode="before",
    )(_vacio_a_none)


class PersonaIn(PersonaBase):
    confirmar_posible_duplicado: bool = False
    motivo_confirmacion: str | None = Field(default=None, max_length=1000)


class PersonaPatch(Entrada):
    apellidos: str | None = Field(default=None, min_length=1, max_length=200)
    nombres: str | None = Field(default=None, min_length=1, max_length=200)
    tipo_documento: Literal["DNI", "LC", "LE", "CI", "Pasaporte", "Otro"] | None = None
    numero_documento: str | None = Field(default=None, max_length=30)
    sin_documento: bool | None = None
    motivo_sin_documento: str | None = Field(default=None, max_length=2000)
    fecha_nacimiento: date | None = None
    fecha_nacimiento_aproximada: bool | None = None
    domicilio: str | None = Field(default=None, max_length=2000)
    localidad: str | None = Field(default=None, max_length=200)
    telefono: str | None = Field(default=None, max_length=100)
    observaciones: str | None = Field(default=None, max_length=5000)
    motivo_cambio: str | None = Field(default=None, max_length=1000)
    confirmar_posible_duplicado: bool = False

    _limpiar = field_validator(
        "numero_documento", "motivo_sin_documento", "domicilio", "localidad", "telefono",
        "observaciones", "motivo_cambio", mode="before",
    )(_vacio_a_none)


class VerificarDuplicadosIn(Entrada):
    apellidos: str
    nombres: str
    tipo_documento: str | None = None
    numero_documento: str | None = None
    fecha_nacimiento: date | None = None
    fecha_nacimiento_aproximada: bool = False
    excluir_id: uuid.UUID | None = None


class UnificarIn(Entrada):
    legajo_a_absorber_id: uuid.UUID
    motivo: str = Field(min_length=5, max_length=2000)


class VinculadoIn(Entrada):
    tipo_vinculo_id: int
    es_institucion: bool = False
    apellidos: str | None = Field(default=None, max_length=200)
    nombres: str | None = Field(default=None, max_length=200)
    nombre_institucion: str | None = Field(default=None, max_length=300)
    numero_documento: str | None = Field(default=None, max_length=30)
    telefono: str | None = Field(default=None, max_length=100)
    domicilio: str | None = Field(default=None, max_length=2000)
    observaciones: str | None = Field(default=None, max_length=5000)
    reservado: bool = False

    _limpiar = field_validator(
        "apellidos", "nombres", "nombre_institucion", "numero_documento", "telefono",
        "domicilio", "observaciones", mode="before",
    )(_vacio_a_none)


class VinculadoPatch(Entrada):
    tipo_vinculo_id: int | None = None
    apellidos: str | None = Field(default=None, max_length=200)
    nombres: str | None = Field(default=None, max_length=200)
    nombre_institucion: str | None = Field(default=None, max_length=300)
    numero_documento: str | None = Field(default=None, max_length=30)
    telefono: str | None = Field(default=None, max_length=100)
    domicilio: str | None = Field(default=None, max_length=2000)
    observaciones: str | None = Field(default=None, max_length=5000)
    reservado: bool | None = None
    activo: bool | None = None


# ---------------------------------------------------------------- casos


class CasoIn(Entrada):
    persona_id: uuid.UUID
    area_id: int | None = None
    motivo: str | None = Field(default=None, max_length=5000)
    reservado: bool = False
    responsable_id: uuid.UUID | None = None
    ingreso_id: uuid.UUID | None = None


class CasoPatch(Entrada):
    area_id: int | None = None
    motivo: str | None = Field(default=None, max_length=5000)
    reservado: bool | None = None


class CambioEstadoIn(Entrada):
    estado: Literal["abierto", "en_seguimiento", "pausado", "cerrado"]
    motivo: str | None = Field(default=None, max_length=2000)


class AsignacionIn(Entrada):
    usuario_id: uuid.UUID
    motivo: str | None = Field(default=None, max_length=2000)
    reemplazar_actuales: bool = False


class FinAsignacionIn(Entrada):
    motivo: str | None = Field(default=None, max_length=2000)


# ---------------------------------------------------------------- expedientes


class ExpedienteIn(Entrada):
    persona_id: uuid.UUID
    caso_id: uuid.UUID | None = None
    numero: str = Field(min_length=1, max_length=100)
    tipo: Literal["administrativo", "judicial"]
    organismo: str | None = Field(default=None, max_length=300)
    caratula: str | None = Field(default=None, max_length=2000)
    observaciones: str | None = Field(default=None, max_length=5000)


class ExpedientePatch(Entrada):
    caso_id: uuid.UUID | None = None
    numero: str | None = Field(default=None, min_length=1, max_length=100)
    tipo: Literal["administrativo", "judicial"] | None = None
    organismo: str | None = Field(default=None, max_length=300)
    caratula: str | None = Field(default=None, max_length=2000)
    observaciones: str | None = Field(default=None, max_length=5000)


# ---------------------------------------------------------------- mesa de entrada


class IngresoIn(Entrada):
    fecha_ingreso: datetime | None = None
    remitente: str | None = Field(default=None, max_length=300)
    tipo_documental_id: int | None = None
    asunto: str = Field(min_length=1, max_length=5000)
    folios: int | None = Field(default=None, ge=0, le=100000)
    persona_mencionada: str | None = Field(default=None, max_length=300)
    documento_mencionado: str | None = Field(default=None, max_length=30)
    numero_expediente_externo: str | None = Field(default=None, max_length=100)
    observaciones: str | None = Field(default=None, max_length=5000)
    persona_id: uuid.UUID | None = None


class VincularIngresoIn(Entrada):
    persona_id: uuid.UUID
    caso_id: uuid.UUID | None = None
    expediente_id: uuid.UUID | None = None


# ---------------------------------------------------------------- documentos


class DocumentoPatch(Entrada):
    titulo: str | None = Field(default=None, min_length=1, max_length=300)
    descripcion: str | None = Field(default=None, max_length=5000)
    tipo_documental_id: int | None = None
    caso_id: uuid.UUID | None = None
    expediente_id: uuid.UUID | None = None
    reservado: bool | None = None


class EliminarDocumentoIn(Entrada):
    motivo: str = Field(min_length=5, max_length=2000)


# ---------------------------------------------------------------- administración


class PermisoIn(Entrada):
    modulo: str
    accion: str
    alcance: Literal["propios", "asignados", "area", "todos"]


class RolIn(Entrada):
    nombre: str = Field(min_length=2, max_length=120)
    descripcion: str | None = Field(default=None, max_length=2000)
    activo: bool = True
    permisos: list[PermisoIn] = []


class UsuarioIn(Entrada):
    usuario: str = Field(min_length=3, max_length=80, pattern=r"^[a-zA-Z0-9._-]+$")
    nombre_completo: str = Field(min_length=2, max_length=200)
    email: str | None = Field(default=None, max_length=200)
    area_id: int | None = None
    roles: list[int] = []
    password_inicial: str = Field(max_length=200)


class UsuarioPatch(Entrada):
    nombre_completo: str | None = Field(default=None, min_length=2, max_length=200)
    email: str | None = Field(default=None, max_length=200)
    area_id: int | None = None
    roles: list[int] | None = None
    activo: bool | None = None


class ResetPasswordIn(Entrada):
    password_temporal: str = Field(max_length=200)


class CatalogoIn(Entrada):
    nombre: str = Field(min_length=2, max_length=200)
    activo: bool = True
    reservado: bool | None = None

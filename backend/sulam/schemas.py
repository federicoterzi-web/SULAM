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


def _cuil(v):
    """CUIL con guiones (20-12345678-6) y dígito verificador correcto."""
    if v is None or (isinstance(v, str) and not v.strip()):
        return None
    from .anses import cuil_valido, formatear

    if not cuil_valido(v):
        raise ValueError("CUIL inválido: revise los 11 números (el último es el dígito verificador).")
    return formatear(v)


# ---------------------------------------------------------------- auth


class LoginIn(Entrada):
    usuario: str = Field(min_length=1, max_length=80)
    password: str = Field(min_length=1, max_length=200)
    # "movil": la sesión se cierra antes por inactividad (teléfonos que se pierden o se prestan).
    dispositivo: Literal["escritorio", "movil"] = "escritorio"


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
    genero: str | None = None
    barrio: str | None = Field(default=None, max_length=200)
    departamento: str | None = Field(default=None, max_length=100)
    cud: str | None = None
    cobertura_salud: list[str] | None = None
    obra_social: str | None = Field(default=None, max_length=200)
    cobertura_previsional: list[str] | None = None
    trabajo_informal: bool | None = None
    discapacidades: list[str] | None = None
    cuil: str | None = Field(default=None, max_length=20)

    _limpiar = field_validator(
        "numero_documento", "motivo_sin_documento", "domicilio", "localidad", "telefono",
        "observaciones", "genero", "barrio", "departamento", "cud", "obra_social", mode="before",
    )(_vacio_a_none)
    _validar_cuil = field_validator("cuil", mode="before")(_cuil)


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
    genero: str | None = None
    barrio: str | None = Field(default=None, max_length=200)
    departamento: str | None = Field(default=None, max_length=100)
    cud: str | None = None
    cobertura_salud: list[str] | None = None
    obra_social: str | None = Field(default=None, max_length=200)
    cobertura_previsional: list[str] | None = None
    trabajo_informal: bool | None = None
    discapacidades: list[str] | None = None
    cuil: str | None = Field(default=None, max_length=20)
    motivo_cambio: str | None = Field(default=None, max_length=1000)
    confirmar_posible_duplicado: bool = False

    _limpiar = field_validator(
        "numero_documento", "motivo_sin_documento", "domicilio", "localidad", "telefono",
        "observaciones", "motivo_cambio", "genero", "barrio", "departamento", "cud", "obra_social",
        mode="before",
    )(_vacio_a_none)
    _validar_cuil = field_validator("cuil", mode="before")(_cuil)


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
    activo: bool | None = None


# ---------------------------------------------------------------- casos


class PersonaCaratula(Entrada):
    """Datos de la persona que figuran en la carátula; actualizan el legajo."""

    genero: str | None = None
    domicilio: str | None = Field(default=None, max_length=2000)
    localidad: str | None = Field(default=None, max_length=200)
    departamento: str | None = Field(default=None, max_length=100)
    telefono: str | None = Field(default=None, max_length=100)
    cud: str | None = None
    cobertura_salud: list[str] | None = None
    obra_social: str | None = Field(default=None, max_length=200)

    _limpiar = field_validator(
        "genero", "domicilio", "localidad", "departamento", "telefono", "cud", "obra_social",
        mode="before",
    )(_vacio_a_none)


class CaratulaCampos(Entrada):
    """Información administrativa del modelo de carátula de legajo."""

    numero_actuacion: int | None = Field(default=None, ge=1, le=9999999)
    anio_actuacion: int | None = Field(default=None, ge=1990, le=2100)
    fecha_ingreso: date | None = None
    antecedentes: bool | None = None
    fecha_ultimo_ingreso: date | None = None
    motivo: str | None = Field(default=None, max_length=5000)
    tipo_ingreso: str | None = None
    tipo_ingreso_detalle: str | None = None
    derivado_por: str | None = None
    derivado_por_detalle: str | None = Field(default=None, max_length=300)
    indicadores: list[str] | None = None
    intervenciones: list[str] | None = None
    intervencion_derivacion: str | None = Field(default=None, max_length=300)
    intervencion_otro: str | None = Field(default=None, max_length=300)
    persona: PersonaCaratula | None = None

    _limpiar = field_validator(
        "motivo", "tipo_ingreso", "tipo_ingreso_detalle", "derivado_por",
        "derivado_por_detalle", "intervencion_derivacion", "intervencion_otro", mode="before",
    )(_vacio_a_none)


class CasoIn(CaratulaCampos):
    persona_id: uuid.UUID
    area_id: int | None = None
    responsable_id: uuid.UUID | None = None
    # Equipo a cargo: todos los anotados son responsables por igual.
    responsables_ids: list[uuid.UUID] = Field(default_factory=list, max_length=20)
    ingreso_id: uuid.UUID | None = None
    # Excepción a «una actuación por persona por año» (solo Administración, con motivo).
    forzar_otra_actuacion: bool = False
    motivo_forzado: str | None = Field(default=None, max_length=1000)


class CasoPatch(Entrada):
    area_id: int | None = None
    motivo: str | None = Field(default=None, max_length=5000)


class ReiteracionIn(Entrada):
    fecha: date | None = None
    motivo: str | None = Field(default=None, max_length=5000)
    tipo_ingreso: str | None = None
    tipo_ingreso_detalle: str | None = None
    derivado_por: str | None = None
    derivado_por_detalle: str | None = Field(default=None, max_length=300)
    reabrir: bool = True

    _limpiar = field_validator(
        "motivo", "tipo_ingreso", "tipo_ingreso_detalle", "derivado_por", "derivado_por_detalle", mode="before"
    )(_vacio_a_none)


class EvolucionIn(Entrada):
    texto: str = Field(min_length=2, max_length=10000)
    fecha: date | None = None
    autor_id: uuid.UUID | None = None
    autor_nombre: str | None = Field(default=None, max_length=200)

    _limpiar = field_validator("autor_nombre", mode="before")(_vacio_a_none)


class DemandaIn(Entrada):
    solicitante_nombre: str | None = Field(default=None, max_length=300)
    solicitante_vinculo: str | None = Field(default=None, max_length=200)
    solicitante_telefono: str | None = Field(default=None, max_length=100)
    solicitud_expresa: str | None = Field(default=None, max_length=10000)
    indicadores: list[str] | None = None
    intervenciones: list[str] | None = None
    intervencion_otro: str | None = Field(default=None, max_length=300)
    cobertura_previsional: list[str] | None = None
    trabajo_informal: bool | None = None
    cobertura_salud: list[str] | None = None
    obra_social: str | None = Field(default=None, max_length=200)
    cud: str | None = None
    discapacidades: list[str] | None = None
    domicilio: str | None = Field(default=None, max_length=2000)
    barrio: str | None = Field(default=None, max_length=200)
    localidad: str | None = Field(default=None, max_length=200)
    departamento: str | None = Field(default=None, max_length=100)
    tipo_vivienda: str | None = None
    vivienda_institucional: str | None = Field(default=None, max_length=300)
    estado_civil: str | None = None
    tiene_hijos: bool | None = None
    cantidad_hijos: int | None = Field(default=None, ge=0, le=50)
    vinculo_con_hijos: bool | None = None
    convive_con: str | None = Field(default=None, max_length=300)
    referente_nombre: str | None = Field(default=None, max_length=300)
    referente_vinculo: str | None = Field(default=None, max_length=200)
    referente_telefono: str | None = Field(default=None, max_length=100)
    diagnosticos: str | None = Field(default=None, max_length=10000)
    tiene_autonomia: bool | None = None
    estado_funcional: str | None = None
    tipo_ingreso: str | None = None
    tipo_ingreso_detalle: str | None = None
    derivado_por: str | None = None
    derivado_por_detalle: str | None = Field(default=None, max_length=300)
    agente_id: uuid.UUID | None = None
    observaciones: str | None = Field(default=None, max_length=10000)
    lugar: str | None = Field(default=None, max_length=200)
    fecha: date | None = None
    receptor_id: uuid.UUID | None = None
    receptor_nombre: str | None = Field(default=None, max_length=200)
    cargado_desde_papel: bool | None = None
    # Persona mayor: género y teléfono (los demás datos de identidad se editan en el legajo)
    genero: str | None = None
    telefono: str | None = Field(default=None, max_length=100)
    actualizar_legajo: bool = True

    _limpiar = field_validator(
        "solicitante_nombre", "solicitante_vinculo", "solicitante_telefono", "solicitud_expresa",
        "intervencion_otro", "obra_social", "cud", "domicilio", "barrio", "localidad", "departamento",
        "tipo_vivienda", "vivienda_institucional", "estado_civil", "convive_con", "referente_nombre",
        "referente_vinculo", "referente_telefono", "diagnosticos", "estado_funcional", "tipo_ingreso",
        "tipo_ingreso_detalle", "derivado_por", "derivado_por_detalle", "observaciones", "lugar",
        "genero", "telefono", "receptor_nombre", mode="before",
    )(_vacio_a_none)


class CambioEstadoIn(Entrada):
    estado: Literal["abierto", "en_seguimiento", "pausado", "cerrado"]
    motivo: str | None = Field(default=None, max_length=2000)


class AsignacionIn(Entrada):
    usuario_id: uuid.UUID
    motivo: str | None = Field(default=None, max_length=2000)
    reemplazar_actuales: bool = False


class EquipoIn(Entrada):
    """Equipo a cargo completo: se suman los nuevos y se finalizan los que no están."""

    usuarios_ids: list[uuid.UUID] = Field(default_factory=list, max_length=20)
    motivo: str | None = Field(default=None, max_length=2000)


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
    fecha_emision: date | None = None
    vence: date | None = None
    numero: str | None = Field(default=None, max_length=100)
    datos: dict[str, str] | None = None


class CampoDocumentoIn(Entrada):
    clave: str | None = Field(default=None, max_length=40)  # los datos que ya existen conservan su clave
    etiqueta: str = Field(min_length=1, max_length=80)
    tipo: Literal["texto", "fecha", "numero"] = "texto"


class TipoDocumentalIn(Entrada):
    nombre: str = Field(min_length=2, max_length=200)
    descripcion: str | None = Field(default=None, max_length=1000)
    tiene_vencimiento: bool = False
    vigencia_dias: int | None = Field(default=None, ge=1, le=36500)
    usa_numero: bool = False
    campos: list[CampoDocumentoIn] = Field(default_factory=list, max_length=12)


class TipoDocumentalPatch(Entrada):
    nombre: str | None = Field(default=None, min_length=2, max_length=200)
    descripcion: str | None = Field(default=None, max_length=1000)
    tiene_vencimiento: bool | None = None
    vigencia_dias: int | None = Field(default=None, ge=1, le=36500)
    usa_numero: bool | None = None
    campos: list[CampoDocumentoIn] | None = Field(default=None, max_length=12)


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
    inicio: Literal["direccion", "jefatura", "tecnico", "carga", "mesa", "administrativo_area", "personal"] | None = None
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
    # Al dar de baja a quien tiene casos a cargo: a quién pasarlos, o dejarlos para asignar.
    reasignar_a: uuid.UUID | None = None
    dejar_sin_asignar: bool = False
    # Reparto caso por caso: {caso_id: usuario_id o null (queda para asignar)}. Tiene que incluir todos los casos abiertos.
    reparto: dict[uuid.UUID, uuid.UUID | None] | None = None


class ResetPasswordIn(Entrada):
    password_temporal: str = Field(max_length=200)


class NumeracionIn(Entrada):
    anio: int = Field(ge=1990, le=2100)
    proximo: int = Field(ge=1, le=9999999)


class CatalogoIn(Entrada):
    nombre: str = Field(min_length=2, max_length=200)
    activo: bool = True


class CaratulasImpresasIn(Entrada):
    caso_ids: list[uuid.UUID] = Field(min_length=1, max_length=200)

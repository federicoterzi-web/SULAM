"""Modelo de datos de SULAM 0.1.

Principios que este modelo implementa:
- Cada persona mayor tiene un único legajo con identificador interno (UUID)
  independiente del documento; el número de legajo es visible y legible.
- Persona, caso y expediente son entidades distintas.
- Nada se borra físicamente: los registros se cierran, se unifican o se marcan
  como eliminados, y la auditoría es de solo agregado (garantizado por trigger).
- Los campos administrativos todavía no relevados (carátula, registro de
  demanda) NO se inventan: quedan como pendientes en DECISIONS.md.
"""

from __future__ import annotations

import uuid
from datetime import date, datetime

from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    Date,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .db import Base

UUIDpk = UUID(as_uuid=True)


def _uuid_pk() -> Mapped[uuid.UUID]:
    return mapped_column(UUIDpk, primary_key=True, default=uuid.uuid4)


def _ts() -> Mapped[datetime]:
    return mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)


# ---------------------------------------------------------------------------
# Catálogos administrables
# ---------------------------------------------------------------------------


class Area(Base):
    __tablename__ = "areas"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    nombre: Mapped[str] = mapped_column(String(200), unique=True)
    activo: Mapped[bool] = mapped_column(Boolean, default=True, server_default=text("true"))


class TipoDocumental(Base):
    __tablename__ = "tipos_documentales"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    nombre: Mapped[str] = mapped_column(String(200), unique=True)
    activo: Mapped[bool] = mapped_column(Boolean, default=True, server_default=text("true"))
    orden: Mapped[int] = mapped_column(Integer, default=0, server_default=text("0"))
    # Plantilla: qué datos se piden al cargar un documento de este tipo.
    descripcion: Mapped[str | None] = mapped_column(Text)
    tiene_vencimiento: Mapped[bool] = mapped_column(Boolean, default=False, server_default=text("false"))
    vigencia_dias: Mapped[int | None] = mapped_column(Integer)  # sugiere la fecha de vencimiento desde la emisión
    usa_numero: Mapped[bool] = mapped_column(Boolean, default=False, server_default=text("false"))
    # [{"clave": "emisor", "etiqueta": "Emisor", "tipo": "texto"|"fecha"|"numero"}]
    campos: Mapped[list] = mapped_column(JSONB, default=list, server_default=text("'[]'::jsonb"))
    creado_por: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("usuarios.id"))


class TipoVinculo(Base):
    __tablename__ = "tipos_vinculo"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    nombre: Mapped[str] = mapped_column(String(200), unique=True)
    activo: Mapped[bool] = mapped_column(Boolean, default=True, server_default=text("true"))


class Contador(Base):
    """Numeradores correlativos (legajos, casos, ingresos), con bloqueo de fila."""

    __tablename__ = "contadores"
    clave: Mapped[str] = mapped_column(String(50), primary_key=True)
    valor: Mapped[int] = mapped_column(Integer, default=0)


# ---------------------------------------------------------------------------
# Usuarios, roles, permisos y sesiones
# ---------------------------------------------------------------------------


class Usuario(Base):
    __tablename__ = "usuarios"
    id: Mapped[uuid.UUID] = _uuid_pk()
    usuario: Mapped[str] = mapped_column(String(80), unique=True)
    nombre_completo: Mapped[str] = mapped_column(String(200))
    email: Mapped[str | None] = mapped_column(String(200))
    area_id: Mapped[int | None] = mapped_column(ForeignKey("areas.id"))
    password_hash: Mapped[str] = mapped_column(String(300))
    activo: Mapped[bool] = mapped_column(Boolean, default=True, server_default=text("true"))
    debe_cambiar_password: Mapped[bool] = mapped_column(
        Boolean, default=True, server_default=text("true")
    )
    intentos_fallidos: Mapped[int] = mapped_column(Integer, default=0, server_default=text("0"))
    bloqueado_hasta: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    ultimo_acceso: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    creado_en: Mapped[datetime] = _ts()

    area: Mapped[Area | None] = relationship()
    roles: Mapped[list["Rol"]] = relationship(secondary="usuarios_roles", lazy="selectin")


class Rol(Base):
    __tablename__ = "roles"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    nombre: Mapped[str] = mapped_column(String(120), unique=True)
    descripcion: Mapped[str | None] = mapped_column(Text)
    activo: Mapped[bool] = mapped_column(Boolean, default=True, server_default=text("true"))
    # Página de inicio de quienes tienen este rol (ver sulam/inicio.py).
    inicio: Mapped[str | None] = mapped_column(String(30))

    permisos: Mapped[list["RolPermiso"]] = relationship(
        back_populates="rol", cascade="all, delete-orphan", lazy="selectin"
    )


class RolPermiso(Base):
    __tablename__ = "roles_permisos"
    __table_args__ = (UniqueConstraint("rol_id", "modulo", "accion"),)
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    rol_id: Mapped[int] = mapped_column(ForeignKey("roles.id", ondelete="CASCADE"))
    modulo: Mapped[str] = mapped_column(String(50))
    accion: Mapped[str] = mapped_column(String(50))
    alcance: Mapped[str] = mapped_column(String(20))

    rol: Mapped[Rol] = relationship(back_populates="permisos")


class UsuarioRol(Base):
    __tablename__ = "usuarios_roles"
    usuario_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("usuarios.id", ondelete="CASCADE"), primary_key=True
    )
    rol_id: Mapped[int] = mapped_column(ForeignKey("roles.id", ondelete="CASCADE"), primary_key=True)


class Sesion(Base):
    __tablename__ = "sesiones"
    id: Mapped[uuid.UUID] = _uuid_pk()
    usuario_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("usuarios.id"), index=True)
    token_hash: Mapped[str] = mapped_column(String(64), unique=True)
    csrf_token: Mapped[str] = mapped_column(String(64))
    creada_en: Mapped[datetime] = _ts()
    expira_en: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    ultimo_uso: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    revocada_en: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    ip: Mapped[str | None] = mapped_column(String(64))
    user_agent: Mapped[str | None] = mapped_column(String(300))
    movil: Mapped[bool] = mapped_column(Boolean, default=False, server_default=text("false"))

    usuario: Mapped[Usuario] = relationship()


# ---------------------------------------------------------------------------
# Legajo único: persona y personas vinculadas
# ---------------------------------------------------------------------------


class Persona(Base):
    __tablename__ = "personas"
    __table_args__ = (
        # Un mismo documento no puede pertenecer a dos legajos activos.
        Index(
            "uq_personas_documento_activo",
            "tipo_documento",
            "numero_documento",
            unique=True,
            postgresql_where=text("numero_documento IS NOT NULL AND unificada_en_id IS NULL"),
        ),
        Index("ix_personas_apellidos_norm", "apellidos_norm"),
        Index(
            "uq_personas_legajo_activo",
            "numero_legajo",
            unique=True,
            postgresql_where=text("unificada_en_id IS NULL"),
        ),
        CheckConstraint(
            "(numero_documento IS NULL) OR (sin_documento = false)",
            name="ck_personas_documento_coherente",
        ),
    )

    id: Mapped[uuid.UUID] = _uuid_pk()
    # Número de legajo visible = DNI (o "LC 1234567", etc.); "SD-000001" si no tiene documento.
    numero_legajo: Mapped[str] = mapped_column(String(40))
    # Número provisorio asignado cuando ingresó sin DNI; se conserva para seguir
    # encontrando la carpeta y los papeles rotulados con él.
    legajo_provisorio: Mapped[str | None] = mapped_column(String(20), index=True)
    tipo_documento: Mapped[str | None] = mapped_column(String(20))
    numero_documento: Mapped[str | None] = mapped_column(String(30))
    sin_documento: Mapped[bool] = mapped_column(Boolean, default=False, server_default=text("false"))
    motivo_sin_documento: Mapped[str | None] = mapped_column(Text)
    apellidos: Mapped[str] = mapped_column(String(200))
    nombres: Mapped[str] = mapped_column(String(200))
    apellidos_norm: Mapped[str] = mapped_column(String(200))
    nombres_norm: Mapped[str] = mapped_column(String(200))
    fecha_nacimiento: Mapped[date | None] = mapped_column(Date)
    fecha_nacimiento_aproximada: Mapped[bool] = mapped_column(
        Boolean, default=False, server_default=text("false")
    )
    domicilio: Mapped[str | None] = mapped_column(Text)
    localidad: Mapped[str | None] = mapped_column(String(200))
    telefono: Mapped[str | None] = mapped_column(String(100))
    # Ubicación del domicilio, marcada a mano o con el GPS en una visita (nunca con servicios externos).
    cuil: Mapped[str | None] = mapped_column(String(13))
    lat: Mapped[float | None] = mapped_column(Float)
    lng: Mapped[float | None] = mapped_column(Float)
    ubicacion_actualizada_en: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    observaciones: Mapped[str | None] = mapped_column(Text)

    # Datos de la carátula y del registro de demanda (ver formularios.py).
    genero: Mapped[str | None] = mapped_column(String(10))
    barrio: Mapped[str | None] = mapped_column(String(200))
    departamento: Mapped[str | None] = mapped_column(String(100))
    cud: Mapped[str | None] = mapped_column(String(20))
    cobertura_salud: Mapped[list | None] = mapped_column(JSONB)
    obra_social: Mapped[str | None] = mapped_column(String(200))
    cobertura_previsional: Mapped[list | None] = mapped_column(JSONB)
    trabajo_informal: Mapped[bool | None] = mapped_column(Boolean)
    discapacidades: Mapped[list | None] = mapped_column(JSONB)

    unificada_en_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("personas.id"))
    unificada_fecha: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    creado_por: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("usuarios.id"))
    creado_en: Mapped[datetime] = _ts()
    actualizado_en: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class PersonaVinculada(Base):
    """Familiares, referentes, denunciantes, convivientes o instituciones
    relacionadas con la persona mayor."""

    __tablename__ = "personas_vinculadas"
    id: Mapped[uuid.UUID] = _uuid_pk()
    persona_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("personas.id"), index=True)
    tipo_vinculo_id: Mapped[int] = mapped_column(ForeignKey("tipos_vinculo.id"))
    es_institucion: Mapped[bool] = mapped_column(Boolean, default=False, server_default=text("false"))
    apellidos: Mapped[str | None] = mapped_column(String(200))
    nombres: Mapped[str | None] = mapped_column(String(200))
    nombre_institucion: Mapped[str | None] = mapped_column(String(300))
    numero_documento: Mapped[str | None] = mapped_column(String(30))
    telefono: Mapped[str | None] = mapped_column(String(100))
    domicilio: Mapped[str | None] = mapped_column(Text)
    observaciones: Mapped[str | None] = mapped_column(Text)
    activo: Mapped[bool] = mapped_column(Boolean, default=True, server_default=text("true"))
    creado_por: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("usuarios.id"))
    creado_en: Mapped[datetime] = _ts()

    tipo_vinculo: Mapped[TipoVinculo] = relationship(lazy="joined")


# ---------------------------------------------------------------------------
# Casos, expedientes e ingresos de Mesa de Entrada
# ---------------------------------------------------------------------------

ESTADOS_CASO = ("abierto", "en_seguimiento", "pausado", "cerrado")


class Caso(Base):
    __tablename__ = "casos"
    __table_args__ = (
        CheckConstraint(
            "estado IN ('abierto','en_seguimiento','pausado','cerrado')", name="ck_casos_estado"
        ),
        Index(
            "uq_casos_actuacion",
            "anio_actuacion",
            "numero_actuacion",
            unique=True,
            postgresql_where=text("numero_actuacion IS NOT NULL"),
        ),
    )
    id: Mapped[uuid.UUID] = _uuid_pk()
    numero: Mapped[str] = mapped_column(String(30), unique=True)
    persona_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("personas.id"), index=True)
    area_id: Mapped[int | None] = mapped_column(ForeignKey("areas.id"))
    estado: Mapped[str] = mapped_column(String(20), default="abierto")
    motivo: Mapped[str | None] = mapped_column(Text)  # "Motivo de ingreso" de la carátula

    # Carátula (modelo institucional)
    # Actuación N° / año: número correlativo de carátula por año (= número del caso).
    numero_actuacion: Mapped[int | None] = mapped_column(Integer)
    anio_actuacion: Mapped[int | None] = mapped_column(Integer)
    fecha_ingreso: Mapped[date | None] = mapped_column(Date)
    antecedentes: Mapped[bool | None] = mapped_column(Boolean)
    fecha_ultimo_ingreso: Mapped[date | None] = mapped_column(Date)
    tipo_ingreso: Mapped[str | None] = mapped_column(String(30))
    tipo_ingreso_detalle: Mapped[str | None] = mapped_column(String(30))
    derivado_por: Mapped[str | None] = mapped_column(String(30))
    derivado_por_detalle: Mapped[str | None] = mapped_column(String(300))
    indicadores: Mapped[list | None] = mapped_column(JSONB)
    intervenciones: Mapped[list | None] = mapped_column(JSONB)
    intervencion_derivacion: Mapped[str | None] = mapped_column(String(300))
    intervencion_otro: Mapped[str | None] = mapped_column(String(300))

    abierto_en: Mapped[datetime] = _ts()
    cerrado_en: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    ultima_actividad: Mapped[datetime] = _ts()
    creado_por: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("usuarios.id"))
    # Primera impresión de la carátula (cola de impresión por tandas).
    caratula_impresa_en: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    caratula_impresa_por: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("usuarios.id"))

    area: Mapped[Area | None] = relationship(lazy="joined")
    asignaciones: Mapped[list["CasoAsignacion"]] = relationship(
        back_populates="caso", order_by="CasoAsignacion.desde", lazy="selectin"
    )
    historial_estados: Mapped[list["CasoEstadoHistorial"]] = relationship(
        order_by="CasoEstadoHistorial.en", lazy="selectin"
    )


class CasoEstadoHistorial(Base):
    __tablename__ = "casos_estados_historial"
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    caso_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("casos.id"), index=True)
    estado_anterior: Mapped[str | None] = mapped_column(String(20))
    estado_nuevo: Mapped[str] = mapped_column(String(20))
    motivo: Mapped[str | None] = mapped_column(Text)
    usuario_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("usuarios.id"))
    en: Mapped[datetime] = _ts()

    usuario: Mapped[Usuario | None] = relationship(lazy="joined")


class CasoEvolucion(Base):
    """Notas de "Evolución del caso" (registro de demanda)."""

    __tablename__ = "casos_evoluciones"
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    caso_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("casos.id"), index=True)
    texto: Mapped[str] = mapped_column(Text)
    # Fecha y autor de la intervención (puede haberse escrito en papel)...
    fecha: Mapped[date | None] = mapped_column(Date)
    autor_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("usuarios.id"))
    autor_nombre: Mapped[str | None] = mapped_column(String(200))
    # ...y quién la cargó en el sistema y cuándo.
    usuario_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("usuarios.id"))
    en: Mapped[datetime] = _ts()

    usuario: Mapped[Usuario | None] = relationship(foreign_keys=[usuario_id], lazy="joined")
    autor: Mapped[Usuario | None] = relationship(foreign_keys=[autor_id], lazy="joined")


class Reiteracion(Base):
    """Nuevo ingreso de una persona que ya tiene caso (actuación) en el año."""

    __tablename__ = "casos_reiteraciones"
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    caso_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("casos.id"), index=True)
    fecha: Mapped[date] = mapped_column(Date)
    motivo: Mapped[str | None] = mapped_column(Text)
    tipo_ingreso: Mapped[str | None] = mapped_column(String(30))
    tipo_ingreso_detalle: Mapped[str | None] = mapped_column(String(30))
    derivado_por: Mapped[str | None] = mapped_column(String(30))
    derivado_por_detalle: Mapped[str | None] = mapped_column(String(300))
    ingreso_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("ingresos.id"))
    usuario_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("usuarios.id"))
    en: Mapped[datetime] = _ts()

    usuario: Mapped[Usuario | None] = relationship(lazy="joined")


class RegistroDemanda(Base):
    """Registro de demanda: se carga después de la carátula, sobre un caso existente."""

    __tablename__ = "registros_demanda"
    id: Mapped[uuid.UUID] = _uuid_pk()
    caso_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("casos.id"), index=True)
    persona_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("personas.id"), index=True)

    # 1. Datos del solicitante
    solicitante_nombre: Mapped[str | None] = mapped_column(String(300))
    solicitante_vinculo: Mapped[str | None] = mapped_column(String(200))
    solicitante_telefono: Mapped[str | None] = mapped_column(String(100))
    # 2. Datos de la persona mayor: se toman del legajo (y se guarda una copia, ver datos_persona)
    datos_persona: Mapped[dict | None] = mapped_column(JSONB)
    # 3. Motivo de consulta
    solicitud_expresa: Mapped[str | None] = mapped_column(Text)
    indicadores: Mapped[list | None] = mapped_column(JSONB)
    intervenciones: Mapped[list | None] = mapped_column(JSONB)
    intervencion_otro: Mapped[str | None] = mapped_column(String(300))
    # 4. Cobertura social y previsional
    cobertura_previsional: Mapped[list | None] = mapped_column(JSONB)
    trabajo_informal: Mapped[bool | None] = mapped_column(Boolean)
    cobertura_salud: Mapped[list | None] = mapped_column(JSONB)
    obra_social: Mapped[str | None] = mapped_column(String(200))
    cud: Mapped[str | None] = mapped_column(String(20))
    discapacidades: Mapped[list | None] = mapped_column(JSONB)
    # 5. Situación habitacional
    domicilio: Mapped[str | None] = mapped_column(Text)
    barrio: Mapped[str | None] = mapped_column(String(200))
    localidad: Mapped[str | None] = mapped_column(String(200))
    departamento: Mapped[str | None] = mapped_column(String(100))
    tipo_vivienda: Mapped[str | None] = mapped_column(String(30))
    vivienda_institucional: Mapped[str | None] = mapped_column(String(300))
    # 6. Situación familiar
    estado_civil: Mapped[str | None] = mapped_column(String(30))
    tiene_hijos: Mapped[bool | None] = mapped_column(Boolean)
    cantidad_hijos: Mapped[int | None] = mapped_column(Integer)
    vinculo_con_hijos: Mapped[bool | None] = mapped_column(Boolean)
    convive_con: Mapped[str | None] = mapped_column(String(300))
    referente_nombre: Mapped[str | None] = mapped_column(String(300))
    referente_vinculo: Mapped[str | None] = mapped_column(String(200))
    referente_telefono: Mapped[str | None] = mapped_column(String(100))
    # 7. Situación de salud
    diagnosticos: Mapped[str | None] = mapped_column(Text)
    tiene_autonomia: Mapped[bool | None] = mapped_column(Boolean)
    estado_funcional: Mapped[str | None] = mapped_column(String(30))
    # 8. Ingreso al sistema
    tipo_ingreso: Mapped[str | None] = mapped_column(String(30))
    tipo_ingreso_detalle: Mapped[str | None] = mapped_column(String(30))
    derivado_por: Mapped[str | None] = mapped_column(String(30))
    derivado_por_detalle: Mapped[str | None] = mapped_column(String(300))
    agente_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("usuarios.id"))
    # Cierre
    observaciones: Mapped[str | None] = mapped_column(Text)
    lugar: Mapped[str | None] = mapped_column(String(200))
    fecha: Mapped[date] = mapped_column(Date)  # fecha del formulario
    # Quien recibió la demanda y firma el original (no necesariamente quien lo carga).
    receptor_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("usuarios.id"))
    receptor_nombre: Mapped[str | None] = mapped_column(String(200))
    cargado_desde_papel: Mapped[bool] = mapped_column(Boolean, default=True, server_default=text("true"))

    creado_por: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("usuarios.id"))  # quien lo cargó
    creado_en: Mapped[datetime] = _ts()
    actualizado_en: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    agente: Mapped[Usuario | None] = relationship(foreign_keys=[agente_id], lazy="joined")
    receptor: Mapped[Usuario | None] = relationship(foreign_keys=[receptor_id], lazy="joined")
    cargador: Mapped[Usuario | None] = relationship(foreign_keys=[creado_por], lazy="joined")


class CasoAsignacion(Base):
    __tablename__ = "casos_asignaciones"
    __table_args__ = (
        Index(
            "uq_asignacion_activa",
            "caso_id",
            "usuario_id",
            unique=True,
            postgresql_where=text("hasta IS NULL"),
        ),
    )
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    caso_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("casos.id"), index=True)
    usuario_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("usuarios.id"), index=True)
    asignado_por: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("usuarios.id"))
    motivo: Mapped[str | None] = mapped_column(Text)
    desde: Mapped[datetime] = _ts()
    hasta: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    finalizado_por: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("usuarios.id"))

    caso: Mapped[Caso] = relationship(back_populates="asignaciones")
    usuario: Mapped[Usuario] = relationship(foreign_keys=[usuario_id], lazy="joined")


class Expediente(Base):
    __tablename__ = "expedientes"
    __table_args__ = (
        CheckConstraint("tipo IN ('administrativo','judicial')", name="ck_expedientes_tipo"),
    )
    id: Mapped[uuid.UUID] = _uuid_pk()
    numero: Mapped[str] = mapped_column(String(100), index=True)
    tipo: Mapped[str] = mapped_column(String(20))
    organismo: Mapped[str | None] = mapped_column(String(300))
    caratula: Mapped[str | None] = mapped_column(Text)
    persona_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("personas.id"), index=True)
    caso_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("casos.id"), index=True)
    observaciones: Mapped[str | None] = mapped_column(Text)
    creado_por: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("usuarios.id"))
    creado_en: Mapped[datetime] = _ts()


class Ingreso(Base):
    """Registro de Mesa de Entrada. Puede existir antes que el legajo."""

    __tablename__ = "ingresos"
    id: Mapped[uuid.UUID] = _uuid_pk()
    numero: Mapped[str] = mapped_column(String(30), unique=True)
    fecha_ingreso: Mapped[datetime] = _ts()
    remitente: Mapped[str | None] = mapped_column(String(300))
    tipo_documental_id: Mapped[int | None] = mapped_column(ForeignKey("tipos_documentales.id"))
    asunto: Mapped[str] = mapped_column(Text)
    folios: Mapped[int | None] = mapped_column(Integer)
    persona_mencionada: Mapped[str | None] = mapped_column(String(300))
    documento_mencionado: Mapped[str | None] = mapped_column(String(30))
    numero_expediente_externo: Mapped[str | None] = mapped_column(String(100))
    observaciones: Mapped[str | None] = mapped_column(Text)
    persona_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("personas.id"), index=True)
    caso_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("casos.id"))
    expediente_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("expedientes.id"))
    vinculado_por: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("usuarios.id"))
    vinculado_en: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    creado_por: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("usuarios.id"))
    creado_en: Mapped[datetime] = _ts()

    tipo_documental: Mapped[TipoDocumental | None] = relationship(lazy="joined")


# ---------------------------------------------------------------------------
# Documentos
# ---------------------------------------------------------------------------


class Documento(Base):
    __tablename__ = "documentos"
    __table_args__ = (
        CheckConstraint(
            "persona_id IS NOT NULL OR ingreso_id IS NOT NULL", name="ck_documentos_pertenencia"
        ),
        Index("ix_documentos_sha256", "sha256"),
    )
    id: Mapped[uuid.UUID] = _uuid_pk()
    persona_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("personas.id"), index=True)
    caso_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("casos.id"), index=True)
    expediente_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("expedientes.id"))
    ingreso_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("ingresos.id"))
    # Escaneo del original en papel de un registro de demanda.
    registro_demanda_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("registros_demanda.id"))
    tipo_documental_id: Mapped[int] = mapped_column(ForeignKey("tipos_documentales.id"))
    titulo: Mapped[str] = mapped_column(String(300))
    descripcion: Mapped[str | None] = mapped_column(Text)
    nombre_original: Mapped[str] = mapped_column(String(300))
    mime: Mapped[str] = mapped_column(String(100))
    tamano: Mapped[int] = mapped_column(BigInteger)
    sha256: Mapped[str] = mapped_column(String(64))
    almacenamiento: Mapped[str] = mapped_column(String(30))
    clave_almacenamiento: Mapped[str] = mapped_column(String(300))
    cargado_por: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("usuarios.id"))
    cargado_en: Mapped[datetime] = _ts()
    eliminado_en: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    eliminado_por: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("usuarios.id"))
    motivo_eliminacion: Mapped[str | None] = mapped_column(Text)
    # Datos según la plantilla del tipo (solo se muestran dentro del legajo).
    fecha_emision: Mapped[date | None] = mapped_column(Date)
    vence: Mapped[date | None] = mapped_column(Date)
    numero: Mapped[str | None] = mapped_column(String(100))
    datos: Mapped[dict] = mapped_column(JSONB, default=dict, server_default=text("'{}'::jsonb"))
    # Texto leído del archivo (hojas separadas por salto de página) y su versión normalizada para buscar.
    texto: Mapped[str | None] = mapped_column(Text)
    texto_busqueda: Mapped[str | None] = mapped_column(Text)
    texto_estado: Mapped[str] = mapped_column(String(12), default="pendiente", server_default="pendiente")
    texto_leido_en: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    tipo_documental: Mapped[TipoDocumental] = relationship(lazy="joined")


class PaginaCaptura(Base):
    """Foto sacada con el celular que todavía no se asignó a un documento (bandeja de cada persona)."""

    __tablename__ = "capturas_paginas"
    __table_args__ = (CheckConstraint("estado IN ('pendiente','clasificada','descartada')", name="ck_captura_pagina_estado"),)
    id: Mapped[uuid.UUID] = _uuid_pk()
    usuario_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("usuarios.id"), index=True)
    mime: Mapped[str] = mapped_column(String(50))
    tamano: Mapped[int] = mapped_column(BigInteger)
    sha256: Mapped[str] = mapped_column(String(64))
    almacenamiento: Mapped[str] = mapped_column(String(30))
    clave_almacenamiento: Mapped[str] = mapped_column(String(300))
    estado: Mapped[str] = mapped_column(String(20), default="pendiente", server_default="pendiente")
    documento_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("documentos.id"))
    creada_en: Mapped[datetime] = _ts()


class EventoAgenda(Base):
    """Actividad agendada: salida, visita, reunión, audiencia, entrevista, trámite o recordatorio."""

    __tablename__ = "agenda_eventos"
    __table_args__ = (
        CheckConstraint("estado IN ('programado','realizado','no_realizado','cancelado')", name="ck_agenda_estado"),
        Index("ix_agenda_eventos_inicio", "inicio"),
    )
    id: Mapped[uuid.UUID] = _uuid_pk()
    tipo: Mapped[str] = mapped_column(String(20))
    titulo: Mapped[str] = mapped_column(String(200))
    descripcion: Mapped[str | None] = mapped_column(Text)
    inicio: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    fin: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    todo_el_dia: Mapped[bool] = mapped_column(Boolean, default=False, server_default=text("false"))
    lugar: Mapped[str | None] = mapped_column(String(300))
    area_id: Mapped[int | None] = mapped_column(ForeignKey("areas.id"))
    persona_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("personas.id"), index=True)
    caso_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("casos.id"), index=True)
    estado: Mapped[str] = mapped_column(String(15), default="programado", server_default="programado")
    resultado: Mapped[str | None] = mapped_column(Text)
    resuelto_por: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("usuarios.id"))
    resuelto_en: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    creado_por: Mapped[uuid.UUID] = mapped_column(ForeignKey("usuarios.id"))
    creado_en: Mapped[datetime] = _ts()
    # Actividades repetidas: todas las de una serie comparten ``serie_id``; cada una tiene su propio resultado.
    serie_id: Mapped[uuid.UUID | None] = mapped_column(index=True)
    repeticion: Mapped[str | None] = mapped_column(String(12))

    area: Mapped[Area | None] = relationship(lazy="joined")
    participantes: Mapped[list["ParticipanteAgenda"]] = relationship(cascade="all, delete-orphan", lazy="selectin")


class ParticipanteAgenda(Base):
    __tablename__ = "agenda_participantes"
    evento_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("agenda_eventos.id", ondelete="CASCADE"), primary_key=True)
    usuario_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("usuarios.id"), primary_key=True)

    usuario: Mapped[Usuario] = relationship(lazy="joined")


class CambioAgenda(Base):
    """Historial de cambios de una actividad (reprogramaciones, lugar, participantes…)."""

    __tablename__ = "agenda_cambios"
    id: Mapped[uuid.UUID] = _uuid_pk()
    evento_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("agenda_eventos.id", ondelete="CASCADE"), index=True)
    usuario_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("usuarios.id"))
    en: Mapped[datetime] = _ts()
    cambios: Mapped[dict] = mapped_column(JSONB)  # {campo: [antes, después]}
    motivo: Mapped[str | None] = mapped_column(Text)

    usuario: Mapped[Usuario] = relationship(lazy="joined")


class Ajuste(Base):
    """Ajuste del sistema que cambia el administrador (clave → valor JSON)."""

    __tablename__ = "ajustes"
    clave: Mapped[str] = mapped_column(String(60), primary_key=True)
    valor: Mapped[dict | list | bool | str | int | None] = mapped_column(JSONB)


class CasoCalibracion(Base):
    """Una comparación entre lo que sugirió la lectura automática y lo que se confirmó. Sin datos personales."""

    __tablename__ = "calibracion_casos"
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    creado_en: Mapped[datetime] = _ts()
    campo: Mapped[str] = mapped_column(String(30))
    resultado: Mapped[str] = mapped_column(String(20))  # acierto / corregido / faltante / sobrante
    tipo_documental: Mapped[str | None] = mapped_column(String(200))
    detalle: Mapped[dict] = mapped_column(JSONB, default=dict, server_default=text("'{}'::jsonb"))
    fragmento: Mapped[str | None] = mapped_column(Text)


# ---------------------------------------------------------------------------
# Auditoría (solo agregado)
# ---------------------------------------------------------------------------


class Auditoria(Base):
    __tablename__ = "auditoria"
    __table_args__ = (
        Index("ix_auditoria_entidad", "entidad", "entidad_id"),
        Index("ix_auditoria_persona", "persona_id"),
        Index("ix_auditoria_usuario_en", "usuario_id", "en"),
    )
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    en: Mapped[datetime] = _ts()
    usuario_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("usuarios.id"))
    accion: Mapped[str] = mapped_column(String(80))
    entidad: Mapped[str] = mapped_column(String(50))
    entidad_id: Mapped[str | None] = mapped_column(String(64))
    persona_id: Mapped[uuid.UUID | None] = mapped_column(UUIDpk)
    detalle: Mapped[dict | None] = mapped_column(JSONB)
    ip: Mapped[str | None] = mapped_column(String(64))

    usuario: Mapped[Usuario | None] = relationship(lazy="joined")


# ---------------------------------------------------------------------------
# Red de recursos: instituciones, centros y cuidadores, con ubicación.
# ---------------------------------------------------------------------------


class Recurso(Base):
    __tablename__ = "recursos"
    id: Mapped[uuid.UUID] = _uuid_pk()
    tipo: Mapped[str] = mapped_column(String(30), index=True)
    categoria: Mapped[str | None] = mapped_column(String(40))
    nombre: Mapped[str] = mapped_column(String(300))
    nombre_norm: Mapped[str] = mapped_column(String(300), index=True)
    direccion: Mapped[str | None] = mapped_column(String(500))
    localidad: Mapped[str | None] = mapped_column(String(200))
    departamento: Mapped[str | None] = mapped_column(String(100), index=True)
    lat: Mapped[float | None] = mapped_column(Float)
    lng: Mapped[float | None] = mapped_column(Float)
    telefono: Mapped[str | None] = mapped_column(String(100))
    telefono_alternativo: Mapped[str | None] = mapped_column(String(100))
    email: Mapped[str | None] = mapped_column(String(200))
    horario: Mapped[str | None] = mapped_column(String(300))
    referente: Mapped[str | None] = mapped_column(String(200))
    referente_cargo: Mapped[str | None] = mapped_column(String(200))
    servicios: Mapped[str | None] = mapped_column(Text)
    observaciones: Mapped[str | None] = mapped_column(Text)
    # Cuidadores formados
    zonas: Mapped[list | None] = mapped_column(JSONB)
    formacion: Mapped[str | None] = mapped_column(Text)
    disponibilidad: Mapped[str | None] = mapped_column(String(300))
    # De dónde salió el dato (ver routers/recursos.ORIGENES).
    origen: Mapped[str | None] = mapped_column(String(30))
    origen_detalle: Mapped[str | None] = mapped_column(String(300))

    activo: Mapped[bool] = mapped_column(Boolean, default=True, server_default=text("true"))
    creado_por: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("usuarios.id"))
    creado_en: Mapped[datetime] = _ts()
    actualizado_por: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("usuarios.id"))
    actualizado_en: Mapped[datetime] = _ts()


class Contacto(Base):
    """Personas de contacto: técnicos de gobiernos locales y de otras instituciones."""

    __tablename__ = "contactos"
    id: Mapped[uuid.UUID] = _uuid_pk()
    nombre: Mapped[str] = mapped_column(String(200))
    nombre_norm: Mapped[str] = mapped_column(String(200), index=True)
    cargo: Mapped[str | None] = mapped_column(String(200))
    institucion: Mapped[str | None] = mapped_column(String(300))
    institucion_norm: Mapped[str | None] = mapped_column(String(300), index=True)
    categoria: Mapped[str | None] = mapped_column(String(40))
    recurso_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("recursos.id"), index=True)
    localidad: Mapped[str | None] = mapped_column(String(200))
    departamento: Mapped[str | None] = mapped_column(String(100), index=True)
    telefono: Mapped[str | None] = mapped_column(String(100))
    telefono_alternativo: Mapped[str | None] = mapped_column(String(100))
    whatsapp: Mapped[str | None] = mapped_column(String(30))
    email: Mapped[str | None] = mapped_column(String(200))
    temas: Mapped[str | None] = mapped_column(Text)
    observaciones: Mapped[str | None] = mapped_column(Text)
    origen: Mapped[str | None] = mapped_column(String(30))
    origen_detalle: Mapped[str | None] = mapped_column(String(300))
    activo: Mapped[bool] = mapped_column(Boolean, default=True, server_default=text("true"))
    creado_por: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("usuarios.id"))
    creado_en: Mapped[datetime] = _ts()
    actualizado_por: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("usuarios.id"))
    actualizado_en: Mapped[datetime] = _ts()

    recurso: Mapped["Recurso | None"] = relationship(lazy="joined")


class Articulacion(Base):
    """Articulación con otra institución o persona en un caso puntual."""

    __tablename__ = "casos_articulaciones"
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    caso_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("casos.id"), index=True)
    contacto_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("contactos.id"), index=True)
    recurso_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("recursos.id"), index=True)
    fecha: Mapped[date] = mapped_column(Date)
    motivo: Mapped[str | None] = mapped_column(Text)
    resultado: Mapped[str | None] = mapped_column(Text)
    usuario_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("usuarios.id"))
    en: Mapped[datetime] = _ts()

    contacto: Mapped["Contacto | None"] = relationship(lazy="joined")
    recurso: Mapped["Recurso | None"] = relationship(lazy="joined")
    usuario: Mapped[Usuario | None] = relationship(lazy="joined")


# ---------------------------------------------------------------------------
# Informes: plantillas editables y documentos redactados en SULAM.
# ---------------------------------------------------------------------------


class PlantillaInforme(Base):
    """Estructura sugerida de un informe: qué datos de la persona se incluyen y
    qué secciones lleva. Las editan Dirección y jefaturas (módulo «plantillas»)."""

    __tablename__ = "plantillas_informe"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    nombre: Mapped[str] = mapped_column(String(200))
    descripcion: Mapped[str | None] = mapped_column(Text)
    # Área que la usa; sin área = para toda la Dirección.
    area_id: Mapped[int | None] = mapped_column(ForeignKey("areas.id"))
    tipo_documental_id: Mapped[int | None] = mapped_column(ForeignKey("tipos_documentales.id"))
    # {"destinatario": bool, "datos": [clave...], "secciones": [{"titulo", "guia", "texto"}]}
    estructura: Mapped[dict] = mapped_column(JSONB)
    orden: Mapped[int] = mapped_column(Integer, default=0, server_default=text("0"))
    activo: Mapped[bool] = mapped_column(Boolean, default=True, server_default=text("true"))
    creado_por: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("usuarios.id"))
    creado_en: Mapped[datetime] = _ts()
    actualizado_por: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("usuarios.id"))
    actualizado_en: Mapped[datetime] = _ts()

    area: Mapped[Area | None] = relationship(lazy="joined")
    tipo_documental: Mapped[TipoDocumental | None] = relationship(lazy="joined")


class Informe(Base):
    """Informe redactado en SULAM. Mientras es borrador se edita; al firmarlo se
    genera el PDF (queda como documento del legajo) y no cambia más. Para
    corregirlo se crea una versión nueva del mismo grupo."""

    __tablename__ = "informes"
    __table_args__ = (
        UniqueConstraint("grupo_id", "version", name="uq_informes_grupo_version"),
        CheckConstraint("estado IN ('borrador', 'firmado', 'reemplazado', 'descartado')", name="ck_informes_estado"),
    )
    id: Mapped[uuid.UUID] = _uuid_pk()
    grupo_id: Mapped[uuid.UUID] = mapped_column(UUIDpk, index=True)
    version: Mapped[int] = mapped_column(Integer, default=1)
    persona_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("personas.id"), index=True)
    caso_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("casos.id"), index=True)
    plantilla_id: Mapped[int | None] = mapped_column(ForeignKey("plantillas_informe.id"))
    tipo_documental_id: Mapped[int | None] = mapped_column(ForeignKey("tipos_documentales.id"))
    titulo: Mapped[str] = mapped_column(String(300))
    lugar: Mapped[str | None] = mapped_column(String(200))
    fecha: Mapped[date] = mapped_column(Date)
    destinatario: Mapped[str | None] = mapped_column(Text)
    # [{"clave", "etiqueta", "valor"}]
    datos: Mapped[list] = mapped_column(JSONB)
    # [{"titulo", "html"}]
    secciones: Mapped[list] = mapped_column(JSONB)
    # [{"nombre", "cargo"}]
    firmantes: Mapped[list] = mapped_column(JSONB)
    estado: Mapped[str] = mapped_column(String(20), default="borrador")
    documento_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("documentos.id"))
    firmado_en: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    firmado_por: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("usuarios.id"))
    creado_por: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("usuarios.id"))
    creado_en: Mapped[datetime] = _ts()
    actualizado_por: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("usuarios.id"))
    actualizado_en: Mapped[datetime] = _ts()

    autor: Mapped[Usuario | None] = relationship(foreign_keys=[creado_por], lazy="joined")
    firmante_usuario: Mapped[Usuario | None] = relationship(foreign_keys=[firmado_por], lazy="joined")
    tipo_documental: Mapped[TipoDocumental | None] = relationship(lazy="joined")


class Constancia(Base):
    """Constancias de organismos sobre la persona (por ahora, la certificación
    negativa de ANSES), con su resultado, vencimiento y el PDF en el legajo."""

    __tablename__ = "constancias"
    __table_args__ = (
        CheckConstraint(
            "resultado IN ('sin_registros', 'con_registros', 'no_emitida')", name="ck_constancias_resultado"
        ),
    )
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    persona_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("personas.id"), index=True)
    tipo: Mapped[str] = mapped_column(String(40), default="negativa_anses")
    cuil: Mapped[str | None] = mapped_column(String(13))
    fecha_emision: Mapped[date] = mapped_column(Date)
    vence: Mapped[date | None] = mapped_column(Date)
    resultado: Mapped[str] = mapped_column(String(20))
    detalle: Mapped[str | None] = mapped_column(Text)
    codigo_validacion: Mapped[str | None] = mapped_column(String(100))
    documento_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("documentos.id"))
    # «pdf» si los datos se leyeron del PDF (y se revisaron), «manual» si se cargaron a mano.
    origen: Mapped[str] = mapped_column(String(20), default="manual")
    observaciones: Mapped[str | None] = mapped_column(Text)
    usuario_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("usuarios.id"))
    en: Mapped[datetime] = _ts()

    usuario: Mapped[Usuario | None] = relationship(lazy="joined")


# ---------------------------------------------------------------------------
# Novedades: circulares e información de la Dirección y de cada área.
# ---------------------------------------------------------------------------


class Novedad(Base):
    """Aviso o circular. Sin área = para toda la Dirección; con área = para esa área."""

    __tablename__ = "novedades"
    id: Mapped[uuid.UUID] = _uuid_pk()
    titulo: Mapped[str] = mapped_column(String(300))
    cuerpo: Mapped[str] = mapped_column(Text)  # HTML limpio (párrafos, listas, negrita…)
    area_id: Mapped[int | None] = mapped_column(ForeignKey("areas.id"), index=True)
    requiere_confirmacion: Mapped[bool] = mapped_column(Boolean, default=True, server_default=text("true"))
    fijada: Mapped[bool] = mapped_column(Boolean, default=False, server_default=text("false"))
    # Circular adjunta (PDF o imagen), en el almacenamiento de archivos.
    archivo_nombre: Mapped[str | None] = mapped_column(String(300))
    archivo_mime: Mapped[str | None] = mapped_column(String(100))
    archivo_tamano: Mapped[int | None] = mapped_column(BigInteger)
    archivo_sha256: Mapped[str | None] = mapped_column(String(64))
    archivo_almacenamiento: Mapped[str | None] = mapped_column(String(30))
    archivo_clave: Mapped[str | None] = mapped_column(String(300))
    autor_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("usuarios.id"))
    publicada_en: Mapped[datetime] = _ts()
    retirada_en: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    retirada_por: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("usuarios.id"))

    area: Mapped[Area | None] = relationship(lazy="joined")
    autor: Mapped[Usuario | None] = relationship(foreign_keys=[autor_id], lazy="joined")


class NovedadLectura(Base):
    """Confirmación de lectura (una por persona)."""

    __tablename__ = "novedades_lecturas"
    novedad_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("novedades.id", ondelete="CASCADE"), primary_key=True)
    usuario_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("usuarios.id"), primary_key=True)
    confirmada_en: Mapped[datetime] = _ts()


# ---------------------------------------------------------------------------
# Archivo físico: dónde está cada carpeta en papel y sus pases.
# ---------------------------------------------------------------------------


class UbicacionFisica(Base):
    """Dónde está hoy la carpeta en papel de un legajo o de un expediente."""

    __tablename__ = "ubicaciones_fisicas"
    __table_args__ = (
        CheckConstraint("(persona_id IS NULL) <> (expediente_id IS NULL)", name="ck_ubicacion_un_objeto"),
        UniqueConstraint("persona_id", name="uq_ubicacion_persona"),
        UniqueConstraint("expediente_id", name="uq_ubicacion_expediente"),
    )
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    persona_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("personas.id"))
    expediente_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("expedientes.id"))
    area_id: Mapped[int] = mapped_column(ForeignKey("areas.id"))
    # Persona que la tiene en su poder (si no, está en el área).
    usuario_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("usuarios.id"))
    desde: Mapped[datetime] = _ts()
    actualizado_por: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("usuarios.id"))

    area: Mapped[Area] = relationship(lazy="joined")
    usuario: Mapped[Usuario | None] = relationship(foreign_keys=[usuario_id], lazy="joined")


class Pase(Base):
    """Movimiento de una carpeta en papel.

    - «pedido»: alguien pide la carpeta; la confirma quien la tiene al entregarla.
    - «envio»: quien la tiene la pasa a otra área o persona; la confirma quien la recibe.
    """

    __tablename__ = "pases"
    __table_args__ = (
        CheckConstraint("(persona_id IS NULL) <> (expediente_id IS NULL)", name="ck_pase_un_objeto"),
        CheckConstraint("tipo IN ('pedido', 'envio')", name="ck_pase_tipo"),
        CheckConstraint("estado IN ('pendiente', 'hecho', 'rechazado', 'cancelado')", name="ck_pase_estado"),
    )
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    tipo: Mapped[str] = mapped_column(String(10))
    persona_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("personas.id"), index=True)
    expediente_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("expedientes.id"), index=True)
    desde_area_id: Mapped[int | None] = mapped_column(ForeignKey("areas.id"))
    desde_usuario_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("usuarios.id"))
    hacia_area_id: Mapped[int] = mapped_column(ForeignKey("areas.id"))
    hacia_usuario_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("usuarios.id"))
    motivo: Mapped[str | None] = mapped_column(Text)
    estado: Mapped[str] = mapped_column(String(12), default="pendiente")
    iniciado_por: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("usuarios.id"))
    iniciado_en: Mapped[datetime] = _ts()
    resuelto_por: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("usuarios.id"))
    resuelto_en: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    respuesta: Mapped[str | None] = mapped_column(Text)

    desde_area: Mapped[Area | None] = relationship(foreign_keys=[desde_area_id], lazy="joined")
    hacia_area: Mapped[Area] = relationship(foreign_keys=[hacia_area_id], lazy="joined")
    desde_usuario: Mapped[Usuario | None] = relationship(foreign_keys=[desde_usuario_id], lazy="joined")
    hacia_usuario: Mapped[Usuario | None] = relationship(foreign_keys=[hacia_usuario_id], lazy="joined")
    iniciador: Mapped[Usuario | None] = relationship(foreign_keys=[iniciado_por], lazy="joined")
    resolvio: Mapped[Usuario | None] = relationship(foreign_keys=[resuelto_por], lazy="joined")


# ---------------------------------------------------------------------------
# Personal: agentes, horarios, reloj, justificativos, revisiones y solicitudes.
# (Portado de la app «Asistencia DAM»; mismas reglas fijas.)
# ---------------------------------------------------------------------------


class Agente(Base):
    __tablename__ = "agentes"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    nombre: Mapped[str] = mapped_column(String(200))
    usuario_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("usuarios.id"), unique=True)
    area_id: Mapped[int | None] = mapped_column(ForeignKey("areas.id"))
    cargo: Mapped[str | None] = mapped_column(String(200))
    id_reloj: Mapped[str | None] = mapped_column(String(80), unique=True)
    boleta: Mapped[str | None] = mapped_column(String(80))
    # [{"desde": "AAAA-MM-DD"|None, "hasta": "AAAA-MM-DD"|None}]
    periodos: Mapped[list] = mapped_column(JSONB)
    revision: Mapped[int] = mapped_column(Integer, default=0, server_default=text("0"))
    creado_en: Mapped[datetime] = _ts()

    area: Mapped[Area | None] = relationship(lazy="joined")
    usuario: Mapped[Usuario | None] = relationship(lazy="joined")


class Horario(Base):
    __tablename__ = "agentes_horarios"
    __table_args__ = (UniqueConstraint("agente_id", "vigente_desde", name="uq_horario_vigencia"),)
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    agente_id: Mapped[int] = mapped_column(ForeignKey("agentes.id", ondelete="CASCADE"), index=True)
    vigente_desde: Mapped[date] = mapped_column(Date)
    vigente_hasta: Mapped[date | None] = mapped_column(Date)
    # {"0": ["08:00", "13:00"], ...}  (0 = lunes)
    semana: Mapped[dict] = mapped_column(JSONB)
    confirmado: Mapped[bool] = mapped_column(Boolean, default=False, server_default=text("false"))
    fuente: Mapped[str] = mapped_column(Text)


class RelojImportacion(Base):
    __tablename__ = "reloj_importaciones"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    nombre_archivo: Mapped[str] = mapped_column(String(300))
    sha256: Mapped[str] = mapped_column(String(64), unique=True)
    almacenamiento: Mapped[str] = mapped_column(String(30))
    clave: Mapped[str] = mapped_column(String(300))
    desde: Mapped[date] = mapped_column(Date)
    hasta: Mapped[date] = mapped_column(Date)
    filas: Mapped[int] = mapped_column(Integer)
    errores: Mapped[list] = mapped_column(JSONB)
    avisos: Mapped[list] = mapped_column(JSONB)
    identidades: Mapped[list] = mapped_column(JSONB)
    incorporada: Mapped[bool] = mapped_column(Boolean, default=False, server_default=text("false"))
    usuario_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("usuarios.id"))
    en: Mapped[datetime] = _ts()


class Marcacion(Base):
    __tablename__ = "marcaciones"
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    importacion_id: Mapped[int] = mapped_column(ForeignKey("reloj_importaciones.id"), index=True)
    agente_id: Mapped[int] = mapped_column(ForeignKey("agentes.id"), index=True)
    dia: Mapped[date] = mapped_column(Date, index=True)
    entrada: Mapped[str | None] = mapped_column(String(8))
    salida: Mapped[str | None] = mapped_column(String(8))
    fila: Mapped[int] = mapped_column(Integer)


class Justificativo(Base):
    __tablename__ = "justificativos"
    __table_args__ = (CheckConstraint("estado IN ('pendiente', 'aprobado', 'rechazado')", name="ck_justificativo_estado"),)
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    agente_id: Mapped[int] = mapped_column(ForeignKey("agentes.id"), index=True)
    codigo: Mapped[str] = mapped_column(String(20))
    desde: Mapped[date] = mapped_column(Date)
    hasta: Mapped[date] = mapped_column(Date)
    hora_desde: Mapped[str | None] = mapped_column(String(5))
    hora_hasta: Mapped[str | None] = mapped_column(String(5))
    excepcion_desde: Mapped[str | None] = mapped_column(String(5))
    excepcion_hasta: Mapped[str | None] = mapped_column(String(5))
    referencia: Mapped[str | None] = mapped_column(Text)
    notas: Mapped[str | None] = mapped_column(Text)
    estado: Mapped[str] = mapped_column(String(12))
    requiere_horario: Mapped[bool] = mapped_column(Boolean, default=False, server_default=text("false"))
    revision: Mapped[int] = mapped_column(Integer, default=0, server_default=text("0"))
    fundamento: Mapped[str | None] = mapped_column(Text)
    # [{"id", "nombre", "sha256", "mime", "almacenamiento", "clave"}]
    adjuntos: Mapped[list] = mapped_column(JSONB, default=list)
    solicitud_id: Mapped[int | None] = mapped_column(ForeignKey("solicitudes_personal.id"))
    usuario_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("usuarios.id"))
    en: Mapped[datetime] = _ts()

    agente: Mapped[Agente] = relationship(lazy="joined")
    usuario: Mapped[Usuario | None] = relationship(lazy="joined")


class RevisionJornada(Base):
    __tablename__ = "revisiones_jornada"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    agente_id: Mapped[int] = mapped_column(ForeignKey("agentes.id"), index=True)
    dia: Mapped[date] = mapped_column(Date)
    huella: Mapped[str] = mapped_column(String(64))
    decision: Mapped[str] = mapped_column(String(30))
    minutos: Mapped[int] = mapped_column(Integer)
    fundamento: Mapped[str] = mapped_column(Text)
    usuario_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("usuarios.id"))
    en: Mapped[datetime] = _ts()

    usuario: Mapped[Usuario | None] = relationship(lazy="joined")


class SolicitudPersonal(Base):
    """Pedido de licencia, comisión o cambio de horario: lo hace la persona, lo aprueba
    su jefatura (o la Dirección) y Personal lo registra como justificativo."""

    __tablename__ = "solicitudes_personal"
    __table_args__ = (
        CheckConstraint("tipo IN ('licencia', 'comision', 'cambio_horario')", name="ck_solicitud_tipo"),
        CheckConstraint(
            "estado IN ('pendiente', 'aprobada', 'rechazada', 'cancelada', 'registrada')", name="ck_solicitud_estado"
        ),
    )
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    agente_id: Mapped[int] = mapped_column(ForeignKey("agentes.id"), index=True)
    tipo: Mapped[str] = mapped_column(String(20))
    clase: Mapped[str | None] = mapped_column(String(40))  # clase de licencia
    desde: Mapped[date] = mapped_column(Date)
    hasta: Mapped[date] = mapped_column(Date)
    hora_desde: Mapped[str | None] = mapped_column(String(5))
    hora_hasta: Mapped[str | None] = mapped_column(String(5))
    nueva_entrada: Mapped[str | None] = mapped_column(String(5))
    nueva_salida: Mapped[str | None] = mapped_column(String(5))
    lugar: Mapped[str | None] = mapped_column(String(300))
    motivo: Mapped[str | None] = mapped_column(Text)
    adjuntos: Mapped[list] = mapped_column(JSONB, default=list)
    estado: Mapped[str] = mapped_column(String(12), default="pendiente")
    pedido_por: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("usuarios.id"))
    pedido_en: Mapped[datetime] = _ts()
    decidido_por: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("usuarios.id"))
    decidido_en: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    respuesta: Mapped[str | None] = mapped_column(Text)
    registrado_por: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("usuarios.id"))
    registrado_en: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    agente: Mapped[Agente] = relationship(lazy="joined")
    solicitante: Mapped[Usuario | None] = relationship(foreign_keys=[pedido_por], lazy="joined")
    decisor: Mapped[Usuario | None] = relationship(foreign_keys=[decidido_por], lazy="joined")
    registrador: Mapped[Usuario | None] = relationship(foreign_keys=[registrado_por], lazy="joined")

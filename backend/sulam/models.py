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
    # Un tipo reservado solo es visible con el permiso "reservados.consultar"
    # o para quien tenga asignado el caso.
    reservado: Mapped[bool] = mapped_column(Boolean, default=False, server_default=text("false"))
    activo: Mapped[bool] = mapped_column(Boolean, default=True, server_default=text("true"))
    orden: Mapped[int] = mapped_column(Integer, default=0, server_default=text("0"))


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
    # Ej.: identidad de un denunciante. Requiere "reservados.consultar".
    reservado: Mapped[bool] = mapped_column(Boolean, default=False, server_default=text("false"))
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
    reservado: Mapped[bool] = mapped_column(Boolean, default=False, server_default=text("false"))
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
    reservado: Mapped[bool] = mapped_column(Boolean, default=False, server_default=text("false"))
    cargado_por: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("usuarios.id"))
    cargado_en: Mapped[datetime] = _ts()
    eliminado_en: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    eliminado_por: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("usuarios.id"))
    motivo_eliminacion: Mapped[str | None] = mapped_column(Text)

    tipo_documental: Mapped[TipoDocumental] = relationship(lazy="joined")


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

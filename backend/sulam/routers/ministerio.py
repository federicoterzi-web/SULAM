"""Integración con el Sistema de Expedientes del Ministerio de Desarrollo Social.

La extensión de Chrome «SULAM · Expedientes del Ministerio» lee la Bandeja de
Entrada de la Dirección con la sesión de la persona que la usa (solo lo que esa
persona ya puede ver) y envía los datos acá:

- cada expediente queda guardado en `expedientes_ministerio` (lo último leído);
- cada pase que llegó a la Dirección se registra una sola vez como ingreso de
  Mesa de Entrada, con el DNI del beneficiario para sugerir el legajo.

La extensión se identifica con una clave personal («token de integración»)
que la persona genera en SULAM y puede revocar cuando quiera. La clave tiene
los mismos permisos que su dueño.
"""

from __future__ import annotations

import hashlib
import re
import secrets
import uuid
from datetime import date, datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from .. import audit
from ..db import get_db
from ..deps import contexto, ip_cliente
from ..models import Expediente, ExpedienteMinisterio, Ingreso, Persona, TipoDocumental, TokenIntegracion
from ..numbering import numero_ingreso
from ..permissions import Contexto, permisos_efectivos, requerir_persona
from ..security import ahora
from ..serializers import expediente_out, persona_resumen
from ..textutil import escapar_like, normalizar, normalizar_documento
from ._comun import no_encontrado, obtener_persona, registrar_actividad_caso, validar_pertenencia

router = APIRouter(tags=["expedientes del ministerio"])

OFICINA_PREDETERMINADA = "DIRECCION DE ADULTOS MAYORES"
PREFIJO_TOKEN = "sulam_"
CLAVE_RE = re.compile(r"^\s*(\d+)\s*/\s*(\d+)\s*-\s*([A-Za-z]+)\s*-\s*(\d{4})\s*$")
MAX_EXPEDIENTES_POR_ENVIO = 50


# ---------------------------------------------------------------------------
# Autenticación por token (la usa la extensión)
# ---------------------------------------------------------------------------


def _hash(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def contexto_integracion(request: Request, db: Session = Depends(get_db)) -> Contexto:
    cabecera = request.headers.get("authorization", "")
    token = cabecera[7:].strip() if cabecera.lower().startswith("bearer ") else ""
    if not token.startswith(PREFIJO_TOKEN):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Falta la clave de integración de SULAM.")
    t = db.execute(
        select(TokenIntegracion).where(TokenIntegracion.token_hash == _hash(token))
    ).scalar_one_or_none()
    if t is None or t.revocado_en is not None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "La clave de integración no existe o fue revocada.")
    usuario = t.usuario
    if not usuario.activo:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "El usuario dueño de la clave está dado de baja.")
    t.ultimo_uso_en = ahora()
    return Contexto(usuario=usuario, sesion=None, ip=ip_cliente(request), permisos=permisos_efectivos(usuario))


# ---------------------------------------------------------------------------
# Claves de integración (las administra cada persona desde SULAM)
# ---------------------------------------------------------------------------


class TokenIn(BaseModel):
    nombre: str = Field("Extensión de Chrome", min_length=1, max_length=100)


def _token_out(t: TokenIntegracion) -> dict:
    return {
        "id": str(t.id),
        "nombre": t.nombre,
        "prefijo": t.prefijo,
        "creado_en": t.creado_en.isoformat() if t.creado_en else None,
        "ultimo_uso_en": t.ultimo_uso_en.isoformat() if t.ultimo_uso_en else None,
        "revocado_en": t.revocado_en.isoformat() if t.revocado_en else None,
    }


@router.get("/integracion/tokens")
def listar_tokens(ctx: Contexto = Depends(contexto), db: Session = Depends(get_db)):
    tokens = db.execute(
        select(TokenIntegracion)
        .where(TokenIntegracion.usuario_id == ctx.id)
        .order_by(TokenIntegracion.creado_en.desc())
    ).scalars()
    return [_token_out(t) for t in tokens]


@router.post("/integracion/tokens", status_code=201)
def crear_token(datos: TokenIn, ctx: Contexto = Depends(contexto), db: Session = Depends(get_db)):
    ctx.requerir("mesa_entrada", "crear")
    if ctx.sesion is None:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Las claves se generan desde SULAM.")
    token = PREFIJO_TOKEN + secrets.token_urlsafe(32)
    t = TokenIntegracion(
        usuario_id=ctx.id, nombre=datos.nombre.strip(), token_hash=_hash(token), prefijo=token[:12]
    )
    db.add(t)
    db.flush()
    db.refresh(t)
    audit.registrar(db, ctx, "crear", "token_integracion", t.id, None, {"nombre": t.nombre})
    db.commit()
    return {**_token_out(t), "token": token}


@router.delete("/integracion/tokens/{token_id}")
def revocar_token(token_id: uuid.UUID, ctx: Contexto = Depends(contexto), db: Session = Depends(get_db)):
    t = db.get(TokenIntegracion, token_id)
    if t is None or t.usuario_id != ctx.id:
        raise no_encontrado("Clave")
    if t.revocado_en is None:
        t.revocado_en = ahora()
        audit.registrar(db, ctx, "revocar", "token_integracion", t.id, None, {"nombre": t.nombre})
    db.commit()
    return _token_out(t)


# ---------------------------------------------------------------------------
# Lo que envía la extensión
# ---------------------------------------------------------------------------


class _Libre(BaseModel):
    model_config = ConfigDict(extra="ignore")


class Marca(_Libre):
    """Fecha, hora y usuario del Ministerio («09/10/2026-1310-CABRERAC»)."""

    fecha: datetime | None = None
    usuario: str | None = Field(None, max_length=100)
    texto: str | None = Field(None, max_length=100)


class Movimiento(_Libre):
    ingreso: Marca | None = None
    fojas_ingreso: int | None = None
    oficina_origen: str | None = Field(None, max_length=300)
    nota: str | None = Field(None, max_length=2000)
    oficina: str | None = Field(None, max_length=300)
    recepcion: Marca | None = None
    reparticion: str | None = Field(None, max_length=100)
    comentarios: str | None = Field(None, max_length=4000)
    egreso: Marca | None = None
    fojas_egreso: int | None = None
    estado: str | None = Field(None, max_length=60)
    dias_sin_recepcion: int | None = None
    dias_pendiente: int | None = None


class FilaBandeja(_Libre):
    asignado: str | None = Field(None, max_length=100)
    fecha_asignacion: date | None = None
    formato: str | None = Field(None, max_length=30)
    fecha_ingreso: date | None = None
    nomenclador: str | None = Field(None, max_length=200)
    asunto: str | None = Field(None, max_length=4000)
    causante: str | None = Field(None, max_length=300)
    estado: str | None = Field(None, max_length=60)


class Detalle(_Libre):
    oficina_origen: str | None = Field(None, max_length=300)
    fecha_ingreso: datetime | None = None
    causante: str | None = Field(None, max_length=300)
    beneficiario: str | None = Field(None, max_length=300)
    beneficiario_documento: str | None = Field(None, max_length=30)
    asunto: str | None = Field(None, max_length=4000)
    nomenclador: str | None = Field(None, max_length=200)
    prioridad: str | None = Field(None, max_length=60)
    formato: str | None = Field(None, max_length=30)
    asignado_a: str | None = Field(None, max_length=100)


class ExpedienteIn(_Libre):
    clave: str = Field(..., max_length=40)
    url: str | None = Field(None, max_length=500)
    en_bandeja: bool = True
    bandeja: FilaBandeja | None = None
    detalle: Detalle | None = None
    movimientos: list[Movimiento] = Field(default_factory=list, max_length=300)


class SincronizarIn(_Libre):
    oficina: str | None = Field(None, max_length=300)
    crear_ingresos_desde: date | None = None
    expedientes: list[ExpedienteIn] = Field(..., max_length=MAX_EXPEDIENTES_POR_ENVIO)
    # Solo en el último envío de una lectura completa de la bandeja: todos los expedientes
    # que hoy están en la Dirección. Los demás se marcan como que ya no están.
    claves_en_bandeja: list[str] | None = Field(None, max_length=5000)


# ---------------------------------------------------------------------------
# Lógica
# ---------------------------------------------------------------------------


def separar_clave(clave: str) -> tuple[str, int, int, str, int]:
    m = CLAVE_RE.match(clave or "")
    if not m:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, f"Número de expediente inválido: {clave!r}.")
    numero, codigo, letra, anio = int(m.group(1)), int(m.group(2)), m.group(3).upper(), int(m.group(4))
    return f"{numero}/{codigo}-{letra}-{anio}", numero, codigo, letra, anio


def _texto(valor: str | None) -> str | None:
    if valor is None:
        return None
    limpio = re.sub(r"\s+", " ", valor).strip()
    return limpio or None


def _asunto_limpio(e: ExpedienteIn) -> str | None:
    """El asunto de la bandeja es el que escribió quien pidió el expediente; el del
    detalle viene precedido por la descripción del nomenclador («..._REF. ...»)."""
    if e.bandeja and _texto(e.bandeja.asunto):
        return _texto(e.bandeja.asunto)
    if e.detalle and _texto(e.detalle.asunto):
        a = _texto(e.detalle.asunto)
        return a.split("_", 1)[1].strip() if "_" in a else a
    return None


def _beneficiario(e: ExpedienteIn) -> tuple[str | None, str | None]:
    if not e.detalle:
        return None, None
    nombre = _texto(e.detalle.beneficiario)
    doc = normalizar_documento(e.detalle.beneficiario_documento)
    if nombre and not doc:
        m = re.search(r"D\.?\s*N\.?\s*I\.?\s*:?\s*([\d.]{6,12})", nombre, re.I)
        if m:
            doc = normalizar_documento(m.group(1))
    if nombre:
        nombre = re.sub(r"\s*-\s*D\.?\s*N\.?\s*I\.?.*$", "", nombre, flags=re.I).strip() or None
        if nombre and normalizar(nombre) in ("sin beneficiario cargado", "sin beneficiario"):
            nombre = None
    if doc and set(doc) == {"0"}:
        doc = None
    return nombre, doc


def _es_oficina(oficina: str | None, nuestra: str) -> bool:
    return bool(oficina) and normalizar(oficina) == normalizar(nuestra)


def _marca_json(m: Marca | None) -> dict | None:
    if m is None:
        return None
    return {"fecha": m.fecha.isoformat() if m.fecha else None, "usuario": m.usuario, "texto": m.texto}


def _clave_pase(clave: str, mov: Movimiento) -> str | None:
    marca = mov.ingreso
    if marca is None:
        return None
    if marca.texto:
        return f"{clave}|{_texto(marca.texto)}"[:120]
    if marca.fecha:
        return f"{clave}|{marca.fecha.isoformat()}"[:120]
    return None


def _a_local(fecha: datetime) -> datetime:
    return fecha if fecha.tzinfo else fecha.replace(tzinfo=timezone.utc)


def _tipo_documental(db: Session, nomenclador: str | None) -> TipoDocumental | None:
    nombre = "Oficio" if nomenclador and nomenclador.upper().startswith("OFICIO") else "Expediente administrativo"
    return db.execute(select(TipoDocumental).where(TipoDocumental.nombre == nombre)).scalars().first()


def _guardar_expediente(db: Session, ctx: Contexto, e: ExpedienteIn, clave: str, partes) -> tuple[ExpedienteMinisterio, bool]:
    _, numero, codigo, letra, anio = partes
    em = db.execute(select(ExpedienteMinisterio).where(ExpedienteMinisterio.clave == clave)).scalar_one_or_none()
    nuevo = em is None
    if nuevo:
        em = ExpedienteMinisterio(clave=clave, numero=numero, codigo=codigo, letra=letra, anio=anio)
        db.add(em)
    d, b = e.detalle, e.bandeja
    nombre, doc = _beneficiario(e)
    ultimo = e.movimientos[-1] if e.movimientos else None
    em.url = e.url or em.url
    em.formato = _texto((b and b.formato) or (d and d.formato)) or em.formato
    em.nomenclador = _texto((d and d.nomenclador) or (b and b.nomenclador)) or em.nomenclador
    em.asunto = _asunto_limpio(e) or em.asunto
    em.causante = _texto((d and d.causante) or (b and b.causante)) or em.causante
    if d is not None:
        em.beneficiario = nombre
        em.documento_beneficiario = doc
        em.prioridad = _texto(d.prioridad)
        em.oficina_origen = _texto(d.oficina_origen)
        em.fecha_ingreso_ministerio = _a_local(d.fecha_ingreso) if d.fecha_ingreso else em.fecha_ingreso_ministerio
    if b is not None:
        em.asignado_a = _texto(b.asignado)
        em.fecha_asignacion = b.fecha_asignacion
    elif d is not None and d.asignado_a:
        em.asignado_a = _texto(d.asignado_a)
    if ultimo is not None:
        em.estado = _texto(ultimo.estado) or (b and _texto(b.estado)) or em.estado
        em.oficina_actual = _texto(ultimo.oficina) or em.oficina_actual
    elif b is not None:
        em.estado = _texto(b.estado) or em.estado
    em.en_bandeja = e.en_bandeja
    if e.movimientos:
        em.movimientos = [
            {
                **m.model_dump(mode="json", exclude={"ingreso", "recepcion", "egreso"}),
                "ingreso": _marca_json(m.ingreso),
                "recepcion": _marca_json(m.recepcion),
                "egreso": _marca_json(m.egreso),
            }
            for m in e.movimientos
        ]
    em.ultima_sincronizacion_en = ahora()
    em.sincronizado_por = ctx.id
    db.flush()
    return em, nuevo


def _crear_ingresos(
    db: Session, ctx: Contexto, em: ExpedienteMinisterio, e: ExpedienteIn, oficina: str, desde: date | None
) -> list[Ingreso]:
    creados: list[Ingreso] = []
    nombre, doc = _beneficiario(e)
    tipo = None
    for mov in e.movimientos:
        if not _es_oficina(mov.oficina, oficina):
            continue
        clave_pase = _clave_pase(em.clave, mov)
        if clave_pase is None:
            continue
        llegada = (mov.recepcion and mov.recepcion.fecha) or (mov.ingreso and mov.ingreso.fecha)
        if desde and llegada and _a_local(llegada).date() < desde:
            continue
        existe = db.execute(select(Ingreso.id).where(Ingreso.pase_ministerio_clave == clave_pase)).first()
        if existe:
            continue
        if tipo is None:
            tipo = _tipo_documental(db, em.nomenclador)
        observaciones = [f"Cargado desde el Sistema de Expedientes del Ministerio (expediente {em.clave})."]
        if em.nomenclador:
            observaciones.append(f"Nomenclador: {em.nomenclador}.")
        if em.prioridad:
            observaciones.append(f"Prioridad: {em.prioridad}.")
        if _texto(mov.nota):
            observaciones.append(f"Nota del pase: {_texto(mov.nota)}.")
        if em.causante:
            observaciones.append(f"Causante: {em.causante}.")
        if mov.recepcion is None:
            observaciones.append("Al momento de la carga, el pase todavía no estaba recepcionado en el Ministerio.")
        ingreso = Ingreso(
            numero=numero_ingreso(db),
            fecha_ingreso=_a_local(llegada) if llegada else ahora(),
            remitente=("Sistema de Expedientes MDS · " + (_texto(mov.oficina_origen) or "sin oficina de origen"))[:300],
            tipo_documental_id=tipo.id if tipo else None,
            asunto=(em.asunto or em.nomenclador or f"Expediente {em.clave}"),
            folios=mov.fojas_ingreso,
            persona_mencionada=nombre,
            documento_mencionado=doc,
            numero_expediente_externo=em.clave,
            observaciones=" ".join(observaciones),
            creado_por=ctx.id,
            pase_ministerio_clave=clave_pase,
            expediente_ministerio_id=em.id,
        )
        db.add(ingreso)
        db.flush()
        audit.registrar(
            db, ctx, "crear", "ingreso", ingreso.id, None,
            {"numero": ingreso.numero, "origen": "sistema_expedientes_ministerio", "expediente": em.clave},
        )
        creados.append(ingreso)
    return creados


def _personas_por_documento(db: Session, documentos: set[str]) -> dict[str, Persona]:
    if not documentos:
        return {}
    filas = db.execute(
        select(Persona).where(Persona.numero_documento.in_(documentos), Persona.unificada_en_id.is_(None))
    ).scalars()
    return {p.numero_documento: p for p in filas}


def _estado_expediente(db: Session, em: ExpedienteMinisterio, personas: dict[str, Persona]) -> dict:
    ingresos = db.execute(
        select(Ingreso).where(Ingreso.expediente_ministerio_id == em.id).order_by(Ingreso.fecha_ingreso)
    ).scalars().all()
    vinculada = None
    for i in reversed(ingresos):
        if i.persona_id:
            vinculada = db.get(Persona, i.persona_id)
            break
    sugerida = personas.get(em.documento_beneficiario) if em.documento_beneficiario else None
    propio = db.execute(select(Expediente).where(Expediente.expediente_ministerio_id == em.id)).scalar_one_or_none()
    if propio is not None and vinculada is None:
        vinculada = db.get(Persona, propio.persona_id)
    return {
        "clave": em.clave,
        "id": str(em.id),
        "expediente_id": str(propio.id) if propio else None,
        "ingresos": [
            {"id": str(i.id), "numero": i.numero, "fecha_ingreso": i.fecha_ingreso.isoformat(), "vinculado": bool(i.persona_id)}
            for i in ingresos
        ],
        "persona": persona_resumen(vinculada) if vinculada else None,
        "persona_sugerida": persona_resumen(sugerida) if (sugerida and not vinculada) else None,
    }


# ---------------------------------------------------------------------------
# Rutas de la extensión
# ---------------------------------------------------------------------------


@router.get("/integracion/yo")
def quien_soy(ctx: Contexto = Depends(contexto_integracion), db: Session = Depends(get_db)):
    db.commit()
    return {
        "usuario": ctx.usuario.usuario,
        "nombre": ctx.usuario.nombre_completo,
        "puede_cargar": ctx.tiene("mesa_entrada", "crear"),
        "oficina": OFICINA_PREDETERMINADA,
    }


@router.post("/integracion/ministerio/sincronizar")
def sincronizar(datos: SincronizarIn, ctx: Contexto = Depends(contexto_integracion), db: Session = Depends(get_db)):
    ctx.requerir("mesa_entrada", "crear")
    oficina = _texto(datos.oficina) or OFICINA_PREDETERMINADA
    resultados = []
    total_ingresos = 0
    tocados: list[ExpedienteMinisterio] = []
    for e in datos.expedientes:
        partes = separar_clave(e.clave)
        clave = partes[0]
        em, nuevo = _guardar_expediente(db, ctx, e, clave, partes)
        creados = _crear_ingresos(db, ctx, em, e, oficina, datos.crear_ingresos_desde)
        total_ingresos += len(creados)
        tocados.append(em)
        resultados.append(
            {"clave": clave, "nuevo": nuevo, "ingresos_creados": [i.numero for i in creados]}
        )
    personas = _personas_por_documento(db, {em.documento_beneficiario for em in tocados if em.documento_beneficiario})
    for r, em in zip(resultados, tocados):
        r.update(_estado_expediente(db, em, personas))
    salieron = 0
    if datos.claves_en_bandeja is not None:
        presentes = set()
        for c in datos.claves_en_bandeja:
            m = CLAVE_RE.match(c)
            if m:
                presentes.add(f"{int(m.group(1))}/{int(m.group(2))}-{m.group(3).upper()}-{m.group(4)}")
        for em in db.execute(
            select(ExpedienteMinisterio).where(ExpedienteMinisterio.en_bandeja.is_(True))
        ).scalars():
            if em.clave not in presentes:
                em.en_bandeja = False
                salieron += 1
    audit.registrar(
        db, ctx, "sincronizar", "expedientes_ministerio", None, None,
        {"expedientes": len(resultados), "ingresos_creados": total_ingresos, "salieron_de_bandeja": salieron},
    )
    db.commit()
    return {
        "expedientes": len(resultados),
        "ingresos_creados": total_ingresos,
        "salieron_de_bandeja": salieron,
        "resultados": resultados,
    }


@router.get("/integracion/ministerio/estado")
def estado(
    claves: str = Query(..., max_length=5000),
    ctx: Contexto = Depends(contexto_integracion),
    db: Session = Depends(get_db),
):
    """Qué sabe SULAM de cada expediente (para marcar las filas de la bandeja del Ministerio)."""
    ctx.requerir("mesa_entrada", "consultar")
    pedidas = []
    for c in claves.split(","):
        m = CLAVE_RE.match(c)
        if m:
            pedidas.append(f"{int(m.group(1))}/{int(m.group(2))}-{m.group(3).upper()}-{m.group(4)}")
    pedidas = pedidas[:200]
    ems = db.execute(select(ExpedienteMinisterio).where(ExpedienteMinisterio.clave.in_(pedidas))).scalars().all()
    personas = _personas_por_documento(db, {em.documento_beneficiario for em in ems if em.documento_beneficiario})
    db.commit()
    return {em.clave: _estado_expediente(db, em, personas) for em in ems}


# ---------------------------------------------------------------------------
# Rutas de la interfaz de SULAM
# ---------------------------------------------------------------------------


def expediente_ministerio_out(em: ExpedienteMinisterio) -> dict:
    return {
        "id": str(em.id),
        "clave": em.clave,
        "url": em.url,
        "formato": em.formato,
        "nomenclador": em.nomenclador,
        "asunto": em.asunto,
        "causante": em.causante,
        "beneficiario": em.beneficiario,
        "documento_beneficiario": em.documento_beneficiario,
        "prioridad": em.prioridad,
        "oficina_origen": em.oficina_origen,
        "fecha_ingreso_ministerio": em.fecha_ingreso_ministerio.isoformat() if em.fecha_ingreso_ministerio else None,
        "asignado_a": em.asignado_a,
        "fecha_asignacion": em.fecha_asignacion.isoformat() if em.fecha_asignacion else None,
        "estado": em.estado,
        "oficina_actual": em.oficina_actual,
        "en_bandeja": em.en_bandeja,
        "ultima_sincronizacion_en": em.ultima_sincronizacion_en.isoformat(),
    }


@router.get("/ministerio/expedientes")
def listar_expedientes_ministerio(
    q: str = Query("", max_length=200),
    en_bandeja: bool = False,
    limite: int = Query(200, ge=1, le=1000),
    ctx: Contexto = Depends(contexto),
    db: Session = Depends(get_db),
):
    ctx.requerir("mesa_entrada", "consultar")
    consulta = select(ExpedienteMinisterio)
    if en_bandeja:
        consulta = consulta.where(ExpedienteMinisterio.en_bandeja.is_(True))
    if q.strip():
        patron = "%" + escapar_like(q.strip()) + "%"
        consulta = consulta.where(
            or_(
                ExpedienteMinisterio.clave.ilike(patron),
                ExpedienteMinisterio.asunto.ilike(patron),
                ExpedienteMinisterio.beneficiario.ilike(patron),
                ExpedienteMinisterio.documento_beneficiario.ilike(patron),
                ExpedienteMinisterio.nomenclador.ilike(patron),
            )
        )
    ems = db.execute(
        consulta.order_by(ExpedienteMinisterio.ultima_sincronizacion_en.desc(), ExpedienteMinisterio.anio.desc(), ExpedienteMinisterio.numero.desc()).limit(limite)
    ).scalars().all()
    personas = _personas_por_documento(db, {em.documento_beneficiario for em in ems if em.documento_beneficiario})
    return [{**expediente_ministerio_out(em), **_estado_expediente(db, em, personas)} for em in ems]


@router.get("/ministerio/expedientes/{expediente_id}")
def ver_expediente_ministerio(expediente_id: uuid.UUID, ctx: Contexto = Depends(contexto), db: Session = Depends(get_db)):
    ctx.requerir("mesa_entrada", "consultar")
    em = db.get(ExpedienteMinisterio, expediente_id)
    if em is None:
        raise no_encontrado("Expediente del Ministerio")
    personas = _personas_por_documento(db, {em.documento_beneficiario} if em.documento_beneficiario else set())
    r = {**expediente_ministerio_out(em), **_estado_expediente(db, em, personas), "movimientos": em.movimientos}
    audit.registrar(db, ctx, "consultar", "expediente_ministerio", em.id, None, {"clave": em.clave})
    db.commit()
    return r


class VincularExpedienteIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    persona_id: uuid.UUID
    caso_id: uuid.UUID | None = None


@router.post("/ministerio/expedientes/{expediente_id}/vincular", status_code=201)
def vincular_expediente_ministerio(
    expediente_id: uuid.UUID,
    datos: VincularExpedienteIn,
    ctx: Contexto = Depends(contexto),
    db: Session = Depends(get_db),
):
    """Crea el expediente del legajo que corresponde a este expediente del Ministerio.

    Desde ahí se manejan sus pases internos, la carpeta en papel y los documentos digitales.
    """
    ctx.requerir("mesa_entrada", "consultar")
    em = db.get(ExpedienteMinisterio, expediente_id)
    if em is None:
        raise no_encontrado("Expediente del Ministerio")
    persona = obtener_persona(db, datos.persona_id)
    requerir_persona(db, ctx, persona, "expedientes", "crear")
    existente = db.execute(select(Expediente).where(Expediente.expediente_ministerio_id == em.id)).scalar_one_or_none()
    if existente is not None:
        raise HTTPException(status.HTTP_409_CONFLICT, "Este expediente ya está vinculado a un legajo.")
    caso, _ = validar_pertenencia(db, persona.id, datos.caso_id, None)
    exp = Expediente(
        numero=em.clave,
        tipo="administrativo",
        organismo="Ministerio de Desarrollo Social",
        caratula=em.asunto[:2000] if em.asunto else None,
        persona_id=persona.id,
        caso_id=caso.id if caso else None,
        expediente_ministerio_id=em.id,
        creado_por=ctx.id,
    )
    db.add(exp)
    db.flush()
    if caso:
        registrar_actividad_caso(caso)
    # Los ingresos de Mesa de Entrada que ya estaban en este legajo quedan ligados al expediente.
    for i in db.execute(select(Ingreso).where(Ingreso.expediente_ministerio_id == em.id)).scalars():
        if i.persona_id == persona.id and i.expediente_id is None:
            i.expediente_id = exp.id
    audit.registrar(
        db, ctx, "crear", "expediente", exp.id, persona.id,
        {"numero": exp.numero, "tipo": exp.tipo, "caso_id": exp.caso_id, "origen": "ministerio"},
    )
    db.commit()
    return expediente_out(exp)

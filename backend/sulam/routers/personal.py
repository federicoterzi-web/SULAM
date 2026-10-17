"""Personal: asistencias (portado de «Asistencia DAM») y solicitudes de licencia,
comisión y cambio de horario.

Permisos (módulo «personal»):
- consultar: ver personal, jornadas, justificativos (Personal y Dirección).
- administrar: altas y bajas, horarios, reloj, justificativos, revisiones (Personal).
- aprobar: aprobar solicitudes. «área» = de su área (no las propias); «todos» = todas.
Cada persona ve sus propias jornadas y solicitudes («Mi asistencia»).

Privacidad: el motivo y los adjuntos de una licencia por enfermedad los ven la
persona, Personal y la Dirección; la jefatura ve tipo y fechas.
"""

from __future__ import annotations

import hashlib
import io
import uuid
from datetime import date, datetime, timedelta
from urllib.parse import quote

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile, status
from fastapi.responses import StreamingResponse
from pydantic import Field
from sqlalchemy import and_, func, or_, select
from sqlalchemy.orm import Session

from .. import audit
from ..asistencia import CODIGOS, CRITERIOS, INCIDENCIAS, ErrorAsistencia, coincide_nombre, informe, leer_reloj, tramo, validar_revision, validar_semana
from ..config import get_settings
from ..db import get_db
from ..deps import contexto
from ..models import (
    Agente,
    Area,
    Horario,
    Justificativo,
    Marcacion,
    RelojImportacion,
    RevisionJornada,
    Rol,
    SolicitudPersonal,
    Usuario,
)
from ..permissions import Contexto
from ..schemas import Entrada
from ..security import ahora, hash_password, revocar_sesiones_usuario, validar_password_nueva
from ..serializers import usuario_breve
from ..storage import almacenamiento_actual, almacenamiento_por_nombre, detectar_mime
from ._comun import no_encontrado

router = APIRouter(tags=["personal"])

CLASES_LICENCIA = {
    "anual": "Licencia anual ordinaria",
    "enfermedad": "Por enfermedad",
    "familiar": "Atención de familiar",
    "examen": "Por examen",
    "particular": "Razones particulares",
    "otra": "Otra",
}
TIPOS_SOLICITUD = {"licencia": "Licencia", "comision": "Comisión de servicio", "cambio_horario": "Cambio de horario"}
MAX_ADJUNTO = 10 * 1024 * 1024


def _hoy() -> date:
    return ahora().astimezone().date()


def _error(e: ErrorAsistencia):
    return HTTPException(status.HTTP_400_BAD_REQUEST, str(e))


# ---------------------------------------------------------------- permisos


def _puede_consultar(ctx: Contexto) -> bool:
    return ctx.tiene("personal", "consultar") or ctx.tiene("personal", "administrar")


def _requerir_consulta(ctx: Contexto) -> None:
    if not _puede_consultar(ctx):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Solo Personal y la Dirección ven esta información.")


def _requerir_admin(ctx: Contexto) -> None:
    ctx.requerir("personal", "administrar")


def _mi_agente(db: Session, ctx: Contexto) -> Agente | None:
    return db.execute(select(Agente).where(Agente.usuario_id == ctx.id)).scalar_one_or_none()


def _obtener(db: Session, modelo, ident, nombre: str):
    obj = db.get(modelo, ident)
    if obj is None:
        raise no_encontrado(nombre)
    return obj


def _agente(db: Session, agente_id: int) -> Agente:
    a = db.get(Agente, agente_id)
    if a is None:
        raise no_encontrado("Agente")
    return a


def _puede_aprobar(ctx: Contexto, s: SolicitudPersonal) -> bool:
    if s.agente.usuario_id == ctx.id:
        return False  # nadie aprueba lo propio
    alc = ctx.alcance("personal", "aprobar")
    if alc == "todos":
        return True
    return alc == "area" and s.agente.area_id is not None and s.agente.area_id == ctx.usuario.area_id


def _ve_detalle_sensible(ctx: Contexto, s: SolicitudPersonal) -> bool:
    if s.clase != "enfermedad":
        return True
    return s.agente.usuario_id == ctx.id or s.pedido_por == ctx.id or ctx.alcance("personal", "consultar") == "todos" or ctx.tiene("personal", "administrar")


# ---------------------------------------------------------------- salida


def _activo(a: Agente, dia: date | None = None) -> bool:
    d = (dia or _hoy()).isoformat()
    return any((not p.get("desde") or p["desde"] <= d) and (not p.get("hasta") or p["hasta"] >= d) for p in a.periodos or [])


def _agente_out(db: Session, a: Agente, horarios: list[Horario] | None = None) -> dict:
    hs = horarios if horarios is not None else db.execute(
        select(Horario).where(Horario.agente_id == a.id).order_by(Horario.vigente_desde.desc())
    ).scalars().all()
    return {
        "id": a.id,
        "nombre": a.nombre,
        "area": {"id": a.area.id, "nombre": a.area.nombre} if a.area else None,
        "cargo": a.cargo,
        "id_reloj": a.id_reloj,
        "boleta": a.boleta,
        "usuario": usuario_breve(a.usuario) | {"activo": a.usuario.activo} if a.usuario else None,
        "periodos": a.periodos,
        "activo": _activo(a),
        "revision": a.revision,
        "horarios": [
            {
                "id": h.id, "vigente_desde": h.vigente_desde.isoformat(), "vigente_hasta": h.vigente_hasta.isoformat() if h.vigente_hasta else None,
                "semana": h.semana, "confirmado": h.confirmado, "fuente": h.fuente,
            }
            for h in hs
        ],
    }


def _justificativo_out(j: Justificativo) -> dict:
    return {
        "id": j.id, "agente": {"id": j.agente.id, "nombre": j.agente.nombre}, "codigo": j.codigo,
        "desde": j.desde.isoformat(), "hasta": j.hasta.isoformat(), "hora_desde": j.hora_desde, "hora_hasta": j.hora_hasta,
        "excepcion_desde": j.excepcion_desde, "excepcion_hasta": j.excepcion_hasta, "referencia": j.referencia, "notas": j.notas,
        "estado": j.estado, "requiere_horario": j.requiere_horario, "revision": j.revision, "fundamento": j.fundamento,
        "adjuntos": [{k: x[k] for k in ("id", "nombre", "mime")} for x in (j.adjuntos or [])],
        "solicitud_id": j.solicitud_id, "usuario": usuario_breve(j.usuario), "en": j.en.isoformat(),
    }


def _solicitud_out(ctx: Contexto, s: SolicitudPersonal) -> dict:
    sensible = _ve_detalle_sensible(ctx, s)
    return {
        "id": s.id, "agente": {"id": s.agente.id, "nombre": s.agente.nombre, "area": s.agente.area.nombre if s.agente.area else None},
        "tipo": s.tipo, "tipo_texto": TIPOS_SOLICITUD[s.tipo], "clase": s.clase, "clase_texto": CLASES_LICENCIA.get(s.clase or "", None),
        "desde": s.desde.isoformat(), "hasta": s.hasta.isoformat(), "hora_desde": s.hora_desde, "hora_hasta": s.hora_hasta,
        "nueva_entrada": s.nueva_entrada, "nueva_salida": s.nueva_salida, "lugar": s.lugar,
        "motivo": s.motivo if sensible else None,
        "adjuntos": [{k: x[k] for k in ("id", "nombre", "mime")} for x in (s.adjuntos or [])] if sensible else [],
        "detalle_reservado": not sensible,
        "estado": s.estado, "pedido_por": usuario_breve(s.solicitante), "pedido_en": s.pedido_en.isoformat(),
        "decidido_por": usuario_breve(s.decisor), "decidido_en": s.decidido_en.isoformat() if s.decidido_en else None,
        "respuesta": s.respuesta, "registrado_por": usuario_breve(s.registrador),
        "registrado_en": s.registrado_en.isoformat() if s.registrado_en else None,
        "puedo_aprobar": s.estado == "pendiente" and _puede_aprobar(ctx, s),
        "puedo_cancelar": s.estado == "pendiente" and (s.pedido_por == ctx.id or s.agente.usuario_id == ctx.id),
        "puedo_registrar": s.estado == "aprobada" and ctx.tiene("personal", "administrar"),
    }


# ---------------------------------------------------------------- catálogo


@router.get("/personal/catalogo")
def catalogo(ctx: Contexto = Depends(contexto), db: Session = Depends(get_db)):
    return {
        "codigos": CODIGOS,
        "incidencias": INCIDENCIAS,
        "criterios": CRITERIOS,
        "clases_licencia": [{"codigo": k, "texto": v} for k, v in CLASES_LICENCIA.items()],
        "tipos": [{"codigo": k, "texto": v} for k, v in TIPOS_SOLICITUD.items()],
        "puedo": {
            "consultar": _puede_consultar(ctx),
            "administrar": ctx.tiene("personal", "administrar"),
            "aprobar": ctx.tiene("personal", "aprobar"),
        },
        "mi_agente": (lambda a: {"id": a.id, "nombre": a.nombre} if a else None)(_mi_agente(db, ctx)),
    }


# ---------------------------------------------------------------- agentes


class AgenteIn(Entrada):
    nombre: str = Field(min_length=3, max_length=200)
    fecha_ingreso: date
    area_id: int | None = None
    cargo: str | None = Field(default=None, max_length=200)
    id_reloj: str | None = Field(default=None, max_length=80)
    boleta: str | None = Field(default=None, max_length=80)
    usuario_id: uuid.UUID | None = None
    # Alta del usuario de SULAM junto con la persona (opcional).
    crear_usuario: str | None = Field(default=None, max_length=80)
    password_inicial: str | None = Field(default=None, max_length=200)
    roles: list[int] = Field(default_factory=list)


class AgentePatch(Entrada):
    nombre: str | None = Field(default=None, min_length=3, max_length=200)
    area_id: int | None = None
    cargo: str | None = Field(default=None, max_length=200)
    id_reloj: str | None = Field(default=None, max_length=80)
    boleta: str | None = Field(default=None, max_length=80)
    usuario_id: uuid.UUID | None = None


class AltaBajaIn(Entrada):
    activo: bool
    fecha: date
    revision_vista: int


class HorarioIn(Entrada):
    vigente_desde: date
    semana: dict
    confirmado: bool = False
    fuente: str = Field(min_length=5, max_length=1000)


@router.get("/personal/agentes")
def listar_agentes(incluir_bajas: bool = False, ctx: Contexto = Depends(contexto), db: Session = Depends(get_db)):
    _requerir_consulta(ctx)
    agentes = db.execute(select(Agente).order_by(Agente.nombre)).scalars().all()
    horarios: dict[int, list[Horario]] = {}
    for h in db.execute(select(Horario).order_by(Horario.vigente_desde.desc())).scalars():
        horarios.setdefault(h.agente_id, []).append(h)
    return [_agente_out(db, a, horarios.get(a.id, [])) for a in agentes if incluir_bajas or _activo(a)]


@router.get("/personal/usuarios-libres")
def usuarios_libres(ctx: Contexto = Depends(contexto), db: Session = Depends(get_db)):
    """Usuarios activos de SULAM que todavía no tienen ficha de personal."""
    _requerir_admin(ctx)
    tomados = select(Agente.usuario_id).where(Agente.usuario_id.is_not(None))
    filas = db.execute(
        select(Usuario).where(Usuario.activo.is_(True), Usuario.id.not_in(tomados)).order_by(Usuario.nombre_completo)
    ).scalars()
    return [{"id": str(u.id), "usuario": u.usuario, "nombre_completo": u.nombre_completo} for u in filas]


def _validar_usuario_libre(db: Session, usuario_id: uuid.UUID, agente_id: int | None = None) -> Usuario:
    u = db.get(Usuario, usuario_id)
    if u is None:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Usuario inexistente.")
    otro = db.execute(select(Agente).where(Agente.usuario_id == usuario_id, Agente.id != (agente_id or -1))).scalar_one_or_none()
    if otro is not None:
        raise HTTPException(status.HTTP_409_CONFLICT, f"Ese usuario ya corresponde a {otro.nombre}.")
    return u


@router.post("/personal/agentes", status_code=201)
def alta_agente(entrada: AgenteIn, ctx: Contexto = Depends(contexto), db: Session = Depends(get_db)):
    _requerir_admin(ctx)
    if entrada.area_id is not None and db.get(Area, entrada.area_id) is None:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Área inexistente.")
    id_reloj = (entrada.id_reloj or "").strip() or None
    if id_reloj and db.execute(select(Agente.id).where(Agente.id_reloj == id_reloj)).first():
        raise HTTPException(status.HTTP_409_CONFLICT, "Ese ID del reloj ya pertenece a otra persona, incluso si está dada de baja.")
    usuario = None
    if entrada.usuario_id:
        usuario = _validar_usuario_libre(db, entrada.usuario_id)
    elif entrada.crear_usuario:
        nombre_u = entrada.crear_usuario.strip().lower()
        if db.execute(select(Usuario.id).where(func.lower(Usuario.usuario) == nombre_u)).first():
            raise HTTPException(status.HTTP_409_CONFLICT, "Ese nombre de usuario ya existe.")
        error = validar_password_nueva(entrada.password_inicial or "")
        if error:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, error)
        usuario = Usuario(
            usuario=nombre_u, nombre_completo=entrada.nombre.strip(), area_id=entrada.area_id,
            password_hash=hash_password(entrada.password_inicial), debe_cambiar_password=True,
        )
        if entrada.roles:
            # Personal no da roles con permisos de administración: eso lo hace Administración.
            roles = db.execute(select(Rol).where(Rol.id.in_(entrada.roles))).scalars().all()
            if any(p.modulo == "administracion" for r in roles for p in r.permisos):
                raise HTTPException(status.HTTP_403_FORBIDDEN, "Los roles de administración los asigna Administración.")
            usuario.roles = list(roles)
        db.add(usuario)
        db.flush()
        audit.registrar(db, ctx, "crear", "usuario", usuario.id, detalle={"usuario": usuario.usuario, "desde": "personal"})
    a = Agente(
        nombre=entrada.nombre.strip(), area_id=entrada.area_id, cargo=(entrada.cargo or "").strip() or None,
        id_reloj=id_reloj, boleta=(entrada.boleta or "").strip() or None, usuario_id=usuario.id if usuario else None,
        periodos=[{"desde": entrada.fecha_ingreso.isoformat(), "hasta": None}],
    )
    db.add(a)
    db.flush()
    if usuario is not None and entrada.area_id is not None:
        usuario.area_id = entrada.area_id
    audit.registrar(db, ctx, "alta_agente", "agente", a.id, None, {"nombre": a.nombre, "ingreso": entrada.fecha_ingreso, "usuario": usuario.usuario if usuario else None})
    db.commit()
    db.refresh(a)
    return _agente_out(db, a)


@router.patch("/personal/agentes/{agente_id}")
def modificar_agente(agente_id: int, entrada: AgentePatch, ctx: Contexto = Depends(contexto), db: Session = Depends(get_db)):
    _requerir_admin(ctx)
    a = _agente(db, agente_id)
    cambios = entrada.model_dump(exclude_unset=True)
    antes = {k: getattr(a, k) for k in cambios}
    if "id_reloj" in cambios:
        nuevo = (cambios["id_reloj"] or "").strip() or None
        if nuevo != a.id_reloj:
            if nuevo and db.execute(select(Agente.id).where(Agente.id_reloj == nuevo, Agente.id != a.id)).first():
                raise HTTPException(status.HTTP_409_CONFLICT, "Ese ID ya pertenece a otra persona.")
            if db.execute(select(Marcacion.id).where(Marcacion.agente_id == a.id)).first():
                raise HTTPException(status.HTTP_409_CONFLICT, "El ID ya tiene marcaciones; conservá su identidad histórica.")
        cambios["id_reloj"] = nuevo
    if "area_id" in cambios and cambios["area_id"] is not None and db.get(Area, cambios["area_id"]) is None:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Área inexistente.")
    if cambios.get("usuario_id"):
        _validar_usuario_libre(db, cambios["usuario_id"], a.id)
    for k, v in cambios.items():
        setattr(a, k, v.strip() if isinstance(v, str) else v)
    # El área de personal manda: se refleja en el usuario de SULAM.
    if a.usuario_id and "area_id" in cambios:
        db.get(Usuario, a.usuario_id).area_id = a.area_id
    a.revision += 1
    audit.registrar(db, ctx, "modificar_agente", "agente", a.id, None, {"antes": antes, "despues": cambios})
    db.commit()
    db.refresh(a)
    return _agente_out(db, a)


@router.post("/personal/agentes/{agente_id}/alta-baja")
def alta_baja(agente_id: int, entrada: AltaBajaIn, ctx: Contexto = Depends(contexto), db: Session = Depends(get_db)):
    _requerir_admin(ctx)
    a = _agente(db, agente_id)
    if entrada.revision_vista != a.revision:
        raise HTTPException(status.HTTP_409_CONFLICT, "El estado de la persona cambió. Actualizá antes de continuar.")
    periodos = [dict(p) for p in (a.periodos or [])]
    abierto = next((p for p in periodos if not p.get("hasta")), None)
    f = entrada.fecha.isoformat()
    if entrada.activo:
        if abierto:
            raise HTTPException(status.HTTP_409_CONFLICT, "Ya está de alta.")
        if any(p.get("hasta") and p["hasta"] >= f for p in periodos):
            raise HTTPException(status.HTTP_400_BAD_REQUEST, "El reingreso debe ser posterior a la baja anterior.")
        periodos.append({"desde": f, "hasta": None})
    else:
        if not abierto:
            raise HTTPException(status.HTTP_409_CONFLICT, "Ya está de baja.")
        if abierto.get("desde") and f < abierto["desde"]:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, "La baja no puede ser anterior al ingreso.")
        if f == abierto.get("desde"):
            periodos.remove(abierto)
        else:
            abierto["hasta"] = (entrada.fecha - timedelta(days=1)).isoformat()
    a.periodos = periodos
    a.revision += 1
    usuario = db.get(Usuario, a.usuario_id) if a.usuario_id else None
    efecto_usuario = None
    if usuario is not None:
        if not entrada.activo and entrada.fecha <= _hoy() and usuario.activo:
            from .admin import _queda_un_administrador

            usuario.activo = False
            try:
                _queda_un_administrador(db)
            except HTTPException:
                db.rollback()
                raise
            revocar_sesiones_usuario(db, usuario.id)
            efecto_usuario = "usuario_desactivado"
        elif entrada.activo and not usuario.activo:
            usuario.activo = True
            efecto_usuario = "usuario_reactivado"
    audit.registrar(
        db, ctx, "reingreso_agente" if entrada.activo else "baja_agente", "agente", a.id, None,
        {"fecha": f, "usuario": usuario.usuario if usuario else None, "efecto": efecto_usuario},
    )
    db.commit()
    return {"ok": True, "efecto_usuario": efecto_usuario}


@router.post("/personal/agentes/{agente_id}/horarios")
def versionar_horario(agente_id: int, entrada: HorarioIn, ctx: Contexto = Depends(contexto), db: Session = Depends(get_db)):
    _requerir_admin(ctx)
    a = _agente(db, agente_id)
    try:
        semana = validar_semana(entrada.semana)
    except ErrorAsistencia as e:
        raise _error(e)
    antes = [{"desde": h.vigente_desde.isoformat(), "semana": h.semana, "confirmado": h.confirmado} for h in db.execute(select(Horario).where(Horario.agente_id == a.id)).scalars()]
    h = db.execute(select(Horario).where(Horario.agente_id == a.id, Horario.vigente_desde == entrada.vigente_desde)).scalar_one_or_none()
    if h is None:
        h = Horario(agente_id=a.id, vigente_desde=entrada.vigente_desde, semana=semana, confirmado=entrada.confirmado, fuente=entrada.fuente.strip())
        db.add(h)
    else:
        h.semana, h.confirmado, h.fuente = semana, entrada.confirmado, entrada.fuente.strip()
    db.flush()
    versiones = db.execute(select(Horario).where(Horario.agente_id == a.id).order_by(Horario.vigente_desde)).scalars().all()
    for i, v in enumerate(versiones):
        v.vigente_hasta = versiones[i + 1].vigente_desde - timedelta(days=1) if i + 1 < len(versiones) else None
    audit.registrar(db, ctx, "horario_versionado", "agente", a.id, None, {"antes": antes, "nuevo": {"desde": entrada.vigente_desde, "semana": semana, "confirmado": entrada.confirmado}})
    db.commit()
    return _agente_out(db, a)


# ---------------------------------------------------------------- reloj


def _importacion_out(db: Session, i: RelojImportacion) -> dict:
    con_id = {a.id_reloj: a for a in db.execute(select(Agente).where(Agente.id_reloj.is_not(None))).scalars()}
    sin = []
    for ident in i.identidades:
        if ident["id_reloj"] in con_id:
            continue
        sugerencias = [
            {"id": a.id, "nombre": a.nombre}
            for a in db.execute(select(Agente).where(Agente.id_reloj.is_(None))).scalars()
            if coincide_nombre(a.nombre, ident["nombre"])
        ]
        sin.append({**ident, "sugerencias": sugerencias})
    return {
        "id": i.id, "nombre_archivo": i.nombre_archivo, "sha256": i.sha256, "desde": i.desde.isoformat(), "hasta": i.hasta.isoformat(),
        "filas": i.filas, "errores": i.errores, "avisos": i.avisos, "sin_identificar": sin, "incorporada": i.incorporada,
        "en": i.en.isoformat(),
    }


def _leer_archivo(i: RelojImportacion) -> dict:
    with almacenamiento_por_nombre(i.almacenamiento).abrir(i.clave) as f:
        datos = f.read()
    if hashlib.sha256(datos).hexdigest() != i.sha256:
        raise HTTPException(status.HTTP_409_CONFLICT, "El archivo original fue modificado; no se usa como evidencia.")
    return leer_reloj(_decodificar(datos))


def _decodificar(datos: bytes) -> str:
    try:
        return datos.decode("utf-8")
    except UnicodeDecodeError:
        return datos.decode("cp1252", errors="replace")


@router.get("/personal/reloj")
def listar_importaciones(ctx: Contexto = Depends(contexto), db: Session = Depends(get_db)):
    _requerir_consulta(ctx)
    return [_importacion_out(db, i) for i in db.execute(select(RelojImportacion).order_by(RelojImportacion.desde.desc())).scalars()]


@router.post("/personal/reloj/previa", status_code=201)
def previa_reloj(archivo: UploadFile = File(...), ctx: Contexto = Depends(contexto), db: Session = Depends(get_db)):
    _requerir_admin(ctx)
    nombre = archivo.filename or "reloj.xls"
    if not nombre.lower().endswith((".xls", ".html", ".htm")):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Seleccioná el .xls del reloj.")
    datos = archivo.file.read(8 * 1024 * 1024 + 1)
    if len(datos) > 8 * 1024 * 1024:
        raise HTTPException(status.HTTP_413_REQUEST_ENTITY_TOO_LARGE, "El archivo supera los 8 MB.")
    if datos[:2] == b"PK" or datos[:2] == b"\xd0\xcf":
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Se espera el .xls del reloj (HTML), no un libro de Excel binario.")
    sha = hashlib.sha256(datos).hexdigest()
    existente = db.execute(select(RelojImportacion).where(RelojImportacion.sha256 == sha)).scalar_one_or_none()
    if existente is not None:
        return _importacion_out(db, existente)
    try:
        leido = leer_reloj(_decodificar(datos))
    except ErrorAsistencia as e:
        raise _error(e)
    almacen = almacenamiento_actual()
    g = almacen.guardar(io.BytesIO(datos))
    identidades = list({(r["id_reloj"], r["nombre"]): {"id_reloj": r["id_reloj"], "nombre": r["nombre"]} for r in leido["registros"]}.values())
    i = RelojImportacion(
        nombre_archivo=nombre[:300], sha256=sha, almacenamiento=almacen.nombre, clave=g.clave,
        desde=date.fromisoformat(leido["desde"]), hasta=date.fromisoformat(leido["hasta"]), filas=len(leido["registros"]),
        errores=leido["errores"], avisos=leido["avisos"], identidades=identidades, usuario_id=ctx.id,
    )
    db.add(i)
    db.flush()
    audit.registrar(db, ctx, "reloj_previsualizado", "reloj", i.id, None, {"archivo": nombre, "sha256": sha, "filas": i.filas, "errores": i.errores})
    db.commit()
    db.refresh(i)
    return _importacion_out(db, i)


class IdentificarIn(Entrada):
    id_reloj: str = Field(min_length=1, max_length=80)
    agente_id: int


@router.post("/personal/reloj/{importacion_id}/identificar")
def identificar(importacion_id: int, entrada: IdentificarIn, ctx: Contexto = Depends(contexto), db: Session = Depends(get_db)):
    """Asigna a una persona el ID del reloj que todavía no tenía."""
    _requerir_admin(ctx)
    i = _obtener(db, RelojImportacion, importacion_id, "Importación")
    if not any(x["id_reloj"] == entrada.id_reloj for x in i.identidades):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Ese ID no figura en el archivo.")
    a = _agente(db, entrada.agente_id)
    if a.id_reloj and a.id_reloj != entrada.id_reloj:
        raise HTTPException(status.HTTP_409_CONFLICT, f"{a.nombre} ya tiene otro ID del reloj ({a.id_reloj}).")
    if db.execute(select(Agente.id).where(Agente.id_reloj == entrada.id_reloj, Agente.id != a.id)).first():
        raise HTTPException(status.HTTP_409_CONFLICT, "Ese ID ya pertenece a otra persona.")
    a.id_reloj = entrada.id_reloj
    a.revision += 1
    audit.registrar(db, ctx, "identidad_reloj", "agente", a.id, None, {"id_reloj": entrada.id_reloj, "importacion": i.id})
    db.commit()
    return _importacion_out(db, i)


@router.post("/personal/reloj/{importacion_id}/incorporar")
def incorporar(importacion_id: int, ctx: Contexto = Depends(contexto), db: Session = Depends(get_db)):
    _requerir_admin(ctx)
    i = db.get(RelojImportacion, importacion_id)
    if i is None:
        raise no_encontrado("Importación")
    if i.incorporada:
        raise HTTPException(status.HTTP_409_CONFLICT, "Este archivo ya fue incorporado; no se duplicaron marcaciones.")
    vista = _importacion_out(db, i)
    if i.errores or vista["sin_identificar"]:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Resolvé errores e identificaciones antes de incorporar la semana.")
    leido = _leer_archivo(i)
    if leido["errores"] != i.errores or len(leido["registros"]) != i.filas:
        raise HTTPException(status.HTTP_409_CONFLICT, "La previsualización no coincide con el archivo original.")
    por_id = {a.id_reloj: a for a in db.execute(select(Agente).where(Agente.id_reloj.is_not(None))).scalars()}
    for r in leido["registros"]:
        a = por_id[r["id_reloj"]]
        if not coincide_nombre(a.nombre, r["nombre"]):
            raise HTTPException(status.HTTP_400_BAD_REQUEST, f"ID {r['id_reloj']}: el nombre {r['nombre']} no coincide con {a.nombre}. Revisá su identidad.")
        db.add(Marcacion(importacion_id=i.id, agente_id=a.id, dia=date.fromisoformat(r["dia"]), entrada=r["entrada"], salida=r["salida"], fila=r["fila"]))
    i.incorporada = True
    audit.registrar(db, ctx, "semana_incorporada", "reloj", i.id, None, {"sha256": i.sha256, "filas": i.filas})
    db.commit()
    return {"incorporadas": i.filas}


@router.get("/personal/reloj/{importacion_id}/original")
def original(importacion_id: int, ctx: Contexto = Depends(contexto), db: Session = Depends(get_db)):
    _requerir_consulta(ctx)
    i = db.get(RelojImportacion, importacion_id)
    if i is None:
        raise no_encontrado("Importación")
    with almacenamiento_por_nombre(i.almacenamiento).abrir(i.clave) as f:
        datos = f.read()
    if hashlib.sha256(datos).hexdigest() != i.sha256:
        raise HTTPException(status.HTTP_409_CONFLICT, "El archivo original fue modificado.")
    return StreamingResponse(
        io.BytesIO(datos), media_type="application/vnd.ms-excel",
        headers={"Content-Disposition": f"attachment; filename*=UTF-8''{quote(i.nombre_archivo)}", "Cache-Control": "no-store"},
    )


# ---------------------------------------------------------------- informe y revisiones


def _datos_motor(db: Session, desde: date, hasta: date, agente_id: int | None) -> dict:
    agentes = db.execute(select(Agente).where(Agente.id == agente_id) if agente_id else select(Agente)).scalars().all()
    ids = [a.id for a in agentes]
    horarios: dict = {}
    for h in db.execute(select(Horario).where(Horario.agente_id.in_(ids))).scalars():
        horarios.setdefault(h.agente_id, []).append(
            {"vigente_desde": h.vigente_desde.isoformat(), "vigente_hasta": h.vigente_hasta.isoformat() if h.vigente_hasta else None, "semana": h.semana, "confirmado": h.confirmado}
        )
    return {
        "agentes": [{"id": a.id, "nombre": a.nombre, "id_reloj": a.id_reloj, "boleta": a.boleta, "periodos": a.periodos, "horarios": horarios.get(a.id, [])} for a in agentes],
        "marcaciones": [
            {"agente_id": m.agente_id, "dia": m.dia.isoformat(), "entrada": m.entrada, "salida": m.salida, "importacion_id": m.importacion_id}
            for m in db.execute(select(Marcacion).where(Marcacion.agente_id.in_(ids), Marcacion.dia >= desde, Marcacion.dia <= hasta)).scalars()
        ],
        "justificativos": [
            {"id": j.id, "agente_id": j.agente_id, "codigo": j.codigo, "estado": j.estado, "desde": j.desde.isoformat(), "hasta": j.hasta.isoformat(),
             "hora_desde": j.hora_desde, "hora_hasta": j.hora_hasta, "excepcion_desde": j.excepcion_desde, "excepcion_hasta": j.excepcion_hasta,
             "requiere_horario": j.requiere_horario}
            for j in db.execute(select(Justificativo).where(Justificativo.agente_id.in_(ids), Justificativo.desde <= hasta, Justificativo.hasta >= desde)).scalars()
        ],
        "importaciones": [
            {"id": i.id, "desde": i.desde.isoformat(), "hasta": i.hasta.isoformat(), "incorporada": i.incorporada}
            for i in db.execute(select(RelojImportacion)).scalars()
        ],
        "revisiones": [
            {"id": r.id, "agente_id": r.agente_id, "dia": r.dia.isoformat(), "huella": r.huella, "decision": r.decision, "minutos": r.minutos,
             "fundamento": r.fundamento, "usuario": r.usuario.nombre_completo if r.usuario else None, "en": r.en.isoformat()}
            for r in db.execute(select(RevisionJornada).where(RevisionJornada.agente_id.in_(ids), RevisionJornada.dia >= desde, RevisionJornada.dia <= hasta)).scalars()
        ],
    }


def _informe(db: Session, desde: date, hasta: date, agente_id: int | None) -> list[dict]:
    try:
        return informe(_datos_motor(db, desde, hasta, agente_id), desde.isoformat(), hasta.isoformat(), agente_id)
    except ErrorAsistencia as e:
        raise _error(e)


@router.get("/personal/informe")
def ver_informe(
    desde: date,
    hasta: date,
    agente_id: int | None = None,
    estado: str | None = Query(None, pattern="^(pendiente|revisado|justificado|auto_aprobado|sin_datos)$"),
    ctx: Contexto = Depends(contexto),
    db: Session = Depends(get_db),
):
    propio = _mi_agente(db, ctx)
    if not _puede_consultar(ctx):
        if propio is None or (agente_id is not None and agente_id != propio.id):
            raise HTTPException(status.HTTP_403_FORBIDDEN, "Solo puede ver sus propias jornadas.")
        agente_id = propio.id
    filas = _informe(db, desde, hasta, agente_id)
    return [f for f in filas if not estado or f["estado"] == estado]


class RevisionIn(Entrada):
    agente_id: int
    dia: date
    decision: str
    minutos: int = 0
    fundamento: str = Field(max_length=2000)
    huella: str = Field(max_length=64)
    revision_vista: int | None = None


@router.post("/personal/revisiones", status_code=201)
def revisar(entrada: RevisionIn, ctx: Contexto = Depends(contexto), db: Session = Depends(get_db)):
    _requerir_admin(ctx)
    filas = _informe(db, entrada.dia, entrada.dia, entrada.agente_id)
    try:
        validar_revision(filas[0] if filas else None, entrada.decision, entrada.minutos, entrada.fundamento, entrada.huella, entrada.revision_vista)
    except ErrorAsistencia as e:
        raise HTTPException(status.HTTP_409_CONFLICT, str(e))
    r = RevisionJornada(agente_id=entrada.agente_id, dia=entrada.dia, huella=entrada.huella, decision=entrada.decision,
                        minutos=entrada.minutos, fundamento=entrada.fundamento.strip(), usuario_id=ctx.id)
    db.add(r)
    db.flush()
    audit.registrar(db, ctx, "jornada_revisada", "agente", entrada.agente_id, None,
                    {"dia": entrada.dia, "decision": entrada.decision, "minutos": entrada.minutos, "fundamento": r.fundamento})
    db.commit()
    return {"ok": True, "id": r.id}


# ---------------------------------------------------------------- justificativos


class JustificativoIn(Entrada):
    agente_id: int
    codigo: str
    desde: date
    hasta: date | None = None
    hora_desde: str | None = None
    hora_hasta: str | None = None
    excepcion_desde: str | None = None
    excepcion_hasta: str | None = None
    referencia: str | None = Field(default=None, max_length=1000)
    notas: str | None = Field(default=None, max_length=5000)


def _validar_justificativo(e: JustificativoIn) -> dict:
    if e.codigo not in CODIGOS:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Código de justificativo no reconocido.")
    hasta = e.hasta or e.desde
    if hasta < e.desde or (hasta - e.desde).days > 366:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Revisá el período; máximo 367 días.")
    try:
        hd, hh = tramo(e.hora_desde, e.hora_hasta, False)
        ed, eh = tramo(e.excepcion_desde, e.excepcion_hasta, False)
    except ErrorAsistencia as x:
        raise _error(x)
    if e.codigo != "CAMBIO" and ed:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "El turno excepcional corresponde al código CAMBIO.")
    return {"codigo": e.codigo, "desde": e.desde, "hasta": hasta, "hora_desde": hd, "hora_hasta": hh, "excepcion_desde": ed, "excepcion_hasta": eh}


def _crear_justificativo(db: Session, ctx: Contexto, agente: Agente, v: dict, referencia, notas, solicitud_id=None, fundamento=None) -> Justificativo:
    requiere = v["codigo"] == "CAMBIO" and not v["excepcion_desde"]
    j = Justificativo(
        agente_id=agente.id, **v, referencia=(referencia or "").strip() or None, notas=(notas or "").strip() or None,
        estado="pendiente" if requiere else "aprobado", requiere_horario=requiere, adjuntos=[], solicitud_id=solicitud_id,
        fundamento=fundamento or ("Falta indicar el nuevo horario." if requiere else "Registrado por Personal. Se aplica según fechas y tramos."),
        usuario_id=ctx.id,
    )
    db.add(j)
    db.flush()
    audit.registrar(db, ctx, "justificativo_cargado", "justificativo", j.id, None,
                    {"agente": agente.nombre, "codigo": j.codigo, "desde": j.desde, "hasta": j.hasta, "solicitud": solicitud_id})
    return j


@router.get("/personal/justificativos")
def listar_justificativos(agente_id: int | None = None, ctx: Contexto = Depends(contexto), db: Session = Depends(get_db)):
    _requerir_consulta(ctx)
    q = select(Justificativo).order_by(Justificativo.en.desc()).limit(500)
    if agente_id:
        q = q.where(Justificativo.agente_id == agente_id)
    return [_justificativo_out(j) for j in db.execute(q).scalars()]


@router.post("/personal/justificativos", status_code=201)
def cargar_justificativo(entrada: JustificativoIn, ctx: Contexto = Depends(contexto), db: Session = Depends(get_db)):
    _requerir_admin(ctx)
    a = _agente(db, entrada.agente_id)
    j = _crear_justificativo(db, ctx, a, _validar_justificativo(entrada), entrada.referencia, entrada.notas)
    db.commit()
    db.refresh(j)
    return _justificativo_out(j)


class DecisionJustIn(Entrada):
    estado: str
    fundamento: str = Field(min_length=5, max_length=2000)
    revision_vista: int


@router.post("/personal/justificativos/{jid}/decision")
def decidir_justificativo(jid: int, entrada: DecisionJustIn, ctx: Contexto = Depends(contexto), db: Session = Depends(get_db)):
    _requerir_admin(ctx)
    j = _obtener(db, Justificativo, jid, "Justificativo")
    if entrada.estado not in ("aprobado", "rechazado"):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Decisión no válida.")
    if entrada.estado == "aprobado" and j.requiere_horario:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Completá el nuevo horario antes de aplicar este cambio.")
    if j.revision != entrada.revision_vista:
        raise HTTPException(status.HTTP_409_CONFLICT, "El justificativo cambió. Actualizá y revisá su estado actual.")
    antes = j.estado
    j.estado, j.fundamento, j.usuario_id = entrada.estado, entrada.fundamento.strip(), ctx.id
    j.revision += 1
    audit.registrar(db, ctx, "justificativo_revisado", "justificativo", j.id, None, {"antes": antes, "despues": j.estado, "fundamento": j.fundamento})
    db.commit()
    db.refresh(j)
    return _justificativo_out(j)


class CompletarHorarioIn(Entrada):
    excepcion_desde: str
    excepcion_hasta: str
    revision_vista: int


@router.post("/personal/justificativos/{jid}/completar-horario")
def completar_horario(jid: int, entrada: CompletarHorarioIn, ctx: Contexto = Depends(contexto), db: Session = Depends(get_db)):
    _requerir_admin(ctx)
    j = _obtener(db, Justificativo, jid, "Justificativo")
    if j.codigo != "CAMBIO" or not j.requiere_horario or j.estado != "pendiente":
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Este justificativo no tiene un cambio horario pendiente de completar.")
    if j.revision != entrada.revision_vista:
        raise HTTPException(status.HTTP_409_CONFLICT, "El justificativo cambió. Actualizá antes de completarlo.")
    try:
        ed, eh = tramo(entrada.excepcion_desde, entrada.excepcion_hasta, True)
    except ErrorAsistencia as e:
        raise _error(e)
    j.excepcion_desde, j.excepcion_hasta, j.estado, j.requiere_horario = ed, eh, "aprobado", False
    j.fundamento, j.usuario_id = "Nuevo horario completado por Personal.", ctx.id
    j.revision += 1
    audit.registrar(db, ctx, "cambio_horario_completado", "justificativo", j.id, None, {"desde": ed, "hasta": eh})
    db.commit()
    db.refresh(j)
    return _justificativo_out(j)


def _guardar_adjunto(archivo: UploadFile) -> dict:
    cabecera = archivo.file.read(16)
    archivo.file.seek(0)
    mime = detectar_mime(cabecera)
    if mime not in ("application/pdf", "image/jpeg", "image/png"):
        raise HTTPException(status.HTTP_415_UNSUPPORTED_MEDIA_TYPE, "Adjuntá un PDF, JPG o PNG.")
    datos = archivo.file.read(MAX_ADJUNTO + 1)
    if len(datos) > MAX_ADJUNTO:
        raise HTTPException(status.HTTP_413_REQUEST_ENTITY_TOO_LARGE, "El adjunto supera los 10 MB.")
    almacen = almacenamiento_actual()
    g = almacen.guardar(io.BytesIO(datos))
    return {"id": uuid.uuid4().hex[:12], "nombre": (archivo.filename or "adjunto")[:200], "sha256": g.sha256, "mime": mime,
            "almacenamiento": almacen.nombre, "clave": g.clave}


def _servir(x: dict):
    almacen = almacenamiento_por_nombre(x["almacenamiento"])
    with almacen.abrir(x["clave"]) as f:
        datos = f.read()
    if hashlib.sha256(datos).hexdigest() != x["sha256"]:
        raise HTTPException(status.HTTP_409_CONFLICT, "El adjunto no coincide con su huella de integridad.")
    return StreamingResponse(io.BytesIO(datos), media_type=x["mime"],
                             headers={"Content-Disposition": f"inline; filename*=UTF-8''{quote(x['nombre'])}", "Cache-Control": "no-store", "X-Content-Type-Options": "nosniff"})


@router.post("/personal/justificativos/{jid}/adjuntos", status_code=201)
def adjuntar_justificativo(jid: int, archivo: UploadFile = File(...), ctx: Contexto = Depends(contexto), db: Session = Depends(get_db)):
    _requerir_admin(ctx)
    j = _obtener(db, Justificativo, jid, "Justificativo")
    x = _guardar_adjunto(archivo)
    j.adjuntos = [*(j.adjuntos or []), x]
    j.revision += 1
    audit.registrar(db, ctx, "adjunto_cargado", "justificativo", j.id, None, {"nombre": x["nombre"], "sha256": x["sha256"]})
    db.commit()
    return {"id": x["id"]}


@router.get("/personal/justificativos/{jid}/adjuntos/{aid}")
def ver_adjunto_justificativo(jid: int, aid: str, ctx: Contexto = Depends(contexto), db: Session = Depends(get_db)):
    _requerir_consulta(ctx)
    j = _obtener(db, Justificativo, jid, "Justificativo")
    x = next((x for x in j.adjuntos or [] if x["id"] == aid), None)
    if x is None:
        raise no_encontrado("Adjunto")
    audit.registrar(db, ctx, "adjunto_descargado", "justificativo", j.id, None, {"nombre": x["nombre"]})
    db.commit()
    return _servir(x)


# ---------------------------------------------------------------- solicitudes


@router.get("/personal/mio")
def mi_asistencia(ctx: Contexto = Depends(contexto), db: Session = Depends(get_db)):
    a = _mi_agente(db, ctx)
    solicitudes = []
    if a is not None:
        solicitudes = [
            _solicitud_out(ctx, s)
            for s in db.execute(select(SolicitudPersonal).where(SolicitudPersonal.agente_id == a.id).order_by(SolicitudPersonal.pedido_en.desc()).limit(50)).scalars()
        ]
    return {"agente": _agente_out(db, a) if a else None, "solicitudes": solicitudes}


@router.post("/personal/solicitudes", status_code=201)
def solicitar(
    tipo: str = Form(...),
    desde: date = Form(...),
    hasta: date | None = Form(None),
    clase: str | None = Form(None),
    hora_desde: str | None = Form(None),
    hora_hasta: str | None = Form(None),
    nueva_entrada: str | None = Form(None),
    nueva_salida: str | None = Form(None),
    lugar: str | None = Form(None, max_length=300),
    motivo: str | None = Form(None, max_length=3000),
    agente_id: int | None = Form(None),
    archivo: UploadFile | None = File(None),
    ctx: Contexto = Depends(contexto),
    db: Session = Depends(get_db),
):
    if agente_id is not None and not ctx.tiene("personal", "administrar"):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Solo Personal carga pedidos en nombre de otra persona.")
    a = _agente(db, agente_id) if agente_id is not None else _mi_agente(db, ctx)
    if a is None:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Su usuario no está vinculado a una ficha de personal. Pídalo a Personal.")
    if tipo not in TIPOS_SOLICITUD:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Tipo de pedido inválido.")
    hasta = hasta or desde
    if hasta < desde or (hasta - desde).days > 366:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Revisá las fechas.")
    vacio = lambda x: (x or "").strip() or None  # noqa: E731
    clase, lugar, motivo = vacio(clase), vacio(lugar), vacio(motivo)
    try:
        hd, hh = tramo(vacio(hora_desde), vacio(hora_hasta), False)
        ne, ns = tramo(vacio(nueva_entrada), vacio(nueva_salida), tipo == "cambio_horario")
    except ErrorAsistencia as e:
        raise _error(e)
    if tipo == "licencia" and clase not in CLASES_LICENCIA:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Elegí el tipo de licencia.")
    if tipo == "comision" and not lugar:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Indicá adónde es la comisión.")
    if tipo != "licencia":
        clase = None
    s = SolicitudPersonal(
        agente_id=a.id, tipo=tipo, clase=clase, desde=desde, hasta=hasta, hora_desde=hd, hora_hasta=hh,
        nueva_entrada=ne if tipo == "cambio_horario" else None, nueva_salida=ns if tipo == "cambio_horario" else None,
        lugar=lugar if tipo == "comision" else None, motivo=motivo, adjuntos=[], pedido_por=ctx.id,
    )
    if archivo is not None and archivo.filename:
        s.adjuntos = [_guardar_adjunto(archivo)]
    db.add(s)
    db.flush()
    audit.registrar(db, ctx, "solicitud_personal", "solicitud", s.id, None, {"agente": a.nombre, "tipo": tipo, "desde": desde, "hasta": hasta})
    db.commit()
    db.refresh(s)
    return _solicitud_out(ctx, s)


@router.get("/personal/solicitudes")
def listar_solicitudes(
    vista: str = Query("para_aprobar", pattern="^(para_aprobar|para_registrar|todas)$"),
    ctx: Contexto = Depends(contexto),
    db: Session = Depends(get_db),
):
    if vista == "para_aprobar":
        if not ctx.tiene("personal", "aprobar"):
            return []
        q = select(SolicitudPersonal).where(SolicitudPersonal.estado == "pendiente").order_by(SolicitudPersonal.desde)
        return [_solicitud_out(ctx, s) for s in db.execute(q).scalars() if _puede_aprobar(ctx, s)]
    _requerir_consulta(ctx)
    q = select(SolicitudPersonal).order_by(SolicitudPersonal.pedido_en.desc()).limit(300)
    if vista == "para_registrar":
        q = select(SolicitudPersonal).where(SolicitudPersonal.estado == "aprobada").order_by(SolicitudPersonal.desde)
    return [_solicitud_out(ctx, s) for s in db.execute(q).scalars()]


def _solicitud(db: Session, sid: int) -> SolicitudPersonal:
    s = db.get(SolicitudPersonal, sid)
    if s is None:
        raise no_encontrado("Pedido")
    return s


class DecisionIn(Entrada):
    aprobar: bool
    respuesta: str | None = Field(default=None, max_length=1000)


@router.post("/personal/solicitudes/{sid}/decidir")
def decidir(sid: int, entrada: DecisionIn, ctx: Contexto = Depends(contexto), db: Session = Depends(get_db)):
    s = _solicitud(db, sid)
    if s.estado != "pendiente":
        raise HTTPException(status.HTTP_409_CONFLICT, "Ese pedido ya se resolvió.")
    if not _puede_aprobar(ctx, s):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Lo aprueba la jefatura del área de la persona (o la Dirección).")
    if not entrada.aprobar and not (entrada.respuesta or "").strip():
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Indicá el motivo del rechazo.")
    s.estado = "aprobada" if entrada.aprobar else "rechazada"
    s.decidido_por, s.decidido_en = ctx.id, ahora()
    s.respuesta = (entrada.respuesta or "").strip() or None
    audit.registrar(db, ctx, "solicitud_aprobada" if entrada.aprobar else "solicitud_rechazada", "solicitud", s.id, None, {"agente": s.agente.nombre, "respuesta": s.respuesta})
    db.commit()
    db.refresh(s)
    return _solicitud_out(ctx, s)


@router.post("/personal/solicitudes/{sid}/cancelar")
def cancelar(sid: int, ctx: Contexto = Depends(contexto), db: Session = Depends(get_db)):
    s = _solicitud(db, sid)
    if s.estado != "pendiente" or not (s.pedido_por == ctx.id or s.agente.usuario_id == ctx.id):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Solo quien pidió puede cancelar un pedido pendiente.")
    s.estado = "cancelada"
    audit.registrar(db, ctx, "solicitud_cancelada", "solicitud", s.id, None)
    db.commit()
    db.refresh(s)
    return _solicitud_out(ctx, s)


class RegistrarIn(Entrada):
    codigo: str
    referencia: str | None = Field(default=None, max_length=1000)


@router.post("/personal/solicitudes/{sid}/registrar")
def registrar(sid: int, entrada: RegistrarIn, ctx: Contexto = Depends(contexto), db: Session = Depends(get_db)):
    """Personal toma conocimiento y lo carga como justificativo."""
    _requerir_admin(ctx)
    s = _solicitud(db, sid)
    if s.estado != "aprobada":
        raise HTTPException(status.HTTP_409_CONFLICT, "Solo se registran pedidos aprobados.")
    codigo = "CAMBIO" if s.tipo == "cambio_horario" else entrada.codigo
    if s.tipo != "cambio_horario" and codigo == "CAMBIO":
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "CAMBIO corresponde a los cambios de horario.")
    v = _validar_justificativo(
        JustificativoIn(agente_id=s.agente_id, codigo=codigo, desde=s.desde, hasta=s.hasta, hora_desde=s.hora_desde, hora_hasta=s.hora_hasta,
                        excepcion_desde=s.nueva_entrada, excepcion_hasta=s.nueva_salida)
    )
    decisor = s.decisor.nombre_completo if s.decisor else "la jefatura"
    j = _crear_justificativo(
        db, ctx, s.agente, v, entrada.referencia or f"Pedido N° {s.id} ({TIPOS_SOLICITUD[s.tipo]})", s.lugar,
        solicitud_id=s.id, fundamento=f"Pedido aprobado por {decisor} el {s.decidido_en:%d/%m/%Y}.",
    )
    j.adjuntos = list(s.adjuntos or [])
    s.estado, s.registrado_por, s.registrado_en = "registrada", ctx.id, ahora()
    audit.registrar(db, ctx, "solicitud_registrada", "solicitud", s.id, None, {"justificativo": j.id, "codigo": codigo})
    db.commit()
    db.refresh(s)
    return _solicitud_out(ctx, s)


@router.get("/personal/solicitudes/{sid}/adjuntos/{aid}")
def ver_adjunto_solicitud(sid: int, aid: str, ctx: Contexto = Depends(contexto), db: Session = Depends(get_db)):
    s = _solicitud(db, sid)
    involucrado = s.agente.usuario_id == ctx.id or s.pedido_por == ctx.id or _puede_consultar(ctx) or _puede_aprobar(ctx, s)
    if not involucrado or not _ve_detalle_sensible(ctx, s):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "No puede ver este adjunto.")
    x = next((x for x in s.adjuntos or [] if x["id"] == aid), None)
    if x is None:
        raise no_encontrado("Adjunto")
    return _servir(x)


# ---------------------------------------------------------------- quién está hoy


def estado_hoy(db: Session, dia: date | None = None) -> dict[str, dict]:
    """{usuario_id: {"estado", "texto", "hasta"}} de quienes no están disponibles hoy.
    No incluye motivos: sólo licencia, comisión o ausencia justificada."""
    d = dia or _hoy()
    salida: dict[str, dict] = {}
    for s in db.execute(
        select(SolicitudPersonal).where(
            SolicitudPersonal.estado.in_(("aprobada", "registrada")), SolicitudPersonal.tipo.in_(("licencia", "comision")),
            SolicitudPersonal.desde <= d, SolicitudPersonal.hasta >= d, SolicitudPersonal.hora_desde.is_(None),
        )
    ).scalars():
        if s.agente.usuario_id:
            salida[str(s.agente.usuario_id)] = {
                "estado": s.tipo, "texto": "De licencia" if s.tipo == "licencia" else "En comisión", "hasta": s.hasta.isoformat(),
            }
    for j in db.execute(
        select(Justificativo).where(
            Justificativo.estado == "aprobado", Justificativo.codigo != "CAMBIO", Justificativo.desde <= d, Justificativo.hasta >= d,
            Justificativo.hora_desde.is_(None), Justificativo.solicitud_id.is_(None),
        )
    ).scalars():
        if j.agente.usuario_id and str(j.agente.usuario_id) not in salida:
            salida[str(j.agente.usuario_id)] = {"estado": "ausente", "texto": "Ausente con justificativo", "hasta": j.hasta.isoformat()}
    return salida


@router.get("/personal/hoy")
def hoy(ctx: Contexto = Depends(contexto), db: Session = Depends(get_db)):
    return estado_hoy(db)


@router.get("/personal/pendientes")
def pendientes(ctx: Contexto = Depends(contexto), db: Session = Depends(get_db)):
    para_aprobar = 0
    if ctx.tiene("personal", "aprobar"):
        para_aprobar = sum(
            1 for s in db.execute(select(SolicitudPersonal).where(SolicitudPersonal.estado == "pendiente")).scalars() if _puede_aprobar(ctx, s)
        )
    para_registrar = 0
    if ctx.tiene("personal", "administrar"):
        para_registrar = db.execute(select(func.count(SolicitudPersonal.id)).where(SolicitudPersonal.estado == "aprobada")).scalar_one()
    return {"para_aprobar": para_aprobar, "para_registrar": para_registrar, "cantidad": para_aprobar + para_registrar}

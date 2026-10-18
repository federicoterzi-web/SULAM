"""Agenda: salidas, visitas y actividades con fecha, participantes y resultado.

- Cada persona ve la suya (en las que participa o que cargó) y, con alcance «área», la de su área.
- Una actividad puede estar ligada a un legajo y a un caso; al registrar el resultado de una salida o visita,
  queda anotado también en la evolución del caso.
- Es interna: no se comparte con otras instituciones.
"""

from __future__ import annotations

import calendar
import uuid
from datetime import date, datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import Field, model_validator
from sqlalchemy import and_, exists, func, or_, select, true
from sqlalchemy.orm import Session

from .. import audit
from ..db import get_db
from ..deps import contexto
from ..models import Agente, Area, CambioAgenda, Caso, CasoEvolucion, Documento, EventoAgenda, ParticipanteAgenda, Persona, SolicitudPersonal, Usuario
from ..permissions import Contexto, filtro_personas, requerir_caso, requerir_persona
from ..schemas import Entrada
from ..security import ahora
from ._comun import no_encontrado, obtener_caso, obtener_persona, registrar_actividad_caso

router = APIRouter(tags=["agenda"])

TIPOS = {
    "salida": "Salida",
    "visita": "Visita domiciliaria",
    "entrevista": "Entrevista",
    "reunion": "Reunión",
    "audiencia": "Audiencia",
    "tramite": "Trámite",
    "recordatorio": "Recordatorio",
    "otro": "Otro",
    "evento": "Evento de Participación",  # solo se crea desde Participación y Sensibilización
}
TIPO_EVENTO = "evento"
ESTADOS_FINALES = {"realizado": "realizada", "no_realizado": "no realizada", "cancelado": "cancelada"}
MAX_RANGO = 500
FRECUENCIAS = {"diaria": "Todos los días hábiles", "semanal": "Todas las semanas", "quincenal": "Cada 15 días", "mensual": "Todos los meses"}
MAX_REPETICIONES = 52
CAMPOS_HISTORIAL = {"tipo": "Clase", "titulo": "Título", "inicio": "Día y hora", "fin": "Fin", "lugar": "Lugar", "descripcion": "Descripción", "todo_el_dia": "Todo el día"}


# ---------------------------------------------------------------- permisos

def _condicion_mio(ctx: Contexto):
    return or_(
        EventoAgenda.creado_por == ctx.id,
        EventoAgenda.id.in_(select(ParticipanteAgenda.evento_id).where(ParticipanteAgenda.usuario_id == ctx.id)),
    )


def _condicion_alcance(ctx: Contexto, alcance: str):
    if alcance == "todos":
        return true()
    if alcance in ("area", "asignados") and ctx.usuario.area_id is not None:
        return or_(_condicion_mio(ctx), EventoAgenda.area_id == ctx.usuario.area_id)
    return _condicion_mio(ctx)


def _en_alcance(db: Session, ctx: Contexto, e: EventoAgenda, alcance: str) -> bool:
    if alcance == "todos":
        return True
    if e.creado_por == ctx.id or any(p.usuario_id == ctx.id for p in e.participantes):
        return True
    return alcance in ("area", "asignados") and ctx.usuario.area_id is not None and e.area_id == ctx.usuario.area_id


def _puede_modificar(db: Session, ctx: Contexto, e: EventoAgenda) -> bool:
    alc = ctx.alcance("agenda", "modificar")
    return alc is not None and _en_alcance(db, ctx, e, alc)


def _evento(db: Session, ctx: Contexto, evento_id: uuid.UUID, accion: str = "consultar") -> EventoAgenda:
    e = db.get(EventoAgenda, evento_id)
    if e is None:
        raise no_encontrado("Actividad")
    alc = ctx.requerir("agenda", accion)
    if not _en_alcance(db, ctx, e, alc):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "La actividad está fuera de su alcance.")
    return e


# ---------------------------------------------------------------- salida

def _historial(db: Session, e: EventoAgenda) -> list[dict]:
    filas = db.execute(select(CambioAgenda).where(CambioAgenda.evento_id == e.id).order_by(CambioAgenda.en.desc())).scalars()
    return [
        {
            "en": c.en.isoformat(),
            "por": c.usuario.nombre_completo,
            "motivo": c.motivo,
            "cambios": [{"campo": campo, "texto": CAMPOS_HISTORIAL.get(campo, campo.replace("_", " ").capitalize()), "antes": v[0], "despues": v[1]} for campo, v in c.cambios.items()],
        }
        for c in filas
    ]


def _salida(db: Session, ctx: Contexto, e: EventoAgenda, detalle: bool = False) -> dict:
    persona = None
    if e.persona_id:
        p = db.get(Persona, e.persona_id)
        try:
            requerir_persona(db, ctx, p, "personas", "consultar")
            persona = {"id": str(p.id), "nombre": f"{p.apellidos}, {p.nombres}", "legajo": p.numero_legajo}
        except HTTPException:
            persona = {"id": None, "nombre": "Legajo reservado", "legajo": None}
    caso = None
    if e.caso_id and persona and persona["id"]:
        c = db.get(Caso, e.caso_id)
        caso = {"id": str(c.id), "numero": c.numero}
    resolvio = db.get(Usuario, e.resuelto_por) if e.resuelto_por else None
    creador = db.get(Usuario, e.creado_por)
    salida = {
        "id": str(e.id),
        "tipo": e.tipo,
        "tipo_texto": TIPOS.get(e.tipo, e.tipo),
        "titulo": e.titulo,
        "descripcion": e.descripcion,
        "inicio": e.inicio.isoformat(),
        "fin": e.fin.isoformat() if e.fin else None,
        "todo_el_dia": e.todo_el_dia,
        "lugar": e.lugar,
        "area": {"id": e.area.id, "nombre": e.area.nombre} if e.area else None,
        "persona": persona,
        "caso": caso,
        "estado": e.estado,
        "resultado": e.resultado,
        "resuelto_por": resolvio.nombre_completo if resolvio else None,
        "resuelto_en": e.resuelto_en.isoformat() if e.resuelto_en else None,
        "participantes": [{"id": str(p.usuario_id), "nombre": p.usuario.nombre_completo} for p in e.participantes],
        "creado_por": creador.nombre_completo if creador else None,
        "soy_participante": any(p.usuario_id == ctx.id for p in e.participantes),
        "puedo_modificar": _puede_modificar(db, ctx, e),
        "serie_id": str(e.serie_id) if e.serie_id else None,
        "repeticion": e.repeticion,
        "repeticion_texto": FRECUENCIAS.get(e.repeticion or ""),
    }
    if detalle:
        salida["historial"] = _historial(db, e)
        if e.serie_id:
            salida["en_la_serie"] = {
                "total": db.scalar(select(func.count()).select_from(EventoAgenda).where(EventoAgenda.serie_id == e.serie_id)),
                "siguientes": db.scalar(
                    select(func.count()).select_from(EventoAgenda).where(
                        EventoAgenda.serie_id == e.serie_id, EventoAgenda.inicio > e.inicio, EventoAgenda.estado == "programado"
                    )
                ),
            }
    return salida


# ---------------------------------------------------------------- entrada

class Repeticion(Entrada):
    frecuencia: str
    hasta: date | None = None
    cantidad: int | None = Field(default=None, ge=2, le=MAX_REPETICIONES)

    @model_validator(mode="after")
    def _valida(self):
        if self.frecuencia not in FRECUENCIAS:
            raise ValueError("Frecuencia inválida.")
        if self.hasta is None and self.cantidad is None:
            raise ValueError("Indique hasta cuándo se repite o cuántas veces.")
        return self


class EventoIn(Entrada):
    tipo: str
    titulo: str = Field(min_length=2, max_length=200)
    descripcion: str | None = Field(default=None, max_length=5000)
    inicio: datetime
    fin: datetime | None = None
    todo_el_dia: bool = False
    lugar: str | None = Field(default=None, max_length=300)
    area_id: int | None = None
    persona_id: uuid.UUID | None = None
    caso_id: uuid.UUID | None = None
    participantes: list[uuid.UUID] | None = None
    repetir: "Repeticion | None" = None

    @model_validator(mode="after")
    def _coherencia(self):
        if self.tipo not in TIPOS:
            raise ValueError("Tipo de actividad inválido.")
        if self.fin is not None and self.fin < self.inicio:
            raise ValueError("El fin es anterior al inicio.")
        return self


class EventoPatch(Entrada):
    tipo: str | None = None
    titulo: str | None = Field(default=None, min_length=2, max_length=200)
    descripcion: str | None = Field(default=None, max_length=5000)
    inicio: datetime | None = None
    fin: datetime | None = None
    todo_el_dia: bool | None = None
    lugar: str | None = Field(default=None, max_length=300)
    persona_id: uuid.UUID | None = None
    caso_id: uuid.UUID | None = None
    participantes: list[uuid.UUID] | None = None
    aplicar_a: str = Field(default="esta", pattern="^(esta|siguientes)$")
    motivo: str | None = Field(default=None, max_length=1000)


class ResultadoIn(Entrada):
    estado: str
    resultado: str | None = Field(default=None, max_length=5000)
    aplicar_a: str = Field(default="esta", pattern="^(esta|siguientes)$")

    @model_validator(mode="after")
    def _estado(self):
        if self.estado not in ESTADOS_FINALES:
            raise ValueError("Estado inválido.")
        return self


def _validar_vinculo(db: Session, ctx: Contexto, persona_id, caso_id):
    persona = caso = None
    if caso_id is not None:
        caso = obtener_caso(db, caso_id)
        if persona_id is not None and caso.persona_id != persona_id:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, "El caso no pertenece a ese legajo.")
        persona_id = caso.persona_id
        requerir_caso(db, ctx, caso, "casos", "consultar")
    if persona_id is not None:
        persona = obtener_persona(db, persona_id)
        requerir_persona(db, ctx, persona, "personas", "consultar")
    return persona, caso


def _validar_participantes(db: Session, ctx: Contexto, ids: list[uuid.UUID] | None) -> list[Usuario]:
    ids = list(dict.fromkeys(ids)) if ids else [ctx.id]
    usuarios = db.execute(select(Usuario).where(Usuario.id.in_(ids), Usuario.activo.is_(True))).scalars().all()
    if len(usuarios) != len(ids):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Algún participante no existe o está dado de baja.")
    if ctx.alcance("agenda", "crear") != "todos":
        for u in usuarios:
            if u.id != ctx.id and u.area_id != ctx.usuario.area_id:
                raise HTTPException(status.HTTP_403_FORBIDDEN, "Solo puede agendar actividades para personas de su área.")
    return usuarios


# ---------------------------------------------------------------- rutas

@router.get("/agenda")
def listar(
    desde: datetime,
    hasta: datetime,
    ambito: str = Query("mio", pattern="^(mio|area|todos)$"),
    estado: str | None = None,
    usuario_id: uuid.UUID | None = None,
    ctx: Contexto = Depends(contexto),
    db: Session = Depends(get_db),
):
    """Actividades entre dos fechas. ``ambito``: las mías, las de mi área o todas (según el alcance de cada uno)."""
    alcance = ctx.requerir("agenda", "consultar")
    q = select(EventoAgenda).where(EventoAgenda.inicio >= desde, EventoAgenda.inicio < hasta)
    if ambito == "mio":
        q = q.where(_condicion_mio(ctx))
    elif ambito == "area":
        if alcance == "propios" or ctx.usuario.area_id is None:
            raise HTTPException(status.HTTP_403_FORBIDDEN, "No tiene acceso a la agenda del área.")
        q = q.where(EventoAgenda.area_id == ctx.usuario.area_id)
    else:
        if alcance != "todos":
            raise HTTPException(status.HTTP_403_FORBIDDEN, "No tiene acceso a toda la agenda.")
    if estado:
        q = q.where(EventoAgenda.estado == estado)
    if usuario_id is not None:
        q = q.where(
            or_(
                EventoAgenda.creado_por == usuario_id,
                EventoAgenda.id.in_(select(ParticipanteAgenda.evento_id).where(ParticipanteAgenda.usuario_id == usuario_id)),
            )
        )
    filas = db.execute(q.order_by(EventoAgenda.inicio).limit(MAX_RANGO)).scalars().all()
    return {"alcance": alcance, "eventos": [_salida(db, ctx, e) for e in filas]}


@router.get("/agenda/tipos")
def tipos(ctx: Contexto = Depends(contexto)):
    ctx.requerir("agenda", "consultar")
    return [{"clave": k, "texto": v} for k, v in TIPOS.items() if k != TIPO_EVENTO]


@router.get("/agenda/participantes")
def posibles_participantes(ctx: Contexto = Depends(contexto), db: Session = Depends(get_db)):
    """Personas con quienes se puede agendar: las de su área (o todas, con alcance «todos»)."""
    ctx.requerir("agenda", "crear")
    q = select(Usuario).where(Usuario.activo.is_(True)).order_by(Usuario.nombre_completo)
    if ctx.alcance("agenda", "crear") != "todos":
        q = q.where(Usuario.area_id == ctx.usuario.area_id) if ctx.usuario.area_id else q.where(Usuario.id == ctx.id)
    return [{"id": str(u.id), "nombre": u.nombre_completo, "area": u.area.nombre if u.area else None} for u in db.execute(q).scalars()]


def _fechas_de_la_serie(inicio: datetime, r: Repeticion) -> list[datetime]:
    """Las fechas de cada repetición (la primera es la propia actividad). Mantiene la hora."""
    tope = inicio + timedelta(days=366)
    limite = datetime.combine(r.hasta, inicio.timetz()) if r.hasta else tope
    limite = min(limite, tope)
    cantidad = r.cantidad or MAX_REPETICIONES
    salida = [inicio]
    k = 0
    actual = inicio
    while len(salida) < min(cantidad, MAX_REPETICIONES):
        k += 1
        if r.frecuencia == "semanal":
            actual = inicio + timedelta(weeks=k)
        elif r.frecuencia == "quincenal":
            actual = inicio + timedelta(weeks=2 * k)
        elif r.frecuencia == "mensual":
            mes = inicio.month - 1 + k
            anio, mes = inicio.year + mes // 12, mes % 12 + 1
            actual = inicio.replace(year=anio, month=mes, day=min(inicio.day, calendar.monthrange(anio, mes)[1]))
        else:  # diaria: solo días hábiles
            actual = actual + timedelta(days=1)
            while actual.weekday() >= 5:
                actual = actual + timedelta(days=1)
        if actual > limite:
            break
        salida.append(actual)
    return salida


def crear_actividades(db: Session, ctx: Contexto, datos: EventoIn) -> list[EventoAgenda]:
    """Crea la actividad (y sus repeticiones). No confirma la transacción: quien llama completa y confirma."""
    ctx.requerir("agenda", "crear")
    persona, caso = _validar_vinculo(db, ctx, datos.persona_id, datos.caso_id)
    participantes = _validar_participantes(db, ctx, datos.participantes)
    area_id = ctx.usuario.area_id
    if datos.area_id is not None and ctx.alcance("agenda", "crear") == "todos":
        if db.get(Area, datos.area_id) is None:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, "Área inexistente.")
        area_id = datos.area_id
    fechas = _fechas_de_la_serie(datos.inicio, datos.repetir) if datos.repetir else [datos.inicio]
    if datos.repetir and len(fechas) < 2:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Con esas fechas la actividad no se repite ninguna vez.")
    serie = uuid.uuid4() if datos.repetir else None
    duracion = (datos.fin - datos.inicio) if datos.fin else None
    creados: list[EventoAgenda] = []
    for f in fechas:
        e = EventoAgenda(
            tipo=datos.tipo, titulo=datos.titulo, descripcion=datos.descripcion, inicio=f, fin=(f + duracion) if duracion is not None else None,
            todo_el_dia=datos.todo_el_dia, lugar=datos.lugar, area_id=area_id,
            persona_id=persona.id if persona else None, caso_id=caso.id if caso else None, creado_por=ctx.id,
            serie_id=serie, repeticion=datos.repetir.frecuencia if datos.repetir else None,
        )
        e.participantes = [ParticipanteAgenda(usuario_id=u.id) for u in participantes]
        db.add(e)
        creados.append(e)
    db.flush()
    audit.registrar(
        db, ctx, "crear", "agenda", creados[0].id, creados[0].persona_id,
        {"tipo": datos.tipo, "inicio": creados[0].inicio.isoformat(), "participantes": len(participantes), "repeticiones": len(creados) if serie else None},
    )
    return creados


@router.post("/agenda", status_code=201)
def crear(datos: EventoIn, ctx: Contexto = Depends(contexto), db: Session = Depends(get_db)):
    if datos.tipo == TIPO_EVENTO:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Los eventos de Participación se cargan desde esa sección.")
    creados = crear_actividades(db, ctx, datos)
    db.commit()
    db.refresh(creados[0])
    salida = _salida(db, ctx, creados[0], detalle=True)
    salida["creadas"] = len(creados)
    return salida


@router.get("/agenda/superpuestos")
def superpuestos(
    desde: datetime,
    hasta: datetime,
    ambito: str = Query("mio", pattern="^(mio|area|todos)$"),
    usuario_id: uuid.UUID | None = None,
    ctx: Contexto = Depends(contexto),
    db: Session = Depends(get_db),
):
    """Datos de otros módulos para mirar junto con la agenda (solo lectura): vencimientos de documentos y
    ausencias del personal (licencias y comisiones aprobadas). Cada uno se ve solo si su rol lo permite."""
    alcance = ctx.requerir("agenda", "consultar")
    d0, d1 = desde.date(), hasta.date()
    if ambito == "area" and (alcance == "propios" or ctx.usuario.area_id is None):
        ambito = "mio"
    if ambito == "todos" and alcance != "todos":
        ambito = "area" if alcance != "propios" and ctx.usuario.area_id is not None else "mio"

    # Vencimientos de documentos de los legajos que puede ver.
    vencimientos: list[dict] = []
    alc_doc = ctx.alcance("documentos", "consultar")
    if alc_doc is not None and usuario_id is None:
        if ambito == "mio":
            alc_doc = "propios" if alc_doc == "propios" else "asignados"
        elif ambito == "area" and alc_doc == "todos":
            alc_doc = "area"
        D2 = Documento
        posterior = exists().where(
            and_(
                Documento.persona_id == D2.persona_id,
                Documento.tipo_documental_id == D2.tipo_documental_id,
                Documento.eliminado_en.is_(None),
                Documento.cargado_en > D2.cargado_en,
                Documento.id != D2.id,
            )
        )
        q = (
            select(Documento, Persona)
            .join(Persona, Persona.id == Documento.persona_id)
            .where(Documento.vence >= d0, Documento.vence < d1, Documento.eliminado_en.is_(None), ~posterior, filtro_personas(ctx, alc_doc))
            .order_by(Documento.vence)
            .limit(300)
        )
        for d, p in db.execute(q).all():
            vencimientos.append(
                {
                    "fecha": d.vence.isoformat(),
                    "documento_id": str(d.id),
                    "tipo": d.tipo_documental.nombre,
                    "persona": {"id": str(p.id), "nombre": f"{p.apellidos}, {p.nombres}"},
                }
            )

    # Ausencias del personal: licencias y comisiones aprobadas o ya registradas.
    q = (
        select(SolicitudPersonal)
        .join(Agente, Agente.id == SolicitudPersonal.agente_id)
        .where(
            SolicitudPersonal.tipo.in_(("licencia", "comision")),
            SolicitudPersonal.estado.in_(("aprobada", "registrada")),
            SolicitudPersonal.desde < d1,
            SolicitudPersonal.hasta >= d0,
        )
        .order_by(SolicitudPersonal.desde)
        .limit(300)
    )
    if usuario_id is not None:
        q = q.where(Agente.usuario_id == usuario_id)
    elif ambito == "mio":
        q = q.where(Agente.usuario_id == ctx.id)
    elif ambito == "area":
        q = q.where(Agente.area_id == ctx.usuario.area_id)
    ausencias = []
    for s in db.execute(q).scalars():
        reservado = s.clase == "enfermedad" and s.agente.usuario_id != ctx.id and ctx.alcance("personal", "consultar") != "todos" and not ctx.tiene("personal", "administrar")
        ausencias.append(
            {
                "desde": s.desde.isoformat(),
                "hasta": s.hasta.isoformat(),
                "agente": s.agente.nombre,
                "usuario_id": str(s.agente.usuario_id) if s.agente.usuario_id else None,
                "tipo_texto": "Ausente" if reservado else ("Comisión de servicio" if s.tipo == "comision" else "Licencia"),
                "lugar": s.lugar if s.tipo == "comision" else None,
                "horas": f"{s.hora_desde}–{s.hora_hasta}" if s.hora_desde and s.hora_hasta else None,
            }
        )
    return {"vencimientos": vencimientos, "ausencias": ausencias}


@router.get("/agenda/{evento_id}")
def ver(evento_id: uuid.UUID, ctx: Contexto = Depends(contexto), db: Session = Depends(get_db)):
    return _salida(db, ctx, _evento(db, ctx, evento_id), detalle=True)


def _destinos(db: Session, e: EventoAgenda, aplicar_a: str) -> list[EventoAgenda]:
    """La actividad y, si se pidió, las siguientes de su serie que todavía no tienen resultado."""
    if aplicar_a != "siguientes":
        return [e]
    if e.serie_id is None:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "La actividad no es parte de una serie.")
    siguientes = db.execute(
        select(EventoAgenda).where(EventoAgenda.serie_id == e.serie_id, EventoAgenda.inicio > e.inicio, EventoAgenda.estado == "programado").order_by(EventoAgenda.inicio)
    ).scalars().all()
    return [e, *siguientes]


@router.patch("/agenda/{evento_id}")
def modificar(evento_id: uuid.UUID, datos: EventoPatch, ctx: Contexto = Depends(contexto), db: Session = Depends(get_db)):
    e = _evento(db, ctx, evento_id, "modificar")
    if e.tipo == TIPO_EVENTO or datos.tipo == TIPO_EVENTO:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Los eventos de Participación se modifican desde esa sección.")
    modificar_actividad(db, ctx, e, datos)
    db.commit()
    db.refresh(e)
    return _salida(db, ctx, e, detalle=True)


def modificar_actividad(db: Session, ctx: Contexto, e: EventoAgenda, datos: EventoPatch, al_aplicar=None) -> list[EventoAgenda]:
    """Aplica los cambios a la actividad (y a las siguientes de su serie, si se pidió). ``al_aplicar(d)`` se llama
    para cada actividad modificada. No confirma la transacción."""
    if e.estado != "programado":
        raise HTTPException(status.HTTP_409_CONFLICT, "La actividad ya tiene resultado: no se puede modificar.")
    cambios = datos.model_dump(exclude_unset=True, exclude={"aplicar_a", "motivo"})
    if cambios.get("tipo") is not None and cambios["tipo"] not in TIPOS:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Tipo de actividad inválido.")
    destinos = _destinos(db, e, datos.aplicar_a)
    for d in destinos[1:]:
        if not _puede_modificar(db, ctx, d):
            raise HTTPException(status.HTTP_403_FORBIDDEN, "Alguna actividad siguiente está fuera de su alcance.")

    vinculo = None
    if "persona_id" in cambios or "caso_id" in cambios:
        persona_id = cambios["persona_id"] if "persona_id" in cambios else e.persona_id
        if "caso_id" in cambios:
            caso_id = cambios["caso_id"]
        else:
            caso_id = None if persona_id != e.persona_id else e.caso_id  # al cambiar de legajo se suelta el caso anterior
        persona, caso = _validar_vinculo(db, ctx, persona_id, caso_id)
        vinculo = (persona.id if persona else None, caso.id if caso else None)
    nuevos_participantes = None
    if cambios.get("participantes") is not None:
        nuevos_participantes = _validar_participantes(db, ctx, cambios["participantes"])

    # Desplazamiento de la hora y duración: las siguientes se mueven lo mismo que la primera.
    nuevo_inicio = cambios.get("inicio") or e.inicio
    desplazamiento = nuevo_inicio - e.inicio
    fin_pedido = "fin" in cambios
    nuevo_fin = cambios["fin"] if fin_pedido else e.fin
    if nuevo_fin is not None and nuevo_fin < nuevo_inicio:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "El fin es anterior al inicio.")
    duracion = (nuevo_fin - nuevo_inicio) if nuevo_fin is not None else None

    for d in destinos:
        antes = {
            "tipo": d.tipo, "titulo": d.titulo, "inicio": d.inicio.isoformat(), "fin": d.fin.isoformat() if d.fin else None,
            "lugar": d.lugar, "descripcion": d.descripcion, "todo_el_dia": d.todo_el_dia,
        }
        nombres_antes = sorted(p.usuario.nombre_completo for p in d.participantes)
        vinculo_antes = (d.persona_id, d.caso_id)
        for campo in ("tipo", "titulo", "todo_el_dia"):
            if cambios.get(campo) is not None:
                setattr(d, campo, cambios[campo])
        for campo in ("descripcion", "lugar"):
            if campo in cambios:
                setattr(d, campo, cambios[campo])
        if cambios.get("inicio") is not None:
            d.inicio = d.inicio + desplazamiento
            if d.fin is not None and not fin_pedido:
                d.fin = d.fin + desplazamiento
        if fin_pedido:
            d.fin = (d.inicio + duracion) if duracion is not None else None
        if vinculo is not None:
            d.persona_id, d.caso_id = vinculo
        if nuevos_participantes is not None:
            d.participantes = [ParticipanteAgenda(usuario_id=u.id) for u in nuevos_participantes]
        despues = {
            "tipo": d.tipo, "titulo": d.titulo, "inicio": d.inicio.isoformat(), "fin": d.fin.isoformat() if d.fin else None,
            "lugar": d.lugar, "descripcion": d.descripcion, "todo_el_dia": d.todo_el_dia,
        }
        diff = {k: [antes[k], despues[k]] for k in antes if antes[k] != despues[k]}
        if nuevos_participantes is not None:
            db.flush()
            db.refresh(d)
            nombres_despues = sorted(p.usuario.nombre_completo for p in d.participantes)
            if nombres_antes != nombres_despues:
                diff["participantes"] = [", ".join(nombres_antes), ", ".join(nombres_despues)]
        if vinculo is not None and vinculo != vinculo_antes:
            diff["legajo"] = ["otro", "otro"] if vinculo_antes[0] and vinculo[0] else ["sin legajo" if not vinculo_antes[0] else "con legajo", "sin legajo" if not vinculo[0] else "con legajo"]
        if diff:
            db.add(CambioAgenda(evento_id=d.id, usuario_id=ctx.id, cambios=diff, motivo=(datos.motivo or "").strip() or None))
        if al_aplicar is not None:
            al_aplicar(d)
        audit.registrar(db, ctx, "modificar", "agenda", d.id, d.persona_id, {"antes": {k: antes[k] for k in diff if k in antes}, "despues": {k: despues[k] for k in diff if k in despues}})
    return destinos


@router.post("/agenda/{evento_id}/resultado")
def registrar_resultado(evento_id: uuid.UUID, datos: ResultadoIn, ctx: Contexto = Depends(contexto), db: Session = Depends(get_db)):
    """Marca la actividad como realizada, no realizada o cancelada. Si está ligada a un caso, queda en su evolución.
    Cancelar «esta y las siguientes» corta una serie."""
    e = _evento(db, ctx, evento_id, "modificar")
    if e.estado != "programado":
        raise HTTPException(status.HTTP_409_CONFLICT, "La actividad ya tiene resultado.")
    if datos.estado == "no_realizado" and not (datos.resultado or "").strip():
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Indique el motivo por el que no se realizó.")
    if datos.aplicar_a == "siguientes" and datos.estado != "cancelado":
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Solo se puede cancelar esta actividad y las siguientes; el resultado se carga de a una.")
    destinos = _destinos(db, e, datos.aplicar_a)
    for d in destinos[1:]:
        if not _puede_modificar(db, ctx, d):
            raise HTTPException(status.HTTP_403_FORBIDDEN, "Alguna actividad siguiente está fuera de su alcance.")
    for d in destinos:
        d.estado = datos.estado
        d.resultado = (datos.resultado or "").strip() or None
        d.resuelto_por = ctx.id
        d.resuelto_en = ahora()
        if d.caso_id and datos.estado != "cancelado":
            caso = db.get(Caso, d.caso_id)
            texto = f"{TIPOS[d.tipo]} {ESTADOS_FINALES[datos.estado]}" + (f" ({d.lugar})" if d.lugar else "") + (f": {d.resultado}" if d.resultado else ".")
            db.add(CasoEvolucion(caso_id=caso.id, texto=texto, fecha=d.inicio.date(), autor_id=ctx.id, usuario_id=ctx.id))
            registrar_actividad_caso(caso)
        audit.registrar(db, ctx, "resultado", "agenda", d.id, d.persona_id, {"estado": d.estado})
    db.commit()
    db.refresh(e)
    return _salida(db, ctx, e, detalle=True)

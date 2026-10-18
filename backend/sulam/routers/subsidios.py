"""Subsidios: residencia de larga estadía, cuidador domiciliario, alimentarios, materiales y otros.

- Trámite: lista de papeles (copiada del catálogo al crear), estado, resolución y vigencia.
- Pagos: uno por mes, con su propia lista de papeles (residencias: la documentación mensual de la circular) y estado.

Permisos del módulo «subsidios»: consultar / crear / modificar. «Administrar» resuelve el trámite (aprobar, rechazar,
suspender, finalizar), carga la resolución y la vigencia, pasa los pagos a liquidación o pagado y genera los pagos del mes.
Hace falta además tener el legajo dentro del alcance de «personas».
"""

from __future__ import annotations

import uuid
from datetime import date
from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.responses import Response
from pydantic import Field
from sqlalchemy import and_, func, or_, select
from sqlalchemy.orm import Session

from .. import audit
from ..db import get_db
from ..deps import contexto
from ..models import Caso, Expediente, Internacion, Persona, Recurso, RecursoPeriodoRequisito, Subsidio, SubsidioPago, SubsidioRequisito
from ..permissions import Contexto, filtro_personas, persona_en_alcance
from ..schemas import Entrada
from ..security import ahora
from ..subsidios_catalogo import (
    CODIGOS_ESTADO,
    CODIGOS_ESTADO_PAGO,
    CODIGOS_ESTADO_REQUISITO,
    CODIGOS_TIPO,
    ESTADOS,
    ESTADOS_PAGO,
    ESTADOS_REQUISITO,
    ESTADOS_RESERVADOS,
    GRUPOS,
    MENSUAL_INSTITUCION,
    MENSUALES,
    PAGO_RESERVADO,
    TIPOS,
    requisitos_de,
)
from ._comun import no_encontrado, obtener_persona

router = APIRouter(tags=["subsidios"])


def _hoy() -> date:
    return date.today()


def _num(x) -> float | None:
    return float(x) if x is not None else None


def _primero_de_mes(d: date) -> date:
    return d.replace(day=1)


def _periodo_texto(d: date) -> str:
    return d.strftime("%Y-%m")


# ---------------------------------------------------------------- salida

def _requisito_out(r: SubsidioRequisito | RecursoPeriodoRequisito) -> dict:
    compartido = isinstance(r, RecursoPeriodoRequisito)
    return {
        "compartido": compartido,
        "id": str(r.id),
        "grupo": "institucion" if compartido else r.grupo,
        "grupo_texto": GRUPOS["institucion"] if compartido else GRUPOS.get(r.grupo, r.grupo),
        "codigo": r.codigo,
        "texto": r.texto,
        "estado": r.estado,
        "fecha_presentado": r.fecha_presentado.isoformat() if r.fecha_presentado else None,
        "observaciones": r.observaciones,
        "propio": r.codigo is None,
    }


def _conteo(requisitos: list[SubsidioRequisito]) -> dict:
    total = sum(1 for r in requisitos if r.estado != "no_corresponde")
    listos = sum(1 for r in requisitos if r.estado == "presentado")
    return {"total": total, "presentados": listos, "faltan": total - listos}


def _pago_out(p: SubsidioPago, requisitos: list[SubsidioRequisito] | None = None) -> dict:
    d = {
        "id": str(p.id),
        "subsidio_id": str(p.subsidio_id),
        "periodo": p.periodo.isoformat(),
        "periodo_texto": _periodo_texto(p.periodo),
        "monto": _num(p.monto),
        "estado": p.estado,
        "fecha_pago": p.fecha_pago.isoformat() if p.fecha_pago else None,
        "comprobante": p.comprobante,
        "observaciones": p.observaciones,
    }
    if requisitos is not None:
        d["papeles"] = _conteo(requisitos)
        d["requisitos"] = [_requisito_out(r) for r in requisitos]
    return d


def _sub_out(s: Subsidio, papeles: dict | None = None, persona: Persona | None = None) -> dict:
    d = {
        "id": str(s.id),
        "persona_id": str(s.persona_id),
        "caso_id": str(s.caso_id) if s.caso_id else None,
        "expediente_id": str(s.expediente_id) if s.expediente_id else None,
        "internacion_id": str(s.internacion_id) if s.internacion_id else None,
        "tipo": s.tipo,
        "tipo_texto": next((t["texto"] for t in TIPOS if t["codigo"] == s.tipo), s.tipo),
        "estado": s.estado,
        "recurso_id": str(s.recurso_id) if s.recurso_id else None,
        "prestador": s.recurso.nombre if s.recurso else s.prestador_texto,
        "prestador_texto": s.prestador_texto,
        "solicitante_nombre": s.solicitante_nombre,
        "solicitante_dni": s.solicitante_dni,
        "solicitante_vinculo": s.solicitante_vinculo,
        "solicitante_telefono": s.solicitante_telefono,
        "horas_semanales": _num(s.horas_semanales),
        "detalle": s.detalle,
        "monto_mensual": _num(s.monto_mensual),
        "fecha_solicitud": s.fecha_solicitud.isoformat() if s.fecha_solicitud else None,
        "fecha_elevacion": s.fecha_elevacion.isoformat() if s.fecha_elevacion else None,
        "resolucion_numero": s.resolucion_numero,
        "resolucion_fecha": s.resolucion_fecha.isoformat() if s.resolucion_fecha else None,
        "desde": s.desde.isoformat() if s.desde else None,
        "hasta": s.hasta.isoformat() if s.hasta else None,
        "observaciones": s.observaciones,
        "mensual": s.tipo in MENSUALES,
        "creado_en": s.creado_en.isoformat() if s.creado_en else None,
    }
    if papeles is not None:
        d["papeles"] = papeles
    if persona is not None:
        d["persona"] = {"id": str(persona.id), "numero_legajo": persona.numero_legajo, "nombre": f"{persona.apellidos}, {persona.nombres}"}
    return d


def _papeles_de(db: Session, ids: list[uuid.UUID]) -> dict[uuid.UUID, dict]:
    if not ids:
        return {}
    por: dict[uuid.UUID, list[SubsidioRequisito]] = {}
    for r in db.execute(select(SubsidioRequisito).where(SubsidioRequisito.subsidio_id.in_(ids), SubsidioRequisito.pago_id.is_(None))).scalars():
        por.setdefault(r.subsidio_id, []).append(r)
    return {i: _conteo(por.get(i, [])) for i in ids}


# ---------------------------------------------------------------- acceso

def _persona_visible(db: Session, ctx: Contexto, persona_id: uuid.UUID) -> Persona:
    p = obtener_persona(db, persona_id, permitir_unificada=True)
    if not persona_en_alcance(db, ctx, p, ctx.requerir("personas", "consultar")):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "El legajo está fuera de su alcance.")
    return p


def _subsidio(db: Session, ctx: Contexto, subsidio_id: uuid.UUID, accion: str = "consultar") -> tuple[Subsidio, Persona, str]:
    alcance = ctx.requerir("subsidios", accion)
    s = db.get(Subsidio, subsidio_id)
    if s is None:
        raise no_encontrado("Subsidio")
    p = _persona_visible(db, ctx, s.persona_id)
    return s, p, alcance


def _propio(ctx: Contexto, alcance: str, creado_por: uuid.UUID | None) -> None:
    if alcance == "propios" and creado_por != ctx.id:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Solo puede modificar lo que cargó usted.")


# ---------------------------------------------------------------- catálogo

@router.get("/subsidios/catalogo")
def catalogo(ctx: Contexto = Depends(contexto)):
    ctx.requerir("subsidios", "consultar")
    return {
        "tipos": TIPOS,
        "estados": ESTADOS,
        "estados_pago": ESTADOS_PAGO,
        "estados_requisito": ESTADOS_REQUISITO,
        "grupos": GRUPOS,
        "mensuales": sorted(MENSUALES),
        "puede": {"crear": ctx.tiene("subsidios", "crear"), "modificar": ctx.alcance("subsidios", "modificar"), "administrar": ctx.tiene("subsidios", "administrar")},
    }


# ---------------------------------------------------------------- alta y consulta

class SubsidioIn(Entrada):
    tipo: str
    caso_id: uuid.UUID | None = None
    expediente_id: uuid.UUID | None = None
    internacion_id: uuid.UUID | None = None
    recurso_id: uuid.UUID | None = None
    prestador_texto: str | None = Field(default=None, max_length=300)
    solicitante_nombre: str | None = Field(default=None, max_length=200)
    solicitante_dni: str | None = Field(default=None, max_length=20)
    solicitante_vinculo: str | None = Field(default=None, max_length=100)
    solicitante_telefono: str | None = Field(default=None, max_length=100)
    horas_semanales: float | None = Field(default=None, ge=0, le=168)
    detalle: str | None = Field(default=None, max_length=3000)
    monto_mensual: Decimal | None = Field(default=None, ge=0, max_digits=12, decimal_places=2)
    fecha_solicitud: date | None = None
    observaciones: str | None = Field(default=None, max_length=3000)


class SubsidioPatch(SubsidioIn):
    tipo: str | None = None  # type: ignore[assignment]
    estado: str | None = None
    fecha_elevacion: date | None = None
    resolucion_numero: str | None = Field(default=None, max_length=100)
    resolucion_fecha: date | None = None
    desde: date | None = None
    hasta: date | None = None


def _validar_vinculos(db: Session, persona_id: uuid.UUID, v: dict) -> None:
    if v.get("tipo") is not None and v["tipo"] not in CODIGOS_TIPO:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Tipo de subsidio inválido.")
    if v.get("caso_id") is not None:
        c = db.get(Caso, v["caso_id"])
        if c is None or c.persona_id != persona_id:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, "El caso no pertenece a este legajo.")
    if v.get("expediente_id") is not None:
        e = db.get(Expediente, v["expediente_id"])
        if e is None or e.persona_id != persona_id:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, "El expediente no pertenece a este legajo.")
    if v.get("internacion_id") is not None:
        i = db.get(Internacion, v["internacion_id"])
        if i is None or i.persona_id != persona_id:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, "La internación no pertenece a este legajo.")
    if v.get("recurso_id") is not None and db.get(Recurso, v["recurso_id"]) is None:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "El recurso elegido no existe en el mapa.")


def _agregar_requisitos(db: Session, s: Subsidio, ctx: Contexto, tipo: str, mensual: bool, pago: SubsidioPago | None) -> None:
    for orden, (grupo, codigo, texto) in enumerate(requisitos_de(tipo, mensual)):
        db.add(SubsidioRequisito(subsidio_id=s.id, pago_id=pago.id if pago else None, grupo=grupo, codigo=codigo, texto=texto, orden=orden, actualizado_por=ctx.id))
    # Papeles de la institución: se cargan una vez por residencia y mes. Sin residencia del mapa, quedan en cada pago.
    if mensual and tipo == "residencia" and pago is not None:
        if s.recurso_id is not None:
            _asegurar_periodo(db, ctx, s.recurso_id, pago.periodo)
        else:
            base = len(requisitos_de(tipo, True))
            for i, (codigo, texto) in enumerate(MENSUAL_INSTITUCION):
                db.add(SubsidioRequisito(subsidio_id=s.id, pago_id=pago.id, grupo="institucion", codigo=codigo, texto=texto, orden=base + i, actualizado_por=ctx.id))


def _asegurar_periodo(db: Session, ctx: Contexto, recurso_id: uuid.UUID, periodo: date) -> bool:
    """Arma la lista de papeles mensuales de la residencia si todavía no existe. Devuelve si la creó."""
    if db.execute(select(RecursoPeriodoRequisito.id).where(RecursoPeriodoRequisito.recurso_id == recurso_id, RecursoPeriodoRequisito.periodo == periodo).limit(1)).first():
        return False
    for orden, (codigo, texto) in enumerate(MENSUAL_INSTITUCION):
        db.add(RecursoPeriodoRequisito(recurso_id=recurso_id, periodo=periodo, codigo=codigo, texto=texto, orden=orden, actualizado_por=ctx.id))
    db.flush()
    return True


def _requisitos_de_pago(db: Session, pago: SubsidioPago, s: Subsidio) -> list:
    """Papeles del mes de un subsidio: los propios y, en residencias del mapa, los de la institución (compartidos)."""
    propios = list(db.execute(select(SubsidioRequisito).where(SubsidioRequisito.pago_id == pago.id).order_by(SubsidioRequisito.orden, SubsidioRequisito.actualizado_en)).scalars())
    if s.tipo == "residencia" and s.recurso_id is not None:
        propios += list(db.execute(select(RecursoPeriodoRequisito).where(RecursoPeriodoRequisito.recurso_id == s.recurso_id, RecursoPeriodoRequisito.periodo == pago.periodo).order_by(RecursoPeriodoRequisito.orden, RecursoPeriodoRequisito.actualizado_en)).scalars())
    return propios


@router.get("/personas/{persona_id}/subsidios")
def subsidios_de_persona(persona_id: uuid.UUID, ctx: Contexto = Depends(contexto), db: Session = Depends(get_db)):
    ctx.requerir("subsidios", "consultar")
    _persona_visible(db, ctx, persona_id)
    filas = db.execute(select(Subsidio).where(Subsidio.persona_id == persona_id).order_by(Subsidio.creado_en.desc())).scalars().all()
    papeles = _papeles_de(db, [s.id for s in filas])
    return [_sub_out(s, papeles[s.id]) for s in filas]


@router.post("/personas/{persona_id}/subsidios", status_code=201)
def crear_subsidio(persona_id: uuid.UUID, datos: SubsidioIn, ctx: Contexto = Depends(contexto), db: Session = Depends(get_db)):
    ctx.requerir("subsidios", "crear")
    p = _persona_visible(db, ctx, persona_id)
    v = datos.model_dump()
    _validar_vinculos(db, persona_id, v)
    s = Subsidio(persona_id=persona_id, creado_por=ctx.id, actualizado_por=ctx.id, **v)
    if s.fecha_solicitud is None:
        s.fecha_solicitud = _hoy()
    db.add(s)
    db.flush()
    _agregar_requisitos(db, s, ctx, s.tipo, False, None)
    audit.registrar(db, ctx, "subsidio_creado", "subsidio", s.id, persona_id, {"tipo": s.tipo})
    db.commit()
    db.refresh(s)
    return _sub_out(s, _papeles_de(db, [s.id])[s.id], p)


@router.get("/subsidios")
def listar(
    tipo: str | None = None,
    estado: str | None = None,
    recurso_id: uuid.UUID | None = None,
    q: str = Query("", max_length=200),
    ctx: Contexto = Depends(contexto),
    db: Session = Depends(get_db),
):
    ctx.requerir("subsidios", "consultar")
    alcance = ctx.requerir("personas", "consultar")
    consulta = select(Subsidio, Persona).join(Persona, Persona.id == Subsidio.persona_id).where(filtro_personas(ctx, alcance))
    if tipo:
        consulta = consulta.where(Subsidio.tipo == tipo)
    if estado:
        consulta = consulta.where(Subsidio.estado == estado)
    if recurso_id:
        consulta = consulta.where(Subsidio.recurso_id == recurso_id)
    if q.strip():
        t = "%" + q.strip().replace("%", "").replace("_", "") + "%"
        consulta = consulta.where(or_(Persona.apellidos.ilike(t), Persona.nombres.ilike(t), Persona.numero_legajo.ilike(t), Subsidio.resolucion_numero.ilike(t)))
    filas = db.execute(consulta.order_by(Subsidio.creado_en.desc()).limit(500)).all()
    papeles = _papeles_de(db, [s.id for s, _ in filas])
    # Resumen sobre lo que la persona puede ver, sin los filtros de tipo/estado.
    base = select(Subsidio.estado, func.count(), func.coalesce(func.sum(Subsidio.monto_mensual), 0)).join(Persona, Persona.id == Subsidio.persona_id).where(filtro_personas(ctx, alcance)).group_by(Subsidio.estado)
    por_estado = {e: {"cantidad": c, "monto_mensual": float(m)} for e, c, m in db.execute(base)}
    return {"items": [_sub_out(s, papeles[s.id], p) for s, p in filas], "por_estado": por_estado}


@router.get("/subsidios/{subsidio_id}")
def ver(subsidio_id: uuid.UUID, ctx: Contexto = Depends(contexto), db: Session = Depends(get_db)):
    s, p, _a = _subsidio(db, ctx, subsidio_id)
    reqs = db.execute(select(SubsidioRequisito).where(SubsidioRequisito.subsidio_id == s.id).order_by(SubsidioRequisito.orden, SubsidioRequisito.actualizado_en)).scalars().all()
    tramite = [r for r in reqs if r.pago_id is None]
    pagos = db.execute(select(SubsidioPago).where(SubsidioPago.subsidio_id == s.id).order_by(SubsidioPago.periodo.desc())).scalars().all()
    d = _sub_out(s, _conteo(tramite), p)
    d["requisitos"] = [_requisito_out(r) for r in tramite]
    d["pagos"] = [_pago_out(x, _requisitos_de_pago(db, x, s)) for x in pagos]
    d["total_pagado"] = float(sum((x.monto or 0) for x in pagos if x.estado == "pagado"))
    return d


@router.patch("/subsidios/{subsidio_id}")
def modificar(subsidio_id: uuid.UUID, datos: SubsidioPatch, ctx: Contexto = Depends(contexto), db: Session = Depends(get_db)):
    s, p, alcance = _subsidio(db, ctx, subsidio_id, "modificar")
    _propio(ctx, alcance, s.creado_por)
    cambios = datos.model_dump(exclude_unset=True)
    if cambios.get("tipo") is None:
        cambios.pop("tipo", None)
    if "tipo" in cambios and cambios["tipo"] != s.tipo:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "No se puede cambiar el tipo de un subsidio. Cree uno nuevo.")
    for k, v in list(cambios.items()):
        if isinstance(v, str):
            cambios[k] = v.strip() or None
    _validar_vinculos(db, s.persona_id, cambios)
    administra = ctx.tiene("subsidios", "administrar")
    reservados = {"estado", "resolucion_numero", "resolucion_fecha", "desde", "hasta"}
    if (reservados & set(cambios) or ("monto_mensual" in cambios and s.estado == "aprobado")) and not administra:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "La resolución, la vigencia, el monto aprobado y el estado del trámite los carga quien administra los subsidios.")
    nuevo_estado = cambios.get("estado")
    if nuevo_estado is not None:
        if nuevo_estado not in CODIGOS_ESTADO:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, "Estado inválido.")
        if nuevo_estado in ESTADOS_RESERVADOS and not administra:
            raise HTTPException(status.HTTP_403_FORBIDDEN, "Solo quien administra los subsidios resuelve el trámite.")
    final = {c: cambios.get(c, getattr(s, c)) for c in ("estado", "resolucion_numero", "desde", "hasta", "fecha_elevacion")}
    if final["estado"] == "elevado" and final["fecha_elevacion"] is None:
        cambios["fecha_elevacion"] = final["fecha_elevacion"] = _hoy()
    if final["estado"] == "aprobado" and (not final["resolucion_numero"] or final["desde"] is None):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Para aprobar cargue el número de resolución y desde cuándo rige.")
    if final["estado"] == "finalizado" and final["hasta"] is None:
        cambios["hasta"] = final["hasta"] = _hoy()
    if final["desde"] and final["hasta"] and final["hasta"] < final["desde"]:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "El fin no puede ser anterior al inicio.")
    diff = {}
    for k, v in cambios.items():
        if getattr(s, k) != v:
            diff[k] = [str(getattr(s, k)) if getattr(s, k) is not None else None, str(v) if v is not None else None]
            setattr(s, k, v)
    if diff:
        s.actualizado_por = ctx.id
        s.actualizado_en = ahora()
        audit.registrar(db, ctx, "subsidio_modificado", "subsidio", s.id, s.persona_id, {"cambios": diff})
        db.commit()
        db.refresh(s)
    return _sub_out(s, _papeles_de(db, [s.id])[s.id], p)


# ---------------------------------------------------------------- papeles

class RequisitoPatch(Entrada):
    estado: str | None = None
    fecha_presentado: date | None = None
    observaciones: str | None = Field(default=None, max_length=1000)


class RequisitoIn(Entrada):
    texto: str = Field(min_length=3, max_length=500)
    grupo: str = "otros"
    pago_id: uuid.UUID | None = None


def _requisito(db: Session, ctx: Contexto, requisito_id: uuid.UUID) -> tuple[SubsidioRequisito, Subsidio, str]:
    r = db.get(SubsidioRequisito, requisito_id)
    if r is None:
        raise no_encontrado("Papel")
    s, _p, alcance = _subsidio(db, ctx, r.subsidio_id, "modificar")
    _propio(ctx, alcance, s.creado_por)
    return r, s, alcance


def _sincronizar_pago(db: Session, pago_id: uuid.UUID | None) -> None:
    """Un mes con todos sus papeles pasa solo a «documentación completa»; si falta alguno, vuelve a «pendiente»."""
    if pago_id is None:
        return
    pago = db.get(SubsidioPago, pago_id)
    if pago is None or pago.estado not in ("pendiente", "documentacion_completa"):
        return
    reqs = _requisitos_de_pago(db, pago, db.get(Subsidio, pago.subsidio_id))
    completo = bool(reqs) and _conteo(reqs)["faltan"] == 0
    pago.estado = "documentacion_completa" if completo else "pendiente"


def _sincronizar_periodo(db: Session, recurso_id: uuid.UUID, periodo: date) -> None:
    """Cuando cambia un papel de la residencia, se recalcula el mes de todos sus residentes."""
    db.flush()
    ids = db.execute(select(SubsidioPago.id).join(Subsidio, Subsidio.id == SubsidioPago.subsidio_id).where(Subsidio.recurso_id == recurso_id, Subsidio.tipo == "residencia", SubsidioPago.periodo == periodo)).scalars().all()
    for i in ids:
        _sincronizar_pago(db, i)

@router.patch("/subsidios/requisitos/{requisito_id}")
def marcar_requisito(requisito_id: uuid.UUID, datos: RequisitoPatch, ctx: Contexto = Depends(contexto), db: Session = Depends(get_db)):
    r, s, _a = _requisito(db, ctx, requisito_id)
    cambios = datos.model_dump(exclude_unset=True)
    if cambios.get("estado") is not None and cambios["estado"] not in CODIGOS_ESTADO_REQUISITO:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Estado inválido.")
    if cambios.get("estado") is None:
        cambios.pop("estado", None)
    anterior = r.estado
    for k, v in cambios.items():
        if isinstance(v, str):
            v = v.strip() or None
        setattr(r, k, v)
    if r.estado == "presentado" and r.fecha_presentado is None:
        r.fecha_presentado = _hoy()
    if r.estado != "presentado":
        r.fecha_presentado = None
    r.actualizado_por = ctx.id
    r.actualizado_en = ahora()
    _sincronizar_pago(db, r.pago_id)
    if anterior != r.estado:
        audit.registrar(db, ctx, "subsidio_papel", "subsidio", s.id, s.persona_id, {"papel": r.codigo or r.texto[:60], "periodo": str(r.pago_id) if r.pago_id else None, "antes": anterior, "despues": r.estado})
    db.commit()
    return _requisito_out(r)


@router.post("/subsidios/{subsidio_id}/requisitos", status_code=201)
def agregar_requisito(subsidio_id: uuid.UUID, datos: RequisitoIn, ctx: Contexto = Depends(contexto), db: Session = Depends(get_db)):
    s, _p, alcance = _subsidio(db, ctx, subsidio_id, "modificar")
    _propio(ctx, alcance, s.creado_por)
    if datos.grupo not in GRUPOS:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Grupo inválido.")
    if datos.pago_id is not None:
        pago = db.get(SubsidioPago, datos.pago_id)
        if pago is None or pago.subsidio_id != s.id:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, "El mes no pertenece a este subsidio.")
    ultimo = db.execute(select(func.coalesce(func.max(SubsidioRequisito.orden), 0)).where(SubsidioRequisito.subsidio_id == s.id, SubsidioRequisito.pago_id == datos.pago_id if datos.pago_id else SubsidioRequisito.pago_id.is_(None))).scalar_one()
    r = SubsidioRequisito(subsidio_id=s.id, pago_id=datos.pago_id, grupo=datos.grupo, codigo=None, texto=datos.texto.strip(), orden=min(ultimo + 1, 32000), actualizado_por=ctx.id)
    db.add(r)
    db.flush()
    _sincronizar_pago(db, datos.pago_id)
    audit.registrar(db, ctx, "subsidio_papel_agregado", "subsidio", s.id, s.persona_id, {"texto": r.texto[:100]})
    db.commit()
    return _requisito_out(r)


@router.delete("/subsidios/requisitos/{requisito_id}", status_code=204)
def quitar_requisito(requisito_id: uuid.UUID, ctx: Contexto = Depends(contexto), db: Session = Depends(get_db)):
    r, s, _a = _requisito(db, ctx, requisito_id)
    if r.codigo is not None:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Los papeles del catálogo no se quitan: márquelos «No corresponde».")
    pago_id = r.pago_id
    audit.registrar(db, ctx, "subsidio_papel_quitado", "subsidio", s.id, s.persona_id, {"texto": r.texto[:100]})
    db.delete(r)
    db.flush()
    _sincronizar_pago(db, pago_id)
    db.commit()
    return Response(status_code=204)


# ------------------------------------------- papeles mensuales de la residencia

class PeriodoRequisitoIn(Entrada):
    texto: str = Field(min_length=3, max_length=500)


def _periodo_de(texto: str) -> date:
    try:
        anio, mes = int(texto[:4]), int(texto[5:7])
        if len(texto) != 7 or texto[4] != "-":
            raise ValueError
        return date(anio, mes, 1)
    except ValueError:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Mes inválido (use AAAA-MM).")


def _recurso_residencia(db: Session, recurso_id: uuid.UUID) -> Recurso:
    rec = db.get(Recurso, recurso_id)
    if rec is None:
        raise no_encontrado("Residencia")
    return rec


@router.get("/subsidios/residencias/{recurso_id}/{periodo}")
def documentacion_mensual(recurso_id: uuid.UUID, periodo: str, ctx: Contexto = Depends(contexto), db: Session = Depends(get_db)):
    """Papeles que la residencia presenta una vez al mes, y cómo está el mes de cada residente con subsidio."""
    ctx.requerir("subsidios", "consultar")
    alcance = ctx.requerir("personas", "consultar")
    inicio = _periodo_de(periodo)
    rec = _recurso_residencia(db, recurso_id)
    reqs = db.execute(select(RecursoPeriodoRequisito).where(RecursoPeriodoRequisito.recurso_id == recurso_id, RecursoPeriodoRequisito.periodo == inicio).order_by(RecursoPeriodoRequisito.orden, RecursoPeriodoRequisito.actualizado_en)).scalars().all()
    filas = db.execute(
        select(SubsidioPago, Subsidio, Persona)
        .join(Subsidio, Subsidio.id == SubsidioPago.subsidio_id)
        .join(Persona, Persona.id == Subsidio.persona_id)
        .where(Subsidio.recurso_id == recurso_id, Subsidio.tipo == "residencia", SubsidioPago.periodo == inicio, filtro_personas(ctx, alcance))
        .order_by(Persona.apellidos, Persona.nombres)
    ).all()
    residentes = []
    for pago, s, per in filas:
        propios = db.execute(select(SubsidioRequisito).where(SubsidioRequisito.pago_id == pago.id)).scalars().all()
        residentes.append({
            "pago_id": str(pago.id), "subsidio_id": str(s.id), "estado": pago.estado, "monto": _num(pago.monto),
            "papeles": _conteo(propios), "persona": {"id": str(per.id), "numero_legajo": per.numero_legajo, "nombre": f"{per.apellidos}, {per.nombres}"},
        })
    return {"recurso": {"id": str(rec.id), "nombre": rec.nombre}, "periodo": periodo, "armado": bool(reqs), "papeles": [_requisito_out(r) for r in reqs], "conteo": _conteo(reqs), "residentes": residentes}


@router.post("/subsidios/residencias/{recurso_id}/{periodo}", status_code=201)
def armar_documentacion(recurso_id: uuid.UUID, periodo: str, ctx: Contexto = Depends(contexto), db: Session = Depends(get_db)):
    ctx.requerir("subsidios", "modificar")
    inicio = _periodo_de(periodo)
    _recurso_residencia(db, recurso_id)
    creada = _asegurar_periodo(db, ctx, recurso_id, inicio)
    if creada:
        audit.registrar(db, ctx, "subsidio_documentacion_mensual", "recurso", recurso_id, None, {"periodo": _periodo_texto(inicio)})
        _sincronizar_periodo(db, recurso_id, inicio)
    db.commit()
    return documentacion_mensual(recurso_id, periodo, ctx, db)


def _periodo_requisito(db: Session, ctx: Contexto, requisito_id: uuid.UUID) -> RecursoPeriodoRequisito:
    ctx.requerir("subsidios", "modificar")
    r = db.get(RecursoPeriodoRequisito, requisito_id)
    if r is None:
        raise no_encontrado("Papel")
    return r


@router.patch("/subsidios/periodo-requisitos/{requisito_id}")
def marcar_papel_residencia(requisito_id: uuid.UUID, datos: RequisitoPatch, ctx: Contexto = Depends(contexto), db: Session = Depends(get_db)):
    r = _periodo_requisito(db, ctx, requisito_id)
    cambios = datos.model_dump(exclude_unset=True)
    if cambios.get("estado") is not None and cambios["estado"] not in CODIGOS_ESTADO_REQUISITO:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Estado inválido.")
    if cambios.get("estado") is None:
        cambios.pop("estado", None)
    anterior = r.estado
    for k, v in cambios.items():
        if isinstance(v, str):
            v = v.strip() or None
        setattr(r, k, v)
    if r.estado == "presentado" and r.fecha_presentado is None:
        r.fecha_presentado = _hoy()
    if r.estado != "presentado":
        r.fecha_presentado = None
    r.actualizado_por = ctx.id
    r.actualizado_en = ahora()
    _sincronizar_periodo(db, r.recurso_id, r.periodo)
    if anterior != r.estado:
        audit.registrar(db, ctx, "subsidio_papel_residencia", "recurso", r.recurso_id, None, {"papel": r.codigo or r.texto[:60], "periodo": _periodo_texto(r.periodo), "antes": anterior, "despues": r.estado})
    db.commit()
    return _requisito_out(r)


@router.post("/subsidios/residencias/{recurso_id}/{periodo}/requisitos", status_code=201)
def agregar_papel_residencia(recurso_id: uuid.UUID, periodo: str, datos: PeriodoRequisitoIn, ctx: Contexto = Depends(contexto), db: Session = Depends(get_db)):
    ctx.requerir("subsidios", "modificar")
    inicio = _periodo_de(periodo)
    _recurso_residencia(db, recurso_id)
    _asegurar_periodo(db, ctx, recurso_id, inicio)
    ultimo = db.execute(select(func.coalesce(func.max(RecursoPeriodoRequisito.orden), 0)).where(RecursoPeriodoRequisito.recurso_id == recurso_id, RecursoPeriodoRequisito.periodo == inicio)).scalar_one()
    r = RecursoPeriodoRequisito(recurso_id=recurso_id, periodo=inicio, codigo=None, texto=datos.texto.strip(), orden=min(ultimo + 1, 32000), actualizado_por=ctx.id)
    db.add(r)
    _sincronizar_periodo(db, recurso_id, inicio)
    audit.registrar(db, ctx, "subsidio_papel_residencia_agregado", "recurso", recurso_id, None, {"texto": r.texto[:100]})
    db.commit()
    return _requisito_out(r)


@router.delete("/subsidios/periodo-requisitos/{requisito_id}", status_code=204)
def quitar_papel_residencia(requisito_id: uuid.UUID, ctx: Contexto = Depends(contexto), db: Session = Depends(get_db)):
    r = _periodo_requisito(db, ctx, requisito_id)
    if r.codigo is not None:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Los papeles del catálogo no se quitan: márquelos «No corresponde».")
    rid, per = r.recurso_id, r.periodo
    audit.registrar(db, ctx, "subsidio_papel_residencia_quitado", "recurso", rid, None, {"texto": r.texto[:100]})
    db.delete(r)
    _sincronizar_periodo(db, rid, per)
    db.commit()
    return Response(status_code=204)


# ---------------------------------------------------------------- pagos

class PagoIn(Entrada):
    periodo: date
    monto: Decimal | None = Field(default=None, ge=0, max_digits=12, decimal_places=2)


class PagoPatch(Entrada):
    estado: str | None = None
    monto: Decimal | None = Field(default=None, ge=0, max_digits=12, decimal_places=2)
    fecha_pago: date | None = None
    comprobante: str | None = Field(default=None, max_length=100)
    observaciones: str | None = Field(default=None, max_length=2000)
    forzar: bool = False


def _vigente_en(s: Subsidio, periodo: date) -> bool:
    if s.estado != "aprobado" or s.desde is None:
        return False
    fin_mes = (periodo.replace(day=28) + (date(2000, 1, 5) - date(2000, 1, 1))).replace(day=1)  # primer día del mes siguiente
    return s.desde < fin_mes and (s.hasta is None or s.hasta >= periodo)


def _crear_pago(db: Session, ctx: Contexto, s: Subsidio, periodo: date, monto: Decimal | None) -> SubsidioPago:
    pago = SubsidioPago(subsidio_id=s.id, periodo=periodo, monto=monto if monto is not None else s.monto_mensual, creado_por=ctx.id, actualizado_por=ctx.id)
    db.add(pago)
    db.flush()
    _agregar_requisitos(db, s, ctx, s.tipo, True, pago)
    audit.registrar(db, ctx, "subsidio_pago_creado", "subsidio", s.id, s.persona_id, {"periodo": _periodo_texto(periodo)})
    return pago


@router.post("/subsidios/{subsidio_id}/pagos", status_code=201)
def agregar_pago(subsidio_id: uuid.UUID, datos: PagoIn, ctx: Contexto = Depends(contexto), db: Session = Depends(get_db)):
    s, _p, alcance = _subsidio(db, ctx, subsidio_id, "modificar")
    _propio(ctx, alcance, s.creado_por)
    if s.tipo not in MENSUALES:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Este tipo de subsidio no tiene pagos mensuales.")
    periodo = _primero_de_mes(datos.periodo)
    if not _vigente_en(s, periodo):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "El subsidio tiene que estar aprobado y vigente en ese mes.")
    if db.execute(select(SubsidioPago.id).where(SubsidioPago.subsidio_id == s.id, SubsidioPago.periodo == periodo)).first():
        raise HTTPException(status.HTTP_409_CONFLICT, "Ya existe el mes " + _periodo_texto(periodo) + ".")
    pago = _crear_pago(db, ctx, s, periodo, datos.monto)
    db.commit()
    return _pago_out(pago, _requisitos_de_pago(db, pago, s))


@router.post("/subsidios/pagos/generar")
def generar_pagos(datos: PagoIn, ctx: Contexto = Depends(contexto), db: Session = Depends(get_db)):
    """Crea el mes de todos los subsidios mensuales aprobados y vigentes (dentro de su alcance) que todavía no lo tienen."""
    ctx.requerir("subsidios", "administrar")
    alcance = ctx.requerir("personas", "consultar")
    periodo = _primero_de_mes(datos.periodo)
    filas = db.execute(
        select(Subsidio).join(Persona, Persona.id == Subsidio.persona_id).where(Subsidio.tipo.in_(MENSUALES), Subsidio.estado == "aprobado", filtro_personas(ctx, alcance))
    ).scalars().all()
    existentes = set(db.execute(select(SubsidioPago.subsidio_id).where(SubsidioPago.periodo == periodo)).scalars())
    creados = 0
    for s in filas:
        if s.id in existentes or not _vigente_en(s, periodo):
            continue
        _crear_pago(db, ctx, s, periodo, None)
        creados += 1
    db.commit()
    return {"periodo": _periodo_texto(periodo), "creados": creados, "ya_existian": len(existentes)}


def _pago(db: Session, ctx: Contexto, pago_id: uuid.UUID, accion: str) -> tuple[SubsidioPago, Subsidio, str]:
    p = db.get(SubsidioPago, pago_id)
    if p is None:
        raise no_encontrado("Pago")
    s, _per, alcance = _subsidio(db, ctx, p.subsidio_id, accion)
    return p, s, alcance


@router.patch("/subsidios/pagos/{pago_id}")
def modificar_pago(pago_id: uuid.UUID, datos: PagoPatch, ctx: Contexto = Depends(contexto), db: Session = Depends(get_db)):
    p, s, alcance = _pago(db, ctx, pago_id, "modificar")
    _propio(ctx, alcance, s.creado_por)
    c = datos.model_dump(exclude_unset=True)
    forzar = c.pop("forzar", False)
    administra = ctx.tiene("subsidios", "administrar")
    estado = c.get("estado")
    if estado is not None:
        if estado not in CODIGOS_ESTADO_PAGO:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, "Estado inválido.")
        if (estado in PAGO_RESERVADO or p.estado in PAGO_RESERVADO) and not administra:
            raise HTTPException(status.HTTP_403_FORBIDDEN, "Solo quien administra los subsidios liquida y registra el pago.")
        if estado in PAGO_RESERVADO and p.estado not in PAGO_RESERVADO:
            faltan = _conteo(_requisitos_de_pago(db, p, s))["faltan"]
            if faltan and not forzar:
                raise HTTPException(status.HTTP_409_CONFLICT, {"mensaje": f"Faltan {faltan} papeles de este mes. Complételos o confirme que desea liquidar igual.", "faltan": faltan})
            if faltan:
                audit.registrar(db, ctx, "subsidio_pago_forzado", "subsidio", s.id, s.persona_id, {"periodo": _periodo_texto(p.periodo), "faltan": faltan})
    elif any(k in c for k in ("monto", "fecha_pago", "comprobante")) and p.estado in PAGO_RESERVADO and not administra:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "El pago ya está en liquidación: lo modifica quien administra los subsidios.")
    if "monto" in c and not administra and p.estado != "pendiente" and p.estado != "documentacion_completa":
        raise HTTPException(status.HTTP_403_FORBIDDEN, "El monto lo cambia quien administra los subsidios.")
    for k, v in list(c.items()):
        if isinstance(v, str):
            c[k] = v.strip() or None
    if c.get("estado") == "pagado" and not (c.get("fecha_pago") or p.fecha_pago):
        c["fecha_pago"] = _hoy()
    diff = {}
    for k, v in c.items():
        if getattr(p, k) != v:
            diff[k] = [str(getattr(p, k)) if getattr(p, k) is not None else None, str(v) if v is not None else None]
            setattr(p, k, v)
    if diff:
        p.actualizado_por = ctx.id
        p.actualizado_en = ahora()
        audit.registrar(db, ctx, "subsidio_pago_modificado", "subsidio", s.id, s.persona_id, {"periodo": _periodo_texto(p.periodo), "cambios": diff})
        db.commit()
        db.refresh(p)
    return _pago_out(p, _requisitos_de_pago(db, p, s))


@router.delete("/subsidios/pagos/{pago_id}", status_code=204)
def quitar_pago(pago_id: uuid.UUID, ctx: Contexto = Depends(contexto), db: Session = Depends(get_db)):
    p, s, alcance = _pago(db, ctx, pago_id, "modificar")
    _propio(ctx, alcance, s.creado_por)
    if p.estado in PAGO_RESERVADO:
        raise HTTPException(status.HTTP_409_CONFLICT, "Un mes en liquidación o pagado no se elimina.")
    audit.registrar(db, ctx, "subsidio_pago_quitado", "subsidio", s.id, s.persona_id, {"periodo": _periodo_texto(p.periodo)})
    db.delete(p)
    db.commit()
    return Response(status_code=204)


@router.get("/subsidios-pagos")
def pagos_del_mes(
    periodo: str = Query(..., pattern=r"^\d{4}-\d{2}$"),
    estado: str | None = None,
    recurso_id: uuid.UUID | None = None,
    ctx: Contexto = Depends(contexto),
    db: Session = Depends(get_db),
):
    """Liquidación del mes: un renglón por subsidio, con sus papeles y estado de pago."""
    ctx.requerir("subsidios", "consultar")
    alcance = ctx.requerir("personas", "consultar")
    anio, mes = int(periodo[:4]), int(periodo[5:])
    if not 1 <= mes <= 12:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Mes inválido.")
    inicio = date(anio, mes, 1)
    consulta = (
        select(SubsidioPago, Subsidio, Persona)
        .join(Subsidio, Subsidio.id == SubsidioPago.subsidio_id)
        .join(Persona, Persona.id == Subsidio.persona_id)
        .where(SubsidioPago.periodo == inicio, filtro_personas(ctx, alcance))
    )
    if estado:
        consulta = consulta.where(SubsidioPago.estado == estado)
    if recurso_id:
        consulta = consulta.where(Subsidio.recurso_id == recurso_id)
    filas = db.execute(consulta.order_by(Persona.apellidos, Persona.nombres)).all()
    conteo: dict[uuid.UUID, list[SubsidioRequisito]] = {}
    ids = [p.id for p, _s, _x in filas]
    if ids:
        for r in db.execute(select(SubsidioRequisito).where(SubsidioRequisito.pago_id.in_(ids))).scalars():
            conteo.setdefault(r.pago_id, []).append(r)
        rids = {s.recurso_id for _p, s, _x in filas if s.tipo == "residencia" and s.recurso_id}
        compartidos: dict[tuple, list] = {}
        if rids:
            for r in db.execute(select(RecursoPeriodoRequisito).where(RecursoPeriodoRequisito.recurso_id.in_(rids), RecursoPeriodoRequisito.periodo == inicio)).scalars():
                compartidos.setdefault(r.recurso_id, []).append(r)
        for pago, s, _x in filas:
            if s.tipo == "residencia" and s.recurso_id:
                conteo.setdefault(pago.id, []).extend(compartidos.get(s.recurso_id, []))
    items = []
    for pago, s, per in filas:
        d = _pago_out(pago)
        d["papeles"] = _conteo(conteo.get(pago.id, []))
        d["subsidio"] = {"id": str(s.id), "tipo": s.tipo, "prestador": s.recurso.nombre if s.recurso else s.prestador_texto, "recurso_id": str(s.recurso_id) if s.recurso_id else None}
        d["persona"] = {"id": str(per.id), "numero_legajo": per.numero_legajo, "nombre": f"{per.apellidos}, {per.nombres}"}
        items.append(d)
    por_estado: dict[str, dict] = {}
    for d in items:
        x = por_estado.setdefault(d["estado"], {"cantidad": 0, "monto": 0.0})
        x["cantidad"] += 1
        x["monto"] += d["monto"] or 0
    return {"periodo": periodo, "items": items, "por_estado": por_estado, "total": sum(d["monto"] or 0 for d in items)}

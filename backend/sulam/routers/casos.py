from __future__ import annotations

import uuid
from datetime import timedelta

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from .. import audit
from ..db import get_db
from ..deps import contexto
from ..models import (
    Area,
    Caso,
    CasoAsignacion,
    CasoEstadoHistorial,
    CasoEvolucion,
    RegistroDemanda,
    Reiteracion,
    Documento,
    Expediente,
    Ingreso,
    Persona,
    Usuario,
)
from ..numbering import formato_caso, nueva_actuacion
from ..permissions import (
    Contexto,
    filtro_casos,
    requerir_caso,
    requerir_persona,
    ve_caso_reservado,
    ve_reservado_de_persona,
)
from ..schemas import (
    AsignacionIn,
    CambioEstadoIn,
    CaratulaCampos,
    CasoIn,
    CasoPatch,
    EvolucionIn,
    FinAsignacionIn,
    ReiteracionIn,
)
from ..security import ahora
from ..serializers import (
    caso_out,
    demanda_out,
    documento_out,
    evolucion_out,
    reiteracion_out,
    expediente_out,
    ingreso_out,
    persona_detalle,
    usuario_breve,
)
from ..textutil import escapar_like, normalizar
from ..formularios import validar_ingreso
from ._caratula import antecedentes_sistema, aplicar_caratula
from .demandas import escaneos_de
from ._comun import no_encontrado, obtener_caso, obtener_persona, registrar_actividad_caso

router = APIRouter(tags=["casos"])

TRANSICIONES_CON_MOTIVO = {"pausado", "cerrado"}
DIAS_SIN_ACTIVIDAD = 30


def _asignar(db: Session, ctx: Contexto, caso: Caso, usuario_id: uuid.UUID, motivo: str | None) -> CasoAsignacion:
    usuario = db.get(Usuario, usuario_id)
    if usuario is None or not usuario.activo:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "El usuario a asignar no existe o está inactivo.")
    ya = db.execute(
        select(CasoAsignacion).where(
            CasoAsignacion.caso_id == caso.id,
            CasoAsignacion.usuario_id == usuario_id,
            CasoAsignacion.hasta.is_(None),
        )
    ).scalar_one_or_none()
    if ya is not None:
        raise HTTPException(status.HTTP_409_CONFLICT, "Ese usuario ya está asignado al caso.")
    a = CasoAsignacion(caso_id=caso.id, usuario_id=usuario_id, asignado_por=ctx.id, motivo=motivo)
    db.add(a)
    db.flush()
    audit.registrar(
        db, ctx, "asignar", "caso", caso.id, caso.persona_id,
        {"usuario": usuario.usuario, "motivo": motivo},
    )
    return a


@router.get("/casos")
def listar_casos(
    estado: str | None = Query(None),
    asignados_a_mi: bool = False,
    persona_id: uuid.UUID | None = None,
    q: str = Query("", max_length=200),
    limite: int = Query(50, ge=1, le=200),
    ctx: Contexto = Depends(contexto),
    db: Session = Depends(get_db),
):
    alcance = ctx.requerir("casos", "consultar")
    consulta = (
        select(Caso, Persona)
        .join(Persona, Persona.id == Caso.persona_id)
        .where(filtro_casos(ctx, alcance))
    )
    if estado:
        consulta = consulta.where(Caso.estado == estado)
    if persona_id:
        consulta = consulta.where(Caso.persona_id == persona_id)
    if asignados_a_mi:
        consulta = consulta.where(
            Caso.id.in_(
                select(CasoAsignacion.caso_id).where(
                    CasoAsignacion.usuario_id == ctx.id, CasoAsignacion.hasta.is_(None)
                )
            )
        )
    if q.strip():
        t = normalizar(q)
        consulta = consulta.where(
            (Caso.numero == q.strip().upper())
            | Persona.apellidos_norm.like("%" + escapar_like(t) + "%")
            | Persona.nombres_norm.like("%" + escapar_like(t) + "%")
        )
    consulta = consulta.order_by(Caso.ultima_actividad.desc()).limit(limite)
    return [caso_out(c, ve_caso_reservado(db, ctx, c), p) for c, p in db.execute(consulta).all()]


@router.post("/casos", status_code=201)
def crear_caso(datos: CasoIn, ctx: Contexto = Depends(contexto), db: Session = Depends(get_db)):
    alcance = ctx.requerir("casos", "crear")
    persona = obtener_persona(db, datos.persona_id)
    requerir_persona(db, ctx, persona, "personas", "consultar")

    area_id = datos.area_id if datos.area_id is not None else ctx.usuario.area_id
    if area_id is not None:
        area = db.get(Area, area_id)
        if area is None or not area.activo:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, "Área inválida.")
    if alcance == "area" and area_id != ctx.usuario.area_id:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Solo puede crear casos de su área.")

    fecha_ingreso = datos.fecha_ingreso or ahora().astimezone().date()
    anio_caso = datos.anio_actuacion or fecha_ingreso.year

    # Una actuación por persona por año: si ya tiene caso en el año, la nueva
    # demanda se trabaja en ese caso (no se arma otra carátula).
    existente = db.execute(
        select(Caso).where(Caso.persona_id == persona.id, Caso.anio_actuacion == anio_caso)
    ).scalars().first()
    if existente is not None:
        if not datos.forzar_otra_actuacion:
            raise HTTPException(
                status.HTTP_409_CONFLICT,
                {
                    "mensaje": (
                        f"{persona.apellidos}, {persona.nombres} ya tiene la actuación "
                        f"N° {existente.numero_actuacion}/{anio_caso}. La nueva demanda se registra en ese caso."
                    ),
                    "caso_existente": {
                        "id": str(existente.id),
                        "numero": existente.numero,
                        "estado": existente.estado,
                        "numero_actuacion": existente.numero_actuacion,
                        "anio_actuacion": existente.anio_actuacion,
                    },
                },
            )
        if ctx.alcance("administracion", "administrar") is None or not datos.motivo_forzado:
            raise HTTPException(
                status.HTTP_403_FORBIDDEN,
                "Solo Administración puede abrir otra actuación en el mismo año, indicando el motivo.",
            )

    if datos.numero_actuacion is not None:
        # Carátula cargada con su número original (por ejemplo, de papel).
        anio = datos.anio_actuacion or fecha_ingreso.year
        n = datos.numero_actuacion
        numero = formato_caso(anio, n)
        if db.execute(select(Caso.id).where(Caso.numero == numero)).first() is not None:
            raise HTTPException(status.HTTP_409_CONFLICT, f"Ya existe la actuación N° {n}/{anio}.")
    else:
        anio, n, numero = nueva_actuacion(db, datos.anio_actuacion or fecha_ingreso.year)
    caso = Caso(
        numero=numero,
        numero_actuacion=n,
        anio_actuacion=anio,
        persona_id=persona.id,
        area_id=area_id,
        estado="abierto",
        reservado=datos.reservado,
        creado_por=ctx.id,
    )
    db.add(caso)
    caratula = datos.model_dump(
        exclude_unset=True,
        exclude={
            "persona_id", "area_id", "reservado", "responsable_id", "ingreso_id", "numero_actuacion",
            "anio_actuacion", "forzar_otra_actuacion", "motivo_forzado",
        },
    )
    if caratula.get("persona") is not None:
        caratula["persona"] = datos.persona.model_dump(exclude_unset=True)
    caratula.setdefault("fecha_ingreso", ahora().astimezone().date())
    if "antecedentes" not in caratula or "fecha_ultimo_ingreso" not in caratula:
        tiene, ultima = antecedentes_sistema(db, persona.id, antes_de=caratula["fecha_ingreso"])
        caratula.setdefault("antecedentes", tiene)
        caratula.setdefault("fecha_ultimo_ingreso", ultima)
    aplicar_caratula(db, ctx, caso, persona, caratula)
    db.flush()
    db.add(CasoEstadoHistorial(caso_id=caso.id, estado_anterior=None, estado_nuevo="abierto", usuario_id=ctx.id))
    audit.registrar(
        db, ctx, "crear", "caso", caso.id, persona.id,
        {
            "numero": caso.numero, "reservado": caso.reservado, "area_id": area_id,
            "tipo_ingreso": caso.tipo_ingreso, "indicadores": caso.indicadores,
            "otra_actuacion_en_el_anio": (
                {"existente": existente.numero, "motivo": datos.motivo_forzado} if existente is not None else None
            ),
        },
    )

    if datos.responsable_id is not None:
        ctx.requerir("casos", "derivar")
        _asignar(db, ctx, caso, datos.responsable_id, "Asignación inicial")

    if datos.ingreso_id is not None:
        ingreso = db.get(Ingreso, datos.ingreso_id)
        if ingreso is None:
            raise no_encontrado("Ingreso")
        if ingreso.persona_id not in (None, persona.id):
            raise HTTPException(status.HTTP_400_BAD_REQUEST, "El ingreso pertenece a otro legajo.")
        ingreso.persona_id = persona.id
        ingreso.caso_id = caso.id
        ingreso.vinculado_por = ctx.id
        ingreso.vinculado_en = ahora()
        audit.registrar(db, ctx, "vincular", "ingreso", ingreso.id, persona.id, {"caso": caso.numero})

    db.commit()
    db.refresh(caso)
    return caso_out(caso, True, persona, detalle=True)


@router.get("/casos/{caso_id}")
def ver_caso(caso_id: uuid.UUID, ctx: Contexto = Depends(contexto), db: Session = Depends(get_db)):
    caso = obtener_caso(db, caso_id)
    requerir_caso(db, ctx, caso, "casos", "consultar")
    visible = ve_caso_reservado(db, ctx, caso)
    persona = db.get(Persona, caso.persona_id)
    r = caso_out(caso, visible, persona, detalle=True)
    r["persona"] = persona_detalle(persona)
    tiene, ultima = antecedentes_sistema(db, persona.id, excluir_caso_id=caso.id,
                                         antes_de=caso.fecha_ingreso or caso.abierto_en.date())
    r["antecedentes_sistema"] = {"tiene": tiene, "fecha_ultimo_ingreso": ultima.isoformat() if ultima else None}
    r["evoluciones"] = []
    r["demandas"] = []
    r["reiteraciones"] = [
        reiteracion_out(x) if visible else {"id": x.id, "fecha": x.fecha.isoformat()}
        for x in db.execute(
            select(Reiteracion).where(Reiteracion.caso_id == caso.id).order_by(Reiteracion.fecha)
        ).scalars()
    ]
    if visible:
        r["evoluciones"] = [
            evolucion_out(e)
            for e in db.execute(
                select(CasoEvolucion)
                .where(CasoEvolucion.caso_id == caso.id)
                .order_by(CasoEvolucion.fecha, CasoEvolucion.en)
            ).scalars()
        ]
    demandas = list(
        db.execute(
            select(RegistroDemanda).where(RegistroDemanda.caso_id == caso.id).order_by(RegistroDemanda.fecha)
        ).scalars()
    )
    escaneos = escaneos_de(db, ctx, [d.id for d in demandas]) if visible else {}
    r["demandas"] = [demanda_out(d, visible, escaneos.get(d.id)) for d in demandas]

    r["expedientes"] = []
    if ctx.tiene("expedientes", "consultar"):
        r["expedientes"] = [
            expediente_out(e, visible)
            for e in db.execute(select(Expediente).where(Expediente.caso_id == caso.id)).scalars()
        ]
    r["documentos"] = []
    if visible and ctx.tiene("documentos", "consultar"):
        q = (
            select(Documento, Usuario)
            .outerjoin(Usuario, Usuario.id == Documento.cargado_por)
            .where(Documento.caso_id == caso.id, Documento.eliminado_en.is_(None))
            .order_by(Documento.cargado_en.desc())
        )
        for d, u in db.execute(q).all():
            ve = not (d.reservado or d.tipo_documental.reservado) or ve_reservado_de_persona(
                db, ctx, caso.persona_id, caso.id
            )
            r["documentos"].append(documento_out(d, ve, u))
    r["ingresos"] = [
        ingreso_out(i) for i in db.execute(select(Ingreso).where(Ingreso.caso_id == caso.id)).scalars()
    ]
    r["permisos"] = {
        "modificar": _puede(db, ctx, caso, "modificar"),
        "derivar": _puede(db, ctx, caso, "derivar"),
    }
    audit.registrar(db, ctx, "consultar_caso", "caso", caso.id, caso.persona_id)
    db.commit()
    return r


def _puede(db: Session, ctx: Contexto, caso: Caso, accion: str) -> bool:
    try:
        requerir_caso(db, ctx, caso, "casos", accion)
        return True
    except HTTPException:
        return False


@router.patch("/casos/{caso_id}")
def modificar_caso(
    caso_id: uuid.UUID, datos: CasoPatch, ctx: Contexto = Depends(contexto), db: Session = Depends(get_db)
):
    caso = obtener_caso(db, caso_id)
    requerir_caso(db, ctx, caso, "casos", "modificar")
    if not ve_caso_reservado(db, ctx, caso):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Caso reservado.")
    cambios_pedidos = datos.model_dump(exclude_unset=True)
    if "area_id" in cambios_pedidos and cambios_pedidos["area_id"] is not None:
        if db.get(Area, cambios_pedidos["area_id"]) is None:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, "Área inválida.")
    diff = audit.cambios(caso, cambios_pedidos)
    if diff:
        registrar_actividad_caso(caso)
        audit.registrar(db, ctx, "modificar", "caso", caso.id, caso.persona_id, {"cambios": diff})
        db.commit()
        db.refresh(caso)
    return caso_out(caso, True, db.get(Persona, caso.persona_id), detalle=True)


@router.patch("/casos/{caso_id}/caratula")
def modificar_caratula(
    caso_id: uuid.UUID, datos: CaratulaCampos, ctx: Contexto = Depends(contexto), db: Session = Depends(get_db)
):
    caso = obtener_caso(db, caso_id)
    requerir_caso(db, ctx, caso, "casos", "modificar")
    if not ve_caso_reservado(db, ctx, caso):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Caso reservado.")
    persona = db.get(Persona, caso.persona_id)
    cambios_pedidos = datos.model_dump(exclude_unset=True)
    for campo in ("numero_actuacion", "anio_actuacion"):
        if campo in cambios_pedidos and cambios_pedidos.pop(campo) != getattr(caso, campo):
            raise HTTPException(status.HTTP_400_BAD_REQUEST, "El número de actuación no se modifica.")
    if datos.persona is not None:
        cambios_pedidos["persona"] = datos.persona.model_dump(exclude_unset=True)
    diff = aplicar_caratula(db, ctx, caso, persona, cambios_pedidos)
    if diff:
        registrar_actividad_caso(caso)
        audit.registrar(db, ctx, "modificar_caratula", "caso", caso.id, caso.persona_id, {"cambios": diff})
    db.commit()
    db.refresh(caso)
    return caso_out(caso, True, persona, detalle=True)


def registrar_reiteracion(
    db: Session, ctx: Contexto, caso: Caso, *, fecha, motivo=None, ingreso_id=None, reabrir=True, **ingreso_datos
) -> Reiteracion:
    validar_ingreso({k: v for k, v in ingreso_datos.items() if k in ("tipo_ingreso", "tipo_ingreso_detalle", "derivado_por")})
    r = Reiteracion(
        caso_id=caso.id, fecha=fecha, motivo=motivo, ingreso_id=ingreso_id, usuario_id=ctx.id,
        **{k: v for k, v in ingreso_datos.items() if v is not None},
    )
    db.add(r)
    if caso.estado == "cerrado" and reabrir:
        db.add(CasoEstadoHistorial(
            caso_id=caso.id, estado_anterior="cerrado", estado_nuevo="abierto",
            motivo="Reiteración" + (f": {motivo}" if motivo else ""), usuario_id=ctx.id,
        ))
        caso.estado = "abierto"
        caso.cerrado_en = None
    registrar_actividad_caso(caso)
    db.flush()
    audit.registrar(
        db, ctx, "reiteracion", "caso", caso.id, caso.persona_id,
        {"fecha": fecha, "ingreso_id": ingreso_id, "reabierto": caso.estado == "abierto" and reabrir},
    )
    return r


@router.post("/casos/{caso_id}/reiteraciones", status_code=201)
def nueva_reiteracion(
    caso_id: uuid.UUID, datos: ReiteracionIn, ctx: Contexto = Depends(contexto), db: Session = Depends(get_db)
):
    caso = obtener_caso(db, caso_id)
    requerir_caso(db, ctx, caso, "casos", "modificar")
    if not ve_caso_reservado(db, ctx, caso):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Caso reservado.")
    valores = datos.model_dump(exclude={"fecha", "reabrir", "motivo"})
    r = registrar_reiteracion(
        db, ctx, caso, fecha=datos.fecha or ahora().astimezone().date(), motivo=datos.motivo,
        reabrir=datos.reabrir, **valores,
    )
    db.commit()
    db.refresh(r)
    return reiteracion_out(r)


@router.post("/casos/{caso_id}/evolucion", status_code=201)
def agregar_evolucion(
    caso_id: uuid.UUID, datos: EvolucionIn, ctx: Contexto = Depends(contexto), db: Session = Depends(get_db)
):
    caso = obtener_caso(db, caso_id)
    requerir_caso(db, ctx, caso, "casos", "modificar")
    if not ve_caso_reservado(db, ctx, caso):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Caso reservado.")
    if datos.autor_id is not None and db.get(Usuario, datos.autor_id) is None:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Autor inexistente.")
    e = CasoEvolucion(
        caso_id=caso.id,
        texto=datos.texto,
        fecha=datos.fecha or ahora().astimezone().date(),
        autor_id=datos.autor_id or (None if datos.autor_nombre else ctx.id),
        autor_nombre=None if datos.autor_id else datos.autor_nombre,
        usuario_id=ctx.id,
    )
    db.add(e)
    registrar_actividad_caso(caso)
    db.flush()
    audit.registrar(db, ctx, "evolucion", "caso", caso.id, caso.persona_id, {"evolucion_id": e.id})
    db.commit()
    db.refresh(e)
    return evolucion_out(e)


@router.post("/casos/{caso_id}/estado")
def cambiar_estado(
    caso_id: uuid.UUID,
    datos: CambioEstadoIn,
    ctx: Contexto = Depends(contexto),
    db: Session = Depends(get_db),
):
    caso = obtener_caso(db, caso_id)
    requerir_caso(db, ctx, caso, "casos", "modificar")
    if datos.estado == caso.estado:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "El caso ya está en ese estado.")
    reapertura = caso.estado == "cerrado"
    if (datos.estado in TRANSICIONES_CON_MOTIVO or reapertura) and not datos.motivo:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            "Indique el motivo para pausar, cerrar o reabrir un caso.",
        )
    anterior = caso.estado
    caso.estado = datos.estado
    caso.cerrado_en = ahora() if datos.estado == "cerrado" else None
    registrar_actividad_caso(caso)
    db.add(
        CasoEstadoHistorial(
            caso_id=caso.id,
            estado_anterior=anterior,
            estado_nuevo=datos.estado,
            motivo=datos.motivo,
            usuario_id=ctx.id,
        )
    )
    audit.registrar(
        db, ctx, "reabrir" if reapertura else "cambiar_estado", "caso", caso.id, caso.persona_id,
        {"de": anterior, "a": datos.estado},
    )
    db.commit()
    db.refresh(caso)
    return caso_out(caso, ve_caso_reservado(db, ctx, caso), db.get(Persona, caso.persona_id), detalle=True)


@router.post("/casos/{caso_id}/asignaciones", status_code=201)
def asignar(
    caso_id: uuid.UUID, datos: AsignacionIn, ctx: Contexto = Depends(contexto), db: Session = Depends(get_db)
):
    caso = obtener_caso(db, caso_id)
    requerir_caso(db, ctx, caso, "casos", "derivar")
    if datos.reemplazar_actuales:
        for a in caso.asignaciones:
            if a.hasta is None and a.usuario_id != datos.usuario_id:
                a.hasta = ahora()
                a.finalizado_por = ctx.id
                audit.registrar(
                    db, ctx, "finalizar_asignacion", "caso", caso.id, caso.persona_id,
                    {"usuario": a.usuario.usuario, "motivo": "Reasignación"},
                )
    _asignar(db, ctx, caso, datos.usuario_id, datos.motivo)
    registrar_actividad_caso(caso)
    db.commit()
    db.refresh(caso)
    return caso_out(caso, ve_caso_reservado(db, ctx, caso), db.get(Persona, caso.persona_id), detalle=True)


@router.post("/casos/{caso_id}/asignaciones/{asignacion_id}/finalizar")
def finalizar_asignacion(
    caso_id: uuid.UUID,
    asignacion_id: int,
    datos: FinAsignacionIn,
    ctx: Contexto = Depends(contexto),
    db: Session = Depends(get_db),
):
    caso = obtener_caso(db, caso_id)
    requerir_caso(db, ctx, caso, "casos", "derivar")
    a = db.get(CasoAsignacion, asignacion_id)
    if a is None or a.caso_id != caso.id:
        raise no_encontrado("Asignación")
    if a.hasta is not None:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "La asignación ya estaba finalizada.")
    a.hasta = ahora()
    a.finalizado_por = ctx.id
    registrar_actividad_caso(caso)
    audit.registrar(
        db, ctx, "finalizar_asignacion", "caso", caso.id, caso.persona_id,
        {"usuario": a.usuario.usuario, "motivo": datos.motivo},
    )
    db.commit()
    db.refresh(caso)
    return caso_out(caso, ve_caso_reservado(db, ctx, caso), db.get(Persona, caso.persona_id), detalle=True)


@router.get("/tablero")
def tablero(ctx: Contexto = Depends(contexto), db: Session = Depends(get_db)):
    mis_casos = []
    sin_actividad = []
    if ctx.tiene("casos", "consultar"):
        asignados = select(CasoAsignacion.caso_id).where(
            CasoAsignacion.usuario_id == ctx.id, CasoAsignacion.hasta.is_(None)
        )
        q = (
            select(Caso, Persona)
            .join(Persona, Persona.id == Caso.persona_id)
            .where(Caso.id.in_(asignados), Caso.estado != "cerrado")
            .order_by(Caso.ultima_actividad.asc())
        )
        limite = ahora() - timedelta(days=DIAS_SIN_ACTIVIDAD)
        for c, p in db.execute(q).all():
            out = caso_out(c, True, p)
            mis_casos.append(out)
            if c.ultima_actividad < limite:
                sin_actividad.append(out)

    ingresos_pendientes = None
    if ctx.tiene("mesa_entrada", "consultar"):
        ingresos_pendientes = db.execute(
            select(func.count(Ingreso.id)).where(Ingreso.persona_id.is_(None))
        ).scalar_one()

    resumen_estados = {}
    if ctx.tiene("casos", "consultar"):
        alcance = ctx.alcance("casos", "consultar")
        filas = db.execute(
            select(Caso.estado, func.count(Caso.id))
            .where(filtro_casos(ctx, alcance))
            .group_by(Caso.estado)
        ).all()
        resumen_estados = {estado: n for estado, n in filas}

    return {
        "mis_casos": mis_casos,
        "sin_actividad": sin_actividad,
        "dias_sin_actividad": DIAS_SIN_ACTIVIDAD,
        "ingresos_pendientes": ingresos_pendientes,
        "resumen_estados": resumen_estados,
    }

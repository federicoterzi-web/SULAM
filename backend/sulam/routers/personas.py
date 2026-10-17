from __future__ import annotations

import uuid
from typing import Literal

from pydantic import BaseModel

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import and_, or_, select, update
from sqlalchemy.orm import Session

from .. import audit, filtros
from ..db import get_db
from ..deps import contexto
from ..duplicates import Coincidencia, buscar_posibles_duplicados
from ..formularios import validar_datos_persona
from ..models import (
    Auditoria,
    Caso,
    Documento,
    Expediente,
    Ingreso,
    Persona,
    PersonaVinculada,
    RegistroDemanda,
    TipoVinculo,
    Usuario,
)
from ..numbering import legajo_de_documento, legajo_provisorio, numero_legajo
from ..permissions import (
    Contexto,
    filtro_casos,
    filtro_personas,
    requerir_persona,
)
from ..schemas import (
    PersonaIn,
    PersonaPatch,
    UnificarIn,
    VerificarDuplicadosIn,
    VinculadoIn,
    VinculadoPatch,
)
from ..security import ahora
from ..serializers import (
    caso_out,
    documento_out,
    expediente_out,
    ingreso_out,
    persona_detalle,
    persona_resumen,
    vinculado_out,
)
from ..textutil import escapar_like, normalizar, normalizar_documento
from ._comun import no_encontrado, obtener_persona

router = APIRouter(tags=["legajos"])


def _coincidencias_out(coincidencias: list[Coincidencia]) -> list[dict]:
    return [
        {
            "persona": persona_resumen(c.persona),
            "nivel": c.nivel,
            "motivos": c.motivos,
        }
        for c in coincidencias
    ]


def _validar_documento(tipo: str | None, numero: str | None, sin_documento: bool) -> tuple[str | None, str | None]:
    numero = normalizar_documento(numero)
    if sin_documento and numero:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            "Si la persona figura sin documento no puede cargarse un número.",
        )
    if numero and not tipo:
        tipo = "DNI"
    if not numero:
        tipo = None
    return tipo, numero


def _controlar_duplicados(
    db: Session,
    *,
    apellidos: str,
    nombres: str,
    tipo: str | None,
    numero: str | None,
    fecha,
    aproximada: bool,
    confirmar: bool,
    excluir_id=None,
) -> list[Coincidencia]:
    coincidencias = buscar_posibles_duplicados(
        db,
        apellidos=apellidos,
        nombres=nombres,
        tipo_documento=tipo,
        numero_documento=numero,
        fecha_nacimiento=fecha,
        fecha_aproximada=aproximada,
        excluir_id=excluir_id,
    )
    bloqueantes = [c for c in coincidencias if c.nivel == "bloqueante"]
    if bloqueantes:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            {
                "mensaje": "Ya existe un legajo con ese documento.",
                "bloqueante": True,
                "coincidencias": _coincidencias_out(bloqueantes),
            },
        )
    if coincidencias and not confirmar:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            {
                "mensaje": "Hay legajos que podrían corresponder a la misma persona. "
                "Revíselos antes de continuar.",
                "bloqueante": False,
                "requiere_confirmacion": True,
                "coincidencias": _coincidencias_out(coincidencias),
            },
        )
    return coincidencias


# ---------------------------------------------------------------- búsqueda y alta


@router.get("/personas")
def listar_personas(
    q: str = Query("", max_length=200),
    f: str | None = Query(None, max_length=20000),
    limite: int = Query(30, ge=1, le=500),
    con_total: bool = False,
    ctx: Contexto = Depends(contexto),
    db: Session = Depends(get_db),
):
    alcance = ctx.requerir("personas", "consultar")
    consulta = select(Persona).where(Persona.unificada_en_id.is_(None), filtro_personas(ctx, alcance))
    texto = normalizar(q)
    doc = normalizar_documento(q)
    if texto or doc:
        condiciones = []
        if doc:
            condiciones.append(Persona.numero_documento == doc)
            condiciones.append(Persona.numero_legajo == q.strip().upper())
            condiciones.append(Persona.legajo_provisorio == q.strip().upper())
        palabras = texto.split()
        if palabras:
            por_palabra = [
                or_(
                    Persona.apellidos_norm.like("%" + escapar_like(p) + "%"),
                    Persona.nombres_norm.like("%" + escapar_like(p) + "%"),
                )
                for p in palabras
            ]
            condiciones.append(and_(*por_palabra))
        consulta = consulta.where(or_(*condiciones))
        audit.registrar(db, ctx, "busqueda", "persona", detalle={"q": q[:200]})
        db.commit()
    consulta = filtros.aplicar("legajos", consulta, f)
    if f:
        audit.registrar(db, ctx, "filtro", "persona", detalle={"campos": filtros.resumen(f)})
        db.commit()
    cantidad = filtros.total(db, consulta) if con_total else None
    consulta = consulta.order_by(Persona.apellidos_norm, Persona.nombres_norm).limit(limite)
    items = [persona_resumen(p) for p in db.execute(consulta).scalars()]
    return {"total": cantidad, "items": items} if con_total else items


@router.post("/personas/verificar-duplicados")
def verificar_duplicados(
    datos: VerificarDuplicadosIn, ctx: Contexto = Depends(contexto), db: Session = Depends(get_db)
):
    if not (ctx.tiene("personas", "crear") or ctx.tiene("personas", "modificar")):
        ctx.requerir("personas", "crear")
    tipo, numero = _validar_documento(datos.tipo_documento, datos.numero_documento, False)
    coincidencias = buscar_posibles_duplicados(
        db,
        apellidos=datos.apellidos,
        nombres=datos.nombres,
        tipo_documento=tipo,
        numero_documento=numero,
        fecha_nacimiento=datos.fecha_nacimiento,
        fecha_aproximada=datos.fecha_nacimiento_aproximada,
        excluir_id=datos.excluir_id,
    )
    return {"coincidencias": _coincidencias_out(coincidencias)}


@router.post("/personas", status_code=201)
def crear_persona(datos: PersonaIn, ctx: Contexto = Depends(contexto), db: Session = Depends(get_db)):
    ctx.requerir("personas", "crear")
    tipo, numero = _validar_documento(datos.tipo_documento, datos.numero_documento, datos.sin_documento)
    coincidencias = _controlar_duplicados(
        db,
        apellidos=datos.apellidos,
        nombres=datos.nombres,
        tipo=tipo,
        numero=numero,
        fecha=datos.fecha_nacimiento,
        aproximada=datos.fecha_nacimiento_aproximada,
        confirmar=datos.confirmar_posible_duplicado,
    )
    valores = datos.model_dump(exclude={"confirmar_posible_duplicado", "motivo_confirmacion"})
    valores.update(tipo_documento=tipo, numero_documento=numero)
    validar_datos_persona(valores)
    persona = Persona(
        **valores,
        numero_legajo=numero_legajo(db, tipo, numero),
        legajo_provisorio=None,
        apellidos_norm=normalizar(datos.apellidos),
        nombres_norm=normalizar(datos.nombres),
        creado_por=ctx.id,
    )
    if persona.numero_legajo.startswith("SD-"):
        persona.legajo_provisorio = persona.numero_legajo
    db.add(persona)
    db.flush()
    detalle = {"numero_legajo": persona.numero_legajo}
    if coincidencias:
        detalle["posibles_duplicados_confirmados"] = [
            {"legajo": c.persona.numero_legajo, "nivel": c.nivel} for c in coincidencias
        ]
        detalle["motivo_confirmacion"] = datos.motivo_confirmacion
    audit.registrar(db, ctx, "crear", "persona", persona.id, persona.id, detalle)
    db.commit()
    return persona_detalle(persona)


# ---------------------------------------------------------------- legajo


@router.get("/personas/{persona_id}")
def ver_legajo(persona_id: uuid.UUID, ctx: Contexto = Depends(contexto), db: Session = Depends(get_db)):
    persona = obtener_persona(db, persona_id)
    requerir_persona(db, ctx, persona, "personas", "consultar")

    resultado = persona_detalle(persona)
    resultado["permisos"] = {
        "modificar": _puede(db, ctx, persona, "personas", "modificar"),
        "crear_caso": ctx.tiene("casos", "crear"),
        "crear_expediente": ctx.tiene("expedientes", "crear"),
        "cargar_documento": _puede(db, ctx, persona, "documentos", "crear"),
        "unificar": ctx.alcance("personas", "administrar") == "todos",
    }

    casos: list[dict] = []
    if ctx.tiene("casos", "consultar"):
        alcance = ctx.alcance("casos", "consultar")
        q = (
            select(Caso)
            .where(Caso.persona_id == persona.id, filtro_casos(ctx, alcance))
            .order_by(Caso.abierto_en.desc())
        )
        for c in db.execute(q).scalars():
            casos.append(caso_out(c))
    resultado["casos"] = casos

    expedientes: list[dict] = []
    if ctx.tiene("expedientes", "consultar"):
        q = select(Expediente).where(Expediente.persona_id == persona.id).order_by(Expediente.creado_en)
        expedientes = [expediente_out(e) for e in db.execute(q).scalars()]
    resultado["expedientes"] = expedientes

    q = (
        select(PersonaVinculada)
        .where(PersonaVinculada.persona_id == persona.id)
        .order_by(PersonaVinculada.activo.desc(), PersonaVinculada.creado_en)
    )
    resultado["vinculados"] = [
        vinculado_out(v) for v in db.execute(q).scalars()
    ]

    documentos: list[dict] = []
    if ctx.tiene("documentos", "consultar"):
        q = (
            select(Documento, Usuario)
            .outerjoin(Usuario, Usuario.id == Documento.cargado_por)
            .where(Documento.persona_id == persona.id, Documento.eliminado_en.is_(None))
            .order_by(Documento.cargado_en.desc())
        )
        for d, u in db.execute(q).all():
            documentos.append(documento_out(d, u))
    resultado["documentos"] = documentos

    q = select(Ingreso).where(Ingreso.persona_id == persona.id).order_by(Ingreso.fecha_ingreso.desc())
    resultado["ingresos"] = [ingreso_out(i) for i in db.execute(q).scalars()]

    audit.registrar(db, ctx, "consultar_legajo", "persona", persona.id, persona.id)
    db.commit()
    return resultado


def _puede(db: Session, ctx: Contexto, persona: Persona, modulo: str, accion: str) -> bool:
    try:
        requerir_persona(db, ctx, persona, modulo, accion)
        return True
    except HTTPException:
        return False


@router.patch("/personas/{persona_id}")
def modificar_persona(
    persona_id: uuid.UUID,
    datos: PersonaPatch,
    ctx: Contexto = Depends(contexto),
    db: Session = Depends(get_db),
):
    persona = obtener_persona(db, persona_id)
    requerir_persona(db, ctx, persona, "personas", "modificar")
    cambios_pedidos = datos.model_dump(
        exclude_unset=True, exclude={"motivo_cambio", "confirmar_posible_duplicado"}
    )
    validar_datos_persona(cambios_pedidos)
    for obligatorio in ("apellidos", "nombres"):
        if obligatorio in cambios_pedidos and not cambios_pedidos[obligatorio]:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, f"El campo {obligatorio} es obligatorio.")

    sin_doc = cambios_pedidos.get("sin_documento", persona.sin_documento)
    tipo = cambios_pedidos.get("tipo_documento", persona.tipo_documento)
    numero = cambios_pedidos.get("numero_documento", persona.numero_documento)
    if cambios_pedidos.get("sin_documento") is True and "numero_documento" not in cambios_pedidos:
        numero = None
    tipo, numero = _validar_documento(tipo, numero, sin_doc)
    if "tipo_documento" in cambios_pedidos or "numero_documento" in cambios_pedidos or "sin_documento" in cambios_pedidos:
        cambios_pedidos.update(tipo_documento=tipo, numero_documento=numero)

    identidad = {"apellidos", "nombres", "numero_documento", "tipo_documento", "fecha_nacimiento"}
    if identidad & cambios_pedidos.keys():
        _controlar_duplicados(
            db,
            apellidos=cambios_pedidos.get("apellidos", persona.apellidos),
            nombres=cambios_pedidos.get("nombres", persona.nombres),
            tipo=tipo,
            numero=numero,
            fecha=cambios_pedidos.get("fecha_nacimiento", persona.fecha_nacimiento),
            aproximada=cambios_pedidos.get(
                "fecha_nacimiento_aproximada", persona.fecha_nacimiento_aproximada
            ),
            confirmar=datos.confirmar_posible_duplicado,
            excluir_id=persona.id,
        )

    diff = audit.cambios(persona, cambios_pedidos)
    if not diff:
        return persona_detalle(persona)
    persona.apellidos_norm = normalizar(persona.apellidos)
    persona.nombres_norm = normalizar(persona.nombres)
    if {"numero_documento", "tipo_documento"} & diff.keys():
        nuevo = legajo_de_documento(persona.tipo_documento, persona.numero_documento)
        if nuevo is None:
            if not persona.legajo_provisorio:
                persona.legajo_provisorio = legajo_provisorio(db)
            nuevo = persona.legajo_provisorio
        if nuevo != persona.numero_legajo:
            diff["numero_legajo"] = [persona.numero_legajo, nuevo]
            persona.numero_legajo = nuevo
    if "numero_documento" in diff and diff["numero_documento"][0] and not datos.motivo_cambio:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            "Para corregir un número de documento existente indique el motivo del cambio.",
        )
    audit.registrar(
        db, ctx, "modificar", "persona", persona.id, persona.id,
        {"cambios": diff, "motivo": datos.motivo_cambio},
    )
    db.commit()
    return persona_detalle(persona)


class UbicacionIn(BaseModel):
    lat: float | None = None
    lng: float | None = None
    origen: Literal["mapa", "gps"] = "mapa"


@router.put("/personas/{persona_id}/ubicacion")
def ubicar_domicilio(
    persona_id: uuid.UUID,
    datos: UbicacionIn,
    ctx: Contexto = Depends(contexto),
    db: Session = Depends(get_db),
):
    """Ubicación del domicilio en el mapa (marcada a mano o con el GPS durante una visita)."""
    from .recursos import CAJA_TUCUMAN

    persona = obtener_persona(db, persona_id)
    requerir_persona(db, ctx, persona, "personas", "modificar")
    if (datos.lat is None) != (datos.lng is None):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Indique latitud y longitud, o ninguna.")
    if datos.lat is not None:
        c = CAJA_TUCUMAN
        if not (c["sur"] <= datos.lat <= c["norte"] and c["oeste"] <= datos.lng <= c["este"]):
            raise HTTPException(status.HTTP_400_BAD_REQUEST, "La ubicación queda fuera de la provincia de Tucumán.")
    persona.lat = round(datos.lat, 6) if datos.lat is not None else None
    persona.lng = round(datos.lng, 6) if datos.lng is not None else None
    persona.ubicacion_actualizada_en = ahora() if datos.lat is not None else None
    audit.registrar(
        db, ctx, "ubicar_domicilio" if datos.lat is not None else "quitar_ubicacion", "persona", persona.id, persona.id,
        {"origen": datos.origen},
    )
    db.commit()
    return persona_detalle(persona)


@router.post("/personas/{persona_id}/unificar")
def unificar(
    persona_id: uuid.UUID,
    datos: UnificarIn,
    ctx: Contexto = Depends(contexto),
    db: Session = Depends(get_db),
):
    """Unifica dos legajos: el legajo indicado en la URL se conserva y absorbe al otro."""
    if ctx.alcance("personas", "administrar") != "todos":
        raise HTTPException(
            status.HTTP_403_FORBIDDEN, "La unificación de legajos requiere un permiso especial."
        )
    destino = obtener_persona(db, persona_id)
    origen = obtener_persona(db, datos.legajo_a_absorber_id)
    if destino.id == origen.id:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "No puede unificarse un legajo consigo mismo.")

    movidos = {}
    for modelo, nombre in (
        (Caso, "casos"),
        (Expediente, "expedientes"),
        (Ingreso, "ingresos"),
        (Documento, "documentos"),
        (PersonaVinculada, "vinculados"),
        (RegistroDemanda, "registros_demanda"),
    ):
        r = db.execute(
            update(modelo).where(modelo.persona_id == origen.id).values(persona_id=destino.id)
        )
        movidos[nombre] = r.rowcount

    origen.unificada_en_id = destino.id
    origen.unificada_fecha = ahora()
    detalle = {
        "conservado": destino.numero_legajo,
        "absorbido": origen.numero_legajo,
        "motivo": datos.motivo,
        "movidos": movidos,
        "datos_absorbido": persona_detalle(origen),
    }
    audit.registrar(db, ctx, "unificar", "persona", destino.id, destino.id, detalle)
    audit.registrar(db, ctx, "unificado_en", "persona", origen.id, origen.id, detalle)
    db.commit()
    return {"conservado": persona_resumen(destino), "absorbido": persona_resumen(origen), "movidos": movidos}


@router.get("/personas/{persona_id}/actividad")
def actividad_legajo(
    persona_id: uuid.UUID,
    limite: int = Query(100, ge=1, le=500),
    ctx: Contexto = Depends(contexto),
    db: Session = Depends(get_db),
):
    """Historial básico del legajo. Las consultas de otros usuarios solo se
    muestran a quien tiene permiso de auditoría."""
    persona = obtener_persona(db, persona_id, permitir_unificada=True)
    requerir_persona(db, ctx, persona, "personas", "consultar")
    q = select(Auditoria).where(Auditoria.persona_id == persona.id)
    if not ctx.tiene("auditoria", "consultar"):
        q = q.where(~Auditoria.accion.like("consultar%"))
    q = q.order_by(Auditoria.en.desc()).limit(limite)
    return [_auditoria_out(a) for a in db.execute(q).scalars()]


def _auditoria_out(a: Auditoria) -> dict:
    return {
        "id": a.id,
        "en": a.en.isoformat(),
        "usuario": a.usuario.nombre_completo if a.usuario else "Sistema",
        "accion": a.accion,
        "entidad": a.entidad,
        "entidad_id": a.entidad_id,
        "detalle": a.detalle,
    }


# ---------------------------------------------------------------- personas vinculadas


@router.post("/personas/{persona_id}/vinculados", status_code=201)
def crear_vinculado(
    persona_id: uuid.UUID,
    datos: VinculadoIn,
    ctx: Contexto = Depends(contexto),
    db: Session = Depends(get_db),
):
    persona = obtener_persona(db, persona_id)
    requerir_persona(db, ctx, persona, "personas", "modificar")
    tipo = db.get(TipoVinculo, datos.tipo_vinculo_id)
    if tipo is None or not tipo.activo:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Tipo de vínculo inválido.")
    if datos.es_institucion and not datos.nombre_institucion:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Indique el nombre de la institución.")
    if not datos.es_institucion and not (datos.apellidos or datos.nombres):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Indique apellidos o nombres.")
    v = PersonaVinculada(**datos.model_dump(), persona_id=persona.id, creado_por=ctx.id)
    v.numero_documento = normalizar_documento(v.numero_documento)
    db.add(v)
    db.flush()
    db.refresh(v)
    audit.registrar(
        db, ctx, "crear", "vinculado", v.id, persona.id,
        {"tipo_vinculo": tipo.nombre},
    )
    db.commit()
    return vinculado_out(v)


@router.patch("/vinculados/{vinculado_id}")
def modificar_vinculado(
    vinculado_id: uuid.UUID,
    datos: VinculadoPatch,
    ctx: Contexto = Depends(contexto),
    db: Session = Depends(get_db),
):
    v = db.get(PersonaVinculada, vinculado_id)
    if v is None:
        raise no_encontrado("Persona vinculada")
    persona = obtener_persona(db, v.persona_id)
    requerir_persona(db, ctx, persona, "personas", "modificar")
    cambios_pedidos = datos.model_dump(exclude_unset=True)
    if "tipo_vinculo_id" in cambios_pedidos:
        tipo = db.get(TipoVinculo, cambios_pedidos["tipo_vinculo_id"])
        if tipo is None:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, "Tipo de vínculo inválido.")
    if "numero_documento" in cambios_pedidos:
        cambios_pedidos["numero_documento"] = normalizar_documento(cambios_pedidos["numero_documento"])
    diff = audit.cambios(v, cambios_pedidos)
    if diff:
        audit.registrar(
            db, ctx, "modificar", "vinculado", v.id, persona.id,
            diff,
        )
        db.commit()
        db.refresh(v)
    return vinculado_out(v)

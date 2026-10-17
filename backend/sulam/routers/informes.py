"""Informes redactados en SULAM y plantillas de informe.

Permisos:
- Ver un informe: consultar el caso (o el legajo, si no tiene caso).
- Redactar, corregir el borrador, firmarlo o abrir una nueva versión: modificar
  el caso (o el legajo). Quien puede escribir evoluciones puede hacer informes.
- Plantillas: módulo «plantillas». Con alcance «todos», todas; con «área», las
  de su área (y crear nuevas para su área).

Un informe firmado no cambia: su PDF queda entre los documentos del legajo.
Para corregirlo se abre una nueva versión (borrador) del mismo grupo; al
firmarla, la anterior queda como «reemplazada».
"""

from __future__ import annotations

import io
import uuid
from datetime import date, datetime

from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.responses import Response
from pydantic import BaseModel, Field, field_validator
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from .. import audit
from ..config import get_settings
from ..db import get_db
from ..deps import contexto
from ..informes import (
    CAMPOS,
    crear_plantillas_iniciales,
    datos_iniciales,
    generar_pdf,
    limpiar_html,
    ultima_demanda,
    valores_disponibles,
)
from ..models import (
    Area,
    Articulacion,
    Caso,
    CasoEvolucion,
    Documento,
    Informe,
    Persona,
    PlantillaInforme,
    TipoDocumental,
)
from ..permissions import Contexto, caso_en_alcance, persona_en_alcance, requerir_caso, requerir_persona
from ..schemas import Entrada, _vacio_a_none
from ..security import ahora
from ..serializers import usuario_breve
from ..storage import almacenamiento_actual
from ._comun import no_encontrado, obtener_caso, obtener_persona, registrar_actividad_caso

router = APIRouter(tags=["informes"])

MAX_HTML = 200_000


# ---------------------------------------------------------------- esquemas


class Dato(BaseModel):
    clave: str | None = Field(default=None, max_length=40)
    etiqueta: str = Field(max_length=200)
    valor: str = Field(default="", max_length=2000)


class SeccionIn(BaseModel):
    titulo: str = Field(default="", max_length=300)
    html: str = Field(default="", max_length=MAX_HTML)


class Firmante(BaseModel):
    nombre: str = Field(default="", max_length=200)
    cargo: str = Field(default="", max_length=200)


class InformeNuevo(Entrada):
    persona_id: uuid.UUID | None = None
    caso_id: uuid.UUID | None = None
    plantilla_id: int | None = None


class InformeIn(Entrada):
    titulo: str = Field(min_length=1, max_length=300)
    lugar: str | None = Field(default=None, max_length=200)
    fecha: date
    destinatario: str | None = Field(default=None, max_length=3000)
    datos: list[Dato] = Field(default_factory=list, max_length=60)
    secciones: list[SeccionIn] = Field(default_factory=list, max_length=60)
    firmantes: list[Firmante] = Field(default_factory=list, max_length=6)
    # Última versión que vio quien edita: si otra persona guardó después, no se pisa.
    actualizado_en: datetime | None = None

    _limpiar = field_validator("lugar", "destinatario", mode="before")(_vacio_a_none)


class SeccionPlantilla(BaseModel):
    titulo: str = Field(default="", max_length=300)
    guia: str = Field(default="", max_length=1000)
    texto: str = Field(default="", max_length=MAX_HTML)


class PlantillaIn(Entrada):
    nombre: str = Field(min_length=2, max_length=200)
    descripcion: str | None = Field(default=None, max_length=2000)
    area_id: int | None = None
    tipo_documental_id: int | None = None
    titulo: str = Field(default="", max_length=300)
    destinatario: bool = False
    destinatario_inicial: str = Field(default="", max_length=2000)
    numerar: bool = True
    datos: list[str] = Field(default_factory=list, max_length=40)
    secciones: list[SeccionPlantilla] = Field(default_factory=list, max_length=40)
    activo: bool = True
    orden: int = 0

    _limpiar = field_validator("descripcion", mode="before")(_vacio_a_none)

    @field_validator("datos")
    @classmethod
    def _datos(cls, v):
        desconocidos = [c for c in v if c not in CAMPOS]
        if desconocidos:
            raise ValueError(f"Datos desconocidos: {', '.join(desconocidos)}")
        return list(dict.fromkeys(v))


# ---------------------------------------------------------------- permisos


def _requerir(db: Session, ctx: Contexto, inf_persona: Persona, caso: Caso | None, accion: str) -> None:
    if caso is not None:
        requerir_caso(db, ctx, caso, "casos", accion)
    else:
        requerir_persona(db, ctx, inf_persona, "personas", accion)


def _puede(db: Session, ctx: Contexto, persona: Persona, caso: Caso | None, accion: str) -> bool:
    if caso is not None:
        alc = ctx.alcance("casos", accion)
        return alc is not None and caso_en_alcance(db, ctx, caso, alc)
    alc = ctx.alcance("personas", accion)
    return alc is not None and persona_en_alcance(db, ctx, persona, alc)


def _obtener(db: Session, informe_id: uuid.UUID) -> Informe:
    inf = db.get(Informe, informe_id)
    if inf is None or inf.estado == "descartado":
        raise no_encontrado("Informe")
    return inf


def _contexto_informe(db: Session, inf: Informe) -> tuple[Persona, Caso | None]:
    persona = db.get(Persona, inf.persona_id)
    caso = db.get(Caso, inf.caso_id) if inf.caso_id else None
    return persona, caso


# ---------------------------------------------------------------- salida


def _resumen(inf: Informe) -> dict:
    return {
        "id": str(inf.id),
        "grupo_id": str(inf.grupo_id),
        "version": inf.version,
        "titulo": inf.titulo,
        "fecha": inf.fecha.isoformat(),
        "estado": inf.estado,
        "caso_id": str(inf.caso_id) if inf.caso_id else None,
        "documento_id": str(inf.documento_id) if inf.documento_id else None,
        "firmado_en": inf.firmado_en.isoformat() if inf.firmado_en else None,
        "firmado_por": usuario_breve(inf.firmante_usuario),
        "autor": usuario_breve(inf.autor),
        "actualizado_en": inf.actualizado_en.isoformat(),
    }


def _plantilla_de(db: Session, inf: Informe) -> PlantillaInforme | None:
    return db.get(PlantillaInforme, inf.plantilla_id) if inf.plantilla_id else None


def _estructura(db: Session, inf: Informe) -> dict:
    p = _plantilla_de(db, inf)
    e = dict(p.estructura) if p else {}
    return {
        "destinatario": bool(e.get("destinatario") or inf.destinatario),
        "numerar": e.get("numerar", True),
        "mostrar_titulo": bool(e.get("titulo", "x")),
        # Guías de cada sección de la plantilla (ayuda mientras se escribe).
        "guias": {s["titulo"]: s.get("guia", "") for s in e.get("secciones", []) if s.get("guia")},
        "secciones_sugeridas": [s["titulo"] for s in e.get("secciones", []) if s.get("titulo")],
    }


def _informe_out(db: Session, ctx: Contexto, inf: Informe) -> dict:
    persona, caso = _contexto_informe(db, inf)
    r = _resumen(inf)
    puede_modificar = _puede(db, ctx, persona, caso, "modificar")
    versiones = db.execute(
        select(Informe)
        .where(Informe.grupo_id == inf.grupo_id, Informe.estado != "descartado")
        .order_by(Informe.version.desc())
    ).scalars().all()
    hay_borrador = any(v.estado == "borrador" for v in versiones)
    r.update(
        {
            "persona": {
                "id": str(persona.id),
                "nombres": persona.nombres,
                "apellidos": persona.apellidos,
                "numero_legajo": persona.numero_legajo,
            },
            "caso": (
                {
                    "id": str(caso.id),
                    "numero": caso.numero,
                    "numero_actuacion": caso.numero_actuacion,
                    "anio_actuacion": caso.anio_actuacion,
                    "area": caso.area.nombre if caso.area else None,
                }
                if caso
                else None
            ),
            "plantilla_id": inf.plantilla_id,
            "tipo_documental": {"id": inf.tipo_documental.id, "nombre": inf.tipo_documental.nombre} if inf.tipo_documental else None,
            "lugar": inf.lugar,
            "destinatario": inf.destinatario,
            "datos": inf.datos,
            "secciones": inf.secciones,
            "firmantes": inf.firmantes,
            "estructura": _estructura(db, inf),
            "versiones": [_resumen(v) for v in versiones],
            "permisos": {
                "modificar": puede_modificar and inf.estado == "borrador",
                "firmar": puede_modificar and inf.estado == "borrador",
                "nueva_version": puede_modificar and inf.estado == "firmado" and not hay_borrador,
                "descartar": puede_modificar and inf.estado == "borrador",
            },
        }
    )
    if inf.estado == "borrador":
        # Valores actuales del legajo para agregar datos o actualizarlos.
        valores = valores_disponibles(db, persona, caso, inf.fecha)
        r["datos_disponibles"] = [{"clave": c, "etiqueta": e, "valor": valores.get(c, "")} for c, e in CAMPOS.items()]
    return r


# ---------------------------------------------------------------- catálogo y listados


def _plantillas_visibles(db: Session, ctx: Contexto, todas: bool = False) -> list[PlantillaInforme]:
    q = select(PlantillaInforme)
    if not todas:
        q = q.where(PlantillaInforme.activo.is_(True))
    lista = list(db.execute(q.order_by(PlantillaInforme.orden, PlantillaInforme.nombre)).scalars())
    area = ctx.usuario.area_id
    # Primero las del área propia, después las generales y al final las de otras áreas.
    return sorted(lista, key=lambda p: (0 if p.area_id == area and area else 1 if p.area_id is None else 2, p.orden, p.nombre))


def _plantilla_out(p: PlantillaInforme, ctx: Contexto | None = None) -> dict:
    e = p.estructura or {}
    r = {
        "id": p.id,
        "nombre": p.nombre,
        "descripcion": p.descripcion,
        "area": {"id": p.area.id, "nombre": p.area.nombre} if p.area else None,
        "tipo_documental": {"id": p.tipo_documental.id, "nombre": p.tipo_documental.nombre} if p.tipo_documental else None,
        "titulo": e.get("titulo", ""),
        "destinatario": bool(e.get("destinatario")),
        "destinatario_inicial": e.get("destinatario_inicial", ""),
        "numerar": e.get("numerar", True),
        "datos": e.get("datos", []),
        "secciones": e.get("secciones", []),
        "activo": p.activo,
        "orden": p.orden,
        "actualizado_en": p.actualizado_en.isoformat(),
    }
    if ctx is not None:
        r["puede_editar"] = _puede_plantilla(ctx, p.area_id)
    return r


@router.get("/informes/catalogo")
def catalogo(ctx: Contexto = Depends(contexto), db: Session = Depends(get_db)):
    return {
        "campos": [{"clave": c, "etiqueta": e} for c, e in CAMPOS.items()],
        "plantillas": [_plantilla_out(p) for p in _plantillas_visibles(db, ctx)],
        "lugar": get_settings().lugar_informes,
    }


def _agrupar(informes: list[Informe]) -> list[dict]:
    grupos: dict[uuid.UUID, list[Informe]] = {}
    for i in informes:
        grupos.setdefault(i.grupo_id, []).append(i)
    salida = []
    for versiones in grupos.values():
        versiones.sort(key=lambda x: x.version, reverse=True)
        vigente = next((v for v in versiones if v.estado == "firmado"), None)
        borrador = next((v for v in versiones if v.estado == "borrador"), None)
        ultima = versiones[0]
        salida.append(
            {
                **_resumen(ultima),
                "vigente": _resumen(vigente) if vigente else None,
                "borrador": _resumen(borrador) if borrador else None,
                "cantidad_versiones": len(versiones),
            }
        )
    salida.sort(key=lambda g: g["actualizado_en"], reverse=True)
    return salida


@router.get("/casos/{caso_id}/informes")
def informes_del_caso(caso_id: uuid.UUID, ctx: Contexto = Depends(contexto), db: Session = Depends(get_db)):
    caso = obtener_caso(db, caso_id)
    requerir_caso(db, ctx, caso, "casos", "consultar")
    lista = db.execute(
        select(Informe).where(Informe.caso_id == caso.id, Informe.estado != "descartado")
    ).scalars().all()
    return _agrupar(list(lista))


@router.get("/personas/{persona_id}/informes")
def informes_de_la_persona(persona_id: uuid.UUID, ctx: Contexto = Depends(contexto), db: Session = Depends(get_db)):
    persona = obtener_persona(db, persona_id)
    requerir_persona(db, ctx, persona, "personas", "consultar")
    lista = list(
        db.execute(select(Informe).where(Informe.persona_id == persona.id, Informe.estado != "descartado")).scalars()
    )
    # Los de casos fuera del alcance de consulta no se muestran.
    alc = ctx.alcance("casos", "consultar")
    visibles = []
    for i in lista:
        if i.caso_id is None:
            visibles.append(i)
        elif alc is not None and caso_en_alcance(db, ctx, db.get(Caso, i.caso_id), alc):
            visibles.append(i)
    return _agrupar(visibles)


# ---------------------------------------------------------------- crear, ver, guardar


@router.post("/informes", status_code=201)
def crear_informe(entrada: InformeNuevo, ctx: Contexto = Depends(contexto), db: Session = Depends(get_db)):
    caso = obtener_caso(db, entrada.caso_id) if entrada.caso_id else None
    if caso is not None:
        persona = obtener_persona(db, caso.persona_id)
        if entrada.persona_id and entrada.persona_id != persona.id:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, "El caso no pertenece a este legajo.")
    elif entrada.persona_id:
        persona = obtener_persona(db, entrada.persona_id)
    else:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Indique el legajo o el caso del informe.")
    _requerir(db, ctx, persona, caso, "modificar")

    plantilla = None
    if entrada.plantilla_id is not None:
        plantilla = db.get(PlantillaInforme, entrada.plantilla_id)
        if plantilla is None or not plantilla.activo:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, "Plantilla inexistente o desactivada.")
    e = plantilla.estructura if plantilla else {"datos": ["nombre", "documento", "domicilio"], "secciones": [{"titulo": "", "texto": ""}]}
    hoy = ahora().date()
    valores = valores_disponibles(db, persona, caso, hoy)
    tipo_doc = plantilla.tipo_documental_id if plantilla else None
    if tipo_doc is None:
        tipo_doc = db.execute(select(TipoDocumental.id).where(TipoDocumental.nombre == "Otros documentos")).scalar()
    inf = Informe(
        grupo_id=uuid.uuid4(),
        version=1,
        persona_id=persona.id,
        caso_id=caso.id if caso else None,
        plantilla_id=plantilla.id if plantilla else None,
        tipo_documental_id=tipo_doc,
        titulo=(e.get("titulo") or (plantilla.nombre if plantilla else "Informe"))[:300],
        lugar=get_settings().lugar_informes,
        fecha=hoy,
        destinatario=(e.get("destinatario_inicial") or "") if e.get("destinatario") else None,
        datos=datos_iniciales(e.get("datos", []), valores),
        secciones=[{"titulo": s.get("titulo", ""), "html": limpiar_html(s.get("texto", ""))} for s in e.get("secciones", [])],
        firmantes=[{"nombre": ctx.usuario.nombre_completo, "cargo": ""}],
        estado="borrador",
        creado_por=ctx.id,
        actualizado_por=ctx.id,
    )
    db.add(inf)
    db.flush()
    audit.registrar(
        db, ctx, "crear", "informe", inf.id, persona.id,
        {"titulo": inf.titulo, "plantilla": plantilla.nombre if plantilla else None, "caso": caso.numero if caso else None},
    )
    db.commit()
    db.refresh(inf)
    return _informe_out(db, ctx, inf)


@router.get("/informes/{informe_id}")
def ver_informe(informe_id: uuid.UUID, ctx: Contexto = Depends(contexto), db: Session = Depends(get_db)):
    inf = _obtener(db, informe_id)
    persona, caso = _contexto_informe(db, inf)
    _requerir(db, ctx, persona, caso, "consultar")
    if inf.estado != "borrador":
        audit.registrar(db, ctx, "consultar", "informe", inf.id, persona.id)
        db.commit()
    return _informe_out(db, ctx, inf)


def _validar_borrador(db: Session, ctx: Contexto, inf: Informe) -> tuple[Persona, Caso | None]:
    persona, caso = _contexto_informe(db, inf)
    _requerir(db, ctx, persona, caso, "modificar")
    if inf.estado != "borrador":
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            "El informe ya está firmado y no se puede cambiar. Para corregirlo, abra una nueva versión.",
        )
    return persona, caso


@router.put("/informes/{informe_id}")
def guardar_informe(
    informe_id: uuid.UUID, entrada: InformeIn, ctx: Contexto = Depends(contexto), db: Session = Depends(get_db)
):
    inf = _obtener(db, informe_id)
    _validar_borrador(db, ctx, inf)
    if entrada.actualizado_en is not None and abs((inf.actualizado_en - entrada.actualizado_en).total_seconds()) > 0.001:
        quien = inf.actualizado_por and db.get(type(ctx.usuario), inf.actualizado_por)
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            {
                "mensaje": "Otra persona guardó cambios en este informe mientras usted lo editaba. "
                "Vuelva a abrirlo para ver la última versión.",
                "por": quien.nombre_completo if quien else None,
            },
        )
    inf.titulo = entrada.titulo
    inf.lugar = entrada.lugar
    inf.fecha = entrada.fecha
    inf.destinatario = entrada.destinatario
    inf.datos = [
        {"clave": d.clave if d.clave in CAMPOS else None, "etiqueta": d.etiqueta.strip(), "valor": d.valor.strip()}
        for d in entrada.datos
        if d.etiqueta.strip()
    ]
    inf.secciones = [{"titulo": s.titulo.strip(), "html": limpiar_html(s.html)} for s in entrada.secciones]
    inf.firmantes = [{"nombre": f.nombre.strip(), "cargo": f.cargo.strip()} for f in entrada.firmantes if f.nombre.strip()]
    inf.actualizado_por = ctx.id
    inf.actualizado_en = ahora()
    db.commit()
    db.refresh(inf)
    return {"actualizado_en": inf.actualizado_en.isoformat(), "secciones": inf.secciones}


def _pdf(db: Session, inf: Informe, borrador: bool = False) -> bytes:
    persona, caso = _contexto_informe(db, inf)
    e = _estructura(db, inf)
    cfg = get_settings()
    leyenda = f"SULAM · {inf.titulo}" + (f" · versión {inf.version}" if inf.version > 1 else "")
    if borrador:
        leyenda = "BORRADOR SIN FIRMAR · " + leyenda
    area = caso.area.nombre if caso and caso.area else None
    if area is None and inf.autor and inf.autor.area_id:
        a = db.get(Area, inf.autor.area_id)
        area = a.nombre if a else None
    return generar_pdf(
        titulo=inf.titulo,
        mostrar_titulo=e["mostrar_titulo"],
        lugar=inf.lugar or cfg.lugar_informes,
        fecha=inf.fecha,
        destinatario=inf.destinatario if e["destinatario"] else None,
        datos=inf.datos,
        secciones=inf.secciones,
        numerar=e["numerar"],
        firmantes=inf.firmantes,
        area=area,
        pie=cfg.pie_informes,
        leyenda=leyenda,
    )


@router.get("/informes/{informe_id}/vista-previa")
def vista_previa(informe_id: uuid.UUID, ctx: Contexto = Depends(contexto), db: Session = Depends(get_db)):
    """PDF del borrador tal como quedaría al firmarlo (no se guarda)."""
    inf = _obtener(db, informe_id)
    persona, caso = _contexto_informe(db, inf)
    _requerir(db, ctx, persona, caso, "consultar")
    pdf = _pdf(db, inf, borrador=inf.estado == "borrador")
    return Response(
        pdf,
        media_type="application/pdf",
        headers={"Content-Disposition": 'inline; filename="vista-previa.pdf"', "Cache-Control": "no-store"},
    )


@router.post("/informes/{informe_id}/firmar")
def firmar_informe(informe_id: uuid.UUID, ctx: Contexto = Depends(contexto), db: Session = Depends(get_db)):
    inf = _obtener(db, informe_id)
    persona, caso = _validar_borrador(db, ctx, inf)
    if not inf.firmantes:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Indique quién firma el informe.")
    if not any((s.get("html") or "").strip() for s in inf.secciones):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "El informe está vacío.")
    pdf = _pdf(db, inf)
    guardado = almacenamiento_actual().guardar(io.BytesIO(pdf))
    tipo = inf.tipo_documental_id or db.execute(
        select(TipoDocumental.id).where(TipoDocumental.nombre == "Otros documentos")
    ).scalar()
    titulo = inf.titulo + (f" (versión {inf.version})" if inf.version > 1 else "")
    doc = Documento(
        persona_id=persona.id,
        caso_id=caso.id if caso else None,
        tipo_documental_id=tipo,
        titulo=titulo[:300],
        descripcion=f"Informe redactado en SULAM, firmado el {ahora():%d/%m/%Y}.",
        nombre_original=f"informe-{inf.fecha:%Y%m%d}-v{inf.version}.pdf",
        mime="application/pdf",
        tamano=guardado.tamano,
        sha256=guardado.sha256,
        almacenamiento=almacenamiento_actual().nombre,
        clave_almacenamiento=guardado.clave,
        cargado_por=ctx.id,
    )
    db.add(doc)
    db.flush()
    anteriores = db.execute(
        select(Informe).where(Informe.grupo_id == inf.grupo_id, Informe.estado == "firmado", Informe.id != inf.id)
    ).scalars().all()
    for a in anteriores:
        a.estado = "reemplazado"
    inf.estado = "firmado"
    inf.documento_id = doc.id
    inf.firmado_en = ahora()
    inf.firmado_por = ctx.id
    if caso is not None:
        registrar_actividad_caso(caso)
    audit.registrar(
        db, ctx, "firmar", "informe", inf.id, persona.id,
        {"titulo": inf.titulo, "version": inf.version, "documento": str(doc.id), "sha256": doc.sha256,
         "reemplaza": [str(a.id) for a in anteriores]},
    )
    db.commit()
    db.refresh(inf)
    return _informe_out(db, ctx, inf)


@router.post("/informes/{informe_id}/nueva-version", status_code=201)
def nueva_version(informe_id: uuid.UUID, ctx: Contexto = Depends(contexto), db: Session = Depends(get_db)):
    inf = _obtener(db, informe_id)
    persona, caso = _contexto_informe(db, inf)
    _requerir(db, ctx, persona, caso, "modificar")
    existente = db.execute(
        select(Informe).where(Informe.grupo_id == inf.grupo_id, Informe.estado == "borrador")
    ).scalars().first()
    if existente is not None:
        return _informe_out(db, ctx, existente)
    if inf.estado not in ("firmado", "reemplazado"):
        raise HTTPException(status.HTTP_409_CONFLICT, "Solo se abren versiones nuevas de informes firmados.")
    ultima = db.execute(select(func.max(Informe.version)).where(Informe.grupo_id == inf.grupo_id)).scalar() or 0
    nuevo = Informe(
        grupo_id=inf.grupo_id,
        version=ultima + 1,
        persona_id=inf.persona_id,
        caso_id=inf.caso_id,
        plantilla_id=inf.plantilla_id,
        tipo_documental_id=inf.tipo_documental_id,
        titulo=inf.titulo,
        lugar=inf.lugar,
        fecha=ahora().date(),
        destinatario=inf.destinatario,
        datos=list(inf.datos),
        secciones=list(inf.secciones),
        firmantes=list(inf.firmantes),
        estado="borrador",
        creado_por=ctx.id,
        actualizado_por=ctx.id,
    )
    db.add(nuevo)
    db.flush()
    audit.registrar(db, ctx, "nueva_version", "informe", nuevo.id, persona.id, {"de": str(inf.id), "version": nuevo.version})
    db.commit()
    db.refresh(nuevo)
    return _informe_out(db, ctx, nuevo)


@router.post("/informes/{informe_id}/descartar")
def descartar(informe_id: uuid.UUID, ctx: Contexto = Depends(contexto), db: Session = Depends(get_db)):
    inf = _obtener(db, informe_id)
    persona, _ = _validar_borrador(db, ctx, inf)
    inf.estado = "descartado"
    inf.actualizado_por = ctx.id
    inf.actualizado_en = ahora()
    audit.registrar(db, ctx, "descartar", "informe", inf.id, persona.id, {"titulo": inf.titulo, "version": inf.version})
    db.commit()
    return {"ok": True}


@router.get("/informes/{informe_id}/fuentes")
def fuentes(informe_id: uuid.UUID, ctx: Contexto = Depends(contexto), db: Session = Depends(get_db)):
    """Textos ya cargados en SULAM que se pueden insertar en el informe."""
    inf = _obtener(db, informe_id)
    persona, caso = _contexto_informe(db, inf)
    _requerir(db, ctx, persona, caso, "consultar")
    salida: list[dict] = []
    if caso is not None:
        if caso.motivo:
            salida.append({"grupo": "Carátula", "titulo": "Motivo de ingreso", "texto": caso.motivo})
        d = ultima_demanda(db, persona, caso)
        if d is not None:
            for campo, titulo in (
                ("solicitud_expresa", "Solicitud expresa"),
                ("diagnosticos", "Diagnósticos referidos"),
                ("observaciones", "Observaciones"),
            ):
                if getattr(d, campo):
                    salida.append({"grupo": f"Registro de demanda del {d.fecha:%d/%m/%Y}", "titulo": titulo, "texto": getattr(d, campo)})
        for ev in db.execute(
            select(CasoEvolucion).where(CasoEvolucion.caso_id == caso.id).order_by(CasoEvolucion.fecha.desc(), CasoEvolucion.en.desc())
        ).scalars():
            f = ev.fecha or ev.en.date()
            autor = ev.autor_nombre or (ev.autor.nombre_completo if ev.autor else "")
            salida.append(
                {"grupo": "Evolución", "titulo": f"{f:%d/%m/%Y}" + (f" · {autor}" if autor else ""), "texto": ev.texto, "fecha": f.isoformat()}
            )
        for a in db.execute(
            select(Articulacion).where(Articulacion.caso_id == caso.id).order_by(Articulacion.fecha.desc())
        ).scalars():
            con = a.contacto.nombre if a.contacto else a.recurso.nombre if a.recurso else ""
            inst = a.contacto.institucion if a.contacto and a.contacto.institucion else ""
            texto = f"El {a.fecha:%d/%m/%Y} se articuló con {con}" + (f" ({inst})" if inst else "") + "."
            if a.motivo:
                texto += f" Motivo: {a.motivo}."
            if a.resultado:
                texto += f" Resultado: {a.resultado}."
            salida.append({"grupo": "Articulación", "titulo": f"{a.fecha:%d/%m/%Y} · {con}", "texto": texto, "fecha": a.fecha.isoformat()})
    if persona.observaciones:
        salida.append({"grupo": "Legajo", "titulo": "Observaciones del legajo", "texto": persona.observaciones})
    return salida


# ---------------------------------------------------------------- plantillas


def _puede_plantilla(ctx: Contexto, area_id: int | None) -> bool:
    alc = ctx.alcance("plantillas", "modificar")
    if alc == "todos":
        return True
    if alc == "area":
        return area_id is not None and area_id == ctx.usuario.area_id
    return False


def _requerir_plantilla(ctx: Contexto, area_id: int | None) -> None:
    ctx.requerir("plantillas", "modificar")
    if not _puede_plantilla(ctx, area_id):
        raise HTTPException(
            status.HTTP_403_FORBIDDEN,
            "Solo puede editar las plantillas de su área. Las generales las edita la Dirección.",
        )


@router.get("/plantillas")
def listar_plantillas(ctx: Contexto = Depends(contexto), db: Session = Depends(get_db)):
    ctx.requerir("plantillas", "modificar")
    return [_plantilla_out(p, ctx) for p in _plantillas_visibles(db, ctx, todas=True)]


def _aplicar(p: PlantillaInforme, e: PlantillaIn) -> None:
    p.nombre = e.nombre
    p.descripcion = e.descripcion
    p.area_id = e.area_id
    p.tipo_documental_id = e.tipo_documental_id
    p.activo = e.activo
    p.orden = e.orden
    p.estructura = {
        "titulo": e.titulo.strip(),
        "destinatario": e.destinatario,
        "destinatario_inicial": e.destinatario_inicial if e.destinatario else "",
        "numerar": e.numerar,
        "datos": e.datos,
        "secciones": [
            {"titulo": s.titulo.strip(), "guia": s.guia.strip(), "texto": limpiar_html(s.texto)} for s in e.secciones
        ],
    }


def _validar_referencias(db: Session, e: PlantillaIn) -> None:
    if e.area_id is not None and db.get(Area, e.area_id) is None:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Área inexistente.")
    if e.tipo_documental_id is not None and db.get(TipoDocumental, e.tipo_documental_id) is None:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Tipo documental inexistente.")
    if not e.secciones:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "La plantilla necesita al menos una sección.")


@router.post("/plantillas", status_code=201)
def crear_plantilla(entrada: PlantillaIn, ctx: Contexto = Depends(contexto), db: Session = Depends(get_db)):
    _requerir_plantilla(ctx, entrada.area_id)
    _validar_referencias(db, entrada)
    p = PlantillaInforme(creado_por=ctx.id, actualizado_por=ctx.id)
    _aplicar(p, entrada)
    db.add(p)
    db.flush()
    audit.registrar(db, ctx, "crear", "plantilla_informe", p.id, None, {"nombre": p.nombre})
    db.commit()
    db.refresh(p)
    return _plantilla_out(p, ctx)


@router.put("/plantillas/{plantilla_id}")
def modificar_plantilla(
    plantilla_id: int, entrada: PlantillaIn, ctx: Contexto = Depends(contexto), db: Session = Depends(get_db)
):
    p = db.get(PlantillaInforme, plantilla_id)
    if p is None:
        raise no_encontrado("Plantilla")
    _requerir_plantilla(ctx, p.area_id)  # la actual
    _requerir_plantilla(ctx, entrada.area_id)  # y la nueva
    _validar_referencias(db, entrada)
    antes = _plantilla_out(p)
    _aplicar(p, entrada)
    p.actualizado_por = ctx.id
    p.actualizado_en = ahora()
    audit.registrar(
        db, ctx, "modificar", "plantilla_informe", p.id, None,
        {"nombre": p.nombre, "antes": {k: antes[k] for k in ("nombre", "datos", "secciones", "activo")}},
    )
    db.commit()
    db.refresh(p)
    return _plantilla_out(p, ctx)

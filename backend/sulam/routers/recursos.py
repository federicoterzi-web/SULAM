"""Red de recursos: centros de día, centros de jubilados, residencias, instituciones
y cuidadores domiciliarios formados, con su ubicación en el mapa."""

from __future__ import annotations

import json
import uuid
from urllib.parse import urlencode
from urllib.request import Request as PedidoHttp
from urllib.request import urlopen

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import Field, field_validator
from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from .. import audit
from ..config import get_settings
from ..db import get_db
from ..deps import contexto
from ..formularios import DEPARTAMENTOS
from ..models import Recurso
from ..permissions import Contexto
from ..schemas import Entrada, _vacio_a_none
from ..security import ahora
from ..textutil import escapar_like, normalizar

router = APIRouter(tags=["recursos"])

TIPOS = [
    {"codigo": "centro_dia", "texto": "Centro de día"},
    {"codigo": "centro_jubilados", "texto": "Centro de jubilados"},
    {"codigo": "residencia", "texto": "Residencia de larga estadía"},
    {
        "codigo": "institucion",
        "texto": "Institución",
        "categorias": [
            {"codigo": "salud", "texto": "Salud (CAPS, hospital)"},
            {"codigo": "municipio", "texto": "Municipio o comuna"},
            {"codigo": "desarrollo_social", "texto": "Desarrollo social"},
            {"codigo": "justicia", "texto": "Justicia y defensorías"},
            {"codigo": "seguridad", "texto": "Seguridad (comisaría)"},
            {"codigo": "educacion", "texto": "Educación"},
            {"codigo": "organizacion_social", "texto": "Organización social o religiosa"},
            {"codigo": "otra", "texto": "Otra"},
        ],
    },
    {"codigo": "cuidador", "texto": "Cuidador/a domiciliario/a formado/a"},
]
CODIGOS_TIPO = {t["codigo"] for t in TIPOS}

# De dónde sale cada dato de la base institucional.
ORIGENES = [
    {"codigo": "relevamiento", "texto": "Relevamiento de la Dirección"},
    {"codigo": "capacitacion", "texto": "Capacitación (Participación y Sensibilización Ciudadana)"},
    {"codigo": "articulacion", "texto": "Articulación en un caso"},
    {"codigo": "derivacion", "texto": "Derivación, nota u oficio recibido"},
    {"codigo": "referencia", "texto": "Referencia de otra institución"},
    {"codigo": "otro", "texto": "Otro"},
]
CODIGOS_ORIGEN = {o["codigo"] for o in ORIGENES}
CATEGORIAS = {c["codigo"] for t in TIPOS for c in t.get("categorias", [])}

# Tucumán, para limitar la búsqueda de direcciones y validar coordenadas.
CAJA_TUCUMAN = {"oeste": -66.3, "sur": -28.1, "este": -64.4, "norte": -26.0}

CAMPOS = (
    "tipo", "categoria", "nombre", "direccion", "localidad", "departamento", "lat", "lng",
    "telefono", "telefono_alternativo", "email", "horario", "referente", "referente_cargo",
    "servicios", "observaciones", "zonas", "formacion", "disponibilidad", "origen", "origen_detalle", "activo",
)


class RecursoIn(Entrada):
    tipo: str
    categoria: str | None = None
    nombre: str = Field(min_length=2, max_length=300)
    direccion: str | None = Field(default=None, max_length=500)
    localidad: str | None = Field(default=None, max_length=200)
    departamento: str | None = Field(default=None, max_length=100)
    lat: float | None = None
    lng: float | None = None
    telefono: str | None = Field(default=None, max_length=100)
    telefono_alternativo: str | None = Field(default=None, max_length=100)
    email: str | None = Field(default=None, max_length=200)
    horario: str | None = Field(default=None, max_length=300)
    referente: str | None = Field(default=None, max_length=200)
    referente_cargo: str | None = Field(default=None, max_length=200)
    servicios: str | None = Field(default=None, max_length=5000)
    observaciones: str | None = Field(default=None, max_length=5000)
    zonas: list[str] | None = None
    formacion: str | None = Field(default=None, max_length=3000)
    disponibilidad: str | None = Field(default=None, max_length=300)
    origen: str | None = None
    origen_detalle: str | None = Field(default=None, max_length=300)
    activo: bool = True

    _limpiar = field_validator(
        "origen", "origen_detalle", "categoria", "direccion", "localidad", "departamento", "telefono", "telefono_alternativo",
        "email", "horario", "referente", "referente_cargo", "servicios", "observaciones",
        "formacion", "disponibilidad", mode="before",
    )(_vacio_a_none)


class RecursoPatch(RecursoIn):
    tipo: str | None = None  # type: ignore[assignment]
    nombre: str | None = Field(default=None, min_length=2, max_length=300)  # type: ignore[assignment]
    activo: bool | None = None  # type: ignore[assignment]


def _validar(v: dict) -> None:
    if v.get("tipo") is not None and v["tipo"] not in CODIGOS_TIPO:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Tipo de recurso inválido.")
    if v.get("categoria") is not None and v["categoria"] not in CATEGORIAS:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Categoría inválida.")
    if v.get("origen") is not None and v["origen"] not in CODIGOS_ORIGEN:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Origen inválido.")
    if (v.get("lat") is None) != (v.get("lng") is None):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Indique latitud y longitud, o ninguna.")
    if v.get("lat") is not None:
        c = CAJA_TUCUMAN
        if not (c["sur"] <= v["lat"] <= c["norte"] and c["oeste"] <= v["lng"] <= c["este"]):
            raise HTTPException(status.HTTP_400_BAD_REQUEST, "La ubicación queda fuera de la provincia de Tucumán.")
    for d in v.get("zonas") or []:
        if d not in DEPARTAMENTOS:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, f"Departamento inválido en zonas: {d}.")


def recurso_out(r: Recurso) -> dict:
    d = {c: getattr(r, c) for c in CAMPOS}
    d["id"] = str(r.id)
    d["zonas"] = r.zonas or []
    d["creado_por"] = str(r.creado_por) if r.creado_por else None
    d["actualizado_en"] = r.actualizado_en.isoformat() if r.actualizado_en else None
    return d


def _obtener(db: Session, recurso_id: uuid.UUID) -> Recurso:
    r = db.get(Recurso, recurso_id)
    if r is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Recurso inexistente.")
    return r


@router.get("/recursos/catalogo")
def catalogo(ctx: Contexto = Depends(contexto)):
    ctx.requerir("recursos", "consultar")
    cfg = get_settings()
    return {
        "tipos": TIPOS,
        "origenes": ORIGENES,
        "departamentos": DEPARTAMENTOS,
        "mapa": {
            "teselas": cfg.mapa_teselas,
            "atribucion": cfg.mapa_atribucion,
            "centro": [-26.83, -65.22],  # San Miguel de Tucumán
            "caja": CAJA_TUCUMAN,
        },
        "geocodificador": cfg.geocodificador_url is not None,
        "puede": {
            "crear": ctx.tiene("recursos", "crear"),
            "modificar": ctx.alcance("recursos", "modificar"),
        },
    }


@router.get("/recursos")
def listar(
    tipo: str | None = None,
    q: str = Query("", max_length=200),
    departamento: str | None = None,
    inactivos: bool = False,
    ctx: Contexto = Depends(contexto),
    db: Session = Depends(get_db),
):
    ctx.requerir("recursos", "consultar")
    consulta = select(Recurso)
    if not inactivos:
        consulta = consulta.where(Recurso.activo)
    if tipo:
        consulta = consulta.where(Recurso.tipo.in_(tipo.split(",")))
    if departamento:
        # Un cuidador aparece también en los departamentos donde trabaja.
        consulta = consulta.where(
            or_(Recurso.departamento == departamento, Recurso.zonas.contains([departamento]))
        )
    if q.strip():
        t = "%" + escapar_like(normalizar(q)) + "%"
        consulta = consulta.where(
            or_(
                Recurso.nombre_norm.like(t),
                Recurso.localidad.ilike("%" + escapar_like(q.strip()) + "%"),
                Recurso.referente.ilike("%" + escapar_like(q.strip()) + "%"),
                Recurso.servicios.ilike("%" + escapar_like(q.strip()) + "%"),
            )
        )
    consulta = consulta.order_by(Recurso.nombre_norm).limit(1000)
    return [recurso_out(r) for r in db.execute(consulta).scalars()]


@router.post("/recursos", status_code=201)
def crear(datos: RecursoIn, ctx: Contexto = Depends(contexto), db: Session = Depends(get_db)):
    ctx.requerir("recursos", "crear")
    v = datos.model_dump()
    _validar(v)
    if v["tipo"] != "institucion":
        v["categoria"] = None
    r = Recurso(**v, nombre_norm=normalizar(v["nombre"]), creado_por=ctx.id, actualizado_por=ctx.id)
    db.add(r)
    db.flush()
    audit.registrar(db, ctx, "crear", "recurso", r.id, detalle={"tipo": r.tipo, "nombre": r.nombre})
    db.commit()
    db.refresh(r)
    return recurso_out(r)


@router.get("/recursos/geocodificar")
def geocodificar(q: str = Query(..., min_length=4, max_length=300), ctx: Contexto = Depends(contexto)):
    """Busca una dirección de una institución o centro (no se usa para domicilios de casos)."""
    ctx.requerir("recursos", "crear")
    cfg = get_settings()
    if not cfg.geocodificador_url:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "La búsqueda de direcciones está desactivada.")
    c = CAJA_TUCUMAN
    params = urlencode(
        {
            "q": q,
            "format": "jsonv2",
            "limit": 5,
            "countrycodes": "ar",
            "viewbox": f"{c['oeste']},{c['norte']},{c['este']},{c['sur']}",
            "bounded": 1,
            "accept-language": "es",
        }
    )
    pedido = PedidoHttp(
        f"{cfg.geocodificador_url}?{params}",
        headers={"User-Agent": "SULAM/0.1 (Direccion de Adultos Mayores de Tucuman)"},
    )
    try:
        with urlopen(pedido, timeout=8) as respuesta:
            resultados = json.loads(respuesta.read().decode("utf-8"))
    except Exception:
        raise HTTPException(
            status.HTTP_502_BAD_GATEWAY,
            "No se pudo consultar el buscador de direcciones. Marque el lugar tocando el mapa.",
        )
    return [
        {"lat": float(x["lat"]), "lng": float(x["lon"]), "descripcion": x.get("display_name", "")}
        for x in resultados
        if "lat" in x and "lon" in x
    ]


@router.get("/recursos/{recurso_id}")
def ver(recurso_id: uuid.UUID, ctx: Contexto = Depends(contexto), db: Session = Depends(get_db)):
    ctx.requerir("recursos", "consultar")
    return recurso_out(_obtener(db, recurso_id))


@router.patch("/recursos/{recurso_id}")
def modificar(
    recurso_id: uuid.UUID, datos: RecursoPatch, ctx: Contexto = Depends(contexto), db: Session = Depends(get_db)
):
    alcance = ctx.requerir("recursos", "modificar")
    r = _obtener(db, recurso_id)
    if alcance == "propios" and r.creado_por != ctx.id:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Solo puede modificar los recursos que cargó usted.")
    cambios = datos.model_dump(exclude_unset=True)
    actual = {c: getattr(r, c) for c in CAMPOS}
    _validar({**actual, **cambios})
    diff = {}
    for campo, valor in cambios.items():
        if campo in ("tipo", "nombre", "activo") and valor is None:
            continue
        if getattr(r, campo) != valor:
            diff[campo] = [getattr(r, campo), valor]
            setattr(r, campo, valor)
    if r.tipo != "institucion":
        r.categoria = None
    if diff:
        r.nombre_norm = normalizar(r.nombre)
        r.actualizado_por = ctx.id
        r.actualizado_en = ahora()
        audit.registrar(db, ctx, "modificar", "recurso", r.id, detalle=json.loads(json.dumps(diff, default=str)))
        db.commit()
        db.refresh(r)
    return recurso_out(r)

"""Casos en el mapa, para organizar las salidas de visita.

Solo casos activos y dentro del alcance de consulta del usuario. La ubicación del domicilio se marca a mano o con el GPS en una
visita; nunca se consulta a servicios externos.
"""

from __future__ import annotations

import os
from datetime import timedelta

from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..db import get_db
from ..deps import contexto
from ..models import Caso, CasoAsignacion, CasoEvolucion, Persona
from ..permissions import Contexto, filtro_casos
from ..security import ahora
from ..serializers import usuario_breve

router = APIRouter(tags=["mapa"])


def punto_de_partida() -> list[float]:
    """Desde dónde salen las visitas (SULAM_PUNTO_PARTIDA="lat,lng"); por defecto, el centro de la capital."""
    valor = os.environ.get("SULAM_PUNTO_PARTIDA", "")
    try:
        lat, lng = (float(x) for x in valor.split(","))
        return [lat, lng]
    except ValueError:
        return [-26.8303, -65.2038]


@router.get("/mapa/casos")
def casos_en_el_mapa(
    de: str = Query("mios", pattern="^(mios|area|todos)$"),
    ctx: Contexto = Depends(contexto),
    db: Session = Depends(get_db),
):
    alcance = ctx.requerir("casos", "consultar")
    consulta = (
        select(Caso, Persona)
        .join(Persona, Persona.id == Caso.persona_id)
        .where(Caso.estado != "cerrado", filtro_casos(ctx, alcance), Persona.unificada_en_id.is_(None))
    )
    if de == "mios":
        consulta = consulta.where(
            Caso.id.in_(
                select(CasoAsignacion.caso_id).where(CasoAsignacion.usuario_id == ctx.id, CasoAsignacion.hasta.is_(None))
            )
        )
    elif de == "area" and ctx.usuario.area_id:
        consulta = consulta.where(Caso.area_id == ctx.usuario.area_id)
    filas = db.execute(consulta.order_by(Caso.ultima_actividad)).all()

    ids = [c.id for c, _ in filas]
    ultima: dict = {}
    for caso_id, fecha in db.execute(
        select(CasoEvolucion.caso_id, CasoEvolucion.fecha)
        .where(CasoEvolucion.caso_id.in_(ids))
        .order_by(CasoEvolucion.caso_id, CasoEvolucion.fecha.desc())
    ).all():
        ultima.setdefault(caso_id, fecha)
    limite = ahora() - timedelta(days=30)

    puntos, sin_ubicacion = [], []
    for c, p in filas:
        d = {
            "caso_id": str(c.id),
            "numero": c.numero,
            "actuacion": f"{c.numero_actuacion}/{c.anio_actuacion}" if c.numero_actuacion else c.numero,
            "estado": c.estado,
            "area": c.area.nombre if c.area else None,
            "responsables": [usuario_breve(a.usuario) for a in c.asignaciones if a.hasta is None],
            "maltrato": any(str(i).startswith("maltrato") for i in c.indicadores or []),
            "sin_actividad": c.ultima_actividad < limite,
            "ultima_evolucion": ultima[c.id].isoformat() if c.id in ultima else None,
            "persona": {
                "id": str(p.id),
                "nombre": f"{p.apellidos.upper()}, {p.nombres}",
                "domicilio": p.domicilio,
                "localidad": p.localidad,
                "departamento": p.departamento,
                "telefono": p.telefono,
            },
        }
        if p.lat is not None and p.lng is not None:
            puntos.append({**d, "lat": p.lat, "lng": p.lng})
        else:
            sin_ubicacion.append(d)
    return {"puntos": puntos, "sin_ubicacion": sin_ubicacion, "partida": punto_de_partida()}


TESELAS_PROPIAS = "/api/mapa/teselas/{z}/{x}/{y}.png"
USER_AGENT = "SULAM/0.1 (Direccion de Adultos Mayores de Tucuman; direccionadultosmayores@gmail.com)"
_DIAS_CACHE = 30


def teselas_para_el_navegador() -> str:
    """Las teselas se piden a este servidor, que las trae con un User-Agent propio y las guarda en disco, como pide la política
    de uso de OpenStreetMap (el navegador no puede identificarse y a veces lo bloquean). Si se configuró un servidor propio
    (SULAM_MAPA_TESELAS), el navegador lo usa directo."""
    return TESELAS_PROPIAS if "SULAM_MAPA_TESELAS" not in os.environ else os.environ["SULAM_MAPA_TESELAS"]


@router.get("/mapa/teselas/{z}/{x}/{y}.png")
def tesela(z: int, x: int, y: int, ctx: Contexto = Depends(contexto)):
    import time
    from urllib.request import Request as Pedido
    from urllib.request import urlopen

    from fastapi import HTTPException
    from fastapi.responses import Response

    from ..config import get_settings

    if not (0 <= z <= 19 and 0 <= x < 2**z and 0 <= y < 2**z):
        raise HTTPException(404, "Tesela inexistente.")
    cfg = get_settings()
    cabeceras = {"Cache-Control": f"private, max-age={7 * 86400}"}
    archivo = cfg.storage_dir.parent / "teselas" / str(z) / str(x) / f"{y}.png"
    try:
        if archivo.is_file() and time.time() - archivo.stat().st_mtime < _DIAS_CACHE * 86400:
            return Response(archivo.read_bytes(), media_type="image/png", headers=cabeceras)
    except OSError:
        pass
    origen = cfg.mapa_teselas.replace("{z}", str(z)).replace("{x}", str(x)).replace("{y}", str(y)).replace("{s}", "a")
    try:
        with urlopen(Pedido(origen, headers={"User-Agent": USER_AGENT, "Referer": "https://sulam.local/"}), timeout=8) as r:
            datos = r.read(1_000_000)
            tipo = r.headers.get_content_type()
    except Exception:
        # Sin internet o bloqueada: se usa la copia vieja si existe.
        if archivo.is_file():
            return Response(archivo.read_bytes(), media_type="image/png", headers={"Cache-Control": "no-store"})
        raise HTTPException(502, "No se pudo obtener el mapa.")
    if not tipo.startswith("image/"):
        raise HTTPException(502, "No se pudo obtener el mapa.")
    try:
        archivo.parent.mkdir(parents=True, exist_ok=True)
        archivo.write_bytes(datos)
    except OSError:
        pass
    return Response(datos, media_type=tipo, headers=cabeceras)


@router.get("/mapa/config")
def configuracion_del_mapa(ctx: Contexto = Depends(contexto)):
    from ..config import get_settings
    from .recursos import CAJA_TUCUMAN

    cfg = get_settings()
    return {
        "teselas": teselas_para_el_navegador(),
        "atribucion": cfg.mapa_atribucion,
        "centro": [-26.83, -65.22],
        "caja": CAJA_TUCUMAN,
        "partida": punto_de_partida(),
    }

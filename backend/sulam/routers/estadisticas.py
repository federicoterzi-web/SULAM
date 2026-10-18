"""Estadísticas: casos y funcionamiento interno (pantalla, Excel y PDF)."""
from __future__ import annotations

from datetime import date
from urllib.parse import quote

from fastapi import APIRouter, Depends, Query
from fastapi.responses import Response
from sqlalchemy.orm import Session

from .. import audit
from .. import estadisticas as E
from ..db import get_db
from ..deps import contexto
from ..permissions import Contexto

router = APIRouter(tags=["estadisticas"])


def _q(ctx, desde, hasta, area_id, f, para):
    return E.preparar(ctx, desde, hasta, area_id, f, para=para)


@router.get("/estadisticas/casos")
def estadisticas_casos(
    desde: date | None = None,
    hasta: date | None = None,
    area_id: int | None = None,
    f: str | None = Query(None, max_length=20000),
    ctx: Contexto = Depends(contexto),
    db: Session = Depends(get_db),
):
    return E.casos(db, _q(ctx, desde, hasta, area_id, f, "casos"))


@router.get("/estadisticas/interno")
def estadisticas_interno(
    desde: date | None = None,
    hasta: date | None = None,
    area_id: int | None = None,
    ctx: Contexto = Depends(contexto),
    db: Session = Depends(get_db),
):
    return E.interno(db, _q(ctx, desde, hasta, area_id, None, "interno"))


@router.get("/estadisticas/participacion")
def estadisticas_participacion(
    desde: date | None = None,
    hasta: date | None = None,
    area_id: int | None = None,
    ctx: Contexto = Depends(contexto),
    db: Session = Depends(get_db),
):
    from .. import estadisticas_participacion as EP

    return EP.participacion(db, EP.preparar(ctx, desde, hasta, area_id))


def _descarga(contenido: bytes, nombre: str, mime: str) -> Response:
    return Response(
        contenido, media_type=mime,
        headers={"Content-Disposition": f"attachment; filename*=UTF-8''{quote(nombre)}", "Cache-Control": "no-store"},
    )


XLSX = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"


@router.get("/estadisticas/{seccion}.xlsx")
def excel(
    seccion: str,
    desde: date | None = None,
    hasta: date | None = None,
    area_id: int | None = None,
    f: str | None = Query(None, max_length=20000),
    ctx: Contexto = Depends(contexto),
    db: Session = Depends(get_db),
):
    from ..estadisticas_salida import excel_casos, excel_interno, excel_participacion, nombre_archivo

    seccion = _seccion(seccion)
    q = _consulta(ctx, desde, hasta, area_id, f, seccion)
    contenido = excel_casos(db, q) if seccion == "casos" else excel_participacion(db, q) if seccion == "participacion" else excel_interno(db, q)
    audit.registrar(db, ctx, "exportar_estadisticas", "estadisticas", detalle={"seccion": seccion, "formato": "xlsx", "desde": q.desde, "hasta": q.hasta})
    db.commit()
    return _descarga(contenido, nombre_archivo(seccion, q, "xlsx"), XLSX)


@router.get("/estadisticas/{seccion}.pdf")
def pdf(
    seccion: str,
    desde: date | None = None,
    hasta: date | None = None,
    area_id: int | None = None,
    f: str | None = Query(None, max_length=20000),
    ctx: Contexto = Depends(contexto),
    db: Session = Depends(get_db),
):
    from ..estadisticas_salida import nombre_archivo, pdf_estadisticas

    seccion = _seccion(seccion)
    q = _consulta(ctx, desde, hasta, area_id, f, seccion)
    contenido = pdf_estadisticas(db, q, seccion)
    audit.registrar(db, ctx, "exportar_estadisticas", "estadisticas", detalle={"seccion": seccion, "formato": "pdf", "desde": q.desde, "hasta": q.hasta})
    db.commit()
    return _descarga(contenido, nombre_archivo(seccion, q, "pdf"), "application/pdf")


def _consulta(ctx, desde, hasta, area_id, f, seccion):
    if seccion == "participacion":
        from .. import estadisticas_participacion as EP

        return EP.preparar(ctx, desde, hasta, area_id)
    return _q(ctx, desde, hasta, area_id, f if seccion == "casos" else None, seccion)


def _seccion(s: str) -> str:
    from fastapi import HTTPException, status

    if s not in ("casos", "interno", "participacion"):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Sección inexistente.")
    return s

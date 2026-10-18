from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from sqlalchemy import text

from . import __version__
from .config import get_settings
from .db import get_engine
from .routers import admin, auth, casos, demandas, documentos, expedientes, general, ingresos, personas, recursos, contactos, mapa, informes, anses, novedades, archivo, personal, avisos, capturas, agenda, participacion, residencias, subsidios, filtros as filtros_router, estadisticas
from .routers import inicio as inicio_por_rol

API = "/api"


def crear_app() -> FastAPI:
    cfg = get_settings()
    app = FastAPI(
        title="SULAM",
        description="Sistema Único de Legajos de Adultos Mayores - Dirección de Adultos Mayores de Tucumán",
        version=__version__,
        docs_url=f"{API}/docs" if cfg.environment != "produccion" else None,
        redoc_url=None,
        openapi_url=f"{API}/openapi.json" if cfg.environment != "produccion" else None,
    )

    for r in (auth, personas, casos, demandas, expedientes, ingresos, documentos, general, inicio_por_rol, recursos, contactos, mapa, informes, anses, novedades, archivo, personal, avisos, capturas, agenda, participacion, residencias, subsidios, filtros_router, estadisticas, admin):
        app.include_router(r.router, prefix=API)

    @app.get(f"{API}/salud", tags=["general"])
    def salud():
        with get_engine().connect() as c:
            c.execute(text("SELECT 1"))
        return {"estado": "ok", "version": __version__}

    @app.middleware("http")
    async def cabeceras_seguridad(request: Request, call_next):
        respuesta = await call_next(request)
        respuesta.headers.setdefault("X-Content-Type-Options", "nosniff")
        respuesta.headers.setdefault("X-Frame-Options", "DENY")
        respuesta.headers.setdefault("Referrer-Policy", "strict-origin-when-cross-origin")
        respuesta.headers.setdefault("Permissions-Policy", "camera=(self), geolocation=(self), microphone=()")
        if request.url.path.startswith(API):
            respuesta.headers.setdefault("Cache-Control", "no-store")
        else:
            respuesta.headers.setdefault(
                "Content-Security-Policy",
                f"default-src 'self'; img-src 'self' data: blob: {_origen(cfg.mapa_teselas)}; "
                "style-src 'self' 'unsafe-inline'; "
                "frame-src 'self' blob:; object-src 'self' blob:; frame-ancestors 'none'",
            )
        return respuesta

    @app.exception_handler(404)
    async def no_encontrado(request: Request, exc):
        if request.url.path.startswith(API):
            detalle = getattr(exc, "detail", "No encontrado.")
            return JSONResponse({"detail": detalle}, status_code=404)
        return _index(cfg.frontend_dist) or JSONResponse({"detail": "No encontrado."}, status_code=404)

    dist = cfg.frontend_dist
    if dist and (dist / "index.html").is_file():
        if (dist / "assets").is_dir():
            app.mount("/assets", StaticFiles(directory=dist / "assets"), name="assets")
        if (dist / "iconos").is_dir():
            app.mount("/iconos", StaticFiles(directory=dist / "iconos"), name="iconos")

        # App instalable en el celular. El service worker no guarda datos (ver frontend/public/sw.js).
        @app.get("/manifest.webmanifest", include_in_schema=False)
        def manifiesto():
            return FileResponse(dist / "manifest.webmanifest", media_type="application/manifest+json")

        @app.get("/sw.js", include_in_schema=False)
        def service_worker():
            return FileResponse(
                dist / "sw.js",
                media_type="text/javascript",
                headers={"Cache-Control": "no-cache", "Service-Worker-Allowed": "/"},
            )

        @app.get("/", include_in_schema=False)
        def inicio():
            return _index(dist)

    return app


def _origen(url: str) -> str:
    """Origen (esquema://host) de la URL de las teselas del mapa, para permitirlo en la CSP."""
    from urllib.parse import urlsplit

    partes = urlsplit(url.replace("{s}", "a"))
    if not partes.scheme or not partes.netloc:
        return ""
    host = partes.netloc.replace("{s}.", "*.")
    return f"{partes.scheme}://{host}"


def _index(dist: Path | None):
    if dist and (dist / "index.html").is_file():
        return FileResponse(dist / "index.html", headers={"Cache-Control": "no-cache"})
    return None


app = crear_app()

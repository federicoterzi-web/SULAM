from __future__ import annotations

import hmac

from fastapi import Depends, HTTPException, Request, status
from sqlalchemy.orm import Session

from .db import get_db
from .models import Area, Rol
from .permissions import Contexto, permisos_efectivos
from .security import COOKIE_SESION, buscar_sesion_valida

METODOS_SEGUROS = {"GET", "HEAD", "OPTIONS"}
RUTAS_CON_PASSWORD_VENCIDA = {"/api/auth/me", "/api/auth/password", "/api/auth/logout"}


class UsuarioSimulado:
    """El administrador visto «como» otro rol (modo debug): mismos datos, pero con el rol y el área elegidos."""

    def __init__(self, real, rol: Rol, area: Area | None):
        self._real = real
        self.roles = [rol]
        self.area = area
        self.area_id = area.id if area else None

    def __getattr__(self, nombre):
        return getattr(self._real, nombre)


def _ver_como(request: Request, db: Session, usuario, sesion) -> Contexto | None:
    """Modo debug: quien administra puede ver SULAM con los permisos de otro rol (solo lectura)."""
    crudo = request.headers.get("x-ver-como")
    if not crudo:
        return None
    reales = permisos_efectivos(usuario)
    if ("administracion", "administrar") not in reales:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "El modo «Ver como» es solo para quien administra el sistema.")
    if request.method not in METODOS_SEGUROS and request.url.path != "/api/auth/logout":
        raise HTTPException(
            status.HTTP_403_FORBIDDEN,
            "Modo «Ver como»: es de solo lectura. Salga del modo para guardar cambios.",
        )
    try:
        rol = db.get(Rol, int(crudo))
    except ValueError:
        rol = None
    if rol is None or not rol.activo:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Rol inexistente para «Ver como».")
    area = None
    cruda_area = request.headers.get("x-ver-como-area")
    if cruda_area:
        try:
            area = db.get(Area, int(cruda_area))
        except ValueError:
            area = None
    permisos = {(p.modulo, p.accion): p.alcance for p in rol.permisos}
    permisos.setdefault(("antecedentes", "consultar"), "todos")
    permisos.setdefault(("chat", "usar"), "todos")
    return Contexto(usuario=UsuarioSimulado(usuario, rol, area), sesion=sesion, ip=ip_cliente(request), permisos=permisos)


def ip_cliente(request: Request) -> str | None:
    return request.client.host if request.client else None


def _contexto(request: Request, db: Session, exigir_password_vigente: bool) -> Contexto:
    token = request.cookies.get(COOKIE_SESION)
    if not token:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Sesión no iniciada.")
    sesion = buscar_sesion_valida(db, token)
    if sesion is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "La sesión expiró. Vuelva a ingresar.")

    if request.method not in METODOS_SEGUROS:
        enviado = request.headers.get("x-csrf-token", "")
        if not hmac.compare_digest(enviado, sesion.csrf_token):
            raise HTTPException(status.HTTP_403_FORBIDDEN, "Falta o es inválido el token CSRF.")

    usuario = sesion.usuario
    if (
        exigir_password_vigente
        and usuario.debe_cambiar_password
        and request.url.path not in RUTAS_CON_PASSWORD_VENCIDA
    ):
        raise HTTPException(
            status.HTTP_403_FORBIDDEN, "Debe cambiar su contraseña antes de continuar."
        )

    simulado = _ver_como(request, db, usuario, sesion)
    if simulado is not None:
        return simulado

    return Contexto(
        usuario=usuario,
        sesion=sesion,
        ip=ip_cliente(request),
        permisos=permisos_efectivos(usuario),
    )


def contexto(request: Request, db: Session = Depends(get_db)) -> Contexto:
    return _contexto(request, db, exigir_password_vigente=True)


def contexto_sin_exigir_cambio(request: Request, db: Session = Depends(get_db)) -> Contexto:
    return _contexto(request, db, exigir_password_vigente=False)

from __future__ import annotations

import hmac

from fastapi import Depends, HTTPException, Request, status
from sqlalchemy.orm import Session

from .db import get_db
from .permissions import Contexto, permisos_efectivos
from .security import COOKIE_SESION, buscar_sesion_valida

METODOS_SEGUROS = {"GET", "HEAD", "OPTIONS"}
RUTAS_CON_PASSWORD_VENCIDA = {"/api/auth/me", "/api/auth/password", "/api/auth/logout"}


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

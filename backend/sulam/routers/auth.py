from __future__ import annotations

from datetime import timedelta

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from .. import audit
from ..config import get_settings
from ..db import get_db
from ..deps import contexto_sin_exigir_cambio, ip_cliente
from ..models import Usuario
from ..permissions import CATALOGO, Contexto, permisos_efectivos
from ..schemas import CambioPasswordIn, LoginIn
from ..security import (
    COOKIE_SESION,
    ahora,
    crear_sesion,
    hash_password,
    hash_señuelo,
    revocar_sesiones_usuario,
    validar_password_nueva,
    verify_password,
)

router = APIRouter(prefix="/auth", tags=["autenticación"])

CREDENCIALES_INVALIDAS = "Usuario o contraseña incorrectos."


def _yo(usuario: Usuario, csrf: str, movil: bool = False) -> dict:
    cfg = get_settings()
    permisos = permisos_efectivos(usuario)
    return {
        "id": str(usuario.id),
        "usuario": usuario.usuario,
        "nombre_completo": usuario.nombre_completo,
        "area": {"id": usuario.area.id, "nombre": usuario.area.nombre} if usuario.area else None,
        "roles": [r.nombre for r in usuario.roles if r.activo],
        "permisos": {f"{m}.{a}": alc for (m, a), alc in sorted(permisos.items())},
        "debe_cambiar_password": usuario.debe_cambiar_password,
        "csrf_token": csrf,
        "modulos": {k: v["nombre"] for k, v in CATALOGO.items()},
        "sesion_movil": movil,
        "inactividad_minutos": cfg.session_idle_minutes_movil if movil else cfg.session_idle_minutes,
    }


@router.post("/login")
def login(datos: LoginIn, request: Request, response: Response, db: Session = Depends(get_db)):
    cfg = get_settings()
    usuario = db.execute(
        select(Usuario).where(func.lower(Usuario.usuario) == datos.usuario.lower())
    ).scalar_one_or_none()
    ip = ip_cliente(request)

    if usuario is None:
        verify_password(datos.password, hash_señuelo())
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, CREDENCIALES_INVALIDAS)

    momento = ahora()
    if usuario.bloqueado_hasta and usuario.bloqueado_hasta > momento:
        raise HTTPException(
            status.HTTP_423_LOCKED,
            "Usuario bloqueado temporalmente por intentos fallidos. Intente más tarde.",
        )

    if not usuario.activo or not verify_password(datos.password, usuario.password_hash):
        usuario.intentos_fallidos += 1
        detalle = {"intentos": usuario.intentos_fallidos}
        if usuario.intentos_fallidos >= cfg.max_failed_logins:
            usuario.bloqueado_hasta = momento + timedelta(minutes=cfg.lockout_minutes)
            usuario.intentos_fallidos = 0
            detalle["bloqueado_hasta"] = usuario.bloqueado_hasta
        audit.registrar(
            db, None, "login_fallido", "usuario", usuario.id, detalle=detalle,
            usuario_id=usuario.id, ip=ip,
        )
        db.commit()
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, CREDENCIALES_INVALIDAS)

    usuario.intentos_fallidos = 0
    usuario.bloqueado_hasta = None
    usuario.ultimo_acceso = momento
    token, sesion = crear_sesion(
        db, usuario, ip, request.headers.get("user-agent"), movil=datos.dispositivo == "movil"
    )
    audit.registrar(
        db, None, "login", "usuario", usuario.id, usuario_id=usuario.id, ip=ip,
        detalle={"dispositivo": datos.dispositivo},
    )
    db.commit()

    response.set_cookie(
        COOKIE_SESION,
        token,
        httponly=True,
        secure=cfg.cookie_secure,
        samesite="strict",
        max_age=cfg.session_hours * 3600,
        path="/",
    )
    return _yo(usuario, sesion.csrf_token, sesion.movil)


@router.post("/logout")
def logout(response: Response, ctx: Contexto = Depends(contexto_sin_exigir_cambio), db: Session = Depends(get_db)):
    ctx.sesion.revocada_en = ahora()
    audit.registrar(db, ctx, "logout", "usuario", ctx.id)
    db.commit()
    response.delete_cookie(COOKIE_SESION, path="/")
    return {"ok": True}


@router.get("/me")
def me(ctx: Contexto = Depends(contexto_sin_exigir_cambio)):
    return _yo(ctx.usuario, ctx.sesion.csrf_token, ctx.sesion.movil)


@router.post("/password")
def cambiar_password(
    datos: CambioPasswordIn,
    ctx: Contexto = Depends(contexto_sin_exigir_cambio),
    db: Session = Depends(get_db),
):
    usuario = ctx.usuario
    if not verify_password(datos.password_actual, usuario.password_hash):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "La contraseña actual no es correcta.")
    error = validar_password_nueva(datos.password_nueva)
    if error:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, error)
    if datos.password_nueva == datos.password_actual:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "La nueva contraseña debe ser distinta.")
    usuario.password_hash = hash_password(datos.password_nueva)
    usuario.debe_cambiar_password = False
    revocar_sesiones_usuario(db, usuario.id, excepto=ctx.sesion.id)
    audit.registrar(db, ctx, "cambio_password", "usuario", usuario.id)
    db.commit()
    return _yo(usuario, ctx.sesion.csrf_token, ctx.sesion.movil)


@router.get("/direccion-publica")
def direccion_publica(request: Request, ctx: Contexto = Depends(contexto_sin_exigir_cambio)):
    """Dirección que llevan los QR impresos y si funciona desde un celular."""
    from ..security import url_publica

    url, sirve = url_publica(request)
    return {"url": url, "sirve_desde_otros_dispositivos": sirve}

"""Contraseñas y sesiones.

- Contraseñas: scrypt (biblioteca estándar de Python), con sal aleatoria.
- Sesiones: token opaco en cookie HttpOnly; en la base solo se guarda su hash.
  Cada sesión tiene un token CSRF que el frontend envía en la cabecera
  X-CSRF-Token en toda operación que modifica datos.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import secrets
from datetime import datetime, timedelta, timezone

from sqlalchemy.orm import Session

from .config import get_settings
from .models import Sesion, Usuario

_N, _R, _P, _DKLEN = 2**15, 8, 1, 64
COOKIE_SESION = "sulam_sesion"
MIN_LARGO_PASSWORD = 10


def hash_password(password: str) -> str:
    salt = secrets.token_bytes(16)
    dk = hashlib.scrypt(password.encode(), salt=salt, n=_N, r=_R, p=_P, dklen=_DKLEN, maxmem=2**26)
    return "scrypt${}${}${}${}${}".format(
        _N, _R, _P, base64.b64encode(salt).decode(), base64.b64encode(dk).decode()
    )


def verify_password(password: str, stored: str) -> bool:
    try:
        algo, n, r, p, salt_b64, dk_b64 = stored.split("$")
        if algo != "scrypt":
            return False
        salt = base64.b64decode(salt_b64)
        expected = base64.b64decode(dk_b64)
        dk = hashlib.scrypt(
            password.encode(), salt=salt, n=int(n), r=int(r), p=int(p), dklen=len(expected),
            maxmem=2**26,
        )
        return hmac.compare_digest(dk, expected)
    except (ValueError, TypeError):
        return False


# Hash fijo para igualar el tiempo de respuesta cuando el usuario no existe.
_HASH_SEÑUELO: str | None = None


def hash_señuelo() -> str:
    global _HASH_SEÑUELO
    if _HASH_SEÑUELO is None:
        _HASH_SEÑUELO = hash_password(secrets.token_urlsafe(16))
    return _HASH_SEÑUELO


def validar_password_nueva(password: str) -> str | None:
    if len(password) < MIN_LARGO_PASSWORD:
        return f"La contraseña debe tener al menos {MIN_LARGO_PASSWORD} caracteres."
    if password.isdigit() or password.isalpha():
        return "La contraseña debe combinar letras con números o símbolos."
    return None


def ahora() -> datetime:
    return datetime.now(timezone.utc)


def _hash_token(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def crear_sesion(
    db: Session, usuario: Usuario, ip: str | None, user_agent: str | None, movil: bool = False
) -> tuple[str, Sesion]:
    cfg = get_settings()
    token = secrets.token_urlsafe(32)
    momento = ahora()
    sesion = Sesion(
        usuario_id=usuario.id,
        token_hash=_hash_token(token),
        csrf_token=secrets.token_urlsafe(24),
        expira_en=momento + timedelta(hours=cfg.session_hours),
        ultimo_uso=momento,
        ip=ip,
        user_agent=(user_agent or "")[:300],
        movil=movil,
    )
    db.add(sesion)
    db.flush()
    return token, sesion


def buscar_sesion_valida(db: Session, token: str) -> Sesion | None:
    cfg = get_settings()
    sesion = db.query(Sesion).filter(Sesion.token_hash == _hash_token(token)).one_or_none()
    if sesion is None or sesion.revocada_en is not None:
        return None
    momento = ahora()
    if sesion.expira_en <= momento:
        return None
    inactividad = cfg.session_idle_minutes_movil if sesion.movil else cfg.session_idle_minutes
    if sesion.ultimo_uso + timedelta(minutes=inactividad) <= momento:
        return None
    if not sesion.usuario.activo:
        return None
    # Se actualiza el último uso como máximo una vez por minuto.
    if momento - sesion.ultimo_uso > timedelta(minutes=1):
        sesion.ultimo_uso = momento
        db.commit()
    return sesion


def revocar_sesiones_usuario(db: Session, usuario_id, excepto=None) -> None:
    q = db.query(Sesion).filter(Sesion.usuario_id == usuario_id, Sesion.revocada_en.is_(None))
    if excepto is not None:
        q = q.filter(Sesion.id != excepto)
    for s in q:
        s.revocada_en = ahora()


# ---------------------------------------------------------------- dirección pública

_LOCALES = {"localhost", "127.0.0.1", "::1", "0.0.0.0"}


def _ip_de_red() -> str | None:
    """IP de esta máquina en la red local (sin enviar nada: UDP no conecta)."""
    import socket

    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
            s.connect(("10.255.255.255", 1))
            ip = s.getsockname()[0]
        return None if ip.startswith("127.") else ip
    except OSError:
        return None


def url_publica(request) -> tuple[str, bool]:
    """Dirección para los QR y si sirve desde otro dispositivo.

    1. SULAM_URL_PUBLICA (o https://SULAM_DOMINIO) si está configurada.
    2. La dirección con la que se abrió SULAM, si no es «localhost».
    3. Abierto como «localhost», fuera de Docker y escuchando en la red: la IP de esta máquina.
    Si nada de eso sirve, devuelve la dirección local y False.
    """
    from pathlib import Path

    cfg = get_settings()
    if cfg.url_publica:
        return cfg.url_publica, True
    base = str(request.base_url).rstrip("/")
    host = request.url.hostname or ""
    if host not in _LOCALES:
        return base, True
    import os

    # Solo si SULAM escucha en la red (servidor --host 0.0.0.0) y no está dentro de Docker.
    escucha_en_red = os.environ.get("SULAM_ESCUCHA", "127.0.0.1") not in _LOCALES - {"0.0.0.0"}
    ip = _ip_de_red() if escucha_en_red and not Path("/.dockerenv").exists() else None
    if ip:
        puerto = f":{request.url.port}" if request.url.port else ""
        return f"{request.url.scheme}://{ip}{puerto}", True
    return base, False

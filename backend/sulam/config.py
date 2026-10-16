"""Configuración de SULAM.

Se lee de variables de entorno. Si existe un archivo `.env` en el directorio
de trabajo (o en la raíz del repositorio), se cargan sus valores sin pisar
variables ya definidas en el entorno.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path


def _load_dotenv() -> None:
    for candidate in (Path.cwd() / ".env", Path(__file__).resolve().parents[2] / ".env"):
        if not candidate.is_file():
            continue
        for raw in candidate.read_text(encoding="utf-8").splitlines():
            line = raw.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, value = line.split("=", 1)
            key = key.strip()
            value = value.strip().strip('"').strip("'")
            os.environ.setdefault(key, value)
        break


def _bool(value: str | None, default: bool) -> bool:
    if value is None or value == "":
        return default
    return value.strip().lower() in {"1", "true", "si", "sí", "yes", "on"}


@dataclass(frozen=True)
class Settings:
    database_url: str
    storage_dir: Path
    backup_dir: Path
    max_upload_mb: int
    session_hours: int
    session_idle_minutes: int
    cookie_secure: bool
    max_failed_logins: int
    lockout_minutes: int
    frontend_dist: Path | None
    environment: str
    allowed_mime: tuple[str, ...] = field(
        default=("application/pdf", "image/jpeg", "image/png")
    )

    @property
    def max_upload_bytes(self) -> int:
        return self.max_upload_mb * 1024 * 1024


@lru_cache
def get_settings() -> Settings:
    _load_dotenv()
    base = Path(os.environ.get("SULAM_DATA_DIR", "./datos")).resolve()
    dist = os.environ.get("SULAM_FRONTEND_DIST")
    default_dist = Path(__file__).resolve().parents[2] / "frontend" / "dist"
    return Settings(
        database_url=os.environ.get(
            "SULAM_DATABASE_URL", "postgresql+psycopg://sulam:sulam@localhost:5432/sulam"
        ),
        storage_dir=Path(os.environ.get("SULAM_STORAGE_DIR", base / "archivos")).resolve(),
        backup_dir=Path(os.environ.get("SULAM_BACKUP_DIR", base / "respaldos")).resolve(),
        max_upload_mb=int(os.environ.get("SULAM_MAX_UPLOAD_MB", "20")),
        session_hours=int(os.environ.get("SULAM_SESSION_HOURS", "10")),
        session_idle_minutes=int(os.environ.get("SULAM_SESSION_IDLE_MINUTES", "60")),
        cookie_secure=_bool(os.environ.get("SULAM_COOKIE_SECURE"), False),
        max_failed_logins=int(os.environ.get("SULAM_MAX_FAILED_LOGINS", "5")),
        lockout_minutes=int(os.environ.get("SULAM_LOCKOUT_MINUTES", "15")),
        frontend_dist=Path(dist).resolve() if dist else default_dist,
        environment=os.environ.get("SULAM_ENV", "desarrollo"),
    )

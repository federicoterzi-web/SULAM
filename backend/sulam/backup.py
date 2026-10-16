"""Respaldo y restauración: base de datos (pg_dump) + archivos documentales.

Un respaldo es un único archivo .tar.gz que contiene:
  - base.dump        volcado de PostgreSQL en formato personalizado
  - archivos/...     copia del almacenamiento local
  - manifiesto.json  fecha, versión y SHA-256 de cada componente

La restauración verifica el manifiesto antes de tocar nada.
"""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import subprocess
import tarfile
import tempfile
from datetime import datetime
from pathlib import Path
from urllib.parse import unquote, urlparse

from . import __version__
from .config import get_settings


def _conexion_libpq(url: str) -> tuple[list[str], dict]:
    """Convierte la URL de SQLAlchemy en argumentos y entorno para pg_dump/pg_restore."""
    u = urlparse(url.replace("+psycopg", "", 1))
    env = dict(os.environ)
    if u.password:
        env["PGPASSWORD"] = unquote(u.password)
    args = [
        "--host", u.hostname or "localhost",
        "--port", str(u.port or 5432),
        "--username", unquote(u.username or "postgres"),
        "--dbname", u.path.lstrip("/"),
    ]
    return args, env


def _sha256(ruta: Path) -> str:
    h = hashlib.sha256()
    with open(ruta, "rb") as f:
        while b := f.read(1024 * 1024):
            h.update(b)
    return h.hexdigest()


def _herramienta(nombre: str) -> str:
    ruta = shutil.which(nombre)
    if ruta is None:
        raise RuntimeError(
            f"No se encontró '{nombre}'. Instale las herramientas cliente de PostgreSQL "
            "(en Windows vienen con el instalador de PostgreSQL) y agréguelas al PATH."
        )
    return ruta


def respaldar(destino: Path | None = None) -> Path:
    cfg = get_settings()
    destino_dir = Path(destino or cfg.backup_dir)
    destino_dir.mkdir(parents=True, exist_ok=True)
    marca = datetime.now().strftime("%Y%m%d-%H%M%S")
    salida = destino_dir / f"sulam-respaldo-{marca}.tar.gz"

    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        dump = tmp / "base.dump"
        args, env = _conexion_libpq(cfg.database_url)
        subprocess.run(
            [_herramienta("pg_dump"), "--format=custom", "--no-owner", "--no-privileges", "--file", str(dump), *args],
            check=True,
            env=env,
        )
        archivos: dict[str, str] = {}
        raiz = cfg.storage_dir
        if raiz.is_dir():
            for ruta in sorted(raiz.glob("??/??/*")):
                if ruta.is_file():
                    archivos[str(ruta.relative_to(raiz)).replace(os.sep, "/")] = _sha256(ruta)
        manifiesto = {
            "sistema": "SULAM",
            "version": __version__,
            "fecha": datetime.now().isoformat(timespec="seconds"),
            "base": {"archivo": "base.dump", "sha256": _sha256(dump)},
            "archivos": archivos,
        }
        (tmp / "manifiesto.json").write_text(json.dumps(manifiesto, indent=2, ensure_ascii=False), encoding="utf-8")

        parcial = salida.with_suffix(".parcial")
        with tarfile.open(parcial, "w:gz") as tar:
            tar.add(tmp / "manifiesto.json", arcname="manifiesto.json")
            tar.add(dump, arcname="base.dump")
            for rel in archivos:
                tar.add(raiz / rel, arcname=f"archivos/{rel}")
        os.replace(parcial, salida)
    return salida


def verificar_respaldo(archivo: Path, extraer_en: Path) -> dict:
    with tarfile.open(archivo, "r:gz") as tar:
        tar.extractall(extraer_en, filter="data")
    manifiesto = json.loads((extraer_en / "manifiesto.json").read_text(encoding="utf-8"))
    if manifiesto.get("sistema") != "SULAM":
        raise RuntimeError("El archivo no es un respaldo de SULAM.")
    if _sha256(extraer_en / "base.dump") != manifiesto["base"]["sha256"]:
        raise RuntimeError("El volcado de la base está dañado (no coincide el SHA-256).")
    for rel, sha in manifiesto["archivos"].items():
        ruta = extraer_en / "archivos" / rel
        if not ruta.is_file() or _sha256(ruta) != sha:
            raise RuntimeError(f"Archivo documental dañado o faltante en el respaldo: {rel}")
    return manifiesto


def restaurar(archivo: Path) -> dict:
    """Reemplaza la base y los archivos actuales por los del respaldo."""
    cfg = get_settings()
    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        manifiesto = verificar_respaldo(Path(archivo), tmp)
        args, env = _conexion_libpq(cfg.database_url)
        subprocess.run(
            [
                _herramienta("pg_restore"), "--clean", "--if-exists", "--no-owner", "--no-privileges",
                "--single-transaction", *args, str(tmp / "base.dump"),
            ],
            check=True,
            env=env,
        )
        raiz = cfg.storage_dir
        raiz.mkdir(parents=True, exist_ok=True)
        for rel in manifiesto["archivos"]:
            destino = raiz / rel
            destino.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(tmp / "archivos" / rel, destino)
    return manifiesto
